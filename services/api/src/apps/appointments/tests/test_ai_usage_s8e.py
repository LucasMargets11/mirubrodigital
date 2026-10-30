from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.appointments.models import (
    AppointmentAIUsageBillingIntent, AppointmentAIUsageCharge,
    AppointmentAIUsageSession, AppointmentAIUsageSettlement,
)
from apps.appointments.services.ai_usage import AIUsageUnavailable
from apps.appointments.services.ai_usage_billing_intent import (
    AIUsageBillingIntentConflict,
    claim_ai_usage_billing_intent,
    mark_ai_usage_billing_intent_failed,
    mark_ai_usage_billing_intent_succeeded,
    prepare_ai_usage_billing_intent,
    retry_ai_usage_billing_intent,
    void_ai_usage_billing_intent,
)
from apps.appointments.tests.test_ai_usage_s8d import AIUsageSettlementFixture
from apps.appointments.services.ai_usage_settlement import finalize_ai_usage_settlement
from apps.appointments.tests.test_ai_usage_s8a import END
from apps.billing.models import SubscriptionV2
from apps.business.models import Business


class BillingIntentFixture(AIUsageSettlementFixture):
    def overage(self):
        self.seed_economic_usage(301)
        return self.close()

    def prepare(self):
        return prepare_ai_usage_billing_intent(self.overage())

    def claim(self):
        return claim_ai_usage_billing_intent(self.prepare())

    def fail(self, intent, **kwargs):
        return mark_ai_usage_billing_intent_failed(
            intent, attempt_token=intent.attempt_token, provider='test_provider',
            failure_code=kwargs.pop('failure_code', 'declined'), **kwargs,
        )

    def succeed(self, intent, **kwargs):
        return mark_ai_usage_billing_intent_succeeded(
            intent, attempt_token=kwargs.pop('attempt_token', intent.attempt_token),
            provider='test_provider', provider_reference='test-result', **kwargs,
        )


