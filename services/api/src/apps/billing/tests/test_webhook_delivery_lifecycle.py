"""
Slice 5B.4 — webhook reliability: persistence, retry, dead-letter, idempotency.

Every Mercado Pago webhook (payment included) is persisted as a
WebhookDelivery and processed through apps.billing.webhook_lifecycle:

    RECEIVED → PROCESSING → PROCESSED | IGNORED | FAILED → … → DEAD_LETTER

These tests run against the project's PostgreSQL database (settings
DATABASES) — the concurrency tests rely on real row locks
(`select_for_update(skip_locked=True)`), which SQLite cannot provide.
"""
from __future__ import annotations

import threading
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.billing.models import WebhookDelivery
from apps.billing.webhook_lifecycle import (
    WebhookOutcome,
    claim_delivery,
    compute_next_retry_at,
    eligible_for_retry_qs,
    process_delivery,
    retry_due_deliveries,
    sanitize_error,
)
from apps.business.models import Business
from apps.menu.models import TipTransaction
from apps.merchant_payments.models import MercadoPagoConnection

User = get_user_model()
S = WebhookDelivery.ProcessingStatus

WEBHOOK_URL = '/api/v1/billing/mercadopago/webhook'
TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='
GLOBAL_TOKEN = 'GLOBAL-PLATFORM-TOKEN'
BUSINESS_TOKEN = 'BUSINESS-TOKEN'

BASE_SETTINGS = dict(
    MP_ACCESS_TOKEN=GLOBAL_TOKEN, MP_WEBHOOK_SECRET=None, DEBUG=True,
    MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    MP_WEBHOOK_RETRY_MAX_ATTEMPTS=3,
    MP_WEBHOOK_RETRY_BASE_SECONDS=300,
    MP_WEBHOOK_RETRY_MAX_BACKOFF_SECONDS=6 * 3600,
    MP_WEBHOOK_PROCESSING_LEASE_SECONDS=900,
)


def _body(payment_id: str, topic: str = 'payment') -> dict:
    return {'type': topic, 'data': {'id': payment_id}, 'action': f'{topic}.updated'}


def _sdk_factory(*, forbidden=frozenset(), responses=None, calls=None):
    """mercadopago.SDK side_effect: records tokens, fails loudly on forbidden ones.

    ``responses`` maps token → payment().get() return value, or → an
    Exception instance to raise from get().
    """
    responses = responses or {}

    def factory(token, *args, **kwargs):
        if calls is not None:
            calls.append(token)
        if token in forbidden:
            raise AssertionError(f'mercadopago.SDK must never be built with {token!r} here')
        instance = MagicMock()
        resp = responses.get(token, {'status': 404, 'response': {}})
        if isinstance(resp, Exception):
            instance.payment.return_value.get.side_effect = resp
        else:
            instance.payment.return_value.get.return_value = resp
        return instance

    return factory


def _approved(ref):
    return {'status': 200, 'response': {'status': 'approved', 'external_reference': ref}}


def _make_due(delivery: WebhookDelivery) -> None:
    WebhookDelivery.objects.filter(pk=delivery.pk).update(
        next_retry_at=timezone.now() - timedelta(seconds=1),
    )


def _make_pending(**extra):
    from apps.billing.models import PendingSubscriptionChange
    business = Business.objects.create(name='Negocio Billing', default_service='gestion')
    defaults = dict(
        business=business,
        user=User.objects.create_user(username=f'u{User.objects.count()}', password='x'),
        target_plan_code='pro', billing_cycle='monthly',
        config_snapshot={}, line_items=[], total_amount=1000, requires_checkout=True,
        status='pending_payment',
    )
    defaults.update(extra)
    return PendingSubscriptionChange.objects.create(**defaults)


class _Base(APITestCase):
    def setUp(self):
        cache.clear()
        self._req = 0

    def _post(self, query: str, body: dict, *, request_id: str | None = None, **headers):
        self._req += 1
        return self.client.post(
            f'{WEBHOOK_URL}?{query}' if query else WEBHOOK_URL, body, format='json',
            HTTP_X_REQUEST_ID=request_id or f'req-{self._req}-{self.id()[-20:]}', **headers,
        )

    def _latest(self) -> WebhookDelivery:
        return WebhookDelivery.objects.order_by('-created_at').first()

    def _tip(self, *, ref='TIP-LIFECYCLE0000001', connected=True, conn_status='connected'):
        business = Business.objects.create(name='Resto', default_service='restaurante')
        if connected:
            MercadoPagoConnection.objects.create(
                business=business, access_token=BUSINESS_TOKEN, status=conn_status,
            )
        tip = TipTransaction.objects.create(
            business=business, amount='100.00', currency='ARS', status='pending',
            external_reference=ref,
        )
        return business, tip


