from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from apps.billing.appointments_plans import AUTOMATIONS, EXTRA_PROFESSIONAL
from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
from apps.billing.plans import get_seat_limit
from apps.billing.payment_webhook import process_payment_event
from apps.billing.runtime import resolve_subscription
from apps.billing.services.appointments import resolve_appointments_subscription_config
from apps.business.context import build_business_context
from apps.business.features import feature_flags_for_v2_subscription
from apps.business.models import Business, Subscription, SubscriptionAddon


class AppointmentsCommercialV2Tests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='S3 Turnos', default_service='appointments')

    def make_subscription(self, plan='appointments', **values):
        fields = dict(
            business=self.business, service_type='appointments', plan_code=plan,
            external_reference=f'SUB-{uuid.uuid4()}', provider='manual', status='active',
        )
        fields.update(values)
        return SubscriptionV2.objects.create(**fields)

    def addon(self, subscription, code=EXTRA_PROFESSIONAL, quantity=1, **values):
        return SubscriptionAddon.objects.create(
            subscription_v2=subscription, code=code, quantity=quantity, **values,
        )

    def test_base_and_pro_accept_null_tier(self):
        for plan in ('appointments', 'appointments_pro'):
            with self.subTest(plan=plan):
                sub = self.make_subscription(plan, status='canceled')
                sub.full_clean(exclude=['price_snapshot'])
                sub.refresh_from_db()
                self.assertIsNone(sub.usage_tier)

    def test_ai_requires_explicit_known_tier_on_create_and_clean(self):
        for tier in (None, '', 'unknown', 'AI_300'):
            with self.subTest(tier=tier):
                with self.assertRaises(ValidationError):
                    self.make_subscription('appointments_ai', usage_tier=tier)
                sub = SubscriptionV2(plan_code='appointments_ai', usage_tier=tier)
                with self.assertRaises(ValidationError):
                    sub.clean()
        for tier in ('ai_300', 'ai_1500', 'ai_3000', 'custom'):
            with self.subTest(tier=tier):
                self.make_subscription('appointments_ai', usage_tier=tier, status='canceled')

    def test_non_ai_plans_reject_tiers(self):
        for plan in ('appointments', 'appointments_pro'):
            for tier in ('ai_300', 'ai_1500', 'custom', 'unknown', ''):
                with self.subTest(plan=plan, tier=tier), self.assertRaises(ValidationError):
                    self.make_subscription(plan, usage_tier=tier)

    def test_transition_to_ai_requires_tier(self):
        sub = self.make_subscription()
        sub.plan_code = 'appointments_ai'
        with self.assertRaises(ValidationError):
            sub.save()
        sub.usage_tier = 'ai_1500'
        sub.save()
        sub.refresh_from_db()
        self.assertEqual(sub.usage_tier, 'ai_1500')
        sub.usage_tier = None
        with self.assertRaises(ValidationError):
            sub.save()

    def test_partial_plan_save_cannot_omit_required_tier(self):
        sub = self.make_subscription()
        sub.plan_code = 'appointments_ai'
        sub.usage_tier = 'ai_300'
        with self.assertRaises(ValidationError):
            sub.save(update_fields=['plan_code'])
        sub.save(update_fields=['plan_code', 'usage_tier'])
        sub.refresh_from_db()
        self.assertEqual(sub.usage_tier, 'ai_300')

    def test_existing_nullable_ai_is_readable_without_defaulting_tier(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        # Simulate the row already present before the expansive migration.
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier=None)
        sub.refresh_from_db()
        sub.clean()
        sub.cancel_at_period_end = True
        sub.save(update_fields=['cancel_at_period_end'])
        config = resolve_appointments_subscription_config(sub)
        self.assertIsNone(config.usage_tier)
        self.assertIsNone(config.usage_tier_config)
        self.assertFalse(config.ai_enabled)
        self.assertTrue(config.automations_enabled)
        self.assertIn('appointments.leads', resolve_subscription(self.business).entitlements)

    def test_unknown_persisted_tier_fails_closed_in_service_runtime_and_flags(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier='unknown')
        sub.refresh_from_db()
        with self.assertRaises(ValidationError):
            resolve_appointments_subscription_config(sub)
        resolved = resolve_subscription(self.business)
        self.assertFalse(resolved.entitlements)
        self.assertFalse(resolved.access_granted)
        flags = feature_flags_for_v2_subscription(sub, self.business)
        self.assertFalse(flags['appointments_core'])
        self.assertFalse(flags['appointments_automations'])

    def test_s1_misclassified_turnos_plan_still_validates_tier(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300', service_type='gestion')
        self.assertIn(
            'appointments.automations',
            resolve_subscription(self.business, service_type='appointments').entitlements,
        )
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier='unknown')
        resolved = resolve_subscription(self.business, service_type='appointments')
        self.assertFalse(resolved.access_granted)
        self.assertFalse(resolved.entitlements)

    def test_legacy_addon_owner_and_limits_unchanged(self):
        legacy = Subscription.objects.create(business=self.business, plan='pro', service='gestion')
        addon = SubscriptionAddon.objects.create(subscription=legacy, code='extra_seat', quantity=3)
        addon.refresh_from_db()
        self.assertIsNone(addon.subscription_v2_id)
        self.assertEqual(legacy.effective_max_seats, legacy.max_seats + 3)
        self.assertIn(self.business.name, str(addon))

    def test_v2_owner_relation_and_display(self):
        sub = self.make_subscription()
        addon = self.addon(sub, quantity=3)
        self.assertEqual(sub.addons.get().pk, addon.pk)
        self.assertIsNone(addon.subscription_id)
        self.assertIn(self.business.name, str(addon))

    def test_xor_rejected_by_model_and_database(self):
        sub = self.make_subscription()
        legacy = Subscription.objects.create(business=self.business)
        for owners in ({}, {'subscription': legacy, 'subscription_v2': sub}):
            with self.subTest(owners=owners):
                with self.assertRaises(ValidationError):
                    SubscriptionAddon.objects.create(code='extra_seat', **owners)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    SubscriptionAddon.objects.bulk_create([
                        SubscriptionAddon(code='extra_seat', **owners),
                    ])

    def test_unique_owner_code_even_inactive(self):
        sub = self.make_subscription()
        legacy = Subscription.objects.create(business=self.business)
        for owners, code in (
            ({'subscription': legacy}, 'extra_seat'),
            ({'subscription_v2': sub}, EXTRA_PROFESSIONAL),
        ):
            SubscriptionAddon.objects.create(code=code, **owners)
            with self.assertRaises(IntegrityError), transaction.atomic():
                SubscriptionAddon.objects.create(code=code, is_active=False, **owners)
        other = self.make_subscription(status='canceled')
        self.addon(other)

    def test_automations_quantity_zero_or_one_only(self):
        sub = self.make_subscription()
        addon = self.addon(sub, AUTOMATIONS, 0)
        addon.quantity = 1
        addon.save()
        for quantity in (-1, 2, 1.5, Decimal('1.5'), '1', True, None):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                addon.quantity = quantity
                addon.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SubscriptionAddon.objects.filter(pk=addon.pk).update(quantity=2)

    def test_extra_professionals_integer_nonnegative_only(self):
        sub = self.make_subscription()
        addon = self.addon(sub, quantity=0)
        addon.quantity = 12
        addon.save()
        for quantity in (-1, 0.1, Decimal('1.1'), '2', True, None):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                addon.quantity = quantity
                addon.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SubscriptionAddon.objects.filter(pk=addon.pk).update(quantity=-1)

    def test_full_clean_does_not_truncate_decimal_quantity(self):
        sub = self.make_subscription()
        for quantity in (1.5, Decimal('1.5'), True):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                SubscriptionAddon(
                    subscription_v2=sub, code=EXTRA_PROFESSIONAL, quantity=quantity,
                ).full_clean()

    def test_partial_addon_save_validates_persisted_combination(self):
        sub = self.make_subscription()
        addon = self.addon(sub, quantity=3)
        addon.code = AUTOMATIONS
        addon.quantity = 1
        with self.assertRaises(ValidationError):
            addon.save(update_fields=['code'])
        addon.save(update_fields=['code', 'quantity'])
        addon.refresh_from_db()
        self.assertEqual(addon.quantity, 1)

    def test_effective_limits_base_pro_ai_with_extras(self):
        for plan, included, tiers in (
            ('appointments', 2, (None,)),
            ('appointments_pro', 5, (None,)),
            ('appointments_ai', 5, ('ai_300', 'ai_1500', 'ai_3000')),
        ):
            for tier in tiers:
                with self.subTest(plan=plan, usage_tier=tier):
                    sub = self.make_subscription(plan, usage_tier=tier, status='canceled')
                    self.addon(sub, quantity=3)
                    config = resolve_appointments_subscription_config(sub)
                    self.assertEqual(config.plan_code, plan)
                    self.assertEqual(config.included_professionals, included)
                    self.assertEqual(config.included_secondary_users, included)
                    self.assertEqual(get_seat_limit(plan), config.included_secondary_users)
                    self.assertEqual(config.extra_professionals, 3)
                    self.assertEqual(config.effective_professional_limit, included + 3)

    def test_extra_professional_addon_does_not_increase_membership_seats(self):
        sub = self.make_subscription('appointments_pro', status='canceled')
        self.addon(sub, quantity=3)
        config = resolve_appointments_subscription_config(sub)
        self.assertEqual(config.effective_professional_limit, 8)
        self.assertEqual(config.included_secondary_users, 5)
        self.assertEqual(get_seat_limit(config.plan_code), 5)

    def test_inactive_extra_does_not_increase_limit(self):
        sub = self.make_subscription()
        self.addon(sub, quantity=3, is_active=False)
        self.assertEqual(resolve_appointments_subscription_config(sub).effective_professional_limit, 2)

    def test_ai_includes_automations_without_addon_and_redundancy_is_detected(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300')
        config = resolve_appointments_subscription_config(sub)
        self.assertTrue(config.ai_enabled)
        self.assertTrue(config.automations_enabled)
        self.assertFalse(sub.addons.exists())
        self.assertIn('appointments.automations', resolve_subscription(self.business).entitlements)
        self.assertTrue(feature_flags_for_v2_subscription(sub, self.business)['appointments_automations'])
        addon = self.addon(sub, AUTOMATIONS)
        with self.assertLogs('apps.billing.services.appointments', level='WARNING'):
            config = resolve_appointments_subscription_config(sub)
        self.assertEqual(config.redundant_addons, (AUTOMATIONS,))
        self.assertEqual(config.effective_professional_limit, 5)
        self.assertTrue(SubscriptionAddon.objects.filter(pk=addon.pk).exists())
        sub.refresh_from_db()
        self.assertEqual(sub.price_snapshot, {})

    def test_base_pro_automations_require_active_positive_addon(self):
        for plan in ('appointments', 'appointments_pro'):
            with self.subTest(plan=plan):
                sub = self.make_subscription(plan)
                self.assertNotIn('appointments.automations', resolve_subscription(self.business).entitlements)
                addon = self.addon(sub, AUTOMATIONS, 0)
                for quantity, active, expected in ((0, True, False), (1, True, True), (1, False, False)):
                    addon.quantity, addon.is_active = quantity, active
                    addon.save()
                    self.assertEqual(resolve_appointments_subscription_config(sub).automations_enabled, expected)
                    self.assertEqual(
                        'appointments.automations' in resolve_subscription(self.business).entitlements, expected,
                    )
                    self.assertEqual(
                        feature_flags_for_v2_subscription(sub, self.business)['appointments_automations'], expected,
                    )
                sub.status = 'canceled'
                sub.save()

    def test_suspended_subscription_does_not_grant_automations(self):
        sub = self.make_subscription('appointments_ai', usage_tier='ai_300', status='suspended')
        self.assertNotIn('appointments.automations', resolve_subscription(self.business).entitlements)

    def test_gestion_addons_do_not_grant_turnos_or_leak_into_turnos(self):
        legacy = Subscription.objects.create(business=self.business, plan='starter', service='gestion')
        SubscriptionAddon.objects.create(subscription=legacy, code='invoices_module')
        sub = self.make_subscription()
        entitlements = resolve_subscription(self.business).entitlements
        self.assertNotIn('gestion.invoices', entitlements)
        self.assertNotIn('appointments.automations', entitlements)
        with self.assertRaises(ValidationError):
            self.addon(sub, 'invoices_module')

    def test_turnos_addons_do_not_grant_gestion(self):
        turnos = self.make_subscription()
        self.addon(turnos, AUTOMATIONS)
        gestion = self.make_subscription('starter', service_type='gestion')
        resolved = resolve_subscription(self.business, service_type='gestion')
        self.assertNotIn('appointments.automations', resolved.entitlements)
        self.assertNotIn('gestion.invoices', resolved.entitlements)
        with self.assertRaises(ValidationError):
            self.addon(gestion, AUTOMATIONS)
        legacy = Subscription.objects.create(business=self.business, plan='pro', service='gestion')
        with self.assertRaises(ValidationError):
            SubscriptionAddon.objects.create(subscription=legacy, code=AUTOMATIONS)

    def test_hybrid_business_context_uses_native_turnos_addon(self):
        self.business.default_service = 'gestion'
        self.business.save()
        self.make_subscription('starter', service_type='gestion')
        sub = self.make_subscription()
        self.addon(sub, AUTOMATIONS)
        context = build_business_context(self.business)
        self.assertTrue(context['features']['appointments_automations'])
        self.assertIn('appointments', context['enabled_services'])

    def test_custom_remains_economically_incomplete(self):
        sub = self.make_subscription('appointments_ai', usage_tier='custom')
        config = resolve_appointments_subscription_config(sub)
        self.assertEqual(config.usage_tier, 'custom')
        for key in ('monthly_price', 'annual_price', 'included_conversations',
                    'extra_conversation_price', 'default_extra_spend_limit'):
            self.assertIsNone(config.usage_tier_config[key])

    def make_pending(self, **values):
        fields = dict(
            business=self.business,
            user=get_user_model().objects.create_user(username=f'user-{uuid.uuid4()}'),
            target_plan_code='pro', billing_cycle='monthly',
            config_snapshot={'crm': True, 'branches_extra_qty': 2},
            total_amount=1000,
        )
        fields.update(values)
        return PendingSubscriptionChange.objects.create(**fields)

    def test_historical_pending_change_unchanged(self):
        pending = self.make_pending()
        pending.status = 'completed'
        pending.save()
        pending.refresh_from_db()
        self.assertIsNone(pending.subscription_v2_id)
        self.assertIsNone(pending.target_usage_tier)
        self.assertEqual(pending.config_snapshot, {'crm': True, 'branches_extra_qty': 2})
        self.assertEqual(pending.total_amount, 1000)

    def test_pending_v2_represents_plan_tier_addons_quantities_and_cycle(self):
        sub = self.make_subscription()
        snapshot = {'addons': {AUTOMATIONS: 0}, 'quantities': {EXTRA_PROFESSIONAL: 3}}
        pending = self.make_pending(
            subscription_v2=sub, target_plan_code='appointments_ai', target_usage_tier='custom',
            config_snapshot=snapshot, billing_cycle='yearly', total_amount=None,
        )
        pending.refresh_from_db()
        self.assertEqual(pending.subscription_v2_id, sub.pk)
        self.assertEqual(pending.target_usage_tier, 'custom')
        self.assertEqual(pending.config_snapshot, snapshot)
        self.assertEqual(pending.billing_cycle, 'yearly')
        self.assertIsNone(pending.total_amount)
        sub.refresh_from_db()
        self.assertEqual(sub.plan_code, 'appointments')
        self.assertFalse(sub.addons.exists())

    def test_invalid_pending_configuration_rejected(self):
        sub = self.make_subscription()
        cases = (
            {'target_plan_code': 'appointments_ai'},
            {'target_usage_tier': 'ai_300'},
            {'billing_cycle': 'weekly'},
            {'config_snapshot': {'addons': {AUTOMATIONS: 2}}},
            {'config_snapshot': {'quantities': {EXTRA_PROFESSIONAL: -1}}},
            {'config_snapshot': {'quantities': {EXTRA_PROFESSIONAL: 1.1}}},
            {'config_snapshot': {'addons': {'invoices_module': 1}}},
            {'config_snapshot': []},
            {'business': Business.objects.create(name='Other')},
        )
        for values in cases:
            fields = dict(subscription_v2=sub, target_plan_code='appointments', config_snapshot={})
            fields.update(values)
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.make_pending(**fields)

    def test_partial_pending_save_cannot_omit_tier(self):
        sub = self.make_subscription()
        pending = self.make_pending(
            subscription_v2=sub, target_plan_code='appointments_pro', config_snapshot={},
        )
        pending.target_plan_code = 'appointments_ai'
        pending.target_usage_tier = 'ai_300'
        with self.assertRaises(ValidationError):
            pending.save(update_fields=['target_plan_code'])
        pending.save(update_fields=['target_plan_code', 'target_usage_tier'])

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_pending_v2_cannot_enter_legacy_payment_apply(self, provider):
        sub = self.make_subscription()
        pending = self.make_pending(
            subscription_v2=sub, target_plan_code='appointments_pro', config_snapshot={},
        )
        result = process_payment_event('not-a-real-payment', flow='billing', ref=f'subscription_change_{pending.pk}')
        self.assertEqual(result.category, 'billing_v2_change_not_supported')
        provider.assert_not_called()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'pending_payment')


