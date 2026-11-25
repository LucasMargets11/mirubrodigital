"""
canonical_pricing.py — Canonical pricing source of truth for the backend.

Reads pricing data from generated/pricing.json (produced by the frontend
canonical layer at apps/web/src/lib/pricing/).

ALL values are **ARS pesos integers** — NOT centavos, NOT floats.
  e.g. Starter monthly = 36000  (means $36.000 ARS)

This module is the ONLY place the backend should read prices from.
commercial_plans.py delegates here; seeds read from here.

Guards
------
* assert_not_centavos(value): raises if value looks suspiciously low
  (< MIN_PLAN_PRICE and plan is non-custom).
* assert_canonical_match(code, value): verifies a runtime value matches
  the canonical price for a given plan/addon/extra code.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Load pricing.json ─────────────────────────────────────────────────────────

def _find_pricing_json() -> Path:
    """Locate pricing.json across host and Docker layouts."""
    base = Path(__file__).resolve()
    # Walk up from canonical_pricing.py looking for generated/pricing.json
    # Docker:  /app/src/apps/billing/… → /app/generated/pricing.json  (parents[3])
    # Host:    <repo>/services/api/src/apps/billing/… → <repo>/generated/  (parents[5])
    for ancestor in base.parents:
        candidate = ancestor / 'generated' / 'pricing.json'
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"pricing.json not found walking up from {base}"
    )

_PRICING_JSON_PATH = _find_pricing_json()


def validate_appointments_catalog(data: dict) -> None:
    """Validate S2 offers without applying the plan-price floor to overage."""
    def integer(value, label, minimum=0):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{label} must be an ARS/count integer >= {minimum}")

    def recurring(offer, monthly='price_monthly', yearly='price_yearly'):
        integer(offer[monthly], f"{offer['code']}.{monthly}", MIN_SANE_PRICE)
        integer(offer[yearly], f"{offer['code']}.{yearly}", MIN_SANE_PRICE)
        if offer[yearly] * 5 != offer[monthly] * 48:
            raise ValueError(f"{offer['code']}: annual price must have exactly 20% discount")

    indexes = {}
    for section in ('products', 'plans', 'addons', 'extras', 'usage_tiers'):
        rows = data[section]
        indexes[section] = {row['code']: row for row in rows}
        if len(indexes[section]) != len(rows):
            raise ValueError(f"Duplicate codes in {section}")

    product = indexes['products']['appointments']
    if product['vertical'] != 'appointments' or type(product['is_active']) is not bool:
        raise ValueError("Invalid appointments product metadata")
    plans = indexes['plans']
    for code in ('appointments', 'appointments_pro', 'appointments_ai'):
        plan = plans[code]
        if plan['vertical'] != 'appointments':
            raise ValueError(f"{code}: invalid vertical")
        integer(plan['professionals_included'], f'{code}.professionals_included')
        integer(plan['secondary_users_included'], f'{code}.secondary_users_included')
        if code != 'appointments_ai':
            recurring(plan)

    ai = plans['appointments_ai']
    if (ai['pricing_mode'] != 'usage_tier'
            or ai['price_monthly'] is not None or ai['price_yearly'] is not None
            or ai['includes_plans'] != ['appointments_pro']
            or ai['included_addons'] != ['appointments_automations']):
        raise ValueError("appointments_ai must be tier-priced and include Pro + Automations")
    tiers = indexes['usage_tiers']
    expected_tiers = {'ai_300', 'ai_1500', 'ai_3000', 'custom'}
    if set(ai['usage_tiers']) != expected_tiers:
        raise ValueError("appointments_ai requires the canonical usage tiers")
    for code in expected_tiers:
        tier = tiers[code]
        if tier['plan_code'] != 'appointments_ai':
            raise ValueError(f'{code}: invalid usage tier plan')
        if code == 'custom':
            if (tier['purchase_mode'] != 'contact_sales' or tier['billing_mode'] != 'manual'
                    or any(tier[key] is not None for key in (
                        'monthly_price', 'annual_price', 'included_conversations',
                        'extra_conversation_price', 'default_extra_spend_limit',
                    ))):
                raise ValueError("custom must be contact_sales/manual without self-service prices")
        else:
            if tier['purchase_mode'] != 'self_service':
                raise ValueError(f'{code}: invalid purchase mode')
            recurring(tier, 'monthly_price', 'annual_price')
            integer(tier['included_conversations'], f'{code}.included_conversations', 1)
            integer(tier['extra_conversation_price'], f'{code}.extra_conversation_price', 1)
            integer(tier['default_extra_spend_limit'], f'{code}.default_extra_spend_limit')

    addon = indexes['addons']['appointments_automations']
    recurring(addon)
    if (addon['vertical'] != 'appointments'
            or addon['available_for'] != ['appointments', 'appointments_pro']
            or addon['included_in'] != ['appointments_ai']):
        raise ValueError("Automations must be purchasable only for Turnos/Pro and included in IA")
    extra = indexes['extras']['appointments_extra_professional']
    recurring(extra)
    integer(extra['quantity_min'], 'appointments_extra_professional.quantity_min')
    integer(extra['quantity_step'], 'appointments_extra_professional.quantity_step', 1)
    if (extra['vertical'] != 'appointments'
            or extra['quantity_min'] != 0 or extra['quantity_step'] != 1
            or extra['available_for'] != ['appointments', 'appointments_pro', 'appointments_ai']
            or extra['code'] in indexes['addons']):
        raise ValueError("Extra professional must be a nonnegative integer quantity, not a fixed addon")


RECEPTION_USAGE_TIERS = ('reception_300', 'reception_1500', 'reception_3000', 'reception_custom')
_TIER_AMOUNT_KEYS = (
    'monthly_price', 'annual_price', 'included_conversations',
    'extra_conversation_price', 'default_extra_spend_limit',
)


def validate_reception_catalog(data: dict) -> None:
    """PROD-02B: Recepcionista IA, an unpublished service of its own.

    While prices and included conversations are pending approval the catalog
    must keep it unsellable: inactive product and contact_sales/manual tiers
    without any amount. Relaxing this requires an explicit commercial decision.
    """
    indexes = {
        section: {row['code']: row for row in data[section]}
        for section in ('products', 'plans', 'addons', 'extras', 'usage_tiers')
    }
    product = indexes['products'].get('reception')
    if product is None or product['vertical'] != 'reception':
        raise ValueError("reception product missing or with an invalid vertical")
    if product['is_active'] is not False:
        raise ValueError("reception product must stay inactive (public sale disabled)")

    reception_plans = [p for p in data['plans'] if p['vertical'] == 'reception']
    if [p['code'] for p in reception_plans] != ['reception']:
        raise ValueError("reception vertical must have exactly the 'reception' plan")
    plan = reception_plans[0]
    if (plan.get('pricing_mode') != 'usage_tier'
            or plan['price_monthly'] is not None or plan['price_yearly'] is not None
            or plan.get('is_custom') is not False):
        raise ValueError("reception plan must be tier-priced without a fixed price")
    secondary = plan.get('secondary_users_included')
    # >= 1: seat checks read a limit of 0 as "unlimited".
    if type(secondary) is not int or secondary < 1:
        raise ValueError("reception.secondary_users_included must be an integer >= 1")
    if any(key in plan for key in ('professionals_included', 'includes_plans', 'included_addons')):
        raise ValueError("reception plan includes no professionals, plans or addons")
    if plan.get('usage_tiers') != list(RECEPTION_USAGE_TIERS):
        raise ValueError("reception plan requires its own canonical usage tiers")

    for code in RECEPTION_USAGE_TIERS:
        tier = indexes['usage_tiers'].get(code)
        if tier is None or tier['plan_code'] != 'reception':
            raise ValueError(f"{code}: missing or not a reception tier")
        if (tier['purchase_mode'] != 'contact_sales' or tier.get('billing_mode') != 'manual'
                or any(tier[key] is not None for key in _TIER_AMOUNT_KEYS)):
            raise ValueError(f"{code}: must stay non-purchasable until prices are approved")
    foreign = [t['code'] for t in data['usage_tiers']
               if t['plan_code'] == 'reception' and t['code'] not in RECEPTION_USAGE_TIERS]
    if foreign:
        raise ValueError(f"unexpected reception tiers: {foreign}")
    for section in ('addons', 'extras'):
        if any(row['vertical'] == 'reception' for row in data[section]):
            raise ValueError(f"reception has no {section} yet")


# Subscription prices, not per-conversation overage.
MIN_SANE_PRICE = 1000


def _load_pricing() -> dict:
    with open(_PRICING_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data.get('unit') == 'ARS_pesos_integer', (
        f"pricing.json unit must be 'ARS_pesos_integer', got '{data.get('unit')}'"
    )
    validate_appointments_catalog(data)
    validate_reception_catalog(data)
    return data

_DATA = _load_pricing()

# ── Plans ─────────────────────────────────────────────────────────────────────

PLANS: List[dict] = _DATA['plans']
ADDONS: List[dict] = _DATA['addons']
EXTRAS: List[dict] = _DATA['extras']
PRODUCTS: List[dict] = _DATA.get('products', [])
USAGE_TIERS: List[dict] = _DATA['usage_tiers']

_PLAN_INDEX: Dict[str, dict] = {p['code']: p for p in PLANS}
_ADDON_INDEX: Dict[str, dict] = {a['code']: a for a in ADDONS}
_EXTRA_INDEX: Dict[str, dict] = {e['code']: e for e in EXTRAS}
_PRODUCT_INDEX: Dict[str, dict] = {p['code']: p for p in PRODUCTS}
_USAGE_TIER_INDEX: Dict[str, dict] = {t['code']: t for t in USAGE_TIERS}


def get_plan(code: str) -> Optional[dict]:
    return _PLAN_INDEX.get(code)


def get_addon(code: str) -> Optional[dict]:
    return _ADDON_INDEX.get(code)


def get_extra(code: str) -> Optional[dict]:
    return _EXTRA_INDEX.get(code)


def get_product(code: str) -> Optional[dict]:
    return _PRODUCT_INDEX.get(code)


def get_usage_tier(code: str) -> Optional[dict]:
    return _USAGE_TIER_INDEX.get(code)


def get_inactive_product_verticals() -> List[str]:
    return [p['vertical'] for p in PRODUCTS if not p['is_active']]


def is_plan_product_active(code: str) -> bool:
    plan = get_plan(code)
    return plan is None or plan['vertical'] not in get_inactive_product_verticals()


def get_appointments_catalog() -> dict:
    """Internal declarative catalog; availability is still controlled by product metadata."""
    return {
        'product': get_product('appointments'),
        'plans': [p for p in PLANS if p['vertical'] == 'appointments'],
        'addons': [a for a in ADDONS if a['vertical'] == 'appointments'],
        'extras': [e for e in EXTRAS if e['vertical'] == 'appointments'],
        'usage_tiers': [t for t in USAGE_TIERS if t['plan_code'] == 'appointments_ai'],
    }


def get_reception_catalog() -> dict:
    """Internal Recepcionista IA catalog (PROD-02B); never sold while the product is inactive."""
    return {
        'product': get_product('reception'),
        'plans': [p for p in PLANS if p['vertical'] == 'reception'],
        'usage_tiers': [t for t in USAGE_TIERS if t['plan_code'] == 'reception'],
    }


def get_products_catalog() -> List[dict]:
    """
    Return active products ordered by the canonical metadata in pricing.json.
    This is the backend source used by onboarding/service selectors.
    """
    products = [p for p in PRODUCTS if p.get('is_active', False)]
    return sorted(products, key=lambda p: (p.get('order', 999), p.get('code', '')))


def usage_tier_price(code: str, cycle: str = 'monthly') -> int:
    tier = _USAGE_TIER_INDEX[code]
    if tier['purchase_mode'] != 'self_service':
        raise ValueError(f"{code} requires contact_sales/manual pricing")
    if cycle not in ('monthly', 'yearly'):
        raise ValueError(f"Invalid billing cycle: {cycle}")
    return tier['monthly_price' if cycle == 'monthly' else 'annual_price']


def plan_price(code: str, cycle: str = 'monthly', *, usage_tier: str | None = None) -> int:
    """Return canonical plan price in ARS pesos. Raises KeyError if not found."""
    key = f'price_{cycle}'
    p = _PLAN_INDEX[code]
    if p.get('pricing_mode') == 'usage_tier':
        if usage_tier is None or usage_tier not in p['usage_tiers']:
            raise ValueError(f"{code} requires a valid usage_tier")
        return usage_tier_price(usage_tier, cycle)
    return p[key]


def addon_price(code: str, cycle: str = 'monthly') -> int:
    key = f'price_{cycle}'
    a = _ADDON_INDEX[code]
    return a[key]


def extra_price(code: str, cycle: str = 'monthly') -> int:
    key = f'price_{cycle}'
    e = _EXTRA_INDEX[code]
    return e[key]


# ── Guards ────────────────────────────────────────────────────────────────────

# Any non-custom plan/addon/extra with a price below this is suspicious
# (likely still in centavos or a unit error).
def assert_not_centavos(value: int | float, label: str = '') -> None:
    """
    Raise ValueError if a price value looks like it's still in centavos.
    Intent: catch values like 99, 299, 499 that should be 36000, 50000, 75000.
    Allows 0 (custom/free plans).
    """
    if value == 0:
        return
    if value < MIN_SANE_PRICE:
        raise ValueError(
            f"Price guard: {label or 'value'} = {value} looks like centavos "
            f"(below MIN_SANE_PRICE={MIN_SANE_PRICE}). "
            f"Expected ARS pesos integer (e.g. 36000 for $36.000)."
        )


def assert_canonical_match(code: str, value: int, cycle: str = 'monthly') -> None:
    """
    Verify that a runtime price matches the canonical value.
    Raises ValueError on mismatch.
    """
    expected = None
    if code in _PLAN_INDEX:
        expected = plan_price(code, cycle)
    elif code in _ADDON_INDEX:
        expected = addon_price(code, cycle)
    elif code in _EXTRA_INDEX:
        expected = extra_price(code, cycle)
    else:
        raise ValueError(f"Price guard: unknown code '{code}' in canonical pricing.")

    if value != expected:
        raise ValueError(
            f"Price guard: {code} ({cycle}) = {value} does not match "
            f"canonical = {expected}."
        )


def price_to_decimal(pesos_int: int) -> Decimal:
    """Convert an ARS pesos integer to Decimal with 2 decimal places.
    e.g. 36000 → Decimal('36000.00')
    """
    return Decimal(str(pesos_int)).quantize(Decimal('0.01'))


def price_to_mp_float(pesos_int: int) -> float:
    """Convert an ARS pesos integer to float for Mercado Pago API.
    e.g. 36000 → 36000.0
    MP expects the amount in the currency's major unit (pesos).
    """
    return float(pesos_int)
