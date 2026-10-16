"""
Encryption-at-rest for merchant-side Mercado Pago OAuth tokens.

Mirrors the pattern already established in `apps.accounts.admin_mfa` for TOTP
secrets: Fernet (AES-128-CBC + HMAC, via the `cryptography` package already a
project dependency) with a dedicated, env-provided key. A dedicated
`MP_TOKEN_ENCRYPTION_KEY` — rather than reusing `MFA_ENCRYPTION_KEY` — keeps
the two secret domains independently rotatable: a compromised or rotated MFA
key must never affect stored payment credentials, and vice versa.

Never falls back to plaintext: a missing key or a decrypt failure raises.
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


class MPTokenEncryptionError(RuntimeError):
    """Raised when a merchant Mercado Pago token cannot be encrypted or
    decrypted. Never include ciphertext, plaintext, or key material in the
    message — this may reach logs."""


def is_valid_fernet_key(key: str | bytes) -> bool:
    """Whether `key` can be used to construct a `Fernet` instance.

    Shared with the `merchant_payments.E002` deploy check so both places
    agree on what counts as "valid" without duplicating the try/except.
    """
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError):
        return False
    return True


def _get_fernet() -> Fernet:
    key = getattr(settings, 'MP_TOKEN_ENCRYPTION_KEY', None)
    if not key:
        raise MPTokenEncryptionError(
            'MP_TOKEN_ENCRYPTION_KEY is not set. Generate one with: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise MPTokenEncryptionError('MP_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.') from exc


def encrypt_token(plaintext: str) -> str:
    """Encrypt a Mercado Pago token for database storage."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a Mercado Pago token read from the database.

    Never falls back to treating the value as plaintext: a key mismatch or
    corrupted ciphertext must fail loudly, not silently return garbage or
    the raw stored value.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        logger.error("Failed to decrypt Mercado Pago token — key mismatch or corruption")
        raise MPTokenEncryptionError('Failed to decrypt stored Mercado Pago token.') from exc
