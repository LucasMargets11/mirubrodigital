"""Bandeja operativa de Leads (LEADS SLICE 2): `GET /api/v1/leads/`.

Cubre los campos nuevos de la fila — preview del último mensaje del paciente,
resumen compacto del turno vinculado y control compacto de la conversación —,
el filtro `appointment=with|without`, aislamiento entre tenants y que el
número de queries no crezca con la página.
"""
from __future__ import annotations

import datetime as dt
import uuid

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APITestCase

from apps.appointments.models import Appointment
from apps.appointments.tests.test_customer_core_access import _login
from apps.customers.models import Customer
from apps.leads.models import ConversationControl, Lead, LeadAgentMessage

from .test_appointment_link import LeadAppointmentLinkMixin
from .test_crm_api import LIST_URL

S = Appointment.Status
Sender = LeadAgentMessage.Sender
State = ConversationControl.State


def conv_id() -> str:
    return 'wac1_' + uuid.uuid4().hex


class InboxListMixin(LeadAppointmentLinkMixin):

    def _message(self, lead, sender, text, sent_at, *, message_id=None):
        role = LeadAgentMessage.Role.USER if sender == Sender.PATIENT else LeadAgentMessage.Role.ASSISTANT
        return LeadAgentMessage.objects.create(
            lead=lead, external_message_id=message_id or uuid.uuid4().hex, role=role, sender=sender,
            text=text, sent_at=sent_at,
        )

    def _control(self, biz, conversation_id, *, state=State.TAKEN, taken_by=None, taken_at=None):
        return ConversationControl.objects.create(
            business=biz, external_conversation_id=conversation_id, state=state,
            command_version=1, last_event_id=uuid.uuid4(), last_command_action='takeover',
            taken_by=taken_by, taken_at=taken_at or (timezone.now() if state == State.TAKEN else None),
        )

    def _link(self, lead, appointment):
        Lead.objects.filter(pk=lead.pk).update(appointment=appointment)

    def _rows(self, params=None):
        response = self.client.get(LIST_URL, params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row['id']: row for row in response.data['results']}

    def _row(self, lead, params=None):
        return self._rows(params)[str(lead.pk)]


# ── Último mensaje del paciente ─────────────────────────────────────────────

