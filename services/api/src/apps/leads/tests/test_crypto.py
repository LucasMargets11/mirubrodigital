"""Cifrado de secretos de AgentCredential (AGENT 02A)."""
from __future__ import annotations

from cryptography.fernet import Fernet
from django.test import SimpleTestCase, override_settings

from apps.leads.crypto import AgentSecretEncryptionError, decrypt_agent_secret, encrypt_agent_secret

from .factories import SECRET, TEST_KEY


@override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class AgentSecretCryptoTests(SimpleTestCase):
    def test_roundtrip(self):
        self.assertEqual(decrypt_agent_secret(encrypt_agent_secret(SECRET)), SECRET)

    def test_ciphertext_is_not_plaintext(self):
        ciphertext = encrypt_agent_secret(SECRET)
        self.assertNotEqual(ciphertext, SECRET)
        self.assertNotIn(SECRET, ciphertext)
        # Fernet no es determinista: dos cifrados del mismo secreto difieren.
        self.assertNotEqual(ciphertext, encrypt_agent_secret(SECRET))

    def test_empty_plaintext_rejected(self):
        with self.assertRaises(AgentSecretEncryptionError):
            encrypt_agent_secret('')

    def test_invalid_ciphertext_raises(self):
        with self.assertRaises(AgentSecretEncryptionError):
            decrypt_agent_secret('not-a-fernet-token')

    def test_no_plaintext_fallback(self):
        # Un valor guardado en claro nunca se devuelve como si fuera el secreto.
        with self.assertRaises(AgentSecretEncryptionError) as ctx:
            decrypt_agent_secret(SECRET)
        self.assertNotIn(SECRET, str(ctx.exception))

    def test_wrong_key_raises_without_leaking(self):
        ciphertext = encrypt_agent_secret(SECRET)
        with override_settings(AGENT_SECRET_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(AgentSecretEncryptionError) as ctx:
                decrypt_agent_secret(ciphertext)
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertNotIn(ciphertext, str(ctx.exception))

    def test_does_not_use_mp_token_key(self):
        with override_settings(AGENT_SECRET_ENCRYPTION_KEY='', MP_TOKEN_ENCRYPTION_KEY=TEST_KEY):
            with self.assertRaises(AgentSecretEncryptionError):
                encrypt_agent_secret(SECRET)


class AgentSecretCryptoMissingKeyTests(SimpleTestCase):
    @override_settings(AGENT_SECRET_ENCRYPTION_KEY='')
    def test_missing_key_fails_closed_on_encrypt(self):
        with self.assertRaises(AgentSecretEncryptionError):
            encrypt_agent_secret(SECRET)

    @override_settings(AGENT_SECRET_ENCRYPTION_KEY='')
    def test_missing_key_fails_closed_on_decrypt(self):
        with override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY):
            ciphertext = encrypt_agent_secret(SECRET)
        with self.assertRaises(AgentSecretEncryptionError):
            decrypt_agent_secret(ciphertext)

    @override_settings(AGENT_SECRET_ENCRYPTION_KEY='not-a-valid-key')
    def test_invalid_key_fails_closed(self):
        with self.assertRaises(AgentSecretEncryptionError) as ctx:
            encrypt_agent_secret(SECRET)
        self.assertNotIn('not-a-valid-key', str(ctx.exception))
