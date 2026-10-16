"""
Slice 5B.2.3 — full producer coverage for Billing webhook routing.

5B.2.2 made `_process_billing_payment` dispatch by the `ref` prefix
(`subscription_change_`, `addon_purchase_`, `reviews_upgrade_`) instead of
assuming every Billing ref resolves to the same kind of change. This file
adds dedicated, independent coverage for that dispatch — one producer at a
time — plus the shared `flow=billing&ref=<external_reference>` hint that
every producer's Preference carries (set once in
MercadoPagoService.create_preference, called by CommercialCheckoutView,
AddonCheckoutView and ReviewsUpgradeView with their own external_reference).

These tests exercise the webhook dispatch directly against a manually
created PendingSubscriptionChange + `flow=billing&ref=...` query string —
independent of the checkout views themselves. AddonCheckoutView's own
suite (test_v2_addon_parity.py) currently has 3 pre-existing failures from
unrelated addon/plan catalog config (not from webhook routing); out of
scope for this slice.
"""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.business.models import Business

User = get_user_model()

WEBHOOK_URL = '/api/v1/billing/mercadopago/webhook'


def _payment_webhook_body(payment_id: str) -> dict:
    return {'type': 'payment', 'data': {'id': payment_id}, 'action': 'payment.updated'}


def _make_pending(*, business=None, **extra):
    from apps.billing.models import PendingSubscriptionChange
    if business is None:
        business = Business.objects.create(name='Negocio Producer Test', default_service='gestion')
    defaults = dict(
        business=business,
        user=User.objects.create_user(username=f'user{User.objects.count()}', password='x'),
        target_plan_code='pro', billing_cycle='monthly',
        config_snapshot={}, line_items=[], total_amount=1000, requires_checkout=True,
        status='pending_payment',
    )
    defaults.update(extra)
    return PendingSubscriptionChange.objects.create(**defaults)


def _mock_approved_payment(mock_sdk_class, ref):
    mock_sdk_class.return_value.payment.return_value.get.return_value = {
        'status': 200,
        'response': {'status': 'approved', 'external_reference': ref},
    }


# ── (1) Preference hint: every producer's notification_url carries flow=billing&ref=<ref> ──

