from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.appointments.models import AppointmentAIUsageCharge, AppointmentAIUsageSession
from apps.appointments.services.ai_usage import (
    AIUsageHardCapReached,
    AIUsageUnavailable,
    resolve_ai_overage_statement,
)
from apps.appointments.tests.test_ai_usage_s8a import AT, END, START
from apps.appointments.tests.test_ai_usage_s8b import AIUsagePolicyFixture
from apps.billing.models import SubscriptionV2
from apps.billing.services.appointments_checkout import ManualContractRequired
from apps.billing.services.appointments_lifecycle import apply_appointments_change
from apps.business.models import Business
from apps.leads.models import Lead
from apps.leads.tests.factories import make_channel, make_state


class AIUsageLedgerFixture(AIUsagePolicyFixture):
    def statement(self, *, start=START, end=END, at=AT):
        return resolve_ai_overage_statement(self.business, start, end, at=at)

    def seed_economic_usage(self, count):
        """Historical fixture; production deliberately does not backfill S8A sessions."""
        self.seed_usage(count)
        policy = self.policy()
        sessions = AppointmentAIUsageSession.objects.order_by('pk')
        AppointmentAIUsageCharge.objects.bulk_create([
            AppointmentAIUsageCharge(
                session=session, business=self.business, subscription=self.subscription,
                usage_period_start=START, usage_period_end=END,
                usage_tier=self.subscription.usage_tier,
                session_ordinal=index, included_sessions_snapshot=policy['included_sessions'],
                classification='included' if index <= policy['included_sessions'] else 'overage',
                unit_price=0 if index <= policy['included_sessions'] else policy['overage_unit_price'],
                amount=0 if index <= policy['included_sessions'] else policy['overage_unit_price'],
            ) for index, session in enumerate(sessions, 1)
        ])


