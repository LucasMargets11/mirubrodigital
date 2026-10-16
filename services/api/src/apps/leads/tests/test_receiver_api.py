"""Receiver HTTP `PUT /api/v1/integrations/agent/leads/<uuid>/` (AGENT 02B)."""
from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin, _login, _turnos_business
from apps.customers.models import Customer
from apps.leads.models import AgentCredential, Lead, LeadAgentState, LeadNote
from apps.leads.services import receiver as receiver_module
from apps.notifications.models import BusinessNotification

from .agent_client import (
    PII_SENTINEL,
    T0,
    T1,
    T2,
    T3,
    bump,
    encode,
    handoff_requested,
    lead_path,
    make_payload,
    sign_headers,
    signed_put,
)
from .factories import SECRET, TEST_KEY, make_business, make_channel, make_credential, make_instance

User = get_user_model()

ENABLED = dict(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
INVALID_SIGNATURE_BODY = {
    'ok': False,
    'error': {'code': 'invalid_signature', 'message': 'Firma inválida.', 'retryable': False, 'fields': []},
}


@override_settings(**ENABLED)
class ReceiverTestBase(TestCase):
    PHONE_NUMBER_ID = '1234567890'

    def setUp(self):
        self.client = APIClient()
        self.business = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        self.instance = make_instance(f'dental-agent-{uuid.uuid4().hex[:8]}')
        self.credential = make_credential(self.instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        self.channel = make_channel(self.instance, self.business, phone_number_id=self.PHONE_NUMBER_ID)

    def payload(self, **overrides):
        data = dict(
            agent_instance_id=self.instance.external_id, business_id=self.business.pk,
            phone_number_id=self.PHONE_NUMBER_ID,
        )
        data.update(overrides)
        return make_payload(**data)

    def put(self, payload, **kwargs):
        kwargs.setdefault('key_id', self.credential.key_id)
        return signed_put(self.client, payload, **kwargs)

    def assertError(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.content)
        body = response.json()
        self.assertIs(body['ok'], False)
        self.assertEqual(body['error']['code'], code)
        self.assertIn('retryable', body['error'])
        self.assertIn('fields', body['error'])
        return body

    def assertResult(self, response, status_code, result, *, received, applied):
        self.assertEqual(response.status_code, status_code, response.content)
        body = response.json()
        self.assertEqual(body['ok'], True)
        self.assertEqual(body['result'], result)
        self.assertEqual(body['received_version'], received)
        self.assertEqual(body['applied_version'], applied)
        return body

    def state(self, payload) -> LeadAgentState:
        return LeadAgentState.objects.select_related('lead').get(
            agent_instance=self.instance, external_lead_id=payload['external_lead_id'],
        )


# ── HMAC ─────────────────────────────────────────────────────────────────────

class HmacAuthenticationTests(ReceiverTestBase):

    def test_valid_signature_creates(self):
        payload = self.payload()
        response = self.put(payload)
        body = self.assertResult(response, 201, 'created', received=1, applied=1)
        self.assertEqual(body['external_lead_id'], payload['external_lead_id'])
        self.assertEqual(body['mirubro_lead_id'], str(self.state(payload).lead_id))
        self.assertEqual(response['X-Request-Id'], response.wsgi_request.META['HTTP_X_REQUEST_ID'])

    def assertUnauthorized(self, response):
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.json(), INVALID_SIGNATURE_BODY)
        self.assertFalse(Lead.objects.exists())

    def test_invalid_signature(self):
        self.assertUnauthorized(self.put(self.payload(), secret='wrong-secret-0123456789abcdefghijk'))

    def test_tampered_body(self):
        payload = self.payload()
        headers = sign_headers(path=lead_path(payload['external_lead_id']), body=encode(payload), key_id=self.credential.key_id)
        tampered = encode({**payload, 'summary': 'otro'})
        response = self.client.generic('PUT', lead_path(payload['external_lead_id']), data=tampered,
                                       content_type='application/json', **headers)
        self.assertUnauthorized(response)

    def test_signature_bound_to_path(self):
        payload = self.payload()
        other = lead_path(uuid.uuid4())
        headers = sign_headers(path=other, body=encode(payload), key_id=self.credential.key_id)
        response = self.client.generic('PUT', lead_path(payload['external_lead_id']), data=encode(payload),
                                       content_type='application/json', **headers)
        self.assertUnauthorized(response)

    def test_old_timestamp(self):
        self.assertUnauthorized(self.put(self.payload(), timestamp=int(time.time()) - 301))

    def test_future_timestamp(self):
        self.assertUnauthorized(self.put(self.payload(), timestamp=int(time.time()) + 301))

    def test_timestamp_within_window_accepted(self):
        self.assertEqual(self.put(self.payload(), timestamp=int(time.time()) - 290).status_code, 201)

    def test_unknown_key(self):
        self.assertUnauthorized(self.put(self.payload(), key_id='no-such-key'))

    def test_revoked_credential(self):
        AgentCredential.objects.filter(pk=self.credential.pk).update(status='revoked', revoked_at=timezone.now())
        self.assertUnauthorized(self.put(self.payload()))

    def test_retiring_credential_still_valid(self):
        AgentCredential.objects.filter(pk=self.credential.pk).update(status='retiring')
        self.assertEqual(self.put(self.payload()).status_code, 201)

    def test_disabled_instance(self):
        self.instance.is_enabled = False
        self.instance.save()
        self.assertUnauthorized(self.put(self.payload()))

    def test_missing_or_malformed_headers(self):
        payload = self.payload()
        body = encode(payload)
        path = lead_path(payload['external_lead_id'])
        good = sign_headers(path=path, body=body, key_id=self.credential.key_id)
        for header in good:
            with self.subTest(missing=header):
                headers = {k: v for k, v in good.items() if k != header}
                self.assertUnauthorized(self.client.generic('PUT', path, data=body, content_type='application/json', **headers))
        for header, value in [('HTTP_X_AGENT_SIGNATURE', good['HTTP_X_AGENT_SIGNATURE'].upper()),
                              ('HTTP_X_AGENT_SIGNATURE', good['HTTP_X_AGENT_SIGNATURE'][3:]),
                              ('HTTP_X_AGENT_TIMESTAMP', '12.5'),
                              ('HTTP_X_REQUEST_ID', 'not-a-uuid')]:
            with self.subTest(header=header, value=value):
                headers = {**good, header: value}
                self.assertUnauthorized(self.client.generic('PUT', path, data=body, content_type='application/json', **headers))

    def test_all_auth_failures_look_identical(self):
        bodies = set()
        for response in (
            self.put(self.payload(), secret='x' * 40),
            self.put(self.payload(), key_id='no-such-key'),
            self.put(self.payload(), timestamp=1),
        ):
            bodies.add((response.status_code, response.content))
        self.assertEqual(len(bodies), 1)

    def test_no_jwt_session_or_business_header_needed_or_used(self):
        user = User.objects.create_user(username='intruder', password='x')
        self.client.force_authenticate(user=user)
        payload = self.payload()
        response = self.client.generic('PUT', lead_path(payload['external_lead_id']), data=encode(payload),
                                       content_type='application/json', HTTP_X_BUSINESS_ID=str(self.business.pk))
        self.assertEqual(response.status_code, 401)

    def test_only_put(self):
        payload = self.payload()
        path = lead_path(payload['external_lead_id'])
        headers = sign_headers(path=path, body=b'', key_id=self.credential.key_id, method='GET')
        response = self.client.get(path, **headers)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()['ok'], False)

    @override_settings(AGENT_INTEGRATION_ENABLED=False)
    def test_disabled_integration_returns_503(self):
        response = self.put(self.payload())
        body = self.assertError(response, 503, 'unavailable')
        self.assertTrue(body['error']['retryable'])
        self.assertFalse(Lead.objects.exists())

    @override_settings(AGENT_SECRET_ENCRYPTION_KEY='')
    def test_missing_encryption_key_fails_closed(self):
        self.assertError(self.put(self.payload()), 503, 'unavailable')
        self.assertFalse(Lead.objects.exists())


