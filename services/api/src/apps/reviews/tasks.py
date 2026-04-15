"""
reviews/tasks.py — Celery periodic tasks for the QR de Reseñas domain.

send_weekly_digest
------------------
Sends a weekly summary email to business owners with smart-filter access.
Scheduled via CELERY_BEAT_SCHEDULE (Mondays at 09:00 UTC-3).

Design:
  - Idempotent: cache guard per business per ISO-week prevents duplicates.
  - Does not send empty digests (skip when 0 reviews AND 0 visits).
  - Only targets businesses with active qr_reviews subscriptions and
    smart_filter_allowed entitlement (Pro or trial).
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name='reviews.send_weekly_digest',
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
def send_weekly_digest():
    """
    Iterate eligible businesses and send the weekly digest email.

    Returns a summary dict: ``{'sent': int, 'skipped': int, 'failed': int}``.
    """
    from .digest import run_weekly_digest

    result = run_weekly_digest()
    logger.info(
        "[ReviewDigest] Weekly digest complete: sent=%d skipped=%d failed=%d",
        result['sent'], result['skipped'], result['failed'],
    )
    return result
