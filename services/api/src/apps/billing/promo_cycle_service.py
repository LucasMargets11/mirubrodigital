"""
billing/promo_cycle_service.py
==============================
Tracks promotional discount cycles and restores the original subscription
price on MercadoPago when all discount cycles are exhausted.

Entry point
-----------
``handle_promo_cycle(subscription, authorized_payment_id)``

Called by ``webhook_processor._handle_authorized_payment`` for every
``subscription_authorized_payment`` event with ``status='authorized'``.
It is intentionally called OUTSIDE the outer ``transaction.atomic()`` block
in the webhook processor so that a MercadoPago restore failure cannot roll
back the subscription activation.

Idempotency contract
--------------------
``PromoCodeRedemption.last_applied_payment_id`` is set to the MP
``authorized_payment_id`` on every consumed cycle.  If the same payment ID
arrives again (duplicate webhook), the handler returns immediately without
incrementing ``cycles_used``.

Price restoration
-----------------
When ``cycles_used >= cycles_total``:
  - ``update_preapproval`` is called on MP with the original plan amount.
  - On success: ``status=COMPLETED``, ``price_restored=True``.
  - On failure: ``status=COMPLETED``, ``price_restored=False`` — the
    ``reconcile_promotional_discounts`` Celery task retries periodically.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def handle_promo_cycle(subscription, authorized_payment_id: str) -> None:
    """
    Process one billing cycle for an active promotional discount.

    Args:
        subscription: A ``SubscriptionV2`` instance whose payment was confirmed
                      as ``'authorized'`` by MercadoPago.
        authorized_payment_id: The MP ``authorized_payment`` resource ID
                                (``data.id`` from the webhook payload).

    Behaviour:
        - No-op if no PENDING/ACTIVE ``PromoCodeRedemption`` exists for this
          subscription.
        - Increments ``cycles_used`` by exactly 1.
        - Transitions ``PENDING → ACTIVE`` on the first confirmed payment.
        - When ``cycles_used >= cycles_total``:
            * Attempts to restore the original amount on the MP preapproval.
            * Marks redemption ``COMPLETED`` regardless of MP outcome.
            * MP failure → ``price_restored=False``, error logged; does NOT raise.

    Thread safety:
        Uses ``select_for_update()`` inside ``transaction.atomic()`` so
        concurrent authorized_payment webhooks for the same subscription are
        serialised at the DB level.
    """
    from .models import PromoCodeRedemption  # local import avoids circular dep

    with transaction.atomic():
        redemption = (
            PromoCodeRedemption.objects
            .select_for_update()
            .filter(
                subscription=subscription,
                status__in=[
                    PromoCodeRedemption.Status.PENDING,
                    PromoCodeRedemption.Status.ACTIVE,
                ],
            )
            .first()
        )

        if redemption is None:
            logger.debug(
                "[promo_cycle] No active redemption for subscription=%s "
                "auth_payment=%s — no-op.",
                subscription.pk, authorized_payment_id,
            )
            return

        # ── Idempotency guard ─────────────────────────────────────────────────
        if redemption.last_applied_payment_id == str(authorized_payment_id):
            logger.info(
                "[promo_cycle] Duplicate payment skipped. "
                "redemption=%s subscription=%s auth_payment=%s cycles_used=%d",
                redemption.pk, subscription.pk,
                authorized_payment_id, redemption.cycles_used,
            )
            return

        # ── First payment: PENDING → ACTIVE ───────────────────────────────────
        if redemption.status == PromoCodeRedemption.Status.PENDING:
            redemption.status = PromoCodeRedemption.Status.ACTIVE
            logger.info(
                "[promo_cycle] Redemption %s: PENDING → ACTIVE (first confirmed payment).",
                redemption.pk,
            )

        # ── Consume cycle ─────────────────────────────────────────────────────
        redemption.cycles_used += 1
        redemption.last_applied_payment_id = str(authorized_payment_id)

        logger.info(
            "[promo_cycle] Cycle consumed: redemption=%s subscription=%s "
            "auth_payment=%s cycles_used=%d / cycles_total=%d",
            redemption.pk, subscription.pk, authorized_payment_id,
            redemption.cycles_used, redemption.cycles_total,
        )

        # ── Price restoration when all cycles are exhausted ───────────────────
        if redemption.cycles_used >= redemption.cycles_total:
            _complete_and_restore_price(redemption, subscription)

        redemption.save()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _complete_and_restore_price(redemption, subscription) -> None:
    """
    Mark the redemption as COMPLETED and attempt to restore the original price
    on the MP preapproval.

    Must be called inside an active ``transaction.atomic()`` + ``select_for_update()``
    context (i.e. from ``handle_promo_cycle``).

    Does NOT raise on MP errors — failures are recorded in ``price_restored=False``
    and retried by ``reconcile_promotional_discounts``.
    """
    from .models import PromoCodeRedemption as _PromoCodeRedemption  # local import
    from .mp_service import MercadoPagoService  # local import avoids circular dep

    redemption.status = _PromoCodeRedemption.Status.COMPLETED

    if not getattr(subscription, 'provider_sub_id', None):
        logger.error(
            "[promo_cycle] Cannot restore price: subscription=%s has no provider_sub_id. "
            "Marked COMPLETED with price_restored=False.",
            subscription.pk,
        )
        redemption.price_restored = False
        return

    try:
        mp = MercadoPagoService()
        mp.update_preapproval(
            subscription.provider_sub_id,
            {"auto_recurring": {"transaction_amount": float(redemption.original_amount)}},
        )
        redemption.price_restored = True
        redemption.price_restored_at = timezone.now()
        logger.info(
            "[promo_cycle] Original price %.2f restored on MP preapproval=%s "
            "(redemption=%s subscription=%s).",
            redemption.original_amount, subscription.provider_sub_id,
            redemption.pk, subscription.pk,
        )

    except Exception as exc:
        logger.error(
            "[promo_cycle] Failed to restore price for subscription=%s "
            "redemption=%s: %s — price_restored=False; "
            "reconcile_promotional_discounts will retry.",
            subscription.pk, redemption.pk, exc,
        )
        redemption.price_restored = False
