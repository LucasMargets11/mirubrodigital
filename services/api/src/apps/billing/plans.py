"""
Plan-level seat limits.

Maps plan tiers (as resolved by billing.runtime._extract_plan_tier) to
the maximum number of *secondary* users (owner excluded) allowed.

Legacy plan limits are static. Canonical Turnos limits come from the
commercial pricing catalog.
"""

PLAN_SEAT_LIMITS: dict[str, int] = {
    'start':      2,
    'starter':    2,
    'plus':       5,
    'pro':        10,
    'business':   25,
    'enterprise': 100,
    # Menu QR tiers (lower seat needs)
    'menu_qr':         2,
    'menu_qr_lite':    2,
    'menu_qr_marca':   3,
    'menu_qr_visual':  5,
    'menu_qr_pro':     10,
    'menu_qr_premium': 15,
}

DEFAULT_SEAT_LIMIT: int = 2


def get_seat_limit(plan_tier: str | None) -> int:
    """Return the maximum secondary-user seats for *plan_tier*."""
    if not plan_tier:
        return DEFAULT_SEAT_LIMIT
    from apps.billing.appointments_plans import PLAN_CODES
    from apps.billing.reception_plans import RECEPTION_PLAN

    if plan_tier in PLAN_CODES or plan_tier == RECEPTION_PLAN:
        # Canonical Turnos and Recepcionista IA limits come from the catalog
        # (validated >= 1 for Recepcionista: callers read 0 as "no limit").
        from apps.billing.canonical_pricing import get_plan

        plan = get_plan(plan_tier)
        if plan is None:
            raise RuntimeError(f'Canonical plan missing from catalog: {plan_tier}')
        return plan['secondary_users_included']
    return PLAN_SEAT_LIMITS.get(plan_tier, DEFAULT_SEAT_LIMIT)
