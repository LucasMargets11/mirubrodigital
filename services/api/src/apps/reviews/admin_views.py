"""
Platform admin views for QR de Reseñas configuration.

GET  /api/v1/platform-admin/clients/<business_id>/qr-reviews-config/
PATCH /api/v1/platform-admin/clients/<business_id>/qr-reviews-config/

Restricted to platform staff with roles: superadmin, operations.
Validates that the business is of service_type 'qr_reviews' before any
read or write operation.
"""
from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import IsPlatformStaff, HasInternalRole
from apps.accounts.platform_audit import log_platform_action
from apps.business.models import Business

from .admin_service import get_admin_qr_reviews_config_snapshot, update_admin_qr_reviews_config

logger = logging.getLogger(__name__)

# Fields accepted by PATCH.
_PATCHABLE_FIELDS = {
    'slug',
    'google_place_id',
    'google_place_name',
    'google_place_formatted_address',
    'google_review_url',
    'custom_redirect_url',
}


def _is_qr_reviews_business(biz: Business) -> bool:
    """True when the business operates under the qr_reviews vertical."""
    canonical = biz.service_type or ''
    legacy = biz.default_service or ''
    return canonical == 'qr_reviews' or legacy == 'qr_reviews'


class AdminQRReviewsConfigView(APIView):
    """
    GET  — Return full QR de Reseñas configuration snapshot.
    PATCH — Update Business.slug and/or ReviewConfig place fields.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def _get_business(self, business_id: int) -> Business | None:
        try:
            return Business.objects.get(pk=business_id, parent__isnull=True)
        except Business.DoesNotExist:
            return None

    def get(self, request: Request, business_id: int) -> Response:
        biz = self._get_business(business_id)
        if biz is None:
            return Response({'detail': 'Cliente no encontrado.'}, status=404)

        if not _is_qr_reviews_business(biz):
            return Response(
                {'detail': 'Este negocio no es de tipo QR de Reseñas.'},
                status=400,
            )

        log_platform_action(
            action='ADMIN_CLIENT_VIEWED',
            actor=request.user,
            entity_type='business',
            entity_id=str(biz.id),
            business=biz,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        snapshot = get_admin_qr_reviews_config_snapshot(biz)
        return Response(snapshot)

    def patch(self, request: Request, business_id: int) -> Response:
        biz = self._get_business(business_id)
        if biz is None:
            return Response({'detail': 'Cliente no encontrado.'}, status=404)

        if not _is_qr_reviews_business(biz):
            return Response(
                {'detail': 'Este negocio no es de tipo QR de Reseñas.'},
                status=400,
            )

        # Reject unknown fields — fail loudly to prevent accidental writes.
        unknown = set(request.data.keys()) - _PATCHABLE_FIELDS
        if unknown:
            return Response(
                {
                    'detail': f'Campos no permitidos: {", ".join(sorted(unknown))}.',
                    'allowed_fields': sorted(_PATCHABLE_FIELDS),
                },
                status=400,
            )

        data = {k: v for k, v in request.data.items() if k in _PATCHABLE_FIELDS}
        if not data:
            return Response(
                {'detail': 'No se enviaron campos válidos para actualizar.'},
                status=400,
            )

        try:
            snapshot = update_admin_qr_reviews_config(biz, data, actor=request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)

        changed_fields = list(data.keys())
        logger.info(
            '[Admin] QR Reviews config updated business=%s fields=%s actor=%s',
            biz.id, changed_fields, request.user.email,
        )
        log_platform_action(
            action='ADMIN_CLIENT_VIEWED',
            actor=request.user,
            entity_type='business',
            entity_id=str(biz.id),
            business=biz,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response(snapshot)
