"""PROD-04B — Autorizaciones de WhatsApp (Meta) por conexión."""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import threading
import time
import uuid
from unittest import mock

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError, RestrictedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AccessAuditLog
from apps.billing.tests.test_reception_service_02b import _superadmin
from apps.business.models import Business
from apps.leads.crypto import AgentSecretEncryptionError
from apps.leads.models import AgentChannel, WhatsAppAuthorization
from apps.leads.services import whatsapp_authorizations as wa

from .factories import TEST_KEY, make_business, make_channel, make_instance

TOKEN = 'EAAG' + 'Tok3nDeMetaDePrueba' * 4
TOKEN_2 = 'EAAG' + 'OtroTokenDeMetaNuevo' * 4
WABA = '102030405060'


def staff(role='superadmin'):
    user = _superadmin()
    if role != 'superadmin':
        user.account_profile.internal_role = role
        user.account_profile.save(update_fields=['internal_role'])
    return user


@override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class _Base(TestCase):
    def setUp(self):
        self.actor = staff()
        self.instance = make_instance(f'wa-agent-{uuid.uuid4().hex[:8]}')
        self.a = make_business(f'wa-a-{uuid.uuid4().hex[:6]}')
        self.b = make_business(f'wa-b-{uuid.uuid4().hex[:6]}')
        self.channel_a = make_channel(self.instance, self.a, phone_number_id='1111111111')
        self.channel_b = make_channel(self.instance, self.b, phone_number_id='2222222222')

    def create(self, owner=None, **kwargs):
        kwargs.setdefault('token', TOKEN)
        kwargs.setdefault('actor', self.actor)
        if owner is None and not kwargs.get('platform'):
            owner = self.a
        return wa.create_whatsapp_authorization(owner_business=owner, **kwargs)

    def link(self, channel, authorization, waba=WABA, actor='default'):
        return wa.associate_channel(
            channel_id=channel.pk, authorization_id=authorization.pk, waba_id=waba,
            actor=self.actor if actor == 'default' else actor,
        )

    def assertCode(self, code, func, *args, **kwargs):
        with self.assertRaises(wa.WhatsAppAuthorizationError) as ctx:
            func(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)

    def audits(self):
        return list(AccessAuditLog.objects.filter(entity_type='whatsapp_authorization').order_by('created_at', 'id'))


