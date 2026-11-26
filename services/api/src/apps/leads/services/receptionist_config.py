"""Configuración de la Recepcionista IA (PROD-03A/03B).

Un solo camino de lectura y escritura para todos los accesos:

- El agente la ve solo a través de su canal activo
  (`receptionist_config_for_agent`, misma regla que el receiver).
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
from apps.business.models import Business

from ..models import AgentInstance, ReceptionistConfig
from .receiver import resolve_channel

WRITABLE_FIELDS = frozenset((*ReceptionistConfig.CONTENT_FIELDS, 'status'))
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


def receptionist_config_for_agent(
    agent_instance: AgentInstance, *, phone_number_id: str, business_id: int,
) -> ReceptionistConfig | None:
    """Configuración del negocio atendido por este canal, o `None` si no hay.

    Errores de relación (canal ajeno/inactivo, negocio inactivo o distinto)
    son los del receiver: `channel_disabled`, `business_inactive`,
    `business_mismatch`.
    """
    channel = resolve_channel(agent_instance, {'phone_number_id': phone_number_id, 'business_id': business_id})
    return ReceptionistConfig.objects.filter(business_id=channel.business_id).first()


def serialize_receptionist_config(config: ReceptionistConfig | None) -> dict:
    """`{"config": null}` si no existe (un GET nunca la crea)."""
    if config is None:
        return {'config': None}
    return {
        'config': {
            'id': str(config.id),
            **{field: getattr(config, field) for field in ReceptionistConfig.CONTENT_FIELDS},
            'status': config.status,
            'version': config.version,
            'missing_for_ready': config.missing_for_ready(),
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
        },
    }


def _parse(data, *, require_version: bool) -> tuple[dict, int | None]:
    if not isinstance(data, dict):
        raise ReceptionistConfigError(400, 'invalid_request', 'Se esperaba un objeto JSON.')
    keys = set(data)
    protected = sorted(keys & PROTECTED_FIELDS)
    if protected:
        raise ReceptionistConfigError(400, 'protected_fields', 'Campos no editables.', fields=protected)
    allowed = WRITABLE_FIELDS | ({EXPECTED_VERSION} if require_version else set())
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
    changes = {key: value for key, value in data.items() if key in WRITABLE_FIELDS}
    # Tipos JSON estrictos: el modelo convertiría 123 en "123".
    wrong = sorted(
        key for key, value in changes.items()
        if not isinstance(value, list if key in _LIST_FIELDS else str)
    )
    if wrong:
        raise ReceptionistConfigError(400, 'validation_error', 'Tipo de dato inválido.', fields={
            key: ['Debe ser una lista.' if key in _LIST_FIELDS else 'Debe ser texto.'] for key in wrong
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
        details={'source': source, 'version': config.version, 'status': config.status, **details},
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
    """Edición parcial con `expected_version`; 409 si la versión es obsoleta."""
    changes, expected = _parse(data, require_version=True)
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
        _save(config)
        _audit(
            'RECEPTIONIST_CONFIG_UPDATED', config=config, actor=actor, source=source,
            changed_fields=changed, previous_version=previous_version,
        )
    return config
