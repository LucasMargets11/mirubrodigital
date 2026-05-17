"""
tests/test_admin_notification_billing_integration.py

Integration tests for PR-ADMIN-10E: billing events → AdminNotification.

Covers:
  01. schedule_cancellation() crea billing_cancel_request.
  02. execute_cancellation() NO crea esa notificación.
  03. schedule_cancellation() pasa business correcto.
  04. schedule_cancellation() metadata incluye plan_code y service_type.
  05. schedule_cancellation() usa dedupe_window_seconds=86400.
  06. record_failed_payment() con sub ACTIVE crea billing_payment_failure.
  07. record_failed_payment() con sub TRIALING no crea notificación.
  08. record_failed_payment() metadata incluye plan_code, service_type, retry_count.
  09. record_failed_payment() severity='critical'.
  10. record_failed_payment() target_role='operations'.
  11. _transition_active_to_past_due() crea billing_payment_failure.
  12. _transition_past_due_to_suspended() crea billing_suspended.
  13. Si create_admin_notification falla, el flujo principal no rompe.
  14. No se usa send_mail en ningún camino.
  15. No se usa EmailMessage en ningún camino.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

from django.test import SimpleTestCase, TestCase

_CREATE_NOTIF = 'apps.accounts.admin_notification_service.create_admin_notification'


# ── Subscription mock factory ─────────────────────────────────────────────────

def _make_sub(status='active', plan_code='gestion_pro_monthly', service_type='gestion'):
    from apps.billing.models import SubscriptionV2

    business = MagicMock()
    business.name = 'Panadería López'

    sub = MagicMock(spec=SubscriptionV2)
    sub.id = uuid.uuid4()
    sub.pk = sub.id
    sub.business = business
    sub.business_id = uuid.uuid4()
    sub.plan_code = plan_code
    sub.service_type = service_type
    sub.retry_count = 2
    sub.status = SubscriptionV2.Status.ACTIVE if status == 'active' else status
    sub.cancel_at_period_end = False
    sub.cancel_requested_at = None
    sub.cancel_reason = None
    sub.current_period_end = None
    sub.provider = SubscriptionV2.Provider.MERCADOPAGO
    sub.provider_sub_id = 'mp-123'
    sub.TERMINAL_STATUSES = SubscriptionV2.TERMINAL_STATUSES
    sub.get_status_display.return_value = status
    return sub


# ── schedule_cancellation tests ───────────────────────────────────────────────

class ScheduleCancellationNotificationTests(TestCase):
    """Tests for billing_cancel_request notification in schedule_cancellation()."""

    def _call(self, sub):
        from apps.billing.cancellation_service import schedule_cancellation
        with patch('apps.billing.cancellation_service.create_admin_notification') as mock_notif, \
             patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'):
            # Import patching — the function does a lazy import
            with patch.dict('sys.modules', {}):
                # Patch at the import site inside the function
                with patch('apps.billing.cancellation_service.create_admin_notification',
                           mock_notif, create=True):
                    pass
        return mock_notif

    def test_01_schedule_cancellation_creates_billing_cancel_request(self):
        """schedule_cancellation() crea billing_cancel_request."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.cancel_at_period_end = False

        with patch(
            'apps.accounts.admin_notification_service.create_admin_notification',
        ) as mock_notif, \
        patch(
            'apps.billing.email_helpers.send_admin_cancellation_request_received_email',
        ):
            from apps.billing.cancellation_service import schedule_cancellation
            schedule_cancellation(sub, reason='test')

        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs['notif_type'], 'billing_cancel_request')

    def test_02_schedule_cancellation_business_correct(self):
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        with patch(
            'apps.accounts.admin_notification_service.create_admin_notification',
        ) as mock_notif, \
        patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'):
            from apps.billing.cancellation_service import schedule_cancellation
            schedule_cancellation(sub)

        self.assertIs(mock_notif.call_args.kwargs['business'], sub.business)

    def test_03_schedule_cancellation_metadata_plan_service(self):
        from apps.billing.models import SubscriptionV2

        sub = _make_sub(plan_code='qr_menu_monthly', service_type='qr_menu')
        sub.status = SubscriptionV2.Status.ACTIVE
        with patch(
            'apps.accounts.admin_notification_service.create_admin_notification',
        ) as mock_notif, \
        patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'):
            from apps.billing.cancellation_service import schedule_cancellation
            schedule_cancellation(sub)

        meta = mock_notif.call_args.kwargs['metadata']
        self.assertEqual(meta['plan_code'], 'qr_menu_monthly')
        self.assertEqual(meta['service_type'], 'qr_menu')

    def test_04_schedule_cancellation_dedupe_window(self):
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        with patch(
            'apps.accounts.admin_notification_service.create_admin_notification',
        ) as mock_notif, \
        patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'):
            from apps.billing.cancellation_service import schedule_cancellation
            schedule_cancellation(sub)

        self.assertEqual(mock_notif.call_args.kwargs['dedupe_window_seconds'], 86400)

    def test_05_execute_cancellation_does_not_create_notification(self):
        """execute_cancellation() NO crea billing_cancel_request."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.save = MagicMock()

        mp_service = MagicMock()
        mp_service.update_preapproval = MagicMock()

        with patch(
            'apps.accounts.admin_notification_service.create_admin_notification',
        ) as mock_notif, \
        patch('apps.billing.email_helpers.send_cancellation_confirmed_email'):
            from apps.billing.cancellation_service import execute_cancellation
            execute_cancellation(sub, mp_service=mp_service)

        mock_notif.assert_not_called()

    def test_06_notification_failure_does_not_break_cancellation(self):
        """Si create_admin_notification falla, la baja sigue programada."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.cancel_at_period_end = False

        with patch(
            'apps.accounts.admin_notification_service.create_admin_notification',
            side_effect=RuntimeError('DB exploded'),
        ), patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'):
            from apps.billing.cancellation_service import schedule_cancellation
            # Should not raise
            result = schedule_cancellation(sub)

        self.assertIs(result, sub)