class EncryptionTests(_Base):
    def test_token_is_encrypted_at_rest_and_round_trips(self):
        authorization = self.create()
        raw = WhatsAppAuthorization.objects.filter(pk=authorization.pk).values_list(
            'encrypted_access_token', flat=True,
        ).get()
        self.assertTrue(raw.startswith('gAAAAA'))
        self.assertNotIn(TOKEN, raw)
        self.link(self.channel_a, authorization)
        self.assertEqual(wa.resolve_channel_access_token(self.channel_a.pk), TOKEN)

    def test_db_rejects_plaintext(self):
        authorization = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            WhatsAppAuthorization.objects.filter(pk=authorization.pk).update(encrypted_access_token=TOKEN)

    def test_wrong_key_fails_without_plaintext_fallback(self):
        authorization = self.create()
        self.link(self.channel_a, authorization)
        with override_settings(AGENT_SECRET_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(AgentSecretEncryptionError) as ctx:
                wa.resolve_channel_access_token(self.channel_a.pk)
        self.assertNotIn(TOKEN, str(ctx.exception))

    def test_missing_key_creates_nothing(self):
        with override_settings(AGENT_SECRET_ENCRYPTION_KEY=''):
            with self.assertRaises(AgentSecretEncryptionError):
                self.create()
        self.assertFalse(WhatsAppAuthorization.objects.exists())
        self.assertEqual(self.audits(), [])

    def test_token_validation(self):
        for bad in ('corto', 'con espacio ' + 'x' * 30, 'x' * 5000, None, 123):
            with self.subTest(bad=bad):
                self.assertCode('invalid_token', self.create, token=bad)
        self.assertFalse(WhatsAppAuthorization.objects.exists())


class NoSecretsTests(_Base):
    def test_representations_and_audit_never_carry_the_token(self):
        authorization = self.create()
        self.link(self.channel_a, authorization)
        wa.rotate_whatsapp_authorization(authorization_id=authorization.pk, token=TOKEN_2, actor=self.actor)
        wa.revoke_whatsapp_authorization(authorization_id=authorization.pk, actor=self.actor)
        authorization.refresh_from_db()
        encrypted = authorization.encrypted_access_token
        texts = [str(authorization), repr(authorization), str(self.channel_a), repr(self.channel_a)]
        texts += [json.dumps(log.details) + log.entity_id for log in self.audits()]
        for text in texts:
            for secret in (TOKEN, TOKEN_2, encrypted, TOKEN[:12], TOKEN[-6:]):
                self.assertNotIn(secret, text)

    def test_audit_metadata(self):
        authorization = self.create()
        self.link(self.channel_a, authorization)
        created, linked = self.audits()
        self.assertEqual((created.action, created.business_id, created.actor), (
            'WHATSAPP_AUTHORIZATION_CREATED', self.a.pk, self.actor,
        ))
        self.assertEqual(created.details, {
            'scope': 'business', 'status': 'active', 'expires_at': None, 'channel_ids': [], 'business_ids': [],
        })
        self.assertEqual(linked.action, 'WHATSAPP_AUTHORIZATION_LINKED')
        self.assertEqual(linked.details['channel_ids'], [str(self.channel_a.pk)])
        self.assertEqual(linked.details['previous_authorization_id'], None)


class SharingAndIsolationTests(_Base):
    def test_shared_authorization_between_channels_of_its_business(self):
        authorization = self.create()
        second = make_channel(self.instance, self.a, phone_number_id='3333333333')
        self.link(self.channel_a, authorization)
        self.link(second, authorization, waba='909090')
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)
        self.assertEqual(
            [wa.resolve_channel_access_token(c.pk) for c in (self.channel_a, second)], [TOKEN, TOKEN],
        )
        second.refresh_from_db()
        self.assertEqual(second.waba_id, '909090')

    def test_platform_authorization_spans_businesses(self):
        platform = self.create(platform=True)
        self.link(self.channel_a, platform)
        self.link(self.channel_b, platform)
        self.assertEqual(wa.resolve_channel_access_token(self.channel_b.pk), TOKEN)
        self.assertEqual(self.audits()[0].business_id, None)
        self.assertEqual(self.audits()[0].details['scope'], 'platform')

    def test_owned_authorization_never_serves_another_business(self):
        authorization = self.create(owner=self.a)
        self.assertCode('whatsapp_authorization_owner_mismatch', self.link, self.channel_b, authorization)
        self.channel_b.whatsapp_authorization = authorization
        with self.assertRaises(ValidationError):
            self.channel_b.save()
        # Forzado por update(): la resolución igual falla cerrada
        AgentChannel.objects.filter(pk=self.channel_b.pk).update(whatsapp_authorization=authorization)
        self.assertCode('whatsapp_authorization_owner_mismatch', wa.resolve_channel_access_token, self.channel_b.pk)

    def test_platform_requires_explicit_flag(self):
        self.assertCode('invalid_owner', wa.create_whatsapp_authorization, token=TOKEN, actor=self.actor)
        self.assertCode(
            'invalid_owner', wa.create_whatsapp_authorization, token=TOKEN, actor=self.actor,
            owner_business=self.a, platform=True,
        )

    def test_owner_is_immutable(self):
        owned = self.create(owner=self.a)
        platform = self.create(platform=True)
        for authorization, new_owner in ((owned, self.b), (owned, None), (platform, self.a)):
            with self.subTest(authorization=str(authorization)):
                authorization.owner_business = new_owner
                with self.assertRaises(ValidationError):
                    authorization.save()

    def test_only_platform_admins_operate(self):
        authorization = self.create()
        for actor in (staff('support_agent'), staff('content_admin'), None):
            with self.subTest(actor=actor):
                self.assertCode('actor_not_authorized', self.create, actor=actor)
                self.assertCode('actor_not_authorized', self.link, self.channel_a, authorization, actor=actor)
        operations = staff('operations')
        self.link(self.channel_a, authorization, actor=operations)

    def test_association_rules(self):
        authorization = self.create()
        self.assertCode('invalid_waba_id', self.link, self.channel_a, authorization, waba='abc')
        AgentChannel.objects.filter(pk=self.channel_a.pk).update(is_active=False, deactivated_at=timezone.now())
        self.assertCode('channel_not_active', self.link, self.channel_a, authorization)
        self.assertCode(
            'whatsapp_authorization_not_found', wa.associate_channel, channel_id=self.channel_b.pk,
            authorization_id=uuid.uuid4(), waba_id=WABA, actor=self.actor,
        )

    def test_relinking_is_audited_and_noop_is_not(self):
        first = self.create()
        second = self.create()
        self.link(self.channel_a, first)
        self.link(self.channel_a, first)
        self.link(self.channel_a, second)
        linked = [log for log in self.audits() if log.action == 'WHATSAPP_AUTHORIZATION_LINKED']
        self.assertEqual(len(linked), 2)
        self.assertEqual(linked[1].details['previous_authorization_id'], str(first.pk))


