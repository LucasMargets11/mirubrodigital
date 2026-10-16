"""MIRUBRO HUMAN MESSAGES: mensajes de recepción hacia el paciente por WhatsApp.

Mismo estilo que `test_takeover.py`: API humana (RBAC, tenant, validación),
outbox `LeadStaffMessage` (claim, fencing, reintentos, backoff), cliente HMAC
(firma, clasificación de respuestas) — todo contra un transporte fake/mock,
nunca un agente real ni un envío real de WhatsApp.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.appointments.tests.test_customer_core_access import _login
from apps.leads import human_message_client as client
from apps.leads.models import Lead, LeadAgentMessage, LeadStaffMessage
from apps.leads.services import human_messages as svc
from apps.leads.services.takeover import TakeoverUnavailable

from .test_crm_api import LeadApiMixin
from .test_takeover import TAKEOVER_SETTINGS, conv_id, later

Status = LeadStaffMessage.Status


def ok(result='queued', *, message_id=None):
    return client.AgentMessageResponse(
        kind=client.KIND_OK, http_status=201 if result == 'queued' else 200,
        result=result, message_id=message_id or f'agent-msg-{uuid.uuid4().hex[:12]}',
    )


def terminal(code, http_status):
    return client.AgentMessageResponse(kind=client.KIND_TERMINAL, http_status=http_status, error_code=code)


def retryable(code='http_503', http_status=503):
    return client.AgentMessageResponse(kind=client.KIND_RETRYABLE, http_status=http_status, error_code=code)


class FakeSend:
    """Transporte fake: registra cada payload enviado y devuelve respuestas en orden."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.payloads: list[client.MessagePayload] = []

    def __call__(self, payload):
        self.payloads.append(payload)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return response(payload) if callable(response) else response


class HumanMessagesMixin(LeadApiMixin):

    def _setup(self):
        self.biz, self.channel = self._setup_tenant('hmsg')
        self.conv = conv_id()
        self.lead = self._lead(self.biz, self.channel, external_conversation_id=self.conv)
        self.user = self._member(self.biz, 'manager')

    def _send(self, text='Hola, te escribo desde recepción.', lead=None, user=None):
        return svc.send_staff_message(lead or self.lead, text, user=user or self.user)

    def _message(self):
        return LeadStaffMessage.objects.get(lead=self.lead)

    def _url(self, lead=None):
        return f'/api/v1/leads/{(lead or self.lead).pk}/messages/'


# ── API humana: RBAC, tenant, validación, respuesta inmediata ──────────────

