"""Historial humano/operativo del Lead (LEADS 04B.4): `LeadActivity` + `activity` en el detalle.

Solo las acciones humanas de la API CRM (PATCH y reconocer atención) generan
eventos, en la misma transacción que el cambio. Un evento por cambio
semántico; cerrar es un único `closed` con el outcome en metadata. El sync del
agente (applied/duplicate/stale, re-armado de atención) nunca genera actividad.
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
from apps.appointments.tests.test_customer_core_access import _login, _turnos_business
from apps.customers.models import Customer
from apps.leads.models import Lead, LeadActivity

from .agent_client import T2, T3, bump, handoff_requested, make_payload, signed_put
from .factories import TEST_KEY, make_channel, make_credential, make_instance
from .test_appointment_link import LeadAppointmentLinkMixin
from .test_crm_api import _detail_url

K = LeadActivity.Kind


def _ack_url(lead) -> str:
    return f'{_detail_url(lead)}acknowledge-attention/'


class LeadActivityMixin(LeadAppointmentLinkMixin):

    def _kinds(self, lead):
        return list(LeadActivity.objects.filter(lead=lead).values_list('kind', flat=True))

    def _customer(self, biz, name='Ana Cliente'):
        return Customer.objects.create(business=biz, name=name, phone=f'11{uuid.uuid4().int % 10**8:08d}')

    def _activity(self, lead, client=None):
        response = (client or self.client).get(_detail_url(lead))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['activity']


class LeadActivityPatchTests(LeadActivityMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('act')
        self.user = _login(self.client, self.biz, 'manager')
        self.lead = self._lead(self.biz, self.channel)

    def patch(self, data, lead=None, client=None):
        return (client or self.client).patch(_detail_url(lead or self.lead), data, format='json')

    def assertPatched(self, data):
        response = self.patch(data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    # ── Cada tipo de cambio ──

    def test_status_change(self):
        response = self.assertPatched({'status': 'in_progress'})
        event = LeadActivity.objects.get(lead=self.lead)
        self.assertEqual(event.kind, K.STATUS_CHANGED)
        self.assertEqual((event.previous_value, event.new_value), ('new', 'in_progress'))
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.business_id, self.biz.pk)
        # La respuesta del PATCH ya trae el historial.
        [row] = response.data['activity']
        self.assertEqual(row['id'], str(event.pk))
        self.assertEqual(row['kind'], 'status_changed')
        self.assertEqual(row['kind_display'], 'Cambio de estado')
        self.assertEqual(row['actor']['id'], self.user.pk)
        self.assertEqual(row['previous'], {'value': 'new', 'label': 'Nuevo'})
        self.assertEqual(row['new'], {'value': 'in_progress', 'label': 'En gestión'})
        self.assertEqual(row['metadata'], {})
        self.assertIsNotNone(row['occurred_at'])

    def test_close_is_single_event_with_outcome(self):
        self.assertPatched({'status': 'in_progress'})
        self.assertPatched({'status': 'closed', 'outcome': 'not_interested'})
        self.assertEqual(self._kinds(self.lead), [K.CLOSED, K.STATUS_CHANGED])
        closed = LeadActivity.objects.get(lead=self.lead, kind=K.CLOSED)
        self.assertEqual((closed.previous_value, closed.new_value), ('in_progress', 'closed'))
        self.assertEqual(closed.metadata, {'outcome': 'not_interested'})
        row = self._activity(self.lead)[0]
        self.assertEqual(row['kind'], 'closed')
        self.assertEqual(row['metadata']['outcome'], {'value': 'not_interested', 'label': 'No interesado'})

    def test_close_directly_from_new(self):
        self.assertPatched({'status': 'closed', 'outcome': 'spam'})
        event = LeadActivity.objects.get(lead=self.lead)
        self.assertEqual((event.kind, event.previous_value), (K.CLOSED, 'new'))

    def test_outcome_change_on_closed_lead(self):
        self.assertPatched({'status': 'closed', 'outcome': 'spam'})
        self.assertPatched({'outcome': 'duplicate'})
        event = LeadActivity.objects.get(lead=self.lead, kind=K.OUTCOME_CHANGED)
        self.assertEqual((event.previous_value, event.new_value), ('spam', 'duplicate'))
        row = self._activity(self.lead)[0]
        self.assertEqual(row['previous'], {'value': 'spam', 'label': 'Spam'})
        self.assertEqual(row['new'], {'value': 'duplicate', 'label': 'Duplicado'})

    def test_assign_reassign_unassign(self):
        member = self._member(self.biz, 'manager', first_name='Bea', last_name='Paz')
        self.assertPatched({'assigned_to': member.pk})
        self.assertPatched({'assigned_to': self.user.pk})  # auto-asignación: sin aviso, pero sí historial
        self.assertPatched({'assigned_to': None})
        events = list(LeadActivity.objects.filter(lead=self.lead).order_by('created_at'))
        self.assertEqual(
            [(e.kind, e.previous_value, e.new_value) for e in events],
            [(K.ASSIGNED, None, member.pk), (K.REASSIGNED, member.pk, self.user.pk), (K.UNASSIGNED, self.user.pk, None)],
        )
        rows = self._activity(self.lead)
        self.assertEqual([r['kind'] for r in rows], ['unassigned', 'reassigned', 'assigned'])
        self.assertEqual(rows[2]['new'], {'id': member.pk, 'display_name': 'Bea Paz'})
        self.assertIsNone(rows[2]['previous'])
        self.assertEqual(rows[0]['previous']['id'], self.user.pk)
        self.assertIsNone(rows[0]['new'])

    def test_customer_link_change_unlink(self):
        first, second = self._customer(self.biz, 'Ana'), self._customer(self.biz, 'Beto')
        self.assertPatched({'customer': str(first.pk)})
        self.assertPatched({'customer': str(second.pk)})
        self.assertPatched({'customer': None})
        events = list(LeadActivity.objects.filter(lead=self.lead).order_by('created_at'))
        self.assertEqual(
            [(e.kind, e.previous_value, e.new_value) for e in events],
            [
                (K.CUSTOMER_LINKED, None, str(first.pk)),
                (K.CUSTOMER_CHANGED, str(first.pk), str(second.pk)),
                (K.CUSTOMER_UNLINKED, str(second.pk), None),
            ],
        )
        rows = self._activity(self.lead)
        self.assertEqual(rows[1]['previous'], {'id': str(first.pk), 'display_name': 'Ana'})
        self.assertEqual(rows[1]['new'], {'id': str(second.pk), 'display_name': 'Beto'})

    def test_appointment_link_change_unlink(self):
        first = self._appointment(self.biz)
        second = self._appointment(self.biz, start=timezone.now() + dt.timedelta(days=2))
        self.assertPatched({'appointment': str(first.pk)})
        self.assertPatched({'appointment': str(second.pk)})
        self.assertPatched({'appointment': None})
        self.assertEqual(
            self._kinds(self.lead), [K.APPOINTMENT_UNLINKED, K.APPOINTMENT_CHANGED, K.APPOINTMENT_LINKED],
        )
        rows = self._activity(self.lead)
        self.assertEqual(rows[1]['previous']['id'], str(first.pk))
        self.assertEqual(rows[1]['new']['id'], str(second.pk))
        self.assertEqual(rows[1]['new']['service_name'], 'Corte')
        self.assertEqual(rows[1]['new']['status'], 'confirmed')

    def test_deleted_reference_keeps_event_readable(self):
        customer = self._customer(self.biz, 'Ana')
        self.assertPatched({'customer': str(customer.pk)})
        customer_id = str(customer.pk)
        customer.delete()  # SET_NULL en el Lead: no es actividad humana
        self.assertEqual(self._kinds(self.lead), [K.CUSTOMER_LINKED])
        row = self._activity(self.lead)[0]
        self.assertEqual(row['new'], {'id': customer_id, 'display_name': None})

    # ── No-op e inválidos ──

    def test_noop_patches_generate_no_activity(self):
        member = self._member(self.biz, 'manager')
        customer = self._customer(self.biz)
        Lead.objects.filter(pk=self.lead.pk).update(assigned_to=member, customer=customer)
        for payload in (
            {},
            {'status': 'new'},
            {'assigned_to': member.pk},
            {'customer': str(customer.pk)},
            {'appointment': None},
            {'outcome': None},
        ):
            with self.subTest(payload=payload):
                self.assertPatched(payload)
        self.assertEqual(self._kinds(self.lead), [])
        # Segundo cierre con el mismo outcome: tampoco.
        self.assertPatched({'status': 'closed', 'outcome': 'spam'})
        self.assertPatched({'status': 'closed', 'outcome': 'spam'})
        self.assertEqual(self._kinds(self.lead), [K.CLOSED])

    def test_invalid_patch_generates_no_activity(self):
        other_biz, _ = self._setup_tenant('act-other')
        foreign_customer = self._customer(other_biz)
        member = self._member(self.biz, 'manager')
        for payload in (
            {'status': 'closed'},  # sin outcome
            {'status': 'in_progress', 'outcome': 'spam'},
            {'status': 'bogus'},
            {'assigned_to': member.pk, 'customer': str(foreign_customer.pk)},  # un campo válido + uno inválido
            {'status': 'in_progress', 'appointment': str(uuid.uuid4())},
            {'status': 'in_progress', 'notes': 'x'},  # campo no editable
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.patch(payload).status_code, status.HTTP_400_BAD_REQUEST)
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.status, self.lead.assigned_to_id), (Lead.Status.NEW, None))
        self.assertFalse(LeadActivity.objects.exists())

    def test_failure_after_activity_rolls_back_everything(self):
        member = self._member(self.biz, 'manager')
        with mock.patch(
            'apps.leads.crm_serializers.schedule_lead_assigned_notification', side_effect=RuntimeError('boom'),
        ):
            with self.assertRaises(RuntimeError):
                self.patch({'status': 'in_progress', 'assigned_to': member.pk})
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.status, self.lead.assigned_to_id), (Lead.Status.NEW, None))
        self.assertFalse(LeadActivity.objects.exists())

    # ── Varios cambios en un PATCH ──

    def test_multi_field_patch_generates_one_event_per_change(self):
        customer = self._customer(self.biz)
        appointment = self._appointment(self.biz)
        response = self.assertPatched({
            'status': 'closed', 'outcome': 'booked', 'assigned_to': self.user.pk,
            'customer': str(customer.pk), 'appointment': str(appointment.pk),
        })
        events = list(LeadActivity.objects.filter(lead=self.lead).order_by('position'))
        self.assertEqual(
            [(e.kind, e.position) for e in events],
            [(K.CLOSED, 0), (K.ASSIGNED, 1), (K.CUSTOMER_LINKED, 2), (K.APPOINTMENT_LINKED, 3)],
        )
        self.assertEqual(len({e.created_at for e in events}), 1)  # mismo instante
        self.assertEqual({e.actor_id for e in events}, {self.user.pk})
        self.assertNotIn(K.OUTCOME_CHANGED, [e.kind for e in events])
        self.assertEqual(
            [r['kind'] for r in response.data['activity']],
            ['closed', 'assigned', 'customer_linked', 'appointment_linked'],
        )

    # ── Orden, actor ──

    def test_newest_first(self):
        self.assertPatched({'status': 'in_progress'})
        LeadActivity.objects.update(created_at=timezone.now() - dt.timedelta(minutes=5))
        customer = self._customer(self.biz)
        self.assertPatched({'customer': str(customer.pk)})
        self.assertPatched({'status': 'closed', 'outcome': 'linked_customer'})
        rows = self._activity(self.lead)
        self.assertEqual([r['kind'] for r in rows], ['closed', 'customer_linked', 'status_changed'])
        stamps = [r['occurred_at'] for r in rows]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_actor_is_the_requesting_user(self):
        owner_client = APIClient()
        owner = _login(owner_client, self.biz, 'owner')
        self.assertPatched({'status': 'in_progress'})
        self.assertEqual(self.patch({'status': 'closed', 'outcome': 'spam'}, client=owner_client).status_code, 200)
        actors = dict(LeadActivity.objects.filter(lead=self.lead).values_list('kind', 'actor_id'))
        self.assertEqual(actors, {K.STATUS_CHANGED: self.user.pk, K.CLOSED: owner.pk})
        rows = self._activity(self.lead)
        self.assertEqual([r['actor']['id'] for r in rows], [owner.pk, self.user.pk])

    def test_deleted_actor_keeps_event(self):
        self.assertPatched({'status': 'in_progress'})
        LeadActivity.objects.update(actor=None)  # equivalente a SET_NULL al borrar el usuario
        row = self._activity(self.lead)[0]
        self.assertIsNone(row['actor'])
        self.assertEqual(row['kind'], 'status_changed')


class LeadActivityAcknowledgeTests(LeadActivityMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('act-ack')
        self.user = _login(self.client, self.biz, 'manager')
        self.lead = self._lead(self.biz, self.channel)
        self.requested_at = timezone.now() - dt.timedelta(hours=1)
        Lead.objects.filter(pk=self.lead.pk).update(needs_attention_at=self.requested_at)

    def ack(self):
        return self.client.post(_ack_url(self.lead), format='json')

    def test_acknowledge_is_recorded_once(self):
        response = self.ack()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        event = LeadActivity.objects.get(lead=self.lead)
        self.assertEqual(event.kind, K.ATTENTION_ACKNOWLEDGED)
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.created_at, self.lead.acknowledged_at)
        self.assertEqual(event.metadata['needs_attention_at'][:19], self.requested_at.astimezone(dt.timezone.utc).isoformat()[:19])
        [row] = response.data['activity']
        self.assertEqual(row['kind'], 'attention_acknowledged')
        self.assertIsNone(row['previous'])
        self.assertIsNone(row['new'])
        # Reconocer de nuevo (no-op idempotente) no agrega eventos.
        self.assertEqual(self.ack().status_code, status.HTTP_200_OK)
        self.assertEqual(self._kinds(self.lead), [K.ATTENTION_ACKNOWLEDGED])

    def test_rejected_acknowledge_records_nothing(self):
        Lead.objects.filter(pk=self.lead.pk).update(status=Lead.Status.CLOSED, outcome=Lead.Outcome.SPAM)
        self.assertEqual(self.ack().status_code, status.HTTP_400_BAD_REQUEST)
        Lead.objects.filter(pk=self.lead.pk).update(status=Lead.Status.NEW, outcome=None, needs_attention_at=None)
        self.assertEqual(self.ack().status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(LeadActivity.objects.exists())

    def test_reacknowledge_after_new_request_records_again(self):
        self.assertEqual(self.ack().status_code, status.HTTP_200_OK)
        Lead.objects.filter(pk=self.lead.pk).update(needs_attention_at=timezone.now())  # el agente re-arma
        self.assertEqual(self.ack().status_code, status.HTTP_200_OK)
        self.assertEqual(self._kinds(self.lead), [K.ATTENTION_ACKNOWLEDGED, K.ATTENTION_ACKNOWLEDGED])


class LeadActivityAccessTests(LeadActivityMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('act-acc')
        self.lead = self._lead(self.biz, self.channel)
        self.event = LeadActivity.objects.create(
            lead=self.lead, kind=K.STATUS_CHANGED, previous_value='new', new_value='in_progress',
            created_at=timezone.now(),
        )

    def test_tenant_isolation(self):
        other_biz, other_channel = self._setup_tenant('act-acc-other')
        foreign_lead = self._lead(other_biz, other_channel)
        LeadActivity.objects.create(lead=foreign_lead, kind=K.CLOSED, created_at=timezone.now())
        _login(self.client, self.biz, 'owner')
        self.assertEqual([r['id'] for r in self._activity(self.lead)], [str(self.event.pk)])
        self.assertEqual(self.client.get(_detail_url(foreign_lead)).status_code, status.HTTP_404_NOT_FOUND)
        # Un usuario del otro tenant no ve el historial de este Lead.
        intruder = APIClient()
        _login(intruder, other_biz, 'owner')
        self.assertEqual(intruder.get(_detail_url(self.lead)).status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_reference_is_not_resolved(self):
        # Defensa en profundidad: un id de Customer de otro Business no se resuelve.
        other_biz, _ = self._setup_tenant('act-acc-ref')
        foreign_customer = self._customer(other_biz, 'Ajeno')
        LeadActivity.objects.create(
            lead=self.lead, kind=K.CUSTOMER_LINKED, new_value=str(foreign_customer.pk), created_at=timezone.now(),
        )
        _login(self.client, self.biz, 'owner')
        row = self._activity(self.lead)[0]
        self.assertEqual(row['new'], {'id': str(foreign_customer.pk), 'display_name': None})

    def test_business_must_match_lead(self):
        other_biz, _ = self._setup_tenant('act-acc-mismatch')
        with self.assertRaises(ValueError):
            LeadActivity.objects.create(
                business=other_biz, lead=self.lead, kind=K.CLOSED, created_at=timezone.now(),
            )

    def test_requires_view_leads(self):
        _login(self.client, self.biz, 'manager')
        perms = rbac.SERVICE_ROLE_PERMISSIONS['appointments']
        with mock.patch.dict(perms, {'manager': perms['manager'] - {'view_leads', 'manage_leads'}}):
            self.assertEqual(self.client.get(_detail_url(self.lead)).status_code, status.HTTP_403_FORBIDDEN)
        # view_leads sin manage_leads alcanza para leer el historial.
        with mock.patch.dict(perms, {'manager': perms['manager'] - {'manage_leads'}}):
            self.assertEqual(len(self._activity(self.lead)), 1)

    def test_viewer_and_unauthenticated(self):
        self.assertIn(
            APIClient().get(_detail_url(self.lead)).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.client.get(_detail_url(self.lead)).status_code, status.HTTP_403_FORBIDDEN)

    def test_requires_entitlement(self):
        from apps.business import entitlements as ent_module

        _login(self.client, self.biz, 'owner')
        with mock.patch.dict(ent_module.PLAN_ENTITLEMENTS, {'appointments_base': {'appointments.customers'}}):
            response = self.client.get(_detail_url(self.lead))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'plan_entitlement_required')

    def test_activity_is_read_only_via_api(self):
        _login(self.client, self.biz, 'owner')
        url = _detail_url(self.lead)
        response = self.client.patch(url, {'activity': []}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['activity'], ['Campo no editable.'])
        for method in ('put', 'delete', 'post'):
            with self.subTest(method=method):
                self.assertEqual(
                    getattr(self.client, method)(url, {}, format='json').status_code,
                    status.HTTP_405_METHOD_NOT_ALLOWED,
                )
        self.assertEqual(self.client.get(f'{url}activity/').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(list(LeadActivity.objects.values_list('pk', flat=True)), [self.event.pk])
        self.assertEqual(LeadActivity.objects.get().new_value, 'in_progress')


@override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class LeadActivityAgentSyncTests(LeadActivityMixin, APITestCase):

    PHONE_NUMBER_ID = '5550001114'

    def test_agent_sync_never_generates_activity_and_keeps_history(self):
        biz = _turnos_business(slug=f'act-sync-{uuid.uuid4().hex[:6]}')
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
        self.assertEqual(self._kinds(lead), [])  # creación por el agente: sin actividad

        # Pedido de atención del agente (escribe needs_attention_at): sin actividad.
        v2 = bump(payload, 2, last_message_at=T2, handoff=handoff_requested('patient_asked_human', last_at=T2))
        self.assertEqual(signed_put(agent_client, v2, key_id=credential.key_id).json()['result'], 'applied')
        self.assertEqual(self._kinds(lead), [])

        user = _login(self.client, biz, 'owner')
        self.assertEqual(self.client.post(_ack_url(lead), format='json').status_code, status.HTTP_200_OK)
        response = self.client.patch(_detail_url(lead), {'status': 'in_progress', 'assigned_to': user.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        human = list(LeadActivity.objects.filter(lead=lead).values_list('pk', 'kind', 'actor_id'))
        self.assertEqual(len(human), 3)

        # applied (nuevo motivo → re-arma atención), duplicate y stale: nada nuevo.
        v3 = bump(
            payload, 3, patient_name='Ana María', last_message_at=T3,
            handoff=handoff_requested('patient_asked_human', 'urgency', last_at=T3),
        )
        self.assertEqual(signed_put(agent_client, v3, key_id=credential.key_id).json()['result'], 'applied')
        self.assertEqual(signed_put(agent_client, v3, key_id=credential.key_id).json()['result'], 'duplicate')
        self.assertEqual(signed_put(agent_client, v2, key_id=credential.key_id).json()['result'], 'stale')

        lead.refresh_from_db()
        self.assertTrue(lead.attention_pending)  # el agente sí re-armó
        self.assertEqual(list(LeadActivity.objects.filter(lead=lead).values_list('pk', 'kind', 'actor_id')), human)
        detail = self.client.get(_detail_url(lead)).data
        self.assertEqual(
            [r['kind'] for r in detail['activity']], ['status_changed', 'assigned', 'attention_acknowledged'],
        )
        self.assertEqual(detail['agent_state']['patient_name'], 'Ana María')