class LegacyAndDeletionTests(_Base):
    def test_legacy_channels_are_untouched(self):
        self.channel_a.refresh_from_db()
        self.assertEqual((self.channel_a.waba_id, self.channel_a.whatsapp_authorization_id), ('', None))
        self.channel_a.save()  # sigue guardando sin datos de WhatsApp
        self.assertCode('whatsapp_authorization_missing', wa.resolve_channel_access_token, self.channel_a.pk)

    def test_waba_format_in_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AgentChannel.objects.filter(pk=self.channel_a.pk).update(waba_id='x1')

    def test_authorization_in_use_cannot_be_deleted(self):
        authorization = self.create()
        self.link(self.channel_a, authorization)
        with self.assertRaises((RestrictedError, ProtectedError)):
            authorization.delete()

    def test_deleting_owner_business_removes_its_channels_and_authorization(self):
        authorization = self.create()
        self.link(self.channel_a, authorization)
        Business.objects.filter(pk=self.a.pk).delete()
        self.assertFalse(WhatsAppAuthorization.objects.filter(pk=authorization.pk).exists())
        self.assertTrue(AgentChannel.objects.filter(pk=self.channel_b.pk).exists())


class RotationRevocationTests(_Base):
    def setUp(self):
        super().setUp()
        self.authorization = self.create()
        self.link(self.channel_a, self.authorization)

    def test_rotation_replaces_token_keeps_channels(self):
        wa.rotate_whatsapp_authorization(authorization_id=self.authorization.pk, token=TOKEN_2, actor=self.actor)
        self.assertEqual(wa.resolve_channel_access_token(self.channel_a.pk), TOKEN_2)
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)
        rotated = self.audits()[-1]
        self.assertEqual(rotated.action, 'WHATSAPP_AUTHORIZATION_ROTATED')
        self.assertEqual(rotated.details['meta_revocation'], 'not_performed')
        self.assertEqual(rotated.details['channel_ids'], [str(self.channel_a.pk)])

    def test_rotation_reactivates_invalid_or_expired(self):
        for status, expires in (('invalid', None), ('active', timezone.now() - dt.timedelta(days=1))):
            with self.subTest(status=status):
                WhatsAppAuthorization.objects.filter(pk=self.authorization.pk).update(status=status, expires_at=expires)
                future = timezone.now() + dt.timedelta(days=30)
                rotated = wa.rotate_whatsapp_authorization(
                    authorization_id=self.authorization.pk, token=TOKEN_2, actor=self.actor, expires_at=future,
                )
                self.assertEqual((rotated.status, rotated.expires_at), ('active', future))
                self.assertEqual(wa.resolve_channel_access_token(self.channel_a.pk), TOKEN_2)

    def test_revocation_is_local_idempotent_and_terminal(self):
        revoked = wa.revoke_whatsapp_authorization(authorization_id=self.authorization.pk, actor=self.actor)
        self.assertEqual(revoked.status, 'revoked')
        self.assertIsNotNone(revoked.revoked_at)
        self.assertCode('whatsapp_authorization_revoked', wa.resolve_channel_access_token, self.channel_a.pk)
        wa.revoke_whatsapp_authorization(authorization_id=self.authorization.pk, actor=self.actor)
        self.assertEqual([a.action for a in self.audits()].count('WHATSAPP_AUTHORIZATION_REVOKED'), 1)
        self.assertEqual(self.audits()[-1].details['meta_revocation'], 'not_performed')
        self.assertCode(
            'whatsapp_authorization_revoked', wa.rotate_whatsapp_authorization,
            authorization_id=self.authorization.pk, token=TOKEN_2, actor=self.actor,
        )
        second = make_channel(self.instance, self.a, phone_number_id='4444444444')
        self.assertCode('whatsapp_authorization_unusable', self.link, second, self.authorization)

    def test_revocation_cuts_every_shared_channel(self):
        second = make_channel(self.instance, self.a, phone_number_id='5555555555')
        self.link(second, self.authorization)
        wa.revoke_whatsapp_authorization(authorization_id=self.authorization.pk, actor=self.actor)
        for channel in (self.channel_a, second):
            self.assertCode('whatsapp_authorization_revoked', wa.resolve_channel_access_token, channel.pk)

    def test_expired_and_invalid_never_resolve(self):
        WhatsAppAuthorization.objects.filter(pk=self.authorization.pk).update(
            expires_at=timezone.now() - dt.timedelta(seconds=1),
        )
        self.assertCode('whatsapp_authorization_expired', wa.resolve_channel_access_token, self.channel_a.pk)
        second = make_channel(self.instance, self.a, phone_number_id='6666666666')
        self.assertCode('whatsapp_authorization_unusable', self.link, second, self.authorization)
        WhatsAppAuthorization.objects.filter(pk=self.authorization.pk).update(status='invalid', expires_at=None)
        self.assertCode('whatsapp_authorization_invalid', wa.resolve_channel_access_token, self.channel_a.pk)

    def test_inactive_channel_never_resolves(self):
        AgentChannel.objects.filter(pk=self.channel_a.pk).update(is_active=False, deactivated_at=timezone.now())
        self.assertCode('channel_not_active', wa.resolve_channel_access_token, self.channel_a.pk)

    def test_expiry_validation(self):
        past = timezone.now() - dt.timedelta(minutes=1)
        naive = dt.datetime(2030, 1, 1)
        for value in (past, naive):
            self.assertCode('invalid_expires_at', self.create, expires_at=value)
            self.assertCode(
                'invalid_expires_at', wa.rotate_whatsapp_authorization, authorization_id=self.authorization.pk,
                token=TOKEN_2, actor=self.actor, expires_at=value,
            )


