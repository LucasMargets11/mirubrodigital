"""Recordatorios internos del Customer (CUSTOMER 07A).

`/api/v1/customers/{id}/reminders/` (GET ?scope, POST) y
`/reminders/{reminder_id}/` (GET, PATCH; sin PUT/DELETE). Cubre contrato,
orden, completar/cancelar (estados finales), `is_overdue` derivado, zona del
Business, RBAC (lectura `view_customers`, escritura
`manage_customer_reminders` — owner/admin/manager), aislamiento entre
tenants, vínculo opcional con Appointment y `created_by` del request.
"""
from __future__ import annotations

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.rbac import permissions_for_service
from apps.appointments.tests.test_customer_core_access import (
    LIST_URL,
    TurnosAgendaMixin,
    _gestion_business,
    _login,
    _turnos_business,
)

from .models import Customer, CustomerReminder

BA = ZoneInfo('America/Argentina/Buenos_Aires')


def _reminders_url(customer, query=''):
    return f'{LIST_URL}{customer.pk}/reminders/{query}'


def _reminder_url(customer, reminder):
    reminder_id = reminder if isinstance(reminder, (str, uuid.UUID)) else reminder.pk
    return f'{LIST_URL}{customer.pk}/reminders/{reminder_id}/'


def _future(hours=24):
    return dj_timezone.now() + dt.timedelta(hours=hours)


class CustomerRemindersMixin(TurnosAgendaMixin):

    def _reminder(self, customer, title='Llamar', *, remind_at=None, status_=CustomerReminder.Status.PENDING, appointment=None):
        return CustomerReminder.objects.create(
            business=customer.business, customer=customer, title=title,
            remind_at=remind_at or _future(), status=status_, appointment=appointment,
            completed_at=dj_timezone.now() if status_ == CustomerReminder.Status.COMPLETED else None,
        )

    def _payload(self, **overrides):
        payload = {'title': 'Llamar mañana', 'remind_at': _future().isoformat()}
        payload.update(overrides)
        return payload


