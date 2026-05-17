"""
Weekly digest for QR de Reseñas.

QR de Reseñas does NOT send any emails. The weekly digest email
(reviews_weekly_digest) has been removed per product policy.

compute_digest_stats() is kept because it is a useful lightweight
aggregation helper used elsewhere. send_digest_for_business() and
run_weekly_digest() are retained as no-ops so existing Celery task
wiring does not break.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg
from django.utils import timezone

from apps.business.models import Business, Subscription

from .entitlements import smart_filter_allowed
from .models import Review, ReviewConfig, ReviewVisit

logger = logging.getLogger(__name__)

# Cache guard retained so the no-op is idempotent (harmless).
_DIGEST_CACHE_PREFIX = 'review_digest:'
_DIGEST_CACHE_TTL = 7 * 86400  # 7 days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _digest_cache_key(business_id: int) -> str:
    """Per-business key to prevent duplicate runs within a week."""
    week = timezone.now().isocalendar()
    return f"{_DIGEST_CACHE_PREFIX}{business_id}:{week.year}W{week.week:02d}"


def _already_sent(business_id: int) -> bool:
    return cache.get(_digest_cache_key(business_id)) is not None


def _mark_digest_sent(business_id: int) -> None:
    cache.set(_digest_cache_key(business_id), 1, timeout=_DIGEST_CACHE_TTL)


# ---------------------------------------------------------------------------
# Digest payload computation (lightweight — only 7-day window)
# ---------------------------------------------------------------------------

def compute_digest_stats(business, *, days: int = 7) -> dict | None:
    """
    Return a dict with 7-day summary metrics, or None if nothing happened.

    Fields:
      new_reviews     – reviews created in window
      negative_count  – reviews below threshold
      unread_count    – reviews still in status 'new' (all time)
      avg_rating      – average rating of reviews in window (or None)
      visits          – QR scan count in window
    """
    now = timezone.now()
    cutoff = now - timedelta(days=days)

    reviews_qs = Review.objects.filter(business=business, created_at__gte=cutoff)
    new_reviews = reviews_qs.count()

    visits = ReviewVisit.objects.filter(business=business, created_at__gte=cutoff).count()

    # Skip digest when nothing happened.
    if new_reviews == 0 and visits == 0:
        return None

    # Threshold for positive/negative split.
    try:
        config = business.review_config
        threshold = config.redirect_threshold
    except ReviewConfig.DoesNotExist:
        threshold = 4

    negative_count = reviews_qs.filter(rating__lt=threshold).count()

    avg_obj = reviews_qs.aggregate(avg=Avg('rating'))
    avg_rating = round(float(avg_obj['avg']), 1) if avg_obj['avg'] is not None else None

    # All-time unread count (status 'new') — useful for operational reporting.
    unread_count = Review.objects.filter(business=business, status='new').count()

    return {
        'new_reviews': new_reviews,
        'negative_count': negative_count,
        'unread_count': unread_count,
        'avg_rating': avg_rating,
        'visits': visits,
    }


# ---------------------------------------------------------------------------
# No-op digest runner — email removed per product policy
# ---------------------------------------------------------------------------

def send_digest_for_business(business) -> bool:
    """
    No-op. QR de Reseñas does not send digest emails.

    Kept to avoid import errors in Celery tasks and tests. Always returns False.
    """
    return False


def run_weekly_digest() -> dict:
    """
    No-op. QR de Reseñas does not send digest emails.

    Kept to avoid import errors in Celery task wiring. Returns empty summary.
    """
    return {'sent': 0, 'skipped': 0, 'failed': 0}
