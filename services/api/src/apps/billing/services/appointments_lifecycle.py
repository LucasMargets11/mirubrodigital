"""Commercial lifecycle for MiRubro Turnos SubscriptionV2 records."""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.billing.appointments_plans import (
    AUTOMATIONS,
    EXTRA_PROFESSIONAL,
    get_appointments_plan_config,
)

GRACE_PERIOD = timedelta(days=3)

logger = logging.getLogger(__name__)


def _ai_change_conflict(subscription, target_plan_code: str, *, at):
    """PROD-02F5.1: the shared AI rule for a change INTO Turnos IA (None if no change of source)."""
    from apps.billing.services.ai_commercial_rules import find_ai_commercial_conflict

    if subscription.plan_code == target_plan_code:
        return None
    return find_ai_commercial_conflict(
        business_id=subscription.business_id, service_type=subscription.service_type,
        plan_code=target_plan_code, starts_at=at, exclude_subscription_id=subscription.pk,
    )


def block_change_for_ai_conflict(pending, conflict) -> None:
    """Hold a change that would open an incompatible AI source (existing 'blocked' state)."""
    pending.status = 'blocked'
    pending.requires_resolution = True
    pending.resolution_details = {
        'code': conflict.code,
        'conflicting_subscription_id': (
            str(conflict.conflicting_subscription_id) if conflict.conflicting_subscription_id else None
        ),
    }
    pending.save(update_fields=['status', 'requires_resolution', 'resolution_details', 'updated_at'])
    logger.error(
        'appointments_change_blocked code=%s pending_change=%s subscription=%s conflicting=%s',
        conflict.code, pending.pk, pending.subscription_v2_id, conflict.conflicting_subscription_id,
    )


class AppointmentsLifecycleError(ValueError):
    pass


def prorate_upgrade_amount(
    *,
    current_amount: int | Decimal,
    target_amount: int | Decimal,
    period_start,
    period_end,
    at=None,
) -> int:
    """Return the remaining-period price difference in whole ARS pesos."""
    at = at or timezone.now()
    if period_end <= period_start:
        raise ValueError('The current billing period must have a positive duration.')
    difference = max(Decimal('0'), Decimal(target_amount) - Decimal(current_amount))
    if difference == 0 or at >= period_end:
        return 0
    total = period_end - period_start
    remaining = period_end - max(at, period_start)

    def seconds(delta):
        return (
            Decimal(delta.days * 86400 + delta.seconds)
            + Decimal(delta.microseconds) / Decimal(1_000_000)
        )

    amount = difference * seconds(remaining) / seconds(total)
    return int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def is_complimentary_grant(subscription) -> bool:
    """
    Platform-admin complimentary access (ADMIN-CLIENTES 01A): manual + trialing
    with no trial_ends_at. Same split as billing.runtime._v2_grants_access:
    a row with trial_ends_at is a trial (S7A keeps trials fail-closed); the
    complimentary window is current_period_start/end instead.
    """
    from apps.billing.models import SubscriptionV2

    return (
        subscription.provider == SubscriptionV2.Provider.MANUAL
        and subscription.status == SubscriptionV2.Status.TRIALING
        and subscription.trial_ends_at is None
    )


def complimentary_grant_active(subscription, *, at=None) -> bool:
    """
    True while a complimentary grant is inside its bonified window
    [current_period_start, current_period_end) — the same end rule as
    billing.runtime._v2_grants_access (end instant excluded), plus the start:
    a grant that has not started yet gives no access. Revoked grants are
    'canceled' and suspended ones are not 'trialing', so both stay out.
    Never applies to Mercado Pago trials.
    """
    at = at or timezone.now()
    if not is_complimentary_grant(subscription):
        return False
    start, end = subscription.current_period_start, subscription.current_period_end
    return start is not None and end is not None and start <= at < end


