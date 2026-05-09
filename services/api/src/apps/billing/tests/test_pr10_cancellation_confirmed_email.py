"""
Tests for PR-10: cancellation_confirmed email.

Covers:
  1.  Helper creates an EmailDelivery record.
  2.  EmailDelivery uses template_key="cancellation_confirmed".
  3.  Owner is the email recipient (to_email).
  4.  EmailDelivery is associated with the business.
  5.  Rendered HTML mentions cancellation.
  6.  Owner without email → no crash, helper returns False.
  7.  queue_transactional_email raises → returns False without propagating.
  8.  execute_cancellation() dispatches email when subscription transitions to CANCELED.
  9.  execute_cancellation() does NOT dispatch email if already CANCELED (no-op).
  10. Email failure does not revert the CANCELED state.
  11. No webhook file is touched (structural assertion).
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
from apps.billing.cancellation_service import execute_cancellation
from apps.billing.email_helpers import send_cancellation_confirmed_email
from apps.billing.models import (
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
)
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
        provider_message_id="test-msg-pr10",
    )
    return mock


def _mock_mp_service():
    """Return a MercadoPagoService mock that silently accepts update_preapproval."""
    mock = MagicMock()
    mock.update_preapproval.return_value = {"status": "cancelled"}
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
        name=name,
        status="active",
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


# ─────────────────────────────────────────────────────────────────────────────
# Class 1 — send_cancellation_confirmed_email() helper
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class SendCancellationConfirmedEmailTests(TestCase):
    """Unit tests for billing.email_helpers.send_cancellation_confirmed_email()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business(name="Mi Negocio SA")
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)
        self.sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.CANCELED,
        )

    # 1. Helper creates EmailDelivery
    @patch("apps.notifications.services.get_email_provider")
    def test_creates_email_delivery(self, mock_get_provider):
        """Helper creates at least one EmailDelivery record."""
        mock_get_provider.return_value = _mock_email_provider()
        before = EmailDelivery.objects.count()

        send_cancellation_confirmed_email(self.sub)

        self.assertGreater(EmailDelivery.objects.count(), before)

    # 2. Correct template key
    @patch("apps.notifications.services.get_email_provider")
    def test_uses_correct_template_key(self, mock_get_provider):
        """EmailDelivery.template_key must be 'cancellation_confirmed'."""
        mock_get_provider.return_value = _mock_email_provider()

        send_cancellation_confirmed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.template_key, "cancellation_confirmed")

    # 3. Owner as recipient
    @patch("apps.notifications.services.get_email_provider")
    def test_uses_owner_email_as_recipient(self, mock_get_provider):
        """to_email must be the owner's email address."""
        mock_get_provider.return_value = _mock_email_provider()

        send_cancellation_confirmed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.to_email, self.owner.email)

    # 4. EmailDelivery linked to business
    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_business(self, mock_get_provider):
        """EmailDelivery.business must be the subscription's business."""
        mock_get_provider.return_value = _mock_email_provider()

        send_cancellation_confirmed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.business_id, self.business.pk)

    # 5. HTML mentions cancellation
    @patch("apps.notifications.services.get_email_provider")
    def test_html_mentions_cancellation(self, mock_get_provider):
        """Rendered HTML body must mention cancellation."""
        mock_get_provider.return_value = _mock_email_provider()

        send_cancellation_confirmed_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        body_lower = delivery.html_body.lower()
        self.assertTrue(
            "cancel" in body_lower,
            "Expected 'cancel' in HTML body",
        )

    # 6. No owner/email → no crash, returns False
    def test_owner_without_email_returns_false(self):
        """When the subscription has no resolvable owner email, returns False."""
        biz = _make_business(name="No-Owner Biz")
        plan = _make_plan()
        sub = _make_subscription(biz, plan, session=None,
                                  status=SubscriptionV2.Status.CANCELED)

        result = send_cancellation_confirmed_email(sub)

        self.assertFalse(result)

    # 7. queue_transactional_email raises → returns False
    @patch(
        "apps.billing.email_helpers.queue_transactional_email",
        side_effect=Exception("SMTP timeout"),
    )
    def test_queue_raises_returns_false_without_propagating(self, _mock_queue):
        """Email failure must never propagate — returns False silently."""
        result = send_cancellation_confirmed_email(self.sub)

        self.assertFalse(result)
        # Subscription status must remain unchanged
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.CANCELED)


# ─────────────────────────────────────────────────────────────────────────────
# Class 2 — execute_cancellation() integration
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class ExecuteCancellationEmailTests(TestCase):
    """Integration tests for cancellation_service.execute_cancellation()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)

    # 8. Dispatches email when subscription transitions to CANCELED
    @patch("apps.billing.email_helpers.send_cancellation_confirmed_email")
    def test_email_sent_when_cancellation_occurs(self, mock_email):
        """execute_cancellation() dispatches email when sub transitions to CANCELED."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        mp_mock = _mock_mp_service()

        execute_cancellation(sub, mp_service=mp_mock)

        mock_email.assert_called_once()
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.CANCELED)

    # 9. No email if already CANCELED (idempotent no-op)
    @patch("apps.billing.email_helpers.send_cancellation_confirmed_email")
    def test_email_not_sent_when_already_canceled(self, mock_email):
        """execute_cancellation() does NOT dispatch email if sub was already CANCELED."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.CANCELED,
        )

        execute_cancellation(sub, mp_service=_mock_mp_service())

        mock_email.assert_not_called()

    # 10. Email failure does not revert CANCELED state
    @patch("apps.billing.email_helpers.send_cancellation_confirmed_email",
           side_effect=Exception("Email backend down"))
    def test_email_failure_does_not_revert_cancellation(self, _mock_email):
        """Email failure must not revert the CANCELED state."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        mp_mock = _mock_mp_service()

        execute_cancellation(sub, mp_service=mp_mock)

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.CANCELED)
        self.assertFalse(sub.is_active)

    # 11. Structural: no webhook module is imported in cancellation_service
    def test_no_webhook_import_in_cancellation_service(self):
        """cancellation_service.py must not import from any webhook module."""
        import importlib
        import sys

        # Reload to get the actual module source path
        import apps.billing.cancellation_service as svc_module
        source_file = svc_module.__file__

        with open(source_file, encoding="utf-8") as fh:
            source = fh.read()

        self.assertNotIn("webhook", source.lower())

    # Bonus: email dispatched with correct subscription arg
    @patch("apps.billing.email_helpers.send_cancellation_confirmed_email")
    def test_email_receives_correct_subscription(self, mock_email):
        """execute_cancellation() passes the subscription instance to the email helper."""
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.ACTIVE,
        )
        mp_mock = _mock_mp_service()

        execute_cancellation(sub, mp_service=mp_mock)

        mock_email.assert_called_once_with(sub)
