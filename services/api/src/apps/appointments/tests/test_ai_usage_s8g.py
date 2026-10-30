from __future__ import annotations

import ast
import inspect
import json
import textwrap
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, OperationalError, connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature

from apps.appointments.models import (
    AppointmentAIUsageBillingAttempt,
    AppointmentAIUsageBillingIntent,
    AppointmentAIUsageCharge,
    AppointmentAIUsageSession,
    AppointmentAIUsageSettlement,
    AppointmentAIUsageSettlementEntry,
)
from apps.appointments.services.ai_usage import AIUsageUnavailable
from apps.appointments.services.ai_usage_billing_intent import prepare_ai_usage_billing_intent
from apps.appointments.services.ai_usage_billing_pipeline import (
    discover_ai_usage_periods_ready_for_settlement,
    process_due_ai_usage_billing,
)
from apps.appointments.tasks import process_due_ai_usage_billing_task
from apps.appointments.tests.test_ai_usage_s8a import AT, END, START
from apps.appointments.tests.test_ai_usage_s8e import BillingIntentFixture
from apps.billing.models import SubscriptionV2
from apps.billing.services.appointments_checkout import appointments_period_end
from apps.business.models import Business

PIPELINE = 'apps.appointments.services.ai_usage_billing_pipeline'
PROVIDER = 'apps.appointments.services.ai_usage_billing_provider'
EMPTY_SUMMARY = {
    'scanned': 0, 'settlements_created': 0, 'settlements_existing': 0,
    'intents_created': 0, 'intents_existing': 0, 'skipped': 0, 'failed': 0,
}


