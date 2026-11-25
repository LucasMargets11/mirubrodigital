"""Permisos y entitlement registrados para Leads (AGENT 02A)."""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.accounts.rbac import APPOINTMENTS_PERMISSIONS, SERVICE_ROLE_PERMISSIONS, permissions_for_service
from apps.accounts.rbac_registry import get_registry
from apps.business.entitlements import (
    ADDON_ENTITLEMENTS,
    APPOINTMENTS_LEADS_ENTITLEMENT,
    PLAN_ENTITLEMENTS,
    get_upgrade_hint,
)

LEAD_PERMISSIONS = ('view_leads', 'manage_leads', 'manage_agent_channels')

EXPECTED = {
    'owner': {'view_leads': True, 'manage_leads': True, 'manage_agent_channels': True},
    'admin': {'view_leads': True, 'manage_leads': True, 'manage_agent_channels': True},
    'manager': {'view_leads': True, 'manage_leads': True, 'manage_agent_channels': False},
    'viewer': {'view_leads': False, 'manage_leads': False, 'manage_agent_channels': False},
    # Rol de Turnos (agenda propia, 7B): sin ningún acceso a Leads.
    'professional': {'view_leads': False, 'manage_leads': False, 'manage_agent_channels': False},
}


class LeadPermissionTests(SimpleTestCase):
    def test_permissions_in_appointments_service(self):
        for perm in LEAD_PERMISSIONS:
            self.assertIn(perm, APPOINTMENTS_PERMISSIONS)

    def test_appointments_roles(self):
        for role, expected in EXPECTED.items():
            perms = permissions_for_service('appointments', role)
            for perm, allowed in expected.items():
                with self.subTest(role=role, perm=perm):
                    self.assertIs(perms[perm], allowed)

    def test_no_new_role(self):
        # Leads no agrega roles: son los de Turnos, todos cubiertos por EXPECTED.
        self.assertEqual(
            set(SERVICE_ROLE_PERMISSIONS['appointments']),
            {'owner', 'admin', 'manager', 'viewer', 'professional'},
        )
        self.assertEqual(set(SERVICE_ROLE_PERMISSIONS['appointments']), set(EXPECTED))

    def test_other_services_do_not_grant_lead_permissions(self):
        # Leads owners: Turnos and, since PROD-02C, Recepcionista IA (test_reception_rbac_02c).
        for service, roles in SERVICE_ROLE_PERMISSIONS.items():
            if service in ('appointments', 'reception'):
                continue
            for role in roles:
                perms = permissions_for_service(service, role)
                for perm in LEAD_PERMISSIONS:
                    with self.subTest(service=service, role=role, perm=perm):
                        self.assertFalse(perms[perm])

    def test_registered_capabilities(self):
        registry = get_registry()
        for perm in LEAD_PERMISSIONS:
            cap = registry.get(perm)
            self.assertIsNotNone(cap, perm)
            self.assertEqual(cap.module, 'Leads')
            self.assertEqual(cap.service, 'appointments')


class LeadEntitlementTests(SimpleTestCase):
    def test_entitlement_code(self):
        self.assertEqual(APPOINTMENTS_LEADS_ENTITLEMENT, 'appointments.leads')

    def test_granted_by_legacy_base_and_canonical_ai_plans(self):
        granting = {plan for plan, entitlements in PLAN_ENTITLEMENTS.items()
                    if APPOINTMENTS_LEADS_ENTITLEMENT in (entitlements or set())}
        self.assertEqual(granting, {'appointments_base', 'appointments_ai'})
        for plan in ('appointments', 'appointments_pro'):
            self.assertNotIn(APPOINTMENTS_LEADS_ENTITLEMENT, PLAN_ENTITLEMENTS[plan])
        for addon, entitlements in ADDON_ENTITLEMENTS.items():
            with self.subTest(addon=addon):
                self.assertNotIn(APPOINTMENTS_LEADS_ENTITLEMENT, entitlements)

    def test_upgrade_hint_points_to_turnos(self):
        self.assertEqual(get_upgrade_hint(APPOINTMENTS_LEADS_ENTITLEMENT), 'Turnos IA')


class LeadsFeatureFlagTests(SimpleTestCase):
    """LEADS 05A: flag de sesión `leads` derivado del entitlement (sin duplicar el plan)."""

    def test_flag_follows_plan_entitlement(self):
        from apps.business.features import FEATURE_KEYS, feature_flags_for_plan

        self.assertIn('leads', FEATURE_KEYS)
        self.assertTrue(feature_flags_for_plan('appointments_base')['leads'])
        self.assertTrue(feature_flags_for_plan('appointments_ai')['leads'])
        for plan in ('appointments', 'appointments_pro'):
            self.assertFalse(feature_flags_for_plan(plan)['leads'])
        for plan in ('starter', 'pro', 'business', 'menu_qr', 'qr_reviews', 'unknown-plan'):
            with self.subTest(plan=plan):
                self.assertFalse(feature_flags_for_plan(plan)['leads'])

    def test_flag_reads_plan_entitlements_live(self):
        from unittest import mock

        from apps.business.features import feature_flags_for_plan

        with mock.patch.dict(PLAN_ENTITLEMENTS, {'appointments_base': {'appointments.customers'}}):
            self.assertFalse(feature_flags_for_plan('appointments_base')['leads'])
