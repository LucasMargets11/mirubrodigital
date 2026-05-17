"""
apps/reviews/tests/test_pr_admin_06_negative_feedback_email.py

ROLLBACK — PR-ADMIN-06 emails REMOVED per product policy.
QR de Reseñas does NOT send emails.

Tests updated to verify the new contract:
  01. notify_negative_feedback() rating ≤ 3 → creates in-app AdminNotification (no email).
  02. notify_negative_feedback() rating > 3 → no notification.
  03. No queue_admin_transactional_email call.
  04. No send_mail call.
  05. No EmailMessage call.
  06. Exception in create_admin_notification does not propagate.
  07. Signal fires for smart-filter business → in-app notification created.
  08. Signal does not fire for base plan business.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription as BizSubscription
from apps.reviews.models import Review, ReviewConfig
from apps.reviews.notifications import notify_negative_feedback
from apps.reviews.signals import on_review_created

User = get_user_model()

_CREATE_NOTIF = 'apps.accounts.admin_notification_service.create_admin_notification'
_ADMIN_HELPER = 'apps.notifications.admin_helpers.queue_admin_transactional_email'


def _disconnect_signal():
    from django.db.models.signals import post_save
    post_save.disconnect(on_review_created, sender=Review)


def _reconnect_signal():
    from django.db.models.signals import post_save
    post_save.connect(on_review_created, sender=Review)


def _make_business(name=None, slug=None):
    name = name or f"Biz-{uuid.uuid4().hex[:6]}"
    slug = slug or f"biz-{uuid.uuid4().hex[:6]}"
    biz = Business.objects.create(name=name, slug=slug, default_service="qr_reviews")
    BizSubscription.objects.create(business=biz, plan="qr_reviews_pro", service="qr_reviews", status="active")
    return biz


def _make_config(business):
    return ReviewConfig.objects.create(
        business=business,
        enabled=True,
        google_place_id="ChIJtest",
        redirect_threshold=4,
        thank_you_message="¡Gracias!",
        mode="smart_filter",
    )


def _make_review(business, rating=2, comment="No me gustó", **kwargs):
    return Review.objects.create(
        business=business, rating=rating, comment=comment,
        source="qr", ip_hash="abc123", **kwargs,
    )


class NegativeFeedbackNoEmailTest(TestCase):
    """notify_negative_feedback() must not send any email."""

    def setUp(self):
        cache.clear()
        _disconnect_signal()
        self.biz = _make_business("Café del Centro", "cafe-centro-06")
        _make_config(self.biz)

    def tearDown(self):
        _reconnect_signal()
        cache.clear()

    # 01 — rating ≤ 3 → in-app notification created
    def test_01_negative_review_creates_in_app_notification(self):
        review = _make_review(self.biz, rating=2)
        with patch(_CREATE_NOTIF) as mock_notif:
            notify_negative_feedback(review)
        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs['notif_type'], 'review_negative')

    # 02 — rating > 3 → no notification
    def test_02_positive_review_no_notification(self):
        review = _make_review(self.biz, rating=4)
        with patch(_CREATE_NOTIF) as mock_notif:
            notify_negative_feedback(review)
        mock_notif.assert_not_called()

    # 03 — no queue_admin_transactional_email
    def test_03_no_queue_admin_transactional_email(self):
        review = _make_review(self.biz, rating=1)
        with patch(_ADMIN_HELPER) as mock_admin_email, \
             patch(_CREATE_NOTIF):
            notify_negative_feedback(review)
        mock_admin_email.assert_not_called()

    # 04 — no send_mail
    def test_04_no_send_mail(self):
        review = _make_review(self.biz, rating=1)
        with patch('django.core.mail.send_mail') as mock_sm, \
             patch(_CREATE_NOTIF):
            notify_negative_feedback(review)
        mock_sm.assert_not_called()

    # 05 — no EmailMessage
    def test_05_no_email_message(self):
        review = _make_review(self.biz, rating=1)
        with patch('django.core.mail.EmailMessage') as mock_em, \
             patch(_CREATE_NOTIF):
            notify_negative_feedback(review)
        mock_em.assert_not_called()

    # 06 — exception in create_admin_notification does not propagate
    def test_06_exception_does_not_propagate(self):
        review = _make_review(self.biz, rating=1)
        with patch(_CREATE_NOTIF, side_effect=RuntimeError('DB error')):
            notify_negative_feedback(review)  # must not raise

    # 07 — signal fires for smart-filter business → in-app notification
    def test_07_signal_creates_in_app_notification(self):
        with patch(_CREATE_NOTIF) as mock_notif:
            _reconnect_signal()
            try:
                Review.objects.create(
                    business=self.biz, rating=1, comment='Signal test',
                    source='qr', ip_hash='sig-06',
                )
            finally:
                _disconnect_signal()
        mock_notif.assert_called_once()

    # 08 — base plan: signal fires but guard in signal skips
    def test_08_signal_skips_base_plan(self):
        base_biz = Business.objects.create(name="Base 06", slug="base-06", default_service="qr_reviews")
        BizSubscription.objects.create(business=base_biz, plan="qr_reviews_base", service="qr_reviews", status="active")
        with patch(_CREATE_NOTIF) as mock_notif:
            _reconnect_signal()
            try:
                Review.objects.create(
                    business=base_biz, rating=1, comment='Base test',
                    source='qr', ip_hash='base-06',
                )
            finally:
                _disconnect_signal()
        mock_notif.assert_not_called()


