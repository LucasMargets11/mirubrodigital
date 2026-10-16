"""MIRUBRO HUMAN MESSAGES: mensajes de recepción hacia el paciente por WhatsApp.

Outbox durable (`LeadStaffMessage`) con el mismo patrón que
`services.takeover` (MIRUBRO TAKEOVER 05A): pedido humano → fila `pending` en
su propia transacción + kick Celery best-effort (after-commit); entrega con
claim corto (skip_locked, attempts, lease) y clasificación de la respuesta del
agente. Nunca se marca `delivered` sin una respuesta real `queued`/`duplicate`.

Reusa la credencial y el feature flag de MIRUBRO TAKEOVER (`AGENT_TAKEOVER_*`):
no hay secreto ni flag propios para esta dirección (ver
`human_message_client`). No se valida localmente si la conversación está
`taken`: el agente es la fuente de verdad (puede haberse auto-pausado sin que
MiRubro lo sepa todavía) y responde `conversation_not_taken` si no corresponde.
"""
from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.business_notifications import on_commit_safely

from .. import human_message_client as client
from ..models import Lead, LeadStaffMessage
from .takeover import TakeoverUnavailable, conversation_id_for, takeover_enabled

logger = logging.getLogger('apps.leads.human_messages')

Status = LeadStaffMessage.Status

TEXT_MAX_CODE_POINTS = client.TEXT_MAX_CODE_POINTS


