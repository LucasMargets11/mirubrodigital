"""PROD-03B — API de configuración de Recepcionista IA."""
from __future__ import annotations

import threading
import time
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.accounts.models import AccessAuditLog, Membership, RolePermissionOverride
from apps.billing.models import SubscriptionV2
from apps.billing.tests.test_reception_service_02b import _business, _reception, _sub, _superadmin
from apps.leads.models import ReceptionistConfig
from apps.leads.services import receptionist_config as service

from .test_receptionist_config_03a import complete

User = get_user_model()
TENANT = '/api/v1/receptionist-config/'


def admin_url(business) -> str:
    return f'/api/v1/platform-admin/clients/{business.id}/receptionist-config/'


def staff_client(role='superadmin') -> APIClient:
    user = _superadmin()
    if role != 'superadmin':
        user.account_profile.internal_role = role
        user.account_profile.save(update_fields=['internal_role'])
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def member_client(business, role='owner'):
    user = User.objects.create_user(username=f'{role}-{uuid.uuid4().hex[:8]}', password='x')
    # bulk_create: el save() de Membership aplica el límite de asientos
    Membership.objects.bulk_create([Membership(user=user, business=business, role=role)])
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies['bid'] = str(business.id)
    return client, user


def reception_business():
    business = _business()
    _reception(business)
    return business


class _Base(TestCase):
    def setUp(self):
        self.business = reception_business()
        self.owner, self.owner_user = member_client(self.business, 'owner')
        self.admin = staff_client()

    def config(self, business=None):
        return ReceptionistConfig.objects.filter(business=business or self.business).first()