@override_settings(MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', BASE_PUBLIC_URL='https://api.example.com')
class CreatePreferenceBillingHintTests(APITestCase):
    """
    All three producers (CommercialCheckoutView, AddonCheckoutView,
    ReviewsUpgradeView) build their external_reference as
    f"{prefix}_{pending_change.id}" and pass it to the SAME
    MercadoPagoService.create_preference() — this proves that shared call
    always embeds flow=billing&ref=<external_reference> in the MP
    notification_url, whatever the prefix.
    """

    @patch('mercadopago.SDK')
    def test_notification_url_embeds_flow_and_ref_for_each_producer(self, mock_sdk_class):
        from apps.billing.mp_service import MercadoPagoService

        mock_sdk_class.return_value.preference.return_value.create.return_value = {
            'status': 201, 'response': {'id': 'pref-1', 'init_point': 'https://mp/init'},
        }
        service = MercadoPagoService()

        for external_reference in ('subscription_change_1', 'addon_purchase_2', 'reviews_upgrade_3'):
            service.create_preference(
                items=[{'title': 'x', 'quantity': 1, 'unit_price': 100, 'currency_id': 'ARS'}],
                external_reference=external_reference,
                back_urls={'success': 'https://x', 'failure': 'https://x', 'pending': 'https://x'},
            )
            sent = mock_sdk_class.return_value.preference.return_value.create.call_args.args[0]
            self.assertEqual(
                sent['notification_url'],
                f'https://api.example.com/api/v1/billing/mercadopago/webhook'
                f'?flow=billing&ref={external_reference}',
            )


# ── (2)(3)(4)(6) Dispatch: each prefix routes to its own domain handler ONLY ──

@override_settings(MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', MP_WEBHOOK_SECRET=None, DEBUG=True)
class BillingProducerDispatchTests(APITestCase):
    """
    Proves _process_billing_payment does not funnel every ref through
    PendingSubscriptionChange as if it were always a subscription_change:
    each family calls exactly one domain handler, with the platform token,
    and never touches apps.merchant_payments.
    """

    def setUp(self):
        cache.clear()

    @patch('apps.merchant_payments.services.get_merchant_payment')
    @patch('apps.billing.reviews_views.apply_reviews_plan_upgrade')
    @patch('apps.billing.services.commercial.apply.apply_addon_activation')
    @patch('apps.billing.services.commercial.apply.apply_subscription_change')
    @patch('mercadopago.SDK')
    def test_subscription_change_routes_only_to_apply_subscription_change(
        self, mock_sdk_class, mock_apply_sub, mock_apply_addon, mock_apply_reviews, mock_merchant_fetch,
    ):
        pending = _make_pending(target_plan_code='pro', billing_cycle='monthly', config_snapshot={})
        ref = f'subscription_change_{pending.id}'
        _mock_approved_payment(mock_sdk_class, ref)

        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref={ref}', _payment_webhook_body('pay-sub-1'), format='json',
        )

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_called_once_with('GLOBAL-PLATFORM-TOKEN')
        mock_apply_sub.assert_called_once_with(
            business=pending.business, target_plan_code='pro', billing_cycle='monthly', config={},
        )
        mock_apply_addon.assert_not_called()
        mock_apply_reviews.assert_not_called()
        mock_merchant_fetch.assert_not_called()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assertEqual(pending.mp_payment_id, 'pay-sub-1')

    @patch('apps.billing.reviews_views.apply_reviews_plan_upgrade')
    @patch('apps.billing.services.commercial.apply.apply_addon_activation')
    @patch('apps.billing.services.commercial.apply.apply_subscription_change')
    @patch('mercadopago.SDK')
    def test_addon_purchase_routes_only_to_apply_addon_activation(
        self, mock_sdk_class, mock_apply_sub, mock_apply_addon, mock_apply_reviews,
    ):
        pending = _make_pending(config_snapshot={'crm': True})
        ref = f'addon_purchase_{pending.id}'
        _mock_approved_payment(mock_sdk_class, ref)

        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref={ref}', _payment_webhook_body('pay-addon-1'), format='json',
        )

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_called_once_with('GLOBAL-PLATFORM-TOKEN')
        mock_apply_addon.assert_called_once_with(business=pending.business, addon_code='crm')
        mock_apply_sub.assert_not_called()
        mock_apply_reviews.assert_not_called()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assertEqual(pending.mp_payment_id, 'pay-addon-1')

    @patch('apps.billing.reviews_views.apply_reviews_plan_upgrade')
    @patch('apps.billing.services.commercial.apply.apply_addon_activation')
    @patch('apps.billing.services.commercial.apply.apply_subscription_change')
    @patch('mercadopago.SDK')
    def test_reviews_upgrade_routes_only_to_apply_reviews_plan_upgrade(
        self, mock_sdk_class, mock_apply_sub, mock_apply_addon, mock_apply_reviews,
    ):
        pending = _make_pending(target_plan_code='qr_reviews_pro')
        ref = f'reviews_upgrade_{pending.id}'
        _mock_approved_payment(mock_sdk_class, ref)

        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref={ref}', _payment_webhook_body('pay-reviews-1'), format='json',
        )

        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_called_once_with('GLOBAL-PLATFORM-TOKEN')
        mock_apply_reviews.assert_called_once_with(
            business=pending.business, target_plan_code='qr_reviews_pro',
        )
        mock_apply_sub.assert_not_called()
        mock_apply_addon.assert_not_called()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assertEqual(pending.mp_payment_id, 'pay-reviews-1')

    # Covers (5)(6): fetched external_reference must match `ref` even for the
    # addon/reviews families, not just subscription_change (already covered
    # in test_webhook_merchant_routing.py).
    @patch('apps.billing.services.commercial.apply.apply_addon_activation')
    @patch('mercadopago.SDK')
    def test_addon_purchase_ref_mismatch_never_confirms(self, mock_sdk_class, mock_apply_addon):
        pending = _make_pending(config_snapshot={'crm': True})
        other = _make_pending(config_snapshot={'invoicing_module': True})
        ref = f'addon_purchase_{pending.id}'
        other_ref = f'addon_purchase_{other.id}'
        _mock_approved_payment(mock_sdk_class, other_ref)

        self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref={ref}', _payment_webhook_body('pay-addon-mismatch'), format='json',
        )

        mock_apply_addon.assert_not_called()
        pending.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(pending.status, 'pending_payment')
        self.assertIsNone(pending.mp_payment_id)
        self.assertEqual(other.status, 'pending_payment')
        self.assertIsNone(other.mp_payment_id)

    @patch('apps.billing.reviews_views.apply_reviews_plan_upgrade')
    @patch('mercadopago.SDK')
    def test_reviews_upgrade_ref_mismatch_never_confirms(self, mock_sdk_class, mock_apply_reviews):
        pending = _make_pending(target_plan_code='qr_reviews_pro')
        other = _make_pending(target_plan_code='qr_reviews_pro')
        ref = f'reviews_upgrade_{pending.id}'
        other_ref = f'reviews_upgrade_{other.id}'
        _mock_approved_payment(mock_sdk_class, other_ref)

        self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref={ref}', _payment_webhook_body('pay-reviews-mismatch'), format='json',
        )

        mock_apply_reviews.assert_not_called()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'pending_payment')
        self.assertIsNone(pending.mp_payment_id)


# ── (7) Invalid / manipulated ref per family never fetches or mutates ──

@override_settings(MP_ACCESS_TOKEN='GLOBAL-PLATFORM-TOKEN', MP_WEBHOOK_SECRET=None, DEBUG=True)
class BillingProducerInvalidRefTests(APITestCase):

    def setUp(self):
        cache.clear()

    @patch('mercadopago.SDK')
    def test_unrecognized_prefix_no_fetch(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref=unknown_family_1',
            _payment_webhook_body('pay-bad-prefix'), format='json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()

    @patch('mercadopago.SDK')
    def test_addon_purchase_unknown_id_no_fetch_no_mutation(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref=addon_purchase_999999999',
            _payment_webhook_body('pay-addon-unknown'), format='json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()

    @patch('mercadopago.SDK')
    def test_addon_purchase_malformed_id_no_fetch(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref=addon_purchase_not-a-number',
            _payment_webhook_body('pay-addon-malformed'), format='json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()

    @patch('mercadopago.SDK')
    def test_reviews_upgrade_unknown_id_no_fetch_no_mutation(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref=reviews_upgrade_999999999',
            _payment_webhook_body('pay-reviews-unknown'), format='json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()

    @patch('mercadopago.SDK')
    def test_reviews_upgrade_malformed_id_no_fetch(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref=reviews_upgrade_not-a-number',
            _payment_webhook_body('pay-reviews-malformed'), format='json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()

    @patch('mercadopago.SDK')
    def test_subscription_change_malformed_id_no_fetch(self, mock_sdk_class):
        resp = self.client.post(
            f'{WEBHOOK_URL}?flow=billing&ref=subscription_change_not-a-number',
            _payment_webhook_body('pay-sub-malformed'), format='json',
        )
        self.assertEqual(resp.status_code, 200)
        mock_sdk_class.assert_not_called()
