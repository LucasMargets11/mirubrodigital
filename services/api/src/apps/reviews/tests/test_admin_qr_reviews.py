"""
Tests for the platform admin QR de Reseñas config endpoints.

Covers:
  1. Admin can GET QR Reviews config for a qr_reviews business.
  2. Admin can change slug to a valid new value.
  3. Duplicate slug is rejected with 400.
  4. Slugs with spaces, apostrophes or uppercase are rejected.
  5. Admin can save google_place_id.
  6. google_place_updated_at is stamped when google_place_id changes.
  7. ReviewConfig is created on first PATCH if it didn't exist.
  8. Non-admin user receives 403.
  9. Non-qr_reviews business returns 400.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import AccountProfile, Membership
from apps.business.models import Business, Subscription
from apps.reviews.models import ReviewConfig

User = get_user_model()

# ── Helpers ────────────────────────────────────────────────────────────────

BASE_URL = '/api/v1/platform-admin/clients/{}/qr-reviews-config/'


def _make_qr_reviews_biz(name='QR Biz', slug='qr-biz-test'):
    biz = Business.objects.create(
        name=name,
        slug=slug,
        default_service='qr_reviews',
        service_type='qr_reviews',
    )
    Subscription.objects.create(business=biz, plan='qr_reviews', service='qr_reviews', status='active')
    return biz


def _make_platform_staff(email='staff@mirubro.com', role='superadmin'):
    user = User.objects.create_user(username=email, email=email, password='s3cur3pass!')
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.is_platform_staff = True
    profile.internal_role = role
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    # Return a fresh instance so Django doesn't use a cached (stale) account_profile.
    return User.objects.get(pk=user.pk)


def _make_regular_user(email='regular@biz.com'):
    user = User.objects.create_user(username=email, email=email, password='pass1234')
    return user


# ── Test: GET config ───────────────────────────────────────────────────────

class AdminQRReviewsGetTests(APITestCase):

    def setUp(self):
        self.staff = _make_platform_staff()
        self.biz = _make_qr_reviews_biz()
        ReviewConfig.objects.create(
            business=self.biz,
            enabled=True,
            google_place_id='ChIJTest123',
            google_place_name='Test Place',
        )

    def test_admin_can_get_config(self):
        """Admin (superadmin) gets full snapshot for a qr_reviews business."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(BASE_URL.format(self.biz.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['business_id'], self.biz.id)
        self.assertEqual(data['business_slug'], 'qr-biz-test')
        self.assertTrue(data['review_config_exists'])
        self.assertEqual(data['google_place_id'], 'ChIJTest123')
        self.assertEqual(data['google_place_name'], 'Test Place')
        self.assertIn('/r/qr-biz-test/', data['public_url'])

    def test_non_admin_gets_403(self):
        """Regular authenticated user cannot access admin endpoint."""
        regular = _make_regular_user()
        self.client.force_authenticate(user=regular)
        response = self.client.get(BASE_URL.format(self.biz.id))
        self.assertEqual(response.status_code, 403)

    def test_non_qr_reviews_biz_returns_400(self):
        """GET on a non-qr_reviews business returns 400."""
        gestion_biz = Business.objects.create(
            name='Gestion Biz', slug='gestion-biz-x', service_type='gestion',
        )
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(BASE_URL.format(gestion_biz.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn('QR de Reseñas', response.json()['detail'])

    def test_unknown_business_returns_404(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(BASE_URL.format(99999))
        self.assertEqual(response.status_code, 404)


# ── Test: PATCH slug ───────────────────────────────────────────────────────

class AdminQRReviewsSlugPatchTests(APITestCase):

    def setUp(self):
        self.staff = _make_platform_staff()
        self.biz = _make_qr_reviews_biz(slug='old-slug-test')
        ReviewConfig.objects.create(business=self.biz)

    def _patch(self, payload):
        self.client.force_authenticate(user=self.staff)
        return self.client.patch(
            BASE_URL.format(self.biz.id),
            data=payload,
            format='json',
        )

    def test_admin_can_change_valid_slug(self):
        """Admin can change the slug to a valid new value."""
        response = self._patch({'slug': 'mcdonalds'})
        self.assertEqual(response.status_code, 200)
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.slug, 'mcdonalds')
        self.assertEqual(response.json()['business_slug'], 'mcdonalds')
        self.assertIn('/r/mcdonalds/', response.json()['public_url'])

    def test_duplicate_slug_rejected(self):
        """Slug already in use by another business is rejected with 400."""
        Business.objects.create(name='Other', slug='taken-slug', service_type='qr_reviews')
        response = self._patch({'slug': 'taken-slug'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('ya está en uso', response.json()['detail'])

    def test_slug_with_spaces_rejected(self):
        response = self._patch({'slug': 'my slug'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('espacios', response.json()['detail'])

    def test_slug_with_apostrophe_rejected(self):
        response = self._patch({'slug': "mc'donalds"})
        self.assertEqual(response.status_code, 400)

    def test_slug_with_uppercase_rejected(self):
        response = self._patch({'slug': 'McDonalDs'})
        self.assertEqual(response.status_code, 400)

    def test_slug_with_special_chars_rejected(self):
        response = self._patch({'slug': 'slug!@#'})
        self.assertEqual(response.status_code, 400)


# ── Test: PATCH google_place_id ────────────────────────────────────────────

class AdminQRReviewsPlaceIdPatchTests(APITestCase):

    def setUp(self):
        self.staff = _make_platform_staff()
        self.biz = _make_qr_reviews_biz(slug='place-biz-test')

    def _patch(self, payload):
        self.client.force_authenticate(user=self.staff)
        return self.client.patch(
            BASE_URL.format(self.biz.id),
            data=payload,
            format='json',
        )

    def test_admin_can_save_google_place_id(self):
        """Admin can save google_place_id; ReviewConfig is created if missing."""
        response = self._patch({'google_place_id': 'ChIJNewPlace999'})
        self.assertEqual(response.status_code, 200)

        cfg = ReviewConfig.objects.get(business=self.biz)
        self.assertEqual(cfg.google_place_id, 'ChIJNewPlace999')

    def test_google_place_updated_at_stamped(self):
        """google_place_updated_at is set when google_place_id changes."""
        response = self._patch({'google_place_id': 'ChIJStampTest'})
        self.assertEqual(response.status_code, 200)

        cfg = ReviewConfig.objects.get(business=self.biz)
        self.assertIsNotNone(cfg.google_place_updated_at)

    def test_review_config_created_if_missing(self):
        """ReviewConfig is created on first PATCH even if it didn't exist."""
        self.assertFalse(ReviewConfig.objects.filter(business=self.biz).exists())
        response = self._patch({'google_place_id': 'ChIJCreate'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ReviewConfig.objects.filter(business=self.biz).exists())
        self.assertEqual(response.json()['review_config_exists'], True)

    def test_can_save_all_place_fields(self):
        """All supported place fields are saved correctly."""
        payload = {
            'google_place_id': 'ChIJFull',
            'google_place_name': 'Test Business Name',
            'google_place_formatted_address': 'Av. Corrientes 1234, Buenos Aires',
            'google_review_url': 'https://search.google.com/local/writereview?placeid=ChIJFull',
            'custom_redirect_url': 'https://g.page/test-biz/review',
        }
        response = self._patch(payload)
        self.assertEqual(response.status_code, 200)

        cfg = ReviewConfig.objects.get(business=self.biz)
        self.assertEqual(cfg.google_place_id, 'ChIJFull')
        self.assertEqual(cfg.google_place_name, 'Test Business Name')
        self.assertEqual(cfg.google_review_url, payload['google_review_url'])
        self.assertEqual(cfg.custom_redirect_url, payload['custom_redirect_url'])

    def test_non_admin_gets_403_on_patch(self):
        """Non-platform-staff user cannot PATCH."""
        regular = _make_regular_user('other@biz.com')
        self.client.force_authenticate(user=regular)
        response = self.client.patch(
            BASE_URL.format(self.biz.id),
            data={'google_place_id': 'ChIJHack'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)


# ── Test: unknown fields and role edge cases ──────────────────────────────

class AdminQRReviewsPermissionAndFieldTests(APITestCase):

    def setUp(self):
        self.biz = _make_qr_reviews_biz(slug='perm-biz-test')
        ReviewConfig.objects.create(business=self.biz)

    def test_unknown_field_returns_400(self):
        """PATCH with a field outside the allowed set must return 400."""
        staff = _make_platform_staff('sup1@mirubro.com')
        self.client.force_authenticate(user=staff)
        response = self.client.patch(
            BASE_URL.format(self.biz.id),
            data={'enabled': True},  # not in _PATCHABLE_FIELDS
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('allowed_fields', data)
        self.assertIn('enabled', data['detail'])

    def test_mixed_known_and_unknown_fields_returns_400(self):
        """PATCH mixing allowed and forbidden fields still returns 400."""
        staff = _make_platform_staff('sup2@mirubro.com')
        self.client.force_authenticate(user=staff)
        response = self.client.patch(
            BASE_URL.format(self.biz.id),
            data={'slug': 'valid-slug', 'mode': 'smart_filter'},  # mode is forbidden
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_operations_role_can_get(self):
        """Staff with 'operations' role can read config."""
        ops_user = _make_platform_staff('ops@mirubro.com', role='operations')
        self.client.force_authenticate(user=ops_user)
        response = self.client.get(BASE_URL.format(self.biz.id))
        self.assertEqual(response.status_code, 200)

    def test_operations_role_can_patch(self):
        """Staff with 'operations' role can update config."""
        ops_user = _make_platform_staff('ops2@mirubro.com', role='operations')
        self.client.force_authenticate(user=ops_user)
        response = self.client.patch(
            BASE_URL.format(self.biz.id),
            data={'google_place_id': 'ChIJOps'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_support_agent_cannot_get(self):
        """support_agent is NOT allowed — this endpoint is operations-level."""
        support = _make_platform_staff('support@mirubro.com', role='support_agent')
        self.client.force_authenticate(user=support)
        response = self.client.get(BASE_URL.format(self.biz.id))
        self.assertEqual(response.status_code, 403)

    def test_content_admin_cannot_get(self):
        """content_admin has no access to this endpoint."""
        content = _make_platform_staff('content@mirubro.com', role='content_admin')
        self.client.force_authenticate(user=content)
        response = self.client.get(BASE_URL.format(self.biz.id))
        self.assertEqual(response.status_code, 403)

    def test_empty_patch_returns_400(self):
        """PATCH with empty body returns 400."""
        staff = _make_platform_staff('sup3@mirubro.com')
        self.client.force_authenticate(user=staff)
        response = self.client.patch(BASE_URL.format(self.biz.id), data={}, format='json')
        self.assertEqual(response.status_code, 400)