class AIUsageBillingPipelineTests(BillingIntentFixture, TestCase):
    def setUp(self):
        super().setUp()
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.guards = {}
        for target in (
            'requests.sessions.Session.request', 'urllib.request.urlopen',
            'socket.create_connection', 'socket.socket.connect', 'http.client.HTTPConnection.connect',
            f'{PROVIDER}.get_ai_usage_billing_provider',
            f'{PROVIDER}.process_ai_usage_billing_intent',
            f'{PROVIDER}.reconcile_ai_usage_billing_intent',
            f'{PROVIDER}.DisabledAIUsageBillingProvider.charge',
            f'{PROVIDER}.DisabledAIUsageBillingProvider.get_status',
        ):
            self.guards[target] = stack.enter_context(
                patch(target, side_effect=AssertionError('Provider/network access forbidden')),
            )

    def run_pipeline(self, at=END):
        summary = process_due_ai_usage_billing(at=at)
        self.assertEqual(set(summary), set(EMPTY_SUMMARY))
        self.assertTrue(all(type(value) is int and value >= 0 for value in summary.values()))
        self.assertEqual(
            summary['scanned'],
            summary['skipped'] + summary['failed'] + summary['intents_created'] + summary['intents_existing'],
        )
        self.assertEqual(json.loads(json.dumps(summary)), summary)
        return summary

    def other_subscription(self, *, start=START, end=END, business=None, status='active'):
        business = business or Business.objects.create(
            name='S8G other', slug=f's8g-{uuid.uuid4().hex}', status='active',
        )
        return SubscriptionV2.objects.create(
            business=business, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_300', billing_cycle='monthly', status=status,
            current_period_start=start, current_period_end=end,
        )

    def test_due_period_creates_settlement_and_intent_at_exact_boundary(self):
        self.record()
        summary = self.run_pipeline()
        self.assertEqual(summary, {
            **EMPTY_SUMMARY, 'scanned': 1, 'settlements_created': 1, 'intents_created': 1,
        })
        settlement = AppointmentAIUsageSettlement.objects.get()
        self.assertEqual((settlement.status, settlement.finalized_at), ('finalized', END))
        self.assertEqual(settlement.billing_intent.status, 'void')
        self.assertEqual(settlement.entries.count(), 1)

    def test_open_period_not_discovered_or_processed(self):
        self.record()
        self.assertEqual(self.run_pipeline(END - timedelta(microseconds=1)), EMPTY_SUMMARY)
        self.assertEqual(discover_ai_usage_periods_ready_for_settlement(at=AT).periods, ())
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_repeat_is_noop_without_duplicate_rows_or_writes(self):
        self.record()
        self.run_pipeline()
        models = (
            AppointmentAIUsageSession, AppointmentAIUsageCharge, AppointmentAIUsageSettlement,
            AppointmentAIUsageSettlementEntry, AppointmentAIUsageBillingIntent,
        )
        snapshots = [list(model.objects.values()) for model in models]
        with (
            patch(f'{PIPELINE}.finalize_ai_usage_settlement', side_effect=AssertionError('Already complete')),
            patch(f'{PIPELINE}.prepare_ai_usage_billing_intent', side_effect=AssertionError('Already complete')),
        ):
            self.assertEqual(self.run_pipeline(), EMPTY_SUMMARY)
        self.assertEqual([list(model.objects.values()) for model in models], snapshots)
        self.assertEqual([model.objects.count() for model in models], [1] * 5)

    def test_finalized_settlement_missing_intent_is_recovered(self):
        self.record()
        settlement = self.close()
        self.assertEqual(discover_ai_usage_periods_ready_for_settlement(at=END).periods, ())
        with patch(
            'apps.appointments.services.ai_usage_settlement.resolve_ai_overage_statement',
            side_effect=AssertionError('Finalized economics must not be revalidated'),
        ):
            summary = self.run_pipeline()
        self.assertEqual(summary, {
            **EMPTY_SUMMARY, 'scanned': 1, 'settlements_existing': 1, 'intents_created': 1,
        })
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.get().settlement_id, settlement.pk)

    def test_finalized_settlement_and_existing_intent_are_noop(self):
        intent = self.prepare()
        self.assertEqual(self.run_pipeline(), EMPTY_SUMMARY)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.get().pk, intent.pk)

    def test_empty_anchored_period_closes_zero_void(self):
        self.assertEqual(self.run_pipeline()['intents_created'], 1)
        intent = AppointmentAIUsageBillingIntent.objects.get()
        self.assertEqual((intent.amount, intent.status, intent.failure_code), (0, 'void', 'zero_amount'))
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)
        self.assertEqual(AppointmentAIUsageSettlementEntry.objects.count(), 0)

    def test_overage_prepares_pending_and_stops_before_claim(self):
        self.seed_economic_usage(301)
        summary = self.run_pipeline()
        self.assertEqual(summary['intents_created'], 1)
        intent = AppointmentAIUsageBillingIntent.objects.get()
        self.assertEqual((intent.amount, intent.status), (300, 'pending'))
        self.assertIsNone(intent.attempt_token)
        self.assertIsNone(intent.provider)
        self.assertFalse(AppointmentAIUsageBillingAttempt.objects.exists())
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 301)

    def test_two_businesses_are_independent(self):
        self.record()
        other = self.other_subscription()
        summary = self.run_pipeline()
        self.assertEqual(summary['settlements_created'], 2)
        self.assertEqual(summary['intents_created'], 2)
        self.assertEqual(
            set(AppointmentAIUsageBillingIntent.objects.values_list('business_id', flat=True)),
            {self.business.pk, other.business_id},
        )
        self.assertEqual(AppointmentAIUsageSettlementEntry.objects.count(), 1)

    def test_controlled_settlement_failure_does_not_abort_other_business(self):
        self.other_subscription()
        from apps.appointments.services.ai_usage_settlement import finalize_ai_usage_settlement

        def finalize(**kwargs):
            if kwargs['business'].pk == self.business.pk:
                raise AIUsageUnavailable('secret raw error')
            return finalize_ai_usage_settlement(**kwargs)

        with patch(f'{PIPELINE}.finalize_ai_usage_settlement', side_effect=finalize):
            with self.assertLogs(PIPELINE, 'INFO') as logs:
                summary = self.run_pipeline()
        self.assertEqual(summary, {
            **EMPTY_SUMMARY, 'scanned': 2, 'settlements_created': 1, 'intents_created': 1, 'failed': 1,
        })
        self.assertFalse(AppointmentAIUsageBillingIntent.objects.filter(business=self.business).exists())
        self.assertNotIn('secret raw error', str(logs.output) + str(summary))

    def test_intent_failure_retains_finalized_settlement_and_next_run_repairs(self):
        self.record()
        with patch(f'{PIPELINE}.prepare_ai_usage_billing_intent', side_effect=AIUsageUnavailable('secret')):
            summary = self.run_pipeline()
        self.assertEqual(summary, {
            **EMPTY_SUMMARY, 'scanned': 1, 'settlements_created': 1, 'failed': 1,
        })
        settlement = AppointmentAIUsageSettlement.objects.get()
        self.assertEqual(settlement.status, 'finalized')
        self.assertFalse(AppointmentAIUsageBillingIntent.objects.exists())
        self.assertEqual(self.run_pipeline(), {
            **EMPTY_SUMMARY, 'scanned': 1, 'settlements_existing': 1, 'intents_created': 1,
        })
        self.assertEqual(AppointmentAIUsageSettlement.objects.get().pk, settlement.pk)

    def test_intent_failure_does_not_abort_other_business(self):
        other = self.other_subscription()

        def prepare(settlement):
            if settlement.business_id == self.business.pk:
                raise AIUsageUnavailable('secret')
            return prepare_ai_usage_billing_intent(settlement)

        with patch(f'{PIPELINE}.prepare_ai_usage_billing_intent', side_effect=prepare):
            summary = self.run_pipeline()
        self.assertEqual((summary['settlements_created'], summary['intents_created'], summary['failed']), (2, 1, 1))
        self.assertTrue(AppointmentAIUsageBillingIntent.objects.filter(business_id=other.business_id).exists())

    def test_pending_settlement_recovers_via_s8d(self):
        self.record()
        pending = self.pending()
        self.assertEqual(self.run_pipeline()['settlements_created'], 1)
        self.assertEqual(AppointmentAIUsageSettlement.objects.get().pk, pending.pk)

    def test_explicit_pending_empty_period_survives_later_non_ai_downgrade(self):
        pending = self.pending()
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(plan_code='appointments_pro', usage_tier=None)
        self.assertEqual(self.run_pipeline()['intents_created'], 1)
        self.assertEqual(AppointmentAIUsageSettlement.objects.get().pk, pending.pk)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.get().status, 'void')

    def test_non_ai_plan_without_recorded_history_does_not_invent_empty_period(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(plan_code='appointments_pro', usage_tier=None)
        self.assertEqual(self.run_pipeline(), EMPTY_SUMMARY)
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_post_period_cancellation_does_not_prevent_closure(self):
        self.record()
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='canceled', is_active=False)
        self.assertEqual(self.run_pipeline()['intents_created'], 1)

    def test_post_period_suspension_and_inactive_business_do_not_prevent_closure(self):
        self.record()
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='suspended', is_active=False)
        Business.objects.filter(pk=self.business.pk).update(status='suspended')
        self.assertEqual(self.run_pipeline()['intents_created'], 1)

    def test_empty_period_with_canceled_subscription_still_closes(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='canceled', is_active=False)
        self.assertEqual(self.run_pipeline()['intents_created'], 1)

    def test_upgrade_and_downgrade_do_not_reprice_or_mutate_subscription(self):
        self.tier('ai_1500')
        self.seed_economic_usage(1501)
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            plan_code='appointments_pro', usage_tier=None,
            current_period_start=END, current_period_end=appointments_period_end(END, 'monthly'),
        )
        history = SubscriptionV2.objects.values().get(pk=self.subscription.pk)
        with patch('apps.billing.canonical_pricing.get_usage_tier', side_effect=AssertionError('repricing')):
            summary = self.run_pipeline()
        self.assertEqual(summary['intents_created'], 1)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.get().amount, 200)
        self.assertEqual(SubscriptionV2.objects.values().get(pk=self.subscription.pk), history)

    def test_later_tier_upgrade_does_not_change_recorded_overage(self):
        self.seed_economic_usage(301)
        self.tier('ai_3000')
        with patch('apps.billing.canonical_pricing.get_usage_tier', side_effect=AssertionError('repricing')):
            self.assertEqual(self.run_pipeline()['intents_created'], 1)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.get().amount, 300)

    def test_missing_ledger_is_skipped_without_zero_backfill(self):
        self.seed_usage(1)
        discovery = discover_ai_usage_periods_ready_for_settlement(at=END)
        self.assertEqual((discovery.periods, discovery.skipped), ((), 1))
        self.assertEqual(self.run_pipeline(), {**EMPTY_SUMMARY, 'scanned': 1, 'skipped': 1})
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())
        self.assertFalse(AppointmentAIUsageCharge.objects.exists())

    def test_inconsistent_ledger_is_rejected_by_s8d_without_intent(self):
        session, _ = self.record()
        AppointmentAIUsageCharge.objects.filter(session=session).update(usage_tier='ai_1500')
        self.assertEqual(self.run_pipeline(), {**EMPTY_SUMMARY, 'scanned': 1, 'failed': 1})
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())
        self.assertFalse(AppointmentAIUsageBillingIntent.objects.exists())

    def test_conflicting_subscription_evidence_is_skipped(self):
        self.record()
        self.other_subscription(business=self.business, status='canceled')
        self.assertEqual(self.run_pipeline(), {**EMPTY_SUMMARY, 'scanned': 1, 'skipped': 1})
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_overlapping_periods_are_skipped_not_arbitrarily_closed(self):
        self.record()
        self.other_subscription(
            business=self.business, start=START - timedelta(days=1), end=END - timedelta(days=1),
            status='canceled',
        )
        self.assertEqual(self.run_pipeline(), {**EMPTY_SUMMARY, 'scanned': 2, 'skipped': 2})
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_invalid_anchor_is_skipped_and_other_business_continues(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(billing_cycle='invalid')
        self.other_subscription()
        summary = self.run_pipeline()
        self.assertEqual((summary['scanned'], summary['skipped'], summary['intents_created']), (2, 1, 1))

    def test_no_arbitrary_empty_history_before_or_after_anchor(self):
        summary = self.run_pipeline(END + timedelta(days=800))
        self.assertEqual(summary['settlements_created'], 1)
        settlement = AppointmentAIUsageSettlement.objects.get()
        self.assertEqual((settlement.usage_period_start, settlement.usage_period_end), (START, END))
        self.assertEqual(self.run_pipeline(END + timedelta(days=900)), EMPTY_SUMMARY)

    def test_lost_anchor_does_not_invent_empty_historical_period(self):
        self.pending()
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            current_period_start=END, current_period_end=appointments_period_end(END, 'monthly'),
        )
        self.assertEqual(self.run_pipeline(), {**EMPTY_SUMMARY, 'scanned': 1, 'skipped': 1})
        self.assertEqual(AppointmentAIUsageSettlement.objects.get().status, 'pending')

    def test_recorded_history_survives_lost_anchor(self):
        self.record()
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            current_period_start=None, current_period_end=None, plan_code='appointments_pro', usage_tier=None,
        )
        self.assertEqual(self.run_pipeline()['intents_created'], 1)

    def test_annual_monthly_subperiods_closed_separately_and_future_month_left_open(self):
        self.subscription.billing_cycle = 'yearly'
        self.subscription.current_period_end = appointments_period_end(START, 'yearly')
        self.subscription.save(update_fields=['billing_cycle', 'current_period_end'])
        self.record()
        self.record(END)
        second_end = appointments_period_end(END, 'monthly')
        discovery = discover_ai_usage_periods_ready_for_settlement(at=second_end)
        self.assertEqual(
            [(p.period_start, p.period_end) for p in discovery.periods],
            [(START, END), (END, second_end)],
        )
        summary = self.run_pipeline(second_end)
        self.assertEqual((summary['settlements_created'], summary['intents_created']), (2, 2))
        self.assertEqual(list(
            AppointmentAIUsageSettlement.objects.order_by('usage_period_start').values_list(
                'usage_period_start', 'usage_period_end', 'total_sessions',
            ),
        ), [(START, END, 1), (END, second_end, 1)])
        self.assertEqual(self.run_pipeline(second_end), EMPTY_SUMMARY)

    def test_empty_annual_subperiods_close_separately_without_sessions(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            billing_cycle='yearly', current_period_end=appointments_period_end(START, 'yearly'),
        )
        summary = self.run_pipeline(appointments_period_end(END, 'monthly'))
        self.assertEqual((summary['settlements_created'], summary['intents_created']), (2, 2))
        self.assertEqual(set(AppointmentAIUsageBillingIntent.objects.values_list('status', flat=True)), {'void'})

    def test_annual_short_month_retains_original_anchor_day(self):
        start = START.replace(year=2027, month=1, day=31)
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            billing_cycle='yearly', current_period_start=start,
            current_period_end=appointments_period_end(start, 'yearly'),
        )
        february = start.replace(month=2, day=28)
        march = start.replace(month=3, day=31)
        self.assertEqual(self.run_pipeline(march)['settlements_created'], 2)
        self.assertEqual(list(
            AppointmentAIUsageSettlement.objects.order_by('usage_period_start').values_list(
                'usage_period_start', 'usage_period_end',
            ),
        ), [(start, february), (february, march)])

    @override_settings(AI_USAGE_BILLING_PROVIDER='mercadopago')
    def test_misconfigured_provider_still_never_called_or_resolved(self):
        self.record()
        self.assertEqual(self.run_pipeline()['intents_created'], 1)
        for guard in self.guards.values():
            guard.assert_not_called()
        self.assertFalse(AppointmentAIUsageBillingAttempt.objects.exists())

    def test_pipeline_does_not_read_credentials_or_environment(self):
        original_getattribute = type(settings).__getattribute__

        def guard(instance, name):
            if 'TOKEN' in name.upper():
                raise AssertionError('Access Token read forbidden')
            return original_getattribute(instance, name)

        with (
            patch('os.getenv', side_effect=AssertionError('Environment read forbidden')),
            patch('os.environ.get', side_effect=AssertionError('Environment read forbidden')),
            patch('django.conf.LazySettings.__getattribute__', guard),
        ):
            self.assertEqual(self.run_pipeline()['intents_created'], 1)

    def test_logs_contain_scope_uuids_and_sanitized_summary(self):
        with self.assertLogs(PIPELINE, 'INFO') as logs:
            summary = self.run_pipeline()
        settlement = AppointmentAIUsageSettlement.objects.get()
        intent = AppointmentAIUsageBillingIntent.objects.get()
        output = '\n'.join(logs.output)
        for value in (str(self.business.pk), START.isoformat(), END.isoformat(), str(settlement.pk), str(intent.pk)):
            self.assertIn(value, output)
        self.assertIn('result=prepared', output)
        self.assertIn(str(summary), output)
        self.assertNotIn('token', output.lower())

    def test_integrity_failure_is_sanitized_and_does_not_abort_run(self):
        with (
            patch(f'{PIPELINE}.finalize_ai_usage_settlement', side_effect=IntegrityError('sensitive raw data')),
            self.assertLogs(PIPELINE, 'WARNING') as logs,
        ):
            summary = self.run_pipeline()
        self.assertEqual(summary, {**EMPTY_SUMMARY, 'scanned': 1, 'failed': 1})
        self.assertNotIn('sensitive raw data', str(summary) + str(logs.output))

    def test_unexpected_database_outage_is_not_silently_reported_as_success(self):
        with patch(f'{PIPELINE}.finalize_ai_usage_settlement', side_effect=OperationalError('database unavailable')):
            with self.assertRaises(OperationalError):
                process_due_ai_usage_billing(at=END)

    def test_invalid_time_is_rejected_before_any_write(self):
        with self.assertRaises(AIUsageUnavailable):
            process_due_ai_usage_billing(at=END.replace(tzinfo=None))
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_default_time_evaluated_once_per_run(self):
        with patch(f'{PIPELINE}.timezone') as clock:
            clock.now.return_value = END
            summary = process_due_ai_usage_billing()
        self.assertEqual(summary['intents_created'], 1)
        clock.now.assert_called_once_with()