class AIUsageBillingIntentTests(BillingIntentFixture, TestCase):
    def test_finalized_overage_copies_exact_integer_snapshot_pending(self):
        settlement = self.overage()
        intent = prepare_ai_usage_billing_intent(settlement)
        intent.refresh_from_db()
        self.assertEqual(intent.settlement_id, settlement.pk)
        self.assertEqual(intent.business_id, settlement.business_id)
        self.assertEqual(intent.subscription_id, settlement.subscription_id)
        self.assertEqual((intent.amount, intent.currency), (settlement.overage_amount, settlement.currency))
        self.assertEqual(intent.amount, 300)
        self.assertIs(type(intent.amount), int)
        self.assertEqual(intent.status, 'pending')
        self.assertIsNone(intent.provider)
        self.assertIsNone(intent.completed_at)
        self.assertIsNone(intent.attempt_token)
        self.assertIsNotNone(intent.created_at)
        self.assertIsNotNone(intent.updated_at)

    def test_retry_returns_same_row_and_deterministic_reference(self):
        intent = self.prepare()
        frozen = AppointmentAIUsageBillingIntent.objects.values().get(pk=intent.pk)
        for _ in range(3):
            repeated = prepare_ai_usage_billing_intent(intent.settlement)
            self.assertEqual(repeated.pk, intent.pk)
            self.assertEqual(repeated.external_reference, f'MIRUBRO-AI-OVERAGE-{intent.settlement_id}')
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.values().get(pk=intent.pk), frozen)

    def test_database_one_to_one_prevents_duplicate(self):
        intent = self.prepare()
        values = AppointmentAIUsageBillingIntent.objects.values().get(pk=intent.pk)
        values['id'] = uuid.uuid4()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentAIUsageBillingIntent.objects.create(**values)
        with connections['default'].cursor() as cursor:
            constraints = connections['default'].introspection.get_constraints(
                cursor, AppointmentAIUsageBillingIntent._meta.db_table,
            )
        self.assertTrue(any(c['unique'] and c['columns'] == ['settlement_id'] for c in constraints.values()))

    def test_pending_settlement_rejected(self):
        with self.assertRaises(AIUsageUnavailable):
            prepare_ai_usage_billing_intent(self.pending())
        self.assertFalse(AppointmentAIUsageBillingIntent.objects.exists())

    def test_missing_settlement_rejected(self):
        with self.assertRaises(AIUsageUnavailable):
            prepare_ai_usage_billing_intent(AppointmentAIUsageSettlement())

    def test_zero_amount_is_void_without_simulated_success_or_provider(self):
        settlement = self.close()
        intent = prepare_ai_usage_billing_intent(settlement)
        self.assertEqual((intent.amount, intent.status, intent.failure_code), (0, 'void', 'zero_amount'))
        self.assertIsNone(intent.provider)
        self.assertIsNone(intent.provider_reference)
        self.assertIsNone(intent.processing_started_at)
        self.assertIsNotNone(intent.completed_at)
        self.assertEqual(prepare_ai_usage_billing_intent(settlement).pk, intent.pk)
        with self.assertRaises(AIUsageBillingIntentConflict):
            claim_ai_usage_billing_intent(intent)

    def test_pricing_changes_cannot_reprice_existing_or_new_intent(self):
        settlement = self.overage()
        with patch('apps.billing.canonical_pricing.get_usage_tier', side_effect=AssertionError('repricing')):
            intent = prepare_ai_usage_billing_intent(settlement)
            self.assertEqual(prepare_ai_usage_billing_intent(settlement).amount, 300)
        self.assertEqual(intent.amount, 300)

    def test_tier_change_preserves_snapshot(self):
        intent = self.prepare()
        self.tier('ai_1500')
        self.assertEqual(prepare_ai_usage_billing_intent(intent.settlement).amount, 300)

    def test_cancellation_and_downgrade_do_not_change_historical_intent(self):
        settlement = self.overage()
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            status='canceled', is_active=False, plan_code='appointments_pro', usage_tier=None,
        )
        intent = prepare_ai_usage_billing_intent(settlement)
        frozen = AppointmentAIUsageBillingIntent.objects.values().get(pk=intent.pk)
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='expired')
        self.assertEqual(prepare_ai_usage_billing_intent(settlement).pk, intent.pk)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.values().get(pk=intent.pk), frozen)

    def test_subscription_business_mismatch_fails_closed(self):
        settlement = self.overage()
        other = Business.objects.create(name='Other', slug=f'other-{uuid.uuid4().hex}')
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(business=other)
        with self.assertRaises(AIUsageUnavailable):
            prepare_ai_usage_billing_intent(settlement)
        self.assertFalse(AppointmentAIUsageBillingIntent.objects.exists())

    def test_stale_caller_values_are_not_used_as_economics(self):
        settlement = self.overage()
        settlement.overage_amount = 999.5
        settlement.currency = 'USD'
        settlement.business_id = uuid.uuid4()
        intent = prepare_ai_usage_billing_intent(settlement)
        self.assertEqual((intent.amount, intent.currency, intent.business_id), (300, 'ARS', self.business.pk))

    def test_snapshot_and_external_reference_immutable_in_database(self):
        intent = self.prepare()
        for values in (
            {'amount': 301}, {'currency': 'USD'}, {'external_reference': 'different'},
            {'business_id': self.business.pk + 100000}, {'subscription_id': uuid.uuid4()},
            {'settlement_id': uuid.uuid4()},
        ):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                AppointmentAIUsageBillingIntent.objects.filter(pk=intent.pk).update(**values)

    def test_database_rejects_mismatched_initial_snapshot(self):
        settlement = self.overage()
        for values in (
            {'amount': 301}, {'currency': 'USD'}, {'external_reference': 'wrong'},
            {'business_id': self.business.pk + 100000}, {'subscription_id': uuid.uuid4()},
        ):
            data = dict(
                settlement=settlement, business=self.business, subscription=self.subscription,
                amount=300, currency='ARS', external_reference=f'MIRUBRO-AI-OVERAGE-{settlement.pk}',
            )
            for name in values:
                data.pop(name.removesuffix('_id'), None)
            data.update(values)
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                AppointmentAIUsageBillingIntent.objects.create(**data)

    def test_claim_only_once_and_persists_token(self):
        claimed = self.claim()
        self.assertEqual(claimed.status, 'processing')
        self.assertIsInstance(claimed.attempt_token, uuid.UUID)
        self.assertIsNotNone(claimed.processing_started_at)
        with self.assertRaises(AIUsageBillingIntentConflict):
            claim_ai_usage_billing_intent(claimed)

    def test_success_terminal_and_late_failure_rejected(self):
        current = self.claim()
        success = self.succeed(current)
        self.assertEqual((success.status, success.provider_reference), ('succeeded', 'test-result'))
        self.assertIsNotNone(success.completed_at)
        for action in (claim_ai_usage_billing_intent, self.fail, self.succeed, void_ai_usage_billing_intent):
            with self.subTest(action=action), self.assertRaises(AIUsageBillingIntentConflict):
                action(success)
        success.refresh_from_db()
        self.assertEqual(success.status, 'succeeded')
        self.assertEqual(prepare_ai_usage_billing_intent(success.settlement).status, 'succeeded')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentAIUsageBillingIntent.objects.filter(pk=success.pk).update(
                status='processing', completed_at=None,
            )

    def test_void_terminal_and_never_revived(self):
        intent = void_ai_usage_billing_intent(self.prepare())
        for action in (claim_ai_usage_billing_intent, self.fail, self.succeed):
            with self.subTest(action=action), self.assertRaises(AIUsageBillingIntentConflict):
                action(intent)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentAIUsageBillingIntent.objects.filter(pk=intent.pk).update(status='pending', completed_at=None)

    def test_processing_cannot_be_voided_or_reclaimed(self):
        intent = self.claim()
        with self.assertRaises(AIUsageBillingIntentConflict):
            void_ai_usage_billing_intent(intent)
        with self.assertRaises(AIUsageBillingIntentConflict):
            retry_ai_usage_billing_intent(intent, attempt_token=intent.attempt_token, confirmed_no_charge=True)

    def test_failed_retry_requires_explicit_reconciliation_and_matching_attempt(self):
        failed = self.fail(self.claim())
        with self.assertRaises(AIUsageBillingIntentConflict):
            claim_ai_usage_billing_intent(failed)
        for token, confirmed in ((failed.attempt_token, False), (uuid.uuid4(), True)):
            with self.assertRaises(AIUsageBillingIntentConflict):
                retry_ai_usage_billing_intent(failed, attempt_token=token, confirmed_no_charge=confirmed)
        pending = retry_ai_usage_billing_intent(
            failed, attempt_token=failed.attempt_token, confirmed_no_charge=True,
        )
        self.assertEqual(pending.status, 'pending')
        self.assertIsNone(pending.provider_reference)
        self.assertIsNone(pending.failure_message)
        self.assertIsNone(pending.attempt_token)
        claimed = claim_ai_usage_billing_intent(pending)
        self.assertNotEqual(claimed.attempt_token, failed.attempt_token)
        self.assertEqual(claimed.external_reference, failed.external_reference)

    def test_old_result_cannot_overwrite_new_attempt_or_other_intent(self):
        failed = self.fail(self.claim())
        old_token = failed.attempt_token
        pending = retry_ai_usage_billing_intent(failed, attempt_token=old_token, confirmed_no_charge=True)
        current = claim_ai_usage_billing_intent(pending)
        for token in (old_token, uuid.uuid4()):
            with self.assertRaises(AIUsageBillingIntentConflict):
                self.succeed(current, attempt_token=token)
        current.refresh_from_db()
        self.assertEqual(current.status, 'processing')
        self.assertEqual(self.succeed(current).status, 'succeeded')

    def test_result_token_from_another_intent_cannot_complete_current_intent(self):
        current = self.claim()
        self.renewal()
        end = END + timedelta(days=30)
        self.seed_usage(300, start=END, end=end)
        AppointmentAIUsageCharge.objects.bulk_create([
            AppointmentAIUsageCharge(
                session=session, business=self.business, subscription=self.subscription,
                usage_period_start=END, usage_period_end=end, usage_tier='ai_300',
                session_ordinal=index, included_sessions_snapshot=300,
                classification='included', unit_price=0, amount=0,
            )
            for index, session in enumerate(
                AppointmentAIUsageSession.objects.filter(usage_period_start=END).order_by('pk'), 1,
            )
        ])
        self.record(END)
        other_settlement = finalize_ai_usage_settlement(
            business=self.business, subscription=self.subscription,
            period_start=END, period_end=end, at=end,
        )
        other = claim_ai_usage_billing_intent(prepare_ai_usage_billing_intent(other_settlement))
        with self.assertRaises(AIUsageBillingIntentConflict):
            self.succeed(other, attempt_token=current.attempt_token)
        other.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(other.status, 'processing')
        self.assertEqual(current.status, 'processing')

    def test_failed_intent_can_be_voided_without_provider_operation(self):
        failed = self.fail(self.claim())
        self.assertEqual(void_ai_usage_billing_intent(failed).status, 'void')

    def test_invalid_provider_metadata_is_explicitly_rejected(self):
        current = self.claim()
        with self.assertRaises(AIUsageBillingIntentConflict):
            mark_ai_usage_billing_intent_succeeded(
                current, attempt_token=current.attempt_token,
                provider='Authorization: Bearer secret', provider_reference='bad\nheader',
            )
        current.refresh_from_db()
        self.assertEqual(current.status, 'processing')

    def test_failure_info_discards_tokens_cards_headers_and_unknown_codes(self):
        secret = 'Authorization: Bearer APP_USR-secret access_token=hidden card=4111111111111111'
        failed = self.fail(self.claim(), failure_code=secret, failure_message=secret)
        failed.refresh_from_db()
        self.assertEqual(failed.failure_code, 'provider_error')
        self.assertEqual(failed.failure_message, 'Provider processing failed; outcome requires reconciliation.')
        self.assertNotIn(secret, str(AppointmentAIUsageBillingIntent.objects.values().get(pk=failed.pk)))

    def test_database_refuses_unsanitized_failure_message(self):
        intent = self.claim()
        with self.assertRaisesMessage(IntegrityError, 'sanitized'), transaction.atomic():
            AppointmentAIUsageBillingIntent.objects.filter(pk=intent.pk).update(
                status='failed', completed_at=intent.processing_started_at,
                failure_code='declined', failure_message='Authorization: Bearer secret',
            )

    def test_services_have_no_external_calls_or_subscription_economic_mutations(self):
        with (
            patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden')),
            patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')),
            patch('socket.create_connection', side_effect=AssertionError('Network forbidden')),
        ):
            history = SubscriptionV2.objects.values().get(pk=self.subscription.pk)
            failed = self.fail(self.claim())
            pending = retry_ai_usage_billing_intent(
                failed, attempt_token=failed.attempt_token, confirmed_no_charge=True,
            )
            void_ai_usage_billing_intent(pending)
            self.assertEqual(SubscriptionV2.objects.values().get(pk=self.subscription.pk), history)

    def test_result_cannot_reassign_attempt_in_database(self):
        intent = self.claim()
        with self.assertRaisesMessage(IntegrityError, 'attempt'), transaction.atomic():
            AppointmentAIUsageBillingIntent.objects.filter(pk=intent.pk).update(
                status='failed', completed_at=intent.processing_started_at,
                attempt_token=uuid.uuid4(), failure_code='declined',
                failure_message='Provider declined the operation.',
            )


