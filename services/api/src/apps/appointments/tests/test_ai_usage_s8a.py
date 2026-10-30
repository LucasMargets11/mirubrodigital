from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import IntegrityError, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.appointments.models import AppointmentAIUsageSession
from apps.appointments.services.ai_usage import (
    AIUsageUnavailable,
    count_ai_sessions_for_usage_period,
    get_appointments_ai_usage,
    get_or_create_ai_usage_session,
    resolve_ai_usage_limit,
    resolve_appointments_ai_usage_period,
)
from apps.billing.models import BillingInvoiceEvent, SubscriptionV2
from apps.billing.services.appointments_checkout import ManualContractRequired
from apps.billing.services.appointments_lifecycle import (
    apply_appointments_change,
    apply_appointments_renewal,
    record_appointments_payment_failure,
    request_appointments_change,
)
from apps.business.models import Business
from apps.leads.models import Lead, LeadAgentMessage
from apps.leads.tests.factories import make_channel, make_instance, make_state

UTC = timezone.utc
START = datetime(2026, 10, 12, 14, 30, tzinfo=UTC)
END = datetime(2026, 11, 12, 14, 30, tzinfo=UTC)
AT = datetime(2026, 10, 20, 10, tzinfo=UTC)


class AIUsageFixture:
    def setUp(self):
        super().setUp()
        self.business = Business.objects.create(
            name='S8A', slug=f's8a-{uuid.uuid4().hex}', default_service='appointments',
            status='active',
        )
        self.subscription = SubscriptionV2.objects.create(
            business=self.business, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_300', billing_cycle='monthly', provider='manual',
            external_reference=f'S8A-{uuid.uuid4()}', status='active', is_active=True,
            current_period_start=START, current_period_end=END,
        )
        self.channel = make_channel(
            make_instance(f'agent-{uuid.uuid4().hex}'), self.business,
            phone_number_id=str(uuid.uuid4().int)[:25],
        )
        self.lead = Lead.objects.create(business=self.business, source='whatsapp_agent')
        self.state = make_state(self.lead, self.channel, opened_at=START, last_message_at=AT)
        self.event_id = uuid.uuid4()

    def record(self, at=AT, *, event_id=None, conversation_id=None, business=None):
        return get_or_create_ai_usage_session(
            business=business or self.business,
            conversation_id=conversation_id or self.state.external_conversation_id,
            interaction_id=event_id or uuid.uuid4(), at=at,
        )

    def usage(self, at=AT):
        return get_appointments_ai_usage(self.business, at=at)

    def tier(self, tier):
        self.subscription.usage_tier = tier
        self.subscription.save(update_fields=['usage_tier'])

    def renewal(self):
        event = BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=f's8a-{uuid.uuid4()}',
            provider_status='authorized', paid_at=END,
        )
        self.assertTrue(apply_appointments_renewal(
            subscription=self.subscription, invoice_event=event,
        ))
        self.subscription.refresh_from_db()

    def change(self, tier):
        user = get_user_model().objects.create_user(username=f's8a-{uuid.uuid4().hex}')
        return request_appointments_change(
            business=self.business, user=user, target={'usage_tier': tier}, at=AT,
        )[0]


