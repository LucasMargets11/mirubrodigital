from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import EmailDelivery


class EmailDeliveryModelTest(TestCase):
    def _make_delivery(self, **kwargs):
        defaults = dict(
            to_email="test@example.com",
            from_email="MiRubro <notificaciones@mirubro.com>",
            subject="Test Subject",
            template_key="test.template",
        )
        defaults.update(kwargs)
        return EmailDelivery.objects.create(**defaults)

    def test_create_minimal(self):
        delivery = self._make_delivery()
        self.assertIsNotNone(delivery.pk)
        self.assertEqual(delivery.to_email, "test@example.com")

    def test_default_status_is_queued(self):
        delivery = self._make_delivery()
        self.assertEqual(delivery.status, EmailDelivery.Status.QUEUED)

    def test_default_provider_is_django(self):
        delivery = self._make_delivery()
        self.assertEqual(delivery.provider, EmailDelivery.Provider.DJANGO)

    def test_str_representation(self):
        delivery = self._make_delivery(
            template_key="account.verify",
            to_email="user@example.com",
        )
        expected = "account.verify → user@example.com [queued]"
        self.assertEqual(str(delivery), expected)

    def test_mark_sending(self):
        delivery = self._make_delivery()
        delivery.mark_sending()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.Status.SENDING)
        self.assertEqual(delivery.error_message, "")

    def test_mark_sent(self):
        delivery = self._make_delivery()
        before = timezone.now()
        delivery.mark_sent(provider_message_id="ses-msg-001")
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.Status.SENT)
        self.assertEqual(delivery.provider_message_id, "ses-msg-001")
        self.assertIsNotNone(delivery.sent_at)
        self.assertGreaterEqual(delivery.sent_at, before)
        self.assertEqual(delivery.error_message, "")

    def test_mark_sent_without_message_id(self):
        delivery = self._make_delivery()
        delivery.mark_sent()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.Status.SENT)
        self.assertEqual(delivery.provider_message_id, "")

    def test_mark_failed(self):
        delivery = self._make_delivery()
        before = timezone.now()
        delivery.mark_failed("SMTP connection refused")
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.Status.FAILED)
        self.assertEqual(delivery.error_message, "SMTP connection refused")
        self.assertIsNotNone(delivery.failed_at)
        self.assertGreaterEqual(delivery.failed_at, before)

    def test_mark_failed_truncates_long_message(self):
        delivery = self._make_delivery()
        long_error = "x" * 6000
        delivery.mark_failed(long_error)
        delivery.refresh_from_db()
        self.assertEqual(len(delivery.error_message), 5000)

    def test_metadata_defaults_to_empty_dict(self):
        delivery = self._make_delivery()
        self.assertEqual(delivery.metadata, {})

    def test_uuid_primary_key(self):
        delivery = self._make_delivery()
        import uuid
        self.assertIsInstance(delivery.pk, uuid.UUID)
