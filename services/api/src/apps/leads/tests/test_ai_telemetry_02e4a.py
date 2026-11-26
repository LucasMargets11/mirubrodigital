"""PROD-02E4A — Telemetría operativa de IA: persistencia e ingesta segura.

`POST /api/v1/integrations/agent/ai-executions/`: un intento real contra el
proveedor por request, tenant derivado del AgentChannel activo en
`executed_at`, idempotencia por (instancia, event_id), separado del consumo
comercial.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
    AppointmentAIUsageSettlement,
)
from apps.billing.models import SubscriptionV2
from apps.billing.tests.test_reception_ai_consumption_02e2a import _Base
from apps.billing.tests.test_reception_service_02b import _business
from apps.leads.models import AgentAIExecution, AgentChannel, AgentCredential, Lead
from apps.leads.tests.agent_client import encode, sign_headers
from apps.leads.tests.factories import SECRET, TEST_KEY, make_channel, make_credential, make_instance, make_state

PATH = '/api/v1/integrations/agent/ai-executions/'
SETTINGS = dict(
    AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=True, AGENT_AI_TELEMETRY_ENABLED=True,
    AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY,
)
SENTINEL = 'SUPER_SECRET_PATIENT_VALUE'


class _TelemetryBase(_Base):

    def setUp(self):
        super().setUp()
        self.biz = _business()
        self.instance = make_instance(f'agent-{uuid.uuid4().hex[:12]}')
        self.credential = make_credential(self.instance, key_id=uuid.uuid4().hex)
        self.channel = self.channel_for(self.instance, self.biz)

    def channel_for(self, instance, biz, phone=None, created=None):
        channel = make_channel(instance, biz, phone_number_id=phone or str(uuid.uuid4().int)[:15])
        AgentChannel.objects.filter(pk=channel.pk).update(created_at=created or timezone.now() - timedelta(days=10))
        channel.refresh_from_db()
        return channel

    def event(self, channel=None, **overrides):
        body = {
            'event_id': str(uuid.uuid4()),
            'phone_number_id': (channel or self.channel).phone_number_id,
            'interaction_id': None,
            'provider': 'openai', 'model': 'gpt-4.1-mini', 'operation': 'response', 'status': 'succeeded',
            'error_code': None, 'input_tokens': 1200, 'output_tokens': 180, 'cached_input_tokens': 1024,
            'provider_request_id': 'resp_abc123', 'latency_ms': 840,
            'executed_at': (timezone.now() - timedelta(minutes=1)).isoformat(),
        }
        body.update(overrides)
        return body

    def post(self, body, credential=None, secret=SECRET, raw=None):
        data = raw if raw is not None else encode(body)
        headers = sign_headers(path=PATH, body=data, key_id=(credential or self.credential).key_id,
                               secret=secret, method='POST')
        return self.client.generic('POST', PATH, data=data, content_type='application/json', **headers)

    def codes(self, response):
        return {(f['field'], f['code']) for f in response.json()['error']['fields']}


# ── Registro ─────────────────────────────────────────────────────────────────

@override_settings(**SETTINGS)
class RecordingTests(_TelemetryBase, TestCase):

    def test_valid_event_with_tokens(self):
        body = self.event()
        response = self.post(body)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json(), {'ok': True, 'result': 'recorded', 'event_id': body['event_id']})
        self.assertEqual(response['Cache-Control'], 'no-store')
        row = AgentAIExecution.objects.get()
        self.assertEqual((row.business_id, row.agent_instance_id, row.channel_id), (self.biz.pk, self.instance.pk, self.channel.pk))
        self.assertEqual((row.input_tokens, row.output_tokens, row.cached_input_tokens, row.latency_ms),
                         (1200, 180, 1024, 840))
        self.assertEqual((row.provider, row.model, row.operation, row.status, row.error_code),
                         ('openai', 'gpt-4.1-mini', 'response', 'succeeded', None))
        self.assertIsNotNone(row.received_at)

    def test_failed_and_unknown_executions(self):
        failed = self.event(status='failed', error_code='timeout', input_tokens=None, output_tokens=None,
                            cached_input_tokens=None, provider_request_id=None)
        self.assertEqual(self.post(failed).status_code, 201)
        unknown = self.event(status='unknown', error_code=None, input_tokens=None, output_tokens=None,
                             cached_input_tokens=None, latency_ms=None, provider_request_id=None)
        self.assertEqual(self.post(unknown).status_code, 201)
        rows = {r.status: r for r in AgentAIExecution.objects.all()}
        self.assertEqual(rows['failed'].error_code, 'timeout')
        self.assertIsNone(rows['unknown'].input_tokens)  # unknown, not zero
        self.assertIsNone(rows['unknown'].latency_ms)
        # A failure needs a normalized code; a success cannot carry one.
        self.assertIn(('error_code', 'required'), self.codes(self.post(self.event(status='failed'))))
        self.assertIn(('error_code', 'not_allowed_on_success'),
                      self.codes(self.post(self.event(error_code='timeout'))))
        self.assertIn(('error_code', 'invalid_choice'),
                      self.codes(self.post(self.event(status='failed', error_code='Boom!'))))

    def test_zero_is_kept_distinct_from_unknown(self):
        self.assertEqual(self.post(self.event(input_tokens=0, output_tokens=0, cached_input_tokens=0, latency_ms=0)).status_code, 201)
        row = AgentAIExecution.objects.get()
        self.assertEqual((row.input_tokens, row.output_tokens, row.cached_input_tokens, row.latency_ms), (0, 0, 0, 0))
        omitted = self.event()
        for key in ('interaction_id', 'cached_input_tokens', 'provider_request_id', 'latency_ms', 'error_code'):
            omitted.pop(key)
        self.assertEqual(self.post(omitted).status_code, 201)
        self.assertIsNone(AgentAIExecution.objects.get(event_id=omitted['event_id']).cached_input_tokens)

    def test_several_attempts_of_one_interaction_with_commercial_link(self):
        self.reception(self.biz)
        conversation = 'wac1_' + uuid.uuid4().hex
        lead = Lead.objects.create(business=self.biz, source='whatsapp_agent')
        make_state(lead, self.channel, external_conversation_id=conversation)
        interaction = uuid.uuid4()
        occurred = timezone.now() - timedelta(minutes=5)
        from apps.appointments.services.ai_usage_authorization import authorize_ai_interaction

        authorize_ai_interaction(agent_instance=self.instance, conversation_id=conversation,
                                 interaction_id=interaction, occurred_at=occurred)
        receipt = AppointmentAIUsageAuthorization.objects.get(business=self.biz, interaction_id=interaction)
        for status, error in (('failed', 'rate_limited'), ('failed', 'timeout'), ('succeeded', None)):
            self.assertEqual(self.post(self.event(interaction_id=str(interaction), status=status, error_code=error)).status_code, 201)
        rows = AgentAIExecution.objects.filter(interaction_id=interaction)
        self.assertEqual(rows.count(), 3)
        self.assertEqual(set(rows.values_list('authorization_id', flat=True)), {receipt.pk})
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=self.biz).count(), 1)  # still one commercial session

    def test_interaction_without_commercial_receipt_is_not_forced(self):
        interaction = str(uuid.uuid4())
        self.assertEqual(self.post(self.event(interaction_id=interaction)).status_code, 201)
        row = AgentAIExecution.objects.get()
        self.assertEqual((str(row.interaction_id), row.authorization_id), (interaction, None))


# ── Idempotencia ─────────────────────────────────────────────────────────────

@override_settings(**SETTINGS)
class IdempotencyTests(_TelemetryBase, TestCase):

    def test_identical_replay_and_conflict(self):
        body = self.event()
        self.assertEqual(self.post(body).status_code, 201)
        replay = self.post(body)  # new request id (HMAC nonce), same event
        self.assertEqual((replay.status_code, replay.json()['result']), (200, 'duplicate'))
        same_instant_other_offset = dict(body, executed_at=timezone.datetime.fromisoformat(body['executed_at'])
                                         .astimezone(timezone.get_fixed_timezone(-180)).isoformat())
        self.assertEqual(self.post(same_instant_other_offset).json()['result'], 'duplicate')
        conflict = self.post(dict(body, output_tokens=181))
        self.assertEqual((conflict.status_code, conflict.json()['error']['code']), (409, 'idempotency_conflict'))
        row = AgentAIExecution.objects.get()
        self.assertEqual(row.output_tokens, 180)  # history never rewritten

    def test_event_ids_are_scoped_per_instance_and_rows_are_immutable(self):
        body = self.event()
        self.post(body)
        other_instance = make_instance(f'agent-{uuid.uuid4().hex[:12]}')
        other_credential = make_credential(other_instance, key_id=uuid.uuid4().hex)
        other_channel = self.channel_for(other_instance, _business())
        response = self.post(dict(body, phone_number_id=other_channel.phone_number_id), credential=other_credential)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AgentAIExecution.objects.count(), 2)
        row = AgentAIExecution.objects.filter(agent_instance=self.instance).get()
        row.output_tokens = 1
        with self.assertRaises(ValueError):
            row.save()
        with self.assertRaises(ValueError):
            row.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AgentAIExecution.objects.bulk_create([AgentAIExecution(
                event_id=row.event_id, business=row.business, agent_instance=row.agent_instance, channel=row.channel,
                provider='openai', model='m', operation='response', status='succeeded', executed_at=row.executed_at,
                payload_hash='0' * 64, request_id=uuid.uuid4(),
            )])


# ── Autenticación y tenant ───────────────────────────────────────────────────

@override_settings(**SETTINGS)
class TenantResolutionTests(_TelemetryBase, TestCase):

    def test_invalid_hmac_and_revoked_credentials(self):
        self.assertEqual(self.post(self.event(), secret='wrong-secret-0123456789').status_code, 401)
        AgentCredential.objects.filter(pk=self.credential.pk).update(status='revoked', revoked_at=timezone.now())
        self.assertEqual(self.post(self.event()).status_code, 401)
        retiring = make_credential(self.instance, key_id=uuid.uuid4().hex, status='retiring')
        self.assertEqual(self.post(self.event(), credential=retiring).status_code, 201)  # same instance, rotated key
        self.assertEqual(AgentAIExecution.objects.count(), 1)

    def test_channel_of_another_instance_and_business_id_never_trusted(self):
        foreign = self.channel_for(make_instance(f'agent-{uuid.uuid4().hex[:12]}'), _business())
        response = self.post(self.event(channel=foreign))
        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'channel_not_authorized'))
        other_biz = _business()
        response = self.post(self.event(business_id=other_biz.pk))
        self.assertIn(('business_id', 'unknown_field'), self.codes(response))
        second = self.channel_for(self.instance, other_biz)
        self.assertEqual(self.post(self.event(channel=second)).status_code, 201)
        self.assertEqual(AgentAIExecution.objects.get().business_id, other_biz.pk)  # from the channel, not the agent
        self.assertFalse(AgentAIExecution.objects.filter(business=self.biz).exists())

    def test_disabled_channel_accepts_only_results_from_its_active_period(self):
        disabled_at = timezone.now() - timedelta(hours=1)
        AgentChannel.objects.filter(pk=self.channel.pk).update(is_active=False, deactivated_at=disabled_at)
        late = self.post(self.event(executed_at=(disabled_at - timedelta(minutes=5)).isoformat()))
        self.assertEqual(late.status_code, 201)
        after = self.post(self.event(executed_at=(disabled_at + timedelta(minutes=5)).isoformat()))
        self.assertEqual((after.status_code, after.json()['error']['code']), (403, 'channel_not_authorized'))
        before_creation = self.post(self.event(executed_at=(self.channel.created_at - timedelta(minutes=1)).isoformat()))
        self.assertEqual(before_creation.status_code, 403)

    def test_reassigned_phone_number_keeps_attribution_by_execution_instant(self):
        moved_at = timezone.now() - timedelta(hours=2)
        AgentChannel.objects.filter(pk=self.channel.pk).update(is_active=False, deactivated_at=moved_at)
        new_instance = make_instance(f'agent-{uuid.uuid4().hex[:12]}')
        new_credential = make_credential(new_instance, key_id=uuid.uuid4().hex)
        new_biz = _business()
        new_channel = self.channel_for(new_instance, new_biz, phone=self.channel.phone_number_id, created=moved_at)
        before = (moved_at - timedelta(minutes=10)).isoformat()
        after = (moved_at + timedelta(minutes=10)).isoformat()
        self.assertEqual(self.post(self.event(executed_at=before)).status_code, 201)  # old owner, late result
        self.assertEqual(self.post(self.event(executed_at=after)).status_code, 403)
        self.assertEqual(self.post(self.event(channel=new_channel, executed_at=before), credential=new_credential).status_code, 403)
        self.assertEqual(self.post(self.event(channel=new_channel, executed_at=after), credential=new_credential).status_code, 201)
        self.assertEqual(
            sorted(AgentAIExecution.objects.values_list('business_id', 'channel_id')),
            sorted([(self.biz.pk, self.channel.pk), (new_biz.pk, new_channel.pk)]),
        )

    @override_settings(AGENT_AI_TELEMETRY_ENABLED=False)
    def test_flag_off_is_unavailable(self):
        response = self.post(self.event())
        self.assertEqual((response.status_code, response.json()['error']['retryable']), (503, True))
        self.assertFalse(AgentAIExecution.objects.exists())


# ── Validación ───────────────────────────────────────────────────────────────

@override_settings(**SETTINGS)
class ValidationTests(_TelemetryBase, TestCase):

    def test_invalid_timestamps(self):
        now = timezone.now()
        cases = {
            '2026-11-01T10:00:00': 'invalid_datetime',
            'yesterday': 'invalid_datetime',
            (now + timedelta(minutes=10)).isoformat(): 'in_future',
            (now - timedelta(days=31)).isoformat(): 'too_old',
        }
        for value, code in cases.items():
            with self.subTest(value=value):
                self.assertIn(('executed_at', code), self.codes(self.post(self.event(executed_at=value))))
        self.assertIn(('executed_at', 'invalid_datetime'), self.codes(self.post(self.event(executed_at=1732000000))))
        self.assertFalse(AgentAIExecution.objects.exists())

    def test_invalid_numbers_and_formats(self):
        for key in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'latency_ms'):
            for value in (-1, 1.5, True, '10', 10**12):
                with self.subTest(key=key, value=value):
                    body = self.event(**{key: value})
                    if key == 'cached_input_tokens' and value == 10**12:
                        body['input_tokens'] = 10**12
                    self.assertIn((key, 'invalid_number'), self.codes(self.post(body)))
        self.assertIn(('cached_input_tokens', 'exceeds_input_tokens'),
                      self.codes(self.post(self.event(input_tokens=10, cached_input_tokens=11))))
        self.assertIn(('cached_input_tokens', 'exceeds_input_tokens'),
                      self.codes(self.post(self.event(input_tokens=None, cached_input_tokens=11))))
        for key, value, code in (('event_id', 'not-a-uuid', 'invalid_uuid'), ('provider', 'acme', 'invalid_choice'),
                                 ('operation', 'image', 'invalid_choice'), ('model', 'gpt 4 ' + 'x' * 70, 'invalid_format'),
                                 ('provider_request_id', 'a' * 200, 'invalid_format'), ('phone_number_id', '+54 11', 'invalid_format'),
                                 ('status', 'ok', 'invalid_choice')):
            with self.subTest(key=key):
                self.assertIn((key, code), self.codes(self.post(self.event(**{key: value}))))
        missing = self.event()
        missing.pop('model')
        self.assertIn(('model', 'required'), self.codes(self.post(missing)))
        self.assertEqual(self.post(None, raw=b'[1, 2]').status_code, 400)
        self.assertFalse(AgentAIExecution.objects.exists())

    def test_no_pii_or_content_in_the_contract(self):
        for key in ('prompt', 'response', 'messages', 'patient_name', 'phone_e164', 'raw', 'business_id'):
            with self.subTest(key=key):
                response = self.post(self.event(**{key: SENTINEL}))
                self.assertIn((key, 'unknown_field'), self.codes(response))
                self.assertNotIn(SENTINEL, response.content.decode())
        with self.assertLogs('apps.leads', level='INFO') as logs:
            self.post(self.event(model=SENTINEL + ' bad'))
            self.post(self.event())
        self.assertNotIn(SENTINEL, '\n'.join(logs.output))
        columns = {f.name for f in AgentAIExecution._meta.get_fields()}
        for forbidden in ('prompt', 'response', 'messages', 'content', 'patient_name', 'phone_e164', 'payload'):
            self.assertNotIn(forbidden, columns)


# ── Independencia comercial ──────────────────────────────────────────────────

@override_settings(**SETTINGS)
class CommercialIndependenceTests(_TelemetryBase, TestCase):

    def _commercial(self):
        return tuple(m.objects.count() for m in (
            AppointmentAIUsageSession, AppointmentAIUsageCharge, AppointmentAIUsageAuthorization,
            AppointmentAIUsageSettlement,
        ))

    def test_late_results_after_suspension_and_no_commercial_change(self):
        sub = self.reception(self.biz)
        self.seed(sub, 300)  # allowance exhausted
        SubscriptionV2.objects.filter(pk=sub.pk).update(status='suspended')
        self.biz.status = 'suspended'
        self.biz.save(update_fields=['status'])
        before, stamp = self._commercial(), SubscriptionV2.objects.get(pk=sub.pk).updated_at
        for _ in range(3):
            self.assertEqual(self.post(self.event(executed_at=(timezone.now() - timedelta(days=2)).isoformat())).status_code, 201)
        self.assertEqual(self._commercial(), before)
        self.assertEqual(SubscriptionV2.objects.get(pk=sub.pk).updated_at, stamp)
        self.assertEqual(AgentAIExecution.objects.filter(business=self.biz).count(), 3)

    def test_without_any_ai_subscription_telemetry_grants_nothing(self):
        self.assertEqual(self.post(self.event()).status_code, 201)
        self.assertEqual(self._commercial(), (0, 0, 0, 0))
        from apps.billing.services.ai_source import resolve_ai_source

        self.assertIsNone(resolve_ai_source(self.biz).subscription)