class MessageTextInvalid(Exception):
    """El texto no cumple el contrato (vacío, demasiado largo o con NUL)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise MessageTextInvalid('blank')
    # len() de un str de Python cuenta code points, igual que el límite del contrato.
    if len(text) > TEXT_MAX_CODE_POINTS:
        raise MessageTextInvalid('too_long')
    if '\x00' in text:
        raise MessageTextInvalid('invalid_characters')
    return text


def _kick(message_id, *, countdown: int | None = None) -> None:
    def _enqueue():
        from ..tasks import deliver_staff_message

        if countdown:
            deliver_staff_message.apply_async((str(message_id),), countdown=countdown)
        else:
            deliver_staff_message.delay(str(message_id))

    # Best-effort: si el broker falla, el Beat lo recupera (el mensaje ya es durable).
    on_commit_safely(_enqueue, description=f'human_message kick message={message_id}')


def send_staff_message(lead: Lead, text: str, *, user) -> LeadStaffMessage:
    """Encola el mensaje (outbox pending) en su propia transacción; el HTTP sale después del commit."""
    if not takeover_enabled():
        raise TakeoverUnavailable('takeover_disabled')
    conversation_id = conversation_id_for(lead)
    if conversation_id is None:
        raise TakeoverUnavailable('conversation_unavailable')
    clean_text = _validate_text(text)

    now = timezone.now()
    with transaction.atomic():
        message = LeadStaffMessage.objects.create(
            lead=lead, text=clean_text, occurred_at=now, created_by=user,
            status=Status.PENDING, next_attempt_at=now,
        )
        _kick(message.pk)
        logger.info('human_message_queued msg=%s lead=%s', message.pk, lead.pk)
    return message


# ── Entrega ─────────────────────────────────────────────────────────────────

def _backoff_seconds(attempts: int) -> int:
    backoff = tuple(getattr(settings, 'AGENT_TAKEOVER_RETRY_BACKOFF_SECONDS', (30, 60, 120, 240, 480, 900)))
    return int(backoff[min(max(attempts, 1), len(backoff)) - 1])


def _max_attempts() -> int:
    return int(getattr(settings, 'AGENT_TAKEOVER_MAX_ATTEMPTS', 10))


def _lease() -> dt.timedelta:
    return dt.timedelta(seconds=int(getattr(settings, 'AGENT_TAKEOVER_DELIVERY_LEASE_SECONDS', 60)))


def _claim(message_id, now) -> LeadStaffMessage | None:
    with transaction.atomic():
        message = (
            LeadStaffMessage.objects.select_for_update(skip_locked=True, of=('self',))
            .select_related('lead__agent_state')
            .filter(pk=message_id)
            .first()
        )
        if message is None:
            return None
        due = message.status == Status.PENDING and message.next_attempt_at <= now
        stuck = message.status == Status.DELIVERING and message.lease_until <= now
        if not (due or stuck):
            return None
        message.status = Status.DELIVERING
        message.attempts += 1
        message.last_attempt_at = now
        message.lease_until = now + _lease()
        message.next_attempt_at = None
        message.save(update_fields=['status', 'attempts', 'last_attempt_at', 'lease_until', 'next_attempt_at'])
        return message


def deliver_staff_message(message_id, *, send=None, now=None) -> str | None:
    """Un intento de entrega si corresponde. Idempotente y seguro en paralelo.

    Devuelve 'delivered' | 'retry' | 'failed', o None si no correspondía
    (flag apagado, otro worker lo tiene, no vencido, ya final).
    """
    if not takeover_enabled():
        return None
    now = now or timezone.now()
    message = _claim(message_id, now)
    if message is None:
        return None

    conversation_id = conversation_id_for(message.lead)
    if conversation_id is None:
        # No debería pasar (external_conversation_id es inmutable una vez
        # creado el LeadAgentState); failsafe defensivo, nunca deja colgado.
        return _record_response(message.pk, message.attempts, client.AgentMessageResponse(
            kind=client.KIND_TERMINAL, error_code='conversation_unavailable',
        ), now=now)

    payload = client.MessagePayload(
        external_conversation_id=conversation_id, event_id=message.event_id,
        client_message_id=message.client_message_id, business_id=message.lead.business_id,
        occurred_at=message.occurred_at, text=message.text,
    )
    send = send or client.send_message
    try:
        response = send(payload)
    except client.HumanMessageClientConfigError:
        logger.error('human_message_client_not_configured msg=%s', message.pk)
        response = client.AgentMessageResponse(kind=client.KIND_RETRYABLE, error_code='client_not_configured')
    except Exception:  # noqa: BLE001 — nunca dejar el mensaje colgado en delivering
        logger.exception('human_message_send_crashed msg=%s', message.pk)
        response = client.AgentMessageResponse(kind=client.KIND_RETRYABLE, error_code='client_error')
    return _record_response(message.pk, message.attempts, response, now=now)


def _record_response(message_id, attempts, response: client.AgentMessageResponse, *, now=None) -> str | None:
    now = now or timezone.now()
    with transaction.atomic():
        message = LeadStaffMessage.objects.select_for_update(of=('self',)).get(pk=message_id)
        if message.status != Status.DELIVERING or message.attempts != attempts:
            # Otro intento (lease vencido) tomó el mensaje: su resultado manda.
            return None
        message.last_status = response.http_status
        message.lease_until = None
        fields = ['status', 'last_status', 'lease_until', 'last_error', 'next_attempt_at', 'result',
                  'delivered_at', 'failed_at', 'message_id']

        log_extra = f'msg={message.pk} lead={message.lead_id} attempt={message.attempts} http={response.http_status}'

        if response.kind == client.KIND_RETRYABLE:
            message.last_error = response.error_code
            if message.attempts >= _max_attempts():
                message.status = Status.FAILED
                message.failed_at = now
                message.next_attempt_at = None
                message.save(update_fields=fields)
                logger.error('human_message_exhausted %s error=%s', log_extra, response.error_code)
                return Status.FAILED
            delay = _backoff_seconds(message.attempts)
            message.status = Status.PENDING
            message.next_attempt_at = now + dt.timedelta(seconds=delay)
            message.save(update_fields=fields)
            logger.warning('human_message_retry %s error=%s in=%ss', log_extra, response.error_code, delay)
            _kick(message.pk, countdown=delay)
            return 'retry'

        if response.kind == client.KIND_TERMINAL:
            message.status = Status.FAILED
            message.failed_at = now
            message.next_attempt_at = None
            message.last_error = response.error_code
            message.save(update_fields=fields)
            logger.error('human_message_failed %s error=%s', log_extra, response.error_code)
            return Status.FAILED

        # 201 queued | 200 duplicate
        message.status = Status.DELIVERED
        message.result = response.result
        message.message_id = response.message_id
        message.delivered_at = now
        message.last_error = None
        message.next_attempt_at = None
        message.save(update_fields=fields)
        logger.info('human_message_delivered %s result=%s message_id=%s', log_extra, response.result, response.message_id)
        return Status.DELIVERED


# ── Barrido (Beat) ──────────────────────────────────────────────────────────

DEFAULT_BATCH_SIZE = 100


def retry_due_staff_messages(*, now=None, send=None, batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, int]:
    """Pendientes vencidos (reintentos o kicks perdidos) + envíos colgados. Seguro en paralelo."""
    counts = {'due': 0, 'delivered': 0, 'retry': 0, 'failed': 0, 'noop': 0, 'errors': 0}
    if not takeover_enabled():
        return counts
    now = now or timezone.now()
    ids = list(
        LeadStaffMessage.objects.filter(
            Q(status=Status.PENDING, next_attempt_at__lte=now)
            | Q(status=Status.DELIVERING, lease_until__lte=now)
        ).order_by('created_at').values_list('id', flat=True)[:batch_size]
    )
    counts['due'] = len(ids)
    for message_id in ids:
        try:
            outcome = deliver_staff_message(message_id, send=send, now=now)
        except Exception:  # noqa: BLE001 — aislar fallos por mensaje
            logger.exception('human_message_sweep_error msg=%s', message_id)
            counts['errors'] += 1
            continue
        if outcome is None:
            counts['noop'] += 1
        elif outcome == Status.DELIVERED:
            counts['delivered'] += 1
        elif outcome == 'retry':
            counts['retry'] += 1
        else:
            counts['failed'] += 1
    return counts


# ── Decoración `authored_by` para el historial (GET messages, LEADS 05C) ────

def authored_by_map(lead: Lead, external_message_ids: list[str]) -> dict[str, dict]:
    """`external_message_id` (== `message_id` que devolvió el agente) → `{id, display_name}`.

    Solo cubre mensajes de staff que YA se encolaron con éxito en el agente
    (`status=delivered`): un mensaje que todavía está en outbox (pending/
    delivering) o que falló definitivamente no tiene `message_id` y por lo
    tanto nunca va a hacer match acá (ni va a sincronizar nunca como
    `LeadAgentMessage`, en el caso de un fallo terminal).
    """
    from apps.customers.serializers import _author_display_name

    if not external_message_ids:
        return {}
    rows = (
        LeadStaffMessage.objects.filter(lead=lead, status=Status.DELIVERED, message_id__in=external_message_ids)
        .select_related('created_by')
    )
    result: dict[str, dict] = {}
    for row in rows:
        if row.created_by_id is None or row.message_id is None:
            continue
        result[row.message_id] = {'id': row.created_by_id, 'display_name': _author_display_name(row.created_by)}
    return result
