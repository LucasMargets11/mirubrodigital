"""Reconocimiento humano de atención (LEADS 04B.1).

`needs_attention_at` es evidencia del agente (solo la escribe el receiver);
`acknowledged_at`/`acknowledged_by` son del humano (solo la acción
`acknowledge-attention`). Pendiente ⇔ pedido informado, Lead abierto y sin
reconocimiento posterior. Cubre la acción (idempotencia, RBAC, entitlement,
tenant), el impacto en filtro/orden `priority` y el re-armado cuando el agente
vuelve a pedir atención después de un reconocimiento.
"""
from __future__ import annotations

import datetime as dt
import uuid
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership
from apps.appointments.tests.test_customer_core_access import _login, _turnos_business
from apps.customers.models import Customer
from apps.leads.models import Lead, LeadAgentState, LeadNote
from apps.notifications.models import BusinessNotification

from .agent_client import T1, T2, T3, bump, handoff_requested, make_payload, signed_put
from .factories import TEST_KEY, make_channel, make_credential, make_instance
from .test_crm_api import LIST_URL, LeadApiMixin, _detail_url


def _ack_url(lead) -> str:
    return f'{LIST_URL}{lead.pk}/acknowledge-attention/'


class AttentionAckApiTests(LeadApiMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('ack')
        self.user = _login(self.client, self.biz, 'manager')
        self.requested_at = timezone.now() - dt.timedelta(hours=1)
        self.lead = self._attention_lead(self.biz, self.channel, self.requested_at)

    def _attention_lead(self, biz, channel, requested_at, **lead_fields):
        lead = self._lead(
            biz, channel, handoff_requested=True, handoff_requested_at=requested_at,
            handoff_reasons=[{'code': 'patient_asked_human'}],
        )
        Lead.objects.filter(pk=lead.pk).update(needs_attention_at=requested_at, **lead_fields)
        lead.refresh_from_db()
        return lead

    def ack(self, lead=None, client=None):
        return (client or self.client).post(_ack_url(lead or self.lead), format='json')

    # ── Acción ──

    def test_acknowledge_sets_human_fields_and_keeps_evidence(self):
        before = timezone.now()
        response = self.ack()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertGreaterEqual(self.lead.acknowledged_at, before)
        self.assertEqual(self.lead.acknowledged_by_id, self.user.pk)
        self.assertEqual(self.lead.needs_attention_at, self.requested_at)  # evidencia intacta
        self.assertEqual(self.lead.status, Lead.Status.NEW)  # reconocer no cambia el estado
        self.assertIsNone(self.lead.assigned_to_id)
        self.assertFalse(self.lead.attention_pending)
        # Respuesta = detalle completo.
        self.assertIs(response.data['needs_attention'], False)
        self.assertEqual(response.data['acknowledged_by']['id'], self.user.pk)
        self.assertIsNotNone(response.data['acknowledged_at'])
        self.assertIsNotNone(response.data['needs_attention_at'])
        self.assertIn('agent_state', response.data)

    def test_acknowledge_is_idempotent(self):
        self.assertEqual(self.ack().status_code, status.HTTP_200_OK)
        self.lead.refresh_from_db()
        first_at, first_by, first_updated = self.lead.acknowledged_at, self.lead.acknowledged_by_id, self.lead.updated_at

        # Repetir (mismo usuario u otro) no cambia nada: conserva el primer reconocimiento.
        self.assertEqual(self.ack().status_code, status.HTTP_200_OK)
        other_client = APIClient()
        _login(other_client, self.biz, 'owner')
        response = self.ack(client=other_client)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['acknowledged_by']['id'], first_by)
        self.lead.refresh_from_db()
        self.assertEqual(
            (self.lead.acknowledged_at, self.lead.acknowledged_by_id, self.lead.updated_at),
            (first_at, first_by, first_updated),
        )

    def test_lead_without_attention_request_is_rejected(self):
        plain = self._lead(self.biz, self.channel)
        response = self.ack(plain)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('non_field_errors', response.data)
        plain.refresh_from_db()
        self.assertIsNone(plain.acknowledged_at)
        self.assertIsNone(plain.needs_attention_at)

    def test_closed_lead(self):
        # Cerrado con pedido sin reconocer: no está pendiente y no se reconoce (no se reabre).
        closed = self._attention_lead(
            self.biz, self.channel, self.requested_at, status=Lead.Status.CLOSED, outcome=Lead.Outcome.OTHER,
        )
        self.assertFalse(closed.attention_pending)
        response = self.ack(closed)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        closed.refresh_from_db()
        self.assertIsNone(closed.acknowledged_at)
        self.assertEqual(closed.status, Lead.Status.CLOSED)

        # Reconocido y después cerrado: reintentar sigue siendo 200 sin cambios (idempotente).
        self.assertEqual(self.ack().status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.patch(_detail_url(self.lead), {'status': 'closed', 'outcome': 'other'}, format='json').status_code,
            status.HTTP_200_OK,
        )
        self.lead.refresh_from_db()
        acked_at = self.lead.acknowledged_at
        response = self.ack()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.acknowledged_at, acked_at)
        self.assertEqual((self.lead.status, self.lead.outcome), (Lead.Status.CLOSED, Lead.Outcome.OTHER))

    def test_only_post_allowed(self):
        self.assertEqual(self.client.get(_ack_url(self.lead)).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            self.client.patch(_ack_url(self.lead), {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(self.client.delete(_ack_url(self.lead)).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_patch_cannot_write_acknowledgement(self):
        for field, value in (
            ('acknowledged_at', timezone.now().isoformat()), ('acknowledged_by', self.user.pk),
            ('needs_attention', False), ('needs_attention_at', None),
        ):
            with self.subTest(field=field):
                response = self.client.patch(_detail_url(self.lead), {field: value}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data[field], ['Campo no editable.'])
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.acknowledged_at)
        self.assertEqual(self.lead.needs_attention_at, self.requested_at)

    def test_crm_changes_keep_acknowledgement(self):
        self.ack()
        self.lead.refresh_from_db()
        acked = (self.lead.acknowledged_at, self.lead.acknowledged_by_id)
        self.client.patch(_detail_url(self.lead), {'status': 'in_progress'}, format='json')
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.acknowledged_at, self.lead.acknowledged_by_id), acked)
        self.assertEqual(self.lead.needs_attention_at, self.requested_at)

    def test_db_rejects_acknowledgement_without_request(self):
        plain = self._lead(self.biz, self.channel)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lead.objects.filter(pk=plain.pk).update(acknowledged_at=timezone.now())

    # ── Acceso ──

    def test_rbac(self):
        # Plan con 2 asientos: se va cambiando el rol de la misma membership.
        membership = Membership.objects.get(user=self.user, business=self.biz)
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                Membership.objects.filter(pk=membership.pk).update(role=role)
                lead = self._attention_lead(self.biz, self.channel, self.requested_at)
                self.assertEqual(self.ack(lead).status_code, status.HTTP_200_OK)

        Membership.objects.filter(pk=membership.pk).update(role='viewer')
        self.assertEqual(self.ack().status_code, status.HTTP_403_FORBIDDEN)
        Membership.objects.filter(pk=membership.pk).update(role='manager')
        self.assertIn(self.ack(client=APIClient()).status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

        # view_leads sin manage_leads: puede ver, no reconocer.
        from apps.accounts import permissions as perm_module

        real = perm_module.permissions_for_service

        def view_only(service, role, business=None):
            perms = dict(real(service, role, business))
            perms['manage_leads'] = False
            return perms

        with mock.patch.object(perm_module, 'permissions_for_service', side_effect=view_only):
            self.assertEqual(self.client.get(_detail_url(self.lead)).status_code, status.HTTP_200_OK)
            self.assertEqual(self.ack().status_code, status.HTTP_403_FORBIDDEN)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.acknowledged_at)

    def test_entitlement_required(self):
        from apps.business import entitlements as ent_module

        owner = APIClient()
        _login(owner, self.biz, 'owner')
        with mock.patch.dict(ent_module.PLAN_ENTITLEMENTS, {'appointments_base': {'appointments.customers'}}):
            response = self.ack(client=owner)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['code'], 'plan_entitlement_required')
        self.assertEqual(response.data['entitlement'], 'appointments.leads')
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.acknowledged_at)

    def test_cross_tenant_is_404(self):
        other_biz, other_channel = self._setup_tenant('ack-other')
        foreign = self._attention_lead(other_biz, other_channel, self.requested_at)
        self.assertEqual(self.ack(foreign).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(f'{LIST_URL}{uuid.uuid4()}/acknowledge-attention/').status_code,
                         status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.acknowledged_at)

    # ── Filtro y orden ──

    def test_needs_attention_filter_and_priority_use_pending_rule(self):
        now = timezone.now()
        LeadAgentState.objects.filter(pk=self.lead.pk).update(last_message_at=now - dt.timedelta(days=2))
        urgent = self._lead(self.biz, self.channel, urgency=True, last_message_at=now - dt.timedelta(hours=1))
        acked = self._attention_lead(self.biz, self.channel, self.requested_at)
        LeadAgentState.objects.filter(pk=acked.pk).update(last_message_at=now - dt.timedelta(days=3))
        self.assertEqual(self.ack(acked).status_code, status.HTTP_200_OK)

        def ids(**params):
            return self._ids(self.client.get(LIST_URL, params))

        self.assertEqual(ids(needs_attention='true'), [str(self.lead.pk)])
        self.assertEqual(set(ids(needs_attention='false')), {str(urgent.pk), str(acked.pk)})
        # Reconocido baja al lugar que le da su urgencia / último mensaje.
        self.assertEqual(ids(), [str(self.lead.pk), str(urgent.pk), str(acked.pk)])
        rows = {row['id']: row for row in self.client.get(LIST_URL).data['results']}
        self.assertIs(rows[str(self.lead.pk)]['needs_attention'], True)
        self.assertIs(rows[str(acked.pk)]['needs_attention'], False)
        self.assertIsNotNone(rows[str(acked.pk)]['acknowledged_at'])
        self.assertIsNotNone(rows[str(acked.pk)]['needs_attention_at'])

        # Nuevo pedido posterior al reconocimiento → vuelve a ser pendiente y a subir.
        Lead.objects.filter(pk=acked.pk).update(needs_attention_at=timezone.now())
        self.assertEqual(set(ids(needs_attention='true')), {str(self.lead.pk), str(acked.pk)})
        self.assertEqual(ids()[2], str(urgent.pk))


