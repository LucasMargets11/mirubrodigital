"""
billing/subscription_activator.py
====================================
Activates a tenant's subscription when the first valid payment is confirmed.

Activation policy
-----------------
Activation happens ONLY when:
  1. A BillingInvoiceEvent with provider_status='authorized' is received.
  2. This is confirmed via a server-to-server fetch from MP (done in webhook_processor).
  3. The linked SubscriptionV2 exists.

The tenant Business status and SubscriptionV2.is_active are set to 'active'
atomically only at this point — never on redirect, never on preapproval
webhook alone.

Idempotency & concurrency safety
---------------------------------
If a payment webhook arrives multiple times, or if the activator is called
twice for the same invoice event (including concurrent workers), the function
is safe:
  - It does an optimistic pre-flight check on the in-memory `is_active` flag.
  - Inside ``transaction.atomic()`` it re-fetches the row with
    ``select_for_update()`` before any write so concurrent callers are
    serialised at the DB level.  The second caller re-reads ``is_active=True``
    after the lock is acquired and exits without writing.

Evidence
--------
After activation, the following evidence chain exists in the DB:
  BillingInvoiceEvent.provider_authorized_payment_id
    → BillingInvoiceEvent.subscription → SubscriptionV2
    → SubscriptionV2.checkout_session   → MpCheckoutSession
    → MpCheckoutSession.plan            → Plan (catalog plan)
    → MpCheckoutSession.tenant          → Business
    → Business.status == 'active'
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from .models import BillingInvoiceEvent, MpCheckoutSession, SubscriptionV2

logger = logging.getLogger(__name__)


def activate_subscription_from_invoice(
    *,
    invoice_event: BillingInvoiceEvent,
    subscription: SubscriptionV2,
) -> bool:
    """
    Activate the subscription and tenant if the invoice event is the first
    authorized payment.

    Returns True if activation was performed, False if already active (idempotent).

    Structured log fields:
      checkout_session_id, provider_preapproval_plan_id, provider_subscription_id,
      provider_authorized_payment_id, previous_status, new_status.
    """
    if subscription.is_active:
        logger.info(
            "[activator] Subscription already active — no-op. "
            "checkout_session_id=%s provider_subscription_id=%s "
            "provider_authorized_payment_id=%s",
            subscription.checkout_session_id,
            subscription.provider_sub_id,
            invoice_event.provider_authorized_payment_id,
        )
        return False

    # Guard: never reactivate a subscription that has been explicitly canceled.
    # A canceled subscription is terminal; reactivation must go through a new
    # checkout session and an explicit operator or user action.
    if not subscription.can_activate():
        logger.warning(
            "[activator] Subscription %s is in terminal status=%s — "
            "refusing activation for invoice_event=%s. "
            "Manual operator action required to reactivate a canceled subscription.",
            subscription.pk, subscription.status, invoice_event.pk,
        )
        return False

    logger.info(
        "[activator] Activating subscription. "
        "checkout_session_id=%s provider_preapproval_plan_id=%s "
        "provider_subscription_id=%s provider_authorized_payment_id=%s "
        "amount=%s currency=%s",
        subscription.checkout_session_id,
        subscription.provider_preapproval_plan_id,
        subscription.provider_sub_id,
        invoice_event.provider_authorized_payment_id,
        invoice_event.amount,
        invoice_event.currency,
    )

    with transaction.atomic():
        # Re-fetch with an exclusive row lock so concurrent webhook deliveries
        # for the same subscription are serialised here.  The pre-flight
        # checks above are an optimistic fast-path; this is the authoritative
        # gate: the second concurrent worker blocks until the first commits,
        # then re-reads is_active=True and exits without double-activating.
        subscription = (
            SubscriptionV2.objects
            .select_for_update()
            .get(pk=subscription.pk)
        )

        # Re-check after acquiring the lock.
        if subscription.is_active:
            logger.info(
                "[activator] Subscription already active (locked re-check) — no-op. "
                "checkout_session_id=%s provider_subscription_id=%s "
                "provider_authorized_payment_id=%s",
                subscription.checkout_session_id,
                subscription.provider_sub_id,
                invoice_event.provider_authorized_payment_id,
            )
            return False

        if not subscription.can_activate():
            logger.warning(
                "[activator] Subscription %s terminal status=%s (locked re-check) — "
                "refusing activation for invoice_event=%s.",
                subscription.pk, subscription.status, invoice_event.pk,
            )
            return False

        prev_sub_status = subscription.status
        prev_is_active  = subscription.is_active

        # ── 1. Activate SubscriptionV2 ────────────────────────────────────────
        subscription.status    = SubscriptionV2.Status.ACTIVE
        subscription.is_active = True
        subscription.current_period_start = invoice_event.paid_at or timezone.now()
        subscription.save(update_fields=[
            'status', 'is_active', 'current_period_start', 'updated_at',
        ])

        # ── 2. Activate the tenant Business ──────────────────────────────────
        _activate_tenant(subscription)

        # ── 3. Move checkout session to activated ─────────────────────────────
        _activate_checkout_session(subscription)

        # ── 4. Ensure a Membership exists for the originating user ────────────
        _ensure_owner_membership(subscription)

    logger.info(
        "[activator] Activation complete. "
        "prev_sub_status=%s new_sub_status=%s prev_is_active=%s "
        "checkout_session_id=%s provider_subscription_id=%s "
        "provider_authorized_payment_id=%s",
        prev_sub_status,
        SubscriptionV2.Status.ACTIVE,
        prev_is_active,
        subscription.checkout_session_id,
        subscription.provider_sub_id,
        invoice_event.provider_authorized_payment_id,
    )
    return True


def record_failed_payment(
    *,
    invoice_event: BillingInvoiceEvent,
    subscription: SubscriptionV2,
    reason: str = '',
) -> None:
    """
    Handle a payment failure: update subscription status but do NOT activate.
    If the subscription was already active (renewal failure), transition to PAST_DUE
    and mirror the state on Business.status.
    """
    logger.info(
        "[activator] Payment failure recorded. "
        "checkout_session_id=%s provider_subscription_id=%s "
        "provider_authorized_payment_id=%s status=%s reason=%r",
        subscription.checkout_session_id,
        subscription.provider_sub_id,
        invoice_event.provider_authorized_payment_id,
        invoice_event.provider_status,
        reason,
    )

    if subscription.status == SubscriptionV2.Status.ACTIVE:
        # Renewal failure — downgrade to past_due.
        subscription.status     = SubscriptionV2.Status.PAST_DUE
        subscription.retry_count = (subscription.retry_count or 0) + 1
        subscription.save(update_fields=['status', 'retry_count', 'updated_at'])

        # Mirror on Business so frontend routing stays consistent.
        _set_tenant_past_due(subscription)

        # Notify the business owner — fire-and-forget, outside any transaction.
        from .email_helpers import send_payment_failed_email
        try:
            send_payment_failed_email(
                subscription,
                reason=reason or None,
                amount=getattr(invoice_event, 'amount', None),
            )
        except Exception as exc:
            logger.exception(
                "[activator] send_payment_failed_email failed — "
                "subscription=%s invoice_event=%s: %s. "
                "Payment failure is recorded; email failure does not revert it.",
                subscription.pk, invoice_event.pk, exc,
            )

        # Notify ADMIN billing team — internal email, fire-and-forget.
        from .email_helpers import send_admin_payment_failure_recurrent_email
        try:
            send_admin_payment_failure_recurrent_email(
                subscription,
                invoice_event=invoice_event,
                reason=reason,
            )
        except Exception as exc:
            logger.exception(
                "[activator] send_admin_payment_failure_recurrent_email failed — "
                "subscription=%s invoice_event=%s: %s. "
                "Payment failure is recorded; email failure does not revert it.",
                subscription.pk, invoice_event.pk, exc,
            )

        # Admin in-app notification — fire-and-forget.
        try:
            from apps.accounts.admin_notification_service import create_admin_notification
            create_admin_notification(
                notif_type='billing_payment_failure',
                severity='critical',
                target_role='operations',
                title='Pago fallido recurrente',
                message=f'{subscription.business.name} pasó a PAST_DUE por fallo de pago.',
                business=subscription.business,
                related_object_type='subscription',
                related_object_id=str(subscription.id),
                action_url=f'/admin/suscripciones/{subscription.id}',
                metadata={
                    'plan_code': subscription.plan_code,
                    'service_type': subscription.service_type,
                    'retry_count': subscription.retry_count,
                },
                dedupe_window_seconds=3600,
            )
        except Exception as exc:
            logger.exception(
                '[activator] create_admin_notification billing_payment_failure failed '
                'for sub=%s — payment failure remains recorded.',
                subscription.pk,
            )
    # else: still checkout_pending or trialing — leave as is.


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _activate_tenant(subscription: SubscriptionV2) -> None:
    """
    Set Business.status based on the SubscriptionV2 status being activated.

    Mapping (Wave 3):
      SubscriptionV2.ACTIVE   → Business.status = 'active'
      SubscriptionV2.TRIALING → Business.status = 'trialing'

    Only transitions away from 'onboarding', 'trialing', or 'past_due'; already-
    active businesses are left untouched to preserve idempotency.
    """
    tenant = subscription.tenant if hasattr(subscription, 'tenant') else \
             getattr(subscription, 'business', None)

    if tenant is None:
        # Try loading via checkout_session.
        session = subscription.checkout_session
        if session:
            tenant = session.tenant

    if tenant is None:
        logger.warning(
            "[activator] No tenant found for subscription=%s — cannot activate Business.",
            subscription.pk,
        )
        return

    # Map SubscriptionV2 status → Business status
    sub_status = subscription.status
    if sub_status == SubscriptionV2.Status.TRIALING:
        target_status = 'trialing'
    else:
        target_status = 'active'

    if tenant.status != target_status:
        old_status = tenant.status
        tenant.status = target_status
        if target_status == 'active':
            tenant.activated_at = timezone.now()
            tenant.save(update_fields=['status', 'activated_at'])
        else:
            tenant.save(update_fields=['status'])
        logger.info(
            "[activator] Business %s status %s → %s",
            tenant.pk, old_status, target_status,
        )

        # Wave 5: record onboarding completion in the audit log so we have a
        # reliable, queryable signal for when a business leaves the onboarding
        # funnel for the first time.
        if old_status == 'onboarding':
            _log_onboarding_completed(tenant, subscription)
    else:
        logger.info(
            "[activator] Business %s already %s — no status change.",
            tenant.pk, target_status,
        )


def _activate_checkout_session(subscription: SubscriptionV2) -> None:
    """Move MpCheckoutSession to 'activated' via the state machine."""
    session = subscription.checkout_session
    if session is None:
        return
    try:
        transitioned = session.transition_to(MpCheckoutSession.Status.ACTIVATED)
        if transitioned:
            logger.info(
                "[activator] MpCheckoutSession %s → activated",
                session.id,
            )
        else:
            logger.info(
                "[activator] MpCheckoutSession %s already in target status — no-op",
                session.id,
            )
    except ValueError as exc:
        # Session is already terminal (e.g. expired then somehow paid).
        # Log as info — the subscription itself was correctly activated; the
        # session status is just a UX indicator and should not block the flow.
        logger.info(
            "[activator] MpCheckoutSession %s transition to activated blocked (already terminal): %s",
            session.id, exc,
        )


def _ensure_owner_membership(subscription: SubscriptionV2) -> None:
    """
    Ensure the user who initiated the checkout session has an owner Membership
    for the tenant Business.
    """
    from apps.accounts.models import Membership

    session = subscription.checkout_session
    if session is None:
        return

    tenant = session.tenant
    user   = session.user

    if tenant is None or user is None:
        return

    membership, created = Membership.objects.get_or_create(
        user=user,
        business=tenant,
        defaults={'role': 'owner'},
    )
    if created:
        logger.info(
            "[activator] Created owner Membership user=%s business=%s",
            user.pk, tenant.pk,
        )


def _set_tenant_past_due(subscription: SubscriptionV2) -> None:
    """
    Mirror SubscriptionV2.PAST_DUE on Business.status.

    Called by record_failed_payment() when an active subscription's renewal
    fails.  Sets Business.status = 'past_due' so the frontend can keep the
    business accessible (grace period is still active) while surfacing a
    renewal banner.

    No-op if the business is already 'past_due' or not found.
    """
    tenant = getattr(subscription, 'business', None)
    if tenant is None:
        session = subscription.checkout_session
        if session:
            tenant = session.tenant
    if tenant is None:
        logger.warning(
            "[activator] No tenant found for subscription=%s — cannot set past_due.",
            subscription.pk,
        )
        return

    if tenant.status not in ('active', 'trialing'):
        # Only transition from operational states.  If already past_due or
        # suspended, don't overwrite.
        logger.info(
            "[activator] Business %s status=%s — skipping past_due transition.",
            tenant.pk, tenant.status,
        )
        return

    old_status = tenant.status
    tenant.status = 'past_due'
    tenant.save(update_fields=['status'])
    logger.info(
        "[activator] Business %s status %s → past_due (renewal failure)",
        tenant.pk, old_status,
    )


def _log_onboarding_completed(tenant, subscription: SubscriptionV2) -> None:
    """
    Write an ONBOARDING_COMPLETED AccessAuditLog entry when a business
    transitions out of 'onboarding' status for the first time.

    This gives us a queryable, time-stamped signal for pilot analytics and
    debugging without any behavioral side-effects.  The write is fire-and-
    forget: failures are logged but never raise so the activation path is
    never disrupted.
    """
    try:
        from apps.accounts.models import AccessAuditLog

        user = None
        session = subscription.checkout_session
        if session:
            user = session.user

        AccessAuditLog.objects.create(
            action='ONBOARDING_COMPLETED',
            actor=user,
            target_user=user,
            business=tenant,
            actor_type='SYSTEM',
            entity_type='Business',
            entity_id=str(tenant.pk),
            after_json={
                'new_status': tenant.status,
                'subscription_id': str(subscription.pk),
                'plan_code': subscription.plan_code or '',
            },
        )
        logger.info(
            "[activator] ONBOARDING_COMPLETED logged for business=%s user=%s",
            tenant.pk, user.pk if user else None,
        )
    except Exception as exc:
        logger.warning(
            "[activator] Failed to log ONBOARDING_COMPLETED for business=%s: %s",
            tenant.pk, exc,
        )
