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

def reconcile_session(session_id: str) -> dict:
    """
    Proactive, user-triggered reconciliation for a checkout session.

    Called when:
      - The user returns from MercadoPago via back_url (redirect).
      - The frontend polls and the session hasn't activated yet.
      - An operator triggers recovery for a stuck onboarding.

    Algorithm
    ---------
    1. Load MpCheckoutSession. If already activated/failed/expired → return.
    2. Transition session from checkout_created → awaiting_webhook (idempotent).
    3. Search MP for preapprovals linked to this session's preapproval_plan_id.
    4. For each found preapproval, upsert SubscriptionV2 (idempotent).
    5. If preapproval.status == 'authorized':
       a. Search MP for authorized_payments by preapproval_id.
       b. Upsert BillingInvoiceEvent for the first authorized payment.
       c. Call activate_subscription_from_invoice (idempotent).
    6. Return a summary dict with action_taken and current status.

    Safe to call multiple times — fully idempotent.
    """
    from .models import BillingInvoiceEvent, MpCheckoutSession, SubscriptionV2
    from .mp_service import MercadoPagoService
    from .subscription_activator import activate_subscription_from_invoice
    from .webhook_processor import _upsert_subscription_v2

    result: dict = {
        'session_id': session_id,
        'status': None,
        'action_taken': [],
        'error': None,
    }

    try:
        session = (
            MpCheckoutSession.objects
            .select_related('plan', 'tenant')
            .get(id=session_id)
        )
    except MpCheckoutSession.DoesNotExist:
        result['error'] = f"MpCheckoutSession {session_id} not found"
        logger.warning("[reconcile_session] %s", result['error'])
        return result

    result['status'] = session.status

    # ── Fast exits for terminal states ────────────────────────────────────────
    if session.status == MpCheckoutSession.Status.ACTIVATED:
        result['action_taken'].append('Session already activated — no-op')
        return result

    if session.status in MpCheckoutSession.TERMINAL_STATUSES:
        result['action_taken'].append(
            f'Session in terminal status {session.status} — cannot recover via reconciliation'
        )
        return result

    plan_id = session.provider_preapproval_plan_id
    if not plan_id:
        result['error'] = 'Session has no provider_preapproval_plan_id — cannot search MP'
        logger.warning("[reconcile_session] %s session=%s", result['error'], session_id)
        return result

    # The external_reference we sent to MP when creating the plan template.
    # This value is echoed back on every preapproval that belongs to this session.
    # We MUST use it to filter the list from MP so we never accidentally process
    # a preapproval that belongs to a different tenant who signed up for the same
    # plan template.
    expected_ext_ref = session.mp_external_reference  # e.g. "SESS-<uuid>"

    # ── Step 2: advance session state ─────────────────────────────────────────
    # Transition checkout_created → awaiting_webhook to signal that the user
    # has returned from MP.  Any other open status is left as-is.
    if session.status == MpCheckoutSession.Status.CHECKOUT_CREATED:
        try:
            session.transition_to(MpCheckoutSession.Status.AWAITING_WEBHOOK)
            result['action_taken'].append('Session transitioned checkout_created → awaiting_webhook')
            result['status'] = session.status
        except ValueError as exc:
            logger.warning('[reconcile_session] State transition skipped: %s', exc)

    # ── Step 3: search MP for preapprovals ───────────────────────────────────
    mp = MercadoPagoService()
    preapprovals = mp.search_preapprovals(plan_id)

    if not preapprovals:
        result['action_taken'].append(
            f'No preapprovals found in MP for plan_id={plan_id} — webhook not yet received'
        )
        logger.info(
            "[reconcile_session] No MP preapprovals for plan_id=%s session=%s",
            plan_id, session_id,
        )
        return result

    activated_any = False

    for preapproval in preapprovals:
        preapproval_id = preapproval.get('id', '')
        mp_status = preapproval.get('status', '')
        mp_ext_ref = preapproval.get('external_reference', '')

        if not preapproval_id:
            continue

        # ── external_reference ownership guard ───────────────────────────────
        # MP's search_preapprovals returns ALL subscribers to this plan template,
        # not just the one for this session.  Only process the preapproval that
        # matches our session's external_reference to avoid cross-tenant activation.
        if expected_ext_ref and mp_ext_ref != expected_ext_ref:
            logger.info(
                "[reconcile_session] Skipping preapproval=%s (ext_ref=%r ≠ expected=%r) session=%s",
                preapproval_id, mp_ext_ref, expected_ext_ref, session_id,
            )
            continue

        logger.info(
            "[reconcile_session] Found preapproval=%s status=%s session=%s",
            preapproval_id, mp_status, session_id,
        )
        result['action_taken'].append(f'Found preapproval {preapproval_id} status={mp_status}')

        # ── Step 4: upsert SubscriptionV2 (idempotent) ───────────────────────
        with transaction.atomic():
            sub_v2 = _upsert_subscription_v2(
                preapproval_id=preapproval_id,
                plan_id=plan_id,
                session=session,
                preapproval_data=preapproval,
            )
        result['action_taken'].append(f'Upserted SubscriptionV2 {sub_v2.pk}')

        # Transition session to LINKED now that we have a preapproval.
        if session.status not in MpCheckoutSession.TERMINAL_STATUSES:
            try:
                session.refresh_from_db(fields=['status'])
                session.transition_to(MpCheckoutSession.Status.LINKED)
                result['action_taken'].append('Session transitioned → linked')
                result['status'] = session.status
            except ValueError:
                pass  # Already linked or terminal — fine.

        if mp_status != 'authorized':
            result['action_taken'].append(
                f'Preapproval status={mp_status} — awaiting authorization, not activating yet'
            )
            continue

        # ── Step 5: search for authorized_payments ───────────────────────────
        auth_payments = mp.search_authorized_payments(preapproval_id)

        invoice_event = None

        for ap in auth_payments:
            ap_id = str(ap.get('id', ''))
            ap_status = ap.get('status', '')

            if ap_status != 'authorized' or not ap_id:
                continue

            amount = ap.get('transaction_amount') or ap.get('total_paid_amount') or 0
            currency = ap.get('currency_id', 'ARS')
            payment_id = str(ap.get('payment_id', '') or ap_id)
            paid_at_str = ap.get('date_approved') or ap.get('date_created')

            # ── Step 5b: upsert BillingInvoiceEvent (idempotent) ─────────────
            with transaction.atomic():
                invoice_event, created = BillingInvoiceEvent.objects.get_or_create(
                    provider_authorized_payment_id=ap_id,
                    defaults={
                        'provider_payment_id': payment_id,
                        'provider_subscription_id': preapproval_id,
                        'subscription': sub_v2,
                        'checkout_session': session,
                        'amount': amount,
                        'currency': currency,
                        'provider_status': ap_status,
                        'paid_at': _parse_dt(paid_at_str),
                        'raw_payload_json': ap,
                    },
                )
            result['action_taken'].append(
                ('Created' if created else 'Found') + f' BillingInvoiceEvent {invoice_event.id}'
            )
            break  # Use the first authorized payment found.

        if invoice_event is None:
            # Preapproval is authorized but no authorized_payment found yet.
            # This can happen in a very tight race window.
            result['action_taken'].append(
                f'Preapproval {preapproval_id} is authorized but no authorized_payment found yet'
            )
            logger.info(
                "[reconcile_session] Preapproval authorized but no auth_payment yet "
                "preapproval_id=%s session=%s",
                preapproval_id, session_id,
            )
            continue

        # ── Step 5c: activate (idempotent) ───────────────────────────────────
        if not sub_v2.is_active and sub_v2.can_activate():
            activated = activate_subscription_from_invoice(
                invoice_event=invoice_event,
                subscription=sub_v2,
            )
            if activated:
                result['action_taken'].append(f'Activated subscription {sub_v2.pk}')
                result['status'] = 'activated'
                activated_any = True

        elif sub_v2.is_active:
            result['action_taken'].append(f'Subscription {sub_v2.pk} already active — no-op')
            result['status'] = 'activated'
            activated_any = True

    if activated_any:
        result['status'] = 'activated'

    # ── Safety net: fix Business.status if subscription is active but business isn't ──
    # This catches the edge case where activation completed but the Business row
    # wasn't updated (e.g. a previous failed DB write after subscription commit).
    # Uses filter().update() — atomically skips if already active (no race condition).
    if result['status'] == 'activated' and session.tenant_id:
        try:
            from django.utils import timezone as tz
            from apps.business.models import Business
            rows = Business.objects.filter(
                pk=session.tenant_id, status='onboarding',
            ).update(status='active', activated_at=tz.now())
            if rows:
                result['action_taken'].append(
                    f'Fixed Business {session.tenant_id} status onboarding → active (safety net)'
                )
                logger.warning(
                    "[reconcile_session] Safety net applied: Business %s was in onboarding "
                    "despite active subscription — fixed to active.",
                    session.tenant_id,
                )
        except Exception as exc:
            logger.warning("[reconcile_session] Safety net check failed: %s", exc)

        # ── Service-specific companion artifacts (legacy sub, ReviewConfig…) ──
        # Idempotent — repairs state when the webhook activated V2 + Business
        # but the per-service hook had not yet run (e.g. older deployments).
        try:
            from .service_activation import ensure_service_activation
            from apps.business.models import Business

            tenant = Business.objects.filter(pk=session.tenant_id).first()
            active_v2 = None
            if tenant is not None:
                from .models import SubscriptionV2
                active_v2 = (
                    SubscriptionV2.objects
                    .filter(business=tenant, is_active=True)
                    .order_by('-updated_at')
                    .first()
                )
            if tenant is not None and active_v2 is not None:
                ensure_service_activation(
                    business=tenant,
                    owner=session.user,
                    plan_code=active_v2.plan_code or '',
                    service_type=(
                        active_v2.service_type
                        or getattr(tenant, 'default_service', '')
                        or ''
                    ),
                    subscription_v2=active_v2,
                    source='reconcile',
                    external_reference=active_v2.external_reference or '',
                    provider='mercadopago',
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[reconcile_session] service_activation hook failed session=%s: %s",
                session_id, exc,
            )

    return result


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
