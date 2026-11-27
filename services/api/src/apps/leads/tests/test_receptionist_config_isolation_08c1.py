"""PROD-08C.1 — `X-Business-Id` explícito y estricto en la configuración del agente.

Con el header presente, el endpoint del comercio opera solo sobre ese negocio
y con una membership activa; nunca cae en otra membership ni en la cookie
`bid`. Sin header, el contrato de PROD-03B no cambia.
"""
from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import AccessAuditLog, Membership
from apps.leads.models import ReceptionistConfig

from .test_receptionist_config_03a import complete
from .test_receptionist_config_api_03b import TENANT, admin_url, reception_business, staff_client

User = get_user_model()


def header(business_or_id) -> dict:
    value = business_or_id if isinstance(business_or_id, str) else str(getattr(business_or_id, 'id', business_or_id))
    return {'HTTP_X_BUSINESS_ID': value}


class _TwoBusinesses(TestCase):
    """Un usuario owner de A y de B, ambos con Recepcionista y config en versión 1."""

    def setUp(self):
        self.a = reception_business()
        self.b = reception_business()
        self.user = User.objects.create_user(username=f'owner-{uuid.uuid4().hex[:8]}', password='x')
        # bulk_create: el save() de Membership aplica el límite de asientos.
        Membership.objects.bulk_create([
            Membership(user=self.user, business=self.a, role='owner'),
            Membership(user=self.user, business=self.b, role='owner'),
        ])
        ReceptionistConfig.objects.create(business=self.a, **complete(assistant_name='Ana'))
        ReceptionistConfig.objects.create(business=self.b, **complete(assistant_name='Bruno'))
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        # La otra pestaña ya cambió de negocio: la cookie apunta a B.
        self.client.cookies['bid'] = str(self.b.id)
        self.audits_before = AccessAuditLog.objects.filter(entity_type='receptionist_config').count()

    def config(self, business):
        return ReceptionistConfig.objects.get(business=business)

    def snapshot(self):
        return {
            b.id: (c.assistant_name, c.version, c.status)
            for b in (self.a, self.b)
            for c in [self.config(b)]
        }

    def assert_nothing_written(self, before):
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            AccessAuditLog.objects.filter(entity_type='receptionist_config').count(), self.audits_before,
        )

    def assert_denied(self, response, code='business_access_denied'):
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()['code'], code)
        # Nada de la configuración de ningún negocio en la respuesta.
        for name in ('Ana', 'Bruno'):
            self.assertNotIn(name, response.content.decode())


class ValidHeaderTests(_TwoBusinesses):
    def test_header_wins_over_cookie_of_another_business(self):
        response = self.client.get(TENANT, **header(self.a))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['config']['assistant_name'], 'Ana')

    def test_same_version_in_both_businesses_only_touches_the_header_business(self):
        self.assertEqual((self.config(self.a).version, self.config(self.b).version), (1, 1))
        response = self.client.patch(
            TENANT, {'expected_version': 1, 'assistant_name': 'Ana María'}, format='json', **header(self.a),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.config(self.a).assistant_name, self.config(self.a).version), ('Ana María', 2))
        self.assertEqual((self.config(self.b).assistant_name, self.config(self.b).version), ('Bruno', 1))

    def test_status_change_only_touches_the_header_business(self):
        response = self.client.patch(TENANT, {'expected_version': 1, 'status': 'ready'}, format='json', **header(self.a))
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.config(self.a).status, self.config(self.b).status), ('ready', 'draft'))