class LastPatientMessageTests(InboxListMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('inbox-msg')
        self.user = _login(self.client, self.biz, 'owner')
        self.lead = self._lead(self.biz, self.channel, summary='Resumen del agente')
        self.t0 = timezone.now() - dt.timedelta(hours=1)

    def test_no_messages_is_null_without_summary_fallback(self):
        row = self._row(self.lead)
        self.assertIsNone(row['last_patient_message_text'])
        self.assertIsNone(row['last_patient_message_at'])

    def test_only_bot_and_staff_messages_is_null(self):
        self._message(self.lead, Sender.BOT, 'Hola, soy el bot', self.t0)
        self._message(self.lead, Sender.STAFF, 'Te escribe recepción', self.t0 + dt.timedelta(minutes=1))
        self.assertIsNone(self._row(self.lead)['last_patient_message_text'])

    def test_later_bot_and_staff_replies_do_not_replace_preview(self):
        self._message(self.lead, Sender.PATIENT, '¿Para cuándo me agendaste?', self.t0)
        self._message(self.lead, Sender.BOT, 'Ya te respondo', self.t0 + dt.timedelta(minutes=1))
        self._message(self.lead, Sender.STAFF, 'Hola, soy recepción', self.t0 + dt.timedelta(minutes=2))
        row = self._row(self.lead)
        self.assertEqual(row['last_patient_message_text'], '¿Para cuándo me agendaste?')
        self.assertEqual(parse_datetime(row['last_patient_message_at']), self.t0)

    def test_orders_by_sent_at_not_insertion(self):
        self._message(self.lead, Sender.PATIENT, 'más nuevo', self.t0 + dt.timedelta(minutes=5))
        self._message(self.lead, Sender.PATIENT, 'más viejo', self.t0)
        self.assertEqual(self._row(self.lead)['last_patient_message_text'], 'más nuevo')

    def test_same_sent_at_tie_break_is_deterministic(self):
        first = self._message(self.lead, Sender.PATIENT, 'uno', self.t0)
        second = self._message(self.lead, Sender.PATIENT, 'dos', self.t0)
        expected = max((first, second), key=lambda message: message.pk).text  # -id
        for _ in range(3):
            self.assertEqual(self._row(self.lead)['last_patient_message_text'], expected)

    def test_long_text_is_truncated_to_240_chars(self):
        self._message(self.lead, Sender.PATIENT, 'x' * 1000, self.t0)
        self.assertEqual(self._row(self.lead)['last_patient_message_text'], 'x' * 240)

    def test_other_lead_episode_does_not_contaminate(self):
        # Mismo canal y conversación, otro episodio (Lead): sus mensajes no se mezclan.
        conversation_id = self.lead.agent_state.external_conversation_id
        other = self._lead(self.biz, self.channel, external_conversation_id=conversation_id)
        self._message(self.lead, Sender.PATIENT, 'mío', self.t0)
        self._message(other, Sender.PATIENT, 'del otro episodio', self.t0 + dt.timedelta(minutes=5))
        rows = self._rows()
        self.assertEqual(rows[str(self.lead.pk)]['last_patient_message_text'], 'mío')
        self.assertEqual(rows[str(other.pk)]['last_patient_message_text'], 'del otro episodio')


# ── Resumen del turno vinculado ─────────────────────────────────────────────

class AppointmentSummaryTests(InboxListMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('inbox-appt')
        self.user = _login(self.client, self.biz, 'owner')
        self.lead = self._lead(self.biz, self.channel)
        self.now = timezone.now()

    def _summary(self, **appointment_kwargs):
        appointment = self._appointment(self.biz, **appointment_kwargs)
        self._link(self.lead, appointment)
        return appointment, self._row(self.lead)['appointment']

    def test_no_appointment_is_null(self):
        self.assertIsNone(self._row(self.lead)['appointment'])

    def test_compact_contract(self):
        appointment, summary = self._summary(start=self.now + dt.timedelta(days=2))
        self.assertEqual(set(summary), {
            'id', 'status', 'start_at', 'end_at', 'service_name', 'professional_name', 'is_upcoming', 'is_past',
        })
        self.assertEqual(summary['id'], str(appointment.pk))
        self.assertEqual(summary['professional_name'], 'Lu')
        body = str(summary)
        for forbidden in ('customer_phone', 'customer_name', 'notes', 'payment', 'Ana Cliente'):
            self.assertNotIn(forbidden, body)

    def test_confirmed_future_is_upcoming(self):
        _, summary = self._summary(start=self.now + dt.timedelta(days=2))
        self.assertEqual(summary['status'], S.CONFIRMED)
        self.assertTrue(summary['is_upcoming'])
        self.assertFalse(summary['is_past'])

    def test_confirmed_past_keeps_persisted_status(self):
        appointment, summary = self._summary(start=self.now - dt.timedelta(days=3))
        self.assertEqual(summary['status'], S.CONFIRMED)
        self.assertFalse(summary['is_upcoming'])
        self.assertTrue(summary['is_past'])
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, S.CONFIRMED)

    def test_cancelled_future_is_not_upcoming(self):
        _, summary = self._summary(status_=S.CANCELLED, start=self.now + dt.timedelta(days=2))
        self.assertEqual(summary['status'], S.CANCELLED)
        self.assertFalse(summary['is_upcoming'])
        self.assertFalse(summary['is_past'])

    def test_completed_and_no_show_past(self):
        for status_ in (S.COMPLETED, S.NO_SHOW):
            with self.subTest(status_):
                _, summary = self._summary(status_=status_, start=self.now - dt.timedelta(days=1))
                self.assertEqual(summary['status'], status_)
                self.assertFalse(summary['is_upcoming'])
                self.assertTrue(summary['is_past'])

    def test_pending_payment_with_live_hold_is_upcoming(self):
        _, summary = self._summary(
            status_=S.PENDING_PAYMENT, start=self.now + dt.timedelta(days=1),
            expires_at=self.now + dt.timedelta(minutes=30),
        )
        self.assertEqual(summary['status'], S.PENDING_PAYMENT)
        self.assertTrue(summary['is_upcoming'])

    def test_pending_payment_with_expired_hold_is_effectively_expired(self):
        appointment, summary = self._summary(
            status_=S.PENDING_PAYMENT, start=self.now + dt.timedelta(days=1),
            expires_at=self.now - dt.timedelta(minutes=1),
        )
        self.assertEqual(summary['status'], S.EXPIRED)
        self.assertFalse(summary['is_upcoming'])
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, S.PENDING_PAYMENT)  # sin cambios persistidos

    def test_professional_null_and_service_name_snapshot(self):
        service, _ = self._agenda(self.biz)
        customer = Customer.objects.create(business=self.biz, name='Bea', phone='1155550102')
        appointment = self._appt(self.biz, service, customer, self.now + dt.timedelta(days=1), pro=None)
        service.name = 'Nombre nuevo'
        service.save(update_fields=['name'])
        self._link(self.lead, appointment)
        summary = self._row(self.lead)['appointment']
        self.assertIsNone(summary['professional_name'])
        self.assertEqual(summary['service_name'], 'Corte')


