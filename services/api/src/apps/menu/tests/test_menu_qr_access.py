"""
Tests for Menú QR vs Restaurante Inteligente access differentiation.

Verifies:
  - menu_qr_online subscriber  → can use all QR/menu endpoints
                                → CANNOT access restaurant-specific endpoints (tables, orders)
  - restaurante_inteligente subscriber → can use all QR/menu endpoints (service hierarchy)
                                       → CAN access restaurant-specific endpoints
  - business_has_service() service hierarchy logic
  - features.py: plus plan includes menu_qr features
  - enabled_services() returns correct set for each plan
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.context import build_business_context
from apps.business.features import feature_flags_for_plan, PLAN_FEATURES
from apps.business.models import Business, BusinessPlan, Subscription
from apps.business.service_catalog import enabled_services
from apps.business.service_policy import business_has_service, SERVICE_IMPLIES

User = get_user_model()


# ---------------------------------------------------------------------------
# Unit tests – service policy
# ---------------------------------------------------------------------------

class ServicePolicyHierarchyTests(TestCase):
    """business_has_service() respects SERVICE_IMPLIES for restaurant→menu_qr."""

    def _business(self, default_service: str, subscription_service: str | None = None) -> Business:
        b = Business.objects.create(name=f"Test_{default_service}", default_service=default_service)
        if subscription_service is not None:
            Subscription.objects.create(business=b, plan=BusinessPlan.PLUS, service=subscription_service, status='active')
        return b

    def test_menu_qr_business_has_menu_qr_service(self):
        b = self._business('menu_qr')
        self.assertTrue(business_has_service(b, 'menu_qr'))

    def test_menu_qr_business_does_not_have_restaurante_service(self):
        b = self._business('menu_qr')
        self.assertFalse(business_has_service(b, 'restaurante'))

    def test_restaurante_business_has_restaurante_service(self):
        b = self._business('restaurante')
        self.assertTrue(business_has_service(b, 'restaurante'))

    def test_restaurante_business_implies_menu_qr_service(self):
        """Critical: restaurant users must be able to access menu_qr endpoints."""
        b = self._business('restaurante')
        self.assertTrue(business_has_service(b, 'menu_qr'))

    def test_restaurante_subscription_service_implies_menu_qr(self):
        """subscription.service takes precedence over default_service."""
        b = self._business('gestion', subscription_service='restaurante')
        self.assertTrue(business_has_service(b, 'menu_qr'))

    def test_gestion_business_does_not_have_menu_qr(self):
        b = self._business('gestion')
        self.assertFalse(business_has_service(b, 'menu_qr'))
        self.assertFalse(business_has_service(b, 'restaurante'))

    def test_service_implies_constant_contains_menu_qr_for_restaurante(self):
        self.assertIn('menu_qr', SERVICE_IMPLIES.get('restaurante', frozenset()))


# ---------------------------------------------------------------------------
# Unit tests – features.py
# ---------------------------------------------------------------------------

class FeaturesPlanTests(TestCase):
    """Plus plan (legacy restaurant) must include all menu_qr feature keys."""

    MENU_QR_FEATURES = {'menu_builder', 'menu_branding', 'public_menu', 'menu_qr_tools'}

    def test_plus_plan_includes_menu_qr_features(self):
        plus_features = set(PLAN_FEATURES.get('plus', []))
        missing = self.MENU_QR_FEATURES - plus_features
        self.assertEqual(
            missing, set(),
            f"plus plan is missing menu QR features: {missing}. "
            "Add them to PLAN_FEATURES['plus'] in features.py."
        )

    def test_menu_qr_plan_has_only_qr_features(self):
        qr_features = set(PLAN_FEATURES.get('menu_qr', []))
        self.assertEqual(qr_features, self.MENU_QR_FEATURES)

    def test_feature_flags_for_plan_plus_enables_qr_tools(self):
        flags = feature_flags_for_plan('plus')
        for key in self.MENU_QR_FEATURES:
            self.assertTrue(flags.get(key), f"feature '{key}' should be True for 'plus' plan")

    def test_feature_flags_for_plan_start_does_not_enable_qr_tools(self):
        """Gestión Comercial Start plan has no QR features."""
        flags = feature_flags_for_plan('start')
        for key in self.MENU_QR_FEATURES:
            self.assertFalse(flags.get(key), f"feature '{key}' should be False for 'start' plan")


# ---------------------------------------------------------------------------
# Unit tests – enabled_services()
# ---------------------------------------------------------------------------

class EnabledServicesTests(TestCase):
    """enabled_services() returns the right set of service slugs per plan."""

    def test_menu_qr_plan_enables_menu_qr_service(self):
        flags = feature_flags_for_plan('menu_qr')
        services = enabled_services('menu_qr', flags)
        self.assertIn('menu_qr', services)
        self.assertNotIn('restaurante', services)
        self.assertNotIn('gestion', services)

    def test_plus_plan_enables_both_restaurante_and_menu_qr(self):
        """Restaurant plan (plus) should enable both services because it includes QR features."""
        flags = feature_flags_for_plan('plus')
        services = enabled_services('plus', flags)
        self.assertIn('restaurante', services)
        self.assertIn('menu_qr', services)
        self.assertNotIn('gestion', services)

    def test_start_plan_enables_only_gestion(self):
        flags = feature_flags_for_plan('start')
        services = enabled_services('start', flags)
        self.assertIn('gestion', services)
        self.assertNotIn('restaurante', services)
        self.assertNotIn('menu_qr', services)


# ---------------------------------------------------------------------------
# Integration tests – API access control
# ---------------------------------------------------------------------------

def _setup_business_with_service(service: str, plan: str) -> tuple[Business, User]:
    """Helper to create a business + user + membership for API tests."""
    user = User.objects.create_user(
        username=f'user_{service}_{plan}',
        email=f'{service}_{plan}@test.local',
        password='testpass123',
    )
    business = Business.objects.create(name=f'Test {service} {plan}', default_service=service)
    Subscription.objects.create(business=business, plan=plan, service=service, status='active')
    Membership.objects.create(user=user, business=business, role='owner')
    return business, user


class MenuQRStandaloneAccessTests(APITestCase):
    """A menu_qr subscriber can use menu/QR endpoints but NOT restaurant endpoints."""

    def setUp(self):
        self.business, self.user = _setup_business_with_service('menu_qr', BusinessPlan.MENU_QR)
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(self.business.id)

    def test_can_list_menu_categories(self):
        url = reverse('menu:category-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_generate_qr_code(self):
        url = reverse('menu-qr', kwargs={'business_id': self.business.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])

    def test_cannot_access_restaurant_tables(self):
        url = reverse('restaurant-tables')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_access_restaurant_tables_map(self):
        url = reverse('restaurant-tables-map')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RestauranteInteligenteAccessTests(APITestCase):
    """A restaurante_inteligente subscriber can use both restaurant AND menu/QR endpoints."""

    def setUp(self):
        self.business, self.user = _setup_business_with_service('restaurante', BusinessPlan.PLUS)
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(self.business.id)

    def test_can_list_menu_categories(self):
        url = reverse('menu:category-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_generate_qr_code(self):
        """Critical regression test: restaurant subscribers must be able to call the QR endpoint."""
        url = reverse('menu-qr', kwargs={'business_id': self.business.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])

    def test_can_access_restaurant_tables(self):
        url = reverse('restaurant-tables')
        response = self.client.get(url)
        # May return 200 with empty list or 200. 404 would also be acceptable if no tables.
        # What we DON'T want is 403.
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_access_restaurant_tables_map(self):
        url = reverse('restaurant-tables-map')
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GestionServiceAccessTests(APITestCase):
    """A gestion subscriber should NOT access restaurant or menu QR endpoints."""

    def setUp(self):
        self.business, self.user = _setup_business_with_service('gestion', BusinessPlan.START)
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(self.business.id)

    def test_cannot_generate_qr_code(self):
        url = reverse('menu-qr', kwargs={'business_id': self.business.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_access_restaurant_tables(self):
        url = reverse('restaurant-tables')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Integration tests – build_business_context()
# ---------------------------------------------------------------------------

class BusinessContextTests(TestCase):
    """build_business_context() returns correct active_service and enabled_services."""

    def test_menu_qr_business_context(self):
        b = Business.objects.create(name='QR Biz', default_service='menu_qr')
        Subscription.objects.create(business=b, plan=BusinessPlan.MENU_QR, service='menu_qr', status='active')
        ctx = build_business_context(b)
        self.assertEqual(ctx['service'], 'menu_qr')
        self.assertIn('menu_qr', ctx['enabled_services'])
        self.assertNotIn('restaurante', ctx['enabled_services'])

    def test_restaurante_business_context(self):
        b = Business.objects.create(name='Resto Biz', default_service='restaurante')
        Subscription.objects.create(business=b, plan=BusinessPlan.PLUS, service='restaurante', status='active')
        ctx = build_business_context(b)
        self.assertEqual(ctx['service'], 'restaurante')
        self.assertIn('restaurante', ctx['enabled_services'])
        # Restaurant plan now also includes menu_qr features
        self.assertIn('menu_qr', ctx['enabled_services'])
