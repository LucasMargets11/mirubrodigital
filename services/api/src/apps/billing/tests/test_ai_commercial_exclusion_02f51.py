"""PROD-02F5.1 — Protección transversal de exclusión comercial IA.

One shared rule (billing.services.ai_commercial_rules): Recepcionista ⟂
Turnos IA on every commercial write path — complimentary grants, Turnos
checkout start, preapproval/payment webhooks, reconciliation (via the
central activator), Turnos plan changes and paid upgrades. Financial
records are always preserved; nothing is canceled or refunded.
"""
from __future__ import annotations

import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.appointments.models import AppointmentAIUsageSession
from apps.billing.complimentary_access_service import IncompatibleAIServiceError, grant_complimentary_access
from apps.billing.models import (
    AppointmentsCheckout,
    BillingEvent,
    BillingInvoiceEvent,
    PaymentAttempt,
    PendingSubscriptionChange,
    SubscriptionV2,
    WebhookDelivery,
)
from apps.billing.services.ai_commercial_rules import (
    AIUsagePeriodOverlapConflict,
    IncompatibleAISourceConflict,
)
from apps.billing.services.ai_source import AMBIGUOUS_AI_SOURCE, resolve_ai_source
from apps.billing.services.appointments_checkout import create_appointments_checkout
from apps.billing.services.appointments_lifecycle import (
    apply_appointments_change,
    apply_appointments_renewal,
    request_appointments_change,
)
from apps.billing.subscription_activator import activate_subscription_from_invoice
from apps.billing.views import AppointmentsCheckoutView
from apps.business.models import Business

User = get_user_model()
AI_QUOTE = {'plan_code': 'appointments_ai', 'billing_cycle': 'monthly', 'usage_tier': 'ai_1500',
            'automations': True, 'extra_professionals': 2}
AI_AMOUNT = 281000


class _Base(TestCase):

    def setUp(self):
        sdk = patch('apps.billing.mp_service.MercadoPagoService.__init__', return_value=None)
        sdk.start()
        self.addCleanup(sdk.stop)
        self.now = timezone.now().replace(microsecond=0)
        self.user = User.objects.create_user(username=f'owner-{uuid.uuid4().hex[:8]}')
        self.business = Business.objects.create(
            name='Negocio IA', slug=f'ia-{uuid.uuid4().hex[:8]}', status='active',
            service_type='gestion', default_service='gestion',
        )

    def reception(self, status=SubscriptionV2.Status.TRIALING, **values):
        defaults = dict(
            business=self.business, service_type='reception', plan_code='reception', usage_tier='reception_300',
            provider='manual', external_reference=f'SUB-{uuid.uuid4()}', status=status,
            is_active=status != SubscriptionV2.Status.CANCELED,
            current_period_start=self.now - timedelta(days=5), current_period_end=self.now + timedelta(days=60),
        )
        defaults.update(values)
        return SubscriptionV2.objects.create(**defaults)

    def turnos(self, plan='appointments', usage_tier=None, **values):
        defaults = dict(
            business=self.business, service_type='appointments', plan_code=plan, usage_tier=usage_tier,
            billing_cycle='monthly', provider='manual', external_reference=f'SUB-{uuid.uuid4()}',
            status='active', is_active=True, current_period_start=self.now - timedelta(days=15),
            current_period_end=self.now + timedelta(days=15), price_snapshot={'total_amount': 23000, 'currency': 'ARS'},
        )
        defaults.update(values)
        return SubscriptionV2.objects.create(**defaults)

    def usage(self, subscription, *, period_start, period_end):
        return AppointmentAIUsageSession.objects.create(
            business=self.business, subscription=subscription, external_conversation_id=f'c-{uuid.uuid4().hex[:6]}',
            opening_interaction_id=uuid.uuid4(), started_at=period_start + timedelta(hours=1),
            expires_at=period_start + timedelta(hours=25), usage_period_start=period_start,
            usage_period_end=period_end, usage_tier=subscription.usage_tier or 'ai_300',
        )

    def checkout(self, **overrides):
        with patch('apps.billing.mp_service.MercadoPagoService.create_preapproval_plan') as provider:
            provider.return_value = {'id': f'plan-{uuid.uuid4()}', 'sandbox_init_point': 'https://mp.invalid/c'}
            result = create_appointments_checkout(
                user=self.user, business=self.business, internal_provisioning=True, **{**AI_QUOTE, **overrides},
            )
        return AppointmentsCheckout.objects.get(pk=result['checkout_id']), provider

    def delivery(self, topic, resource):
        return WebhookDelivery.objects.create(topic=topic, resource_id=resource, received_at=timezone.now())

    def preapproval_webhook(self, checkout, preapproval_id, amount=AI_AMOUNT):
        from apps.billing.webhook_processor import _handle_subscription_preapproval

        preapproval = {
            'id': preapproval_id, 'status': 'authorized', 'preapproval_plan_id': checkout.provider_preapproval_plan_id,
            'external_reference': checkout.external_reference,
            'auto_recurring': {'transaction_amount': amount, 'currency_id': 'ARS'},
        }
        delivery = self.delivery('subscription_preapproval', preapproval_id)
        with patch('apps.billing.mp_service.MercadoPagoService.get_preapproval', return_value=preapproval):
            _handle_subscription_preapproval(preapproval_id, delivery)
        return delivery

    def payment_webhook(self, preapproval_id, auth_id, amount=AI_AMOUNT):
        from apps.billing.webhook_processor import _handle_authorized_payment

        delivery = self.delivery('subscription_authorized_payment', auth_id)
        payment = {'id': auth_id, 'payment_id': f'pay-{auth_id}', 'status': 'authorized',
                   'preapproval_id': preapproval_id, 'transaction_amount': amount, 'currency_id': 'ARS',
                   'date_approved': timezone.now().isoformat()}
        with patch('apps.billing.mp_service.MercadoPagoService.get_authorized_payment', return_value=payment), \
                patch('apps.billing.email_helpers.send_subscription_activated_email'), \
                patch('apps.billing.email_helpers.send_admin_subscription_payment_created_email'):
            _handle_authorized_payment(auth_id, delivery)
        delivery.refresh_from_db()
        return delivery


