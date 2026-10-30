import copy
import json
from unittest import TestCase

from apps.billing import canonical_pricing as pricing


class AppointmentsCanonicalPricingTests(TestCase):
    def test_plans_prices_and_included_resources(self):
        for code, monthly, annual, included in (
            ('appointments', 23000, 220800, 2),
            ('appointments_pro', 28000, 268800, 5),
        ):
            with self.subTest(code=code):
                self.assertEqual(pricing.plan_price(code), monthly)
                self.assertEqual(pricing.plan_price(code, 'yearly'), annual)
                self.assertEqual(annual * 5, monthly * 48)
                plan = pricing.get_plan(code)
                self.assertEqual(plan['professionals_included'], included)
                self.assertEqual(plan['secondary_users_included'], included)
        self.assertIsNone(pricing.get_plan('appointments_base'))
        self.assertIsNone(pricing.get_plan('ai_300'))

    def test_complete_ia_tier_prices_overage_and_caps(self):
        for code, monthly, annual, included, overage, cap in (
            ('ai_300', 150000, 1440000, 300, 300, 75000),
            ('ai_1500', 275000, 2640000, 1500, 200, 137500),
            ('ai_3000', 385000, 3696000, 3000, 160, 192500),
        ):
            with self.subTest(code=code):
                self.assertEqual(pricing.plan_price('appointments_ai', usage_tier=code), monthly)
                self.assertEqual(pricing.plan_price('appointments_ai', 'yearly', usage_tier=code), annual)
                self.assertEqual(annual * 5, monthly * 48)
                tier = pricing.get_usage_tier(code)
                self.assertEqual(tier['included_conversations'], included)
                self.assertEqual(tier['extra_conversation_price'], overage)
                self.assertEqual(tier['default_extra_spend_limit'], cap)
                self.assertLess(overage, pricing.MIN_SANE_PRICE)

    def test_ia_includes_pro_and_automations_without_surcharges(self):
        ai = pricing.get_plan('appointments_ai')
        self.assertIsNone(ai['price_monthly'])
        self.assertIsNone(ai['price_yearly'])
        self.assertEqual(ai['includes_plans'], ['appointments_pro'])
        self.assertEqual(ai['included_addons'], ['appointments_automations'])
        self.assertEqual(ai['usage_tiers'], ['ai_300', 'ai_1500', 'ai_3000', 'custom'])
        with self.assertRaises(ValueError):
            pricing.plan_price('appointments_ai')
        with self.assertRaises(ValueError):
            pricing.plan_price('appointments_ai', usage_tier='missing')

    def test_automations_and_quantity_extra(self):
        self.assertEqual(pricing.addon_price('appointments_automations'), 8500)
        self.assertEqual(pricing.addon_price('appointments_automations', 'yearly'), 81600)
        addon = pricing.get_addon('appointments_automations')
        self.assertEqual(addon['available_for'], ['appointments', 'appointments_pro'])
        self.assertEqual(addon['included_in'], ['appointments_ai'])
        self.assertEqual(pricing.extra_price('appointments_extra_professional'), 3000)
        self.assertEqual(pricing.extra_price('appointments_extra_professional', 'yearly'), 28800)
        extra = pricing.get_extra('appointments_extra_professional')
        self.assertEqual(extra['quantity_min'], 0)
        self.assertEqual(extra['quantity_step'], 1)
        self.assertIsNone(pricing.get_addon('appointments_extra_professional'))

    def test_custom_is_manual_without_a_zero_price_fallback(self):
        custom = pricing.get_usage_tier('custom')
        self.assertEqual(custom['purchase_mode'], 'contact_sales')
        self.assertEqual(custom['billing_mode'], 'manual')
        for key in ('monthly_price', 'annual_price', 'extra_conversation_price'):
            self.assertIsNone(custom[key])
        for cycle in ('monthly', 'yearly'):
            with self.assertRaises(ValueError):
                pricing.plan_price('appointments_ai', cycle, usage_tier='custom')
            with self.assertRaises(ValueError):
                pricing.usage_tier_price('custom', cycle)

    def test_product_is_not_public_or_purchasable(self):
        self.assertFalse(pricing.get_product('appointments')['is_active'])
        self.assertNotIn('appointments', [p['code'] for p in pricing.get_products_catalog()])
        for code in ('appointments', 'appointments_pro', 'appointments_ai'):
            self.assertFalse(pricing.is_plan_product_active(code))
        for code in ('gestion_start', 'menu_qr_basico', 'qr_reviews_base', 'resto_basic'):
            self.assertTrue(pricing.is_plan_product_active(code))

    def test_generated_json_is_valid_and_all_sections_load(self):
        with pricing._PRICING_JSON_PATH.open(encoding='utf-8') as source:
            data = json.load(source)
        pricing.validate_appointments_catalog(data)
        self.assertEqual(set(pricing.get_appointments_catalog()), {
            'product', 'plans', 'addons', 'extras', 'usage_tiers',
        })

    def test_validator_rejects_non_integer_money_wrong_discount_and_custom_zero(self):
        with pricing._PRICING_JSON_PATH.open(encoding='utf-8') as source:
            data = json.load(source)
        for section, code, field, invalid in (
            ('plans', 'appointments', 'price_monthly', 23000.0),
            ('plans', 'appointments_pro', 'price_yearly', 268801),
            ('addons', 'appointments_automations', 'price_yearly', 81601),
            ('extras', 'appointments_extra_professional', 'price_yearly', 28801),
            ('extras', 'appointments_extra_professional', 'quantity_min', -1),
            ('extras', 'appointments_extra_professional', 'quantity_step', True),
            ('usage_tiers', 'ai_300', 'annual_price', 1440001),
            ('usage_tiers', 'ai_1500', 'extra_conversation_price', 200.5),
            ('usage_tiers', 'ai_3000', 'default_extra_spend_limit', -1),
            ('usage_tiers', 'custom', 'monthly_price', 0),
            ('usage_tiers', 'custom', 'purchase_mode', 'self_service'),
        ):
            with self.subTest(section=section, code=code, field=field):
                invalid_data = copy.deepcopy(data)
                row = next(row for row in invalid_data[section] if row['code'] == code)
                row[field] = invalid
                with self.assertRaises(ValueError):
                    pricing.validate_appointments_catalog(invalid_data)
