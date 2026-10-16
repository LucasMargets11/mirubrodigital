"""Concurrencia real del webhook `flow=appointment` (Slice 6B, tests 19-23).

`TransactionTestCase` + threads con conexiones propias a PostgreSQL. Se
ejercitan los locks reales (profesional/Business → Appointment →
AppointmentPayment) contra:
- otro worker procesando el mismo pago (dos notificaciones distintas);
- el worker de expiración de holds;
- una reserva pública nueva sobre el mismo horario.

Invariantes: nunca dos turnos ocupando el mismo recurso/horario, nunca dos
aplicaciones del mismo pago, el dinero cobrado siempre queda registrado.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone as dj_timezone

from apps.billing.models import WebhookDelivery
from apps.billing.webhook_lifecycle import process_delivery

from ..models import Appointment, AppointmentPayment, AppointmentProfessional, AppointmentSchedule
from ..services import payment_confirmation
from ..services.booking import BookingError, create_public_appointment
from ..services.expiration import expire_due_appointment_holds
from .test_appointment_checkout import TOKEN_A, create_business, create_service
from .test_appointment_payment_webhook import WEBHOOK_SETTINGS, FakePaymentsSDK, mp_payment

S = WebhookDelivery.ProcessingStatus
P = AppointmentPayment.Status
MONDAY = dt.date(2030, 3, 4)
assert MONDAY.weekday() == 0
SLOT_START = dt.datetime(2030, 3, 4, 13, 0, tzinfo=dt.timezone.utc)  # 10:00 -03:00


def run_concurrently(*targets, timeout=60):
  """Arranca todos los targets juntos (barrier); devuelve {índice: resultado|excepción}."""
  barrier = threading.Barrier(len(targets))
  results: dict[int, object] = {}
  lock = threading.Lock()

  def wrap(i, fn):
    try:
      barrier.wait()
      value = fn()
    except Exception as exc:  # noqa: BLE001 — se inspecciona en el test
      value = exc
    finally:
      connections.close_all()
    with lock:
      results[i] = value

  threads = [threading.Thread(target=wrap, args=(i, fn)) for i, fn in enumerate(targets)]
  for t in threads:
    t.start()
  for t in threads:
    t.join(timeout=timeout)
  assert len(results) == len(targets), results
  return results


@override_settings(**WEBHOOK_SETTINGS)
class ConcurrentAppointmentWebhookTests(TransactionTestCase):
  available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

  def setUp(self):
    cache.clear()
    self.biz = create_business(name='Concurrencia Webhook', slug='concurrencia-webhook', token=TOKEN_A)
    self.service = create_service(self.biz, deposit_value=Decimal('40'))
    self.professional = AppointmentProfessional.objects.create(business=self.biz, name='Ana')
    self.professional.services.add(self.service)
    for prof in (None, self.professional):
      AppointmentSchedule.objects.create(
        business=self.biz, professional=prof, weekday=MONDAY.weekday(), start_time='09:00', end_time='18:00',
      )
    self.mp = FakePaymentsSDK()
    patcher = patch('mercadopago.SDK', new=self.mp)
    patcher.start()
    self.addCleanup(patcher.stop)

    self.outcomes: list = []
    self.outcomes_lock = threading.Lock()
    original = payment_confirmation.apply_provider_payment

    def spy(**kwargs):
      outcome = original(**kwargs)
      with self.outcomes_lock:
        self.outcomes.append(outcome.result)
      return outcome

    spy_patch = patch.object(payment_confirmation, 'apply_provider_payment', side_effect=spy)
    spy_patch.start()
    self.addCleanup(spy_patch.stop)

  def _appointment(self, *, expires_at):
    return Appointment.objects.create(
      business=self.biz, service=self.service, professional=self.professional,
      customer_name='Cliente', customer_phone='1100000000',
      start_at=SLOT_START, end_at=SLOT_START + dt.timedelta(minutes=30),
      status=Appointment.Status.PENDING_PAYMENT, expires_at=expires_at, source=Appointment.Source.PUBLIC,
      service_name=self.service.name, service_duration_minutes=30, service_price=self.service.price,
      deposit_type=self.service.deposit_type, deposit_value=self.service.deposit_value,
    )

  def _payment(self, appt):
    pid = uuid.uuid4()
    return AppointmentPayment.objects.create(
      id=pid, business=self.biz, appointment=appt,
      external_reference=AppointmentPayment.build_external_reference(pid),
      amount=appt.deposit_amount, status=P.PENDING, provider_preference_id='PREF-C',
    )

  def _delivery(self, payment, payment_id='9001'):
    return WebhookDelivery.objects.create(
      topic='payment', resource_id=payment_id, signature_valid=True, flow='appointment',
      ref=payment.external_reference, x_request_id=f'x-{uuid.uuid4().hex}',
      processing_status=S.RECEIVED, received_at=dj_timezone.now(),
    )

  def _slow_locked_section(self, seconds):
    """Retiene los locks del webhook un rato (dentro de la transacción)."""
    original = payment_confirmation._review_reason

    def slow(**kwargs):
      time.sleep(seconds)
      return original(**kwargs)

    return patch.object(payment_confirmation, '_review_reason', side_effect=slow)

  def _occupying_slot(self):
    return Appointment.objects.occupying().filter(
      business=self.biz, professional=self.professional,
      start_at__lt=SLOT_START + dt.timedelta(minutes=30), end_at__gt=SLOT_START,
    )

  # 19 + 23. dos webhooks concurrentes del mismo pago → una sola aplicación ------------------------
  def test_concurrent_webhooks_apply_payment_once(self):
    appt = self._appointment(expires_at=dj_timezone.now() + dt.timedelta(minutes=5))
    payment = self._payment(appt)

    def slow_fetch(payment_id):
      time.sleep(0.2)  # ambos workers pasan el fetch y compiten por los locks
      return mp_payment(payment)

    self.mp.responses[TOKEN_A] = slow_fetch
    d1, d2 = self._delivery(payment), self._delivery(payment)

    results = run_concurrently(lambda: process_delivery(d1.pk), lambda: process_delivery(d2.pk))

    self.assertCountEqual(results.values(), [S.PROCESSED, S.PROCESSED], results)
    self.assertEqual(sorted(self.outcomes), ['already_applied', 'applied'])
    payment.refresh_from_db()
    appt.refresh_from_db()
    self.assertEqual((payment.status, payment.provider_payment_id), (P.APPROVED, '9001'))
    self.assertEqual(appt.status, Appointment.Status.CONFIRMED)
    self.assertEqual(AppointmentPayment.objects.filter(provider_payment_id='9001').count(), 1)

  def test_same_delivery_claimed_by_two_workers_runs_once(self):
    appt = self._appointment(expires_at=dj_timezone.now() + dt.timedelta(minutes=5))
    payment = self._payment(appt)

    def slow_fetch(payment_id):
      time.sleep(0.3)
      return mp_payment(payment)

    self.mp.responses[TOKEN_A] = slow_fetch
    delivery = self._delivery(payment)

    results = run_concurrently(lambda: process_delivery(delivery.pk), lambda: process_delivery(delivery.pk))

    self.assertCountEqual(results.values(), [S.PROCESSED, None], results)
    self.assertEqual(self.outcomes, ['applied'])

  # 20. webhook vs expiración ---------------------------------------------------------------------
  def test_webhook_vs_expiration_worker(self):
    expires_at = dj_timezone.now() - dt.timedelta(seconds=2)
    appt = self._appointment(expires_at=expires_at)
    payment = self._payment(appt)
    self.mp.responses[TOKEN_A] = mp_payment(payment, date_approved=expires_at - dt.timedelta(seconds=30))
    delivery = self._delivery(payment)

    def expire_later():
      time.sleep(0.3)  # llega mientras el webhook tiene el turno lockeado
      return expire_due_appointment_holds()

    with self._slow_locked_section(1.0):
      results = run_concurrently(lambda: process_delivery(delivery.pk), expire_later)

    self.assertEqual(results[0], S.PROCESSED, results)
    self.assertEqual(results[1], 0, 'el UPDATE re-evalúa el WHERE tras el lock: el turno ya estaba confirmado')
    appt.refresh_from_db()
    payment.refresh_from_db()
    self.assertEqual((appt.status, appt.expires_at), (Appointment.Status.CONFIRMED, None))
    self.assertEqual(payment.status, P.APPROVED)

  def test_webhook_vs_expiration_worker_any_order(self):
    for _ in range(3):
      expires_at = dj_timezone.now() - dt.timedelta(seconds=2)
      appt = self._appointment(expires_at=expires_at)
      payment = self._payment(appt)
      self.mp.responses[TOKEN_A] = mp_payment(payment, date_approved=expires_at - dt.timedelta(seconds=30))
      delivery = self._delivery(payment, payment_id=f'pay-{appt.pk.hex[:8]}')

      results = run_concurrently(lambda: process_delivery(delivery.pk), expire_due_appointment_holds)

      self.assertEqual(results[0], S.PROCESSED, results)
      appt.refresh_from_db()
      payment.refresh_from_db()
      # Aprobado dentro de la ventana: confirma con o sin materialización previa de `expired`.
      self.assertEqual(appt.status, Appointment.Status.CONFIRMED)
      self.assertEqual(payment.status, P.APPROVED)
      Appointment.objects.filter(pk=appt.pk).update(status=Appointment.Status.CANCELLED)

  # 21 + 22. webhook vs nueva reserva del horario liberado ---------------------------------------------
  def _book_same_slot(self):
    return create_public_appointment(
      business=self.biz, service_id=str(self.service.id), professional_id=str(self.professional.id),
      start_at=SLOT_START, customer_name='Otro cliente', customer_phone='1199999999',
    )

  def test_webhook_holding_lock_blocks_new_booking(self):
    expires_at = dj_timezone.now() - dt.timedelta(seconds=2)
    appt = self._appointment(expires_at=expires_at)
    payment = self._payment(appt)
    self.mp.responses[TOKEN_A] = mp_payment(payment, date_approved=expires_at - dt.timedelta(seconds=30))
    delivery = self._delivery(payment)

    def book_later():
      time.sleep(0.3)
      return self._book_same_slot()

    with self._slow_locked_section(1.0):
      results = run_concurrently(lambda: process_delivery(delivery.pk), book_later)

    self.assertEqual(results[0], S.PROCESSED)
    self.assertIsInstance(results[1], BookingError, results)
    appt.refresh_from_db()
    self.assertEqual(appt.status, Appointment.Status.CONFIRMED)
    self.assertEqual(list(self._occupying_slot()), [appt])

  def test_new_booking_first_then_late_webhook_requires_review(self):
    expires_at = dj_timezone.now() - dt.timedelta(seconds=2)
    appt = self._appointment(expires_at=expires_at)
    payment = self._payment(appt)
    self.mp.responses[TOKEN_A] = mp_payment(payment, date_approved=expires_at - dt.timedelta(seconds=30))

    other = self._book_same_slot()  # el hold vencido liberó el horario
    self.assertEqual(process_delivery(self._delivery(payment).pk), S.PROCESSED)

    payment.refresh_from_db()
    appt.refresh_from_db()
    self.assertEqual((payment.status, payment.review_reason), (P.REQUIRES_REVIEW, 'slot_conflict'))
    self.assertEqual(appt.status, Appointment.Status.EXPIRED)
    self.assertEqual(list(self._occupying_slot()), [other])

  def test_webhook_vs_new_booking_any_order_never_double_books(self):
    for i in range(4):
      expires_at = dj_timezone.now() - dt.timedelta(seconds=2)
      appt = self._appointment(expires_at=expires_at)
      payment = self._payment(appt)
      self.mp.responses[TOKEN_A] = mp_payment(payment, date_approved=expires_at - dt.timedelta(seconds=30))
      delivery = self._delivery(payment, payment_id=f'race-{i}')

      results = run_concurrently(lambda: process_delivery(delivery.pk), self._book_same_slot)

      self.assertEqual(results[0], S.PROCESSED, results)
      payment.refresh_from_db()
      appt.refresh_from_db()
      occupying = list(self._occupying_slot())
      self.assertEqual(len(occupying), 1, occupying)
      self.assertIn(payment.status, AppointmentPayment.CAPTURED_STATUSES)  # el dinero quedó registrado
      if isinstance(results[1], BookingError):
        self.assertEqual((appt.status, payment.status), (Appointment.Status.CONFIRMED, P.APPROVED))
      else:
        self.assertEqual((payment.status, payment.review_reason), (P.REQUIRES_REVIEW, 'slot_conflict'))
        self.assertEqual(occupying, [results[1]])
      # Liberar el horario para la próxima vuelta.
      Appointment.objects.filter(business=self.biz).update(status=Appointment.Status.CANCELLED, expires_at=None)
