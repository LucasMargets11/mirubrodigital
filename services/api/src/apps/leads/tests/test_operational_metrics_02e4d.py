"""PROD-02E4D — métricas agregadas de ejecuciones IA, costos estimados y API admin.

Las tarifas de estos tests son FIXTURES DE PRUEBA, no precios reales.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.tests.test_reception_rbac_02c import _client, _member
from apps.appointments.models import AppointmentAIUsageCharge, AppointmentAIUsageSession
from apps.billing.models import SubscriptionV2
from apps.billing.tests.test_admin_ai_usage_02e3b import _staff
from apps.billing.tests.test_reception_service_02b import _superadmin
from apps.leads.models import AgentAIExecution, AIProviderRate, Lead, LeadAgentMessage
from apps.leads.services.ai_execution_metrics import P95_MIN_SAMPLES
from apps.leads.services.whatsapp_metrics import whatsapp_metrics
from apps.leads.tests.factories import make_business, make_channel, make_instance, make_state

UTC = dt_timezone.utc
# 2026-10-04 12:00 UTC = 09:00 Buenos Aires (the factories' Business timezone)
NOON = datetime(2026, 10, 4, 12, tzinfo=UTC)
PERIOD = '?date_from=2026-10-04&date_to=2026-10-04'
TEST_SOURCE = 'TEST FIXTURE — not a real provider price'


def url(business_id, query=PERIOD):
    return f'/api/v1/platform-admin/clients/{business_id}/operational-metrics/{query}'


class _Base:

    def setUp(self):
        self.biz = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        self.instance = make_instance(f'agent-{uuid.uuid4().hex[:10]}')
        self.channel = make_channel(self.instance, self.biz, phone_number_id=str(uuid.uuid4().int)[:15])
        self.api = APIClient()
        self.api.force_authenticate(_superadmin())

    def execution(self, *, channel=None, model='gpt-4.1-mini', status='succeeded', error_code=None,
                  input_tokens=1200, output_tokens=180, cached=1024, latency=800, at=NOON, operation='response'):
        channel = channel or self.channel
        return AgentAIExecution.objects.create(
            event_id=uuid.uuid4(), business=channel.business, agent_instance=channel.agent_instance, channel=channel,
            provider='openai', model=model, operation=operation, status=status, error_code=error_code,
            input_tokens=input_tokens, output_tokens=output_tokens, cached_input_tokens=cached, latency_ms=latency,
            executed_at=at, payload_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(), request_id=uuid.uuid4(),
        )

    def rate(self, model='gpt-4.1-mini', input_rate='2', cached_rate='0.5', output_rate='8',
             valid_from=NOON - timedelta(days=365), valid_until=None, status='verified'):
        return AIProviderRate.objects.create(
            provider='openai', model=model, input_per_million=Decimal(input_rate),
            cached_input_per_million=Decimal(cached_rate), output_per_million=Decimal(output_rate),
            valid_from=valid_from, valid_until=valid_until, status=status, source_reference=TEST_SOURCE,
        )

    def get(self, business=None, query=PERIOD, client=None, expected=200):
        response = (client or self.api).get(url((business or self.biz).pk, query))
        self.assertEqual(response.status_code, expected, response.content)
        return response.json() if expected in (200, 400) else response


class AggregationTests(_Base, TestCase):

    def test_executions_statuses_models_tokens_and_latency(self):
        self.execution()
        self.execution(model='gpt-4.1', input_tokens=10, output_tokens=5, cached=0, latency=200)
        self.execution(status='failed', error_code='rate_limited', input_tokens=None, output_tokens=None,
                       cached=None, latency=50)
        self.execution(status='unknown', input_tokens=None, output_tokens=None, cached=None, latency=None)
        body = self.get()['openai_activity']
        self.assertEqual(body['executions'], 4)
        self.assertEqual(body['by_status'], {'succeeded': 2, 'failed': 1, 'unknown': 1})
        self.assertEqual(body['by_operation'], {'response': 4})
        self.assertEqual([(m['model'], m['executions']) for m in body['by_model']], [('gpt-4.1', 1), ('gpt-4.1-mini', 3)])
        self.assertEqual(body['tokens']['input'], {'total': 1210, 'reported': 2, 'unknown': 2})
        self.assertEqual(body['tokens']['cached_input'], {'total': 1024, 'reported': 2, 'unknown': 2})
        self.assertEqual(body['latency_ms'], {'reported': 3, 'average': 350.0, 'p95': None,
                                              'p95_min_samples': P95_MIN_SAMPLES})

    def test_unknown_metrics_stay_null_and_p95_needs_enough_samples(self):
        self.execution(status='unknown', input_tokens=None, output_tokens=None, cached=None, latency=None)
        body = self.get()['openai_activity']
        self.assertEqual(body['tokens']['input'], {'total': None, 'reported': 0, 'unknown': 1})
        self.assertIsNone(body['latency_ms']['average'])
        for latency in range(1, 21):
            self.execution(latency=latency * 10)
        self.assertEqual(self.get()['openai_activity']['latency_ms']['p95'], 190)  # nearest rank of 20

    def test_daily_buckets_in_business_timezone_and_bounds(self):
        self.execution(at=datetime(2026, 10, 4, 3, tzinfo=UTC))    # 00:00 local: first instant, included
        self.execution(at=datetime(2026, 10, 5, 2, 59, tzinfo=UTC))  # 23:59 local
        self.execution(at=datetime(2026, 10, 5, 3, tzinfo=UTC))    # next local day: excluded
        self.execution(at=datetime(2026, 10, 4, 2, 59, tzinfo=UTC))  # previous local day: excluded
        body = self.get()
        self.assertEqual(body['period'], {
            'timezone': 'America/Argentina/Buenos_Aires', 'date_from': '2026-10-04', 'date_to': '2026-10-04',
            'days': 1, 'start': '2026-10-04T00:00:00-03:00', 'end': '2026-10-05T00:00:00-03:00',
            'bounds': 'start inclusive, end exclusive (local midnights)',
        })
        self.assertEqual(body['openai_activity']['executions'], 2)
        self.assertEqual([d['executions'] for d in body['openai_activity']['daily']], [2])

    def test_period_validation_and_default(self):
        for query in ('?date_from=2026-10-05&date_to=2026-10-04', '?date_from=2026-01-01&date_to=2026-10-04',
                      '?date_from=04/10/2026', '?date_to=nope'):
            with self.subTest(query=query):
                self.assertEqual(self.get(query=query, expected=400)['code'], 'invalid_period')
        self.assertEqual(self.get(query='?date_from=2026-07-05&date_to=2026-10-04')['period']['days'], 92)
        self.assertEqual(self.get(query='')['period']['days'], 30)


class CostTests(_Base, TestCase):

    def test_formula_with_cached_and_uncached_input(self):
        self.rate()
        self.execution()  # (176*2 + 1024*0.5 + 180*8) / 1e6 = 2304 / 1e6
        costs = self.get()['openai_costs']
        self.assertEqual(costs['estimated_total'], '0.0023040000')
        self.assertEqual((costs['currency'], costs['kind'], costs['complete']), ('USD', 'estimated', True))
        self.assertEqual((costs['costed_executions'], costs['uncosted_executions']), (1, 0))
        self.assertEqual(costs['rates_used'][0]['source_reference'], TEST_SOURCE)

    def test_decimal_precision(self):
        self.rate(input_rate='0.100000', cached_rate='0.000000', output_rate='0.000000')
        for _ in range(7):
            self.execution(input_tokens=1, output_tokens=0, cached=0)  # 1e-7 each; floats would drift
        self.assertEqual(self.get()['openai_costs']['estimated_total'], '0.0000007000')

    def test_rate_by_model_and_validity_at_execution_time(self):
        cutover = NOON - timedelta(hours=1)
        self.rate(output_rate='8', valid_until=cutover)
        self.rate(output_rate='16', valid_from=cutover)
        self.rate(model='gpt-4.1', input_rate='10', cached_rate='10', output_rate='0')
        self.execution(input_tokens=0, cached=0, output_tokens=1_000_000, at=cutover - timedelta(minutes=1))  # $8
        self.execution(input_tokens=0, cached=0, output_tokens=1_000_000, at=cutover)  # $16
        self.execution(model='gpt-4.1', input_tokens=100_000, cached=0, output_tokens=7)  # $1
        costs = self.get()['openai_costs']
        self.assertEqual(costs['estimated_total'], '25.0000000000')
        self.assertEqual({(m['model'], m['estimated_cost']) for m in costs['by_model']},
                         {('gpt-4.1', '1.0000000000'), ('gpt-4.1-mini', '24.0000000000')})
        self.assertEqual(len(costs['rates_used']), 3)

    def test_missing_ambiguous_and_partial(self):
        self.rate()
        self.execution()  # costed
        self.execution(status='failed', error_code='timeout', input_tokens=None, output_tokens=None, cached=None)
        self.execution(cached=None)
        self.execution(model='gpt-unpriced')
        self.rate(model='gpt-draft', status='draft')
        self.execution(model='gpt-draft')  # draft rates are never used
        AIProviderRate.objects.bulk_create([AIProviderRate(  # overlapping data that bypassed save()
            provider='openai', model=m, input_per_million=1, cached_input_per_million=1, output_per_million=1,
            valid_from=NOON - timedelta(days=d), status='verified', source_reference=TEST_SOURCE,
        ) for m, d in (('gpt-dup', 2), ('gpt-dup', 1))])
        self.execution(model='gpt-dup')
        costs = self.get()['openai_costs']
        self.assertEqual(costs['uncosted_reasons'], {'tokens_unknown': 1, 'cached_tokens_unknown': 1,
                                                     'no_rate': 2, 'ambiguous_rate': 1})
        self.assertEqual((costs['complete'], costs['costed_executions'], costs['uncosted_executions'],
                          costs['estimated_total']), (False, 1, 5, '0.0023040000'))
        self.assertEqual(costs['daily'][0]['complete'], False)

    def test_failed_execution_with_tokens_is_costed_not_zero(self):
        self.rate()
        self.execution(status='failed', error_code='content_filtered', input_tokens=1000, cached=0, output_tokens=0)
        self.assertEqual(self.get()['openai_costs']['estimated_total'], '0.0020000000')

    def test_rate_integrity(self):
        rate = self.rate(valid_until=NOON)
        with self.assertRaises(ValidationError):
            self.rate(valid_from=NOON - timedelta(days=1))  # overlaps
        self.rate(valid_from=NOON)  # contiguous is fine
        rate.output_per_million = Decimal('99')
        with self.assertRaises(ValidationError):
            rate.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIProviderRate.objects.filter(pk=rate.pk).update(currency='EUR')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIProviderRate.objects.bulk_create([AIProviderRate(
                provider='openai', model='x', input_per_million=-1, cached_input_per_million=0,
                output_per_million=0, valid_from=NOON, source_reference=TEST_SOURCE,
            )])
        self.assertFalse(AIProviderRate.objects.exclude(source_reference=TEST_SOURCE).exists())  # nothing seeded


class EndpointTests(_Base, TestCase):

    def test_permissions_and_no_store(self):
        for role, expected in (('superadmin', 200), ('operations', 200), ('support_agent', 403),
                               ('content_admin', 403)):
            client = APIClient()
            client.force_authenticate(_staff(role))
            with self.subTest(role=role):
                self.assertEqual(client.get(url(self.biz.pk)).status_code, expected)
        self.assertEqual(_client(_member(self.biz, 'owner')).get(url(self.biz.pk)).status_code, 403)
        self.assertIn(APIClient().get(url(self.biz.pk)).status_code, (401, 403))
        response = self.api.get(url(self.biz.pk))
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(self.api.get(url(999999999)).status_code, 404)
        self.assertEqual(self.api.post(url(self.biz.pk), {}).status_code, 405)

    def test_isolation_between_businesses(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        other_channel = make_channel(make_instance(f'agent-{uuid.uuid4().hex[:10]}'), other,
                                     phone_number_id=str(uuid.uuid4().int)[:15])
        self.rate()
        self.execution()
        for _ in range(3):
            self.execution(channel=other_channel)
        AgentAIExecution.objects.filter(pk=self.execution(channel=other_channel).pk).update(business=self.biz)
        mine, theirs = self.get(), self.get(other)
        self.assertEqual((mine['openai_activity']['executions'], theirs['openai_activity']['executions']), (1, 3))
        self.assertEqual(mine['openai_costs']['estimated_total'], '0.0023040000')

    def test_history_of_suspended_business(self):
        SubscriptionV2.objects.create(
            business=self.biz, service_type='reception', plan_code='reception', usage_tier='reception_300',
            external_reference=f'SUB-{uuid.uuid4()}', status='suspended', provider='manual',
        )
        self.biz.status = 'suspended'
        self.biz.save(update_fields=['status'])
        self.execution()
        self.assertEqual(self.get()['openai_activity']['executions'], 1)

    def test_whatsapp_block_is_whatsapp_metrics_and_blocks_are_separate(self):
        lead = Lead.objects.create(business=self.biz, source='whatsapp_agent')
        make_state(lead, self.channel, external_conversation_id='wac1_' + uuid.uuid4().hex,
                   patient_name='Ana SENTINEL')
        LeadAgentMessage.objects.create(lead=lead, external_message_id='m1', sender='patient', role='user',
                                        text='SECRET_PATIENT_TEXT', sent_at=NOON)
        self.execution()
        body = self.get()
        expected = whatsapp_metrics(self.biz, start=datetime.fromisoformat(body['period']['start']),
                                    end=datetime.fromisoformat(body['period']['end']))
        self.assertEqual(body['whatsapp'], expected)
        self.assertEqual(body['whatsapp']['totals']['messages'], 1)
        self.assertIn('activity_is_not_current_connection_status', body['coverage']['notes'])
        text = str(body)
        for secret in ('SECRET_PATIENT_TEXT', 'SENTINEL', 'resp_', 'payload_hash'):
            self.assertNotIn(secret, text)

    def test_commercial_sessions_block_and_no_commercial_effect(self):
        sub = SubscriptionV2.objects.create(
            business=self.biz, service_type='reception', plan_code='reception', usage_tier='reception_300',
            external_reference=f'SUB-{uuid.uuid4()}', status='active', provider='manual',
        )
        period_start = datetime(2026, 10, 1, tzinfo=UTC)
        AppointmentAIUsageSession.objects.create(
            business=self.biz, subscription=sub, external_conversation_id='wac1_' + uuid.uuid4().hex,
            opening_interaction_id=uuid.uuid4(), started_at=NOON, expires_at=NOON + timedelta(hours=24),
            usage_period_start=period_start, usage_period_end=period_start + timedelta(days=31),
            usage_tier='reception_300',
        )
        self.execution()
        self.execution()
        before = (AppointmentAIUsageSession.objects.count(), AppointmentAIUsageCharge.objects.count(),
                  SubscriptionV2.objects.get(pk=sub.pk).updated_at)
        with CaptureQueriesContext(connection) as queries:
            body = self.get()
        self.assertEqual(body['commercial_ai_sessions']['started'], 1)
        self.assertEqual(body['openai_activity']['executions'], 2)  # attempts, not sessions
        sql = ' '.join(q['sql'].upper() for q in queries.captured_queries)
        for verb in ('INSERT ', 'UPDATE ', 'DELETE ', 'FOR UPDATE'):
            self.assertNotIn(verb, sql)
        self.assertEqual(before, (AppointmentAIUsageSession.objects.count(), AppointmentAIUsageCharge.objects.count(),
                                  SubscriptionV2.objects.get(pk=sub.pk).updated_at))
