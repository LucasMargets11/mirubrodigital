"""
billing/tasks.py — Celery periodic tasks for subscription lifecycle management.

expire_subscriptions
--------------------
Enforces time-based subscription state transitions for SubscriptionV2.

Transitions performed:
  1. ACTIVE   → PAST_DUE   when current_period_end has passed (sets grace_until)
  2. PAST_DUE → SUSPENDED  when grace_until has passed
  3. TRIALING → SUSPENDED  when trial_ends_at has passed without payment conversion

Design principles:
  - Idempotent: uses status-conditional filter+update so re-runs are safe.
  - Does NOT touch legacy business.Subscription or billing.Subscription.
  - Does NOT cancel subscriptions directly (cancellation is a billing flow concern).
  - Does NOT re-activate subscriptions (activation is handled by payment webhook).
  - Safety: _DEFAULT_GRACE_DAYS is used only as a last-resort fallback when
    grace_until was not set by the webhook. Webhooks should always set it.

Configure the schedule in settings.py via CELERY_BEAT_SCHEDULE.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Fallback grace period when a subscription enters PAST_DUE without an
# explicit grace_until set by the payment webhook.
# Kept deliberately conservative (3 days). Webhooks should always set
# grace_until explicitly; this only fires in edge cases.
_DEFAULT_GRACE_DAYS = 3


@shared_task(
    bind=True,
    name='billing.expire_subscriptions',
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def expire_subscriptions(self):
    """
    Enforce subscription lifecycle transitions based on time rules.

    Idempotent — all updates use optimistic status-conditional filters so
    that running the task twice produces the same final state.

    Returns:
        dict with transition counts: {
            'active_to_past_due': int,
            'past_due_to_suspended': int,
            'trial_to_suspended': int,
        }
    """
    from apps.billing.models import SubscriptionV2  # local import avoids circular

    now = timezone.now()
    counts = {
        'active_to_past_due': 0,
        'past_due_to_suspended': 0,
        'trial_to_suspended': 0,
    }

    try:
        counts['active_to_past_due'] = _transition_active_to_past_due(
            SubscriptionV2, now,
        )
        counts['past_due_to_suspended'] = _transition_past_due_to_suspended(
            SubscriptionV2, now,
        )
        counts['trial_to_suspended'] = _transition_trial_to_suspended(
            SubscriptionV2, now,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("[billing.task] expire_subscriptions failed: %s", exc)
        raise self.retry(exc=exc)

    logger.info("[billing.task] expire_subscriptions complete: %s", counts)
    return counts


# ──────────────────────────────────────────────────────────────────────────────
# Transition helpers (private)
# ──────────────────────────────────────────────────────────────────────────────

def _transition_active_to_past_due(SubscriptionV2, now) -> int:
    """
    ACTIVE → PAST_DUE when current_period_end < now.

    Sets grace_until to the existing value if already set, otherwise falls
    back to now + _DEFAULT_GRACE_DAYS.  The webhook should always set
    grace_until on the subscription before this task runs; the fallback
    is a safety net only.
    """
    expired = list(
        SubscriptionV2.objects
        .filter(
            status=SubscriptionV2.Status.ACTIVE,
            current_period_end__lt=now,
            current_period_end__isnull=False,
        )
        .values('pk', 'business_id', 'current_period_end', 'grace_until')
    )

    count = 0
    for row in expired:
        grace = row['grace_until'] or (now + timedelta(days=_DEFAULT_GRACE_DAYS))
        updated = SubscriptionV2.objects.filter(
            pk=row['pk'],
            status=SubscriptionV2.Status.ACTIVE,
        ).update(
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until=grace,
        )
        if updated:
            count += 1
            logger.info(
                "[billing.task] active→past_due business=%s sub=%s "
                "period_end=%s grace_until=%s",
                row['business_id'], row['pk'],
                row['current_period_end'], grace,
            )
    return count


def _transition_past_due_to_suspended(SubscriptionV2, now) -> int:
    """
    PAST_DUE → SUSPENDED when grace_until < now.

    Only affects subscriptions where grace_until is explicitly set.
    PAST_DUE subscriptions without grace_until are NOT touched here
    (they are either in an indeterminate state or should be reviewed manually).
    """
    grace_expired = list(
        SubscriptionV2.objects
        .filter(
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until__lt=now,
            grace_until__isnull=False,
        )
        .values('pk', 'business_id', 'grace_until')
    )

    count = 0
    for row in grace_expired:
        updated = SubscriptionV2.objects.filter(
            pk=row['pk'],
            status=SubscriptionV2.Status.PAST_DUE,
        ).update(status=SubscriptionV2.Status.SUSPENDED)
        if updated:
            count += 1
            logger.info(
                "[billing.task] past_due→suspended business=%s sub=%s grace_was=%s",
                row['business_id'], row['pk'], row['grace_until'],
            )
    return count


def _transition_trial_to_suspended(SubscriptionV2, now) -> int:
    """
    TRIALING → SUSPENDED when trial_ends_at < now.

    A trial that expired without converting to ACTIVE (no approved payment)
    is suspended.  The user must subscribe or contact support to reactivate.
    """
    trial_expired = list(
        SubscriptionV2.objects
        .filter(
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at__lt=now,
            trial_ends_at__isnull=False,
        )
        .values('pk', 'business_id', 'trial_ends_at')
    )

    count = 0
    for row in trial_expired:
        updated = SubscriptionV2.objects.filter(
            pk=row['pk'],
            status=SubscriptionV2.Status.TRIALING,
        ).update(status=SubscriptionV2.Status.SUSPENDED)
        if updated:
            count += 1
            logger.info(
                "[billing.task] trialing→suspended business=%s sub=%s trial_ended=%s",
                row['business_id'], row['pk'], row['trial_ends_at'],
            )
    return count


@shared_task(
    bind=True,
    name='billing.expire_checkout_sessions',
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def expire_checkout_sessions(self):
    """
    Mark MpCheckoutSession records whose expires_at has passed as EXPIRED.

    Runs every 15 minutes (configure via CELERY_BEAT_SCHEDULE).
    Idempotent: filter+update on status+expires_at ensures re-runs are safe.

    Returns:
        dict: {'expired': int}
    """
    from apps.billing.models import MpCheckoutSession  # local import avoids circular

    now = timezone.now()
    try:
        count = (
            MpCheckoutSession.objects
            .filter(
                status__in=MpCheckoutSession.OPEN_STATUSES,
                expires_at__lt=now,
            )
            .update(status=MpCheckoutSession.Status.EXPIRED)
        )
        logger.info("[billing.task] expire_checkout_sessions: %d sessions expired", count)
        return {'expired': count}
    except Exception as exc:
        logger.exception("[billing.task] expire_checkout_sessions failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='billing.execute_scheduled_cancellations',
    max_retries=3,
    default_retry_delay=120,
    acks_late=True,
)
def execute_scheduled_cancellations(self):
    """
    Execute subscription cancellations whose effective date (current_period_end)
    has passed.

    Finds all SubscriptionV2 where:
      - cancel_at_period_end = True
      - current_period_end <= now
      - status is NOT already CANCELED

    For each:
      1. Cancels the preapproval in MercadoPago.
      2. Updates the local subscription status to CANCELED.
      3. Handles errors without silently losing state.

    Idempotent: already-CANCELED subscriptions are skipped safely.

    Returns:
        dict: {'canceled': int, 'failed': int}
    """
    from apps.billing.models import SubscriptionV2   # local import avoids circular
    from apps.billing.cancellation_service import execute_cancellation
    from apps.billing.mp_service import MercadoPagoService

    now = timezone.now()
    counts = {'canceled': 0, 'failed': 0}

    due = list(
        SubscriptionV2.objects
        .filter(
            cancel_at_period_end=True,
            current_period_end__lte=now,
        )
        .exclude(status=SubscriptionV2.Status.CANCELED)
        .values_list('pk', flat=True)
    )

    if not due:
        logger.info("[billing.task] execute_scheduled_cancellations: nothing due.")
        return counts

    mp_service = MercadoPagoService()

    for sub_pk in due:
        try:
            sub = SubscriptionV2.objects.get(pk=sub_pk)

            # Double-check: skip if already canceled (race condition guard)
            if sub.status == SubscriptionV2.Status.CANCELED:
                continue

            execute_cancellation(sub, mp_service=mp_service)
            counts['canceled'] += 1

        except SubscriptionV2.DoesNotExist:
            logger.warning(
                "[billing.task] Subscription %s disappeared during cancellation run.", sub_pk,
            )
        except Exception as exc:
            counts['failed'] += 1
            logger.error(
                "[billing.task] Failed to execute cancellation for sub=%s: %s",
                sub_pk, exc,
            )

    logger.info(
        "[billing.task] execute_scheduled_cancellations complete: %s", counts,
    )

    # If there were failures, retry the entire task so they get another chance.
    if counts['failed'] > 0:
        try:
            raise self.retry(
                exc=Exception(f"{counts['failed']} cancellations failed"),
            )
        except self.MaxRetriesExceededError:
            logger.error(
                "[billing.task] Max retries exceeded for execute_scheduled_cancellations. "
                "Manual intervention needed for %d subs.", counts['failed'],
            )

    return counts


@shared_task(
    bind=True,
    name='billing.reconcile_promotional_discounts',
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
)
def reconcile_promotional_discounts(self):
    """
    Retry MercadoPago price restoration for promotional discounts where a
    previous attempt failed (``price_restored=False``).

    Also catches the edge case where a redemption reached ``cycles_used >=
    cycles_total`` while still ACTIVE (e.g. if ``handle_promo_cycle`` was not
    called due to an unexpected exception during webhook processing).

    Candidates
    ----------
    1. ``COMPLETED`` with ``price_restored=False`` — MP call failed during webhook.
    2. ``ACTIVE`` with ``cycles_used >= cycles_total`` — missed during webhook.

    Idempotent — redundant calls produce the same outcome.

    Returns:
        dict: {'restored': int, 'failed': int, 'skipped': int}
    """
    from django.db.models import F
    from apps.billing.models import PromoCodeRedemption  # local import avoids circular
    from apps.billing.mp_service import MercadoPagoService

    counts = {'restored': 0, 'failed': 0, 'skipped': 0}

    # Gather both candidate sets; deduplicate by pk.
    completed_unrestored = list(
        PromoCodeRedemption.objects
        .filter(status=PromoCodeRedemption.Status.COMPLETED, price_restored=False)
        .select_related('subscription')
    )
    active_exhausted = list(
        PromoCodeRedemption.objects
        .filter(status=PromoCodeRedemption.Status.ACTIVE)
        .filter(cycles_used__gte=F('cycles_total'))
        .select_related('subscription')
    )

    all_candidates: dict = {r.pk: r for r in completed_unrestored}
    for r in active_exhausted:
        all_candidates.setdefault(r.pk, r)

    if not all_candidates:
        logger.info("[billing.task] reconcile_promotional_discounts: nothing to do.")
        return counts

    logger.info(
        "[billing.task] reconcile_promotional_discounts: %d candidate(s).",
        len(all_candidates),
    )

    try:
        mp = MercadoPagoService()
    except Exception as exc:
        logger.error(
            "[billing.task] reconcile_promotional_discounts: cannot initialise MP client: %s",
            exc,
        )
        raise self.retry(exc=exc)

    for redemption in all_candidates.values():
        subscription = redemption.subscription
        if subscription is None or not getattr(subscription, 'provider_sub_id', None):
            logger.warning(
                "[billing.task] reconcile: redemption=%s has no linked subscription "
                "with provider_sub_id — skipping.",
                redemption.pk,
            )
            counts['skipped'] += 1
            continue

        try:
            mp.update_preapproval(
                subscription.provider_sub_id,
                {"auto_recurring": {"transaction_amount": float(redemption.original_amount)}},
            )
        except Exception as exc:
            logger.error(
                "[billing.task] reconcile: failed to restore price for "
                "redemption=%s subscription=%s: %s",
                redemption.pk, subscription.pk, exc,
            )
            counts['failed'] += 1
            continue

        # Persist success atomically.
        from django.db import transaction as _tx
        with _tx.atomic():
            updated = (
                PromoCodeRedemption.objects
                .filter(pk=redemption.pk)
                .exclude(price_restored=True)
                .update(
                    status=PromoCodeRedemption.Status.COMPLETED,
                    price_restored=True,
                    price_restored_at=timezone.now(),
                )
            )
        if updated:
            counts['restored'] += 1
            logger.info(
                "[billing.task] reconcile: price restored for redemption=%s subscription=%s.",
                redemption.pk, subscription.pk,
            )
        else:
            counts['skipped'] += 1  # already restored by concurrent run

    logger.info("[billing.task] reconcile_promotional_discounts complete: %s", counts)
    return counts
