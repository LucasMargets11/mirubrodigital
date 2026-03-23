"""
billing/cancellation_service.py — Domain logic for subscription cancellation.

Responsibilities:
  - Schedule cancellation (set cancel_at_period_end, cancel_requested_at, etc.)
  - Undo a scheduled cancellation
  - Execute a scheduled cancellation against MercadoPago
  - Validate business rules (permissions, state, timing)

All MP interaction is delegated to MercadoPagoService.
"""
from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone

from .models import SubscriptionV2
from .mp_service import MercadoPagoService

logger = logging.getLogger(__name__)


class CancellationError(Exception):
    """Domain error raised when a cancellation operation is invalid."""
    pass


def schedule_cancellation(
    subscription: SubscriptionV2,
    reason: str = '',
) -> SubscriptionV2:
    """
    Schedule a subscription for cancellation at current_period_end.

    The user keeps access until the end of the current billing period.
    The actual MP cancellation is executed by the periodic task.

    Raises:
        CancellationError: if the subscription cannot be scheduled for cancellation.
    """
    if subscription.status in SubscriptionV2.TERMINAL_STATUSES:
        raise CancellationError('La suscripción ya está cancelada.')

    if subscription.cancel_at_period_end:
        raise CancellationError('La baja ya está programada.')

    if subscription.status not in (
        SubscriptionV2.Status.ACTIVE,
        SubscriptionV2.Status.TRIALING,
        SubscriptionV2.Status.PAST_DUE,
    ):
        raise CancellationError(
            f'No se puede programar la baja en estado "{subscription.get_status_display()}".'
        )

    now = timezone.now()

    # For manual/legacy subscriptions without a billing period,
    # set current_period_end to now so the cron job picks it up immediately.
    update_fields = [
        'cancel_at_period_end',
        'cancel_requested_at',
        'cancel_reason',
        'updated_at',
    ]
    if not subscription.current_period_end:
        subscription.current_period_end = now
        update_fields.append('current_period_end')

    effective_date = subscription.current_period_end

    subscription.cancel_at_period_end = True
    subscription.cancel_requested_at = now
    subscription.cancel_reason = reason or ''
    subscription.save(update_fields=update_fields)

    logger.info(
        "[cancellation] Scheduled cancellation for sub=%s business=%s effective=%s reason=%r",
        subscription.pk, subscription.business_id, effective_date, reason,
    )
    return subscription


def undo_cancellation(subscription: SubscriptionV2) -> SubscriptionV2:
    """
    Undo a scheduled cancellation if the effective date has not passed.

    Raises:
        CancellationError: if the cancellation cannot be undone.
    """
    if not subscription.cancel_at_period_end:
        raise CancellationError('No hay baja programada para deshacer.')

    if subscription.status in SubscriptionV2.TERMINAL_STATUSES:
        raise CancellationError('La suscripción ya fue cancelada definitivamente.')

    now = timezone.now()
    effective_date = subscription.current_period_end

    if effective_date and effective_date <= now:
        raise CancellationError(
            'La fecha efectiva de baja ya pasó. No se puede deshacer.'
        )

    subscription.cancel_at_period_end = False
    subscription.cancel_requested_at = None
    subscription.cancel_reason = None
    subscription.save(update_fields=[
        'cancel_at_period_end',
        'cancel_requested_at',
        'cancel_reason',
        'updated_at',
    ])

    logger.info(
        "[cancellation] Undid scheduled cancellation for sub=%s business=%s",
        subscription.pk, subscription.business_id,
    )
    return subscription


def execute_cancellation(
    subscription: SubscriptionV2,
    mp_service: MercadoPagoService | None = None,
) -> SubscriptionV2:
    """
    Execute the actual cancellation of a subscription.

    Cancels the preapproval in MercadoPago (if applicable) and marks the
    subscription as CANCELED locally.

    Idempotent: if the subscription is already CANCELED, this is a no-op.

    Args:
        subscription: The SubscriptionV2 to cancel.
        mp_service: Optional MercadoPagoService instance (for testing/DI).

    Returns:
        The updated subscription.

    Raises:
        Exception: if the MP API call fails (caller should handle retries).
    """
    if subscription.status == SubscriptionV2.Status.CANCELED:
        logger.info(
            "[cancellation] Already canceled sub=%s — idempotent no-op.",
            subscription.pk,
        )
        return subscription

    now = timezone.now()

    # Cancel in MercadoPago if we have a provider subscription ID
    if (
        subscription.provider == SubscriptionV2.Provider.MERCADOPAGO
        and subscription.provider_sub_id
    ):
        svc = mp_service or MercadoPagoService()
        try:
            svc.update_preapproval(
                subscription.provider_sub_id,
                {"status": "cancelled"},
            )
            logger.info(
                "[cancellation] MP preapproval cancelled id=%s sub=%s",
                subscription.provider_sub_id, subscription.pk,
            )
        except Exception as exc:
            logger.error(
                "[cancellation] MP cancellation failed sub=%s mp_id=%s: %s",
                subscription.pk, subscription.provider_sub_id, exc,
            )
            raise

    subscription.status = SubscriptionV2.Status.CANCELED
    subscription.canceled_at = now
    subscription.is_active = False
    subscription.save(update_fields=[
        'status', 'canceled_at', 'is_active', 'updated_at',
    ])

    logger.info(
        "[cancellation] Subscription canceled sub=%s business=%s",
        subscription.pk, subscription.business_id,
    )
    return subscription
