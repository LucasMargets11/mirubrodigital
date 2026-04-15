"""
Bloque 18 — Tests for weekly digest email system.

Covers:
  - Digest stats computation (new_reviews, negative, unread, avg, visits)
  - Empty digest suppression (nothing happened → None)
  - Entitlement gating (Base → skip, Pro → send, trial → send)
  - Owner email resolution (no owner → skip)
  - Cache guard (already sent this week → skip)
  - Email body content (subject, links, stats)
  - Batch runner (run_weekly_digest iterates eligible businesses)
  - Celery task wiring
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
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
# Unit tests — compute_digest_stats
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
# Unit tests — cache guard
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
# Integration tests — send_digest_for_business
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
@patch('apps.reviews.notifications.send_mail')
class SendDigestForBusinessTests(TestCase):
    """Integration tests for the per-business digest sender."""

    def setUp(self):
        cache.clear()
        self.biz = _biz(slug='send-digest')
        self.user = _owner(self.biz, email='digest@test.com')
        _review(self.biz, rating=3)
        _visit(self.biz)
        mail.outbox.clear()  # Clear after setUp-triggered signal emails

    def test_sends_email_for_pro_business(self, _mock_notif):
        result = send_digest_for_business(self.biz)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Resumen semanal', mail.outbox[0].subject)
        self.assertIn(self.biz.name, mail.outbox[0].subject)

    def test_email_body_includes_stats(self, _mock_notif):
        send_digest_for_business(self.biz)
        body = mail.outbox[0].body
        self.assertIn('Nuevas reseñas: 1', body)
        self.assertIn('Escaneos QR: 1', body)
        self.assertIn('feedback', body.lower())
        self.assertIn('analytics', body.lower())

    def test_email_body_includes_negative_count(self, _mock_notif):
        send_digest_for_business(self.biz)
        body = mail.outbox[0].body
        self.assertIn('Feedback negativo: 1', body)

    def test_skips_base_plan(self, _mock_notif):
        base_biz = _biz(slug='base-digest', plan='qr_reviews_base')
        _owner(base_biz, email='base@test.com')
        _review(base_biz, rating=3)
        result = send_digest_for_business(base_biz)
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_for_trial_active(self, _mock_notif):
        trial_biz = _biz(slug='trial-digest', plan='qr_reviews_base')
        _owner(trial_biz, email='trial@test.com')
        config = trial_biz.review_config
        config.trial_ends_at = timezone.now() + timedelta(days=3)
        config.trial_used = True
        config.save()
        _review(trial_biz, rating=2)
        result = send_digest_for_business(trial_biz)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_skips_expired_trial(self, _mock_notif):
        expired_biz = _biz(slug='expired-digest', plan='qr_reviews_base')
        _owner(expired_biz, email='expired@test.com')
        config = expired_biz.review_config
        config.trial_ends_at = timezone.now() - timedelta(days=1)
        config.trial_used = True
        config.save()
        _review(expired_biz, rating=2)
        result = send_digest_for_business(expired_biz)
        self.assertFalse(result)

    def test_skips_if_no_owner_email(self, _mock_notif):
        no_email_biz = _biz(slug='no-email-digest')
        _review(no_email_biz, rating=3)
        result = send_digest_for_business(no_email_biz)
        self.assertFalse(result)

    def test_skips_empty_digest(self, _mock_notif):
        empty_biz = _biz(slug='empty-digest')
        _owner(empty_biz, email='empty@test.com')
        result = send_digest_for_business(empty_biz)
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_cache_guard_prevents_duplicate(self, _mock_notif):
        send_digest_for_business(self.biz)
        self.assertEqual(len(mail.outbox), 1)
        # Second call same week → skipped
        result = send_digest_for_business(self.biz)
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_sent_to_owner(self, _mock_notif):
        send_digest_for_business(self.biz)
        self.assertEqual(mail.outbox[0].to, ['digest@test.com'])


# ---------------------------------------------------------------------------
# Integration tests — run_weekly_digest batch runner
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
@patch('apps.reviews.notifications.send_mail')
class RunWeeklyDigestTests(TestCase):
    """Tests for the batch runner that iterates all eligible businesses."""

    def setUp(self):
        cache.clear()
        mail.outbox.clear()

    def test_sends_to_eligible_skips_ineligible(self, _mock_notif):
        pro = _biz(slug='batch-pro', plan='qr_reviews_pro')
        _owner(pro, email='pro@test.com')
        _review(pro, rating=4)

        base = _biz(slug='batch-base', plan='qr_reviews_base')
        _owner(base, email='base@test.com')
        _review(base, rating=3)

        result = run_weekly_digest()
        self.assertEqual(result['sent'], 1)
        self.assertGreaterEqual(result['skipped'], 1)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['pro@test.com'])

    def test_returns_zero_when_no_businesses(self, _mock_notif):
        result = run_weekly_digest()
        self.assertEqual(result['sent'], 0)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(result['failed'], 0)

    def test_handles_send_mail_failure_gracefully(self, _mock_notif):
        pro = _biz(slug='fail-pro', plan='qr_reviews_pro')
        _owner(pro, email='fail@test.com')
        _review(pro, rating=4)

        with patch('apps.reviews.digest.send_mail', side_effect=Exception('SMTP down')):
            result = run_weekly_digest()
        # Failed in send_digest_for_business → returns False → counted as skipped
        # (exception is caught inside send_digest_for_business)
        self.assertEqual(result['sent'], 0)
        self.assertEqual(result['failed'], 0)  # caught inside, not propagated
        self.assertGreaterEqual(result['skipped'], 1)


# ---------------------------------------------------------------------------
# Celery task wiring
# ---------------------------------------------------------------------------

class CeleryTaskTests(TestCase):
    """Verify the Celery task calls the batch runner."""

    def test_task_calls_run_weekly_digest(self):
        with patch('apps.reviews.digest.run_weekly_digest', return_value={'sent': 0, 'skipped': 0, 'failed': 0}) as mock_run:
            from ..tasks import send_weekly_digest
            send_weekly_digest()
            mock_run.assert_called_once()
