"""
billing/webhook_lifecycle.py
============================
Slice 5B.4 — delivery lifecycle for inbound Mercado Pago webhooks.

Every WebhookDelivery (all topics, including ``payment``) goes through:

    RECEIVED ──claim──▶ PROCESSING ──▶ PROCESSED    (applied, or already applied)
                                  ├──▶ IGNORED      (known no-op / permanent)
                                  └──▶ FAILED       (transient; next_retry_at set)
    FAILED ──claim (next_retry_at <= now)──▶ PROCESSING ──▶ … ──▶ DEAD_LETTER
                                                  (attempts >= max_attempts)

Claiming
--------
A worker claims a delivery in a SHORT transaction:
``select_for_update(skip_locked=True)`` → eligibility check → status
PROCESSING, attempts += 1, last_attempt_at = now → commit. The business
logic then runs OUTSIDE that transaction (it performs HTTP calls to MP and
has its own atomic blocks — e.g. the merchant refresh safe-state markers
from 5B.3 must commit independently). Two workers therefore can never run
the same delivery at the same time: the second one either skips the locked
row or, after the first commits, sees a fresh PROCESSING lease.

A PROCESSING row whose lease expired (worker crashed mid-run) becomes
claimable again; the final status write is guarded by (status, attempts)
so a worker that lost its lease never overwrites a newer attempt's result.

Classification
--------------
- Handler returns normally / returns ``WebhookOutcome.processed()`` → PROCESSED
- Handler returns ``WebhookOutcome.ignored(category)``              → IGNORED
- Handler raises ``WebhookTransientError(category)``                 → FAILED
- Handler raises ``WebhookPermanentError(category)``  → DEAD_LETTER at once
  (known non-recoverable condition that still needs a human; never retried)
- Any other exception (unexpected)        → FAILED, category ``internal_error``
- FAILED with attempts >= max_attempts                               → DEAD_LETTER

Ownership: each claim increments ``attempts``, which doubles as the
attempt's version token. The final write is conditioned on
(status=PROCESSING, attempts=<the claim's value>), so only the worker that
holds the current attempt can record a result.

Nothing written to ``error_message`` or to logs from here contains tokens:
see ``sanitize_error``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import WebhookDelivery

logger = logging.getLogger(__name__)

Status = WebhookDelivery.ProcessingStatus


# ─────────────────────────────────────────────────────────────────────────────
# Outcomes
# ─────────────────────────────────────────────────────────────────────────────

class WebhookTransientError(Exception):
    """Potentially recoverable failure — the delivery goes FAILED and is retried.

    ``category`` is a short machine-readable slug persisted on the delivery.
    The message must never contain credentials (it is sanitized anyway).
    """

    def __init__(self, category: str, message: str = ''):
        self.category = category
        super().__init__(message or category)


class WebhookPermanentError(Exception):
    """Known non-recoverable failure that needs manual intervention.

    The delivery goes straight to DEAD_LETTER (no automatic retry) and stays
    observable; an operator can replay it with
    ``retry_mp_webhooks --id <id> --revive-dead-letter`` once the cause is
    fixed (e.g. the Business reconnected Mercado Pago).
    """

    def __init__(self, category: str, message: str = ''):
        self.category = category
        super().__init__(message or category)


@dataclass(frozen=True)
class WebhookOutcome:
    status: str
    category: str = ''
    detail: str = ''

    @classmethod
    def processed(cls, detail: str = '') -> 'WebhookOutcome':
        return cls(Status.PROCESSED, '', detail)

    @classmethod
    def ignored(cls, category: str, detail: str = '') -> 'WebhookOutcome':
        return cls(Status.IGNORED, category, detail)


# ─────────────────────────────────────────────────────────────────────────────
# Retry policy (single source of truth — settings.MP_WEBHOOK_RETRY_*)
# ─────────────────────────────────────────────────────────────────────────────

def max_attempts() -> int:
    return max(1, int(getattr(settings, 'MP_WEBHOOK_RETRY_MAX_ATTEMPTS', 8)))


def processing_lease() -> timedelta:
    return timedelta(seconds=int(getattr(settings, 'MP_WEBHOOK_PROCESSING_LEASE_SECONDS', 900)))


def compute_next_retry_at(attempts: int, now=None):
    """Exponential backoff: base * 2**(attempts-1), capped at the max backoff."""
    now = now or timezone.now()
    base = int(getattr(settings, 'MP_WEBHOOK_RETRY_BASE_SECONDS', 300))
    cap = int(getattr(settings, 'MP_WEBHOOK_RETRY_MAX_BACKOFF_SECONDS', 6 * 3600))
    exponent = max(0, attempts - 1)
    delay = min(cap, base * (2 ** min(exponent, 20)))
    return now + timedelta(seconds=delay)


# ─────────────────────────────────────────────────────────────────────────────
# Sanitization
# ─────────────────────────────────────────────────────────────────────────────

_MAX_ERROR_LEN = 500

_SECRET_PATTERNS = (
    # Mercado Pago credential formats (access tokens, public keys).
    re.compile(r'\b(?:APP_USR|TEST)-[A-Za-z0-9_\-]{6,}'),
    re.compile(r'(?i)bearer\s+[A-Za-z0-9_\-\.=]+'),
    re.compile(
        r'(?i)(access_token|refresh_token|client_secret|authorization|x-signature)'
        r'(["\']?\s*[:=]\s*["\']?)[^\s,"\'}]+'
    ),
)


def _configured_secrets() -> list[str]:
    names = (
        'MP_ACCESS_TOKEN', 'MP_CLIENT_SECRET', 'MP_WEBHOOK_SECRET',
        'MP_TOKEN_ENCRYPTION_KEY',
    )
    values = [getattr(settings, n, None) for n in names]
    return [v for v in values if isinstance(v, str) and len(v) >= 6]


def sanitize_error(text) -> str:
    """Redact anything credential-shaped and truncate. Safe for DB and logs."""
    s = str(text or '')
    for secret in _configured_secrets():
        s = s.replace(secret, '[REDACTED]')
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            s = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}[REDACTED]', s)
        else:
            s = pattern.sub('[REDACTED]', s)
    if len(s) > _MAX_ERROR_LEN:
        s = s[:_MAX_ERROR_LEN - 1] + '…'
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Claim
# ─────────────────────────────────────────────────────────────────────────────

def claim_delivery(delivery_id, *, now=None, revive_dead_letter: bool = False):
    """
    Atomically claim a delivery for one processing attempt.

    Returns the claimed (PROCESSING) instance, or None when the row is
    locked by another worker, missing, or not eligible.
    """
    now = now or timezone.now()
    limit = max_attempts()
    with transaction.atomic():
        delivery = (
            WebhookDelivery.objects
            .select_for_update(skip_locked=True)
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None:
            return None

        st = delivery.processing_status
        if st == Status.RECEIVED:
            eligible = delivery.signature_valid
        elif st == Status.FAILED:
            eligible = True
        elif st == Status.PROCESSING:
            eligible = (
                delivery.last_attempt_at is None
                or delivery.last_attempt_at <= now - processing_lease()
            )
        elif st == Status.DEAD_LETTER:
            eligible = revive_dead_letter
        else:  # PROCESSED / IGNORED / DUPLICATED are terminal.
            eligible = False

        if not eligible:
            return None

        # Out of attempts (e.g. a crashed final attempt whose lease expired,
        # or a lowered max): dead-letter without running again.
        if st in (Status.FAILED, Status.PROCESSING) and delivery.attempts >= limit:
            delivery.processing_status = Status.DEAD_LETTER
            delivery.next_retry_at = None
            if st == Status.PROCESSING:
                delivery.error_category = 'lease_expired'
                delivery.error_message = 'Processing lease expired on the final attempt'
            delivery.processed_at = now
            delivery.save(update_fields=[
                'processing_status', 'next_retry_at', 'error_category',
                'error_message', 'processed_at',
            ])
            _log_final(delivery)
            return None

        delivery.processing_status = Status.PROCESSING
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.next_retry_at = None
        delivery.save(update_fields=[
            'processing_status', 'attempts', 'last_attempt_at', 'next_retry_at',
        ])
    delivery._error_at_claim = delivery.error_message
    return delivery


# ─────────────────────────────────────────────────────────────────────────────
# Process one delivery
# ─────────────────────────────────────────────────────────────────────────────

def process_delivery(delivery_id, *, revive_dead_letter: bool = False) -> str | None:
    """
    Claim → execute → record. Never raises.

    Returns the final status written, or None if the delivery was not
    claimed (locked elsewhere / not eligible).
    """
    try:
        claimed = claim_delivery(delivery_id, revive_dead_letter=revive_dead_letter)
    except Exception as exc:  # DB unavailable etc. — the row stays as it was.
        logger.error(
            "[webhook.lifecycle] claim failed delivery=%s error=%s",
            delivery_id, sanitize_error(f'{type(exc).__name__}: {exc}'),
        )
        return None
    if claimed is None:
        return None

    from .webhook_processor import execute_delivery

    try:
        outcome = execute_delivery(claimed)
    except WebhookTransientError as exc:
        return _record_failure(claimed, exc.category, str(exc))
    except WebhookPermanentError as exc:
        return _record_failure(claimed, exc.category, str(exc), permanent=True)
    except Exception as exc:
        return _record_failure(claimed, 'internal_error', f'{type(exc).__name__}: {exc}')

    if outcome is None:
        outcome = WebhookOutcome.processed()
    return _record_outcome(claimed, outcome)


def _guarded_update(delivery: WebhookDelivery, **fields) -> bool:
    """Write the attempt's result only if this worker still owns the lease."""
    try:
        updated = WebhookDelivery.objects.filter(
            pk=delivery.pk,
            processing_status=Status.PROCESSING,
            attempts=delivery.attempts,
        ).update(**fields)
    except Exception as exc:
        # Row stays PROCESSING; the lease expiry makes it retryable later.
        logger.error(
            "[webhook.lifecycle] could not record result delivery=%s error=%s",
            delivery.pk, sanitize_error(f'{type(exc).__name__}: {exc}'),
        )
        return False
    if not updated:
        logger.warning(
            "[webhook.lifecycle] lease lost — result discarded delivery=%s attempt=%s",
            delivery.pk, delivery.attempts,
        )
        return False
    for k, v in fields.items():
        setattr(delivery, k, v)
    return True


