"""
Tests for QR de Reseñas standalone product.

Verifies:
  - Feature flags for qr_reviews plan return qr_reviews_core (not menu_qr_reviews)
  - enabled_services() returns only ['qr_reviews'] for a qr_reviews plan
  - Service policy: qr_reviews is NOT implied by menu_qr
  - Runtime tier extraction handles qr_reviews and bundle-qr_reviews-monthly
  - qr_entitlements: qr_reviews plan gets reviews_allowed=True, tips_allowed=False
  - Onboarding: qr_reviews is a valid service type
  - Public review redirect endpoint returns data for valid slug
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.features import feature_flags_for_plan, PLAN_FEATURES, FEATURE_KEYS
from apps.business.models import Business, BusinessPlan, Subscription
from apps.business.service_catalog import enabled_services, SERVICE_CATALOG
from apps.business.service_policy import business_has_service, SERVICE_IMPLIES
from apps.billing.runtime import _extract_plan_tier
from apps.menu.qr_entitlements import resolve_menu_qr_flags
from apps.menu.models import MenuEngagementSettings

User = get_user_model()


# ---------------------------------------------------------------------------
# Unit tests – feature flags
# ---------------------------------------------------------------------------

class QRReviewsFeatureFlagsTests(TestCase):
    """qr_reviews plan exposes qr_reviews_core, not menu_qr_reviews."""

    def test_qr_reviews_core_in_feature_keys(self):
        self.assertIn('qr_reviews_core', FEATURE_KEYS)

    def test_plan_features_qr_reviews_has_core_flag(self):
        features = PLAN_FEATURES.get('qr_reviews', ())
        self.assertIn('qr_reviews_core', features)

    def test_plan_features_qr_reviews_does_not_have_menu_qr_reviews(self):
        """Decision 2: qr_reviews_core is the standalone flag, NOT menu_qr_reviews."""
        features = PLAN_FEATURES.get('qr_reviews', ())
        self.assertNotIn('menu_qr_reviews', features)

    def test_feature_flags_for_plan_qr_reviews(self):
        flags = feature_flags_for_plan('qr_reviews')
        self.assertTrue(flags.get('qr_reviews_core'))
        self.assertTrue(flags.get('dashboard'))
        self.assertTrue(flags.get('services'))
        self.assertTrue(flags.get('settings'))

    def test_feature_flags_for_plan_qr_reviews_no_menu_features(self):
        flags = feature_flags_for_plan('qr_reviews')
        self.assertFalse(flags.get('menu_builder'))
        self.assertFalse(flags.get('menu_branding'))


# ---------------------------------------------------------------------------
# Unit tests – service catalog and enabled_services
# ---------------------------------------------------------------------------

class QRReviewsServiceCatalogTests(TestCase):
    """qr_reviews is properly defined in SERVICE_CATALOG."""

    def test_catalog_has_qr_reviews(self):
        slugs = [s.slug for s in SERVICE_CATALOG]
        self.assertIn('qr_reviews', slugs)

    def test_enabled_services_qr_reviews_plan(self):
        flags = feature_flags_for_plan('qr_reviews')
        services = enabled_services('qr_reviews', flags)
        self.assertEqual(services, ['qr_reviews'])

    def test_enabled_services_qr_reviews_does_not_include_menu_qr(self):
        flags = feature_flags_for_plan('qr_reviews')
        services = enabled_services('qr_reviews', flags)
        self.assertNotIn('menu_qr', services)


# ---------------------------------------------------------------------------
# Unit tests – service policy (no implication)
# ---------------------------------------------------------------------------

class QRReviewsServicePolicyTests(TestCase):

    def test_qr_reviews_not_implied_by_menu_qr(self):
        menu_qr_implies = SERVICE_IMPLIES.get('menu_qr', frozenset())
        self.assertNotIn('qr_reviews', menu_qr_implies)

    def test_qr_reviews_not_implied_by_restaurante(self):
        restaurante_implies = SERVICE_IMPLIES.get('restaurante', frozenset())
        self.assertNotIn('qr_reviews', restaurante_implies)

    def test_qr_reviews_business_has_qr_reviews_service(self):
        b = Business.objects.create(name='Test QR Reviews', default_service='qr_reviews')
        self.assertTrue(business_has_service(b, 'qr_reviews'))

    def test_qr_reviews_business_does_not_have_menu_qr(self):
        b = Business.objects.create(name='Test QR Reviews', default_service='qr_reviews')
        self.assertFalse(business_has_service(b, 'menu_qr'))


# ---------------------------------------------------------------------------
# Unit tests – runtime tier extraction
# ---------------------------------------------------------------------------

class QRReviewsRuntimeTests(TestCase):

    def test_extract_plan_tier_qr_reviews(self):
        self.assertEqual(_extract_plan_tier('qr_reviews'), 'qr_reviews')

    def test_extract_plan_tier_bundle(self):
        self.assertEqual(_extract_plan_tier('bundle-qr_reviews-monthly'), 'qr_reviews')


# ---------------------------------------------------------------------------
# Unit tests – qr_entitlements
# ---------------------------------------------------------------------------

class QRReviewsEntitlementsTests(TestCase):

    def test_qr_reviews_plan_allows_reviews(self):
        # Build a minimal subscription-like object
        class FakeSub:
            plan = 'qr_reviews'
        flags = resolve_menu_qr_flags(FakeSub())
        self.assertTrue(flags['reviews_allowed'])

    def test_qr_reviews_plan_disallows_tips(self):
        class FakeSub:
            plan = 'qr_reviews'
        flags = resolve_menu_qr_flags(FakeSub())
        self.assertFalse(flags['tips_allowed'])


# ---------------------------------------------------------------------------
# Unit tests – onboarding valid service types
# ---------------------------------------------------------------------------

class QRReviewsOnboardingTests(TestCase):

    def test_qr_reviews_is_valid_service_type(self):
        from apps.accounts.onboarding_views import VALID_SERVICE_TYPES
        self.assertIn('qr_reviews', VALID_SERVICE_TYPES)


# ---------------------------------------------------------------------------
# Integration tests – public review redirect endpoint
# ---------------------------------------------------------------------------

class PublicReviewRedirectTests(APITestCase):

    def setUp(self):
        self.business = Business.objects.create(
            name='Cafetería Test',
            default_service='qr_reviews',
            slug='cafeteria-test',
        )
        Subscription.objects.create(
            business=self.business, plan='qr_reviews', service='qr_reviews', status='active',
        )
        self.engagement = MenuEngagementSettings.objects.create(
            business=self.business,
            reviews_enabled=True,
            google_place_id='ChIJtestplaceid',
        )

    def test_returns_business_name_and_review_url(self):
        url = reverse('menu:public-review-redirect', kwargs={'slug': 'cafeteria-test'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['business_name'], 'Cafetería Test')
        self.assertIn('google.com', response.data['review_url'])

    def test_returns_404_for_nonexistent_slug(self):
        url = reverse('menu:public-review-redirect', kwargs={'slug': 'no-existe'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_when_no_engagement(self):
        biz = Business.objects.create(
            name='Sin Config', default_service='qr_reviews', slug='sin-config',
        )
        url = reverse('menu:public-review-redirect', kwargs={'slug': 'sin-config'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_when_no_place_id(self):
        biz = Business.objects.create(
            name='Sin Place ID', default_service='qr_reviews', slug='sin-place',
        )
        MenuEngagementSettings.objects.create(
            business=biz, reviews_enabled=True, google_place_id='',
        )
        url = reverse('menu:public-review-redirect', kwargs={'slug': 'sin-place'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_when_reviews_disabled(self):
        """A1: reviews_enabled=False must return 404 even with a valid place_id."""
        biz = Business.objects.create(
            name='Reviews Off', default_service='qr_reviews', slug='reviews-off',
        )
        MenuEngagementSettings.objects.create(
            business=biz, reviews_enabled=False, google_place_id='ChIJtestplaceid',
        )
        url = reverse('menu:public-review-redirect', kwargs={'slug': 'reviews-off'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_when_plan_disallows_reviews(self):
        """A2: Business on menu_qr_lite (reviews_allowed=False) must return 404."""
        biz = Business.objects.create(
            name='Lite Plan', default_service='menu_qr', slug='lite-plan',
        )
        Subscription.objects.create(
            business=biz, plan='menu_qr_lite', service='menu_qr', status='active',
        )
        MenuEngagementSettings.objects.create(
            business=biz, reviews_enabled=True, google_place_id='ChIJtestplaceid',
        )
        url = reverse('menu:public-review-redirect', kwargs={'slug': 'lite-plan'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Integration tests – ReviewQRCodeView gating
# ---------------------------------------------------------------------------

class ReviewQRCodeGatingTests(APITestCase):
    """A3: ReviewQRCodeView must deny access when plan disallows reviews."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testqruser', password='testpass123',
        )
        self.business = Business.objects.create(
            name='No Reviews Biz', default_service='menu_qr', slug='no-reviews',
        )
        Subscription.objects.create(
            business=self.business, plan='menu_qr_lite', service='menu_qr', status='active',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='owner',
        )
        self.client.force_authenticate(user=self.user)

    def test_returns_403_when_plan_disallows_reviews(self):
        """menu_qr_lite user with manage_menu must NOT generate review QR."""
        url = reverse('reviews-qr')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
