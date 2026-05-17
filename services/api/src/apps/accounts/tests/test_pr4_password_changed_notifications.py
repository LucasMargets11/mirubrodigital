"""
Tests for PR-4: password-changed security email.

Verifies:
  1. EmailService.send_password_changed_email creates an EmailDelivery.
  2. Delivery uses template_key="password_changed".
  3. Delivery uses user.email as recipient.
  4. Subject is correct.
  5. HTML body contains the security warning text.
  6. Metadata does not contain passwords or tokens.
  7. If queue_transactional_email raises, the method returns False without propagating.
  8. ChangePasswordView fires the email only on success.
  9. ForceChangePasswordView fires the email only on success.
  10. ResetPasswordView fires the email only on success.
  11. A failed password change (wrong current_password) does NOT fire the email.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock, call

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import AccountProfile
from apps.notifications.models import EmailDelivery
from apps.notifications.providers.base import EmailSendResult

User = get_user_model()

CHANGE_URL = "/api/v1/auth/change-password/"
FORCE_CHANGE_URL = "/api/v1/auth/force-change-password/"
RESET_URL = "/api/v1/auth/reset-password/"


def _make_user(email="changed@example.com", username=None, account_mode="personal",
               must_change_password=False, password="OldPass123!"):
    username = username or email
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name="Changed",
        last_name="User",
    )
    AccountProfile.objects.update_or_create(
        user=user,
        defaults={
            "account_mode": account_mode,
            "must_change_password": must_change_password,
        },
    )
    return user


def _mock_provider(success=True):
    mock = MagicMock()
    mock.provider_name = "django"
    mock.send_email.return_value = EmailSendResult(
        success=success,
        provider_message_id="test-msg-pr4",
    )
    return mock


def _auth_client(user):
    """Return an APIClient authenticated as the given user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# EmailService.send_password_changed_email (unit tests)
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    SUPPORT_EMAIL="soporte@mirubro.com",
)
class SendPasswordChangedEmailTest(TestCase):

    def setUp(self):
        self.user = _make_user()

    @patch("apps.notifications.services.get_email_provider")
    def test_creates_email_delivery(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        self.assertEqual(EmailDelivery.objects.count(), 1)

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_password_changed_template_key(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.template_key, "password_changed")

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_user_email_as_recipient(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.to_email, self.user.email)

    @patch("apps.notifications.services.get_email_provider")
    def test_subject_is_correct(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.subject, "Tu contraseña de MiRubro fue modificada")

    @patch("apps.notifications.services.get_email_provider")
    def test_html_body_contains_security_warning(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        delivery = EmailDelivery.objects.get()
        self.assertIn("no fuiste vos", delivery.html_body)

    @patch("apps.notifications.services.get_email_provider")
    def test_metadata_has_no_sensitive_data(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        delivery = EmailDelivery.objects.get()
        metadata_str = str(delivery.metadata)
        self.assertNotIn("password", metadata_str.lower())
        self.assertNotIn("token", metadata_str.lower())

    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_user(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.user_id, self.user.pk)

    def test_returns_false_and_logs_on_exception(self):
        from apps.accounts.services import EmailService
        with patch(
            "apps.accounts.services.queue_transactional_email",
            side_effect=RuntimeError("SMTP down"),
        ):
            with self.assertLogs("apps.accounts.services", level="ERROR"):
                result = EmailService.send_password_changed_email(self.user)

        self.assertFalse(result)

    @patch("apps.accounts.services.queue_transactional_email")
    def test_uses_async_dispatch_by_default(self, mock_queue):
        from apps.accounts.services import EmailService
        EmailService.send_password_changed_email(self.user)

        self.assertTrue(mock_queue.called)
        call_kwargs = mock_queue.call_args.kwargs
        self.assertTrue(call_kwargs.get("send_async", False))


# ─────────────────────────────────────────────────────────────────────────────
# View smoke tests — email dispatched on successful change
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    SUPPORT_EMAIL="soporte@mirubro.com",
)
class ChangePasswordViewEmailTest(TestCase):

    @patch("apps.notifications.services.get_email_provider")
    def test_fires_email_on_success(self, mock_get):
        mock_get.return_value = _mock_provider()
        user = _make_user(email="change1@example.com", username="change1@example.com")
        client = _auth_client(user)

        resp = client.post(CHANGE_URL, {
            "current_password": "OldPass123!",
            "new_password": "NewSecure456!",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            EmailDelivery.objects.filter(
                to_email="change1@example.com",
                template_key="password_changed",
            ).count(),
            1,
        )

    def test_no_email_on_wrong_current_password(self):
        user = _make_user(email="change2@example.com", username="change2@example.com")
        client = _auth_client(user)

        resp = client.post(CHANGE_URL, {
            "current_password": "WrongPassword!",
            "new_password": "NewSecure456!",
        })

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            EmailDelivery.objects.filter(to_email="change2@example.com").count(),
            0,
        )

    def test_no_email_on_invalid_new_password(self):
        user = _make_user(email="change3@example.com", username="change3@example.com")
        client = _auth_client(user)

        resp = client.post(CHANGE_URL, {
            "current_password": "OldPass123!",
            "new_password": "short",
        })

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            EmailDelivery.objects.filter(to_email="change3@example.com").count(),
            0,
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    SUPPORT_EMAIL="soporte@mirubro.com",
)
class ForceChangePasswordViewEmailTest(TestCase):

    @patch("apps.notifications.services.get_email_provider")
    def test_fires_email_on_success(self, mock_get):
        mock_get.return_value = _mock_provider()
        user = _make_user(
            email="force1@example.com", username="force1@example.com",
            must_change_password=True,
        )
        client = _auth_client(user)

        resp = client.post(FORCE_CHANGE_URL, {
            "current_password": "OldPass123!",
            "new_password": "NewSecure456!",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            EmailDelivery.objects.filter(
                to_email="force1@example.com",
                template_key="password_changed",
            ).count(),
            1,
        )

    def test_no_email_on_wrong_current_password(self):
        user = _make_user(
            email="force2@example.com", username="force2@example.com",
            must_change_password=True,
        )
        client = _auth_client(user)

        resp = client.post(FORCE_CHANGE_URL, {
            "current_password": "WrongPassword!",
            "new_password": "NewSecure456!",
        })

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            EmailDelivery.objects.filter(to_email="force2@example.com").count(),
            0,
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    SUPPORT_EMAIL="soporte@mirubro.com",
)
@patch("apps.accounts.views.ResetPasswordView.throttle_classes", new=[])
class ResetPasswordViewEmailTest(TestCase):

    @patch("apps.notifications.services.get_email_provider")
    def test_fires_email_on_success(self, mock_get):
        mock_get.return_value = _mock_provider()
        user = _make_user(email="reset1@example.com", username="reset1@example.com")
        profile = AccountProfile.objects.get(user=user)
        token = profile.generate_password_reset_token()

        resp = self.client.post(RESET_URL, {
            "token": token,
            "new_password": "NewSecure456!",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            EmailDelivery.objects.filter(
                to_email="reset1@example.com",
                template_key="password_changed",
            ).count(),
            1,
        )

    def test_no_email_on_invalid_token(self):
        resp = self.client.post(RESET_URL, {
            "token": "completely-invalid-token",
            "new_password": "NewSecure456!",
        })

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(EmailDelivery.objects.count(), 0)
