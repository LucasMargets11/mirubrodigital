"""PROD-02D — Guards de Leads, Clientes y aislamiento funcional de agenda.

Leads aceptan `appointments.leads` o `reception.leads` (cada uno contra su
propia suscripción). Clientes core también con `reception.customers`. La
agenda exige Turnos operativo (`has_agenda_access`): ni el rol, ni un
override, ni una flag la habilitan. `appointment-context` expone el aditivo
`agenda_enabled` y el receiver ignora confirmaciones sin Turnos.
"""
from __future__ import annotations

import datetime as dt
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Membership, RolePermissionOverride
from apps.appointments.models import Appointment, AppointmentService
from apps.appointments.services.agenda_access import has_agenda_access
from apps.billing.models import SubscriptionV2
from apps.billing.tests.test_reception_service_02b import _business, _reception, _sub, _superadmin
from apps.business.models import Subscription
from apps.customers.models import Customer
from apps.leads.models import AppointmentProposal, Lead, LeadAgentMessage, LeadNote
from apps.leads.services.appointment_context import agent_appointment_context

from . import test_receiver_api
from .agent_client import lead_path, sign_headers
from .factories import make_channel, make_instance, make_state
from .test_takeover import TAKEOVER_SETTINGS

User = get_user_model()
LEADS = '/api/v1/leads/'
AGENDA = '/api/v1/appointments/'

COMBOS = {
    # name: (principal, [subscription makers])
    'reception_only': ('reception', [_reception]),
    'gestion_reception': ('gestion', [lambda b: _sub(b, 'gestion', 'pro'), _reception]),
    'reception_turnos': ('reception', [_reception, lambda b: _sub(b, 'appointments', 'appointments_pro')]),
    'turnos_reception': ('appointments', [lambda b: _sub(b, 'appointments', 'appointments_pro'), _reception]),
    'turnos_ia': ('appointments', [lambda b: _sub(b, 'appointments', 'appointments_ai', 'ai_300')]),
    'turnos_base_v2': ('appointments', [lambda b: _sub(b, 'appointments', 'appointments_base')]),
    'turnos_base_legacy': ('appointments', [lambda b: Subscription.objects.create(
        business=b, plan='appointments_base', status='active', service='appointments')]),
    'turnos_pro_only': ('appointments', [lambda b: _sub(b, 'appointments', 'appointments_pro')]),
    'gestion_only': ('gestion', [lambda b: _sub(b, 'gestion', 'pro')]),
}
# name: (Leads API for a manager, operational agenda)
EXPECTED = {
    'reception_only': (200, False),
    'gestion_reception': (200, False),
    'reception_turnos': (200, True),
    'turnos_reception': (200, True),
    'turnos_ia': (200, True),
    'turnos_base_v2': (200, True),
    'turnos_base_legacy': (200, True),
    'turnos_pro_only': (403, True),
    'gestion_only': (403, False),
}


def _make(name):
    principal, makers = COMBOS[name]
    biz = _business(service=principal)
    for make in makers:
        make(biz)
    return biz