class CheckoutStartTests(_Base):

    def test_turnos_ia_checkout_is_blocked_before_any_provider_call(self):
        self.reception()
        with patch('apps.billing.mp_service.MercadoPagoService.create_preapproval_plan') as provider, \
                self.assertRaises(IncompatibleAISourceConflict):
            create_appointments_checkout(user=self.user, business=self.business, internal_provisioning=True, **AI_QUOTE)
        provider.assert_not_called()
        self.assertFalse(AppointmentsCheckout.objects.exists())

    def test_internal_checkout_endpoint_answers_the_conflict_code(self):
        self.reception()
        staff = User.objects.create_user(username=f'staff-{uuid.uuid4().hex[:6]}', is_staff=True)
        request = APIRequestFactory().post('/billing/internal/appointments/checkout/',
                                           {'business_id': self.business.pk, **AI_QUOTE}, format='json')
        force_authenticate(request, user=staff)
        with patch('apps.billing.mp_service.MercadoPagoService.create_preapproval_plan') as provider:
            response = AppointmentsCheckoutView.as_view()(request)
        self.assertEqual((response.status_code, response.data['code']), (409, 'incompatible_ai_service'))
        provider.assert_not_called()

    def test_turnos_base_and_pro_checkouts_stay_compatible_with_reception(self):
        self.reception()
        for plan in ('appointments', 'appointments_pro'):
            with self.subTest(plan=plan):
                AppointmentsCheckout.objects.all().delete()
                checkout, provider = self.checkout(plan_code=plan, usage_tier=None)
                self.assertEqual(checkout.plan_code, plan)
                provider.assert_called_once()

    def test_canceled_reception_with_running_usage_blocks_a_new_turnos_ia(self):
        old = self.reception(status=SubscriptionV2.Status.CANCELED)
        self.usage(old, period_start=self.now - timedelta(days=5), period_end=self.now + timedelta(days=25))
        with self.assertRaises(AIUsagePeriodOverlapConflict):
            self.checkout()
        self.assertFalse(AppointmentsCheckout.objects.exists())

    def test_canceled_reception_without_usage_does_not_block(self):
        self.reception(status=SubscriptionV2.Status.CANCELED)
        checkout, _ = self.checkout()
        self.assertEqual(checkout.plan_code, 'appointments_ai')


