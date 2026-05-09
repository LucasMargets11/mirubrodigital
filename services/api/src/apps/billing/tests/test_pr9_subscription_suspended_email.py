"""
Tests for PR-9: subscription_suspended email.

Covers:
  1.  Helper creates an EmailDelivery record.
  2.  EmailDelivery uses template_key="subscription_suspended".
  3.  Owner is the email recipient (to_email).
  4.  EmailDelivery is associated with the business.
  5.  Rendered HTML mentions suspension / reactivation.
  6.  Owner without email → no crash, helper returns False.
  7.  queue_transactional_email raises → returns False without propagating.
  8.  _transition_past_due_to_suspended() dispatches email when updated == 1.
  9.  _transition_trial_to_suspended() dispatches email when updated == 1.
  10. updated == 0 → no email dispatched (past_due path).
  11. updated == 0 → no email dispatched (trial path).
  12. Sub already SUSPENDED → filter matches nothing → no email.
  13. Email failure does not break _transition_past_due_to_suspended() count.
  14. Email failure does not break _transition_trial_to_suspended() count.
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
from apps.billing.email_helpers import send_subscription_suspended_email
from apps.billing.models import (
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
)
from apps.billing.tasks import (
    _transition_past_due_to_suspended,
    _transition_trial_to_suspended,
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
        provider_message_id="test-msg-pr9",
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


def _make_subscription(business, plan, session=None, status=SubscriptionV2.Status.SUSPENDED,
                        grace_until=None, trial_ends_at=None):
    sub = SubscriptionV2.objects.create(
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
    if grace_until is not None:
        sub.grace_until = grace_until
        sub.save(update_fields=['grace_until'])
    if trial_ends_at is not None:
        sub.trial_ends_at = trial_ends_at
        sub.save(update_fields=['trial_ends_at'])
    return sub


# ─────────────────────────────────────────────────────────────────────────────
# Class 1 — send_subscription_suspended_email() helper
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class SendSubscriptionSuspendedEmailTests(TestCase):
    """Unit tests for billing.email_helpers.send_subscription_suspended_email()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business(name="Mi Negocio SA")
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)
        self.sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.SUSPENDED,
        )

    # 1. Helper creates EmailDelivery
    @patch("apps.notifications.services.get_email_provider")
    def test_creates_email_delivery(self, mock_get_provider):
        """Helper creates at least one EmailDelivery record."""
        mock_get_provider.return_value = _mock_email_provider()
        before = EmailDelivery.objects.count()

        send_subscription_suspended_email(self.sub)

        self.assertGreater(EmailDelivery.objects.count(), before)

    # 2. Correct template key
    @patch("apps.notifications.services.get_email_provider")
    def test_uses_correct_template_key(self, mock_get_provider):
        """EmailDelivery.template_key must be 'subscription_suspended'."""
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_suspended_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.template_key, "subscription_suspended")

    # 3. Owner as recipient
    @patch("apps.notifications.services.get_email_provider")
    def test_uses_owner_email_as_recipient(self, mock_get_provider):
        """to_email must be the owner's email address."""
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_suspended_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.to_email, self.owner.email)

    # 4. EmailDelivery linked to business
    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_business(self, mock_get_provider):
        """EmailDelivery.business must be the subscription's business."""
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_suspended_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        self.assertEqual(delivery.business_id, self.business.pk)

    # 5. HTML mentions suspension / reactivation
    @patch("apps.notifications.services.get_email_provider")
    def test_html_mentions_suspension_and_reactivation(self, mock_get_provider):
        """Rendered HTML body must mention suspension and reactivation."""
        mock_get_provider.return_value = _mock_email_provider()

        send_subscription_suspended_email(self.sub)

        delivery = EmailDelivery.objects.filter(to_email=self.owner.email).latest("created_at")
        body_lower = delivery.html_body.lower()
        self.assertTrue(
            "suspend" in body_lower or "suspendid" in body_lower,
            "Expected 'suspend' or 'suspendid' in HTML body",
        )
        self.assertTrue(
            "reactiv" in body_lower,
            "Expected 'reactiv' in HTML body",
        )

    # 6. No owner/email → no crash, returns False
    def test_owner_without_email_returns_false(self):
        """When the subscription has no resolvable owner email, returns False."""
        biz = _make_business(name="No-Owner Biz")
        plan = _make_plan()
        sub = _make_subscription(biz, plan, session=None,
                                  status=SubscriptionV2.Status.SUSPENDED)

        result = send_subscription_suspended_email(sub)

        self.assertFalse(result)

    # 7. queue_transactional_email raises → returns False
    @patch(
        "apps.billing.email_helpers.queue_transactional_email",
        side_effect=Exception("SMTP timeout"),
    )
    def test_queue_raises_returns_false_without_propagating(self, _mock_queue):
        """Email failure must never propagate — returns False silently."""
        result = send_subscription_suspended_email(self.sub)

        self.assertFalse(result)
        # Subscription status must remain unchanged
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.SUSPENDED)


