"""
Tests for the public landing text customisation feature.

Covers:
  1. Defaults (empty fields) → fallback to Business.name and default copy.
  2. Persisting `public_display_name` overrides business_name + display_name.
  3. Persisting `public_subtitle` overrides default subtitle.
  4. Persisting `public_question` overrides generated question.
  5. Whitespace is stripped (leading/trailing).
  6. Whitespace-only payload is rejected (400).
  7. HTML / angle-brackets are rejected (400).
  8. Max-length enforcement (120 / 180 / 180) → 400 when exceeded.
  9. Public endpoint never exposes the raw editable fields, only computed ones.
 10. URL slug `/r/{slug}/` is NOT affected — slug remains the Business.slug.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.business.models import Business, Subscription

from ..models import ReviewConfig

User = get_user_model()


def _make_business(slug='claudia', name='Centro Estético Claudia'):
    biz = Business.objects.create(name=name, slug=slug, default_service='qr_reviews')
    Subscription.objects.create(
        business=biz, plan='qr_reviews', service='qr_reviews', status='active',
    )
    return biz


def _make_owner(business):
    user = User.objects.create_user(
        email=f'owner-{business.slug}@example.com',
        password='Passw0rd!123',
    )
    user.business = business
    user.role = 'owner'
    user.save()
    return user


# ═══════════════════════════════════════════════════════════════════
# Public landing — defaults & overrides
# ═══════════════════════════════════════════════════════════════════

class PublicLandingDisplayDefaultsTests(TestCase):
    """Public endpoint returns fallbacks when the new fields are empty."""

    def setUp(self):
        self.biz = _make_business(slug='claudia-defaults')
        ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            mode='smart_filter',
            google_place_id='ChIJtest',
        )
        self.client = APIClient()

    def test_defaults_use_business_name_and_default_copy(self):
        url = f'/api/v1/reviews/public/{self.biz.slug}/'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['business_name'], 'Centro Estético Claudia')
        self.assertEqual(data['display_name'], 'Centro Estético Claudia')
        self.assertEqual(
            data['question'],
            '¿Cómo fue tu experiencia en Centro Estético Claudia?',
        )
        self.assertEqual(data['subtitle'], 'Tu opinión nos ayuda a mejorar 💛')

    def test_public_endpoint_does_not_expose_raw_fields(self):
        url = f'/api/v1/reviews/public/{self.biz.slug}/'
        data = self.client.get(url).json()
        self.assertNotIn('public_display_name', data)
        self.assertNotIn('public_subtitle', data)
        self.assertNotIn('public_question', data)


class PublicLandingDisplayOverridesTests(TestCase):
    """Custom values override the defaults but URL slug stays the same."""

    def setUp(self):
        self.biz = _make_business(slug='claudia-custom', name='Estética Claudia')
        self.config = ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            mode='smart_filter',
            google_place_id='ChIJtest',
            public_display_name='Centro Estético Claudia',
            public_subtitle='Queremos saber tu opinión 💛',
            public_question='¿Qué te pareció tu visita?',
        )
        self.client = APIClient()

    def test_display_name_overrides_business_name(self):
        data = self.client.get(f'/api/v1/reviews/public/{self.biz.slug}/').json()
        self.assertEqual(data['business_name'], 'Centro Estético Claudia')
        self.assertEqual(data['display_name'], 'Centro Estético Claudia')

    def test_subtitle_override(self):
        data = self.client.get(f'/api/v1/reviews/public/{self.biz.slug}/').json()
        self.assertEqual(data['subtitle'], 'Queremos saber tu opinión 💛')

    def test_question_override(self):
        data = self.client.get(f'/api/v1/reviews/public/{self.biz.slug}/').json()
        self.assertEqual(data['question'], '¿Qué te pareció tu visita?')

    def test_url_slug_unchanged(self):
        # The slug used to reach the landing remains Business.slug — never the
        # new public_display_name.
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.slug, 'claudia-custom')
        # 404 when querying the would-be slug derived from the display name.
        res = self.client.get('/api/v1/reviews/public/centro-estetico-claudia/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ═══════════════════════════════════════════════════════════════════
# Private PATCH endpoint — validation
# ═══════════════════════════════════════════════════════════════════

class PrivateConfigPublicTextValidationTests(APITestCase):
    """PATCH /api/v1/reviews/config/ validates the new editable fields."""

    def setUp(self):
        self.biz = _make_business(slug='claudia-validate')
        ReviewConfig.objects.create(business=self.biz, enabled=True, mode='direct')
        self.owner = _make_owner(self.biz)
        self.client.force_authenticate(user=self.owner)
        self.url = '/api/v1/reviews/config/'

    def test_whitespace_is_trimmed(self):
        res = self.client.patch(
            self.url,
            {'public_display_name': '  Claudia Spa  '},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        self.assertEqual(res.data['public_display_name'], 'Claudia Spa')

    def test_whitespace_only_is_rejected(self):
        res = self.client.patch(
            self.url,
            {'public_display_name': '   '},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('public_display_name', res.data)

    def test_html_is_rejected(self):
        res = self.client.patch(
            self.url,
            {'public_question': '¿Qué <script>alert(1)</script> pasó?'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('public_question', res.data)

    def test_angle_bracket_alone_is_rejected(self):
        res = self.client.patch(
            self.url,
            {'public_subtitle': 'algo > 5 estrellas'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_max_length_display_name(self):
        res = self.client.patch(
            self.url,
            {'public_display_name': 'x' * 121},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_max_length_subtitle(self):
        res = self.client.patch(
            self.url,
            {'public_subtitle': 'x' * 181},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_max_length_question(self):
        res = self.client.patch(
            self.url,
            {'public_question': 'x' * 181},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_strings_clear_overrides(self):
        # Set then clear.
        self.client.patch(
            self.url,
            {'public_display_name': 'Foo'},
            format='json',
        )
        res = self.client.patch(
            self.url,
            {'public_display_name': ''},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['public_display_name'], '')
