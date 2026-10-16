"""Infraestructura de entregas externas al Customer (CUSTOMER 07D.2).

prepare (consent gate + destination snapshot + idempotency) → execute (lock,
re-validación, fake provider) → sent / failed / skipped + reintentos. Sin
proveedor real: todo con fakes inyectados. Locking sobre PostgreSQL real.
"""
from __future__ import annotations

import datetime as dt
import threading
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin, _login, _turnos_business

from . import deliveries
from .contact_preferences import consent_destination
from .deliveries import (
  DeliveryPreparationError, cancel_delivery, execute_delivery, mask_destination, prepare_customer_delivery,
  retry_due_customer_deliveries,
)
from .delivery_providers import FakeEmailProvider, FakeWhatsAppProvider, ProviderSendResult
from .models import Customer, CustomerContactPreferences, CustomerMessageDelivery, CustomerReminder
from .test_timeline import _without_permission

D = CustomerMessageDelivery
S = D.Status
WA = D.Channel.WHATSAPP
EMAIL = D.Channel.EMAIL
REMINDER = D.Purpose.APPOINTMENT_REMINDER


def _deliveries_url(customer):
  return f'/api/v1/customers/{customer.pk}/deliveries/'


class DeliveryMixin(TurnosAgendaMixin):

  def _customer(self, biz, name='Ana', *, phone='1155550101', email='ana@example.com', **extra):
    return Customer.objects.create(business=biz, name=name, phone=phone, email=email, **extra)

  def _consent(self, customer, *channels, dnc=False):
    """Preferencias con consentimiento ligado al destino ACTUAL de cada canal."""
    now = dj_timezone.now()
    prefs = CustomerContactPreferences.for_customer(customer)
    for channel in channels:
      setattr(prefs, f'{channel}_enabled', True)
      setattr(prefs, f'{channel}_consent_at', now)
      setattr(prefs, f'{channel}_consent_source', CustomerContactPreferences.ConsentSource.MANUAL)
      setattr(prefs, f'{channel}_consent_value', consent_destination(customer, channel))
    prefs.do_not_contact = dnc
    prefs.save()
    return prefs

  def _prepare(self, customer, channel=WA, *, key=None, purpose=REMINDER, **kwargs):
    kwargs.setdefault('enqueue', False)
    return prepare_customer_delivery(
      business=customer.business, customer=customer, channel=channel, purpose=purpose,
      idempotency_key=key or f'test:{customer.pk}:{channel}:{purpose}', **kwargs,
    )

  def _pending(self, customer, channel=WA, **kwargs):
    self._consent(customer, channel)
    delivery, created = self._prepare(customer, channel, **kwargs)
    self.assertTrue(created)
    self.assertEqual(delivery.status, S.PENDING)
    return delivery

  def _make_due(self, delivery):
    D.objects.filter(pk=delivery.pk).update(next_retry_at=dj_timezone.now() - dt.timedelta(seconds=1))


class FlakyProvider(FakeWhatsAppProvider):
  """Falla de forma reintentable las primeras `failures` veces."""

  def __init__(self, failures):
    super().__init__('success')
    self.failures = failures

  def send(self, message):
    self.sent.append(message)
    if len(self.sent) <= self.failures:
      return ProviderSendResult.failure('fake_temporary_error', 'temporal', retryable=True)
    return ProviderSendResult.ok('fake-final')


# ── 27. Modelo / preparación ────────────────────────────────────────────────

