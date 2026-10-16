"""Mutaciones internas de `Appointment` contra el estado actual (Slice 6B.1).

PATCH/PUT/DELETE del panel pasan por `services.admin_mutation` (locks +
revalidación + `update_fields`). La concurrencia real vive en
`test_admin_mutation_concurrency.py`; acá se cubre el comportamiento con
formularios "viejos" (instancia leída antes de un cambio del webhook) y las
reglas sobre estados financieros.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone as dj_timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Membership

from ..models import Appointment, AppointmentPayment, AppointmentProfessional, AppointmentSchedule, AppointmentService
from ..serializers import AppointmentSerializer
from ..services.expiration import expire_due_appointment_holds
from .test_appointment_checkout import TOKEN_A, create_business, create_service
from .test_appointment_payment_webhook import WEBHOOK_SETTINGS, FakePaymentsSDK, mp_payment

User = get_user_model()
A = Appointment.Status
P = AppointmentPayment.Status
ART = dt.timezone(dt.timedelta(hours=-3))
MONDAY = dt.date(2030, 3, 4)


def at(hour, minute=0):
  return dt.datetime(2030, 3, 4, hour, minute, tzinfo=ART)


@override_settings(**WEBHOOK_SETTINGS)
class AdminMutationTests(APITestCase):
  def setUp(self):
    cache.clear()
    self.biz = create_business(name='Admin Biz', slug='admin-biz', token=TOKEN_A)
    self.service = create_service(self.biz, deposit_value=Decimal('40'))
    self.other_service = AppointmentService.objects.create(
      business=self.biz, name='Color', duration_minutes=60, price=Decimal('500'),
    )
    self.pro = AppointmentProfessional.objects.create(business=self.biz, name='Ana')
    self.pro.services.add(self.service, self.other_service)
    for prof in (None, self.pro):
      AppointmentSchedule.objects.create(
        business=self.biz, professional=prof, weekday=MONDAY.weekday(), start_time='09:00', end_time='18:00',
      )
    user = User.objects.create_user(username='admin-biz', password='x')
    Membership.objects.create(user=user, business=self.biz, role='owner')
    self.client.force_authenticate(user=user)
    self.mp = FakePaymentsSDK()
    patcher = patch('mercadopago.SDK', new=self.mp)
    patcher.start()
    self.addCleanup(patcher.stop)

  def _appointment(self, *, status=A.PENDING_PAYMENT, start=None, expires_in=dt.timedelta(minutes=5)):
    start = start or at(10)
    return Appointment.objects.create(
      business=self.biz, service=self.service, professional=self.pro,
      customer_name='Cliente', customer_phone='1100000000',
      start_at=start, end_at=start + dt.timedelta(minutes=30), status=status,
      expires_at=(dj_timezone.now() + expires_in) if status == A.PENDING_PAYMENT else None,
      source=Appointment.Source.PUBLIC, service_name=self.service.name, service_duration_minutes=30,
      service_price=self.service.price, deposit_type=self.service.deposit_type,
      deposit_value=self.service.deposit_value,
    )

  def _payment(self, appt, status=P.PENDING, **extra):
    pid = uuid.uuid4()
    return AppointmentPayment.objects.create(
      id=pid, business=self.biz, appointment=appt,
      external_reference=AppointmentPayment.build_external_reference(pid),
      amount=appt.deposit_amount, status=status, provider_preference_id='PREF-1', **extra,
    )

  def _confirm_via_webhook(self, payment):
    from apps.billing.payment_webhook import process_payment_event
    self.mp.responses[TOKEN_A] = mp_payment(payment)
    process_payment_event(f'pay-{payment.pk.hex[:8]}', flow='appointment', ref=payment.external_reference)

  def _form(self, appt, **overrides):
    payload = {
      'service_id': str(appt.service_id), 'professional_id': str(appt.professional_id),
      'start_at': appt.start_at.isoformat(), 'customer_name': appt.customer_name,
      'customer_phone': appt.customer_phone,
    }
    payload.update(overrides)
    return payload

  def _url(self, appt):
    return f'/api/v1/appointments/appointments/{appt.pk}/'

  def _payment_row(self, payment):
    return AppointmentPayment.objects.filter(pk=payment.pk).values().get()

  # 8 + 9. PATCH stale no revierte `confirmed` ni `expires_at` ---------------------------------------
  def test_stale_instance_patch_does_not_revert_webhook_confirmation(self):
    appt = self._appointment()
    payment = self._payment(appt)
    stale = Appointment.objects.get(pk=appt.pk)  # el admin abrió el formulario acá
    self.assertEqual(stale.status, A.PENDING_PAYMENT)

    self._confirm_via_webhook(payment)

    serializer = AppointmentSerializer(stale, data=self._form(stale, notes='nota'), partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    result = serializer.save()

    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.expires_at, appt.notes), (A.CONFIRMED, None, 'nota'))
    self.assertEqual((result.status, result.expires_at), (A.CONFIRMED, None))
    self.assertEqual(self._payment_row(payment)['status'], P.APPROVED)

  def test_stale_patch_via_api_keeps_confirmation(self):
    appt = self._appointment()
    payment = self._payment(appt)
    form = self._form(appt, customer_name='Cliente Editado')
    self._confirm_via_webhook(payment)

    res = self.client.patch(self._url(appt), form, format='json')

    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual(res.json()['status'], A.CONFIRMED)
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.expires_at, appt.customer_name), (A.CONFIRMED, None, 'Cliente Editado'))

  def test_patch_cannot_restore_pending_payment_or_expired(self):
    appt = self._appointment()
    self._confirm_via_webhook(self._payment(appt))
    for target in (A.PENDING_PAYMENT, A.EXPIRED):
      res = self.client.patch(self._url(appt), {'status': target}, format='json')
      self.assertEqual(res.status_code, 400, res.content)
      self.assertIn('status', res.json())
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.expires_at), (A.CONFIRMED, None))

  def test_echoing_current_system_status_is_a_noop(self):
    appt = self._appointment()
    res = self.client.patch(self._url(appt), {'status': A.PENDING_PAYMENT, 'notes': 'x'}, format='json')
    self.assertEqual(res.status_code, 200, res.content)
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.notes), (A.PENDING_PAYMENT, 'x'))
    self.assertIsNotNone(appt.expires_at)

  def test_stale_patch_does_not_revive_materialized_expiration(self):
    appt = self._appointment(expires_in=dt.timedelta(seconds=-1))
    stale = Appointment.objects.get(pk=appt.pk)
    self.assertEqual(expire_due_appointment_holds(), 1)
    serializer = AppointmentSerializer(stale, data={'notes': 'tarde'}, partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.notes), (A.EXPIRED, 'tarde'))
    self.assertIsNotNone(appt.expires_at)

  def test_only_changed_fields_are_written(self):
    appt = self._appointment()
    with patch.object(Appointment, 'save', autospec=True, side_effect=Appointment.save) as save:
      self.client.patch(self._url(appt), self._form(appt, notes='n'), format='json')
    self.assertEqual(sorted(save.call_args.kwargs['update_fields']), ['notes', 'updated_at'])

  def test_unchanged_slot_is_not_revalidated(self):
    """Editar datos del cliente no falla si el horario ya no está en la grilla actual."""
    appt = self._appointment(status=A.CONFIRMED)
    AppointmentSchedule.objects.filter(business=self.biz).update(start_time='12:00')
    res = self.client.patch(self._url(appt), self._form(appt, notes='ok'), format='json')
    self.assertEqual(res.status_code, 200, res.content)

  # Reactivación manual revalida solapamiento ------------------------------------------------------
  def test_reactivating_cancelled_into_occupied_slot_is_rejected(self):
    old = self._appointment(status=A.CANCELLED)
    self._appointment(status=A.CONFIRMED)
    res = self.client.patch(self._url(old), {'status': A.CONFIRMED}, format='json')
    self.assertEqual(res.status_code, 400, res.content)
    old.refresh_from_db()
    self.assertEqual(old.status, A.CANCELLED)

  def test_manual_confirmation_clears_hold(self):
    appt = self._appointment()
    res = self.client.patch(self._url(appt), {'status': A.CONFIRMED}, format='json')
    self.assertEqual(res.status_code, 200, res.content)
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.expires_at), (A.CONFIRMED, None))

  # 5 + 11. AppointmentPayment nunca cambia desde el PATCH genérico ---------------------------------
  def test_generic_patch_never_touches_payment(self):
    appt = self._appointment()
    payment = self._payment(appt, status=P.REQUIRES_REVIEW, provider_payment_id='555', provider_status='approved',
                            review_reason='slot_conflict', paid_at=dj_timezone.now())
    before = self._payment_row(payment)
    res = self.client.patch(self._url(appt), {
      'notes': 'x', 'payments': [], 'payment_status': 'approved', 'status_payment': 'approved',
      'review_reason': '', 'paid_at': None, 'deposit_value': '0', 'service_price': '0',
    }, format='json')
    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual(self._payment_row(payment), before)
    appt.refresh_from_db()
    self.assertEqual(appt.deposit_value, Decimal('40.00'))
    self.assertNotIn('payments', res.json())

  def test_cancel_preserves_payment_traceability(self):
    appt = self._appointment()
    payment = self._payment(appt)
    self._confirm_via_webhook(payment)
    before = self._payment_row(payment)
    res = self.client.delete(self._url(appt))
    self.assertEqual(res.status_code, 204)
    appt.refresh_from_db()
    self.assertEqual(appt.status, A.CANCELLED)
    self.assertEqual(self._payment_row(payment), before)
    self.assertEqual(before['status'], P.APPROVED)

  def test_cancel_is_idempotent(self):
    appt = self._appointment(status=A.CANCELLED)
    self.assertEqual(self.client.delete(self._url(appt)).status_code, 204)
    appt.refresh_from_db()
    self.assertEqual(appt.status, A.CANCELLED)

  # 6. Reprogramación de un turno pagado ------------------------------------------------------------
  def test_reschedule_paid_appointment_keeps_payment_and_snapshot(self):
    appt = self._appointment()
    payment = self._payment(appt)
    self._confirm_via_webhook(payment)
    before = self._payment_row(payment)
    self.service.price = Decimal('999')
    self.service.deposit_value = Decimal('99')
    self.service.save()

    res = self.client.patch(self._url(appt), self._form(appt, start_at=at(15).isoformat()), format='json')

    self.assertEqual(res.status_code, 200, res.content)
    appt.refresh_from_db()
    self.assertEqual((appt.status, appt.start_at, appt.end_at), (A.CONFIRMED, at(15), at(15, 30)))
    # Mover no re-cotiza: snapshot (y seña) intactos, pago intacto, sin Preference nueva.
    self.assertEqual((appt.service_price, appt.deposit_value), (Decimal('100.00'), Decimal('40.00')))
    self.assertEqual(self._payment_row(payment), before)
    self.assertEqual(AppointmentPayment.objects.filter(appointment=appt).count(), 1)

  def test_reschedule_paid_appointment_into_occupied_slot_is_rejected(self):
    appt = self._appointment()
    self._confirm_via_webhook(self._payment(appt))
    self._appointment(status=A.CONFIRMED, start=at(15))
    res = self.client.patch(self._url(appt), self._form(appt, start_at=at(15).isoformat()), format='json')
    self.assertEqual(res.status_code, 400)
    appt.refresh_from_db()
    self.assertEqual(appt.start_at, at(10))

  def test_service_change_rejected_when_payment_active_or_captured(self):
    for status in (P.PENDING, P.UNCERTAIN, P.CREATING, P.APPROVED, P.REQUIRES_REVIEW):
      with self.subTest(status=status):
        appt = self._appointment(status=A.CONFIRMED, start=at(11))
        extra = {'provider_payment_id': f'pp-{status}'} if status in AppointmentPayment.CAPTURED_STATUSES else {}
        self._payment(appt, status=status, **extra)
        res = self.client.patch(self._url(appt), self._form(appt, service_id=str(self.other_service.id)), format='json')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('service_id', res.json())
        appt.refresh_from_db()
        self.assertEqual(appt.service_id, self.service.id)
        appt.delete()

  def test_service_change_allowed_without_payment_and_resnapshots(self):
    appt = self._appointment(status=A.CONFIRMED)
    self._payment(appt, status=P.ERROR)  # intento fallido: no es dinero ni intento activo
    res = self.client.patch(self._url(appt), self._form(appt, service_id=str(self.other_service.id)), format='json')
    self.assertEqual(res.status_code, 200, res.content)
    appt.refresh_from_db()
    self.assertEqual((appt.service_name, appt.service_duration_minutes, appt.end_at), ('Color', 60, at(11)))
