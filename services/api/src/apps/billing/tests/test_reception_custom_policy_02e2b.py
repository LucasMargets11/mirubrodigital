"""PROD-02E2B — Política personalizada de consumo IA (Recepcionista Custom).

`reception_custom` toma su cupo de una política individual por suscripción
(billing.ReceptionAIUsagePolicy, versionada, una sola vigente por instante),
con el mismo motor, la misma sesión de 24 h y la misma ausencia de excedentes
que los tiers fijos. Sin política vigente: `manual_contract_required`; con
datos inconsistentes: `usage_policy_undefined`. Nunca ilimitado.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from django.contrib.auth import get_user_model

from apps.accounts.models import AccessAuditLog
from apps.appointments.models import (
    AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
)
from apps.appointments.services.ai_usage import (
    AIUsageHardCapReached, AIUsageUnavailable, get_appointments_ai_usage, resolve_ai_usage_limit,
)
from apps.appointments.services.ai_usage_authorization import authorize_ai_interaction
from apps.billing.models import (
    RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS, ReceptionAIUsagePolicy, ReceptionAIUsagePolicyChange,
    SubscriptionV2,
)
from apps.billing.services.ai_source import (
    AMBIGUOUS_AI_SOURCE, MANUAL_CONTRACT, USAGE_POLICY_UNDEFINED, resolve_ai_source,
)
from apps.billing.services.appointments_checkout import ManualContractRequired
from apps.billing.services.reception_ai_policy import (
    CustomPolicyError, cancel_scheduled_reception_custom_change, change_reception_custom_allowance,
    create_reception_custom_policy, effective_reception_custom_policy, revoke_reception_custom_policy,
)
from apps.billing.tests.test_reception_ai_consumption_02e2a import AI_SETTINGS, _add_months, _Base
from apps.billing.tests.test_reception_service_02b import _business, _superadmin

Action = ReceptionAIUsagePolicyChange.Action


class _CustomBase(_Base):

    def setUp(self):
        super().setUp()
        self.admin = _superadmin()

    def custom(self, biz=None, **extra):
        biz = biz or _business()
        return biz, self.reception(biz, tier='reception_custom', **extra)

    def policy(self, sub, included=5, now=None, **extra):
        return create_reception_custom_policy(
            subscription=sub, included_sessions=included, actor=self.admin, reason='Acuerdo comercial',
            now=now or self.start, **extra,
        )

    def code(self, fn, **kwargs):
        with self.assertRaises(CustomPolicyError) as ctx:
            fn(**kwargs)
        return ctx.exception.code

    def denied(self, credential, conversation, at, **kwargs):
        body = self.authorize(credential, conversation, at, **kwargs)
        self.assertFalse(body['allowed'], body)
        return body['reason']


# ── Resolución ───────────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class CustomPolicyResolutionTests(_CustomBase, TestCase):

    def test_valid_policy_opens_an_included_session_on_its_own_allowance(self):
        biz, sub = self.custom()
        self.policy(sub, included=7)
        source = resolve_ai_source(biz, at=self.at)
        self.assertEqual((source.subscription.pk, source.policy_configured, source.policy_reason), (sub.pk, True, None))
        self.assertEqual(resolve_ai_usage_limit(sub, at=self.at), 7)
        conversation, credential, _ = self.agent(biz)
        body = self.authorize(credential, conversation, self.at)
        self.assertTrue(body['allowed'], body)
        self.assertEqual((body['included'], body['used'], body['remaining']), (7, 1, 6))
        session = AppointmentAIUsageSession.objects.get(business=biz)
        self.assertEqual((session.subscription_id, session.usage_tier), (sub.pk, 'reception_custom'))
        charge = AppointmentAIUsageCharge.objects.get(session=session)
        self.assertEqual(
            (charge.classification, charge.amount, charge.session_ordinal, charge.included_sessions_snapshot),
            ('included', 0, 1, 7),
        )

    def test_absent_future_expired_and_revoked_policies_block_and_record_nothing(self):
        def absent(sub):
            pass

        def future(sub):
            self.policy(sub, valid_from=self.at + timedelta(days=1))

        def expired(sub):
            self.policy(sub, valid_until=self.start + timedelta(hours=1))

        def revoked(sub):
            self.policy(sub)
            revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja', now=self.start + timedelta(hours=1))

        for make in (absent, future, expired, revoked):
            with self.subTest(make.__name__):
                biz, sub = self.custom()
                make(sub)
                source = resolve_ai_source(biz, at=self.at)
                self.assertEqual((source.policy_configured, source.policy_reason), (False, MANUAL_CONTRACT))
                with self.assertRaises(ManualContractRequired):
                    resolve_ai_usage_limit(sub, at=self.at)
                conversation, credential, _ = self.agent(biz)
                self.assertEqual(self.denied(credential, conversation, self.at), MANUAL_CONTRACT)
                self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())
                self.assertFalse(AppointmentAIUsageAuthorization.objects.filter(business=biz).exists())

    def test_overlapping_or_invalid_rows_fail_closed_as_undefined(self):
        biz, sub = self.custom()
        # Bypass the service (and save()) to simulate corrupted data.
        ReceptionAIUsagePolicy.objects.bulk_create([
            ReceptionAIUsagePolicy(business=biz, subscription=sub, included_sessions=n, valid_from=self.start,
                                   valid_until=self.end) for n in (5, 50)
        ])
        self.assertEqual(resolve_ai_source(biz, at=self.at).policy_reason, USAGE_POLICY_UNDEFINED)
        conversation, credential, _ = self.agent(biz)
        self.assertEqual(self.denied(credential, conversation, self.at), USAGE_POLICY_UNDEFINED)
        self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())

    def test_catalog_custom_row_with_overage_fails_closed(self):
        from apps.billing import canonical_pricing

        biz, sub = self.custom()
        self.policy(sub)
        real = canonical_pricing.get_usage_tier
        for changes in ({'extra_conversation_price': 300}, {'default_extra_spend_limit': 75000},
                        {'billing_mode': 'automatic'}):
            with self.subTest(changes=changes), patch.object(
                canonical_pricing, 'get_usage_tier',
                side_effect=lambda code, c=changes: {**real(code), **c} if code == 'reception_custom' else real(code),
            ):
                with self.assertRaises(AIUsageUnavailable) as ctx:
                    resolve_ai_usage_limit(sub, at=self.at)
                self.assertEqual(ctx.exception.reason, USAGE_POLICY_UNDEFINED)

    def test_kill_switch_still_blocks_custom(self):
        _, sub = self.custom()
        self.policy(sub)
        with patch('apps.appointments.services.ai_usage.RECEPTION_AI_CONSUMPTION_ENABLED', False):
            with self.assertRaises(AIUsageUnavailable) as ctx:
                resolve_ai_usage_limit(sub, at=self.at)
        self.assertEqual(ctx.exception.reason, USAGE_POLICY_UNDEFINED)

    def test_lifecycle_still_gates_a_valid_policy(self):
        for status in ('suspended', 'checkout_pending'):
            with self.subTest(status):
                biz, sub = self.custom()
                self.policy(sub, valid_until=self.end + timedelta(days=365))
                SubscriptionV2.objects.filter(pk=sub.pk).update(status=status)
                conversation, credential, _ = self.agent(biz)
                self.denied(credential, conversation, self.at)
                self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())


# ── Validación de cupos y vínculo ────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class CustomPolicyValidationTests(_CustomBase, TestCase):

    def test_zero_negative_and_non_integer_allowances_are_rejected(self):
        _, sub = self.custom()
        for value in (0, -1, 1.5, '10', True, None, RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS + 1):
            with self.subTest(value=value):
                self.assertEqual(self.code(self.policy, sub=sub, included=value), 'invalid_allowance')
        self.assertFalse(ReceptionAIUsagePolicy.objects.filter(subscription=sub).exists())
        self.policy(sub, included=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReceptionAIUsagePolicy.objects.filter(subscription=sub).update(included_sessions=0)

    def test_policy_requires_a_reception_custom_subscription(self):
        biz = _business()
        for sub in (self.reception(biz, tier='reception_300'),
                    self.sub(_business(service='appointments'), 'appointments', 'appointments_ai', 'ai_300')):
            with self.subTest(tier=sub.usage_tier):
                self.assertEqual(self.code(self.policy, sub=sub), 'wrong_subscription')
                with self.assertRaises(ValidationError):
                    ReceptionAIUsagePolicy.objects.create(
                        business=sub.business, subscription=sub, included_sessions=5, valid_from=self.start,
                    )
        _, canceled = self.custom(status='canceled')
        self.assertEqual(self.code(self.policy, sub=canceled), 'subscription_canceled')
        _, sub = self.custom()
        with self.assertRaises(ValidationError):
            ReceptionAIUsagePolicy.objects.create(
                business=_business(), subscription=sub, included_sessions=5, valid_from=self.start,
            )

    def test_tier_changed_away_from_custom_ignores_the_policy(self):
        _, sub = self.custom()
        self.policy(sub, included=9)
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier='reception_300')
        sub.refresh_from_db()
        self.assertEqual(resolve_ai_usage_limit(sub, at=self.at), 300)

    def test_actor_reason_window_and_uniqueness(self):
        _, sub = self.custom()
        common = dict(subscription=sub, included_sessions=5, now=self.start)
        self.assertEqual(self.code(create_reception_custom_policy, actor=None, reason='x', **common), 'actor_required')
        plain = get_user_model().objects.create_user(username=f'u-{uuid.uuid4().hex}', email=f'{uuid.uuid4().hex}@x.test')
        self.assertEqual(self.code(create_reception_custom_policy, actor=plain, reason='x', **common),
                         'actor_not_platform_staff')
        self.assertEqual(self.code(create_reception_custom_policy, actor=self.admin, reason='  ', **common),
                         'reason_required')
        self.assertEqual(self.code(create_reception_custom_policy, actor=self.admin, reason='x',
                                   valid_from=self.start - timedelta(seconds=1), **common), 'backdated')
        self.assertEqual(self.code(create_reception_custom_policy, actor=self.admin, reason='x',
                                   valid_until=self.start, **common), 'invalid_window')
        self.policy(sub)
        self.assertEqual(self.code(self.policy, sub=sub, now=self.at), 'policy_exists')
        self.assertEqual(ReceptionAIUsagePolicy.objects.filter(subscription=sub).count(), 1)

    def test_businesses_are_isolated(self):
        biz_a, sub_a = self.custom()
        biz_b, sub_b = self.custom()
        self.policy(sub_a, included=1)
        self.policy(sub_b, included=3)
        self.seed(sub_a, 1)
        conversation, credential, _ = self.agent(biz_a)
        self.assertEqual(self.denied(credential, conversation, self.at), 'hard_cap_reached')
        conversation, credential, _ = self.agent(biz_b)
        self.assertTrue(self.authorize(credential, conversation, self.at)['allowed'])
        self.assertEqual(effective_reception_custom_policy(sub_b, at=self.at).business_id, biz_b.pk)
        _, sub_c = self.custom()
        with self.assertRaises(Exception):
            effective_reception_custom_policy(sub_c, at=self.at)  # sub_a/sub_b policies never leak


# ── Consumo, sesiones y cupo ─────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class CustomConsumptionTests(_CustomBase, TestCase):

    def test_window_reuse_for_24_hours_then_a_new_session(self):
        biz, sub = self.custom()
        self.policy(sub, included=5)
        conversation, credential, _ = self.agent(biz)
        first = uuid.uuid4()
        self.assertTrue(self.authorize(credential, conversation, self.at, interaction=first)['allowed'])
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(hours=23))['allowed'])
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(hours=23), interaction=first,
                                       occurred=self.at)['allowed'])
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 1)
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(hours=25))['allowed'])
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 2)

    def test_exhausted_allowance_is_a_hard_cap_without_overage(self):
        biz, sub = self.custom()
        self.policy(sub, included=3)
        self.seed(sub, 2)
        open_conversation, credential, _ = self.agent(biz)
        self.assertTrue(self.authorize(credential, open_conversation, self.at)['allowed'])  # session 3
        other, other_credential, _ = self.agent(biz)
        self.assertEqual(self.denied(other_credential, other, self.at + timedelta(minutes=1)), 'hard_cap_reached')
        self.assertTrue(self.authorize(credential, open_conversation, self.at + timedelta(hours=1))['allowed'])
        self.assertFalse(AppointmentAIUsageCharge.objects.filter(business=biz, classification='overage').exists())

    def test_db_refuses_a_custom_overage_charge(self):
        biz, sub = self.custom()
        self.policy(sub, included=1)
        conversation, credential, _ = self.agent(biz)
        self.authorize(credential, conversation, self.at)
        session = AppointmentAIUsageSession.objects.get(business=biz)
        AppointmentAIUsageCharge.objects.filter(session=session).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentAIUsageCharge.objects.create(
                session=session, business=biz, subscription=sub, usage_period_start=self.start,
                usage_period_end=self.end, usage_tier='reception_custom', session_ordinal=2,
                included_sessions_snapshot=1, classification='overage', unit_price=300, amount=300, currency='ARS',
            )

    def test_increase_applies_now_without_resetting_consumption(self):
        biz, sub = self.custom()
        self.policy(sub, included=3)
        self.seed(sub, 3)
        conversation, credential, _ = self.agent(biz)
        self.assertEqual(self.denied(credential, conversation, self.at), 'hard_cap_reached')
        change = change_reception_custom_allowance(
            subscription=sub, included_sessions=5, actor=self.admin, reason='Ampliación', now=self.at,
        )
        self.assertEqual((change.action, change.previous_included_sessions, change.new_included_sessions,
                          change.effective_at), (Action.INCREASED, 3, 5, self.at))
        body = self.authorize(credential, conversation, self.at + timedelta(minutes=1))
        self.assertTrue(body['allowed'], body)
        self.assertEqual((body['used'], body['included']), (4, 5))
        charge = AppointmentAIUsageCharge.objects.get(business=biz)
        self.assertEqual((charge.session_ordinal, charge.included_sessions_snapshot), (4, 5))
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 4)  # history kept
        # The previous version stays as history, closed at the change instant.
        old = ReceptionAIUsagePolicy.objects.get(subscription=sub, included_sessions=3)
        self.assertEqual((old.status, old.valid_until), ('active', self.at))

    def test_reduction_is_never_immediate_and_starts_next_period(self):
        biz, sub = self.custom()
        self.policy(sub, included=10)
        change = change_reception_custom_allowance(
            subscription=sub, included_sessions=3, actor=self.admin, reason='Reducción', now=self.at,
        )
        self.assertEqual((change.action, change.effective_at), (Action.REDUCTION_SCHEDULED, self.end))
        self.seed(sub, 5)
        # Current period: still 10, the 6th session is included.
        self.assertEqual(effective_reception_custom_policy(sub, at=self.at).included_sessions, 10)
        conversation, credential, _ = self.agent(biz)
        self.assertTrue(self.authorize(credential, conversation, self.at + timedelta(hours=1))['allowed'])
        # Next period: the lower allowance, consumption counted afresh.
        nxt = self.end + timedelta(hours=1)
        usage = get_appointments_ai_usage(biz, at=nxt)
        self.assertEqual((usage['included'], usage['used'], usage['period_start']), (3, 0, self.end))
        # No stacking: a pending change must be canceled first.
        self.assertEqual(self.code(change_reception_custom_allowance, subscription=sub, included_sessions=20,
                                   actor=self.admin, reason='x', now=self.at + timedelta(hours=2)),
                         'scheduled_change_pending')
        cancel = cancel_scheduled_reception_custom_change(
            subscription=sub, actor=self.admin, reason='Se mantiene', now=self.at + timedelta(hours=2),
        )
        self.assertEqual(cancel.action, Action.SCHEDULE_CANCELED)
        self.assertEqual(get_appointments_ai_usage(biz, at=nxt)['included'], 10)
        self.assertEqual(self.code(change_reception_custom_allowance, subscription=sub, included_sessions=10,
                                   actor=self.admin, reason='x', now=self.at + timedelta(hours=3)), 'no_change')

    def test_reduction_rejected_when_policy_ends_before_next_period(self):
        _, sub = self.custom()
        self.policy(sub, included=10, valid_until=self.end - timedelta(days=1))
        self.assertEqual(self.code(change_reception_custom_allowance, subscription=sub, included_sessions=3,
                                   actor=self.admin, reason='x', now=self.at), 'policy_ends_before_next_period')

    def test_audit_trail_is_complete_and_append_only(self):
        _, sub = self.custom()
        self.policy(sub, included=5)
        change_reception_custom_allowance(subscription=sub, included_sessions=8, actor=self.admin,
                                          reason='Ampliación', now=self.at)
        change_reception_custom_allowance(subscription=sub, included_sessions=4, actor=self.admin,
                                          reason='Reducción', now=self.at + timedelta(hours=1))
        cancel_scheduled_reception_custom_change(subscription=sub, actor=self.admin, reason='Cancelada',
                                                 now=self.at + timedelta(hours=2))
        revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja',
                                       now=self.at + timedelta(hours=3))
        changes = list(ReceptionAIUsagePolicyChange.objects.filter(subscription=sub).order_by('created_at'))
        self.assertEqual(
            [(c.action, c.previous_included_sessions, c.new_included_sessions) for c in changes],
            [(Action.CREATED, None, 5), (Action.INCREASED, 5, 8), (Action.REDUCTION_SCHEDULED, 8, 4),
             (Action.SCHEDULE_CANCELED, 8, 4), (Action.REVOKED, 8, None)],
        )
        self.assertTrue(all(c.actor_id == self.admin.pk and c.reason for c in changes))
        self.assertEqual(
            AccessAuditLog.objects.filter(entity_type='reception_ai_usage_policy', actor=self.admin).count(), 5,
        )
        with self.assertRaises(ValidationError):
            changes[0].save()
        with self.assertRaises(ValidationError):
            changes[0].delete()
        version = ReceptionAIUsagePolicy.objects.filter(subscription=sub).first()
        version.included_sessions += 1
        with self.assertRaises(ValidationError):
            version.save()
        with self.assertRaises(ValidationError):
            version.delete()

    def test_revocation_stops_open_windows_replays_and_late_interactions(self):
        biz, sub = self.custom()
        self.policy(sub, included=5)
        conversation, credential, _ = self.agent(biz)
        first = uuid.uuid4()
        self.assertTrue(self.authorize(credential, conversation, self.at, interaction=first)['allowed'])
        revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja',
                                       now=self.at + timedelta(hours=1))
        later = self.at + timedelta(hours=2)
        self.assertEqual(self.denied(credential, conversation, later), MANUAL_CONTRACT)  # open window
        self.assertEqual(self.denied(credential, conversation, later, interaction=first, occurred=self.at),
                         MANUAL_CONTRACT)  # replay of an authorized receipt
        self.assertEqual(self.denied(credential, conversation, later, occurred=self.at + timedelta(minutes=30)),
                         MANUAL_CONTRACT)  # late interaction that happened before the revocation
        self.assertEqual(AppointmentAIUsageAuthorization.objects.filter(business=biz).count(), 1)
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 1)  # history kept
        # A new agreement re-enables it without resetting the period's consumption.
        self.policy(sub, included=5, now=self.at + timedelta(hours=3))
        body = self.authorize(credential, conversation, self.at + timedelta(hours=4))
        self.assertTrue(body['allowed'], body)
        self.assertEqual(body['used'], 1)  # same 24 h window, reused

    def test_suspension_blocks_open_window_even_with_a_valid_policy(self):
        biz, sub = self.custom()
        self.policy(sub)
        conversation, credential, _ = self.agent(biz)
        self.assertTrue(self.authorize(credential, conversation, self.at)['allowed'])
        SubscriptionV2.objects.filter(pk=sub.pk).update(status='suspended')
        self.assertEqual(self.denied(credential, conversation, self.at + timedelta(hours=1)), 'suspended')


# ── Compatibilidad ───────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class CompatibilityTests(_CustomBase, TestCase):

    def test_fixed_tiers_and_turnos_ia_are_unchanged(self):
        for tier, included in (('reception_300', 300), ('reception_1500', 1500), ('reception_3000', 3000)):
            with self.subTest(tier=tier):
                self.assertEqual(resolve_ai_usage_limit(self.reception(_business(), tier=tier), at=self.at), included)
        biz = _business(service='appointments')
        self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        conversation, credential, _ = self.agent(biz)
        self.assertTrue(self.authorize(credential, conversation, self.at)['allowed'])
        turnos_custom = self.sub(_business(service='appointments'), 'appointments', 'appointments_ai', 'custom')
        with self.assertRaises(ManualContractRequired):
            resolve_ai_usage_limit(turnos_custom, at=self.at)

    def test_custom_reception_plus_turnos_ia_is_ambiguous(self):
        biz, sub = self.custom(_business(service='appointments'))
        self.policy(sub)
        self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        self.assertEqual(resolve_ai_source(biz, at=self.at).reason, AMBIGUOUS_AI_SOURCE)
        conversation, credential, _ = self.agent(biz)
        self.assertEqual(self.denied(credential, conversation, self.at), AMBIGUOUS_AI_SOURCE)
        self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())

    def test_source_change_to_custom_never_reuses_turnos_ia_receipts(self):
        biz = _business(service='appointments')
        turnos_ia = self.sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        conversation, credential, _ = self.agent(biz)
        first = uuid.uuid4()
        self.assertTrue(self.authorize(credential, conversation, self.at, interaction=first)['allowed'])
        SubscriptionV2.objects.filter(pk=turnos_ia.pk).update(status='suspended')
        _, custom = self.custom(biz)
        self.policy(custom)
        later = self.at + timedelta(hours=1)
        self.assertEqual(self.denied(credential, conversation, later, interaction=first, occurred=self.at),
                         'interaction_conflict')
        self.assertTrue(self.authorize(credential, conversation, later)['allowed'])
        self.assertEqual(
            AppointmentAIUsageSession.objects.filter(business=biz, subscription=custom).count(), 1,
        )

    def test_period_change_restarts_counting_with_the_same_policy(self):
        biz, sub = self.custom()
        self.policy(sub, included=2)
        self.seed(sub, 2)
        self.assertFalse(get_appointments_ai_usage(biz, at=self.at)['remaining'])
        nxt = self.end + timedelta(hours=1)
        usage = get_appointments_ai_usage(biz, at=nxt)
        self.assertEqual((usage['used'], usage['included'], usage['period_end']), (0, 2, _add_months(self.start, 2)))


# ── Concurrencia ─────────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class CustomPolicyConcurrencyTests(_CustomBase, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def _consume(self, conversation, instance, occurred, results):
        try:
            authorize_ai_interaction(agent_instance=instance, conversation_id=conversation,
                                     interaction_id=uuid.uuid4(), occurred_at=occurred)
            results.append('allowed')
        except AIUsageHardCapReached:
            results.append('hard_cap_reached')
        except ManualContractRequired:
            results.append('manual_contract_required')
        except AIUsageUnavailable as exc:
            results.append(exc.reason)
        finally:
            connection.close()

    def _while_locked(self, mutate, consumer_args):
        """Run `mutate` in a held transaction; the consumer must wait for its commit."""
        locked, release, results = threading.Event(), threading.Event(), []

        def mutator():
            try:
                with transaction.atomic():
                    mutate()
                    locked.set()
                    release.wait(15)
            finally:
                connection.close()

        def consumer():
            locked.wait(15)
            self._consume(*consumer_args, results)

        threads = [threading.Thread(target=mutator), threading.Thread(target=consumer)]
        for thread in threads:
            thread.start()
        locked.wait(15)
        time.sleep(1.0)
        self.assertTrue(threads[1].is_alive(), 'consumption must wait for the policy change lock')
        self.assertEqual(results, [])
        release.set()
        for thread in threads:
            thread.join(30)
        return results

    def test_revocation_and_consumption_are_serialized(self):
        biz, sub = self.custom()
        self.policy(sub, included=5)
        conversation, _, instance = self.agent(biz)
        results = self._while_locked(
            lambda: revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Baja'),
            (conversation, instance, timezone.now() - timedelta(minutes=1)),
        )
        self.assertEqual(results, ['manual_contract_required'])
        self.assertFalse(AppointmentAIUsageSession.objects.filter(business=biz).exists())

    def test_increase_and_consumption_are_serialized(self):
        biz, sub = self.custom()
        self.policy(sub, included=1)
        self.seed(sub, 1)
        conversation, _, instance = self.agent(biz)
        changed_at = timezone.now() - timedelta(minutes=2)
        results = self._while_locked(
            lambda: change_reception_custom_allowance(subscription=sub, included_sessions=2, actor=self.admin,
                                                      reason='Ampliación', now=changed_at),
            (conversation, instance, timezone.now() - timedelta(minutes=1)),
        )
        self.assertEqual(results, ['allowed'])
        charge = AppointmentAIUsageCharge.objects.get(business=biz)
        self.assertEqual((charge.session_ordinal, charge.included_sessions_snapshot), (2, 2))

    def test_two_conversations_race_for_the_last_custom_session(self):
        biz, sub = self.custom()
        self.policy(sub, included=2)
        self.seed(sub, 1)
        agents = [self.agent(biz) for _ in range(2)]
        results, barrier = [], threading.Barrier(2)
        occurred = timezone.now() - timedelta(minutes=1)

        def run(conversation, instance):
            barrier.wait()
            self._consume(conversation, instance, occurred, results)

        threads = [threading.Thread(target=run, args=(conv, inst)) for conv, _, inst in agents]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(sorted(results), ['allowed', 'hard_cap_reached'])
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 2)
        self.assertFalse(AppointmentAIUsageCharge.objects.filter(business=biz, classification='overage').exists())
