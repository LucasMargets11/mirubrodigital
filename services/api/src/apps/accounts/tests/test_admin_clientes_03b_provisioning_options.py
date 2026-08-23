"""
accounts/tests/test_admin_clientes_03b_provisioning_options.py

ADMIN-CLIENTES 03B — GET /api/v1/platform-admin/clients/provisioning-options/

Read-only endpoint. No writes, no Mercado Pago, no auditing. Response is
built exclusively from the same real rules grant_complimentary_access()
uses (Plan.plan_status='active' + canonical_pricing vertical mapping) — no
duplicated compatibility matrix is asserted against here; every assertion
is checked against the real resolver (Plan queryset + canonical_pricing +
_check_plan_service_compatibility).

Test matrix:
  1.  Superadmin authenticated -> 200.
  2.  Unauthenticated -> 401/403.
  3.  Normal user (no platform_staff) -> 403.
  4.  operations -> 403.
  5.  support_agent -> 403.
  6.  content_admin -> 403.
  7.  Response contains only supported services (per canonical resolver).
  8.  Each service contains only active+compatible plans.
  9.  Inactive plan excluded.
  10. Active but incompatible (no canonical pricing entry) plan excluded.
  11. Service with zero compatible plans is absent entirely.
  12. 'restaurante' vertical excluded (no canonical relation yet).
  13. Returned codes are accepted by the same resolver grant_complimentary_access() uses.
  14. Deterministic ordering (services and plans).
  15. No sensitive/Mercado Pago fields in the response.
  16. No DB rows created (Business/Membership/SubscriptionV2/AccessAuditLog counts unchanged).
  17. Mercado Pago is never called.
  18. Route does not collide with /clients/<business_id>/.
  19. GET /clients/ still allows superadmin and operations (regression).
  20. POST /clients/ still exclusive to superadmin (regression).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import AccessAuditLog
from apps.billing.complimentary_access_service import (
    PlanServiceMismatchError,
    _check_plan_service_compatibility,
)
from apps.billing.models import Plan, SubscriptionV2
from apps.business.models import Business

User = get_user_model()
URL = '/api/v1/platform-admin/clients/provisioning-options/'
CLIENTS_URL = '/api/v1/platform-admin/clients/'


def _make_user(*, role=None, platform_staff=False, active=True, email=None):
    email = email or f'user-{uuid.uuid4().hex}@example.com'
    user = User.objects.create_user(
        username=f'username-{uuid.uuid4().hex}',
        email=email,
        password='SecurePass123!',
        is_active=active,
    )
    profile = user.account_profile
    profile.is_platform_staff = platform_staff
    profile.internal_role = role
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    user.refresh_from_db()
    return user


def _make_plan(code, name, plan_status='active'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'price': Decimal('50000.00'),
            'interval': 'monthly',
            'currency': 'ARS',
            'frequency': 1,
            'frequency_type': 'months',
            'plan_status': plan_status,
        },
    )
    return plan


class AdminClientProvisioningOptionsPermissionTests(TestCase):
    def setUp(self):
        self.superadmin = _make_user(role='superadmin', platform_staff=True)
        _make_plan('gestion_pro', 'Gestión Pro')

    def _get(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client.get(URL)

    def test_01_superadmin_gets_200(self):
        self.assertEqual(self._get(self.superadmin).status_code, 200)

    def test_02_unauthenticated_is_rejected(self):
        self.assertIn(self._get(None).status_code, (401, 403))

    def test_03_normal_user_is_rejected(self):
        normal = _make_user()
        self.assertEqual(self._get(normal).status_code, 403)

    def test_04_operations_is_rejected(self):
        operations = _make_user(role='operations', platform_staff=True)
        self.assertEqual(self._get(operations).status_code, 403)

    def test_05_support_agent_is_rejected(self):
        support = _make_user(role='support_agent', platform_staff=True)
        self.assertEqual(self._get(support).status_code, 403)

    def test_06_content_admin_is_rejected(self):
        content = _make_user(role='content_admin', platform_staff=True)
        self.assertEqual(self._get(content).status_code, 403)


class AdminClientProvisioningOptionsContentTests(TestCase):
    def setUp(self):
        self.superadmin = _make_user(role='superadmin', platform_staff=True)
        # Real canonical, compatible, active plans (one per supported vertical).
        _make_plan('gestion_pro', 'Gestión Pro')
        _make_plan('gestion_start', 'Starter')
        _make_plan('menu_qr_basico', 'Lite')
        _make_plan('qr_reviews_base', 'Reseñas Base')
        # Inactive plan for an otherwise-compatible vertical — must be excluded.
        _make_plan('gestion_business', 'Business', plan_status='inactive')
        # Active but with no canonical pricing entry (legacy restaurante plan
        # code, per generated/pricing.json — no 'restaurante' product/vertical
        # exists there) — must be excluded.
        _make_plan('resto_basic', 'Restaurante Básico')

    def _get(self):
        client = APIClient()
        client.force_authenticate(user=self.superadmin)
        return client.get(URL)

    def _services_by_value(self, payload):
        return {svc['value']: svc for svc in payload['services']}

    def test_07_response_contains_only_supported_services(self):
        response = self._get()
        services = self._services_by_value(response.data)
        self.assertEqual(set(services), {'gestion', 'menu_qr', 'qr_reviews'})

    def test_08_each_service_has_only_active_compatible_plans(self):
        # Real seed migrations may pre-populate additional active/compatible
        # plans (e.g. qr_reviews_pro) — assert our fixtures are present and
        # excluded plans stay excluded, rather than an exact-set equality
        # that would be brittle against other real, canonical seed rows.
        response = self._get()
        services = self._services_by_value(response.data)
        gestion_codes = {p['code'] for p in services['gestion']['plans']}
        self.assertTrue({'gestion_pro', 'gestion_start'}.issubset(gestion_codes))
        menu_qr_codes = {p['code'] for p in services['menu_qr']['plans']}
        self.assertIn('menu_qr_basico', menu_qr_codes)
        qr_reviews_codes = {p['code'] for p in services['qr_reviews']['plans']}
        self.assertIn('qr_reviews_base', qr_reviews_codes)
        for svc in services.values():
            for plan in svc['plans']:
                self.assertTrue(
                    Plan.objects.filter(code=plan['code'], plan_status='active').exists()
                )


    def test_09_inactive_plan_is_excluded(self):
        response = self._get()
        all_codes = {
            p['code']
            for svc in response.data['services']
            for p in svc['plans']
        }
        self.assertNotIn('gestion_business', all_codes)

    def test_10_active_but_incompatible_plan_is_excluded(self):
        response = self._get()
        all_codes = {
            p['code']
            for svc in response.data['services']
            for p in svc['plans']
        }
        self.assertNotIn('resto_basic', all_codes)

    def test_11_service_without_compatible_plans_is_absent(self):
        # No plan in this suite maps to 'restaurante', 'menu_qr_visual' or
        # 'menu_qr_marca' — none of them should appear as a service key.
        response = self._get()
        services = self._services_by_value(response.data)
        self.assertNotIn('menu_qr_visual', services)
        self.assertNotIn('menu_qr_marca', services)

    def test_12_restaurante_vertical_is_excluded(self):
        response = self._get()
        services = self._services_by_value(response.data)
        self.assertNotIn('restaurante', services)

    def test_13_returned_codes_are_accepted_by_canonical_resolver(self):
        response = self._get()
        for svc in response.data['services']:
            for plan in svc['plans']:
                self.assertTrue(
                    Plan.objects.filter(code=plan['code'], plan_status='active').exists()
                )
                # Must not raise — same helper grant_complimentary_access() calls.
                _check_plan_service_compatibility(plan['code'], svc['value'])

    def test_14_ordering_is_deterministic(self):
        first = self._get().data
        second = self._get().data
        self.assertEqual(
            [s['value'] for s in first['services']],
            [s['value'] for s in second['services']],
        )
        for s1, s2 in zip(first['services'], second['services']):
            self.assertEqual(
                [p['code'] for p in s1['plans']],
                [p['code'] for p in s2['plans']],
            )
        # Explicitly deterministic (sorted) service and plan order.
        values = [s['value'] for s in first['services']]
        self.assertEqual(values, sorted(values))
        for svc in first['services']:
            codes = [p['code'] for p in svc['plans']]
            self.assertEqual(codes, sorted(codes))

    def test_15_no_sensitive_or_mercadopago_fields(self):
        response = self._get()
        payload_str = str(response.data)
        for forbidden in ('mp_preapproval_plan_id', 'price', 'entitlement', 'secret', 'mercadopago'):
            self.assertNotIn(forbidden, payload_str.lower())
        for svc in response.data['services']:
            self.assertEqual(set(svc.keys()), {'value', 'label', 'plans'})
            for plan in svc['plans']:
                self.assertEqual(set(plan.keys()), {'code', 'name'})

    def test_16_no_rows_created(self):
        biz_before = Business.objects.count()
        sub_before = SubscriptionV2.objects.count()
        audit_before = AccessAuditLog.objects.count()

        self._get()

        self.assertEqual(Business.objects.count(), biz_before)
        self.assertEqual(SubscriptionV2.objects.count(), sub_before)
        self.assertEqual(AccessAuditLog.objects.count(), audit_before)

    @patch('mercadopago.SDK')
    def test_17_mercadopago_is_never_called(self, mocked_sdk):
        self._get()
        mocked_sdk.assert_not_called()


class AdminClientProvisioningOptionsRouteTests(TestCase):
    def setUp(self):
        self.superadmin = _make_user(role='superadmin', platform_staff=True)
        self.operations = _make_user(role='operations', platform_staff=True)

    def test_18_route_does_not_collide_with_client_detail(self):
        client = APIClient()
        client.force_authenticate(user=self.superadmin)

        options_response = client.get(URL)
        self.assertEqual(options_response.status_code, 200)
        self.assertIn('services', options_response.data)

        # A real, unrelated business id still resolves via the detail view.
        biz = Business.objects.create(name='Detail Biz', parent=None, service_type='gestion')
        detail_response = client.get(f'{CLIENTS_URL}{biz.id}/')
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotIn('services', detail_response.data)

    def test_19_clients_list_still_allows_superadmin_and_operations(self):
        client = APIClient()
        client.force_authenticate(user=self.superadmin)
        self.assertEqual(client.get(CLIENTS_URL).status_code, 200)

        client.force_authenticate(user=self.operations)
        self.assertEqual(client.get(CLIENTS_URL).status_code, 200)

    def test_20_clients_post_still_exclusive_to_superadmin(self):
        client = APIClient()
        client.force_authenticate(user=self.operations)
        response = client.post(CLIENTS_URL, {}, format='json')
        self.assertEqual(response.status_code, 403)
