"""Vinculación segura de recursos WhatsApp a un comercio — PROD-10B2.

`link_whatsapp_channel` es la operación interna común de la vinculación
asistida y de Embedded Signup (solo cambia `source`). Compone lo existente:

1. Validaciones locales baratas, sin locks: actor superadmin, cliente HQ con
   Recepcionista no cancelada (`admin_reception_business`), instancia
   compartida configurada y habilitada, y conflictos visibles del número.
2. `verify_whatsapp_resources` (PROD-10B1): solo lecturas a Meta, FUERA de
   cualquier transacción o lock.
3. Una transacción: lock del Business → revalidación local → (autorización
   existente → canal, el orden de `associate_channel`) →
   `create_whatsapp_authorization` + alta o reutilización del `AgentChannel`
   + `associate_channel` + evidencia + auditoría estricta. Cualquier falla
   revierte todo: no quedan autorizaciones huérfanas.

No rota, reemplaza, reasigna, desactiva ni revoca: cualquier diferencia con
una conexión existente (otro negocio, otra instancia, otra WABA, otra
credencial) se rechaza y queda para los servicios específicos. No suscribe
webhooks, no registra números y no toca la atención automática ni la
configuración del agente.

La verificación prueba que el token es de nuestra app y cubre la WABA y el
número; NO prueba la propiedad legal de esos recursos por parte del comercio.
"""
from __future__ import annotations

import datetime as dt
import hmac
import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.platform_audit import record_platform_action
from apps.business.models import Business

from ..crypto import AgentSecretEncryptionError
from ..models import AgentChannel, AgentInstance, ReceptionistConfig, WhatsAppAuthorization
from . import whatsapp_authorizations as wa
from .meta_graph import WhatsAppResourceVerification, verify_whatsapp_resources
from .receptionist_config import admin_reception_business

logger = logging.getLogger('apps.leads.receiver')

SOURCE_ASSISTED = 'assisted'
SOURCE_EMBEDDED_SIGNUP = 'embedded_signup'
LINK_SOURCES = frozenset({SOURCE_ASSISTED, SOURCE_EMBEDDED_SIGNUP})
REASON_MAX_LENGTH = 255
EVIDENCE_VERSION = 1

OUTCOME_LINKED = 'linked'
OUTCOME_ALREADY_LINKED = 'already_linked'

_fail = wa._fail


@dataclass(frozen=True)
class WhatsAppChannelLink:
    """Resultado sin secretos: ni token ni valores cifrados."""
    channel: AgentChannel
    authorization_id: str
    outcome: str                      # linked | already_linked
    created_channel: bool
    created_authorization: bool
    verification: dict                # la evidencia guardada en el canal
    # Solo informativo: la vinculación nunca la cambia (ver reporte PROD-10B2).
    automatic_attention_enabled: bool


# ── Validaciones locales ─────────────────────────────────────────────────────

def _require_superadmin(actor) -> None:
    wa._require_admin(actor)
    if actor.account_profile.internal_role != 'superadmin':
        raise _fail('actor_not_authorized', 'Solo superadmin puede vincular WhatsApp.')


def _clean_reason(reason) -> str:
    reason = reason.strip() if isinstance(reason, str) else ''
    if not reason or len(reason) > REASON_MAX_LENGTH:
        raise _fail('invalid_reason', f'Debe indicar un motivo (1 a {REASON_MAX_LENGTH} caracteres).')
    return reason


def _eligible_business(business: Business) -> Business:
    """Re-resuelve por id: nunca confía en el estado del objeto recibido."""
    resolved = admin_reception_business(getattr(business, 'pk', None)) if business is not None else None
    if resolved is None:
        raise _fail('client_not_eligible', 'Cliente HQ con Recepcionista IA no cancelada requerido.')
    return resolved


def _shared_instance() -> AgentInstance:
    external_id = getattr(settings, 'WHATSAPP_LINK_AGENT_INSTANCE_ID', '')
    if not external_id:
        raise _fail('agent_instance_not_configured', 'Instancia compartida del agente no configurada.')
    instance = AgentInstance.objects.filter(external_id=external_id).first()
    if instance is None or not instance.is_enabled:
        raise _fail('agent_instance_unavailable', 'Instancia compartida del agente inexistente o deshabilitada.')
    return instance


def _active_channel(phone_number_id: str, *, lock: bool = False) -> AgentChannel | None:
    qs = AgentChannel.objects.filter(
        provider=AgentChannel.Provider.WHATSAPP_CLOUD, phone_number_id=phone_number_id, is_active=True,
    )
    if lock:
        qs = qs.select_for_update(of=('self',))
    return qs.select_related('whatsapp_authorization').first()


