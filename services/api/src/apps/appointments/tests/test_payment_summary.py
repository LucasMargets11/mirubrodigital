"""Slice 7B.3: estado operativo efectivo + resumen financiero en el panel interno.

`effective_status` y `payment_summary` salen del serializer interno
(`/api/v1/appointments/appointments/`), derivados server-side del estado
persistido de Appointment/AppointmentPayment — nunca de BusinessNotification.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone as dj_timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.notifications.models import BusinessNotification

from ..models import Appointment, AppointmentPayment
from ..public_serializers import PublicAppointmentBookingStatusSerializer
from ..services.notifications import notify_appointment_payment_review
from ..services.payment_summary import representative_payment
from .test_appointment_checkout import create_appointment, create_business, create_service

User = get_user_model()
P = AppointmentPayment.Status
R = AppointmentPayment.ReviewReason
LIST_URL = '/api/v1/appointments/appointments/'
NOTIF_URL = '/api/v1/notifications/business/'
# Valores distintivos: no pueden aparecer por casualidad en uuids/fechas.
PREF_ID = 'PREF-SECRET-7B3'
MP_PAYMENT_ID = '5566778899'


def detail_url(appt: Appointment) -> str:
  return f'{LIST_URL}{appt.pk}/'


def public_url(appt: Appointment) -> str:
  return f'/api/v1/appointments/public/{appt.business.slug}/bookings/{appt.public_token}/'


class _Base(APITestCase):
  def setUp(self):
    self.biz = create_business(name='Biz A', slug='biz-a-7b3')
    self.service = create_service(self.biz)
    self.user = User.objects.create_user(username='owner-a-7b3', password='x')
    Membership.objects.create(user=self.user, business=self.biz, role='owner')
    self.client.force_authenticate(self.user)
    self._seq = 0

  def make_appt(self, **kw) -> Appointment:
    return create_appointment(self.biz, self.service, **kw)

  def pay(self, appt, status_, *, minutes_ago=0, amount=Decimal('30.00'), review_reason='', paid=None):
    """Crea un intento con `created_at` controlado (orden entre intentos)."""
    self._seq += 1
    pid = uuid.uuid4()
    captured = status_ in AppointmentPayment.CAPTURED_STATUSES
    payment = AppointmentPayment.objects.create(
      id=pid, business=appt.business, appointment=appt,
      external_reference=AppointmentPayment.build_external_reference(pid),
      amount=amount, status=status_,
      provider_preference_id=f'{PREF_ID}-{self._seq}',
      provider_payment_id=f'{MP_PAYMENT_ID}{self._seq}' if captured else None,
      checkout_url='https://mp.example/checkout/secret-7b3',
      failure_reason='mp_uncertain:504' if status_ == P.UNCERTAIN else '',
      review_reason=review_reason,
      paid_at=paid if paid is not None else (dj_timezone.now() if captured else None),
    )
    AppointmentPayment.objects.filter(pk=pid).update(
      created_at=dj_timezone.now() - dt.timedelta(minutes=minutes_ago),
    )
    payment.refresh_from_db()
    return payment

  def get_row(self, appt):
    res = self.client.get(detail_url(appt))
    self.assertEqual(res.status_code, 200, res.content)
    return res.data


class EffectiveStatusTests(_Base):
  # 1. pending_payment vigente
  def test_pending_payment_in_window(self):
    appt = self.make_appt()
    row = self.get_row(appt)
    self.assertEqual(row['status'], 'pending_payment')
    self.assertEqual(row['effective_status'], 'pending_payment')
    self.assertEqual(row['effective_status_display'], 'Pendiente de pago')
    self.assertIsNotNone(row['expires_at'])

  # 2. pending_payment vencido → expired sin mutar DB
  def test_expired_hold_is_expired_without_mutation(self):
    appt = self.make_appt(expires_in=-dt.timedelta(minutes=1))
    before = Appointment.objects.filter(pk=appt.pk).values('status', 'expires_at', 'updated_at').get()
    row = self.get_row(appt)
    self.assertEqual(row['effective_status'], 'expired')
    self.assertEqual(row['effective_status_display'], 'Vencido')
    self.assertEqual(row['status'], 'pending_payment')
    list_row = self.client.get(LIST_URL).data[0]
    self.assertEqual(list_row['effective_status'], 'expired')
    after = Appointment.objects.filter(pk=appt.pk).values('status', 'expires_at', 'updated_at').get()
    self.assertEqual(before, after)

  def test_status_filter_uses_effective_status(self):
    live = self.make_appt()
    stale = self.make_appt(expires_in=-dt.timedelta(minutes=1))
    Appointment.objects.filter(pk=stale.pk).update(start_at=live.start_at + dt.timedelta(hours=1),
                                                   end_at=live.end_at + dt.timedelta(hours=1))
    normalized = self.make_appt(status_=Appointment.Status.EXPIRED)
    Appointment.objects.filter(pk=normalized.pk).update(start_at=live.start_at + dt.timedelta(hours=2),
                                                        end_at=live.end_at + dt.timedelta(hours=2))
    confirmed = self.make_appt(status_=Appointment.Status.CONFIRMED)
    Appointment.objects.filter(pk=confirmed.pk).update(start_at=live.start_at + dt.timedelta(hours=3),
                                                       end_at=live.end_at + dt.timedelta(hours=3))

    def ids(status_):
      res = self.client.get(LIST_URL, {'status': status_})
      self.assertEqual(res.status_code, 200)
      return {r['id'] for r in res.data}

    self.assertEqual(ids('pending_payment'), {str(live.pk)})
    self.assertEqual(ids('expired'), {str(stale.pk), str(normalized.pk)})
    self.assertEqual(ids('confirmed'), {str(confirmed.pk)})


class PaymentSummaryTests(_Base):
  # 3. confirmed sin payment → null
  def test_confirmed_without_payment_has_null_summary(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED, source=Appointment.Source.MANUAL)
    row = self.get_row(appt)
    self.assertEqual(row['effective_status'], 'confirmed')
    self.assertIsNone(row['payment_summary'])

  # 4. approved
  def test_approved_summary(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED)
    paid = dj_timezone.now() - dt.timedelta(hours=1)
    self.pay(appt, P.APPROVED, paid=paid)
    summary = self.get_row(appt)['payment_summary']
    self.assertEqual(summary['status'], 'approved')
    self.assertEqual(summary['amount'], '30.00')
    self.assertEqual(summary['currency'], 'ARS')
    self.assertIsNotNone(summary['paid_at'])
    self.assertFalse(summary['requires_review'])
    self.assertIsNone(summary['review_reason'])
    self.assertEqual(set(summary), {'status', 'amount', 'currency', 'paid_at', 'requires_review', 'review_reason'})

  # 5. el importe sale del snapshot del intento, nunca del servicio actual
  def test_amount_comes_from_payment_snapshot(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED)
    self.pay(appt, P.APPROVED, amount=Decimal('30.00'))
    self.service.price = Decimal('999')
    self.service.deposit_value = Decimal('500')
    self.service.save()
    self.assertEqual(self.get_row(appt)['payment_summary']['amount'], '30.00')

  # 6. requires_review gana sobre cualquier otro intento (aun más nuevo)
  def test_requires_review_has_priority(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED)
    self.pay(appt, P.REQUIRES_REVIEW, minutes_ago=30, review_reason=R.APPOINTMENT_ALREADY_CONFIRMED)
    self.pay(appt, P.APPROVED, minutes_ago=10)
    self.pay(appt, P.REJECTED, minutes_ago=1)
    summary = self.get_row(appt)['payment_summary']
    self.assertEqual(summary['status'], 'requires_review')
    self.assertTrue(summary['requires_review'])
    self.assertEqual(summary['review_reason'], 'appointment_already_confirmed')

  # 7. approved gana sobre un rejected (viejo o nuevo)
  def test_approved_beats_rejected(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED)
    self.pay(appt, P.REJECTED, minutes_ago=20)
    self.pay(appt, P.APPROVED, minutes_ago=10)
    self.pay(appt, P.ERROR, minutes_ago=1)
    self.assertEqual(self.get_row(appt)['payment_summary']['status'], 'approved')

  # 8. uncertain
  def test_uncertain_is_represented(self):
    appt = self.make_appt()
    self.pay(appt, P.REJECTED, minutes_ago=5)
    self.pay(appt, P.UNCERTAIN, minutes_ago=3)
    summary = self.get_row(appt)['payment_summary']
    self.assertEqual(summary['status'], 'uncertain')
    self.assertFalse(summary['requires_review'])
    self.assertIsNone(summary['paid_at'])

  # 9. varios intentos: activo > terminal más reciente; sin activo → el último
  def test_multiple_attempts_choose_correct_one(self):
    appt = self.make_appt()
    self.pay(appt, P.REJECTED, minutes_ago=30)
    self.pay(appt, P.PENDING, minutes_ago=20)
    self.pay(appt, P.ERROR, minutes_ago=1)
    self.assertEqual(self.get_row(appt)['payment_summary']['status'], 'pending')

    other = self.make_appt()
    Appointment.objects.filter(pk=other.pk).update(start_at=other.start_at + dt.timedelta(hours=2),
                                                   end_at=other.end_at + dt.timedelta(hours=2))
    self.pay(other, P.REJECTED, minutes_ago=30)
    self.pay(other, P.CANCELLED, minutes_ago=2)
    self.pay(other, P.ERROR, minutes_ago=10)
    self.assertEqual(self.get_row(other)['payment_summary']['status'], 'cancelled')

  def test_same_rule_for_public_payment_status(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED)
    self.pay(appt, P.APPROVED, minutes_ago=10)
    review = self.pay(appt, P.REQUIRES_REVIEW, minutes_ago=5, review_reason=R.SLOT_CONFLICT)
    self.assertEqual(representative_payment(appt), review)
    self.assertEqual(PublicAppointmentBookingStatusSerializer(appt).data['payment_status'], 'requires_review')

  # 10. nunca ids de provider / referencias / checkout / failure_reason
  def test_provider_ids_are_not_exposed(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED)
    payment = self.pay(appt, P.REQUIRES_REVIEW, review_reason=R.APPROVED_AFTER_EXPIRY)
    uncertain_appt = self.make_appt()
    Appointment.objects.filter(pk=uncertain_appt.pk).update(
      start_at=appt.start_at + dt.timedelta(hours=2), end_at=appt.end_at + dt.timedelta(hours=2))
    uncertain = self.pay(uncertain_appt, P.UNCERTAIN)
    for body in (self.client.get(LIST_URL).content.decode(), self.client.get(detail_url(appt)).content.decode()):
      for secret in (
        payment.provider_payment_id, payment.provider_preference_id, payment.external_reference,
        uncertain.provider_preference_id, uncertain.external_reference,
        'secret-7b3', 'mp_uncertain', 'external_reference', 'provider_payment_id', 'checkout_url',
        'failure_reason',
      ):
        self.assertNotIn(secret, body)


class TenantIsolationTests(_Base):
  # 11. Business A no ve payment summary de B
  def test_business_a_does_not_see_b(self):
    biz_b = create_business(name='Biz B', slug='biz-b-7b3')
    appt_b = create_appointment(biz_b, create_service(biz_b), status_=Appointment.Status.CONFIRMED)
    payment_b = self.pay(appt_b, P.REQUIRES_REVIEW, review_reason=R.SLOT_CONFLICT)
    own = self.make_appt()

    res = self.client.get(LIST_URL)
    self.assertEqual([r['id'] for r in res.data], [str(own.pk)])
    self.assertNotIn(payment_b.provider_payment_id, res.content.decode())
    self.assertNotIn('requires_review', res.content.decode())
    self.assertEqual(self.client.get(detail_url(appt_b)).status_code, 404)

    user_b = User.objects.create_user(username='owner-b-7b3', password='x')
    Membership.objects.create(user=user_b, business=biz_b, role='owner')
    self.client.force_authenticate(user_b)
    rows = self.client.get(LIST_URL).data
    self.assertEqual([r['id'] for r in rows], [str(appt_b.pk)])
    self.assertEqual(rows[0]['payment_summary']['status'], 'requires_review')

  def test_anonymous_rejected(self):
    self.client.force_authenticate(None)
    self.assertIn(self.client.get(LIST_URL).status_code, (401, 403))


class RequiresReviewPersistenceTests(_Base):
  # 12. marcar la notificación como leída no borra la señal financiera
  def test_marking_notification_read_keeps_requires_review(self):
    appt = self.make_appt(expires_in=-dt.timedelta(minutes=5))
    Appointment.objects.filter(pk=appt.pk).update(status=Appointment.Status.EXPIRED)
    payment = self.pay(appt, P.REQUIRES_REVIEW, review_reason=R.APPROVED_AFTER_EXPIRY)
    notify_appointment_payment_review(payment.pk)
    notif = BusinessNotification.objects.get(business=self.biz)

    row = self.get_row(appt)['payment_summary']
    self.assertTrue(row['requires_review'])

    res = self.client.post(f'{NOTIF_URL}{notif.pk}/read/')
    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual(self.client.get(NOTIF_URL).data['unread_count'], 0)

    rows = self.client.get(LIST_URL).data
    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0]['effective_status'], 'expired')
    summary = rows[0]['payment_summary']
    self.assertEqual(summary['status'], 'requires_review')
    self.assertTrue(summary['requires_review'])
    self.assertEqual(summary['review_reason'], 'approved_after_expiry')
    payment.refresh_from_db()
    self.assertEqual(payment.status, P.REQUIRES_REVIEW)


class PublicContractTests(_Base):
  # 13. el serializer público no gana campos financieros internos
  def test_public_get_contract_unchanged(self):
    appt = self.make_appt(status_=Appointment.Status.CONFIRMED)
    payment = self.pay(appt, P.REQUIRES_REVIEW, review_reason=R.SLOT_CONFLICT)
    self.client.force_authenticate(None)
    res = self.client.get(public_url(appt))
    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual(set(res.data), {
      'public_token', 'status', 'expires_at', 'start_at', 'end_at', 'customer_name', 'service',
      'professional', 'deposit_amount', 'payment_status', 'contact_whatsapp_url',
    })
    self.assertEqual(res.data['payment_status'], 'requires_review')
    body = res.content.decode()
    for secret in (
      'payment_summary', 'paid_at', 'review_reason', 'slot_conflict', 'requires_review":true',
      'effective_status', payment.provider_payment_id, payment.provider_preference_id,
      payment.external_reference, 'secret-7b3',
    ):
      self.assertNotIn(secret, body)
