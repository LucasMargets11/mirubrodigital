"""
Bloque 18 — Tests for weekly digest system.

ROLLBACK: QR de Reseñas does NOT send emails.
Covers:
  - compute_digest_stats() still works correctly (preserved)
  - Cache guard helpers still work (preserved)
  - send_digest_for_business() is a no-op → returns False, no emails
  - run_weekly_digest() is a no-op → returns {'sent': 0, 'skipped': 0, 'failed': 0}
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

from ..digest import (
    _already_sent,
    _digest_cache_key,
    _mark_digest_sent,
    compute_digest_stats,
    run_weekly_digest,
    send_digest_for_business,
)
from ..models import Review, ReviewConfig, ReviewVisit

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _biz(name='Digest Biz', slug=None, plan='qr_reviews_pro'):
    slug = slug or f'digest-{Business.objects.count()}'
    biz = Business.objects.create(name=name, slug=slug, default_service='qr_reviews')
    Subscription.objects.create(business=biz, plan=plan, service='qr_reviews', status='active')
    ReviewConfig.objects.create(business=biz, redirect_threshold=4)
    return biz


def _owner(business, email='owner@example.com'):
    user = User.objects.create_user(
        username=f'u-{business.slug}',
        email=email,
        password='pass1234',
    )
    Membership.objects.create(user=user, business=business, role='owner')
    return user


def _review(business, rating=4, **kwargs):
    return Review.objects.create(business=business, rating=rating, **kwargs)


def _visit(business):
    return ReviewVisit.objects.create(business=business)


# ---------------------------------------------------------------------------
# Unit tests — compute_digest_stats (function preserved)
# ---------------------------------------------------------------------------

class ComputeDigestStatsTests(TestCase):
    """Tests for compute_digest_stats() — lightweight 7-day aggregation."""

    def setUp(self):
        cache.clear()
        self.biz = _biz(slug='stats-digest')

    def test_returns_none_when_nothing_happened(self):
        result = compute_digest_stats(self.biz)
        self.assertIsNone(result)

    def test_returns_none_with_only_old_reviews(self):
        r = _review(self.biz, rating=5)
        Review.objects.filter(pk=r.pk).update(created_at=timezone.now() - timedelta(days=10))
        result = compute_digest_stats(self.biz)
        self.assertIsNone(result)

    def test_counts_new_reviews(self):
        _review(self.biz, rating=5)
        _review(self.biz, rating=3)
        result = compute_digest_stats(self.biz)
        self.assertEqual(result['new_reviews'], 2)

    def test_counts_negative_reviews(self):
        _review(self.biz, rating=5)     # positive (≥4)
        _review(self.biz, rating=2)     # negative (<4)
        _review(self.biz, rating=1)     # negative
        result = compute_digest_stats(self.biz)
        self.assertEqual(result['negative_count'], 2)

    def test_average_rating(self):
        _review(self.biz, rating=4)
        _review(self.biz, rating=2)
        result = compute_digest_stats(self.biz)
        self.assertAlmostEqual(result['avg_rating'], 3.0, places=1)

    def test_visits_counted(self):
        _visit(self.biz)
        _visit(self.biz)
        result = compute_digest_stats(self.biz)
        self.assertIsNotNone(result)
        self.assertEqual(result['visits'], 2)
        self.assertEqual(result['new_reviews'], 0)

    def test_unread_count_is_all_time(self):
        """Unread count includes reviews older than 7 days."""
        old = _review(self.biz, rating=3, status='new')
        Review.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))
        _review(self.biz, rating=5, status='new')  # recent
        result = compute_digest_stats(self.biz)
        self.assertEqual(result['unread_count'], 2)

    def test_only_visits_produces_digest(self):
        """Visits alone (no reviews) should still produce a digest."""
        _visit(self.biz)
        result = compute_digest_stats(self.biz)
        self.assertIsNotNone(result)
        self.assertEqual(result['new_reviews'], 0)
        self.assertIsNone(result['avg_rating'])
        self.assertEqual(result['visits'], 1)


# ---------------------------------------------------------------------------
# Unit tests — cache guard (helpers preserved)
# ---------------------------------------------------------------------------

class DigestCacheGuardTests(TestCase):

    def setUp(self):
        cache.clear()

    def test_not_sent_by_default(self):
        self.assertFalse(_already_sent(1))

    def test_mark_sent_blocks_duplicate(self):
        _mark_digest_sent(1)
        self.assertTrue(_already_sent(1))

    def test_different_business_not_blocked(self):
        _mark_digest_sent(1)
        self.assertFalse(_already_sent(2))


# ---------------------------------------------------------------------------
# Unit tests — send_digest_for_business (no-op)
# ---------------------------------------------------------------------------

class SendDigestNoOpTests(TestCase):
    """send_digest_for_business() is a no-op — always False, no emails sent."""

    def setUp(self):
        cache.clear()
        self.biz = _biz(slug='send-digest')
        self.owner = _owner(self.biz, email='digest@test.com')
        _review(self.biz, rating=3)
        _visit(self.biz)

    def test_returns_false_always(self):
        result = send_digest_for_business(self.biz)
        self.assertFalse(result)

    def test_returns_false_with_no_data(self):
        empty_biz = _biz(slug='empty-digest')
        _owner(empty_biz)
        result = send_digest_for_business(empty_biz)
        self.assertFalse(result)

    def test_no_queue_transactional_email_call(self):
        with patch('apps.notifications.services.queue_transactional_email') as mock_q:
            send_digest_for_business(self.biz)
        mock_q.assert_not_called()

    def test_no_send_mail(self):
        with patch('django.core.mail.send_mail') as mock_sm:
            send_digest_for_business(self.biz)
        mock_sm.assert_not_called()

    def test_no_email_message(self):
        with patch('django.core.mail.EmailMessage') as mock_em:
            send_digest_for_business(self.biz)
        mock_em.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests — run_weekly_digest (no-op)
# ---------------------------------------------------------------------------

class RunWeeklyDigestNoOpTests(TestCase):
    """run_weekly_digest() is a no-op — returns zeroed dict."""

    def setUp(self):
        cache.clear()

    def test_returns_zeroed_dict(self):
        result = run_weekly_digest()
        self.assertEqual(result, {'sent': 0, 'skipped': 0, 'failed': 0})

    def test_no_queue_calls(self):
        _biz(slug='rwd-pro', plan='qr_reviews_pro')
        with patch('apps.notifications.services.queue_transactional_email') as mock_q:
            run_weekly_digest()
        mock_q.assert_not_called()

    def test_always_returns_zero_sent(self):
        # Create many businesses with reviews — should still be 0
        for i in range(3):
            biz = _biz(slug=f'rwd-many-{i}')
            _owner(biz)
            _review(biz, rating=3)
        result = run_weekly_digest()
        self.assertEqual(result['sent'], 0)
