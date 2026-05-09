from unittest.mock import MagicMock, patch

from celery.exceptions import MaxRetriesExceededError, Retry
from django.test import TestCase

from apps.notifications.tasks import send_email_delivery


class SendEmailDeliveryTaskTest(TestCase):
    @patch("apps.notifications.services.send_queued_email_delivery")
    def test_task_calls_service_with_delivery_id(self, mock_service):
        mock_service.return_value = MagicMock()
        send_email_delivery.apply(args=["test-delivery-id-001"])
        mock_service.assert_called_once_with("test-delivery-id-001")

    @patch("apps.notifications.services.send_queued_email_delivery")
    def test_task_raises_retry_on_unexpected_exception(self, mock_service):
        mock_service.side_effect = RuntimeError("Unexpected DB error")
        with self.assertRaises((Retry, MaxRetriesExceededError)):
            send_email_delivery.apply(args=["bad-id"], throw=True)

    @patch("apps.notifications.services.send_queued_email_delivery")
    def test_task_does_not_raise_on_success(self, mock_service):
        mock_service.return_value = MagicMock()
        # Should complete without raising
        result = send_email_delivery.apply(args=["ok-delivery-id"])
        self.assertIsNone(result.result)
