"""
Turnos IA internal provisioning (pilot) — /admin/clientes/nuevo.

A platform superadmin can provision a client with the tier-priced
``appointments_ai`` plan as complimentary access: the form gets the plan and
its provisionable usage tiers from provisioning-options, and the grant
stores ``usage_tier`` on the manual SubscriptionV2, which is what grants
``appointments.leads``. Turnos / Turnos Pro and public checkout keep their
behaviour.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccessAuditLog
from apps.billing.checkout_session_service import start_checkout
from apps.billing.models import Plan, SubscriptionV2
from apps.business.entitlements import has_appointments_leads_access, has_entitlement
from apps.business.models import Business

User = get_user_model()
CLIENTS_URL = '/api/v1/platform-admin/clients/'
OPTIONS_URL = '/api/v1/platform-admin/clients/provisioning-options/'


def _superadmin():
    user = User.objects.create_user(
        username=f'sa-{uuid.uuid4().hex}', email=f'sa-{uuid.uuid4().hex}@example.com',
        password='SecurePass123!',
    )
    profile = user.account_profile
    profile.is_platform_staff = True
    profile.internal_role = 'superadmin'
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


class TurnosIAProvisioningTests(TestCase):
    def setUp(self):
        call_command('seed_appointments_catalog', stdout=StringIO())
        self.client = APIClient()
        self.client.force_authenticate(user=_superadmin())
        self.starts_at = timezone.now().replace(microsecond=0)
        self.ends_at = self.starts_at + timedelta(days=180)

    def payload(self, **overrides):
        data = {
            'business_name': 'Clínica Piloto',
            'business_slug': f'clinica-{uuid.uuid4().hex[:10]}',
            'service_type': 'appointments',
            'country': 'AR',
            'currency': 'ARS',
            'owner_email': f'owner-{uuid.uuid4().hex[:10]}@example.test',
            'plan_code': 'appointments_ai',
            'usage_tier': 'ai_300',
            'complimentary_start': self.starts_at.isoformat(),
            'complimentary_end': self.ends_at.isoformat(),
            'grant_reason': 'Piloto Turnos IA',
        }
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not ...}

    def _appointments_option(self):
        response = self.client.get(OPTIONS_URL)
        self.assertEqual(response.status_code, 200)
        return next(s for s in response.data['services'] if s['value'] == 'appointments')

    def test_options_offer_turnos_ia_with_self_service_tiers_only(self):
        service = self._appointments_option()
        plans = {p['code']: p for p in service['plans']}
        self.assertEqual(set(plans), {'appointments', 'appointments_ai', 'appointments_pro'})
        self.assertEqual(
            [t['code'] for t in plans['appointments_ai']['usage_tiers']],
            ['ai_300', 'ai_1500', 'ai_3000'],
        )
        self.assertEqual(set(plans['appointments']), {'code', 'name'})
        self.assertEqual(set(plans['appointments_pro']), {'code', 'name'})

    def test_provisioning_turnos_ia_stores_tier_and_grants_leads(self):
        response = self.client.post(CLIENTS_URL, self.payload(), format='json')

        self.assertEqual(response.status_code, 201, response.data)
        business = Business.objects.get(pk=response.data['business_id'])
        sub = SubscriptionV2.objects.get(business=business)
        self.assertEqual(
            (sub.service_type, sub.plan_code, sub.usage_tier, sub.provider, sub.status, sub.is_active),
            ('appointments', 'appointments_ai', 'ai_300', 'manual', 'trialing', True),
        )
        self.assertEqual(sub.current_period_start, self.starts_at)
        self.assertEqual(sub.current_period_end, self.ends_at)
        self.assertEqual(sub.manual_grant_reason, 'Piloto Turnos IA')
        self.assertTrue(has_appointments_leads_access(business))
        audit = AccessAuditLog.objects.get(action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED', business=business)
        self.assertEqual(audit.details['usage_tier'], 'ai_300')

    def test_turnos_ia_requires_a_provisionable_tier(self):
        for tier in (..., None, '', 'custom', 'ai_9999'):
            with self.subTest(tier=tier):
                response = self.client.post(CLIENTS_URL, self.payload(usage_tier=tier), format='json')
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data['code'], 'invalid_complimentary_usage_tier')
                self.assertEqual(response.data['field'], 'usage_tier')
        self.assertFalse(Business.objects.exists())
        self.assertFalse(SubscriptionV2.objects.exists())

    def test_turnos_and_pro_reject_tier_and_keep_current_entitlements(self):
        response = self.client.post(
            CLIENTS_URL, self.payload(plan_code='appointments', usage_tier='ai_300'), format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'invalid_complimentary_usage_tier')

        for plan_code in ('appointments', 'appointments_pro'):
            with self.subTest(plan_code=plan_code):
                response = self.client.post(
                    CLIENTS_URL, self.payload(plan_code=plan_code, usage_tier=...), format='json',
                )
                self.assertEqual(response.status_code, 201, response.data)
                business = Business.objects.get(pk=response.data['business_id'])
                sub = SubscriptionV2.objects.get(business=business)
                self.assertIsNone(sub.usage_tier)
                self.assertTrue(has_entitlement(business, 'appointments.customers'))
                self.assertFalse(has_appointments_leads_access(business))

    def test_seed_twice_keeps_one_inactive_ia_plan_and_public_checkout_blocked(self):
        call_command('seed_appointments_catalog', stdout=StringIO())
        self.assertEqual(Plan.objects.filter(code='appointments_ai').count(), 1)
        self.assertFalse(Plan.objects.filter(code__startswith='appointments', plan_status='active').exists())
        with self.assertRaisesMessage(ValueError, 'not available'):
            start_checkout(user=None, tenant=None, plan_code='appointments_ai')
