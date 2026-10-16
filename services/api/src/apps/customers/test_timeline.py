"""Timeline unificada del Customer (CUSTOMER 04A/04B).

`GET /api/v1/customers/{id}/timeline/?types=&limit=&offset=`: eventos
normalizados construidos al consultar desde Appointment / Sale / Quote /
Order comercial (sin tabla de eventos). Cubre contrato por tipo, mezcla y orden, módulos del
Business, RBAC por fuente, aislamiento entre tenants y paginación estable.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts import permissions as accounts_permissions
from apps.appointments.tests.test_customer_core_access import (
    LIST_URL, S, TurnosAgendaMixin, _gestion_business, _login, _turnos_business,
)
from apps.invoices.models import Invoice, InvoiceSeries
from apps.sales.models import Order, OrderItem, Quote, QuoteItem, Sale, SaleItem

from .models import Customer
from .timeline import build_customer_timeline


def _timeline_url(customer, **params):
    qs = '&'.join(f'{k}={v}' for k, v in params.items())
    return f'{LIST_URL}{customer.pk}/timeline/' + (f'?{qs}' if qs else '')


def _set_created_at(obj, when):
    type(obj).objects.filter(pk=obj.pk).update(created_at=when)
    obj.refresh_from_db()
    return obj


class TimelineMixin(TurnosAgendaMixin):

    def setUp(self):
        self.now = dj_timezone.now()

    def _days(self, n):
        return self.now + dt.timedelta(days=n)

    def _sale(self, biz, customer, when, *, total='150.00', status_=Sale.Status.COMPLETED):
        number = Sale.objects.filter(business=biz).count() + 1
        sale = Sale.objects.create(
            business=biz, customer=customer, number=number, status=status_,
            subtotal=Decimal(total), total=Decimal(total), payment_method=Sale.PaymentMethod.CARD,
        )
        SaleItem.objects.create(
            sale=sale, product_name_snapshot='Producto', quantity=Decimal('1'),
            unit_price=Decimal(total), line_total=Decimal(total),
        )
        return _set_created_at(sale, when)

    def _quote(self, biz, customer, when, *, total='80.00', status_=Quote.Status.SENT, deleted=False):
        number = f'P-{Quote.objects.filter(business=biz).count() + 1:06d}'
        quote = Quote.objects.create(
            business=biz, customer=customer, number=number, status=status_, total=Decimal(total),
            customer_name=customer.name, is_deleted=deleted,
        )
        QuoteItem.objects.create(
            quote=quote, name_snapshot='Item', quantity=Decimal('1'), unit_price=Decimal(total),
            total_line=Decimal(total),
        )
        return _set_created_at(quote, when)

    def _order(self, biz, customer, when, *, total='320.00', status_=Order.Status.CONFIRMED, items=2, order_date=None):
        """Pedido creado en `when`; `order_date` = su día local salvo que se indique otra (editada)."""
        number = f'O-{Order.objects.filter(business=biz).count() + 1:06d}'
        local_day = when.astimezone(ZoneInfo(biz.timezone)).date()
        order = Order.objects.create(
            business=biz, customer=customer, number=number, status=status_, total=Decimal(total),
            subtotal=Decimal(total), pending_balance=Decimal(total), order_date=order_date or local_day,
        )
        for _ in range(items):
            OrderItem.objects.create(
                order=order, name_snapshot='Item', unit_price=Decimal('1'), quantity=Decimal('1'),
                subtotal=Decimal('1'),
            )
        return _set_created_at(order, when)

    def _get(self, customer, **params):
        resp = self.client.get(_timeline_url(customer, **params))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, getattr(resp, 'data', resp))
        return resp.data

    def _keys(self, data):
        return [(row['type'], row['source_id']) for row in data['results']]


def _without_permission(*codes):
    """`permissions_for_service` real (con overrides del Business) y `codes` apagados."""
    real = accounts_permissions.permissions_for_service

    def fake(service, role, business=None):
        perms = dict(real(service, role, business))
        for code in codes:
            perms[code] = False
        return perms

    return mock.patch.object(accounts_permissions, 'permissions_for_service', side_effect=fake)


# ── Turnos-only ──────────────────────────────────────────────────────────────

class TurnosTimelineTests(TimelineMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.biz = _turnos_business(slug='timeline-turnos')
        self.service, self.pro = self._agenda(self.biz)
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550101')
        _login(self.client, self.biz, 'owner')

    def test_appointment_event_contract(self):
        appt = self._appt(self.biz, self.service, self.customer, self._days(-3), status_=S.COMPLETED, pro=self.pro)
        data = self._get(self.customer)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['types'], ['appointment'])
        event = data['results'][0]
        self.assertEqual(event['type'], 'appointment')
        self.assertEqual(event['source_id'], str(appt.pk))
        self.assertEqual(event['id'], f'appointment:{appt.pk}')
        self.assertEqual(event['occurred_at'], appt.start_at.isoformat())
        self.assertEqual(event['title'], 'Corte')
        self.assertEqual(event['subtitle'], 'Lu')
        self.assertEqual(event['status'], 'completed')
        self.assertEqual(event['amount'], '1000.00')
        local_day = appt.start_at.astimezone(dt.timezone(dt.timedelta(hours=-3))).date().isoformat()
        self.assertEqual(event['href'], f'/app/turnos/turnos?date={local_day}&appointment={appt.pk}')
        self.assertEqual(event['metadata']['service_name'], 'Corte')
        self.assertIn('payment_summary', event['metadata'])

    def test_keeps_cancelled_and_no_show_but_excludes_upcoming(self):
        cancelled = self._appt(self.biz, self.service, self.customer, self._days(-5), status_=S.CANCELLED)
        type(cancelled).objects.filter(pk=cancelled.pk).update(updated_at=self._days(-5))  # fecha de cancelación
        no_show = self._appt(self.biz, self.service, self.customer, self._days(-4), status_=S.NO_SHOW)
        self._appt(self.biz, self.service, self.customer, self._days(2), status_=S.CONFIRMED)  # próximo
        data = self._get(self.customer)
        self.assertEqual(self._keys(data), [('appointment', str(no_show.pk)), ('appointment', str(cancelled.pk))])

    def test_turnos_only_never_returns_sales_quotes_or_orders(self):
        # Datos comerciales existentes (p.ej. de un plan anterior) no se filtran.
        self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.COMPLETED)
        self._sale(self.biz, self.customer, self._days(-2))
        self._quote(self.biz, self.customer, self._days(-2))
        self._order(self.biz, self.customer, self._days(-2))
        data = self._get(self.customer)
        self.assertEqual(data['types'], ['appointment'])
        self.assertEqual({row['type'] for row in data['results']}, {'appointment'})
        self.assertEqual(data['count'], 1)

    def test_requesting_only_commercial_types_is_403(self):
        resp = self.client.get(_timeline_url(self.customer, types='sale,quote,order'))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['code'], 'timeline_access_required')

    def test_without_view_appointments_is_403(self):
        with _without_permission('view_appointments'):
            resp = self.client.get(_timeline_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['code'], 'timeline_access_required')

    def test_viewer_can_read(self):
        self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.COMPLETED)
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self._get(self.customer)['count'], 1)

    def test_cross_tenant_customer_is_404_and_corrupt_fk_not_leaked(self):
        other = _turnos_business(slug='timeline-turnos-b')
        other_service, _ = self._agenda(other)
        foreign = Customer.objects.create(business=other, name='Ajeno', phone='1155550199')
        self._appt(other, other_service, foreign, self._days(-1), status_=S.COMPLETED)
        # FK cruzada (dato corrupto): turno de B apuntando al Customer de A.
        self._appt(other, other_service, self.customer, self._days(-2), status_=S.COMPLETED)

        resp = self.client.get(_timeline_url(foreign))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._get(self.customer)['count'], 0)


# ── Gestión-only ─────────────────────────────────────────────────────────────

class GestionTimelineTests(TimelineMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.biz = _gestion_business('pro', 'timeline-gestion')
        self.customer = Customer.objects.create(business=self.biz, name='Bruno')
        _login(self.client, self.biz, 'owner')

    def test_sale_event_contract(self):
        sale = self._sale(self.biz, self.customer, self._days(-1), total='250.50')
        data = self._get(self.customer)
        self.assertEqual(data['types'], ['sale', 'quote', 'order'])
        event = data['results'][0]
        self.assertEqual(event['type'], 'sale')
        self.assertEqual(event['source_id'], str(sale.pk))
        self.assertEqual(event['occurred_at'], sale.created_at.isoformat())
        self.assertEqual(event['title'], f'Venta #{sale.number}')
        self.assertEqual(event['status'], 'completed')
        self.assertEqual(event['status_display'], 'Completada')
        self.assertEqual(event['amount'], '250.50')
        self.assertIsNone(event['currency'])
        self.assertEqual(event['href'], f'/app/gestion/ventas/{sale.pk}')
        self.assertEqual(event['metadata']['items_count'], 1)
        self.assertEqual(event['metadata']['payment_method'], 'card')
        self.assertIsNone(event['metadata']['invoice'])

    def test_quote_event_contract_and_deleted_excluded(self):
        quote = self._quote(self.biz, self.customer, self._days(-2), status_=Quote.Status.ACCEPTED)
        self._quote(self.biz, self.customer, self._days(-1), deleted=True)
        data = self._get(self.customer)
        self.assertEqual(data['count'], 1)
        event = data['results'][0]
        self.assertEqual(event['type'], 'quote')
        self.assertEqual(event['source_id'], str(quote.pk))
        self.assertEqual(event['title'], f'Presupuesto {quote.number}')
        self.assertEqual(event['status'], 'accepted')
        self.assertEqual(event['amount'], '80.00')
        self.assertEqual(event['currency'], 'ARS')
        self.assertEqual(event['href'], f'/app/gestion/ventas/presupuestos/{quote.pk}')
        self.assertEqual(event['metadata']['items_count'], 1)

    def test_gestion_only_never_returns_appointments(self):
        self._sale(self.biz, self.customer, self._days(-1))
        data = self._get(self.customer)
        self.assertNotIn('appointment', data['types'])
        self.assertEqual({row['type'] for row in data['results']}, {'sale'})
        resp = self.client.get(_timeline_url(self.customer, types='appointment'))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_mixed_sales_and_quotes_ordered_by_occurred_at(self):
        s1 = self._sale(self.biz, self.customer, self._days(-10))
        q1 = self._quote(self.biz, self.customer, self._days(-5))
        s2 = self._sale(self.biz, self.customer, self._days(-1))
        data = self._get(self.customer)
        self.assertEqual(self._keys(data), [('sale', str(s2.pk)), ('quote', str(q1.pk)), ('sale', str(s1.pk))])

    def test_cancelled_sale_keeps_original_date(self):
        sale = self._sale(self.biz, self.customer, self._days(-3), status_=Sale.Status.CANCELLED)
        event = self._get(self.customer)['results'][0]
        self.assertEqual(event['status'], 'cancelled')
        self.assertEqual(event['occurred_at'], sale.created_at.isoformat())

    def test_without_view_sales_excludes_sales(self):
        self._sale(self.biz, self.customer, self._days(-1))
        quote = self._quote(self.biz, self.customer, self._days(-2))
        with _without_permission('view_sales'):
            data = self._get(self.customer)
        self.assertEqual(data['types'], ['quote', 'order'])
        self.assertEqual(self._keys(data), [('quote', str(quote.pk))])

    def test_without_view_quotes_excludes_quotes(self):
        sale = self._sale(self.biz, self.customer, self._days(-1))
        self._quote(self.biz, self.customer, self._days(-2))
        with _without_permission('view_quotes'):
            data = self._get(self.customer)
        self.assertEqual(data['types'], ['sale', 'order'])
        self.assertEqual(self._keys(data), [('sale', str(sale.pk))])

    def test_without_any_source_permission_is_403(self):
        with _without_permission('view_sales', 'view_quotes', 'view_orders'):
            resp = self.client.get(_timeline_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['code'], 'timeline_access_required')

    def test_types_filter(self):
        self._sale(self.biz, self.customer, self._days(-1))
        quote = self._quote(self.biz, self.customer, self._days(-2))
        data = self._get(self.customer, types='quote')
        self.assertEqual(data['types'], ['quote'])
        self.assertEqual(self._keys(data), [('quote', str(quote.pk))])
        self.assertEqual(self.client.get(_timeline_url(self.customer, types='invoice')).status_code, 400)

    def test_other_customer_and_cross_tenant(self):
        other_customer = Customer.objects.create(business=self.biz, name='Otro')
        self._sale(self.biz, other_customer, self._days(-1))
        other_biz = _gestion_business('pro', 'timeline-gestion-b')
        foreign = Customer.objects.create(business=other_biz, name='Ajeno')
        self._sale(other_biz, foreign, self._days(-1))
        # FK cruzada (dato corrupto): venta de B apuntando al Customer de A.
        self._sale(other_biz, self.customer, self._days(-2))

        self.assertEqual(self._get(self.customer)['count'], 0)
        self.assertEqual(self.client.get(_timeline_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_is_stable_and_complete(self):
        expected = []
        same_instant = self._days(-3)
        for i in range(4):
            expected.append(('sale', str(self._sale(self.biz, self.customer, self._days(-i - 1)).pk)))
        for _ in range(3):  # empates de fecha: desempate determinista
            expected.append(('quote', str(self._quote(self.biz, self.customer, same_instant).pk)))
        full = self._keys(self._get(self.customer, limit=100))
        self.assertEqual(len(full), 7)
        self.assertEqual(sorted(full), sorted(expected))

        pages = []
        offset = 0
        while True:
            data = self._get(self.customer, limit=3, offset=offset)
            self.assertEqual(data['count'], 7)
            if not data['results']:
                break
            pages.extend(self._keys(data))
            offset += 3
        self.assertEqual(pages, full)
        self.assertEqual(self._keys(self._get(self.customer, limit=100)), full)  # repetible

    def test_empty_timeline(self):
        data = self._get(self.customer)
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])


# ── Business con Turnos + Gestión ────────────────────────────────────────────

class MixedTimelineTests(TimelineMixin, APITestCase):
    """Hoy un request resuelve permisos de UN servicio activo; el gate de Turnos
    se fuerza para simular un Business con ambos módulos y el rol habilitado."""

    def setUp(self):
        super().setUp()
        self.biz = _gestion_business('pro', 'timeline-mixto')
        self.biz.timezone = 'America/Argentina/Buenos_Aires'
        self.biz.save(update_fields=['timezone'])
        self.service, self.pro = self._agenda(self.biz)
        self.customer = Customer.objects.create(business=self.biz, name='Caro', phone='1155550301')
        _login(self.client, self.biz, 'owner')

    def _seed(self):
        appt = self._appt(self.biz, self.service, self.customer, self._days(-2), status_=S.COMPLETED, pro=self.pro)
        sale = self._sale(self.biz, self.customer, self._days(-1))
        quote = self._quote(self.biz, self.customer, self._days(-3))
        return appt, sale, quote

    def test_all_three_types_mixed_and_ordered(self):
        appt, sale, quote = self._seed()
        with mock.patch('apps.customers.views._includes_appointments_summary', return_value=True):
            data = self._get(self.customer)
        self.assertEqual(data['types'], ['appointment', 'sale', 'quote', 'order'])
        self.assertEqual(data['count'], 3)
        self.assertEqual(
            self._keys(data),
            [('sale', str(sale.pk)), ('appointment', str(appt.pk)), ('quote', str(quote.pk))],
        )

    def test_without_turnos_gate_only_commercial(self):
        self._seed()
        data = self._get(self.customer)
        self.assertEqual(data['types'], ['sale', 'quote', 'order'])
        self.assertEqual({row['type'] for row in data['results']}, {'sale', 'quote'})

    def test_service_merge_and_pagination_window(self):
        appt, sale, quote = self._seed()
        types = ['appointment', 'sale', 'quote']
        count, page1 = build_customer_timeline(self.customer, types, offset=0, limit=2, now=dj_timezone.now())
        _, page2 = build_customer_timeline(self.customer, types, offset=2, limit=2, now=dj_timezone.now())
        self.assertEqual(count, 3)
        self.assertEqual([e['source_id'] for e in page1 + page2], [str(sale.pk), str(appt.pk), str(quote.pk)])


# ── CUSTOMER 04A.1: occurred_at semántico de los turnos ─────────────────────

class AppointmentOccurredAtTests(TimelineMixin, APITestCase):
    """Cancelados/vencidos se fechan cuando ocurrió la cancelación/vencimiento,
    no por su `start_at` (que puede ser futuro). Misma regla en el historial
    de Turnos (CUSTOMER 03) y en la timeline."""

    def setUp(self):
        super().setUp()
        self.biz = _gestion_business('pro', 'timeline-occurred')
        self.service, self.pro = self._agenda(self.biz)
        self.customer = Customer.objects.create(business=self.biz, name='Dani', phone='1155550401')
        _login(self.client, self.biz, 'owner')
        # Business con Turnos + Gestión (ver MixedTimelineTests).
        patcher = mock.patch('apps.customers.views._includes_appointments_summary', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _hours(self, n):
        return self.now + dt.timedelta(hours=n)

    def _touch(self, appt, updated_at):
        type(appt).objects.filter(pk=appt.pk).update(updated_at=updated_at)
        appt.refresh_from_db()
        return appt

    def _event(self, appt, **params):
        rows = [r for r in self._get(self.customer, **params)['results'] if r['source_id'] == str(appt.pk)]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_completed_past_uses_start_at(self):
        appt = self._appt(self.biz, self.service, self.customer, self._days(-3), status_=S.COMPLETED)
        self._touch(appt, self._days(-1))  # marcado después: no mueve la fecha
        self.assertEqual(self._event(appt)['occurred_at'], appt.start_at.isoformat())

    def test_no_show_uses_start_at(self):
        appt = self._appt(self.biz, self.service, self.customer, self._days(-2), status_=S.NO_SHOW)
        self._touch(appt, self._days(-1))
        self.assertEqual(self._event(appt)['occurred_at'], appt.start_at.isoformat())

    def test_confirmed_historic_uses_start_at(self):
        appt = self._appt(self.biz, self.service, self.customer, self._days(-4), status_=S.CONFIRMED)
        self._touch(appt, self._days(-10))  # creado antes: tampoco mueve la fecha
        event = self._event(appt)
        self.assertEqual(event['occurred_at'], appt.start_at.isoformat())
        self.assertEqual(event['status'], 'confirmed')

    def test_future_cancelled_is_dated_at_cancellation_and_mixed_order(self):
        cancelled = self._appt(self.biz, self.service, self.customer, self._days(18), status_=S.CANCELLED)
        self._touch(cancelled, self._hours(-1))  # cancelado "hoy", turno de dentro de 18 días
        sale = self._sale(self.biz, self.customer, self._days(-1))
        quote = self._quote(self.biz, self.customer, self._days(-4))
        older = self._appt(self.biz, self.service, self.customer, self._days(-2), status_=S.COMPLETED)

        data = self._get(self.customer)
        self.assertEqual(
            self._keys(data),
            [
                ('appointment', str(cancelled.pk)),
                ('sale', str(sale.pk)),
                ('appointment', str(older.pk)),
                ('quote', str(quote.pk)),
            ],
        )
        event = data['results'][0]
        self.assertEqual(event['occurred_at'], cancelled.updated_at.isoformat())
        self.assertEqual(event['metadata']['start_at'], cancelled.start_at.isoformat())  # el turno no cambia
        self.assertEqual(event['status'], 'cancelled')

    def test_future_cancelled_long_ago_is_not_on_top(self):
        cancelled = self._appt(self.biz, self.service, self.customer, self._days(18), status_=S.CANCELLED)
        self._touch(cancelled, self._days(-5))
        sale = self._sale(self.biz, self.customer, self._days(-1))
        self.assertEqual(
            self._keys(self._get(self.customer)),
            [('sale', str(sale.pk)), ('appointment', str(cancelled.pk))],
        )

    def test_future_expired_uses_expires_at(self):
        expired = self._appt(
            self.biz, self.service, self.customer, self._days(10), status_=S.EXPIRED, expires_at=self._hours(-5),
        )
        self._touch(expired, self._hours(-1))  # materializado más tarde por el Beat
        sale = self._sale(self.biz, self.customer, self._hours(-3))
        data = self._get(self.customer)
        self.assertEqual(self._keys(data), [('sale', str(sale.pk)), ('appointment', str(expired.pk))])
        self.assertEqual(data['results'][1]['occurred_at'], expired.expires_at.isoformat())

    def test_pending_payment_with_lapsed_hold_uses_expires_at(self):
        hold = self._appt(
            self.biz, self.service, self.customer, self._days(7), status_=S.PENDING_PAYMENT, expires_at=self._hours(-2),
        )
        event = self._event(hold)
        self.assertEqual(event['status'], 'expired')
        self.assertEqual(event['occurred_at'], hold.expires_at.isoformat())

    def test_upcoming_unchanged(self):
        upcoming = self._appt(self.biz, self.service, self.customer, self._days(3), status_=S.CONFIRMED)
        hold = self._appt(
            self.biz, self.service, self.customer, self._days(5), status_=S.PENDING_PAYMENT, expires_at=self._hours(2),
        )
        past = self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.COMPLETED)
        # La timeline no incluye próximos.
        self.assertEqual(self._keys(self._get(self.customer)), [('appointment', str(past.pk))])
        # El scope `upcoming` de CUSTOMER 03 sigue igual: ocupantes futuros, el más cercano primero.
        resp = self.client.get(f'{LIST_URL}{self.customer.pk}/appointments/?scope=upcoming')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual([r['id'] for r in resp.data['results']], [str(upcoming.pk), str(hold.pk)])
        self.assertEqual(resp.data['results'][0]['occurred_at'], upcoming.start_at.isoformat())

    def test_appointments_history_shares_rule_and_order(self):
        cancelled = self._appt(self.biz, self.service, self.customer, self._days(18), status_=S.CANCELLED)
        self._touch(cancelled, self._days(-3))
        recent = self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.COMPLETED)
        resp = self.client.get(f'{LIST_URL}{self.customer.pk}/appointments/?scope=history')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        rows = resp.data['results']
        self.assertEqual([r['id'] for r in rows], [str(recent.pk), str(cancelled.pk)])
        self.assertEqual(rows[1]['occurred_at'], cancelled.updated_at.isoformat())
        timeline_rows = self._get(self.customer, types='appointment')['results']
        self.assertEqual([r['metadata'] for r in timeline_rows], rows)

    def test_sql_and_python_rule_agree(self):
        from apps.appointments.models import Appointment
        from apps.appointments.services.customer_history import appointment_occurred_at, occurred_at_expression

        cases = [
            (self._days(-2), S.COMPLETED, None),
            (self._days(-2), S.NO_SHOW, None),
            (self._days(-2), S.CONFIRMED, None),
            (self._days(9), S.CANCELLED, None),
            (self._days(9), S.EXPIRED, self._hours(-4)),
            (self._days(9), S.PENDING_PAYMENT, self._hours(-4)),
            (self._days(9), S.PENDING_PAYMENT, self._hours(4)),
        ]
        for start, status_, expires in cases:
            appt = self._appt(self.biz, self.service, self.customer, start, status_=status_, expires_at=expires)
            self._touch(appt, self._hours(-1))
        now = dj_timezone.now()
        rows = Appointment.objects.filter(customer=self.customer).annotate(occ=occurred_at_expression(now=now))
        self.assertEqual(rows.count(), len(cases))
        for appt in rows:
            self.assertEqual(appt.occ, appointment_occurred_at(appt, now=now), appt.status)

    def test_filters_and_pagination_keep_working(self):
        cancelled = self._appt(self.biz, self.service, self.customer, self._days(18), status_=S.CANCELLED)
        self._touch(cancelled, self._hours(-1))
        expired = self._appt(
            self.biz, self.service, self.customer, self._days(10), status_=S.EXPIRED, expires_at=self._days(-2),
        )
        done = self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.COMPLETED)
        self._sale(self.biz, self.customer, self._days(-3))

        only_appts = self._get(self.customer, types='appointment')
        self.assertEqual(only_appts['types'], ['appointment'])
        expected = [('appointment', str(cancelled.pk)), ('appointment', str(done.pk)), ('appointment', str(expired.pk))]
        self.assertEqual(self._keys(only_appts), expected)

        paged = []
        for offset in range(3):
            data = self._get(self.customer, types='appointment', limit=1, offset=offset)
            self.assertEqual(data['count'], 3)
            paged.extend(self._keys(data))
        self.assertEqual(paged, expected)
        full = self._get(self.customer, limit=2)
        self.assertEqual(full['count'], 4)
        self.assertEqual(self._keys(full), expected[:2])


# ── CUSTOMER 04B: Pedidos comerciales (sales.Order) ─────────────────────────

class OrderTimelineTests(TimelineMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.biz = _gestion_business('pro', 'timeline-orders')
        self.customer = Customer.objects.create(business=self.biz, name='Eva', phone='1155550501')
        self.tz = ZoneInfo(self.biz.timezone)
        _login(self.client, self.biz, 'owner')

    def _local_midnight(self, day):
        return dt.datetime.combine(day, dt.time.min, tzinfo=self.tz)

    def test_order_event_contract(self):
        order = self._order(self.biz, self.customer, self._days(-1), total='320.50', items=3)
        data = self._get(self.customer)
        self.assertEqual(data['types'], ['sale', 'quote', 'order'])
        self.assertEqual(data['count'], 1)
        event = data['results'][0]
        self.assertEqual(event['type'], 'order')
        self.assertEqual(event['id'], f'order:{order.pk}')
        self.assertEqual(event['source_id'], str(order.pk))
        self.assertEqual(event['title'], f'Pedido {order.number}')
        self.assertIsNone(event['subtitle'])
        self.assertEqual(event['status'], 'confirmed')
        self.assertEqual(event['status_display'], 'Confirmado')
        self.assertEqual(event['amount'], '320.50')
        self.assertIsNone(event['currency'])
        self.assertEqual(event['href'], f'/app/gestion/ventas/pedidos/{order.pk}')
        meta = event['metadata']
        self.assertEqual(meta['number'], order.number)
        self.assertEqual(meta['items_count'], 3)
        self.assertEqual(meta['order_date'], order.order_date.isoformat())
        self.assertIsNone(meta['estimated_delivery_date'])
        self.assertEqual(meta['payment_status'], 'pending')
        self.assertEqual(meta['payment_status_display'], 'Pendiente')
        self.assertEqual(meta['total_paid'], '0.00')
        self.assertEqual(meta['pending_balance'], '320.50')

    def test_occurred_at_is_created_instant_when_order_date_is_creation_day(self):
        order = self._order(self.biz, self.customer, self._days(-2))
        self.assertEqual(order.order_date, order.created_at.astimezone(self.tz).date())
        event = self._get(self.customer)['results'][0]
        self.assertEqual(dt.datetime.fromisoformat(event['occurred_at']), order.created_at)

    def test_occurred_at_follows_edited_order_date(self):
        business_day = (self._days(-6)).astimezone(self.tz).date()
        order = self._order(self.biz, self.customer, self._days(-1), order_date=business_day)
        event = self._get(self.customer)['results'][0]
        occurred = dt.datetime.fromisoformat(event['occurred_at'])
        self.assertEqual(occurred, self._local_midnight(business_day))
        self.assertEqual(occurred.astimezone(self.tz).date(), order.order_date)  # cae en el día del pedido

    def test_cancelled_order_is_included_with_status(self):
        order = self._order(self.biz, self.customer, self._days(-1), status_=Order.Status.CANCELLED)
        Order.objects.filter(pk=order.pk).update(deleted_at=self.now)  # como hace `cancel`
        event = self._get(self.customer)['results'][0]
        self.assertEqual(event['source_id'], str(order.pk))
        self.assertEqual(event['status'], 'cancelled')
        self.assertEqual(event['status_display'], 'Cancelado')

    def test_without_view_orders_excludes_orders(self):
        sale = self._sale(self.biz, self.customer, self._days(-2))
        self._order(self.biz, self.customer, self._days(-1))
        with _without_permission('view_orders'):
            data = self._get(self.customer)
            resp = self.client.get(_timeline_url(self.customer, types='order'))
        self.assertEqual(data['types'], ['sale', 'quote'])
        self.assertEqual(self._keys(data), [('sale', str(sale.pk))])
        self.assertEqual(data['count'], 1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_without_orders_module_excludes_orders(self):
        sale = self._sale(self.biz, self.customer, self._days(-2))
        self._order(self.biz, self.customer, self._days(-1))
        entitlements = {'gestion.customers', 'gestion.quotes'}
        with mock.patch('apps.customers.views._business_entitlements', return_value=entitlements):
            data = self._get(self.customer)
        self.assertEqual(data['types'], ['sale', 'quote'])
        self.assertEqual(self._keys(data), [('sale', str(sale.pk))])

    def test_only_orders_permission_still_sees_orders(self):
        order = self._order(self.biz, self.customer, self._days(-1))
        self._sale(self.biz, self.customer, self._days(-2))
        with _without_permission('view_sales', 'view_quotes'):
            data = self._get(self.customer)
        self.assertEqual(data['types'], ['order'])
        self.assertEqual(self._keys(data), [('order', str(order.pk))])

    def test_other_customer_and_cross_tenant(self):
        other_customer = Customer.objects.create(business=self.biz, name='Otro')
        self._order(self.biz, other_customer, self._days(-1))
        other_biz = _gestion_business('pro', 'timeline-orders-b')
        foreign = Customer.objects.create(business=other_biz, name='Ajeno')
        self._order(other_biz, foreign, self._days(-1))
        # FK cruzada (dato corrupto): pedido de B apuntando al Customer de A.
        self._order(other_biz, self.customer, self._days(-2))

        data = self._get(self.customer)
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])
        self.assertEqual(self.client.get(_timeline_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)

    def test_types_filter_order_and_combined(self):
        sale = self._sale(self.biz, self.customer, self._days(-3))
        quote = self._quote(self.biz, self.customer, self._days(-2))
        order = self._order(self.biz, self.customer, self._days(-1))

        only = self._get(self.customer, types='order')
        self.assertEqual(only['types'], ['order'])
        self.assertEqual(only['count'], 1)
        self.assertEqual(self._keys(only), [('order', str(order.pk))])

        combined = self._get(self.customer, types='order,sale')
        self.assertEqual(combined['types'], ['sale', 'order'])
        self.assertEqual(combined['count'], 2)
        self.assertEqual(self._keys(combined), [('order', str(order.pk)), ('sale', str(sale.pk))])
        self.assertNotIn(('quote', str(quote.pk)), self._keys(combined))

    def test_pagination_stable_with_orders_and_ties(self):
        tie_day = self._days(-4).astimezone(self.tz).date()
        expected = []
        for i in range(3):
            expected.append(('sale', str(self._sale(self.biz, self.customer, self._days(-i - 1)).pk)))
        for _ in range(3):  # misma `order_date` editada → mismo instante: desempate por pk
            expected.append(('order', str(self._order(self.biz, self.customer, self._days(-1), order_date=tie_day).pk)))
        expected.append(('quote', str(self._quote(self.biz, self.customer, self._local_midnight(tie_day)).pk)))
        full = self._keys(self._get(self.customer, limit=100))
        self.assertEqual(len(full), 7)
        self.assertEqual(sorted(full), sorted(expected))
        # Empate exacto pedido/presupuesto: el tipo desempata (order antes que quote).
        self.assertEqual(full[-1][0], 'quote')

        for size in (2, 3):
            pages = []
            offset = 0
            while True:
                data = self._get(self.customer, limit=size, offset=offset)
                self.assertEqual(data['count'], 7)
                if not data['results']:
                    break
                pages.extend(self._keys(data))
                offset += size
            self.assertEqual(pages, full)


class FourTypesTimelineTests(TimelineMixin, APITestCase):
    """Turnos + Ventas + Presupuestos + Pedidos en una sola timeline (gate de Turnos forzado)."""

    def setUp(self):
        super().setUp()
        self.biz = _gestion_business('pro', 'timeline-four')
        self.service, self.pro = self._agenda(self.biz)
        self.customer = Customer.objects.create(business=self.biz, name='Fede', phone='1155550601')
        _login(self.client, self.biz, 'owner')
        patcher = mock.patch('apps.customers.views._includes_appointments_summary', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_four_types_mixed_ordered_and_paginated(self):
        order = self._order(self.biz, self.customer, self._days(-1))
        appt = self._appt(self.biz, self.service, self.customer, self._days(-2), status_=S.COMPLETED, pro=self.pro)
        sale = self._sale(self.biz, self.customer, self._days(-3))
        quote = self._quote(self.biz, self.customer, self._days(-4))
        expected = [
            ('order', str(order.pk)), ('appointment', str(appt.pk)), ('sale', str(sale.pk)), ('quote', str(quote.pk)),
        ]
        data = self._get(self.customer)
        self.assertEqual(data['types'], ['appointment', 'sale', 'quote', 'order'])
        self.assertEqual(data['count'], 4)
        self.assertEqual(self._keys(data), expected)

        paged = []
        for offset in range(0, 4, 3):
            paged.extend(self._keys(self._get(self.customer, limit=3, offset=offset)))
        self.assertEqual(paged, expected)

        count, events = build_customer_timeline(
            self.customer, ['appointment', 'sale', 'quote', 'order'], offset=1, limit=2, now=dj_timezone.now(),
        )
        self.assertEqual(count, 4)
        self.assertEqual([(e['type'], e['source_id']) for e in events], expected[1:3])


class SaleInvoiceMetadataTests(TimelineMixin, APITestCase):
    """La factura de una venta (OneToOne) va en `metadata.invoice`, sin N+1."""

    def setUp(self):
        super().setUp()
        self.biz = _gestion_business('pro', 'timeline-invoice')
        self.customer = Customer.objects.create(business=self.biz, name='Gabi')
        self.series = InvoiceSeries.objects.create(business=self.biz, code='B', prefix='0001')
        _login(self.client, self.biz, 'owner')

    def _invoice(self, sale, number, status_=Invoice.Status.ISSUED):
        return Invoice.objects.create(
            business=self.biz, sale=sale, series=self.series, number=number,
            full_number=self.series.format_full_number(number), status=status_, total=sale.total,
        )

    def test_invoice_in_sale_metadata(self):
        invoiced = self._sale(self.biz, self.customer, self._days(-1))
        invoice = self._invoice(invoiced, 7, status_=Invoice.Status.VOIDED)
        plain = self._sale(self.biz, self.customer, self._days(-2))
        rows = {r['source_id']: r for r in self._get(self.customer, types='sale')['results']}
        self.assertEqual(rows[str(invoiced.pk)]['metadata']['invoice'], {
            'id': str(invoice.pk), 'full_number': invoice.full_number, 'status': 'voided', 'status_display': 'Anulada',
        })
        self.assertIsNone(rows[str(plain.pk)]['metadata']['invoice'])

    def test_no_n_plus_one(self):
        def run():
            with CaptureQueriesContext(connection) as ctx:
                build_customer_timeline(self.customer, ['sale', 'order'], offset=0, limit=20, now=dj_timezone.now())
            return len(ctx.captured_queries)

        sale = self._sale(self.biz, self.customer, self._days(-1))
        self._invoice(sale, 1)
        self._order(self.biz, self.customer, self._days(-1))
        baseline = run()
        for i in range(3):
            more = self._sale(self.biz, self.customer, self._days(-i - 2))
            self._invoice(more, i + 2)
            self._order(self.biz, self.customer, self._days(-i - 2))
        self.assertEqual(run(), baseline)
