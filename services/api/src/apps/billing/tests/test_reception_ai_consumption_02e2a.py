"""PROD-02E2A — Consumo IA de Recepcionista con cupos fijos y sin excedentes.

Reusa el motor de Turnos IA (sesión de 24 h por conversación, recibo por
interacción, locks) con la suscripción Recepcionista como fuente única. El cupo
incluido es el límite duro: al agotarlo `hard_cap_reached`, nunca `overage`.
"""
from __future__ import annotations

import threading
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
)
from apps.appointments.services.ai_usage import (
    AIUsageHardCapReached, AIUsageUnavailable, get_appointments_ai_usage,
)
from apps.appointments.services.ai_usage_authorization import authorize_ai_interaction
from apps.billing import canonical_pricing
from apps.billing.models import SubscriptionV2
from apps.billing.services.ai_source import AISourceResolution
from apps.billing.tests.test_reception_service_02b import _business, _superadmin
from apps.leads.models import Lead
from apps.leads.tests.agent_client import encode, sign_headers
from apps.leads.tests.factories import (
    SECRET, TEST_KEY, enable_reception_attention, make_channel, make_credential, make_instance, make_state,
)

PATH = '/api/internal/appointments/ai-usage/authorize/'
AI_SETTINGS = dict(AI_USAGE_METERING_ENABLED=True, AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)


