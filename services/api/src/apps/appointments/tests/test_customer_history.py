"""Historial de Turnos del Customer (Turnos CUSTOMER 03).

`GET /api/v1/customers/{id}/appointments/?scope=upcoming|history|all`:
feed paginado derivado de `Appointment.customer` (sin tabla de eventos).
Cubre: partición próximos/historial, estados visibles en el historial, orden,
paginación, aislamiento entre tenants, permisos y la reserva pública repetida
del mismo teléfono reutilizando el mismo Customer.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer

from ..models import Appointment, AppointmentPayment, AppointmentSchedule, AppointmentService
from .test_customer_core_access import LIST_URL, S, TurnosAgendaMixin, _gestion_business, _login, _turnos_business


def _history_url(customer, scope=None, **params):
    query = {'scope': scope, **params} if scope else params
    qs = '&'.join(f'{k}={v}' for k, v in query.items())
    return f'{LIST_URL}{customer.pk}/appointments/' + (f'?{qs}' if qs else '')


class CustomerHistoryMixin(TurnosAgendaMixin):

    def setUp(self):
        self.biz = _turnos_business(slug='turnos-historial')
        self.service, self.pro = self._agenda(self.biz)
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550001')
        self.now = dj_timezone.now()

    def _days(self, n, hour=0):
        return self.now + dt.timedelta(days=n, hours=hour)

    def _get(self, scope=None, **params):
        resp = self.client.get(_history_url(self.customer, scope, **params))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data

    def _ids(self, scope=None, **params):
        return [row['id'] for row in self._get(scope, **params)['results']]


class CustomerHistoryContentTests(CustomerHistoryMixin, APITestCase):

    def setUp(self):
        super().setUp()
        _login(self.client, self.biz, 'owner')

    def test_single_appointment_returns_one_event_with_snapshots(self):
        appt = self._appt(self.biz, self.service, self.customer, self._days(-3), status_=S.COMPLETED, pro=self.pro)
        # El snapshot manda: renombrar el servicio no cambia el historial.
        self.service.name = 'Corte renombrado'
        self.service.save(update_fields=['name'])

        data = self._get('history')
        self.assertEqual(data['count'], 1)
        row = data['results'][0]
        self.assertEqual(row['type'], 'appointment')
        self.assertEqual(row['id'], str(appt.pk))
        self.assertEqual(row['occurred_at'], row['start_at'])
        self.assertEqual(row['service_name'], 'Corte')
        self.assertEqual(row['service_price'], '1000.00')
        self.assertEqual(row['professional_id'], str(self.pro.pk))
        self.assertEqual(row['professional_name'], 'Lu')
        self.assertEqual(row['status'], S.COMPLETED)
        self.assertEqual(row['status_display'], 'Completado')
        self.assertEqual(row['source'], 'manual')
        self.assertEqual(row['customer_name'], 'Ana')
        self.assertIsNone(row['payment_summary'])
        self.assertIn('created_at', row)
        self.assertNotIn('customer_phone', row)
        self.assertEqual(self._ids('upcoming'), [])

    def test_cancelled_no_show_completed_and_expired_appear_in_history(self):
        completed = self._appt(self.biz, self.service, self.customer, self._days(-10), status_=S.COMPLETED)
        no_show = self._appt(self.biz, self.service, self.customer, self._days(-8), status_=S.NO_SHOW)
        cancelled = self._appt(self.biz, self.service, self.customer, self._days(-6), status_=S.CANCELLED)
        past_confirmed = self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.CONFIRMED)
        # Futuros que NO son próximos: cancelado, vencido y hold vencido.
        future_cancelled = self._appt(self.biz, self.service, self.customer, self._days(2), status_=S.CANCELLED)
        expired = self._appt(self.biz, self.service, self.customer, self._days(3), status_=S.EXPIRED)
        stale_hold = self._appt(self.biz, self.service, self.customer, self._days(4), status_=S.PENDING_PAYMENT,
                                expires_at=self.now - dt.timedelta(minutes=1))
        upcoming = self._appt(self.biz, self.service, self.customer, self._days(5), status_=S.CONFIRMED)

        history = {row['id']: row['status'] for row in self._get('history')['results']}
        self.assertEqual(history, {
            str(completed.pk): S.COMPLETED,
            str(no_show.pk): S.NO_SHOW,
            str(cancelled.pk): S.CANCELLED,
            str(past_confirmed.pk): S.CONFIRMED,
            str(future_cancelled.pk): S.CANCELLED,
            str(expired.pk): S.EXPIRED,
            str(stale_hold.pk): S.EXPIRED,  # estado efectivo
        })
        self.assertEqual(self._ids('upcoming'), [str(upcoming.pk)])

    def test_upcoming_includes_live_hold_and_excludes_expired_and_cancelled(self):
        live_hold = self._appt(self.biz, self.service, self.customer, self._days(2), status_=S.PENDING_PAYMENT,
                               expires_at=self.now + dt.timedelta(minutes=10))
        later = self._appt(self.biz, self.service, self.customer, self._days(6), status_=S.CONFIRMED)
        self._appt(self.biz, self.service, self.customer, self._days(1), status_=S.EXPIRED)
        self._appt(self.biz, self.service, self.customer, self._days(1, 2), status_=S.CANCELLED)
        # Próximos: el más cercano primero.
        self.assertEqual(self._ids('upcoming'), [str(live_hold.pk), str(later.pk)])
        self.assertEqual(self._get('upcoming')['results'][0]['status'], S.PENDING_PAYMENT)

    def test_upcoming_matches_summary_count(self):
        self._appt(self.biz, self.service, self.customer, self._days(2), status_=S.CONFIRMED)
        self._appt(self.biz, self.service, self.customer, self._days(3), status_=S.CANCELLED)
        self._appt(self.biz, self.service, self.customer, self._days(-3), status_=S.COMPLETED)
        summary = self.client.get(f'{LIST_URL}{self.customer.pk}/').data['appointments_summary']
        self.assertEqual(self._get('upcoming')['count'], summary['upcoming'])
        self.assertEqual(self._get('upcoming')['count'] + self._get('history')['count'], self._get('all')['count'])

    def test_history_is_most_recent_first(self):
        oldest = self._appt(self.biz, self.service, self.customer, self._days(-30), status_=S.COMPLETED)
        newest = self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.NO_SHOW)
        middle = self._appt(self.biz, self.service, self.customer, self._days(-10), status_=S.CANCELLED)
        # CUSTOMER 04A.1: un cancelado se fecha por su cancelación (`updated_at`).
        Appointment.objects.filter(pk=middle.pk).update(updated_at=self._days(-10))
        self.assertEqual(self._ids('history'), [str(newest.pk), str(middle.pk), str(oldest.pk)])
        future = self._appt(self.biz, self.service, self.customer, self._days(3), status_=S.CONFIRMED)
        self.assertEqual(self._ids(), [str(future.pk), str(newest.pk), str(middle.pk), str(oldest.pk)])

    def test_pagination(self):
        created = [
            self._appt(self.biz, self.service, self.customer, self._days(-n), status_=S.COMPLETED)
            for n in range(1, 8)
        ]
        first = self._get('history', limit=3)
        self.assertEqual(first['count'], 7)
        self.assertEqual(len(first['results']), 3)
        self.assertIsNotNone(first['next'])
        self.assertIsNone(first['previous'])
        last = self._get('history', limit=3, offset=6)
        self.assertEqual([r['id'] for r in last['results']], [str(created[-1].pk)])
        self.assertIsNone(last['next'])
        # Default 25, máximo 100: nunca una lista infinita.
        self.assertEqual(len(self._get('history', limit=1000)['results']), 7)

    def test_payment_summary_is_exposed_safely(self):
        appt = self._appt(self.biz, self.service, self.customer, self._days(-2), status_=S.CONFIRMED)
        AppointmentPayment.objects.create(
            appointment=appt, business=self.biz, status=AppointmentPayment.Status.APPROVED,
            amount=Decimal('500.00'), currency='ARS', external_reference=f'APPOINTMENT_PAYMENT-{appt.pk}',
            provider_payment_id='MP-1', paid_at=self.now,
        )
        row = self._get('history')['results'][0]
        self.assertEqual(row['payment_summary']['status'], 'approved')
        self.assertEqual(row['payment_summary']['amount'], '500.00')
        self.assertNotIn('external_reference', row['payment_summary'])

    def test_other_customer_appointments_are_not_included(self):
        other = Customer.objects.create(business=self.biz, name='Beto', phone='1155550002')
        self._appt(self.biz, self.service, other, self._days(-2), status_=S.COMPLETED)
        self.assertEqual(self._get()['count'], 0)

    def test_invalid_scope_is_400(self):
        resp = self.client.get(_history_url(self.customer, 'futuro'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_query_count_is_constant(self):
        for n in range(1, 4):
            self._appt(self.biz, self.service, self.customer, self._days(-n), status_=S.COMPLETED, pro=self.pro)
        self._get('history')
        with CaptureQueriesContext(connection) as small:
            self._get('history')
        for n in range(4, 15):
            self._appt(self.biz, self.service, self.customer, self._days(-n), status_=S.NO_SHOW, pro=self.pro)
        with CaptureQueriesContext(connection) as big:
            self._get('history')
        self.assertEqual(len(small), len(big))


class CustomerHistoryAccessTests(CustomerHistoryMixin, APITestCase):

    def test_viewer_can_read(self):
        self._appt(self.biz, self.service, self.customer, self._days(-2), status_=S.COMPLETED)
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self._get('history')['count'], 1)

    def test_role_without_permissions_gets_403(self):
        _login(self.client, self.biz, 'cashier')  # sin permisos en Turnos
        resp = self.client.get(_history_url(self.customer, 'history'))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_gestion_business_without_turnos_gets_403(self):
        pro = _gestion_business('pro', 'gestion-pro-hist')
        customer = Customer.objects.create(business=pro, name='Cliente Gestión')
        _login(self.client, pro, 'owner')  # tiene view_customers, no view_appointments
        resp = self.client.get(_history_url(customer, 'history'))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['code'], 'appointments_access_required')

    def test_tenant_isolation(self):
        other = _turnos_business(slug='turnos-historial-b')
        other_service, _ = self._agenda(other)
        foreign = Customer.objects.create(business=other, name='Ajeno', phone='1155550009')
        self._appt(other, other_service, foreign, self._days(-1), status_=S.COMPLETED)
        # FK cruzada (dato corrupto): un turno de B apuntando al Customer de A.
        self._appt(other, other_service, self.customer, self._days(-2), status_=S.COMPLETED)

        _login(self.client, self.biz, 'owner')
        resp = self.client.get(_history_url(foreign, 'history'))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._get('all')['count'], 0)


class RepeatedPublicBookingHistoryTests(APITestCase):
    """Customer existente → nueva reserva pública → mismo Customer → ambos turnos en su historial."""

    def setUp(self):
        cache.clear()
        self.biz = _turnos_business(slug='turnos-repetido')
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=Decimal('1000'),
            deposit_type=AppointmentService.DepositType.NONE,
        )
        for weekday in range(7):
            AppointmentSchedule.objects.create(
                business=self.biz, professional=None, weekday=weekday, start_time='09:00', end_time='18:00',
            )

    def _book(self, day, hour, phone, name):
        resp = self.client.post(f'/api/v1/appointments/public/{self.biz.slug}/bookings/', {
            'service': str(self.service.id),
            'start': f'{day.isoformat()}T{hour}:00:00-03:00',
            'customer_name': name,
            'customer_phone': phone,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return Appointment.objects.get(public_token=resp.data['public_token'])

    def test_repeated_booking_reuses_customer_and_history_shows_both(self):
        first_day = (dj_timezone.now() + dt.timedelta(days=3)).date()
        first = self._book(first_day, 10, '+54 9 11 4444-3333', 'Lucía Web')
        self.assertIsNotNone(first.customer_id)

        # Mismo teléfono con otro formato y otro nombre tipeado.
        second = self._book(first_day + dt.timedelta(days=7), 11, '5491144443333', 'Lu')
        self.assertEqual(second.customer_id, first.customer_id)
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 1)
        customer = Customer.objects.get(pk=first.customer_id)
        self.assertEqual(customer.name, 'Lucía Web')  # el Customer existente no se muta

        _login(self.client, self.biz, 'owner')
        rows = self.client.get(_history_url(customer, 'upcoming')).data['results']
        self.assertEqual([r['id'] for r in rows], [str(first.pk), str(second.pk)])
        # Cada turno conserva su snapshot de nombre.
        self.assertEqual([r['customer_name'] for r in rows], ['Lucía Web', 'Lu'])
        self.assertEqual({r['source'] for r in rows}, {'public'})

        # Cuando el primero ya pasó y se completó, pasa al historial.
        Appointment.objects.filter(pk=first.pk).update(
            start_at=dj_timezone.now() - dt.timedelta(days=1),
            end_at=dj_timezone.now() - dt.timedelta(days=1) + dt.timedelta(minutes=30),
            status=S.COMPLETED,
        )
        history = self.client.get(_history_url(customer, 'history')).data['results']
        upcoming = self.client.get(_history_url(customer, 'upcoming')).data['results']
        self.assertEqual([r['id'] for r in history], [str(first.pk)])
        self.assertEqual([r['id'] for r in upcoming], [str(second.pk)])
