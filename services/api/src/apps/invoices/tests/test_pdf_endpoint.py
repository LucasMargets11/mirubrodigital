"""
Tests para el endpoint GET /api/v1/invoices/<pk>/pdf/

Cubre:
- Perfil con fiscal_address (sin legal_address) → 200 PDF bytes
- Perfil incompleto (sin razón social ni domicilio) → 422 con missing_fields
- Branding sin logos → 200
- Branding con logo PNG válido → 200 (no crash)
"""
from __future__ import annotations

import io
import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessBillingProfile, BusinessBranding, Subscription
from apps.invoices.models import Invoice, InvoiceSeries
from apps.sales.models import Sale, SaleItem

User = get_user_model()


def _make_minimal_png() -> bytes:
    """Genera un PNG de 1×1 píxel válido en memoria."""
    # PNG signature + IHDR + IDAT + IEND (1x1 rojo)
    import base64
    _1x1_red_png_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        'z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=='
    )
    return base64.b64decode(_1x1_red_png_b64)


class InvoicePDFEndpointTests(APITestCase):
    """Tests del endpoint GET /api/v1/invoices/<pk>/pdf/"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='manager_test',
            email='manager@test.com',
            password='testpass123',
        )

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _bootstrap_business(self, plan: str = 'pro', role: str = 'manager') -> Business:
        """Crea Business, Subscription, Membership y autentica el cliente."""
        business = Business.objects.create(name='Test Biz')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(
            user=self.user,
            business=business,
            role=role,
        )
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def _make_invoice(self, business: Business) -> Invoice:
        """Crea una venta con ítem y una factura asociadas al business."""
        sales_number = Sale.objects.filter(business=business).count() + 1
        sale = Sale.objects.create(
            business=business,
            number=sales_number,
            subtotal='100.00',
            discount='0.00',
            total='100.00',
        )
        SaleItem.objects.create(
            sale=sale,
            product_name_snapshot='Producto de prueba',
            quantity='2',
            unit_price='50.00',
            line_total='100.00',
        )
        series = InvoiceSeries.objects.create(
            business=business,
            code='X',
            next_number=1,
        )
        invoice = Invoice.objects.create(
            id=uuid.uuid4(),
            business=business,
            sale=sale,
            series=series,
            number=1,
            full_number='X-00000001',
            subtotal='100.00',
            discount='0.00',
            total='100.00',
        )
        return invoice

    def _pdf_url(self, invoice: Invoice) -> str:
        return reverse('invoices:invoice-pdf', args=[invoice.pk])

    # ──────────────────────────────────────────────
    # Test 1: fiscal_address (sin legacy legal_address) → 200
    # ──────────────────────────────────────────────

    def test_pdf_with_fiscal_address_returns_200(self):
        """
        El modelo tiene fiscal_address (no legal_address).
        get_issuer_data() debe usar fiscal_address como fallback de legal_address.
        El endpoint debe devolver 200 con PDF bytes, nunca AttributeError.
        """
        business = self._bootstrap_business()
        invoice = self._make_invoice(business)

        # Perfil con fiscal_address, sin legal_address explícito
        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Empresa de Prueba S.A.'
        profile.tax_id = '20-12345678-9'
        profile.tax_id_type = 'cuit'
        profile.vat_condition = 'responsable_inscripto'
        profile.fiscal_address = 'Av. Corrientes 1234, Buenos Aires'
        profile.email = 'empresa@test.com'
        profile.save()

        response = self.client.get(self._pdf_url(invoice))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100, 'El PDF debe tener contenido')

    # ──────────────────────────────────────────────
    # Test 2: Perfil incompleto → 422 con missing_fields
    # ──────────────────────────────────────────────

    def test_pdf_with_incomplete_profile_returns_422(self):
        """
        Perfil con legal_name y fiscal_address vacíos → 422 con código
        'issuer_profile_incomplete' y lista de missing_fields.
        """
        business = self._bootstrap_business()
        invoice = self._make_invoice(business)

        # Aseguramos perfil completamente vacío
        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = ''
        profile.fiscal_address = ''
        profile.commercial_address = ''
        profile.save()

        response = self.client.get(self._pdf_url(invoice))

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data['code'], 'issuer_profile_incomplete')
        self.assertIn('missing_fields', data)
        self.assertIsInstance(data['missing_fields'], list)
        self.assertGreater(len(data['missing_fields']), 0)
        self.assertIn('legal_name', data['missing_fields'])

    def test_pdf_with_missing_address_includes_fiscal_address_in_missing_fields(self):
        """
        Perfil con legal_name OK pero sin domicilio → 422 con fiscal_address en missing_fields.
        """
        business = self._bootstrap_business()
        invoice = self._make_invoice(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Empresa Test'
        profile.fiscal_address = ''
        profile.commercial_address = ''
        profile.save()

        response = self.client.get(self._pdf_url(invoice))

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertIn('fiscal_address', data['missing_fields'])

    # ──────────────────────────────────────────────
    # Test 3: Branding sin logos → 200
    # ──────────────────────────────────────────────

    def test_pdf_without_logos_returns_200(self):
        """
        Branding sin logos configurados no debe romper el PDF.
        El texto con la razón social debe actuar como fallback.
        """
        business = self._bootstrap_business()
        invoice = self._make_invoice(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Sin Logo S.A.'
        profile.fiscal_address = 'Calle Falsa 123'
        profile.save()

        # Branding sin imágenes (vacío)
        BusinessBranding.objects.get_or_create(business=business)

        response = self.client.get(self._pdf_url(invoice))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    # ──────────────────────────────────────────────
    # Test 4: PDF incluye datos fiscales correctos
    # ──────────────────────────────────────────────

    def test_pdf_bytes_returned_with_full_profile(self):
        """
        Perfil completo (razón social, CUIT, IVA, domicilio) → 200 con bytes de PDF.
        """
        business = self._bootstrap_business()
        invoice = self._make_invoice(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Comercio Full S.R.L.'
        profile.tax_id = '30-99887766-5'
        profile.tax_id_type = 'cuit'
        profile.vat_condition = 'monotributo'
        profile.fiscal_address = 'Lavalle 500, CABA'
        profile.commercial_address = 'Lavalle 500, CABA'
        profile.iibb = '901-234567-8'
        profile.phone = '+54 11 4444-5555'
        profile.email = 'info@comercio.com'
        profile.website = 'https://comercio.com'
        profile.save()

        response = self.client.get(self._pdf_url(invoice))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        # PDF comienza con %PDF
        self.assertTrue(response.content.startswith(b'%PDF'), 'La respuesta debe ser un PDF válido')

    # ──────────────────────────────────────────────
    # Test 5: Branding con logo PNG → 200 sin crash
    # ──────────────────────────────────────────────

    def test_pdf_with_valid_png_logo_returns_200(self):
        """
        Si hay un logo PNG válido en branding, el PDF debe generarse sin errores.
        """
        from django.core.files.base import ContentFile

        business = self._bootstrap_business()
        invoice = self._make_invoice(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Logo Corp S.A.'
        profile.fiscal_address = 'Belgrano 800'
        profile.save()

        branding, _ = BusinessBranding.objects.get_or_create(business=business)
        png_bytes = _make_minimal_png()
        branding.logo_horizontal.save(
            'test_logo.png',
            ContentFile(png_bytes),
            save=True,
        )

        response = self.client.get(self._pdf_url(invoice))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

        # Cleanup
        if branding.logo_horizontal:
            try:
                branding.logo_horizontal.delete(save=True)
            except Exception:
                pass

    # ──────────────────────────────────────────────
    # Test 6: Unauthenticated → 401
    # ──────────────────────────────────────────────

    def test_pdf_unauthenticated_returns_401(self):
        """Sin autenticación el endpoint debe rechazar con 401."""
        business = self._bootstrap_business()
        invoice = self._make_invoice(business)
        self.client.force_authenticate(user=None)  # log out

        response = self.client.get(self._pdf_url(invoice))

        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
