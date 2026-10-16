"""Tests para la reserva pública `/t/[slug]` (Slice 4B).

Cubre: creación con/sin seña, cálculo de seña, snapshot inmutable,
expiración de holds (dinámica + management command), bloqueo de
disponibilidad, endpoint de estado por `public_token`, y que el payload del
cliente no puede alterar nada que deba resolverse server-side.

La concurrencia real (varios requests simultáneos al mismo slot) vive en
`test_public_booking_concurrency.py` (requiere `TransactionTestCase`).
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.business.models import Business, BusinessPlan, Subscription

from ..models import (
    Appointment,
    AppointmentPayment,
    AppointmentProfessional,
    AppointmentSchedule,
    AppointmentService,
)

# 2026-09-21 es un lunes (weekday=0), igual que en test_public.py/test_availability.py.
MONDAY = dt.date(2026, 9, 21)
TZ_OFFSET = '-03:00'


def _create_business(
    name='Turnos Biz',
    slug='turnos-biz',
    timezone='America/Argentina/Buenos_Aires',
    default_service='appointments',
    status='active',
    with_subscription=True,
):
    biz = Business.objects.create(
        name=name, default_service=default_service, slug=slug, timezone=timezone, status=status,
    )
    if with_subscription:
        Subscription.objects.create(
            business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
        )
    return biz


def _slot(hour: int, minute: int = 0) -> str:
    return f'{MONDAY.isoformat()}T{hour:02d}:{minute:02d}:00{TZ_OFFSET}'


class PublicAppointmentBookingCreateViewTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.biz = _create_business()

        self.service_none = AppointmentService.objects.create(
            business=self.biz, name='Corte simple', duration_minutes=30, price=Decimal('1000'),
            deposit_type=AppointmentService.DepositType.NONE,
        )
        self.service_fixed = AppointmentService.objects.create(
            business=self.biz, name='Color', duration_minutes=30, price=Decimal('5000'),
            deposit_type=AppointmentService.DepositType.FIXED, deposit_value=Decimal('1500'),
        )
        self.service_percentage = AppointmentService.objects.create(
            business=self.biz, name='Alisado', duration_minutes=30, price=Decimal('5000'),
            deposit_type=AppointmentService.DepositType.PERCENTAGE, deposit_value=Decimal('20'),
        )

        self.professional = AppointmentProfessional.objects.create(business=self.biz, name='Ana')
        self.professional.services.add(self.service_none, self.service_fixed, self.service_percentage)

        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=self.professional, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )

    def _post(self, slug=None, **overrides):
        # Slice 7B.1: todos los servicios de este setUp tienen profesional →
        # el profesional es obligatorio (los tests del carril "sin profesional"
        # usan un servicio sin profesionales asignados).
        payload = {
            'service': str(self.service_none.id),
            'professional': str(self.professional.id),
            'start': _slot(10, 0),
            'customer_name': 'Cliente de prueba',
            'customer_phone': '+54 9 11 5555-5555',
        }
        payload.update(overrides)
        return self.client.post(
            f'/api/v1/appointments/public/{slug or self.biz.slug}/bookings/', payload, format='json',
        )

    # 1. servicio none -> confirmed directo ------------------------------------------
    def test_service_without_deposit_creates_confirmed_appointment(self):
        resp = self._post(service=str(self.service_none.id), start=_slot(10, 0))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['status'], 'confirmed')
        self.assertIsNone(resp.data['expires_at'])

        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        self.assertEqual(appt.status, Appointment.Status.CONFIRMED)
        self.assertEqual(appt.source, Appointment.Source.PUBLIC)
        self.assertIsNone(appt.expires_at)

    # 2. servicio fixed -> pending_payment --------------------------------------------
    def test_service_with_fixed_deposit_creates_pending_payment(self):
        resp = self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['status'], 'pending_payment')
        self.assertIsNotNone(resp.data['expires_at'])

    # 3. servicio percentage -> pending_payment ---------------------------------------
    def test_service_with_percentage_deposit_creates_pending_payment(self):
        resp = self._post(service=str(self.service_percentage.id), start=_slot(12, 0))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['status'], 'pending_payment')
        self.assertIsNotNone(resp.data['expires_at'])

    # 4. cálculo de seña fixed ---------------------------------------------------------
    def test_deposit_amount_fixed(self):
        resp = self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Decimal(resp.data['deposit_amount']), Decimal('1500.00'))

    # 5. cálculo de seña percentage -----------------------------------------------------
    def test_deposit_amount_percentage(self):
        resp = self._post(service=str(self.service_percentage.id), start=_slot(12, 0))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        # 20% de 5000 = 1000.00
        self.assertEqual(Decimal(resp.data['deposit_amount']), Decimal('1000.00'))

    # 7. expires_at ~10 minutos ----------------------------------------------------------
    def test_expires_at_is_roughly_ten_minutes_from_now(self):
        before = dj_timezone.now()
        resp = self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
        after = dj_timezone.now()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        self.assertGreaterEqual(appt.expires_at, before + dt.timedelta(minutes=9, seconds=55))
        self.assertLessEqual(appt.expires_at, after + dt.timedelta(minutes=10, seconds=5))

    # 6. snapshots ------------------------------------------------------------------------
    def test_price_snapshot_is_immutable_after_service_changes(self):
        resp = self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        self.assertEqual(appt.service_name, 'Color')
        self.assertEqual(appt.service_price, Decimal('5000.00'))
        self.assertEqual(appt.deposit_type, AppointmentService.DepositType.FIXED)
        self.assertEqual(appt.deposit_value, Decimal('1500.00'))

        self.service_fixed.price = Decimal('9999')
        self.service_fixed.deposit_value = Decimal('1')
        self.service_fixed.save()

        appt.refresh_from_db()
        self.assertEqual(appt.service_price, Decimal('5000.00'))
        self.assertEqual(appt.deposit_value, Decimal('1500.00'))

    # 8. hold vigente bloquea availability -------------------------------------------------
    def test_pending_payment_hold_blocks_availability_while_valid(self):
        resp = self._post(
            service=str(self.service_fixed.id), professional=str(self.professional.id), start=_slot(11, 0),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        avail = self.client.get(
            f'/api/v1/appointments/public/{self.biz.slug}/availability/',
            {'service': str(self.service_fixed.id), 'date': MONDAY.isoformat(), 'professional': str(self.professional.id)},
        )
        starts = [s['start'][11:16] for s in avail.data['slots']]
        self.assertNotIn('11:00', starts)

    # 9. hold vencido libera availability ---------------------------------------------------
    def test_expired_hold_frees_availability(self):
        resp = self._post(
            service=str(self.service_fixed.id), professional=str(self.professional.id), start=_slot(11, 0),
        )
        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        appt.expires_at = dj_timezone.now() - dt.timedelta(minutes=1)
        appt.save(update_fields=['expires_at'])

        avail = self.client.get(
            f'/api/v1/appointments/public/{self.biz.slug}/availability/',
            {'service': str(self.service_fixed.id), 'date': MONDAY.isoformat(), 'professional': str(self.professional.id)},
        )
        starts = [s['start'][11:16] for s in avail.data['slots']]
        self.assertIn('11:00', starts)

    # 10. command cambia vencidos a expired ---------------------------------------------------
    def test_expire_command_updates_status_to_expired(self):
        resp = self._post(service=str(self.service_fixed.id), start=_slot(11, 0))
        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        appt.expires_at = dj_timezone.now() - dt.timedelta(minutes=1)
        appt.save(update_fields=['expires_at'])

        call_command('expire_appointment_holds')

        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointment.Status.EXPIRED)

    # 11. expired no bloquea -------------------------------------------------------------------
    def test_expired_appointment_does_not_block_new_booking(self):
        resp = self._post(
            service=str(self.service_fixed.id), professional=str(self.professional.id), start=_slot(11, 0),
        )
        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        appt.status = Appointment.Status.EXPIRED
        appt.expires_at = dj_timezone.now() - dt.timedelta(minutes=1)
        appt.save(update_fields=['status', 'expires_at'])

        resp2 = self._post(
            service=str(self.service_none.id), professional=str(self.professional.id), start=_slot(11, 0),
        )
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.data)

    # 12. confirmed sí bloquea ------------------------------------------------------------------
    def test_confirmed_appointment_blocks_same_slot(self):
        resp = self._post(
            service=str(self.service_none.id), professional=str(self.professional.id), start=_slot(11, 0),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        resp2 = self._post(
            service=str(self.service_fixed.id), professional=str(self.professional.id), start=_slot(11, 0),
        )
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)

    # 17. slot ya ocupado (variante explícita, sin profesional) --------------------------------
    def test_occupied_slot_without_professional_is_rejected(self):
        service_no_prof = AppointmentService.objects.create(
            business=self.biz, name='Consulta', duration_minutes=30, price=Decimal('1000'),
        )
        resp = self._post(service=str(service_no_prof.id), professional=None, start=_slot(13, 0))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        resp2 = self._post(service=str(service_no_prof.id), professional=None, start=_slot(13, 0))
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)

    # 15. cross-tenant service -------------------------------------------------------------------
    def test_service_from_other_business_rejected(self):
        other = _create_business(name='Otro', slug='otro-booking-biz')
        other_service = AppointmentService.objects.create(business=other, name='Corte', duration_minutes=30, price=100)
        resp = self._post(service=str(other_service.id), start=_slot(10, 0))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service', resp.data)
        self.assertFalse(Appointment.objects.filter(business=self.biz).exists())

    # 16. cross-tenant professional --------------------------------------------------------------
    def test_professional_from_other_business_rejected(self):
        other = _create_business(name='Otro', slug='otro-booking-biz-2')
        other_professional = AppointmentProfessional.objects.create(business=other, name='Bruno')
        resp = self._post(
            service=str(self.service_none.id), professional=str(other_professional.id), start=_slot(10, 0),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    # 21. payload no puede alterar precio/status/end_at/business ----------------------------------
    def test_payload_cannot_override_server_resolved_fields(self):
        other = _create_business(name='Otro', slug='otro-booking-biz-3')
        resp = self._post(
            service=str(self.service_fixed.id),
            start=_slot(11, 0),
            status='confirmed',
            price='1.00',
            end='2000-01-01T00:00:00-03:00',
            business_id=str(other.id),
            business=str(other.id),
            deposit_amount='0.01',
            source='manual',
            duration=1,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        self.assertEqual(appt.business_id, self.biz.id)
        self.assertEqual(appt.service_price, Decimal('5000.00'))
        self.assertEqual(appt.status, Appointment.Status.PENDING_PAYMENT)
        self.assertEqual(appt.source, Appointment.Source.PUBLIC)
        self.assertEqual(appt.end_at, appt.start_at + dt.timedelta(minutes=self.service_fixed.duration_minutes))

    # 22. business sin appointments ------------------------------------------------------------------
    def test_business_without_appointments_service_returns_404(self):
        other = _create_business(
            name='Restaurante', slug='restaurante-booking-biz', default_service='restaurante',
            with_subscription=False,
        )
        Subscription.objects.create(business=other, plan=BusinessPlan.PLUS, service='restaurante', status='active')
        resp = self._post(slug=other.slug, service=str(self.service_none.id), start=_slot(10, 0))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_slug_returns_404(self):
        resp = self._post(slug='no-existe', service=str(self.service_none.id), start=_slot(10, 0))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # 23. datos de cliente inválidos ---------------------------------------------------------------
    def test_customer_name_too_short_returns_400(self):
        resp = self._post(customer_name='A')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_phone_too_short_returns_400(self):
        resp = self._post(customer_phone='123')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_required_fields_returns_400(self):
        resp = self.client.post(
            f'/api/v1/appointments/public/{self.biz.slug}/bookings/', {}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ('service', 'start', 'customer_name', 'customer_phone'):
            self.assertIn(field, resp.data)


class PublicAppointmentBookingStatusViewTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.biz = _create_business()
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=Decimal('1000'),
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )
        resp = self.client.post(
            f'/api/v1/appointments/public/{self.biz.slug}/bookings/',
            {
                'service': str(self.service.id),
                'start': _slot(10, 0),
                'customer_name': 'Cliente de prueba',
                'customer_phone': '+54 9 11 5555-5555',
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        self.public_token = resp.data['public_token']

    def _get_status(self, slug=None, token=None):
        return self.client.get(
            f'/api/v1/appointments/public/{slug or self.biz.slug}/bookings/{token or self.public_token}/',
        )

    # 18. public_token válido -------------------------------------------------------------------
    def test_valid_public_token_returns_booking_status(self):
        resp = self._get_status()
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], 'confirmed')
        self.assertEqual(resp.data['service']['name'], 'Corte')
        self.assertEqual(resp.data['customer_name'], 'Cliente de prueba')
        self.assertNotIn('id', resp.data)

    # 19. token inválido ------------------------------------------------------------------------
    def test_unknown_token_returns_404(self):
        resp = self._get_status(token=str(uuid.uuid4()))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_malformed_token_returns_404(self):
        resp = self.client.get(f'/api/v1/appointments/public/{self.biz.slug}/bookings/not-a-uuid/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # 20. token perteneciente a otro slug ----------------------------------------------------------
    def test_token_from_other_business_returns_404(self):
        other = _create_business(name='Otro', slug='otro-status-biz')
        resp = self._get_status(slug=other.slug)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # 11 (parte 2). estado expirado se refleja aunque el status físico no se actualizó --------------
    def test_expired_hold_is_reflected_even_before_command_runs(self):
        fixed_service = AppointmentService.objects.create(
            business=self.biz, name='Con seña', duration_minutes=30, price=Decimal('2000'),
            deposit_type=AppointmentService.DepositType.FIXED, deposit_value=Decimal('500'),
        )
        resp = self.client.post(
            f'/api/v1/appointments/public/{self.biz.slug}/bookings/',
            {
                'service': str(fixed_service.id),
                'start': _slot(14, 0),
                'customer_name': 'Cliente con seña',
                'customer_phone': '+54 9 11 5555-5556',
            },
            format='json',
        )
        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        appt.expires_at = dj_timezone.now() - dt.timedelta(minutes=1)
        appt.save(update_fields=['expires_at'])

        status_resp = self._get_status(token=resp.data['public_token'])
        self.assertEqual(status_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(status_resp.data['status'], 'expired')
        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointment.Status.PENDING_PAYMENT)


class PublicAppointmentBookingPaymentStatusTests(APITestCase):
    """Slice 6C: `payment_status` público normalizado + no exposición de datos internos."""

    def setUp(self):
        cache.clear()
        self.biz = _create_business(slug='turnos-6c')
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Con seña', duration_minutes=30, price=Decimal('2000'),
            deposit_type=AppointmentService.DepositType.FIXED, deposit_value=Decimal('500'),
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )
        resp = self.client.post(
            f'/api/v1/appointments/public/{self.biz.slug}/bookings/',
            {
                'service': str(self.service.id),
                'start': _slot(11, 0),
                'customer_name': 'Cliente 6C',
                'customer_phone': '+54 9 11 5555-0000',
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        self.public_token = resp.data['public_token']
        self.appointment = Appointment.objects.get(public_token=self.public_token)

    def _get(self):
        resp = self.client.get(f'/api/v1/appointments/public/{self.biz.slug}/bookings/{self.public_token}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data

    def _payment(self, status_value, **fields):
        payment_id = uuid.uuid4()
        return AppointmentPayment.objects.create(
            id=payment_id,
            business=self.biz,
            appointment=self.appointment,
            external_reference=AppointmentPayment.build_external_reference(payment_id),
            amount=Decimal('500'),
            status=status_value,
            **fields,
        )

    def test_payment_status_is_null_without_attempts(self):
        self.assertIsNone(self._get()['payment_status'])

    def test_create_response_includes_null_payment_status(self):
        resp = self.client.post(
            f'/api/v1/appointments/public/{self.biz.slug}/bookings/',
            {
                'service': str(self.service.id),
                'start': _slot(12, 0),
                'customer_name': 'Otro cliente',
                'customer_phone': '+54 9 11 5555-0001',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('payment_status', resp.data)
        self.assertIsNone(resp.data['payment_status'])

    def test_pending_attempt_is_reported(self):
        self._payment(AppointmentPayment.Status.PENDING, checkout_url='https://mp.example/checkout')
        self.assertEqual(self._get()['payment_status'], 'pending')

    def test_latest_terminal_attempt_is_reported(self):
        self._payment(AppointmentPayment.Status.ERROR, failure_reason='mp_rejected:x')
        self._payment(AppointmentPayment.Status.REJECTED, provider_payment_id='111')
        self.assertEqual(self._get()['payment_status'], 'rejected')

    def test_active_attempt_wins_over_older_terminal_attempt(self):
        self._payment(AppointmentPayment.Status.REJECTED, provider_payment_id='222')
        self._payment(AppointmentPayment.Status.UNCERTAIN, failure_reason='mp_uncertain:504')
        self.assertEqual(self._get()['payment_status'], 'uncertain')

    def test_requires_review_wins_over_newer_attempts(self):
        self._payment(
            AppointmentPayment.Status.REQUIRES_REVIEW,
            provider_payment_id='333',
            review_reason=AppointmentPayment.ReviewReason.APPROVED_AFTER_EXPIRY,
        )
        self._payment(AppointmentPayment.Status.CANCELLED)
        self.assertEqual(self._get()['payment_status'], 'requires_review')

    def test_approved_attempt_is_reported(self):
        self._payment(AppointmentPayment.Status.APPROVED, provider_payment_id='444')
        self.assertEqual(self._get()['payment_status'], 'approved')

    def test_internal_payment_fields_are_never_exposed(self):
        self._payment(
            AppointmentPayment.Status.REQUIRES_REVIEW,
            provider_payment_id='PROVIDER-PAY-SECRET',
            provider_preference_id='PREF-SECRET',
            checkout_url='https://mp.example/checkout/PREF-SECRET',
            failure_reason='mp_uncertain:SECRET',
            review_reason=AppointmentPayment.ReviewReason.SLOT_CONFLICT,
        )
        data = self._get()
        self.assertEqual(
            set(data.keys()),
            {
                'public_token', 'status', 'expires_at', 'start_at', 'end_at', 'customer_name',
                'service', 'professional', 'deposit_amount', 'payment_status',
                'contact_whatsapp_url',  # Slice 6D: link wa.me o null, nunca el teléfono crudo
            },
        )
        body = str(data)
        for needle in (
            'PROVIDER-PAY-SECRET', 'PREF-SECRET', 'APPOINTMENT_PAYMENT-', 'mp_uncertain',
            'slot_conflict', str(self.appointment.id),
        ):
            self.assertNotIn(needle, body)
