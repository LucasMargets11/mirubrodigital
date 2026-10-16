from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import MercadoPagoConnection

# ---------------------------------------------------------------------------
# Canonical merchant-side (Customer → Business) Mercado Pago credential
# resolution. Slice 5B.1, extended with refresh/lifecycle in Slice 5B.3B.
#
# Any flow where a customer pays a Business (Tips today, Turnos later) MUST
# resolve its Mercado Pago client through this module. There is no fallback
# to the platform's global MP_ACCESS_TOKEN here — that token belongs to
# apps.billing (Business → MiRubro subscriptions), a separate domain, and
# must never receive money that belongs to a merchant's own MP account.
#
# Refresh grant, per Mercado Pago's official OAuth reference (POST
# https://api.mercadopago.com/oauth/token, grant_type=refresh_token):
# access tokens issued by this flow are long-lived (~180 days) but MP
# rotates the refresh_token on every refresh — the new one MUST be stored,
# the old one becomes unusable. A rejected refresh_token (expired, revoked,
# already used, or belonging to another client) comes back as HTTP 400
# with error=invalid_grant.
# ---------------------------------------------------------------------------

# Small tolerance applied when deciding whether a token needs refreshing.
# Access tokens live for ~180 days, so this only exists to avoid a request
# using a token that is technically still valid when checked but expires
# before the downstream Mercado Pago call completes (request latency +
# clock drift between this server and MP's). It is intentionally small —
# proactive refresh isn't needed at this token lifetime, this is purely a
# request-safety margin. Centralized here so it is never hardcoded at each
# call site.
TOKEN_REFRESH_SKEW = datetime.timedelta(minutes=5)

MP_TOKEN_URL = 'https://api.mercadopago.com/oauth/token'

logger = logging.getLogger(__name__)


class MerchantPaymentConnectionUnavailable(Exception):
    """Raised when a Business has no usable Mercado Pago connection for
    merchant-side (Customer → Business) payments.

    Never include token values in the message — this exception's text may
    reach logs and, via a generic detail, API responses.
    """

    def __init__(self, business_id, reason: str):
        self.business_id = business_id
        self.reason = reason
        super().__init__(
            f"No hay una conexión de Mercado Pago utilizable para el negocio {business_id} ({reason})."
        )


def _needs_refresh(conn: MercadoPagoConnection) -> bool:
    if not conn.token_expires_at:
        return False
    return conn.token_expires_at <= timezone.now() + TOKEN_REFRESH_SKEW


def _apply_refresh_response(conn: MercadoPagoConnection, data: dict) -> None:
    """Persists a successful refresh response onto `conn` (not yet saved).

    Only overwrites fields Mercado Pago actually returned. `mp_user_id` is
    the one exception: it is never overwritten once set, only filled in if
    it was blank — a refresh response reporting a *different* user_id than
    what this connection was authorized under is treated as inconsistent
    and ignored (logged), never silently trusted.
    """
    conn.access_token = data['access_token']

    new_refresh_token = data.get('refresh_token')
    if new_refresh_token:
        conn.refresh_token = new_refresh_token

    expires_in = data.get('expires_in')
    conn.token_expires_at = (
        timezone.now() + datetime.timedelta(seconds=expires_in) if expires_in else None
    )

    scope = data.get('scope')
    if scope is not None:
        conn.scope = scope

    returned_user_id = data.get('user_id')
    if returned_user_id is not None:
        returned_user_id = str(returned_user_id)
        if not conn.mp_user_id:
            conn.mp_user_id = returned_user_id
        elif returned_user_id != conn.mp_user_id:
            logger.warning(
                "[MP refresh] business=%s: refresh response user_id=%s does not match "
                "stored mp_user_id=%s — ignoring, not overwriting.",
                conn.business_id, returned_user_id, conn.mp_user_id,
            )

    conn.status = 'connected'
    conn.last_error = ''


