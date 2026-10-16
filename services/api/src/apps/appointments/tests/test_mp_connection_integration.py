"""Slice 7B.2 — Business solo-Turnos conecta MP desde Turnos y el checkout 6A
resuelve esa misma `MercadoPagoConnection`.

End-to-end sobre los endpoints reales: OAuth start (context=appointments) →
callback → status → checkout público de seña. Solo se mockea Mercado Pago
(token exchange y SDK de Preferences).
"""
from __future__ import annotations

import urllib.parse
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership
from apps.merchant_payments.models import MercadoPagoConnection

from ..models import AppointmentPayment
from .test_appointment_checkout import (
  API_BASE, FRONT_BASE, GLOBAL_TOKEN, TEST_ENCRYPTION_KEY, FakeMercadoPago,
  create_appointment, create_business, create_service,
)

MP_START_URL = '/api/v1/menu/mercadopago/connect/start/'
MP_CALLBACK_URL = '/api/v1/menu/mercadopago/connect/callback/'
MP_STATUS_URL = '/api/v1/menu/mercadopago/connect/status/'
OAUTH_TOKEN = 'APP_USR-TURNOS-OAUTH-TOKEN'


@override_settings(
  MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
  MP_ACCESS_TOKEN=GLOBAL_TOKEN,
  MP_CLIENT_ID='TEST-CLIENT-ID',
  MP_CLIENT_SECRET='TEST-CLIENT-SECRET',
  MP_REDIRECT_URI=f'{API_BASE}/api/v1/menu/mercadopago/connect/callback/',
  BASE_PUBLIC_URL=API_BASE,
  FRONTEND_URL=FRONT_BASE,
)
class AppointmentsOnlyMercadoPagoIntegrationTests(APITestCase):
  def setUp(self):
    cache.clear()
    # appointments habilitado, menú NO habilitado, sin conexión previa.
    self.biz = create_business(name='Barbería Solo Turnos', slug='solo-turnos')
    self.service = create_service(self.biz)
    self.appt = create_appointment(self.biz, self.service)
    user = get_user_model().objects.create_user(username='owner-turnos', password='pass1234')
    Membership.objects.create(user=user, business=self.biz, role='owner')
    self.admin = APIClient()
    self.admin.force_authenticate(user)
    self.admin.cookies['bid'] = str(self.biz.id)

    self.mp = FakeMercadoPago()
    patcher = patch('mercadopago.SDK', new=self.mp)
    patcher.start()
    self.addCleanup(patcher.stop)

  def _checkout(self):
    return self.client.post(
      f'/api/v1/appointments/public/{self.biz.slug}/bookings/{self.appt.public_token}/checkout/',
      {}, format='json',
    )

  @patch('apps.merchant_payments.views.requests.post')
  def test_connect_from_turnos_then_checkout_uses_that_connection(self, mock_post):
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {
      'access_token': OAUTH_TOKEN, 'refresh_token': 'TG-R', 'expires_in': 3600,
      'user_id': 9001, 'scope': 'offline_access read write',
    }
    start = self.admin.get(MP_START_URL, {'context': 'appointments'})
    self.assertEqual(start.status_code, status.HTTP_200_OK)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(start.data['auth_url']).query)['state'][0]

    cb = self.client.get(MP_CALLBACK_URL, {'code': 'code-1', 'state': state})
    self.assertEqual(cb.url, f'{FRONT_BASE}/app/turnos/configuracion?mp=connected')

    st = self.admin.get(MP_STATUS_URL)
    self.assertTrue(st.data['connected'])
    self.assertEqual(st.data['mp_user_id'], '9001')

    res = self._checkout()
    self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.content)
    self.assertEqual(self.mp.tokens, [OAUTH_TOKEN])  # la conexión del Business, nunca la global
    self.assertEqual(MercadoPagoConnection.objects.filter(business=self.biz).count(), 1)

  def test_not_connected_status_says_so_and_checkout_fails_safely(self):
    st = self.admin.get(MP_STATUS_URL)
    self.assertEqual(st.status_code, status.HTTP_200_OK)
    self.assertFalse(st.data['connected'])

    res = self._checkout()
    self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
    self.assertEqual(res.data['code'], 'payment_unavailable')
    self.assertEqual(AppointmentPayment.objects.get().failure_reason, 'mp_not_connected')
    self.assertEqual(self.mp.tokens, [])
