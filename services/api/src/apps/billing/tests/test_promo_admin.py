"""
tests/test_promo_admin.py
=========================
Tests for the platform admin promo-codes API:
  GET  /api/v1/platform-admin/promo-codes/
  POST /api/v1/platform-admin/promo-codes/
  GET  /api/v1/platform-admin/promo-codes/<id>/
  PATCH /api/v1/platform-admin/promo-codes/<id>/
  GET  /api/v1/platform-admin/promo-codes/<id>/redemptions/

Tests
-----
1. test_list_promo_codes_as_platform_staff      — GET 200, list returned
2. test_list_promo_codes_blocked_non_staff       — GET 403
3. test_create_valid_promo_code                 — POST 201, code uppercased
4. test_create_rejects_empty_plan_codes         — POST 400
5. test_create_rejects_yearly_period            — POST 400
6. test_patch_active_false                      — PATCH 200, active=False saved
7. test_list_redemptions                        — GET 200, redemption data returned
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.billing.models import (
    Plan,
    PromoCode,
    PromoCodeRedemption,
    SubscriptionV2,
)
from apps.business.models import Business
from apps.business.models import Subscription as BizSubscription
from apps.accounts.models import AccountProfile

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_staff_user(email='staff@mirubro.com'):
    user = User.objects.create_user(email=email, username=email, password='testpass')
    # Use a direct UPDATE to avoid ORM-level caching of the reverse accessor
    # that was set when the signal auto-created the profile with is_platform_staff=False.
    AccountProfile.objects.filter(user=user).update(
        is_platform_staff=True,
        internal_role='superadmin',
    )
    # Return a fresh instance so the cached 'account_profile' descriptor is clean.
    return User.objects.get(pk=user.pk)


def _make_regular_user(email='regular@mirubro.com'):
    return User.objects.create_user(email=email, username=email, password='testpass')


def _make_plan(code='gestion_pro'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults=dict(
            name='Pro Plan',
            price=Decimal('50000'),
            interval='monthly',
            currency='ARS',
            frequency=1,
            frequency_type='months',
            plan_status='active',
        ),
    )
    return plan


def _make_business(name='Admin Test Biz', service='gestion'):
    biz = Business.objects.create(
        name=name, default_service=service, service_type=service, status='active',
    )
    BizSubscription.objects.create(business=biz, plan='start', status='active')
    return biz


def _make_subscription(business, plan):
    return SubscriptionV2.objects.create(
        business=business,
        service_type=business.default_service,
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        external_reference=f"SUB-{uuid.uuid4()}",
        provider_sub_id=f"PREAPPROVAL-{uuid.uuid4()}",
        status=SubscriptionV2.Status.ACTIVE,
        is_active=True,
    )


def _make_promo(code='PROMO20', plan_code='gestion_pro', **kwargs):
    defaults = dict(
        name='20% Off',
        discount_type=PromoCode.DiscountType.PERCENT,
        discount_value=Decimal('20'),
        duration_cycles=2,
        active=True,
        applies_to_plan_codes=[plan_code],
        applies_to_billing_periods=['monthly'],
    )
    defaults.update(kwargs)
    return PromoCode.objects.create(code=code, **defaults)


def _make_redemption(promo, subscription):
    return PromoCodeRedemption.objects.create(
        promo_code=promo,
        business=subscription.business,
        subscription=subscription,
        original_amount=Decimal('50000.00'),
        discounted_amount=Decimal('40000.00'),
        cycles_total=2,
        cycles_used=1,
        status=PromoCodeRedemption.Status.ACTIVE,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Base test case
# ─────────────────────────────────────────────────────────────────────────────

class PromoAdminBaseTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user()
        self.regular = _make_regular_user()
        self.plan = _make_plan()
        self.biz = _make_business()
        self.client = APIClient()

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.staff)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class ListPromoCodesTest(PromoAdminBaseTest):
    def test_list_promo_codes_as_platform_staff(self):
        _make_promo('LIST1', 'gestion_pro')
        _make_promo('LIST2', 'gestion_pro')
        self._auth()
        resp = self.client.get('/api/v1/platform-admin/promo-codes/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('results', data)
        self.assertGreaterEqual(len(data['results']), 2)
        codes = {r['code'] for r in data['results']}
        self.assertIn('LIST1', codes)
        self.assertIn('LIST2', codes)

    def test_list_promo_codes_blocked_non_staff(self):
        self._auth(self.regular)
        resp = self.client.get('/api/v1/platform-admin/promo-codes/')
        self.assertEqual(resp.status_code, 403)


class CreatePromoCodeTest(PromoAdminBaseTest):
    def _payload(self, **overrides):
        data = {
            'code': 'newpromo',
            'name': 'New Promo',
            'discount_type': 'percent',
            'discount_value': '15.00',
            'duration_cycles': 3,
            'applies_to_plan_codes': ['gestion_pro'],
            'applies_to_billing_periods': ['monthly'],
            'active': True,
        }
        data.update(overrides)
        return data

    def test_create_valid_promo_code(self):
        self._auth()
        resp = self.client.post(
            '/api/v1/platform-admin/promo-codes/',
            data=self._payload(code='newpromo'),
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        # code should be uppercased
        self.assertEqual(data['code'], 'NEWPROMO')
        self.assertEqual(data['name'], 'New Promo')
        self.assertTrue(PromoCode.objects.filter(code='NEWPROMO').exists())

    def test_create_rejects_empty_plan_codes(self):
        self._auth()
        resp = self.client.post(
            '/api/v1/platform-admin/promo-codes/',
            data=self._payload(applies_to_plan_codes=[]),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('applies_to_plan_codes', resp.json())

    def test_create_rejects_yearly_period(self):
        self._auth()
        resp = self.client.post(
            '/api/v1/platform-admin/promo-codes/',
            data=self._payload(applies_to_billing_periods=['yearly']),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('applies_to_billing_periods', resp.json())


class PatchPromoCodeTest(PromoAdminBaseTest):
    def test_patch_active_false(self):
        promo = _make_promo('PATCHME', 'gestion_pro')
        self.assertTrue(promo.active)
        self._auth()
        resp = self.client.patch(
            f'/api/v1/platform-admin/promo-codes/{promo.pk}/',
            data={'active': False},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        promo.refresh_from_db()
        self.assertFalse(promo.active)
        self.assertFalse(resp.json()['active'])


class ListRedemptionsTest(PromoAdminBaseTest):
    def test_list_redemptions(self):
        promo = _make_promo('REDEEM1', 'gestion_pro')
        sub = _make_subscription(self.biz, self.plan)
        _make_redemption(promo, sub)
        self._auth()
        resp = self.client.get(f'/api/v1/platform-admin/promo-codes/{promo.pk}/redemptions/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('results', data)
        self.assertEqual(len(data['results']), 1)
        row = data['results'][0]
        self.assertEqual(row['business_id'], self.biz.pk)
        self.assertEqual(row['cycles_used'], 1)
        self.assertEqual(row['status'], 'active')


class PromoCodeOptionsTest(PromoAdminBaseTest):
    def test_options_returns_200_for_staff(self):
        _make_plan('gestion_pro')
        self._auth()
        resp = self.client.get('/api/v1/platform-admin/promo-codes/options/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('services', data)
        self.assertIn('plans', data)
        self.assertIn('billing_periods', data)
        self.assertIn('discount_types', data)
        # billing_periods MVP must only expose 'monthly'
        self.assertEqual([p['value'] for p in data['billing_periods']], ['monthly'])
        # Each plan entry has required keys
        for plan in data['plans']:
            self.assertIn('code', plan)
            self.assertIn('label', plan)
            self.assertIn('service', plan)
            self.assertIn('billing_period', plan)
            self.assertIn('price', plan)

    def test_options_returns_403_for_non_staff(self):
        self._auth(self.regular)
        resp = self.client.get('/api/v1/platform-admin/promo-codes/options/')
        self.assertEqual(resp.status_code, 403)

    def test_options_only_includes_active_monthly_plans(self):
        from apps.billing.models import Plan as PlanModel
        _make_plan('gestion_pro')
        # Create an inactive plan — should be excluded
        PlanModel.objects.create(
            code='gestion_inactive_test',
            name='Inactive Plan',
            price=99999,
            interval='monthly',
            currency='ARS',
            frequency=1,
            frequency_type='months',
            plan_status='inactive',
        )
        # Create a yearly plan — should be excluded
        PlanModel.objects.create(
            code='gestion_yearly_test',
            name='Yearly Plan',
            price=500000,
            interval='yearly',
            currency='ARS',
            frequency=12,
            frequency_type='months',
            plan_status='active',
        )
        self._auth()
        resp = self.client.get('/api/v1/platform-admin/promo-codes/options/')
        self.assertEqual(resp.status_code, 200)
        codes = [p['code'] for p in resp.json()['plans']]
        self.assertNotIn('gestion_inactive_test', codes)
        self.assertNotIn('gestion_yearly_test', codes)
        self.assertIn('gestion_pro', codes)

    def test_options_includes_qr_reviews_pro(self):
        """qr_reviews_pro active monthly plan appears in options."""
        from decimal import Decimal as D
        from apps.billing.models import Plan as PlanModel
        PlanModel.objects.update_or_create(
            code='qr_reviews_pro',
            defaults=dict(
                name='Reseñas Pro',
                price=D('28000'),
                interval='monthly',
                currency='ARS',
                frequency=1,
                frequency_type='months',
                plan_status='active',
            ),
        )
        self._auth()
        resp = self.client.get('/api/v1/platform-admin/promo-codes/options/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        codes = [p['code'] for p in data['plans']]
        self.assertIn('qr_reviews_pro', codes)
        plan = next(p for p in data['plans'] if p['code'] == 'qr_reviews_pro')
        self.assertEqual(plan['service'], 'qr_reviews')
        self.assertEqual(plan['service_label'], 'Reseñas QR')
        self.assertEqual(plan['billing_period'], 'monthly')

    def test_options_service_label_present_on_all_plans(self):
        """Every plan entry includes the service_label key."""
        _make_plan('gestion_pro')
        self._auth()
        resp = self.client.get('/api/v1/platform-admin/promo-codes/options/')
        self.assertEqual(resp.status_code, 200)
        for plan in resp.json()['plans']:
            self.assertIn('service_label', plan)

    def test_services_no_duplicate_labels_for_qr_reviews(self):
        """Plans with code 'qr_reviews' and 'qr_reviews_pro' both map to
        service='qr_reviews' — only one services entry is returned."""
        from decimal import Decimal as D
        from apps.billing.models import Plan as PlanModel
        PlanModel.objects.update_or_create(
            code='qr_reviews',
            defaults=dict(name='QR de Reseñas', price=D('20000'), interval='monthly',
                          currency='ARS', frequency=1, frequency_type='months', plan_status='active'),
        )
        PlanModel.objects.update_or_create(
            code='qr_reviews_pro',
            defaults=dict(name='Reseñas Pro', price=D('28000'), interval='monthly',
                          currency='ARS', frequency=1, frequency_type='months', plan_status='active'),
        )
        self._auth()
        resp = self.client.get('/api/v1/platform-admin/promo-codes/options/')
        self.assertEqual(resp.status_code, 200)
        service_values = [s['value'] for s in resp.json()['services']]
        # Both plans belong to the same canonical service slug
        self.assertEqual(service_values.count('qr_reviews'), 1)
        # The label must not be the raw fallback "Qr"
        service_labels = [s['label'] for s in resp.json()['services']]
        self.assertNotIn('Qr', service_labels)
        self.assertIn('Reseñas QR', service_labels)

    def test_create_promo_with_qr_reviews_pro_plan(self):
        """A promo code can be created with qr_reviews_pro as an applies_to_plan_codes entry."""
        self._auth()
        payload = {
            'code': 'REVPRO10',
            'name': 'Desc Reseñas Pro',
            'discount_type': 'percent',
            'discount_value': '10.00',
            'duration_cycles': 2,
            'applies_to_plan_codes': ['qr_reviews_pro'],
            'applies_to_billing_periods': ['monthly'],
            'active': True,
        }
        resp = self.client.post('/api/v1/platform-admin/promo-codes/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data['code'], 'REVPRO10')
        self.assertEqual(data['applies_to_plan_codes'], ['qr_reviews_pro'])
