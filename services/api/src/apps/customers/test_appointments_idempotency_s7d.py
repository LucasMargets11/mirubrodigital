"""S7D: real PostgreSQL claims, retries and recovery; no external sends."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock, patch

from botocore.exceptions import ReadTimeoutError
from django.conf import settings
from django.db import DatabaseError, IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.appointments.services.reminder_automation import no_show_key, upcoming_key
from apps.appointments.tests.test_customer_core_access import _turnos_business
from apps.billing.models import SubscriptionV2
from apps.billing.services.appointments import can_use_appointments_automations

from . import deliveries
from .deliveries import execute_delivery, processing_lease, retry_due_customer_deliveries
from .delivery_providers import AmazonSESProvider, ProviderSendResult
from .models import CustomerCommunicationSettings, CustomerMessageDelivery, CustomerReminder
from .reminder_deliveries import (
    delivery_idempotency_key, prepare_reminder_deliveries, recover_missing_reminder_deliveries,
)
from .tasks import execute_customer_delivery
from .test_deliveries import DeliveryMixin

D = CustomerMessageDelivery
S = D.Status
PURPOSES = (D.Purpose.APPOINTMENT_REMINDER, D.Purpose.NO_SHOW_FOLLOWUP)


class S7DFixture(DeliveryMixin):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql', 'S7D requires isolated PostgreSQL')
        self.now = timezone.now().replace(microsecond=0)
        clock = patch('django.utils.timezone.now', return_value=self.now)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.biz = _turnos_business(slug='s7d')
        self._enable_automations()
        self.customer = self._customer(self.biz)
        self._consent(self.customer, D.Channel.EMAIL)
        CustomerCommunicationSettings.objects.create(
            business=self.biz, appointment_email_enabled=True, no_show_email_enabled=True,
        )
        service, _ = self._agenda(self.biz)
        self.reminders = {}
        for purpose in PURPOSES:
            upcoming = purpose == D.Purpose.APPOINTMENT_REMINDER
            appointment = self._appt(
                self.biz, service, self.customer, self.now + timedelta(days=2),
                status_=Appointment.Status.CONFIRMED if upcoming else Appointment.Status.NO_SHOW,
            )
            self.reminders[purpose] = CustomerReminder.objects.create(
                business=self.biz, customer=self.customer, appointment=appointment,
                source=CustomerReminder.Source.APPOINTMENT_UPCOMING if upcoming else CustomerReminder.Source.NO_SHOW_FOLLOWUP,
                automation_key=upcoming_key(appointment) if upcoming else no_show_key(appointment),
                title='S7D internal reminder', remind_at=self.now,
            )
        self.provider = Mock()
        self.provider.name = D.Provider.FAKE_EMAIL
        self.provider.channel = D.Channel.EMAIL
        self.provider.send.return_value = ProviderSendResult.ok('s7d-accepted')
        provider = patch('apps.customers.deliveries.get_provider', return_value=self.provider)
        self.get_provider = provider.start()
        self.addCleanup(provider.stop)
        boto = patch('boto3.client', side_effect=AssertionError('No real provider allowed'))
        boto.start()
        self.addCleanup(boto.stop)

    def prepare(self, purpose=PURPOSES[0], *, enqueue=False):
        return prepare_reminder_deliveries(self.reminders[purpose], enqueue=enqueue)[0]

    def subscription_status(self, status):
        SubscriptionV2.objects.filter(business=self.biz, service_type='appointments').update(status=status)

    def fail_retriably(self, delivery):
        self.provider.send.return_value = ProviderSendResult.failure('temporary', retryable=True)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.FAILED)
        delivery.refresh_from_db()
        self.assertEqual(delivery.attempt_count, 1)
        self.assertIsNotNone(delivery.next_retry_at)
        self.clock.return_value = delivery.next_retry_at
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        self.provider.send.return_value = ProviderSendResult.ok('s7d-accepted')

    def assert_no_revival(self, delivery):
        delivery.refresh_from_db()
        before = D.objects.filter(pk=delivery.pk).values().get()
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        result = retry_due_customer_deliveries(now=self.clock.return_value + timedelta(days=1))
        self.assertEqual((result.sent, result.stale, result.errors), (0, 0, 0))
        self.assertEqual(self.prepare(delivery.purpose).pk, delivery.pk)
        self.assertEqual(recover_missing_reminder_deliveries(), 0)
        self.assertEqual(D.objects.filter(pk=delivery.pk).values().get(), before)
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()


class AppointmentsIdempotencyS7DTests(S7DFixture, TestCase):
    def test_retriable_retry_reuses_delivery_and_revalidates_canonical_access(self):
        for purpose in PURPOSES:
            with self.subTest(purpose=purpose):
                delivery = self.prepare(purpose)
                self.fail_retriably(delivery)
                with patch.object(deliveries, 'can_use_appointments_automations', wraps=can_use_appointments_automations) as gate:
                    self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
                    gate.assert_called_once()
                    self.assertEqual(gate.call_args.args[0].pk, self.biz.pk)
                delivery.refresh_from_db()
                self.assertEqual((delivery.status, delivery.attempt_count), (S.SENT, 2))
                self.assertIsNotNone(delivery.sent_at)
                self.assertIsNone(delivery.next_retry_at)
                self.provider.send.assert_called_once()
                self.assertEqual(self.provider.send.call_args.args[0].idempotency_key, delivery.idempotency_key)
                self.assertEqual(self.prepare(purpose).pk, delivery.pk)
                self.assertEqual(D.objects.filter(reminder=delivery.reminder, channel=delivery.channel).count(), 1)

    def test_entitlement_lost_before_retry_skips_without_consuming_attempt(self):
        for purpose in PURPOSES:
            with self.subTest(purpose=purpose):
                self.subscription_status('active')
                delivery = self.prepare(purpose)
                self.fail_retriably(delivery)
                last_attempt, failed_at = delivery.last_attempt_at, delivery.failed_at
                self.subscription_status('suspended')
                with patch.object(deliveries, 'can_use_appointments_automations', wraps=can_use_appointments_automations) as gate:
                    result = retry_due_customer_deliveries()
                    gate.assert_called_once()
                self.assertEqual((result.skipped, result.errors), (1, 0))
                delivery.refresh_from_db()
                self.assertEqual((delivery.status, delivery.attempt_count), (S.SKIPPED, 1))
                self.assertEqual(delivery.skip_reason, deliveries.SKIP_APPOINTMENTS_AUTOMATIONS)
                self.assertEqual(delivery.skipped_at, self.clock.return_value)
                self.assertEqual((delivery.last_attempt_at, delivery.failed_at), (last_attempt, failed_at))
                self.assertIsNone(delivery.next_retry_at)
                self.provider.send.assert_not_called()
                self.get_provider.assert_not_called()

    def test_reactivation_before_retry_allows_only_still_eligible_delivery(self):
        delivery = self.prepare()
        self.fail_retriably(delivery)
        self.subscription_status('suspended')
        self.subscription_status('active')
        self.assertEqual(retry_due_customer_deliveries().sent, 1)
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempt_count), (S.SENT, 2))
        self.provider.send.assert_called_once()

    def test_retry_not_due_does_not_consume_attempt(self):
        delivery = self.prepare()
        self.fail_retriably(delivery)
        self.clock.return_value -= timedelta(microseconds=1)
        self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempt_count), (S.FAILED, 1))
        self.provider.send.assert_not_called()

    def test_sent_never_revives_after_reactivation(self):
        delivery = self.prepare()
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
        self.subscription_status('suspended')
        self.subscription_status('active')
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        self.assert_no_revival(delivery)

    def test_skipped_never_revives_after_reactivation(self):
        delivery = self.prepare()
        self.subscription_status('suspended')
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SKIPPED)
        self.subscription_status('active')
        self.assert_no_revival(delivery)

    def test_terminal_failure_never_revives_after_reactivation(self):
        delivery = self.prepare()
        self.provider.send.return_value = ProviderSendResult.failure('rejected', retryable=False)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.FAILED)
        self.subscription_status('suspended')
        self.subscription_status('active')
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        self.assert_no_revival(delivery)

    @override_settings(CUSTOMER_DELIVERY_MAX_ATTEMPTS=1)
    def test_exhausted_retry_budget_is_terminal(self):
        delivery = self.prepare()
        self.provider.send.return_value = ProviderSendResult.failure('temporary', retryable=True)
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.FAILED)
        delivery.refresh_from_db()
        self.assertIsNone(delivery.next_retry_at)
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        self.assert_no_revival(delivery)

    def test_pending_recovery_revalidates_entitlement_before_provider(self):
        delivery = self.prepare()
        D.objects.filter(pk=delivery.pk).update(created_at=self.now - timedelta(minutes=5))
        self.subscription_status('suspended')
        with patch.object(deliveries, 'can_use_appointments_automations', wraps=can_use_appointments_automations) as gate:
            self.assertEqual(retry_due_customer_deliveries().skipped, 1)
            gate.assert_called_once()
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempt_count), (S.SKIPPED, 0))
        self.assertEqual(delivery.skip_reason, deliveries.SKIP_APPOINTMENTS_AUTOMATIONS)
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()

    def test_missing_delivery_recovery_is_idempotent_and_runtime_checks_again(self):
        CustomerReminder.objects.filter(business=self.biz).update(notified_at=self.now)
        with patch('apps.customers.tasks.execute_customer_delivery.delay') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(recover_missing_reminder_deliveries(), 2)
            self.assertEqual(enqueue.call_count, 2)
        self.assertEqual(recover_missing_reminder_deliveries(), 0)
        self.subscription_status('suspended')
        for delivery in D.objects.all():
            self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SKIPPED)
        self.assertEqual(D.objects.filter(status=S.SKIPPED, attempt_count=0).count(), 2)
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()

    def test_stale_processing_recovery_never_requeues_unknown_outcome(self):
        delivery = self.prepare()
        deliveries._claim(delivery.pk, self.provider, self.now)
        self.clock.return_value = self.now + processing_lease() + timedelta(seconds=1)
        self.subscription_status('suspended')
        result = retry_due_customer_deliveries()
        self.assertEqual((result.stale, result.due, result.errors), (1, 0, 0))
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.failure_code, delivery.attempt_count), (S.FAILED, 'outcome_unknown', 1))
        self.assertEqual(delivery.failed_at, self.clock.return_value)
        self.assertIsNone(delivery.next_retry_at)
        self.subscription_status('active')
        self.assert_no_revival(delivery)

    @override_settings(AWS_SES_FROM_EMAIL='sender@example.com')
    def test_ambiguous_ses_read_timeout_is_terminal_without_blind_retry(self):
        delivery = self.prepare()
        client = Mock()
        client.send_email.side_effect = ReadTimeoutError(endpoint_url='https://ses.example.invalid')
        self.assertEqual(execute_delivery(delivery.pk, provider=AmazonSESProvider(client=client)), S.FAILED)
        client.send_email.assert_called_once()
        delivery.refresh_from_db()
        self.assertEqual((delivery.failure_code, delivery.attempt_count), ('provider_exception', 1))
        self.assertIsNone(delivery.next_retry_at)
        self.assert_no_revival(delivery)
        client.send_email.assert_called_once()

    def test_provider_acceptance_then_database_failure_stays_fail_safe(self):
        delivery = self.prepare()
        with patch.object(deliveries, '_record_result', side_effect=DatabaseError('simulated write failure')):
            with self.assertRaises(DatabaseError):
                execute_customer_delivery.run(str(delivery.pk))
        self.provider.send.assert_called_once()
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempt_count), (S.PROCESSING, 1))
        self.clock.return_value = self.now + processing_lease() + timedelta(seconds=1)
        self.assertEqual(retry_due_customer_deliveries().stale, 1)
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        self.assert_no_revival(delivery)

    def test_prior_send_evidence_blocks_inconsistent_retry_candidate(self):
        for purpose, evidence in zip(PURPOSES, ({'sent_at': self.now}, {'provider_message_id': 'already-accepted'})):
            with self.subTest(evidence=evidence):
                delivery = self.prepare(purpose)
                self.fail_retriably(delivery)
                D.objects.filter(pk=delivery.pk).update(**evidence)
                self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
                delivery.refresh_from_db()
                self.assertEqual(delivery.attempt_count, 1)
                self.assertEqual((delivery.status, delivery.failure_code), (S.FAILED, 'prior_send_evidence'))
                self.assertIsNone(delivery.next_retry_at)
                for field, value in evidence.items():
                    self.assertEqual(getattr(delivery, field), value)
                self.provider.send.assert_not_called()
                self.get_provider.assert_not_called()

    def test_prior_send_evidence_also_blocks_pending_recovery(self):
        for purpose, evidence in zip(PURPOSES, ({'sent_at': self.now}, {'provider_message_id': 'already-accepted'})):
            with self.subTest(evidence=evidence):
                delivery = self.prepare(purpose)
                D.objects.filter(pk=delivery.pk).update(
                    created_at=self.now - timedelta(minutes=5), **evidence,
                )
                result = retry_due_customer_deliveries()
                self.assertEqual((result.sent, result.noop, result.errors), (0, 1, 0))
                delivery.refresh_from_db()
                self.assertEqual((delivery.status, delivery.failure_code, delivery.attempt_count), (S.FAILED, 'prior_send_evidence', 0))
                self.assertIsNone(delivery.next_retry_at)
                for field, value in evidence.items():
                    self.assertEqual(getattr(delivery, field), value)
                self.provider.send.assert_not_called()
                self.get_provider.assert_not_called()

    def test_database_unique_key_protects_same_automatic_event(self):
        for purpose in PURPOSES:
            with self.subTest(purpose=purpose):
                delivery = self.prepare(purpose)
                self.assertEqual(self.prepare(purpose).pk, delivery.pk)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    D.objects.create(
                        business=self.biz, customer=self.customer, appointment=delivery.appointment,
                        reminder=delivery.reminder, channel=delivery.channel, purpose=delivery.purpose,
                        destination_snapshot=delivery.destination_snapshot,
                        idempotency_key=delivery_idempotency_key(delivery.reminder),
                    )
                self.assertEqual(D.objects.filter(reminder=delivery.reminder).count(), 1)


class AppointmentsConcurrencyS7DTests(S7DFixture, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def worker(self, action):
        try:
            return action()
        finally:
            connections.close_all()

    def race_execution(self, *, during_claim=False, retry=False):
        delivery = self.prepare()
        if retry:
            self.fail_retriably(delivery)
        entered, release = threading.Event(), threading.Event()
        real_gate = deliveries._gate

        def wait():
            entered.set()
            if not release.wait(10):
                raise TimeoutError('S7D worker was not released')

        def slow_gate(customer, channel):
            wait()
            return real_gate(customer, channel)

        def slow_send(message):
            wait()
            return ProviderSendResult.ok('s7d-once')

        self.provider.send.side_effect = None if during_claim else slow_send
        with patch.object(deliveries, '_gate', side_effect=slow_gate if during_claim else real_gate):
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(self.worker, lambda: execute_customer_delivery.run(str(delivery.pk)))
                try:
                    self.assertTrue(entered.wait(10))
                    self.assertIsNone(execute_customer_delivery.run(str(delivery.pk)))
                    if not during_claim:
                        delivery.refresh_from_db()
                        self.assertEqual((delivery.status, delivery.attempt_count), (S.PROCESSING, 2 if retry else 1))
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=10), S.SENT)
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempt_count), (S.SENT, 2 if retry else 1))
        self.provider.send.assert_called_once()
        self.get_provider.assert_called_once()
        self.assertEqual(D.objects.count(), 1)

    def test_two_workers_claim_same_pending_only_one_sends(self):
        self.race_execution(during_claim=True)

    def test_second_worker_sees_committed_processing_without_new_attempt(self):
        self.race_execution()

    def test_two_workers_claim_same_retry_only_one_consumes_attempt(self):
        self.race_execution(during_claim=True, retry=True)

    def test_two_workers_prepare_same_automatic_event_enqueue_once(self):
        real_context = deliveries.build_delivery_context
        for purpose in PURPOSES:
            with self.subTest(purpose=purpose):
                barrier = threading.Barrier(2)

                def concurrent_context(*args, **kwargs):
                    context = real_context(*args, **kwargs)
                    barrier.wait(timeout=10)
                    return context

                with patch.object(deliveries, 'build_delivery_context', side_effect=concurrent_context):
                    with patch('apps.customers.tasks.execute_customer_delivery.delay') as enqueue:
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [pool.submit(self.worker, lambda: self.prepare(purpose, enqueue=True)) for _ in range(2)]
                            deliveries_created = [future.result(timeout=15) for future in futures]
                        self.assertEqual(deliveries_created[0].pk, deliveries_created[1].pk)
                        enqueue.assert_called_once_with(str(deliveries_created[0].pk))
                self.assertEqual(D.objects.filter(reminder=self.reminders[purpose]).count(), 1)

    def test_late_worker_result_after_recovery_cannot_revive_delivery(self):
        delivery = self.prepare()
        entered, release = threading.Event(), threading.Event()

        def late_success(message):
            entered.set()
            if not release.wait(10):
                raise TimeoutError('S7D worker was not released')
            return ProviderSendResult.ok('accepted-but-late')

        self.provider.send.side_effect = late_success
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.worker, lambda: execute_customer_delivery.run(str(delivery.pk)))
            try:
                self.assertTrue(entered.wait(10))
                self.clock.return_value = self.now + processing_lease() + timedelta(seconds=1)
                self.assertEqual(retry_due_customer_deliveries().stale, 1)
            finally:
                release.set()
            self.assertIsNone(first.result(timeout=10))
        self.provider.send.assert_called_once()
        self.provider.send.reset_mock()
        self.get_provider.reset_mock()
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.failure_code, delivery.attempt_count), (S.FAILED, 'outcome_unknown', 1))
        self.assert_no_revival(delivery)

    def test_outer_transaction_cannot_roll_back_claim_after_provider_send(self):
        delivery = self.prepare()
        with transaction.atomic():
            with self.assertRaisesRegex(RuntimeError, 'durable'):
                execute_customer_delivery.run(str(delivery.pk))
            transaction.set_rollback(True)
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempt_count), (S.PENDING, 0))
        self.provider.send.assert_not_called()
        self.get_provider.assert_not_called()
        self.assertEqual(execute_customer_delivery.run(str(delivery.pk)), S.SENT)
        self.provider.send.assert_called_once()
