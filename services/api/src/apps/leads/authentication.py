"""Autenticación HMAC service-to-service del agente (AGENT 02B, Contract V1).

Headers: `X-Agent-Key-Id`, `X-Agent-Timestamp` (unix s), `X-Request-Id`
(UUID), `X-Agent-Signature` (`v1=<hex minúscula>`). Sin JWT, cookies,
sesión, `X-Business-Id` ni Membership: el principal es técnico
(`AgentPrincipal`), nunca un User de Django.

Todo fallo responde 401 `invalid_signature` idéntico; el motivo real solo va
al log técnico junto con `key_id` y `request_id` (nunca headers completos,
firma, canonical string ni secretos).
"""
from __future__ import annotations

import hmac
import logging
import re
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import RequestDataTooBig
from rest_framework.authentication import BaseAuthentication

from . import errors
from .contract import (
    NONCE_TTL_SECONDS,
    TIMESTAMP_TOLERANCE_SECONDS,
    body_sha256,
    canonical_string,
    compute_signature,
)
from .crypto import SETTING_NAME as ENCRYPTION_KEY_SETTING, AgentSecretEncryptionError
from .models import KEY_ID_REGEX, AgentCredential, AgentInstance

logger = logging.getLogger('apps.leads.receiver')

MAX_BODY_BYTES = 64 * 1024

_KEY_ID_RE = re.compile(KEY_ID_REGEX)
_TIMESTAMP_RE = re.compile(r'^[0-9]{1,12}$')
_REQUEST_ID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
_SIGNATURE_RE = re.compile(r'^v1=[0-9a-f]{64}$')

ACCEPTED_CREDENTIAL_STATUSES = (AgentCredential.Status.ACTIVE, AgentCredential.Status.RETIRING)


@dataclass(frozen=True)
class AgentPrincipal:
    """Principal técnico autenticado (no es un User de Django)."""

    credential: AgentCredential
    agent_instance: AgentInstance
    request_id: str

    is_authenticated = True
    is_anonymous = False

    @property
    def key_id(self) -> str:
        return self.credential.key_id


def well_formed_request_id(value: str | None) -> str | None:
    return value if value and _REQUEST_ID_RE.match(value) else None


def _header(request, name: str) -> str | None:
    value = request.META.get('HTTP_' + name.upper().replace('-', '_'))
    return value if isinstance(value, str) else None


def _log_failure(reason: str, key_id: str | None, request_id: str | None) -> None:
    # Solo valores ya validados por regex (nunca el header crudo).
    safe_key = key_id if key_id and _KEY_ID_RE.match(key_id) else None
    logger.warning(
        'agent_auth_failed reason=%s key_id=%s request_id=%s',
        reason, safe_key, well_formed_request_id(request_id),
    )


def _fail(reason: str, key_id: str | None, request_id: str | None) -> errors.AgentAuthenticationFailed:
    _log_failure(reason, key_id, request_id)
    return errors.AgentAuthenticationFailed(reason)


class AgentHmacAuthentication(BaseAuthentication):

    def authenticate_header(self, request) -> str:
        return 'AgentHMAC'

    def authenticate(self, request):
        django_request = request._request
        key_id = _header(django_request, 'X-Agent-Key-Id')
        timestamp = _header(django_request, 'X-Agent-Timestamp')
        request_id = _header(django_request, 'X-Request-Id')
        signature = _header(django_request, 'X-Agent-Signature')

        # 1. Headers
        if not (
            key_id and _KEY_ID_RE.match(key_id)
            and timestamp and _TIMESTAMP_RE.match(timestamp)
            and request_id and _REQUEST_ID_RE.match(request_id)
            and signature and _SIGNATURE_RE.match(signature)
        ):
            raise _fail('malformed_headers', key_id, request_id)

        # Fail-closed por configuración: sin clave no hay verificación posible.
        if not getattr(settings, ENCRYPTION_KEY_SETTING, None):
            logger.error('agent_auth_unavailable reason=encryption_key_missing key_id=%s request_id=%s', key_id, request_id)
            raise errors.unavailable()

        # 2–4. Credencial → instancia
        credential = (
            AgentCredential.objects.select_related('agent_instance')
            .filter(key_id=key_id).first()
        )
        if credential is None:
            raise _fail('unknown_key', key_id, request_id)
        if credential.status not in ACCEPTED_CREDENTIAL_STATUSES:
            raise _fail('credential_revoked', key_id, request_id)
        instance = credential.agent_instance
        if not instance.is_enabled:
            raise _fail('instance_disabled', key_id, request_id)

        # 5. Secreto
        try:
            secret = credential.get_secret()
        except AgentSecretEncryptionError:
            raise _fail('secret_undecryptable', key_id, request_id)

        # 6. Ventana de timestamp
        if abs(int(time.time()) - int(timestamp)) > TIMESTAMP_TOLERANCE_SECONDS:
            raise _fail('timestamp_out_of_window', key_id, request_id)

        # 7. Body crudo (antes de cualquier parseo)
        try:
            raw_body = django_request.body
        except RequestDataTooBig:
            raise errors.invalid_request('Body demasiado grande.')
        if len(raw_body) > MAX_BODY_BYTES:
            raise errors.invalid_request('Body demasiado grande.')

        # 8–10. Canonical + HMAC + compare_digest
        canonical = canonical_string(
            method=django_request.method,
            path=django_request.path_info,
            timestamp=timestamp,
            request_id=request_id,
            key_id=key_id,
            body_hash=body_sha256(raw_body),
        )
        expected = compute_signature(secret, canonical)
        if not hmac.compare_digest(expected.encode('ascii'), signature.encode('ascii')):
            raise _fail('bad_signature', key_id, request_id)

        # 11. Replay (nonce). Fail-open SOLO si el cache falla: firma y
        # timestamp ya se verificaron y la idempotencia por versión hace
        # inocuo un PUT repetido.
        nonce_key = f'agent-req:{key_id}:{request_id.lower()}'
        try:
            first_use = cache.add(nonce_key, 1, timeout=NONCE_TTL_SECONDS)
        except Exception:
            logger.error('agent_nonce_unavailable key_id=%s request_id=%s', key_id, request_id)
            first_use = True
        if not first_use:
            raise _fail('replayed_request_id', key_id, request_id)

        return AgentPrincipal(credential=credential, agent_instance=instance, request_id=request_id), credential
