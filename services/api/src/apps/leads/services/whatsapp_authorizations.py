"""Autorizaciones de WhatsApp (Meta) por conexión — PROD-04B.

Único camino de escritura y de resolución de `WhatsAppAuthorization`:
creación, asociación explícita a canales, rotación, revocación local y
resolución interna del token vigente de un canal.

Reglas:
- Solo administración interna: el actor es personal de plataforma con rol
  `superadmin` u `operations` (no hay endpoints ni frontend en este slice).
- Una autorización con dueño solo sirve a canales de ese Business; las de
  plataforma (sin dueño) requieren `platform=True` explícito al crearse.
- El token se recibe ya leído de stdin/env por el llamador, se cifra con
  `crypto.py` y nunca vuelve a salir salvo por `resolve_channel_access_token`.
- Auditoría estricta (`record_platform_action`) en la misma transacción, con
  metadatos únicamente: si falla, la operación se revierte.
- Lock order: autorización y luego canal, en todas las operaciones.
- Revocar o rotar es LOCAL: no invalida el token ante Meta (no hay llamadas
  a Meta). La auditoría lo deja explícito (`meta_revocation`).
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.accounts.platform_audit import record_platform_action
from apps.business.models import Business

from .. import errors
from ..crypto import AgentSecretEncryptionError
from ..models import WABA_ID_REGEX, AgentChannel, AgentInstance, WhatsAppAuthorization
from .receiver import resolve_channel_by_phone

logger = logging.getLogger('apps.leads.receiver')

ADMIN_ROLES = frozenset({'superadmin', 'operations'})
TOKEN_MIN_LENGTH = 20
TOKEN_MAX_LENGTH = 4096
_TOKEN_RE = re.compile(r'^[\x21-\x7e]+$')  # ASCII visible, sin espacios
_WABA_RE = re.compile(WABA_ID_REGEX)
META_REVOCATION_NOT_PERFORMED = 'not_performed'


class WhatsAppAuthorizationError(Exception):
    """Error de dominio con código técnico; el mensaje nunca incluye el token."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> WhatsAppAuthorizationError:
    return WhatsAppAuthorizationError(code, message)


def _require_admin(actor) -> None:
    profile = getattr(actor, 'account_profile', None)
    if (
        actor is None or not getattr(actor, 'is_active', False) or profile is None
        or not profile.is_platform_staff or profile.internal_role not in ADMIN_ROLES
    ):
        raise _fail('actor_not_authorized', 'Solo personal de plataforma (superadmin/operations).')


def _validate_token(token) -> None:
    if not isinstance(token, str) or not (TOKEN_MIN_LENGTH <= len(token) <= TOKEN_MAX_LENGTH):
        raise _fail('invalid_token', f'Token inválido: entre {TOKEN_MIN_LENGTH} y {TOKEN_MAX_LENGTH} caracteres.')
    if not _TOKEN_RE.fullmatch(token):
        raise _fail('invalid_token', 'Token inválido: solo caracteres visibles, sin espacios.')


def _validate_expiry(expires_at: dt.datetime | None) -> None:
    if expires_at is None:
        return
    if timezone.is_naive(expires_at):
        raise _fail('invalid_expires_at', 'expires_at debe tener zona horaria.')
    if expires_at <= timezone.now():
        raise _fail('invalid_expires_at', 'expires_at debe ser futuro.')


def _is_expired(authorization: WhatsAppAuthorization, now: dt.datetime) -> bool:
    return authorization.expires_at is not None and authorization.expires_at <= now


def _audit(action: str, *, authorization: WhatsAppAuthorization, actor, business=None, **details) -> None:
    channels = list(
        AgentChannel.objects.filter(whatsapp_authorization=authorization)
        .order_by('created_at').values('id', 'business_id')
    )
    scope = 'platform' if authorization.is_platform else 'business'
    record_platform_action(
        action=action, actor=actor,
        business=business if business is not None else authorization.owner_business,
        # Sin Business solo una autorización de plataforma, y explícitamente.
        platform_scope=business is None and authorization.is_platform,
        entity_type='whatsapp_authorization', entity_id=str(authorization.pk),
        details={
            'scope': scope,
            'status': authorization.status,
            'expires_at': authorization.expires_at.isoformat() if authorization.expires_at else None,
            'channel_ids': [str(c['id']) for c in channels],
            'business_ids': sorted({c['business_id'] for c in channels}),
            **details,
        },
    )


