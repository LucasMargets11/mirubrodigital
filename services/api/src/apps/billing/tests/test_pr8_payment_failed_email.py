"""
Tests for PR-8: payment_failed email.

Covers:
  1.  Helper creates an EmailDelivery record.
  2.  EmailDelivery uses template_key="payment_failed".
  3.  Owner is the email recipient (to_email).
  4.  EmailDelivery is associated with the business.
  5.  Rendered HTML mentions the payment problem message.
  6.  Owner without email → no crash, helper returns False.
  7.  queue_transactional_email raises → returns False without propagating.
  8.  record_failed_payment() dispatches email when subscription was ACTIVE.
  9.  record_failed_payment() does NOT dispatch email when sub was not ACTIVE.
  10. _transition_active_to_past_due() dispatches email when updated == 1.
  11. _transition_active_to_past_due() does NOT dispatch email when updated == 0.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.email_helpers import send_payment_failed_email
from apps.billing.models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
)
from apps.billing.subscription_activator import record_failed_payment
from apps.billing.tasks import _transition_active_to_past_due
from apps.business.models import Business, Subscription as BizSubscription
from apps.notifications.models import EmailDelivery
from apps.notifications.providers.base import EmailSendResult

User = get_user_model()

_SETTINGS = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "EMAIL_PROVIDER": "django",
    "EMAIL_TRANSACTIONAL_ENABLED": True,
    "FRONTEND_URL": "https://app.mirubro.com",
    "SUPPORT_EMAIL": "soporte@mirubro.com",
}


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def _mock_email_provider(success=True):
    mock = MagicMock()
    mock.provider_name = "django"
    mock.send_email.return_value = EmailSendResult(
        success=success,
        provider_message_id="test-msg-pr8",
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
        expires_at=timezone.now() + timedelta(hours=1),
    )


def _make_subscription(business, plan, session=None,
                       status=SubscriptionV2.Status.ACTIVE):
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
# Class 1 — send_payment_failed_email() helper
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class SendPaymentFailedEmailTests(TestCase):
    """Unit tests for billing.email_helpers.send_payment_failed_email()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business(name="Mi Negocio SA")
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)
        self.sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
        )

    @patch("apps.notifications.services.get_email_provider")
    def test_creates_email_delivery(self, mock_get_provider):
        """Helper creates at least one EmailDelivery record."""
        mock_get_provider.return_value = _mock_email_provider()
        before = EmailDelivery.objects.count()

        send_payment_failed_email(self.sub)

        self.assertGreater(EmailDelivery.objects.count(), before)

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_correct_template_key(self, mock_get_provider):
        """EmailDelivery.template_key must be 'payment_failed'."""
        mock_get_provider.return_value = _mock_email_provider()

        send_payment_failed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.template_key, "payment_failed")

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_owner_email_as_recipient(self, mock_get_provider):
        """to_email must be the owner's email address."""
        mock_get_provider.return_value = _mock_email_provider()

        send_payment_failed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.to_email, self.owner.email)

    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_business(self, mock_get_provider):
        """EmailDelivery.business must be the subscription's business."""
        mock_get_provider.return_value = _mock_email_provider()

        send_payment_failed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.business_id, self.business.pk)

    @patch("apps.notifications.services.get_email_provider")
    def test_html_mentions_payment_problem(self, mock_get_provider):
        """Rendered HTML body must mention the payment problem."""
        mock_get_provider.return_value = _mock_email_provider()

        send_payment_failed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertIn("problema", delivery.html_body.lower())

    def test_owner_without_email_returns_false(self):
        """When the subscription has no resolvable owner email, returns False."""
        biz = _make_business(name="Empty Biz")
        plan = _make_plan(code=f"plan-{uuid.uuid4().hex[:6]}")
        sub = _make_subscription(biz, plan, session=None,
                                 status=SubscriptionV2.Status.PAST_DUE)

        result = send_payment_failed_email(sub)

        self.assertFalse(result)

    @patch("apps.billing.email_helpers.queue_transactional_email",
           side_effect=Exception("SMTP timeout"))
    def test_queue_raises_returns_false_without_propagating(self, _mock_queue):
        """Email failure must never propagate — returns False silently."""
        result = send_payment_failed_email(self.sub)

        self.assertFalse(result)
        # Subscription status unchanged
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.PAST_DUE)

    @patch("apps.notifications.services.get_email_provider")
    def test_returns_true_on_success(self, mock_get_provider):
        """Returns True when email is successfully enqueued."""
        mock_get_provider.return_value = _mock_email_provider()

        result = send_payment_failed_email(self.sub)

        self.assertTrue(result)


