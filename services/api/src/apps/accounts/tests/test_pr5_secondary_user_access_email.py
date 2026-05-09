"""
Tests for PR-5: secondary-user access email.

Verifies:
  1. EmailService.send_secondary_user_access_email creates an EmailDelivery.
  2. Delivery uses template_key="secondary_user_access".
  3. Delivery uses user.email as recipient.
  4. Delivery is associated with the business.
  5. HTML body mentions "Ingresar con Google".
  6. HTML body does NOT contain password, PIN, or token strings.
  7. If the user has no email, nothing is queued and False is returned.
  8. If queue_transactional_email raises, returns False without propagating.
  9. InternalUserService.create_internal_user attempts to send the email
     when the secondary user has an email.
  10. If the email send fails, user creation is still successful.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import AccountProfile, Membership
from apps.accounts.services import EmailService, InternalUserService
from apps.business.models import Business, Subscription
from apps.notifications.models import EmailDelivery
from apps.notifications.providers.base import EmailSendResult

User = get_user_model()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_provider(success=True):
    mock = MagicMock()
    mock.provider_name = "django"
    mock.send_email.return_value = EmailSendResult(
        success=success,
        provider_message_id="test-msg-pr5",
    )
    return mock


def _make_business(name="Test HQ"):
    return Business.objects.create(name=name, default_service="gestion", status="active")


def _make_subscription(business, plan="starter", max_seats=5):
    return Subscription.objects.create(
        business=business,
        plan=plan,
        status="active",
        max_seats=max_seats,
    )


def _make_owner(business, username="owner@test.com", email="owner@test.com"):
    owner = User.objects.create_user(
        username=username,
        email=email,
        password="OwnerPass123!",
        first_name="Owner",
        last_name="User",
    )
    Membership.objects.create(user=owner, business=business, role="owner")
    return owner


def _make_secondary_user(email="secondary@example.com", username=None):
    username = username or email
    user = User.objects.create_user(
        username=username,
        email=email,
        password="Pass123!",
        first_name="Ana",
        last_name="García",
    )
    return user


# ── Unit tests: EmailService.send_secondary_user_access_email ────────────────

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    SUPPORT_EMAIL="soporte@mirubro.com",
)
class SendSecondaryUserAccessEmailTest(TestCase):

    def setUp(self):
        self.business = _make_business()
        self.user = _make_secondary_user(email="secondary@example.com")

    # 1. Creates an EmailDelivery
    @patch("apps.notifications.services.get_email_provider")
    def test_creates_email_delivery(self, mock_get_provider):
        mock_get_provider.return_value = _mock_provider()

        result = EmailService.send_secondary_user_access_email(
            self.user, self.business, "cashier"
        )

        self.assertTrue(result)
        self.assertEqual(EmailDelivery.objects.count(), 1)

    # 2. Correct template_key
    @patch("apps.notifications.services.get_email_provider")
    def test_uses_correct_template_key(self, mock_get_provider):
        mock_get_provider.return_value = _mock_provider()

        EmailService.send_secondary_user_access_email(self.user, self.business, "admin")

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.template_key, "secondary_user_access")

    # 3. Correct recipient
    @patch("apps.notifications.services.get_email_provider")
    def test_uses_user_email_as_recipient(self, mock_get_provider):
        mock_get_provider.return_value = _mock_provider()

        EmailService.send_secondary_user_access_email(self.user, self.business, "cashier")

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.to_email, self.user.email)

    # 4. Delivery associated with the business
    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_business(self, mock_get_provider):
        mock_get_provider.return_value = _mock_provider()

        EmailService.send_secondary_user_access_email(self.user, self.business, "cashier")

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.business_id, self.business.pk)

    # 5. HTML mentions "Ingresar con Google"
    @patch("apps.notifications.services.get_email_provider")
    def test_html_mentions_google_login(self, mock_get_provider):
        mock_get_provider.return_value = _mock_provider()

        EmailService.send_secondary_user_access_email(self.user, self.business, "cashier")

        delivery = EmailDelivery.objects.get()
        self.assertIn("Ingresar con Google", delivery.html_body)

    # 6. No sensitive data in HTML
    @patch("apps.notifications.services.get_email_provider")
    def test_html_has_no_sensitive_data(self, mock_get_provider):
        mock_get_provider.return_value = _mock_provider()

        EmailService.send_secondary_user_access_email(self.user, self.business, "cashier")

        delivery = EmailDelivery.objects.get()
        html = delivery.html_body.lower()
        self.assertNotIn("contraseña", html)
        self.assertNotIn("password", html)
        self.assertNotIn("pin", html)
        self.assertNotIn("token", html)

    # 7. No email → not queued, returns False
    def test_no_email_skips_send(self):
        self.user.email = ""
        self.user.save()

        result = EmailService.send_secondary_user_access_email(
            self.user, self.business, "cashier"
        )

        self.assertFalse(result)
        self.assertEqual(EmailDelivery.objects.count(), 0)

    # 8. Exception → returns False, does not propagate
    @patch(
        "apps.accounts.services.queue_transactional_email",
        side_effect=Exception("SMTP timeout"),
    )
    def test_exception_returns_false_without_raising(self, _mock_queue):
        result = EmailService.send_secondary_user_access_email(
            self.user, self.business, "cashier"
        )

        self.assertFalse(result)


# ── Integration tests: InternalUserService.create_internal_user ──────────────

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    SUPPORT_EMAIL="soporte@mirubro.com",
)
class InternalUserCreationEmailTest(TestCase):

    def setUp(self):
        self.business = _make_business()
        _make_subscription(self.business)
        self.owner = _make_owner(self.business)

    def _create_user(self, email="secondary@example.com"):
        return InternalUserService.create_internal_user(
            business=self.business,
            first_name="Ana",
            last_name="García",
            username=f"ana.garcia.{email}",
            password="SecurePass99!",
            role="cashier",
            email=email,
            created_by_user=self.owner,
        )

    # 9. Email is sent when secondary user has email
    @patch("apps.notifications.services.get_email_provider")
    def test_email_sent_on_user_creation_with_email(self, mock_get_provider):
        mock_get_provider.return_value = _mock_provider()

        result = self._create_user(email="secondary@example.com")

        self.assertIsNotNone(result["user"])
        self.assertEqual(
            EmailDelivery.objects.filter(template_key="secondary_user_access").count(), 1
        )

    # 10. Email failure does not block user creation
    @patch(
        "apps.accounts.services.queue_transactional_email",
        side_effect=Exception("provider down"),
    )
    def test_email_failure_does_not_block_user_creation(self, _mock_queue):
        result = self._create_user(email="secondary@example.com")

        # User and membership must exist regardless
        user = result["user"]
        self.assertIsNotNone(user.pk)
        self.assertTrue(
            Membership.objects.filter(user=user, business=self.business).exists()
        )
