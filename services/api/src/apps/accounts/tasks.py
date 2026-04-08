"""
accounts/tasks.py — Celery tasks for async email delivery.

send_verification_email
-----------------------
Sends the verification email outside the HTTP request cycle.
Called via transaction.on_commit() in RegisterView so the email is only
dispatched after the user row is committed.

Design principles:
  - Accepts primitive arguments (user_id, token) so the task is serializable.
  - Failures are logged by EmailService; the task does NOT retry automatically
    because verification tokens have a long TTL and the user can request a new one.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='accounts.send_verification_email')
def send_verification_email_task(user_id: int, token: str) -> bool:
    """Send verification email asynchronously via Celery worker."""
    from django.contrib.auth import get_user_model

    from apps.accounts.services import EmailService

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error(
            '[send_verification_email_task] User id=%s not found, skipping email',
            user_id,
        )
        return False

    return EmailService.send_verification_email(user, token)


@shared_task(name='accounts.flush_expired_tokens')
def flush_expired_tokens_task() -> int:
    """Purge expired outstanding/blacklisted JWT tokens to prevent table bloat.

    Wraps the management command provided by simplejwt.token_blacklist.
    Scheduled daily via CELERY_BEAT_SCHEDULE.
    """
    from django.core.management import call_command

    call_command('flushexpiredtokens')
    logger.info('[flush_expired_tokens_task] Flushed expired tokens')
