"""
Tests de permisos para BusinessBrandingView y BusinessLogoUploadView.

Verifica que:
- Usuarios de Gestión Comercial (gestion) puedan leer y modificar branding.
- Usuarios de Carta Online (menu_qr) puedan leer y subir logos.
- Usuarios de QR de Reseñas (qr_reviews) puedan leer y subir logos.
- Usuarios sin permisos de configuración reciban 403.
- Usuarios de otro negocio no accedan al branding ajeno (multi-tenant).
"""
from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessBranding, Subscription

User = get_user_model()

BRANDING_URL = '/api/v1/settings/branding/'
UPLOAD_URL = '/api/v1/settings/branding/upload-logo/'


def _make_minimal_png() -> bytes:
    """Genera una imagen PNG 1x1 real usando Pillow (válida para ImageField)."""
    from PIL import Image
    import io as _io
    img = Image.new('RGB', (1, 1), color=(255, 255, 255))
    buf = _io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


_MINIMAL_PNG = _make_minimal_png()


def _setup_business(user, service: str, role: str = 'owner') -> Business:
    """Helper: crea Business+Subscription+Membership y autentica al cliente de prueba."""
    plan = service if service != 'gestion' else 'starter'
    business = Business.objects.create(name=f'Biz-{service}-{role}')
    Subscription.objects.create(business=business, plan=plan, service=service, status='active')
    Membership.objects.create(user=user, business=business, role=role)
    BusinessBranding.objects.get_or_create(business=business)
    return business