class ReplayProtectionTests(ReceiverTestBase):

    def test_first_accepted_same_request_id_rejected_other_accepted(self):
        payload = self.payload()
        request_id = str(uuid.uuid4())
        self.assertEqual(self.put(payload, request_id=request_id).status_code, 201)
        replay = self.put(payload, request_id=request_id)
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json(), INVALID_SIGNATURE_BODY)
        self.assertResult(self.put(payload), 200, 'duplicate', received=1, applied=1)

    def test_retry_with_new_timestamp_request_id_and_signature_is_valid(self):
        payload = self.payload()
        request_id = str(uuid.uuid4())
        now = int(time.time())
        self.assertEqual(self.put(payload, request_id=request_id, timestamp=now - 10).status_code, 201)
        # Mismo body/versión, nuevo timestamp + X-Request-Id + firma → retry válido.
        self.assertResult(self.put(payload, timestamp=now), 200, 'duplicate', received=1, applied=1)
        # Mismo X-Request-Id dentro de la ventana (aun re-firmado) → 401.
        self.assertEqual(self.put(payload, request_id=request_id, timestamp=now).json(), INVALID_SIGNATURE_BODY)

    def test_cache_failure_fails_open_for_nonce_only(self):
        payload = self.payload()
        with mock.patch('apps.leads.authentication.cache.add', side_effect=ConnectionError('redis down')):
            self.assertEqual(self.put(payload).status_code, 201)
            # La firma sigue siendo obligatoria.
            self.assertEqual(self.put(bump(payload, 2), secret='y' * 40).status_code, 401)
            self.assertEqual(self.put(bump(payload, 2), timestamp=1).status_code, 401)

    def test_nonce_key_and_ttl(self):
        request_id = str(uuid.uuid4())
        with mock.patch('apps.leads.authentication.cache.add', return_value=True) as add:
            self.put(self.payload(), request_id=request_id)
        add.assert_called_once_with(f'agent-req:{self.credential.key_id}:{request_id}', 1, timeout=600)


