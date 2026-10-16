"""Throttle del API de integración del agente (AGENT 02B).

Scope por `AgentInstance` (no por IP ni por key_id: una rotación de
credenciales no resetea el límite). Corre después de la autenticación HMAC,
así que solo cuenta requests firmadas válidas. Fail-open si el cache falla
(mismo criterio que `apps.accounts.throttles.FailOpenAnonThrottle`).
"""
from __future__ import annotations

import logging

from django.core.exceptions import ImproperlyConfigured
from rest_framework.throttling import SimpleRateThrottle

from .authentication import AgentPrincipal

logger = logging.getLogger('apps.leads.receiver')


class AgentLeadSyncThrottle(SimpleRateThrottle):
    scope = 'agent_leads_sync'

    def get_rate(self):
        from rest_framework.settings import api_settings

        rates = api_settings.DEFAULT_THROTTLE_RATES or {}
        if self.scope not in rates:
            raise ImproperlyConfigured(f"No default throttle rate set for '{self.scope}' scope")
        return rates[self.scope]

    def get_cache_key(self, request, view):
        principal = request.user
        if not isinstance(principal, AgentPrincipal):
            return None
        return self.cache_format % {'scope': self.scope, 'ident': str(principal.agent_instance.pk)}

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.error('RATE_LIMIT_REDIS_UNAVAILABLE throttle=%s', self.scope)
            return True
