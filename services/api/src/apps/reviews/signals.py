"""
Django signals for the QR de Reseñas domain.

Notifies the business owner via email when a new internal review
(negative feedback) is created, only if the business has smart-filter
access (Pro or trial).
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .entitlements import smart_filter_allowed
from .models import Review
from .notifications import notify_negative_feedback
from .views import invalidate_review_stats_cache

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Review)
def on_review_created(sender, instance, created, **kwargs):
    """Invalidate stats cache and send owner notification for new reviews."""
    if not created:
        return

    invalidate_review_stats_cache(instance.business_id)

    # Only notify when smart-filter is active (Pro / trial)
    if not smart_filter_allowed(instance.business):
        logger.debug(
            "[Reviews] Signal skip notification business=%s reason=no_smart_filter",
            instance.business_id,
        )
        return

    logger.info(
        "[Reviews] Signal notify business=%s review=%s rating=%s",
        instance.business_id, instance.id, instance.rating,
    )
    notify_negative_feedback(instance)
