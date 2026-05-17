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

# ─────────────────────────────────────────────────────────────────────────────
# PR-8 — payment_failed
# ─────────────────────────────────────────────────────────────────────────────

def send_payment_failed_email(subscription, *, reason: str | None = None,
                              amount=None) -> bool:
    """
    Notify the business owner that a payment failed and their subscription
    has entered PAST_DUE status.

    Parameters
    ----------
    subscription : SubscriptionV2 instance (already saved as PAST_DUE).
    reason       : Optional human-readable failure reason from the provider.
    amount       : Optional Decimal/str amount that was attempted.

    Returns True if the email was enqueued, False otherwise.
    """
    owner = get_owner_user(subscription)
    if owner is None:
        return False

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    billing_url = f"{frontend_url}/billing"

    plan_name = _resolve_plan_name(subscription)

    try:
        queue_transactional_email(
            to_email=owner.email,
            subject="Hubo un problema con el pago de tu suscripción",
            template_key="payment_failed",
            context={
                "user_name": owner.get_full_name() or owner.username,
                "business_name": subscription.business.name,
                "plan_name": plan_name,
                "failure_reason": reason or "",
                "amount": amount,
                "billing_url": billing_url,
            },
            user=owner,
            business=subscription.business,
            send_async=True,
        )
        logger.info(
            "[billing.email] payment_failed email enqueued "
            "owner=%s subscription=%s business=%s",
            owner.pk,
            subscription.pk,
            subscription.business_id,
        )
        return True
    except Exception:
        logger.exception(
            "[billing.email] Failed to queue payment_failed email "
            "for owner=%s subscription=%s",
            owner.pk,
            subscription.pk,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PR-9 — subscription_suspended
# ─────────────────────────────────────────────────────────────────────────────

def send_subscription_suspended_email(subscription, *, reason: str | None = None) -> bool:
    """
    Notify the business owner that their subscription has been suspended.

    Called after a subscription transitions to SUSPENDED status (either from
    PAST_DUE when grace_until expired, or from TRIALING when trial_ends_at
    expired).  Runs outside any active transaction.atomic() block.

    Parameters
    ----------
    subscription : SubscriptionV2 instance (already saved as SUSPENDED).
    reason       : Optional human-readable reason (not currently shown but
                   kept for future use and logging).

    Returns True if the email was enqueued, False otherwise.
    """
    owner = get_owner_user(subscription)
    if owner is None:
        return False

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    reactivation_url = f"{frontend_url}/billing"

    plan_name = _resolve_plan_name(subscription)
    grace_expired_at = getattr(subscription, 'grace_until', None)

    try:
        queue_transactional_email(
            to_email=owner.email,
            subject="Tu acceso a MiRubro fue suspendido",
            template_key="subscription_suspended",
            context={
                "user_name": owner.get_full_name() or owner.username,
                "business_name": subscription.business.name,
                "plan_name": plan_name,
                "grace_expired_at": grace_expired_at,
                "reactivation_url": reactivation_url,
                "support_email": getattr(settings, 'SUPPORT_EMAIL', 'soporte@mirubro.com'),
            },
            user=owner,
            business=subscription.business,
            send_async=True,
        )
        logger.info(
            "[billing.email] subscription_suspended email enqueued "
            "owner=%s subscription=%s business=%s reason=%s",
            owner.pk,
            subscription.pk,
            subscription.business_id,
            reason,
        )
        return True
    except Exception:
        logger.exception(
            "[billing.email] Failed to queue subscription_suspended email "
            "for owner=%s subscription=%s",
            owner.pk,
            subscription.pk,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PR-10 — cancellation_confirmed
# ─────────────────────────────────────────────────────────────────────────────

def send_cancellation_confirmed_email(subscription) -> bool:
    """
    Notify the business owner that their subscription has been canceled.

    Called at the end of execute_cancellation() only when the cancellation
    actually changed the subscription to CANCELED status.  Runs outside any
    active transaction.atomic() block.

    Parameters
    ----------
    subscription : SubscriptionV2 instance (already saved as CANCELED).

    Returns True if the email was enqueued, False otherwise.
    """
    owner = get_owner_user(subscription)
    if owner is None:
        return False

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    resubscribe_url = f"{frontend_url}/billing"

    plan_name = _resolve_plan_name(subscription)
    canceled_at = getattr(subscription, 'canceled_at', None)
    # access_until: subscriptions canceled at period end may still have access.
    access_until = getattr(subscription, 'current_period_end', None)

    try:
        queue_transactional_email(
            to_email=owner.email,
            subject="Tu suscripción a MiRubro fue cancelada",
            template_key="cancellation_confirmed",
            context={
                "user_name": owner.get_full_name() or owner.username,
                "business_name": subscription.business.name,
                "plan_name": plan_name,
                "canceled_at": canceled_at,
                "access_until": access_until,
                "resubscribe_url": resubscribe_url,
                "support_email": getattr(settings, 'SUPPORT_EMAIL', 'soporte@mirubro.com'),
            },
            user=owner,
            business=subscription.business,
            send_async=True,
        )
        logger.info(
            "[billing.email] cancellation_confirmed email enqueued "
            "owner=%s subscription=%s business=%s",
            owner.pk,
            subscription.pk,
            subscription.business_id,
        )
        return True
    except Exception:
        logger.exception(
            "[billing.email] Failed to queue cancellation_confirmed email "
            "for owner=%s subscription=%s",
            owner.pk,
            subscription.pk,
        )
        return False


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


def _build_admin_subscription_url(subscription_id: str) -> str:
    """Build the admin panel URL for a subscription detail."""
    base = getattr(settings, 'ADMIN_FRONTEND_URL', '').rstrip('/')
    return f"{base}/suscripciones/{subscription_id}"


# ─────────────────────────────────────────────────────────────────────────────
# PR-ADMIN-03 — admin_subscription_payment_created (internal ADMIN email)
# ─────────────────────────────────────────────────────────────────────────────

def send_admin_subscription_payment_created_email(subscription, invoice_event) -> bool:
    """
    Send an internal ADMIN email notifying the billing team that a customer
    completed a payment and their subscription is now active.

    This is a separate internal notification from the client-facing
    send_subscription_activated_email().  It uses the admin_helpers layer
    (queue_admin_transactional_email) and is addressed to recipient_category="billing".

    Parameters
    ----------
    subscription  : SubscriptionV2 instance (already ACTIVE).
    invoice_event : BillingInvoiceEvent instance that triggered activation.

    Returns True if the email was enqueued, False otherwise.
    Failures are logged but never propagated — the webhook must not be affected.
    """
    from apps.notifications.admin_helpers import queue_admin_transactional_email

    owner = get_owner_user(subscription)
    owner_email = owner.email if owner is not None else None

    paid_at = getattr(invoice_event, 'paid_at', None)
    paid_at_str = paid_at.strftime("%d/%m/%Y %H:%M") if paid_at else ""
    amount = getattr(invoice_event, 'amount', None)
    currency = getattr(invoice_event, 'currency', 'ARS')
    admin_url = _build_admin_subscription_url(str(subscription.pk))

    try:
        result = queue_admin_transactional_email(
            recipient_category="billing",
            subject="Nuevo cliente suscripto en MiRubro",
            template_key="admin_subscription_payment_created",
            context={
                "business_name": subscription.business.name,
                "business_id": str(subscription.business_id),
                "owner_email": owner_email or "",
                "plan_code": subscription.plan_code,
                "service_type": subscription.service_type,
                "amount": str(amount) if amount is not None else "",
                "currency": currency,
                "paid_at": paid_at_str,
                "invoice_event_id": str(invoice_event.pk),
                "admin_url": admin_url,
            },
            related_business=subscription.business,
            related_user=owner,
            metadata={
                "event_type": "admin_subscription_payment_created",
                "subscription_id": str(subscription.pk),
                "invoice_event_id": str(invoice_event.pk),
                "related_business_id": str(subscription.business_id),
                "service_type": subscription.service_type,
                "plan_code": subscription.plan_code,
                "amount": str(amount) if amount is not None else "",
                "currency": currency,
            },
        )
        logger.info(
            "[billing.email] admin_subscription_payment_created email enqueued=%s "
            "subscription=%s business=%s",
            result,
            subscription.pk,
            subscription.business_id,
        )
        return result
    except Exception:
        logger.exception(
            "[billing.email] Failed to queue admin_subscription_payment_created email "
            "for subscription=%s business=%s",
            subscription.pk,
            subscription.business_id,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PR-ADMIN-04 — admin_cancellation_request_received (internal ADMIN email)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# PR-ADMIN-08 — admin_payment_failure_recurrent (internal ADMIN email)
# ─────────────────────────────────────────────────────────────────────────────

def send_admin_payment_failure_recurrent_email(
    subscription,
    invoice_event=None,
    *,
    reason: str | None = None,
) -> bool:
    """
    Send an internal ADMIN email notifying the billing team that an active
    subscription has transitioned to PAST_DUE due to a payment failure or
    expiry of the billing period without a confirmed payment.

    Can be called from:
      - record_failed_payment()       in subscription_activator.py (invoice_event present)
      - _transition_active_to_past_due() in tasks.py               (invoice_event=None)

    Parameters
    ----------
    subscription  : SubscriptionV2 instance (already saved as PAST_DUE).
    invoice_event : BillingInvoiceEvent or None (not available in time-based path).
    reason        : Optional human-readable failure reason.

    Returns True if the email was enqueued, False otherwise.
    Failures are logged but never propagated — the billing state change must
    not be reverted by an email failure.
    """
    from apps.notifications.admin_helpers import queue_admin_transactional_email

    owner = get_owner_user(subscription)
    owner_email = owner.email if owner is not None else None

    retry_count = getattr(subscription, 'retry_count', 0) or 0
    # In the time-based task path, retry_count may still be 0 since it is only
    # incremented by record_failed_payment().  Show at least 1 so the email
    # does not read "Intento #0".
    display_retry_count = max(retry_count, 1)

    if retry_count >= 3:
        urgency = "crítico"
    elif retry_count == 2:
        urgency = "atención"
    else:
        urgency = "aviso"

    amount = getattr(invoice_event, 'amount', None) if invoice_event is not None else None
    currency = (getattr(invoice_event, 'currency', None) or 'ARS') if invoice_event is not None else 'ARS'
    provider_status = (getattr(invoice_event, 'provider_status', '') or '') if invoice_event is not None else ''
    invoice_event_id = str(invoice_event.pk) if invoice_event is not None else ''

    grace_until = getattr(subscription, 'grace_until', None)
    grace_until_str = grace_until.strftime("%d/%m/%Y %H:%M") if grace_until else ''

    current_period_end = getattr(subscription, 'current_period_end', None)
    current_period_end_str = current_period_end.strftime("%d/%m/%Y %H:%M") if current_period_end else ''

    admin_url = _build_admin_subscription_url(str(subscription.pk))

    try:
        result = queue_admin_transactional_email(
            recipient_category="billing",
            subject="Pago fallido en MiRubro — requiere revisión",
            template_key="admin_payment_failure_recurrent",
            context={
                "business_name": subscription.business.name,
                "business_id": str(subscription.business_id),
                "owner_email": owner_email or "",
                "plan_code": subscription.plan_code or "",
                "service_type": subscription.service_type or "",
                "retry_count": display_retry_count,
                "urgency": urgency,
                "amount": str(amount) if amount is not None else "",
                "currency": currency,
                "failure_reason": reason or "",
                "provider_status": provider_status,
                "grace_until": grace_until_str,
                "current_period_end": current_period_end_str,
                "invoice_event_id": invoice_event_id,
                "admin_url": admin_url,
            },
            related_business=subscription.business,
            related_user=owner,
            metadata={
                "event_type": "admin_payment_failure_recurrent",
                "subscription_id": str(subscription.pk),
                "related_business_id": str(subscription.business_id),
                "plan_code": subscription.plan_code or "",
                "service_type": subscription.service_type or "",
                "retry_count": display_retry_count,
                "amount": str(amount) if amount is not None else "",
                "currency": currency,
                "provider_status": provider_status,
                "invoice_event_id": invoice_event_id,
            },
        )
        logger.info(
            "[billing.email] admin_payment_failure_recurrent email enqueued=%s "
            "subscription=%s business=%s retry_count=%s",
            result,
            subscription.pk,
            subscription.business_id,
            display_retry_count,
        )
        return result
    except Exception:
        logger.exception(
            "[billing.email] Failed to queue admin_payment_failure_recurrent email "
            "for subscription=%s business=%s",
            subscription.pk,
            subscription.business_id,
        )
        return False


def send_admin_cancellation_request_received_email(subscription) -> bool:
    """
    Send an internal ADMIN email notifying the operations team that a customer
    has requested the cancellation of their subscription.

    Called after schedule_cancellation() succeeds (cancel_at_period_end=True,
    cancel_requested_at set, subscription saved).  Must NOT be called from
    execute_cancellation() or undo_cancellation().

    Returns True if enqueued, False otherwise.
    Failures are logged but never propagated — the cancellation flow must
    not be affected by an email failure.
    """
    from apps.notifications.admin_helpers import queue_admin_transactional_email

    owner = get_owner_user(subscription)
    owner_email = owner.email if owner is not None else None
    admin_url = _build_admin_subscription_url(str(subscription.pk))

    cancel_requested_at = getattr(subscription, 'cancel_requested_at', None)
    cancel_requested_at_str = (
        cancel_requested_at.strftime("%d/%m/%Y %H:%M") if cancel_requested_at else ""
    )
    effective_date = getattr(subscription, 'current_period_end', None)
    effective_date_str = (
        effective_date.strftime("%d/%m/%Y %H:%M") if effective_date else ""
    )
    cancel_reason = getattr(subscription, 'cancel_reason', None) or ""

    try:
        result = queue_admin_transactional_email(
            recipient_category="operations",
            subject="Solicitud de baja recibida en MiRubro",
            template_key="admin_cancellation_request_received",
            context={
                "business_name": subscription.business.name,
                "business_id": str(subscription.business_id),
                "owner_email": owner_email or "",
                "plan_code": subscription.plan_code,
                "service_type": subscription.service_type,
                "cancel_requested_at": cancel_requested_at_str,
                "effective_date": effective_date_str,
                "cancel_reason": cancel_reason,
                "admin_url": admin_url,
            },
            related_business=subscription.business,
            related_user=owner,
            metadata={
                "event_type": "admin_cancellation_request_received",
                "subscription_id": str(subscription.pk),
                "related_business_id": str(subscription.business_id),
                "service_type": subscription.service_type,
                "plan_code": subscription.plan_code,
            },
        )
        logger.info(
            "[billing.email] admin_cancellation_request_received email enqueued=%s "
            "subscription=%s business=%s",
            result,
            subscription.pk,
            subscription.business_id,
        )
        return result
    except Exception:
        logger.exception(
            "[billing.email] Failed to queue admin_cancellation_request_received email "
            "for subscription=%s business=%s",
            subscription.pk,
            subscription.business_id,
        )
        return False
