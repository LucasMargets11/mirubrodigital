"""
tests/test_promo_codes.py
=========================
Unit tests for the PromoCode + PromoCodeRedemption models and promo_service.

Coverage
--------
  1.  Happy path: percent discount, single plan
  2.  Happy path: fixed_amount discount
  3.  Code not found → CODE_NOT_FOUND
  4.  Code inactive → CODE_INACTIVE
  5.  Code not yet started → CODE_NOT_STARTED
  6.  Code expired → CODE_EXPIRED
  7.  Plan not in applies_to_plan_codes → PLAN_NOT_ELIGIBLE
  8.  Empty applies_to_plan_codes → PLAN_NOT_ELIGIBLE (must specify at least one plan)
  9.  Billing period not in applies_to_billing_periods → BILLING_PERIOD_NOT_ELIGIBLE
 10.  Empty applies_to_billing_periods → BILLING_PERIOD_NOT_ELIGIBLE (must specify at least one period)
 11.  Service not matching → SERVICE_NOT_ELIGIBLE
 12.  Global max_redemptions reached → MAX_REDEMPTIONS_REACHED
 13.  Per-business limit reached → ALREADY_USED_BY_BUSINESS
 14.  compute_discounted_amount: percent — result never negative
 15.  compute_discounted_amount: fixed_amount — clamp at zero
 16.  PromoCodeRedemption DB unique constraint: duplicate pending/active blocked
 17.  PromoCodeRedemption DB unique constraint: completed + new pending allowed
 18.  Case-insensitive code lookup (lowercase input, uppercase DB entry)
 19.  Empty code string → CODE_NOT_FOUND
 20.  Yearly billing_period always rejected (MVP rule) → BILLING_PERIOD_NOT_ELIGIBLE
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import Plan, PromoCode, PromoCodeRedemption
from apps.billing.promo_service import (
    ALREADY_USED_BY_BUSINESS,
    BILLING_PERIOD_NOT_ELIGIBLE,
    CODE_EXPIRED,
    CODE_INACTIVE,
    CODE_NOT_FOUND,
    CODE_NOT_STARTED,
    MAX_REDEMPTIONS_REACHED,
    PLAN_NOT_ELIGIBLE,
    SERVICE_NOT_ELIGIBLE,
    validate_promo_code,
)
from apps.business.models import Business
from apps.business.models import Subscription as BizSubscription

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Shared factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email='promo@test.com'):
    return User.objects.create_user(email=email, username=email, password='testpass1234')


def _make_plan(code='start', price=29900):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults=dict(
            name='Start Plan',
            price=Decimal(str(price)),
            interval='monthly',
            currency='ARS',
            frequency=1,
            frequency_type='months',
            plan_status='active',
        ),
    )
    return plan


def _make_business(name='Test Biz', service='gestion'):
    biz = Business.objects.create(name=name, default_service=service, service_type=service)
    BizSubscription.objects.create(business=biz, plan='start', status='active')
    return biz


def _make_promo(code='PROMO10', **kwargs):
    defaults = dict(
        name='10% Off',
        discount_type=PromoCode.DiscountType.PERCENT,
        discount_value=Decimal('10.00'),
        duration_cycles=1,
        active=True,
        applies_to_plan_codes=['start'],
        applies_to_billing_periods=['monthly'],
    )
    defaults.update(kwargs)
    return PromoCode.objects.create(code=code, **defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class PromoServiceValidationTests(TestCase):

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business()

    def _validate(self, code='PROMO10', plan_code='start', billing_period='monthly', business=None):
        return validate_promo_code(
            code=code,
            plan_code=plan_code,
            billing_period=billing_period,
            business=business or self.business,
            plan_price=self.plan.price,
        )

    # ── 1. Happy path: percent discount ──────────────────────────────────────

    def test_valid_percent_discount(self):
        _make_promo(code='PCT10', discount_type='percent', discount_value=Decimal('10'))
        result = self._validate(code='PCT10')

        self.assertTrue(result['valid'])
        self.assertEqual(result['discount_type'], 'percent')
        self.assertEqual(result['discount_value'], Decimal('10'))
        self.assertEqual(result['duration_cycles'], 1)
        self.assertEqual(result['original_amount'], Decimal('29900.00'))
        # 29900 * 0.90 = 26910.00
        self.assertEqual(result['discounted_amount'], Decimal('26910.00'))
        self.assertIn('summary', result)
        self.assertIsNotNone(result['promo_code'])

    # ── 2. Happy path: fixed_amount discount ─────────────────────────────────

    def test_valid_fixed_amount_discount(self):
        _make_promo(
            code='FIXED5000',
            discount_type='fixed_amount',
            discount_value=Decimal('5000'),
        )
        result = self._validate(code='FIXED5000')

        self.assertTrue(result['valid'])
        self.assertEqual(result['discounted_amount'], Decimal('24900.00'))

    # ── 3. Code not found ─────────────────────────────────────────────────────

    def test_code_not_found(self):
        result = self._validate(code='NONEXISTENT')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], CODE_NOT_FOUND)

    # ── 4. Code inactive ─────────────────────────────────────────────────────

    def test_code_inactive(self):
        _make_promo(code='INACTIVE', active=False)
        result = self._validate(code='INACTIVE')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], CODE_INACTIVE)

    # ── 5. Code not yet started ───────────────────────────────────────────────

    def test_code_not_started(self):
        future = timezone.now() + timedelta(days=7)
        _make_promo(code='FUTURE', starts_at=future)
        result = self._validate(code='FUTURE')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], CODE_NOT_STARTED)

    # ── 6. Code expired ───────────────────────────────────────────────────────

    def test_code_expired(self):
        past = timezone.now() - timedelta(days=1)
        _make_promo(code='EXPIRED', ends_at=past)
        result = self._validate(code='EXPIRED')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], CODE_EXPIRED)

    # ── 7. Plan not eligible ──────────────────────────────────────────────────

    def test_plan_not_eligible(self):
        _make_promo(code='PLANONLY', applies_to_plan_codes=['pro'])
        result = self._validate(code='PLANONLY', plan_code='start')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], PLAN_NOT_ELIGIBLE)

    # ── 8. Empty applies_to_plan_codes = invalid (must specify at least one plan) ──

    def test_empty_plan_codes_is_invalid(self):
        _make_promo(code='OPENPLAN', applies_to_plan_codes=[])
        result = self._validate(code='OPENPLAN', plan_code='start')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], PLAN_NOT_ELIGIBLE)

    # ── 9. Billing period not eligible ───────────────────────────────────────

    def test_billing_period_not_eligible(self):
        _make_promo(code='MONTHLY_ONLY', applies_to_billing_periods=['monthly'])
        result = self._validate(code='MONTHLY_ONLY', billing_period='yearly')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], BILLING_PERIOD_NOT_ELIGIBLE)

    # ── 10. Empty applies_to_billing_periods = invalid (must specify at least one period) ──

    def test_empty_billing_periods_is_invalid(self):
        # billing_period='monthly' passes the MVP hard rule but empty list is still rejected
        _make_promo(code='ANYPERIOD', applies_to_billing_periods=[])
        result = self._validate(code='ANYPERIOD', billing_period='monthly')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], BILLING_PERIOD_NOT_ELIGIBLE)

    # ── 11. Service not eligible ──────────────────────────────────────────────

    def test_service_not_eligible(self):
        _make_promo(code='GESTION_ONLY', applies_to_service='gestion')
        biz_restaurant = _make_business(name='Restaurant Biz', service='restaurante')
        result = validate_promo_code(
            code='GESTION_ONLY',
            plan_code='start',
            billing_period='monthly',
            business=biz_restaurant,
            plan_price=self.plan.price,
        )
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], SERVICE_NOT_ELIGIBLE)

    def test_service_eligible_matching(self):
        _make_promo(code='GESTION2', applies_to_service='gestion')
        # self.business has service_type='gestion'
        result = self._validate(code='GESTION2')
        self.assertTrue(result['valid'])

    # ── 12. Global max_redemptions reached ───────────────────────────────────

    def test_global_max_redemptions_reached(self):
        promo = _make_promo(code='LIMITED', max_redemptions=2)
        other_biz1 = _make_business(name='Biz A')
        other_biz2 = _make_business(name='Biz B')
        plan = _make_plan()
        # Create 2 completed redemptions (counts toward the limit)
        for biz in [other_biz1, other_biz2]:
            PromoCodeRedemption.objects.create(
                promo_code=promo,
                business=biz,
                original_amount=Decimal('29900'),
                discounted_amount=Decimal('26910'),
                cycles_total=1,
                status=PromoCodeRedemption.Status.COMPLETED,
            )

        result = self._validate(code='LIMITED')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], MAX_REDEMPTIONS_REACHED)

    # ── 13. Per-business limit reached ───────────────────────────────────────

    def test_per_business_limit_reached(self):
        promo = _make_promo(code='ONCE_PER_BIZ', max_redemptions_per_business=1)
        PromoCodeRedemption.objects.create(
            promo_code=promo,
            business=self.business,
            original_amount=Decimal('29900'),
            discounted_amount=Decimal('26910'),
            cycles_total=1,
            status=PromoCodeRedemption.Status.ACTIVE,
        )

        result = self._validate(code='ONCE_PER_BIZ')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], ALREADY_USED_BY_BUSINESS)

    # ── 14. Percent discount never negative ──────────────────────────────────

    def test_percent_discount_never_negative(self):
        promo = _make_promo(code='FULL', discount_value=Decimal('100'))
        result = self._validate(code='FULL')
        self.assertTrue(result['valid'])
        self.assertEqual(result['discounted_amount'], Decimal('0.00'))

    # ── 15. Fixed amount clamped at zero ─────────────────────────────────────

    def test_fixed_amount_clamp_at_zero(self):
        promo = _make_promo(
            code='HUGE',
            discount_type='fixed_amount',
            discount_value=Decimal('999999'),
        )
        result = self._validate(code='HUGE')
        self.assertTrue(result['valid'])
        self.assertEqual(result['discounted_amount'], Decimal('0.00'))

    # ── 16. DB unique constraint: duplicate pending blocked ───────────────────

    def test_db_unique_constraint_blocks_second_pending(self):
        promo = _make_promo(code='ONCE')
        PromoCodeRedemption.objects.create(
            promo_code=promo,
            business=self.business,
            original_amount=Decimal('29900'),
            discounted_amount=Decimal('26910'),
            cycles_total=1,
            status=PromoCodeRedemption.Status.PENDING,
        )
        with self.assertRaises(IntegrityError):
            PromoCodeRedemption.objects.create(
                promo_code=promo,
                business=self.business,
                original_amount=Decimal('29900'),
                discounted_amount=Decimal('26910'),
                cycles_total=1,
                status=PromoCodeRedemption.Status.PENDING,
            )

    # ── 17. Completed + new pending allowed ───────────────────────────────────

    def test_db_completed_allows_new_pending_for_different_promo(self):
        """After a completed redemption, a second promo code can be redeemed."""
        promo1 = _make_promo(code='PROMO_A')
        promo2 = _make_promo(code='PROMO_B')
        PromoCodeRedemption.objects.create(
            promo_code=promo1,
            business=self.business,
            original_amount=Decimal('29900'),
            discounted_amount=Decimal('26910'),
            cycles_total=1,
            status=PromoCodeRedemption.Status.COMPLETED,
        )
        # Should not raise — different promo code, and promo1 is completed (not counted in constraint)
        r = PromoCodeRedemption.objects.create(
            promo_code=promo2,
            business=self.business,
            original_amount=Decimal('29900'),
            discounted_amount=Decimal('26910'),
            cycles_total=1,
            status=PromoCodeRedemption.Status.PENDING,
        )
        self.assertIsNotNone(r.pk)

    # ── 18. Case-insensitive lookup ───────────────────────────────────────────

    def test_case_insensitive_code(self):
        _make_promo(code='MYCODE')
        result = self._validate(code='mycode')
        self.assertTrue(result['valid'])

        result_mixed = self._validate(code='MyCode')
        self.assertTrue(result_mixed['valid'])

    # ── 19. Empty code string ─────────────────────────────────────────────────

    def test_empty_code_returns_not_found(self):
        result = self._validate(code='')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], CODE_NOT_FOUND)

    def test_whitespace_code_returns_not_found(self):
        result = self._validate(code='   ')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], CODE_NOT_FOUND)

    # ── 20. Yearly billing period always rejected by MVP rule ─────────────────

    def test_yearly_billing_period_is_invalid(self):
        # MVP rule: 'yearly' is always rejected regardless of what the promo allows.
        _make_promo(code='YEARLYTRY', applies_to_billing_periods=['monthly', 'yearly'])
        result = self._validate(code='YEARLYTRY', billing_period='yearly')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error_code'], BILLING_PERIOD_NOT_ELIGIBLE)


class PromoCodeModelTests(TestCase):

    def test_compute_discounted_percent(self):
        promo = PromoCode(
            code='X', name='X', discount_type='percent', discount_value=Decimal('25'),
            duration_cycles=1, applies_to_plan_codes=['start'],
        )
        result = promo.compute_discounted_amount(Decimal('40000'))
        self.assertEqual(result, Decimal('30000.00'))

    def test_compute_discounted_fixed(self):
        promo = PromoCode(
            code='X', name='X', discount_type='fixed_amount', discount_value=Decimal('10000'),
            duration_cycles=1, applies_to_plan_codes=['start'],
        )
        result = promo.compute_discounted_amount(Decimal('29900'))
        self.assertEqual(result, Decimal('19900.00'))

    def test_compute_discounted_fixed_clamp(self):
        promo = PromoCode(
            code='X', name='X', discount_type='fixed_amount', discount_value=Decimal('50000'),
            duration_cycles=1, applies_to_plan_codes=['start'],
        )
        result = promo.compute_discounted_amount(Decimal('29900'))
        self.assertEqual(result, Decimal('0.00'))
