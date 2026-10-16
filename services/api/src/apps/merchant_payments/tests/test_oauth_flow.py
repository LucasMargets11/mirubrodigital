"""
Characterization tests for the Mercado Pago OAuth connect flow and the
per-business MercadoPagoConnection lifecycle.

Originally written in `apps.menu.tests.test_mercadopago_characterization`
BEFORE the Slice 5A extraction (while this code still lived in `apps.menu`),
confirmed green there, then moved here unchanged in behavior — only the
model import below now points at this app instead of `apps.menu.models`.
They assert against the public HTTP contract (URL paths, status codes, JSON
shape), which was preserved across the extraction.
"""
from __future__ import annotations

import base64

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.merchant_payments.models import MercadoPagoConnection

MP_START_URL = '/api/v1/menu/mercadopago/connect/start/'
MP_CALLBACK_URL = '/api/v1/menu/mercadopago/connect/callback/'
MP_STATUS_URL = '/api/v1/menu/mercadopago/connect/status/'
MP_DISCONNECT_URL = '/api/v1/menu/mercadopago/connect/'

# Slice 5B.3A added Fernet encryption-at-rest for access_token/refresh_token
# (see apps.merchant_payments.crypto) — any MercadoPagoConnection write now
# needs a valid key configured.
TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='


