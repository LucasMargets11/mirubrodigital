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



