"""PROD-02E3A — Servicio compartido y API de consulta de consumo IA.

`GET /api/v1/ai-usage/` informa, para la fuente IA única del comercio
(Recepcionista IA o Turnos IA), exactamente lo que el motor decidiría para una
sesión nueva en el instante del servidor, sin locks ni escrituras.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
    AppointmentAIUsageSettlement,
)
from apps.billing import canonical_pricing
from apps.billing.models import ReceptionAIUsagePolicy, ReceptionAIUsagePolicyChange, SubscriptionV2
from apps.billing.services.reception_ai_policy import (
    change_reception_custom_allowance, create_reception_custom_policy, revoke_reception_custom_policy,
)
from apps.billing.tests.test_reception_ai_consumption_02e2a import AI_SETTINGS, _add_months, _Base
from apps.accounts.tests.test_reception_rbac_02c import _client, _member
from apps.billing.tests.test_reception_service_02b import _business, _superadmin

URL = '/api/v1/ai-usage/'


class _SummaryBase(_Base):

    def setUp(self):
        super().setUp()
        self.admin = _superadmin()

    def owner(self, biz):
        return _client(_member(biz, 'owner'))

    def get(self, biz, role='owner', expected=200, client=None, path=URL):
        response = (client or _client(_member(biz, role))).get(path)
        self.assertEqual(response.status_code, expected, response.content)
        return response.json()

    def custom(self, biz=None, included=None, **extra):
        biz = biz or _business()
        sub = self.reception(biz, tier='reception_custom', **extra)
        if included is not None:
            create_reception_custom_policy(subscription=sub, included_sessions=included, actor=self.admin,
                                           reason='Acuerdo', now=self.start)
        return biz, sub

    def turnos_ia(self, biz=None, **extra):
        biz = biz or _business(service='appointments')
        return biz, self.sub(biz, 'appointments', 'appointments_ai', 'ai_300', **extra)

    def engine_allows_new_session(self, biz):
        conversation, credential, _ = self.agent(biz)
        return self.authorize(credential, conversation, timezone.now())['allowed']


# ── Estados y contrato ───────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class SummaryContractTests(_SummaryBase, TestCase):

    def test_fixed_reception_tiers(self):
        for tier, included in (('reception_300', 300), ('reception_1500', 1500), ('reception_3000', 3000)):
            with self.subTest(tier=tier):
                biz = _business()
                self.reception(biz, tier=tier)
                body = self.get(biz)
                self.assertEqual((body['status'], body['reason'], body['can_start_new_session']),
                                 ('available', None, True))
                self.assertEqual(body['source'], {'product': 'reception', 'service_type': 'reception',
                                                  'plan_code': 'reception', 'usage_tier': tier,
                                                  'policy_kind': 'catalog'})
                self.assertEqual(body['sessions'], {'included': included, 'used': 0, 'available_included': included})
                self.assertEqual(body['hard_cap'], {'max_sessions': included, 'remaining_sessions': included})
                self.assertEqual(body['overage'], {'enabled': False, 'unit_price': None, 'spend_limit': 0,
                                                   'max_sessions': 0, 'used_sessions': 0, 'amount': 0,
                                                   'currency': 'ARS'})
                self.assertEqual(body['period'], {'start': self.start.isoformat(), 'end': self.end.isoformat()})
                self.assertEqual((body['unit'], body['contract_version'], body['scheduled_change']),
                                 ('ai_session_24h', 1, None))

    def test_custom_with_policy_and_without(self):
        biz, _ = self.custom(included=7)
        body = self.get(biz)
        self.assertEqual((body['status'], body['source']['policy_kind'], body['sessions']['included']),
                         ('available', 'custom', 7))
        biz, _ = self.custom()
        body = self.get(biz)
        self.assertEqual((body['status'], body['reason'], body['can_start_new_session']),
                         ('policy_not_configured', 'manual_contract_required', False))
        self.assertEqual(body['source']['usage_tier'], 'reception_custom')
        # Never an invented or unlimited allowance.
        self.assertEqual((body['period'], body['sessions'], body['hard_cap'], body['overage']), (None,) * 4)

    def test_partial_then_exhausted_is_not_a_suspension(self):
        biz, sub = self.custom(included=3)
        self.seed(sub, 2)
        body = self.get(biz)
        self.assertEqual((body['status'], body['sessions']), ('available', {'included': 3, 'used': 2, 'available_included': 1}))
        self.seed(sub, 1)
        body = self.get(biz)
        self.assertEqual((body['status'], body['reason'], body['can_start_new_session']),
                         ('exhausted', 'hard_cap_reached', False))
        self.assertEqual((body['sessions']['used'], body['sessions']['available_included'],
                          body['hard_cap']['remaining_sessions']), (3, 0, 0))

    def test_window_reuse_counts_one_session(self):
        biz = _business()
        self.reception(biz)
        conversation, credential, _ = self.agent(biz)
        now = timezone.now()
        self.authorize(credential, conversation, now - timedelta(hours=2))
        self.authorize(credential, conversation, now - timedelta(hours=1))
        self.assertEqual(self.get(biz)['sessions']['used'], 1)

    def test_previous_period_sessions_are_not_counted(self):
        biz = _business()
        sub = self.reception(biz)
        previous = _add_months(self.start, -1)
        self.seed(sub, 4, previous, self.start)
        self.seed(sub, 1)
        body = self.get(biz)
        self.assertEqual((body['sessions']['used'], body['period']['start']), (1, self.start.isoformat()))

    def test_increase_reduction_and_revocation(self):
        biz, sub = self.custom(included=3)
        self.seed(sub, 3)
        self.assertEqual(self.get(biz)['status'], 'exhausted')
        change_reception_custom_allowance(subscription=sub, included_sessions=5, actor=self.admin, reason='Más')
        body = self.get(biz)
        self.assertEqual((body['status'], body['sessions']['included'], body['sessions']['used']), ('available', 5, 3))
        change_reception_custom_allowance(subscription=sub, included_sessions=4, actor=self.admin, reason='Menos')
        body = self.get(biz)
        self.assertEqual(body['sessions']['included'], 5)  # reductions are never immediate
        self.assertEqual(body['scheduled_change'], {'included_sessions': 4, 'effective_at': self.end.isoformat()})
        revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja')
        body = self.get(biz)
        self.assertEqual((body['status'], body['reason'], body['scheduled_change']),
                         ('policy_not_configured', 'manual_contract_required', None))
        # No internal audit data leaks into the merchant contract.
        self.assertNotIn('Baja', str(body))
        self.assertNotIn(str(self.admin.pk), str(body))

    def test_turnos_ia_with_its_existing_overage(self):
        tier = canonical_pricing.get_usage_tier('ai_300')
        price, cap = tier['extra_conversation_price'], tier['default_extra_spend_limit']
        biz, sub = self.turnos_ia()
        self.seed(sub, 301)
        body = self.get(biz)
        self.assertEqual((body['status'], body['source']['product']), ('available', 'appointments_ai'))
        self.assertEqual(body['overage'], {'enabled': True, 'unit_price': price, 'spend_limit': cap,
                                           'max_sessions': cap // price, 'used_sessions': 1, 'amount': price,
                                           'currency': 'ARS'})
        self.assertEqual(body['hard_cap']['max_sessions'], 300 + cap // price)
        self.seed(sub, 300 + cap // price - 301)
        self.assertEqual(self.get(biz)['status'], 'exhausted')

    def test_ambiguous_suspended_and_not_contracted(self):
        biz = _business(service='appointments')
        self.reception(biz)
        self.turnos_ia(biz)
        body = self.get(biz)
        self.assertEqual((body['status'], body['reason'], body['source']), ('ambiguous_source', 'ambiguous_ai_source', None))

        biz = _business()
        self.reception(biz, status='suspended')
        body = self.get(biz)
        self.assertEqual((body['status'], body['reason'], body['sessions']), ('suspended', 'suspended', None))

        biz = _business(service='appointments')
        self.sub(biz, 'appointments', 'appointments_pro')
        self.assertEqual(self.get(biz, expected=403)['code'], 'ai_service_not_contracted')

    @override_settings(AI_USAGE_METERING_ENABLED=False)
    def test_metering_disabled_is_unavailable(self):
        biz = _business()
        self.reception(biz)
        body = self.get(biz)
        self.assertEqual((body['status'], body['reason'], body['can_start_new_session']),
                         ('unavailable', 'metering_disabled', False))


# ── Permisos y aislamiento ───────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class SummaryAccessTests(_SummaryBase, TestCase):

    def test_owner_and_admin_allowed_others_denied_on_reception(self):
        biz = _business()
        self.reception(biz)
        for role, expected in (('owner', 200), ('admin', 200), ('manager', 403), ('viewer', 403)):
            with self.subTest(role=role):
                self.get(biz, role=role, expected=expected)

    def test_roles_on_turnos_ia(self):
        biz, _ = self.turnos_ia()
        for role, expected in (('owner', 200), ('admin', 200), ('manager', 403), ('viewer', 403),
                               ('professional', 403)):
            with self.subTest(role=role):
                self.get(biz, role=role, expected=expected)

    def test_anonymous_and_non_member_denied(self):
        from rest_framework.test import APIClient

        self.assertIn(APIClient().get(URL).status_code, (401, 403))

    def test_gestion_principal_plus_reception(self):
        biz = _business(service='gestion')
        self.sub(biz, 'gestion', 'pro')
        sub = self.reception(biz)
        body = self.get(biz)
        self.assertEqual((body['status'], body['source']['product'], body['source']['usage_tier']),
                         ('available', 'reception', sub.usage_tier))

    def test_tenant_comes_from_the_authenticated_context(self):
        mine, other = _business(), _business()
        self.reception(mine)
        other_sub = self.reception(other)
        self.seed(other_sub, 7)
        client = self.owner(mine)
        client.credentials(HTTP_X_BUSINESS_ID=str(other.pk))
        response = client.get(f'{URL}?business_id={other.pk}&business={other.pk}&at=2020-01-01T00:00:00Z')
        if response.status_code == 200:
            self.assertEqual(response.json()['sessions']['used'], 0)  # never the other tenant's data
        else:
            self.assertEqual(response.status_code, 403)
        body = self.get(mine, client=self.owner(mine), path=f'{URL}?at=2020-01-01T00:00:00Z&now=2020-01-01')
        evaluated = timezone.datetime.fromisoformat(body['evaluated_at'])
        self.assertLess(abs((timezone.now() - evaluated).total_seconds()), 60)  # server time only

    def test_write_methods_not_allowed(self):
        biz = _business()
        self.reception(biz)
        client = self.owner(biz)
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(client, method)(URL, {}, format='json').status_code, 405)


# ── Solo lectura y coincidencia con el motor ─────────────────────────────────

@override_settings(**AI_SETTINGS)
class SummaryReadOnlyAndEngineTests(_SummaryBase, TestCase):

    def _counts(self):
        return tuple(model.objects.count() for model in (
            AppointmentAIUsageSession, AppointmentAIUsageCharge, AppointmentAIUsageAuthorization,
            AppointmentAIUsageSettlement, ReceptionAIUsagePolicy, ReceptionAIUsagePolicyChange,
        ))

    def test_no_side_effects_no_locks_no_writes(self):
        biz, sub = self.custom(included=3)
        self.seed(sub, 3)
        client = self.owner(biz)
        before, stamp = self._counts(), SubscriptionV2.objects.get(pk=sub.pk).updated_at
        with CaptureQueriesContext(connection) as queries:
            for _ in range(3):
                self.assertEqual(client.get(URL).json()['status'], 'exhausted')
        sql = ' '.join(q['sql'].upper() for q in queries.captured_queries)
        self.assertNotIn('FOR UPDATE', sql)
        for verb in ('INSERT ', 'UPDATE ', 'DELETE '):
            self.assertNotIn(verb, sql.replace('FOR UPDATE', ''))
        self.assertEqual(self._counts(), before)
        self.assertEqual(SubscriptionV2.objects.get(pk=sub.pk).updated_at, stamp)

    def test_reported_admission_matches_the_engine(self):
        def fixed_available(biz):
            self.reception(biz)

        def fixed_exhausted(biz):
            self.seed(self.reception(biz), 300)

        def custom_last_slot(biz):
            _, sub = self.custom(biz, included=2)
            self.seed(sub, 1)

        def custom_exhausted(biz):
            _, sub = self.custom(biz, included=2)
            self.seed(sub, 2)

        def custom_without_policy(biz):
            self.custom(biz)

        def custom_revoked(biz):
            _, sub = self.custom(biz, included=2)
            revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja')

        def turnos_ia_overage(biz):
            self.seed(self.turnos_ia(biz)[1], 300)

        for make in (fixed_available, fixed_exhausted, custom_last_slot, custom_exhausted,
                     custom_without_policy, custom_revoked, turnos_ia_overage):
            with self.subTest(make.__name__):
                biz = _business(service='appointments' if make is turnos_ia_overage else 'reception')
                make(biz)
                body = self.get(biz)
                self.assertEqual(body['can_start_new_session'], self.engine_allows_new_session(biz), body)
                if body['can_start_new_session']:
                    self.assertEqual(self.get(biz)['sessions']['used'], (body['sessions']['used'] + 1))
