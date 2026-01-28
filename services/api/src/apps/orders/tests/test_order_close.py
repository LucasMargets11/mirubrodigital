from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, CommercialSettings, Subscription
from apps.catalog.models import Product
from apps.inventory.models import ProductStock
from apps.orders.models import Order, OrderItem
from apps.sales.models import Sale


class OrderCloseAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='resto', email='resto@example.com', password='pass1234'
    )

  def _create_business(self, name: str = 'La Pizzeria') -> Business:
    business = Business.objects.create(name=name, default_service='restaurante')
    Subscription.objects.create(business=business, plan=BusinessPlan.PLUS, status='active')
    settings = CommercialSettings.objects.for_business(business)
    settings.block_sales_if_no_open_cash_session = False
    settings.save()
    return business

  def _authenticate(self, business: Business, role: str = 'cashier'):
    Membership.objects.create(user=self.user, business=business, role=role)
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)

  def _create_product(self, business: Business, *, stock: Decimal = Decimal('10')) -> Product:
    product = Product.objects.create(
      business=business,
      name='Pizza Margarita',
      sku='PIZZA-001',
      barcode='1234567890',
      cost=Decimal('100.00'),
      price=Decimal('250.00'),
      stock_min=Decimal('2.00'),
    )
    ProductStock.objects.create(business=business, product=product, quantity=stock)
    return product

  def _create_order(self, business: Business, product: Product, *, quantity: Decimal = Decimal('1'), unit_price: Decimal = Decimal('100')) -> Order:
    order = Order.objects.create(business=business, number=1, total_amount=Decimal('0'))
    total = quantity * unit_price
    OrderItem.objects.create(
      order=order,
      product=product,
      name=product.name,
      quantity=quantity,
      unit_price=unit_price,
      total_price=total,
    )
    order.total_amount = total
    order.save(update_fields=['total_amount'])
    return order

  def test_close_order_creates_sale_and_updates_status(self):
    business = self._create_business()
    product = self._create_product(business)
    order = self._create_order(business, product, quantity=Decimal('2'), unit_price=Decimal('150.00'))
    self._authenticate(business, role='cashier')

    url = reverse('orders:order-close', args=[order.id])
    response = self.client.post(url, {'payment_method': 'cash'}, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    order.refresh_from_db()
    self.assertEqual(order.status, Order.Status.PAID)
    self.assertIsNotNone(order.sale_id)

    sale = Sale.objects.get(pk=order.sale_id)
    self.assertEqual(sale.total, Decimal('300.00'))

    stock = ProductStock.objects.get(product=product)
    self.assertEqual(stock.quantity, Decimal('8.00'))

  def test_close_order_requires_permission(self):
    business = self._create_business('Sin permisos')
    product = self._create_product(business)
    order = self._create_order(business, product)
    self._authenticate(business, role='viewer')

    url = reverse('orders:order-close', args=[order.id])
    response = self.client.post(url, {'payment_method': 'cash'}, format='json')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    order.refresh_from_db()
    self.assertIsNone(order.sale_id)

  def test_close_order_respects_stock_limits(self):
    business = self._create_business('Stock limitado')
    product = self._create_product(business, stock=Decimal('1'))
    order = self._create_order(business, product, quantity=Decimal('3'), unit_price=Decimal('120.00'))
    self._authenticate(business, role='cashier')

    url = reverse('orders:order-close', args=[order.id])
    response = self.client.post(url, {'payment_method': 'cash'}, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('error', response.data)
    self.assertEqual(response.data['error']['code'], 'OUT_OF_STOCK')
    order.refresh_from_db()
    self.assertIsNone(order.sale_id)

  def test_close_order_requires_customer_when_setting_enabled(self):
    business = self._create_business('Cliente obligatorio')
    settings = CommercialSettings.objects.for_business(business)
    settings.require_customer_for_sales = True
    settings.save()
    product = self._create_product(business)
    order = self._create_order(business, product)
    self._authenticate(business, role='cashier')

    url = reverse('orders:order-close', args=[order.id])
    response = self.client.post(url, {'payment_method': 'cash'}, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertEqual(response.data['error']['code'], 'CUSTOMER_REQUIRED')

  def test_close_order_allows_negative_stock_when_setting_enabled(self):
    business = self._create_business('Permitir negativo')
    settings = CommercialSettings.objects.for_business(business)
    settings.allow_sell_without_stock = True
    settings.save()
    product = self._create_product(business, stock=Decimal('1'))
    order = self._create_order(business, product, quantity=Decimal('4'), unit_price=Decimal('100.00'))
    self._authenticate(business, role='cashier')

    url = reverse('orders:order-close', args=[order.id])
    response = self.client.post(url, {'payment_method': 'cash'}, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    order.refresh_from_db()
    self.assertEqual(order.status, Order.Status.PAID)
    stock = ProductStock.objects.get(product=product)
    self.assertEqual(stock.quantity, Decimal('-3.00'))
