"""Concurrencia admin ↔ webhook ↔ expiración ↔ reservas (Slice 6B.1).

`TransactionTestCase` + threads con conexiones propias a PostgreSQL. El
admin entra por el endpoint real (`PATCH`/`DELETE`
`/api/v1/appointments/appointments/<id>/`), el webhook por el lifecycle de
`WebhookDelivery` (`process_delivery`) y las reservas por
`create_public_appointment`.

Para forzar cada orden de la carrera se retiene el lock de uno de los lados
dentro de su transacción (sleep en la sección crítica) y el otro arranca un
instante después. Invariantes verificados en todos los casos:
- nunca dos turnos ocupando el mismo recurso/horario;
- el PATCH nunca revierte `confirmed` / `expires_at` del webhook;
- `AppointmentPayment` nunca se modifica desde el admin.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone as dj_timezone
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.billing.models import WebhookDelivery
from apps.billing.webhook_lifecycle import process_delivery

from ..models import Appointment, AppointmentPayment, AppointmentProfessional, AppointmentSchedule
from ..services import admin_mutation, payment_confirmation
from ..services.booking import BookingError, create_public_appointment
from ..services.expiration import expire_due_appointment_holds
from .test_appointment_checkout import TOKEN_A, create_business, create_service
from .test_appointment_payment_webhook import WEBHOOK_SETTINGS, FakePaymentsSDK, mp_payment

User = get_user_model()
S = WebhookDelivery.ProcessingStatus
P = AppointmentPayment.Status
A = Appointment.Status

MONDAY = dt.date(2030, 3, 4)
assert MONDAY.weekday() == 0
ART = dt.timezone(dt.timedelta(hours=-3))


def at(hour, minute=0):
  return dt.datetime(2030, 3, 4, hour, minute, tzinfo=ART)


def run_concurrently(*targets, timeout=60):
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
  assert len(results) == len(targets), f'posible deadlock/cuelgue: {results}'
  return results


def delayed(fn, seconds=0.3):
  def run():
    time.sleep(seconds)
    return fn()
  return run


def hold_lock(module, name, seconds=1.0):
  """Retiene la sección crítica de `module.name` (dentro de su transacción)."""
  original = getattr(module, name)

  def slow(*args, **kwargs):
    time.sleep(seconds)
    return original(*args, **kwargs)

  return patch.object(module, name, side_effect=slow)


@override_settings(**WEBHOOK_SETTINGS)
class AdminMutationConcurrencyTests(TransactionTestCase):
  available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

  def setUp(self):
    cache.clear()
    self.biz = create_business(name='Admin Concurrencia', slug='admin-concurrencia', token=TOKEN_A)
    self.service = create_service(self.biz, deposit_value=Decimal('40'))
    self.p1 = AppointmentProfessional.objects.create(business=self.biz, name='Ana')
    self.p2 = AppointmentProfessional.objects.create(business=self.biz, name='Beto')
    for prof in (None, self.p1, self.p2):
      if prof:
        prof.services.add(self.service)
      AppointmentSchedule.objects.create(
        business=self.biz, professional=prof, weekday=MONDAY.weekday(), start_time='09:00', end_time='18:00',
      )
    self.user = User.objects.create_user(username='admin-conc', password='x')
    Membership.objects.create(user=self.user, business=self.biz, role='owner')

    self.mp = FakePaymentsSDK()
    patcher = patch('mercadopago.SDK', new=self.mp)
    patcher.start()
    self.addCleanup(patcher.stop)

  # ── fixtures ─────────────────────────────────────────────────────────
  def _appointment(self, *, professional=None, start=None, status=A.PENDING_PAYMENT, expires_in=dt.timedelta(minutes=5)):
    start = start or at(10)
    return Appointment.objects.create(
      business=self.biz, service=self.service, professional=professional or self.p1,
      customer_name='Cliente', customer_phone='1100000000',
      start_at=start, end_at=start + dt.timedelta(minutes=30), status=status,
      expires_at=(dj_timezone.now() + expires_in) if status == A.PENDING_PAYMENT else None,
      source=Appointment.Source.PUBLIC, service_name=self.service.name, service_duration_minutes=30,
      service_price=self.service.price, deposit_type=self.service.deposit_type,
      deposit_value=self.service.deposit_value,
    )

  def _payment(self, appt):
    pid = uuid.uuid4()
    return AppointmentPayment.objects.create(
      id=pid, business=self.biz, appointment=appt,
      external_reference=AppointmentPayment.build_external_reference(pid),
      amount=appt.deposit_amount, status=P.PENDING, provider_preference_id='PREF-ADM',
      checkout_url='https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=PREF-ADM',
    )

  def _approved_delivery(self, payment, *, payment_id=None, date_approved=None):
    self.mp.responses[TOKEN_A] = mp_payment(payment, date_approved=date_approved)
    return WebhookDelivery.objects.create(
      topic='payment', resource_id=payment_id or f'pay-{uuid.uuid4().hex[:10]}', signature_valid=True,
      flow='appointment', ref=payment.external_reference, x_request_id=f'x-{uuid.uuid4().hex}',
      processing_status=S.RECEIVED, received_at=dj_timezone.now(),
    )

  def _client(self):
    client = APIClient()
    client.force_authenticate(user=self.user)
    return client

  def _patch(self, appt, payload):
    return lambda: self._client().patch(f'/api/v1/appointments/appointments/{appt.pk}/', payload, format='json')

  def _delete(self, appt):
    return lambda: self._client().delete(f'/api/v1/appointments/appointments/{appt.pk}/')

  def _edit_form(self, appt, **overrides):
    """Payload del formulario de edición del panel (siempre manda servicio/profesional/horario)."""
    payload = {
      'service_id': str(appt.service_id),
      'professional_id': str(appt.professional_id) if appt.professional_id else None,
      'start_at': appt.start_at.isoformat(),
      'customer_name': appt.customer_name,
      'customer_phone': appt.customer_phone,
    }
    payload.update(overrides)
    return payload

  def _book(self, professional, start):
    return lambda: create_public_appointment(
      business=self.biz, service_id=str(self.service.id), professional_id=str(professional.id),
      start_at=start, customer_name='Otro', customer_phone='1199999999',
    )

  def _payment_state(self, payment):
    return tuple(AppointmentPayment.objects.filter(pk=payment.pk).values_list(
      'status', 'provider_payment_id', 'provider_status', 'amount', 'paid_at', 'review_reason',
      'provider_preference_id', 'checkout_url',
    ).get())

  def assertNoDoubleOccupancy(self):
    occupying = list(Appointment.objects.occupying().filter(business=self.biz))
    for i, a in enumerate(occupying):
      for b in occupying[i + 1:]:
        if a.professional_id == b.professional_id:
          self.assertFalse(
            a.start_at < b.end_at and b.start_at < a.end_at,
            f'doble ocupación: {a.pk} {a.start_at} / {b.pk} {b.start_at}',
          )

  # 1 + 8 + 9. admin PATCH vs webhook approved (ambos órdenes) ---------------------------------------
  def test_admin_patch_vs_webhook_webhook_holds_lock(self):
    appt = self._appointment()
    payment = self._payment(appt)
    delivery = self._approved_delivery(payment)
    form = self._edit_form(appt, notes='Trae su propio producto')  # formulario abierto con el turno pending

    with hold_lock(payment_confirmation, '_review_reason'):
      results = run_concurrently(lambda: process_delivery(delivery.pk), delayed(self._patch(appt, form)))

    self.assertEqual(results[0], S.PROCESSED)
    self.assertEqual(results[1].status_code, 200, results[1].content)
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.expires_at, appt.notes), (A.CONFIRMED, None, 'Trae su propio producto'))
    self.assertEqual(results[1].json()['status'], A.CONFIRMED)  # la respuesta refleja el estado real
    self.assertEqual(self._payment_state(payment)[0], P.APPROVED)
    self.assertNoDoubleOccupancy()

  def test_admin_patch_vs_webhook_admin_holds_lock(self):
    appt = self._appointment()
    payment = self._payment(appt)
    delivery = self._approved_delivery(payment)
    form = self._edit_form(appt, notes='Nota admin')

    with hold_lock(admin_mutation, '_apply_changes'):
      results = run_concurrently(self._patch(appt, form), delayed(lambda: process_delivery(delivery.pk)))

    self.assertEqual(results[0].status_code, 200, results[0].content)
    self.assertEqual(results[1], S.PROCESSED)
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.expires_at, appt.notes), (A.CONFIRMED, None, 'Nota admin'))
    self.assertEqual(self._payment_state(payment)[0], P.APPROVED)

  # 2. admin reprogramación vs webhook approved --------------------------------------------------------
  def test_admin_reschedule_vs_webhook_both_orders(self):
    for holder in ('webhook', 'admin'):
      with self.subTest(holder=holder):
        Appointment.objects.filter(business=self.biz).update(status=A.CANCELLED, expires_at=None)
        appt = self._appointment()
        payment = self._payment(appt)
        delivery = self._approved_delivery(payment)
        move = self._patch(appt, self._edit_form(appt, start_at=at(11).isoformat()))
        webhook = lambda: process_delivery(delivery.pk)  # noqa: E731

        if holder == 'webhook':
          with hold_lock(payment_confirmation, '_review_reason'):
            results = run_concurrently(webhook, delayed(move))
          webhook_result, admin_result = results[0], results[1]
        else:
          with hold_lock(admin_mutation, '_apply_changes'):
            results = run_concurrently(move, delayed(webhook))
          admin_result, webhook_result = results[0], results[1]

        self.assertEqual(webhook_result, S.PROCESSED)
        self.assertEqual(admin_result.status_code, 200, admin_result.content)
        appt.refresh_from_db()
        self.assertEqual((appt.status, appt.start_at, appt.expires_at), (A.CONFIRMED, at(11), None))
        state = self._payment_state(payment)
        self.assertEqual((state[0], state[3]), (P.APPROVED, Decimal('40.00')))
        self.assertEqual(AppointmentPayment.objects.filter(appointment=appt).count(), 1)  # sin Preference nueva
        self.assertNoDoubleOccupancy()

  # 3 + 12. admin cancelación vs webhook approved --------------------------------------------------------
  def test_admin_cancel_vs_webhook_webhook_first(self):
    appt = self._appointment()
    payment = self._payment(appt)
    delivery = self._approved_delivery(payment)

    with hold_lock(payment_confirmation, '_review_reason'):
      results = run_concurrently(lambda: process_delivery(delivery.pk), delayed(self._delete(appt)))

    self.assertEqual(results[0], S.PROCESSED)
    self.assertEqual(results[1].status_code, 204)
    appt.refresh_from_db()
    self.assertEqual(appt.status, A.CANCELLED)
    # El dinero cobrado sigue registrado y aplicado; sin refund automático.
    state = self._payment_state(payment)
    self.assertEqual((state[0], state[2]), (P.APPROVED, 'approved'))
    self.assertIsNotNone(state[4])

  def test_admin_cancel_vs_webhook_cancel_first(self):
    appt = self._appointment()
    payment = self._payment(appt)
    delivery = self._approved_delivery(payment)

    with hold_lock(admin_mutation, '_apply_changes'):
      results = run_concurrently(self._delete(appt), delayed(lambda: process_delivery(delivery.pk)))

    self.assertEqual(results[0].status_code, 204)
    self.assertEqual(results[1], S.PROCESSED)
    appt.refresh_from_db()
    payment.refresh_from_db()
    self.assertEqual(appt.status, A.CANCELLED)  # nunca se reabre
    self.assertEqual((payment.status, payment.review_reason), (P.REQUIRES_REVIEW, 'appointment_not_payable'))
    self.assertIsNotNone(payment.paid_at)

  # 4. admin cambio de profesional vs nueva reserva ------------------------------------------------------
  def test_admin_professional_change_vs_new_booking(self):
    for holder in ('admin', 'booking', None):
      with self.subTest(holder=holder):
        Appointment.objects.filter(business=self.biz).update(status=A.CANCELLED, expires_at=None)
        appt = self._appointment(professional=self.p1, status=A.CONFIRMED)
        move = self._patch(appt, self._edit_form(appt, professional_id=str(self.p2.id)))
        book = self._book(self.p2, at(10))

        if holder == 'admin':
          with hold_lock(admin_mutation, '_apply_changes'):
            res = run_concurrently(move, delayed(book))
          admin_res, booking_res = res[0], res[1]
        elif holder == 'booking':
          from ..services import booking as booking_module
          with hold_lock(booking_module, 'ensure_slot_available'):
            res = run_concurrently(book, delayed(move))
          booking_res, admin_res = res[0], res[1]
        else:
          res = run_concurrently(move, book)
          admin_res, booking_res = res[0], res[1]

        admin_ok = admin_res.status_code == 200
        booking_ok = not isinstance(booking_res, Exception)
        self.assertTrue(admin_ok != booking_ok, (admin_res.status_code, booking_res))
        if not booking_ok:
          self.assertIsInstance(booking_res, BookingError)
        if holder == 'admin':
          self.assertTrue(admin_ok)
        if holder == 'booking':
          self.assertTrue(booking_ok)
          self.assertEqual(admin_res.status_code, 400)
        p2_slot = Appointment.objects.occupying().filter(professional=self.p2, start_at=at(10))
        self.assertEqual(p2_slot.count(), 1)
        self.assertNoDoubleOccupancy()

  # 5. admin reprogramación vs expiración ----------------------------------------------------------------
  def test_admin_reschedule_vs_expiration(self):
    for holder in ('admin', 'expire'):
      with self.subTest(holder=holder):
        Appointment.objects.filter(business=self.biz).update(status=A.CANCELLED, expires_at=None)
        appt = self._appointment(expires_in=dt.timedelta(seconds=-2))  # hold ya vencido, status sin materializar
        payment = self._payment(appt)
        before = self._payment_state(payment)
        expires_at = appt.expires_at
        move = self._patch(appt, self._edit_form(appt, start_at=at(12).isoformat()))

        if holder == 'admin':
          with hold_lock(admin_mutation, '_apply_changes'):
            res = run_concurrently(move, delayed(expire_due_appointment_holds))
        else:
          res = run_concurrently(delayed(move), expire_due_appointment_holds)
        admin_res, expired = res[0], res[1]

        self.assertEqual(admin_res.status_code, 200, admin_res.content)
        self.assertEqual(expired, 1)
        appt.refresh_from_db()
        # El PATCH solo escribió el horario: nunca "revive" el pending_payment vencido.
        self.assertEqual((appt.status, appt.start_at, appt.expires_at), (A.EXPIRED, at(12), expires_at))
        self.assertEqual(self._payment_state(payment), before)

  # 6. dos admins reprogramando el mismo turno --------------------------------------------------------------
  def test_two_admins_rescheduling_same_appointment(self):
    appt = self._appointment(professional=self.p1, status=A.CONFIRMED)
    to_p2 = self._patch(appt, self._edit_form(appt, professional_id=str(self.p2.id), start_at=at(14).isoformat()))
    to_p1_later = self._patch(appt, self._edit_form(appt, start_at=at(15).isoformat()))

    with hold_lock(admin_mutation, '_apply_changes', seconds=0.8):
      res = run_concurrently(to_p2, delayed(to_p1_later))
    first, second = res[0], res[1]

    # El segundo request leyó el turno en P1, pero después del lock lo encuentra
    # en P2: re-lockea con el profesional actual y aplica contra ese estado.
    self.assertEqual((first.status_code, second.status_code), (200, 200), (first.content, second.content))
    appt.refresh_from_db()
    self.assertEqual((appt.professional_id, appt.start_at), (self.p1.id, at(15)))
    self.assertEqual(appt.status, A.CONFIRMED)
    self.assertEqual(Appointment.objects.filter(business=self.biz).count(), 1)
    self.assertNoDoubleOccupancy()

  def test_two_admins_moving_two_appointments_into_same_slot(self):
    a = self._appointment(professional=self.p1, start=at(10), status=A.CONFIRMED)
    b = self._appointment(professional=self.p2, start=at(11), status=A.CONFIRMED)
    target = at(16).isoformat()
    res = run_concurrently(
      self._patch(a, self._edit_form(a, professional_id=str(self.p2.id), start_at=target)),
      self._patch(b, self._edit_form(b, start_at=target)),
    )
    codes = sorted(r.status_code for r in res.values())
    self.assertEqual(codes, [200, 400], [r.content for r in res.values()])
    self.assertEqual(Appointment.objects.occupying().filter(professional=self.p2, start_at=at(16)).count(), 1)
    self.assertNoDoubleOccupancy()

  # 7. reprogramación cruzada entre profesionales no deadlockea ------------------------------------------------
  def test_cross_professional_reschedules_do_not_deadlock(self):
    for i in range(5):
      Appointment.objects.filter(business=self.biz).update(status=A.CANCELLED, expires_at=None)
      x = self._appointment(professional=self.p1, start=at(10), status=A.CONFIRMED)
      y = self._appointment(professional=self.p2, start=at(11), status=A.CONFIRMED)
      res = run_concurrently(
        self._patch(x, self._edit_form(x, professional_id=str(self.p2.id), start_at=at(13).isoformat())),
        self._patch(y, self._edit_form(y, professional_id=str(self.p1.id), start_at=at(14).isoformat())),
        timeout=30,
      )
      self.assertEqual([res[0].status_code, res[1].status_code], [200, 200], [r.content for r in res.values()])
      x.refresh_from_db()
      y.refresh_from_db()
      self.assertEqual((x.professional_id, y.professional_id), (self.p2.id, self.p1.id))
      self.assertNoDoubleOccupancy()

  # 10. Nunca dos confirmados: reactivación manual vs webhook del turno que ocupó el horario -------------------
  def test_manual_reactivation_vs_webhook_never_double_confirms(self):
    for holder in ('webhook', 'admin'):
      with self.subTest(holder=holder):
        Appointment.objects.filter(business=self.biz).update(status=A.CANCELLED, expires_at=None)
        old = self._appointment(professional=self.p1, status=A.CONFIRMED)
        Appointment.objects.filter(pk=old.pk).update(status=A.CANCELLED)
        paying = self._appointment(professional=self.p1)  # mismo horario, hold vigente
        delivery = self._approved_delivery(self._payment(paying))
        reactivate = self._patch(old, {'status': A.CONFIRMED})
        webhook = lambda: process_delivery(delivery.pk)  # noqa: E731

        if holder == 'webhook':
          with hold_lock(payment_confirmation, '_review_reason'):
            run_concurrently(webhook, delayed(reactivate))
        else:
          with hold_lock(admin_mutation, '_apply_changes'):
            run_concurrently(reactivate, delayed(webhook))

        confirmed = Appointment.objects.filter(professional=self.p1, start_at=at(10), status=A.CONFIRMED)
        self.assertEqual(confirmed.count(), 1)
        self.assertNoDoubleOccupancy()
