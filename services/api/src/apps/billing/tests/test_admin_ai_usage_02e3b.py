"""PROD-02E3B — Consumo y políticas IA desde Platform Admin (solo lectura).

Resumen comercial = el mismo servicio de PROD-02E3A + suscripción fuente y
diagnóstico interno; historial desde sesiones y cargos registrados (snapshots
históricos); políticas Recepcionista Custom y su historial de cambios.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.test_reception_rbac_02c import _client, _member
from apps.appointments.models import AppointmentAIUsageCharge, AppointmentAIUsageSession
from apps.billing.models import SubscriptionV2
from apps.billing.services.reception_ai_policy import (
    change_reception_custom_allowance, create_reception_custom_policy, revoke_reception_custom_policy,
)
from apps.billing.tests.test_reception_ai_consumption_02e2a import AI_SETTINGS, _add_months, _Base
from apps.billing.tests.test_reception_service_02b import _business, _superadmin

User = get_user_model()


def base(business_id):
    return f'/api/v1/platform-admin/clients/{business_id}/ai-usage/'


def _staff(role):
    user = User.objects.create_user(username=f'{role}-{uuid.uuid4().hex}', email=f'{uuid.uuid4().hex}@x.test')
    profile = user.account_profile
    profile.is_platform_staff, profile.internal_role = True, role
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


class _AdminBase(_Base):

    def setUp(self):
        super().setUp()
        self.admin = _superadmin()
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def overview(self, biz, client=None, expected=200, suffix=''):
        response = (client or self.api).get(base(biz.pk) + suffix)
        self.assertEqual(response.status_code, expected, response.content)
        return response.json() if expected == 200 else response

    def diag(self, biz):
        return self.overview(biz)['diagnosis']['code']

    def custom(self, biz=None, included=None, **extra):
        biz = biz or _business()
        sub = self.reception(biz, tier='reception_custom', **extra)
        if included is not None:
            create_reception_custom_policy(subscription=sub, included_sessions=included, actor=self.admin,
                                           reason='Acuerdo inicial', now=self.start)
        return biz, sub

    def charged(self, sub, count, period_start, period_end, snapshot, ordinal_from=1, tier=None):
        for i in range(count):
            session = AppointmentAIUsageSession.objects.create(
                business=sub.business, subscription=sub, external_conversation_id=f'h-{uuid.uuid4().hex}',
                opening_interaction_id=uuid.uuid4(), started_at=period_start,
                expires_at=period_start + timedelta(hours=24), usage_period_start=period_start,
                usage_period_end=period_end, usage_tier=tier or sub.usage_tier,
            )
            AppointmentAIUsageCharge.objects.create(
                session=session, business=sub.business, subscription=sub, usage_period_start=period_start,
                usage_period_end=period_end, usage_tier=tier or sub.usage_tier, session_ordinal=ordinal_from + i,
                included_sessions_snapshot=snapshot, classification='included', unit_price=0, amount=0,
                currency='ARS',
            )


# ── Seguridad ────────────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class AdminAccessTests(_AdminBase, TestCase):

    def test_platform_roles(self):
        biz = _business()
        self.reception(biz)
        for role, expected in (('superadmin', 200), ('operations', 200), ('support_agent', 403),
                               ('content_admin', 403)):
            client = APIClient()
            client.force_authenticate(_staff(role))
            for suffix in ('', 'history/', 'policies/'):
                with self.subTest(role=role, suffix=suffix):
                    self.assertEqual(client.get(base(biz.pk) + suffix).status_code, expected)

    def test_merchant_users_and_anonymous_are_denied(self):
        biz = _business()
        self.reception(biz)
        for role in ('owner', 'admin'):
            with self.subTest(role=role):
                client = _client(_member(biz, role))
                for suffix in ('', 'history/', 'policies/'):
                    self.assertEqual(client.get(base(biz.pk) + suffix).status_code, 403)
        self.assertIn(APIClient().get(base(biz.pk)).status_code, (401, 403))
        # Internal role without the platform staff flag is not enough.
        user = _staff('superadmin')
        user.account_profile.is_platform_staff = False
        user.account_profile.save(update_fields=['is_platform_staff'])
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.get(base(biz.pk)).status_code, 403)

    def test_unknown_or_branch_business_is_404_and_writes_are_405(self):
        self.assertEqual(self.api.get(base(999999999)).status_code, 404)
        biz = _business()
        for method in ('post', 'put', 'patch', 'delete'):
            for suffix in ('', 'history/', 'policies/'):
                with self.subTest(method=method, suffix=suffix):
                    self.assertEqual(getattr(self.api, method)(base(biz.pk) + suffix, {}, format='json').status_code, 405)


# ── Resumen y diagnóstico ────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class AdminOverviewTests(_AdminBase, TestCase):

    def test_fixed_reception_matches_the_merchant_api(self):
        biz = _business()
        sub = self.reception(biz, tier='reception_1500')
        self.seed(sub, 4)
        body = self.overview(biz)
        merchant = _client(_member(biz, 'owner')).get('/api/v1/ai-usage/').json()
        for payload in (body['summary'], merchant):
            payload.pop('evaluated_at')
        self.assertEqual(body['summary'], merchant)
        self.assertEqual((body['diagnosis']['code'], body['scope']), ('ok', 'commercial_authorization_only'))
        self.assertEqual(body['source_subscription']['id'], str(sub.pk))
        self.assertEqual((body['source_subscription']['product'], body['source_subscription']['usage_tier'],
                          body['source_subscription']['status']), ('reception', 'reception_1500', 'active'))
        for leaked in ('provider_sub_id', 'external_reference', 'raw_snapshot_json', 'manual_granted_by'):
            self.assertNotIn(leaked, body['source_subscription'])

    def test_custom_and_turnos_ia(self):
        biz, sub = self.custom(included=9)
        body = self.overview(biz)
        self.assertEqual((body['summary']['source']['policy_kind'], body['summary']['sessions']['included'],
                          body['diagnosis']['code']), ('custom', 9, 'ok'))
        biz = _business(service='appointments')
        turnos = self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        body = self.overview(biz)
        self.assertEqual((body['summary']['source']['product'], body['summary']['overage']['enabled'],
                          body['source_subscription']['id']), ('appointments_ai', True, str(turnos.pk)))

    def test_lifecycle_diagnoses(self):
        cases = {
            'no_ai_subscription': lambda b: None,
            'subscription_suspended': lambda b: self.reception(b, status='suspended'),
            'subscription_canceled': lambda b: self.reception(b, status='canceled'),
            'invalid_tier': lambda b: SubscriptionV2.objects.filter(pk=self.reception(b).pk).update(usage_tier='ai_300'),
        }
        for code, make in cases.items():
            with self.subTest(code):
                biz = _business()
                make(biz)
                body = self.overview(biz)
                self.assertEqual(body['diagnosis']['code'], code)
                self.assertFalse(body['summary']['can_start_new_session'])
        self.assertEqual(self.overview(_business())['summary']['status'], 'not_contracted')

    def test_benefit_not_started_and_expired(self):
        now = timezone.now()
        for code, start, end in (('benefit_not_started', now + timedelta(days=1), now + timedelta(days=30)),
                                 ('benefit_expired', now - timedelta(days=40), now - timedelta(days=1))):
            with self.subTest(code):
                biz = _business()
                biz.status = 'trialing'
                biz.save(update_fields=['status'])
                self.reception(biz, provider='manual', status='trialing', billing_cycle='',
                               current_period_start=start, current_period_end=end,
                               manual_granted_by=self.admin, manual_grant_reason='Beneficio')
                self.assertEqual(self.diag(biz), code)

    def test_custom_policy_diagnoses(self):
        biz, _ = self.custom()
        self.assertEqual(self.diag(biz), 'custom_policy_missing')
        biz, sub = self.custom(included=3)
        revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja')
        self.assertEqual(self.diag(biz), 'custom_policy_revoked')
        biz, sub = self.custom()
        create_reception_custom_policy(subscription=sub, included_sessions=3, actor=self.admin, reason='x',
                                       now=self.start, valid_until=self.start + timedelta(hours=1))
        self.assertEqual(self.diag(biz), 'custom_policy_expired')
        biz, sub = self.custom()
        create_reception_custom_policy(subscription=sub, included_sessions=3, actor=self.admin, reason='x',
                                       valid_from=timezone.now() + timedelta(days=2))
        self.assertEqual(self.diag(biz), 'custom_policy_not_started')

    def test_exhausted_ambiguous_kill_switch_metering_and_resolution_error(self):
        biz, sub = self.custom(included=2)
        self.seed(sub, 2)
        body = self.overview(biz)
        self.assertEqual((body['summary']['status'], body['diagnosis']['code']), ('exhausted', 'quota_exhausted'))

        biz = _business(service='appointments')
        self.reception(biz)
        self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        body = self.overview(biz)
        self.assertEqual(body['diagnosis']['code'], 'ambiguous_ai_source')
        self.assertEqual({c['product'] for c in body['diagnosis']['candidates']}, {'reception', 'appointments_ai'})

        biz = _business()
        self.reception(biz)
        with patch('apps.appointments.services.ai_usage.RECEPTION_AI_CONSUMPTION_ENABLED', False):
            self.assertEqual(self.diag(biz), 'reception_kill_switch_disabled')
        with override_settings(AI_USAGE_METERING_ENABLED=False):
            self.assertEqual(self.diag(biz), 'metering_disabled')
        with patch('apps.billing.services.ai_source._candidate', side_effect=RuntimeError('boom')):
            body = self.overview(biz)
        self.assertEqual(body['diagnosis']['code'], 'resolution_error')
        self.assertNotIn('boom', str(body))

    def test_time_parameters_are_ignored(self):
        biz = _business()
        self.reception(biz)
        body = self.overview(biz, suffix='?now=2020-01-01T00:00:00Z&at=2020-01-01T00:00:00Z')
        evaluated = timezone.datetime.fromisoformat(body['evaluated_at'])
        self.assertLess(abs((timezone.now() - evaluated).total_seconds()), 60)


# ── Historial ────────────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class AdminHistoryTests(_AdminBase, TestCase):

    def test_history_uses_snapshots_and_survives_blocking(self):
        biz, sub = self.custom(included=3)
        previous = _add_months(self.start, -1)
        self.charged(sub, 2, previous, self.start, snapshot=10)  # allowance recorded then
        self.charged(sub, 3, self.start, self.end, snapshot=3)
        change_reception_custom_allowance(subscription=sub, included_sessions=5, actor=self.admin, reason='Más')
        self.charged(sub, 1, self.start, self.end, snapshot=5, ordinal_from=4)
        self.seed(sub, 1)  # a session without economic evidence
        revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja')
        SubscriptionV2.objects.filter(pk=sub.pk).update(status='canceled')
        self.assertFalse(self.overview(biz)['summary']['can_start_new_session'])

        body = self.overview(biz, suffix='history/')
        self.assertEqual(body['count'], 2)
        current, past = body['results']
        self.assertEqual(current['period'], {'start': self.start.isoformat(), 'end': self.end.isoformat()})
        self.assertEqual(current['engine_counted_sessions'], 5)
        (row,) = current['attributions']
        self.assertEqual((row['subscription_id'], row['subscription_status_now'], row['usage_tier']),
                         (str(sub.pk), 'canceled', 'reception_custom'))
        self.assertEqual((row['sessions'], row['sessions_without_charge']), (5, 1))
        self.assertIsNone(row['included_sessions_snapshot'])  # not reliably rebuildable
        self.assertEqual(row['charges']['included'], 4)
        (old,) = past['attributions']
        self.assertEqual(old['included_sessions_snapshot'], {'min': 10, 'max': 10})  # never today's 5

    def test_attribution_per_subscription_vs_engine_count(self):
        biz = _business(service='appointments')
        turnos = self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        self.charged(turnos, 2, self.start, self.end, snapshot=300)
        SubscriptionV2.objects.filter(pk=turnos.pk).update(status='suspended')
        reception = self.reception(biz)
        self.charged(reception, 1, self.start, self.end, snapshot=300, ordinal_from=3)
        (period,) = self.overview(biz, suffix='history/')['results']
        self.assertEqual(period['engine_counted_sessions'], 3)
        self.assertEqual(
            sorted((a['product'], a['sessions']) for a in period['attributions']),
            [('appointments_ai', 2), ('reception', 1)],
        )
        # The engine (and the summary) count all three against the current source.
        self.assertEqual(self.overview(biz)['summary']['sessions']['used'], 3)

    def test_pagination_and_isolation(self):
        biz = _business()
        sub = self.reception(biz)
        anchor = self.start
        for months in range(5):
            start = _add_months(anchor, -months)
            self.seed(sub, months + 1, start, _add_months(start, 1))
        other = _business()
        self.seed(self.reception(other), 9)
        body = self.overview(biz, suffix='history/?limit=2&offset=2')
        self.assertEqual((body['count'], body['limit'], body['offset'], len(body['results'])), (5, 2, 2, 2))
        self.assertEqual([r['engine_counted_sessions'] for r in body['results']], [3, 4])
        self.assertEqual(self.overview(biz, suffix='history/?limit=999')['limit'], 36)
        self.assertEqual(self.overview(biz, suffix='history/?limit=abc&offset=-3')['limit'], 12)
        all_rows = self.overview(biz, suffix='history/')['results']
        self.assertNotIn(9, [r['engine_counted_sessions'] for r in all_rows])
        self.assertEqual(self.overview(_business(), suffix='history/')['results'], [])


# ── Políticas ────────────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class AdminPoliciesTests(_AdminBase, TestCase):

    def test_current_scheduled_versions_and_changes(self):
        operator = _staff('operations')
        biz, sub = self.custom(included=10)
        change_reception_custom_allowance(subscription=sub, included_sessions=4, actor=operator, reason='Reducción pactada')
        body = self.overview(biz, suffix='policies/')
        self.assertEqual([v['included_sessions'] for v in body['current']], [10])
        self.assertEqual([(v['included_sessions'], v['valid_from']) for v in body['scheduled']],
                         [(4, self.end.isoformat())])
        changes = body['changes']['results']
        self.assertEqual(body['changes']['count'], 2)
        latest = changes[0]
        self.assertEqual((latest['action'], latest['previous_included_sessions'], latest['new_included_sessions'],
                          latest['effective_at'], latest['reason'], latest['actor']['id']),
                         ('reduction_scheduled', 10, 4, self.end.isoformat(), 'Reducción pactada', operator.pk))
        self.assertTrue(latest['recorded_at'])
        self.assertEqual(changes[1]['actor']['id'], self.admin.pk)

    def test_revoked_versions_and_pagination_and_isolation(self):
        biz, sub = self.custom(included=3)
        change_reception_custom_allowance(subscription=sub, included_sessions=6, actor=self.admin, reason='Más')
        revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja')
        other_biz, _ = self.custom(included=99)
        body = self.overview(biz, suffix='policies/?limit=2')
        self.assertEqual(body['current'], [])
        self.assertEqual(sorted(v['state'] for v in body['versions']), ['past', 'revoked'])
        revoked = next(v for v in body['versions'] if v['state'] == 'revoked')
        self.assertEqual((revoked['revoked_by']['id'], revoked['included_sessions']), (self.admin.pk, 6))
        self.assertEqual((body['changes']['count'], len(body['changes']['results'])), (3, 2))
        self.assertEqual(body['changes']['results'][0]['action'], 'revoked')
        self.assertNotIn(99, [v['included_sessions'] for v in body['versions']])
        self.assertEqual(self.overview(other_biz, suffix='policies/')['changes']['count'], 1)


# ── Solo lectura ─────────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class AdminReadOnlyTests(_AdminBase, TestCase):

    def test_no_writes_no_locks_and_no_store(self):
        biz, sub = self.custom(included=2)
        self.charged(sub, 2, self.start, self.end, snapshot=2)
        stamp = SubscriptionV2.objects.get(pk=sub.pk).updated_at
        with CaptureQueriesContext(connection) as queries:
            for suffix in ('', 'history/', 'policies/'):
                response = self.api.get(base(biz.pk) + suffix)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Cache-Control'], 'no-store')
        sql = ' '.join(q['sql'].upper() for q in queries.captured_queries)
        for verb in ('FOR UPDATE', 'INSERT ', 'UPDATE ', 'DELETE '):
            self.assertNotIn(verb, sql)
        self.assertEqual(SubscriptionV2.objects.get(pk=sub.pk).updated_at, stamp)
