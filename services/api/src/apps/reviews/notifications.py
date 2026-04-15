"""
Email notifications for the QR de Reseñas domain.

Sends a transactional email to the business owner when negative
feedback is submitted via the public smart-filter flow.

Anti-spam: at most 1 email per business per hour (Django cache).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

from apps.accounts.models import Membership

logger = logging.getLogger(__name__)

# At most one notification email per business per hour.
_THROTTLE_SECONDS = 3600
_CACHE_PREFIX = 'review_notif:'


def _throttle_key(business_id: int) -> str:
    return f"{_CACHE_PREFIX}{business_id}"


def _is_throttled(business_id: int) -> bool:
    return cache.get(_throttle_key(business_id)) is not None


def _mark_sent(business_id: int) -> None:
    cache.set(_throttle_key(business_id), 1, timeout=_THROTTLE_SECONDS)


def _get_owner_email(business) -> str | None:
    """Return the email of the first active owner with a non-empty address."""
    membership = (
        Membership.objects
        .filter(business=business, role='owner', status=Membership.Status.ACTIVE)
        .select_related('user')
        .first()
    )
    if membership and membership.user.email:
        return membership.user.email
    return None


def notify_negative_feedback(review) -> bool:
    """
    Send an email to the business owner about new negative feedback.

    Returns True if the email was sent, False if skipped or failed.
    Failures are logged but never propagated.
    """
    business = review.business

    # Throttle: 1 email per business per hour
    if _is_throttled(business.id):
        logger.debug(
            "[ReviewNotif] Throttled for business=%s (already sent recently)", business.id
        )
        return False

    owner_email = _get_owner_email(business)
    if not owner_email:
        logger.warning("[ReviewNotif] No owner email for business=%s", business.id)
        return False

    # Build email content
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    feedback_url = f"{frontend_url}/app/resenas/feedback"

    stars = '★' * review.rating + '☆' * (5 - review.rating)
    comment_line = f"\nComentario: {review.comment}\n" if review.comment else ""
    contact_line = f"Contacto: {review.contact_info}\n" if review.contact_info else ""

    subject = f"Nuevo feedback en {business.name} — {review.rating}★"
    body = (
        f"Hola,\n\n"
        f"Tu negocio {business.name} recibió una nueva opinión de un cliente:\n\n"
        f"  Puntaje: {stars} ({review.rating}/5)\n"
        f"{comment_line}"
        f"{contact_line}"
        f"\nPodés ver y gestionar el feedback desde tu panel:\n\n"
        f"  {feedback_url}\n\n"
        f"— Mirubro"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[owner_email],
            fail_silently=False,
        )
        _mark_sent(business.id)
        logger.info(
            "[ReviewNotif] Sent email to %s for business=%s review=%s",
            owner_email, business.id, review.id,
        )
        return True
    except Exception:
        logger.exception(
            "[ReviewNotif] Failed to send email for business=%s", business.id
        )
        return False