def subscription_lifecycle_access(subscription, *, at=None) -> bool:
    """Lifecycle-only access; cancellation-at-period-end expires at the boundary."""
    from apps.billing.models import SubscriptionV2

    at = at or timezone.now()
    if subscription.service_type != SubscriptionV2.ServiceType.APPOINTMENTS:
        return False
    if subscription.cancel_at_period_end and subscription.current_period_end:
        if subscription.current_period_end <= at:
            return False
    if subscription.status == SubscriptionV2.Status.ACTIVE:
        return True
    if complimentary_grant_active(subscription, at=at):
        return True
    return (
        subscription.status == SubscriptionV2.Status.PAST_DUE
        and subscription.grace_until is not None
        and subscription.grace_until >= at
    )


def can_create_appointments(business, *, at=None) -> bool:
    subscription = _appointments_subscription(business)
    return subscription is not None and subscription_lifecycle_access(subscription, at=at)


def appointments_v2_allows_creation(business, *, at=None) -> bool | None:
    """Return None for legacy-only businesses so S6 does not migrate legacy access."""
    subscription = _appointments_subscription(business, include_canceled=True)
    if subscription is None:
        return None
    return subscription_lifecycle_access(subscription, at=at)


def can_send_appointments_automation(business, *, at=None) -> bool:
    from apps.billing.services.appointments import can_use_appointments_automations

    return can_use_appointments_automations(business, at=at)


def can_start_ai_conversation(business, *, at=None) -> bool:
    subscription = _current_subscription(business)
    if subscription is None or not subscription_lifecycle_access(subscription, at=at):
        return False
    try:
        from apps.billing.services.appointments import resolve_appointments_subscription_config

        return resolve_appointments_subscription_config(subscription).ai_enabled
    except ValidationError:
        return False


def effective_usage_tier(subscription) -> dict:
    """Expose the current commercial tier and its effective start for future S9."""
    return {
        'effective_usage_tier': subscription.usage_tier,
        'effective_from': (
            subscription.usage_tier_effective_from
            or subscription.current_period_start
        ),
    }


def usage_tier_change_context(*, previous_tier, effective_tier, effective_from) -> dict:
    """S9 contract: only unclosed overage may be re-evaluated at the new tier."""
    return {
        'previous_usage_tier': previous_tier,
        'effective_usage_tier': effective_tier,
        'effective_from': effective_from,
        'reevaluate_unclosed_overage': previous_tier != effective_tier,
        'closed_overage_is_mutable': False,
    }


def _current_subscription(business):
    return _appointments_subscription(business)


def _appointments_subscription(business, *, include_canceled=False):
    from apps.billing.models import SubscriptionV2

    queryset = SubscriptionV2.objects.filter(
        business=business,
        service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
    )
    if not include_canceled:
        queryset = queryset.exclude(status=SubscriptionV2.Status.CANCELED)
    return queryset.order_by('-created_at').first()


def _current_configuration(subscription) -> dict:
    from apps.billing.services.appointments import resolve_appointments_subscription_config

    config = resolve_appointments_subscription_config(subscription)
    active_addons = {
        addon.code: addon.quantity
        for addon in subscription.addons.filter(is_active=True)
    }
    return {
        'plan_code': config.plan_code,
        'usage_tier': config.usage_tier,
        'billing_cycle': subscription.billing_cycle or 'monthly',
        'automations': active_addons.get(AUTOMATIONS, 0) == 1,
        'extra_professionals': active_addons.get(EXTRA_PROFESSIONAL, 0),
    }


def _target_rank(plan_code: str, usage_tier: str | None) -> tuple[int, int]:
    plan_rank = {'appointments': 0, 'appointments_pro': 1, 'appointments_ai': 2}[plan_code]
    tier_rank = {'ai_300': 0, 'ai_1500': 1, 'ai_3000': 2, 'custom': 3}.get(usage_tier, 0)
    return plan_rank, tier_rank if plan_code == 'appointments_ai' else 0


