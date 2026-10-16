"""Vínculo humano Lead → Appointment (LEADS 04B.2): `PATCH /api/v1/leads/{id}/` con `appointment`.

El vínculo solo apunta a un turno EXISTENTE del mismo Business: nunca crea ni
modifica el turno, ni cambia status/outcome/atención del Lead, y sobrevive a
los syncs posteriores del agente.
"""
from __future__ import annotations

import datetime as dt
import uuid
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts import rbac
from apps.appointments.models import Appointment
from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin, _login, _turnos_business
from apps.customers.models import Customer
from apps.leads.models import Lead

from .agent_client import T2, bump, handoff_requested, make_payload, signed_put
from .factories import TEST_KEY, make_channel, make_credential, make_instance
from .test_crm_api import LeadApiMixin, _detail_url

NOT_FOUND_MESSAGE = 'El turno no existe en este negocio.'
S = Appointment.Status


class LeadAppointmentLinkMixin(LeadApiMixin, TurnosAgendaMixin):

    def _appointment(self, biz, *, status_=S.CONFIRMED, start=None, expires_at=None):
        agendas = self.__dict__.setdefault('_agendas', {})
        if biz.pk not in agendas:
            agendas[biz.pk] = self._agenda(biz)
        service, pro = agendas[biz.pk]
        customer = Customer.objects.create(business=biz, name='Ana Cliente', phone='1155550101')
        start = start or timezone.now() + dt.timedelta(days=1)
        return self._appt(biz, service, customer, start, status_=status_, pro=pro, expires_at=expires_at)

    @staticmethod
    def _snapshot(appointment):
        return Appointment.objects.filter(pk=appointment.pk).values().get()

    @staticmethod
    def _crm(lead):
        return Lead.objects.filter(pk=lead.pk).values(
            'status', 'outcome', 'needs_attention_at', 'acknowledged_at', 'acknowledged_by', 'closed_at', 'closed_by',
            'assigned_to', 'customer',
        ).get()