# ─────────────────────────────────────────────────────────────────────────────
# Class 2 — _transition_past_due_to_suspended() integration
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class TransitionPastDueToSuspendedEmailTests(TestCase):
    """Integration tests for tasks._transition_past_due_to_suspended()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)

    # 8. Dispatches email when updated == 1
    @patch("apps.billing.email_helpers.send_subscription_suspended_email")
    def test_email_sent_when_updated(self, mock_email):
        """_transition_past_due_to_suspended() dispatches email when updated == 1."""
        expired_grace = timezone.now() - timedelta(days=1)
        _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until=expired_grace,
        )

        count = _transition_past_due_to_suspended(SubscriptionV2, timezone.now())

        self.assertEqual(count, 1)
        mock_email.assert_called_once()

    # 10. updated == 0 → no email
    @patch("apps.billing.email_helpers.send_subscription_suspended_email")
    def test_email_not_sent_when_not_updated(self, mock_email):
        """_transition_past_due_to_suspended() does NOT dispatch email when updated == 0.

        Scenario: grace_until is in the future → filter matches nothing.
        """
        future_grace = timezone.now() + timedelta(days=5)
        _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until=future_grace,
        )

        count = _transition_past_due_to_suspended(SubscriptionV2, timezone.now())

        self.assertEqual(count, 0)
        mock_email.assert_not_called()

    # 12. Sub already SUSPENDED → no email
    @patch("apps.billing.email_helpers.send_subscription_suspended_email")
    def test_email_not_sent_when_already_suspended(self, mock_email):
        """_transition_past_due_to_suspended() skips subs already in SUSPENDED."""
        expired_grace = timezone.now() - timedelta(days=1)
        _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.SUSPENDED,  # already suspended
            grace_until=expired_grace,
        )

        _transition_past_due_to_suspended(SubscriptionV2, timezone.now())

        mock_email.assert_not_called()

    # 13. Email failure does not break count
    @patch("apps.billing.email_helpers.send_subscription_suspended_email",
           side_effect=Exception("Email backend down"))
    def test_email_failure_does_not_affect_count(self, _mock_email):
        """Email failure must not break _transition_past_due_to_suspended() count."""
        expired_grace = timezone.now() - timedelta(days=1)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until=expired_grace,
        )

        count = _transition_past_due_to_suspended(SubscriptionV2, timezone.now())

        self.assertEqual(count, 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.SUSPENDED)


# ─────────────────────────────────────────────────────────────────────────────
# Class 3 — _transition_trial_to_suspended() integration
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(**_SETTINGS)
class TransitionTrialToSuspendedEmailTests(TestCase):
    """Integration tests for tasks._transition_trial_to_suspended()."""

    def setUp(self):
        self.plan = _make_plan()
        self.business = _make_business()
        self.owner = _make_user()
        Membership.objects.create(user=self.owner, business=self.business, role="owner")
        self.session = _make_session(self.owner, self.plan, self.business)

    # 9. Dispatches email when updated == 1
    @patch("apps.billing.email_helpers.send_subscription_suspended_email")
    def test_email_sent_when_updated(self, mock_email):
        """_transition_trial_to_suspended() dispatches email when updated == 1."""
        expired_trial = timezone.now() - timedelta(days=1)
        _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at=expired_trial,
        )

        count = _transition_trial_to_suspended(SubscriptionV2, timezone.now())

        self.assertEqual(count, 1)
        mock_email.assert_called_once()

    # 11. updated == 0 → no email (trial path)
    @patch("apps.billing.email_helpers.send_subscription_suspended_email")
    def test_email_not_sent_when_not_updated(self, mock_email):
        """_transition_trial_to_suspended() does NOT dispatch email when updated == 0.

        Scenario: trial_ends_at is in the future → filter matches nothing.
        """
        future_trial = timezone.now() + timedelta(days=7)
        _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at=future_trial,
        )

        count = _transition_trial_to_suspended(SubscriptionV2, timezone.now())

        self.assertEqual(count, 0)
        mock_email.assert_not_called()

    # 12. Sub already SUSPENDED → no email (trial path)
    @patch("apps.billing.email_helpers.send_subscription_suspended_email")
    def test_email_not_sent_when_already_suspended(self, mock_email):
        """_transition_trial_to_suspended() skips subs already in SUSPENDED."""
        expired_trial = timezone.now() - timedelta(days=1)
        _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.SUSPENDED,  # already suspended
            trial_ends_at=expired_trial,
        )

        _transition_trial_to_suspended(SubscriptionV2, timezone.now())

        mock_email.assert_not_called()

    # 14. Email failure does not break count (trial path)
    @patch("apps.billing.email_helpers.send_subscription_suspended_email",
           side_effect=Exception("Email backend down"))
    def test_email_failure_does_not_affect_count(self, _mock_email):
        """Email failure must not break _transition_trial_to_suspended() count."""
        expired_trial = timezone.now() - timedelta(days=1)
        sub = _make_subscription(
            self.business, self.plan, session=self.session,
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at=expired_trial,
        )

        count = _transition_trial_to_suspended(SubscriptionV2, timezone.now())

        self.assertEqual(count, 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.SUSPENDED)
