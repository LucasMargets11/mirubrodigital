"""
Bloque 16 — Tests for negative-feedback notification system.

Covers:
  - Signal fires on Review creation, not on update
  - Email sent for Pro business with smart-filter access
  - Email sent for trial-active business
  - Email NOT sent for Base plan (no smart-filter)
  - Anti-spam: throttle blocks second email within window
  - Anti-spam: allows email after cache expires
  - Owner email resolution: active owner, no owner, no email
  - Email content: subject, stars, body fields
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

from ..models import Review, ReviewConfig
from ..notifications import (
    _CACHE_PREFIX,
    _THROTTLE_SECONDS,
    _get_owner_email,
    _is_throttled,
    _mark_sent,
    notify_negative_feedback,
)
from ..signals import on_review_created

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _disconnect_signal():
    """Disconnect the post_save signal so unit tests can call notify_negative_feedback directly."""
    from django.db.models.signals import post_save
    post_save.disconnect(on_review_created, sender=Review)


def _reconnect_signal():
    from django.db.models.signals import post_save
    post_save.connect(on_review_created, sender=Review)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    return ReviewConfig.objects.create(business=business, **defaults)


def _owner(business, email='owner@example.com'):
    user = User.objects.create_user(username=f'owner_{business.slug}', email=email, password='pass')
    Membership.objects.create(user=user, business=business, role='owner', status='active')
    return user


def _review(business, rating=2, comment='Malo', **kwargs):
    return Review.objects.create(
        business=business, rating=rating, comment=comment,
        source='qr', ip_hash='abc123', **kwargs,
    )


# ---------------------------------------------------------------------------
# Unit tests: notifications.py functions
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NotifyNegativeFeedbackTests(TestCase):
    """Direct tests for notify_negative_feedback()."""

    def setUp(self):
        cache.clear()
        _disconnect_signal()

    def tearDown(self):
        _reconnect_signal()
        cache.clear()

    def test_email_sent_pro_owner(self):
        biz = _biz_pro()
        _cfg(biz)
        _owner(biz, email='pro@example.com')
        review = _review(biz, rating=2, comment='Frío')

        result = notify_negative_feedback(review)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('2★', mail.outbox[0].subject)
        self.assertIn('pro@example.com', mail.outbox[0].to)

    def test_email_body_contains_business_and_comment(self):
        biz = _biz_pro(name='Mi Café', slug='mi-cafe')
        _cfg(biz)
        _owner(biz, email='cafe@example.com')
        review = _review(biz, rating=1, comment='Horrible servicio')

        notify_negative_feedback(review)

        body = mail.outbox[0].body
        self.assertIn('Mi Café', body)
        self.assertIn('Horrible servicio', body)
        self.assertIn('★☆☆☆☆', body)
        self.assertIn('/app/resenas/feedback', body)

    def test_email_body_no_comment(self):
        biz = _biz_pro(name='No Comment Biz', slug='no-comment')
        _cfg(biz)
        _owner(biz, email='nc@example.com')
        review = _review(biz, rating=3, comment='')

        notify_negative_feedback(review)

        body = mail.outbox[0].body
        self.assertNotIn('Comentario:', body)

    def test_email_body_with_contact(self):
        biz = _biz_pro(name='Contact Biz', slug='contact-biz')
        _cfg(biz)
        _owner(biz, email='ct@example.com')
        review = _review(biz, rating=2, comment='Malo', contact_info='juan@gmail.com')

        notify_negative_feedback(review)

        body = mail.outbox[0].body
        self.assertIn('juan@gmail.com', body)

    def test_no_owner_returns_false(self):
        biz = _biz_pro(slug='no-owner')
        _cfg(biz)
        review = _review(biz)

        result = notify_negative_feedback(review)

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_owner_no_email_returns_false(self):
        biz = _biz_pro(slug='no-email')
        _cfg(biz)
        _owner(biz, email='')

        review = _review(biz)
        result = notify_negative_feedback(review)

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_owner_skipped(self):
        biz = _biz_pro(slug='inactive-owner')
        _cfg(biz)
        user = User.objects.create_user(username='inactive_o', email='ina@example.com', password='pass')
        Membership.objects.create(user=user, business=biz, role='owner', status='inactive')

        review = _review(biz)
        result = notify_negative_feedback(review)

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_throttle_blocks_second_email(self):
        biz = _biz_pro(slug='throttle-biz')
        _cfg(biz)
        _owner(biz, email='throt@example.com')

        review1 = _review(biz, rating=1, comment='Bad 1')
        result1 = notify_negative_feedback(review1)
        self.assertTrue(result1)
        self.assertEqual(len(mail.outbox), 1)

        review2 = _review(biz, rating=2, comment='Bad 2')
        result2 = notify_negative_feedback(review2)
        self.assertFalse(result2)
        self.assertEqual(len(mail.outbox), 1)  # Still 1

    def test_throttle_allows_after_clear(self):
        biz = _biz_pro(slug='throttle-clear')
        _cfg(biz)
        _owner(biz, email='clear@example.com')

        review1 = _review(biz, rating=1)
        notify_negative_feedback(review1)
        self.assertEqual(len(mail.outbox), 1)

        # Simulate cache expiry
        cache.delete(f'{_CACHE_PREFIX}{biz.id}')

        review2 = _review(biz, rating=2)
        result2 = notify_negative_feedback(review2)
        self.assertTrue(result2)
        self.assertEqual(len(mail.outbox), 2)

    def test_send_mail_failure_returns_false(self):
        biz = _biz_pro(slug='fail-mail')
        _cfg(biz)
        _owner(biz, email='fail@example.com')
        review = _review(biz)

        with patch('apps.reviews.notifications.send_mail', side_effect=Exception('SMTP down')):
            result = notify_negative_feedback(review)

        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Unit tests: throttle helpers
# ---------------------------------------------------------------------------

class ThrottleHelperTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_initially_not_throttled(self):
        self.assertFalse(_is_throttled(999))

    def test_mark_sent_makes_throttled(self):
        _mark_sent(999)
        self.assertTrue(_is_throttled(999))

    def test_different_business_not_throttled(self):
        _mark_sent(111)
        self.assertFalse(_is_throttled(222))


# ---------------------------------------------------------------------------
# Unit tests: owner email resolution
# ---------------------------------------------------------------------------

class OwnerEmailTests(TestCase):
    def test_active_owner_found(self):
        biz = _biz(slug='oe-active')
        _owner(biz, email='active@example.com')
        self.assertEqual(_get_owner_email(biz), 'active@example.com')

    def test_no_membership(self):
        biz = _biz(slug='oe-none')
        self.assertIsNone(_get_owner_email(biz))

    def test_inactive_owner_not_returned(self):
        biz = _biz(slug='oe-inactive')
        user = User.objects.create_user(username='oe_ina', email='ina@example.com', password='pass')
        Membership.objects.create(user=user, business=biz, role='owner', status='inactive')
        self.assertIsNone(_get_owner_email(biz))


# ---------------------------------------------------------------------------
# Integration tests: signal fires on Review creation
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SignalIntegrationTests(TestCase):
    """Verify the post_save signal triggers notification end-to-end."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_signal_fires_on_create_pro(self):
        """Creating a Review for a Pro business sends an email."""
        biz = _biz_pro(slug='sig-pro')
        _cfg(biz)
        _owner(biz, email='sigpro@example.com')

        Review.objects.create(
            business=biz, rating=2, comment='Signal test',
            source='qr', ip_hash='sig1',
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Signal test', mail.outbox[0].body)

    def test_signal_does_not_fire_on_update(self):
        """Updating an existing Review does NOT send email."""
        biz = _biz_pro(slug='sig-update')
        _cfg(biz)
        _owner(biz, email='sigup@example.com')

        review = Review.objects.create(
            business=biz, rating=2, comment='Initial',
            source='qr', ip_hash='sig2',
        )
        mail.outbox.clear()  # Reset after creation email

        review.status = 'read'
        review.save()

        self.assertEqual(len(mail.outbox), 0)

    def test_signal_skipped_for_base_plan(self):
        """Base plan (no smart_filter_allowed) should NOT trigger email."""
        biz = _biz(slug='sig-base', plan='qr_reviews')
        _cfg(biz, mode='direct')
        _owner(biz, email='sigbase@example.com')

        Review.objects.create(
            business=biz, rating=1, comment='Base test',
            source='qr', ip_hash='sig3',
        )

        self.assertEqual(len(mail.outbox), 0)

    def test_signal_fires_for_trial_active(self):
        """Trial-active business should receive notification email."""
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

        self.assertEqual(len(mail.outbox), 1)

    def test_signal_skipped_for_expired_trial(self):
        """Expired trial should NOT trigger email."""
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

        self.assertEqual(len(mail.outbox), 0)

    def test_multiple_reviews_throttled(self):
        """Multiple rapid reviews only produce 1 email."""
        biz = _biz_pro(slug='sig-thr')
        _cfg(biz)
        _owner(biz, email='sigthr@example.com')

        for i in range(5):
            Review.objects.create(
                business=biz, rating=1, comment=f'Rapid {i}',
                source='qr', ip_hash=f'thr{i}',
            )

        self.assertEqual(len(mail.outbox), 1)
