"""Recepcionista IA commercial configuration (PROD-02B).

Recepcionista is a service of its own (`service_type='reception'`), independent
of Turnos. Its catalog lives in generated/pricing.json (product, single
tier-priced plan and own usage tiers) and is validated by
canonical_pricing.validate_reception_catalog.

Prices and included conversations are NOT defined yet: every tier is
non-purchasable (contact_sales/manual, null amounts) and the product stays
inactive, so neither the public checkout nor complimentary provisioning can
sell or grant it. This module only resolves what an existing subscription is
entitled to; it never makes a tier usable for AI metering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from apps.billing.canonical_pricing import RECEPTION_USAGE_TIERS as USAGE_TIERS

if TYPE_CHECKING:
    from apps.billing.models import SubscriptionV2

RECEPTION_SERVICE = 'reception'
RECEPTION_PLAN = 'reception'


def validate_reception_usage_tier(usage_tier: str | None) -> None:
    """A Recepcionista subscription always carries one of its own tiers."""
    if usage_tier not in USAGE_TIERS:
        raise ValidationError({'usage_tier': 'Recepcionista IA requires an explicit valid usage tier.'})


@dataclass(frozen=True)
class ReceptionPlanConfig:
    plan_code: str
    usage_tier: str
    included_secondary_users: int
    usage_tier_config: dict


def get_reception_plan_config(plan_code: str, usage_tier: str | None) -> ReceptionPlanConfig:
    """Canonical plan + tier for Recepcionista, or ValidationError (fail closed)."""
    from apps.billing import canonical_pricing

    if plan_code != RECEPTION_PLAN:
        raise ValidationError({'plan_code': 'Not the canonical Recepcionista plan.'})
    validate_reception_usage_tier(usage_tier)
    plan = canonical_pricing.get_plan(plan_code)
    if plan is None or plan.get('vertical') != RECEPTION_SERVICE:
        raise ValidationError({'plan_code': 'Recepcionista plan missing from canonical catalog.'})
    if usage_tier not in plan.get('usage_tiers', []):
        raise ValidationError({'usage_tier': 'Usage tier not offered by the Recepcionista plan.'})
    tier = canonical_pricing.get_usage_tier(usage_tier)
    if tier is None or tier.get('plan_code') != plan_code:
        raise ValidationError({'usage_tier': 'Usage tier missing from canonical catalog.'})
    return ReceptionPlanConfig(
        plan_code=plan_code,
        usage_tier=usage_tier,
        included_secondary_users=plan['secondary_users_included'],
        usage_tier_config=tier.copy(),
    )


def resolve_reception_subscription_config(subscription: SubscriptionV2) -> ReceptionPlanConfig:
    from apps.billing.runtime import _extract_plan_tier

    if subscription.service_type != RECEPTION_SERVICE:
        raise ValidationError({'service_type': 'Not a Recepcionista subscription.'})
    return get_reception_plan_config(_extract_plan_tier(subscription.plan_code), subscription.usage_tier)


def get_reception_subscription_entitlements(subscription: SubscriptionV2) -> set[str]:
    """Entitlements of a valid Recepcionista subscription; ValidationError otherwise."""
    from apps.business.entitlements import get_plan_entitlements

    config = resolve_reception_subscription_config(subscription)
    return get_plan_entitlements(config.plan_code)
