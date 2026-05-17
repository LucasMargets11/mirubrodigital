"""
apps/billing/tests/test_pr_admin_04_cancellation_request_email.py

Tests para PR-ADMIN-04: email interno admin_cancellation_request_received.

Cubre:
  01. Helper usa template_key="admin_cancellation_request_received".
  02. Helper usa recipient_category="operations".
  03. Helper asocia related_business.
  04. Helper asocia related_user (owner) si puede resolverlo.
  05. Context incluye business_name, plan_code, service_type, cancel_requested_at,
      cancel_reason, effective_date y admin_url.
  06. Metadata incluye event_type, subscription_id, related_business_id,
      plan_code y service_type.
  07. Metadata NO incluye tokens, payloads MP, headers ni datos sensibles.
  08. Si queue_admin_transactional_email falla, el helper devuelve False.
  09. Si no hay owner, el helper no crashea.
  10. schedule_cancellation() exitoso llama al helper una vez.
  11. schedule_cancellation() con baja ya programada NO llama al helper.
  12. Si schedule_cancellation() falla por validación (status inválido), NO llama.
  13. Si falla el helper, la baja igual queda programada.
  14. execute_cancellation() NO llama a send_admin_cancellation_request_received_email.
  15. undo_cancellation() NO llama a send_admin_cancellation_request_received_email.
  16. No se modifica ni se rompe cancellation_confirmed.
  17. No se usa send_mail.
  18. No se usa EmailMessage.
  19. Template admin_cancellation_request_received.html se renderiza sin errores.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.cancellation_service import (
    CancellationError,
    execute_cancellation,
    schedule_cancellation,
    undo_cancellation,
)
from apps.billing.email_helpers import send_admin_cancellation_request_received_email
from apps.billing.models import MpCheckoutSession, Plan, SubscriptionV2
from apps.business.models import Business, Subscription as BizSubscription
from apps.notifications.services import render_email_template

User = get_user_model()

_ADMIN_HELPER_TARGET = "apps.notifications.admin_helpers.queue_admin_transactional_email"
_SEND_CANCELLATION_CONFIRMED = "apps.billing.email_helpers.send_cancellation_confirmed_email"
_SEND_ADMIN_CANCEL_TARGET = (
    "apps.billing.email_helpers.send_admin_cancellation_request_received_email"
)
_MP_UPDATE = "apps.billing.mp_service.MercadoPagoService.update_preapproval"


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email=None):
    email = email or f"u{uuid.uuid4().hex[:8]}@test.com"
    return User.objects.create_user(email=email, username=email, password="Passw0rd!")


def _make_plan(code=None):
    code = code or f"gestion_pro_monthly_{uuid.uuid4().hex[:6]}"
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults=dict(
            name="Gestión Pro",
            price=Decimal("49900"),
            currency="ARS",
            interval="monthly",
            plan_status="active",
        ),
    )
    return plan


def _make_business(name=None):
    name = name or f"Biz-{uuid.uuid4().hex[:6]}"
    biz = Business.objects.create(
        name=name, status="active", default_service="gestion", service_type="gestion",
    )
    BizSubscription.objects.create(business=biz, plan="start", status="active")
    return biz


def _make_session(user, plan, tenant):
    return MpCheckoutSession.objects.create(
        user=user,
        plan=plan,
        tenant=tenant,
        status=MpCheckoutSession.Status.LINKED,
        provider_preapproval_plan_id=f"PLAN-{uuid.uuid4().hex[:8]}",
        idempotency_key=f"key-{uuid.uuid4()}",
        mp_external_reference=f"SESS-{uuid.uuid4()}",
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )


def _make_subscription(business, plan, session=None,
                       status=SubscriptionV2.Status.ACTIVE,
                       cancel_at_period_end=False):
    return SubscriptionV2.objects.create(
        business=business,
        service_type="gestion",
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=f"preapp-{uuid.uuid4()}",
        external_reference=f"SUB-{uuid.uuid4()}",
        status=status,
        is_active=(status == SubscriptionV2.Status.ACTIVE),
        cancel_at_period_end=cancel_at_period_end,
        checkout_session=session,
        current_period_end=timezone.now() + timezone.timedelta(days=15),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 01-09: Helper unit tests
# ─────────────────────────────────────────────────────────────────────────────

class SendAdminCancellationRequestEmailHelperTest(TestCase):
    """Unit tests for send_admin_cancellation_request_received_email()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business("Empresa Test SA")
        self.owner = _make_user("owner@empresa.com")
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        session = _make_session(self.owner, self.plan, self.business)
        self.subscription = _make_subscription(self.business, self.plan, session=session)
        # Simulate that a cancellation was just scheduled
        self.subscription.cancel_at_period_end = True
        self.subscription.cancel_requested_at = timezone.now()
        self.subscription.cancel_reason = "Too expensive"
        self.subscription.save(update_fields=[
            "cancel_at_period_end", "cancel_requested_at", "cancel_reason",
        ])

    # 01 — template_key correcto
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_uses_correct_template_key(self, mock_helper):
        result = send_admin_cancellation_request_received_email(self.subscription)
        self.assertTrue(result)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["template_key"], "admin_cancellation_request_received")

    # 02 — recipient_category="operations"
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_uses_operations_recipient_category(self, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["recipient_category"], "operations")

    # 03 — related_business correcto
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_associates_correct_business(self, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["related_business"], self.business)

    # 04 — related_user resuelto al owner
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_associates_owner_as_related_user(self, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["related_user"], self.owner)

    # 05 — Context incluye campos requeridos
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_context_includes_required_fields(self, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        _, kwargs = mock_helper.call_args
        ctx = kwargs["context"]

        self.assertEqual(ctx["business_name"], self.business.name)
        self.assertEqual(ctx["plan_code"], self.subscription.plan_code)
        self.assertEqual(ctx["service_type"], self.subscription.service_type)
        self.assertIn("cancel_requested_at", ctx)
        self.assertIn("cancel_reason", ctx)
        self.assertIn("effective_date", ctx)
        self.assertIn("admin_url", ctx)
        self.assertIn(f"/suscripciones/{self.subscription.pk}", ctx["admin_url"])

    # 05b — cancel_reason presente en el context cuando está disponible
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_context_includes_cancel_reason(self, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["context"]["cancel_reason"], "Too expensive")

    # 06 — Metadata incluye campos requeridos
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_metadata_includes_required_fields(self, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        _, kwargs = mock_helper.call_args
        meta = kwargs["metadata"]

        self.assertEqual(meta["event_type"], "admin_cancellation_request_received")
        self.assertEqual(meta["subscription_id"], str(self.subscription.pk))
        self.assertEqual(meta["related_business_id"], str(self.business.pk))
        self.assertEqual(meta["plan_code"], self.subscription.plan_code)
        self.assertEqual(meta["service_type"], self.subscription.service_type)

    # 07 — Metadata NO incluye datos sensibles
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_metadata_does_not_include_sensitive_data(self, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        _, kwargs = mock_helper.call_args
        meta = kwargs["metadata"]

        self.assertNotIn("token", meta)
        self.assertNotIn("password", meta)
        self.assertNotIn("raw_payload_json", meta)
        self.assertNotIn("headers", meta)
        self.assertNotIn("x_signature", meta)
        self.assertNotIn("authorization", meta)

    # 08 — Si queue_admin_transactional_email falla, devuelve False
    @patch(_ADMIN_HELPER_TARGET, side_effect=RuntimeError("Fallo simulado"))
    def test_returns_false_if_inner_helper_raises(self, mock_helper):
        result = send_admin_cancellation_request_received_email(self.subscription)
        self.assertFalse(result)

    # 09 — Sin owner, no crashea
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_no_owner_does_not_crash(self, mock_helper):
        business_no_owner = _make_business("Sin Owner SA")
        sub = _make_subscription(business_no_owner, self.plan)
        result = send_admin_cancellation_request_received_email(sub)
        self.assertTrue(result)
        _, kwargs = mock_helper.call_args
        self.assertIsNone(kwargs["related_user"])

    # 17 — No usa send_mail
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    @patch("django.core.mail.send_mail")
    def test_does_not_use_send_mail(self, mock_send_mail, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        mock_send_mail.assert_not_called()

    # 18 — No usa EmailMessage
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    @patch("django.core.mail.EmailMessage")
    def test_does_not_use_email_message(self, mock_email_msg, mock_helper):
        send_admin_cancellation_request_received_email(self.subscription)
        mock_email_msg.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 10-15: Integration tests via cancellation_service
# ─────────────────────────────────────────────────────────────────────────────

class ScheduleCancellationAdminEmailIntegrationTest(TestCase):
    """
    Verify the admin email is triggered/skipped based on schedule_cancellation() outcome.
    """

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business("Biz Cancelación")
        self.owner = _make_user("cancel_owner@test.com")
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        session = _make_session(self.owner, self.plan, self.business)
        self.subscription = _make_subscription(
            self.business, self.plan, session=session,
            status=SubscriptionV2.Status.ACTIVE,
        )

    # 10 — schedule_cancellation() exitoso → admin helper llamado una vez
    @patch(_SEND_ADMIN_CANCEL_TARGET)
    def test_schedule_cancellation_calls_admin_helper_once(self, mock_admin_email):
        schedule_cancellation(self.subscription, reason="Ya no lo necesito")
        mock_admin_email.assert_called_once()

    # 11 — baja ya programada → CancellationError levantado antes → NO llama al helper
    @patch(_SEND_ADMIN_CANCEL_TARGET)
    def test_already_scheduled_does_not_call_admin_helper(self, mock_admin_email):
        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=["cancel_at_period_end"])

        with self.assertRaises(CancellationError):
            schedule_cancellation(self.subscription)

        mock_admin_email.assert_not_called()

    # 12 — status inválido → CancellationError → NO llama al helper
    @patch(_SEND_ADMIN_CANCEL_TARGET)
    def test_invalid_status_does_not_call_admin_helper(self, mock_admin_email):
        self.subscription.status = SubscriptionV2.Status.CANCELED
        self.subscription.save(update_fields=["status"])

        with self.assertRaises(CancellationError):
            schedule_cancellation(self.subscription)

        mock_admin_email.assert_not_called()

    # 13 — Si falla el helper, la baja igual queda programada
    @patch(_SEND_ADMIN_CANCEL_TARGET, side_effect=RuntimeError("Email caído"))
    def test_helper_failure_does_not_revert_cancellation(self, mock_admin_email):
        result = schedule_cancellation(self.subscription, reason="Prueba fallo")
        result.refresh_from_db()
        self.assertTrue(result.cancel_at_period_end)
        self.assertIsNotNone(result.cancel_requested_at)

    # 14 — execute_cancellation() NO llama al helper de solicitud de baja
    @patch(_SEND_ADMIN_CANCEL_TARGET)
    @patch(_SEND_CANCELLATION_CONFIRMED)
    @patch(_MP_UPDATE, return_value={"status": "cancelled"})
    def test_execute_cancellation_does_not_call_admin_helper(
        self, mock_mp, mock_confirmed, mock_admin_email
    ):
        self.subscription.status = SubscriptionV2.Status.ACTIVE
        self.subscription.is_active = True
        self.subscription.save(update_fields=["status", "is_active"])

        execute_cancellation(self.subscription)

        mock_admin_email.assert_not_called()

    # 15 — undo_cancellation() NO llama al helper de solicitud de baja
    @patch(_SEND_ADMIN_CANCEL_TARGET)
    def test_undo_cancellation_does_not_call_admin_helper(self, mock_admin_email):
        # First schedule
        self.subscription.cancel_at_period_end = True
        self.subscription.cancel_requested_at = timezone.now()
        self.subscription.current_period_end = timezone.now() + timezone.timedelta(days=15)
        self.subscription.save(update_fields=[
            "cancel_at_period_end", "cancel_requested_at", "current_period_end",
        ])

        undo_cancellation(self.subscription)

        mock_admin_email.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 16: cancellation_confirmed not modified
# ─────────────────────────────────────────────────────────────────────────────

class CancellationConfirmedNotModifiedTest(TestCase):
    """
    Structural test: schedule_cancellation() must not touch send_cancellation_confirmed_email.
    execute_cancellation() still fires cancellation_confirmed (unchanged).
    """

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business("Biz Confirmed")
        self.owner = _make_user("conf_owner@test.com")
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        session = _make_session(self.owner, self.plan, self.business)
        self.subscription = _make_subscription(
            self.business, self.plan, session=session,
            status=SubscriptionV2.Status.ACTIVE,
        )

    # schedule_cancellation does NOT call cancellation_confirmed
    @patch(_SEND_ADMIN_CANCEL_TARGET)
    @patch(_SEND_CANCELLATION_CONFIRMED)
    def test_schedule_cancellation_does_not_call_cancellation_confirmed(
        self, mock_confirmed, mock_admin_email
    ):
        schedule_cancellation(self.subscription)
        mock_confirmed.assert_not_called()

    # execute_cancellation still fires cancellation_confirmed
    @patch(_SEND_CANCELLATION_CONFIRMED)
    @patch(_MP_UPDATE, return_value={"status": "cancelled"})
    def test_execute_cancellation_still_fires_cancellation_confirmed(
        self, mock_mp, mock_confirmed
    ):
        execute_cancellation(self.subscription)
        mock_confirmed.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 19: Template rendering
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancellationRequestReceivedTemplateTest(TestCase):
    """admin_cancellation_request_received.html se renderiza sin errores."""

    def test_full_context_renders_correctly(self):
        context = {
            "business_name": "Empresa Ejemplo SA",
            "business_id": "biz-123",
            "owner_email": "owner@empresa.com",
            "plan_code": "gestion_pro_monthly",
            "service_type": "gestion",
            "cancel_requested_at": "10/05/2026 14:30",
            "effective_date": "31/05/2026 23:59",
            "cancel_reason": "No lo necesito más",
            "admin_url": "http://localhost:3000/admin/suscripciones/sub-uuid-001",
        }
        html, text = render_email_template("admin_cancellation_request_received", context)
        self.assertIn("Empresa Ejemplo SA", html)
        self.assertIn("gestion_pro_monthly", html)
        self.assertIn("NOTIFICACIÓN INTERNA", html)
        self.assertIn("Ver suscripción en admin", html)
        self.assertIn("Solicitud de baja recibida", html)
        self.assertIn("No lo necesito más", html)
        self.assertIn("admin/suscripciones/sub-uuid-001", html)

    def test_renders_without_optional_fields(self):
        context = {
            "business_name": "Biz Sin Datos",
            "business_id": "biz-456",
            "owner_email": "",
            "plan_code": "menu_qr_basic_monthly",
            "service_type": "menu_qr",
            "cancel_requested_at": "",
            "effective_date": "",
            "cancel_reason": "",
            "admin_url": "",
        }
        html, text = render_email_template("admin_cancellation_request_received", context)
        self.assertIn("Biz Sin Datos", html)
        self.assertIsInstance(html, str)