class AIUsageSessionTests(AIUsageFixture, TestCase):
    def test_first_interaction_creates_one_session_and_expected_usage_shape(self):
        session, created = self.record(event_id=self.event_id)
        self.assertTrue(created)
        session.refresh_from_db()
        self.assertEqual(session.started_at, AT)
        self.assertEqual(session.expires_at, AT + timedelta(hours=24))
        self.assertEqual(session.opening_interaction_id, self.event_id)
        self.assertEqual(session.subscription_id, self.subscription.pk)
        self.assertEqual(session.usage_tier, 'ai_300')
        self.assertEqual(self.usage(), {
            'usage_tier': 'ai_300', 'period_start': START, 'period_end': END,
            'used': 1, 'included': 300, 'remaining': 299,
        })

    def test_second_interaction_inside_24h_does_not_increment_or_slide_expiry(self):
        first, _ = self.record()
        second, created = self.record(AT + timedelta(hours=23))
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.expires_at, AT + timedelta(hours=24))
        self.assertEqual(self.usage()['used'], 1)

    def test_just_before_24h_is_same_session(self):
        first, _ = self.record()
        second, created = self.record(AT + timedelta(hours=24, microseconds=-1))
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)

    def test_exactly_24h_opens_new_session(self):
        first, _ = self.record()
        second, created = self.record(AT + timedelta(hours=24))
        self.assertTrue(created)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.usage()['used'], 2)

    def test_after_24h_opens_new_session(self):
        self.record()
        self.assertTrue(self.record(AT + timedelta(hours=25))[1])
        self.assertEqual(self.usage()['used'], 2)

    def test_retry_opening_event_is_idempotent_even_after_other_sessions(self):
        first, _ = self.record(event_id=self.event_id)
        self.record(AT + timedelta(days=2))
        retry, created = self.record(event_id=self.event_id)
        self.assertFalse(created)
        self.assertEqual(first.pk, retry.pk)
        self.assertEqual(self.usage()['used'], 2)

    def test_nonopening_event_retry_uses_original_time_not_delivery_time(self):
        first, _ = self.record()
        inner_id = uuid.uuid4()
        self.record(AT + timedelta(hours=2), event_id=inner_id)
        self.record(AT + timedelta(days=2))
        retry, created = self.record(AT + timedelta(hours=2), event_id=inner_id)
        self.assertFalse(created)
        self.assertEqual(first.pk, retry.pk)
        self.assertEqual(self.usage()['used'], 2)

    def test_opening_event_identity_cannot_be_reused_with_another_time(self):
        self.record(event_id=self.event_id)
        with self.assertRaisesMessage(AIUsageUnavailable, 'conflicts'):
            self.record(AT + timedelta(days=2), event_id=self.event_id)

    def test_businesses_do_not_share_sessions_or_event_keys(self):
        first, _ = self.record(event_id=self.event_id)
        other = Business.objects.create(name='Other', slug='s8a-other', status='active')
        SubscriptionV2.objects.create(
            business=other, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_300', billing_cycle='monthly', provider='manual', status='active',
            external_reference=f'S8A-{uuid.uuid4()}',
            current_period_start=START, current_period_end=END,
        )
        channel = make_channel(self.channel.agent_instance, other, phone_number_id='99112233')
        make_state(
            Lead.objects.create(business=other), channel,
            external_conversation_id=self.state.external_conversation_id,
        )
        second, created = self.record(business=other, event_id=self.event_id)
        self.assertTrue(created)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.usage()['used'], 1)
        self.assertEqual(get_appointments_ai_usage(other, at=AT)['used'], 1)

    def test_different_conversations_create_different_sessions(self):
        self.record()
        other = make_state(Lead.objects.create(business=self.business), self.channel)
        self.assertTrue(self.record(conversation_id=other.external_conversation_id)[1])
        self.assertEqual(self.usage()['used'], 2)

    def test_new_lead_episode_in_same_conversation_does_not_increment(self):
        first, _ = self.record()
        make_state(
            Lead.objects.create(business=self.business), self.channel,
            external_conversation_id=self.state.external_conversation_id,
        )
        second, created = self.record(AT + timedelta(hours=1))
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)

    def test_utc_not_calendar_date_or_midnight(self):
        local = timezone(timedelta(hours=-3))
        first, _ = self.record(datetime(2026, 10, 20, 23, 55, tzinfo=local))
        second, created = self.record(datetime(2026, 10, 21, 0, 5, tzinfo=local))
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.started_at, datetime(2026, 10, 21, 2, 55, tzinfo=UTC))

    def test_missing_or_foreign_or_ambiguous_context_fails_closed(self):
        for conversation in ('unknown', '', 'x' * 65):
            with self.subTest(conversation=conversation), self.assertRaises(AIUsageUnavailable):
                get_or_create_ai_usage_session(
                    business=self.business, conversation_id=conversation,
                    interaction_id=uuid.uuid4(), at=AT,
                )
        other_channel = make_channel(self.channel.agent_instance, self.business, phone_number_id='9876')
        make_state(
            Lead.objects.create(business=self.business), other_channel,
            external_conversation_id=self.state.external_conversation_id,
        )
        with self.assertRaisesMessage(AIUsageUnavailable, 'ambiguous'):
            self.record()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_foreign_conversation_cannot_be_used_by_business(self):
        other = Business.objects.create(name='Foreign', slug='s8a-foreign', status='active')
        channel = make_channel(self.channel.agent_instance, other, phone_number_id='76543')
        state = make_state(Lead.objects.create(business=other), channel)
        with self.assertRaisesMessage(AIUsageUnavailable, 'context'):
            self.record(conversation_id=state.external_conversation_id)

    def test_naive_time_and_mutable_event_identifiers_are_rejected(self):
        with self.assertRaises(AIUsageUnavailable):
            self.record(AT.replace(tzinfo=None))
        with self.assertRaises(AIUsageUnavailable):
            self.record(event_id='not-a-uuid')

    def test_out_of_order_overlap_is_explicitly_unresolved(self):
        self.record(AT + timedelta(hours=1))
        with self.assertRaisesMessage(AIUsageUnavailable, 'Out-of-order'):
            self.record(AT)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 1)

    def test_no_automatic_metering_from_bot_staff_or_patient_messages(self):
        for sender, role in (('bot', 'assistant'), ('staff', 'assistant'), ('patient', 'user')):
            LeadAgentMessage.objects.create(
                lead=self.lead, external_message_id=f'msg-{sender}',
                sender=sender, role=role, text='Not proof of AI participation', sent_at=AT,
            )
        self.assertEqual(self.usage()['used'], 0)

    def test_database_enforces_duration_period_tier_and_unique_keys(self):
        first, _ = self.record(event_id=self.event_id)
        invalid = (
            {'expires_at': AT + timedelta(hours=25)},
            {'usage_period_end': AT},
            {'usage_tier': 'custom'},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    AppointmentAIUsageSession.objects.filter(pk=first.pk).update(**values)
        for overrides in ({}, {'started_at': AT + timedelta(days=2),
                                'expires_at': AT + timedelta(days=3)}):
            values = {
                field: getattr(first, field) for field in (
                    'business', 'subscription', 'external_conversation_id', 'opening_interaction_id',
                    'started_at', 'expires_at', 'usage_period_start', 'usage_period_end', 'usage_tier',
                )
            }
            values.update(overrides)
            with self.assertRaises(IntegrityError), transaction.atomic():
                AppointmentAIUsageSession.objects.create(**values)


class AIUsagePeriodTests(AIUsageFixture, TestCase):
    def test_monthly_period_uses_renewal_anchor_not_first_day(self):
        self.assertEqual(
            resolve_appointments_ai_usage_period(self.subscription, at=AT), (START, END),
        )
        self.renewal()
        self.assertEqual(
            resolve_appointments_ai_usage_period(self.subscription, at=END),
            (END, datetime(2026, 12, 12, 14, 30, tzinfo=UTC)),
        )

    def test_annual_subscription_has_monthly_usage_periods(self):
        self.subscription.billing_cycle = 'yearly'
        self.subscription.current_period_end = START.replace(year=2027)
        self.subscription.save(update_fields=['billing_cycle', 'current_period_end'])
        self.assertEqual(
            resolve_appointments_ai_usage_period(self.subscription, at=END),
            (END, datetime(2026, 12, 12, 14, 30, tzinfo=UTC)),
        )
        self.record(END)
        self.assertEqual(self.usage(END)['used'], 1)
        self.assertEqual(self.usage(AT)['used'], 0)

    def test_annual_short_month_preserves_original_anchor_day_and_leap_year(self):
        for year, feb_day in ((2026, 28), (2028, 29)):
            self.subscription.billing_cycle = 'yearly'
            self.subscription.current_period_start = datetime(year, 1, 31, 8, tzinfo=UTC)
            self.subscription.current_period_end = datetime(year + 1, 1, 31, 8, tzinfo=UTC)
            feb = datetime(year, 2, feb_day, 8, tzinfo=UTC)
            march = datetime(year, 3, 31, 8, tzinfo=UTC)
            with self.subTest(year=year):
                self.assertEqual(
                    resolve_appointments_ai_usage_period(self.subscription, at=feb), (feb, march),
                )

    def test_cross_period_session_stays_in_start_period_after_renewal(self):
        first, _ = self.record(END - timedelta(minutes=10))
        self.renewal()
        second, created = self.record(END + timedelta(minutes=10))
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.usage_period_start, START)
        self.assertEqual(second.usage_period_end, END)
        self.assertEqual(self.usage(END + timedelta(minutes=10))['used'], 0)
        self.assertEqual(count_ai_sessions_for_usage_period(
            business=self.business, period_start=START, period_end=END,
        ), 1)

    def test_new_session_at_expiry_after_period_change_is_in_new_period(self):
        first, _ = self.record(END - timedelta(minutes=10))
        self.renewal()
        second, created = self.record(first.expires_at)
        self.assertTrue(created)
        self.assertEqual(second.usage_period_start, END)
        self.assertEqual(self.usage(second.started_at)['used'], 1)

    def test_grace_starts_next_usage_month_at_renewal_boundary(self):
        record_appointments_payment_failure(subscription=self.subscription, at=END)
        session, created = self.record(END + timedelta(hours=1))
        self.assertTrue(created)
        self.assertEqual(session.usage_period_start, END)
        self.assertEqual(session.usage_period_end, datetime(2026, 12, 12, 14, 30, tzinfo=UTC))
        self.assertEqual(self.usage(session.started_at)['used'], 1)

    def test_missing_invalid_or_historical_anchor_is_not_guessed(self):
        for field, value in (
            ('current_period_start', None), ('current_period_end', None),
            ('current_period_end', START), ('billing_cycle', 'invalid'),
        ):
            original = getattr(self.subscription, field)
            setattr(self.subscription, field, value)
            with self.subTest(field=field, value=value), self.assertRaises(AIUsageUnavailable):
                resolve_appointments_ai_usage_period(self.subscription, at=AT)
            setattr(self.subscription, field, original)
        with self.assertRaises(AIUsageUnavailable):
            resolve_appointments_ai_usage_period(self.subscription, at=START - timedelta(seconds=1))