class AIUsageBillingPipelineTaskTests(TestCase):
    def test_task_delegates_to_service_and_returns_summary(self):
        expected = {**EMPTY_SUMMARY, 'scanned': 1, 'settlements_created': 1, 'intents_created': 1}
        with patch(f'{PIPELINE}.process_due_ai_usage_billing', return_value=expected) as service:
            self.assertEqual(process_due_ai_usage_billing_task.apply().get(), expected)
        service.assert_called_once_with()

    def test_task_has_no_economic_or_provider_logic(self):
        function = ast.parse(textwrap.dedent(inspect.getsource(process_due_ai_usage_billing_task.run))).body[0]
        self.assertEqual(len(function.body), 2)
        self.assertIsInstance(function.body[0], ast.ImportFrom)
        self.assertIsInstance(function.body[1], ast.Return)
        call = function.body[1].value
        self.assertIsInstance(call, ast.Call)
        self.assertEqual(call.func.id, 'process_due_ai_usage_billing')
        self.assertEqual(call.args, [])
        self.assertEqual(call.keywords, [])

    def test_task_name_and_hourly_canonical_schedule(self):
        self.assertEqual(process_due_ai_usage_billing_task.name, 'appointments.process_due_ai_usage_billing')
        entries = [
            item for item in settings.CELERY_BEAT_SCHEDULE.values()
            if item['task'] == process_due_ai_usage_billing_task.name
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['schedule'].minute, {10})
        self.assertEqual(entries[0]['schedule'].hour, set(range(24)))