# ── Receiver: re-pedido de atención después de un reconocimiento ────────────

@override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class AttentionAckReceiverTests(LeadApiMixin, APITestCase):

    PHONE_NUMBER_ID = '5550002223'

    def setUp(self):
        self.biz = _turnos_business(slug=f'ackr-{uuid.uuid4().hex[:6]}')
        instance = make_instance(f'agent-{uuid.uuid4().hex[:8]}')
        self.credential = make_credential(instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        make_channel(instance, self.biz, phone_number_id=self.PHONE_NUMBER_ID)
        self.agent = APIClient()
        self.user = _login(self.client, self.biz, 'manager')
        self.v1 = make_payload(
            agent_instance_id=instance.external_id, business_id=self.biz.pk, phone_number_id=self.PHONE_NUMBER_ID,
            handoff=handoff_requested('patient_asked_human'),
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = signed_put(self.agent, self.v1, key_id=self.credential.key_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.lead = Lead.objects.get(pk=response.json()['mirubro_lead_id'])
        self.first_request = self.lead.needs_attention_at
        self.assertIsNotNone(self.first_request)

    def sync(self, payload):
        response = signed_put(self.agent, payload, key_id=self.credential.key_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response

    def acknowledge(self):
        response = self.client.post(_ack_url(self.lead), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        return self.lead.acknowledged_at, self.lead.acknowledged_by_id

    def test_unchanged_reasons_keep_acknowledgement(self):
        acked = self.acknowledge()
        response = self.sync(bump(self.v1, 2, summary='otro resumen', last_message_at=T2))
        self.assertEqual(response.json()['result'], 'applied')
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.needs_attention_at, self.first_request)
        self.assertEqual((self.lead.acknowledged_at, self.lead.acknowledged_by_id), acked)
        self.assertFalse(self.lead.attention_pending)

    def test_repeated_reason_after_ack_makes_it_pending_again(self):
        acked = self.acknowledge()
        with self.captureOnCommitCallbacks(execute=True):
            self.sync(bump(self.v1, 2, handoff=handoff_requested('patient_asked_human', last_at=T2), last_message_at=T2))
        self.lead.refresh_from_db()
        # Evidencia avanza (posterior al reconocimiento); datos humanos intactos.
        self.assertGreater(self.lead.needs_attention_at, acked[0])
        self.assertEqual((self.lead.acknowledged_at, self.lead.acknowledged_by_id), acked)
        self.assertTrue(self.lead.attention_pending)
        self.assertEqual(self.client.get(_detail_url(self.lead)).data['needs_attention'], True)
        self.assertEqual(self._ids(self.client.get(LIST_URL, {'needs_attention': 'true'})), [str(self.lead.pk)])
        # LEADS 04B.3: ciclo nuevo → segundo aviso.
        self.assertEqual(
            BusinessNotification.objects.filter(business=self.biz, kind='agent_lead_handoff').count(), 2,
        )

        # Un humano lo reconoce de nuevo: nuevo timestamp y autor.
        second = self.acknowledge()
        self.assertGreater(second[0], acked[0])
        self.assertFalse(self.lead.attention_pending)

    def test_new_reason_after_ack_makes_it_pending_again(self):
        self.acknowledge()
        handoff = handoff_requested('patient_asked_human')
        handoff['reasons'].append({'code': 'urgency', 'first_at': T2, 'last_at': T2})
        self.sync(bump(self.v1, 2, handoff=handoff, urgency=True, last_message_at=T2))
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.attention_pending)

    def test_new_request_while_pending_keeps_first_timestamp(self):
        self.sync(bump(self.v1, 2, handoff=handoff_requested('patient_asked_human', last_at=T2), last_message_at=T2))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.needs_attention_at, self.first_request)  # pendiente desde el primero
        self.assertTrue(self.lead.attention_pending)
        self.assertIsNone(self.lead.acknowledged_at)

    def test_stale_and_duplicate_do_not_rearm(self):
        v2 = bump(self.v1, 2, handoff=handoff_requested('patient_asked_human', last_at=T2), last_message_at=T2)
        self.sync(v2)
        acked = self.acknowledge()
        self.assertEqual(self.sync(v2).json()['result'], 'duplicate')
        self.assertEqual(self.sync(self.v1).json()['result'], 'stale')
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.acknowledged_at, self.lead.acknowledged_by_id), acked)
        self.assertFalse(self.lead.attention_pending)

    def test_closed_lead_is_not_rearmed(self):
        self.acknowledge()
        response = self.client.patch(_detail_url(self.lead), {'status': 'closed', 'outcome': 'other'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        before = Lead.objects.filter(pk=self.lead.pk).values().get()
        self.sync(bump(self.v1, 2, handoff=handoff_requested('patient_asked_human', last_at=T3), last_message_at=T3))
        after = Lead.objects.filter(pk=self.lead.pk).values().get()
        self.assertEqual(after, before)  # ni estado, ni evidencia, ni reconocimiento
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.attention_pending)

    def test_sync_never_touches_human_crm_fields(self):
        assignee = self._member(self.biz, 'admin')
        customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550101')
        response = self.client.patch(
            _detail_url(self.lead), {'status': 'in_progress', 'assigned_to': assignee.pk, 'customer': str(customer.pk)},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.client.post(f'{_detail_url(self.lead)}notes/', {'body': 'Llamar'}, format='json')
        acked = self.acknowledge()

        self.sync(bump(self.v1, 2, handoff=handoff_requested('patient_asked_human', last_at=T2),
                       patient_name='Otro nombre', last_message_at=T2))
        self.lead.refresh_from_db()
        self.assertEqual(
            (self.lead.status, self.lead.assigned_to_id, self.lead.customer_id, self.lead.outcome),
            (Lead.Status.IN_PROGRESS, assignee.pk, customer.pk, None),
        )
        self.assertEqual((self.lead.acknowledged_at, self.lead.acknowledged_by_id), acked)
        self.assertEqual(LeadNote.objects.filter(lead=self.lead).count(), 1)
        self.assertEqual(LeadAgentState.objects.get(pk=self.lead.pk).patient_name, 'Otro nombre')
        self.assertTrue(self.lead.attention_pending)

    def test_first_handoff_on_existing_lead_after_create(self):
        # Lead creado sin handoff: la transición false → true sigue seteando la evidencia (04A).
        v1 = make_payload(
            agent_instance_id=self.v1['agent_instance_id'], business_id=self.biz.pk,
            phone_number_id=self.PHONE_NUMBER_ID,
        )
        created = signed_put(self.agent, v1, key_id=self.credential.key_id)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        lead = Lead.objects.get(pk=created.json()['mirubro_lead_id'])
        self.assertIsNone(lead.needs_attention_at)
        self.sync(bump(v1, 2, handoff=handoff_requested('lead_ready', first_at=T1), last_message_at=T2))
        lead.refresh_from_db()
        self.assertIsNotNone(lead.needs_attention_at)
        self.assertTrue(lead.attention_pending)
