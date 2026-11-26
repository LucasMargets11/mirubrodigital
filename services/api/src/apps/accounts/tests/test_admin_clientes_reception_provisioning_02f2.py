"""PROD-02F2 — Alta interna de Recepcionista IA con cupos fijos (beneficio bonificado).

Platform Admin (superadmin) provisiona un Business nuevo con `reception` /
`reception` y un tier fijo (300/1500/3000), con el mismo flujo atómico que
Turnos IA. `reception_custom`, el checkout público y la asociación automática
de cuentas existentes siguen fuera.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.admin_client_provisioning_service import provision_admin_client
from apps.accounts.models import AccessAuditLog, Membership
from apps.appointments.services.agenda_access import has_agenda_access
from apps.appointments.services.ai_usage import get_appointments_ai_usage, resolve_ai_usage_limit
from apps.billing import canonical_pricing
from apps.billing.complimentary_access_service import list_provisioning_options
from apps.billing.models import SubscriptionV2
from apps.billing.runtime import resolve_subscription
from apps.billing.services.ai_source import RECEPTION_SOURCE, resolve_ai_source
from apps.business.entitlements import has_entitlement
from apps.business.models import Business
from apps.leads.models import AgentChannel, AgentCredential, AgentInstance

User = get_user_model()
CLIENTS_URL = '/api/v1/platform-admin/clients/'
OPTIONS_URL = '/api/v1/platform-admin/clients/provisioning-options/'
FIXED = {'reception_300': 300, 'reception_1500': 1500, 'reception_3000': 3000}
BA = ZoneInfo('America/Argentina/Buenos_Aires')


def _staff(role='superadmin'):
    user = User.objects.create_user(username=f'{role}-{uuid.uuid4().hex}', email=f'{uuid.uuid4().hex}@example.com')
    profile = user.account_profile
    profile.is_platform_staff, profile.internal_role = True, role
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


class _Base(TestCase):

    def setUp(self):
        call_command('seed_reception_catalog', stdout=StringIO())
        call_command('seed_appointments_catalog', stdout=StringIO())
        self.admin = _staff()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.starts_at = timezone.now().replace(microsecond=0) - timedelta(hours=1)
        self.ends_at = self.starts_at + timedelta(days=180)

    def payload(self, **overrides):
        data = {
            'business_name': 'Clínica Recepcionista', 'business_slug': f'rcp-{uuid.uuid4().hex[:10]}',
            'service_type': 'reception', 'country': 'AR', 'currency': 'ARS',
            'owner_email': f'owner-{uuid.uuid4().hex[:10]}@example.test',
            'plan_code': 'reception', 'usage_tier': 'reception_300',
            'complimentary_start': self.starts_at.isoformat(), 'complimentary_end': self.ends_at.isoformat(),
            'grant_reason': 'Piloto Recepcionista IA',
        }
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not ...}

    def provision(self, **overrides):
        return self.client.post(CLIENTS_URL, self.payload(**overrides), format='json')


class ReceptionOptionsTests(_Base):

    def test_options_offer_reception_with_the_three_fixed_tiers_only(self):
        response = self.client.get(OPTIONS_URL)
        self.assertEqual(response.status_code, 200)
        services = {s['value']: s for s in response.data['services']}
        reception = services['reception']
        self.assertEqual([p['code'] for p in reception['plans']], ['reception'])
        self.assertEqual([t['code'] for t in reception['plans'][0]['usage_tiers']], list(FIXED))
        # Turnos IA keeps its own rule; internal availability ≠ public availability
        ai = next(p for p in services['appointments']['plans'] if p['code'] == 'appointments_ai')
        self.assertEqual([t['code'] for t in ai['usage_tiers']], ['ai_300', 'ai_1500', 'ai_3000'])
        self.assertFalse(canonical_pricing.is_plan_product_active('reception'))

    def test_eligibility_follows_the_real_catalog_terms(self):
        real = canonical_pricing.get_usage_tier
        for changes in ({'purchase_mode': 'self_service'}, {'extra_conversation_price': 300},
                        {'default_extra_spend_limit': 75000}, {'included_conversations': None},
                        {'monthly_price': 1000}, {'billing_mode': 'automatic'}):
            with self.subTest(changes=changes), patch(
                'apps.billing.complimentary_access_service._get_canonical_usage_tier',
                side_effect=lambda code, c=changes: {**real(code), **c} if code == 'reception_300' else real(code),
            ):
                reception = next(s for s in list_provisioning_options() if s['value'] == 'reception')
                self.assertNotIn('reception_300', [t['code'] for t in reception['plans'][0]['usage_tiers']])

    def test_other_inactive_verticals_are_not_generalized(self):
        values = {s['value'] for s in list_provisioning_options()}
        self.assertTrue({'reception', 'appointments'} <= values)
        plans = [p['code'] for s in list_provisioning_options() for p in s['plans']]
        self.assertEqual(plans.count('reception'), 1)


class ReceptionProvisioningTests(_Base):

    def test_each_fixed_tier_provisions_a_complete_client(self):
        for tier, included in FIXED.items():
            with self.subTest(tier=tier):
                response = self.provision(usage_tier=tier)
                self.assertEqual(response.status_code, 201, response.data)
                business = Business.objects.get(pk=response.data['business_id'])
                self.assertEqual((business.service_type, business.default_service, business.status, business.parent_id),
                                 ('reception', 'reception', 'trialing', None))
                owner = User.objects.get(pk=response.data['owner_user_id'])
                self.assertTrue(response.data['owner']['created'])
                self.assertFalse(owner.has_usable_password())
                membership = Membership.objects.get(business=business)
                self.assertEqual((membership.user_id, membership.role, membership.status), (owner.pk, 'owner', 'active'))
                sub = SubscriptionV2.objects.get(business=business)
                self.assertEqual(
                    (sub.service_type, sub.plan_code, sub.usage_tier, sub.provider, sub.status, sub.is_active,
                     sub.billing_cycle, sub.trial_ends_at),
                    ('reception', 'reception', tier, 'manual', 'trialing', True, '', None),
                )
                self.assertEqual((sub.current_period_start, sub.current_period_end), (self.starts_at, self.ends_at))
                self.assertEqual(resolve_ai_usage_limit(sub, at=timezone.now()), included)
                self.assertTrue(AccessAuditLog.objects.filter(business=business, action='ADMIN_CLIENT_CREATED').exists())
                self.assertTrue(AccessAuditLog.objects.filter(
                    business=business, action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED',
                    details__usage_tier=tier).exists())
        # Commercial provisioning never creates the operational agent
        self.assertFalse(AgentInstance.objects.exists() or AgentChannel.objects.exists()
                         or AgentCredential.objects.exists())

    def test_access_ai_quota_entitlements_agenda_and_seats(self):
        response = self.provision(usage_tier='reception_1500')
        business = Business.objects.get(pk=response.data['business_id'])
        now = timezone.now()
        source = resolve_ai_source(business, at=now)
        self.assertEqual((source.source, source.policy_configured), (RECEPTION_SOURCE, True))
        usage = get_appointments_ai_usage(business, at=now)
        self.assertEqual((usage['included'], usage['used'], usage['usage_tier']), (1500, 0, 'reception_1500'))
        self.assertEqual(usage['period_start'], self.starts_at)  # monthly from the grant start
        for code in ('reception.leads', 'reception.customers', 'reception.ai'):
            self.assertTrue(has_entitlement(business, code), code)
        self.assertFalse(has_agenda_access(business))
        self.assertTrue(resolve_subscription(business, service_type='reception').access_granted)
        # Five provisional secondary seats; the owner is outside the quota
        for i in range(5):
            Membership.objects.create(user=User.objects.create_user(username=f'u{i}-{uuid.uuid4().hex[:6]}'),
                                      business=business, role='manager')
        with self.assertRaises(ValidationError):
            Membership.objects.create(user=User.objects.create_user(username=f'u6-{uuid.uuid4().hex[:6]}'),
                                      business=business, role='manager')

    def test_future_current_and_expired_benefits(self):
        now = timezone.now().replace(microsecond=0)
        windows = {
            'future': (now + timedelta(days=1), now + timedelta(days=31), False),
            'current': (now - timedelta(days=1), now + timedelta(days=29), True),
            'expired': (now - timedelta(days=40), now - timedelta(days=1), False),
        }
        for name, (start, end, expected) in windows.items():
            with self.subTest(name):
                response = self.provision(complimentary_start=start.isoformat(), complimentary_end=end.isoformat())
                self.assertEqual(response.status_code, 201, response.data)
                business = Business.objects.get(pk=response.data['business_id'])
                self.assertEqual(resolve_subscription(business, service_type='reception').access_granted, expected)
                self.assertEqual(resolve_ai_source(business, at=now).source is not None, expected)

    def test_date_only_values_are_midnights_in_the_server_timezone(self):
        response = self.provision(complimentary_start='2026-12-01', complimentary_end='2027-06-01')
        self.assertEqual(response.status_code, 201, response.data)
        sub = SubscriptionV2.objects.get(business_id=response.data['business_id'])
        self.assertEqual(sub.current_period_start, datetime.combine(datetime(2026, 12, 1).date(), time(), tzinfo=BA))
        self.assertEqual(sub.current_period_end, datetime.combine(datetime(2027, 6, 1).date(), time(), tzinfo=BA))


class ReceptionRejectionTests(_Base):

    def test_custom_and_invalid_tiers_and_plans_are_rejected(self):
        for overrides, code in (
            ({'usage_tier': 'reception_custom'}, 'invalid_complimentary_usage_tier'),
            ({'usage_tier': 'ai_300'}, 'invalid_complimentary_usage_tier'),
            ({'usage_tier': 'reception_999'}, 'invalid_complimentary_usage_tier'),
            ({'usage_tier': ...}, 'invalid_complimentary_usage_tier'),
            ({'plan_code': 'reception_pro'}, 'complimentary_plan_not_available'),
            ({'plan_code': 'reception', 'service_type': 'appointments'}, 'complimentary_plan_service_mismatch'),
            ({'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'}, 'complimentary_plan_service_mismatch'),
        ):
            with self.subTest(overrides=overrides):
                response = self.provision(**overrides)
                self.assertIn(response.status_code, (400, 409), response.data)
                self.assertEqual(response.data['code'], code)
        self.assertFalse(Business.objects.exists())
        self.assertFalse(SubscriptionV2.objects.exists())

    def test_public_checkout_stays_blocked(self):
        response = APIClient().post('/api/v1/billing/start-subscription', {
            'email': f'{uuid.uuid4().hex[:8]}@x.test', 'password': 'Secret-123456',
            'business_name': 'Nuevo', 'plan_code': 'reception',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Business.objects.filter(default_service='reception').exists())

    def test_existing_account_is_never_attached_automatically(self):
        existing = User.objects.create_user(username='taken@example.test', email='Taken@Example.test')
        other = Business.objects.create(name='Otro', slug=f'otro-{uuid.uuid4().hex[:6]}', status='active')
        Membership.objects.create(user=existing, business=other, role='owner')
        response = self.provision(owner_email='taken@example.test')
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual((response.data['code'], response.data['field']),
                         ('existing_owner_requires_confirmation', 'owner_email'))
        self.assertFalse(Business.objects.filter(default_service='reception').exists())
        self.assertEqual(Membership.objects.filter(user=existing).count(), 1)
        # Other products keep their existing behaviour (reuse the account)
        response = self.provision(service_type='appointments', plan_code='appointments_ai', usage_tier='ai_300',
                                  owner_email='taken@example.test')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data['owner']['created'])

    def test_failure_rolls_back_everything(self):
        users_before = User.objects.count()
        with patch('apps.accounts.admin_client_provisioning_service.log_platform_action',
                   side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                provision_admin_client(**{**self.payload(), 'complimentary_start': self.starts_at,
                                          'complimentary_end': self.ends_at}, granted_by=self.admin)
        self.assertFalse(Business.objects.exists())
        self.assertFalse(SubscriptionV2.objects.exists())
        self.assertEqual(User.objects.count(), users_before)

    def test_only_superadmin_can_provision(self):
        for role in ('operations', 'support_agent', 'content_admin'):
            client = APIClient()
            client.force_authenticate(user=_staff(role))
            with self.subTest(role=role):
                self.assertEqual(client.post(CLIENTS_URL, self.payload(), format='json').status_code, 403)
        self.assertIn(APIClient().post(CLIENTS_URL, self.payload(), format='json').status_code, (401, 403))
        owner = User.objects.create_user(username=f'owner-{uuid.uuid4().hex[:6]}')
        client = APIClient()
        client.force_authenticate(user=owner)
        self.assertEqual(client.post(CLIENTS_URL, self.payload(), format='json').status_code, 403)
        self.assertFalse(Business.objects.exists())