class PrepareDeliveryTests(DeliveryMixin, TestCase):

  def setUp(self):
    self.biz = _turnos_business(slug='delivery-prepare')
    self.customer = self._customer(self.biz)

  def test_1_whatsapp_usable_is_pending_with_snapshot(self):
    delivery = self._pending(self.customer, WA)
    self.assertEqual(delivery.destination_snapshot, consent_destination(self.customer, WA))
    self.assertTrue(delivery.destination_snapshot.startswith('54'))
    self.assertEqual(delivery.attempt_count, 0)
    self.assertIsNone(delivery.provider)
    self.assertEqual(delivery.template_key, D.TemplateKey.APPOINTMENT_REMINDER_V1)

  def test_2_email_usable_is_pending_with_normalized_email(self):
    self.customer.email = '  Ana@Example.COM '
    self.customer.save()
    delivery = self._pending(self.customer, EMAIL)
    self.assertEqual(delivery.destination_snapshot, 'ana@example.com')

  def test_3_do_not_contact_is_skipped(self):
    self._consent(self.customer, WA, dnc=True)
    delivery, created = self._prepare(self.customer)
    self.assertTrue(created)
    self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, 'do_not_contact'))
    self.assertIsNotNone(delivery.skipped_at)
    self.assertIsNone(delivery.failure_code)

  def test_4_channel_disabled_is_skipped(self):
    self._consent(self.customer, EMAIL)  # WhatsApp apagado
    delivery, _ = self._prepare(self.customer, WA)
    self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, 'disabled'))

  def test_4b_no_preferences_row_is_skipped_as_disabled(self):
    delivery, _ = self._prepare(self.customer, WA)
    self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, 'disabled'))
    self.assertFalse(CustomerContactPreferences.objects.filter(customer=self.customer).exists())

  def test_5_consent_missing_is_skipped(self):
    prefs = self._consent(self.customer, WA)
    CustomerContactPreferences.objects.filter(pk=prefs.pk).update(whatsapp_consent_value=None)
    delivery, _ = self._prepare(self.customer, WA)
    self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, 'consent_missing'))

  def test_6_destination_changed_since_consent_is_skipped(self):
    self._consent(self.customer, WA, EMAIL)
    self.customer.phone = '1166660202'
    self.customer.email = 'otra@example.com'
    self.customer.save()
    wa, _ = self._prepare(self.customer, WA)
    em, _ = self._prepare(self.customer, EMAIL)
    self.assertEqual((wa.status, wa.skip_reason), (S.SKIPPED, 'consent_destination_changed'))
    self.assertEqual((em.status, em.skip_reason), (S.SKIPPED, 'consent_destination_changed'))
    # Auditoría: queda el destino que se habría usado (enmascarado en la API).
    self.assertEqual(wa.destination_snapshot, consent_destination(self.customer, WA))

  def test_7_missing_phone_and_email_are_skipped(self):
    self._consent(self.customer, WA, EMAIL)
    Customer.objects.filter(pk=self.customer.pk).update(phone='', email='')
    self.customer.refresh_from_db()
    wa, _ = self._prepare(self.customer, WA)
    em, _ = self._prepare(self.customer, EMAIL)
    self.assertEqual((wa.status, wa.skip_reason, wa.destination_snapshot), (S.SKIPPED, 'missing_phone', None))
    self.assertEqual((em.status, em.skip_reason, em.destination_snapshot), (S.SKIPPED, 'missing_email', None))

  def test_8_snapshot_does_not_follow_customer_changes(self):
    delivery = self._pending(self.customer, WA)
    original = delivery.destination_snapshot
    self.customer.phone = '1166660202'
    self.customer.save()
    delivery.refresh_from_db()
    self.assertEqual(delivery.destination_snapshot, original)

  def test_9_duplicate_idempotency_key_returns_same_delivery(self):
    first = self._pending(self.customer, WA, key='appointment-reminder:a:r:whatsapp')
    again, created = self._prepare(self.customer, WA, key='appointment-reminder:a:r:whatsapp')
    self.assertFalse(created)
    self.assertEqual(again.pk, first.pk)
    self.assertEqual(D.objects.count(), 1)
    # Aunque ahora el canal no sea usable, el evento ya tiene su Delivery.
    self._consent(self.customer, WA, dnc=True)
    again, created = self._prepare(self.customer, WA, key='appointment-reminder:a:r:whatsapp')
    self.assertEqual((again.pk, created, again.status), (first.pk, False, S.PENDING))

  def test_9b_key_reused_for_other_communication_is_rejected(self):
    self._pending(self.customer, WA, key='k1')
    with self.assertRaises(DeliveryPreparationError):
      self._prepare(self.customer, EMAIL, key='k1')
    other = self._customer(self.biz, 'Beto', phone='1177770303', email='beto@example.com')
    with self.assertRaises(DeliveryPreparationError):
      self._prepare(other, WA, key='k1')

  def test_9c_db_unique_constraint_per_business(self):
    delivery = self._pending(self.customer, WA, key='dup')
    with self.assertRaises(IntegrityError), transaction.atomic():
      D.objects.create(
        business=self.biz, customer=self.customer, channel=WA, purpose=REMINDER,
        idempotency_key='dup', destination_snapshot=delivery.destination_snapshot,
      )
    # La misma key en OTRO Business es otra comunicación.
    biz2 = _turnos_business(slug='delivery-prepare-2')
    other = self._customer(biz2)
    self._consent(other, WA)
    other_delivery, created = self._prepare(other, WA, key='dup')
    self.assertTrue(created)
    self.assertNotEqual(other_delivery.pk, delivery.pk)

  def test_10_other_tenant_blocked(self):
    biz2 = _turnos_business(slug='delivery-prepare-other')
    foreign = self._customer(biz2, 'Ajena')
    self._consent(foreign, WA)
    with self.assertRaises(DeliveryPreparationError):
      prepare_customer_delivery(
        business=self.biz, customer=foreign, channel=WA, purpose=REMINDER, idempotency_key='x', enqueue=False,
      )
    service, pro = self._agenda(biz2)
    foreign_appt = self._appt(biz2, service, foreign, dj_timezone.now() + dt.timedelta(days=1), pro=pro)
    self._consent(self.customer, WA)
    with self.assertRaises(DeliveryPreparationError):
      self._prepare(self.customer, WA, key='y', appointment=foreign_appt)
    foreign_reminder = CustomerReminder.objects.create(
      business=biz2, customer=foreign, title='X', remind_at=dj_timezone.now(),
    )
    with self.assertRaises(DeliveryPreparationError):
      self._prepare(self.customer, WA, key='z', reminder=foreign_reminder)
    self.assertFalse(D.objects.exists())

  def test_11_inactive_customer_is_skipped(self):
    self._consent(self.customer, WA)
    Customer.objects.filter(pk=self.customer.pk).update(is_active=False)
    self.customer.refresh_from_db()
    delivery, _ = self._prepare(self.customer, WA)
    self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, 'customer_inactive'))

  def test_invalid_channel_and_purpose_rejected(self):
    for kwargs in ({'channel': 'sms'}, {'channel': 'phone'}, {'purpose': 'marketing'}, {'key': '   '}):
      with self.subTest(**kwargs), self.assertRaises(DeliveryPreparationError):
        self._prepare(self.customer, kwargs.get('channel', WA), purpose=kwargs.get('purpose', REMINDER), key=kwargs.get('key', 'k'))

  def test_context_is_minimal_and_links_reminder_and_appointment(self):
    service, pro = self._agenda(self.biz)
    start = dj_timezone.now() + dt.timedelta(days=1)
    appt = self._appt(self.biz, service, self.customer, start, pro=pro)
    reminder = CustomerReminder.objects.create(
      business=self.biz, customer=self.customer, title='Recordar', remind_at=start - dt.timedelta(hours=24), appointment=appt,
    )
    wa = self._pending(self.customer, WA, key=f'appointment-reminder:{appt.pk}:{reminder.pk}:whatsapp', appointment=appt, reminder=reminder)
    self._consent(self.customer, WA, EMAIL)
    em, _ = self._prepare(self.customer, EMAIL, key=f'appointment-reminder:{appt.pk}:{reminder.pk}:email', appointment=appt, reminder=reminder)
    self.assertEqual(wa.context, {
      'customer_id': str(self.customer.pk), 'appointment_id': str(appt.pk), 'reminder_id': str(reminder.pk),
      'service_name': 'Corte', 'appointment_start_at': start.isoformat(),
      'customer_name': 'Ana', 'business_name': self.biz.name, 'business_timezone': 'America/Argentina/Buenos_Aires',
      'business_reply_to': None,
    })
    self.assertNotIn(self.customer.phone, str(wa.context))
    # Un recordatorio → varios deliveries (uno por canal), sin OneToOne.
    self.assertEqual(set(reminder.message_deliveries.values_list('channel', flat=True)), {WA, EMAIL})
    self.assertEqual(em.status, S.PENDING)

  def test_enqueue_on_commit_only_for_new_pending(self):
    self._consent(self.customer, WA)
    with patch('apps.customers.tasks.execute_customer_delivery.delay') as delay:
      with self.captureOnCommitCallbacks(execute=True):
        delivery, _ = self._prepare(self.customer, WA, key='enq', enqueue=True)
      delay.assert_called_once_with(str(delivery.pk))
      with self.captureOnCommitCallbacks(execute=True):
        self._prepare(self.customer, WA, key='enq', enqueue=True)  # idempotente: no re-encola
        self._prepare(self.customer, EMAIL, key='enq-email', enqueue=True)  # skipped: no se encola
      delay.assert_called_once()

  def test_model_save_rejects_cross_tenant(self):
    biz2 = _turnos_business(slug='delivery-save-other')
    with self.assertRaises(ValueError):
      D(business=biz2, customer=self.customer, channel=WA, purpose=REMINDER, idempotency_key='x', destination_snapshot='1').save()

  def test_mask_destination(self):
    self.assertEqual(mask_destination(WA, '5491155550202'), '•••• 0202')
    self.assertEqual(mask_destination(EMAIL, 'ana@dominio.com'), 'a•••@dominio.com')
    self.assertIsNone(mask_destination(WA, None))


