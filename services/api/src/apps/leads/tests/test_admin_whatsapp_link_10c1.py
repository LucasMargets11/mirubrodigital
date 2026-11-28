"""PROD-10C1 — POST administrativo de vinculación WhatsApp y evidencia en el GET.

Graph simulado: `requests.request` del cliente de 10B1 se reemplaza por una
sesión falsa, así ninguna request puede salir a Meta. PostgreSQL descartable.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import AccessAuditLog
from apps.billing.tests.test_reception_service_02b import _business, _reception, _superadmin
from apps.leads.models import AgentChannel, ReceptionistConfig, WhatsAppAuthorization
from apps.leads.services import meta_graph as mg
from apps.leads.services import receptionist_config as rc
from apps.leads.services import whatsapp_authorizations as wa
from apps.leads.services import whatsapp_link as wl

from .factories import enable_reception_attention, make_channel, make_instance
from .test_meta_graph_10b1 import FakeSession, apps, debug, meta_error, our_app, phones
from .test_receptionist_config_api_03b import member_client, staff_client
from .test_whatsapp_link_10b2 import INSTANCE, LINK_SETTINGS, PHONE, SECRETS, TOKEN, TOKEN_2, WABA, routes, ts

REASON = 'Alta asistida pedida por el comercio'


def url(business) -> str:
    return f'/api/v1/platform-admin/clients/{getattr(business, "pk", business)}/whatsapp-connections/'


def config_url(business) -> str:
    return f'/api/v1/platform-admin/clients/{business.pk}/receptionist-config/'


def phone_with(platform_type=None, *, drop=False):
    response = phones(PHONE)
    body = json.loads(response._raw)
    if drop:
        body['data'][0].pop('platform_type')
    else:
        body['data'][0]['platform_type'] = platform_type
    response._raw = json.dumps(body).encode()
    return response


class _Mixin:
    def make_world(self):
        cache.clear()  # throttle por usuario
        self.business = _business()
        _reception(self.business)
        self.instance = make_instance(INSTANCE)
        self.admin = staff_client()

    def body(self, **overrides):
        data = {'waba_id': WABA, 'phone_number_id': PHONE, 'access_token': TOKEN, 'reason': REASON}
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not None}

    @contextmanager
    def graph(self, session=None):
        session = session or FakeSession(routes())
        with mock.patch.object(mg.requests, 'request', new=session.request):
            yield session

    def post(self, data=None, *, business=None, client=None, session=None):
        with self.graph(session):
            return (client or self.admin).post(url(business or self.business), data or self.body(), format='json')


@override_settings(**LINK_SETTINGS)
class _Base(_Mixin, TestCase):
    def setUp(self):
        self.make_world()

    def ok(self, response, status):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNoSecrets(response.content.decode())
        return response.json()

    def error(self, response, status, code, field=None):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        body = response.json()
        self.assertEqual(body['code'], code)
        self.assertEqual(set(body), {'code', 'detail', 'field', 'retryable'})
        if field is not None:
            self.assertEqual(body['field'], field)
        self.assertNoSecrets(response.content.decode())
        return body

    def assertNoSecrets(self, *texts):
        for text in texts:
            for secret in SECRETS:
                self.assertNotIn(secret, str(text))

    def assertNothingWritten(self):
        self.assertFalse(AgentChannel.objects.filter(phone_number_id=PHONE).exists())
        self.assertEqual(WhatsAppAuthorization.objects.count(), 0)
        self.assertFalse(AccessAuditLog.objects.filter(action__startswith='WHATSAPP_').exists())

    def get_rows(self, client=None):
        response = (client or self.admin).get(url(self.business))
        self.assertEqual(response.status_code, 200, response.content)
        return {row['phone_number_id']: row for row in response.json()['channels']}


# ── Contrato del POST ────────────────────────────────────────────────────────

class LinkEndpointTests(_Base):
    def test_new_link_returns_201_with_non_secret_channel(self):
        body = self.ok(self.post(), 201)
        self.assertEqual((body['outcome'], body['created_channel'], body['created_authorization']),
                         ('linked', True, True))
        self.assertEqual((body['business_id'], body['contract_version']), (self.business.pk, 1))
        self.assertIs(body['automatic_attention_enabled'], False)
        channel = body['channel']
        self.assertEqual((channel['phone_number_id'], channel['waba_id'], channel['local_status']),
                         (PHONE, WABA, 'credential_ready'))
        self.assertEqual(channel['agent_instance']['external_id'], INSTANCE)
        self.assertEqual(channel['authorization']['kind'], 'business')
        verification = channel['meta_verification']
        self.assertEqual(verification['status'], 'valid')
        self.assertEqual(verification['source'], 'assisted')
        self.assertIs(verification['app_subscribed_observed'], True)
        self.assertIs(verification['legal_ownership_verified'], False)
        self.assertNotIn('access_token', str(body))
        self.assertNotIn('encrypted', str(body))
        stored = AgentChannel.objects.get(pk=channel['id'])
        self.assertEqual(stored.business_id, self.business.pk)
        self.assertEqual(WhatsAppAuthorization.objects.get().owner_business_id, self.business.pk)

    def test_equivalent_repeat_returns_200(self):
        first = self.ok(self.post(), 201)
        second = self.ok(self.post(), 200)
        self.assertEqual(second['outcome'], 'already_linked')
        self.assertEqual(second['channel']['id'], first['channel']['id'])
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)

    def test_source_is_always_assisted(self):
        self.error(self.post(self.body(source='embedded_signup')), 400, 'unexpected_fields', 'source')
        self.ok(self.post(), 201)
        audit = AccessAuditLog.objects.get(action='WHATSAPP_CHANNEL_LINKED')
        self.assertEqual(audit.details['source'], 'assisted')

    def test_extra_fields_are_rejected_without_writes(self):
        for extra in ({'business_id': 999}, {'agent_instance_id': 'x'}, {'platform': True}, {'token': TOKEN}):
            self.error(self.post(self.body(**extra)), 400, 'unexpected_fields')
        self.assertNothingWritten()

    def test_missing_or_non_string_fields(self):
        for field in ('waba_id', 'phone_number_id', 'access_token', 'reason'):
            data = self.body()
            data.pop(field)
            self.error(self.post(data), 400, 'invalid_field', field)
        self.error(self.post(self.body(waba_id=102030)), 400, 'invalid_field', 'waba_id')
        self.error(self.post(self.body(access_token='x' * 5000)), 400, 'invalid_field', 'access_token')
        self.assertNothingWritten()

    def test_non_object_body(self):
        with self.graph():
            response = self.admin.post(url(self.business), [TOKEN], format='json')
        self.error(response, 400, 'invalid_request')

    def test_service_validation_errors_never_echo_the_token(self):
        self.error(self.post(self.body(access_token='bad token with spaces ' + TOKEN)), 400, 'invalid_token',
                   'access_token')
        self.error(self.post(self.body(reason='   ')), 400, 'invalid_reason', 'reason')

    def test_no_secrets_in_logs(self):
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger('apps.leads').debug('marker')
            self.ok(self.post(), 201)
            self.error(self.post(self.body(access_token=TOKEN_2)), 409, 'channel_credential_conflict')
            self.post(session=FakeSession(routes(debug_response=debug(is_valid=False))))
        self.assertNoSecrets(*logs.output)

    def test_throttled_per_user(self):
        from apps.leads.whatsapp_connection_views import WhatsAppLinkThrottle
        with mock.patch.object(WhatsAppLinkThrottle, 'THROTTLE_RATES', {'admin_whatsapp_link': '2/minute'}):
            self.post()
            self.post()
            self.assertEqual(self.post().status_code, 429)
            self.assertEqual(self.admin.get(url(self.business)).status_code, 200)  # el GET no consume


# ── Permisos y aislamiento ───────────────────────────────────────────────────

class PermissionTests(_Base):
    def test_operations_can_read_but_not_link(self):
        operations = staff_client('operations')
        self.assertEqual(operations.get(url(self.business)).status_code, 200)
        with self.graph() as session:
            response = operations.post(url(self.business), self.body(), format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(session.calls, [])
        self.assertNothingWritten()

    def test_business_members_cannot_read_or_link(self):
        client, _ = member_client(self.business, 'owner')
        self.assertEqual(client.get(url(self.business)).status_code, 403)
        self.assertEqual(self.post(client=client).status_code, 403)
        self.assertNothingWritten()

    def test_anonymous(self):
        from rest_framework.test import APIClient
        self.assertIn(self.post(client=APIClient()).status_code, (401, 403))

    def test_client_not_found_or_ineligible(self):
        self.error(self.post(business=999999), 404, 'client_not_found')
        other = _business()  # sin Recepcionista
        self.error(self.post(business=other), 404, 'client_not_found')
        self.assertNothingWritten()

    def test_business_comes_only_from_the_route(self):
        other = _business()
        _reception(other)
        body = self.ok(self.post(business=other), 201)
        self.assertEqual(body['business_id'], other.pk)
        self.assertEqual(AgentChannel.objects.get(phone_number_id=PHONE).business_id, other.pk)
        self.assertEqual(self.get_rows(), {})  # el otro cliente no ve nada

    def test_number_of_another_client_is_not_revealed(self):
        other = _business()
        _reception(other)
        self.ok(self.post(business=other), 201)
        body = self.error(self.post(), 409, 'phone_number_unavailable')
        self.assertNotIn(str(other.pk), str(body))
        self.assertNotIn(other.name, str(body))


# ── Cloud API ────────────────────────────────────────────────────────────────

class PlatformTypeTests(_Base):
    def test_cloud_api_is_accepted(self):
        self.ok(self.post(session=FakeSession(routes(phone_response=phone_with('CLOUD_API')))), 201)

    def test_incompatible_unknown_or_missing_platform_is_rejected(self):
        for response in (phone_with('ON_PREMISE'), phone_with('NOT_APPLICABLE'), phone_with('cloud_api'),
                         phone_with(''), phone_with(None), phone_with(drop=True)):
            self.error(self.post(session=FakeSession(routes(phone_response=response))), 422,
                       'phone_platform_not_supported', 'phone_number_id')
        self.assertNothingWritten()

    def test_rule_applies_to_embedded_signup_source(self):
        with self.assertRaises(wa.WhatsAppAuthorizationError) as ctx:
            wl.link_whatsapp_channel(
                business=self.business, waba_id=WABA, phone_number_id=PHONE, token=TOKEN, actor=_superadmin(),
                reason=REASON, source=wl.SOURCE_EMBEDDED_SIGNUP,
                session=FakeSession(routes(phone_response=phone_with('ON_PREMISE'))),
            )
        self.assertEqual(ctx.exception.code, 'phone_platform_not_supported')
        self.assertNothingWritten()


# ── Atención automática ──────────────────────────────────────────────────────

class AttentionTests(_Base):
    def test_enabled_attention_blocks_new_link_before_meta(self):
        config = enable_reception_attention(self.business)
        with self.graph() as session:
            response = self.admin.post(url(self.business), self.body(), format='json')
        self.error(response, 409, 'automatic_attention_must_be_paused')
        self.assertEqual(session.calls, [])
        self.assertNothingWritten()
        config.refresh_from_db()
        self.assertTrue(config.automatic_attention_enabled)  # nunca se pausa sola

    def test_enabled_attention_blocks_first_credential_of_existing_channel(self):
        enable_reception_attention(self.business)
        channel = make_channel(self.instance, self.business, phone_number_id=PHONE)
        self.error(self.post(), 409, 'automatic_attention_must_be_paused')
        channel.refresh_from_db()
        self.assertIsNone(channel.whatsapp_authorization_id)

    def test_paused_attention_allows_link(self):
        config = enable_reception_attention(self.business)
        ReceptionistConfig.objects.filter(pk=config.pk).update(automatic_attention_enabled=False)
        self.ok(self.post(), 201)

    def test_equivalent_reverification_needs_no_pause(self):
        self.ok(self.post(), 201)
        config = enable_reception_attention(self.business)
        before = ReceptionistConfig.objects.filter(pk=config.pk).values().get()
        body = self.ok(self.post(), 200)
        self.assertEqual(body['outcome'], 'already_linked')
        self.assertIs(body['automatic_attention_enabled'], True)
        self.assertEqual(ReceptionistConfig.objects.filter(pk=config.pk).values().get(), before)

    def test_different_token_with_attention_enabled_is_still_a_conflict(self):
        self.ok(self.post(), 201)
        enable_reception_attention(self.business)
        self.error(self.post(self.body(access_token=TOKEN_2)), 409, 'channel_credential_conflict')

    def test_attention_enabled_while_meta_was_consulted(self):
        """Revalidación bajo lock: la atención se habilitó durante la verificación."""
        config = enable_reception_attention(self.business)
        ReceptionistConfig.objects.filter(pk=config.pk).update(automatic_attention_enabled=False)
        real = wl.verify_whatsapp_resources

        def verify_then_enable(**kwargs):
            result = real(**kwargs)
            ReceptionistConfig.objects.filter(pk=config.pk).update(automatic_attention_enabled=True)
            return result

        with mock.patch.object(wl, 'verify_whatsapp_resources', side_effect=verify_then_enable):
            self.error(self.post(), 409, 'automatic_attention_must_be_paused')
        self.assertNothingWritten()


# ── Conflictos y Meta ────────────────────────────────────────────────────────

class ConflictAndMetaErrorTests(_Base):
    def test_conflicts_map_to_409(self):
        self.ok(self.post(), 201)
        self.error(self.post(self.body(waba_id='777888999')), 409, 'channel_waba_mismatch')
        self.error(self.post(self.body(access_token=TOKEN_2)), 409, 'channel_credential_conflict')
        other_phone = '555000111222'
        make_channel(make_instance('other-agent-10c1'), self.business, phone_number_id=other_phone)
        self.error(self.post(self.body(phone_number_id=other_phone)), 409, 'channel_agent_instance_mismatch')
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)

    @override_settings(WHATSAPP_LINK_AGENT_INSTANCE_ID='')
    def test_instance_not_configured_is_503(self):
        self.error(self.post(), 503, 'agent_instance_not_configured')

    @override_settings(WHATSAPP_APP_SECRET='')
    def test_meta_not_configured_is_503(self):
        self.error(self.post(), 503, 'meta_not_configured')
        self.assertNothingWritten()

    def test_definitive_meta_errors_are_422_not_retryable(self):
        cases = [
            ('token_invalid', 'access_token', routes(debug_response=debug(is_valid=False))),
            ('token_expired', 'access_token', routes(debug_response=debug(expires_at=ts(-1)))),
            ('token_app_mismatch', 'access_token', routes(debug_response=debug(app_id='999'))),
            ('permissions_missing', 'access_token',
             routes(debug_response=debug(expires_at=ts(30), scopes=['whatsapp_business_management']))),
            ('phone_number_not_in_waba', 'phone_number_id', routes(phone_response=phones('111'))),
        ]
        for code, field, session_routes in cases:
            body = self.error(self.post(session=FakeSession(session_routes)), 422, code, field)
            self.assertIs(body['retryable'], False)
        self.assertNothingWritten()

    def test_transient_meta_errors_are_retryable(self):
        body = self.error(self.post(session=FakeSession(routes(phone_response=meta_error(503, 2)))),
                          503, 'meta_unavailable')
        self.assertIs(body['retryable'], True)
        body = self.error(self.post(session=FakeSession(routes(debug_response=meta_error(429, 4, transient=True)))),
                          503, 'meta_rate_limited')
        self.assertIs(body['retryable'], True)
        self.assertNothingWritten()

    def test_meta_error_text_never_reaches_the_response(self):
        body = self.error(self.post(session=FakeSession(routes(phone_response=meta_error(400, 100)))), 422,
                          'meta_request_rejected')
        self.assertNotIn('boom', body['detail'])

    def test_audit_failure_rolls_back_and_returns_500_without_secrets(self):
        self.admin.raise_request_exception = False
        with mock.patch.object(wl, 'record_platform_action', side_effect=RuntimeError('audit down')):
            response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertNoSecrets(response.content.decode())
        self.assertNothingWritten()


# ── GET: evidencia ───────────────────────────────────────────────────────────

class ReadContractTests(_Base):
    def test_valid_evidence(self):
        self.ok(self.post(), 201)
        row = self.get_rows()[PHONE]
        verification = row['meta_verification']
        self.assertEqual(verification['status'], 'valid')
        self.assertEqual((verification['waba_id'], verification['phone_number_id']), (WABA, PHONE))
        self.assertIs(verification['resources_verified'], True)
        self.assertIs(verification['app_subscribed_observed'], True)
        self.assertIs(verification['override_callback_observed'], False)
        self.assertEqual(verification['phone']['platform_type'], 'CLOUD_API')
        self.assertIsNotNone(verification['verified_at'])
        self.assertNotIn('token', verification)
        self.assertNotIn('authorization_updated_at', verification)
        # Sigue sin afirmar conectividad: la verificación es histórica.
        response = self.admin.get(url(self.business)).json()
        self.assertEqual(response['external_verification']['meta_connectivity'], 'unknown')

    def test_override_and_unsubscribed_are_reported_as_observed(self):
        self.ok(self.post(session=FakeSession(routes(apps_response=apps(our_app('https://other.example/hook'))))), 201)
        verification = self.get_rows()[PHONE]['meta_verification']
        self.assertIs(verification['override_callback_observed'], True)
        self.assertNotIn('other.example', str(verification))

    def test_unsubscribed_app(self):
        self.ok(self.post(session=FakeSession(routes(apps_response=apps()))), 201)
        verification = self.get_rows()[PHONE]['meta_verification']
        self.assertIs(verification['app_subscribed_observed'], False)

    def test_invalidated_evidence(self):
        body = self.ok(self.post(), 201)
        authorization_id = body['channel']['authorization']['id']
        wa.rotate_whatsapp_authorization(authorization_id=authorization_id, token=TOKEN_2, actor=_superadmin())
        row = self.get_rows()[PHONE]
        self.assertEqual(row['meta_verification'], {'status': 'invalidated'})
        self.assertEqual(row['local_status'], 'credential_ready')  # estado local y evidencia son distintos

    def test_legacy_channel_without_evidence(self):
        channel = make_channel(self.instance, self.business, phone_number_id='5491100009')
        authorization = wa.create_whatsapp_authorization(token=TOKEN, actor=_superadmin(), owner_business=self.business)
        wa.associate_channel(channel_id=channel.pk, authorization_id=authorization.pk, waba_id=WABA, actor=_superadmin())
        row = self.get_rows()['5491100009']
        self.assertEqual(row['local_status'], 'credential_ready')
        self.assertEqual(row['meta_verification'], {'status': 'missing'})

    def test_get_stays_read_only(self):
        self.ok(self.post(), 201)
        with CaptureQueriesContext(connection) as queries:
            self.admin.get(url(self.business))
        self.assertFalse([q for q in queries if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))])


# ── Concurrencia: vinculación vs. habilitación de la atención ────────────────

@override_settings(**LINK_SETTINGS)
class AttentionConcurrencyTests(_Mixin, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        self.make_world()
        self.actor = _superadmin()
        config = enable_reception_attention(self.business)
        ReceptionistConfig.objects.filter(pk=config.pk).update(automatic_attention_enabled=False)
        self.config = ReceptionistConfig.objects.get(pk=config.pk)

    def enable(self):
        rc.update_receptionist_config(
            self.business, {'expected_version': self.config.version, 'automatic_attention_enabled': True},
            actor=self.actor, source=rc.SOURCE_PLATFORM_ADMIN,
        )
        return 'enabled'

    def link(self):
        return wl.link_whatsapp_channel(
            business=self.business, waba_id=WABA, phone_number_id=PHONE, token=TOKEN, actor=self.actor,
            reason=REASON, source=wl.SOURCE_ASSISTED, session=FakeSession(routes()),
        ).outcome

    def race(self, first, second, *, slow_target, slow_attr):
        results, started = {}, threading.Event()
        real = getattr(slow_target, slow_attr)

        def slow(*args, **kwargs):
            started.set()
            time.sleep(0.4)  # retiene los locks de su transacción
            return real(*args, **kwargs)

        def worker(name, call):
            try:
                results[name] = call()
            except wa.WhatsAppAuthorizationError as error:
                results[name] = error.code
            except Exception as error:  # visible en el assert
                results[name] = repr(error)
            finally:
                connection.close()

        with mock.patch.object(slow_target, slow_attr, side_effect=slow):
            a = threading.Thread(target=worker, args=('first', first))
            b = threading.Thread(target=worker, args=('second', second))
            a.start()
            started.wait(5)
            b.start()
            a.join(15)
            b.join(15)
        return results

    def test_link_holding_the_lock_makes_enable_wait(self):
        results = self.race(self.link, self.enable, slow_target=wl, slow_attr='record_platform_action')
        self.assertEqual(results, {'first': 'linked', 'second': 'enabled'})
        self.assertTrue(AgentChannel.objects.filter(phone_number_id=PHONE, is_active=True).exists())
        self.assertTrue(ReceptionistConfig.objects.get(pk=self.config.pk).automatic_attention_enabled)

    def test_enable_holding_the_lock_blocks_the_link(self):
        results = self.race(self.enable, self.link, slow_target=rc, slow_attr='_audit')
        self.assertEqual(results, {'first': 'enabled', 'second': 'automatic_attention_must_be_paused'})
        self.assertFalse(AgentChannel.objects.filter(phone_number_id=PHONE).exists())
        self.assertEqual(WhatsAppAuthorization.objects.count(), 0)
