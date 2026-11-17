"""
Turnos IA pilot: AI usage for a complimentary grant created by the admin form.

The grant (provider=manual, status=trialing, billing_cycle='', Business
'trialing') is created through grant_complimentary_access() exactly as
/admin/clientes/nuevo does, and is never patched afterwards. Usage periods are
monthly, anchored at the grant start and clipped to its end; the tier is a hard
cap (no billable overage).
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
)
from apps.appointments.services.ai_usage import (
    get_appointments_ai_usage, resolve_ai_usage_policy, resolve_appointments_ai_usage_period,
)
from apps.billing.complimentary_access_service import grant_complimentary_access
from apps.billing.models import SubscriptionV2
from apps.billing.services.appointments_lifecycle import (
    appointments_v2_allows_creation, subscription_lifecycle_access,
)
from apps.business.models import Business
from apps.leads.models import Lead
from apps.leads.tests.agent_client import encode, sign_headers
from apps.leads.tests.factories import SECRET, TEST_KEY, make_channel, make_credential, make_instance, make_state

PATH = '/api/internal/appointments/ai-usage/authorize/'
User = get_user_model()


def _add_months(value, months):
    month = value.month - 1 + months
    return value.replace(year=value.year + month // 12, month=month % 12 + 1)


def _superadmin():
    user = User.objects.create_user(username=f'sa-{uuid.uuid4().hex}', email=f'{uuid.uuid4().hex}@x.test')
    profile = user.account_profile
    profile.is_platform_staff, profile.internal_role = True, 'superadmin'
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


@override_settings(AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class ComplimentaryAIUsageTests(TestCase):
    def setUp(self):
        call_command('seed_appointments_catalog', stdout=StringIO())
        real_now = timezone.now() - timedelta(days=2)
        # Day <= 28 keeps month arithmetic in assertions trivial; still in the past.
        self.start = real_now.replace(day=min(real_now.day, 28), minute=0, second=0, microsecond=0)
        self.end = _add_months(self.start, 6)
        self.admin = _superadmin()
        self.business, self.subscription = self.make_grant('appointments_ai', 'ai_300')
        self.conversation = 'wac1_' + uuid.uuid4().hex
        self.channel, self.credential = self.make_agent(self.business, self.conversation)
        self.client = APIClient()

    def make_grant(self, plan_code, usage_tier, *, start=None, end=None):
        business = Business.objects.create(
            name='Piloto', slug=f'piloto-{uuid.uuid4().hex[:10]}',
            service_type='appointments', default_service='appointments', status='onboarding',
        )
        sub = grant_complimentary_access(
            business=business, plan_code=plan_code, service_type='appointments',
            starts_at=start or self.start, ends_at=end or self.end,
            granted_by=self.admin, reason='Piloto', usage_tier=usage_tier,
        )
        business.refresh_from_db()
        return business, sub

    def make_agent(self, business, conversation):
        instance = make_instance(f'agent-{uuid.uuid4().hex[:12]}')
        channel = make_channel(instance, business, phone_number_id=str(uuid.uuid4().int)[:20])
        lead = Lead.objects.create(business=business, source='whatsapp_agent')
        make_state(lead, channel, external_conversation_id=conversation)
        return channel, make_credential(instance, key_id=uuid.uuid4().hex)

    def post(self, at, *, interaction=None, occurred=None, conversation=None, credential=None):
        body = encode({
            'external_conversation_id': conversation or self.conversation,
            'interaction_id': str(interaction or uuid.uuid4()),
            'occurred_at': (occurred or at).isoformat(),
        })
        headers = sign_headers(path=PATH, body=body, key_id=(credential or self.credential).key_id,
                               secret=SECRET, method='POST')
        with patch('apps.appointments.services.ai_usage_authorization.timezone.now', return_value=at):
            response = self.client.generic('POST', PATH, data=body, content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def seed_usage(self, count, period_start, period_end):
        AppointmentAIUsageSession.objects.bulk_create([
            AppointmentAIUsageSession(
                business=self.business, subscription=self.subscription,
                external_conversation_id=f'seed-{uuid.uuid4().hex}', opening_interaction_id=uuid.uuid4(),
                started_at=period_start, expires_at=period_start + timedelta(hours=24),
                usage_period_start=period_start, usage_period_end=period_end, usage_tier='ai_300',
            ) for _ in range(count)
        ])

    def assert_untouched_grant(self):
        sub = SubscriptionV2.objects.get(pk=self.subscription.pk)
        self.assertEqual(
            (sub.provider, sub.status, sub.billing_cycle, sub.usage_tier, sub.current_period_end),
            ('manual', 'trialing', '', 'ai_300', self.end),
        )

    # ── first conversation, retry ─────────────────────────────────────────
    def test_first_conversation_is_authorized_and_counted_once(self):
        at = self.start + timedelta(hours=5)
        month_end = _add_months(self.start, 1)
        with patch('apps.appointments.services.ai_usage_authorization.timezone.now', return_value=at):
            before = get_appointments_ai_usage(self.business, at=at)
        self.assertEqual((before['used'], before['included'], before['period_end']), (0, 300, month_end))

        interaction = uuid.uuid4()
        first = self.post(at, interaction=interaction)
        self.assertTrue(first['allowed'])
        self.assertTrue(first['created'])
        self.assertEqual((first['used'], first['included'], first['remaining']), (1, 300, 299))

        retry = self.post(at + timedelta(minutes=3), interaction=interaction, occurred=at)
        self.assertEqual((retry['allowed'], retry['created'], retry['session_id'], retry['used']),
                         (True, False, first['session_id'], 1))
        self.assertEqual(AppointmentAIUsageAuthorization.objects.count(), 1)
        charge = AppointmentAIUsageCharge.objects.get()
        self.assertEqual((charge.classification, charge.amount), ('included', 0))
        self.assertEqual(self.business.status, 'trialing')
        self.assert_untouched_grant()

    # ── tier limit (hard cap, no overage) ─────────────────────────────────
    def test_tier_is_a_hard_cap_without_overage(self):
        month_end = _add_months(self.start, 1)
        self.seed_usage(300, self.start, month_end)
        at = self.start + timedelta(days=3)
        policy = resolve_ai_usage_policy(self.business, at=at)
        self.assertEqual((policy['max_overage_sessions'], policy['can_start_new_session']), (0, False))
        self.assertEqual(self.post(at), {'allowed': False, 'reason': 'hard_cap_reached'})
        self.assertFalse(AppointmentAIUsageCharge.objects.exists())

    # ── monthly renewal and clipped last period ───────────────────────────
    def test_next_month_starts_a_fresh_allowance(self):
        self.seed_usage(300, self.start, _add_months(self.start, 1))
        at = _add_months(self.start, 1) + timedelta(hours=1)
        body = self.post(at)
        self.assertTrue(body['allowed'])
        self.assertEqual(body['used'], 1)
        self.assertEqual(body['period_start'].replace('Z', '+00:00'), _add_months(self.start, 1).isoformat())

    def test_six_contiguous_monthly_periods_ending_at_the_grant_end(self):
        cursor, periods = self.start, []
        while cursor < self.end:
            period = resolve_appointments_ai_usage_period(self.subscription, at=cursor)
            self.assertEqual(period[0], cursor)
            periods.append(period)
            cursor = period[1]
        self.assertEqual(len(periods), 6)
        self.assertEqual(periods[-1][1], self.end)

    def test_short_grant_clips_the_period_at_its_end(self):
        end = self.start + timedelta(days=10)
        business, sub = self.make_grant('appointments_ai', 'ai_300', end=end)
        self.assertEqual(
            resolve_appointments_ai_usage_period(sub, at=self.start + timedelta(days=1)), (self.start, end),
        )

    # ── outside the benefit ───────────────────────────────────────────────
    def test_expired_grant_is_blocked(self):
        self.assertFalse(self.post(self.end + timedelta(hours=1))['allowed'])
        self.assertFalse(self.post(self.end)['allowed'])
        self.assertFalse(AppointmentAIUsageSession.objects.exists())

    def test_future_grant_is_blocked(self):
        start = timezone.now().replace(microsecond=0) + timedelta(days=5)
        business, sub = self.make_grant('appointments_ai', 'ai_300', start=start, end=start + timedelta(days=30))
        conversation = 'wac1_' + uuid.uuid4().hex
        _, credential = self.make_agent(business, conversation)
        now = timezone.now()
        self.assertFalse(subscription_lifecycle_access(sub, at=now))
        body = self.post(now, conversation=conversation, credential=credential)
        self.assertFalse(body['allowed'])

    def test_revoked_or_suspended_grant_is_blocked(self):
        at = self.start + timedelta(hours=5)
        for status in ('canceled', 'suspended'):
            with self.subTest(status=status):
                SubscriptionV2.objects.filter(pk=self.subscription.pk).update(status=status)
                self.assertFalse(self.post(at)['allowed'])
        self.assertFalse(AppointmentAIUsageSession.objects.exists())

    def test_other_business_conversation_and_bad_signature_stay_isolated(self):
        other, _ = self.make_grant('appointments_ai', 'ai_300')
        other_conversation = 'wac1_' + uuid.uuid4().hex
        self.make_agent(other, other_conversation)
        at = self.start + timedelta(hours=5)
        # This agent's credential cannot authorize another agent/business conversation.
        self.assertEqual(self.post(at, conversation=other_conversation),
                         {'allowed': False, 'reason': 'unsafe_conversation_context'})
        body = encode({'external_conversation_id': self.conversation,
                       'interaction_id': str(uuid.uuid4()), 'occurred_at': at.isoformat()})
        headers = sign_headers(path=PATH, body=body, key_id=self.credential.key_id,
                               secret='wrong-secret-' + 'x' * 32, method='POST')
        response = self.client.generic('POST', PATH, data=body, content_type='application/json', **headers)
        self.assertEqual(response.status_code, 401)

    # ── controls ──────────────────────────────────────────────────────────
    def test_conventional_turnos_grant_has_no_ai_but_can_operate(self):
        business, sub = self.make_grant('appointments', None)
        conversation = 'wac1_' + uuid.uuid4().hex
        _, credential = self.make_agent(business, conversation)
        body = self.post(self.start + timedelta(hours=5), conversation=conversation, credential=credential)
        self.assertFalse(body['allowed'])
        self.assertTrue(appointments_v2_allows_creation(business))

    def test_mercadopago_trial_keeps_previous_lifecycle(self):
        sub = SubscriptionV2(
            business=self.business, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_300', provider='mercadopago', status='trialing',
            current_period_start=self.start, current_period_end=self.end,
        )
        self.assertFalse(subscription_lifecycle_access(sub, at=self.start + timedelta(hours=1)))

    def test_manual_trial_with_trial_end_is_not_a_complimentary_grant(self):
        sub = SubscriptionV2(
            business=self.business, service_type='appointments', plan_code='appointments_ai',
            usage_tier='ai_300', provider='manual', status='trialing', billing_cycle='monthly',
            trial_ends_at=self.end, current_period_start=self.start, current_period_end=self.end,
        )
        self.assertFalse(subscription_lifecycle_access(sub, at=self.start + timedelta(hours=1)))

    def test_paid_monthly_ai_subscription_is_unchanged(self):
        business = Business.objects.create(name='Pago', slug=f'pago-{uuid.uuid4().hex[:8]}', status='active')
        sub = SubscriptionV2.objects.create(
            business=business, service_type='appointments', plan_code='appointments_ai', usage_tier='ai_300',
            billing_cycle='monthly', provider='mercadopago', external_reference=f'SUB-{uuid.uuid4()}',
            status='active', is_active=True, current_period_start=self.start,
            current_period_end=_add_months(self.start, 1),
        )
        conversation = 'wac1_' + uuid.uuid4().hex
        _, credential = self.make_agent(business, conversation)
        body = self.post(self.start + timedelta(hours=5), conversation=conversation, credential=credential)
        self.assertTrue(body['allowed'])
        self.assertEqual(body['period_end'].replace('Z', '+00:00'), sub.current_period_end.isoformat())
        policy = resolve_ai_usage_policy(business, at=self.start + timedelta(hours=5))
        self.assertGreater(policy['max_overage_sessions'], 0)
