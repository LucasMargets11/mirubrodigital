"""
Tests for PR-7: subscription_activated email.

Covers:
  1.  activate_subscription_from_invoice() returns True  → email enqueued.
  2.  activate_subscription_from_invoice() returns False → email NOT enqueued.
  3.  EmailDelivery uses template_key="subscription_activated".
  4.  Owner is the email recipient (to_email).
  5.  EmailDelivery is associated with the business.
  6.  Rendered HTML includes business_name and plan_name.
  7.  Owner without email → no crash, send returns False, no delivery created.
  8.  queue_transactional_email raises → activation NOT reverted (sub stays ACTIVE).
  9.  Duplicate webhook guard (activated=False) → no second email dispatched.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.email_helpers import get_owner_user, send_subscription_activated_email
from apps.billing.models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
    WebhookDelivery,
)
from apps.billing.webhook_processor import _handle_authorized_payment
from apps.business.models import Business, Subscription as BizSubscription
from apps.notifications.models import EmailDelivery
from apps.notifications.providers.base import EmailSendResult

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def _mock_email_provider(success=True):
    mock = MagicMock()
    mock.provider_name = "django"
    mock.send_email.return_value = EmailSendResult(
        success=success,
        provider_message_id="test-msg-pr7",
    )
    return mock


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
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )


def _make_subscription(business, plan, session=None,
                       status=SubscriptionV2.Status.CHECKOUT_PENDING):
    return SubscriptionV2.objects.create(
        business=business,
        service_type=business.default_service,
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=f"preapp-{uuid.uuid4()}",
        external_reference=f"SUB-{uuid.uuid4()}",
        status=status,
        checkout_session=session,
    )


def _make_invoice_event(subscription, ap_id=None, amount="49900.00",
                        provider_status="authorized"):
    return BillingInvoiceEvent.objects.create(
        subscription=subscription,
        provider_authorized_payment_id=ap_id or f"AP-{uuid.uuid4().hex[:8]}",
        provider_subscription_id=subscription.provider_sub_id or "",
        provider_status=provider_status,
        amount=Decimal(amount),
        currency="ARS",
    )


def _make_webhook_delivery(resource_id="AP-test-001"):
    return WebhookDelivery.objects.create(
        topic="subscription_authorized_payment",
        resource_id=resource_id,
        received_at=timezone.now(),
        processing_status=WebhookDelivery.ProcessingStatus.RECEIVED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Class 1 — get_owner_user() helper
# ─────────────────────────────────────────────────────────────────────────────

class GetOwnerUserTests(TestCase):
    """Unit tests for billing.email_helpers.get_owner_user()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")

    def test_resolves_from_checkout_session_user(self):
        """Primary path: subscription.checkout_session.user returned when it has email."""
        session = _make_session(self.owner, self.plan, self.business)
        sub = _make_subscription(self.business, self.plan, session=session)

        result = get_owner_user(sub)

        self.assertEqual(result, self.owner)

    def test_falls_back_to_membership_when_session_user_has_no_email(self):
        """When session.user has no email, falls back to Membership query."""
        no_email_user = _make_user()
        no_email_user.email = ""
        no_email_user.save()
        session = _make_session(no_email_user, self.plan, self.business)
        sub = _make_subscription(self.business, self.plan, session=session)

        result = get_owner_user(sub)

        # Should resolve to the Membership owner (self.owner) via fallback
        self.assertEqual(result, self.owner)

    def test_falls_back_to_membership_when_no_session(self):
        """When checkout_session is None, resolves owner from Membership."""
        sub = _make_subscription(self.business, self.plan, session=None)

        result = get_owner_user(sub)

        self.assertEqual(result, self.owner)

    def test_returns_none_when_owner_has_no_email(self):
        """Returns None when the only owner Membership user has no email."""
        self.owner.email = ""
        self.owner.save()
        sub = _make_subscription(self.business, self.plan, session=None)

        result = get_owner_user(sub)

        self.assertIsNone(result)

    def test_returns_none_when_no_owner_membership(self):
        """Returns None when no Membership with role='owner' exists for the business."""
        empty_biz = _make_business(name="Empty")
        plan = _make_plan(code="other_plan")
        sub = _make_subscription(empty_biz, plan, session=None)

        result = get_owner_user(sub)

        self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────────────
