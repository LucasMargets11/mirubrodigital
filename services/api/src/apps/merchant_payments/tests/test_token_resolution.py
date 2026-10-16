"""
Unit tests for apps.merchant_payments.services — the canonical merchant-side
(Customer → Business) Mercado Pago credential resolver. Slice 5B.1.

These exercise the resolver directly (no HTTP layer), independent of any
one consumer (Tips today, Turnos later).
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.business.models import Business
from apps.merchant_payments.models import MercadoPagoConnection
from apps.merchant_payments.services import (
    MerchantPaymentConnectionUnavailable,
    get_merchant_connection,
    get_merchant_mp_client,
)

# Slice 5B.3A added Fernet encryption-at-rest for access_token/refresh_token
# (see apps.merchant_payments.crypto) — any MercadoPagoConnection write now
# needs a valid key configured.
TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class GetMerchantConnectionTests(TestCase):
    def _business(self, name='Negocio') -> Business:
        return Business.objects.create(name=name, default_service='restaurante')

    def test_returns_connection_when_connected_with_token(self):
        business = self._business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN-1', status='connected',
        )
        self.assertEqual(get_merchant_connection(business), conn)

    def test_raises_when_no_connection_exists(self):
        business = self._business()
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertEqual(ctx.exception.reason, 'not_connected')

    def test_raises_when_status_not_connected(self):
        business = self._business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN-1', status='revoked',
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertIn('status=revoked', ctx.exception.reason)

    def test_raises_when_access_token_blank(self):
        business = self._business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='', status='connected',
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertEqual(ctx.exception.reason, 'missing_access_token')

    def test_raises_when_token_expired_and_no_refresh_token(self):
        """Slice 5B.3B: an expired token now triggers an attempted refresh
        instead of failing immediately on the stale check. With no
        refresh_token stored, that attempt fails safe — see
        test_refresh_lifecycle.py for the full refresh behavior."""
        business = self._business()
        MercadoPagoConnection.objects.create(
            business=business,
            access_token='TOKEN-1',
            status='connected',
            token_expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertEqual(ctx.exception.reason, 'no_refresh_token')

    def test_no_expiry_recorded_is_fine(self):
        business = self._business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN-1', status='connected', token_expires_at=None,
        )
        self.assertEqual(get_merchant_connection(business), conn)

    def test_exception_message_never_contains_token(self):
        business = self._business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='SUPER-SECRET-TOKEN', status='error',
        )
        with self.assertRaises(MerchantPaymentConnectionUnavailable) as ctx:
            get_merchant_connection(business)
        self.assertNotIn('SUPER-SECRET-TOKEN', str(ctx.exception))

    def test_business_a_never_resolves_to_business_b_connection(self):
        business_a = self._business('A')
        business_b = self._business('B')
        MercadoPagoConnection.objects.create(business=business_a, access_token='TOKEN-A', status='connected')
        MercadoPagoConnection.objects.create(business=business_b, access_token='TOKEN-B', status='connected')

        conn_a = get_merchant_connection(business_a)
        conn_b = get_merchant_connection(business_b)

        self.assertEqual(conn_a.access_token, 'TOKEN-A')
        self.assertEqual(conn_b.access_token, 'TOKEN-B')


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class GetMerchantMpClientTests(TestCase):
    def _business(self, name='Negocio') -> Business:
        return Business.objects.create(name=name, default_service='restaurante')

    @patch('mercadopago.SDK')
    def test_builds_sdk_with_business_token(self, mock_sdk_class):
        business = self._business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN-1', status='connected',
        )
        get_merchant_mp_client(business)
        mock_sdk_class.assert_called_once_with('TOKEN-1')

    @patch('mercadopago.SDK')
    def test_never_builds_sdk_with_settings_global_token(self, mock_sdk_class):
        from django.conf import settings
        business = self._business()
        MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN-1', status='connected',
        )
        get_merchant_mp_client(business)
        for call in mock_sdk_class.call_args_list:
            self.assertNotEqual(call.args[0] if call.args else None, getattr(settings, 'MP_ACCESS_TOKEN', object()))

    @patch('mercadopago.SDK')
    def test_raises_without_calling_sdk_when_unavailable(self, mock_sdk_class):
        business = self._business()
        with self.assertRaises(MerchantPaymentConnectionUnavailable):
            get_merchant_mp_client(business)
        mock_sdk_class.assert_not_called()