# ─────────────────────────────────────────────────────────────────────────────
# (1)(2)(3)(4)(5)(6)(7)(8)(11) payment lifecycle end-to-end
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**BASE_SETTINGS)
class PaymentDeliveryLifecycleTests(_Base):

    @patch('mercadopago.SDK')
    def test_valid_payment_webhook_is_persisted_with_replay_metadata(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: _approved(tip.external_reference)},
        )
        resp = self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-1'),
                          HTTP_X_SIGNATURE='ts=1,v1=abc')

        self.assertEqual(resp.status_code, 200)
        d = self._latest()
        self.assertEqual((d.topic, d.resource_id, d.flow, d.ref),
                         ('payment', 'pay-1', 'tip', tip.external_reference))
        self.assertTrue(d.signature_valid)
        # (2) success → PROCESSED
        self.assertEqual(d.processing_status, S.PROCESSED)
        self.assertEqual(d.attempts, 1)
        self.assertIsNone(d.next_retry_at)
        self.assertEqual(d.error_category, '')
        # The raw signature is not persisted (not needed for replay).
        self.assertEqual(d.x_signature, '')
        self.assertNotIn('x-signature', d.headers_json)

    @patch('mercadopago.SDK')
    def test_transient_error_marks_failed_schedules_retry_and_acks_200(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: {'status': 500, 'response': {}}},
        )
        before = timezone.now()
        resp = self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-2'))

        # (11) persisted + transient failure → 2xx: MiRubro owns the retry.
        self.assertEqual(resp.status_code, 200)
        d = self._latest()
        self.assertEqual(d.processing_status, S.FAILED)            # (3)
        self.assertEqual(d.attempts, 1)                            # (4)
        self.assertEqual(d.error_category, 'provider_fetch_failed')
        # (5) next_retry_at = now + base * 2**0
        self.assertIsNotNone(d.next_retry_at)
        delta = (d.next_retry_at - before).total_seconds()
        self.assertTrue(299 <= delta <= 310, delta)
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')

    @patch('mercadopago.SDK')
    def test_retry_after_timeout_succeeds_and_is_processed(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: TimeoutError('read timed out')},
        )
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-3'))
        d = self._latest()
        self.assertEqual(d.processing_status, S.FAILED)

        # Not due yet → the sweeper does not touch it.
        self.assertEqual(retry_due_deliveries()['picked'], 0)

        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: _approved(tip.external_reference)},
        )
        _make_due(d)
        counts = retry_due_deliveries()

        self.assertEqual(counts['picked'], 1)
        d.refresh_from_db()
        self.assertEqual(d.processing_status, S.PROCESSED)         # (6)
        self.assertEqual(d.attempts, 2)
        self.assertEqual(d.error_message, '')
        self.assertEqual(d.error_category, '')
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')
        self.assertEqual(tip.mp_payment_id, 'pay-3')

    @patch('mercadopago.SDK')
    def test_repeated_failures_reach_dead_letter_which_is_never_auto_retried(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: {'status': 503, 'response': {}}},
        )
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-4'))
        d = self._latest()

        for expected_attempts in (2, 3):
            _make_due(d)
            retry_due_deliveries()
            d.refresh_from_db()
            self.assertEqual(d.attempts, expected_attempts)
            if expected_attempts < 3:
                self.assertEqual(d.processing_status, S.FAILED)
                # Exponential: second backoff = base * 2.
                delta = (d.next_retry_at - d.last_attempt_at).total_seconds()
                self.assertTrue(599 <= delta <= 610, delta)

        # (7) MAX_ATTEMPTS=3 reached → DEAD_LETTER
        self.assertEqual(d.processing_status, S.DEAD_LETTER)
        self.assertIsNone(d.next_retry_at)

        # (8) never retried automatically, even if next_retry_at looked due.
        WebhookDelivery.objects.filter(pk=d.pk).update(next_retry_at=timezone.now() - timedelta(hours=1))
        self.assertFalse(eligible_for_retry_qs().filter(pk=d.pk).exists())
        self.assertEqual(retry_due_deliveries()['picked'], 0)
        self.assertIsNone(process_delivery(d.pk))
        d.refresh_from_db()
        self.assertEqual((d.processing_status, d.attempts), (S.DEAD_LETTER, 3))

    def test_backoff_is_exponential_and_capped(self):
        now = timezone.now()
        delays = [(compute_next_retry_at(n, now) - now).total_seconds() for n in (1, 2, 3, 10)]
        self.assertEqual(delays[:3], [300, 600, 1200])
        self.assertEqual(delays[3], 6 * 3600)


