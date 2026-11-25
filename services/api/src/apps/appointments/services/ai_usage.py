"""S8A metering, S8B admission and S8C economic snapshots; no payment integration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.appointments.models import AppointmentAIUsageCharge, AppointmentAIUsageSession
from apps.billing import canonical_pricing
from apps.billing.models import SubscriptionV2
from apps.billing.runtime import resolve_subscription
from apps.billing.services.appointments import resolve_appointments_subscription_config
from apps.billing.services.appointments_checkout import ManualContractRequired, appointments_period_end
from apps.billing.services.appointments_lifecycle import (
    complimentary_grant_active, is_complimentary_grant, subscription_lifecycle_access,
)

# Cycle used for a complimentary grant (billing_cycle=''): monthly usage
# periods anchored at the grant start and clipped to the grant end.
COMPLIMENTARY_CYCLE = 'complimentary'


def _usage_cycle(subscription: SubscriptionV2) -> str:
    if subscription.billing_cycle in ('monthly', 'yearly'):
        return subscription.billing_cycle
    if is_complimentary_grant(subscription):
        return COMPLIMENTARY_CYCLE
    return subscription.billing_cycle
from apps.business.models import Business
from apps.leads.models import LeadAgentState

SESSION_DURATION = timedelta(hours=24)

# PROD-02E1: Recepcionista IA is recognized as an AI source, but its
# consumption stays blocked until PROD-02E2 defines tier allowances and
# economics (and the billing pipeline covers it). Never unlimited.
RECEPTION_AI_CONSUMPTION_ENABLED = False


class AIUsageUnavailable(ValueError):
    """Unresolved or ineligible commercial/context data; never a plan fallback."""

    def __init__(self, message: str, *, reason: str = 'usage_unavailable') -> None:
        super().__init__(message)
        self.reason = reason


class AIUsageHardCapReached(AIUsageUnavailable):
    """The next session would exceed the usage month's permitted overage."""


def _utc(at: datetime) -> datetime:
    if not isinstance(at, datetime) or timezone.is_naive(at):
        raise AIUsageUnavailable('An explicit timezone-aware interaction time is required.')
    return at.astimezone(dt_timezone.utc)


def _reception_ai_usage_limit(subscription: SubscriptionV2) -> int:
    from apps.billing.reception_plans import resolve_reception_subscription_config

    try:
        config = resolve_reception_subscription_config(subscription)
    except ValidationError as exc:
        raise AIUsageUnavailable('Invalid Recepcionista configuration.', reason='invalid_tier') from exc
    if config.usage_tier == 'reception_custom':
        raise ManualContractRequired('custom usage requires manual commercial resolution.')
    included = config.usage_tier_config.get('included_conversations')
    if type(included) is not int or included <= 0:
        # An undefined allowance is never "unlimited".
        raise AIUsageUnavailable(
            'The Recepcionista tier has no defined conversation allowance.', reason='usage_policy_undefined',
        )
    if not RECEPTION_AI_CONSUMPTION_ENABLED:
        raise AIUsageUnavailable(
            'Recepcionista AI consumption is not enabled yet.', reason='usage_policy_undefined',
        )
    return included


def resolve_ai_usage_limit(subscription: SubscriptionV2) -> int:
    if subscription.service_type == 'reception' and subscription.plan_code == 'reception':
        return _reception_ai_usage_limit(subscription)
    if subscription.service_type != 'appointments' or subscription.plan_code != 'appointments_ai':
        raise AIUsageUnavailable('An effective canonical appointments_ai subscription is required.', reason='no_ai_entitlement')
    try:
        config = resolve_appointments_subscription_config(subscription)
    except ValidationError as exc:
        raise AIUsageUnavailable('Invalid appointments_ai configuration.', reason='invalid_tier') from exc
    if config.usage_tier == 'custom':
        raise ManualContractRequired('custom usage requires manual commercial resolution.')
    if not config.ai_enabled or config.usage_tier_config is None:
        raise AIUsageUnavailable('An explicit resolved AI usage tier is required.', reason='invalid_tier')
    included = config.usage_tier_config.get('included_conversations')
    if type(included) is not int or included <= 0:
        raise AIUsageUnavailable('The AI tier has no resolved included session allowance.')
    return included


