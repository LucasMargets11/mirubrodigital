from __future__ import annotations

from django.db import migrations, models

from apps.merchant_payments.fields import EncryptedTextField

# ---------------------------------------------------------------------------
# Slice 5B.3A — encrypt MercadoPagoConnection.access_token / refresh_token at
# rest (Fernet, see apps.merchant_payments.crypto).
#
# Phased so that a historical plaintext row is never lost and there is never
# a moment with two persisted copies of a token:
#
#   1. Widen the columns from varchar(512) to text (still plaintext). Pure
#      schema change — Postgres casts varchar→text without touching data.
#      Needed headroom: Fernet ciphertext runs longer than its plaintext.
#   2. Re-save every existing row's access_token/refresh_token as its own
#      Fernet ciphertext, in place — no new column, no second copy.
#   3. Swap the field class to EncryptedTextField, wiring up transparent
#      encrypt-on-write / decrypt-on-read for all future ORM access. Same
#      underlying column type (text), so no further data movement.
#
# Requires MP_TOKEN_ENCRYPTION_KEY to be set — encrypt_token() raises
# MPTokenEncryptionError otherwise, which aborts the migration rather than
# silently persisting plaintext.
# ---------------------------------------------------------------------------


def encrypt_existing_tokens(apps, schema_editor):
    from apps.merchant_payments.crypto import encrypt_token

    MercadoPagoConnection = apps.get_model('merchant_payments', 'MercadoPagoConnection')
    # One row per Business (OneToOne) — small table, no chunking needed.
    for conn in MercadoPagoConnection.objects.all():
        # Always encrypt, including a blank refresh_token — from_db_value on
        # the encrypted field decrypts unconditionally on read, so a plain
        # '' left un-encrypted here would fail to decrypt later.
        conn.access_token = encrypt_token(conn.access_token)
        conn.refresh_token = encrypt_token(conn.refresh_token)
        conn.save(update_fields=['access_token', 'refresh_token'])


def decrypt_existing_tokens(apps, schema_editor):
    """Reverse of encrypt_existing_tokens, for `migrate` rollbacks.

    Intentional, not a bug: rolling back below this migration puts every
    access_token/refresh_token back in plaintext in the database — the same
    state as before Slice 5B.3A. That is correct behavior for a schema
    rollback, but it means "rollback" must never be treated as a safe
    response to a *secrets* incident (e.g. a suspected key compromise);
    doing so would deliberately re-expose the very credentials the
    migration was written to protect.
    """
    from apps.merchant_payments.crypto import decrypt_token

    MercadoPagoConnection = apps.get_model('merchant_payments', 'MercadoPagoConnection')
    for conn in MercadoPagoConnection.objects.all():
        conn.access_token = decrypt_token(conn.access_token)
        conn.refresh_token = decrypt_token(conn.refresh_token)
        conn.save(update_fields=['access_token', 'refresh_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('merchant_payments', '0001_move_mercadopago_connection'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mercadopagoconnection',
            name='access_token',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='mercadopagoconnection',
            name='refresh_token',
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(encrypt_existing_tokens, decrypt_existing_tokens),
        migrations.AlterField(
            model_name='mercadopagoconnection',
            name='access_token',
            field=EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name='mercadopagoconnection',
            name='refresh_token',
            field=EncryptedTextField(blank=True),
        ),
    ]
