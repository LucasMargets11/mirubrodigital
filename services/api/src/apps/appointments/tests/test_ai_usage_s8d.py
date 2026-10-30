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
    AppointmentAIUsageCharge,
    AppointmentAIUsageSession,
    AppointmentAIUsageSettlement,
    AppointmentAIUsageSettlementEntry,
)
from apps.appointments.services.ai_usage import AIUsageUnavailable
from apps.appointments.services.ai_usage_settlement import finalize_ai_usage_settlement
from apps.appointments.tests.test_ai_usage_s8a import AT, END, START
from apps.appointments.tests.test_ai_usage_s8c import AIUsageLedgerFixture
from apps.billing.models import SubscriptionV2
from apps.billing.services.appointments_lifecycle import apply_appointments_change
from apps.business.models import Business


class AIUsageSettlementFixture(AIUsageLedgerFixture):
    def close(self, *, start=START, end=END, at=END, business=None, subscription=None):
        return finalize_ai_usage_settlement(
            business=business or self.business, subscription=subscription or self.subscription,
            period_start=start, period_end=end, at=at,
        )

    def pending(self, **overrides):
        values = dict(
            business=self.business, subscription=self.subscription,
            usage_period_start=START, usage_period_end=END, total_sessions=0,
            included_sessions_snapshot=0, overage_sessions=0, overage_amount=0,
            terms_snapshot=[],
        )
        values.update(overrides)
        return AppointmentAIUsageSettlement.objects.create(**values)