# ── Schema / request ────────────────────────────────────────────────────────

class RequestValidationTests(ReceiverTestBase):

    def test_validation_error_format_without_values(self):
        payload = self.payload(agent_status=PII_SENTINEL, phone_e164=PII_SENTINEL)
        body = self.assertError(self.put(payload), 400, 'validation_error')
        self.assertIn({'field': 'agent_status', 'code': 'invalid_choice'}, body['error']['fields'])
        self.assertNotIn(PII_SENTINEL, json.dumps(body))
        self.assertFalse(Lead.objects.exists())

    def test_event_id_mismatch_applies_nothing(self):
        payload = self.payload(event_id=str(uuid.uuid4()))
        body = self.assertError(self.put(payload), 400, 'validation_error')
        self.assertIn({'field': 'event_id', 'code': 'mismatch'}, body['error']['fields'])
        self.assertFalse(Lead.objects.exists())

    def test_path_body_mismatch(self):
        payload = self.payload()
        response = self.put(payload, path=lead_path(uuid.uuid4()))
        self.assertError(response, 400, 'invalid_request')
        self.assertFalse(Lead.objects.exists())

    def test_malformed_json(self):
        path = lead_path(uuid.uuid4())
        response = self.put(None, path=path, body=b'{"schema_version":')
        self.assertError(response, 400, 'invalid_request')

    def test_non_object_json(self):
        response = self.put(None, path=lead_path(uuid.uuid4()), body=b'[1,2]')
        self.assertError(response, 400, 'invalid_request')

    def test_agent_instance_mismatch_is_401(self):
        payload = self.payload(agent_instance_id='someone-else')
        self.assertEqual(self.put(payload).json(), INVALID_SIGNATURE_BODY)
        self.assertFalse(Lead.objects.exists())

    def test_unknown_fields_ignored_and_not_persisted(self):
        payload = self.payload()
        payload['transcript'] = PII_SENTINEL
        self.assertEqual(self.put(payload).status_code, 201)
        state = self.state(payload)
        self.assertNotIn(PII_SENTINEL, repr(LeadAgentState.objects.filter(pk=state.pk).values().get()))


# ── Tenant ──────────────────────────────────────────────────────────────────

