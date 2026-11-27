"""PROD-03C — GET de configuración de Recepcionista IA para el agente (HMAC)."""
from __future__ import annotations

import json
import uuid

from django.apps import apps as django_apps
from django.test import override_settings

from apps.accounts.models import AccessAuditLog
from apps.business.models import Business, BusinessBillingProfile, BusinessBranding
from apps.leads.models import AgentChannel, AgentCredential, ReceptionistConfig

from .agent_client import sign_headers
from .factories import SECRET, make_business, make_channel, make_credential, make_instance
from .test_receiver_api import INVALID_SIGNATURE_BODY, ReceiverTestBase
from .test_receptionist_config_03a import complete

TOP_KEYS = {'ok', 'contract_version', 'business', 'channel', 'config'}
BUSINESS_KEYS = {'id', 'name', 'timezone', 'address', 'website', 'whatsapp_phone'}
CONFIG_KEYS = {'status', 'version', 'updated_at', 'missing_for_ready', 'content', 'automatic_attention_enabled'}


def config_path(business_id, phone_number_id) -> str:
    return f'/api/v1/integrations/agent/businesses/{business_id}/channels/{phone_number_id}/receptionist-config/'


class _Base(ReceiverTestBase):
    def get(self, business=None, phone=None, *, credential=None, secret=SECRET, **sign_kwargs):
        path = config_path((business or self.business).pk, phone or self.PHONE_NUMBER_ID)
        headers = sign_headers(
            path=path, body=b'', key_id=(credential or self.credential).key_id, secret=secret, method='GET',
            **sign_kwargs,
        )
        return self.client.get(path, **headers)

    def ok(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIn('X-Request-Id', response)
        body = response.json()
        self.assertEqual(set(body), TOP_KEYS)
        self.assertEqual(set(body['business']), BUSINESS_KEYS)
        self.assertEqual(set(body['config']), CONFIG_KEYS)
        self.assertEqual((body['ok'], body['contract_version']), (True, 1))
        return body


class ContractTests(_Base):
    def test_ready_full_shape_without_any_lead(self):
        BusinessBillingProfile.objects.filter(business=self.business).update(
            commercial_address='Av. Siempreviva 742', website='https://ejemplo.test',
        )
        BusinessBranding.objects.filter(business=self.business).update(whatsapp_phone='+5491112345678')
        config = ReceptionistConfig.objects.create(business=self.business, status='ready', **complete(
            faqs=[{'question': '¿Abren sábados?', 'answer': 'No.'}],
        ))
        body = self.ok(self.get())
        self.assertEqual(body['business'], {
            'id': self.business.pk, 'name': self.business.name, 'timezone': 'America/Argentina/Buenos_Aires',
            'address': 'Av. Siempreviva 742', 'website': 'https://ejemplo.test', 'whatsapp_phone': '+5491112345678',
        })
        self.assertEqual(body['channel'], {'provider': 'whatsapp_cloud', 'phone_number_id': self.PHONE_NUMBER_ID})
        self.assertEqual(body['config']['status'], 'ready')
        self.assertEqual(body['config']['version'], config.version)
        self.assertEqual(body['config']['missing_for_ready'], [])
        self.assertEqual(set(body['config']['content']), set(ReceptionistConfig.CONTENT_FIELDS))
        self.assertEqual(body['config']['content']['assistant_name'], 'Sofía')
        self.assertEqual(body['config']['content']['faqs'], [{'question': '¿Abren sábados?', 'answer': 'No.'}])

    def test_missing_profiles_are_null_not_errors(self):
        BusinessBillingProfile.objects.filter(business=self.business).delete()
        BusinessBranding.objects.filter(business=self.business).delete()
        body = self.ok(self.get())
        self.assertEqual(
            (body['business']['address'], body['business']['website'], body['business']['whatsapp_phone']),
            (None, None, None),
        )

    def test_missing_config(self):
        body = self.ok(self.get())
        self.assertEqual(body['config'], {
            'status': 'missing', 'version': None, 'updated_at': None, 'missing_for_ready': None, 'content': None,
            'automatic_attention_enabled': False,
        })

    def test_draft_never_delivers_content(self):
        ReceptionistConfig.objects.create(business=self.business, **complete(
            welcome_message='', custom_instructions='INSTRUCCION-BORRADOR',
        ))
        response = self.get()
        body = self.ok(response)
        self.assertEqual(body['config']['status'], 'draft')
        self.assertIsNone(body['config']['content'])
        self.assertEqual(body['config']['missing_for_ready'], ['welcome_message'])
        self.assertNotIn(b'INSTRUCCION-BORRADOR', response.content)

    def test_complete_but_draft_still_has_no_content(self):
        ReceptionistConfig.objects.create(business=self.business, **complete())
        body = self.ok(self.get())
        self.assertEqual((body['config']['status'], body['config']['missing_for_ready']), ('draft', []))
        self.assertIsNone(body['config']['content'])

    def test_content_update_and_version(self):
        config = ReceptionistConfig.objects.create(business=self.business, status='ready', **complete())
        first = self.ok(self.get())['config']
        config.assistant_name = 'Valentina'
        config.save()
        second = self.ok(self.get())['config']
        self.assertEqual((second['version'], second['content']['assistant_name']), (first['version'] + 1, 'Valentina'))
        config.status = 'draft'
        config.save()
        third = self.ok(self.get())['config']
        self.assertEqual((third['status'], third['version'], third['content']), ('draft', first['version'] + 2, None))

    def test_business_data_is_live_and_does_not_move_config_version(self):
        ReceptionistConfig.objects.create(business=self.business, status='ready', **complete())
        before = self.ok(self.get())
        Business.objects.filter(pk=self.business.pk).update(name='Nombre Nuevo', timezone='America/Montevideo')
        BusinessBillingProfile.objects.filter(business=self.business).update(commercial_address='Calle 2')
        after = self.ok(self.get())
        self.assertEqual(
            (after['business']['name'], after['business']['timezone'], after['business']['address']),
            ('Nombre Nuevo', 'America/Montevideo', 'Calle 2'),
        )
        self.assertEqual(after['config']['version'], before['config']['version'])
        self.assertEqual(after['config']['updated_at'], before['config']['updated_at'])
        # Sin copia: ReceptionistConfig no guarda nada de Business
        self.assertNotIn('Nombre Nuevo', json.dumps(after['config']))


class IsolationTests(_Base):
    def test_one_instance_two_businesses_two_configs(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        make_channel(self.instance, other, phone_number_id='2222222222')
        ReceptionistConfig.objects.create(business=self.business, status='ready', **complete(assistant_name='Ana'))
        ReceptionistConfig.objects.create(business=other, status='ready', **complete(assistant_name='Bruno'))
        a = self.ok(self.get())
        b = self.ok(self.get(other, '2222222222'))
        self.assertEqual((a['business']['id'], a['config']['content']['assistant_name']), (self.business.pk, 'Ana'))
        self.assertEqual((b['business']['id'], b['config']['content']['assistant_name']), (other.pk, 'Bruno'))

    def test_foreign_channel(self):
        foreign = make_instance(f'other-agent-{uuid.uuid4().hex[:8]}')
        foreign_business = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        make_channel(foreign, foreign_business, phone_number_id='3333333333')
        ReceptionistConfig.objects.create(business=foreign_business, status='ready', **complete())
        self.assertError(self.get(foreign_business, '3333333333'), 403, 'channel_disabled')

    def test_deactivated_and_unknown_channel(self):
        self.assertError(self.get(phone='9999999999'), 403, 'channel_disabled')
        AgentChannel.objects.filter(pk=self.channel.pk).update(is_active=False, deactivated_at='2026-11-26T00:00Z')
        self.assertError(self.get(), 403, 'channel_disabled')

    def test_business_mismatch_and_suspended(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        ReceptionistConfig.objects.create(business=other, status='ready', **complete(assistant_name='Ajeno'))
        response = self.get(other, self.PHONE_NUMBER_ID)
        self.assertError(response, 409, 'business_mismatch')
        self.assertNotIn(b'Ajeno', response.content)
        Business.objects.filter(pk=self.business.pk).update(status='suspended')
        self.assertError(self.get(), 403, 'business_inactive')

    def test_malformed_path_is_router_404(self):
        for path in (
            '/api/v1/integrations/agent/businesses/abc/channels/1234567890/receptionist-config/',
            '/api/v1/integrations/agent/businesses/1/channels/12ab/receptionist-config/',
        ):
            headers = sign_headers(path=path, body=b'', key_id=self.credential.key_id, method='GET')
            self.assertEqual(self.client.get(path, **headers).status_code, 404)


class AuthenticationTests(_Base):
    def test_invalid_credentials(self):
        self.assertEqual(self.get(secret='x' * 40).json(), INVALID_SIGNATURE_BODY)
        unknown = AgentCredential(agent_instance=self.instance, key_id='never-created')
        self.assertEqual(self.get(credential=unknown).status_code, 401)
        self.assertEqual(self.get(timestamp=1).status_code, 401)

    def test_revoked_credential_and_disabled_instance(self):
        AgentCredential.objects.filter(pk=self.credential.pk).update(status='revoked', revoked_at='2026-11-26T00:00Z')
        self.assertEqual(self.get().json(), INVALID_SIGNATURE_BODY)
        fresh = make_credential(self.instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        self.assertEqual(self.get(credential=fresh).status_code, 200)
        self.instance.is_enabled = False
        self.instance.save(update_fields=['is_enabled'])
        self.assertEqual(self.get(credential=fresh).status_code, 401)

    def test_replay_is_rejected(self):
        request_id = str(uuid.uuid4())
        self.assertEqual(self.get(request_id=request_id).status_code, 200)
        self.assertEqual(self.get(request_id=request_id).json(), INVALID_SIGNATURE_BODY)

    def test_signature_is_bound_to_the_path(self):
        other = make_business(f'biz-{uuid.uuid4().hex[:8]}')
        make_channel(self.instance, other, phone_number_id='2222222222')
        headers = sign_headers(
            path=config_path(self.business.pk, self.PHONE_NUMBER_ID), body=b'', key_id=self.credential.key_id,
            method='GET',
        )
        self.assertEqual(self.client.get(config_path(other.pk, '2222222222'), **headers).status_code, 401)

    def test_merchant_session_is_not_an_agent(self):
        from apps.billing.tests.test_reception_service_02b import _superadmin

        self.client.force_authenticate(user=_superadmin())
        response = self.client.get(config_path(self.business.pk, self.PHONE_NUMBER_ID))
        self.assertEqual(response.status_code, 401)

    @override_settings(AGENT_INTEGRATION_ENABLED=False)
    def test_integration_flag_off(self):
        self.assertError(self.get(), 503, 'unavailable')

    def test_only_get(self):
        path = config_path(self.business.pk, self.PHONE_NUMBER_ID)
        headers = sign_headers(path=path, body=b'{}', key_id=self.credential.key_id, method='PUT')
        response = self.client.generic('PUT', path, data=b'{}', content_type='application/json', **headers)
        self.assertEqual(response.status_code, 405)


class NoSecretsNoSideEffectsTests(_Base):
    def test_no_secrets_fiscal_or_internal_data(self):
        BusinessBillingProfile.objects.filter(business=self.business).update(
            legal_name='RAZON-SOCIAL-SA', tax_id='30-12345678-9', iibb='IIBB-123', email='facturas@privado.test',
            phone='+54 11 0000-0000', fiscal_address='DOMICILIO-FISCAL', commercial_address='Calle 1',
        )
        ReceptionistConfig.objects.create(business=self.business, status='ready', **complete())
        raw = self.get().content.decode()
        for private in (
            'RAZON-SOCIAL-SA', '30-12345678-9', 'IIBB-123', 'facturas@privado.test', '0000-0000', 'DOMICILIO-FISCAL',
            SECRET, self.credential.encrypted_secret, self.credential.key_id, self.instance.external_id,
            str(self.channel.pk), 'subscription', 'agenda', 'usage', 'plan',
        ):
            self.assertNotIn(private, raw)

    def test_get_has_no_side_effects(self):
        ReceptionistConfig.objects.create(business=self.business, **complete())

        def snapshot():
            counts = {
                model._meta.label: model.objects.count()
                for model in django_apps.get_app_config('leads').get_models()
            }
            counts['audit'] = AccessAuditLog.objects.count()
            config = ReceptionistConfig.objects.get(business=self.business)
            counts['config'] = (config.version, config.status, config.updated_at)
            return counts

        before = snapshot()
        for _ in range(3):
            self.ok(self.get())
        self.ok(self.get(phone=self.PHONE_NUMBER_ID))
        self.assertEqual(snapshot(), before)

    def test_missing_config_is_never_created_by_get(self):
        self.ok(self.get())
        self.assertFalse(ReceptionistConfig.objects.exists())
