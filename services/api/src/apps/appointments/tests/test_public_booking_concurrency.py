"""Test de concurrencia real para la reserva pública (Slice 4B).

Mismo patrón que `test_appointments_concurrency.py` (booking interno):
`TransactionTestCase` + threads con conexiones reales a PostgreSQL, para
ejercitar de verdad `services.booking.create_public_appointment` (lock +
revalidación dentro de la misma transacción) en vez de simular la carrera.
"""
from __future__ import annotations

import datetime as dt
import threading
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.business.models import Business, BusinessPlan, Subscription

from ..models import Appointment, AppointmentProfessional, AppointmentSchedule, AppointmentService

MONDAY = dt.date(2030, 3, 4)
assert MONDAY.weekday() == 0


class ConcurrentPublicBookingTests(TransactionTestCase):
    # Workaround para un bug pre-existente del repo (no introducido por Slice 4B):
    # `apps.treasury.ExpenseTemplate` es un modelo `managed = False` ("Sprint 1:
    # frozen — table stays for legacy reads", ver `apps/treasury/models.py:154-156`)
    # cuya tabla física sigue teniendo una FK viva a `business_business`, pero que
    # Django no lista como tabla a flushear (no es "managed"). El flush por
    # defecto de `TransactionTestCase` (`allow_cascade=False`) emite un
    # `TRUNCATE business_business` sin CASCADE y Postgres lo rechaza porque esa
    # FK huérfana sigue ahí. Fijar `available_apps` (mismo conjunto que
    # `INSTALLED_APPS`, sin quitar ninguno) activa `allow_cascade=True` en el
    # flush — evita el crash sin tocar `treasury`, fuera de alcance de este slice.
    available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

    def setUp(self):
        cache.clear()
        self.business = Business.objects.create(
            name='Concurrency Public Biz', default_service='appointments', slug='concurrency-public-biz',
            status='active',
        )
        Subscription.objects.create(
            business=self.business, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
        )
        self.service = AppointmentService.objects.create(
            business=self.business, name='Corte', duration_minutes=30, price=Decimal('100'),
        )
        self.professional = AppointmentProfessional.objects.create(business=self.business, name='Ana')
        self.professional.services.add(self.service)

        AppointmentSchedule.objects.create(
            business=self.business, professional=None, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )
        AppointmentSchedule.objects.create(
            business=self.business, professional=self.professional, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )

    # 13. 5 requests concurrentes mismo slot con profesional -> uno solo crea -----------------
    def test_concurrent_public_bookings_same_professional_slot_only_one_succeeds(self):
        payload = {
            'service': str(self.service.id),
            'professional': str(self.professional.id),
            'start': f'{MONDAY.isoformat()}T10:00:00-03:00',
            'customer_name': 'Cliente concurrente',
            'customer_phone': '1122334455',
        }

        results: list[int] = []
        results_lock = threading.Lock()

        def attempt():
            try:
                client = APIClient()
                resp = client.post(
                    f'/api/v1/appointments/public/{self.business.slug}/bookings/', payload, format='json',
                )
                with results_lock:
                    results.append(resp.status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 5)
        self.assertEqual(results.count(201), 1, f'Se esperaba exactamente 1 reserva creada, resultados: {results}')
        self.assertEqual(results.count(400), 4, f'Se esperaban 4 rechazos por solapamiento, resultados: {results}')

        created = Appointment.objects.filter(business=self.business, professional=self.professional)
        self.assertEqual(created.count(), 1)

    # 14. mismo caso sin profesional ------------------------------------------------------------
    def test_concurrent_public_bookings_same_business_slot_without_professional_only_one_succeeds(self):
        # Slice 7B.1: el carril "sin profesional" solo existe para servicios sin
        # profesionales elegibles (`self.service` tiene uno).
        service_no_prof = AppointmentService.objects.create(
            business=self.business, name='Consulta', duration_minutes=30, price=Decimal('100'),
        )
        payload = {
            'service': str(service_no_prof.id),
            'start': f'{MONDAY.isoformat()}T14:00:00-03:00',
            'customer_name': 'Cliente concurrente sin profesional',
            'customer_phone': '1122334455',
        }

        results: list[int] = []
        results_lock = threading.Lock()

        def attempt():
            try:
                client = APIClient()
                resp = client.post(
                    f'/api/v1/appointments/public/{self.business.slug}/bookings/', payload, format='json',
                )
                with results_lock:
                    results.append(resp.status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 5)
        self.assertEqual(results.count(201), 1, f'Se esperaba exactamente 1 reserva creada, resultados: {results}')
        self.assertEqual(results.count(400), 4, f'Se esperaban 4 rechazos por solapamiento, resultados: {results}')

        created = Appointment.objects.filter(business=self.business, professional__isnull=True)
        self.assertEqual(created.count(), 1)
