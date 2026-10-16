"""
Deploy-time system check for `MP_TOKEN_ENCRYPTION_KEY` (see `crypto.py`).

Registered with `deploy=True`, so it only runs on `manage.py check --deploy`
— never on `manage.py test`, `migrate`, `runserver`, etc. Those must keep
working in dev/CI environments that have no key configured, and individual
tests already set a valid key explicitly via `override_settings` where they
need one. This check exists purely as an earlier, explicit signal for
deploy pipelines, ahead of migration 0002_encrypt_mp_tokens or the first
real OAuth callback — both of which already fail safely on their own via
`crypto._get_fernet()` if the key is missing or malformed.
"""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register

from .crypto import is_valid_fernet_key

E_MISSING = 'merchant_payments.E001'
E_INVALID = 'merchant_payments.E002'


@register(Tags.security, deploy=True)
def check_mp_token_encryption_key(app_configs, **kwargs):
    key = getattr(settings, 'MP_TOKEN_ENCRYPTION_KEY', None)

    if not key:
        return [
            Error(
                'MP_TOKEN_ENCRYPTION_KEY is not set.',
                hint=(
                    'Required before deploying merchant_payments migration 0002 or '
                    'accepting Mercado Pago OAuth connections. Generate one with: '
                    'python -c "from cryptography.fernet import Fernet; '
                    'print(Fernet.generate_key().decode())"'
                ),
                id=E_MISSING,
            )
        ]

    if not is_valid_fernet_key(key):
        return [
            Error(
                'MP_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.',
                hint=(
                    'Generate one with: python -c "from cryptography.fernet import Fernet; '
                    'print(Fernet.generate_key().decode())"'
                ),
                id=E_INVALID,
            )
        ]

    return []
