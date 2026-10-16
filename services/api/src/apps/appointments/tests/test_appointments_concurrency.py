"""
Test de concurrencia real para la creación de `Appointment` (Slice 3A).

Usa `TransactionTestCase` (no `TestCase`) a propósito: `TestCase` envuelve
cada test en una transacción que se revierte al final y comparte una única
conexión, lo que hace que dos threads NUNCA vean commits reales del otro —
inútil para probar el locking de
`apps.appointments.services.booking.lock_professionals`.
`TransactionTestCase` permite que cada thread abra su propia conexión real
a PostgreSQL y haga commits reales, que es justamente lo que hace falta
para reproducir la carrera de doble-booking.

Requiere PostgreSQL (el proyecto no soporta SQLite, ver `config.settings`).
"""
from __future__ import annotations

import datetime as dt
import threading

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription

from ..models import Appointment, AppointmentProfessional, AppointmentSchedule, AppointmentService

User = get_user_model()

MONDAY = dt.date(2030, 3, 4)
assert MONDAY.weekday() == 0


class ConcurrentBookingTests(TransactionTestCase):
    # Workaround para un bug pre-existente del repo (Slice 4B lo documenta al
    # tropezar con él de nuevo): `apps.treasury.ExpenseTemplate` es un modelo
    # `managed = False` (tabla congelada, ver `apps/treasury/models.py:154-156`)
    # cuya FK a `business_business` sigue viva en la base pero que Django no
    # incluye en el flush automático de `TransactionTestCase`. Sin esto, el
    # `TRUNCATE` sin CASCADE que Django emite por default falla contra
    # Postgres. Fijar `available_apps` (mismo conjunto que `INSTALLED_APPS`)
    # activa `allow_cascade=True` — evita el crash sin tocar `treasury`.
    available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

    def setUp(self):
        self.business = Business.objects.create(
            name='Concurrency Biz', default_service='appointments', slug='concurrency-biz',
        )
        Subscription.objects.create(
            business=self.business, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
        )
        self.service = AppointmentService.objects.create(
            business=self.business, name='Corte', duration_minutes=30, price=100,
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

        self.user = User.objects.create_user(username='concurrency-user', password='pass1234')
        Membership.objects.create(user=self.user, business=self.business, role='owner')

    def test_concurrent_create_same_professional_slot_only_one_succeeds(self):
        payload = {
            'service_id': str(self.service.id),
            'professional_id': str(self.professional.id),
            'start_at': f'{MONDAY.isoformat()}T10:00:00-03:00',
            'customer_name': 'Cliente concurrente',
            'customer_phone': '1122334455',
        }

        results: list[int] = []
        results_lock = threading.Lock()

        def attempt():
            try:
                client = APIClient()
                client.force_authenticate(user=self.user)
                resp = client.post('/api/v1/appointments/appointments/', payload, format='json')
                with results_lock:
                    results.append(resp.status_code)
            finally:
                # Cada thread abre su propia conexión; hay que cerrarla
                # explícitamente al terminar (patrón estándar de Django
                # para tests con threads).
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 5)
        self.assertEqual(results.count(201), 1, f'Se esperaba exactamente 1 turno creado, resultados: {results}')
        self.assertEqual(results.count(400), 4, f'Se esperaban 4 rechazos por solapamiento, resultados: {results}')

        confirmed = Appointment.objects.filter(
            business=self.business, professional=self.professional, status=Appointment.Status.CONFIRMED,
        )
        self.assertEqual(confirmed.count(), 1)

    def test_concurrent_create_same_business_slot_without_professional_only_one_succeeds(self):
        """Turno sin `professional` (slot "a nivel negocio"): `lock_professionals`
        lockea la fila de `Business` en vez de una fila de `AppointmentProfessional`
        (ver docstring de `booking.lock_professionals`). Mismo escenario de carrera
        que el test de arriba, pero ejercitando esa otra rama del locking.
        """
        # Slice 7B.1: el carril "sin profesional" solo existe para servicios sin
        # profesionales elegibles (`self.service` tiene uno).
        service_no_prof = AppointmentService.objects.create(
            business=self.business, name='Consulta', duration_minutes=30, price=100,
        )
        payload = {
            'service_id': str(service_no_prof.id),
            'start_at': f'{MONDAY.isoformat()}T14:00:00-03:00',
            'customer_name': 'Cliente concurrente sin profesional',
            'customer_phone': '1122334455',
        }

        results: list[int] = []
        results_lock = threading.Lock()

        def attempt():
            try:
                client = APIClient()
                client.force_authenticate(user=self.user)
                resp = client.post('/api/v1/appointments/appointments/', payload, format='json')
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
        self.assertEqual(results.count(201), 1, f'Se esperaba exactamente 1 turno creado, resultados: {results}')
        self.assertEqual(results.count(400), 4, f'Se esperaban 4 rechazos por solapamiento, resultados: {results}')

        confirmed = Appointment.objects.filter(
            business=self.business, professional__isnull=True, status=Appointment.Status.CONFIRMED,
        )
        self.assertEqual(confirmed.count(), 1)