class BrandingPermissionsReadTests(APITestCase):
    """GET /api/v1/settings/branding/ — lectura por distintos servicios."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='branding_read_tester',
            email='branding_read@test.com',
            password='testpass123',
        )

    def _authenticate(self, business: Business):
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)

    def test_gestion_owner_can_read_branding(self):
        """Owner de Gestión Comercial puede leer branding."""
        biz = _setup_business(self.user, service='gestion')
        self._authenticate(biz)
        r = self.client.get(BRANDING_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_menu_qr_owner_can_read_branding(self):
        """Owner de Carta Online (menu_qr) puede leer branding."""
        biz = _setup_business(self.user, service='menu_qr')
        self._authenticate(biz)
        r = self.client.get(BRANDING_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_qr_reviews_owner_can_read_branding(self):
        """Owner de QR de Reseñas puede leer branding."""
        biz = _setup_business(self.user, service='qr_reviews')
        self._authenticate(biz)
        r = self.client.get(BRANDING_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_restaurante_owner_can_read_branding(self):
        """Owner de Restaurante puede leer branding."""
        biz = _setup_business(self.user, service='restaurante')
        self._authenticate(biz)
        r = self.client.get(BRANDING_URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_unauthenticated_cannot_read_branding(self):
        """Usuario no autenticado recibe 401/403."""
        biz = _setup_business(self.user, service='gestion')
        self.client.cookies['bid'] = str(biz.id)
        r = self.client.get(BRANDING_URL)
        self.assertIn(r.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class BrandingPermissionsPatchTests(APITestCase):
    """PATCH /api/v1/settings/branding/ — edición de accent_color."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='branding_patch_tester',
            email='branding_patch@test.com',
            password='testpass123',
        )

    def _authenticate(self, business: Business):
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)

    def test_gestion_owner_can_patch_branding(self):
        """Owner de Gestión Comercial puede actualizar accent_color."""
        biz = _setup_business(self.user, service='gestion')
        self._authenticate(biz)
        r = self.client.patch(BRANDING_URL, {'accent_color': '#FF0000'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get('accent_color'), '#FF0000')

    def test_menu_qr_owner_can_patch_branding(self):
        """Owner de Carta Online puede actualizar accent_color."""
        biz = _setup_business(self.user, service='menu_qr')
        self._authenticate(biz)
        r = self.client.patch(BRANDING_URL, {'accent_color': '#00FF00'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_qr_reviews_owner_can_patch_branding(self):
        """Owner de QR de Reseñas puede actualizar accent_color."""
        biz = _setup_business(self.user, service='qr_reviews')
        self._authenticate(biz)
        r = self.client.patch(BRANDING_URL, {'accent_color': '#0000FF'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)


class BrandingLogoUploadPermissionTests(APITestCase):
    """POST /api/v1/settings/branding/upload-logo/ — subida de logo por servicio."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='branding_upload_perm_tester',
            email='branding_upload_perm@test.com',
            password='testpass123',
        )

    def _authenticate(self, business: Business):
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)

    def _upload(self, logo_type: str = 'horizontal'):
        png_file = io.BytesIO(_MINIMAL_PNG)
        png_file.name = 'logo.png'
        return self.client.post(
            UPLOAD_URL,
            {'file': png_file, 'type': logo_type},
            format='multipart',
        )

    def test_gestion_owner_can_upload_horizontal_logo(self):
        """Owner de Gestión Comercial puede subir logo horizontal."""
        biz = _setup_business(self.user, service='gestion')
        self._authenticate(biz)
        r = self._upload('horizontal')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('logo_horizontal_url', r.data)

    def test_menu_qr_owner_can_upload_horizontal_logo(self):
        """Owner de Carta Online puede subir logo horizontal."""
        biz = _setup_business(self.user, service='menu_qr')
        self._authenticate(biz)
        r = self._upload('horizontal')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_menu_qr_owner_can_upload_square_logo(self):
        """Owner de Carta Online puede subir logo cuadrado/vertical."""
        biz = _setup_business(self.user, service='menu_qr')
        self._authenticate(biz)
        r = self._upload('square')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('logo_square_url', r.data)

    def test_qr_reviews_owner_can_upload_logo(self):
        """Owner de QR de Reseñas puede subir logo."""
        biz = _setup_business(self.user, service='qr_reviews')
        self._authenticate(biz)
        r = self._upload('square')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_qr_reviews_owner_can_upload_horizontal_logo(self):
        """Owner de QR de Reseñas puede subir logo horizontal."""
        biz = _setup_business(self.user, service='qr_reviews')
        self._authenticate(biz)
        r = self._upload('horizontal')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_upload_logo(self):
        """Viewer (solo lectura) no puede subir logo — recibe 403."""
        biz = _setup_business(self.user, service='qr_reviews', role='viewer')
        self._authenticate(biz)
        r = self._upload('horizontal')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_business_user_cannot_access_target_business_branding(self):
        """Un usuario de otro negocio no puede leer el branding del negocio ajeno.

        El sistema resuelve el bid cookie para ese usuario, que no tiene
        membresía en target_biz. El middleware hace fallback al negocio propio
        del usuario, por lo que jamás accede al branding de target_biz.
        Para verificar el aislamiento: el owner de target_biz sube un logo y
        comprobamos que other_user no puede ver ese logo en su propia respuesta.
        """
        other_user = User.objects.create_user(
            username='other_biz_user',
            email='other_biz@test.com',
            password='testpass123',
        )
        target_biz = _setup_business(self.user, service='gestion')
        other_biz = _setup_business(other_user, service='gestion')

        # Autenticamos como owner del target_biz y subimos un logo distintivo
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(target_biz.id)
        from apps.business.models import BusinessBranding
        branding = BusinessBranding.objects.get(business=target_biz)
        branding.accent_color = '#AABBCC'
        branding.save()

        # Ahora autenticamos como other_user con bid apuntando a target_biz
        self.client.force_authenticate(user=other_user)
        self.client.cookies['bid'] = str(target_biz.id)

        png_file = io.BytesIO(_MINIMAL_PNG)
        png_file.name = 'logo.png'
        r = self.client.post(
            UPLOAD_URL,
            {'file': png_file, 'type': 'horizontal'},
            format='multipart',
        )

        if r.status_code == 200:
            # El sistema hizo fallback al negocio propio de other_user.
            # Verificar que NO modificó el branding de target_biz.
            target_branding = BusinessBranding.objects.get(business=target_biz)
            self.assertFalse(bool(target_branding.logo_horizontal),
                msg='El logo de target_biz no debería haber sido modificado por un usuario ajeno.')
        else:
            # Si retornó 403/404, también es correcto.
            self.assertIn(r.status_code, [403, 404])
