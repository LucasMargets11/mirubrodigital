import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.notifications.models import EmailDelivery
from apps.notifications.providers.base import EmailSendResult
from apps.notifications.providers.amazon_ses import AmazonSESProvider
from apps.notifications.providers.django_email import DjangoEmailProvider
from apps.notifications.services import (
    get_email_provider,
    queue_transactional_email,
    render_email_template,
    send_queued_email_delivery,
)


class GetEmailProviderTest(TestCase):
    @override_settings(EMAIL_PROVIDER="django", EMAIL_TRANSACTIONAL_ENABLED=True)
    def test_returns_django_provider_by_default(self):
        provider = get_email_provider()
        self.assertIsInstance(provider, DjangoEmailProvider)

    @override_settings(EMAIL_PROVIDER="amazon_ses", EMAIL_TRANSACTIONAL_ENABLED=True)
    def test_returns_ses_provider_when_configured(self):
        provider = get_email_provider()
        self.assertIsInstance(provider, AmazonSESProvider)

    @override_settings(EMAIL_PROVIDER="amazon_ses", EMAIL_TRANSACTIONAL_ENABLED=False)
    def test_returns_django_provider_when_transactional_disabled(self):
        provider = get_email_provider()
        self.assertIsInstance(provider, DjangoEmailProvider)

    @override_settings(EMAIL_PROVIDER="unknown_value", EMAIL_TRANSACTIONAL_ENABLED=True)
    def test_returns_django_provider_for_unknown_value(self):
        provider = get_email_provider()
        self.assertIsInstance(provider, DjangoEmailProvider)


class RenderEmailTemplateTest(TestCase):
    def test_render_generic_template_includes_context(self):
        html, text = render_email_template("generic", {"title": "Hola Mundo", "message": "Mensaje de prueba"})
        self.assertIn("Hola Mundo", html)
        self.assertIn("Mensaje de prueba", html)

    def test_text_body_is_stripped_html(self):
        html, text = render_email_template("generic", {"title": "Test", "message": "Texto plano"})
        self.assertNotIn("<", text)
        self.assertGreater(len(text), 0)

    def test_fallback_to_generic_for_unknown_key(self):
        # Must not raise; falls back to generic.html
        html, text = render_email_template("does_not_exist_template_xyz123")
        self.assertIsInstance(html, str)
        self.assertGreater(len(html), 0)

    def test_base_context_includes_app_name(self):
        html, _ = render_email_template("generic")
        self.assertIn("MiRubro", html)

    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_base_context_includes_support_email(self):
        html, _ = render_email_template("generic")
        self.assertIn("soporte@mirubro.com", html)


class QueueTransactionalEmailTest(TestCase):
    def _mock_provider(self, success=True, message_id="msg-001", error=""):
        mock_provider = MagicMock()
        mock_provider.provider_name = "django"
        mock_provider.send_email.return_value = EmailSendResult(
            success=success,
            provider_message_id=message_id,
            error_message=error,
        )
        return mock_provider

    @patch("apps.notifications.services.get_email_provider")
    def test_creates_delivery_record(self, mock_get):
        mock_get.return_value = self._mock_provider()
        delivery = queue_transactional_email(
            to_email="u@example.com",
            subject="Test",
            template_key="generic",
            send_async=False,
        )
        self.assertIsNotNone(delivery.pk)
        self.assertEqual(delivery.to_email, "u@example.com")

    @patch("apps.notifications.services.get_email_provider")
    def test_delivery_status_sent_after_sync_send(self, mock_get):
        mock_get.return_value = self._mock_provider(success=True)
        delivery = queue_transactional_email(
            to_email="u@example.com",
            subject="Test",
            send_async=False,
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.Status.SENT)

    @override_settings(EMAIL_TRANSACTIONAL_ENABLED=False)
    @patch("apps.notifications.services.get_email_provider")
    def test_marks_failed_when_transactional_disabled(self, mock_get):
        delivery = queue_transactional_email(
            to_email="u@example.com",
            subject="Test",
            send_async=False,
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.Status.FAILED)
        self.assertIn("disabled", delivery.error_message)
        mock_get.assert_not_called()

    @patch("apps.notifications.services.get_email_provider")
    def test_persists_html_and_text_body(self, mock_get):
        mock_get.return_value = self._mock_provider()
        delivery = queue_transactional_email(
            to_email="u@example.com",
            subject="Test",
            template_key="generic",
            context={"title": "Hi", "message": "World"},
            send_async=False,
        )
        self.assertIn("Hi", delivery.html_body)
        self.assertGreater(len(delivery.text_body), 0)

    @patch("apps.notifications.services.get_email_provider")
    def test_uses_default_from_email(self, mock_get):
        mock_get.return_value = self._mock_provider()
        delivery = queue_transactional_email(
            to_email="u@example.com",
            subject="S",
            send_async=False,
        )
        self.assertIn("mirubro.com", delivery.from_email)

    @patch("apps.notifications.services.get_email_provider")
    def test_custom_from_email_overrides_default(self, mock_get):
        mock_get.return_value = self._mock_provider()
        delivery = queue_transactional_email(
            to_email="u@example.com",
            subject="S",
            from_email="custom@example.com",
            send_async=False,
        )
        self.assertEqual(delivery.from_email, "custom@example.com")


