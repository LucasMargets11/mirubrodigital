"""
Bloque 15 — Comprehensive public-flow and branding tests for QR de Reseñas.

Covers:
  - PublicReviewConfigSerializer: logo_url, accent_color, is_pro, fallbacks
  - Direct mode: landing + submit integration
  - Smart-filter mode: landing + submit integration (high/low rating)
  - Branding fallbacks: empty branding, partial, full, no-branding edge case
  - effective_mode governance: Pro, Base, trial active, trial expired
  - Tracking: ReviewVisit creation, Review creation/non-creation, stats consistency
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from apps.business.models import Business, BusinessBranding, Subscription

from ..models import Review, ReviewConfig, ReviewVisit
from ..serializers import PublicReviewConfigSerializer

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _biz(name='Pub Biz', slug='pub-biz', plan='qr_reviews', service='qr_reviews'):
    """Create a business with subscription. Signal auto-creates BusinessBranding."""
    biz = Business.objects.create(name=name, slug=slug, default_service=service)
    Subscription.objects.create(business=biz, plan=plan, service=service, status='active')
    return biz


def _biz_pro(name='Pro Biz', slug='pro-biz'):
    return _biz(name=name, slug=slug, plan='qr_reviews_pro')


def _cfg(business, **kwargs):
    """Create an enabled ReviewConfig with sensible defaults."""
    defaults = dict(
        enabled=True,
        google_place_id='ChIJtest',
        redirect_threshold=4,
        thank_you_message='¡Gracias!',
        mode='direct',
    )
    defaults.update(kwargs)
    return ReviewConfig.objects.create(business=business, **defaults)


def _request():
    """Build a fake DRF request for serializer context."""
    factory = APIRequestFactory()
    return factory.get('/fake/')


# ═══════════════════════════════════════════════════════════════════════════
# 1. PublicReviewConfigSerializer — branding & is_pro fields
# ═══════════════════════════════════════════════════════════════════════════

class PublicSerializerBrandingTests(TestCase):
    """Unit tests for logo_url, accent_color, is_pro on PublicReviewConfigSerializer."""

    def setUp(self):
        self.biz = _biz(slug='ser-biz')
        self.config = _cfg(self.biz)
        self.branding = self.biz.branding  # auto-created by signal

    def _serialize(self, config=None):
        config = config or self.config
        request = _request()
        return PublicReviewConfigSerializer(config, context={'request': request}).data

    # ── logo_url ───────────────────────────────────────────────

    def test_logo_url_with_logo(self):
        """When logo_square has a file, logo_url is an absolute URL."""
        self.branding.logo_square.save('logo.png', ContentFile(b'\x89PNG fake'), save=True)
        data = self._serialize()
        self.assertIsNotNone(data['logo_url'])
        self.assertIn('logo', data['logo_url'])
        self.assertTrue(data['logo_url'].startswith('http'))

    def test_logo_url_without_logo(self):
        """Empty logo_square → logo_url is None."""
        data = self._serialize()
        self.assertIsNone(data['logo_url'])

    def test_logo_url_without_request_context(self):
        """If no request in context, falls back to relative URL."""
        self.branding.logo_square.save('logo2.png', ContentFile(b'\x89PNG fake'), save=True)
        data = PublicReviewConfigSerializer(self.config).data
        # Should still return something (relative path), not crash
        self.assertIsNotNone(data['logo_url'])

    # ── accent_color ───────────────────────────────────────────

    def test_accent_color_present(self):
        """When accent_color is set, it's returned."""
        self.branding.accent_color = '#FF5500'
        self.branding.save()
        data = self._serialize()
        self.assertEqual(data['accent_color'], '#FF5500')

    def test_accent_color_empty(self):
        """Empty accent_color → None."""
        data = self._serialize()
        self.assertIsNone(data['accent_color'])

    # ── is_pro ─────────────────────────────────────────────────

    def test_is_pro_true_for_pro_plan(self):
        pro = _biz_pro(slug='pro-ser')
        config = _cfg(pro)
        data = self._serialize(config)
        self.assertTrue(data['is_pro'])

    def test_is_pro_false_for_base_plan(self):
        data = self._serialize()
        self.assertFalse(data['is_pro'])

    # ── combined fallback ──────────────────────────────────────

    def test_defaults_all_null_for_empty_branding(self):
        """A new business has auto-created empty branding → all null/False."""
        data = self._serialize()
        self.assertIsNone(data['logo_url'])
        self.assertIsNone(data['accent_color'])
        self.assertFalse(data['is_pro'])

    def test_full_branding_pro_returns_all_fields(self):
        """Pro business with full branding returns logo_url + accent_color + is_pro."""
        pro = _biz_pro(slug='full-brand')
        branding = pro.branding
        branding.logo_square.save('square.png', ContentFile(b'\x89PNG fake'), save=True)
        branding.accent_color = '#0066CC'
        branding.save()
        config = _cfg(pro)

        data = self._serialize(config)
        self.assertIsNotNone(data['logo_url'])
        self.assertEqual(data['accent_color'], '#0066CC')
        self.assertTrue(data['is_pro'])

    # ── logo_url horizontal-first fallback ─────────────────────

    def test_logo_url_prefers_horizontal_over_square(self):
        """When both logo_horizontal and logo_square exist,
        the public serializer must expose logo_horizontal in logo_url."""
        self.branding.logo_horizontal.save('horiz.png', ContentFile(b'\x89PNG fake'), save=True)
        self.branding.logo_square.save('square.png', ContentFile(b'\x89PNG fake'), save=True)
        data = self._serialize()
        self.assertIsNotNone(data['logo_url'])
        self.assertIn('horiz', data['logo_url'])
        self.assertNotIn('square', data['logo_url'])

    def test_logo_url_falls_back_to_square_when_no_horizontal(self):
        """When only logo_square exists, the public serializer must expose logo_square in logo_url."""
        self.branding.logo_square.save('sq-only.png', ContentFile(b'\x89PNG fake'), save=True)
        data = self._serialize()
        self.assertIsNotNone(data['logo_url'])
        self.assertIn('sq-only', data['logo_url'])