class RollbackTests(_Base):
    def test_audit_failure_rolls_back_every_operation(self):
        authorization = self.create()
        boom = mock.patch.object(wa, 'record_platform_action', side_effect=RuntimeError('audit down'))
        with boom, self.assertRaises(RuntimeError):
            self.create()
        self.assertEqual(WhatsAppAuthorization.objects.count(), 1)
        with boom, self.assertRaises(RuntimeError):
            self.link(self.channel_a, authorization)
        self.channel_a.refresh_from_db()
        self.assertEqual((self.channel_a.whatsapp_authorization_id, self.channel_a.waba_id), (None, ''))
        self.link(self.channel_a, authorization)
        with boom, self.assertRaises(RuntimeError):
            wa.rotate_whatsapp_authorization(authorization_id=authorization.pk, token=TOKEN_2, actor=self.actor)
        self.assertEqual(wa.resolve_channel_access_token(self.channel_a.pk), TOKEN)
        with boom, self.assertRaises(RuntimeError):
            wa.revoke_whatsapp_authorization(authorization_id=authorization.pk, actor=self.actor)
        authorization.refresh_from_db()
        self.assertEqual(authorization.status, 'active')


@override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class CommandTests(_Base):
    def run_cmd(self, *args, env=None, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        environ = {k: v for k, v in os.environ.items() if k not in ('WHATSAPP_PROVISION_TOKEN', 'AGENT_PROVISION_SECRET')}
        environ.update(env or {})
        with mock.patch.dict(os.environ, environ, clear=True):
            with mock.patch('sys.stdin', stdin or io.StringIO('')):
                call_command('provision_agent', *args, stdout=out, stderr=err)
        return out.getvalue() + err.getvalue()

    def test_create_link_rotate_revoke_without_echoing_tokens(self):
        common = ['--external-id', self.instance.external_id, '--business-id', str(self.a.pk),
                  '--phone-number-id', '1111111111', '--waba-id', WABA, '--actor-email', self.actor.email]
        out = self.run_cmd(*common, '--create-whatsapp-authorization', '--whatsapp-token-stdin',
                           stdin=io.StringIO(TOKEN + '\n'))
        authorization = WhatsAppAuthorization.objects.get()
        self.assertEqual(authorization.owner_business_id, self.a.pk)
        self.assertEqual(wa.resolve_channel_access_token(self.channel_a.pk), TOKEN)
        out += self.run_cmd('--rotate-whatsapp-authorization', str(authorization.pk), '--actor-email',
                            self.actor.email, env={'WHATSAPP_PROVISION_TOKEN': TOKEN_2})
        self.assertIn('sigue válido ante Meta', out)
        self.assertEqual(wa.resolve_channel_access_token(self.channel_a.pk), TOKEN_2)
        out += self.run_cmd('--revoke-whatsapp-authorization', str(authorization.pk), '--actor-email',
                            self.actor.email)
        authorization.refresh_from_db()
        self.assertEqual(authorization.status, 'revoked')
        for secret in (TOKEN, TOKEN_2, authorization.encrypted_access_token):
            self.assertNotIn(secret, out)

    def test_link_existing_and_platform_flag(self):
        common = ['--external-id', self.instance.external_id, '--waba-id', WABA, '--actor-email', self.actor.email]
        self.run_cmd(*common, '--business-id', str(self.a.pk), '--phone-number-id', '1111111111',
                     '--create-whatsapp-authorization', '--platform-whatsapp-authorization',
                     env={'WHATSAPP_PROVISION_TOKEN': TOKEN})
        platform = WhatsAppAuthorization.objects.get()
        self.assertIsNone(platform.owner_business_id)
        self.run_cmd(*common, '--business-id', str(self.b.pk), '--phone-number-id', '2222222222',
                     '--whatsapp-authorization-id', str(platform.pk))
        self.assertEqual(wa.resolve_channel_access_token(self.channel_b.pk), TOKEN)

    def test_command_guards(self):
        common = ['--external-id', self.instance.external_id, '--business-id', str(self.a.pk),
                  '--phone-number-id', '1111111111', '--waba-id', WABA]
        cases = [
            (common + ['--create-whatsapp-authorization'], 'actor-email'),
            (common + ['--create-whatsapp-authorization', '--actor-email', 'nadie@x.test'], 'único usuario'),
            (common + ['--create-whatsapp-authorization', '--actor-email', self.actor.email], 'WHATSAPP_PROVISION_TOKEN'),
            (common[:-2] + ['--create-whatsapp-authorization', '--actor-email', self.actor.email], 'waba-id'),
            (common + ['--platform-whatsapp-authorization', '--actor-email', self.actor.email], 'solo con'),
            (['--rotate-whatsapp-authorization', 'no-uuid', '--actor-email', self.actor.email,
              ], 'WHATSAPP_PROVISION_TOKEN'),
            (['--revoke-whatsapp-authorization', 'no-uuid', '--actor-email', self.actor.email], 'inválido'),
        ]
        for args, message in cases:
            with self.subTest(args=args), self.assertRaises(CommandError) as ctx:
                self.run_cmd(*args)
            self.assertIn(message, str(ctx.exception))
        self.assertFalse(WhatsAppAuthorization.objects.exists())
        # Un fallo al asociar revierte también la creación del token
        with self.assertRaises(CommandError):
            self.run_cmd(*common[:-1], 'abc', '--create-whatsapp-authorization', '--actor-email',
                         self.actor.email, env={'WHATSAPP_PROVISION_TOKEN': TOKEN})
        self.assertFalse(WhatsAppAuthorization.objects.exists())

    def test_token_is_never_a_cli_argument(self):
        with self.assertRaises(CommandError):
            self.run_cmd('--revoke-whatsapp-authorization', str(uuid.uuid4()), '--whatsapp-token', TOKEN)


@override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class ConcurrencyTests(TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        self.actor = staff()
        instance = make_instance(f'wa-agent-{uuid.uuid4().hex[:8]}')
        self.business = make_business(f'wa-c-{uuid.uuid4().hex[:6]}')
        self.channel = make_channel(instance, self.business, phone_number_id='7777777777')
        self.authorization = wa.create_whatsapp_authorization(
            token=TOKEN, actor=self.actor, owner_business=self.business,
        )
        wa.associate_channel(
            channel_id=self.channel.pk, authorization_id=self.authorization.pk, waba_id=WABA, actor=self.actor,
        )

    def race(self, *calls):
        results, barrier = [], threading.Barrier(len(calls))
        real = wa.record_platform_action

        def slow(**kwargs):
            time.sleep(0.3)  # retiene el lock: el otro espera
            return real(**kwargs)

        def worker(call):
            try:
                barrier.wait()
                call()
                results.append('ok')
            except wa.WhatsAppAuthorizationError as error:
                results.append(error.code)
            finally:
                connection.close()

        with mock.patch.object(wa, 'record_platform_action', side_effect=slow):
            threads = [threading.Thread(target=worker, args=(call,)) for call in calls]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
        return sorted(results)

    def test_rotate_vs_revoke_ends_consistent(self):
        results = self.race(
            lambda: wa.rotate_whatsapp_authorization(authorization_id=self.authorization.pk, token=TOKEN_2, actor=self.actor),
            lambda: wa.revoke_whatsapp_authorization(authorization_id=self.authorization.pk, actor=self.actor),
        )
        self.assertIn(results, (['ok', 'ok'], ['ok', 'whatsapp_authorization_revoked']))
        self.authorization.refresh_from_db()
        self.assertEqual(self.authorization.status, 'revoked')
        with self.assertRaises(wa.WhatsAppAuthorizationError):
            wa.resolve_channel_access_token(self.channel.pk)

    def test_two_rotations_serialize(self):
        tokens = (TOKEN_2, 'EAAG' + 'TercerTokenDePrueba1' * 4)
        results = self.race(*[
            (lambda t=t: wa.rotate_whatsapp_authorization(authorization_id=self.authorization.pk, token=t, actor=self.actor))
            for t in tokens
        ])
        self.assertEqual(results, ['ok', 'ok'])
        self.assertIn(wa.resolve_channel_access_token(self.channel.pk), tokens)
        self.assertEqual(
            AccessAuditLog.objects.filter(action='WHATSAPP_AUTHORIZATION_ROTATED').count(), 2,
        )

    def test_link_vs_revoke_never_leaves_a_resolvable_revoked_link(self):
        other = make_channel(self.channel.agent_instance, self.business, phone_number_id='8888888888')
        results = self.race(
            lambda: wa.revoke_whatsapp_authorization(authorization_id=self.authorization.pk, actor=self.actor),
            lambda: wa.associate_channel(
                channel_id=other.pk, authorization_id=self.authorization.pk, waba_id=WABA, actor=self.actor,
            ),
        )
        self.assertIn(results, (['ok', 'ok'], ['ok', 'whatsapp_authorization_unusable']))
        for channel in (self.channel, other):
            with self.assertRaises(wa.WhatsAppAuthorizationError):
                wa.resolve_channel_access_token(channel.pk)
