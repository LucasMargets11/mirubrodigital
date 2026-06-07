from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend

from apps.accounts.models import EmployeeProfile, Membership
from apps.business.models import Business, BusinessPlan, CommercialSettings, Subscription
from apps.cash.models import Payment
from apps.catalog.models import Product
from apps.inventory.models import ProductStock, StockMovement
from apps.orders.models import Order
from apps.sales.models import Sale

URL_COUNTER_ORDERS = '/api/v1/pos/orders/counter/'
URL_POS_SALES = '/api/v1/pos/sales/'
URL_KITCHEN_BOARD = '/api/v1/orders/kitchen/board/'

User = get_user_model()


def _make_business(name: str = 'PosCounterBiz') -> Business:
    business = Business.objects.create(name=name, default_service='restaurante', status='active')
    Subscription.objects.create(business=business, plan=BusinessPlan.PLUS, status='active')
    return business


def _make_employee(
    business: Business,
    code: str = 'EMP-COUNTER-01',
    role_type: str = EmployeeProfile.RoleType.CASHIER,
    pin: str = '123456',
    emp_status: str = EmployeeProfile.Status.ACTIVE,
    must_change_pin: bool = False,
) -> EmployeeProfile:
    return EmployeeProfile.objects.create(
        business=business,
        first_name='Caja',
        last_name='Counter',
        alias='Caja Counter',
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


def _owner_client(business: Business) -> APIClient:
    user = User.objects.create_user(
        username=f'owner-{business.pk}',
        email=f'owner-{business.pk}@example.com',
        password='pass1234',
    )
    Membership.objects.create(user=user, business=business, role='owner')
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies['bid'] = str(business.id)
    return client


def _make_product(
    business: Business,
    *,
    name: str = 'Hamburguesa Mostrador',
    price: str = '120.00',
    stock: str = '10.00',
    is_active: bool = True,
) -> Product:
    product = Product.objects.create(
        business=business,
        name=name,
        sku=f'SKU-{name[:8].upper()}',
        barcode='123456789',
        cost=Decimal('50.00'),
        price=Decimal(price),
        stock_min=Decimal('1.00'),
        is_active=is_active,
    )
    ProductStock.objects.create(business=business, product=product, quantity=Decimal(stock))
    return product


class PosCounterOrderCreateTests(TestCase):

    def setUp(self):
        self.business = _make_business()
        self.employee = _make_employee(self.business)
        self.client = _employee_client(self.employee, self.business)
        self.owner_client = _owner_client(self.business)
        self.product = _make_product(self.business)
        settings_obj = CommercialSettings.objects.for_business(self.business)
        settings_obj.block_sales_if_no_open_cash_session = False
        settings_obj.require_customer_for_sales = False
        settings_obj.save()

    def _payload(self, **extra):
        payload = {
            'items': [
                {
                    'product_id': str(self.product.pk),
                    'quantity': '2',
                    'note': 'sin cebolla',
                }
            ],
            'customer_name': 'Mostrador 4',
            'note': 'retira en caja',
            'send_to_kitchen': True,
        }
        payload.update(extra)
        return payload

    def test_employee_pos_can_create_counter_order(self):
        response = self.client.post(URL_COUNTER_ORDERS, self._payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(pk=response.json()['id'])
        self.assertEqual(order.channel, Order.Channel.PICKUP)
        self.assertEqual(order.status, Order.Status.SENT)
        self.assertIsNone(order.table_id)
        self.assertEqual(order.customer_name, 'Mostrador 4')
        self.assertEqual(order.note, 'retira en caja')
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().kitchen_status, order.items.first().KitchenStatus.PENDING)

    def test_request_without_valid_pos_token_is_rejected(self):
        client = APIClient()
        response = client.post(URL_COUNTER_ORDERS, self._payload(), format='json')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_counter_order_pos_creates_no_sale_payment_or_stock_movement(self):
        initial_quantity = ProductStock.objects.get(product=self.product).quantity
        response = self.client.post(URL_COUNTER_ORDERS, self._payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(pk=response.json()['id'])
        self.assertIsNone(order.sale_id)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        stock = ProductStock.objects.get(product=self.product)
        self.assertEqual(stock.quantity, initial_quantity)

    def test_counter_order_pos_appears_in_kitchen_board_when_sent(self):
        response = self.client.post(URL_COUNTER_ORDERS, self._payload(send_to_kitchen=True), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        board_response = self.owner_client.get(URL_KITCHEN_BOARD)
        self.assertEqual(board_response.status_code, status.HTTP_200_OK, board_response.data)
        order_ids = {str(item['id']) for item in board_response.json()}
        self.assertIn(response.json()['id'], order_ids)

    def test_product_from_other_business_is_rejected(self):
        other_business = _make_business('PosCounterOtherBiz')
        other_product = _make_product(other_business)

        response = self.client.post(
            URL_COUNTER_ORDERS,
            self._payload(items=[{'product_id': str(other_product.pk), 'quantity': '1'}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product_id', str(response.json()))

    def test_inactive_product_is_rejected(self):
        inactive_product = _make_product(self.business, name='Inactivo', is_active=False)

        response = self.client.post(
            URL_COUNTER_ORDERS,
            self._payload(items=[{'product_id': str(inactive_product.pk), 'quantity': '1'}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product_id', str(response.json()))

    def test_invalid_quantity_is_rejected(self):
        response = self.client.post(
            URL_COUNTER_ORDERS,
            self._payload(items=[{'product_id': str(self.product.pk), 'quantity': '0'}]),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity', str(response.json()))

    def test_pos_sale_endpoint_still_works(self):
        response = self.client.post(
            URL_POS_SALES,
            {
                'payment_method': 'cash',
                'items': [
                    {
                        'product_id': str(self.product.pk),
                        'quantity': 1,
                    }
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Sale.objects.count(), 1)