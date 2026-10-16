"""Aviso interno de CustomerReminders vencidos (CUSTOMER 07C).

`dispatch_due_customer_reminders` (Beat cada minuto) → una sola
`BusinessNotification` `customer_reminder_due` por recordatorio + `notified_at`.
El recordatorio sigue `pending`. Locking/idempotencia sobre PostgreSQL real.
"""
from __future__ import annotations

import datetime as dt
import threading
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership
from apps.appointments.tests.test_customer_core_access import _gestion_business, _login, _turnos_business
from apps.notifications.models import BusinessNotification

from . import reminder_dispatch
from .models import Customer, CustomerReminder
from .reminder_dispatch import dispatch_due_customer_reminders, dispatch_reminder
from .test_reminders import CustomerRemindersMixin, _reminder_url

R = CustomerReminder.Status
Kind = BusinessNotification.Kind
NOTIFICATIONS_URL = '/api/v1/notifications/business/'


def _ago(minutes=5):
    return dj_timezone.now() - dt.timedelta(minutes=minutes)


def _notifications(**filters):
    return BusinessNotification.objects.filter(kind=Kind.CUSTOMER_REMINDER_DUE, **filters)


class ReminderDispatchTests(CustomerRemindersMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug='dispatch-biz')
        self.customer = Customer.objects.create(
            business=self.biz, name='Ana Confirmada', phone='1155550101', email='ana@example.com',
        )

    # ── 1–4 elegibilidad ─────────────────────────────────────────────────────

    def test_due_pending_creates_notification_and_stays_pending(self):
        reminder = self._reminder(self.customer, 'Llamar por inasistencia', remind_at=_ago())
        result = dispatch_due_customer_reminders()
        self.assertEqual(result.as_dict(), {'due': 1, 'dispatched': 1, 'skipped': 0, 'failed': 0})
        notification = _notifications().get()
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, R.PENDING)
        self.assertIsNotNone(reminder.notified_at)
        self.assertIsNone(reminder.completed_at)
        self.assertEqual(notification.business_id, self.biz.pk)
        self.assertIsNone(notification.read_at)

    def test_future_reminder_not_notified(self):
        reminder = self._reminder(self.customer, remind_at=dj_timezone.now() + dt.timedelta(minutes=2))
        self.assertEqual(dispatch_due_customer_reminders().due, 0)
        self.assertFalse(_notifications().exists())
        reminder.refresh_from_db()
        self.assertIsNone(reminder.notified_at)

    def test_completed_and_cancelled_not_notified(self):
        self._reminder(self.customer, 'Hecho', remind_at=_ago(), status_=R.COMPLETED)
        self._reminder(self.customer, 'Cancelado', remind_at=_ago(), status_=R.CANCELLED)
        self.assertEqual(dispatch_due_customer_reminders().due, 0)
        self.assertFalse(_notifications().exists())

    def test_already_notified_not_duplicated(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        CustomerReminder.objects.filter(pk=reminder.pk).update(notified_at=_ago(1))
        self.assertEqual(dispatch_due_customer_reminders().due, 0)
        self.assertFalse(_notifications().exists())

    def test_remind_at_exactly_now_is_due(self):
        now = dj_timezone.now()
        self._reminder(self.customer, remind_at=now)
        self.assertEqual(dispatch_due_customer_reminders(now=now).dispatched, 1)

    # ── 9–13 contenido ───────────────────────────────────────────────────────

    def test_notification_contract(self):
        remind_at = _ago()
        reminder = self._reminder(self.customer, 'Llamar por inasistencia', remind_at=remind_at)
        reminder.description = 'Preguntar si quiere\nreprogramar el turno.'
        reminder.save()
        now = dj_timezone.now()
        dispatch_due_customer_reminders(now=now)
        notification = _notifications().get()
        self.assertEqual(notification.title, 'Recordatorio: Llamar por inasistencia')
        self.assertEqual(notification.message, 'Ana Confirmada\nPreguntar si quiere reprogramar el turno.')
        self.assertEqual(notification.action_url, f'/app/clientes/{self.customer.pk}')
        self.assertEqual(notification.severity, BusinessNotification.Severity.INFO)
        self.assertEqual(notification.dedupe_key, f'customer_reminder_due:{reminder.pk}')
        self.assertEqual((notification.related_object_type, notification.related_object_id), ('customer_reminder', str(reminder.pk)))
        self.assertEqual(notification.metadata, {
            'reminder_id': str(reminder.pk),
            'customer_id': str(self.customer.pk),
            'appointment_id': None,
            'reminder_source': 'manual',
            'remind_at': remind_at.isoformat(),
        })
        # Nada de PII del cliente en el aviso (salvo el nombre en el mensaje).
        serialized = f'{notification.title} {notification.message} {notification.metadata}'
        self.assertNotIn('1155550101', serialized)
        self.assertNotIn('ana@example.com', serialized)
        reminder.refresh_from_db()
        self.assertEqual(reminder.notified_at, now)

    def test_message_without_description_and_long_description_truncated(self):
        self._reminder(self.customer, 'Sin descripción', remind_at=_ago(3))
        long_one = self._reminder(self.customer, 'Larga', remind_at=_ago(2))
        long_one.description = 'x' * 1500
        long_one.save()
        dispatch_due_customer_reminders()
        self.assertEqual(_notifications(title='Recordatorio: Sin descripción').get().message, 'Ana Confirmada')
        message = _notifications(title='Recordatorio: Larga').get().message
        self.assertTrue(message.startswith('Ana Confirmada\n'))
        self.assertLessEqual(len(message.split('\n', 1)[1]), reminder_dispatch.MESSAGE_DESCRIPTION_MAX)
        self.assertTrue(message.endswith('…'))

    def test_linked_appointment_in_metadata(self):
        service, pro = self._agenda(self.biz)
        appt = self._appt(self.biz, service, self.customer, dj_timezone.now() + dt.timedelta(days=1), pro=pro)
        reminder = self._reminder(self.customer, remind_at=_ago(), appointment=appt)
        dispatch_due_customer_reminders()
        self.assertEqual(_notifications().get().metadata['appointment_id'], str(appt.pk))
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.notified_at)

    def test_updated_at_untouched_by_notification(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        before = CustomerReminder.objects.get(pk=reminder.pk).updated_at
        dispatch_due_customer_reminders()
        self.assertEqual(CustomerReminder.objects.get(pk=reminder.pk).updated_at, before)

    # ── 14–19 idempotencia / retry ───────────────────────────────────────────

    def test_running_twice_creates_one_notification(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        dispatch_due_customer_reminders()
        first_notified_at = CustomerReminder.objects.get(pk=reminder.pk).notified_at
        second = dispatch_due_customer_reminders()
        self.assertEqual(second.due, 0)
        self.assertEqual(_notifications().count(), 1)
        self.assertEqual(CustomerReminder.objects.get(pk=reminder.pk).notified_at, first_notified_at)

    def test_dispatch_one_after_success_is_skipped(self):
        """Retry de un id ya procesado (p.ej. lista de ids vieja) → skipped."""
        reminder = self._reminder(self.customer, remind_at=_ago())
        self.assertEqual(dispatch_reminder(reminder.pk), 'dispatched')
        self.assertEqual(dispatch_reminder(reminder.pk), 'skipped')
        self.assertEqual(_notifications().count(), 1)

    def test_stale_id_completed_meanwhile_is_skipped(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        CustomerReminder.objects.filter(pk=reminder.pk).update(status=R.COMPLETED, completed_at=dj_timezone.now())
        self.assertEqual(dispatch_reminder(reminder.pk), 'skipped')
        self.assertFalse(_notifications().exists())

    def test_existing_notification_with_same_key_is_reused(self):
        """Red de seguridad: si ya existe el aviso (dedupe_key) no se crea otro; se marca."""
        reminder = self._reminder(self.customer, remind_at=_ago())
        BusinessNotification.objects.create(
            business=self.biz, kind=Kind.CUSTOMER_REMINDER_DUE, title='x',
            dedupe_key=f'customer_reminder_due:{reminder.pk}',
        )
        self.assertEqual(dispatch_due_customer_reminders().dispatched, 1)
        self.assertEqual(_notifications().count(), 1)
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.notified_at)

    def test_notification_failure_keeps_notified_at_null_and_retry_succeeds(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        with patch.object(reminder_dispatch, 'create_business_notification', side_effect=RuntimeError('db down')), \
                self.assertLogs('apps.customers.reminder_dispatch', level='ERROR') as logs:
            result = dispatch_due_customer_reminders()
        self.assertEqual((result.dispatched, result.failed), (0, 1))
        self.assertIn(str(reminder.pk), '\n'.join(logs.output))
        reminder.refresh_from_db()
        self.assertIsNone(reminder.notified_at)
        self.assertFalse(_notifications().exists())

        retry = dispatch_due_customer_reminders()
        self.assertEqual((retry.dispatched, retry.failed), (1, 0))
        self.assertEqual(_notifications().count(), 1)

    def test_crash_after_notification_before_marking_rolls_back_both(self):
        """Worker muere entre crear el aviso y marcar `notified_at` → no queda aviso huérfano."""
        reminder = self._reminder(self.customer, remind_at=_ago())
        real_notify = reminder_dispatch._notify

        def notify_then_crash(r):
            real_notify(r)
            raise RuntimeError('worker killed')

        with patch.object(reminder_dispatch, '_notify', side_effect=notify_then_crash), self.assertLogs(level='ERROR'):
            self.assertEqual(dispatch_due_customer_reminders().failed, 1)
        self.assertFalse(_notifications().exists())
        reminder.refresh_from_db()
        self.assertIsNone(reminder.notified_at)

        dispatch_due_customer_reminders()
        dispatch_due_customer_reminders()
        self.assertEqual(_notifications().count(), 1)

    def test_one_failing_reminder_does_not_block_others(self):
        bad = self._reminder(self.customer, 'Malo', remind_at=_ago(10))
        good = self._reminder(self.customer, 'Bueno', remind_at=_ago(5))
        real_notify = reminder_dispatch._notify

        def flaky(r):
            if r.pk == bad.pk:
                raise RuntimeError('boom')
            return real_notify(r)

        with patch.object(reminder_dispatch, '_notify', side_effect=flaky), self.assertLogs(level='ERROR'):
            result = dispatch_due_customer_reminders()
        self.assertEqual((result.due, result.dispatched, result.failed), (2, 1, 1))
        bad.refresh_from_db()
        good.refresh_from_db()
        self.assertIsNone(bad.notified_at)
        self.assertIsNotNone(good.notified_at)
        self.assertEqual(list(_notifications().values_list('related_object_id', flat=True)), [str(good.pk)])

    def test_logs_use_ids_not_customer_data(self):
        self._reminder(self.customer, 'Llamar a Ana al 1155550101', remind_at=_ago())
        with self.assertLogs('apps.customers.reminder_dispatch', level='INFO') as logs:
            dispatch_due_customer_reminders()
        output = '\n'.join(logs.output)
        self.assertIn('dispatched=1', output)
        for sensitive in ('1155550101', 'ana@example.com', 'Ana Confirmada'):
            self.assertNotIn(sensitive, output)

    # ── 20 tenants ──────────────────────────────────────────────────────────

    def test_each_notification_belongs_to_its_business(self):
        other = _gestion_business('pro', 'dispatch-other')
        other_customer = Customer.objects.create(business=other, name='Bruno')
        mine = self._reminder(self.customer, 'Mío', remind_at=_ago())
        theirs = self._reminder(other_customer, 'Ajeno', remind_at=_ago())
        dispatch_due_customer_reminders()
        self.assertEqual(_notifications(related_object_id=str(mine.pk)).get().business_id, self.biz.pk)
        theirs_notification = _notifications(related_object_id=str(theirs.pk)).get()
        self.assertEqual(theirs_notification.business_id, other.pk)
        self.assertEqual(theirs_notification.action_url, f'/app/clientes/{other_customer.pk}')

        _login(self.client, self.biz, 'owner')
        titles = [row['title'] for row in self.client.get(NOTIFICATIONS_URL).data['results']]
        self.assertEqual(titles, ['Recordatorio: Mío'])
        resp = self.client.post(f'{NOTIFICATIONS_URL}{theirs_notification.pk}/read/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ── 21–24 ciclo de vida del recordatorio manual ─────────────────────────

    def test_complete_or_cancel_before_due_never_notifies(self):
        _login(self.client, self.biz, 'owner')
        done = self._reminder(self.customer, 'Completar', remind_at=dj_timezone.now() + dt.timedelta(minutes=1))
        dropped = self._reminder(self.customer, 'Cancelar', remind_at=dj_timezone.now() + dt.timedelta(minutes=1))
        self.client.patch(_reminder_url(self.customer, done), {'status': 'completed'}, format='json')
        self.client.patch(_reminder_url(self.customer, dropped), {'status': 'cancelled'}, format='json')
        dispatch_due_customer_reminders(now=dj_timezone.now() + dt.timedelta(minutes=5))
        self.assertFalse(_notifications().exists())

    def test_complete_after_notification_keeps_notification_and_notified_at(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        dispatch_due_customer_reminders()
        notified_at = CustomerReminder.objects.get(pk=reminder.pk).notified_at
        _login(self.client, self.biz, 'owner')
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'status': 'completed'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], 'completed')
        self.assertIsNotNone(resp.data['notified_at'])
        reminder.refresh_from_db()
        self.assertEqual(reminder.notified_at, notified_at)
        self.assertEqual(_notifications().count(), 1)

    def test_edit_before_due_uses_new_time(self):
        now = dj_timezone.now()
        reminder = self._reminder(self.customer, remind_at=now + dt.timedelta(minutes=1))
        _login(self.client, self.biz, 'owner')
        new_time = now + dt.timedelta(hours=2)
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'remind_at': new_time.isoformat()}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(dispatch_due_customer_reminders(now=now + dt.timedelta(minutes=5)).due, 0)
        self.assertEqual(dispatch_due_customer_reminders(now=now + dt.timedelta(hours=2, minutes=1)).dispatched, 1)

    def test_postponing_a_notified_reminder_does_not_notify_again(self):
        """Un recordatorio produce como máximo un aviso: posponerlo no lo re-arma."""
        reminder = self._reminder(self.customer, remind_at=_ago())
        dispatch_due_customer_reminders()
        _login(self.client, self.biz, 'owner')
        later = dj_timezone.now() + dt.timedelta(hours=1)
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'remind_at': later.isoformat()}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIsNotNone(resp.data['notified_at'])
        dispatch_due_customer_reminders(now=later + dt.timedelta(minutes=1))
        self.assertEqual(_notifications().count(), 1)

    def test_patch_never_clears_notified_at_written_concurrently(self):
        """La edición guarda solo los campos editados (no pisa `notified_at`)."""
        from .serializers import CustomerReminderSerializer

        reminder = self._reminder(self.customer, remind_at=_ago())
        stale = CustomerReminder.objects.get(pk=reminder.pk)  # lo leyó el PATCH antes del aviso
        dispatch_due_customer_reminders()
        serializer = CustomerReminderSerializer(stale, data={'title': 'Nuevo título'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        reminder.refresh_from_db()
        self.assertEqual(reminder.title, 'Nuevo título')
        self.assertIsNotNone(reminder.notified_at)

    # ── API / superficie existente ──────────────────────────────────────────

    def test_reminder_api_exposes_notified_at(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        _login(self.client, self.biz, 'owner')
        row = self.client.get(_reminder_url(self.customer, reminder)).data
        self.assertIsNone(row['notified_at'])
        dispatch_due_customer_reminders()
        row = self.client.get(_reminder_url(self.customer, reminder)).data
        self.assertEqual(row['status'], 'pending')
        self.assertTrue(row['is_overdue'])
        self.assertTrue(row['notified_at'].endswith('-03:00'))  # en Business.timezone
        resp = self.client.patch(_reminder_url(self.customer, reminder), {'notified_at': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.notified_at)  # read-only

    def test_notification_in_existing_inbox_unread_and_mark_read(self):
        self._reminder(self.customer, 'Llamar', remind_at=_ago())
        dispatch_due_customer_reminders()
        _login(self.client, self.biz, 'owner')
        data = self.client.get(f'{NOTIFICATIONS_URL}?unread=true').data
        self.assertEqual(data['unread_count'], 1)
        [row] = data['results']
        self.assertEqual(row['kind'], 'customer_reminder_due')
        self.assertEqual(row['action_url'], f'/app/clientes/{self.customer.pk}')
        self.assertNotIn('metadata', row)
        resp = self.client.post(f'{NOTIFICATIONS_URL}{row["id"]}/read/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f'{NOTIFICATIONS_URL}?unread=true').data['unread_count'], 0)

    def test_recipients_follow_existing_business_notification_policy(self):
        """Business-wide (read_at compartido); owner/admin y, desde CUSTOMER
        07C.1, manager por `view_customer_reminder_notifications`."""
        self._reminder(self.customer, remind_at=_ago())
        dispatch_due_customer_reminders()
        for role, expected in (('owner', 200), ('admin', 200), ('manager', 200), ('viewer', 403)):
            with self.subTest(role=role):
                Membership.objects.filter(business=self.biz).delete()  # límite de 2 asientos
                client = APIClient()
                _login(client, self.biz, role)
                self.assertEqual(client.get(NOTIFICATIONS_URL).status_code, expected)


class ReminderDispatchTaskTests(CustomerRemindersMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug='dispatch-task')
        self.customer = Customer.objects.create(business=self.biz, name='Ana')

    def test_task_runs_dispatch_and_is_idempotent(self):
        from .tasks import dispatch_due_customer_reminders as task

        self._reminder(self.customer, remind_at=_ago())
        self.assertEqual(task.apply().get(), {'due': 1, 'dispatched': 1, 'skipped': 0, 'failed': 0})
        self.assertEqual(task.apply().get(), {'due': 0, 'dispatched': 0, 'skipped': 0, 'failed': 0})
        self.assertEqual(_notifications().count(), 1)

    def test_beat_schedule_registers_task_once(self):
        from config.celery import app

        entries = [name for name, entry in settings.CELERY_BEAT_SCHEDULE.items() if entry['task'] == 'customers.dispatch_due_reminders']
        self.assertEqual(entries, ['customers-dispatch-due-reminders'])
        app.loader.import_default_modules()
        self.assertIn('customers.dispatch_due_reminders', app.tasks)


class ReminderDispatchConcurrencyTests(CustomerRemindersMixin, TransactionTestCase):
    """Dos workers simultáneos sobre PostgreSQL real (FOR UPDATE SKIP LOCKED)."""

    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        self.biz = _turnos_business(slug='dispatch-concurrency')
        self.customer = Customer.objects.create(business=self.biz, name='Ana')

    def test_two_workers_produce_one_notification(self):
        self.assertEqual(connection.vendor, 'postgresql')
        reminder = self._reminder(self.customer, remind_at=_ago())
        inside = threading.Event()
        release = threading.Event()
        real_notify = reminder_dispatch._notify
        results = {}

        def slow_notify(r):
            created = real_notify(r)
            inside.set()
            release.wait(10)
            return created

        def worker_a():
            try:
                with patch.object(reminder_dispatch, '_notify', side_effect=slow_notify):
                    results['a'] = dispatch_due_customer_reminders().as_dict()
            finally:
                connection.close()

        thread = threading.Thread(target=worker_a)
        thread.start()
        try:
            self.assertTrue(inside.wait(10))
            # Worker B corre mientras A tiene la fila bloqueada y el aviso sin commitear.
            results['b'] = dispatch_due_customer_reminders().as_dict()
        finally:
            release.set()
            thread.join(10)

        self.assertEqual(results['a']['dispatched'], 1)
        self.assertEqual(results['b']['dispatched'], 0)
        self.assertEqual(_notifications().count(), 1)
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.notified_at)
        self.assertEqual(reminder.status, R.PENDING)

        # Un tercer worker después del commit tampoco duplica.
        self.assertEqual(dispatch_due_customer_reminders().due, 0)
        self.assertEqual(_notifications().count(), 1)

    def test_completing_while_dispatch_holds_lock_keeps_single_notification(self):
        reminder = self._reminder(self.customer, remind_at=_ago())
        inside = threading.Event()
        release = threading.Event()
        real_notify = reminder_dispatch._notify

        def slow_notify(r):
            created = real_notify(r)
            inside.set()
            release.wait(10)
            return created

        def worker():
            try:
                with patch.object(reminder_dispatch, '_notify', side_effect=slow_notify):
                    dispatch_due_customer_reminders()
            finally:
                connection.close()

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(inside.wait(10))
        completer_done = threading.Event()

        def complete():
            try:
                stale = CustomerReminder.objects.get(pk=reminder.pk)
                stale.status, stale.completed_at = R.COMPLETED, dj_timezone.now()
                stale.save(update_fields=['status', 'completed_at', 'updated_at'])  # espera el lock del worker
            finally:
                completer_done.set()
                connection.close()

        completer = threading.Thread(target=complete)
        completer.start()
        self.assertFalse(completer_done.wait(0.5))  # bloqueado por el FOR UPDATE
        release.set()
        thread.join(10)
        completer.join(10)

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, R.COMPLETED)
        self.assertIsNotNone(reminder.notified_at)
        self.assertEqual(_notifications().count(), 1)