class LeadAppointmentLinkTests(LeadAppointmentLinkMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('link')
        self.user = _login(self.client, self.biz, 'manager')
        self.lead = self._lead(self.biz, self.channel)
        self.appointment = self._appointment(self.biz)

    def patch(self, data, lead=None):
        return self.client.patch(_detail_url(lead or self.lead), data, format='json')

    def test_link_valid_appointment(self):
        stamp = timezone.now() - dt.timedelta(hours=1)
        Lead.objects.filter(pk=self.lead.pk).update(needs_attention_at=stamp)
        crm_before = self._crm(self.lead)
        appt_before = self._snapshot(self.appointment)
        appointments = Appointment.objects.count()

        response = self.patch({'appointment': str(self.appointment.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['appointment'], {
            'id': str(self.appointment.pk),
            'start_at': response.data['appointment']['start_at'],
            'end_at': response.data['appointment']['end_at'],
            'status': 'confirmed',
            'service_name': 'Corte',
        })
        self.assertTrue(response.data['needs_attention'])
        # Sin datos de contacto del turno en la representación.
        self.assertNotIn('1155550000', str(response.data['appointment']))
        self.assertNotIn('Ana Cliente', str(response.data['appointment']))

        self.lead.refresh_from_db()
        self.assertEqual(self.lead.appointment_id, self.appointment.pk)
        self.assertEqual(self._crm(self.lead), crm_before)
        self.assertEqual(self._snapshot(self.appointment), appt_before)
        self.assertEqual(Appointment.objects.count(), appointments)

    def test_unlink(self):
        Lead.objects.filter(pk=self.lead.pk).update(appointment=self.appointment)
        crm_before = self._crm(self.lead)
        appt_before = self._snapshot(self.appointment)

        response = self.patch({'appointment': None})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNone(response.data['appointment'])
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.appointment_id)
        self.assertEqual(self._crm(self.lead), crm_before)
        self.assertEqual(self._snapshot(self.appointment), appt_before)

    def test_unlink_when_not_linked_is_noop(self):
        response = self.patch({'appointment': None})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNone(response.data['appointment'])

    def test_relink_to_another_appointment(self):
        Lead.objects.filter(pk=self.lead.pk).update(appointment=self.appointment)
        other = self._appointment(self.biz, start=timezone.now() + dt.timedelta(days=2))
        response = self.patch({'appointment': str(other.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.appointment_id, other.pk)

    def test_keeping_current_appointment_is_noop(self):
        Lead.objects.filter(pk=self.lead.pk).update(appointment=self.appointment)
        updated_at = Lead.objects.values_list('updated_at', flat=True).get(pk=self.lead.pk)
        response = self.patch({'appointment': str(self.appointment.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(Lead.objects.values_list('updated_at', flat=True).get(pk=self.lead.pk), updated_at)

    def test_nonexistent_and_foreign_appointment_indistinguishable(self):
        other_biz, _ = self._setup_tenant('link-other')
        foreign = self._appointment(other_biz)
        foreign_before = self._snapshot(foreign)

        missing = self.patch({'appointment': str(uuid.uuid4())})
        cross = self.patch({'appointment': str(foreign.pk)})
        for response in (missing, cross):
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
            self.assertEqual(response.data, {'appointment': [NOT_FOUND_MESSAGE]})
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.appointment_id)
        self.assertEqual(self._snapshot(foreign), foreign_before)
        self.assertFalse(foreign.leads.exists())

    def test_invalid_uuid(self):
        response = self.patch({'appointment': 'no-es-un-uuid'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', response.data)

    def test_invalid_appointment_rolls_back_other_fields(self):
        response = self.patch({'status': 'in_progress', 'appointment': str(uuid.uuid4())})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_link_together_with_other_fields(self):
        response = self.patch({'status': 'closed', 'outcome': 'booked', 'appointment': str(self.appointment.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.status, self.lead.outcome), (Lead.Status.CLOSED, Lead.Outcome.BOOKED))
        self.assertEqual(self.lead.appointment_id, self.appointment.pk)

    def test_patch_other_fields_keeps_link(self):
        Lead.objects.filter(pk=self.lead.pk).update(appointment=self.appointment)
        customer = Customer.objects.create(business=self.biz, name='Otro', phone='1155550202')
        response = self.patch({'status': 'in_progress', 'assigned_to': self.user.pk, 'customer': str(customer.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['appointment']['id'], str(self.appointment.pk))
        response = self.patch({'status': 'closed', 'outcome': 'other'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.appointment_id, self.appointment.pk)

    def test_linking_does_not_touch_status_outcome_or_attention(self):
        # Ni siquiera `booked`: vincular un turno no cierra ni cambia el resultado.
        stamp = timezone.now() - dt.timedelta(hours=2)
        Lead.objects.filter(pk=self.lead.pk).update(
            status=Lead.Status.IN_PROGRESS, needs_attention_at=stamp,
            acknowledged_at=stamp + dt.timedelta(minutes=5), acknowledged_by=self.user,
        )
        crm_before = self._crm(self.lead)
        self.assertEqual(self.patch({'appointment': str(self.appointment.pk)}).status_code, status.HTTP_200_OK)
        self.assertEqual(self._crm(self.lead), crm_before)
        self.assertEqual(self.patch({'appointment': None}).status_code, status.HTTP_200_OK)
        self.assertEqual(self._crm(self.lead), crm_before)

    def test_closed_lead_can_link_and_unlink(self):
        # Igual que `customer`: el vínculo es metadata CRM editable aunque el Lead esté cerrado.
        self.patch({'status': 'closed', 'outcome': 'other'})
        crm_before = self._crm(self.lead)
        self.assertEqual(self.patch({'appointment': str(self.appointment.pk)}).status_code, status.HTTP_200_OK)
        self.assertEqual(self._crm(self.lead), crm_before)
        self.assertEqual(self.patch({'appointment': None}).status_code, status.HTTP_200_OK)
        self.assertEqual(self._crm(self.lead), crm_before)

    def test_any_appointment_status_is_linkable(self):
        cases = {
            'confirmed': {'status_': S.CONFIRMED},
            'completed': {'status_': S.COMPLETED},
            'cancelled': {'status_': S.CANCELLED},
            'no_show': {'status_': S.NO_SHOW},
            'expired': {'status_': S.EXPIRED},
            'pending_payment': {'status_': S.PENDING_PAYMENT, 'expires_at': timezone.now() + dt.timedelta(minutes=10)},
        }
        for expected, kwargs in cases.items():
            with self.subTest(status=expected):
                appointment = self._appointment(self.biz, **kwargs)
                before = self._snapshot(appointment)
                response = self.patch({'appointment': str(appointment.pk)})
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                self.assertEqual(response.data['appointment']['status'], expected)
                self.assertEqual(self._snapshot(appointment), before)

    def test_expired_hold_reports_effective_status(self):
        appointment = self._appointment(
            self.biz, status_=S.PENDING_PAYMENT, expires_at=timezone.now() - dt.timedelta(minutes=1),
        )
        response = self.patch({'appointment': str(appointment.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['appointment']['status'], 'expired')
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, S.PENDING_PAYMENT)

    def test_same_appointment_on_several_leads(self):
        other_lead = self._lead(self.biz, self.channel)
        self.assertEqual(self.patch({'appointment': str(self.appointment.pk)}).status_code, status.HTTP_200_OK)
        response = self.patch({'appointment': str(self.appointment.pk)}, lead=other_lead)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(set(self.appointment.leads.values_list('pk', flat=True)), {self.lead.pk, other_lead.pk})

    def test_deleting_appointment_unlinks_lead(self):
        Lead.objects.filter(pk=self.lead.pk).update(appointment=self.appointment)
        self.appointment.delete()
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.appointment_id)
        response = self.client.get(_detail_url(self.lead))
        self.assertIsNone(response.data['appointment'])


class LeadAppointmentLinkAccessTests(LeadAppointmentLinkMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('link-acc')
        self.lead = self._lead(self.biz, self.channel)
        self.appointment = self._appointment(self.biz)

    def _link(self, client=None):
        return (client or self.client).patch(
            _detail_url(self.lead), {'appointment': str(self.appointment.pk)}, format='json',
        )

    def assertNotLinked(self):
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.appointment_id)

    def test_owner_admin_manager_can_link(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                Lead.objects.filter(pk=self.lead.pk).update(appointment=None)
                client = APIClient()
                _login(client, self.biz, role)
                self.assertEqual(self._link(client).status_code, status.HTTP_200_OK)
                self.lead.refresh_from_db()
                self.assertEqual(self.lead.appointment_id, self.appointment.pk)
                from apps.accounts.models import Membership

                Membership.objects.filter(business=self.biz).delete()  # 2 asientos en Turnos

    def test_viewer_cannot_link(self):
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self._link().status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotLinked()

    def test_view_leads_without_manage_leads_cannot_link(self):
        _login(self.client, self.biz, 'manager')
        perms = rbac.SERVICE_ROLE_PERMISSIONS['appointments']
        with mock.patch.dict(perms, {'manager': perms['manager'] - {'manage_leads'}}):
            self.assertEqual(self.client.get(_detail_url(self.lead)).status_code, status.HTTP_200_OK)
            self.assertEqual(self._link().status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotLinked()

    def test_unauthenticated(self):
        self.assertIn(self._link(APIClient()).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertNotLinked()

    def test_without_entitlement(self):
        from apps.business import entitlements as ent_module

        _login(self.client, self.biz, 'owner')
        with mock.patch.dict(ent_module.PLAN_ENTITLEMENTS, {'appointments_base': {'appointments.customers'}}):
            response = self._link()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'plan_entitlement_required')
        self.assertNotLinked()

    def test_cross_tenant_lead_is_404(self):
        other_biz, other_channel = self._setup_tenant('link-acc-other')
        foreign_lead = self._lead(other_biz, other_channel)
        _login(self.client, self.biz, 'owner')
        # Lead ajeno con turno propio → 404; con turno del otro tenant → 404 igual.
        foreign_appt = self._appointment(other_biz)
        for appt in (self.appointment, foreign_appt):
            with self.subTest(appointment=str(appt.pk)):
                response = self.client.patch(_detail_url(foreign_lead), {'appointment': str(appt.pk)}, format='json')
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        foreign_lead.refresh_from_db()
        self.assertIsNone(foreign_lead.appointment_id)

    def test_other_tenant_user_cannot_link(self):
        other_biz, _ = self._setup_tenant('link-acc-intruder')
        _login(self.client, other_biz, 'owner')
        self.assertEqual(self._link().status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotLinked()


@override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class LeadAppointmentLinkSurvivesAgentSyncTests(LeadAppointmentLinkMixin, APITestCase):

    PHONE_NUMBER_ID = '5550001113'

    def test_link_survives_agent_syncs(self):
        biz = _turnos_business(slug=f'link-sync-{uuid.uuid4().hex[:6]}')
        instance = make_instance(f'agent-{uuid.uuid4().hex[:8]}')
        credential = make_credential(instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        make_channel(instance, biz, phone_number_id=self.PHONE_NUMBER_ID)
        agent_client = APIClient()

        payload = make_payload(
            agent_instance_id=instance.external_id, business_id=biz.pk, phone_number_id=self.PHONE_NUMBER_ID,
        )
        created = signed_put(agent_client, payload, key_id=credential.key_id)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        lead = Lead.objects.get(pk=created.json()['mirubro_lead_id'])

        _login(self.client, biz, 'owner')
        appointment = self._appointment(biz)
        appt_before = self._snapshot(appointment)
        response = self.client.patch(_detail_url(lead), {'appointment': str(appointment.pk)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Versión nueva con pedido de atención del agente.
        update = bump(
            payload, 2, patient_name='Ana María', last_message_at=T2,
            handoff=handoff_requested('patient_asked_human', last_at=T2),
        )
        synced = signed_put(agent_client, update, key_id=credential.key_id)
        self.assertEqual(synced.status_code, status.HTTP_200_OK, synced.content)
        self.assertEqual(synced.json()['result'], 'applied')
        # Reenvío idéntico (duplicate) tampoco toca el vínculo.
        self.assertEqual(signed_put(agent_client, update, key_id=credential.key_id).status_code, status.HTTP_200_OK)

        lead.refresh_from_db()
        self.assertEqual(lead.appointment_id, appointment.pk)
        self.assertIsNotNone(lead.needs_attention_at)
        self.assertEqual(self._snapshot(appointment), appt_before)
        detail = self.client.get(_detail_url(lead)).data
        self.assertEqual(detail['appointment']['id'], str(appointment.pk))
        self.assertEqual(detail['agent_state']['patient_name'], 'Ana María')
