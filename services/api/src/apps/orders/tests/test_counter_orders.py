from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.cash.models import Payment
from apps.catalog.models import Product
from apps.inventory.models import ProductStock
from apps.orders.models import Order, OrderItem


class CounterOrderCreateTests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='counter-orders',
      email='counter-orders@example.com',
      password='pass1234',
    )

  def _create_business(self, name: str = 'Counter Orders Biz') -> Business:
    business = Business.objects.create(name=name, default_service='restaurante')
    Subscription.objects.create(business=business, plan=BusinessPlan.PLUS, service='restaurante', status='active')
    return business

  def _authenticate(self, business: Business, role: str = 'owner'):
    Membership.objects.create(user=self.user, business=business, role=role)
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)

  def _create_product(self, business: Business, *, name='Hamburguesa', price='120.00', stock='10.00', is_active=True) -> Product:
    product = Product.objects.create(
      business=business,
      name=name,
      sku=f'SKU-{name[:6].upper()}',
      barcode='123456',
      cost=Decimal('50.00'),
      price=Decimal(price),
      stock_min=Decimal('1.00'),
      is_active=is_active,
    )
    ProductStock.objects.create(business=business, product=product, quantity=Decimal(stock))
    return product

  def test_create_counter_order_creates_pickup_order_without_table(self):
    business = self._create_business()
    self._authenticate(business)
    product = self._create_product(business)

    response = self.client.post(
      reverse('orders:order-counter-create'),
      {
        'items': [
          {
            'product_id': str(product.id),
            'quantity': '2',
            'note': 'sin cebolla',
          }
        ],
        'customer_name': 'Mostrador 12',
        'note': 'pedido para retirar',
        'send_to_kitchen': True,
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    order = Order.objects.get(pk=response.data['id'])
    self.assertEqual(order.channel, Order.Channel.PICKUP)
    self.assertIsNone(order.table_id)
    self.assertEqual(order.table_name, '')
    self.assertEqual(order.customer_name, 'Mostrador 12')
    self.assertEqual(order.note, 'pedido para retirar')
    self.assertEqual(order.status, Order.Status.SENT)
    self.assertEqual(order.items.count(), 1)

    item = order.items.first()
    self.assertIsNotNone(item)
    self.assertEqual(item.product_id, product.id)
    self.assertEqual(item.note, 'sin cebolla')
    self.assertEqual(item.kitchen_status, OrderItem.KitchenStatus.PENDING)

  def test_send_to_kitchen_false_creates_open_order(self):
    business = self._create_business('Counter Open')
    self._authenticate(business)
    product = self._create_product(business)

    response = self.client.post(
      reverse('orders:order-counter-create'),
      {
        'items': [{'product_id': str(product.id), 'quantity': '1'}],
        'send_to_kitchen': False,
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    order = Order.objects.get(pk=response.data['id'])
    self.assertEqual(order.status, Order.Status.OPEN)

  def test_counter_order_does_not_create_sale_payment_or_discount_stock(self):
    business = self._create_business('No Sale Side Effects')
    self._authenticate(business)
    product = self._create_product(business, stock='7.00')

    response = self.client.post(
      reverse('orders:order-counter-create'),
      {
        'items': [{'product_id': str(product.id), 'quantity': '3'}],
        'send_to_kitchen': True,
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    order = Order.objects.get(pk=response.data['id'])
    self.assertIsNone(order.sale_id)
    self.assertEqual(Payment.objects.count(), 0)
    stock = ProductStock.objects.get(product=product)
    self.assertEqual(stock.quantity, Decimal('7.00'))

  def test_counter_order_sent_appears_in_kitchen_board(self):
    business = self._create_business('Kitchen Board Counter')
    self._authenticate(business)
    product = self._create_product(business)

    create_response = self.client.post(
      reverse('orders:order-counter-create'),
      {
        'items': [{'product_id': str(product.id), 'quantity': '1'}],
        'customer_name': 'Mostrador 5',
        'send_to_kitchen': True,
      },
      format='json',
    )
    self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

    board_response = self.client.get(reverse('orders:kitchen-board'))
    self.assertEqual(board_response.status_code, status.HTTP_200_OK)
    order_ids = {str(item['id']) for item in board_response.data}
    self.assertIn(create_response.data['id'], order_ids)

  def test_rejects_product_from_other_business(self):
    business = self._create_business('Local Business')
    other = self._create_business('Other Business')
    self._authenticate(business)
    external_product = self._create_product(other)

    response = self.client.post(
      reverse('orders:order-counter-create'),
      {
        'items': [{'product_id': str(external_product.id), 'quantity': '1'}],
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('product_id', str(response.data))

  def test_rejects_inactive_product(self):
    business = self._create_business('Inactive Product Biz')
    self._authenticate(business)
    product = self._create_product(business, is_active=False)

    response = self.client.post(
      reverse('orders:order-counter-create'),
      {
        'items': [{'product_id': str(product.id), 'quantity': '1'}],
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('product_id', str(response.data))

  def test_rejects_invalid_quantity(self):
    business = self._create_business('Invalid Quantity Biz')
    self._authenticate(business)
    product = self._create_product(business)

    response = self.client.post(
      reverse('orders:order-counter-create'),
      {
        'items': [{'product_id': str(product.id), 'quantity': '0'}],
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('quantity', str(response.data))