def _check_existing(channel: AgentChannel | None, *, business: Business, instance: AgentInstance,
                    waba_id: str, now: dt.datetime) -> None:
    """Conflictos con un canal activo del mismo número. Nunca revela el otro negocio."""
    if channel is None:
        return
    if channel.business_id != business.pk:
        raise _fail('phone_number_unavailable', 'El número ya está vinculado y no puede vincularse acá.')
    if channel.agent_instance_id != instance.pk:
        raise _fail('channel_agent_instance_mismatch', 'El canal existente usa otra instancia del agente.')
    if channel.waba_id and channel.waba_id != waba_id:
        raise _fail('channel_waba_mismatch', 'El canal existente está vinculado a otra WABA.')
    authorization = channel.whatsapp_authorization
    if authorization is None:
        return  # canal sin credencial (alta previa por shell): se completa
    if authorization.is_platform or wa.channel_credential_problem(channel, now) is not None:
        # Plataforma, revocada, inválida o vencida: reemplazarla es rotación
        # o reasignación, reservadas a servicios posteriores.
        raise _fail('channel_credential_conflict', 'El canal ya tiene otra credencial; no se reemplaza acá.')


def _effective_expiry(verification: WhatsAppResourceVerification) -> dt.datetime | None:
    """Vencimiento efectivo en el único campo existente (`expires_at`).

    El token deja de servir cuando vence él o su acceso a datos: se guarda el
    menor de ambos (None solo si Meta no informó ninguno). Así la regla local
    existente (`channel_credential_problem`) bloquea la entrega a tiempo.
    """
    dates = [d for d in (verification.token.expires_at, verification.token.data_access_expires_at) if d]
    return min(dates) if dates else None


# ── Evidencia ────────────────────────────────────────────────────────────────

def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _evidence(verification: WhatsAppResourceVerification, *, phone_number_id: str,
              authorization: WhatsAppAuthorization, source: str) -> dict:
    phone, token = verification.phone_number, verification.token
    return {
        'version': EVIDENCE_VERSION,
        'verified_at': _iso(verification.verified_at),
        'source': source,
        # Ligadura: si cambia cualquiera, la evidencia deja de valer.
        'authorization_id': str(authorization.pk),
        'authorization_updated_at': _iso(authorization.updated_at),
        'waba_id': verification.waba_id,
        'phone_number_id': phone_number_id,
        'app_subscribed': verification.subscription.app_subscribed,
        'override_callback_configured': verification.subscription.override_callback_configured,
        'phone': {
            'display_phone_number': phone.display_phone_number,
            'verified_name': phone.verified_name,
            'code_verification_status': phone.code_verification_status,
            'quality_rating': phone.quality_rating,
            'platform_type': phone.platform_type,
        },
        'token': {
            'type': token.token_type,
            'scope_coverage': dict(sorted(token.scope_coverage.items())),
            'expires_at': _iso(token.expires_at),
            'data_access_expires_at': _iso(token.data_access_expires_at),
        },
        'legal_ownership_verified': False,
    }


def channel_meta_verification(channel: AgentChannel | None, now: dt.datetime | None = None) -> dict | None:
    """Evidencia vigente del canal, o `None` si ya no corresponde.

    Pura (sin consultas extra si `whatsapp_authorization` viene cargada). Se
    descarta si el canal no entregaría hoy su credencial
    (`channel_credential_problem`), o si cambió la autorización, su versión
    (rotación, revocación o invalidación tocan `updated_at`), la WABA o el
    número. Aun vigente es histórica: `verified_at` dice cuándo se observó,
    no que la conexión funcione ahora.
    """
    if channel is None or not channel.meta_verification:
        return None
    if wa.channel_credential_problem(channel, now or timezone.now()) is not None:
        return None
    evidence, authorization = channel.meta_verification, channel.whatsapp_authorization
    try:
        bound_updated_at = dt.datetime.fromisoformat(evidence.get('authorization_updated_at') or '')
    except (TypeError, ValueError):
        return None
    if (
        evidence.get('version') != EVIDENCE_VERSION
        or evidence.get('authorization_id') != str(authorization.pk)
        or bound_updated_at != authorization.updated_at
        or evidence.get('waba_id') != channel.waba_id
        or evidence.get('phone_number_id') != channel.phone_number_id
    ):
        return None
    return evidence


# ── Operación ────────────────────────────────────────────────────────────────

def _same_token(authorization: WhatsAppAuthorization, token: str) -> bool:
    try:
        stored = authorization.get_token()
    except AgentSecretEncryptionError:
        raise _fail('whatsapp_credential_unreadable', 'No se pudo leer la credencial guardada.') from None
    return hmac.compare_digest(stored.encode(), token.encode())


def _locked_existing(phone_number_id: str) -> AgentChannel | None:
    """Canal activo bloqueado respetando el orden autorización → canal."""
    current = _active_channel(phone_number_id)
    if current is None or current.whatsapp_authorization_id is None:
        return _active_channel(phone_number_id, lock=True)
    wa._locked_authorization(current.whatsapp_authorization_id)
    locked = _active_channel(phone_number_id, lock=True)
    if locked is None or locked.pk != current.pk or locked.whatsapp_authorization_id != current.whatsapp_authorization_id:
        raise _fail('channel_changed_concurrently', 'El canal cambió durante la vinculación; reintentar.')
    return locked