# ── Control compacto de la conversación ─────────────────────────────────────

class ConversationControlSummaryTests(InboxListMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('inbox-ctl')
        self.user = _login(self.client, self.biz, 'owner')
        self.conv = conv_id()
        self.lead = self._lead(self.biz, self.channel, external_conversation_id=self.conv)

    def test_without_control_is_active(self):
        row = self._row(self.lead)
        self.assertEqual(row['conversation_control'], {'state': State.ACTIVE, 'taken_by': None, 'taken_at': None, 'handoff_pending': False})
        self.assertEqual(row['conversation_state'], State.ACTIVE)

    def test_without_agent_state_is_null(self):
        lead = Lead.objects.create(business=self.biz)
        row = self._row(lead)
        self.assertIsNone(row['conversation_control'])
        self.assertIsNone(row['conversation_state'])

    def test_taken_by_is_the_operator_not_the_assignee(self):
        operator = self._member(self.biz, 'manager', first_name='Operadora')
        assignee = self._member(self.biz, 'manager', first_name='Asignada')
        Lead.objects.filter(pk=self.lead.pk).update(assigned_to=assignee)
        control = self._control(self.biz, self.conv, taken_by=operator)
        row = self._row(self.lead)
        self.assertEqual(row['conversation_control']['state'], State.TAKEN)
        self.assertEqual(row['conversation_control']['taken_by']['id'], operator.pk)
        self.assertEqual(row['conversation_control']['taken_by']['display_name'], 'Operadora')
        self.assertIsNotNone(row['conversation_control']['taken_at'])
        self.assertEqual(row['assigned_to']['id'], assignee.pk)
        self.assertEqual(row['conversation_state'], State.TAKEN)  # compatibilidad
        self.assertEqual(control.pk, ConversationControl.objects.get(business=self.biz).pk)

    def test_shared_conversation_across_episodes(self):
        operator = self._member(self.biz, 'manager', first_name='Op')
        other = self._lead(self.biz, self.channel, external_conversation_id=self.conv)
        self._control(self.biz, self.conv, taken_by=operator)
        rows = self._rows()
        for lead in (self.lead, other):
            self.assertEqual(rows[str(lead.pk)]['conversation_control']['taken_by']['id'], operator.pk)

    def test_same_conversation_id_in_other_tenant_does_not_contaminate(self):
        other_biz, other_channel = self._setup_tenant('inbox-ctl-other')
        intruder = self._member(other_biz, 'manager', first_name='Intrusa')
        self._lead(other_biz, other_channel, external_conversation_id=self.conv)
        self._control(other_biz, self.conv, taken_by=intruder)
        row = self._row(self.lead)
        self.assertEqual(row['conversation_control'], {'state': State.ACTIVE, 'taken_by': None, 'taken_at': None, 'handoff_pending': False})
        self.assertEqual(row['conversation_state'], State.ACTIVE)
        self.assertNotIn('Intrusa', str(self._rows()))

    def test_error_and_pending_states(self):
        for state in (State.ERROR, State.TAKEOVER_PENDING, State.RELEASE_PENDING):
            with self.subTest(state):
                ConversationControl.objects.filter(business=self.biz).delete()
                self._control(self.biz, self.conv, state=state)
                row = self._row(self.lead)
                self.assertEqual(row['conversation_control']['state'], state)
                self.assertIsNone(row['conversation_control']['taken_by'])


# ── Filtro appointment=with|without ─────────────────────────────────────────

class AppointmentFilterTests(InboxListMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('inbox-flt')
        self.user = _login(self.client, self.biz, 'owner')
        now = timezone.now()
        self.without = self._lead(self.biz, self.channel)
        self.future = self._lead(self.biz, self.channel)
        self.past = self._lead(self.biz, self.channel)
        self.cancelled = self._lead(self.biz, self.channel)
        self.completed = self._lead(self.biz, self.channel)
        self._link(self.future, self._appointment(self.biz, start=now + dt.timedelta(days=1)))
        self._link(self.past, self._appointment(self.biz, start=now - dt.timedelta(days=3)))
        self._link(self.cancelled, self._appointment(self.biz, status_=S.CANCELLED, start=now + dt.timedelta(days=2)))
        self._link(self.completed, self._appointment(self.biz, status_=S.COMPLETED, start=now - dt.timedelta(days=5)))

    def test_with_includes_any_linked_appointment(self):
        ids = set(self._ids(self.client.get(LIST_URL, {'appointment': 'with'})))
        self.assertEqual(ids, {str(lead.pk) for lead in (self.future, self.past, self.cancelled, self.completed)})

    def test_without(self):
        self.assertEqual(self._ids(self.client.get(LIST_URL, {'appointment': 'without'})), [str(self.without.pk)])

    def test_invalid_value(self):
        response = self.client.get(LIST_URL, {'appointment': 'future'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', response.data)

    def test_tenant_isolation(self):
        other_biz, other_channel = self._setup_tenant('inbox-flt-other')
        foreign = self._lead(other_biz, other_channel)
        self._link(foreign, self._appointment(other_biz))
        ids = set(self._ids(self.client.get(LIST_URL, {'appointment': 'with'})))
        self.assertNotIn(str(foreign.pk), ids)


# ── Performance ─────────────────────────────────────────────────────────────

class InboxQueryCountTests(InboxListMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('inbox-perf')
        self.user = _login(self.client, self.biz, 'owner')
        self.assignee = self._member(self.biz, 'manager')
        self.operator = self._member(self.biz, 'manager')
        self.customer = Customer.objects.create(business=self.biz, name='C', phone='1')

    def _full_lead(self):
        conversation_id = conv_id()
        lead = self._lead(self.biz, self.channel, external_conversation_id=conversation_id)
        Lead.objects.filter(pk=lead.pk).update(assigned_to=self.assignee, customer=self.customer)
        self._link(lead, self._appointment(self.biz))
        now = timezone.now()
        self._message(lead, Sender.PATIENT, 'hola', now - dt.timedelta(minutes=2))
        self._message(lead, Sender.BOT, 'respuesta', now - dt.timedelta(minutes=1))
        self._control(self.biz, conversation_id, taken_by=self.operator)
        return lead

    def _count(self):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return len(ctx), response

    def test_query_count_is_constant_from_one_lead_to_full_page(self):
        self._full_lead()
        single, _ = self._count()
        for _ in range(24):
            self._full_lead()
        full, response = self._count()
        self.assertEqual(len(response.data['results']), 25)
        self.assertEqual(single, full)
        row = response.data['results'][0]
        self.assertEqual(row['conversation_control']['taken_by']['id'], self.operator.pk)
        self.assertEqual(row['appointment']['professional_name'], 'Lu')
        self.assertEqual(row['last_patient_message_text'], 'hola')
