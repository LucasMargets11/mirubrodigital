"""Errores del API de integración del agente (Contract V1).

Formato uniforme, sin PII y sin eco de valores recibidos:

    {"ok": false, "error": {"code", "message", "retryable", "fields": [...]}}

`fields` solo lleva ruta del campo + código de error, nunca el valor.
"""
from __future__ import annotations

from rest_framework.exceptions import APIException


class AgentApiError(APIException):
    """Error de contrato con status, código y retryable explícitos."""

    def __init__(self, status_code: int, code: str, message: str, *, retryable: bool = False, fields=None):
        self.status_code = status_code
        self.error_code = code
        self.error_message = message
        self.retryable = retryable
        self.fields = list(fields or [])
        super().__init__(detail=message, code=code)

    def as_body(self) -> dict:
        return {
            'ok': False,
            'error': {
                'code': self.error_code,
                'message': self.error_message,
                'retryable': self.retryable,
                'fields': self.fields,
            },
        }


class AgentAuthenticationFailed(AgentApiError):
    """401 genérico: desde afuera todos los fallos de auth se ven iguales.

    `reason` es un código técnico que solo va al log (nunca a la respuesta).
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(401, 'invalid_signature', 'Firma inválida.')


def invalid_request(message: str = 'Request inválido.') -> AgentApiError:
    return AgentApiError(400, 'invalid_request', message)


def validation_error(fields) -> AgentApiError:
    return AgentApiError(400, 'validation_error', 'Payload inválido.', fields=fields)


def channel_disabled() -> AgentApiError:
    return AgentApiError(403, 'channel_disabled', 'Canal no habilitado.')


def business_inactive() -> AgentApiError:
    return AgentApiError(403, 'business_inactive', 'Negocio no habilitado para recibir consultas.')


def version_conflict() -> AgentApiError:
    return AgentApiError(409, 'version_conflict', 'Conflicto de versión o identidad del lead.')


def business_mismatch() -> AgentApiError:
    return AgentApiError(409, 'business_mismatch', 'El negocio informado no coincide con el canal.')


def rate_limited() -> AgentApiError:
    return AgentApiError(429, 'rate_limited', 'Demasiadas solicitudes.', retryable=True)


def unavailable() -> AgentApiError:
    return AgentApiError(503, 'unavailable', 'Servicio no disponible.', retryable=True)


def internal_error() -> AgentApiError:
    return AgentApiError(500, 'internal_error', 'Error interno.', retryable=True)


def flatten_serializer_errors(errors, prefix: str = '') -> list[dict]:
    """`serializer.errors` → `[{"field": "handoff.reasons[0].code", "code": "invalid_choice"}]`.

    Descarta los mensajes de DRF (algunos ecoan el valor recibido).
    """
    out: list[dict] = []
    if isinstance(errors, dict):
        for key, value in errors.items():
            name = 'non_field_errors' if key == 'non_field_errors' and not prefix else key
            path = f'{prefix}.{name}' if prefix and key != 'non_field_errors' else (prefix or name)
            out.extend(flatten_serializer_errors(value, path))
    elif isinstance(errors, list):
        if errors and all(isinstance(item, (dict, list)) for item in errors):
            for index, item in enumerate(errors):
                out.extend(flatten_serializer_errors(item, f'{prefix}[{index}]'))
        else:
            for item in errors:
                if isinstance(item, (dict, list)):
                    out.extend(flatten_serializer_errors(item, prefix))
                else:
                    out.append({'field': prefix, 'code': getattr(item, 'code', None) or 'invalid'})
    else:
        out.append({'field': prefix, 'code': getattr(errors, 'code', None) or 'invalid'})
    return out