def _attention_enabled(business: Business) -> bool:
    return bool(
        ReceptionistConfig.objects.filter(business=business)
        .values_list('automatic_attention_enabled', flat=True).first()
    )


def link_whatsapp_channel(
    *, business: Business, waba_id: str, phone_number_id: str, token: str, actor, reason: str, source: str,
    session=None,
) -> WhatsAppChannelLink:
    """Vincula WABA + número verificados en Meta a `business`. Ver docstring del módulo.

    Errores: `WhatsAppAuthorizationError` (locales y conflictos) o
    `MetaGraphError` (verificación, ya normalizado; `transient` indica si
    conviene reintentar). Nunca escribe ante una verificación inválida.
    `session` es solo para tests (sesión HTTP simulada).
    """
    _require_superadmin(actor)
    if source not in LINK_SOURCES:
        raise _fail('invalid_source', 'Origen inválido: assisted o embedded_signup.')
    reason = _clean_reason(reason)
    wa._validate_token(token)
    business = _eligible_business(business)
    instance = _shared_instance()
    # Falla rápido, antes de llamar a Meta (se revalida bajo lock).
    _check_existing(
        _active_channel(phone_number_id) if isinstance(phone_number_id, str) else None,
        business=business, instance=instance, waba_id=waba_id, now=timezone.now(),
    )

    verification = verify_whatsapp_resources(
        token=token, waba_id=waba_id, phone_number_id=phone_number_id, session=session,
    )
    waba_id = verification.waba_id
    phone_number_id = verification.phone_number.phone_number_id
    expires_at = _effective_expiry(verification)

    try:
        with transaction.atomic():
            Business.objects.select_for_update().filter(pk=business.pk).first()
            business = _eligible_business(business)
            if _shared_instance().pk != instance.pk:
                raise _fail('agent_instance_unavailable', 'La instancia compartida cambió; reintentar.')
            now = timezone.now()
            if expires_at is not None and expires_at <= now:
                raise _fail('whatsapp_authorization_expired', 'La autorización venció durante la vinculación.')
            channel = _locked_existing(phone_number_id)
            _check_existing(channel, business=business, instance=instance, waba_id=waba_id, now=now)

            created_channel = channel is None
            if created_channel:
                channel = AgentChannel(
                    provider=AgentChannel.Provider.WHATSAPP_CLOUD, phone_number_id=phone_number_id,
                    agent_instance=instance, business=business,
                )
                channel.save()

            authorization = channel.whatsapp_authorization
            created_authorization = authorization is None
            if created_authorization:
                authorization = wa.create_whatsapp_authorization(
                    token=token, actor=actor, owner_business=business, expires_at=expires_at,
                )
                channel = wa.associate_channel(
                    channel_id=channel.pk, authorization_id=authorization.pk, waba_id=waba_id, actor=actor,
                )
            elif not _same_token(authorization, token):
                raise _fail(
                    'channel_credential_conflict',
                    'El canal ya tiene otra credencial; reemplazarla es una rotación explícita.',
                )

            evidence = _evidence(
                verification, phone_number_id=phone_number_id, authorization=authorization, source=source,
            )
            channel.meta_verification = evidence
            channel.save(update_fields=['meta_verification'])
            attention = _attention_enabled(business)
            outcome = OUTCOME_LINKED if created_authorization else OUTCOME_ALREADY_LINKED
            record_platform_action(
                action='WHATSAPP_CHANNEL_LINKED', actor=actor, business=business,
                entity_type='agent_channel', entity_id=str(channel.pk),
                details={
                    'outcome': outcome,
                    'source': source,
                    'reason': reason,
                    'agent_instance': instance.external_id,
                    'waba_id': waba_id,
                    'phone_number_id': phone_number_id,
                    'authorization_id': str(authorization.pk),
                    'created_channel': created_channel,
                    'created_authorization': created_authorization,
                    'expires_at': _iso(authorization.expires_at),
                    'verified_at': evidence['verified_at'],
                    'app_subscribed': evidence['app_subscribed'],
                    'scope_coverage': evidence['token']['scope_coverage'],
                    'automatic_attention_enabled': attention,
                    'legal_ownership_verified': False,
                },
            )
    except IntegrityError:
        # Carrera con otro alta del mismo número (constraint de pnid activo
        # único): todo se revirtió; no se revela con quién.
        raise _fail('phone_number_unavailable', 'El número ya está vinculado y no puede vincularse acá.') from None

    logger.info(
        'whatsapp_link ok business_id=%s channel_id=%s outcome=%s source=%s',
        business.pk, channel.pk, outcome, source,
    )
    return WhatsAppChannelLink(
        channel=channel, authorization_id=str(authorization.pk), outcome=outcome,
        created_channel=created_channel, created_authorization=created_authorization,
        verification=evidence, automatic_attention_enabled=attention,
    )
