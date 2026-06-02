"""
Bloque 16 — Tests for negative-feedback notification system.

ROLLBACK: QR de Reseñas does NOT send emails.
Covers:
  - notify_negative_feedback() calls create_admin_notification for rating ≤ 3
  - notify_negative_feedback() does nothing for rating > 3
  - No emails sent under any circumstance
  - Exception in create_admin_notification does not propagate
  - Signal fires on Review creation, not on update
  - Signal triggers for Pro/smart-filter business
  - Signal skipped for Base plan
  - Signal triggers for trial-active business
  - Signal skipped for expired trial
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

from ..models import Review, ReviewConfig
from ..notifications import notify_negative_feedback
from ..signals import on_review_created

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _disconnect_signal():
    from django.db.models.signals import post_save
    post_save.disconnect(on_review_created, sender=Review)


def _reconnect_signal():
    from django.db.models.signals import post_save
    post_save.connect(on_review_created, sender=Review)


def _biz(name='Notif Biz', slug='notif-biz', plan='qr_reviews', service='qr_reviews'):
    biz = Business.objects.create(name=name, slug=slug, default_service=service)
    Subscription.objects.create(business=biz, plan=plan, service=service, status='active')
    return biz


def _biz_pro(name='Pro Notif', slug='pro-notif'):
    return _biz(name=name, slug=slug, plan='qr_reviews_pro')


def _cfg(business, **kwargs):
    defaults = dict(
        enabled=True,
        google_place_id='ChIJtest',
        redirect_threshold=4,
        thank_you_message='¡Gracias!',
        mode='smart_filter',
    )
    defaults.update(kwargs)
    return ReviewConfig.objects.get_or_create(business=business, defaults=defaults)[0]


def _owner(business, email='owner@example.com'):
    user = User.objects.create_user(username=f'owner_{business.slug}', email=email, password='pass')
    Membership.objects.create(user=user, business=business, role='owner', status='active')
    return user


def _review(business, rating=2, comment='Malo', **kwargs):
    return Review.objects.create(
        business=business, rating=rating, comment=comment,
        source='qr', ip_hash='abc123', **kwargs,
    )


_CREATE_NOTIF = 'apps.accounts.admin_notification_service.create_admin_notification'
_ADMIN_EMAIL = 'apps.notifications.admin_helpers.queue_admin_transactional_email'


# ---------------------------------------------------------------------------
# Unit tests: notify_negative_feedback()
# ---------------------------------------------------------------------------

class NotifyNegativeFeedbackTests(TestCase):
    """Direct tests for notify_negative_feedback() — in-app only, no email."""

    def setUp(self):
        cache.clear()
        _disconnect_signal()
        self.biz = _biz_pro(slug='unit-notif')
        _cfg(self.biz)

    def tearDown(self):
        _reconnect_signal()
        cache.clear()

    def test_rating_le_3_calls_create_admin_notification(self):
        review = _review(self.biz, rating=2)
        with patch(_CREATE_NOTIF) as mock_notif:
            notify_negative_feedback(review)
        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs['notif_type'], 'review_negative')

    def test_rating_gt_3_skips_notification(self):
        review = _review(self.biz, rating=4)
        with patch(_CREATE_NOTIF) as mock_notif:
            notify_negative_feedback(review)
        mock_notif.assert_not_called()

    def test_rating_eq_3_calls_create_admin_notification(self):
        review = _review(self.biz, rating=3)
        with patch(_CREATE_NOTIF) as mock_notif:
            notify_negative_feedback(review)
        mock_notif.assert_called_once()

    def test_returns_none(self):
        review = _review(self.biz, rating=1)
        with patch(_CREATE_NOTIF):
            result = notify_negative_feedback(review)
        self.assertIsNone(result)

    def test_exception_does_not_propagate(self):
        review = _review(self.biz, rating=1)
        with patch(_CREATE_NOTIF, side_effect=Exception('DB error')):
            notify_negative_feedback(review)  # must not raise

    def test_no_email_sent_for_negative_review(self):
        review = _review(self.biz, rating=1)
        with patch(_ADMIN_EMAIL) as mock_email, patch(_CREATE_NOTIF):
            notify_negative_feedback(review)
        mock_email.assert_not_called()

    def test_no_email_sent_for_positive_review(self):
        review = _review(self.biz, rating=5)
        with patch(_ADMIN_EMAIL) as mock_email, patch(_CREATE_NOTIF):
            notify_negative_feedback(review)
        mock_email.assert_not_called()


# ---------------------------------------------------------------------------
# Integration tests: signal fires on Review creation
# ---------------------------------------------------------------------------

class SignalIntegrationTests(TestCase):
    """Verify the post_save signal triggers create_admin_notification end-to-end."""

    def setUp(self):
        cache.clear()
        patcher = patch(_CREATE_NOTIF, return_value=None)
        self.mock_notif = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        cache.clear()

    def test_signal_fires_on_create_pro(self):
        """Creating a Review for a Pro business calls create_admin_notification."""
        biz = _biz_pro(slug='sig-pro')
        _cfg(biz)
        _owner(biz, email='sigpro@example.com')

        Review.objects.create(
            business=biz, rating=2, comment='Signal test',
            source='qr', ip_hash='sig1',
        )

        self.mock_notif.assert_called_once()

    def test_signal_does_not_fire_on_update(self):
        """Updating an existing Review does NOT call create_admin_notification."""
        biz = _biz_pro(slug='sig-update')
        _cfg(biz)
        _owner(biz, email='sigup@example.com')

        review = Review.objects.create(
            business=biz, rating=2, comment='Initial',
            source='qr', ip_hash='sig2',
        )
        self.mock_notif.reset_mock()

        review.status = 'read'
        review.save()

        self.mock_notif.assert_not_called()

    def test_signal_skipped_when_no_reviews_subscription(self):
        """Business without any qr_reviews subscription → no smart_filter → no notification.

        Smart-filter is now part of the Base tier, so the only "skip" case is a
        business that has no reviews entitlement at all.
        """
        biz = Business.objects.create(
            name='No Sub Biz', slug='sig-nosub', default_service='qr_reviews',
        )
        _cfg(biz, mode='direct')
        _owner(biz, email='signosub@example.com')

        Review.objects.create(
            business=biz, rating=1, comment='No sub test',
            source='qr', ip_hash='sig3',
        )

        self.mock_notif.assert_not_called()

    def test_signal_fires_for_trial_active(self):
        """Trial-active business should trigger create_admin_notification."""
        biz = _biz(slug='sig-trial', plan='qr_reviews')
        _cfg(
            biz,
            mode='smart_filter',
            trial_used=True,
            trial_ends_at=timezone.now() + timedelta(days=3),
        )
        _owner(biz, email='sigtrial@example.com')

        Review.objects.create(
            business=biz, rating=1, comment='Trial test',
            source='qr', ip_hash='sig4',
        )

        self.mock_notif.assert_called_once()

    def test_signal_still_fires_for_expired_trial_on_base_plan(self):
        """Smart-filter is now plan-granted, so an expired trial does NOT block the signal."""
        biz = _biz(slug='sig-exp', plan='qr_reviews')
        _cfg(
            biz,
            mode='smart_filter',
            trial_used=True,
            trial_ends_at=timezone.now() - timedelta(days=1),
        )
        _owner(biz, email='sigexp@example.com')

        Review.objects.create(
            business=biz, rating=1, comment='Expired test',
            source='qr', ip_hash='sig5',
        )

        self.mock_notif.assert_called_once()

    def test_positive_review_no_notification(self):
        """Rating > 3 does not trigger notification even for Pro plan."""
        biz = _biz_pro(slug='sig-pos')
        _cfg(biz)
        _owner(biz, email='pos@example.com')

        Review.objects.create(
            business=biz, rating=5, comment='Excellent',
            source='qr', ip_hash='sig6',
        )

        self.mock_notif.assert_not_called()