def _snapshot(config: dict) -> dict:
    return {
        'addons': {AUTOMATIONS: int(config['automations'])},
        'quantities': {EXTRA_PROFESSIONAL: config['extra_professionals']},
    }


def quote_appointments_change(*, subscription, target: dict, at=None) -> dict:
    from apps.billing.services.appointments_checkout import quote_appointments

    at = at or timezone.now()
    current = _current_configuration(subscription)
    target = {
        'plan_code': target.get('plan_code', current['plan_code']),
        'usage_tier': target.get('usage_tier', current['usage_tier']),
        'billing_cycle': target.get('billing_cycle', current['billing_cycle']),
        'automations': target.get('automations', current['automations']),
        'extra_professionals': target.get(
            'extra_professionals', current['extra_professionals'],
        ),
    }
    current_quote = quote_appointments(
        plan_code=current['plan_code'],
        usage_tier=current['usage_tier'],
        billing_cycle=current['billing_cycle'],
        automations=current['automations'],
        extra_professionals=current['extra_professionals'],
    )
    target_quote = quote_appointments(**target)
    target_rank = _target_rank(target['plan_code'], target['usage_tier'])
    current_rank = _target_rank(current['plan_code'], current['usage_tier'])
    is_downgrade = target_rank < current_rank or (
        target_rank == current_rank
        and target_quote['total_amount'] < current_quote['total_amount']
    )
    cycle_change = target['billing_cycle'] != current['billing_cycle']
    if cycle_change:
        effective_at = subscription.current_period_end
        if effective_at is None:
            raise AppointmentsLifecycleError('A current period end is required to quote a cycle change.')
        amount = target_quote['total_amount']
        kind = 'billing_cycle'
    else:
        if not is_downgrade:
            if subscription.current_period_start is None or subscription.current_period_end is None:
                raise AppointmentsLifecycleError('The current billing period is incomplete.')
            amount = prorate_upgrade_amount(
                current_amount=current_quote['total_amount'],
                target_amount=target_quote['total_amount'],
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end,
                at=at,
            )
            effective_at = at
            kind = 'upgrade'
        else:
            effective_at = subscription.current_period_end
            amount = target_quote['total_amount']
            kind = 'downgrade'
    next_renewal = None
    if effective_at is not None and cycle_change:
        from apps.billing.services.appointments_checkout import appointments_period_end

        next_renewal = appointments_period_end(effective_at, target['billing_cycle'])
    checkout_items = []
    if kind == 'upgrade' and amount > 0:
        checkout_items = [{
            'code': 'appointments_proration',
            'description': 'Diferencia proporcional de actualización de Turnos',
            'quantity': 1,
            'unit_price': amount,
            'total': amount,
        }]
    return {
        'current_plan_code': current['plan_code'],
        'current_usage_tier': current['usage_tier'],
        'current_billing_cycle': current['billing_cycle'],
        'current_configuration': current,
        'target': target,
        'kind': kind,
        'is_downgrade': is_downgrade,
        'current_amount': current_quote['total_amount'],
        'target_amount': target_quote['total_amount'],
        'amount_due_now': amount if kind == 'upgrade' else 0,
        'amount_at_effective_date': amount if kind != 'upgrade' else target_quote['total_amount'],
        'effective_at': effective_at,
        'next_renewal_at': next_renewal,
        'line_items': target_quote['line_items'],
        'checkout_line_items': checkout_items,
        'proration': {
            'current_amount': current_quote['total_amount'],
            'target_amount': target_quote['total_amount'],
            'amount_due_now': amount if kind == 'upgrade' else 0,
            'period_start': subscription.current_period_start,
            'period_end': subscription.current_period_end,
            'calculated_at': at,
        },
        'quote': target_quote,
    }


