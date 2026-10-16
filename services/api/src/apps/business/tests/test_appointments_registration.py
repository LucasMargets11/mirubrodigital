"""
Tests for MiRubro Turnos (`appointments`) — Slice 1 product registration.

Verifies:
  - `appointments` is recognized as a valid service/plan code across the
    canonical registries (ServiceType, SERVICE_CHOICES, BusinessPlan).
  - feature_flags_for_plan('appointments_base') exposes `appointments_core`.
  - SERVICE_CATALOG / enabled_services() surface `appointments` correctly.
  - business_has_service() grants/denies access based on the business's
    service, mirroring the pattern used for qr_reviews.
  - build_business_context() resolves the active service and enabled
    services list for a Turnos-only business.
  - Existing products (gestion, menu_qr, qr_reviews, restaurante) keep their
    prior behaviour — `appointments` must not leak into their enabled sets.
"""

from __future__ import annotations

from django.test import TestCase

from apps.business.context import build_business_context
from apps.business.features import FEATURE_KEYS, PLAN_FEATURES, feature_flags_for_plan
from apps.business.models import Business, BusinessPlan, Subscription
from apps.business.service_catalog import SERVICE_CATALOG, enabled_services
from apps.business.service_policy import SERVICE_IMPLIES, business_has_service


# ---------------------------------------------------------------------------
# Unit tests – canonical registries
# ---------------------------------------------------------------------------

class AppointmentsRegistryTests(TestCase):
    """`appointments` is registered wherever other standalone products are."""

    def test_appointments_in_business_service_choices(self):
        codes = [code for code, _ in Business.SERVICE_CHOICES]
        self.assertIn('appointments', codes)

    def test_appointments_in_service_type_enum(self):
        self.assertIn('appointments', Business.ServiceType.values)

    def test_appointments_base_in_business_plan_enum(self):
        self.assertIn('appointments_base', BusinessPlan.values)


# ---------------------------------------------------------------------------
# Unit tests – features.py
# ---------------------------------------------------------------------------

class AppointmentsFeatureFlagsTests(TestCase):

    def test_appointments_core_in_feature_keys(self):
        self.assertIn('appointments_core', FEATURE_KEYS)

    def test_plan_features_appointments_base_has_core_flag(self):
        features = PLAN_FEATURES.get('appointments_base', ())
        self.assertIn('appointments_core', features)

    def test_feature_flags_for_plan_appointments_base(self):
        flags = feature_flags_for_plan('appointments_base')
        self.assertTrue(flags.get('appointments_core'))
        self.assertTrue(flags.get('dashboard'))
        self.assertTrue(flags.get('services'))
        self.assertTrue(flags.get('settings'))

    def test_feature_flags_for_plan_appointments_base_no_other_product_features(self):
        flags = feature_flags_for_plan('appointments_base')
        self.assertFalse(flags.get('menu_builder'))
        self.assertFalse(flags.get('qr_reviews_core'))
        self.assertFalse(flags.get('products'))


# ---------------------------------------------------------------------------
# Unit tests – service catalog and enabled_services()
# ---------------------------------------------------------------------------

class AppointmentsServiceCatalogTests(TestCase):

    def test_catalog_has_appointments(self):
        slugs = [s.slug for s in SERVICE_CATALOG]
        self.assertIn('appointments', slugs)

    def test_enabled_services_appointments_base_plan(self):
        flags = feature_flags_for_plan('appointments_base')
        services = enabled_services('appointments_base', flags)
        self.assertEqual(services, ['appointments'])

    def test_enabled_services_appointments_does_not_include_other_products(self):
        flags = feature_flags_for_plan('appointments_base')
        services = enabled_services('appointments_base', flags)
        self.assertNotIn('menu_qr', services)
        self.assertNotIn('qr_reviews', services)
        self.assertNotIn('restaurante', services)