# ─────────────────────────────────────────────────────────────────────────────
# (9)(10)(12)(18) HTTP semantics and non-retryable outcomes
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**BASE_SETTINGS)
class ReceptionSemanticsTests(_Base):

    def test_persistence_failure_returns_503_and_nothing_is_acked(self):
        with patch.object(WebhookDelivery.objects, 'create', side_effect=DatabaseError('db down')):
            resp = self._post('flow=tip&ref=TIP-X', _body('pay-10'))
        # (10) lost before persisting → 5xx so Mercado Pago retries.
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(WebhookDelivery.objects.count(), 0)

    @override_settings(MP_WEBHOOK_SECRET='webhook-secret-value', DEBUG=False)
    @patch('mercadopago.SDK')
    def test_invalid_signature_is_rejected_and_never_processed(self, mock_sdk):
        _, tip = self._tip()
        resp = self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-12'),
                          HTTP_X_SIGNATURE='ts=1713300000,v1=deadbeef')

        self.assertEqual(resp.status_code, 400)                    # (12) unchanged
        mock_sdk.assert_not_called()
        d = self._latest()
        self.assertEqual((d.processing_status, d.error_category), (S.IGNORED, 'invalid_signature'))
        self.assertEqual(d.attempts, 0)
        self.assertFalse(eligible_for_retry_qs().filter(pk=d.pk).exists())
        self.assertIsNone(process_delivery(d.pk))
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')

    @patch('mercadopago.SDK')
    def test_legacy_unresolved_is_ignored_and_never_looped(self, mock_sdk):
        resp = self._post('', _body('pay-legacy'))

        self.assertEqual(resp.status_code, 200)
        mock_sdk.assert_not_called()                               # no classification fetch
        d = self._latest()
        # (18) + (9) IGNORED is terminal: not eligible, not re-claimable.
        self.assertEqual((d.processing_status, d.error_category), (S.IGNORED, 'legacy_unresolved'))
        self.assertIsNone(d.next_retry_at)
        WebhookDelivery.objects.filter(pk=d.pk).update(next_retry_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(retry_due_deliveries()['picked'], 0)
        self.assertIsNone(process_delivery(d.pk))
        d.refresh_from_db()
        self.assertEqual(d.attempts, 1)

    @patch('mercadopago.SDK')
    def test_merchant_ref_mismatch_is_ignored_not_retried(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: _approved('TIP-SOMEONEELSE')},
        )
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-mm'))
        d = self._latest()
        self.assertEqual((d.processing_status, d.error_category), (S.IGNORED, 'merchant_ref_mismatch'))
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')

    @patch('apps.billing.mp_service.MercadoPagoService.get_preapproval', return_value=None)
    def test_subscription_topic_fetch_failure_is_retryable(self, _mock_get):
        resp = self._post('', _body('preapp-1', topic='subscription_preapproval'))
        self.assertEqual(resp.status_code, 200)
        d = self._latest()
        self.assertEqual((d.processing_status, d.error_category), (S.FAILED, 'provider_fetch_failed'))
        self.assertIsNotNone(d.next_retry_at)

    def test_unsupported_topic_is_ignored(self):
        self._post('', _body('x-1', topic='merchant_order'))
        d = self._latest()
        self.assertEqual((d.processing_status, d.error_category), (S.IGNORED, 'unsupported_topic'))

    @patch('mercadopago.SDK')
    def test_same_request_id_is_duplicated_and_not_reprocessed(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: _approved(tip.external_reference)},
        )
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-dup'), request_id='same-req')
        resp = self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-dup'), request_id='same-req')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_sdk.call_count, 1)
        self.assertEqual(self._latest().processing_status, S.DUPLICATED)


# ─────────────────────────────────────────────────────────────────────────────
# (13)(14)(15) replay routing — exactly the 5B.2 credentials
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**BASE_SETTINGS)
class ReplayRoutingTests(_Base):

    @patch('apps.merchant_payments.services.get_merchant_payment')
    @patch('apps.billing.services.commercial.apply.apply_subscription_change')
    @patch('mercadopago.SDK')
    def test_billing_replay_uses_platform_token_only(self, mock_sdk, mock_apply, mock_merchant):
        pending = _make_pending()
        ref = f'subscription_change_{pending.id}'
        mock_sdk.side_effect = _sdk_factory(
            forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: ConnectionError('reset')},
        )
        self._post(f'flow=billing&ref={ref}', _body('bill-13'))
        d = self._latest()
        self.assertEqual(d.processing_status, S.FAILED)

        calls = []
        mock_sdk.side_effect = _sdk_factory(
            forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: _approved(ref)}, calls=calls,
        )
        _make_due(d)
        retry_due_deliveries()

        d.refresh_from_db()
        self.assertEqual(d.processing_status, S.PROCESSED)
        self.assertEqual(set(calls), {GLOBAL_TOKEN})               # (13)
        mock_merchant.assert_not_called()
        mock_apply.assert_called_once()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')

    @patch('mercadopago.SDK')
    def test_tip_replay_uses_business_token_only(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: {'status': 502, 'response': {}}},
        )
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-14'))
        d = self._latest()

        calls = []
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN},
            responses={BUSINESS_TOKEN: _approved(tip.external_reference)}, calls=calls,
        )
        _make_due(d)
        retry_due_deliveries()

        d.refresh_from_db()
        self.assertEqual(d.processing_status, S.PROCESSED)
        self.assertEqual(calls, [BUSINESS_TOKEN])                  # (14)
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')

    @patch('mercadopago.SDK')
    def test_merchant_reauth_required_dead_letters_at_once_and_never_uses_global_token(self, mock_sdk):
        business, tip = self._tip(conn_status='error')   # needs reauthorization
        calls = []
        mock_sdk.side_effect = _sdk_factory(forbidden={GLOBAL_TOKEN}, calls=calls)

        resp = self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-15'))
        self.assertEqual(resp.status_code, 200)
        d = self._latest()
        # Permanent until the owner reconnects: no 8x retry loop, straight to DEAD_LETTER.
        self.assertEqual(
            (d.processing_status, d.error_category, d.attempts),
            (S.DEAD_LETTER, 'merchant_reauth_required', 1),
        )
        self.assertIsNone(d.next_retry_at)
        self.assertEqual(retry_due_deliveries()['picked'], 0)
        self.assertEqual(calls, [])                                 # (15) no SDK at all
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')

        # Owner reconnects -> operator revives -> Business token only.
        MercadoPagoConnection.objects.filter(business=business).update(status='connected')
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN},
            responses={BUSINESS_TOKEN: _approved(tip.external_reference)}, calls=calls,
        )
        call_command('retry_mp_webhooks', '--id', str(d.pk), '--revive-dead-letter', stdout=StringIO())
        d.refresh_from_db()
        self.assertEqual((d.processing_status, d.attempts), (S.PROCESSED, 2))
        self.assertEqual(calls, [BUSINESS_TOKEN])
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')

    @patch('apps.billing.mp_service.MercadoPagoService.get_authorized_payment')
    def test_provider_id_mismatch_is_permanent_dead_letter(self, mock_get):
        mock_get.return_value = {'id': 'OTHER-ID', 'status': 'authorized', 'preapproval_id': 'p-1'}
        self._post('', _body('ap-1', topic='subscription_authorized_payment'))
        d = self._latest()
        self.assertEqual(
            (d.processing_status, d.error_category, d.attempts),
            (S.DEAD_LETTER, 'provider_id_mismatch', 1),
        )
        self.assertEqual(retry_due_deliveries()['picked'], 0)

    @patch('mercadopago.SDK')
    def test_network_timeout_and_5xx_are_transient(self, mock_sdk):
        pending = _make_pending()
        ref = f'subscription_change_{pending.id}'
        for i, resp in enumerate((TimeoutError('timed out'), ConnectionError('reset'),
                                  {'status': 500, 'response': {}}, {'status': 503, 'response': {}})):
            mock_sdk.side_effect = _sdk_factory(forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: resp})
            self._post(f'flow=billing&ref={ref}', _body(f'bill-t{i}'))
            d = self._latest()
            self.assertEqual((d.processing_status, d.error_category), (S.FAILED, 'provider_fetch_failed'))

    @patch('mercadopago.SDK')
    def test_invalid_refs_are_ignored_without_fetch(self, mock_sdk):
        for query in ('flow=billing&ref=unknown_prefix_1', 'flow=billing&ref=subscription_change_999999',
                      'flow=tip&ref=TIP-DOESNOTEXIST', 'flow=tip', 'flow=billing'):
            self._post(query, _body('pay-invalid'))
            self.assertEqual(self._latest().processing_status, S.IGNORED, query)
        mock_sdk.assert_not_called()

    @patch('apps.merchant_payments.services.refresh_merchant_connection')
    @patch('mercadopago.SDK')
    def test_temporary_refresh_failure_is_retryable(self, mock_sdk, mock_refresh):
        from apps.merchant_payments.services import MerchantPaymentConnectionUnavailable
        business, tip = self._tip()
        MercadoPagoConnection.objects.filter(business=business).update(
            token_expires_at=timezone.now() - timedelta(minutes=1),
        )
        mock_refresh.side_effect = MerchantPaymentConnectionUnavailable(
            business.id, 'refresh_temporarily_unavailable',
        )
        mock_sdk.side_effect = _sdk_factory(forbidden={GLOBAL_TOKEN})
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-rf'))
        d = self._latest()
        self.assertEqual((d.processing_status, d.error_category), (S.FAILED, 'merchant_refresh_temporary'))


