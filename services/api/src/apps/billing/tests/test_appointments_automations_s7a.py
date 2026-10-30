from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.billing.appointments_plans import AUTOMATIONS
from apps.billing.models import BillingInvoiceEvent, SubscriptionV2
from apps.billing.runtime import resolve_subscription
from apps.billing.services.appointments import (
    can_use_appointments_automations,
    resolve_appointments_subscription_config,
)
from apps.billing.services.appointments_lifecycle import (
    GRACE_PERIOD,
    apply_appointments_change,
    apply_appointments_renewal,
    can_send_appointments_automation,
    record_appointments_payment_failure,
    request_appointments_change,
)
from apps.business.context import build_business_context
from apps.business.entitlements import APPOINTMENTS_AUTOMATIONS_ENTITLEMENT, has_entitlement
from apps.business.features import (
    feature_flags_for_subscription,
    feature_flags_for_v2_subscription,
)
from apps.business.models import Business, Subscription, SubscriptionAddon


class AppointmentsAutomationsS7ATests(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        clock = patch('django.utils.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.business = Business.objects.create(
            name='Turnos S7A', default_service='appointments', status='active',
        )
        self.user = get_user_model().objects.create_user(username=f's7a-{uuid.uuid4()}')
        self.period_end = self.now + timedelta(days=15)

    def make_subscription(self, plan='appointments', **values):
        fields = {
            'business': self.business,
            'service_type': 'appointments',
            'plan_code': plan,
            'provider': 'manual',
            'status': 'active',
            'is_active': True,
            'external_reference': f'SUB-{uuid.uuid4()}',
            'billing_cycle': 'monthly',
            'current_period_start': self.now - timedelta(days=15),
            'current_period_end': self.period_end,
        }
        fields.update(values)
        return SubscriptionV2.objects.create(**fields)

    def addon(self, subscription, *, quantity=1, active=True):
        return SubscriptionAddon.objects.create(
            subscription_v2=subscription, code=AUTOMATIONS,
            quantity=quantity, is_active=active,
        )

    def assert_access(self, expected, subscription=None):
        self.assertIs(can_use_appointments_automations(self.business), expected)
        self.assertIs(can_send_appointments_automation(self.business), expected)
        self.assertIs(
            has_entitlement(self.business, APPOINTMENTS_AUTOMATIONS_ENTITLEMENT),
            expected,
        )
        self.assertIs(
            build_business_context(self.business)['features']['appointments_automations'],
            expected,
        )
        if subscription is not None:
            subscription.refresh_from_db()
            self.assertIs(
                feature_flags_for_v2_subscription(
                    subscription, self.business,
                )['appointments_automations'],
                expected,
            )

    def test_base_without_addon(self):
        self.assert_access(False, self.make_subscription())

    def test_base_with_active_addon(self):
        sub = self.make_subscription()
        self.addon(sub)
        self.assert_access(True, sub)

    def test_pro_without_addon(self):
        self.assert_access(False, self.make_subscription('appointments_pro'))

    def test_pro_with_active_addon(self):
        sub = self.make_subscription('appointments_pro')
        self.addon(sub)
        self.assert_access(True, sub)

    def test_zero_quantity_addon_does_not_grant_access(self):
        sub = self.make_subscription()
        self.addon(sub, quantity=0)
        self.assert_access(False, sub)

    def test_inactive_addon_does_not_grant_access(self):
        sub = self.make_subscription('appointments_pro')
        self.addon(sub, active=False)
        self.assert_access(False, sub)

    def test_ai_300_includes_automations_without_addon(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        self.assert_access(True, sub)
        self.assertFalse(sub.addons.exists())

    def test_ai_1500_includes_automations_without_addon(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_1500')
        self.assert_access(True, sub)
        self.assertFalse(sub.addons.exists())

    def test_ai_3000_includes_automations_without_addon(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_3000')
        self.assert_access(True, sub)
        self.assertFalse(sub.addons.exists())

    def test_ai_custom_preserves_s3_inclusion_without_metering(self):
        sub = self.make_subscription('appointments_ai', usage_tier='custom')
        self.assert_access(True, sub)
        self.assertFalse(sub.addons.exists())

    def test_redundant_ai_addon_has_no_additional_effect_or_writes(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        before = resolve_appointments_subscription_config(sub)
        entitlements = resolve_subscription(self.business).entitlements
        addon = self.addon(sub)
        with self.assertLogs('apps.billing.services.appointments', level='WARNING'):
            self.assert_access(True, sub)
            after = resolve_appointments_subscription_config(sub)
            self.assertEqual(resolve_subscription(self.business).entitlements, entitlements)
        self.assertEqual(after.redundant_addons, (AUTOMATIONS,))
        self.assertEqual(after.automations_enabled, before.automations_enabled)
        addon.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(sub.addons.count(), 1)
        self.assertEqual(addon.quantity, 1)
        self.assertTrue(addon.is_active)
        self.assertEqual(sub.price_snapshot, {})

    def test_addon_access_is_preserved_during_three_day_grace(self):
        sub = self.make_subscription('appointments_pro')
        self.addon(sub)
        record_appointments_payment_failure(subscription=sub, at=self.now)
        sub.refresh_from_db()
        self.assertEqual(sub.grace_until, self.now + timedelta(days=3))
        self.assert_access(True, sub)
        self.assertTrue(
            can_use_appointments_automations(self.business, at=self.now + GRACE_PERIOD),
        )
        self.assertFalse(can_use_appointments_automations(
            self.business, at=self.now + GRACE_PERIOD + timedelta(microseconds=1),
        ))

    def test_ai_access_is_preserved_during_grace(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_1500')
        record_appointments_payment_failure(subscription=sub, at=self.now)
        self.assert_access(True, sub)

    def test_grace_does_not_grant_a_missing_entitlement(self):
        sub = self.make_subscription('appointments_pro')
        record_appointments_payment_failure(subscription=sub, at=self.now)
        self.assert_access(False, sub)

    def test_expired_grace_denies_even_before_suspension_job(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300', status='past_due',
            grace_until=self.now - timedelta(microseconds=1),
        )
        self.assert_access(False, sub)

    def test_past_due_without_grace_deadline_fails_closed(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300', status='past_due',
        )
        self.assert_access(False, sub)

    def test_suspended_after_grace_blocks_addon_and_ai(self):
        sub = self.make_subscription(
            status='suspended', grace_until=self.now - timedelta(days=1),
        )
        self.addon(sub)
        self.assert_access(False, sub)
        sub.plan_code, sub.usage_tier = 'appointments_ai', 'ai_300'
        sub.save(update_fields=['plan_code', 'usage_tier'])
        self.assert_access(False, sub)

    def test_scheduled_cancellation_retains_access_only_until_boundary(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300', cancel_at_period_end=True,
        )
        self.assert_access(True, sub)
        with patch('django.utils.timezone.now', return_value=self.period_end):
            self.assert_access(False, sub)

    def test_scheduled_cancellation_does_not_grant_missing_addon(self):
        sub = self.make_subscription(cancel_at_period_end=True)
        self.assert_access(False, sub)
        self.addon(sub)
        self.assert_access(True, sub)

    def test_cancellation_without_period_end_fails_closed(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300',
            cancel_at_period_end=True, current_period_end=None,
        )
        with self.assertLogs('apps.billing.services.appointments', level='WARNING'):
            self.assert_access(False, sub)

    def test_reactivation_resolves_current_configuration_again(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300', status='suspended',
        )
        self.assert_access(False, sub)
        event = BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=f's7a-{uuid.uuid4()}',
            provider_status='authorized', paid_at=self.now,
            amount=39000, currency='ARS',
        )
        self.assertTrue(apply_appointments_renewal(subscription=sub, invoice_event=event))
        self.assert_access(True, sub)

    def test_pending_downgrade_keeps_ai_until_applied(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        pending, _ = request_appointments_change(
            business=self.business, user=self.user,
            target={'plan_code': 'appointments_pro', 'usage_tier': None},
            at=self.now,
        )
        self.assertEqual(pending.status, 'scheduled')
        self.assertEqual(pending.scheduled_for, self.period_end)
        self.assert_access(True, sub)
        self.assertEqual(sub.plan_code, 'appointments_ai')
        # An overdue intention still does not replace the persisted configuration.
        with patch('django.utils.timezone.now', return_value=self.period_end):
            self.assert_access(True, sub)

    def test_applied_downgrade_removes_ai_inclusion(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        pending, _ = request_appointments_change(
            business=self.business, user=self.user,
            target={'plan_code': 'appointments_pro', 'usage_tier': None},
            at=self.now,
        )
        self.assert_access(True, sub)
        self.assertTrue(apply_appointments_change(pending, at=self.period_end))
        self.assert_access(False, sub)
        self.assertEqual(sub.plan_code, 'appointments_pro')

    def test_pending_then_immediate_upgrade_to_ai(self):
        sub = self.make_subscription('appointments_pro')
        pending, _ = request_appointments_change(
            business=self.business, user=self.user,
            target={'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'},
            at=self.now,
        )
        self.assertEqual(pending.status, 'pending_payment')
        self.assert_access(False, sub)
        self.assertTrue(apply_appointments_change(
            pending, payment_id='s7a-local-payment', at=self.now,
        ))
        self.assert_access(True, sub)
        self.assertEqual(sub.plan_code, 'appointments_ai')

    def test_pending_addon_removal_does_not_change_current_access(self):
        sub = self.make_subscription('appointments_pro')
        self.addon(sub)
        pending, _ = request_appointments_change(
            business=self.business, user=self.user,
            target={'automations': False}, at=self.now,
        )
        self.assert_access(True, sub)
        self.assertTrue(apply_appointments_change(pending, at=self.period_end))
        self.assert_access(False, sub)

    def test_absence_of_subscription(self):
        self.assert_access(False)

    def test_only_canceled_or_checkout_pending_subscription(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300', status='canceled',
        )
        self.assert_access(False, sub)
        sub.status = 'checkout_pending'
        sub.save(update_fields=['status'])
        self.assert_access(False, sub)

    def test_trial_and_unknown_lifecycle_states_fail_closed(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300', status='trialing',
            trial_ends_at=self.period_end,
        )
        self.assert_access(False, sub)
        SubscriptionV2.objects.filter(pk=sub.pk).update(status='unknown')
        self.assert_access(False, sub)

    def test_unknown_or_ambiguous_plan_codes_fail_closed(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        self.addon(sub)
        for code in ('unknown', 'pro', 'appointments_future', 'appointments_ai_unknown'):
            with self.subTest(code=code):
                SubscriptionV2.objects.filter(pk=sub.pk).update(
                    plan_code=code,
                    usage_tier='ai_300' if code.startswith('appointments_ai') else None,
                )
                self.assert_access(False, sub)

    def test_unknown_persisted_ai_tier_fails_closed(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier='unknown')
        with self.assertLogs('apps.billing.services.appointments', level='ERROR'):
            self.assert_access(False, sub)

    def test_legacy_null_ai_tier_keeps_s3_automations_inclusion(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier=None)
        self.assert_access(True, sub)

    def test_legacy_base_addon_is_not_newly_recognized(self):
        legacy = Subscription.objects.create(
            business=self.business, service='appointments',
            plan='appointments_base', status='active',
        )
        # Historical rows bypass today's prohibition on legacy Turnos add-on owners.
        SubscriptionAddon.objects.bulk_create([
            SubscriptionAddon(subscription=legacy, code=AUTOMATIONS, quantity=1),
        ])
        self.assertNotIn(
            APPOINTMENTS_AUTOMATIONS_ENTITLEMENT,
            resolve_subscription(self.business, service_type='appointments').entitlements,
        )
        self.assert_access(False)
        self.assertFalse(feature_flags_for_subscription(legacy)['appointments_automations'])

    def test_v2_legacy_base_does_not_gain_new_addon_support(self):
        sub = self.make_subscription()
        self.addon(sub)
        SubscriptionV2.objects.filter(pk=sub.pk).update(plan_code='appointments_base')
        self.assert_access(False, sub)

    def test_legacy_ai_without_v2_configuration_fails_closed(self):
        legacy = Subscription.objects.create(
            business=self.business, service='appointments',
            plan='appointments_ai', status='active',
        )
        self.assert_access(False)
        self.assertFalse(feature_flags_for_subscription(legacy)['appointments_automations'])

    def test_hybrid_business_uses_turnos_configuration_not_gestion(self):
        self.business.default_service = 'gestion'
        self.business.save(update_fields=['default_service'])
        self.make_subscription('starter', service_type='gestion')
        sub = self.make_subscription('appointments_pro')
        self.addon(sub)
        self.assert_access(True, sub)
        sub.status = 'suspended'
        sub.save(update_fields=['status'])
        self.assert_access(False, sub)

    def test_other_service_does_not_supply_turnos_subscription(self):
        self.make_subscription('pro', service_type='gestion')
        self.assert_access(False)

    def test_misclassified_subscription_fails_s6_lifecycle_closed(self):
        sub = self.make_subscription(
            'appointments_ai', usage_tier='ai_300', service_type='gestion',
        )
        self.assert_access(False, sub)
