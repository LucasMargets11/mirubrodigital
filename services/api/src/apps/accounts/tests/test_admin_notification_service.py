"""
Tests for admin_notification_service.create_admin_notification().

Covers:
  1.  Returns AdminNotification instance on success
  2.  Saves notif_type correctly
  3.  Saves title correctly
  4.  Saves severity correctly
  5.  Saves message correctly
  6.  Saves target_role correctly
  7.  Saves target_user correctly
  8.  Saves business correctly
  9.  Saves related_object_type correctly
  10. Saves related_object_id correctly
  11. Saves action_url correctly
  12. Saves custom metadata
  13. Strips sensitive keys from metadata (all 9 keys)
  14. Leaves non-sensitive metadata keys intact
  15. Dedupe within window returns None (no new record)
  16. Dedupe after window expiry creates a new record
  17. Dedupe skips if prior record is resolved (creates new)
  18. Dedupe skips if prior record is archived (creates new)
  19. No dedupe when related_object_id is empty
  20. No dedupe when dedupe_window_seconds is None
  21. Exception inside save() returns None (does not raise)
  22. Exception is logged (logger.error called)
  23. No send_mail or EmailMessage usage in service module
"""
import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.admin_notification import AdminNotification
from apps.accounts.admin_notification_service import create_admin_notification
from apps.business.models import Business

User = get_user_model()


def _create_business(name='Test Business'):
    b = Business(
        name=name,
        slug=name.lower().replace(' ', '-'),
        default_service='gestion',
    )
    b.save()
    return b


class CreateAdminNotificationBasicTests(TestCase):

    def test_returns_admin_notification_instance(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Hello',
        )
        self.assertIsInstance(result, AdminNotification)

    def test_saves_notif_type(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.BILLING_PAYMENT_FAILED,
            title='Payment failed',
        )
        self.assertEqual(result.notif_type, 'billing_payment_failed')

    def test_saves_title(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Custom title',
        )
        self.assertEqual(result.title, 'Custom title')

    def test_saves_severity(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_ERROR,
            title='Error',
            severity=AdminNotification.Severity.CRITICAL,
        )
        self.assertEqual(result.severity, 'critical')

    def test_saves_message(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Info',
            message='Detailed message here.',
        )
        self.assertEqual(result.message, 'Detailed message here.')

    def test_saves_target_role(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Role-targeted',
            target_role='superadmin',
        )
        self.assertEqual(result.target_role, 'superadmin')

    def test_saves_target_user(self):
        user = User.objects.create_user(
            username='staff@mirubro.com',
            email='staff@mirubro.com',
            password='Secret123!',
        )
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='User-targeted',
            target_user=user,
        )
        self.assertEqual(result.target_user_id, user.pk)

    def test_saves_business(self):
        biz = _create_business()
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.BILLING_TRIAL_ENDING,
            title='Trial ending',
            business=biz,
        )
        self.assertEqual(result.business_id, biz.pk)

    def test_saves_related_object_type(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SUPPORT_TICKET_CREATED,
            title='Ticket created',
            related_object_type='support_ticket',
            related_object_id='abc-123',
        )
        self.assertEqual(result.related_object_type, 'support_ticket')

    def test_saves_related_object_id(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SUPPORT_TICKET_CREATED,
            title='Ticket created',
            related_object_type='support_ticket',
            related_object_id='abc-123',
        )
        self.assertEqual(result.related_object_id, 'abc-123')

    def test_saves_action_url(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Click me',
            action_url='/admin/support/TK-0001/',
        )
        self.assertEqual(result.action_url, '/admin/support/TK-0001/')

    def test_saves_custom_metadata(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='With meta',
            metadata={'source': 'webhook', 'amount': 9900},
        )
        self.assertEqual(result.metadata['source'], 'webhook')
        self.assertEqual(result.metadata['amount'], 9900)


class CreateAdminNotificationMetadataSanitizationTests(TestCase):

    SENSITIVE_KEYS = [
        'token', 'password', 'pin', 'secret',
        'authorization', 'x_signature', 'raw_payload_json',
        'headers', 'access_token', 'refresh_token',
    ]

    def test_strips_all_sensitive_keys(self):
        dirty_metadata = {k: 'should_be_removed' for k in self.SENSITIVE_KEYS}
        dirty_metadata['safe_key'] = 'keep_me'

        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Sanitization test',
            metadata=dirty_metadata,
        )

        for key in self.SENSITIVE_KEYS:
            self.assertNotIn(key, result.metadata, f'Key "{key}" should have been stripped')

    def test_leaves_non_sensitive_keys(self):
        result = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Keep safe',
            metadata={'safe_key': 'keep_me', 'amount': 100},
        )
        self.assertIn('safe_key', result.metadata)
        self.assertIn('amount', result.metadata)


