"""
billing/payment_webhook.py
==========================
Processing of Mercado Pago ``payment`` topic deliveries (Billing one-time
payments and merchant Tips).

Slice 5B.4 moved this logic out of MercadoPagoWebhookView so it can run
from a persisted WebhookDelivery (retry / replay) without the original HTTP
request. Routing is exactly the 5B.2.2 architecture:

  Merchant: flow=tip     → TipTransaction(ref) → Business → merchant
            connection → Business token → authoritative fetch
            flow=appointment → AppointmentPayment(ref) → Business → merchant
            connection → Business token → authoritative fetch (Slice 6B)
  Billing:  flow=billing → PendingSubscriptionChange(ref) → platform
            credentials → authoritative fetch
  Anything else → fail closed (IGNORED): no fetch, no mutation. A bare
  payment_id is never used to decide the domain or the credential.

Return values follow apps.billing.webhook_lifecycle: a WebhookOutcome
(PROCESSED / IGNORED) or a raised WebhookTransientError (→ FAILED, retried).
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import BillingEvent
from .webhook_lifecycle import WebhookOutcome, WebhookPermanentError, WebhookTransientError

logger = logging.getLogger(__name__)

# MerchantPaymentConnectionUnavailable.reason values that a later retry can
# plausibly clear on its own. Every other reason requires the Business to
# reconnect (see _fetch_merchant_payment_or_raise).
_MERCHANT_TRANSIENT_REASONS = frozenset({'refresh_temporarily_unavailable'})


def process_payment_event(payment_id, *, flow=None, ref=None, billing_event=None) -> WebhookOutcome:
    """
    Process one ``payment`` notification. See module docstring for routing.
    """
    from .views import _update_billing_event

    if not payment_id:
        return WebhookOutcome.ignored('missing_resource_id')

    # ── Merchant-side (Customer → Business) routing ────────────────────────
    # A merchant (Tip) payment is NEVER re-fetched with the platform's
    # global MP_ACCESS_TOKEN. This is a hint, not proof of identity — the
    # confirmation still re-derives the Business from the local
    # TipTransaction and requires the merchant-fetched payment's own
    # external_reference to match it.
    if flow == 'tip':
        if not ref:
            logger.warning("[MPWebhook][merchant] flow=tip without ref — payment_id=%s", payment_id)
            return WebhookOutcome.ignored('merchant_missing_ref')
        return _process_merchant_tip_payment(payment_id, ref)

    # Turnos (Slice 6B): mismo esquema merchant-side que Tips — el Business
    # sale del AppointmentPayment local, nunca del request ni de un fetch.
    if flow == 'appointment':
        if not ref:
            logger.warning("[MPWebhook][appointment] flow=appointment without ref — payment_id=%s", payment_id)
            return WebhookOutcome.ignored('merchant_missing_ref')
        return _process_merchant_appointment_payment(payment_id, ref)

    # ── Billing-side (Business → MiRubro) routing ───────────────────────────
    # A Billing payment is NEVER re-fetched with a merchant's own connection.
    if flow == 'billing':
        if not ref:
            logger.warning("[MPWebhook][billing] flow=billing without ref — payment_id=%s", payment_id)
            return WebhookOutcome.ignored('billing_missing_ref')
        return _process_billing_payment(payment_id, ref, billing_event)

    # ── Legacy / unrecognized hint ───────────────────────────────────────────
    # Preferences created before 5B.2.2, or a malformed/forged callback.
    # payment_id is deliberately NOT used to search TipTransaction or
    # PendingSubscriptionChange, nor to fetch the payment to "find out" the
    # domain: ids are scoped per MP account and can collide. Fail closed.
    # Recovery: Tips → PublicTipVerifyView (tip_id path param). Billing has
    # no equivalent recovery path today (see Slice 5B.2.2 report).
    logger.warning(
        "[MPWebhook] LEGACY/UNRESOLVED — payment_id=%s has no recognized flow hint "
        "(flow=%r). No payment fetch performed; no local record mutated.",
        payment_id, flow,
    )
    _update_billing_event(
        billing_event,
        new_status=BillingEvent.ProcessingStatus.IGNORED,
        error_message=f'legacy_unresolved: payment_id={payment_id} has no flow hint',
    )
    return WebhookOutcome.ignored('legacy_unresolved')


# ─────────────────────────────────────────────────────────────────────────────
# Merchant (Tips)
# ─────────────────────────────────────────────────────────────────────────────

def _process_merchant_tip_payment(payment_id, external_reference: str) -> WebhookOutcome:
    """
    Authoritative confirmation for a merchant-side Tip payment. Resolves the
    owning Business from the local TipTransaction FIRST, then re-fetches the
    payment using ONLY that Business's own Mercado Pago connection — never
    the platform's global token, never another Business's connection.
    """
    from apps.menu.models import TipTransaction

    try:
        tip = TipTransaction.objects.select_related('business').get(
            external_reference=external_reference,
        )
    except TipTransaction.DoesNotExist:
        logger.warning(
            "[MPWebhook][merchant] TipTransaction not found for ref=%s payment_id=%s",
            external_reference, payment_id,
        )
        return WebhookOutcome.ignored('merchant_record_not_found')

    payment_data = _fetch_merchant_payment_or_raise(tip.business, payment_id)

    fetched_ref = payment_data.get('external_reference')
    if fetched_ref != tip.external_reference:
        logger.warning(
            "[MPWebhook][merchant] external_reference mismatch: expected=%s got=%s payment_id=%s",
            tip.external_reference, fetched_ref, payment_id,
        )
        return WebhookOutcome.ignored(
            'merchant_ref_mismatch', f'expected={tip.external_reference} got={fetched_ref}',
        )

    process_tip_payment(tip.external_reference, payment_data.get('status'), payment_id)
    return WebhookOutcome.processed()


def _fetch_merchant_payment_or_raise(business, payment_id) -> dict:
    """
    Merchant-side authoritative fetch with the 5B.4 failure classification
    (Tips and Turnos). Never falls back to the global token. A temporary
    refresh failure is retried with backoff. A connection that needs the
    Business to reconnect (refresh rejected, not connected, status=error, …)
    will not heal on its own: DEAD_LETTER at once, observable, replayable
    with --revive-dead-letter after the owner reconnects.
    get_merchant_payment collapses network errors, 5xx and 404 into None —
    treated as transient; bounded retries end in DEAD_LETTER.
    """
    from apps.merchant_payments.services import (
        MerchantPaymentConnectionUnavailable,
        get_merchant_payment,
    )

    try:
        payment_data = get_merchant_payment(business, payment_id)
    except MerchantPaymentConnectionUnavailable as exc:
        detail = f'merchant connection unavailable business={exc.business_id} reason={exc.reason}'
        if exc.reason in _MERCHANT_TRANSIENT_REASONS:
            raise WebhookTransientError('merchant_refresh_temporary', detail) from None
        raise WebhookPermanentError('merchant_reauth_required', detail) from None

    if not payment_data:
        raise WebhookTransientError(
            'provider_fetch_failed',
            f'merchant payment fetch returned nothing payment_id={payment_id} business={business.id}',
        )
    return payment_data


# ─────────────────────────────────────────────────────────────────────────────
# Merchant (Turnos — Slice 6B)
# ─────────────────────────────────────────────────────────────────────────────

def _process_merchant_appointment_payment(payment_id, external_reference: str) -> WebhookOutcome:
    """
    Authoritative confirmation for a Turnos deposit. external_reference →
    AppointmentPayment → Business → that Business's own MP connection →
    re-fetch → validate → apply (apps.appointments.services.payment_confirmation,
    which owns the locking and the "confirm only if still safe" rules).

    Outcomes:
      applied / idempotent / pending / rejected / requires_review → PROCESSED
      stale event, ref mismatch, unknown record                   → IGNORED
      MP timeout / 5xx / temporary refresh / concurrent move      → FAILED (retry)
      reauth needed, amount/currency/collector mismatch, payment
      id already used, second approved payment                    → DEAD_LETTER
    """
    from apps.appointments.models import EXTERNAL_REFERENCE_PREFIX, AppointmentPayment
    from apps.appointments.services import payment_confirmation as confirmation
    from apps.merchant_payments.models import MercadoPagoConnection

    if not external_reference.startswith(EXTERNAL_REFERENCE_PREFIX):
        logger.warning(
            "[MPWebhook][appointment] unrecognized ref=%r payment_id=%s", external_reference, payment_id,
        )
        return WebhookOutcome.ignored('appointment_unrecognized_ref')

    try:
        appointment_payment = AppointmentPayment.objects.select_related('business', 'appointment').get(
            external_reference=external_reference,
        )
    except AppointmentPayment.DoesNotExist:
        logger.warning(
            "[MPWebhook][appointment] AppointmentPayment not found for ref=%s payment_id=%s",
            external_reference, payment_id,
        )
        return WebhookOutcome.ignored('merchant_record_not_found')

    business = appointment_payment.business
    if appointment_payment.appointment.business_id != business.id:
        raise WebhookPermanentError(
            'appointment_business_mismatch', f'appointment_payment={appointment_payment.pk}',
        )

    payment_data = _fetch_merchant_payment_or_raise(business, payment_id)

    merchant_user_id = (
        MercadoPagoConnection.objects.filter(business=business)
        .values_list('mp_user_id', flat=True).first()
    )
    problem = confirmation.validate_provider_payment(
        appointment_payment, payment_data, merchant_user_id=merchant_user_id,
    )
    if problem is None:
        try:
            outcome = confirmation.apply_provider_payment(
                appointment_payment_id=appointment_payment.pk,
                provider_payment_id=payment_id,
                payment_data=payment_data,
            )
        except confirmation.ConcurrentAppointmentChange:
            raise WebhookTransientError(
                'appointment_concurrent_change', f'appointment_payment={appointment_payment.pk}',
            ) from None
    else:
        outcome = problem

    R = confirmation.Result
    detail = f'appointment_payment={appointment_payment.pk} payment_id={payment_id} {outcome.detail}'.strip()
    if outcome.result in (R.APPLIED, R.ALREADY_APPLIED, R.STATUS_RECORDED):
        return WebhookOutcome.processed()
    if outcome.result == R.REQUIRES_REVIEW:
        # The money is recorded on the AppointmentPayment (requires_review);
        # the delivery itself succeeded. Note kept for operators.
        return WebhookOutcome.processed(f'requires_review {detail}')
    if outcome.result == R.STALE:
        return WebhookOutcome.ignored('appointment_stale_event', detail)
    if outcome.result == R.REF_MISMATCH:
        logger.warning("[MPWebhook][appointment] external_reference mismatch %s", detail)
        return WebhookOutcome.ignored('merchant_ref_mismatch', detail)
    # Financial inconsistency: nothing was mutated; a human must look.
    logger.error("[MPWebhook][appointment] %s — %s", outcome.result, detail)
    raise WebhookPermanentError(f'appointment_{outcome.result}', detail)


def process_tip_payment(external_reference: str, payment_status: str, payment_id) -> None:
    """Idempotently update a TipTransaction from an MP payment. Never creates one."""
    from apps.menu.models import TipTransaction
    try:
        tip = TipTransaction.objects.get(external_reference=external_reference)
    except TipTransaction.DoesNotExist:
        logger.warning("[TipWebhook] TipTransaction not found for ref %s", external_reference)
        return

    status_map = {
        'approved': 'approved', 'authorized': 'approved',
        'rejected': 'rejected', 'cancelled': 'cancelled',
        'pending': 'pending',   'in_process': 'pending',
    }
    new_status = status_map.get(payment_status, tip.status)
    update_fields = ['updated_at']
    if tip.status != new_status:
        tip.status = new_status
        update_fields.append('status')
    if payment_id and not tip.mp_payment_id:
        tip.mp_payment_id = str(payment_id)
        update_fields.append('mp_payment_id')
    tip.save(update_fields=update_fields)
    logger.info("[TipWebhook] %s → %s (mp_payment_id=%s)", external_reference, new_status, payment_id)


# ─────────────────────────────────────────────────────────────────────────────
# Billing
# ─────────────────────────────────────────────────────────────────────────────

def _process_billing_payment(payment_id, ref: str, billing_event=None) -> WebhookOutcome:
    """
    Authoritative confirmation for a Billing one-time payment. Resolves the
    PendingSubscriptionChange from the local ``ref`` FIRST, THEN fetches the
    payment using ONLY the platform's own credentials, and requires the
    fetched payment's external_reference to match ``ref``.
    """
    from .models import PendingSubscriptionChange
    from .mp_service import MercadoPagoService

    is_subscription_change = ref.startswith('subscription_change_')
    is_addon_purchase       = ref.startswith('addon_purchase_')
    is_reviews_upgrade      = ref.startswith('reviews_upgrade_')

    if not (is_subscription_change or is_addon_purchase or is_reviews_upgrade):
        logger.warning(
            "[MPWebhook][billing] Unrecognized ref pattern=%r — payment_id=%s", ref, payment_id,
        )
        return WebhookOutcome.ignored('billing_unrecognized_ref')

    pending_change_id = ref.split('_')[-1]
    try:
        pending_change = PendingSubscriptionChange.objects.get(id=pending_change_id)
    except (PendingSubscriptionChange.DoesNotExist, ValueError, TypeError, ValidationError):
        logger.warning(
            "[MPWebhook][billing] PendingSubscriptionChange not found for ref=%s payment_id=%s",
            ref, payment_id,
        )
        return WebhookOutcome.ignored('billing_record_not_found')

    payment_data = MercadoPagoService().get_payment(payment_id)
    if not payment_data:
        # get_payment collapses network errors, 5xx and 404 into None.
        raise WebhookTransientError(
            'provider_fetch_failed', f'platform payment fetch returned nothing payment_id={payment_id}',
        )

    fetched_ref = payment_data.get('external_reference')
    if fetched_ref != ref:
        logger.warning(
            "[MPWebhook][billing] external_reference mismatch: expected=%s got=%s payment_id=%s",
            ref, fetched_ref, payment_id,
        )
        return WebhookOutcome.ignored('billing_ref_mismatch', f'expected={ref} got={fetched_ref}')

    _apply_billing_payment(
        pending_change=pending_change,
        payment_data=payment_data,
        payment_id=payment_id,
        billing_event=billing_event,
        is_addon_purchase=is_addon_purchase,
        is_reviews_upgrade=is_reviews_upgrade,
    )
    return WebhookOutcome.processed()


def _apply_billing_payment(*, pending_change, payment_data, payment_id,
                           billing_event, is_addon_purchase, is_reviews_upgrade) -> None:
    """
    Apply a Billing payment's status to its PendingSubscriptionChange.

    Idempotent: a change already ``completed`` is never re-applied
    (duplicate notifications and retries are no-ops). If the apply itself
    fails, the change is marked ``failed`` and the error is re-raised so the
    delivery goes FAILED and is retried — the approved branch re-applies a
    ``failed`` change.
    """
    from apps.billing.services.commercial.apply import apply_subscription_change, apply_addon_activation
    from apps.billing.reviews_views import apply_reviews_plan_upgrade
    from .views import _create_payment_attempt, _resolve_subscriptionv2, _update_billing_event

    payment_status = payment_data.get('status')

    if pending_change.status == 'completed':
        logger.info(
            "[MPWebhook][billing] PendingSubscriptionChange %s already completed — no-op "
            "(payment_id=%s status=%s)",
            pending_change.id, payment_id, payment_status,
        )
        return

    pending_change.mp_payment_id = str(payment_id)

    if payment_status == 'approved':
        pending_change.status = 'processing'
        pending_change.save()
        try:
            if is_addon_purchase:
                addon_codes = [k for k, v in pending_change.config_snapshot.items() if v is True]
                if addon_codes:
                    apply_addon_activation(
                        business=pending_change.business,
                        addon_code=addon_codes[0],
                    )
                else:
                    raise ValueError("No addon code found in config_snapshot")
            elif is_reviews_upgrade:
                apply_reviews_plan_upgrade(
                    business=pending_change.business,
                    target_plan_code=pending_change.target_plan_code,
                )
            else:
                apply_subscription_change(
                    business=pending_change.business,
                    target_plan_code=pending_change.target_plan_code,
                    billing_cycle=pending_change.billing_cycle,
                    config=pending_change.config_snapshot,
                )
        except Exception as e:
            pending_change.status = 'failed'
            pending_change.save()
            _update_billing_event(billing_event, new_status=BillingEvent.ProcessingStatus.ERROR,
                                  error_message=str(e))
            logger.error("[MPWebhook][billing] Error applying change %s: %s", pending_change.id, e)
            raise WebhookTransientError(
                'billing_apply_failed', f'{type(e).__name__}: {e}',
            ) from None

        pending_change.status = 'completed'
        pending_change.applied_at = timezone.now()
        pending_change.save()
        try:
            biz = pending_change.business
            svc = 'qr_reviews' if is_reviews_upgrade else biz.default_service
            v2 = _resolve_subscriptionv2(biz, svc)
            _create_payment_attempt(v2, billing_event, payment_data, payment_id)
            if v2:
                _update_billing_event(billing_event, sub_v2=v2,
                                      new_status=BillingEvent.ProcessingStatus.PROCESSED)
        except Exception as exc:
            logger.warning("[_apply_billing_payment] PaymentAttempt update failed: %s", exc)

    elif payment_status in ['rejected', 'cancelled']:
        pending_change.status = 'failed'
        pending_change.save()
        try:
            biz = pending_change.business
            v2 = _resolve_subscriptionv2(biz, biz.default_service)
            _create_payment_attempt(v2, billing_event, payment_data, payment_id)
            _update_billing_event(billing_event, sub_v2=v2,
                                  new_status=BillingEvent.ProcessingStatus.PROCESSED)
        except Exception as exc:
            logger.warning("[_apply_billing_payment] PaymentAttempt (rejected) failed: %s", exc)
    else:
        pending_change.save()
