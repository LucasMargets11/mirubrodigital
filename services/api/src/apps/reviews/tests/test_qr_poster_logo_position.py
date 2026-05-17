"""
Tests para los nuevos campos logo_position y logo_margin_mm en
POST /api/v1/reviews/qr-posters/generate-pdf/

Cubre:
- Cada posición válida genera PDF sin error (200 + application/pdf)
- logo_variant='none' genera PDF sin logo (200 + no error)
- logo_margin_mm dentro del rango válido acepta (0, 8, 40)
- logo_margin_mm fuera del rango (> 40) devuelve 400
- logo_position inválido devuelve 400
- Backward compat: ausencia de logo_position/logo_margin_mm no rompe
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

User = get_user_model()

URL = '/api/v1/reviews/qr-posters/generate-pdf/'


def _minimal_payload(**overrides) -> dict:
    base = {
        'poster_size': 'a4_portrait',
        'template_code': 'simple_centered',
        'main_text': 'Escaneá y dejanos tu reseña',
        'include_logo': False,
        'logo_variant': 'none',
        'background_color': '#FFFFFF',
    }
    base.update(overrides)
    return base


class QrPosterLogoPositionBaseTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='logo_pos_test_user',
            email='logo_pos@test.com',
            password='testpass123',
        )
        self.business = Business.objects.create(
            name='Logo Position Test Biz',
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


class LogoPositionValidationTests(QrPosterLogoPositionBaseTest):
    """Valida las reglas de logo_position y logo_margin_mm en el serializer."""

    def test_invalid_logo_position_returns_400(self):
        response = self.client.post(
            URL,
            _minimal_payload(logo_position='diagonal-super'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logo_margin_mm_above_40_returns_400(self):
        response = self.client.post(
            URL,
            _minimal_payload(logo_margin_mm=41.0),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logo_margin_mm_below_0_returns_400(self):
        response = self.client.post(
            URL,
            _minimal_payload(logo_margin_mm=-1.0),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logo_margin_mm_valid_range_boundary_0(self):
        response = self.client.post(
            URL,
            _minimal_payload(logo_margin_mm=0.0),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_logo_margin_mm_valid_range_boundary_40(self):
        response = self.client.post(
            URL,
            _minimal_payload(logo_margin_mm=40.0),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_logo_variant_none_generates_pdf_without_error(self):
        response = self.client.post(
            URL,
            _minimal_payload(logo_variant='none', include_logo=False),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_backward_compat_no_position_or_margin_fields(self):
        """Diseños sin logo_position/logo_margin_mm siguen funcionando (defaults)."""
        payload = {
            'poster_size': 'a4_portrait',
            'template_code': 'simple_centered',
            'main_text': 'Sin posición ni margen',
            'include_logo': False,
            'logo_variant': 'none',
            'background_color': '#FFFFFF',
            # Deliberadamente sin logo_position ni logo_margin_mm
        }
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')


VALID_POSITIONS = [
    'top-left', 'top-center', 'top-right',
    'bottom-left', 'bottom-center', 'bottom-right',
    'middle-left', 'middle-right',
]


class AllLogoPositionsGeneratePdfTests(QrPosterLogoPositionBaseTest):
    """Verifica que cada posición válida genera un PDF correcto (sin logo real en tests)."""

    def _test_position(self, position: str):
        response = self.client.post(
            URL,
            _minimal_payload(
                logo_variant='none',
                include_logo=False,
                logo_position=position,
                logo_margin_mm=8.0,
            ),
            format='json',
        )
        # PDF responses are plain HttpResponse (no .data); error responses are DRF Response
        detail = getattr(response, 'data', response.content[:120])
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            msg=f'position={position} devolvió {response.status_code}: {detail}',
        )
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_all_valid_positions(self):
        for pos in VALID_POSITIONS:
            with self.subTest(position=pos):
                self._test_position(pos)
