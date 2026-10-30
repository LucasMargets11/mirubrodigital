"""S7B: real preparation/worker paths, current S7A access, no external IO."""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.appointments.services.reminder_automation import upcoming_key
from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin
from apps.billing.appointments_plans import AUTOMATIONS
from apps.billing.models import BillingInvoiceEvent, SubscriptionV2
from apps.billing.services.appointments import can_use_appointments_automations
from apps.billing.services.appointments_lifecycle import (
    apply_appointments_change, apply_appointments_renewal,
    record_appointments_payment_failure, request_appointments_change,
)
from apps.business.models import Business, SubscriptionAddon
from apps.leads.tests import test_human_messages as human_tests
from apps.notifications.models import BusinessNotification

from .deliveries import prepare_customer_delivery, retry_due_customer_deliveries
from .delivery_providers import ProviderSendResult
from .models import (
    Customer, CustomerCommunicationSettings, CustomerContactPreferences,
    CustomerMessageDelivery, CustomerReminder,
)
from .reminder_deliveries import prepare_reminder_deliveries, recover_missing_reminder_deliveries
from .reminder_dispatch import dispatch_due_customer_reminders
from .tasks import execute_customer_delivery

D = CustomerMessageDelivery
S = D.Status
DENIED = 'appointments_automations_unavailable'


