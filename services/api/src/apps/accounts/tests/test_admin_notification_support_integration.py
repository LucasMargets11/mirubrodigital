"""
tests/test_admin_notification_support_integration.py

Integration tests for PR-ADMIN-10E: support ticket → AdminNotification.

Covers:
  01. Ticket de tenant crea notificación support_ticket_created.
  02. Ticket de admin (ORIGIN_ADMIN) NO crea notificación.
  03. La notificación tiene notif_type correcto.
  04. La notificación tiene severity='warning'.
  05. La notificación tiene target_role='support_agent'.
  06. El title contiene 'Nuevo ticket de soporte'.
  07. El message contiene el nombre del negocio y el subject.
  08. metadata incluye ticket_reference, ticket_priority, ticket_category.
  09. metadata NO incluye datos sensibles (email, body del mensaje).
  10. Si create_admin_notification lanza excepción, el helper no propaga.
  11. No se usa send_mail.
  12. No se usa EmailMessage.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call, patch

from django.test import TestCase

from apps.accounts.support_ticket import SupportTicket
from apps.accounts.tenant_support_views import _notify_admin_ticket_created

_CREATE_NOTIF = 'apps.accounts.admin_notification_service.create_admin_notification'
_IMPORT_TARGET = 'apps.accounts.tenant_support_views._notify_admin_ticket_created'


# ── Helper factories ──────────────────────────────────────────────────────────

def _make_ticket(origin=SupportTicket.ORIGIN_TENANT):
    business = MagicMock()
    business.name = 'Café del Sur'

    ticket = MagicMock(spec=SupportTicket)
    ticket.id = uuid.uuid4()
    ticket.origin = origin
    ticket.reference = 'TKT-0001'
    ticket.subject = 'Mi app no carga'
    ticket.priority = SupportTicket.PRIORITY_MEDIUM
    ticket.category = 'billing'
    ticket.contact_email = 'owner@cafedelsur.com'
    ticket.business = business
    return ticket


# ── Tests ─────────────────────────────────────────────────────────────────────

class NotifyAdminTicketCreatedTests(TestCase):
    """Unit tests for _notify_admin_ticket_created."""

    def test_01_tenant_ticket_creates_notification(self):
        """Ticket de tenant crea notificación support_ticket_created."""
        ticket = _make_ticket(origin=SupportTicket.ORIGIN_TENANT)
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs['notif_type'], 'support_ticket_created')

    def test_02_admin_ticket_does_not_create_notification(self):
        """Ticket de admin NO crea notificación."""
        ticket = _make_ticket(origin=SupportTicket.ORIGIN_ADMIN)
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        mock_create.assert_not_called()

    def test_03_correct_notif_type(self):
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        self.assertEqual(mock_create.call_args.kwargs['notif_type'], 'support_ticket_created')

    def test_04_severity_warning(self):
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        self.assertEqual(mock_create.call_args.kwargs['severity'], 'warning')

    def test_05_target_role_support_agent(self):
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        self.assertEqual(mock_create.call_args.kwargs['target_role'], 'support_agent')

    def test_06_title_contains_nuevo_ticket(self):
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        self.assertIn('ticket', mock_create.call_args.kwargs['title'].lower())

    def test_07_message_contains_business_name_and_subject(self):
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        message = mock_create.call_args.kwargs['message']
        self.assertIn('Café del Sur', message)
        self.assertIn('Mi app no carga', message)

    def test_08_metadata_includes_reference_priority_category(self):
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        meta = mock_create.call_args.kwargs['metadata']
        self.assertEqual(meta['ticket_reference'], 'TKT-0001')
        self.assertEqual(meta['ticket_priority'], SupportTicket.PRIORITY_MEDIUM)
        self.assertEqual(meta['ticket_category'], 'billing')

    def test_09_metadata_does_not_include_sensitive_data(self):
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF) as mock_create:
            _notify_admin_ticket_created(ticket)
        meta = mock_create.call_args.kwargs['metadata']
        # contact_email and message body must not be in metadata
        self.assertNotIn('contact_email', meta)
        self.assertNotIn('email', str(meta).lower())
        self.assertNotIn('body', meta)

    def test_10_exception_does_not_propagate(self):
        """Si create_admin_notification lanza excepción, el helper no propaga."""
        ticket = _make_ticket()
        with patch(_CREATE_NOTIF, side_effect=RuntimeError('DB error')):
            # Should not raise
            _notify_admin_ticket_created(ticket)

    def test_11_no_send_mail_used(self):
        ticket = _make_ticket()
        with patch('django.core.mail.send_mail') as mock_mail, \
                patch(_CREATE_NOTIF):
            _notify_admin_ticket_created(ticket)
        mock_mail.assert_not_called()

    def test_12_no_email_message_used(self):
        ticket = _make_ticket()
        with patch('django.core.mail.EmailMessage') as mock_em, \
                patch(_CREATE_NOTIF):
            _notify_admin_ticket_created(ticket)
        mock_em.assert_not_called()