@transaction.atomic
def request_appointments_change(*, business, user, target: dict, at=None):
    """Persist an explicit quote; upgrades apply now after payment, others at renewal."""
    from apps.appointments.services.professional_quota import count_active_professionals
    from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
    from apps.billing.services.appointments_checkout import quote_appointments

    at = at or timezone.now()
    from apps.business.models import Business

    Business.objects.select_for_update().get(pk=business.pk)
    subscription = (
        SubscriptionV2.objects.select_for_update()
        .filter(business=business, service_type=SubscriptionV2.ServiceType.APPOINTMENTS)
        .exclude(status=SubscriptionV2.Status.CANCELED)
        .order_by('-created_at')
        .first()
    )
    if subscription is None or not subscription_lifecycle_access(subscription, at=at):
        raise AppointmentsLifecycleError('An accessible Turnos subscription is required.')
    if subscription.status != SubscriptionV2.Status.ACTIVE:
        raise AppointmentsLifecycleError('Plan changes are unavailable during payment grace.')
    if subscription.cancel_at_period_end:
        raise AppointmentsLifecycleError('Undo the scheduled cancellation before changing the plan.')

    open_changes = list(
        PendingSubscriptionChange.objects.select_for_update().filter(
            subscription_v2=subscription,
            status__in=('pending_payment', 'scheduled', 'blocked'),
        )
    )
    if any(change.status == 'pending_payment' for change in open_changes):
        raise AppointmentsLifecycleError('A Turnos upgrade payment is already pending.')

    quote = quote_appointments_change(subscription=subscription, target=target, at=at)
    target_config = quote['target']
    conflict = _ai_change_conflict(subscription, target_config['plan_code'], at=at)
    if conflict is not None:
        raise conflict
    if (
        target_config == quote['current_configuration']
    ):
        raise AppointmentsLifecycleError('The requested Turnos configuration is unchanged.')
    for existing in open_changes:
        existing.status = 'canceled'
        existing.save(update_fields=['status', 'updated_at'])
    target_plan = get_appointments_plan_config(
        target_config['plan_code'], target_config['usage_tier'],
    )
    future_limit = target_config['extra_professionals'] + target_plan.included_professionals
    active_count = count_active_professionals(business)
    resolution = {}
    if quote['is_downgrade'] and active_count > future_limit:
        resolution = {
            'current_active_count': active_count,
            'future_limit': future_limit,
            'excess_count': active_count - future_limit,
        }

    snapshot = _snapshot(target_config)
    is_scheduled = quote['kind'] != 'upgrade'
    amount = (
        quote['amount_due_now'] if not is_scheduled
        else quote['amount_at_effective_date']
    )
    pending = PendingSubscriptionChange.objects.create(
        business=business,
        user=user,
        subscription_v2=subscription,
        target_plan_code=target_config['plan_code'],
        target_usage_tier=target_config['usage_tier'],
        billing_cycle=target_config['billing_cycle'],
        config_snapshot=snapshot,
        line_items=quote['line_items'],
        total_amount=amount,
        requires_checkout=not is_scheduled and amount > 0,
        is_upgrade=not is_scheduled,
        is_downgrade=quote['is_downgrade'],
        scheduled_for=quote['effective_at'] if is_scheduled else None,
        requires_resolution=bool(resolution),
        resolution_details=resolution,
        status=(
            'blocked' if resolution
            else 'scheduled' if is_scheduled
            else 'pending_payment' if amount > 0
            else 'processing'
        ),
    )
    quote['pending_change_id'] = str(pending.pk)
    quote['requires_checkout'] = pending.requires_checkout
    quote['requires_resolution'] = pending.requires_resolution
    quote['resolution_details'] = pending.resolution_details
    return pending, quote