@override_settings(
    MP_CLIENT_ID='TEST-CLIENT-ID',
    MP_CLIENT_SECRET='TEST-CLIENT-SECRET',
    MP_REDIRECT_URI='https://api.example.com/api/v1/menu/mercadopago/connect/callback/',
    FRONTEND_URL='https://app.example.com',
    MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
)
class MercadoPagoOAuthCharacterizationTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='mp-user', email='mp@example.com', password='pass1234'
        )
        cache.clear()

    def _create_business(self, name: str = 'Casa Central', plan: str = BusinessPlan.PLUS) -> Business:
        business = Business.objects.create(name=name, default_service='restaurante')
        Subscription.objects.create(business=business, plan=plan, status='active')
        return business

    def _authenticate(self, business: Business, role: str = 'owner') -> None:
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(business.id)

    # ── Start ────────────────────────────────────────────────────────────

    def test_oauth_start_returns_auth_url_with_state(self):
        business = self._create_business()
        self._authenticate(business)

        response = self.client.get(MP_START_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        auth_url = response.data['auth_url']
        self.assertIn('client_id=TEST-CLIENT-ID', auth_url)
        self.assertIn('state=', auth_url)

        # The state token embeds the business id (base64) and is registered in cache.
        state_token = auth_url.split('state=')[1].split('&')[0]
        import urllib.parse
        decoded_state = urllib.parse.unquote(state_token)
        payload = base64.urlsafe_b64decode(decoded_state.encode()).decode()
        self.assertTrue(payload.startswith(f"{business.id}:"))
        # Slice 7B.2: the cache entry now also carries the (closed) return
        # context; without ?context= it defaults to the historical Menu flow.
        self.assertEqual(
            cache.get(f"mp_oauth_state:{decoded_state}"),
            {'business_id': business.id, 'context': 'menu'},
        )

    def test_oauth_start_without_configured_credentials_returns_503(self):
        business = self._create_business()
        self._authenticate(business)

        with override_settings(MP_CLIENT_ID='', MP_REDIRECT_URI=''):
            response = self.client.get(MP_START_URL)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_oauth_start_requires_authentication(self):
        response = self.client.get(MP_START_URL)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    # ── Callback ─────────────────────────────────────────────────────────

    def _seed_state(self, business: Business) -> str:
        import secrets as _secrets
        nonce = _secrets.token_urlsafe(24)
        payload = f"{business.id}:{nonce}"
        state_token = base64.urlsafe_b64encode(payload.encode()).decode()
        cache.set(f"mp_oauth_state:{state_token}", business.id, 600)
        return state_token

    @patch('apps.merchant_payments.views.requests.post')
    def test_oauth_callback_valid_state_creates_connection(self, mock_post):
        business = self._create_business()
        state_token = self._seed_state(business)

        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            'access_token': 'BIZ-ACCESS-TOKEN',
            'refresh_token': 'BIZ-REFRESH-TOKEN',
            'expires_in': 3600,
            'user_id': 555444333,
            'scope': 'read write',
        }

        response = self.client.get(MP_CALLBACK_URL, {'code': 'auth-code-123', 'state': state_token})

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn('mp_connected=1', response.url)

        conn = MercadoPagoConnection.objects.get(business=business)
        self.assertEqual(conn.access_token, 'BIZ-ACCESS-TOKEN')
        self.assertEqual(conn.refresh_token, 'BIZ-REFRESH-TOKEN')
        self.assertEqual(conn.mp_user_id, '555444333')
        self.assertEqual(conn.status, 'connected')

    @patch('apps.merchant_payments.views.requests.post')
    def test_oauth_callback_reuses_existing_connection_no_duplicate(self, mock_post):
        """A second successful callback for the same business overwrites, never duplicates."""
        business = self._create_business()
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            'access_token': 'FIRST-TOKEN', 'refresh_token': '', 'expires_in': 0,
            'user_id': 111, 'scope': '',
        }
        state1 = self._seed_state(business)
        self.client.get(MP_CALLBACK_URL, {'code': 'code-1', 'state': state1})

        mock_post.return_value.json.return_value = {
            'access_token': 'SECOND-TOKEN', 'refresh_token': '', 'expires_in': 0,
            'user_id': 222, 'scope': '',
        }
        state2 = self._seed_state(business)
        self.client.get(MP_CALLBACK_URL, {'code': 'code-2', 'state': state2})

        self.assertEqual(MercadoPagoConnection.objects.filter(business=business).count(), 1)
        conn = MercadoPagoConnection.objects.get(business=business)
        self.assertEqual(conn.access_token, 'SECOND-TOKEN')

    def test_oauth_callback_invalid_state_redirects_with_error(self):
        response = self.client.get(MP_CALLBACK_URL, {'code': 'auth-code', 'state': 'not-a-real-state'})
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        # Slice 7B.2.1: without a valid state the originating product is
        # unknown → neutral home, generic flag (was Menú + mp_error=state_expired).
        self.assertEqual(response.url, 'https://app.example.com/app?mp=error')

    @patch('apps.merchant_payments.views.requests.post')
    def test_oauth_callback_state_is_single_use(self, mock_post):
        business = self._create_business()
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            'access_token': 'TOKEN-A', 'refresh_token': '', 'expires_in': 0,
            'user_id': 1, 'scope': '',
        }
        state_token = self._seed_state(business)

        first = self.client.get(MP_CALLBACK_URL, {'code': 'code-a', 'state': state_token})
        self.assertIn('mp_connected=1', first.url)

        # Replaying the same state must fail — it was deleted from cache after first use.
        second = self.client.get(MP_CALLBACK_URL, {'code': 'code-b', 'state': state_token})
        self.assertEqual(second.url, 'https://app.example.com/app?mp=error')

    def test_oauth_callback_missing_params_redirects_with_error(self):
        response = self.client.get(MP_CALLBACK_URL)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, 'https://app.example.com/app?mp=error')

    # ── Status / multi-tenant ────────────────────────────────────────────

    def test_business_retains_its_own_connection_status(self):
        business = self._create_business('Negocio A')
        other = self._create_business('Negocio B')
        MercadoPagoConnection.objects.create(
            business=business, access_token='tok-a', mp_user_id='111', status='connected',
        )

        self._authenticate(business)
        response = self.client.get(MP_STATUS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['connected'])
        self.assertEqual(response.data['mp_user_id'], '111')

        # A second, unrelated business must never see business A's connection.
        self.client.cookies['bid'] = str(other.id)
        Membership.objects.create(user=self.user, business=other, role='owner')
        response_other = self.client.get(MP_STATUS_URL)
        self.assertEqual(response_other.status_code, status.HTTP_200_OK)
        self.assertFalse(response_other.data['connected'])
        self.assertIsNone(response_other.data['mp_user_id'])

    def test_status_never_exposes_raw_tokens(self):
        business = self._create_business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='super-secret-token', mp_user_id='42', status='connected',
        )
        self._authenticate(business)
        response = self.client.get(MP_STATUS_URL)
        self.assertNotIn('access_token', response.data)
        self.assertNotIn('refresh_token', response.data)

    # ── Disconnect ───────────────────────────────────────────────────────

    def test_disconnect_removes_connection(self):
        business = self._create_business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='tok', mp_user_id='9', status='connected',
        )
        self._authenticate(business)

        response = self.client.delete(MP_DISCONNECT_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(MercadoPagoConnection.objects.filter(business=business).exists())

    def test_disconnect_without_existing_connection_returns_404(self):
        business = self._create_business()
        self._authenticate(business)
        response = self.client.delete(MP_DISCONNECT_URL)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
