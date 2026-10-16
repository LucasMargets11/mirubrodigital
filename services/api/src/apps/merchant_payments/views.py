from __future__ import annotations

import base64
import logging
import secrets
import urllib.parse

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership, HasPermission

from .models import MercadoPagoConnection
from .serializers import MercadoPagoConnectionStatusSerializer  # noqa: F401 — re-exported for callers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mercado Pago OAuth — per-business connection (moved from apps.menu, Slice 5A)
# ---------------------------------------------------------------------------

MP_OAUTH_BASE = 'https://auth.mercadopago.com.ar/authorization'
MP_TOKEN_URL = 'https://api.mercadopago.com/oauth/token'
_STATE_CACHE_PREFIX = 'mp_oauth_state:'
_STATE_TTL = 600  # 10 minutes

# Slice 7B.2 — which product started the OAuth flow. Closed server-side set:
# the client only picks a key, the callback only ever redirects to one of
# these fixed in-app paths (never a client-supplied URL → no open redirect).
# 'menu' keeps the historical landing and query params unchanged.
OAUTH_CONTEXT_MENU = 'menu'
OAUTH_CONTEXT_APPOINTMENTS = 'appointments'
_OAUTH_CONTEXTS = (OAUTH_CONTEXT_MENU, OAUTH_CONTEXT_APPOINTMENTS)
_APPOINTMENTS_RETURN_PATH = '/app/turnos/configuracion'
_MENU_RETURN_PATH = '/app/settings/online-menu'
# Slice 7B.2.1 — no valid state ⇒ the product that started the flow is
# unknown: land on the neutral app home instead of a Menú-only page.
_NEUTRAL_RETURN_PATH = '/app'


class IsBusinessOwnerOrAdmin(BasePermission):
    """Changing the Business's MP credentials is a financial action:
    only OWNER / ADMIN of the current Business (Slice 7B.2.1)."""
    message = 'Solo el dueño o un administrador del negocio puede cambiar la conexión con Mercado Pago.'

    def has_permission(self, request, view) -> bool:
        membership = resolve_request_membership(request)
        return membership is not None and membership.role in ('owner', 'admin')


def _consume_state(state_token):
    """Atomically consume a single-use OAuth state.

    Returns ``(business_id, context)`` or ``(None, None)`` when the state is
    unknown, expired or was already consumed. Only the request whose
    ``cache.delete`` actually removed the key wins, so two concurrent
    callbacks can never both use the same state.

    Entries written before Slice 7B.2 hold a bare business id (no context):
    they fall back to the historical Menu landing.
    """
    cache_key = f"{_STATE_CACHE_PREFIX}{state_token}"
    payload = cache.get(cache_key)
    if payload is None or not cache.delete(cache_key):
        return None, None
    if isinstance(payload, dict):
        context = payload.get('context')
        return payload.get('business_id'), context if context in _OAUTH_CONTEXTS else OAUTH_CONTEXT_MENU
    return payload, OAUTH_CONTEXT_MENU


