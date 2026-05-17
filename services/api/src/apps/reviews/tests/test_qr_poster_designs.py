"""
Tests para los endpoints de historial de diseños QR de Reseñas PRO.

GET/POST  /api/v1/reviews/qr-posters/designs/
GET/PATCH/DELETE /api/v1/reviews/qr-posters/designs/<uuid>/

Cobertura:
 1. PRO lista diseños vacíos → 200
 2. Plan básico lista diseños → 403
 3. Crear diseño PRO sin imagen → 201
 4. Crear diseño PRO con imagen → 201
 5. Sexto diseño → 400 design_limit_reached
 6. PATCH actualiza name → 200
 7. PATCH actualiza payload → 200
 8. PATCH reemplaza imagen → 200
 9. PATCH a background_mode=color limpia imagen
10. DELETE elimina diseño → 204
11. Otro tenant no puede ver diseño → 404
12. Payload inválido → 400
13. Sin auth → 401/403
"""
from __future__ import annotations

import io
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.reviews.models import ReviewQrPosterDesign

User = get_user_model()

LIST_URL = '/api/v1/reviews/qr-posters/designs/'


def _detail_url(design_id) -> str:
    return f'/api/v1/reviews/qr-posters/designs/{design_id}/'


# ── Minimal valid payload ──────────────────────────────────────────────────────

def _minimal_payload(**overrides) -> dict:
    base = {
        'poster_size': 'a4_portrait',
        'template_code': 'simple_centered',
        'main_text': 'Escaneá y dejanos tu opinión',
        'subtitle': 'Tu reseña nos ayuda a mejorar',
        'include_logo': False,
        'logo_variant': 'none',
        'background_color': '#FFFFFF',
        'background_mode': 'color',
    }
    base.update(overrides)
    return base


def _tiny_png() -> bytes:
    """Returns a valid PNG (200×300) usable by ReportLab when rendering PDFs."""
    import io as _io
    from PIL import Image as _PilImage
    buf = _io.BytesIO()
    _PilImage.new('RGB', (200, 300), color=(200, 100, 50)).save(buf, format='PNG')
    return buf.getvalue()


# ── Base test class ────────────────────────────────────────────────────────────

class DesignBaseTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='design_test_user',
            email='design_test@test.com',
            password='testpass123',
        )

    def _bootstrap_business(self, plan: str = 'qr_reviews_pro') -> Business:
        business = Business.objects.create(
            name=f'Biz {plan}',
            slug=f'biz-{plan.replace("_", "-")}',
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

    def _create_design(self, business, name='Mi diseño', **payload_overrides) -> ReviewQrPosterDesign:
        payload = _minimal_payload(**payload_overrides)
        return ReviewQrPosterDesign.objects.create(
            business=business,
            name=name,
            payload=payload,
            created_by=self.user,
            updated_by=self.user,
        )


# ── Test 1: PRO lista diseños vacíos → 200 ────────────────────────────────────

class ListDesignsProTest(DesignBaseTest):

    def test_pro_list_empty(self):
        self._bootstrap_business('qr_reviews_pro')
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 0)
        self.assertEqual(resp.data['limit'], 5)
        self.assertEqual(resp.data['results'], [])


# ── Test 2: Plan básico lista diseños → 403 ───────────────────────────────────

class ListDesignsBasicPlanTest(DesignBaseTest):

    def test_base_plan_returns_403(self):
        self._bootstrap_business('qr_reviews')
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_qr_reviews_base_plan_returns_403(self):
        self._bootstrap_business('qr_reviews_base')
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ── Test 3: Crear diseño PRO sin imagen → 201 ─────────────────────────────────

class CreateDesignNoImageTest(DesignBaseTest):

    def test_create_design_returns_201(self):
        self._bootstrap_business('qr_reviews_pro')
        data = {
            'name': 'Cartel principal',
            'payload': _minimal_payload(),
        }
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', resp.data)
        self.assertEqual(resp.data['name'], 'Cartel principal')
        self.assertIsNone(resp.data['background_image_url'])
        self.assertEqual(ReviewQrPosterDesign.objects.count(), 1)

    def test_create_design_list_shows_one(self):
        business = self._bootstrap_business('qr_reviews_pro')
        self._create_design(business)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(len(resp.data['results']), 1)


# ── Test 4: Crear diseño PRO con imagen → 201 ─────────────────────────────────

