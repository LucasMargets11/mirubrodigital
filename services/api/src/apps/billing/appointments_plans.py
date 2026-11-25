"""Commercial Turnos configuration. Prices and included capacity come from S2."""
from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError

PLAN_CODES = frozenset({'appointments', 'appointments_pro', 'appointments_ai'})
AUTOMATIONS = 'appointments_automations'
EXTRA_PROFESSIONAL = 'appointments_extra_professional'
ADDON_CODES = frozenset({AUTOMATIONS, EXTRA_PROFESSIONAL})
USAGE_TIERS = ('ai_300', 'ai_1500', 'ai_3000', 'custom')


def validate_usage_tier(plan_code: str, usage_tier: str | None, *,
                        allow_legacy_null: bool = False) -> None:
    if plan_code == 'appointments_ai':
        if usage_tier is None and allow_legacy_null:
            return
        if usage_tier not in USAGE_TIERS:
            raise ValidationError({'usage_tier': 'Turnos IA requires an explicit valid usage tier.'})
    elif plan_code == 'reception':
        # PROD-02B: Recepcionista IA has its own tiers (never Turnos IA's).
        from apps.billing.reception_plans import validate_reception_usage_tier

        validate_reception_usage_tier(usage_tier)
    elif usage_tier is not None:
        raise ValidationError({'usage_tier': 'This plan does not support a usage tier.'})


def validate_addon_quantity(code: str, quantity: int) -> None:
    # Validate before Django's IntegerField can silently coerce a decimal.
    if type(quantity) is not int or quantity < 0:
        raise ValidationError({'quantity': 'Quantity must be a nonnegative integer.'})
    if code == AUTOMATIONS and quantity > 1:
        raise ValidationError({'quantity': 'Automations quantity must be 0 or 1.'})


@dataclass(frozen=True)
class AppointmentsPlanConfig:
    plan_code: str
    usage_tier: str | None
    included_professionals: int
    included_secondary_users: int
    automations_included: bool
    ai_enabled: bool
    usage_tier_config: dict | None


def get_appointments_plan_config(plan_code: str, usage_tier: str | None, *,
                                allow_legacy_null: bool = False) -> AppointmentsPlanConfig:
    from apps.billing import canonical_pricing

    if plan_code not in PLAN_CODES:
        raise ValidationError({'plan_code': 'Not a canonical Turnos plan.'})
    validate_usage_tier(plan_code, usage_tier, allow_legacy_null=allow_legacy_null)
    plan = canonical_pricing.get_plan(plan_code)
    if plan is None:
        raise ValidationError({'plan_code': 'Turnos plan missing from canonical catalog.'})
    tier = None
    if usage_tier is not None:
        tier = canonical_pricing.get_usage_tier(usage_tier)
        if tier is None or tier['plan_code'] != plan_code:
            raise ValidationError({'usage_tier': 'Usage tier missing from canonical catalog.'})
        tier = tier.copy()
    return AppointmentsPlanConfig(
        plan_code=plan_code,
        usage_tier=usage_tier,
        included_professionals=plan['professionals_included'],
        included_secondary_users=plan['secondary_users_included'],
        automations_included=AUTOMATIONS in plan.get('included_addons', []),
        ai_enabled=plan_code == 'appointments_ai' and tier is not None,
        usage_tier_config=tier,
    )