class MercadoPagoOAuthStartView(APIView):
    """Start the OAuth flow for connecting a business's Mercado Pago account."""
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, IsBusinessOwnerOrAdmin]
    required_permission = 'manage_settings'

    def get(self, request):
        client_id = getattr(settings, 'MP_CLIENT_ID', None)
        redirect_uri = getattr(settings, 'MP_REDIRECT_URI', None)
        if not client_id or not redirect_uri:
            return Response(
                {'detail': 'MP OAuth no configurado en este servidor.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        context = request.query_params.get('context') or OAUTH_CONTEXT_MENU
        if context not in _OAUTH_CONTEXTS:
            return Response({'detail': 'Contexto inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        business = getattr(request, 'business')
        nonce = secrets.token_urlsafe(24)
        state_payload = f"{business.id}:{nonce}"
        state_token = base64.urlsafe_b64encode(state_payload.encode()).decode()

        # Store in cache to validate on callback. The business and the return
        # context live only server-side, bound to this single-use state.
        cache.set(
            f"{_STATE_CACHE_PREFIX}{state_token}",
            {'business_id': business.id, 'context': context},
            _STATE_TTL,
        )

        params = {
            'client_id': client_id,
            'response_type': 'code',
            'platform_id': 'mp',
            'redirect_uri': redirect_uri,
            'state': state_token,
        }
        auth_url = f"{MP_OAUTH_BASE}?{urllib.parse.urlencode(params)}"
        return Response({'auth_url': auth_url})


class MercadoPagoOAuthCallbackView(APIView):
    """Handle the OAuth callback and store tokens for a business."""
    permission_classes = [AllowAny]  # MP redirects here anonymously

    def get(self, request):
        code = request.query_params.get('code')
        state_token = request.query_params.get('state')
        error = request.query_params.get('error')

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')

        # Consume the state first (even on a MP-side error/cancel) so the
        # return context is known and the state can never be replayed.
        # context stays None when there is no valid state (missing, expired,
        # replayed): errors then land on the neutral home, never on Menú.
        business_id, context = _consume_state(state_token) if state_token else (None, None)

        if error:
            logger.warning(f"[MP OAuth] Error from MP: {error}")
            return self._redirect_error(frontend_url, error, context)

        if not code or not state_token:
            return self._redirect_error(frontend_url, 'missing_params', context)

        if not business_id:
            logger.warning("[MP OAuth] State token expired or invalid")
            return self._redirect_error(frontend_url, 'state_expired', context)

        client_id = getattr(settings, 'MP_CLIENT_ID', '')
        client_secret = getattr(settings, 'MP_CLIENT_SECRET', '')
        redirect_uri = getattr(settings, 'MP_REDIRECT_URI', '')

        # Exchange code for tokens
        try:
            resp = requests.post(MP_TOKEN_URL, json={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
            }, timeout=15)
            resp.raise_for_status()
            token_data = resp.json()
        except Exception as exc:
            logger.error(f"[MP OAuth] Token exchange failed: {exc}", exc_info=True)
            return self._redirect_error(frontend_url, 'token_exchange_failed', context)

        from apps.business.models import Business
        try:
            business = Business.objects.get(pk=business_id)
        except Business.DoesNotExist:
            return self._redirect_error(frontend_url, 'business_not_found', context)

        import datetime
        expires_in = token_data.get('expires_in', 0)
        expires_at = timezone.now() + datetime.timedelta(seconds=expires_in) if expires_in else None

        MercadoPagoConnection.objects.update_or_create(
            business=business,
            defaults={
                'access_token': token_data.get('access_token', ''),
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expires_at': expires_at,
                'mp_user_id': str(token_data.get('user_id', '')),
                'scope': token_data.get('scope', ''),
                'status': 'connected',
                'last_error': '',
            },
        )

        logger.info(f"[MP OAuth] Connected business {business_id} → MP user {token_data.get('user_id')}")
        from django.http import HttpResponseRedirect
        if context == OAUTH_CONTEXT_APPOINTMENTS:
            return HttpResponseRedirect(f"{frontend_url}{_APPOINTMENTS_RETURN_PATH}?mp=connected")
        return HttpResponseRedirect(f"{frontend_url}{_MENU_RETURN_PATH}?mp_connected=1")

    def _redirect_error(self, frontend_url, reason, context=None):
        from django.http import HttpResponseRedirect
        # Generic flag only for Turnos / neutral: the reason (possibly echoed
        # from MP) never reaches the URL.
        if context == OAUTH_CONTEXT_APPOINTMENTS:
            return HttpResponseRedirect(f"{frontend_url}{_APPOINTMENTS_RETURN_PATH}?mp=error")
        if context != OAUTH_CONTEXT_MENU:
            return HttpResponseRedirect(f"{frontend_url}{_NEUTRAL_RETURN_PATH}?mp=error")
        return HttpResponseRedirect(
            f"{frontend_url}{_MENU_RETURN_PATH}?mp_error={urllib.parse.quote(reason)}"
        )


class MercadoPagoConnectionStatusView(APIView):
    """Returns the MP connection status for the panel (no tokens exposed)."""
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_settings'

    def get(self, request):
        business = getattr(request, 'business')
        try:
            conn = business.mp_connection
            return Response({
                'connected': conn.status == 'connected',
                'status': conn.status,
                'mp_user_id': conn.mp_user_id,
                'updated_at': conn.updated_at,
            })
        except MercadoPagoConnection.DoesNotExist:
            return Response({'connected': False, 'status': None, 'mp_user_id': None, 'updated_at': None})


class MercadoPagoDisconnectView(APIView):
    """Disconnect the business's Mercado Pago connection.

    Remote revocation: Mercado Pago's OAuth reference documents authorization
    revocation only as something triggered by the seller (from their own MP
    account) or by MP-side events (password change, security action, app
    deletion) — there is no documented, supported API endpoint for a
    marketplace application to remotely revoke a specific user's
    authorization. Calling an undocumented endpoint would be relying on
    unspecified behavior for a security-sensitive operation, so this view
    does not attempt one. Local invalidation below does not depend on it:
    the business can always stop using this connection locally, even if
    Mercado Pago is unreachable.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, IsBusinessOwnerOrAdmin]
    required_permission = 'manage_settings'

    def delete(self, request):
        business = getattr(request, 'business')
        with transaction.atomic():
            conn = MercadoPagoConnection.objects.select_for_update().filter(business=business).first()
            if not conn:
                return Response({'detail': 'No había conexión activa.'}, status=status.HTTP_404_NOT_FOUND)
            conn.delete()
        return Response({'detail': 'Conexión con Mercado Pago eliminada.'})