class AIUsageLifecycleTests(AIUsageFixture, TestCase):
    def test_each_canonical_tier_resolves_included_quota(self):
        for tier, included in (('ai_300', 300), ('ai_1500', 1500), ('ai_3000', 3000)):
            self.tier(tier)
            with self.subTest(tier=tier):
                self.assertEqual(resolve_ai_usage_limit(self.subscription), included)
                self.assertEqual(self.usage()['included'], included)

    def test_upgrade_immediately_changes_quota_without_rewriting_history(self):
        first, _ = self.record()
        pending = self.change('ai_1500')
        self.assertTrue(apply_appointments_change(pending, payment_id='s8a-upgrade', at=AT))
        self.assertEqual(self.usage()['included'], 1500)
        self.assertEqual(self.usage()['remaining'], 1499)
        first.refresh_from_db()
        self.assertEqual(first.usage_tier, 'ai_300')
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 1)

    def test_pending_downgrade_keeps_current_tier(self):
        self.tier('ai_1500')
        self.record()
        pending = self.change('ai_300')
        self.assertEqual(pending.status, 'scheduled')
        self.assertEqual(self.usage()['usage_tier'], 'ai_1500')
        self.assertEqual(self.usage()['included'], 1500)

    def test_applied_downgrade_uses_new_quota_and_preserves_sessions(self):
        self.tier('ai_1500')
        first, _ = self.record()
        self.change('ai_300')
        self.renewal()
        self.assertEqual(self.usage(END)['usage_tier'], 'ai_300')
        self.assertEqual(self.usage(END)['included'], 300)
        first.refresh_from_db()
        self.assertEqual(first.usage_tier, 'ai_1500')
        self.assertEqual(first.usage_period_start, START)

    def test_no_subscription_fails_closed_without_legacy_fallback(self):
        self.subscription.delete()
        with self.assertRaises(AIUsageUnavailable):
            self.record()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_non_ai_or_malformed_plan_fails_closed(self):
        for plan, tier in (('appointments_pro', None), ('appointments', None), ('pro', None)):
            SubscriptionV2.objects.filter(pk=self.subscription.pk).update(plan_code=plan, usage_tier=tier)
            with self.subTest(plan=plan), self.assertRaises(AIUsageUnavailable):
                self.record()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_invalid_or_null_tier_fails_closed(self):
        for tier in ('invalid', None):
            SubscriptionV2.objects.filter(pk=self.subscription.pk).update(usage_tier=tier)
            with self.subTest(tier=tier), self.assertRaises(AIUsageUnavailable):
                self.record()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_custom_requires_manual_resolution_not_invented_quota(self):
        self.tier('custom')
        for action in (self.record, self.usage):
            with self.assertRaisesMessage(ManualContractRequired, 'manual'):
                action()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_suspended_subscription_does_not_open_session(self):
        self.subscription.status = 'suspended'
        self.subscription.save(update_fields=['status'])
        with self.assertRaises(AIUsageUnavailable):
            self.record()
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)

    def test_suspended_business_does_not_open_session(self):
        self.business.status = 'suspended'
        self.business.save(update_fields=['status'])
        with self.assertRaises(AIUsageUnavailable):
            self.record()

    def test_expired_grace_and_cancellation_boundary_fail_closed(self):
        record_appointments_payment_failure(subscription=self.subscription, at=AT)
        with self.assertRaises(AIUsageUnavailable):
            self.record(AT + timedelta(days=3, microseconds=1))
        self.subscription.refresh_from_db()
        self.subscription.status = 'active'
        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=['status', 'cancel_at_period_end'])
        self.record(END - timedelta(minutes=1))
        with self.assertRaises(AIUsageUnavailable):
            self.record(END)

    def test_cancellation_keeps_history_and_prevents_deleting_subscription(self):
        first, _ = self.record()
        self.subscription.status = 'canceled'
        self.subscription.save(update_fields=['status'])
        with self.assertRaises(AIUsageUnavailable):
            self.record(AT + timedelta(days=2))
        first.refresh_from_db()
        self.assertEqual(first.usage_tier, 'ai_300')
        with self.assertRaises(ProtectedError):
            self.subscription.delete()

    def test_zero_remaining_does_not_enforce_hard_cap(self):
        self.record()
        template = AppointmentAIUsageSession.objects.get()
        AppointmentAIUsageSession.objects.bulk_create([
            AppointmentAIUsageSession(
                business=self.business, subscription=self.subscription,
                external_conversation_id=f'quota-fixture-{index}', opening_interaction_id=uuid.uuid4(),
                started_at=AT, expires_at=template.expires_at,
                usage_period_start=START, usage_period_end=END, usage_tier='ai_300',
            ) for index in range(299)
        ])
        self.assertEqual(self.usage()['remaining'], 0)
        self.assertTrue(self.record(AT + timedelta(hours=24))[1])
        self.assertEqual(self.usage()['used'], 301)
        self.assertEqual(self.usage()['remaining'], 0)