# ─────────────────────────────────────────────────────────────────────────────
# (16)(17) idempotency of repeated processing
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**BASE_SETTINGS)
class IdempotencyTests(_Base):

    @patch('mercadopago.SDK')
    def test_duplicated_tip_notification_does_not_duplicate_effects(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: _approved(tip.external_reference)},
        )
        # Two distinct notifications for the same payment (e.g. created + updated).
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-16'))
        tip.refresh_from_db()
        first_updated = tip.updated_at
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-16'))

        self.assertEqual(
            sorted(WebhookDelivery.objects.values_list('processing_status', flat=True)),
            [S.PROCESSED, S.PROCESSED],
        )
        self.assertEqual(TipTransaction.objects.count(), 1)       # (16) no new TipTransaction
        tip.refresh_from_db()
        self.assertEqual((tip.status, tip.mp_payment_id), ('approved', 'pay-16'))
        self.assertGreaterEqual(tip.updated_at, first_updated)

    @patch('mercadopago.SDK')
    def test_tip_already_processed_then_replayed_is_a_no_op(self, mock_sdk):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: _approved(tip.external_reference)},
        )
        self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-16b'))
        d = self._latest()
        # A FAILED replay of an already-applied Tip (e.g. the ack was lost).
        WebhookDelivery.objects.filter(pk=d.pk).update(processing_status=S.FAILED)
        self.assertEqual(process_delivery(d.pk), S.PROCESSED)
        self.assertEqual(TipTransaction.objects.count(), 1)
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')

    @patch('apps.billing.services.commercial.apply.apply_subscription_change')
    @patch('mercadopago.SDK')
    def test_duplicated_billing_notification_applies_change_once(self, mock_sdk, mock_apply):
        from apps.billing.models import PaymentAttempt
        pending = _make_pending()
        ref = f'subscription_change_{pending.id}'
        mock_sdk.side_effect = _sdk_factory(forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: _approved(ref)})

        self._post(f'flow=billing&ref={ref}', _body('bill-17'))
        self._post(f'flow=billing&ref={ref}', _body('bill-17'))
        # And an explicit replay of the first delivery.
        first = WebhookDelivery.objects.order_by('created_at').first()
        WebhookDelivery.objects.filter(pk=first.pk).update(processing_status=S.FAILED)
        self.assertEqual(process_delivery(first.pk), S.PROCESSED)

        mock_apply.assert_called_once()                            # (17)
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assertLessEqual(PaymentAttempt.objects.filter(external_payment_id='bill-17').count(), 1)

    @patch('apps.billing.services.commercial.apply.apply_addon_activation')
    @patch('mercadopago.SDK')
    def test_addon_purchase_replay_activates_once(self, mock_sdk, mock_addon):
        pending = _make_pending(config_snapshot={'crm': True})
        ref = f'addon_purchase_{pending.id}'
        mock_sdk.side_effect = _sdk_factory(forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: _approved(ref)})
        self._post(f'flow=billing&ref={ref}', _body('addon-1'))
        d = self._latest()
        self._post(f'flow=billing&ref={ref}', _body('addon-1'))
        WebhookDelivery.objects.filter(pk=d.pk).update(processing_status=S.FAILED)
        self.assertEqual(process_delivery(d.pk), S.PROCESSED)

        mock_addon.assert_called_once()
        self.assertEqual(mock_addon.call_args.kwargs['addon_code'], 'crm')
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')

    @patch('apps.billing.reviews_views.apply_reviews_plan_upgrade')
    @patch('mercadopago.SDK')
    def test_reviews_upgrade_replay_applies_once(self, mock_sdk, mock_upgrade):
        pending = _make_pending(target_plan_code='qr_reviews_pro')
        ref = f'reviews_upgrade_{pending.id}'
        mock_sdk.side_effect = _sdk_factory(forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: _approved(ref)})
        self._post(f'flow=billing&ref={ref}', _body('rev-1'))
        d = self._latest()
        self._post(f'flow=billing&ref={ref}', _body('rev-1'))
        WebhookDelivery.objects.filter(pk=d.pk).update(processing_status=S.FAILED)
        self.assertEqual(process_delivery(d.pk), S.PROCESSED)

        mock_upgrade.assert_called_once()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')

    @patch('apps.billing.services.commercial.apply.apply_subscription_change')
    @patch('mercadopago.SDK')
    def test_rejected_notification_after_completion_does_not_revert(self, mock_sdk, mock_apply):
        pending = _make_pending()
        ref = f'subscription_change_{pending.id}'
        mock_sdk.side_effect = _sdk_factory(forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: _approved(ref)})
        self._post(f'flow=billing&ref={ref}', _body('bill-rev'))
        mock_sdk.side_effect = _sdk_factory(forbidden={BUSINESS_TOKEN}, responses={
            GLOBAL_TOKEN: {'status': 200, 'response': {'status': 'rejected', 'external_reference': ref}},
        })
        self._post(f'flow=billing&ref={ref}', _body('bill-rev'))
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        mock_apply.assert_called_once()

    @patch('apps.billing.services.commercial.apply.apply_subscription_change')
    @patch('mercadopago.SDK')
    def test_billing_apply_failure_is_retried_and_then_applied_once(self, mock_sdk, mock_apply):
        pending = _make_pending()
        ref = f'subscription_change_{pending.id}'
        mock_sdk.side_effect = _sdk_factory(forbidden={BUSINESS_TOKEN}, responses={GLOBAL_TOKEN: _approved(ref)})
        mock_apply.side_effect = [RuntimeError('deadlock detected'), None]

        self._post(f'flow=billing&ref={ref}', _body('bill-apply'))
        d = self._latest()
        self.assertEqual((d.processing_status, d.error_category), (S.FAILED, 'billing_apply_failed'))
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'failed')

        _make_due(d)
        retry_due_deliveries()
        d.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(d.processing_status, S.PROCESSED)
        self.assertEqual(pending.status, 'completed')
        self.assertEqual(mock_apply.call_count, 2)


