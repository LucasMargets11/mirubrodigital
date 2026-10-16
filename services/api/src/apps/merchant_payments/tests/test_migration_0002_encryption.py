"""
merchant_payments/tests/test_migration_0002_encryption.py — data preservation
across Slice 5B.3A's encryption-at-rest migration
(`0002_encrypt_mp_tokens`), run against real PostgreSQL the same way
`test_migration_preservation.py` exercises the Slice 5A move.

Reproduces an installation that existed BEFORE Slice 5B.3A (tokens still
plaintext, `merchant_payments` migrated only up to `0001`):

  1. downgrade migration state to `merchant_payments.0001` (tokens are still
     plain CharField columns) and create a MercadoPagoConnection row through
     that historical model, bound to a real Business, with plaintext tokens;
  2. re-apply `0002_encrypt_mp_tokens` (and everything after);
  3. re-read the row through the CURRENT model and assert the original
     access_token/refresh_token values are recovered unchanged;
  4. read the physical column values via raw SQL and assert neither is the
     plaintext that was written in step 1 — the migration must not leave a
     plaintext copy behind anywhere.
"""
from __future__ import annotations

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase, override_settings

from apps.business.models import Business
from apps.merchant_payments.crypto import MPTokenEncryptionError
from apps.merchant_payments.models import MercadoPagoConnection

TEST_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='

PRE_5B3A_TARGETS = [
    ('merchant_payments', '0001_move_mercadopago_connection'),
]
MIGRATION_0002 = ('merchant_payments', '0002_encrypt_mp_tokens')


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class EncryptionMigrationPreservationTest(TestCase):
    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.latest_targets = self.executor.loader.graph.leaf_nodes()

    def test_historical_plaintext_row_survives_encryption_migration(self):
        # ── 1. Reproduce the pre-Slice-5B.3A state (plaintext tokens) ──────
        self.executor.migrate(PRE_5B3A_TARGETS)

        old_state = self.executor.loader.project_state(PRE_5B3A_TARGETS)
        HistoricalMercadoPagoConnection = old_state.apps.get_model(
            'merchant_payments', 'MercadoPagoConnection',
        )

        business = Business.objects.create(
            name='Pre-5B3A Business', default_service='gestion', status='active',
        )

        historical_conn = HistoricalMercadoPagoConnection.objects.create(
            business_id=business.id,
            access_token='ACCESS-TOKEN-PLAINTEXT-0001',
            refresh_token='REFRESH-TOKEN-PLAINTEXT-0001',
            mp_user_id='MP-USER-11223344',
            scope='read write offline_access',
            status='connected',
        )
        original_pk = historical_conn.pk

        # Sanity: at this point the column really does hold plaintext.
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT access_token, refresh_token FROM menu_mercadopagoconnection WHERE id = %s',
                [original_pk],
            )
            raw_access_before, raw_refresh_before = cursor.fetchone()
        self.assertEqual(raw_access_before, 'ACCESS-TOKEN-PLAINTEXT-0001')
        self.assertEqual(raw_refresh_before, 'REFRESH-TOKEN-PLAINTEXT-0001')

        # Flush the FK-check trigger Postgres queued for the INSERT above —
        # otherwise the migration's real ALTER TABLE, in the same
        # transaction, fails with "cannot ALTER TABLE ... because it has
        # pending trigger events".
        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

        # ── 2. Apply the encryption migration (+ everything after it) ─────
        forward_executor = MigrationExecutor(connection)
        forward_executor.migrate(self.latest_targets)

        # ── 3. Re-read through the CURRENT model: original values recovered
        rows = MercadoPagoConnection.objects.filter(business_id=business.id)
        self.assertEqual(rows.count(), 1, 'expected exactly one preserved row')

        current_conn = rows.get()
        self.assertEqual(current_conn.pk, original_pk)
        self.assertEqual(current_conn.access_token, 'ACCESS-TOKEN-PLAINTEXT-0001')
        self.assertEqual(current_conn.refresh_token, 'REFRESH-TOKEN-PLAINTEXT-0001')
        self.assertEqual(current_conn.mp_user_id, 'MP-USER-11223344')
        self.assertEqual(current_conn.status, 'connected')

        # ── 4. No plaintext copy survives physically in the row ────────────
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT access_token, refresh_token FROM menu_mercadopagoconnection WHERE id = %s',
                [original_pk],
            )
            raw_access_after, raw_refresh_after = cursor.fetchone()
        self.assertNotEqual(raw_access_after, 'ACCESS-TOKEN-PLAINTEXT-0001')
        self.assertNotEqual(raw_refresh_after, 'REFRESH-TOKEN-PLAINTEXT-0001')

        # Still exactly one row, same table — no shadow column/table left over.
        self.assertEqual(
            MercadoPagoConnection.objects.filter(business_id=business.id).count(), 1,
        )


