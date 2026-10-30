"""S8D: internal, immutable historical closure. No payment side effects."""
from __future__ import annotations

from datetime import datetime

from django.db import transaction

from apps.appointments.models import (
    AppointmentAIUsageCharge,
    AppointmentAIUsageSettlement,
    AppointmentAIUsageSettlementEntry,
)
from apps.appointments.services.ai_usage import (
    AIUsageUnavailable,
    _utc,
    resolve_ai_overage_statement,
    resolve_appointments_ai_usage_period,
)
from apps.billing.models import SubscriptionV2
from apps.business.models import Business


@transaction.atomic
def finalize_ai_usage_settlement(
    *, business: Business, subscription: SubscriptionV2,
    period_start: datetime, period_end: datetime, at: datetime,
) -> AppointmentAIUsageSettlement:
    """Close an explicit period using ledger evidence, not current access/pricing.

    The period tuple is the stable idempotency key (the UUID is its reference).
    The business lock follows S8A/S6 lock order and serializes closers with writers.
    """
    start, end, now = _utc(period_start), _utc(period_end), _utc(at)
    if end <= start or now < end:
        raise AIUsageUnavailable('Only an ended positive usage period can be finalized.')
    business = Business.objects.select_for_update().get(pk=business.pk)
    subscription = SubscriptionV2.objects.select_for_update().get(pk=subscription.pk)
    if subscription.business_id != business.pk:
        raise AIUsageUnavailable('The settlement subscription belongs to another business.')
    key = dict(
        business=business, subscription=subscription,
        usage_period_start=start, usage_period_end=end,
    )
    existing = AppointmentAIUsageSettlement.objects.filter(**key).first()
    if existing is not None and existing.status == 'finalized':
        return existing

    statement = resolve_ai_overage_statement(business, start, end, at=now)
    if statement['status'] != 'eligible_for_settlement':
        raise AIUsageUnavailable('The usage statement is not eligible for settlement.')
    charges = list(AppointmentAIUsageCharge.objects.filter(
        business=business, usage_period_start=start, usage_period_end=end,
    ).order_by('session_ordinal', 'pk'))
    if any(entry.subscription_id != subscription.pk for entry in charges):
        raise AIUsageUnavailable('The usage period has conflicting subscription evidence.')
    if not charges:
        # With no recorded terms, only the persisted anchor can prove the period.
        # Do not invent historical empty periods after an anchor has been lost.
        if resolve_appointments_ai_usage_period(subscription, at=start) != (start, end):
            raise AIUsageUnavailable('The empty usage period has no matching historical anchor.')
    if AppointmentAIUsageSettlementEntry.objects.filter(
        charge__in=charges,
    ).exclude(settlement=existing).exists():
        raise AIUsageUnavailable('A usage charge already belongs to another settlement.')

    values = dict(
        currency=statement['currency'],
        total_sessions=statement['total_sessions'],
        included_sessions_snapshot=statement['included_sessions'],
        overage_sessions=statement['overage_sessions'],
        overage_amount=statement['overage_amount'],
        terms_snapshot=[
            {
                'charge_id': str(entry.pk), 'session_id': str(entry.session_id),
                'usage_tier': entry.usage_tier, 'session_ordinal': entry.session_ordinal,
                'included_sessions_snapshot': entry.included_sessions_snapshot,
                'classification': entry.classification, 'unit_price': entry.unit_price,
                'amount': entry.amount, 'currency': entry.currency,
            }
            for entry in charges
        ],
    )
    if existing is None:
        settlement = AppointmentAIUsageSettlement.objects.create(**key, **values)
    else:
        settlement = existing
        for field, value in values.items():
            setattr(settlement, field, value)
        settlement.save(update_fields=list(values))
        settlement.entries.all().delete()
    AppointmentAIUsageSettlementEntry.objects.bulk_create([
        AppointmentAIUsageSettlementEntry(settlement=settlement, charge=entry)
        for entry in charges
    ])
    settlement.status = 'finalized'
    settlement.finalized_at = now
    settlement.save(update_fields=['status', 'finalized_at'])
    return settlement
