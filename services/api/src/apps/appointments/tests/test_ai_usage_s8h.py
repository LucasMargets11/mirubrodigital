import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
)
from apps.appointments.services.ai_usage_authorization import authorize_ai_interaction
from apps.appointments.tests.test_ai_usage_s8a import AT
from apps.appointments.tests.test_ai_usage_s8b import AIUsagePolicyFixture
from apps.billing.models import SubscriptionV2
from apps.leads.models import Lead, LeadAgentState
from apps.leads.tests.agent_client import encode, sign_headers
from apps.leads.tests.factories import SECRET, TEST_KEY, make_credential, make_instance, make_state

PATH = '/api/internal/appointments/ai-usage/authorize/'


@override_settings(AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class AIUsageAuthorizationTests(AIUsagePolicyFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.state.external_conversation_id = 'wac1_' + 'a' * 32
        self.state.save(update_fields=['external_conversation_id'])
        self.credential = make_credential(self.channel.agent_instance, key_id=uuid.uuid4().hex)
        self.client = APIClient()

    def payload(self, **overrides):
        return {
            'external_conversation_id': self.state.external_conversation_id,
            'interaction_id': str(self.event_id), 'occurred_at': AT.isoformat(), **overrides,
        }

    def post(self, payload=None, *, now=AT, credential=None, secret=SECRET):
        body = encode(self.payload() if payload is None else payload)
        headers = sign_headers(
            path=PATH, body=body, key_id=(credential or self.credential).key_id,
            secret=secret, method='POST',
        )
        with patch('apps.appointments.services.ai_usage_authorization.timezone.now', return_value=now):
            return self.client.generic('POST', PATH, data=body, content_type='application/json', **headers)

    def assertBlocked(self, response, reason):
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {'allowed': False, 'reason': reason})

    def assertNoUsage(self):
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 0)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)
        self.assertEqual(AppointmentAIUsageAuthorization.objects.count(), 0)

    def test_valid_ai_creates_session_and_minimal_response(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), {
            'allowed', 'session_id', 'created', 'usage_tier', 'period_start',
            'period_end', 'used', 'included', 'remaining',
        })
        self.assertTrue(body['allowed'])
        self.assertTrue(body['created'])
        self.assertEqual((body['used'], body['included'], body['remaining']), (1, 300, 299))
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_second_interaction_reuses_and_retries_do_not_duplicate(self):
        first = self.post().json()
        second_payload = self.payload(
            interaction_id=str(uuid.uuid4()), occurred_at=(AT + timedelta(hours=1)).isoformat(),
        )
        second = self.post(second_payload, now=AT + timedelta(hours=1)).json()
        retry = self.post(second_payload, now=AT + timedelta(hours=2)).json()
        opening_retry = self.post(now=AT + timedelta(hours=2)).json()
        self.assertEqual({x['session_id'] for x in (first, second, retry, opening_retry)}, {first['session_id']})
        self.assertFalse(second['created'])
        self.assertFalse(retry['created'])
        self.assertFalse(opening_retry['created'])
        self.assertEqual(AppointmentAIUsageAuthorization.objects.count(), 2)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_after_24h_creates_new_session(self):
        first = self.post().json()
        at = AT + timedelta(hours=24)
        second = self.post(self.payload(
            interaction_id=str(uuid.uuid4()), occurred_at=at.isoformat(),
        ), now=at).json()
        self.assertTrue(second['created'])
        self.assertNotEqual(first['session_id'], second['session_id'])
        self.assertEqual(second['used'], 2)

    def test_hard_cap_blocks_new_but_reuses_current_window(self):
        self.seed_usage(549)
        first = self.post().json()
        self.assertTrue(first['allowed'])
        self.assertTrue(self.post(self.payload(interaction_id=str(uuid.uuid4()))).json()['allowed'])
        at = AT + timedelta(hours=24)
        self.assertBlocked(self.post(self.payload(
            interaction_id=str(uuid.uuid4()), occurred_at=at.isoformat(),
        ), now=at), 'hard_cap_reached')
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_suspended_blocks_even_retry_with_old_timestamp(self):
        self.post()
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status='suspended')
        self.assertBlocked(self.post(now=AT + timedelta(minutes=5)), 'suspended')
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_business_suspended_blocks(self):
        self.business.status = 'suspended'
        self.business.save(update_fields=['status'])
        self.assertBlocked(self.post(), 'suspended')
        self.assertNoUsage()

    def test_grace_allows_and_expired_grace_blocks(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            status='past_due', grace_until=AT + timedelta(days=3),
        )
        self.assertTrue(self.post().json()['allowed'])
        self.assertBlocked(self.post(now=AT + timedelta(days=3, seconds=1)), 'suspended')

    def test_invalid_tier_blocks(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(usage_tier='invalid')
        self.assertBlocked(self.post(), 'invalid_tier')
        self.assertNoUsage()

    def test_no_ai_entitlement_blocks(self):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(plan_code='appointments_pro', usage_tier=None)
        self.assertBlocked(self.post(), 'no_ai_entitlement')
        self.assertNoUsage()

    def test_custom_requires_manual_contract(self):
        self.tier('custom')
        self.assertBlocked(self.post(), 'manual_contract_required')
        self.assertNoUsage()

    def test_invalid_auth_and_human_auth_cannot_authorize(self):
        self.assertEqual(self.post(secret='invalid').status_code, 401)
        self.assertEqual(self.client.post(PATH, self.payload(), format='json').status_code, 401)
        self.assertNoUsage()

    def test_rotating_credential_is_accepted_revoked_is_not(self):
        self.credential.status = 'retiring'
        self.credential.save(update_fields=['status'])
        self.assertTrue(self.post().json()['allowed'])
        self.credential.status = 'revoked'
        self.credential.revoked_at = AT
        self.credential.save(update_fields=['status', 'revoked_at'])
        self.assertEqual(self.post().status_code, 401)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_other_instance_cannot_access_conversation(self):
        credential = make_credential(make_instance('other-s8h'), key_id=uuid.uuid4().hex)
        self.assertBlocked(self.post(credential=credential), 'unsafe_conversation_context')
        self.assertNoUsage()

    def test_ambiguous_context_cannot_select_a_tenant(self):
        from apps.leads.tests.factories import make_business, make_channel

        other = make_business('s8h-other')
        channel = make_channel(self.channel.agent_instance, other, phone_number_id='99123')
        make_state(Lead.objects.create(business=other), channel,
                   external_conversation_id=self.state.external_conversation_id)
        self.assertBlocked(self.post(), 'unsafe_conversation_context')
        self.assertNoUsage()

    def test_missing_or_inactive_context_fails_closed(self):
        self.assertBlocked(self.post(self.payload(external_conversation_id='wac1_' + 'b' * 32)),
                           'unsafe_conversation_context')
        self.channel.is_active = False
        self.channel.save(update_fields=['is_active'])
        self.assertBlocked(self.post(), 'unsafe_conversation_context')
        self.assertNoUsage()

    def test_invalid_payloads_never_generate_usage(self):
        for payload in [
            {}, [], self.payload(business_id=self.business.pk),
            self.payload(interaction_id='random'), self.payload(external_conversation_id='phone\nunsafe'),
            self.payload(occurred_at='2026-10-20T10:00:00'),
            self.payload(occurred_at='bad'), self.payload(occurred_at=None),
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload).status_code, 400)
                self.assertNoUsage()

    def test_future_and_expired_interactions_do_not_generate_usage(self):
        self.assertBlocked(self.post(now=AT - timedelta(seconds=1)), 'invalid_request')
        self.assertBlocked(self.post(now=AT + timedelta(days=2)), 'interaction_expired')
        self.assertNoUsage()

    def test_nonopening_interaction_cannot_be_rebound_to_new_time_or_conversation(self):
        self.post()
        inner = self.payload(interaction_id=str(uuid.uuid4()))
        self.post(inner)
        self.assertBlocked(self.post({**inner, 'occurred_at': (AT + timedelta(minutes=1)).isoformat()},
                                     now=AT + timedelta(minutes=1)), 'interaction_conflict')
        make_state(Lead.objects.create(business=self.business), self.channel,
                   external_conversation_id='wac1_' + 'b' * 32)
        self.assertBlocked(self.post({**inner, 'external_conversation_id': 'wac1_' + 'b' * 32}),
                           'interaction_conflict')
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_logs_do_not_contain_secrets_or_raw_conversation(self):
        with self.assertLogs('apps.appointments.ai_usage_views', level='INFO') as logs:
            self.post()
        text = ' '.join(logs.output)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(self.state.external_conversation_id, text)
        self.assertIn(f'business={self.business.pk}', text)
        self.assertIn('allowed=true', text)


@skipUnlessDBFeature('has_select_for_update')
@override_settings(AI_USAGE_METERING_ENABLED=True)
class AIUsageAuthorizationConcurrencyTests(AIUsagePolicyFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def race(self, *, same_interaction):
        barrier = threading.Barrier(2)
        interaction_id = uuid.uuid4()

        def worker():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                _, session, created, _ = authorize_ai_interaction(
                    agent_instance=self.channel.agent_instance,
                    conversation_id=self.state.external_conversation_id,
                    interaction_id=interaction_id if same_interaction else uuid.uuid4(),
                    occurred_at=AT,
                )
                return session.pk, created
            finally:
                connections.close_all()

        with patch('apps.appointments.services.ai_usage_authorization.timezone.now', return_value=AT), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            results = [f.result(timeout=30) for f in futures]
        self.assertEqual(len({pk for pk, _ in results}), 1)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageAuthorization.objects.count(), 1 if same_interaction else 2)

    def test_concurrent_retry_does_not_duplicate_session_or_ledger(self):
        self.race(same_interaction=True)

    def test_concurrent_different_interactions_reuse_window(self):
        self.race(same_interaction=False)
