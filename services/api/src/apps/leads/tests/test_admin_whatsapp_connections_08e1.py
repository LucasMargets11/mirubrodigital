"""PROD-08E1 — Platform Admin: estado local de las conexiones WhatsApp."""
from __future__ import annotations

import datetime as dt
import io
import logging
import uuid
from unittest import mock

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import AccessAuditLog
from apps.billing.tests.test_reception_service_02b import _business, _reception, _superadmin
from apps.leads.models import AgentChannel, AgentInstance, WhatsAppAuthorization
from apps.leads.services import whatsapp_authorizations as wa

from .factories import TEST_KEY, make_channel, make_instance
from .test_receptionist_config_api_03b import member_client, staff_client

TOKEN = 'EAAG' + 'SecretoDeMetaParaElPanel' * 4
TOKEN_B = 'EAAG' + 'SecretoDeOtroComercioXYZ' * 4
WABA = '908070605040'
WRITE_SQL = ('INSERT', 'UPDATE', 'DELETE')


def url(business_or_id) -> str:
    return f'/api/v1/platform-admin/clients/{getattr(business_or_id, "id", business_or_id)}/whatsapp-connections/'


@override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class _Base(TestCase):
    def setUp(self):
        self.actor = _superadmin()
        self.business = _business()
        _reception(self.business)
        self.instance = make_instance(f'wa-panel-{uuid.uuid4().hex[:8]}')
        self.admin = staff_client()

    def authorize(self, channel, owner='self', token=TOKEN, waba=WABA, **kwargs):
        if owner == 'platform':
            authorization = wa.create_whatsapp_authorization(token=token, actor=self.actor, platform=True, **kwargs)
        else:
            authorization = wa.create_whatsapp_authorization(
                token=token, actor=self.actor, owner_business=channel.business if owner == 'self' else owner, **kwargs,
            )
        wa.associate_channel(channel_id=channel.pk, authorization_id=authorization.pk, waba_id=waba, actor=self.actor)
        return authorization

    def get(self, business=None, client=None, **extra):
        response = (client or self.admin).get(url(business or self.business), **extra)
        return response

    def channels(self, business=None):
        response = self.get(business)
        self.assertEqual(response.status_code, 200, response.content)
        return {row['phone_number_id']: row for row in response.json()['channels']}


class ContractTests(_Base):
    def test_business_without_channels(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        body = response.json()
        self.assertEqual(body['contract_version'], 1)
        self.assertEqual(body['business_id'], self.business.id)
        self.assertEqual(body['channels'], [])
        self.assertEqual(body['external_verification']['performed'], False)
        self.assertEqual(body['external_verification']['meta_connectivity'], 'unknown')

    def test_ready_channel_exposes_only_metadata(self):
        channel = make_channel(self.instance, self.business, phone_number_id='5491100001')
        authorization = self.authorize(channel, expires_at=timezone.now() + dt.timedelta(days=30))
        row = self.channels()['5491100001']
        self.assertEqual(row['local_status'], 'credential_ready')
        self.assertEqual(row['id'], str(channel.pk))
        self.assertEqual(row['provider'], 'whatsapp_cloud')
        self.assertEqual(row['waba_id'], WABA)
        self.assertTrue(row['is_active'])
        self.assertEqual(row['agent_instance'], {
            'external_id': self.instance.external_id, 'name': self.instance.name,
            'is_enabled': True, 'disabled_at': None,
        })
        self.assertEqual(row['authorization']['id'], str(authorization.pk))
        self.assertEqual(row['authorization']['kind'], 'business')
        self.assertTrue(row['authorization']['owned_by_this_business'])
        self.assertEqual(row['authorization']['status'], 'active')
        self.assertFalse(row['authorization']['expired'])
        self.assertIsNotNone(row['authorization']['expires_at'])
        # Nada que sugiera conectividad real.
        for key in ('online', 'connected', 'can_send', 'display_phone_number', 'meta_permissions'):
            self.assertNotIn(key, row)

    def test_multiple_channels_active_and_inactive(self):
        active = make_channel(self.instance, self.business, phone_number_id='5491100002')
        self.authorize(active)
        make_channel(
            self.instance, self.business, phone_number_id='5491100003', is_active=False,
            deactivated_at=timezone.now(),
        )
        make_channel(self.instance, self.business, phone_number_id='5491100004')
        rows = self.channels()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows['5491100002']['local_status'], 'credential_ready')
        self.assertEqual(rows['5491100003']['local_status'], 'channel_not_active')
        self.assertIsNotNone(rows['5491100003']['deactivated_at'])
        self.assertEqual(rows['5491100004']['local_status'], 'whatsapp_authorization_missing')
        self.assertIsNone(rows['5491100004']['authorization'])
        self.assertIsNone(rows['5491100004']['waba_id'])
        # Activos primero.
        self.assertFalse(self.get().json()['channels'][-1]['is_active'])

    def test_disabled_agent_instance(self):
        channel = make_channel(self.instance, self.business, phone_number_id='5491100005')
        self.authorize(channel)
        AgentInstance.objects.filter(pk=self.instance.pk).update(is_enabled=False, disabled_at=timezone.now())
        row = self.channels()['5491100005']
        self.assertEqual(row['local_status'], 'agent_instance_disabled')
        self.assertFalse(row['agent_instance']['is_enabled'])
        self.assertEqual(row['authorization']['status'], 'active')


