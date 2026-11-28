"""PROD-10B1 — Cliente Graph de servidor y verificación de recursos WhatsApp.

Todo con respuestas HTTP simuladas (sesión falsa): ninguna llamada real a
Meta, ninguna credencial real, ninguna escritura (ni lectura) en la base.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from urllib.parse import urlsplit

import requests
from django.test import TestCase, override_settings

from apps.leads.services import meta_graph as mg
from apps.leads.services.meta_graph import MetaGraphError, verify_whatsapp_resources

APP_ID = '111222333444'
APP_SECRET = 'app-secret-NOT-REAL-0123456789abcdef'
TOKEN = 'EAAG-test-token-NOT-REAL-' + 'x' * 40
WABA = '102030405060'
PHONE = '987654321012'
NOW = dt.datetime(2026, 11, 28, 12, 0, tzinfo=dt.timezone.utc)
FUTURE = int((NOW + dt.timedelta(days=60)).timestamp())
PAST = int((NOW - dt.timedelta(days=1)).timestamp())

META_SETTINGS = dict(
    WHATSAPP_APP_ID=APP_ID, WHATSAPP_APP_SECRET=APP_SECRET, WHATSAPP_GRAPH_VERSION='v23.0',
    WHATSAPP_GRAPH_TIMEOUT_SECONDS=10,
)
SECRETS = (TOKEN, APP_SECRET, f'{APP_ID}|{APP_SECRET}')


class FakeResponse:
    def __init__(self, status=200, body=None, *, raw: bytes | None = None, headers=None, chunk=None):
        self.status_code = status
        self._raw = raw if raw is not None else (json.dumps(body).encode() if body is not None else b'')
        self.headers = headers if headers is not None else {}
        self._chunk = chunk
        self.closed = False

    def iter_content(self, chunk_size=1):
        if self._chunk is not None:
            yield from self._chunk()
            return
        for i in range(0, len(self._raw), chunk_size):
            yield self._raw[i:i + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    """Responde por path; registra cada request. Un valor Exception se lanza."""

    def __init__(self, routes: dict):
        self.routes = {path: (list(v) if isinstance(v, list) else [v]) for path, v in routes.items()}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({'method': method, 'url': url, **kwargs})
        parts = urlsplit(url)
        assert parts.scheme == 'https' and parts.netloc == 'graph.facebook.com', url
        assert not parts.query, 'query params must go through params=, never in the URL'
        path = parts.path.split('/', 2)[2]
        queue = self.routes.get(path)
        if not queue:
            raise AssertionError(f'unexpected request {path}')
        value = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(value, Exception):
            raise value
        return value


def debug(**overrides):
    data = {
        'app_id': APP_ID, 'type': 'SYSTEM_USER', 'application': 'Mi Rubro', 'is_valid': True,
        'expires_at': FUTURE, 'data_access_expires_at': FUTURE,
        'scopes': ['business_management', 'whatsapp_business_management', 'whatsapp_business_messaging'],
        'granular_scopes': [
            {'scope': 'whatsapp_business_management', 'target_ids': [WABA]},
            {'scope': 'whatsapp_business_messaging', 'target_ids': [WABA]},
        ],
    }
    data.update(overrides)
    return FakeResponse(200, {'data': data})


def phones(*ids, after=None):
    body = {'data': [
        {'id': pid, 'display_phone_number': '+54 9 11 5555-0000', 'verified_name': 'Clínica Sol',
         'code_verification_status': 'VERIFIED', 'quality_rating': 'GREEN', 'platform_type': 'CLOUD_API',
         'throughput': {'level': 'STANDARD'}}
        for pid in ids
    ]}
    if after:
        body['paging'] = {
            'cursors': {'before': 'b', 'after': after},
            'next': f'https://graph.facebook.com/v23.0/{WABA}/phone_numbers?access_token={TOKEN}&after={after}',
        }
    return FakeResponse(200, body)


def apps(*entries):
    return FakeResponse(200, {'data': list(entries)})


def our_app(override=None):
    entry = {'whatsapp_business_api_data': {'id': APP_ID, 'link': 'https://x', 'name': 'Mi Rubro'}}
    if override:
        entry['override_callback_uri'] = override
    return entry


def meta_error(status, code, subcode=None, transient=None):
    error = {'message': f'boom {TOKEN}', 'type': 'OAuthException', 'code': code, 'fbtrace_id': 'abc'}
    if subcode is not None:
        error['error_subcode'] = subcode
    if transient is not None:
        error['is_transient'] = transient
    return FakeResponse(status, {'error': error})


def routes(debug_response=None, phone_response=None, apps_response=None):
    return {
        'debug_token': debug_response or debug(),
        f'{WABA}/phone_numbers': phone_response or phones(PHONE),
        f'{WABA}/subscribed_apps': apps_response or apps(our_app()),
    }


@override_settings(**META_SETTINGS)
class _Base(TestCase):

    def verify(self, session, **kwargs):
        params = dict(token=TOKEN, waba_id=WABA, phone_number_id=PHONE, now=NOW, session=session)
        params.update(kwargs)
        with self.assertNumQueries(0):
            return verify_whatsapp_resources(**params)

    def fails(self, session, code, **kwargs) -> MetaGraphError:
        with self.assertRaises(MetaGraphError) as ctx:
            self.verify(session, **kwargs)
        self.assertEqual(ctx.exception.code, code)
        self.assert_no_secrets(str(ctx.exception), ctx.exception.detail, repr(ctx.exception.args))
        return ctx.exception

    def assert_no_secrets(self, *texts):
        for text in texts:
            for secret in SECRETS:
                self.assertNotIn(secret, str(text))


class VerificationTests(_Base):

    def test_valid_token_and_resources_return_normalized_metadata_only(self):
        session = FakeSession(routes())
        result = self.verify(session)
        self.assertEqual(result.waba_id, WABA)
        self.assertEqual(result.token.app_id, APP_ID)
        self.assertEqual(result.token.token_type, 'SYSTEM_USER')
        self.assertEqual(result.token.expires_at, dt.datetime.fromtimestamp(FUTURE, tz=dt.timezone.utc))
        self.assertEqual(result.token.scope_coverage, {
            'whatsapp_business_management': 'explicit', 'whatsapp_business_messaging': 'explicit',
        })
        self.assertEqual(
            (result.phone_number.phone_number_id, result.phone_number.verified_name, result.phone_number.platform_type,
             result.phone_number.code_verification_status, result.phone_number.quality_rating),
            (PHONE, 'Clínica Sol', 'CLOUD_API', 'VERIFIED', 'GREEN'),
        )
        self.assertEqual((result.subscription.app_subscribed, result.subscription.override_callback_configured), (True, False))
        self.assertEqual(result.verified_at, NOW)
        self.assert_no_secrets(repr(result))

        # Transporte: host fijo, versión configurada, sin redirects, timeout, streaming, sin query en URL.
        self.assertEqual([c['url'] for c in session.calls], [
            'https://graph.facebook.com/v23.0/debug_token',
            f'https://graph.facebook.com/v23.0/{WABA}/phone_numbers',
            f'https://graph.facebook.com/v23.0/{WABA}/subscribed_apps',
        ])
        for call in session.calls:
            self.assertEqual((call['method'], call['allow_redirects'], call['timeout'], call['stream']), ('GET', False, 10.0, True))
        # debug_token: app access token solo en el header; input_token en params (contrato de Meta).
        self.assertEqual(session.calls[0]['headers']['Authorization'], f'Bearer {APP_ID}|{APP_SECRET}')
        self.assertEqual(session.calls[0]['params'], {'input_token': TOKEN})
        # WABA: token del recurso solo en el header; nunca el app secret.
        for call in session.calls[1:]:
            self.assertEqual(call['headers']['Authorization'], f'Bearer {TOKEN}')
            self.assertNotIn('input_token', call['params'] or {})
            self.assertNotIn(APP_SECRET, json.dumps(call['params']))
        self.assertEqual(session.calls[1]['params']['fields'], mg.PHONE_FIELDS)

    def test_all_assets_coverage_only_when_meta_omits_target_ids(self):
        session = FakeSession(routes(debug(granular_scopes=[
            {'scope': 'whatsapp_business_management'}, {'scope': 'whatsapp_business_messaging'},
        ])))
        result = self.verify(session)
        self.assertEqual(set(result.token.scope_coverage.values()), {'all_assets'})

    def test_never_reported_expiry_is_none(self):
        result = self.verify(FakeSession(routes(debug(expires_at=0, data_access_expires_at=0))))
        self.assertIsNone(result.token.expires_at)
        self.assertIsNone(result.token.data_access_expires_at)

    def test_invalid_and_expired_tokens(self):
        self.fails(FakeSession(routes(debug(is_valid=False, error={'code': 190, 'message': TOKEN}))), mg.TOKEN_INVALID)
        self.fails(FakeSession(routes(debug(is_valid=False, error={'code': 190, 'subcode': 463}))), mg.TOKEN_EXPIRED)
        self.fails(FakeSession(routes(debug(is_valid=False, expires_at=PAST))), mg.TOKEN_EXPIRED)
        self.fails(FakeSession(routes(debug(expires_at=PAST))), mg.TOKEN_EXPIRED)
        self.fails(FakeSession(routes(debug(data_access_expires_at=PAST))), mg.DATA_ACCESS_EXPIRED)

    def test_token_of_another_app(self):
        session = FakeSession(routes(debug(app_id='999888777')))
        self.fails(session, mg.TOKEN_APP_MISMATCH)
        self.assertEqual(len(session.calls), 1)  # nunca se usa sobre la WABA

    def test_missing_permissions(self):
        error = self.fails(FakeSession(routes(debug(scopes=['business_management', 'whatsapp_business_management']))),
                           mg.PERMISSIONS_MISSING)
        self.assertEqual(error.detail, 'whatsapp_business_messaging')

    def test_insufficient_or_unverifiable_scope(self):
        other = [{'scope': p, 'target_ids': ['555'] if p == 'whatsapp_business_management' else [WABA]}
                 for p in mg.REQUIRED_PERMISSIONS]
        error = self.fails(FakeSession(routes(debug(granular_scopes=other))), mg.SCOPE_NOT_GRANTED)
        self.assertEqual(error.detail, 'whatsapp_business_management')
        # Sin granular_scopes: no se asume alcance universal.
        body = json.loads(debug()._raw)
        body['data'].pop('granular_scopes')
        self.fails(FakeSession(routes(FakeResponse(200, body))), mg.SCOPE_UNVERIFIED)
        # Falta la entrada de uno de los permisos.
        self.fails(FakeSession(routes(debug(granular_scopes=[
            {'scope': 'whatsapp_business_management', 'target_ids': [WABA]},
        ]))), mg.SCOPE_UNVERIFIED)

    def test_phone_number_must_belong_to_the_waba(self):
        self.fails(FakeSession(routes(phone_response=phones('111', '222'))), mg.PHONE_NOT_IN_WABA)
        self.fails(FakeSession(routes(phone_response=meta_error(400, 100, 33))), mg.RESOURCE_NOT_FOUND)
        self.fails(FakeSession(routes(phone_response=meta_error(403, 200))), mg.PERMISSION_DENIED)
        self.fails(FakeSession(routes(phone_response=meta_error(400, 10))), mg.PERMISSION_DENIED)
        self.fails(FakeSession(routes(phone_response=meta_error(400, 100))), mg.REQUEST_REJECTED)

    def test_pagination_uses_cursor_and_never_follows_next_url(self):
        session = FakeSession(routes(phone_response=[phones('111', after='CURSOR1'), phones(PHONE)]))
        result = self.verify(session)
        self.assertEqual(result.phone_number.phone_number_id, PHONE)
        phone_calls = [c for c in session.calls if c['url'].endswith('/phone_numbers')]
        self.assertEqual(len(phone_calls), 2)
        self.assertNotIn('after', phone_calls[0]['params'])
        self.assertEqual(phone_calls[1]['params']['after'], 'CURSOR1')
        self.assertEqual(phone_calls[1]['params']['limit'], mg.PAGE_LIMIT)
        self.assertTrue(all('access_token' not in c['url'] for c in session.calls))

    def test_pagination_bounds_and_invalid_cursor(self):
        endless = FakeSession(routes(phone_response=phones('111', after='CURSOR')))
        error = self.fails(endless, mg.INVALID_RESPONSE)
        self.assertEqual(error.detail, 'too_many_pages')
        self.assertEqual(len([c for c in endless.calls if c['url'].endswith('/phone_numbers')]), mg.MAX_PAGES)
        self.fails(FakeSession(routes(phone_response=phones('111', after='bad cursor&access_token=x'))), mg.INVALID_RESPONSE)

    def test_subscription_observed_state(self):
        result = self.verify(FakeSession(routes(apps_response=apps(our_app('https://override.example/hook')))))
        self.assertEqual((result.subscription.app_subscribed, result.subscription.override_callback_configured), (True, True))
        result = self.verify(FakeSession(routes(apps_response=apps({'whatsapp_business_api_data': {'id': '42'}}))))
        self.assertEqual((result.subscription.app_subscribed, result.subscription.override_callback_configured), (False, None))
        result = self.verify(FakeSession(routes(apps_response=apps())))
        self.assertFalse(result.subscription.app_subscribed)


class TransportTests(_Base):

    def test_timeout_and_network_errors_are_transient_and_never_chain_the_url(self):
        for exc, detail in (
            (requests.Timeout(f'timeout https://graph.facebook.com/v23.0/debug_token?input_token={TOKEN}'), 'timeout'),
            (requests.ConnectionError(f'failed https://graph.facebook.com/v23.0/debug_token?input_token={TOKEN}'), 'network'),
        ):
            with self.subTest(detail):
                error = self.fails(FakeSession(routes(exc)), mg.UNAVAILABLE)
                self.assertTrue(error.transient)
                self.assertEqual(error.detail, detail)
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)

    def test_rate_limits_and_meta_errors(self):
        cases = [
            (meta_error(429, 613), mg.RATE_LIMITED, True),
            (meta_error(400, 4), mg.RATE_LIMITED, True),
            (meta_error(400, 80007), mg.RATE_LIMITED, True),
            (FakeResponse(429, raw=b'slow down'), mg.RATE_LIMITED, True),
            (meta_error(500, 1), mg.UNAVAILABLE, True),
            (FakeResponse(503, raw=b'<html>'), mg.UNAVAILABLE, True),
            (meta_error(400, 2, transient=True), mg.UNAVAILABLE, True),
            (meta_error(400, 12345, transient=True), mg.UNAVAILABLE, True),
            (meta_error(401, 190), mg.TOKEN_INVALID, False),
            (meta_error(401, 190, 463), mg.TOKEN_EXPIRED, False),
            (meta_error(400, 99999), mg.META_ERROR, False),
        ]
        for response, code, transient in cases:
            with self.subTest(code=code, status=response.status_code):
                error = self.fails(FakeSession(routes(response)), code)
                self.assertEqual(error.transient, transient)
                self.assertEqual(error.http_status, response.status_code)

    def test_200_with_error_body_is_classified(self):
        self.fails(FakeSession(routes(meta_error(200, 190))), mg.TOKEN_INVALID)

    def test_invalid_responses(self):
        cases = [
            FakeResponse(302, raw=b'', headers={'Location': 'https://evil.example'}),
            FakeResponse(200, raw=b'not json'),
            FakeResponse(200, raw=b'[1,2]'),
            FakeResponse(200, {'data': 'nope'}),
            FakeResponse(200, {'data': {'is_valid': 'yes'}}),
            FakeResponse(200, {'data': {'is_valid': True, 'app_id': APP_ID, 'scopes': 'all'}}),
            FakeResponse(200, raw=b'{}', headers={'Content-Length': str(mg.MAX_RESPONSE_BYTES + 1)}),
            FakeResponse(200, raw=b'{}', headers={'Content-Length': 'abc'}),
            FakeResponse(200, chunk=lambda: iter([b'x' * (mg.MAX_RESPONSE_BYTES // 2 + 1)] * 2)),
        ]
        for response in cases:
            with self.subTest(status=response.status_code, headers=response.headers):
                self.fails(FakeSession(routes(response)), mg.INVALID_RESPONSE)
        self.fails(FakeSession(routes(phone_response=FakeResponse(200, {'data': {'id': PHONE}}))), mg.INVALID_RESPONSE)
        self.fails(FakeSession(routes(phone_response=FakeResponse(200, {'data': ['x']}))), mg.INVALID_RESPONSE)
        self.fails(FakeSession(routes(apps_response=FakeResponse(200, {'data': [1]}))), mg.INVALID_RESPONSE)

    def test_responses_are_closed(self):
        response = meta_error(500, 1)
        self.fails(FakeSession(routes(response)), mg.UNAVAILABLE)
        self.assertTrue(response.closed)


class ConfigurationAndInputTests(TestCase):

    def run_verify(self, session, **kwargs):
        params = dict(token=TOKEN, waba_id=WABA, phone_number_id=PHONE, now=NOW, session=session)
        params.update(kwargs)
        with self.assertRaises(MetaGraphError) as ctx, self.assertNumQueries(0):
            verify_whatsapp_resources(**params)
        return ctx.exception

    def test_missing_or_invalid_configuration_fails_closed_without_calls(self):
        for overrides in (
            {'WHATSAPP_APP_ID': ''},
            {'WHATSAPP_APP_ID': 'abc'},
            {'WHATSAPP_APP_SECRET': ''},
            {'WHATSAPP_APP_SECRET': 'short'},
            {'WHATSAPP_GRAPH_VERSION': ''},
            {'WHATSAPP_GRAPH_VERSION': 'latest'},
            {'WHATSAPP_GRAPH_VERSION': 'v23.0/../evil'},
            {'WHATSAPP_GRAPH_TIMEOUT_SECONDS': 0},
            {'WHATSAPP_GRAPH_TIMEOUT_SECONDS': 120},
        ):
            with self.subTest(overrides=overrides), override_settings(**{**META_SETTINGS, **overrides}):
                session = FakeSession(routes())
                self.assertEqual(self.run_verify(session).code, mg.NOT_CONFIGURED)
                self.assertEqual(session.calls, [])

    def test_default_graph_version_is_the_bots(self):
        from django.conf import settings

        self.assertEqual(settings.WHATSAPP_GRAPH_VERSION, 'v23.0')

    @override_settings(**META_SETTINGS)
    def test_invalid_input_never_reaches_meta(self):
        for kwargs, field in (
            ({'waba_id': '12a'}, 'waba_id'), ({'waba_id': ''}, 'waba_id'), ({'waba_id': '1' * 33}, 'waba_id'),
            ({'phone_number_id': '1/../2'}, 'phone_number_id'), ({'phone_number_id': 123}, 'phone_number_id'),
            ({'token': 'short'}, 'token'), ({'token': 'has space ' + 'x' * 30}, 'token'), ({'token': None}, 'token'),
        ):
            with self.subTest(field=field, kwargs=kwargs):
                session = FakeSession(routes())
                error = self.run_verify(session, **kwargs)
                self.assertEqual((error.code, error.detail), (mg.INVALID_INPUT, field))
                self.assertEqual(session.calls, [])


@override_settings(**META_SETTINGS)
class SecretExposureTests(_Base):

    def test_logs_never_contain_secrets_on_success_or_failure(self):
        with self.assertLogs(level='DEBUG') as captured:
            self.verify(FakeSession(routes()))
            for response in (meta_error(500, 1), debug(app_id='1'), meta_error(401, 190)):
                with self.assertRaises(MetaGraphError):
                    self.verify(FakeSession(routes(response)))
            logging.getLogger('apps.leads.meta_graph').debug('marker')
        self.assert_no_secrets('\n'.join(captured.output))
        self.assertTrue(any('meta_graph verify ok' in line for line in captured.output))

    def test_urllib3_request_line_is_redacted(self):
        log = logging.getLogger('urllib3.connectionpool')
        with self.assertLogs('urllib3.connectionpool', level='DEBUG') as captured:
            log.debug('%s://%s:%s "%s %s %s" %s %s', 'https', 'graph.facebook.com', 443, 'GET',
                      f'/v23.0/debug_token?input_token={TOKEN}&access_token={APP_ID}|{APP_SECRET}', 'HTTP/1.1', 200, 512)
            log.debug('Starting new HTTPS connection (%d): %s:%s', 1, 'graph.facebook.com', 443)
        self.assert_no_secrets('\n'.join(captured.output))
        self.assertIn('input_token=[REDACTED]', captured.output[0])
        self.assertIn('access_token=[REDACTED]', captured.output[0])
        self.assertIn('Starting new HTTPS connection (1)', captured.output[1])

    def test_meta_error_messages_are_never_propagated(self):
        error = self.fails(FakeSession(routes(meta_error(400, 99999))), mg.META_ERROR)
        self.assertEqual(str(error), mg.META_ERROR)
        self.assertEqual(error.detail, '')
