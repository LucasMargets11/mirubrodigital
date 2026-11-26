"""PROD-02E4C — métricas operativas de WhatsApp por Business (solo lectura).

Fuente: lo que el agente sincroniza (`LeadAgentMessage`, `LeadAgentState`),
más `LeadActivity` (takeover) y `LeadStaffMessage` (outbox de recepción).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession
from apps.billing.models import SubscriptionV2
from apps.leads.models import AgentChannel, Lead, LeadActivity, LeadAgentMessage, LeadAgentState, LeadStaffMessage
from apps.leads.services.whatsapp_metrics import (
    MAX_RANGE_DAYS, WhatsAppMetricsRangeError, whatsapp_metrics,
)
from apps.leads.tests.agent_client import T0, T1, bump, make_payload, signed_put
from apps.leads.tests.factories import TEST_KEY, make_business, make_channel, make_credential, make_instance, make_state

UTC = dt_timezone.utc
DAY = datetime(2026, 10, 4, tzinfo=UTC)


def at(hours):
    return DAY + timedelta(hours=hours)


class _Base:

    def setUp(self):
        self.biz = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        self.instance = make_instance(f'agent-{uuid.uuid4().hex[:10]}')
        self.channel = make_channel(self.instance, self.biz, phone_number_id=str(uuid.uuid4().int)[:15])

    def lead(self, channel=None, biz=None, **state):
        channel = channel or self.channel
        lead = Lead.objects.create(business=biz or channel.business, source='whatsapp_agent')
        state.setdefault('external_conversation_id', 'wac1_' + uuid.uuid4().hex)
        make_state(lead, channel, **state)
        return lead

    def msg(self, lead, sender, hours, status=None, message_id=None):
        return LeadAgentMessage.objects.create(
            lead=lead, external_message_id=message_id or uuid.uuid4().hex, sender=sender,
            role='user' if sender == 'patient' else 'assistant', text='texto', sent_at=at(hours), status=status,
        )

    def metrics(self, biz=None, start=None, end=None):
        return whatsapp_metrics(biz or self.biz, start=start or DAY, end=end or DAY + timedelta(days=1))


class MetricsTests(_Base, TestCase):

    def test_inbound_outbound_senders_and_statuses(self):
        lead = self.lead()
        self.msg(lead, 'patient', 1)
        self.msg(lead, 'patient', 2)
        self.msg(lead, 'bot', 1.1, 'read')
        self.msg(lead, 'bot', 2.1, 'delivered')
        self.msg(lead, 'bot', 2.2, None)
        self.msg(lead, 'staff', 3, 'sent')
        self.msg(lead, 'staff', 3.1, 'failed')
        body = self.metrics()
        self.assertTrue(body['available'])
        self.assertEqual(body['totals'], {'messages': 7, 'inbound': 2, 'outbound': 5,
                                          'ai_generated': None, 'automated_non_ai': None})
        self.assertEqual(body['by_sender'], {'patient': 2, 'bot': 3, 'staff': 2})
        self.assertEqual(body['outbound_status'], {'semantics': 'last_synced_status', 'sent': 1, 'delivered': 1,
                                                   'read': 1, 'failed': 1, 'unknown': 1})
        self.assertEqual(sum(v for k, v in body['outbound_status'].items() if k != 'semantics'),
                         body['totals']['outbound'])  # one status per message, no double count
        self.assertEqual(body['conversations'], {'with_activity': 1, 'leads_with_activity': 1})

    def test_unknown_is_not_zero(self):
        no_channel = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        body = self.metrics(no_channel)
        self.assertFalse(body['available'])
        self.assertIsNone(body['totals']['messages'])
        self.assertIsNone(body['handoffs']['requested'])
        self.assertTrue(all(d['inbound'] is None for d in body['daily']))
        # Channel but nothing ever synced: still unknown
        make_channel(make_instance(f'agent-{uuid.uuid4().hex[:10]}'), no_channel, phone_number_id='555000111')
        self.assertIsNone(self.metrics(no_channel)['totals']['messages'])
        # Synced but quiet day: a real zero
        self.lead()
        body = self.metrics()
        self.assertEqual((body['available'], body['totals']['messages']), (True, 0))

    def test_same_message_in_two_episodes_counts_once_with_its_best_status(self):
        conversation = 'wac1_' + uuid.uuid4().hex
        old = self.lead(external_conversation_id=conversation)
        new = self.lead(external_conversation_id=conversation)
        self.msg(old, 'bot', 5, 'sent', message_id='m-boundary')
        self.msg(new, 'bot', 5, 'read', message_id='m-boundary')
        self.msg(new, 'patient', 6)
        body = self.metrics()
        self.assertEqual(body['totals']['messages'], 2)
        self.assertEqual((body['outbound_status']['read'], body['outbound_status']['sent']), (1, 0))
        self.assertEqual(body['conversations'], {'with_activity': 1, 'leads_with_activity': 2})

    def test_range_boundaries_and_daily_activity_in_business_timezone(self):
        lead = self.lead()
        self.msg(lead, 'patient', -0.5)   # before start
        self.msg(lead, 'patient', 0)      # start included
        self.msg(lead, 'bot', 23.99)
        self.msg(lead, 'bot', 24)         # end excluded
        body = self.metrics()
        self.assertEqual(body['totals']['messages'], 2)
        # Buenos Aires (UTC-3): [00:00Z, 24:00Z) spans two local dates
        self.assertEqual(body['timezone'], 'America/Argentina/Buenos_Aires')
        self.assertEqual([(d['date'], d['inbound'], d['outbound']) for d in body['daily']],
                         [('2026-10-03', 1, 0), ('2026-10-04', 0, 1)])

    def test_range_validation(self):
        for start, end in ((DAY, DAY), (DAY, DAY - timedelta(hours=1)),
                           (DAY, DAY + timedelta(days=MAX_RANGE_DAYS + 1)),
                           (DAY.replace(tzinfo=None), DAY + timedelta(days=1))):
            with self.subTest(start=start, end=end), self.assertRaises(WhatsAppMetricsRangeError):
                whatsapp_metrics(self.biz, start=start, end=end)

    def test_handoffs_takeovers_and_staff_outbox(self):
        self.lead(handoff_requested=True, handoff_requested_at=at(2), handoff_paused_at=at(2.5))
        self.lead(handoff_requested=True, handoff_requested_at=at(30))  # outside the range
        lead = self.lead()
        for kind, hours in ((LeadActivity.Kind.TAKEOVER_APPLIED, 3), (LeadActivity.Kind.RELEASE_APPLIED, 4),
                            (LeadActivity.Kind.TAKEOVER_REQUESTED, 3)):
            LeadActivity.objects.create(business=self.biz, lead=lead, kind=kind, created_at=at(hours))
        LeadStaffMessage.objects.create(lead=lead, text='hola', occurred_at=at(3), status='pending',
                                        next_attempt_at=at(3))
        LeadStaffMessage.objects.create(lead=lead, text='hola', occurred_at=at(3.2), status='delivered',
                                        result='queued', delivered_at=at(3.3), message_id='bot-msg-1')
        LeadStaffMessage.objects.create(lead=lead, text='hola', occurred_at=at(3.4), status='failed',
                                        failed_at=at(3.5))
        body = self.metrics()
        self.assertEqual(body['handoffs'], {'requested': 1, 'bot_paused_for_reception': 1,
                                            'takeovers_applied': 1, 'releases_applied': 1})
        self.assertEqual(body['staff_messages'], {'semantics': 'mirubro_outbox_to_agent', 'requested': 3,
                                                  'queued_in_agent': 1, 'pending': 1, 'failed': 1})

    def test_isolation_between_businesses_and_reassigned_channels(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        old_lead = self.lead()
        self.msg(old_lead, 'patient', 1)
        # The number moves to another Business on another instance
        AgentChannel.objects.filter(pk=self.channel.pk).update(is_active=False, deactivated_at=at(2))
        new_channel = make_channel(make_instance(f'agent-{uuid.uuid4().hex[:10]}'), other,
                                   phone_number_id=self.channel.phone_number_id)
        new_lead = self.lead(channel=new_channel)
        self.msg(new_lead, 'patient', 3, message_id='shared-id')
        self.msg(new_lead, 'bot', 3.1, 'read')
        mine, theirs = self.metrics(), self.metrics(other)
        self.assertEqual((mine['totals']['messages'], theirs['totals']['messages']), (1, 2))
        self.assertEqual([c['channel_id'] for c in mine['channels']], [str(self.channel.pk)])
        self.assertEqual(mine['channels'][0]['is_active'], False)
        self.assertEqual([c['channel_id'] for c in theirs['channels']], [str(new_channel.pk)])
        # A Lead of A attached to B's channel (inconsistent data) is never counted for A
        # (save() refuses it; simulated with a raw update, as bulk paths could)
        stray = self.lead()
        LeadAgentState.objects.filter(lead=stray).update(channel=new_channel)
        self.msg(stray, 'patient', 4)
        self.assertEqual(self.metrics()['totals']['messages'], 1)

    def test_read_only_and_no_commercial_effect(self):
        lead = self.lead()
        self.msg(lead, 'patient', 1)
        self.msg(lead, 'bot', 1.1, 'read')
        before = tuple(m.objects.count() for m in (
            AppointmentAIUsageSession, AppointmentAIUsageCharge, AppointmentAIUsageAuthorization, SubscriptionV2,
            LeadAgentMessage, Lead,
        ))
        with CaptureQueriesContext(connection) as queries:
            self.metrics()
        sql = ' '.join(q['sql'].upper() for q in queries.captured_queries)
        for verb in ('INSERT ', 'UPDATE ', 'DELETE ', 'FOR UPDATE'):
            self.assertNotIn(verb, sql)
        after = tuple(m.objects.count() for m in (
            AppointmentAIUsageSession, AppointmentAIUsageCharge, AppointmentAIUsageAuthorization, SubscriptionV2,
            LeadAgentMessage, Lead,
        ))
        self.assertEqual(before, after)

    def test_no_message_text_or_patient_data_in_the_contract(self):
        lead = self.lead(patient_name='Ana Pérez SENTINEL', phone_e164='+5491112345678')
        LeadAgentMessage.objects.create(lead=lead, external_message_id='x1', sender='patient', role='user',
                                        text='SECRET_PATIENT_TEXT', sent_at=at(1))
        text = str(self.metrics())
        for secret in ('SECRET_PATIENT_TEXT', 'SENTINEL', '+5491112345678', 'x1'):
            self.assertNotIn(secret, text)


@override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class ReceiverPathTests(_Base, TestCase):
    """Through the real signed lead.sync: retries and successive statuses never double count."""

    def test_sync_retries_and_status_progression(self):
        client = APIClient()
        credential = make_credential(self.instance, key_id=f'key-{uuid.uuid4().hex[:8]}')

        def message(status):
            return [
                {'external_message_id': 'p-1', 'role': 'user', 'sender': 'patient', 'text': 'Hola',
                 'sent_at': T0, 'status': None},
                {'external_message_id': 'b-1', 'role': 'assistant', 'sender': 'bot', 'text': 'Buen día',
                 'sent_at': T1, 'status': status},
            ]

        payload = make_payload(agent_instance_id=self.instance.external_id, business_id=self.biz.pk,
                               phone_number_id=self.channel.phone_number_id, messages=message('sent'))
        for _ in range(2):  # HTTP retry of the same revision (new request id)
            self.assertEqual(signed_put(client, payload, key_id=credential.key_id).status_code // 100, 2)
        for version, status in ((2, 'delivered'), (3, 'read')):
            self.assertEqual(
                signed_put(client, bump(payload, version, messages=message(status)), key_id=credential.key_id)
                .status_code // 100, 2,
            )
        body = self.metrics()
        self.assertEqual((body['totals']['messages'], body['totals']['inbound'], body['totals']['outbound']), (2, 1, 1))
        self.assertEqual(body['outbound_status'], {'semantics': 'last_synced_status', 'sent': 0, 'delivered': 0,
                                                   'read': 1, 'failed': 0, 'unknown': 0})
        self.assertEqual(LeadAgentMessage.objects.filter(lead__business=self.biz).count(), 2)
        self.assertIsInstance(timezone.now(), datetime)
