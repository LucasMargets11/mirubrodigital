"""PROD-08E1 — Platform Admin: estado local de las conexiones WhatsApp.

  GET /api/v1/platform-admin/clients/<business_id>/whatsapp-connections/

Mismo acceso y resolución que la configuración de Recepcionista en Platform
Admin: personal de plataforma `superadmin`/`operations`, cliente HQ con
Recepcionista no cancelada, Business solo por la ruta. Solo lectura,
`no-store`, sin auditoría ni escrituras. Nunca tokens ni secretos.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import HasInternalRole, IsPlatformStaff

from .receptionist_config_views import admin_reception_business
from .services.whatsapp_authorizations import admin_whatsapp_connections


class AdminClientWhatsAppConnectionsView(APIView):
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request, business_id: int):
        business = admin_reception_business(business_id)
        if business is None:
            response = Response({'code': 'client_not_found', 'detail': 'Cliente no encontrado.'}, status=404)
        else:
            response = Response(admin_whatsapp_connections(business))
        response['Cache-Control'] = 'no-store'
        return response
