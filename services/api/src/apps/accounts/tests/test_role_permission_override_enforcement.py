"""RBAC-FIX 01: los `RolePermissionOverride` del Business se aplican en el enforcement.

Antes del fix el editor de roles del owner guardaba y mostraba los overrides,
pero `request_has_permission` (y por ende `HasPermission`), `/auth/me/` y el
resumen de acceso resolvían solo los defaults del rol.

Regla: los overrides se buscan con `membership.business` (misma clave con la
que escribe `PUT /api/v1/owner/access/roles/{role}/permissions/`). En herencia
HQ → sucursal la membership es la del HQ, así que aplican los overrides del HQ.
"""
from __future__ import annotations

import uuid

from django.test import RequestFactory
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership, RolePermissionOverride
from apps.accounts.permissions import request_has_permission
from apps.accounts.rbac import SERVICE_ROLE_PERMISSIONS, permissions_for_service
from apps.appointments.tests.test_customer_core_access import _gestion_business, _login, _turnos_business
from apps.business.models import Business
from apps.leads.models import Lead
from apps.notifications.models import BusinessNotification

ROLE_PERMS_URL = '/api/v1/owner/access/roles/{role}/permissions/'
ROLE_DETAIL_URL = '/api/v1/owner/access/roles/{role}/'
ME_URL = '/api/v1/auth/me/'
SUMMARY_URL = '/api/v1/owner/access/summary/'
LEADS_URL = '/api/v1/leads/'
CUSTOMERS_URL = '/api/v1/customers/'
NOTIFICATIONS_URL = '/api/v1/notifications/business/'


def _override(business, role, permission, enabled, service):
    return RolePermissionOverride.objects.create(
        business=business, role=role, service=service, permission=permission, enabled=enabled,
    )


def _summary_granted(response) -> set[str]:
    return {
        perm['code'] for perms in response.data['permissions_by_module'].values() for perm in perms if perm['granted']
    }