def _locked_authorization(authorization_id) -> WhatsAppAuthorization:
    authorization = WhatsAppAuthorization.objects.select_for_update().filter(pk=authorization_id).first()
    if authorization is None:
        raise _fail('whatsapp_authorization_not_found', 'Autorización inexistente.')
    return authorization


def create_whatsapp_authorization(
    *, token: str, actor, owner_business: Business | None = None, platform: bool = False,
    expires_at: dt.datetime | None = None,
) -> WhatsAppAuthorization:
    """Crea una autorización activa. Sin dueño solo con `platform=True`."""
    _require_admin(actor)
    if (owner_business is None) != platform:
        raise _fail(
            'invalid_owner', 'Indicar un Business dueño, o platform=True sin dueño (excepcional).',
        )
    _validate_token(token)
    _validate_expiry(expires_at)
    with transaction.atomic():
        authorization = WhatsAppAuthorization(owner_business=owner_business, expires_at=expires_at)
        authorization.set_token(token)
        authorization.save()
        _audit('WHATSAPP_AUTHORIZATION_CREATED', authorization=authorization, actor=actor)
    return authorization


def associate_channel(*, channel_id, authorization_id, waba_id: str, actor) -> AgentChannel:
    """Asocia explícitamente un canal activo a una autorización vigente.

    Reasignar a otra autorización es la misma operación (queda auditada).
    """
    _require_admin(actor)
    if not isinstance(waba_id, str) or not _WABA_RE.fullmatch(waba_id):
        raise _fail('invalid_waba_id', 'waba_id inválido: solo dígitos, 1 a 32.')
    with transaction.atomic():
        authorization = _locked_authorization(authorization_id)
        channel = AgentChannel.objects.select_for_update().filter(pk=channel_id).first()
        if channel is None or not channel.is_active:
            raise _fail('channel_not_active', 'Canal inexistente o inactivo.')
        if authorization.status != WhatsAppAuthorization.Status.ACTIVE or _is_expired(authorization, timezone.now()):
            raise _fail('whatsapp_authorization_unusable', 'Solo se asocian autorizaciones activas y vigentes.')
        if not authorization.is_platform and authorization.owner_business_id != channel.business_id:
            raise _fail('whatsapp_authorization_owner_mismatch', 'La autorización pertenece a otro negocio.')
        previous = channel.whatsapp_authorization_id
        if previous == authorization.pk and channel.waba_id == waba_id:
            return channel
        channel.whatsapp_authorization = authorization
        channel.waba_id = waba_id
        channel.save(update_fields=['whatsapp_authorization', 'waba_id'])
        _audit(
            'WHATSAPP_AUTHORIZATION_LINKED', authorization=authorization, actor=actor, business=channel.business,
            channel_id=str(channel.pk), previous_authorization_id=str(previous) if previous else None,
        )
    return channel


def rotate_whatsapp_authorization(
    *, authorization_id, token: str, actor, expires_at: dt.datetime | None = None,
) -> WhatsAppAuthorization:
    """Reemplaza el token en la misma fila (los canales siguen asociados).

    Una revocada no se rota: se crea otra. Una inválida o vencida vuelve a
    `active` con el token nuevo. El token anterior sigue válido ante Meta
    hasta que se revoque allá.
    """
    _require_admin(actor)
    _validate_token(token)
    _validate_expiry(expires_at)
    with transaction.atomic():
        authorization = _locked_authorization(authorization_id)
        if authorization.status == WhatsAppAuthorization.Status.REVOKED:
            raise _fail('whatsapp_authorization_revoked', 'Autorización revocada: crear una nueva.')
        previous_status = authorization.status
        authorization.set_token(token)
        authorization.status = WhatsAppAuthorization.Status.ACTIVE
        authorization.expires_at = expires_at
        authorization.save(update_fields=['encrypted_access_token', 'status', 'expires_at', 'updated_at'])
        _audit(
            'WHATSAPP_AUTHORIZATION_ROTATED', authorization=authorization, actor=actor,
            previous_status=previous_status, meta_revocation=META_REVOCATION_NOT_PERFORMED,
        )
    return authorization


