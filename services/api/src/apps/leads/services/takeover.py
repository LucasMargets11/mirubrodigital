"""Control humano de la conversación: takeover / release hacia el agente (MIRUBRO TAKEOVER 05A).

Máquina de estados de `ConversationControl` (ver docs/MIRUBRO_TAKEOVER_CLIENT.md):

    active ──takeover──▶ takeover_pending ──ACK──▶ taken
    taken  ──release───▶ release_pending  ──ACK──▶ active
    *_pending ──fallo terminal / reintentos agotados / version_regression──▶ error
    error  ──takeover|release (versión nueva)──▶ *_pending

Reglas:
- Pedido humano (`request_conversation_command`): en UNA transacción bloquea
  la fila de control, valida la transición, `command_version += 1`, crea el
  `TakeoverCommand` pending y mueve el estado a `*_pending`. El HTTP sale
  después del commit (kick Celery best-effort + Beat de recuperación).
- Pedido repetido (mismo estado o mismo pending) → idempotente, sin comando nuevo.
  La acción opuesta mientras hay un comando en vuelo → `TakeoverConflict`.
- Entrega (`deliver_takeover_command`): claim corto (skip_locked, attempts+1,
  lease) → HTTP fuera de transacción → resultado bajo lock control → command,
  fenced por `attempts`. El resultado de un comando solo mueve el estado
  operativo si sigue siendo el vigente (`command.version == control.command_version`):
  un ACK tardío de un comando viejo nunca pisa un estado más nuevo.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.business_notifications import on_commit_safely

from .. import takeover_client as client
from ..models import (
    EXTERNAL_CONVERSATION_ID_REGEX, ConversationControl, Lead, LeadActivity, LeadAgentState, TakeoverCommand,
)

logger = logging.getLogger('apps.leads.takeover')

State = ConversationControl.State
Action = TakeoverCommand.Action
CmdStatus = TakeoverCommand.Status
K = LeadActivity.Kind

_CONVERSATION_ID_RE = re.compile(EXTERNAL_CONVERSATION_ID_REGEX)

ERROR_VERSION_REGRESSION = 'version_regression'
ERROR_UNEXPECTED_AGENT_STATE = 'unexpected_agent_state'
ERROR_DELIVERY_EXHAUSTED = 'delivery_exhausted'
ERROR_SUPERSEDED = 'superseded'

_PENDING_FOR = {Action.TAKEOVER: State.TAKEOVER_PENDING, Action.RELEASE: State.RELEASE_PENDING}
_DONE_FOR = {Action.TAKEOVER: State.TAKEN, Action.RELEASE: State.ACTIVE}
_EXPECTED_AGENT_STATE = {Action.TAKEOVER: 'paused', Action.RELEASE: 'active'}
_REQUESTED_KIND = {Action.TAKEOVER: K.TAKEOVER_REQUESTED, Action.RELEASE: K.RELEASE_REQUESTED}
_APPLIED_KIND = {Action.TAKEOVER: K.TAKEOVER_APPLIED, Action.RELEASE: K.RELEASE_APPLIED}
_FAILED_KIND = {Action.TAKEOVER: K.TAKEOVER_FAILED, Action.RELEASE: K.RELEASE_FAILED}


class TakeoverUnavailable(Exception):
    """La acción no está disponible (flag apagado o Lead sin conversación del agente)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class TakeoverConflict(Exception):
    """Hay un comando opuesto en vuelo: se decide de nuevo cuando termine."""


def takeover_enabled() -> bool:
    return bool(getattr(settings, 'AGENT_TAKEOVER_ENABLED', False))


def conversation_id_for(lead: Lead) -> str | None:
    """`LeadAgentState.external_conversation_id` con el formato del agente; nunca teléfono ni lead id."""
    try:
        state = lead.agent_state
    except LeadAgentState.DoesNotExist:
        return None
    value = state.external_conversation_id
    return value if value and _CONVERSATION_ID_RE.match(value) else None


# ── Pedido humano ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommandRequestResult:
    state: str
    command_version: int
    created: bool


def _next_version(control: ConversationControl) -> int:
    # Nunca reutilizar ni quedar por debajo de lo que el agente ya aplicó.
    return max(control.command_version, control.agent_applied_version) + 1