class WebhookTests(_Base):

    def test_preapproval_for_an_incompatible_checkout_opens_no_subscription(self):
        checkout, _ = self.checkout()
        reception = self.reception()  # granted while the checkout was open
        delivery = self.preapproval_webhook(checkout, 'pre-1')
        checkout.refresh_from_db()
        self.assertFalse(SubscriptionV2.objects.filter(provider_sub_id='pre-1').exists())
        self.assertEqual((checkout.status, checkout.failure_code, checkout.provider_preapproval_id),
                         (AppointmentsCheckout.Status.FAILED, 'incompatible_ai_service', 'pre-1'))
        # The payment that follows is recorded, never activated, never refunded
        delivery = self.payment_webhook('pre-1', 'auth-1')
        invoice = BillingInvoiceEvent.objects.get(provider_authorized_payment_id='auth-1')
        self.assertEqual((invoice.provider_status, invoice.amount, invoice.subscription_id),
                         ('authorized', Decimal(AI_AMOUNT), None))
        checkout.refresh_from_db()
        self.assertEqual(checkout.failure_code, 'incompatible_ai_service')
        self.assertFalse(SubscriptionV2.objects.filter(plan_code='appointments_ai').exists())
        reception.refresh_from_db()
        self.assertEqual((reception.status, reception.is_active), ('trialing', True))

    def test_paid_checkout_whose_reception_appeared_later_is_held_with_records_intact(self):
        checkout, _ = self.checkout()
        self.preapproval_webhook(checkout, 'pre-2')
        pending = SubscriptionV2.objects.get(provider_sub_id='pre-2')
        self.assertEqual(pending.status, SubscriptionV2.Status.CHECKOUT_PENDING)
        self.reception()  # race: Recepcionista granted before the payment arrives
        self.payment_webhook('pre-2', 'auth-2')
        pending.refresh_from_db()
        checkout.refresh_from_db()
        self.assertEqual((pending.status, pending.is_active), (SubscriptionV2.Status.CHECKOUT_PENDING, False))
        self.assertEqual((checkout.status, checkout.failure_code),
                         (AppointmentsCheckout.Status.FAILED, 'incompatible_ai_service'))
        invoice = BillingInvoiceEvent.objects.get(provider_authorized_payment_id='auth-2')
        self.assertEqual((invoice.provider_status, invoice.subscription_id), ('authorized', pending.pk))
        self.assertNotEqual(resolve_ai_source(self.business).reason, AMBIGUOUS_AI_SOURCE)

    def test_generic_activation_path_is_blocked_and_noted_on_the_delivery(self):
        self.reception()
        generic = SubscriptionV2.objects.create(
            business=self.business, service_type='appointments', plan_code='appointments_ai', usage_tier='ai_300',
            provider='mercadopago', provider_sub_id='pre-g', external_reference=f'SUB-{uuid.uuid4()}',
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )
        delivery = self.payment_webhook('pre-g', 'auth-g')
        generic.refresh_from_db()
        self.assertFalse(generic.is_active)
        self.assertIn('incompatible_ai_service', delivery.error_message)
        self.assertIn('manual review', delivery.error_message)
        self.assertTrue(BillingInvoiceEvent.objects.filter(provider_authorized_payment_id='auth-g',
                                                           subscription=generic).exists())

    def test_reconciliation_reports_and_never_activates(self):
        from apps.billing.reconciliation import reconcile_subscription

        self.reception()
        generic = SubscriptionV2.objects.create(
            business=self.business, service_type='appointments', plan_code='appointments_ai', usage_tier='ai_300',
            provider='mercadopago', provider_sub_id='pre-r', external_reference=f'SUB-{uuid.uuid4()}',
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )
        BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id='auth-r', provider_subscription_id='pre-r', provider_status='authorized',
            amount=Decimal('61000'), currency='ARS', paid_at=self.now,
        )
        with patch('apps.billing.mp_service.MercadoPagoService.get_preapproval',
                   return_value={'id': 'pre-r', 'status': 'authorized', 'preapproval_plan_id': ''}):
            result = reconcile_subscription('pre-r')
        generic.refresh_from_db()
        self.assertFalse(generic.is_active)
        self.assertIn('incompatible_ai_service', result['error'])
        self.assertTrue(BillingInvoiceEvent.objects.filter(provider_authorized_payment_id='auth-r').exists())

    def test_compatible_turnos_pro_payment_still_activates_next_to_reception(self):
        self.reception()
        checkout, _ = self.checkout(plan_code='appointments_pro', usage_tier=None, automations=False,
                                    extra_professionals=0)
        amount = checkout.quote_snapshot['total_amount']
        self.preapproval_webhook(checkout, 'pre-p', amount=amount)
        sub = SubscriptionV2.objects.get(provider_sub_id='pre-p')
        self.assertEqual(sub.plan_code, 'appointments_pro')
        self.payment_webhook('pre-p', 'auth-p', amount=amount)
        sub.refresh_from_db()
        self.assertTrue(sub.is_active)


