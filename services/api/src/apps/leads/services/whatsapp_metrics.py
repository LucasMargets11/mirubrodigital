"""PROD-02E4C — métricas operativas de WhatsApp por Business (solo lectura).

Fuente única: lo que el agente ya sincroniza con `lead.sync` (no hay otra copia
de mensajes en MiRubro ni callbacks de Meta: los webhooks de estado llegan al
agente). Sin tablas nuevas, sin migraciones, sin escrituras ni locks.

Fuentes y cobertura (ver docs/MIRUBRO_WHATSAPP_METRICS.md):

* `LeadAgentMessage` — mensajes del EPISODIO de cada Lead (openedAt..closedAt,
  máx. 500 por lead). Conversaciones que nunca generaron Lead, mensajes fuera
  de un episodio o con el sync apagado NO están: los totales son "mensajes
  registrados", nunca "mensajes de WhatsApp" ni "mensajes facturados".
  - `sender`: patient (entrante) | bot | staff (recepción vía takeover).
    `bot` no distingue IA de respuestas automáticas: ambas categorías se
    informan como desconocidas (null), nunca se infieren.
  - `sent_at`: hora original (entrante: timestamp de WhatsApp; saliente:
    aceptación de Meta o, si no se conoce, hora de guardado en el agente).
  - `status` (solo salientes): el ÚLTIMO estado sincronizado del mensaje (no el
    estado histórico al cierre del rango). Mensajes de un episodio ya cerrado
    quedan con el estado de su último sync. null = no informado (desconocido).
  - Identidad: `external_message_id` es el id interno del mensaje en el agente,
    único por AgentInstance. Se deduplica por (agent_instance,
    external_message_id): un mismo mensaje en dos episodios cuenta una vez, con
    su estado más avanzado (read > delivered > sent > failed > null). Los
    reintentos del sync son upserts y nunca duplican filas.
* `LeadAgentState` — conversación (`external_conversation_id`), canal original
  (`channel`, fijo desde el primer sync del lead) y handoff del episodio
  (`handoff_requested_at`, `handoff_paused_at`).
* `LeadActivity` — tomas/reanudaciones humanas aplicadas (takeover/release).
* `LeadStaffMessage` — mensajes que recepción pidió enviar desde MiRubro; su
  estado es el del outbox hacia el agente (encolado/fallido), nunca la
  entrega por WhatsApp (esa llega por `LeadAgentMessage`, sender=staff).

Aislamiento: todo se filtra por `lead.business` Y `channel.business` (el canal
del episodio); un número reasignado a otro Business no mueve el histórico.
Nada de esto es consumo comercial de IA (sesiones/cargos) ni costo de Meta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import timezone

from ..models import AgentChannel, LeadActivity, LeadAgentMessage, LeadAgentState, LeadStaffMessage

CONTRACT_VERSION = 1
MAX_RANGE_DAYS = 92
SOURCE = 'agent_lead_sync'
SYNCED_MESSAGES_PER_LEAD_CAP = 500  # agent MAX_SYNCED_MESSAGES (lead-sync.util.ts)

_STATUS_RANK = {None: 0, 'failed': 1, 'sent': 2, 'delivered': 3, 'read': 4}
OUTBOUND_SENDERS = ('bot', 'staff')

LIMITATIONS = (
    'messages_only_from_synced_lead_episodes',
    'messages_capped_per_lead',
    'bot_messages_not_split_ai_vs_automated',
    'delivery_status_is_last_synced_not_historical',
    'inbound_messages_have_no_delivery_status',
    'staff_message_outbox_status_is_not_whatsapp_delivery',
    'not_billable_meta_conversations',
)


class WhatsAppMetricsRangeError(ValueError):
    """Rango inválido (sin zona, vacío, invertido o mayor que MAX_RANGE_DAYS)."""


def _aware(value, name):
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise WhatsAppMetricsRangeError(f'{name} must be a timezone-aware datetime.')
    return value


def validate_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = _aware(start, 'start'), _aware(end, 'end')
    if end <= start:
        raise WhatsAppMetricsRangeError('end must be after start.')
    # 1 h of slack: 92 local days can span 92 d + 1 h across a DST change
    if end - start > timedelta(days=MAX_RANGE_DAYS, hours=1):
        raise WhatsAppMetricsRangeError(f'The range cannot exceed {MAX_RANGE_DAYS} days.')
    return start, end


def _business_tz(business) -> ZoneInfo:
    try:
        return ZoneInfo(getattr(business, 'timezone', None) or 'UTC')
    except Exception:  # noqa: BLE001 — an invalid stored zone falls back to UTC
        return ZoneInfo('UTC')


@dataclass
class _Message:
    sender: str
    status: Optional[str]
    sent_at: datetime
    conversation: str
    lead_id: object
    channel_id: object


def _messages(business, start, end) -> list[_Message]:
    rows = (
        LeadAgentMessage.objects
        .filter(
            lead__business=business,
            lead__agent_state__channel__business=business,
            sent_at__gte=start, sent_at__lt=end,
        )
        .values_list(
            'lead__agent_state__agent_instance_id', 'external_message_id', 'sender', 'status', 'sent_at',
            'lead__agent_state__external_conversation_id', 'lead_id', 'lead__agent_state__channel_id',
        )
        .order_by()
    )
    unique: dict[tuple, _Message] = {}
    for instance_id, message_id, sender, status, sent_at, conversation, lead_id, channel_id in rows.iterator(chunk_size=2000):
        key = (instance_id, message_id)
        current = unique.get(key)
        if current is None:
            unique[key] = _Message(sender, status, sent_at, conversation, lead_id, channel_id)
        elif _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(current.status, 0):
            current.status = status
    return list(unique.values())


def _days(start: datetime, end: datetime, tz: ZoneInfo) -> list[date]:
    first = start.astimezone(tz).date()
    last = (end - timedelta(microseconds=1)).astimezone(tz).date()
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def whatsapp_metrics(business, *, start: datetime, end: datetime) -> dict:
    """Métricas de [start, end) para `business`. Solo lectura."""
    start, end = validate_range(start, end)
    tz = _business_tz(business)

    channels = AgentChannel.objects.filter(business=business)
    has_channel = channels.exists()
    sync_observed = LeadAgentState.objects.filter(lead__business=business, channel__business=business).exists()
    available = has_channel and sync_observed

    messages = _messages(business, start, end) if available else []
    inbound = [m for m in messages if m.sender == 'patient']
    outbound = [m for m in messages if m.sender in OUTBOUND_SENDERS]

    def counted(value):
        # null = unknown (no agent channel or nothing ever synced), never 0
        return value if available else None

    status_counts = {key: 0 for key in ('sent', 'delivered', 'read', 'failed', 'unknown')}
    for m in outbound:
        status_counts[m.status or 'unknown'] += 1

    # Leads that hit the agent's per-lead cap may be missing messages
    capped = (
        LeadAgentMessage.objects.filter(lead__business=business, lead__agent_state__channel__business=business,
                                        lead_id__in={m.lead_id for m in messages})
        .values('lead_id').annotate(n=Count('id')).filter(n__gte=SYNCED_MESSAGES_PER_LEAD_CAP).count()
        if messages else 0
    )

    states = LeadAgentState.objects.filter(lead__business=business, channel__business=business)
    handoffs_requested = states.filter(handoff_requested_at__gte=start, handoff_requested_at__lt=end).count()
    handoffs_paused = states.filter(handoff_paused_at__gte=start, handoff_paused_at__lt=end).count()
    activities = LeadActivity.objects.filter(business=business, lead__business=business,
                                             created_at__gte=start, created_at__lt=end)
    takeovers = activities.filter(kind=LeadActivity.Kind.TAKEOVER_APPLIED).count()
    releases = activities.filter(kind=LeadActivity.Kind.RELEASE_APPLIED).count()
    staff = LeadStaffMessage.objects.filter(lead__business=business, occurred_at__gte=start, occurred_at__lt=end)
    staff_counts = dict(staff.values_list('status').annotate(n=Count('id')).order_by())

    by_day = {day: {'inbound': 0, 'outbound': 0, 'conversations': set()} for day in _days(start, end, tz)}
    for m in messages:
        day = m.sent_at.astimezone(tz).date()
        bucket = by_day.get(day)
        if bucket is None:  # cannot happen inside [start, end); defensive
            continue
        bucket['inbound' if m.sender == 'patient' else 'outbound'] += 1
        bucket['conversations'].add(m.conversation)

    per_channel = {}
    for m in messages:
        per_channel[m.channel_id] = per_channel.get(m.channel_id, 0) + 1
    channel_rows = {c.pk: c for c in channels.filter(pk__in=per_channel)}

    return {
        'contract_version': CONTRACT_VERSION,
        'business_id': business.pk,
        'timezone': str(tz),
        'range': {'start': start.isoformat(), 'end': end.isoformat()},
        'source': SOURCE,
        'available': available,
        'totals': {
            'messages': counted(len(messages)),
            'inbound': counted(len(inbound)),
            'outbound': counted(len(outbound)),
            'ai_generated': None,         # not distinguishable from `bot`
            'automated_non_ai': None,     # not distinguishable from `bot`
        },
        'by_sender': {
            'patient': counted(len(inbound)),
            'bot': counted(sum(1 for m in outbound if m.sender == 'bot')),
            'staff': counted(sum(1 for m in outbound if m.sender == 'staff')),
        },
        'outbound_status': {
            'semantics': 'last_synced_status',
            **{key: counted(value) for key, value in status_counts.items()},
        },
        'conversations': {
            'with_activity': counted(len({m.conversation for m in messages})),
            'leads_with_activity': counted(len({m.lead_id for m in messages})),
        },
        'handoffs': {
            'requested': counted(handoffs_requested),
            'bot_paused_for_reception': counted(handoffs_paused),
            'takeovers_applied': counted(takeovers),
            'releases_applied': counted(releases),
        },
        'staff_messages': {
            'semantics': 'mirubro_outbox_to_agent',
            'requested': sum(staff_counts.values()),
            'queued_in_agent': staff_counts.get(LeadStaffMessage.Status.DELIVERED, 0),
            'pending': staff_counts.get(LeadStaffMessage.Status.PENDING, 0)
            + staff_counts.get(LeadStaffMessage.Status.DELIVERING, 0),
            'failed': staff_counts.get(LeadStaffMessage.Status.FAILED, 0),
        },
        'channels': [
            {
                'channel_id': str(channel_id),
                'phone_number_id': channel_rows[channel_id].phone_number_id if channel_id in channel_rows else None,
                'is_active': channel_rows[channel_id].is_active if channel_id in channel_rows else None,
                'messages': count,
            }
            for channel_id, count in sorted(per_channel.items(), key=lambda item: str(item[0]))
        ],
        'daily': [
            {
                'date': day.isoformat(),
                'inbound': counted(bucket['inbound']),
                'outbound': counted(bucket['outbound']),
                'conversations': counted(len(bucket['conversations'])),
            }
            for day, bucket in sorted(by_day.items())
        ],
        'coverage': {
            'has_agent_channel': has_channel,
            'sync_observed': sync_observed,
            'leads_at_message_cap': capped,
            'limitations': list(LIMITATIONS),
        },
    }
