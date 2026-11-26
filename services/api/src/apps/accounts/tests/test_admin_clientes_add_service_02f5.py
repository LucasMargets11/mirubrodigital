"""PROD-02F5 — Incorporación de servicios a comercios existentes.

POST /api/v1/platform-admin/clients/<id>/services/ agrega UN servicio
bonificado a un Business HQ existente sin tocar su identidad, estado global,
propietario, usuarios, overrides, clientes ni suscripciones previas.
Recepcionista ⟂ Turnos IA en ambos sentidos; altas IA que reiniciarían un
cupo ya contado se rechazan; todo en una transacción con auditoría obligatoria.
"""
from __future__ import annotations

import threading
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.admin_client_provisioning_service import (
    ActiveComplimentarySubscriptionConflictError,
    ComplimentaryIncompatibleAIServiceError,
)
from apps.accounts.admin_client_service_addition import add_service_to_client
from apps.accounts.models import AccessAuditLog, Membership, RolePermissionOverride
from apps.accounts.tests.test_admin_clientes_04c_google_preauthorized import _ensure_plan
from apps.accounts.tests.test_admin_clientes_reception_provisioning_02f2 import _Base, _staff
from apps.appointments.models import AppointmentAIUsageSession
from apps.billing import canonical_pricing
from apps.billing.complimentary_access_service import grant_complimentary_access
from apps.billing.models import (
    PaymentAttempt,
    ReceptionAIUsagePolicy,
    ReceptionAIUsagePolicyChange,
    SubscriptionV2,
)
from apps.billing.services.ai_source import RECEPTION_SOURCE, resolve_ai_source
from apps.business.models import Business
from apps.customers.models import Customer
from apps.leads.models import AgentChannel, AgentCredential, AgentInstance

from django.contrib.auth import get_user_model

User = get_user_model()


def services_url(business_id):
    return f'/api/v1/platform-admin/clients/{business_id}/services/'


def _gestion_client(status='active'):
    """An existing Gestión client with owner, staff, overrides, customers and a paid subscription."""
    business = Business.objects.create(
        name='Ferretería Existente', slug=f'ferr-{uuid.uuid4().hex[:8]}', status=status,
        service_type='gestion', default_service='gestion',
    )
    owner = User.objects.create_user(username=f'own-{uuid.uuid4().hex[:6]}', email=f'{uuid.uuid4().hex[:6]}@x.test')
    Membership.objects.create(user=owner, business=business, role='owner')
    manager = User.objects.create_user(username=f'mgr-{uuid.uuid4().hex[:6]}')
    Membership.objects.bulk_create([Membership(user=manager, business=business, role='manager',
                                               permissions={'can_void_order': True})])
    RolePermissionOverride.objects.create(business=business, role='manager', service='gestion',
                                          permission='view_reports', enabled=False)
    Customer.objects.create(business=business, name='Cliente Fiel')
    now = timezone.now()
    SubscriptionV2.objects.create(
        business=business, service_type='gestion', plan_code='gestion_pro', provider='mercadopago',
        provider_sub_id=f'pre-{uuid.uuid4().hex}', external_reference=f'SUB-{uuid.uuid4()}', status='active', is_active=True,
        current_period_start=now - timedelta(days=10), current_period_end=now + timedelta(days=20),
    )
    return business


def _snapshot(business):
    business.refresh_from_db()
    return {
        'business': (business.name, business.slug, business.status, business.service_type,
                     business.default_service, business.parent_id, business.activated_at, business.suspended_at),
        'memberships': sorted(Membership.objects.filter(business=business)
                              .values_list('user_id', 'role', 'status', 'permissions')),
        'overrides': sorted(RolePermissionOverride.objects.filter(business=business)
                            .values_list('role', 'service', 'permission', 'enabled')),
        'customers': sorted(Customer.objects.filter(business=business).values_list('pk', 'name')),
        'subscriptions': sorted(
            (str(pk), *rest) for pk, *rest in SubscriptionV2.objects.filter(business=business).values_list(
                'pk', 'service_type', 'plan_code', 'usage_tier', 'provider', 'provider_sub_id', 'status',
                'is_active', 'current_period_start', 'current_period_end')
        ),
        'users': User.objects.count(),
    }


