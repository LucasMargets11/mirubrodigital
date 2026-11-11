from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.billing import canonical_pricing
from apps.billing.models import (
    AppointmentsCheckout,
    BillingInvoiceEvent,
    Plan,
    SubscriptionV2,
    WebhookDelivery,
)
from apps.billing.services.appointments_checkout import (
    ManualContractRequired,
    apply_appointments_preapproval,
    create_appointments_checkout,
    quote_appointments,
)
from apps.billing.webhook_lifecycle import WebhookPermanentError
from apps.billing.views import AppointmentsCheckoutView, AppointmentsQuoteView
from apps.business.models import Business, Subscription as LegacySubscription, SubscriptionAddon

User = get_user_model()


class AppointmentsQuoteS5Tests(TestCase):
    def quote(self, plan_code, **values):
        return quote_appointments(
            plan_code=plan_code,
            billing_cycle=values.pop('billing_cycle', 'monthly'),
            **values,
        )

    def test_base_monthly_and_addon_combinations(self):
        self.assertEqual(self.quote('appointments')['total_amount'], 23000)
        base_automations = self.quote('appointments', automations=True)
        self.assertEqual(base_automations['addons_amount'], 8500)
        self.assertEqual(base_automations['total_amount'], 31500)
        base_extras = self.quote('appointments', extra_professionals=2)
        self.assertEqual(base_extras['extras_amount'], 6000)
        self.assertEqual(base_extras['total_amount'], 29000)
        combined = self.quote('appointments', automations=True, extra_professionals=2)
        self.assertEqual(combined['total_amount'], 37500)

    def test_pro_monthly_and_extra_professional(self):
        self.assertEqual(self.quote('appointments_pro')['total_amount'], 28000)
        self.assertEqual(
            self.quote('appointments_pro', extra_professionals=1)['total_amount'],
            31000,
        )
        self.assertEqual(self.quote('appointments_pro', automations=True)['total_amount'], 36500)

    def test_all_self_service_ia_tiers_are_full_prices(self):
        for tier, amount in (
            ('ai_300', 150000),
            ('ai_1500', 275000),
            ('ai_3000', 385000),
        ):
            with self.subTest(tier=tier):
                quote = self.quote('appointments_ai', usage_tier=tier)
                self.assertEqual(quote['base_amount'], amount)
                self.assertEqual(quote['addons_amount'], 0)
                self.assertEqual(quote['total_amount'], amount)

    def test_ia_automations_are_included_and_extras_are_charged_once(self):
        quote = self.quote(
            'appointments_ai',
            usage_tier='ai_1500',
            automations=True,
            extra_professionals=2,
        )
        self.assertEqual(quote['automations'], 'included')
        self.assertEqual(quote['addons_amount'], 0)
        self.assertEqual(quote['extras_amount'], 6000)
        self.assertEqual(quote['total_amount'], 281000)
        self.assertEqual(
            [line for line in quote['line_items'] if line['code'] == 'appointments_automations'][0]['total'],
            0,
        )

    def test_annual_prices_are_taken_directly_from_canonical_catalog(self):
        for plan, amount in (
            ('appointments', 220800),
            ('appointments_pro', 268800),
        ):
            with self.subTest(plan=plan):
                self.assertEqual(
                    self.quote(plan, billing_cycle='yearly')['total_amount'],
                    amount,
                )
        self.assertEqual(
            self.quote('appointments_ai', billing_cycle='yearly', usage_tier='ai_3000')['total_amount'],
            3696000,
        )
        self.assertEqual(
            self.quote('appointments', billing_cycle='yearly', extra_professionals=2)['extras_amount'],
            57600,
        )
        self.assertEqual(
            self.quote('appointments', billing_cycle='yearly', automations=True)['addons_amount'],
            81600,
        )

    def test_invalid_tiers_and_required_ai_tier_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.quote('appointments', usage_tier='ai_300')
        with self.assertRaises(ValidationError):
            self.quote('appointments_ai')
        with self.assertRaises(ValidationError):
            self.quote('appointments_ai', usage_tier='unknown')

    def test_custom_requires_manual_contract(self):
        with self.assertRaises(ManualContractRequired):
            self.quote('appointments_ai', usage_tier='custom')

    def test_staff_quote_returns_contact_sales_for_custom(self):
        user = User.objects.create_user(
            username='turnos-staff-custom@test.invalid',
            email='turnos-staff-custom@test.invalid',
            is_staff=True,
        )
        request = APIRequestFactory().post(
            '/billing/internal/appointments/quote/',
            {
                'plan_code': 'appointments_ai',
                'billing_cycle': 'monthly',
                'usage_tier': 'custom',
            },
            format='json',
        )
        force_authenticate(request, user=user)
        response = AppointmentsQuoteView.as_view()(request)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {
            'status': 'contact_sales',
            'code': 'manual_contract_required',
        })

    def test_invalid_extra_quantities_and_automation_quantities_are_rejected(self):
        for quantity in (-1, 1.5, Decimal('2.0'), True):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.quote('appointments', extra_professionals=quantity)
        with self.assertRaises(ValidationError):
            self.quote('appointments', automations_quantity=2)

    def test_legacy_appointments_base_is_not_a_canonical_plan(self):
        with self.assertRaises(ValidationError):
            self.quote('appointments_base')
        self.assertIsNone(canonical_pricing.get_plan('appointments_base'))
        self.assertFalse(Plan.objects.filter(code='appointments_base').exists())

    def test_catalog_remains_inactive_and_public_checkout_has_no_bypass(self):
        self.assertFalse(canonical_pricing.get_product('appointments')['is_active'])
        user = User.objects.create_user(username='turnos-staff@test.invalid', email='turnos-staff@test.invalid')
        business = Business.objects.create(name='Inactive product business')
        with patch('apps.billing.mp_service.MercadoPagoService.create_preapproval_plan') as provider:
            with self.assertRaisesRegex(ValueError, 'not available'):
                create_appointments_checkout(
                    user=user,
                    business=business,
                    plan_code='appointments',
                    billing_cycle='monthly',
                )
            provider.assert_not_called()

    def test_internal_quote_and_checkout_endpoints_reject_anonymous_access(self):
        factory = APIRequestFactory()
        quote_response = AppointmentsQuoteView.as_view()(factory.post(
            '/billing/internal/appointments/quote/',
            {'plan_code': 'appointments', 'billing_cycle': 'monthly'},
            format='json',
        ))
        checkout_response = AppointmentsCheckoutView.as_view()(factory.post(
            '/billing/internal/appointments/checkout/',
            {
                'business_id': 1,
                'plan_code': 'appointments',
                'billing_cycle': 'monthly',
            },
            format='json',
        ))
        self.assertIn(quote_response.status_code, (401, 403))
        self.assertIn(checkout_response.status_code, (401, 403))