def _locked_control(business_id: int, conversation_id: str, *, create: bool) -> ConversationControl | None:
    if create:
        # INSERT … ON CONFLICT DO NOTHING: dos primeros pedidos simultáneos no
        # chocan con IntegrityError; el segundo espera al primero y lo ve.
        ConversationControl.objects.bulk_create(
            [ConversationControl(business_id=business_id, external_conversation_id=conversation_id)],
            ignore_conflicts=True,
        )
    return (
        ConversationControl.objects.select_for_update(of=('self',))
        .filter(business_id=business_id, external_conversation_id=conversation_id)
        .first()
    )


def _record_activity(lead_id, business_id, kind, *, actor=None, **metadata) -> None:
    if lead_id is None:
        return
    LeadActivity.objects.create(
        business_id=business_id, lead_id=lead_id, kind=kind, actor=actor,
        created_at=timezone.now(), metadata=metadata,
    )


def _kick(command_id, *, countdown: int | None = None) -> None:
    def _enqueue():
        from ..tasks import deliver_takeover_command

        if countdown:
            deliver_takeover_command.apply_async((str(command_id),), countdown=countdown)
        else:
            deliver_takeover_command.delay(str(command_id))

    # Best-effort: si el broker falla el Beat lo recupera (el comando ya es durable).
    on_commit_safely(_enqueue, description=f'takeover kick command={command_id}')


def request_conversation_command(lead: Lead, action: str, *, user) -> CommandRequestResult:
    if not takeover_enabled():
        raise TakeoverUnavailable('takeover_disabled')
    conversation_id = conversation_id_for(lead)
    if conversation_id is None:
        raise TakeoverUnavailable('conversation_unavailable')

    with transaction.atomic():
        control = _locked_control(lead.business_id, conversation_id, create=action == Action.TAKEOVER)
        if control is None:
            # Release sin control = nunca se tomó: ya está activa.
            return CommandRequestResult(state=State.ACTIVE, command_version=0, created=False)

        pending, done = _PENDING_FOR[action], _DONE_FOR[action]
        if control.state in (pending, done):
            return CommandRequestResult(state=control.state, command_version=control.command_version, created=False)
        if control.state not in (State.ACTIVE, State.TAKEN, State.ERROR):
            # El opuesto está en vuelo (MVP: una sola acción a la vez).
            raise TakeoverConflict()

        now = timezone.now()
        # Un pending viejo (posible solo tras un error) no se envía más.
        TakeoverCommand.objects.filter(conversation_control=control, status=CmdStatus.PENDING).update(
            status=CmdStatus.FAILED, failed_at=now, last_error=ERROR_SUPERSEDED, next_attempt_at=None,
        )
        version = _next_version(control)
        command = TakeoverCommand.objects.create(
            conversation_control=control, version=version, action=action, occurred_at=now,
            next_attempt_at=now, requested_by=user, requested_from_lead=lead,
        )
        control.command_version = version
        control.last_command_action = action
        control.last_event_id = command.event_id
        control.state = pending
        control.last_command_at = now
        control.last_error_code = None
        control.save(update_fields=[
            'command_version', 'last_command_action', 'last_event_id', 'state', 'last_command_at',
            'last_error_code', 'updated_at',
        ])
        _record_activity(lead.pk, lead.business_id, _REQUESTED_KIND[action], actor=user, version=version)
        logger.info(
            'takeover_command_requested control=%s cmd=%s action=%s v=%s event=%s',
            control.pk, command.pk, action, version, command.event_id,
        )
        _kick(command.pk)
    return CommandRequestResult(state=pending, command_version=version, created=True)


# ── Entrega ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Claim:
    command_id: object
    control_id: object
    attempts: int
    payload: client.CommandPayload


def _backoff_seconds(attempts: int) -> int:
    backoff = tuple(getattr(settings, 'AGENT_TAKEOVER_RETRY_BACKOFF_SECONDS', (30, 60, 120, 240, 480, 900)))
    return int(backoff[min(max(attempts, 1), len(backoff)) - 1])


def _max_attempts() -> int:
    return int(getattr(settings, 'AGENT_TAKEOVER_MAX_ATTEMPTS', 10))


def _lease() -> dt.timedelta:
    return dt.timedelta(seconds=int(getattr(settings, 'AGENT_TAKEOVER_DELIVERY_LEASE_SECONDS', 60)))