class AuthorizationStateTests(_Base):
    def setUp(self):
        super().setUp()
        self.channel = make_channel(self.instance, self.business, phone_number_id='5491100010')

    def row(self):
        return self.channels()['5491100010']

    def test_missing(self):
        self.assertEqual(self.row()['local_status'], 'whatsapp_authorization_missing')

    def test_expired(self):
        authorization = self.authorize(self.channel, expires_at=timezone.now() + dt.timedelta(days=1))
        WhatsAppAuthorization.objects.filter(pk=authorization.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
        row = self.row()
        self.assertEqual(row['local_status'], 'whatsapp_authorization_expired')
        self.assertTrue(row['authorization']['expired'])
        self.assertEqual(row['authorization']['status'], 'active')

    def test_revoked(self):
        authorization = self.authorize(self.channel)
        wa.revoke_whatsapp_authorization(authorization_id=authorization.pk, actor=self.actor)
        row = self.row()
        self.assertEqual(row['local_status'], 'whatsapp_authorization_revoked')
        self.assertEqual(row['authorization']['status'], 'revoked')
        self.assertIsNotNone(row['authorization']['revoked_at'])

    def test_invalid(self):
        authorization = self.authorize(self.channel)
        WhatsAppAuthorization.objects.filter(pk=authorization.pk).update(status='invalid')
        row = self.row()
        self.assertEqual(row['local_status'], 'whatsapp_authorization_invalid')
        self.assertEqual(row['authorization']['status'], 'invalid')

    def test_waba_missing(self):
        self.authorize(self.channel)
        AgentChannel.objects.filter(pk=self.channel.pk).update(waba_id='')
        row = self.row()
        self.assertEqual(row['local_status'], 'whatsapp_waba_missing')
        self.assertIsNone(row['waba_id'])

    def test_same_rule_as_agent_delivery(self):
        """El estado local es exactamente la regla con la que se entrega la credencial."""
        authorization = self.authorize(self.channel)
        cases = [
            ('credential_ready', {}),
            ('whatsapp_authorization_invalid', {'status': 'invalid'}),
            ('whatsapp_authorization_expired', {'status': 'active', 'expires_at': timezone.now() - dt.timedelta(days=1)}),
        ]
        for expected, change in cases:
            with self.subTest(expected=expected):
                if change:
                    WhatsAppAuthorization.objects.filter(pk=authorization.pk).update(**change)
                self.assertEqual(self.row()['local_status'], expected)
                if expected == 'credential_ready':
                    self.assertEqual(wa.resolve_channel_access_token(self.channel.pk), TOKEN)
                else:
                    with self.assertRaises(wa.WhatsAppAuthorizationError) as ctx:
                        wa.resolve_channel_access_token(self.channel.pk)
                    self.assertEqual(ctx.exception.code, expected)


class SharedAndIsolationTests(_Base):
    def test_platform_authorization_shared_with_another_business(self):
        other = _business()
        _reception(other)
        mine = make_channel(self.instance, self.business, phone_number_id='5491100020')
        theirs = make_channel(self.instance, other, phone_number_id='5491100021')
        shared = self.authorize(mine, owner='platform')
        wa.associate_channel(channel_id=theirs.pk, authorization_id=shared.pk, waba_id='111222333', actor=self.actor)

        body = self.get().json()
        self.assertEqual([row['phone_number_id'] for row in body['channels']], ['5491100020'])
        authorization = body['channels'][0]['authorization']
        self.assertEqual(authorization['kind'], 'platform')
        self.assertIsNone(authorization['owned_by_this_business'])
        text = self.get().content.decode()
        # Nada del otro comercio: ni su canal, ni su WABA, ni su id.
        for value in ('5491100021', '111222333', str(theirs.pk), f'"business_id": {other.id}'):
            self.assertNotIn(value, text)
        self.assertEqual(self.channels()['5491100020']['local_status'], 'credential_ready')

    def test_owner_mismatch_does_not_reveal_the_owner(self):
        other = _business()
        channel = make_channel(self.instance, self.business, phone_number_id='5491100022')
        foreign = wa.create_whatsapp_authorization(token=TOKEN_B, actor=self.actor, owner_business=other)
        # Estado imposible por el servicio; se fuerza para comprobar el fail-closed.
        AgentChannel.objects.filter(pk=channel.pk).update(whatsapp_authorization=foreign, waba_id=WABA)
        response = self.get()
        row = {r['phone_number_id']: r for r in response.json()['channels']}['5491100022']
        self.assertEqual(row['local_status'], 'whatsapp_authorization_owner_mismatch')
        self.assertFalse(row['authorization']['owned_by_this_business'])
        self.assertNotIn('owner_business_id', row['authorization'])
        self.assertNotIn(other.id, row['authorization'].values())
        self.assertNotIn(f'"business_id": {other.id}', response.content.decode())

    def test_isolation_between_businesses(self):
        other = _business()
        _reception(other)
        make_channel(self.instance, self.business, phone_number_id='5491100030')
        make_channel(self.instance, other, phone_number_id='5491100031')
        self.assertEqual(list(self.channels(self.business)), ['5491100030'])
        self.assertEqual(list(self.channels(other)), ['5491100031'])


class AccessTests(_Base):
    def test_roles(self):
        self.assertEqual(self.get(client=staff_client('operations')).status_code, 200)
        for role in ('support_agent', 'content_admin'):
            with self.subTest(role=role):
                self.assertEqual(self.get(client=staff_client(role)).status_code, 403)
        merchant, _ = member_client(self.business, 'owner')
        self.assertEqual(self.get(client=merchant).status_code, 403)
        from rest_framework.test import APIClient
        self.assertIn(APIClient().get(url(self.business)).status_code, (401, 403))

    def test_reception_as_additional_service(self):
        business = _business(service='management')
        _reception(business)
        make_channel(self.instance, business, phone_number_id='5491100040')
        self.assertEqual(list(self.channels(business)), ['5491100040'])

    def test_client_not_found_cases(self):
        without_reception = _business(service='management')
        canceled = _business()
        _reception(canceled, status='canceled')
        branch = _business()
        _reception(branch)
        type(branch).objects.filter(pk=branch.pk).update(parent=self.business)
        for target in (without_reception, canceled, branch, 999_999_999):
            with self.subTest(target=getattr(target, 'id', target)):
                response = self.get(target)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()['code'], 'client_not_found')
                self.assertEqual(response['Cache-Control'], 'no-store')

    def test_ignores_bid_cookie_and_business_header(self):
        other = _business()
        _reception(other)
        make_channel(self.instance, self.business, phone_number_id='5491100050')
        make_channel(self.instance, other, phone_number_id='5491100051')
        self.admin.cookies['bid'] = str(other.id)
        for header in (str(other.id), 'abc'):
            with self.subTest(header=header):
                rows = self.channels_with(HTTP_X_BUSINESS_ID=header)
                self.assertEqual(list(rows), ['5491100050'])

    def channels_with(self, **extra):
        response = self.get(**extra)
        self.assertEqual(response.status_code, 200, response.content)
        return {row['phone_number_id']: row for row in response.json()['channels']}

    def test_only_get(self):
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.admin, method)(url(self.business), {}, format='json').status_code, 405)