@transaction.atomic
def apply_appointments_change(pending, *, payment_id: str | None = None, at=None) -> bool:
    """Apply a persisted Turnos target once, retaining existing add-on rows."""
    from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
    from apps.business.models import Business
    from apps.business.models import SubscriptionAddon

    at = at or timezone.now()
    initial = PendingSubscriptionChange.objects.select_related('subscription_v2').get(
        pk=pending.pk,
    )
    if initial.subscription_v2_id is None:
        raise AppointmentsLifecycleError('A SubscriptionV2 owner is required.')
    Business.objects.select_for_update().get(pk=initial.subscription_v2.business_id)
    subscription = SubscriptionV2.objects.select_for_update().get(
        pk=initial.subscription_v2_id,
    )
    pending = PendingSubscriptionChange.objects.select_for_update().get(pk=pending.pk)
    if pending.status == 'completed':
        return False
    if pending.requires_resolution:
        raise AppointmentsLifecycleError('Resolve the professional excess before applying this change.')
    if pending.subscription_v2_id is None:
        raise AppointmentsLifecycleError('A SubscriptionV2 owner is required.')
    conflict = _ai_change_conflict(subscription, pending.target_plan_code, at=at)
    if conflict is not None:
        block_change_for_ai_conflict(pending, conflict)
        return False
    old_tier = subscription.usage_tier
    subscription.plan_code = pending.target_plan_code
    subscription.usage_tier = pending.target_usage_tier
    subscription.billing_cycle = pending.billing_cycle
    subscription.price_snapshot = {
        **(subscription.price_snapshot or {}),
        'plan_code': pending.target_plan_code,
        'usage_tier': pending.target_usage_tier,
        'billing_cycle': pending.billing_cycle,
        'line_items': pending.line_items,
        'total_amount': sum(item['total'] for item in pending.line_items),
        'currency': 'ARS',
    }
    if old_tier != subscription.usage_tier:
        subscription.usage_tier_effective_from = at
    subscription.save(update_fields=[
        'plan_code', 'usage_tier', 'billing_cycle', 'price_snapshot',
        'usage_tier_effective_from', 'updated_at',
    ])
    addons = pending.config_snapshot.get('addons', {})
    quantities = pending.config_snapshot.get('quantities', {})
    _upsert_addon(
        SubscriptionAddon, subscription, AUTOMATIONS,
        addons.get(AUTOMATIONS, 0), is_active=bool(addons.get(AUTOMATIONS, 0)),
    )
    _upsert_addon(
        SubscriptionAddon, subscription, EXTRA_PROFESSIONAL,
        quantities.get(EXTRA_PROFESSIONAL, 0), is_active=True,
    )
    pending.status = 'completed'
    pending.applied_at = at
    if payment_id is not None:
        pending.mp_payment_id = payment_id
    pending.save(update_fields=['status', 'applied_at', 'mp_payment_id', 'updated_at'])
    return True


@transaction.atomic
def prepare_appointments_provider_change(pending) -> bool:
    """Set Mercado Pago's next recurring charge without changing the paid period."""
    from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
    from apps.billing.mp_service import MercadoPagoService
    from apps.business.models import Business

    initial = PendingSubscriptionChange.objects.select_related('subscription_v2').get(
        pk=pending.pk,
    )
    if initial.subscription_v2_id is None:
        raise AppointmentsLifecycleError('A SubscriptionV2 owner is required.')
    Business.objects.select_for_update().get(pk=initial.subscription_v2.business_id)
    subscription = SubscriptionV2.objects.select_for_update().get(
        pk=initial.subscription_v2_id,
    )
    pending = PendingSubscriptionChange.objects.select_for_update().get(pk=pending.pk)
    # PROD-02F5.1: never reprice Mercado Pago towards an incompatible AI source.
    conflict = _ai_change_conflict(subscription, pending.target_plan_code, at=timezone.now())
    if conflict is not None:
        raise conflict
    if subscription.provider == SubscriptionV2.Provider.MANUAL:
        return False
    if subscription.provider != SubscriptionV2.Provider.MERCADOPAGO:
        raise AppointmentsLifecycleError('This Turnos provider does not support lifecycle changes.')
    if not subscription.provider_sub_id:
        raise AppointmentsLifecycleError('Mercado Pago subscription ID is missing.')
    start_date = pending.scheduled_for or subscription.current_period_end
    if start_date is None:
        raise AppointmentsLifecycleError('A period end is required to schedule recurring billing.')
    amount = sum(item['total'] for item in pending.line_items)
    frequency = 12 if pending.billing_cycle == 'yearly' else 1
    MercadoPagoService().update_preapproval(
        subscription.provider_sub_id,
        {
            'auto_recurring': {
                'transaction_amount': amount,
                'currency_id': 'ARS',
                'frequency': frequency,
                'frequency_type': 'months',
                'start_date': start_date.isoformat(),
            },
        },
    )
    return True


