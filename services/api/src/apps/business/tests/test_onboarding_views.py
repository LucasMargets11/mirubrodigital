"""
Tests for the Gestión Comercial onboarding endpoints.

Pattern: APITestCase + force_authenticate + client.cookies['bid'].
Rollout flag is enabled for all tests via @override_settings.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import (
    Business,
    BusinessBillingProfile,
    BusinessOnboardingProgress,
    CommercialSettings,
    Subscription,
)
from apps.catalog.models import Product, ProductCategory

User = get_user_model()

ONBOARDING_ENABLED = {
    'ROLLOUT_FLAGS': {
        'new_onboarding_enabled': True,
    }
}


@override_settings(**ONBOARDING_ENABLED)
class GestionOnboardingContextTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='owner1',
            email='owner1@example.com',
            password='testpass',
        )

    def _bootstrap_business(self, role: str = 'owner', plan: str = 'starter') -> Business:
        business = Business.objects.create(name='Mi Negocio')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    # ── context ──────────────────────────────────────────────────────────────

    def test_context_returns_200_for_owner(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-context')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data
        self.assertIn('progress', data)
        self.assertIn('steps', data)
        self.assertEqual(len(data['steps']), 3)

    def test_context_creates_progress_lazily(self):
        business = self._bootstrap_business()
        self.assertFalse(
            BusinessOnboardingProgress.objects.filter(business=business).exists()
        )
        url = reverse('business:onboarding-gestion-context')
        self.client.get(url)
        self.assertTrue(
            BusinessOnboardingProgress.objects.filter(business=business).exists()
        )

    def test_context_returns_403_for_manager_role(self):
        self._bootstrap_business(role='manager')
        url = reverse('business:onboarding-gestion-context')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_context_returns_503_when_rollout_disabled(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-context')
        with self.settings(ROLLOUT_FLAGS={'new_onboarding_enabled': False}):
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_context_step_business_basics_pending_when_name_is_placeholder(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-context')
        resp = self.client.get(url)
        steps = {s['id']: s for s in resp.data['steps']}
        # 'mi negocio' is a placeholder, so status should NOT be 'completed'
        self.assertNotEqual(steps['business_basics']['status'], 'completed')

    def test_context_step_first_product_completed_with_product(self):
        business = self._bootstrap_business()
        Product.objects.create(
            business=business, name='Café', price=Decimal('150'), sku='CAFE-01',
        )
        url = reverse('business:onboarding-gestion-context')
        resp = self.client.get(url)
        steps = {s['id']: s for s in resp.data['steps']}
        self.assertEqual(steps['first_product']['status'], 'completed')


@override_settings(**ONBOARDING_ENABLED)
class GestionOnboardingBusinessBasicsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='owner2',
            email='owner2@example.com',
            password='testpass',
        )

    def _bootstrap_business(self, role: str = 'owner', plan: str = 'starter') -> Business:
        business = Business.objects.create(name='Mi Negocio')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def test_business_basics_updates_business_and_billing_profile(self):
        business = self._bootstrap_business()
        url = reverse('business:onboarding-gestion-business-basics')
        resp = self.client.post(
            url,
            {'business_name': 'Panadería El Sol', 'phone': '+5491155554444'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        business.refresh_from_db()
        # Both models must be synced
        self.assertEqual(business.name, 'Panadería El Sol')
        billing = BusinessBillingProfile.objects.get(pk=business.pk)
        self.assertEqual(billing.trade_name, 'Panadería El Sol')

    def test_business_basics_rejects_short_name(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-business-basics')
        resp = self.client.post(url, {'business_name': 'A'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_business_basics_requires_owner_or_admin(self):
        self._bootstrap_business(role='seller')
        url = reverse('business:onboarding-gestion-business-basics')
        resp = self.client.post(url, {'business_name': 'Test'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(**ONBOARDING_ENABLED)
class GestionOnboardingFirstProductTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='owner3',
            email='owner3@example.com',
            password='testpass',
        )

    def _bootstrap_business(self, role: str = 'owner', plan: str = 'starter') -> Business:
        business = Business.objects.create(name='Test Biz')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def test_first_product_creates_product(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-first-product')
        resp = self.client.post(
            url,
            {'name': 'Empanada', 'price': '200.00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('product', resp.data)
        self.assertEqual(resp.data['product']['name'], 'Empanada')

    def test_first_product_creates_and_reuses_category(self):
        business = self._bootstrap_business()
        url = reverse('business:onboarding-gestion-first-product')

        # First call — creates category
        resp = self.client.post(
            url,
            {'name': 'Pizza', 'price': '300', 'category_name': 'Comida'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        category_count = ProductCategory.objects.filter(business=business, name__iexact='comida').count()
        self.assertEqual(category_count, 1)

    def test_first_product_creates_stock_movement_when_initial_stock_set(self):
        from apps.inventory.models import StockMovement
        business = self._bootstrap_business()
        url = reverse('business:onboarding-gestion-first-product')
        resp = self.client.post(
            url,
            {'name': 'Mate', 'price': '50', 'initial_stock': '10'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(resp.data.get('stock_movement'))
        # Stock movement recorded in DB
        product_id = resp.data['product']['id']
        product = Product.objects.get(pk=product_id)
        movement_count = StockMovement.objects.filter(
            business=business, product=product, movement_type=StockMovement.MovementType.IN,
        ).count()
        self.assertEqual(movement_count, 1)

    def test_first_product_rejects_negative_price(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-first-product')
        resp = self.client.post(
            url,
            {'name': 'Test', 'price': '-10'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_first_product_rejects_negative_initial_stock(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-first-product')
        resp = self.client.post(
            url,
            {'name': 'Test', 'price': '10', 'initial_stock': '-5'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(**ONBOARDING_ENABLED)
class GestionOnboardingSalesSetupTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='owner4',
            email='owner4@example.com',
            password='testpass',
        )

    def _bootstrap_business(self, role: str = 'owner', plan: str = 'starter') -> Business:
        business = Business.objects.create(name='Setup Biz')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def test_sales_setup_starter_sets_block_sales_false(self):
        business = self._bootstrap_business(plan='starter')
        url = reverse('business:onboarding-gestion-sales-setup')
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cs = CommercialSettings.objects.for_business(business)
        self.assertFalse(cs.block_sales_if_no_open_cash_session)

    def test_sales_setup_pro_plan_is_noop_no_error(self):
        self._bootstrap_business(plan='pro')
        url = reverse('business:onboarding-gestion-sales-setup')
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_sales_setup_pro_returns_warning_when_block_sales_is_true(self):
        """PRO plan: does not modify CommercialSettings; emits warning if cash blocking is on."""
        business = self._bootstrap_business(plan='pro')
        # Ensure block_sales_if_no_open_cash_session is True (default, but explicit for clarity)
        cs = CommercialSettings.objects.for_business(business)
        cs.block_sales_if_no_open_cash_session = True
        cs.save(update_fields=['block_sales_if_no_open_cash_session', 'updated_at'])

        url = reverse('business:onboarding-gestion-sales-setup')
        resp = self.client.post(url, {}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Setting must NOT be overwritten
        cs.refresh_from_db()
        self.assertTrue(cs.block_sales_if_no_open_cash_session)
        # Warning must be present and non-empty
        self.assertIn('warning', resp.data)
        self.assertIsInstance(resp.data['warning'], str)
        self.assertTrue(len(resp.data['warning']) > 0)


@override_settings(**ONBOARDING_ENABLED)
class GestionOnboardingSkipStepTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='owner5',
            email='owner5@example.com',
            password='testpass',
        )

    def _bootstrap_business(self, role: str = 'owner') -> Business:
        business = Business.objects.create(name='Skip Biz')
        Subscription.objects.create(business=business, plan='starter', status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def test_skip_business_basics_records_skipped_step(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-skip-step')
        resp = self.client.post(url, {'step_id': 'business_basics'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('business_basics', resp.data['progress']['skipped_steps'])

    def test_skip_first_product_records_skipped_step(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-skip-step')
        resp = self.client.post(url, {'step_id': 'first_product'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_skip_sales_setup_returns_400(self):
        self._bootstrap_business()
        url = reverse('business:onboarding-gestion-skip-step')
        resp = self.client.post(url, {'step_id': 'sales_setup'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(**ONBOARDING_ENABLED)
class GestionOnboardingCompleteAndDismissTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='owner6',
            email='owner6@example.com',
            password='testpass',
        )

    def _bootstrap_business(self, role: str = 'owner') -> Business:
        business = Business.objects.create(name='Done Biz')
        Subscription.objects.create(business=business, plan='starter', status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def test_complete_sets_completed_at(self):
        business = self._bootstrap_business()
        url = reverse('business:onboarding-gestion-complete')
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        progress = BusinessOnboardingProgress.objects.get(business=business, product_type='gestion')
        self.assertIsNotNone(progress.completed_at)
        self.assertIsNone(progress.dismissed_at)

    def test_dismiss_sets_dismissed_at_not_completed_at(self):
        business = self._bootstrap_business()
        url = reverse('business:onboarding-gestion-dismiss')
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        progress = BusinessOnboardingProgress.objects.get(business=business, product_type='gestion')
        self.assertIsNotNone(progress.dismissed_at)
        self.assertIsNone(progress.completed_at)

    def test_non_owner_admin_cannot_complete(self):
        self._bootstrap_business(role='viewer')
        url = reverse('business:onboarding-gestion-complete')
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_admin_cannot_dismiss(self):
        self._bootstrap_business(role='seller')
        url = reverse('business:onboarding-gestion-dismiss')
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
