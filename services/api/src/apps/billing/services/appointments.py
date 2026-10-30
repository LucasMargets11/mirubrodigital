"""Read-only Turnos configuration and effective automations access."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from apps.billing.appointments_plans import (
    ADDON_CODES, AUTOMATIONS, EXTRA_PROFESSIONAL, PLAN_CODES,
    get_appointments_plan_config, validate_addon_quantity,
)

if TYPE_CHECKING:
    from apps.billing.models import SubscriptionV2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppointmentsSubscriptionConfig:
    plan_code: str
    usage_tier: str | None
    included_professionals: int
    extra_professionals: int
    effective_professional_limit: int
    included_secondary_users: int
    automations_enabled: bool
    ai_enabled: bool
    usage_tier_config: dict | None
    redundant_addons: tuple[str, ...]


def resolve_appointments_subscription_config(
    subscription: SubscriptionV2,
) -> AppointmentsSubscriptionConfig:
    from apps.billing.runtime import _extract_plan_tier

    # S1 also recognizes canonical Turnos codes on historical misclassified services.
    plan_code = _extract_plan_tier(subscription.plan_code)
    if plan_code == 'appointments_base':
        plan_code = 'appointments'
    plan = get_appointments_plan_config(
        plan_code, subscription.usage_tier,
        allow_legacy_null=subscription.has_legacy_null_usage_tier(),
    )
    quantities = {}
    for addon in subscription.addons.filter(is_active=True, code__in=ADDON_CODES):
        validate_addon_quantity(addon.code, addon.quantity)
        quantities[addon.code] = addon.quantity
    extras = quantities.get(EXTRA_PROFESSIONAL, 0)
    automations = quantities.get(AUTOMATIONS, 0) == 1
    redundant = (AUTOMATIONS,) if plan.automations_included and automations else ()
    if redundant:
        logger.warning(
            "Redundant included Turnos addon subscription_v2=%s code=%s; no extra capacity or charge",
            subscription.pk, AUTOMATIONS,
        )
    return AppointmentsSubscriptionConfig(
        plan_code=plan.plan_code,
        usage_tier=plan.usage_tier,
        included_professionals=plan.included_professionals,
        extra_professionals=extras,
        effective_professional_limit=plan.included_professionals + extras,
        included_secondary_users=plan.included_secondary_users,
        automations_enabled=plan.automations_included or automations,
        ai_enabled=plan.ai_enabled,
        usage_tier_config=plan.usage_tier_config,
        redundant_addons=redundant,
    )


def get_appointments_subscription_entitlements(subscription: SubscriptionV2) -> set[str]:
    from apps.business.entitlements import APPOINTMENTS_AUTOMATIONS_ENTITLEMENT, get_plan_entitlements

    config = resolve_appointments_subscription_config(subscription)
    entitlements = get_plan_entitlements(config.plan_code)
    if config.automations_enabled:
        entitlements.add(APPOINTMENTS_AUTOMATIONS_ENTITLEMENT)
    return entitlements


def can_use_appointments_automations(business, *, at=None) -> bool:
    """Effective S7A access, using current S3 configuration and S6 lifecycle only."""
    from apps.billing.runtime import resolve_subscription
    from apps.billing.services.appointments_lifecycle import subscription_lifecycle_access
    from apps.business.entitlements import APPOINTMENTS_AUTOMATIONS_ENTITLEMENT

    resolved = resolve_subscription(business, service_type='appointments')
    subscription = resolved.subscription_v2
    if subscription is None:
        return (
            resolved.source == 'legacy'
            and resolved.plan == 'appointments_base'
            and resolved.access_granted
            and APPOINTMENTS_AUTOMATIONS_ENTITLEMENT in resolved.entitlements
        )
    if subscription.plan_code == 'appointments_base':
        return (
            APPOINTMENTS_AUTOMATIONS_ENTITLEMENT in resolved.entitlements
            and subscription_lifecycle_access(subscription, at=at)
        )
    # S1's permissive code extraction is not evidence of a valid commercial plan.
    if subscription.plan_code not in PLAN_CODES:
        logger.warning(
            "Ambiguous Turnos automations plan subscription_v2=%s plan=%s",
            subscription.pk, subscription.plan_code,
        )
        return False
    if subscription.cancel_at_period_end and subscription.current_period_end is None:
        logger.warning(
            "Missing Turnos cancellation boundary subscription_v2=%s", subscription.pk,
        )
        return False
    if not subscription_lifecycle_access(subscription, at=at):
        return False
    try:
        config = resolve_appointments_subscription_config(subscription)
    except ValidationError as exc:
        logger.error(
            "Invalid Turnos automations configuration subscription_v2=%s: %s",
            subscription.pk, exc,
        )
        return False
    return config.automations_enabled
