"""
Slice 5B.3B — access-token refresh, concurrency locking, and disconnect
lifecycle for `MercadoPagoConnection`.

Covers the refresh grant (`apps.merchant_payments.services.refresh_merchant_connection`
/ `get_merchant_connection`), the `select_for_update` locking that prevents
concurrent refreshes of the same Business's connection, and the disconnect
view's local-invalidation behavior (see its docstring for why no remote
revocation call is attempted — Mercado Pago documents revocation as
user/MP-initiated only, with no supported endpoint for an app to trigger it
remotely).

Encryption-at-rest, the OAuth start/callback/status flow, and basic
credential-resolution rules (not-connected, wrong status, blank token,
cross-tenant isolation) are already covered by `test_token_encryption.py`,
`test_oauth_flow.py`, and `test_token_resolution.py` respectively — not
duplicated here.
"""
from __future__ import annotations

import datetime
import threading
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps as django_apps
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.merchant_payments.models import MercadoPagoConnection
from apps.merchant_payments.services import (
    TOKEN_REFRESH_SKEW,
    MerchantPaymentConnectionUnavailable,
    get_merchant_connection,
    get_merchant_mp_client,
)

TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='
MP_DISCONNECT_URL = '/api/v1/menu/mercadopago/connect/'


def _business(name='Negocio') -> Business:
    return Business.objects.create(name=name, default_service='restaurante')


