"""
billing/webhook_processor.py
==============================
Robust, auditable, idempotent MercadoPago webhook handler.

Responsibilities
----------------
1. Persist every inbound webhook as a WebhookDelivery BEFORE any business logic.
2. Verify the MP signature (HMAC-SHA256). Always.
3. Detect duplicates — respond 200 immediately without re-processing.
4. Dispatch to topic-specific handlers.
5. NEVER trust the webhook body for activation; always fetch authoritative data
   from MP server-to-server.

Supported topics
----------------
- subscription_preapproval      : a user subscribed to one of our plans
- subscription_authorized_payment : a recurring charge was processed

Deduplication strategy
----------------------
A webhook delivery is considered a duplicate if another WebhookDelivery with
the same (topic + resource_id + x_request_id + payload_hash) already exists
in status processed/duplicated.

Primary key for idempotency: x_request_id (present in most MP webhooks).
Secondary key: payload_hash (SHA-256 of raw body bytes).

Correlation chain (end-to-end)
-------------------------------
1. checkout_session_service creates an MP plan →
       stores `provider_preapproval_plan_id` on MpCheckoutSession.
2. User completes checkout → MP sends `subscription_preapproval` webhook with
       data.id = preapproval_id (user subscription).
3. We fetch preapproval from MP → get `preapproval_plan_id` from response.
4. We find MpCheckoutSession by `provider_preapproval_plan_id`.
       → This is the PRIMARY correlation key. No email heuristics.
5. We upsert SubscriptionV2 with provider_sub_id = preapproval_id.
6. MP later sends `subscription_authorized_payment` webhook →
       data.id = authorized_payment_id.
7. We fetch authorized_payment from MP → get `preapproval_id` from response.
8. We find SubscriptionV2 by `provider_sub_id`.
9. We upsert BillingInvoiceEvent.
10. If first valid payment → activate_subscription().
"""
from __future__ import annotations

import hashlib
import hmac as hmac_lib
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    SubscriptionV2,
    WebhookDelivery,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point called from MercadoPagoWebhookView
# ─────────────────────────────────────────────────────────────────────────────

def receive_webhook(request) -> tuple[WebhookDelivery, bool]:
    """
    Persist the webhook delivery, verify signature, detect duplicate.

    Returns:
        (delivery, signature_valid)

    The caller should check ``delivery.processing_status`` after this call:
      - RECEIVED   → proceed to dispatch
      - DUPLICATED → respond 200 and stop
      - IGNORED    → respond 200 and stop (signature invalid)
    """
    now = timezone.now()
    body_bytes: bytes = request.body
    payload_hash = hashlib.sha256(body_bytes).hexdigest()

    x_request_id = request.headers.get('x-request-id', '')
    x_signature   = request.headers.get('x-signature', '')
    topic         = request.data.get('type', '')
    resource_id   = str(request.data.get('data', {}).get('id', ''))
    action        = request.data.get('action', '')

    sig_valid = _verify_mp_signature(request, x_request_id, x_signature)

    headers_snapshot = {
        'x-request-id': x_request_id,
        'x-signature':  x_signature,
        'user-agent':   request.headers.get('user-agent', ''),
        'content-type': request.headers.get('content-type', ''),
    }

    # ── Deduplication check ───────────────────────────────────────────────────
    # First try the most stable key: x_request_id (set by MP on every notification).
    # If absent, fall back to payload_hash comparison.
    dup_qs = WebhookDelivery.objects.filter(
        processing_status__in=[
            WebhookDelivery.ProcessingStatus.PROCESSED,
            WebhookDelivery.ProcessingStatus.DUPLICATED,
        ],
    )
    if x_request_id:
        duplicate = dup_qs.filter(x_request_id=x_request_id).first()
    else:
        duplicate = dup_qs.filter(
            topic=topic,
            resource_id=resource_id,
            payload_hash=payload_hash,
        ).first()

    initial_status = (
        WebhookDelivery.ProcessingStatus.DUPLICATED
        if duplicate else WebhookDelivery.ProcessingStatus.RECEIVED
    )

    delivery = WebhookDelivery.objects.create(
        provider='mercadopago',
        topic=topic,
        resource_id=resource_id,
        action=action,
        x_request_id=x_request_id,
        x_signature=x_signature,
        signature_valid=sig_valid,
        payload_hash=payload_hash,
        headers_json=headers_snapshot,
        body_json=request.data,
        processing_status=initial_status,
        received_at=now,
    )

    if duplicate:
        logger.info(
            "[webhook] Duplicate delivery detected — topic=%s resource_id=%s x_request_id=%s "
            "original_delivery=%s new_delivery=%s",
            topic, resource_id, x_request_id, duplicate.id, delivery.id,
        )
        return delivery, sig_valid

    if not sig_valid:
        delivery.processing_status = WebhookDelivery.ProcessingStatus.IGNORED
        delivery.error_message = 'Signature verification failed'
        delivery.save(update_fields=['processing_status', 'error_message'])
        logger.warning(
            "[webhook] Invalid signature — delivery=%s topic=%s resource_id=%s x_request_id=%s",
            delivery.id, topic, resource_id, x_request_id,
        )
        return delivery, sig_valid

    logger.info(
        "[webhook] Received delivery=%s topic=%s resource_id=%s x_request_id=%s sig_valid=%s",
        delivery.id, topic, resource_id, x_request_id, sig_valid,
    )
    return delivery, sig_valid