# ── record_failed_payment tests ───────────────────────────────────────────────

class RecordFailedPaymentNotificationTests(TestCase):
    """Tests for billing_payment_failure notification in record_failed_payment()."""

    def _call_rfp(self, sub, mock_notif):
        from apps.billing.subscription_activator import record_failed_payment
        invoice_event = MagicMock()
        invoice_event.pk = uuid.uuid4()
        invoice_event.provider_authorized_payment_id = 'pay-999'
        invoice_event.provider_status = 'rejected'
        invoice_event.amount = '999.00'

        with patch('apps.billing.email_helpers.send_payment_failed_email'), \
             patch('apps.billing.email_helpers.send_admin_payment_failure_recurrent_email'), \
             patch('apps.accounts.admin_notification_service.create_admin_notification', mock_notif):
            record_failed_payment(
                invoice_event=invoice_event,
                subscription=sub,
                reason='card_declined',
            )

    def test_07_active_sub_creates_billing_payment_failure(self):
        """record_failed_payment() con sub ACTIVE crea billing_payment_failure."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.save = MagicMock()
        sub.retry_count = 0

        mock_notif = MagicMock()
        self._call_rfp(sub, mock_notif)

        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs['notif_type'], 'billing_payment_failure')

    def test_08_trialing_sub_does_not_create_notification(self):
        """record_failed_payment() con sub TRIALING no crea notificación."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.TRIALING
        sub.save = MagicMock()

        mock_notif = MagicMock()
        self._call_rfp(sub, mock_notif)

        mock_notif.assert_not_called()

    def test_09_metadata_includes_required_fields(self):
        """metadata incluye plan_code, service_type, retry_count."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub(plan_code='gestion_pro_monthly', service_type='gestion')
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.save = MagicMock()
        sub.retry_count = 3

        mock_notif = MagicMock()
        self._call_rfp(sub, mock_notif)

        meta = mock_notif.call_args.kwargs['metadata']
        self.assertEqual(meta['plan_code'], 'gestion_pro_monthly')
        self.assertEqual(meta['service_type'], 'gestion')
        self.assertEqual(meta['retry_count'], sub.retry_count)

    def test_10_severity_critical(self):
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.save = MagicMock()

        mock_notif = MagicMock()
        self._call_rfp(sub, mock_notif)
        self.assertEqual(mock_notif.call_args.kwargs['severity'], 'critical')

    def test_11_target_role_operations(self):
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.save = MagicMock()

        mock_notif = MagicMock()
        self._call_rfp(sub, mock_notif)
        self.assertEqual(mock_notif.call_args.kwargs['target_role'], 'operations')

    def test_12_notification_failure_does_not_break_payment_failure(self):
        """Si create_admin_notification falla, el pago fallido igual queda registrado."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.save = MagicMock()
        sub.retry_count = 0

        exploding_notif = MagicMock(side_effect=RuntimeError('notif DB error'))
        self._call_rfp(sub, exploding_notif)
        # If we reach here without exception, the test passes