# ── 28. Ejecución ───────────────────────────────────────────────────────────

class ExecuteDeliveryTests(DeliveryMixin, TestCase):

  def setUp(self):
    self.biz = _turnos_business(slug='delivery-exec')
    self.customer = self._customer(self.biz)

  def test_12_13_14_fake_success_is_sent(self):
    delivery = self._pending(self.customer, WA)
    provider = FakeWhatsAppProvider('success')
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SENT)
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, S.SENT)
    self.assertTrue(delivery.provider_message_id.startswith('fake-'))
    self.assertEqual(delivery.provider, D.Provider.FAKE_WHATSAPP)
    self.assertEqual(delivery.attempt_count, 1)
    self.assertIsNotNone(delivery.sent_at)
    self.assertIsNotNone(delivery.last_attempt_at)
    self.assertIsNone(delivery.delivered_at)  # sent ≠ delivered
    message = provider.sent[0]
    self.assertEqual(message.destination, delivery.destination_snapshot)
    self.assertEqual(message.idempotency_key, delivery.idempotency_key)

  def test_default_provider_is_fake_per_channel(self):
    delivery = self._pending(self.customer, EMAIL)
    self.assertEqual(execute_delivery(delivery.pk), S.SENT)
    delivery.refresh_from_db()
    self.assertEqual(delivery.provider, D.Provider.FAKE_EMAIL)

  def test_15_executing_twice_does_not_resend(self):
    delivery = self._pending(self.customer, WA)
    provider = FakeWhatsAppProvider('success')
    execute_delivery(delivery.pk, provider=provider)
    self.assertIsNone(execute_delivery(delivery.pk, provider=provider))
    self.assertEqual(len(provider.sent), 1)
    delivery.refresh_from_db()
    self.assertEqual(delivery.attempt_count, 1)

  def test_17_consent_revoked_after_prepare_is_skipped(self):
    cases = {
      'do_not_contact': lambda prefs: setattr(prefs, 'do_not_contact', True),
      'disabled': lambda prefs: setattr(prefs, 'whatsapp_enabled', False),
      'consent_missing': lambda prefs: setattr(prefs, 'whatsapp_consent_value', None),
    }
    for reason, mutate in cases.items():
      with self.subTest(reason=reason):
        CustomerContactPreferences.objects.filter(customer=self.customer).delete()
        delivery = self._pending(self.customer, WA, key=f'revoke-{reason}')
        prefs = CustomerContactPreferences.objects.get(customer=self.customer)
        mutate(prefs)
        prefs.save()
        provider = FakeWhatsAppProvider('success')
        self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SKIPPED)
        self.assertEqual(provider.sent, [])
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, reason))
        self.assertEqual(delivery.attempt_count, 0)
        self.assertIsNone(delivery.failure_code)

  def test_18_destination_changed_without_reconsent_is_skipped(self):
    delivery = self._pending(self.customer, WA)
    self.customer.phone = '1166660202'
    self.customer.save()
    provider = FakeWhatsAppProvider('success')
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SKIPPED)
    delivery.refresh_from_db()
    self.assertEqual(delivery.skip_reason, 'consent_destination_changed')
    self.assertEqual(provider.sent, [])

  def test_18b_destination_reconsented_to_other_value_is_destination_changed(self):
    delivery = self._pending(self.customer, WA)
    original = delivery.destination_snapshot
    self.customer.phone = '1166660202'
    self.customer.save()
    self._consent(self.customer, WA)  # B ahora es usable…
    provider = FakeWhatsAppProvider('success')
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SKIPPED)
    delivery.refresh_from_db()
    # …pero el Delivery era para A: no se envía a A ni se reescribe a B.
    self.assertEqual((delivery.skip_reason, delivery.destination_snapshot), ('destination_changed', original))
    self.assertEqual(provider.sent, [])

  def test_missing_phone_and_inactive_at_execution_are_skipped(self):
    wa = self._pending(self.customer, WA, key='wa')
    Customer.objects.filter(pk=self.customer.pk).update(phone='')
    self.assertEqual(execute_delivery(wa.pk, provider=FakeWhatsAppProvider()), S.SKIPPED)
    wa.refresh_from_db()
    self.assertEqual(wa.skip_reason, 'missing_phone')
    em = self._pending(self.customer, EMAIL, key='em')
    Customer.objects.filter(pk=self.customer.pk).update(is_active=False)
    self.assertEqual(execute_delivery(em.pk, provider=FakeEmailProvider()), S.SKIPPED)
    em.refresh_from_db()
    self.assertEqual(em.skip_reason, 'customer_inactive')

  def test_19_retryable_failure_schedules_retry(self):
    delivery = self._pending(self.customer, WA)
    before = dj_timezone.now()
    self.assertEqual(execute_delivery(delivery.pk, provider=FakeWhatsAppProvider('retryable_failure')), S.FAILED)
    delivery.refresh_from_db()
    self.assertEqual((delivery.status, delivery.failure_code, delivery.attempt_count), (S.FAILED, 'fake_temporary_error', 1))
    self.assertIsNotNone(delivery.failed_at)
    self.assertGreaterEqual(delivery.next_retry_at, before + dt.timedelta(seconds=60))
    self.assertLess(delivery.next_retry_at, before + dt.timedelta(seconds=120))
    # Reintento no vencido: no se ejecuta.
    self.assertIsNone(execute_delivery(delivery.pk, provider=FakeWhatsAppProvider('success')))

  def test_20_permanent_failure_has_no_retry(self):
    delivery = self._pending(self.customer, WA)
    self.assertEqual(execute_delivery(delivery.pk, provider=FakeWhatsAppProvider('permanent_failure')), S.FAILED)
    delivery.refresh_from_db()
    self.assertEqual((delivery.failure_code, delivery.next_retry_at), ('fake_rejected', None))
    self.assertIsNone(execute_delivery(delivery.pk, provider=FakeWhatsAppProvider('success')))

  def test_provider_exception_is_failed_without_retry(self):
    delivery = self._pending(self.customer, WA)
    provider = FakeWhatsAppProvider('success')
    with patch.object(provider, 'send', side_effect=TimeoutError('boom')):
      self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.FAILED)
    delivery.refresh_from_db()
    self.assertEqual((delivery.failure_code, delivery.next_retry_at), ('provider_exception', None))

  def test_21_max_attempts_respected(self):
    delivery = self._pending(self.customer, WA)
    provider = FakeWhatsAppProvider('retryable_failure')
    backoffs = []
    for attempt in (1, 2, 3):
      start = dj_timezone.now()
      self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.FAILED)
      delivery.refresh_from_db()
      self.assertEqual(delivery.attempt_count, attempt)
      if delivery.next_retry_at:
        backoffs.append(round((delivery.next_retry_at - start).total_seconds() / 60))
        self._make_due(delivery)
    self.assertEqual(backoffs, [1, 5])
    self.assertIsNone(delivery.next_retry_at)
    self.assertIsNone(execute_delivery(delivery.pk, provider=provider))
    self.assertEqual(len(provider.sent), 3)

  def test_22_retry_then_success(self):
    delivery = self._pending(self.customer, WA)
    provider = FlakyProvider(failures=2)
    execute_delivery(delivery.pk, provider=provider)
    self._make_due(delivery)
    execute_delivery(delivery.pk, provider=provider)
    self._make_due(delivery)
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SENT)
    delivery.refresh_from_db()
    self.assertEqual((delivery.status, delivery.attempt_count, delivery.provider_message_id), (S.SENT, 3, 'fake-final'))
    self.assertIsNone(delivery.failure_code)
    self.assertIsNone(delivery.next_retry_at)

  def test_retry_revalidates_consent(self):
    delivery = self._pending(self.customer, WA)
    execute_delivery(delivery.pk, provider=FakeWhatsAppProvider('retryable_failure'))
    self._make_due(delivery)
    self._consent(self.customer, WA, dnc=True)
    provider = FakeWhatsAppProvider('success')
    self.assertEqual(execute_delivery(delivery.pk, provider=provider), S.SKIPPED)
    delivery.refresh_from_db()
    self.assertEqual((delivery.status, delivery.skip_reason, delivery.next_retry_at), (S.SKIPPED, 'do_not_contact', None))
    self.assertEqual(provider.sent, [])

  def test_23_failed_delivery_does_not_affect_another(self):
    other = self._customer(self.biz, 'Beto', phone='1177770303', email='beto@example.com')
    bad = self._pending(self.customer, WA)
    good = self._pending(other, WA)
    D.objects.filter(pk__in=[bad.pk, good.pk]).update(created_at=dj_timezone.now() - dt.timedelta(minutes=5))
    real = deliveries.execute_delivery

    def flaky(delivery_id, **kwargs):
      if delivery_id == bad.pk:
        raise RuntimeError('db hiccup')
      return real(delivery_id, **kwargs)

    with patch.object(deliveries, 'execute_delivery', side_effect=flaky):
      result = retry_due_customer_deliveries(provider=FakeWhatsAppProvider('success'))
    self.assertEqual((result.errors, result.sent), (1, 1))
    good.refresh_from_db()
    bad.refresh_from_db()
    self.assertEqual((good.status, bad.status), (S.SENT, S.PENDING))

  def test_sweep_picks_due_retries_and_lost_pending_only(self):
    fresh = self._pending(self.customer, WA, key='fresh')
    other = self._customer(self.biz, 'Beto', phone='1177770303', email='beto@example.com')
    lost = self._pending(other, WA, key='lost')
    D.objects.filter(pk=lost.pk).update(created_at=dj_timezone.now() - dt.timedelta(minutes=5))
    retry = self._pending(other, EMAIL, key='retry')
    execute_delivery(retry.pk, provider=FakeEmailProvider('retryable_failure'))
    not_due = self._pending(self.customer, EMAIL, key='not-due')
    execute_delivery(not_due.pk, provider=FakeEmailProvider('retryable_failure'))
    self._make_due(retry)
    with override_settings(CUSTOMER_DELIVERY_FAKE_MODE='success'):
      result = retry_due_customer_deliveries()
    self.assertEqual((result.due, result.sent), (2, 2))
    for delivery, expected in ((fresh, S.PENDING), (lost, S.SENT), (retry, S.SENT), (not_due, S.FAILED)):
      delivery.refresh_from_db()
      self.assertEqual(delivery.status, expected, delivery.idempotency_key)

  def test_stale_processing_becomes_outcome_unknown_without_resend(self):
    delivery = self._pending(self.customer, WA)
    D.objects.filter(pk=delivery.pk).update(
      status=S.PROCESSING, attempt_count=1, last_attempt_at=dj_timezone.now() - dt.timedelta(minutes=30),
    )
    provider = FakeWhatsAppProvider('success')
    result = retry_due_customer_deliveries(provider=provider)
    self.assertEqual(result.stale, 1)
    delivery.refresh_from_db()
    self.assertEqual((delivery.status, delivery.failure_code, delivery.next_retry_at), (S.FAILED, 'outcome_unknown', None))
    self.assertEqual(provider.sent, [])

  def test_cancel_delivery(self):
    pending = self._pending(self.customer, WA, key='c1')
    self.assertTrue(cancel_delivery(pending.pk))
    pending.refresh_from_db()
    self.assertEqual(pending.status, S.CANCELLED)
    self.assertIsNone(execute_delivery(pending.pk, provider=FakeWhatsAppProvider()))
    sent = self._pending(self.customer, EMAIL, key='c2')
    execute_delivery(sent.pk, provider=FakeEmailProvider())
    self.assertFalse(cancel_delivery(sent.pk))

  def test_reminder_notified_at_is_untouched(self):
    reminder = CustomerReminder.objects.create(
      business=self.biz, customer=self.customer, title='Llamar', remind_at=dj_timezone.now() + dt.timedelta(hours=1),
    )
    delivery = self._pending(self.customer, WA, reminder=reminder)
    execute_delivery(delivery.pk, provider=FakeWhatsAppProvider())
    reminder.refresh_from_db()
    self.assertIsNone(reminder.notified_at)
    self.assertEqual(reminder.status, CustomerReminder.Status.PENDING)

  def test_provider_channel_mismatch_rejected(self):
    delivery = self._pending(self.customer, WA)
    with self.assertRaises(ValueError):
      execute_delivery(delivery.pk, provider=FakeEmailProvider())
    delivery.refresh_from_db()
    self.assertEqual(delivery.status, S.PENDING)

  def test_beat_and_tasks_registered(self):
    entries = [e for e in settings.CELERY_BEAT_SCHEDULE.values() if e['task'] == 'customers.retry_due_deliveries']
    self.assertEqual(len(entries), 1)
    from . import tasks

    delivery = self._pending(self.customer, WA)
    with override_settings(CUSTOMER_DELIVERY_FAKE_MODE='success'):
      self.assertEqual(tasks.execute_customer_delivery(str(delivery.pk)), S.SENT)
      self.assertEqual(tasks.retry_due_customer_deliveries()['sent'], 0)