class TenantResolutionTests(ReceiverTestBase):

    def test_valid_channel_resolves_business(self):
        payload = self.payload()
        self.assertEqual(self.put(payload).status_code, 201)
        state = self.state(payload)
        self.assertEqual(state.lead.business_id, self.business.pk)
        self.assertEqual(state.channel_id, self.channel.pk)

    def test_unknown_channel(self):
        self.assertError(self.put(self.payload(phone_number_id='999')), 403, 'channel_disabled')

    def test_inactive_channel(self):
        self.channel.is_active = False
        self.channel.deactivated_at = timezone.now()
        self.channel.save()
        self.assertError(self.put(self.payload()), 403, 'channel_disabled')

    def test_channel_of_other_instance(self):
        other = make_instance(f'other-agent-{uuid.uuid4().hex[:6]}')
        make_channel(other, self.business, phone_number_id='555')
        self.assertError(self.put(self.payload(phone_number_id='555')), 403, 'channel_disabled')
        self.assertFalse(Lead.objects.exists())

    def test_business_mismatch(self):
        other = make_business(f'other-{uuid.uuid4().hex[:6]}')
        self.assertError(self.put(self.payload(business_id=other.pk)), 409, 'business_mismatch')
        self.assertFalse(Lead.objects.exists())

    def test_business_inactive(self):
        for status in ('suspended', 'canceled', 'pending_activation'):
            self.business.status = status
            self.business.save(update_fields=['status'])
            with self.subTest(status=status):
                self.assertError(self.put(self.payload()), 403, 'business_inactive')
        self.assertFalse(Lead.objects.exists())

    def test_allowed_business_statuses(self):
        for status in ('onboarding', 'trialing', 'active', 'past_due'):
            self.business.status = status
            self.business.save(update_fields=['status'])
            with self.subTest(status=status):
                self.assertEqual(self.put(self.payload()).status_code, 201)


# ── Idempotencia ────────────────────────────────────────────────────────────

class IdempotencyTests(ReceiverTestBase):

    def test_full_lifecycle(self):
        v1 = self.payload()
        self.assertResult(self.put(v1), 201, 'created', received=1, applied=1)
        self.assertResult(self.put(v1), 200, 'duplicate', received=1, applied=1)
        self.assertError(self.put({**v1, 'summary': 'distinto'}), 409, 'version_conflict')
        v2 = bump(v1, 2, summary='v2', last_message_at=T2)
        self.assertResult(self.put(v2), 200, 'applied', received=2, applied=2)
        self.assertResult(self.put(v1), 200, 'stale', received=1, applied=2)
        state = self.state(v1)
        self.assertEqual(state.applied_version, 2)
        self.assertEqual(state.summary, 'v2')
        self.assertEqual(str(state.last_event_id), v2['event_id'])
        self.assertEqual(Lead.objects.count(), 1)

    def test_reordered_keys_and_unknown_fields_are_duplicate(self):
        v1 = self.payload()
        self.put(v1)
        variant = dict(reversed(list(v1.items())))
        variant['handoff'] = dict(reversed(list(v1['handoff'].items())))
        variant['unknown_future_field'] = {'x': 1}
        variant['sent_at'] = '2026-10-04T13:00:00Z'
        self.assertNotEqual(encode(variant), encode(v1))
        self.assertResult(self.put(variant), 200, 'duplicate', received=1, applied=1)

    def test_version_gap_allowed(self):
        v1 = self.payload()
        self.put(v1)
        self.assertResult(self.put(bump(v1, 8, summary='v8')), 200, 'applied', received=8, applied=8)

    def test_retry_after_lost_response_does_not_duplicate(self):
        v1 = self.payload()
        first = self.put(v1)
        retry = self.put(v1)  # nuevo request_id, mismo snapshot
        self.assertEqual(retry.json()['mirubro_lead_id'], first.json()['mirubro_lead_id'])
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(LeadAgentState.objects.count(), 1)

    def test_stale_and_duplicate_do_not_touch_row(self):
        v1 = self.payload()
        self.put(v1)
        self.put(bump(v1, 3))
        before = LeadAgentState.objects.filter(agent_instance=self.instance).values().get()
        self.put(v1)
        self.put(bump(v1, 3))
        self.assertEqual(LeadAgentState.objects.filter(agent_instance=self.instance).values().get(), before)

    def test_unique_lead_per_external_identity(self):
        v1 = self.payload()
        self.put(v1)
        self.put(bump(v1, 2))
        self.put(self.payload())  # otro external_lead_id → otro Lead
        self.assertEqual(Lead.objects.count(), 2)

    def test_creation_race_resolved_by_constraint(self):
        """Simula el perdedor de la carrera: la primera lectura no ve la fila,
        el insert choca con la constraint y se re-lee con select_for_update."""
        v1 = self.payload()
        first = self.put(v1)
        real_locked_state = receiver_module._locked_state
        calls = []

        def racing(*args, **kwargs):
            calls.append(1)
            return None if len(calls) == 1 else real_locked_state(*args, **kwargs)

        with mock.patch.object(receiver_module, '_locked_state', side_effect=racing):
            retry = self.put(v1)
            applied = self.put(bump(v1, 2))
        self.assertResult(retry, 200, 'duplicate', received=1, applied=1)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(retry.json()['mirubro_lead_id'], first.json()['mirubro_lead_id'])
        self.assertEqual(Lead.objects.count(), 1)