class LifecycleTests(_Base):

    def test_base_or_pro_to_ai_change_is_rejected_while_reception_lives(self):
        self.reception()
        for plan in ('appointments', 'appointments_pro'):
            with self.subTest(plan=plan):
                SubscriptionV2.objects.filter(service_type='appointments').delete()
                self.turnos(plan=plan)
                with self.assertRaises(IncompatibleAISourceConflict):
                    request_appointments_change(business=self.business, user=self.user,
                                                target={'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'},
                                                at=self.now)
                self.assertFalse(PendingSubscriptionChange.objects.exists())

    def test_base_to_pro_change_is_unaffected(self):
        self.reception()
        self.turnos()
        pending, _ = request_appointments_change(business=self.business, user=self.user,
                                                 target={'plan_code': 'appointments_pro'}, at=self.now)
        self.assertTrue(apply_appointments_change(pending, payment_id='pay-pro', at=self.now))

    def test_pending_change_is_held_when_reception_appears_before_it_applies(self):
        sub = self.turnos(plan='appointments_pro')
        pending, _ = request_appointments_change(business=self.business, user=self.user,
                                                 target={'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'},
                                                 at=self.now)
        reception = self.reception()
        self.assertFalse(apply_appointments_change(pending, payment_id='pay-ai', at=self.now))
        pending.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual((pending.status, pending.requires_resolution), ('blocked', True))
        self.assertEqual(pending.resolution_details, {'code': 'incompatible_ai_service',
                                                      'conflicting_subscription_id': str(reception.pk)})
        self.assertEqual(sub.plan_code, 'appointments_pro')

    def test_paid_upgrade_is_held_with_payment_recorded_and_mp_untouched(self):
        from apps.billing.payment_webhook import _apply_billing_payment

        sub = self.turnos(plan='appointments_pro', provider='mercadopago', provider_sub_id='pre-up')
        pending, _ = request_appointments_change(business=self.business, user=self.user,
                                                 target={'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'},
                                                 at=self.now)
        self.reception()
        billing_event = BillingEvent.objects.create(
            business=self.business, provider='mercadopago', provider_event_id=f'evt-{uuid.uuid4()}',
            payload={'id': 'pay-up'}, received_at=self.now,
        )
        payment = {'id': 'pay-up', 'status': 'approved', 'transaction_amount': float(pending.total_amount),
                   'currency_id': 'ARS', 'external_reference': f'subscription_change_{pending.pk}'}
        with patch('apps.billing.mp_service.MercadoPagoService.update_preapproval') as update:
            _apply_billing_payment(pending_change=pending, payment_data=payment, payment_id='pay-up',
                                   billing_event=billing_event, is_addon_purchase=False, is_reviews_upgrade=False,
                                   is_appointments_change=True)
        update.assert_not_called()
        pending.refresh_from_db()
        sub.refresh_from_db()
        billing_event.refresh_from_db()
        self.assertEqual((pending.status, pending.mp_payment_id), ('blocked', 'pay-up'))
        self.assertEqual(sub.plan_code, 'appointments_pro')
        self.assertEqual(billing_event.status, BillingEvent.ProcessingStatus.ERROR)
        self.assertTrue(PaymentAttempt.objects.filter(subscription=sub, external_payment_id='pay-up').exists())


