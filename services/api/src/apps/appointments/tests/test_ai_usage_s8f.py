from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature

from apps.appointments.models import AppointmentAIUsageBillingAttempt
from apps.appointments.services.ai_usage_billing_intent import (
    AIUsageBillingIntentConflict,
    prepare_ai_usage_billing_intent,
    retry_ai_usage_billing_intent,
    void_ai_usage_billing_intent,
)
from apps.appointments.services.ai_usage_billing_provider import (
    AIUsageBillingRequest,
    AIUsageBillingResult,
    DisabledAIUsageBillingProvider,
    get_ai_usage_billing_provider,
    process_ai_usage_billing_intent,
    reconcile_ai_usage_billing_intent,
    record_ai_usage_billing_result,
)
from apps.appointments.tests.test_ai_usage_s8e import BillingIntentFixture
from apps.billing.models import SubscriptionV2


class FakeProvider:
    name = 'fake'

    def __init__(self, result=None):
        self.result = result or AIUsageBillingResult('succeeded', 'fake-1')
        self.requests = []
        self.status_requests = []

    def charge(self, request):
        self.requests.append(request)
        return self.result

    def get_status(self, provider_reference, *, external_reference):
        self.status_requests.append((provider_reference, external_reference))
        return self.result


class AIUsageBillingProviderTests(BillingIntentFixture, TestCase):
    def setUp(self):
        super().setUp()
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target in (
            'requests.sessions.Session.request', 'urllib.request.urlopen',
            'socket.create_connection', 'socket.socket.connect', 'http.client.HTTPConnection.connect',
        ):
            stack.enter_context(patch(target, side_effect=AssertionError('Network forbidden')))

    def unknown(self, *, reference='fake-1'):
        adapter = FakeProvider(AIUsageBillingResult('outcome_unknown', reference, 'timeout'))
        intent = process_ai_usage_billing_intent(self.prepare(), provider=adapter)
        return intent, adapter

    @override_settings(AI_USAGE_BILLING_PROVIDER='disabled')
    def test_default_disabled_no_network_and_explicit_reason(self):
        adapter = get_ai_usage_billing_provider()
        self.assertIsInstance(adapter, DisabledAIUsageBillingProvider)
        result = adapter.charge(AIUsageBillingRequest(uuid.uuid4(), 300, 'ARS', 'stable'))
        self.assertEqual((result.status, result.failure_code), ('failed', 'provider_not_enabled'))
        self.assertIsNone(result.provider_reference)

    @override_settings(AI_USAGE_BILLING_PROVIDER='disabled')
    def test_pending_can_claim_but_disabled_never_succeeds(self):
        claimed = self.claim()
        result = process_ai_usage_billing_intent(claimed, attempt_token=claimed.attempt_token)
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.attempt_token, claimed.attempt_token)
        attempt = result.provider_attempts.get()
        self.assertEqual((attempt.provider, attempt.failure_code), ('disabled', 'provider_not_enabled'))
        self.assertIsNone(result.provider_reference)

    def test_unknown_configuration_and_mercadopago_fail_closed(self):
        for value in ('mercadopago', 'fake', 'invalid', '', None):
            with self.subTest(value=value), override_settings(AI_USAGE_BILLING_PROVIDER=value):
                with self.assertLogs('apps.appointments.services.ai_usage_billing_provider', 'WARNING'):
                    self.assertIsInstance(get_ai_usage_billing_provider(), DisabledAIUsageBillingProvider)

    def test_success_uses_frozen_amount_and_stable_idempotency_reference(self):
        intent = self.prepare()
        intent.amount = 99999
        intent.external_reference = 'stale'
        adapter = FakeProvider()
        result = process_ai_usage_billing_intent(intent, provider=adapter)
        request = adapter.requests[0]
        self.assertEqual(result.status, 'succeeded')
        self.assertEqual((request.amount, request.currency), (300, 'ARS'))
        self.assertEqual(request.intent_id, result.pk)
        self.assertEqual(request.external_reference, result.external_reference)
        self.assertEqual(request.idempotency_key, result.external_reference)
        self.assertEqual(result.provider_reference, 'fake-1')

    def test_known_failure_marks_failed(self):
        result = process_ai_usage_billing_intent(
            self.prepare(), provider=FakeProvider(AIUsageBillingResult('failed', 'fake-1', 'declined')),
        )
        self.assertEqual((result.status, result.failure_code), ('failed', 'declined'))

    def test_unknown_retains_processing_and_blocks_all_retry_and_dispatch(self):
        intent, adapter = self.unknown()
        self.assertEqual(intent.status, 'processing')
        self.assertEqual(intent.provider_attempts.get().status, 'outcome_unknown')
        self.assertIsNone(intent.completed_at)
        with self.assertRaises(AIUsageBillingIntentConflict):
            retry_ai_usage_billing_intent(
                intent, attempt_token=intent.attempt_token, confirmed_no_charge=True,
            )
        for token in (None, intent.attempt_token):
            with self.assertRaises(AIUsageBillingIntentConflict):
                process_ai_usage_billing_intent(intent, provider=adapter, attempt_token=token)
        self.assertEqual(len(adapter.requests), 1)

    def test_late_old_token_rejected_after_retry(self):
        adapter = FakeProvider(AIUsageBillingResult('failed', failure_code='declined'))
        failed = process_ai_usage_billing_intent(self.prepare(), provider=adapter)
        old_token = failed.attempt_token
        pending = retry_ai_usage_billing_intent(
            failed, attempt_token=old_token, confirmed_no_charge=True,
        )
        adapter.result = AIUsageBillingResult('outcome_unknown', 'fake-2', 'timeout')
        current = process_ai_usage_billing_intent(pending, provider=adapter)
        with self.assertRaises(AIUsageBillingIntentConflict):
            record_ai_usage_billing_result(
                current, attempt_token=old_token, result=AIUsageBillingResult('succeeded', 'fake-1'),
            )
        self.assertEqual(current.provider_attempts.get(attempt_token=current.attempt_token).status, 'outcome_unknown')

    def test_reference_set_once_and_cannot_be_replaced_or_cleared(self):
        intent, _ = self.unknown()
        for reference in ('other', None):
            with self.subTest(reference=reference), self.assertRaises(AIUsageBillingIntentConflict):
                record_ai_usage_billing_result(
                    intent, attempt_token=intent.attempt_token,
                    result=AIUsageBillingResult('outcome_unknown', reference, 'timeout'),
                )
        self.assertEqual(intent.provider_attempts.get().provider_reference, 'fake-1')
        result = record_ai_usage_billing_result(
            intent, attempt_token=intent.attempt_token, result=AIUsageBillingResult('succeeded', 'fake-1'),
        )
        self.assertEqual(result.provider_reference, 'fake-1')
        with self.assertRaises(AIUsageBillingIntentConflict):
            record_ai_usage_billing_result(
                intent, attempt_token=intent.attempt_token, result=AIUsageBillingResult('succeeded', 'fake-1'),
            )

    def test_reference_database_guard(self):
        intent, _ = self.unknown()
        with self.assertRaises(IntegrityError), transaction.atomic():
            intent.provider_attempts.update(provider_reference='replacement')

    def test_unknown_reservation_still_blocks_dispatch_after_out_of_band_s8e_retry(self):
        intent, adapter = self.unknown()
        failed = self.fail(intent)
        pending = retry_ai_usage_billing_intent(
            failed, attempt_token=failed.attempt_token, confirmed_no_charge=True,
        )
        with self.assertRaises(AIUsageBillingIntentConflict):
            process_ai_usage_billing_intent(pending, provider=adapter)
        self.assertEqual(len(adapter.requests), 1)

    def test_retry_keeps_external_reference_and_attempt_history(self):
        adapter = FakeProvider(AIUsageBillingResult('failed', 'declined-1', 'declined'))
        failed = process_ai_usage_billing_intent(self.prepare(), provider=adapter)
        pending = retry_ai_usage_billing_intent(
            failed, attempt_token=failed.attempt_token, confirmed_no_charge=True,
        )
        adapter.result = AIUsageBillingResult('succeeded', 'success-2')
        result = process_ai_usage_billing_intent(pending, provider=adapter)
        self.assertEqual([r.idempotency_key for r in adapter.requests], [failed.external_reference] * 2)
        self.assertEqual(result.provider_attempts.count(), 2)
        self.assertEqual(result.provider_attempts.get(attempt_token=failed.attempt_token).provider_reference, 'declined-1')

    def test_succeeded_never_charged_twice(self):
        adapter = FakeProvider()
        intent = process_ai_usage_billing_intent(self.prepare(), provider=adapter)
        with self.assertRaises(AIUsageBillingIntentConflict):
            process_ai_usage_billing_intent(intent, provider=adapter)
        self.assertEqual(len(adapter.requests), 1)

    def test_void_never_processed(self):
        intent = void_ai_usage_billing_intent(self.prepare())
        adapter = FakeProvider()
        with self.assertRaises(AIUsageBillingIntentConflict):
            process_ai_usage_billing_intent(intent, provider=adapter)
        self.assertEqual(adapter.requests, [])
        self.assertFalse(intent.provider_attempts.exists())

    def test_zero_never_reaches_provider(self):
        intent = prepare_ai_usage_billing_intent(self.close())
        adapter = FakeProvider()
        with self.assertRaises(AIUsageBillingIntentConflict):
            process_ai_usage_billing_intent(intent, provider=adapter)
        self.assertEqual(adapter.requests, [])

    def test_error_sanitized_without_raw_payloads(self):
        raw = 'Authorization: secret access_token=hidden card=4111111111111111'
        adapter = FakeProvider(AIUsageBillingResult('failed', 'fake-1', raw))
        result = process_ai_usage_billing_intent(self.prepare(), provider=adapter)
        self.assertEqual(result.status, 'processing')
        self.assertIsNone(result.failure_code)
        self.assertEqual(result.provider_attempts.get().failure_code, 'provider_error')
        self.assertNotIn(raw, str(result.provider_attempts.values().get()))

    def test_timeout_or_generic_error_cannot_masquerade_as_known_failure(self):
        for code in ('timeout', 'provider_error', None, 'unrecognized'):
            with self.subTest(code=code):
                self.assertEqual(AIUsageBillingResult('failed', 'fake-1', code).status, 'outcome_unknown')

    def test_timeout_remains_unknown_without_leaking_exception(self):
        adapter = FakeProvider()
        with patch.object(adapter, 'charge', side_effect=TimeoutError('secret token')):
            result = process_ai_usage_billing_intent(self.prepare(), provider=adapter)
        self.assertEqual(result.status, 'processing')
        attempt = result.provider_attempts.get()
        self.assertEqual((attempt.status, attempt.failure_code), ('outcome_unknown', 'timeout'))
        self.assertIsNone(attempt.provider_reference)

    def test_unexpected_error_is_explicit_and_reservation_blocks_redispatch(self):
        intent = self.prepare()
        adapter = FakeProvider()
        with patch.object(adapter, 'charge', side_effect=RuntimeError('adapter implementation error')):
            with self.assertRaises(RuntimeError):
                process_ai_usage_billing_intent(intent, provider=adapter)
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'processing')
        self.assertEqual(intent.provider_attempts.get().failure_code, 'dispatch_incomplete')
        with self.assertRaises(AIUsageBillingIntentConflict):
            process_ai_usage_billing_intent(intent, provider=adapter)

    def test_reconciliation_success(self):
        intent, adapter = self.unknown()
        adapter.result = AIUsageBillingResult('succeeded', 'fake-1')
        result = reconcile_ai_usage_billing_intent(intent, attempt_token=intent.attempt_token, provider=adapter)
        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(adapter.status_requests, [('fake-1', intent.external_reference)])
        self.assertEqual(len(adapter.requests), 1)

    def test_reconciliation_known_failure(self):
        intent, adapter = self.unknown()
        adapter.result = AIUsageBillingResult('failed', 'fake-1', 'declined')
        result = reconcile_ai_usage_billing_intent(intent, attempt_token=intent.attempt_token, provider=adapter)
        self.assertEqual((result.status, result.failure_code), ('failed', 'declined'))

    def test_reconciliation_unknown_stays_fail_safe(self):
        intent, adapter = self.unknown()
        for _ in range(2):
            result = reconcile_ai_usage_billing_intent(intent, attempt_token=intent.attempt_token, provider=adapter)
            self.assertEqual(result.status, 'processing')
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(result.provider_attempts.get().provider_reference, 'fake-1')

    def test_reconciliation_timeout_keeps_reference(self):
        intent, adapter = self.unknown()
        with patch.object(adapter, 'get_status', side_effect=TimeoutError('secret')):
            result = reconcile_ai_usage_billing_intent(intent, attempt_token=intent.attempt_token, provider=adapter)
        self.assertEqual(result.status, 'processing')
        self.assertEqual(result.provider_attempts.get().provider_reference, 'fake-1')

    def test_missing_reference_requires_late_correlated_evidence(self):
        intent, adapter = self.unknown(reference=None)
        with self.assertRaises(AIUsageBillingIntentConflict):
            reconcile_ai_usage_billing_intent(intent, attempt_token=intent.attempt_token, provider=adapter)
        self.assertEqual(adapter.status_requests, [])
        result = record_ai_usage_billing_result(
            intent, attempt_token=intent.attempt_token, result=AIUsageBillingResult('succeeded', 'late-1'),
        )
        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.provider_attempts.get().provider_reference, 'late-1')

    def test_wrong_provider_and_stale_reconciliation_rejected(self):
        intent, adapter = self.unknown()
        with self.assertRaises(AIUsageBillingIntentConflict):
            reconcile_ai_usage_billing_intent(intent, attempt_token=intent.attempt_token)
        with self.assertRaises(AIUsageBillingIntentConflict):
            reconcile_ai_usage_billing_intent(intent, attempt_token=uuid.uuid4(), provider=adapter)
        self.assertEqual(adapter.status_requests, [])

    @override_settings(AI_USAGE_BILLING_PROVIDER='disabled')
    def test_adapter_does_not_read_credentials_or_environment(self):
        intent = self.prepare()
        original_getattribute = type(settings).__getattribute__

        def guarded_getattribute(instance, name):
            if 'TOKEN' in name.upper():
                raise AssertionError('Access Token read forbidden')
            return original_getattribute(instance, name)

        with (
            patch('os.getenv', side_effect=AssertionError('Environment read forbidden')),
            patch('os.environ.get', side_effect=AssertionError('Environment read forbidden')),
            patch('django.conf.LazySettings.__getattribute__', guarded_getattribute),
        ):
            result = process_ai_usage_billing_intent(intent, provider=get_ai_usage_billing_provider())
        self.assertEqual(result.status, 'failed')

    def test_no_tax_repricing_or_subscription_changes(self):
        intent = self.prepare()
        subscription = SubscriptionV2.objects.values().get(pk=self.subscription.pk)
        settlement = type(intent.settlement).objects.values().get(pk=intent.settlement_id)
        adapter = FakeProvider()
        with patch('apps.billing.canonical_pricing.get_usage_tier', side_effect=AssertionError('repricing')):
            process_ai_usage_billing_intent(intent, provider=adapter)
        self.assertEqual(adapter.requests[0].amount, settlement['overage_amount'])
        self.assertEqual(SubscriptionV2.objects.values().get(pk=self.subscription.pk), subscription)
        self.assertEqual(type(intent.settlement).objects.values().get(pk=intent.settlement_id), settlement)

    def test_invalid_or_raw_provider_results_rejected_safely(self):
        adapter = FakeProvider()
        adapter.result = {'status': 'succeeded', 'provider_reference': 'raw'}
        intent = self.prepare()
        with self.assertRaises(AIUsageBillingIntentConflict):
            process_ai_usage_billing_intent(intent, provider=adapter)
        self.assertEqual(intent.provider_attempts.get().status, 'outcome_unknown')
        for status, reference in (('invalid', 'fake'), ('succeeded', None), ('failed', 'bad\nheader')):
            with self.subTest(status=status, reference=reference), self.assertRaises(AIUsageBillingIntentConflict):
                AIUsageBillingResult(status, reference)


