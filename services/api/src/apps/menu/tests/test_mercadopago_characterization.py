"""
Characterization tests for how Tips (apps.menu) consumes the merchant-side
Mercado Pago connection.

Written BEFORE the Slice 5A extraction (`apps.merchant_payments`), when
MercadoPagoConnection still lived in `apps.menu.models`; confirmed green
there, then updated to import the model from its new home after the
extraction. The OAuth connect-flow tests that used to live in this same
file moved to `apps.merchant_payments.tests.test_oauth_flow` — TipTransaction
and the tip creation/verify views stay in `apps.menu`, only consuming the
connection now owned by `apps.merchant_payments`.

Slice 5B.1: Tips no longer falls back to the platform's global MP_ACCESS_TOKEN
when a business has no usable connection. That behavior is deliberately no
longer valid and its characterization test below has been replaced with tests
proving the new, hardened behavior: explicit failure, no global fallback, no
cross-tenant token leakage, and no token exposure in responses or logs.
"""
from __future__ import annotations

import logging
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.business.models import Business, BusinessPlan, Subscription
from apps.menu.models import MenuEngagementSettings, PublicMenuConfig, TipTransaction
from apps.merchant_payments.models import MercadoPagoConnection


@override_settings(MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN')
class TipsConsumesMercadoPagoConnectionCharacterizationTests(APITestCase):
    """Freezes how Tips (menu) resolves the MP access token via the connection."""

    def setUp(self):
        cache.clear()

    def _create_business_with_tips(self, name: str = 'Restaurante Tips') -> Business:
        business = Business.objects.create(name=name, default_service='restaurante')
        Subscription.objects.create(business=business, plan=BusinessPlan.PLUS, status='active')
        config = PublicMenuConfig.objects.create(
            business=business, enabled=True, slug=f"{name.lower().replace(' ', '-')}", brand_name=business.name,
        )
        MenuEngagementSettings.objects.create(
            business=business, tips_enabled=True, tips_mode='mp_oauth_checkout',
        )
        return business, config

    @patch('mercadopago.SDK')
    def test_tip_uses_business_connection_token_when_connected(self, mock_sdk_class):
        business, config = self._create_business_with_tips()
        MercadoPagoConnection.objects.create(
            business=business, access_token='BUSINESS-OWN-TOKEN', mp_user_id='77', status='connected',
        )
        mock_sdk_instance = mock_sdk_class.return_value
        mock_sdk_instance.preference.return_value.create.return_value = {
            'status': 201, 'response': {'id': 'pref-123', 'init_point': 'https://mp.example/init'},
        }

        url = f'/api/v1/menu/public/slug/{config.slug}/tips/create-preference/'
        response = self.client.post(url, {'amount': '150.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_sdk_class.assert_called_once_with('BUSINESS-OWN-TOKEN')

        tip = TipTransaction.objects.get(business=business)
        self.assertEqual(tip.status, 'pending')
        self.assertEqual(tip.mp_preference_id, 'pref-123')

    @patch('mercadopago.SDK')
    def test_tip_fails_explicitly_when_business_not_connected(self, mock_sdk_class):
        """No connection at all → explicit 503, never the global platform token."""
        business, config = self._create_business_with_tips('Sin Conectar')

        url = f'/api/v1/menu/public/slug/{config.slug}/tips/create-preference/'
        response = self.client.post(url, {'amount': '80.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        mock_sdk_class.assert_not_called()
        self.assertFalse(TipTransaction.objects.filter(business=business).exists())

    @patch('mercadopago.SDK')
    def test_tip_fails_explicitly_when_connection_not_status_connected(self, mock_sdk_class):
        """A connection row exists but status != 'connected' → still explicit failure, no fallback."""
        business, config = self._create_business_with_tips('Conexion Vencida')
        MercadoPagoConnection.objects.create(
            business=business, access_token='STALE-TOKEN', mp_user_id='99', status='expired',
        )

        url = f'/api/v1/menu/public/slug/{config.slug}/tips/create-preference/'
        response = self.client.post(url, {'amount': '80.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        mock_sdk_class.assert_not_called()

    @patch('mercadopago.SDK')
    def test_global_token_never_used_for_merchant_payments(self, mock_sdk_class):
        """Regression guard: whatever the outcome, the global platform token is never
        the value handed to the MP SDK for a merchant-side (Tips) flow."""
        business, config = self._create_business_with_tips('Nunca Global')
        mock_sdk_instance = mock_sdk_class.return_value
        mock_sdk_instance.preference.return_value.create.return_value = {
            'status': 201, 'response': {'id': 'pref-999', 'init_point': 'https://mp.example/init'},
        }

        url = f'/api/v1/menu/public/slug/{config.slug}/tips/create-preference/'
        self.client.post(url, {'amount': '10.00'}, format='json')

        for call in mock_sdk_class.call_args_list:
            self.assertNotIn('GLOBAL-PLATFORM-TOKEN', call.args)

    @patch('mercadopago.SDK')
    def test_business_a_never_uses_business_b_token(self, mock_sdk_class):
        """Cross-tenant guard: Business A's tip must use A's token, never B's."""
        business_a, config_a = self._create_business_with_tips('Negocio A')
        business_b, _config_b = self._create_business_with_tips('Negocio B')
        MercadoPagoConnection.objects.create(
            business=business_a, access_token='TOKEN-A', mp_user_id='1', status='connected',
        )
        MercadoPagoConnection.objects.create(
            business=business_b, access_token='TOKEN-B', mp_user_id='2', status='connected',
        )
        mock_sdk_instance = mock_sdk_class.return_value
        mock_sdk_instance.preference.return_value.create.return_value = {
            'status': 201, 'response': {'id': 'pref-a', 'init_point': 'https://mp.example/init'},
        }

        url = f'/api/v1/menu/public/slug/{config_a.slug}/tips/create-preference/'
        response = self.client.post(url, {'amount': '25.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_sdk_class.assert_called_once_with('TOKEN-A')

    @patch('mercadopago.SDK')
    def test_connection_unavailable_error_does_not_leak_token_in_response(self, mock_sdk_class):
        business, config = self._create_business_with_tips('Respuesta Segura')
        MercadoPagoConnection.objects.create(
            business=business, access_token='SUPER-SECRET-TOKEN', mp_user_id='5', status='error',
        )

        url = f'/api/v1/menu/public/slug/{config.slug}/tips/create-preference/'
        response = self.client.post(url, {'amount': '10.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertNotIn('SUPER-SECRET-TOKEN', str(response.content))

    @patch('mercadopago.SDK')
    def test_connection_unavailable_error_does_not_leak_token_in_logs(self, mock_sdk_class):
        business, config = self._create_business_with_tips('Logs Seguros')
        MercadoPagoConnection.objects.create(
            business=business, access_token='SUPER-SECRET-LOG-TOKEN', mp_user_id='6', status='revoked',
        )

        url = f'/api/v1/menu/public/slug/{config.slug}/tips/create-preference/'
        with self.assertLogs('apps.menu.views', level='WARNING') as captured:
            self.client.post(url, {'amount': '10.00'}, format='json')

        for message in captured.output:
            self.assertNotIn('SUPER-SECRET-LOG-TOKEN', message)