class ImmutableFieldTests(ReceiverTestBase):

    def test_each_immutable_field_conflicts(self):
        v1 = self.payload()
        self.put(v1)
        make_channel(self.instance, self.business, phone_number_id='777')
        changes = {
            'external_conversation_id': 'wac1_ffffffffffffffffffffffffffffffff',
            'previous_external_lead_id': str(uuid.uuid4()),
            'phone_e164': '+5491100000000',
            'opened_at': '2026-10-04T11:00:00Z',
            'phone_number_id': '777',
        }
        before = LeadAgentState.objects.filter(agent_instance=self.instance).values().get()
        for field, value in changes.items():
            with self.subTest(field=field):
                self.assertError(self.put(bump(v1, 2, **{field: value})), 409, 'version_conflict')
        self.assertEqual(LeadAgentState.objects.filter(agent_instance=self.instance).values().get(), before)

    def test_agent_instance_change_is_rejected_as_auth(self):
        # agent_instance_id ≠ instancia de la credencial → 401 (no llega a la fila).
        v1 = self.payload()
        self.put(v1)
        before = LeadAgentState.objects.filter(agent_instance=self.instance).values().get()
        other = make_instance(f'other-agent-{uuid.uuid4().hex[:6]}')
        response = self.put(bump(v1, 2, agent_instance_id=other.external_id))
        self.assertEqual(response.json(), INVALID_SIGNATURE_BODY)
        self.assertEqual(LeadAgentState.objects.filter(agent_instance=self.instance).values().get(), before)

    def test_external_lead_id_is_the_identity(self):
        # Otro external_lead_id es otro Lead (es la clave), nunca muta el existente.
        v1 = self.payload()
        self.put(v1)
        before = LeadAgentState.objects.filter(external_lead_id=v1['external_lead_id']).values().get()
        other = bump(v1, 2, external_lead_id=str(uuid.uuid4()))
        self.assertResult(self.put(other), 201, 'created', received=2, applied=2)
        self.assertEqual(LeadAgentState.objects.filter(external_lead_id=v1['external_lead_id']).values().get(), before)

    def test_business_change_is_business_mismatch(self):
        v1 = self.payload()
        self.put(v1)
        other = make_business(f'mov-{uuid.uuid4().hex[:6]}')
        # Mismo número reasignado a otro Business (desactivar + crear).
        self.channel.is_active = False
        self.channel.deactivated_at = timezone.now()
        self.channel.save()
        make_channel(self.instance, other, phone_number_id=self.PHONE_NUMBER_ID)
        self.assertError(self.put(bump(v1, 2, business_id=other.pk)), 409, 'business_mismatch')
        self.assertEqual(self.state(v1).lead.business_id, self.business.pk)

    def test_declared_business_not_matching_channel(self):
        v1 = self.payload()
        self.put(v1)
        other = make_business(f'mov-{uuid.uuid4().hex[:6]}')
        self.assertError(self.put(bump(v1, 2, business_id=other.pk)), 409, 'business_mismatch')


# ── Aislamiento CRM ─────────────────────────────────────────────────────────