@skipUnlessDBFeature('has_select_for_update')
class AIUsageBillingProviderConcurrencyTests(BillingIntentFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def test_two_workers_dispatch_once_with_committed_reservation(self):
        self.race_dispatch(self.prepare())

    def test_two_workers_with_same_claim_token_dispatch_once(self):
        intent = self.claim()
        self.race_dispatch(intent, attempt_token=intent.attempt_token)

    def race_dispatch(self, intent, *, attempt_token=None):
        barrier = threading.Barrier(2)
        adapter = FakeProvider()
        original_charge = adapter.charge

        def charge(request):
            self.assertFalse(connections['default'].in_atomic_block)
            self.assertEqual(AppointmentAIUsageBillingAttempt.objects.filter(intent=intent).count(), 1)
            return original_charge(request)

        adapter.charge = charge

        def worker():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    return process_ai_usage_billing_intent(
                        intent, provider=adapter, attempt_token=attempt_token,
                    ).status
                except AIUsageBillingIntentConflict:
                    return 'conflict'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertCountEqual(results, ['succeeded', 'conflict'])
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(intent.provider_attempts.count(), 1)

    def test_outer_transaction_rejected_before_provider_dispatch(self):
        intent = self.prepare()
        adapter = FakeProvider()
        with transaction.atomic(), self.assertRaises(RuntimeError):
            process_ai_usage_billing_intent(intent, provider=adapter)
        self.assertEqual(adapter.requests, [])
        self.assertFalse(intent.provider_attempts.exists())
