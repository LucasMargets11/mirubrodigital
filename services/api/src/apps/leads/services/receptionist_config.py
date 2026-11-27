"""Configuración de la Recepcionista IA (PROD-03A/03B).

Un solo camino de lectura y escritura para todos los accesos:

- El agente la ve solo a través de su canal activo
  (`receptionist_config_for_agent` / `agent_receptionist_config`, misma regla
  que el receiver; PROD-03C la expone por HMAC).
- Platform Admin y el comercio (owner/admin) la crean y editan con
  `create_receptionist_config` / `update_receptionist_config`: mismas
  validaciones (las del modelo), mismo bloqueo, misma auditoría. Las vistas
  solo deciden QUÉ Business (el cliente elegido o `request.business`).

La configuración no concede capacidades (agenda, permisos, consumo IA) ni
guarda credenciales: esos campos no existen y cualquier clave fuera de
`WRITABLE_FIELDS` se rechaza.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.accounts.platform_audit import record_platform_action
from apps.business.models import Business, BusinessBillingProfile, BusinessBranding

from ..models import AgentChannel, AgentInstance, ReceptionistConfig
from .receiver import resolve_channel

WRITABLE_FIELDS = frozenset((*ReceptionistConfig.CONTENT_FIELDS, 'status'))
# PROD-09C1: solo Platform Admin, solo en edición (crear nunca habilita).
ATTENTION_FIELD = 'automatic_attention_enabled'
ADMIN_ONLY_FIELDS = frozenset((ATTENTION_FIELD,))
# Del modelo pero nunca escribibles: identidad, relación y metadatos.
PROTECTED_FIELDS = frozenset(('id', 'business', 'business_id', 'version', 'created_at', 'updated_at'))
EXPECTED_VERSION = 'expected_version'
_LIST_FIELDS = frozenset(('services', 'faqs'))

SOURCE_PLATFORM_ADMIN = 'platform_admin'
SOURCE_BUSINESS = 'business'


class ReceptionistConfigError(Exception):
    def __init__(self, status: int, code: str, detail: str, **extra):
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra

    def as_body(self) -> dict:
        return {'code': self.code, 'detail': self.detail, **self.extra}


def _resolve_for_agent(
    agent_instance: AgentInstance, *, phone_number_id: str, business_id: int,
) -> tuple[AgentChannel, ReceptionistConfig | None]:
    channel = resolve_channel(agent_instance, {'phone_number_id': phone_number_id, 'business_id': business_id})
    return channel, ReceptionistConfig.objects.filter(business_id=channel.business_id).first()


def receptionist_config_for_agent(
    agent_instance: AgentInstance, *, phone_number_id: str, business_id: int,
) -> ReceptionistConfig | None:
    """Configuración del negocio atendido por este canal, o `None` si no hay.

    Errores de relación (canal ajeno/inactivo, negocio inactivo o distinto)
    son los del receiver: `channel_disabled`, `business_inactive`,
    `business_mismatch`.
    """
    return _resolve_for_agent(agent_instance, phone_number_id=phone_number_id, business_id=business_id)[1]


# PROD-03C: contrato de lectura del agente. Sube solo ante cambios
# incompatibles de forma; los aditivos no lo mueven.
AGENT_CONFIG_CONTRACT_VERSION = 1
CONFIG_MISSING = 'missing'


def _public_business(business: Business) -> dict:
    """Datos comerciales públicos, leídos en vivo de Business y sus perfiles.

    Nada fiscal ni de contacto interno: ni razón social, CUIT, IVA, IIBB,
    domicilio fiscal, ni el email/teléfono de facturación. El WhatsApp sale de
    `BusinessBranding.whatsapp_phone`, que ya es el contacto público opt-in.
    """
    billing = (
        BusinessBillingProfile.objects.filter(business=business)
        .values('commercial_address', 'website').first() or {}
    )
    whatsapp = (
        BusinessBranding.objects.filter(business=business).values_list('whatsapp_phone', flat=True).first() or ''
    )
    return {
        'id': business.pk,
        'name': business.name,
        'timezone': business.timezone,
        'address': billing.get('commercial_address') or None,
        'website': billing.get('website') or None,
        'whatsapp_phone': whatsapp or None,
    }


def _config_block(config: ReceptionistConfig | None) -> dict:
    """Estado, versión y contenido de UNA lectura de la fila (consistente).

    `content` solo cuando está lista: un borrador no entrega texto usable.
    `version` es la de ReceptionistConfig; cambios de Business o sus perfiles
    no la mueven.
    """
    if config is None:
        return {
            'status': CONFIG_MISSING, 'version': None, 'updated_at': None, 'missing_for_ready': None,
            'content': None, ATTENTION_FIELD: False,
        }
    ready = config.is_ready
    return {
        'status': ReceptionistConfig.Status.READY if ready else ReceptionistConfig.Status.DRAFT,
        'version': config.version,
        'updated_at': config.updated_at.isoformat(),
        'missing_for_ready': config.missing_for_ready(),
        'content': {field: getattr(config, field) for field in ReceptionistConfig.CONTENT_FIELDS} if ready else None,
        # PROD-09C1 (aditivo): habilitación operativa, independiente de `status`.
        ATTENTION_FIELD: bool(config.automatic_attention_enabled),
    }


def agent_receptionist_config(
    agent_instance: AgentInstance, *, phone_number_id: str, business_id: int,
) -> dict:
    """Payload del GET del agente. Solo lectura: no crea ni modifica nada.

    `ready` es completitud de la configuración, nunca autorización: el uso de
    IA se sigue autorizando por interacción (`ai-usage/authorize`).
    """
    channel, config = _resolve_for_agent(agent_instance, phone_number_id=phone_number_id, business_id=business_id)
    return {
        'ok': True,
        'contract_version': AGENT_CONFIG_CONTRACT_VERSION,
        'business': _public_business(channel.business),
        'channel': {'provider': channel.provider, 'phone_number_id': channel.phone_number_id},
        'config': _config_block(config),
    }


def serialize_receptionist_config(config: ReceptionistConfig | None) -> dict:
    """`{"config": null}` si no existe (un GET nunca la crea)."""
    if config is None:
        return {'config': None}
    return {
        'config': {
            'id': str(config.id),
            **{field: getattr(config, field) for field in ReceptionistConfig.CONTENT_FIELDS},
            'status': config.status,
            ATTENTION_FIELD: config.automatic_attention_enabled,
            'version': config.version,
            'missing_for_ready': config.missing_for_ready(),
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
        },
    }


def _parse(data, *, require_version: bool, admin_fields: bool = False) -> tuple[dict, int | None]:
    if not isinstance(data, dict):
        raise ReceptionistConfigError(400, 'invalid_request', 'Se esperaba un objeto JSON.')
    keys = set(data)
    protected = sorted(keys & (PROTECTED_FIELDS | (frozenset() if admin_fields else ADMIN_ONLY_FIELDS)))
    if protected:
        raise ReceptionistConfigError(400, 'protected_fields', 'Campos no editables.', fields=protected)
    allowed = WRITABLE_FIELDS | ({EXPECTED_VERSION} if require_version else set()) | (
        ADMIN_ONLY_FIELDS if admin_fields else frozenset()
    )
    unknown = sorted(keys - allowed)
    if unknown:
        raise ReceptionistConfigError(
            400, 'unknown_fields', 'Campos no permitidos.', fields=unknown, allowed_fields=sorted(allowed),
        )
    expected = None
    if require_version:
        expected = data.get(EXPECTED_VERSION)
        if type(expected) is not int or expected < 1:
            raise ReceptionistConfigError(
                400, 'expected_version_required', 'Enviá expected_version (entero) con la versión leída.',
            )
    changes = {key: value for key, value in data.items() if key in allowed and key != EXPECTED_VERSION}

    # Tipos JSON estrictos: el modelo convertiría 123 en "123" (o 1 en True).
    def wrong_type(key, value) -> bool:
        if key in ADMIN_ONLY_FIELDS:
            return type(value) is not bool
        return not isinstance(value, list if key in _LIST_FIELDS else str)

    wrong = sorted(key for key, value in changes.items() if wrong_type(key, value))
    if wrong:
        raise ReceptionistConfigError(400, 'validation_error', 'Tipo de dato inválido.', fields={
            key: [
                'Debe ser true o false.' if key in ADMIN_ONLY_FIELDS
                else 'Debe ser una lista.' if key in _LIST_FIELDS else 'Debe ser texto.'
            ] for key in wrong
        })
    return changes, expected


def _save(config: ReceptionistConfig) -> None:
    try:
        config.save()
    except DjangoValidationError as error:
        fields = getattr(error, 'message_dict', None) or {'non_field_errors': error.messages}
        raise ReceptionistConfigError(400, 'validation_error', 'Configuración inválida.', fields=fields) from None


def _audit(action: str, *, config: ReceptionistConfig, actor, source: str, **details) -> None:
    # Solo metadatos: nunca el contenido (instrucciones, FAQs, textos).
    record_platform_action(
        action=action, actor=actor, business=config.business,
        entity_type='receptionist_config', entity_id=str(config.id),
        details={
            'source': source, 'version': config.version, 'status': config.status,
            ATTENTION_FIELD: config.automatic_attention_enabled, **details,
        },
    )


def create_receptionist_config(business: Business, data, *, actor, source: str) -> ReceptionistConfig:
    """Crea el borrador (o la config completa enviada). 409 si ya existe."""
    changes, _ = _parse(data, require_version=False)
    with transaction.atomic():
        # Serializa creaciones concurrentes del mismo Business (mismo orden de
        # lock que grant_complimentary_access: Business primero).
        Business.objects.select_for_update().only('pk').get(pk=business.pk)
        if ReceptionistConfig.objects.filter(business_id=business.pk).exists():
            raise ReceptionistConfigError(409, 'receptionist_config_exists', 'El negocio ya tiene configuración.')
        config = ReceptionistConfig(business=business, **changes)
        try:
            with transaction.atomic():
                _save(config)
        except IntegrityError:
            raise ReceptionistConfigError(
                409, 'receptionist_config_exists', 'El negocio ya tiene configuración.',
            ) from None
        _audit(
            'RECEPTIONIST_CONFIG_CREATED', config=config, actor=actor, source=source,
            changed_fields=sorted(changes),
        )
    return config


def update_receptionist_config(business: Business, data, *, actor, source: str) -> ReceptionistConfig:
    """Edición parcial con `expected_version`; 409 si la versión es obsoleta.

    PROD-09C1: `automatic_attention_enabled` solo desde Platform Admin. Volver
    a borrador con la atención habilitada la pausa en la misma escritura;
    volver a «lista» nunca la reactiva.
    """
    changes, expected = _parse(data, require_version=True, admin_fields=source == SOURCE_PLATFORM_ADMIN)
    with transaction.atomic():
        config = ReceptionistConfig.objects.select_for_update().filter(business_id=business.pk).first()
        if config is None:
            raise ReceptionistConfigError(404, 'receptionist_config_not_found', 'El negocio no tiene configuración.')
        if config.version != expected:
            raise ReceptionistConfigError(
                409, 'version_conflict', 'La configuración cambió; volvé a leerla.', current_version=config.version,
            )
        changed = sorted(field for field, value in changes.items() if getattr(config, field) != value)
        if not changed:
            return config
        previous_version = config.version
        for field in changed:
            setattr(config, field, changes[field])
        attention = None
        if ATTENTION_FIELD in changed:
            attention = 'enabled' if config.automatic_attention_enabled else 'paused'
        elif (
            ATTENTION_FIELD not in changes and config.automatic_attention_enabled
            and config.status != ReceptionistConfig.Status.READY
        ):
            # Borrador con la atención encendida: se pausa en la misma escritura.
            # Si el PATCH pide `true` explícito junto con borrador, lo rechaza clean().
            config.automatic_attention_enabled = False
            changed = sorted((*changed, ATTENTION_FIELD))
            attention = 'paused_by_draft'
        _save(config)
        extra = {'automatic_attention': attention} if attention else {}
        _audit(
            'RECEPTIONIST_CONFIG_UPDATED', config=config, actor=actor, source=source,
            changed_fields=changed, previous_version=previous_version, **extra,
        )
    return config