# ═══════════════════════════════════════════════════════════════════════════
# 2. Direct mode — public integration
# ═══════════════════════════════════════════════════════════════════════════

class PublicDirectModeIntegrationTests(APITestCase):
    """E2E tests for the direct mode public experience."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.biz = _biz(slug='dir-int')
        self.config = _cfg(self.biz, mode='direct')

    def test_landing_returns_direct_mode(self):
        resp = self.client.get('/api/v1/reviews/public/dir-int/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['mode'], 'direct')
        self.assertEqual(resp.data['effective_mode'], 'direct')
        self.assertEqual(resp.data['business_name'], 'Pub Biz')

    def test_landing_creates_visit(self):
        self.client.get('/api/v1/reviews/public/dir-int/')
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 1)

    def test_landing_returns_branding_fields(self):
        """Even empty branding, the fields are present and null."""
        resp = self.client.get('/api/v1/reviews/public/dir-int/')
        self.assertIn('logo_url', resp.data)
        self.assertIn('accent_color', resp.data)
        self.assertIn('is_pro', resp.data)
        self.assertIsNone(resp.data['logo_url'])
        self.assertIsNone(resp.data['accent_color'])
        self.assertFalse(resp.data['is_pro'])

    def test_landing_with_branding_pro(self):
        """Pro business with branding returns logo + accent in landing."""
        pro = _biz_pro(slug='dir-pro')
        _cfg(pro, mode='direct')
        branding = pro.branding
        branding.logo_square.save('dir-logo.png', ContentFile(b'\x89PNG'), save=True)
        branding.accent_color = '#AA0000'
        branding.save()

        resp = self.client.get('/api/v1/reviews/public/dir-pro/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['logo_url'])
        self.assertEqual(resp.data['accent_color'], '#AA0000')
        self.assertTrue(resp.data['is_pro'])

    def test_submit_low_rating_redirects_in_direct(self):
        """Even low ratings always redirect in direct mode — no Review created."""
        resp = self.client.post('/api/v1/reviews/public/dir-int/submit/', {'rating': 1})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertEqual(Review.objects.count(), 0)

    def test_submit_high_rating_redirects_in_direct(self):
        resp = self.client.post('/api/v1/reviews/public/dir-int/submit/', {'rating': 5})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertEqual(Review.objects.count(), 0)

    def test_submit_never_creates_review_in_direct(self):
        """Submit every possible rating — none should create a Review."""
        for r in range(1, 6):
            self.client.post('/api/v1/reviews/public/dir-int/submit/', {'rating': r})
        self.assertEqual(Review.objects.count(), 0)

    def test_submit_returns_redirect_url(self):
        resp = self.client.post('/api/v1/reviews/public/dir-int/submit/', {'rating': 3})
        self.assertIn('placeid=ChIJtest', resp.data['redirect_url'])

    def test_submit_returns_thank_you_message(self):
        resp = self.client.post('/api/v1/reviews/public/dir-int/submit/', {'rating': 3})
        self.assertEqual(resp.data['message'], '¡Gracias!')


# ═══════════════════════════════════════════════════════════════════════════
# 3. Smart-filter mode — public integration
# ═══════════════════════════════════════════════════════════════════════════

class PublicSmartFilterIntegrationTests(APITestCase):
    """E2E tests for the smart_filter mode public experience."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.biz = _biz_pro(slug='sf-int')
        self.config = _cfg(self.biz, mode='smart_filter')

    def test_landing_returns_smart_filter_mode(self):
        resp = self.client.get('/api/v1/reviews/public/sf-int/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['mode'], 'smart_filter')
        self.assertEqual(resp.data['effective_mode'], 'smart_filter')

    def test_landing_creates_visit(self):
        self.client.get('/api/v1/reviews/public/sf-int/')
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 1)

    def test_landing_returns_all_fields(self):
        """smart_filter landing includes config fields + branding."""
        resp = self.client.get('/api/v1/reviews/public/sf-int/')
        for field in [
            'business_name', 'redirect_url', 'redirect_threshold',
            'collect_contact', 'thank_you_message', 'enabled',
            'mode', 'effective_mode', 'logo_url', 'accent_color', 'is_pro',
        ]:
            self.assertIn(field, resp.data, f'Missing field: {field}')

    def test_high_rating_redirects(self):
        """Rating >= threshold → redirect action, no Review created."""
        resp = self.client.post('/api/v1/reviews/public/sf-int/submit/', {'rating': 5})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertEqual(Review.objects.count(), 0)

    def test_threshold_boundary_redirects(self):
        """Rating == threshold → redirect."""
        resp = self.client.post('/api/v1/reviews/public/sf-int/submit/', {'rating': 4})
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertEqual(Review.objects.count(), 0)

    def test_low_rating_creates_feedback(self):
        """Rating < threshold → creates Review with submitted action."""
        resp = self.client.post(
            '/api/v1/reviews/public/sf-int/submit/',
            {'rating': 2, 'comment': 'Mejorar servicio'},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['action'], 'submitted')
        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.first()
        self.assertEqual(review.rating, 2)
        self.assertEqual(review.comment, 'Mejorar servicio')
        self.assertEqual(review.business, self.biz)

    def test_low_rating_with_contact_info(self):
        """Contact info is persisted when collect_contact is enabled."""
        self.config.collect_contact = True
        self.config.save()
        resp = self.client.post(
            '/api/v1/reviews/public/sf-int/submit/',
            {'rating': 1, 'comment': 'Malo', 'contact_info': 'test@mail.com'},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        review = Review.objects.first()
        self.assertEqual(review.contact_info, 'test@mail.com')

    def test_low_rating_source_defaults_qr(self):
        """Default source is 'qr'."""
        self.client.post('/api/v1/reviews/public/sf-int/submit/', {'rating': 2})
        self.assertEqual(Review.objects.first().source, 'qr')

    def test_low_rating_custom_source(self):
        """Explicit source is persisted."""
        self.client.post(
            '/api/v1/reviews/public/sf-int/submit/',
            {'rating': 2, 'source': 'menu'},
        )
        self.assertEqual(Review.objects.first().source, 'menu')

    def test_dedup_blocks_second_submit(self):
        """Same IP cannot submit twice within 10-min window."""
        self.client.post('/api/v1/reviews/public/sf-int/submit/', {'rating': 2})
        resp = self.client.post('/api/v1/reviews/public/sf-int/submit/', {'rating': 3})
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(Review.objects.count(), 1)

    def test_smart_filter_with_branding(self):
        """Pro business with branding shows branding in landing."""
        branding = self.biz.branding
        branding.logo_square.save('sf-logo.png', ContentFile(b'\x89PNG'), save=True)
        branding.accent_color = '#00CC66'
        branding.save()

        resp = self.client.get('/api/v1/reviews/public/sf-int/')
        self.assertIsNotNone(resp.data['logo_url'])
        self.assertEqual(resp.data['accent_color'], '#00CC66')
        self.assertTrue(resp.data['is_pro'])


# ═══════════════════════════════════════════════════════════════════════════
# 4. Branding fallback edge cases
# ═══════════════════════════════════════════════════════════════════════════

class BrandingFallbackTests(APITestCase):
    """Verify branding resolves correctly across different states."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_new_business_auto_creates_branding(self):
        """post_save signal creates empty BrandingProfile."""
        biz = _biz(slug='auto-brand')
        self.assertTrue(BusinessBranding.objects.filter(business=biz).exists())

    def test_empty_branding_returns_null(self):
        """Auto-created branding with no data → null fields in API."""
        biz = _biz(slug='empty-brand')
        _cfg(biz)
        resp = self.client.get('/api/v1/reviews/public/empty-brand/')
        self.assertIsNone(resp.data['logo_url'])
        self.assertIsNone(resp.data['accent_color'])

    def test_partial_branding_logo_only(self):
        """Only logo set → logo_url present, accent_color null."""
        biz = _biz(slug='logo-only')
        _cfg(biz)
        branding = biz.branding
        branding.logo_square.save('only-logo.png', ContentFile(b'\x89PNG'), save=True)

        resp = self.client.get('/api/v1/reviews/public/logo-only/')
        self.assertIsNotNone(resp.data['logo_url'])
        self.assertIsNone(resp.data['accent_color'])

    def test_partial_branding_accent_only(self):
        """Only accent_color set → logo_url null, accent_color present."""
        biz = _biz(slug='accent-only')
        _cfg(biz)
        branding = biz.branding
        branding.accent_color = '#112233'
        branding.save()

        resp = self.client.get('/api/v1/reviews/public/accent-only/')
        self.assertIsNone(resp.data['logo_url'])
        self.assertEqual(resp.data['accent_color'], '#112233')

    def test_full_branding(self):
        """Both logo and accent → both present."""
        biz = _biz(slug='full-brand')
        _cfg(biz)
        branding = biz.branding
        branding.logo_square.save('full-logo.png', ContentFile(b'\x89PNG'), save=True)
        branding.accent_color = '#AABBCC'
        branding.save()

        resp = self.client.get('/api/v1/reviews/public/full-brand/')
        self.assertIsNotNone(resp.data['logo_url'])
        self.assertEqual(resp.data['accent_color'], '#AABBCC')

    def test_no_branding_object_does_not_crash(self):
        """If BusinessBranding is somehow missing, serializer returns None gracefully."""
        biz = _biz(slug='no-branding')
        _cfg(biz)
        # Force-delete the auto-created branding
        BusinessBranding.objects.filter(business=biz).delete()

        resp = self.client.get('/api/v1/reviews/public/no-branding/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data['logo_url'])
        self.assertIsNone(resp.data['accent_color'])

    def test_base_plan_is_pro_false(self):
        biz = _biz(slug='base-brand')
        _cfg(biz)
        resp = self.client.get('/api/v1/reviews/public/base-brand/')
        self.assertFalse(resp.data['is_pro'])

    def test_pro_plan_is_pro_true(self):
        biz = _biz_pro(slug='pro-brand')
        _cfg(biz)
        resp = self.client.get('/api/v1/reviews/public/pro-brand/')
        self.assertTrue(resp.data['is_pro'])


# ═══════════════════════════════════════════════════════════════════════════
# 5. effective_mode governance in public flow
# ═══════════════════════════════════════════════════════════════════════════

class EffectiveModePublicTests(APITestCase):
    """Verify effective_mode correctly governs public submit behavior."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_base_with_smart_filter_mode_falls_back_to_direct(self):
        """Base plan with mode=smart_filter → effective_mode=direct."""
        biz = _biz(slug='base-sf', plan='qr_reviews')
        _cfg(biz, mode='smart_filter')

        resp = self.client.get('/api/v1/reviews/public/base-sf/')
        self.assertEqual(resp.data['mode'], 'smart_filter')
        self.assertEqual(resp.data['effective_mode'], 'direct')

    def test_base_smart_filter_submit_always_redirects(self):
        """Submit on Base-plan smart_filter config → redirect (effective_mode=direct)."""
        biz = _biz(slug='base-sf-sub', plan='qr_reviews')
        _cfg(biz, mode='smart_filter')

        resp = self.client.post('/api/v1/reviews/public/base-sf-sub/submit/', {'rating': 1})
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertEqual(Review.objects.count(), 0)

    def test_pro_with_smart_filter_stays_smart_filter(self):
        """Pro plan with mode=smart_filter → effective_mode=smart_filter."""
        biz = _biz_pro(slug='pro-sf')
        _cfg(biz, mode='smart_filter')

        resp = self.client.get('/api/v1/reviews/public/pro-sf/')
        self.assertEqual(resp.data['mode'], 'smart_filter')
        self.assertEqual(resp.data['effective_mode'], 'smart_filter')

    def test_pro_smart_filter_low_rating_creates_review(self):
        """Pro plan, smart_filter, low rating → Review created."""
        biz = _biz_pro(slug='pro-sf-sub')
        _cfg(biz, mode='smart_filter')

        resp = self.client.post('/api/v1/reviews/public/pro-sf-sub/submit/', {'rating': 2})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['action'], 'submitted')
        self.assertEqual(Review.objects.count(), 1)

    def test_trial_active_allows_smart_filter(self):
        """Active trial on Base plan → effective_mode=smart_filter."""
        biz = _biz(slug='trial-active', plan='qr_reviews')
        _cfg(
            biz,
            mode='smart_filter',
            trial_used=True,
            trial_ends_at=timezone.now() + timedelta(days=3),
        )

        resp = self.client.get('/api/v1/reviews/public/trial-active/')
        self.assertEqual(resp.data['effective_mode'], 'smart_filter')

    def test_trial_active_submit_creates_review(self):
        """Active trial, low rating → Review created (smart_filter works)."""
        biz = _biz(slug='trial-sub', plan='qr_reviews')
        _cfg(
            biz,
            mode='smart_filter',
            trial_used=True,
            trial_ends_at=timezone.now() + timedelta(days=3),
        )

        resp = self.client.post('/api/v1/reviews/public/trial-sub/submit/', {'rating': 2})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Review.objects.count(), 1)

    def test_trial_expired_falls_back_to_direct(self):
        """Expired trial on Base plan → effective_mode=direct."""
        biz = _biz(slug='trial-exp', plan='qr_reviews')
        _cfg(
            biz,
            mode='smart_filter',
            trial_used=True,
            trial_ends_at=timezone.now() - timedelta(days=1),
        )

        resp = self.client.get('/api/v1/reviews/public/trial-exp/')
        self.assertEqual(resp.data['mode'], 'smart_filter')
        self.assertEqual(resp.data['effective_mode'], 'direct')

    def test_trial_expired_submit_redirects(self):
        """Expired trial → low rating submit still redirects (effective_mode=direct)."""
        biz = _biz(slug='trial-exp-sub', plan='qr_reviews')
        _cfg(
            biz,
            mode='smart_filter',
            trial_used=True,
            trial_ends_at=timezone.now() - timedelta(days=1),
        )

        resp = self.client.post('/api/v1/reviews/public/trial-exp-sub/submit/', {'rating': 1})
        self.assertEqual(resp.data['action'], 'redirect')
        self.assertEqual(Review.objects.count(), 0)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Tracking consistency