def refresh_merchant_connection(conn: MercadoPagoConnection) -> MercadoPagoConnection:
    """
    Refreshes `conn`'s access token via Mercado Pago's refresh_token grant
    and persists the result.

    Caller MUST hold a `select_for_update()` lock on `conn`'s row, inside an
    open `transaction.atomic()` block, and that block must NOT be exited
    with this call's exception still propagating — a failure here writes a
    safe-state marker (`status`/`last_error`) onto `conn` that must survive
    even though the overall flow ultimately reports an error to the caller.
    See `get_merchant_connection` for the calling pattern.

    Raises MerchantPaymentConnectionUnavailable on any failure. Never falls
    back to the platform's global token — an unusable business connection
    is a hard stop for merchant-side payments, not a degraded mode.
    """
    if not conn.refresh_token:
        conn.status = 'error'
        conn.last_error = 'no_refresh_token'
        conn.save(update_fields=['status', 'last_error', 'updated_at'])
        raise MerchantPaymentConnectionUnavailable(conn.business_id, 'no_refresh_token')

    try:
        resp = requests.post(
            MP_TOKEN_URL,
            json={
                'client_id': getattr(settings, 'MP_CLIENT_ID', ''),
                'client_secret': getattr(settings, 'MP_CLIENT_SECRET', ''),
                'grant_type': 'refresh_token',
                'refresh_token': conn.refresh_token,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning("[MP refresh] business=%s: network error (%s)", conn.business_id, exc)
        # Transient — leave status/last_error untouched so a retry on the
        # next request can succeed without needing manual reconnection.
        raise MerchantPaymentConnectionUnavailable(conn.business_id, 'refresh_temporarily_unavailable') from None

    if resp.status_code == 400:
        # invalid_grant: refresh_token expired/revoked/already-used/wrong client.
        # Definitively rejected — MP will never accept this refresh_token again.
        conn.status = 'error'
        conn.last_error = 'refresh_rejected'
        conn.save(update_fields=['status', 'last_error', 'updated_at'])
        raise MerchantPaymentConnectionUnavailable(conn.business_id, 'refresh_rejected')

    if resp.status_code != 200:
        # Any other non-2xx (5xx, rate limit, etc.) is treated as transient —
        # same reasoning as the network-error branch above.
        logger.warning(
            "[MP refresh] business=%s: unexpected status %s", conn.business_id, resp.status_code,
        )
        raise MerchantPaymentConnectionUnavailable(conn.business_id, 'refresh_temporarily_unavailable')

    try:
        data = resp.json()
        if 'access_token' not in data or not data['access_token']:
            raise ValueError('missing access_token')
    except (ValueError, TypeError):
        conn.status = 'error'
        conn.last_error = 'invalid_refresh_response'
        conn.save(update_fields=['status', 'last_error', 'updated_at'])
        raise MerchantPaymentConnectionUnavailable(conn.business_id, 'invalid_refresh_response') from None

    _apply_refresh_response(conn, data)
    conn.save(update_fields=[
        'access_token', 'refresh_token', 'token_expires_at', 'scope',
        'mp_user_id', 'status', 'last_error', 'updated_at',
    ])
    return conn


def _resolve_and_refresh_locked(business) -> tuple[MercadoPagoConnection | None, Exception | None]:
    """Runs inside a `select_for_update()` lock. Never raises — returns
    (connection, None) on success or (None, error) on failure, so the
    caller's `transaction.atomic()` block always exits cleanly and any
    safe-state writes from a failed refresh are committed rather than
    rolled back by a propagating exception.
    """
    try:
        conn = MercadoPagoConnection.objects.select_for_update().get(business=business)
    except MercadoPagoConnection.DoesNotExist:
        return None, MerchantPaymentConnectionUnavailable(business.id, 'not_connected')

    if conn.status != 'connected':
        return None, MerchantPaymentConnectionUnavailable(business.id, f'status={conn.status}')
    if not conn.access_token:
        return None, MerchantPaymentConnectionUnavailable(business.id, 'missing_access_token')

    if not _needs_refresh(conn):
        return conn, None

    try:
        conn = refresh_merchant_connection(conn)
    except MerchantPaymentConnectionUnavailable as exc:
        return None, exc

    return conn, None


def get_merchant_connection(business) -> MercadoPagoConnection:
    """
    Resolves a usable MercadoPagoConnection for `business`, refreshing its
    access token first if it is expired or near expiry (see
    `TOKEN_REFRESH_SKEW`).

    Locks the connection row for the duration of the check-and-maybe-refresh
    so that concurrent callers for the same business never trigger more than
    one remote refresh: the first caller to acquire the lock refreshes and
    commits; every other caller blocks on the lock, then re-reads the
    already-refreshed row and returns it without calling Mercado Pago again.

    Raises MerchantPaymentConnectionUnavailable if the business has no
    connection, it exists but cannot be used, or a needed refresh failed.
    Never falls back to any other Business's connection or to a
    platform-level token.
    """
    with transaction.atomic():
        conn, error = _resolve_and_refresh_locked(business)

    if error is not None:
        raise error
    return conn


def get_merchant_mp_client(business):
    """Builds a mercadopago.SDK client authenticated as `business`'s own MP account."""
    import mercadopago

    conn = get_merchant_connection(business)
    return mercadopago.SDK(conn.access_token)


# ---------------------------------------------------------------------------
# Preference creation (Slice 6A). Generic merchant-side primitive — it knows
# nothing about any consumer domain (Turnos, Tips, ...): the caller builds
# the preference body and owns its own local state machine.
#
# Mercado Pago does NOT officially document idempotency for
# POST /checkout/preferences (X-Idempotency-Key is only documented as
# mandatory for the Payments and Refunds APIs). So this primitive never
# relies on it and never retries: every call either
#   - CREATED:   MP answered 2xx with a usable id + init_point;
#   - REJECTED:  MP definitively did not create anything (a 4xx it
#                rejected, or the connection was never established) —
#                safe for the caller to record a terminal error;
#   - UNCERTAIN: the preference MAY exist remotely (timeout after the
#                request was sent, 5xx, unparseable/incomplete 2xx...).
#                The caller must NOT create another preference for the
#                same attempt automatically; it must park the attempt in a
#                blocking, observable state for manual reconciliation
#                (MP preference search by external_reference).
# ---------------------------------------------------------------------------

# Seconds. Explicit instead of the SDK default (60s) so a public request
# fails fast; the result of a timeout is UNCERTAIN, never retried.
PREFERENCE_CREATE_TIMEOUT = 20.0

# 4xx answers where Mercado Pago rejected the request without creating
# anything. 408/409/423 are deliberately excluded (their outcome is not
# provably "nothing was created").
_PREFERENCE_REJECTED_STATUSES = frozenset({400, 401, 403, 404, 422, 429})


class PreferenceOutcome:
    CREATED = 'created'
    REJECTED = 'rejected'
    UNCERTAIN = 'uncertain'


@dataclass(frozen=True)
class MerchantPreferenceResult:
    outcome: str
    preference_id: str | None = None
    init_point: str | None = None
    # HTTP status from MP (None when no response was received), or a short
    # internal code. Never a token, never the raw MP payload.
    detail: str = ''


def create_merchant_preference(business, preference_data: dict) -> MerchantPreferenceResult:
    """
    Creates a Checkout Pro preference in `business`'s own Mercado Pago
    account (resolved via `get_merchant_mp_client`, so it inherits
    decrypt/refresh/locking/fail-safe — never the platform token).

    Raises MerchantPaymentConnectionUnavailable BEFORE any remote call if
    the business has no usable connection. Otherwise never raises: returns
    a MerchantPreferenceResult (see the block comment above for semantics).
    Automatic SDK retries are disabled for this POST.
    """
    from mercadopago.config import RequestOptions

    sdk = get_merchant_mp_client(business)
    request_options = RequestOptions(
        connection_timeout=PREFERENCE_CREATE_TIMEOUT,
        max_retries=0,
    )

    try:
        result = sdk.preference().create(preference_data, request_options)
    except requests.exceptions.ConnectTimeout:
        # The TCP/TLS connection was never established: the request body
        # never reached Mercado Pago.
        logger.warning("[MP preference] business=%s: connect timeout", business.id)
        return MerchantPreferenceResult(PreferenceOutcome.REJECTED, detail='connect_timeout')
    except Exception as exc:  # noqa: BLE001 — anything else may have reached MP
        logger.error(
            "[MP preference] business=%s: uncertain outcome (%s)", business.id, type(exc).__name__,
        )
        return MerchantPreferenceResult(PreferenceOutcome.UNCERTAIN, detail=type(exc).__name__[:64])

    http_status = result.get('status') if isinstance(result, dict) else None
    response = result.get('response') if isinstance(result, dict) else None

    if http_status in (200, 201):
        response = response if isinstance(response, dict) else {}
        preference_id = response.get('id')
        init_point = response.get('init_point')
        if preference_id and init_point:
            return MerchantPreferenceResult(
                PreferenceOutcome.CREATED,
                preference_id=str(preference_id),
                init_point=str(init_point),
                detail=str(http_status),
            )
        # 2xx but unusable: a preference may well exist remotely.
        logger.error(
            "[MP preference] business=%s: 2xx without id/init_point (id_present=%s)",
            business.id, bool(preference_id),
        )
        return MerchantPreferenceResult(
            PreferenceOutcome.UNCERTAIN,
            preference_id=str(preference_id) if preference_id else None,
            detail=f'{http_status}_incomplete',
        )

    error_code = ''
    if isinstance(response, dict):
        error_code = str(response.get('error') or '')[:64]
    logger.error(
        "[MP preference] business=%s: status=%s error=%s", business.id, http_status, error_code or '-',
    )
    if http_status in _PREFERENCE_REJECTED_STATUSES:
        return MerchantPreferenceResult(PreferenceOutcome.REJECTED, detail=str(http_status))
    return MerchantPreferenceResult(PreferenceOutcome.UNCERTAIN, detail=str(http_status))


def get_merchant_payment(business, payment_id: str) -> dict | None:
    """
    Authoritative re-fetch of a payment, using `business`'s own Mercado Pago
    connection. Returns None on error/not-found — never falls back to any
    other credential.
    """
    sdk = get_merchant_mp_client(business)
    try:
        result = sdk.payment().get(payment_id)
    except Exception:
        return None

    if result.get('status') not in (200, 201):
        return None
    return result.get('response') or None
