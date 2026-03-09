"""
sales/tests/test_pos_sales.py — Backend tests for POS sales operative endpoint.

Test blocks:
  A. Create sale (POST /api/v1/pos/sales/)
     A1. Valid cashier without open session, settings allow no session → 201.
     A2. Valid cashier with open cash session → 201, sale.cash_session set.
     A3. created_by_employee set correctly, created_by is NULL.
     A4. must_change_pin=True blocks access.
     A5. Suspended employee is rejected.
     A6. Role without can_create_sale (kitchen) is rejected.
     A7. Invalid token is rejected.
     A8. Missing items is rejected.
     A9. block_sales_if_no_open_cash_session=True + no session → 400.
     A10. Audit log is created on success.

  B. Get products (GET /api/v1/pos/catalog/products/)
     B1. Returns active products for the employee's business.
     B2. Search filter works (name icontains).
     B3. Invalid token is rejected.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend
from django.conf import settings

from apps.accounts.models import AccessAuditLog, EmployeeProfile
from apps.business.models import Business, CommercialSettings
from apps.cash.models import CashSession
from apps.catalog.models import Product
from apps.sales.models import Sale

User = get_user_model()

# ── URL shortcuts ─────────────────────────────────────────────────────────────

URL_SALES    = '/api/v1/pos/sales/'
URL_PRODUCTS = '/api/v1/pos/catalog/products/'

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_business(name: str = 'PosSalesBiz') -> Business:
    return Business.objects.create(name=name, default_service='gestion', status='active')


def _make_employee(
    business: Business,
    code: str = 'EMP-0001',
    role_type: str = EmployeeProfile.RoleType.CASHIER,
    pin: str = '123456',
    emp_status: str = EmployeeProfile.Status.ACTIVE,
    must_change_pin: bool = False,
) -> EmployeeProfile:
    return EmployeeProfile.objects.create(
        business=business,
        first_name='Test',
        last_name='Employee',
        alias='Tester',
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
        'actor_type':  'employee',
        'employee_id': str(employee.pk),
        'business_id': business.pk,
        'role_type':   employee.role_type,
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


def _make_product(business: Business, name: str = 'Producto Test', price: str = '150.00') -> Product:
    return Product.objects.create(
        business=business,
        name=name,
        sku=f'SKU-{name[:6].upper()}',
        price=Decimal(price),
        is_active=True,
    )


def _make_open_session(employee: EmployeeProfile, business: Business) -> CashSession:
    return CashSession.objects.create(
        business=business,
        opened_by_employee=employee,
        opened_by_name=employee.alias or 'Tester',
        status=CashSession.Status.OPEN,
        opening_cash_amount=Decimal('500.00'),
    )


def _sale_payload(product: Product) -> dict:
    return {
        'payment_method': 'cash',
        'items': [
            {
                'product_id': str(product.pk),
                'quantity': 1,
            }
        ],
    }


# ── A. Create sale ─────────────────────────────────────────────────────────────


class PosSaleCreateTests(TestCase):

    def setUp(self):
        self.business = _make_business()
        self.employee = _make_employee(self.business)
        self.product = _make_product(self.business)
        self.client = _employee_client(self.employee, self.business)

    def _ensure_settings_allow_no_session(self):
        """Ensure CommercialSettings.block_sales_if_no_open_cash_session = False."""
        cs, _ = CommercialSettings.objects.get_or_create(business=self.business)
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.save()
        return cs

    # A1 —————————————————————————————————————————————————————————————————————

    def test_A1_cashier_creates_sale_without_open_session(self):
        self._ensure_settings_allow_no_session()
        resp = self.client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        data = resp.json()
        self.assertIn('sale', data)
        self.assertEqual(data['sale']['payment_method'], 'cash')

    # A2 —————————————————————————————————————————————————————————————————————

    def test_A2_sale_links_to_open_cash_session(self):
        self._ensure_settings_allow_no_session()
        session = _make_open_session(self.employee, self.business)
        resp = self.client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        sale = Sale.objects.get(pk=resp.json()['sale']['id'])
        self.assertEqual(sale.cash_session_id, session.pk)

    # A3 —————————————————————————————————————————————————————————————————————

    def test_A3_created_by_employee_set_correctly(self):
        self._ensure_settings_allow_no_session()
        resp = self.client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        sale = Sale.objects.get(pk=resp.json()['sale']['id'])
        self.assertEqual(sale.created_by_employee_id, self.employee.pk)
        self.assertIsNone(sale.created_by_id)

    # A4 —————————————————————————————————————————————————————————————————————

    def test_A4_must_change_pin_blocks_access(self):
        emp = _make_employee(self.business, code='EMP-0002', must_change_pin=True)
        client = _employee_client(emp, self.business)
        resp = client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.json().get('code'), 'pin_change_required')

    # A5 —————————————————————————————————————————————————————————————————————

    def test_A5_suspended_employee_is_rejected(self):
        emp = _make_employee(
            self.business, code='EMP-0003',
            emp_status=EmployeeProfile.Status.SUSPENDED,
        )
        client = _employee_client(emp, self.business)
        resp = client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # A6 —————————————————————————————————————————————————————————————————————

    def test_A6_kitchen_role_cannot_create_sale(self):
        emp = _make_employee(self.business, code='EMP-0004', role_type=EmployeeProfile.RoleType.KITCHEN)
        client = _employee_client(emp, self.business)
        resp = client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.json().get('code'), 'capability_required')

    # A7 —————————————————————————————————————————————————————————————————————

    def test_A7_invalid_token_is_rejected(self):
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN='this-is-not-a-valid-jwt')
        resp = client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    # A8 —————————————————————————————————————————————————————————————————————

    def test_A8_empty_items_rejected(self):
        self._ensure_settings_allow_no_session()
        payload = {'payment_method': 'cash', 'items': []}
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # A9 —————————————————————————————————————————————————————————————————————

    def test_A9_block_if_no_cash_session_enforced(self):
        cs, _ = CommercialSettings.objects.get_or_create(business=self.business)
        cs.block_sales_if_no_open_cash_session = True
        cs.require_customer_for_sales = False
        cs.save()
        # No open session exists
        resp = self.client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error_code = resp.json().get('error', {}).get('code')
        self.assertEqual(error_code, 'CASH_SESSION_REQUIRED')

    # A10 ————————————————————————————————————————————————————————————————————

    def test_A10_audit_log_created_on_sale(self):
        self._ensure_settings_allow_no_session()
        resp = self.client.post(URL_SALES, _sale_payload(self.product), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        sale_id = resp.json()['sale']['id']
        log = AccessAuditLog.objects.filter(
            action='SALE_CREATED_POS',
            entity_type='sale',
            entity_id=sale_id,
            actor_employee=self.employee,
        ).first()
        self.assertIsNotNone(log, 'Audit log should be created')
        self.assertEqual(log.actor_type, AccessAuditLog.ActorType.EMPLOYEE)


# ── B. Get products ────────────────────────────────────────────────────────────


class PosCatalogProductsTests(TestCase):

    def setUp(self):
        self.business = _make_business(name='CatalogBiz')
        self.employee = _make_employee(self.business)
        self.client = _employee_client(self.employee, self.business)

    def test_B1_returns_active_products(self):
        _make_product(self.business, name='Café', price='50.00')
        _make_product(self.business, name='Té', price='40.00')
        resp = self.client.get(URL_PRODUCTS)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn('results', data)
        names = [p['name'] for p in data['results']]
        self.assertIn('Café', names)
        self.assertIn('Té', names)

    def test_B2_search_filter_works(self):
        _make_product(self.business, name='Empanada de carne', price='80.00')
        _make_product(self.business, name='Pizza', price='200.00')
        resp = self.client.get(URL_PRODUCTS + '?search=empa')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [p['name'] for p in resp.json()['results']]
        self.assertIn('Empanada de carne', names)
        self.assertNotIn('Pizza', names)

    def test_B3_invalid_token_rejected(self):
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN='bad-token')
        resp = client.get(URL_PRODUCTS)
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