# ─────────────────────────────────────────────────────────────────────────────
# (19) no secrets in error_message / logs
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**BASE_SETTINGS)
class SanitizationTests(_Base):

    @patch('apps.billing.payment_webhook.process_tip_payment')
    @patch('mercadopago.SDK')
    def test_error_and_logs_never_contain_tokens(self, mock_sdk, mock_process_tip):
        _, tip = self._tip()
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, responses={BUSINESS_TOKEN: _approved(tip.external_reference)},
        )
        leaky = (
            f'boom APP_USR-1234567890-abcdef token={GLOBAL_TOKEN} '
            'access_token=super-secret-access refresh_token: "super-secret-refresh" '
            'Authorization: Bearer abc.def.ghi'
        )
        mock_process_tip.side_effect = RuntimeError(leaky)

        with self.assertLogs('apps.billing', level='DEBUG') as logs:
            self._post(f'flow=tip&ref={tip.external_reference}', _body('pay-19'))

        d = self._latest()
        self.assertEqual((d.processing_status, d.error_category), (S.FAILED, 'internal_error'))
        haystacks = [d.error_message, '\n'.join(logs.output)]
        for secret in ('APP_USR-1234567890-abcdef', GLOBAL_TOKEN, 'super-secret-access',
                       'super-secret-refresh', 'abc.def.ghi', TEST_ENCRYPTION_KEY):
            for hay in haystacks:
                self.assertNotIn(secret, hay)
        self.assertIn('[REDACTED]', d.error_message)

    def test_sanitize_truncates(self):
        self.assertLessEqual(len(sanitize_error('x' * 5000)), 500)


