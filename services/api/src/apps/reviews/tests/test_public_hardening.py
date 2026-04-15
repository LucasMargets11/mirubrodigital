"""
Tests for public reviews hardening (Phase 1-2).

Covers:
  - Business status gating on landing + submit
  - ReviewVisit dedup by IP hash
  - Bot detection for visits
  - custom_redirect_url validation (https required)
"""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.business.models import Business, Subscription
from apps.reviews.models import Review, ReviewConfig, ReviewVisit


def _make_biz(name='Rev Biz', slug='rev-biz', biz_status='active',
              plan='qr_reviews', service='qr_reviews'):
    biz = Business.objects.create(
        name=name, slug=slug, status=biz_status, default_service=service,
    )
    Subscription.objects.create(business=biz, plan=plan, service=service, status='active')
    return biz


def _make_config(business, **kwargs):
    defaults = dict(
        enabled=True,
        google_place_id='ChIJtest',
        redirect_threshold=4,
        thank_you_message='¡Gracias!',
        mode='direct',
    )
    defaults.update(kwargs)
    return ReviewConfig.objects.create(business=business, **defaults)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Business status gating — Landing
# ═══════════════════════════════════════════════════════════════════════════

class ReviewLandingStatusGatingTests(APITestCase):

    def setUp(self):
        cache.clear()

    def _url(self, slug):
        return f'/api/v1/reviews/public/{slug}/'

    def test_active_returns_200(self):
        biz = _make_biz(slug='rev-active', biz_status='active')
        _make_config(biz)
        resp = self.client.get(self._url('rev-active'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_trialing_returns_200(self):
        biz = _make_biz(slug='rev-trial', biz_status='trialing')
        _make_config(biz)
        resp = self.client.get(self._url('rev-trial'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_past_due_returns_200(self):
        biz = _make_biz(slug='rev-past', biz_status='past_due')
        _make_config(biz)
        resp = self.client.get(self._url('rev-past'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_suspended_returns_404(self):
        biz = _make_biz(slug='rev-susp', biz_status='suspended')
        _make_config(biz)
        resp = self.client.get(self._url('rev-susp'))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_canceled_returns_404(self):
        biz = _make_biz(slug='rev-cancel', biz_status='canceled')
        _make_config(biz)
        resp = self.client.get(self._url('rev-cancel'))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_onboarding_returns_404(self):
        biz = _make_biz(slug='rev-onboard', biz_status='onboarding')
        _make_config(biz)
        resp = self.client.get(self._url('rev-onboard'))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Business status gating — Submit
# ═══════════════════════════════════════════════════════════════════════════

class ReviewSubmitStatusGatingTests(APITestCase):

    def setUp(self):
        cache.clear()

    def _url(self, slug):
        return f'/api/v1/reviews/public/{slug}/submit/'

    def test_active_business_can_submit(self):
        biz = _make_biz(slug='sub-active', biz_status='active')
        _make_config(biz)
        resp = self.client.post(self._url('sub-active'), {'rating': 5}, format='json')
        # direct mode with rating → redirect action
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

    def test_suspended_business_submit_returns_404(self):
        biz = _make_biz(slug='sub-susp', biz_status='suspended')
        _make_config(biz)
        resp = self.client.post(self._url('sub-susp'), {'rating': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_canceled_business_submit_returns_404(self):
        biz = _make_biz(slug='sub-cancel', biz_status='canceled')
        _make_config(biz)
        resp = self.client.post(self._url('sub-cancel'), {'rating': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ═══════════════════════════════════════════════════════════════════════════
# 3. ReviewVisit dedup and bot detection
# ═══════════════════════════════════════════════════════════════════════════

class ReviewVisitDedupTests(APITestCase):

    def setUp(self):
        cache.clear()
        self.biz = _make_biz(slug='visit-dedup')
        _make_config(self.biz)

    def _url(self):
        return '/api/v1/reviews/public/visit-dedup/'

    def test_first_visit_creates_record(self):
        self.client.get(self._url())
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 1)

    def test_second_visit_same_ip_within_window_does_not_duplicate(self):
        self.client.get(self._url())
        self.client.get(self._url())
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 1)

    def test_visit_after_window_creates_new_record(self):
        self.client.get(self._url())
        # Manually age the existing visit
        ReviewVisit.objects.filter(business=self.biz).update(
            created_at=timezone.now() - timedelta(minutes=10),
        )
        self.client.get(self._url())
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 2)

    def test_bot_user_agent_does_not_create_visit(self):
        self.client.get(self._url(), HTTP_USER_AGENT='WhatsApp/2.21.3 A')
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 0)

    def test_googlebot_does_not_create_visit(self):
        self.client.get(
            self._url(),
            HTTP_USER_AGENT='Mozilla/5.0 (compatible; Googlebot/2.1)',
        )
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 0)

    def test_normal_browser_creates_visit(self):
        self.client.get(
            self._url(),
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
        )
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 4. custom_redirect_url validation
# ═══════════════════════════════════════════════════════════════════════════

class CustomRedirectUrlValidationTests(TestCase):

    def test_https_url_accepted(self):
        from apps.reviews.serializers import ReviewConfigSerializer
        biz = _make_biz(slug='redir-ok')
        config = _make_config(biz)
        serializer = ReviewConfigSerializer(
            instance=config,
            data={'custom_redirect_url': 'https://example.com/review'},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_http_url_rejected(self):
        from apps.reviews.serializers import ReviewConfigSerializer
        biz = _make_biz(slug='redir-http')
        config = _make_config(biz)
        serializer = ReviewConfigSerializer(
            instance=config,
            data={'custom_redirect_url': 'http://evil.com'},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('custom_redirect_url', serializer.errors)

    def test_empty_url_accepted(self):
        from apps.reviews.serializers import ReviewConfigSerializer
        biz = _make_biz(slug='redir-empty')
        config = _make_config(biz)
        serializer = ReviewConfigSerializer(
            instance=config,
            data={'custom_redirect_url': ''},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