class AIUsageLedgerTests(AIUsageLedgerFixture, TestCase):
    def test_included_session_records_zero_and_complete_snapshot(self):
        session, created = self.record()
        self.assertTrue(created)
        entry = AppointmentAIUsageCharge.objects.get(session=session)
        self.assertEqual(entry.business_id, self.business.pk)
        self.assertEqual(entry.subscription_id, self.subscription.pk)
        self.assertEqual((entry.usage_period_start, entry.usage_period_end), (START, END))
        self.assertEqual(entry.usage_tier, 'ai_300')
        self.assertEqual(entry.included_sessions_snapshot, 300)
        self.assertEqual(entry.session_ordinal, 1)
        self.assertEqual((entry.classification, entry.unit_price, entry.amount), ('included', 0, 0))
        self.assertEqual(entry.currency, 'ARS')
        self.assertIsNotNone(entry.created_at)

    def test_last_included_session_is_still_zero(self):
        self.seed_usage(299)
        session, _ = self.record()
        entry = session.economic_entry
        self.assertEqual(entry.session_ordinal, 300)
        self.assertEqual((entry.classification, entry.amount), ('included', 0))

    def assert_first_extra(self, tier, allowance, price):
        self.tier(tier)
        self.seed_usage(allowance)
        session, _ = self.record()
        entry = session.economic_entry
        self.assertEqual(entry.usage_tier, tier)
        self.assertEqual(entry.session_ordinal, allowance + 1)
        self.assertEqual(entry.included_sessions_snapshot, allowance)
        self.assertEqual((entry.classification, entry.unit_price, entry.amount), ('overage', price, price))

    def test_first_extra_ai_300_snapshots_300(self):
        self.assert_first_extra('ai_300', 300, 300)

    def test_first_extra_ai_1500_snapshots_200(self):
        self.assert_first_extra('ai_1500', 1500, 200)

    def test_first_extra_ai_3000_snapshots_160(self):
        self.assert_first_extra('ai_3000', 3000, 160)

    def test_multiple_extras_statement_sums_exact_rows_without_floats(self):
        self.seed_economic_usage(300)
        for day in range(3):
            self.record(AT + timedelta(days=day))
        statement = self.statement(at=AT + timedelta(days=3))
        self.assertEqual(statement, {
            'usage_tier': 'ai_300', 'usage_tiers': ['ai_300'],
            'period_start': START, 'period_end': END,
            'included_sessions': 300, 'total_sessions': 303, 'overage_sessions': 3,
            'overage_amount': 900, 'currency': 'ARS', 'status': 'open',
            'settlement_ready_amount': 0,
        })
        for key in ('included_sessions', 'total_sessions', 'overage_sessions',
                    'overage_amount', 'settlement_ready_amount'):
            self.assertIs(type(statement[key]), int)

    def test_reused_session_does_not_create_entry(self):
        session, _ = self.record()
        reused, created = self.record(AT + timedelta(hours=23))
        self.assertFalse(created)
        self.assertEqual(session.pk, reused.pk)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_opening_retry_does_not_create_entry_even_after_another_session(self):
        session, _ = self.record(event_id=self.event_id)
        self.record(AT + timedelta(days=2))
        retry, created = self.record(event_id=self.event_id)
        self.assertFalse(created)
        self.assertEqual(session.pk, retry.pk)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 2)

    def test_nonopening_retry_does_not_create_entry(self):
        self.record()
        event = uuid.uuid4()
        self.record(AT + timedelta(hours=1), event_id=event)
        self.record(AT + timedelta(days=2))
        self.assertFalse(self.record(AT + timedelta(hours=1), event_id=event)[1])
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 2)

    def test_last_allowed_session_gets_entry_blocked_session_does_not(self):
        self.seed_usage(549)
        session, _ = self.record()
        self.assertEqual(session.economic_entry.amount, 300)
        with self.assertRaises(AIUsageHardCapReached):
            self.record(session.expires_at)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 550)

    def test_pre_authorization_has_no_economic_side_effect(self):
        self.policy()
        self.allowed()
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_failed_creation_rolls_back_session_and_ledger(self):
        with patch.object(AppointmentAIUsageCharge.objects, 'create', side_effect=IntegrityError('ledger')):
            with self.assertRaises(IntegrityError):
                self.record()
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_invalid_context_does_not_create_entry(self):
        with self.assertRaises(AIUsageUnavailable):
            self.record(conversation_id='missing')
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_custom_never_invents_economic_terms(self):
        self.tier('custom')
        with self.assertRaises(ManualContractRequired):
            self.record()
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)
        self.assertEqual(self.statement()['overage_amount'], 0)
        self.assertIsNone(self.statement()['usage_tier'])

    def test_database_uniqueness_prevents_second_entry_for_session(self):
        session, _ = self.record()
        values = AppointmentAIUsageCharge.objects.filter(session=session).values().get()
        values.pop('id')
        values.pop('created_at')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentAIUsageCharge.objects.create(**values)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_database_rejects_invalid_economics(self):
        session, _ = self.record()
        for values in (
            {'amount': 1}, {'unit_price': 1}, {'classification': 'overage'},
            {'classification': 'unknown'}, {'session_ordinal': 0},
            {'usage_tier': 'custom'}, {'currency': 'USD'},
            {'usage_period_end': START},
        ):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                AppointmentAIUsageCharge.objects.filter(session=session).update(**values)

    def test_economic_evidence_protects_session_from_deletion(self):
        session, _ = self.record()
        with self.assertRaises(ProtectedError):
            session.delete()

    def test_upgrade_preserves_old_extra_and_new_session_uses_new_allowance(self):
        self.seed_economic_usage(300)
        old, _ = self.record()
        history = AppointmentAIUsageCharge.objects.filter(session=old).values().get()
        change = self.change('ai_1500')
        self.assertTrue(apply_appointments_change(change, payment_id='s8c-upgrade', at=AT))
        new, _ = self.record(AT + timedelta(days=1))
        self.assertEqual(new.economic_entry.usage_tier, 'ai_1500')
        self.assertEqual(new.economic_entry.included_sessions_snapshot, 1500)
        self.assertEqual(new.economic_entry.amount, 0)
        self.assertEqual(AppointmentAIUsageCharge.objects.filter(session=old).values().get(), history)
        statement = self.statement(at=END)
        self.assertIsNone(statement['usage_tier'])
        self.assertEqual(statement['usage_tiers'], ['ai_1500', 'ai_300'])
        self.assertEqual(statement['overage_amount'], 300)
        self.assertEqual(statement['settlement_ready_amount'], 300)
        self.assertEqual(self.policy()['overage_amount'], 0)

    def test_post_upgrade_extra_uses_new_price(self):
        self.seed_usage(300)
        old, _ = self.record()
        change = self.change('ai_1500')
        self.assertTrue(apply_appointments_change(change, payment_id='s8c-price-upgrade', at=AT))
        self.seed_usage(1199)
        new, _ = self.record(AT + timedelta(days=1))
        self.assertEqual(new.economic_entry.amount, 200)
        self.assertEqual(new.economic_entry.usage_tier, 'ai_1500')
        old.economic_entry.refresh_from_db()
        self.assertEqual(old.economic_entry.amount, 300)

    def test_applied_downgrade_preserves_history_and_new_sessions_use_new_terms(self):
        self.tier('ai_1500')
        self.seed_usage(1500)
        old, _ = self.record()
        history = AppointmentAIUsageCharge.objects.filter(session=old).values().get()
        change = self.change('ai_300')
        self.assertEqual(change.status, 'scheduled')
        self.assertEqual(self.policy()['usage_tier'], 'ai_1500')
        self.renewal()
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.usage_tier, 'ai_300')
        new, _ = self.record(END)
        self.assertEqual(new.economic_entry.usage_tier, 'ai_300')
        self.assertEqual(new.economic_entry.amount, 0)
        self.seed_usage(299, start=END, end=self.subscription.current_period_end)
        extra, _ = self.record(END + timedelta(days=1))
        self.assertEqual(extra.economic_entry.amount, 300)
        self.assertEqual(AppointmentAIUsageCharge.objects.filter(session=old).values().get(), history)

    def test_same_period_applied_downgrade_does_not_reclassify_included_history(self):
        self.tier('ai_1500')
        self.seed_economic_usage(320)
        history = list(AppointmentAIUsageCharge.objects.order_by('pk').values())
        change = self.change('ai_300')
        self.assertTrue(apply_appointments_change(change, at=AT))
        session, _ = self.record()
        self.assertEqual(session.economic_entry.session_ordinal, 321)
        self.assertEqual(session.economic_entry.amount, 300)
        self.assertEqual(
            list(AppointmentAIUsageCharge.objects.exclude(session=session).order_by('pk').values()), history,
        )
        statement = self.statement()
        self.assertEqual(statement['included_sessions'], 320)
        self.assertEqual(statement['overage_sessions'], 1)
        self.assertEqual(statement['overage_amount'], 300)
        self.assertEqual(self.policy()['overage_amount'], 6300)

    def test_cross_month_session_stays_in_start_period(self):
        self.seed_economic_usage(300)
        session, _ = self.record(END - timedelta(minutes=10))
        self.renewal()
        reused, created = self.record(END + timedelta(minutes=10))
        self.assertFalse(created)
        self.assertEqual(reused.pk, session.pk)
        self.assertEqual(session.economic_entry.usage_period_start, START)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 301)
        self.assertEqual(self.statement(at=END)['overage_amount'], 300)
        self.assertEqual(
            self.statement(start=END, end=self.subscription.current_period_end, at=END)['total_sessions'], 0,
        )

    def test_statement_is_eligible_exactly_at_end_and_never_paid(self):
        self.seed_economic_usage(300)
        self.record()
        self.assertEqual(self.statement(at=END - timedelta(microseconds=1))['status'], 'open')
        statement = self.statement(at=END)
        self.assertEqual(statement['status'], 'eligible_for_settlement')
        self.assertEqual(statement['settlement_ready_amount'], 300)
        self.assertEqual(self.statement(at=END + timedelta(days=60)), statement)

    def test_statement_without_overage_returns_integer_zero(self):
        self.record()
        self.assertEqual(self.statement()['overage_amount'], 0)
        self.assertEqual(self.statement()['included_sessions'], 1)
        self.assertEqual(self.statement()['overage_sessions'], 0)

    def test_empty_statement_does_not_invent_tier_or_allowance(self):
        statement = self.statement(at=END)
        self.assertIsNone(statement['usage_tier'])
        self.assertEqual(statement['usage_tiers'], [])
        self.assertEqual(statement['total_sessions'], 0)
        self.assertEqual(statement['overage_amount'], 0)
        self.assertIs(type(statement['overage_amount']), int)

    def test_historical_statement_does_not_need_current_subscription_access_or_price(self):
        self.seed_economic_usage(300)
        self.record()
        self.tier('custom')
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='canceled')
        with patch('apps.billing.canonical_pricing.get_usage_tier', side_effect=AssertionError('repricing')):
            self.assertEqual(self.statement(at=END)['overage_amount'], 300)

    def test_statement_refuses_missing_evidence_instead_of_silent_underbilling(self):
        self.seed_usage(1)
        with self.assertRaisesMessage(AIUsageUnavailable, 'without economic evidence'):
            self.statement()
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)

    def test_statement_refuses_inconsistent_session_snapshot(self):
        session, _ = self.record()
        AppointmentAIUsageCharge.objects.filter(session=session).update(usage_tier='ai_1500')
        with self.assertRaisesMessage(AIUsageUnavailable, 'inconsistent economic evidence'):
            self.statement()

    def test_statement_requires_aware_positive_period(self):
        for start, end in ((END, START), (START, START), (START.replace(tzinfo=None), END)):
            with self.subTest(start=start, end=end), self.assertRaises(AIUsageUnavailable):
                self.statement(start=start, end=end)

    def test_businesses_do_not_share_ledger_or_statements(self):
        self.record(event_id=self.event_id)
        other = Business.objects.create(name='S8C other', slug='s8c-other', status='active')
        SubscriptionV2.objects.create(
            business=other, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_1500', billing_cycle='monthly', provider='manual',
            external_reference=f'S8C-{uuid.uuid4()}', status='active',
            current_period_start=START, current_period_end=END,
        )
        channel = make_channel(self.channel.agent_instance, other, phone_number_id='9876543210')
        state = make_state(
            Lead.objects.create(business=other), channel,
            external_conversation_id=self.state.external_conversation_id,
        )
        session, _ = self.record(
            business=other, conversation_id=state.external_conversation_id, event_id=self.event_id,
        )
        self.assertEqual(session.economic_entry.business_id, other.pk)
        self.assertEqual(session.economic_entry.usage_tier, 'ai_1500')
        with self.assertRaises(AIUsageUnavailable):
            self.record(business=other, conversation_id='unknown-conversation')
        statement = resolve_ai_overage_statement(other, START, END, at=AT)
        self.assertEqual(statement['total_sessions'], 1)
        self.assertEqual(statement['usage_tier'], 'ai_1500')
        self.assertEqual(self.statement()['total_sessions'], 1)
        self.assertEqual(self.statement()['usage_tier'], 'ai_300')
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 2)


