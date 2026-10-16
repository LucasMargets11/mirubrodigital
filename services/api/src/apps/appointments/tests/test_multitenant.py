"""
Multi-tenant isolation tests for `apps.appointments`.

Verifies Business A can never list, view, or edit Business B's categories or
services, and that a service's category must belong to the same Business —
mirroring the isolation guarantees already enforced in `apps.catalog`.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription, BusinessPlan

from ..models import (
    Appointment,
    AppointmentCategory,
    AppointmentException,
    AppointmentProfessional,
    AppointmentSchedule,
    AppointmentService,
)

User = get_user_model()


def _create_business(name, slug):
    biz = Business.objects.create(name=name, default_service='appointments', slug=slug)
    Subscription.objects.create(business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active')
    return biz


def _auth_client(client, business, role='owner'):
    user = User.objects.create_user(username=f'u-{business.slug}', password='pass1234')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


class MultiTenantCategoryTests(APITestCase):

    def setUp(self):
        self.biz_a = _create_business('Business A', 'biz-a')
        self.biz_b = _create_business('Business B', 'biz-b')
        self.category_b = AppointmentCategory.objects.create(business=self.biz_b, name='Categoría de B')
        _auth_client(self.client, self.biz_a, role='owner')

    def test_business_a_cannot_list_business_b_categories(self):
        resp = self.client.get('/api/v1/appointments/categories/?include_inactive=true')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in resp.data]
        self.assertNotIn(str(self.category_b.id), ids)

    def test_business_a_cannot_retrieve_business_b_category(self):
        resp = self.client.get(f'/api/v1/appointments/categories/{self.category_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_a_cannot_edit_business_b_category(self):
        resp = self.client.patch(f'/api/v1/appointments/categories/{self.category_b.id}/', {'name': 'Hackeado'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.category_b.refresh_from_db()
        self.assertEqual(self.category_b.name, 'Categoría de B')

    def test_business_a_cannot_delete_business_b_category(self):
        resp = self.client.delete(f'/api/v1/appointments/categories/{self.category_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.category_b.refresh_from_db()
        self.assertTrue(self.category_b.is_active)


class MultiTenantServiceTests(APITestCase):

    def setUp(self):
        self.biz_a = _create_business('Business A', 'biz-a')
        self.biz_b = _create_business('Business B', 'biz-b')
        self.category_b = AppointmentCategory.objects.create(business=self.biz_b, name='Categoría de B')
        self.service_b = AppointmentService.objects.create(
            business=self.biz_b, name='Servicio de B', duration_minutes=30, price=100,
        )
        _auth_client(self.client, self.biz_a, role='owner')

    def test_business_a_cannot_list_business_b_services(self):
        resp = self.client.get('/api/v1/appointments/services/?include_inactive=true')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in resp.data]
        self.assertNotIn(str(self.service_b.id), ids)

    def test_business_a_cannot_retrieve_business_b_service(self):
        resp = self.client.get(f'/api/v1/appointments/services/{self.service_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_a_cannot_edit_business_b_service(self):
        resp = self.client.patch(f'/api/v1/appointments/services/{self.service_b.id}/', {'name': 'Hackeado'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.service_b.refresh_from_db()
        self.assertEqual(self.service_b.name, 'Servicio de B')

    def test_business_a_cannot_delete_business_b_service(self):
        resp = self.client.delete(f'/api/v1/appointments/services/{self.service_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.service_b.refresh_from_db()
        self.assertTrue(self.service_b.is_active)

    def test_service_category_must_belong_to_same_business(self):
        """A service created under Business A cannot reference Business B's category."""
        resp = self.client.post('/api/v1/appointments/services/', {
            'name': 'Servicio nuevo',
            'duration_minutes': 30,
            'price': '100',
            'category_id': str(self.category_b.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('category_id', resp.data)

    def test_never_trusts_business_id_from_frontend(self):
        """Even if a client sends a business id in the payload, the server-resolved
        business from the authenticated membership always wins."""
        resp = self.client.post('/api/v1/appointments/services/', {
            'business': self.biz_b.id,
            'name': 'Intento cross-tenant',
            'duration_minutes': 30,
            'price': '100',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        created = AppointmentService.objects.get(pk=resp.data['id'])
        self.assertEqual(created.business_id, self.biz_a.id)


class MultiTenantProfessionalTests(APITestCase):

    def setUp(self):
        self.biz_a = _create_business('Business A', 'biz-a')
        self.biz_b = _create_business('Business B', 'biz-b')
        self.service_b = AppointmentService.objects.create(
            business=self.biz_b, name='Servicio de B', duration_minutes=30, price=100,
        )
        self.professional_b = AppointmentProfessional.objects.create(
            business=self.biz_b, name='Profesional de B',
        )
        _auth_client(self.client, self.biz_a, role='owner')

    def test_business_a_cannot_list_business_b_professionals(self):
        resp = self.client.get('/api/v1/appointments/professionals/?include_inactive=true')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in resp.data]
        self.assertNotIn(str(self.professional_b.id), ids)

    def test_business_a_cannot_retrieve_business_b_professional(self):
        resp = self.client.get(f'/api/v1/appointments/professionals/{self.professional_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_a_cannot_edit_business_b_professional(self):
        resp = self.client.patch(
            f'/api/v1/appointments/professionals/{self.professional_b.id}/',
            {'name': 'Hackeado'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.professional_b.refresh_from_db()
        self.assertEqual(self.professional_b.name, 'Profesional de B')

    def test_business_a_cannot_delete_business_b_professional(self):
        resp = self.client.delete(f'/api/v1/appointments/professionals/{self.professional_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.professional_b.refresh_from_db()
        self.assertTrue(self.professional_b.is_active)

    def test_professional_service_must_belong_to_same_business(self):
        """A professional created under Business A cannot reference Business B's service."""
        resp = self.client.post('/api/v1/appointments/professionals/', {
            'name': 'Profesional nuevo',
            'service_ids': [str(self.service_b.id)],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service_ids', resp.data)

    def test_never_trusts_business_id_from_frontend(self):
        """Even if a client sends a business id in the payload, the server-resolved
        business from the authenticated membership always wins."""
        resp = self.client.post('/api/v1/appointments/professionals/', {
            'business': self.biz_b.id,
            'name': 'Intento cross-tenant',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        created = AppointmentProfessional.objects.get(pk=resp.data['id'])
        self.assertEqual(created.business_id, self.biz_a.id)

    def test_business_without_appointments_service_cannot_use_endpoint(self):
        other_biz = Business.objects.create(name='No Appointments Biz', default_service='gestion', slug='no-appointments-biz')
        Subscription.objects.create(business=other_biz, plan='starter', service='gestion', status='active')
        user = User.objects.create_user(username='u-no-appointments', password='pass1234')
        Membership.objects.create(user=user, business=other_biz, role='owner')
        self.client.force_authenticate(user=user)

        resp = self.client.get('/api/v1/appointments/professionals/')
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))


class MultiTenantScheduleTests(APITestCase):

    def setUp(self):
        self.biz_a = _create_business('Business A', 'biz-a-sched')
        self.biz_b = _create_business('Business B', 'biz-b-sched')
        self.professional_b = AppointmentProfessional.objects.create(business=self.biz_b, name='Profesional de B')
        self.schedule_b = AppointmentSchedule.objects.create(
            business=self.biz_b, weekday=0, start_time='09:00', end_time='13:00',
        )
        _auth_client(self.client, self.biz_a, role='owner')

    def test_business_a_cannot_list_business_b_schedules(self):
        resp = self.client.get('/api/v1/appointments/schedules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in resp.data]
        self.assertNotIn(str(self.schedule_b.id), ids)

    def test_business_a_cannot_retrieve_business_b_schedule(self):
        resp = self.client.get(f'/api/v1/appointments/schedules/{self.schedule_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_a_cannot_edit_business_b_schedule(self):
        resp = self.client.patch(
            f'/api/v1/appointments/schedules/{self.schedule_b.id}/',
            {'end_time': '20:00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.schedule_b.refresh_from_db()
        self.assertEqual(str(self.schedule_b.end_time), '13:00:00')

    def test_business_a_cannot_delete_business_b_schedule(self):
        resp = self.client.delete(f'/api/v1/appointments/schedules/{self.schedule_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(AppointmentSchedule.objects.filter(pk=self.schedule_b.id).exists())

    def test_schedule_professional_must_belong_to_same_business(self):
        resp = self.client.post('/api/v1/appointments/schedules/', {
            'weekday': 0,
            'start_time': '09:00',
            'end_time': '13:00',
            'professional_id': str(self.professional_b.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional_id', resp.data)

    def test_never_trusts_business_id_from_frontend(self):
        resp = self.client.post('/api/v1/appointments/schedules/', {
            'business': self.biz_b.id,
            'weekday': 0,
            'start_time': '09:00',
            'end_time': '13:00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        created = AppointmentSchedule.objects.get(pk=resp.data['id'])
        self.assertEqual(created.business_id, self.biz_a.id)


class MultiTenantExceptionTests(APITestCase):

    def setUp(self):
        self.biz_a = _create_business('Business A', 'biz-a-exc')
        self.biz_b = _create_business('Business B', 'biz-b-exc')
        self.professional_b = AppointmentProfessional.objects.create(business=self.biz_b, name='Profesional de B')
        self.exception_b = AppointmentException.objects.create(
            business=self.biz_b, date='2026-12-25', is_closed=True,
        )
        _auth_client(self.client, self.biz_a, role='owner')

    def test_business_a_cannot_list_business_b_exceptions(self):
        resp = self.client.get('/api/v1/appointments/exceptions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in resp.data]
        self.assertNotIn(str(self.exception_b.id), ids)

    def test_business_a_cannot_retrieve_business_b_exception(self):
        resp = self.client.get(f'/api/v1/appointments/exceptions/{self.exception_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_a_cannot_edit_business_b_exception(self):
        resp = self.client.patch(
            f'/api/v1/appointments/exceptions/{self.exception_b.id}/',
            {'note': 'Hackeado'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.exception_b.refresh_from_db()
        self.assertEqual(self.exception_b.note, '')

    def test_business_a_cannot_delete_business_b_exception(self):
        resp = self.client.delete(f'/api/v1/appointments/exceptions/{self.exception_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(AppointmentException.objects.filter(pk=self.exception_b.id).exists())

    def test_exception_professional_must_belong_to_same_business(self):
        resp = self.client.post('/api/v1/appointments/exceptions/', {
            'date': '2026-12-25',
            'is_closed': True,
            'professional_id': str(self.professional_b.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional_id', resp.data)

    def test_never_trusts_business_id_from_frontend(self):
        resp = self.client.post('/api/v1/appointments/exceptions/', {
            'business': self.biz_b.id,
            'date': '2026-12-25',
            'is_closed': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        created = AppointmentException.objects.get(pk=resp.data['id'])
        self.assertEqual(created.business_id, self.biz_a.id)


class MultiTenantAppointmentTests(APITestCase):
    """Slice 3A: A no puede listar/ver/editar/cancelar turnos de B, y no puede
    reservar contra el service/professional de B."""

    # 2026-09-21 es un lunes (weekday=0).
    MONDAY = '2026-09-21'

    def setUp(self):
        self.biz_a = _create_business('Business A', 'biz-a-appt')
        self.biz_b = _create_business('Business B', 'biz-b-appt')

        self.service_a = AppointmentService.objects.create(
            business=self.biz_a, name='Servicio de A', duration_minutes=30, price=100,
        )
        AppointmentSchedule.objects.create(
            business=self.biz_a, professional=None, weekday=0, start_time='09:00', end_time='18:00',
        )

        self.service_b = AppointmentService.objects.create(
            business=self.biz_b, name='Servicio de B', duration_minutes=30, price=100,
        )
        self.professional_b = AppointmentProfessional.objects.create(business=self.biz_b, name='Profesional de B')
        self.professional_b.services.add(self.service_b)
        AppointmentSchedule.objects.create(
            business=self.biz_b, professional=None, weekday=0, start_time='09:00', end_time='18:00',
        )
        self.appointment_b = Appointment.objects.create(
            business=self.biz_b,
            service=self.service_b,
            customer_name='Cliente de B',
            customer_phone='1100000000',
            start_at='2026-09-21T10:00:00-03:00',
            end_at='2026-09-21T10:30:00-03:00',
            service_name=self.service_b.name,
            service_duration_minutes=self.service_b.duration_minutes,
            service_price=self.service_b.price,
            deposit_type=self.service_b.deposit_type,
            deposit_value=self.service_b.deposit_value,
        )

        _auth_client(self.client, self.biz_a, role='owner')

    def test_business_a_cannot_list_business_b_appointments(self):
        resp = self.client.get('/api/v1/appointments/appointments/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in resp.data]
        self.assertNotIn(str(self.appointment_b.id), ids)

    def test_business_a_cannot_retrieve_business_b_appointment(self):
        resp = self.client.get(f'/api/v1/appointments/appointments/{self.appointment_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_a_cannot_edit_business_b_appointment(self):
        resp = self.client.patch(
            f'/api/v1/appointments/appointments/{self.appointment_b.id}/',
            {'customer_name': 'Hackeado'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.appointment_b.refresh_from_db()
        self.assertEqual(self.appointment_b.customer_name, 'Cliente de B')

    def test_business_a_cannot_cancel_business_b_appointment(self):
        resp = self.client.delete(f'/api/v1/appointments/appointments/{self.appointment_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.appointment_b.refresh_from_db()
        self.assertEqual(self.appointment_b.status, Appointment.Status.CONFIRMED)

    def test_appointment_service_must_belong_to_same_business(self):
        resp = self.client.post('/api/v1/appointments/appointments/', {
            'service_id': str(self.service_b.id),
            'start_at': f'{self.MONDAY}T11:00:00-03:00',
            'customer_name': 'Intento cross-tenant',
            'customer_phone': '1122334455',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service_id', resp.data)

    def test_appointment_professional_must_belong_to_same_business(self):
        resp = self.client.post('/api/v1/appointments/appointments/', {
            'service_id': str(self.service_a.id),
            'professional_id': str(self.professional_b.id),
            'start_at': f'{self.MONDAY}T11:00:00-03:00',
            'customer_name': 'Intento cross-tenant',
            'customer_phone': '1122334455',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional_id', resp.data)

    def test_never_trusts_business_id_from_frontend(self):
        resp = self.client.post('/api/v1/appointments/appointments/', {
            'business': self.biz_b.id,
            'service_id': str(self.service_a.id),
            'start_at': f'{self.MONDAY}T11:00:00-03:00',
            'customer_name': 'Intento cross-tenant',
            'customer_phone': '1122334455',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        created = Appointment.objects.get(pk=resp.data['id'])
        self.assertEqual(created.business_id, self.biz_a.id)
