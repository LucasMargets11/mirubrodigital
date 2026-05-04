"""
Tests for the Gestión Comercial Setup Center context endpoint.

GET /api/v1/setup/gestion/context → 200

Pattern: APITestCase + force_authenticate + client.cookies['bid'].
No rollout flag required — this endpoint is always available.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import (
    Business,
    BusinessBillingProfile,
    BusinessBranding,
    Subscription,
)
from apps.catalog.models import Product, ProductCategory
from apps.inventory.models import ProductStock
from apps.invoices.models import DocumentSeries
from apps.treasury.models import Account, TreasurySettings

User = get_user_model()

URL = 'business:setup-gestion-context'


class GestionSetupContextTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='setupowner',
            email='setupowner@example.com',
            password='testpass',
        )

    def _bootstrap(self, plan: str = 'starter', role: str = 'owner') -> Business:
        business = Business.objects.create(name='Negocio Setup Test')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    # ── HTTP basics ───────────────────────────────────────────────────────────

    def test_returns_200_for_owner(self):
        self._bootstrap()
        resp = self.client.get(reverse(URL))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_returns_200_for_manager_role(self):
        """Setup context is read-only — all roles may access it."""
        self._bootstrap(role='manager')
        resp = self.client.get(reverse(URL))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_returns_401_for_anonymous(self):
        self.client.logout()
        resp = self.client.get(reverse(URL))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    # ── Response shape ────────────────────────────────────────────────────────

    def test_response_has_required_keys(self):
        self._bootstrap()
        data = self.client.get(reverse(URL)).data
        for key in ('plan', 'features', 'tasks', 'progress', 'status_map'):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_plan_code_and_name_returned(self):
        self._bootstrap(plan='starter')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['plan']['code'], 'starter')
        self.assertEqual(data['plan']['name'], 'Starter')

    def test_pro_plan_code_returned(self):
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['plan']['code'], 'pro')
        self.assertEqual(data['plan']['name'], 'Pro')

    def test_progress_has_completed_and_total(self):
        self._bootstrap()
        data = self.client.get(reverse(URL)).data
        self.assertIn('completed', data['progress'])
        self.assertIn('total', data['progress'])

    # ── Plan-tier step visibility ─────────────────────────────────────────────

    def test_starter_sees_5_steps_in_progress(self):
        """Starter: 5 base steps (min_tier=0), 5 PRO/BUSINESS steps excluded."""
        self._bootstrap(plan='starter')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['progress']['total'], 5)

    def test_pro_sees_9_steps_in_progress(self):
        """PRO: 5 base + 4 PRO steps (document_series, treasury_accounts, cash_link, team)."""
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['progress']['total'], 9)

    def test_business_sees_10_steps_in_progress(self):
        """BUSINESS: all 10 steps."""
        self._bootstrap(plan='business')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['progress']['total'], 10)

    def test_upgrade_steps_not_in_progress_total(self):
        """Steps with status='upgrade' must not be counted in total."""
        self._bootstrap(plan='starter')
        data = self.client.get(reverse(URL)).data
        # 'gestion.branches' is BUSINESS-only so should be 'upgrade' for starter
        self.assertEqual(data['tasks']['gestion.branches']['status'], 'upgrade')
        # 'gestion.treasury_accounts' is PRO-only
        self.assertEqual(data['tasks']['gestion.treasury_accounts']['status'], 'upgrade')

    def test_upgrade_steps_map_to_pending_in_status_map(self):
        """Upgrade steps must appear as 'pending' in status_map (frontend only knows 2 values)."""
        self._bootstrap(plan='starter')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.branches'], 'pending')
        self.assertEqual(data['status_map']['gestion.treasury_accounts'], 'pending')

    # ── business_and_fiscal task ──────────────────────────────────────────────

    def test_business_and_fiscal_pending_for_placeholder_name(self):
        business = self._bootstrap()
        # The default name 'Negocio Setup Test' is not a placeholder
        # Force a placeholder name
        business.name = 'mi negocio'
        business.save()
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.business_and_fiscal'], 'pending')

    def test_business_and_fiscal_completed_for_real_name(self):
        business = self._bootstrap()
        business.name = 'Cafetería El Ángel'
        business.save()
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.business_and_fiscal'], 'completed')

    def test_business_and_fiscal_completed_when_billing_profile_has_legal_name(self):
        business = self._bootstrap()
        business.name = 'mi negocio'
        business.save()
        bp, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        bp.legal_name = 'Razón Social SA'
        bp.save()
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.business_and_fiscal'], 'completed')

    # ── branding task ─────────────────────────────────────────────────────────

    def test_branding_pending_when_no_logos(self):
        self._bootstrap()
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.branding'], 'pending')

    # ── categories task ───────────────────────────────────────────────────────

    def test_categories_pending_when_no_categories(self):
        self._bootstrap()
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.categories'], 'pending')

    def test_categories_completed_when_category_exists(self):
        business = self._bootstrap()
        ProductCategory.objects.create(business=business, name='Bebidas')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.categories'], 'completed')

    # ── products task ─────────────────────────────────────────────────────────

    def test_products_pending_when_no_products(self):
        self._bootstrap()
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.products'], 'pending')

    def test_products_completed_when_product_exists(self):
        business = self._bootstrap()
        Product.objects.create(business=business, name='Café', price='150.00', sku='CAF-01')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.products'], 'completed')

    # ── initial_stock task ────────────────────────────────────────────────────

    def test_initial_stock_pending_when_no_stock(self):
        self._bootstrap()
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.initial_stock'], 'pending')

    def test_initial_stock_completed_when_stock_gt_zero(self):
        business = self._bootstrap()
        product = Product.objects.create(business=business, name='Café', price='150.00', sku='CAF-02')
        ProductStock.objects.create(business=business, product=product, quantity=10)
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.initial_stock'], 'completed')

    # ── treasury_accounts task (PRO+) ─────────────────────────────────────────

    def test_treasury_accounts_pending_for_pro_when_no_accounts(self):
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.treasury_accounts'], 'pending')
        self.assertEqual(data['tasks']['gestion.treasury_accounts']['status'], 'pending')

    def test_treasury_accounts_completed_when_active_account_exists(self):
        business = self._bootstrap(plan='pro')
        Account.objects.create(business=business, name='Caja Principal', type='cash', is_active=True)
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.treasury_accounts'], 'completed')

    # ── cash_link task (PRO+) ─────────────────────────────────────────────────

    def test_cash_link_pending_when_no_treasury_settings(self):
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.cash_link'], 'pending')

    def test_cash_link_completed_when_default_cash_account_set(self):
        business = self._bootstrap(plan='pro')
        account = Account.objects.create(business=business, name='Caja', type='cash', is_active=True)
        TreasurySettings.objects.create(business=business, default_cash_account=account)
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.cash_link'], 'completed')

    # ── document_series task (PRO+) ───────────────────────────────────────────

    def test_document_series_pending_for_pro_when_no_series(self):
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.document_series'], 'pending')

    def test_document_series_completed_when_series_exists(self):
        business = self._bootstrap(plan='pro')
        DocumentSeries.objects.create(
            business=business,
            document_type='invoice',
            is_active=True,
        )
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.document_series'], 'completed')

    # ── team task (PRO+) ──────────────────────────────────────────────────────

    def test_team_pending_when_only_one_member(self):
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.team'], 'pending')

    def test_team_completed_when_second_member_added(self):
        business = self._bootstrap(plan='pro')
        second_user = User.objects.create_user(username='staff1', email='staff1@example.com', password='x')
        Membership.objects.create(user=second_user, business=business, role='cashier')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.team'], 'completed')

    # ── branches task (BUSINESS+) ─────────────────────────────────────────────

    def test_branches_pending_for_business_when_no_branch(self):
        business = self._bootstrap(plan='business')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.branches'], 'pending')
        self.assertEqual(data['tasks']['gestion.branches']['status'], 'pending')

    def test_branches_completed_when_branch_exists(self):
        business = self._bootstrap(plan='business')
        branch = Business.objects.create(name='Sucursal Norte', parent=business)
        Subscription.objects.create(business=branch, plan='business', status='active')
        data = self.client.get(reverse(URL)).data
        self.assertEqual(data['status_map']['gestion.branches'], 'completed')

    # ── progress count ────────────────────────────────────────────────────────

    def test_progress_completed_increments_per_completed_task(self):
        business = self._bootstrap(plan='starter')
        # Initially 0 completed
        data = self.client.get(reverse(URL)).data
        initial_completed = data['progress']['completed']

        # Add a category → categories becomes completed
        ProductCategory.objects.create(business=business, name='Ropa')
        data2 = self.client.get(reverse(URL)).data
        self.assertEqual(data2['progress']['completed'], initial_completed + 1)

    # ── features dict ─────────────────────────────────────────────────────────

    def test_features_products_true_for_starter(self):
        self._bootstrap(plan='starter')
        data = self.client.get(reverse(URL)).data
        self.assertTrue(data['features']['products'])

    def test_features_treasury_false_for_starter(self):
        self._bootstrap(plan='starter')
        data = self.client.get(reverse(URL)).data
        self.assertFalse(data['features']['treasury'])

    def test_features_treasury_true_for_pro(self):
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertTrue(data['features']['treasury'])

    def test_features_multi_branch_false_for_pro(self):
        self._bootstrap(plan='pro')
        data = self.client.get(reverse(URL)).data
        self.assertFalse(data['features']['multi_branch'])

    def test_features_multi_branch_true_for_business(self):
        self._bootstrap(plan='business')
        data = self.client.get(reverse(URL)).data
        self.assertTrue(data['features']['multi_branch'])
