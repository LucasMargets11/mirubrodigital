from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.appointments.models import AppointmentAIUsageSession
from apps.appointments.services.ai_usage import (
    AIUsageHardCapReached,
    AIUsageUnavailable,
    can_start_ai_usage_session,
    resolve_ai_usage_policy,
)
from apps.appointments.tests.test_ai_usage_s8a import AIUsageFixture, AT, END, START
from apps.billing import canonical_pricing
from apps.billing.models import SubscriptionV2
from apps.billing.services.appointments_checkout import ManualContractRequired
from apps.billing.services.appointments_lifecycle import (
    apply_appointments_change,
    record_appointments_payment_failure,
)
from apps.business.models import Business
from apps.leads.models import Lead
from apps.leads.tests.factories import make_state


class AIUsagePolicyFixture(AIUsageFixture):
    def seed_usage(self, count, *, start=START, end=END):
        AppointmentAIUsageSession.objects.bulk_create([
            AppointmentAIUsageSession(
                business=self.business, subscription=self.subscription,
                external_conversation_id=f's8b-{uuid.uuid4().hex}',
                opening_interaction_id=uuid.uuid4(),
                started_at=start, expires_at=start + timedelta(hours=24),
                usage_period_start=start, usage_period_end=end,
                usage_tier=self.subscription.usage_tier,
            ) for _ in range(count)
        ])

    def policy(self, at=AT):
        return resolve_ai_usage_policy(self.business, at=at)

    def allowed(self, at=AT):
        return can_start_ai_usage_session(self.business, at=at)


