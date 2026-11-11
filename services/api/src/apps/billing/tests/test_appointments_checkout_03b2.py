import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.db.models import Q
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Membership
from apps.billing.models import (
    AppointmentsCheckout,
    BillingInvoiceEvent,
    SubscriptionV2,
    WebhookDelivery,
)
from apps.billing.services.appointments_checkout import (
    APPOINTMENTS_CHECKOUT_TTL,
    create_appointments_checkout,
    expire_stale_appointments_checkouts,
    quote_appointments,
)
from apps.billing.views import PublicAppointmentsCheckoutStatusView
from apps.business.models import Business, Subscription as LegacySubscription, SubscriptionAddon

User = get_user_model()


class AppointmentsCheckoutStatus03B2Tests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(
            username='turnos-status-owner@test.invalid',
            email='turnos-status-owner@test.invalid',
            password='test-password',
        )
        self.business = Business.objects.create(name='Turnos status owner')
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role='owner',
            status=Membership.Status.ACTIVE,
        )
        self.checkout = self.make_checkout()

    def make_checkout(self, *, status=AppointmentsCheckout.Status.PENDING, expires_at=None):
        quote = quote_appointments(
            plan_code='appointments',
            billing_cycle='monthly',
            automations=True,
            extra_professionals=1,
        )
        return AppointmentsCheckout.objects.create(
            business=self.business,
            user=self.owner,
            external_reference=f'APPT-{uuid.uuid4()}',
            provider_preapproval_plan_id=f'plan-{uuid.uuid4()}',
            plan_code='appointments',
            billing_cycle='monthly',
            automations='enabled',
            extra_professional_quantity=1,
            quote_snapshot=quote,
            metadata_json={
                'service_type': 'appointments',
                'plan_code': 'appointments',
                'usage_tier': None,
                'billing_cycle': 'monthly',
                'automations': 'enabled',
                'extra_professionals': 1,
                'business_id': str(self.business.pk),
                'quote_version': quote['quote_version'],
                'catalog_version': quote['catalog_version'],
            },
            status=status,
            expires_at=expires_at or timezone.now() + APPOINTMENTS_CHECKOUT_TTL,
        )

    def get_status(self, checkout_id, *, user=None):
        request = self.factory.get(
            f'/api/v1/billing/appointments/checkouts/{checkout_id}/status/',
        )
        if user is not None:
            force_authenticate(request, user=user)
        return PublicAppointmentsCheckoutStatusView.as_view()(
            request,
            checkout_id=checkout_id,
        )

    def test_owner_sees_only_public_fields_for_own_checkout(self):
        response = self.get_status(self.checkout.pk, user=self.owner)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['checkout_id'], str(self.checkout.pk))
        self.assertNotIn('business_id', response.data)
        self.assertNotIn('provider_checkout_url', response.data)
        self.assertNotIn('metadata_json', response.data)

    def test_anonymous_and_other_tenant_cannot_observe_checkout(self):
        anonymous = self.get_status(self.checkout.pk)
        other_owner = User.objects.create_user(
            username='turnos-status-other@test.invalid',
            email='turnos-status-other@test.invalid',
        )
        other_business = Business.objects.create(name='Other Turnos business')
        Membership.objects.create(
            user=other_owner,
            business=other_business,
            role='owner',
            status=Membership.Status.ACTIVE,
        )
        foreign = self.get_status(self.checkout.pk, user=other_owner)

        self.assertIn(anonymous.status_code, (401, 403))
        self.assertEqual(foreign.status_code, 404)

    def test_status_reports_linked_active_failed_and_expired_states(self):
        self.checkout.status = AppointmentsCheckout.Status.LINKED
        self.checkout.save(update_fields=['status', 'updated_at'])
        linked = self.get_status(self.checkout.pk, user=self.owner)
        self.assertEqual(linked.data['status'], 'linked')

        self.checkout.status = AppointmentsCheckout.Status.FAILED
        self.checkout.failure_code = 'payment_failed'
        self.checkout.save(update_fields=['status', 'failure_code', 'updated_at'])
        failed = self.get_status(self.checkout.pk, user=self.owner)
        self.assertEqual(failed.data['status'], 'failed')
        self.assertFalse(failed.data['can_retry'])

        self.checkout.status = AppointmentsCheckout.Status.PENDING
        self.checkout.expires_at = timezone.now() - APPOINTMENTS_CHECKOUT_TTL
        self.checkout.save(update_fields=['status', 'expires_at', 'updated_at'])
        expired = self.get_status(self.checkout.pk, user=self.owner)
        self.assertEqual(expired.data['status'], 'expired')
        self.assertEqual(expired.data['failure_code'], 'checkout_expired')
        self.assertFalse(expired.data['can_retry'])


