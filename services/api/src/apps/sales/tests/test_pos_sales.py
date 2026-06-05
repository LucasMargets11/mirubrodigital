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

  C. Split payment — POST /api/v1/pos/sales/ with payments array.
     C1. Single payment via payments array → 201, Payment record created.
     C2. Two payments (split) → 201, two Payment records.
     C3. Sum less than total → 400.
     C4. Sum greater than total → 400.
     C5. Negative amount → 400.
     C6. Cash payment with open session impacts session (Payment.session set).
     C7. Transfer payment does not add cash expected total.
     C8. Atomicity: if payments validation fails, no sale/stock created.
     C9. Legacy single payment_method still works (backward compat).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

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
from apps.cash.models import CashSession, Payment
from apps.catalog.models import Product
from apps.inventory.models import StockMovement
from apps.inventory.services import ensure_stock_record
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


# ── C. Split payment ──────────────────────────────────────────────────────────


class PosSplitPaymentTests(TestCase):
    """Tests for the split payment feature (payments array in POST /api/v1/pos/sales/)."""

    def setUp(self):
        self.business = _make_business(name='SplitPayBiz')
        self.employee = _make_employee(self.business, code='EMP-SP01')
        self.product = _make_product(self.business, name='Hamburguesa', price='150.00')
        self.client = _employee_client(self.employee, self.business)
        self._ensure_settings()

    def _ensure_settings(self):
        cs, _ = CommercialSettings.objects.get_or_create(business=self.business)
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.save()

    def _split_payload(self, payments, quantity=1):
        return {
            'items': [{'product_id': str(self.product.pk), 'quantity': quantity}],
            'payments': payments,
        }

    # C1 —————————————————————————————————————————————————————————————————————

    def test_C1_single_payment_via_payments_array(self):
        payload = self._split_payload([
            {'method': 'cash', 'amount': '150.00'},
        ])
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        sale_id = resp.json()['sale']['id']
        sale = Sale.objects.get(pk=sale_id)
        self.assertEqual(sale.total, Decimal('150.00'))
        self.assertEqual(sale.payment_method, 'cash')
        payments = Payment.objects.filter(sale=sale)
        self.assertEqual(payments.count(), 1)
        self.assertEqual(payments.first().method, 'cash')
        self.assertEqual(payments.first().amount, Decimal('150.00'))

    # C2 —————————————————————————————————————————————————————————————————————

    def test_C2_two_payments_split(self):
        # Product is 150 x 2 = 300
        payload = self._split_payload([
            {'method': 'cash', 'amount': '100.00'},
            {'method': 'transfer', 'amount': '200.00', 'reference': 'Op 456'},
        ], quantity=2)
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        sale = Sale.objects.get(pk=resp.json()['sale']['id'])
        self.assertEqual(sale.total, Decimal('300.00'))
        payments = Payment.objects.filter(sale=sale).order_by('amount')
        self.assertEqual(payments.count(), 2)
        cash_pay = payments.get(method='cash')
        self.assertEqual(cash_pay.amount, Decimal('100.00'))
        transfer_pay = payments.get(method='transfer')
        self.assertEqual(transfer_pay.amount, Decimal('200.00'))
        self.assertEqual(transfer_pay.reference, 'Op 456')
        # Primary payment_method on sale should be the largest = transfer
        self.assertEqual(sale.payment_method, 'transfer')

    # C3 —————————————————————————————————————————————————————————————————————

    def test_C3_sum_less_than_total_rejected(self):
        payload = self._split_payload([
            {'method': 'cash', 'amount': '100.00'},
        ])
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # C4 —————————————————————————————————————————————————————————————————————

    def test_C4_sum_greater_than_total_rejected(self):
        payload = self._split_payload([
            {'method': 'cash', 'amount': '200.00'},
        ])
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # C5 —————————————————————————————————————————————————————————————————————

    def test_C5_negative_amount_rejected(self):
        payload = self._split_payload([
            {'method': 'cash', 'amount': '-50.00'},
            {'method': 'transfer', 'amount': '200.00'},
        ])
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # C6 —————————————————————————————————————————————————————————————————————

    def test_C6_cash_payment_with_session_links_correctly(self):
        session = _make_open_session(self.employee, self.business)
        payload = self._split_payload([
            {'method': 'cash', 'amount': '150.00'},
        ])
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        payment = Payment.objects.get(sale_id=resp.json()['sale']['id'])
        self.assertEqual(payment.session_id, session.pk)

    # C7 —————————————————————————————————————————————————————————————————————

    def test_C7_transfer_does_not_impact_cash_expected(self):
        from apps.cash.services import compute_session_totals
        session = _make_open_session(self.employee, self.business)
        # Sale with split: 50 cash + 100 transfer = 150
        payload = self._split_payload([
            {'method': 'cash', 'amount': '50.00'},
            {'method': 'transfer', 'amount': '100.00'},
        ])
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        totals = compute_session_totals(session)
        # Cash expected = opening (500) + cash payments (50) = 550
        self.assertEqual(totals['cash_expected_total'], Decimal('550.00'))
        # Total payments = 150
        self.assertEqual(totals['payments_total'], Decimal('150.00'))
        # Cash-only payments = 50
        self.assertEqual(totals['cash_payments_total'], Decimal('50.00'))

    # C8 —————————————————————————————————————————————————————————————————————

    def test_C8_atomicity_no_stock_deducted_on_payment_failure(self):
        from apps.inventory.models import StockRecord
        from apps.inventory.services import ensure_stock_record
        # Ensure stock record exists and note the initial quantity
        stock = ensure_stock_record(self.business, self.product)
        initial_qty = stock.quantity
        # Wrong total — sum doesn't match
        payload = self._split_payload([
            {'method': 'cash', 'amount': '999.00'},
        ])
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Stock should NOT have changed
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, initial_qty)
        # No sale should have been created
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)

    # C9 —————————————————————————————————————————————————————————————————————

    def test_C9_legacy_payment_method_still_works(self):
        """Old-style payload without payments array still creates a sale."""
        payload = {
            'payment_method': 'cash',
            'items': [{'product_id': str(self.product.pk), 'quantity': 1}],
        }
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        sale = Sale.objects.get(pk=resp.json()['sale']['id'])
        self.assertEqual(sale.payment_method, 'cash')
        self.assertEqual(sale.total, Decimal('150.00'))
        # No Payment records should be created for legacy flow
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 0)


