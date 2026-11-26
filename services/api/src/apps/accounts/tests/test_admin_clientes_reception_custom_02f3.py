"""PROD-02F3 — Alta atómica de Recepcionista Custom.

`reception_custom` se provisiona con `custom_included_sessions`: la
SubscriptionV2 bonificada y su ReceptionAIUsagePolicy (+ su cambio de
auditoría) nacen en la misma transacción; cualquier fallo revierte todo.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.test_admin_clientes_reception_provisioning_02f2 import CLIENTS_URL, OPTIONS_URL, _Base, _staff
from apps.appointments.services.ai_usage import get_appointments_ai_usage
from apps.billing import canonical_pricing
from apps.billing.complimentary_access_service import (
    InvalidCustomAllowanceError, grant_complimentary_access, list_provisioning_options,
)
from apps.billing.models import ReceptionAIUsagePolicy, ReceptionAIUsagePolicyChange, SubscriptionV2
from apps.billing.services.ai_source import resolve_ai_source
from apps.billing.services.reception_ai_policy import effective_reception_custom_policy
from apps.business.models import Business
from apps.leads.models import AgentChannel, AgentInstance

User = get_user_model()


class _CustomBase(_Base):

    def custom(self, sessions=750, **overrides):
        return self.provision(usage_tier='reception_custom', custom_included_sessions=sessions, **overrides)

    def assertNothingCreated(self, users_before=None):
        self.assertFalse(Business.objects.exists())
        self.assertFalse(SubscriptionV2.objects.exists())
        self.assertFalse(ReceptionAIUsagePolicy.objects.exists())
        self.assertFalse(ReceptionAIUsagePolicyChange.objects.exists())
        if users_before is not None:
            self.assertEqual(User.objects.count(), users_before)


class CustomOptionsTests(_CustomBase):

    def test_custom_is_offered_with_its_allowance_bounds_and_fixed_tiers_unchanged(self):
        reception = next(s for s in self.client.get(OPTIONS_URL).data['services'] if s['value'] == 'reception')
        tiers = {t['code']: t for t in reception['plans'][0]['usage_tiers']}
        self.assertEqual(list(tiers), ['reception_300', 'reception_1500', 'reception_3000', 'reception_custom'])
        self.assertEqual(tiers['reception_custom']['custom_allowance'], {'min': 1, 'max': 1_000_000})
        for code in ('reception_300', 'reception_1500', 'reception_3000'):
            self.assertEqual(set(tiers[code]), {'code', 'name'})
        self.assertFalse(canonical_pricing.is_plan_product_active('reception'))

    def test_custom_follows_its_real_catalog_terms(self):
        real = canonical_pricing.get_usage_tier
        for changes in ({'purchase_mode': 'internal'}, {'included_conversations': 5000},
                        {'extra_conversation_price': 300}, {'default_extra_spend_limit': 1000},
                        {'monthly_price': 1}, {'billing_mode': 'automatic'}):
            with self.subTest(changes=changes), patch(
                'apps.billing.complimentary_access_service._get_canonical_usage_tier',
                side_effect=lambda code, c=changes: {**real(code), **c} if code == 'reception_custom' else real(code),
            ):
                reception = next(s for s in list_provisioning_options() if s['value'] == 'reception')
                self.assertNotIn('reception_custom', [t['code'] for t in reception['plans'][0]['usage_tiers']])


class CustomProvisioningTests(_CustomBase):

    def test_complete_atomic_alta_with_its_policy(self):
        before = timezone.now()
        response = self.custom(sessions=750)
        after = timezone.now()
        self.assertEqual(response.status_code, 201, response.data)
        business = Business.objects.get(pk=response.data['business_id'])
        sub = SubscriptionV2.objects.get(business=business)
        self.assertEqual((sub.service_type, sub.usage_tier, sub.provider, sub.status),
                         ('reception', 'reception_custom', 'manual', 'trialing'))
        policy = ReceptionAIUsagePolicy.objects.get(subscription=sub)
        self.assertEqual((policy.business_id, policy.included_sessions, policy.status, policy.created_by_id),
                         (business.pk, 750, 'active', self.admin.pk))
        # Benefit already started: the policy starts at the server instant, never retroactively,
        # and ends with the bonified window
        self.assertTrue(before <= policy.valid_from <= after)
        self.assertGreater(policy.valid_from, sub.current_period_start)
        self.assertEqual(policy.valid_until, sub.current_period_end)
        change = ReceptionAIUsagePolicyChange.objects.get(policy=policy)
        self.assertEqual((change.action, change.new_included_sessions, change.actor_id, change.reason),
                         ('created', 750, self.admin.pk, 'Piloto Recepcionista IA'))
        now = timezone.now()
        self.assertTrue(resolve_ai_source(business, at=now).policy_configured)
        self.assertEqual(get_appointments_ai_usage(business, at=now)['included'], 750)
        self.assertFalse(AgentInstance.objects.exists() or AgentChannel.objects.exists())

    def test_future_benefit_policy_starts_with_it(self):
        start = timezone.now().replace(microsecond=0) + timedelta(days=2)
        end = start + timedelta(days=90)
        response = self.custom(sessions=40, complimentary_start=start.isoformat(), complimentary_end=end.isoformat())
        self.assertEqual(response.status_code, 201, response.data)
        sub = SubscriptionV2.objects.get(business_id=response.data['business_id'])
        policy = ReceptionAIUsagePolicy.objects.get(subscription=sub)
        self.assertEqual((policy.valid_from, policy.valid_until), (start, end))
        self.assertIsNone(resolve_ai_source(sub.business, at=timezone.now()).source)  # not started
        self.assertEqual(effective_reception_custom_policy(sub, at=start + timedelta(hours=1)).included_sessions, 40)

    def test_window_that_cannot_hold_a_valid_policy_is_rejected(self):
        start = timezone.now() - timedelta(days=40)
        response = self.custom(complimentary_start=start.isoformat(),
                               complimentary_end=(timezone.now() - timedelta(minutes=1)).isoformat())
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual((response.data['code'], response.data['field']),
                         ('invalid_custom_included_sessions', 'custom_included_sessions'))
        self.assertNothingCreated()

    def test_two_custom_clients_keep_their_own_allowance(self):
        first = Business.objects.get(pk=self.custom(sessions=100).data['business_id'])
        second = Business.objects.get(pk=self.custom(sessions=2000).data['business_id'])
        now = timezone.now()
        self.assertEqual((get_appointments_ai_usage(first, at=now)['included'],
                          get_appointments_ai_usage(second, at=now)['included']), (100, 2000))
        self.assertEqual(ReceptionAIUsagePolicy.objects.filter(business=first).count(), 1)


class CustomValidationTests(_CustomBase):

    def test_missing_out_of_range_and_non_integer_allowances(self):
        for value in (..., None, 0, -1, 1_000_001):
            with self.subTest(value=value):
                response = self.custom(sessions=value)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data['code'], 'invalid_custom_included_sessions')
        for value in (1.5, 10.0, '10', True, [], {}):
            with self.subTest(value=value):
                response = self.custom(sessions=value)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn('custom_included_sessions', response.data)  # strict shape error
        self.assertNothingCreated()

    def test_field_rejected_for_any_other_tier_or_product(self):
        for overrides in ({'usage_tier': 'reception_300'},
                          {'service_type': 'appointments', 'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'}):
            with self.subTest(overrides=overrides):
                response = self.provision(custom_included_sessions=100, **overrides)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data['code'], 'invalid_custom_included_sessions')
        self.assertNothingCreated()
        # null is "not sent" for the other tiers
        self.assertEqual(self.provision(custom_included_sessions=None).status_code, 201)

    def test_no_enabled_path_creates_a_custom_without_policy(self):
        business = Business.objects.create(name='X', slug=f'x-{uuid.uuid4().hex[:6]}', service_type='reception',
                                           default_service='reception', status='onboarding')
        with self.assertRaises(InvalidCustomAllowanceError):
            grant_complimentary_access(business=business, plan_code='reception', service_type='reception',
                                       starts_at=self.starts_at, ends_at=self.ends_at, granted_by=self.admin,
                                       reason='sin cupo', usage_tier='reception_custom')
        self.assertFalse(SubscriptionV2.objects.filter(business=business).exists())


class CustomSafetyTests(_CustomBase):

    def test_rollback_when_policy_or_its_audit_fails(self):
        users_before = User.objects.count()
        for target in ('apps.billing.services.reception_ai_policy.create_reception_custom_policy',
                       'apps.billing.services.reception_ai_policy.ReceptionAIUsagePolicyChange.objects.create'):
            with self.subTest(target=target), patch(target, side_effect=RuntimeError('boom')):
                with self.assertRaises(RuntimeError):
                    self.custom()
                self.assertNothingCreated(users_before)

    def test_existing_owner_permissions_and_checkout(self):
        User.objects.create_user(username='dueno@example.test', email='dueno@example.test')
        response = self.custom(owner_email='dueno@example.test')
        self.assertEqual((response.status_code, response.data['code']), (409, 'existing_owner_requires_confirmation'))
        operations = APIClient()
        operations.force_authenticate(user=_staff('operations'))
        payload = self.payload(usage_tier='reception_custom', custom_included_sessions=10)
        self.assertEqual(operations.post(CLIENTS_URL, payload, format='json').status_code, 403)
        self.assertNothingCreated()
        response = APIClient().post('/api/v1/billing/start-subscription', {
            'email': f'{uuid.uuid4().hex[:8]}@x.test', 'password': 'Secret-123456',
            'business_name': 'Nuevo', 'plan_code': 'reception',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_fixed_tiers_and_turnos_ia_unchanged(self):
        response = self.provision(usage_tier='reception_3000')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(ReceptionAIUsagePolicy.objects.exists())
        response = self.provision(service_type='appointments', plan_code='appointments_ai', usage_tier='ai_1500')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(SubscriptionV2.objects.get(business_id=response.data['business_id']).usage_tier, 'ai_1500')
