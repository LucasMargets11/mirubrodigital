"""
billing/email_helpers.py
========================
Fire-and-forget email helpers for billing lifecycle events.

Design rules
------------
- All public functions return bool (True = enqueued, False = skipped/failed).
- Failures are always logged but NEVER propagated — billing state changes must
  not be rolled back because of an email failure.
- Never called inside a transaction.atomic() block.
- Owner resolution: checkout_session.user first, Membership fallback.
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.notifications.services import queue_transactional_email

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Owner resolution
# ─────────────────────────────────────────────────────────────────────────────

def get_owner_user(subscription):
    """
    Resolve the owner User for a SubscriptionV2.

    Resolution order
    ----------------
    1. subscription.checkout_session.user  — the user who initiated checkout;
       always an owner by construction.
    2. Membership(business=subscription.business, role='owner').user  — fallback
       for subscriptions created outside the checkout flow.

    Returns None if no owner with an email address is found.
    """
    # Path A: user from checkout session (preferred — no extra DB query).
    session = getattr(subscription, 'checkout_session', None)
    if session is not None:
        user = getattr(session, 'user', None)
        if user is not None and getattr(user, 'email', None):
            return user

    # Path B: Membership query fallback.
    try:
        from apps.accounts.models import Membership  # avoid circular import at module level

        membership = (
            Membership.objects
            .filter(business=subscription.business, role='owner')
            .select_related('user')
            .first()
        )
        if membership and membership.user and getattr(membership.user, 'email', None):
            return membership.user
    except Exception:
        logger.warning(
            "[billing.email] Failed to resolve owner Membership for business=%s",
            subscription.business_id,
        )

    logger.warning(
        "[billing.email] No owner with email found for subscription=%s business=%s",
        subscription.pk,
        subscription.business_id,
    )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PR-7 — subscription_activated
# ─────────────────────────────────────────────────────────────────────────────

def send_subscription_activated_email(subscription, invoice_event) -> bool:
    """
    Notify the business owner that their subscription is now active.

    Called after activate_subscription_from_invoice() returns True, outside
    any active transaction.atomic() block.

    Parameters
    ----------
    subscription  : SubscriptionV2 instance (already saved as ACTIVE).
    invoice_event : BillingInvoiceEvent instance that triggered activation.

    Returns True if the email was enqueued, False otherwise.
    """
    owner = get_owner_user(subscription)
    if owner is None:
        return False

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    dashboard_url = f"{frontend_url}/dashboard"

    plan_name = _resolve_plan_name(subscription)
    billing_period = _resolve_billing_period(subscription)
    next_billing_date = getattr(subscription, 'current_period_end', None)
    amount = getattr(invoice_event, 'amount', None)

    try:
        queue_transactional_email(
            to_email=owner.email,
            subject="¡Tu suscripción a MiRubro está activa!",
            template_key="subscription_activated",
            context={
                "user_name": owner.get_full_name() or owner.username,
                "business_name": subscription.business.name,
                "plan_name": plan_name,
                "billing_period": billing_period,
                "next_billing_date": next_billing_date,
                "amount": amount,
                "dashboard_url": dashboard_url,
            },
            user=owner,
            business=subscription.business,
            send_async=True,
        )
        logger.info(
            "[billing.email] subscription_activated email enqueued "
            "owner=%s subscription=%s business=%s",
            owner.pk,
            subscription.pk,
            subscription.business_id,
        )
        return True
    except Exception:
        logger.exception(
            "[billing.email] Failed to queue subscription_activated email "
            "for owner=%s subscription=%s",
            owner.pk,
            subscription.pk,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_plan_name(subscription) -> str:
    """
    Return a human-readable plan name.

    Tries (in order):
    1. subscription.checkout_session.plan.name
    2. Derive from subscription.plan_code (strip period suffix, capitalise)
    3. Map from subscription.service_type
    4. Generic fallback
    """
    session = getattr(subscription, 'checkout_session', None)
    if session is not None:
        plan = getattr(session, 'plan', None)
        if plan is not None:
            name = getattr(plan, 'name', None)
            if name:
                return name

    plan_code = getattr(subscription, 'plan_code', '') or ''
    if plan_code:
        base = plan_code.replace('_monthly', '').replace('_yearly', '')
        return ' '.join(part.capitalize() for part in base.split('_'))

    service_labels = {
        'gestion':        'Gestión Comercial',
        'restaurante':    'Restaurantes',
        'menu_qr':        'Menú QR',
        'menu_qr_visual': 'Menú QR Visual',
        'menu_qr_marca':  'Menú QR Marca',
        'qr_reviews':     'QR de Reseñas',
    }
    service_type = getattr(subscription, 'service_type', '') or ''
    return service_labels.get(service_type, 'Plan MiRubro')


def _resolve_billing_period(subscription) -> str:
    """Derive billing period label from plan_code."""
    plan_code = getattr(subscription, 'plan_code', '') or ''
    if plan_code.endswith('_yearly'):
        return 'anual'
    return 'mensual'