class CreateAdminNotificationDedupeTests(TestCase):

    def test_dedupe_within_window_returns_none(self):
        # First call: creates
        first = create_admin_notification(
            notif_type=AdminNotification.NotifType.BILLING_PAYMENT_FAILED,
            title='Payment failed',
            related_object_type='subscription',
            related_object_id='sub-001',
            dedupe_window_seconds=3600,
        )
        self.assertIsNotNone(first)

        # Second call within window: should be suppressed
        duplicate = create_admin_notification(
            notif_type=AdminNotification.NotifType.BILLING_PAYMENT_FAILED,
            title='Payment failed again',
            related_object_type='subscription',
            related_object_id='sub-001',
            dedupe_window_seconds=3600,
        )
        self.assertIsNone(duplicate)
        # Only 1 record in DB
        self.assertEqual(AdminNotification.objects.count(), 1)

    def test_dedupe_after_window_creates_new(self):
        # Create a notification with an artificially old created_at
        first = create_admin_notification(
            notif_type=AdminNotification.NotifType.BILLING_PAYMENT_FAILED,
            title='Old failure',
            related_object_type='subscription',
            related_object_id='sub-002',
            dedupe_window_seconds=3600,
        )
        # Backdate the first record to be outside the window
        AdminNotification.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timezone.timedelta(seconds=7200)
        )

        # Second call: window has expired, should create
        second = create_admin_notification(
            notif_type=AdminNotification.NotifType.BILLING_PAYMENT_FAILED,
            title='New failure',
            related_object_type='subscription',
            related_object_id='sub-002',
            dedupe_window_seconds=3600,
        )
        self.assertIsNotNone(second)
        self.assertEqual(AdminNotification.objects.count(), 2)

    def test_dedupe_skipped_if_prior_resolved(self):
        first = create_admin_notification(
            notif_type=AdminNotification.NotifType.SUPPORT_TICKET_OVERDUE,
            title='Overdue',
            related_object_type='ticket',
            related_object_id='tk-100',
            dedupe_window_seconds=3600,
        )
        first.mark_resolved()

        # Prior is resolved → not in [unread, read] → should create new
        second = create_admin_notification(
            notif_type=AdminNotification.NotifType.SUPPORT_TICKET_OVERDUE,
            title='Overdue again',
            related_object_type='ticket',
            related_object_id='tk-100',
            dedupe_window_seconds=3600,
        )
        self.assertIsNotNone(second)
        self.assertEqual(AdminNotification.objects.count(), 2)

    def test_dedupe_skipped_if_prior_archived(self):
        first = create_admin_notification(
            notif_type=AdminNotification.NotifType.SUPPORT_TICKET_OVERDUE,
            title='Overdue',
            related_object_type='ticket',
            related_object_id='tk-200',
            dedupe_window_seconds=3600,
        )
        first.mark_archived()

        second = create_admin_notification(
            notif_type=AdminNotification.NotifType.SUPPORT_TICKET_OVERDUE,
            title='Overdue again',
            related_object_type='ticket',
            related_object_id='tk-200',
            dedupe_window_seconds=3600,
        )
        self.assertIsNotNone(second)
        self.assertEqual(AdminNotification.objects.count(), 2)

    def test_no_dedupe_without_related_object_id(self):
        first = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Info',
            related_object_type='',
            related_object_id='',
            dedupe_window_seconds=3600,
        )
        second = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Info again',
            related_object_type='',
            related_object_id='',
            dedupe_window_seconds=3600,
        )
        # Both should be created when related_object_id is empty
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(AdminNotification.objects.count(), 2)

    def test_no_dedupe_without_dedupe_window_seconds(self):
        first = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='First',
            related_object_type='ticket',
            related_object_id='tk-300',
        )
        second = create_admin_notification(
            notif_type=AdminNotification.NotifType.SYSTEM_INFO,
            title='Second',
            related_object_type='ticket',
            related_object_id='tk-300',
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(AdminNotification.objects.count(), 2)


class CreateAdminNotificationErrorHandlingTests(TestCase):

    def test_exception_returns_none_does_not_raise(self):
        with patch(
            'apps.accounts.admin_notification.AdminNotification.save',
            side_effect=Exception('DB is down'),
        ):
            result = create_admin_notification(
                notif_type=AdminNotification.NotifType.SYSTEM_ERROR,
                title='Broken',
            )
        self.assertIsNone(result)

    def test_exception_is_logged(self):
        with patch(
            'apps.accounts.admin_notification.AdminNotification.save',
            side_effect=Exception('DB error'),
        ):
            with self.assertLogs('apps.accounts.admin_notification_service', level=logging.ERROR) as log:
                create_admin_notification(
                    notif_type=AdminNotification.NotifType.SYSTEM_ERROR,
                    title='Broken',
                )
        self.assertTrue(
            any('create_admin_notification failed' in msg for msg in log.output),
            'Expected error log message not found',
        )


class CreateAdminNotificationNoEmailTests(TestCase):
    """Verify no email-sending code is invoked."""

    def test_no_send_mail_called(self):
        with patch('django.core.mail.send_mail') as mock_send:
            create_admin_notification(
                notif_type=AdminNotification.NotifType.SYSTEM_INFO,
                title='No email test',
            )
            mock_send.assert_not_called()
