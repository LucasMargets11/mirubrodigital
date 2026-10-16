"""Notificaciones operativas de Leads (LEADS 04B.3).

1. `agent_lead_handoff` por ciclo de atención: el pedido inicial avisa;
   reconocer no avisa; un pedido realmente nuevo tras el reconocimiento vuelve
   a avisar; duplicate/stale, updates mientras sigue pendiente y Leads cerrados
   no avisan.
2. `lead_assigned` personal (`recipient`) al nuevo asignado cuando un humano
   cambia `assigned_to`; nada al desasignar, repetir, auto-asignarse, cambiar
   otros campos ni al asignado anterior.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership
from apps.appointments.tests.test_customer_core_access import _login, _turnos_business
from apps.leads.models import Lead
from apps.leads.services import notifications as notifications_module
from apps.leads.services import receiver as receiver_module
from apps.notifications.business_notifications import create_business_notification
from apps.notifications.models import BusinessNotification

from .agent_client import T2, T3, bump, handoff_requested, make_payload, signed_put
from .factories import TEST_KEY, make_channel, make_credential, make_instance
from .test_crm_api import LIST_URL, LeadApiMixin, _detail_url

Kind = BusinessNotification.Kind
NOTIFICATIONS_URL = '/api/v1/notifications/business/'


def _ack_url(lead) -> str:
    return f'{LIST_URL}{lead.pk}/acknowledge-attention/'


# ── 1. Ciclos de atención ───────────────────────────────────────────────────

@override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class HandoffCycleNotificationTests(LeadApiMixin, APITestCase):

    PHONE_NUMBER_ID = '5550004443'

    def setUp(self):
        self.biz = _turnos_business(slug=f'hcyc-{uuid.uuid4().hex[:6]}')
        instance = make_instance(f'agent-{uuid.uuid4().hex[:8]}')
        self.credential = make_credential(instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        make_channel(instance, self.biz, phone_number_id=self.PHONE_NUMBER_ID)
        self.agent = APIClient()
        self.user = _login(self.client, self.biz, 'manager')
        self.v1 = make_payload(
            agent_instance_id=instance.external_id, business_id=self.biz.pk, phone_number_id=self.PHONE_NUMBER_ID,
            handoff=handoff_requested('patient_asked_human'),
        )
        response = self.sync(self.v1, expected=status.HTTP_201_CREATED)
        self.lead = Lead.objects.get(pk=response.json()['mirubro_lead_id'])

    def sync(self, payload, expected=status.HTTP_200_OK, result=None):
        with self.captureOnCommitCallbacks(execute=True):
            response = signed_put(self.agent, payload, key_id=self.credential.key_id)
        self.assertEqual(response.status_code, expected, response.content)
        if result is not None:
            self.assertEqual(response.json()['result'], result)
        return response

    def acknowledge(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(_ack_url(self.lead), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()

    def handoffs(self):
        return BusinessNotification.objects.filter(kind=Kind.AGENT_LEAD_HANDOFF).order_by('created_at')

    def new_request(self, version, last_at):
        # Mismo motivo repetido más tarde (`last_at` avanza) = pedido nuevo (04B.1).
        return bump(self.v1, version, handoff=handoff_requested('patient_asked_human', last_at=last_at),
                    last_message_at=last_at)

    def test_initial_request_notifies_once(self):
        [notification] = self.handoffs()
        self.lead.refresh_from_db()
        self.assertEqual(notification.business_id, self.biz.pk)
        self.assertEqual(notification.related_object_type, 'lead')
        self.assertEqual(notification.related_object_id, str(self.lead.pk))
        self.assertEqual(notification.dedupe_key, receiver_module.handoff_dedupe_key(self.lead))
        self.assertIsNone(notification.recipient_id)  # aviso del equipo

    def test_ack_then_new_request_notifies_again(self):
        self.acknowledge()
        self.assertEqual(self.handoffs().count(), 1)  # reconocer no avisa

        self.sync(self.new_request(2, T2), result='applied')
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.attention_pending)
        first, second = self.handoffs()
        self.assertNotEqual(first.dedupe_key, second.dedupe_key)
        self.assertEqual(second.dedupe_key, receiver_module.handoff_dedupe_key(self.lead))
        self.assertEqual(second.related_object_id, str(self.lead.pk))

        # Tercer ciclo: otro reconocimiento + motivo nuevo.
        self.acknowledge()
        self.sync(bump(self.v1, 3, handoff={
            **handoff_requested('patient_asked_human', last_at=T2),
            'reasons': [
                {'code': 'patient_asked_human', 'first_at': self.v1['handoff']['requested_at'], 'last_at': T2},
                {'code': 'urgency', 'first_at': T3, 'last_at': T3},
            ],
        }, last_message_at=T3), result='applied')
        self.assertEqual(self.handoffs().count(), 3)

    def test_duplicate_and_stale_do_not_notify(self):
        self.acknowledge()
        v2 = self.new_request(2, T2)
        self.sync(v2, result='applied')
        self.assertEqual(self.handoffs().count(), 2)
        self.sync(v2, result='duplicate')  # retry del mismo evento
        self.sync(self.v1, result='stale')
        self.assertEqual(self.handoffs().count(), 2)

    def test_retry_after_ack_does_not_resurrect_lost_notification(self):
        # El aviso se perdió y el humano ya reconoció por otro medio: el retry no avisa tarde.
        self.handoffs().delete()
        self.acknowledge()
        self.sync(self.v1, result='duplicate')
        self.assertFalse(self.handoffs().exists())

    def test_updates_while_pending_do_not_spam(self):
        self.sync(bump(self.v1, 2, summary='otro resumen', urgency=True), result='applied')
        self.sync(self.new_request(3, T2), result='applied')  # motivo repetido, sigue pendiente
        self.sync(bump(self.v1, 4, handoff={
            **handoff_requested('patient_asked_human', last_at=T2),
            'reasons': [
                {'code': 'patient_asked_human', 'first_at': self.v1['handoff']['requested_at'], 'last_at': T2},
                {'code': 'lead_ready', 'first_at': T3, 'last_at': T3},
            ],
        }, last_message_at=T3), result='applied')  # motivo nuevo, sigue pendiente
        self.assertEqual(self.handoffs().count(), 1)
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.attention_pending)

    def test_closed_lead_does_not_notify(self):
        self.acknowledge()
        response = self.client.patch(_detail_url(self.lead), {'status': 'closed', 'outcome': 'other'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.sync(self.new_request(2, T2), result='applied')
        self.sync(self.new_request(2, T2), result='duplicate')
        self.assertEqual(self.handoffs().count(), 1)

    def test_closed_while_pending_does_not_notify_new_reasons(self):
        Lead.objects.filter(pk=self.lead.pk).update(status='closed', outcome='other')
        self.handoffs().delete()
        self.sync(self.new_request(2, T2), result='applied')
        self.assertFalse(self.handoffs().exists())


# ── 2. Asignación ───────────────────────────────────────────────────────────

class LeadAssignedNotificationTests(LeadApiMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('asg')
        # Owner no consume asiento: owner + 2 managers entran en el plan Turnos.
        self.owner = _login(self.client, self.biz, 'owner')
        self.alice = self._member(self.biz)
        self.bob = self._member(self.biz)
        self.lead = self._lead(self.biz, self.channel)

    def patch(self, data, client=None):
        with self.captureOnCommitCallbacks(execute=True):
            response = (client or self.client).patch(_detail_url(self.lead), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def assigned(self, **filters):
        return BusinessNotification.objects.filter(kind=Kind.LEAD_ASSIGNED, **filters)

    def test_initial_assignment_notifies_assignee(self):
        self.patch({'assigned_to': self.alice.pk})
        [notification] = self.assigned()
        self.assertEqual(notification.recipient_id, self.alice.pk)
        self.assertEqual(notification.business_id, self.biz.pk)
        self.assertEqual(notification.related_object_type, 'lead')
        self.assertEqual(notification.related_object_id, str(self.lead.pk))
        self.assertEqual(notification.metadata['assigned_by'], self.owner.pk)

    def test_reassignment_notifies_only_new_assignee(self):
        self.patch({'assigned_to': self.alice.pk})
        self.patch({'assigned_to': self.bob.pk})
        self.assertEqual(self.assigned(recipient=self.alice).count(), 1)
        self.assertEqual(self.assigned(recipient=self.bob).count(), 1)
        # Volver a asignar a Alice es un evento nuevo.
        self.patch({'assigned_to': self.alice.pk})
        self.assertEqual(self.assigned(recipient=self.alice).count(), 2)
        self.assertEqual(self.assigned().count(), 3)

    def test_same_assignment_repeated_does_not_notify(self):
        self.patch({'assigned_to': self.alice.pk})
        self.patch({'assigned_to': self.alice.pk})
        self.patch({'assigned_to': self.alice.pk, 'status': 'in_progress'})
        self.assertEqual(self.assigned().count(), 1)

    def test_unassign_does_not_notify(self):
        self.patch({'assigned_to': self.alice.pk})
        self.patch({'assigned_to': None})
        self.assertEqual(self.assigned().count(), 1)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.assigned_to_id)

    def test_other_fields_do_not_notify(self):
        self.patch({'status': 'in_progress'})
        self.patch({'status': 'closed', 'outcome': 'other'})
        self.assertFalse(self.assigned().exists())

    def test_self_assignment_does_not_notify(self):
        manager = APIClient()
        manager.force_authenticate(user=self.alice)
        manager.cookies['bid'] = str(self.biz.pk)
        self.patch({'assigned_to': self.alice.pk}, client=manager)
        self.assertFalse(self.assigned().exists())

    def test_superseded_assignment_is_not_notified(self):
        # Post-commit tardío: si otra reasignación ya ganó, no se avisa a quien ya no es asignado.
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.patch(_detail_url(self.lead), {'assigned_to': self.alice.pk}, format='json')
        Lead.objects.filter(pk=self.lead.pk).update(assigned_to=self.bob)
        for callback in callbacks:
            callback()
        self.assertFalse(self.assigned().exists())

    def test_failed_notification_does_not_break_patch(self):
        with mock.patch.object(notifications_module, 'create_business_notification', side_effect=RuntimeError('db down')):
            with self.assertLogs('apps.notifications.business_notifications', level='ERROR'):
                self.patch({'assigned_to': self.alice.pk})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.alice.pk)

    # ── Visibilidad / tenant ──

    def _client_for(self, user, biz=None):
        client = APIClient()
        client.force_authenticate(user=user)
        client.cookies['bid'] = str((biz or self.biz).pk)
        return client

    def test_only_recipient_sees_personal_notification(self):
        self.patch({'assigned_to': self.alice.pk})
        notification = self.assigned().get()

        alice = self._client_for(self.alice)
        response = alice.get(NOTIFICATIONS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([row['id'] for row in response.data['results']], [str(notification.pk)])
        self.assertEqual(response.data['unread_count'], 1)
        self.assertNotIn('recipient', response.data['results'][0])

        # Ni otro manager ni el owner (que ve todos los kinds del equipo) ven el personal ajeno.
        for client in (self._client_for(self.bob), self.client):
            response = client.get(NOTIFICATIONS_URL)
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data['results'], [])
            self.assertEqual(response.data['unread_count'], 0)
            self.assertEqual(
                client.post(f'{NOTIFICATIONS_URL}{notification.pk}/read/').status_code, status.HTTP_404_NOT_FOUND,
            )
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

        response = alice.post(f'{NOTIFICATIONS_URL}{notification.pk}/read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNotNone(response.data['read_at'])

    def test_tenant_isolation(self):
        other_biz, other_channel = self._setup_tenant('asg-other')
        other_owner = _login(APIClient(), other_biz, 'owner')
        # El asignado también es miembro de otro negocio: allí no ve el aviso.
        Membership.objects.create(user=self.alice, business=other_biz, role='manager')
        self.patch({'assigned_to': self.alice.pk})
        self.assertEqual(self.assigned().get().business_id, self.biz.pk)

        response = self._client_for(self.alice, other_biz).get(NOTIFICATIONS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['results'], [])
        response = self._client_for(other_owner, other_biz).get(NOTIFICATIONS_URL)
        self.assertEqual(response.data['results'], [])

        # Un usuario de otro negocio no es asignable (400) → sin aviso.
        foreign = self._member(other_biz)
        response = self.client.patch(_detail_url(self.lead), {'assigned_to': foreign.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.assigned(recipient=foreign).exists())

    def test_team_notifications_unchanged(self):
        # Regresión: los avisos del equipo (recipient null) siguen visibles como antes.
        create_business_notification(
            business_id=self.biz.pk, kind=Kind.AGENT_LEAD_HANDOFF, dedupe_key='team-handoff', title='Handoff',
        )
        create_business_notification(
            business_id=self.biz.pk, kind=Kind.APPOINTMENT_CONFIRMED, dedupe_key='team-appt', title='Turno',
        )
        self.patch({'assigned_to': self.alice.pk})

        owner_kinds = sorted(row['kind'] for row in self.client.get(NOTIFICATIONS_URL).data['results'])
        self.assertEqual(owner_kinds, ['agent_lead_handoff', 'appointment_confirmed'])
        alice_kinds = sorted(
            row['kind'] for row in self._client_for(self.alice).get(NOTIFICATIONS_URL).data['results']
        )
        self.assertEqual(alice_kinds, ['agent_lead_handoff', 'lead_assigned'])
        bob_kinds = [row['kind'] for row in self._client_for(self.bob).get(NOTIFICATIONS_URL).data['results']]
        self.assertEqual(bob_kinds, ['agent_lead_handoff'])
