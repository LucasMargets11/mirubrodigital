"""Tests para los endpoints públicos de Turnos (Slice 4A, `/t/[slug]`).

Cubre resolución por slug, exposición de datos públicos (sin campos
privados), profesionales por servicio, y que la disponibilidad pública
delega en el mismo motor (`compute_availability`) que el panel interno.
"""
from __future__ import annotations

import datetime as dt

from rest_framework import status
from rest_framework.test import APITestCase

from apps.business.models import Business, BusinessPlan, Subscription

from ..models import (
    Appointment,
    AppointmentCategory,
    AppointmentProfessional,
    AppointmentSchedule,
    AppointmentService,
)

# 2026-09-21 es un lunes (weekday=0), igual que en test_availability.py.
MONDAY = dt.date(2026, 9, 21)


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


class PublicAppointmentBusinessViewTests(APITestCase):
    def setUp(self):
        self.biz = _create_business()
        self.category = AppointmentCategory.objects.create(business=self.biz, name='Cortes')
        self.inactive_category = AppointmentCategory.objects.create(
            business=self.biz, name='Descontinuado', is_active=False,
        )
        self.service = AppointmentService.objects.create(
            business=self.biz, category=self.category, name='Corte + barba',
            duration_minutes=60, price=5000,
        )
        self.inactive_service = AppointmentService.objects.create(
            business=self.biz, name='Viejo servicio', duration_minutes=30, price=1000, is_active=False,
        )

    def _get(self, slug=None):
        return self.client.get(f'/api/v1/appointments/public/{slug or self.biz.slug}/')

    # 1. business público válido -------------------------------------------------
    def test_valid_public_business_returns_expected_shape(self):
        resp = self._get()
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['business']['slug'], self.biz.slug)
        self.assertEqual(resp.data['business']['name'], self.biz.name)
        self.assertEqual(resp.data['business']['timezone'], self.biz.timezone)
        self.assertNotIn('id', resp.data['business'])
        self.assertNotIn('status', resp.data['business'])

    # 2. slug inexistente ---------------------------------------------------------
    def test_nonexistent_slug_returns_404(self):
        resp = self._get(slug='no-existe')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # 3. business sin appointments --------------------------------------------------
    def test_business_without_appointments_service_returns_404(self):
        other = _create_business(
            name='Restaurante', slug='restaurante-biz', default_service='restaurante',
            with_subscription=False,
        )
        Subscription.objects.create(business=other, plan=BusinessPlan.PLUS, service='restaurante', status='active')
        resp = self._get(slug=other.slug)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_suspended_business_returns_404(self):
        suspended = _create_business(name='Suspendido', slug='suspendido-biz', status='suspended')
        resp = self._get(slug=suspended.slug)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_onboarding_business_returns_404(self):
        onboarding = _create_business(name='Onboarding Biz', slug='onboarding-biz', status='onboarding')
        resp = self._get(slug=onboarding.slug)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # 4. solo categorías/servicios activos -------------------------------------------
    def test_only_active_categories_and_services_are_returned(self):
        resp = self._get()
        category_names = [c['name'] for c in resp.data['categories']]
        service_names = [s['name'] for s in resp.data['services']]
        self.assertIn('Cortes', category_names)
        self.assertNotIn('Descontinuado', category_names)
        self.assertIn('Corte + barba', service_names)
        self.assertNotIn('Viejo servicio', service_names)

    # Forma del servicio público: sin sort_order/timestamps, con categoría embebida.
    def test_service_public_shape(self):
        resp = self._get()
        service_data = next(s for s in resp.data['services'] if s['id'] == str(self.service.id))
        self.assertEqual(set(service_data.keys()), {
            'id', 'name', 'description', 'duration_minutes', 'price',
            'deposit_type', 'deposit_value', 'category',
        })
        self.assertEqual(service_data['category'], {'id': str(self.category.id), 'name': 'Cortes'})

    # No cross-tenant: negocio ajeno no ve nada de este negocio.
    def test_other_business_data_not_leaked(self):
        other = _create_business(name='Otro negocio', slug='otro-negocio')
        AppointmentService.objects.create(business=other, name='Servicio ajeno', duration_minutes=30, price=100)
        resp = self._get(slug=other.slug)
        service_names = [s['name'] for s in resp.data['services']]
        self.assertNotIn('Corte + barba', service_names)


