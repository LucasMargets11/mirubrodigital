"""Recordatorio automático vencido → CustomerMessageDelivery por email (CUSTOMER 07D.4A).

    reminder due → BusinessNotification interna (07C) → prepare_reminder_deliveries
    → consent gate (07D.2) → FakeEmailProvider → sent (simulado)

Sin envío real: el proveedor de email en tests es SIEMPRE el fake (guard en
settings) y `boto3.client` se parchea para fallar si algo intentara crearlo.
Mismo escenario de agenda que 07B/07C (lunes/martes 2030, Ana, owner logueado).
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.appointments.models import Appointment
from apps.appointments.services.reminder_automation import reconcile_appointment_reminders
from apps.appointments.tests import test_reminder_automation as automation_tests
from apps.appointments.tests.test_appointment_payment_webhook import WEBHOOK_SETTINGS
from apps.appointments.tests.test_customer_core_access import _login, _turnos_business
from apps.appointments.tests.test_reminder_automation import MONDAY, at
from apps.notifications.models import BusinessNotification

from . import reminder_deliveries
from .contact_preferences import consent_destination
from .deliveries import execute_delivery
from .delivery_providers import FakeEmailProvider, get_provider
from .delivery_templates import render_email
from .models import (
  CustomerCommunicationSettings, CustomerContactPreferences, CustomerMessageDelivery, CustomerReminder,
)
from .reminder_deliveries import (
  cancel_stale_appointment_deliveries, delivery_idempotency_key, prepare_reminder_deliveries,
  recover_missing_reminder_deliveries,
)
from .reminder_dispatch import dispatch_due_customer_reminders

D = CustomerMessageDelivery
DS = D.Status
R = CustomerReminder.Status
Src = CustomerReminder.Source
URL = '/api/v1/appointments/communication-automation-settings/'
DUE = BusinessNotification.Kind.CUSTOMER_REMINDER_DUE
TUESDAY = MONDAY + dt.timedelta(days=1)


def _comm(biz, **fields):
  obj, _ = CustomerCommunicationSettings.objects.update_or_create(business=biz, defaults=fields)
  return obj


def _consent(customer, channel='email', *, dnc=False):
  """Email permitido con consentimiento ligado al destino ACTUAL."""
  prefs = CustomerContactPreferences.for_customer(customer)
  setattr(prefs, f'{channel}_enabled', True)
  setattr(prefs, f'{channel}_consent_at', dj_timezone.now())
  setattr(prefs, f'{channel}_consent_source', CustomerContactPreferences.ConsentSource.MANUAL)
  setattr(prefs, f'{channel}_consent_value', consent_destination(customer, channel))
  prefs.do_not_contact = dnc
  prefs.save()
  return prefs


# ── 1-6. Settings API ────────────────────────────────────────────────────────

class CommunicationAutomationSettingsAPITests(APITestCase):

  def setUp(self):
    self.biz = _turnos_business(slug='comm-auto')
    self.api = APIClient()

  def _as(self, role, biz=None):
    _login(self.api, biz or self.biz, role)

  def test_1_defaults_off_without_creating_row(self):
    self._as('owner')
    resp = self.api.get(URL)
    self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
    self.assertEqual(
      {k: v for k, v in resp.json().items() if k != 'updated_at'},
      {'appointment_email_enabled': False, 'no_show_email_enabled': False, 'email_delivery_mode': 'simulation'},
    )
    self.assertFalse(CustomerCommunicationSettings.objects.exists())

  def test_existing_rows_start_off(self):
    """Una fila previa (p. ej. con Reply-To de 07D.3A.1) no activa nada."""
    row = CustomerCommunicationSettings.objects.create(business=self.biz, reply_to_email='turnos@negocio.com')
    row.refresh_from_db()
    self.assertFalse(row.appointment_email_enabled)
    self.assertFalse(row.no_show_email_enabled)

  def test_2_3_owner_and_admin_modify(self):
    for role, payload in (
      ('owner', {'appointment_email_enabled': True}),
      ('admin', {'no_show_email_enabled': True}),
    ):
      with self.subTest(role=role):
        self._as(role)
        resp = self.api.patch(URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
    row = CustomerCommunicationSettings.objects.get(business=self.biz)
    self.assertTrue(row.appointment_email_enabled)
    self.assertTrue(row.no_show_email_enabled)
    self.assertEqual(row.reply_to_email, '')

  def test_patch_does_not_touch_reply_to_nor_mode(self):
    _comm(self.biz, reply_to_email='turnos@negocio.com')
    self._as('owner')
    resp = self.api.patch(
      URL, {'appointment_email_enabled': True, 'reply_to_email': 'x@y.com', 'email_delivery_mode': 'live'}, format='json',
    )
    self.assertEqual(resp.status_code, status.HTTP_200_OK)
    self.assertEqual(resp.json()['email_delivery_mode'], 'simulation')
    self.assertNotIn('reply_to_email', resp.json())
    self.assertEqual(CustomerCommunicationSettings.objects.get(business=self.biz).reply_to_email, 'turnos@negocio.com')

  def test_4_manager_reads_but_cannot_modify(self):
    _comm(self.biz, appointment_email_enabled=True)
    self._as('manager')
    resp = self.api.get(URL)
    self.assertEqual((resp.status_code, resp.json()['appointment_email_enabled']), (200, True))
    self.assertEqual(self.api.patch(URL, {'appointment_email_enabled': False}, format='json').status_code, 403)
    self.assertTrue(CustomerCommunicationSettings.objects.get(business=self.biz).appointment_email_enabled)

  def test_5_viewer_has_no_access(self):
    self._as('viewer')
    self.assertEqual(self.api.get(URL).status_code, 403)
    self.assertEqual(self.api.patch(URL, {'appointment_email_enabled': True}, format='json').status_code, 403)
    self.assertFalse(CustomerCommunicationSettings.objects.exists())

  def test_put_not_allowed(self):
    self._as('owner')
    self.assertEqual(self.api.put(URL, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

  def test_6_tenant_isolation(self):
    other = _turnos_business(slug='comm-auto-other')
    _comm(other, appointment_email_enabled=True, no_show_email_enabled=True)
    self._as('owner')
    self.assertFalse(self.api.get(URL).json()['appointment_email_enabled'])
    self.api.patch(URL, {'appointment_email_enabled': True}, format='json')
    self.api.patch(URL, {'no_show_email_enabled': False}, format='json')
    self.assertTrue(CustomerCommunicationSettings.objects.get(business=other).no_show_email_enabled)

  def test_mode_is_live_only_with_explicit_ses(self):
    self._as('owner')
    with override_settings(CUSTOMER_DELIVERY_PROVIDER_EMAIL='ses'):
      self.assertEqual(self.api.get(URL).json()['email_delivery_mode'], 'live')
    with override_settings(CUSTOMER_DELIVERY_PROVIDER_EMAIL='fake', AWS_ACCESS_KEY_ID='AKIA-present'):
      self.assertEqual(self.api.get(URL).json()['email_delivery_mode'], 'simulation')


# ── 7-29. Generación / ciclo de vida / ejecución ─────────────────────────────

@override_settings(**WEBHOOK_SETTINGS)
class ReminderDeliveryTests(APITestCase):
  # Métodos de la TestCase de 07B sin bindear (el runner la volvería a correr).
  _base_setUp = automation_tests.AppointmentReminderAutomationTests.setUp
  _on = automation_tests.AppointmentReminderAutomationTests._on
  _create_via_api = automation_tests.AppointmentReminderAutomationTests._create_via_api
  _appt = automation_tests.AppointmentReminderAutomationTests._appt
  _patch = automation_tests.AppointmentReminderAutomationTests._patch
  _auto = automation_tests.AppointmentReminderAutomationTests._auto

  def setUp(self):
    self._base_setUp()
    self.customer.email = 'Ana@Example.com'
    self.customer.save()
    boto = patch('boto3.client', side_effect=AssertionError('no real AWS client in tests'))
    self.boto = boto.start()
    self.addCleanup(boto.stop)

  # helpers ---------------------------------------------------------------

  def _email_on(self, **fields):
    defaults = {'appointment_email_enabled': True, 'no_show_email_enabled': True}
    defaults.update(fields)
    return _comm(self.biz, **defaults)

  def _due_reminder(self, start=None):
    """Turno confirmado con recordatorio automático 24 h antes."""
    self._on(appointment_reminder_hours_before=24)
    appt = self._create_via_api(start=start or at(16))
    return appt, self._auto(appt).get()

  def _dispatch(self, reminder, minutes=1):
    return dispatch_due_customer_reminders(now=reminder.remind_at + dt.timedelta(minutes=minutes))

  def _deliveries(self, **filters):
    return D.objects.filter(business=self.biz, **filters)

  # 7 / 10 / 15 / 16 / 17 generación ----------------------------------------

  def test_7_setting_off_creates_no_delivery(self):
    _consent(self.customer)
    _, reminder = self._due_reminder()
    self.assertEqual(self._dispatch(reminder).dispatched, 1)
    self.assertEqual(BusinessNotification.objects.filter(kind=DUE).count(), 1)
    self.assertFalse(D.objects.exists())

  def test_8_15_16_17_on_with_consent_prepares_pending_email(self):
    self._email_on()
    _consent(self.customer)
    appt, reminder = self._due_reminder()
    self._dispatch(reminder)

    # aviso interno intacto + Delivery externo
    self.assertEqual(BusinessNotification.objects.filter(kind=DUE, related_object_id=str(reminder.pk)).count(), 1)
    reminder.refresh_from_db()
    self.assertIsNotNone(reminder.notified_at)
    self.assertEqual(reminder.status, R.PENDING)

    delivery = self._deliveries().get()
    self.assertEqual(delivery.status, DS.PENDING)
    self.assertEqual(delivery.channel, D.Channel.EMAIL)
    self.assertEqual(delivery.purpose, D.Purpose.APPOINTMENT_REMINDER)
    self.assertEqual(delivery.template_key, D.TemplateKey.APPOINTMENT_REMINDER_V1)
    # 15 relaciones
    self.assertEqual((delivery.customer_id, delivery.appointment_id, delivery.reminder_id), (self.customer.pk, appt.pk, reminder.pk))
    # 11 idempotency key estable
    self.assertEqual(delivery.idempotency_key, f'appointment-reminder:{appt.pk}:{reminder.pk}:email')
    self.assertEqual(delivery.idempotency_key, delivery_idempotency_key(reminder))
    # 16 snapshots
    self.assertEqual(delivery.destination_snapshot, 'ana@example.com')
    ctx = delivery.context
    self.assertEqual(ctx['customer_id'], str(self.customer.pk))
    self.assertEqual(ctx['appointment_id'], str(appt.pk))
    self.assertEqual(ctx['reminder_id'], str(reminder.pk))
    self.assertEqual(ctx['customer_name'], 'Ana')
    self.assertEqual(ctx['business_name'], self.biz.name)
    self.assertEqual(ctx['service_name'], appt.service_name)
    self.assertEqual(dt.datetime.fromisoformat(ctx['appointment_start_at']), at(16))
    self.assertNotIn('ana@example.com', str(ctx).lower())
    # 17 el template renderiza con ese contexto
    rendered = render_email(delivery.template_key, ctx)
    self.assertIn('Recordatorio de turno', rendered.subject)
    self.assertIn('16:00', rendered.text_body)

  def test_9_24_duplicate_dispatch_and_recovery_reuse_same_delivery(self):
    self._email_on()
    _consent(self.customer)
    _, reminder = self._due_reminder()
    self._dispatch(reminder)
    self._dispatch(reminder, minutes=2)  # Beat duplicado: ya avisado → no elegible
    recover_missing_reminder_deliveries(now=reminder.remind_at + dt.timedelta(minutes=3))
    reminder.refresh_from_db()
    first = prepare_reminder_deliveries(reminder, now=reminder.remind_at + dt.timedelta(minutes=4), enqueue=False)
    second = prepare_reminder_deliveries(reminder, now=reminder.remind_at + dt.timedelta(minutes=5), enqueue=False)
    self.assertEqual(self._deliveries().count(), 1)
    self.assertEqual(first[0].pk, second[0].pk)
    self.assertEqual(first[0].pk, self._deliveries().get().pk)
    self.assertEqual(BusinessNotification.objects.filter(kind=DUE).count(), 1)

  def test_10_manual_reminder_never_creates_delivery(self):
    self._email_on()
    _consent(self.customer)
    appt = self._appt()
    manual = CustomerReminder.objects.create(
      business=self.biz, customer=self.customer, appointment=appt, title='Llamar', remind_at=at(9),
    )
    self.assertEqual(self._dispatch(manual).dispatched, 1)
    manual.refresh_from_db()
    self.assertEqual(prepare_reminder_deliveries(manual, now=at(10), enqueue=False), [])
    recover_missing_reminder_deliveries(now=at(9, 5))
    self.assertFalse(D.objects.exists())

  # 11-14 consent gate → skipped auditado -------------------------------------

  def _skip_reason_after_dispatch(self):
    self._email_on()
    _, reminder = self._due_reminder()
    self._dispatch(reminder)
    delivery = self._deliveries().get()
    self.assertEqual(delivery.status, DS.SKIPPED)
    self.assertIsNotNone(delivery.skipped_at)
    return delivery.skip_reason

  def test_11_do_not_contact_is_skipped(self):
    _consent(self.customer, dnc=True)
    self.assertEqual(self._skip_reason_after_dispatch(), 'do_not_contact')

  def test_12_email_disabled_is_skipped(self):
    self.assertEqual(self._skip_reason_after_dispatch(), 'disabled')
    self.assertFalse(CustomerContactPreferences.objects.exists())

  def test_13_destination_changed_since_consent_is_skipped(self):
    _consent(self.customer)
    self.customer.email = 'nueva@example.com'
    self.customer.save()
    self.assertEqual(self._skip_reason_after_dispatch(), 'consent_destination_changed')

  def test_14_missing_email_is_skipped(self):
    _consent(self.customer)
    self.customer.email = ''
    self.customer.save()
    self.assertEqual(self._skip_reason_after_dispatch(), 'missing_email')

  # No-show ------------------------------------------------------------------

  def test_no_show_followup_email(self):
    self._email_on()
    _consent(self.customer)
    self._on(no_show_followup_delay_hours=1)
    appt = self._create_via_api()
    self._patch(appt, {'status': 'no_show'})
    followup = self._auto(appt, Src.NO_SHOW_FOLLOWUP).get()
    self._dispatch(followup)
    delivery = self._deliveries().get()
    self.assertEqual(delivery.status, DS.PENDING)
    self.assertEqual(delivery.purpose, D.Purpose.NO_SHOW_FOLLOWUP)
    self.assertEqual(delivery.template_key, D.TemplateKey.NO_SHOW_FOLLOWUP_V1)
    self.assertEqual(delivery.idempotency_key, f'no-show:{appt.pk}:{followup.pk}:email')
    rendered = render_email(delivery.template_key, delivery.context)
    self.assertIn('no pudiste asistir', rendered.text_body)
    self.assertNotIn('Recordatorio de turno', rendered.subject)

  def test_no_show_switch_is_independent(self):
    self._email_on(no_show_email_enabled=False)
    _consent(self.customer)
    self._on(no_show_followup_delay_hours=1)
    appt = self._create_via_api()
    self._patch(appt, {'status': 'no_show'})
    self._dispatch(self._auto(appt, Src.NO_SHOW_FOLLOWUP).get())
    self.assertFalse(D.objects.exists())

  # 18-24 ciclo de vida -------------------------------------------------------

  def _pending_delivery(self, start=None):
    self._email_on()
    _consent(self.customer)
    appt, reminder = self._due_reminder(start=start)
    self._dispatch(reminder)
    delivery = self._deliveries().get()
    self.assertEqual(delivery.status, DS.PENDING)
    return appt, reminder, delivery

  def test_18_cancelled_appointment_cancels_pending_delivery(self):
    appt, reminder, delivery = self._pending_delivery()
    self._patch(appt, {'status': 'cancelled'})
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, DS.CANCELLED)
    self.assertIsNotNone(delivery.cancelled_at)
    self.assertTrue(D.objects.filter(pk=delivery.pk).exists())  # no se borra
    reminder.refresh_from_db()
    self.assertIsNotNone(reminder.notified_at)  # el aviso interno no cambia
    self.assertIsNone(execute_delivery(delivery.pk, provider=FakeEmailProvider()))

  def test_18b_retryable_failure_is_also_cancelled(self):
    appt, _, delivery = self._pending_delivery()
    self.assertEqual(execute_delivery(delivery.pk, provider=FakeEmailProvider('retryable_failure')), DS.FAILED)
    delivery.refresh_from_db()
    self.assertIsNotNone(delivery.next_retry_at)
    self._patch(appt, {'status': 'cancelled'})
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, DS.CANCELLED)

  def test_19_expired_appointment_cancels_pending_delivery(self):
    appt, _, delivery = self._pending_delivery()
    Appointment.objects.filter(pk=appt.pk).update(status=Appointment.Status.EXPIRED)
    appt.refresh_from_db()
    reconcile_appointment_reminders(appt)
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, DS.CANCELLED)

  def test_20_21_reschedule_cancels_old_and_new_reminder_gets_new_delivery(self):
    appt, old_reminder, old = self._pending_delivery()
    old_snapshot = (old.destination_snapshot, dict(old.context), old.idempotency_key)
    self._patch(appt, {'start_at': at(18, day=TUESDAY).isoformat()})

    old.refresh_from_db()
    self.assertEqual(old.status, DS.CANCELLED)
    self.assertEqual((old.destination_snapshot, old.context, old.idempotency_key), old_snapshot)  # sin reescribir

    fresh = self._auto(appt).exclude(pk=old_reminder.pk).get()
    self._dispatch(fresh)
    new = self._deliveries().exclude(pk=old.pk).get()
    self.assertEqual(new.status, DS.PENDING)
    self.assertEqual(new.reminder_id, fresh.pk)
    self.assertNotEqual(new.idempotency_key, old.idempotency_key)
    self.assertEqual(dt.datetime.fromisoformat(new.context['appointment_start_at']), at(18, day=TUESDAY))
    # el recordatorio viejo (consumido) nunca vuelve a preparar nada
    old_reminder.refresh_from_db()
    self.assertEqual(prepare_reminder_deliveries(old_reminder, now=fresh.remind_at, enqueue=False), [])
    self.assertEqual(self._deliveries().count(), 2)

  def test_reschedule_between_notification_and_preparation_prepares_nothing(self):
    self._email_on()
    _consent(self.customer)
    appt, reminder = self._due_reminder()
    with patch.object(reminder_deliveries, 'prepare_customer_delivery', side_effect=RuntimeError('db hiccup')):
      self._dispatch(reminder)
    self._patch(appt, {'start_at': at(18, day=TUESDAY).isoformat()})
    recover_missing_reminder_deliveries(now=reminder.remind_at + dt.timedelta(minutes=5))
    self.assertFalse(self._deliveries().filter(reminder=reminder).exists())

  def test_customer_change_cancels_pending_delivery(self):
    from .models import Customer

    appt, _, delivery = self._pending_delivery()
    other = Customer.objects.create(business=self.biz, name='Beto', phone='1155550199', email='beto@example.com')
    Appointment.objects.filter(pk=appt.pk).update(customer=other)
    appt.refresh_from_db()
    self.assertEqual(cancel_stale_appointment_deliveries(appt), 1)
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, DS.CANCELLED)

  def test_unrelated_edit_keeps_pending_delivery(self):
    appt, _, delivery = self._pending_delivery()
    self._patch(appt, {'notes': 'Trae el pelo lavado'})
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, DS.PENDING)

  def test_22_sent_delivery_is_not_cancelled_retroactively(self):
    appt, _, delivery = self._pending_delivery()
    self.assertEqual(execute_delivery(delivery.pk, provider=FakeEmailProvider()), DS.SENT)
    self._patch(appt, {'status': 'cancelled'})
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, DS.SENT)
    self.assertIsNone(delivery.cancelled_at)

  def test_23_skipped_is_not_revived(self):
    self._email_on()
    appt, reminder = self._due_reminder()  # sin consentimiento → skipped
    self._dispatch(reminder)
    delivery = self._deliveries().get()
    self.assertEqual(delivery.status, DS.SKIPPED)
    _consent(self.customer)  # consentir después no revive el skipped
    recover_missing_reminder_deliveries(now=reminder.remind_at + dt.timedelta(minutes=2))
    reminder.refresh_from_db()
    self.assertEqual(prepare_reminder_deliveries(reminder, now=reminder.remind_at, enqueue=False)[0].pk, delivery.pk)
    self._patch(appt, {'status': 'cancelled'})
    delivery.refresh_from_db()
    self.assertEqual((delivery.status, delivery.skip_reason), (DS.SKIPPED, 'disabled'))
    self.assertEqual(self._deliveries().count(), 1)

  # 25-29 ejecución con FakeEmailProvider -------------------------------------

  def test_25_26_27_28_29_due_reminder_executes_with_fake_provider(self):
    self._email_on()
    _consent(self.customer)
    _, reminder = self._due_reminder()
    self.assertEqual(settings.CUSTOMER_DELIVERY_PROVIDER_EMAIL, 'fake')
    self.assertIsInstance(get_provider(D.Channel.EMAIL), FakeEmailProvider)

    with patch('apps.customers.tasks.execute_customer_delivery.delay') as delay, \
        self.captureOnCommitCallbacks(execute=True):
      self._dispatch(reminder)
    delivery = self._deliveries().get()
    delay.assert_called_once_with(str(delivery.pk))  # 25: encolado tras el commit

    # Lo que haría el worker: proveedor por default del entorno (fake).
    self.assertEqual(execute_delivery(delivery.pk), DS.SENT)
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, DS.SENT)
    self.assertEqual(delivery.provider, D.Provider.FAKE_EMAIL)
    self.assertTrue(delivery.provider_message_id.startswith('fake-'))
    self.assertIsNone(delivery.delivered_at)
    self.boto.assert_not_called()  # 29: nada de AWS / network

    # 28: aparece en la ficha (Comunicaciones), simulado.
    resp = self.client.get(f'/api/v1/customers/{self.customer.pk}/deliveries/')
    self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
    items = resp.json()['results']
    self.assertEqual(len(items), 1)
    self.assertEqual(items[0]['status'], 'sent')
    self.assertTrue(items[0]['is_simulated'])
    self.assertEqual(items[0]['purpose'], 'appointment_reminder')
    self.assertNotIn('provider_message_id', items[0])

  def test_skipped_is_not_enqueued(self):
    self._email_on()
    _, reminder = self._due_reminder()
    with patch('apps.customers.tasks.execute_customer_delivery.delay') as delay, \
        self.captureOnCommitCallbacks(execute=True):
      self._dispatch(reminder)
    delay.assert_not_called()

  # Fallos aislados + recuperación -----------------------------------------------

  def test_preparation_failure_keeps_notification_and_recovers_later(self):
    self._email_on()
    _consent(self.customer)
    _, reminder = self._due_reminder()
    with patch.object(reminder_deliveries, 'prepare_customer_delivery', side_effect=RuntimeError('db hiccup')), \
        self.assertLogs('apps.customers.reminder_deliveries', level='ERROR') as logs:
      result = self._dispatch(reminder)
    self.assertEqual(result.dispatched, 1)
    self.assertIn(str(reminder.pk), '\n'.join(logs.output))
    reminder.refresh_from_db()
    self.assertIsNotNone(reminder.notified_at)
    self.assertEqual(BusinessNotification.objects.filter(kind=DUE).count(), 1)
    self.assertFalse(D.objects.exists())

    # Próxima corrida de Beat: reintenta por idempotencia, sin re-avisar.
    dispatch_due_customer_reminders(now=reminder.notified_at + dt.timedelta(minutes=1))
    self.assertEqual(self._deliveries().get().status, DS.PENDING)
    self.assertEqual(BusinessNotification.objects.filter(kind=DUE).count(), 1)

  def test_recovery_window_is_bounded(self):
    self._email_on()
    _consent(self.customer)
    _, reminder = self._due_reminder()
    with patch.object(reminder_deliveries, 'prepare_customer_delivery', side_effect=RuntimeError('boom')):
      self._dispatch(reminder)
    reminder.refresh_from_db()
    self.assertEqual(recover_missing_reminder_deliveries(now=reminder.notified_at + dt.timedelta(hours=2)), 0)
    self.assertFalse(D.objects.exists())

  def test_recovery_ignores_other_business_and_rules_off(self):
    _consent(self.customer)
    _, reminder = self._due_reminder()
    self._dispatch(reminder)  # regla de email apagada
    other = _turnos_business(slug='comm-auto-other-biz')
    _comm(other, appointment_email_enabled=True)
    self.assertEqual(recover_missing_reminder_deliveries(now=reminder.remind_at + dt.timedelta(minutes=2)), 0)
    self.assertFalse(D.objects.exists())


class ProviderGuardTests(APITestCase):

  def test_test_suite_always_uses_fake_email_provider(self):
    self.assertEqual(settings.CUSTOMER_DELIVERY_PROVIDER_EMAIL, 'fake')
    self.assertIsInstance(get_provider(D.Channel.EMAIL), FakeEmailProvider)
