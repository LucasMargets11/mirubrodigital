"""Cliente HMAC MiRubro → Agent para mensajes humanos (MIRUBRO HUMAN MESSAGES).

Contrato del agente: `docs/MIRUBRO_HUMAN_MESSAGES.md` del repo del bot. Mismo
esquema HMAC que `takeover_client` (Contract V1 §9, `contract.canonical_string`),
MISMA credencial (`AGENT_TAKEOVER_KEY_ID` / `AGENT_TAKEOVER_SECRET`): el agente
no tiene un secreto separado para esta dirección.

Cada intento HTTP lleva `X-Request-Id`, timestamp y firma NUEVOS; el body
(event_id, business_id, client_message_id, occurred_at, text) es idéntico
entre reintentos (mismo `client_message_id` = misma identidad lógica del
mensaje, el agente lo trata como reintento/duplicado). Nunca se loguea el
secreto, la firma, el canonical ni el body (el body incluye el texto del
paciente/recepción).

`send_message` nunca lanza por errores de transporte: devuelve un
`AgentMessageResponse` clasificado que el servicio traduce a estado.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from django.conf import settings

from .contract import body_sha256, canonical_string, compute_signature, format_utc

MESSAGE_PATH_TEMPLATE = '/integrations/mirubro/conversations/{external_conversation_id}/messages'
HTTP_METHOD = 'POST'
TEXT_MAX_CODE_POINTS = 4096

# Clasificación de la respuesta (lo que el servicio necesita para decidir).
KIND_OK = 'ok'                # 201 queued | 200 duplicate
KIND_RETRYABLE = 'retryable'  # 5xx, 429, red, timeout, 2xx ilegible
KIND_TERMINAL = 'terminal'    # 4xx del contrato, redirect, otro 4xx

ERROR_TIMEOUT = 'timeout'
ERROR_NETWORK = 'network_error'
ERROR_INVALID_RESPONSE = 'invalid_response'
ERROR_REDIRECT = 'unexpected_redirect'
ERROR_HTTP = 'http_{status}'

# Códigos de error documentados en el contrato (los demás 4xx → http_<status>).
KNOWN_AGENT_ERROR_CODES = frozenset({
    'invalid_payload', 'invalid_signature', 'human_messages_disabled', 'takeover_disabled', 'tls_required',
    'conversation_not_found', 'conversation_not_taken', 'business_mismatch', 'message_conflict',
    'outside_service_window',
})
RESULTS = ('queued', 'duplicate')


class HumanMessageClientConfigError(RuntimeError):
    """Falta configuración del cliente (base URL, key id o secret)."""


@dataclass(frozen=True)
class AgentMessageResponse:
    kind: str
    http_status: int | None = None
    result: str | None = None
    message_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class MessagePayload:
    external_conversation_id: str
    event_id: uuid.UUID
    client_message_id: uuid.UUID
    business_id: int
    occurred_at: dt.datetime
    text: str


def build_body(payload: MessagePayload) -> bytes:
    """Exactamente las 5 claves del contrato, orden fijo → bytes idénticos entre reintentos."""
    return json.dumps(
        {
            'event_id': str(payload.event_id).lower(),
            'business_id': int(payload.business_id),
            'client_message_id': str(payload.client_message_id).lower(),
            'occurred_at': format_utc(payload.occurred_at),
            'text': payload.text,
        },
        separators=(',', ':'),
    ).encode('utf-8')


def message_path(base_url: str, external_conversation_id: str) -> str:
    """Path exacto que firma y recibe el agente (prefijo de la base URL incluido, sin query)."""
    prefix = urlsplit(base_url).path.rstrip('/')
    return prefix + MESSAGE_PATH_TEMPLATE.format(external_conversation_id=external_conversation_id)


def build_request(payload: MessagePayload, *, base_url: str, key_id: str, secret: str,
                  timestamp: int, request_id: str) -> tuple[str, bytes, dict[str, str]]:
    path = message_path(base_url, payload.external_conversation_id)
    body = build_body(payload)
    canonical = canonical_string(
        method=HTTP_METHOD, path=path, timestamp=str(timestamp), request_id=request_id,
        key_id=key_id, body_hash=body_sha256(body),
    )
    parts = urlsplit(base_url)
    url = f'{parts.scheme}://{parts.netloc}{path}'
    headers = {
        'Content-Type': 'application/json',
        'X-Mirubro-Key-Id': key_id,
        'X-Mirubro-Timestamp': str(timestamp),
        'X-Request-Id': request_id,
        'X-Mirubro-Signature': compute_signature(secret, canonical),
    }
    return url, body, headers


def _config() -> tuple[str, str, str]:
    base_url = getattr(settings, 'AGENT_TAKEOVER_BASE_URL', '') or ''
    key_id = getattr(settings, 'AGENT_TAKEOVER_KEY_ID', '') or ''
    secret = getattr(settings, 'AGENT_TAKEOVER_SECRET', '') or ''
    if not (base_url and key_id and secret):
        raise HumanMessageClientConfigError('AGENT_TAKEOVER_BASE_URL/KEY_ID/SECRET not configured')
    return base_url, key_id, secret


def classify_response(status_code: int, body: bytes) -> AgentMessageResponse:
    try:
        data = json.loads(body.decode('utf-8')) if body else None
    except (UnicodeDecodeError, ValueError):
        data = None

    if status_code in (200, 201):
        if (
            isinstance(data, dict) and data.get('ok') is True and data.get('result') in RESULTS
            and isinstance(data.get('message_id'), str) and data['message_id']
        ):
            return AgentMessageResponse(
                kind=KIND_OK, http_status=status_code, result=data['result'], message_id=data['message_id'],
            )
        # 2xx ilegible (proxy, versión del bot): reintentar es seguro (mismo
        # client_message_id → el agente lo ve como duplicado si ya lo aplicó).
        return AgentMessageResponse(kind=KIND_RETRYABLE, http_status=status_code, error_code=ERROR_INVALID_RESPONSE)

    agent_code = None
    if isinstance(data, dict) and isinstance(data.get('error'), dict):
        code = data['error'].get('code')
        agent_code = code if code in KNOWN_AGENT_ERROR_CODES else None
    error_code = agent_code or ERROR_HTTP.format(status=status_code)

    if 300 <= status_code < 400:
        return AgentMessageResponse(kind=KIND_TERMINAL, http_status=status_code, error_code=ERROR_REDIRECT)
    if status_code >= 500 or status_code in (408, 429):
        return AgentMessageResponse(kind=KIND_RETRYABLE, http_status=status_code, error_code=error_code)
    return AgentMessageResponse(kind=KIND_TERMINAL, http_status=status_code, error_code=error_code)


def send_message(payload: MessagePayload, *, session: requests.Session | None = None) -> AgentMessageResponse:
    """Un intento HTTP (request_id/timestamp/firma nuevos). Sin redirects, timeout fijo."""
    base_url, key_id, secret = _config()
    url, body, headers = build_request(
        payload, base_url=base_url, key_id=key_id, secret=secret,
        timestamp=int(time.time()), request_id=str(uuid.uuid4()),
    )
    http = session or requests
    try:
        response = http.request(
            HTTP_METHOD, url, data=body, headers=headers,
            timeout=getattr(settings, 'AGENT_TAKEOVER_TIMEOUT_SECONDS', 10), allow_redirects=False,
        )
    except requests.Timeout:
        return AgentMessageResponse(kind=KIND_RETRYABLE, error_code=ERROR_TIMEOUT)
    except requests.RequestException:
        return AgentMessageResponse(kind=KIND_RETRYABLE, error_code=ERROR_NETWORK)
    return classify_response(response.status_code, response.content or b'')