class AIUsageSettlementTests(AIUsageSettlementFixture, TestCase):
    def test_open_period_fails_without_creating_pending_or_membership(self):
        self.record()
        with self.assertRaisesMessage(AIUsageUnavailable, 'ended positive usage period'):
            self.close(at=END - timedelta(microseconds=1))
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())
        self.assertFalse(AppointmentAIUsageSettlementEntry.objects.exists())

    def test_exact_end_finalizes_with_explicit_reference_and_time(self):
        session, _ = self.record()
        settlement = self.close()
        self.assertEqual(settlement.status, 'finalized')
        self.assertEqual(settlement.finalized_at, END)
        self.assertIsInstance(settlement.pk, uuid.UUID)
        self.assertIsNotNone(settlement.created_at)
        self.assertEqual((settlement.usage_period_start, settlement.usage_period_end), (START, END))
        self.assertEqual(list(settlement.charges.all()), [session.economic_entry])

    def test_no_overage_is_auditable_zero(self):
        self.record()
        settlement = self.close()
        self.assertEqual(
            (settlement.total_sessions, settlement.included_sessions_snapshot,
             settlement.overage_sessions, settlement.overage_amount),
            (1, 1, 0, 0),
        )
        self.assertEqual(settlement.terms_snapshot[0]['included_sessions_snapshot'], 300)

    def test_empty_period_with_persisted_anchor_closes_zero(self):
        settlement = self.close()
        self.assertEqual(settlement.total_sessions, 0)
        self.assertEqual(settlement.overage_amount, 0)
        self.assertEqual(settlement.terms_snapshot, [])
        self.assertEqual(self.close().pk, settlement.pk)

    def test_empty_arbitrary_period_is_not_invented(self):
        with self.assertRaises(AIUsageUnavailable):
            self.close(start=START + timedelta(days=1))
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_empty_anchored_period_can_close_after_non_ai_downgrade_and_cancellation(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            plan_code='appointments_pro', usage_tier=None, status='canceled', is_active=False,
        )
        self.assertEqual(self.close().overage_amount, 0)

    def assert_tier_total(self, tier, included, price):
        self.tier(tier)
        self.seed_economic_usage(included)
        for day in range(3):
            self.record(AT + timedelta(days=day))
        statement = self.statement(at=END)
        settlement = self.close()
        self.assertEqual(settlement.total_sessions, statement['total_sessions'])
        self.assertEqual(settlement.included_sessions_snapshot, statement['included_sessions'])
        self.assertEqual(settlement.overage_sessions, 3)
        self.assertEqual(settlement.overage_amount, 3 * price)
        self.assertEqual(settlement.charges.count(), included + 3)
        extras = [term for term in settlement.terms_snapshot if term['classification'] == 'overage']
        self.assertEqual([term['unit_price'] for term in extras], [price] * 3)
        settlement.refresh_from_db()
        self.assertEqual(settlement.currency, 'ARS')
        for field in ('total_sessions', 'included_sessions_snapshot', 'overage_sessions', 'overage_amount'):
            self.assertIs(type(getattr(settlement, field)), int)
        for term in settlement.terms_snapshot:
            for field in ('unit_price', 'amount', 'session_ordinal', 'included_sessions_snapshot'):
                self.assertIs(type(term[field]), int)
            self.assertEqual(term['currency'], 'ARS')

    def test_ai_300_exact_integer_ars(self):
        self.assert_tier_total('ai_300', 300, 300)

    def test_ai_1500_exact_integer_ars(self):
        self.assert_tier_total('ai_1500', 1500, 200)

    def test_ai_3000_exact_integer_ars(self):
        self.assert_tier_total('ai_3000', 3000, 160)

    def test_mixed_tiers_preserve_historical_amount_and_terms(self):
        self.seed_economic_usage(300)
        self.record()
        change = self.change('ai_1500')
        self.assertTrue(apply_appointments_change(change, payment_id='s8d-upgrade', at=AT))
        self.record(AT + timedelta(days=1))
        settlement = self.close()
        self.assertEqual(settlement.total_sessions, 302)
        self.assertEqual(settlement.included_sessions_snapshot, 301)
        self.assertEqual(settlement.overage_sessions, 1)
        self.assertEqual(settlement.overage_amount, 300)
        self.assertEqual({term['usage_tier'] for term in settlement.terms_snapshot}, {'ai_300', 'ai_1500'})
        self.assertEqual(
            {term['included_sessions_snapshot'] for term in settlement.terms_snapshot}, {300, 1500},
        )

    def test_no_current_pricing_read_before_or_after_closure(self):
        self.seed_economic_usage(300)
        self.record()
        with patch('apps.billing.canonical_pricing.get_usage_tier', side_effect=AssertionError('repricing')):
            settlement = self.close()
            frozen = AppointmentAIUsageSettlement.objects.values().get(pk=settlement.pk)
            self.tier('custom')
            self.assertEqual(self.close(at=END + timedelta(days=365)).pk, settlement.pk)
            self.assertEqual(AppointmentAIUsageSettlement.objects.values().get(pk=settlement.pk), frozen)
            self.assertEqual(self.statement(at=END)['overage_amount'], 300)

    def test_repeat_reuses_same_settlement_and_memberships(self):
        self.record()
        settlement = self.close()
        memberships = list(settlement.entries.values())
        with patch(
            'apps.appointments.services.ai_usage_settlement.resolve_ai_overage_statement',
            side_effect=AssertionError('Finalized history must not be recalculated.'),
        ):
            self.assertEqual(self.close(at=END + timedelta(days=1)).pk, settlement.pk)
        self.assertEqual(AppointmentAIUsageSettlement.objects.count(), 1)
        self.assertEqual(list(settlement.entries.values()), memberships)

    def test_database_unique_period_even_for_pending_rows(self):
        self.pending()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.pending()

    def test_charge_can_only_be_assigned_once(self):
        session, _ = self.record()
        pending = self.pending()
        AppointmentAIUsageSettlementEntry.objects.create(settlement=pending, charge=session.economic_entry)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentAIUsageSettlementEntry.objects.create(
                settlement=pending, charge=session.economic_entry,
            )
        self.assertEqual(AppointmentAIUsageSettlementEntry.objects.count(), 1)

    def test_charge_cannot_be_linked_to_incompatible_period(self):
        session, _ = self.record()
        pending = self.pending(usage_period_start=START - timedelta(days=1))
        with self.assertRaisesMessage(IntegrityError, 'scope mismatch'), transaction.atomic():
            AppointmentAIUsageSettlementEntry.objects.create(
                settlement=pending, charge=session.economic_entry,
            )

    def test_charge_cannot_be_reassigned_to_second_settlement(self):
        session, _ = self.record()
        settlement = self.close()
        pending = self.pending(usage_period_start=START - timedelta(days=1))
        with self.assertRaisesMessage(IntegrityError, 'reassigned'), transaction.atomic():
            settlement.entries.filter(charge=session.economic_entry).update(settlement=pending)
        self.assertEqual(session.economic_entry.settlement_entry.settlement_id, settlement.pk)

    def test_recover_pending_settlement_atomically(self):
        self.record()
        pending = self.pending()
        settlement = self.close()
        self.assertEqual(settlement.pk, pending.pk)
        self.assertEqual(settlement.status, 'finalized')
        self.assertEqual(settlement.charges.count(), 1)

    def test_post_period_cancellation_does_not_prevent_closure(self):
        self.seed_economic_usage(301)
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='canceled', is_active=False)
        self.assertEqual(self.close().overage_amount, 300)

    def test_post_period_suspension_and_inactive_business_do_not_prevent_closure(self):
        self.seed_economic_usage(301)
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='suspended', is_active=False)
        Business.objects.filter(pk=self.business.pk).update(status='suspended')
        self.assertEqual(self.close().overage_amount, 300)

    def test_post_period_applied_downgrade_and_renewed_anchor_preserve_totals(self):
        self.tier('ai_1500')
        self.seed_economic_usage(1501)
        self.change('ai_300')
        self.renewal()
        self.assertEqual(self.subscription.usage_tier, 'ai_300')
        self.assertGreater(self.subscription.current_period_start, START)
        self.assertEqual(self.close().overage_amount, 200)

    def test_later_non_ai_plan_does_not_reinterpret_recorded_period(self):
        self.seed_economic_usage(301)
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            plan_code='appointments_pro', usage_tier=None,
        )
        self.assertEqual(self.close().overage_amount, 300)

    def test_missing_ledger_fails_closed_without_backfill(self):
        self.seed_usage(1)
        with self.assertRaisesMessage(AIUsageUnavailable, 'without economic evidence'):
            self.close()
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())
        self.assertFalse(AppointmentAIUsageSettlementEntry.objects.exists())
        self.assertFalse(AppointmentAIUsageCharge.objects.exists())

    def test_inconsistent_ledger_fails_closed(self):
        session, _ = self.record()
        AppointmentAIUsageCharge.objects.filter(session=session).update(usage_tier='ai_1500')
        with self.assertRaisesMessage(AIUsageUnavailable, 'inconsistent economic evidence'):
            self.close()
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_invalid_times_are_rejected(self):
        for overrides in (
            {'start': END}, {'end': START}, {'at': END.replace(tzinfo=None)},
            {'start': START.replace(tzinfo=None)}, {'end': END.replace(tzinfo=None)},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(AIUsageUnavailable):
                self.close(**overrides)
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_other_business_cannot_close_subscription(self):
        other = Business.objects.create(name='S8D other', slug='s8d-other', status='active')
        with self.assertRaisesMessage(AIUsageUnavailable, 'another business'):
            self.close(business=other)
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())

    def test_businesses_keep_separate_settlements_and_evidence(self):
        self.seed_economic_usage(301)
        own = self.close()
        other = Business.objects.create(name='S8D other', slug='s8d-other', status='active')
        subscription = SubscriptionV2.objects.create(
            business=other, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_3000', billing_cycle='monthly', status='active',
            current_period_start=START, current_period_end=END,
        )
        separate = self.close(business=other, subscription=subscription)
        self.assertNotEqual(separate.pk, own.pk)
        self.assertEqual(separate.overage_amount, 0)
        self.assertEqual(separate.charges.count(), 0)
        self.assertEqual(own.charges.count(), 301)

    def test_wrong_subscription_for_recorded_period_is_rejected(self):
        self.record()
        subscription = SubscriptionV2.objects.create(
            business=self.business, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_3000', billing_cycle='monthly', status='canceled',
            current_period_start=START, current_period_end=END,
        )
        with self.assertRaisesMessage(AIUsageUnavailable, 'conflicting subscription'):
            self.close(subscription=subscription)

    def test_noncalendar_anchor_closes_only_recorded_period(self):
        self.seed_economic_usage(301)
        settlement = self.close()
        self.assertEqual(settlement.usage_period_start.day, 12)
        self.assertEqual(settlement.usage_period_start.hour, 14)
        self.assertEqual(settlement.usage_period_end, END)
        self.assertEqual(settlement.overage_amount, 300)
        with self.assertRaises(AIUsageUnavailable):
            self.close(start=START.replace(day=1), end=END.replace(day=1))

    def test_annual_subscription_closes_independent_monthly_subperiods(self):
        self.subscription.billing_cycle = 'yearly'
        self.subscription.current_period_end = START.replace(year=START.year + 1)
        self.subscription.save(update_fields=['billing_cycle', 'current_period_end'])
        first_session, _ = self.record()
        second_session, _ = self.record(END)
        second_end = END.replace(month=12)
        first = self.close()
        with self.assertRaises(AIUsageUnavailable):
            self.close(start=END, end=second_end, at=second_end - timedelta(microseconds=1))
        second = self.close(start=END, end=second_end, at=second_end)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(list(first.charges.all()), [first_session.economic_entry])
        self.assertEqual(list(second.charges.all()), [second_session.economic_entry])
        self.assertEqual((first.total_sessions, second.total_sessions), (1, 1))

    def test_failure_during_membership_creation_rolls_back_everything(self):
        self.record()
        with patch.object(
            AppointmentAIUsageSettlementEntry.objects, 'bulk_create',
            side_effect=IntegrityError('membership failure'),
        ):
            with self.assertRaises(IntegrityError):
                self.close()
        self.assertFalse(AppointmentAIUsageSettlement.objects.exists())
        self.assertFalse(AppointmentAIUsageSettlementEntry.objects.exists())
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_finalized_settlement_is_immutable_in_database(self):
        self.record()
        settlement = self.close()
        for values in (
            {'overage_amount': 1}, {'terms_snapshot': []}, {'status': 'pending', 'finalized_at': None},
            {'currency': 'USD'}, {'finalized_at': END + timedelta(days=1)},
        ):
            with self.subTest(values=values), self.assertRaisesMessage(
                IntegrityError, 'immutable',
            ), transaction.atomic():
                AppointmentAIUsageSettlement.objects.filter(pk=settlement.pk).update(**values)

    def test_finalized_membership_and_economic_evidence_are_immutable(self):
        session, _ = self.record()
        settlement = self.close()
        for queryset, operation in (
            (settlement.entries.all(), 'delete'),
            (AppointmentAIUsageCharge.objects.filter(session=session), 'update'),
            (AppointmentAIUsageSession.objects.filter(pk=session.pk), 'update'),
        ):
            with self.subTest(model=queryset.model), self.assertRaisesMessage(
                IntegrityError, 'immutable',
            ), transaction.atomic():
                if operation == 'delete':
                    queryset.delete()
                else:
                    queryset.update(usage_tier='ai_1500')

    def test_late_historical_session_is_rejected_not_silently_unsettled(self):
        self.record()
        settlement = self.close()
        with self.assertRaisesMessage(IntegrityError, 'already finalized'), transaction.atomic():
            self.record(AT + timedelta(days=2))
        self.assertEqual(AppointmentAIUsageSession.objects.count(), settlement.total_sessions)
        self.assertEqual(self.statement(at=END)['total_sessions'], settlement.total_sessions)

    def test_closure_does_not_block_next_period_or_change_subscription_economics(self):
        self.record()
        history = SubscriptionV2.objects.values().get(pk=self.subscription.pk)
        self.close()
        self.assertEqual(SubscriptionV2.objects.values().get(pk=self.subscription.pk), history)
        self.renewal()
        session, created = self.record(END)
        self.assertTrue(created)
        self.assertEqual(session.economic_entry.usage_period_start, END)
        self.assertFalse(AppointmentAIUsageSettlementEntry.objects.filter(charge__session=session).exists())

    def test_finalized_zero_settlement_cannot_be_deleted(self):
        settlement = self.close()
        with self.assertRaisesMessage(IntegrityError, 'immutable'), transaction.atomic():
            AppointmentAIUsageSettlement.objects.filter(pk=settlement.pk).delete()

    def test_late_charge_insert_is_rejected_in_database(self):
        session, _ = self.record()
        self.close()
        values = AppointmentAIUsageCharge.objects.filter(session=session).values().get()
        values['id'] = uuid.uuid4()
        with self.assertRaisesMessage(IntegrityError, 'already finalized'), transaction.atomic():
            AppointmentAIUsageCharge.objects.create(**values)

    def test_finalization_database_guard_rejects_missing_membership(self):
        self.record()
        pending = self.pending(total_sessions=1, included_sessions_snapshot=1)
        with self.assertRaisesMessage(IntegrityError, 'Incomplete'), transaction.atomic():
            AppointmentAIUsageSettlement.objects.filter(pk=pending.pk).update(
                status='finalized', finalized_at=END,
            )