# ── 16. Concurrencia (PostgreSQL real) ──────────────────────────────────────

class DeliveryConcurrencyTests(DeliveryMixin, TransactionTestCase):

  available_apps = list(settings.INSTALLED_APPS)

  def setUp(self):
    self.biz = _turnos_business(slug='delivery-concurrency')
    self.customer = self._customer(self.biz)

  def _run_in_thread(self, target):
    def wrapper():
      try:
        target()
      finally:
        connection.close()
    thread = threading.Thread(target=wrapper)
    thread.start()
    return thread

  def test_16_concurrent_execution_sends_once_while_sending(self):
    delivery = self._pending(self.customer, WA)
    inside, release = threading.Event(), threading.Event()
    sends = []

    class SlowProvider(FakeWhatsAppProvider):
      def send(self, message):
        sends.append(message)
        inside.set()
        release.wait(10)
        return super().send(message)

    results = {}
    thread = self._run_in_thread(lambda: results.setdefault('a', execute_delivery(delivery.pk, provider=SlowProvider())))
    try:
      self.assertTrue(inside.wait(10))
      # B llega mientras A está en provider.send: ve `processing` → no envía.
      results['b'] = execute_delivery(delivery.pk, provider=SlowProvider())
    finally:
      release.set()
      thread.join(10)
    self.assertEqual((results['a'], results['b']), (S.SENT, None))
    self.assertEqual(len(sends), 1)
    delivery.refresh_from_db()
    self.assertEqual((delivery.status, delivery.attempt_count), (S.SENT, 1))

  def test_16b_concurrent_claim_skips_locked_row(self):
    delivery = self._pending(self.customer, WA)
    inside, release = threading.Event(), threading.Event()
    real_gate = deliveries._gate

    def slow_gate(customer, channel):
      if threading.current_thread() is not threading.main_thread():
        inside.set()
        release.wait(10)
      return real_gate(customer, channel)

    providers = {'a': FakeWhatsAppProvider(), 'b': FakeWhatsAppProvider()}
    results = {}
    with patch.object(deliveries, '_gate', side_effect=slow_gate):
      thread = self._run_in_thread(lambda: results.setdefault('a', execute_delivery(delivery.pk, provider=providers['a'])))
      try:
        self.assertTrue(inside.wait(10))
        # A tiene la fila bloqueada (FOR UPDATE) dentro del claim: B la saltea.
        results['b'] = execute_delivery(delivery.pk, provider=providers['b'])
      finally:
        release.set()
        thread.join(10)
    self.assertEqual((results['a'], results['b']), (S.SENT, None))
    self.assertEqual((len(providers['a'].sent), len(providers['b'].sent)), (1, 0))

  def test_concurrent_prepare_same_key_creates_one(self):
    self._consent(self.customer, WA)
    barrier = threading.Barrier(2)
    ids = []

    def worker():
      barrier.wait(5)
      delivery, _ = self._prepare(self.customer, WA, key='race')
      ids.append(delivery.pk)

    threads = [self._run_in_thread(worker) for _ in range(2)]
    for thread in threads:
      thread.join(10)
    self.assertEqual(len(ids), 2)
    self.assertEqual(len(set(ids)), 1)
    self.assertEqual(D.objects.filter(idempotency_key='race').count(), 1)