@skipUnlessDBFeature('has_select_for_update')
class AIUsageBillingPipelineConcurrencyTests(BillingIntentFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def race(self):
        from apps.appointments.services.ai_usage_billing_pipeline import discover_ai_usage_periods_ready_for_settlement
        barrier = threading.Barrier(2)

        def discover(*, at):
            result = discover_ai_usage_periods_ready_for_settlement(at=at)
            barrier.wait(timeout=10)
            return result

        def worker():
            connections.close_all()
            try:
                return process_due_ai_usage_billing(at=END)
            finally:
                connections.close_all()

        with patch(f'{PIPELINE}.discover_ai_usage_periods_ready_for_settlement', side_effect=discover):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(worker) for _ in range(2)]
                return [future.result(timeout=30) for future in futures]

    def test_two_workers_discover_same_due_period_only_one_settlement_and_intent(self):
        self.record()
        summaries = self.race()
        self.assertEqual(sum(run['failed'] for run in summaries), 0)
        self.assertEqual(sum(run['settlements_created'] for run in summaries), 1)
        self.assertEqual(sum(run['settlements_existing'] for run in summaries), 1)
        self.assertEqual(sum(run['intents_created'] for run in summaries), 1)
        self.assertEqual(sum(run['intents_existing'] for run in summaries), 1)
        self.assertEqual(AppointmentAIUsageSettlement.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageSettlementEntry.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)
        self.assertFalse(AppointmentAIUsageBillingAttempt.objects.exists())

    def test_two_workers_repair_same_finalized_settlement_only_one_intent(self):
        self.record()
        settlement = self.close()
        from apps.appointments.services.ai_usage_billing_pipeline import _finalize
        barrier = threading.Barrier(2)

        def finalize(period, *, at):
            # Both workers must capture the same recovery candidate before either prepares.
            barrier.wait(timeout=10)
            return _finalize(period, at=at)

        def worker():
            connections.close_all()
            try:
                return process_due_ai_usage_billing(at=END)
            finally:
                connections.close_all()

        with patch(f'{PIPELINE}._finalize', side_effect=finalize):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(worker) for _ in range(2)]
                summaries = [future.result(timeout=30) for future in futures]
        self.assertEqual(sum(run['failed'] for run in summaries), 0)
        self.assertEqual(sum(run['settlements_existing'] for run in summaries), 2)
        self.assertEqual(sum(run['intents_created'] for run in summaries), 1)
        self.assertEqual(sum(run['intents_existing'] for run in summaries), 1)
        self.assertEqual(AppointmentAIUsageSettlement.objects.get().pk, settlement.pk)
        self.assertEqual(AppointmentAIUsageBillingIntent.objects.count(), 1)