def revoke_whatsapp_authorization(*, authorization_id, actor) -> WhatsAppAuthorization:
    """Revocación LOCAL: deja de resolverse para todos sus canales. Idempotente."""
    _require_admin(actor)
    with transaction.atomic():
        authorization = _locked_authorization(authorization_id)
        if authorization.status == WhatsAppAuthorization.Status.REVOKED:
            return authorization
        previous_status = authorization.status
        authorization.status = WhatsAppAuthorization.Status.REVOKED
        authorization.revoked_at = timezone.now()
        authorization.save(update_fields=['status', 'revoked_at', 'updated_at'])
        _audit(
            'WHATSAPP_AUTHORIZATION_REVOKED', authorization=authorization, actor=actor,
            previous_status=previous_status, meta_revocation=META_REVOCATION_NOT_PERFORMED,
        )
    return authorization


@dataclass(frozen=True)
class ChannelWhatsAppCredential:
    channel: AgentChannel
    access_token: str
    expires_at: dt.datetime | None

    def __repr__(self) -> str:  # nunca el token
        return f'<ChannelWhatsAppCredential channel={self.channel.pk}>'


_CREDENTIAL_PROBLEMS = {
    'channel_not_active': 'Canal inexistente o inactivo.',
    'whatsapp_authorization_missing': 'El canal no tiene autorización de WhatsApp.',
    'whatsapp_authorization_owner_mismatch': 'La autorización pertenece a otro negocio.',
    'whatsapp_authorization_revoked': 'Autorización revocada.',
    'whatsapp_authorization_invalid': 'Autorización rechazada por Meta.',
    'whatsapp_authorization_expired': 'Autorización vencida.',
    'whatsapp_waba_missing': 'El canal no tiene WABA asociada.',
}


def channel_credential_problem(channel: AgentChannel | None, now: dt.datetime) -> str | None:
    """Primera regla local que impide entregar la credencial de un canal, o `None`.

    Pura: usa solo metadatos ya cargados (`channel.whatsapp_authorization`),
    nunca descifra ni consulta a Meta. Es la regla única de
    `resolve_channel_whatsapp_credential` y del estado de Platform Admin.
    """
    if channel is None or not channel.is_active:
        return 'channel_not_active'
    authorization = channel.whatsapp_authorization
    if authorization is None:
        return 'whatsapp_authorization_missing'
    if not authorization.is_platform and authorization.owner_business_id != channel.business_id:
        return 'whatsapp_authorization_owner_mismatch'
    if authorization.status == WhatsAppAuthorization.Status.REVOKED:
        return 'whatsapp_authorization_revoked'
    if authorization.status == WhatsAppAuthorization.Status.INVALID:
        return 'whatsapp_authorization_invalid'
    if _is_expired(authorization, now):
        return 'whatsapp_authorization_expired'
    if not channel.waba_id:
        return 'whatsapp_waba_missing'
    return None


def resolve_channel_whatsapp_credential(channel_id) -> ChannelWhatsAppCredential:
    """Credencial vigente de un canal: canal + token + vencimiento.

    Fail-closed: canal inactivo, sin autorización o sin WABA, revocada,
    inválida, vencida o de otro negocio ⇒ error; nunca un token. Un fallo de
    descifrado propaga `AgentSecretEncryptionError` (sin fallback a texto
    plano). Solo lectura: una sola consulta, sin locks ni escrituras.
    """
    channel = (
        AgentChannel.objects.select_related('whatsapp_authorization')
        .filter(pk=channel_id).first()
    )
    problem = channel_credential_problem(channel, timezone.now())
    if problem is not None:
        raise _fail(problem, _CREDENTIAL_PROBLEMS[problem])
    authorization = channel.whatsapp_authorization
    return ChannelWhatsAppCredential(
        channel=channel, access_token=authorization.get_token(), expires_at=authorization.expires_at,
    )


def resolve_channel_access_token(channel_id) -> str:
    """Token vigente de un canal (uso interno). Ver `resolve_channel_whatsapp_credential`."""
    return resolve_channel_whatsapp_credential(channel_id).access_token


# PROD-04C: contrato de entrega al agente. Sube solo ante cambios
# incompatibles de forma; los aditivos no lo mueven.
AGENT_WHATSAPP_CREDENTIAL_CONTRACT_VERSION = 1


