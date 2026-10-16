"""
Slice 5B.2 / 5B.2.1 / 5B.2.2 — deterministic webhook credential routing.

Regression coverage for MercadoPagoWebhookView.process_payment_event().

Before 5B.2, every `payment` webhook was re-fetched with the platform's
global MP_ACCESS_TOKEN (apps.billing.mp_service.MercadoPagoService) BEFORE
the code even knew whether the payment belonged to Billing or to a merchant
(Tips).

5B.2 / 5B.2.1 added a `flow=tip&ref=<external_reference>` hint to Tip
Preferences (set at creation time in PublicTipCreatePreferenceView) so the
webhook resolves the owning Business from the local TipTransaction FIRST,
then re-fetches the payment using ONLY that Business's own Mercado Pago
connection (apps.merchant_payments). A local `TipTransaction.mp_payment_id`
fallback covered Preferences created before the hint existed.

5B.2.2 closes the remaining gaps:
  - Billing Preferences now carry the same kind of hint —
    `flow=billing&ref=<external_reference>` (set in
    MercadoPagoService.create_preference) — resolved against
    PendingSubscriptionChange BEFORE the (always-platform-token) fetch.
  - The `TipTransaction.mp_payment_id` historic fallback is REMOVED as an
    authoritative routing decision: a bare payment_id is scoped per Mercado
    Pago account and can coincide between two unrelated accounts (e.g. a
    Tip and a Billing charge), so using it to decide which credential to
    fetch with — before knowing the account — is exactly the ambiguous
    routing this slice eliminates. Events with no recognized flow hint are
    now failed closed: no fetch, no mutation, logged as unresolved. Recovery
    for historic Tips remains PublicTipVerifyView (resolved via the tip_id
    URL path parameter, unambiguous by construction).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.business.models import Business
from apps.menu.models import TipTransaction
from apps.merchant_payments.models import MercadoPagoConnection

User = get_user_model()

WEBHOOK_URL = '/api/v1/billing/mercadopago/webhook'

# Slice 5B.3A added Fernet encryption-at-rest for MercadoPagoConnection
# access_token/refresh_token (see apps.merchant_payments.crypto) — any test
# class below that creates one needs a valid key configured.
TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='


def _payment_webhook_body(payment_id: str) -> dict:
    return {'type': 'payment', 'data': {'id': payment_id}, 'action': 'payment.updated'}


def _sdk_factory(*, forbidden_tokens: frozenset = frozenset(), responses: dict | None = None):
    """
    Builds a `mercadopago.SDK` side_effect for asserting which credential a
    code path actually uses.

    - Raises immediately (failing the test loudly, not just via a later
      assertion) if instantiated with any token in `forbidden_tokens` — used
      to prove the platform's global token can never even be constructed on
      a route that must never touch it.
    - Otherwise returns a MagicMock whose `payment().get(...)` answers with
      `responses[token]` (default: a 404-shaped response for unlisted tokens).
    """
    responses = responses or {}

    def factory(token, *args, **kwargs):
        if token in forbidden_tokens:
            raise AssertionError(
                f"mercadopago.SDK must never be instantiated with token={token!r} on this route",
            )
        instance = MagicMock()
        instance.payment.return_value.get.return_value = responses.get(
            token, {'status': 404, 'response': {}},
        )
        return instance

    return factory


@override_settings(
    MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', MP_WEBHOOK_SECRET=None, DEBUG=True,
    MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
)
class MercadoPagoWebhookMerchantRoutingTests(APITestCase):
    """Dev-bypass signature (no MP_WEBHOOK_SECRET) — focuses on credential routing."""

    def setUp(self):
        cache.clear()

    def _business_with_tip(self, *, name='Restaurante', connected=True, token='BUSINESS-TOKEN',
                            ref='TIP-ROUTINGTEST00001'):
        business = Business.objects.create(name=name, default_service='restaurante')
        if connected:
            MercadoPagoConnection.objects.create(
                business=business, access_token=token, status='connected',
            )
        tip = TipTransaction.objects.create(
            business=business, amount='100.00', currency='ARS', status='pending',
            external_reference=ref,
        )
        return business, tip

    # Covers: (2) webhook Tip -> usa token del Business, (3) Tip nunca usa
    # token global, (10) payment aprobado -> transición correcta.
    @patch('mercadopago.SDK')
    def test_tip_webhook_uses_business_token_and_approves(self, mock_sdk_class):
        business, tip = self._business_with_tip()
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'approved', 'external_reference': tip.external_reference},
        }

        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref={tip.external_reference}',
            _payment_webhook_body('pay-1'), format='json',
        )

        self.assertEqual(resp.status_code, 200)
        # Proves both (2) and (3) at once: the SDK was built with the
        # Business's own token, and never with the global platform token.
        mock_sdk_class.assert_called_once_with('BUSINESS-TOKEN')
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')
        self.assertEqual(tip.mp_payment_id, 'pay-1')

    # Covers: (4) Business A nunca procesa con token de B.
    @patch('mercadopago.SDK')
    def test_business_a_never_uses_business_b_token(self, mock_sdk_class):
        _business_a, tip_a = self._business_with_tip(
            name='Negocio A', token='TOKEN-A', ref='TIP-BUSINESSA0000001',
        )
        self._business_with_tip(name='Negocio B', token='TOKEN-B', ref='TIP-BUSINESSB0000001')
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'approved', 'external_reference': tip_a.external_reference},
        }

        self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref={tip_a.external_reference}',
            _payment_webhook_body('pay-2'), format='json',
        )

        mock_sdk_class.assert_called_once_with('TOKEN-A')

    # Covers: (5) conexión merchant inexistente -> fallo explícito, no fallback.
    @patch('mercadopago.SDK')
    def test_missing_merchant_connection_fails_explicitly_no_fallback(self, mock_sdk_class):
        _business, tip = self._business_with_tip(connected=False)

        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref={tip.external_reference}',
            _payment_webhook_body('pay-3'), format='json',
        )

        self.assertEqual(resp.status_code, 200)  # webhook ack, no MP retry storm
        mock_sdk_class.assert_not_called()  # neither business's nor platform's SDK
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')  # untouched

    # Covers: (6) payment re-fetch devuelve otro external_reference -> no confirmar.
    @patch('mercadopago.SDK')
    def test_external_reference_mismatch_does_not_confirm(self, mock_sdk_class):
        _business, tip = self._business_with_tip()
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'approved', 'external_reference': 'TIP-SOMETHINGELSE001'},
        }

        self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref={tip.external_reference}',
            _payment_webhook_body('pay-4'), format='json',
        )

        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')
        self.assertIsNone(tip.mp_payment_id)

    # Covers: (9) TipTransaction inexistente -> no mutación.
    @patch('mercadopago.SDK')
    def test_unknown_tip_reference_no_mutation(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref=TIP-DOESNOTEXIST00001',
            _payment_webhook_body('pay-5'), format='json',
        )

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()
        self.assertFalse(TipTransaction.objects.filter(external_reference='TIP-DOESNOTEXIST00001').exists())

    # Covers: (11) payment rechazado -> comportamiento actual preservado.
    @patch('mercadopago.SDK')
    def test_tip_webhook_rejected_status(self, mock_sdk_class):
        _business, tip = self._business_with_tip()
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'rejected', 'external_reference': tip.external_reference},
        }

        self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref={tip.external_reference}',
            _payment_webhook_body('pay-6'), format='json',
        )

        tip.refresh_from_db()
        self.assertEqual(tip.status, 'rejected')

    # Covers: (7) webhook duplicado -> idempotente.
    #
    # Note: WebhookDelivery-level dedup (x-request-id) only short-circuits the
    # Phase 3 topics (subscription_preapproval / subscription_authorized_payment)
    # — the legacy `payment` topic re-processes every delivery. Idempotency for
    # Tips instead comes from process_tip_payment's write-if-changed update, so
    # replaying the same webhook converges to the same final state without
    # ever touching a different (e.g. the global) credential.
    @patch('mercadopago.SDK')
    def test_duplicate_tip_webhook_is_idempotent(self, mock_sdk_class):
        _business, tip = self._business_with_tip()
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'approved', 'external_reference': tip.external_reference},
        }

        url = f'{WEBHOOK_URL}?flow=tip&ref={tip.external_reference}'
        body = _payment_webhook_body('pay-7')

        r1 = self.client.post(url, body, format='json', HTTP_X_REQUEST_ID='dup-req-1')
        r2 = self.client.post(url, body, format='json', HTTP_X_REQUEST_ID='dup-req-2')

        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        for call in mock_sdk_class.call_args_list:
            self.assertEqual(call.args, ('BUSINESS-TOKEN',))
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')
        self.assertEqual(tip.mp_payment_id, 'pay-7')

    # Covers: (12) tokens no aparecen en response/logs.
    def test_missing_connection_does_not_leak_token_in_logs(self):
        business, tip = self._business_with_tip(connected=False)
        MercadoPagoConnection.objects.create(
            business=business, access_token='SUPER-SECRET-TOKEN', status='revoked',
        )

        with self.assertLogs('apps.billing', level='WARNING') as captured:
            resp = self.client.post(
                f'{WEBHOOK_URL}?flow=tip&ref={tip.external_reference}',
                _payment_webhook_body('pay-8'), format='json',
            )

        self.assertNotIn('SUPER-SECRET-TOKEN', str(resp.content))
        for message in captured.output:
            self.assertNotIn('SUPER-SECRET-TOKEN', message)


# Covers: (2) nuevo Billing -> routing plataforma antes del fetch; (4) Billing
# jamás instancia cliente merchant; (6) hint Billing manipulado -> no mutación.
#
# Slice 5B.2.2: Billing Preferences now carry an explicit
# `flow=billing&ref=<external_reference>` hint (set in
# MercadoPagoService.create_preference), the same way Tips do. The webhook
# resolves the expected PendingSubscriptionChange from `ref` BEFORE fetching
# — the fetch itself always uses the platform token (Billing never had a
# merchant-credential risk), but the hint removes the need for a speculative
# "classification" fetch to find out whether an unhinted payment is Billing
# or a Tip (see MercadoPagoWebhookLegacyUnresolvedRoutingTests below for why
# that classification fetch was removed).
@override_settings(MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', MP_WEBHOOK_SECRET=None, DEBUG=True)
class MercadoPagoWebhookBillingRoutingTests(APITestCase):
    def setUp(self):
        cache.clear()

    def _pending_change(self, *, business=None, kind='subscription_change', **extra):
        from apps.billing.models import PendingSubscriptionChange
        if business is None:
            business = Business.objects.create(name='Negocio Billing', default_service='gestion')
        user = self._user()
        defaults = dict(
            business=business, user=user, target_plan_code='pro', billing_cycle='monthly',
            config_snapshot={}, line_items=[], total_amount=1000, requires_checkout=True,
            status='pending_payment',
        )
        defaults.update(extra)
        pending = PendingSubscriptionChange.objects.create(**defaults)
        ref = f"{kind}_{pending.id}"
        return pending, ref

    def _user(self):
        return User.objects.create_user(username=f'user{User.objects.count()}', password='x')

    @patch('mercadopago.SDK')
    def test_billing_flow_hint_uses_platform_token_and_applies(self, mock_sdk_class):
        from apps.billing.models import PendingSubscriptionChange
        pending, ref = self._pending_change()
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'approved', 'external_reference': ref},
        }

        with patch('apps.billing.services.commercial.apply.apply_subscription_change') as mock_apply:
            resp = self.client.post(
                f'{WEBHOOK_URL}?flow=billing&ref={ref}',
                _payment_webhook_body('pay-100'), format='json',
            )

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_called_once_with('GLOBAL-PLATFORM-TOKEN')
        mock_apply.assert_called_once()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assertEqual(pending.mp_payment_id, 'pay-100')

    # Covers: (6) hint Billing manipulado -> no mutación.
    @patch('mercadopago.SDK')
    def test_billing_ref_pointing_at_unrelated_change_never_confirms_mismatch(self, mock_sdk_class):
        pending_a, ref_a = self._pending_change(kind='subscription_change')
        _pending_b, ref_b = self._pending_change(kind='subscription_change')
        # The hint says ref_a, but MP's own fetched payment resolves to ref_b —
        # must not apply anything to either record.
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'approved', 'external_reference': ref_b},
        }

        with patch('apps.billing.services.commercial.apply.apply_subscription_change') as mock_apply:
            self.client.post(
                f'{WEBHOOK_URL}?flow=billing&ref={ref_a}',
                _payment_webhook_body('pay-101'), format='json',
            )

        mock_apply.assert_not_called()
        pending_a.refresh_from_db()
        self.assertEqual(pending_a.status, 'pending_payment')
        self.assertIsNone(pending_a.mp_payment_id)

    # Covers: (6) PendingSubscriptionChange inexistente -> no mutación, no fetch necesario.
    @patch('mercadopago.SDK')
    def test_billing_ref_unknown_change_no_fetch(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref=subscription_change_999999999',
            _payment_webhook_body('pay-102'), format='json',
        )

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()


# Covers: (8) firma inválida -> rechazado, at the full webhook-view level —
# a bad signature must reject before ANY credential routing (Billing or merchant).
@override_settings(MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', MP_WEBHOOK_SECRET='real-secret', DEBUG=False)
class MercadoPagoWebhookInvalidSignatureRoutingTests(APITestCase):
    def setUp(self):
        cache.clear()

    @patch('mercadopago.SDK')
    def test_invalid_signature_rejected_before_any_routing(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref=TIP-WHATEVER000000001',
            _payment_webhook_body('pay-bad-sig'), format='json',
            HTTP_X_SIGNATURE='ts=1,v1=deadbeef', HTTP_X_REQUEST_ID='req-bad-sig',
        )

        self.assertEqual(resp.status_code, 400)
        mock_sdk_class.assert_not_called()


# ── Slice 5B.2.2 ─────────────────────────────────────────────────────────────
# Removes the 5B.2.1 fallback that decided routing by searching
# TipTransaction.mp_payment_id for the incoming payment_id: a bare payment_id
# is scoped per Mercado Pago account, so two DIFFERENT accounts (e.g. a
# merchant business and MiRubro's own platform account, or two different
# merchant businesses) can end up with the same numeric id. Deciding which
# credential to fetch with — merchant vs platform, or business A vs business
# B — from that id alone is exactly the ambiguous routing item 6 of the
# Slice 5B.2.2 audit requires removing. It is no longer consulted at all: a
# webhook with no `flow` hint is now failed closed unconditionally.
@override_settings(
    MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', MP_WEBHOOK_SECRET=None, DEBUG=True,
    MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
)
class MercadoPagoWebhookLegacyUnresolvedRoutingTests(APITestCase):
    def setUp(self):
        cache.clear()

    def _business_with_tip(self, *, name='Restaurante', connected=True, token='BUSINESS-TOKEN',
                            ref='TIP-HIST000000000001', mp_payment_id=None):
        business = Business.objects.create(name=name, default_service='restaurante')
        if connected:
            MercadoPagoConnection.objects.create(
                business=business, access_token=token, status='connected',
            )
        tip = TipTransaction.objects.create(
            business=business, amount='50.00', currency='ARS', status='pending',
            external_reference=ref, mp_payment_id=mp_payment_id,
        )
        return business, tip

    def _pending_change(self, *, business=None, ref_prefix='subscription_change', mp_payment_id=None):
        from apps.billing.models import PendingSubscriptionChange
        if business is None:
            business = Business.objects.create(name='Negocio Billing', default_service='gestion')
        user = User.objects.create_user(username=f'user{User.objects.count()}', password='x')
        pending = PendingSubscriptionChange.objects.create(
            business=business, user=user, target_plan_code='pro', billing_cycle='monthly',
            config_snapshot={}, line_items=[], total_amount=1000, requires_checkout=True,
            status='pending_payment', mp_payment_id=mp_payment_id,
        )
        ref = f"{ref_prefix}_{pending.id}"
        return pending, ref

    # Covers: (7) legacy sin flow y sin correlación inequívoca -> ningún fetch,
    # for a Tip that would previously have been resolved via the
    # mp_payment_id fallback.
    @patch('mercadopago.SDK')
    def test_no_flow_hint_never_fetches_even_with_a_locally_known_payment_id(self, mock_sdk_class):
        _business, tip = self._business_with_tip(mp_payment_id='pay-200')

        # No flow=tip hint — this is exactly a pre-5B.2 Preference's webhook.
        resp = self.client.post(WEBHOOK_URL, _payment_webhook_body('pay-200'), format='json')

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')

    # Covers: (7) same, for a Billing PendingSubscriptionChange.
    @patch('mercadopago.SDK')
    def test_no_flow_hint_never_fetches_for_a_locally_known_billing_payment_id(self, mock_sdk_class):
        pending, _ref = self._pending_change(mp_payment_id='pay-billing-known')

        resp = self.client.post(WEBHOOK_URL, _payment_webhook_body('pay-billing-known'), format='json')

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'pending_payment')

    # Covers: (8) legacy ambiguo -> observable + no mutación.
    @patch('mercadopago.SDK')
    def test_no_flow_hint_is_logged_as_unresolved(self, mock_sdk_class):
        with self.assertLogs('apps.billing', level='WARNING') as captured:
            resp = self.client.post(WEBHOOK_URL, _payment_webhook_body('pay-999'), format='json')

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()
        self.assertTrue(any('LEGACY/UNRESOLVED' in message for message in captured.output))

    # Covers: (9) mp_payment_id coincidente entre un Tip y un pago Billing no
    # cambia routing — the exact scenario item 6 of the audit warns about:
    # the SAME payment_id known locally for both a Tip (via a different
    # business's MP account) and a Billing PendingSubscriptionChange (via
    # the platform's own account). Neither is fetched or mutated; the
    # collision itself proves why the old mp_payment_id-based routing was
    # unsafe as an authoritative signal.
    @patch('mercadopago.SDK')
    def test_colliding_payment_id_between_tip_and_billing_fetches_neither(self, mock_sdk_class):
        colliding_id = 'pay-collision-1'
        _business, tip = self._business_with_tip(mp_payment_id=colliding_id)
        pending, _ref = self._pending_change(mp_payment_id=colliding_id)

        resp = self.client.post(WEBHOOK_URL, _payment_webhook_body(colliding_id), format='json')

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()
        tip.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(tip.status, 'pending')
        self.assertEqual(pending.status, 'pending_payment')

    # Covers: (6) Query manipulada hacia Business B -> nunca confirma con
    # datos que en realidad no son de B. (flow=tip path, unchanged from 5B.2.1.)
    @patch('mercadopago.SDK')
    def test_hinted_ref_pointing_at_business_b_never_confirms_mismatched_payment(self, mock_sdk_class):
        _business_a, tip_a = self._business_with_tip(
            name='Negocio A', token='TOKEN-A', ref='TIP-CROSSA000000001',
        )
        _business_b, tip_b = self._business_with_tip(
            name='Negocio B', token='TOKEN-B', ref='TIP-CROSSB000000001',
        )
        # Whatever payment_id is supplied, ref=B routes to Business B's own
        # token exclusively — and the payment fetched with it doesn't
        # correspond to B's tip, so nothing is confirmed.
        mock_sdk_class.side_effect = _sdk_factory(
            forbidden_tokens=frozenset({'GLOBAL-PLATFORM-TOKEN'}),
            responses={
                'TOKEN-B': {
                    'status': 200,
                    'response': {'status': 'approved', 'external_reference': tip_a.external_reference},
                },
            },
        )

        self.client.post(
            f'{WEBHOOK_URL}?flow=tip&ref={tip_b.external_reference}',
            _payment_webhook_body('pay-cross-1'), format='json',
        )

        mock_sdk_class.assert_called_once_with('TOKEN-B')  # A's token never touched
        tip_a.refresh_from_db()
        tip_b.refresh_from_db()
        self.assertEqual(tip_a.status, 'pending')
        self.assertEqual(tip_b.status, 'pending')

    # Covers: (10) tokens no aparecen en logs, for the no-flow-hint path.
    def test_no_flow_hint_does_not_leak_tokens_in_logs(self):
        self._business_with_tip(mp_payment_id=None, token='SUPER-SECRET-TOKEN')
        with patch('mercadopago.SDK') as mock_sdk_class:
            with self.assertLogs('apps.billing', level='WARNING') as captured:
                self.client.post(WEBHOOK_URL, _payment_webhook_body('pay-log-1'), format='json')
            mock_sdk_class.assert_not_called()

        for message in captured.output:
            self.assertNotIn('SUPER-SECRET-TOKEN', message)


# Covers: (8) PublicTipVerifyView sigue pudiendo recuperar un Tip histórico
# con su Business — the recovery path 5B.2.1 defers to when a webhook can't
# auto-confirm. Unchanged code (apps.menu.views.PublicTipVerifyView), already
# resolving via the Business's own connection since Slice 5B.1; this proves
# it still closes the loop for the "unresolvable via webhook" case above.
@override_settings(MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class PublicTipVerifyRecoversHistoricTipTests(APITestCase):
    def setUp(self):
        cache.clear()

    @patch('mercadopago.SDK')
    def test_verify_confirms_historic_tip_via_business_token(self, mock_sdk_class):
        business = Business.objects.create(name='Recupera Historico', default_service='restaurante')
        MercadoPagoConnection.objects.create(
            business=business, access_token='BUSINESS-TOKEN', status='connected',
        )
        tip = TipTransaction.objects.create(
            business=business, amount='75.00', currency='ARS', status='pending',
            external_reference='TIP-RECOVERME000001',
        )
        mock_sdk_class.return_value.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'status': 'approved', 'external_reference': tip.external_reference},
        }

        resp = self.client.get(f'/api/v1/menu/public/tips/{tip.id}/verify/?payment_id=pay-recover-1')

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_called_once_with('BUSINESS-TOKEN')
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')
        self.assertEqual(tip.mp_payment_id, 'pay-recover-1')
