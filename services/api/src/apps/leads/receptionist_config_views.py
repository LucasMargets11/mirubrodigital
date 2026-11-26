"""PROD-03B — API de configuración de Recepcionista IA.

Comercio (owner/admin), Business = `request.business` (nunca un id del cliente):
  GET   /api/v1/receptionist-config/
  POST  /api/v1/receptionist-config/   crea el borrador (409 si ya existe)
  PATCH /api/v1/receptionist-config/   edición parcial con `expected_version`

Platform Admin (superadmin/operations), cliente HQ elegido:
  GET|POST|PATCH /api/v1/platform-admin/clients/<business_id>/receptionist-config/

Ambos delegan en `services/receptionist_config.py` (mismas validaciones,
bloqueo, versión y auditoría). GET nunca crea: sin configuración responde
`{"config": null}`. `status=ready` significa configuración completa, NO
activación del bot.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasEntitlement, HasPermission
from apps.accounts.platform_permissions import HasInternalRole, IsPlatformStaff
from apps.billing.models import SubscriptionV2
from apps.business.entitlements import RECEPTION_AI_ENTITLEMENT
from apps.business.models import Business

from .models import ReceptionistConfig
from .services.receptionist_config import (
    SOURCE_BUSINESS, SOURCE_PLATFORM_ADMIN, ReceptionistConfigError, create_receptionist_config,
    serialize_receptionist_config, update_receptionist_config,
)


class _ReceptionistConfigMixin:
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    source = ''

    def target_business(self, request, **kwargs) -> Business | None:
        raise NotImplementedError

    def _respond(self, body: dict, status: int = 200) -> Response:
        response = Response(body, status=status)
        response['Cache-Control'] = 'no-store'
        return response

    def _run(self, request, kwargs, operation, *, status: int = 200) -> Response:
        business = self.target_business(request, **kwargs)
        if business is None:
            return self._respond({'code': 'client_not_found', 'detail': 'Cliente no encontrado.'}, 404)
        try:
            config = operation(business)
        except ReceptionistConfigError as error:
            return self._respond(error.as_body(), error.status)
        return self._respond(serialize_receptionist_config(config), status)

    def get(self, request, **kwargs):
        return self._run(
            request, kwargs, lambda business: ReceptionistConfig.objects.filter(business=business).first(),
        )

    def post(self, request, **kwargs):
        return self._run(
            request, kwargs,
            lambda business: create_receptionist_config(
                business, request.data, actor=request.user, source=self.source,
            ),
            status=201,
        )

    def patch(self, request, **kwargs):
        return self._run(
            request, kwargs,
            lambda business: update_receptionist_config(
                business, request.data, actor=request.user, source=self.source,
            ),
        )


class ReceptionistConfigView(_ReceptionistConfigMixin, APIView):
    """Comercio: Recepcionista IA vigente (`reception.ai`) + `manage_agent_channels`
    (owner/admin del servicio `reception`; manager y viewer no)."""

    permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
    required_entitlement = RECEPTION_AI_ENTITLEMENT
    required_permission = 'manage_agent_channels'
    source = SOURCE_BUSINESS

    def target_business(self, request, **kwargs):
        return request.business


class AdminClientReceptionistConfigView(_ReceptionistConfigMixin, APIView):
    """Platform Admin: cliente HQ con servicio Recepcionista IA no cancelado."""

    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']
    source = SOURCE_PLATFORM_ADMIN

    def target_business(self, request, business_id: int, **kwargs):
        business = Business.objects.filter(pk=business_id, parent__isnull=True).first()
        if business is None:
            return None
        has_reception = (
            SubscriptionV2.objects.filter(business=business, service_type='reception')
            .exclude(status=SubscriptionV2.Status.CANCELED).exists()
        )
        return business if has_reception else None
