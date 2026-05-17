"""
Tests for the AdminNotification model.

Covers:
  1.  Instance creation with required fields only
  2.  Auto-assigned UUID primary key
  3.  Default status = unread
  4.  Default severity = info
  5.  Default metadata = {}
  6.  Default message = ''
  7.  Default target_role = ''
  8.  Default action_url = ''
  9.  Default dedupe_key = ''
  10. Nullable FK: business can be None
  11. Nullable FK: target_user can be None
  12. __str__ representation
  13. Ordering: newer records come first
  14. All NotifType choices are valid
  15. All Severity choices are valid
  16. All Status choices are valid
  17. Meta.indexes defines 4 named indexes
  18. mark_read: unread → read, sets read_at
  19. mark_read is idempotent (calling twice doesn't change read_at)
  20. mark_resolved: unread → resolved, sets resolved_at
  21. mark_resolved: read → resolved, sets resolved_at
  22. mark_resolved is idempotent
  23. mark_archived: any status → archived, sets archived_at
  24. mark_archived is idempotent
"""
import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.admin_notification import AdminNotification

User = get_user_model()


def _make_notification(**kwargs):
    """Return an unsaved AdminNotification with mandatory fields pre-set."""
    defaults = {
        'notif_type': AdminNotification.NotifType.SYSTEM_INFO,
        'title': 'Test notification',
    }
    defaults.update(kwargs)
    return AdminNotification(**defaults)


class AdminNotificationCreationTests(TestCase):

    def test_create_with_required_fields(self):
        n = _make_notification()
        n.save()
        self.assertIsNotNone(n.pk)

    def test_uuid_primary_key(self):
        n = _make_notification()
        n.save()
        # pk is a UUID: str representation has 32 hex chars + 4 dashes = 36 chars
        self.assertEqual(len(str(n.pk)), 36)

    def test_default_status_unread(self):
        n = _make_notification()
        n.save()
        self.assertEqual(n.status, AdminNotification.Status.UNREAD)

    def test_default_severity_info(self):
        n = _make_notification()
        n.save()
        self.assertEqual(n.severity, AdminNotification.Severity.INFO)

    def test_default_metadata_empty_dict(self):
        n = _make_notification()
        n.save()
        self.assertEqual(n.metadata, {})

    def test_default_message_empty_string(self):
        n = _make_notification()
        n.save()
        self.assertEqual(n.message, '')

    def test_default_target_role_empty(self):
        n = _make_notification()
        n.save()
        self.assertEqual(n.target_role, '')

    def test_default_action_url_empty(self):
        n = _make_notification()
        n.save()
        self.assertEqual(n.action_url, '')

    def test_default_dedupe_key_empty(self):
        n = _make_notification()
        n.save()
        self.assertEqual(n.dedupe_key, '')

    def test_business_nullable(self):
        n = _make_notification(business=None)
        n.save()
        self.assertIsNone(n.business)

    def test_target_user_nullable(self):
        n = _make_notification(target_user=None)
        n.save()
        self.assertIsNone(n.target_user)

    def test_str_representation(self):
        n = _make_notification(
            notif_type=AdminNotification.NotifType.BILLING_PAYMENT_FAILED,
            severity=AdminNotification.Severity.CRITICAL,
        )
        n.save()
        result = str(n)
        self.assertIn('billing_payment_failed', result)
        self.assertIn('critical', result)
        self.assertIn('unread', result)


class AdminNotificationOrderingTests(TestCase):

    def test_ordering_newest_first(self):
        n1 = _make_notification(title='first')
        n1.save()
        # Ensure distinct created_at values
        time.sleep(0.01)
        n2 = _make_notification(title='second')
        n2.save()

        pks = list(AdminNotification.objects.values_list('pk', flat=True))
        self.assertEqual(pks[0], n2.pk, 'Newer record should come first')


