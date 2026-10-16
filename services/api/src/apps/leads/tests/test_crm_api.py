"""API humana de Leads (LEADS 04A): `/api/v1/leads/`.

Cubre RBAC (view_leads / manage_leads por rol), aislamiento entre tenants,
filtros/búsqueda/orden/paginación, contrato del detalle (sin internals del
sync), mutaciones CRM con transiciones y cierre, asignación, vínculo manual
con Customer, notas y la regresión de ownership con un `lead.sync` posterior.
"""
from __future__ import annotations

import datetime as dt
import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership
from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin, _gestion_business, _login, _turnos_business
from apps.customers.models import Customer
from apps.leads.models import Lead, LeadAgentState, LeadNote

from .agent_client import T2, bump, make_payload, signed_put
from .factories import TEST_KEY, make_channel, make_credential, make_instance, make_state

User = get_user_model()

LIST_URL = '/api/v1/leads/'


def _detail_url(lead) -> str:
    return f'{LIST_URL}{lead.pk}/'


def _notes_url(lead) -> str:
    return f'{LIST_URL}{lead.pk}/notes/'


def _note_url(lead, note) -> str:
    return f'{LIST_URL}{lead.pk}/notes/{note.pk}/'


class LeadApiMixin:
    def _setup_tenant(self, slug):
        biz = _turnos_business(slug=f'{slug}-{uuid.uuid4().hex[:6]}')
        instance = make_instance(f'agent-{uuid.uuid4().hex[:8]}')
        channel = make_channel(instance, biz, phone_number_id=str(uuid.uuid4().int)[:12])
        return biz, channel

    def _lead(self, biz, channel, *, created_at=None, **state):
        lead = Lead.objects.create(business=biz)
        make_state(lead, channel, **state)
        if created_at is not None:
            Lead.objects.filter(pk=lead.pk).update(created_at=created_at)
        return lead

    def _member(self, biz, role='manager', **user_fields):
        user = User.objects.create_user(username=f'{role}-{uuid.uuid4().hex[:8]}@example.com', password='x', **user_fields)
        Membership.objects.create(user=user, business=biz, role=role)
        return user

    def _ids(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [row['id'] for row in response.data['results']]


# ── RBAC ────────────────────────────────────────────────────────────────────

class LeadRbacTests(LeadApiMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('rbac')
        self.lead = self._lead(self.biz, self.channel)
        self.note = LeadNote.objects.create(lead=self.lead, body='Inicial')

    def test_unauthenticated(self):
        for response in (
            self.client.get(LIST_URL),
            self.client.get(_detail_url(self.lead)),
            self.client.patch(_detail_url(self.lead), {'status': 'in_progress'}, format='json'),
            self.client.post(_notes_url(self.lead), {'body': 'x'}, format='json'),
        ):
            self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_owner_admin_manager_read_and_manage(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                client = APIClient()
                _login(client, self.biz, role)
                self.assertEqual(client.get(LIST_URL).status_code, status.HTTP_200_OK)
                self.assertEqual(client.get(_detail_url(self.lead)).status_code, status.HTTP_200_OK)
                self.assertEqual(client.get(_notes_url(self.lead)).status_code, status.HTTP_200_OK)
                created = client.post(_notes_url(self.lead), {'body': f'nota {role}'}, format='json')
                self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
                patched = client.patch(_detail_url(self.lead), {'status': 'in_progress'}, format='json')
                self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)

    def test_viewer_has_no_lead_access(self):
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(_detail_url(self.lead)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(_notes_url(self.lead)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.patch(_detail_url(self.lead), {'status': 'in_progress'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(_notes_url(self.lead), {'body': 'x'}, format='json').status_code, status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(_note_url(self.lead, self.note), {'body': 'x'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(_note_url(self.lead, self.note)).status_code, status.HTTP_403_FORBIDDEN)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)
        self.assertTrue(LeadNote.objects.filter(pk=self.note.pk, body='Inicial').exists())

    def test_view_only_cannot_mutate(self):
        # Rol con view_leads pero sin manage_leads (no existe hoy en el registry): se simula el mapa de permisos.
        from unittest import mock

        from apps.accounts import permissions as perm_module

        real = perm_module.permissions_for_service

        def view_only(service, role, business=None):
            perms = dict(real(service, role, business))
            perms['manage_leads'] = False
            return perms

        _login(self.client, self.biz, 'manager')
        with mock.patch.object(perm_module, 'permissions_for_service', side_effect=view_only):
            self.assertEqual(self.client.get(_detail_url(self.lead)).status_code, status.HTTP_200_OK)
            self.assertEqual(
                self.client.patch(_detail_url(self.lead), {'status': 'in_progress'}, format='json').status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.client.post(_notes_url(self.lead), {'body': 'x'}, format='json').status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.client.patch(_note_url(self.lead, self.note), {'body': 'x'}, format='json').status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(self.client.delete(_note_url(self.lead, self.note)).status_code, status.HTTP_403_FORBIDDEN)

    def test_gestion_business_has_no_lead_permissions(self):
        biz = _gestion_business('starter', f'gestion-{uuid.uuid4().hex[:6]}')
        _login(self.client, biz, 'owner')
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_403_FORBIDDEN)


# ── Entitlement `appointments.leads` (LEADS 04A.1) ─────────────────────────

class LeadEntitlementGateTests(LeadApiMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('ent')
        self.lead = self._lead(self.biz, self.channel)
        self.note = LeadNote.objects.create(lead=self.lead, body='Inicial')

    def _all_requests(self, client):
        return {
            'list': client.get(LIST_URL),
            'detail': client.get(_detail_url(self.lead)),
            'notes': client.get(_notes_url(self.lead)),
            'patch': client.patch(_detail_url(self.lead), {'status': 'in_progress'}, format='json'),
            'note_create': client.post(_notes_url(self.lead), {'body': 'x'}, format='json'),
            'note_edit': client.patch(_note_url(self.lead, self.note), {'body': 'editada'}, format='json'),
        }

    def assertEntitlementDenied(self, response):
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['code'], 'plan_entitlement_required')
        self.assertEqual(response.data['entitlement'], 'appointments.leads')
        self.assertEqual(response.data['upgrade_hint'], 'Turnos Base')

    def test_entitlement_and_permission_allow(self):
        _login(self.client, self.biz, 'manager')
        for name, response in self._all_requests(self.client).items():
            with self.subTest(request=name):
                self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED), response.data)

    def test_plan_without_entitlement_is_denied_even_for_owner(self):
        from unittest import mock

        from apps.business import entitlements as ent_module

        _login(self.client, self.biz, 'owner')
        without_leads = {'appointments_base': {'appointments.customers'}}
        with mock.patch.dict(ent_module.PLAN_ENTITLEMENTS, without_leads):
            for name, response in self._all_requests(self.client).items():
                with self.subTest(request=name):
                    self.assertEntitlementDenied(response)
            # El resto de Turnos (Clientes core) sigue disponible: el gate es solo de Leads.
            self.assertEqual(self.client.get('/api/v1/customers/').status_code, status.HTTP_200_OK)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)
        self.assertEqual(LeadNote.objects.get(pk=self.note.pk).body, 'Inicial')

    def test_entitlement_with_insufficient_rbac(self):
        _login(self.client, self.biz, 'viewer')
        for name, response in self._all_requests(self.client).items():
            with self.subTest(request=name):
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertNotEqual(response.data.get('code'), 'plan_entitlement_required')
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_inactive_subscription_is_denied(self):
        from apps.billing.models import SubscriptionV2

        SubscriptionV2.objects.filter(business=self.biz).update(status=SubscriptionV2.Status.CANCELED)
        _login(self.client, self.biz, 'owner')
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'subscription_access_denied')

    def test_other_product_business_is_denied(self):
        for plan in ('starter', 'business', 'qr_reviews_base'):
            with self.subTest(plan=plan):
                biz = _gestion_business(plan, f'{plan}-{uuid.uuid4().hex[:6]}')
                client = APIClient()
                _login(client, biz, 'owner')
                response = client.get(LIST_URL)
                self.assertEntitlementDenied(response)

    def test_other_tenant_lead_still_404_with_entitlement(self):
        other_biz, other_channel = self._setup_tenant('ent-other')
        foreign = self._lead(other_biz, other_channel)
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.get(_detail_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(_detail_url(foreign), {'status': 'in_progress'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )


# ── Aislamiento entre tenants ─────────────────────────────────────────────────

class LeadTenantIsolationTests(LeadApiMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('mine')
        self.other_biz, self.other_channel = self._setup_tenant('other')
        self.lead = self._lead(self.biz, self.channel)
        self.foreign = self._lead(self.other_biz, self.other_channel)
        self.foreign_note = LeadNote.objects.create(lead=self.foreign, body='Ajena')
        self.user = _login(self.client, self.biz, 'owner')

    def test_list_only_current_business(self):
        self.assertEqual(self._ids(self.client.get(LIST_URL)), [str(self.lead.pk)])

    def test_business_id_param_is_ignored(self):
        response = self.client.get(LIST_URL, {'business_id': self.other_biz.pk, 'business': self.other_biz.pk})
        self.assertEqual(self._ids(response), [str(self.lead.pk)])

    def test_foreign_lead_is_404(self):
        self.assertEqual(self.client.get(_detail_url(self.foreign)).status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.patch(_detail_url(self.foreign), {'status': 'in_progress'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.status, Lead.Status.NEW)

    def test_foreign_notes_are_404(self):
        self.assertEqual(self.client.get(_notes_url(self.foreign)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.post(_notes_url(self.foreign), {'body': 'x'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        # Nota ajena colgada de MI lead en la URL: tampoco aparece.
        for url in (_note_url(self.foreign, self.foreign_note), f'{_notes_url(self.lead)}{self.foreign_note.pk}/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.patch(url, {'body': 'x'}, format='json').status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.foreign_note.refresh_from_db()
        self.assertEqual(self.foreign_note.body, 'Ajena')

    def test_foreign_customer_not_linkable(self):
        foreign_customer = Customer.objects.create(business=self.other_biz, name='Ajeno', phone='1155550000')
        response = self.client.patch(_detail_url(self.lead), {'customer': str(foreign_customer.pk)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('customer', response.data)
        missing = self.client.patch(_detail_url(self.lead), {'customer': str(uuid.uuid4())}, format='json')
        self.assertEqual(missing.data, response.data)  # sin oráculo
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.customer_id)

    def test_foreign_user_not_assignable(self):
        outsider = self._member(self.other_biz, 'owner')
        response = self.client.patch(_detail_url(self.lead), {'assigned_to': outsider.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('assigned_to', response.data)
        missing = self.client.patch(_detail_url(self.lead), {'assigned_to': 999999999}, format='json')
        self.assertEqual(missing.data, response.data)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.assigned_to_id)


# ── Listado: filtros, búsqueda, orden, paginación ────────────────────────────

class LeadListTests(LeadApiMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('list')
        self.user = _login(self.client, self.biz, 'owner')

    def test_list_contract_has_no_internals(self):
        lead = self._lead(self.biz, self.channel, patient_name='Ana', reason='Dolor')
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'count', 'next', 'previous', 'results'})
        row = response.data['results'][0]
        self.assertEqual(row['id'], str(lead.pk))
        self.assertEqual(set(row), {
            'id', 'source', 'status', 'outcome', 'created_at', 'updated_at', 'needs_attention_at',
            'needs_attention', 'acknowledged_at', 'assigned_to', 'customer', 'agent', 'conversation_state',
        })
        self.assertEqual(set(row['agent']), {
            'patient_name', 'whatsapp_profile_name', 'phone_e164', 'reason', 'preferred_time', 'urgency',
            'agent_status', 'handoff_requested', 'handoff_reasons', 'summary', 'last_message_at',
        })
        body = str(response.data)
        for forbidden in ('payload_hash', 'last_event_id', 'encrypted_secret', 'phone_number_id', 'a' * 64):
            self.assertNotIn(forbidden, body)

    def test_filters(self):
        assignee = self._member(self.biz, 'manager', first_name='Mara')
        customer = Customer.objects.create(business=self.biz, name='Cliente X', phone='1155550101')
        urgent = self._lead(self.biz, self.channel, urgency=True)
        handoff = self._lead(
            self.biz, self.channel, handoff_requested=True, handoff_requested_at=timezone.now(),
            handoff_reasons=[{'code': 'human_requested'}],
        )
        Lead.objects.filter(pk=handoff.pk).update(needs_attention_at=timezone.now())
        assigned = self._lead(self.biz, self.channel)
        Lead.objects.filter(pk=assigned.pk).update(assigned_to=assignee, status=Lead.Status.IN_PROGRESS)
        linked = self._lead(self.biz, self.channel)
        Lead.objects.filter(pk=linked.pk).update(customer=customer)
        closed = self._lead(self.biz, self.channel)
        Lead.objects.filter(pk=closed.pk).update(status=Lead.Status.CLOSED, outcome=Lead.Outcome.SPAM)
        everyone = {str(lead.pk) for lead in (urgent, handoff, assigned, linked, closed)}

        def ids(**params):
            return set(self._ids(self.client.get(LIST_URL, params)))

        self.assertEqual(ids(status='in_progress'), {str(assigned.pk)})
        self.assertEqual(ids(status='closed'), {str(closed.pk)})
        self.assertEqual(ids(status='new'), everyone - {str(assigned.pk), str(closed.pk)})
        self.assertEqual(ids(urgency='true'), {str(urgent.pk)})
        self.assertEqual(ids(urgency='false'), everyone - {str(urgent.pk)})
        self.assertEqual(ids(handoff='true'), {str(handoff.pk)})
        self.assertEqual(ids(handoff='false'), everyone - {str(handoff.pk)})
        self.assertEqual(ids(needs_attention='true'), {str(handoff.pk)})
        self.assertEqual(ids(needs_attention='false'), everyone - {str(handoff.pk)})
        self.assertEqual(ids(assigned_to=assignee.pk), {str(assigned.pk)})
        self.assertEqual(ids(assigned_to='unassigned'), everyone - {str(assigned.pk)})
        self.assertEqual(ids(customer=str(customer.pk)), {str(linked.pk)})
        self.assertEqual(ids(customer='unlinked'), everyone - {str(linked.pk)})
        self.assertEqual(ids(source='whatsapp_agent'), everyone)
        self.assertEqual(ids(outcome='spam'), {str(closed.pk)})
        self.assertEqual(ids(outcome='booked'), set())

    def test_invalid_filter_values_are_400(self):
        for params in (
            {'status': 'open'}, {'urgency': 'yes'}, {'handoff': '1'}, {'assigned_to': 'me'},
            {'customer': 'nope'}, {'source': 'web'}, {'outcome': 'won'}, {'needs_attention': 'x'},
            {'ordering': 'payload_hash'}, {'ordering': 'agent_state__last_event_id'},
        ):
            with self.subTest(params=params):
                response = self.client.get(LIST_URL, params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn(next(iter(params)), response.data)

    def test_search(self):
        ana = self._lead(self.biz, self.channel, patient_name='Ana Pérez', phone_e164='+5491112345678')
        bruno = self._lead(
            self.biz, self.channel, patient_name=None, whatsapp_profile_name='Brunito', phone_e164='+5491187654321',
            reason='Ortodoncia invisible', summary='Quiere presupuesto',
        )
        customer = Customer.objects.create(business=self.biz, name='Carla Gómez', phone='11 4444-5555')
        linked = self._lead(self.biz, self.channel, patient_name='Desconocida', phone_e164='+5491100000000')
        Lead.objects.filter(pk=linked.pk).update(customer=customer)

        def ids(q):
            return self._ids(self.client.get(LIST_URL, {'q': q}))

        self.assertEqual(ids('ana pé'), [str(ana.pk)])
        self.assertEqual(ids('bruni'), [str(bruno.pk)])
        self.assertEqual(ids('+54911123'), [str(ana.pk)])
        self.assertEqual(ids('11 1234-5678'), [str(ana.pk)])
        self.assertEqual(ids('ortodon'), [str(bruno.pk)])
        self.assertEqual(ids('PRESUPUESTO'), [str(bruno.pk)])
        self.assertEqual(ids('carla'), [str(linked.pk)])
        self.assertEqual(ids('4444-5555'), [str(linked.pk)])
        self.assertEqual(ids('zzz-no-match'), [])

    def test_default_priority_ordering(self):
        now = timezone.now()
        old_plain = self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(hours=5))
        recent_plain = self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(minutes=5))
        urgent = self._lead(self.biz, self.channel, urgency=True, last_message_at=now - dt.timedelta(hours=10))
        attention = self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(days=2))
        Lead.objects.filter(pk=attention.pk).update(needs_attention_at=now - dt.timedelta(days=2))
        # Cerrado que pidió atención: el timestamp queda como historia, no lo sube.
        closed_attention = self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(days=3))
        Lead.objects.filter(pk=closed_attention.pk).update(
            needs_attention_at=now, status=Lead.Status.CLOSED, outcome=Lead.Outcome.OTHER,
        )
        expected = [attention, urgent, recent_plain, old_plain, closed_attention]
        self.assertEqual(self._ids(self.client.get(LIST_URL)), [str(lead.pk) for lead in expected])
        self.assertEqual(
            self._ids(self.client.get(LIST_URL, {'ordering': 'priority'})), [str(lead.pk) for lead in expected],
        )

    def _attention(self, lead, at):
        Lead.objects.filter(pk=lead.pk).update(needs_attention_at=at)
        return lead

    def _close(self, lead):
        Lead.objects.filter(pk=lead.pk).update(status=Lead.Status.CLOSED, outcome=Lead.Outcome.OTHER)
        return lead

    def _default_order(self):
        return self._ids(self.client.get(LIST_URL))

    def test_priority_closed_urgent_after_open_with_attention(self):
        now = timezone.now()
        closed_urgent = self._close(self._lead(self.biz, self.channel, urgency=True, last_message_at=now))
        attention = self._attention(
            self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(days=5)), now - dt.timedelta(days=5),
        )
        self.assertEqual(self._default_order(), [str(attention.pk), str(closed_urgent.pk)])

    def test_priority_recent_closed_after_open_pending(self):
        now = timezone.now()
        closed_recent = self._close(self._lead(self.biz, self.channel, last_message_at=now))
        Lead.objects.filter(pk=closed_recent.pk).update(created_at=now)
        open_old = self._lead(
            self.biz, self.channel, created_at=now - dt.timedelta(days=10), last_message_at=now - dt.timedelta(days=10),
        )
        self.assertEqual(self._default_order(), [str(open_old.pk), str(closed_recent.pk)])

    def test_priority_pending_attention_urgent_first(self):
        now = timezone.now()
        plain_recent = self._attention(self._lead(self.biz, self.channel, last_message_at=now), now)
        urgent_old = self._attention(
            self._lead(self.biz, self.channel, urgency=True, last_message_at=now - dt.timedelta(days=1)), now,
        )
        urgent_recent = self._attention(
            self._lead(self.biz, self.channel, urgency=True, last_message_at=now - dt.timedelta(hours=1)), now,
        )
        plain_old = self._attention(
            self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(days=2)), now,
        )
        # Un abierto urgente sin atención pendiente nunca supera a uno con atención.
        urgent_no_attention = self._lead(self.biz, self.channel, urgency=True, last_message_at=now)
        self.assertEqual(
            self._default_order(),
            [str(lead.pk) for lead in (urgent_recent, urgent_old, plain_recent, plain_old, urgent_no_attention)],
        )

    def test_priority_open_without_attention(self):
        now = timezone.now()
        acknowledged = self._attention(self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(hours=3)), now)
        # Reconocido después del pedido: deja de estar pendiente, sigue siendo un abierto más.
        Lead.objects.filter(pk=acknowledged.pk).update(acknowledged_at=now + dt.timedelta(minutes=1))
        in_progress = self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(hours=1))
        Lead.objects.filter(pk=in_progress.pk).update(status=Lead.Status.IN_PROGRESS)
        new_old = self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(hours=5))
        urgent = self._lead(self.biz, self.channel, urgency=True, last_message_at=now - dt.timedelta(days=1))
        self.assertEqual(
            self._default_order(), [str(lead.pk) for lead in (urgent, in_progress, acknowledged, new_old)],
        )

    def test_priority_closed_always_last(self):
        now = timezone.now()
        closed_attention_urgent = self._close(self._attention(
            self._lead(self.biz, self.channel, urgency=True, last_message_at=now), now,
        ))
        closed_recent = self._close(self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(minutes=1)))
        closed_old = self._close(self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(days=3)))
        open_old = self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(days=30))
        attention = self._attention(self._lead(self.biz, self.channel, last_message_at=now - dt.timedelta(days=20)), now)
        # Entre cerrados la urgencia no cuenta: solo último mensaje y creación.
        self.assertEqual(
            self._default_order(),
            [str(lead.pk) for lead in (attention, open_old, closed_attention_urgent, closed_recent, closed_old)],
        )

    def test_priority_tiebreak_last_message_then_created(self):
        now = timezone.now()
        same_message = now - dt.timedelta(hours=2)
        older_created = self._lead(
            self.biz, self.channel, created_at=now - dt.timedelta(days=2), last_message_at=same_message,
        )
        newer_created = self._lead(
            self.biz, self.channel, created_at=now - dt.timedelta(days=1), last_message_at=same_message,
        )
        latest_message = self._lead(
            self.biz, self.channel, created_at=now - dt.timedelta(days=9), last_message_at=now,
        )
        closed_a = self._close(self._lead(
            self.biz, self.channel, created_at=now - dt.timedelta(days=4), last_message_at=same_message,
        ))
        closed_b = self._close(self._lead(
            self.biz, self.channel, created_at=now - dt.timedelta(days=3), last_message_at=same_message,
        ))
        self.assertEqual(
            self._default_order(),
            [str(lead.pk) for lead in (latest_message, newer_created, older_created, closed_b, closed_a)],
        )

    def test_explicit_orderings(self):
        now = timezone.now()
        a = self._lead(self.biz, self.channel, created_at=now - dt.timedelta(days=3), last_message_at=now - dt.timedelta(hours=1))
        b = self._lead(self.biz, self.channel, created_at=now - dt.timedelta(days=2), last_message_at=now - dt.timedelta(hours=3))
        c = self._lead(self.biz, self.channel, created_at=now - dt.timedelta(days=1), last_message_at=now - dt.timedelta(hours=2))
        ids = lambda ordering: self._ids(self.client.get(LIST_URL, {'ordering': ordering}))  # noqa: E731
        self.assertEqual(ids('created_at'), [str(a.pk), str(b.pk), str(c.pk)])
        self.assertEqual(ids('-created_at'), [str(c.pk), str(b.pk), str(a.pk)])
        self.assertEqual(ids('last_message_at'), [str(b.pk), str(c.pk), str(a.pk)])
        self.assertEqual(ids('-last_message_at'), [str(a.pk), str(c.pk), str(b.pk)])

    def test_pagination(self):
        for _ in range(30):
            self._lead(self.biz, self.channel)
        first = self.client.get(LIST_URL)
        self.assertEqual(first.data['count'], 30)
        self.assertEqual(len(first.data['results']), 25)
        self.assertIsNotNone(first.data['next'])
        page = self.client.get(LIST_URL, {'limit': 10, 'offset': 25})
        self.assertEqual(len(page.data['results']), 5)
        capped = self.client.get(LIST_URL, {'limit': 1000})
        self.assertEqual(len(capped.data['results']), 30)  # max_limit 100

    def test_list_query_count_is_constant(self):
        assignee = self._member(self.biz, 'manager')
        customer = Customer.objects.create(business=self.biz, name='C', phone='1')

        def make_batch(n):
            for _ in range(n):
                lead = self._lead(self.biz, self.channel)
                Lead.objects.filter(pk=lead.pk).update(assigned_to=assignee, customer=customer)
                LeadNote.objects.create(lead=lead, body='n')

        make_batch(2)
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_200_OK)
        make_batch(8)
        with CaptureQueriesContext(connection) as large:
            self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(len(small), len(large))


# ── Detalle ─────────────────────────────────────────────────────────────────

class LeadDetailTests(LeadApiMixin, TurnosAgendaMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('detail')
        self.user = _login(self.client, self.biz, 'owner')

    def test_detail_contract(self):
        now = timezone.now()
        lead = self._lead(
            self.biz, self.channel, patient_name='Ana', reason='Dolor', handoff_requested=True,
            handoff_requested_at=now, handoff_reasons=[{'code': 'human_requested'}],
        )
        customer = Customer.objects.create(business=self.biz, name='Ana Cliente', phone='1155550101')
        service, pro = self._agenda(self.biz)
        appointment = self._appt(self.biz, service, customer, now + dt.timedelta(days=1), pro=pro)
        closer = self._member(self.biz, 'manager', first_name='Mara', last_name='Paz')
        Lead.objects.filter(pk=lead.pk).update(
            customer=customer, appointment=appointment, status=Lead.Status.CLOSED, outcome=Lead.Outcome.BOOKED,
            closed_at=now, closed_by=closer, assigned_to=closer, needs_attention_at=now,
        )
        old = LeadNote.objects.create(lead=lead, body='Vieja', author=self.user)
        LeadNote.objects.filter(pk=old.pk).update(created_at=now - dt.timedelta(days=1))
        new = LeadNote.objects.create(lead=lead, body='Nueva', author=closer)

        response = self.client.get(_detail_url(lead))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        data = response.data
        self.assertEqual(set(data), {
            'id', 'source', 'status', 'outcome', 'assigned_to', 'customer', 'appointment', 'needs_attention_at',
            'needs_attention', 'acknowledged_at', 'acknowledged_by',
            'closed_at', 'closed_by', 'created_at', 'updated_at', 'agent_state', 'notes', 'activity',
            'conversation_control',
        })
        self.assertEqual(data['activity'], [])  # LEADS 04B.4: cambios por `.update()` no son actividad humana
        self.assertEqual(data['status'], 'closed')
        self.assertEqual(data['outcome'], 'booked')
        self.assertEqual(data['assigned_to'], {'id': closer.pk, 'display_name': 'Mara Paz'})
        self.assertEqual(data['closed_by'], {'id': closer.pk, 'display_name': 'Mara Paz'})
        self.assertEqual(data['customer'], {'id': str(customer.pk), 'display_name': 'Ana Cliente'})
        self.assertEqual(data['appointment']['id'], str(appointment.pk))
        self.assertEqual(set(data['appointment']), {'id', 'start_at', 'end_at', 'status', 'service_name'})
        self.assertEqual(set(data['agent_state']), {
            'agent_instance_id', 'external_lead_id', 'external_conversation_id', 'previous_external_lead_id',
            'channel', 'phone_e164', 'patient_name', 'whatsapp_profile_name', 'reason', 'preferred_time', 'urgency',
            'agent_status', 'handoff_requested', 'handoff_requested_at', 'handoff_reasons', 'summary',
            'opened_at', 'closed_at', 'close_reason', 'last_message_at', 'applied_version', 'last_synced_at',
        })
        self.assertEqual(data['agent_state']['agent_instance_id'], self.channel.agent_instance.external_id)
        self.assertEqual(data['agent_state']['channel'], 'whatsapp_cloud')
        self.assertEqual(data['agent_state']['patient_name'], 'Ana')
        self.assertEqual([note['id'] for note in data['notes']], [str(new.pk), str(old.pk)])
        self.assertEqual(set(data['notes'][0]), {'id', 'body', 'author', 'created_at', 'updated_at'})
        body = str(data)
        for forbidden in (
            'payload_hash', 'last_event_id', 'encrypted_secret', 'credential', 'phone_number_id',
            self.channel.phone_number_id, str(self.channel.agent_instance_id), 'a' * 64, '@example.com',
        ):
            self.assertNotIn(forbidden, body)

    def test_detail_query_count_bounded(self):
        lead = self._lead(self.biz, self.channel)
        author = lambda: User.objects.create_user(username=f'a-{uuid.uuid4().hex[:8]}', password='x')  # noqa: E731
        for i in range(5):
            LeadNote.objects.create(lead=lead, body=f'n{i}', author=author())
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(_detail_url(lead)).status_code, status.HTTP_200_OK)
        LeadNote.objects.create(lead=lead, body='otra', author=author())
        with CaptureQueriesContext(connection) as ctx2:
            self.client.get(_detail_url(lead))
        self.assertEqual(len(ctx), len(ctx2))


# ── Mutaciones CRM ──────────────────────────────────────────────────────────

class LeadMutationTests(LeadApiMixin, TurnosAgendaMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('mut')
        self.user = _login(self.client, self.biz, 'manager')
        self.lead = self._lead(self.biz, self.channel)

    def patch(self, data, lead=None):
        return self.client.patch(_detail_url(lead or self.lead), data, format='json')

    def test_new_to_in_progress(self):
        response = self.patch({'status': 'in_progress'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'in_progress')
        self.assertIn('agent_state', response.data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.IN_PROGRESS)
        self.assertIsNone(self.lead.closed_at)

    def test_new_to_closed_with_outcome_sets_closed_fields(self):
        before = timezone.now()
        response = self.patch({'status': 'closed', 'outcome': 'not_interested'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.CLOSED)
        self.assertEqual(self.lead.outcome, Lead.Outcome.NOT_INTERESTED)
        self.assertGreaterEqual(self.lead.closed_at, before)
        self.assertEqual(self.lead.closed_by_id, self.user.pk)
        self.assertEqual(response.data['closed_by']['id'], self.user.pk)

    def test_in_progress_to_closed(self):
        self.patch({'status': 'in_progress'})
        response = self.patch({'status': 'closed', 'outcome': 'unreachable'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.status, self.lead.outcome), ('closed', 'unreachable'))
        self.assertIsNotNone(self.lead.closed_at)

    def test_close_without_outcome_rejected(self):
        for payload in ({'status': 'closed'}, {'status': 'closed', 'outcome': None}):
            with self.subTest(payload=payload):
                response = self.patch(payload)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('outcome', response.data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_outcome_on_open_lead_rejected(self):
        for payload in ({'outcome': 'booked'}, {'status': 'in_progress', 'outcome': 'booked'}):
            with self.subTest(payload=payload):
                response = self.patch(payload)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('outcome', response.data)
        self.assertEqual(self.patch({'outcome': None}).status_code, status.HTTP_200_OK)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.outcome)

    def test_invalid_choices_rejected(self):
        self.assertEqual(self.patch({'status': 'won'}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.patch({'status': 'closed', 'outcome': 'won'}).status_code, status.HTTP_400_BAD_REQUEST)

    def test_in_progress_back_to_new_rejected(self):
        self.patch({'status': 'in_progress'})
        response = self.patch({'status': 'new'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', response.data)

    def test_closed_cannot_reopen(self):
        self.patch({'status': 'closed', 'outcome': 'spam'})
        for target in ('new', 'in_progress'):
            with self.subTest(target=target):
                response = self.patch({'status': target, 'outcome': None})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('status', response.data)
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.status, self.lead.outcome), ('closed', 'spam'))

    def test_closing_twice_keeps_first_close_stamp(self):
        self.patch({'status': 'closed', 'outcome': 'spam'})
        self.lead.refresh_from_db()
        first_closed_at, first_closer = self.lead.closed_at, self.lead.closed_by_id
        other = APIClient()
        _login(other, self.biz, 'admin')
        response = other.patch(_detail_url(self.lead), {'status': 'closed', 'outcome': 'duplicate'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.closed_at, first_closed_at)
        self.assertEqual(self.lead.closed_by_id, first_closer)
        self.assertEqual(self.lead.outcome, Lead.Outcome.DUPLICATE)

    def test_closed_lead_outcome_change_and_cannot_clear(self):
        self.patch({'status': 'closed', 'outcome': 'spam'})
        self.assertEqual(self.patch({'outcome': 'other'}).status_code, status.HTTP_200_OK)
        response = self.patch({'outcome': None})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.outcome, Lead.Outcome.OTHER)

    def test_server_owned_and_agent_fields_rejected_explicitly(self):
        forbidden = {
            'source': 'whatsapp_agent', 'needs_attention_at': None, 'closed_at': timezone.now().isoformat(),
            'closed_by': self.user.pk, 'acknowledged_at': timezone.now().isoformat(),
            'acknowledged_by': self.user.pk, 'needs_attention': False, 'business': 1, 'business_id': 1, 'id': str(uuid.uuid4()),
            'patient_name': 'Hack', 'phone_e164': '+5491100000000', 'urgency': True, 'agent_status': 'closed',
            'handoff_requested': True, 'summary': 'x', 'applied_version': 99, 'payload_hash': 'b' * 64,
            'agent_state': {'patient_name': 'Hack'}, 'agent': {'urgency': True}, 'created_at': None,
        }
        state_before = LeadAgentState.objects.filter(pk=self.lead.pk).values().get()
        for field, value in forbidden.items():
            with self.subTest(field=field):
                response = self.patch({'status': 'in_progress', field: value})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertEqual(response.data[field], ['Campo no editable.'])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)
        self.assertEqual(LeadAgentState.objects.filter(pk=self.lead.pk).values().get(), state_before)

    def test_needs_attention_preserved_on_human_changes(self):
        stamp = timezone.now() - dt.timedelta(hours=1)
        Lead.objects.filter(pk=self.lead.pk).update(needs_attention_at=stamp)
        assignee = self._member(self.biz, 'manager')
        self.patch({'status': 'in_progress', 'assigned_to': assignee.pk})
        self.patch({'status': 'closed', 'outcome': 'other'})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.needs_attention_at, stamp)

    # ── Asignación ──

    def test_assign_and_unassign(self):
        assignee = self._member(self.biz, 'admin', first_name='Lu', last_name='Gómez')
        response = self.patch({'assigned_to': assignee.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['assigned_to'], {'id': assignee.pk, 'display_name': 'Lu Gómez'})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, assignee.pk)
        self.assertEqual(self.lead.status, Lead.Status.NEW)  # asignar no cambia el estado
        response = self.patch({'assigned_to': None})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['assigned_to'])
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.assigned_to_id)

    def test_assign_rejects_inactive_or_roleless_members(self):
        # Plan con 2 asientos: un solo miembro extra que va cambiando de situación.
        member = self._member(self.biz, 'manager')
        membership = Membership.objects.get(user=member, business=self.biz)
        cases = {
            'inactive_membership': lambda: Membership.objects.filter(pk=membership.pk).update(status=Membership.Status.INACTIVE),
            'disabled_user': lambda: User.objects.filter(pk=member.pk).update(is_active=False),
            'viewer_role': lambda: Membership.objects.filter(pk=membership.pk).update(role='viewer'),
        }
        for name, apply in cases.items():
            with self.subTest(case=name):
                Membership.objects.filter(pk=membership.pk).update(status=Membership.Status.ACTIVE, role='manager')
                User.objects.filter(pk=member.pk).update(is_active=True)
                apply()
                response = self.patch({'assigned_to': member.pk})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('assigned_to', response.data)
        self.assertEqual(self.patch({'assigned_to': 'abc'}).status_code, status.HTTP_400_BAD_REQUEST)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.assigned_to_id)

    def test_keeping_current_assignee_is_valid_after_they_lose_access(self):
        assignee = self._member(self.biz, 'manager')
        self.patch({'assigned_to': assignee.pk})
        Membership.objects.filter(user=assignee).update(status=Membership.Status.INACTIVE)
        response = self.patch({'assigned_to': assignee.pk, 'status': 'in_progress'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    # ── Customer ──

    def test_link_and_unlink_customer_without_touching_it(self):
        customer = Customer.objects.create(business=self.biz, name='Ana Cliente', phone='1155550101')
        state = LeadAgentState.objects.get(pk=self.lead.pk)
        customers_before = Customer.objects.count()
        response = self.patch({'customer': str(customer.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['customer'], {'id': str(customer.pk), 'display_name': 'Ana Cliente'})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.customer_id, customer.pk)
        self.assertIsNone(self.lead.outcome)
        customer.refresh_from_db()
        self.assertEqual((customer.name, customer.phone), ('Ana Cliente', '1155550101'))
        self.assertNotEqual(customer.phone, state.phone_e164)
        self.assertEqual(Customer.objects.count(), customers_before)

        response = self.patch({'customer': None})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['customer'])
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.customer_id)
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())

    def test_inactive_customer_not_linkable(self):
        customer = Customer.objects.create(business=self.biz, name='Baja', phone='1', is_active=False)
        response = self.patch({'customer': str(customer.pk)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('customer', response.data)

    def test_no_customer_or_appointment_created(self):
        customers, appointments = Customer.objects.count(), self._appointment_count()
        self.patch({'status': 'closed', 'outcome': 'booked'})
        self.assertEqual(Customer.objects.count(), customers)
        self.assertEqual(self._appointment_count(), appointments)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.customer_id)
        self.assertIsNone(self.lead.appointment_id)

    def _appointment_count(self):
        from apps.appointments.models import Appointment

        return Appointment.objects.count()

    def test_put_and_delete_not_allowed(self):
        self.assertEqual(
            self.client.put(_detail_url(self.lead), {'status': 'in_progress'}, format='json').status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(self.client.delete(_detail_url(self.lead)).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Lead.objects.filter(pk=self.lead.pk).exists())
        self.assertEqual(self.client.post(LIST_URL, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# ── Notas ───────────────────────────────────────────────────────────────────

class LeadNotesTests(LeadApiMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('notes')
        self.user = _login(self.client, self.biz, 'manager')
        self.user.first_name, self.user.last_name = 'Lucía', 'Pérez'
        self.user.save()
        self.lead = self._lead(self.biz, self.channel)

    def test_create_author_from_request(self):
        other = self._member(self.biz, 'owner')
        response = self.client.post(
            _notes_url(self.lead), {'body': '  Llamar mañana.  ', 'author': other.pk, 'author_id': other.pk},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(set(response.data), {'id', 'body', 'author', 'created_at', 'updated_at'})
        self.assertEqual(response.data['body'], 'Llamar mañana.')
        self.assertEqual(response.data['author'], {'id': str(self.user.pk), 'name': 'Lucía Pérez'})
        note = LeadNote.objects.get(pk=response.data['id'])
        self.assertEqual((note.author_id, note.business_id, note.lead_id), (self.user.pk, self.biz.pk, self.lead.pk))

    def test_empty_and_too_long_body_rejected(self):
        for body in ('', '   '):
            with self.subTest(body=body):
                response = self.client.post(_notes_url(self.lead), {'body': body}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('body', response.data)
        self.assertEqual(
            self.client.post(_notes_url(self.lead), {}, format='json').status_code, status.HTTP_400_BAD_REQUEST,
        )
        too_long = self.client.post(_notes_url(self.lead), {'body': 'x' * (LeadNote.BODY_MAX_LENGTH + 1)}, format='json')
        self.assertEqual(too_long.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(LeadNote.objects.exists())

    def test_list_most_recent_first_paginated(self):
        now = timezone.now()
        old = LeadNote.objects.create(lead=self.lead, body='Vieja')
        LeadNote.objects.filter(pk=old.pk).update(created_at=now - dt.timedelta(days=1))
        new = LeadNote.objects.create(lead=self.lead, body='Nueva')
        response = self.client.get(_notes_url(self.lead))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data['results']], [str(new.pk), str(old.pk)])

    def test_edit_and_delete(self):
        note = LeadNote.objects.create(lead=self.lead, body='Original', author=self.user)
        response = self.client.patch(_note_url(self.lead, note), {'body': 'Editada', 'author': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        note.refresh_from_db()
        self.assertEqual((note.body, note.author_id), ('Editada', self.user.pk))
        blank = self.client.patch(_note_url(self.lead, note), {'body': ''}, format='json')
        self.assertEqual(blank.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.put(_note_url(self.lead, note), {'body': 'x'}, format='json').status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(_note_url(self.lead, note)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(LeadNote.objects.filter(pk=note.pk).exists())

    def test_note_of_another_lead_same_business_is_404(self):
        other_lead = self._lead(self.biz, self.channel)
        note = LeadNote.objects.create(lead=other_lead, body='De otro lead')
        url = f'{_notes_url(self.lead)}{note.pk}/'
        self.assertEqual(self.client.patch(url, {'body': 'x'}, format='json').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)


# ── Regresión: ownership CRM vs sync del agente ──────────────────────────────

@override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class LeadCrmSurvivesAgentSyncTests(LeadApiMixin, APITestCase):

    PHONE_NUMBER_ID = '5550001112'

    def test_human_crm_survives_new_agent_version(self):
        biz = _turnos_business(slug=f'regr-{uuid.uuid4().hex[:6]}')
        instance = make_instance(f'agent-{uuid.uuid4().hex[:8]}')
        credential = make_credential(instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        make_channel(instance, biz, phone_number_id=self.PHONE_NUMBER_ID)
        agent_client = APIClient()

        # 1. El agente crea el Lead.
        payload = make_payload(
            agent_instance_id=instance.external_id, business_id=biz.pk, phone_number_id=self.PHONE_NUMBER_ID,
        )
        created = signed_put(agent_client, payload, key_id=credential.key_id)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        lead = Lead.objects.get(pk=created.json()['mirubro_lead_id'])

        # 2. Un humano lo gestiona por la API humana.
        _login(self.client, biz, 'owner')
        assignee = self._member(biz, 'manager')
        customer = Customer.objects.create(business=biz, name='Ana Cliente', phone='1155550101')
        response = self.client.patch(
            _detail_url(lead), {'status': 'in_progress', 'assigned_to': assignee.pk, 'customer': str(customer.pk)},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        note = self.client.post(_notes_url(lead), {'body': 'Llamar a la tarde'}, format='json')
        self.assertEqual(note.status_code, status.HTTP_201_CREATED)

        # 3. Llega una nueva versión del agente.
        update = bump(payload, 2, patient_name='Ana María Pérez', reason='Control anual', last_message_at=T2)
        synced = signed_put(agent_client, update, key_id=credential.key_id)
        self.assertEqual(synced.status_code, status.HTTP_200_OK, synced.content)
        self.assertEqual(synced.json()['result'], 'applied')

        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.IN_PROGRESS)
        self.assertEqual(lead.assigned_to_id, assignee.pk)
        self.assertEqual(lead.customer_id, customer.pk)
        self.assertTrue(LeadNote.objects.filter(pk=note.data['id'], lead=lead).exists())
        state = LeadAgentState.objects.get(pk=lead.pk)
        self.assertEqual((state.applied_version, state.patient_name, state.reason), (2, 'Ana María Pérez', 'Control anual'))

        detail = self.client.get(_detail_url(lead)).data
        self.assertEqual(detail['agent_state']['patient_name'], 'Ana María Pérez')
        self.assertEqual(detail['customer']['id'], str(customer.pk))
        self.assertEqual(len(detail['notes']), 1)
