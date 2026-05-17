from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings

from apps.notifications.providers.amazon_ses import AmazonSESProvider
from apps.notifications.providers.base import EmailSendResult
from apps.notifications.providers.django_email import DjangoEmailProvider


class DjangoEmailProviderTest(TestCase):
    def setUp(self):
        self.provider = DjangoEmailProvider()

    def test_send_email_places_in_outbox(self):
        result = self.provider.send_email(
            to_email="recipient@example.com",
            from_email="MiRubro <notificaciones@mirubro.com>",
            subject="Test Subject",
            html_body="<p>Hello</p>",
            text_body="Hello",
        )
        self.assertTrue(result.success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["recipient@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Test Subject")

    def test_send_email_attaches_html_alternative(self):
        self.provider.send_email(
            to_email="r@example.com",
            from_email="MiRubro <notificaciones@mirubro.com>",
            subject="HTML Test",
            html_body="<p>HTML content</p>",
            text_body="HTML content",
        )
        msg = mail.outbox[0]
        content_types = [alt[1] for alt in msg.alternatives]
        self.assertIn("text/html", content_types)

    def test_send_email_returns_empty_provider_message_id(self):
        result = self.provider.send_email(
            to_email="r@example.com",
            from_email="no-reply@mirubro.com",
            subject="S",
            text_body="body",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.provider_message_id, "")

    def test_send_email_returns_result_instance(self):
        result = self.provider.send_email(
            to_email="r@example.com",
            from_email="no-reply@mirubro.com",
            subject="S",
            text_body="body",
        )
        self.assertIsInstance(result, EmailSendResult)


class AmazonSESProviderTest(SimpleTestCase):
    def _make_client(self, message_id="ses-abc-123"):
        client = MagicMock()
        client.send_email.return_value = {"MessageId": message_id}
        return client

    def test_send_email_calls_ses_client(self):
        client = self._make_client()
        result = AmazonSESProvider(client=client).send_email(
            to_email="user@example.com",
            from_email="MiRubro <notificaciones@mirubro.com>",
            subject="Hello",
            html_body="<p>Hi</p>",
            text_body="Hi",
        )
        self.assertTrue(result.success)
        self.assertTrue(client.send_email.called)

    def test_send_email_returns_message_id(self):
        client = self._make_client(message_id="ses-msg-999")
        result = AmazonSESProvider(client=client).send_email(
            to_email="u@example.com",
            from_email="n@mirubro.com",
            subject="S",
            html_body="<p>body</p>",
            text_body="body",
        )
        self.assertEqual(result.provider_message_id, "ses-msg-999")

    @override_settings(AWS_SES_CONFIGURATION_SET="my-config-set")
    def test_send_email_includes_configuration_set(self):
        client = self._make_client()
        AmazonSESProvider(client=client).send_email(
            to_email="u@example.com",
            from_email="n@mirubro.com",
            subject="S",
            html_body="<p>body</p>",
            text_body="body",
        )
        call_kwargs = client.send_email.call_args[1]
        self.assertEqual(call_kwargs.get("ConfigurationSetName"), "my-config-set")

    @override_settings(AWS_SES_CONFIGURATION_SET="")
    def test_send_email_omits_configuration_set_when_empty(self):
        client = self._make_client()
        AmazonSESProvider(client=client).send_email(
            to_email="u@example.com",
            from_email="n@mirubro.com",
            subject="S",
            html_body="<p>body</p>",
            text_body="body",
        )
        call_kwargs = client.send_email.call_args[1]
        self.assertNotIn("ConfigurationSetName", call_kwargs)

    def test_send_email_returns_failure_on_client_error(self):
        client = MagicMock()
        client.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}},
            "SendEmail",
        )
        result = AmazonSESProvider(client=client).send_email(
            to_email="u@example.com",
            from_email="n@mirubro.com",
            subject="S",
            html_body="<p>body</p>",
            text_body="body",
        )
        self.assertFalse(result.success)
        self.assertIn("MessageRejected", result.error_message)

    def test_send_email_refuses_empty_bodies_without_calling_ses(self):
        client = self._make_client()
        result = AmazonSESProvider(client=client).send_email(
            to_email="u@example.com",
            from_email="n@mirubro.com",
            subject="S",
            html_body="",
            text_body="",
        )
        self.assertFalse(result.success)
        self.assertFalse(client.send_email.called)

    def test_payload_structure(self):
        client = self._make_client()
        AmazonSESProvider(client=client).send_email(
            to_email="u@example.com",
            from_email="Sender <n@mirubro.com>",
            subject="My Subject",
            html_body="<p>HTML</p>",
            text_body="Text",
        )
        call_kwargs = client.send_email.call_args[1]
        self.assertEqual(call_kwargs["FromEmailAddress"], "Sender <n@mirubro.com>")
        self.assertEqual(call_kwargs["Destination"]["ToAddresses"], ["u@example.com"])
        body = call_kwargs["Content"]["Simple"]["Body"]
        self.assertEqual(body["Html"]["Data"], "<p>HTML</p>")
        self.assertEqual(body["Text"]["Data"], "Text")