@override_settings(MP_TOKEN_ENCRYPTION_KEY='')
class EncryptionMigrationMissingKeyRollbackTest(TestCase):
    """A missing/invalid key at migration time must abort `0002` atomically:
    no row half-converted to ciphertext, no partial commit of the widened
    columns, and the migration left unrecorded — recoverable by re-running
    `migrate` once a valid key is configured."""

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.latest_targets = self.executor.loader.graph.leaf_nodes()

    def test_missing_key_aborts_migration_without_partial_state(self):
        # ── 1. Reproduce the pre-Slice-5B.3A state (plaintext tokens) ──────
        self.executor.migrate(PRE_5B3A_TARGETS)

        old_state = self.executor.loader.project_state(PRE_5B3A_TARGETS)
        HistoricalMercadoPagoConnection = old_state.apps.get_model(
            'merchant_payments', 'MercadoPagoConnection',
        )

        business = Business.objects.create(
            name='Missing-Key Business', default_service='gestion', status='active',
        )
        historical_conn = HistoricalMercadoPagoConnection.objects.create(
            business_id=business.id,
            access_token='ACCESS-TOKEN-PLAINTEXT-NOKEY',
            refresh_token='REFRESH-TOKEN-PLAINTEXT-NOKEY',
            mp_user_id='MP-USER-55667788',
            scope='read write offline_access',
            status='connected',
        )
        original_pk = historical_conn.pk

        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

        # ── 2. Attempt the encryption migration with NO key configured ────
        # (class-level @override_settings(MP_TOKEN_ENCRYPTION_KEY='')) — the
        # RunPython step must raise, aborting the whole atomic migration.
        forward_executor = MigrationExecutor(connection)
        with self.assertRaises(MPTokenEncryptionError):
            forward_executor.migrate(self.latest_targets)

        # ── 3. Migration 0002 must NOT be recorded as applied ──────────────
        recorder = MigrationRecorder(connection)
        self.assertNotIn(MIGRATION_0002, recorder.applied_migrations())

        # ── 4. The row must still hold its original plaintext, unchanged —
        # no partial ciphertext, no widened-but-unconverted column left by a
        # half-applied migration.
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT access_token, refresh_token FROM menu_mercadopagoconnection WHERE id = %s',
                [original_pk],
            )
            raw_access, raw_refresh = cursor.fetchone()
        self.assertEqual(raw_access, 'ACCESS-TOKEN-PLAINTEXT-NOKEY')
        self.assertEqual(raw_refresh, 'REFRESH-TOKEN-PLAINTEXT-NOKEY')

        # ── 5. Recoverable: re-running `migrate` with a valid key now set
        # completes cleanly, proving the aborted attempt left no residue
        # that would block a correct retry.
        with override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_KEY):
            retry_executor = MigrationExecutor(connection)
            retry_executor.migrate(self.latest_targets)

            self.assertIn(
                MIGRATION_0002, MigrationRecorder(connection).applied_migrations(),
            )

            current_conn = MercadoPagoConnection.objects.get(business_id=business.id)
            self.assertEqual(current_conn.pk, original_pk)
            self.assertEqual(current_conn.access_token, 'ACCESS-TOKEN-PLAINTEXT-NOKEY')
            self.assertEqual(current_conn.refresh_token, 'REFRESH-TOKEN-PLAINTEXT-NOKEY')