class CreateDesignWithImageTest(DesignBaseTest):

    def test_create_design_with_image_returns_201(self):
        self._bootstrap_business('qr_reviews_pro')
        payload = _minimal_payload(background_mode='image')
        image_file = SimpleUploadedFile('bg.png', _tiny_png(), content_type='image/png')
        resp = self.client.post(
            LIST_URL,
            data={
                'name': 'Cartel con imagen',
                'payload': json.dumps(payload),
                'background_image': image_file,
            },
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        design = ReviewQrPosterDesign.objects.get(id=resp.data['id'])
        self.assertTrue(bool(design.background_image))


# ── Test 5: Sexto diseño → 400 design_limit_reached ──────────────────────────

class DesignLimitTest(DesignBaseTest):

    def test_sixth_design_returns_400(self):
        business = self._bootstrap_business('qr_reviews_pro')
        for i in range(5):
            self._create_design(business, name=f'Diseño {i+1}')
        data = {'name': 'Diseño 6', 'payload': _minimal_payload()}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get('code'), 'design_limit_reached')

    def test_fifth_design_succeeds(self):
        business = self._bootstrap_business('qr_reviews_pro')
        for i in range(4):
            self._create_design(business, name=f'Diseño {i+1}')
        data = {'name': 'Diseño 5', 'payload': _minimal_payload()}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


# ── Test 6: PATCH actualiza name → 200 ────────────────────────────────────────

