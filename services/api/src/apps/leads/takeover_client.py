"""Cliente HMAC MiRubro → Agent para comandos takeover/release (MIRUBRO TAKEOVER 05A).

Contrato del agente: `docs/MIRUBRO_TAKEOVER.md` del repo del bot (AGENT
TAKEOVER 01A). Mismo esquema HMAC que Agent → MiRubro (Contract V1 §9,
`contract.canonical_string`), con headers y credencial propios de esta
dirección (`AGENT_TAKEOVER_KEY_ID` / `AGENT_TAKEOVER_SECRET`, solo env).

Cada intento HTTP lleva `X-Request-Id`, timestamp y firma NUEVOS; el body
(event_id, version, occurred_at, business_id) es idéntico entre reintentos.
Nunca se loguea el secreto, la firma, el canonical ni el body.

`send_command` nunca lanza por errores de transporte: devuelve un
`AgentCommandResponse` clasificado que el servicio traduce a estado.
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

TAKEOVER_PATH_TEMPLATE = '/integrations/mirubro/conversations/{external_conversation_id}/{action}'
HTTP_METHOD = 'PUT'

# Clasificación de la respuesta (lo que el servicio necesita para decidir).
KIND_OK = 'ok'                # 200 con result applied|duplicate|stale
KIND_RETRYABLE = 'retryable'  # 5xx, 429, red, timeout, 200 ilegible
KIND_TERMINAL = 'terminal'    # 4xx del contrato, redirect, otro 4xx

ERROR_TIMEOUT = 'timeout'
ERROR_NETWORK = 'network_error'
ERROR_INVALID_RESPONSE = 'invalid_response'
ERROR_REDIRECT = 'unexpected_redirect'
ERROR_HTTP = 'http_{status}'
ERROR_AUTH = 'invalid_signature'

# Códigos de error del agente que se conservan tal cual (los demás → http_<status>).
KNOWN_AGENT_ERROR_CODES = frozenset({
    'invalid_payload', 'invalid_signature', 'takeover_disabled', 'tls_required',
    'conversation_not_found', 'version_conflict', 'business_mismatch',
})
RESULTS = ('applied', 'duplicate', 'stale')
AGENT_STATES = ('paused', 'active')


class TakeoverClientConfigError(RuntimeError):
    """Falta configuración del cliente (base URL, key id o secret)."""


@dataclass(frozen=True)
class AgentCommandResponse:
    kind: str
    http_status: int | None = None
    result: str | None = None
    applied_version: int | None = None
    agent_state: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class CommandPayload:
    external_conversation_id: str
    action: str
    event_id: uuid.UUID
    version: int
    occurred_at: dt.datetime
    business_id: int


def build_body(payload: CommandPayload) -> bytes:
    """Exactamente las 4 claves del contrato, orden fijo → bytes idénticos entre reintentos."""
    return json.dumps(
        {
            'event_id': str(payload.event_id).lower(),
            'version': int(payload.version),
            'occurred_at': format_utc(payload.occurred_at),
            'business_id': int(payload.business_id),
        },
        separators=(',', ':'),
    ).encode('utf-8')


def command_path(base_url: str, external_conversation_id: str, action: str) -> str:
    """Path exacto que firma y recibe el agente (prefijo de la base URL incluido, sin query)."""
    prefix = urlsplit(base_url).path.rstrip('/')
    return prefix + TAKEOVER_PATH_TEMPLATE.format(external_conversation_id=external_conversation_id, action=action)


def build_request(payload: CommandPayload, *, base_url: str, key_id: str, secret: str,
                  timestamp: int, request_id: str) -> tuple[str, bytes, dict[str, str]]:
    path = command_path(base_url, payload.external_conversation_id, payload.action)
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
        raise TakeoverClientConfigError('AGENT_TAKEOVER_BASE_URL/KEY_ID/SECRET not configured')
    return base_url, key_id, secret


def _safe_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def classify_response(status_code: int, body: bytes) -> AgentCommandResponse:
    try:
        data = json.loads(body.decode('utf-8')) if body else None
    except (UnicodeDecodeError, ValueError):
        data = None

    if status_code == 200:
        if (
            isinstance(data, dict) and data.get('ok') is True and data.get('result') in RESULTS
            and _safe_int(data.get('applied_version')) is not None and data.get('state') in AGENT_STATES
        ):
            return AgentCommandResponse(
                kind=KIND_OK, http_status=200, result=data['result'],
                applied_version=data['applied_version'], agent_state=data['state'],
            )
        # 200 ilegible (proxy, versión del bot): reintentar es seguro (idempotente).
        return AgentCommandResponse(kind=KIND_RETRYABLE, http_status=200, error_code=ERROR_INVALID_RESPONSE)

    agent_code = None
    if isinstance(data, dict) and isinstance(data.get('error'), dict):
        code = data['error'].get('code')
        agent_code = code if code in KNOWN_AGENT_ERROR_CODES else None
    error_code = agent_code or ERROR_HTTP.format(status=status_code)

    if 300 <= status_code < 400:
        return AgentCommandResponse(kind=KIND_TERMINAL, http_status=status_code, error_code=ERROR_REDIRECT)
    if status_code >= 500 or status_code in (408, 429):
        return AgentCommandResponse(kind=KIND_RETRYABLE, http_status=status_code, error_code=error_code)
    return AgentCommandResponse(kind=KIND_TERMINAL, http_status=status_code, error_code=error_code)


def send_command(payload: CommandPayload, *, session: requests.Session | None = None) -> AgentCommandResponse:
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
        return AgentCommandResponse(kind=KIND_RETRYABLE, error_code=ERROR_TIMEOUT)
    except requests.RequestException:
        return AgentCommandResponse(kind=KIND_RETRYABLE, error_code=ERROR_NETWORK)
    return classify_response(response.status_code, response.content or b'')
