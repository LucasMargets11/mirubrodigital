"""MIRUBRO TAKEOVER 05A: control humano de la conversación (takeover / release → Agent).

Cubre la API humana (RBAC, tenant, disponibilidad), la máquina de estados y el
versionado de `ConversationControl`, el outbox `TakeoverCommand` (reintentos,
fencing, ACK tardío), el cliente HMAC y el mapeo de respuestas del agente.
La concurrencia real en PostgreSQL está en `TakeoverConcurrencyTests`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import threading
import uuid
from unittest import mock

import requests
from django.conf import settings
from django.core import checks
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.appointments.tests.test_customer_core_access import _login
from apps.leads import takeover_client as client
from apps.leads.checks import check_agent_takeover_config
from apps.leads.models import ConversationControl, Lead, LeadActivity, TakeoverCommand
from apps.leads.services import takeover as svc

from .factories import make_state
from .test_crm_api import LeadApiMixin

State = ConversationControl.State
CmdStatus = TakeoverCommand.Status

TAKEOVER_SECRET = 'takeover-secret-0123456789abcdef-0123456789'
TAKEOVER_SETTINGS = dict(
    AGENT_TAKEOVER_ENABLED=True,
    AGENT_TAKEOVER_BASE_URL='https://agent.example.test',
    AGENT_TAKEOVER_KEY_ID='mirubro-inbound-1',
    AGENT_TAKEOVER_SECRET=TAKEOVER_SECRET,
)


def conv_id() -> str:
    return 'wac1_' + uuid.uuid4().hex


def ok(result='applied', *, applied_version, state):
    return client.AgentCommandResponse(
        kind=client.KIND_OK, http_status=200, result=result, applied_version=applied_version, agent_state=state,
    )


def terminal(code, http_status):
    return client.AgentCommandResponse(kind=client.KIND_TERMINAL, http_status=http_status, error_code=code)


def retryable(code='http_503', http_status=503):
    return client.AgentCommandResponse(kind=client.KIND_RETRYABLE, http_status=http_status, error_code=code)


class FakeSend:
    """Transporte fake: registra cada payload enviado y devuelve respuestas en orden.

    Una respuesta puede ser callable(payload) para responder según el comando.
    """

    def __init__(self, *responses):
        self.responses = list(responses)
        self.payloads: list[client.CommandPayload] = []

    def __call__(self, payload):
        self.payloads.append(payload)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return response(payload) if callable(response) else response


def agent_ack(payload):
    """Respuesta del agente para un comando aplicado."""
    return ok(applied_version=payload.version, state='paused' if payload.action == 'takeover' else 'active')


def later(seconds=3600):
    return timezone.now() + dt.timedelta(seconds=seconds)


class TakeoverMixin(LeadApiMixin):

    def _setup(self):
        self.biz, self.channel = self._setup_tenant('tko')
        self.conv = conv_id()
        self.lead = self._lead(self.biz, self.channel, external_conversation_id=self.conv)
        self.user = self._member(self.biz, 'manager')

    def _request(self, action, lead=None, user=None):
        return svc.request_conversation_command(lead or self.lead, action, user=user or self.user)

    def _control(self, conv=None):
        return ConversationControl.objects.get(business=self.biz, external_conversation_id=conv or self.conv)

    def _deliver_current(self, send, now=None):
        command = TakeoverCommand.objects.filter(conversation_control=self._control()).order_by('-version').first()
        return svc.deliver_takeover_command(command.pk, send=send, now=now)

    def _taken(self):
        self._request('takeover')
        self._deliver_current(FakeSend(agent_ack))
        self.assertEqual(self._control().state, State.TAKEN)


# ── API humana: RBAC, tenant, disponibilidad ────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class TakeoverApiTests(TakeoverMixin, APITestCase):

    def setUp(self):
        self._setup()

    def _url(self, lead, action='takeover'):
        return f'/api/v1/leads/{lead.pk}/{action}/'

    def test_owner_admin_manager_can_takeover_and_release(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                # Business propio por rol: el plan tiene límite de 2 usuarios.
                biz, channel = self._setup_tenant(f'tko-{role}')
                conv = conv_id()
                lead = self._lead(biz, channel, external_conversation_id=conv)
                api = APIClient()
                user = _login(api, biz, role)
                response = api.post(self._url(lead), {}, format='json')
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
                self.assertEqual(response.data, {'ok': True, 'state': 'takeover_pending', 'command_version': 1})
                control = ConversationControl.objects.get(business=biz, external_conversation_id=conv)
                self.assertEqual(control.state, State.TAKEOVER_PENDING)
                self._deliver_current_for(control, FakeSend(agent_ack))
                release = api.post(self._url(lead, 'release'), {}, format='json')
                self.assertEqual(release.status_code, status.HTTP_202_ACCEPTED, release.data)
                self.assertEqual(release.data, {'ok': True, 'state': 'release_pending', 'command_version': 2})
                command = TakeoverCommand.objects.get(conversation_control=control, version=1)
                self.assertEqual(command.requested_by, user)

    def _deliver_current_for(self, control, send):
        command = control.commands.order_by('-version').first()
        svc.deliver_takeover_command(command.pk, send=send)

    def test_viewer_blocked(self):
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.client.post(self._url(self.lead)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self._url(self.lead, 'release')).status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ConversationControl.objects.exists())

    def test_unauthenticated_blocked(self):
        response = self.client.post(self._url(self.lead))
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertFalse(TakeoverCommand.objects.exists())

    def test_view_only_can_read_state_but_not_command(self):
        from apps.accounts import permissions as perm_module

        real = perm_module.permissions_for_service

        def view_only(service, role, business=None):
            perms = dict(real(service, role, business))
            perms['manage_leads'] = False
            return perms

        _login(self.client, self.biz, 'manager')
        with mock.patch.object(perm_module, 'permissions_for_service', side_effect=view_only):
            self.assertEqual(self.client.post(self._url(self.lead)).status_code, status.HTTP_403_FORBIDDEN)
            detail = self.client.get(f'/api/v1/leads/{self.lead.pk}/')
            self.assertEqual(detail.status_code, status.HTTP_200_OK)
            self.assertEqual(detail.data['conversation_control']['state'], 'active')
        self.assertFalse(TakeoverCommand.objects.exists())

    def test_other_business_lead_is_404(self):
        other_biz, other_channel = self._setup_tenant('tko-other')
        foreign = self._lead(other_biz, other_channel, external_conversation_id=conv_id())
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.post(self._url(foreign)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self._url(foreign, 'release')).status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ConversationControl.objects.exists())

    def test_same_conversation_id_in_other_business_is_independent(self):
        other_biz, other_channel = self._setup_tenant('tko-twin')
        self._lead(other_biz, other_channel, external_conversation_id=self.conv)
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.post(self._url(self.lead)).status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(ConversationControl.objects.filter(business=other_biz).count(), 0)
        self.assertEqual(self._control().business, self.biz)

    def test_lead_without_agent_state_rejected(self):
        bare = Lead.objects.create(business=self.biz)
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(bare))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'conversation_unavailable')
        detail = self.client.get(f'/api/v1/leads/{bare.pk}/')
        self.assertIsNone(detail.data['conversation_control'])
        self.assertFalse(ConversationControl.objects.exists())

    def test_conversation_id_not_in_agent_format_rejected(self):
        lead = self._lead(self.biz, self.channel, external_conversation_id='conv-legacy-123')
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(lead))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'conversation_unavailable')
        detail = self.client.get(f'/api/v1/leads/{lead.pk}/')
        self.assertFalse(detail.data['conversation_control']['available'])

    @override_settings(AGENT_TAKEOVER_ENABLED=False)
    def test_flag_off_is_503_without_command(self):
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(self.lead))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['code'], 'takeover_disabled')
        self.assertFalse(ConversationControl.objects.exists())
        detail = self.client.get(f'/api/v1/leads/{self.lead.pk}/')
        self.assertFalse(detail.data['conversation_control']['available'])

    def test_entitlement_required(self):
        from apps.business import entitlements as ent_module

        _login(self.client, self.biz, 'owner')
        with mock.patch.dict(ent_module.PLAN_ENTITLEMENTS, {'appointments_base': {'appointments.customers'}}):
            response = self.client.post(self._url(self.lead))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(TakeoverCommand.objects.exists())

    def test_get_not_allowed_and_body_ignored(self):
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.get(self._url(self.lead)).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.post(self._url(self.lead), {'version': 99, 'state': 'taken'}, format='json')
        self.assertEqual(response.data['command_version'], 1)

    def test_repeated_takeover_is_200_without_new_command(self):
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.post(self._url(self.lead)).status_code, status.HTTP_202_ACCEPTED)
        again = self.client.post(self._url(self.lead))
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(again.data, {'ok': True, 'state': 'takeover_pending', 'command_version': 1})
        self.assertEqual(TakeoverCommand.objects.count(), 1)

    def test_release_while_takeover_pending_is_409(self):
        _login(self.client, self.biz, 'owner')
        self.client.post(self._url(self.lead))
        response = self.client.post(self._url(self.lead, 'release'))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'command_in_progress')
        self.assertEqual(TakeoverCommand.objects.count(), 1)
        self.assertEqual(self._control().state, State.TAKEOVER_PENDING)

    def test_release_on_never_taken_conversation_is_idempotent(self):
        _login(self.client, self.biz, 'owner')
        response = self.client.post(self._url(self.lead, 'release'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'ok': True, 'state': 'active', 'command_version': 0})
        self.assertFalse(ConversationControl.objects.exists())

    def test_detail_and_list_expose_state_without_internals(self):
        user = _login(self.client, self.biz, 'owner')
        self.client.post(self._url(self.lead))
        detail = self.client.get(f'/api/v1/leads/{self.lead.pk}/').data['conversation_control']
        self.assertEqual(set(detail), {
            'state', 'command_version', 'last_action', 'taken_at', 'taken_by', 'released_at', 'last_error_code',
            'available',
        })
        self.assertEqual(detail['state'], 'takeover_pending')
        self.assertIsNone(detail['taken_by'])  # taken_by solo con el ACK
        self._deliver_current(FakeSend(agent_ack))
        detail = self.client.get(f'/api/v1/leads/{self.lead.pk}/').data['conversation_control']
        self.assertEqual(detail['state'], 'taken')
        self.assertEqual(detail['taken_by']['id'], user.pk)
        self.assertEqual(detail['last_action'], 'takeover')
        self.assertTrue(detail['available'])
        rendered = json.dumps(detail, default=str)
        command = TakeoverCommand.objects.get()
        self.assertNotIn(str(command.event_id), rendered)
        self.assertNotIn(TAKEOVER_SECRET, rendered)

        bare = Lead.objects.create(business=self.biz)
        plain = self._lead(self.biz, self.channel, external_conversation_id=conv_id())
        rows = {row['id']: row for row in self.client.get('/api/v1/leads/').data['results']}
        self.assertEqual(rows[str(self.lead.pk)]['conversation_state'], 'taken')
        self.assertEqual(rows[str(plain.pk)]['conversation_state'], 'active')
        self.assertIsNone(rows[str(bare.pk)]['conversation_state'])

    def test_new_lead_on_same_conversation_shows_taken(self):
        _login(self.client, self.biz, 'owner')
        self.client.post(self._url(self.lead))
        self._deliver_current(FakeSend(agent_ack))
        newer = self._lead(self.biz, self.channel, external_conversation_id=self.conv)
        detail = self.client.get(f'/api/v1/leads/{newer.pk}/').data['conversation_control']
        self.assertEqual(detail['state'], 'taken')
        again = self.client.post(self._url(newer))
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(ConversationControl.objects.count(), 1)
        self.assertEqual(TakeoverCommand.objects.count(), 1)


# ── Máquina de estados, versionado, outbox ──────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class TakeoverStateTests(TakeoverMixin, TestCase):

    def setUp(self):
        self._setup()

    def test_takeover_creates_pending_command_v1(self):
        result = self._request('takeover')
        self.assertEqual((result.state, result.command_version, result.created), ('takeover_pending', 1, True))
        control = self._control()
        command = TakeoverCommand.objects.get()
        self.assertEqual((control.state, control.command_version, control.last_command_action),
                         (State.TAKEOVER_PENDING, 1, 'takeover'))
        self.assertEqual(control.last_event_id, command.event_id)
        self.assertEqual((command.version, command.action, command.status, command.attempts),
                         (1, 'takeover', CmdStatus.PENDING, 0))
        self.assertEqual(command.requested_from_lead, self.lead)
        self.assertIsNone(control.taken_by)

    def test_command_is_durable_before_http_and_kicked_after_commit(self):
        with mock.patch('apps.leads.tasks.deliver_takeover_command.delay') as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self._request('takeover')
                # Antes del commit: el comando ya está en la DB y no salió nada.
                self.assertTrue(TakeoverCommand.objects.filter(status=CmdStatus.PENDING).exists())
                delay.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
        delay.assert_called_once_with(str(TakeoverCommand.objects.get().pk))

    def test_broker_failure_on_kick_does_not_break_request(self):
        with mock.patch('apps.leads.tasks.deliver_takeover_command.delay', side_effect=RuntimeError('broker down')):
            with self.captureOnCommitCallbacks(execute=True):
                self._request('takeover')
        self.assertEqual(TakeoverCommand.objects.get().status, CmdStatus.PENDING)

    def test_full_cycle_versions_and_events(self):
        send = FakeSend(agent_ack)
        self._request('takeover')
        self.assertEqual(self._deliver_current(send), CmdStatus.DELIVERED)
        control = self._control()
        self.assertEqual(control.state, State.TAKEN)
        self.assertEqual(control.taken_by, self.user)
        self.assertIsNotNone(control.taken_at)
        self.assertIsNotNone(control.last_success_at)

        self.assertEqual(self._request('release').command_version, 2)
        self.assertEqual(self._control().state, State.RELEASE_PENDING)
        self._deliver_current(send)
        control = self._control()
        self.assertEqual(control.state, State.ACTIVE)
        self.assertIsNone(control.taken_by)
        self.assertIsNone(control.taken_at)
        self.assertIsNotNone(control.released_at)

        self.assertEqual(self._request('takeover').command_version, 3)
        commands = list(TakeoverCommand.objects.order_by('version'))
        self.assertEqual([(c.version, c.action) for c in commands], [(1, 'takeover'), (2, 'release'), (3, 'takeover')])
        self.assertEqual(len({c.event_id for c in commands}), 3)
        self.assertEqual([p.version for p in send.payloads], [1, 2])
        self.assertEqual([p.business_id for p in send.payloads], [self.biz.pk, self.biz.pk])
        self.assertEqual([p.external_conversation_id for p in send.payloads], [self.conv, self.conv])

    def test_repeated_actions_do_not_create_commands(self):
        self._request('takeover')
        self.assertFalse(self._request('takeover').created)
        self._deliver_current(FakeSend(agent_ack))
        self.assertFalse(self._request('takeover').created)
        self._request('release')
        self.assertFalse(self._request('release').created)
        with self.assertRaises(svc.TakeoverConflict):
            self._request('takeover')
        self._deliver_current(FakeSend(agent_ack))
        result = self._request('release')
        self.assertEqual((result.created, result.state, result.command_version), (False, 'active', 2))
        self.assertEqual(TakeoverCommand.objects.count(), 2)

    def test_activity_trail(self):
        self._request('takeover')
        self._deliver_current(FakeSend(agent_ack))
        self._request('release')
        self._deliver_current(FakeSend(terminal('conversation_not_found', 404)))
        kinds = list(LeadActivity.objects.filter(lead=self.lead).order_by('created_at').values_list('kind', 'metadata'))
        self.assertEqual(kinds, [
            ('takeover_requested', {'version': 1}),
            ('takeover_applied', {'version': 1}),
            ('release_requested', {'version': 2}),
            ('release_failed', {'version': 2, 'error_code': 'conversation_not_found'}),
        ])
        requested = LeadActivity.objects.get(kind='takeover_requested')
        self.assertEqual(requested.actor, self.user)
        self.assertIsNone(LeadActivity.objects.get(kind='takeover_applied').actor)

    def test_no_business_notification_for_takeover(self):
        from apps.notifications.models import BusinessNotification

        before = BusinessNotification.objects.count()
        self._request('takeover')
        self._deliver_current(FakeSend(agent_ack))
        self.assertEqual(BusinessNotification.objects.count(), before)

    # ── Respuestas del agente ───────────────────────────────────────────────

    def test_duplicate_counts_as_delivered(self):
        self._request('takeover')
        self._deliver_current(FakeSend(ok('duplicate', applied_version=1, state='paused')))
        command = TakeoverCommand.objects.get()
        self.assertEqual((command.status, command.result), (CmdStatus.DELIVERED, 'duplicate'))
        self.assertEqual(self._control().state, State.TAKEN)

    def test_stale_with_higher_agent_version_is_version_regression(self):
        self._request('takeover')
        self._deliver_current(FakeSend(ok('stale', applied_version=7, state='paused')))
        command = TakeoverCommand.objects.get()
        self.assertEqual((command.status, command.result, command.agent_applied_version),
                         (CmdStatus.DELIVERED, 'stale', 7))
        control = self._control()
        self.assertEqual((control.state, control.last_error_code, control.agent_applied_version),
                         (State.ERROR, 'version_regression', 7))
        self.assertIsNone(control.taken_by)
        # Recuperación: la versión nueva queda por encima de la del agente (nunca se baja).
        result = self._request('release')
        self.assertEqual(result.command_version, 8)

    def test_applied_with_unexpected_state_is_error(self):
        self._request('takeover')
        self._deliver_current(FakeSend(ok('applied', applied_version=1, state='active')))
        control = self._control()
        self.assertEqual((control.state, control.last_error_code), (State.ERROR, 'unexpected_agent_state'))

    def test_terminal_errors_fail_without_retry(self):
        cases = [
            ('invalid_signature', 401), ('takeover_disabled', 403), ('tls_required', 403),
            ('conversation_not_found', 404), ('version_conflict', 409), ('business_mismatch', 409),
            ('invalid_payload', 400),
        ]
        for code, http_status in cases:
            with self.subTest(code=code):
                conv = conv_id()
                lead = self._lead(self.biz, self.channel, external_conversation_id=conv)
                self._request('takeover', lead=lead)
                control = self._control(conv)
                command = control.commands.get()
                send = FakeSend(terminal(code, http_status))
                self.assertEqual(svc.deliver_takeover_command(command.pk, send=send), CmdStatus.FAILED)
                command.refresh_from_db()
                control.refresh_from_db()
                self.assertEqual((command.status, command.last_error, command.last_status, command.next_attempt_at),
                                 (CmdStatus.FAILED, code, http_status, None))
                self.assertEqual((control.state, control.last_error_code), (State.ERROR, code))
                # Nunca se reintenta (ni por Beat).
                svc.retry_due_takeover_commands(now=later(), send=send)
                self.assertEqual(len(send.payloads), 1)

    def test_error_state_allows_new_command_with_next_version(self):
        self._request('takeover')
        self._deliver_current(FakeSend(terminal('conversation_not_found', 404)))
        result = self._request('takeover')
        self.assertEqual((result.created, result.command_version), (True, 2))
        self._deliver_current(FakeSend(agent_ack))
        self.assertEqual(self._control().state, State.TAKEN)

    def test_retryable_keeps_pending_with_backoff_and_same_body(self):
        send = FakeSend(retryable(), client.AgentCommandResponse(kind=client.KIND_RETRYABLE, error_code='timeout'),
                        agent_ack)
        self._request('takeover')
        command = TakeoverCommand.objects.get()
        t0 = timezone.now()
        self.assertEqual(self._deliver_current(send), 'retry')
        command.refresh_from_db()
        self.assertEqual((command.status, command.attempts, command.last_error, command.last_status),
                         (CmdStatus.PENDING, 1, 'http_503', 503))
        self.assertAlmostEqual((command.next_attempt_at - t0).total_seconds(), 30, delta=5)
        control = self._control()
        self.assertEqual((control.state, control.last_error_code), (State.TAKEOVER_PENDING, 'http_503'))

        # No vencido → no sale.
        self.assertIsNone(svc.deliver_takeover_command(command.pk, send=send))
        self.assertEqual(len(send.payloads), 1)

        self.assertEqual(svc.deliver_takeover_command(command.pk, send=send, now=later(31)), 'retry')
        command.refresh_from_db()
        self.assertEqual((command.attempts, command.last_error, command.last_status), (2, 'timeout', None))
        self.assertAlmostEqual((command.next_attempt_at - timezone.now()).total_seconds(), 60, delta=5)

        self.assertEqual(svc.deliver_takeover_command(command.pk, send=send, now=later(61)), CmdStatus.DELIVERED)
        self.assertEqual(self._control().state, State.TAKEN)
        self.assertEqual(self._control().last_error_code, None)
        # Mismo comando en los 3 intentos: version, event_id, occurred_at y body idénticos.
        self.assertEqual(len({(p.version, p.event_id, p.occurred_at) for p in send.payloads}), 1)
        self.assertEqual(len({client.build_body(p) for p in send.payloads}), 1)
        self.assertEqual(send.payloads[0].event_id, command.event_id)

    def test_backoff_schedule(self):
        self.assertEqual([svc._backoff_seconds(n) for n in range(1, 9)], [30, 60, 120, 240, 480, 900, 900, 900])

    @override_settings(AGENT_TAKEOVER_MAX_ATTEMPTS=2)
    def test_exhausted_retries_fail_command_and_control(self):
        send = FakeSend(retryable())
        self._request('takeover')
        command = TakeoverCommand.objects.get()
        self._deliver_current(send)
        self.assertEqual(svc.deliver_takeover_command(command.pk, send=send, now=later()), CmdStatus.FAILED)
        command.refresh_from_db()
        self.assertEqual((command.status, command.attempts, command.next_attempt_at), (CmdStatus.FAILED, 2, None))
        control = self._control()
        self.assertEqual((control.state, control.last_error_code), (State.ERROR, 'delivery_exhausted'))

    def test_client_not_configured_is_retryable(self):
        self._request('takeover')
        with override_settings(AGENT_TAKEOVER_SECRET=''):
            self.assertEqual(self._deliver_current(None), 'retry')
        command = TakeoverCommand.objects.get()
        self.assertEqual((command.status, command.last_error), (CmdStatus.PENDING, 'client_not_configured'))

    def test_send_crash_never_leaves_delivering(self):
        def boom(payload):
            raise ValueError('bug')

        self._request('takeover')
        self.assertEqual(self._deliver_current(boom), 'retry')
        self.assertEqual(TakeoverCommand.objects.get().status, CmdStatus.PENDING)

    # ── Recuperación, fencing, ACK tardío ───────────────────────────────────

    def test_pending_survives_restart_and_beat_delivers(self):
        self._request('takeover')  # el kick se "pierde" (on_commit no corre en TestCase)
        send = FakeSend(agent_ack)
        counts = svc.retry_due_takeover_commands(send=send)
        self.assertEqual((counts['due'], counts['delivered']), (1, 1))
        self.assertEqual(self._control().state, State.TAKEN)
        self.assertEqual(svc.retry_due_takeover_commands(send=send)['due'], 0)

    def test_stuck_delivering_is_resent_with_same_event_after_lease(self):
        self._request('takeover')
        command = TakeoverCommand.objects.get()
        claim = svc._claim(command.pk, timezone.now())  # worker murió tras el claim
        self.assertIsNotNone(claim)
        send = FakeSend(agent_ack)
        self.assertEqual(svc.retry_due_takeover_commands(send=send)['due'], 0)  # lease vigente
        counts = svc.retry_due_takeover_commands(now=later(61), send=send)
        self.assertEqual(counts['delivered'], 1)
        command.refresh_from_db()
        self.assertEqual((command.attempts, command.status), (2, CmdStatus.DELIVERED))
        self.assertEqual(send.payloads[0].event_id, command.event_id)
        # La respuesta del intento muerto, si llega, está fenced.
        self.assertIsNone(svc.record_command_response(claim, agent_ack(claim.payload)))

    def test_concurrent_claim_is_skipped(self):
        self._request('takeover')
        command = TakeoverCommand.objects.get()
        self.assertIsNotNone(svc._claim(command.pk, timezone.now()))
        send = FakeSend(agent_ack)
        self.assertIsNone(svc.deliver_takeover_command(command.pk, send=send))
        self.assertEqual(send.payloads, [])

    def test_late_ack_never_overwrites_newer_command(self):
        # v1 takeover en vuelo (claim hecho, HTTP lento).
        self._request('takeover')
        v1 = TakeoverCommand.objects.get(version=1)
        claim_v1 = svc._claim(v1.pk, timezone.now())
        # Mientras tanto MiRubro queda en error (p. ej. un stale con regresión) y
        # el humano pide release → v2 vigente.
        ConversationControl.objects.filter(pk=self._control().pk).update(state=State.ERROR, last_error_code='x')
        result = self._request('release')
        self.assertEqual((result.created, result.command_version), (True, 2))
        # Llega el ACK tardío de v1 (aplicado, pausado).
        outcome = svc.record_command_response(claim_v1, ok(applied_version=1, state='paused'))
        self.assertEqual(outcome, CmdStatus.DELIVERED)
        v1.refresh_from_db()
        self.assertEqual((v1.status, v1.result), (CmdStatus.DELIVERED, 'applied'))
        control = self._control()
        self.assertEqual((control.state, control.command_version), (State.RELEASE_PENDING, 2))
        self.assertIsNone(control.taken_by)
        self.assertFalse(LeadActivity.objects.filter(kind='takeover_applied').exists())
        # v2 sigue su curso normal.
        self._deliver_current(FakeSend(agent_ack))
        self.assertEqual(self._control().state, State.ACTIVE)

    def test_late_failure_of_old_command_does_not_touch_state(self):
        self._request('takeover')
        v1 = TakeoverCommand.objects.get(version=1)
        claim_v1 = svc._claim(v1.pk, timezone.now())
        ConversationControl.objects.filter(pk=self._control().pk).update(state=State.ERROR)
        self._request('release')
        svc.record_command_response(claim_v1, terminal('conversation_not_found', 404))
        self.assertEqual(self._control().state, State.RELEASE_PENDING)
        self.assertEqual(self._control().last_error_code, None)

    def test_superseded_pending_command_is_never_sent(self):
        self._request('takeover')
        v1 = TakeoverCommand.objects.get(version=1)
        ConversationControl.objects.filter(pk=self._control().pk).update(state=State.ERROR)
        self._request('release')
        v1.refresh_from_db()
        self.assertEqual((v1.status, v1.last_error), (CmdStatus.FAILED, 'superseded'))
        send = FakeSend(agent_ack)
        svc.retry_due_takeover_commands(send=send)
        self.assertEqual([p.version for p in send.payloads], [2])

    @override_settings(AGENT_TAKEOVER_ENABLED=False)
    def test_flag_off_delivery_is_noop(self):
        control = ConversationControl.objects.create(
            business=self.biz, external_conversation_id=self.conv, state=State.TAKEOVER_PENDING, command_version=1,
            last_command_action='takeover', last_event_id=uuid.uuid4(),
        )
        command = TakeoverCommand.objects.create(
            conversation_control=control, version=1, action='takeover', occurred_at=timezone.now(),
            next_attempt_at=timezone.now(),
        )
        send = FakeSend(agent_ack)
        self.assertIsNone(svc.deliver_takeover_command(command.pk, send=send))
        self.assertEqual(svc.retry_due_takeover_commands(send=send)['due'], 0)
        self.assertEqual(send.payloads, [])

    def test_beat_schedule_registers_sweeper_once(self):
        entries = [e for e in settings.CELERY_BEAT_SCHEDULE.values() if e['task'] == 'leads.retry_due_takeover_commands']
        self.assertEqual(len(entries), 1)

    # Regression (2026-10-08 QA incident): a real takeover command sat
    # `pending`/attempts=0 forever because the celery-worker/celery-beat
    # Docker images were stale (built before apps.leads.tasks existed) — the
    # worker's own task registry never had `leads.deliver_takeover_command` /
    # `leads.retry_due_takeover_commands` at all, so every kick and every
    # Beat tick silently had nothing to run. `retry_due_takeover_commands`
    # itself was always correct (see the other tests in this class); the gap
    # was that nothing enforced the task names actually being importable.
    # This can't catch a stale *image* (it runs against live source like any
    # test), but it does fail loudly if the task names/module path ever drift.
    def test_takeover_tasks_are_registered_with_celery(self):
        from config.celery import app as celery_app

        for name in (
            'leads.deliver_takeover_command',
            'leads.retry_due_takeover_commands',
            'leads.deliver_staff_message',
            'leads.retry_due_staff_messages',
        ):
            self.assertIn(name, celery_app.tasks, f'{name} is not registered with the celery app')


# ── Cliente HMAC ────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.content = json.dumps(body).encode() if body is not None else b''


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self.calls = []
        self.response = response or _FakeResponse(200, {
            'ok': True, 'result': 'applied', 'received_version': 4, 'applied_version': 4, 'state': 'paused',
        })
        self.exc = exc

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.exc:
            raise self.exc
        return self.response


def _payload(**overrides):
    data = dict(
        external_conversation_id='wac1_0123456789abcdef0123456789abcdef', action='takeover',
        event_id=uuid.UUID('6f1c2a4e-8b7d-4c3a-9e2f-1a2b3c4d5e6f'), version=4,
        occurred_at=dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.timezone.utc), business_id=3,
    )
    data.update(overrides)
    return client.CommandPayload(**data)


@override_settings(**TAKEOVER_SETTINGS)
class TakeoverClientTests(TestCase):

    def test_exact_body(self):
        self.assertEqual(
            client.build_body(_payload()),
            b'{"event_id":"6f1c2a4e-8b7d-4c3a-9e2f-1a2b3c4d5e6f","version":4,'
            b'"occurred_at":"2026-10-06T12:00:00.000000Z","business_id":3}',
        )

    def test_request_path_headers_and_signature(self):
        url, body, headers = client.build_request(
            _payload(action='release'), base_url='https://agent.example.test', key_id='mirubro-inbound-1',
            secret=TAKEOVER_SECRET, timestamp=1791288000, request_id='3f1d2c4b-5a6e-4f70-8a91-b2c3d4e5f607',
        )
        path = '/integrations/mirubro/conversations/wac1_0123456789abcdef0123456789abcdef/release'
        self.assertEqual(url, 'https://agent.example.test' + path)
        self.assertEqual(set(headers), {
            'Content-Type', 'X-Mirubro-Key-Id', 'X-Mirubro-Timestamp', 'X-Request-Id', 'X-Mirubro-Signature',
        })
        canonical = '\n'.join([
            'v1', 'PUT', path, '1791288000', '3f1d2c4b-5a6e-4f70-8a91-b2c3d4e5f607', 'mirubro-inbound-1',
            hashlib.sha256(body).hexdigest(),
        ])
        self.assertFalse(canonical.endswith('\n'))
        expected = 'v1=' + hmac.new(TAKEOVER_SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(headers['X-Mirubro-Signature'], expected)
        self.assertEqual(headers['X-Mirubro-Key-Id'], 'mirubro-inbound-1')

    def test_base_url_prefix_is_part_of_signed_path(self):
        self.assertEqual(
            client.command_path('https://proxy.test/bot/', 'wac1_' + 'a' * 32, 'takeover'),
            '/bot/integrations/mirubro/conversations/wac1_' + 'a' * 32 + '/takeover',
        )

    def test_each_attempt_has_new_request_id_timestamp_signature_same_body(self):
        session = _FakeSession()
        with mock.patch.object(client.time, 'time', side_effect=[1791288000, 1791288031]):
            client.send_command(_payload(), session=session)
            client.send_command(_payload(), session=session)
        (m1, u1, k1), (m2, u2, k2) = session.calls
        self.assertEqual((m1, m2), ('PUT', 'PUT'))
        self.assertEqual(k1['data'], k2['data'])
        self.assertNotEqual(k1['headers']['X-Request-Id'], k2['headers']['X-Request-Id'])
        self.assertNotEqual(k1['headers']['X-Mirubro-Timestamp'], k2['headers']['X-Mirubro-Timestamp'])
        self.assertNotEqual(k1['headers']['X-Mirubro-Signature'], k2['headers']['X-Mirubro-Signature'])
        self.assertEqual(k1['headers']['X-Request-Id'], k1['headers']['X-Request-Id'].lower())
        self.assertIs(k1['allow_redirects'], False)
        self.assertEqual(k1['timeout'], 10)

    def test_success_response_parsed(self):
        response = client.send_command(_payload(), session=_FakeSession())
        self.assertEqual(response, client.AgentCommandResponse(
            kind=client.KIND_OK, http_status=200, result='applied', applied_version=4, agent_state='paused',
        ))

    def test_classification(self):
        def err(code):
            return {'ok': False, 'error': {'code': code, 'message': 'x'}}

        cases = [
            (200, {'ok': True, 'result': 'stale', 'applied_version': 9, 'state': 'active'}, client.KIND_OK, None),
            (200, {'ok': True, 'result': 'weird'}, client.KIND_RETRYABLE, 'invalid_response'),
            (200, None, client.KIND_RETRYABLE, 'invalid_response'),
            (302, None, client.KIND_TERMINAL, 'unexpected_redirect'),
            (400, err('invalid_payload'), client.KIND_TERMINAL, 'invalid_payload'),
            (401, err('invalid_signature'), client.KIND_TERMINAL, 'invalid_signature'),
            (403, err('takeover_disabled'), client.KIND_TERMINAL, 'takeover_disabled'),
            (403, err('tls_required'), client.KIND_TERMINAL, 'tls_required'),
            (404, err('conversation_not_found'), client.KIND_TERMINAL, 'conversation_not_found'),
            (409, err('version_conflict'), client.KIND_TERMINAL, 'version_conflict'),
            (409, err('business_mismatch'), client.KIND_TERMINAL, 'business_mismatch'),
            (418, err('something_else'), client.KIND_TERMINAL, 'http_418'),
            (429, None, client.KIND_RETRYABLE, 'http_429'),
            (500, None, client.KIND_RETRYABLE, 'http_500'),
            (503, {'html': True}, client.KIND_RETRYABLE, 'http_503'),
        ]
        for http_status, body, kind, code in cases:
            with self.subTest(status=http_status, code=code):
                response = client.send_command(_payload(), session=_FakeSession(_FakeResponse(http_status, body)))
                self.assertEqual((response.kind, response.error_code, response.http_status), (kind, code, http_status))

    def test_timeout_and_network_errors_are_retryable(self):
        timeout = client.send_command(_payload(), session=_FakeSession(exc=requests.Timeout()))
        self.assertEqual((timeout.kind, timeout.error_code), (client.KIND_RETRYABLE, 'timeout'))
        network = client.send_command(_payload(), session=_FakeSession(exc=requests.ConnectionError()))
        self.assertEqual((network.kind, network.error_code), (client.KIND_RETRYABLE, 'network_error'))

    @override_settings(AGENT_TAKEOVER_KEY_ID='')
    def test_missing_config_raises(self):
        with self.assertRaises(client.TakeoverClientConfigError):
            client.send_command(_payload(), session=_FakeSession())


# ── System checks ───────────────────────────────────────────────────────────

class TakeoverChecksTests(TestCase):

    def _ids(self):
        return sorted(error.id for error in check_agent_takeover_config())

    @override_settings(AGENT_TAKEOVER_ENABLED=False, AGENT_TAKEOVER_BASE_URL='', AGENT_TAKEOVER_SECRET='')
    def test_flag_off_requires_nothing(self):
        self.assertEqual(self._ids(), [])

    @override_settings(**TAKEOVER_SETTINGS)
    def test_valid_config(self):
        self.assertEqual(self._ids(), [])

    @override_settings(AGENT_TAKEOVER_ENABLED=True, AGENT_TAKEOVER_BASE_URL='', AGENT_TAKEOVER_KEY_ID='bad key!',
                       AGENT_TAKEOVER_SECRET='short')
    def test_invalid_config(self):
        self.assertEqual(self._ids(), ['leads.E003', 'leads.E004', 'leads.E005'])

    @override_settings(**{**TAKEOVER_SETTINGS, 'AGENT_TAKEOVER_BASE_URL': 'http://agent.local:3000', 'DEBUG': False})
    def test_plain_http_outside_debug(self):
        self.assertEqual(self._ids(), ['leads.E006'])

    @override_settings(**{**TAKEOVER_SETTINGS, 'AGENT_TAKEOVER_BASE_URL': 'http://agent.local:3000', 'DEBUG': True})
    def test_plain_http_allowed_in_debug(self):
        self.assertEqual(self._ids(), [])

    def test_registered(self):
        self.assertIn(check_agent_takeover_config, checks.registry.registry.registered_checks)


# ── Concurrencia real (PostgreSQL) ──────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class TakeoverConcurrencyTests(TakeoverMixin, TransactionTestCase):
    # Flush con CASCADE (FK treasury_* → business_business), ver memoria de tests.
    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL only')
        self._setup()
        kick = mock.patch.object(svc, '_kick')
        kick.start()
        self.addCleanup(kick.stop)

    def _race(self, *funcs):
        barrier = threading.Barrier(len(funcs))
        results: list = [None] * len(funcs)

        def run(index, func):
            from django.db import connections
            try:
                barrier.wait(timeout=10)
                results[index] = func()
            except Exception as exc:  # noqa: BLE001
                results[index] = exc
            finally:
                connections.close_all()

        threads = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(funcs)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return results

    def test_a_simultaneous_takeovers_create_one_command(self):
        other = self._member(self.biz, 'admin')
        lead = Lead.objects.select_related('agent_state').get(pk=self.lead.pk)
        for _ in range(3):
            results = self._race(
                lambda: svc.request_conversation_command(lead, 'takeover', user=self.user),
                lambda: svc.request_conversation_command(lead, 'takeover', user=other),
            )
            self.assertTrue(all(isinstance(r, svc.CommandRequestResult) for r in results), results)
        self.assertEqual(sorted(r.created for r in results), [False, False])
        self.assertEqual(ConversationControl.objects.count(), 1)
        self.assertEqual(TakeoverCommand.objects.count(), 1)
        control = self._control()
        self.assertEqual((control.state, control.command_version), (State.TAKEOVER_PENDING, 1))

    def test_a_first_ever_takeovers_race_on_insert(self):
        results = self._race(*[
            (lambda: svc.request_conversation_command(
                Lead.objects.select_related('agent_state').get(pk=self.lead.pk), 'takeover', user=self.user))
            for _ in range(4)
        ])
        self.assertTrue(all(isinstance(r, svc.CommandRequestResult) for r in results), results)
        self.assertEqual(sorted(r.created for r in results), [False, False, False, True])
        self.assertEqual({r.command_version for r in results}, {1})
        self.assertEqual(TakeoverCommand.objects.count(), 1)

    def test_b_takeover_and_release_simultaneous_from_active(self):
        ConversationControl.objects.create(business=self.biz, external_conversation_id=self.conv)
        lead = Lead.objects.select_related('agent_state').get(pk=self.lead.pk)
        results = self._race(
            lambda: svc.request_conversation_command(lead, 'takeover', user=self.user),
            lambda: svc.request_conversation_command(lead, 'release', user=self.user),
        )
        takeover, release = results
        self.assertIsInstance(takeover, svc.CommandRequestResult)
        self.assertTrue(takeover.created)
        # release corrió antes (idempotente: active) o después (409 conflict).
        if isinstance(release, svc.CommandRequestResult):
            self.assertEqual((release.created, release.state), (False, 'active'))
        else:
            self.assertIsInstance(release, svc.TakeoverConflict)
        self.assertEqual(TakeoverCommand.objects.count(), 1)
        control = self._control()
        self.assertEqual((control.state, control.command_version), (State.TAKEOVER_PENDING, 1))

    def test_c_parallel_deliveries_send_once_with_same_event(self):
        svc.request_conversation_command(
            Lead.objects.select_related('agent_state').get(pk=self.lead.pk), 'takeover', user=self.user,
        )
        command = TakeoverCommand.objects.get()
        sent = []
        lock = threading.Lock()

        def slow_send(payload):
            with lock:
                sent.append(payload)
            return agent_ack(payload)

        results = self._race(*[lambda: svc.deliver_takeover_command(command.pk, send=slow_send) for _ in range(4)])
        self.assertEqual(sorted(map(str, results)), ['None', 'None', 'None', 'delivered'])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].event_id, command.event_id)
        command.refresh_from_db()
        self.assertEqual((command.status, command.attempts), (CmdStatus.DELIVERED, 1))
        self.assertEqual(self._control().state, State.TAKEN)

    def test_d_late_ack_racing_new_release(self):
        lead = Lead.objects.select_related('agent_state').get(pk=self.lead.pk)
        svc.request_conversation_command(lead, 'takeover', user=self.user)
        v1 = TakeoverCommand.objects.get()
        claim_v1 = svc._claim(v1.pk, timezone.now())
        ConversationControl.objects.filter(pk=self._control().pk).update(state=State.ERROR)
        results = self._race(
            lambda: svc.request_conversation_command(lead, 'release', user=self.user),
            lambda: svc.record_command_response(claim_v1, ok(applied_version=1, state='paused')),
        )
        self.assertFalse(any(isinstance(r, Exception) for r in results), results)
        control = self._control()
        # Gane quien gane el lock, el estado final es el de v2 (release pendiente).
        self.assertEqual((control.state, control.command_version), (State.RELEASE_PENDING, 2))
        v1.refresh_from_db()
        self.assertEqual(v1.status, CmdStatus.DELIVERED)
