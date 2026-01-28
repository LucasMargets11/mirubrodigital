from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.cash.models import CashRegister, CashSession, Payment
from apps.cash.services import compute_session_totals
from apps.sales.models import Sale, SaleItem


class RestaurantReportsAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='resto-report-user',
            email='resto-report@example.com',
            password='demo1234',
        )
        self.business = self._create_business('Restaurante Reportes')
        self.business.default_service = 'restaurante'
        self.business.save(update_fields=['default_service'])
        self._authenticate(self.business, role='manager')

    def _create_business(self, name: str) -> Business:
        business = Business.objects.create(name=name, default_service='restaurante')
        Subscription.objects.create(business=business, plan='plus', status='active')
        return business

    def _authenticate(self, business: Business, role: str = 'manager'):
        Membership.objects.get_or_create(user=self.user, business=business, defaults={'role': role})
        membership = Membership.objects.get(user=self.user, business=business)
        membership.role = role
        membership.save(update_fields=['role'])
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)

    def _create_sale(
        self,
        business: Business,
        *,
        total: Decimal,
        created_at,
        items: list[dict] | None = None,
    ) -> Sale:
        number = Sale.objects.filter(business=business).count() + 1
        sale = Sale.objects.create(
            business=business,
            number=number,
            status=Sale.Status.COMPLETED,
            payment_method=Sale.PaymentMethod.CASH,
            subtotal=total,
            discount=Decimal('0.00'),
            total=total,
        )
        if items:
            subtotal = Decimal('0.00')
            for item in items:
                quantity = Decimal(item['quantity'])
                unit_price = Decimal(item['unit_price'])
                line_total = Decimal(item.get('line_total') or quantity * unit_price)
                subtotal += line_total
                SaleItem.objects.create(
                    sale=sale,
                    product=None,
                    product_name_snapshot=item['name'],
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            sale.subtotal = subtotal
            sale.total = subtotal
            sale.save(update_fields=['subtotal', 'total'])
        else:
            SaleItem.objects.create(
                sale=sale,
                product=None,
                product_name_snapshot='Producto',
                quantity=Decimal('1.00'),
                unit_price=total,
                line_total=total,
            )
        Sale.objects.filter(pk=sale.pk).update(created_at=created_at, updated_at=created_at)
        sale.refresh_from_db()
        return sale

    def _create_session(self, business: Business) -> CashSession:
        register = CashRegister.objects.create(business=business, name='Caja Principal')
        return CashSession.objects.create(
            business=business,
            register=register,
            opened_by=self.user,
            opening_cash_amount=Decimal('300.00'),
        )

    def _close_session(self, session: CashSession, *, difference: Decimal = Decimal('0.00')) -> CashSession:
        totals = compute_session_totals(session)
        session.expected_cash_total = totals['cash_expected_total']
        session.closing_cash_counted = (totals['cash_expected_total'] or Decimal('0.00')) + difference
        session.difference_amount = difference
        session.status = CashSession.Status.CLOSED
        session.closed_at = timezone.now()
        session.save(
            update_fields=['expected_cash_total', 'closing_cash_counted', 'difference_amount', 'status', 'closed_at']
        )
        return session

    def test_summary_requires_permission(self):
        self._authenticate(self.business, role='salon')

        response = self.client.get('/api/v1/restaurant/reports/summary/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_summary_returns_kpis_and_compare(self):
        now = timezone.now()
        session = self._create_session(self.business)
        sale = self._create_sale(
            self.business,
            total=Decimal('480.00'),
            created_at=now - timedelta(days=2),
            items=[{'name': 'Menu Ejecutivo', 'quantity': Decimal('2'), 'unit_price': Decimal('240.00')}],
        )
        Payment.objects.create(
            business=self.business,
            sale=sale,
            session=session,
            method=Payment.Method.CASH,
            amount=sale.total,
        )
        self._close_session(session, difference=Decimal('5.00'))

        params = {
            'date_from': (now.date() - timedelta(days=3)).isoformat(),
            'date_to': now.date().isoformat(),
            'compare': '1',
        }
        response = self.client.get('/api/v1/restaurant/reports/summary/', params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data['kpis']['sales_count'], 1)
        self.assertEqual(data['kpis']['cash_sessions_closed'], 1)
        self.assertEqual(data['kpis']['revenue_total'], '480.00')
        self.assertEqual(data['kpis']['cash_diff_total'], '5.00')
        self.assertIn('compare', data)
        self.assertEqual(data['payments'][0]['method'], Payment.Method.CASH)

    def test_products_endpoint_returns_top_and_bottom(self):
        now = timezone.now()
        self._create_sale(
            self.business,
            total=Decimal('0'),
            created_at=now - timedelta(days=1),
            items=[
                {'name': 'Pizza Margarita', 'quantity': Decimal('5'), 'unit_price': Decimal('1000.00')},
                {'name': 'Empanada', 'quantity': Decimal('2'), 'unit_price': Decimal('400.00')},
            ],
        )
        self._create_sale(
            self.business,
            total=Decimal('0'),
            created_at=now - timedelta(days=1),
            items=[{'name': 'Flan Casero', 'quantity': Decimal('1'), 'unit_price': Decimal('800.00')}],
        )

        params = {
            'date_from': (now.date() - timedelta(days=3)).isoformat(),
            'date_to': now.date().isoformat(),
        }
        response = self.client.get('/api/v1/restaurant/reports/products/', params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertTrue(any(row['name'] == 'Pizza Margarita' for row in data['top']))
        self.assertTrue(any(row['name'] == 'Flan Casero' for row in data['bottom']))

    def test_cash_sessions_endpoint_only_returns_closed(self):
        now = timezone.now()
        open_session = self._create_session(self.business)
        closed_session = self._close_session(self._create_session(self.business))
        params = {
            'date_from': (now.date() - timedelta(days=1)).isoformat(),
            'date_to': (now.date() + timedelta(days=1)).isoformat(),
        }

        response = self.client.get('/api/v1/restaurant/reports/cash-sessions/', params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row['id'] for row in response.data['results']]
        self.assertIn(str(closed_session.id), ids)
        self.assertNotIn(str(open_session.id), ids)
