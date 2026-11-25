"""Contexto de turnos autenticado para el agente, sin inferencias del historial."""
from __future__ import annotations

import datetime as dt
import uuid

from django.test import override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.leads.models import AppointmentProposal, Lead, LeadAgentState

from .agent_client import bump, lead_path, sign_headers
from .factories import activate_turnos, make_business, make_channel, make_credential, make_instance
from .test_receiver_api import ProposalReceiverTestBase


class AppointmentContextTests(ProposalReceiverTestBase):
    def context(self, *, external_lead_id=None, credential=None, **sign_kwargs):
        path = lead_path(external_lead_id or self.base_payload['external_lead_id']) + 'appointment-context/'
        headers = sign_headers(
            path=path, body=b'', key_id=(credential or self.credential).key_id, method='GET', **sign_kwargs,
        )
        return self.client.get(path, **headers)

    def assertContext(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        # PROD-02D: `agenda_enabled` aditivo; estos tests tienen Turnos operativo.
        self.assertEqual(set(body), {'ok', 'external_lead_id', 'agenda_enabled', 'proposal', 'appointment'})
        self.assertIs(body['ok'], True)
        self.assertIs(body['agenda_enabled'], True)
        self.assertEqual(body['external_lead_id'], self.base_payload['external_lead_id'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIn('X-Request-Id', response)
        return body

    def test_no_proposal_or_appointment(self):
        self.proposal.delete()
        body = self.assertContext(self.context())
        self.assertIsNone(body['proposal'])
        self.assertIsNone(body['appointment'])

    def test_queued_proposal_exact_shape_snapshots_and_nullable_professional(self):
        AppointmentProposal.objects.filter(pk=self.proposal.pk).update(professional_name=None)
        body = self.assertContext(self.context())
        self.assertEqual(body['proposal'], {
            'id': str(self.proposal.pk), 'status': 'queued',
            'service_name': self.proposal.service_name, 'professional_name': None,
            'proposed_start_at': body['proposal']['proposed_start_at'],
            'expires_at': body['proposal']['expires_at'],
        })
        self.assertEqual(parse_datetime(body['proposal']['proposed_start_at']), self.proposal.proposed_start_at)
        self.assertEqual(parse_datetime(body['proposal']['expires_at']), self.proposal.expires_at)
        self.assertIsNone(body['appointment'])

    def test_pending_delivery_and_terminal_states_are_not_exposed(self):
        for status in ('pending_delivery', 'expired', 'superseded', 'converted', 'delivery_failed'):
            with self.subTest(status=status):
                AppointmentProposal.objects.filter(pk=self.proposal.pk).update(status=status)
                body = self.assertContext(self.context())
                self.assertIsNone(body['proposal'])
                self.assertIsNone(body['appointment'])

    def test_lazy_expiry(self):
        AppointmentProposal.objects.filter(pk=self.proposal.pk).update(expires_at=timezone.now() - dt.timedelta(seconds=1))
        self.assertIsNone(self.assertContext(self.context())['proposal'])
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, 'expired')

    def test_real_appointment_takes_precedence_and_preserves_status(self):
        appointment = self._appt(self.business, self.service, None, self.proposal.proposed_start_at)
        Lead.objects.filter(pk=self.lead.pk).update(appointment=appointment)
        for status in ('confirmed', 'cancelled'):
            with self.subTest(status=status):
                appointment.status = status
                appointment.save(update_fields=['status'])
                body = self.assertContext(self.context())
                self.assertIsNone(body['proposal'])
                self.assertEqual(body['appointment'], {
                    'id': str(appointment.pk), 'status': status,
                    'start_at': body['appointment']['start_at'],
                })
                self.assertEqual(parse_datetime(body['appointment']['start_at']), appointment.start_at)
        self.proposal.delete()
        self.assertIsNotNone(self.assertContext(self.context())['appointment'])

    def test_put_returns_same_context_for_applied_duplicate_and_stale(self):
        expected = self.assertContext(self.context())
        v2 = bump(self.base_payload, 2)
        for payload in (v2, v2, self.base_payload):
            body = self.put(payload).json()
            self.assertEqual(body['proposal'], expected['proposal'])
            self.assertEqual(body['appointment'], expected['appointment'])

    def test_created_put_includes_nullable_context(self):
        response = self.put(self.payload(external_conversation_id='new-conversation'))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.json()['proposal'])
        self.assertIsNone(response.json()['appointment'])

    def test_unknown_and_invalid_external_lead_id(self):
        self.assertError(self.context(external_lead_id=uuid.uuid4()), 404, 'lead_not_found')
        self.assertEqual(self.context(external_lead_id='not-a-uuid').status_code, 404)

    def test_missing_auth_bad_signature_and_signature_method_binding(self):
        path = lead_path(self.base_payload['external_lead_id']) + 'appointment-context/'
        self.assertError(self.client.get(path), 401, 'invalid_signature')
        self.assertError(self.context(secret='wrong-secret'), 401, 'invalid_signature')
        headers = sign_headers(path=path, body=b'', key_id=self.credential.key_id, method='PUT')
        self.assertError(self.client.get(path, **headers), 401, 'invalid_signature')

    def test_other_agent_cannot_read_even_with_business_header(self):
        other = make_instance('context-other-agent')
        credential = make_credential(other, key_id='context-other-key')
        response = self.context(credential=credential)
        self.assertError(response, 404, 'lead_not_found')
        path = lead_path(self.base_payload['external_lead_id']) + 'appointment-context/'
        headers = sign_headers(path=path, body=b'', key_id=credential.key_id, method='GET')
        self.assertError(self.client.get(path, HTTP_X_BUSINESS_ID=str(self.business.pk), **headers), 404, 'lead_not_found')

    def test_channel_disabled_or_reassigned_to_another_agent(self):
        self.channel.is_active = False
        self.channel.save(update_fields=['is_active'])
        self.assertError(self.context(), 403, 'channel_disabled')
        self.channel.is_active = True
        self.channel.agent_instance = make_instance('reassigned-channel')
        self.channel.save(update_fields=['is_active', 'agent_instance'])
        self.assertError(self.context(), 403, 'channel_disabled')

    def test_stored_lead_business_must_match_channel(self):
        business = make_business('context-other-business')
        channel = make_channel(self.instance, business, phone_number_id='999111')
        LeadAgentState.objects.filter(pk=self.lead.pk).update(channel=channel)
        self.assertError(self.context(), 409, 'business_mismatch')

    def test_inactive_business_rejected(self):
        self.business.status = 'cancelled'
        self.business.save(update_fields=['status'])
        self.assertError(self.context(), 403, 'business_inactive')

    def test_foreign_business_appointment_not_exposed(self):
        business = make_business('foreign-appointment')
        activate_turnos(business)
        service, _ = self._agenda(business)
        appointment = self._appt(business, service, None, self.proposal.proposed_start_at)
        Lead.objects.filter(pk=self.lead.pk).update(appointment=appointment)
        self.assertError(self.context(), 409, 'business_mismatch')

    def test_integration_disabled(self):
        with override_settings(AGENT_INTEGRATION_ENABLED=False):
            self.assertError(self.context(), 503, 'unavailable')