class AppointmentsCheckoutWebhook03B2Tests(TestCase):
    def setUp(self):
        self.sdk_constructor = patch(
            'apps.billing.mp_service.MercadoPagoService.__init__',
            return_value=None,
        )
        self.sdk_constructor.start()
        self.addCleanup(self.sdk_constructor.stop)
        self.owner = User.objects.create_user(
            username='turnos-recovery-owner@test.invalid',
            email='turnos-recovery-owner@test.invalid',
            password='test-password',
        )
        self.business = Business.objects.create(name='Turnos recovery business')
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role='owner',
            status=Membership.Status.ACTIVE,
        )
        self.quote_request = {
            'plan_code': 'appointments',
            'billing_cycle': 'monthly',
            'automations': True,
            'extra_professionals': 2,
        }
        self.provider_plan = patch(
            'apps.billing.mp_service.MercadoPagoService.create_preapproval_plan',
            side_effect=lambda **kwargs: {
                'id': f'plan-{uuid.uuid4()}',
                'sandbox_init_point': 'https://mp.invalid/checkout',
            },
        )
        self.create_plan = self.provider_plan.start()
        self.addCleanup(self.provider_plan.stop)

    def make_checkout(self):
        result = create_appointments_checkout(
            user=self.owner,
            business=self.business,
            internal_provisioning=True,
            **self.quote_request,
        )
        return AppointmentsCheckout.objects.get(pk=result['checkout_id'])

    def preapproval(self, checkout, *, subscription_id):
        return {
            'id': subscription_id,
            'status': 'authorized',
            'preapproval_plan_id': checkout.provider_preapproval_plan_id,
            'external_reference': checkout.external_reference,
            'auto_recurring': {
                'transaction_amount': checkout.quote_snapshot['total_amount'],
                'currency_id': checkout.quote_snapshot['currency'],
            },
        }

    def payment(self, checkout, *, subscription_id, payment_id):
        return {
            'id': payment_id,
            'payment_id': f'provider-{payment_id}',
            'status': 'authorized',
            'preapproval_id': subscription_id,
            'transaction_amount': checkout.quote_snapshot['total_amount'],
            'currency_id': checkout.quote_snapshot['currency'],
            'date_approved': timezone.now().isoformat(),
        }

    def delivery(self, topic, resource):
        return WebhookDelivery.objects.create(
            topic=topic,
            resource_id=resource,
            received_at=timezone.now(),
        )

    def send_preapproval(self, checkout, subscription_id):
        from apps.billing.webhook_processor import _handle_subscription_preapproval

        data = self.preapproval(checkout, subscription_id=subscription_id)
        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_preapproval',
            return_value=data,
        ):
            _handle_subscription_preapproval(
                subscription_id,
                self.delivery('subscription_preapproval', subscription_id),
            )

    def send_payment(self, checkout, subscription_id, payment_id):
        from apps.billing.webhook_processor import _handle_authorized_payment

        data = self.payment(
            checkout,
            subscription_id=subscription_id,
            payment_id=payment_id,
        )
        with (
            patch(
                'apps.billing.mp_service.MercadoPagoService.get_authorized_payment',
                return_value=data,
            ),
            patch('apps.billing.email_helpers.send_subscription_activated_email'),
            patch('apps.billing.email_helpers.send_admin_subscription_payment_created_email'),
        ):
            _handle_authorized_payment(
                payment_id,
                self.delivery('subscription_authorized_payment', payment_id),
            )

    def test_reconciliation_of_preapproval_recovers_orphan_invoice(self):
        checkout = self.make_checkout()
        subscription_id = f'sub-{uuid.uuid4()}'
        payment_id = f'auth-{uuid.uuid4()}'
        payment_data = self.payment(
            checkout,
            subscription_id=subscription_id,
            payment_id=payment_id,
        )
        BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=payment_id,
            provider_payment_id=payment_data['payment_id'],
            provider_subscription_id=subscription_id,
            amount=payment_data['transaction_amount'],
            currency=payment_data['currency_id'],
            provider_status='authorized',
            paid_at=timezone.now(),
            raw_payload_json=payment_data,
        )

        from apps.billing.reconciliation import reconcile_subscription

        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_preapproval',
            return_value=self.preapproval(checkout, subscription_id=subscription_id),
        ):
            result = reconcile_subscription(subscription_id)

        checkout.refresh_from_db()
        self.assertIsNone(result['error'])
        self.assertEqual(checkout.status, AppointmentsCheckout.Status.ACTIVE)

    def test_reconciliation_of_authorized_invoice_uses_turnos_finalizer(self):
        checkout = self.make_checkout()
        subscription_id = f'sub-{uuid.uuid4()}'
        payment_id = f'auth-{uuid.uuid4()}'
        self.send_preapproval(checkout, subscription_id)

        from apps.billing.reconciliation import reconcile_invoice_event

        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_authorized_payment',
            return_value=self.payment(
                checkout,
                subscription_id=subscription_id,
                payment_id=payment_id,
            ),
        ):
            result = reconcile_invoice_event(payment_id)

        checkout.refresh_from_db()
        self.assertIsNone(result['error'])
        self.assertEqual(checkout.status, AppointmentsCheckout.Status.ACTIVE)

    def test_rejected_initial_payment_marks_checkout_failed_and_releases_retry_slot(self):
        checkout = self.make_checkout()
        subscription_id = f'sub-{uuid.uuid4()}'
        self.send_preapproval(checkout, subscription_id)
        payment_id = f'auth-{uuid.uuid4()}'
        payment_data = {
            **self.payment(
                checkout,
                subscription_id=subscription_id,
                payment_id=payment_id,
            ),
            'status': 'rejected',
            'status_detail': 'cc_rejected',
        }

        from apps.billing.webhook_processor import _handle_authorized_payment

        with patch(
            'apps.billing.mp_service.MercadoPagoService.get_authorized_payment',
            return_value=payment_data,
        ):
            _handle_authorized_payment(
                payment_id,
                self.delivery('subscription_authorized_payment', payment_id),
            )

        checkout.refresh_from_db()
        subscription = SubscriptionV2.objects.get(provider_sub_id=subscription_id)
        self.assertEqual(checkout.status, AppointmentsCheckout.Status.FAILED)
        self.assertEqual(checkout.failure_code, 'payment_failed')
        self.assertEqual(subscription.status, SubscriptionV2.Status.CANCELED)

    def test_payment_before_preapproval_is_recovered_and_applies_addons_once(self):
        checkout = self.make_checkout()
        subscription_id = f'sub-{uuid.uuid4()}'
        payment_id = f'auth-{uuid.uuid4()}'

        self.send_payment(checkout, subscription_id, payment_id)
        self.assertFalse(SubscriptionV2.objects.filter(provider_sub_id=subscription_id).exists())
        orphan = BillingInvoiceEvent.objects.get(provider_authorized_payment_id=payment_id)
        self.assertIsNone(orphan.subscription_id)

        self.send_preapproval(checkout, subscription_id)
        self.send_preapproval(checkout, subscription_id)

        checkout.refresh_from_db()
        subscription = SubscriptionV2.objects.get(provider_sub_id=subscription_id)
        self.assertEqual(checkout.status, AppointmentsCheckout.Status.ACTIVE)
        self.assertEqual(subscription.status, SubscriptionV2.Status.ACTIVE)
        self.assertEqual(
            SubscriptionAddon.objects.filter(
                subscription_v2=subscription,
                code='appointments_extra_professional',
            ).count(),
            1,
        )
        request = APIRequestFactory().get(
            f'/api/v1/billing/appointments/checkouts/{checkout.pk}/status/',
        )
        force_authenticate(request, user=self.owner)
        response = PublicAppointmentsCheckoutStatusView.as_view()(
            request,
            checkout_id=checkout.pk,
        )
        self.assertEqual(response.data['status'], 'active')
        self.assertEqual(
            SubscriptionAddon.objects.get(
                subscription_v2=subscription,
                code='appointments_extra_professional',
            ).quantity,
            2,
        )
        self.assertEqual(
            SubscriptionAddon.objects.filter(
                subscription_v2=subscription,
                code='appointments_automations',
                is_active=True,
            ).count(),
            1,
        )

    def test_duplicate_payment_and_recovery_after_normal_webhook_are_idempotent(self):
        checkout = self.make_checkout()
        subscription_id = f'sub-{uuid.uuid4()}'
        payment_id = f'auth-{uuid.uuid4()}'
        self.send_preapproval(checkout, subscription_id)
        self.send_payment(checkout, subscription_id, payment_id)
        self.send_payment(checkout, subscription_id, payment_id)
        self.send_preapproval(checkout, subscription_id)

        self.assertEqual(BillingInvoiceEvent.objects.filter(
            provider_authorized_payment_id=payment_id,
        ).count(), 1)
        self.assertEqual(SubscriptionV2.objects.filter(
            business=self.business,
            service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
            is_active=True,
        ).count(), 1)

    def test_expiration_releases_slot_and_retry_does_not_reuse_old_checkout(self):
        first = self.make_checkout()
        self.send_preapproval(first, f'sub-{uuid.uuid4()}')
        first.expires_at = timezone.now() - APPOINTMENTS_CHECKOUT_TTL
        first.save(update_fields=['expires_at', 'updated_at'])
        self.assertEqual(expire_stale_appointments_checkouts(business=self.business), 1)

        second = self.make_checkout()

        first.refresh_from_db()
        self.assertEqual(first.status, AppointmentsCheckout.Status.EXPIRED)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(AppointmentsCheckout.objects.count(), 2)

    def test_late_payment_supersedes_unpaid_retry_and_activates_expired_checkout(self):
        first = self.make_checkout()
        first_subscription_id = f'sub-{uuid.uuid4()}'
        self.send_preapproval(first, first_subscription_id)
        first.expires_at = timezone.now() - APPOINTMENTS_CHECKOUT_TTL
        first.save(update_fields=['expires_at', 'updated_at'])
        expire_stale_appointments_checkouts(business=self.business)

        retry = self.make_checkout()
        retry_subscription_id = f'sub-{uuid.uuid4()}'
        self.send_preapproval(retry, retry_subscription_id)
        self.send_payment(first, first_subscription_id, f'auth-{uuid.uuid4()}')

        first.refresh_from_db()
        retry.refresh_from_db()
        self.assertEqual(first.status, AppointmentsCheckout.Status.ACTIVE)
        self.assertEqual(retry.status, AppointmentsCheckout.Status.FAILED)
        self.assertEqual(retry.failure_code, 'superseded_by_paid_checkout')
        self.assertEqual(
            SubscriptionV2.objects.filter(
                business=self.business,
                service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
                is_active=True,
            ).count(),
            1,
        )

    def test_two_authorized_checkouts_are_flagged_without_second_activation(self):
        first = self.make_checkout()
        first_subscription_id = f'sub-{uuid.uuid4()}'
        self.send_preapproval(first, first_subscription_id)
        first.expires_at = timezone.now() - APPOINTMENTS_CHECKOUT_TTL
        first.save(update_fields=['expires_at', 'updated_at'])
        expire_stale_appointments_checkouts(business=self.business)

        retry = self.make_checkout()
        retry_subscription_id = f'sub-{uuid.uuid4()}'
        self.send_preapproval(retry, retry_subscription_id)
        self.send_payment(retry, retry_subscription_id, f'auth-{uuid.uuid4()}')
        self.send_payment(first, first_subscription_id, f'auth-{uuid.uuid4()}')

        first.refresh_from_db()
        retry.refresh_from_db()
        self.assertEqual(first.failure_code, 'multiple_authorized_payments')
        self.assertEqual(retry.failure_code, 'multiple_authorized_payments')
        self.assertEqual(retry.status, AppointmentsCheckout.Status.ACTIVE)
        self.assertEqual(
            SubscriptionV2.objects.filter(
                business=self.business,
                service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
                is_active=True,
            ).count(),
            1,
        )

    def test_provider_plan_creation_is_mocked_and_no_real_provider_calls_occur(self):
        checkout = self.make_checkout()

        self.assertEqual(self.create_plan.call_count, 1)
        self.assertTrue(checkout.provider_checkout_url.startswith('https://mp.invalid/'))