class TurnosCustomerRemindersTests(CustomerRemindersMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug='rem-turnos')
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550101')

    # ── Alta / contrato ──────────────────────────────────────────────────────

    def test_create_reminder_contract_and_created_by_from_request(self):
        user = _login(self.client, self.biz, 'owner')
        user.first_name, user.last_name = 'Lucía', 'Pérez'
        user.email = 'lucia@example.com'
        user.save()
        intruder = _login(self.client.__class__(), self.biz, 'manager')
        resp = self.client.post(
            _reminders_url(self.customer),
            self._payload(
                title='  Llamar mañana  ', description=' Confirmar seña ',
                created_by=str(intruder.pk), created_by_id=intruder.pk, business=str(uuid.uuid4()),
                completed_at=dj_timezone.now().isoformat(),
            ),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(set(resp.data), {
            'id', 'title', 'description', 'remind_at', 'status', 'status_display', 'is_overdue',
            'source', 'source_display', 'is_automatic', 'appointment_id', 'appointment_start_at', 'created_by', 'completed_at', 'notified_at', 'created_at', 'updated_at',
        })
        self.assertEqual(resp.data['title'], 'Llamar mañana')
        self.assertEqual(resp.data['description'], 'Confirmar seña')
        self.assertEqual(resp.data['status'], 'pending')
        self.assertEqual(resp.data['status_display'], 'Pendiente')
        self.assertEqual((resp.data['source'], resp.data['is_automatic']), ('manual', False))
        self.assertFalse(resp.data['is_overdue'])
        self.assertIsNone(resp.data['appointment_id'])
        self.assertIsNone(resp.data['appointment_start_at'])
        self.assertIsNone(resp.data['completed_at'])
        self.assertEqual(resp.data['created_by'], {'id': str(user.pk), 'name': 'Lucía Pérez'})
        self.assertNotIn('example.com', str(resp.data))
        reminder = CustomerReminder.objects.get(pk=resp.data['id'])
        self.assertEqual(reminder.created_by_id, user.pk)
        self.assertEqual(reminder.business_id, self.biz.pk)
        self.assertEqual(reminder.customer_id, self.customer.pk)
        self.assertIsNone(reminder.completed_at)
        self.assertTrue(dj_timezone.is_aware(reminder.remind_at))

    def test_create_cannot_start_closed(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), self._payload(status='completed'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', resp.data)
        self.assertFalse(CustomerReminder.objects.exists())

    def test_blank_title_rejected(self):
        _login(self.client, self.biz, 'owner')
        for title in ('', '   '):
            resp = self.client.post(_reminders_url(self.customer), self._payload(title=title), format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, title)
            self.assertIn('title', resp.data)
        resp = self.client.post(_reminders_url(self.customer), {'remind_at': _future().isoformat()}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', resp.data)
        self.assertFalse(CustomerReminder.objects.exists())

    def test_remind_at_required_and_lengths(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), {'title': 'Sin fecha'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('remind_at', resp.data)
        too_long = self._payload(title='x' * (CustomerReminder.TITLE_MAX_LENGTH + 1))
        self.assertEqual(self.client.post(_reminders_url(self.customer), too_long, format='json').status_code, status.HTTP_400_BAD_REQUEST)
        too_long = self._payload(description='x' * (CustomerReminder.DESCRIPTION_MAX_LENGTH + 1))
        self.assertEqual(self.client.post(_reminders_url(self.customer), too_long, format='json').status_code, status.HTTP_400_BAD_REQUEST)

    def test_past_remind_at_allowed_and_overdue(self):
        """Se puede registrar algo ya vencido ("tenía que llamar ayer"): queda pending + overdue."""
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), self._payload(remind_at=_future(-2).isoformat()), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['status'], 'pending')
        self.assertTrue(resp.data['is_overdue'])

    # ── Listado / orden / scopes ─────────────────────────────────────────────

    def test_list_pending_ordered_by_remind_at(self):
        _login(self.client, self.biz, 'owner')
        later = self._reminder(self.customer, 'Después', remind_at=_future(72))
        overdue = self._reminder(self.customer, 'Vencido', remind_at=_future(-5))
        soon = self._reminder(self.customer, 'Pronto', remind_at=_future(1))
        self._reminder(self.customer, 'Hecho', status_=CustomerReminder.Status.COMPLETED)
        self._reminder(self.customer, 'Cancelado', status_=CustomerReminder.Status.CANCELLED)
        other = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        self._reminder(other, 'De Beto')

        resp = self.client.get(_reminders_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['count'], 3)
        self.assertEqual([row['id'] for row in resp.data['results']], [str(overdue.pk), str(soon.pk), str(later.pk)])
        self.assertEqual(resp.data['counts'], {'pending': 3, 'closed': 2})

    def test_list_closed_and_all_scopes(self):
        _login(self.client, self.biz, 'owner')
        pending = self._reminder(self.customer, 'Pendiente', remind_at=_future(5))
        done_old = self._reminder(self.customer, 'Hecho viejo', remind_at=_future(-48), status_=CustomerReminder.Status.COMPLETED)
        cancelled = self._reminder(self.customer, 'Cancelado', remind_at=_future(-1), status_=CustomerReminder.Status.CANCELLED)

        closed = self.client.get(_reminders_url(self.customer, '?scope=closed'))
        self.assertEqual(closed.status_code, status.HTTP_200_OK, closed.data)
        self.assertEqual([row['id'] for row in closed.data['results']], [str(cancelled.pk), str(done_old.pk)])
        # Cerrados nunca figuran como vencidos.
        self.assertFalse(any(row['is_overdue'] for row in closed.data['results']))

        everything = self.client.get(_reminders_url(self.customer, '?scope=all'))
        self.assertEqual(
            [row['id'] for row in everything.data['results']], [str(pending.pk), str(done_old.pk), str(cancelled.pk)],
        )
        self.assertEqual(self.client.get(_reminders_url(self.customer, '?scope=nope')).status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_is_paginated(self):
        _login(self.client, self.biz, 'owner')
        for index in range(4):
            self._reminder(self.customer, f'R{index}', remind_at=_future(index + 1))
        resp = self.client.get(_reminders_url(self.customer, '?limit=2'))
        self.assertEqual(resp.data['count'], 4)
        self.assertEqual(len(resp.data['results']), 2)
        self.assertIsNotNone(resp.data['next'])

    # ── Overdue derivado ─────────────────────────────────────────────────────

    def test_overdue_is_derived_and_never_persisted(self):
        _login(self.client, self.biz, 'owner')
        overdue = self._reminder(self.customer, 'Vencido', remind_at=_future(-1))
        upcoming = self._reminder(self.customer, 'Futuro', remind_at=_future(1))
        resp = self.client.get(_reminders_url(self.customer))
        flags = {row['id']: (row['status'], row['is_overdue']) for row in resp.data['results']}
        self.assertEqual(flags[str(overdue.pk)], ('pending', True))
        self.assertEqual(flags[str(upcoming.pk)], ('pending', False))
        overdue.refresh_from_db()
        self.assertEqual(overdue.status, CustomerReminder.Status.PENDING)
        self.assertEqual(set(CustomerReminder.Status.values), {'pending', 'completed', 'cancelled'})

    def test_model_is_overdue(self):
        now = dj_timezone.now()
        reminder = self._reminder(self.customer, remind_at=now - dt.timedelta(minutes=1))
        self.assertTrue(reminder.is_overdue(now=now))
        self.assertFalse(reminder.is_overdue(now=now - dt.timedelta(hours=1)))
        reminder.status = CustomerReminder.Status.CANCELLED
        self.assertFalse(reminder.is_overdue(now=now))

    # ── Zona horaria ─────────────────────────────────────────────────────────

    def test_naive_remind_at_is_business_local_time(self):
        """Sin offset = hora del Business (Buenos Aires, UTC-3), no UTC ni el navegador."""
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), self._payload(remind_at='2030-10-03T16:00'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        reminder = CustomerReminder.objects.get(pk=resp.data['id'])
        self.assertEqual(reminder.remind_at, dt.datetime(2030, 10, 3, 19, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(resp.data['remind_at'], '2030-10-03T16:00:00-03:00')

    def test_offset_remind_at_keeps_instant_and_renders_in_business_zone(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), self._payload(remind_at='2030-10-03T19:00:00Z'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['remind_at'], '2030-10-03T16:00:00-03:00')

    def test_other_business_timezone(self):
        self.biz.timezone = 'Europe/Madrid'
        self.biz.save(update_fields=['timezone'])
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), self._payload(remind_at='2030-01-15T09:30'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        reminder = CustomerReminder.objects.get(pk=resp.data['id'])
        self.assertEqual(reminder.remind_at, dt.datetime(2030, 1, 15, 8, 30, tzinfo=dt.timezone.utc))
        self.assertEqual(resp.data['remind_at'], '2030-01-15T09:30:00+01:00')

    # ── Completar / cancelar / editar ────────────────────────────────────────

    def test_complete_sets_completed_at(self):
        _login(self.client, self.biz, 'owner')
        reminder = self._reminder(self.customer, remind_at=_future(-1))
        before = dj_timezone.now()
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'status': 'completed'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], 'completed')
        self.assertEqual(resp.data['status_display'], 'Completado')
        self.assertFalse(resp.data['is_overdue'])
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, CustomerReminder.Status.COMPLETED)
        self.assertGreaterEqual(reminder.completed_at, before)
        pending = self.client.get(_reminders_url(self.customer))
        self.assertEqual(pending.data['count'], 0)
        self.assertEqual(pending.data['counts'], {'pending': 0, 'closed': 1})

    def test_cancel(self):
        _login(self.client, self.biz, 'owner')
        reminder = self._reminder(self.customer)
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'status': 'cancelled'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], 'cancelled')
        self.assertIsNone(resp.data['completed_at'])
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, CustomerReminder.Status.CANCELLED)

    def test_closed_reminders_are_final(self):
        _login(self.client, self.biz, 'owner')
        done = self._reminder(self.customer, 'Hecho', status_=CustomerReminder.Status.COMPLETED)
        cancelled = self._reminder(self.customer, 'Cancelado', status_=CustomerReminder.Status.CANCELLED)
        for reminder in (done, cancelled):
            for payload in ({'status': 'pending'}, {'title': 'Cambio'}, {'status': 'cancelled'}, {'status': 'completed'}):
                with self.subTest(reminder=reminder.title, payload=payload):
                    resp = self.client.patch(_reminder_url(self.customer, reminder), payload, format='json')
                    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn('status', resp.data)
        done.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual((done.status, done.title), ('completed', 'Hecho'))
        self.assertEqual((cancelled.status, cancelled.title), ('cancelled', 'Cancelado'))

    def test_edit_pending_fields(self):
        _login(self.client, self.biz, 'owner')
        reminder = self._reminder(self.customer, 'Original')
        resp = self.client.patch(
            _reminder_url(self.customer, reminder),
            {'title': ' Nuevo ', 'description': 'Detalle', 'remind_at': '2030-05-01T10:15'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        reminder.refresh_from_db()
        self.assertEqual(reminder.title, 'Nuevo')
        self.assertEqual(reminder.description, 'Detalle')
        self.assertEqual(reminder.remind_at, dt.datetime(2030, 5, 1, 10, 15, tzinfo=BA))
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'title': '  '}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_and_delete_not_allowed(self):
        _login(self.client, self.biz, 'owner')
        reminder = self._reminder(self.customer)
        url = _reminder_url(self.customer, reminder)
        self.assertEqual(self.client.put(url, self._payload(), format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(CustomerReminder.objects.filter(pk=reminder.pk).exists())

    # ── Appointment opcional ─────────────────────────────────────────────────

    def test_link_appointment_same_business_and_customer(self):
        _login(self.client, self.biz, 'owner')
        service, pro = self._agenda(self.biz)
        appt = self._appt(self.biz, service, self.customer, _future(48), pro=pro)
        resp = self.client.post(
            _reminders_url(self.customer), self._payload(title='Confirmar asistencia', appointment_id=str(appt.pk)), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['appointment_id'], str(appt.pk))
        self.assertIsNotNone(resp.data['appointment_start_at'])
        self.assertEqual(CustomerReminder.objects.get(pk=resp.data['id']).appointment_id, appt.pk)
        # Se puede desvincular mientras está pendiente.
        resp = self.client.patch(_reminder_url(self.customer, resp.data['id']), {'appointment_id': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIsNone(resp.data['appointment_id'])

    def test_link_appointment_without_customer_allowed(self):
        _login(self.client, self.biz, 'owner')
        service, pro = self._agenda(self.biz)
        appt = self._appt(self.biz, service, None, _future(48), pro=pro)
        resp = self.client.post(_reminders_url(self.customer), self._payload(appointment_id=str(appt.pk)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_appointment_other_business_rejected(self):
        other_biz = _turnos_business(slug='rem-turnos-appt-b')
        foreign_customer = Customer.objects.create(business=other_biz, name='Ajeno', phone='1155550199')
        service, pro = self._agenda(other_biz)
        foreign_appt = self._appt(other_biz, service, foreign_customer, _future(48), pro=pro)
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), self._payload(appointment_id=str(foreign_appt.pk)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment_id', resp.data)
        self.assertNotIn('Ajeno', str(resp.data))
        reminder = self._reminder(self.customer)
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'appointment_id': str(foreign_appt.pk)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CustomerReminder.objects.filter(appointment=foreign_appt).exists())

    def test_appointment_of_other_customer_rejected(self):
        _login(self.client, self.biz, 'owner')
        other = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        service, pro = self._agenda(self.biz)
        appt = self._appt(self.biz, service, other, _future(48), pro=pro)
        resp = self.client.post(_reminders_url(self.customer), self._payload(appointment_id=str(appt.pk)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment_id', resp.data)

    def test_unknown_appointment_rejected(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_reminders_url(self.customer), self._payload(appointment_id=str(uuid.uuid4())), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reassigned_appointment_does_not_block_completion(self):
        """Si el turno pasa a otro Customer después, el recordatorio igual se puede cerrar."""
        _login(self.client, self.biz, 'owner')
        service, pro = self._agenda(self.biz)
        appt = self._appt(self.biz, service, self.customer, _future(48), pro=pro)
        reminder = self._reminder(self.customer, appointment=appt)
        appt.customer = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        appt.save(update_fields=['customer'])
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'status': 'completed'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_model_rejects_business_mismatch(self):
        other_biz = _turnos_business(slug='rem-turnos-model-b')
        with self.assertRaises(ValueError):
            CustomerReminder.objects.create(business=other_biz, customer=self.customer, title='Cruzado', remind_at=_future())
        foreign_customer = Customer.objects.create(business=other_biz, name='Ajeno', phone='1155550199')
        service, pro = self._agenda(other_biz)
        foreign_appt = self._appt(other_biz, service, foreign_customer, _future(48), pro=pro)
        with self.assertRaises(ValueError):
            CustomerReminder.objects.create(customer=self.customer, title='Cruzado', remind_at=_future(), appointment=foreign_appt)
        self.assertFalse(CustomerReminder.objects.exists())

    # ── RBAC ─────────────────────────────────────────────────────────────────

    def test_viewer_read_only(self):
        reminder = self._reminder(self.customer, 'Original')
        _login(self.client, self.biz, 'viewer')
        listed = self.client.get(_reminders_url(self.customer))
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.data)
        self.assertEqual([row['id'] for row in listed.data['results']], [str(reminder.pk)])
        url = _reminder_url(self.customer, reminder)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(_reminders_url(self.customer), self._payload(), format='json').status_code, status.HTTP_403_FORBIDDEN)
        for payload in ({'title': 'x'}, {'status': 'completed'}, {'status': 'cancelled'}):
            self.assertEqual(self.client.patch(url, payload, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)
        reminder.refresh_from_db()
        self.assertEqual((reminder.title, reminder.status), ('Original', 'pending'))

    def test_manager_and_admin_can_manage(self):
        for role in ('manager', 'admin'):
            with self.subTest(role=role):
                user = _login(self.client, self.biz, role)
                created = self.client.post(_reminders_url(self.customer), self._payload(title=f'R {role}'), format='json')
                self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
                self.assertEqual(created.data['created_by']['id'], str(user.pk))
                url = _reminder_url(self.customer, created.data['id'])
                self.assertEqual(self.client.patch(url, {'title': f'R {role} editado'}, format='json').status_code, status.HTTP_200_OK)
                self.assertEqual(self.client.patch(url, {'status': 'completed'}, format='json').status_code, status.HTTP_200_OK)
                other = self.client.post(_reminders_url(self.customer), self._payload(), format='json')
                cancel = self.client.patch(_reminder_url(self.customer, other.data['id']), {'status': 'cancelled'}, format='json')
                self.assertEqual(cancel.status_code, status.HTTP_200_OK)

    def test_anonymous_rejected(self):
        resp = self.client.get(_reminders_url(self.customer))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    # ── Tenant safety ────────────────────────────────────────────────────────

    def test_customer_from_other_business_404(self):
        other_biz = _turnos_business(slug='rem-turnos-b')
        foreign = Customer.objects.create(business=other_biz, name='Ajeno', phone='1155550199')
        self._reminder(foreign, 'Secreto')
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.get(_reminders_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.post(_reminders_url(foreign), self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(CustomerReminder.objects.filter(customer=foreign).count(), 1)

    def test_reminder_from_other_business_404(self):
        other_biz = _turnos_business(slug='rem-turnos-c')
        foreign_customer = Customer.objects.create(business=other_biz, name='Ajeno', phone='1155550198')
        foreign = self._reminder(foreign_customer, 'Secreto')
        _login(self.client, self.biz, 'owner')
        for url in (_reminder_url(self.customer, foreign), _reminder_url(foreign_customer, foreign)):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.patch(url, {'status': 'completed'}, format='json').status_code, status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, CustomerReminder.Status.PENDING)

    def test_reminder_of_other_customer_same_business_404(self):
        _login(self.client, self.biz, 'owner')
        other = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        reminder = self._reminder(other, 'De Beto')
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'status': 'cancelled'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, CustomerReminder.Status.PENDING)

    def test_not_in_timeline(self):
        """Los recordatorios tienen sección propia: la timeline histórica no los incluye."""
        _login(self.client, self.biz, 'owner')
        self._reminder(self.customer, 'Llamar')
        resp = self.client.get(f'{LIST_URL}{self.customer.pk}/timeline/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertNotIn('reminder', resp.data['types'])
        self.assertEqual(resp.data['count'], 0)


class GestionCustomerRemindersTests(CustomerRemindersMixin, APITestCase):
    """Mismo endpoint con el RBAC de Gestión: cashier/staff tienen
    `manage_customers` (POS) pero NO `manage_customer_reminders`."""

    def setUp(self):
        self.biz = _gestion_business('pro', 'rem-gestion')
        self.customer = Customer.objects.create(business=self.biz, name='Carla')

    def _assert_read_only(self, role):
        reminder = self._reminder(self.customer, 'Original')
        _login(self.client, self.biz, role)
        listed = self.client.get(_reminders_url(self.customer))
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.data)
        self.assertEqual([row['id'] for row in listed.data['results']], [str(reminder.pk)])
        url = _reminder_url(self.customer, reminder)
        self.assertEqual(self.client.post(_reminders_url(self.customer), self._payload(), format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(url, {'status': 'completed'}, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(url, {'status': 'cancelled'}, format='json').status_code, status.HTTP_403_FORBIDDEN)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, CustomerReminder.Status.PENDING)

    def test_owner_admin_manager_manage(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                _login(self.client, self.biz, role)
                created = self.client.post(_reminders_url(self.customer), self._payload(), format='json')
                self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
                done = self.client.patch(_reminder_url(self.customer, created.data['id']), {'status': 'completed'}, format='json')
                self.assertEqual(done.status_code, status.HTTP_200_OK, done.data)

    # Un test por rol: el plan tiene límite de asientos.
    def test_cashier_read_only(self):
        self._assert_read_only('cashier')

    def test_staff_read_only(self):
        self._assert_read_only('staff')

    def test_viewer_read_only(self):
        self._assert_read_only('viewer')

    def test_analyst_read_only(self):
        self._assert_read_only('analyst')

    def test_contador_read_only(self):
        self._assert_read_only('contador')


class CustomerRemindersPermissionMatrixTests(APITestCase):
    """`manage_customer_reminders` solo para owner/admin/manager donde hay Clientes."""

    def test_matrix(self):
        expected = {
            'gestion': {'owner': True, 'admin': True, 'manager': True, 'cashier': False, 'staff': False,
                        'viewer': False, 'analyst': False, 'contador': False},
            'appointments': {'owner': True, 'admin': True, 'manager': True, 'viewer': False},
        }
        for service, roles in expected.items():
            for role, allowed in roles.items():
                with self.subTest(service=service, role=role):
                    perms = permissions_for_service(service, role)
                    self.assertEqual(perms['manage_customer_reminders'], allowed)
                    self.assertTrue(perms['view_customers'])

    def test_registered_capability(self):
        from apps.accounts.rbac_registry import get_registry
        cap = get_registry().get('manage_customer_reminders')
        self.assertIsNotNone(cap)
        self.assertEqual(cap.module, 'Clientes')
