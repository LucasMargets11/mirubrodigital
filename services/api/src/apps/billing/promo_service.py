"""
billing/promo_service.py
========================
Pure validation logic for promotional codes.

The backend is always the source of truth — discount calculations are never
delegated to the frontend.

Validation order
----------------
1.  Code exists in the database.
2.  Code is active (PromoCode.active == True).
3.  Code has started (starts_at <= now, if set).
4.  Code has not expired (ends_at >= now, if set).
5.  Plan is eligible (applies_to_plan_codes non-empty AND plan_code in it).
6.  Billing period is 'monthly' (MVP hard rule) AND applies_to_billing_periods is
    non-empty AND billing_period is in it.
7.  Service type is eligible (matches applies_to_service, if set).
8.  Global max_redemptions not exceeded (counts pending + active + completed).
9.  Per-business max_redemptions_per_business not exceeded (same count).
10. Compute and return discounted_amount.

No side effects
---------------
This module has NO DB writes.  Callers (start_checkout) are responsible for
creating a PromoCodeRedemption record.
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from apps.business.models import Business

logger = logging.getLogger(__name__)

# ── Error codes ────────────────────────────────────────────────────────────────

CODE_NOT_FOUND              = 'CODE_NOT_FOUND'
CODE_INACTIVE               = 'CODE_INACTIVE'
CODE_NOT_STARTED            = 'CODE_NOT_STARTED'
CODE_EXPIRED                = 'CODE_EXPIRED'
PLAN_NOT_ELIGIBLE           = 'PLAN_NOT_ELIGIBLE'
BILLING_PERIOD_NOT_ELIGIBLE = 'BILLING_PERIOD_NOT_ELIGIBLE'
SERVICE_NOT_ELIGIBLE        = 'SERVICE_NOT_ELIGIBLE'
MAX_REDEMPTIONS_REACHED     = 'MAX_REDEMPTIONS_REACHED'
ALREADY_USED_BY_BUSINESS    = 'ALREADY_USED_BY_BUSINESS'

# Redemption statuses that count towards limits (not cancelled/expired history).
_COUNTED_STATUSES = ['pending', 'active', 'completed']


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def validate_promo_code(
    *,
    code: str,
    plan_code: str,
    billing_period: str,
    business: 'Business',
    plan_price: Decimal,
) -> dict:
    """
    Validate *code* against the given context and compute the discounted amount.

    Parameters
    ----------
    code:           Promotional code string (case-insensitive, leading/trailing
                    spaces stripped internally).
    plan_code:      Plan.code the user is subscribing to.
    billing_period: 'monthly' or 'yearly'.
    business:       Business instance applying the code.
    plan_price:     Plan.price (DecimalField, ARS pesos).

    Returns
    -------
    On success::

        {
            'valid': True,
            'promo_code': <PromoCode instance>,
            'discount_type': str,          # 'percent' | 'fixed_amount'
            'discount_value': Decimal,
            'duration_cycles': int,        # >= 1
            'original_amount': Decimal,    # ARS pesos
            'discounted_amount': Decimal,  # ARS pesos, >= 0
            'summary': str,                # human-readable Spanish summary
        }

    On failure::

        {
            'valid': False,
            'error_code': str,   # one of the CODE_* / *_NOT_ELIGIBLE constants
            'detail': str,       # human-readable Spanish error
        }

    Never raises — always returns a dict.
    """
    from .models import PromoCode, PromoCodeRedemption

    code_upper = (code or '').strip().upper()
    if not code_upper:
        return _error(CODE_NOT_FOUND, 'El código promocional no existe.')

    # ── 1. Existence ──────────────────────────────────────────────────────────
    try:
        promo = PromoCode.objects.get(code=code_upper)
    except PromoCode.DoesNotExist:
        logger.info('[promo_service] Code not found: %r', code_upper)
        return _error(CODE_NOT_FOUND, 'El código promocional no existe.')

    now = timezone.now()

    # ── 2. Active flag ────────────────────────────────────────────────────────
    if not promo.active:
        logger.info('[promo_service] Code inactive: %r', code_upper)
        return _error(CODE_INACTIVE, 'Este código no está disponible.')

    # ── 3. Start date ─────────────────────────────────────────────────────────
    if promo.starts_at and now < promo.starts_at:
        logger.info('[promo_service] Code not yet started: %r starts_at=%s', code_upper, promo.starts_at)
        return _error(CODE_NOT_STARTED, 'Este código aún no está vigente.')

    # ── 4. Expiry ─────────────────────────────────────────────────────────────
    if promo.ends_at and now > promo.ends_at:
        logger.info('[promo_service] Code expired: %r ends_at=%s', code_upper, promo.ends_at)
        return _error(CODE_EXPIRED, 'Este código ha vencido.')

    # ── 5. Plan eligibility ───────────────────────────────────────────────────
    # applies_to_plan_codes must be non-empty; empty list does NOT mean "all plans".
    if not promo.applies_to_plan_codes or plan_code not in promo.applies_to_plan_codes:
        logger.info(
            '[promo_service] Plan not eligible: code=%r plan=%r eligible=%r',
            code_upper, plan_code, promo.applies_to_plan_codes,
        )
        return _error(PLAN_NOT_ELIGIBLE, 'Este código no aplica al plan seleccionado.')

    # ── 6. Billing period eligibility ─────────────────────────────────────────
    # MVP rule: only monthly billing period is accepted.
    if billing_period != 'monthly':
        logger.info(
            '[promo_service] Non-monthly billing period rejected (MVP): code=%r period=%r',
            code_upper, billing_period,
        )
        return _error(BILLING_PERIOD_NOT_ELIGIBLE, 'Solo se aceptan codigos para planes mensuales.')
    # applies_to_billing_periods must be non-empty; empty list does NOT mean "all periods".
    if not promo.applies_to_billing_periods or billing_period not in promo.applies_to_billing_periods:
        logger.info(
            '[promo_service] Billing period not eligible: code=%r period=%r eligible=%r',
            code_upper, billing_period, promo.applies_to_billing_periods,
        )
        return _error(BILLING_PERIOD_NOT_ELIGIBLE, 'Este codigo no aplica al periodo de facturacion seleccionado.')

    # ── 7. Service eligibility ────────────────────────────────────────────────
    if promo.applies_to_service:
        # Prefer service_type (canonical), fall back to default_service (legacy).
        biz_service = (
            getattr(business, 'service_type', '') or
            getattr(business, 'default_service', '') or ''
        )
        if biz_service != promo.applies_to_service:
            logger.info(
                '[promo_service] Service not eligible: code=%r promo_svc=%r biz_svc=%r',
                code_upper, promo.applies_to_service, biz_service,
            )
            return _error(SERVICE_NOT_ELIGIBLE, 'Este código no aplica al servicio seleccionado.')

    # ── 8. Global max_redemptions ─────────────────────────────────────────────
    if promo.max_redemptions is not None:
        used = PromoCodeRedemption.objects.filter(
            promo_code=promo,
            status__in=_COUNTED_STATUSES,
        ).count()
        if used >= promo.max_redemptions:
            logger.info(
                '[promo_service] Global limit reached: code=%r used=%d max=%d',
                code_upper, used, promo.max_redemptions,
            )
            return _error(MAX_REDEMPTIONS_REACHED, 'Este código ha alcanzado su límite de usos.')

    # ── 9. Per-business limit ─────────────────────────────────────────────────
    biz_uses = PromoCodeRedemption.objects.filter(
        promo_code=promo,
        business=business,
        status__in=_COUNTED_STATUSES,
    ).count()
    if biz_uses >= promo.max_redemptions_per_business:
        logger.info(
            '[promo_service] Per-business limit reached: code=%r biz=%s uses=%d max=%d',
            code_upper, business.pk, biz_uses, promo.max_redemptions_per_business,
        )
        return _error(ALREADY_USED_BY_BUSINESS, 'Este código ya fue utilizado por tu negocio.')

    # ── 10. Discount calculation ──────────────────────────────────────────────
    original_amount   = plan_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    discounted_amount = promo.compute_discounted_amount(original_amount)
    summary = _build_summary(promo, original_amount, discounted_amount)

    logger.info(
        '[promo_service] Valid: code=%r plan=%r period=%r original=%s discounted=%s cycles=%d',
        code_upper, plan_code, billing_period, original_amount, discounted_amount, promo.duration_cycles,
    )

    return {
        'valid': True,
        'promo_code': promo,
        'discount_type': promo.discount_type,
        'discount_value': promo.discount_value,
        'duration_cycles': promo.duration_cycles,
        'original_amount': original_amount,
        'discounted_amount': discounted_amount,
        'summary': summary,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _error(code: str, detail: str) -> dict:
    return {'valid': False, 'error_code': code, 'detail': detail}


def _format_ars(amount: Decimal) -> str:
    """Format ARS pesos in Argentine style: $29.900 (dots as thousands separator)."""
    int_val = int(amount)
    if amount == Decimal(int_val):
        # Whole pesos — skip decimal part for readability
        formatted = f'{int_val:,}'.replace(',', '.')
        return f'${formatted}'
    # Has cents
    formatted = f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'${formatted}'


def _build_summary(promo, original_amount: Decimal, discounted_amount: Decimal) -> str:
    from .models import PromoCode

    if promo.discount_type == PromoCode.DiscountType.PERCENT:
        pct = int(promo.discount_value) if promo.discount_value % 1 == 0 else promo.discount_value
        discount_str = f'{pct}% de descuento'
    else:
        discount_str = f'{_format_ars(promo.discount_value)} de descuento'

    cycles = promo.duration_cycles
    duration_str = 'durante 1 mes' if cycles == 1 else f'durante {cycles} meses'

    return (
        f'{discount_str} {duration_str}. '
        f'Luego pagás {_format_ars(original_amount)}/mes.'
    )
