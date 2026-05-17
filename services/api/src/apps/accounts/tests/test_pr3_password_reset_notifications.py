"""
Tests for PR-3: password-reset email migrated to apps.notifications.

Verifies:
  1. EmailService.send_password_reset_email creates an EmailDelivery.
  2. Delivery uses template_key="password_reset".
  3. Delivery uses user.email as recipient.
  4. HTML body contains /nueva-contrasena?token=...
  5. Subject is correct.
  6. Delivery is linked to the user.
  7. Token does NOT appear in metadata.
  8. If queue_transactional_email raises, the method returns False.
  9. ForgotPasswordView still returns 200 with the expected body.
  10. Anti-enumeration: non-existent email returns the same 200 response.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import AccountProfile
from apps.notifications.models import EmailDelivery
from apps.notifications.providers.base import EmailSendResult

User = get_user_model()

TOKEN = "pr3resettoken123"
FORGOT_URL = "/api/v1/auth/forgot-password/"


def _make_user(email="resetme@example.com", username=None, account_mode="personal"):
    username = username or email
    user = User.objects.create_user(
        username=username,
        email=email,
        password="SecurePass123!",
        first_name="Reset",
        last_name="User",
    )
    AccountProfile.objects.update_or_create(
        user=user,
        defaults={"account_mode": account_mode},
    )
    return user


def _mock_provider(success=True):
    mock = MagicMock()
    mock.provider_name = "django"
    mock.send_email.return_value = EmailSendResult(
        success=success,
        provider_message_id="test-msg-pr3",
    )
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# EmailService.send_password_reset_email
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    PASSWORD_RESET_TOKEN_HOURS=2,
)
class SendPasswordResetEmailTest(TestCase):
    """Unit tests for EmailService.send_password_reset_email."""

    def setUp(self):
        self.user = _make_user()

    @patch("apps.notifications.services.get_email_provider")
    def test_creates_email_delivery(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        result = EmailService.send_password_reset_email(self.user, TOKEN)

        self.assertTrue(result)
        self.assertEqual(EmailDelivery.objects.filter(to_email=self.user.email).count(), 1)

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_password_reset_template_key(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_reset_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.template_key, "password_reset")

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_user_email_as_recipient(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_reset_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.to_email, self.user.email)

    @patch("apps.notifications.services.get_email_provider")
    def test_html_body_contains_reset_url(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_reset_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        expected_url = f"https://app.mirubro.com/nueva-contrasena?token={TOKEN}"
        self.assertIn(expected_url, delivery.html_body)

    @patch("apps.notifications.services.get_email_provider")
    def test_subject_is_correct(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_reset_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.subject, "Recuperá tu contraseña en MiRubro")

    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_user(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_reset_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.user_id, self.user.pk)

    @patch("apps.notifications.services.get_email_provider")
    def test_token_not_stored_in_metadata(self, mock_get):
        """Token must NOT appear in metadata — only in the rendered body."""
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_reset_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertNotIn(TOKEN, str(delivery.metadata))

    def test_returns_false_and_logs_on_exception(self):
        """If queue_transactional_email raises, send_password_reset_email returns False."""
        from apps.accounts.services import EmailService

        with patch(
            "apps.accounts.services.queue_transactional_email",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs("apps.accounts.services", level="ERROR"):
                result = EmailService.send_password_reset_email(self.user, TOKEN)

        self.assertFalse(result)

    def test_uses_async_dispatch_by_default(self):
        """send_password_reset_email should enqueue, not send synchronously."""
        from apps.accounts.services import EmailService

        with patch("apps.accounts.services.queue_transactional_email") as mock_q:
            mock_q.return_value = MagicMock()
            EmailService.send_password_reset_email(self.user, TOKEN)

        self.assertIsNotNone(mock_q.call_args)
        call_kwargs = mock_q.call_args[1]
        self.assertTrue(call_kwargs.get("send_async", False))


# ─────────────────────────────────────────────────────────────────────────────
# ForgotPasswordView smoke tests
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    PASSWORD_RESET_TOKEN_HOURS=2,
)
@patch("apps.accounts.views.ForgotPasswordView.throttle_classes", new=[])
class ForgotPasswordViewSmokeTest(TestCase):
    """ForgotPasswordView must keep working after PR-3 migration."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

    @patch("apps.notifications.services.get_email_provider")
    def test_returns_200_for_existing_user(self, mock_get):
        mock_get.return_value = _mock_provider()
        _make_user(email="forgotme1@example.com", username="forgotme1@example.com")

        resp = self.client.post(FORGOT_URL, {"email": "forgotme1@example.com"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

    def test_returns_200_for_nonexistent_email(self):
        """Anti-enumeration: unknown emails must return the same 200 response."""
        resp = self.client.post(FORGOT_URL, {"email": "ghost@example.com"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

    @patch("apps.notifications.services.get_email_provider")
    def test_same_response_shape_for_existing_and_missing(self, mock_get):
        """Both paths must return identical JSON to prevent enumeration."""
        mock_get.return_value = _mock_provider()
        _make_user(email="forgotme2@example.com", username="forgotme2@example.com")

        resp_existing = self.client.post(FORGOT_URL, {"email": "forgotme2@example.com"})
        resp_missing = self.client.post(FORGOT_URL, {"email": "nobody@example.com"})

        self.assertEqual(resp_existing.status_code, resp_missing.status_code)
        self.assertEqual(resp_existing.data["status"], resp_missing.data["status"])
        self.assertEqual(resp_existing.data["message"], resp_missing.data["message"])

    @patch("apps.notifications.services.get_email_provider")
    def test_creates_delivery_for_existing_user(self, mock_get):
        mock_get.return_value = _mock_provider()
        _make_user(email="forgotme3@example.com", username="forgotme3@example.com")

        self.client.post(FORGOT_URL, {"email": "forgotme3@example.com"})

        self.assertEqual(
            EmailDelivery.objects.filter(
                to_email="forgotme3@example.com",
                template_key="password_reset",
            ).count(),
            1,
        )

    def test_no_delivery_for_nonexistent_email(self):
        """No EmailDelivery should be created when the user doesn't exist."""
        self.client.post(FORGOT_URL, {"email": "ghost2@example.com"})

        self.assertEqual(
            EmailDelivery.objects.filter(to_email="ghost2@example.com").count(),
            0,
        )
