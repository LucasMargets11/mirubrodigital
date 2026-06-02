"""
Tests for the canonical pricing layer (Deploy 3).

Verifies:
  - canonical_pricing.py loads correctly and returns expected values
  - Guards catch centavo-like values
  - commercial_plans.py prices match canonical
  - price_to_decimal / price_to_mp_float conversions are correct
  - Parity: PLANS, ADDONS, extras all delegate to canonical
"""
from __future__ import annotations

from decimal import Decimal
from unittest import TestCase

from apps.billing.canonical_pricing import (
    ADDONS,
    EXTRAS,
    MIN_SANE_PRICE,
    PLANS,
    addon_price,
    assert_canonical_match,
    assert_not_centavos,
    extra_price,
    get_addon,
    get_extra,
    get_plan,
    plan_price,
    price_to_decimal,
    price_to_mp_float,
)


class TestCanonicalPricingLoad(TestCase):
    """pricing.json loads and indexes are populated."""

    def test_plans_loaded(self):
        self.assertGreaterEqual(len(PLANS), 9)

    def test_addons_loaded(self):
        self.assertGreaterEqual(len(ADDONS), 4)

    def test_extras_loaded(self):
        self.assertGreaterEqual(len(EXTRAS), 2)

    def test_unit_is_pesos(self):
        # Module-level assertion would have failed on import if wrong,
        # but let's verify the data is accessible.
        self.assertIsNotNone(get_plan('gestion_start'))


class TestPlanPrices(TestCase):
    """Spot-check canonical plan prices (ARS pesos integers)."""

    def test_gestion_start_monthly(self):
        self.assertEqual(plan_price('gestion_start', 'monthly'), 36000)

    def test_gestion_start_yearly(self):
        self.assertEqual(plan_price('gestion_start', 'yearly'), 345600)

    def test_gestion_pro_monthly(self):
        self.assertEqual(plan_price('gestion_pro', 'monthly'), 50000)

    def test_gestion_business_monthly(self):
        self.assertEqual(plan_price('gestion_business', 'monthly'), 75000)

    def test_gestion_enterprise_is_zero(self):
        self.assertEqual(plan_price('gestion_enterprise', 'monthly'), 0)

    def test_menu_qr_basico(self):
        self.assertEqual(plan_price('menu_qr_basico', 'monthly'), 18000)

    def test_menu_qr_visual(self):
        self.assertEqual(plan_price('menu_qr_visual', 'monthly'), 30000)

    def test_menu_qr_marca(self):
        self.assertEqual(plan_price('menu_qr_marca', 'monthly'), 55000)

    def test_qr_reviews_base(self):
        self.assertEqual(plan_price('qr_reviews_base', 'monthly'), 20000)
        self.assertEqual(plan_price('qr_reviews_base', 'yearly'), 192000)

    def test_qr_reviews_pro(self):
        self.assertEqual(plan_price('qr_reviews_pro', 'monthly'), 28000)
        self.assertEqual(plan_price('qr_reviews_pro', 'yearly'), 268800)

    def test_unknown_plan_raises(self):
        with self.assertRaises(KeyError):
            plan_price('nonexistent_plan')


class TestAddonPrices(TestCase):

    def test_crm_monthly(self):
        self.assertEqual(addon_price('crm', 'monthly'), 8000)

    def test_invoicing_monthly(self):
        self.assertEqual(addon_price('invoicing', 'monthly'), 15000)

    def test_qr_reviews_addon(self):
        self.assertEqual(addon_price('qr_reviews', 'monthly'), 12000)

    def test_qr_tips_addon(self):
        self.assertEqual(addon_price('qr_tips', 'monthly'), 12000)


class TestExtraPrices(TestCase):

    def test_extra_branch_monthly(self):
        self.assertEqual(extra_price('extra_branch', 'monthly'), 12000)

    def test_extra_user_monthly(self):
        self.assertEqual(extra_price('extra_user', 'monthly'), 5000)

    def test_extra_branch_yearly(self):
        self.assertEqual(extra_price('extra_branch', 'yearly'), 115200)

    def test_extra_user_yearly(self):
        self.assertEqual(extra_price('extra_user', 'yearly'), 48000)