def _record_outcome(delivery: WebhookDelivery, outcome: WebhookOutcome) -> str | None:
    fields = {
        'processing_status': outcome.status,
        'error_category': outcome.category,
        'next_retry_at': None,
        'processed_at': timezone.now(),
    }
    if outcome.detail:
        fields['error_message'] = sanitize_error(outcome.detail)
    elif outcome.status == Status.PROCESSED:
        # Keep a note a handler wrote during THIS attempt (e.g. orphan
        # preapproval); otherwise clear the previous attempt's error.
        current = WebhookDelivery.objects.filter(pk=delivery.pk).values_list(
            'error_message', flat=True,
        ).first()
        wrote_note = current and current != getattr(delivery, '_error_at_claim', '')
        fields['error_message'] = sanitize_error(current) if wrote_note else ''
    if not _guarded_update(delivery, **fields):
        return None
    _log_final(delivery)
    return outcome.status


def _record_failure(delivery: WebhookDelivery, category: str, message: str,
                    *, permanent: bool = False) -> str | None:
    now = timezone.now()
    dead = permanent or delivery.attempts >= max_attempts()
    fields = {
        'processing_status': Status.DEAD_LETTER if dead else Status.FAILED,
        'error_category': category[:64],
        'error_message': sanitize_error(message),
        'next_retry_at': None if dead else compute_next_retry_at(delivery.attempts, now),
        'processed_at': now,
    }
    if not _guarded_update(delivery, **fields):
        return None
    _log_final(delivery)
    return fields['processing_status']