# ─────────────────────────────────────────────────────────────────────────────
# (20) task / command only take eligible deliveries
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**BASE_SETTINGS)
class EligibilityTests(TestCase):

    def _row(self, status, **extra):
        now = timezone.now()
        defaults = dict(
            topic='payment', resource_id='r', signature_valid=True,
            processing_status=status, received_at=now,
        )
        defaults.update(extra)
        return WebhookDelivery.objects.create(**defaults)

    def setUp(self):
        now = timezone.now()
        old = now - timedelta(hours=1)
        self.eligible = {
            self._row(S.FAILED, attempts=1, next_retry_at=now - timedelta(seconds=5)).pk,
            self._row(S.PROCESSING, attempts=1, last_attempt_at=old).pk,         # crashed worker
            self._row(S.RECEIVED, received_at=old).pk,                            # never claimed
        }
        self.not_eligible = {
            self._row(S.FAILED, attempts=1, next_retry_at=now + timedelta(minutes=5)).pk,
            self._row(S.FAILED, attempts=3, next_retry_at=now - timedelta(seconds=5)).pk,
            self._row(S.DEAD_LETTER, attempts=3).pk,
            self._row(S.IGNORED).pk,
            self._row(S.PROCESSED, attempts=1).pk,
            self._row(S.DUPLICATED).pk,
            self._row(S.PROCESSING, attempts=1, last_attempt_at=now).pk,         # in flight
            self._row(S.RECEIVED).pk,                                             # inline owns it
            self._row(S.RECEIVED, received_at=old, signature_valid=False).pk,
        }

    def test_eligible_queryset(self):
        self.assertEqual(set(eligible_for_retry_qs().values_list('pk', flat=True)), self.eligible)

    def test_task_processes_only_eligible(self):
        from apps.billing.tasks import retry_failed_webhooks
        seen = []
        with patch('apps.billing.webhook_lifecycle.process_delivery',
                   side_effect=lambda pk, **kw: seen.append(pk) or S.PROCESSED):
            result = retry_failed_webhooks()
        self.assertEqual(set(seen), self.eligible)
        self.assertEqual(result['picked'], 3)

    def test_command_sweep_and_dry_run(self):
        out = StringIO()
        call_command('retry_mp_webhooks', '--dry-run', stdout=out)
        self.assertIn('3 eligible', out.getvalue())
        seen = []
        with patch('apps.billing.webhook_lifecycle.process_delivery',
                   side_effect=lambda pk, **kw: seen.append(pk) or S.PROCESSED):
            call_command('retry_mp_webhooks', stdout=StringIO())
        self.assertEqual(set(seen), self.eligible)

    def test_command_refuses_terminal_and_dead_letter_without_flag(self):
        processed = WebhookDelivery.objects.filter(processing_status=S.PROCESSED).first()
        ignored = WebhookDelivery.objects.filter(processing_status=S.IGNORED).first()
        dead = WebhookDelivery.objects.filter(processing_status=S.DEAD_LETTER).first()
        for row in (processed, ignored, dead):
            with self.assertRaises(CommandError):
                call_command('retry_mp_webhooks', '--id', str(row.pk), stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('retry_mp_webhooks', '--revive-dead-letter', stdout=StringIO())

    def _snapshot(self):
        return sorted(WebhookDelivery.objects.values_list(
            'pk', 'processing_status', 'attempts', 'next_retry_at', 'last_attempt_at', 'error_message',
        ))

    def test_dry_run_does_not_mutate(self):
        before = self._snapshot()
        call_command('retry_mp_webhooks', '--dry-run', stdout=StringIO())
        for row in WebhookDelivery.objects.exclude(
                processing_status__in=[S.PROCESSED, S.IGNORED, S.DUPLICATED, S.DEAD_LETTER]):
            call_command('retry_mp_webhooks', '--id', str(row.pk), '--dry-run', stdout=StringIO())
        self.assertEqual(self._snapshot(), before)

    @patch('apps.billing.webhook_processor.execute_delivery', return_value=WebhookOutcome.processed())
    def test_command_id_touches_only_that_delivery(self, mock_exec):
        target = WebhookDelivery.objects.filter(
            processing_status=S.FAILED, next_retry_at__gt=timezone.now()).first()   # not yet due
        before = [r for r in self._snapshot() if r[0] != target.pk]
        call_command('retry_mp_webhooks', '--id', str(target.pk), stdout=StringIO())
        target.refresh_from_db()
        self.assertEqual(target.processing_status, S.PROCESSED)   # --id ignores next_retry_at
        self.assertEqual(mock_exec.call_count, 1)
        self.assertEqual([r for r in self._snapshot() if r[0] != target.pk], before)

    def test_fresh_processing_lease_cannot_be_claimed_expired_one_can(self):
        fresh = self._row(S.PROCESSING, attempts=1, last_attempt_at=timezone.now() - timedelta(seconds=60))
        self.assertIsNone(claim_delivery(fresh.pk))
        fresh.refresh_from_db()
        self.assertEqual((fresh.processing_status, fresh.attempts), (S.PROCESSING, 1))

        expired = self._row(S.PROCESSING, attempts=1, last_attempt_at=timezone.now() - timedelta(seconds=901))
        claimed = claim_delivery(expired.pk)
        self.assertIsNotNone(claimed)
        self.assertEqual((claimed.processing_status, claimed.attempts), (S.PROCESSING, 2))

    @patch('apps.billing.webhook_processor.execute_delivery', return_value=WebhookOutcome.processed())
    def test_command_revives_dead_letter_explicitly(self, _mock_exec):
        dead = WebhookDelivery.objects.filter(processing_status=S.DEAD_LETTER).first()
        call_command('retry_mp_webhooks', '--id', str(dead.pk), '--revive-dead-letter', stdout=StringIO())
        dead.refresh_from_db()
        self.assertEqual((dead.processing_status, dead.attempts), (S.PROCESSED, 4))

    def test_stale_processing_on_final_attempt_goes_dead_letter(self):
        row = self._row(S.PROCESSING, attempts=3, last_attempt_at=timezone.now() - timedelta(hours=1))
        self.assertIsNone(claim_delivery(row.pk))
        row.refresh_from_db()
        self.assertEqual((row.processing_status, row.error_category), (S.DEAD_LETTER, 'lease_expired'))


# ─────────────────────────────────────────────────────────────────────────────
# (21) two workers never process the same delivery at once (real PG locks)
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**BASE_SETTINGS)
class ConcurrentWorkerTests(TransactionTestCase):
    # Declaring available_apps makes the post-test flush use TRUNCATE ... CASCADE
    # (a pre-existing FK from treasury_* to business_business otherwise
    # breaks the plain flush on PostgreSQL).
    available_apps = list(settings.INSTALLED_APPS)

    def _delivery(self, status=S.FAILED):
        return WebhookDelivery.objects.create(
            topic='payment', resource_id='conc', signature_valid=True, attempts=1,
            processing_status=status, received_at=timezone.now(),
            next_retry_at=timezone.now() - timedelta(seconds=1),
        )

    def test_locked_row_is_skipped_not_waited_on(self):
        self.assertEqual(connection.vendor, 'postgresql')
        d = self._delivery()
        locked, release = threading.Event(), threading.Event()

        def holder():
            try:
                with transaction.atomic():
                    WebhookDelivery.objects.select_for_update().get(pk=d.pk)
                    locked.set()
                    release.wait(10)
            finally:
                connection.close()

        t = threading.Thread(target=holder)
        t.start()
        try:
            self.assertTrue(locked.wait(10))
            self.assertIsNone(claim_delivery(d.pk))                # skip_locked → no wait, no claim
        finally:
            release.set()
            t.join(10)
        claimed = claim_delivery(d.pk)
        self.assertIsNotNone(claimed)
        self.assertEqual((claimed.processing_status, claimed.attempts), (S.PROCESSING, 2))

    def test_two_workers_process_one_delivery_exactly_once(self):
        d = self._delivery()
        started = threading.Event()
        proceed = threading.Event()
        executions = []

        def slow_execute(delivery):
            executions.append(delivery.pk)
            started.set()
            proceed.wait(10)
            return WebhookOutcome.processed()

        results = {}

        def worker(name):
            try:
                results[name] = process_delivery(d.pk)
            finally:
                connection.close()

        with patch('apps.billing.webhook_processor.execute_delivery', side_effect=slow_execute):
            t1 = threading.Thread(target=worker, args=('w1',))
            t1.start()
            self.assertTrue(started.wait(10))                      # w1 holds the lease
            t2 = threading.Thread(target=worker, args=('w2',))
            t2.start()
            t2.join(10)                                            # w2 returns immediately
            proceed.set()
            t1.join(10)

        self.assertEqual(len(executions), 1)
        self.assertEqual(results, {'w1': S.PROCESSED, 'w2': None})
        d.refresh_from_db()
        self.assertEqual((d.processing_status, d.attempts), (S.PROCESSED, 2))

    def test_slow_worker_whose_lease_expired_cannot_overwrite_the_recovering_worker(self):
        """Real race: worker A is still running when its lease expires; B
        reclaims and finishes; A's late result must be discarded."""
        d = self._delivery()
        a_inside, a_release = threading.Event(), threading.Event()
        results = {}

        def execute(delivery):
            if not a_inside.is_set():          # worker A (first caller)
                a_inside.set()
                a_release.wait(10)
                raise TimeoutError('A finally timed out')
            return WebhookOutcome.processed()  # worker B

        def worker_a():
            try:
                results['A'] = process_delivery(d.pk)
            finally:
                connection.close()

        with patch('apps.billing.webhook_processor.execute_delivery', side_effect=execute):
            ta = threading.Thread(target=worker_a)
            ta.start()
            self.assertTrue(a_inside.wait(10))
            # B cannot take a live lease...
            self.assertIsNone(claim_delivery(d.pk))
            # ...but can once it expires.
            WebhookDelivery.objects.filter(pk=d.pk).update(
                last_attempt_at=timezone.now() - timedelta(hours=1),
            )
            results['B'] = process_delivery(d.pk)
            a_release.set()
            ta.join(10)

        self.assertEqual(results, {'A': None, 'B': S.PROCESSED})
        d.refresh_from_db()
        self.assertEqual((d.processing_status, d.attempts, d.error_category), (S.PROCESSED, 3, ''))

    def test_worker_that_lost_its_lease_cannot_overwrite_newer_attempt(self):
        d = self._delivery()
        first = claim_delivery(d.pk)
        # Lease expires; a second worker reclaims and finishes.
        WebhookDelivery.objects.filter(pk=d.pk).update(last_attempt_at=timezone.now() - timedelta(hours=1))
        with patch('apps.billing.webhook_processor.execute_delivery', return_value=WebhookOutcome.processed()):
            self.assertEqual(process_delivery(d.pk), S.PROCESSED)
        # The stale first worker now tries to record a failure.
        from apps.billing.webhook_lifecycle import _record_failure
        self.assertIsNone(_record_failure(first, 'internal_error', 'late'))
        d.refresh_from_db()
        self.assertEqual((d.processing_status, d.attempts), (S.PROCESSED, 3))


