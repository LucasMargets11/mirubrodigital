"""Cliente de servidor de Meta Graph API y verificación de recursos WhatsApp (PROD-10B1).

Capa común para la vinculación asistida (PROD-10) y Embedded Signup
(PROD-11): la verificación es la misma sin importar cómo se obtuvo el token.
Este módulo solo LEE de Meta y nunca escribe en la base: no persiste tokens,
no toca `AgentChannel` ni `WhatsAppAuthorization`, no suscribe webhooks ni
registra números.

Transporte (mismo patrón que `takeover_client`, con `requests`):
- host oficial fijo `https://graph.facebook.com`, versión configurada y
  validada, paths construidos solo con ids numéricos validados;
- timeout acotado, sin redirects, sin reintentos automáticos;
- cuerpo leído en streaming con tope de tamaño;
- el app access token y el token del recurso van en el header
  `Authorization`; el único secreto que viaja en la query es `input_token`
  de `debug_token` (lo exige el contrato de Meta) y el logger de urllib3 lo
  redacta (`_RedactCredentialsFilter`);
- la paginación usa `paging.cursors.after` y reconstruye la URL: nunca se
  sigue `paging.next` (Meta incluye ahí el access_token).

Errores normalizados (`MetaGraphError.code`), nunca el cuerpo ni el mensaje
de Meta. `transient=True` = puede reintentarse más tarde (el llamador decide).

Referencias (leídas 2026-11-28):
- debug_token: https://developers.facebook.com/docs/graph-api/reference/debug_token
- phone_numbers: https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-phone-numbers
- subscribed_apps: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/override
- permisos/tokens: https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/
- versiones: https://developers.facebook.com/docs/graph-api/changelog/versions/
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.utils import timezone

from ..models import PHONE_NUMBER_ID_REGEX, WABA_ID_REGEX
from .whatsapp_authorizations import TOKEN_MAX_LENGTH, TOKEN_MIN_LENGTH, _TOKEN_RE

logger = logging.getLogger('apps.leads.meta_graph')

GRAPH_HOST = 'https://graph.facebook.com'
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PAGES = 10
PAGE_LIMIT = 100
REQUIRED_PERMISSIONS = ('whatsapp_business_management', 'whatsapp_business_messaging')
PHONE_FIELDS = 'id,display_phone_number,verified_name,code_verification_status,quality_rating,platform_type'

_VERSION_RE = re.compile(r'^v[0-9]{1,3}\.[0-9]$')
_APP_ID_RE = re.compile(r'^[0-9]{1,32}$')
_WABA_RE = re.compile(WABA_ID_REGEX)
_PHONE_RE = re.compile(PHONE_NUMBER_ID_REGEX)
_CURSOR_RE = re.compile(r'^[A-Za-z0-9_\-=]{1,512}$')

# Códigos de error normalizados.
NOT_CONFIGURED = 'meta_not_configured'
INVALID_INPUT = 'invalid_input'
TOKEN_INVALID = 'token_invalid'
TOKEN_EXPIRED = 'token_expired'
TOKEN_APP_MISMATCH = 'token_app_mismatch'
DATA_ACCESS_EXPIRED = 'data_access_expired'
PERMISSIONS_MISSING = 'permissions_missing'
SCOPE_NOT_GRANTED = 'resource_scope_not_granted'
SCOPE_UNVERIFIED = 'resource_scope_unverified'
PERMISSION_DENIED = 'permission_denied'
RESOURCE_NOT_FOUND = 'resource_not_found'
PHONE_NOT_IN_WABA = 'phone_number_not_in_waba'
REQUEST_REJECTED = 'meta_request_rejected'
RATE_LIMITED = 'meta_rate_limited'
UNAVAILABLE = 'meta_unavailable'
INVALID_RESPONSE = 'meta_invalid_response'
META_ERROR = 'meta_error'

# Códigos de Meta (https://developers.facebook.com/docs/graph-api/guides/error-handling).
_TOKEN_CODES = frozenset({102, 190})
_TOKEN_EXPIRED_SUBCODES = frozenset({463, 467})
_PERMISSION_CODES = frozenset({10, *range(200, 300)})
_RATE_LIMIT_CODES = frozenset({4, 17, 32, 613, 80007, 80008, 130429})
_TRANSIENT_CODES = frozenset({1, 2})
_NOT_FOUND_SUBCODES = frozenset({33})


class MetaGraphError(Exception):
    """Falla normalizada. El mensaje es fijo: nunca incluye tokens, URLs ni texto de Meta."""

    def __init__(self, code: str, *, transient: bool = False, http_status: int | None = None,
                 meta_code: int | None = None, meta_subcode: int | None = None, detail: str = ''):
        super().__init__(code)
        self.code = code
        self.transient = transient
        self.http_status = http_status
        self.meta_code = meta_code
        self.meta_subcode = meta_subcode
        # Solo metadatos propios (p. ej. nombres de permisos faltantes), nunca datos de Meta crudos.
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return f'MetaGraphError({self.code!r}, transient={self.transient})'


# ── Redacción en logs HTTP ────────────────────────────────────────────────────

_SECRET_PARAM_RE = re.compile(
    r'((?:input_token|access_token|appsecret_proof|client_secret|code|fb_exchange_token)=)[^&\s"\']+'
)


class _RedactCredentialsFilter(logging.Filter):
    """urllib3 loguea en DEBUG la línea `GET /path?query`: se redactan credenciales."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — un log mal formado no debe filtrar secretos
            return False
        redacted = _SECRET_PARAM_RE.sub(r'\1[REDACTED]', message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


_URLLIB3_LOGGER = logging.getLogger('urllib3.connectionpool')
if not any(isinstance(f, _RedactCredentialsFilter) for f in _URLLIB3_LOGGER.filters):
    _URLLIB3_LOGGER.addFilter(_RedactCredentialsFilter())


# ── Configuración ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Config:
    app_id: str
    app_secret: str
    version: str
    timeout: float

    @property
    def app_access_token(self) -> str:
        # Solo en memoria y solo en el header Authorization.
        return f'{self.app_id}|{self.app_secret}'


def _config() -> _Config:
    app_id = getattr(settings, 'WHATSAPP_APP_ID', '') or ''
    app_secret = getattr(settings, 'WHATSAPP_APP_SECRET', '') or ''
    version = getattr(settings, 'WHATSAPP_GRAPH_VERSION', '') or ''
    timeout = getattr(settings, 'WHATSAPP_GRAPH_TIMEOUT_SECONDS', 10)
    if (
        not _APP_ID_RE.fullmatch(app_id) or not isinstance(app_secret, str) or len(app_secret) < 16
        or not _VERSION_RE.fullmatch(version)
        or not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 30
    ):
        raise MetaGraphError(NOT_CONFIGURED)
    return _Config(app_id=app_id, app_secret=app_secret, version=version, timeout=float(timeout))


def _validate_token(token) -> None:
    if not isinstance(token, str) or not (TOKEN_MIN_LENGTH <= len(token) <= TOKEN_MAX_LENGTH) \
            or not _TOKEN_RE.fullmatch(token):
        raise MetaGraphError(INVALID_INPUT, detail='token')


def _validate_id(value, regex: re.Pattern, name: str) -> str:
    if not isinstance(value, str) or not regex.fullmatch(value):
        raise MetaGraphError(INVALID_INPUT, detail=name)
    return value


# ── Transporte ────────────────────────────────────────────────────────────────

def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _read_body(response) -> bytes:
    length = response.headers.get('Content-Length') if response.headers else None
    if length is not None:
        try:
            if int(length) > MAX_RESPONSE_BYTES:
                raise MetaGraphError(INVALID_RESPONSE, http_status=response.status_code)
        except ValueError:
            raise MetaGraphError(INVALID_RESPONSE, http_status=response.status_code) from None
    chunks, size = [], 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise MetaGraphError(INVALID_RESPONSE, http_status=response.status_code)
        chunks.append(chunk)
    return b''.join(chunks)


def _classify_error(status: int, data) -> MetaGraphError:
    error = data.get('error') if isinstance(data, dict) else None
    code = _int(error.get('code')) if isinstance(error, dict) else None
    subcode = _int(error.get('error_subcode')) if isinstance(error, dict) else None
    transient_flag = isinstance(error, dict) and error.get('is_transient') is True
    meta = dict(http_status=status, meta_code=code, meta_subcode=subcode)
    if status == 429 or code in _RATE_LIMIT_CODES:
        return MetaGraphError(RATE_LIMITED, transient=True, **meta)
    if code in _TOKEN_CODES:
        return MetaGraphError(TOKEN_EXPIRED if subcode in _TOKEN_EXPIRED_SUBCODES else TOKEN_INVALID, **meta)
    if code in _PERMISSION_CODES:
        return MetaGraphError(PERMISSION_DENIED, **meta)
    if code == 100 and subcode in _NOT_FOUND_SUBCODES:
        return MetaGraphError(RESOURCE_NOT_FOUND, **meta)
    if status >= 500 or code in _TRANSIENT_CODES or transient_flag:
        return MetaGraphError(UNAVAILABLE, transient=True, **meta)
    if code == 100:
        return MetaGraphError(REQUEST_REJECTED, **meta)
    if status in (401, 403):
        return MetaGraphError(TOKEN_INVALID if status == 401 else PERMISSION_DENIED, **meta)
    return MetaGraphError(META_ERROR, **meta)


class MetaGraphClient:
    """Lecturas de Graph API. Un intento por llamada; nunca loguea secretos ni respuestas."""

    def __init__(self, *, session: requests.Session | None = None):
        self._config = _config()
        self._http = session or requests

    def _get(self, path: str, *, bearer: str, params: dict | None = None) -> dict:
        url = f'{GRAPH_HOST}/{self._config.version}/{path}'
        try:
            response = self._http.request(
                'GET', url, params=params or None,
                headers={'Authorization': f'Bearer {bearer}', 'Accept': 'application/json'},
                timeout=self._config.timeout, allow_redirects=False, stream=True,
            )
        except requests.Timeout:
            raise MetaGraphError(UNAVAILABLE, transient=True, detail='timeout') from None
        except requests.RequestException:
            # La excepción de requests puede incluir la URL con input_token: se descarta.
            raise MetaGraphError(UNAVAILABLE, transient=True, detail='network') from None
        try:
            status = response.status_code
            if 300 <= status < 400:
                raise MetaGraphError(INVALID_RESPONSE, http_status=status, detail='redirect')
            try:
                body = _read_body(response)
            except requests.RequestException:
                raise MetaGraphError(UNAVAILABLE, transient=True, http_status=status, detail='network') from None
            try:
                data = json.loads(body.decode('utf-8')) if body else None
            except (UnicodeDecodeError, ValueError):
                data = None
            if status != 200:
                raise _classify_error(status, data)
            if not isinstance(data, dict):
                raise MetaGraphError(INVALID_RESPONSE, http_status=status)
            if 'error' in data:
                raise _classify_error(status, data)
            return data
        finally:
            close = getattr(response, 'close', None)
            if callable(close):
                close()

    def _paginate(self, path: str, *, bearer: str, params: dict) -> list:
        rows, after = [], None
        for _ in range(MAX_PAGES):
            page_params = {**params, 'limit': PAGE_LIMIT, **({'after': after} if after else {})}
            data = self._get(path, bearer=bearer, params=page_params)
            items = data.get('data')
            if not isinstance(items, list):
                raise MetaGraphError(INVALID_RESPONSE)
            rows.extend(items)
            paging = data.get('paging') if isinstance(data.get('paging'), dict) else {}
            cursors = paging.get('cursors') if isinstance(paging.get('cursors'), dict) else {}
            after = cursors.get('after')
            # Hay otra página solo si Meta informa `next`; el cursor se valida antes de usarlo.
            if not paging.get('next') or not after:
                return rows
            if not isinstance(after, str) or not _CURSOR_RE.fullmatch(after):
                raise MetaGraphError(INVALID_RESPONSE)
        # Más páginas que el tope: no se decide sobre un listado incompleto.
        raise MetaGraphError(INVALID_RESPONSE, detail='too_many_pages')

    # Operaciones de lectura ────────────────────────────────────────────────

    def debug_token(self, token: str) -> dict:
        """`GET /debug_token?input_token=` con app access token (contrato de Meta)."""
        _validate_token(token)
        data = self._get('debug_token', bearer=self._config.app_access_token, params={'input_token': token})
        inner = data.get('data')
        if not isinstance(inner, dict):
            raise MetaGraphError(INVALID_RESPONSE)
        return inner

    def waba_phone_numbers(self, waba_id: str, token: str) -> list:
        _validate_id(waba_id, _WABA_RE, 'waba_id')
        _validate_token(token)
        return self._paginate(f'{waba_id}/phone_numbers', bearer=token, params={'fields': PHONE_FIELDS})

    def waba_subscribed_apps(self, waba_id: str, token: str) -> list:
        _validate_id(waba_id, _WABA_RE, 'waba_id')
        _validate_token(token)
        return self._paginate(f'{waba_id}/subscribed_apps', bearer=token, params={})


# ── Verificación de recursos ──────────────────────────────────────────────────

@dataclass(frozen=True)
class TokenInspection:
    app_id: str
    token_type: str | None
    scopes: tuple[str, ...]
    expires_at: dt.datetime | None          # None: Meta no informó vencimiento (0 o ausente)
    data_access_expires_at: dt.datetime | None
    # Por permiso requerido: 'explicit' (WABA en target_ids) o 'all_assets'
    # (Meta omite target_ids cuando el permiso cubre todo, según debug_token).
    scope_coverage: dict


@dataclass(frozen=True)
class PhoneNumberInfo:
    phone_number_id: str
    display_phone_number: str | None
    verified_name: str | None
    code_verification_status: str | None
    quality_rating: str | None
    platform_type: str | None


@dataclass(frozen=True)
class SubscriptionInfo:
    app_subscribed: bool
    override_callback_configured: bool | None  # None si nuestra app no está suscripta


@dataclass(frozen=True)
class WhatsAppResourceVerification:
    """Resultado normalizado: solo metadatos no secretos.

    Prueba que el token es válido, de nuestra app, con los permisos y el
    alcance sobre la WABA, y que el número pertenece a ella. NO prueba la
    propiedad legal de los recursos por parte del comercio.
    """
    waba_id: str
    token: TokenInspection
    phone_number: PhoneNumberInfo
    subscription: SubscriptionInfo
    verified_at: dt.datetime


def _timestamp(value) -> dt.datetime | None:
    seconds = _int(value)
    if seconds is None or seconds <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise MetaGraphError(INVALID_RESPONSE) from None


def _str_or_none(value, max_length: int = 256) -> str | None:
    return value[:max_length] if isinstance(value, str) and value else None


def inspect_token(client: MetaGraphClient, token: str, *, waba_id: str, now: dt.datetime) -> TokenInspection:
    data = client.debug_token(token)
    is_valid = data.get('is_valid')
    if not isinstance(is_valid, bool):
        raise MetaGraphError(INVALID_RESPONSE)
    if not is_valid:
        error = data.get('error') if isinstance(data.get('error'), dict) else {}
        subcode = _int(error.get('subcode', error.get('error_subcode')))
        expired_at = _timestamp(data.get('expires_at'))
        if subcode in _TOKEN_EXPIRED_SUBCODES or (expired_at is not None and expired_at <= now):
            raise MetaGraphError(TOKEN_EXPIRED, meta_code=_int(error.get('code')), meta_subcode=subcode)
        raise MetaGraphError(TOKEN_INVALID, meta_code=_int(error.get('code')), meta_subcode=subcode)

    app_id = data.get('app_id')
    app_id = str(app_id) if isinstance(app_id, (str, int)) and not isinstance(app_id, bool) else None
    if app_id is None:
        raise MetaGraphError(INVALID_RESPONSE)
    if app_id != client._config.app_id:
        raise MetaGraphError(TOKEN_APP_MISMATCH)

    expires_at = _timestamp(data.get('expires_at'))
    if expires_at is not None and expires_at <= now:
        raise MetaGraphError(TOKEN_EXPIRED)
    data_access = _timestamp(data.get('data_access_expires_at'))
    if data_access is not None and data_access <= now:
        raise MetaGraphError(DATA_ACCESS_EXPIRED)

    scopes = data.get('scopes')
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        raise MetaGraphError(INVALID_RESPONSE)
    missing = [p for p in REQUIRED_PERMISSIONS if p not in scopes]
    if missing:
        raise MetaGraphError(PERMISSIONS_MISSING, detail=','.join(missing))

    granular = data.get('granular_scopes')
    if granular is None:
        # Sin granular_scopes no hay respaldo contractual de alcance universal: fail-closed.
        raise MetaGraphError(SCOPE_UNVERIFIED)
    if not isinstance(granular, list):
        raise MetaGraphError(INVALID_RESPONSE)
    coverage = {}
    for permission in REQUIRED_PERMISSIONS:
        entries = [g for g in granular if isinstance(g, dict) and g.get('scope') == permission]
        if not entries:
            raise MetaGraphError(SCOPE_UNVERIFIED, detail=permission)
        targets = entries[0].get('target_ids')
        if targets is None:
            # debug_token: los targets se omiten cuando el permiso aplica a todos los activos.
            coverage[permission] = 'all_assets'
            continue
        if not isinstance(targets, list) or not all(isinstance(t, (str, int)) for t in targets):
            raise MetaGraphError(INVALID_RESPONSE)
        if waba_id not in {str(t) for t in targets}:
            raise MetaGraphError(SCOPE_NOT_GRANTED, detail=permission)
        coverage[permission] = 'explicit'

    return TokenInspection(
        app_id=app_id, token_type=_str_or_none(data.get('type'), 32), scopes=tuple(sorted(set(scopes))),
        expires_at=expires_at, data_access_expires_at=data_access, scope_coverage=coverage,
    )


def _phone_number(rows: list, phone_number_id: str) -> PhoneNumberInfo:
    for row in rows:
        if not isinstance(row, dict):
            raise MetaGraphError(INVALID_RESPONSE)
        if str(row.get('id')) == phone_number_id:
            return PhoneNumberInfo(
                phone_number_id=phone_number_id,
                display_phone_number=_str_or_none(row.get('display_phone_number'), 32),
                verified_name=_str_or_none(row.get('verified_name')),
                code_verification_status=_str_or_none(row.get('code_verification_status'), 32),
                quality_rating=_str_or_none(row.get('quality_rating'), 32),
                platform_type=_str_or_none(row.get('platform_type'), 32),
            )
    raise MetaGraphError(PHONE_NOT_IN_WABA)


def _subscription(rows: list, app_id: str) -> SubscriptionInfo:
    for row in rows:
        if not isinstance(row, dict):
            raise MetaGraphError(INVALID_RESPONSE)
        api_data = row.get('whatsapp_business_api_data')
        if isinstance(api_data, dict) and str(api_data.get('id')) == app_id:
            return SubscriptionInfo(app_subscribed=True, override_callback_configured=bool(row.get('override_callback_uri')))
    return SubscriptionInfo(app_subscribed=False, override_callback_configured=None)


def verify_whatsapp_resources(
    *, token: str, waba_id: str, phone_number_id: str,
    now: dt.datetime | None = None, session: requests.Session | None = None,
) -> WhatsAppResourceVerification:
    """Verificación completa, solo lecturas, independiente del origen del token.

    Orden: entrada → configuración → token (debug_token) → pertenencia del
    número a la WABA → suscripción observada de nuestra app. Falla en el
    primer problema con un `MetaGraphError` normalizado. Sin escrituras.
    """
    waba_id = _validate_id(waba_id, _WABA_RE, 'waba_id')
    phone_number_id = _validate_id(phone_number_id, _PHONE_RE, 'phone_number_id')
    _validate_token(token)
    now = now or timezone.now()
    client = MetaGraphClient(session=session)
    inspection = inspect_token(client, token, waba_id=waba_id, now=now)
    phone = _phone_number(client.waba_phone_numbers(waba_id, token), phone_number_id)
    subscription = _subscription(client.waba_subscribed_apps(waba_id, token), inspection.app_id)
    logger.info(
        'meta_graph verify ok waba=%s phone_number_id=%s app_subscribed=%s coverage=%s',
        waba_id, phone_number_id, subscription.app_subscribed, ','.join(sorted(set(inspection.scope_coverage.values()))),
    )
    return WhatsAppResourceVerification(
        waba_id=waba_id, token=inspection, phone_number=phone, subscription=subscription, verified_at=now,
    )