class RenewalAndContinuityTests(_Base):

    def test_renewal_of_the_same_ai_subscription_is_never_blocked_by_its_own_usage(self):
        sub = self.turnos(plan='appointments_ai', usage_tier='ai_300')
        self.usage(sub, period_start=sub.current_period_start, period_end=sub.current_period_end)
        event = BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=f'auth-{uuid.uuid4()}', provider_status='authorized',
            paid_at=sub.current_period_end, amount=Decimal('23000'), currency='ARS',
        )
        self.assertTrue(apply_appointments_renewal(subscription=sub, invoice_event=event))
        # Recovery of the same subscription from past_due is not re-gated by usage either
        SubscriptionV2.objects.filter(pk=sub.pk).update(status='past_due', is_active=False)
        sub.refresh_from_db()
        self.assertTrue(activate_subscription_from_invoice(invoice_event=event, subscription=sub))

    def test_ai_tier_change_within_turnos_ia_is_not_a_new_source(self):
        sub = self.turnos(plan='appointments_ai', usage_tier='ai_1500')
        self.usage(sub, period_start=sub.current_period_start, period_end=sub.current_period_end)
        pending, _ = request_appointments_change(business=self.business, user=self.user,
                                                 target={'usage_tier': 'ai_3000'}, at=self.now)
        self.assertTrue(apply_appointments_change(pending, payment_id='pay-tier', at=self.now))


class InFlightPurchaseTests(_Base):
    """An open Turnos IA purchase blocks a new Recepcionista grant (no paid conflict later)."""

    def _grant_reception(self):
        call_command('seed_reception_catalog', stdout=StringIO())
        admin = User.objects.create_user(username=f'adm-{uuid.uuid4().hex[:6]}')
        return grant_complimentary_access(
            business=self.business, plan_code='reception', service_type='reception', starts_at=self.now,
            ends_at=self.now + timedelta(days=30), granted_by=admin, reason='x', usage_tier='reception_300',
        )

    def test_open_turnos_ia_checkout_blocks_reception(self):
        checkout, _ = self.checkout()
        with self.assertRaises(IncompatibleAIServiceError):
            self._grant_reception()
        # Once that checkout is closed (expired/failed) Recepcionista is allowed again
        AppointmentsCheckout.objects.filter(pk=checkout.pk).update(status='failed')
        self.assertEqual(self._grant_reception().plan_code, 'reception')

    def test_stale_pending_checkout_does_not_block(self):
        checkout, _ = self.checkout()
        AppointmentsCheckout.objects.filter(pk=checkout.pk).update(expires_at=self.now - timedelta(minutes=1))
        self.assertEqual(self._grant_reception().plan_code, 'reception')

    def test_pending_change_to_turnos_ia_blocks_reception(self):
        self.turnos(plan='appointments_pro')
        request_appointments_change(business=self.business, user=self.user,
                                    target={'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'}, at=self.now)
        with self.assertRaises(IncompatibleAIServiceError):
            self._grant_reception()

    def test_turnos_base_checkout_does_not_block_reception(self):
        self.checkout(plan_code='appointments', usage_tier=None)
        self.assertEqual(self._grant_reception().plan_code, 'reception')


