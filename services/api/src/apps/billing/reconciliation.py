"""
billing/reconciliation.py
==========================
Utilities for manual / operator-triggered reconciliation with MercadoPago.

These functions are SAFE and IDEMPOTENT — they query MP authoritatively and
recompose local state without triggering duplicate activations.

Intended use
------------
- Support staff investigating a "subscription created in MP but not in DB" case.
- Post-incident recovery after any outage that caused missed webhooks.
- Scheduled nightly reconciliation job (optional, see management command).

NOT a replacement for the real-time webhook flow.  Webhooks are always the
primary path; reconciliation is the safety net.

Available functions
-------------------
reconcile_checkout_session(session_id)
    Re-checks MP for the plan associated with a specific checkout session.
    Resolves the preapproval if found, links subscription, activates if warranted.

reconcile_subscription(provider_subscription_id)
    Fetches the preapproval from MP, re-links it to the correct checkout session
    and subscription, activates if payment evidence exists.

reconcile_by_preapproval_plan(provider_preapproval_plan_id)
    Finds a checkout session by plan ID, then reconciles everything attached to it.

reconcile_invoice_event(provider_authorized_payment_id)
    Fetches an authorized_payment from MP and upserts the BillingInvoiceEvent,
    then activates if applicable.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def reconcile_checkout_session(checkout_session_id: str) -> dict:
    """
    Re-fetch the MP plan associated with a checkout session and reconcile state.

    Returns a dict with keys:
        session_id, status, action_taken, error
    """
    from .models import MpCheckoutSession
    from .mp_service import MercadoPagoService

    result = {
        'session_id': checkout_session_id,
        'status': None,
        'action_taken': [],
        'error': None,
    }

    try:
        session = MpCheckoutSession.objects.get(id=checkout_session_id)
    except MpCheckoutSession.DoesNotExist:
        result['error'] = f"MpCheckoutSession {checkout_session_id} not found"
        logger.warning("[reconcile] %s", result['error'])
        return result

    result['status'] = session.status

    if not session.provider_preapproval_plan_id:
        result['error'] = "Session has no provider_preapproval_plan_id — cannot reconcile yet"
        logger.info("[reconcile] %s session=%s", result['error'], checkout_session_id)
        return result

    mp = MercadoPagoService()

    # Search for preapprovals associated with this plan.
    # MP does not provide a direct "list preapprovals by plan" endpoint in all SDK versions,
    # so we reconcile via the plan metadata.
    plan_data = mp.get_preapproval_plan(session.provider_preapproval_plan_id)
    if not plan_data:
        result['error'] = f"MP plan {session.provider_preapproval_plan_id} not found"
        return result

    result['action_taken'].append(f"Fetched MP plan {session.provider_preapproval_plan_id}")

    logger.info(
        "[reconcile] checkout_session=%s plan_id=%s plan_status=%s",
        checkout_session_id, session.provider_preapproval_plan_id, plan_data.get('status'),
    )

    # If a subscription exists for this session, reconcile it.
    for sub in session.subscriptions.all():  # type: ignore[attr-defined]
        sub_result = reconcile_subscription(sub.provider_sub_id)
        result['action_taken'].extend(sub_result.get('action_taken', []))

    return result


def reconcile_subscription(provider_subscription_id: str) -> dict:
    """
    Fetch a preapproval from MP and reconcile the local SubscriptionV2.

    Returns a dict with keys:
        provider_subscription_id, subscription_id, action_taken, error
    """
    from .models import BillingInvoiceEvent, MpCheckoutSession, SubscriptionV2
    from .mp_service import MercadoPagoService
    from .subscription_activator import activate_subscription_from_invoice

    result: dict = {
        'provider_subscription_id': provider_subscription_id,
        'subscription_id': None,
        'action_taken': [],
        'error': None,
    }

    if not provider_subscription_id:
        result['error'] = "Empty provider_subscription_id"
        return result

    mp = MercadoPagoService()
    preapproval = mp.get_preapproval(provider_subscription_id)
    if not preapproval:
        result['error'] = f"MP preapproval {provider_subscription_id} not found"
        logger.warning("[reconcile] %s", result['error'])
        return result

    plan_id = preapproval.get('preapproval_plan_id', '')

    # Find or create the SubscriptionV2.
    sub = SubscriptionV2.objects.filter(provider_sub_id=provider_subscription_id).first()
    if sub is None:
        # Try to locate the checkout session first.
        session = MpCheckoutSession.objects.filter(
            provider_preapproval_plan_id=plan_id
        ).first() if plan_id else None

        if session is None:
            result['error'] = (
                f"No MpCheckoutSession for plan_id={plan_id} — cannot create SubscriptionV2"
            )
            logger.warning("[reconcile] %s", result['error'])
            return result

        with transaction.atomic():
            sub, created = SubscriptionV2.objects.get_or_create(
                provider_sub_id=provider_subscription_id,
                defaults={
                    'business': session.tenant,
                    'service_type': session.tenant.default_service if session.tenant else 'gestion',
                    'plan_code': session.plan.code,
                    'provider': SubscriptionV2.Provider.MERCADOPAGO,
                    'external_reference': f"RECONCILE-{provider_subscription_id}",
                    'provider_preapproval_plan_id': plan_id,
                    'checkout_session': session,
                    'raw_snapshot_json': preapproval,
                    'status': SubscriptionV2.Status.CHECKOUT_PENDING,
                },
            )
            if created:
                result['action_taken'].append(f"Created SubscriptionV2 {sub.pk}")
    else:
        # Refresh snapshot.
        with transaction.atomic():
            changed: dict = {'raw_snapshot_json': preapproval}
            if not sub.checkout_session_id and plan_id:
                session = MpCheckoutSession.objects.filter(
                    provider_preapproval_plan_id=plan_id
                ).first()
                if session:
                    changed['checkout_session'] = session
            if not sub.provider_preapproval_plan_id and plan_id:
                changed['provider_preapproval_plan_id'] = plan_id
            for k, v in changed.items():
                setattr(sub, k, v)
            sub.save(update_fields=list(changed.keys()) + ['updated_at'])
            result['action_taken'].append(f"Updated SubscriptionV2 {sub.pk} fields={list(changed.keys())}")

    result['subscription_id'] = str(sub.pk)

    # Check for existing authorized invoice events — activate if found and not yet active.
    authorized_invoices = BillingInvoiceEvent.objects.filter(
        provider_subscription_id=provider_subscription_id,
        provider_status='authorized',
    ).order_by('paid_at', 'created_at')

    for invoice in authorized_invoices:
        if not sub.is_active:
            activated = activate_subscription_from_invoice(
                invoice_event=invoice,
                subscription=sub,
            )
            if activated:
                result['action_taken'].append(
                    f"Activated subscription via invoice {invoice.provider_authorized_payment_id}"
                )
                # Refresh local state.
                sub.refresh_from_db()

    return result


def reconcile_by_preapproval_plan(provider_preapproval_plan_id: str) -> dict:
    """
    Find the checkout session for a plan ID and reconcile all subscriptions.

    Returns a dict with keys:
        plan_id, session_id, action_taken, error
    """
    from .models import MpCheckoutSession

    result: dict = {
        'plan_id': provider_preapproval_plan_id,
        'session_id': None,
        'action_taken': [],
        'error': None,
    }

    session = MpCheckoutSession.objects.filter(
        provider_preapproval_plan_id=provider_preapproval_plan_id
    ).first()

    if session is None:
        result['error'] = f"No MpCheckoutSession for plan_id={provider_preapproval_plan_id}"
        logger.warning("[reconcile] %s", result['error'])
        return result

    result['session_id'] = str(session.id)
    sub_ids = list(session.subscriptions.values_list('provider_sub_id', flat=True))

    for sub_id in sub_ids:
        sub_result = reconcile_subscription(sub_id)
        result['action_taken'].extend(sub_result.get('action_taken', []))

    if not sub_ids:
        result['action_taken'].append(
            "No subscriptions found for session — may need to wait for webhook"
        )

    return result


def reconcile_invoice_event(provider_authorized_payment_id: str) -> dict:
    """
    Fetch an authorized_payment from MP and upsert the BillingInvoiceEvent.
    Activates the subscription if not yet active.

    Returns a dict with keys:
        provider_authorized_payment_id, invoice_event_id, action_taken, error
    """
    from .models import BillingInvoiceEvent, SubscriptionV2
    from .mp_service import MercadoPagoService
    from .subscription_activator import activate_subscription_from_invoice

    result: dict = {
        'provider_authorized_payment_id': provider_authorized_payment_id,
        'invoice_event_id': None,
        'action_taken': [],
        'error': None,
    }

    if not provider_authorized_payment_id:
        result['error'] = "Empty provider_authorized_payment_id"
        return result

    mp = MercadoPagoService()
    ap_data = mp.get_authorized_payment(provider_authorized_payment_id)
    if not ap_data:
        result['error'] = f"MP authorized_payment {provider_authorized_payment_id} not found"
        return result

    ap_status      = ap_data.get('status', '')
    preapproval_id = ap_data.get('preapproval_id', '')
    amount         = ap_data.get('transaction_amount') or 0
    currency       = ap_data.get('currency_id', 'ARS')
    payment_id     = str(ap_data.get('payment_id', '') or '')
    paid_at_str    = ap_data.get('date_approved') or ap_data.get('date_created')

    invoice_event, created = BillingInvoiceEvent.objects.get_or_create(
        provider_authorized_payment_id=provider_authorized_payment_id,
        defaults={
            'provider_payment_id': payment_id,
            'provider_subscription_id': preapproval_id,
            'amount': amount,
            'currency': currency,
            'provider_status': ap_status,
            'paid_at': _parse_dt(paid_at_str),
            'raw_payload_json': ap_data,
        },
    )
    result['invoice_event_id'] = str(invoice_event.id)
    result['action_taken'].append(
        ("Created" if created else "Found") + f" BillingInvoiceEvent {invoice_event.id}"
    )

    # Find subscription.
    sub = SubscriptionV2.objects.filter(provider_sub_id=preapproval_id).first() if preapproval_id else None
    if sub is None:
        result['error'] = f"No SubscriptionV2 for preapproval_id={preapproval_id}"
        logger.warning("[reconcile] %s", result['error'])
        return result

    if ap_status == 'authorized' and not sub.is_active:
        activated = activate_subscription_from_invoice(
            invoice_event=invoice_event,
            subscription=sub,
        )
        if activated:
            result['action_taken'].append(f"Activated subscription {sub.pk}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_dt(value):
    if not value:
        return None
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone as tz
    try:
        dt = parse_datetime(str(value))
        if dt and dt.tzinfo is None:
            dt = tz.make_aware(dt)
        return dt
    except Exception:
        return None
