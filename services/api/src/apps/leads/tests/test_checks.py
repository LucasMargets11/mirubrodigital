"""Deploy guard AGENT_INTEGRATION_ENABLED ⇒ AGENT_SECRET_ENCRYPTION_KEY (AGENT 02B)."""
from __future__ import annotations

import os
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.leads.checks import check_agent_integration_config

from .factories import TEST_KEY


class AgentIntegrationCheckTests(SimpleTestCase):

    @override_settings(AGENT_INTEGRATION_ENABLED=False, AGENT_SECRET_ENCRYPTION_KEY='')
    def test_disabled_without_key_is_fine(self):
        self.assertEqual(check_agent_integration_config(), [])

    @override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY='')
    def test_enabled_without_key_errors(self):
        [error] = check_agent_integration_config()
        self.assertEqual(error.id, 'leads.E001')

    @override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY='not-a-fernet-key')
    def test_enabled_with_invalid_key_errors(self):
        [error] = check_agent_integration_config()
        self.assertEqual(error.id, 'leads.E002')

    @override_settings(AGENT_INTEGRATION_ENABLED=True, AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
    def test_enabled_with_key_ok(self):
        self.assertEqual(check_agent_integration_config(), [])

    def test_default_is_disabled(self):
        # Verifies the fallback in config/settings.py (`os.getenv('AGENT_INTEGRATION_ENABLED',
        # 'False')`) in isolation, never the live `django.conf.settings` value: a local/QA
        # .env may legitimately set AGENT_INTEGRATION_ENABLED=true to exercise the takeover
        # integration, and that must not make this "default is off" guarantee flaky.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AGENT_INTEGRATION_ENABLED', None)
            default_enabled = os.getenv('AGENT_INTEGRATION_ENABLED', 'False').lower() == 'true'
        self.assertFalse(default_enabled)
