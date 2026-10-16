"""
Slice 7B.2 — OAuth return context (Menu vs Turnos) and appointments-only access.

The context is a closed server-side value bound to the single-use state in
cache; the callback only ever redirects to one of two fixed in-app paths.
"""
from __future__ import annotations

import urllib.parse
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

TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='
FRONT = 'https://app.example.com'
TURNOS_OK = f'{FRONT}/app/turnos/configuracion?mp=connected'
TURNOS_ERR = f'{FRONT}/app/turnos/configuracion?mp=error'
NEUTRAL_ERR = f'{FRONT}/app?mp=error'

ACCESS_TOKEN = 'APP_USR-SECRET-ACCESS-TOKEN'
REFRESH_TOKEN = 'TG-SECRET-REFRESH-TOKEN'


def _token_response(mock_post, access=ACCESS_TOKEN, user_id=777):
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {
        'access_token': access, 'refresh_token': REFRESH_TOKEN,
        'expires_in': 3600, 'user_id': user_id, 'scope': 'offline_access read write',
    }


class _OAuthHelpers:
    def setUp(self):
        cache.clear()
        self._n = 0

    # ── helpers ─────────────────────────────────────────────────────────
    def _appointments_business(self, name='Turnos A', slug='turnos-a') -> Business:
        """Business with appointments enabled and menu NOT enabled."""
        biz = Business.objects.create(name=name, default_service='appointments', slug=slug)
        Subscription.objects.create(
            business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
        )
        return biz

    def _menu_business(self) -> Business:
        biz = Business.objects.create(name='Resto', default_service='restaurante')
        Subscription.objects.create(business=biz, plan=BusinessPlan.PLUS, status='active')
        return biz

    def _login(self, business, role='owner'):
        self._n += 1
        user = get_user_model().objects.create_user(username=f'u{self._n}', password='pass1234')
        Membership.objects.create(user=user, business=business, role=role)
        self.client.force_authenticate(user)
        self.client.cookies['bid'] = str(business.id)
        return user

    def _start(self, context=None):
        params = {'context': context} if context is not None else {}
        res = self.client.get(MP_START_URL, params)
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(res.data['auth_url']).query)
        return qs['state'][0]

    def _callback(self, state, **extra):
        self.client.force_authenticate(None)  # MP redirects anonymously
        return self.client.get(MP_CALLBACK_URL, {'code': 'auth-code', 'state': state, **extra})


