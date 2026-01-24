from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, CommercialSettings, Subscription
from apps.catalog.models import Product
from apps.cash.models import CashSession, Payment
from apps.inventory.models import ProductStock, StockMovement
from apps.sales.models import Sale, SaleItem


class SalesAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(username='seller', email='seller@example.com', password='pass1234')

  def _create_business(self, name: str = 'Mi Negocio', *, disable_cash_block: bool = True) -> Business:
    business = Business.objects.create(name=name)
    Subscription.objects.create(business=business, plan='starter', status='active')
    if disable_cash_block:
      settings = CommercialSettings.objects.for_business(business)
      settings.block_sales_if_no_open_cash_session = False
      settings.save()
    return business

  def _configure_settings(self, business: Business, **kwargs) -> CommercialSettings:
    settings = CommercialSettings.objects.for_business(business)
    for field, value in kwargs.items():
      setattr(settings, field, value)
    settings.save()
    return settings

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
    self.assertIn('error', response.data)
    self.assertEqual(response.data['error']['code'], 'OUT_OF_STOCK')

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

  def test_create_sale_links_cash_session_when_provided(self):
    business = self._create_business('Caja activa')
    product = self._create_product(business, Decimal('5'))
    session = CashSession.objects.create(business=business, opened_by=self.user, opening_cash_amount=Decimal('100'))
    self._authenticate(business, role='cashier')

    url = reverse('sales:sale-list')
    payload = {
      'payment_method': 'cash',
      'cash_session_id': str(session.id),
      'items': [
        {
          'product_id': str(product.id),
          'quantity': '1',
        }
      ],
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    sale = Sale.objects.first()
    self.assertIsNotNone(sale)
    self.assertEqual(sale.cash_session_id, session.id)

  def test_create_sale_rejects_closed_cash_session(self):
    business = self._create_business('Caja cerrada')
    product = self._create_product(business, Decimal('5'))
    session = CashSession.objects.create(business=business, opened_by=self.user, opening_cash_amount=Decimal('50'))
    session.status = CashSession.Status.CLOSED
    session.save(update_fields=['status'])
    self._authenticate(business, role='cashier')

    url = reverse('sales:sale-list')
    payload = {
      'payment_method': 'cash',
      'cash_session_id': str(session.id),
      'items': [
        {
          'product_id': str(product.id),
          'quantity': '1',
        }
      ],
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('cash_session_id', response.data)

  def test_create_sale_blocked_without_cash_session_when_setting_enabled(self):
    business = self._create_business('Caja obligatoria', disable_cash_block=False)
    product = self._create_product(business, Decimal('3'))
    self._authenticate(business, role='cashier')

    url = reverse('sales:sale-list')
    payload = {
      'items': [
        {'product_id': str(product.id), 'quantity': '1'},
      ]
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertEqual(response.data['error']['code'], 'CASH_SESSION_REQUIRED')

  def test_create_sale_requires_customer_when_setting_enabled(self):
    business = self._create_business('Cliente obligatorio')
    self._configure_settings(business, require_customer_for_sales=True)
    product = self._create_product(business, Decimal('4'))
    self._authenticate(business, role='cashier')

    url = reverse('sales:sale-list')
    payload = {
      'items': [
        {'product_id': str(product.id), 'quantity': '1'},
      ]
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertEqual(response.data['error']['code'], 'CUSTOMER_REQUIRED')

  def test_create_sale_allows_negative_stock_when_permitted(self):
    business = self._create_business('Venta sin stock')
    settings = self._configure_settings(business, allow_sell_without_stock=True)
    product = self._create_product(business, Decimal('2'))
    self._authenticate(business, role='cashier')

    url = reverse('sales:sale-list')
    payload = {
      'items': [
        {'product_id': str(product.id), 'quantity': '5'},
      ]
    }

    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    stock = ProductStock.objects.get(product=product)
    self.assertEqual(stock.quantity, Decimal('-3.00'))
    movement = StockMovement.objects.filter(product=product).first()
    self.assertIsNotNone(movement)
    self.assertEqual(movement.reason, 'SALE_ALLOW_NO_STOCK')
    self.assertTrue(movement.metadata.get('allowed_without_stock'))
    self.assertEqual(movement.metadata.get('requested_qty'), '5')
    self.assertEqual(movement.metadata.get('available_stock'), '2.00')
    self.assertTrue(settings.allow_sell_without_stock)

  def test_cancel_sale_restores_negative_stock(self):
    business = self._create_business('Cancelar venta sin stock')
    self._configure_settings(business, allow_sell_without_stock=True)
    product = self._create_product(business, Decimal('1'))
    self._authenticate(business, role='manager')

    create_url = reverse('sales:sale-list')
    payload = {
      'items': [
        {'product_id': str(product.id), 'quantity': '4'},
      ]
    }

    create_response = self.client.post(create_url, payload, format='json')
    self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
    sale_id = create_response.data['id']
    stock = ProductStock.objects.get(product=product)
    self.assertEqual(stock.quantity, Decimal('-3.00'))

    cancel_url = reverse('sales:sale-cancel', args=[sale_id])
    cancel_response = self.client.post(cancel_url, {'reason': 'Error en carga'}, format='json')
    self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
    stock.refresh_from_db()
    self.assertEqual(stock.quantity, Decimal('1.00'))

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
