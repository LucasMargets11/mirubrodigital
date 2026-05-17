"""
Notifications for the QR de Reseñas domain.

QR de Reseñas does NOT send any emails (no admin alert, no digest, no owner email).

The only allowed outbound action is an in-app AdminNotification for genuinely
negative reviews (rating ≤ 3), created via create_admin_notification().
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_negative_feedback(review) -> None:
    """
    Create an in-app AdminNotification for genuinely negative reviews (rating ≤ 3).

    No email is sent. Fire-and-forget: failures are logged but never propagated.
    Returns None (previously returned bool for email enqueue; callers should not
    rely on the return value).
    """
    if review.rating > 3:
        return None

    business = review.business
    try:
        from apps.accounts.admin_notification_service import create_admin_notification
        create_admin_notification(
            notif_type='review_negative',
            severity='warning',
            target_role='support_agent',
            title='Nueva reseña negativa',
            message=f'{business.name} recibió una reseña de {review.rating} estrellas.',
            business=business,
            related_object_type='review',
            related_object_id=str(review.id),
            action_url='/admin/notificaciones',
            metadata={
                'rating': review.rating,
                'review_id': str(review.id),
            },
            dedupe_window_seconds=3600,
        )
    except Exception:
        logger.exception(
            '[ReviewNotif] create_admin_notification failed for business=%s review=%s',
            business.id, review.id,
        )
    return None