class AppointmentsOutboundS7BTests(TurnosAgendaMixin, TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        clock = patch('django.utils.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.business = Business.objects.create(
            name='S7B', default_service='appointments', status='active',
        )
        self.subscription = SubscriptionV2.objects.create(
            business=self.business, service_type='appointments',
            plan_code='appointments_ai', usage_tier='ai_300',
            provider='manual', status='active', is_active=True,
            external_reference=f'S7B-{uuid.uuid4()}', billing_cycle='monthly',
            current_period_start=self.now - timedelta(days=15),
            current_period_end=self.now + timedelta(days=15),
        )
        self.customer = Customer.objects.create(
            business=self.business, name='Ana', phone='1155550101', email='ana@example.com',
        )
        CustomerContactPreferences.objects.create(
            business=self.business, customer=self.customer, email_enabled=True,
            email_consent_at=self.now, email_consent_source='manual',
            email_consent_value=self.customer.email,
        )
        CustomerCommunicationSettings.objects.create(
            business=self.business, appointment_email_enabled=True, no_show_email_enabled=True,
        )
        service, _ = self._agenda(self.business)
        self.appointment = self._appt(
            self.business, service, self.customer, self.now + timedelta(hours=4),
        )
        self.reminder = CustomerReminder.objects.create(
            business=self.business, customer=self.customer, appointment=self.appointment,
            source=CustomerReminder.Source.APPOINTMENT_UPCOMING,
            automation_key=upcoming_key(self.appointment),
            title='Internal reminder', remind_at=self.now,
        )
        self.provider = Mock()
        self.provider.name = D.Provider.FAKE_EMAIL
        self.provider.channel = D.Channel.EMAIL
        self.provider.send.return_value = ProviderSendResult.ok('s7b-mocked')
        provider = patch('apps.customers.deliveries.get_provider', return_value=self.provider)
        self.get_provider = provider.start()
        self.addCleanup(provider.stop)
        boto = patch('boto3.client', side_effect=AssertionError('No real provider allowed'))
        boto.start()
        self.addCleanup(boto.stop)

    def configure(self, plan='appointments_ai', **fields):
        fields = {'plan_code': plan, 'usage_tier': 'ai_300' if plan == 'appointments_ai' else None, **fields}
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(**fields)
        self.subscription.refresh_from_db()

    def prepare(self, *, enqueue=False):
        return prepare_reminder_deliveries(self.reminder, enqueue=enqueue)[0]

    def assert_blocked(self, delivery):
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SKIPPED)
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, DENIED))
        self.assertIsNotNone(delivery.skipped_at)
        self.assertIsNone(delivery.sent_at)
        self.assertIsNone(delivery.provider_message_id)
        self.assertIsNone(delivery.next_retry_at)
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()

    def test_base_without_addon_is_skipped_before_enqueue(self):
        self.configure('appointments')
        with patch('apps.customers.tasks.execute_customer_delivery.delay') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                delivery = self.prepare(enqueue=True)
            enqueue.assert_not_called()
        self.assertEqual(delivery.attempt_count, 0)
        self.assertEqual(delivery.skip_reason, DENIED)
        self.assertIsNone(delivery.provider)
        self.provider.send.assert_not_called()

    def test_base_and_pro_with_addon_can_enqueue_and_send(self):
        for plan in ('appointments', 'appointments_pro'):
            with self.subTest(plan=plan):
                self.configure(plan)
                addon = SubscriptionAddon.objects.create(
                    subscription_v2=self.subscription, code=AUTOMATIONS, quantity=1, is_active=True,
                )
                with patch('apps.customers.tasks.execute_customer_delivery.delay') as enqueue:
                    with self.captureOnCommitCallbacks(execute=True):
                        delivery, _ = prepare_customer_delivery(
                            business=self.business, customer=self.customer, channel=D.Channel.EMAIL,
                            purpose=D.Purpose.APPOINTMENT_REMINDER, idempotency_key=plan,
                        )
                    enqueue.assert_called_once_with(str(delivery.pk))
                self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
                addon.delete()
        self.assertEqual(self.provider.send.call_count, 2)

    def test_ai_without_addon_sends_only_once(self):
        delivery = self.prepare()
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        self.assertEqual(self.prepare().pk, delivery.pk)
        self.provider.send.assert_called_once()

    def test_s8h_traditional_automations_never_authorize_or_meter_ai(self):
        from apps.appointments.models import (
            AppointmentAIUsageAuthorization, AppointmentAIUsageCharge, AppointmentAIUsageSession,
        )

        with patch(
            'apps.appointments.services.ai_usage_authorization.authorize_ai_interaction',
            side_effect=AssertionError('S7 must not authorize AI'),
        ) as authorize:
            for purpose in (D.Purpose.APPOINTMENT_REMINDER, D.Purpose.NO_SHOW_FOLLOWUP):
                delivery, _ = prepare_customer_delivery(
                    business=self.business, customer=self.customer, channel=D.Channel.EMAIL,
                    purpose=purpose, idempotency_key=f's8h-{purpose}', enqueue=False,
                )
                self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
            authorize.assert_not_called()
        self.assertEqual(self.provider.send.call_count, 2)
        self.assertFalse(AppointmentAIUsageSession.objects.exists())
        self.assertFalse(AppointmentAIUsageCharge.objects.exists())
        self.assertFalse(AppointmentAIUsageAuthorization.objects.exists())

    def test_grace_allows_outbound(self):
        record_appointments_payment_failure(subscription=self.subscription, at=self.now)
        self.assertEqual(execute_customer_delivery.run(str(self.prepare().pk)), S.SENT)
        self.provider.send.assert_called_once()

    def test_suspended_blocks_existing_delivery_without_provider_initialization(self):
        delivery = self.prepare()
        self.configure(status='suspended', grace_until=self.now - timedelta(seconds=1))
        self.assert_blocked(delivery)
        delivery.refresh_from_db()
        self.assertEqual(delivery.attempt_count, 0)

    def test_enqueued_while_active_then_suspended_blocks_at_runtime(self):
        with patch('apps.customers.tasks.execute_customer_delivery.delay') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                delivery = self.prepare(enqueue=True)
            enqueue.assert_called_once_with(str(delivery.pk))
        self.configure(status='suspended')
        self.assert_blocked(delivery)

    def test_no_show_without_reminder_link_still_checks_runtime_entitlement(self):
        delivery, _ = prepare_customer_delivery(
            business=self.business, customer=self.customer, channel=D.Channel.EMAIL,
            purpose=D.Purpose.NO_SHOW_FOLLOWUP, idempotency_key='no-show-unlinked', enqueue=False,
        )
        self.configure('appointments_pro')
        self.assert_blocked(delivery)

    def request_downgrade(self):
        user = get_user_model().objects.create_user(username=f's7b-{uuid.uuid4()}')
        change, _ = request_appointments_change(
            business=self.business, user=user,
            target={'plan_code': 'appointments_pro', 'usage_tier': None}, at=self.now,
        )
        return change

    def test_pending_ai_to_pro_downgrade_still_allows_send(self):
        self.request_downgrade()
        self.assertEqual(execute_customer_delivery.run(str(self.prepare().pk)), S.SENT)
        self.provider.send.assert_called_once()

    def test_applied_downgrade_blocks_queued_delivery(self):
        delivery = self.prepare()
        change = self.request_downgrade()
        self.assertTrue(apply_appointments_change(change, at=self.subscription.current_period_end))
        self.assert_blocked(delivery)

    def test_reactivation_allows_new_event_without_reviving_skipped_event(self):
        self.configure(status='suspended')
        skipped = self.prepare()
        self.assertEqual(skipped.status, S.SKIPPED)
        event = BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=f's7b-{uuid.uuid4()}',
            provider_status='authorized', paid_at=self.now, amount=39000, currency='ARS',
        )
        self.assertTrue(apply_appointments_renewal(subscription=self.subscription, invoice_event=event))
        self.assertEqual(self.prepare().pk, skipped.pk)
        self.assertIsNone(execute_customer_delivery.run(str(skipped.pk)))
        self.appointment.status = Appointment.Status.NO_SHOW
        self.appointment.save(update_fields=['status'])
        self.reminder.source = CustomerReminder.Source.NO_SHOW_FOLLOWUP
        self.reminder.save(update_fields=['source'])
        delivery = self.prepare()
        self.assertNotEqual(delivery.pk, skipped.pk)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
        self.provider.send.assert_called_once()

    def test_helper_false_is_authoritative_even_for_ai(self):
        delivery = self.prepare()
        with patch('apps.customers.deliveries.can_use_appointments_automations', return_value=False) as gate:
            self.assert_blocked(delivery)
            gate.assert_called_once()

    def test_retry_rechecks_current_entitlement(self):
        delivery = self.prepare()
        self.provider.send.return_value = ProviderSendResult.failure('temporary', retryable=True)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.FAILED)
        delivery.refresh_from_db()
        self.assertIsNotNone(delivery.next_retry_at)
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        self.configure(status='suspended')
        with patch('django.utils.timezone.now', return_value=delivery.next_retry_at):
            result = retry_due_customer_deliveries()
        self.assertEqual(result.skipped, 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.attempt_count, 1)
        self.assertEqual(delivery.skip_reason, DENIED)
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()

    def test_direct_preparation_cannot_bypass_gate_for_either_purpose(self):
        self.configure('appointments')
        for purpose in D.Purpose.values:
            with self.subTest(purpose=purpose):
                delivery, _ = prepare_customer_delivery(
                    business=self.business, customer=self.customer, channel=D.Channel.EMAIL,
                    purpose=purpose, idempotency_key=purpose, enqueue=False,
                )
                self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, DENIED))

    def test_dispatch_and_recovery_keep_internal_notice_but_do_not_enqueue(self):
        self.configure('appointments')
        with patch('apps.customers.tasks.execute_customer_delivery.delay') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(dispatch_due_customer_reminders().dispatched, 1)
                self.assertEqual(recover_missing_reminder_deliveries(), 0)
            enqueue.assert_not_called()
        self.assertEqual(BusinessNotification.objects.filter(
            kind=BusinessNotification.Kind.CUSTOMER_REMINDER_DUE,
        ).count(), 1)
        self.reminder.refresh_from_db()
        self.assertIsNotNone(self.reminder.notified_at)
        self.assertEqual(D.objects.get().skip_reason, DENIED)
        self.provider.send.assert_not_called()

    def test_scheduled_cancellation_still_valid_allows_send(self):
        self.configure(cancel_at_period_end=True)
        self.assertEqual(execute_customer_delivery.run(str(self.prepare().pk)), S.SENT)


@override_settings(**human_tests.TAKEOVER_SETTINGS)
class ManualOutboundS7BTests(human_tests.HumanMessagesMixin, TestCase):
    def test_manual_staff_message_is_not_subject_to_automations_gate(self):
        self._setup()
        self.assertFalse(can_use_appointments_automations(self.biz))
        transport = human_tests.FakeSend(human_tests.ok())
        with patch('apps.billing.services.appointments.can_use_appointments_automations', return_value=False):
            message = self._send()
            self.assertEqual(
                human_tests.svc.deliver_staff_message(message.pk, send=transport), 'delivered',
            )
        self.assertEqual(len(transport.payloads), 1)
