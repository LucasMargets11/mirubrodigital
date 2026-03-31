"""
Tests for ticket integration in admin dashboard and client detail endpoints.

Covers:
  1.  Dashboard metrics include ticket_kpis
  2.  ticket_kpis counts match expected values
  3.  Dashboard alerts include urgent_unassigned alert
  4.  Dashboard alerts suppress ticket alert when none urgent
  5.  Client detail includes support_summary
  6.  support_summary counts are scoped to the correct business
  7.  support_summary recent_tickets returns up to 5 items
  8.  support_summary handles business with zero tickets
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccountProfile
from apps.accounts.support_ticket import SupportTicket
from apps.business.models import Business

User = get_user_model()

DASHBOARD_URL = '/api/v1/platform-admin/dashboard/metrics/'
CLIENT_DETAIL_URL = '/api/v1/platform-admin/clients/{}/'


def _create_admin(email='admin@mirubro.com', password='SecurePass123!', role='superadmin'):
    user = User.objects.create_user(username=email, email=email, password=password)
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.is_platform_staff = True
    profile.internal_role = role
    profile.save()
    # Refresh so the user object picks up the updated profile cache
    user.refresh_from_db()
    return user


def _make_ticket(business, status='open', priority='medium', assigned_to=None, **kw):
    t = SupportTicket(
        subject=kw.get('subject', 'Test ticket'),
        business=business,
        category='other',
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        origin='admin',
    )
    t.save()
    return t


class DashboardTicketKPIsTests(TestCase):
    """Dashboard metrics endpoint includes ticket_kpis."""

    def setUp(self):
        self.admin = _create_admin()
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

        self.biz = Business.objects.create(name='Biz One', default_service='gestion')

    def test_dashboard_includes_ticket_kpis(self):
        resp = self.client_api.get(DASHBOARD_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('ticket_kpis', resp.data)
        for key in ('open_tickets', 'waiting_on_client', 'urgent_unassigned', 'new_last_7_days'):
            self.assertIn(key, resp.data['ticket_kpis'])

    def test_ticket_kpis_counts(self):
        _make_ticket(self.biz, status='open')
        _make_ticket(self.biz, status='in_progress')
        _make_ticket(self.biz, status='waiting_on_client')
        _make_ticket(self.biz, status='resolved')
        _make_ticket(self.biz, status='closed')
        _make_ticket(self.biz, status='open', priority='urgent')  # urgent, unassigned

        resp = self.client_api.get(DASHBOARD_URL)
        kpis = resp.data['ticket_kpis']

        # open = open + in_progress
        self.assertEqual(kpis['open_tickets'], 3)  # 2 open + 1 in_progress
        self.assertEqual(kpis['waiting_on_client'], 1)
        self.assertEqual(kpis['urgent_unassigned'], 1)
        # All 6 created just now → new_last_7_days = 6
        self.assertEqual(kpis['new_last_7_days'], 6)

    def test_urgent_unassigned_excluded_when_resolved(self):
        _make_ticket(self.biz, status='resolved', priority='urgent')
        _make_ticket(self.biz, status='closed', priority='urgent')

        resp = self.client_api.get(DASHBOARD_URL)
        self.assertEqual(resp.data['ticket_kpis']['urgent_unassigned'], 0)

    def test_urgent_unassigned_excluded_when_assigned(self):
        _make_ticket(self.biz, status='open', priority='urgent', assigned_to=self.admin)

        resp = self.client_api.get(DASHBOARD_URL)
        self.assertEqual(resp.data['ticket_kpis']['urgent_unassigned'], 0)

    def test_alert_when_urgent_unassigned(self):
        _make_ticket(self.biz, status='open', priority='urgent')

        resp = self.client_api.get(DASHBOARD_URL)
        alert_messages = [a['message'] for a in resp.data['alerts']]
        self.assertTrue(any('urgente' in m for m in alert_messages))

    def test_no_ticket_alert_when_none_urgent(self):
        _make_ticket(self.biz, status='open', priority='medium')

        resp = self.client_api.get(DASHBOARD_URL)
        alert_messages = [a['message'] for a in resp.data['alerts']]
        self.assertFalse(any('urgente' in m for m in alert_messages))


class ClientDetailSupportSummaryTests(TestCase):
    """Client detail endpoint includes support_summary."""

    def setUp(self):
        self.admin = _create_admin(email='admin2@mirubro.com')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.admin)

        self.biz_a = Business.objects.create(name='Business A', default_service='gestion')
        self.biz_b = Business.objects.create(name='Business B', default_service='gestion')

    def test_client_detail_includes_support_summary(self):
        resp = self.client_api.get(CLIENT_DETAIL_URL.format(self.biz_a.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('support_summary', resp.data)
        for key in ('total_tickets', 'open_tickets', 'resolved_tickets',
                     'last_ticket_at', 'last_ticket_reference', 'recent_tickets'):
            self.assertIn(key, resp.data['support_summary'])

    def test_support_summary_counts_correct(self):
        _make_ticket(self.biz_a, status='open')
        _make_ticket(self.biz_a, status='in_progress')
        _make_ticket(self.biz_a, status='waiting_on_client')
        _make_ticket(self.biz_a, status='resolved')
        _make_ticket(self.biz_a, status='closed')

        resp = self.client_api.get(CLIENT_DETAIL_URL.format(self.biz_a.id))
        ss = resp.data['support_summary']

        self.assertEqual(ss['total_tickets'], 5)
        self.assertEqual(ss['open_tickets'], 3)  # open + in_progress + waiting
        self.assertEqual(ss['resolved_tickets'], 1)

    def test_support_summary_scoped_to_business(self):
        _make_ticket(self.biz_a, status='open')
        _make_ticket(self.biz_a, status='open')
        _make_ticket(self.biz_b, status='open')  # should NOT appear

        resp = self.client_api.get(CLIENT_DETAIL_URL.format(self.biz_a.id))
        ss = resp.data['support_summary']

        self.assertEqual(ss['total_tickets'], 2)
        self.assertEqual(ss['open_tickets'], 2)

    def test_support_summary_recent_tickets_max_5(self):
        for i in range(7):
            _make_ticket(self.biz_a, subject=f'Ticket {i}')

        resp = self.client_api.get(CLIENT_DETAIL_URL.format(self.biz_a.id))
        ss = resp.data['support_summary']

        self.assertEqual(len(ss['recent_tickets']), 5)

    def test_support_summary_recent_ticket_fields(self):
        _make_ticket(self.biz_a, status='open', priority='high', subject='Test fields')

        resp = self.client_api.get(CLIENT_DETAIL_URL.format(self.biz_a.id))
        ticket = resp.data['support_summary']['recent_tickets'][0]

        self.assertIn('id', ticket)
        self.assertIn('reference', ticket)
        self.assertEqual(ticket['subject'], 'Test fields')
        self.assertEqual(ticket['status'], 'open')
        self.assertEqual(ticket['priority'], 'high')
        self.assertIn('created_at', ticket)
        self.assertIn('updated_at', ticket)

    def test_support_summary_last_ticket(self):
        t = _make_ticket(self.biz_a, subject='Last one')

        resp = self.client_api.get(CLIENT_DETAIL_URL.format(self.biz_a.id))
        ss = resp.data['support_summary']

        self.assertEqual(ss['last_ticket_reference'], t.reference)
        self.assertIsNotNone(ss['last_ticket_at'])

    def test_support_summary_zero_tickets(self):
        resp = self.client_api.get(CLIENT_DETAIL_URL.format(self.biz_a.id))
        ss = resp.data['support_summary']

        self.assertEqual(ss['total_tickets'], 0)
        self.assertEqual(ss['open_tickets'], 0)
        self.assertEqual(ss['resolved_tickets'], 0)
        self.assertIsNone(ss['last_ticket_at'])
        self.assertIsNone(ss['last_ticket_reference'])
        self.assertEqual(ss['recent_tickets'], [])
