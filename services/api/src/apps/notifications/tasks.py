"""
notifications/tasks.py — Celery tasks for transactional email dispatch.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_email_delivery",
    acks_late=True,
)
def send_email_delivery(self, delivery_id):
    """
    Dispatch a single EmailDelivery by its UUID string.

    Retries up to 3 times (60 s apart) on unexpected exceptions.
    Controlled provider failures (success=False) do NOT trigger a retry —
    the delivery is already marked as failed and the error is persisted.
    """
    from .services import send_queued_email_delivery

    try:
        send_queued_email_delivery(delivery_id)
    except Exception as exc:
        logger.exception(
            "Unexpected error in send_email_delivery task for %s: %s",
            delivery_id,
            exc,
        )
        raise self.retry(exc=exc)
