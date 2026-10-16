"""Webhook `flow=appointment` → confirmación segura del turno (Slice 6B).

End-to-end por el endpoint real del webhook (`WebhookDelivery` + lifecycle
5B.4) sobre PostgreSQL. Lo único mockeado es `mercadopago.SDK`: la
resolución de la conexión del Business (decrypt/lock/refresh) corre de
verdad. Concurrencia real: `test_appointment_payment_webhook_concurrency.py`.
"""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone
from rest_framework.test import APITestCase

from apps.billing.models import WebhookDelivery

from ..models import Appointment, AppointmentPayment
from ..services.expiration import expire_due_appointment_holds
from .test_appointment_checkout import (
  GLOBAL_TOKEN,
  TEST_ENCRYPTION_KEY,
  TOKEN_A,
  TOKEN_B,
  create_appointment,
  create_business,
  create_service,
)

WEBHOOK_URL = '/api/v1/billing/mercadopago/webhook'
S = WebhookDelivery.ProcessingStatus
P = AppointmentPayment.Status
R = AppointmentPayment.ReviewReason

WEBHOOK_SETTINGS = dict(
  MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
  MP_ACCESS_TOKEN=GLOBAL_TOKEN,
  MP_WEBHOOK_SECRET=None,
  DEBUG=True,
  MP_WEBHOOK_RETRY_MAX_ATTEMPTS=3,
  MP_WEBHOOK_RETRY_BASE_SECONDS=300,
  MP_WEBHOOK_PROCESSING_LEASE_SECONDS=900,
)


def mp_payment(payment: AppointmentPayment, *, status='approved', date_approved=None, amount=None,
               currency=None, ref=None, collector_id=None, metadata=None, http_status=200) -> dict:
  """Respuesta de `GET /v1/payments/{id}` (solo campos documentados)."""
  if date_approved is None and status == 'approved':
    date_approved = dj_timezone.now() - dt.timedelta(minutes=1)
  if isinstance(date_approved, dt.datetime):
    date_approved = date_approved.isoformat(timespec='milliseconds')
  body = {
    'id': 1234,
    'status': status,
    'status_detail': 'accredited' if status == 'approved' else status,
    'external_reference': payment.external_reference if ref is None else ref,
    'transaction_amount': float(payment.amount if amount is None else amount),
    'currency_id': currency or payment.currency,
    'date_approved': date_approved,
    'date_created': dj_timezone.now().isoformat(),
    'payer': {'email': 'payer@example.com'},
  }
  if collector_id is not None:
    body['collector_id'] = collector_id
  if metadata is not None:
    body['metadata'] = metadata
  return {'status': http_status, 'response': body}


class FakePaymentsSDK:
  """Reemplazo de `mercadopago.SDK` para `payment().get()`.

  `responses[token]` es un dict (respuesta del SDK), una Exception (se
  lanza) o un callable(payment_id) → respuesta. Falla en voz alta si se
  construye con el token global.
  """

  def __init__(self):
    self.tokens: list[str] = []
    self.responses: dict = {}

  def __call__(self, token, *args, **kwargs):
    if token == GLOBAL_TOKEN:
      raise AssertionError('mercadopago.SDK must never be built with the platform token for flow=appointment')
    self.tokens.append(token)
    sdk = MagicMock()
    resp = self.responses.get(token, {'status': 404, 'response': {}})

    def get(payment_id, *a, **kw):
      if isinstance(resp, Exception):
        raise resp
      return resp(payment_id) if callable(resp) else resp

    sdk.payment.return_value.get.side_effect = get
    return sdk


