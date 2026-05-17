"""
Tests for platform admin notification endpoints.

Covers:
  Auth / permissions
  1.  Unauthenticated user gets 401/403.
  2.  Non-platform-staff user gets 403.
  3.  Superadmin can list all notifications.
  4.  Operations sees target_role="operations" and own target_user.
  5.  Support agent sees target_role="support_agent" and own target_user.
  6.  Content admin sees target_role="content_admin" and own target_user.
  7.  Operations does NOT see support_agent notifications.
  8.  Support agent does NOT see operations notifications.

  List
  9.  Default list excludes archived.
  10. list with status=archived includes archived.
  11. Results ordered by created_at DESC.
  12. Filter by status=unread.
  13. Filter by severity=critical.
  14. Filter by type.
  15. Invalid status returns 400.
  16. Invalid severity returns 400.
  17. Invalid type returns 400.
  18. Response includes business_name.
  19. Response does NOT include metadata.
  20. Response does NOT include dedupe_key.
  21. Pagination response includes total, page, page_size, total_pages.

  Unread count
  22. Counts only visible unread notifications.
  23. critical_count counts critical+unread only.
  24. Excludes read/resolved/archived from count.

  Mark read
  25. POST read changes unread → read.
  26. POST read sets read_at.
  27. POST read is idempotent (second call returns 200 unchanged).
  28. User outside scope gets 404.

  Archive
  29. POST archive changes status → archived.
  30. POST archive sets archived_at.
  31. POST archive is idempotent.
  32. User outside scope gets 404.

  Resolve
  33. POST resolve changes unread → resolved.
  34. POST resolve sets resolved_at.
  35. POST resolve on unread also sets read_at.
  36. POST resolve is idempotent.
  37. User outside scope gets 404.

  Security / email
  38. No send_mail called during any endpoint.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.admin_notification import AdminNotification
from apps.accounts.models import AccountProfile
from apps.business.models import Business

User = get_user_model()

LIST_URL           = '/api/v1/platform-admin/notifications/'
UNREAD_COUNT_URL   = '/api/v1/platform-admin/notifications/unread-count/'
READ_URL           = '/api/v1/platform-admin/notifications/{}/read/'
ARCHIVE_URL        = '/api/v1/platform-admin/notifications/{}/archive/'
RESOLVE_URL        = '/api/v1/platform-admin/notifications/{}/resolve/'


# ── Test factories ────────────────────────────────────────────────────────────

def _create_staff(email, role='superadmin', password='SecurePass123!'):
    user = User.objects.create_user(username=email, email=email, password=password)
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.is_platform_staff = True
    profile.internal_role = role
    profile.save()
    user.refresh_from_db()
    return user


def _create_regular_user(email='regular@example.com'):
    user = User.objects.create_user(username=email, email=email, password='Pass123!')
    AccountProfile.objects.get_or_create(user=user)
    return user


def _create_business(name='TestBiz'):
    b = Business(
        name=name,
        slug=name.lower().replace(' ', '-'),
        default_service='gestion',
    )
    b.save()
    return b


def _make_notif(
    notif_type=AdminNotification.NotifType.SYSTEM_INFO,
    title='Test',
    status=AdminNotification.Status.UNREAD,
    severity=AdminNotification.Severity.INFO,
    target_role='',
    target_user=None,
    business=None,
    related_object_type='',
    related_object_id='',
    **kwargs,
) -> AdminNotification:
    n = AdminNotification(
        notif_type=notif_type,
        title=title,
        status=status,
        severity=severity,
        target_role=target_role,
        target_user=target_user,
        business=business,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        **kwargs,
    )
    n.save()
    return n


# ── Auth / Permissions ────────────────────────────────────────────────────────

class NotificationPermissionsTests(TestCase):

    def test_unauthenticated_list_returns_403(self):
        client = APIClient()
        resp = client.get(LIST_URL)
        self.assertIn(resp.status_code, [401, 403])

    def test_non_platform_staff_gets_403(self):
        user = _create_regular_user()
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 403)

    def test_superadmin_can_list(self):
        admin = _create_staff('super@mirubro.com', role='superadmin')
        _make_notif(title='For everyone')
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 1)

    def test_operations_sees_own_role_notification(self):
        ops = _create_staff('ops@mirubro.com', role='operations')
        _make_notif(title='Ops notif', target_role='operations')
        client = APIClient()
        client.force_authenticate(user=ops)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 1)

    def test_operations_sees_personal_target_user_notification(self):
        ops = _create_staff('ops2@mirubro.com', role='operations')
        _make_notif(title='Personal ops', target_user=ops)
        client = APIClient()
        client.force_authenticate(user=ops)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 1)

    def test_support_agent_sees_own_role_notification(self):
        sup = _create_staff('sup@mirubro.com', role='support_agent')
        _make_notif(title='Support notif', target_role='support_agent')
        client = APIClient()
        client.force_authenticate(user=sup)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 1)

    def test_content_admin_sees_own_role_notification(self):
        content = _create_staff('content@mirubro.com', role='content_admin')
        _make_notif(title='Content notif', target_role='content_admin')
        client = APIClient()
        client.force_authenticate(user=content)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 1)

    def test_operations_does_not_see_support_notifications(self):
        ops = _create_staff('ops3@mirubro.com', role='operations')
        _make_notif(title='Support-only notif', target_role='support_agent')
        client = APIClient()
        client.force_authenticate(user=ops)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 0)

    def test_support_does_not_see_operations_notifications(self):
        sup = _create_staff('sup2@mirubro.com', role='support_agent')
        _make_notif(title='Ops-only notif', target_role='operations')
        client = APIClient()
        client.force_authenticate(user=sup)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 0)


# ── List tests ────────────────────────────────────────────────────────────────

class NotificationListTests(TestCase):

    def setUp(self):
        self.admin = _create_staff('super2@mirubro.com', role='superadmin')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

    def test_default_list_excludes_archived(self):
        _make_notif(title='Active', status=AdminNotification.Status.UNREAD)
        _make_notif(title='Archived', status=AdminNotification.Status.ARCHIVED)
        resp = self.client_api.get(LIST_URL)
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(resp.data['results'][0]['title'], 'Active')

    def test_status_archived_includes_archived(self):
        _make_notif(title='Archived', status=AdminNotification.Status.ARCHIVED)
        resp = self.client_api.get(LIST_URL, {'status': 'archived'})
        self.assertEqual(resp.data['total'], 1)

    def test_ordered_by_created_at_desc(self):
        n1 = _make_notif(title='First')
        n2 = _make_notif(title='Second')
        # Backdate n1 so order is clear
        AdminNotification.objects.filter(pk=n1.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=1)
        )
        resp = self.client_api.get(LIST_URL)
        titles = [item['title'] for item in resp.data['results']]
        self.assertEqual(titles[0], 'Second')
        self.assertEqual(titles[1], 'First')

    def test_filter_by_status_unread(self):
        _make_notif(title='Unread', status=AdminNotification.Status.UNREAD)
        _make_notif(title='Read', status=AdminNotification.Status.READ)
        resp = self.client_api.get(LIST_URL, {'status': 'unread'})
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(resp.data['results'][0]['title'], 'Unread')

    def test_filter_by_severity_critical(self):
        _make_notif(title='Critical', severity=AdminNotification.Severity.CRITICAL)
        _make_notif(title='Info', severity=AdminNotification.Severity.INFO)
        resp = self.client_api.get(LIST_URL, {'severity': 'critical'})
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(resp.data['results'][0]['title'], 'Critical')

    def test_filter_by_type(self):
        _make_notif(title='Payment', notif_type=AdminNotification.NotifType.BILLING_PAYMENT_FAILED)
        _make_notif(title='Info', notif_type=AdminNotification.NotifType.SYSTEM_INFO)
        resp = self.client_api.get(LIST_URL, {'type': 'billing_payment_failed'})
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(resp.data['results'][0]['title'], 'Payment')

    def test_invalid_status_returns_400(self):
        resp = self.client_api.get(LIST_URL, {'status': 'nonexistent'})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_severity_returns_400(self):
        resp = self.client_api.get(LIST_URL, {'severity': 'mega_critical'})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_type_returns_400(self):
        resp = self.client_api.get(LIST_URL, {'type': 'not_a_type'})
        self.assertEqual(resp.status_code, 400)

    def test_response_includes_business_name(self):
        biz = _create_business('ACME Corp')
        _make_notif(title='Biz notif', business=biz)
        resp = self.client_api.get(LIST_URL)
        item = resp.data['results'][0]
        self.assertEqual(item['business_name'], 'ACME Corp')

    def test_response_does_not_include_metadata(self):
        _make_notif(title='With meta', metadata={'secret': 'hidden'})
        resp = self.client_api.get(LIST_URL)
        item = resp.data['results'][0]
        self.assertNotIn('metadata', item)

    def test_response_does_not_include_dedupe_key(self):
        _make_notif(title='With dedupe', dedupe_key='abc123')
        resp = self.client_api.get(LIST_URL)
        item = resp.data['results'][0]
        self.assertNotIn('dedupe_key', item)

    def test_pagination_fields_present(self):
        resp = self.client_api.get(LIST_URL)
        self.assertIn('total', resp.data)
        self.assertIn('page', resp.data)
        self.assertIn('page_size', resp.data)
        self.assertIn('total_pages', resp.data)
        self.assertIn('unread_count', resp.data)


# ── Unread count ──────────────────────────────────────────────────────────────

class NotificationUnreadCountTests(TestCase):

    def setUp(self):
        self.admin = _create_staff('super3@mirubro.com', role='superadmin')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

    def test_counts_only_unread_visible(self):
        _make_notif(title='U1', status=AdminNotification.Status.UNREAD)
        _make_notif(title='U2', status=AdminNotification.Status.UNREAD)
        _make_notif(title='R1', status=AdminNotification.Status.READ)
        resp = self.client_api.get(UNREAD_COUNT_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 2)

    def test_critical_count_only_critical_unread(self):
        _make_notif(title='C1', status=AdminNotification.Status.UNREAD, severity=AdminNotification.Severity.CRITICAL)
        _make_notif(title='I1', status=AdminNotification.Status.UNREAD, severity=AdminNotification.Severity.INFO)
        resp = self.client_api.get(UNREAD_COUNT_URL)
        self.assertEqual(resp.data['critical_count'], 1)

    def test_excludes_resolved_and_archived(self):
        _make_notif(title='R', status=AdminNotification.Status.RESOLVED)
        _make_notif(title='A', status=AdminNotification.Status.ARCHIVED)
        resp = self.client_api.get(UNREAD_COUNT_URL)
        self.assertEqual(resp.data['count'], 0)

    def test_scoped_user_counts_only_visible(self):
        ops = _create_staff('ops_count@mirubro.com', role='operations')
        _make_notif(title='Ops', target_role='operations', status=AdminNotification.Status.UNREAD)
        _make_notif(title='Support', target_role='support_agent', status=AdminNotification.Status.UNREAD)
        client = APIClient()
        client.force_authenticate(user=ops)
        resp = client.get(UNREAD_COUNT_URL)
        self.assertEqual(resp.data['count'], 1)


# ── Mark read ─────────────────────────────────────────────────────────────────

class NotificationMarkReadTests(TestCase):

    def setUp(self):
        self.admin = _create_staff('super4@mirubro.com', role='superadmin')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

    def test_read_changes_unread_to_read(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        resp = self.client_api.post(READ_URL.format(n.pk))
        self.assertEqual(resp.status_code, 200)
        n.refresh_from_db()
        self.assertEqual(n.status, AdminNotification.Status.READ)

    def test_read_sets_read_at(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api.post(READ_URL.format(n.pk))
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)

    def test_read_is_idempotent(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api.post(READ_URL.format(n.pk))
        n.refresh_from_db()
        first_read_at = n.read_at
        resp2 = self.client_api.post(READ_URL.format(n.pk))
        self.assertEqual(resp2.status_code, 200)
        n.refresh_from_db()
        self.assertEqual(n.read_at, first_read_at)

    def test_read_outside_scope_returns_404(self):
        ops = _create_staff('ops_rd@mirubro.com', role='operations')
        n = _make_notif(title='Support only', target_role='support_agent')
        client = APIClient()
        client.force_authenticate(user=ops)
        resp = client.post(READ_URL.format(n.pk))
        self.assertEqual(resp.status_code, 404)


# ── Archive ───────────────────────────────────────────────────────────────────

class NotificationArchiveTests(TestCase):

    def setUp(self):
        self.admin = _create_staff('super5@mirubro.com', role='superadmin')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

    def test_archive_changes_status_to_archived(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        resp = self.client_api.post(ARCHIVE_URL.format(n.pk))
        self.assertEqual(resp.status_code, 200)
        n.refresh_from_db()
        self.assertEqual(n.status, AdminNotification.Status.ARCHIVED)

    def test_archive_sets_archived_at(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api.post(ARCHIVE_URL.format(n.pk))
        n.refresh_from_db()
        self.assertIsNotNone(n.archived_at)

    def test_archive_is_idempotent(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api.post(ARCHIVE_URL.format(n.pk))
        n.refresh_from_db()
        first_archived_at = n.archived_at
        resp2 = self.client_api.post(ARCHIVE_URL.format(n.pk))
        self.assertEqual(resp2.status_code, 200)
        n.refresh_from_db()
        self.assertEqual(n.archived_at, first_archived_at)

    def test_archive_outside_scope_returns_404(self):
        ops = _create_staff('ops_ar@mirubro.com', role='operations')
        n = _make_notif(title='Support only', target_role='support_agent')
        client = APIClient()
        client.force_authenticate(user=ops)
        resp = client.post(ARCHIVE_URL.format(n.pk))
        self.assertEqual(resp.status_code, 404)


# ── Resolve ───────────────────────────────────────────────────────────────────

class NotificationResolveTests(TestCase):

    def setUp(self):
        self.admin = _create_staff('super6@mirubro.com', role='superadmin')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

    def test_resolve_changes_unread_to_resolved(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        resp = self.client_api.post(RESOLVE_URL.format(n.pk))
        self.assertEqual(resp.status_code, 200)
        n.refresh_from_db()
        self.assertEqual(n.status, AdminNotification.Status.RESOLVED)

    def test_resolve_sets_resolved_at(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api.post(RESOLVE_URL.format(n.pk))
        n.refresh_from_db()
        self.assertIsNotNone(n.resolved_at)

    def test_resolve_on_unread_also_sets_read_at(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api.post(RESOLVE_URL.format(n.pk))
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)

    def test_resolve_is_idempotent(self):
        n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api.post(RESOLVE_URL.format(n.pk))
        n.refresh_from_db()
        first_resolved_at = n.resolved_at
        resp2 = self.client_api.post(RESOLVE_URL.format(n.pk))
        self.assertEqual(resp2.status_code, 200)
        n.refresh_from_db()
        self.assertEqual(n.resolved_at, first_resolved_at)

    def test_resolve_outside_scope_returns_404(self):
        ops = _create_staff('ops_rs@mirubro.com', role='operations')
        n = _make_notif(title='Support only', target_role='support_agent')
        client = APIClient()
        client.force_authenticate(user=ops)
        resp = client.post(RESOLVE_URL.format(n.pk))
        self.assertEqual(resp.status_code, 404)


# ── Security: no email calls ──────────────────────────────────────────────────

class NotificationNoEmailTests(TestCase):

    def setUp(self):
        self.admin = _create_staff('super7@mirubro.com', role='superadmin')
        self.n = _make_notif(status=AdminNotification.Status.UNREAD)
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

    def test_no_send_mail_on_list(self):
        with patch('django.core.mail.send_mail') as m:
            self.client_api.get(LIST_URL)
            m.assert_not_called()

    def test_no_send_mail_on_read(self):
        with patch('django.core.mail.send_mail') as m:
            self.client_api.post(READ_URL.format(self.n.pk))
            m.assert_not_called()

    def test_no_send_mail_on_archive(self):
        with patch('django.core.mail.send_mail') as m:
            self.client_api.post(ARCHIVE_URL.format(self.n.pk))
            m.assert_not_called()

    def test_no_send_mail_on_resolve(self):
        with patch('django.core.mail.send_mail') as m:
            self.client_api.post(RESOLVE_URL.format(self.n.pk))
            m.assert_not_called()