class AIUsagePolicyTests(AIUsagePolicyFixture, TestCase):
    def test_ai_300_within_allowance_is_included(self):
        self.seed_usage(299)
        self.assertTrue(self.allowed())
        self.assertTrue(self.record()[1])
        policy = self.policy()
        self.assertEqual(policy['used_sessions'], 300)
        self.assertEqual(policy['overage_sessions'], 0)
        self.assertEqual(policy['overage_amount'], 0)

    def test_session_301_is_first_overage(self):
        self.seed_usage(300)
        self.assertTrue(self.allowed())
        self.assertTrue(self.record()[1])
        self.assertEqual(self.policy()['overage_sessions'], 1)
        self.assertEqual(self.policy()['overage_amount'], 300)

    def test_policy_exact_shape_and_integer_ars(self):
        self.seed_usage(320)
        policy = self.policy()
        self.assertEqual(policy, {
            'usage_tier': 'ai_300',
            'included_sessions': 300,
            'used_sessions': 320,
            'overage_sessions': 20,
            'overage_unit_price': 300,
            'overage_amount': 6000,
            'hard_cap_amount': 75000,
            'max_overage_sessions': 250,
            'max_total_sessions': 550,
            'can_start_new_session': True,
            'blocked_reason': None,
        })
        for key in (
            'included_sessions', 'used_sessions', 'overage_sessions',
            'overage_unit_price', 'overage_amount', 'hard_cap_amount',
            'max_overage_sessions', 'max_total_sessions',
        ):
            self.assertIs(type(policy[key]), int, key)

    def test_ai_1500_allowance_and_overage(self):
        self.tier('ai_1500')
        self.seed_usage(1500)
        self.assertEqual(self.policy()['overage_amount'], 0)
        self.record()
        policy = self.policy()
        self.assertEqual(policy['included_sessions'], 1500)
        self.assertEqual(policy['overage_sessions'], 1)
        self.assertEqual(policy['overage_unit_price'], 200)
        self.assertEqual(policy['overage_amount'], 200)
        self.assertEqual(policy['hard_cap_amount'], 137500)
        self.assertEqual(policy['max_overage_sessions'], 687)
        self.assertEqual(policy['max_total_sessions'], 2187)
        self.assertTrue(policy['can_start_new_session'])

    def test_ai_3000_allowance_and_overage(self):
        self.tier('ai_3000')
        self.seed_usage(3000)
        self.assertEqual(self.policy()['overage_amount'], 0)
        self.record()
        policy = self.policy()
        self.assertEqual(policy['included_sessions'], 3000)
        self.assertEqual(policy['overage_sessions'], 1)
        self.assertEqual(policy['overage_unit_price'], 160)
        self.assertEqual(policy['overage_amount'], 160)
        self.assertEqual(policy['hard_cap_amount'], 192500)
        self.assertEqual(policy['max_overage_sessions'], 1203)
        self.assertEqual(policy['max_total_sessions'], 4203)
        self.assertTrue(policy['can_start_new_session'])

    def assert_last_slot(self, maximum, amount, cap):
        self.seed_usage(maximum - 1)
        self.assertTrue(self.allowed())
        self.assertTrue(self.record()[1])
        policy = self.policy()
        self.assertEqual(policy['used_sessions'], maximum)
        self.assertEqual(policy['overage_amount'], amount)
        self.assertEqual(policy['hard_cap_amount'], cap)
        self.assertFalse(policy['can_start_new_session'])
        self.assertEqual(policy['blocked_reason'], 'hard_cap_reached')
        with self.assertRaises(AIUsageHardCapReached):
            self.record(AT + timedelta(hours=24))
        self.assertEqual(self.usage()['used'], maximum)

    def test_exact_ai_300_cap_session_is_permitted_and_next_is_blocked(self):
        self.assert_last_slot(550, 75000, 75000)

    def test_ai_1500_cap_uses_floor_not_rounding_even_with_unspent_remainder(self):
        self.tier('ai_1500')
        self.assert_last_slot(2187, 137400, 137500)

    def test_ai_3000_cap_uses_floor_not_rounding_even_with_unspent_remainder(self):
        self.tier('ai_3000')
        self.assert_last_slot(4203, 192480, 192500)

    def test_active_session_and_opening_retry_survive_exhausted_cap(self):
        self.seed_usage(549)
        session, _ = self.record(event_id=self.event_id)
        self.assertFalse(self.allowed())
        reused, created = self.record(AT + timedelta(hours=23))
        self.assertFalse(created)
        self.assertEqual(reused.pk, session.pk)
        self.assertEqual(reused.expires_at, session.expires_at)
        retry, created = self.record(event_id=self.event_id)
        self.assertFalse(created)
        self.assertEqual(retry.pk, session.pk)
        self.assertEqual(self.usage()['used'], 550)

    def test_expired_session_is_blocked_at_exact_24h_when_cap_exhausted(self):
        self.seed_usage(549)
        session, _ = self.record()
        with self.assertRaises(AIUsageHardCapReached):
            self.record(session.expires_at)
        self.assertEqual(self.usage()['used'], 550)

    def test_other_conversation_cannot_reuse_active_session_at_cap(self):
        self.seed_usage(549)
        self.record()
        other = make_state(Lead.objects.create(business=self.business), self.channel)
        with self.assertRaises(AIUsageHardCapReached):
            self.record(conversation_id=other.external_conversation_id)
        self.assertEqual(self.usage()['used'], 550)

    def test_upgrade_immediately_increases_capacity_without_resetting_usage(self):
        self.seed_usage(550)
        self.assertFalse(self.allowed())
        history = list(AppointmentAIUsageSession.objects.values())
        pending = self.change('ai_1500')
        self.assertTrue(apply_appointments_change(pending, payment_id='s8b-upgrade', at=AT))
        policy = self.policy()
        self.assertEqual(policy['usage_tier'], 'ai_1500')
        self.assertEqual(policy['used_sessions'], 550)
        self.assertEqual(policy['overage_amount'], 0)
        self.assertEqual(policy['max_total_sessions'], 2187)
        self.assertEqual(policy['overage_unit_price'], 200)
        self.assertEqual(policy['hard_cap_amount'], 137500)
        self.assertTrue(policy['can_start_new_session'])
        self.assertEqual(list(AppointmentAIUsageSession.objects.values()), history)
        self.assertTrue(self.record()[1])

    def test_pending_downgrade_keeps_current_policy(self):
        self.tier('ai_1500')
        self.seed_usage(600)
        before = self.policy()
        pending = self.change('ai_300')
        self.assertEqual(pending.status, 'scheduled')
        self.assertEqual(self.policy(), before)
        self.assertTrue(self.record()[1])

    def test_applied_downgrade_reduces_policy_without_rewriting_history(self):
        self.tier('ai_1500')
        self.seed_usage(320)
        history = list(AppointmentAIUsageSession.objects.values())
        pending = self.change('ai_300')
        self.assertTrue(apply_appointments_change(pending, at=AT))
        policy = self.policy()
        self.assertEqual(policy['usage_tier'], 'ai_300')
        self.assertEqual(policy['used_sessions'], 320)
        self.assertEqual(policy['max_total_sessions'], 550)
        self.assertEqual(policy['overage_amount'], 6000)
        self.assertTrue(policy['can_start_new_session'])
        self.assertEqual(list(AppointmentAIUsageSession.objects.values()), history)

    def test_applied_downgrade_above_new_limit_blocks_only_new_sessions(self):
        self.tier('ai_1500')
        self.seed_usage(600)
        session, _ = self.record()
        pending = self.change('ai_300')
        self.assertTrue(apply_appointments_change(pending, at=AT))
        policy = self.policy()
        self.assertEqual(policy['used_sessions'], 601)
        self.assertEqual(policy['max_total_sessions'], 550)
        self.assertEqual(policy['overage_amount'], 90300)
        self.assertFalse(policy['can_start_new_session'])
        self.assertEqual(self.record(AT + timedelta(hours=1))[0].pk, session.pk)
        with self.assertRaises(AIUsageHardCapReached):
            self.record(session.expires_at)
        self.assertEqual(self.usage()['used'], 601)

    def test_grace_permits_last_slot_but_enforces_cap(self):
        self.seed_usage(549)
        record_appointments_payment_failure(subscription=self.subscription, at=AT)
        self.assertTrue(self.allowed())
        self.record()
        self.assertFalse(self.allowed())
        with self.assertRaises(AIUsageHardCapReached):
            self.record(AT + timedelta(hours=24))

    def test_expired_grace_fails_closed(self):
        record_appointments_payment_failure(subscription=self.subscription, at=AT)
        with self.assertRaises(AIUsageUnavailable):
            self.allowed(AT + timedelta(days=3, microseconds=1))

    def test_suspended_subscription_fails_closed(self):
        self.subscription.status = 'suspended'
        self.subscription.save(update_fields=['status'])
        for action in (self.policy, self.allowed, self.record):
            with self.assertRaises(AIUsageUnavailable):
                action()

    def test_suspended_business_fails_closed(self):
        Business.objects.filter(pk=self.business.pk).update(status='suspended')
        for action in (self.policy, self.allowed, self.record):
            with self.assertRaises(AIUsageUnavailable):
                action()

    def test_cancel_at_period_end_allows_until_boundary(self):
        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=['cancel_at_period_end'])
        self.assertTrue(self.allowed(END - timedelta(microseconds=1)))
        self.assertTrue(self.record(END - timedelta(microseconds=1))[1])
        for action in (self.policy, self.allowed, self.record):
            with self.assertRaises(AIUsageUnavailable):
                action(END)

    def test_cancellation_does_not_bypass_cap(self):
        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=['cancel_at_period_end'])
        self.seed_usage(550)
        self.assertFalse(self.allowed())
        with self.assertRaises(AIUsageHardCapReached):
            self.record()

    def test_custom_is_manual_unresolved_without_invented_terms(self):
        self.tier('custom')
        for action in (self.policy, self.allowed, self.record):
            with self.assertRaises(ManualContractRequired):
                action()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_invalid_and_null_tiers_fail_closed(self):
        for tier in ('invalid', None):
            SubscriptionV2.objects.filter(pk=self.subscription.pk).update(usage_tier=tier)
            for action in (self.policy, self.allowed, self.record):
                with self.subTest(tier=tier, action=action), self.assertRaises(AIUsageUnavailable):
                    action()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_without_effective_ai_fails_closed(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            plan_code='appointments_pro', usage_tier=None,
        )
        for action in (self.policy, self.allowed, self.record):
            with self.assertRaises(AIUsageUnavailable):
                action()

    def test_missing_subscription_fails_closed(self):
        self.subscription.delete()
        for action in (self.policy, self.allowed, self.record):
            with self.assertRaises(AIUsageUnavailable):
                action()

    def test_unresolved_or_noninteger_commercial_terms_fail_closed(self):
        tier = canonical_pricing.get_usage_tier('ai_300')
        for key, value in (
            ('extra_conversation_price', None), ('extra_conversation_price', 0),
            ('extra_conversation_price', 300.0), ('extra_conversation_price', True),
            ('default_extra_spend_limit', None), ('default_extra_spend_limit', -1),
            ('default_extra_spend_limit', 75000.0), ('default_extra_spend_limit', False),
        ):
            with self.subTest(key=key, value=value), patch.object(
                canonical_pricing, 'get_usage_tier', return_value={**tier, key: value},
            ), self.assertRaises(AIUsageUnavailable):
                self.record()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_new_usage_month_has_its_own_cap(self):
        self.seed_usage(550)
        self.assertFalse(self.allowed())
        self.renewal()
        self.assertTrue(self.allowed(END))
        self.assertTrue(self.record(END)[1])
        self.assertEqual(self.policy(END)['used_sessions'], 1)

    def test_active_cross_period_session_does_not_consume_new_period_capacity(self):
        self.seed_usage(549)
        first, _ = self.record(END - timedelta(minutes=10))
        self.renewal()
        next_end = self.subscription.current_period_end
        self.seed_usage(550, start=END, end=next_end)
        self.assertFalse(self.allowed(END))
        session, created = self.record(END + timedelta(minutes=10))
        self.assertFalse(created)
        self.assertEqual(session.pk, first.pk)
        self.assertEqual(self.policy(END)['used_sessions'], 550)
        with self.assertRaises(AIUsageHardCapReached):
            self.record(first.expires_at)

    def test_policy_and_session_creation_do_not_write_billing_or_amounts(self):
        self.seed_usage(300)
        models = list(apps.get_app_config('billing').get_models())
        counts = {model: model.objects.count() for model in models}
        subscription = SubscriptionV2.objects.filter(pk=self.subscription.pk).values().get()
        self.policy()
        self.allowed()
        self.record()
        self.assertEqual({model: model.objects.count() for model in models}, counts)
        self.assertEqual(
            SubscriptionV2.objects.filter(pk=self.subscription.pk).values().get(), subscription,
        )
        self.assertEqual(self.policy()['overage_amount'], 300)


@skipUnlessDBFeature('has_select_for_update')
class AIUsagePolicyConcurrencyTests(AIUsagePolicyFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def test_distinct_conversations_racing_for_last_slot_only_one_opens(self):
        self.seed_usage(549)
        other = make_state(Lead.objects.create(business=self.business), self.channel)
        barrier = threading.Barrier(2)

        def worker(conversation):
            connections.close_all()
            try:
                business = Business.objects.get(pk=self.business.pk)
                barrier.wait(timeout=10)
                try:
                    return self.record(business=business, conversation_id=conversation)[1]
                except AIUsageHardCapReached:
                    return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(worker, conversation) for conversation in (
                    self.state.external_conversation_id, other.external_conversation_id,
                )
            ]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.policy()['used_sessions'], 550)
        self.assertEqual(self.policy()['overage_amount'], 75000)
        self.assertFalse(self.allowed())
