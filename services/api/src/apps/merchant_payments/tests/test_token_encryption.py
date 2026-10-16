"""
Slice 5B.3A — encryption-at-rest for MercadoPagoConnection.access_token /
refresh_token.

Covers: ciphertext is what's physically in the database, the ORM keeps
handing back plaintext, decrypt failures never fall back to treating a value
as plaintext, and nothing (serializers, exceptions, logs) leaks a token or
the encryption key.
"""
from __future__ import annotations

import logging

from django.db import connection
from django.test import TestCase, override_settings

from apps.business.models import Business
from apps.merchant_payments.crypto import (
    MPTokenEncryptionError,
    decrypt_token,
    encrypt_token,
)
from apps.merchant_payments.models import MercadoPagoConnection
from apps.merchant_payments.serializers import MercadoPagoConnectionStatusSerializer

TEST_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='
OTHER_KEY = 'Sxk9dQKfvKq3iN1n9m2FQ2b1J8y2yQY0Y0e3xnQmN9k='  # a different, valid Fernet key


def _business(name='Negocio') -> Business:
    return Business.objects.create(name=name, default_service='restaurante')


def _raw_columns(connection_id: int) -> tuple[str, str]:
    """Reads the physical, un-decrypted DB row via raw SQL — bypasses the ORM's
    from_db_value so we see exactly what's stored on disk."""
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT access_token, refresh_token FROM menu_mercadopagoconnection WHERE id = %s',
            [connection_id],
        )
        return cursor.fetchone()


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class TokenPersistedEncryptedTests(TestCase):
    def test_access_token_persisted_encrypted(self):
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='APP_USR-plaintext-access-token', status='connected',
        )
        raw_access, _ = _raw_columns(conn.id)
        self.assertNotEqual(raw_access, 'APP_USR-plaintext-access-token')
        self.assertNotIn('plaintext-access-token', raw_access)

    def test_refresh_token_persisted_encrypted(self):
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='tok', refresh_token='TG-plaintext-refresh-token',
            status='connected',
        )
        _, raw_refresh = _raw_columns(conn.id)
        self.assertNotEqual(raw_refresh, 'TG-plaintext-refresh-token')
        self.assertNotIn('plaintext-refresh-token', raw_refresh)

    def test_blank_refresh_token_also_not_stored_as_plaintext_empty_string(self):
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='tok', refresh_token='', status='connected',
        )
        _, raw_refresh = _raw_columns(conn.id)
        # Physically stored value must still be Fernet ciphertext, not ''.
        self.assertNotEqual(raw_refresh, '')

    def test_application_recovers_original_tokens(self):
        business = _business()
        MercadoPagoConnection.objects.create(
            business=business,
            access_token='APP_USR-original-access',
            refresh_token='TG-original-refresh',
            status='connected',
        )
        fetched = MercadoPagoConnection.objects.get(business=business)
        self.assertEqual(fetched.access_token, 'APP_USR-original-access')
        self.assertEqual(fetched.refresh_token, 'TG-original-refresh')

    def test_no_plaintext_copy_anywhere_in_the_row(self):
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business,
            access_token='SUPER-SECRET-ACCESS',
            refresh_token='SUPER-SECRET-REFRESH',
            status='connected',
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM menu_mercadopagoconnection WHERE id = %s", [conn.id],
            )
            columns = [c[0] for c in cursor.description]
            row = cursor.fetchone()
        row_text = ' '.join(str(v) for v in row)
        self.assertNotIn('SUPER-SECRET-ACCESS', row_text)
        self.assertNotIn('SUPER-SECRET-REFRESH', row_text)
        self.assertIn('access_token', columns)
        self.assertIn('refresh_token', columns)


class CryptoHelperTests(TestCase):
    @override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
    def test_encrypt_then_decrypt_roundtrips(self):
        ciphertext = encrypt_token('hello-token')
        self.assertNotEqual(ciphertext, 'hello-token')
        self.assertEqual(decrypt_token(ciphertext), 'hello-token')

    @override_settings(MP_TOKEN_ENCRYPTION_KEY='')
    def test_missing_key_fails_safely_on_encrypt(self):
        with self.assertRaises(MPTokenEncryptionError):
            encrypt_token('some-token')

    @override_settings(MP_TOKEN_ENCRYPTION_KEY='')
    def test_missing_key_fails_safely_on_decrypt(self):
        with self.assertRaises(MPTokenEncryptionError):
            decrypt_token('anything')

    def test_wrong_key_fails_safely_never_returns_plaintext(self):
        with override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY):
            ciphertext = encrypt_token('secret-value')
        with override_settings(MP_TOKEN_ENCRYPTION_KEY=OTHER_KEY):
            with self.assertRaises(MPTokenEncryptionError):
                decrypt_token(ciphertext)

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
    def test_corrupted_ciphertext_fails_safely(self):
        ciphertext = encrypt_token('secret-value')
        corrupted = ciphertext[:-4] + 'abcd'
        with self.assertRaises(MPTokenEncryptionError):
            decrypt_token(corrupted)

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
    def test_decrypt_failure_error_message_never_contains_ciphertext_or_key(self):
        ciphertext = encrypt_token('secret-value')
        corrupted = ciphertext[:-4] + 'abcd'
        try:
            decrypt_token(corrupted)
            self.fail('expected MPTokenEncryptionError')
        except MPTokenEncryptionError as exc:
            message = str(exc)
            self.assertNotIn(corrupted, message)
            self.assertNotIn(TEST_KEY, message)
            self.assertNotIn('secret-value', message)

    @override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
    def test_reading_row_with_wrong_key_raises_not_silently_returns_ciphertext(self):
        """A stored row can never be silently misread as plaintext: reading it
        back under the wrong key must raise, not return the raw ciphertext or
        garbage as if it were a usable token."""
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='TOKEN-UNDER-KEY-1', status='connected',
        )
        conn_id = conn.id

        with override_settings(MP_TOKEN_ENCRYPTION_KEY=OTHER_KEY):
            with self.assertRaises(MPTokenEncryptionError):
                MercadoPagoConnection.objects.get(id=conn_id)


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class SerializerNeverExposesTokensTests(TestCase):
    def test_status_serializer_has_no_token_fields(self):
        business = _business()
        conn = MercadoPagoConnection.objects.create(
            business=business, access_token='SUPER-SECRET-TOKEN', refresh_token='SUPER-SECRET-REFRESH',
            mp_user_id='42', status='connected',
        )
        data = MercadoPagoConnectionStatusSerializer({
            'connected': True,
            'status': conn.status,
            'mp_user_id': conn.mp_user_id,
            'updated_at': conn.updated_at,
        }).data
        rendered = str(data)
        self.assertNotIn('SUPER-SECRET-TOKEN', rendered)
        self.assertNotIn('SUPER-SECRET-REFRESH', rendered)
        self.assertNotIn('access_token', data)
        self.assertNotIn('refresh_token', data)


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class LoggingNeverContainsSecretsTests(TestCase):
    def test_decrypt_error_log_record_has_no_secret_material(self):
        ciphertext = encrypt_token('secret-value')
        corrupted = ciphertext[:-4] + 'abcd'

        with self.assertLogs('apps.merchant_payments.crypto', level='ERROR') as captured:
            with self.assertRaises(MPTokenEncryptionError):
                decrypt_token(corrupted)

        full_log = '\n'.join(captured.output)
        self.assertNotIn(corrupted, full_log)
        self.assertNotIn(TEST_KEY, full_log)
        self.assertNotIn('secret-value', full_log)
