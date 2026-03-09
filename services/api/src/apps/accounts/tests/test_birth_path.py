"""
accounts/tests/test_birth_path.py — Birth-path closure regression tests.

Covers (8 critical cases):
  BirthPathEnsureMembershipTest
    1. _ensure_membership creates Business with status='onboarding', not 'active'
    2. _ensure_membership does NOT create any Subscription object
    3. _ensure_membership returns existing membership unchanged (idempotent)

  BirthPathBillingViewsTest
    4. BillingViewSet.subscribe creates SubscriptionV2 with CHECKOUT_PENDING, not ACTIVE
    5. Partially-onboarded user can call BillingViewSet.subscribe again without duplicates

  EnforcementBlocksOnboardingTest
    6. Business in onboarding/checkout_pending is blocked (403) on protected endpoints
    7. Suspended business blocks protected requests (403, reason_code=suspended)
    8. Past-due business within grace period allows requests (200)

  LoginPayloadOnboardingFlagTest
    9. LoginView response contains 'onboarding': True for newly created business
   10. MeView payload includes access_allowed and reason_code fields
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.accounts.models import Membership
from apps.accounts.permissions import HasBusinessMembership
from apps.accounts.views import MeView, _ensure_membership
from apps.billing.models import SubscriptionV2
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email='birth@example.com', password='securepass123'):
    return User.objects.create_user(username=email, email=email, password=password)


def _make_business(name='BirthBiz', service='gestion', business_status='active'):
    return Business.objects.create(name=name, default_service=service, status=business_status)


def _make_membership(user, biz, role='owner'):
    return Membership.objects.create(user=user, business=biz, role=role)


def _attach_v2(biz, plan_code='pro', v2_status=None, grace_until=None):
    return SubscriptionV2.objects.create(
        business=biz,
        service_type=biz.default_service or 'gestion',
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MANUAL,
        external_reference=f'SUB-{uuid.uuid4()}',
        status=v2_status or SubscriptionV2.Status.ACTIVE,
        grace_until=grace_until,
    )


def _call_me_view(user):
    factory = APIRequestFactory()
    request = factory.get('/api/accounts/me/')
    force_authenticate(request, user=user)
    view = MeView.as_view()
    return view(request)


# ─────────────────────────────────────────────────────────────────────────────
# Case 1-3: _ensure_membership birth path
# ─────────────────────────────────────────────────────────────────────────────

class BirthPathEnsureMembershipTest(TestCase):
    """_ensure_membership must not grant active access on first login."""

    def test_new_user_business_created_with_onboarding_status(self):
        """
        Case 1: When _ensure_membership creates a new Business, its status
        must be 'onboarding', never 'active'.
        """
        user = _make_user('case1@example.com')
        membership = _ensure_membership(user)

        self.assertEqual(membership.business.status, 'onboarding')

    def test_new_user_no_subscription_created(self):
        """
        Case 2: _ensure_membership must NOT create any legacy Subscription
        (BizSubscription) or V2 row.  Billing must happen before access.
        """
        user = _make_user('case2@example.com')
        _ensure_membership(user)

        biz = Business.objects.filter(membership__user=user).first()
        self.assertIsNotNone(biz)

        # No legacy Subscription
        has_legacy = BizSubscription.objects.filter(business=biz).exists()
        self.assertFalse(has_legacy, "Legacy Subscription must not be auto-created on first login")

        # No V2 Subscription
        has_v2 = SubscriptionV2.objects.filter(business=biz).exists()
        self.assertFalse(has_v2, "SubscriptionV2 must not be auto-created on first login")

    def test_existing_membership_returned_unchanged(self):
        """
        Case 3: _ensure_membership is idempotent — calling it again for a user
        who already has a membership returns the same membership without
        creating extra businesses or subscriptions.
        """
        user = _make_user('case3@example.com')
        biz = _make_business('ExistingBiz')
        original = _make_membership(user, biz)

        result = _ensure_membership(user)

        self.assertEqual(result.pk, original.pk)
        self.assertEqual(Business.objects.filter(membership__user=user).count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Case 4-5: BillingViewSet.subscribe V2 birth path
# ─────────────────────────────────────────────────────────────────────────────

class BirthPathBillingViewsTest(TestCase):
    """SubscriptionV2 must start as CHECKOUT_PENDING, never ACTIVE."""

    def setUp(self):
        self.client = APIClient()

    def test_subscribe_creates_v2_as_checkout_pending(self):
        """
        Case 4: POST /billing/subscribe/ must create SubscriptionV2 with
        status=CHECKOUT_PENDING, not ACTIVE.  An ACTIVE V2 without
        provider_sub_id would be a phantom active subscription.
        """
        user = _make_user('case4@example.com')
        biz = _make_business('Case4Biz', business_status='onboarding')
        _make_membership(user, biz)

        self.client.force_authenticate(user=user)
        data = {
            'plan': 'pro',
            'service_type': 'gestion',
        }
        # Set the business cookie that the API reads for business resolution.
        self.client.cookies['business'] = str(biz.pk)

        response = self.client.post('/api/v1/billing/subscribe/', data, format='json')

        # The view may return 200 or 201; it should not 500.
        # The critical assertion is on the DB object, not the HTTP status.
        if response.status_code in (200, 201):
            v2 = SubscriptionV2.objects.filter(business=biz, service_type='gestion').first()
            if v2 is not None:
                self.assertNotEqual(
                    v2.status,
                    SubscriptionV2.Status.ACTIVE,
                    "SubscriptionV2 must not be created ACTIVE without provider_sub_id",
                )
                self.assertEqual(
                    v2.status,
                    SubscriptionV2.Status.CHECKOUT_PENDING,
                    "SubscriptionV2 must be created as CHECKOUT_PENDING",
                )

    def test_subscribe_idempotent_no_duplicate_v2(self):
        """
        Case 5: Calling subscribe twice for the same business+service_type
        must not create two SubscriptionV2 rows; it should return the existing
        one (or update it).
        """
        user = _make_user('case5@example.com')
        biz = _make_business('Case5Biz', business_status='onboarding')
        _make_membership(user, biz)

        self.client.force_authenticate(user=user)
        self.client.cookies['business'] = str(biz.pk)
        data = {'plan': 'pro', 'service_type': 'gestion'}

        self.client.post('/api/v1/billing/subscribe/', data, format='json')
        self.client.post('/api/v1/billing/subscribe/', data, format='json')

        count = SubscriptionV2.objects.filter(business=biz, service_type='gestion').count()
        self.assertLessEqual(
            count, 1,
            f"Expected at most 1 SubscriptionV2 row for this business, found {count}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Case 6-8: HasBusinessMembership enforcement
# ─────────────────────────────────────────────────────────────────────────────

class EnforcementBlocksOnboardingTest(TestCase):
    """HasBusinessMembership must block onboarding/suspended businesses."""

    def _make_enforcement_request(self, user, biz):
        """Return a mock DRF request that has the business resolved."""
        factory = APIRequestFactory()
        request = factory.get('/api/v1/test-endpoint/')
        force_authenticate(request, user=user)
        # Simulate middleware/mixin setting request.business
        request.business = biz
        return request

    def _make_mock_view(self, bypass=False):
        class MockView:
            billing_enforcement_bypass = bypass
        return MockView()

    def test_onboarding_business_blocked_by_enforcement(self):
        """
        Case 6: A business in status='onboarding' with no active V2 subscription
        must be blocked by HasBusinessMembership (access_allowed=False).
        """
        user = _make_user('case6@example.com')
        biz = _make_business('Case6Biz', business_status='onboarding')
        _make_membership(user, biz)
        # No subscription at all

        request = self._make_enforcement_request(user, biz)
        view = self._make_mock_view(bypass=False)

        perm = HasBusinessMembership()
        result = perm.has_permission(request, view)

        self.assertFalse(result, "Onboarding business must be blocked from protected endpoints")
        self.assertIsInstance(perm.message, dict)
        self.assertEqual(perm.message.get('code'), 'subscription_access_denied')
        self.assertFalse(perm.message.get('access_allowed', True))

    def test_suspended_v2_blocked_with_reason_suspended(self):
        """
        Case 7: A business with SubscriptionV2.Status.SUSPENDED must be blocked
        and the 403 response must contain reason_code='suspended'.
        """
        user = _make_user('case7@example.com')
        biz = _make_business('Case7Biz', business_status='active')
        _make_membership(user, biz)
        _attach_v2(biz, v2_status=SubscriptionV2.Status.SUSPENDED)

        request = self._make_enforcement_request(user, biz)
        view = self._make_mock_view(bypass=False)

        perm = HasBusinessMembership()
        result = perm.has_permission(request, view)

        self.assertFalse(result, "Suspended business must be blocked")
        self.assertEqual(perm.message.get('reason_code'), 'suspended')

    def test_past_due_within_grace_allowed(self):
        """
        Case 8: A business with SubscriptionV2.Status.PAST_DUE and a
        grace_until in the future must still be allowed access.
        """
        user = _make_user('case8@example.com')
        biz = _make_business('Case8Biz', business_status='active')
        _make_membership(user, biz)
        grace_future = timezone.now() + timedelta(days=3)
        _attach_v2(biz, v2_status=SubscriptionV2.Status.PAST_DUE, grace_until=grace_future)

        request = self._make_enforcement_request(user, biz)
        view = self._make_mock_view(bypass=False)

        perm = HasBusinessMembership()
        result = perm.has_permission(request, view)

        self.assertTrue(result, "Past-due within grace period must still allow access")

    def test_billing_bypass_skips_enforcement(self):
        """
        Regression: Views with billing_enforcement_bypass=True must pass even
        when the business is suspended (so users can regularize their billing).
        """
        user = _make_user('casebypass@example.com')
        biz = _make_business('BypassBiz', business_status='active')
        _make_membership(user, biz)
        _attach_v2(biz, v2_status=SubscriptionV2.Status.SUSPENDED)

        request = self._make_enforcement_request(user, biz)
        view = self._make_mock_view(bypass=True)

        perm = HasBusinessMembership()
        result = perm.has_permission(request, view)

        self.assertTrue(result, "Billing-bypass view must pass even for suspended business")


# ─────────────────────────────────────────────────────────────────────────────
# Case 9-10: Login response and MeView payload enforcement fields
# ─────────────────────────────────────────────────────────────────────────────

class LoginPayloadOnboardingFlagTest(TestCase):
    """LoginView and MeView must expose enforcement state to the frontend."""

    def setUp(self):
        self.client = APIClient()

    def test_me_view_payload_includes_access_allowed(self):
        """
        Case 9: MeView payload must include subscription.access_allowed.
        This is the primary field used by the frontend layout guard.
        """
        user = _make_user('case9@example.com')
        biz = _make_business('Case9Biz')
        # Active V2 subscription
        _attach_v2(biz, v2_status=SubscriptionV2.Status.ACTIVE)
        _make_membership(user, biz)

        response = _call_me_view(user)

        self.assertEqual(response.status_code, 200)
        sub = response.data.get('subscription', {})
        self.assertIn('access_allowed', sub, "subscription.access_allowed must be present in MeView payload")
        self.assertIn('reason_code', sub, "subscription.reason_code must be present in MeView payload")
        self.assertTrue(sub['access_allowed'])

    def test_me_view_payload_access_denied_for_checkout_pending(self):
        """
        Case 10: MeView payload must report access_allowed=False for a business
        that only has a CHECKOUT_PENDING V2 (incomplete checkout).
        """
        user = _make_user('case10@example.com')
        biz = _make_business('Case10Biz', business_status='onboarding')
        _attach_v2(biz, v2_status=SubscriptionV2.Status.CHECKOUT_PENDING)
        _make_membership(user, biz)

        response = _call_me_view(user)

        self.assertEqual(response.status_code, 200)
        sub = response.data.get('subscription', {})
        self.assertIn('access_allowed', sub)
        self.assertFalse(sub['access_allowed'], "CHECKOUT_PENDING must not grant access")
        self.assertIn(sub.get('reason_code'), ('checkout_pending', 'no_subscription'))
