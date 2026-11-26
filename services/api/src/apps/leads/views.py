"""API de integración del agente (AGENT 02B).

`PUT /api/v1/integrations/agent/leads/<uuid:external_lead_id>/`
`GET /api/v1/integrations/agent/leads/<uuid:external_lead_id>/appointment-context/`
`GET /api/v1/integrations/agent/businesses/<id>/channels/<phone_number_id>/receptionist-config/` (PROD-03C)
`GET /api/v1/integrations/agent/channels/<phone_number_id>/whatsapp-credential/` (PROD-04C)

View fina: el flag de integración, la auth HMAC, el throttle y el formato de
respuesta viven acá; la lógica de tenant/idempotencia en
`services.receiver`. Toda respuesta (éxito o error) usa el envelope del
Contract V1 y lleva `X-Request-Id`.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import OperationalError
from rest_framework import exceptions as drf_exceptions
from rest_framework.parsers import JSONParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from . import errors
from .authentication import (
    AgentHmacAuthentication, AgentPrincipal, FailClosedAgentHmacAuthentication, well_formed_request_id,
)
from .serializers import LeadSyncSerializer
from .services.appointment_context import agent_appointment_context, appointment_context
from .services.receiver import receive_lead_sync
from .services.receptionist_config import agent_receptionist_config
from .services.whatsapp_authorizations import agent_whatsapp_credential
from .throttles import AgentLeadSyncThrottle, FailClosedAgentThrottle

logger = logging.getLogger('apps.leads.receiver')


class IsAuthenticatedAgent(BasePermission):
    def has_permission(self, request, view) -> bool:
        return isinstance(request.user, AgentPrincipal)


class AgentIntegrationView(APIView):
    authentication_classes = [AgentHmacAuthentication]
    permission_classes = [IsAuthenticatedAgent]
    throttle_classes = [AgentLeadSyncThrottle]
    parser_classes = [JSONParser]

    def initial(self, request, *args, **kwargs):
        self._started = time.monotonic()
        # Deploy guard en runtime: deshabilitado ⇒ 503 antes de tocar DB/HMAC.
        if not getattr(settings, 'AGENT_INTEGRATION_ENABLED', False):
            raise errors.unavailable()
        super().initial(request, *args, **kwargs)

    # ── Respuestas ────────────────────────────────────────────────────────

    def handle_exception(self, exc):
        if isinstance(exc, errors.AgentApiError):
            error = exc
        elif isinstance(exc, drf_exceptions.Throttled):
            error = errors.rate_limited()
        elif isinstance(exc, drf_exceptions.MethodNotAllowed):
            error = errors.AgentApiError(405, 'invalid_request', 'Método no permitido.')
        elif isinstance(exc, (drf_exceptions.ParseError, drf_exceptions.UnsupportedMediaType)):
            error = errors.invalid_request('Body inválido: se espera JSON.')
        elif isinstance(exc, (drf_exceptions.NotAuthenticated, drf_exceptions.AuthenticationFailed, drf_exceptions.PermissionDenied)):
            error = errors.AgentAuthenticationFailed('not_authenticated')
        elif isinstance(exc, (OperationalError,)):
            logger.error('agent_sync_unavailable exc=%s request_id=%s', type(exc).__name__, self._request_id())
            error = errors.unavailable()
        else:
            # Sin mensaje de la excepción: puede contener valores del payload.
            logger.error('agent_sync_internal_error exc=%s request_id=%s', type(exc).__name__, self._request_id())
            error = errors.internal_error()
        extra = {}
        if isinstance(error, errors.AgentAuthenticationFailed):
            extra['reason'] = error.reason
        if error.fields:
            # Solo ruta + código; nunca valores.
            extra['fields'] = ','.join(f"{item['field']}:{item['code']}" for item in error.fields)
        self._log_result(error.error_code, error.status_code, extra=extra)
        response = Response(error.as_body(), status=error.status_code)
        if isinstance(exc, drf_exceptions.Throttled) and exc.wait is not None:
            response['Retry-After'] = str(int(exc.wait) + 1)
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        request_id = self._request_id()
        if request_id:
            response['X-Request-Id'] = request_id
        return response

    # ── Logging técnico (sin PII) ─────────────────────────────────────────

    def _request_id(self) -> str | None:
        request = getattr(self, 'request', None)
        if request is None:
            return None
        return well_formed_request_id(request.META.get('HTTP_X_REQUEST_ID'))

    def _log_result(self, result: str, status_code: int, *, business_id=None, extra=None) -> None:
        request = getattr(self, 'request', None)
        data = getattr(self, '_data', None)
        principal = getattr(request, '_user', None)
        principal = principal if isinstance(principal, AgentPrincipal) else None
        started = getattr(self, '_started', None)
        latency_ms = int((time.monotonic() - started) * 1000) if started is not None else None
        fields = {
            'result': result,
            'status': status_code,
            'request_id': self._request_id(),
            'key_id': principal.key_id if principal else None,
            'agent_instance': principal.agent_instance.external_id if principal else None,
            'latency_ms': latency_ms,
        }
        if data is not None:
            fields.update({
                'business_id': business_id if business_id is not None else data['business_id'],
                'phone_number_id': data['phone_number_id'],
                'external_lead_id': str(data['external_lead_id']),
                'external_conversation_id': data['external_conversation_id'],
                'event_id': str(data['event_id']),
                'version': data['version'],
            })
        if extra:
            fields.update(extra)
        level = logging.INFO if status_code < 400 else logging.WARNING
        logger.log(level, 'agent_lead_sync ' + ' '.join(f'{key}=%s' for key in fields), *fields.values())


class AgentLeadSyncView(AgentIntegrationView):
    http_method_names = ['put']

    def put(self, request, external_lead_id):
        principal: AgentPrincipal = request.user
        try:
            payload = request.data
        except drf_exceptions.ParseError:
            raise errors.invalid_request('JSON inválido.')
        if not isinstance(payload, dict):
            raise errors.invalid_request('El body debe ser un objeto JSON.')

        serializer = LeadSyncSerializer(data=payload)
        if not serializer.is_valid():
            raise errors.validation_error(errors.flatten_serializer_errors(serializer.errors))
        data = self._data = serializer.validated_data

        if data['external_lead_id'] != external_lead_id:
            raise errors.invalid_request('external_lead_id del path y del body no coinciden.')

        outcome = receive_lead_sync(agent_instance=principal.agent_instance, data=data)
        context = appointment_context(outcome.lead)
        self._log_result(outcome.result, outcome.status_code, business_id=outcome.business_id)
        return Response(
            {
                'ok': True,
                'result': outcome.result,
                'external_lead_id': str(data['external_lead_id']),
                'received_version': outcome.received_version,
                'applied_version': outcome.applied_version,
                'mirubro_lead_id': str(outcome.lead.pk),
                **context,
            },
            status=outcome.status_code,
        )


class AgentAppointmentContextView(AgentIntegrationView):
    http_method_names = ['get']

    def get(self, request, external_lead_id):
        principal: AgentPrincipal = request.user
        body = agent_appointment_context(
            agent_instance=principal.agent_instance, external_lead_id=external_lead_id,
        )
        self._log_result('appointment_context', 200)
        response = Response(body)
        response['Cache-Control'] = 'no-store'
        return response


class AgentReceptionistConfigView(AgentIntegrationView):
    """PROD-03C: configuración de Recepcionista IA del negocio de este canal.

    Business y canal van en el path porque la firma HMAC cubre el path (no el
    query string). El tenant sale del canal activo de la instancia
    autenticada; `business_id` solo se contrasta (`business_mismatch`), igual
    que en `lead.sync`. No necesita Lead ni conversación previa.
    """

    http_method_names = ['get']

    def get(self, request, business_id, phone_number_id):
        principal: AgentPrincipal = request.user
        body = agent_receptionist_config(
            principal.agent_instance, phone_number_id=phone_number_id, business_id=int(business_id),
        )
        self._log_result(
            'receptionist_config', 200, extra={
                'business_id': body['business']['id'], 'phone_number_id': phone_number_id,
                'config_status': body['config']['status'], 'config_version': body['config']['version'],
            },
        )
        response = Response(body)
        response['Cache-Control'] = 'no-store'
        return response


class AgentWhatsAppCredentialView(AgentIntegrationView):
    """PROD-04C: credencial WhatsApp vigente del canal (token de Meta).

    El número va en el path firmado; el Business sale del canal activo de la
    instancia autenticada, sin que el agente lo conozca de antemano. Nonce y
    throttle fail-closed: sin Redis no se entrega ningún token. Nunca se
    loguea el token (solo negocio, número y vencimiento).
    """

    authentication_classes = [FailClosedAgentHmacAuthentication]
    throttle_classes = [FailClosedAgentThrottle]
    http_method_names = ['get']

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        # También en errores: ningún intermediario guarda respuestas de esta ruta.
        response['Cache-Control'] = 'no-store'
        return response

    def get(self, request, phone_number_id):
        principal: AgentPrincipal = request.user
        body = agent_whatsapp_credential(principal.agent_instance, phone_number_id=phone_number_id)
        self._log_result(
            'whatsapp_credential', 200, extra={
                'business_id': body['business_id'], 'phone_number_id': phone_number_id,
                'expires_at': body['expires_at'],
            },
        )
        return Response(body)
