"""
Tests para POST /api/v1/reviews/qr-posters/generate-pdf/

Cubre:
- qr_reviews_pro: 200 + application/pdf + body no vacío + Content-Disposition
- qr_reviews (base): 403 con code plan_entitlement_required
- qr_reviews_base: 403
- sin autenticación: 401 / 403
- poster_size inválido: 400
- template_code inválido: 400
- background_color inválido: 400
- main_text demasiado largo: 400
- main_text vacío: 400
- include_logo=true sin logo no rompe generación
- business sin slug: 400
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

User = get_user_model()

URL = '/api/v1/reviews/qr-posters/generate-pdf/'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_payload(**overrides) -> dict:
    """Payload mínimo válido para generar un cartel."""
    base = {
        'poster_size': 'a4_portrait',
        'template_code': 'simple_centered',
        'main_text': 'Escaneá y dejanos tu opinión',
        'subtitle': 'Tu reseña nos ayuda a mejorar',
        'include_logo': False,
        'logo_variant': 'none',
        'background_color': '#FFFFFF',
    }
    base.update(overrides)
    return base


class QrPostersBaseTest(APITestCase):
    """Helpers de fixture para tests de carteles QR."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='qrposters_test_user',
            email='qrposters@test.com',
            password='testpass123',
        )

    def _bootstrap_business(self, plan: str = 'qr_reviews_pro') -> Business:
        """Crea Business + Subscription + Membership y autentica el cliente."""
        business = Business.objects.create(
            name=f'Biz {plan}',
            default_service='qr_reviews',
        )
        Subscription.objects.create(
            business=business,
            plan=plan,
            service='qr_reviews',
            status='active',
        )
        Membership.objects.create(user=self.user, business=business, role='owner')
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def _bootstrap_restaurante(self, plan: str = 'plus') -> Business:
        """
        Crea un Business de Restaurante Inteligente (default_service='restaurante')
        con Subscription de paquete que incluye QR de Reseñas + Carteles.
        """
        business = Business.objects.create(
            name=f'Resto {plan}',
            default_service='restaurante',
        )
        Subscription.objects.create(
            business=business,
            plan=plan,
            service='restaurante',
            status='active',
        )
        Membership.objects.create(user=self.user, business=business, role='owner')
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business


# ── Acceso por plan ───────────────────────────────────────────────────────────

class PlanAccessTests(QrPostersBaseTest):
    """Verifica que solo qr_reviews_pro tiene acceso."""

    def test_pro_plan_returns_200_pdf(self):
        self._bootstrap_business(plan='qr_reviews_pro')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100)

    def test_pro_content_disposition_header(self):
        self._bootstrap_business(plan='qr_reviews_pro')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertIn('cartel-qr-resenas.pdf', response['Content-Disposition'])

    def test_base_plan_returns_403(self):
        self._bootstrap_business(plan='qr_reviews')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'plan_entitlement_required')

    def test_qr_reviews_base_plan_returns_403(self):
        self._bootstrap_business(plan='qr_reviews_base')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'plan_entitlement_required')

    def test_restaurante_inteligente_bundle_returns_200_pdf(self):
        """Restaurante Inteligente (plan 'plus') incluye Carteles → 200 PDF."""
        self._bootstrap_restaurante(plan='plus')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100)

    def test_unauthenticated_returns_403_or_401(self):
        business = Business.objects.create(name='Unauth Biz', default_service='qr_reviews')
        Subscription.objects.create(
            business=business, plan='qr_reviews_pro', service='qr_reviews', status='active',
        )
        self.client.cookies['bid'] = str(business.id)
        # no force_authenticate
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ── Validaciones del serializer ───────────────────────────────────────────────