class _AddBase(_Base):

    def setUp(self):
        super().setUp()
        _ensure_plan('gestion_pro')

    def service_payload(self, **overrides):
        data = {
            'service_type': 'reception', 'plan_code': 'reception', 'usage_tier': 'reception_300',
            'complimentary_start': self.starts_at.isoformat(), 'complimentary_end': self.ends_at.isoformat(),
            'grant_reason': 'Suma Recepcionista IA',
        }
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not ...}

    def add(self, business, client=None, **overrides):
        return (client or self.client).post(services_url(business.pk), self.service_payload(**overrides), format='json')

    def assert_unchanged_except_new(self, before, business, new_sub_ids):
        after = _snapshot(business)
        added = [row for row in after['subscriptions'] if row[0] in new_sub_ids]
        self.assertEqual(sorted(r for r in after.pop('subscriptions') if r[0] not in new_sub_ids),
                         before.pop('subscriptions'))
        self.assertEqual(after, before)
        return added


class AddServiceSuccessTests(_AddBase):

    def test_gestion_active_plus_reception_fixed(self):
        business = _gestion_client()
        before = _snapshot(business)
        response = self.add(business)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(set(response.data), {'business', 'subscription', 'custom_policy'})
        self.assertEqual(response.data['business'], {
            'id': business.pk, 'status': 'active', 'service_type': 'gestion', 'default_service': 'gestion',
        })
        sub = response.data['subscription']
        self.assertEqual(set(sub), {'id', 'service_type', 'plan_code', 'usage_tier', 'provider', 'status',
                                    'current_period_start', 'current_period_end'})
        self.assertEqual((sub['service_type'], sub['plan_code'], sub['usage_tier'], sub['provider'], sub['status']),
                         ('reception', 'reception', 'reception_300', 'manual', 'trialing'))
        self.assertIsNone(response.data['custom_policy'])
        self.assert_unchanged_except_new(before, business, {sub['id']})
        # No agents, channels or credentials; no payment artifacts
        self.assertFalse(AgentInstance.objects.exists() or AgentChannel.objects.exists() or AgentCredential.objects.exists())
        self.assertFalse(PaymentAttempt.objects.filter(subscription__business=business).exists())
        # The Business can now consume Recepcionista as its AI source
        self.assertEqual(resolve_ai_source(business, at=timezone.now()).source, RECEPTION_SOURCE)
        log = AccessAuditLog.objects.get(action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED', business=business)
        self.assertEqual(log.actor_id, self.admin.pk)
        self.assertEqual({k: log.details[k] for k in ('operation', 'subscription_id', 'service_type', 'plan_code',
                                                       'usage_tier', 'custom_included_sessions', 'reason',
                                                       'business_status')},
                         {'operation': 'client_service_added', 'subscription_id': sub['id'],
                          'service_type': 'reception', 'plan_code': 'reception', 'usage_tier': 'reception_300',
                          'custom_included_sessions': None, 'reason': 'Suma Recepcionista IA',
                          'business_status': 'active'})
        self.assertIn('current_period_start', log.details)
        self.assertIn('current_period_end', log.details)
        self.assertEqual(AccessAuditLog.objects.filter(business=business).count(), 1)

    def test_gestion_active_plus_reception_custom(self):
        business = _gestion_client()
        before = _snapshot(business)
        response = self.add(business, usage_tier='reception_custom', custom_included_sessions=60)
        self.assertEqual(response.status_code, 201, response.data)
        sub = SubscriptionV2.objects.get(pk=response.data['subscription']['id'])
        policy = ReceptionAIUsagePolicy.objects.get(subscription=sub)
        self.assertEqual(policy.included_sessions, 60)
        self.assertEqual(response.data['custom_policy']['id'], str(policy.pk))
        self.assertEqual(response.data['custom_policy']['included_sessions'], 60)
        self.assertTrue(ReceptionAIUsagePolicyChange.objects.filter(policy=policy, action='created').exists())
        log = AccessAuditLog.objects.get(action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED', business=business)
        self.assertEqual((log.details['custom_included_sessions'], log.details['custom_policy_id']), (60, str(policy.pk)))
        self.assert_unchanged_except_new(before, business, {str(sub.pk)})

    def test_reception_coexists_with_turnos_base_and_pro_in_both_orders(self):
        for plan in ('appointments', 'appointments_pro'):
            with self.subTest(plan=plan, order='reception first'):
                business = _gestion_client()
                self.assertEqual(self.add(business).status_code, 201)
                response = self.add(business, service_type='appointments', plan_code=plan, usage_tier=...)
                self.assertEqual(response.status_code, 201, response.data)
            with self.subTest(plan=plan, order='turnos first'):
                business = _gestion_client()
                self.assertEqual(self.add(business, service_type='appointments', plan_code=plan,
                                          usage_tier=...).status_code, 201)
                self.assertEqual(self.add(business).status_code, 201)
                self.assertEqual(SubscriptionV2.objects.filter(business=business).exclude(status='canceled').count(), 3)

    def test_trialing_business_stays_trialing_and_keeps_its_principal_service(self):
        business = _gestion_client(status='trialing')
        response = self.add(business)
        self.assertEqual(response.status_code, 201, response.data)
        business.refresh_from_db()
        self.assertEqual((business.status, business.service_type, business.default_service),
                         ('trialing', 'gestion', 'gestion'))

    def test_future_benefit_is_recorded_without_touching_the_business(self):
        business = _gestion_client()
        start = timezone.now().replace(microsecond=0) + timedelta(days=10)
        before = _snapshot(business)
        response = self.add(business, complimentary_start=start.isoformat(),
                            complimentary_end=(start + timedelta(days=90)).isoformat())
        self.assertEqual(response.status_code, 201, response.data)
        sub = SubscriptionV2.objects.get(pk=response.data['subscription']['id'])
        self.assertEqual(sub.current_period_start, start)
        self.assertIsNone(resolve_ai_source(business, at=timezone.now()).subscription)
        self.assertEqual(resolve_ai_source(business, at=start + timedelta(hours=1)).source, RECEPTION_SOURCE)
        self.assert_unchanged_except_new(before, business, {str(sub.pk)})

    def test_canceled_subscription_is_never_reused(self):
        business = _gestion_client()
        first = self.add(business, usage_tier='reception_custom', custom_included_sessions=30)
        old = SubscriptionV2.objects.get(pk=first.data['subscription']['id'])
        old_policy = ReceptionAIUsagePolicy.objects.get(subscription=old)
        SubscriptionV2.objects.filter(pk=old.pk).update(status='canceled', is_active=False)
        response = self.add(business, usage_tier='reception_custom', custom_included_sessions=45)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotEqual(response.data['subscription']['id'], str(old.pk))
        self.assertNotEqual(response.data['custom_policy']['id'], str(old_policy.pk))
        old.refresh_from_db()
        old_policy.refresh_from_db()
        self.assertEqual((old.status, old_policy.included_sessions, old_policy.subscription_id),
                         ('canceled', 30, old.pk))


class CompatibilityTests(_AddBase):

    def test_reception_and_turnos_ia_exclude_each_other_in_both_directions(self):
        with_reception = _gestion_client()
        self.assertEqual(self.add(with_reception).status_code, 201)
        with_turnos_ia = _gestion_client()
        self.assertEqual(self.add(with_turnos_ia, service_type='appointments', plan_code='appointments_ai',
                                  usage_tier='ai_300').status_code, 201)
        cases = (
            (with_reception, {'service_type': 'appointments', 'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'}),
            (with_turnos_ia, {}),
        )
        for business, overrides in cases:
            with self.subTest(business=business.slug):
                before = _snapshot(business)
                response = self.add(business, **overrides)
                self.assertEqual(response.status_code, 409, response.data)
                self.assertEqual((response.data['code'], response.data['field']), ('incompatible_ai_service', 'service_type'))
                self.assertEqual(_snapshot(business), before)

    def test_a_canceled_turnos_ia_without_usage_does_not_block_reception(self):
        business = _gestion_client()
        self.add(business, service_type='appointments', plan_code='appointments_ai', usage_tier='ai_300')
        SubscriptionV2.objects.filter(business=business, plan_code='appointments_ai').update(status='canceled')
        self.assertEqual(self.add(business).status_code, 201)

    def test_duplicate_non_canceled_service_is_rejected(self):
        business = _gestion_client()
        self.assertEqual(self.add(business).status_code, 201)
        for overrides in ({}, {'usage_tier': 'reception_custom', 'custom_included_sessions': 10}):
            with self.subTest(**overrides):
                response = self.add(business, **overrides)
                self.assertEqual((response.status_code, response.data['code']),
                                 (409, 'active_complimentary_subscription_conflict'))
        # Same rule for the principal service itself
        response = self.add(business, service_type='gestion', plan_code='gestion_pro', usage_tier=...)
        self.assertEqual(response.data['code'], 'active_complimentary_subscription_conflict')
        self.assertEqual(SubscriptionV2.objects.filter(business=business, service_type='reception').count(), 1)


class UsageContinuityTests(_AddBase):

    def _counted_usage(self, business, *, source_plan, period_start, period_end):
        service = 'reception' if source_plan == 'reception' else 'appointments'
        old = SubscriptionV2.objects.create(
            business=business, service_type=service, plan_code=source_plan,
            usage_tier='reception_300' if service == 'reception' else 'ai_300', provider='manual',
            external_reference=f'SUB-{uuid.uuid4()}', status='canceled', is_active=False,
            current_period_start=period_start - timedelta(days=30), current_period_end=period_end + timedelta(days=60),
        )
        AppointmentAIUsageSession.objects.create(
            business=business, subscription=old, external_conversation_id='conv-1',
            opening_interaction_id=uuid.uuid4(), started_at=period_start + timedelta(hours=1),
            expires_at=period_start + timedelta(hours=25), usage_period_start=period_start,
            usage_period_end=period_end, usage_tier=old.usage_tier,
        )

    def test_new_ai_grant_cannot_restart_a_running_usage_period(self):
        now = timezone.now().replace(microsecond=0)
        for source_plan, overrides in (
            ('reception', {}),
            ('appointments_ai', {}),  # cross-source: Turnos IA usage blocks a Recepcionista restart too
            ('reception', {'service_type': 'appointments', 'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'}),
        ):
            with self.subTest(source=source_plan, requested=overrides.get('plan_code', 'reception')):
                business = _gestion_client()
                period_end = now + timedelta(days=12)
                self._counted_usage(business, source_plan=source_plan,
                                    period_start=now - timedelta(days=18), period_end=period_end)
                before = _snapshot(business)
                response = self.add(business, **overrides)
                self.assertEqual(response.status_code, 409, response.data)
                self.assertEqual((response.data['code'], response.data['field']),
                                 ('ai_usage_period_overlap', 'complimentary_start'))
                self.assertEqual(_snapshot(business), before)
                # Starting exactly when the counted period ends is allowed
                later = self.add(business, complimentary_start=period_end.isoformat(),
                                 complimentary_end=(period_end + timedelta(days=90)).isoformat(), **overrides)
                self.assertEqual(later.status_code, 201, later.data)

    def test_non_ai_services_ignore_ai_usage_history(self):
        business = _gestion_client()
        now = timezone.now()
        self._counted_usage(business, source_plan='reception', period_start=now - timedelta(days=5),
                            period_end=now + timedelta(days=25))
        response = self.add(business, service_type='appointments', plan_code='appointments', usage_tier=...)
        self.assertEqual(response.status_code, 201, response.data)


class TargetBusinessTests(_AddBase):

    def test_missing_branch_and_non_operational_businesses_are_rejected(self):
        hq = _gestion_client()
        branch = Business.objects.create(name='Sucursal', slug=f'suc-{uuid.uuid4().hex[:8]}', parent=hq, status='active')
        response = self.client.post(services_url(999999), self.service_payload(), format='json')
        self.assertEqual((response.status_code, response.data['code']), (404, 'client_not_found'))
        response = self.add(branch)
        self.assertEqual((response.status_code, response.data['code']), (404, 'client_not_found'))
        for status in ('onboarding', 'pending_activation', 'past_due', 'suspended', 'canceled'):
            with self.subTest(status=status):
                business = _gestion_client(status=status)
                before = _snapshot(business)
                response = self.add(business)
                self.assertEqual((response.status_code, response.data['code']), (409, 'client_status_not_eligible'))
                self.assertEqual(_snapshot(business), before)
        self.assertFalse(SubscriptionV2.objects.filter(service_type='reception').exists())


class AtomicityTests(_AddBase):

    def _kwargs(self, business, **overrides):
        payload = self.service_payload(**overrides)
        return {**payload, 'business_id': business.pk, 'complimentary_start': self.starts_at,
                'complimentary_end': self.ends_at, 'granted_by': self.admin}

    def _assert_nothing_added(self, business, before):
        self.assertEqual(_snapshot(business), before)
        self.assertFalse(ReceptionAIUsagePolicy.objects.exists())
        self.assertFalse(ReceptionAIUsagePolicyChange.objects.exists())
        self.assertFalse(AccessAuditLog.objects.filter(business=business).exists())

    def test_policy_failure_rolls_back_the_whole_addition(self):
        business = _gestion_client()
        before = _snapshot(business)
        with patch('apps.billing.services.reception_ai_policy.ReceptionAIUsagePolicyChange.objects.create',
                   side_effect=RuntimeError('policy audit down')), self.assertRaises(RuntimeError):
            add_service_to_client(**self._kwargs(business, usage_tier='reception_custom', custom_included_sessions=50))
        self._assert_nothing_added(business, before)

    def test_mandatory_audit_failure_rolls_back_the_whole_addition(self):
        business = _gestion_client()
        before = _snapshot(business)
        with patch('apps.accounts.platform_audit.record_platform_action', side_effect=RuntimeError('audit down')), \
                self.assertRaises(RuntimeError):
            add_service_to_client(**self._kwargs(business, usage_tier='reception_custom', custom_included_sessions=50))
        self._assert_nothing_added(business, before)

    def test_audit_failure_over_http_is_a_500_with_nothing_persisted(self):
        business = _gestion_client()
        before = _snapshot(business)
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=self.admin)
        with patch('apps.accounts.platform_audit.record_platform_action', side_effect=RuntimeError('audit down')):
            response = self.add(business, client=client)
        self.assertEqual(response.status_code, 500)
        self._assert_nothing_added(business, before)


class AdvanceStatusRuleTests(_AddBase):
    """grant_complimentary_access only advances a never-activated Business."""

    def test_grant_never_downgrades_nor_reactivates(self):
        expected = {'onboarding': 'trialing', 'pending_activation': 'trialing', 'trialing': 'trialing',
                    'active': 'active', 'past_due': 'past_due', 'suspended': 'suspended', 'canceled': 'canceled'}
        for initial, final in expected.items():
            with self.subTest(status=initial):
                business = Business.objects.create(name='B', slug=f'b-{uuid.uuid4().hex[:8]}', status=initial)
                grant_complimentary_access(
                    business=business, plan_code='gestion_pro', service_type='gestion', starts_at=self.starts_at,
                    ends_at=self.ends_at, granted_by=self.admin, reason='regla de estado',
                )
                business.refresh_from_db()
                self.assertEqual(business.status, final)


class PayloadAndPermissionTests(_AddBase):

    def test_unknown_and_identity_fields_are_rejected(self):
        business = _gestion_client()
        for field, value in (
            ('owner_email', 'otro@x.test'), ('status', 'active'), ('business_name', 'Otro'),
            ('default_service', 'reception'), ('business_slug', 'otro'), ('country', 'UY'), ('currency', 'USD'),
            ('attach_existing_owner', True), ('owner_confirmation_token', 'x'), ('provider', 'mercadopago'),
        ):
            with self.subTest(field=field):
                response = self.add(business, **{field: value})
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data[field], ['Campo no permitido.'])
        self.assertFalse(SubscriptionV2.objects.filter(service_type='reception').exists())

    def test_existing_validators_are_reused(self):
        business = _gestion_client()
        cases = (
            ({'usage_tier': ...}, 400, 'invalid_complimentary_usage_tier'),
            ({'custom_included_sessions': 10}, 400, 'invalid_custom_included_sessions'),
            ({'usage_tier': 'reception_custom'}, 400, 'invalid_custom_included_sessions'),
            ({'grant_reason': '  '}, 400, 'invalid_complimentary_grant_reason'),
            ({'complimentary_end': (self.starts_at - timedelta(days=1)).isoformat()}, 400, 'invalid_complimentary_period'),
            ({'plan_code': 'gestion_pro'}, 400, 'complimentary_plan_service_mismatch'),
            ({'plan_code': 'nope'}, 400, 'complimentary_plan_not_available'),
            ({'service_type': 'restaurante', 'plan_code': 'gestion_pro', 'usage_tier': ...}, 400,
             'complimentary_plan_service_mismatch'),
        )
        for overrides, status_code, code in cases:
            with self.subTest(code=code, overrides=overrides):
                response = self.add(business, **overrides)
                self.assertEqual((response.status_code, response.data.get('code')), (status_code, code), response.data)
        self.assertEqual(self.add(business, custom_included_sessions='10').status_code, 400)  # strict shape
        self.assertFalse(SubscriptionV2.objects.filter(service_type='reception').exists())

    def test_only_superadmin_platform_staff_may_add_services(self):
        business = _gestion_client()
        for role in ('operations', 'support_agent', 'content_admin'):
            client = APIClient()
            client.force_authenticate(user=_staff(role))
            with self.subTest(role=role):
                self.assertEqual(self.add(business, client=client).status_code, 403)
        self.assertIn(self.add(business, client=APIClient()).status_code, (401, 403))
        owner = Membership.objects.get(business=business, role='owner').user
        owner_client = APIClient()
        owner_client.force_authenticate(user=owner)  # a membership is never an admin authorization
        self.assertEqual(self.add(business, client=owner_client).status_code, 403)
        self.assertFalse(SubscriptionV2.objects.filter(service_type='reception').exists())

    def test_public_checkout_stays_blocked_after_an_internal_addition(self):
        business = _gestion_client()
        self.assertEqual(self.add(business).status_code, 201)
        self.assertFalse(canonical_pricing.is_plan_product_active('reception'))
        self.assertNotIn('reception', [p['code'] for p in canonical_pricing.get_products_catalog()])
        sub = SubscriptionV2.objects.get(business=business, service_type='reception')
        self.assertEqual((sub.provider, sub.provider_sub_id), ('manual', None))
        self.assertFalse(PaymentAttempt.objects.filter(subscription__business=business).exists())