def _fake_refresh_response(**overrides):
    payload = {
        'access_token': 'REFRESHED-ACCESS-TOKEN',
        'refresh_token': 'REFRESHED-REFRESH-TOKEN',
        'expires_in': 3600,
        'scope': 'read write',
        'user_id': 999,
    }
    payload.update(overrides)
    return SimpleNamespace(status_code=200, json=lambda: payload)


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY, MP_CLIENT_ID='CID', MP_CLIENT_SECRET='CSECRET')
class RefreshDecisionTests(TestCase):
    """Items 1-3: whether a refresh is attempted at all."""

    @patch('apps.merchant_payments.services.requests.post')
    def test_valid_token_does_not_refresh(self, mock_post):
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN-1', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() + datetime.timedelta(days=30),
        )
        conn = get_merchant_connection(business)
        mock_post.assert_not_called()
        self.assertEqual(conn.access_token, 'TOKEN-1')

    @patch('apps.merchant_payments.services.requests.post')
    def test_token_near_expiry_within_skew_refreshes(self, mock_post):
        mock_post.return_value = _fake_refresh_response()
        business = _business()
        near_expiry = timezone.now() + (TOKEN_REFRESH_SKEW / 2)
        MercadoPagoConnection.objects.create(
            business=business, access_token='OLD-TOKEN', refresh_token='REFRESH-1',
            status='connected', token_expires_at=near_expiry,
        )
        conn = get_merchant_connection(business)
        mock_post.assert_called_once()
        self.assertEqual(conn.access_token, 'REFRESHED-ACCESS-TOKEN')

    @patch('apps.merchant_payments.services.requests.post')
    def test_expired_token_refreshes(self, mock_post):
        mock_post.return_value = _fake_refresh_response()
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='OLD-TOKEN', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        conn = get_merchant_connection(business)
        mock_post.assert_called_once()
        self.assertEqual(conn.access_token, 'REFRESHED-ACCESS-TOKEN')


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY, MP_CLIENT_ID='CID', MP_CLIENT_SECRET='CSECRET')
class RefreshPersistenceTests(TestCase):
    """Items 4-7: what a successful refresh writes, and that it stays encrypted."""

    @patch('apps.merchant_payments.services.requests.post')
    def test_new_access_token_persisted(self, mock_post):
        mock_post.return_value = _fake_refresh_response(access_token='NEW-ACCESS')
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        get_merchant_connection(business)
        conn.refresh_from_db()
        self.assertEqual(conn.access_token, 'NEW-ACCESS')

    @patch('apps.merchant_payments.services.requests.post')
    def test_rotated_refresh_token_persisted(self, mock_post):
        mock_post.return_value = _fake_refresh_response(refresh_token='ROTATED-REFRESH')
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='ORIGINAL-REFRESH',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        get_merchant_connection(business)
        conn.refresh_from_db()
        self.assertEqual(conn.refresh_token, 'ROTATED-REFRESH')

    @patch('apps.merchant_payments.services.requests.post')
    def test_missing_refresh_token_in_response_keeps_previous_one(self, mock_post):
        """MP's docs say the refresh_token always rotates, but the resolver
        must not destroy a usable one if a response ever omits it."""
        mock_post.return_value = _fake_refresh_response(refresh_token=None)
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='ORIGINAL-REFRESH',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        get_merchant_connection(business)
        conn.refresh_from_db()
        self.assertEqual(conn.refresh_token, 'ORIGINAL-REFRESH')

    @patch('apps.merchant_payments.services.requests.post')
    def test_expiry_updated_from_expires_in(self, mock_post):
        mock_post.return_value = _fake_refresh_response(expires_in=7200)
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        before = timezone.now()
        get_merchant_connection(business)
        conn.refresh_from_db()
        self.assertGreater(conn.token_expires_at, before + datetime.timedelta(seconds=7000))

    @patch('apps.merchant_payments.services.requests.post')
    def test_refreshed_tokens_remain_encrypted_in_db(self, mock_post):
        mock_post.return_value = _fake_refresh_response(
            access_token='SUPER-SECRET-NEW-ACCESS', refresh_token='SUPER-SECRET-NEW-REFRESH',
        )
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        get_merchant_connection(business)

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT access_token, refresh_token FROM menu_mercadopagoconnection WHERE id = %s',
                [conn.id],
            )
            raw_access, raw_refresh = cursor.fetchone()
        self.assertNotIn('SUPER-SECRET-NEW-ACCESS', raw_access)
        self.assertNotIn('SUPER-SECRET-NEW-REFRESH', raw_refresh)


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY, MP_CLIENT_ID='CID', MP_CLIENT_SECRET='CSECRET')
class RefreshFailureTests(TestCase):
    """Items 10-13: distinguishable failure modes, all fail-safe, no secrets leaked."""

    def test_no_refresh_token_fails_safe_without_network_call(self):
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        with patch('apps.merchant_payments.services.requests.post') as mock_post:
            with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
                get_merchant_connection(business)
        mock_post.assert_not_called()
        self.assertEqual(ctx.exception.reason, 'no_refresh_token')
        conn.refresh_from_db()
        self.assertEqual(conn.status, 'error')

    @patch('apps.merchant_payments.services.requests.post')
    @patch('mercadopago.SDK')
    def test_refresh_rejected_never_falls_back_to_global_token(self, mock_sdk, mock_post):
        mock_post.return_value = SimpleNamespace(status_code=400, json=lambda: {'error': 'invalid_grant'})
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='STALE-REFRESH',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_mp_client(business)
        self.assertEqual(ctx.exception.reason, 'refresh_rejected')
        mock_sdk.assert_not_called()
        conn.refresh_from_db()
        self.assertEqual(conn.status, 'error')
        self.assertEqual(conn.last_error, 'refresh_rejected')

    @patch('apps.merchant_payments.services.requests.post')
    def test_invalid_response_fails_safe(self, mock_post):
        mock_post.return_value = SimpleNamespace(status_code=200, json=lambda: {'scope': 'read'})
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertEqual(ctx.exception.reason, 'invalid_refresh_response')
        conn.refresh_from_db()
        self.assertEqual(conn.status, 'error')

    @patch('apps.merchant_payments.services.requests.post')
    def test_transient_network_error_does_not_flip_status_to_error(self, mock_post):
        import requests as requests_module
        mock_post.side_effect = requests_module.ConnectionError('boom')
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='OLD', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertEqual(ctx.exception.reason, 'refresh_temporarily_unavailable')
        conn.refresh_from_db()
        # Transient failure — status must stay 'connected' so the next
        # request can retry without requiring the user to reconnect.
        self.assertEqual(conn.status, 'connected')

    @patch('apps.merchant_payments.services.requests.post')
    def test_error_message_never_contains_secret_tokens(self, mock_post):
        mock_post.return_value = SimpleNamespace(status_code=400, json=lambda: {'error': 'invalid_grant'})
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='SUPER-SECRET-ACCESS', refresh_token='SUPER-SECRET-REFRESH',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        message = str(ctx.exception)
        self.assertNotIn('SUPER-SECRET-ACCESS', message)
        self.assertNotIn('SUPER-SECRET-REFRESH', message)


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY, MP_CLIENT_ID='CID', MP_CLIENT_SECRET='CSECRET')
class CrossTenantRefreshTests(TestCase):
    """Item 19: refreshing one Business's connection must never touch another's."""

    @patch('apps.merchant_payments.services.requests.post')
    def test_refreshing_business_a_never_touches_business_b(self, mock_post):
        mock_post.return_value = _fake_refresh_response(access_token='A-REFRESHED')
        business_a = _business('A')
        business_b = _business('B')
        MercadoPagoConnection.objects.create(
            business=business_a, access_token='A-OLD', refresh_token='A-REFRESH',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        conn_b = MercadoPagoConnection.objects.create(
            business=business_b, access_token='B-TOKEN', refresh_token='B-REFRESH',
            status='connected', token_expires_at=timezone.now() + datetime.timedelta(days=30),
        )

        get_merchant_connection(business_a)

        conn_b.refresh_from_db()
        self.assertEqual(conn_b.access_token, 'B-TOKEN')
        mock_post.assert_called_once()


class ConcurrentRefreshTests(TransactionTestCase):
    """Items 8-9: concurrent requests for the same Business collapse into a
    single remote refresh; every caller ends up with the refreshed token.

    Requires PostgreSQL — same reasoning/workaround as
    `apps.appointments.tests.test_appointments_concurrency`: `TestCase`
    shares one connection/transaction across threads, which would never
    exercise real row locking.
    """
    available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

    def setUp(self):
        self.business = _business('Concurrency Biz')

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY, MP_CLIENT_ID='CID', MP_CLIENT_SECRET='CSECRET')
    @patch('apps.merchant_payments.services.requests.post')
    def test_five_concurrent_requests_trigger_exactly_one_refresh(self, mock_post):
        mock_post.return_value = _fake_refresh_response(access_token='REFRESHED-ONCE')
        MercadoPagoConnection.objects.create(
            business=self.business, access_token='OLD', refresh_token='REFRESH-1',
            status='connected', token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )

        results: list[str] = []
        errors: list[BaseException] = []
        results_lock = threading.Lock()

        def attempt():
            try:
                conn = get_merchant_connection(self.business)
                with results_lock:
                    results.append(conn.access_token)
            except BaseException as exc:  # noqa: BLE001 — captured for assertion, not swallowed
                with results_lock:
                    errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 5)
        # Item 9: every caller — including the 4 that didn't refresh —
        # reused the single refreshed token, never the stale one.
        self.assertTrue(all(token == 'REFRESHED-ONCE' for token in results), results)
        # Item 8: exactly one remote refresh call, no matter how many
        # concurrent requests needed a usable token.
        self.assertEqual(mock_post.call_count, 1)


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class DisconnectLifecycleTests(TestCase):
    """Items 15-18: local invalidation is immediate and unconditional;
    there is no remote revocation call to succeed or fail (see
    `MercadoPagoDisconnectView`'s docstring for why)."""

    def _authenticated_client(self, business: Business) -> APIClient:
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(
            username=f'disc-user-{business.id}', password='pass1234',
        )
        Subscription.objects.create(business=business, plan=BusinessPlan.PLUS, status='active')
        Membership.objects.create(user=user, business=business, role='owner')
        client = APIClient()
        client.force_authenticate(user)
        client.cookies['bid'] = str(business.id)
        return client

    def test_disconnect_prevents_local_use_immediately(self):
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN', refresh_token='REFRESH', status='connected',
        )
        client = self._authenticated_client(business)

        response = client.delete(MP_DISCONNECT_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertEqual(ctx.exception.reason, 'not_connected')

    def test_no_tokens_usable_after_disconnect(self):
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN', refresh_token='REFRESH', status='connected',
        )
        client = self._authenticated_client(business)
        client.delete(MP_DISCONNECT_URL)

        with self.assertRaises(MerchantPaymentConnectionUnavailable):
            get_merchant_mp_client(business)
        self.assertFalse(MercadoPagoConnection.objects.filter(business=business).exists())

    def test_disconnect_never_makes_a_remote_http_call(self):
        """No documented, supported endpoint exists for the app to remotely
        revoke a specific user's authorization (see view docstring) — so
        disconnect must never attempt one."""
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN', refresh_token='REFRESH', status='connected',
        )
        client = self._authenticated_client(business)

        with patch('apps.merchant_payments.views.requests') as mock_requests:
            response = client.delete(MP_DISCONNECT_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_requests.post.assert_not_called()

    def test_disconnect_succeeds_even_if_mercado_pago_is_unreachable(self):
        """There is nothing remote to fail, so local disconnect must succeed
        unconditionally — including while MP itself would be down."""
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN', refresh_token='REFRESH', status='connected',
        )
        client = self._authenticated_client(business)

        with patch('apps.merchant_payments.views.requests.post', side_effect=Exception('MP is down')):
            response = client.delete(MP_DISCONNECT_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(MercadoPagoConnection.objects.filter(business=business).exists())