class SerializerValidationTests(QrPostersBaseTest):
    """Verifica que el serializer rechaza payloads inválidos con 400."""

    def setUp(self):
        super().setUp()
        self._bootstrap_business(plan='qr_reviews_pro')

    def test_invalid_poster_size_returns_400(self):
        response = self.client.post(URL, _minimal_payload(poster_size='xxlarge'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('poster_size', response.data)

    def test_invalid_template_code_returns_400(self):
        response = self.client.post(URL, _minimal_payload(template_code='floating_logo'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('template_code', response.data)

    def test_invalid_background_color_returns_400(self):
        response = self.client.post(URL, _minimal_payload(background_color='rojo'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('background_color', response.data)

    def test_background_color_shorthand_returns_400(self):
        # #FFF es inválido — requiere #RRGGBB exacto
        response = self.client.post(URL, _minimal_payload(background_color='#FFF'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('background_color', response.data)

    def test_main_text_too_long_returns_400(self):
        long_text = 'A' * 81
        response = self.client.post(URL, _minimal_payload(main_text=long_text), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_text', response.data)

    def test_main_text_blank_returns_400(self):
        response = self.client.post(URL, _minimal_payload(main_text='   '), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_text', response.data)

    def test_missing_main_text_returns_400(self):
        payload = _minimal_payload()
        del payload['main_text']
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_text', response.data)

    def test_missing_poster_size_returns_400(self):
        payload = _minimal_payload()
        del payload['poster_size']
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('poster_size', response.data)

    def test_invalid_logo_variant_returns_400(self):
        response = self.client.post(URL, _minimal_payload(logo_variant='vertical'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('logo_variant', response.data)


# ── Generación de PDF ─────────────────────────────────────────────────────────

class PdfGenerationTests(QrPostersBaseTest):
    """Verifica que el PDF se genera correctamente en distintos escenarios."""

    def setUp(self):
        super().setUp()
        self._bootstrap_business(plan='qr_reviews_pro')

    def test_all_valid_poster_sizes_return_200(self):
        valid_sizes = [
            'a4_portrait', 'a4_landscape', 'a5_portrait',
            'half_a4', 'desk_card', 'sticker_square',
        ]
        for size in valid_sizes:
            with self.subTest(size=size):
                response = self.client.post(URL, _minimal_payload(poster_size=size), format='json')
                self.assertEqual(
                    response.status_code, status.HTTP_200_OK,
                    msg=f"poster_size={size} esperaba 200, obtuvo {response.status_code}: {response.data if hasattr(response, 'data') else ''}",
                )
                self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_all_valid_template_codes_return_200(self):
        valid_templates = ['simple_centered', 'qr_left', 'bold_cta']
        for tpl in valid_templates:
            with self.subTest(template=tpl):
                response = self.client.post(URL, _minimal_payload(template_code=tpl), format='json')
                self.assertEqual(
                    response.status_code, status.HTTP_200_OK,
                    msg=f"template_code={tpl} esperaba 200",
                )

    def test_include_logo_true_no_logo_configured_returns_200(self):
        """El PDF se genera aunque no haya logo — no debe lanzar excepción."""
        response = self.client.post(
            URL,
            _minimal_payload(include_logo=True, logo_variant='default'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.content), 100)

    def test_dark_background_color_returns_200(self):
        response = self.client.post(URL, _minimal_payload(background_color='#1E293B'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_subtitle_optional_omitted_returns_200(self):
        payload = _minimal_payload()
        payload.pop('subtitle', None)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_subtitle_empty_string_returns_200(self):
        response = self.client.post(URL, _minimal_payload(subtitle=''), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pdf_starts_with_pdf_magic_bytes(self):
        """Verifica que el body es un PDF real (magic bytes %PDF)."""
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            response.content.startswith(b'%PDF'),
            msg='El contenido no parece un PDF válido',
        )


# ── Tests específicos de layouts (Fase 1B) ────────────────────────────────────

class LayoutTests(QrPostersBaseTest):
    """Verifica comportamientos específicos de cada template."""

    def setUp(self):
        super().setUp()
        self._bootstrap_business(plan='qr_reviews_pro')

    # ── simple_centered ───────────────────────────────────────────────────────

    def test_simple_centered_portrait_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(template_code='simple_centered', poster_size='a4_portrait'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_simple_centered_sticker_square_returns_200(self):
        """El formato cuadrado (10×10 cm) debe funcionar con simple_centered."""
        response = self.client.post(
            URL,
            _minimal_payload(template_code='simple_centered', poster_size='sticker_square'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    # ── qr_left ───────────────────────────────────────────────────────────────

    def test_qr_left_landscape_a4_returns_200(self):
        """qr_left con A4 landscape debe usar el layout de dos columnas."""
        response = self.client.post(
            URL,
            _minimal_payload(template_code='qr_left', poster_size='a4_landscape'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_qr_left_half_a4_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(template_code='qr_left', poster_size='half_a4'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_qr_left_desk_card_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(template_code='qr_left', poster_size='desk_card'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_qr_left_portrait_fallback_returns_200(self):
        """qr_left con A4 portrait debe hacer fallback a simple_centered sin error."""
        response = self.client.post(
            URL,
            _minimal_payload(template_code='qr_left', poster_size='a4_portrait'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_qr_left_sticker_square_fallback_returns_200(self):
        """sticker_square es cuadrado (aspect=1.0 < 1.2) — debe hacer fallback."""
        response = self.client.post(
            URL,
            _minimal_payload(template_code='qr_left', poster_size='sticker_square'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── bold_cta ──────────────────────────────────────────────────────────────

    def test_bold_cta_light_background_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(template_code='bold_cta', background_color='#FFFFFF'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_bold_cta_dark_background_returns_200(self):
        """Con fondo oscuro, el texto debe ser blanco y el QR en caja blanca."""
        response = self.client.post(
            URL,
            _minimal_payload(template_code='bold_cta', background_color='#0F172A'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_bold_cta_saturated_color_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(template_code='bold_cta', background_color='#2563EB'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_bold_cta_all_sizes_return_200(self):
        """bold_cta debe generar PDF válido en todos los tamaños."""
        valid_sizes = [
            'a4_portrait', 'a4_landscape', 'a5_portrait',
            'half_a4', 'desk_card', 'sticker_square',
        ]
        for size in valid_sizes:
            with self.subTest(size=size):
                response = self.client.post(
                    URL,
                    _minimal_payload(template_code='bold_cta', poster_size=size),
                    format='json',
                )
                self.assertEqual(
                    response.status_code, status.HTTP_200_OK,
                    msg=f'bold_cta + {size} esperaba 200',
                )

    def test_bold_cta_no_subtitle_returns_200(self):
        payload = _minimal_payload(template_code='bold_cta')
        payload.pop('subtitle', None)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_bold_cta_no_logo_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(template_code='bold_cta', include_logo=False, logo_variant='none'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── Combinaciones cruzadas ────────────────────────────────────────────────

    def test_all_templates_all_sizes_return_200(self):
        """Matriz completa: 3 templates × 6 tamaños = 18 combinaciones."""
        templates = ['simple_centered', 'qr_left', 'bold_cta']
        sizes = [
            'a4_portrait', 'a4_landscape', 'a5_portrait',
            'half_a4', 'desk_card', 'sticker_square',
        ]
        for tpl in templates:
            for size in sizes:
                with self.subTest(template=tpl, size=size):
                    response = self.client.post(
                        URL,
                        _minimal_payload(template_code=tpl, poster_size=size),
                        format='json',
                    )
                    self.assertEqual(
                        response.status_code, status.HTTP_200_OK,
                        msg=f'{tpl} + {size}: esperaba 200',
                    )
                    self.assertTrue(
                        response.content.startswith(b'%PDF'),
                        msg=f'{tpl} + {size}: bytes no son PDF válido',
                    )


# ── Imagen de fondo (Fase 3A) ─────────────────────────────────────────────────

class BackgroundImageTests(QrPostersBaseTest):
    """
    Verifica generación de PDF con imagen de fondo (background_mode='image').

    Usa SimpleUploadedFile para simular uploads multipart en tests.
    Las imágenes de prueba se generan en memoria con Pillow (ya instalado
    como dependencia de ReportLab).
    """

    def setUp(self):
        super().setUp()
        self._bootstrap_business(plan='qr_reviews_pro')

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_jpg_bytes(w: int = 200, h: int = 300) -> bytes:
        """Genera un JPEG mínimo válido en memoria."""
        import io as _io
        from PIL import Image as _PilImage
        buf = _io.BytesIO()
        _PilImage.new('RGB', (w, h), color=(200, 100, 50)).save(buf, format='JPEG')
        return buf.getvalue()

    @staticmethod
    def _make_png_bytes(w: int = 200, h: int = 300) -> bytes:
        """Genera un PNG mínimo válido en memoria."""
        import io as _io
        from PIL import Image as _PilImage
        buf = _io.BytesIO()
        _PilImage.new('RGB', (w, h), color=(50, 100, 200)).save(buf, format='PNG')
        return buf.getvalue()

    def _post_with_image(
        self,
        image_bytes: bytes,
        filename: str = 'bg.jpg',
        **payload_overrides,
    ):
        """POST multipart con imagen de fondo."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        content_type = 'image/png' if filename.endswith('.png') else 'image/jpeg'
        payload = _minimal_payload(background_mode='image', **payload_overrides)
        bg_file = SimpleUploadedFile(filename, image_bytes, content_type=content_type)
        return self.client.post(
            URL,
            {**payload, 'background_image': bg_file},
            format='multipart',
        )

    # ── Tests ─────────────────────────────────────────────────────────────────

    def test_jpg_background_returns_200_pdf(self):
        """Imagen JPG válida genera PDF 200."""
        response = self._post_with_image(self._make_jpg_bytes(), 'bg.jpg')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_png_background_returns_200_pdf(self):
        """Imagen PNG válida genera PDF 200."""
        response = self._post_with_image(self._make_png_bytes(), 'bg.png')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_image_mode_without_file_returns_400(self):
        """background_mode=image sin archivo devuelve 400."""
        payload = _minimal_payload(background_mode='image')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('background_image', response.data)

    def test_invalid_file_returns_400(self):
        """Archivo que no es imagen devuelve 400."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        payload = _minimal_payload(background_mode='image')
        fake_file = SimpleUploadedFile('bg.jpg', b'not an image at all', content_type='image/jpeg')
        response = self.client.post(
            URL, {**payload, 'background_image': fake_file}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('background_image', response.data)

    def test_oversized_file_returns_400(self):
        """Imagen mayor a 10 MB devuelve 400."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        payload = _minimal_payload(background_mode='image')
        # 10 MB + 1 byte; contenido no importa — el tamaño se verifica primero
        big_file = SimpleUploadedFile(
            'big.jpg', b'\xff\xd8\xff' + b'\x00' * (10 * 1024 * 1024 + 1),
            content_type='image/jpeg',
        )
        response = self.client.post(
            URL, {**payload, 'background_image': big_file}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('background_image', response.data)

    def test_base_plan_with_image_returns_403(self):
        """Plan base con imagen de fondo sigue dando 403."""
        self._bootstrap_business(plan='qr_reviews')
        response = self._post_with_image(self._make_jpg_bytes())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'plan_entitlement_required')

    def test_color_mode_default_unaffected(self):
        """background_mode=color (default) sigue funcionando sin imagen."""
        response = self.client.post(
            URL, _minimal_payload(background_mode='color'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_image_with_all_templates_returns_200(self):
        """Imagen de fondo funciona con los 3 templates."""
        jpg = self._make_jpg_bytes()
        for tpl in ('simple_centered', 'qr_left', 'bold_cta'):
            with self.subTest(template=tpl):
                response = self._post_with_image(jpg, template_code=tpl)
                self.assertEqual(
                    response.status_code, status.HTTP_200_OK,
                    msg=f'{tpl} con imagen esperaba 200',
                )
                self.assertTrue(response.content.startswith(b'%PDF'))


# ── Tipografía y colores de texto (Fase 4A) ───────────────────────────────────

class TypographyTests(QrPostersBaseTest):
    """
    Verifica los campos title_font, main_text_color y subtitle_text_color.

    Cubre:
    - payload sin campos nuevos sigue funcionando (200)
    - title_font=sans_bold/serif_bold/mono_bold generan PDF 200
    - title_font inválido devuelve 400
    - main_text_color válido genera PDF 200
    - subtitle_text_color válido genera PDF 200
    - color inválido devuelve 400
    - imagen de fondo + colores custom genera PDF 200
    """

    def setUp(self):
        super().setUp()
        self._bootstrap_business(plan='qr_reviews_pro')

    # ── title_font ────────────────────────────────────────────────────────────

    def test_default_payload_without_typography_fields_returns_200(self):
        """Payload sin campos nuevos sigue generando PDF 200 (retrocompatibilidad)."""
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_title_font_sans_bold_returns_200(self):
        response = self.client.post(
            URL, _minimal_payload(title_font='sans_bold'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_title_font_serif_bold_returns_200(self):
        response = self.client.post(
            URL, _minimal_payload(title_font='serif_bold'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_title_font_mono_bold_returns_200(self):
        response = self.client.post(
            URL, _minimal_payload(title_font='mono_bold'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_invalid_title_font_returns_400(self):
        response = self.client.post(
            URL, _minimal_payload(title_font='comic_sans'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title_font', response.data)

    # ── main_text_color ───────────────────────────────────────────────────────

    def test_main_text_color_valid_returns_200(self):
        response = self.client.post(
            URL, _minimal_payload(main_text_color='#FF0000'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_subtitle_text_color_valid_returns_200(self):
        response = self.client.post(
            URL, _minimal_payload(subtitle_text_color='#00FF00'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_invalid_main_text_color_returns_400(self):
        response = self.client.post(
            URL, _minimal_payload(main_text_color='red'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_text_color', response.data)

    def test_invalid_subtitle_text_color_returns_400(self):
        response = self.client.post(
            URL, _minimal_payload(subtitle_text_color='#GGGGGG'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('subtitle_text_color', response.data)

    def test_image_background_with_custom_colors_returns_200(self):
        """Imagen de fondo + colores custom + fuente personalizada genera PDF 200."""
        import io as _io
        from PIL import Image as _PilImage
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = _io.BytesIO()
        _PilImage.new('RGB', (200, 300), color=(100, 100, 100)).save(buf, format='JPEG')
        bg_file = SimpleUploadedFile('bg.jpg', buf.getvalue(), content_type='image/jpeg')
        payload = _minimal_payload(
            background_mode='image',
            title_font='serif_bold',
            main_text_color='#FFFFFF',
            subtitle_text_color='#DDDDDD',
        )
        response = self.client.post(
            URL, {**payload, 'background_image': bg_file}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))


class OutlineTests(QrPostersBaseTest):
    """
    Verifica los campos de borde/contorno de letra (Fase 4C):
      main_text_outline_enabled, main_text_outline_color,
      subtitle_text_outline_enabled, subtitle_text_outline_color,
      text_outline_width.

    Cubre:
    - payload sin campos de borde sigue funcionando (retrocompatibilidad)
    - borde activado en título genera PDF 200
    - borde activado en subtítulo genera PDF 200
    - ambos bordes activados generan PDF 200
    - color de borde inválido devuelve 400 (título y subtítulo)
    - ancho de borde inválido devuelve 400
    - borde + imagen de fondo genera PDF 200
    - borde funciona con los 3 templates
    """

    def setUp(self):
        super().setUp()
        self._bootstrap_business(plan='qr_reviews_pro')

    def test_default_payload_without_outline_returns_200(self):
        """Payload sin campos de borde sigue generando PDF 200 (retrocompatibilidad)."""
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_main_text_outline_enabled_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(
                main_text_outline_enabled=True,
                main_text_outline_color='#FFFFFF',
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_subtitle_outline_enabled_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(
                subtitle_text_outline_enabled=True,
                subtitle_text_outline_color='#000000',
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_both_outlines_enabled_returns_200(self):
        response = self.client.post(
            URL,
            _minimal_payload(
                main_text_outline_enabled=True,
                main_text_outline_color='#FF0000',
                subtitle_text_outline_enabled=True,
                subtitle_text_outline_color='#0000FF',
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_invalid_main_outline_color_returns_400(self):
        response = self.client.post(
            URL,
            _minimal_payload(
                main_text_outline_enabled=True,
                main_text_outline_color='black',
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_text_outline_color', response.data)

    def test_invalid_sub_outline_color_returns_400(self):
        response = self.client.post(
            URL,
            _minimal_payload(
                subtitle_text_outline_enabled=True,
                subtitle_text_outline_color='#ZZZZZZ',
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('subtitle_text_outline_color', response.data)

    def test_invalid_outline_width_returns_400(self):
        response = self.client.post(
            URL,
            _minimal_payload(text_outline_width=1.5),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('text_outline_width', response.data)

    def test_outline_with_image_background_returns_200(self):
        """Borde + imagen de fondo genera PDF 200."""
        import io as _io
        from PIL import Image as _PilImage
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = _io.BytesIO()
        _PilImage.new('RGB', (200, 300), color=(30, 30, 30)).save(buf, format='JPEG')
        bg_file = SimpleUploadedFile('bg.jpg', buf.getvalue(), content_type='image/jpeg')
        payload = _minimal_payload(
            background_mode='image',
            main_text_outline_enabled=True,
            main_text_outline_color='#FFFFFF',
            subtitle_text_outline_enabled=True,
            subtitle_text_outline_color='#FFFFFF',
        )
        response = self.client.post(
            URL, {**payload, 'background_image': bg_file}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_outline_with_all_templates_returns_200(self):
        """Borde de letra funciona con los 3 templates."""
        for tpl in ('simple_centered', 'qr_left', 'bold_cta'):
            with self.subTest(template=tpl):
                response = self.client.post(
                    URL,
                    _minimal_payload(
                        template_code=tpl,
                        main_text_outline_enabled=True,
                        main_text_outline_color='#000000',
                    ),
                    format='json',
                )
                self.assertEqual(
                    response.status_code, status.HTTP_200_OK,
                    msg=f'{tpl} con borde esperaba 200',
                )
                self.assertTrue(response.content.startswith(b'%PDF'))


# ── qr_scale / text_spacing / uppercase_mode ─────────────────────────────────

class NewFieldsTests(QrPostersBaseTest):
    """Tests para los 3 campos nuevos: qr_scale, text_spacing, uppercase_mode."""

    def setUp(self):
        super().setUp()
        self._bootstrap_business(plan='qr_reviews_pro')

    # ── Retrocompatibilidad ────────────────────────────────────────────────────

    def test_payload_without_new_fields_returns_200(self):
        """Payload sin qr_scale/text_spacing/uppercase_mode sigue generando PDF."""
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    # ── qr_scale ──────────────────────────────────────────────────────────────

    def test_qr_scale_small_returns_200(self):
        response = self.client.post(URL, _minimal_payload(qr_scale='small'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_qr_scale_medium_returns_200(self):
        response = self.client.post(URL, _minimal_payload(qr_scale='medium'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_qr_scale_large_returns_200(self):
        response = self.client.post(URL, _minimal_payload(qr_scale='large'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_qr_scale_invalid_returns_400(self):
        response = self.client.post(URL, _minimal_payload(qr_scale='xlarge'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── text_spacing ──────────────────────────────────────────────────────────

    def test_text_spacing_tight_returns_200(self):
        response = self.client.post(URL, _minimal_payload(text_spacing='tight'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_text_spacing_normal_returns_200(self):
        response = self.client.post(URL, _minimal_payload(text_spacing='normal'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_text_spacing_loose_returns_200(self):
        response = self.client.post(URL, _minimal_payload(text_spacing='loose'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_text_spacing_invalid_returns_400(self):
        response = self.client.post(URL, _minimal_payload(text_spacing='wide'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── uppercase_mode ────────────────────────────────────────────────────────

    def test_uppercase_none_returns_200(self):
        response = self.client.post(URL, _minimal_payload(uppercase_mode='none'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_uppercase_title_returns_200(self):
        response = self.client.post(URL, _minimal_payload(uppercase_mode='title'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_uppercase_all_returns_200(self):
        response = self.client.post(URL, _minimal_payload(uppercase_mode='all'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_uppercase_invalid_returns_400(self):
        response = self.client.post(URL, _minimal_payload(uppercase_mode='both'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Combinaciones ─────────────────────────────────────────────────────────

    def test_combination_qr_scale_spacing_uppercase_returns_200(self):
        """Los 3 campos nuevos juntos generan PDF sin error."""
        response = self.client.post(
            URL,
            _minimal_payload(
                qr_scale='large',
                text_spacing='loose',
                uppercase_mode='all',
                template_code='bold_cta',
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_combination_with_background_image_returns_200(self):
        """Campos nuevos combinados con imagen de fondo generan PDF."""
        import io as _io
        from PIL import Image as _PilImage
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = _io.BytesIO()
        _PilImage.new('RGB', (400, 600), color=(100, 150, 200)).save(buf, format='PNG')
        bg_file = SimpleUploadedFile('bg.png', buf.getvalue(), content_type='image/png')
        payload = _minimal_payload(
            background_mode='image',
            qr_scale='large',
            text_spacing='loose',
            uppercase_mode='title',
        )
        response = self.client.post(
            URL, {**payload, 'background_image': bg_file}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_new_fields_with_all_templates_returns_200(self):
        """Campos nuevos funcionan en los 3 templates."""
        for tpl in ('simple_centered', 'qr_left', 'bold_cta'):
            with self.subTest(template=tpl):
                response = self.client.post(
                    URL,
                    _minimal_payload(
                        template_code=tpl,
                        qr_scale='small',
                        text_spacing='tight',
                        uppercase_mode='title',
                    ),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK,
                                 msg=f'{tpl} con campos nuevos esperaba 200')
                self.assertTrue(response.content.startswith(b'%PDF'))

