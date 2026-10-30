"""S7C: S3 configuration + S6 lifecycle + S7A access through the S7B worker."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.appointments.models import Appointment
from apps.appointments.services.customer_history import scoped_customer_appointments
from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin
from apps.billing.appointments_plans import AUTOMATIONS
from apps.billing.models import BillingInvoiceEvent, SubscriptionV2
from apps.billing.services.appointments import can_use_appointments_automations
from apps.billing.services.appointments_lifecycle import (
    GRACE_PERIOD,
    apply_appointments_change,
    apply_appointments_renewal,
    can_send_appointments_automation,
    record_appointments_payment_failure,
    request_appointments_change,
)
from apps.billing.tasks import _transition_past_due_to_suspended
from apps.business.models import Business, SubscriptionAddon

from .deliveries import prepare_customer_delivery, retry_due_customer_deliveries
from .delivery_providers import ProviderSendResult
from .models import (
    Customer,
    CustomerCommunicationSettings,
    CustomerContactPreferences,
    CustomerMessageDelivery,
    CustomerNote,
    CustomerReminder,
    CustomerReminderAutomationSettings,
)
from .tasks import execute_customer_delivery

D = CustomerMessageDelivery
S = D.Status
DENIED = 'appointments_automations_unavailable'
TICK = timedelta(microseconds=1)


class AppointmentsLifecycleS7CTests(TurnosAgendaMixin, TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 29, 12, tzinfo=dt_timezone.utc)
        clock = patch('django.utils.timezone.now', return_value=self.now)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.period_end = self.now + timedelta(days=15)
        self.business = Business.objects.create(
            name='S7C', default_service='appointments', status='active',
        )
        self.subscription = SubscriptionV2.objects.create(
            business=self.business, service_type='appointments',
            plan_code='appointments_ai', usage_tier='ai_300',
            provider='manual', status='active', is_active=True,
            external_reference=f'S7C-{uuid.uuid4()}', billing_cycle='monthly',
            current_period_start=self.now - timedelta(days=15),
            current_period_end=self.period_end,
        )
        self.user = get_user_model().objects.create_user(username=f's7c-{uuid.uuid4()}')
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
            self.business, service, self.customer, self.period_end + timedelta(days=10),
        )
        self.provider = Mock()
        self.provider.name = D.Provider.FAKE_EMAIL
        self.provider.channel = D.Channel.EMAIL
        self.provider.send.return_value = ProviderSendResult.ok('s7c-mocked')
        provider = patch('apps.customers.deliveries.get_provider', return_value=self.provider)
        self.get_provider = provider.start()
        self.addCleanup(provider.stop)
        boto = patch('boto3.client', side_effect=AssertionError('No external provider allowed'))
        boto.start()
        self.addCleanup(boto.stop)

    def configure(self, plan='appointments_ai', *, automations=False):
        SubscriptionV2.objects.filter(pk=self.subscription.pk).update(
            plan_code=plan, usage_tier='ai_300' if plan == 'appointments_ai' else None,
        )
        if automations:
            SubscriptionAddon.objects.create(
                subscription_v2=self.subscription, code=AUTOMATIONS, quantity=1, is_active=True,
            )
        self.subscription.refresh_from_db()

    def prepare(self, purpose=D.Purpose.APPOINTMENT_REMINDER, *, key=None):
        with patch('apps.customers.tasks.execute_customer_delivery.delay') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                delivery, _ = prepare_customer_delivery(
                    business=self.business, customer=self.customer, channel=D.Channel.EMAIL,
                    purpose=purpose, idempotency_key=key or f's7c-{uuid.uuid4()}',
                    appointment=self.appointment,
                )
            if delivery.status == S.PENDING:
                enqueue.assert_called_once_with(str(delivery.pk))
            else:
                enqueue.assert_not_called()
        return delivery

    def assert_access(self, expected):
        self.assertIs(
            can_use_appointments_automations(self.business, at=self.clock.return_value),
            expected,
        )
        self.assertIs(
            can_send_appointments_automation(self.business, at=self.clock.return_value),
            expected,
        )

    def assert_new_outbound(self, expected):
        self.assert_access(expected)
        for purpose in (D.Purpose.APPOINTMENT_REMINDER, D.Purpose.NO_SHOW_FOLLOWUP):
            with self.subTest(purpose=purpose, at=self.clock.return_value):
                self.provider.send.reset_mock()
                self.get_provider.reset_mock()
                delivery = self.prepare(purpose)
                self.assertEqual(delivery.status, S.PENDING if expected else S.SKIPPED)
                outcome = execute_customer_delivery.run(str(delivery.pk))
                self.assertEqual(outcome, S.SENT if expected else None)
                delivery.refresh_from_db()
                if expected:
                    self.assertEqual(delivery.status, S.SENT)
                    self.assertEqual(delivery.attempt_count, 1)
                    self.provider.send.assert_called_once()
                else:
                    self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, DENIED))
                    self.assertEqual(delivery.skipped_at, self.clock.return_value)
                    self.assertEqual(delivery.attempt_count, 0)
                    self.assertIsNone(delivery.next_retry_at)
                    self.assertIsNone(delivery.sent_at)
                    self.assertIsNone(delivery.provider_message_id)
                    self.get_provider.assert_not_called()
                    self.provider.send.assert_not_called()

    def fail_payment(self):
        self.clock.return_value = self.period_end
        self.assertTrue(record_appointments_payment_failure(
            subscription=self.subscription, at=self.clock.return_value,
        ))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.PAST_DUE)
        self.assertEqual(self.subscription.grace_until, self.period_end + timedelta(days=3))

    def suspend(self):
        self.clock.return_value = self.period_end + GRACE_PERIOD + TICK
        with patch('apps.billing.email_helpers.send_subscription_suspended_email'):
            self.assertEqual(
                _transition_past_due_to_suspended(SubscriptionV2, self.clock.return_value), 1,
            )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.SUSPENDED)
        self.assertEqual(self.subscription.suspended_at, self.clock.return_value)

    def renew(self):
        event = BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=f's7c-{uuid.uuid4()}',
            provider_status='authorized', paid_at=self.clock.return_value,
            amount=39000, currency='ARS',
        )
        self.assertTrue(apply_appointments_renewal(
            subscription=self.subscription, invoice_event=event,
        ))
        self.subscription.refresh_from_db()
        state = SubscriptionV2.objects.filter(pk=self.subscription.pk).values().get()
        self.assertFalse(apply_appointments_renewal(
            subscription=self.subscription, invoice_event=event,
        ))
        self.assertEqual(
            SubscriptionV2.objects.filter(pk=self.subscription.pk).values().get(), state,
        )
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.ACTIVE)
        self.assertTrue(self.subscription.is_active)
        self.assertIsNone(self.subscription.grace_started_at)
        self.assertIsNone(self.subscription.grace_until)
        self.assertIsNone(self.subscription.suspended_at)

    def change(self, **target):
        pending, _ = request_appointments_change(
            business=self.business, user=self.user, target=target,
            at=self.clock.return_value,
        )
        return pending

    def test_active_ai_has_access(self):
        self.assert_new_outbound(True)

    def test_active_pro_with_addon_has_access(self):
        self.configure('appointments_pro', automations=True)
        self.assert_new_outbound(True)

    def test_active_pro_without_addon_is_blocked(self):
        self.configure('appointments_pro')
        self.assert_new_outbound(False)

    def test_grace_boundaries_use_s6_without_waiting_for_suspension_job(self):
        self.fail_payment()
        for offset, expected in (
            (timedelta(0), True),
            (timedelta(days=1, hours=12), True),
            (GRACE_PERIOD - TICK, True),
            (GRACE_PERIOD, True),
            (GRACE_PERIOD + TICK, False),
        ):
            with self.subTest(offset=offset):
                self.clock.return_value = self.period_end + offset
                self.assert_new_outbound(expected)
                self.subscription.refresh_from_db()
                self.assertEqual(self.subscription.status, SubscriptionV2.Status.PAST_DUE)
        self.assertEqual(
            _transition_past_due_to_suspended(SubscriptionV2, self.period_end + GRACE_PERIOD), 0,
        )
        self.suspend()
        self.assert_new_outbound(False)

    def test_grace_preserves_addon_but_cannot_grant_a_missing_entitlement(self):
        self.configure('appointments_pro', automations=True)
        self.fail_payment()
        self.clock.return_value = self.subscription.grace_until - TICK
        self.assert_new_outbound(True)
        self.clock.return_value = self.subscription.grace_until + TICK
        self.assert_new_outbound(False)

    def test_grace_without_commercial_entitlement_is_blocked(self):
        self.configure('appointments_pro')
        self.fail_payment()
        self.assert_new_outbound(False)

    def test_repeated_payment_failure_does_not_extend_grace(self):
        self.fail_payment()
        deadline = self.subscription.grace_until
        self.clock.return_value += timedelta(days=2)
        self.assertFalse(record_appointments_payment_failure(
            subscription=self.subscription, at=self.clock.return_value,
        ))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.grace_until, deadline)
        self.assert_new_outbound(True)
        self.clock.return_value = deadline + TICK
        self.assert_new_outbound(False)

    def test_cancel_at_period_end_blocks_at_exact_boundary(self):
        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=['cancel_at_period_end'])
        for at, expected in (
            (self.period_end - TICK, True),
            (self.period_end, False),
            (self.period_end + TICK, False),
        ):
            self.clock.return_value = at
            self.assert_new_outbound(expected)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.ACTIVE)

    def test_cancel_boundary_takes_precedence_over_unexpired_grace(self):
        self.fail_payment()
        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=['cancel_at_period_end'])
        self.assert_new_outbound(False)

    def test_reactivation_during_grace_preserves_access_and_clears_grace(self):
        self.fail_payment()
        self.clock.return_value += timedelta(days=1)
        self.assert_new_outbound(True)
        self.renew()
        self.assert_new_outbound(True)

    def test_reactivation_after_grace_before_suspension_job_recovers_access(self):
        self.fail_payment()
        self.clock.return_value = self.subscription.grace_until + TICK
        self.assert_access(False)
        self.renew()
        self.assert_new_outbound(True)

    def test_reactivation_from_suspended_recovers_ai_access(self):
        self.fail_payment()
        self.suspend()
        self.assert_access(False)
        self.renew()
        self.assert_new_outbound(True)

    def test_reactivation_from_suspended_recovers_addon_access(self):
        self.configure('appointments_pro', automations=True)
        self.fail_payment()
        self.suspend()
        self.renew()
        self.assert_new_outbound(True)

    def test_reactivation_does_not_grant_missing_commercial_entitlement(self):
        self.configure('appointments_pro')
        self.fail_payment()
        self.suspend()
        self.renew()
        self.assert_new_outbound(False)

    def test_ai_to_pro_blocks_only_after_renewal_applies_downgrade(self):
        pending = self.change(plan_code='appointments_pro', usage_tier=None)
        self.assertEqual(pending.status, 'scheduled')
        self.assertEqual(pending.scheduled_for, self.period_end)
        self.assert_new_outbound(True)
        self.clock.return_value = self.period_end - TICK
        self.assert_new_outbound(True)
        self.clock.return_value = self.period_end
        self.assert_new_outbound(True)
        self.renew()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assertEqual(pending.applied_at, self.period_end)
        self.assert_new_outbound(False)

    def test_ai_to_pro_with_automations_keeps_access_after_renewal(self):
        pending = self.change(
            plan_code='appointments_pro', usage_tier=None, automations=True,
        )
        self.assertEqual(pending.status, 'scheduled')
        self.assert_new_outbound(True)
        self.clock.return_value = self.period_end
        self.renew()
        self.assert_new_outbound(True)
        self.assertTrue(self.subscription.addons.filter(
            code=AUTOMATIONS, quantity=1, is_active=True,
        ).exists())

    def test_pro_to_ai_grants_access_immediately_after_application(self):
        self.configure('appointments_pro')
        pending = self.change(plan_code='appointments_ai', usage_tier='ai_300')
        self.assertEqual(pending.status, 'pending_payment')
        self.assert_new_outbound(False)
        self.assertTrue(apply_appointments_change(
            pending, payment_id='s7c-upgrade-ai', at=self.clock.return_value,
        ))
        self.assert_new_outbound(True)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.current_period_end, self.period_end)

    def test_future_addon_removal_preserves_access_until_applied(self):
        self.configure('appointments_pro', automations=True)
        addon = self.subscription.addons.get(code=AUTOMATIONS)
        pending = self.change(automations=False)
        self.assertEqual(pending.scheduled_for, self.period_end)
        self.assert_new_outbound(True)
        self.clock.return_value = self.period_end - TICK
        self.assert_new_outbound(True)
        self.clock.return_value = self.period_end
        self.assert_new_outbound(True)
        self.renew()
        self.assert_new_outbound(False)
        addon.refresh_from_db()
        self.assertFalse(addon.is_active)
        self.assertEqual(addon.quantity, 0)
        self.assertEqual(addon.deactivated_at, self.period_end)

    def test_immediate_addon_upgrade_grants_access_after_application(self):
        self.configure('appointments_pro')
        pending = self.change(automations=True)
        self.assertEqual(pending.status, 'pending_payment')
        self.assert_new_outbound(False)
        self.assertTrue(apply_appointments_change(
            pending, payment_id='s7c-upgrade-addon', at=self.clock.return_value,
        ))
        self.assert_new_outbound(True)

    def assert_queued_blocked(self, deliveries):
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        for delivery in deliveries:
            self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SKIPPED)
            delivery.refresh_from_db()
            self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, DENIED))
            self.assertEqual(delivery.skipped_at, self.clock.return_value)
            self.assertEqual(delivery.attempt_count, 0)
            self.assertIsNone(delivery.next_retry_at)
            self.assertIsNone(delivery.sent_at)
            self.assertIsNone(delivery.provider_message_id)
            self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()

    def queue_both_purposes(self):
        deliveries = [
            self.prepare(D.Purpose.APPOINTMENT_REMINDER),
            self.prepare(D.Purpose.NO_SHOW_FOLLOWUP),
        ]
        self.assertTrue(all(delivery.status == S.PENDING for delivery in deliveries))
        return deliveries

    def test_jobs_queued_before_suspension_are_skipped_afterward(self):
        deliveries = self.queue_both_purposes()
        self.fail_payment()
        self.suspend()
        self.assert_queued_blocked(deliveries)

    def test_jobs_queued_before_grace_expiry_are_skipped_without_suspension_job(self):
        deliveries = self.queue_both_purposes()
        self.fail_payment()
        self.clock.return_value = self.subscription.grace_until + TICK
        self.assert_queued_blocked(deliveries)

    def test_jobs_queued_before_cancellation_are_skipped_at_period_end(self):
        deliveries = self.queue_both_purposes()
        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=['cancel_at_period_end'])
        self.clock.return_value = self.period_end
        self.assert_queued_blocked(deliveries)

    def test_jobs_queued_before_downgrade_use_current_configuration(self):
        deliveries = self.queue_both_purposes()
        self.change(plan_code='appointments_pro', usage_tier=None)
        self.clock.return_value = self.period_end
        self.renew()
        self.assert_queued_blocked(deliveries)

    def test_jobs_queued_before_addon_removal_use_current_configuration(self):
        self.configure('appointments_pro', automations=True)
        deliveries = self.queue_both_purposes()
        self.change(automations=False)
        self.clock.return_value = self.period_end
        self.renew()
        self.assert_queued_blocked(deliveries)

    def test_eligible_retry_queued_before_reactivation_sends_once_after_recovery(self):
        delivery = self.prepare(key='retry-after-reactivation')
        self.provider.send.return_value = ProviderSendResult.failure('temporary', retryable=True)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.FAILED)
        delivery.refresh_from_db()
        retry_at = delivery.next_retry_at
        self.assertIsNotNone(retry_at)
        self.assertEqual(delivery.attempt_count, 1)
        self.provider.send.reset_mock()
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        self.provider.send.assert_not_called()
        self.fail_payment()
        self.suspend()
        self.renew()
        self.provider.send.return_value = ProviderSendResult.ok('s7c-retry')
        result = retry_due_customer_deliveries()
        self.assertEqual((result.due, result.sent, result.errors), (1, 1, 0))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, S.SENT)
        self.assertEqual(delivery.attempt_count, 2)
        self.assertIsNone(delivery.next_retry_at)
        self.assertEqual(self.prepare(key='retry-after-reactivation').pk, delivery.pk)
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        self.assertEqual(retry_due_customer_deliveries().due, 0)
        self.provider.send.assert_called_once()

    def test_pending_job_delayed_until_after_reactivation_can_send(self):
        delivery = self.prepare()
        self.fail_payment()
        self.suspend()
        self.renew()
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        self.provider.send.assert_called_once()

    def test_retry_skipped_during_suspension_stays_final_after_reactivation(self):
        delivery = self.prepare(key='final-skipped')
        self.provider.send.return_value = ProviderSendResult.failure('temporary', retryable=True)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.FAILED)
        self.fail_payment()
        self.suspend()
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        result = retry_due_customer_deliveries()
        self.assertEqual((result.due, result.skipped, result.errors), (1, 1, 0))
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.skip_reason), (S.SKIPPED, DENIED))
        self.assertEqual(delivery.attempt_count, 1)
        self.assertIsNone(delivery.next_retry_at)
        self.renew()
        self.assert_access(True)
        self.assertEqual(self.prepare(key='final-skipped').pk, delivery.pk)
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        self.assertEqual(retry_due_customer_deliveries().due, 0)
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()

    def test_nonretryable_failure_is_not_revived_by_reactivation(self):
        delivery = self.prepare()
        self.provider.send.return_value = ProviderSendResult.failure('permanent', retryable=False)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.FAILED)
        self.fail_payment()
        self.suspend()
        self.renew()
        self.provider.send.reset_mock()
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        self.assertEqual(retry_due_customer_deliveries().due, 0)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, S.FAILED)
        self.assertIsNone(delivery.next_retry_at)
        self.provider.send.assert_not_called()

    def test_loss_of_access_preserves_history_configuration_and_appointments(self):
        historical = self._appt(
            self.business, self.appointment.service, self.customer,
            self.now - timedelta(days=1), status_=Appointment.Status.COMPLETED,
        )
        CustomerNote.objects.create(
            business=self.business, customer=self.customer, body='Existing customer history',
        )
        CustomerReminderAutomationSettings.objects.create(
            business=self.business, appointment_reminder_enabled=True, no_show_followup_enabled=True,
        )
        CustomerReminder.objects.create(
            business=self.business, customer=self.customer, appointment=self.appointment,
            title='Internal reminder', remind_at=self.period_end,
        )
        sent = self.prepare(key='sent-history')
        self.assertEqual(execute_customer_delivery.run(str(sent.pk)), S.SENT)
        models = (
            Business, Customer, Appointment, CustomerNote, CustomerReminder,
            CustomerCommunicationSettings, CustomerContactPreferences,
            CustomerReminderAutomationSettings, D,
        )
        snapshots = {
            model: list(model.objects.order_by('pk').values()) for model in models
        }
        pending = self.change(plan_code='appointments_pro', usage_tier=None)
        self.fail_payment()
        self.clock.return_value = self.subscription.grace_until + TICK
        self.assert_access(False)
        self.suspend()
        self.assert_access(False)
        self.renew()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assert_access(False)
        for model, before in snapshots.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(list(model.objects.order_by('pk').values()), before)
        self.assertIn(historical.pk, scoped_customer_appointments(
            self.customer, 'history', now=self.clock.return_value,
        ).values_list('pk', flat=True))
        self.assertIsNone(execute_customer_delivery.run(str(sent.pk)))
        self.assert_new_outbound(False)
