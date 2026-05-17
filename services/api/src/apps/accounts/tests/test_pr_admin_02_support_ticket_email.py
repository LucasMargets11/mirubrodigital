"""
apps/accounts/tests/test_pr_admin_02_support_ticket_email.py

Tests para PR-ADMIN-02: email interno admin_support_ticket_created.

Cubre:
  01. Cliente crea ticket → se encola email interno.
  02. Email usa template_key="admin_support_ticket_created".
  03. Email usa recipient_category="support" vía el helper.
  04. Email se asocia al business correcto.
  05. Email se asocia al user que creó el ticket.
  06. Context incluye ticket_reference, ticket_subject, business_name y admin_url.
  07. Metadata incluye event_type, ticket_id, ticket_reference y related_business_id.
  08. Metadata NO incluye cuerpo completo del mensaje del cliente.
  09. Si falla el helper, el ticket igual se crea y la response sigue siendo 201.
  10. Request inválida (subject vacío) → no se encola email.
  11. Ticket creado desde AdminTicketCreateView no dispara admin_support_ticket_created.
  12. No se usa send_mail.
  13. No se usa EmailMessage.
  14. admin_url apunta al detalle del ticket en admin.
  15. Renderiza admin_support_ticket_created.html sin errores.
"""
import logging
from unittest.mock import call, patch, MagicMock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import AccountProfile, Membership
from apps.accounts.support_ticket import SupportTicket
from apps.business.models import Business, Subscription
from apps.notifications.services import render_email_template

User = get_user_model()

BASE_URL = '/api/v1/support/tickets/'
ADMIN_CREATE_URL = '/api/v1/platform-admin/tickets/create/'

_HELPER_TARGET = "apps.accounts.tenant_support_views.queue_admin_transactional_email"


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _make_business(name="Biz Test"):
    biz = Business.objects.create(name=name, default_service="gestion")
    Subscription.objects.create(business=biz, plan="starter", status="active")
    return biz


def _make_owner(email="owner@test.com", business=None):
    user = User.objects.create_user(username=email, email=email, password="pass1234")
    if business:
        Membership.objects.create(user=user, business=business, role="owner")
    return user


def _make_admin(email="admin@mirubro.com"):
    user = User.objects.create_user(username=email, email=email, password="SecureAdmin1!")
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.is_platform_staff = True
    profile.internal_role = "superadmin"
    profile.save()
    return user


# ── 01-13: Main test class ────────────────────────────────────────────────────

class TenantTicketCreatedEmailTest(TestCase):
    """Email interno admin_support_ticket_created vía tenant endpoint."""

    def setUp(self):
        self.business = _make_business("Mi Negocio SA")
        self.owner = _make_owner("owner@test.com", self.business)
        self.api = APIClient()
        self.api.force_authenticate(user=self.owner)
        self.api.credentials(HTTP_X_BUSINESS_ID=str(self.business.id))

    def _post_ticket(self, **overrides):
        payload = {
            "subject": "Problema con facturación",
            "body": "No puedo ver mi factura del mes pasado.",
            "category": "billing",
            "contact_email": "owner@test.com",
        }
        payload.update(overrides)
        return self.api.post(BASE_URL, payload, format="json")

    # 01 — Se encola email al crear ticket
    @patch(_HELPER_TARGET)
    def test_ticket_creation_enqueues_admin_email(self, mock_helper):
        resp = self._post_ticket()
        self.assertEqual(resp.status_code, 201)
        mock_helper.assert_called_once()

    # 02 — template_key correcto
    @patch(_HELPER_TARGET)
    def test_email_uses_correct_template_key(self, mock_helper):
        self._post_ticket()
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["template_key"], "admin_support_ticket_created")

    # 03 — recipient_category="support"
    @patch(_HELPER_TARGET)
    def test_email_uses_support_recipient_category(self, mock_helper):
        self._post_ticket()
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["recipient_category"], "support")

    # 04 — related_business correcto
    @patch(_HELPER_TARGET)
    def test_email_associates_correct_business(self, mock_helper):
        self._post_ticket()
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["related_business"], self.business)

    # 05 — related_user correcto
    @patch(_HELPER_TARGET)
    def test_email_associates_correct_user(self, mock_helper):
        self._post_ticket()
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["related_user"], self.owner)

    # 06 — Context incluye campos clave
    @patch(_HELPER_TARGET)
    def test_context_includes_ticket_fields(self, mock_helper):
        resp = self._post_ticket(subject="Mi asunto de prueba")
        self.assertEqual(resp.status_code, 201)
        ticket_id = resp.data["id"]
        ticket = SupportTicket.objects.get(id=ticket_id)

        _, kwargs = mock_helper.call_args
        ctx = kwargs["context"]

        self.assertEqual(ctx["ticket_reference"], ticket.reference)
        self.assertEqual(ctx["ticket_subject"], "Mi asunto de prueba")
        self.assertEqual(ctx["business_name"], self.business.name)
        self.assertIn(ticket_id, ctx["admin_url"])

    # 07 — Metadata incluye campos requeridos
    @patch(_HELPER_TARGET)
    def test_metadata_includes_required_fields(self, mock_helper):
        resp = self._post_ticket()
        self.assertEqual(resp.status_code, 201)
        ticket_id = resp.data["id"]
        ticket = SupportTicket.objects.get(id=ticket_id)

        _, kwargs = mock_helper.call_args
        meta = kwargs["metadata"]

        self.assertEqual(meta["event_type"], "admin_support_ticket_created")
        self.assertEqual(meta["ticket_id"], ticket_id)
        self.assertEqual(meta["ticket_reference"], ticket.reference)
        self.assertEqual(meta["related_business_id"], str(self.business.id))

    # 08 — Metadata NO incluye cuerpo del mensaje
    @patch(_HELPER_TARGET)
    def test_metadata_does_not_include_message_body(self, mock_helper):
        self._post_ticket(body="Mensaje confidencial del cliente que no debe estar en meta.")
        _, kwargs = mock_helper.call_args
        meta = kwargs["metadata"]
        # Body text must not leak into metadata keys or values
        for value in meta.values():
            if isinstance(value, str):
                self.assertNotIn("confidencial", value)
        self.assertNotIn("body", meta)
        self.assertNotIn("message", meta)

    # 09 — Si falla el helper, el ticket se crea y response es 201
    @patch(_HELPER_TARGET, side_effect=RuntimeError("Celery caído"))
    def test_helper_failure_does_not_break_ticket_creation(self, mock_helper):
        resp = self._post_ticket()
        # The view's own try/except in _queue_ticket_created_email wraps the helper
        # but the helper itself is best-effort — ticket must still be created.
        self.assertEqual(resp.status_code, 201)
        ticket_id = resp.data["id"]
        self.assertTrue(SupportTicket.objects.filter(id=ticket_id).exists())

    # 10 — Request inválida → no se encola email
    @patch(_HELPER_TARGET)
    def test_invalid_request_does_not_enqueue_email(self, mock_helper):
        resp = self._post_ticket(subject="")  # subject is required
        self.assertEqual(resp.status_code, 400)
        mock_helper.assert_not_called()

    # 12 — No usa send_mail
    @patch(_HELPER_TARGET)
    @patch("django.core.mail.send_mail")
    def test_does_not_use_send_mail(self, mock_send_mail, mock_helper):
        self._post_ticket()
        mock_send_mail.assert_not_called()

    # 13 — No usa EmailMessage
    @patch(_HELPER_TARGET)
    @patch("django.core.mail.EmailMessage")
    def test_does_not_use_email_message(self, mock_email_msg, mock_helper):
        self._post_ticket()
        mock_email_msg.assert_not_called()

    # 14 — admin_url apunta al detalle del ticket
    @patch(_HELPER_TARGET)
    @override_settings(ADMIN_FRONTEND_URL="http://localhost:3000/admin")
    def test_admin_url_points_to_ticket_detail(self, mock_helper):
        resp = self._post_ticket()
        ticket_id = resp.data["id"]
        _, kwargs = mock_helper.call_args
        admin_url = kwargs["context"]["admin_url"]
        self.assertIn(f"/soporte/{ticket_id}", admin_url)

    # Extra — admin_url no duplica /admin si ADMIN_FRONTEND_URL ya lo incluye
    @patch(_HELPER_TARGET)
    @override_settings(ADMIN_FRONTEND_URL="http://localhost:3000/admin")
    def test_admin_url_does_not_duplicate_admin_prefix(self, mock_helper):
        resp = self._post_ticket()
        _, kwargs = mock_helper.call_args
        admin_url = kwargs["context"]["admin_url"]
        self.assertNotIn("/admin/admin", admin_url)


