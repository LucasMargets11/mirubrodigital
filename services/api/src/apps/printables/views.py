"""
View para el endpoint POST /api/v1/printables/generate-pdf/
"""
from __future__ import annotations

import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasEntitlement
from apps.catalog.models import Product

from .pdf import render_signage_pdf
from .serializers import GeneratePDFSerializer

logger = logging.getLogger(__name__)


class GeneratePDFView(APIView):
    """
    POST /api/v1/printables/generate-pdf/

    Genera un PDF A4 con carteles/etiquetas imprimibles.
    Requiere plan PRO (entitlement: gestion.print_signage).
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement]
    required_entitlement = 'gestion.print_signage'

    def post(self, request):
        serializer = GeneratePDFSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data     = serializer.validated_data
        business = request.business

        # ── Validar product_ids pertenecen al business ──────────────────────
        for item in data['items']:
            product_id = item.get('product_id')
            if product_id:
                exists = Product.objects.filter(
                    pk=product_id,
                    business=business,
                    is_active=True,
                ).exists()
                if not exists:
                    return Response(
                        {
                            'code': 'invalid_product',
                            'message': 'El producto no existe o no pertenece a este negocio.',
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # ── Generar PDF ───────────────────────────────────────────────────────
        try:
            pdf_bytes = render_signage_pdf(data, business=business)
        except Exception:
            logger.exception('Error al generar PDF de carteles (business=%s)', business.id)
            return Response(
                {
                    'code': 'pdf_generation_error',
                    'message': 'No se pudo generar el PDF. Intentá nuevamente.',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="carteles-etiquetas.pdf"'
        return response