# ─────────────────────────────────────────────────────────────────────────────
# Slice 5B.4.1 — migration 0023 on historic rows (real PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────

class Migration0023HistoricReceivedTests(TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    BEFORE = [('billing', '0022_add_appointments_service_type'),
              ('menu', '0014_remove_mercadopagoconnection_state_only')]
    AFTER = [('billing', '0023_webhookdelivery_retry_lifecycle')]

    def _migrate(self, targets):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def tearDown(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_historic_received_classification(self):
        old_apps = self._migrate(self.BEFORE)
        OldDelivery = old_apps.get_model('billing', 'WebhookDelivery')
        self.assertNotIn('attempts', [f.name for f in OldDelivery._meta.get_fields()])

        # Local records the legacy handler would have written (tables not
        # touched by 0023, so the current models are fine for them).
        biz = Business.objects.create(name='Hist', default_service='restaurante')

        def tip(ref, pid, status):
            TipTransaction.objects.create(business=biz, amount='10.00', currency='ARS',
                                          status=status, external_reference=ref, mp_payment_id=pid)
        tip('TIP-HIST-1', 'tip-final', 'approved')
        tip('TIP-HIST-2', 'tip-pending', 'pending')
        tip('TIP-HIST-3', 'both', 'approved')
        _make_pending(mp_payment_id='bill-done', status='completed')
        _make_pending(mp_payment_id='bill-failed', status='failed')
        _make_pending(mp_payment_id='both', status='completed')

        now = timezone.now()

        def row(topic, rid, status='received', **extra):
            data = dict(topic=topic, resource_id=rid, processing_status=status, received_at=now,
                        signature_valid=True, x_request_id=f'x-{topic}-{rid}-{status}',
                        payload_hash='h' * 64, body_json={'type': topic, 'data': {'id': rid}})
            data.update(extra)
            return OldDelivery.objects.create(**data).pk

        ids = {
            'tip_final': row('payment', 'tip-final'),
            'tip_pending': row('payment', 'tip-pending'),
            'bill_done': row('payment', 'bill-done'),
            'bill_failed': row('payment', 'bill-failed'),
            'both': row('payment', 'both'),
            'unknown': row('payment', 'nobody-knows'),
            'no_rid': row('payment', ''),
            'preapproval': row('subscription_preapproval', 'pre-1'),
            'auth_payment': row('subscription_authorized_payment', 'ap-1'),
            'other_topic': row('merchant_order', 'mo-1'),
            'bad_sig': row('payment', 'tip-final', signature_valid=False),
            'failed': row('subscription_preapproval', 'pre-2', 'failed', error_message='boom'),
            'processed': row('subscription_preapproval', 'pre-3', 'processed', error_message='Orphan: note'),
            'ignored': row('merchant_order', 'mo-2', 'ignored'),
            'duplicated': row('payment', 'dup', 'duplicated'),
        }

        self._migrate(self.AFTER)

        def get(key):
            return WebhookDelivery.objects.get(pk=ids[key])

        expected = {
            'tip_final': (S.IGNORED, 'legacy_applied'),
            'bill_done': (S.IGNORED, 'legacy_applied'),
            'tip_pending': (S.DEAD_LETTER, 'legacy_unverified'),
            'bill_failed': (S.DEAD_LETTER, 'legacy_unverified'),
            'both': (S.DEAD_LETTER, 'legacy_unverified'),
            'unknown': (S.DEAD_LETTER, 'legacy_unverified'),
            'no_rid': (S.IGNORED, 'missing_resource_id'),
            'preapproval': (S.DEAD_LETTER, 'legacy_unverified'),
            'auth_payment': (S.DEAD_LETTER, 'legacy_unverified'),
            'other_topic': (S.IGNORED, 'unsupported_topic'),
            'bad_sig': (S.IGNORED, 'invalid_signature'),
            # Non-RECEIVED rows are untouched.
            'failed': (S.FAILED, ''),
            'processed': (S.PROCESSED, ''),
            'ignored': (S.IGNORED, ''),
            'duplicated': (S.DUPLICATED, ''),
        }
        for key, (status, category) in expected.items():
            d = get(key)
            self.assertEqual((d.processing_status, d.error_category), (status, category), key)

        # New fields exist with safe defaults; historic metadata preserved.
        d = get('unknown')
        self.assertEqual((d.attempts, d.flow, d.ref), (0, '', ''))
        self.assertIsNone(d.next_retry_at)
        self.assertIsNone(d.last_attempt_at)
        self.assertEqual(d.body_json, {'type': 'payment', 'data': {'id': 'nobody-knows'}})
        self.assertEqual((d.x_request_id, d.payload_hash), ('x-payment-nobody-knows-received', 'h' * 64))
        self.assertTrue(d.error_message.startswith('Pre-5B.4 delivery'))
        self.assertEqual(get('failed').error_message, 'boom')
        self.assertEqual(get('processed').error_message, 'Orphan: note')

        # Nothing historic is picked up by the automatic sweeper.
        self.assertFalse(eligible_for_retry_qs().filter(pk__in=ids.values()).exists())
