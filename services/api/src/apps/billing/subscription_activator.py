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
    If the subscription was already active (renewal failure), transition to PAST_DUE.
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
    # else: still checkout_pending — just leave it as is.


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _activate_tenant(subscription: SubscriptionV2) -> None:
    """Set Business.status = 'active' atomically."""
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

    if tenant.status != 'active':
        old_status = tenant.status
        tenant.status = 'active'
        tenant.save(update_fields=['status'])
        logger.info(
            "[activator] Business %s status %s → active",
            tenant.pk, old_status,
        )
    else:
        logger.info(
            "[activator] Business %s already active — no status change.",
            tenant.pk,
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
