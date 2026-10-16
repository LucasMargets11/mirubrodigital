"""Management command `provision_agent` (AGENT 02A)."""
from __future__ import annotations

import io
import os
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.leads.management.commands.provision_agent import SECRET_ENV
from apps.leads.models import AgentChannel, AgentCredential, AgentInstance

from .factories import SECRET, TEST_KEY, make_business, make_channel, make_instance


@override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class ProvisionAgentCommandTests(TestCase):
    def setUp(self):
        self.business = make_business('prov-a')

    def run_cmd(self, *args, env=None, stdin=None):
        out = io.StringIO()
        environ = {k: v for k, v in os.environ.items() if k != SECRET_ENV}
        environ.update(env or {})
        with mock.patch.dict(os.environ, environ, clear=True):
            if stdin is not None:
                with mock.patch('sys.stdin', stdin):
                    call_command('provision_agent', *args, stdout=out)
            else:
                call_command('provision_agent', *args, stdout=out)
        return out.getvalue()

    def full_args(self, **overrides):
        args = {
            '--external-id': 'dental-agent-dev', '--name': 'Dental dev', '--key-id': 'k1',
            '--business-id': str(self.business.pk), '--phone-number-id': '1234567890',
        }
        args.update(overrides)
        return [item for pair in args.items() if pair[1] is not None for item in pair]

    def test_full_provisioning_from_env(self):
        output = self.run_cmd(*self.full_args(), env={SECRET_ENV: SECRET})
        instance = AgentInstance.objects.get(external_id='dental-agent-dev')
        credential = AgentCredential.objects.get(key_id='k1')
        channel = AgentChannel.objects.get(phone_number_id='1234567890')
        self.assertEqual(instance.name, 'Dental dev')
        self.assertEqual(credential.agent_instance, instance)
        self.assertEqual(credential.get_secret(), SECRET)
        self.assertNotEqual(credential.encrypted_secret, SECRET)
        self.assertEqual((channel.business, channel.agent_instance, channel.is_active), (self.business, instance, True))
        self.assertNotIn(SECRET, output)
        self.assertNotIn(credential.encrypted_secret, output)
        self.assertIn(str(instance.pk), output)
        self.assertIn(str(channel.pk), output)

    def test_secret_from_stdin(self):
        self.run_cmd(
            '--external-id', 'dental-agent-dev', '--key-id', 'k1', '--secret-stdin', stdin=io.StringIO(SECRET + '\n'),
        )
        self.assertEqual(AgentCredential.objects.get(key_id='k1').get_secret(), SECRET)

    def test_idempotent_rerun(self):
        self.run_cmd(*self.full_args(), env={SECRET_ENV: SECRET})
        ciphertext = AgentCredential.objects.get(key_id='k1').encrypted_secret
        # Re-ejecutar (incluso sin secreto) no duplica ni re-cifra.
        self.run_cmd(*self.full_args())
        self.assertEqual(AgentInstance.objects.count(), 1)
        self.assertEqual(AgentCredential.objects.count(), 1)
        self.assertEqual(AgentChannel.objects.count(), 1)
        self.assertEqual(AgentCredential.objects.get(key_id='k1').encrypted_secret, ciphertext)

    def test_missing_secret_fails_without_persisting(self):
        with self.assertRaises(CommandError):
            self.run_cmd(*self.full_args())
        self.assertFalse(AgentInstance.objects.exists())
        self.assertFalse(AgentCredential.objects.exists())

    def test_short_secret_rejected(self):
        with self.assertRaises(CommandError) as ctx:
            self.run_cmd(*self.full_args(), env={SECRET_ENV: 'short'})
        self.assertNotIn('short', str(ctx.exception).replace('caracteres', ''))
        self.assertFalse(AgentCredential.objects.exists())

    def test_missing_encryption_key_fails_closed(self):
        with override_settings(AGENT_SECRET_ENCRYPTION_KEY=''):
            with self.assertRaises(CommandError):
                self.run_cmd(*self.full_args(), env={SECRET_ENV: SECRET})
        self.assertFalse(AgentInstance.objects.exists())
        self.assertFalse(AgentCredential.objects.exists())

    def test_unknown_business_rejected(self):
        with self.assertRaises(CommandError):
            self.run_cmd(*self.full_args(**{'--business-id': '999999', '--key-id': None}))
        self.assertFalse(AgentInstance.objects.exists())

    def test_active_channel_elsewhere_rejected(self):
        other_business = make_business('prov-b')
        make_channel(make_instance('other-agent'), other_business, '1234567890')
        with self.assertRaises(CommandError):
            self.run_cmd(*self.full_args(**{'--key-id': None}))
        self.assertEqual(AgentChannel.objects.count(), 1)
        self.assertFalse(AgentInstance.objects.filter(external_id='dental-agent-dev').exists())

    def test_key_id_of_other_instance_rejected(self):
        self.run_cmd('--external-id', 'other-agent', '--key-id', 'k1', env={SECRET_ENV: SECRET})
        with self.assertRaises(CommandError):
            self.run_cmd('--external-id', 'dental-agent-dev', '--key-id', 'k1', env={SECRET_ENV: SECRET})

    def test_invalid_identifiers_rejected(self):
        with self.assertRaises(CommandError):
            self.run_cmd('--external-id', 'Bad_ID')
        with self.assertRaises(CommandError):
            self.run_cmd(*self.full_args(**{'--phone-number-id': '+54911', '--key-id': None}))
        self.assertFalse(AgentInstance.objects.exists())

    def test_business_and_phone_go_together(self):
        with self.assertRaises(CommandError):
            self.run_cmd('--external-id', 'dental-agent-dev', '--business-id', str(self.business.pk))

    def test_secret_is_not_a_cli_argument(self):
        with self.assertRaises(CommandError):
            call_command('provision_agent', '--external-id', 'dental-agent-dev', '--secret', SECRET)
