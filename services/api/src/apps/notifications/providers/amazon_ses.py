import logging

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from .base import BaseEmailProvider, EmailSendResult

logger = logging.getLogger(__name__)


class AmazonSESProvider(BaseEmailProvider):
    """
    Send transactional emails via Amazon SES v2 API.

    Credentials are resolved by the IAM Role attached to the instance/task.
    No access keys are used. No SMTP is used.
    """

    provider_name = "amazon_ses"

    def __init__(self, client=None):
        """
        Accept an optional pre-built boto3 SESv2 client for dependency injection.
        In production, pass no argument — the IAM Role resolves credentials automatically.
        In tests, inject a MagicMock client to avoid real AWS calls.
        """
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        import boto3
        return boto3.client("sesv2", region_name=settings.AWS_SES_REGION)

    def send_email(self, *, to_email, from_email, subject, html_body="", text_body="", metadata=None):
        if not html_body and not text_body:
            return EmailSendResult(
                success=False,
                error_message="Both html_body and text_body are empty. Refusing to call SES.",
            )

        payload = {
            "FromEmailAddress": from_email,
            "Destination": {"ToAddresses": [to_email]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body or "", "Charset": "UTF-8"},
                        "Html": {"Data": html_body or "", "Charset": "UTF-8"},
                    },
                }
            },
        }

        configuration_set = getattr(settings, "AWS_SES_CONFIGURATION_SET", "")
        if configuration_set:
            payload["ConfigurationSetName"] = configuration_set

        try:
            client = self._get_client()
            response = client.send_email(**payload)
            message_id = response.get("MessageId", "")
            return EmailSendResult(success=True, provider_message_id=message_id)
        except (ClientError, BotoCoreError) as exc:
            logger.error("AmazonSESProvider error sending to %s: %s", to_email, exc)
            return EmailSendResult(success=False, error_message=str(exc))
        except Exception as exc:
            logger.exception("AmazonSESProvider unexpected error sending to %s: %s", to_email, exc)
            return EmailSendResult(success=False, error_message=str(exc))
