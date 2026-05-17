import logging

from django.core.mail import EmailMultiAlternatives

from .base import BaseEmailProvider, EmailSendResult

logger = logging.getLogger(__name__)


class DjangoEmailProvider(BaseEmailProvider):
    provider_name = "django"

    def send_email(self, *, to_email, from_email, subject, html_body="", text_body="", metadata=None):
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body or " ",
                from_email=from_email,
                to=[to_email],
            )
            if html_body:
                msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)
            return EmailSendResult(success=True)
        except Exception as exc:
            logger.exception("DjangoEmailProvider failed for %s: %s", to_email, exc)
            return EmailSendResult(success=False, error_message=str(exc))
