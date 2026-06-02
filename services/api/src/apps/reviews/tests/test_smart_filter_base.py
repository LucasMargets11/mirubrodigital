"""
Smart-filter is part of the Base tier — regression tests.

Verifies that a business on ``qr_reviews_base`` can:
  • Read ``smart_filter_allowed = True`` from the config endpoint.
  • PATCH ``mode = 'smart_filter'`` successfully.
  • Submit a high rating → redirect to Google.
  • Submit a low rating → private feedback (no external redirect).
  • Receive the feedback (basic). Status-management UI is gated on Pro
    at the frontend; the backend list endpoint still returns the rows.

Also verifies that carteles (qr_poster_designs) remain Pro-only.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.business.models import Business, Subscription
from apps.accounts.models import Membership
from apps.reviews.models import Review, ReviewConfig
from apps.reviews.entitlements import (
    is_reviews_pro,
    reviews_allowed,
    smart_filter_allowed,
)

User = get_user_model()


def _create_business(slug: str, plan: str) -> Business:
    biz = Business.objects.create(name=f'Biz {slug}', default_service='qr_reviews', slug=slug)
    Subscription.objects.create(business=biz, plan=plan, service='qr_reviews', status='active')
    return biz


def _auth_client(client: APIClient, business: Business, role: str = 'owner') -> User:
    user = User.objects.create_user(username=f'u-{business.slug}', password='pass1234')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


class SmartFilterBaseEntitlementTests(APITestCase):
    """Direct unit tests on the resolver."""

    def test_smart_filter_allowed_for_qr_reviews_base(self):
        biz = _create_business(slug='base-biz', plan='qr_reviews_base')
        self.assertTrue(smart_filter_allowed(biz))
        self.assertFalse(is_reviews_pro(biz))
        self.assertTrue(reviews_allowed(biz))

    def test_smart_filter_allowed_for_legacy_qr_reviews(self):
        biz = _create_business(slug='legacy-biz', plan='qr_reviews')
        self.assertTrue(smart_filter_allowed(biz))
        self.assertFalse(is_reviews_pro(biz))

    def test_smart_filter_allowed_for_qr_reviews_pro(self):
        biz = _create_business(slug='pro-biz', plan='qr_reviews_pro')
        self.assertTrue(smart_filter_allowed(biz))
        self.assertTrue(is_reviews_pro(biz))


class SmartFilterBaseConfigPatchTests(APITestCase):
    """PATCH /api/v1/reviews/config/ — Base must accept mode=smart_filter."""

    def setUp(self):
        cache.clear()
        self.biz = _create_business(slug='base-cfg', plan='qr_reviews_base')
        ReviewConfig.objects.create(business=self.biz, enabled=True, mode='direct')
        _auth_client(self.client, self.biz)

    def test_base_can_set_smart_filter_mode(self):
        resp = self.client.patch(
            '/api/v1/reviews/config/',
            {'mode': 'smart_filter'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['mode'], 'smart_filter')
        self.assertEqual(resp.data['effective_mode'], 'smart_filter')
        self.assertTrue(resp.data['smart_filter_allowed'])
        self.assertFalse(resp.data['is_reviews_pro'])


class SmartFilterBaseSubmitFlowTests(APITestCase):
    """Public submit endpoint behaviour for a Base business in smart_filter mode."""

    def setUp(self):
        cache.clear()
        self.biz = _create_business(slug='base-submit', plan='qr_reviews_base')
        ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            mode='smart_filter',
            google_place_id='ChIJbase',
            redirect_threshold=4,
            thank_you_message='¡Gracias!',
        )

    def test_high_rating_redirects_to_google(self):
        resp = self.client.post(
            '/api/v1/reviews/public/base-submit/submit/',
            {'rating': 5},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertIn('placeid=ChIJbase', resp.data['redirect_url'])
        self.assertEqual(Review.objects.filter(business=self.biz).count(), 0)

    def test_low_rating_becomes_private_feedback(self):
        resp = self.client.post(
            '/api/v1/reviews/public/base-submit/submit/',
            {'rating': 2, 'comment': 'No me gustó'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['action'], 'submitted')
        reviews = Review.objects.filter(business=self.biz)
        self.assertEqual(reviews.count(), 1)
        self.assertEqual(reviews.first().rating, 2)

    def test_boundary_threshold_redirects(self):
        """rating == threshold should redirect (threshold=4)."""
        resp = self.client.post(
            '/api/v1/reviews/public/base-submit/submit/',
            {'rating': 4},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['action'], 'redirect')


class CartelesStillProOnlyTests(APITestCase):
    """Posters / carteles endpoints must remain Pro-only."""

    def setUp(self):
        cache.clear()

    def test_base_cannot_list_poster_designs(self):
        biz = _create_business(slug='base-posters', plan='qr_reviews_base')
        _auth_client(self.client, biz)
        resp = self.client.get('/api/v1/reviews/qr-posters/designs/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_pro_can_list_poster_designs(self):
        biz = _create_business(slug='pro-posters', plan='qr_reviews_pro')
        _auth_client(self.client, biz)
        resp = self.client.get('/api/v1/reviews/qr-posters/designs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class StatusManagementProOnlyTests(APITestCase):
    """PATCH /api/v1/reviews/<id>/ — status changes are Pro-only (PR-A)."""

    def setUp(self):
        cache.clear()

    def _make_review(self, business) -> Review:
        return Review.objects.create(
            business=business, rating=2, comment='Test',
            source='qr', ip_hash='hash-status',
        )

    def test_base_cannot_change_status(self):
        biz = _create_business(slug='base-status', plan='qr_reviews_base')
        _auth_client(self.client, biz)
        review = self._make_review(biz)

        resp = self.client.patch(
            f'/api/v1/reviews/{review.id}/',
            {'status': 'read'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Pro', resp.data['detail'])

        review.refresh_from_db()
        self.assertEqual(review.status, 'new')  # unchanged

    def test_pro_can_change_status(self):
        biz = _create_business(slug='pro-status', plan='qr_reviews_pro')
        _auth_client(self.client, biz)
        review = self._make_review(biz)

        resp = self.client.patch(
            f'/api/v1/reviews/{review.id}/',
            {'status': 'read'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        review.refresh_from_db()
        self.assertEqual(review.status, 'read')


class StatsProOnlyFieldsTests(APITestCase):
    """GET /api/v1/reviews/stats/ — advanced metrics are stripped for Base (PR-A)."""

    _PRO_ONLY_FIELDS = {
        'conversion_rate', 'resolution_rate', 'positive_rate', 'negative_rate',
        'contacted_reviews', 'resolved_reviews', 'status_distribution',
        'reviews_last_7_days', 'reviews_last_30_days',
        'visits_last_7_days', 'visits_last_30_days', 'daily_trend',
    }
    _BASE_FIELDS = {
        'total_reviews', 'average_rating', 'total_visits',
        'rating_distribution', 'recent_reviews', 'new_reviews',
        'negative_reviews', 'positive_reviews',
        'redirect_threshold', 'effective_mode',
    }

    def setUp(self):
        cache.clear()

    def test_base_stats_response_strips_advanced_fields(self):
        biz = _create_business(slug='base-stats', plan='qr_reviews_base')
        _auth_client(self.client, biz)

        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        keys = set(resp.data.keys())
        self.assertTrue(self._BASE_FIELDS.issubset(keys), msg=f"missing base fields: {self._BASE_FIELDS - keys}")
        leaked = keys & self._PRO_ONLY_FIELDS
        self.assertFalse(leaked, msg=f"Pro-only fields leaked to Base: {leaked}")

    def test_pro_stats_response_includes_advanced_fields(self):
        biz = _create_business(slug='pro-stats', plan='qr_reviews_pro')
        _auth_client(self.client, biz)

        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        keys = set(resp.data.keys())
        self.assertTrue(self._BASE_FIELDS.issubset(keys))
        self.assertTrue(self._PRO_ONLY_FIELDS.issubset(keys),
                        msg=f"missing pro fields: {self._PRO_ONLY_FIELDS - keys}")