def _log_final(delivery: WebhookDelivery) -> None:
    level = logging.INFO
    if delivery.processing_status == Status.FAILED:
        level = logging.WARNING
    elif delivery.processing_status == Status.DEAD_LETTER:
        level = logging.ERROR
    logger.log(
        level,
        "[webhook.lifecycle] delivery=%s topic=%s resource_id=%s flow=%s attempt=%s "
        "status=%s category=%s next_retry_at=%s",
        delivery.pk, delivery.topic, delivery.resource_id, delivery.flow or '-',
        delivery.attempts, delivery.processing_status, delivery.error_category or '-',
        delivery.next_retry_at.isoformat() if delivery.next_retry_at else '-',
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sweeper (Celery Beat task + management command)
# ─────────────────────────────────────────────────────────────────────────────

def eligible_for_retry_qs(now=None):
    """
    Deliveries the automatic sweeper may pick up:
      - FAILED with next_retry_at <= now and attempts < max_attempts
      - PROCESSING whose lease expired (worker crashed mid-attempt)
      - RECEIVED (signature valid) never claimed within one lease period
        (process crashed between persistence and inline processing)
    DEAD_LETTER, IGNORED, PROCESSED and DUPLICATED are never included.
    """
    now = now or timezone.now()
    stale = now - processing_lease()
    return WebhookDelivery.objects.filter(
        Q(processing_status=Status.FAILED, next_retry_at__lte=now, attempts__lt=max_attempts())
        | Q(processing_status=Status.PROCESSING, last_attempt_at__lte=stale)
        | Q(processing_status=Status.RECEIVED, signature_valid=True, received_at__lte=stale)
    )


# Slice 5B.4.2 — the migration that creates the lifecycle columns. Until it
# is applied (deploy window: new worker/Beat started before `migrate`) the
# sweeper must not touch the table.
LIFECYCLE_MIGRATION = ('billing', '0023_webhookdelivery_retry_lifecycle')
_lifecycle_schema_ready = False


def lifecycle_schema_ready() -> bool:
    """True once LIFECYCLE_MIGRATION is recorded as applied (cached per process)."""
    global _lifecycle_schema_ready
    if not _lifecycle_schema_ready:
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder
        _lifecycle_schema_ready = (
            LIFECYCLE_MIGRATION in MigrationRecorder(connection).applied_migrations()
        )
    return _lifecycle_schema_ready


def retry_due_deliveries(*, limit: int = 100, now=None) -> dict:
    """Process every eligible delivery (up to ``limit``). Never raises."""
    if not lifecycle_schema_ready():
        logger.warning(
            "[webhook.lifecycle] retry sweep skipped: migration %s.%s not applied yet",
            *LIFECYCLE_MIGRATION,
        )
        return {'picked': 0, 'skipped': 0, 'schema_not_ready': True}
    now = now or timezone.now()
    ids = list(
        eligible_for_retry_qs(now)
        .order_by('next_retry_at', 'received_at')
        .values_list('pk', flat=True)[:limit]
    )
    counts = {'picked': len(ids), 'skipped': 0}
    for delivery_id in ids:
        result = process_delivery(delivery_id)
        key = result or 'skipped'
        counts[key] = counts.get(key, 0) + 1
    if ids:
        logger.info("[webhook.lifecycle] retry sweep: %s", counts)
    return counts
