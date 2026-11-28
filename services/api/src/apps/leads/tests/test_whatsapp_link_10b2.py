"""PROD-10B2 — Servicio común de vinculación segura de WhatsApp.

Graph simulado (sesión falsa de PROD-10B1): ninguna llamada real a Meta ni
credenciales reales. PostgreSQL descartable del runner de tests.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
import uuid
from unittest import mock

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AccessAuditLog
from apps.billing.models import SubscriptionV2
from apps.billing.tests.test_reception_service_02b import _business, _reception, _superadmin
from apps.business.models import Business
from apps.leads.models import AgentChannel, ReceptionistConfig, WhatsAppAuthorization
from apps.leads.services import whatsapp_authorizations as wa
from apps.leads.services import whatsapp_link as wl
from apps.leads.services.meta_graph import MetaGraphError

from .agent_client import sign_headers
from .factories import SECRET, TEST_KEY, enable_reception_attention, make_channel, make_credential, make_instance
from .test_meta_graph_10b1 import (
    APP_ID, APP_SECRET, META_SETTINGS, PHONE, TOKEN, WABA, FakeResponse, FakeSession, apps, debug, meta_error,
    our_app, phones,
)

TOKEN_2 = 'EAAG-otro-token-NOT-REAL-' + 'y' * 40
INSTANCE = 'shared-agent-10b2'
SECRETS = (TOKEN, TOKEN_2, APP_SECRET, f'{APP_ID}|{APP_SECRET}')
LINK_SETTINGS = dict(
    META_SETTINGS, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY, AGENT_INTEGRATION_ENABLED=True,
    WHATSAPP_LINK_AGENT_INSTANCE_ID=INSTANCE,
)


def ts(days: float) -> int:
    return int((timezone.now() + dt.timedelta(days=days)).timestamp())


def routes(*, debug_response=None, phone_response=None, apps_response=None, waba=WABA):
    return {
        'debug_token': debug_response or debug(expires_at=ts(60), data_access_expires_at=ts(90)),
        f'{waba}/phone_numbers': phone_response or phones(PHONE),
        f'{waba}/subscribed_apps': apps_response or apps(our_app()),
    }


def graph(**kwargs) -> FakeSession:
    return FakeSession(routes(**kwargs))


class _Mixin:
    def make_world(self):
        self.actor = _superadmin()
        self.business = _business()
        _reception(self.business)
        self.instance = make_instance(INSTANCE)

    def link(self, *, business=None, token=TOKEN, waba=WABA, phone=PHONE, session=None, actor=None,
             source=wl.SOURCE_ASSISTED, reason='Alta asistida del cliente'):
        return wl.link_whatsapp_channel(
            business=business or self.business, waba_id=waba, phone_number_id=phone, token=token,
            actor=actor or self.actor, reason=reason, source=source,
            session=session if session is not None else graph(waba=waba),
        )


@override_settings(**LINK_SETTINGS)
class _Base(_Mixin, TestCase):
    def setUp(self):
        self.make_world()

    def assertCode(self, code, **kwargs):
        with self.assertRaises(wa.WhatsAppAuthorizationError) as ctx:
            self.link(**kwargs)
        self.assertEqual(ctx.exception.code, code)
        self.assertNoSecrets(str(ctx.exception))
        return ctx.exception

    def assertMetaCode(self, code, session):
        with self.assertRaises(MetaGraphError) as ctx:
            self.link(session=session)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def assertNoSecrets(self, *texts):
        for text in texts:
            for secret in SECRETS:
                self.assertNotIn(secret, str(text))

    def assertNothingWritten(self):
        self.assertFalse(AgentChannel.objects.filter(phone_number_id=PHONE).exists())
        self.assertEqual(WhatsAppAuthorization.objects.count(), 0)
        self.assertEqual(AccessAuditLog.objects.filter(action__startswith='WHATSAPP_').count(), 0)

    def link_audits(self):
        return list(AccessAuditLog.objects.filter(action='WHATSAPP_CHANNEL_LINKED').order_by('created_at', 'id'))


# ── Vinculación válida ───────────────────────────────────────────────────────

class LinkTests(_Base):
    def test_valid_link_creates_owned_encrypted_authorization_and_channel(self):
        result = self.link()
        self.assertEqual((result.outcome, result.created_channel, result.created_authorization),
                         ('linked', True, True))
        channel = AgentChannel.objects.select_related('whatsapp_authorization').get(pk=result.channel.pk)
        self.assertEqual((channel.business_id, channel.agent_instance_id, channel.phone_number_id, channel.waba_id),
                         (self.business.pk, self.instance.pk, PHONE, WABA))
        self.assertTrue(channel.is_active)
        authorization = channel.whatsapp_authorization
        self.assertEqual(str(authorization.pk), result.authorization_id)
        self.assertEqual(authorization.owner_business_id, self.business.pk)
        self.assertFalse(authorization.is_platform)
        self.assertEqual(authorization.status, 'active')
        raw = WhatsAppAuthorization.objects.filter(pk=authorization.pk).values_list('encrypted_access_token', flat=True)[0]
        self.assertTrue(raw.startswith('gAAAAA'))
        self.assertNotIn(TOKEN, raw)
        self.assertEqual(authorization.get_token(), TOKEN)
        self.assertIsNone(wa.channel_credential_problem(channel, timezone.now()))

    def test_effective_expiry_is_the_earliest_of_token_and_data_access(self):
        token_exp, data_exp = ts(90), ts(30)
        result = self.link(session=FakeSession(routes(
            debug_response=debug(expires_at=token_exp, data_access_expires_at=data_exp),
        )))
        authorization = WhatsAppAuthorization.objects.get(pk=result.authorization_id)
        self.assertEqual(authorization.expires_at, dt.datetime.fromtimestamp(data_exp, tz=dt.timezone.utc))
        self.assertEqual(result.verification['token']['expires_at'],
                         dt.datetime.fromtimestamp(token_exp, tz=dt.timezone.utc).isoformat())

    def test_no_expiry_reported_keeps_expires_at_null(self):
        result = self.link(session=FakeSession(routes(debug_response=debug(expires_at=0, data_access_expires_at=0))))
        self.assertIsNone(WhatsAppAuthorization.objects.get(pk=result.authorization_id).expires_at)

    def test_audit_is_metadata_only_and_complete(self):
        result = self.link(source=wl.SOURCE_EMBEDDED_SIGNUP)
        actions = list(AccessAuditLog.objects.filter(business=self.business).values_list('action', flat=True))
        for action in ('WHATSAPP_AUTHORIZATION_CREATED', 'WHATSAPP_AUTHORIZATION_LINKED', 'WHATSAPP_CHANNEL_LINKED'):
            self.assertIn(action, actions)
        [audit] = self.link_audits()
        self.assertEqual(audit.entity_id, str(result.channel.pk))
        self.assertEqual(audit.details['outcome'], 'linked')
        self.assertEqual(audit.details['source'], 'embedded_signup')
        self.assertEqual(audit.details['reason'], 'Alta asistida del cliente')
        self.assertEqual(audit.details['agent_instance'], INSTANCE)
        self.assertIs(audit.details['legal_ownership_verified'], False)
        for row in AccessAuditLog.objects.all():
            self.assertNoSecrets(row.details)
        self.assertNoSecrets(repr(result), result.verification)

    def test_reuses_existing_channel_without_credential(self):
        channel = make_channel(self.instance, self.business, phone_number_id=PHONE)
        result = self.link()
        self.assertEqual(result.channel.pk, channel.pk)
        self.assertEqual((result.created_channel, result.created_authorization), (False, True))
        self.assertEqual(AgentChannel.objects.filter(phone_number_id=PHONE).count(), 1)

    def test_no_secret_in_logs(self):
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger('apps.leads').debug('marker')
            self.link()
        self.assertNoSecrets(*logs.output)

    def test_meta_calls_send_token_only_in_headers(self):
        session = graph()
        self.link(session=session)
        self.assertEqual(len(session.calls), 3)
        for call in session.calls:
            self.assertNotIn(TOKEN, call['url'])


# ── Validaciones previas: nada se escribe ────────────────────────────────────

class LocalValidationTests(_Base):
    def test_operations_staff_is_rejected(self):
        operations = _superadmin()
        operations.account_profile.internal_role = 'operations'
        operations.account_profile.save(update_fields=['internal_role'])
        session = graph()
        self.assertCode('actor_not_authorized', actor=operations, session=session)
        self.assertEqual(session.calls, [])
        self.assertNothingWritten()

    def test_non_staff_is_rejected(self):
        user = _superadmin()
        user.account_profile.is_platform_staff = False
        user.account_profile.save(update_fields=['is_platform_staff'])
        self.assertCode('actor_not_authorized', actor=user)

    def test_invalid_source_and_reason(self):
        self.assertCode('invalid_source', source='platform')
        self.assertCode('invalid_reason', reason='   ')
        self.assertCode('invalid_reason', reason='x' * 256)
        self.assertNothingWritten()

    def test_client_without_reception_is_not_eligible(self):
        SubscriptionV2.objects.filter(business=self.business).update(status=SubscriptionV2.Status.CANCELED)
        session = graph()
        self.assertCode('client_not_eligible', session=session)
        self.assertEqual(session.calls, [])
        self.assertNothingWritten()

    def test_branch_is_not_eligible(self):
        branch = Business.objects.create(
            name='Sucursal', slug=f'br-{uuid.uuid4().hex[:6]}', parent=self.business, service_type='reception',
            default_service='reception', status='active',
        )
        _reception(branch)
        self.assertCode('client_not_eligible', business=branch)

    @override_settings(WHATSAPP_LINK_AGENT_INSTANCE_ID='')
    def test_instance_not_configured(self):
        session = graph()
        self.assertCode('agent_instance_not_configured', session=session)
        self.assertEqual(session.calls, [])

    @override_settings(WHATSAPP_LINK_AGENT_INSTANCE_ID='missing-instance')
    def test_instance_missing(self):
        self.assertCode('agent_instance_unavailable')

    def test_instance_disabled(self):
        self.instance.is_enabled = False
        self.instance.save(update_fields=['is_enabled'])
        session = graph()
        self.assertCode('agent_instance_unavailable', session=session)
        self.assertEqual(session.calls, [])
        self.assertNothingWritten()

    def test_malformed_token_is_rejected_before_meta(self):
        session = graph()
        self.assertCode('invalid_token', token='short', session=session)
        self.assertEqual(session.calls, [])


class MetaVerificationTests(_Base):
    def test_invalid_token(self):
        self.assertMetaCode('token_invalid', FakeSession(routes(debug_response=debug(is_valid=False))))
        self.assertNothingWritten()

    def test_expired_token(self):
        self.assertMetaCode('token_expired', FakeSession(routes(debug_response=debug(expires_at=ts(-1)))))
        self.assertNothingWritten()

    def test_data_access_expired(self):
        self.assertMetaCode('data_access_expired', FakeSession(routes(
            debug_response=debug(expires_at=ts(30), data_access_expires_at=ts(-1)),
        )))
        self.assertNothingWritten()

    def test_other_app_token(self):
        self.assertMetaCode('token_app_mismatch', FakeSession(routes(debug_response=debug(app_id='999'))))
        self.assertNothingWritten()

    def test_missing_permissions(self):
        self.assertMetaCode('permissions_missing', FakeSession(routes(
            debug_response=debug(expires_at=ts(30), scopes=['whatsapp_business_management']),
        )))
        self.assertNothingWritten()

    def test_scope_not_covering_the_waba(self):
        self.assertMetaCode('resource_scope_not_granted', FakeSession(routes(debug_response=debug(
            expires_at=ts(30), granular_scopes=[
                {'scope': 'whatsapp_business_management', 'target_ids': ['555']},
                {'scope': 'whatsapp_business_messaging', 'target_ids': ['555']},
            ],
        ))))
        self.assertNothingWritten()

    def test_phone_outside_the_waba(self):
        self.assertMetaCode('phone_number_not_in_waba', FakeSession(routes(phone_response=phones('111'))))
        self.assertNothingWritten()

    def test_meta_unavailable_is_transient_and_writes_nothing(self):
        error = self.assertMetaCode('meta_unavailable', FakeSession(routes(phone_response=meta_error(503, 2))))
        self.assertTrue(error.transient)
        self.assertNothingWritten()

    def test_expiry_reached_between_verification_and_write(self):
        verified = wl.verify_whatsapp_resources(
            token=TOKEN, waba_id=WABA, phone_number_id=PHONE,
            session=FakeSession(routes(debug_response=debug(expires_at=ts(1), data_access_expires_at=ts(2)))),
        )
        later = timezone.now() + dt.timedelta(days=1, hours=1)  # Meta tardó: venció en el medio
        with mock.patch.object(wl, 'verify_whatsapp_resources', return_value=verified), \
                mock.patch.object(wl.timezone, 'now', return_value=later):
            self.assertCode('whatsapp_authorization_expired')
        self.assertNothingWritten()


# ── Idempotencia y conflictos ────────────────────────────────────────────────

class IdempotencyAndConflictTests(_Base):
    def test_equivalent_repeat_does_not_duplicate(self):
        first = self.link()
        second = self.link()
        self.assertEqual((second.outcome, second.created_channel, second.created_authorization),
                         ('already_linked', False, False))
        self.assertEqual(second.channel.pk, first.channel.pk)
        self.assertEqual(second.authorization_id, first.authorization_id)
        self.assertEqual(AgentChannel.objects.filter(phone_number_id=PHONE).count(), 1)
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)
        self.assertEqual([a.details['outcome'] for a in self.link_audits()], ['linked', 'already_linked'])
        channel = AgentChannel.objects.select_related('whatsapp_authorization').get(pk=first.channel.pk)
        self.assertEqual(wl.channel_meta_verification(channel), second.verification)

    def test_different_token_is_not_rotated_silently(self):
        first = self.link()
        before = WhatsAppAuthorization.objects.get(pk=first.authorization_id)
        self.assertCode('channel_credential_conflict', token=TOKEN_2)
        after = WhatsAppAuthorization.objects.get(pk=first.authorization_id)
        self.assertEqual((after.get_token(), after.updated_at), (TOKEN, before.updated_at))
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)
        self.assertEqual(len(self.link_audits()), 1)

    def test_number_active_for_another_business_is_rejected_without_revealing_it(self):
        other = _business()
        _reception(other)
        make_channel(self.instance, other, phone_number_id=PHONE)
        session = graph()
        error = self.assertCode('phone_number_unavailable', session=session)
        self.assertEqual(session.calls, [])
        self.assertNotIn(str(other.pk), str(error))
        self.assertNotIn(other.name, str(error))
        self.assertEqual(AgentChannel.objects.get(phone_number_id=PHONE).business_id, other.pk)
        self.assertEqual(WhatsAppAuthorization.objects.count(), 0)

    def test_other_waba_is_rejected(self):
        self.link()
        self.assertCode('channel_waba_mismatch', waba='777888999')
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)

    def test_other_instance_is_rejected(self):
        make_channel(make_instance('other-agent-10b2'), self.business, phone_number_id=PHONE)
        self.assertCode('channel_agent_instance_mismatch')
        self.assertEqual(WhatsAppAuthorization.objects.count(), 0)

    def test_revoked_or_platform_credential_is_not_replaced(self):
        result = self.link()
        wa.revoke_whatsapp_authorization(authorization_id=result.authorization_id, actor=self.actor)
        self.assertCode('channel_credential_conflict')
        other_phone = '555000111222'
        channel = make_channel(self.instance, self.business, phone_number_id=other_phone)
        platform = wa.create_whatsapp_authorization(token=TOKEN, actor=self.actor, platform=True)
        wa.associate_channel(channel_id=channel.pk, authorization_id=platform.pk, waba_id=WABA, actor=self.actor)
        self.assertCode('channel_credential_conflict', phone=other_phone)
        self.assertEqual(WhatsAppAuthorization.objects.count(), 2)

    def test_conflict_detected_under_lock_after_verification(self):
        """El número se ocupa mientras se consultaba a Meta: revalidación en la transacción."""
        other = _business()
        session = graph()
        real = wl.verify_whatsapp_resources

        def verify_then_steal(**kwargs):
            result = real(**kwargs)
            make_channel(self.instance, other, phone_number_id=PHONE)
            return result

        with mock.patch.object(wl, 'verify_whatsapp_resources', side_effect=verify_then_steal):
            self.assertCode('phone_number_unavailable', session=session)
        self.assertEqual(WhatsAppAuthorization.objects.count(), 0)


# ── Atomicidad ───────────────────────────────────────────────────────────────

class RollbackTests(_Base):
    def test_audit_failure_rolls_back_everything(self):
        with mock.patch.object(wl, 'record_platform_action', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                self.link()
        self.assertNothingWritten()

    def test_association_failure_leaves_no_orphan_authorization(self):
        with mock.patch.object(wa, 'associate_channel', side_effect=RuntimeError('db down')):
            with self.assertRaises(RuntimeError):
                self.link()
        self.assertNothingWritten()

    def test_evidence_failure_on_existing_channel_rolls_back(self):
        channel = make_channel(self.instance, self.business, phone_number_id=PHONE)
        real_save = AgentChannel.save

        def failing_save(obj, *args, **kwargs):
            if kwargs.get('update_fields') == ['meta_verification']:
                raise RuntimeError('write failed')
            return real_save(obj, *args, **kwargs)

        with mock.patch.object(AgentChannel, 'save', failing_save):
            with self.assertRaises(RuntimeError):
                self.link()
        channel.refresh_from_db()
        self.assertIsNone(channel.whatsapp_authorization_id)
        self.assertEqual((channel.waba_id, channel.meta_verification), ('', None))
        self.assertEqual(WhatsAppAuthorization.objects.count(), 0)


# ── Evidencia ────────────────────────────────────────────────────────────────

class EvidenceTests(_Base):
    def channel(self, result):
        return AgentChannel.objects.select_related('whatsapp_authorization').get(pk=result.channel.pk)

    def test_evidence_contents_are_non_secret_and_bound(self):
        result = self.link()
        evidence = wl.channel_meta_verification(self.channel(result))
        self.assertEqual(evidence, result.verification)
        self.assertEqual(evidence['version'], 1)
        self.assertEqual((evidence['authorization_id'], evidence['waba_id'], evidence['phone_number_id']),
                         (result.authorization_id, WABA, PHONE))
        self.assertEqual((evidence['app_subscribed'], evidence['override_callback_configured']), (True, False))
        self.assertEqual(evidence['phone']['verified_name'], 'Clínica Sol')
        self.assertEqual(evidence['phone']['platform_type'], 'CLOUD_API')
        self.assertEqual(set(evidence['token']), {'type', 'scope_coverage', 'expires_at', 'data_access_expires_at'})
        self.assertNotIn('throughput', evidence['phone'])  # solo los campos elegidos, nunca la respuesta cruda
        self.assertIs(evidence['legal_ownership_verified'], False)
        self.assertNoSecrets(evidence)

    def test_unsubscribed_app_is_recorded_as_observed(self):
        result = self.link(session=FakeSession(routes(apps_response=apps())))
        self.assertIs(result.verification['app_subscribed'], False)
        self.assertIsNone(result.verification['override_callback_configured'])

    def test_rotation_invalidates(self):
        result = self.link()
        wa.rotate_whatsapp_authorization(authorization_id=result.authorization_id, token=TOKEN_2, actor=self.actor)
        self.assertIsNone(wl.channel_meta_verification(self.channel(result)))

    def test_revocation_invalidates(self):
        result = self.link()
        wa.revoke_whatsapp_authorization(authorization_id=result.authorization_id, actor=self.actor)
        self.assertIsNone(wl.channel_meta_verification(self.channel(result)))

    def test_reassociation_or_waba_change_invalidates(self):
        result = self.link()
        other = wa.create_whatsapp_authorization(token=TOKEN_2, actor=self.actor, owner_business=self.business)
        wa.associate_channel(channel_id=result.channel.pk, authorization_id=other.pk, waba_id=WABA, actor=self.actor)
        self.assertIsNone(wl.channel_meta_verification(self.channel(result)))
        wa.associate_channel(
            channel_id=result.channel.pk, authorization_id=result.authorization_id, waba_id='444555666',
            actor=self.actor,
        )
        self.assertIsNone(wl.channel_meta_verification(self.channel(result)))

    def test_expiry_or_deactivation_invalidates(self):
        result = self.link(session=FakeSession(routes(
            debug_response=debug(expires_at=ts(1), data_access_expires_at=ts(1)),
        )))
        channel = self.channel(result)
        self.assertIsNotNone(wl.channel_meta_verification(channel))
        self.assertIsNone(wl.channel_meta_verification(channel, timezone.now() + dt.timedelta(days=2)))
        AgentChannel.objects.filter(pk=channel.pk).update(is_active=False, deactivated_at=timezone.now())
        self.assertIsNone(wl.channel_meta_verification(self.channel(result)))

    def test_tampered_or_missing_evidence_is_ignored(self):
        result = self.link()
        for broken in ({**result.verification, 'version': 2}, {**result.verification, 'authorization_updated_at': 'x'},
                       {**result.verification, 'phone_number_id': '1'}):
            AgentChannel.objects.filter(pk=result.channel.pk).update(meta_verification=broken)
            self.assertIsNone(wl.channel_meta_verification(self.channel(result)))
        self.assertIsNone(wl.channel_meta_verification(make_channel(self.instance, self.business, phone_number_id='42')))
        self.assertIsNone(wl.channel_meta_verification(None))


# ── Atención automática ──────────────────────────────────────────────────────

class AttentionTests(_Base):
    def test_attention_disabled_stays_disabled(self):
        result = self.link()
        self.assertIs(result.automatic_attention_enabled, False)
        self.assertFalse(ReceptionistConfig.objects.filter(business=self.business).exists())

    def test_enabled_attention_is_preserved_untouched(self):
        config = enable_reception_attention(self.business)
        before = ReceptionistConfig.objects.filter(pk=config.pk).values().get()
        result = self.link()
        self.assertIs(result.automatic_attention_enabled, True)
        self.assertEqual(ReceptionistConfig.objects.filter(pk=config.pk).values().get(), before)
        self.assertIs(self.link_audits()[0].details['automatic_attention_enabled'], True)


# ── Entrega por el endpoint HMAC existente (PROD-04C) ────────────────────────

class CredentialDeliveryTests(_Base):
    def test_linked_channel_credential_is_delivered_to_the_agent(self):
        credential = make_credential(self.instance, key_id=f'key-{uuid.uuid4().hex[:8]}')
        result = self.link()
        path = f'/api/v1/integrations/agent/channels/{PHONE}/whatsapp-credential/'
        headers = sign_headers(path=path, body=b'', key_id=credential.key_id, secret=SECRET, method='GET')
        response = self.client.get(path, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body['business_id'], body['phone_number_id'], body['waba_id'], body['access_token']),
                         (self.business.pk, PHONE, WABA, TOKEN))
        expires = WhatsAppAuthorization.objects.get(pk=result.authorization_id).expires_at
        self.assertEqual(dt.datetime.fromisoformat(body['expires_at']), expires)


# ── Concurrencia (transacciones reales) ──────────────────────────────────────

@override_settings(**LINK_SETTINGS)
class ConcurrencyTests(_Mixin, TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        self.make_world()

    def race(self, *calls):
        results, barrier = [], threading.Barrier(len(calls))
        real = wl.record_platform_action

        def slow(**kwargs):
            time.sleep(0.3)  # retiene los locks: el otro espera o choca con la constraint
            return real(**kwargs)

        def worker(call):
            try:
                barrier.wait()
                results.append(call().outcome)
            except wa.WhatsAppAuthorizationError as error:
                results.append(error.code)
            except Exception as error:  # visible en el assert, no se pierde en el hilo
                results.append(repr(error))
            finally:
                connection.close()

        with mock.patch.object(wl, 'record_platform_action', side_effect=slow):
            threads = [threading.Thread(target=worker, args=(call,)) for call in calls]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(15)
        return sorted(results)

    def test_meta_is_called_outside_any_transaction(self):
        states = []

        class Probe(FakeSession):
            def request(self, method, url, **kwargs):
                states.append(connection.in_atomic_block)
                return super().request(method, url, **kwargs)

        self.link(session=Probe(routes()))
        self.assertEqual(states, [False, False, False])

    def test_two_businesses_same_number(self):
        other = _business()
        _reception(other)
        results = self.race(lambda: self.link(), lambda: self.link(business=other))
        self.assertEqual(results, ['linked', 'phone_number_unavailable'])
        self.assertEqual(AgentChannel.objects.filter(phone_number_id=PHONE, is_active=True).count(), 1)
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)
        channel = AgentChannel.objects.get(phone_number_id=PHONE)
        self.assertEqual(WhatsAppAuthorization.objects.get().owner_business_id, channel.business_id)

    def test_same_business_repeated_concurrently(self):
        results = self.race(lambda: self.link(), lambda: self.link())
        self.assertEqual(results, ['already_linked', 'linked'])
        self.assertEqual(AgentChannel.objects.filter(phone_number_id=PHONE).count(), 1)
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)

    def test_same_business_different_tokens_concurrently(self):
        results = self.race(lambda: self.link(), lambda: self.link(token=TOKEN_2))
        self.assertEqual(results, ['channel_credential_conflict', 'linked'])
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)
