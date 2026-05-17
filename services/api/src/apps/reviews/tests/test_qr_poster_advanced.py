"""
Tests de personalización avanzada del QR para carteles de reseñas PRO.

Cubre:
- qr_size_mm: valor personalizado genera PDF sin error
- qr_size_mm fuera de rango: 400
- qr_vertical_align top/center/bottom: genera PDF sin error
- qr_vertical_align inválido: 400
- qr_bottom_offset_mm: valor personalizado genera PDF sin error
- qr_bottom_offset_mm fuera de rango: 400
- backward compat: payload sin campos nuevos usa qr_scale (small/medium/large)
- PosterPayloadSerializer acepta y valida los nuevos campos en diseños guardados
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.reviews.qr_poster_serializer import GenerateQrPosterSerializer
from apps.reviews.qr_poster_design_serializer import PosterPayloadSerializer

User = get_user_model()

URL = '/api/v1/reviews/qr-posters/generate-pdf/'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_payload(**overrides) -> dict:
    base = {
        'poster_size': 'a4_portrait',
        'template_code': 'simple_centered',
        'main_text': 'Escaneá y dejanos tu opinión',
        'subtitle': '',
        'include_logo': False,
        'logo_variant': 'none',
        'background_color': '#FFFFFF',
    }
    base.update(overrides)
    return base


class QrPosterAdvancedBaseTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='qrposter_adv_user',
            email='qrposter_adv@test.com',
            password='testpass123',
        )
        self.business = Business.objects.create(
            name='Biz Advanced QR',
            default_service='qr_reviews',
        )
        Subscription.objects.create(
            business=self.business,
            plan='qr_reviews_pro',
            service='qr_reviews',
            status='active',
        )
        Membership.objects.create(user=self.user, business=self.business, role='owner')
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(self.business.id)


# ── Serializer unit tests (sin BD) ───────────────────────────────────────────

class GenerateSerializerValidationTests(APITestCase):
    """Valida los nuevos campos directamente sobre el serializer."""

    def _base(self, **overrides) -> dict:
        d = {
            'poster_size': 'a4_portrait',
            'template_code': 'simple_centered',
            'main_text': 'Test',
        }
        d.update(overrides)
        return d

    def test_qr_size_mm_valid(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_size_mm=48))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['qr_size_mm'], 48.0)

    def test_qr_size_mm_min_edge(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_size_mm=22))
        self.assertTrue(s.is_valid(), s.errors)

    def test_qr_size_mm_max_edge(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_size_mm=90))
        self.assertTrue(s.is_valid(), s.errors)

    def test_qr_size_mm_below_min(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_size_mm=21))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_size_mm', s.errors)

    def test_qr_size_mm_above_max(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_size_mm=91))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_size_mm', s.errors)

    def test_qr_size_mm_null_allowed(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_size_mm=None))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertIsNone(s.validated_data.get('qr_size_mm'))

    def test_qr_vertical_align_valid_values(self):
        for val in ('top', 'center', 'bottom'):
            s = GenerateQrPosterSerializer(data=self._base(qr_vertical_align=val))
            self.assertTrue(s.is_valid(), f'align={val}: {s.errors}')

    def test_qr_vertical_align_invalid(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_vertical_align='left'))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_vertical_align', s.errors)

    def test_qr_vertical_align_default_is_center(self):
        s = GenerateQrPosterSerializer(data=self._base())
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data.get('qr_vertical_align'), 'center')

    def test_qr_bottom_offset_mm_valid(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_bottom_offset_mm=16))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['qr_bottom_offset_mm'], 16.0)

    def test_qr_bottom_offset_mm_zero(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_bottom_offset_mm=0))
        self.assertTrue(s.is_valid(), s.errors)

    def test_qr_bottom_offset_mm_max(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_bottom_offset_mm=80))
        self.assertTrue(s.is_valid(), s.errors)

    def test_qr_bottom_offset_mm_above_max(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_bottom_offset_mm=81))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_bottom_offset_mm', s.errors)

    def test_qr_bottom_offset_mm_negative(self):
        s = GenerateQrPosterSerializer(data=self._base(qr_bottom_offset_mm=-1))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_bottom_offset_mm', s.errors)


# ── Integration tests (generación real de PDF) ────────────────────────────────

class QrSizeMmPdfTests(QrPosterAdvancedBaseTest):

    def test_custom_qr_size_mm_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_size_mm=55), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(len(resp.content) > 0)

    def test_small_qr_size_mm_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_size_mm=22), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_large_qr_size_mm_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_size_mm=90), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_qr_size_mm_out_of_range_returns_400(self):
        resp = self.client.post(URL, _minimal_payload(qr_size_mm=5), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_qr_size_mm_too_large_returns_400(self):
        resp = self.client.post(URL, _minimal_payload(qr_size_mm=100), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class QrVerticalAlignPdfTests(QrPosterAdvancedBaseTest):

    def test_align_top_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_vertical_align='top'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_align_center_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_vertical_align='center'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_align_bottom_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_vertical_align='bottom'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_invalid_align_returns_400(self):
        resp = self.client.post(URL, _minimal_payload(qr_vertical_align='middle'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_align_bottom_with_offset_generates_pdf(self):
        resp = self.client.post(
            URL,
            _minimal_payload(qr_vertical_align='bottom', qr_bottom_offset_mm=20),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class QrBottomOffsetPdfTests(QrPosterAdvancedBaseTest):

    def test_offset_zero_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_bottom_offset_mm=0), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_offset_max_generates_pdf(self):
        resp = self.client.post(URL, _minimal_payload(qr_bottom_offset_mm=80), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_offset_out_of_range_returns_400(self):
        resp = self.client.post(URL, _minimal_payload(qr_bottom_offset_mm=90), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class BackwardCompatTests(QrPosterAdvancedBaseTest):
    """Payloads legados sin campos nuevos deben seguir funcionando."""

    def test_legacy_payload_no_new_fields(self):
        payload = {
            'poster_size': 'a4_portrait',
            'template_code': 'simple_centered',
            'main_text': 'Texto legacy',
            'include_logo': False,
            'background_color': '#FFFFFF',
            'qr_scale': 'large',
        }
        resp = self.client.post(URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_legacy_qr_scale_small(self):
        resp = self.client.post(URL, _minimal_payload(qr_scale='small'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_legacy_qr_scale_medium(self):
        resp = self.client.post(URL, _minimal_payload(qr_scale='medium'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_qr_size_mm_takes_precedence_over_scale(self):
        """Cuando qr_size_mm está presente, debe ignorarse qr_scale."""
        resp = self.client.post(
            URL,
            _minimal_payload(qr_size_mm=32, qr_scale='large'),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_bold_cta_template_with_new_params(self):
        resp = self.client.post(
            URL,
            _minimal_payload(
                template_code='bold_cta',
                qr_size_mm=48,
                qr_vertical_align='bottom',
                qr_bottom_offset_mm=12,
            ),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_qr_left_template_with_new_params(self):
        resp = self.client.post(
            URL,
            _minimal_payload(
                poster_size='a4_landscape',
                template_code='qr_left',
                qr_size_mm=60,
                qr_vertical_align='center',
            ),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ── PosterPayloadSerializer (diseños guardados) ───────────────────────────────

class PosterPayloadSerializerTests(APITestCase):
    """Tests unitarios del serializer de payload para diseños guardados."""

    def _base(self, **overrides) -> dict:
        d = {
            'poster_size': 'a4_portrait',
            'template_code': 'simple_centered',
            'main_text': 'Test',
            'background_color': '#FFFFFF',
        }
        d.update(overrides)
        return d

    def test_new_fields_accepted(self):
        s = PosterPayloadSerializer(data=self._base(
            qr_size_mm=48,
            qr_vertical_align='bottom',
            qr_bottom_offset_mm=16,
        ))
        self.assertTrue(s.is_valid(), s.errors)

    def test_legacy_payload_still_valid(self):
        s = PosterPayloadSerializer(data=self._base(qr_scale='medium'))
        self.assertTrue(s.is_valid(), s.errors)

    def test_invalid_qr_vertical_align_rejected(self):
        s = PosterPayloadSerializer(data=self._base(qr_vertical_align='diagonal'))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_vertical_align', s.errors)

    def test_qr_size_mm_out_of_range_rejected(self):
        s = PosterPayloadSerializer(data=self._base(qr_size_mm=10))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_size_mm', s.errors)

    def test_qr_bottom_offset_mm_out_of_range_rejected(self):
        s = PosterPayloadSerializer(data=self._base(qr_bottom_offset_mm=100))
        self.assertFalse(s.is_valid())
        self.assertIn('qr_bottom_offset_mm', s.errors)


# ── Unit tests for _resolve_qr_size_pt() ─────────────────────────────────────

from django.test import TestCase  # noqa: E402
from reportlab.lib.units import mm as _mm
from apps.reviews.qr_posters import _resolve_qr_size_pt, MIN_QR_SIZE  # noqa: E402


class ResolveQrSizePtTests(TestCase):
    """Pure-function unit tests for _resolve_qr_size_pt()."""

    def test_22mm_returns_22mm(self):
        result = _resolve_qr_size_pt(22.0, 'medium')
        self.assertAlmostEqual(result, 22.0 * _mm, places=2)

    def test_90mm_returns_90mm(self):
        result = _resolve_qr_size_pt(90.0, 'medium')
        self.assertAlmostEqual(result, 90.0 * _mm, places=2)

    def test_qr_size_mm_wins_over_large_scale(self):
        result = _resolve_qr_size_pt(22.0, 'large')
        self.assertAlmostEqual(result, 22.0 * _mm, places=2)

    def test_none_falls_back_to_small_scale(self):
        result = _resolve_qr_size_pt(None, 'small')
        self.assertAlmostEqual(result, 32.0 * _mm, places=2)

    def test_none_falls_back_to_medium_scale(self):
        result = _resolve_qr_size_pt(None, 'medium')
        self.assertAlmostEqual(result, 48.0 * _mm, places=2)

    def test_none_falls_back_to_large_scale(self):
        result = _resolve_qr_size_pt(None, 'large')
        self.assertAlmostEqual(result, 68.0 * _mm, places=2)

    def test_below_min_clamped_to_min_qr_size(self):
        result = _resolve_qr_size_pt(10.0, 'medium')
        self.assertGreaterEqual(result, MIN_QR_SIZE)

    def test_above_max_clamped_to_90mm(self):
        result = _resolve_qr_size_pt(200.0, 'medium')
        self.assertAlmostEqual(result, 90.0 * _mm, places=2)

    def test_unknown_scale_falls_back_to_default(self):
        result = _resolve_qr_size_pt(None, 'unknown_scale')
        self.assertAlmostEqual(result, 48.0 * _mm, places=2)


# ── Unit tests for resolve_poster_font() ─────────────────────────────────────

import pytest  # noqa: E402
from apps.reviews.qr_posters import resolve_poster_font, FONT_BOLD  # noqa: E402


class ResolvePosterFontTests(TestCase):
    """Pure-function unit tests for resolve_poster_font()."""

    def test_cinzel_regular(self):
        name = resolve_poster_font('cinzel', 'regular')
        self.assertEqual(name, 'Cinzel-Regular')

    def test_cinzel_bold(self):
        name = resolve_poster_font('cinzel', 'bold')
        self.assertEqual(name, 'Cinzel-Bold')

    def test_cinzel_black(self):
        name = resolve_poster_font('cinzel', 'black')
        self.assertEqual(name, 'Cinzel-Black')

    def test_montserrat_bold(self):
        name = resolve_poster_font('montserrat', 'bold')
        self.assertEqual(name, 'Montserrat-Bold')

    def test_oswald_black_normalizes_to_bold(self):
        # Oswald has no Black weight; should fall back to bold.
        name = resolve_poster_font('oswald', 'black')
        self.assertEqual(name, 'Oswald-Bold')

    def test_cormorant_garamond_black_normalizes_to_bold(self):
        name = resolve_poster_font('cormorant_garamond', 'black')
        self.assertEqual(name, 'CormorantGaramond-Bold')

    def test_libre_baskerville_black_normalizes_to_bold(self):
        name = resolve_poster_font('libre_baskerville', 'black')
        self.assertEqual(name, 'LibreBaskerville-Bold')

    def test_unknown_family_returns_helvetica_bold(self):
        name = resolve_poster_font('unknown_family', 'bold')
        self.assertEqual(name, FONT_BOLD)

    def test_none_family_returns_helvetica_bold(self):
        name = resolve_poster_font(None, 'bold')
        self.assertEqual(name, FONT_BOLD)

    def test_none_weight_defaults_to_bold(self):
        name = resolve_poster_font('montserrat', None)
        self.assertEqual(name, 'Montserrat-Bold')

    def test_unknown_weight_normalizes_to_bold(self):
        name = resolve_poster_font('poppins', 'ultralight')
        self.assertEqual(name, 'Poppins-Bold')

    def test_all_families_resolve_without_error(self):
        families = [
            'cinzel', 'montserrat', 'poppins', 'raleway', 'playfair_display',
            'work_sans', 'lato', 'oswald', 'cormorant_garamond', 'libre_baskerville',
        ]
        for fam in families:
            with self.subTest(family=fam):
                name = resolve_poster_font(fam, 'bold')
                self.assertNotEqual(name, FONT_BOLD, f'{fam}/bold should not fall back')


# ── Serializer unit tests for font_family / font_weight ──────────────────────

class FontFieldsSerializerTests(APITestCase):
    """Validates font_family and font_weight in both generate and design serializers."""

    def _base(self, **overrides) -> dict:
        d = {
            'poster_size': 'a4_portrait',
            'template_code': 'simple_centered',
            'main_text': 'Test',
        }
        d.update(overrides)
        return d

    # GenerateQrPosterSerializer

    def test_font_family_valid(self):
        s = GenerateQrPosterSerializer(data=self._base(font_family='cinzel'))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['font_family'], 'cinzel')

    def test_font_weight_valid(self):
        s = GenerateQrPosterSerializer(data=self._base(font_family='montserrat', font_weight='black'))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['font_weight'], 'black')

    def test_font_family_invalid_rejected(self):
        s = GenerateQrPosterSerializer(data=self._base(font_family='comic_sans'))
        self.assertFalse(s.is_valid())
        self.assertIn('font_family', s.errors)

    def test_font_weight_invalid_rejected(self):
        s = GenerateQrPosterSerializer(data=self._base(font_weight='ultralight'))
        self.assertFalse(s.is_valid())
        self.assertIn('font_weight', s.errors)

    def test_font_family_null_allowed(self):
        s = GenerateQrPosterSerializer(data=self._base(font_family=None))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertIsNone(s.validated_data.get('font_family'))

    def test_font_weight_null_allowed(self):
        s = GenerateQrPosterSerializer(data=self._base(font_weight=None))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertIsNone(s.validated_data.get('font_weight'))

    def test_omitting_font_fields_defaults_to_none(self):
        s = GenerateQrPosterSerializer(data=self._base())
        self.assertTrue(s.is_valid(), s.errors)
        self.assertIsNone(s.validated_data.get('font_family'))
        self.assertIsNone(s.validated_data.get('font_weight'))

    # PosterPayloadSerializer

    def test_design_serializer_accepts_font_fields(self):
        s = PosterPayloadSerializer(data={
            'poster_size': 'a4_portrait',
            'template_code': 'simple_centered',
            'main_text': 'Test',
            'background_color': '#FFFFFF',
            'font_family': 'playfair_display',
            'font_weight': 'bold',
        })
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['font_family'], 'playfair_display')

    def test_design_serializer_invalid_family_rejected(self):
        s = PosterPayloadSerializer(data={
            'poster_size': 'a4_portrait',
            'template_code': 'simple_centered',
            'main_text': 'Test',
            'background_color': '#FFFFFF',
            'font_family': 'not_a_font',
        })
        self.assertFalse(s.is_valid())
        self.assertIn('font_family', s.errors)


# ── Integration tests: font_family → PDF generation ──────────────────────────

class FontFamilyPdfTests(QrPosterAdvancedBaseTest):
    """End-to-end: each font family generates a valid PDF."""

    def test_cinzel_black_generates_pdf(self):
        resp = self.client.post(
            URL,
            _minimal_payload(font_family='cinzel', font_weight='black'),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content[:4] == b'%PDF')

    def test_montserrat_regular_generates_pdf(self):
        resp = self.client.post(
            URL,
            _minimal_payload(font_family='montserrat', font_weight='regular'),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_oswald_black_request_generates_pdf(self):
        # Oswald has no Black; backend normalizes to Bold → still returns valid PDF.
        resp = self.client.post(
            URL,
            _minimal_payload(font_family='oswald', font_weight='black'),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_old_design_no_font_family_backward_compat(self):
        # Payload without font_family uses legacy title_font system.
        resp = self.client.post(
            URL,
            _minimal_payload(title_font='serif_bold'),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_invalid_font_family_returns_400(self):
        resp = self.client.post(
            URL,
            _minimal_payload(font_family='papyrus'),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_all_families_bold_generate_pdf(self):
        families = [
            'cinzel', 'montserrat', 'poppins', 'raleway', 'playfair_display',
            'work_sans', 'lato', 'oswald', 'cormorant_garamond', 'libre_baskerville',
        ]
        for fam in families:
            with self.subTest(family=fam):
                resp = self.client.post(
                    URL,
                    _minimal_payload(font_family=fam, font_weight='bold'),
                    format='json',
                )
                self.assertEqual(
                    resp.status_code, status.HTTP_200_OK,
                    f'{fam}/bold returned {resp.status_code}: {resp.content[:200]}',
                )