class AppointmentsCheckoutWebhookS5Tests(TestCase):
    def setUp(self):
        sdk_constructor = patch('apps.billing.mp_service.MercadoPagoService.__init__', return_value=None)
        sdk_constructor.start()
        self.addCleanup(sdk_constructor.stop)
        self.user = User.objects.create_user(
            username='appointments-owner@test.invalid',
            email='appointments-owner@test.invalid',
            password='test-password',
        )
        self.business = Business.objects.create(
            name='Turnos Checkout Business',
            default_service='gestion',
            service_type='gestion',
        )
        self.legacy = LegacySubscription.objects.create(
            business=self.business,
            plan='start',
            status='active',
        )
        self.quote_request = {
            'plan_code': 'appointments_ai',
            'billing_cycle': 'monthly',
            'usage_tier': 'ai_1500',
            'automations': True,
            'extra_professionals': 2,
        }

    def make_checkout(self, **overrides):
        request = dict(self.quote_request)
        request.update(overrides)
        with patch('apps.billing.mp_service.MercadoPagoService.create_preapproval_plan') as provider:
            provider.return_value = {
                'id': f'plan-{uuid.uuid4()}',
                'sandbox_init_point': 'https://mp.invalid/checkout',
            }
            result = create_appointments_checkout(
                user=self.user,
                business=self.business,
                internal_provisioning=True,
                **request,
            )
        return result, provider

    def make_delivery(self, topic='subscription_preapproval', resource='resource-id'):
        return WebhookDelivery.objects.create(
            topic=topic,
            resource_id=resource,
            received_at=timezone.now(),
        )

    def test_checkout_metadata_and_provider_recurring_amount_match_quote(self):
        result, provider = self.make_checkout()
        checkout = AppointmentsCheckout.objects.get(pk=result['checkout_id'])
        self.assertEqual(checkout.metadata_json['service_type'], 'appointments')
        self.assertEqual(checkout.metadata_json['plan_code'], 'appointments_ai')
        self.assertEqual(checkout.metadata_json['usage_tier'], 'ai_1500')
        self.assertEqual(checkout.metadata_json['billing_cycle'], 'monthly')
        self.assertEqual(checkout.metadata_json['automations'], 'included')
        self.assertEqual(checkout.metadata_json['extra_professionals'], 2)
        self.assertEqual(checkout.metadata_json['business_id'], str(self.business.pk))
        self.assertIn('catalog_version', checkout.metadata_json)
        self.assertIn('line_items', checkout.quote_snapshot)
        self.assertIn('unit_prices', checkout.quote_snapshot)
        self.assertIn('quantities', checkout.quote_snapshot)
        self.assertIn('subtotal', checkout.quote_snapshot)
        self.assertIn('discount_amount', checkout.quote_snapshot)
        self.assertIn('total_amount', checkout.quote_snapshot)
        self.assertIn('currency', checkout.quote_snapshot)
        self.assertIn('catalog_version', checkout.quote_snapshot)
        self.assertIn('created_at', checkout.quote_snapshot)
        recurring = provider.call_args.kwargs['auto_recurring']
        self.assertEqual(recurring['transaction_amount'], checkout.quote_snapshot['total_amount'])
        self.assertEqual(recurring['transaction_amount'], 281000)
        self.assertEqual(recurring['currency_id'], 'ARS')
        self.assertEqual(provider.call_args.kwargs['metadata'], checkout.metadata_json)
        self.assertFalse(Plan.objects.filter(code='appointments_ai').exists())

    def test_same_checkout_retry_reuses_snapshot_without_duplicate_provider_plan(self):
        first, provider = self.make_checkout()
        second, _ = self.make_checkout()
        self.assertFalse(first['reused'])
        self.assertTrue(second['reused'])
        self.assertEqual(first['checkout_id'], second['checkout_id'])
        self.assertEqual(AppointmentsCheckout.objects.count(), 1)
        provider.assert_called_once()

    def test_snapshot_prices_do_not_change_when_catalog_price_changes(self):
        result, _ = self.make_checkout()
        checkout = AppointmentsCheckout.objects.get(pk=result['checkout_id'])
        expected = checkout.quote_snapshot['total_amount']
        with patch('apps.billing.canonical_pricing.usage_tier_price', return_value=999999):
            applied = apply_appointments_preapproval(
                preapproval_id='snapshot-price-preapproval',
                plan_id=checkout.provider_preapproval_plan_id,
                preapproval={
                    'external_reference': checkout.external_reference,
                    'auto_recurring': {
                        'transaction_amount': expected,
                        'currency_id': 'ARS',
                    },
                },
            )
        self.assertTrue(applied)
        checkout.refresh_from_db()
        self.assertEqual(checkout.subscription_v2.price_snapshot['total_amount'], expected)

    def test_annual_provider_frequency_and_amount_match_quote(self):
        _, provider = self.make_checkout(
            plan_code='appointments',
            billing_cycle='yearly',
            usage_tier=None,
            automations=True,
            extra_professionals=2,
        )
        self.assertEqual(
            provider.call_args.kwargs['auto_recurring'],
            {
                'frequency': 12,
                'frequency_type': 'months',
                'transaction_amount': 360000,
                'currency_id': 'ARS',
            },
        )

    def test_custom_tier_does_not_create_provider_checkout(self):
        with patch('apps.billing.mp_service.MercadoPagoService.create_preapproval_plan') as provider:
            with self.assertRaises(ManualContractRequired):
                create_appointments_checkout(
                    user=self.user,
                    business=self.business,
                    internal_provisioning=True,
                    plan_code='appointments_ai',
                    billing_cycle='monthly',
                    usage_tier='custom',
                )
            provider.assert_not_called()

    def test_preapproval_webhook_creates_subscriptionv2_from_persisted_checkout(self):
        result, provider = self.make_checkout()
        checkout = AppointmentsCheckout.objects.get(pk=result['checkout_id'])
        preapproval_id = 'mp-preapproval-s5-1'
        preapproval = {
            'id': preapproval_id,
            'status': 'authorized',
            'preapproval_plan_id': checkout.provider_preapproval_plan_id,
            'external_reference': checkout.external_reference,
            'auto_recurring': {
                'transaction_amount': 281000,
                'currency_id': 'ARS',
            },
        }
        from apps.billing.webhook_processor import _handle_subscription_preapproval

        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_preapproval',
            return_value=preapproval,
        ):
            _handle_subscription_preapproval(preapproval_id, self.make_delivery())

        subscription = SubscriptionV2.objects.get(provider_sub_id=preapproval_id)
        checkout.refresh_from_db()
        self.assertEqual(subscription.service_type, 'appointments')
        self.assertEqual(subscription.plan_code, 'appointments_ai')
        self.assertEqual(subscription.usage_tier, 'ai_1500')
        self.assertEqual(subscription.billing_cycle, 'monthly')
        self.assertEqual(subscription.status, SubscriptionV2.Status.CHECKOUT_PENDING)
        self.assertEqual(subscription.price_snapshot['total_amount'], 281000)
        self.assertEqual(checkout.subscription_v2_id, subscription.pk)
        self.assertEqual(checkout.status, AppointmentsCheckout.Status.LINKED)
        self.assertFalse(SubscriptionAddon.objects.filter(
            subscription_v2=subscription, code='appointments_automations',
        ).exists())
        provider.assert_called_once()

    def test_authorized_webhook_activates_and_persists_addons_and_quantity(self):
        _, provider = self.make_checkout()
        checkout = AppointmentsCheckout.objects.first()
        preapproval_id = 'mp-preapproval-s5-2'
        preapproval = {
            'id': preapproval_id,
            'status': 'authorized',
            'preapproval_plan_id': checkout.provider_preapproval_plan_id,
            'external_reference': checkout.external_reference,
            'auto_recurring': {'transaction_amount': 281000, 'currency_id': 'ARS'},
        }
        from apps.billing.webhook_processor import (
            _handle_authorized_payment,
            _handle_subscription_preapproval,
        )

        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_preapproval',
            return_value=preapproval,
        ):
            _handle_subscription_preapproval(preapproval_id, self.make_delivery())
        with (
            patch(
                'apps.billing.mp_service.MercadoPagoService.get_authorized_payment',
                return_value={
                    'id': 'auth-payment-s5-2',
                    'payment_id': 'payment-s5-2',
                    'status': 'authorized',
                    'preapproval_id': preapproval_id,
                    'transaction_amount': 281000,
                    'currency_id': 'ARS',
                    'date_approved': timezone.now().isoformat(),
                },
            ),
            patch('apps.billing.email_helpers.send_subscription_activated_email'),
            patch('apps.billing.email_helpers.send_admin_subscription_payment_created_email'),
        ):
            _handle_authorized_payment('auth-payment-s5-2', self.make_delivery(
                topic='subscription_authorized_payment',
                resource='auth-payment-s5-2',
            ))

        checkout.refresh_from_db()
        subscription = SubscriptionV2.objects.get(provider_sub_id=preapproval_id)
        self.assertEqual(checkout.status, AppointmentsCheckout.Status.ACTIVE)
        self.assertEqual(subscription.status, SubscriptionV2.Status.ACTIVE)
        self.assertTrue(subscription.is_active)
        self.assertIsNotNone(subscription.current_period_start)
        self.assertIsNotNone(subscription.current_period_end)
        self.assertEqual(subscription.billing_cycle, 'monthly')
        extra = SubscriptionAddon.objects.get(
            subscription_v2=subscription,
            code='appointments_extra_professional',
        )
        self.assertEqual(extra.quantity, 2)
        self.assertFalse(SubscriptionAddon.objects.filter(
            subscription_v2=subscription,
            code='appointments_automations',
        ).exists())
        self.assertEqual(
            LegacySubscription.objects.get(pk=self.legacy.pk).plan,
            'start',
        )

    def test_retry_webhook_does_not_duplicate_subscription_addons_or_quantity(self):
        _, provider = self.make_checkout()
        checkout = AppointmentsCheckout.objects.first()
        preapproval_id = 'mp-preapproval-s5-retry'
        preapproval = {
            'id': preapproval_id,
            'status': 'authorized',
            'preapproval_plan_id': checkout.provider_preapproval_plan_id,
            'external_reference': checkout.external_reference,
            'auto_recurring': {'transaction_amount': 281000, 'currency_id': 'ARS'},
        }
        from apps.billing.webhook_processor import (
            _handle_authorized_payment,
            _handle_subscription_preapproval,
        )

        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_preapproval',
            return_value=preapproval,
        ):
            _handle_subscription_preapproval(preapproval_id, self.make_delivery())
        payment = {
            'id': 'auth-payment-s5-retry',
            'payment_id': 'payment-s5-retry',
            'status': 'authorized',
            'preapproval_id': preapproval_id,
            'transaction_amount': 281000,
            'currency_id': 'ARS',
            'date_approved': timezone.now().isoformat(),
        }
        with (
            patch(
                'apps.billing.mp_service.MercadoPagoService.get_authorized_payment',
                return_value=payment,
            ),
            patch('apps.billing.email_helpers.send_subscription_activated_email'),
            patch('apps.billing.email_helpers.send_admin_subscription_payment_created_email'),
        ):
            _handle_authorized_payment('auth-payment-s5-retry', self.make_delivery(
                topic='subscription_authorized_payment', resource='auth-payment-s5-retry',
            ))
            _handle_authorized_payment('auth-payment-s5-retry', self.make_delivery(
                topic='subscription_authorized_payment', resource='auth-payment-s5-retry',
            ))

        subscription = SubscriptionV2.objects.get(provider_sub_id=preapproval_id)
        self.assertEqual(SubscriptionV2.objects.filter(
            business=self.business, service_type='appointments',
        ).count(), 1)
        self.assertEqual(SubscriptionAddon.objects.filter(subscription_v2=subscription).count(), 1)
        self.assertEqual(SubscriptionAddon.objects.get(
            subscription_v2=subscription, code='appointments_extra_professional',
        ).quantity, 2)
        self.assertEqual(BillingInvoiceEvent.objects.filter(
            provider_authorized_payment_id='auth-payment-s5-retry',
        ).count(), 1)
        self.assertEqual(LegacySubscription.objects.filter(business=self.business).count(), 1)
        provider.assert_called_once()

    def test_preapproval_amount_mismatch_does_not_create_subscription(self):
        result, _ = self.make_checkout()
        checkout = AppointmentsCheckout.objects.get(pk=result['checkout_id'])
        with self.assertRaises(WebhookPermanentError):
            apply_appointments_preapproval(
                preapproval_id='mismatch-preapproval',
                plan_id=checkout.provider_preapproval_plan_id,
                preapproval={
                    'external_reference': checkout.external_reference,
                    'auto_recurring': {'transaction_amount': 1, 'currency_id': 'ARS'},
                },
            )
        self.assertFalse(SubscriptionV2.objects.filter(business=self.business).exists())

    def test_another_product_subscription_is_not_changed_by_turnos_webhook(self):
        result, _ = self.make_checkout()
        checkout = AppointmentsCheckout.objects.get(pk=result['checkout_id'])
        preapproval = {
            'id': 'other-product-check',
            'status': 'authorized',
            'preapproval_plan_id': checkout.provider_preapproval_plan_id,
            'external_reference': checkout.external_reference,
            'auto_recurring': {'transaction_amount': 281000, 'currency_id': 'ARS'},
        }
        from apps.billing.webhook_processor import _handle_subscription_preapproval

        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_preapproval',
            return_value=preapproval,
        ):
            _handle_subscription_preapproval(preapproval['id'], self.make_delivery())
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.plan, 'start')
        self.assertEqual(self.legacy.status, 'active')
        self.assertFalse(SubscriptionV2.objects.filter(
            business=self.business, service_type='gestion',
        ).exists())

    def test_open_checkout_database_constraint_is_enforced(self):
        _, _ = self.make_checkout()
        checkout = AppointmentsCheckout.objects.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppointmentsCheckout.objects.create(
                business=self.business,
                user=self.user,
                external_reference=f'APPT-{uuid.uuid4()}',
                plan_code='appointments',
                billing_cycle='monthly',
                automations='disabled',
                quote_snapshot=checkout.quote_snapshot,
                metadata_json=checkout.metadata_json,
                expires_at=checkout.expires_at,
            )