@transaction.atomic
def resolve_professional_excess(pending, *, at=None):
    """Mark a blocked downgrade ready after the owner has reduced active count."""
    from apps.appointments.services.professional_quota import count_active_professionals
    from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
    from apps.business.models import Business

    at = at or timezone.now()
    initial = PendingSubscriptionChange.objects.select_related('subscription_v2').get(
        pk=pending.pk,
    )
    if initial.subscription_v2_id is None:
        raise AppointmentsLifecycleError('A SubscriptionV2 owner is required.')
    Business.objects.select_for_update().get(
        pk=initial.subscription_v2.business_id,
    )
    subscription = SubscriptionV2.objects.select_for_update().get(
        pk=initial.subscription_v2_id,
    )
    pending = PendingSubscriptionChange.objects.select_for_update().get(pk=pending.pk)
    if pending.status != 'blocked' or not pending.requires_resolution:
        raise AppointmentsLifecycleError('This pending change is not blocked for resolution.')
    target_config = get_appointments_plan_config(
        pending.target_plan_code, pending.target_usage_tier,
    )
    future_limit = target_config.included_professionals + pending.config_snapshot.get(
        'quantities', {},
    ).get(EXTRA_PROFESSIONAL, 0)
    active_count = count_active_professionals(subscription.business)
    if active_count > future_limit:
        pending.resolution_details = {
            'current_active_count': active_count,
            'future_limit': future_limit,
            'excess_count': active_count - future_limit,
        }
        pending.save(update_fields=['resolution_details', 'updated_at'])
        return pending
    if pending.scheduled_for is None or pending.scheduled_for <= at:
        pending.scheduled_for = subscription.current_period_end
    pending.status = 'scheduled'
    pending.requires_resolution = False
    pending.resolution_details = {}
    pending.save(update_fields=[
        'status', 'requires_resolution', 'resolution_details', 'scheduled_for', 'updated_at',
    ])
    return pending


def _upsert_addon(model, subscription, code, quantity, *, is_active):
    addon = model.objects.filter(
        subscription_v2=subscription,
        code=code,
    ).first()
    if addon is None:
        if quantity == 0:
            return
        addon = model(
            subscription_v2=subscription,
            code=code,
            quantity=quantity,
            is_active=is_active,
        )
    else:
        addon.quantity = quantity
        addon.is_active = is_active
        addon.deactivated_at = None if is_active else timezone.now()
    addon.save()