class SendQueuedEmailDeliveryTest(TestCase):
    def _create_delivery(self, **kwargs):
        defaults = dict(
            to_email="u@example.com",
            from_email="MiRubro <notificaciones@mirubro.com>",
            subject="Test",
            template_key="generic",
            html_body="<p>Hi</p>",
            text_body="Hi",
        )
        defaults.update(kwargs)
        return EmailDelivery.objects.create(**defaults)

    @patch("apps.notifications.services.get_email_provider")
    def test_marks_sent_on_success(self, mock_get):
        mock_provider = MagicMock()
        mock_provider.provider_name = "django"
        mock_provider.send_email.return_value = EmailSendResult(
            success=True, provider_message_id="id-001"
        )
        mock_get.return_value = mock_provider

        delivery = self._create_delivery()
        result = send_queued_email_delivery(delivery.pk)
        result.refresh_from_db()
        self.assertEqual(result.status, EmailDelivery.Status.SENT)
        self.assertEqual(result.provider_message_id, "id-001")

    @patch("apps.notifications.services.get_email_provider")
    def test_marks_failed_on_provider_failure(self, mock_get):
        mock_provider = MagicMock()
        mock_provider.provider_name = "django"
        mock_provider.send_email.return_value = EmailSendResult(
            success=False, error_message="Connection refused"
        )
        mock_get.return_value = mock_provider

        delivery = self._create_delivery()
        result = send_queued_email_delivery(delivery.pk)
        result.refresh_from_db()
        self.assertEqual(result.status, EmailDelivery.Status.FAILED)
        self.assertIn("Connection refused", result.error_message)

    @patch("apps.notifications.services.get_email_provider")
    def test_does_not_resend_already_sent_delivery(self, mock_get):
        mock_provider = MagicMock()
        mock_get.return_value = mock_provider

        delivery = self._create_delivery()
        delivery.mark_sending()
        delivery.mark_sent(provider_message_id="already-sent")

        result = send_queued_email_delivery(delivery.pk)
        mock_provider.send_email.assert_not_called()
        self.assertEqual(result.status, EmailDelivery.Status.SENT)

    def test_returns_none_for_missing_delivery(self):
        result = send_queued_email_delivery(uuid.uuid4())
        self.assertIsNone(result)

    @patch("apps.notifications.services.get_email_provider")
    def test_unexpected_provider_exception_propagates(self, mock_get):
        mock_provider = MagicMock()
        mock_provider.send_email.side_effect = RuntimeError("DB exploded")
        mock_get.return_value = mock_provider

        delivery = self._create_delivery()
        with self.assertRaises(RuntimeError):
            send_queued_email_delivery(delivery.pk)
