"""
tests/test_reviews_upgrade.py
=================================
Tests for the in-place upgrade from qr_reviews_base → qr_reviews_pro.

Covers:
  1. Successful upgrade → creates PendingSubscriptionChange + MP preference
  2. Non-owner gets 403
  3. Already Pro returns 409
  4. Non-reviews plan returns 400
  5. Idempotency: re-POST reuses existing pending change
  6. apply_reviews_plan_upgrade updates legacy + V2
  7. apply_reviews_plan_upgrade creates V2 when missing
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription as BizSubscription
from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
from apps.billing.reviews_views import apply_reviews_plan_upgrade

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = 'owner@test.com'):
    return User.objects.create_user(email=email, username=email, password='testpass1234')


def _make_business(owner, plan: str = 'qr_reviews_base', service: str = 'qr_reviews'):
    biz = Business.objects.create(name='Reviews Biz', default_service=service)
    BizSubscription.objects.create(business=biz, plan=plan, status='active')
    Membership.objects.create(user=owner, business=biz, role='owner')
    return biz


def _auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


UPGRADE_URL = '/api/v1/billing/reviews/upgrade/'


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class ReviewsUpgradeEndpointTests(TestCase):
    """POST /api/v1/billing/reviews/upgrade/"""

    def setUp(self):
        self.owner = _make_user()
        self.biz = _make_business(self.owner, plan='qr_reviews_base')
        self.client = _auth_client(self.owner)

    @patch('apps.billing.reviews_views.MercadoPagoService')
    def test_successful_upgrade_creates_preference(self, MockMP):
        MockMP.return_value.create_preference.return_value = {
            'id': 'pref-123',
            'init_point': 'https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref-123',
        }

        res = self.client.post(UPGRADE_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn('checkout_url', data)
        self.assertIn('pending_change_id', data)
        self.assertEqual(data['checkout_url'], 'https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref-123')

        # PendingSubscriptionChange created
        pending = PendingSubscriptionChange.objects.get(id=data['pending_change_id'])
        self.assertEqual(pending.target_plan_code, 'qr_reviews_pro')
        self.assertEqual(pending.status, 'pending_payment')
        self.assertEqual(pending.mp_preference_id, 'pref-123')

    def test_non_owner_gets_403(self):
        employee = _make_user('employee@test.com')
        Membership.objects.create(user=employee, business=self.biz, role='admin')
        client = _auth_client(employee)

        res = client.post(UPGRADE_URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_already_pro_returns_409(self):
        sub = self.biz.subscription
        sub.plan = 'qr_reviews_pro'
        sub.save()

        res = self.client.post(UPGRADE_URL)
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_non_reviews_plan_returns_400(self):
        sub = self.biz.subscription
        sub.plan = 'pro'  # Gestión Comercial plan, not reviews
        sub.save()

        res = self.client.post(UPGRADE_URL)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.billing.reviews_views.MercadoPagoService')
    def test_idempotency_reuses_existing_pending(self, MockMP):
        MockMP.return_value.create_preference.return_value = {
            'id': 'pref-first',
            'init_point': 'https://mp.com/first',
        }

        # First call
        res1 = self.client.post(UPGRADE_URL)
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        id1 = res1.json()['pending_change_id']

        # Second call — should reuse
        res2 = self.client.post(UPGRADE_URL)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        id2 = res2.json()['pending_change_id']
        self.assertEqual(id1, id2)

        # Only one PendingSubscriptionChange exists
        count = PendingSubscriptionChange.objects.filter(
            business=self.biz, target_plan_code='qr_reviews_pro',
        ).count()
        self.assertEqual(count, 1)

    @patch('apps.billing.reviews_views.MercadoPagoService')
    def test_qr_reviews_legacy_plan_can_upgrade(self, MockMP):
        """The legacy plan code 'qr_reviews' (without _base suffix) is also upgradeable."""
        sub = self.biz.subscription
        sub.plan = 'qr_reviews'
        sub.save()

        MockMP.return_value.create_preference.return_value = {
            'id': 'pref-legacy',
            'init_point': 'https://mp.com/legacy',
        }

        res = self.client.post(UPGRADE_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# apply_reviews_plan_upgrade tests
# ---------------------------------------------------------------------------

class ApplyReviewsPlanUpgradeTests(TestCase):
    """apply_reviews_plan_upgrade() — updates legacy + V2."""

    def setUp(self):
        self.owner = _make_user('apply@test.com')
        self.biz = _make_business(self.owner, plan='qr_reviews_base')

    def test_updates_legacy_subscription_plan(self):
        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')
        self.biz.subscription.refresh_from_db()
        self.assertEqual(self.biz.subscription.plan, 'qr_reviews_pro')

    def test_creates_v2_when_missing(self):
        self.assertFalse(
            SubscriptionV2.objects.filter(business=self.biz, service_type='qr_reviews').exists()
        )
        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')

        v2 = SubscriptionV2.objects.filter(business=self.biz, service_type='qr_reviews').first()
        self.assertIsNotNone(v2)
        self.assertEqual(v2.plan_code, 'qr_reviews_pro')
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)

    def test_updates_existing_v2(self):
        SubscriptionV2.objects.create(
            business=self.biz,
            service_type='qr_reviews',
            plan_code='qr_reviews_base',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            external_reference='SUB-existing-123',
            status=SubscriptionV2.Status.ACTIVE,
        )

        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')

        v2 = SubscriptionV2.objects.get(business=self.biz, service_type='qr_reviews')
        self.assertEqual(v2.plan_code, 'qr_reviews_pro')
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)

    def test_entitlements_resolve_after_upgrade(self):
        """After upgrade, is_reviews_pro returns True."""
        from apps.reviews.entitlements import is_reviews_pro
        self.assertFalse(is_reviews_pro(self.biz))

        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')
        self.biz.subscription.refresh_from_db()

        self.assertTrue(is_reviews_pro(self.biz))
