"""
Tests for PR-2: verification email migrated to apps.notifications.

Verifies:
  1. EmailService.send_verification_email creates an EmailDelivery.
  2. Delivery uses template_key="verify_email".
  3. Delivery uses to_email=user.email.
  4. Delivery html_body contains /verificar-email?token=...
  5. send_verification_email_task still calls EmailService.send_verification_email.
  6. No real emails are sent (locmem / mocked provider).
  7. Registration and resend views still work (smoke).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.notifications.models import EmailDelivery
from apps.notifications.providers.base import EmailSendResult

User = get_user_model()

TOKEN = "abc123verifytoken"


def _make_user(email="verifyme@example.com", username=None):
    username = username or email
    return User.objects.create_user(
        username=username,
        email=email,
        password="SecurePass123!",
        first_name="Test",
        last_name="User",
    )


def _mock_provider(success=True):
    mock = MagicMock()
    mock.provider_name = "django"
    mock.send_email.return_value = EmailSendResult(
        success=success,
        provider_message_id="test-msg-001",
    )
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# EmailService.send_verification_email
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_PROVIDER="django",
    EMAIL_TRANSACTIONAL_ENABLED=True,
    FRONTEND_URL="https://app.mirubro.com",
    EMAIL_VERIFICATION_TOKEN_HOURS=48,
)
class SendVerificationEmailTest(TestCase):
    """Unit tests for EmailService.send_verification_email."""

    def setUp(self):
        self.user = _make_user()

    @patch("apps.notifications.services.get_email_provider")
    def test_creates_email_delivery(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        result = EmailService.send_verification_email(self.user, TOKEN)

        self.assertTrue(result)
        self.assertEqual(EmailDelivery.objects.filter(to_email=self.user.email).count(), 1)

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_verify_email_template_key(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_verification_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.template_key, "verify_email")

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_user_email_as_recipient(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_verification_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.to_email, self.user.email)

    @patch("apps.notifications.services.get_email_provider")
    def test_html_body_contains_verification_url(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_verification_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        expected_url = f"https://app.mirubro.com/verificar-email?token={TOKEN}"
        self.assertIn(expected_url, delivery.html_body)

    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_linked_to_user(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_verification_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.user_id, self.user.pk)

    @patch("apps.notifications.services.get_email_provider")
    def test_subject_is_correct(self, mock_get):
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_verification_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertEqual(delivery.subject, "Verificá tu email en MiRubro")

    @patch("apps.notifications.services.get_email_provider")
    def test_token_not_stored_in_metadata(self, mock_get):
        """Token must NOT appear in metadata — only in the rendered body."""
        mock_get.return_value = _mock_provider()

        from apps.accounts.services import EmailService
        EmailService.send_verification_email(self.user, TOKEN)

        delivery = EmailDelivery.objects.get(to_email=self.user.email)
        self.assertNotIn(TOKEN, str(delivery.metadata))

    def test_returns_false_and_logs_on_exception(self):
        """If queue_transactional_email raises, send_verification_email returns False."""
        from apps.accounts.services import EmailService

        with patch(
            "apps.accounts.services.queue_transactional_email",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs("apps.accounts.services", level="ERROR"):
                result = EmailService.send_verification_email(self.user, TOKEN)

        self.assertFalse(result)

    def test_uses_async_dispatch_by_default(self):
        """send_verification_email should enqueue, not send synchronously."""
        from apps.accounts.services import EmailService

        with patch("apps.accounts.services.queue_transactional_email") as mock_q:
            mock_q.return_value = MagicMock()
            EmailService.send_verification_email(self.user, TOKEN)

        self.assertIsNotNone(mock_q.call_args)
        call_kwargs = mock_q.call_args[1]
        self.assertTrue(call_kwargs.get("send_async", False))


# ─────────────────────────────────────────────────────────────────────────────
# send_verification_email_task still calls EmailService
# ─────────────────────────────────────────────────────────────────────────────

class SendVerificationEmailTaskTest(TestCase):
    """The Celery task must still delegate to EmailService.send_verification_email."""

    def setUp(self):
        self.user = _make_user(email="taskuser@example.com", username="taskuser@example.com")

    @patch("apps.accounts.services.EmailService.send_verification_email")
    def test_task_calls_email_service(self, mock_method):
        mock_method.return_value = True

        from apps.accounts.tasks import send_verification_email_task
        result = send_verification_email_task(self.user.pk, TOKEN)

        mock_method.assert_called_once_with(self.user, TOKEN)
        self.assertTrue(result)

    def test_task_returns_false_for_missing_user(self):
        from apps.accounts.tasks import send_verification_email_task

        with self.assertLogs("apps.accounts.tasks", level="ERROR"):
            result = send_verification_email_task(999999, TOKEN)

        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────────────
# Smoke: registration and resend views still work
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class RegisterViewSmokeTest(TestCase):
    """Registration view must still return 201 after the migration."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

    @patch("apps.accounts.views.send_verification_email_task")
    def test_registration_returns_201(self, mock_task):
        resp = self.client.post(
            "/api/v1/auth/register/",
            {"email": "newuser@example.com", "password": "SecurePass123!"},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "created")

    @patch("apps.accounts.views.send_verification_email_task")
    def test_registration_dispatches_task(self, mock_task):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                "/api/v1/auth/register/",
                {"email": "newtask@example.com", "password": "SecurePass123!"},
            )
        mock_task.delay.assert_called_once()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUTHENTICATION_BACKENDS=["apps.accounts.auth_backends.UsernameOrEmailBackend"],
)
class ResendVerificationSmokeTest(TestCase):
    """Resend-verification view must still work after the migration."""

    def setUp(self):
        from rest_framework.test import APIClient
        from apps.accounts.models import AccountProfile, Membership
        from apps.business.models import Business, Subscription

        self.user = _make_user(email="resend@example.com", username="resend@example.com")
        profile = self.user.account_profile
        profile.email_verified = False
        profile.save(update_fields=["email_verified"])
        business = Business.objects.create(
            name="Resend HQ", default_service="gestion", status="active"
        )
        Subscription.objects.create(
            business=business, plan="starter", status="active", max_seats=5
        )
        Membership.objects.create(user=self.user, business=business, role="owner")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("apps.accounts.views.send_verification_email_task")
    def test_resend_returns_200_and_queued(self, mock_task):
        resp = self.client.post("/api/v1/auth/resend-verification/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "queued")
        mock_task.delay.assert_called_once()
