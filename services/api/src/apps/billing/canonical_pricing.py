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

def _load_pricing() -> dict:
    with open(_PRICING_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data.get('unit') == 'ARS_pesos_integer', (
        f"pricing.json unit must be 'ARS_pesos_integer', got '{data.get('unit')}'"
    )
    return data

_DATA = _load_pricing()

# ── Plans ─────────────────────────────────────────────────────────────────────

PLANS: List[dict] = _DATA['plans']
ADDONS: List[dict] = _DATA['addons']
EXTRAS: List[dict] = _DATA['extras']
PRODUCTS: List[dict] = _DATA.get('products', [])

_PLAN_INDEX: Dict[str, dict] = {p['code']: p for p in PLANS}
_ADDON_INDEX: Dict[str, dict] = {a['code']: a for a in ADDONS}
_EXTRA_INDEX: Dict[str, dict] = {e['code']: e for e in EXTRAS}
_PRODUCT_INDEX: Dict[str, dict] = {p['code']: p for p in PRODUCTS}


def get_plan(code: str) -> Optional[dict]:
    return _PLAN_INDEX.get(code)


def get_addon(code: str) -> Optional[dict]:
    return _ADDON_INDEX.get(code)


def get_extra(code: str) -> Optional[dict]:
    return _EXTRA_INDEX.get(code)


def get_product(code: str) -> Optional[dict]:
    return _PRODUCT_INDEX.get(code)


def get_products_catalog() -> List[dict]:
    """
    Return active products ordered by the canonical metadata in pricing.json.
    This is the backend source used by onboarding/service selectors.
    """
    products = [p for p in PRODUCTS if p.get('is_active', False)]
    return sorted(products, key=lambda p: (p.get('order', 999), p.get('code', '')))


def plan_price(code: str, cycle: str = 'monthly') -> int:
    """Return canonical plan price in ARS pesos. Raises KeyError if not found."""
    key = f'price_{cycle}'
    p = _PLAN_INDEX[code]
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
MIN_SANE_PRICE = 1000  # ARS $1.000 — lowest realistic price

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
