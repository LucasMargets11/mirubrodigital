"""PROD-04C — GET HMAC de la credencial WhatsApp de un canal para el agente."""
from __future__ import annotations

import datetime as dt
import uuid
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import AccessAuditLog
from apps.business.models import Business
from apps.leads import throttles
from apps.leads.models import AgentChannel, AgentCredential, WhatsAppAuthorization
from apps.leads.services import whatsapp_authorizations as wa

from .agent_client import sign_headers
from .factories import SECRET, make_business, make_channel, make_credential, make_instance
from .test_receiver_api import INVALID_SIGNATURE_BODY, ReceiverTestBase
from .test_whatsapp_authorizations_04b import TOKEN, TOKEN_2, WABA, staff

KEYS = {'ok', 'contract_version', 'business_id', 'phone_number_id', 'waba_id', 'access_token', 'expires_at'}
OTHER_PHONE = '2222222222'


def credential_path(phone_number_id) -> str:
    return f'/api/v1/integrations/agent/channels/{phone_number_id}/whatsapp-credential/'


class _Base(ReceiverTestBase):
    def setUp(self):
        super().setUp()
        self.actor = staff()
        self.authorization = self.authorize(self.channel)

    def authorize(self, channel, *, token=TOKEN, waba=WABA, owner='channel', **kwargs):
        owner_business = channel.business if owner == 'channel' else owner
        authorization = wa.create_whatsapp_authorization(
            token=token, actor=self.actor, owner_business=owner_business, **kwargs,
        )
        self.link(channel, authorization, waba)
        return authorization

    def link(self, channel, authorization, waba=WABA):
        wa.associate_channel(channel_id=channel.pk, authorization_id=authorization.pk, waba_id=waba, actor=self.actor)

    def get(self, phone=None, *, credential=None, secret=SECRET, sign_path=None, **sign_kwargs):
        path = credential_path(phone or self.PHONE_NUMBER_ID)
        headers = sign_headers(
            path=sign_path or path, body=b'', key_id=(credential or self.credential).key_id, secret=secret,
            method='GET', **sign_kwargs,
        )
        return self.client.get(path, **headers)

    def ok(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIn('X-Request-Id', response)
        body = response.json()
        self.assertEqual(set(body), KEYS)
        self.assertEqual((body['ok'], body['contract_version']), (True, 1))
        return body

    def denied(self, response, status_code, code):
        self.assertEqual(response['Cache-Control'], 'no-store')
        body = self.assertError(response, status_code, code)
        for secret in (TOKEN, TOKEN_2, TOKEN[4:24]):
            self.assertNotIn(secret, response.content.decode())
        return body


class ContractTests(_Base):
    def test_resolves_business_from_the_number_alone(self):
        body = self.ok(self.get())
        self.assertEqual(body, {
            'ok': True, 'contract_version': 1, 'business_id': self.business.pk,
            'phone_number_id': self.PHONE_NUMBER_ID, 'waba_id': WABA, 'access_token': TOKEN, 'expires_at': None,
        })

    def test_expires_at_is_delivered(self):
        expires = timezone.now() + dt.timedelta(days=30)
        wa.rotate_whatsapp_authorization(
            authorization_id=self.authorization.pk, token=TOKEN, actor=self.actor, expires_at=expires,
        )
        self.assertEqual(dt.datetime.fromisoformat(self.ok(self.get())['expires_at']), expires)

    def test_one_instance_two_businesses(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        other_channel = make_channel(self.instance, other, phone_number_id=OTHER_PHONE)
        self.authorize(other_channel, token=TOKEN_2, waba='999888777')
        a, b = self.ok(self.get()), self.ok(self.get(OTHER_PHONE))
        self.assertEqual((a['business_id'], a['access_token'], a['waba_id']), (self.business.pk, TOKEN, WABA))
        self.assertEqual((b['business_id'], b['access_token'], b['waba_id']), (other.pk, TOKEN_2, '999888777'))

    def test_shared_business_authorization(self):
        second = make_channel(self.instance, self.business, phone_number_id=OTHER_PHONE)
        self.link(second, self.authorization)
        a, b = self.ok(self.get()), self.ok(self.get(OTHER_PHONE))
        self.assertEqual((a['access_token'], b['access_token']), (TOKEN, TOKEN))
        self.assertEqual((a['phone_number_id'], b['phone_number_id']), (self.PHONE_NUMBER_ID, OTHER_PHONE))
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)

    def test_shared_platform_authorization_for_two_businesses(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        other_channel = make_channel(self.instance, other, phone_number_id=OTHER_PHONE)
        platform = wa.create_whatsapp_authorization(token=TOKEN_2, actor=self.actor, platform=True)
        self.link(self.channel, platform)
        self.link(other_channel, platform)
        a, b = self.ok(self.get()), self.ok(self.get(OTHER_PHONE))
        self.assertEqual((a['business_id'], b['business_id']), (self.business.pk, other.pk))
        self.assertEqual((a['access_token'], b['access_token']), (TOKEN_2, TOKEN_2))


class IsolationTests(_Base):
    def test_channel_of_another_instance(self):
        foreign = make_instance(f'other-agent-{uuid.uuid4().hex[:8]}')
        foreign_business = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        foreign_channel = make_channel(foreign, foreign_business, phone_number_id=OTHER_PHONE)
        self.authorize(foreign_channel, token=TOKEN_2)
        self.denied(self.get(OTHER_PHONE), 403, 'channel_disabled')
        # Y la otra instancia tampoco ve el canal de esta.
        foreign_key = make_credential(foreign, key_id=f'key-{uuid.uuid4().hex[:8]}')
        self.denied(self.get(credential=foreign_key), 403, 'channel_disabled')
        self.assertEqual(self.ok(self.get(OTHER_PHONE, credential=foreign_key))['access_token'], TOKEN_2)

    def test_unknown_and_inactive_channel(self):
        self.denied(self.get('9999999999'), 403, 'channel_disabled')
        AgentChannel.objects.filter(pk=self.channel.pk).update(is_active=False, deactivated_at=timezone.now())
        self.denied(self.get(), 403, 'channel_disabled')

    def test_suspended_business(self):
        Business.objects.filter(pk=self.business.pk).update(status='suspended')
        self.denied(self.get(), 403, 'business_inactive')

    def test_authorization_of_another_business_is_rechecked(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        foreign_authorization = wa.create_whatsapp_authorization(token=TOKEN_2, actor=self.actor, owner_business=other)
        # Solo posible salteando save() (update): la entrega igual falla cerrada.
        AgentChannel.objects.filter(pk=self.channel.pk).update(whatsapp_authorization=foreign_authorization)
        self.denied(self.get(), 403, 'whatsapp_authorization_owner_mismatch')

    def test_legacy_channel_without_authorization_or_waba(self):
        legacy = make_channel(self.instance, self.business, phone_number_id=OTHER_PHONE)
        self.denied(self.get(OTHER_PHONE), 403, 'whatsapp_authorization_missing')
        AgentChannel.objects.filter(pk=legacy.pk).update(whatsapp_authorization=self.authorization)
        self.denied(self.get(OTHER_PHONE), 403, 'whatsapp_waba_missing')

    def test_concurrent_reassignment_between_reads(self):
        foreign = make_instance(f'other-agent-{uuid.uuid4().hex[:8]}')
        original = wa.resolve_channel_whatsapp_credential

        def moved(channel_id):
            AgentChannel.objects.filter(pk=channel_id).update(agent_instance=foreign)
            return original(channel_id)

        with mock.patch.object(wa, 'resolve_channel_whatsapp_credential', side_effect=moved):
            self.denied(self.get(), 403, 'channel_disabled')

    def test_malformed_number_is_router_404(self):
        path = credential_path('12ab')
        headers = sign_headers(path=path, body=b'', key_id=self.credential.key_id, method='GET')
        self.assertEqual(self.client.get(path, **headers).status_code, 404)


class LifecycleTests(_Base):
    def test_rotation_is_effective_on_the_next_request(self):
        self.assertEqual(self.ok(self.get())['access_token'], TOKEN)
        wa.rotate_whatsapp_authorization(authorization_id=self.authorization.pk, token=TOKEN_2, actor=self.actor)
        self.assertEqual(self.ok(self.get())['access_token'], TOKEN_2)

    def test_revocation_is_effective_on_the_next_request(self):
        self.ok(self.get())
        wa.revoke_whatsapp_authorization(authorization_id=self.authorization.pk, actor=self.actor)
        self.denied(self.get(), 403, 'whatsapp_authorization_revoked')

    def test_expired_and_invalid(self):
        WhatsAppAuthorization.objects.filter(pk=self.authorization.pk).update(
            expires_at=timezone.now() - dt.timedelta(seconds=1),
        )
        self.denied(self.get(), 403, 'whatsapp_authorization_expired')
        WhatsAppAuthorization.objects.filter(pk=self.authorization.pk).update(status='invalid', expires_at=None)
        self.denied(self.get(), 403, 'whatsapp_authorization_invalid')

    def test_undecryptable_token_fails_closed(self):
        # Prefijo Fernet válido (pasa el CHECK) pero contenido corrupto.
        WhatsAppAuthorization.objects.filter(pk=self.authorization.pk).update(
            encrypted_access_token='gAAAAA' + 'x' * 80,
        )
        with self.assertLogs('apps.leads', level='INFO') as logs:
            body = self.denied(self.get(), 503, 'unavailable')
        self.assertTrue(body['error']['retryable'])
        self.assertIn('agent_whatsapp_credential_undecryptable', '\n'.join(logs.output))
        self.assertNotIn('gAAAAA', '\n'.join(logs.output))


class AuthenticationTests(_Base):
    def test_bad_signature_timestamp_and_unknown_key(self):
        for response in (
            self.get(secret='x' * 40),
            self.get(timestamp=1),
            self.get(credential=AgentCredential(agent_instance=self.instance, key_id='never-created')),
        ):
            self.assertEqual(response.json(), INVALID_SIGNATURE_BODY)
            self.assertEqual(response['Cache-Control'], 'no-store')

    def test_missing_headers(self):
        response = self.client.get(credential_path(self.PHONE_NUMBER_ID))
        self.assertEqual(response.json(), INVALID_SIGNATURE_BODY)

    def test_signature_is_bound_to_the_number(self):
        make_channel(self.instance, self.business, phone_number_id=OTHER_PHONE)
        response = self.get(OTHER_PHONE, sign_path=credential_path(self.PHONE_NUMBER_ID))
        self.assertEqual(response.json(), INVALID_SIGNATURE_BODY)

    def test_replay_is_rejected(self):
        request_id = str(uuid.uuid4())
        self.ok(self.get(request_id=request_id))
        self.assertEqual(self.get(request_id=request_id).json(), INVALID_SIGNATURE_BODY)

    def test_nonce_cache_down_fails_closed(self):
        with mock.patch('apps.leads.authentication.cache.add', side_effect=ConnectionError('redis down')):
            response = self.get()
        self.denied(response, 503, 'unavailable')

    def test_throttle_cache_down_fails_closed(self):
        broken = mock.Mock()
        broken.get.side_effect = ConnectionError('redis down')
        with mock.patch.object(throttles.AgentLeadSyncThrottle, 'cache', broken):
            response = self.get()
        self.denied(response, 503, 'unavailable')

    def test_revoked_credential_and_disabled_instance(self):
        AgentCredential.objects.filter(pk=self.credential.pk).update(status='revoked', revoked_at=timezone.now())
        self.assertEqual(self.get().json(), INVALID_SIGNATURE_BODY)
        fresh = make_credential(self.instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        self.ok(self.get(credential=fresh))
        self.instance.is_enabled = False
        self.instance.save(update_fields=['is_enabled'])
        self.assertEqual(self.get(credential=fresh).json(), INVALID_SIGNATURE_BODY)

    def test_human_sessions_cannot_read_it(self):
        path = credential_path(self.PHONE_NUMBER_ID)
        self.client.force_authenticate(user=staff())
        self.assertEqual(self.client.get(path).json(), INVALID_SIGNATURE_BODY)
        self.client.force_authenticate(user=None)
        user = get_user_model().objects.create_user(username=f'u-{uuid.uuid4().hex[:6]}', password='x-Test-1234')
        self.client.force_login(user)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(TOKEN, response.content.decode())

    @override_settings(AGENT_INTEGRATION_ENABLED=False)
    def test_integration_flag_off(self):
        self.denied(self.get(), 503, 'unavailable')

    def test_only_get(self):
        path = credential_path(self.PHONE_NUMBER_ID)
        for method in ('POST', 'PUT', 'DELETE'):
            headers = sign_headers(path=path, body=b'{}', key_id=self.credential.key_id, method=method)
            response = self.client.generic(method, path, data=b'{}', content_type='application/json', **headers)
            self.assertEqual(response.status_code, 405)


class NoSecretsNoSideEffectsTests(_Base):
    def test_logs_never_contain_secrets(self):
        stored = WhatsAppAuthorization.objects.get(pk=self.authorization.pk).encrypted_access_token
        with self.assertLogs('apps.leads', level='DEBUG') as logs:
            self.ok(self.get())
            self.get(secret='x' * 40)
            self.get('9999999999')
            wa.revoke_whatsapp_authorization(authorization_id=self.authorization.pk, actor=self.actor)
            self.get()
        output = '\n'.join(logs.output)
        self.assertIn('result=whatsapp_credential', output)
        self.assertIn('whatsapp_authorization_revoked', output)
        for secret in (TOKEN, TOKEN[4:24], stored, stored[10:40], SECRET):
            self.assertNotIn(secret, output)

    def test_success_has_no_other_secrets_or_ids(self):
        raw = self.get().content.decode()
        stored = WhatsAppAuthorization.objects.get(pk=self.authorization.pk).encrypted_access_token
        for private in (
            stored, SECRET, self.credential.encrypted_secret, self.credential.key_id, self.instance.external_id,
            str(self.channel.pk), str(self.authorization.pk),
        ):
            self.assertNotIn(private, raw)

    def test_get_has_no_side_effects(self):
        def snapshot():
            counts = {model._meta.label: model.objects.count() for model in django_apps.get_app_config('leads').get_models()}
            counts['audit'] = AccessAuditLog.objects.count()
            counts['authorization'] = WhatsAppAuthorization.objects.filter(pk=self.authorization.pk).values().get()
            counts['channel'] = AgentChannel.objects.filter(pk=self.channel.pk).values().get()
            return counts

        before = snapshot()
        with CaptureQueriesContext(connection) as queries:
            for _ in range(3):
                self.ok(self.get())
            self.get('9999999999')
        writes = [q['sql'] for q in queries.captured_queries if q['sql'].lstrip().split(' ', 1)[0].upper()
                  in {'INSERT', 'UPDATE', 'DELETE'}]
        self.assertEqual(writes, [])
        self.assertEqual(snapshot(), before)