class AdminNotificationChoicesTests(TestCase):

    def test_all_notif_types_are_valid(self):
        valid_values = {choice[0] for choice in AdminNotification.NotifType.choices}
        expected = {
            'support_ticket_created', 'support_ticket_replied',
            'support_ticket_escalated', 'support_ticket_overdue',
            'billing_payment_failed', 'billing_trial_ending',
            'billing_subscription_canceled', 'billing_subscription_created',
            'review_reported', 'review_response_pending',
            'security_admin_login_failed', 'security_mfa_disabled',
            'security_suspicious_auth', 'security_multiple_failures',
            'system_error', 'system_info',
        }
        self.assertEqual(valid_values, expected)

    def test_all_severity_values(self):
        valid_values = {c[0] for c in AdminNotification.Severity.choices}
        self.assertEqual(valid_values, {'info', 'success', 'warning', 'critical'})

    def test_all_status_values(self):
        valid_values = {c[0] for c in AdminNotification.Status.choices}
        self.assertEqual(valid_values, {'unread', 'read', 'resolved', 'archived'})


class AdminNotificationMetaIndexesTests(TestCase):

    def test_four_named_indexes_exist(self):
        index_names = {idx.name for idx in AdminNotification._meta.indexes}
        self.assertIn('adminnotif_status_ts_idx', index_names)
        self.assertIn('adminnotif_role_ts_idx', index_names)
        self.assertIn('adminnotif_business_ts_idx', index_names)
        self.assertIn('adminnotif_related_idx', index_names)
        self.assertEqual(len(AdminNotification._meta.indexes), 4)


class AdminNotificationMarkReadTests(TestCase):

    def setUp(self):
        self.n = _make_notification()
        self.n.save()

    def test_mark_read_transitions_unread_to_read(self):
        self.n.mark_read()
        self.n.refresh_from_db()
        self.assertEqual(self.n.status, AdminNotification.Status.READ)

    def test_mark_read_sets_read_at(self):
        before = timezone.now()
        self.n.mark_read()
        self.n.refresh_from_db()
        self.assertIsNotNone(self.n.read_at)
        self.assertGreaterEqual(self.n.read_at, before)

    def test_mark_read_idempotent(self):
        self.n.mark_read()
        first_read_at = self.n.read_at
        self.n.mark_read()
        self.assertEqual(self.n.read_at, first_read_at)
        self.assertEqual(self.n.status, AdminNotification.Status.READ)


class AdminNotificationMarkResolvedTests(TestCase):

    def test_mark_resolved_from_unread(self):
        n = _make_notification()
        n.save()
        n.mark_resolved()
        n.refresh_from_db()
        self.assertEqual(n.status, AdminNotification.Status.RESOLVED)
        self.assertIsNotNone(n.resolved_at)

    def test_mark_resolved_from_read(self):
        n = _make_notification()
        n.save()
        n.mark_read()
        n.mark_resolved()
        n.refresh_from_db()
        self.assertEqual(n.status, AdminNotification.Status.RESOLVED)
        self.assertIsNotNone(n.resolved_at)

    def test_mark_resolved_idempotent(self):
        n = _make_notification()
        n.save()
        n.mark_resolved()
        first_resolved_at = n.resolved_at
        n.mark_resolved()
        self.assertEqual(n.resolved_at, first_resolved_at)
        self.assertEqual(n.status, AdminNotification.Status.RESOLVED)

    def test_mark_resolved_does_not_change_already_archived(self):
        n = _make_notification()
        n.save()
        n.mark_archived()
        n.mark_resolved()
        n.refresh_from_db()
        # archived takes precedence; resolved won't override
        self.assertEqual(n.status, AdminNotification.Status.ARCHIVED)


class AdminNotificationMarkArchivedTests(TestCase):

    def test_mark_archived_from_unread(self):
        n = _make_notification()
        n.save()
        n.mark_archived()
        n.refresh_from_db()
        self.assertEqual(n.status, AdminNotification.Status.ARCHIVED)
        self.assertIsNotNone(n.archived_at)

    def test_mark_archived_from_resolved(self):
        n = _make_notification()
        n.save()
        n.mark_resolved()
        n.mark_archived()
        n.refresh_from_db()
        self.assertEqual(n.status, AdminNotification.Status.ARCHIVED)

    def test_mark_archived_idempotent(self):
        n = _make_notification()
        n.save()
        n.mark_archived()
        first_archived_at = n.archived_at
        n.mark_archived()
        self.assertEqual(n.archived_at, first_archived_at)
        self.assertEqual(n.status, AdminNotification.Status.ARCHIVED)