def _claim(command_id, now) -> _Claim | None:
    with transaction.atomic():
        command = (
            TakeoverCommand.objects.select_for_update(skip_locked=True, of=('self',))
            .select_related('conversation_control')
            .filter(pk=command_id)
            .first()
        )
        if command is None:
            return None
        due = command.status == CmdStatus.PENDING and command.next_attempt_at <= now
        stuck = command.status == CmdStatus.DELIVERING and command.lease_until <= now
        if not (due or stuck):
            return None
        control = command.conversation_control
        if control.command_version > command.version:
            # Ya hay un comando más nuevo: este no tiene nada que decir.
            command.status = CmdStatus.FAILED
            command.failed_at = now
            command.last_error = ERROR_SUPERSEDED
            command.next_attempt_at = None
            command.lease_until = None
            command.save(update_fields=['status', 'failed_at', 'last_error', 'next_attempt_at', 'lease_until'])
            return None
        command.status = CmdStatus.DELIVERING
        command.attempts += 1
        command.last_attempt_at = now
        command.lease_until = now + _lease()
        command.next_attempt_at = None
        command.save(update_fields=['status', 'attempts', 'last_attempt_at', 'lease_until', 'next_attempt_at'])
        return _Claim(
            command_id=command.pk, control_id=control.pk, attempts=command.attempts,
            payload=client.CommandPayload(
                external_conversation_id=control.external_conversation_id, action=command.action,
                event_id=command.event_id, version=command.version, occurred_at=command.occurred_at,
                business_id=control.business_id,
            ),
        )


def deliver_takeover_command(command_id, *, send=None, now=None) -> str | None:
    """Un intento de entrega si corresponde. Idempotente y seguro en paralelo.

    Devuelve 'delivered' | 'retry' | 'failed', o None si no correspondía
    (flag apagado, otro worker lo tiene, no vencido, ya final, superseded).
    """
    if not takeover_enabled():
        return None
    claim = _claim(command_id, now or timezone.now())
    if claim is None:
        return None
    send = send or client.send_command
    try:
        response = send(claim.payload)
    except client.TakeoverClientConfigError:
        logger.error('takeover_client_not_configured cmd=%s', claim.command_id)
        response = client.AgentCommandResponse(kind=client.KIND_RETRYABLE, error_code='client_not_configured')
    except Exception:  # noqa: BLE001 — nunca dejar el comando colgado en delivering
        logger.exception('takeover_send_crashed cmd=%s', claim.command_id)
        response = client.AgentCommandResponse(kind=client.KIND_RETRYABLE, error_code='client_error')
    return record_command_response(claim, response)


def _fail_control(control, command, error_code) -> None:
    control.state = State.ERROR
    control.last_error_code = error_code
    control.save(update_fields=['state', 'last_error_code', 'updated_at'])
    _record_activity(
        command.requested_from_lead_id, control.business_id, _FAILED_KIND[command.action],
        version=command.version, error_code=error_code,
    )