@transaction.atomic
def apply_appointments_renewal(*, subscription, invoice_event) -> bool:
    """Advance one paid period and apply a valid scheduled change at most once."""
    from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
    from apps.business.models import Business

    Business.objects.select_for_update().get(pk=subscription.business_id)
    subscription = SubscriptionV2.objects.select_for_update().get(pk=subscription.pk)
    payment_id = str(invoice_event.provider_authorized_payment_id)
    if subscription.last_renewal_payment_id == payment_id:
        return False
    if subscription.status == SubscriptionV2.Status.CANCELED or subscription.cancel_at_period_end:
        return False
    if subscription.current_period_end is None:
        return False
    boundary = subscription.current_period_end
    pending = (
        PendingSubscriptionChange.objects.select_for_update()
        .filter(
            subscription_v2=subscription,
            status__in=('scheduled', 'blocked'),
            scheduled_for__lte=boundary,
        )
        .order_by('created_at')
        .first()
    )
    if subscription.provider == SubscriptionV2.Provider.MERCADOPAGO:
        expected_amount = (
            sum(item['total'] for item in pending.line_items)
            if pending is not None and pending.status == 'scheduled'
            else (subscription.price_snapshot or {}).get('total_amount')
        )
        if expected_amount is not None:
            from decimal import InvalidOperation
            from apps.billing.webhook_lifecycle import WebhookPermanentError

            try:
                actual_amount = Decimal(str(invoice_event.amount))
                expected_amount = Decimal(str(expected_amount))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise WebhookPermanentError(
                    'appointments_renewal_amount_invalid',
                    'Turnos renewal amount is missing or invalid.',
                ) from exc
            if actual_amount != expected_amount or invoice_event.currency != 'ARS':
                raise WebhookPermanentError(
                    'appointments_renewal_amount_mismatch',
                    'Renewal payment does not match the stored Turnos recurring amount.',
                )
    if pending is not None:
        target = get_appointments_plan_config(pending.target_plan_code, pending.target_usage_tier)
        from apps.appointments.services.professional_quota import count_active_professionals

        future_limit = target.included_professionals + pending.config_snapshot.get(
            'quantities', {},
        ).get(EXTRA_PROFESSIONAL, 0)
        active_count = count_active_professionals(subscription.business)
        if active_count > future_limit:
            pending.status = 'blocked'
            pending.requires_resolution = True
            pending.resolution_details = {
                'current_active_count': active_count,
                'future_limit': future_limit,
                'excess_count': active_count - future_limit,
            }
            pending.save(update_fields=[
                'status', 'requires_resolution', 'resolution_details', 'updated_at',
            ])
        elif pending.status == 'scheduled':
            pending.status = 'scheduled'
            pending.requires_resolution = False
            pending.resolution_details = {}
            pending.save(update_fields=[
                'status', 'requires_resolution', 'resolution_details', 'updated_at',
            ])
            if apply_appointments_change(pending, at=boundary):
                subscription.refresh_from_db()

    from apps.billing.services.appointments_checkout import appointments_period_end

    start = boundary
    end = appointments_period_end(start, subscription.billing_cycle or 'monthly')
    subscription.current_period_start = start
    subscription.current_period_end = end
    subscription.status = SubscriptionV2.Status.ACTIVE
    subscription.is_active = True
    subscription.grace_started_at = None
    subscription.grace_until = None
    subscription.suspended_at = None
    subscription.last_renewal_payment_id = payment_id
    subscription.save(update_fields=[
        'current_period_start', 'current_period_end', 'status', 'is_active',
        'grace_started_at', 'grace_until', 'suspended_at',
        'last_renewal_payment_id', 'updated_at',
    ])
    return True


@transaction.atomic
def record_appointments_payment_failure(*, subscription, at=None) -> bool:
    from apps.billing.models import SubscriptionV2

    at = at or timezone.now()
    subscription = SubscriptionV2.objects.select_for_update().get(pk=subscription.pk)
    if subscription.status not in (
        SubscriptionV2.Status.ACTIVE,
        SubscriptionV2.Status.PAST_DUE,
    ):
        return False
    if subscription.status == SubscriptionV2.Status.PAST_DUE and subscription.grace_until:
        return False
    subscription.status = SubscriptionV2.Status.PAST_DUE
    subscription.retry_count += 1
    subscription.grace_started_at = at
    subscription.grace_until = at + GRACE_PERIOD
    subscription.save(update_fields=[
        'status', 'retry_count', 'grace_started_at', 'grace_until', 'updated_at',
    ])
    return True
