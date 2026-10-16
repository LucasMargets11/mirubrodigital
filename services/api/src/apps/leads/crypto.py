"""
Encryption-at-rest for the shared secrets of `AgentCredential` (AGENT 02A).

Same pattern as `apps.merchant_payments.crypto` (Fernet with a dedicated,
env-provided key) but with its OWN key, `AGENT_SECRET_ENCRYPTION_KEY`, so
the agent-integration secrets rotate independently of the Mercado Pago
tokens (`MP_TOKEN_ENCRYPTION_KEY`) and MFA secrets (`MFA_ENCRYPTION_KEY`).

The secret is encrypted — not hashed — because HMAC request signing needs
the raw secret on both ends.

Never falls back to plaintext: a missing/invalid key or a decrypt failure
raises `AgentSecretEncryptionError`. Messages never include plaintext,
ciphertext or key material (they may reach logs).
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

SETTING_NAME = 'AGENT_SECRET_ENCRYPTION_KEY'


class AgentSecretEncryptionError(RuntimeError):
    """Raised when an agent credential secret cannot be encrypted or
    decrypted. Never include ciphertext, plaintext, or key material in the
    message — this may reach logs."""


def _get_fernet() -> Fernet:
    key = getattr(settings, SETTING_NAME, None)
    if not key:
        raise AgentSecretEncryptionError(
            f'{SETTING_NAME} is not set. Generate one with: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise AgentSecretEncryptionError(f'{SETTING_NAME} is not a valid Fernet key.') from exc


def encrypt_agent_secret(plaintext: str) -> str:
    """Encrypt an agent HMAC secret for database storage."""
    if not isinstance(plaintext, str) or not plaintext:
        raise AgentSecretEncryptionError('Agent secret must be a non-empty string.')
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_agent_secret(ciphertext: str) -> str:
    """Decrypt an agent HMAC secret read from the database.

    Never treats the stored value as plaintext: a key mismatch or corrupted
    ciphertext fails loudly.
    """
    if not isinstance(ciphertext, str) or not ciphertext:
        raise AgentSecretEncryptionError('Stored agent secret is empty or malformed.')
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        logger.error('Failed to decrypt agent credential secret — key mismatch or corruption')
        raise AgentSecretEncryptionError('Failed to decrypt stored agent secret.') from exc