# Class 2 — send_subscription_activated_email()
# ─────────────────────────────────────────────────────────────────────────────

EMAIL_SETTINGS = dict(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    SUPPORT_EMAIL="soporte@mirubro.com",
)


@override_settings(**EMAIL_SETTINGS)
class SendSubscriptionActivatedEmailTests(TestCase):
    """Unit tests for billing.email_helpers.send_subscription_activated_email()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business(name="Panadería Don José")
        self.owner = _make_user(email="owner@panaderia.com")
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        session = _make_session(self.owner, self.plan, self.business)
        self.subscription = _make_subscription(self.business, self.plan, session=session)
        self.invoice_event = _make_invoice_event(self.subscription, amount="49900.00")

    # ── Test 3: correct template_key ─────────────────────────────────────────

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_correct_template_key(self, mock_get_provider):
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_activated_email(self.subscription, self.invoice_event)

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.template_key, "subscription_activated")

    # ── Test 4: owner is the recipient ───────────────────────────────────────

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_owner_email_as_recipient(self, mock_get_provider):
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_activated_email(self.subscription, self.invoice_event)

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.to_email, self.owner.email)

    # ── Test 5: business linked to delivery ──────────────────────────────────

    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_business(self, mock_get_provider):
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_activated_email(self.subscription, self.invoice_event)

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.business_id, self.business.pk)

    # ── Test 6a: HTML includes business_name ─────────────────────────────────

    @patch("apps.notifications.services.get_email_provider")
    def test_html_includes_business_name(self, mock_get_provider):
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_activated_email(self.subscription, self.invoice_event)

        delivery = EmailDelivery.objects.get()
        self.assertIn("Panadería Don José", delivery.html_body)

    # ── Test 6b: HTML includes plan_name ─────────────────────────────────────

    @patch("apps.notifications.services.get_email_provider")
    def test_html_includes_plan_name(self, mock_get_provider):
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_activated_email(self.subscription, self.invoice_event)

        delivery = EmailDelivery.objects.get()
        # Plan name resolved from plan.name via checkout_session.plan
        self.assertIn("Gestión Pro", delivery.html_body)

    # ── Sanity: returns True on success ──────────────────────────────────────

    @patch("apps.notifications.services.get_email_provider")
    def test_returns_true_on_success(self, mock_get_provider):
        mock_get_provider.return_value = _mock_email_provider()

        result = send_subscription_activated_email(self.subscription, self.invoice_event)

        self.assertTrue(result)
        self.assertEqual(EmailDelivery.objects.count(), 1)

    # ── Test 7: owner without email → False, no delivery ─────────────────────

    def test_owner_without_email_returns_false(self):
        self.owner.email = ""
        self.owner.save()
        # Clear session so fallback hits Membership (which also has no email now)
        self.subscription.checkout_session = None
        self.subscription.save()

        result = send_subscription_activated_email(self.subscription, self.invoice_event)

        self.assertFalse(result)
        self.assertEqual(EmailDelivery.objects.count(), 0)

    # ── Test 8: queue raises → returns False, subscription stays ACTIVE ───────

    @patch(
        "apps.billing.email_helpers.queue_transactional_email",
        side_effect=Exception("SMTP timeout"),
    )
    def test_queue_raises_returns_false_without_propagating(self, _mock_queue):
        """Email failure must never propagate — returns False silently."""
        # Set subscription to ACTIVE to simulate post-activation state
        self.subscription.status = SubscriptionV2.Status.ACTIVE
        self.subscription.is_active = True
        self.subscription.save()

        result = send_subscription_activated_email(self.subscription, self.invoice_event)

        self.assertFalse(result)
        # Subscription must remain ACTIVE — email failure does NOT revert it
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.ACTIVE)
        self.assertTrue(self.subscription.is_active)


# ─────────────────────────────────────────────────────────────────────────────
# Class 3 — webhook_processor trigger (activated=True/False guard)
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**EMAIL_SETTINGS)
class WebhookActivationTriggerTests(TestCase):
    """
    Integration tests for the Step 6 trigger in _handle_authorized_payment().

    The MP API and activate_subscription_from_invoice are mocked to control
    the `activated` flag.  send_subscription_activated_email is also mocked
    to isolate the trigger logic from the email delivery stack.
    """

    def setUp(self):
        self.plan = _make_plan(code="gestion_starter_monthly")
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)
        self.ap_id = f"AP-{uuid.uuid4().hex[:8]}"
        self.preapproval_id = f"preapp-{uuid.uuid4().hex[:8]}"
        self.subscription = SubscriptionV2.objects.create(
            business=self.business,
            service_type=self.business.default_service,
            plan_code=self.plan.code,
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=self.preapproval_id,
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
            checkout_session=self.session,
        )
        self.delivery = _make_webhook_delivery(resource_id=self.ap_id)
        # Fake authoritative MP response
        self._ap_data = {
            "id": self.ap_id,
            "status": "authorized",
            "preapproval_id": self.preapproval_id,
            "payment_id": f"pay-{uuid.uuid4().hex[:6]}",
            "transaction_amount": 49900,
            "currency_id": "ARS",
            "date_approved": "2026-05-09T12:00:00.000-03:00",
        }

    def _call_handler(self, activated_return, email_mock):
        """
        Call _handle_authorized_payment with all external dependencies mocked.
        Returns the email mock to allow assertions.
        """
        with (
            patch("apps.billing.mp_service.MercadoPagoService.get_authorized_payment",
                  return_value=self._ap_data),
            patch("apps.billing.subscription_activator.activate_subscription_from_invoice",
                  return_value=activated_return) as mock_activator,
            patch("apps.billing.promo_cycle_service.handle_promo_cycle"),
        ):
            _handle_authorized_payment(self.ap_id, self.delivery)
        return mock_activator

    # ── Test 1: activated=True → email dispatched ─────────────────────────────

    def test_email_sent_when_activated_true(self):
        """When activation succeeds, send_subscription_activated_email is called."""
        with (
            patch("apps.billing.mp_service.MercadoPagoService.get_authorized_payment",
                  return_value=self._ap_data),
            patch("apps.billing.subscription_activator.activate_subscription_from_invoice",
                  return_value=True),
            patch("apps.billing.promo_cycle_service.handle_promo_cycle"),
            patch("apps.billing.email_helpers.send_subscription_activated_email") as mock_email,
        ):
            _handle_authorized_payment(self.ap_id, self.delivery)

        mock_email.assert_called_once()
        # First positional arg is the subscription
        called_sub = mock_email.call_args[0][0]
        self.assertEqual(called_sub.pk, self.subscription.pk)

    # ── Test 2: activated=False → email NOT dispatched ────────────────────────

    def test_email_not_sent_when_activated_false(self):
        """When activate_subscription_from_invoice() returns False, no email is sent."""
        with (
            patch("apps.billing.mp_service.MercadoPagoService.get_authorized_payment",
                  return_value=self._ap_data),
            patch("apps.billing.subscription_activator.activate_subscription_from_invoice",
                  return_value=False),
            patch("apps.billing.promo_cycle_service.handle_promo_cycle"),
            patch("apps.billing.email_helpers.send_subscription_activated_email") as mock_email,
        ):
            _handle_authorized_payment(self.ap_id, self.delivery)

        mock_email.assert_not_called()

    # ── Test 9: duplicate webhook → activated=False → no second email ─────────

    def test_duplicate_guard_no_second_email(self):
        """
        A duplicate authorized_payment webhook causes the double-checked lock
        in activate_subscription_from_invoice() to return False → no email.

        We simulate this by having the mock return False (same outcome as the
        double-checked lock returning early).
        """
        with (
            patch("apps.billing.mp_service.MercadoPagoService.get_authorized_payment",
                  return_value=self._ap_data),
            patch("apps.billing.subscription_activator.activate_subscription_from_invoice",
                  return_value=False),
            patch("apps.billing.promo_cycle_service.handle_promo_cycle"),
            patch("apps.billing.email_helpers.send_subscription_activated_email") as mock_email,
        ):
            # First webhook
            _handle_authorized_payment(self.ap_id, self.delivery)
            # Simulate second webhook (BillingInvoiceEvent already exists → updated=False)
            delivery2 = _make_webhook_delivery(resource_id=f"{self.ap_id}-dup")
            _handle_authorized_payment(self.ap_id, delivery2)

        # send_subscription_activated_email should have been called 0 times in total
        mock_email.assert_not_called()
