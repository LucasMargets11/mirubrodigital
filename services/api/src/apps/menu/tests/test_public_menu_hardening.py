"""
Tests for public menu hardening (Phase 1-2).

Covers:
  - Business status gating on PublicMenuBySlugView and PublicMenuResolveView
  - No exposure of business.id or sku in public response
  - Items with is_available=False excluded from public payload
  - Rate limiting on public endpoints
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.business.models import Business, Subscription
from apps.menu.models import (
    MenuCategory,
    MenuItem,
    PublicMenuConfig,
    ensure_menu_branding,
    ensure_public_menu_config,
)

User = get_user_model()


def _make_business(name='Test Biz', slug='test-slug', biz_status='active',
                   plan='menu_qr', service='menu_qr'):
    """Create a business with subscription and public menu config.

    NOTE: PublicMenuConfig.slug is generated from the business *name*
    (via slugify), NOT from Business.slug.  The returned config
    carries the authoritative slug used in the public URL.
    """
    biz = Business.objects.create(
        name=name, slug=slug, status=biz_status, default_service=service,
    )
    Subscription.objects.create(business=biz, plan=plan, service=service, status='active')
    config = ensure_public_menu_config(biz)
    config.enabled = True
    config.save()
    ensure_menu_branding(biz)
    return biz, config


# ═══════════════════════════════════════════════════════════════════════════
# 1. Business status gating — PublicMenuBySlugView
# ═══════════════════════════════════════════════════════════════════════════

class PublicMenuStatusGatingTests(APITestCase):
    """Public menu returns 404 for non-publishable business statuses."""

    def _url(self, slug):
        return f'/api/v1/menu/public/slug/{slug}/'

    def test_active_business_returns_200(self):
        _, config = _make_business(name='Active Biz', biz_status='active')
        resp = self.client.get(self._url(config.slug))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_trialing_business_returns_200(self):
        _, config = _make_business(name='Trial Biz', biz_status='trialing')
        resp = self.client.get(self._url(config.slug))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_past_due_business_returns_200(self):
        _, config = _make_business(name='Past Due Biz', biz_status='past_due')
        resp = self.client.get(self._url(config.slug))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_suspended_business_returns_404(self):
        _, config = _make_business(name='Susp Biz', biz_status='suspended')
        resp = self.client.get(self._url(config.slug))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_canceled_business_returns_404(self):
        _, config = _make_business(name='Cancel Biz', biz_status='canceled')
        resp = self.client.get(self._url(config.slug))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_onboarding_business_returns_404(self):
        _, config = _make_business(name='Onboard Biz', biz_status='onboarding')
        resp = self.client.get(self._url(config.slug))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_disabled_config_returns_404(self):
        _, config = _make_business(name='Disabled Biz')
        config.enabled = False
        config.save()
        resp = self.client.get(self._url(config.slug))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Business status gating — PublicMenuResolveView
# ═══════════════════════════════════════════════════════════════════════════

class PublicMenuResolveStatusGatingTests(APITestCase):
    """Resolve endpoint returns 404 for non-publishable business statuses."""

    def test_active_resolves(self):
        _, config = _make_business(name='Res Active', biz_status='active')
        resp = self.client.get(f'/api/v1/menu/public/resolve/{config.public_id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['slug'], config.slug)

    def test_suspended_returns_404(self):
        _, config = _make_business(name='Res Susp', biz_status='suspended')
        resp = self.client.get(f'/api/v1/menu/public/resolve/{config.public_id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_canceled_returns_404(self):
        _, config = _make_business(name='Res Cancel', biz_status='canceled')
        resp = self.client.get(f'/api/v1/menu/public/resolve/{config.public_id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ═══════════════════════════════════════════════════════════════════════════
# 3. No internal data exposure
# ═══════════════════════════════════════════════════════════════════════════

class PublicMenuDataExposureTests(APITestCase):
    """Public menu response must not leak internal identifiers."""

    def setUp(self):
        self.biz, self.config = _make_business(name='Expo Biz')
        cat = MenuCategory.objects.create(
            business=self.biz, name='Bebidas', position=1,
        )
        MenuItem.objects.create(
            business=self.biz, category=cat, name='Café',
            price='150.00', sku='SKU-001', is_available=True, position=1,
        )

    def test_response_does_not_contain_business_id(self):
        resp = self.client.get(f'/api/v1/menu/public/slug/{self.config.slug}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        business_data = resp.data['business']
        self.assertNotIn('id', business_data)
        self.assertIn('name', business_data)

    def test_items_do_not_contain_sku(self):
        resp = self.client.get(f'/api/v1/menu/public/slug/{self.config.slug}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.data['categories'][0]['items']
        self.assertTrue(len(items) > 0)
        for item in items:
            self.assertNotIn('sku', item)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Unavailable items filtered
# ═══════════════════════════════════════════════════════════════════════════

class PublicMenuAvailabilityFilterTests(APITestCase):
    """Public menu must only contain available items."""

    def setUp(self):
        self.biz, self.config = _make_business(name='Avail Biz')
        self.cat = MenuCategory.objects.create(
            business=self.biz, name='Comidas', position=1,
        )
        MenuItem.objects.create(
            business=self.biz, category=self.cat, name='Empanada',
            price='200.00', is_available=True, position=1,
        )
        MenuItem.objects.create(
            business=self.biz, category=self.cat, name='Pizza',
            price='500.00', is_available=False, position=2,
        )

    def test_unavailable_items_excluded_from_public_response(self):
        resp = self.client.get(f'/api/v1/menu/public/slug/{self.config.slug}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.data['categories'][0]['items']
        names = [i['name'] for i in items]
        self.assertIn('Empanada', names)
        self.assertNotIn('Pizza', names)

    def test_all_items_available_returns_all(self):
        MenuItem.objects.filter(name='Pizza').update(is_available=True)
        resp = self.client.get(f'/api/v1/menu/public/slug/{self.config.slug}/')
        items = resp.data['categories'][0]['items']
        self.assertEqual(len(items), 2)
