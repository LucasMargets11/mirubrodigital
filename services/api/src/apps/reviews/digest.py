"""
Weekly digest email for QR de Reseñas.

Sends a concise operational summary to business owners who have
smart-filter access (Pro plan or active trial).  The digest covers
the last 7 days and is designed to be *useful without opening the app*.

Anti-spam rules:
  - Never sent when nothing happened (0 new reviews AND 0 visits).
  - Separate from the real-time negative-feedback alert (notifications.py).
  - At most 1 digest per business per execution window (idempotent via
    cache guard keyed on ISO-week).

Stats are computed in a lightweight manner, NOT reusing the full
ReviewStatsView._compute_stats (which includes 30-day trend,
recent_reviews serialization, etc.).  Only the fields needed for
the digest body are queried.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Avg, Count
from django.utils import timezone

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

from .entitlements import smart_filter_allowed
from .models import Review, ReviewConfig, ReviewVisit

logger = logging.getLogger(__name__)

# Cache guard — one digest per business per calendar week.
_DIGEST_CACHE_PREFIX = 'review_digest:'
_DIGEST_CACHE_TTL = 7 * 86400  # 7 days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _digest_cache_key(business_id: int) -> str:
    """Per-business key to prevent duplicate sends within a week."""
    week = timezone.now().isocalendar()
    return f"{_DIGEST_CACHE_PREFIX}{business_id}:{week.year}W{week.week:02d}"


def _already_sent(business_id: int) -> bool:
    return cache.get(_digest_cache_key(business_id)) is not None


def _mark_digest_sent(business_id: int) -> None:
    cache.set(_digest_cache_key(business_id), 1, timeout=_DIGEST_CACHE_TTL)


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

    # All-time unread count (status 'new') — important for operational digest.
    unread_count = Review.objects.filter(business=business, status='new').count()

    return {
        'new_reviews': new_reviews,
        'negative_count': negative_count,
        'unread_count': unread_count,
        'avg_rating': avg_rating,
        'visits': visits,
    }


# ---------------------------------------------------------------------------
# Email body
# ---------------------------------------------------------------------------

def _build_digest_body(business_name: str, stats: dict, feedback_url: str, analytics_url: str) -> str:
    """Build the plain-text digest email body."""
    lines = [
        f"Hola,\n",
        f"Resumen semanal de Reseñas para {business_name}:\n",
    ]

    lines.append(f"  • Nuevas reseñas: {stats['new_reviews']}")
    if stats['avg_rating'] is not None:
        lines.append(f"  • Promedio de la semana: {stats['avg_rating']}/5")
    if stats['negative_count'] > 0:
        lines.append(f"  • Feedback negativo: {stats['negative_count']}")
    if stats['unread_count'] > 0:
        lines.append(f"  • Pendientes sin leer: {stats['unread_count']}")
    lines.append(f"  • Escaneos QR: {stats['visits']}")

    lines.append(f"\nGestioná tu feedback: {feedback_url}")
    lines.append(f"Ver analytics: {analytics_url}")
    lines.append(f"\n— Mirubro")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Send digest for a single business
# ---------------------------------------------------------------------------

def send_digest_for_business(business) -> bool:
    """
    Compute and send the weekly digest for *business*.

    Returns True if the email was sent, False if skipped or failed.
    """
    # Guard: entitlement check (Pro or trial).
    if not smart_filter_allowed(business):
        return False

    # Guard: already sent this week.
    if _already_sent(business.id):
        logger.debug("[ReviewDigest] Already sent this week for business=%s", business.id)
        return False

    # Guard: owner email exists.
    owner_email = _get_owner_email(business)
    if not owner_email:
        logger.warning("[ReviewDigest] No owner email for business=%s", business.id)
        return False

    # Compute stats.
    stats = compute_digest_stats(business)
    if stats is None:
        logger.debug("[ReviewDigest] Nothing to report for business=%s", business.id)
        return False

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    feedback_url = f"{frontend_url}/app/resenas/feedback"
    analytics_url = f"{frontend_url}/app/resenas/analytics"

    subject = f"Resumen semanal — {business.name}"
    body = _build_digest_body(business.name, stats, feedback_url, analytics_url)

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[owner_email],
            fail_silently=False,
        )
        _mark_digest_sent(business.id)
        logger.info(
            "[ReviewDigest] Sent digest to %s for business=%s (reviews=%d, visits=%d)",
            owner_email, business.id, stats['new_reviews'], stats['visits'],
        )
        return True
    except Exception:
        logger.exception("[ReviewDigest] Failed to send digest for business=%s", business.id)
        return False


# ---------------------------------------------------------------------------
# Batch runner — called by the Celery task
# ---------------------------------------------------------------------------

def run_weekly_digest() -> dict:
    """
    Iterate all businesses with an active qr_reviews subscription and
    send the digest where appropriate.

    Returns a summary dict: ``{'sent': int, 'skipped': int, 'failed': int}``.
    """
    sent = skipped = failed = 0

    # Businesses with an active reviews-related subscription.
    active_biz_ids = (
        Subscription.objects
        .filter(
            service='qr_reviews',
            status='active',
        )
        .values_list('business_id', flat=True)
    )

    businesses = Business.objects.filter(id__in=active_biz_ids).iterator()

    for business in businesses:
        try:
            result = send_digest_for_business(business)
            if result:
                sent += 1
            else:
                skipped += 1
        except Exception:
            logger.exception(
                "[ReviewDigest] Unexpected error for business=%s", business.id
            )
            failed += 1

    return {'sent': sent, 'skipped': skipped, 'failed': failed}
