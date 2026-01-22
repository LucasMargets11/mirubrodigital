from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.cash.models import CashMovement, CashRegister, CashSession, Payment
from apps.cash.services import compute_session_totals
from apps.catalog.models import Product
from apps.inventory.models import ProductStock
from apps.sales.models import Sale, SaleItem


class ReportsAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='reports-user',
      email='reports@example.com',
      password='pass1234',
    )
    self.business = self._create_business('Demo Reports')
    self._authenticate(self.business, role='manager')

  def _create_business(self, name: str) -> Business:
    business = Business.objects.create(name=name)
    Subscription.objects.create(business=business, plan='pro', status='active')
    return business

  def _authenticate(self, business: Business, role: str = 'manager'):
    Membership.objects.get_or_create(user=self.user, business=business, defaults={'role': role})
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)

  def _create_sale(
    self,
    business: Business,
    *,
    total: Decimal,
    created_at=None,
    payment_method: str = Sale.PaymentMethod.CASH,
    status: str = Sale.Status.COMPLETED,
    items: list[dict] | None = None,
  ) -> Sale:
    number = Sale.objects.filter(business=business).count() + 1
    subtotal = total
    if items:
      subtotal = Decimal('0')
      for item in items:
        quantity = Decimal(item['quantity'])
        unit_price = Decimal(item['unit_price'])
        line_total = item.get('line_total')
        if line_total is None:
          line_total = quantity * unit_price
        line_total = Decimal(line_total)
        subtotal += line_total
      total = subtotal
    sale = Sale.objects.create(
      business=business,
      number=number,
      status=status,
      payment_method=payment_method,
      subtotal=subtotal,
      discount=Decimal('0.00'),
      total=total,
    )
    if items:
      for item in items:
        SaleItem.objects.create(
          sale=sale,
          product=None,
          product_name_snapshot=item['name'],
          quantity=Decimal(item['quantity']),
          unit_price=Decimal(item['unit_price']),
          line_total=Decimal(item.get('line_total') or Decimal(item['quantity']) * Decimal(item['unit_price'])),
        )
    else:
      SaleItem.objects.create(
        sale=sale,
        product=None,
        product_name_snapshot='Producto Demo',
        quantity=Decimal('1.00'),
        unit_price=total,
        line_total=total,
      )
    if created_at:
      Sale.objects.filter(pk=sale.pk).update(created_at=created_at, updated_at=created_at)
      sale.refresh_from_db()
    return sale

  def _create_session(self, business: Business) -> CashSession:
    register = CashRegister.objects.create(business=business, name='Caja Test')
    session = CashSession.objects.create(
      business=business,
      register=register,
      opened_by=self.user,
      opening_cash_amount=Decimal('500.00'),
    )
    return session

  def _create_product_with_stock(
    self,
    *,
    business: Business | None = None,
    name: str,
    stock: Decimal,
    stock_min: Decimal = Decimal('0'),
  ) -> Product:
    target_business = business or self.business
    product = Product.objects.create(
      business=target_business,
      name=name,
      sku='',
      barcode='',
      price=Decimal('100.00'),
      cost=Decimal('40.00'),
      stock_min=stock_min,
    )
    ProductStock.objects.create(business=target_business, product=product, quantity=stock)
    return product

  def test_summary_returns_expected_fields(self):
    session = self._create_session(self.business)
    now = timezone.now()
    sale = self._create_sale(self.business, total=Decimal('500.00'), created_at=now - timedelta(days=1))
    Payment.objects.create(
      business=self.business,
      sale=sale,
      session=session,
      method=Payment.Method.CASH,
      amount=Decimal('300.00'),
    )
    Payment.objects.create(
      business=self.business,
      sale=sale,
      session=session,
      method=Payment.Method.CREDIT,
      amount=Decimal('200.00'),
    )
    date_from = (now.date() - timedelta(days=2)).isoformat()
    date_to = now.date().isoformat()

    response = self.client.get('/api/v1/reports/summary/', {'from': date_from, 'to': date_to})

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    data = response.data
    self.assertEqual(data['kpis']['sales_count'], 1)
    self.assertEqual(data['kpis']['gross_sales_total'], '500.00')
    self.assertEqual(len(data['series']), 1)
    self.assertTrue(any(row['method'] == Payment.Method.CASH for row in data['payments_breakdown']))

  def test_summary_is_scoped_to_current_business(self):
    other_business = self._create_business('Otra Sucursal')
    self._create_sale(other_business, total=Decimal('900.00'), created_at=timezone.now() - timedelta(days=1))
    now = timezone.now()
    self._create_sale(self.business, total=Decimal('120.00'), created_at=now - timedelta(days=2))

    response = self.client.get('/api/v1/reports/summary/', {'from': (now.date() - timedelta(days=3)).isoformat(), 'to': now.date().isoformat()})

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data['kpis']['sales_count'], 1)

  def test_sales_list_requires_permission(self):
    other_user = get_user_model().objects.create_user(username='cashier', email='cashier@example.com', password='demo1234')
    other_business = self._create_business('Sin permisos')
    Membership.objects.create(user=other_user, business=other_business, role='cashier')
    self.client.force_authenticate(other_user)
    self.client.cookies['bid'] = str(other_business.id)

    response = self.client.get('/api/v1/reports/sales/')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_cash_closure_detail_expected_breakdown(self):
    session = self._create_session(self.business)
    sale = self._create_sale(self.business, total=Decimal('400.00'))
    Payment.objects.create(
      business=self.business,
      sale=sale,
      session=session,
      method=Payment.Method.CASH,
      amount=Decimal('400.00'),
    )
    CashMovement.objects.create(
      business=self.business,
      session=session,
      movement_type=CashMovement.MovementType.IN,
      category=CashMovement.Category.DEPOSIT,
      method=Payment.Method.CASH,
      amount=Decimal('150.00'),
    )
    CashMovement.objects.create(
      business=self.business,
      session=session,
      movement_type=CashMovement.MovementType.OUT,
      category=CashMovement.Category.WITHDRAW,
      method=Payment.Method.CASH,
      amount=Decimal('50.00'),
    )
    totals = compute_session_totals(session)
    session.expected_cash_total = totals['cash_expected_total']
    session.closing_cash_counted = totals['cash_expected_total']
    session.difference_amount = Decimal('0.00')
    session.status = CashSession.Status.CLOSED
    session.closed_at = timezone.now()
    session.save(update_fields=['expected_cash_total', 'closing_cash_counted', 'difference_amount', 'status', 'closed_at'])

    response = self.client.get(f'/api/v1/reports/cash/closures/{session.id}/')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    breakdown = response.data['expected_breakdown']
    expected_value = (session.opening_cash_amount + Decimal('400.00') + Decimal('150.00') - Decimal('50.00')).quantize(Decimal('0.01'))
    self.assertEqual(breakdown['expected_cash'], f"{expected_value:.2f}")

  def test_products_report_requires_permission(self):
    membership = Membership.objects.get(user=self.user, business=self.business)
    membership.role = 'cashier'
    membership.save(update_fields=['role'])

    response = self.client.get('/api/v1/reports/products/')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_products_report_returns_rows(self):
    now = timezone.now()
    self._create_sale(
      self.business,
      total=Decimal('0'),
      created_at=now - timedelta(days=3),
      items=[
        {'name': 'Latte', 'quantity': Decimal('3'), 'unit_price': Decimal('500.00')},
      ],
    )
    self._create_sale(
      self.business,
      total=Decimal('0'),
      created_at=now - timedelta(days=2),
      items=[
        {'name': 'Medialuna', 'quantity': Decimal('1'), 'unit_price': Decimal('500.00')},
      ],
    )

    response = self.client.get('/api/v1/reports/products/', {'from': (now.date() - timedelta(days=5)).isoformat(), 'to': now.date().isoformat()})

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data['totals']['products_count'], 2)
    self.assertEqual(len(response.data['results']), 2)
    top_product = response.data['results'][0]
    self.assertEqual(top_product['name'], 'Latte')
    self.assertEqual(top_product['sales_count'], 1)
    self.assertEqual(top_product['quantity'], '3.00')
    self.assertEqual(top_product['share'], '75.00')

  def test_products_report_is_scoped_per_business(self):
    now = timezone.now()
    other_business = self._create_business('Otro demo')
    self._create_sale(
      other_business,
      total=Decimal('0'),
      created_at=now - timedelta(days=1),
      items=[{'name': 'Ajeno', 'quantity': Decimal('2'), 'unit_price': Decimal('100.00')}],
    )
    self._create_sale(
      self.business,
      total=Decimal('0'),
      created_at=now - timedelta(days=1),
      items=[{'name': 'Local', 'quantity': Decimal('2'), 'unit_price': Decimal('120.00')}],
    )

    response = self.client.get('/api/v1/reports/products/', {'from': (now.date() - timedelta(days=2)).isoformat(), 'to': now.date().isoformat()})

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data['totals']['products_count'], 1)
    self.assertEqual(response.data['results'][0]['name'], 'Local')

  def test_top_products_leaderboard_metric_toggle(self):
    now = timezone.now()
    self._create_sale(
      self.business,
      total=Decimal('0'),
      created_at=now - timedelta(days=1),
      items=[{'name': 'Clásico Crepe', 'quantity': Decimal('7'), 'unit_price': Decimal('100.00')}],
    )
    self._create_sale(
      self.business,
      total=Decimal('0'),
      created_at=now - timedelta(days=1),
      items=[{'name': 'Veggie Wrap', 'quantity': Decimal('15'), 'unit_price': Decimal('10.00')}],
    )
    other_business = self._create_business('Otra sucursal')
    self._create_sale(
      other_business,
      total=Decimal('0'),
      created_at=now - timedelta(days=1),
      items=[{'name': 'Ajena', 'quantity': Decimal('9'), 'unit_price': Decimal('50.00')}],
    )

    params = {'from': (now.date() - timedelta(days=2)).isoformat(), 'to': now.date().isoformat()}
    amount_response = self.client.get('/api/v1/reports/products/top/', {**params, 'metric': 'amount'})

    self.assertEqual(amount_response.status_code, status.HTTP_200_OK)
    self.assertEqual(amount_response.data['metric'], 'amount')
    self.assertEqual(amount_response.data['items'][0]['name'], 'Clásico Crepe')
    self.assertEqual(amount_response.data['items'][0]['share_pct'], '82.4')

    units_response = self.client.get('/api/v1/reports/products/top/', {**params, 'metric': 'units'})

    self.assertEqual(units_response.status_code, status.HTTP_200_OK)
    self.assertEqual(units_response.data['metric'], 'units')
    self.assertEqual(units_response.data['items'][0]['name'], 'Veggie Wrap')
    self.assertEqual(units_response.data['items'][0]['share_pct'], '68.2')

  def test_stock_alerts_requires_permission(self):
    membership = Membership.objects.get(user=self.user, business=self.business)
    membership.role = 'cashier'
    membership.save(update_fields=['role'])

    response = self.client.get('/api/v1/reports/stock/alerts/')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_stock_alerts_counts_and_items(self):
    self._create_product_with_stock(name='Yerba 500g', stock=Decimal('0'), stock_min=Decimal('3'))
    self._create_product_with_stock(name='Coca 500', stock=Decimal('2'), stock_min=Decimal('5'))
    self._create_product_with_stock(name='Snack mini', stock=Decimal('1'), stock_min=Decimal('0'))
    self._create_product_with_stock(name='Con stock', stock=Decimal('15'), stock_min=Decimal('4'))
    other_business = self._create_business('Otro negocio')
    self._create_product_with_stock(business=other_business, name='Ajeno', stock=Decimal('0'), stock_min=Decimal('4'))

    response = self.client.get('/api/v1/reports/stock/alerts/', {'limit': 5})

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    data = response.data
    expected_threshold = f"{settings.REPORTS_LOW_STOCK_THRESHOLD_DEFAULT.quantize(Decimal('0.01')):.2f}"
    self.assertEqual(data['low_stock_threshold_default'], expected_threshold)
    self.assertEqual(data['out_of_stock_count'], 1)
    self.assertEqual(data['low_stock_count'], 2)
    self.assertGreaterEqual(len(data['items']), 3)
    self.assertEqual(data['items'][0]['status'], 'OUT')
    snack_row = next(item for item in data['items'] if item['name'] == 'Snack mini')
    self.assertEqual(snack_row['status'], 'LOW')
    self.assertEqual(snack_row['threshold'], expected_threshold)