@skipUnlessDBFeature('has_select_for_update')
class AIUsageConcurrencyTests(AIUsageFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def race(self, *, same_event=False):
        barrier = threading.Barrier(2)
        event_id = uuid.uuid4()

        def worker():
            connections.close_all()
            try:
                business = Business.objects.get(pk=self.business.pk)
                barrier.wait(timeout=10)
                session, created = get_or_create_ai_usage_session(
                    business=business, conversation_id=self.state.external_conversation_id,
                    interaction_id=event_id if same_event else uuid.uuid4(), at=AT,
                )
                return session.pk, created
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_distinct_interactions_create_only_one_session(self):
        result = self.race()
        self.assertEqual(len({pk for pk, _ in result}), 1)
        self.assertEqual(sum(created for _, created in result), 1)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 1)

    def test_concurrent_retries_create_only_one_session(self):
        result = self.race(same_event=True)
        self.assertEqual(len({pk for pk, _ in result}), 1)
        self.assertEqual(sum(created for _, created in result), 1)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 1)

    def test_concurrent_interactions_reuse_existing_session(self):
        first, _ = self.record(AT - timedelta(hours=1))
        result = self.race()
        self.assertEqual({pk for pk, _ in result}, {first.pk})
        self.assertFalse(any(created for _, created in result))
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 1)