class DraftCreationAndReadTests(_Base):
    def test_get_without_config_returns_null_and_creates_nothing(self):
        for client, url in ((self.owner, TENANT), (self.admin, admin_url(self.business))):
            response = client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'config': None})
            self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIsNone(self.config())
        self.assertFalse(AccessAuditLog.objects.filter(entity_type='receptionist_config').exists())

    def test_empty_post_creates_a_draft(self):
        response = self.owner.post(TENANT, {}, format='json')
        self.assertEqual(response.status_code, 201)
        body = response.json()['config']
        self.assertEqual((body['status'], body['version']), ('draft', 1))
        self.assertIn('assistant_name', body['missing_for_ready'])
        self.assertNotIn('business_hours', body['missing_for_ready'])
        self.assertEqual(self.config().business_id, self.business.id)

    def test_post_with_content_and_second_post_conflicts(self):
        response = self.admin.post(admin_url(self.business), complete(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['config']['assistant_name'], 'Sofía')
        again = self.owner.post(TENANT, {}, format='json')
        self.assertEqual((again.status_code, again.json()['code']), (409, 'receptionist_config_exists'))
        self.assertEqual(ReceptionistConfig.objects.filter(business=self.business).count(), 1)

    def test_owner_reads_and_edits(self):
        self.owner.post(TENANT, complete(), format='json')
        response = self.owner.patch(TENANT, {'expected_version': 1, 'tone': 'formal'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()['config']['tone'], response.json()['config']['version']), ('formal', 2))
        self.assertEqual(self.owner.get(TENANT).json()['config']['tone'], 'formal')

    def test_payload_does_not_duplicate_business_data(self):
        self.owner.post(TENANT, {}, format='json')
        body = self.owner.get(TENANT).json()['config']
        for key in ('business', 'business_id', 'name', 'address', 'timezone', 'whatsapp_phone'):
            self.assertNotIn(key, body)


class ReadyValidationTests(_Base):
    def test_ready_requires_minimum_and_reports_fields(self):
        response = self.owner.post(TENANT, {'status': 'ready', 'assistant_name': 'Sofía'}, format='json')
        self.assertEqual((response.status_code, response.json()['code']), (400, 'validation_error'))
        self.assertIn('status', response.json()['fields'])
        self.assertIsNone(self.config())

    def test_ready_without_hours_is_allowed(self):
        response = self.owner.post(TENANT, {**complete(business_hours=''), 'status': 'ready'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['config']['status'], 'ready')

    def test_patch_to_ready_then_breaking_it_is_rejected(self):
        self.owner.post(TENANT, complete(), format='json')
        ready = self.owner.patch(TENANT, {'expected_version': 1, 'status': 'ready'}, format='json')
        self.assertEqual((ready.status_code, ready.json()['config']['version']), (200, 2))
        broken = self.owner.patch(TENANT, {'expected_version': 2, 'welcome_message': ''}, format='json')
        self.assertEqual(broken.status_code, 400)
        self.assertEqual((self.config().version, self.config().status), (2, 'ready'))

    def test_model_validations_are_reused(self):
        self.owner.post(TENANT, {}, format='json')
        for payload in (
            {'assistant_name': 'x' * 81},
            {'tone': 'aggressive'},
            {'services': [{'name': 'Corte', 'price': 1}]},
            {'faqs': [{'question': '¿?'}]},
            {'custom_instructions': 'clave sk-proj-ABCDEFGHIJKLMNOPQRSTUV'},
        ):
            with self.subTest(payload=payload):
                response = self.owner.patch(TENANT, {'expected_version': 1, **payload}, format='json')
                self.assertEqual((response.status_code, response.json()['code']), (400, 'validation_error'))
        self.assertEqual(self.config().version, 1)

    def test_strict_json_types(self):
        self.owner.post(TENANT, {}, format='json')
        for payload in ({'assistant_name': 123}, {'services': 'Corte'}, {'status': None}):
            with self.subTest(payload=payload):
                response = self.owner.patch(TENANT, {'expected_version': 1, **payload}, format='json')
                self.assertEqual((response.status_code, response.json()['code']), (400, 'validation_error'))


class VersionTests(_Base):
    def setUp(self):
        super().setUp()
        self.owner.post(TENANT, complete(), format='json')

    def test_expected_version_is_required_and_strict(self):
        for payload in ({'tone': 'formal'}, {'expected_version': '1'}, {'expected_version': True},
                        {'expected_version': 0}):
            with self.subTest(payload=payload):
                response = self.owner.patch(TENANT, payload, format='json')
                self.assertEqual((response.status_code, response.json()['code']), (400, 'expected_version_required'))

    def test_stale_version_is_409_with_current_version(self):
        self.owner.patch(TENANT, {'expected_version': 1, 'tone': 'formal'}, format='json')
        stale = self.admin.patch(admin_url(self.business), {'expected_version': 1, 'tone': 'warm'}, format='json')
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json(), {
            'code': 'version_conflict', 'detail': 'La configuración cambió; volvé a leerla.', 'current_version': 2,
        })
        self.assertEqual(self.config().tone, 'formal')

    def test_no_op_write_keeps_version_and_writes_no_audit(self):
        before = AccessAuditLog.objects.count()
        response = self.owner.patch(TENANT, {'expected_version': 1, 'tone': 'warm'}, format='json')
        self.assertEqual((response.status_code, response.json()['config']['version']), (200, 1))
        self.assertEqual(AccessAuditLog.objects.count(), before)

    def test_status_change_increments(self):
        response = self.owner.patch(TENANT, {'expected_version': 1, 'status': 'ready'}, format='json')
        self.assertEqual(response.json()['config']['version'], 2)

    def test_patch_without_config_is_404(self):
        ReceptionistConfig.objects.all().delete()
        response = self.owner.patch(TENANT, {'expected_version': 1, 'tone': 'formal'}, format='json')
        self.assertEqual((response.status_code, response.json()['code']), (404, 'receptionist_config_not_found'))
        self.assertIsNone(self.config())


class ProtectedFieldsTests(_Base):
    def setUp(self):
        super().setUp()
        self.owner.post(TENANT, {}, format='json')

    def test_protected_fields_rejected(self):
        other = reception_business()
        for key, value in (
            ('business', other.id), ('business_id', other.id), ('version', 99), ('id', str(uuid.uuid4())),
            ('created_at', '2020-01-01T00:00:00Z'),
        ):
            for client, url in ((self.owner, TENANT), (self.admin, admin_url(self.business))):
                with self.subTest(key=key, url=url):
                    response = client.patch(url, {'expected_version': 1, key: value}, format='json')
                    self.assertEqual((response.status_code, response.json()['code']), (400, 'protected_fields'))
        config = self.config()
        self.assertEqual((config.business_id, config.version), (self.business.id, 1))

    def test_capabilities_and_credentials_are_unknown_fields(self):
        for key in ('agenda_enabled', 'permissions', 'plan', 'usage_tier', 'included_sessions', 'api_key',
                    'token', 'secret', 'phone_number_id', 'agent_instance', 'is_active'):
            with self.subTest(key=key):
                response = self.owner.patch(TENANT, {'expected_version': 1, key: True}, format='json')
                self.assertEqual((response.status_code, response.json()['code']), (400, 'unknown_fields'))
                self.assertIn(key, response.json()['fields'])
        create = self.admin.post(admin_url(reception_business()), {'plan': 'x'}, format='json')
        self.assertEqual(create.json()['code'], 'unknown_fields')

    def test_expected_version_not_accepted_on_create(self):
        business = reception_business()
        response = self.admin.post(admin_url(business), {'expected_version': 1}, format='json')
        self.assertEqual(response.json()['code'], 'unknown_fields')

    def test_non_object_body(self):
        response = self.owner.patch(TENANT, [1, 2], format='json')
        self.assertEqual((response.status_code, response.json()['code']), (400, 'invalid_request'))


class IsolationTests(_Base):
    def test_tenant_ignores_foreign_business_hints(self):
        other = reception_business()
        member_client(other, 'owner')
        response = self.owner.post(f'{TENANT}?business_id={other.id}', {}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(self.config())
        self.assertIsNone(self.config(other))

    def test_member_of_a_cannot_reach_b_with_cookie(self):
        other = reception_business()
        ReceptionistConfig.objects.create(business=other, assistant_name='Bruno')
        # Un `bid` ajeno nunca selecciona ese negocio: el contexto sale de la
        # membership (cae al propio) y la config de B no se ve ni se edita.
        self.owner.cookies['bid'] = str(other.id)
        self.assertEqual(self.owner.get(TENANT).json(), {'config': None})
        self.assertEqual(self.owner.post(TENANT, {}, format='json').status_code, 201)
        self.assertEqual(self.config().business_id, self.business.id)
        self.assertEqual((self.config(other).assistant_name, self.config(other).version), ('Bruno', 1))

    def test_edits_never_touch_another_business(self):
        other = reception_business()
        self.admin.post(admin_url(other), complete(assistant_name='Bruno'), format='json')
        self.owner.post(TENANT, complete(assistant_name='Ana'), format='json')
        self.owner.patch(TENANT, {'expected_version': 1, 'assistant_name': 'Ana María'}, format='json')
        self.assertEqual((self.config(other).assistant_name, self.config(other).version), ('Bruno', 1))


class PermissionTests(_Base):
    def test_tenant_roles(self):
        for role, expected in (('admin', 200), ('manager', 403), ('viewer', 403)):
            client, _ = member_client(self.business, role)
            with self.subTest(role=role):
                self.assertEqual(client.get(TENANT).status_code, expected)
                self.assertEqual(client.post(TENANT, {}, format='json').status_code,
                                 201 if expected == 200 and role == 'admin' else expected)

    def test_permission_override_can_revoke_owner_admin_access(self):
        RolePermissionOverride.objects.create(
            business=self.business, role='admin', service='reception', permission='manage_agent_channels',
            enabled=False,
        )
        client, _ = member_client(self.business, 'admin')
        self.assertEqual(client.get(TENANT).status_code, 403)

    def test_tenant_requires_reception_ai(self):
        for label, make in (
            ('turnos_ia', lambda b: _sub(b, 'appointments', 'appointments_ai', 'ai_300')),
            ('gestion', lambda b: _sub(b, 'gestion', 'pro')),
            ('reception_suspended', lambda b: _reception(b, status=SubscriptionV2.Status.SUSPENDED)),
        ):
            with self.subTest(label=label):
                business = _business(service='appointments' if label == 'turnos_ia' else 'reception')
                make(business)
                client, _ = member_client(business, 'owner')
                self.assertEqual(client.get(TENANT).status_code, 403)
                self.assertEqual(client.post(TENANT, {}, format='json').status_code, 403)
                self.assertIsNone(self.config(business))

    def test_anonymous_and_platform_staff_without_membership(self):
        self.assertIn(APIClient().get(TENANT).status_code, (401, 403))
        self.assertIn(APIClient().get(admin_url(self.business)).status_code, (401, 403))

    def test_admin_roles(self):
        for role, expected in (('operations', 200), ('support_agent', 403), ('content_admin', 403)):
            with self.subTest(role=role):
                self.assertEqual(staff_client(role).get(admin_url(self.business)).status_code, expected)

    def test_merchant_owner_is_never_platform_admin(self):
        self.assertEqual(self.owner.get(admin_url(self.business)).status_code, 403)

    def test_admin_client_rules(self):
        branch = _business()
        branch.parent = self.business
        branch.save(update_fields=['parent'])
        without_reception = _business()
        _sub(without_reception, 'gestion', 'pro')
        canceled = _business()
        _reception(canceled, status=SubscriptionV2.Status.CANCELED)
        for business in (branch, without_reception, canceled):
            with self.subTest(business=business.slug):
                response = self.admin.post(admin_url(business), {}, format='json')
                self.assertEqual((response.status_code, response.json()['code']), (404, 'client_not_found'))
                self.assertIsNone(self.config(business))
        self.assertEqual(self.admin.get('/api/v1/platform-admin/clients/999999/receptionist-config/').status_code, 404)

    def test_admin_can_prepare_a_suspended_reception_client(self):
        business = _business()
        _reception(business, status=SubscriptionV2.Status.SUSPENDED)
        self.assertEqual(self.admin.post(admin_url(business), {}, format='json').status_code, 201)


class AuditTests(_Base):
    def logs(self):
        return list(AccessAuditLog.objects.filter(entity_type='receptionist_config').order_by('created_at', 'id'))

    def test_create_and_update_are_audited_without_content(self):
        secret_text = 'INSTRUCCION-PRIVADA-123'
        self.owner.post(TENANT, complete(custom_instructions=secret_text), format='json')
        self.admin.patch(
            admin_url(self.business),
            {'expected_version': 1, 'faqs': [{'question': '¿Abren?', 'answer': 'RESPUESTA-PRIVADA'}],
             'status': 'ready'},
            format='json',
        )
        created, updated = self.logs()
        self.assertEqual(
            (created.action, created.actor, created.business_id), ('RECEPTIONIST_CONFIG_CREATED', self.owner_user,
                                                                  self.business.id),
        )
        self.assertEqual(created.details['source'], 'business')
        self.assertEqual(updated.action, 'RECEPTIONIST_CONFIG_UPDATED')
        self.assertEqual(updated.details, {
            'source': 'platform_admin', 'version': 2, 'status': 'ready', 'changed_fields': ['faqs', 'status'],
            'previous_version': 1, 'automatic_attention_enabled': False,
        })
        dump = str([log.details for log in self.logs()])
        for private in (secret_text, 'RESPUESTA-PRIVADA', 'Sofía', '¿Abren?'):
            self.assertNotIn(private, dump)

    def test_audit_failure_rolls_back_create(self):
        with patch.object(service, 'record_platform_action', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                service.create_receptionist_config(
                    self.business, complete(), actor=self.owner_user, source=service.SOURCE_BUSINESS,
                )
        self.assertIsNone(self.config())

    def test_audit_failure_rolls_back_update(self):
        self.owner.post(TENANT, complete(), format='json')
        with patch.object(service, 'record_platform_action', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                service.update_receptionist_config(
                    self.business, {'expected_version': 1, 'assistant_name': 'Otra'},
                    actor=self.owner_user, source=service.SOURCE_BUSINESS,
                )
        config = self.config()
        self.assertEqual((config.assistant_name, config.version), ('Sofía', 1))
        self.assertEqual(len(self.logs()), 1)


class ConcurrencyTests(TransactionTestCase):
    """Dos escrituras simultáneas reales (threads, conexiones separadas)."""

    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        self.business = reception_business()
        self.actor = _superadmin()

    def _race(self, call):
        results, barrier = [], threading.Barrier(2)
        real_audit = service.record_platform_action

        def slow_audit(**kwargs):
            # El primero retiene el lock un momento: el segundo llega a esperar.
            time.sleep(0.3)
            return real_audit(**kwargs)

        def worker(payload):
            try:
                barrier.wait()
                results.append(('ok', call(payload)))
            except service.ReceptionistConfigError as error:
                results.append((error.code, None))
            finally:
                connection.close()

        with patch.object(service, 'record_platform_action', side_effect=slow_audit):
            threads = [threading.Thread(target=worker, args=(p,)) for p in self.payloads]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
        return sorted(code for code, _ in results)

    def test_concurrent_creation_creates_exactly_one(self):
        self.payloads = [complete(assistant_name='Ana'), complete(assistant_name='Bruno')]
        codes = self._race(lambda data: service.create_receptionist_config(
            self.business, data, actor=self.actor, source=service.SOURCE_PLATFORM_ADMIN,
        ))
        self.assertEqual(codes, ['ok', 'receptionist_config_exists'])
        self.assertEqual(ReceptionistConfig.objects.filter(business=self.business).count(), 1)
        self.assertEqual(
            AccessAuditLog.objects.filter(action='RECEPTIONIST_CONFIG_CREATED', business=self.business).count(), 1,
        )

    def test_concurrent_edits_with_same_version_one_wins(self):
        service.create_receptionist_config(
            self.business, complete(), actor=self.actor, source=service.SOURCE_PLATFORM_ADMIN,
        )
        self.payloads = [
            {'expected_version': 1, 'assistant_name': 'Ana'},
            {'expected_version': 1, 'assistant_name': 'Bruno'},
        ]
        codes = self._race(lambda data: service.update_receptionist_config(
            self.business, data, actor=self.actor, source=service.SOURCE_PLATFORM_ADMIN,
        ))
        self.assertEqual(codes, ['ok', 'version_conflict'])
        config = ReceptionistConfig.objects.get(business=self.business)
        self.assertEqual(config.version, 2)
        self.assertIn(config.assistant_name, ('Ana', 'Bruno'))
        self.assertEqual(
            AccessAuditLog.objects.filter(action='RECEPTIONIST_CONFIG_UPDATED', business=self.business).count(), 1,
        )
