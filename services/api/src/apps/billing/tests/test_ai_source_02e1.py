"""PROD-02E1 — Resolvedor único de la fuente IA (actualizado en PROD-02E2A).

Fuentes: Recepcionista (`reception`/`reception`) y Turnos IA
(`appointments`/`appointments_ai`). Una sola elegible → esa; ninguna →
fail-closed; dos → `ambiguous_ai_source`. Desde PROD-02E2A Recepcionista
consume sus cupos fijos sin excedentes; un cupo indefinido nunca es ilimitado.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import AppointmentAIUsageAuthorization, AppointmentAIUsageSession
from apps.appointments.services.ai_usage import (
    AIUsageUnavailable, get_appointments_ai_usage, resolve_ai_usage_limit,
)
from apps.billing.models import SubscriptionV2
from apps.billing.services.ai_source import (
    AMBIGUOUS_AI_SOURCE, APPOINTMENTS_AI_SOURCE, MANUAL_CONTRACT, NO_AI_ENTITLEMENT, RECEPTION_SOURCE,
    USAGE_POLICY_UNDEFINED, resolve_ai_source,
)
from apps.billing.services.appointments_checkout import ManualContractRequired
from apps.billing.tests.test_reception_service_02b import _business, _superadmin
from apps.leads.models import Lead
from apps.leads.tests.agent_client import encode, sign_headers
from apps.leads.tests.factories import SECRET, TEST_KEY, make_channel, make_credential, make_instance, make_state

PATH = '/api/internal/appointments/ai-usage/authorize/'


def _add_months(value, months):
    month = value.month - 1 + months
    return value.replace(year=value.year + month // 12, month=month % 12 + 1)


class _Fixtures:

    def setUp(self):
        real = timezone.now() - timedelta(days=2)
        self.start = real.replace(day=min(real.day, 28), minute=0, second=0, microsecond=0)
        self.at = self.start + timedelta(hours=5)

    def sub(self, biz, service_type, plan_code, usage_tier=None, **extra):
        defaults = dict(
            billing_cycle='monthly', provider='mercadopago', status='active', is_active=True,
            current_period_start=self.start, current_period_end=_add_months(self.start, 1),
        )
        defaults.update(extra)
        return SubscriptionV2.objects.create(
            business=biz, service_type=service_type, plan_code=plan_code, usage_tier=usage_tier,
            external_reference=f'SUB-{uuid.uuid4()}', **defaults,
        )

    def turnos_ia(self, biz, **extra):
        return self.sub(biz, 'appointments', 'appointments_ai', 'ai_300', **extra)

    def reception(self, biz, tier='reception_300', **extra):
        return self.sub(biz, 'reception', 'reception', tier, **extra)

    def resolve(self, biz, at=None):
        return resolve_ai_source(biz, at=at or self.at)


# ── Resolución y elegibilidad ────────────────────────────────────────────────

class AISourceResolutionTests(_Fixtures, TestCase):

    def test_turnos_ia_is_the_single_source_with_a_configured_policy(self):
        biz = _business(service='appointments')
        sub = self.turnos_ia(biz)
        result = self.resolve(biz)
        self.assertEqual((result.source, result.subscription, result.reason), (APPOINTMENTS_AI_SOURCE, sub, None))
        self.assertTrue(result.eligible)
        self.assertTrue(result.policy_configured)

    def test_reception_is_eligible_with_its_fixed_policy(self):
        # PROD-02E2A: reception_300/1500/3000 carry an internal fixed allowance.
        biz = _business()
        sub = self.reception(biz)
        result = self.resolve(biz)
        self.assertEqual((result.source, result.subscription, result.reason), (RECEPTION_SOURCE, sub, None))
        self.assertTrue(result.policy_configured)
        self.assertIsNone(result.policy_reason)
        custom = _business()
        self.reception(custom, tier='reception_custom')
        self.assertEqual(self.resolve(custom).policy_reason, MANUAL_CONTRACT)

    def test_reception_source_whatever_the_principal_service(self):
        cases = {
            'gestion principal': ('gestion', [lambda b: self.sub(b, 'gestion', 'pro')]),
            'turnos base': ('appointments', [lambda b: self.sub(b, 'appointments', 'appointments_base')]),
            'turnos pro': ('appointments', [lambda b: self.sub(b, 'appointments', 'appointments_pro')]),
            'reception principal + turnos pro': ('reception', [lambda b: self.sub(b, 'appointments', 'appointments_pro')]),
        }
        for name, (principal, makers) in cases.items():
            with self.subTest(name):
                biz = _business(service=principal)
                for make in makers:
                    make(biz)
                sub = self.reception(biz)
                result = self.resolve(biz)
                self.assertEqual((result.source, result.subscription), (RECEPTION_SOURCE, sub))

    def test_reception_plus_turnos_ia_is_ambiguous(self):
        biz = _business(service='appointments')
        self.turnos_ia(biz)
        self.reception(biz)
        result = self.resolve(biz)
        self.assertEqual(result.reason, AMBIGUOUS_AI_SOURCE)
        self.assertIsNone(result.subscription)
        self.assertEqual({c.source for c in result.candidates}, {RECEPTION_SOURCE, APPOINTMENTS_AI_SOURCE})
        with self.assertRaises(AIUsageUnavailable) as ctx:
            get_appointments_ai_usage(biz, at=self.at)
        self.assertEqual(ctx.exception.reason, AMBIGUOUS_AI_SOURCE)

    def test_one_ineligible_source_leaves_the_other(self):
        biz = _business(service='appointments')
        self.turnos_ia(biz)
        self.reception(biz, status=SubscriptionV2.Status.SUSPENDED)
        self.assertEqual(self.resolve(biz).source, APPOINTMENTS_AI_SOURCE)
        other = _business()
        self.turnos_ia(other, status=SubscriptionV2.Status.SUSPENDED)
        self.reception(other)
        self.assertEqual(self.resolve(other).source, RECEPTION_SOURCE)

    def test_no_source_fails_closed(self):
        cases = {
            'turnos pro without AI': lambda b: self.sub(b, 'appointments', 'appointments_pro'),
            'gestion only': lambda b: self.sub(b, 'gestion', 'pro'),
            'nothing': lambda b: None,
        }
        for name, make in cases.items():
            with self.subTest(name):
                biz = _business(service='gestion')
                make(biz)
                result = self.resolve(biz)
                self.assertIsNone(result.subscription)
                self.assertEqual(result.reason, NO_AI_ENTITLEMENT)

    def test_canceled_suspended_and_pending_are_never_sources(self):
        for status_ in (SubscriptionV2.Status.CANCELED, SubscriptionV2.Status.CHECKOUT_PENDING,
                        SubscriptionV2.Status.SUSPENDED):
            for maker in (self.reception, self.turnos_ia):
                with self.subTest(status=status_, source=maker.__name__):
                    biz = _business()
                    maker(biz, status=status_)
                    result = self.resolve(biz)
                    self.assertIsNone(result.subscription)
                    self.assertIn(result.reason, (NO_AI_ENTITLEMENT, 'suspended'))

    def test_benefits_only_inside_their_window(self):
        for maker in (self.reception, self.turnos_ia):
            with self.subTest(source=maker.__name__):
                biz = _business()
                biz.status = 'trialing'
                biz.save(update_fields=['status'])
                start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
                maker(biz, provider='manual', status=SubscriptionV2.Status.TRIALING, billing_cycle='',
                      current_period_start=start, current_period_end=start + timedelta(days=30),
                      manual_granted_by=_superadmin(), manual_grant_reason='Beneficio')
                with patch('django.utils.timezone.now', return_value=start - timedelta(seconds=1)):
                    self.assertIsNone(self.resolve(biz, at=start - timedelta(seconds=1)).subscription)
                with patch('django.utils.timezone.now', return_value=start + timedelta(hours=1)):
                    self.assertIsNotNone(self.resolve(biz, at=start + timedelta(hours=1)).subscription)
                end = start + timedelta(days=30)
                with patch('django.utils.timezone.now', return_value=end):
                    self.assertIsNone(self.resolve(biz, at=end).subscription)

    def test_invalid_plan_or_tier_is_never_a_source(self):
        wrong_plan = _business()
        self.sub(wrong_plan, 'reception', 'pro')
        self.assertIsNone(self.resolve(wrong_plan).subscription)
        mislabeled = _business(service='gestion')
        self.sub(mislabeled, 'gestion', 'reception', 'reception_300')
        self.assertIsNone(self.resolve(mislabeled).subscription)
        bad_tier = _business()
        sub = self.reception(bad_tier)
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier='ai_300')
        result = self.resolve(bad_tier)
        self.assertIsNone(result.subscription)
        self.assertIn(result.reason, ('invalid_tier', 'suspended', NO_AI_ENTITLEMENT))

    def test_business_status_still_gates_consumption(self):
        biz = _business()
        self.reception(biz)
        biz.status = 'suspended'
        biz.save(update_fields=['status'])
        self.assertIsNone(self.resolve(biz).subscription)

    def test_sources_are_isolated_between_businesses(self):
        a, b = _business(), _business()
        self.reception(a)
        self.assertEqual(self.resolve(a).source, RECEPTION_SOURCE)
        self.assertIsNone(self.resolve(b).subscription)

    def test_resolver_error_fails_closed(self):
        biz = _business()
        self.reception(biz)
        with patch('apps.billing.runtime.resolve_subscription', side_effect=RuntimeError('boom')):
            result = self.resolve(biz)
        self.assertIsNone(result.subscription)
        self.assertEqual(result.reason, NO_AI_ENTITLEMENT)


# ── Cupo indefinido: nunca ilimitado ─────────────────────────────────────────

class UndefinedAllowanceTests(_Fixtures, TestCase):

    def _with_tier(self, code, **changes):
        from apps.billing import canonical_pricing

        real = canonical_pricing.get_usage_tier

        def patched(tier_code):
            tier = real(tier_code)
            return {**tier, **changes} if tier_code == code else tier

        return patch.object(canonical_pricing, 'get_usage_tier', side_effect=patched)

    def test_fixed_allowances(self):
        for tier, included in (('reception_300', 300), ('reception_1500', 1500), ('reception_3000', 3000)):
            with self.subTest(tier=tier):
                self.assertEqual(resolve_ai_usage_limit(self.reception(_business(), tier=tier)), included)

    def test_undefined_allowance_is_never_unlimited(self):
        sub = self.reception(_business())
        for changes in ({'included_conversations': None}, {'included_conversations': 0}):
            with self.subTest(changes=changes), self._with_tier('reception_300', **changes):
                with self.assertRaises(AIUsageUnavailable) as ctx:
                    resolve_ai_usage_limit(sub)
                self.assertEqual(ctx.exception.reason, USAGE_POLICY_UNDEFINED)
                self.assertFalse(self.resolve(sub.business).policy_configured)

    def test_any_overage_policy_fails_closed(self):
        sub = self.reception(_business())
        for changes in ({'default_extra_spend_limit': 75000}, {'extra_conversation_price': 300},
                        {'purchase_mode': 'self_service'}, {'default_extra_spend_limit': None}):
            with self.subTest(changes=changes), self._with_tier('reception_300', **changes):
                with self.assertRaises(AIUsageUnavailable) as ctx:
                    resolve_ai_usage_limit(sub)
                self.assertEqual(ctx.exception.reason, USAGE_POLICY_UNDEFINED)

    def test_custom_tier_requires_manual_contract(self):
        sub = self.reception(_business(), tier='reception_custom')
        with self.assertRaises(ManualContractRequired):
            resolve_ai_usage_limit(sub)

    def test_kill_switch_blocks_reception(self):
        sub = self.reception(_business())
        with patch('apps.appointments.services.ai_usage.RECEPTION_AI_CONSUMPTION_ENABLED', False):
            with self.assertRaises(AIUsageUnavailable) as ctx:
                resolve_ai_usage_limit(sub)
        self.assertEqual(ctx.exception.reason, USAGE_POLICY_UNDEFINED)


# ── Integración con el endpoint del agente ───────────────────────────────────

@override_settings(AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class AgentAuthorizationIntegrationTests(_Fixtures, TestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def agent(self, biz):
        conversation = 'wac1_' + uuid.uuid4().hex
        instance = make_instance(f'agent-{uuid.uuid4().hex[:12]}')
        channel = make_channel(instance, biz, phone_number_id=str(uuid.uuid4().int)[:20])
        lead = Lead.objects.create(business=biz, source='whatsapp_agent')
        make_state(lead, channel, external_conversation_id=conversation)
        return conversation, make_credential(instance, key_id=uuid.uuid4().hex)

    def authorize(self, biz):
        conversation, credential = self.agent(biz)
        body = encode({
            'external_conversation_id': conversation,
            'interaction_id': str(uuid.uuid4()),
            'occurred_at': self.at.isoformat(),
        })
        headers = sign_headers(path=PATH, body=body, key_id=credential.key_id, secret=SECRET, method='POST')
        with patch('apps.appointments.services.ai_usage_authorization.timezone.now', return_value=self.at):
            response = self.client.generic('POST', PATH, data=body, content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_turnos_ia_still_authorized_and_counted(self):
        biz = _business(service='appointments')
        self.turnos_ia(biz)
        body = self.authorize(biz)
        self.assertTrue(body['allowed'], body)
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 1)

    def test_reception_authorized_whatever_the_principal(self):
        for name, principal, extra in (
            ('reception only', 'reception', None),
            ('gestion + reception', 'gestion', lambda b: self.sub(b, 'gestion', 'pro')),
            ('reception + turnos pro', 'reception', lambda b: self.sub(b, 'appointments', 'appointments_pro')),
        ):
            with self.subTest(name):
                biz = _business(service=principal)
                if extra:
                    extra(biz)
                sub = self.reception(biz)
                body = self.authorize(biz)
                self.assertTrue(body['allowed'], body)
                self.assertEqual(
                    list(AppointmentAIUsageSession.objects.filter(business=biz).values_list('subscription_id', flat=True)),
                    [sub.pk],
                )

    def test_reception_custom_blocked_and_records_nothing(self):
        biz = _business()
        self.reception(biz, tier='reception_custom')
        body = self.authorize(biz)
        self.assertEqual((body['allowed'], body['reason']), (False, MANUAL_CONTRACT))
        self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())
        self.assertFalse(AppointmentAIUsageAuthorization.objects.filter(business=biz).exists())

    def test_reception_plus_turnos_ia_never_double_counts(self):
        biz = _business(service='appointments')
        self.turnos_ia(biz)
        self.reception(biz)
        body = self.authorize(biz)
        self.assertEqual((body['allowed'], body['reason']), (False, AMBIGUOUS_AI_SOURCE))
        self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())