# ---------------------------------------------------------------------------
# Unit tests – service policy (entitlement gate)
# ---------------------------------------------------------------------------

class AppointmentsServicePolicyTests(TestCase):

    def test_appointments_not_implied_by_other_services(self):
        for service in ('menu_qr', 'restaurante', 'qr_reviews'):
            implied = SERVICE_IMPLIES.get(service, frozenset())
            self.assertNotIn('appointments', implied)

    def test_business_with_appointments_can_access(self):
        b = Business.objects.create(name='Test Turnos', default_service='appointments')
        self.assertTrue(business_has_service(b, 'appointments'))

    def test_business_without_appointments_is_blocked(self):
        b = Business.objects.create(name='Test Gestion', default_service='gestion')
        self.assertFalse(business_has_service(b, 'appointments'))

    def test_appointments_subscription_service_grants_access(self):
        """subscription.service (not just default_service) is honoured."""
        b = Business.objects.create(name='Test Turnos Sub', default_service='gestion')
        Subscription.objects.create(
            business=b, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
        )
        self.assertTrue(business_has_service(b, 'appointments'))

    def test_appointments_business_does_not_have_other_services(self):
        b = Business.objects.create(name='Test Turnos Only', default_service='appointments')
        self.assertFalse(business_has_service(b, 'menu_qr'))
        self.assertFalse(business_has_service(b, 'qr_reviews'))
        self.assertFalse(business_has_service(b, 'restaurante'))


# ---------------------------------------------------------------------------
# Integration tests – build_business_context()
# ---------------------------------------------------------------------------

class AppointmentsBusinessContextTests(TestCase):

    def test_appointments_business_context(self):
        b = Business.objects.create(name='Turnos Biz', default_service='appointments')
        Subscription.objects.create(
            business=b, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
        )
        ctx = build_business_context(b)
        self.assertEqual(ctx['service'], 'appointments')
        self.assertIn('appointments', ctx['enabled_services'])
        self.assertTrue(ctx['features'].get('appointments_core'))
        self.assertTrue(ctx['access_allowed'])

    def test_appointments_business_context_excludes_other_products(self):
        b = Business.objects.create(name='Turnos Biz 2', default_service='appointments')
        Subscription.objects.create(
            business=b, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
        )
        ctx = build_business_context(b)
        self.assertNotIn('menu_qr', ctx['enabled_services'])
        self.assertNotIn('qr_reviews', ctx['enabled_services'])
        self.assertNotIn('restaurante', ctx['enabled_services'])


# ---------------------------------------------------------------------------
# Regression tests – existing products keep their prior behaviour
# ---------------------------------------------------------------------------

class ExistingProductsUnaffectedTests(TestCase):
    """Registering `appointments` must not change existing products' access."""

    def test_gestion_business_context_unaffected(self):
        b = Business.objects.create(name='Gestion Biz', default_service='gestion')
        Subscription.objects.create(business=b, plan=BusinessPlan.START, service='gestion', status='active')
        ctx = build_business_context(b)
        self.assertEqual(ctx['service'], 'gestion')
        self.assertIn('gestion', ctx['enabled_services'])
        self.assertNotIn('appointments', ctx['enabled_services'])

    def test_menu_qr_business_still_has_menu_qr_not_appointments(self):
        b = Business.objects.create(name='Menu QR Biz', default_service='menu_qr')
        self.assertTrue(business_has_service(b, 'menu_qr'))
        self.assertFalse(business_has_service(b, 'appointments'))

    def test_qr_reviews_business_still_has_qr_reviews_not_appointments(self):
        b = Business.objects.create(name='QR Reviews Biz', default_service='qr_reviews')
        self.assertTrue(business_has_service(b, 'qr_reviews'))
        self.assertFalse(business_has_service(b, 'appointments'))

    def test_restaurante_plan_features_unaffected(self):
        flags = feature_flags_for_plan('plus')
        self.assertFalse(flags.get('appointments_core'))