def _monthly_boundary(anchor: datetime, offset: int) -> datetime:
    # S6 owns month arithmetic; retain the original day after short months.
    first = anchor.replace(day=1)
    for _ in range(offset):
        first = appointments_period_end(first, 'monthly')
    last_day = (appointments_period_end(first, 'monthly') - timedelta(days=1)).day
    return first.replace(day=min(anchor.day, last_day))


def resolve_appointments_ai_usage_period(
    subscription: SubscriptionV2, *, at: datetime,
) -> tuple[datetime, datetime]:
    at = _utc(at)
    if subscription.current_period_start is None or subscription.current_period_end is None:
        raise AIUsageUnavailable('The subscription renewal anchor is unresolved.')
    start = _utc(subscription.current_period_start)
    end = _utc(subscription.current_period_end)
    cycle = _usage_cycle(subscription)
    if end <= start or at < start or cycle not in ('monthly', 'yearly', COMPLIMENTARY_CYCLE):
        raise AIUsageUnavailable('The subscription billing period is invalid or historical.')
    if cycle == 'monthly' and at < end:
        return start, end
    if cycle == COMPLIMENTARY_CYCLE and at >= end:
        # No grace after a complimentary grant: the benefit simply ends.
        raise AIUsageUnavailable('The complimentary access has ended.', reason='suspended')
    # During S6 grace the next usage month still starts at the renewal boundary.
    anchor = end if at >= end else start
    offset = (at.year - anchor.year) * 12 + at.month - anchor.month
    period_start = _monthly_boundary(anchor, offset)
    if period_start > at:
        offset -= 1
        period_start = _monthly_boundary(anchor, offset)
    period_end = _monthly_boundary(anchor, offset + 1)
    if at < end:
        period_end = min(period_end, end)
    return period_start, period_end


def _locked_subscription(business: Business, *, at: datetime) -> SubscriptionV2:
    # PROD-02E1: one AI source per Business (billing.services.ai_source).
    # Recepcionista + Turnos IA fails closed; an eligible Recepcionista is the
    # source next to Turnos Base/Pro. Otherwise the original Turnos IA path
    # below runs unchanged (same checks, locks and reasons).
    from apps.billing.services.ai_source import (
        AMBIGUOUS_AI_SOURCE, RECEPTION_SOURCE, resolve_ai_source,
    )

    source = resolve_ai_source(business, at=at)
    if source.reason == AMBIGUOUS_AI_SOURCE:
        raise AIUsageUnavailable('More than one eligible AI source.', reason=AMBIGUOUS_AI_SOURCE)
    if source.source == RECEPTION_SOURCE:
        subscription = SubscriptionV2.objects.select_for_update().get(pk=source.subscription.pk)
        if subscription.business_id != business.pk:
            raise AIUsageUnavailable('AI source of another business.', reason='no_ai_entitlement')
        resolve_ai_usage_limit(subscription)
        return subscription
    resolved = resolve_subscription(business, service_type='appointments')
    if resolved.subscription_v2 is None:
        raise AIUsageUnavailable('No effective appointments_ai subscription.', reason='no_ai_entitlement')
    subscription = SubscriptionV2.objects.select_for_update().get(pk=resolved.subscription_v2.pk)
    # A complimentary grant leaves the Business in 'trialing' (01A); only an
    # in-window grant may use that status, never a Mercado Pago trial.
    business_ok = business.status == 'active' or (
        business.status == 'trialing' and complimentary_grant_active(subscription, at=at)
    )
    if not business_ok or not subscription_lifecycle_access(subscription, at=at):
        raise AIUsageUnavailable('AI usage is not allowed by the current lifecycle.', reason='suspended')
    if subscription.cancel_at_period_end and subscription.current_period_end is None:
        raise AIUsageUnavailable('The cancellation boundary is unresolved.')
    resolve_ai_usage_limit(subscription)
    return subscription


def count_ai_sessions_for_usage_period(
    *, business: Business, period_start: datetime, period_end: datetime,
) -> int:
    start, end = _utc(period_start), _utc(period_end)
    if end <= start:
        raise AIUsageUnavailable('A positive usage period is required.')
    return AppointmentAIUsageSession.objects.filter(
        business=business, usage_period_start=start, usage_period_end=end,
    ).count()


