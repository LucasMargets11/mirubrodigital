"""Platform Admin: conexiones WhatsApp de un cliente.

  GET  /api/v1/platform-admin/clients/<business_id>/whatsapp-connections/
       PROD-08E1 (+10C1 aditivo: `meta_verification` por canal). Superadmin u
       operations. Solo lectura, sin auditoría.
  POST /api/v1/platform-admin/clients/<business_id>/whatsapp-connections/
       PROD-10C1: vinculación asistida. Solo superadmin. Body exacto
       `{waba_id, phone_number_id, access_token, reason}`; delega todo en
       `link_whatsapp_channel` (origen `assisted`, fijado acá). 201 alta nueva,
       200 repetición equivalente.

Mismo acceso y resolución que la configuración de Recepcionista: cliente HQ
con Recepcionista no cancelada, Business solo por la ruta. Siempre
`no-store`. El token entra solo por el body y nunca sale (ni en errores).
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.platform_permissions import HasInternalRole, IsPlatformStaff

from .models import AgentChannel
from .services.meta_graph import MetaGraphError
from .services.receptionist_config import admin_reception_business
from .services.whatsapp_authorizations import (
    ADMIN_WHATSAPP_CONNECTIONS_CONTRACT_VERSION, WhatsAppAuthorizationError, admin_whatsapp_channel,
    admin_whatsapp_connections,
)
from .services.whatsapp_link import OUTCOME_LINKED, SOURCE_ASSISTED, link_whatsapp_channel

LINK_FIELDS = ('waba_id', 'phone_number_id', 'access_token', 'reason')
LINK_FIELD_MAX_LENGTH = 4096  # cota de tamaño; el servicio valida cada formato

# Errores locales → (HTTP, campo). Los no listados (conflictos) son 409.
LOCAL_ERRORS = {
    'actor_not_authorized': (403, None),
    'invalid_token': (400, 'access_token'),
    'invalid_reason': (400, 'reason'),
    'agent_instance_not_configured': (503, None),
    'agent_instance_unavailable': (503, None),
    'whatsapp_credential_unreadable': (503, None),
    'phone_platform_not_supported': (422, 'phone_number_id'),
    'whatsapp_authorization_expired': (422, 'access_token'),
}
RETRYABLE_LOCAL = frozenset({'channel_changed_concurrently'})

# Errores de Meta (ya normalizados por 10B1) → (HTTP, campo, detalle fijo).
META_ERRORS = {
    'meta_not_configured': (503, None, 'Integración con Meta no configurada.'),
    'invalid_input': (400, None, 'Datos inválidos.'),
    'token_invalid': (422, 'access_token', 'Meta rechazó el token.'),
    'token_expired': (422, 'access_token', 'El token está vencido.'),
    'token_app_mismatch': (422, 'access_token', 'El token no pertenece a la aplicación de Mi Rubro.'),
    'data_access_expired': (422, 'access_token', 'El acceso a datos del token está vencido.'),
    'permissions_missing': (422, 'access_token', 'Faltan permisos de WhatsApp en el token.'),
    'resource_scope_not_granted': (422, 'waba_id', 'El token no cubre esa WABA.'),
    'resource_scope_unverified': (422, 'waba_id', 'No se pudo comprobar el alcance del token sobre la WABA.'),
    'permission_denied': (422, 'waba_id', 'Meta negó el acceso a la WABA.'),
    'resource_not_found': (422, 'waba_id', 'Meta no encontró la WABA.'),
    'phone_number_not_in_waba': (422, 'phone_number_id', 'El número no pertenece a esa WABA.'),
    'meta_request_rejected': (422, None, 'Meta rechazó la consulta.'),
    'meta_rate_limited': (503, None, 'Meta limitó las consultas; reintentar más tarde.'),
    'meta_unavailable': (503, None, 'Meta no está disponible; reintentar más tarde.'),
    'meta_invalid_response': (502, None, 'Respuesta inesperada de Meta.'),
    'meta_error': (502, None, 'Error de Meta.'),
}


def _no_store(body: dict, status: int = 200) -> Response:
    response = Response(body, status=status)
    response['Cache-Control'] = 'no-store'
    return response


def _error(status: int, code: str, detail: str, field: str | None = None, retryable: bool = False) -> Response:
    return _no_store({'code': code, 'detail': detail, 'field': field, 'retryable': retryable}, status)


def _client_not_found() -> Response:
    return _error(404, 'client_not_found', 'Cliente no encontrado.')


def _parse_link_body(data) -> tuple[dict | None, Response | None]:
    """Body exacto: solo los cuatro campos, todos texto. Los errores nunca repiten valores."""
    if not isinstance(data, dict):
        return None, _error(400, 'invalid_request', 'El cuerpo debe ser un objeto JSON.')
    unexpected = sorted(set(data) - set(LINK_FIELDS))
    if unexpected:
        return None, _error(400, 'unexpected_fields', f'Campos no admitidos: {", ".join(unexpected)}.', unexpected[0])
    for field in LINK_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value or len(value) > LINK_FIELD_MAX_LENGTH:
            return None, _error(400, 'invalid_field', 'Campo requerido o inválido.', field)
    return {field: data[field] for field in LINK_FIELDS}, None


class WhatsAppLinkThrottle(ScopedRateThrottle):
    """Throttle por usuario solo para el POST (el GET no lo consume)."""
    scope_attr = 'link_throttle_scope'


class AdminClientWhatsAppConnectionsView(APIView):
    http_method_names = ['get', 'post', 'head', 'options']
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    link_throttle_scope = 'admin_whatsapp_link'

    @property
    def allowed_internal_roles(self) -> list[str]:
        # Leer: superadmin u operations. Vincular: solo superadmin.
        return ['superadmin'] if self.request.method == 'POST' else ['superadmin', 'operations']

    def get_throttles(self):
        return [WhatsAppLinkThrottle()] if self.request.method == 'POST' else []

    def get(self, request, business_id: int):
        business = admin_reception_business(business_id)
        if business is None:
            return _client_not_found()
        return _no_store(admin_whatsapp_connections(business))

    def post(self, request, business_id: int):
        business = admin_reception_business(business_id)
        if business is None:
            return _client_not_found()
        body, invalid = _parse_link_body(request.data)
        if invalid is not None:
            return invalid
        try:
            result = link_whatsapp_channel(
                business=business, waba_id=body['waba_id'], phone_number_id=body['phone_number_id'],
                token=body['access_token'], actor=request.user, reason=body['reason'], source=SOURCE_ASSISTED,
            )
        except WhatsAppAuthorizationError as exc:
            if exc.code == 'client_not_eligible':
                return _client_not_found()
            status, field = LOCAL_ERRORS.get(exc.code, (409, None))
            return _error(status, exc.code, str(exc), field, exc.code in RETRYABLE_LOCAL)
        except MetaGraphError as exc:
            status, field, detail = META_ERRORS.get(exc.code, (502, None, 'Error de Meta.'))
            return _error(status, exc.code, detail, field, exc.transient)
        now = timezone.now()
        channel = AgentChannel.objects.select_related('agent_instance', 'whatsapp_authorization').get(
            pk=result.channel.pk,
        )
        return _no_store({
            'contract_version': ADMIN_WHATSAPP_CONNECTIONS_CONTRACT_VERSION,
            'business_id': business.pk,
            'outcome': result.outcome,
            'created_channel': result.created_channel,
            'created_authorization': result.created_authorization,
            'automatic_attention_enabled': result.automatic_attention_enabled,
            'evaluated_at': now.isoformat(),
            'channel': admin_whatsapp_channel(channel, now),
        }, 201 if result.outcome == OUTCOME_LINKED else 200)
