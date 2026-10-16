"""Deploy guard de la integración del agente (AGENT 02B).

Con `AGENT_INTEGRATION_ENABLED=true` el receiver exige una
`AGENT_SECRET_ENCRYPTION_KEY` Fernet válida; si falta, `manage.py check` /
`migrate` fallan (y la vista responde 503). Con el flag apagado (default) no
se exige nada: los entornos que no usan la integración no se rompen.
"""
from __future__ import annotations

import re

from cryptography.fernet import Fernet
from django.conf import settings
from django.core import checks


@checks.register(checks.Tags.security)
def check_agent_integration_config(app_configs=None, **kwargs):
    if not getattr(settings, 'AGENT_INTEGRATION_ENABLED', False):
        return []
    key = getattr(settings, 'AGENT_SECRET_ENCRYPTION_KEY', None)
    if not key:
        return [checks.Error(
            'AGENT_INTEGRATION_ENABLED=true requires AGENT_SECRET_ENCRYPTION_KEY.',
            hint='Generate a Fernet key and set AGENT_SECRET_ENCRYPTION_KEY, or disable the integration.',
            id='leads.E001',
        )]
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError):
        return [checks.Error(
            'AGENT_SECRET_ENCRYPTION_KEY is not a valid Fernet key.',
            id='leads.E002',
        )]
    return []


# MIRUBRO TAKEOVER 05A: credencial y endpoint del agente para comandos
# MiRubro → Agent. Solo se exige con AGENT_TAKEOVER_ENABLED=true. Los mensajes
# nombran la variable y la regla, nunca el valor.
TAKEOVER_SECRET_MIN_BYTES = 32
TAKEOVER_SECRET_MAX_BYTES = 512


@checks.register(checks.Tags.security)
def check_agent_takeover_config(app_configs=None, **kwargs):
    if not getattr(settings, 'AGENT_TAKEOVER_ENABLED', False):
        return []
    from urllib.parse import urlsplit

    from .models import KEY_ID_REGEX

    errors = []
    base_url = getattr(settings, 'AGENT_TAKEOVER_BASE_URL', '') or ''
    parts = urlsplit(base_url)
    if parts.scheme not in ('http', 'https') or not parts.netloc or parts.query or parts.fragment:
        errors.append(checks.Error(
            'AGENT_TAKEOVER_ENABLED=true requires AGENT_TAKEOVER_BASE_URL (http(s)://host[:port][/prefix]).',
            id='leads.E003',
        ))
    elif parts.scheme == 'http' and not settings.DEBUG:
        errors.append(checks.Error(
            'AGENT_TAKEOVER_BASE_URL must use https outside DEBUG (the agent rejects plain HTTP: tls_required).',
            id='leads.E006',
        ))
    key_id = getattr(settings, 'AGENT_TAKEOVER_KEY_ID', '') or ''
    if not re.fullmatch(KEY_ID_REGEX, key_id):
        errors.append(checks.Error(
            'AGENT_TAKEOVER_KEY_ID must match ^[A-Za-z0-9_.-]{1,64}$.', id='leads.E004',
        ))
    secret = getattr(settings, 'AGENT_TAKEOVER_SECRET', '') or ''
    size = len(secret.encode('utf-8'))
    if not TAKEOVER_SECRET_MIN_BYTES <= size <= TAKEOVER_SECRET_MAX_BYTES:
        errors.append(checks.Error(
            f'AGENT_TAKEOVER_SECRET must be {TAKEOVER_SECRET_MIN_BYTES}-{TAKEOVER_SECRET_MAX_BYTES} bytes.',
            id='leads.E005',
        ))
    return errors