@override_settings(**TAKEOVER_SETTINGS)
class HumanMessagesApiTests(HumanMessagesMixin, APITestCase):

    def setUp(self):
        self._setup()

    def test_owner_admin_manager_can_send(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                biz, channel = self._setup_tenant(f'hmsg-{role}')
                lead = self._lead(biz, channel, external_conversation_id=conv_id())
                api = APIClient()
                user = _login(api, biz, role)
                response = api.post(self._url(lead), {'text': f'Hola, {role}'}, format='json')
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
                self.assertEqual(response.data['ok'], True)
                self.assertEqual(response.data['status'], 'queued_locally')
                message = LeadStaffMessage.objects.get(lead=lead)
                self.assertEqual(response.data['id'], str(message.pk))
                self.assertEqual(message.created_by, user)
                self.assertEqual(message.status, Status.PENDING)

    def test_viewer_blocked(self):
        _login(self.client, self.biz, 'viewer')
        response = self.client.post(self._url(), {'text': 'hola'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(LeadStaffMessage.objects.exists())

    def test_unauthenticated_blocked(self):
        response = self.client.post(self._url(), {'text': 'hola'}, format='json')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertFalse(LeadStaffMessage.objects.exists())

    def test_other_business_lead_is_404(self):
        other_biz, other_channel = self._setup_tenant('hmsg-other')
        foreign = self._lead(other_biz, other_channel, external_conversation_id=conv_id())
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(foreign), {'text': 'hola'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(LeadStaffMessage.objects.exists())

    def test_blank_text_rejected(self):
        _login(self.client, self.biz, 'owner')
        for text in ('', '   ', '\t\n'):
            with self.subTest(text=repr(text)):
                response = self.client.post(self._url(), {'text': text}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(LeadStaffMessage.objects.exists())

    def test_text_over_limit_rejected(self):
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(), {'text': 'a' * 4097}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(LeadStaffMessage.objects.exists())

    def test_text_at_limit_accepted_and_sent_as_is(self):
        _login(self.client, self.biz, 'owner')
        text = '  hola, dejo espacios  \n'
        response = self.client.post(self._url(), {'text': text}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(LeadStaffMessage.objects.get().text, text)  # sin trim: tal cual

    def test_lead_without_agent_state_rejected(self):
        bare = Lead.objects.create(business=self.biz)
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(bare), {'text': 'hola'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'conversation_unavailable')
        self.assertFalse(LeadStaffMessage.objects.exists())

    @override_settings(AGENT_TAKEOVER_ENABLED=False)
    def test_flag_off_is_503(self):
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(), {'text': 'hola'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['code'], 'takeover_disabled')
        self.assertFalse(LeadStaffMessage.objects.exists())

    def test_get_still_works_and_response_never_says_sent(self):
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(), {'text': 'hola'}, format='json')
        self.assertNotIn('enviado', str(response.data).lower())
        self.assertNotIn('sent', str(response.data).lower())
        get_response = self.client.get(self._url())
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data['results'], [])  # el outbox local no aparece en el historial


# ── authored_by (join local LeadStaffMessage ↔ LeadAgentMessage) ───────────

@override_settings(**TAKEOVER_SETTINGS)
class AuthoredByTests(HumanMessagesMixin, APITestCase):

    def setUp(self):
        self._setup()

    def _synced(self, *, external_message_id, sender, text='hola', role=None):
        return LeadAgentMessage.objects.create(
            lead=self.lead, external_message_id=external_message_id,
            role=role or (LeadAgentMessage.Role.USER if sender == 'patient' else LeadAgentMessage.Role.ASSISTANT),
            sender=sender, text=text, sent_at=timezone.now(),
        )

    def test_staff_message_synced_gets_authored_by(self):
        message = self._send()
        svc.deliver_staff_message(message.pk, send=FakeSend(ok(message_id='agent-msg-1')))
        self._synced(external_message_id='agent-msg-1', sender='staff', text=message.text)

        _login(self.client, self.biz, 'owner')
        response = self.client.get(self._url())
        rows = response.data['results']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['authored_by'], {'id': self.user.pk, 'display_name': mock.ANY})

    def test_staff_message_without_local_match_falls_back_to_generic_label(self):
        self._synced(external_message_id='orphan-1', sender='staff')
        _login(self.client, self.biz, 'owner')
        rows = self.client.get(self._url()).data['results']
        self.assertEqual(rows[0]['authored_by'], {'id': None, 'display_name': 'Recepción'})

    def test_patient_and_bot_messages_have_no_authored_by(self):
        self._synced(external_message_id='p-1', sender='patient')
        self._synced(external_message_id='b-1', sender='bot')
        _login(self.client, self.biz, 'owner')
        rows = self.client.get(self._url()).data['results']
        self.assertEqual({row['authored_by'] for row in rows}, {None})

    def test_pending_or_failed_outbox_never_matches(self):
        message = self._send()  # sigue pending: sin message_id todavía
        self._synced(external_message_id='unrelated', sender='staff')
        _login(self.client, self.biz, 'owner')
        rows = self.client.get(self._url()).data['results']
        self.assertEqual(rows[0]['authored_by'], {'id': None, 'display_name': 'Recepción'})
        self.assertEqual(message.status, Status.PENDING)


# ── Outbox: encolado, entrega, respuestas del agente, reintentos ───────────

@override_settings(**TAKEOVER_SETTINGS)
class HumanMessagesStateTests(HumanMessagesMixin, TestCase):

    def setUp(self):
        self._setup()

    def test_send_creates_pending_row_with_stable_identity(self):
        message = self._send('Hola!')
        self.assertEqual(message.status, Status.PENDING)
        self.assertEqual(message.text, 'Hola!')
        self.assertEqual(message.created_by, self.user)
        self.assertIsNotNone(message.client_message_id)
        self.assertIsNotNone(message.event_id)
        self.assertEqual(message.attempts, 0)

    def test_disabled_flag_raises(self):
        with override_settings(AGENT_TAKEOVER_ENABLED=False):
            with self.assertRaises(TakeoverUnavailable) as ctx:
                self._send()
            self.assertEqual(ctx.exception.code, 'takeover_disabled')

    def test_lead_without_conversation_raises(self):
        bare = Lead.objects.create(business=self.biz)
        with self.assertRaises(TakeoverUnavailable) as ctx:
            self._send(lead=bare)
        self.assertEqual(ctx.exception.code, 'conversation_unavailable')

    def test_kick_is_scheduled_after_commit_not_before(self):
        with mock.patch('apps.leads.tasks.deliver_staff_message.delay') as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self._send()
                delay.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
        delay.assert_called_once_with(str(LeadStaffMessage.objects.get().pk))

    def test_broker_failure_on_kick_does_not_break_request(self):
        with mock.patch('apps.leads.tasks.deliver_staff_message.delay', side_effect=RuntimeError('broker down')):
            with self.captureOnCommitCallbacks(execute=True):
                self._send()
        self.assertEqual(LeadStaffMessage.objects.get().status, Status.PENDING)

    def test_happy_path_queued(self):
        message = self._send()
        send = FakeSend(ok('queued', message_id='agent-msg-abc'))
        outcome = svc.deliver_staff_message(message.pk, send=send)
        self.assertEqual(outcome, Status.DELIVERED)
        message.refresh_from_db()
        self.assertEqual((message.status, message.result, message.message_id),
                         (Status.DELIVERED, 'queued', 'agent-msg-abc'))
        self.assertIsNotNone(message.delivered_at)
        payload = send.payloads[0]
        self.assertEqual(payload.external_conversation_id, self.conv)
        self.assertEqual(payload.business_id, self.biz.pk)
        self.assertEqual(payload.text, message.text)
        self.assertEqual(payload.event_id, message.event_id)
        self.assertEqual(payload.client_message_id, message.client_message_id)

    def test_duplicate_result_counts_as_delivered(self):
        message = self._send()
        send = FakeSend(ok('duplicate', message_id='agent-msg-xyz'))
        self.assertEqual(svc.deliver_staff_message(message.pk, send=send), Status.DELIVERED)
        message.refresh_from_db()
        self.assertEqual((message.status, message.result), (Status.DELIVERED, 'duplicate'))

    def test_terminal_errors_fail_without_retry(self):
        cases = [
            ('invalid_payload', 400), ('invalid_signature', 401), ('human_messages_disabled', 403),
            ('takeover_disabled', 403), ('tls_required', 403), ('conversation_not_found', 404),
            ('conversation_not_taken', 409), ('business_mismatch', 409), ('message_conflict', 409),
            ('outside_service_window', 409),
        ]
        for code, http_status in cases:
            with self.subTest(code=code):
                message = self._send(lead=self._lead(self.biz, self.channel, external_conversation_id=conv_id()))
                send = FakeSend(terminal(code, http_status))
                self.assertEqual(svc.deliver_staff_message(message.pk, send=send), Status.FAILED)
                message.refresh_from_db()
                self.assertEqual(
                    (message.status, message.last_error, message.last_status, message.next_attempt_at),
                    (Status.FAILED, code, http_status, None),
                )
                self.assertIsNotNone(message.failed_at)
                self.assertIsNone(message.message_id)
                # Nunca se reintenta (ni por Beat).
                svc.retry_due_staff_messages(now=later(), send=send)
                self.assertEqual(len(send.payloads), 1)

    def test_unknown_4xx_maps_to_http_status_code(self):
        message = self._send()
        send = FakeSend(terminal('http_422', 422))
        self.assertEqual(svc.deliver_staff_message(message.pk, send=send), Status.FAILED)
        self.assertEqual(LeadStaffMessage.objects.get().last_error, 'http_422')

    def test_retryable_keeps_pending_with_backoff_and_same_body(self):
        send = FakeSend(retryable(), client.AgentMessageResponse(kind=client.KIND_RETRYABLE, error_code='timeout'),
                        ok('queued', message_id='agent-msg-1'))
        message = self._send()
        t0 = timezone.now()
        self.assertEqual(svc.deliver_staff_message(message.pk, send=send), 'retry')
        message.refresh_from_db()
        self.assertEqual((message.status, message.attempts, message.last_error, message.last_status),
                         (Status.PENDING, 1, 'http_503', 503))
        self.assertAlmostEqual((message.next_attempt_at - t0).total_seconds(), 30, delta=5)

        # No vencido → no sale.
        self.assertIsNone(svc.deliver_staff_message(message.pk, send=send))
        self.assertEqual(len(send.payloads), 1)

        self.assertEqual(svc.deliver_staff_message(message.pk, send=send, now=later(31)), 'retry')
        message.refresh_from_db()
        self.assertEqual((message.attempts, message.last_error, message.last_status), (2, 'timeout', None))

        self.assertEqual(svc.deliver_staff_message(message.pk, send=send, now=later(95)), Status.DELIVERED)
        message.refresh_from_db()
        self.assertEqual((message.status, message.result, message.message_id),
                         (Status.DELIVERED, 'queued', 'agent-msg-1'))
        # Mismo mensaje en los 3 intentos: event_id, client_message_id y body idénticos.
        self.assertEqual(len({(p.event_id, p.client_message_id, p.occurred_at) for p in send.payloads}), 1)
        self.assertEqual(len({client.build_body(p) for p in send.payloads}), 1)

    def test_backoff_schedule_matches_takeover(self):
        self.assertEqual([svc._backoff_seconds(n) for n in range(1, 9)], [30, 60, 120, 240, 480, 900, 900, 900])

    @override_settings(AGENT_TAKEOVER_MAX_ATTEMPTS=2)
    def test_exhausted_retries_fail(self):
        send = FakeSend(retryable())
        message = self._send()
        svc.deliver_staff_message(message.pk, send=send)
        self.assertEqual(svc.deliver_staff_message(message.pk, send=send, now=later()), Status.FAILED)
        message.refresh_from_db()
        self.assertEqual((message.status, message.attempts, message.next_attempt_at), (Status.FAILED, 2, None))

    def test_client_not_configured_is_retryable(self):
        message = self._send()
        with override_settings(AGENT_TAKEOVER_SECRET=''):
            self.assertEqual(svc.deliver_staff_message(message.pk, send=None), 'retry')
        message.refresh_from_db()
        self.assertEqual((message.status, message.last_error), (Status.PENDING, 'client_not_configured'))

    def test_send_crash_never_leaves_delivering(self):
        def boom(payload):
            raise ValueError('bug')

        message = self._send()
        self.assertEqual(svc.deliver_staff_message(message.pk, send=boom), 'retry')
        self.assertEqual(LeadStaffMessage.objects.get().status, Status.PENDING)

    # ── Recuperación, fencing, concurrencia ─────────────────────────────────

    def test_pending_survives_restart_and_beat_delivers(self):
        self._send()  # el kick se "pierde" (on_commit no corre en TestCase)
        send = FakeSend(ok('queued', message_id='agent-msg-1'))
        counts = svc.retry_due_staff_messages(send=send)
        self.assertEqual((counts['due'], counts['delivered']), (1, 1))
        self.assertEqual(svc.retry_due_staff_messages(send=send)['due'], 0)

    def test_stuck_delivering_is_resent_with_same_identity_after_lease(self):
        message = self._send()
        claim = svc._claim(message.pk, timezone.now())  # worker murió tras el claim
        self.assertIsNotNone(claim)
        send = FakeSend(ok('queued', message_id='agent-msg-1'))
        self.assertEqual(svc.retry_due_staff_messages(send=send)['due'], 0)  # lease vigente
        counts = svc.retry_due_staff_messages(now=later(61), send=send)
        self.assertEqual(counts['delivered'], 1)
        message.refresh_from_db()
        self.assertEqual((message.attempts, message.status), (2, Status.DELIVERED))

    def test_double_claim_is_fenced(self):
        message = self._send()
        now = timezone.now()
        first = svc._claim(message.pk, now)
        second = svc._claim(message.pk, now)
        self.assertIsNotNone(first)
        self.assertIsNone(second)  # ya está delivering y el lease no venció

    def test_late_ack_after_lease_expired_is_ignored(self):
        message = self._send()
        svc._claim(message.pk, timezone.now())
        # Lease vencido: otro intento reclama y entrega.
        svc.retry_due_staff_messages(now=later(61), send=FakeSend(ok('queued', message_id='agent-msg-new')))
        message.refresh_from_db()
        self.assertEqual(message.status, Status.DELIVERED)
        # El intento original (fenced por attempts) ya no puede escribir nada.
        stale_result = svc._record_response(message.pk, attempts=1, response=terminal('conversation_not_found', 404))
        self.assertIsNone(stale_result)
        message.refresh_from_db()
        self.assertEqual(message.status, Status.DELIVERED)  # intacto

    def test_disabled_flag_sweep_is_noop(self):
        self._send()
        with override_settings(AGENT_TAKEOVER_ENABLED=False):
            counts = svc.retry_due_staff_messages(send=FakeSend(ok()))
        self.assertEqual(counts['due'], 0)
        self.assertEqual(LeadStaffMessage.objects.get().status, Status.PENDING)


# ── Cliente HMAC: firma, body determinístico, clasificación ────────────────

class HumanMessageClientTests(TestCase):

    def _payload(self, **overrides):
        data = dict(
            external_conversation_id=conv_id(), event_id=uuid.uuid4(), client_message_id=uuid.uuid4(),
            business_id=3, occurred_at=timezone.now(), text='Hola, ¿cómo estás?',
        )
        data.update(overrides)
        return client.MessagePayload(**data)

    def test_build_body_has_exactly_five_keys_in_fixed_order(self):
        import json

        payload = self._payload()
        body = json.loads(client.build_body(payload))
        self.assertEqual(list(body.keys()), ['event_id', 'business_id', 'client_message_id', 'occurred_at', 'text'])
        self.assertEqual(body['text'], payload.text)

    def test_build_body_is_deterministic(self):
        payload = self._payload()
        self.assertEqual(client.build_body(payload), client.build_body(payload))

    def test_build_request_signs_post_with_message_path(self):
        payload = self._payload(external_conversation_id='wac1_' + 'a' * 32)
        url, body, headers = client.build_request(
            payload, base_url='https://agent.example.test', key_id='k1', secret='s' * 32,
            timestamp=1700000000, request_id='req-1',
        )
        self.assertEqual(url, f'https://agent.example.test/integrations/mirubro/conversations/{payload.external_conversation_id}/messages')
        self.assertEqual(headers['X-Mirubro-Key-Id'], 'k1')
        self.assertTrue(headers['X-Mirubro-Signature'].startswith('v1='))
        self.assertEqual(body, client.build_body(payload))

    def test_classify_response_queued_201(self):
        body = b'{"ok":true,"result":"queued","client_message_id":"x","message_id":"agent-1"}'
        response = client.classify_response(201, body)
        self.assertEqual((response.kind, response.result, response.message_id), (client.KIND_OK, 'queued', 'agent-1'))

    def test_classify_response_duplicate_200(self):
        body = b'{"ok":true,"result":"duplicate","client_message_id":"x","message_id":"agent-1"}'
        response = client.classify_response(200, body)
        self.assertEqual((response.kind, response.result), (client.KIND_OK, 'duplicate'))

    def test_classify_response_documented_error_code_preserved(self):
        body = b'{"ok":false,"error":{"code":"outside_service_window","message":"too late"}}'
        response = client.classify_response(409, body)
        self.assertEqual((response.kind, response.error_code), (client.KIND_TERMINAL, 'outside_service_window'))

    def test_classify_response_unknown_error_code_maps_to_http_status(self):
        body = b'{"ok":false,"error":{"code":"something_new","message":"?"}}'
        response = client.classify_response(409, body)
        self.assertEqual(response.error_code, 'http_409')

    def test_classify_response_5xx_is_retryable(self):
        self.assertEqual(client.classify_response(503, b'').kind, client.KIND_RETRYABLE)

    def test_classify_response_unreadable_2xx_is_retryable(self):
        self.assertEqual(client.classify_response(201, b'not json').kind, client.KIND_RETRYABLE)

    def test_classify_response_redirect_is_terminal(self):
        response = client.classify_response(302, b'')
        self.assertEqual((response.kind, response.error_code), (client.KIND_TERMINAL, 'unexpected_redirect'))