def _add_months(value, months):
    month = value.month - 1 + months
    return value.replace(year=value.year + month // 12, month=month % 12 + 1)


class _Base:

    def setUp(self):
        real = timezone.now() - timedelta(days=3)
        self.start = real.replace(day=min(real.day, 28), minute=0, second=0, microsecond=0)
        self.end = _add_months(self.start, 1)
        self.at = self.start + timedelta(hours=5)
        self.client = APIClient()

    def sub(self, biz, service_type, plan_code, usage_tier=None, **extra):
        defaults = dict(billing_cycle='monthly', provider='mercadopago', status='active', is_active=True,
                        current_period_start=self.start, current_period_end=self.end)
        defaults.update(extra)
        return SubscriptionV2.objects.create(
            business=biz, service_type=service_type, plan_code=plan_code, usage_tier=usage_tier,
            external_reference=f'SUB-{uuid.uuid4()}', **defaults,
        )

    def reception(self, biz, tier='reception_300', **extra):
        return self.sub(biz, 'reception', 'reception', tier, **extra)

    def agent(self, biz, conversation=None):
        conversation = conversation or 'wac1_' + uuid.uuid4().hex
        instance = make_instance(f'agent-{uuid.uuid4().hex[:12]}')
        channel = make_channel(instance, biz, phone_number_id=str(uuid.uuid4().int)[:20])
        lead = Lead.objects.create(business=biz, source='whatsapp_agent')
        make_state(lead, channel, external_conversation_id=conversation)
        enable_reception_attention(biz)  # PROD-09C1
        return conversation, make_credential(instance, key_id=uuid.uuid4().hex), instance

    def authorize(self, credential, conversation, at, interaction=None, occurred=None):
        body = encode({
            'external_conversation_id': conversation,
            'interaction_id': str(interaction or uuid.uuid4()),
            'occurred_at': (occurred or at).isoformat(),
        })
        headers = sign_headers(path=PATH, body=body, key_id=credential.key_id, secret=SECRET, method='POST')
        with patch('apps.appointments.services.ai_usage_authorization.timezone.now', return_value=at):
            response = self.client.generic('POST', PATH, data=body, content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def seed(self, sub, count, period_start=None, period_end=None):
        period_start, period_end = period_start or self.start, period_end or self.end
        AppointmentAIUsageSession.objects.bulk_create([
            AppointmentAIUsageSession(
                business=sub.business, subscription=sub,
                external_conversation_id=f'seed-{uuid.uuid4().hex}', opening_interaction_id=uuid.uuid4(),
                started_at=period_start, expires_at=period_start + timedelta(hours=24),
                usage_period_start=period_start, usage_period_end=period_end, usage_tier=sub.usage_tier,
            ) for _ in range(count)
        ])


@override_settings(**AI_SETTINGS)
class ReceptionConsumptionTests(_Base, TestCase):

    def test_three_fixed_tiers_open_a_session_with_an_included_charge(self):
        for tier, included in (('reception_300', 300), ('reception_1500', 1500), ('reception_3000', 3000)):
            with self.subTest(tier=tier):
                biz = _business()
                sub = self.reception(biz, tier=tier)
                conversation, credential, _ = self.agent(biz)
                body = self.authorize(credential, conversation, self.at)
                self.assertTrue(body['allowed'], body)
                session = AppointmentAIUsageSession.objects.get(business=biz)
                self.assertEqual((session.subscription_id, session.usage_tier), (sub.pk, tier))
                self.assertEqual((session.usage_period_start, session.usage_period_end), (self.start, self.end))
                charge = AppointmentAIUsageCharge.objects.get(session=session)
                self.assertEqual(
                    (charge.classification, charge.unit_price, charge.amount, charge.included_sessions_snapshot),
                    ('included', 0, 0, included),
                )
                usage = get_appointments_ai_usage(biz, at=self.at)
                self.assertEqual((usage['used'], usage['included'], usage['remaining']), (1, included, included - 1))

    def test_window_reuse_new_window_and_replays(self):
        biz = _business()
        self.reception(biz)
        conversation, credential, _ = self.agent(biz)
        first = uuid.uuid4()
        self.assertTrue(self.authorize(credential, conversation, self.at, interaction=first)['allowed'])
        # Inside 24 h: same session, a new receipt, no new charge.
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(hours=3))['allowed'])
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 1)
        self.assertEqual(AppointmentAIUsageAuthorization.objects.filter(business=biz).count(), 2)
        # Exact replay: idempotent. Same id with another time: conflict.
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(hours=4),
                                       interaction=first, occurred=self.at)['allowed'])
        conflict = self.authorize(credential, conversation, self.at + timedelta(hours=4), interaction=first,
                                  occurred=self.at + timedelta(minutes=1))
        self.assertEqual((conflict['allowed'], conflict['reason']), (False, 'interaction_conflict'))
        self.assertEqual(AppointmentAIUsageAuthorization.objects.filter(business=biz).count(), 2)
        # After the window: a second session and a second included charge.
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(hours=25))['allowed'])
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 2)
        self.assertEqual(
            set(AppointmentAIUsageCharge.objects.filter(business=biz).values_list('classification', flat=True)),
            {'included'},
        )

    def test_exhausted_allowance_is_the_hard_cap_without_overage(self):
        biz = _business()
        sub = self.reception(biz)
        open_conversation, credential, _ = self.agent(biz)
        self.seed(sub, 299)
        self.assertTrue(self.authorize(credential, open_conversation, self.at)['allowed'])  # session 300
        other, other_credential, _ = self.agent(biz)
        denied = self.authorize(other_credential, other, self.at + timedelta(minutes=5))
        self.assertEqual((denied['allowed'], denied['reason']), (False, 'hard_cap_reached'))
        # The session already open keeps working inside its window.
        self.assertTrue(self.authorize(credential, open_conversation, self.at + timedelta(hours=2))['allowed'])
        self.assertFalse(AppointmentAIUsageCharge.objects.filter(business=biz, classification='overage').exists())
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 300)

    def test_db_refuses_a_reception_overage_charge(self):
        biz = _business()
        sub = self.reception(biz)
        conversation, credential, _ = self.agent(biz)
        self.authorize(credential, conversation, self.at)
        session = AppointmentAIUsageSession.objects.get(business=biz)
        AppointmentAIUsageCharge.objects.filter(session=session).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentAIUsageCharge.objects.create(
                session=session, business=biz, subscription=sub, usage_period_start=self.start,
                usage_period_end=self.end, usage_tier='reception_300', session_ordinal=301,
                included_sessions_snapshot=300, classification='overage', unit_price=300, amount=300,
                currency='ARS',
            )

    def test_benefit_window_is_strict_and_never_charges(self):
        admin = _superadmin()

        def grant(start, end):
            biz = _business()
            biz.status = 'trialing'
            biz.save(update_fields=['status'])
            sub = self.reception(biz, provider='manual', status='trialing', billing_cycle='',
                                 current_period_start=start, current_period_end=end,
                                 manual_granted_by=admin, manual_grant_reason='Beneficio')
            return biz, sub

        now = timezone.now()
        active_biz, active_sub = grant(self.start, self.start + timedelta(days=90))
        conversation, credential, _ = self.agent(active_biz)
        self.assertTrue(self.authorize(credential, conversation, self.at)['allowed'])
        session = AppointmentAIUsageSession.objects.get(business=active_biz)
        self.assertEqual((session.usage_period_start, session.usage_period_end), (self.start, _add_months(self.start, 1)))
        self.seed(active_sub, 299, self.start, _add_months(self.start, 1))
        other, other_credential, _ = self.agent(active_biz)
        self.assertEqual(self.authorize(other_credential, other, self.at)['reason'], 'hard_cap_reached')

        future_biz, _ = grant(now + timedelta(days=1), now + timedelta(days=30))
        conversation, credential, _ = self.agent(future_biz)
        self.assertFalse(self.authorize(credential, conversation, now)['allowed'])

        expired_biz, _ = grant(now - timedelta(days=40), now - timedelta(days=1))
        conversation, credential, _ = self.agent(expired_biz)
        self.assertFalse(self.authorize(credential, conversation, now - timedelta(hours=1))['allowed'])
        self.assertFalse(AppointmentAIUsageSession.objects.filter(business__in=[future_biz, expired_biz]).exists())

    def test_inactive_custom_and_invalid_sources_record_nothing(self):
        cases = {
            'suspended': lambda b: self.reception(b, status='suspended'),
            'canceled': lambda b: self.reception(b, status='canceled'),
            'checkout_pending': lambda b: self.reception(b, status='checkout_pending'),
            'custom': lambda b: self.reception(b, tier='reception_custom'),
            'invalid tier': lambda b: SubscriptionV2.objects.filter(pk=self.reception(b).pk).update(usage_tier='ai_300'),
            'ambiguous': lambda b: (self.reception(b), self.sub(b, 'appointments', 'appointments_ai', 'ai_300')),
        }
        expected = {'custom': 'manual_contract_required', 'ambiguous': 'ambiguous_ai_source'}
        for name, make in cases.items():
            with self.subTest(name):
                biz = _business()
                make(biz)
                conversation, credential, _ = self.agent(biz)
                body = self.authorize(credential, conversation, self.at)
                self.assertFalse(body['allowed'])
                if name in expected:
                    self.assertEqual(body['reason'], expected[name])
                self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())
                self.assertFalse(AppointmentAIUsageAuthorization.objects.filter(business=biz).exists())

    def test_businesses_are_isolated(self):
        full, empty = _business(), _business()
        full_sub = self.reception(full)
        self.reception(empty)
        self.seed(full_sub, 300)
        conversation, credential, _ = self.agent(full)
        self.assertEqual(self.authorize(credential, conversation, self.at)['reason'], 'hard_cap_reached')
        conversation, credential, _ = self.agent(empty)
        self.assertTrue(self.authorize(credential, conversation, self.at)['allowed'])

    def test_resolver_denial_cannot_be_bypassed_by_the_turnos_ia_path(self):
        biz = _business(service='appointments')
        self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        with patch('apps.billing.services.ai_source.resolve_ai_source',
                   return_value=AISourceResolution(None, None, 'no_ai_entitlement')):
            with self.assertRaises(AIUsageUnavailable) as ctx:
                get_appointments_ai_usage(biz, at=self.at)
        self.assertEqual(ctx.exception.reason, 'no_ai_entitlement')

    def test_source_change_never_reuses_another_subscriptions_session(self):
        biz = _business(service='appointments')
        turnos_ia = self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        conversation, credential, _ = self.agent(biz)
        first = uuid.uuid4()
        self.assertTrue(self.authorize(credential, conversation, self.at, interaction=first)['allowed'])
        # Turnos IA ends, Recepcionista becomes the single source.
        SubscriptionV2.objects.filter(pk=turnos_ia.pk).update(status='suspended')
        reception = self.reception(biz)
        replay = self.authorize(credential, conversation, self.at + timedelta(hours=1), interaction=first,
                                occurred=self.at)
        self.assertEqual((replay['allowed'], replay['reason']), (False, 'interaction_conflict'))
        fresh = self.authorize(credential, conversation, self.at + timedelta(hours=1))
        self.assertTrue(fresh['allowed'], fresh)
        self.assertEqual(
            sorted(AppointmentAIUsageSession.objects.filter(business=biz).values_list('subscription_id', flat=True)),
            sorted([turnos_ia.pk, reception.pk]),
        )

    def test_public_checkout_still_blocked(self):
        self.assertFalse(canonical_pricing.is_plan_product_active('reception'))
        response = self.client.post('/api/v1/billing/start-subscription', {
            'email': f'{uuid.uuid4().hex[:8]}@x.test', 'password': 'Secret-123456',
            'business_name': 'X', 'plan_code': 'reception',
        }, format='json')
        self.assertEqual(response.status_code, 400)


@override_settings(**AI_SETTINGS)
class LastSlotConcurrencyTests(_Base, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def test_two_conversations_race_for_the_last_included_session(self):
        biz = _business()
        sub = self.reception(biz)
        self.seed(sub, 299)
        agents = [self.agent(biz) for _ in range(2)]
        results, barrier = [], threading.Barrier(2)
        occurred = timezone.now() - timedelta(minutes=1)  # inside the 24 h window vs the real clock

        def run(conversation, instance):
            try:
                barrier.wait()
                authorize_ai_interaction(
                    agent_instance=instance, conversation_id=conversation,
                    interaction_id=uuid.uuid4(), occurred_at=occurred,
                )
                results.append('allowed')
            except AIUsageHardCapReached:
                results.append('hard_cap_reached')  # same mapping as the agent endpoint
            except AIUsageUnavailable as exc:
                results.append(exc.reason)
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(conv, inst)) for conv, _, inst in agents]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), ['allowed', 'hard_cap_reached'])
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 300)
        self.assertFalse(AppointmentAIUsageCharge.objects.filter(business=biz, classification='overage').exists())
