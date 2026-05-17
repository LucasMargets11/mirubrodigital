"""
apps/reviews/tests/test_pr_admin_07_reviews_digest_email.py

ROLLBACK — PR-ADMIN-07 digest emails REMOVED per product policy.
QR de Reseñas does NOT send emails.

Tests updated to verify the new contract:
  01. send_digest_for_business() always returns False (no-op).
  02. No queue_transactional_email call.
  03. No send_mail call.
  04. No EmailMessage call.
  05. run_weekly_digest() returns {'sent': 0, 'skipped': 0, 'failed': 0}.
  06. compute_digest_stats() still works correctly (stats computation preserved).
  07. compute_digest_stats() returns None when nothing happened.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

from ..digest import (
    compute_digest_stats,
    run_weekly_digest,
    send_digest_for_business,
)
from ..models import Review, ReviewConfig, ReviewVisit

User = get_user_model()


def _biz(name='Digest07 Biz', slug=None, plan='qr_reviews_pro'):
    slug = slug or f'pr07-{Business.objects.count()}'
    biz = Business.objects.create(name=name, slug=slug, default_service='qr_reviews')
    Subscription.objects.create(business=biz, plan=plan, service='qr_reviews', status='active')
    ReviewConfig.objects.create(business=biz, redirect_threshold=4)
    return biz


def _owner(business, email='owner07@example.com'):
    user = User.objects.create_user(
        username=f'u07-{business.slug}',
        email=email,
        password='pass1234',
    )
    Membership.objects.create(
        user=user,
        business=business,
        role='owner',
        status=Membership.Status.ACTIVE,
    )
    return user


def _review(business, rating=4, **kwargs):
    return Review.objects.create(business=business, rating=rating, **kwargs)


def _visit(business):
    return ReviewVisit.objects.create(business=business)


class SendDigestNoEmailTests(TestCase):
    """send_digest_for_business() is a no-op — no emails sent."""

    def setUp(self):
        cache.clear()
        self.biz = _biz(slug='pr07-main')
        self.owner = _owner(self.biz)
        _review(self.biz, rating=3)
        _visit(self.biz)

    # 01 — always returns False
    def test_01_returns_false(self):
        result = send_digest_for_business(self.biz)
        self.assertFalse(result)

    # 02 — no queue_transactional_email
    def test_02_no_queue_transactional_email(self):
        from unittest.mock import patch
        with patch('apps.notifications.services.queue_transactional_email') as mock_q:
            send_digest_for_business(self.biz)
        mock_q.assert_not_called()

    # 03 — no send_mail
    def test_03_no_send_mail(self):
        from unittest.mock import patch
        with patch('django.core.mail.send_mail') as mock_sm:
            send_digest_for_business(self.biz)
        mock_sm.assert_not_called()

    # 04 — no EmailMessage
    def test_04_no_email_message(self):
        from unittest.mock import patch
        with patch('django.core.mail.EmailMessage') as mock_em:
            send_digest_for_business(self.biz)
        mock_em.assert_not_called()

    # 05 — run_weekly_digest no-op
    def test_05_run_weekly_digest_noop(self):
        result = run_weekly_digest()
        self.assertEqual(result, {'sent': 0, 'skipped': 0, 'failed': 0})

    # 06 — compute_digest_stats still works
    def test_06_compute_digest_stats_works(self):
        result = compute_digest_stats(self.biz)
        self.assertIsNotNone(result)
        self.assertEqual(result['new_reviews'], 1)
        self.assertEqual(result['visits'], 1)

    # 07 — compute_digest_stats returns None when nothing happened
    def test_07_compute_digest_stats_none_when_empty(self):
        empty_biz = _biz(slug='pr07-empty2')
        result = compute_digest_stats(empty_biz)
        self.assertIsNone(result)