class CrmIsolationTests(TurnosAgendaMixin, ReceiverTestBase):

    def test_new_version_never_touches_crm_fields(self):
        v1 = self.payload()
        self.put(v1)
        lead = self.state(v1).lead
        user = User.objects.create_user(username=f'u-{uuid.uuid4().hex[:6]}', password='x')
        customer = Customer.objects.create(business=self.business, name='Cliente', phone='1112345678')
        service, pro = self._agenda(self.business)
        appointment = self._appt(self.business, service, customer, timezone.now() + dt.timedelta(days=1), pro=pro)
        closed_at = timezone.now()
        Lead.objects.filter(pk=lead.pk).update(
            status='closed', outcome='booked', assigned_to=user, customer=customer, appointment=appointment,
            closed_at=closed_at, closed_by=user,
        )
        LeadNote.objects.create(lead=lead, author=user, body='nota humana')
        crm_before = Lead.objects.filter(pk=lead.pk).values(
            'status', 'outcome', 'assigned_to', 'customer', 'appointment', 'closed_at', 'closed_by', 'business',
        ).get()
        notes_before = list(LeadNote.objects.values())

        v2 = bump(v1, 2, agent_status='closed', closed_at=T3, close_reason='idle', last_message_at=T2, summary='nuevo')
        self.assertResult(self.put(v2), 200, 'applied', received=2, applied=2)

        crm_after = Lead.objects.filter(pk=lead.pk).values(*crm_before.keys()).get()
        self.assertEqual(crm_after, crm_before)
        self.assertEqual(crm_after['appointment'], appointment.pk)
        self.assertEqual(list(LeadNote.objects.values()), notes_before)
        state = self.state(v1)
        self.assertEqual(state.agent_status, 'closed')
        self.assertEqual(state.summary, 'nuevo')
        self.assertEqual(Customer.objects.filter(business=self.business).count(), 1)

    def test_created_lead_defaults(self):
        v1 = self.payload()
        self.put(v1)
        lead = self.state(v1).lead
        self.assertEqual((lead.source, lead.status, lead.outcome), ('whatsapp_agent', 'new', None))
        self.assertIsNone(lead.assigned_to_id)
        self.assertIsNone(lead.customer_id)
        self.assertIsNone(lead.appointment_id)
        self.assertIsNone(lead.needs_attention_at)
        self.assertFalse(Customer.objects.exists())


# ── Handoff ─────────────────────────────────────────────────────────────────