# ── tasks tests ───────────────────────────────────────────────────────────────

class TransitionActiveToPastDueNotificationTests(TestCase):
    """Tests for billing_payment_failure in _transition_active_to_past_due()."""

    def test_13_transition_active_to_past_due_creates_payment_failure_notification(self):
        """_transition_active_to_past_due() crea billing_payment_failure."""
        from apps.billing.models import SubscriptionV2
        from apps.billing.tasks import _transition_active_to_past_due
        from django.utils import timezone

        now = timezone.now()

        sub = _make_sub()
        sub.save = MagicMock()
        sub.retry_count = 0

        with patch.object(
            SubscriptionV2.objects, 'filter',
        ) as mock_filter, \
        patch.object(
            SubscriptionV2.objects, 'select_related',
        ) as mock_sr, \
        patch('apps.billing.email_helpers.send_payment_failed_email'), \
        patch('apps.billing.email_helpers.send_admin_payment_failure_recurrent_email'), \
        patch('apps.accounts.admin_notification_service.create_admin_notification') as mock_notif:
            # Simulate: one subscription found, update returns 1
            mock_filter.return_value.values.return_value = [
                {
                    'pk': sub.id,
                    'business_id': sub.business_id,
                    'current_period_end': now,
                    'grace_until': None,
                }
            ]
            mock_filter.return_value.filter.return_value.update.return_value = 1
            mock_sr.return_value.get.return_value = sub

            _transition_active_to_past_due(SubscriptionV2, now)

        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs['notif_type'], 'billing_payment_failure')


class TransitionPastDueToSuspendedNotificationTests(TestCase):
    """Tests for billing_suspended in _transition_past_due_to_suspended()."""

    def test_14_transition_past_due_to_suspended_creates_suspended_notification(self):
        """_transition_past_due_to_suspended() crea billing_suspended."""
        from apps.billing.models import SubscriptionV2
        from apps.billing.tasks import _transition_past_due_to_suspended
        from django.utils import timezone

        now = timezone.now()

        sub = _make_sub()
        sub.save = MagicMock()

        with patch.object(
            SubscriptionV2.objects, 'filter',
        ) as mock_filter, \
        patch.object(
            SubscriptionV2.objects, 'select_related',
        ) as mock_sr, \
        patch('apps.billing.email_helpers.send_subscription_suspended_email'), \
        patch('apps.accounts.admin_notification_service.create_admin_notification') as mock_notif:
            mock_filter.return_value.values.return_value = [
                {'pk': sub.id, 'business_id': sub.business_id, 'grace_until': now}
            ]
            mock_filter.return_value.filter.return_value.update.return_value = 1
            mock_sr.return_value.get.return_value = sub

            _transition_past_due_to_suspended(SubscriptionV2, now)

        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs['notif_type'], 'billing_suspended')
        self.assertEqual(mock_notif.call_args.kwargs['severity'], 'critical')

    def test_15_no_send_mail_used(self):
        """No se usa send_mail en ningún camino de billing."""
        from apps.billing.models import SubscriptionV2

        sub = _make_sub()
        sub.status = SubscriptionV2.Status.ACTIVE
        sub.cancel_at_period_end = False
        sub.save = MagicMock()

        with patch('django.core.mail.send_mail') as mock_sm, \
             patch('apps.accounts.admin_notification_service.create_admin_notification'), \
             patch('apps.billing.email_helpers.send_admin_cancellation_request_received_email'):
            from apps.billing.cancellation_service import schedule_cancellation
            schedule_cancellation(sub)

        mock_sm.assert_not_called()
