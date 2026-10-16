"""Aviso interno (CUSTOMER 07C) × recordatorios automáticos de Turnos (CUSTOMER 07B).

Un automático ya avisado (`notified_at`) es un evento consumido: la
reconciliación no lo mueve, no lo cancela ni cambia su Customer, y nunca
resetea `notified_at`. Una reprogramación posterior es un evento nuevo.
"""
from __future__ import annotations

import datetime as dt

from django.test import override_settings
from django.utils import timezone as dj_timezone
from rest_framework.test import APITestCase

from apps.customers.models import Customer, CustomerReminder
from apps.customers.reminder_dispatch import dispatch_due_customer_reminders
from apps.notifications.models import BusinessNotification

from ..services.reminder_automation import reconcile_appointment_reminders
from .test_appointment_payment_webhook import WEBHOOK_SETTINGS
from . import test_reminder_automation as automation_tests
from .test_reminder_automation import MONDAY, _automation, at

R = CustomerReminder.Status
S = CustomerReminder.Source
DUE = BusinessNotification.Kind.CUSTOMER_REMINDER_DUE


def _notifications():
    return BusinessNotification.objects.filter(kind=DUE)


@override_settings(**WEBHOOK_SETTINGS)
class ReminderDispatchLifecycleTests(APITestCase):
    # Mismo escenario que 07B (agenda lunes/martes 2030, Ana, owner logueado).
    # Se toman los métodos sin bindear la TestCase de 07B en este módulo (el
    # runner la volvería a correr).
    setUp = automation_tests.AppointmentReminderAutomationTests.setUp
    _on = automation_tests.AppointmentReminderAutomationTests._on
    _create_via_api = automation_tests.AppointmentReminderAutomationTests._create_via_api
    _appt = automation_tests.AppointmentReminderAutomationTests._appt
    _patch = automation_tests.AppointmentReminderAutomationTests._patch
    _auto = automation_tests.AppointmentReminderAutomationTests._auto

    def _dispatch_at(self, when):
        return dispatch_due_customer_reminders(now=when)

    # 7 automático "antes del turno" -----------------------------------------

    def test_appointment_upcoming_dispatches(self):
        self._on(appointment_reminder_hours_before=24)
        appt = self._create_via_api(start=at(16))
        reminder = self._auto(appt).get()
        self.assertEqual(self._dispatch_at(reminder.remind_at - dt.timedelta(minutes=1)).due, 0)
        self.assertEqual(self._dispatch_at(reminder.remind_at + dt.timedelta(minutes=1)).dispatched, 1)
        notification = _notifications().get()
        self.assertEqual(notification.title, 'Recordatorio: Confirmar turno de Ana')
        self.assertTrue(notification.message.startswith('Ana\nTurno de '))
        self.assertEqual(notification.action_url, f'/app/clientes/{self.customer.pk}')
        self.assertEqual(notification.metadata['reminder_source'], S.APPOINTMENT_UPCOMING)
        self.assertEqual(notification.metadata['appointment_id'], str(appt.pk))
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, R.PENDING)
        self.assertIsNotNone(reminder.notified_at)

    # 8 automático no-show ---------------------------------------------------

    def test_no_show_followup_dispatches(self):
        self._on(no_show_followup_delay_hours=1)
        appt = self._create_via_api()
        self._patch(appt, {'status': 'no_show'})
        followup = self._auto(appt, S.NO_SHOW_FOLLOWUP).get()
        self._dispatch_at(followup.remind_at + dt.timedelta(minutes=1))
        notification = _notifications().get()
        self.assertEqual(notification.title, 'Recordatorio: Contactar por inasistencia')
        self.assertEqual(notification.metadata['reminder_source'], S.NO_SHOW_FOLLOWUP)
        self.assertEqual(notification.related_object_id, str(followup.pk))

    # 25 reprogramado antes del aviso → 07B intacto -----------------------------

    def test_reschedule_before_notification_moves_and_notifies_at_new_time(self):
        self._on(appointment_reminder_hours_before=24)
        appt = self._create_via_api(start=at(16))
        original = self._auto(appt).get()
        old_remind_at = original.remind_at
        self._patch(appt, {'start_at': at(18).isoformat()})
        [moved] = self._auto(appt)
        self.assertEqual(moved.pk, original.pk)
        self.assertEqual(self._dispatch_at(old_remind_at + dt.timedelta(minutes=1)).due, 0)
        self.assertEqual(self._dispatch_at(moved.remind_at + dt.timedelta(minutes=1)).dispatched, 1)
        self.assertEqual(_notifications().get().related_object_id, str(moved.pk))

    # 26 / §17 reprogramado después del aviso → evento consumido -----------------

    def test_reschedule_after_notification_keeps_notified_one_and_creates_new(self):
        self._on(appointment_reminder_hours_before=24)
        appt = self._create_via_api(start=at(16))
        notified = self._auto(appt).get()
        self._dispatch_at(notified.remind_at + dt.timedelta(minutes=1))
        notified.refresh_from_db()
        notified_snapshot = (notified.remind_at, notified.automation_key, notified.notified_at, notified.description)

        tuesday = MONDAY + dt.timedelta(days=1)
        self._patch(appt, {'start_at': at(18, day=tuesday).isoformat()})

        notified.refresh_from_db()
        self.assertEqual(notified.status, R.PENDING)  # lo resuelve una persona
        self.assertEqual(
            (notified.remind_at, notified.automation_key, notified.notified_at, notified.description), notified_snapshot,
        )
        fresh = self._auto(appt).exclude(pk=notified.pk).get()
        self.assertEqual(fresh.status, R.PENDING)
        self.assertIsNone(fresh.notified_at)
        self.assertEqual(fresh.remind_at, at(18))
        self.assertEqual(_notifications().count(), 1)  # el aviso previo queda como evidencia

        self._dispatch_at(fresh.remind_at + dt.timedelta(minutes=1))
        self.assertEqual(
            sorted(_notifications().values_list('related_object_id', flat=True)), sorted([str(notified.pk), str(fresh.pk)]),
        )

    def test_reschedule_after_notification_with_rule_off_creates_nothing_new(self):
        self._on(appointment_reminder_hours_before=24)
        appt = self._create_via_api(start=at(16))
        notified = self._auto(appt).get()
        self._dispatch_at(notified.remind_at + dt.timedelta(minutes=1))
        _automation(self.biz, appointment_reminder_enabled=False)
        self._patch(appt, {'start_at': at(17).isoformat()})
        self.assertEqual(list(self._auto(appt).values_list('pk', flat=True)), [notified.pk])

    def test_notified_reminder_untouched_by_cancel_and_customer_change(self):
        self._on()
        appt = self._create_via_api(start=at(16))
        notified = self._auto(appt).get()
        self._dispatch_at(notified.remind_at + dt.timedelta(minutes=1))
        beto = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        self._patch(appt, {'customer_id': str(beto.pk)})
        self._patch(appt, {'status': 'cancelled'})
        notified.refresh_from_db()
        self.assertEqual((notified.status, notified.customer_id), (R.PENDING, self.customer.pk))
        self.assertIsNotNone(notified.notified_at)

    def test_reprocessing_same_slot_after_notification_does_not_duplicate(self):
        self._on()
        appt = self._create_via_api(start=at(16))
        notified = self._auto(appt).get()
        self._dispatch_at(notified.remind_at + dt.timedelta(minutes=1))
        for _ in range(2):
            reconcile_appointment_reminders(appt)
        self._patch(appt, {'notes': 'Sin cambios de horario'})
        self.assertEqual(list(self._auto(appt).values_list('pk', flat=True)), [notified.pk])
        self.assertEqual(self._dispatch_at(dj_timezone.now() + dt.timedelta(days=3650)).due, 0)
