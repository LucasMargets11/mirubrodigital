"""PROD-09D1 — Extensión de vigencia bonificada de Recepcionista IA y pausa de la
atención automática en la baja definitiva.

La extensión mueve solo `current_period_end` de la MISMA suscripción vigente
(plan, tier, inicio, proveedor y estado intactos). El cupo del período en curso
no se reinicia ni se duplica: el último período, recortado por el vencimiento,
conserva sus sesiones registradas aunque su fin cambie. En `reception_custom`
la versión de política alineada con el vencimiento se extiende en la misma
transacción. La baja definitiva de Recepcionista pausa la atención automática;
una contratación posterior no la recupera.
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
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.admin_client_provisioning_service import UnauthorizedProvisioningActorError
from apps.accounts.admin_client_service_addition import extend_client_service
from apps.accounts.models import AccessAuditLog
from apps.appointments.models import AppointmentAIUsageCharge, AppointmentAIUsageSession
from apps.appointments.services.ai_usage import get_appointments_ai_usage, resolve_ai_usage_limit
from apps.appointments.services.ai_usage_authorization import authorize_ai_interaction
from apps.billing.cancellation_service import cancel_subscription_immediately, execute_cancellation
from apps.billing.complimentary_access_service import (
    ComplimentaryExtensionError, extend_complimentary_access, grant_complimentary_access,
)
from apps.billing.models import ReceptionAIUsagePolicy, ReceptionAIUsagePolicyChange, SubscriptionV2
from apps.billing.services.reception_ai_policy import (
    cancel_scheduled_reception_custom_change, change_reception_custom_allowance, revoke_reception_custom_policy,
)
from apps.billing.tests.test_reception_ai_consumption_02e2a import AI_SETTINGS, _add_months, _Base
from apps.billing.tests.test_reception_service_02b import _business, _superadmin
from apps.business.models import Business
from apps.leads.models import ReceptionistConfig
from apps.leads.tests.factories import enable_reception_attention

Action = ReceptionAIUsagePolicyChange.Action


def extension_url(business_id, subscription_id):
    return f'/api/v1/platform-admin/clients/{business_id}/subscriptions/{subscription_id}/extension/'


def _extension_audits(sub):
    return AccessAuditLog.objects.filter(
        action='PLATFORM_ADMIN_ACTION', entity_id=str(sub.pk), details__operation='complimentary_extension',
    )


class _ExtBase(_Base):

    def setUp(self):
        super().setUp()
        call_command('seed_reception_catalog', stdout=StringIO())
        self.admin = _superadmin()
        # Bonified window [start, start+10d): its only usage period is clipped
        # by the grant end (the monthly boundary is start+1 month).
        self.clip_end = self.start + timedelta(days=10)

    def grant(self, biz=None, *, start=None, end=None, tier='reception_300', custom=None):
        biz = biz or _business()
        sub = grant_complimentary_access(
            business=biz, plan_code='reception', service_type='reception',
            starts_at=start or self.start, ends_at=end or self.clip_end, granted_by=self.admin,
            reason='Piloto Recepcionista', usage_tier=tier, custom_included_sessions=custom,
        )
        return biz, sub

    def extend(self, sub, end, *, reason='Extensión acordada', actor=None):
        return extend_client_service(
            business_id=sub.business_id, subscription_id=sub.pk, complimentary_end=end,
            extended_by=actor or self.admin, reason=reason,
        )

    def rejected(self, sub, end, *, business_id=None, reason='Extensión acordada', **kwargs):
        with self.assertRaises(ComplimentaryExtensionError) as ctx:
            extend_complimentary_access(
                business_id=business_id or sub.business_id, subscription_id=sub.pk, new_end=end,
                extended_by=self.admin, reason=reason, **kwargs,
            )
        return ctx.exception.code

    def snapshot(self, sub):
        return SubscriptionV2.objects.filter(pk=sub.pk).values(
            'business_id', 'service_type', 'plan_code', 'usage_tier', 'provider', 'status', 'is_active',
            'current_period_start', 'current_period_end', 'trial_ends_at', 'cancel_at_period_end',
        ).get()


# ── Extensión: identidad comercial y validaciones ─────────────────────────────

@override_settings(**AI_SETTINGS)
class ExtensionServiceTests(_ExtBase, TestCase):

    def test_fixed_extension_keeps_identity_status_and_attention(self):
        biz, sub = self.grant()
        config = enable_reception_attention(biz)
        before = self.snapshot(sub)
        business_status = Business.objects.get(pk=biz.pk).status
        new_end = self.start + timedelta(days=70)
        result = self.extend(sub, new_end)
        after = self.snapshot(sub)
        self.assertEqual(after.pop('current_period_end'), new_end)
        before.pop('current_period_end')
        self.assertEqual(after, before)
        self.assertEqual((result.subscription.pk, result.previous_end, result.custom_policy),
                         (sub.pk, self.clip_end, None))
        self.assertEqual(SubscriptionV2.objects.filter(business=biz).count(), 1)
        self.assertEqual(Business.objects.get(pk=biz.pk).status, business_status)
        [audit] = _extension_audits(sub)
        self.assertEqual(audit.actor_id, self.admin.pk)
        self.assertEqual(
            (audit.details['previous_period_end'], audit.details['new_period_end'], audit.details['reason']),
            (self.clip_end.isoformat(), new_end.isoformat(), 'Extensión acordada'),
        )
        # Extending never enables nor pauses automatic attention.
        config.refresh_from_db()
        self.assertEqual((config.automatic_attention_enabled, config.version), (True, 1))
        config.automatic_attention_enabled = False
        config.save()
        self.extend(sub, new_end + timedelta(days=5))
        config.refresh_from_db()
        self.assertFalse(config.automatic_attention_enabled)

    def test_invalid_dates_and_reasons(self):
        _, sub = self.grant()
        for end in (self.clip_end, self.clip_end - timedelta(seconds=1), self.start):
            with self.subTest(end=end):
                self.assertEqual(self.rejected(sub, end), 'invalid_end')
        self.assertEqual(self.rejected(sub, (self.clip_end + timedelta(days=1)).replace(tzinfo=None)), 'invalid_end')
        for reason in ('', '   ', 'x' * 256):
            with self.subTest(reason=len(reason)):
                self.assertEqual(self.rejected(sub, self.clip_end + timedelta(days=1), reason=reason),
                                 'invalid_reason')
        self.assertEqual(self.snapshot(sub)['current_period_end'], self.clip_end)
        self.assertFalse(_extension_audits(sub).exists())

    def test_foreign_canceled_expired_and_incompatible_subscriptions(self):
        later = timezone.now() + timedelta(days=90)
        now = timezone.now()
        other_biz = _business()

        def foreign():
            _, sub = self.grant()
            return sub, {'business_id': other_biz.pk}

        def canceled():
            _, sub = self.grant()
            cancel_subscription_immediately(subscription=sub, canceled_by=self.admin, reason='Baja')
            return sub, {}

        def suspended():
            _, sub = self.grant()
            SubscriptionV2.objects.filter(pk=sub.pk).update(status='suspended')
            return sub, {}

        def expired():
            _, sub = self.grant(start=now - timedelta(days=40), end=now - timedelta(days=1))
            return sub, {}

        def not_started():
            _, sub = self.grant(start=now + timedelta(days=1), end=now + timedelta(days=20))
            return sub, {}

        def paid():
            return self.reception(_business()), {}

        def trial():
            _, sub = self.grant()
            SubscriptionV2.objects.filter(pk=sub.pk).update(trial_ends_at=self.clip_end)
            return sub, {}

        def scheduled_cancel():
            _, sub = self.grant()
            SubscriptionV2.objects.filter(pk=sub.pk).update(cancel_at_period_end=True)
            return sub, {}

        def other_product():
            biz = _business('appointments')
            return self.sub(biz, 'appointments', 'appointments_base', provider='manual', status='trialing',
                            billing_cycle='', manual_granted_by=self.admin, manual_grant_reason='x'), {}

        def branch():
            _, sub = self.grant()
            hq = _business()
            Business.objects.filter(pk=sub.business_id).update(parent=hq)
            return sub, {}

        cases = {
            foreign: 'subscription_not_found', canceled: 'subscription_canceled',
            suspended: 'subscription_suspended', expired: 'subscription_not_current',
            not_started: 'subscription_not_current', paid: 'subscription_not_complimentary',
            trial: 'subscription_not_complimentary', scheduled_cancel: 'cancellation_scheduled',
            other_product: 'subscription_not_extendable', branch: 'client_not_found',
        }
        for make, code in cases.items():
            with self.subTest(make.__name__):
                sub, kwargs = make()
                before = self.snapshot(sub)
                self.assertEqual(self.rejected(sub, later, **kwargs), code)
                self.assertEqual(self.snapshot(sub), before)
                self.assertFalse(_extension_audits(sub).exists())

    def test_actor_must_be_a_fresh_superadmin(self):
        from apps.accounts.tests.test_admin_clientes_reception_provisioning_02f2 import _staff

        _, sub = self.grant()
        for actor in (_staff('operations'), _business_user()):
            with self.subTest(actor=actor.username), self.assertRaises(UnauthorizedProvisioningActorError):
                self.extend(sub, self.clip_end + timedelta(days=5), actor=actor)
        self.assertEqual(self.snapshot(sub)['current_period_end'], self.clip_end)

    def test_audit_failure_rolls_everything_back(self):
        _, sub = self.grant(tier='reception_custom', custom=5)
        policy = ReceptionAIUsagePolicy.objects.get(subscription=sub)
        with patch('apps.accounts.platform_audit.record_platform_action', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                self.extend(sub, self.clip_end + timedelta(days=30))
        policy.refresh_from_db()
        self.assertEqual((self.snapshot(sub)['current_period_end'], policy.valid_until), (self.clip_end, self.clip_end))
        self.assertFalse(ReceptionAIUsagePolicyChange.objects.filter(subscription=sub, action=Action.EXTENDED).exists())

    def test_policy_failure_rolls_the_subscription_back(self):
        _, sub = self.grant(tier='reception_custom', custom=5)
        with patch('apps.billing.services.reception_ai_policy.extend_reception_custom_policy',
                   side_effect=RuntimeError('policy down')):
            with self.assertRaises(RuntimeError):
                self.extend(sub, self.clip_end + timedelta(days=30))
        self.assertEqual(self.snapshot(sub)['current_period_end'], self.clip_end)
        self.assertFalse(_extension_audits(sub).exists())

    def test_businesses_are_isolated(self):
        biz_a, sub_a = self.grant()
        biz_b, sub_b = self.grant(tier='reception_custom', custom=7)
        self.seed(sub_b, 3, self.start, self.clip_end)
        before_b = self.snapshot(sub_b)
        policy_b = ReceptionAIUsagePolicy.objects.get(subscription=sub_b)
        self.extend(sub_a, self.start + timedelta(days=60))
        self.assertEqual(self.snapshot(sub_b), before_b)
        policy_b.refresh_from_db()
        self.assertEqual(policy_b.valid_until, self.clip_end)
        self.assertEqual(get_appointments_ai_usage(biz_b, at=timezone.now())['used'], 3)
        # A's subscription cannot be extended through B's client id.
        self.assertEqual(self.rejected(sub_a, self.start + timedelta(days=90), business_id=biz_b.pk),
                         'subscription_not_found')


def _business_user():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(username=f'u-{uuid.uuid4().hex}', email=f'{uuid.uuid4().hex}@x.test')


# ── Continuidad del consumo ───────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class ConsumptionContinuityTests(_ExtBase, TestCase):

    def test_clipped_period_keeps_its_count_window_and_cap_after_extension(self):
        biz, sub = self.grant()
        conversation, credential, _ = self.agent(biz)
        first = self.authorize(credential, conversation, self.at)
        self.assertTrue(first['allowed'], first)
        self.seed(sub, 298, self.start, self.clip_end)
        self.assertEqual(get_appointments_ai_usage(biz, at=self.at)['used'], 299)
        sessions = sorted(AppointmentAIUsageSession.objects.filter(business=biz)
                          .values_list('pk', 'usage_period_start', 'usage_period_end', 'expires_at'))
        charges = sorted(AppointmentAIUsageCharge.objects.filter(business=biz)
                         .values_list('pk', 'usage_period_start', 'usage_period_end', 'session_ordinal', 'amount'))

        self.extend(sub, self.start + timedelta(days=75))

        usage = get_appointments_ai_usage(biz, at=self.at)
        # Same anchor, later end of the running period; the count is NOT reset.
        self.assertEqual((usage['period_start'], usage['period_end']), (self.start, _add_months(self.start, 1)))
        self.assertEqual((usage['used'], usage['included'], usage['remaining']), (299, 300, 1))
        # Recorded rows are untouched.
        self.assertEqual(sorted(AppointmentAIUsageSession.objects.filter(business=biz)
                                .values_list('pk', 'usage_period_start', 'usage_period_end', 'expires_at')), sessions)
        self.assertEqual(sorted(AppointmentAIUsageCharge.objects.filter(business=biz).values_list(
            'pk', 'usage_period_start', 'usage_period_end', 'session_ordinal', 'amount')), charges)
        # The open 24 h window is reused, not re-charged.
        again = self.authorize(credential, conversation, self.at + timedelta(hours=1))
        self.assertTrue(again['allowed'], again)
        self.assertEqual(again['used'], 299)
        # The last included session, then the hard cap (no duplicated allowance, no overage).
        other, other_credential, _ = self.agent(biz)
        last = self.authorize(other_credential, other, self.at + timedelta(hours=2))
        self.assertEqual((last['allowed'], last['used']), (True, 300))
        new_charge = AppointmentAIUsageCharge.objects.exclude(pk__in=[c[0] for c in charges]).get(business=biz)
        self.assertEqual((new_charge.session_ordinal, new_charge.classification, new_charge.amount,
                          new_charge.usage_period_end), (300, 'included', 0, _add_months(self.start, 1)))
        third, third_credential, _ = self.agent(biz)
        self.assertEqual(self.authorize(third_credential, third, self.at + timedelta(hours=3))['reason'],
                         'hard_cap_reached')
        self.assertFalse(AppointmentAIUsageCharge.objects.filter(business=biz, classification='overage').exists())

    def test_unclipped_running_period_is_unchanged_and_the_next_one_starts_fresh(self):
        end = self.start + timedelta(days=45)
        biz, sub = self.grant(end=end)
        boundary = _add_months(self.start, 1)
        self.seed(sub, 120, self.start, boundary)
        self.extend(sub, self.start + timedelta(days=100))
        usage = get_appointments_ai_usage(biz, at=self.at)
        self.assertEqual((usage['period_start'], usage['period_end'], usage['used']), (self.start, boundary, 120))
        nxt = get_appointments_ai_usage(biz, at=boundary + timedelta(hours=1))
        self.assertEqual((nxt['period_start'], nxt['used']), (boundary, 0))

    def test_access_continues_after_the_previous_end(self):
        biz, sub = self.grant()
        self.seed(sub, 10, self.start, self.clip_end)
        after_old_end = self.clip_end + timedelta(days=1)
        self.assertEqual(self.rejected(sub, self.clip_end, reason='x'), 'invalid_end')
        self.extend(sub, self.start + timedelta(days=60))
        usage = get_appointments_ai_usage(biz, at=after_old_end)
        self.assertEqual((usage['period_start'], usage['used']), (self.start, 10))

    def test_custom_extension_extends_the_aligned_policy_and_keeps_the_allowance(self):
        biz, sub = self.grant(tier='reception_custom', custom=5)
        policy = ReceptionAIUsagePolicy.objects.get(subscription=sub)
        self.seed(sub, 4, self.start, self.clip_end)
        new_end = self.start + timedelta(days=50)
        result = self.extend(sub, new_end)
        policy.refresh_from_db()
        self.assertEqual((result.custom_policy.pk, policy.valid_until, policy.included_sessions, policy.status),
                         (policy.pk, new_end, 5, 'active'))
        self.assertEqual(ReceptionAIUsagePolicy.objects.filter(subscription=sub).count(), 1)
        [change] = ReceptionAIUsagePolicyChange.objects.filter(subscription=sub, action=Action.EXTENDED)
        self.assertEqual((change.previous_included_sessions, change.new_included_sessions, change.effective_at,
                          change.details['before']['valid_until'], change.details['after']['valid_until']),
                         (5, 5, self.clip_end, self.clip_end.isoformat(), new_end.isoformat()))
        [audit] = _extension_audits(sub)
        self.assertEqual(audit.details['custom_policy_change_id'], str(change.pk))
        later = self.clip_end + timedelta(days=2)
        self.assertEqual(resolve_ai_usage_limit(sub, at=later), 5)
        usage = get_appointments_ai_usage(biz, at=later)
        self.assertEqual((usage['used'], usage['remaining']), (4, 1))

    def test_custom_scheduled_reduction_is_preserved(self):
        end = self.start + timedelta(days=45)
        biz, sub = self.grant(end=end, tier='reception_custom', custom=10)
        boundary = _add_months(self.start, 1)
        change_reception_custom_allowance(subscription=sub, included_sessions=4, actor=self.admin, reason='Baja de cupo')
        current = ReceptionAIUsagePolicy.objects.get(subscription=sub, included_sessions=10)
        scheduled = ReceptionAIUsagePolicy.objects.get(subscription=sub, included_sessions=4)
        self.assertEqual((current.valid_until, scheduled.valid_from, scheduled.valid_until), (boundary, boundary, end))
        new_end = self.start + timedelta(days=95)
        self.extend(sub, new_end)
        current.refresh_from_db()
        scheduled.refresh_from_db()
        self.assertEqual((current.valid_until, scheduled.valid_from, scheduled.valid_until),
                         (boundary, boundary, new_end))
        self.assertEqual(resolve_ai_usage_limit(sub, at=timezone.now()), 10)
        self.assertEqual(resolve_ai_usage_limit(sub, at=end + timedelta(days=1)), 4)
        # The scheduled change is still a pending one; canceling restores the current up to the new end.
        cancel_scheduled_reception_custom_change(subscription=sub, actor=self.admin, reason='Se mantiene')
        current.refresh_from_db()
        self.assertEqual(current.valid_until, new_end)

    def test_revoked_custom_policy_is_never_reactivated(self):
        _, sub = self.grant(tier='reception_custom', custom=5)
        revoke_reception_custom_policy(subscription=sub, actor=self.admin, reason='Revocada')
        self.assertEqual(self.rejected(sub, self.clip_end + timedelta(days=20)), 'custom_policy_not_extendable')
        self.assertEqual(self.snapshot(sub)['current_period_end'], self.clip_end)
        policy = ReceptionAIUsagePolicy.objects.get(subscription=sub)
        self.assertEqual((policy.status, policy.valid_until), ('revoked', self.clip_end))
        self.assertFalse(_extension_audits(sub).exists())


# ── Endpoint ─────────────────────────────────────────────────────────────────

@override_settings(**AI_SETTINGS)
class ExtensionEndpointTests(_ExtBase, TestCase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def post(self, sub, data, business_id=None, client=None):
        return (client or self.client).post(
            extension_url(business_id or sub.business_id, sub.pk), data, format='json',
        )

    def test_contract(self):
        _, sub = self.grant(tier='reception_custom', custom=8)
        new_end = self.start + timedelta(days=40)
        response = self.post(sub, {'complimentary_end': new_end.isoformat(), 'reason': 'Extensión piloto'})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['subscription']['id'], str(sub.pk))
        self.assertEqual((body['subscription']['status'], body['subscription']['usage_tier'],
                          body['subscription']['provider']), ('trialing', 'reception_custom', 'manual'))
        self.assertEqual(body['extension'], {'previous_end': self.clip_end.isoformat(), 'new_end': new_end.isoformat()})
        self.assertEqual((body['custom_policy']['included_sessions'], body['custom_policy']['valid_until']),
                         (8, new_end.isoformat()))

    def test_errors(self):
        _, sub = self.grant()
        later = (self.clip_end + timedelta(days=5)).isoformat()
        cases = [
            ({'complimentary_end': later}, 400, None),
            ({'reason': 'x'}, 400, None),
            ({'complimentary_end': later, 'reason': 'x', 'plan_code': 'reception'}, 400, None),
            ({'complimentary_end': 'mañana', 'reason': 'x'}, 400, None),
            ({'complimentary_end': self.clip_end.isoformat(), 'reason': 'x'}, 400, 'invalid_end'),
            ({'complimentary_end': later, 'reason': '  '}, 400, 'invalid_reason'),
        ]
        for data, status_code, code in cases:
            with self.subTest(data=data):
                response = self.post(sub, data)
                self.assertEqual(response.status_code, status_code, response.content)
                if code:
                    self.assertEqual(response.json()['code'], code)
        foreign = _business()
        response = self.post(sub, {'complimentary_end': later, 'reason': 'x'}, business_id=foreign.pk)
        self.assertEqual((response.status_code, response.json()['code']), (404, 'subscription_not_found'))
        cancel_subscription_immediately(subscription=sub, canceled_by=self.admin, reason='Baja')
        response = self.post(sub, {'complimentary_end': later, 'reason': 'x'})
        self.assertEqual((response.status_code, response.json()['code']), (409, 'subscription_canceled'))
        response = self.client.post(f'/api/v1/platform-admin/clients/{sub.business_id}/subscriptions/123/extension/',
                                    {'complimentary_end': later, 'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_permissions(self):
        from apps.accounts.tests.test_admin_clientes_reception_provisioning_02f2 import _staff

        _, sub = self.grant()
        data = {'complimentary_end': (self.clip_end + timedelta(days=5)).isoformat(), 'reason': 'x'}
        anonymous = APIClient()
        self.assertIn(self.post(sub, data, client=anonymous).status_code, (401, 403))
        for user in (_staff('operations'), _business_user()):
            client = APIClient()
            client.force_authenticate(user=user)
            with self.subTest(user=user.username):
                self.assertEqual(self.post(sub, data, client=client).status_code, 403)
        self.assertEqual(self.snapshot(sub)['current_period_end'], self.clip_end)


# ── Baja definitiva y atención automática ─────────────────────────────────────

@override_settings(**AI_SETTINGS)
class CancellationAttentionTests(_ExtBase, TestCase):

    def config_audits(self, biz):
        return AccessAuditLog.objects.filter(
            action='RECEPTIONIST_CONFIG_UPDATED', business=biz, details__automatic_attention='paused_by_cancellation',
        )

    def test_admin_cancel_pauses_attention_and_a_new_grant_does_not_restore_it(self):
        biz, sub = self.grant()
        config = enable_reception_attention(biz)
        cancel_subscription_immediately(subscription=sub, canceled_by=self.admin, reason='Baja definitiva')
        config.refresh_from_db()
        self.assertEqual((config.automatic_attention_enabled, config.version, config.status), (False, 2, 'ready'))
        [audit] = self.config_audits(biz)
        self.assertEqual((audit.actor_id, audit.details['subscription_id'], audit.details['changed_fields'],
                          audit.details['source']), (self.admin.pk, str(sub.pk), ['automatic_attention_enabled'],
                                                     'platform_admin'))
        # New contract: attention stays paused and authorization is denied.
        now = timezone.now()
        _, new_sub = self.grant(biz, start=now - timedelta(hours=1), end=now + timedelta(days=30))
        config.refresh_from_db()
        self.assertFalse(config.automatic_attention_enabled)
        conversation, credential, _ = self.agent(biz)
        body = self.authorize(credential, conversation, now - timedelta(minutes=1))
        self.assertEqual((body['allowed'], body['reason']), (False, 'automatic_attention_disabled'))
        self.assertFalse(AppointmentAIUsageSession.objects.filter(subscription=new_sub).exists())

    def test_scheduled_cancellation_pauses_attention_as_system(self):
        biz, sub = self.grant()
        config = enable_reception_attention(biz)
        SubscriptionV2.objects.filter(pk=sub.pk).update(cancel_at_period_end=True)
        sub.refresh_from_db()
        with patch('apps.billing.email_helpers.send_cancellation_confirmed_email'):
            execute_cancellation(sub)
        sub.refresh_from_db()
        config.refresh_from_db()
        self.assertEqual((sub.status, config.automatic_attention_enabled), ('canceled', False))
        [audit] = self.config_audits(biz)
        self.assertEqual((audit.actor_id, audit.actor_type, audit.details['source']), (None, 'SYSTEM', 'system'))
        # Idempotent: a second run changes nothing.
        execute_cancellation(sub)
        self.assertEqual(self.config_audits(biz).count(), 1)

    def test_no_config_or_paused_attention_writes_nothing(self):
        for setup in ('missing', 'paused'):
            with self.subTest(setup):
                biz, sub = self.grant()
                if setup == 'paused':
                    config = enable_reception_attention(biz)
                    config.automatic_attention_enabled = False
                    config.save()
                cancel_subscription_immediately(subscription=sub, canceled_by=self.admin, reason='Baja')
                self.assertEqual(SubscriptionV2.objects.get(pk=sub.pk).status, 'canceled')
                self.assertFalse(self.config_audits(biz).exists())

    def test_pause_failure_rolls_the_cancellation_back(self):
        biz, sub = self.grant()
        config = enable_reception_attention(biz)
        with patch('apps.leads.services.receptionist_config.record_platform_action',
                   side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                cancel_subscription_immediately(subscription=sub, canceled_by=self.admin, reason='Baja')
        config.refresh_from_db()
        self.assertEqual((SubscriptionV2.objects.get(pk=sub.pk).status, config.automatic_attention_enabled),
                         ('trialing', True))

    def test_other_products_cancellation_leaves_attention_untouched(self):
        biz, _ = self.grant()
        config = enable_reception_attention(biz)
        other = self.sub(biz, 'appointments', 'appointments_base', provider='manual', status='trialing',
                         billing_cycle='', manual_granted_by=self.admin, manual_grant_reason='x')
        cancel_subscription_immediately(subscription=other, canceled_by=self.admin, reason='Baja Turnos')
        config.refresh_from_db()
        self.assertEqual((config.automatic_attention_enabled, config.version), (True, 1))
        self.assertFalse(self.config_audits(biz).exists())

    def test_cancellation_isolated_per_business(self):
        biz_a, sub_a = self.grant()
        biz_b, _ = self.grant()
        enable_reception_attention(biz_a)
        config_b = enable_reception_attention(biz_b)
        cancel_subscription_immediately(subscription=sub_a, canceled_by=self.admin, reason='Baja')
        config_b.refresh_from_db()
        self.assertTrue(config_b.automatic_attention_enabled)


# ── Concurrencia ─────────────────────────────────────────────────────────────

def _run_parallel(*targets):
    errors, barrier = [], threading.Barrier(len(targets))

    def wrap(fn):
        def run():
            try:
                barrier.wait()
                fn()
            except Exception as exc:  # noqa: BLE001 — collected for assertions
                errors.append(exc)
            finally:
                connection.close()
        return run

    threads = [threading.Thread(target=wrap(fn)) for fn in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return errors


@override_settings(**AI_SETTINGS)
class ExtensionConcurrencyTests(_ExtBase, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def test_concurrent_extensions_serialize_and_keep_policy_aligned(self):
        _, sub = self.grant(tier='reception_custom', custom=6)
        ends = [self.start + timedelta(days=40), self.start + timedelta(days=80)]
        errors = _run_parallel(*[(lambda end=end: self.extend(sub, end)) for end in ends])
        self.assertTrue(all(isinstance(e, ComplimentaryExtensionError) and e.code == 'invalid_end' for e in errors),
                        errors)
        self.assertLessEqual(len(errors), 1)
        self.assertEqual(self.snapshot(sub)['current_period_end'], ends[1])
        [policy] = ReceptionAIUsagePolicy.objects.filter(subscription=sub)
        self.assertEqual(policy.valid_until, ends[1])
        changes = ReceptionAIUsagePolicyChange.objects.filter(subscription=sub, action=Action.EXTENDED).count()
        self.assertEqual(changes, 2 - len(errors))
        self.assertEqual(_extension_audits(sub).count(), 2 - len(errors))

    def test_extension_and_consumption_race_without_deadlock_or_reset(self):
        biz, sub = self.grant()
        self.seed(sub, 299, self.start, self.clip_end)
        conversation, _, instance = self.agent(biz)
        occurred = timezone.now() - timedelta(minutes=1)
        results = []

        def consume():
            _, session, created, usage = authorize_ai_interaction(
                agent_instance=instance, conversation_id=conversation,
                interaction_id=uuid.uuid4(), occurred_at=occurred,
            )
            results.append((created, usage['used']))

        errors = _run_parallel(consume, lambda: self.extend(sub, self.start + timedelta(days=60)))
        self.assertEqual(errors, [])
        self.assertEqual(results, [(True, 300)])
        self.assertEqual(self.snapshot(sub)['current_period_end'], self.start + timedelta(days=60))
        self.assertEqual(AppointmentAIUsageSession.objects.filter(business=biz).count(), 300)

    def test_cancellation_and_authorization_race_without_deadlock(self):
        biz, sub = self.grant()
        conversation, _, instance = self.agent(biz)
        occurred = timezone.now() - timedelta(minutes=1)
        outcomes = []

        def consume():
            try:
                authorize_ai_interaction(agent_instance=instance, conversation_id=conversation,
                                         interaction_id=uuid.uuid4(), occurred_at=occurred)
                outcomes.append('allowed')
            except Exception as exc:  # noqa: BLE001
                outcomes.append(getattr(exc, 'reason', type(exc).__name__))

        errors = _run_parallel(
            consume, lambda: cancel_subscription_immediately(subscription=sub, canceled_by=self.admin, reason='Baja'),
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(SubscriptionV2.objects.get(pk=sub.pk).status, 'canceled')
        self.assertFalse(ReceptionistConfig.objects.get(business=biz).automatic_attention_enabled)
