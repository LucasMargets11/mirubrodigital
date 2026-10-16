"""Receiver service de `lead.sync` (AGENT 02B, Contract V1).

Recibe un payload ya autenticado (HMAC) y validado (serializer) y aplica:

1. Tenant: `AgentChannel` activo por `(whatsapp_cloud, phone_number_id)` →
   misma `AgentInstance` → Business habilitado → `business_id` coincidente.
2. Idempotencia por `(agent_instance, external_lead_id)` con
   `select_for_update`: created / applied / duplicate / stale /
   version_conflict. Carrera de creación resuelta por la constraint única.
3. Solo escribe campos agent-owned de `LeadAgentState`. Del `Lead` CRM solo
   crea la fila con defaults y, ante un pedido de atención, escribe
   `needs_attention_at` (vacío → ahora; ya reconocido por un humano y Lead
   abierto → ahora, vuelve a quedar pendiente). Nunca `acknowledged_*`.
4. Notificación `agent_lead_handoff` post-commit, sin PII, una por ciclo de
   atención (LEADS 04B.3: el ciclo es `needs_attention_at`, que solo avanza
   con un pedido nuevo posterior a un reconocimiento) y solo mientras está
   pendiente; duplicate/stale la re-aseguran (repara un fallo post-commit).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.business_notifications import create_business_notification, on_commit_safely
from apps.notifications.models import BusinessNotification

from .. import errors
from ..contract import ALLOWED_BUSINESS_STATUSES, compute_payload_hash, format_utc, sort_handoff_reasons
from ..models import AgentChannel, AgentInstance, Lead, LeadAgentMessage, LeadAgentState

logger = logging.getLogger('apps.leads.receiver')

RESULT_CREATED = 'created'
RESULT_APPLIED = 'applied'
RESULT_DUPLICATE = 'duplicate'
RESULT_STALE = 'stale'

HANDOFF_NOTIFICATION_TITLE = 'Nueva consulta para recepción'
HANDOFF_NOTIFICATION_MESSAGE = 'Una consulta requiere atención humana.'

# Campos que el sync escribe en una versión nueva (todo lo demás es identidad
# inmutable o CRM).
AGENT_OWNED_FIELDS = (
    'patient_name', 'whatsapp_profile_name', 'reason', 'preferred_time', 'urgency',
    'agent_status', 'handoff_requested', 'handoff_requested_at', 'handoff_reasons',
    'summary', 'closed_at', 'close_reason', 'last_message_at',
)
SYNC_METADATA_FIELDS = ('applied_version', 'payload_hash', 'last_event_id', 'last_synced_at')


@dataclass(frozen=True)
class ReceiverResult:
    result: str
    lead: Lead
    received_version: int
    applied_version: int
    business_id: int

    @property
    def status_code(self) -> int:
        return 201 if self.result == RESULT_CREATED else 200


def resolve_channel(agent_instance: AgentInstance, data: dict) -> AgentChannel:
    """Tenant derivado del canal activo, nunca de headers/cookies/membership."""
    channel = (
        AgentChannel.objects.select_related('business')
        .filter(
            provider=AgentChannel.Provider.WHATSAPP_CLOUD,
            phone_number_id=data['phone_number_id'],
            is_active=True,
        )
        .first()
    )
    if channel is None or channel.agent_instance_id != agent_instance.id:
        raise errors.channel_disabled()
    if channel.business.status not in ALLOWED_BUSINESS_STATUSES:
        raise errors.business_inactive()
    if data['business_id'] != channel.business_id:
        raise errors.business_mismatch()
    return channel


def _agent_fields(data: dict) -> dict:
    handoff = data['handoff']
    return {
        'patient_name': data['patient_name'],
        'whatsapp_profile_name': data['whatsapp_profile_name'],
        'reason': data['reason'],
        'preferred_time': data['preferred_time'],
        'urgency': data['urgency'],
        'agent_status': data['agent_status'],
        'handoff_requested': handoff['requested'],
        'handoff_requested_at': handoff['requested_at'],
        'handoff_reasons': [
            {'code': reason['code'], 'first_at': format_utc(reason['first_at']), 'last_at': format_utc(reason['last_at'])}
            for reason in sort_handoff_reasons(handoff['reasons'])
        ],
        'summary': data['summary'],
        'closed_at': data['closed_at'],
        'close_reason': data['close_reason'],
        'last_message_at': data['last_message_at'],
    }


def _identity_matches(state: LeadAgentState, channel: AgentChannel, data: dict) -> bool:
    """Campos inmutables por Lead (business se chequea aparte → 409 business_mismatch)."""
    return (
        state.channel.provider == channel.provider
        and state.channel.phone_number_id == data['phone_number_id']
        and state.external_conversation_id == data['external_conversation_id']
        and state.external_lead_id == data['external_lead_id']
        and state.previous_external_lead_id == data['previous_external_lead_id']
        and state.phone_e164 == data['phone_e164']
        and state.opened_at == data['opened_at']
    )


def _locked_state(agent_instance: AgentInstance, external_lead_id) -> LeadAgentState | None:
    return (
        LeadAgentState.objects.select_for_update(of=('self',))
        .select_related('lead', 'channel')
        .filter(agent_instance=agent_instance, external_lead_id=external_lead_id)
        .first()
    )


def handoff_dedupe_key(lead: Lead) -> str:
    """Una notificación por ciclo de atención: `needs_attention_at` lo identifica
    (se conserva mientras el pedido sigue pendiente y avanza solo con un pedido
    nuevo tras un reconocimiento)."""
    return f'agent_lead_handoff:{lead.pk}:{format_utc(lead.needs_attention_at)}'


def ensure_agent_lead_handoff_notification(lead_id) -> BusinessNotification | None:
    """Garantiza (idempotente) la notificación del ciclo de atención actual.

    Solo si el estado ya aplicado lo amerita: `handoff_requested=True` y pedido
    pendiente (`Lead.attention_pending`: informado, sin reconocer y Lead no
    cerrado). get-or-create por `handoff_dedupe_key` → una sola por ciclo, sin
    importar cuántas veces se llame (transición, motivo nuevo mientras sigue
    pendiente, retry duplicate/stale). Sin PII.
    """
    state = (
        LeadAgentState.objects.select_related('lead', 'agent_instance')
        .filter(lead_id=lead_id).first()
    )
    if state is None or not state.handoff_requested or not state.lead.attention_pending:
        return None
    severity = BusinessNotification.Severity.CRITICAL if state.urgency else BusinessNotification.Severity.INFO
    notification, _ = create_business_notification(
        business_id=state.lead.business_id,
        kind=BusinessNotification.Kind.AGENT_LEAD_HANDOFF,
        dedupe_key=handoff_dedupe_key(state.lead),
        title=HANDOFF_NOTIFICATION_TITLE,
        message=HANDOFF_NOTIFICATION_MESSAGE,
        severity=severity,
        # El panel de leads todavía no existe: sin action_url.
        action_url='',
        related_object_type='lead',
        related_object_id=str(lead_id),
        metadata={
            'source': 'agent_sync',
            'agent_instance': state.agent_instance.external_id,
            'attention_at': format_utc(state.lead.needs_attention_at),
        },
    )
    return notification


def _schedule_handoff_notification(lead: Lead) -> None:
    """Post-commit: un fallo se loguea (on_commit_safely) y nunca afecta al sync;
    el próximo duplicate/stale del mismo Lead la repara."""
    lead_id = lead.pk
    on_commit_safely(
        lambda: ensure_agent_lead_handoff_notification(lead_id),
        description=f'agent_lead_handoff lead={lead_id}',
    )


def _recover_handoff_notification(state: LeadAgentState) -> None:
    """duplicate/stale no cambian nada, pero reparan un aviso perdido (fallo
    post-commit) del ciclo actual; `ensure` ignora uno reconocido o cerrado."""
    if state.handoff_requested and state.lead.needs_attention_at is not None:
        _schedule_handoff_notification(state.lead)


def _sync_messages(lead: Lead, messages: list[dict]) -> None:
    """Upsert por `(lead, external_message_id)` (LEADS 05C): un reintento o
    reenvío de la misma revisión nunca duplica, solo refresca campos mutables
    (p. ej. `status` de un mensaje saliente que progresa sent -> delivered).
    """
    if not messages:
        return
    rows = [
        LeadAgentMessage(
            lead=lead,
            external_message_id=m['external_message_id'],
            role=m['role'],
            sender=m['sender'],
            text=m['text'],
            sent_at=m['sent_at'],
            status=m['status'],
        )
        for m in messages
    ]
    LeadAgentMessage.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=['lead', 'external_message_id'],
        update_fields=['role', 'sender', 'text', 'sent_at', 'status'],
    )


def _reason_signals(reasons: list[dict]) -> dict[str, str]:
    # `last_at` se guarda con `format_utc` (ancho fijo, UTC) → comparable como texto.
    return {reason['code']: reason['last_at'] for reason in reasons}


def _is_new_attention_request(was_requested: bool, old_reasons: list[dict], state: LeadAgentState) -> bool:
    """¿Esta versión trae un pedido de atención nuevo?

    `handoff.requested` es sticky en el contrato (nunca vuelve a false), así
    que además de la transición false → true cuenta como pedido nuevo un motivo
    nuevo o un `last_at` que avanza (el agente repitió el motivo).
    """
    if not state.handoff_requested:
        return False
    if not was_requested:
        return True
    old = _reason_signals(old_reasons)
    return any(
        code not in old or last_at > old[code]
        for code, last_at in _reason_signals(state.handoff_reasons).items()
    )


def _request_attention(lead: Lead) -> None:
    """Registra un pedido de atención en el Lead CRM (solo `needs_attention_at`).

    - Sin pedido previo → se setea.
    - Pendiente (sin reconocer) → se conserva: sigue pendiente desde el primero.
    - Reconocido y Lead abierto → avanza a ahora y vuelve a quedar pendiente;
      `acknowledged_*` quedan como historia del reconocimiento anterior.
    - Cerrado (y ya informado) → no cambia: un pedido no reabre el Lead.

    Lock de la fila del Lead (orden: LeadAgentState → Lead; la acción humana
    solo bloquea el Lead) y timestamp tomado DESPUÉS del lock, así queda
    estrictamente posterior a un reconocimiento concurrente ya commiteado.
    """
    current = Lead.objects.select_for_update(of=('self',)).only(
        'id', 'status', 'needs_attention_at', 'acknowledged_at',
    ).get(pk=lead.pk)
    if current.needs_attention_at is not None and (
        current.status == Lead.Status.CLOSED or not current.attention_acknowledged
    ):
        return
    stamp = timezone.now()
    # update() acotado: no pisa campos CRM editados por humanos.
    Lead.objects.filter(pk=lead.pk).update(needs_attention_at=stamp, updated_at=stamp)


def _create(agent_instance: AgentInstance, channel: AgentChannel, data: dict, payload_hash: str, now) -> LeadAgentState | None:
    """Crea Lead + LeadAgentState en un savepoint. None si perdió la carrera."""
    fields = _agent_fields(data)
    try:
        with transaction.atomic():
            lead = Lead.objects.create(
                business=channel.business,
                source=Lead.Source.WHATSAPP_AGENT,
                status=Lead.Status.NEW,
                needs_attention_at=now if fields['handoff_requested'] else None,
            )
            state = LeadAgentState.objects.create(
                lead=lead,
                agent_instance=agent_instance,
                channel=channel,
                external_lead_id=data['external_lead_id'],
                external_conversation_id=data['external_conversation_id'],
                previous_external_lead_id=data['previous_external_lead_id'],
                phone_e164=data['phone_e164'],
                opened_at=data['opened_at'],
                applied_version=data['version'],
                payload_hash=payload_hash,
                last_event_id=data['event_id'],
                last_synced_at=now,
                **fields,
            )
            _sync_messages(lead, data['messages'])
            return state
    except IntegrityError:
        # Otra request creó el mismo (agent_instance, external_lead_id).
        return None


def receive_lead_sync(*, agent_instance: AgentInstance, data: dict) -> ReceiverResult:
    """`data` = `validated_data` de `LeadSyncSerializer` (identidad path/body ya verificada)."""
    if data['agent_instance_id'] != agent_instance.external_id:
        raise errors.AgentAuthenticationFailed('agent_instance_mismatch')

    channel = resolve_channel(agent_instance, data)
    payload_hash = compute_payload_hash(data)
    version = data['version']
    now = timezone.now()

    with transaction.atomic():
        state = _locked_state(agent_instance, data['external_lead_id'])
        if state is None:
            created = _create(agent_instance, channel, data, payload_hash, now)
            if created is not None:
                if created.handoff_requested:
                    _schedule_handoff_notification(created.lead)
                return ReceiverResult(RESULT_CREATED, created.lead, version, created.applied_version, channel.business_id)
            state = _locked_state(agent_instance, data['external_lead_id'])
            if state is None:  # pragma: no cover - IntegrityError ajeno a la identidad
                raise errors.internal_error()

        lead = state.lead
        if lead.business_id != channel.business_id:
            raise errors.business_mismatch()
        if not _identity_matches(state, channel, data):
            raise errors.version_conflict()

        if version < state.applied_version:
            _recover_handoff_notification(state)
            return ReceiverResult(RESULT_STALE, lead, version, state.applied_version, channel.business_id)
        if version == state.applied_version:
            if payload_hash == state.payload_hash:
                _recover_handoff_notification(state)
                return ReceiverResult(RESULT_DUPLICATE, lead, version, state.applied_version, channel.business_id)
            raise errors.version_conflict()

        was_requested = state.handoff_requested
        old_reasons = list(state.handoff_reasons or [])
        for field, value in _agent_fields(data).items():
            setattr(state, field, value)
        state.applied_version = version
        state.payload_hash = payload_hash
        state.last_event_id = data['event_id']
        state.last_synced_at = now
        state.save(update_fields=[*AGENT_OWNED_FIELDS, *SYNC_METADATA_FIELDS])
        _sync_messages(lead, data['messages'])

        if _is_new_attention_request(was_requested, old_reasons, state):
            _request_attention(lead)
            # Ciclo nuevo → aviso nuevo; pedido aún pendiente → misma clave (sin
            # spam); Lead cerrado o ya reconocido → `ensure` no crea nada.
            _schedule_handoff_notification(lead)

        return ReceiverResult(RESULT_APPLIED, lead, version, state.applied_version, channel.business_id)
