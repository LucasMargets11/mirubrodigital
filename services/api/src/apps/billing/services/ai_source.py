"""Single resolver of the subscription that sources a Business's AI (PROD-02E1).

Possible sources (exact service/plan pairs, never a cross-service fallback):
  * `reception`    — SubscriptionV2 service_type='reception',   plan_code='reception'
  * `appointments_ai` — SubscriptionV2 service_type='appointments', plan_code='appointments_ai'

A candidate is *commercially eligible* only when all of these hold at `at`:
  - it belongs to the Business and is resolved by billing.runtime for its own
    service (so canceled / checkout_pending rows are never candidates);
  - the Turnos/Recepcionista lifecycle allows it at the interaction instant
    (active, in-window complimentary grant, past_due inside grace,
    cancel-at-period-end boundary) — the states billing enforcement allows,
    so suspended, expired past_due, not-yet-started or ended benefits are out;
  - the Business itself may consume (active, or trialing only for an
    in-window complimentary grant), as the metering engine already required;
  - plan and tier are valid for that product.

Resolution: 0 eligible → `no_ai_entitlement`; 1 → that subscription; 2 →
`ambiguous_ai_source` (fail closed: Recepcionista + Turnos IA must never mean
two allowances or two bills). `Business.service_type` plays no role.

Eligibility is not a consumption policy: `policy_configured` tells whether the
tier has a positive included-conversation allowance (and, for self-service
tiers, its overage economics). An undefined allowance is NEVER unlimited.
`reception_custom` (PROD-02E2B) is configured only while its individual
policy (billing.ReceptionAIUsagePolicy) is effective at `at`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger(__name__)

RECEPTION_SOURCE = 'reception'
APPOINTMENTS_AI_SOURCE = 'appointments_ai'

# source → (service_type, exact plan_code)
AI_SOURCES = {
    RECEPTION_SOURCE: ('reception', 'reception'),
    APPOINTMENTS_AI_SOURCE: ('appointments', 'appointments_ai'),
}

NO_AI_ENTITLEMENT = 'no_ai_entitlement'
AMBIGUOUS_AI_SOURCE = 'ambiguous_ai_source'
USAGE_POLICY_UNDEFINED = 'usage_policy_undefined'
MANUAL_CONTRACT = 'manual_contract_required'


@dataclass(frozen=True)
class AISourceCandidate:
    source: str
    subscription: object
    eligible: bool
    reason: Optional[str]          # why it is not eligible
    policy_configured: bool
    policy_reason: Optional[str]   # why no usable consumption policy


@dataclass(frozen=True)
class AISourceResolution:
    source: Optional[str]
    subscription: Optional[object]
    reason: Optional[str]                      # None only when one eligible source
    policy_configured: bool = False
    policy_reason: Optional[str] = None
    candidates: tuple = field(default_factory=tuple)

    @property
    def eligible(self) -> bool:
        return self.subscription is not None and self.reason is None


def _lifecycle_access(subscription, *, at: datetime) -> bool:
    """Same rule as appointments_lifecycle.subscription_lifecycle_access, per product."""
    from apps.billing.models import SubscriptionV2
    from apps.billing.services.appointments_lifecycle import (
        complimentary_grant_active, subscription_lifecycle_access,
    )

    if subscription.service_type == SubscriptionV2.ServiceType.APPOINTMENTS:
        return subscription_lifecycle_access(subscription, at=at)
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


def _business_may_consume(business, subscription, *, at: datetime) -> bool:
    from apps.billing.services.appointments_lifecycle import complimentary_grant_active

    return business.status == 'active' or (
        business.status == 'trialing' and complimentary_grant_active(subscription, at=at)
    )


def _tier_policy(source: str, subscription, *, at: datetime) -> tuple[bool, Optional[str]]:
    """(policy_configured, reason). Plan/tier validity raises ValidationError."""
    if source == RECEPTION_SOURCE:
        from apps.billing.reception_plans import resolve_reception_subscription_config

        config = resolve_reception_subscription_config(subscription)
        if config.usage_tier == 'reception_custom':
            return _custom_policy(subscription, config.usage_tier_config, at=at)
        tier = config.usage_tier_config
    else:
        from apps.billing.services.appointments import resolve_appointments_subscription_config

        config = resolve_appointments_subscription_config(subscription)
        if config.usage_tier == 'custom':
            return False, MANUAL_CONTRACT
        if not config.ai_enabled or config.usage_tier_config is None:
            raise ValidationError({'usage_tier': 'AI tier unresolved.'})
        tier = config.usage_tier_config
    if tier.get('purchase_mode') == 'contact_sales' and tier.get('code', '').endswith('custom'):
        return False, MANUAL_CONTRACT
    included = tier.get('included_conversations')
    if type(included) is not int or included <= 0:
        return False, USAGE_POLICY_UNDEFINED
    mode = tier.get('purchase_mode')
    if mode == 'self_service':
        price = tier.get('extra_conversation_price')
        cap = tier.get('default_extra_spend_limit')
        if type(price) is not int or price <= 0 or type(cap) is not int or cap < 0:
            return False, USAGE_POLICY_UNDEFINED
    elif mode == 'internal':
        # PROD-02E2A: fixed allowance with overage disabled (no price, cap 0).
        if (tier.get('billing_mode') != 'manual' or tier.get('extra_conversation_price') is not None
                or type(tier.get('default_extra_spend_limit')) is not int
                or tier.get('default_extra_spend_limit') != 0):
            return False, USAGE_POLICY_UNDEFINED
    else:
        return False, USAGE_POLICY_UNDEFINED
    return True, None


def _custom_policy(subscription, tier: dict, *, at: datetime) -> tuple[bool, Optional[str]]:
    """PROD-02E2B: the allowance comes from the subscription's custom policy at `at`."""
    from apps.billing.services.reception_ai_policy import (
        InvalidCustomPolicy, NoEffectiveCustomPolicy, effective_reception_custom_policy,
    )

    if (tier.get('billing_mode') != 'manual' or tier.get('extra_conversation_price') is not None
            or tier.get('default_extra_spend_limit') not in (None, 0)):
        return False, USAGE_POLICY_UNDEFINED
    try:
        effective_reception_custom_policy(subscription, at=at)
    except NoEffectiveCustomPolicy:
        return False, MANUAL_CONTRACT
    except InvalidCustomPolicy:
        return False, USAGE_POLICY_UNDEFINED
    return True, None