def dispatch_webhook(delivery: WebhookDelivery) -> None:
    """
    Route a validated, non-duplicate delivery to the appropriate topic handler.
    Updates delivery.processing_status to PROCESSED or FAILED.
    """
    topic = delivery.topic
    resource_id = delivery.resource_id

    try:
        if topic == 'subscription_preapproval':
            _handle_subscription_preapproval(resource_id, delivery)
        elif topic == 'subscription_authorized_payment':
            _handle_authorized_payment(resource_id, delivery)
        else:
            # Other topics (payment, etc.) are handled by the legacy path in views.py
            # for backward compatibility.  Mark as ignored here so the delivery log
            # stays accurate.
            logger.info("[webhook] Topic '%s' not handled by Phase 3 processor — delivery=%s",
                        topic, delivery.id)
            delivery.processing_status = WebhookDelivery.ProcessingStatus.IGNORED
            delivery.processed_at = timezone.now()
            delivery.save(update_fields=['processing_status', 'processed_at'])
            return

        delivery.processing_status = WebhookDelivery.ProcessingStatus.PROCESSED
        delivery.processed_at = timezone.now()
        delivery.save(update_fields=['processing_status', 'processed_at'])

    except Exception as exc:
        delivery.processing_status = WebhookDelivery.ProcessingStatus.FAILED
        delivery.error_message = str(exc)
        delivery.processed_at = timezone.now()
        delivery.save(update_fields=['processing_status', 'error_message', 'processed_at'])
        logger.exception(
            "[webhook] Processing failed for delivery=%s topic=%s resource_id=%s: %s",
            delivery.id, topic, resource_id, exc,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Topic handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_subscription_preapproval(preapproval_id: str, delivery: WebhookDelivery) -> None:
    """
    Handle `subscription_preapproval` webhook.

    Correlation strategy (strictly in order, no email fallbacks):
      1. Fetch authoritative preapproval from MP.
      2. Extract `preapproval_plan_id` from the response.
      3. Find MpCheckoutSession by `provider_preapproval_plan_id`.
      4. Upsert SubscriptionV2.
      5. Transition session to linked/activated depending on preapproval status.
    """
    from .mp_service import MercadoPagoService

    if not preapproval_id:
        logger.warning("[webhook/preapproval] Empty preapproval_id — delivery=%s", delivery.id)
        return

    mp = MercadoPagoService()

    # Step 1: authoritative fetch — NEVER trust the webhook body alone.
    preapproval = mp.get_preapproval(preapproval_id)
    if not preapproval:
        raise ValueError(f"Could not fetch preapproval {preapproval_id} from MP")

    mp_status = preapproval.get('status', '')
    plan_id   = preapproval.get('preapproval_plan_id', '')

    logger.info(
        "[webhook/preapproval] delivery=%s preapproval_id=%s preapproval_status=%s plan_id=%s",
        delivery.id, preapproval_id, mp_status, plan_id,
    )

    # Step 2: find checkout session by plan_id (primary correlation key).
    session = None
    if plan_id:
        session = MpCheckoutSession.objects.filter(
            provider_preapproval_plan_id=plan_id
        ).first()

    if session is None:
        # Orphaned event: no session found for this plan_id.
        # Log with full context for operator / support investigation.
        logger.warning(
            "[webhook/preapproval] ORPHAN — no MpCheckoutSession for plan_id=%s "
            "preapproval_id=%s delivery=%s. "
            "Possible causes: checkout session expired/deleted, plan_id mismatch, "
            "or subscription created outside this system.",
            plan_id, preapproval_id, delivery.id,
        )
        # Do NOT activate anything. Store context on delivery for traceability.
        delivery.error_message = (
            f"Orphan: no session for plan_id={plan_id} preapproval_id={preapproval_id}"
        )
        delivery.save(update_fields=['error_message'])
        return

    logger.info(
        "[webhook/preapproval] Correlated delivery=%s → session=%s (status=%s)",
        delivery.id, session.id, session.status,
    )

    # Step 3: upsert SubscriptionV2 via the authoritative data.
    with transaction.atomic():
        _upsert_subscription_v2(
            preapproval_id=preapproval_id,
            plan_id=plan_id,
            session=session,
            preapproval_data=preapproval,
        )

        # Transition checkout session to LINKED via the state machine.
        # This guard prevents late webhooks from reopening terminal sessions
        # (e.g. a delayed preapproval notification after the session was already
        # activated, expired, or superseded).
        if session.status in MpCheckoutSession.TERMINAL_STATUSES:
            logger.info(
                "[webhook/preapproval] Session %s is already terminal (status=%s) — "
                "skipping state transition for delivery=%s",
                session.id, session.status, delivery.id,
            )
        else:
            try:
                transitioned = session.transition_to(MpCheckoutSession.Status.LINKED)
                if transitioned:
                    logger.info(
                        "[webhook/preapproval] session=%s → linked (delivery=%s)",
                        session.id, delivery.id,
                    )
            except ValueError as exc:
                logger.warning(
                    "[webhook/preapproval] State transition blocked for session=%s: %s",
                    session.id, exc,
                )


def _handle_authorized_payment(authorized_payment_id: str, delivery: WebhookDelivery) -> None:
    """
    Handle `subscription_authorized_payment` webhook.

    This is the ONLY trigger for activating a tenant / subscription.

    Flow:
      1. Fetch authoritative authorized_payment from MP.
      2. Upsert BillingInvoiceEvent.
      3. Find SubscriptionV2 by provider_sub_id.
      4. If first valid payment → activate subscription + session.
    """
    from .mp_service import MercadoPagoService
    from .subscription_activator import activate_subscription_from_invoice

    if not authorized_payment_id:
        logger.warning("[webhook/authorized_payment] Empty authorized_payment_id — delivery=%s", delivery.id)
        return

    mp = MercadoPagoService()

    # Step 1: authoritative fetch.
    ap_data = mp.get_authorized_payment(authorized_payment_id)
    if not ap_data:
        raise ValueError(f"Could not fetch authorized_payment {authorized_payment_id} from MP")

    ap_status         = ap_data.get('status', '')
    preapproval_id    = ap_data.get('preapproval_id', '')
    payment_id        = str(ap_data.get('payment_id', '') or ap_data.get('id', ''))
    amount            = ap_data.get('transaction_amount') or ap_data.get('total_paid_amount') or 0
    currency          = ap_data.get('currency_id', 'ARS')
    paid_at_str       = ap_data.get('date_approved') or ap_data.get('date_created')

    # ── Fix 5: Cross-validate authoritative response before processing ────────
    returned_id = str(ap_data.get('id', ''))
    if returned_id and returned_id != str(authorized_payment_id):
        raise ValueError(
            f"[webhook/authorized_payment] ID mismatch: requested={authorized_payment_id} "
            f"but MP returned id={returned_id}. Possible caching or routing issue."
        )

    if ap_status == 'authorized' and not preapproval_id:
        # Without preapproval_id we cannot correlate to any subscription.
        # Reject rather than log-and-continue to avoid silent data loss.
        raise ValueError(
            f"[webhook/authorized_payment] authorized payment {authorized_payment_id} has no "
            f"preapproval_id in MP response — cannot correlate to a subscription."
        )

    logger.info(
        "[webhook/authorized_payment] delivery=%s auth_payment_id=%s status=%s "
        "preapproval_id=%s amount=%s",
        delivery.id, authorized_payment_id, ap_status, preapproval_id, amount,
    )

    # Step 2: upsert BillingInvoiceEvent (idempotent by provider_authorized_payment_id).
    with transaction.atomic():
        invoice_event, created = BillingInvoiceEvent.objects.get_or_create(
            provider_authorized_payment_id=authorized_payment_id,
            defaults={
                'provider_payment_id': payment_id,
                'provider_subscription_id': preapproval_id,
                'amount': amount,
                'currency': currency,
                'provider_status': ap_status,
                'paid_at': _parse_dt(paid_at_str),
                'raw_payload_json': ap_data,
                'webhook_delivery': delivery,
            },
        )
        if not created:
            # Update mutable fields (status can change, e.g. pending → authorized).
            changed = {}
            if invoice_event.provider_status != ap_status:
                changed['provider_status'] = ap_status
            if not invoice_event.paid_at and _parse_dt(paid_at_str):
                changed['paid_at'] = _parse_dt(paid_at_str)
            if changed:
                for k, v in changed.items():
                    setattr(invoice_event, k, v)
                invoice_event.save(update_fields=list(changed.keys()) + ['updated_at'])
            logger.info(
                "[webhook/authorized_payment] BillingInvoiceEvent already exists id=%s — updated fields=%s",
                invoice_event.id, list(changed.keys()),
            )
        else:
            logger.info(
                "[webhook/authorized_payment] Created BillingInvoiceEvent id=%s auth_payment_id=%s",
                invoice_event.id, authorized_payment_id,
            )

        # Step 3: find SubscriptionV2 by preapproval_id.
        subscription = None
        if preapproval_id:
            subscription = SubscriptionV2.objects.filter(
                provider_sub_id=preapproval_id
            ).first()

        if subscription is None:
            # May happen if the preapproval webhook fired AFTER the payment webhook
            # (race condition).  Log as orphan — the reconciliation job will fix it.
            logger.warning(
                "[webhook/authorized_payment] No SubscriptionV2 for preapproval_id=%s "
                "auth_payment_id=%s delivery=%s — orphan invoice event, will be reconciled.",
                preapproval_id, authorized_payment_id, delivery.id,
            )
        else:
            # Link invoice event to subscription (idempotent).
            if invoice_event.subscription_id != subscription.pk:
                invoice_event.subscription = subscription
                invoice_event.save(update_fields=['subscription', 'updated_at'])

            # Link invoice event to checkout session if available.
            if subscription.checkout_session_id and invoice_event.checkout_session_id is None:
                invoice_event.checkout_session = subscription.checkout_session
                invoice_event.save(update_fields=['checkout_session', 'updated_at'])

        # Step 4: activate if first valid payment.
        if ap_status == 'authorized' and subscription is not None:
            # Guard: preapproval_id from the payment must match subscription.provider_sub_id.
            # This should always hold since we looked up by provider_sub_id, but an explicit
            # check prevents silent data corruption if there is ever an index inconsistency.
            if subscription.provider_sub_id != preapproval_id:
                raise ValueError(
                    f"[webhook/authorized_payment] preapproval_id mismatch: "
                    f"subscription.provider_sub_id={subscription.provider_sub_id!r} but "
                    f"authorized_payment.preapproval_id={preapproval_id!r}. "
                    f"Refusing activation."
                )
            # Warn on zero-amount payments (free trials, test charges).
            if float(amount or 0) <= 0:
                logger.warning(
                    "[webhook/authorized_payment] 'authorized' payment but amount=%s ≤ 0 "
                    "for auth_payment=%s subscription=%s — proceeding with activation "
                    "but flagging for manual review.",
                    amount, authorized_payment_id, subscription.pk,
                )
            # Guard: refuse to activate a subscription in a terminal state.
            # A late authorized_payment webhook for a CANCELED subscription must not
            # resurrect it — that requires an explicit operator action.
            if not subscription.can_activate():
                logger.warning(
                    "[webhook/authorized_payment] Subscription %s is in terminal "
                    "status=%s — refusing activation for auth_payment=%s delivery=%s",
                    subscription.pk, subscription.status, authorized_payment_id, delivery.id,
                )
            else:
                activate_subscription_from_invoice(
                    invoice_event=invoice_event,
                    subscription=subscription,
                )
        elif ap_status != 'authorized':
            logger.info(
                "[webhook/authorized_payment] Payment status=%s — not activating (delivery=%s)",
                ap_status, delivery.id,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_subscription_v2(
    *,
    preapproval_id: str,
    plan_id: str,
    session: MpCheckoutSession,
    preapproval_data: dict,
) -> SubscriptionV2:
    """
    Create or update a SubscriptionV2 from authoritative preapproval data.
    Idempotent: uses provider_sub_id as the unique key.
    """
    mp_status = preapproval_data.get('status', '')

    # Determine plan_code from the checkout session's plan FK.
    plan_code = session.plan.code

    defaults = {
        'business': session.tenant,
        'service_type': (session.tenant.default_service if session.tenant else 'gestion'),
        'plan_code': plan_code,
        'provider': SubscriptionV2.Provider.MERCADOPAGO,
        'external_reference': session.mp_external_reference or f"SUB-{preapproval_id}",
        'provider_preapproval_plan_id': plan_id,
        'checkout_session': session,
        'raw_snapshot_json': preapproval_data,
        # Do NOT set status=ACTIVE here.  Status transitions are driven by payments.
        # A preapproval webhook puts us in CHECKOUT_PENDING still; activation waits
        # for the first authorized_payment event.
        'status': SubscriptionV2.Status.CHECKOUT_PENDING,
    }

    sub, created = SubscriptionV2.objects.get_or_create(
        provider_sub_id=preapproval_id,
        defaults=defaults,
    )

    if not created:
        # Update mutable fields on subsequent webhooks.
        changed: dict = {}
        if not sub.checkout_session_id:
            changed['checkout_session'] = session
        if not sub.provider_preapproval_plan_id:
            changed['provider_preapproval_plan_id'] = plan_id
        changed['raw_snapshot_json'] = preapproval_data
        for k, v in changed.items():
            setattr(sub, k, v)
        sub.save(update_fields=list(changed.keys()) + ['updated_at'])
        logger.info(
            "[webhook/preapproval] SubscriptionV2 already exists id=%s — updated fields=%s",
            sub.pk, list(changed.keys()),
        )
    else:
        logger.info(
            "[webhook/preapproval] Created SubscriptionV2 id=%s preapproval_id=%s plan_id=%s",
            sub.pk, preapproval_id, plan_id,
        )

    return sub


def _verify_mp_signature(request, x_request_id: str, x_signature: str) -> bool:
    """
    Verify the Mercado Pago webhook signature.

    Algorithm (per MP docs):
      manifest = "id:<data.id>;request-id:<x-request-id>;ts:<ts>"
      expected  = HMAC-SHA256(manifest, secret)
      compare   = compare_digest(expected, v1_from_header)

    Returns True if valid.
    Returns True if MP_WEBHOOK_SECRET is not set (DEV bypass — logged as warning).
    Returns False if secret is set but signature is absent or invalid.
    """
    secret = getattr(settings, 'MP_WEBHOOK_SECRET', None)
    if not secret:
        if getattr(settings, 'DEBUG', False):
            logger.warning(
                "[webhook] MP_WEBHOOK_SECRET not set — DEV mode bypass active. "
                "This MUST be set in production via the MP_WEBHOOK_SECRET env var.",
            )
            return True
        # Production without a secret: reject every unsigned webhook.
        # A missing secret in non-DEBUG mode is a misconfiguration, not a DEV convenience.
        logger.error(
            "[webhook] MP_WEBHOOK_SECRET is not configured in a non-DEBUG environment. "
            "All inbound webhooks will be rejected until it is set. "
            "Fix: add MP_WEBHOOK_SECRET to your environment variables.",
        )
        return False

    ts = ''
    v1 = ''
    for part in x_signature.split(','):
        part = part.strip()
        if part.startswith('ts='):
            ts = part[3:]
        elif part.startswith('v1='):
            v1 = part[3:]

    if not ts or not v1:
        logger.warning("[webhook] x-signature header missing or malformed: %r", x_signature)
        return False

    data_id = str(request.data.get('data', {}).get('id', ''))
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts}"

    try:
        expected = hmac_lib.new(
            secret.encode('utf-8'),
            manifest.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
    except Exception as exc:
        logger.error("[webhook] HMAC computation error: %s", exc)
        return False

    if not hmac_lib.compare_digest(expected, v1):
        logger.warning("[webhook] Signature mismatch manifest=%r", manifest)
        return False

    return True


def _parse_dt(value: str | None):
    """Parse an ISO datetime string from MP. Returns None on failure."""
    if not value:
        return None
    from django.utils.dateparse import parse_datetime
    try:
        result = parse_datetime(value)
        if result and result.tzinfo is None:
            from django.utils import timezone as tz
            result = tz.make_aware(result)
        return result
    except Exception:
        return None