# ═══════════════════════════════════════════════════════════════════════════

class TrackingConsistencyTests(APITestCase):
    """Verify ReviewVisit and Review tracking is consistent and correct."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.biz = _biz_pro(slug='track-biz')
        self.config = _cfg(self.biz, mode='smart_filter')

    def test_visit_created_on_landing(self):
        """Each GET to public landing creates exactly one ReviewVisit."""
        self.client.get('/api/v1/reviews/public/track-biz/')
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 1)

    def test_multiple_visits_tracked(self):
        """Multiple landings → multiple visits (distinct IPs bypass dedup)."""
        for i in range(5):
            with patch('apps.reviews.views.hash_ip', return_value=f'ip-{i}'):
                self.client.get('/api/v1/reviews/public/track-biz/')
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 5)

    def test_no_visit_on_submit(self):
        """POST to submit does NOT create a visit (only landing does)."""
        self.client.post('/api/v1/reviews/public/track-biz/submit/', {'rating': 2})
        self.assertEqual(ReviewVisit.objects.filter(business=self.biz).count(), 0)

    def test_review_only_on_low_rating_smart_filter(self):
        """In smart_filter: low rating → Review, high rating → no Review."""
        self.client.post('/api/v1/reviews/public/track-biz/submit/', {'rating': 2})
        self.assertEqual(Review.objects.count(), 1)

    def test_review_not_created_on_high_rating(self):
        """High rating in smart_filter → no Review (redirect only)."""
        self.client.post('/api/v1/reviews/public/track-biz/submit/', {'rating': 5})
        self.assertEqual(Review.objects.count(), 0)

    def test_review_not_created_in_direct_mode(self):
        """Direct mode → never creates Review regardless of rating."""
        biz_d = _biz(slug='track-dir')
        _cfg(biz_d, mode='direct')
        for r in range(1, 6):
            self.client.post('/api/v1/reviews/public/track-dir/submit/', {'rating': r})
        self.assertEqual(Review.objects.filter(business=biz_d).count(), 0)

    def test_review_fields_match_submission(self):
        """All submitted fields are persisted correctly on the Review."""
        self.client.post(
            '/api/v1/reviews/public/track-biz/submit/',
            {'rating': 3, 'comment': 'Feedback here', 'contact_info': 'me@x.com', 'source': 'direct'},
        )
        review = Review.objects.first()
        self.assertEqual(review.rating, 3)
        self.assertEqual(review.comment, 'Feedback here')
        self.assertEqual(review.contact_info, 'me@x.com')
        self.assertEqual(review.source, 'direct')
        self.assertEqual(review.status, 'new')
        self.assertIsNotNone(review.ip_hash)

    def test_stats_reflect_visits_and_reviews(self):
        """Stats endpoint counts match actual tracking data."""
        from apps.accounts.models import Membership

        user = User.objects.create_user(username='stats-u', password='pass')
        Membership.objects.create(user=user, business=self.biz, role='owner')
        self.client.force_authenticate(user=user)

        # Generate tracking data
        from rest_framework.test import APIClient
        anon = APIClient()
        for i in range(3):
            with patch('apps.reviews.views.hash_ip', return_value=f'visit-ip-{i}'):
                anon.get('/api/v1/reviews/public/track-biz/')
        anon.post('/api/v1/reviews/public/track-biz/submit/', {'rating': 2, 'comment': 'Meh'})

        # Check stats
        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_visits'], 3)
        self.assertEqual(resp.data['total_reviews'], 1)
        self.assertEqual(resp.data['negative_reviews'], 1)
        self.assertEqual(resp.data['positive_reviews'], 0)

    def test_conversion_rate_reflects_tracking(self):
        """conversion_rate = reviews / visits * 100."""
        from apps.accounts.models import Membership

        user = User.objects.create_user(username='conv-u', password='pass')
        Membership.objects.create(user=user, business=self.biz, role='owner')

        from rest_framework.test import APIClient
        anon = APIClient()
        # 4 visits (distinct IPs to bypass dedup)
        for i in range(4):
            with patch('apps.reviews.views.hash_ip', return_value=f'conv-ip-{i}'):
                anon.get('/api/v1/reviews/public/track-biz/')
        # 2 reviews (low rating)
        anon.post('/api/v1/reviews/public/track-biz/submit/', {'rating': 1})
        # Need a fresh IP for second submit (dedup). We patch ip hash.
        with patch('apps.reviews.views.hash_ip', return_value='different-ip'):
            anon.post('/api/v1/reviews/public/track-biz/submit/', {'rating': 2})

        self.client.force_authenticate(user=user)
        resp = self.client.get('/api/v1/reviews/stats/')
        self.assertEqual(resp.data['total_visits'], 4)
        self.assertEqual(resp.data['total_reviews'], 2)
        self.assertEqual(resp.data['conversion_rate'], 50.0)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Disabled / 404 guard tests
# ═══════════════════════════════════════════════════════════════════════════

class PublicGuardTests(APITestCase):
    """Verify disabled/missing config returns correct error codes."""

    def test_landing_disabled_returns_404(self):
        biz = _biz(slug='dis-guard')
        _cfg(biz, enabled=False)
        resp = self.client.get('/api/v1/reviews/public/dis-guard/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_landing_no_config_returns_404(self):
        biz = _biz(slug='nocfg-guard')
        resp = self.client.get('/api/v1/reviews/public/nocfg-guard/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_landing_no_entitlement_returns_404(self):
        """Business without reviews entitlement → 404."""
        biz = Business.objects.create(name='No Ent', slug='no-ent', default_service='menu_qr')
        Subscription.objects.create(business=biz, plan='menu_qr_lite', service='menu_qr', status='active')
        _cfg(biz)
        resp = self.client.get('/api/v1/reviews/public/no-ent/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_disabled_returns_403(self):
        biz = _biz(slug='dis-sub')
        _cfg(biz, enabled=False)
        resp = self.client.post('/api/v1/reviews/public/dis-sub/submit/', {'rating': 3})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_submit_no_entitlement_returns_403(self):
        """Business without reviews entitlement → 403 on submit."""
        biz = Business.objects.create(name='No Ent Sub', slug='no-ent-sub', default_service='menu_qr')
        Subscription.objects.create(business=biz, plan='menu_qr_lite', service='menu_qr', status='active')
        _cfg(biz)
        resp = self.client.post('/api/v1/reviews/public/no-ent-sub/submit/', {'rating': 3})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_landing_nonexistent_slug_returns_404(self):
        resp = self.client.get('/api/v1/reviews/public/does-not-exist/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_nonexistent_slug_returns_404(self):
        resp = self.client.post('/api/v1/reviews/public/does-not-exist/submit/', {'rating': 3})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_landing_no_visit_when_disabled(self):
        """Disabled config → no ReviewVisit created."""
        biz = _biz(slug='dis-visit')
        _cfg(biz, enabled=False)
        self.client.get('/api/v1/reviews/public/dis-visit/')
        self.assertEqual(ReviewVisit.objects.filter(business=biz).count(), 0)