def _candidate(business, source: str, *, at: datetime) -> Optional[AISourceCandidate]:
    from apps.billing.runtime import resolve_subscription

    service_type, plan_code = AI_SOURCES[source]
    resolved = resolve_subscription(business, service_type=service_type)
    subscription = resolved.subscription_v2
    if (
        subscription is None
        or subscription.business_id != business.pk
        or subscription.service_type != service_type
        or subscription.plan_code != plan_code
    ):
        return None

    def ineligible(reason):
        return AISourceCandidate(source, subscription, False, reason, False, None)

    # PROD-02E2A: evaluated at the interaction instant `at` with the product
    # lifecycle (the same states billing enforcement allows: active,
    # in-window complimentary grant, past_due in grace), exactly as the
    # metering engine always did. runtime access_granted/enforcement use the
    # wall clock and would diverge for historical occurrence times.
    if not _lifecycle_access(subscription, at=at):
        return ineligible('suspended')
    if subscription.cancel_at_period_end and subscription.current_period_end is None:
        return ineligible('suspended')
    if not _business_may_consume(business, subscription, at=at):
        return ineligible('suspended')
    try:
        configured, policy_reason = _tier_policy(source, subscription, at=at)
    except ValidationError:
        return ineligible('invalid_tier')
    return AISourceCandidate(source, subscription, True, None, configured, policy_reason)


def resolve_ai_source(business, *, at: Optional[datetime] = None) -> AISourceResolution:
    """Fail-closed resolution of the Business's single AI source (read-only, no locks)."""
    at = at or timezone.now()
    try:
        candidates = tuple(
            c for c in (_candidate(business, source, at=at) for source in AI_SOURCES) if c is not None
        )
    except Exception:  # noqa: BLE001 — ambiguous state never opens AI
        logger.exception('ai_source resolution failed business=%s', getattr(business, 'pk', None))
        return AISourceResolution(None, None, NO_AI_ENTITLEMENT)
    eligible = [c for c in candidates if c.eligible]
    if len(eligible) > 1:
        logger.warning(
            'ai_source ambiguous business=%s sources=%s',
            business.pk, sorted(c.source for c in eligible),
        )
        return AISourceResolution(None, None, AMBIGUOUS_AI_SOURCE, candidates=candidates)
    if not eligible:
        reason = candidates[0].reason if len(candidates) == 1 else NO_AI_ENTITLEMENT
        return AISourceResolution(None, None, reason or NO_AI_ENTITLEMENT, candidates=candidates)
    winner = eligible[0]
    return AISourceResolution(
        winner.source, winner.subscription, None,
        policy_configured=winner.policy_configured, policy_reason=winner.policy_reason,
        candidates=candidates,
    )