class SecretsAndSideEffectsTests(_Base):
    def setUp(self):
        super().setUp()
        self.channel = make_channel(self.instance, self.business, phone_number_id='5491100060')
        self.authorization = self.authorize(self.channel)

    def test_no_token_or_ciphertext_in_response_or_logs(self):
        stored = WhatsAppAuthorization.objects.get(pk=self.authorization.pk).encrypted_access_token
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            response = self.get()
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)
        self.assertEqual(response.status_code, 200)
        for secret in (TOKEN, stored, stored[:40]):
            self.assertNotIn(secret, response.content.decode())
            self.assertNotIn(secret, stream.getvalue())
        for key in ('access_token', 'encrypted_access_token', 'token', 'secret'):
            self.assertNotIn(f'"{key}"', response.content.decode())

    def test_never_decrypts(self):
        with mock.patch.object(WhatsAppAuthorization, 'get_token', side_effect=AssertionError('decrypted')), \
                mock.patch('apps.leads.models.decrypt_agent_secret', side_effect=AssertionError('decrypted')):
            row = self.channels()['5491100060']
        self.assertEqual(row['local_status'], 'credential_ready')

    def test_get_has_no_writes(self):
        audits = AccessAuditLog.objects.count()
        updated_at = WhatsAppAuthorization.objects.get(pk=self.authorization.pk).updated_at
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.get().status_code, 200)
        writes = [q['sql'] for q in queries.captured_queries if q['sql'].lstrip().upper().startswith(WRITE_SQL)]
        self.assertEqual(writes, [])
        self.assertEqual(AccessAuditLog.objects.count(), audits)
        self.assertEqual(WhatsAppAuthorization.objects.get(pk=self.authorization.pk).updated_at, updated_at)