class PosSaleIdempotencyTests(TestCase):

    def setUp(self):
        self.business = _make_business(name='PosIdempotencyBiz')
        self.employee = _make_employee(self.business, code='EMP-ID01')
        self.product = _make_product(self.business, name='Milanesa', price='200.00')
        self.client = _employee_client(self.employee, self.business)
        self._ensure_settings()
        self._set_stock(self.product, '10.00')

    def _ensure_settings(self):
        cs, _ = CommercialSettings.objects.get_or_create(business=self.business)
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.save()

    def _payload(self, **extra):
        payload = {
            'payment_method': 'cash',
            'items': [
                {
                    'product_id': str(self.product.pk),
                    'quantity': 1,
                }
            ],
        }
        payload.update(extra)
        return payload

    def _set_stock(self, product: Product, quantity) -> None:
        stock = ensure_stock_record(product.business, product)
        stock.quantity = Decimal(str(quantity))
        stock.save(update_fields=['quantity', 'updated_at'])

    def test_sale_without_client_order_id_still_works(self):
        resp = self.client.post(URL_SALES, self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertFalse(resp.json()['duplicate'])
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 1)
        sale = Sale.objects.get(business=self.business)
        self.assertIsNone(sale.client_order_id)

    def test_new_client_order_id_is_saved(self):
        client_order_id = uuid4()
        resp = self.client.post(
            URL_SALES,
            self._payload(client_order_id=str(client_order_id)),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertFalse(resp.json()['duplicate'])
        sale = Sale.objects.get(pk=resp.json()['sale']['id'])
        self.assertEqual(sale.client_order_id, client_order_id)
        self.assertEqual(resp.json()['server_id'], str(sale.pk))

    def test_duplicate_client_order_id_returns_existing_sale(self):
        client_order_id = str(uuid4())
        first = self.client.post(URL_SALES, self._payload(client_order_id=client_order_id), format='json')
        second = self.client.post(URL_SALES, self._payload(client_order_id=client_order_id), format='json')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 1)
        self.assertEqual(second.json()['sale']['id'], first.json()['sale']['id'])
        self.assertTrue(second.json()['duplicate'])

    def test_same_client_order_id_can_be_reused_in_another_business(self):
        other_business = _make_business(name='OtherIdempotencyBiz')
        other_employee = _make_employee(other_business, code='EMP-ID02')
        other_product = _make_product(other_business, name='Pizza', price='220.00')
        other_client = _employee_client(other_employee, other_business)
        cs, _ = CommercialSettings.objects.get_or_create(business=other_business)
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.save()
        other_stock = ensure_stock_record(other_business, other_product)
        other_stock.quantity = Decimal('10.00')
        other_stock.save(update_fields=['quantity', 'updated_at'])

        client_order_id = str(uuid4())
        first = self.client.post(URL_SALES, self._payload(client_order_id=client_order_id), format='json')
        second = other_client.post(
            URL_SALES,
            {
                'payment_method': 'cash',
                'client_order_id': client_order_id,
                'items': [{'product_id': str(other_product.pk), 'quantity': 1}],
            },
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED, second.data)
        self.assertEqual(Sale.objects.filter(client_order_id=client_order_id).count(), 2)

    def test_invalid_client_order_id_returns_400(self):
        resp = self.client.post(
            URL_SALES,
            self._payload(client_order_id='not-a-uuid'),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('client_order_id', resp.json())
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)

    def test_failed_validation_does_not_leave_partial_sale(self):
        payload = self._payload(
            client_order_id=str(uuid4()),
            payments=[{'method': 'cash', 'amount': '999.00'}],
        )
        resp = self.client.post(URL_SALES, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
        self.assertEqual(Payment.objects.filter(business=self.business).count(), 0)

    def test_cash_session_failure_does_not_leave_partial_sale(self):
        cs, _ = CommercialSettings.objects.get_or_create(business=self.business)
        cs.block_sales_if_no_open_cash_session = True
        cs.require_customer_for_sales = False
        cs.save()

        resp = self.client.post(
            URL_SALES,
            self._payload(client_order_id=str(uuid4())),
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['error']['code'], 'CASH_SESSION_REQUIRED')
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
        self.assertEqual(Payment.objects.filter(business=self.business).count(), 0)

    def test_stock_failure_does_not_leave_partial_sale(self):
        cs, _ = CommercialSettings.objects.get_or_create(business=self.business)
        cs.allow_sell_without_stock = False
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.save()

        self._set_stock(self.product, '0.00')

        resp = self.client.post(
            URL_SALES,
            self._payload(client_order_id=str(uuid4())),
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
        self.assertEqual(Payment.objects.filter(business=self.business).count(), 0)
        self.assertEqual(
            StockMovement.objects.filter(
                business=self.business,
                product=self.product,
                movement_type=StockMovement.MovementType.OUT,
            ).count(),
            0,
        )

    def test_duplicate_retry_does_not_deduct_stock_twice(self):
        client_order_id = str(uuid4())
        payload = self._payload(client_order_id=client_order_id)
        initial_stock = ensure_stock_record(self.business, self.product).quantity

        first = self.client.post(URL_SALES, payload, format='json')
        stock_after_first = ensure_stock_record(self.business, self.product).quantity
        stock_movements_after_first = StockMovement.objects.filter(
            business=self.business,
            product=self.product,
            movement_type=StockMovement.MovementType.OUT,
        ).count()
        second = self.client.post(URL_SALES, payload, format='json')
        stock_after_second = ensure_stock_record(self.business, self.product).quantity
        stock_movements_after_second = StockMovement.objects.filter(
            business=self.business,
            product=self.product,
            movement_type=StockMovement.MovementType.OUT,
        ).count()

        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual(stock_after_first, initial_stock - Decimal('1.00'))
        self.assertEqual(stock_after_second, stock_after_first)
        self.assertEqual(stock_movements_after_first, 1)
        self.assertEqual(stock_movements_after_second, 1)

    def test_duplicate_retry_does_not_duplicate_payment_or_cash_totals(self):
        from apps.cash.services import compute_session_totals

        session = _make_open_session(self.employee, self.business)
        client_order_id = str(uuid4())
        payload = {
            'client_order_id': client_order_id,
            'items': [{'product_id': str(self.product.pk), 'quantity': 1}],
            'payments': [{'method': 'cash', 'amount': '200.00'}],
        }

        first = self.client.post(URL_SALES, payload, format='json')
        totals_after_first = compute_session_totals(session)
        second = self.client.post(URL_SALES, payload, format='json')
        totals_after_second = compute_session_totals(session)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual(Payment.objects.filter(sale_id=first.json()['sale']['id']).count(), 1)
        self.assertEqual(Payment.objects.filter(session=session).count(), 1)
        self.assertEqual(totals_after_first['cash_expected_total'], totals_after_second['cash_expected_total'])
        self.assertEqual(totals_after_first['payments_total'], totals_after_second['payments_total'])