class OverrideApiMixin:

    def _owner_put(self, owner_client, role, permission, enabled):
        response = owner_client.put(
            ROLE_PERMS_URL.format(role=role), {'permissions': [{'permission': permission, 'enabled': enabled}]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response


# ── HasPermission: Turnos ───────────────────────────────────────────────────

class TurnosHasPermissionOverrideTests(OverrideApiMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug=f'ovr-t-{uuid.uuid4().hex[:6]}')
        self.owner_client = APIClient()
        _login(self.owner_client, self.biz, 'owner')
        self.lead = Lead.objects.create(business=self.biz)

    def test_revoke_via_owner_editor_is_enforced(self):
        manager = APIClient()
        _login(manager, self.biz, 'manager')
        self.assertEqual(manager.get(LEADS_URL).status_code, status.HTTP_200_OK)

        self._owner_put(self.owner_client, 'manager', 'view_leads', False)
        self.assertEqual(manager.get(LEADS_URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(manager.get(f'{LEADS_URL}{self.lead.pk}/').status_code, status.HTTP_403_FORBIDDEN)
        # Solo se revocó la lectura: la mutación depende de `manage_leads`.
        response = manager.patch(f'{LEADS_URL}{self.lead.pk}/', {'status': 'in_progress'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._owner_put(self.owner_client, 'manager', 'manage_leads', False)
        response = manager.patch(f'{LEADS_URL}{self.lead.pk}/', {'status': 'closed', 'outcome': 'spam'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.IN_PROGRESS)

        # Re-habilitar vuelve al acceso.
        self._owner_put(self.owner_client, 'manager', 'view_leads', True)
        self.assertEqual(manager.get(LEADS_URL).status_code, status.HTTP_200_OK)

    def test_grant_via_owner_editor_is_enforced(self):
        viewer = APIClient()
        _login(viewer, self.biz, 'viewer')
        self.assertEqual(viewer.get(LEADS_URL).status_code, status.HTTP_403_FORBIDDEN)
        self._owner_put(self.owner_client, 'viewer', 'view_leads', True)
        self.assertEqual(viewer.get(LEADS_URL).status_code, status.HTTP_200_OK)
        # Grant de lectura no implica escritura.
        response = viewer.patch(f'{LEADS_URL}{self.lead.pk}/', {'status': 'in_progress'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_not_affected_by_other_roles_overrides_and_not_editable(self):
        for permission in ('view_leads', 'manage_leads', 'view_customers'):
            _override(self.biz, 'manager', permission, False, 'appointments')
            _override(self.biz, 'admin', permission, False, 'appointments')
        self.assertEqual(self.owner_client.get(LEADS_URL).status_code, status.HTTP_200_OK)
        response = self.owner_client.patch(f'{LEADS_URL}{self.lead.pk}/', {'status': 'in_progress'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Regla actual: el editor no permite overrides sobre el rol owner.
        response = self.owner_client.put(
            ROLE_PERMS_URL.format(role='owner'), {'permissions': [{'permission': 'view_leads', 'enabled': False}]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(RolePermissionOverride.objects.filter(business=self.biz, role='owner').exists())
        self.assertEqual(self.owner_client.get(LEADS_URL).status_code, status.HTTP_200_OK)


# ── HasPermission: Gestión ──────────────────────────────────────────────────

class GestionHasPermissionOverrideTests(OverrideApiMixin, APITestCase):

    def setUp(self):
        self.biz = _gestion_business('business', f'ovr-g-{uuid.uuid4().hex[:6]}')
        self.owner_client = APIClient()
        _login(self.owner_client, self.biz, 'owner')

    def test_revoke_is_enforced(self):
        manager = APIClient()
        _login(manager, self.biz, 'manager')
        self.assertEqual(manager.get(CUSTOMERS_URL).status_code, status.HTTP_200_OK)
        self._owner_put(self.owner_client, 'manager', 'view_customers', False)
        self.assertEqual(manager.get(CUSTOMERS_URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.owner_client.get(CUSTOMERS_URL).status_code, status.HTTP_200_OK)

    def test_grant_is_enforced(self):
        role = 'cashier'
        self.assertNotIn('manage_products', SERVICE_ROLE_PERMISSIONS['gestion'][role])
        cashier = APIClient()
        _login(cashier, self.biz, role)
        url = '/api/v1/catalog/products/'
        payload = {'name': f'Producto {uuid.uuid4().hex[:6]}', 'price': '10.00'}
        self.assertEqual(cashier.post(url, payload, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self._owner_put(self.owner_client, role, 'manage_products', True)
        response = cashier.post(url, payload, format='json')
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN, getattr(response, 'data', None))


# ── Sesión y resumen de acceso ──────────────────────────────────────────────

class SessionAndSummaryOverrideTests(OverrideApiMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug=f'ovr-s-{uuid.uuid4().hex[:6]}')
        self.owner_client = APIClient()
        _login(self.owner_client, self.biz, 'owner')
        self.manager = APIClient()
        _login(self.manager, self.biz, 'manager')

    def test_me_returns_effective_permissions(self):
        self.assertTrue(self.manager.get(ME_URL).data['permissions']['view_leads'])
        self._owner_put(self.owner_client, 'manager', 'view_leads', False)
        self._owner_put(self.owner_client, 'manager', 'manage_agent_channels', True)
        permissions = self.manager.get(ME_URL).data['permissions']
        self.assertFalse(permissions['view_leads'])
        self.assertTrue(permissions['manage_agent_channels'])
        self.assertTrue(permissions['manage_leads'])
        # El owner sigue con todo.
        owner_permissions = self.owner_client.get(ME_URL).data['permissions']
        self.assertTrue(owner_permissions['view_leads'])

    def test_summary_returns_effective_permissions(self):
        self.assertIn('view_leads', _summary_granted(self.manager.get(SUMMARY_URL)))
        self._owner_put(self.owner_client, 'manager', 'view_leads', False)
        self._owner_put(self.owner_client, 'manager', 'manage_agent_channels', True)
        granted = _summary_granted(self.manager.get(SUMMARY_URL))
        self.assertNotIn('view_leads', granted)
        self.assertIn('manage_agent_channels', granted)

    def test_me_summary_and_role_editor_agree(self):
        self._owner_put(self.owner_client, 'manager', 'view_leads', False)
        me = self.manager.get(ME_URL).data['permissions']
        summary = _summary_granted(self.manager.get(SUMMARY_URL))
        detail = self.owner_client.get(ROLE_DETAIL_URL.format(role='manager')).data
        editor = {p['code'] for perms in detail['permissions_by_module'].values() for p in perms if p['enabled']}
        self.assertEqual(editor, summary)
        self.assertEqual(editor, {code for code in editor if me.get(code)})
        self.assertFalse(me['view_leads'])


# ── Caller directo de request_has_permission ────────────────────────────────

class DirectCallerOverrideTests(OverrideApiMixin, APITestCase):
    """Bandeja de notificaciones: filtra kinds con `request_has_permission`."""

    def setUp(self):
        self.biz = _turnos_business(slug=f'ovr-n-{uuid.uuid4().hex[:6]}')
        self.owner_client = APIClient()
        _login(self.owner_client, self.biz, 'owner')
        for kind in (BusinessNotification.Kind.AGENT_LEAD_HANDOFF, BusinessNotification.Kind.CUSTOMER_REMINDER_DUE):
            BusinessNotification.objects.create(
                business=self.biz, kind=kind, title=kind, dedupe_key=f'{kind}:{uuid.uuid4()}',
            )

    def _kinds(self, client):
        response = client.get(NOTIFICATIONS_URL)
        if response.status_code != status.HTTP_200_OK:
            return response.status_code
        return {row['kind'] for row in response.data['results']}

    def test_revoke_hides_kind(self):
        manager = APIClient()
        _login(manager, self.biz, 'manager')
        self.assertIn('agent_lead_handoff', self._kinds(manager))
        self._owner_put(self.owner_client, 'manager', 'view_leads', False)
        self.assertNotIn('agent_lead_handoff', self._kinds(manager))

    def test_grant_shows_kind(self):
        viewer = APIClient()
        _login(viewer, self.biz, 'viewer')
        self.assertEqual(self._kinds(viewer), status.HTTP_403_FORBIDDEN)
        self._owner_put(self.owner_client, 'viewer', 'view_leads', True)
        self.assertEqual(self._kinds(viewer), {'agent_lead_handoff'})


# ── Tenant isolation ────────────────────────────────────────────────────────

class OverrideTenantIsolationTests(OverrideApiMixin, APITestCase):

    def setUp(self):
        self.biz_a = _turnos_business(slug=f'ovr-a-{uuid.uuid4().hex[:6]}')
        self.biz_b = _turnos_business(slug=f'ovr-b-{uuid.uuid4().hex[:6]}')

    def test_override_of_one_business_does_not_affect_another(self):
        _override(self.biz_a, 'manager', 'view_leads', False, 'appointments')
        manager_a, manager_b = APIClient(), APIClient()
        _login(manager_a, self.biz_a, 'manager')
        _login(manager_b, self.biz_b, 'manager')
        self.assertEqual(manager_a.get(LEADS_URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(manager_b.get(LEADS_URL).status_code, status.HTTP_200_OK)
        self.assertTrue(manager_b.get(ME_URL).data['permissions']['view_leads'])

    def test_same_user_in_two_businesses_gets_each_business_overrides(self):
        # Un override de A nunca se aplica a la membership de B del mismo usuario (ni al revés).
        _override(self.biz_a, 'manager', 'view_leads', False, 'appointments')
        _override(self.biz_b, 'manager', 'manage_agent_channels', True, 'appointments')
        client = APIClient()
        user = _login(client, self.biz_a, 'manager')
        Membership.objects.create(user=user, business=self.biz_b, role='manager')

        client.cookies['bid'] = str(self.biz_a.id)
        self.assertEqual(client.get(LEADS_URL).status_code, status.HTTP_403_FORBIDDEN)
        perms_a = client.get(ME_URL).data['permissions']
        self.assertFalse(perms_a['view_leads'])
        self.assertFalse(perms_a['manage_agent_channels'])

        client.cookies['bid'] = str(self.biz_b.id)
        self.assertEqual(client.get(LEADS_URL).status_code, status.HTTP_200_OK)
        perms_b = client.get(ME_URL).data['permissions']
        self.assertTrue(perms_b['view_leads'])
        self.assertTrue(perms_b['manage_agent_channels'])

    def test_override_for_other_service_is_ignored(self):
        # Mismo Business y rol, pero el override es de otro servicio.
        _override(self.biz_a, 'manager', 'view_leads', False, 'gestion')
        manager = APIClient()
        _login(manager, self.biz_a, 'manager')
        self.assertEqual(manager.get(LEADS_URL).status_code, status.HTTP_200_OK)


# ── HQ → sucursal ───────────────────────────────────────────────────────────

class HqBranchOverrideTests(APITestCase):
    """Admin del HQ heredado en una sucursal: aplican los overrides del HQ (membership.business)."""

    def setUp(self):
        self.hq = _gestion_business('business', f'ovr-hq-{uuid.uuid4().hex[:6]}')
        self.branch = Business.objects.create(name='Sucursal', parent=self.hq, default_service='gestion')
        self.admin = _login(APIClient(), self.hq, 'admin')
        self.factory = RequestFactory()

    def _request(self, business, user=None):
        request = Request(self.factory.get('/x/', HTTP_X_BUSINESS_ID=str(business.id)))
        request.user = user or self.admin
        return request

    def test_inherited_admin_uses_hq_overrides(self):
        _override(self.hq, 'admin', 'view_customers', False, 'gestion')
        request = self._request(self.branch)
        self.assertFalse(request_has_permission(request, 'view_customers'))
        self.assertEqual(request.business, self.branch)
        self.assertEqual(request.membership.business, self.hq)
        self.assertTrue(request_has_permission(self._request(self.branch), 'view_sales'))
        self.assertFalse(request_has_permission(self._request(self.hq), 'view_customers'))

    def test_branch_overrides_do_not_apply_to_inherited_admin(self):
        # Semántica actual (sin cambios): no hay overrides por sucursal para el heredado.
        _override(self.branch, 'admin', 'view_customers', False, 'gestion')
        self.assertTrue(request_has_permission(self._request(self.branch), 'view_customers'))

    def test_hq_overrides_do_not_leak_to_direct_branch_membership(self):
        _override(self.hq, 'manager', 'view_customers', False, 'gestion')
        branch_manager = _login(APIClient(), self.branch, 'manager')
        self.assertTrue(request_has_permission(self._request(self.branch, branch_manager), 'view_customers'))


# ── Sin overrides ───────────────────────────────────────────────────────────

class NoOverrideBehaviourTests(APITestCase):

    def test_effective_permissions_equal_defaults_without_overrides(self):
        biz = _turnos_business(slug=f'ovr-none-{uuid.uuid4().hex[:6]}')
        # Overrides de OTRO Business no cuentan.
        other = _turnos_business(slug=f'ovr-none-o-{uuid.uuid4().hex[:6]}')
        _override(other, 'manager', 'view_leads', False, 'appointments')
        for role in ('owner', 'admin', 'manager', 'viewer'):
            with self.subTest(role=role):
                self.assertEqual(
                    permissions_for_service('appointments', role, biz), permissions_for_service('appointments', role),
                )
        client = APIClient()
        _login(client, biz, 'manager')
        self.assertEqual(client.get(ME_URL).data['permissions'], permissions_for_service('appointments', 'manager'))
        self.assertEqual(client.get(LEADS_URL).status_code, status.HTTP_200_OK)


# ── Leads: validación de assigned_to ────────────────────────────────────────

class LeadAssigneeOverrideTests(APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug=f'ovr-l-{uuid.uuid4().hex[:6]}')
        self.owner_client = APIClient()
        _login(self.owner_client, self.biz, 'owner')
        self.lead = Lead.objects.create(business=self.biz)

    def _assign(self, user):
        return self.owner_client.patch(f'{LEADS_URL}{self.lead.pk}/', {'assigned_to': user.pk}, format='json')

    def test_revoked_view_leads_not_assignable(self):
        manager = _login(APIClient(), self.biz, 'manager')
        _override(self.biz, 'manager', 'view_leads', False, 'appointments')
        response = self._assign(manager)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['assigned_to'], ['La persona no tiene acceso a Leads.'])

    def test_granted_view_leads_assignable(self):
        viewer = _login(APIClient(), self.biz, 'viewer')
        self.assertEqual(self._assign(viewer).status_code, status.HTTP_400_BAD_REQUEST)
        _override(self.biz, 'viewer', 'view_leads', True, 'appointments')
        response = self._assign(viewer)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['assigned_to']['id'], viewer.pk)

    def test_assignee_evaluated_with_lead_business_overrides_only(self):
        other = _turnos_business(slug=f'ovr-l-o-{uuid.uuid4().hex[:6]}')
        _override(other, 'manager', 'view_leads', False, 'appointments')
        manager = _login(APIClient(), self.biz, 'manager')
        self.assertEqual(self._assign(manager).status_code, status.HTTP_200_OK)
