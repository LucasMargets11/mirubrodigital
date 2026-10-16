"""
Django field wrapping merchant Mercado Pago token storage in Fernet
encryption (see `crypto.py`). Physically the database column holds
ciphertext; the ORM keeps handing callers plaintext, exactly like a plain
CharField/TextField — so `get_merchant_mp_client`, the OAuth callback, and
existing tests that read/write `conn.access_token` as a plain string need no
changes.
"""
from __future__ import annotations

from django.db import models

from .crypto import decrypt_token, encrypt_token


class EncryptedTextField(models.TextField):
    """A TextField whose value is Fernet-encrypted in the database.

    Encryption happens in `get_prep_value` (called on every INSERT/UPDATE),
    decryption in `from_db_value` (called on every row fetched from the
    database). In-memory attribute access is always plaintext.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        return encrypt_token(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_token(value)
