"""
apps/billing/tests/test_pr_admin_03_subscription_payment_email.py

Tests para PR-ADMIN-03: email interno admin_subscription_payment_created.

Cubre:
  01. Helper usa template_key="admin_subscription_payment_created".
  02. Helper usa recipient_category="billing".
  03. Helper asocia related_business.
  04. Helper asocia related_user (owner) si puede resolverlo.
  05. Context incluye business_name, plan_code, service_type, amount, currency,
      paid_at, invoice_event_id y admin_url.
  06. Metadata incluye event_type, subscription_id, invoice_event_id,
      related_business_id, plan_code, service_type, amount y currency.
  07. Metadata NO incluye raw_payload_json, headers, tokens ni firmas.
  08. Si queue_admin_transactional_email falla, el helper devuelve False.
  09. Si no hay owner, el helper no crashea y puede enviar igual como email interno.
  10. En webhook con ap_status="authorized" y activated=True, se llama al helper una vez.
  11. En webhook con activated=False, NO se llama al helper.
  12. En webhook con ap_status!="authorized", NO se llama al helper.
  13. Si falla el helper, el webhook sigue procesándose correctamente.
  14. No se modifica ni se rompe subscription_activated.
  15. No se usa send_mail.
  16. No se usa EmailMessage.
  17. admin_url apunta al detalle de la suscripción en admin.
  18. Template admin_subscription_payment_created.html se renderiza sin errores.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.email_helpers import (
    get_owner_user,
    send_admin_subscription_payment_created_email,
)
from apps.billing.models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
    WebhookDelivery,
)
from apps.business.models import Business, Subscription as BizSubscription
from apps.notifications.services import render_email_template

User = get_user_model()

_ADMIN_HELPER_TARGET = "apps.notifications.admin_helpers.queue_admin_transactional_email"
_SEND_ACTIVATED_TARGET = "apps.billing.email_helpers.send_subscription_activated_email"
_SEND_ADMIN_TARGET = "apps.billing.email_helpers.send_admin_subscription_payment_created_email"
_ACTIVATE_TARGET = "apps.billing.subscription_activator.activate_subscription_from_invoice"
_MP_GET_AUTHORIZED = "apps.billing.mp_service.MercadoPagoService.get_authorized_payment"
_PROMO_CYCLE_TARGET = "apps.billing.promo_cycle_service.handle_promo_cycle"


# ─────────────────────────────────────────────────────────────────────────────
# Factories (reused from PR-7 pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email=None):
    email = email or f"u{uuid.uuid4().hex[:8]}@test.com"
    return User.objects.create_user(email=email, username=email, password="Passw0rd!")


def _make_plan(code="gestion_pro_monthly"):
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
                       status=SubscriptionV2.Status.CHECKOUT_PENDING):
    return SubscriptionV2.objects.create(
        business=business,
        service_type="gestion",
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=f"preapp-{uuid.uuid4()}",
        external_reference=f"SUB-{uuid.uuid4()}",
        status=status,
        checkout_session=session,
    )


def _make_invoice_event(subscription, amount="49900.00", provider_status="authorized"):
    return BillingInvoiceEvent.objects.create(
        subscription=subscription,
        provider_authorized_payment_id=f"AP-{uuid.uuid4().hex[:8]}",
        provider_subscription_id=subscription.provider_sub_id or "",
        provider_status=provider_status,
        amount=Decimal(amount),
        currency="ARS",
        paid_at=timezone.now(),
    )


def _make_webhook_delivery():
    return WebhookDelivery.objects.create(
        topic="subscription_authorized_payment",
        resource_id=f"AP-{uuid.uuid4().hex[:8]}",
        received_at=timezone.now(),
        processing_status=WebhookDelivery.ProcessingStatus.RECEIVED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 01-09: Direct helper unit tests
# ─────────────────────────────────────────────────────────────────────────────

class SendAdminPaymentCreatedEmailHelperTest(TestCase):
    """Unit tests for send_admin_subscription_payment_created_email()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business("Empresa Test SA")
        self.owner = _make_user("owner@empresa.com")
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        session = _make_session(self.owner, self.plan, self.business)
        self.subscription = _make_subscription(
            self.business, self.plan, session=session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        self.invoice = _make_invoice_event(self.subscription, amount="49900.00")

    # 01 — template_key correcto
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_uses_correct_template_key(self, mock_helper):
        result = send_admin_subscription_payment_created_email(
            self.subscription, self.invoice
        )
        self.assertTrue(result)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["template_key"], "admin_subscription_payment_created")

    # 02 — recipient_category="billing"
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_uses_billing_recipient_category(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["recipient_category"], "billing")

    # 03 — related_business correcto
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_associates_correct_business(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["related_business"], self.business)

    # 04 — related_user resuelto al owner
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_associates_owner_as_related_user(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        self.assertEqual(kwargs["related_user"], self.owner)

    # 05 — Context incluye campos requeridos
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_context_includes_required_fields(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        ctx = kwargs["context"]

        self.assertEqual(ctx["business_name"], self.business.name)
        self.assertEqual(ctx["plan_code"], self.subscription.plan_code)
        self.assertEqual(ctx["service_type"], self.subscription.service_type)
        self.assertIn(str(self.invoice.amount), ctx["amount"])
        self.assertEqual(ctx["currency"], "ARS")
        self.assertIn("paid_at", ctx)
        self.assertEqual(ctx["invoice_event_id"], str(self.invoice.pk))
        self.assertIn("admin_url", ctx)

    # 05b — admin_url apunta al detalle de la suscripción
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    @override_settings(ADMIN_FRONTEND_URL="http://localhost:3000/admin")
    def test_admin_url_points_to_subscription_detail(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        admin_url = kwargs["context"]["admin_url"]
        self.assertIn(f"/suscripciones/{self.subscription.pk}", admin_url)

    # 05c — admin_url no duplica /admin
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    @override_settings(ADMIN_FRONTEND_URL="http://localhost:3000/admin")
    def test_admin_url_does_not_duplicate_admin_prefix(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        admin_url = kwargs["context"]["admin_url"]
        self.assertNotIn("/admin/admin", admin_url)

    # 06 — Metadata incluye campos requeridos
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_metadata_includes_required_fields(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        meta = kwargs["metadata"]

        self.assertEqual(meta["event_type"], "admin_subscription_payment_created")
        self.assertEqual(meta["subscription_id"], str(self.subscription.pk))
        self.assertEqual(meta["invoice_event_id"], str(self.invoice.pk))
        self.assertEqual(meta["related_business_id"], str(self.business.pk))
        self.assertEqual(meta["plan_code"], self.subscription.plan_code)
        self.assertEqual(meta["service_type"], self.subscription.service_type)
        self.assertIn("amount", meta)
        self.assertEqual(meta["currency"], "ARS")

    # 07 — Metadata NO incluye datos sensibles
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_metadata_does_not_include_sensitive_data(self, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        _, kwargs = mock_helper.call_args
        meta = kwargs["metadata"]

        self.assertNotIn("raw_payload_json", meta)
        self.assertNotIn("headers", meta)
        self.assertNotIn("token", meta)
        self.assertNotIn("x_signature", meta)
        self.assertNotIn("authorization", meta)
        self.assertNotIn("password", meta)

    # 08 — Si queue_admin_transactional_email falla, devuelve False
    @patch(_ADMIN_HELPER_TARGET, side_effect=RuntimeError("Fallo simulado"))
    def test_returns_false_if_inner_helper_raises(self, mock_helper):
        result = send_admin_subscription_payment_created_email(
            self.subscription, self.invoice
        )
        self.assertFalse(result)

    # 08b — Si queue_admin_transactional_email devuelve False, el helper devuelve False
    @patch(_ADMIN_HELPER_TARGET, return_value=False)
    def test_returns_false_if_inner_helper_returns_false(self, mock_helper):
        result = send_admin_subscription_payment_created_email(
            self.subscription, self.invoice
        )
        self.assertFalse(result)

    # 09 — Sin owner, no crashea y puede enviar igual
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    def test_no_owner_does_not_crash(self, mock_helper):
        """When no owner is resolvable, the helper still attempts the email with related_user=None."""
        business_no_owner = _make_business("Sin Owner SA")
        sub = _make_subscription(business_no_owner, self.plan)
        invoice = _make_invoice_event(sub)

        result = send_admin_subscription_payment_created_email(sub, invoice)
        # Should have called the helper (best-effort), returning True or False based on mock
        self.assertTrue(result)
        _, kwargs = mock_helper.call_args
        self.assertIsNone(kwargs["related_user"])

    # 15 — No usa send_mail
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    @patch("django.core.mail.send_mail")
    def test_does_not_use_send_mail(self, mock_send_mail, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        mock_send_mail.assert_not_called()

    # 16 — No usa EmailMessage
    @patch(_ADMIN_HELPER_TARGET, return_value=True)
    @patch("django.core.mail.EmailMessage")
    def test_does_not_use_email_message(self, mock_email_msg, mock_helper):
        send_admin_subscription_payment_created_email(self.subscription, self.invoice)
        mock_email_msg.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 10-14: Integration tests via webhook processor
# ─────────────────────────────────────────────────────────────────────────────

class WebhookProcessorAdminEmailIntegrationTest(TestCase):
    """
    Verify the admin email is triggered/skipped based on ap_status and activated flag.
    Uses mocks to avoid real MP API calls and real Celery dispatch.

    Follows the exact same patching pattern as test_pr7_subscription_activated_email.py.
    """

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business("WebhookBiz SA")
        self.owner = _make_user("hook_owner@test.com")
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        session = _make_session(self.owner, self.plan, self.business)
        self.subscription = _make_subscription(
            self.business, self.plan, session=session,
        )
        self.ap_id = f"AP-{uuid.uuid4().hex[:8]}"
        self.delivery = _make_webhook_delivery()
        self.delivery.resource_id = self.ap_id
        self.delivery.save()
        self._ap_data = {
            "id": self.ap_id,
            "status": "authorized",
            "preapproval_id": self.subscription.provider_sub_id,
            "payment_id": f"pay-{uuid.uuid4().hex[:6]}",
            "transaction_amount": 49900,
            "currency_id": "ARS",
            "date_approved": "2026-05-10T14:00:00.000-03:00",
        }

    # 10 — authorized + activated=True → admin helper llamado una vez
    def test_authorized_activated_calls_admin_helper_once(self):
        with (
            patch(_MP_GET_AUTHORIZED, return_value=self._ap_data),
            patch(_ACTIVATE_TARGET, return_value=True),
            patch(_PROMO_CYCLE_TARGET),
            patch(_SEND_ACTIVATED_TARGET),
            patch(_SEND_ADMIN_TARGET) as mock_admin_email,
        ):
            from apps.billing.webhook_processor import _handle_authorized_payment
            _handle_authorized_payment(self.ap_id, self.delivery)

        mock_admin_email.assert_called_once()

    # 11 — activated=False → admin helper NO llamado
    def test_activated_false_does_not_call_admin_helper(self):
        with (
            patch(_MP_GET_AUTHORIZED, return_value=self._ap_data),
            patch(_ACTIVATE_TARGET, return_value=False),
            patch(_PROMO_CYCLE_TARGET),
            patch(_SEND_ACTIVATED_TARGET),
            patch(_SEND_ADMIN_TARGET) as mock_admin_email,
        ):
            from apps.billing.webhook_processor import _handle_authorized_payment
            _handle_authorized_payment(self.ap_id, self.delivery)

        mock_admin_email.assert_not_called()

    # 12 — ap_status != "authorized" → admin helper NO llamado
    def test_non_authorized_status_does_not_call_admin_helper(self):
        ap_data_pending = {**self._ap_data, "status": "pending"}
        with (
            patch(_MP_GET_AUTHORIZED, return_value=ap_data_pending),
            patch(_ACTIVATE_TARGET, return_value=False),
            patch(_PROMO_CYCLE_TARGET),
            patch(_SEND_ACTIVATED_TARGET),
            patch(_SEND_ADMIN_TARGET) as mock_admin_email,
        ):
            from apps.billing.webhook_processor import _handle_authorized_payment
            _handle_authorized_payment(self.ap_id, self.delivery)

        mock_admin_email.assert_not_called()

    # 13 — Si falla el admin helper, el webhook sigue procesándose sin excepción
    def test_admin_helper_failure_does_not_break_webhook(self):
        """webhook_processor must not propagate admin email exceptions."""
        with (
            patch(_MP_GET_AUTHORIZED, return_value=self._ap_data),
            patch(_ACTIVATE_TARGET, return_value=True),
            patch(_PROMO_CYCLE_TARGET),
            patch(_SEND_ACTIVATED_TARGET),
            patch(_SEND_ADMIN_TARGET, side_effect=RuntimeError("Celery caído")),
        ):
            from apps.billing.webhook_processor import _handle_authorized_payment
            try:
                _handle_authorized_payment(self.ap_id, self.delivery)
            except Exception as exc:
                self.fail(
                    f"_handle_authorized_payment propagated an exception: {exc}"
                )

    # 14 — client subscription_activated email is still called, unchanged
    def test_client_subscription_activated_email_still_fires(self):
        with (
            patch(_MP_GET_AUTHORIZED, return_value=self._ap_data),
            patch(_ACTIVATE_TARGET, return_value=True),
            patch(_PROMO_CYCLE_TARGET),
            patch(_SEND_ACTIVATED_TARGET) as mock_client_email,
            patch(_SEND_ADMIN_TARGET),
        ):
            from apps.billing.webhook_processor import _handle_authorized_payment
            _handle_authorized_payment(self.ap_id, self.delivery)

        mock_client_email.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 18: Template rendering
# ─────────────────────────────────────────────────────────────────────────────

class AdminSubscriptionPaymentCreatedTemplateTest(TestCase):
    """admin_subscription_payment_created.html se renderiza sin errores."""

    def test_full_context_renders_correctly(self):
        context = {
            "business_name": "Empresa Ejemplo SA",
            "business_id": "biz-123",
            "owner_email": "owner@empresa.com",
            "plan_code": "gestion_pro_monthly",
            "service_type": "gestion",
            "amount": "49900.00",
            "currency": "ARS",
            "paid_at": "10/05/2026 14:30",
            "invoice_event_id": "inv-event-uuid-001",
            "admin_url": "http://localhost:3000/admin/suscripciones/sub-uuid-001",
        }
        html, text = render_email_template("admin_subscription_payment_created", context)
        self.assertIn("Empresa Ejemplo SA", html)
        self.assertIn("gestion_pro_monthly", html)
        self.assertIn("49900.00", html)
        self.assertIn("NOTIFICACIÓN INTERNA", html)
        self.assertIn("Ver suscripción en admin", html)
        self.assertIn("admin/suscripciones/sub-uuid-001", html)

    def test_renders_without_optional_owner_email(self):
        context = {
            "business_name": "Sin Owner",
            "business_id": "biz-456",
            "owner_email": "",
            "plan_code": "menu_qr_basic_monthly",
            "service_type": "menu_qr",
            "amount": "9900.00",
            "currency": "ARS",
            "paid_at": "",
            "invoice_event_id": "inv-event-uuid-002",
            "admin_url": "",
        }
        html, text = render_email_template("admin_subscription_payment_created", context)
        self.assertIn("Sin Owner", html)
        self.assertIsInstance(html, str)