class AppointmentsCommercialMigrationTests(TransactionTestCase):
    available_apps = settings.INSTALLED_APPS

    def test_expansive_migrations_preserve_legacy_rows(self):
        before = [('billing', '0023_webhookdelivery_retry_lifecycle'),
                  ('business', '0027_alter_subscription_plan')]
        after = [('billing', '0025_subscriptionv2_billing_cycle_appointmentscheckout'),
                 ('business', '0028_subscriptionaddon_v2_owner')]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            business = apps.get_model('business', 'Business').objects.create(
                name='Historical S3', default_service='appointments',
            )
            legacy = apps.get_model('business', 'Subscription').objects.create(
                business=business, plan='pro', service='gestion',
            )
            addon = apps.get_model('business', 'SubscriptionAddon').objects.create(
                subscription=legacy, code='extra_seat', quantity=4,
            )
            v2 = apps.get_model('billing', 'SubscriptionV2').objects.create(
                business=business, service_type='appointments', plan_code='appointments_ai',
                external_reference=f'SUB-{uuid.uuid4()}', provider='manual', status='active',
            )
            user_model = get_user_model()
            user = apps.get_model(user_model._meta.app_label, user_model._meta.model_name).objects.create(
                username='historical-s3', email='historical-s3@example.test',
            )
            pending = apps.get_model('billing', 'PendingSubscriptionChange').objects.create(
                business=business, user=user, target_plan_code='pro', billing_cycle='monthly',
                config_snapshot={'crm': True}, total_amount=1000,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            migrated = SubscriptionV2.objects.get(pk=v2.pk)
            self.assertIsNone(migrated.usage_tier)
            config = resolve_appointments_subscription_config(migrated)
            self.assertIsNone(config.usage_tier)
            self.assertTrue(config.automations_enabled)
            migrated_addon = SubscriptionAddon.objects.get(pk=addon.pk)
            self.assertEqual(migrated_addon.subscription_id, legacy.pk)
            self.assertIsNone(migrated_addon.subscription_v2_id)
            self.assertEqual(migrated_addon.quantity, 4)
            migrated_pending = PendingSubscriptionChange.objects.get(pk=pending.pk)
            self.assertIsNone(migrated_pending.subscription_v2_id)
            self.assertIsNone(migrated_pending.target_usage_tier)
            self.assertEqual(migrated_pending.config_snapshot, {'crm': True})
            self.assertEqual(migrated_pending.total_amount, 1000)
        finally:
            MigrationExecutor(connection).migrate(latest)
