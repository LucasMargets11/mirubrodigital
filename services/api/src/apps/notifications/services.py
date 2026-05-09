"""
notifications/services.py — Core functions for transactional email dispatch.

Public API:
    get_email_provider()            → active BaseEmailProvider instance
    render_email_template(key, ctx) → (html_body, text_body)
    queue_transactional_email(...)  → EmailDelivery (persisted, optionally enqueued)
    send_transactional_email(...)   → EmailDelivery (sent synchronously)
    send_queued_email_delivery(id)  → EmailDelivery | None
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import EmailDelivery
from .providers import AmazonSESProvider, DjangoEmailProvider

logger = logging.getLogger(__name__)


def get_email_provider():
    """
    Return the active email provider based on settings.

    Rules:
      - EMAIL_PROVIDER == 'amazon_ses' AND EMAIL_TRANSACTIONAL_ENABLED=True → AmazonSESProvider
      - anything else → DjangoEmailProvider
    """
    if (
        getattr(settings, "EMAIL_PROVIDER", "django") == "amazon_ses"
        and getattr(settings, "EMAIL_TRANSACTIONAL_ENABLED", True)
    ):
        return AmazonSESProvider()
    return DjangoEmailProvider()


def render_email_template(template_key, context=None):
    """
    Render HTML and plain-text bodies for the given template_key.

    Lookup order:
      1. emails/{template_key}.html
      2. emails/generic.html  (fallback)

    Returns: (html_body: str, text_body: str)
    """
    ctx = {
        "app_name": "MiRubro",
        "support_email": getattr(settings, "SUPPORT_EMAIL", ""),
        "frontend_url": getattr(settings, "FRONTEND_URL", ""),
    }
    if context:
        ctx.update(context)

    template_name = f"emails/{template_key}.html"
    try:
        html_body = render_to_string(template_name, ctx)
    except TemplateDoesNotExist:
        logger.debug(
            "Template '%s' not found, falling back to emails/generic.html",
            template_name,
        )
        html_body = render_to_string("emails/generic.html", ctx)

    text_body = strip_tags(html_body).strip()
    return html_body, text_body


def queue_transactional_email(
    *,
    to_email,
    subject,
    template_key="generic",
    context=None,
    business=None,
    user=None,
    from_email=None,
    metadata=None,
    send_async=True,
):
    """
    Render, persist and optionally dispatch a transactional email.

    - If EMAIL_TRANSACTIONAL_ENABLED=False: creates the delivery and immediately
      marks it failed with an explanatory message. No send attempt is made.
    - If send_async=True: enqueues send_email_delivery Celery task.
    - If send_async=False: sends synchronously via send_queued_email_delivery.

    Returns the EmailDelivery instance.
    """
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    metadata = metadata or {}

    html_body, text_body = render_email_template(template_key, context)

    delivery = EmailDelivery.objects.create(
        to_email=to_email,
        from_email=from_email,
        subject=subject,
        template_key=template_key,
        html_body=html_body,
        text_body=text_body,
        business=business,
        user=user,
        metadata=metadata,
        status=EmailDelivery.Status.QUEUED,
    )

    if not getattr(settings, "EMAIL_TRANSACTIONAL_ENABLED", True):
        delivery.mark_failed("EMAIL_TRANSACTIONAL_ENABLED is disabled.")
        logger.info(
            "Transactional email suppressed (disabled): template=%s to=%s",
            template_key,
            to_email,
        )
        return delivery

    if send_async:
        from .tasks import send_email_delivery
        send_email_delivery.delay(str(delivery.id))
    else:
        send_queued_email_delivery(delivery.id)

    return delivery


def send_transactional_email(
    *,
    to_email,
    subject,
    template_key="generic",
    context=None,
    business=None,
    user=None,
    from_email=None,
    metadata=None,
):
    """Synchronous convenience wrapper around queue_transactional_email."""
    return queue_transactional_email(
        to_email=to_email,
        subject=subject,
        template_key=template_key,
        context=context,
        business=business,
        user=user,
        from_email=from_email,
        metadata=metadata,
        send_async=False,
    )


def send_queued_email_delivery(delivery_id):
    """
    Locate an EmailDelivery by pk, send it via the active provider and update status.

    - Already-sent deliveries are skipped without re-sending.
    - Provider failures (success=False) mark the delivery as failed without raising.
    - Unexpected exceptions from the provider propagate to allow Celery retry.

    Returns the EmailDelivery instance, or None if not found.
    """
    try:
        delivery = EmailDelivery.objects.get(pk=delivery_id)
    except EmailDelivery.DoesNotExist:
        logger.error("EmailDelivery not found: %s", delivery_id)
        return None

    if delivery.status == EmailDelivery.Status.SENT:
        logger.info("EmailDelivery %s already sent, skipping.", delivery_id)
        return delivery

    delivery.mark_sending()

    provider = get_email_provider()
    try:
        result = provider.send_email(
            to_email=delivery.to_email,
            from_email=delivery.from_email,
            subject=delivery.subject,
            html_body=delivery.html_body,
            text_body=delivery.text_body,
            metadata=delivery.metadata,
        )
    except Exception as exc:
        # Unexpected provider error — propagate so the Celery task can retry.
        logger.exception(
            "Unexpected provider error for delivery %s: %s", delivery_id, exc
        )
        raise

    if result.success:
        delivery.mark_sent(provider_message_id=result.provider_message_id)
        logger.info(
            "Email sent: template=%s to=%s provider=%s msg_id=%s",
            delivery.template_key,
            delivery.to_email,
            provider.provider_name,
            result.provider_message_id,
        )
    else:
        delivery.mark_failed(result.error_message)
        logger.error(
            "Email failed: template=%s to=%s provider=%s error=%s",
            delivery.template_key,
            delivery.to_email,
            provider.provider_name,
            result.error_message,
        )

    return delivery