# ─────────────────────────────────────────────────────────────────────────────
# Class 2 — record_failed_payment() integration
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class RecordFailedPaymentEmailTests(TestCase):
    """Integration tests for record_failed_payment() email dispatch."""

    def setUp(self):
        self.plan = _make_plan(code=f"gestion_monthly_{uuid.uuid4().hex[:4]}")
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_email_sent_when_active_transitions_to_past_due(self, mock_email):
        """record_failed_payment() must call send_payment_failed_email when sub was ACTIVE."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        mock_email.assert_called_once()

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_email_not_sent_when_already_past_due(self, mock_email):
        """record_failed_payment() must NOT call send_payment_failed_email when sub was not ACTIVE."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        mock_email.assert_not_called()

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_email_not_sent_when_checkout_pending(self, mock_email):
        """record_failed_payment() must NOT call send_payment_failed_email when sub is CHECKOUT_PENDING."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        mock_email.assert_not_called()

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_sub_becomes_past_due_even_if_email_fails(self, mock_email):
        """Email failure must not revert the ACTIVE→PAST_DUE transition."""
        mock_email.side_effect = Exception("SMTP error")
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        event = _make_invoice_event(sub)

        record_failed_payment(invoice_event=event, subscription=sub)

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)


# ─────────────────────────────────────────────────────────────────────────────
# Class 3 — _transition_active_to_past_due() integration
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class TransitionActiveToPastDueEmailTests(TestCase):
    """Integration tests for tasks._transition_active_to_past_due() email dispatch."""

    def setUp(self):
        self.plan = _make_plan(code=f"gestion_monthly_{uuid.uuid4().hex[:4]}")
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_email_sent_when_updated(self, mock_email):
        """_transition_active_to_past_due() dispatches email when updated == 1."""
        past_end = timezone.now() - timedelta(days=2)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        sub.current_period_end = past_end
        sub.save(update_fields=['current_period_end'])

        now = timezone.now()
        count = _transition_active_to_past_due(SubscriptionV2, now)

        self.assertEqual(count, 1)
        mock_email.assert_called_once()

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_email_not_sent_when_not_updated(self, mock_email):
        """_transition_active_to_past_due() does NOT dispatch email when updated == 0.

        Scenario: subscription period_end is in the future → filter matches nothing.
        """
        future_end = timezone.now() + timedelta(days=30)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        sub.current_period_end = future_end
        sub.save(update_fields=['current_period_end'])

        now = timezone.now()
        count = _transition_active_to_past_due(SubscriptionV2, now)

        self.assertEqual(count, 0)
        mock_email.assert_not_called()

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_email_not_sent_when_already_past_due(self, mock_email):
        """_transition_active_to_past_due() skips subs already in PAST_DUE."""
        past_end = timezone.now() - timedelta(days=2)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
        )
        sub.current_period_end = past_end
        sub.save(update_fields=['current_period_end'])

        now = timezone.now()
        _transition_active_to_past_due(SubscriptionV2, now)

        mock_email.assert_not_called()

    @patch("apps.billing.email_helpers.send_payment_failed_email")
    def test_email_failure_does_not_affect_count(self, mock_email):
        """Email failure must not affect the transition count."""
        mock_email.side_effect = Exception("Email backend down")
        past_end = timezone.now() - timedelta(days=2)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        sub.current_period_end = past_end
        sub.save(update_fields=['current_period_end'])

        now = timezone.now()
        count = _transition_active_to_past_due(SubscriptionV2, now)

        self.assertEqual(count, 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)