def agent_whatsapp_credential(agent_instance: AgentInstance, *, phone_number_id: str) -> dict:
    """Payload del GET HMAC del agente. Solo lectura: no crea ni modifica nada.

    El Business sale del canal activo de la instancia autenticada
    (`resolve_channel_by_phone`). Entregar la credencial no autoriza IA ni el
    envío de mensajes, ni prueba permisos reales ante Meta: es solo el token
    que Mi Rubro tiene guardado para este canal.
    """
    channel = resolve_channel_by_phone(agent_instance, phone_number_id)
    try:
        credential = resolve_channel_whatsapp_credential(channel.pk)
    except WhatsAppAuthorizationError as exc:
        if exc.code == 'channel_not_active':
            raise errors.channel_disabled()
        raise errors.AgentApiError(403, exc.code, 'Credencial de WhatsApp no disponible para este canal.')
    except AgentSecretEncryptionError:
        # Sin el mensaje de la excepción ni valores: solo el canal.
        logger.error('agent_whatsapp_credential_undecryptable channel_id=%s', channel.pk)
        raise errors.unavailable()
    resolved = credential.channel
    # Contraste entre las dos lecturas: el canal no cambió de instancia,
    # negocio ni número en el medio (reasignación concurrente).
    if (
        resolved.agent_instance_id != agent_instance.id or resolved.business_id != channel.business_id
        or resolved.phone_number_id != channel.phone_number_id
    ):
        raise errors.channel_disabled()
    return {
        'ok': True,
        'contract_version': AGENT_WHATSAPP_CREDENTIAL_CONTRACT_VERSION,
        'business_id': channel.business_id,
        'phone_number_id': resolved.phone_number_id,
        'waba_id': resolved.waba_id,
        'access_token': credential.access_token,
        'expires_at': credential.expires_at.isoformat() if credential.expires_at else None,
    }


# ── PROD-08E1: estado local de conexiones para Platform Admin ────────────────

ADMIN_WHATSAPP_CONNECTIONS_CONTRACT_VERSION = 1


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _authorization_block(channel: AgentChannel, now: dt.datetime) -> dict | None:
    """Metadatos de la autorización del canal. Nunca el token (ni cifrado).

    Una autorización de plataforma puede cubrir canales de otros negocios: no
    se informa cuáles ni cuántos. Si el dueño es otro negocio, tampoco se
    informa su id.
    """
    authorization = channel.whatsapp_authorization
    if authorization is None:
        return None
    return {
        'id': str(authorization.pk),
        'kind': 'platform' if authorization.is_platform else 'business',
        'owned_by_this_business': (
            None if authorization.is_platform else authorization.owner_business_id == channel.business_id
        ),
        'status': authorization.status,
        'expired': _is_expired(authorization, now),
        'expires_at': _iso(authorization.expires_at),
        'revoked_at': _iso(authorization.revoked_at),
        'created_at': _iso(authorization.created_at),
        'updated_at': _iso(authorization.updated_at),
    }


def admin_whatsapp_connections(business: Business) -> dict:
    """Canales WhatsApp del Business y su estado LOCAL. Solo lectura.

    Sin escrituras, locks, descifrado ni llamadas a Meta: `local_status`
    describe lo que Mi Rubro tiene registrado (la misma regla con la que
    entrega la credencial al agente), nunca conectividad real, permisos en
    Meta, agente online ni capacidad de envío.
    """
    now = timezone.now()
    channels = (
        AgentChannel.objects.filter(business=business)
        .select_related('agent_instance', 'whatsapp_authorization')
        .order_by('-is_active', '-created_at', 'id')
    )
    rows = []
    for channel in channels:
        instance = channel.agent_instance
        problem = channel_credential_problem(channel, now)
        if problem is None and not instance.is_enabled:
            problem = 'agent_instance_disabled'
        rows.append({
            'id': str(channel.pk),
            'provider': channel.provider,
            'phone_number_id': channel.phone_number_id,
            'waba_id': channel.waba_id or None,
            'is_active': channel.is_active,
            'created_at': _iso(channel.created_at),
            'deactivated_at': _iso(channel.deactivated_at),
            'agent_instance': {
                'external_id': instance.external_id,
                'name': instance.name,
                'is_enabled': instance.is_enabled,
                'disabled_at': _iso(instance.disabled_at),
            },
            'authorization': _authorization_block(channel, now),
            # `credential_ready`: Mi Rubro entregaría al agente la credencial guardada.
            'local_status': problem or 'credential_ready',
        })
    return {
        'contract_version': ADMIN_WHATSAPP_CONNECTIONS_CONTRACT_VERSION,
        'business_id': business.pk,
        'evaluated_at': now.isoformat(),
        'channels': rows,
        'external_verification': {
            'performed': False,
            'meta_connectivity': 'unknown',
            'detail': 'Estado local de Mi Rubro; no se consultó a Meta ni al agente.',
        },
    }
