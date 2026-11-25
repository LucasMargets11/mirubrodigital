"""PROD-02C — RBAC de Recepcionista IA y resolución multiservicio.

Leads (`view_leads`, `manage_leads`, `manage_agent_channels`, `view_ai_usage`)
se evalúan en su servicio dueño (Recepcionista, si no Turnos); la agenda en
Turnos; el resto en el servicio activo. Sin uniones de mapas: un deny explícito
de cualquier proveedor gana y un override de otro servicio no otorga nada.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Membership, RolePermissionOverride
from apps.accounts.rbac import (
    APPOINTMENTS_OWN_PERMISSIONS,
    GESTION_PERMISSIONS,
    RECEPTION_PERMISSIONS,
    SERVICE_ROLE_PERMISSIONS,
    permissions_for_service,
)
from apps.accounts.rbac_registry import get_registry
from apps.accounts.service_permissions import AGENDA_PERMISSIONS, LEADS_PERMISSIONS, effective_permissions
from apps.billing.models import SubscriptionV2
from apps.billing.tests.test_reception_service_02b import _business, _reception, _sub, _superadmin
from apps.business.context import build_business_context
from apps.business.models import Subscription
from apps.leads.services.assignees import assignable_memberships
from apps.notifications.models import BusinessNotification

User = get_user_model()
ME_URL = '/api/v1/auth/me/'
ROLES_URL = '/api/v1/owner/access/roles/'

RECEPTION_MATRIX = {
    'owner': RECEPTION_PERMISSIONS,
    'admin': RECEPTION_PERMISSIONS,
    'manager': {'view_leads', 'manage_leads', 'view_customers', 'manage_customers',
                'manage_customer_notes', 'manage_settings'},
    'viewer': {'view_customers'},
}


def _member(business, role):
    user = User.objects.create_user(username=f'{role}-{uuid.uuid4().hex[:8]}', password='x')
    return Membership.objects.create(user=user, business=business, role=role)


def _client(membership):
    client = APIClient()
    client.force_authenticate(user=membership.user)
    client.cookies['bid'] = str(membership.business_id)
    return client


def _effective(business, role):
    return effective_permissions(business, role, build_business_context(business)['service'])


def _granted(perms, codes):
    return {code for code in codes if perms.get(code)}


# ── Mapa RBAC y registry ─────────────────────────────────────────────────────

class ReceptionRoleMapTests(SimpleTestCase):

    def test_roles_and_defaults(self):
        self.assertEqual(set(SERVICE_ROLE_PERMISSIONS['reception']), set(RECEPTION_MATRIX))
        for role, expected in RECEPTION_MATRIX.items():
            with self.subTest(role=role):
                perms = permissions_for_service('reception', role)
                self.assertEqual({code for code, on in perms.items() if on}, set(expected))

    def test_reception_never_grants_agenda_professionals_or_gestion(self):
        forbidden = AGENDA_PERMISSIONS | APPOINTMENTS_OWN_PERMISSIONS | (GESTION_PERMISSIONS - RECEPTION_PERMISSIONS)
        for role in ('owner', 'admin', 'manager', 'viewer', 'professional', 'cashier'):
            with self.subTest(role=role):
                perms = permissions_for_service('reception', role)
                self.assertEqual(_granted(perms, forbidden), set())
        self.assertEqual(_granted(permissions_for_service('reception', 'professional'), RECEPTION_PERMISSIONS), set())

    def test_view_ai_usage_owner_admin_only(self):
        for service in ('reception', 'appointments'):
            for role, allowed in (('owner', True), ('admin', True), ('manager', False), ('viewer', False)):
                with self.subTest(service=service, role=role):
                    self.assertIs(permissions_for_service(service, role)['view_ai_usage'], allowed)

    def test_registry_lists_reception_without_moving_lead_owners(self):
        registry = get_registry()
        self.assertEqual({cap.code for cap in registry.get_by_service('reception')}, RECEPTION_PERMISSIONS)
        self.assertEqual(registry.get('view_leads').service, 'appointments')
        self.assertEqual(registry.get('view_ai_usage').service, 'reception')
        self.assertIn('view_ai_usage', {cap.code for cap in registry.get_by_service('appointments')})
        self.assertFalse(AGENDA_PERMISSIONS & {cap.code for cap in registry.get_by_service('reception')})


# ── Resolución efectiva por combinación de servicios ─────────────────────────

class ReceptionOnlyTests(TestCase):

    def setUp(self):
        self.biz = _business()
        _reception(self.biz)

    def test_permissions_by_role(self):
        for role, expected in RECEPTION_MATRIX.items():
            with self.subTest(role=role):
                perms = _effective(self.biz, role)
                self.assertEqual(_granted(perms, RECEPTION_PERMISSIONS), set(expected))
                self.assertEqual(_granted(perms, AGENDA_PERMISSIONS), set())
        professional = _effective(self.biz, 'professional')
        self.assertEqual(_granted(professional, LEADS_PERMISSIONS | AGENDA_PERMISSIONS), set())

    def test_overrides_cannot_reach_agenda_or_other_products(self):
        for permission in ('manage_appointments', 'view_appointments', 'manage_sales', 'view_products'):
            RolePermissionOverride.objects.create(
                business=self.biz, role='manager', service='reception', permission=permission, enabled=True,
            )
        perms = _effective(self.biz, 'manager')
        for permission in ('manage_appointments', 'view_appointments', 'manage_sales', 'view_products'):
            self.assertFalse(perms.get(permission, False), permission)

    def test_reception_override_inside_scope_applies(self):
        RolePermissionOverride.objects.create(
            business=self.biz, role='manager', service='reception', permission='view_ai_usage', enabled=True,
        )
        RolePermissionOverride.objects.create(
            business=self.biz, role='manager', service='reception', permission='manage_leads', enabled=False,
        )
        perms = _effective(self.biz, 'manager')
        self.assertTrue(perms['view_ai_usage'])
        self.assertFalse(perms['manage_leads'])
        self.assertTrue(perms['view_leads'])


class GestionPrincipalWithReceptionTests(TestCase):

    def setUp(self):
        self.biz = _business(service='gestion')
        _sub(self.biz, 'gestion', 'pro')
        _reception(self.biz)

    def test_leads_from_reception_rest_from_gestion(self):
        manager = _effective(self.biz, 'manager')
        self.assertEqual(build_business_context(self.biz)['service'], 'gestion')
        self.assertTrue(manager['view_leads'])
        self.assertTrue(manager['manage_leads'])
        self.assertFalse(manager['manage_agent_channels'])
        self.assertEqual(manager['view_sales'], permissions_for_service('gestion', 'manager')['view_sales'])
        self.assertEqual(_granted(manager, AGENDA_PERMISSIONS), set())
        # A Gestión-only role gets nothing from Recepcionista.
        self.assertEqual(_granted(_effective(self.biz, 'cashier'), LEADS_PERMISSIONS), set())

    def test_gestion_override_never_grants_leads(self):
        RolePermissionOverride.objects.create(
            business=self.biz, role='cashier', service='gestion', permission='view_leads', enabled=True,
        )
        self.assertFalse(_effective(self.biz, 'cashier')['view_leads'])

    def test_reception_deny_wins(self):
        RolePermissionOverride.objects.create(
            business=self.biz, role='manager', service='reception', permission='view_leads', enabled=False,
        )
        self.assertFalse(_effective(self.biz, 'manager')['view_leads'])


class ReceptionPrincipalWithTurnosTests(TestCase):

    def test_agenda_from_turnos_leads_and_customers_from_reception(self):
        biz = _business(service='reception')
        _reception(biz)
        _sub(biz, 'appointments', 'appointments_pro')
        self.assertEqual(build_business_context(biz)['service'], 'reception')
        manager = _effective(biz, 'manager')
        self.assertTrue(manager['view_appointments'])
        self.assertTrue(manager['manage_appointments'])
        self.assertFalse(manager['manage_reminder_automations'])
        self.assertTrue(manager['view_leads'])
        self.assertTrue(manager['manage_customers'])
        viewer = _effective(biz, 'viewer')
        self.assertTrue(viewer['view_appointments'])
        self.assertFalse(viewer['view_leads'])

    def test_reception_override_does_not_touch_agenda(self):
        biz = _business(service='reception')
        _reception(biz)
        _sub(biz, 'appointments', 'appointments_pro')
        RolePermissionOverride.objects.create(
            business=biz, role='viewer', service='reception', permission='manage_appointments', enabled=True,
        )
        self.assertFalse(_effective(biz, 'viewer')['manage_appointments'])


class TurnosPrincipalWithReceptionTests(TestCase):

    def setUp(self):
        self.biz = _business(service='appointments')
        _sub(self.biz, 'appointments', 'appointments_pro')
        _reception(self.biz)

    def test_leads_owned_by_reception(self):
        self.assertEqual(build_business_context(self.biz)['service'], 'appointments')
        manager = _effective(self.biz, 'manager')
        self.assertTrue(manager['view_leads'])
        self.assertTrue(manager['view_appointments'])
        # Turnos allow overrides do not add Leads: Recepcionista owns them.
        RolePermissionOverride.objects.create(
            business=self.biz, role='viewer', service='appointments', permission='view_leads', enabled=True,
        )
        self.assertFalse(_effective(self.biz, 'viewer')['view_leads'])

    def test_turnos_deny_is_not_neutralized_by_reception(self):
        RolePermissionOverride.objects.create(
            business=self.biz, role='manager', service='appointments', permission='view_leads', enabled=False,
        )
        self.assertFalse(_effective(self.biz, 'manager')['view_leads'])
        self.assertTrue(_effective(self.biz, 'manager')['manage_leads'])


class TurnosCompatibilityTests(TestCase):

    def test_turnos_ia_and_turnos_base_keep_leads(self):
        cases = {
            'turnos_ia': lambda b: _sub(b, 'appointments', 'appointments_ai', 'ai_300'),
            'turnos_base_v2': lambda b: _sub(b, 'appointments', 'appointments_base'),
            'turnos_base_legacy': lambda b: Subscription.objects.create(
                business=b, plan='appointments_base', status='active', service='appointments'),
        }
        for name, make in cases.items():
            with self.subTest(name):
                biz = _business(service='appointments')
                make(biz)
                manager = _effective(biz, 'manager')
                self.assertTrue(manager['view_leads'])
                self.assertTrue(manager['manage_leads'])
                self.assertTrue(manager['view_appointments'])
                self.assertFalse(manager['view_ai_usage'])
                self.assertTrue(_effective(biz, 'owner')['view_ai_usage'])
                self.assertFalse(_effective(biz, 'viewer')['view_leads'])

    def test_existing_turnos_overrides_still_apply(self):
        biz = _business(service='appointments')
        _sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        RolePermissionOverride.objects.create(
            business=biz, role='manager', service='appointments', permission='manage_leads', enabled=False,
        )
        self.assertFalse(_effective(biz, 'manager')['manage_leads'])

    def test_gestion_only_has_no_leads_or_agenda(self):
        biz = _business(service='gestion')
        _sub(biz, 'gestion', 'business')
        owner = _effective(biz, 'owner')
        self.assertEqual(_granted(owner, LEADS_PERMISSIONS | AGENDA_PERMISSIONS), set())
        self.assertEqual(owner, {**permissions_for_service('gestion', 'owner', biz), **{
            code: False for code in LEADS_PERMISSIONS | AGENDA_PERMISSIONS}})


class ReceptionWithoutAccessTests(TestCase):

    def test_suspended_or_canceled_reception_grants_nothing_next_to_gestion(self):
        for status in (SubscriptionV2.Status.SUSPENDED, SubscriptionV2.Status.CANCELED):
            with self.subTest(status=status):
                biz = _business(service='gestion')
                _sub(biz, 'gestion', 'pro')
                _reception(biz, status=status)
                self.assertEqual(_granted(_effective(biz, 'owner'), LEADS_PERMISSIONS), set())
                context = build_business_context(biz)
                self.assertNotIn('reception', context['enabled_services'])
                self.assertFalse(context['features']['leads'])

    def test_future_benefit_grants_only_from_its_start(self):
        biz = _business(service='gestion')
        _sub(biz, 'gestion', 'pro')
        start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
        _reception(
            biz, status=SubscriptionV2.Status.TRIALING, is_active=True,
            current_period_start=start, current_period_end=start + timedelta(days=90),
            manual_granted_by=_superadmin(), manual_grant_reason='Beneficio futuro',
        )
        with patch('django.utils.timezone.now', return_value=start - timedelta(seconds=1)):
            self.assertFalse(_effective(biz, 'manager')['view_leads'])
            self.assertFalse(build_business_context(biz)['features']['leads'])
        with patch('django.utils.timezone.now', return_value=start):
            self.assertTrue(_effective(biz, 'manager')['view_leads'])
            self.assertTrue(build_business_context(biz)['features']['leads'])

    def test_suspended_principal_reception_has_no_session_capability(self):
        biz = _business()
        _reception(biz, status=SubscriptionV2.Status.SUSPENDED)
        context = build_business_context(biz)
        self.assertFalse(context['access_allowed'])
        self.assertFalse(context['features']['leads'])
        self.assertFalse(context['features']['customers'])
        self.assertFalse(context['features']['agenda_integration'])


# ── Contexto de sesión ───────────────────────────────────────────────────────

class SessionContextTests(TestCase):

    def _ctx(self, service, *subs):
        biz = _business(service=service)
        for make in subs:
            make(biz)
        return build_business_context(biz)

    def test_flags_per_combination(self):
        reception = _reception
        gestion = lambda b: _sub(b, 'gestion', 'pro')  # noqa: E731
        turnos = lambda b: _sub(b, 'appointments', 'appointments_pro')  # noqa: E731
        turnos_ia = lambda b: _sub(b, 'appointments', 'appointments_ai', 'ai_300')  # noqa: E731
        turnos_base = lambda b: _sub(b, 'appointments', 'appointments_base')  # noqa: E731
        cases = [
            # name, principal, subs, enabled ⊇, reception_core, leads, customers, agenda_integration
            ('reception only', 'reception', [reception], {'reception'}, True, True, True, False),
            ('gestion + reception', 'gestion', [gestion, reception], {'gestion', 'reception'}, True, True, True, False),
            ('reception + turnos', 'reception', [reception, turnos], {'reception', 'appointments'}, True, True, True, True),
            ('turnos + reception', 'appointments', [turnos, reception], {'appointments', 'reception'}, True, True, True, True),
            ('turnos ia', 'appointments', [turnos_ia], {'appointments'}, False, True, True, True),
            ('turnos base v2', 'appointments', [turnos_base], {'appointments'}, False, True, True, True),
            ('turnos pro only', 'appointments', [turnos], {'appointments'}, False, False, True, False),
            ('gestion only', 'gestion', [gestion], {'gestion'}, False, False, True, False),
        ]
        for name, principal, subs, enabled, core, leads, customers, agenda in cases:
            with self.subTest(name):
                ctx = self._ctx(principal, *subs)
                self.assertTrue(enabled.issubset(set(ctx['enabled_services'])), ctx['enabled_services'])
                self.assertEqual('reception' in ctx['enabled_services'], core)
                self.assertIs(ctx['features']['reception_core'], core)
                self.assertIs(ctx['features']['leads'], leads)
                self.assertIs(ctx['features']['customers'], customers)
                self.assertIs(ctx['features']['agenda_integration'], agenda)
                self.assertEqual(ctx['service'], principal)

    def test_me_exposes_effective_permissions(self):
        biz = _business(service='gestion')
        _sub(biz, 'gestion', 'pro')
        _reception(biz)
        manager = _member(biz, 'manager')
        data = _client(manager).get(ME_URL).json()
        self.assertEqual(data['current']['service'], 'gestion')
        self.assertIn('reception', data['services']['enabled'])
        self.assertTrue(data['features']['leads'])
        self.assertTrue(data['permissions']['view_leads'])
        self.assertFalse(data['permissions']['manage_agent_channels'])
        self.assertFalse(data['permissions']['view_appointments'])


# ── Consumidores ─────────────────────────────────────────────────────────────

class ConsumerTests(TestCase):

    def setUp(self):
        self.biz = _business(service='gestion')
        _sub(self.biz, 'gestion', 'pro')
        _reception(self.biz)
        self.owner = _member(self.biz, 'owner')
        self.manager = _member(self.biz, 'manager')
        self.cashier = _member(self.biz, 'cashier')

    def test_assignees_follow_reception_permissions(self):
        ids = {m.pk for m in assignable_memberships(self.biz.pk, 'gestion')}
        self.assertIn(self.owner.pk, ids)
        self.assertIn(self.manager.pk, ids)
        self.assertNotIn(self.cashier.pk, ids)
        reception_only = _business()
        _reception(reception_only)
        viewer = _member(reception_only, 'viewer')
        manager = _member(reception_only, 'manager')
        ids = {m.pk for m in assignable_memberships(reception_only.pk, 'reception')}
        self.assertEqual(ids, {manager.pk})
        self.assertNotIn(viewer.pk, ids)

    def test_handoff_notifications_follow_reception_permissions(self):
        BusinessNotification.objects.create(
            business=self.biz, kind=BusinessNotification.Kind.AGENT_LEAD_HANDOFF,
            title='Consulta', dedupe_key=f'h-{uuid.uuid4().hex}',
        )
        response = _client(self.manager).get('/api/v1/notifications/business/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row['kind'] for row in response.json()['results']], ['agent_lead_handoff'])
        cashier = _client(self.cashier).get('/api/v1/notifications/business/')
        if cashier.status_code == 200:
            self.assertNotIn('agent_lead_handoff', [row['kind'] for row in cashier.json()['results']])
        else:
            self.assertEqual(cashier.status_code, 403)

    def test_role_editor_per_service(self):
        client = _client(self.owner)
        default = client.get(f'{ROLES_URL}manager/')
        self.assertEqual(default.status_code, 200, default.content)
        reception = client.get(f'{ROLES_URL}manager/?service=reception')
        self.assertEqual(reception.status_code, 200, reception.content)
        self.assertEqual(client.get(f'{ROLES_URL}manager/?service=appointments').status_code, 400)
        self.assertEqual(client.get(f'{ROLES_URL}cashier/?service=reception').status_code, 404)
        # Agenda keys are not editable through Recepcionista.
        rejected = client.put(f'{ROLES_URL}manager/permissions/?service=reception', {
            'permissions': [{'permission': 'manage_appointments', 'enabled': True}],
        }, format='json')
        self.assertEqual(rejected.status_code, 400, rejected.content)
        ok = client.put(f'{ROLES_URL}manager/permissions/?service=reception', {
            'permissions': [{'permission': 'view_leads', 'enabled': False}],
        }, format='json')
        self.assertEqual(ok.status_code, 200, ok.content)
        override = RolePermissionOverride.objects.get(business=self.biz, role='manager', permission='view_leads')
        self.assertEqual(override.service, 'reception')
        self.assertFalse(_effective(self.biz, 'manager')['view_leads'])
        self.assertFalse(RolePermissionOverride.objects.filter(business=self.biz, service='gestion').exists())

    def test_access_summary_lists_reception_capabilities(self):
        data = _client(self.manager).get('/api/v1/owner/access/summary/').json()
        codes = {perm['code']: perm['granted'] for perms in data['permissions_by_module'].values() for perm in perms}
        self.assertTrue(codes['view_leads'])
        self.assertFalse(codes['view_ai_usage'])