class TestGuards(TestCase):
    """assert_not_centavos and assert_canonical_match."""

    def test_zero_is_allowed(self):
        assert_not_centavos(0, 'free')  # Should not raise

    def test_valid_pesos_allowed(self):
        assert_not_centavos(36000, 'starter')  # Should not raise

    def test_min_sane_price_boundary(self):
        assert_not_centavos(MIN_SANE_PRICE, 'boundary')  # Exactly at min — ok

    def test_centavo_value_raises(self):
        with self.assertRaises(ValueError) as ctx:
            assert_not_centavos(99, 'starter_centavos')
        self.assertIn('looks like centavos', str(ctx.exception))

    def test_old_pro_centavo_raises(self):
        with self.assertRaises(ValueError):
            assert_not_centavos(299, 'pro_centavos')

    def test_canonical_match_correct(self):
        assert_canonical_match('gestion_start', 36000, 'monthly')  # ok

    def test_canonical_match_wrong_value(self):
        with self.assertRaises(ValueError):
            assert_canonical_match('gestion_start', 9900, 'monthly')

    def test_canonical_match_unknown_code(self):
        with self.assertRaises(ValueError):
            assert_canonical_match('nonexistent', 100, 'monthly')

    def test_canonical_match_addon(self):
        assert_canonical_match('crm', 8000, 'monthly')  # Should not raise

    def test_canonical_match_extra(self):
        assert_canonical_match('extra_branch', 12000, 'monthly')


class TestConverters(TestCase):

    def test_price_to_decimal(self):
        self.assertEqual(price_to_decimal(36000), Decimal('36000.00'))

    def test_price_to_decimal_zero(self):
        self.assertEqual(price_to_decimal(0), Decimal('0.00'))

    def test_price_to_mp_float(self):
        self.assertEqual(price_to_mp_float(36000), 36000.0)
        self.assertIsInstance(price_to_mp_float(36000), float)

    def test_price_to_mp_float_zero(self):
        self.assertEqual(price_to_mp_float(0), 0.0)


class TestCommercialPlansParity(TestCase):
    """Verify commercial_plans.py delegates to canonical and values match."""

    def test_plans_prices_match_canonical(self):
        from apps.billing.commercial_plans import PLANS

        canonical_map = {
            'gestion_start': (36000, 345600),
            'gestion_pro': (50000, 480000),
            'gestion_business': (75000, 720000),
            'gestion_enterprise': (0, 0),
        }
        for p in PLANS:
            code = p['code']
            if code in canonical_map:
                expected_m, expected_y = canonical_map[code]
                self.assertEqual(
                    p['pricing']['monthly'], expected_m,
                    f"{code} monthly mismatch"
                )
                self.assertEqual(
                    p['pricing']['yearly'], expected_y,
                    f"{code} yearly mismatch"
                )

    def test_addon_crm_matches(self):
        from apps.billing.commercial_plans import ADDONS as CP_ADDONS

        crm = next(a for a in CP_ADDONS if a['code'] == 'crm')
        self.assertEqual(crm['pricing']['monthly'], 8000)
        self.assertEqual(crm['pricing']['yearly'], 76800)

    def test_addon_invoicing_matches(self):
        from apps.billing.commercial_plans import ADDONS as CP_ADDONS

        inv = next(a for a in CP_ADDONS if a['code'] == 'invoicing')
        self.assertEqual(inv['pricing']['monthly'], 15000)
        self.assertEqual(inv['pricing']['yearly'], 144000)

    def test_branch_extra_matches(self):
        from apps.billing.commercial_plans import BRANCH_EXTRA_PRICING

        self.assertEqual(BRANCH_EXTRA_PRICING['monthly'], 12000)
        self.assertEqual(BRANCH_EXTRA_PRICING['yearly'], 115200)

    def test_seat_extra_matches(self):
        from apps.billing.commercial_plans import SEAT_EXTRA_PRICING

        self.assertEqual(SEAT_EXTRA_PRICING['monthly'], 5000)
        self.assertEqual(SEAT_EXTRA_PRICING['yearly'], 48000)


class TestNoMoreCentavoDivisions(TestCase):
    """Sanity: all canonical prices should be >= MIN_SANE_PRICE or zero."""

    def test_all_plan_prices_sane(self):
        for p in PLANS:
            for cycle in ('monthly', 'yearly'):
                val = p[f'price_{cycle}']
                if val == 0:
                    continue  # custom/free
                self.assertGreaterEqual(
                    val, MIN_SANE_PRICE,
                    f"Plan {p['code']} {cycle} = {val} is suspiciously low"
                )

    def test_all_addon_prices_sane(self):
        for a in ADDONS:
            for cycle in ('monthly', 'yearly'):
                val = a[f'price_{cycle}']
                if val == 0:
                    continue
                self.assertGreaterEqual(
                    val, MIN_SANE_PRICE,
                    f"Addon {a['code']} {cycle} = {val} is suspiciously low"
                )

    def test_all_extra_prices_sane(self):
        for e in EXTRAS:
            for cycle in ('monthly', 'yearly'):
                val = e[f'price_{cycle}']
                if val == 0:
                    continue
                self.assertGreaterEqual(
                    val, MIN_SANE_PRICE,
                    f"Extra {e['code']} {cycle} = {val} is suspiciously low"
                )
