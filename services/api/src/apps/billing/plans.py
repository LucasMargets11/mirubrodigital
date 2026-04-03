"""
Plan-level seat limits.

Maps plan tiers (as resolved by billing.runtime._extract_plan_tier) to
the maximum number of *secondary* users (owner excluded) allowed.

This is a static lookup — no DB model involved.  To change a plan's
seat limit, update PLAN_SEAT_LIMITS and redeploy.
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
    return PLAN_SEAT_LIMITS.get(plan_tier, DEFAULT_SEAT_LIMIT)