@skipUnlessDBFeature('has_select_for_update')
class AIUsageBillingIntentConcurrencyTests(BillingIntentFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def race(self, operation):
        barrier = threading.Barrier(2)

        def worker():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    return operation()
                except AIUsageBillingIntentConflict:
                    return 'conflict'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            return [future.result(timeout=30) for future in futures]

    def test_two_preparers_create_one_row(self):
        settlement = self.overage()
        results = self.race(lambda: prepare_ai_usage_billing_intent(settlement).pk)
        self.assertEqual(results[0], results[1])
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.count(), 1)

    def test_two_workers_only_one_claim(self):
        intent = self.prepare()
        results = self.race(lambda: claim_ai_usage_billing_intent(intent).attempt_token)
        self.assertEqual(results.count('conflict'), 1)
        intent.refresh_from_db()
        self.assertIn(intent.attempt_token, results)
        self.assertEqual(intent.status, 'processing')

    def test_success_and_failure_race_only_one_result_wins(self):
        intent = self.claim()
        barrier = threading.Barrier(2)

        def worker(succeeded):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    return (self.succeed(intent) if succeeded else self.fail(intent)).status
                except AIUsageBillingIntentConflict:
                    return 'conflict'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, result) for result in (True, False)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(results.count('conflict'), 1)
        intent.refresh_from_db()
        self.assertIn(intent.status, ('succeeded', 'failed'))
