import time
import uuid
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.db import OperationalError, ProgrammingError, connection
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.appointments.checks import (
    ai_usage_database_ready, check_ai_usage_config, check_ai_usage_database,
)
from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
)
from apps.appointments.services.ai_usage import AIUsageUnavailable
from apps.appointments.services.ai_usage_authorization import authorize_ai_interaction
from apps.appointments.tests.test_ai_usage_s8a import AT
from apps.appointments.tests.test_ai_usage_s8b import AIUsagePolicyFixture
from apps.billing.models import SubscriptionV2
from apps.leads.contract import TIMESTAMP_TOLERANCE_SECONDS
from apps.leads.tests.agent_client import encode, sign_headers
from apps.leads.tests.factories import SECRET, TEST_KEY, make_credential

AUTHORIZE = '/api/internal/appointments/ai-usage/authorize/'
HEALTH = '/api/internal/appointments/ai-usage/health/'
LOGGER = 'apps.appointments.ai_usage_views'


@override_settings(
    AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=True,
    AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY,
)
class AIUsageOperationsTests(AIUsagePolicyFixture, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.state.external_conversation_id = 'wac1_' + 'a' * 32
        self.state.save(update_fields=['external_conversation_id'])
        self.credential = make_credential(self.channel.agent_instance, key_id=uuid.uuid4().hex)
        self.client = APIClient()

    def payload(self):
        return {
            'external_conversation_id': self.state.external_conversation_id,
            'interaction_id': str(self.event_id),
            'occurred_at': AT.isoformat(),
        }

    def headers(self, *, path=AUTHORIZE, body=None, **kwargs):
        return sign_headers(
            path=path, body=encode(self.payload()) if body is None else body,
            key_id=self.credential.key_id, method='GET' if path == HEALTH else 'POST',
            **kwargs,
        )

    def send(self, *, path=AUTHORIZE, body=None, headers=None, **sign_kwargs):
        body = (b'' if path == HEALTH else encode(self.payload())) if body is None else body
        headers = self.headers(path=path, body=body, **sign_kwargs) if headers is None else headers
        with patch('apps.appointments.services.ai_usage_authorization.timezone.now', return_value=AT):
            return self.client.generic(
                'GET' if path == HEALTH else 'POST', path, data=body,
                content_type='application/json', **headers,
            )

    def assertNoUsage(self):
        for model in (AppointmentAIUsageAuthorization, AppointmentAIUsageSession, AppointmentAIUsageCharge):
            self.assertEqual(model.objects.count(), 0)

    @override_settings(AI_USAGE_METERING_ENABLED=False)
    def test_flag_disabled_creates_no_usage_and_logs_correlation(self):
        with self.assertLogs(LOGGER, level='INFO') as logs:
            response = self.send()
        self.assertEqual(response.json(), {'allowed': False, 'reason': 'metering_disabled'})
        record = logs.records[-1]
        self.assertEqual(record.metric, 'authorization_blocked')
        self.assertEqual(record.interaction_id, str(self.event_id))
        self.assertEqual(record.request_id, response['X-Request-Id'])
        self.assertNoUsage()

    @override_settings(AI_USAGE_METERING_ENABLED=False)
    def test_service_itself_cannot_bypass_flag(self):
        with self.assertRaises(AIUsageUnavailable) as caught:
            authorize_ai_interaction(
                agent_instance=self.channel.agent_instance,
                conversation_id=self.state.external_conversation_id,
                interaction_id=self.event_id, occurred_at=AT,
            )
        self.assertEqual(caught.exception.reason, 'metering_disabled')
        self.assertNoUsage()

    def test_missing_metering_configuration_is_fail_closed(self):
        with override_settings():
            del settings.AI_USAGE_METERING_ENABLED
            response = self.send()
        self.assertEqual(response.json(), {'allowed': False, 'reason': 'metering_disabled'})
        self.assertNoUsage()

    def test_enabled_allowed_reused_latency_and_receipt_correlation(self):
        with self.assertLogs(LOGGER, level='INFO') as logs:
            first = self.send()
            second = self.send()
        self.assertTrue(first.json()['allowed'])
        self.assertEqual([r.metric for r in logs.records], ['authorization_allowed', 'authorization_reused'])
        receipt = AppointmentAIUsageAuthorization.objects.get(interaction_id=self.event_id)
        for record, response in zip(logs.records, (first, second)):
            self.assertEqual(record.count, 1)
            self.assertEqual(record.request_id, response['X-Request-Id'])
            self.assertEqual(record.interaction_id, str(receipt.interaction_id))
            self.assertEqual(record.session_id, str(receipt.session_id))
            self.assertEqual(record.business_id, self.business.pk)
            self.assertGreaterEqual(record.duration_ms, 0)
            self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotEqual(first['X-Request-Id'], second['X-Request-Id'])
        self.assertEqual(AppointmentAIUsageSession.objects.count(), 1)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_rollback_preserves_history_and_reenable_reuses_receipt(self):
        first = self.send().json()
        receipt = AppointmentAIUsageAuthorization.objects.values().get()
        with override_settings(AI_USAGE_METERING_ENABLED=False):
            self.assertFalse(self.send().json()['allowed'])
        self.assertEqual(AppointmentAIUsageAuthorization.objects.values().get(), receipt)
        second = self.send().json()
        self.assertEqual(first['session_id'], second['session_id'])
        self.assertFalse(second['created'])
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_health_is_protected_and_minimal(self):
        self.assertEqual(self.client.get(HEALTH).status_code, 401)
        response = self.send(path=HEALTH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'status': 'ok', 'metering_enabled': True,
            'agent_integration_enabled': True, 'database': 'ok',
        })
        self.assertEqual(response['Cache-Control'], 'no-store')
        for value in (SECRET, TEST_KEY, self.credential.key_id, self.state.external_conversation_id, str(self.event_id)):
            self.assertNotIn(value, response.content.decode())
        self.assertNoUsage()

    @override_settings(AI_USAGE_METERING_ENABLED=False, AGENT_INTEGRATION_ENABLED=False)
    def test_health_can_diagnose_both_flags_off_but_still_requires_hmac(self):
        self.assertEqual(self.client.get(HEALTH).status_code, 401)
        response = self.send(path=HEALTH)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['metering_enabled'])
        self.assertFalse(response.json()['agent_integration_enabled'])

    @override_settings(AGENT_INTEGRATION_ENABLED=False)
    def test_health_detects_invalid_enabled_config(self):
        response = self.send(path=HEALTH)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['database'], 'ok')

    def test_health_detects_unavailable_database_and_missing_migration(self):
        for effect in (OperationalError('private database details'), ProgrammingError('private table details')):
            with self.subTest(effect=type(effect).__name__), patch(
                'apps.appointments.ai_usage_views.ai_usage_database_ready', side_effect=effect,
            ):
                response = self.send(path=HEALTH)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()['database'], 'unavailable')
                self.assertNotIn('private', response.content.decode())
        with patch('apps.appointments.ai_usage_views.ai_usage_database_ready', return_value=False):
            self.assertEqual(self.send(path=HEALTH).status_code, 503)

    def test_auth_failure_and_revocation_are_counted(self):
        with self.assertLogs(LOGGER, level='INFO') as logs:
            self.assertEqual(self.send(secret='wrong').status_code, 401)
            self.credential.status = 'revoked'
            self.credential.revoked_at = AT
            self.credential.save(update_fields=['status', 'revoked_at'])
            self.assertEqual(self.send().status_code, 401)
        self.assertEqual([r.metric for r in logs.records], ['authorization_auth_failed'] * 2)
        self.assertNoUsage()

    def test_nonce_replay_rejected_for_authorization_and_health(self):
        for path in (AUTHORIZE, HEALTH):
            body = b'' if path == HEALTH else encode(self.payload())
            headers = self.headers(path=path, body=body)
            self.assertEqual(self.send(path=path, body=body, headers=headers).status_code, 200)
            self.assertEqual(self.send(path=path, body=body, headers=headers).status_code, 401)
        self.assertEqual(AppointmentAIUsageAuthorization.objects.count(), 1)

    def test_timestamp_outside_window_rejected_in_both_directions(self):
        now = int(time.time())
        with patch('apps.leads.authentication.time.time', return_value=now):
            for offset in (-TIMESTAMP_TOLERANCE_SECONDS - 1, TIMESTAMP_TOLERANCE_SECONDS + 1):
                with self.subTest(offset=offset):
                    self.assertEqual(self.send(timestamp=now + offset).status_code, 401)
        self.assertNoUsage()

    def test_valid_clock_skew_including_boundaries(self):
        now = int(time.time())
        with patch('apps.leads.authentication.time.time', return_value=now):
            for offset in (-TIMESTAMP_TOLERANCE_SECONDS, TIMESTAMP_TOLERANCE_SECONDS):
                with self.subTest(offset=offset):
                    self.assertTrue(self.send(timestamp=now + offset).json()['allowed'])
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_correct_signature_with_altered_body_is_rejected(self):
        headers = self.headers()
        body = encode({**self.payload(), 'interaction_id': str(uuid.uuid4())})
        self.assertEqual(self.send(body=body, headers=headers).status_code, 401)
        self.assertNoUsage()

    def test_untrusted_correlation_header_cannot_inject_logs(self):
        headers = self.headers()
        headers['HTTP_X_REQUEST_ID'] += '\nprivate-patient'
        with self.assertLogs(LOGGER, level='INFO') as logs, self.assertLogs(level='INFO') as other_logs:
            response = self.send(headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('X-Request-Id', response)
        self.assertNotIn('private-patient', ' '.join(logs.output + other_logs.output))
        self.assertNoUsage()

    def test_throttle_is_shared_by_instance_across_rotating_keys(self):
        with patch('apps.appointments.ai_usage_views.AIUsageThrottle.get_rate', return_value='2/minute'):
            self.assertEqual(self.send().status_code, 200)
            self.credential = make_credential(self.channel.agent_instance, key_id=uuid.uuid4().hex)
            self.assertEqual(self.send().status_code, 200)
            response = self.send()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['error']['code'], 'rate_limited')
        self.assertIn('Retry-After', response)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 1)

    def test_nonce_cache_failure_is_fail_closed_only_for_metering(self):
        with patch('apps.leads.authentication.cache.add', side_effect=ConnectionError('private redis details')):
            self.assertEqual(self.send().status_code, 503)
        self.assertNoUsage()

    def test_throttle_cache_failure_is_fail_closed(self):
        with patch('apps.leads.throttles.AgentLeadSyncThrottle.cache.get', side_effect=ConnectionError('private')):
            self.assertEqual(self.send().status_code, 503)
        self.assertNoUsage()

    def test_backend_error_and_timeout_have_separate_metrics(self):
        for effect, metric in (
            (OperationalError('sensitive database'), 'backend_error'),
            (ProgrammingError('sensitive table'), 'backend_error'),
            (RuntimeError('sensitive backend'), 'backend_error'),
            (TimeoutError('sensitive timeout'), 'authorization_timeout'),
        ):
            with self.subTest(metric=metric), patch(
                'apps.appointments.ai_usage_views.authorize_ai_interaction', side_effect=effect,
            ), self.assertLogs(LOGGER, level='INFO') as logs:
                response = self.send()
                self.assertIn(response.status_code, (500, 503))
                self.assertEqual(logs.records[-1].metric, metric)
                self.assertNotIn('sensitive', ' '.join(logs.output))
                self.assertNotIn('sensitive', response.content.decode())
        self.assertNoUsage()

    def test_blocked_reason_metrics_use_real_policy_and_context(self):
        scenarios = (
            ('unsafe_conversation_context', {'external_conversation_id': 'wac1_' + 'b' * 32}, None),
            ('invalid_tier', {}, {'usage_tier': 'unknown'}),
            ('no_ai_entitlement', {}, {'plan_code': 'appointments_pro', 'usage_tier': None}),
        )
        for reason, changes, subscription in scenarios:
            with self.subTest(reason=reason):
                SubscriptionV2.objects.filter(pk=self.subscription.pk).update(plan_code='appointments_ai', usage_tier='ai_300')
                if subscription:
                    SubscriptionV2.objects.filter(pk=self.subscription.pk).update(**subscription)
                with self.assertLogs(LOGGER, level='INFO') as logs:
                    response = self.send(body=encode({**self.payload(), **changes}))
                self.assertEqual(response.json(), {'allowed': False, 'reason': reason})
                record = logs.records[-1]
                self.assertEqual((record.metric, record.reason, record.count), ('authorization_blocked', reason, 1))
        self.assertNoUsage()

    def test_hard_cap_metric(self):
        self.seed_usage(550)
        with self.assertLogs(LOGGER, level='INFO') as logs:
            response = self.send()
        self.assertEqual(response.json(), {'allowed': False, 'reason': 'hard_cap_reached'})
        self.assertEqual(logs.records[-1].reason, 'hard_cap_reached')
        self.assertEqual(AppointmentAIUsageAuthorization.objects.count(), 0)
        self.assertEqual(AppointmentAIUsageCharge.objects.count(), 0)

    def test_logs_do_not_contain_body_signature_secret_or_raw_context(self):
        headers = self.headers()
        with self.assertLogs(LOGGER, level='INFO') as logs, self.assertLogs(level='INFO') as other_logs:
            self.send(headers=headers)
            body = encode({**self.payload(), 'prompt': 'private-patient-message'})
            self.send(body=body)
            self.send(body=b'{private-invalid-json')
        records = logs.records + other_logs.records
        text = ' '.join(logs.output + other_logs.output) + ' '.join(str(r.__dict__) for r in records)
        for value in (
            SECRET, TEST_KEY, headers['HTTP_X_AGENT_SIGNATURE'],
            self.state.external_conversation_id, 'private-patient-message', 'private-invalid-json',
        ):
            self.assertNotIn(value, text)
        self.assertIn(str(self.event_id), text)
        self.assertIn(headers['HTTP_X_REQUEST_ID'], text)

    def test_database_check_requires_0015_and_reads_models(self):
        self.assertTrue(ai_usage_database_ready())
        self.assertEqual(check_ai_usage_database(databases=['default']), [])
        with patch('apps.appointments.checks.MigrationRecorder.applied_migrations', return_value={}):
            self.assertFalse(ai_usage_database_ready())
            self.assertEqual(check_ai_usage_database(databases=['default'])[0].id, 'appointments.E002')
        with patch.object(connection, 'cursor', side_effect=OperationalError('private')):
            self.assertEqual(check_ai_usage_database(databases=['default'])[0].id, 'appointments.E002')


class AIUsageConfigurationTests(SimpleTestCase):
    @override_settings(AI_USAGE_METERING_ENABLED=False, AGENT_INTEGRATION_ENABLED=False)
    def test_disabled_needs_no_integration_or_database(self):
        self.assertEqual(check_ai_usage_config(), [])
        self.assertEqual(check_ai_usage_database(databases=['default']), [])

    @override_settings(AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=False)
    def test_enabled_without_integration_is_invalid(self):
        self.assertEqual(check_ai_usage_config()[0].id, 'appointments.E001')

    @override_settings(AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=True)
    def test_valid_config_and_database_check_is_opt_in(self):
        self.assertEqual(check_ai_usage_config(), [])
        self.assertEqual(check_ai_usage_database(), [])
