from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, CommercialSettings, Subscription
from apps.cash.models import CashSession, Payment
from apps.catalog.models import Product
from apps.inventory.models import ProductStock
from apps.orders.models import Order, OrderItem
from apps.sales.models import Sale


class OrderCheckoutFlowTests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(username='cashier', email='cashier@example.com', password='pass1234')

  def _create_business(self, name: str = 'Checkout Corp') -> Business:
    business = Business.objects.create(name=name, default_service='restaurante')
    Subscription.objects.create(business=business, plan=BusinessPlan.PLUS, status='active')
    settings = CommercialSettings.objects.for_business(business)
    settings.block_sales_if_no_open_cash_session = False
    settings.allow_sell_without_stock = False
    settings.save()
    return business

  def _authenticate(self, business: Business, role: str = 'cashier'):
    Membership.objects.create(user=self.user, business=business, role=role)
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)

  def _create_product(self, business: Business, *, stock: Decimal = Decimal('10'), price: Decimal = Decimal('150')) -> Product:
    product = Product.objects.create(
      business=business,
      name='Combo Especial',
      sku='CB-01',
      barcode='111222333',
      cost=Decimal('80.00'),
      price=price,
      stock_min=Decimal('2'),
    )
    ProductStock.objects.create(business=business, product=product, quantity=stock)
    return product

  def _create_order(self, business: Business, product: Product, *, quantity: Decimal = Decimal('1')) -> Order:
    order = Order.objects.create(business=business, number=1, total_amount=Decimal('0'))
    line_total = quantity * product.price
    OrderItem.objects.create(
      order=order,
      product=product,
      name=product.name,
      quantity=quantity,
      unit_price=product.price,
      total_price=line_total,
    )
    order.total_amount = line_total
    order.save(update_fields=['total_amount'])
    return order

  def _open_cash_session(self, business: Business) -> CashSession:
    return CashSession.objects.create(business=business, opened_by=self.user, opening_cash_amount=Decimal('0'))

  def test_create_sale_endpoint_creates_sale(self):
    business = self._create_business()
    product = self._create_product(business)
    order = self._create_order(business, product)
    self._authenticate(business)

    url = reverse('orders:order-create-sale', args=[order.id])
    response = self.client.post(url, {'payment_method': Sale.PaymentMethod.CASH}, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    order.refresh_from_db()
    self.assertIsNotNone(order.sale_id)
    sale = order.sale
    self.assertIsNotNone(sale)
    self.assertEqual(sale.total, Decimal(order.total_amount))
    self.assertEqual(sale.items.count(), 1)

  def test_checkout_returns_totals_with_existing_payments(self):
    business = self._create_business('Resumen Test')
    product = self._create_product(business)
    order = self._create_order(business, product, quantity=Decimal('2'))
    self._authenticate(business)

    create_url = reverse('orders:order-create-sale', args=[order.id])
    self.client.post(create_url, {'payment_method': Sale.PaymentMethod.CASH}, format='json')
    order.refresh_from_db()
    session = self._open_cash_session(business)
    Payment.objects.create(
      business=business,
      sale=order.sale,
      session=session,
      method=Payment.Method.CASH,
      amount=Decimal('100.00'),
      reference='',
      created_by=self.user,
    )

    url = reverse('orders:order-checkout', args=[order.id])
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertIn('totals', response.data)
    totals = response.data['totals']
    self.assertEqual(totals['paid_total'], '100.00')
    expected_balance = Decimal(order.sale.total) - Decimal('100.00')
    self.assertEqual(totals['balance'], f"{expected_balance:.2f}")

  def test_pay_order_creates_payments_and_marks_order_paid(self):
    business = self._create_business('Cobro Test')
    product = self._create_product(business)
    order = self._create_order(business, product)
    self._authenticate(business)
    self.client.post(reverse('orders:order-create-sale', args=[order.id]), {'payment_method': Sale.PaymentMethod.CASH}, format='json')
    order.refresh_from_db()
    session = self._open_cash_session(business)

    pay_url = reverse('orders:order-pay', args=[order.id])
    response = self.client.post(
      pay_url,
      {
        'cash_session_id': str(session.id),
        'payments': [
          {
            'method': Payment.Method.CASH,
            'amount': str(order.sale.total),
            'reference': 'Caja principal',
          }
        ],
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    order.refresh_from_db()
    self.assertEqual(order.status, Order.Status.PAID)
    sale = order.sale
    self.assertEqual(sale.cash_session_id, session.id)
    payments = sale.payments.all()
    self.assertEqual(payments.count(), 1)
    self.assertEqual(payments.first().amount, sale.total)

  def test_pay_order_conflict_when_already_paid(self):
    business = self._create_business('Conflicto Pago')
    product = self._create_product(business)
    order = self._create_order(business, product)
    self._authenticate(business)
    self.client.post(reverse('orders:order-create-sale', args=[order.id]), {'payment_method': Sale.PaymentMethod.CASH}, format='json')
    order.refresh_from_db()
    session = self._open_cash_session(business)

    pay_url = reverse('orders:order-pay', args=[order.id])
    payload = {
      'cash_session_id': str(session.id),
      'payments': [
        {'method': Payment.Method.CASH, 'amount': str(order.total_amount)},
      ],
    }
    first_response = self.client.post(pay_url, payload, format='json')
    self.assertEqual(first_response.status_code, status.HTTP_200_OK)

    second_response = self.client.post(pay_url, payload, format='json')
    self.assertEqual(second_response.status_code, status.HTTP_409_CONFLICT)

  def test_pay_order_conflict_when_session_closed(self):
    business = self._create_business('Sesion Cerrada')
    product = self._create_product(business)
    order = self._create_order(business, product)
    self._authenticate(business)
    self.client.post(reverse('orders:order-create-sale', args=[order.id]), {'payment_method': Sale.PaymentMethod.CASH}, format='json')
    order.refresh_from_db()
    session = self._open_cash_session(business)
    session.status = CashSession.Status.CLOSED
    session.save(update_fields=['status'])

    pay_url = reverse('orders:order-pay', args=[order.id])
    response = self.client.post(
      pay_url,
      {
        'cash_session_id': str(session.id),
        'payments': [
          {'method': Payment.Method.CASH, 'amount': str(order.total_amount)},
        ],
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
*** End File