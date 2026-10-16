"""Concurrencia real del checkout de seña (Slice 6A, test 15).

`TransactionTestCase` + threads con conexiones reales a PostgreSQL: varios
POST simultáneos al checkout del mismo turno NO deben crear más de una
Preference ni más de un `AppointmentPayment` activo. Mercado Pago está
mockeado con una latencia artificial para que las requests se solapen
mientras la primera está "en vuelo".
"""
from __future__ import annotations

import threading
import time
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from ..models import AppointmentPayment
from .test_appointment_checkout import (
  API_BASE,
  FRONT_BASE,
  GLOBAL_TOKEN,
  TEST_ENCRYPTION_KEY,
  TOKEN_A,
  FakeMercadoPago,
  _mp_created,
  create_appointment,
  create_business,
  create_service,
)

# Por debajo del throttle `public_appointments_checkout` (10/minute).
N_REQUESTS = 6


@override_settings(
  MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
  MP_ACCESS_TOKEN=GLOBAL_TOKEN,
  BASE_PUBLIC_URL=API_BASE,
  FRONTEND_URL=FRONT_BASE,
)
class ConcurrentAppointmentCheckoutTests(TransactionTestCase):
  # Ver test_public_booking_concurrency.py: activa allow_cascade en el flush.
  available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

  def setUp(self):
    cache.clear()
    self.biz = create_business(name='Concurrencia Pago', slug='concurrencia-pago', token=TOKEN_A)
    self.appt = create_appointment(self.biz, create_service(self.biz, deposit_value=Decimal('40')))
    self.mp = FakeMercadoPago()
    self.calls_lock = threading.Lock()

  def _run_concurrently(self, behavior):
    self.mp.behavior = behavior
    url = f'/api/v1/appointments/public/{self.biz.slug}/bookings/{self.appt.public_token}/checkout/'
    barrier = threading.Barrier(N_REQUESTS)
    results: list[int] = []

    def attempt():
      try:
        barrier.wait()
        res = APIClient().post(url, {}, format='json')
        with self.calls_lock:
          results.append(res.status_code)
      finally:
        connections.close_all()

    with patch('mercadopago.SDK', new=self.mp):
      threads = [threading.Thread(target=attempt) for _ in range(N_REQUESTS)]
      for t in threads:
        t.start()
      for t in threads:
        t.join(timeout=60)
    self.assertEqual(len(results), N_REQUESTS, results)
    return results

  def test_concurrent_checkouts_create_single_preference(self):
    def slow_created(data):
      time.sleep(0.5)  # la Preference "en vuelo" mientras llegan las demás requests
      return _mp_created('PREF-CONCURRENT')

    results = self._run_concurrently(slow_created)

    self.assertEqual(len(self.mp.preference_calls), 1, results)
    self.assertEqual(results.count(201), 1, results)
    # El resto: 409 (intento `creating` en vuelo) o 200 (reuso del `pending`).
    self.assertTrue(all(code in (200, 201, 409) for code in results), results)
    self.assertEqual(AppointmentPayment.objects.count(), 1)
    payment = AppointmentPayment.objects.get()
    self.assertEqual(payment.status, AppointmentPayment.Status.PENDING)
    self.assertEqual(payment.provider_preference_id, 'PREF-CONCURRENT')
    self.assertEqual(payment.amount, Decimal('40.00'))

  def test_concurrent_checkouts_after_uncertain_outcome_never_recreate(self):
    def slow_timeout(data):
      import requests
      time.sleep(0.3)
      raise requests.exceptions.ReadTimeout('read timed out')

    results = self._run_concurrently(slow_timeout)

    self.assertEqual(len(self.mp.preference_calls), 1, results)
    self.assertEqual(results.count(502), 1, results)
    self.assertEqual(results.count(409), N_REQUESTS - 1, results)
    self.assertEqual(AppointmentPayment.objects.count(), 1)
    self.assertEqual(AppointmentPayment.objects.get().status, AppointmentPayment.Status.UNCERTAIN)
