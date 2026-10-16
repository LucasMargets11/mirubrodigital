"""API de integración del agente (AGENT 02B).

`PUT /api/v1/integrations/agent/leads/<uuid:external_lead_id>/`

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
from .authentication import AgentHmacAuthentication, AgentPrincipal, well_formed_request_id
from .serializers import LeadSyncSerializer
from .services.receiver import receive_lead_sync
from .throttles import AgentLeadSyncThrottle

logger = logging.getLogger('apps.leads.receiver')


class IsAuthenticatedAgent(BasePermission):
    def has_permission(self, request, view) -> bool:
        return isinstance(request.user, AgentPrincipal)


class AgentLeadSyncView(APIView):
    authentication_classes = [AgentHmacAuthentication]
    permission_classes = [IsAuthenticatedAgent]
    throttle_classes = [AgentLeadSyncThrottle]
    parser_classes = [JSONParser]
    http_method_names = ['put']

    def initial(self, request, *args, **kwargs):
        self._started = time.monotonic()
        # Deploy guard en runtime: deshabilitado ⇒ 503 antes de tocar DB/HMAC.
        if not getattr(settings, 'AGENT_INTEGRATION_ENABLED', False):
            raise errors.unavailable()
        super().initial(request, *args, **kwargs)

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
        self._log_result(outcome.result, outcome.status_code, business_id=outcome.business_id)
        return Response(
            {
                'ok': True,
                'result': outcome.result,
                'external_lead_id': str(data['external_lead_id']),
                'received_version': outcome.received_version,
                'applied_version': outcome.applied_version,
                'mirubro_lead_id': str(outcome.lead.pk),
            },
            status=outcome.status_code,
        )

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
