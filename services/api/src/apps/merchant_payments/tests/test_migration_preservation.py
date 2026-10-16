"""
merchant_payments/tests/test_migration_preservation.py — data preservation
across the Slice 5A state-only move of MercadoPagoConnection.

Reproduces an installation that existed BEFORE Slice 5A:

  1. downgrades migration state so `menu.MercadoPagoConnection` still exists
     (menu at 0013, merchant_payments unapplied);
  2. creates a MercadoPagoConnection row through that historical model,
     bound to a real Business row, and records its PK/values;
  3. re-applies `merchant_payments.0001_move_mercadopago_connection` and
     `menu.0014_remove_mercadopagoconnection_state_only` (and everything
     after);
  4. re-reads the row through the current
     `apps.merchant_payments.models.MercadoPagoConnection` and asserts the
     PK, Business FK, and field values survived untouched, that exactly one
     row exists, and that no second table was created for the model.

Both migrations are `SeparateDatabaseAndState` with empty
`database_operations` — they only ever move Django's migration STATE, never
touch the database. That means the backward/forward replay below never
issues real DDL, only DML against Django's own `django_migrations`
bookkeeping table — safe to run inside `TestCase`'s per-test transaction,
which is rolled back at the end regardless of outcome, restoring both the
test data and the migration bookkeeping in one step (no manual teardown
needed, and no dependency on `flush`, which this schema's unrelated legacy
`treasury_expensetemplate` orphan table makes unsafe to run standalone).
"""
from __future__ import annotations

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, override_settings

from apps.business.models import Business
from apps.merchant_payments.models import MercadoPagoConnection

PRE_SLICE_5A_TARGETS = [
    ('menu', '0013_menucategory_product_category'),
    ('merchant_payments', None),
]

# `self.latest_targets` below also replays Slice 5B.3A's
# `0002_encrypt_mp_tokens`, which requires a valid key (see
# apps.merchant_payments.crypto) to re-save the row created in this test.
TEST_ENCRYPTION_KEY = '7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I='


@override_settings(MP_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class MercadoPagoConnectionMigrationPreservationTest(TestCase):
    """Simulates the Slice 5A move on an installation with pre-existing data."""

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.latest_targets = self.executor.loader.graph.leaf_nodes()

    def test_data_survives_the_state_only_move(self):
        # ── 1. Reproduce the pre-Slice-5A state ────────────────────────────
        self.executor.migrate(PRE_SLICE_5A_TARGETS)

        old_state = self.executor.loader.project_state(
            [('menu', '0013_menucategory_product_category')],
        )
        HistoricalMercadoPagoConnection = old_state.apps.get_model(
            'menu', 'MercadoPagoConnection',
        )

        business = Business.objects.create(
            name='Pre-Slice5A Business', default_service='gestion', status='active',
        )

        historical_conn = HistoricalMercadoPagoConnection.objects.create(
            business_id=business.id,
            access_token='ACCESS-TOKEN-LEGACY-0001',
            refresh_token='REFRESH-TOKEN-LEGACY-0001',
            mp_user_id='MP-USER-99887766',
            scope='read write offline_access',
            status='connected',
        )
        original_pk = historical_conn.pk
        original_created_at = historical_conn.created_at

        self.assertEqual(
            HistoricalMercadoPagoConnection.objects.filter(business_id=business.id).count(),
            1,
        )

        # Flush the FK-check trigger Postgres queued for the INSERT above —
        # otherwise a later real ALTER TABLE on this same table, in the same
        # transaction (e.g. Slice 5B.3A's 0002_encrypt_mp_tokens), fails with
        # "cannot ALTER TABLE ... because it has pending trigger events".
        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

        # ── 2. Apply the Slice 5A move (+ everything after it) ────────────
        forward_executor = MigrationExecutor(connection)
        forward_executor.migrate(self.latest_targets)

        # ── 3. Re-read through the CURRENT model and assert preservation ──
        rows = MercadoPagoConnection.objects.filter(business_id=business.id)
        self.assertEqual(rows.count(), 1, 'expected exactly one preserved row')

        current_conn = rows.get()
        self.assertEqual(current_conn.pk, original_pk)
        self.assertEqual(current_conn.business_id, business.id)
        self.assertEqual(current_conn.access_token, 'ACCESS-TOKEN-LEGACY-0001')
        self.assertEqual(current_conn.refresh_token, 'REFRESH-TOKEN-LEGACY-0001')
        self.assertEqual(current_conn.mp_user_id, 'MP-USER-99887766')
        self.assertEqual(current_conn.scope, 'read write offline_access')
        self.assertEqual(current_conn.status, 'connected')
        self.assertEqual(current_conn.created_at, original_created_at)

        # business.mp_connection (OneToOne reverse accessor) still resolves
        business.refresh_from_db()
        self.assertEqual(business.mp_connection.pk, original_pk)

        # No second table was created for the moved model — it still lives
        # in the original `menu_mercadopagoconnection` table.
        self.assertEqual(MercadoPagoConnection._meta.db_table, 'menu_mercadopagoconnection')
        table_names = set(connection.introspection.table_names())
        self.assertIn('menu_mercadopagoconnection', table_names)
        self.assertNotIn('merchant_payments_mercadopagoconnection', table_names)