class HandoffTests(ReceiverTestBase):

    def notifications(self):
        return BusinessNotification.objects.filter(business=self.business, kind='agent_lead_handoff')

    def test_create_with_handoff_sets_attention_and_notifies(self):
        v1 = self.payload(handoff=handoff_requested('patient_asked_human'), urgency=True)
        with self.captureOnCommitCallbacks(execute=True):
            self.put(v1)
        state = self.state(v1)
        self.assertIsNotNone(state.lead.needs_attention_at)
        self.assertEqual(state.lead.status, 'new')
        [notification] = self.notifications()
        self.assertEqual(notification.severity, 'critical')
        # LEADS 04B.3: una por ciclo de atención (needs_attention_at).
        self.assertEqual(notification.dedupe_key, receiver_module.handoff_dedupe_key(state.lead))
        self.assertIsNone(notification.recipient_id)
        self.assertEqual(notification.related_object_type, 'lead')
        self.assertEqual(notification.related_object_id, str(state.lead_id))
        self.assertEqual(notification.action_url, '')

    def test_false_to_true_transition(self):
        v1 = self.payload()
        with self.captureOnCommitCallbacks(execute=True):
            self.put(v1)
        self.assertIsNone(self.state(v1).lead.needs_attention_at)
        self.assertFalse(self.notifications().exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.put(bump(v1, 2, handoff=handoff_requested('lead_ready')))
        self.assertIsNotNone(self.state(v1).lead.needs_attention_at)
        [notification] = self.notifications()
        self.assertEqual(notification.severity, 'info')

    def test_retry_and_true_to_true_do_not_duplicate(self):
        v1 = self.payload(handoff=handoff_requested('lead_ready'))
        with self.captureOnCommitCallbacks(execute=True):
            self.put(v1)
        first_attention = self.state(v1).lead.needs_attention_at
        with self.captureOnCommitCallbacks(execute=True):
            self.assertResult(self.put(v1), 200, 'duplicate', received=1, applied=1)  # retry
            v2 = bump(v1, 2, handoff=handoff_requested('lead_ready', 'urgency'), urgency=True,
                      reason='Otro motivo', preferred_time='Jueves', summary='cambió')
            self.assertResult(self.put(v2), 200, 'applied', received=2, applied=2)
        self.assertEqual(self.notifications().count(), 1)
        self.assertEqual(self.state(v1).lead.needs_attention_at, first_attention)
        self.assertEqual(self.state(v1).reason, 'Otro motivo')

    # ── 02B.1: recuperación de la notificación ──────────────────────────────

    def _put_with_failing_notification(self, payload):
        with mock.patch.object(receiver_module, 'create_business_notification', side_effect=RuntimeError('db down')):
            with self.assertLogs('apps.notifications.business_notifications', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    return self.put(payload)

    def test_failed_notification_is_recovered_by_duplicate(self):
        v1 = self.payload(handoff=handoff_requested('patient_asked_human'))
        first = self._put_with_failing_notification(v1)
        # El sync quedó aplicado aunque el aviso falló.
        self.assertResult(first, 201, 'created', received=1, applied=1)
        state = self.state(v1)
        self.assertTrue(state.handoff_requested)
        self.assertIsNotNone(state.lead.needs_attention_at)
        self.assertFalse(self.notifications().exists())
        # Mismo sync, request_id nuevo → duplicate repara el aviso.
        with self.captureOnCommitCallbacks(execute=True):
            self.assertResult(self.put(v1), 200, 'duplicate', received=1, applied=1)
        self.assertEqual(self.notifications().count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertResult(self.put(v1), 200, 'duplicate', received=1, applied=1)
        self.assertEqual(self.notifications().count(), 1)

    def test_failed_notification_on_transition_is_recovered_by_stale(self):
        v1 = self.payload()
        self.put(v1)
        v2 = bump(v1, 2, handoff=handoff_requested('lead_ready'))
        self.assertResult(self._put_with_failing_notification(v2), 200, 'applied', received=2, applied=2)
        self.assertFalse(self.notifications().exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertResult(self.put(v1), 200, 'stale', received=1, applied=2)
        self.assertEqual(self.notifications().count(), 1)

    def test_duplicate_without_handoff_creates_nothing(self):
        v1 = self.payload()
        with self.captureOnCommitCallbacks(execute=True):
            self.put(v1)
            self.put(v1)
        self.assertFalse(self.notifications().exists())

    def test_ensure_helper_is_idempotent_and_guarded(self):
        v1 = self.payload(handoff=handoff_requested('lead_ready'))
        self.put(v1)  # sin ejecutar on_commit
        lead_id = self.state(v1).lead_id
        first = receiver_module.ensure_agent_lead_handoff_notification(lead_id)
        second = receiver_module.ensure_agent_lead_handoff_notification(lead_id)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.notifications().count(), 1)
        # Sin needs_attention_at (p. ej. un humano lo limpió) no crea nada.
        self.notifications().delete()
        Lead.objects.filter(pk=lead_id).update(needs_attention_at=None)
        self.assertIsNone(receiver_module.ensure_agent_lead_handoff_notification(lead_id))
        self.assertFalse(self.notifications().exists())

    def test_handoff_on_closed_crm_lead_without_attention(self):
        v1 = self.payload()
        self.put(v1)
        lead = self.state(v1).lead
        user = User.objects.create_user(username=f'c-{uuid.uuid4().hex[:6]}', password='x')
        closed_at = timezone.now() - dt.timedelta(hours=1)
        Lead.objects.filter(pk=lead.pk).update(status='closed', outcome='other', closed_at=closed_at, closed_by=user)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertResult(self.put(bump(v1, 2, handoff=handoff_requested('urgency'), summary='nuevo')),
                              200, 'applied', received=2, applied=2)
        lead.refresh_from_db()
        self.assertEqual((lead.status, lead.outcome, lead.closed_at, lead.closed_by_id),
                         ('closed', 'other', closed_at, user.pk))
        self.assertIsNotNone(lead.needs_attention_at)
        self.assertEqual(self.state(v1).summary, 'nuevo')
        # LEADS 04B.3: un Lead cerrado no genera avisos de atención.
        self.assertFalse(self.notifications().exists())

    def test_does_not_reopen_closed_lead_nor_overwrite_attention(self):
        v1 = self.payload()
        self.put(v1)
        lead = self.state(v1).lead
        earlier = timezone.now() - dt.timedelta(days=1)
        Lead.objects.filter(pk=lead.pk).update(status='closed', outcome='other', needs_attention_at=earlier)
        with self.captureOnCommitCallbacks(execute=True):
            self.put(bump(v1, 2, handoff=handoff_requested('urgency')))
        lead.refresh_from_db()
        self.assertEqual((lead.status, lead.outcome), ('closed', 'other'))
        self.assertEqual(lead.needs_attention_at, earlier)
        self.assertIsNone(lead.assigned_to_id)

    def test_notification_content_has_no_pii(self):
        v1 = self.payload(
            patient_name=PII_SENTINEL, whatsapp_profile_name=PII_SENTINEL, reason=PII_SENTINEL,
            preferred_time=PII_SENTINEL, summary=PII_SENTINEL, phone_e164='+5491198765432',
            handoff=handoff_requested('urgency'),
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.put(v1)
        row = self.notifications().values().get()
        dumped = json.dumps(row, default=str)
        self.assertNotIn(PII_SENTINEL, dumped)
        self.assertNotIn('98765432', dumped)
        self.assertEqual(row['title'], 'Nueva consulta para recepción')

    def test_manager_with_view_leads_sees_kind(self):
        business = _turnos_business(slug=f'turnos-{uuid.uuid4().hex[:6]}')
        make_channel(self.instance, business, phone_number_id='4242')
        v1 = self.payload(business_id=business.pk, phone_number_id='4242', handoff=handoff_requested('lead_ready'))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.put(v1).status_code, 201)
        manager = APIClient()
        _login(manager, business, 'manager')
        response = manager.get('/api/v1/notifications/business/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row['kind'] for row in response.data['results']], ['agent_lead_handoff'])


# ── Logs sin PII ────────────────────────────────────────────────────────────

class LoggingTests(ReceiverTestBase):

    def assertNoSentinel(self, logs):
        joined = '\n'.join(logs.output)
        self.assertNotIn(PII_SENTINEL, joined)
        self.assertNotIn('v1=', joined)  # nunca la firma

    def test_success_and_errors_do_not_log_pii(self):
        pii = dict(patient_name=PII_SENTINEL, whatsapp_profile_name=PII_SENTINEL, reason=PII_SENTINEL,
                   preferred_time=PII_SENTINEL, summary=PII_SENTINEL)
        with self.assertLogs(level='DEBUG') as logs:
            v1 = self.payload(**pii)
            self.put(v1)                                                  # created
            self.put({**v1, 'phone_e164': PII_SENTINEL})                  # 400 validation
            self.put(self.payload(**pii), secret=PII_SENTINEL * 2)        # 401
            self.put(self.payload(**pii), key_id='bad key!')              # 401 malformed key
            self.put(bump(v1, 2, phone_e164='+5491100000000', **pii))     # 409
            self.put(self.payload(phone_number_id='999', **pii))          # 403
        self.assertNoSentinel(logs)
        joined = '\n'.join(logs.output)
        self.assertIn('result=created', joined)
        self.assertIn('reason=bad_signature', joined)
        self.assertNotIn('5491112345678', joined)
        self.assertNotIn('5491100000000', joined)

    def test_internal_error_does_not_log_exception_message(self):
        with mock.patch.object(receiver_module, 'resolve_channel', side_effect=RuntimeError(PII_SENTINEL)):
            with self.assertLogs(level='DEBUG') as logs:
                response = self.put(self.payload())
        self.assertError(response, 500, 'internal_error')
        self.assertNoSentinel(logs)
        self.assertNotIn(PII_SENTINEL, response.content.decode())


# ── Throttle ────────────────────────────────────────────────────────────────

class ThrottleTests(ReceiverTestBase):

    def test_rate_limited_per_instance(self):
        from rest_framework.settings import api_settings

        rates = {**api_settings.DEFAULT_THROTTLE_RATES, 'agent_leads_sync': '2/minute'}
        with mock.patch.object(api_settings, 'DEFAULT_THROTTLE_RATES', rates):
            v1 = self.payload()
            self.put(v1)
            self.put(v1)
            response = self.put(v1)
        body = self.assertError(response, 429, 'rate_limited')
        self.assertTrue(body['error']['retryable'])
        self.assertIn('Retry-After', response)