@skipUnlessDBFeature('has_select_for_update')
class AIUsageSettlementConcurrencyTests(AIUsageSettlementFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def race(self, *, writer=False):
        self.seed_economic_usage(301)
        barrier = threading.Barrier(2)

        def worker(write):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                if write:
                    try:
                        self.record(AT + timedelta(days=2))
                        return 'recorded'
                    except IntegrityError as exc:
                        if 'already finalized' not in str(exc):
                            raise
                        return 'closed'
                return self.close().pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, False), pool.submit(worker, writer)]
            return [future.result(timeout=30) for future in futures]

    def test_two_closers_produce_one_settlement_and_one_membership_per_charge(self):
        results = self.race()
        self.assertEqual(results[0], results[1])
        self.assertEqual(AppointmentAIUsageSettlement.objects.count(), 1)
        settlement = AppointmentAIUsageSettlement.objects.get()
        self.assertEqual(settlement.overage_amount, 300)
        self.assertEqual(settlement.entries.count(), 301)
        self.assertEqual(AppointmentAIUsageSettlementEntry.objects.count(), 301)

    def test_closer_serializes_with_historical_session_writer(self):
        _, outcome = self.race(writer=True)
        settlement = AppointmentAIUsageSettlement.objects.get()
        count = 302 if outcome == 'recorded' else 301
        self.assertEqual(settlement.total_sessions, count)
        self.assertEqual(settlement.entries.count(), count)
        self.assertEqual(settlement.overage_amount, 600 if outcome == 'recorded' else 300)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), count)