@transaction.atomic
def get_or_create_ai_usage_session(
    *, business: Business, conversation_id: str, interaction_id: UUID, at: datetime,
) -> tuple[AppointmentAIUsageSession, bool]:
    """Trusted internal boundary, NOT a message/sync hook.

    The caller attests real AI participation after a valid customer interaction.
    Retries MUST retain the event UUID and its original occurrence time, including
    retries of non-opening interactions. No receipt-time default or raw messages.
    """
    at = _utc(at)
    if not isinstance(interaction_id, UUID):
        raise AIUsageUnavailable('An immutable interaction UUID is required.')
    if not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 64:
        raise AIUsageUnavailable('A canonical conversation identity is required.')
    # A stable existing row serializes even the first session; never lock an
    # empty session queryset. S6 locks the subscription next in the same order.
    business = Business.objects.select_for_update().get(pk=business.pk)
    subscription = _locked_subscription(business, at=at)
    identities = set(LeadAgentState.objects.filter(
        lead__business=business, channel__business=business,
        channel__is_active=True, external_conversation_id=conversation_id,
    ).values_list('channel_id', 'agent_instance_id'))
    if len(identities) != 1:
        raise AIUsageUnavailable('The conversation context is missing or ambiguous.', reason='unsafe_conversation_context')
    sessions = AppointmentAIUsageSession.objects.filter(business=business)
    opening = sessions.filter(opening_interaction_id=interaction_id).first()
    if opening is not None:
        if opening.external_conversation_id != conversation_id or opening.started_at != at:
            raise AIUsageUnavailable('Interaction identity conflicts with the original session.', reason='interaction_conflict')
        return opening, False
    sessions = sessions.filter(external_conversation_id=conversation_id)
    existing = sessions.filter(started_at__lte=at, expires_at__gt=at).first()
    if existing is not None:
        return existing, False
    if sessions.filter(started_at__gt=at, started_at__lt=at + SESSION_DURATION).exists():
        raise AIUsageUnavailable('Out-of-order interaction would overlap a recorded session.')
    period_start, period_end = resolve_appointments_ai_usage_period(subscription, at=at)
    policy = resolve_ai_usage_policy(business, at=at)
    if not policy['can_start_new_session']:
        raise AIUsageHardCapReached('The next AI session would exceed the hard cap.')
    if subscription.business_id != business.pk or policy['usage_tier'] != subscription.usage_tier:
        raise AIUsageUnavailable('The session subscription and economic policy are inconsistent.')
    session = AppointmentAIUsageSession.objects.create(
        business=business, subscription=subscription,
        external_conversation_id=conversation_id, opening_interaction_id=interaction_id,
        started_at=at, expires_at=at + SESSION_DURATION,
        usage_period_start=period_start, usage_period_end=period_end,
        usage_tier=subscription.usage_tier,
    )
    included = policy['used_sessions'] < policy['included_sessions']
    price = 0 if included else policy['overage_unit_price']
    AppointmentAIUsageCharge.objects.create(
        session=session, business=business, subscription=subscription,
        usage_period_start=period_start, usage_period_end=period_end,
        usage_tier=policy['usage_tier'], session_ordinal=policy['used_sessions'] + 1,
        included_sessions_snapshot=policy['included_sessions'],
        classification='included' if included else 'overage',
        unit_price=price, amount=price, currency='ARS',
    )
    return session, True


@transaction.atomic
def get_appointments_ai_usage(business: Business, *, at: datetime) -> dict:
    return _appointments_ai_usage(business, at=at)[0]


def _appointments_ai_usage(business: Business, *, at: datetime) -> tuple[dict, SubscriptionV2]:
    at = _utc(at)
    business = Business.objects.select_for_update().get(pk=business.pk)
    subscription = _locked_subscription(business, at=at)
    period_start, period_end = resolve_appointments_ai_usage_period(subscription, at=at)
    included = resolve_ai_usage_limit(subscription)
    used = count_ai_sessions_for_usage_period(
        business=business, period_start=period_start, period_end=period_end,
    )
    return {
        'usage_tier': subscription.usage_tier,
        'period_start': period_start,
        'period_end': period_end,
        'used': used,
        'included': included,
        'remaining': max(0, included - used),
    }, subscription