# ── 21/24. API de auditoría ─────────────────────────────────────────────────

class CustomerDeliveriesAPITests(DeliveryMixin, APITestCase):

  def setUp(self):
    self.biz = _turnos_business(slug='delivery-api')
    self.customer = self._customer(self.biz, phone='1155550202', email='ana@dominio.com')

  def test_list_masked_contract_and_order(self):
    wa = self._pending(self.customer, WA, key='wa')
    execute_delivery(wa.pk, provider=FakeWhatsAppProvider())
    em = self._pending(self.customer, EMAIL, key='em')
    execute_delivery(em.pk, provider=FakeEmailProvider('permanent_failure'))
    _login(self.client, self.biz, 'viewer')
    resp = self.client.get(_deliveries_url(self.customer))
    self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
    self.assertEqual(resp.data['count'], 2)
    first, second = resp.data['results']
    self.assertEqual(first['id'], str(em.pk))
    self.assertEqual((first['status'], first['failure_code'], first['destination_masked']), ('failed', 'fake_rejected', 'a•••@dominio.com'))
    self.assertEqual((second['status'], second['destination_masked'], second['attempt_count']), ('sent', '•••• 0202', 1))
    self.assertEqual(second['channel_display'], 'WhatsApp')
    self.assertEqual(second['purpose_display'], 'Recordatorio de turno')
    self.assertEqual(second['max_attempts'], 3)
    self.assertIs(second['is_simulated'], True)
    body = str(resp.data)
    for secret in ('5491155550202', '1155550202', 'ana@dominio.com', 'idempotency', 'context', 'failure_message', 'rechazo'):
      self.assertNotIn(secret, body)
    self.assertTrue(second['sent_at'].endswith('-03:00'))

  def test_paginated(self):
    self._consent(self.customer, WA)
    for i in range(3):
      self._prepare(self.customer, WA, key=f'p{i}')
    _login(self.client, self.biz, 'viewer')
    resp = self.client.get(_deliveries_url(self.customer), {'limit': 2})
    self.assertEqual((resp.data['count'], len(resp.data['results'])), (3, 2))
    self.assertIsNotNone(resp.data['next'])

  def test_read_only_for_everyone(self):
    _login(self.client, self.biz, 'owner')
    for method in ('post', 'put', 'patch', 'delete'):
      with self.subTest(method=method):
        resp = getattr(self.client, method)(_deliveries_url(self.customer), {'channel': 'whatsapp'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
    self.assertFalse(D.objects.exists())

  def test_other_tenant_customer_is_404(self):
    biz2 = _turnos_business(slug='delivery-api-other')
    foreign = self._customer(biz2, 'Ajena')
    self._pending(foreign, WA)
    _login(self.client, self.biz, 'owner')
    self.assertEqual(self.client.get(_deliveries_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)

  def test_requires_view_customers(self):
    self.assertIn(self.client.get(_deliveries_url(self.customer)).status_code, (401, 403))
    _login(self.client, self.biz, 'viewer')
    with _without_permission('view_customers'):
      self.assertEqual(self.client.get(_deliveries_url(self.customer)).status_code, status.HTTP_403_FORBIDDEN)
    self.assertEqual(self.client.get(_deliveries_url(self.customer)).status_code, status.HTTP_200_OK)

  def test_roles_with_view_customers_can_read(self):
    self._pending(self.customer, WA)
    for role in ('owner', 'admin', 'manager', 'viewer'):
      with self.subTest(role=role):
        Membership.objects.filter(business=self.biz).delete()  # límite real de asientos
        _login(self.client, self.biz, role)
        resp = self.client.get(_deliveries_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['count'], 1)