class PatchNameTest(DesignBaseTest):

    def test_patch_name_returns_200(self):
        business = self._bootstrap_business('qr_reviews_pro')
        design = self._create_design(business, name='Nombre viejo')
        resp = self.client.patch(
            _detail_url(design.id),
            {'name': 'Nombre nuevo'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['name'], 'Nombre nuevo')
        design.refresh_from_db()
        self.assertEqual(design.name, 'Nombre nuevo')


# ── Test 7: PATCH actualiza payload → 200 ────────────────────────────────────

class PatchPayloadTest(DesignBaseTest):

    def test_patch_payload_returns_200(self):
        business = self._bootstrap_business('qr_reviews_pro')
        design = self._create_design(business)
        new_payload = _minimal_payload(main_text='Texto actualizado', background_color='#FF0000')
        resp = self.client.patch(
            _detail_url(design.id),
            {'payload': new_payload},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        design.refresh_from_db()
        self.assertEqual(design.payload['main_text'], 'Texto actualizado')
        self.assertEqual(design.payload['background_color'], '#FF0000')


# ── Test 8: PATCH reemplaza imagen → 200 ─────────────────────────────────────

class PatchReplaceImageTest(DesignBaseTest):

    def test_patch_replaces_image(self):
        business = self._bootstrap_business('qr_reviews_pro')
        # Create with image
        first_file = SimpleUploadedFile('first.png', _tiny_png(), content_type='image/png')
        payload = _minimal_payload(background_mode='image')
        resp_create = self.client.post(
            LIST_URL,
            data={'name': 'Con imagen', 'payload': json.dumps(payload), 'background_image': first_file},
            format='multipart',
        )
        self.assertEqual(resp_create.status_code, status.HTTP_201_CREATED)
        design_id = resp_create.data['id']

        # PATCH with new image
        second_file = SimpleUploadedFile('second.png', _tiny_png(), content_type='image/png')
        resp_patch = self.client.patch(
            _detail_url(design_id),
            data={'background_image': second_file},
            format='multipart',
        )
        self.assertEqual(resp_patch.status_code, status.HTTP_200_OK)
        design = ReviewQrPosterDesign.objects.get(id=design_id)
        self.assertTrue(bool(design.background_image))


# ── Test 9: PATCH a background_mode=color limpia imagen ──────────────────────

class PatchSwitchToColorTest(DesignBaseTest):

    def test_patch_to_color_mode_clears_image(self):
        business = self._bootstrap_business('qr_reviews_pro')
        # Create with image
        image_file = SimpleUploadedFile('bg.png', _tiny_png(), content_type='image/png')
        payload = _minimal_payload(background_mode='image')
        resp_create = self.client.post(
            LIST_URL,
            data={'name': 'Con imagen', 'payload': json.dumps(payload), 'background_image': image_file},
            format='multipart',
        )
        self.assertEqual(resp_create.status_code, status.HTTP_201_CREATED)
        design_id = resp_create.data['id']

        # Patch to color mode
        new_payload = _minimal_payload(background_mode='color', background_color='#0000FF')
        resp = self.client.patch(
            _detail_url(design_id),
            {'payload': new_payload},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        design = ReviewQrPosterDesign.objects.get(id=design_id)
        self.assertFalse(bool(design.background_image))
        self.assertIsNone(resp.data['background_image_url'])


# ── Test 10: DELETE elimina diseño → 204 ─────────────────────────────────────

class DeleteDesignTest(DesignBaseTest):

    def test_delete_returns_204(self):
        business = self._bootstrap_business('qr_reviews_pro')
        design = self._create_design(business)
        resp = self.client.delete(_detail_url(design.id))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ReviewQrPosterDesign.objects.filter(id=design.id).exists())

    def test_delete_reduces_count(self):
        business = self._bootstrap_business('qr_reviews_pro')
        d1 = self._create_design(business, name='D1')
        d2 = self._create_design(business, name='D2')
        self.client.delete(_detail_url(d1.id))
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.data['count'], 1)


# ── Test 11: Otro tenant no puede ver diseño → 404 ───────────────────────────

class TenantIsolationTest(DesignBaseTest):

    def test_other_tenant_get_returns_404(self):
        # Business A
        business_a = self._bootstrap_business('qr_reviews_pro')
        design = self._create_design(business_a, name='Diseño A')

        # Business B (different user)
        user_b = User.objects.create_user(username='user_b_tenant', password='pass')
        business_b = Business.objects.create(name='Biz B', slug='biz-b', default_service='qr_reviews')
        Subscription.objects.create(business=business_b, plan='qr_reviews_pro', service='qr_reviews', status='active')
        Membership.objects.create(user=user_b, business=business_b, role='owner')

        self.client.force_authenticate(user=user_b)
        self.client.cookies['bid'] = str(business_b.id)

        resp = self.client.get(_detail_url(design.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_tenant_patch_returns_404(self):
        business_a = self._bootstrap_business('qr_reviews_pro')
        design = self._create_design(business_a)

        user_b = User.objects.create_user(username='user_b_patch', password='pass')
        business_b = Business.objects.create(name='Biz B2', slug='biz-b2', default_service='qr_reviews')
        Subscription.objects.create(business=business_b, plan='qr_reviews_pro', service='qr_reviews', status='active')
        Membership.objects.create(user=user_b, business=business_b, role='owner')

        self.client.force_authenticate(user=user_b)
        self.client.cookies['bid'] = str(business_b.id)

        resp = self.client.patch(_detail_url(design.id), {'name': 'Hack'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_tenant_delete_returns_404(self):
        business_a = self._bootstrap_business('qr_reviews_pro')
        design = self._create_design(business_a)

        user_b = User.objects.create_user(username='user_b_delete', password='pass')
        business_b = Business.objects.create(name='Biz B3', slug='biz-b3', default_service='qr_reviews')
        Subscription.objects.create(business=business_b, plan='qr_reviews_pro', service='qr_reviews', status='active')
        Membership.objects.create(user=user_b, business=business_b, role='owner')

        self.client.force_authenticate(user=user_b)
        self.client.cookies['bid'] = str(business_b.id)

        resp = self.client.delete(_detail_url(design.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(ReviewQrPosterDesign.objects.filter(id=design.id).exists())


# ── Test 12: Payload inválido → 400 ──────────────────────────────────────────

class InvalidPayloadTest(DesignBaseTest):

    def setUp(self):
        super().setUp()
        self._bootstrap_business('qr_reviews_pro')

    def test_invalid_poster_size_returns_400(self):
        data = {'name': 'X', 'payload': _minimal_payload(poster_size='xxlarge')}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_background_color_returns_400(self):
        data = {'name': 'X', 'payload': _minimal_payload(background_color='rojo')}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_main_text_returns_400(self):
        data = {'name': 'X', 'payload': _minimal_payload(main_text='   ')}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_name_returns_400(self):
        data = {'payload': _minimal_payload()}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_payload_returns_400(self):
        data = {'name': 'Sin payload'}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ── Test 13: Sin auth → 401/403 ──────────────────────────────────────────────

class UnauthenticatedTest(DesignBaseTest):

    def test_list_unauthenticated(self):
        business = Business.objects.create(name='Unauth Biz', default_service='qr_reviews', slug='unauth-biz')
        Subscription.objects.create(business=business, plan='qr_reviews_pro', service='qr_reviews', status='active')
        self.client.cookies['bid'] = str(business.id)
        # no force_authenticate
        resp = self.client.get(LIST_URL)
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_create_unauthenticated(self):
        business = Business.objects.create(name='Unauth Biz2', default_service='qr_reviews', slug='unauth-biz2')
        Subscription.objects.create(business=business, plan='qr_reviews_pro', service='qr_reviews', status='active')
        self.client.cookies['bid'] = str(business.id)
        data = {'name': 'Test', 'payload': _minimal_payload()}
        resp = self.client.post(LIST_URL, data, format='json')
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ── Test 14: PATCH con background_mode=image sin imagen → 400 ────────────────

class PatchImageModeWithoutImageTest(DesignBaseTest):

    def test_patch_image_mode_no_file_no_existing_returns_400(self):
        """PATCH switching to background_mode=image with no file and no existing image → 400."""
        business = self._bootstrap_business('qr_reviews_pro')
        # Design created without image (color mode)
        design = self._create_design(business)
        self.assertFalse(bool(design.background_image))

        new_payload = _minimal_payload(background_mode='image')
        resp = self.client.patch(
            _detail_url(design.id),
            {'payload': new_payload},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('background_image', resp.data)


# ── Test 15-21: POST designs/<uuid>/generate-pdf/ ────────────────────────────

def _design_pdf_url(design_id) -> str:
    return f'/api/v1/reviews/qr-posters/designs/{design_id}/generate-pdf/'


class GeneratePdfFromDesignNoImageTest(DesignBaseTest):
    """Test 15: PRO genera PDF desde diseño sin imagen → 200 PDF."""

    def test_generate_pdf_color_design_returns_200(self):
        business = self._bootstrap_business('qr_reviews_pro')
        business.slug = 'biz-qr-reviews-pro'
        business.save()
        design = self._create_design(business)
        resp = self.client.post(_design_pdf_url(design.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn(b'%PDF', resp.content[:10])


class GeneratePdfFromDesignWithImageTest(DesignBaseTest):
    """Test 16: PRO genera PDF desde diseño con imagen guardada → 200 PDF."""

    def test_generate_pdf_image_design_returns_200(self):
        business = self._bootstrap_business('qr_reviews_pro')
        business.slug = 'biz-qr-reviews-pro'
        business.save()

        # Create design with image via API so the file is stored properly
        image_file = SimpleUploadedFile('bg.png', _tiny_png(), content_type='image/png')
        payload = _minimal_payload(background_mode='image')
        resp_create = self.client.post(
            LIST_URL,
            data={'name': 'Con imagen', 'payload': json.dumps(payload), 'background_image': image_file},
            format='multipart',
        )
        self.assertEqual(resp_create.status_code, status.HTTP_201_CREATED)
        design_id = resp_create.data['id']

        resp = self.client.post(_design_pdf_url(design_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn(b'%PDF', resp.content[:10])


class GeneratePdfFromDesignBasicPlanTest(DesignBaseTest):
    """Test 17: Plan básico genera PDF desde diseño → 403."""

    def test_basic_plan_returns_403(self):
        business = self._bootstrap_business('qr_reviews_pro')
        business.slug = 'biz-qr-reviews-pro'
        business.save()
        design = self._create_design(business)

        # Switch to basic plan
        from apps.business.models import Subscription as _Sub  # noqa: PLC0415
        _Sub.objects.filter(business=business).update(plan='qr_reviews')

        resp = self.client.post(_design_pdf_url(design.id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class GeneratePdfFromDesignTenantIsolationTest(DesignBaseTest):
    """Test 18: Otro tenant intenta generar PDF desde diseño ajeno → 404."""

    def test_other_tenant_returns_404(self):
        # Business A — create design
        business_a = self._bootstrap_business('qr_reviews_pro')
        business_a.slug = 'biz-a-pdf'
        business_a.save()
        design = self._create_design(business_a)

        # Business B — different user
        user_b = User.objects.create_user(username='user_b_pdf', password='pass')
        business_b = Business.objects.create(
            name='Biz B PDF', slug='biz-b-pdf', default_service='qr_reviews',
        )
        Subscription.objects.create(
            business=business_b, plan='qr_reviews_pro', service='qr_reviews', status='active',
        )
        Membership.objects.create(user=user_b, business=business_b, role='owner')

        self.client.force_authenticate(user=user_b)
        self.client.cookies['bid'] = str(business_b.id)

        resp = self.client.post(_design_pdf_url(design.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class GeneratePdfFromDesignImageModeNoFileTest(DesignBaseTest):
    """Test 19: Diseño con background_mode=image pero sin imagen guardada → 400."""

    def test_image_mode_no_stored_image_returns_400(self):
        business = self._bootstrap_business('qr_reviews_pro')
        business.slug = 'biz-qr-reviews-pro'
        business.save()
        # Create design with image mode but no file (direct DB creation)
        design = ReviewQrPosterDesign.objects.create(
            business=business,
            name='Sin archivo',
            payload=_minimal_payload(background_mode='image'),
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertFalse(bool(design.background_image))

        resp = self.client.post(_design_pdf_url(design.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get('code'), 'missing_design_background_image')


class GeneratePdfFromDesignNotFoundTest(DesignBaseTest):
    """Test 20: Diseño inexistente → 404."""

    def test_nonexistent_design_returns_404(self):
        self._bootstrap_business('qr_reviews_pro')
        import uuid  # noqa: PLC0415
        resp = self.client.post(_design_pdf_url(uuid.uuid4()))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class GeneratePdfFromDesignUnauthenticatedTest(DesignBaseTest):
    """Test 21: Sin auth → 401/403."""

    def test_unauthenticated_returns_401_or_403(self):
        business = Business.objects.create(
            name='Unauth PDF Biz', slug='unauth-pdf-biz', default_service='qr_reviews',
        )
        Subscription.objects.create(
            business=business, plan='qr_reviews_pro', service='qr_reviews', status='active',
        )
        design = ReviewQrPosterDesign.objects.create(
            business=business,
            name='X',
            payload=_minimal_payload(),
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.cookies['bid'] = str(business.id)
        # No force_authenticate
        resp = self.client.post(_design_pdf_url(design.id))
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ── Test 22: background_image_url devuelve URL absoluta ──────────────────────

class BackgroundImageUrlAbsoluteTest(DesignBaseTest):
    """
    Verifica que background_image_url en la respuesta sea una URL absoluta
    (http://testserver/media/...) y no una ruta relativa (/media/...).

    Esto cubre el bug donde get_background_image_url() devolvía la URL relativa
    de FileSystemStorage sin pasar por request.build_absolute_uri().
    """

    def _create_via_api_with_image(self) -> dict:
        self._bootstrap_business('qr_reviews_pro')
        payload = _minimal_payload(background_mode='image')
        image_file = SimpleUploadedFile('fondo.png', _tiny_png(), content_type='image/png')
        resp = self.client.post(
            LIST_URL,
            data={'name': 'Con imagen', 'payload': json.dumps(payload), 'background_image': image_file},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        return resp.data

    def test_create_response_has_absolute_url(self):
        data = self._create_via_api_with_image()
        url = data.get('background_image_url')
        self.assertIsNotNone(url, 'background_image_url debe ser no-nulo cuando hay imagen')
        self.assertTrue(
            url.startswith('http://') or url.startswith('https://'),
            f'background_image_url debe ser absoluta, se recibió: {url!r}',
        )

    def test_list_response_has_absolute_url(self):
        self._create_via_api_with_image()
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        url = resp.data['results'][0].get('background_image_url')
        self.assertIsNotNone(url)
        self.assertTrue(
            url.startswith('http://') or url.startswith('https://'),
            f'background_image_url en list debe ser absoluta, se recibió: {url!r}',
        )

    def test_detail_response_has_absolute_url(self):
        data = self._create_via_api_with_image()
        design_id = data['id']
        resp = self.client.get(_detail_url(design_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        url = resp.data.get('background_image_url')
        self.assertIsNotNone(url)
        self.assertTrue(
            url.startswith('http://') or url.startswith('https://'),
            f'background_image_url en detail debe ser absoluta, se recibió: {url!r}',
        )

    def test_patch_response_preserves_absolute_url(self):
        data = self._create_via_api_with_image()
        design_id = data['id']
        resp = self.client.patch(
            _detail_url(design_id),
            {'name': 'Nombre editado'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        url = resp.data.get('background_image_url')
        self.assertIsNotNone(url)
        self.assertTrue(
            url.startswith('http://') or url.startswith('https://'),
            f'background_image_url en patch debe ser absoluta, se recibió: {url!r}',
        )


# ── Test 23: Archivo con formato inválido → 400 ───────────────────────────────

class CreateDesignInvalidImageTypeTest(DesignBaseTest):
    """Test 23: Subir archivo no-imagen (GIF, texto) → 400."""

    def test_gif_file_returns_400(self):
        """GIF no está en los formatos permitidos (JPEG/PNG)."""
        self._bootstrap_business('qr_reviews_pro')
        payload = _minimal_payload(background_mode='image')
        # Minimal valid GIF header
        gif_bytes = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00'
            b'!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01'
            b'\x00\x00\x02\x02D\x01\x00;'
        )
        gif_file = SimpleUploadedFile('fondo.gif', gif_bytes, content_type='image/gif')
        resp = self.client.post(
            LIST_URL,
            data={'name': 'Con gif', 'payload': json.dumps(payload), 'background_image': gif_file},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_text_file_returns_400(self):
        """Archivo de texto plano — PIL no puede abrirlo como imagen."""
        self._bootstrap_business('qr_reviews_pro')
        payload = _minimal_payload(background_mode='image')
        txt_file = SimpleUploadedFile('fondo.txt', b'no soy una imagen', content_type='text/plain')
        resp = self.client.post(
            LIST_URL,
            data={'name': 'Con txt', 'payload': json.dumps(payload), 'background_image': txt_file},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ── Test 24: Archivo demasiado grande → 400 ───────────────────────────────────

class CreateDesignImageTooLargeTest(DesignBaseTest):
    """Test 24: Imagen que supera el límite de 10 MB → 400."""

    def test_image_over_10mb_returns_400(self):
        self._bootstrap_business('qr_reviews_pro')
        payload = _minimal_payload(background_mode='image')
        # Build a fake "image" file that is just > 10 MB of valid PNG header + padding.
        # We use a real PNG so PIL can read size, but pad it to exceed 10 MB.
        buf = io.BytesIO(_tiny_png())
        # Pad to 10 MB + 1 byte
        buf.seek(0, 2)
        buf.write(b'\x00' * (10 * 1024 * 1024 + 1 - buf.tell()))
        oversized = SimpleUploadedFile(
            'too_big.png', buf.getvalue(), content_type='image/png',
        )
        resp = self.client.post(
            LIST_URL,
            data={'name': 'Muy grande', 'payload': json.dumps(payload), 'background_image': oversized},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ── Test 25: public_media_storage local behavior ──────────────────────────────

class PublicMediaStorageLocalTest(APITestCase):
    """
    Test 25: Verifica que public_media_storage() devuelve un FileSystemStorage
    con location=MEDIA_ROOT y base_url=MEDIA_URL cuando no hay bucket S3.

    Garantiza que el storage explícito sea correcto y no dependa de defaults
    implícitos de Django que podrían cambiar entre versiones.
    """

    def test_local_storage_uses_media_root(self):
        from django.conf import settings
        from django.core.files.storage import FileSystemStorage

        from common.storages import public_media_storage

        with self.settings(AWS_STORAGE_BUCKET_NAME=''):
            storage = public_media_storage()

        self.assertIsInstance(storage, FileSystemStorage)
        self.assertEqual(storage.location, str(settings.MEDIA_ROOT))

    def test_local_storage_uses_media_url(self):
        from django.conf import settings
        from django.core.files.storage import FileSystemStorage

        from common.storages import public_media_storage

        with self.settings(AWS_STORAGE_BUCKET_NAME=''):
            storage = public_media_storage()

        self.assertIsInstance(storage, FileSystemStorage)
        self.assertEqual(storage.base_url, settings.MEDIA_URL)

    def test_local_storage_not_s3_when_no_bucket(self):
        """Sin bucket configurado, nunca se debe devolver S3Boto3Storage."""
        from django.core.files.storage import FileSystemStorage

        from common.storages import public_media_storage

        with self.settings(AWS_STORAGE_BUCKET_NAME=''):
            storage = public_media_storage()

        self.assertIsInstance(storage, FileSystemStorage)
