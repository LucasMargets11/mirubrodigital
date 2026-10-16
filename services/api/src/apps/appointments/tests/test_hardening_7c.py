"""Slice 7C — hardening previo al piloto (backend).

1. Seña: regla canónica `deposit_config_error` (serializer + `model.clean`) y
   guard en la reserva pública para servicios legacy con monto de seña 0.
2. Expiración automática: task Celery `appointments.expire_holds` + Beat.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Appointment, AppointmentPayment, AppointmentService
from ..services.deposit import deposit_config_error
from ..tasks import expire_appointment_holds
from . import test_public_booking
from .test_public_booking import _slot
from .test_services import _auth_client, _create_business


class DepositConfigRuleTests(TestCase):
  def _err(self, deposit_type, value, price='1000'):
    return deposit_config_error(price=Decimal(price), deposit_type=deposit_type, deposit_value=Decimal(value))

  def test_none_is_always_valid(self):
    self.assertIsNone(self._err('none', '0'))
    self.assertIsNone(self._err('none', '500'))

  def test_fixed_zero_rejected(self):
    self.assertIsNotNone(self._err('fixed', '0'))

  def test_fixed_positive_valid(self):
    self.assertIsNone(self._err('fixed', '1'))
    self.assertIsNone(self._err('fixed', '1000'))

  def test_fixed_over_price_rejected(self):
    self.assertIsNotNone(self._err('fixed', '1000.01'))

  def test_fixed_with_price_zero_rejected(self):
    self.assertIsNotNone(self._err('fixed', '0', price='0'))
    self.assertIsNotNone(self._err('fixed', '1', price='0'))

  def test_percentage_range(self):
    self.assertIsNotNone(self._err('percentage', '0'))
    self.assertIsNone(self._err('percentage', '0.01'))
    self.assertIsNone(self._err('percentage', '100'))
    self.assertIsNotNone(self._err('percentage', '100.01'))

  def test_percentage_with_price_zero_rejected(self):
    self.assertIsNotNone(self._err('percentage', '50', price='0'))

  def test_model_clean_uses_same_rule(self):
    biz = _create_business()
    service = AppointmentService(
      business=biz, name='Color', duration_minutes=30, price=Decimal('1000'),
      deposit_type=AppointmentService.DepositType.FIXED, deposit_value=Decimal('0'),
    )
    with self.assertRaises(ValidationError) as ctx:
      service.full_clean()
    self.assertIn('deposit_value', ctx.exception.message_dict)

    service.deposit_value = Decimal('300')
    service.full_clean()  # no levanta


class DepositSerializerTests(APITestCase):
  def setUp(self):
    self.biz = _create_business()
    _auth_client(self.client, self.biz, role='owner')

  def _create(self, **overrides):
    payload = {
      'name': f'Servicio {uuid.uuid4().hex[:6]}', 'duration_minutes': 30, 'price': '1000.00',
      'deposit_type': 'none', 'deposit_value': '0',
    }
    payload.update(overrides)
    return self.client.post('/api/v1/appointments/services/', payload, format='json')

  def test_fixed_zero_rejected_on_create(self):
    resp = self._create(deposit_type='fixed', deposit_value='0')
    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('deposit_value', resp.data)

  def test_fixed_positive_valid(self):
    resp = self._create(deposit_type='fixed', deposit_value='250')
    self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
    self.assertEqual(resp.data['deposit_value'], '250.00')

  def test_fixed_over_price_rejected(self):
    resp = self._create(deposit_type='fixed', deposit_value='1500')
    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

  def test_none_still_forces_zero(self):
    resp = self._create(deposit_type='none', deposit_value='500')
    self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
    self.assertEqual(resp.data['deposit_value'], '0.00')

  def test_percentage_unchanged(self):
    self.assertEqual(self._create(deposit_type='percentage', deposit_value='50').status_code, 201)
    self.assertEqual(self._create(deposit_type='percentage', deposit_value='0').status_code, 400)
    self.assertEqual(self._create(deposit_type='percentage', deposit_value='101').status_code, 400)

  def test_price_zero_with_fixed_rejected(self):
    resp = self._create(price='0', deposit_type='fixed', deposit_value='0')
    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

  def test_partial_update_to_fixed_zero_rejected(self):
    resp = self._create(deposit_type='fixed', deposit_value='250')
    patch = self.client.patch(
      f"/api/v1/appointments/services/{resp.data['id']}/", {'deposit_value': '0'}, format='json',
    )
    self.assertEqual(patch.status_code, status.HTTP_400_BAD_REQUEST)

  def test_partial_update_price_below_fixed_rejected(self):
    resp = self._create(deposit_type='fixed', deposit_value='250')
    patch = self.client.patch(f"/api/v1/appointments/services/{resp.data['id']}/", {'price': '0'}, format='json')
    self.assertEqual(patch.status_code, status.HTTP_400_BAD_REQUEST)


class LegacyZeroDepositBookingTests(APITestCase):
  """Servicios legacy `fixed=0` (no migrados): la reserva pública no crea un
  `pending_payment` imposible de pagar."""

  # Referencia vía el módulo: importar la clase acá la haría correr dos veces.
  setUp = test_public_booking.PublicAppointmentBookingCreateViewTests.setUp
  _post = test_public_booking.PublicAppointmentBookingCreateViewTests._post

  def _legacy(self, **fields):
    # `.update()` saltea la validación, como un dato previo a 7C.
    AppointmentService.objects.filter(pk=self.service_fixed.pk).update(**fields)

  def test_legacy_fixed_zero_booking_rejected(self):
    self._legacy(deposit_value=Decimal('0'))
    resp = self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('service', resp.data)
    self.assertFalse(Appointment.objects.filter(service=self.service_fixed).exists())

  def test_legacy_percentage_with_price_zero_booking_rejected(self):
    AppointmentService.objects.filter(pk=self.service_percentage.pk).update(price=Decimal('0'))
    resp = self._post(service=str(self.service_percentage.id), start=_slot(12, 0))
    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(Appointment.objects.filter(service=self.service_percentage).exists())

  def test_valid_fixed_still_creates_pending_payment(self):
    resp = self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
    self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
    self.assertEqual(resp.data['status'], 'pending_payment')
    self.assertGreater(Decimal(resp.data['deposit_amount']), 0)

  def test_no_pending_payment_with_zero_amount_is_creatable(self):
    self._legacy(deposit_value=Decimal('0'))
    self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
    for appt in Appointment.objects.filter(status=Appointment.Status.PENDING_PAYMENT):
      self.assertGreater(appt.deposit_amount, 0)


class ExpireHoldsTaskTests(TestCase):
  def setUp(self):
    self.biz = _create_business()
    self.service = AppointmentService.objects.create(
      business=self.biz, name='Color', duration_minutes=30, price=Decimal('1000'),
      deposit_type=AppointmentService.DepositType.FIXED, deposit_value=Decimal('300'),
    )
    self.now = dj_timezone.now()

  def _appt(self, status_value, *, expires_delta, hour):
    start = (self.now + dt.timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return Appointment.objects.create(
      business=self.biz, service=self.service, start_at=start, end_at=start + dt.timedelta(minutes=30),
      status=status_value,
      expires_at=self.now + expires_delta if expires_delta is not None else None,
      source=Appointment.Source.PUBLIC, service_name=self.service.name, service_duration_minutes=30,
      service_price=self.service.price, deposit_type=self.service.deposit_type,
      deposit_value=self.service.deposit_value, customer_name='Cliente', customer_phone='+5491155555555',
    )

  def test_task_expires_due_hold_and_keeps_others(self):
    due = self._appt(Appointment.Status.PENDING_PAYMENT, expires_delta=-dt.timedelta(minutes=1), hour=10)
    live = self._appt(Appointment.Status.PENDING_PAYMENT, expires_delta=dt.timedelta(minutes=5), hour=11)
    confirmed = self._appt(Appointment.Status.CONFIRMED, expires_delta=-dt.timedelta(minutes=1), hour=12)

    payment_id = uuid.uuid4()
    payment = AppointmentPayment.objects.create(
      id=payment_id, business=self.biz, appointment=due,
      external_reference=AppointmentPayment.build_external_reference(payment_id),
      amount=Decimal('300'), status=AppointmentPayment.Status.PENDING,
    )

    result = expire_appointment_holds.apply().get()
    self.assertEqual(result, {'expired': 1})

    due.refresh_from_db()
    live.refresh_from_db()
    confirmed.refresh_from_db()
    self.assertEqual(due.status, Appointment.Status.EXPIRED)
    self.assertIsNotNone(due.expires_at)  # el webhook lo sigue usando
    self.assertEqual(live.status, Appointment.Status.PENDING_PAYMENT)
    self.assertEqual(confirmed.status, Appointment.Status.CONFIRMED)

    payment.refresh_from_db()
    self.assertEqual(payment.status, AppointmentPayment.Status.PENDING)

  def test_task_is_idempotent(self):
    self._appt(Appointment.Status.PENDING_PAYMENT, expires_delta=-dt.timedelta(minutes=1), hour=10)
    self.assertEqual(expire_appointment_holds.apply().get(), {'expired': 1})
    self.assertEqual(expire_appointment_holds.apply().get(), {'expired': 0})
    self.assertEqual(Appointment.objects.filter(status=Appointment.Status.EXPIRED).count(), 1)

  def test_task_registered_in_beat_schedule(self):
    entries = [e for e in settings.CELERY_BEAT_SCHEDULE.values() if e['task'] == 'appointments.expire_holds']
    self.assertEqual(len(entries), 1)
    self.assertEqual(expire_appointment_holds.name, 'appointments.expire_holds')