class _Base(APITestCase):
  def setUp(self):
    cache.clear()
    self._req = 0
    self.biz = create_business(name='Barbería A', slug='barberia-a', token=TOKEN_A)
    self.service = create_service(self.biz)
    self.appt = create_appointment(self.biz, self.service)
    self.payment = self._payment(self.appt)
    self.mp = FakePaymentsSDK()
    patcher = patch('mercadopago.SDK', new=self.mp)
    patcher.start()
    self.addCleanup(patcher.stop)

  def _payment(self, appt, *, status=P.PENDING, **extra):
    import uuid
    pid = uuid.uuid4()
    return AppointmentPayment.objects.create(
      id=pid, business=appt.business, appointment=appt,
      external_reference=AppointmentPayment.build_external_reference(pid),
      amount=appt.deposit_amount, status=status, provider_preference_id='PREF-1',
      checkout_url='https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=PREF-1', **extra,
    )

  def _notify(self, payment_id='1234', *, ref=None, flow='appointment', request_id=None) -> WebhookDelivery:
    self._req += 1
    ref = self.payment.external_reference if ref is None else ref
    query = '&'.join(p for p in (f'flow={flow}' if flow else '', f'ref={ref}' if ref else '') if p)
    res = self.client.post(
      f'{WEBHOOK_URL}?{query}', {'type': 'payment', 'data': {'id': payment_id}, 'action': 'payment.updated'},
      format='json', HTTP_X_REQUEST_ID=request_id or f'req-{self._req}-{self.id()[-24:]}',
    )
    self.assertEqual(res.status_code, 200, res.content)
    return WebhookDelivery.objects.order_by('-created_at').first()

  def _reload(self):
    self.payment.refresh_from_db()
    self.appt.refresh_from_db()

  def assertUnchanged(self, status=P.PENDING, appt_status=Appointment.Status.PENDING_PAYMENT):
    self._reload()
    self.assertEqual(self.payment.status, status)
    self.assertIsNone(self.payment.provider_payment_id)
    self.assertIsNone(self.payment.paid_at)
    self.assertEqual(self.appt.status, appt_status)


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentWebhookRoutingTests(_Base):
  # 1 + 2 + 3. routing determinístico, token del Business, nunca el global ------------------
  def test_flow_appointment_resolves_local_payment_and_uses_business_token(self):
    other = create_business(name='Barbería B', slug='barberia-b', token=TOKEN_B)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.mp.responses[TOKEN_B] = mp_payment(self.payment)

    delivery = self._notify()

    self.assertEqual(delivery.processing_status, S.PROCESSED, delivery.error_message)
    self.assertEqual(delivery.flow, 'appointment')
    self.assertEqual(self.mp.tokens, [TOKEN_A])
    self.assertNotIn(GLOBAL_TOKEN, self.mp.tokens)
    self.assertNotIn(TOKEN_B, self.mp.tokens)
    self._reload()
    self.assertEqual(self.payment.status, P.APPROVED)
    self.assertEqual(other.appointment_payments.count(), 0)

  def test_global_token_is_never_used_even_without_business_connection(self):
    self.biz.mp_connection.delete()
    with patch('apps.billing.mp_service.MercadoPagoService.get_payment') as platform_fetch:
      delivery = self._notify()
    platform_fetch.assert_not_called()
    self.assertEqual(self.mp.tokens, [])
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.DEAD_LETTER, 'merchant_reauth_required'))
    self.assertUnchanged()

  def test_unknown_ref_is_ignored_without_fetch(self):
    delivery = self._notify(ref='APPOINTMENT_PAYMENT-' + '0' * 32)
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.IGNORED, 'merchant_record_not_found'))
    self.assertEqual(self.mp.tokens, [])
    self.assertUnchanged()

  def test_unrecognized_ref_prefix_is_ignored_without_fetch(self):
    delivery = self._notify(ref='TIP-123')
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.IGNORED, 'appointment_unrecognized_ref'))
    self.assertEqual(self.mp.tokens, [])

  def test_flow_appointment_without_ref_is_ignored(self):
    delivery = self._notify(ref='')
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.IGNORED, 'merchant_missing_ref'))
    self.assertEqual(self.mp.tokens, [])

  def test_legacy_without_flow_stays_fail_closed(self):
    delivery = self._notify(flow='')
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.IGNORED, 'legacy_unresolved'))
    self.assertEqual(self.mp.tokens, [])
    self.assertUnchanged()

  def test_business_id_in_request_is_irrelevant(self):
    """Un `business_id` en query/body no participa del routing."""
    create_business(name='Barbería B', slug='barberia-b', token=TOKEN_B)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    res = self.client.post(
      f'{WEBHOOK_URL}?flow=appointment&ref={self.payment.external_reference}&business_id=999',
      {'type': 'payment', 'data': {'id': '1234'}, 'business_id': 'other'}, format='json',
      HTTP_X_REQUEST_ID='req-bizid',
    )
    self.assertEqual(res.status_code, 200)
    self.assertEqual(self.mp.tokens, [TOKEN_A])


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentWebhookValidationTests(_Base):
  # 4. external_reference mismatch → sin mutación -----------------------------------------------
  def test_external_reference_mismatch_does_not_mutate(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, ref='APPOINTMENT_PAYMENT-' + 'f' * 32)
    delivery = self._notify()
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.IGNORED, 'merchant_ref_mismatch'))
    self.assertUnchanged()

  # 5. amount mismatch → sin confirmación -------------------------------------------------------
  def test_amount_mismatch_does_not_confirm(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, amount=Decimal('1.00'))
    delivery = self._notify()
    self.assertEqual(
      (delivery.processing_status, delivery.error_category), (S.DEAD_LETTER, 'appointment_financial_mismatch'),
    )
    self.assertIn('amount', delivery.error_message)
    self.assertUnchanged()

  def test_amount_float_representation_matches(self):
    self.payment.amount = Decimal('33.30')
    self.payment.save()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, amount=33.3)
    self.assertEqual(self._notify().processing_status, S.PROCESSED)

  # 6. currency mismatch → sin confirmación -----------------------------------------------------
  def test_currency_mismatch_does_not_confirm(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, currency='USD')
    delivery = self._notify()
    self.assertEqual(delivery.processing_status, S.DEAD_LETTER)
    self.assertIn('currency', delivery.error_message)
    self.assertUnchanged()

  def test_collector_mismatch_does_not_confirm(self):
    conn = self.biz.mp_connection
    conn.mp_user_id = '111'
    conn.save()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, collector_id=222)
    delivery = self._notify()
    self.assertEqual(delivery.processing_status, S.DEAD_LETTER)
    self.assertIn('collector', delivery.error_message)
    self.assertUnchanged()

  def test_collector_match_confirms(self):
    conn = self.biz.mp_connection
    conn.mp_user_id = '111'
    conn.save()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, collector_id=111)
    self.assertEqual(self._notify().processing_status, S.PROCESSED)
    self._reload()
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)

  def test_metadata_mismatch_does_not_confirm(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, metadata={'appointment_payment_id': 'other'})
    self.assertEqual(self._notify().processing_status, S.DEAD_LETTER)
    self.assertUnchanged()

  # 7. provider_payment_id no reutilizable ---------------------------------------------------------
  def test_payment_id_already_linked_to_other_attempt_is_rejected(self):
    other_appt = create_appointment(self.biz, self.service)
    other = self._payment(other_appt, status=P.REJECTED, provider_payment_id='1234', provider_status='rejected')
    # MP devuelve el ref de ESTE intento: el mismo pago no puede quedar en dos filas.
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    delivery = self._notify('1234')
    self.assertEqual(
      (delivery.processing_status, delivery.error_category), (S.DEAD_LETTER, 'appointment_payment_id_conflict'),
    )
    self.assertUnchanged()
    other.refresh_from_db()
    self.assertEqual(other.status, P.REJECTED)

  def test_db_constraint_forbids_same_provider_payment_twice(self):
    self._payment(create_appointment(self.biz, self.service), status=P.REJECTED, provider_payment_id='777')
    with self.assertRaises(IntegrityError), transaction.atomic():
      self._payment(create_appointment(self.biz, self.service), status=P.REJECTED, provider_payment_id='777')

  def test_db_constraint_captured_requires_provider_payment_id(self):
    with self.assertRaises(IntegrityError), transaction.atomic():
      AppointmentPayment.objects.filter(pk=self.payment.pk).update(status=P.APPROVED)


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentWebhookConfirmationTests(_Base):
  # 8 + 9. approved normal → payment approved + turno confirmado + expires_at null ---------------
  def test_approved_confirms_appointment(self):
    approved_at = dj_timezone.now() - dt.timedelta(minutes=2)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=approved_at)

    delivery = self._notify('1234')

    self.assertEqual(delivery.processing_status, S.PROCESSED, delivery.error_message)
    self._reload()
    self.assertEqual(self.payment.status, P.APPROVED)
    self.assertEqual(self.payment.provider_payment_id, '1234')
    self.assertEqual(self.payment.provider_status, 'approved')
    self.assertEqual(self.payment.review_reason, '')
    self.assertEqual(self.payment.paid_at, approved_at.replace(microsecond=approved_at.microsecond // 1000 * 1000))
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)
    self.assertIsNone(self.appt.expires_at)

  # 10. approved duplicado → idempotente --------------------------------------------------------
  def test_duplicate_approved_is_idempotent(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1234')
    self._reload()
    first_updated = (self.payment.updated_at, self.appt.updated_at)

    delivery = self._notify('1234')

    self.assertEqual(delivery.processing_status, S.PROCESSED)
    self._reload()
    self.assertEqual((self.payment.status, self.appt.status), (P.APPROVED, Appointment.Status.CONFIRMED))
    self.assertEqual((self.payment.updated_at, self.appt.updated_at), first_updated)

  def test_same_notification_replayed_is_deduplicated(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1234', request_id='same-x-request-id')
    delivery = self._notify('1234', request_id='same-x-request-id')
    self.assertEqual(delivery.processing_status, S.DUPLICATED)

  def test_old_pending_webhook_never_regresses_approved(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1234')
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, status='pending')
    self._notify('1234')
    self._reload()
    self.assertEqual((self.payment.status, self.appt.status), (P.APPROVED, Appointment.Status.CONFIRMED))
    self.assertEqual(self.payment.provider_status, 'approved')

  def test_later_refund_status_is_recorded_without_touching_state(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1234')
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, status='refunded')
    self.assertEqual(self._notify('1234').processing_status, S.PROCESSED)
    self._reload()
    self.assertEqual((self.payment.status, self.payment.provider_status), (P.APPROVED, 'refunded'))
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)

  def test_second_approved_payment_for_same_attempt_is_dead_lettered(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1234')
    delivery = self._notify('5678')
    self.assertEqual(
      (delivery.processing_status, delivery.error_category), (S.DEAD_LETTER, 'appointment_duplicate_capture'),
    )
    self._reload()
    self.assertEqual(self.payment.provider_payment_id, '1234')

  # 11. pending / in_process → turno sigue pending_payment -------------------------------------
  def test_pending_and_in_process_keep_appointment_pending(self):
    for provider_status in ('pending', 'in_process'):
      self.mp.responses[TOKEN_A] = mp_payment(self.payment, status=provider_status)
      self.assertEqual(self._notify('1234').processing_status, S.PROCESSED)
      self._reload()
      self.assertEqual(self.payment.status, P.PENDING)
      self.assertEqual(self.payment.provider_status, provider_status)
      self.assertEqual(self.payment.provider_payment_id, '1234')
      self.assertIsNone(self.payment.paid_at)
      self.assertEqual(self.appt.status, Appointment.Status.PENDING_PAYMENT)
      self.assertIsNotNone(self.appt.expires_at)

  # 12. rejected → payment rejected --------------------------------------------------------------
  def test_rejected_marks_payment_rejected(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, status='rejected')
    self.assertEqual(self._notify('1234').processing_status, S.PROCESSED)
    self._reload()
    self.assertEqual((self.payment.status, self.payment.provider_status), (P.REJECTED, 'rejected'))
    self.assertEqual(self.appt.status, Appointment.Status.PENDING_PAYMENT)

  def test_cancelled_marks_payment_cancelled(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, status='cancelled')
    self._notify('1234')
    self._reload()
    self.assertEqual(self.payment.status, P.CANCELLED)

  def test_retry_on_same_preference_after_rejection_can_approve(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, status='rejected')
    self._notify('1111')
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('2222')
    self._reload()
    self.assertEqual((self.payment.status, self.payment.provider_payment_id), (P.APPROVED, '2222'))
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)

  def test_old_rejection_of_other_payment_does_not_override_pending(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, status='in_process')
    self._notify('2222')
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, status='rejected')
    delivery = self._notify('1111')
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.IGNORED, 'appointment_stale_event'))
    self._reload()
    self.assertEqual((self.payment.status, self.payment.provider_payment_id), (P.PENDING, '2222'))

  def test_webhook_resolves_uncertain_attempt(self):
    AppointmentPayment.objects.filter(pk=self.payment.pk).update(status=P.UNCERTAIN, checkout_url=None)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1234')
    self._reload()
    self.assertEqual((self.payment.status, self.appt.status), (P.APPROVED, Appointment.Status.CONFIRMED))


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentWebhookTimeWindowTests(_Base):
  def _expire_hold(self, *, minutes_ago=1):
    expires_at = dj_timezone.now() - dt.timedelta(minutes=minutes_ago)
    Appointment.objects.filter(pk=self.appt.pk).update(expires_at=expires_at)
    self.appt.refresh_from_db()
    return self.appt.expires_at

  # 13. aprobado antes del vencimiento, webhook después → confirma -----------------------------
  def test_approved_before_expiry_with_late_webhook_confirms(self):
    expires_at = self._expire_hold()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=expires_at - dt.timedelta(minutes=1))
    self._notify('1234')
    self._reload()
    self.assertEqual((self.payment.status, self.appt.status), (P.APPROVED, Appointment.Status.CONFIRMED))
    self.assertIsNone(self.appt.expires_at)

  def test_approved_before_expiry_confirms_even_after_expiration_worker(self):
    expires_at = self._expire_hold()
    self.assertEqual(expire_due_appointment_holds(), 1)
    self.appt.refresh_from_db()
    self.assertEqual(self.appt.status, Appointment.Status.EXPIRED)
    self.assertEqual(self.appt.expires_at, expires_at)  # conservado como evidencia

    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=expires_at - dt.timedelta(seconds=30))
    self._notify('1234')
    self._reload()
    self.assertEqual((self.payment.status, self.appt.status), (P.APPROVED, Appointment.Status.CONFIRMED))

  def test_approval_date_timezone_is_normalized(self):
    expires_at = self._expire_hold()
    # Misma instancia expresada en -03:00: 30s antes del vencimiento.
    local = (expires_at - dt.timedelta(seconds=30)).astimezone(dt.timezone(dt.timedelta(hours=-3)))
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=local.isoformat(timespec='milliseconds'))
    self._notify('1234')
    self._reload()
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)

  def test_approval_without_timezone_is_not_trusted(self):
    naive = (dj_timezone.now() - dt.timedelta(minutes=1)).replace(tzinfo=None).isoformat()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=naive)
    self._notify('1234')
    self._reload()
    self.assertEqual((self.payment.status, self.payment.review_reason), (P.REQUIRES_REVIEW, R.APPROVAL_TIME_UNKNOWN))
    self.assertEqual(self.appt.status, Appointment.Status.PENDING_PAYMENT)

  # 14. aprobado después del vencimiento → requires_review ---------------------------------------
  def test_approved_after_expiry_requires_review(self):
    expires_at = self._expire_hold(minutes_ago=5)
    approved_at = expires_at + dt.timedelta(minutes=1)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=approved_at)

    delivery = self._notify('1234')

    self.assertEqual(delivery.processing_status, S.PROCESSED)
    self.assertIn('requires_review', delivery.error_message)
    self._reload()
    self.assertEqual(self.payment.status, P.REQUIRES_REVIEW)
    self.assertEqual(self.payment.review_reason, R.APPROVED_AFTER_EXPIRY)
    self.assertEqual(self.payment.provider_payment_id, '1234')
    self.assertEqual(self.payment.provider_status, 'approved')
    self.assertIsNotNone(self.payment.paid_at)  # el dinero existe
    self.assertEqual(self.appt.status, Appointment.Status.EXPIRED)
    self.assertEqual(self.appt.expires_at, expires_at)
    self.assertFalse(Appointment.objects.occupying().filter(pk=self.appt.pk).exists())

    # Webhook repetido: sigue en revisión, no se confirma.
    self.assertEqual(self._notify('1234').processing_status, S.PROCESSED)
    self._reload()
    self.assertEqual((self.payment.status, self.appt.status), (P.REQUIRES_REVIEW, Appointment.Status.EXPIRED))

  # 15. dentro de la ventana pero slot ocupado → requires_review -------------------------------
  def test_approved_in_window_but_slot_taken_requires_review(self):
    expires_at = self._expire_hold()
    intruder = create_appointment(self.biz, self.service)
    Appointment.objects.filter(pk=intruder.pk).update(start_at=self.appt.start_at, end_at=self.appt.end_at)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=expires_at - dt.timedelta(minutes=1))

    self._notify('1234')

    self._reload()
    intruder.refresh_from_db()
    self.assertEqual((self.payment.status, self.payment.review_reason), (P.REQUIRES_REVIEW, R.SLOT_CONFLICT))
    self.assertEqual(self.appt.status, Appointment.Status.EXPIRED)
    self.assertEqual(intruder.status, Appointment.Status.PENDING_PAYMENT)
    occupying = Appointment.objects.occupying().filter(
      business=self.biz, start_at__lt=self.appt.end_at, end_at__gt=self.appt.start_at,
    )
    self.assertEqual(list(occupying), [intruder])

  def test_non_overlapping_appointment_does_not_block_confirmation(self):
    expires_at = self._expire_hold()
    other = create_appointment(self.biz, self.service, status_=Appointment.Status.CONFIRMED)
    Appointment.objects.filter(pk=other.pk).update(
      start_at=self.appt.end_at, end_at=self.appt.end_at + dt.timedelta(minutes=30),
    )
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=expires_at - dt.timedelta(minutes=1))
    self._notify('1234')
    self._reload()
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentWebhookIncompatibleStateTests(_Base):
  # 16. turno cancelado + approved → requires_review, nunca se reabre ---------------------------
  def test_cancelled_completed_no_show_are_never_reopened(self):
    for appt_status in (Appointment.Status.CANCELLED, Appointment.Status.COMPLETED, Appointment.Status.NO_SHOW):
      with self.subTest(appt_status=appt_status):
        appt = create_appointment(self.biz, self.service)
        Appointment.objects.filter(pk=appt.pk).update(status=appt_status, expires_at=None)
        self.payment = self._payment(appt)
        self.appt = appt
        self.mp.responses[TOKEN_A] = mp_payment(self.payment)

        self.assertEqual(self._notify(f'pay-{appt_status}').processing_status, S.PROCESSED)

        self._reload()
        self.assertEqual(self.payment.status, P.REQUIRES_REVIEW)
        self.assertEqual(self.payment.review_reason, R.APPOINTMENT_NOT_PAYABLE)
        self.assertIsNotNone(self.payment.paid_at)
        self.assertEqual(self.appt.status, appt_status)

  def test_appointment_confirmed_by_other_means_requires_review(self):
    Appointment.objects.filter(pk=self.appt.pk).update(status=Appointment.Status.CONFIRMED, expires_at=None)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1234')
    self._reload()
    self.assertEqual(
      (self.payment.status, self.payment.review_reason), (P.REQUIRES_REVIEW, R.APPOINTMENT_ALREADY_CONFIRMED),
    )
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)

  def test_second_attempt_paid_after_first_confirmed_requires_review(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self._notify('1111')
    second = self._payment(self.appt, status=P.REJECTED)
    self.mp.responses[TOKEN_A] = mp_payment(second)
    self._notify('2222', ref=second.external_reference)
    second.refresh_from_db()
    self.assertEqual((second.status, second.review_reason), (P.REQUIRES_REVIEW, R.APPOINTMENT_ALREADY_CONFIRMED))
    self._reload()
    self.assertEqual((self.payment.status, self.appt.status), (P.APPROVED, Appointment.Status.CONFIRMED))


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentWebhookLifecycleTests(_Base):
  # 17. timeout / 5xx → FAILED + retry --------------------------------------------------------------
  def test_provider_timeout_or_5xx_goes_failed_and_retries(self):
    import requests
    for failure in (requests.exceptions.ReadTimeout('timed out'), {'status': 500, 'response': {}}):
      with self.subTest(failure=type(failure).__name__):
        self.mp.responses[TOKEN_A] = failure
        delivery = self._notify('1234')
        self.assertEqual((delivery.processing_status, delivery.error_category), (S.FAILED, 'provider_fetch_failed'))
        self.assertIsNotNone(delivery.next_retry_at)
        self.assertUnchanged()

    # Retry manual (mismo camino que el sweeper) una vez que MP responde.
    from apps.billing.webhook_lifecycle import process_delivery
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    WebhookDelivery.objects.filter(pk=delivery.pk).update(next_retry_at=dj_timezone.now())
    self.assertEqual(process_delivery(delivery.pk), S.PROCESSED)
    self._reload()
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)

  def test_temporary_refresh_failure_is_retried(self):
    from apps.merchant_payments.services import MerchantPaymentConnectionUnavailable
    with patch(
      'apps.merchant_payments.services.get_merchant_payment',
      side_effect=MerchantPaymentConnectionUnavailable(self.biz.id, 'refresh_temporarily_unavailable'),
    ):
      delivery = self._notify('1234')
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.FAILED, 'merchant_refresh_temporary'))
    self.assertUnchanged()

  # 18. conexión merchant no recuperable → terminal seguro ------------------------------------------
  def test_unrecoverable_merchant_connection_is_dead_lettered(self):
    conn = self.biz.mp_connection
    conn.status = 'error'
    conn.save()
    delivery = self._notify('1234')
    self.assertEqual((delivery.processing_status, delivery.error_category), (S.DEAD_LETTER, 'merchant_reauth_required'))
    self.assertIsNone(delivery.next_retry_at)
    self.assertEqual(self.mp.tokens, [])
    self.assertUnchanged()

  # 24. tokens / PII fuera de logs y de WebhookDelivery ----------------------------------------------
  def test_tokens_and_pii_never_logged(self):
    scenarios = [
      mp_payment(self.payment, amount=Decimal('1')),                   # financial mismatch
      {'status': 500, 'response': {'message': f'token {TOKEN_A}'}},    # fetch failure
      mp_payment(self.payment),                                        # applied
    ]
    with self.assertLogs(level='DEBUG') as logs:
      deliveries = []
      for resp in scenarios:
        self.mp.responses[TOKEN_A] = resp
        deliveries.append(self._notify('1234'))
      self.mp.responses[TOKEN_A] = RuntimeError(f'boom Bearer {TOKEN_A}')
      deliveries.append(self._notify('1234'))

    output = '\n'.join(logs.output)
    stored = '\n'.join(f'{d.error_message} {d.error_category}' for d in WebhookDelivery.objects.all())
    for secret in (TOKEN_A, GLOBAL_TOKEN, 'Juana', '1155554444', 'juana@example.com', 'payer@example.com'):
      self.assertNotIn(secret, output)
      self.assertNotIn(secret, stored)


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentHoldExpirationTraceabilityTests(TestCase):
  # 12 (spec). La expiración conserva los intentos financieros --------------------------------------
  def test_expiration_keeps_payment_attempts_and_expires_at(self):
    biz = create_business(name='Barbería A', slug='barberia-a', token=TOKEN_A)
    service = create_service(biz)
    rows = {}
    for st in (P.PENDING, P.UNCERTAIN, P.CREATING):
      appt = create_appointment(biz, service, expires_in=dt.timedelta(minutes=-1))
      rows[st] = (appt, AppointmentPayment.objects.create(
        business=biz, appointment=appt, external_reference=f'APPOINTMENT_PAYMENT-{st}',
        amount=Decimal('30'), status=st, provider_preference_id='PREF-X',
      ))

    self.assertEqual(expire_due_appointment_holds(), 3)

    for st, (appt, payment) in rows.items():
      appt_before = appt.expires_at
      appt.refresh_from_db()
      payment.refresh_from_db()
      self.assertEqual(appt.status, Appointment.Status.EXPIRED)
      self.assertEqual(appt.expires_at, appt_before)
      self.assertEqual(payment.status, st)
      self.assertEqual(payment.provider_preference_id, 'PREF-X')
    self.assertEqual(AppointmentPayment.objects.count(), 3)