class LostAccessTests(_TwoBusinesses):
    def _requests(self, target):
        return (
            self.client.get(TENANT, **header(target)),
            self.client.post(TENANT, {}, format='json', **header(target)),
            self.client.patch(TENANT, {'expected_version': 1, 'assistant_name': 'X'}, format='json', **header(target)),
        )

    def test_deleted_membership_is_rejected_without_falling_back(self):
        before = self.snapshot()
        Membership.objects.filter(user=self.user, business=self.a).delete()
        for response in self._requests(self.a):
            self.assert_denied(response)
        # Antes, el fallback resolvía B (cookie / otra membership) con la misma versión.
        self.assert_nothing_written(before)

    def test_suspended_or_inactive_membership_is_rejected(self):
        before = self.snapshot()
        for status in (Membership.Status.SUSPENDED, Membership.Status.INACTIVE):
            Membership.objects.filter(user=self.user, business=self.a).update(status=status)
            with self.subTest(status=status):
                for response in self._requests(self.a):
                    self.assert_denied(response)
        self.assert_nothing_written(before)

    def test_foreign_business_is_rejected(self):
        foreign = reception_business()
        ReceptionistConfig.objects.create(business=foreign, assistant_name='Ajeno')
        before = self.snapshot()
        for response in self._requests(foreign):
            self.assert_denied(response)
            self.assertNotIn('Ajeno', response.content.decode())
        self.assertEqual((self.config(foreign).assistant_name, self.config(foreign).version), ('Ajeno', 1))
        self.assert_nothing_written(before)

    def test_nonexistent_business_is_rejected(self):
        before = self.snapshot()
        for response in self._requests(999_999_999):
            self.assert_denied(response)
        self.assert_nothing_written(before)

    def test_post_with_lost_access_creates_nothing_anywhere(self):
        fresh = reception_business()
        Membership.objects.bulk_create([Membership(user=self.user, business=fresh, role='owner')])
        Membership.objects.filter(user=self.user, business=fresh).delete()
        response = self.client.post(TENANT, complete(), format='json', **header(fresh))
        self.assert_denied(response)
        self.assertFalse(ReceptionistConfig.objects.filter(business=fresh).exists())
        self.assertEqual(ReceptionistConfig.objects.count(), 2)


class InvalidHeaderTests(_TwoBusinesses):
    def test_malformed_ids_are_rejected(self):
        before = self.snapshot()
        for value in ('', 'abc', '0', '-1', f'{self.a.id} ', f' {self.a.id}', f'{self.a.id},{self.b.id}', '1e3', '٣'):
            with self.subTest(value=value):
                for response in (
                    self.client.get(TENANT, **header(value)),
                    self.client.post(TENANT, {}, format='json', **header(value)),
                    self.client.patch(TENANT, {'expected_version': 1, 'assistant_name': 'X'}, format='json', **header(value)),
                ):
                    self.assert_denied(response, 'business_header_invalid')
        self.assert_nothing_written(before)


class CompatibilityTests(_TwoBusinesses):
    def test_without_header_the_previous_contract_is_unchanged(self):
        # Sin header decide la cookie, como en PROD-03B.
        self.assertEqual(self.client.get(TENANT).json()['config']['assistant_name'], 'Bruno')
        self.client.cookies['bid'] = str(self.a.id)
        self.assertEqual(self.client.get(TENANT).json()['config']['assistant_name'], 'Ana')

    def test_permissions_still_apply_with_a_valid_header(self):
        manager = User.objects.create_user(username=f'manager-{uuid.uuid4().hex[:8]}', password='x')
        Membership.objects.bulk_create([Membership(user=manager, business=self.a, role='manager')])
        client = APIClient()
        client.force_authenticate(user=manager)
        self.assertEqual(client.get(TENANT, **header(self.a)).status_code, 403)

    def test_versioning_still_applies_with_a_valid_header(self):
        response = self.client.patch(TENANT, {'expected_version': 5, 'tone': 'formal'}, format='json', **header(self.a))
        self.assertEqual((response.status_code, response.json()['code']), (409, 'version_conflict'))
        self.assertEqual(response.json()['current_version'], 1)

    def test_anonymous_with_header_is_still_unauthenticated(self):
        response = APIClient().get(TENANT, **header(self.a))
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn('Ana', response.content.decode())


class PlatformAdminIndependenceTests(_TwoBusinesses):
    def test_admin_route_ignores_business_header_and_cookie(self):
        admin = staff_client()
        admin.cookies['bid'] = str(self.b.id)
        response = admin.patch(
            admin_url(self.a), {'expected_version': 1, 'assistant_name': 'Ana (admin)'}, format='json',
            **header(self.b),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.config(self.a).assistant_name, 'Ana (admin)')
        self.assertEqual((self.config(self.b).assistant_name, self.config(self.b).version), ('Bruno', 1))
        self.assertEqual(admin.get(admin_url(self.b), **header('abc')).json()['config']['assistant_name'], 'Bruno')
