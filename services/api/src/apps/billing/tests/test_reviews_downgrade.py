"""
tests/test_reviews_downgrade.py
=================================
Tests for the downgrade from qr_reviews_pro → qr_reviews_base.

Covers:
  1. Successful downgrade with confirm=True
  2. Non-owner gets 403
  3. Already Base returns 409
  4. Non-reviews plan returns 400
  5. Missing confirm returns 400
  6. apply_reviews_plan_downgrade updates legacy + V2
  7. Entitlements resolve correctly after downgrade
  8. PendingSubscriptionChange audit record created
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription as BizSubscription
from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
from apps.billing.reviews_views import apply_reviews_plan_downgrade

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = 'owner@test.com'):
    return User.objects.create_user(email=email, username=email, password='testpass1234')


def _make_business(owner, plan: str = 'qr_reviews_pro', service: str = 'qr_reviews'):
    biz = Business.objects.create(name='Reviews Biz', default_service=service)
    BizSubscription.objects.create(business=biz, plan=plan, status='active')
    Membership.objects.create(user=owner, business=biz, role='owner')
    return biz


def _auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


DOWNGRADE_URL = '/api/v1/billing/reviews/downgrade/'


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class ReviewsDowngradeEndpointTests(TestCase):
    """POST /api/v1/billing/reviews/downgrade/"""

    def setUp(self):
        self.owner = _make_user()
        self.biz = _make_business(self.owner, plan='qr_reviews_pro')
        self.client = _auth_client(self.owner)

    def test_successful_downgrade(self):
        res = self.client.post(DOWNGRADE_URL, {'confirm': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['plan'], 'qr_reviews_base')
        self.assertEqual(data['previous_plan'], 'qr_reviews_pro')

        # Subscription updated
        self.biz.subscription.refresh_from_db()
        self.assertEqual(self.biz.subscription.plan, 'qr_reviews_base')

    def test_non_owner_gets_403(self):
        employee = _make_user('employee@test.com')
        Membership.objects.create(user=employee, business=self.biz, role='admin')
        client = _auth_client(employee)

        res = client.post(DOWNGRADE_URL, {'confirm': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_already_base_returns_409(self):
        sub = self.biz.subscription
        sub.plan = 'qr_reviews_base'
        sub.save()

        res = self.client.post(DOWNGRADE_URL, {'confirm': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_non_reviews_plan_returns_400(self):
        sub = self.biz.subscription
        sub.plan = 'pro'  # Gestión Comercial plan, not reviews
        sub.save()

        res = self.client.post(DOWNGRADE_URL, {'confirm': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_confirm_returns_400(self):
        res = self.client.post(DOWNGRADE_URL, {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(res.json().get('requires_confirm'))

    def test_confirm_false_returns_400(self):
        res = self.client.post(DOWNGRADE_URL, {'confirm': False}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        res = client.post(DOWNGRADE_URL, {'confirm': True}, format='json')
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ---------------------------------------------------------------------------
# apply_reviews_plan_downgrade tests
# ---------------------------------------------------------------------------

class ApplyReviewsPlanDowngradeTests(TestCase):
    """apply_reviews_plan_downgrade() — updates legacy + V2 + audit record."""

    def setUp(self):
        self.owner = _make_user('apply-down@test.com')
        self.biz = _make_business(self.owner, plan='qr_reviews_pro')

    def test_updates_legacy_subscription_plan(self):
        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)
        self.biz.subscription.refresh_from_db()
        self.assertEqual(self.biz.subscription.plan, 'qr_reviews_base')

    def test_creates_audit_record(self):
        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)

        record = PendingSubscriptionChange.objects.filter(
            business=self.biz, is_downgrade=True, status='completed',
        ).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.target_plan_code, 'qr_reviews_base')
        self.assertEqual(record.total_amount, 0)
        self.assertEqual(record.config_snapshot['previous_plan'], 'qr_reviews_pro')

    def test_syncs_existing_v2(self):
        SubscriptionV2.objects.create(
            business=self.biz,
            service_type='qr_reviews',
            plan_code='qr_reviews_pro',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            external_reference='SUB-existing-456',
            status=SubscriptionV2.Status.ACTIVE,
        )

        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)

        v2 = SubscriptionV2.objects.get(business=self.biz, service_type='qr_reviews')
        self.assertEqual(v2.plan_code, 'qr_reviews_base')
        # Status stays ACTIVE — downgraded but still subscribed to Base
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)

    def test_entitlements_resolve_after_downgrade(self):
        """After downgrade, is_reviews_pro returns False and smart_filter_allowed is False."""
        from apps.reviews.entitlements import is_reviews_pro, smart_filter_allowed
        self.assertTrue(is_reviews_pro(self.biz))

        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)
        self.biz.subscription.refresh_from_db()

        self.assertFalse(is_reviews_pro(self.biz))
        self.assertFalse(smart_filter_allowed(self.biz))

    def test_no_v2_does_not_crash(self):
        """Downgrade works even if no SubscriptionV2 exists."""
        self.assertFalse(
            SubscriptionV2.objects.filter(business=self.biz, service_type='qr_reviews').exists()
        )
        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)
        self.biz.subscription.refresh_from_db()
        self.assertEqual(self.biz.subscription.plan, 'qr_reviews_base')
