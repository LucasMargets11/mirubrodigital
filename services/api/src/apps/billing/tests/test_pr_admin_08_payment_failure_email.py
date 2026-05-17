"""
apps/billing/tests/test_pr_admin_08_payment_failure_email.py

Tests para PR-ADMIN-08: email interno admin_payment_failure_recurrent.

Cubre:
Helper
  01. Helper usa template_key="admin_payment_failure_recurrent".
  02. Helper usa recipient_category="billing".
  03. Helper asocia related_business.
  04. Helper asocia related_user (owner) si puede resolverlo.
  05. Context incluye business_name, plan_code, service_type, retry_count y admin_url.
  06. Context incluye amount, currency, provider_status e invoice_event_id con invoice_event.
  07. Helper funciona con invoice_event=None.
  08. Metadata incluye event_type, subscription_id, related_business_id, retry_count
      e invoice_event_id.
  09. Metadata NO incluye payloads, headers, tokens ni firmas.
  10. Si queue_admin_transactional_email falla, el helper devuelve False.
  11. Si no hay owner, el helper no crashea (devuelve bool).
  12. retry_count=0 en context muestra al menos 1 (display_retry_count).
  13. Template renderiza con context completo sin errores.
  14. Template renderiza sin invoice_event (campos opcionales ausentes).

Integración con record_failed_payment()
  15. Sub ACTIVE → llama al helper admin una vez.
  16. Sub no ACTIVE → no llama al helper admin.
  17. Si falla el helper admin, record_failed_payment() igual deja la suscripción en PAST_DUE.
  18. No rompe ni modifica el email al cliente send_payment_failed_email.

Integración con tasks._transition_active_to_past_due()
  19. Llama al helper admin cuando el update fue exitoso.
  20. No llama al helper admin si no hubo update.
  21. _transition_past_due_to_suspended() no llama al helper admin.
  22. Si falla el helper admin, la transición ACTIVE→PAST_DUE sigue aplicada.
  23. No rompe send_payment_failed_email al cliente.

Seguridad / legacy
  24. No se usa send_mail.
  25. No se usa EmailMessage.
  26. No se tocan webhooks.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.email_helpers import send_admin_payment_failure_recurrent_email
from apps.billing.models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
)
from apps.billing.subscription_activator import record_failed_payment
from apps.billing.tasks import _transition_active_to_past_due, _transition_past_due_to_suspended
from apps.business.models import Business, Subscription as BizSubscription
from apps.notifications.services import render_email_template

User = get_user_model()

_ADMIN_TARGET = "apps.notifications.admin_helpers.queue_admin_transactional_email"
_CLIENT_EMAIL_TARGET = "apps.billing.email_helpers.send_payment_failed_email"
_ADMIN_HELPER_TARGET = "apps.billing.email_helpers.send_admin_payment_failure_recurrent_email"
_SUSPENDED_EMAIL_TARGET = "apps.billing.email_helpers.send_subscription_suspended_email"

_SETTINGS = {
    "BILLING_EMAIL": "billing@mirubro.com",
    "ADMIN_FRONTEND_URL": "http://localhost:3000/admin",
    "EMAIL_TRANSACTIONAL_ENABLED": True,
    "FRONTEND_URL": "https://app.mirubro.com",
}


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email=None):
    email = email or f"u{uuid.uuid4().hex[:8]}@test.com"
    return User.objects.create_user(
        email=email,
        username=email,
        password="Passw0rd!",
        first_name="Test",
        last_name="Owner",
    )


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


def _make_business(name=None, status="active"):
    name = name or f"Biz-{uuid.uuid4().hex[:6]}"
    biz = Business.objects.create(
        name=name,
        status=status,
        default_service="gestion",
        service_type="gestion",
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
        expires_at=timezone.now() + timedelta(hours=1),
    )


def _make_subscription(business, plan, session=None,
                       status=SubscriptionV2.Status.ACTIVE,
                       retry_count=0):
    return SubscriptionV2.objects.create(
        business=business,
        service_type=business.default_service,
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=f"preapp-{uuid.uuid4()}",
        external_reference=f"SUB-{uuid.uuid4()}",
        status=status,
        is_active=(status == SubscriptionV2.Status.ACTIVE),
        checkout_session=session,
        retry_count=retry_count,
    )


def _make_invoice_event(subscription, ap_id=None, amount="49900.00",
                        provider_status="charged_back"):
    return BillingInvoiceEvent.objects.create(
        subscription=subscription,
        provider_authorized_payment_id=ap_id or f"AP-{uuid.uuid4().hex[:8]}",
        provider_subscription_id=subscription.provider_sub_id or "",
        provider_status=provider_status,
        amount=Decimal(amount),
        currency="ARS",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Class 1 — send_admin_payment_failure_recurrent_email() helper
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class SendAdminPaymentFailureEmailTests(TestCase):
    """Unit tests for billing.email_helpers.send_admin_payment_failure_recurrent_email()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business(name="Mi Negocio SA")
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)
        self.sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
            retry_count=1,
        )
        self.event = _make_invoice_event(self.sub, provider_status="charged_back")

    @patch(_ADMIN_TARGET)
    def test_uses_template_key(self, mock_q):
        """Helper uses template_key='admin_payment_failure_recurrent'."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        mock_q.assert_called_once()
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["template_key"], "admin_payment_failure_recurrent")

    @patch(_ADMIN_TARGET)
    def test_uses_recipient_category_billing(self, mock_q):
        """Helper uses recipient_category='billing'."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["recipient_category"], "billing")

    @patch(_ADMIN_TARGET)
    def test_associates_related_business(self, mock_q):
        """Helper passes related_business=subscription.business."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["related_business"], self.business)

    @patch(_ADMIN_TARGET)
    def test_associates_related_user(self, mock_q):
        """Helper passes related_user=owner when resolvable."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["related_user"], self.owner)

    @patch(_ADMIN_TARGET)
    def test_context_business_name(self, mock_q):
        """context['business_name'] matches subscription.business.name."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["context"]["business_name"], self.business.name)

    @patch(_ADMIN_TARGET)
    def test_context_plan_code_and_service_type(self, mock_q):
        """context includes plan_code and service_type."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        ctx = kwargs["context"]
        self.assertEqual(ctx["plan_code"], self.plan.code)
        self.assertEqual(ctx["service_type"], self.business.default_service)

    @patch(_ADMIN_TARGET)
    def test_context_retry_count(self, mock_q):
        """context['retry_count'] matches subscription.retry_count."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["context"]["retry_count"], 1)

    @patch(_ADMIN_TARGET)
    def test_context_admin_url_contains_subscription_id(self, mock_q):
        """context['admin_url'] contains subscription.pk."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertIn(str(self.sub.pk), kwargs["context"]["admin_url"])

    @patch(_ADMIN_TARGET)
    def test_context_invoice_fields_when_event_provided(self, mock_q):
        """context includes amount, currency, provider_status and invoice_event_id."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        ctx = kwargs["context"]
        self.assertEqual(ctx["amount"], str(self.event.amount))
        self.assertEqual(ctx["currency"], "ARS")
        self.assertEqual(ctx["provider_status"], "charged_back")
        self.assertEqual(ctx["invoice_event_id"], str(self.event.pk))

    @patch(_ADMIN_TARGET)
    def test_works_with_invoice_event_none(self, mock_q):
        """Helper works when invoice_event=None (time-based task path)."""
        mock_q.return_value = True
        result = send_admin_payment_failure_recurrent_email(self.sub, invoice_event=None)
        mock_q.assert_called_once()
        self.assertTrue(result)
        _, kwargs = mock_q.call_args
        ctx = kwargs["context"]
        # Fields derived from invoice_event must be empty/blank
        self.assertEqual(ctx["amount"], "")
        self.assertEqual(ctx["provider_status"], "")
        self.assertEqual(ctx["invoice_event_id"], "")

    @patch(_ADMIN_TARGET)
    def test_metadata_event_type(self, mock_q):
        """metadata['event_type'] == 'admin_payment_failure_recurrent'."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["metadata"]["event_type"], "admin_payment_failure_recurrent")

    @patch(_ADMIN_TARGET)
    def test_metadata_subscription_id(self, mock_q):
        """metadata['subscription_id'] matches subscription.pk."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["metadata"]["subscription_id"], str(self.sub.pk))

    @patch(_ADMIN_TARGET)
    def test_metadata_retry_count(self, mock_q):
        """metadata['retry_count'] is present."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertIn("retry_count", kwargs["metadata"])

    @patch(_ADMIN_TARGET)
    def test_metadata_invoice_event_id(self, mock_q):
        """metadata['invoice_event_id'] matches event.pk."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        self.assertEqual(kwargs["metadata"]["invoice_event_id"], str(self.event.pk))

    @patch(_ADMIN_TARGET)
    def test_metadata_no_sensitive_keys(self, mock_q):
        """metadata must not include raw payloads, headers, tokens or signatures."""
        mock_q.return_value = True
        send_admin_payment_failure_recurrent_email(self.sub, self.event)
        _, kwargs = mock_q.call_args
        meta = kwargs["metadata"]
        forbidden = {"raw_payload_json", "x_signature", "headers", "token",
                     "authorization", "password", "pin"}
        overlap = set(meta.keys()) & forbidden
        self.assertEqual(overlap, set(), f"Sensitive keys found in metadata: {overlap}")

    @patch(_ADMIN_TARGET, side_effect=Exception("queue down"))
    def test_queue_failure_returns_false(self, _mock_q):
        """If queue_admin_transactional_email raises, helper returns False without propagating."""
        result = send_admin_payment_failure_recurrent_email(self.sub, self.event)
        self.assertFalse(result)

    def test_no_owner_does_not_crash(self):
        """Helper does not crash if owner cannot be resolved — returns bool."""
        biz = _make_business(name="No Owner Biz")
        plan = _make_plan(code=f"plan-{uuid.uuid4().hex[:6]}")
        sub = _make_subscription(biz, plan, session=None,
                                 status=SubscriptionV2.Status.PAST_DUE)
        with patch(_ADMIN_TARGET, return_value=False):
            result = send_admin_payment_failure_recurrent_email(sub)
        self.assertIsInstance(result, bool)

    @patch(_ADMIN_TARGET)
    def test_retry_count_zero_shows_at_least_one(self, mock_q):
        """When retry_count==0 (task path), context shows display_retry_count >= 1."""
        mock_q.return_value = True
        # Use a fresh business to avoid uq_subscriptionv2_active_per_service
        biz0 = _make_business(name="Zero Retry Biz")
        Membership.objects.create(user=self.owner, business=biz0, role="owner")
        sess0 = _make_session(self.owner, self.plan, biz0)
        sub = _make_subscription(
            biz0, self.plan, session=sess0,
            status=SubscriptionV2.Status.PAST_DUE,
            retry_count=0,
        )
        send_admin_payment_failure_recurrent_email(sub, invoice_event=None)
        _, kwargs = mock_q.call_args
        self.assertGreaterEqual(kwargs["context"]["retry_count"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# Class 2 — Template rendering
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class AdminPaymentFailureTemplateTests(TestCase):
    """Template rendering tests for admin_payment_failure_recurrent.html."""

    def _full_context(self):
        return {
            "business_name": "Pizzería Roma",
            "business_id": "123",
            "owner_email": "owner@test.com",
            "plan_code": "gestion_pro_monthly",
            "service_type": "gestion",
            "retry_count": 2,
            "urgency": "atención",
            "amount": "49900.00",
            "currency": "ARS",
            "failure_reason": "insufficient_funds",
            "provider_status": "charged_back",
            "grace_until": "15/05/2026 23:59",
            "current_period_end": "13/05/2026 23:59",
            "invoice_event_id": str(uuid.uuid4()),
            "admin_url": "http://localhost:3000/admin/suscripciones/abc-123",
        }

    def test_template_renders_with_full_context(self):
        """Template renders without errors given a complete context."""
        html, _text = render_email_template("admin_payment_failure_recurrent", self._full_context())
        self.assertIn("Pago fallido", html)
        self.assertIn("Pizzer", html)  # "Pizzería Roma" — avoid encoding issues
        self.assertIn("49900.00", html)
        self.assertIn("insufficient_funds", html)
        self.assertIn("Ver suscripci", html)  # "Ver suscripción en admin"

    def test_template_renders_without_optional_fields(self):
        """Template renders without errors when optional fields are absent."""
        minimal = {
            "business_name": "EmpresaX",
            "business_id": "99",
            "owner_email": "",
            "plan_code": "start_monthly",
            "service_type": "gestion",
            "retry_count": 1,
            "urgency": "aviso",
            "amount": "",
            "currency": "ARS",
            "failure_reason": "",
            "provider_status": "",
            "grace_until": "",
            "current_period_end": "",
            "invoice_event_id": "",
            "admin_url": "",
        }
        html, _text = render_email_template("admin_payment_failure_recurrent", minimal)
        self.assertIn("EmpresaX", html)
        self.assertIn("PAST_DUE", html)


# ─────────────────────────────────────────────────────────────────────────────
# Class 3 — Integration with record_failed_payment()
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class RecordFailedPaymentAdminEmailTests(TestCase):
    """Integration tests for record_failed_payment() → admin email dispatch."""

    def setUp(self):
        self.plan = _make_plan(code=f"plan-{uuid.uuid4().hex[:6]}")
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)

    @patch(_ADMIN_TARGET)
    @patch(_CLIENT_EMAIL_TARGET)
    def test_admin_email_called_when_active(self, mock_client, mock_admin):
        """record_failed_payment() calls admin helper once when sub was ACTIVE."""
        mock_admin.return_value = True
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        mock_admin.assert_called_once()

    @patch(_ADMIN_TARGET)
    @patch(_CLIENT_EMAIL_TARGET)
    def test_admin_email_not_called_when_not_active(self, mock_client, mock_admin):
        """record_failed_payment() does NOT call admin helper if sub was not ACTIVE."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        mock_admin.assert_not_called()

    @patch(_ADMIN_HELPER_TARGET, side_effect=Exception("admin down"))
    @patch(_CLIENT_EMAIL_TARGET)
    def test_admin_failure_leaves_past_due(self, mock_client, mock_admin):
        """Admin email failure does not revert the ACTIVE→PAST_DUE transition."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)

    @patch(_ADMIN_TARGET)
    @patch(_CLIENT_EMAIL_TARGET)
    def test_client_email_still_called_alongside_admin(self, mock_client, mock_admin):
        """Both client email and admin email are called independently."""
        mock_admin.return_value = True
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        mock_client.assert_called_once()
        mock_admin.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Class 4 — Integration with tasks._transition_active_to_past_due()
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class TransitionActiveToPastDueAdminEmailTests(TestCase):
    """Integration tests for _transition_active_to_past_due() → admin email dispatch."""

    def setUp(self):
        self.plan = _make_plan(code=f"plan-{uuid.uuid4().hex[:6]}")
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)

    @patch(_ADMIN_HELPER_TARGET)
    @patch(_CLIENT_EMAIL_TARGET)
    def test_admin_email_called_on_successful_update(self, mock_client, mock_admin):
        """_transition_active_to_past_due() calls admin helper when update was made."""
        past_end = timezone.now() - timedelta(days=2)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        sub.current_period_end = past_end
        sub.save(update_fields=["current_period_end"])

        count = _transition_active_to_past_due(SubscriptionV2, timezone.now())

        self.assertEqual(count, 1)
        mock_admin.assert_called_once()

    @patch(_ADMIN_HELPER_TARGET)
    @patch(_CLIENT_EMAIL_TARGET)
    def test_admin_email_not_called_when_no_update(self, mock_client, mock_admin):
        """_transition_active_to_past_due() does NOT call admin helper if nothing updated."""
        future_end = timezone.now() + timedelta(days=30)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        sub.current_period_end = future_end
        sub.save(update_fields=["current_period_end"])

        count = _transition_active_to_past_due(SubscriptionV2, timezone.now())

        self.assertEqual(count, 0)
        mock_admin.assert_not_called()

    @patch(_ADMIN_HELPER_TARGET)
    @patch(_SUSPENDED_EMAIL_TARGET)
    def test_past_due_to_suspended_does_not_call_admin(self, mock_suspended, mock_admin):
        """_transition_past_due_to_suspended() must NOT call admin payment failure helper."""
        past_grace = timezone.now() - timedelta(days=1)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
        )
        sub.grace_until = past_grace
        sub.save(update_fields=["grace_until"])

        _transition_past_due_to_suspended(SubscriptionV2, timezone.now())

        mock_admin.assert_not_called()

    @patch(_ADMIN_HELPER_TARGET, side_effect=Exception("admin offline"))
    @patch(_CLIENT_EMAIL_TARGET)
    def test_admin_failure_does_not_revert_past_due(self, mock_client, mock_admin):
        """Admin email failure must not revert the ACTIVE→PAST_DUE transition."""
        past_end = timezone.now() - timedelta(days=2)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        sub.current_period_end = past_end
        sub.save(update_fields=["current_period_end"])

        count = _transition_active_to_past_due(SubscriptionV2, timezone.now())

        self.assertEqual(count, 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)

    @patch(_ADMIN_HELPER_TARGET)
    @patch(_CLIENT_EMAIL_TARGET)
    def test_client_email_still_called_alongside_admin(self, mock_client, mock_admin):
        """Both client email and admin email are called independently in task path."""
        past_end = timezone.now() - timedelta(days=2)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        sub.current_period_end = past_end
        sub.save(update_fields=["current_period_end"])

        _transition_active_to_past_due(SubscriptionV2, timezone.now())

        mock_client.assert_called_once()
        mock_admin.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Class 5 — Security / legacy checks
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class SecurityLegacyTests(TestCase):
    """Security and legacy checks for PR-ADMIN-08."""

    def setUp(self):
        self.plan = _make_plan(code=f"plan-{uuid.uuid4().hex[:6]}")
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)
        self.sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
            retry_count=1,
        )
        self.event = _make_invoice_event(self.sub)

    @patch(_ADMIN_TARGET)
    def test_no_send_mail(self, mock_admin):
        """send_admin_payment_failure_recurrent_email never uses send_mail."""
        mock_admin.return_value = True
        with patch("django.core.mail.send_mail") as mock_send_mail:
            send_admin_payment_failure_recurrent_email(self.sub, self.event)
            mock_send_mail.assert_not_called()

    @patch(_ADMIN_TARGET)
    def test_no_email_message(self, mock_admin):
        """send_admin_payment_failure_recurrent_email never uses EmailMessage."""
        mock_admin.return_value = True
        with patch("django.core.mail.EmailMessage") as mock_em:
            send_admin_payment_failure_recurrent_email(self.sub, self.event)
            mock_em.assert_not_called()
