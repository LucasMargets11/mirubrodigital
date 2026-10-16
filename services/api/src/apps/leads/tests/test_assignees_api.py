"""Personas asignables a Leads (LEADS 05B.1): `GET /api/v1/leads/assignees/`.

El listado y `validate_assigned_to` comparten `services.assignees`; acá se
cubre la regla (membership/usuario activos, `view_leads` efectivo con
overrides), aislamiento entre tenants, HQ → sucursal, el contrato mínimo
(`id` + `display_name`), entitlement, RBAC y la coherencia listado ↔ PATCH.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership, RolePermissionOverride
from apps.appointments.tests.test_customer_core_access import _login, _turnos_business
from apps.business.models import Business
from apps.leads.models import Lead

from .test_crm_api import LIST_URL, LeadApiMixin, _detail_url

User = get_user_model()

ASSIGNEES_URL = f'{LIST_URL}assignees/'


def _override(business, role, enabled, permission='view_leads'):
    return RolePermissionOverride.objects.create(
        business=business, role=role, service='appointments', permission=permission, enabled=enabled,
    )


class AssigneesMixin(LeadApiMixin):

    def _members(self, biz, *specs):
        """Crea miembros sin pasar por el límite de asientos (bulk_create no dispara pre_save).

        Cada spec es `(role, {campos de usuario})`; devuelve los usuarios en orden.
        """
        users = [
            User.objects.create_user(username=f'{role}-{uuid.uuid4().hex[:8]}@example.com', password='x', **fields)
            for role, fields in specs
        ]
        Membership.objects.bulk_create(
            [Membership(user=user, business=biz, role=role) for user, (role, _) in zip(users, specs)]
        )
        return users

    def _assignee_ids(self, client=None):
        response = (client or self.client).get(ASSIGNEES_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row['id'] for row in response.data}


class LeadAssigneesListTests(AssigneesMixin, APITestCase):

    def setUp(self):
        self.biz, self.channel = self._setup_tenant('asg')
        self.lead = self._lead(self.biz, self.channel)
        self.owner = _login(self.client, self.biz, 'owner')

    def test_contract_is_minimal_and_sorted_by_name(self):
        zoe, ana = self._members(
            self.biz, ('manager', {'first_name': 'Zoe', 'last_name': 'Ruiz'}), ('admin', {'first_name': 'ana', 'last_name': 'Paz'}),
        )
        response = self.client.get(ASSIGNEES_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for row in response.data:
            self.assertEqual(set(row), {'id', 'display_name'})
            self.assertNotIn('@', row['display_name'])  # username es el email: nunca se expone
        names = [row['display_name'] for row in response.data]
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertEqual([r['id'] for r in response.data if r['id'] in (zoe.pk, ana.pk)], [ana.pk, zoe.pk])

    def test_owner_admin_manager_listed_viewer_not_by_default(self):
        admin, manager, viewer = self._members(self.biz, ('admin', {}), ('manager', {}), ('viewer', {}))
        ids = self._assignee_ids()
        self.assertEqual(ids, {self.owner.pk, admin.pk, manager.pk})
        self.assertNotIn(viewer.pk, ids)

    def test_viewer_granted_by_override_is_listed(self):
        (viewer,) = self._members(self.biz, ('viewer', {}))
        _override(self.biz, 'viewer', True)
        self.assertIn(viewer.pk, self._assignee_ids())

    def test_manager_revoked_by_override_is_not_listed(self):
        (manager,) = self._members(self.biz, ('manager', {}))
        _override(self.biz, 'manager', False)
        self.assertNotIn(manager.pk, self._assignee_ids())
        # Un override de otro permiso no afecta.
        RolePermissionOverride.objects.all().delete()
        _override(self.biz, 'manager', False, permission='manage_leads')
        self.assertIn(manager.pk, self._assignee_ids())

    def test_inactive_user_and_inactive_membership_excluded(self):
        disabled, inactive, suspended = self._members(self.biz, ('manager', {}), ('manager', {}), ('admin', {}))
        User.objects.filter(pk=disabled.pk).update(is_active=False)
        Membership.objects.filter(user=inactive).update(status=Membership.Status.INACTIVE)
        Membership.objects.filter(user=suspended).update(status=Membership.Status.SUSPENDED)
        self.assertEqual(self._assignee_ids(), {self.owner.pk})

    def test_other_tenant_members_never_listed(self):
        other, _ = self._setup_tenant('asg-other')
        (foreign,) = self._members(other, ('manager', {}))
        _override(other, 'viewer', True)  # overrides de otro Business no se mezclan
        (viewer,) = self._members(self.biz, ('viewer', {}))
        ids = self._assignee_ids()
        self.assertNotIn(foreign.pk, ids)
        self.assertNotIn(viewer.pk, ids)
        # Desde el otro tenant, nadie de este.
        client = APIClient()
        other_owner = _login(client, other, 'owner')
        self.assertEqual(self._assignee_ids(client), {other_owner.pk, foreign.pk})

    def test_listing_matches_patch_validation(self):
        other, _ = self._setup_tenant('asg-coh')
        candidates = self._members(
            self.biz, ('admin', {}), ('manager', {}), ('cashier', {}), ('analyst', {}), ('viewer', {}), ('staff', {}),
            ('manager', {}), ('manager', {}),
        )
        admin, manager, cashier, analyst, granted_viewer, staff, disabled, inactive = candidates
        (foreign,) = self._members(other, ('manager', {}))
        User.objects.filter(pk=disabled.pk).update(is_active=False)
        Membership.objects.filter(user=inactive).update(status=Membership.Status.INACTIVE)
        _override(self.biz, 'viewer', True)  # analyst hereda los defaults de viewer, no sus overrides

        listed = self._assignee_ids()
        everyone = [self.owner, *candidates, foreign]
        for user in everyone:
            with self.subTest(user=user.username):
                Lead.objects.filter(pk=self.lead.pk).update(assigned_to=None)
                response = self.client.patch(_detail_url(self.lead), {'assigned_to': user.pk}, format='json')
                accepted = response.status_code == status.HTTP_200_OK
                self.assertEqual(accepted, user.pk in listed, response.data)
                if not accepted:
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn('assigned_to', response.data)
        self.assertTrue(listed >= {self.owner.pk, admin.pk, manager.pk, granted_viewer.pk})
        self.assertFalse(listed & {cashier.pk, analyst.pk, staff.pk, disabled.pk, inactive.pk, foreign.pk})


class LeadAssigneesHqBranchTests(AssigneesMixin, APITestCase):
    """HQ → sucursal: el owner/admin heredado opera la sucursal pero no es asignable en ella."""

    def setUp(self):
        self.hq = _turnos_business(slug=f'asg-hq-{uuid.uuid4().hex[:6]}')
        # La suscripción V2 de Turnos no se hereda del HQ: la sucursal tiene la suya.
        self.branch = _turnos_business(slug=f'asg-br-{uuid.uuid4().hex[:6]}')
        Business.objects.filter(pk=self.branch.pk).update(parent=self.hq)
        self.branch.refresh_from_db()
        self.branch_lead = Lead.objects.create(business=self.branch)
        self.hq_owner = _login(APIClient(), self.hq, 'owner')
        self.hq_admin, self.hq_manager = self._members(self.hq, ('admin', {}), ('manager', {}))
        self.branch_manager, self.branch_viewer = self._members(self.branch, ('manager', {}), ('viewer', {}))

    def _as(self, user, business):
        client = APIClient()
        client.force_authenticate(user=user)
        client.cookies['bid'] = str(business.id)
        return client

    def test_inherited_owner_and_admin_see_only_direct_branch_members(self):
        for user in (self.hq_owner, self.hq_admin):
            with self.subTest(user=user.username):
                client = self._as(user, self.branch)
                self.assertEqual(self._assignee_ids(client), {self.branch_manager.pk})
                # Y el PATCH acepta exactamente eso: el heredado (ni otro miembro del HQ) no es asignable.
                for candidate in (self.hq_owner, self.hq_admin, self.hq_manager, self.branch_viewer):
                    response = client.patch(_detail_url(self.branch_lead), {'assigned_to': candidate.pk}, format='json')
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                response = client.patch(_detail_url(self.branch_lead), {'assigned_to': self.branch_manager.pk}, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                Lead.objects.filter(pk=self.branch_lead.pk).update(assigned_to=None)

    def test_hq_listing_excludes_branch_members(self):
        ids = self._assignee_ids(self._as(self.hq_owner, self.hq))
        self.assertEqual(ids, {self.hq_owner.pk, self.hq_admin.pk, self.hq_manager.pk})

    def test_branch_member_sees_same_branch_listing(self):
        self.assertEqual(self._assignee_ids(self._as(self.branch_manager, self.branch)), {self.branch_manager.pk})

    def test_branch_overrides_apply_to_branch_members_only(self):
        _override(self.branch, 'viewer', True)
        _override(self.hq, 'manager', False)
        self.assertEqual(
            self._assignee_ids(self._as(self.hq_owner, self.branch)), {self.branch_manager.pk, self.branch_viewer.pk},
        )
        self.assertNotIn(self.hq_manager.pk, self._assignee_ids(self._as(self.hq_owner, self.hq)))


class LeadAssigneesAccessTests(AssigneesMixin, APITestCase):

    def setUp(self):
        self.biz, _ = self._setup_tenant('asg-acc')

    def test_unauthenticated(self):
        self.assertIn(self.client.get(ASSIGNEES_URL).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_view_leads_required(self):
        for role, expected in (('owner', 200), ('admin', 200), ('manager', 200), ('viewer', 403), ('staff', 403)):
            with self.subTest(role=role):
                client = APIClient()
                _login(client, self.biz, role)
                self.assertEqual(client.get(ASSIGNEES_URL).status_code, expected)
                Membership.objects.filter(business=self.biz).exclude(role='owner').delete()

    def test_override_controls_access(self):
        _override(self.biz, 'viewer', True)
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.client.get(ASSIGNEES_URL).status_code, status.HTTP_200_OK)
        client = APIClient()
        Membership.objects.filter(business=self.biz, role='viewer').delete()
        _login(client, self.biz, 'manager')
        _override(self.biz, 'manager', False)
        self.assertEqual(client.get(ASSIGNEES_URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_read_only_endpoint(self):
        _login(self.client, self.biz, 'owner')
        for method in ('post', 'patch', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(ASSIGNEES_URL, {}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_plan_without_entitlement_is_denied(self):
        from apps.business import entitlements as ent_module

        _login(self.client, self.biz, 'owner')
        with mock.patch.dict(ent_module.PLAN_ENTITLEMENTS, {'appointments_base': {'appointments.customers'}}):
            response = self.client.get(ASSIGNEES_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['code'], 'plan_entitlement_required')
        self.assertEqual(response.data['entitlement'], 'appointments.leads')