@transaction.atomic
def resolve_ai_usage_policy(business: Business, *, at: datetime) -> dict:
    """Resolve admission for a NEW session, not an already open 24h window.

    Unresolved/manual contracts and lifecycle denials retain S8A's explicit
    exceptions. Monetary values are integer ARS from the canonical catalog.
    """
    usage, subscription = _appointments_ai_usage(business, at=at)
    tier = canonical_pricing.get_usage_tier(usage['usage_tier'])
    if tier is None:
        raise AIUsageUnavailable('An explicit resolved AI usage tier is required.')
    price = tier.get('extra_conversation_price')
    cap = tier.get('default_extra_spend_limit')
    if type(price) is not int or price <= 0 or type(cap) is not int or cap < 0:
        raise AIUsageUnavailable('The AI overage price or hard cap is unresolved.')
    if is_complimentary_grant(subscription):
        # A complimentary grant never charges: no overage, the tier is the cap.
        cap = 0
    overage = max(0, usage['used'] - usage['included'])
    max_overage = cap // price
    max_total = usage['included'] + max_overage
    allowed = usage['used'] < max_total
    return {
        'usage_tier': usage['usage_tier'],
        'included_sessions': usage['included'],
        'used_sessions': usage['used'],
        'overage_sessions': overage,
        'overage_unit_price': price,
        'overage_amount': overage * price,
        'hard_cap_amount': cap,
        'max_overage_sessions': max_overage,
        'max_total_sessions': max_total,
        'can_start_new_session': allowed,
        'blocked_reason': None if allowed else 'hard_cap_reached',
    }


def can_start_ai_usage_session(business: Business, *, at: datetime) -> bool:
    """Preauthorization only; creation rechecks under its own enclosing lock.

    Do not use this to gate interactions within an existing session: only
    get_or_create_ai_usage_session can determine whether a new slot is needed.
    """
    return resolve_ai_usage_policy(business, at=at)['can_start_new_session']


@transaction.atomic
def resolve_ai_overage_statement(
    business: Business, period_start: datetime, period_end: datetime, *, at: datetime | None = None,
) -> dict:
    """Historical recorded economics, not S8B's repriced admission estimate.

    Closed means eligible by time only, never invoiced, settled or paid.
    No backfill: missing economic evidence must not become a zero-valued charge.
    """
    start, end = _utc(period_start), _utc(period_end)
    now = _utc(at if at is not None else timezone.now())
    if end <= start:
        raise AIUsageUnavailable('A positive usage period is required.')
    business = Business.objects.select_for_update().get(pk=business.pk)
    entries = list(AppointmentAIUsageCharge.objects.filter(
        business=business, usage_period_start=start, usage_period_end=end,
    ).select_related('session', 'subscription'))
    sessions = count_ai_sessions_for_usage_period(
        business=business, period_start=start, period_end=end,
    )
    if len(entries) != sessions:
        raise AIUsageUnavailable('The usage period has sessions without economic evidence.')
    for entry in entries:
        session = entry.session
        if (
            session.business_id != business.pk
            or entry.subscription.business_id != business.pk
            or session.subscription_id != entry.subscription_id
            or session.usage_period_start != start or session.usage_period_end != end
            or session.usage_tier != entry.usage_tier
            or not start <= session.started_at < end
        ):
            raise AIUsageUnavailable('The usage period has inconsistent economic evidence.')
    tiers = sorted({entry.usage_tier for entry in entries})
    extras = [entry for entry in entries if entry.classification == 'overage']
    amount = sum(entry.amount for entry in extras)
    return {
        'usage_tier': tiers[0] if len(tiers) == 1 else None,
        'usage_tiers': tiers,
        'period_start': start,
        'period_end': end,
        'included_sessions': len(entries) - len(extras),
        'total_sessions': len(entries),
        'overage_sessions': len(extras),
        'overage_amount': amount,
        'currency': 'ARS',
        'status': 'open' if now < end else 'eligible_for_settlement',
        'settlement_ready_amount': 0 if now < end else amount,
    }