def record_command_response(claim: _Claim, response: client.AgentCommandResponse, *, now=None) -> str | None:
    now = now or timezone.now()
    with transaction.atomic():
        # Orden de locks: control → command (igual que el pedido humano).
        control = ConversationControl.objects.select_for_update(of=('self',)).get(pk=claim.control_id)
        command = TakeoverCommand.objects.select_for_update(of=('self',)).get(pk=claim.command_id)
        if command.status != CmdStatus.DELIVERING or command.attempts != claim.attempts:
            # Otro intento (lease vencido) tomó el comando: su resultado manda.
            return None
        current = command.version == control.command_version
        command.last_status = response.http_status
        command.lease_until = None
        fields = ['status', 'last_status', 'lease_until', 'last_error', 'next_attempt_at', 'result',
                  'delivered_at', 'failed_at', 'agent_applied_version']

        log_extra = (
            f'control={control.pk} cmd={command.pk} action={command.action} v={command.version} '
            f'attempt={command.attempts} http={response.http_status}'
        )

        if response.kind == client.KIND_RETRYABLE:
            command.last_error = response.error_code
            if command.attempts >= _max_attempts():
                command.status = CmdStatus.FAILED
                command.failed_at = now
                command.next_attempt_at = None
                command.save(update_fields=fields)
                logger.error('takeover_command_exhausted %s error=%s', log_extra, response.error_code)
                if current:
                    _fail_control(control, command, ERROR_DELIVERY_EXHAUSTED)
                return CmdStatus.FAILED
            delay = _backoff_seconds(command.attempts)
            command.status = CmdStatus.PENDING
            command.next_attempt_at = now + dt.timedelta(seconds=delay)
            command.save(update_fields=fields)
            if current:
                # Sigue pending; el código visible explica la demora.
                control.last_error_code = response.error_code
                control.save(update_fields=['last_error_code', 'updated_at'])
            logger.warning('takeover_command_retry %s error=%s in=%ss', log_extra, response.error_code, delay)
            _kick(command.pk, countdown=delay)
            return 'retry'

        if response.kind == client.KIND_TERMINAL:
            command.status = CmdStatus.FAILED
            command.failed_at = now
            command.next_attempt_at = None
            command.last_error = response.error_code
            command.save(update_fields=fields)
            logger.error('takeover_command_failed %s error=%s', log_extra, response.error_code)
            if current:
                _fail_control(control, command, response.error_code)
            return CmdStatus.FAILED

        # 200 applied | duplicate | stale
        applied_version = response.applied_version
        command.status = CmdStatus.DELIVERED
        command.result = response.result
        command.delivered_at = now
        command.agent_applied_version = applied_version
        command.last_error = None
        command.next_attempt_at = None
        command.save(update_fields=fields)
        if applied_version > control.agent_applied_version:
            control.agent_applied_version = applied_version
            control.save(update_fields=['agent_applied_version', 'updated_at'])

        if response.result == TakeoverCommand.Result.STALE or applied_version > control.command_version:
            if applied_version > control.command_version:
                # El agente tiene una versión que MiRubro nunca emitió (o perdió):
                # no se baja la del agente; el próximo comando sale por encima.
                logger.error('takeover_version_regression %s applied_version=%s control_version=%s',
                             log_extra, applied_version, control.command_version)
                _fail_control(control, command, ERROR_VERSION_REGRESSION)
            else:
                logger.info('takeover_command_stale %s applied_version=%s', log_extra, applied_version)
            return CmdStatus.DELIVERED

        if not current:
            # ACK tardío de un comando viejo: entregado, pero el estado vigente no se toca.
            logger.info('takeover_command_late_ack %s result=%s control_version=%s',
                        log_extra, response.result, control.command_version)
            return CmdStatus.DELIVERED

        if applied_version != command.version or response.agent_state != _EXPECTED_AGENT_STATE[command.action]:
            logger.error('takeover_unexpected_agent_state %s result=%s applied_version=%s state=%s',
                         log_extra, response.result, applied_version, response.agent_state)
            _fail_control(control, command, ERROR_UNEXPECTED_AGENT_STATE)
            return CmdStatus.DELIVERED

        control.state = _DONE_FOR[command.action]
        control.last_success_at = now
        control.last_error_code = None
        if command.action == Action.TAKEOVER:
            control.taken_at = now
            control.taken_by_id = command.requested_by_id
        else:
            control.released_at = now
            control.taken_at = None
            control.taken_by = None
        control.save(update_fields=[
            'state', 'last_success_at', 'last_error_code', 'taken_at', 'taken_by', 'released_at', 'updated_at',
        ])
        _record_activity(
            command.requested_from_lead_id, control.business_id, _APPLIED_KIND[command.action],
            version=command.version,
        )
        logger.info('takeover_command_delivered %s result=%s state=%s', log_extra, response.result, control.state)
        return CmdStatus.DELIVERED


# ── Barrido (Beat) ──────────────────────────────────────────────────────────

DEFAULT_BATCH_SIZE = 100


def retry_due_takeover_commands(*, now=None, send=None, batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, int]:
    """Pendientes vencidos (reintentos o kicks perdidos) + envíos colgados. Seguro en paralelo."""
    counts = {'due': 0, 'delivered': 0, 'retry': 0, 'failed': 0, 'noop': 0, 'errors': 0}
    if not takeover_enabled():
        return counts
    now = now or timezone.now()
    ids = list(
        TakeoverCommand.objects.filter(
            Q(status=CmdStatus.PENDING, next_attempt_at__lte=now)
            | Q(status=CmdStatus.DELIVERING, lease_until__lte=now)
        ).order_by('created_at').values_list('id', flat=True)[:batch_size]
    )
    counts['due'] = len(ids)
    for command_id in ids:
        try:
            outcome = deliver_takeover_command(command_id, send=send, now=now)
        except Exception:  # noqa: BLE001 — aislar fallos por comando
            logger.exception('takeover_sweep_error cmd=%s', command_id)
            counts['errors'] += 1
            continue
        counts[outcome if outcome in counts else 'noop'] += 1
    return counts


# ── Lectura ─────────────────────────────────────────────────────────────────

def control_for_lead(lead: Lead) -> ConversationControl | None:
    conversation_id = conversation_id_for(lead)
    if conversation_id is None:
        return None
    return (
        ConversationControl.objects.select_related('taken_by')
        .filter(business_id=lead.business_id, external_conversation_id=conversation_id)
        .first()
    )
