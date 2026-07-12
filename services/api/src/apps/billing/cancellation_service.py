"""
billing/cancellation_service.py — Domain logic for subscription cancellation.

Responsibilities:
  - Schedule cancellation (set cancel_at_period_end, cancel_requested_at, etc.)
  - Undo a scheduled cancellation
  - Execute a scheduled cancellation against MercadoPago
  - Immediate administrative cancellation (admin-panel initiated)
  - Validate business rules (permissions, state, timing)

All MP interaction is delegated to MercadoPagoService.
"""
from __future__ import annotations

import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .models import SubscriptionV2
from .mp_service import (
    MercadoPagoService,
    MercadoPagoCancelError,
    MercadoPagoPreapprovalNotFound,
    ProviderSubscriptionNotFound,
    MercadoPagoAuthError,
    normalize_mp_subscription_status,
    _mask_preapproval_id,
)

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

    # Notify internal ADMIN operations team — fire-and-forget, never re-raises.
    try:
        from apps.billing.email_helpers import send_admin_cancellation_request_received_email
        send_admin_cancellation_request_received_email(subscription)
    except Exception:
        logger.exception(
            "[cancellation] send_admin_cancellation_request_received_email failed "
            "for sub=%s — cancellation remains scheduled.",
            subscription.pk,
        )

    # Admin in-app notification — fire-and-forget, never re-raises.
    try:
        from apps.accounts.admin_notification_service import create_admin_notification
        create_admin_notification(
            notif_type='billing_cancel_request',
            severity='warning',
            target_role='operations',
            title='Solicitud de baja recibida',
            message=f'{subscription.business.name} solicit\u00f3 la baja de su suscripci\u00f3n.',
            business=subscription.business,
            related_object_type='subscription',
            related_object_id=str(subscription.id),
            action_url=f'/admin/suscripciones/{subscription.id}',
            metadata={
                'plan_code': subscription.plan_code,
                'service_type': subscription.service_type,
            },
            dedupe_window_seconds=86400,
        )
    except Exception:
        logger.exception(
            '[cancellation] create_admin_notification billing_cancel_request failed '
            'for sub=%s — cancellation remains scheduled.',
            subscription.pk,
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
                {"status": "canceled"},
            )
            logger.info(
                "[cancellation] MP preapproval canceled id=%s sub=%s",
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

    # Notify the owner — fire-and-forget, never re-raises.
    try:
        from apps.billing.email_helpers import send_cancellation_confirmed_email
        send_cancellation_confirmed_email(subscription)
    except Exception as exc:
        logger.exception(
            "[cancellation] send_cancellation_confirmed_email failed for sub=%s: %s",
            subscription.pk, exc,
        )

    return subscription


# ── Statuses that an admin can immediately cancel ─────────────────────────────
ADMIN_CANCELLABLE_STATUSES = frozenset({
    SubscriptionV2.Status.ACTIVE,
    SubscriptionV2.Status.TRIALING,
    SubscriptionV2.Status.PAST_DUE,
    SubscriptionV2.Status.SUSPENDED,
})


def cancel_subscription_immediately(
    *,
    subscription: SubscriptionV2,
    canceled_by,
    reason: str,
    mp_service: MercadoPagoService | None = None,
) -> dict:
    """
    Immediately cancel a subscription from the admin panel.

    This is the single source of truth for admin-initiated cancellations.
    It performs the following steps atomically with proper concurrency control:

      1. Pre-flight validation (no lock).
      2. Short atomic tx: acquire row lock, re-validate state, read provider_sub_id.
      3. Call Mercado Pago cancel_preapproval() — OUTSIDE the transaction.
      4. Atomic tx: write local state, revert Business to onboarding, log audit.

    Idempotent: if the subscription is already CANCELED, returns a success dict
    without calling Mercado Pago again.

    Security:
      - provider_sub_id is always read from the database (never accepted from caller).
      - The access token is never logged.
      - preapproval_id is logged in masked form only.

    Args:
        subscription: The SubscriptionV2 to cancel.
        canceled_by:  The User (platform admin) performing the cancellation.
        reason:       Human-readable reason; stored in cancel_reason.
        mp_service:   Optional MercadoPagoService instance (for testing / DI).

    Returns:
        dict with keys:
            subscription_id, business_id, previous_status, status,
            provider_status, is_active, canceled_at

    Raises:
        CancellationError: subscription state is not cancellable.
        ProviderSubscriptionNotFound: MP cannot locate the preapproval; local unchanged.
        MercadoPagoAuthError: MP returned 401/403; local unchanged.
        MercadoPagoCancelError: any other unconfirmed MP error; local unchanged.
    """
    # ── 0. Idempotency fast-path (no lock needed) ──────────────────────────
    if subscription.status == SubscriptionV2.Status.CANCELED:
        logger.info(
            "[admin_cancel] Already canceled sub=%s — idempotent no-op.",
            subscription.pk,
        )
        return _build_cancel_result(subscription, subscription.status, 'canceled')

    # ── 1. Pre-flight state check ──────────────────────────────────────────
    if subscription.status not in ADMIN_CANCELLABLE_STATUSES:
        raise CancellationError(
            f'No se puede cancelar una suscripción en estado '
            f'"{subscription.get_status_display()}". '
            f'Solo se puede cancelar en estado: activa, trialing, pago vencido o suspendida.'
        )

    # ── 2. Short atomic tx: lock row + validate + read preapproval_id ─────
    with transaction.atomic():
        locked = (
            SubscriptionV2.objects
            .select_for_update()
            .get(pk=subscription.pk)
        )

        # Re-check after acquiring the lock — another concurrent process may
        # have canceled the subscription between steps 0 and 2.
        if locked.status == SubscriptionV2.Status.CANCELED:
            logger.info(
                "[admin_cancel] Already canceled (locked re-check) sub=%s — no-op.",
                locked.pk,
            )
            return _build_cancel_result(locked, locked.status, 'canceled')

        if locked.status not in ADMIN_CANCELLABLE_STATUSES:
            raise CancellationError(
                f'Estado incompatible detectado al obtener el bloqueo: '
                f'"{locked.get_status_display()}".'
            )

        previous_status = locked.status
        preapproval_id = locked.provider_sub_id
        is_mp = locked.provider == SubscriptionV2.Provider.MERCADOPAGO

        if is_mp and not preapproval_id:
            raise CancellationError(
                'La suscripción no tiene identificador externo de Mercado Pago '
                '(provider_sub_id vacío). No se puede cancelar automáticamente. '
                'Verificá el estado manualmente en el panel de Mercado Pago.'
            )
    # Transaction ends here — row lock is released.

    # ── 3. Cancel at Mercado Pago (OUTSIDE transaction to avoid long hold) ─
    provider_status = 'canceled'
    if is_mp and preapproval_id:
        svc = mp_service or MercadoPagoService()
        masked = _mask_preapproval_id(preapproval_id)
        logger.info(
            "[admin_cancel] Requesting MP cancel. "
            "sub=%s business=%s preapproval=%s admin=%s previous_status=%s",
            locked.pk, locked.business_id, masked, canceled_by.pk, previous_status,
        )
        # Raises MercadoPagoCancelError on any unrecoverable MP error.
        # cancel_preapproval() already normalizes the status via normalize_mp_subscription_status().
        mp_response = svc.cancel_preapproval(preapproval_id)
        # Normalize: MP may return 'cancelled' (British) or 'canceled' (American).
        provider_status = normalize_mp_subscription_status(mp_response.get('status', 'canceled'))

    # ── 4. Atomic write: update local state ───────────────────────────────
    now = timezone.now()
    with transaction.atomic():
        locked = (
            SubscriptionV2.objects
            .select_for_update()
            .select_related('business')
            .get(pk=subscription.pk)
        )

        # Idempotency: another process may have finished between steps 2 and 4.
        if locked.status == SubscriptionV2.Status.CANCELED:
            logger.info(
                "[admin_cancel] Sub already canceled in write tx sub=%s — idempotent.",
                locked.pk,
            )
            return _build_cancel_result(locked, previous_status, provider_status)

        locked.status = SubscriptionV2.Status.CANCELED
        locked.is_active = False
        locked.canceled_at = now
        locked.cancel_reason = reason
        locked.canceled_by = canceled_by
        locked.save(update_fields=[
            'status', 'is_active', 'canceled_at',
            'cancel_reason', 'canceled_by', 'updated_at',
        ])

        # Revert Business to onboarding so the client can re-subscribe.
        _revert_business_for_admin_cancel(locked)

        # Audit log — never raises, written inside the same transaction.
        _log_admin_cancel_audit(
            subscription=locked,
            canceled_by=canceled_by,
            previous_status=previous_status,
            provider_status=provider_status,
            reason=reason,
            preapproval_id=preapproval_id if is_mp else None,
        )

    logger.info(
        "[admin_cancel] Subscription canceled successfully. "
        "sub=%s business=%s previous_status=%s admin=%s",
        locked.pk, locked.business_id, previous_status, canceled_by.pk,
    )

    return _build_cancel_result(locked, previous_status, provider_status)


# ── Private helpers ───────────────────────────────────────────────────────────

def _revert_business_for_admin_cancel(subscription: SubscriptionV2) -> None:
    """
    Set Business.status to 'onboarding' after an admin cancellation, unless:
      - The business already has other non-canceled subscriptions (other services).
      - The business is already in 'onboarding' or 'canceled' status.

    'onboarding' is chosen so the client can re-subscribe without operator intervention.
    """
    business = subscription.business
    if business is None:
        return

    # Check for other active/non-terminal subscriptions for this business
    other_active = (
        SubscriptionV2.objects
        .filter(business_id=business.pk)
        .exclude(pk=subscription.pk)
        .exclude(status=SubscriptionV2.Status.CANCELED)
        .exists()
    )

    if other_active:
        logger.info(
            "[admin_cancel] Business=%s has other active subscriptions — "
            "skipping business status revert.",
            business.pk,
        )
        return

    if business.status in ('onboarding', 'canceled'):
        return

    old_biz_status = business.status
    business.status = 'onboarding'
    business.save(update_fields=['status'])
    logger.info(
        "[admin_cancel] Business=%s status %s → onboarding",
        business.pk, old_biz_status,
    )
    # Cancel legacy business.Subscription if still active so that the
    # runtime fallback path (resolve_subscription → legacy) cannot grant
    # access after the SubscriptionV2 has been canceled.
    _cancel_legacy_subscription_if_active(business)


def _cancel_legacy_subscription_if_active(business) -> None:
    """
    Cancel the legacy business.Subscription if it is still 'active'.

    The billing runtime (runtime.resolve_subscription) falls back to the legacy
    business.Subscription when no usable SubscriptionV2 exists.  After an admin
    cancellation the V2 is excluded from the lookup (status=canceled), so an
    active legacy sub would still grant access via the fallback path.

    Canceling the legacy sub here closes that gap while remaining idempotent:
    if the sub is already 'canceled' or 'past_due', or if no legacy sub exists,
    this is a no-op.

    Only touches business.Subscription (the runtime-relevant legacy model).
    Does NOT modify billing.Subscription which is dead weight.
    """
    legacy_sub = getattr(business, 'subscription', None)
    if legacy_sub is None:
        return
    if legacy_sub.status == 'active':
        legacy_sub.status = 'canceled'
        legacy_sub.save(update_fields=['status', 'updated_at'])
        logger.info(
            "[admin_cancel] Legacy business.Subscription id=%s → canceled for Business=%s",
            legacy_sub.pk, business.pk,
        )

def _log_admin_cancel_audit(
    *,
    subscription: SubscriptionV2,
    canceled_by,
    previous_status: str,
    provider_status: str,
    reason: str,
    preapproval_id: str | None,
) -> None:
    """Write a platform audit log entry for an admin cancellation. Never raises."""
    try:
        from apps.accounts.platform_audit import log_platform_action
        log_platform_action(
            action='ADMIN_SUBSCRIPTION_CANCELED',
            actor=canceled_by,
            entity_type='subscription_v2',
            entity_id=str(subscription.id),
            business=subscription.business,
            details={
                'subscription_id': str(subscription.id),
                'business_id': subscription.business_id,
                'plan_code': subscription.plan_code,
                'service_type': subscription.service_type,
                'previous_status': previous_status,
                'new_status': SubscriptionV2.Status.CANCELED,
                'provider_status': provider_status,
                'reason': reason,
                'preapproval_id_masked': (
                    _mask_preapproval_id(preapproval_id) if preapproval_id else None
                ),
            },
        )
    except Exception:
        logger.exception(
            "[admin_cancel] Audit log failed for sub=%s — cancellation still applied.",
            subscription.pk,
        )


def _build_cancel_result(
    subscription: SubscriptionV2,
    previous_status: str,
    provider_status: str,
) -> dict:
    """Build the standardised result dict returned by cancel_subscription_immediately."""
    return {
        'subscription_id': str(subscription.id),
        'business_id': subscription.business_id,
        'previous_status': previous_status,
        'status': subscription.status,
        'provider_status': provider_status,
        'is_active': subscription.is_active,
        'canceled_at': (
            subscription.canceled_at.isoformat()
            if subscription.canceled_at else None
        ),
    }
