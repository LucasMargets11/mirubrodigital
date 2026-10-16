"""
merchant_payments/tests/test_encryption_key_check.py — the
`merchant_payments.E00x` deploy check for `MP_TOKEN_ENCRYPTION_KEY`
(see `checks.py`).

Registered with `deploy=True`, so it must:
  - stay silent on ordinary commands (`manage.py check`, and by extension
    `migrate` / `test` / `runserver`) even when the key is missing or
    malformed — dev/CI environments that don't touch Mercado Pago OAuth
    must keep working, and existing tests set a valid key explicitly via
    `override_settings` only where they need one;
  - fire only under `manage.py check --deploy`, catching an absent, empty,
    or malformed key before it reaches production;
  - never echo the key value in its error message.
"""
from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import TestCase, override_settings

from apps.merchant_payments.checks import (
    E_INVALID,
    E_MISSING,
    check_mp_token_encryption_key,
)

VALID_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='
MALFORMED_KEY = 'not-a-valid-fernet-key'


class CheckFunctionTests(TestCase):
    @override_settings(MP_TOKEN_ENCRYPTION_KEY=VALID_KEY)
    def test_valid_key_passes(self):
        self.assertEqual(check_mp_token_encryption_key(None), [])

    @override_settings(MP_TOKEN_ENCRYPTION_KEY='')
    def test_empty_key_fails(self):
        # `MP_TOKEN_ENCRYPTION_KEY` is always defined via
        # `os.getenv('MP_TOKEN_ENCRYPTION_KEY', '')` (settings.py) — an
        # absent env var and an empty one both resolve to `''` here, so this
        # single case covers both "ausente" and "vacío".
        errors = check_mp_token_encryption_key(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, E_MISSING)

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=MALFORMED_KEY)
    def test_malformed_key_fails(self):
        errors = check_mp_token_encryption_key(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, E_INVALID)

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=MALFORMED_KEY)
    def test_malformed_key_error_never_echoes_the_key(self):
        errors = check_mp_token_encryption_key(None)
        rendered = str(errors[0])
        self.assertNotIn(MALFORMED_KEY, rendered)


class DeployFlagGatingTests(TestCase):
    """`manage.py check` (no flag) must never fail on this check; only
    `manage.py check --deploy` may.

    Scoped to `tags=['security']` (the tag this check is registered under)
    so these tests aren't coupled to unrelated pre-existing deploy-check
    noise elsewhere in the project (e.g. drf_spectacular's own untagged
    `deploy=True` schema-generation check) — out of scope here and not
    something this slice touches.
    """

    @override_settings(MP_TOKEN_ENCRYPTION_KEY='')
    def test_plain_check_ignores_missing_key(self):
        call_command('check', tags=['security'])  # must not raise

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=MALFORMED_KEY)
    def test_plain_check_ignores_malformed_key(self):
        call_command('check', tags=['security'])  # must not raise

    @override_settings(MP_TOKEN_ENCRYPTION_KEY='')
    def test_deploy_check_fails_on_missing_key(self):
        with self.assertRaises(SystemCheckError):
            call_command('check', deploy=True, tags=['security'])

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=MALFORMED_KEY)
    def test_deploy_check_fails_on_malformed_key(self):
        with self.assertRaises(SystemCheckError):
            call_command('check', deploy=True, tags=['security'])

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=VALID_KEY)
    def test_deploy_check_passes_on_valid_key(self):
        call_command('check', deploy=True, tags=['security'])  # must not raise
