"""
Tests para la generación de PDF de presupuestos.

Cubre:
- Presupuesto con logo configurado → PDF con logo (no crash)
- Presupuesto sin logo → PDF generado correctamente
- Presupuesto con branding incompleto → PDF generado sin romperse
- Endpoint GET /api/v1/sales/quotes/<pk>/pdf/ → 200 con logo
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessBillingProfile, BusinessBranding, Subscription
from apps.sales.models import Quote, QuoteItem

User = get_user_model()


def _make_minimal_png() -> bytes:
    """Genera un PNG de 10×10 píxeles válido en memoria usando Pillow."""
    from io import BytesIO
    from PIL import Image
    img = Image.new('RGB', (10, 10), color=(200, 50, 50))
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


class QuotePDFTests(APITestCase):
    """Tests de generación de PDF para presupuestos."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='quote_pdf_test',
            email='quotetest@test.com',
            password='testpass123',
        )

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _bootstrap_business(self, plan: str = 'pro', role: str = 'manager') -> Business:
        business = Business.objects.create(name='Test Biz Quotes')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def _make_quote(self, business: Business) -> Quote:
        quote = Quote.objects.create(
            business=business,
            number='P-000001',
            status=Quote.Status.DRAFT,
            customer_name='Cliente de Prueba',
            customer_email='cliente@test.com',
            subtotal=Decimal('200.00'),
            discount_total=Decimal('0.00'),
            tax_total=Decimal('0.00'),
            total=Decimal('200.00'),
        )
        QuoteItem.objects.create(
            quote=quote,
            name_snapshot='Producto Test',
            quantity=Decimal('2'),
            unit_price=Decimal('100.00'),
            discount=Decimal('0.00'),
            total_line=Decimal('200.00'),
        )
        return quote

    def _pdf_url(self, quote: Quote) -> str:
        return reverse('sales:quote-pdf', args=[quote.pk])

    # ──────────────────────────────────────────────
    # Test 1: PDF sin logos → 200
    # ──────────────────────────────────────────────

    def test_pdf_without_logos_returns_200(self):
        """PDF de presupuesto sin logo configurado debe generarse sin romperse."""
        business = self._bootstrap_business()
        quote = self._make_quote(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Sin Logo S.A.'
        profile.fiscal_address = 'Calle Falsa 123'
        profile.save()

        BusinessBranding.objects.get_or_create(business=business)

        response = self.client.get(self._pdf_url(quote))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        content = b''.join(response.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'), 'La respuesta debe ser un PDF válido')

    # ──────────────────────────────────────────────
    # Test 2: PDF con logo PNG → 200 sin crash
    # ──────────────────────────────────────────────

    def test_pdf_with_valid_png_logo_returns_200(self):
        """Si hay un logo PNG válido en branding, el PDF de presupuesto debe incluirlo."""
        business = self._bootstrap_business()
        quote = self._make_quote(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Logo Corp S.A.'
        profile.fiscal_address = 'Belgrano 800'
        profile.save()

        branding, _ = BusinessBranding.objects.get_or_create(business=business)
        png_bytes = _make_minimal_png()
        branding.logo_horizontal.save('test_logo.png', ContentFile(png_bytes), save=True)

        response = self.client.get(self._pdf_url(quote))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        content = b''.join(response.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'), 'La respuesta debe ser un PDF válido')
        # PDF con logo debe ser más grande que sin logo
        self.assertGreater(len(content), 500, 'El PDF con logo debe tener contenido sustancial')

        # Cleanup
        if branding.logo_horizontal:
            try:
                branding.logo_horizontal.delete(save=True)
            except Exception:
                pass

    # ──────────────────────────────────────────────
    # Test 3: PDF con logo square (fallback) → 200
    # ──────────────────────────────────────────────

    def test_pdf_with_square_logo_fallback_returns_200(self):
        """Si solo hay logo_square (sin horizontal), el presupuesto debe usarlo como fallback."""
        business = self._bootstrap_business()
        quote = self._make_quote(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Square Logo S.A.'
        profile.fiscal_address = 'San Martín 100'
        profile.save()

        branding, _ = BusinessBranding.objects.get_or_create(business=business)
        png_bytes = _make_minimal_png()
        branding.logo_square.save('test_logo_sq.png', ContentFile(png_bytes), save=True)

        response = self.client.get(self._pdf_url(quote))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

        # Cleanup
        if branding.logo_square:
            try:
                branding.logo_square.delete(save=True)
            except Exception:
                pass

    # ──────────────────────────────────────────────
    # Test 4: Sin branding creado → 200 (auto-crea)
    # ──────────────────────────────────────────────

    def test_pdf_without_branding_object_returns_200(self):
        """Si no existe BusinessBranding, get_or_create lo crea y el PDF no se rompe."""
        business = self._bootstrap_business()
        quote = self._make_quote(business)

        response = self.client.get(self._pdf_url(quote))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    # ──────────────────────────────────────────────
    # Test 5: Unit test build_quote_pdf con logo
    # ──────────────────────────────────────────────

    def test_build_quote_pdf_includes_branding_context(self):
        """build_quote_pdf debe generar bytes PDF válidos con logo configurado."""
        from apps.sales.quote_pdf import build_quote_pdf

        business = self._bootstrap_business()
        quote = self._make_quote(business)

        profile, _ = BusinessBillingProfile.objects.get_or_create(business=business)
        profile.legal_name = 'Unit Test Corp'
        profile.fiscal_address = 'Rivadavia 500'
        profile.save()

        branding, _ = BusinessBranding.objects.get_or_create(business=business)
        png_bytes = _make_minimal_png()
        branding.logo_horizontal.save('unit_test_logo.png', ContentFile(png_bytes), save=True)

        pdf_bytes = build_quote_pdf(quote)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'), 'Debe ser un PDF válido')
        self.assertGreater(len(pdf_bytes), 500)

        # Cleanup
        if branding.logo_horizontal:
            try:
                branding.logo_horizontal.delete(save=True)
            except Exception:
                pass

    def test_build_quote_pdf_without_logo_does_not_crash(self):
        """build_quote_pdf sin logo no debe lanzar excepción."""
        from apps.sales.quote_pdf import build_quote_pdf

        business = self._bootstrap_business()
        quote = self._make_quote(business)

        pdf_bytes = build_quote_pdf(quote)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