class AppointmentsCheckoutConcurrency03B2Tests(TransactionTestCase):
    def setUp(self):
        self.sdk_constructor = patch(
            'apps.billing.mp_service.MercadoPagoService.__init__',
            return_value=None,
        )
        self.sdk_constructor.start()
        self.addCleanup(self.sdk_constructor.stop)
        self.owner = User.objects.create_user(
            username='turnos-concurrent-owner@test.invalid',
            email='turnos-concurrent-owner@test.invalid',
        )
        self.business = Business.objects.create(name='Turnos concurrency business')
        self._resource_ids = []
        self.quote_request = {
            'plan_code': 'appointments',
            'billing_cycle': 'monthly',
            'automations': True,
            'extra_professionals': 1,
        }

    def test_simultaneous_identical_checkout_requests_create_one_provider_plan(self):
        barrier = Barrier(2)
        provider_call = patch(
            'apps.billing.mp_service.MercadoPagoService.create_preapproval_plan',
            return_value={
                'id': f'plan-{uuid.uuid4()}',
                'sandbox_init_point': 'https://mp.invalid/checkout',
            },
        )
        create_plan = provider_call.start()
        self.addCleanup(provider_call.stop)

        def create_checkout():
            connections.close_all()
            try:
                barrier.wait(timeout=5)
                return create_appointments_checkout(
                    user=self.owner,
                    business=self.business,
                    internal_provisioning=True,
                    **self.quote_request,
                )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create_checkout(), range(2)))

        self.assertEqual({result['checkout_id'] for result in results}, {
            results[0]['checkout_id'],
        })
        self.assertEqual(AppointmentsCheckout.objects.filter(business=self.business).count(), 1)
        create_plan.assert_called_once()

    def test_concurrent_duplicate_authorized_webhooks_finalize_once(self):
        create_plan = patch(
            'apps.billing.mp_service.MercadoPagoService.create_preapproval_plan',
            return_value={
                'id': f'plan-{uuid.uuid4()}',
                'sandbox_init_point': 'https://mp.invalid/checkout',
            },
        )
        create_plan_mock = create_plan.start()
        self.addCleanup(create_plan.stop)
        checkout_result = create_appointments_checkout(
            user=self.owner,
            business=self.business,
            internal_provisioning=True,
            **self.quote_request,
        )
        checkout = AppointmentsCheckout.objects.get(pk=checkout_result['checkout_id'])
        subscription_id = f'sub-{uuid.uuid4()}'
        from apps.billing.services.appointments_checkout import apply_appointments_preapproval

        apply_appointments_preapproval(
            preapproval_id=subscription_id,
            plan_id=checkout.provider_preapproval_plan_id,
            preapproval={
                'id': subscription_id,
                'status': 'authorized',
                'preapproval_plan_id': checkout.provider_preapproval_plan_id,
                'external_reference': checkout.external_reference,
                'auto_recurring': {
                    'transaction_amount': checkout.quote_snapshot['total_amount'],
                    'currency_id': checkout.quote_snapshot['currency'],
                },
            },
        )
        payment_id = f'auth-{uuid.uuid4()}'
        self._resource_ids.append(payment_id)
        payment_data = {
            'id': payment_id,
            'payment_id': f'provider-{payment_id}',
            'status': 'authorized',
            'preapproval_id': subscription_id,
            'transaction_amount': checkout.quote_snapshot['total_amount'],
            'currency_id': checkout.quote_snapshot['currency'],
            'date_approved': timezone.now().isoformat(),
        }
        delivery_ids = [
            WebhookDelivery.objects.create(
                topic='subscription_authorized_payment',
                resource_id=payment_id,
                received_at=timezone.now(),
            ).pk
            for _ in range(2)
        ]
        barrier = Barrier(2)

        def process_delivery(delivery_id):
            connections.close_all()
            try:
                delivery = WebhookDelivery.objects.get(pk=delivery_id)
                barrier.wait(timeout=5)
                from apps.billing.webhook_processor import _handle_authorized_payment

                with (
                    patch(
                        'apps.billing.mp_service.MercadoPagoService.get_authorized_payment',
                        return_value=payment_data,
                    ),
                    patch('apps.billing.email_helpers.send_subscription_activated_email'),
                    patch('apps.billing.email_helpers.send_admin_subscription_payment_created_email'),
                ):
                    _handle_authorized_payment(payment_id, delivery)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(process_delivery, delivery_ids))

        subscription = SubscriptionV2.objects.get(provider_sub_id=subscription_id)
        checkout.refresh_from_db()
        self.assertTrue(subscription.is_active)
        self.assertEqual(checkout.status, AppointmentsCheckout.Status.ACTIVE)
        self.assertEqual(BillingInvoiceEvent.objects.filter(
            provider_authorized_payment_id=payment_id,
        ).count(), 1)
        self.assertEqual(SubscriptionAddon.objects.filter(
            subscription_v2=subscription,
            code='appointments_extra_professional',
        ).count(), 1)
        create_plan_mock.assert_called_once()

    def _fixture_teardown(self):
        business_id = getattr(self, 'business', None)
        owner_id = getattr(self, 'owner', None)
        if business_id is None or owner_id is None:
            return
        business_id = self.business.pk
        subscription_ids = list(
            SubscriptionV2.objects.filter(business_id=business_id).values_list('pk', flat=True)
        )
        preapproval_ids = list(
            SubscriptionV2.objects.filter(business_id=business_id)
            .exclude(provider_sub_id__isnull=True)
            .values_list('provider_sub_id', flat=True)
        )
        BillingInvoiceEvent.objects.filter(
            Q(subscription_id__in=subscription_ids)
            | Q(provider_subscription_id__in=preapproval_ids)
        ).delete()
        AppointmentsCheckout.objects.filter(business_id=business_id).delete()
        SubscriptionAddon.objects.filter(subscription_v2_id__in=subscription_ids).delete()
        SubscriptionV2.objects.filter(pk__in=subscription_ids).delete()
        Membership.objects.filter(business_id=business_id).delete()
        LegacySubscription.objects.filter(business_id=business_id).delete()
        Business.objects.filter(pk=business_id).delete()
        WebhookDelivery.objects.filter(resource_id__in=self._resource_ids).delete()
        User.objects.filter(pk=self.owner.pk).delete()
