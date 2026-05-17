"""
Tests para la validación de tamaño en MenuLogoUploadView.

Cubre:
- Archivo > 5 MB → 400 con mensaje "El archivo supera el límite de 5 MB."
- Archivo válido < 5 MB → 200 con URL del logo
- Archivo exactamente en el límite (5 MB exactos) → no rechazado por tamaño
"""
from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

User = get_user_model()

URL = '/api/v1/menu/public/logo/'

def _make_minimal_png() -> bytes:
    """Genera una imagen PNG 1x1 real usando Pillow (valida para ImageField)."""
    from PIL import Image
    import io as _io
    img = Image.new('RGB', (1, 1), color=(255, 255, 255))
    buf = _io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()

_MINIMAL_PNG = _make_minimal_png()


class MenuLogoUploadSizeTests(APITestCase):
    """Valida que MenuLogoUploadView rechace archivos mayores a 5 MB."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='menu_logo_tester',
            email='menu_logo@test.com',
            password='testpass123',
        )

    def _bootstrap_business(self) -> Business:
        """Crea Business + Subscription activa + Membership owner y autentica.

        Usa service='menu_qr' para que el owner tenga 'manage_menu_branding'.
        """
        business = Business.objects.create(
            name='Biz Menu Logo Test',
            default_service='menu_qr',
        )
        Subscription.objects.create(
            business=business,
            plan='menu_qr',
            service='menu_qr',
            status='active',
        )
        Membership.objects.create(user=self.user, business=business, role='owner')
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    # ── Tests ─────────────────────────────────────────────────────────────────

    def test_oversized_file_returns_400(self):
        """Un archivo de 5 MB + 1 byte debe ser rechazado con 400."""
        self._bootstrap_business()

        oversized_content = b'\x00' * (5 * 1024 * 1024 + 1)
        oversized_file = io.BytesIO(oversized_content)
        oversized_file.name = 'logo.png'

        response = self.client.post(
            URL,
            {'file': oversized_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('error'), 'El archivo supera el límite de 5 MB.')

    def test_valid_file_under_limit_returns_200(self):
        """Un logo PNG pequeño debe procesarse correctamente."""
        self._bootstrap_business()

        valid_file = io.BytesIO(_MINIMAL_PNG)
        valid_file.name = 'logo.png'

        response = self.client.post(
            URL,
            {'file': valid_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('url', response.data)

    def test_file_at_exact_limit_is_allowed(self):
        """Un archivo de exactamente 5 MB no debe ser rechazado por tamaño."""
        self._bootstrap_business()

        exact_content = b'\x00' * (5 * 1024 * 1024)
        exact_file = io.BytesIO(exact_content)
        exact_file.name = 'logo.png'

        response = self.client.post(
            URL,
            {'file': exact_file},
            format='multipart',
        )

        self.assertNotEqual(
            response.data.get('error'),
            'El archivo supera el límite de 5 MB.',
            msg='Un archivo de exactamente 5 MB no debe ser rechazado por tamaño.',
        )
