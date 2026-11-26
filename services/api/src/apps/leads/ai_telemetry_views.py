"""PROD-02E4A — `POST /api/v1/integrations/agent/ai-executions/`.

Ingesta de telemetría operativa de IA (un intento real contra el proveedor por
request). Auth HMAC Contract V1 de la instancia (nonce fail-closed), throttle
por instancia fail-closed, flag `AGENT_AI_TELEMETRY_ENABLED` (apagado ⇒ 503,
reintentable) además de `AGENT_INTEGRATION_ENABLED`. Nunca autoriza IA: para
eso está `/api/internal/appointments/ai-usage/authorize/`.

Respuestas (envelope Contract V1, sin eco de valores):
  201 {"ok": true, "result": "recorded",  "event_id": "<uuid>"}
  200 {"ok": true, "result": "duplicate", "event_id": "<uuid>"}
  400 validation_error (fields: ruta + código) · 401 invalid_signature
  403 channel_not_authorized · 409 idempotency_conflict · 429 · 503
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response

from . import errors
from .authentication import AgentHmacAuthentication
from .models import (
    AI_TELEMETRY_ERROR_CODES, AI_TELEMETRY_MAX_LATENCY_MS, AI_TELEMETRY_MAX_TOKENS, AI_TELEMETRY_MODEL_REGEX,
    AI_TELEMETRY_OPERATIONS, AI_TELEMETRY_PROVIDER_REQUEST_ID_REGEX, AI_TELEMETRY_PROVIDERS, PHONE_NUMBER_ID_REGEX,
    AgentAIExecution,
)
from .services.ai_telemetry import RECORDED, record_ai_execution
from .throttles import AgentLeadSyncThrottle
from .views import AgentIntegrationView

logger = logging.getLogger('apps.leads.ai_telemetry')

# Ventana aceptada para `executed_at`: no futuro (tolerancia de reloj) y no más
# viejo que el outbox razonable del agente.
EXECUTED_AT_FUTURE_SKEW = timedelta(seconds=60)
EXECUTED_AT_MAX_AGE = timedelta(days=30)

REQUIRED = ('event_id', 'phone_number_id', 'provider', 'model', 'operation', 'status', 'executed_at')
OPTIONAL = ('interaction_id', 'error_code', 'input_tokens', 'output_tokens', 'cached_input_tokens',
            'provider_request_id', 'latency_ms')
_UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
_PHONE_RE = re.compile(PHONE_NUMBER_ID_REGEX)
_MODEL_RE = re.compile(AI_TELEMETRY_MODEL_REGEX)
_REQUEST_ID_RE = re.compile(AI_TELEMETRY_PROVIDER_REQUEST_ID_REGEX)


class AITelemetryHmacAuthentication(AgentHmacAuthentication):
    nonce_fail_closed = True


class AITelemetryThrottle(AgentLeadSyncThrottle):
    scope = 'agent_ai_telemetry'
    fail_closed = True


def validate_execution(body) -> dict:
    """Validación estricta (sin coerciones). AgentApiError(400) con rutas + códigos."""
    if not isinstance(body, dict):
        raise errors.invalid_request('Se espera un objeto JSON.')
    problems = []

    def bad(field, code):
        problems.append({'field': field, 'code': code})

    for key in body:
        if key not in REQUIRED and key not in OPTIONAL:
            bad(key, 'unknown_field')
    for key in REQUIRED:
        if body.get(key) is None:
            bad(key, 'required')
    data = {key: None for key in OPTIONAL}

    def uuid_field(key):
        value = body.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
            bad(key, 'invalid_uuid')
            return None
        return uuid.UUID(value)

    def choice(key, allowed):
        value = body.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or value not in allowed:
            bad(key, 'invalid_choice')
            return None
        return value

    def pattern(key, regex):
        value = body.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not regex.fullmatch(value):
            bad(key, 'invalid_format')
            return None
        return value

    def count(key, maximum):
        value = body.get(key)
        if value is None:
            return None
        # bool es subclase de int: se rechaza igual que floats y strings.
        if type(value) is not int or value < 0 or value > maximum:
            bad(key, 'invalid_number')
            return None
        return value

    data['event_id'] = uuid_field('event_id')
    data['interaction_id'] = uuid_field('interaction_id')
    data['phone_number_id'] = pattern('phone_number_id', _PHONE_RE)
    data['provider'] = choice('provider', AI_TELEMETRY_PROVIDERS)
    data['model'] = pattern('model', _MODEL_RE)
    data['operation'] = choice('operation', AI_TELEMETRY_OPERATIONS)
    data['status'] = choice('status', tuple(AgentAIExecution.Status.values))
    data['error_code'] = choice('error_code', AI_TELEMETRY_ERROR_CODES)
    data['provider_request_id'] = pattern('provider_request_id', _REQUEST_ID_RE)
    for key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
        data[key] = count(key, AI_TELEMETRY_MAX_TOKENS)
    data['latency_ms'] = count('latency_ms', AI_TELEMETRY_MAX_LATENCY_MS)

    raw_at = body.get('executed_at')
    if raw_at is not None:
        try:
            at = parse_datetime(raw_at) if isinstance(raw_at, str) and len(raw_at) <= 40 else None
        except ValueError:
            at = None
        if at is None or timezone.is_naive(at):
            bad('executed_at', 'invalid_datetime')
        else:
            now = timezone.now()
            if at > now + EXECUTED_AT_FUTURE_SKEW:
                bad('executed_at', 'in_future')
            elif at < now - EXECUTED_AT_MAX_AGE:
                bad('executed_at', 'too_old')
            else:
                data['executed_at'] = at

    status = data['status']
    if status == 'succeeded' and data['error_code'] is not None:
        bad('error_code', 'not_allowed_on_success')
    if status == 'failed' and body.get('error_code') is None:
        bad('error_code', 'required')
    if data['cached_input_tokens'] is not None and (
        data['input_tokens'] is None or data['cached_input_tokens'] > data['input_tokens']
    ):
        bad('cached_input_tokens', 'exceeds_input_tokens')

    if problems:
        # Orden estable y sin duplicados; nunca valores.
        seen, unique = set(), []
        for item in problems:
            key = (item['field'], item['code'])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        raise errors.validation_error(unique)
    return data


class AgentAIExecutionView(AgentIntegrationView):
    http_method_names = ['post']
    authentication_classes = [AITelemetryHmacAuthentication]
    throttle_classes = [AITelemetryThrottle]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)  # flag de integración + HMAC + throttle
        if not getattr(settings, 'AGENT_AI_TELEMETRY_ENABLED', False):
            raise errors.unavailable()

    def post(self, request):
        data = validate_execution(request.data)
        execution, result = record_ai_execution(request.user, data)
        self._logged = (result, execution.business_id, str(execution.event_id))
        return Response(
            {'ok': True, 'result': result, 'event_id': str(execution.event_id)},
            status=201 if result == RECORDED else 200,
        )

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        logged = getattr(self, '_logged', None)
        if logged is not None:
            # Solo identificadores técnicos: nunca tokens de contenido, prompts ni PII.
            logger.info(
                'agent_ai_execution result=%s business_id=%s event_id=%s request_id=%s status=%s',
                logged[0], logged[1], logged[2], self._request_id(), response.status_code,
            )
        return response