@skipUnlessDBFeature('has_select_for_update')
class AIUsageLedgerConcurrencyTests(AIUsageLedgerFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def race(self, *, same_event=False, distinct_conversations=False, last_slot=False):
        if last_slot:
            self.seed_usage(549)
        else:
            self.seed_usage(300)
        other = make_state(Lead.objects.create(business=self.business), self.channel)
        barrier = threading.Barrier(2)
        event_id = uuid.uuid4()

        def worker(conversation):
            connections.close_all()
            try:
                business = Business.objects.get(pk=self.business.pk)
                barrier.wait(timeout=10)
                try:
                    session, created = self.record(
                        business=business, conversation_id=conversation,
                        event_id=event_id if same_event else uuid.uuid4(),
                    )
                    return session.pk, created
                except AIUsageHardCapReached:
                    return None, False
            finally:
                connections.close_all()

        conversations = [
            self.state.external_conversation_id,
            other.external_conversation_id if distinct_conversations else self.state.external_conversation_id,
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, conversation) for conversation in conversations]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_retry_creates_one_economic_entry(self):
        results = self.race(same_event=True)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({pk for pk, _ in results}), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.get().amount, 300)

    def test_concurrent_interactions_reuse_one_session_and_entry(self):
        results = self.race()
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_concurrent_distinct_sessions_have_distinct_ordinals(self):
        results = self.race(distinct_conversations=True)
        self.assertEqual(sum(created for _, created in results), 2)
        self.assertEqual(
            set(AppointmentAIUsageCharge.objects.values_list('session_ordinal', flat=True)), {301, 302},
        )
        self.assertEqual(sum(AppointmentAIUsageCharge.objects.values_list('amount', flat=True)), 600)

    def test_concurrent_last_slot_creates_one_entry(self):
        results = self.race(distinct_conversations=True, last_slot=True)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.get().session_ordinal, 550)