def _login(biz, role='manager'):
    user = User.objects.create_user(username=f'{role}-{uuid.uuid4().hex[:8]}', password='x')
    Membership.objects.create(user=user, business=biz, role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies['bid'] = str(biz.id)
    return client, user


def _lead(biz):
    instance = make_instance(f'agent-{uuid.uuid4().hex[:8]}')
    channel = make_channel(instance, biz, phone_number_id=str(uuid.uuid4().int)[:12])
    lead = Lead.objects.create(business=biz)
    state = make_state(lead, channel)
    return lead, state


def _code(response):
    data = getattr(response, 'data', None) or {}
    return data.get('code') if isinstance(data, dict) else None


# ── Matriz por combinación comercial ─────────────────────────────────────────

class CombinationMatrixTests(TestCase):

    def test_leads_api_and_agenda_per_combination(self):
        for name, (leads_status, agenda) in EXPECTED.items():
            with self.subTest(name):
                biz = _make(name)
                client, _ = _login(biz, 'manager')
                self.assertEqual(client.get(LEADS).status_code, leads_status)
                self.assertIs(has_agenda_access(biz), agenda)

    def test_agenda_requires_an_effective_turnos_subscription(self):
        cases = {
            'suspended': lambda b: _sub(b, 'appointments', 'appointments_pro', status=SubscriptionV2.Status.SUSPENDED),
            'canceled': lambda b: _sub(b, 'appointments', 'appointments_pro', status=SubscriptionV2.Status.CANCELED),
            'checkout_pending': lambda b: _sub(b, 'appointments', 'appointments_pro',
                                               status=SubscriptionV2.Status.CHECKOUT_PENDING),
            'no subscription at all': lambda b: None,
            'legacy not active': lambda b: Subscription.objects.create(
                business=b, plan='appointments_base', status='canceled', service='appointments'),
        }
        for name, make in cases.items():
            with self.subTest(name):
                biz = _business(service='appointments')
                make(biz)
                self.assertFalse(has_agenda_access(biz))

    def test_future_turnos_benefit_has_no_agenda_until_start(self):
        biz = _business(service='appointments')
        start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
        _sub(biz, 'appointments', 'appointments_pro', status=SubscriptionV2.Status.TRIALING, is_active=True,
             current_period_start=start, current_period_end=start + timedelta(days=60),
             manual_granted_by=_superadmin(), manual_grant_reason='Beneficio futuro')
        with patch('django.utils.timezone.now', return_value=start - timedelta(seconds=1)):
            self.assertFalse(has_agenda_access(biz))
        with patch('django.utils.timezone.now', return_value=start):
            self.assertTrue(has_agenda_access(biz))

    def test_ambiguous_state_fails_closed(self):
        biz = _make('turnos_pro_only')
        with patch('apps.billing.runtime.resolve_subscription', side_effect=RuntimeError('boom')):
            self.assertFalse(has_agenda_access(biz))
        self.assertFalse(has_agenda_access(None))

    def test_reception_without_access_denies_leads(self):
        for status_ in (SubscriptionV2.Status.SUSPENDED, SubscriptionV2.Status.CANCELED):
            with self.subTest(status=status_):
                biz = _business(service='gestion')
                _sub(biz, 'gestion', 'pro')
                _reception(biz, status=status_)
                client, _ = _login(biz, 'owner')
                self.assertEqual(client.get(LEADS).status_code, 403)

    def test_future_reception_benefit_opens_leads_only_from_its_start(self):
        biz = _business(service='gestion')
        _sub(biz, 'gestion', 'pro')
        start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
        _reception(biz, status=SubscriptionV2.Status.TRIALING, is_active=True,
                   current_period_start=start, current_period_end=start + timedelta(days=60),
                   manual_granted_by=_superadmin(), manual_grant_reason='Beneficio futuro')
        client, _ = _login(biz, 'owner')
        with patch('django.utils.timezone.now', return_value=start - timedelta(seconds=1)):
            self.assertEqual(client.get(LEADS).status_code, 403)
        with patch('django.utils.timezone.now', return_value=start + timedelta(seconds=1)):
            self.assertEqual(client.get(LEADS).status_code, 200)

    def test_suspended_principal_reception_blocks_everything(self):
        biz = _business()
        _reception(biz, status=SubscriptionV2.Status.SUSPENDED)
        user = User.objects.create_user(username=f'o-{uuid.uuid4().hex[:8]}', password='x')
        Membership.objects.create(user=user, business=biz, role='owner')
        client = APIClient()
        client.force_authenticate(user=user)
        client.cookies['bid'] = str(biz.id)
        for url in (LEADS, '/api/v1/customers/'):
            response = client.get(url)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(_code(response), 'subscription_access_denied')


# ── Solo Recepcionista: Leads, clientes y operación humana ───────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ReceptionOnlyOperationsTests(TestCase):

    def setUp(self):
        self.biz = _make('reception_only')
        self.lead, self.state = _lead(self.biz)
        self.client, self.user = _login(self.biz, 'manager')

    def test_leads_crud_notes_assign_and_activity(self):
        self.assertEqual([r['id'] for r in self.client.get(LEADS).data['results']], [str(self.lead.pk)])
        detail = self.client.get(f'{LEADS}{self.lead.pk}/')
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertIsNone(detail.data['appointment'])
        patched = self.client.patch(f'{LEADS}{self.lead.pk}/', {'status': 'in_progress'}, format='json')
        self.assertEqual(patched.status_code, 200, patched.data)
        assignees = self.client.get(f'{LEADS}assignees/')
        self.assertEqual(assignees.status_code, 200, assignees.data)
        assigned = self.client.patch(f'{LEADS}{self.lead.pk}/', {'assigned_to': self.user.pk}, format='json')
        self.assertEqual(assigned.status_code, 200, assigned.data)
        note = self.client.post(f'{LEADS}{self.lead.pk}/notes/', {'body': 'Llamar'}, format='json')
        self.assertEqual(note.status_code, 201, note.data)
        self.assertTrue(LeadNote.objects.filter(lead=self.lead).exists())
        self.assertTrue(self.client.get(f'{LEADS}{self.lead.pk}/').data['activity'])

    def test_conversation_takeover_and_messages(self):
        self.assertEqual(self.client.get(f'{LEADS}{self.lead.pk}/messages/').status_code, 200)
        taken = self.client.post(f'{LEADS}{self.lead.pk}/takeover/')
        # Guards pass (entitlement + RBAC); the command itself is the takeover service's business.
        self.assertNotEqual(taken.status_code, 403, taken.data)
        self.assertNotEqual(_code(taken), 'plan_entitlement_required')
        self.assertNotEqual(_code(self.client.post(f'{LEADS}{self.lead.pk}/release/')), 'plan_entitlement_required')

    def test_customers_list_create_and_link(self):
        self.assertEqual(self.client.get('/api/v1/customers/').status_code, 200)
        created = self.client.post('/api/v1/customers/', {'name': 'Ana', 'phone': '1155550000'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        customer = Customer.objects.get(business=self.biz, name='Ana')
        detail = self.client.get(f'/api/v1/customers/{customer.pk}/')
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertIsNone(detail.data.get('appointments_summary'))
        linked = self.client.patch(f'{LEADS}{self.lead.pk}/', {'customer': str(customer.pk)}, format='json')
        self.assertEqual(linked.status_code, 200, linked.data)
        self.assertEqual(Lead.objects.get(pk=self.lead.pk).customer_id, customer.pk)

    def test_customers_do_not_open_gestion_or_agenda_sections(self):
        customer = Customer.objects.create(business=self.biz, name='Leo', phone='1155550001')
        self.assertEqual(self.client.get(f'/api/v1/customers/{customer.pk}/appointments/').status_code, 403)
        timeline = self.client.get(f'/api/v1/customers/{customer.pk}/timeline/')
        if timeline.status_code == 200:
            self.assertEqual(timeline.data['types'], [])
        else:
            self.assertEqual(timeline.status_code, 403)

    def test_agenda_endpoints_denied(self):
        _, owner = _login(self.biz, 'owner')
        owner_client = APIClient()
        owner_client.force_authenticate(user=owner)
        owner_client.cookies['bid'] = str(self.biz.id)
        for client in (self.client, owner_client):
            for url in ('services/', 'professionals/', 'schedules/', 'appointments/', 'availability/', 'categories/'):
                with self.subTest(url=url):
                    self.assertEqual(client.get(AGENDA + url).status_code, 403)
            self.assertEqual(client.post(AGENDA + 'services/', {'name': 'X'}, format='json').status_code, 403)
            self.assertEqual(client.post(f'{LEADS}{self.lead.pk}/appointment/', {}, format='json').status_code, 403)
            self.assertEqual(client.get(f'{LEADS}{self.lead.pk}/appointment-proposals/current/').status_code, 403)

    def test_viewer_has_no_leads(self):
        viewer, _ = _login(self.biz, 'viewer')
        self.assertEqual(viewer.get(LEADS).status_code, 403)
        self.assertEqual(viewer.get('/api/v1/customers/').status_code, 200)


class TenantIsolationTests(TestCase):

    def test_reception_tenants_are_isolated(self):
        a, b = _make('reception_only'), _make('reception_only')
        lead_a, _ = _lead(a)
        lead_b, _ = _lead(b)
        client, _ = _login(a, 'manager')
        self.assertEqual([r['id'] for r in client.get(LEADS).data['results']], [str(lead_a.pk)])
        self.assertEqual(client.get(f'{LEADS}{lead_b.pk}/').status_code, 404)
        self.assertEqual(client.patch(f'{LEADS}{lead_b.pk}/', {'status': 'in_progress'}, format='json').status_code, 404)


# ── Overrides y owner sin suscripción de Turnos válida ───────────────────────

class OverridesNeverOpenAgendaTests(TestCase):
    """Gestión + Recepcionista con overrides crudos de agenda en `gestion` (el
    editor no los permite, pero la tabla sí): RBAC pasa, la agenda no."""

    def setUp(self):
        self.biz = _make('gestion_reception')
        for permission in ('view_appointments', 'manage_appointments'):
            RolePermissionOverride.objects.create(
                business=self.biz, role='owner', service='gestion', permission=permission, enabled=True,
            )
        self.lead, _ = _lead(self.biz)
        self.client, _ = _login(self.biz, 'owner')
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=Decimal('1000'),
            deposit_type=AppointmentService.DepositType.NONE,
        )

    def test_every_agenda_path_answers_agenda_unavailable(self):
        responses = {
            'services list': self.client.get(AGENDA + 'services/'),
            'service detail': self.client.get(f'{AGENDA}services/{self.service.pk}/'),
            'professional create': self.client.post(AGENDA + 'professionals/', {'name': 'Lu'}, format='json'),
            'availability': self.client.get(AGENDA + 'availability/'),
            'appointment create': self.client.post(AGENDA + 'appointments/', {}, format='json'),
            'lead appointment create': self.client.post(f'{LEADS}{self.lead.pk}/appointment/', {}, format='json'),
            'proposal create': self.client.post(f'{LEADS}{self.lead.pk}/appointment-proposals/', {}, format='json'),
            'proposal current': self.client.get(f'{LEADS}{self.lead.pk}/appointment-proposals/current/'),
        }
        for name, response in responses.items():
            with self.subTest(name):
                self.assertEqual(response.status_code, 403, getattr(response, 'data', None))
                self.assertEqual(_code(response), 'agenda_unavailable')

    def test_lead_patch_cannot_link_an_appointment(self):
        appointment = Appointment.objects.create(
            business=self.biz, service=self.service, customer_name='X', customer_phone='1155550000',
            start_at=timezone.now() + dt.timedelta(days=1), end_at=timezone.now() + dt.timedelta(days=1, minutes=30),
            status=Appointment.Status.CONFIRMED, service_name='Corte', service_duration_minutes=30,
            service_price=Decimal('1000'), deposit_type='none', deposit_value=Decimal('0'),
        )
        response = self.client.patch(f'{LEADS}{self.lead.pk}/', {'appointment': str(appointment.pk)}, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(_code(response), 'agenda_unavailable')
        self.assertIsNone(Lead.objects.get(pk=self.lead.pk).appointment_id)
        # Other CRM fields keep working.
        ok = self.client.patch(f'{LEADS}{self.lead.pk}/', {'status': 'in_progress'}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)


class CombinationRoleTests(TestCase):

    def test_reception_principal_with_turnos_operates_agenda(self):
        biz = _make('reception_turnos')
        client, _ = _login(biz, 'manager')
        self.assertEqual(client.get(AGENDA + 'services/').status_code, 200)
        self.assertEqual(client.get(LEADS).status_code, 200)
        viewer, _ = _login(biz, 'viewer')
        self.assertEqual(viewer.get(LEADS).status_code, 403)

    def test_turnos_principal_with_reception(self):
        biz = _make('turnos_reception')
        manager, _ = _login(biz, 'manager')
        self.assertEqual(manager.get(LEADS).status_code, 200)
        self.assertEqual(manager.get(AGENDA + 'services/').status_code, 200)
        professional, _ = _login(biz, 'professional')
        self.assertEqual(professional.get(LEADS).status_code, 403)

    def test_suspended_turnos_next_to_reception_closes_agenda_only(self):
        biz = _business(service='reception')
        _reception(biz)
        _sub(biz, 'appointments', 'appointments_pro', status=SubscriptionV2.Status.SUSPENDED)
        client, _ = _login(biz, 'owner')
        self.assertEqual(client.get(LEADS).status_code, 200)
        self.assertEqual(client.get(AGENDA + 'services/').status_code, 403)


# ── Contrato con el agente ───────────────────────────────────────────────────

class AgentAgendaContractTests(test_receiver_api.ProposalReceiverTestBase):
    """Reusa el Business con Turnos y la propuesta QUEUED de ProposalReceiverTestBase."""

    def context(self):
        path = lead_path(self.base_payload['external_lead_id']) + 'appointment-context/'
        headers = sign_headers(path=path, body=b'', key_id=self.credential.key_id, method='GET')
        return self.client.get(path, **headers)

    def test_context_with_agenda(self):
        body = self.context().json()
        self.assertIs(body['agenda_enabled'], True)
        self.assertEqual(body['proposal']['id'], str(self.proposal.pk))

    def _suspend_turnos(self):
        SubscriptionV2.objects.filter(business=self.business, service_type='appointments').update(
            status=SubscriptionV2.Status.SUSPENDED,
        )

    def test_context_without_agenda_hides_proposal_and_appointment(self):
        self._suspend_turnos()
        response = self.context()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), {'ok', 'external_lead_id', 'agenda_enabled', 'proposal', 'appointment'})
        self.assertIs(body['agenda_enabled'], False)
        self.assertIsNone(body['proposal'])
        self.assertIsNone(body['appointment'])

    def test_context_fails_closed_on_ambiguous_state(self):
        with patch('apps.billing.runtime.resolve_subscription', side_effect=RuntimeError('boom')):
            body = self.context().json()
        self.assertIs(body['agenda_enabled'], False)
        self.assertIsNone(body['proposal'])

    def test_agent_confirmation_without_agenda_is_ignored_but_sync_applies(self):
        self._suspend_turnos()
        payload = self.confirmation_payload()
        response = self.put(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.proposal.refresh_from_db()
        self.assertIsNone(self.proposal.confirmation_requested_at)
        self.assertEqual(self.proposal.status, AppointmentProposal.Status.QUEUED)
        self.assertFalse(Appointment.objects.exists())
        self.assertTrue(LeadAgentMessage.objects.filter(lead=self.lead, external_message_id='patient-msg-1').exists())
        self.assertIs(response.json()['agenda_enabled'], False)

    def test_reception_only_lead_context(self):
        biz = _make('reception_only')
        instance = make_instance(f'agent-{uuid.uuid4().hex[:8]}')
        channel = make_channel(instance, biz, phone_number_id=str(uuid.uuid4().int)[:12])
        lead = Lead.objects.create(business=biz)
        state = make_state(lead, channel)
        body = agent_appointment_context(agent_instance=instance, external_lead_id=state.external_lead_id)
        self.assertEqual(body['agenda_enabled'], False)
        self.assertIsNone(body['proposal'])
        self.assertIsNone(body['appointment'])
