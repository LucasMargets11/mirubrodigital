from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.catalog.models import Product
from apps.cash.models import CashSession, Payment
from apps.inventory.models import ProductStock
from apps.sales.models import Sale, SaleItem


class SalesAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(username='seller', email='seller@example.com', password='pass1234')

  def _create_business(self, name: str = 'Mi Negocio') -> Business:
    business = Business.objects.create(name=name)
    Subscription.objects.create(business=business, plan='starter', status='active')
    return business

  def _authenticate(self, business: Business, role: str):
    Membership.objects.create(user=self.user, business=business, role=role)
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)

  def _create_product(self, business: Business, stock: Decimal) -> Product:
    product = Product.objects.create(
      business=business,
      name='Producto Test',
      sku='SKU-TEST',
      barcode='123',
      cost=Decimal('50'),
      price=Decimal('120'),
      stock_min=Decimal('2'),
    )
    ProductStock.objects.create(business=business, product=product, quantity=stock)
    return product

  def _create_sale_with_items(self, business: Business, items) -> Sale:
    number = Sale.objects.filter(business=business).count() + 1
    subtotal = sum((item['unit_price'] * item['quantity'] for item in items), Decimal('0'))
    sale = Sale.objects.create(
      business=business,
      number=number,
      subtotal=subtotal,
      discount=Decimal('0'),
      total=subtotal,
      payment_method=Sale.PaymentMethod.CASH,
    )
    for item in items:
      line_total = item['unit_price'] * item['quantity']
      SaleItem.objects.create(
        sale=sale,
        product=item['product'],
        product_name_snapshot=item['product'].name,
        quantity=item['quantity'],
        unit_price=item['unit_price'],
        line_total=line_total,
      )
    return sale

  def test_create_sale_requires_permission(self):
    business = self._create_business('Solo lectura')
    product = self._create_product(business, Decimal('10'))
    self._authenticate(business, role='viewer')

    url = reverse('sales:sale-list')
    payload = {
      'items': [
        {
          'product_id': str(product.id),
          'quantity': '1',
        }
      ],
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_create_sale_with_insufficient_stock_returns_400(self):
    business = self._create_business('Stock limitado')
    product = self._create_product(business, Decimal('2'))
    self._authenticate(business, role='cashier')

    url = reverse('sales:sale-list')
    payload = {
      'items': [
        {
          'product_id': str(product.id),
          'quantity': '5',
        }
      ],
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('items', response.data)

  def test_create_sale_deducts_stock_and_returns_totals(self):
    business = self._create_business('Caja')
    product = self._create_product(business, Decimal('10'))
    self._authenticate(business, role='cashier')

    url = reverse('sales:sale-list')
    payload = {
      'payment_method': 'cash',
      'discount': '50.00',
      'notes': 'Venta mostrador',
      'items': [
        {
          'product_id': str(product.id),
          'quantity': '3',
          'unit_price': '150.00',
        }
      ],
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertEqual(Sale.objects.count(), 1)

    sale = Sale.objects.first()
    self.assertEqual(sale.subtotal, Decimal('450.00'))
    self.assertEqual(sale.discount, Decimal('50.00'))
    self.assertEqual(sale.total, Decimal('400.00'))

    stock = ProductStock.objects.get(product=product)
    self.assertEqual(stock.quantity, Decimal('7.00'))

    self.assertEqual(response.data['subtotal'], '450.00')
    self.assertEqual(response.data['total'], '400.00')
    self.assertEqual(len(response.data['items']), 1)

  def test_sale_list_paid_total_not_duplicated_by_items(self):
    business = self._create_business('Pagos sin duplicar')
    product_a = self._create_product(business, Decimal('10'))
    product_b = self._create_product(business, Decimal('5'))
    sale = self._create_sale_with_items(
      business,
      [
        {'product': product_a, 'quantity': Decimal('1'), 'unit_price': Decimal('1000.00')},
        {'product': product_b, 'quantity': Decimal('2'), 'unit_price': Decimal('2000.00')},
      ],
    )
    session = CashSession.objects.create(business=business, opened_by=self.user, opening_cash_amount=Decimal('0'))
    Payment.objects.create(
      business=business,
      sale=sale,
      session=session,
      method=Payment.Method.CASH,
      amount=Decimal('5000.00'),
    )

    self._authenticate(business, role='cashier')
    url = reverse('sales:sale-list')
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(len(response.data['results']), 1)
    sale_data = response.data['results'][0]
    self.assertEqual(Decimal(sale_data['paid_total']), Decimal('5000.00'))
    self.assertEqual(Decimal(sale_data['balance']), Decimal('0'))

  def test_sale_detail_paid_total_sums_multiple_payments(self):
    business = self._create_business('Pagos múltiples')
    product_a = self._create_product(business, Decimal('10'))
    product_b = self._create_product(business, Decimal('5'))
    sale = self._create_sale_with_items(
      business,
      [
        {'product': product_a, 'quantity': Decimal('1'), 'unit_price': Decimal('4000.00')},
        {'product': product_b, 'quantity': Decimal('1'), 'unit_price': Decimal('5000.00')},
      ],
    )

    session = CashSession.objects.create(business=business, opened_by=self.user, opening_cash_amount=Decimal('0'))
    Payment.objects.create(
      business=business,
      sale=sale,
      session=session,
      method=Payment.Method.CASH,
      amount=Decimal('5000.00'),
    )
    Payment.objects.create(
      business=business,
      sale=sale,
      session=session,
      method=Payment.Method.DEBIT,
      amount=Decimal('2000.00'),
    )

    self._authenticate(business, role='cashier')
    url = reverse('sales:sale-detail', args=[sale.id])
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(Decimal(response.data['paid_total']), Decimal('7000.00'))
    self.assertEqual(Decimal(response.data['balance']), Decimal('2000.00'))
