"""Tests del checkout de seña con Mercado Pago (Slice 6A).

`POST /api/v1/appointments/public/<slug>/bookings/<public_token>/checkout/`
→ `AppointmentPayment` + Preference en la cuenta MP del Business.

Corren sobre PostgreSQL real. Lo único mockeado es la comunicación con
Mercado Pago (`mercadopago.SDK`): la resolución de la conexión del Business
(`apps.merchant_payments.services.get_merchant_connection`: decrypt, lock,
refresh) corre de verdad contra la base.

La concurrencia real (threads + conexiones propias) vive en
`test_appointment_checkout_concurrency.py`.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from decimal import Decimal
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import requests
from django.core.cache import cache
from django.db import DatabaseError, IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.business.models import Business, BusinessPlan, Subscription
from apps.merchant_payments.models import MercadoPagoConnection

from ..models import Appointment, AppointmentPayment, AppointmentService

TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='
GLOBAL_TOKEN = 'GLOBAL-PLATFORM-TOKEN-must-never-be-used'
TOKEN_A = 'APP_USR-BUSINESS-A-SECRET-TOKEN'
TOKEN_B = 'APP_USR-BUSINESS-B-SECRET-TOKEN'
API_BASE = 'https://api.mirubro.test'
FRONT_BASE = 'https://app.mirubro.test'

EXT_REF_RE = re.compile(r'^APPOINTMENT_PAYMENT-[0-9a-f]{32}$')


def _mp_created(pref_id='PREF-123'):
  return {
    'status': 201,
    'response': {
      'id': pref_id,
      'init_point': f'https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id={pref_id}',
      'sandbox_init_point': f'https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id={pref_id}',
    },
  }


def create_business(*, name, slug, token=None, conn_status='connected'):
  biz = Business.objects.create(
    name=name, default_service='appointments', slug=slug,
    timezone='America/Argentina/Buenos_Aires', status='active',
  )
  Subscription.objects.create(
    business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
  )
  if token is not None:
    MercadoPagoConnection.objects.create(business=biz, access_token=token, status=conn_status)
  return biz


def create_service(business, *, deposit_type='fixed', deposit_value=Decimal('30'), price=Decimal('100')):
  return AppointmentService.objects.create(
    business=business, name='Corte', duration_minutes=30, price=price,
    deposit_type=deposit_type, deposit_value=deposit_value,
  )


def create_appointment(business, service, *, status_=Appointment.Status.PENDING_PAYMENT,
                       expires_in=dt.timedelta(minutes=10), source=Appointment.Source.PUBLIC):
  now = dj_timezone.now()
  start = now + dt.timedelta(days=2)
  return Appointment.objects.create(
    business=business, service=service,
    customer_name='Juana Pérez', customer_phone='1155554444', customer_email='juana@example.com',
    start_at=start, end_at=start + dt.timedelta(minutes=30),
    status=status_,
    expires_at=(now + expires_in) if status_ == Appointment.Status.PENDING_PAYMENT else None,
    source=source,
    service_name=service.name, service_duration_minutes=service.duration_minutes,
    service_price=service.price, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
  )


class FakeMercadoPago:
  """Reemplazo de `mercadopago.SDK`: registra tokens y requests de Preference."""

  def __init__(self):
    self.tokens: list[str] = []
    self.preference_calls: list[tuple[str, dict, object]] = []
    self.behavior = lambda data: _mp_created()

  def __call__(self, token):
    self.tokens.append(token)
    sdk = MagicMock()

    def create(data, request_options=None):
      self.preference_calls.append((token, data, request_options))
      return self.behavior(data)

    sdk.preference.return_value.create.side_effect = create
    return sdk


@override_settings(
  MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
  MP_ACCESS_TOKEN=GLOBAL_TOKEN,
  BASE_PUBLIC_URL=API_BASE,
  FRONTEND_URL=FRONT_BASE,
)
class AppointmentCheckoutTests(APITestCase):
  def setUp(self):
    cache.clear()
    self.biz = create_business(name='Barbería A', slug='barberia-a', token=TOKEN_A)
    self.service = create_service(self.biz)
    self.appt = create_appointment(self.biz, self.service)

    self.mp = FakeMercadoPago()
    patcher = patch('mercadopago.SDK', new=self.mp)
    patcher.start()
    self.addCleanup(patcher.stop)

  def _url(self, slug=None, token=None):
    return (
      f'/api/v1/appointments/public/{slug or self.biz.slug}/bookings/'
      f'{token or self.appt.public_token}/checkout/'
    )

  def _post(self, slug=None, token=None, data=None):
    return self.client.post(self._url(slug, token), data or {}, format='json')

  # 1. pending_payment válido → AppointmentPayment creado ----------------------------------
  def test_valid_pending_payment_creates_payment(self):
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.content)
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.appointment_id, self.appt.id)
    self.assertEqual(payment.business_id, self.biz.id)
    self.assertEqual(payment.status, AppointmentPayment.Status.PENDING)
    self.assertEqual(payment.provider, 'mercadopago')
    self.assertEqual(res.data['payment_id'], str(payment.id))
    self.assertEqual(res.data['status'], 'pending')
    self.assertEqual(res.data['currency'], 'ARS')
    self.assertIsNotNone(res.data['expires_at'])
    # El turno NO se confirma en este slice.
    self.appt.refresh_from_db()
    self.assertEqual(self.appt.status, Appointment.Status.PENDING_PAYMENT)
    self.assertEqual(len(self.mp.preference_calls), 1)

  def test_response_exposes_no_internal_or_provider_ids(self):
    res = self._post()
    self.assertEqual(
      set(res.data), {'payment_id', 'status', 'amount', 'currency', 'checkout_url', 'expires_at'},
    )
    body = res.content.decode()
    payment = AppointmentPayment.objects.get()
    self.assertNotIn(payment.external_reference, body)
    self.assertNotIn(str(self.appt.id), body)
    self.assertNotIn('PREF-123"', body.replace('pref_id=PREF-123', ''))  # preference id solo dentro de la URL

  # 2. monto del snapshot --------------------------------------------------------------------
  def test_amount_comes_from_appointment_snapshot_not_current_service(self):
    self.service.deposit_value = Decimal('999')
    self.service.price = Decimal('5000')
    self.service.save()
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_201_CREATED)
    self.assertEqual(res.data['amount'], '30.00')
    self.assertEqual(AppointmentPayment.objects.get().amount, Decimal('30.00'))
    _, data, _ = self.mp.preference_calls[0]
    self.assertEqual(data['items'][0]['unit_price'], 30.0)
    self.assertEqual(data['items'][0]['currency_id'], 'ARS')

  def test_percentage_deposit_amount_from_snapshot(self):
    svc = create_service(self.biz, deposit_type='percentage', deposit_value=Decimal('25'), price=Decimal('150'))
    appt = create_appointment(self.biz, svc)
    res = self._post(token=appt.public_token)
    self.assertEqual(res.status_code, status.HTTP_201_CREATED)
    self.assertEqual(res.data['amount'], '37.50')

  # 3. sin seña → no checkout -----------------------------------------------------------------
  def test_no_deposit_confirmed_appointment_rejected(self):
    svc = create_service(self.biz, deposit_type='none', deposit_value=Decimal('0'))
    appt = create_appointment(self.biz, svc, status_=Appointment.Status.CONFIRMED)
    res = self._post(token=appt.public_token)
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(res.data['code'], 'not_payable')
    self.assertFalse(AppointmentPayment.objects.exists())
    self.assertEqual(self.mp.preference_calls, [])

  def test_zero_deposit_even_if_pending_payment_creates_nothing(self):
    svc = create_service(self.biz, deposit_type='none', deposit_value=Decimal('0'))
    appt = create_appointment(self.biz, svc)  # estado inconsistente, defensa en profundidad
    res = self._post(token=appt.public_token)
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertFalse(AppointmentPayment.objects.exists())
    self.assertEqual(self.mp.tokens, [])

  # 4. confirmed → rechazado -----------------------------------------------------------------
  def test_confirmed_appointment_rejected(self):
    Appointment.objects.filter(pk=self.appt.pk).update(status=Appointment.Status.CONFIRMED, expires_at=None)
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(res.data['code'], 'not_payable')
    self.assertFalse(AppointmentPayment.objects.exists())
    self.assertEqual(self.mp.tokens, [])

  def test_cancelled_appointment_rejected(self):
    Appointment.objects.filter(pk=self.appt.pk).update(status=Appointment.Status.CANCELLED, expires_at=None)
    self.assertEqual(self._post().status_code, status.HTTP_409_CONFLICT)
    self.assertFalse(AppointmentPayment.objects.exists())

  def test_manual_source_rejected(self):
    appt = create_appointment(self.biz, self.service, source=Appointment.Source.MANUAL)
    res = self._post(token=appt.public_token)
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertFalse(AppointmentPayment.objects.exists())

  # 5. expired → rechazado, normalizado, sin Preference ----------------------------------------
  def test_expired_hold_is_normalized_and_no_preference(self):
    Appointment.objects.filter(pk=self.appt.pk).update(expires_at=dj_timezone.now() - dt.timedelta(seconds=1))
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(res.data['code'], 'expired')
    self.appt.refresh_from_db()
    self.assertEqual(self.appt.status, Appointment.Status.EXPIRED)
    self.assertFalse(AppointmentPayment.objects.exists())
    self.assertEqual(self.mp.tokens, [])

  def test_already_expired_status_rejected(self):
    Appointment.objects.filter(pk=self.appt.pk).update(status=Appointment.Status.EXPIRED)
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertFalse(AppointmentPayment.objects.exists())
    self.assertEqual(self.mp.tokens, [])

  def test_existing_pending_payment_not_reused_after_hold_expires(self):
    self.assertEqual(self._post().status_code, status.HTTP_201_CREATED)
    Appointment.objects.filter(pk=self.appt.pk).update(expires_at=dj_timezone.now() - dt.timedelta(seconds=1))
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(res.data['code'], 'expired')
    self.assertEqual(len(self.mp.preference_calls), 1)

  # 6. slug/business incorrecto → rechazado ------------------------------------------------------
  def test_token_under_other_business_slug_returns_404(self):
    other = create_business(name='Barbería B', slug='barberia-b', token=TOKEN_B)
    res = self._post(slug=other.slug)
    self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
    self.assertFalse(AppointmentPayment.objects.exists())
    self.assertEqual(self.mp.tokens, [])

  def test_unknown_slug_and_unknown_token_return_404(self):
    self.assertEqual(self._post(slug='no-existe').status_code, status.HTTP_404_NOT_FOUND)
    self.assertEqual(
      self._post(token='00000000-0000-0000-0000-000000000000').status_code, status.HTTP_404_NOT_FOUND,
    )
    self.assertFalse(AppointmentPayment.objects.exists())

  def test_business_without_appointments_enabled_returns_404(self):
    Subscription.objects.filter(business=self.biz).update(service='restaurante')
    self.assertEqual(self._post().status_code, status.HTTP_404_NOT_FOUND)
    self.assertFalse(AppointmentPayment.objects.exists())
    self.assertEqual(self.mp.tokens, [])

  def test_non_publishable_business_returns_404(self):
    Business.objects.filter(pk=self.biz.pk).update(status='suspended')
    self.assertEqual(self._post().status_code, status.HTTP_404_NOT_FOUND)
    self.assertFalse(AppointmentPayment.objects.exists())

  # 7. sin conexión MP → fallo seguro ------------------------------------------------------------
  def test_no_mp_connection_fails_safely(self):
    MercadoPagoConnection.objects.filter(business=self.biz).delete()
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
    self.assertEqual(res.data['code'], 'payment_unavailable')
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.ERROR)
    self.assertEqual(payment.failure_reason, 'mp_not_connected')
    self.assertIsNone(payment.provider_preference_id)
    self.assertEqual(self.mp.tokens, [])  # nunca se construyó un SDK (ni con token global)

  def test_revoked_mp_connection_fails_safely_and_allows_retry_later(self):
    MercadoPagoConnection.objects.filter(business=self.biz).update(status='revoked')
    self.assertEqual(self._post().status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
    self.assertEqual(self.mp.tokens, [])
    MercadoPagoConnection.objects.filter(business=self.biz).update(status='connected')
    self.assertEqual(self._post().status_code, status.HTTP_201_CREATED)
    self.assertEqual(AppointmentPayment.objects.filter(status='pending').count(), 1)
    self.assertEqual(AppointmentPayment.objects.filter(status='error').count(), 1)

  # 8/9. token del Business, nunca global -----------------------------------------------------------
  def test_uses_business_token_never_global(self):
    self.assertEqual(self._post().status_code, status.HTTP_201_CREATED)
    self.assertEqual(self.mp.tokens, [TOKEN_A])
    self.assertNotIn(GLOBAL_TOKEN, self.mp.tokens)
    token_used, _, request_options = self.mp.preference_calls[0]
    self.assertEqual(token_used, TOKEN_A)
    # Sin reintentos automáticos del SDK en el POST de Preference.
    self.assertEqual(request_options.max_retries, 0)

  # 10. external_reference server-side ---------------------------------------------------------------
  def test_external_reference_generated_server_side(self):
    self._post()
    payment = AppointmentPayment.objects.get()
    self.assertRegex(payment.external_reference, EXT_REF_RE)
    self.assertEqual(payment.external_reference, f'APPOINTMENT_PAYMENT-{payment.id.hex}')
    _, data, _ = self.mp.preference_calls[0]
    self.assertEqual(data['external_reference'], payment.external_reference)

  # 11. notification_url con flow=appointment&ref=... -------------------------------------------------
  def test_notification_url_has_explicit_appointment_routing(self):
    self._post()
    payment = AppointmentPayment.objects.get()
    _, data, _ = self.mp.preference_calls[0]
    url = urlparse(data['notification_url'])
    self.assertEqual(f'{url.scheme}://{url.netloc}', API_BASE)
    self.assertEqual(url.path, '/api/v1/billing/mercadopago/webhook')
    self.assertEqual(parse_qs(url.query), {'flow': ['appointment'], 'ref': [payment.external_reference]})
    self.assertIn(f'flow=appointment&ref={payment.external_reference}', data['notification_url'])

  @override_settings(BASE_PUBLIC_URL=None)
  def test_missing_base_public_url_refuses_to_create_preference(self):
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
    self.assertEqual(self.mp.preference_calls, [])
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.ERROR)
    self.assertEqual(payment.failure_reason, 'notification_url_unavailable')

  def test_preference_expires_with_hold_back_urls_without_pii(self):
    self._post()
    _, data, _ = self.mp.preference_calls[0]
    self.appt.refresh_from_db()
    self.assertTrue(data['expires'])
    expected_to = self.appt.expires_at.replace(microsecond=self.appt.expires_at.microsecond // 1000 * 1000)
    self.assertEqual(dt.datetime.fromisoformat(data['expiration_date_to']), expected_to)
    self.assertLess(dt.datetime.fromisoformat(data['expiration_date_from']), dj_timezone.now())
    self.assertIn({'id': 'ticket'}, data['payment_methods']['excluded_payment_types'])
    for key in ('success', 'pending', 'failure'):
      back = data['back_urls'][key]
      self.assertTrue(back.startswith(f'{FRONT_BASE}/t/{self.biz.slug}?'))
      self.assertEqual(parse_qs(urlparse(back).query), {'booking': [str(self.appt.public_token)], 'payment': [key]})
    blob = repr(data)
    for pii in ('Juana', '1155554444', 'juana@example.com'):
      self.assertNotIn(pii, blob)

  # 12/13. preference id + checkout_url persistidos/devueltos --------------------------------------
  def test_preference_id_and_checkout_url_persisted_and_returned(self):
    self.mp.behavior = lambda data: _mp_created('PREF-XYZ')
    res = self._post()
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.provider_preference_id, 'PREF-XYZ')
    self.assertEqual(payment.checkout_url, 'https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=PREF-XYZ')
    self.assertEqual(res.data['checkout_url'], payment.checkout_url)

  # 14. dos requests secuenciales → una sola Preference activa -----------------------------------
  def test_sequential_requests_reuse_pending_attempt(self):
    first = self._post()
    second = self._post()
    self.assertEqual(first.status_code, status.HTTP_201_CREATED)
    self.assertEqual(second.status_code, status.HTTP_200_OK)
    self.assertEqual(first.data['payment_id'], second.data['payment_id'])
    self.assertEqual(first.data['checkout_url'], second.data['checkout_url'])
    self.assertEqual(len(self.mp.preference_calls), 1)
    self.assertEqual(AppointmentPayment.objects.count(), 1)

  def test_attempt_in_creating_state_blocks_new_attempt(self):
    AppointmentPayment.objects.create(
      business=self.biz, appointment=self.appt, external_reference='APPOINTMENT_PAYMENT-x1',
      amount=Decimal('30'), status=AppointmentPayment.Status.CREATING,
    )
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(res.data['code'], 'payment_in_progress')
    self.assertEqual(self.mp.tokens, [])

  def test_db_partial_unique_constraint_single_active_attempt(self):
    AppointmentPayment.objects.create(
      business=self.biz, appointment=self.appt, external_reference='APPOINTMENT_PAYMENT-a',
      amount=Decimal('30'), status=AppointmentPayment.Status.PENDING,
    )
    for st in AppointmentPayment.ACTIVE_STATUSES:
      with self.subTest(status=st), self.assertRaises(IntegrityError), transaction.atomic():
        AppointmentPayment.objects.create(
          business=self.biz, appointment=self.appt, external_reference=f'APPOINTMENT_PAYMENT-{st}',
          amount=Decimal('30'), status=st,
        )
    # Estados terminales no cuentan como activos.
    for st in ('error', 'cancelled', 'rejected'):
      AppointmentPayment.objects.create(
        business=self.biz, appointment=self.appt, external_reference=f'APPOINTMENT_PAYMENT-{st}',
        amount=Decimal('30'), status=st,
      )

  def test_active_statuses_match_db_constraint(self):
    constraint = next(
      c for c in AppointmentPayment._meta.constraints if c.name == 'appointment_payment_single_active'
    )
    (lookup, values), = constraint.condition.children
    self.assertEqual(lookup, 'status__in')
    self.assertEqual(set(values), {str(s) for s in AppointmentPayment.ACTIVE_STATUSES})

  # 16. Business A nunca usa la conexión de B -----------------------------------------------------
  def test_each_business_uses_only_its_own_connection(self):
    biz_b = create_business(name='Barbería B', slug='barberia-b', token=TOKEN_B)
    appt_b = create_appointment(biz_b, create_service(biz_b))
    self.assertEqual(self._post().status_code, status.HTTP_201_CREATED)
    self.assertEqual(self._post(slug=biz_b.slug, token=appt_b.public_token).status_code, status.HTTP_201_CREATED)
    self.assertEqual(self.mp.tokens, [TOKEN_A, TOKEN_B])
    pay_a = AppointmentPayment.objects.get(appointment=self.appt)
    pay_b = AppointmentPayment.objects.get(appointment=appt_b)
    self.assertEqual(pay_a.business_id, self.biz.id)
    self.assertEqual(pay_b.business_id, biz_b.id)

  def test_business_b_without_connection_never_falls_back_to_a(self):
    biz_b = create_business(name='Barbería B', slug='barberia-b', token=None)
    appt_b = create_appointment(biz_b, create_service(biz_b))
    res = self._post(slug=biz_b.slug, token=appt_b.public_token)
    self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
    self.assertEqual(self.mp.tokens, [])

  # 17. payload malicioso ------------------------------------------------------------------------
  def test_malicious_payload_cannot_alter_amount_status_or_reference(self):
    res = self._post(data={
      'amount': '1.00', 'price': '1', 'percentage': '1', 'deposit_value': '1',
      'currency': 'USD', 'status': 'approved', 'external_reference': 'ATTACKER-REF',
      'business_id': 999, 'appointment_id': 'x', 'provider_preference_id': 'EVIL',
      'checkout_url': 'https://evil.example/pay', 'notification_url': 'https://evil.example/hook',
    })
    self.assertEqual(res.status_code, status.HTTP_201_CREATED)
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.amount, Decimal('30.00'))
    self.assertEqual(payment.currency, 'ARS')
    self.assertEqual(payment.status, AppointmentPayment.Status.PENDING)
    self.assertRegex(payment.external_reference, EXT_REF_RE)
    self.assertEqual(payment.provider_preference_id, 'PREF-123')
    _, data, _ = self.mp.preference_calls[0]
    self.assertNotIn('evil', repr(data))
    self.assertNotIn('ATTACKER', repr(data))
    self.appt.refresh_from_db()
    self.assertEqual(self.appt.status, Appointment.Status.PENDING_PAYMENT)

  # 18. tokens nunca en response/logs ----------------------------------------------------------------
  def test_tokens_never_in_response_or_logs(self):
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
      def emit(self, record):
        records.append(record)

    handler = Capture(level=logging.DEBUG)
    loggers = [logging.getLogger(n) for n in ('', 'apps', 'apps.appointments', 'apps.merchant_payments')]
    previous = [lg.level for lg in loggers]
    for lg in loggers:
      lg.addHandler(handler)
      lg.setLevel(logging.DEBUG)
    try:
      bodies = [self._post().content.decode()]
      appt2 = create_appointment(self.biz, self.service)
      self.mp.behavior = lambda data: {'status': 500, 'response': {'error': 'internal_error', 'token': TOKEN_A}}
      bodies.append(self._post(token=appt2.public_token).content.decode())
      appt3 = create_appointment(self.biz, self.service)

      def boom(data):
        raise requests.exceptions.ReadTimeout(f'timeout for {TOKEN_A}')

      self.mp.behavior = boom
      bodies.append(self._post(token=appt3.public_token).content.decode())
    finally:
      for lg, lvl in zip(loggers, previous):
        lg.removeHandler(handler)
        lg.setLevel(lvl)

    self.assertTrue(records)
    messages = [r.getMessage() for r in records]
    for secret in (TOKEN_A, GLOBAL_TOKEN):
      for body in bodies:
        self.assertNotIn(secret, body)
      for msg in messages:
        self.assertNotIn(secret, msg)

  # 19. fallo MP definitivo → estado local coherente ----------------------------------------------
  def test_mp_rejection_marks_error_and_allows_new_attempt(self):
    self.mp.behavior = lambda data: {'status': 400, 'response': {'error': 'bad_request', 'message': 'x'}}
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_502_BAD_GATEWAY)
    self.assertEqual(res.data['code'], 'payment_provider_error')
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.ERROR)
    self.assertEqual(payment.failure_reason, 'mp_rejected:400')
    self.assertIsNone(payment.checkout_url)

    self.mp.behavior = lambda data: _mp_created('PREF-2')
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_201_CREATED)
    self.assertEqual(AppointmentPayment.objects.filter(status='pending').count(), 1)
    self.assertEqual(len(self.mp.preference_calls), 2)
    # Cada intento tiene su propia referencia.
    self.assertEqual(AppointmentPayment.objects.values('external_reference').distinct().count(), 2)

  def test_connect_timeout_is_definitive_error(self):
    def boom(data):
      raise requests.exceptions.ConnectTimeout('connect timeout')

    self.mp.behavior = boom
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_502_BAD_GATEWAY)
    self.assertEqual(AppointmentPayment.objects.get().status, AppointmentPayment.Status.ERROR)

  # 20. resultado incierto → fail-closed -------------------------------------------------------------
  def test_read_timeout_is_uncertain_and_blocks_retry(self):
    def boom(data):
      raise requests.exceptions.ReadTimeout('read timed out')

    self.mp.behavior = boom
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_502_BAD_GATEWAY)
    self.assertEqual(res.data['code'], 'payment_uncertain')
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.UNCERTAIN)
    self.assertEqual(payment.failure_reason, 'mp_uncertain:ReadTimeout')

    # El retry del cliente NO crea una segunda Preference.
    self.mp.behavior = lambda data: _mp_created('PREF-SHOULD-NOT-EXIST')
    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(res.data['code'], 'payment_in_progress')
    self.assertEqual(len(self.mp.preference_calls), 1)
    self.assertEqual(AppointmentPayment.objects.count(), 1)
    self.appt.refresh_from_db()
    self.assertEqual(self.appt.status, Appointment.Status.PENDING_PAYMENT)

  def test_mp_5xx_is_uncertain(self):
    self.mp.behavior = lambda data: {'status': 503, 'response': None}
    self.assertEqual(self._post().status_code, status.HTTP_502_BAD_GATEWAY)
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.UNCERTAIN)
    self.assertEqual(payment.failure_reason, 'mp_uncertain:503')

  def test_incomplete_2xx_is_uncertain_and_keeps_preference_id(self):
    self.mp.behavior = lambda data: {'status': 201, 'response': {'id': 'PREF-NO-URL'}}
    self.assertEqual(self._post().status_code, status.HTTP_502_BAD_GATEWAY)
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.UNCERTAIN)
    self.assertEqual(payment.provider_preference_id, 'PREF-NO-URL')
    self.assertIsNone(payment.checkout_url)

  def test_local_persistence_failure_after_remote_creation_stays_blocking(self):
    # MP creó la Preference pero no se pudo persistir el resultado local:
    # la fila queda `creating` (activa) y un retry NO recrea la Preference.
    with patch('apps.appointments.services.payment._finalize', side_effect=DatabaseError('db down')):
      with self.assertRaises(DatabaseError):
        self._post()
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.CREATING)

    res = self._post()
    self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(len(self.mp.preference_calls), 1)

  # Throttle -----------------------------------------------------------------------------------------
  def test_endpoint_is_throttled(self):
    from ..public_views import PublicAppointmentCheckoutView
    self.assertEqual(PublicAppointmentCheckoutView.throttle_scope, 'public_appointments_checkout')
    self.assertTrue(PublicAppointmentCheckoutView.throttle_classes)


# El webhook `flow=appointment` (Slice 6B) se cubre en test_appointment_payment_webhook.py.
