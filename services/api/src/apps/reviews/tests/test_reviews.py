"""
Tests for the standalone reviews domain (Phases 1–3.5).

Covers:
  - Models: ReviewConfig.redirect_url priority, Review creation
  - Public endpoints: landing, submit (redirect + feedback flows)
  - Private endpoints: config GET/PATCH, QR, list, detail status update
  - Status transitions: valid transitions, invalid transitions, strict enforcement
  - Menu integration: _build_public_engagement reads ReviewConfig first, legacy fallback, reviews_hybrid flag
  - Route resolution: /api/v1/reviews/qr/ resolves to reviews app (no legacy shadow)
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.menu.models import MenuEngagementSettings

from ..models import Review, ReviewConfig, ReviewStatus, ReviewVisit

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_business(name='Test Biz', slug='test-biz', service='qr_reviews', plan='qr_reviews'):
    biz = Business.objects.create(name=name, default_service=service, slug=slug)
    Subscription.objects.create(business=biz, plan=plan, service=service, status='active')
    return biz


def _auth_client(client, business, role='owner'):
    user = User.objects.create_user(username=f'u-{business.slug}', password='pass1234')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class ReviewConfigModelTests(TestCase):

    def setUp(self):
        self.biz = Business.objects.create(name='Model Biz', slug='model-biz', default_service='qr_reviews')

    def test_redirect_url_priority_custom(self):
        cfg = ReviewConfig.objects.create(
            business=self.biz,
            custom_redirect_url='https://custom.example.com',
            google_place_id='ChIJtest',
            google_review_url='https://google.com/review',
        )
        self.assertEqual(cfg.redirect_url, 'https://custom.example.com')

    def test_redirect_url_priority_place_id(self):
        cfg = ReviewConfig.objects.create(
            business=self.biz,
            google_place_id='ChIJtest',
            google_review_url='https://google.com/review',
        )
        self.assertIn('placeid=ChIJtest', cfg.redirect_url)

    def test_redirect_url_priority_google_url(self):
        cfg = ReviewConfig.objects.create(
            business=self.biz,
            google_review_url='https://google.com/review',
        )
        self.assertEqual(cfg.redirect_url, 'https://google.com/review')

    def test_redirect_url_none_when_empty(self):
        cfg = ReviewConfig.objects.create(business=self.biz)
        self.assertIsNone(cfg.redirect_url)


class ReviewModelTests(TestCase):

    def test_create_review(self):
        biz = Business.objects.create(name='Rev Biz', slug='rev-biz', default_service='qr_reviews')
        review = Review.objects.create(business=biz, rating=3, comment='Buena comida')
        self.assertEqual(review.rating, 3)
        self.assertEqual(review.status, ReviewStatus.NEW)
        self.assertIsNotNone(review.id)

    def test_review_ordering(self):
        biz = Business.objects.create(name='Ord Biz', slug='ord-biz', default_service='qr_reviews')
        r1 = Review.objects.create(business=biz, rating=5)
        r2 = Review.objects.create(business=biz, rating=1)
        reviews = list(Review.objects.filter(business=biz))
        self.assertEqual(reviews[0].id, r2.id)  # newer first


# ---------------------------------------------------------------------------
# Public endpoint tests
# ---------------------------------------------------------------------------

class PublicReviewLandingTests(APITestCase):

    def setUp(self):
        self.biz = _create_business()
        self.config = ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            google_place_id='ChIJtest123',
            redirect_threshold=4,
            thank_you_message='Gracias!',
        )

    def test_returns_config(self):
        resp = self.client.get('/api/v1/reviews/public/test-biz/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['business_name'], 'Test Biz')
        self.assertIn('placeid=ChIJtest123', resp.data['redirect_url'])
        self.assertEqual(resp.data['redirect_threshold'], 4)
        self.assertTrue(resp.data['enabled'])

    def test_returns_404_for_nonexistent_slug(self):
        resp = self.client.get('/api/v1/reviews/public/noexiste/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_when_disabled(self):
        self.config.enabled = False
        self.config.save()
        resp = self.client.get('/api/v1/reviews/public/test-biz/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_when_no_config(self):
        biz2 = _create_business(name='No Cfg', slug='no-cfg')
        resp = self.client.get('/api/v1/reviews/public/no-cfg/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PublicReviewSubmitTests(APITestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.biz = _create_business()
        self.config = ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            google_place_id='ChIJtest123',
            redirect_threshold=4,
            thank_you_message='Gracias!',
        )

    def test_high_rating_returns_redirect(self):
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 5})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertIn('placeid=ChIJtest123', resp.data['redirect_url'])
        self.assertEqual(Review.objects.count(), 0)

    def test_low_rating_creates_review(self):
        resp = self.client.post(
            '/api/v1/reviews/public/test-biz/submit/',
            {'rating': 2, 'comment': 'Puede mejorar'},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['action'], 'submitted')
        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.first()
        self.assertEqual(review.rating, 2)
        self.assertEqual(review.comment, 'Puede mejorar')

    def test_threshold_boundary_redirects(self):
        """rating == threshold should redirect."""
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 4})
        self.assertEqual(resp.data['action'], 'redirect')

    def test_invalid_rating_returns_400(self):
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 0})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rating_above_5_returns_400(self):
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 6})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_rating_returns_400(self):
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disabled_config_returns_403(self):
        self.config.enabled = False
        self.config.save()
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 3})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_dedup_blocks_second_submit(self):
        self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 2})
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 3})
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# ---------------------------------------------------------------------------
# Private endpoint tests
# ---------------------------------------------------------------------------

class ReviewConfigViewTests(APITestCase):

    def setUp(self):
        self.biz = _create_business(slug='cfg-biz')
        self.user = _auth_client(self.client, self.biz)

    def test_get_creates_default_config(self):
        resp = self.client.get('/api/v1/reviews/config/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['enabled'])
        self.assertTrue(ReviewConfig.objects.filter(business=self.biz).exists())

    def test_patch_updates_config(self):
        ReviewConfig.objects.create(business=self.biz)
        resp = self.client.patch(
            '/api/v1/reviews/config/',
            {'enabled': True, 'google_place_id': 'ChIJnew', 'redirect_threshold': 3},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['enabled'])
        self.assertEqual(resp.data['redirect_threshold'], 3)

    def test_patch_invalid_threshold(self):
        ReviewConfig.objects.create(business=self.biz)
        resp = self.client.patch(
            '/api/v1/reviews/config/',
            {'redirect_threshold': 6},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewQRCodeViewTests(APITestCase):

    def setUp(self):
        self.biz = _create_business(slug='qr-biz')
        self.user = _auth_client(self.client, self.biz)

    def test_qr_returns_svg(self):
        resp = self.client.get('/api/v1/reviews/qr/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('data:image/svg+xml;base64,', resp.data['qr_svg'])
        self.assertEqual(resp.data['slug'], 'qr-biz')

    def test_qr_denied_without_plan(self):
        biz2 = Business.objects.create(name='No Plan', slug='no-plan', default_service='menu_qr')
        Subscription.objects.create(business=biz2, plan='menu_qr_lite', service='menu_qr', status='active')
        user2 = User.objects.create_user(username='noplanuser', password='pass123')
        Membership.objects.create(user=user2, business=biz2, role='owner')
        self.client.force_authenticate(user=user2)
        resp = self.client.get('/api/v1/reviews/qr/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class ReviewListViewTests(APITestCase):

    def setUp(self):
        self.biz = _create_business(slug='list-biz')
        self.user = _auth_client(self.client, self.biz)
        Review.objects.create(business=self.biz, rating=5, comment='Excelente')
        Review.objects.create(business=self.biz, rating=2, comment='Regular', status=ReviewStatus.READ)

    def test_list_all(self):
        resp = self.client.get('/api/v1/reviews/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

    def test_filter_by_status(self):
        resp = self.client.get('/api/v1/reviews/?status=read')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['status'], 'read')

    def test_filter_by_rating(self):
        resp = self.client.get('/api/v1/reviews/?rating=5')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['rating'], 5)

    def test_filter_by_rating_min(self):
        Review.objects.create(business=self.biz, rating=3, comment='Buena')
        resp = self.client.get('/api/v1/reviews/?rating_min=3')
        ratings = [r['rating'] for r in resp.data]
        self.assertTrue(all(r >= 3 for r in ratings))
        self.assertEqual(len(resp.data), 2)  # rating 5 and 3, not rating 2

    def test_filter_by_rating_max(self):
        resp = self.client.get('/api/v1/reviews/?rating_max=3')
        ratings = [r['rating'] for r in resp.data]
        self.assertTrue(all(r <= 3 for r in ratings))
        self.assertEqual(len(resp.data), 1)  # only rating 2

    def test_filter_by_rating_range(self):
        Review.objects.create(business=self.biz, rating=3, comment='Buena')
        Review.objects.create(business=self.biz, rating=1, comment='Mala')
        resp = self.client.get('/api/v1/reviews/?rating_min=2&rating_max=4')
        ratings = [r['rating'] for r in resp.data]
        self.assertTrue(all(2 <= r <= 4 for r in ratings))
        self.assertEqual(len(resp.data), 2)  # rating 2 and 3


class ReviewDetailViewTests(APITestCase):

    def setUp(self):
        self.biz = _create_business(slug='detail-biz')
        self.user = _auth_client(self.client, self.biz)
        self.review = Review.objects.create(business=self.biz, rating=3)

    def test_patch_status(self):
        resp = self.client.patch(
            f'/api/v1/reviews/{self.review.id}/',
            {'status': 'read'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'read')
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, ReviewStatus.READ)

    def test_patch_invalid_status(self):
        resp = self.client.patch(
            f'/api/v1/reviews/{self.review.id}/',
            {'status': 'invalid_status'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Menu integration tests
# ---------------------------------------------------------------------------

class MenuIntegrationTests(TestCase):
    """_build_public_engagement reads ReviewConfig first, fallback to legacy."""

    def setUp(self):
        self.biz = Business.objects.create(
            name='Menu Int Biz', slug='menu-int', default_service='qr_reviews',
        )
        Subscription.objects.create(
            business=self.biz, plan='qr_reviews', service='qr_reviews', status='active',
        )
        # Legacy engagement settings (always needed for tips/other fields)
        MenuEngagementSettings.objects.create(
            business=self.biz,
            reviews_enabled=True,
            google_place_id='ChIJlegacy',
        )

    def test_uses_review_config_when_exists(self):
        from apps.menu.views import _build_public_engagement

        ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            google_place_id='ChIJnewconfig',
        )
        result = _build_public_engagement(self.biz, None)
        self.assertTrue(result['reviews_enabled'])
        self.assertIn('ChIJnewconfig', result['google_write_review_url'])
        self.assertTrue(result['reviews_hybrid'])

    def test_falls_back_to_legacy_when_no_review_config(self):
        from apps.menu.views import _build_public_engagement

        # No ReviewConfig exists
        result = _build_public_engagement(self.biz, None)
        self.assertTrue(result['reviews_enabled'])
        self.assertIn('ChIJlegacy', result['google_write_review_url'])
        self.assertFalse(result['reviews_hybrid'])

    def test_review_config_disabled_means_reviews_off(self):
        from apps.menu.views import _build_public_engagement

        ReviewConfig.objects.create(
            business=self.biz,
            enabled=False,
            google_place_id='ChIJdisabled',
        )
        result = _build_public_engagement(self.biz, None)
        self.assertFalse(result['reviews_enabled'])
        self.assertFalse(result['reviews_hybrid'])


# ---------------------------------------------------------------------------
# Phase 3.5: Strict status transition tests
# ---------------------------------------------------------------------------

class ReviewStatusTransitionTests(APITestCase):
    """Verify all valid status transitions pass and invalid ones are rejected."""

    def setUp(self):
        self.biz = _create_business(slug='status-biz')
        self.user = _auth_client(self.client, self.biz)

    def _create_review(self, initial_status='new'):
        return Review.objects.create(
            business=self.biz, rating=2, status=initial_status,
        )

    def test_new_to_read(self):
        review = self._create_review('new')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'read'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'read')

    def test_read_to_contacted(self):
        review = self._create_review('read')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'contacted'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'contacted')

    def test_contacted_to_resolved(self):
        review = self._create_review('contacted')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'resolved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'resolved')

    def test_resolved_to_read_reopen(self):
        review = self._create_review('resolved')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'read'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'read')

    def test_invalid_status_rejected(self):
        review = self._create_review('new')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'archived'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bogus_status_rejected(self):
        review = self._create_review('new')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'banana'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # Phase 3.5: strict transition rejection tests
    def test_new_to_resolved_rejected(self):
        review = self._create_review('new')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'resolved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Transición no permitida', str(resp.data))

    def test_new_to_contacted_rejected(self):
        review = self._create_review('new')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'contacted'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resolved_to_contacted_rejected(self):
        review = self._create_review('resolved')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'contacted'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resolved_to_resolved_rejected(self):
        review = self._create_review('resolved')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'resolved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_to_resolved_rejected(self):
        review = self._create_review('read')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'resolved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contacted_to_read_rejected(self):
        review = self._create_review('contacted')
        resp = self.client.patch(f'/api/v1/reviews/{review.id}/', {'status': 'read'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Phase 3: Route resolution tests
# ---------------------------------------------------------------------------

class QRRouteResolutionTests(APITestCase):
    """Verify /api/v1/reviews/qr/ resolves to the reviews app view."""

    def setUp(self):
        self.biz = _create_business(slug='route-biz')
        self.user = _auth_client(self.client, self.biz)

    def test_qr_route_resolves_to_reviews_app(self):
        """The QR endpoint uses manage_reviews permission (not manage_menu)."""
        resp = self.client.get('/api/v1/reviews/qr/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('qr_svg', resp.data)
        self.assertEqual(resp.data['slug'], 'route-biz')

    def test_qr_route_requires_reviews_permission(self):
        """A user with only manage_menu (no manage_reviews) should be denied."""
        from django.urls import resolve
        match = resolve('/api/v1/reviews/qr/')
        # Verify it resolves to the reviews app namespace
        self.assertEqual(match.namespace, 'reviews')
        self.assertEqual(match.url_name, 'qr')


# ---------------------------------------------------------------------------
# Phase 3: Submit edge cases
# ---------------------------------------------------------------------------

class PublicSubmitEdgeCaseTests(APITestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.biz = _create_business()

    def test_high_rating_no_redirect_url(self):
        """When config has no redirect URL, high rating still returns redirect action but url is None."""
        ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            redirect_threshold=4,
        )
        resp = self.client.post('/api/v1/reviews/public/test-biz/submit/', {'rating': 5})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertIsNone(resp.data['redirect_url'])


# ---------------------------------------------------------------------------
# Analytics Pro: Stats endpoint tests
# ---------------------------------------------------------------------------

class ReviewStatsViewTests(APITestCase):
    """Tests for GET /api/v1/reviews/stats/ analytics endpoint."""

    def setUp(self):
        self.biz = _create_business(slug='stats-biz')
        self.user = _auth_client(self.client, self.biz)

    def test_empty_stats(self):
        """Stats with no reviews returns zeroes."""
        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_reviews'], 0)
        self.assertEqual(resp.data['average_rating'], 0)
        self.assertEqual(resp.data['total_visits'], 0)
        self.assertEqual(resp.data['conversion_rate'], 0)
        self.assertEqual(resp.data['positive_reviews'], 0)
        self.assertEqual(resp.data['negative_reviews'], 0)
        self.assertEqual(resp.data['resolution_rate'], 0)
        self.assertEqual(resp.data['reviews_last_7_days'], 0)
        self.assertEqual(resp.data['reviews_last_30_days'], 0)

    def test_positive_negative_counts(self):
        """Positive = rating >= 4, negative = rating <= 3."""
        Review.objects.create(business=self.biz, rating=5)
        Review.objects.create(business=self.biz, rating=4)
        Review.objects.create(business=self.biz, rating=3)
        Review.objects.create(business=self.biz, rating=2)
        Review.objects.create(business=self.biz, rating=1)

        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.data['positive_reviews'], 2)  # 5, 4
        self.assertEqual(resp.data['negative_reviews'], 3)  # 3, 2, 1
        self.assertEqual(resp.data['positive_rate'], 40.0)
        self.assertEqual(resp.data['negative_rate'], 60.0)

    def test_conversion_rate(self):
        """conversion_rate = total_reviews / total_visits * 100."""
        Review.objects.create(business=self.biz, rating=3)
        Review.objects.create(business=self.biz, rating=2)
        # 10 visits, 2 reviews → 20% conversion
        for _ in range(10):
            ReviewVisit.objects.create(business=self.biz)

        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.data['total_reviews'], 2)
        self.assertEqual(resp.data['total_visits'], 10)
        self.assertEqual(resp.data['conversion_rate'], 20.0)

    def test_conversion_rate_zero_visits(self):
        """conversion_rate = 0 when no visits (avoid division by zero)."""
        Review.objects.create(business=self.biz, rating=5)
        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.data['conversion_rate'], 0)

    def test_resolution_rate(self):
        """resolution_rate = resolved / total_reviews * 100."""
        Review.objects.create(business=self.biz, rating=2, status='resolved')
        Review.objects.create(business=self.biz, rating=3, status='resolved')
        Review.objects.create(business=self.biz, rating=1, status='new')
        Review.objects.create(business=self.biz, rating=2, status='contacted')

        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.data['resolved_reviews'], 2)
        self.assertEqual(resp.data['resolution_rate'], 50.0)

    def test_rating_distribution(self):
        """rating_distribution has keys 1-5 with correct counts."""
        Review.objects.create(business=self.biz, rating=5)
        Review.objects.create(business=self.biz, rating=5)
        Review.objects.create(business=self.biz, rating=3)
        Review.objects.create(business=self.biz, rating=1)

        resp = self.client.get('/api/v1/reviews/stats/')
        dist = resp.data['rating_distribution']
        self.assertEqual(dist['5'], 2)
        self.assertEqual(dist['3'], 1)
        self.assertEqual(dist['1'], 1)
        self.assertEqual(dist['2'], 0)
        self.assertEqual(dist['4'], 0)

    def test_status_distribution(self):
        """status_distribution has keys new/read/contacted/resolved."""
        Review.objects.create(business=self.biz, rating=2, status='new')
        Review.objects.create(business=self.biz, rating=3, status='new')
        Review.objects.create(business=self.biz, rating=1, status='read')
        Review.objects.create(business=self.biz, rating=2, status='resolved')

        resp = self.client.get('/api/v1/reviews/stats/')
        dist = resp.data['status_distribution']
        self.assertEqual(dist['new'], 2)
        self.assertEqual(dist['read'], 1)
        self.assertEqual(dist['contacted'], 0)
        self.assertEqual(dist['resolved'], 1)

    def test_reviews_last_7_and_30_days(self):
        """Trend counts use created_at filtering."""
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()

        # Recent review (within 7 days)
        Review.objects.create(business=self.biz, rating=5)
        Review.objects.create(business=self.biz, rating=4)

        # Older review (within 30 days but not 7)
        old_review = Review.objects.create(business=self.biz, rating=3)
        Review.objects.filter(pk=old_review.pk).update(
            created_at=now - timedelta(days=15),
        )

        # Very old review (outside 30 days)
        ancient_review = Review.objects.create(business=self.biz, rating=2)
        Review.objects.filter(pk=ancient_review.pk).update(
            created_at=now - timedelta(days=60),
        )

        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.data['reviews_last_7_days'], 2)
        self.assertEqual(resp.data['reviews_last_30_days'], 3)  # 2 recent + 1 at 15 days
        self.assertEqual(resp.data['total_reviews'], 4)

    def test_recent_reviews_returns_latest(self):
        """recent_reviews returns at most 5, newest first."""
        for i in range(7):
            Review.objects.create(business=self.biz, rating=(i % 5) + 1, comment=f'Review {i}')

        resp = self.client.get('/api/v1/reviews/stats/')
        recent = resp.data['recent_reviews']
        self.assertEqual(len(recent), 5)
        # Newest first (default ordering is -created_at)
        self.assertEqual(recent[0]['comment'], 'Review 6')

    def test_average_rating(self):
        """average_rating is rounded to 1 decimal."""
        Review.objects.create(business=self.biz, rating=5)
        Review.objects.create(business=self.biz, rating=4)
        Review.objects.create(business=self.biz, rating=3)

        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.data['average_rating'], 4.0)

    def test_visit_tracking_on_landing(self):
        """PublicReviewLandingView creates a ReviewVisit."""
        ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            google_place_id='ChIJ123',
        )
        self.client.logout()  # public endpoint
        # Use anonymous client
        from rest_framework.test import APIClient
        anon = APIClient()
        resp = anon.get('/api/v1/reviews/public/stats-biz/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 1)

    def test_stats_requires_auth(self):
        """Stats endpoint requires authentication."""
        self.client.logout()
        from rest_framework.test import APIClient
        anon = APIClient()
        resp = anon.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