@override_settings(
    MP_CLIENT_ID='TEST-CLIENT-ID',
    MP_CLIENT_SECRET='TEST-CLIENT-SECRET',
    MP_REDIRECT_URI='https://api.example.com/api/v1/menu/mercadopago/connect/callback/',
    FRONTEND_URL=FRONT,
    MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
)
class OAuthContextTests(_OAuthHelpers, APITestCase):
    # 1. start from appointments stores context ------------------------------------------
    def test_start_from_appointments_stores_context_server_side(self):
        biz = self._appointments_business()
        self._login(biz)
        state = self._start('appointments')
        self.assertEqual(
            cache.get(f'mp_oauth_state:{state}'),
            {'business_id': biz.id, 'context': 'appointments'},
        )
        # The context is not echoed into the MP authorization URL.
        res = self.client.get(MP_START_URL, {'context': 'appointments'})
        self.assertNotIn('appointments', res.data['auth_url'])

    # 2. callback appointments → /app/turnos/configuracion -----------------------------
    @patch('apps.merchant_payments.views.requests.post')
    def test_callback_appointments_returns_to_turnos(self, mock_post):
        _token_response(mock_post)
        biz = self._appointments_business()
        self._login(biz)
        res = self._callback(self._start('appointments'))
        self.assertEqual(res.status_code, status.HTTP_302_FOUND)
        self.assertEqual(res.url, TURNOS_OK)
        conn = MercadoPagoConnection.objects.get(business=biz)
        self.assertEqual(conn.status, 'connected')
        self.assertEqual(conn.access_token, ACCESS_TOKEN)

    @patch('apps.merchant_payments.views.requests.post')
    def test_callback_appointments_errors_return_generic_flag(self, mock_post):
        biz = self._appointments_business()
        self._login(biz)
        # MP-side cancel/deny: reason never forwarded to the Turnos URL.
        res = self._callback(self._start('appointments'), error='access_denied')
        self.assertEqual(res.url, TURNOS_ERR)
        mock_post.assert_not_called()
        # Token exchange failure.
        self._login(biz)
        mock_post.side_effect = RuntimeError('boom secret detail')
        res = self._callback(self._start('appointments'))
        self.assertEqual(res.url, TURNOS_ERR)
        self.assertFalse(MercadoPagoConnection.objects.filter(business=biz).exists())

    @patch('apps.merchant_payments.views.requests.post')
    def test_mp_error_consumes_state(self, mock_post):
        _token_response(mock_post)
        biz = self._appointments_business()
        self._login(biz)
        state = self._start('appointments')
        self._callback(state, error='access_denied')
        res = self._callback(state)
        self.assertEqual(res.url, NEUTRAL_ERR)
        self.assertFalse(MercadoPagoConnection.objects.filter(business=biz).exists())

    # 3. callback menu keeps the historical return --------------------------------------
    @patch('apps.merchant_payments.views.requests.post')
    def test_callback_menu_keeps_current_return(self, mock_post):
        _token_response(mock_post)
        biz = self._menu_business()
        for context in ('menu', None):
            self._login(biz)
            res = self._callback(self._start(context))
            self.assertEqual(res.url, f'{FRONT}/app/settings/online-menu?mp_connected=1')

    @patch('apps.merchant_payments.views.requests.post')
    def test_legacy_state_without_context_falls_back_to_menu(self, mock_post):
        """States written before 7B.2 hold a bare business id."""
        _token_response(mock_post)
        biz = self._appointments_business()
        cache.set('mp_oauth_state:legacy-state', biz.id, 600)
        res = self._callback('legacy-state')
        self.assertEqual(res.url, f'{FRONT}/app/settings/online-menu?mp_connected=1')
        self.assertTrue(MercadoPagoConnection.objects.filter(business=biz).exists())

    # 4. manipulated context never produces an arbitrary redirect ----------------------
    def test_start_rejects_unknown_context(self):
        biz = self._appointments_business()
        self._login(biz)
        with patch('apps.merchant_payments.views.cache.set') as cache_set:
            for bad in ('https://evil.example.com', '//evil.example.com', 'appointments/../x', 'MENU', ' '):
                res = self.client.get(MP_START_URL, {'context': bad})
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, bad)
                self.assertNotIn('auth_url', res.data)
        cache_set.assert_not_called()

    @patch('apps.merchant_payments.views.requests.post')
    def test_callback_ignores_client_supplied_redirects(self, mock_post):
        _token_response(mock_post)
        biz = self._appointments_business()
        self._login(biz)
        state = self._start('appointments')
        res = self._callback(
            state, context='menu', return_url='https://evil.example.com', next='//evil.example.com',
        )
        self.assertEqual(res.url, TURNOS_OK)

    @patch('apps.merchant_payments.views.requests.post')
    def test_tampered_cached_context_falls_back_to_menu(self, mock_post):
        _token_response(mock_post)
        biz = self._appointments_business()
        cache.set('mp_oauth_state:odd', {'business_id': biz.id, 'context': 'https://evil.example.com'}, 600)
        res = self._callback('odd')
        self.assertTrue(res.url.startswith(f'{FRONT}/app/'))
        self.assertNotIn('evil', res.url)

    # 5/6. invalid state rejected; state single-use ------------------------------------
    @patch('apps.merchant_payments.views.requests.post')
    def test_invalid_state_rejected_and_state_single_use(self, mock_post):
        _token_response(mock_post)
        res = self._callback('not-a-real-state')
        self.assertEqual(res.url, NEUTRAL_ERR)
        mock_post.assert_not_called()

        biz = self._appointments_business()
        self._login(biz)
        state = self._start('appointments')
        self.assertEqual(self._callback(state).url, TURNOS_OK)
        # Replay: the state (and its context) is gone.
        replay = self._callback(state)
        self.assertEqual(replay.url, NEUTRAL_ERR)
        self.assertEqual(mock_post.call_count, 1)

    @patch('apps.merchant_payments.views.requests.post')
    def test_callback_does_not_accept_business_id(self, mock_post):
        _token_response(mock_post)
        biz_a = self._appointments_business('A', 'turnos-a')
        biz_b = self._appointments_business('B', 'turnos-b')
        self._login(biz_a)
        state = self._start('appointments')
        self._callback(state, business_id=biz_b.id, business=biz_b.id, bid=biz_b.id)
        self.assertTrue(MercadoPagoConnection.objects.filter(business=biz_a).exists())
        self.assertFalse(MercadoPagoConnection.objects.filter(business=biz_b).exists())

    # 7/8/9. appointments-only business: start, status, disconnect -----------------------
    def test_appointments_only_business_can_start_status_and_disconnect(self):
        biz = self._appointments_business()
        self._login(biz)

        self._start('appointments')

        res = self.client.get(MP_STATUS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['connected'])

        MercadoPagoConnection.objects.create(business=biz, access_token=ACCESS_TOKEN, mp_user_id='42')
        res = self.client.get(MP_STATUS_URL)
        self.assertTrue(res.data['connected'])
        self.assertEqual(res.data['mp_user_id'], '42')

        res = self.client.delete(MP_DISCONNECT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(MercadoPagoConnection.objects.filter(business=biz).exists())
        self.assertFalse(self.client.get(MP_STATUS_URL).data['connected'])

    def test_viewer_cannot_manage_mp_connection(self):
        biz = self._appointments_business()
        MercadoPagoConnection.objects.create(business=biz, access_token=ACCESS_TOKEN)
        self._login(biz, role='viewer')
        self.assertEqual(self.client.get(MP_START_URL, {'context': 'appointments'}).status_code, 403)
        self.assertEqual(self.client.get(MP_STATUS_URL).status_code, 403)
        self.assertEqual(self.client.delete(MP_DISCONNECT_URL).status_code, 403)
        self.assertTrue(MercadoPagoConnection.objects.filter(business=biz).exists())

    def test_admin_can_manage_mp_connection(self):
        biz = self._appointments_business()
        self._login(biz, role='admin')
        self._start('appointments')
        self.assertEqual(self.client.get(MP_STATUS_URL).status_code, 200)


@override_settings(
    MP_CLIENT_ID='TEST-CLIENT-ID',
    MP_CLIENT_SECRET='TEST-CLIENT-SECRET',
    MP_REDIRECT_URI='https://api.example.com/api/v1/menu/mercadopago/connect/callback/',
    FRONTEND_URL=FRONT,
    MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
)
class FinancialRoleAndFallbackTests(_OAuthHelpers, APITestCase):
    """Slice 7B.2.1 — connect/disconnect only OWNER/ADMIN; neutral fallback."""

    def _start_status(self, role, service_business=None):
        biz = service_business or self._appointments_business()
        self._login(biz, role=role)
        return self.client.get(MP_START_URL, {'context': 'appointments'}).status_code

    def _disconnect_status(self, role, service_business=None):
        biz = service_business or self._appointments_business()
        MercadoPagoConnection.objects.create(business=biz, access_token=ACCESS_TOKEN, mp_user_id='1')
        self._login(biz, role=role)
        code = self.client.delete(MP_DISCONNECT_URL).status_code
        return code, MercadoPagoConnection.objects.filter(business=biz).exists()

    # 1-4. start --------------------------------------------------------------------------
    def test_owner_and_admin_can_start_oauth(self):
        self.assertEqual(self._start_status('owner'), 200)
        cache.clear()
        self.assertEqual(self._start_status('admin', self._appointments_business('B', 'turnos-b')), 200)

    def test_manager_cannot_start_oauth(self):
        with patch('apps.merchant_payments.views.cache.set') as cache_set:
            self.assertEqual(self._start_status('manager'), 403)
        cache_set.assert_not_called()

    def test_viewer_cannot_start_oauth(self):
        self.assertEqual(self._start_status('viewer'), 403)

    def test_manager_blocked_in_menu_business_too(self):
        """Same rule for every product sharing the connection."""
        self.assertEqual(self._start_status('manager', self._menu_business()), 403)

    # 5-7. disconnect ---------------------------------------------------------------------
    def test_owner_can_disconnect(self):
        self.assertEqual(self._disconnect_status('owner'), (200, False))

    def test_admin_can_disconnect(self):
        self.assertEqual(self._disconnect_status('admin'), (200, False))

    def test_manager_cannot_disconnect(self):
        self.assertEqual(self._disconnect_status('manager'), (403, True))

    def test_viewer_cannot_disconnect(self):
        self.assertEqual(self._disconnect_status('viewer'), (403, True))

    def test_manager_can_still_read_status(self):
        biz = self._appointments_business()
        MercadoPagoConnection.objects.create(business=biz, access_token=ACCESS_TOKEN, mp_user_id='7')
        self._login(biz, role='manager')
        res = self.client.get(MP_STATUS_URL)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['connected'])

    # 8-9. valid states -------------------------------------------------------------------
    @patch('apps.merchant_payments.views.requests.post')
    def test_valid_states_return_to_their_product(self, mock_post):
        _token_response(mock_post)
        biz = self._appointments_business()
        cache.set('mp_oauth_state:s-app', {'business_id': biz.id, 'context': 'appointments'}, 600)
        self.assertEqual(self._callback('s-app').url, TURNOS_OK)
        cache.set('mp_oauth_state:s-menu', {'business_id': biz.id, 'context': 'menu'}, 600)
        self.assertEqual(self._callback('s-menu').url, f'{FRONT}/app/settings/online-menu?mp_connected=1')
        cache.set('mp_oauth_state:s-menu-err', {'business_id': biz.id, 'context': 'menu'}, 600)
        self.assertEqual(
            self._callback('s-menu-err', error='access_denied').url,
            f'{FRONT}/app/settings/online-menu?mp_error=access_denied',
        )

    # 10. expired / missing state → neutral, never a Menú-only page --------------------------
    @patch('apps.merchant_payments.views.requests.post')
    def test_expired_or_missing_state_lands_on_neutral_home(self, mock_post):
        _token_response(mock_post)
        cases = [
            {'code': 'c', 'state': 'expired-state'},
            {'state': 'expired-state', 'error': 'access_denied'},
            {'error': 'access_denied'},
            {'code': 'c'},
            {},
        ]
        self.client.force_authenticate(None)
        for params in cases:
            res = self.client.get(MP_CALLBACK_URL, params)
            self.assertEqual(res.status_code, status.HTTP_302_FOUND)
            self.assertEqual(res.url, NEUTRAL_ERR, params)
        mock_post.assert_not_called()

    # 11. cancel from appointments ------------------------------------------------------------
    def test_cancel_from_appointments_returns_to_turnos(self):
        biz = self._appointments_business()
        cache.set('mp_oauth_state:s-cancel', {'business_id': biz.id, 'context': 'appointments'}, 600)
        res = self._callback('s-cancel', error='access_denied', error_description='User cancelled')
        self.assertEqual(res.url, TURNOS_ERR)

    # 12. no client parameter can produce an external redirect -------------------------------
    @patch('apps.merchant_payments.views.requests.post')
    def test_no_client_param_creates_external_redirect(self, mock_post):
        _token_response(mock_post)
        biz = self._appointments_business()
        evil = {
            'return_url': 'https://evil.example.com', 'next': '//evil.example.com',
            'redirect': 'https://evil.example.com', 'context': 'https://evil.example.com',
            'redirect_uri': 'https://evil.example.com',
        }
        cache.set('mp_oauth_state:s-ok', {'business_id': biz.id, 'context': 'appointments'}, 600)
        responses = [
            self._callback('s-ok', **evil),
            self._callback('s-ok', **evil),  # replay → neutral
            self._callback('bogus', **evil),
            self.client.get(MP_CALLBACK_URL, {**evil, 'error': 'x'}),
        ]
        for res in responses:
            self.assertTrue(res.url.startswith(f'{FRONT}/app'), res.url)
            self.assertNotIn('evil', res.url)

    # 10. business A never touches B --------------------------------------------------
    def test_business_a_never_modifies_b(self):
        biz_a = self._appointments_business('A', 'turnos-a')
        biz_b = self._appointments_business('B', 'turnos-b')
        MercadoPagoConnection.objects.create(business=biz_b, access_token='B-TOKEN', mp_user_id='B')
        self._login(biz_a)
        # bid cookie pointing at B without membership is not honoured.
        self.client.cookies['bid'] = str(biz_b.id)
        self.client.delete(MP_DISCONNECT_URL)
        self.assertTrue(MercadoPagoConnection.objects.filter(business=biz_b).exists())
        self.client.cookies['bid'] = str(biz_a.id)
        res = self.client.delete(MP_DISCONNECT_URL)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(MercadoPagoConnection.objects.filter(business=biz_b).exists())

    # 11. tokens never in responses -------------------------------------------------------
    @patch('apps.merchant_payments.views.requests.post')
    def test_tokens_never_in_responses(self, mock_post):
        _token_response(mock_post)
        biz = self._appointments_business()
        self._login(biz)
        start = self.client.get(MP_START_URL, {'context': 'appointments'})
        state = urllib.parse.parse_qs(urllib.parse.urlparse(start.data['auth_url']).query)['state'][0]
        cb = self._callback(state)
        self._login(biz)
        st = self.client.get(MP_STATUS_URL)
        dc = self.client.delete(MP_DISCONNECT_URL)
        for res in (start, cb, st, dc):
            blob = res.content.decode() + (res.get('Location') or '')
            for secret in (ACCESS_TOKEN, REFRESH_TOKEN, 'TEST-CLIENT-SECRET', 'offline_access'):
                self.assertNotIn(secret, blob)
        self.assertEqual(set(st.data), {'connected', 'status', 'mp_user_id', 'updated_at'})
