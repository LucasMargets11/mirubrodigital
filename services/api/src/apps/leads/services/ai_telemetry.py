"""PROD-02E4A — ingesta de telemetría operativa de IA del agente.

`record_ai_execution(principal, data)` registra UN intento real contra el
proveedor de IA. Reglas:

* Tenant: el `AgentChannel` de la instancia autenticada con ese
  `phone_number_id` que estaba activo en `executed_at`
  (created_at <= executed_at < deactivated_at). Nunca un business_id del
  agente. Un canal desactivado o reasignado después sigue atribuyendo los
  resultados tardíos de su período; un canal de otra instancia, o uno que no
  existía/no estaba activo en ese instante, es `channel_not_authorized`.
* Independiente del consumo comercial: no lee ni escribe suscripciones,
  sesiones, cargos, cupos, intents ni settlements, y no concede acceso. Una
  suspensión comercial posterior no impide registrar costos ya incurridos.
  Solo enlaza (si existe) la `AppointmentAIUsageAuthorization` del mismo
  Business e interacción cuya conversación pertenece a ese canal.
* Idempotencia por (agent_instance, event_id): repetición idéntica → duplicate
  sin escribir; mismo id con otro contenido → conflicto. Las filas son
  inmutables (un replay nunca modifica el historial).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import timezone as dt_timezone

from django.db import IntegrityError, transaction
from django.db.models import Q

from .. import errors
from ..models import AgentAIExecution, AgentChannel, LeadAgentState

logger = logging.getLogger('apps.leads.ai_telemetry')

RECORDED = 'recorded'
DUPLICATE = 'duplicate'

# Campos que definen la identidad de contenido del evento (orden estable).
HASHED_FIELDS = (
    'event_id', 'phone_number_id', 'interaction_id', 'provider', 'model', 'operation', 'status',
    'error_code', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'provider_request_id',
    'latency_ms', 'executed_at',
)


def channel_not_authorized() -> errors.AgentApiError:
    return errors.AgentApiError(403, 'channel_not_authorized', 'Canal no autorizado para esa ejecución.')


def idempotency_conflict() -> errors.AgentApiError:
    return errors.AgentApiError(409, 'idempotency_conflict', 'El evento ya fue registrado con otro contenido.')


def payload_hash(data: dict) -> str:
    def norm(key):
        value = data.get(key)
        if key == 'executed_at':
            return value.astimezone(dt_timezone.utc).isoformat()
        if key in ('event_id', 'interaction_id'):
            return str(value).lower() if value is not None else None
        return value

    canonical = json.dumps([[key, norm(key)] for key in HASHED_FIELDS], separators=(',', ':'), sort_keys=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _resolve_channel(instance, phone_number_id: str, executed_at):
    channels = list(
        AgentChannel.objects.select_related('business')
        .filter(agent_instance=instance, phone_number_id=phone_number_id, created_at__lte=executed_at)
        .filter(Q(deactivated_at__isnull=True) | Q(deactivated_at__gt=executed_at))[:2]
    )
    return channels[0] if len(channels) == 1 else None


def _authorization_for(channel, interaction_id):
    from apps.appointments.models import AppointmentAIUsageAuthorization

    if interaction_id is None:
        return None
    receipt = (
        AppointmentAIUsageAuthorization.objects.select_related('session')
        .filter(business_id=channel.business_id, interaction_id=interaction_id).first()
    )
    if receipt is None:
        return None
    # Solo si la conversación de esa autorización es de este mismo canal.
    if not LeadAgentState.objects.filter(
        channel=channel, external_conversation_id=receipt.session.external_conversation_id,
    ).exists():
        return None
    return receipt


def _existing(instance, event_id):
    return AgentAIExecution.objects.filter(agent_instance=instance, event_id=event_id).first()


def _compare(existing, digest):
    if existing.payload_hash != digest:
        raise idempotency_conflict()
    return existing, DUPLICATE


def record_ai_execution(principal, data: dict):
    """(execution, result) con result en {recorded, duplicate}; AgentApiError si no."""
    instance = principal.agent_instance
    digest = payload_hash(data)
    existing = _existing(instance, data['event_id'])
    if existing is not None:
        return _compare(existing, digest)
    channel = _resolve_channel(instance, data['phone_number_id'], data['executed_at'])
    if channel is None:
        raise channel_not_authorized()
    authorization = _authorization_for(channel, data.get('interaction_id'))
    try:
        with transaction.atomic():
            execution = AgentAIExecution.objects.create(
                event_id=data['event_id'], business_id=channel.business_id, agent_instance=instance,
                channel=channel, interaction_id=data.get('interaction_id'), authorization=authorization,
                provider=data['provider'], model=data['model'], operation=data['operation'],
                status=data['status'], error_code=data.get('error_code'),
                input_tokens=data.get('input_tokens'), output_tokens=data.get('output_tokens'),
                cached_input_tokens=data.get('cached_input_tokens'),
                provider_request_id=data.get('provider_request_id'), latency_ms=data.get('latency_ms'),
                executed_at=data['executed_at'], payload_hash=digest, request_id=principal.request_id,
            )
    except IntegrityError:
        # Carrera con el mismo event_id: el primero gana; el resto compara contenido.
        existing = _existing(instance, data['event_id'])
        if existing is None:
            raise
        return _compare(existing, digest)
    return execution, RECORDED
