"""
Tests para `Appointment` (Slice 3A): creación manual, snapshots, cálculo de
`end_at`, integración con el motor de disponibilidad, solapamiento y
transiciones de estado.

El aislamiento multi-tenant vive en `test_multitenant.py` (mismo patrón que
el resto de `apps.appointments`) y la concurrencia real contra PostgreSQL
vive en `test_appointments_concurrency.py` (requiere `TransactionTestCase`).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription

from ..models import (
    Appointment,
    AppointmentProfessional,
    AppointmentSchedule,
    AppointmentService,
)

User = get_user_model()

# 2026-09-21 es un lunes (weekday=0); mismo día canónico que
# `test_availability.py` para que los horarios de negocio/profesional
# armados en `setUp` coincidan.
MONDAY = dt.date(2026, 9, 21)


def _create_business(name='Turnos Biz', slug='turnos-biz', timezone='America/Argentina/Buenos_Aires'):
    biz = Business.objects.create(name=name, default_service='appointments', slug=slug, timezone=timezone)
    Subscription.objects.create(business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active')
    return biz


def _auth_client(client, business, role='owner'):
    user = User.objects.create_user(username=f'u-{business.slug}', password='pass1234')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


def _iso(date, time_str, offset='-03:00'):
    return f'{date.isoformat()}T{time_str}:00{offset}'


class AppointmentApiTestCase(APITestCase):
    """Base común: negocio con horario Lunes 09:00-18:00 (negocio y profesional)."""

    def setUp(self):
        self.biz = _create_business()
        self.owner = _auth_client(self.client, self.biz, role='owner')

        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=Decimal('100'),
            deposit_type=AppointmentService.DepositType.FIXED, deposit_value=Decimal('20'),
        )
        self.other_service = AppointmentService.objects.create(
            business=self.biz, name='Coloración', duration_minutes=60, price=Decimal('500'),
        )

        self.professional = AppointmentProfessional.objects.create(business=self.biz, name='Ana')
        self.professional.services.add(self.service)

        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=self.professional, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )

    def _create_payload(self, **overrides):
        payload = {
            'service_id': str(self.service.id),
            'professional_id': str(self.professional.id),
            'start_at': _iso(MONDAY, '10:00'),
            'customer_name': 'Juana Pérez',
            'customer_phone': '1122334455',
            'customer_email': 'juana@example.com',
            'notes': 'Primera vez',
        }
        payload.update(overrides)
        return payload


class CreateAppointmentTests(AppointmentApiTestCase):

    def test_creates_manual_appointment(self):
        resp = self.client.post('/api/v1/appointments/appointments/', self._create_payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['status'], 'confirmed')
        self.assertEqual(resp.data['source'], 'manual')
        self.assertEqual(resp.data['customer_name'], 'Juana Pérez')

        appointment = Appointment.objects.get(pk=resp.data['id'])
        self.assertEqual(appointment.business_id, self.biz.id)
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertEqual(appointment.source, Appointment.Source.MANUAL)

    def test_snapshot_captured_at_creation(self):
        resp = self.client.post('/api/v1/appointments/appointments/', self._create_payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        appointment = Appointment.objects.get(pk=resp.data['id'])

        self.assertEqual(appointment.service_name, 'Corte')
        self.assertEqual(appointment.service_duration_minutes, 30)
        self.assertEqual(appointment.service_price, Decimal('100.00'))
        self.assertEqual(appointment.deposit_type, AppointmentService.DepositType.FIXED)
        self.assertEqual(appointment.deposit_value, Decimal('20.00'))

        # Cambiar el servicio después no debe alterar el turno ya creado.
        self.service.name = 'Corte premium'
        self.service.price = Decimal('999')
        self.service.save(update_fields=['name', 'price'])
        appointment.refresh_from_db()
        self.assertEqual(appointment.service_name, 'Corte')
        self.assertEqual(appointment.service_price, Decimal('100.00'))

    def test_end_at_computed_server_side_ignores_client_value(self):
        payload = self._create_payload()
        payload['end_at'] = _iso(MONDAY, '23:00')  # debe ser ignorado (read-only)
        resp = self.client.post('/api/v1/appointments/appointments/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        appointment = Appointment.objects.get(pk=resp.data['id'])
        expected_end = appointment.start_at + dt.timedelta(minutes=30)
        self.assertEqual(appointment.end_at, expected_end)

    def test_professional_is_optional(self):
        # Slice 7B.1: opcional solo para servicios SIN profesionales elegibles.
        payload = self._create_payload(service_id=str(self.other_service.id))
        del payload['professional_id']
        resp = self.client.post('/api/v1/appointments/appointments/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIsNone(resp.data['professional'])

        appointment = Appointment.objects.get(pk=resp.data['id'])
        self.assertIsNone(appointment.professional)

    def test_professional_not_performing_service_is_rejected(self):
        payload = self._create_payload(service_id=str(self.other_service.id))
        resp = self.client.post('/api/v1/appointments/appointments/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    def test_slot_outside_availability_is_rejected(self):
        payload = self._create_payload(start_at=_iso(MONDAY, '20:00'))
        resp = self.client.post('/api/v1/appointments/appointments/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_at', resp.data)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_overlapping_appointment_is_rejected(self):
        first = self.client.post('/api/v1/appointments/appointments/', self._create_payload(), format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)

        overlapping = self._create_payload(start_at=_iso(MONDAY, '10:15'), customer_name='Otro Cliente')
        resp = self.client.post('/api/v1/appointments/appointments/', overlapping, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_at', resp.data)
        self.assertEqual(Appointment.objects.filter(status=Appointment.Status.CONFIRMED).count(), 1)

    def test_business_level_appointments_without_professional_can_still_overlap(self):
        payload = self._create_payload(service_id=str(self.other_service.id))
        del payload['professional_id']
        first = self.client.post('/api/v1/appointments/appointments/', payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)

        overlapping = self._create_payload(
            service_id=str(self.other_service.id), start_at=_iso(MONDAY, '10:15'), customer_name='Otro Cliente',
        )
        del overlapping['professional_id']
        resp = self.client.post('/api/v1/appointments/appointments/', overlapping, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_at', resp.data)

    def test_missing_required_customer_fields(self):
        payload = self._create_payload()
        del payload['customer_phone']
        resp = self.client.post('/api/v1/appointments/appointments/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('customer_phone', resp.data)

    def test_never_trusts_business_id_from_frontend(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-appt')
        payload = self._create_payload(business=str(other_biz.id))
        resp = self.client.post('/api/v1/appointments/appointments/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        created = Appointment.objects.get(pk=resp.data['id'])
        self.assertEqual(created.business_id, self.biz.id)


class UpdateAppointmentTests(AppointmentApiTestCase):

    def setUp(self):
        super().setUp()
        resp = self.client.post('/api/v1/appointments/appointments/', self._create_payload(), format='json')
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        self.appointment_id = resp.data['id']

    def test_reschedule_updates_start_and_end(self):
        resp = self.client.patch(
            f'/api/v1/appointments/appointments/{self.appointment_id}/',
            {'start_at': _iso(MONDAY, '14:00')},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        appointment = Appointment.objects.get(pk=self.appointment_id)
        expected_start = dt.datetime.fromisoformat(_iso(MONDAY, '14:00'))
        self.assertEqual(appointment.start_at, expected_start)
        self.assertEqual(appointment.end_at, expected_start + dt.timedelta(minutes=30))

    def test_reschedule_into_occupied_slot_is_rejected(self):
        other = self.client.post(
            '/api/v1/appointments/appointments/',
            self._create_payload(start_at=_iso(MONDAY, '15:00'), customer_name='Otro'),
            format='json',
        )
        self.assertEqual(other.status_code, status.HTTP_201_CREATED, other.data)

        resp = self.client.patch(
            f'/api/v1/appointments/appointments/{self.appointment_id}/',
            {'start_at': _iso(MONDAY, '15:15')},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_at', resp.data)

    def test_cancel_frees_availability_for_new_appointment(self):
        resp = self.client.patch(
            f'/api/v1/appointments/appointments/{self.appointment_id}/',
            {'status': 'cancelled'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        resp2 = self.client.post(
            '/api/v1/appointments/appointments/',
            self._create_payload(customer_name='Cliente nuevo'),
            format='json',
        )
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.data)

    def test_delete_maps_to_cancelled_not_hard_delete(self):
        resp = self.client.delete(f'/api/v1/appointments/appointments/{self.appointment_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        appointment = Appointment.objects.get(pk=self.appointment_id)
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)

    def test_completed_does_not_block_future_slot(self):
        resp = self.client.patch(
            f'/api/v1/appointments/appointments/{self.appointment_id}/',
            {'status': 'completed'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        resp2 = self.client.post(
            '/api/v1/appointments/appointments/',
            self._create_payload(customer_name='Cliente nuevo'),
            format='json',
        )
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.data)

    def test_no_show_does_not_block_future_slot(self):
        resp = self.client.patch(
            f'/api/v1/appointments/appointments/{self.appointment_id}/',
            {'status': 'no_show'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        resp2 = self.client.post(
            '/api/v1/appointments/appointments/',
            self._create_payload(customer_name='Cliente nuevo'),
            format='json',
        )
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.data)

    def test_mark_no_show_status_directly(self):
        resp = self.client.patch(
            f'/api/v1/appointments/appointments/{self.appointment_id}/',
            {'status': 'no_show'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(Appointment.objects.get(pk=self.appointment_id).status, Appointment.Status.NO_SHOW)


class ListAppointmentTests(AppointmentApiTestCase):

    def test_filters_by_date_professional_and_status(self):
        self.client.post('/api/v1/appointments/appointments/', self._create_payload(), format='json')
        other_day = self._create_payload(start_at=_iso(MONDAY + dt.timedelta(days=7), '10:00'), customer_name='Otro día')
        self.client.post('/api/v1/appointments/appointments/', other_day, format='json')

        resp = self.client.get(f'/api/v1/appointments/appointments/?date={MONDAY.isoformat()}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

        resp = self.client.get(f'/api/v1/appointments/appointments/?professional={self.professional.id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

        resp = self.client.get('/api/v1/appointments/appointments/?status=confirmed')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)
