"""S8G offline closure: persisted usage evidence -> S8D settlement -> S8E intent."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.appointments.models import (
    AppointmentAIUsageBillingIntent,
    AppointmentAIUsageCharge,
    AppointmentAIUsageSession,
    AppointmentAIUsageSettlement,
)
from apps.appointments.services.ai_usage import (
    AIUsageUnavailable,
    _utc,
    resolve_appointments_ai_usage_period,
)
from apps.appointments.services.ai_usage_billing_intent import prepare_ai_usage_billing_intent
from apps.appointments.services.ai_usage_settlement import finalize_ai_usage_settlement
from apps.billing.models import SubscriptionV2
from apps.business.models import Business

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIUsageBillingPeriod:
    business_id: int
    subscription_id: uuid.UUID
    period_start: datetime
    period_end: datetime

    def scope(self) -> dict:
        return {
            'business_id': self.business_id,
            'subscription_id': self.subscription_id,
            'usage_period_start': self.period_start,
            'usage_period_end': self.period_end,
        }


@dataclass(frozen=True)
class AIUsagePeriodDiscovery:
    periods: tuple[AIUsageBillingPeriod, ...]
    skipped: int


class AIUsageBillingRunSummary(TypedDict):
    scanned: int
    settlements_created: int
    settlements_existing: int
    intents_created: int
    intents_existing: int
    skipped: int
    failed: int


def _log_period(level: int, period: AIUsageBillingPeriod, result: str, *,
                settlement_id: uuid.UUID | None = None,
                intent_id: uuid.UUID | None = None) -> None:
    logger.log(
        level,
        'AI usage billing business=%s subscription=%s start=%s end=%s '
        'settlement=%s intent=%s result=%s',
        period.business_id, period.subscription_id, period.period_start.isoformat(),
        period.period_end.isoformat(), settlement_id, intent_id, result,
    )


def discover_ai_usage_periods_ready_for_settlement(*, at: datetime) -> AIUsagePeriodDiscovery:
    """Find explicit ended periods, never extrapolate before/after persisted anchors.

    Discovery checks structural completeness, not amounts. S8D remains the sole
    authority for validating and finalizing historical economics under locks.
    """
    now = _utc(at)
    fields = ('business_id', 'subscription_id', 'usage_period_start', 'usage_period_end')
    recorded: set[AIUsageBillingPeriod] = set()
    for model in (AppointmentAIUsageSession, AppointmentAIUsageCharge, AppointmentAIUsageSettlement):
        rows = model.objects.filter(usage_period_end__lte=now)
        if model is AppointmentAIUsageSettlement:
            rows = rows.filter(status='pending')
        recorded.update(AIUsageBillingPeriod(*row) for row in rows.values_list(*fields).distinct())

    anchored: set[AIUsageBillingPeriod] = set()
    skipped = 0
    subscriptions = SubscriptionV2.objects.filter(
        service_type='appointments', plan_code='appointments_ai',
        current_period_start__lt=now, current_period_end__isnull=False,
    ).order_by('pk')
    for subscription in subscriptions.iterator():
        cursor = subscription.current_period_start
        end = subscription.current_period_end
        try:
            if end <= cursor:
                raise AIUsageUnavailable('Invalid persisted anchor.')
            while cursor < min(end, now):
                start, boundary = resolve_appointments_ai_usage_period(subscription, at=cursor)
                if start != cursor or boundary <= cursor or boundary > end:
                    raise AIUsageUnavailable('Ambiguous persisted subperiod.')
                if boundary > now:
                    break
                anchored.add(AIUsageBillingPeriod(subscription.business_id, subscription.pk, start, boundary))
                cursor = boundary
        except AIUsageUnavailable:
            skipped += 1
            logger.warning(
                'AI usage billing business=%s subscription=%s result=invalid_anchor',
                subscription.business_id, subscription.pk,
            )

    finalized = set(AppointmentAIUsageSettlement.objects.filter(
        status='finalized', usage_period_end__lte=now,
    ).values_list('business_id', 'usage_period_start', 'usage_period_end'))
    grouped: dict[tuple[int, datetime, datetime], set[AIUsageBillingPeriod]] = {}
    for period in recorded | anchored:
        key = (period.business_id, period.period_start, period.period_end)
        if key not in finalized:
            grouped.setdefault(key, set()).add(period)

    overlapping = set()
    active: list[tuple[int, datetime, datetime]] = []
    for key in sorted(set(grouped) | finalized):
        business_id, start, end = key
        active = [other for other in active if other[0] == business_id and other[2] > start]
        if active:
            overlapping.update(active)
            overlapping.add(key)
        active.append(key)

    ready = []
    for key in sorted(grouped):
        choices = grouped[key]
        period = min(choices, key=lambda item: str(item.subscription_id))
        sessions = AppointmentAIUsageSession.objects.filter(
            business_id=period.business_id, usage_period_start=period.period_start,
            usage_period_end=period.period_end,
        )
        subscription = SubscriptionV2.objects.filter(
            pk=period.subscription_id, business_id=period.business_id,
        ).first()
        has_sessions = sessions.exists()
        matches_anchor = period in anchored
        if not has_sessions and not matches_anchor and subscription is not None:
            # An explicit pending period can retain valid evidence after a plan change.
            try:
                matches_anchor = resolve_appointments_ai_usage_period(
                    subscription, at=period.period_start,
                ) == (period.period_start, period.period_end)
            except AIUsageUnavailable:
                matches_anchor = False
        if (
            len(choices) != 1
            or key in overlapping
            or period.period_end <= period.period_start
            or subscription is None
            or sessions.filter(economic_entry__isnull=True).exists()
            or (not has_sessions and not matches_anchor)
        ):
            skipped += 1
            _log_period(logging.WARNING, period, 'incomplete_or_ambiguous_evidence')
            continue
        ready.append(period)
    return AIUsagePeriodDiscovery(tuple(ready), skipped)


@transaction.atomic
def _finalize(period: AIUsageBillingPeriod, *, at: datetime) -> tuple[AppointmentAIUsageSettlement, bool]:
    # S8D/S8A lock order also makes created/existing counters accurate in races.
    business = Business.objects.select_for_update().get(pk=period.business_id)
    subscription = SubscriptionV2.objects.select_for_update().get(pk=period.subscription_id)
    existing = AppointmentAIUsageSettlement.objects.filter(**period.scope(), status='finalized').exists()
    settlement = finalize_ai_usage_settlement(
        business=business, subscription=subscription,
        period_start=period.period_start, period_end=period.period_end, at=at,
    )
    return settlement, not existing


@transaction.atomic
def _prepare(settlement: AppointmentAIUsageSettlement) -> tuple[AppointmentAIUsageBillingIntent, bool]:
    frozen = AppointmentAIUsageSettlement.objects.select_for_update().get(pk=settlement.pk)
    existing = AppointmentAIUsageBillingIntent.objects.filter(settlement=frozen).exists()
    return prepare_ai_usage_billing_intent(frozen), not existing


def process_due_ai_usage_billing(*, at: datetime | None = None) -> AIUsageBillingRunSummary:
    """Stop at preparation. No provider lookup, dispatch or remote reconciliation."""
    now = _utc(at if at is not None else timezone.now())
    discovery = discover_ai_usage_periods_ready_for_settlement(at=now)
    # Recovery is independent of discovery: finalized history must not be revalidated.
    repairs = [
        AIUsageBillingPeriod(*row)
        for row in AppointmentAIUsageSettlement.objects.filter(
            status='finalized', usage_period_end__lte=now, billing_intent__isnull=True,
        ).values_list('business_id', 'subscription_id', 'usage_period_start', 'usage_period_end')
    ]
    periods = sorted(
        set(discovery.periods) | set(repairs),
        key=lambda period: (period.business_id, period.period_start, str(period.subscription_id)),
    )
    summary: AIUsageBillingRunSummary = {
        'scanned': len(periods) + discovery.skipped,
        'settlements_created': 0, 'settlements_existing': 0,
        'intents_created': 0, 'intents_existing': 0,
        'skipped': discovery.skipped, 'failed': 0,
    }
    for period in periods:
        _log_period(logging.INFO, period, 'candidate')
        try:
            settlement, created = _finalize(period, at=now)
        except (AIUsageUnavailable, ObjectDoesNotExist, IntegrityError):
            summary['failed'] += 1
            _log_period(logging.WARNING, period, 'settlement_failed')
            continue
        summary['settlements_created' if created else 'settlements_existing'] += 1
        try:
            intent, created = _prepare(settlement)
        except (AIUsageUnavailable, ObjectDoesNotExist, IntegrityError):
            summary['failed'] += 1
            _log_period(logging.WARNING, period, 'intent_failed', settlement_id=settlement.pk)
            continue
        summary['intents_created' if created else 'intents_existing'] += 1
        _log_period(logging.INFO, period, 'prepared', settlement_id=settlement.pk, intent_id=intent.pk)
    logger.info('AI usage billing offline run summary=%s', summary)
    return summary
