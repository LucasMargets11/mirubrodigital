from __future__ import annotations

import logging
from typing import Dict, List

from apps.business.features import feature_flags_for_plan, feature_flags_for_subscription, feature_flags_for_v2_subscription
from apps.business.models import BusinessPlan
from apps.business.service_catalog import enabled_services

logger = logging.getLogger(__name__)


def build_business_context(business) -> Dict[str, object]:
    """
    Build the runtime business context for a business.

    Source priority (V2-first):
      1. SubscriptionV2 via billing.runtime.resolve_subscription
      2. legacy business.Subscription as controlled fallback
      3. Minimal safe state when no subscription exists

    The returned dict preserves backward-compatible keys.
    Enforcement fields (access_allowed, reason_code, grace_until, access_until,
    show_renewal_prompt) are added non-breaking alongside legacy keys.

    IMPORTANT: 'status'='none' means no valid subscription was found.
    Access control is enforced via has_entitlement() / HasEntitlement, which
    respect resolved.access_granted — no optimistic defaults are injected.
    """
    from apps.billing.runtime import resolve_subscription

    resolved = resolve_subscription(business)

    # ── Plan & status ──────────────────────────────────────────────────────
    # plan falls back to STARTER for display only; access is controlled by
    # resolved.access_granted via has_entitlement(), never by plan alone.
    plan = resolved.plan or BusinessPlan.STARTER
    status = resolved.status or 'none'

    # ── Feature flags ──────────────────────────────────────────────────────
    # Legacy source: use full subscription logic (includes addon enrichment).
    # V2 source: use feature_flags_for_v2_subscription which bridges addon
    #   flags from the legacy subscription where a native V2 addon model is
    #   absent.  Legacy is used only as a read-only bridge, not as primary.
    # none: base flags on plan tier only.
    if resolved.source == 'legacy' and resolved.legacy_sub is not None:
        feature_flags = feature_flags_for_subscription(resolved.legacy_sub)
    elif resolved.source == 'v2' and resolved.subscription_v2 is not None:
        feature_flags = feature_flags_for_v2_subscription(resolved.subscription_v2, business)
    else:
        feature_flags = feature_flags_for_plan(plan)

    # ── Service list ───────────────────────────────────────────────────────
    service_list: List[str] = enabled_services(plan, feature_flags)

    # ── Active service ─────────────────────────────────────────────────────
    default_service = (
        resolved.service_type
        or business.default_service
        or 'gestion'
    )
    if default_service not in service_list and service_list:
        active_service = service_list[0]
    elif not service_list:
        active_service = 'gestion'
    else:
        active_service = default_service

    # ── Enforcement decision ───────────────────────────────────────────────
    # Central access gating: all enforcement metadata is computed here and
    # surfaced in the context dict for MeView / _session_payload.
    from apps.billing.enforcement import get_enforcement_decision
    decision = get_enforcement_decision(resolved)

    grace_until_iso = (
        decision.grace_until.isoformat() if decision.grace_until else None
    )
    access_until_iso = (
        decision.access_until.isoformat() if decision.access_until else None
    )

    return {
        # ─ Backward-compatible keys (stable contract) ─────────────────────
        'plan': plan,
        'status': status,
        'features': feature_flags,
        'enabled_services': service_list,
        'default_service': default_service,
        'service': active_service,
        # ─ Observability / source (non-breaking addition) ─────────────────
        '_subscription_source': resolved.source,
        # ─ Enforcement fields for frontend and API consumers ──────────────
        'access_allowed': decision.access_allowed,
        'reason_code': decision.reason_code,
        'grace_until': grace_until_iso,
        'access_until': access_until_iso,
        'show_renewal_prompt': decision.show_renewal_prompt,
    }