class PublicAppointmentProfessionalsViewTests(APITestCase):
    def setUp(self):
        self.biz = _create_business()
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=1000,
        )
        self.other_service = AppointmentService.objects.create(
            business=self.biz, name='Color', duration_minutes=90, price=3000,
        )
        self.professional = AppointmentProfessional.objects.create(
            business=self.biz, name='Lucas', phone='+54 9 11 5555-5555', email='lucas@example.com',
        )
        self.professional.services.add(self.service)
        self.inactive_professional = AppointmentProfessional.objects.create(
            business=self.biz, name='Inactivo', is_active=False,
        )
        self.inactive_professional.services.add(self.service)

    def _get(self, slug=None, **params):
        return self.client.get(
            f'/api/v1/appointments/public/{slug or self.biz.slug}/professionals/', params,
        )

    # 5. profesionales activos del servicio -------------------------------------------
    def test_returns_only_active_professionals_for_service(self):
        resp = self._get(service=str(self.service.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        names = [p['name'] for p in resp.data]
        self.assertIn('Lucas', names)
        self.assertNotIn('Inactivo', names)

    # No devuelve profesionales que no realizan el servicio pedido.
    def test_excludes_professionals_not_linked_to_service(self):
        resp = self._get(service=str(self.other_service.id))
        self.assertEqual(resp.data, [])

    # 6. no filtrar datos privados -----------------------------------------------------
    def test_professional_payload_excludes_private_fields(self):
        resp = self._get(service=str(self.service.id))
        professional_data = resp.data[0]
        self.assertEqual(set(professional_data.keys()), {'id', 'name', 'description'})
        self.assertNotIn('phone', professional_data)
        self.assertNotIn('email', professional_data)

    def test_missing_service_param_returns_400(self):
        resp = self._get()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # 9. profesional / servicio de otro business rechazado -----------------------------
    def test_service_from_other_business_returns_400(self):
        other = _create_business(name='Otro', slug='otro-prof-biz')
        other_service = AppointmentService.objects.create(business=other, name='Corte', duration_minutes=30, price=100)
        resp = self._get(service=str(other_service.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_business_returns_404(self):
        resp = self._get(slug='no-existe', service=str(self.service.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PublicAppointmentAvailabilityViewTests(APITestCase):
    def setUp(self):
        self.biz = _create_business()
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=1000,
        )
        AppointmentSchedule.objects.create(
            business=self.biz, professional=None, weekday=0,
            start_time='09:00', end_time='10:00',
        )

    def _get(self, slug=None, **params):
        return self.client.get(
            f'/api/v1/appointments/public/{slug or self.biz.slug}/availability/', params,
        )

    # 7. availability pública usa el motor existente ------------------------------------
    def test_returns_same_slots_as_internal_engine(self):
        resp = self._get(service=str(self.service.id), date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data['slots']), 3)
        self.assertEqual(resp.data['slots'][0]['start'][:16], f'{MONDAY.isoformat()}T09:00')

    def test_missing_params_return_400(self):
        resp = self._get(service=str(self.service.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('date', resp.data)

    def test_invalid_date_returns_400(self):
        resp = self._get(service=str(self.service.id), date='21-09-2026')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # 8. servicio de otro business rechazado ---------------------------------------------
    def test_service_from_other_business_rejected(self):
        other = _create_business(name='Otro', slug='otro-avail-biz')
        other_service = AppointmentService.objects.create(business=other, name='Corte', duration_minutes=30, price=100)
        resp = self._get(service=str(other_service.id), date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service', resp.data)

    # 9. profesional de otro business rechazado ------------------------------------------
    def test_professional_from_other_business_rejected(self):
        other = _create_business(name='Otro', slug='otro-avail-biz-2')
        other_professional = AppointmentProfessional.objects.create(business=other, name='Bruno')
        resp = self._get(
            service=str(self.service.id), date=MONDAY.isoformat(),
            professional=str(other_professional.id),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    # 10. slots ocupados no aparecen -------------------------------------------------------
    def test_occupied_slots_are_excluded(self):
        tz = dt.timezone(dt.timedelta(hours=-3))
        Appointment.objects.create(
            business=self.biz, service=self.service, professional=None,
            customer_name='Cliente', customer_phone='+54 9 11 5555-5555',
            start_at=dt.datetime(2026, 9, 21, 9, 0, tzinfo=tz),
            end_at=dt.datetime(2026, 9, 21, 9, 30, tzinfo=tz),
            service_name=self.service.name, service_duration_minutes=30,
            service_price=self.service.price, deposit_type=self.service.deposit_type,
            deposit_value=self.service.deposit_value,
        )
        resp = self._get(service=str(self.service.id), date=MONDAY.isoformat())
        starts = [s['start'][11:16] for s in resp.data['slots']]
        self.assertNotIn('09:00', starts)

    def test_nonexistent_business_returns_404(self):
        resp = self._get(slug='no-existe', service=str(self.service.id), date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_without_appointments_returns_404(self):
        other = _create_business(
            name='Sin turnos', slug='sin-turnos-biz', default_service='gestion', with_subscription=False,
        )
        resp = self._get(slug=other.slug, service=str(self.service.id), date=MONDAY.isoformat())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