class ConcurrentAdditionTests(TransactionTestCase):
    """Real threads/connections: the Business lock serializes additions."""

    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        call_command('seed_reception_catalog', stdout=StringIO())
        call_command('seed_appointments_catalog', stdout=StringIO())
        self.admin = _staff()
        self.starts_at = timezone.now().replace(microsecond=0) - timedelta(hours=1)
        self.ends_at = self.starts_at + timedelta(days=90)
        self.business = Business.objects.create(name='Carrera', slug=f'carrera-{uuid.uuid4().hex[:8]}',
                                                status='active', service_type='gestion', default_service='gestion')

    def _race(self, *specs):
        barrier = threading.Barrier(len(specs))
        outcomes = []

        def worker(spec):
            try:
                barrier.wait(timeout=10)
                try:
                    add_service_to_client(
                        business_id=self.business.pk, complimentary_start=self.starts_at,
                        complimentary_end=self.ends_at, granted_by=self.admin, grant_reason='carrera', **spec,
                    )
                    outcomes.append(('ok', spec['plan_code']))
                except (ComplimentaryIncompatibleAIServiceError, ActiveComplimentarySubscriptionConflictError) as exc:
                    outcomes.append((type(exc).__name__, spec['plan_code']))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(spec,)) for spec in specs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        return outcomes

    def _live(self):
        return SubscriptionV2.objects.filter(business=self.business).exclude(status='canceled')

    def test_incompatible_ai_additions_never_both_succeed(self):
        outcomes = self._race(
            {'service_type': 'reception', 'plan_code': 'reception', 'usage_tier': 'reception_300'},
            {'service_type': 'appointments', 'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'},
        )
        self.assertEqual(sorted(o[0] for o in outcomes), ['ComplimentaryIncompatibleAIServiceError', 'ok'])
        self.assertEqual(self._live().count(), 1)

    def test_duplicate_additions_create_a_single_subscription(self):
        spec = {'service_type': 'reception', 'plan_code': 'reception', 'usage_tier': 'reception_300'}
        outcomes = self._race(spec, dict(spec))
        self.assertEqual(sorted(o[0] for o in outcomes), ['ActiveComplimentarySubscriptionConflictError', 'ok'])
        self.assertEqual(self._live().filter(service_type='reception').count(), 1)

    def test_compatible_additions_both_succeed(self):
        outcomes = self._race(
            {'service_type': 'reception', 'plan_code': 'reception', 'usage_tier': 'reception_300'},
            {'service_type': 'appointments', 'plan_code': 'appointments_pro'},
        )
        self.assertEqual([o[0] for o in outcomes], ['ok', 'ok'])
        self.assertEqual(self._live().count(), 2)
        self.business.refresh_from_db()
        self.assertEqual((self.business.status, self.business.service_type), ('active', 'gestion'))