class SharedRuleTests(_Base):

    def test_grant_keeps_its_taxonomy_through_the_shared_rule(self):
        call_command('seed_reception_catalog', stdout=StringIO())
        admin = User.objects.create_user(username=f'adm-{uuid.uuid4().hex[:6]}')
        self.turnos(plan='appointments_ai', usage_tier='ai_300')
        with self.assertRaises(IncompatibleAIServiceError):
            grant_complimentary_access(
                business=self.business, plan_code='reception', service_type='reception',
                starts_at=self.now, ends_at=self.now + timedelta(days=30), granted_by=admin,
                reason='x', usage_tier='reception_300',
            )

    def test_rule_refuses_to_run_outside_a_transaction(self):
        from apps.billing.services import ai_commercial_rules

        with patch.object(ai_commercial_rules.connection, 'in_atomic_block', False), self.assertRaises(RuntimeError):
            ai_commercial_rules.find_ai_commercial_conflict(
                business_id=self.business.pk, service_type='reception', plan_code='reception', starts_at=self.now,
            )

    def test_resolver_stays_fail_closed_for_legacy_coexistence(self):
        # Rows written before this guard (or by hand) never become a usable AI source
        self.reception()
        self.turnos(plan='appointments_ai', usage_tier='ai_300')
        self.assertEqual(resolve_ai_source(self.business).reason, AMBIGUOUS_AI_SOURCE)
        self.assertIsNone(resolve_ai_source(self.business).subscription)


class CrossPathConcurrencyTests(TransactionTestCase):
    """Different paths racing for the same Business serialize on its row."""

    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        call_command('seed_reception_catalog', stdout=StringIO())
        self.now = timezone.now().replace(microsecond=0)
        self.admin = User.objects.create_user(username=f'adm-{uuid.uuid4().hex[:6]}')
        self.user = User.objects.create_user(username=f'own-{uuid.uuid4().hex[:6]}')
        self.business = Business.objects.create(name='Carrera', slug=f'car-{uuid.uuid4().hex[:8]}', status='active',
                                                service_type='gestion', default_service='gestion')

    def _race(self, *calls):
        barrier = threading.Barrier(len(calls))
        outcomes = []

        def worker(name, fn):
            try:
                barrier.wait(timeout=10)
                try:
                    fn()
                    outcomes.append((name, 'ok'))
                except (IncompatibleAIServiceError, IncompatibleAISourceConflict):
                    outcomes.append((name, 'conflict'))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=call) for call in calls]
        sdk = patch('apps.billing.mp_service.MercadoPagoService.__init__', return_value=None)
        provider = patch('apps.billing.mp_service.MercadoPagoService.create_preapproval_plan',
                         return_value={'id': f'plan-{uuid.uuid4()}', 'sandbox_init_point': 'https://mp.invalid/c'})
        with sdk, provider:
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
        return sorted(o[1] for o in outcomes)

    def _grant_reception(self):
        grant_complimentary_access(
            business=self.business, plan_code='reception', service_type='reception', starts_at=self.now,
            ends_at=self.now + timedelta(days=30), granted_by=self.admin, reason='carrera',
            usage_tier='reception_300',
        )

    def test_reception_grant_vs_turnos_ia_checkout(self):
        def checkout():
            create_appointments_checkout(user=self.user, business=self.business, internal_provisioning=True,
                                         **AI_QUOTE)

        self.assertEqual(self._race(('grant', self._grant_reception), ('checkout', checkout)), ['conflict', 'ok'])
        live_reception = SubscriptionV2.objects.filter(business=self.business, service_type='reception').exists()
        open_checkout = AppointmentsCheckout.objects.filter(business=self.business).exists()
        self.assertNotEqual(live_reception, open_checkout)

    def test_reception_grant_vs_turnos_plan_change_to_ai(self):
        SubscriptionV2.objects.create(
            business=self.business, service_type='appointments', plan_code='appointments_pro', billing_cycle='monthly',
            provider='manual', external_reference=f'SUB-{uuid.uuid4()}', status='active', is_active=True,
            current_period_start=self.now - timedelta(days=10), current_period_end=self.now + timedelta(days=20),
            price_snapshot={'total_amount': 28000, 'currency': 'ARS'},
        )

        def change():
            from django.db import transaction

            with transaction.atomic():
                request_appointments_change(business=self.business, user=self.user,
                                            target={'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'})

        self.assertEqual(self._race(('grant', self._grant_reception), ('change', change)), ['conflict', 'ok'])
        live_reception = SubscriptionV2.objects.filter(business=self.business, service_type='reception').exists()
        self.assertNotEqual(live_reception, PendingSubscriptionChange.objects.exists())