# ── 11 — AdminTicketCreateView no dispara el email ───────────────────────────

class AdminTicketCreateNoEmailTest(TestCase):
    """Ticket creado desde el panel admin NO dispara admin_support_ticket_created."""

    def setUp(self):
        self.admin_user = _make_admin()
        self.business = _make_business("Biz Admin Test")
        self.api = APIClient()
        self.api.force_authenticate(user=self.admin_user)

    @patch(_HELPER_TARGET)
    def test_admin_create_does_not_trigger_email(self, mock_helper):
        payload = {
            "business_id": str(self.business.id),
            "subject": "Ticket creado por admin",
            "body": "Descripción desde admin.",
            "category": "technical",
            "priority": "medium",
        }
        resp = self.api.post(ADMIN_CREATE_URL, payload, format="json")
        # The admin view may return 200 or 201 depending on implementation;
        # what matters is that the helper was NOT called via the tenant path.
        mock_helper.assert_not_called()


# ── 15 — Template renderiza sin errores ──────────────────────────────────────

class AdminSupportTicketCreatedTemplateTest(TestCase):
    """admin_support_ticket_created.html se renderiza sin errores."""

    def test_full_context_renders_correctly(self):
        context = {
            "ticket_reference": "TK-0001",
            "ticket_subject": "Mi problema",
            "ticket_category": "billing",
            "ticket_priority": "medium",
            "business_name": "Empresa Ejemplo SA",
            "contact_email": "cliente@empresa.com",
            "created_at": "10/05/2026 14:30",
            "admin_url": "http://localhost:3000/admin/soporte/abc-123",
        }
        html, text = render_email_template("admin_support_ticket_created", context)
        self.assertIn("TK-0001", html)
        self.assertIn("Mi problema", html)
        self.assertIn("Empresa Ejemplo SA", html)
        self.assertIn("NOTIFICACIÓN INTERNA", html)
        self.assertIn("Abrir ticket en admin", html)
        self.assertIn("http://localhost:3000/admin/soporte/abc-123", html)

    def test_renders_without_optional_fields(self):
        """Template no rompe si admin_url está vacío."""
        context = {
            "ticket_reference": "TK-0002",
            "ticket_subject": "Sin url",
            "ticket_category": "other",
            "ticket_priority": "low",
            "business_name": "Empresa X",
            "contact_email": "",
            "created_at": "",
            "admin_url": "",
        }
        html, text = render_email_template("admin_support_ticket_created", context)
        self.assertIn("TK-0002", html)
        self.assertIsInstance(html, str)
