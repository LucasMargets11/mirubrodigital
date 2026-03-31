"""
Tests for tenant-facing support ticket endpoints.

Covers:
  1.  Owner can create a ticket
  2.  Owner can list only their business tickets
  3.  Owner can view detail of their ticket
  4.  Owner cannot view ticket of another business
  5.  Owner can reply to a ticket
  6.  System messages (is_system=True) are hidden in tenant detail
  7.  Owner can close a ticket
  8.  Owner can reopen a closed ticket
  9.  Non-owner role gets 403
  10. Anti-spam: 10 open tickets limit
  11. Reply on waiting_on_client auto-reopens ticket
  12. Tenant audit trail actions are recorded
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Membership, AccessAuditLog
from apps.accounts.support_ticket import SupportTicket, TicketMessage
from apps.business.models import Business, Subscription

User = get_user_model()

BASE_URL = '/api/v1/support/tickets/'


class TenantSupportTestCase(TestCase):
    """Test suite for tenant support endpoints."""

    def setUp(self):
        # ── Business A (primary test business) ───────────────────────────
        self.business_a = Business.objects.create(
            name='Business A', default_service='gestion',
        )
        Subscription.objects.create(
            business=self.business_a, plan='starter', status='active',
        )

        self.owner = User.objects.create_user(
            username='owner_a@test.com', email='owner_a@test.com', password='pass1234',
        )
        Membership.objects.create(
            user=self.owner, business=self.business_a, role='owner',
        )

        # ── Business B (isolation test) ──────────────────────────────────
        self.business_b = Business.objects.create(
            name='Business B', default_service='gestion',
        )
        Subscription.objects.create(
            business=self.business_b, plan='starter', status='active',
        )

        self.owner_b = User.objects.create_user(
            username='owner_b@test.com', email='owner_b@test.com', password='pass1234',
        )
        Membership.objects.create(
            user=self.owner_b, business=self.business_b, role='owner',
        )

        # ── Non-owner user on Business A ─────────────────────────────────
        self.staff_user = User.objects.create_user(
            username='staff@test.com', email='staff@test.com', password='pass1234',
        )
        Membership.objects.create(
            user=self.staff_user, business=self.business_a, role='staff',
        )

        self.client = APIClient()

    def _auth_as(self, user, business):
        """Authenticate and set business context via header."""
        self.client.force_authenticate(user=user)
        self.client.credentials(HTTP_X_BUSINESS_ID=str(business.id))

    def _create_ticket(self, business=None, status_val=SupportTicket.STATUS_OPEN, subject='Test Ticket'):
        """Helper to create a ticket directly in the DB."""
        biz = business or self.business_a
        t = SupportTicket(
            subject=subject,
            business=biz,
            category='other',
            created_by=self.owner,
            origin=SupportTicket.ORIGIN_TENANT,
            status=status_val,
        )
        t.save()
        return t

    # ── 1. Owner can create ticket ────────────────────────────────────────

    def test_owner_can_create_ticket(self):
        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(BASE_URL, {
            'subject': 'Mi primer ticket',
            'category': 'billing',
            'body': 'Tengo un problema con la facturación.',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', resp.data)
        self.assertIn('reference', resp.data)
        self.assertTrue(resp.data['reference'].startswith('TK-'))

        ticket = SupportTicket.objects.get(pk=resp.data['id'])
        self.assertEqual(ticket.origin, SupportTicket.ORIGIN_TENANT)
        self.assertEqual(ticket.business, self.business_a)
        self.assertEqual(ticket.category, 'billing')
        self.assertEqual(ticket.messages.count(), 1)

    # ── 2. Owner can list only their business tickets ─────────────────────

    def test_owner_lists_only_own_business_tickets(self):
        self._create_ticket(business=self.business_a, subject='Ticket A')
        self._create_ticket(business=self.business_b, subject='Ticket B')

        self._auth_as(self.owner, self.business_a)
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        subjects = [t['subject'] for t in resp.data['results']]
        self.assertIn('Ticket A', subjects)
        self.assertNotIn('Ticket B', subjects)

    # ── 3. Owner can view detail ──────────────────────────────────────────

    def test_owner_can_view_detail(self):
        ticket = self._create_ticket()
        TicketMessage.objects.create(ticket=ticket, author=self.owner, body='Hola')

        self._auth_as(self.owner, self.business_a)
        resp = self.client.get(f'{BASE_URL}{ticket.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['reference'], ticket.reference)
        self.assertEqual(len(resp.data['messages']), 1)
        self.assertIn('can_close', resp.data)
        self.assertIn('can_reopen', resp.data)

    # ── 4. Owner cannot view ticket of another business ───────────────────

    def test_owner_cannot_view_other_business_ticket(self):
        ticket_b = self._create_ticket(business=self.business_b)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.get(f'{BASE_URL}{ticket_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ── 5. Owner can reply ────────────────────────────────────────────────

    def test_owner_can_reply(self):
        ticket = self._create_ticket()

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/reply/', {
            'body': 'Gracias por la ayuda',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['body'], 'Gracias por la ayuda')
        self.assertEqual(ticket.messages.filter(is_system=False).count(), 1)

    # ── 6. System messages hidden in tenant detail ────────────────────────

    def test_system_messages_hidden_in_detail(self):
        ticket = self._create_ticket()
        TicketMessage.objects.create(ticket=ticket, author=self.owner, body='Visible')
        TicketMessage.objects.create(ticket=ticket, author=self.owner, body='System msg', is_system=True)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.get(f'{BASE_URL}{ticket.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        bodies = [m['body'] for m in resp.data['messages']]
        self.assertIn('Visible', bodies)
        self.assertNotIn('System msg', bodies)

    # ── 7. Owner can close ticket ─────────────────────────────────────────

    def test_owner_can_close_ticket(self):
        ticket = self._create_ticket()

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/close/', {
            'action': 'close',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], SupportTicket.STATUS_CLOSED)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.STATUS_CLOSED)
        self.assertIsNotNone(ticket.closed_at)

    # ── 8. Owner can reopen ticket ────────────────────────────────────────

    def test_owner_can_reopen_ticket(self):
        ticket = self._create_ticket(status_val=SupportTicket.STATUS_CLOSED)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/close/', {
            'action': 'reopen',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], SupportTicket.STATUS_OPEN)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.STATUS_OPEN)
        self.assertIsNone(ticket.closed_at)

    # ── 9. Non-owner gets 403 ────────────────────────────────────────────

    def test_non_owner_denied(self):
        self._auth_as(self.staff_user, self.business_a)

        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(BASE_URL, {
            'subject': 'Test', 'body': 'Body', 'category': 'other',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ── 10. Anti-spam: 10 open tickets limit ─────────────────────────────

    def test_anti_spam_limit(self):
        for i in range(10):
            self._create_ticket(subject=f'Ticket {i}')

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(BASE_URL, {
            'subject': 'Ticket 11',
            'body': 'Should fail',
            'category': 'other',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Límite', resp.data['detail'])

    # ── 11. Reply on waiting_on_client auto-reopens ──────────────────────

    def test_reply_on_waiting_auto_reopens(self):
        ticket = self._create_ticket(status_val=SupportTicket.STATUS_WAITING)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/reply/', {
            'body': 'Aquí va mi respuesta',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.STATUS_OPEN)

    def test_reply_on_resolved_auto_reopens(self):
        ticket = self._create_ticket(status_val=SupportTicket.STATUS_RESOLVED)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/reply/', {
            'body': 'Todavía tengo el problema',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.STATUS_OPEN)

    # ── 12. Audit trail tenant actions ───────────────────────────────────

    def test_audit_trail_on_create(self):
        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(BASE_URL, {
            'subject': 'Audit test',
            'body': 'Checking audit',
            'category': 'technical',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        log = AccessAuditLog.objects.filter(
            action='TENANT_TICKET_CREATED',
            actor=self.owner,
            business=self.business_a,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.entity_type, 'support_ticket')

    def test_audit_trail_on_close(self):
        ticket = self._create_ticket()

        self._auth_as(self.owner, self.business_a)
        self.client.post(f'{BASE_URL}{ticket.id}/close/', {
            'action': 'close',
        }, format='json')

        log = AccessAuditLog.objects.filter(
            action='TENANT_TICKET_CLOSED',
            actor=self.owner,
        ).first()
        self.assertIsNotNone(log)

    def test_audit_trail_on_reopen(self):
        ticket = self._create_ticket(status_val=SupportTicket.STATUS_CLOSED)

        self._auth_as(self.owner, self.business_a)
        self.client.post(f'{BASE_URL}{ticket.id}/close/', {
            'action': 'reopen',
        }, format='json')

        log = AccessAuditLog.objects.filter(
            action='TENANT_TICKET_REOPENED',
            actor=self.owner,
        ).first()
        self.assertIsNotNone(log)

    def test_audit_trail_on_reply(self):
        ticket = self._create_ticket()

        self._auth_as(self.owner, self.business_a)
        self.client.post(f'{BASE_URL}{ticket.id}/reply/', {
            'body': 'Reply audit test',
        }, format='json')

        log = AccessAuditLog.objects.filter(
            action='TENANT_TICKET_REPLIED',
            actor=self.owner,
        ).first()
        self.assertIsNotNone(log)

    # ── Edge cases ────────────────────────────────────────────────────────

    def test_cannot_reply_closed_ticket(self):
        ticket = self._create_ticket(status_val=SupportTicket.STATUS_CLOSED)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/reply/', {
            'body': 'Should fail',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_close_already_closed(self):
        ticket = self._create_ticket(status_val=SupportTicket.STATUS_CLOSED)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/close/', {
            'action': 'close',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_reopen_non_closed(self):
        ticket = self._create_ticket(status_val=SupportTicket.STATUS_OPEN)

        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(f'{BASE_URL}{ticket.id}/close/', {
            'action': 'reopen',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_requires_body(self):
        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(BASE_URL, {
            'subject': 'No body',
            'category': 'other',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_requires_subject(self):
        self._auth_as(self.owner, self.business_a)
        resp = self.client.post(BASE_URL, {
            'body': 'No subject',
            'category': 'other',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_author_anonymized_in_detail(self):
        """Staff messages show 'Soporte Mi Rubro' instead of real name."""
        from apps.accounts.models import AccountProfile

        ticket = self._create_ticket()

        # Create a platform staff user
        staff_platform = User.objects.create_user(
            username='agent@mirubro.com',
            email='agent@mirubro.com',
            password='pass1234',
            first_name='Juan',
            last_name='Agente',
        )
        AccountProfile.objects.filter(user=staff_platform).update(
            is_platform_staff=True,
            internal_role='support_agent',
            email_verified=True,
        )
        TicketMessage.objects.create(
            ticket=ticket, author=staff_platform, body='Te ayudo con eso.',
        )

        self._auth_as(self.owner, self.business_a)
        resp = self.client.get(f'{BASE_URL}{ticket.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        staff_msg = resp.data['messages'][0]
        self.assertEqual(staff_msg['author_name'], 'Soporte Mi Rubro')
        self.assertTrue(staff_msg['is_from_staff'])
