"""
sales/tests/test_pos_offline_bootstrap.py — Backend tests for the POS offline
bootstrap snapshot endpoint.

Endpoint under test:
  GET /api/v1/pos/offline/bootstrap/

Coverage:
  - Authenticated POS employee can fetch the bootstrap snapshot.
  - Unauthenticated request is rejected (401/403).
  - Snapshot contains the correct business and employee.
  - Snapshot contains the business's active categories and products.
  - Snapshot excludes products from other businesses.
  - Snapshot excludes inactive products and inactive categories.
  - Snapshot includes payment_methods.
  - Snapshot includes commercial_settings.
  - Snapshot includes operation_settings.
  - Snapshot does NOT expose tables / kitchen / orders offline support.
  - cash_session is null when no open session exists.
  - cash_session is returned when an open session exists.
  - offline_policy.enabled reflects the entitlement helper.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend

from apps.accounts.models import EmployeeProfile
from apps.business.models import Business, CommercialSettings
from apps.cash.models import CashRegister, CashSession
from apps.catalog.models import Product, ProductCategory
from apps.inventory.models import ProductStock

URL_BOOTSTRAP = '/api/v1/pos/offline/bootstrap/'

# Path of the entitlement helper as imported inside the view module — patched
# per-test so enabled True/False cases are deterministic without subscriptions.
_ENTITLEMENT_HELPER = 'apps.sales.pos_offline_views.has_pos_offline_contingency_access'


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_business(name: str = 'OfflineBiz', service: str = 'restaurante') -> Business:
    return Business.objects.create(name=name, default_service=service, status='active')


def _make_employee(
    business: Business,
    code: str = 'EMP-OFF-1',
    role_type: str = EmployeeProfile.RoleType.CASHIER,
    pin: str = '123456',
    emp_status: str = EmployeeProfile.Status.ACTIVE,
    must_change_pin: bool = False,
) -> EmployeeProfile:
    return EmployeeProfile.objects.create(
        business=business,
        first_name='Ana',
        last_name='Lopez',
        alias='Ana',
        employee_code=code,
        role_type=role_type,
        credential_type=EmployeeProfile.CredentialType.PIN,
        login_code_hash=make_password(pin),
        must_change_pin=must_change_pin,
        status=emp_status,
    )


def _make_employee_token(employee: EmployeeProfile, business: Business) -> str:
    now = timezone.now()
    payload = {
        'actor_type': 'employee',
        'employee_id': str(employee.pk),
        'business_id': business.pk,
        'role_type': employee.role_type,
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(hours=12)).timestamp()),
    }
    backend = TokenBackend(
        algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
        signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
    )
    return backend.encode(payload)


def _employee_client(employee: EmployeeProfile, business: Business) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_EMPLOYEE_TOKEN=_make_employee_token(employee, business))
    return client


def _make_category(business: Business, name: str, is_active: bool = True) -> ProductCategory:
    return ProductCategory.objects.create(business=business, name=name, is_active=is_active)


def _make_product(
    business: Business,
    name: str = 'Producto',
    price: str = '150.00',
    is_active: bool = True,
    category: ProductCategory | None = None,
    sku: str = '',
    barcode: str = '',
) -> Product:
    return Product.objects.create(
        business=business,
        name=name,
        sku=sku or f'SKU-{name[:6].upper()}',
        barcode=barcode,
        price=Decimal(price),
        is_active=is_active,
        category=category,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class PosOfflineBootstrapTests(TestCase):

    def setUp(self):
        self.business = _make_business()
        self.employee = _make_employee(self.business)
        self.client = _employee_client(self.employee, self.business)

        self.category = _make_category(self.business, 'Bebidas')
        self.inactive_category = _make_category(self.business, 'Discontinuados', is_active=False)
        self.product = _make_product(
            self.business, name='Gaseosa', price='200.00', category=self.category,
            sku='SKU-GAS', barcode='779000000001',
        )
        self.inactive_product = _make_product(
            self.business, name='Viejo', price='10.00', is_active=False,
        )

        # Another business with its own data — must never leak.
        self.other_business = _make_business(name='OtherBiz')
        self.other_product = _make_product(self.other_business, name='AjenoProd', price='99.00')

    def _get(self):
        with mock.patch(_ENTITLEMENT_HELPER, return_value=True):
            return self.client.get(URL_BOOTSTRAP)

    def test_authenticated_employee_can_fetch_bootstrap(self):
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['bootstrap_version'], 1)
        self.assertIn('generated_at', response.data)

    def test_unauthenticated_request_is_rejected(self):
        anon = APIClient()
        response = anon.get(URL_BOOTSTRAP)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_contains_correct_business_and_employee(self):
        response = self._get()
        biz = response.data['business']
        emp = response.data['employee']
        self.assertEqual(biz['id'], str(self.business.pk))
        self.assertEqual(biz['name'], self.business.name)
        self.assertEqual(biz['currency'], 'ARS')
        self.assertEqual(emp['id'], str(self.employee.pk))
        self.assertEqual(emp['code'], self.employee.employee_code)
        self.assertEqual(emp['role'], self.employee.role_type)

    def test_contains_business_categories_and_products(self):
        response = self._get()
        category_ids = {c['id'] for c in response.data['categories']}
        product_ids = {p['id'] for p in response.data['products']}
        self.assertIn(str(self.category.pk), category_ids)
        self.assertIn(str(self.product.pk), product_ids)

    def test_excludes_products_from_other_business(self):
        response = self._get()
        product_ids = {p['id'] for p in response.data['products']}
        self.assertNotIn(str(self.other_product.pk), product_ids)

    def test_excludes_inactive_products_and_categories(self):
        response = self._get()
        product_ids = {p['id'] for p in response.data['products']}
        category_ids = {c['id'] for c in response.data['categories']}
        self.assertNotIn(str(self.inactive_product.pk), product_ids)
        self.assertNotIn(str(self.inactive_category.pk), category_ids)

    def test_includes_payment_methods(self):
        response = self._get()
        codes = {m['code'] for m in response.data['payment_methods']}
        self.assertEqual(codes, {'cash', 'transfer', 'card', 'other'})

    def test_includes_commercial_settings(self):
        response = self._get()
        cs = response.data['commercial_settings']
        self.assertIn('allow_sell_without_stock', cs)
        self.assertIn('block_sales_if_no_open_cash_session', cs)
        self.assertIn('require_customer_for_sales', cs)

    def test_includes_operation_settings(self):
        response = self._get()
        ops = response.data['operation_settings']
        self.assertIn('pos_quick_sale_enabled', ops)
        self.assertIn('kitchen_enabled', ops)
        self.assertIn('tables_enabled', ops)
        self.assertIn('counter_orders_enabled', ops)

    def test_offline_policy_is_quick_sale_only_without_kitchen_tables_orders(self):
        response = self._get()
        policy = response.data['offline_policy']
        self.assertEqual(policy['mode'], 'quick_sale_only')
        self.assertFalse(policy['supports_kitchen'])
        self.assertFalse(policy['supports_tables'])
        self.assertFalse(policy['supports_orders'])
        self.assertEqual(policy['expires_in_hours'], 24)

    def test_does_not_expose_tables_kitchen_or_orders_collections(self):
        response = self._get()
        for forbidden_key in ('tables', 'kitchen', 'orders', 'customers', 'sales'):
            self.assertNotIn(forbidden_key, response.data)

    def test_cash_session_null_when_no_open_session(self):
        response = self._get()
        self.assertIsNone(response.data['cash_session'])

    def test_cash_session_returned_when_open_session_exists(self):
        register = CashRegister.objects.create(business=self.business, name='Caja 1')
        session = CashSession.objects.create(
            business=self.business,
            opened_by_employee=self.employee,
            opened_by_name='Ana',
            status=CashSession.Status.OPEN,
            opening_cash_amount=Decimal('500.00'),
            register=register,
        )
        response = self._get()
        cash = response.data['cash_session']
        self.assertIsNotNone(cash)
        self.assertEqual(cash['id'], str(session.pk))
        self.assertEqual(cash['status'], 'open')
        self.assertEqual(cash['register_name'], 'Caja 1')

    def test_offline_policy_enabled_reflects_entitlement_true(self):
        with mock.patch(_ENTITLEMENT_HELPER, return_value=True):
            response = self.client.get(URL_BOOTSTRAP)
        self.assertTrue(response.data['offline_policy']['enabled'])

    def test_offline_policy_enabled_reflects_entitlement_false(self):
        with mock.patch(_ENTITLEMENT_HELPER, return_value=False):
            response = self.client.get(URL_BOOTSTRAP)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['offline_policy']['enabled'])

    def test_product_includes_stock_and_category_id(self):
        ProductStock.objects.update_or_create(
            business=self.business,
            product=self.product,
            defaults={'quantity': Decimal('12.00')},
        )
        response = self._get()
        product = next(
            p for p in response.data['products'] if p['id'] == str(self.product.pk)
        )
        self.assertEqual(product['category_id'], str(self.category.pk))
        self.assertEqual(product['sku'], 'SKU-GAS')
        self.assertEqual(product['barcode'], '779000000001')
        self.assertEqual(Decimal(product['current_stock']), Decimal('12.00'))
        self.assertEqual(Decimal(product['price']), Decimal('200.00'))

    def test_must_change_pin_employee_is_blocked(self):
        emp = _make_employee(
            self.business, code='EMP-PIN', must_change_pin=True,
        )
        client = _employee_client(emp, self.business)
        response = client.get(URL_BOOTSTRAP)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
