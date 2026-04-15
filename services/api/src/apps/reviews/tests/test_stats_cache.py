"""
Bloque 17 — Tests for ReviewStatsView caching, invalidation, and new metrics.

Covers:
  - Cache hit / miss behaviour on ReviewStatsView
  - Cache invalidation on Review creation (via signal)
  - Cache invalidation on status update (via ReviewDetailView.patch)
  - daily_trend field: 30-day array with correct counts
  - visits_last_7_days / visits_last_30_days metrics
  - New response fields present in stats payload
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

from ..models import Review, ReviewConfig, ReviewVisit
from ..views import _stats_cache_key, invalidate_review_stats_cache

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_business(name='Stats Biz', slug='stats-biz'):
    biz = Business.objects.create(name=name, default_service='qr_reviews', slug=slug)
    Subscription.objects.create(business=biz, plan='qr_reviews', service='qr_reviews', status='active')
    ReviewConfig.objects.create(business=biz, redirect_threshold=4)
    return biz


def _auth_client(client, business, role='owner'):
    user = User.objects.create_user(username=f'u-{business.slug}', password='pass1234')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


def _review(business, rating=4, **kwargs):
    return Review.objects.create(business=business, rating=rating, **kwargs)


def _visit(business, **kwargs):
    return ReviewVisit.objects.create(business=business, **kwargs)


# ---------------------------------------------------------------------------
# Unit tests — cache utilities
# ---------------------------------------------------------------------------

class CacheUtilityTests(TestCase):
    """Unit tests for cache key generation and invalidation helper."""

    def setUp(self):
        cache.clear()

    def test_cache_key_format(self):
        self.assertEqual(_stats_cache_key(42), 'review_stats:42')

    def test_invalidate_deletes_cached_value(self):
        cache.set(_stats_cache_key(99), {'total': 7}, 300)
        invalidate_review_stats_cache(99)
        self.assertIsNone(cache.get(_stats_cache_key(99)))

    def test_invalidate_noop_when_no_cache(self):
        # Should not raise
        invalidate_review_stats_cache(999)


# ---------------------------------------------------------------------------
# Integration tests — cache behaviour on ReviewStatsView
# ---------------------------------------------------------------------------

class ReviewStatsCacheTests(APITestCase):
    """Integration tests for caching behaviour of GET /api/v1/reviews/stats/."""

    def setUp(self):
        cache.clear()
        self.biz = _create_business()
        self.user = _auth_client(self.client, self.biz)
        # Seed one review so we get a non-empty response
        _review(self.biz, rating=5)

    def _get_stats(self):
        return self.client.get('/api/v1/reviews/stats/')

    def test_first_call_populates_cache(self):
        resp = self._get_stats()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cached = cache.get(_stats_cache_key(self.biz.id))
        self.assertIsNotNone(cached)
        self.assertEqual(cached['total_reviews'], 1)

    def test_second_call_returns_cached_value(self):
        # First call fills cache
        self._get_stats()
        # Create another review — signal would invalidate, so reset cache manually
        Review.objects.create(business=self.biz, rating=3)
        # Re-set cache to verify GET reads from cache, not DB
        cache.set(_stats_cache_key(self.biz.id), {'total_reviews': 1, 'cached': True}, 300)
        resp = self._get_stats()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data.get('cached', False))

    def test_invalidation_on_review_create_via_signal(self):
        """When a new Review is created, the signal should clear the cache."""
        # Fill cache
        self._get_stats()
        self.assertIsNotNone(cache.get(_stats_cache_key(self.biz.id)))
        # Create new review → signal fires → cache cleared
        _review(self.biz, rating=2)
        self.assertIsNone(cache.get(_stats_cache_key(self.biz.id)))

    def test_invalidation_on_status_update(self):
        """PATCH /api/v1/reviews/<id>/ clears the cache."""
        review = _review(self.biz, rating=2, status='new')
        # Fill cache
        self._get_stats()
        self.assertIsNotNone(cache.get(_stats_cache_key(self.biz.id)))
        # Update status (new → read is valid)
        resp = self.client.patch(
            f'/api/v1/reviews/{review.id}/',
            {'status': 'read'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(_stats_cache_key(self.biz.id)))


# ---------------------------------------------------------------------------
# Tests — new response fields
# ---------------------------------------------------------------------------

class ReviewStatsNewFieldsTests(APITestCase):
    """Tests that new fields are present and correct in the stats response."""

    def setUp(self):
        cache.clear()
        self.biz = _create_business(slug='new-fields-biz')
        self.user = _auth_client(self.client, self.biz)

    def _get_stats(self):
        return self.client.get('/api/v1/reviews/stats/')

    def test_response_includes_daily_trend(self):
        _review(self.biz, rating=5)
        resp = self._get_stats()
        self.assertIn('daily_trend', resp.data)
        trend = resp.data['daily_trend']
        self.assertEqual(len(trend), 30)
        for entry in trend:
            self.assertIn('date', entry)
            self.assertIn('count', entry)

    def test_response_includes_visit_window_counts(self):
        _review(self.biz, rating=5)
        resp = self._get_stats()
        self.assertIn('visits_last_7_days', resp.data)
        self.assertIn('visits_last_30_days', resp.data)

    def test_daily_trend_counts_match_reviews(self):
        """Reviews created today should appear in the last day of daily_trend."""
        _review(self.biz, rating=4)
        _review(self.biz, rating=2)
        resp = self._get_stats()
        trend = resp.data['daily_trend']
        today_count = trend[-1]['count']  # last entry = today
        self.assertEqual(today_count, 2)

    def test_daily_trend_zero_fills_missing_days(self):
        """Days with no reviews should have count 0."""
        _review(self.biz, rating=3)
        resp = self._get_stats()
        trend = resp.data['daily_trend']
        # At least 29 of the 30 days should have count 0
        zero_days = [d for d in trend if d['count'] == 0]
        self.assertGreaterEqual(len(zero_days), 29)

    def test_visits_last_7_days(self):
        _review(self.biz, rating=5)  # need at least one review
        now = timezone.now()
        _visit(self.biz)  # today
        # Create one visit 3 days ago
        v = _visit(self.biz)
        ReviewVisit.objects.filter(pk=v.pk).update(created_at=now - timedelta(days=3))
        # Create one visit 10 days ago (outside 7-day window)
        v2 = _visit(self.biz)
        ReviewVisit.objects.filter(pk=v2.pk).update(created_at=now - timedelta(days=10))
        resp = self._get_stats()
        self.assertEqual(resp.data['visits_last_7_days'], 2)
        self.assertEqual(resp.data['visits_last_30_days'], 3)

    def test_total_visits_and_conversion(self):
        _review(self.biz, rating=5)
        _visit(self.biz)
        _visit(self.biz)
        _visit(self.biz)
        resp = self._get_stats()
        self.assertEqual(resp.data['total_visits'], 3)
        # 1 review / 3 visits = 33.3%
        self.assertAlmostEqual(resp.data['conversion_rate'], 33.3, places=1)

    def test_daily_trend_dates_are_iso_format(self):
        _review(self.biz, rating=5)
        resp = self._get_stats()
        trend = resp.data['daily_trend']
        import re
        for entry in trend:
            self.assertRegex(entry['date'], r'^\d{4}-\d{2}-\d{2}$')

    def test_empty_business_returns_zero_visits(self):
        _review(self.biz, rating=5)
        resp = self._get_stats()
        self.assertEqual(resp.data['visits_last_7_days'], 0)
        self.assertEqual(resp.data['visits_last_30_days'], 0)

    def test_daily_trend_ordered_chronologically(self):
        _review(self.biz, rating=5)
        resp = self._get_stats()
        trend = resp.data['daily_trend']
        dates = [entry['date'] for entry in trend]
        self.assertEqual(dates, sorted(dates))
