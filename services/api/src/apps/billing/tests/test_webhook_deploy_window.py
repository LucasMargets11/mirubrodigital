"""
Slice 5B.4.2 — deploy window between the pre-5B.4 code, migration 0023 and
the new webhook lifecycle code (real PostgreSQL).

Scenarios:
  - migration graph: billing.0023 → menu.0014 has no cycle;
  - an OLD writer (pre-5B.4 WebhookDelivery model) running after 0023;
  - Mercado Pago's retry of that notification reaching the NEW code;
  - a hint-less `payment` row that does exist after 0023;
  - NEW code (API + sweeper) running before 0023 is applied.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing import webhook_lifecycle
from apps.billing.models import WebhookDelivery
from apps.billing.tasks import retry_failed_webhooks
from apps.billing.tests.test_webhook_delivery_lifecycle import (
    BASE_SETTINGS, BUSINESS_TOKEN, GLOBAL_TOKEN, WEBHOOK_URL,
    _approved, _body, _sdk_factory,
)
from apps.billing.webhook_lifecycle import eligible_for_retry_qs, retry_due_deliveries
from apps.business.models import Business
from apps.menu.models import TipTransaction
from apps.merchant_payments.models import MercadoPagoConnection

S = WebhookDelivery.ProcessingStatus

BILLING_0022 = ('billing', '0022_add_appointments_service_type')
BILLING_0023 = ('billing', '0023_webhookdelivery_retry_lifecycle')
MENU_0014 = ('menu', '0014_remove_mercadopagoconnection_state_only')


class MigrationGraphTests(SimpleTestCase):

    def test_billing_0023_depends_on_menu_0014_without_cycle(self):
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        graph.ensure_not_cyclic()
        self.assertIn(MENU_0014, graph.node_map[BILLING_0023].parents)
        # menu.0014 (and everything it needs) must not need billing.0023.
        self.assertNotIn(BILLING_0023, graph.forwards_plan(MENU_0014))


class _MigratingTestCase(TransactionTestCase):
    available_apps = list(settings.INSTALLED_APPS)

    def _migrate(self, targets):
        MigrationExecutor(connection).migrate(targets)

    def _old_delivery_model(self):
        """WebhookDelivery exactly as the pre-5B.4 code declares it (state at 0022)."""
        state = MigrationExecutor(connection).loader.project_state([BILLING_0022, MENU_0014])
        return state.apps.get_model('billing', 'WebhookDelivery')

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        webhook_lifecycle._lifecycle_schema_ready = False
        super().tearDown()


@override_settings(**BASE_SETTINGS)
class OldWriterAfter0023Tests(_MigratingTestCase):
    """Migration 0023 applied, pre-5B.4 code still receiving webhooks."""

    def _old_writer_create(self, **extra):
        # Same INSERT the pre-5B.4 receive_webhook() issues: only the columns
        # its model knows (no attempts/flow/ref/error_category/...).
        OldDelivery = self._old_delivery_model()
        self.assertNotIn('flow', [f.name for f in OldDelivery._meta.get_fields()])
        data = dict(
            provider='mercadopago', topic='payment', resource_id='pay-window',
            action='payment.updated', x_request_id='req-window-1', x_signature='',
            signature_valid=True, payload_hash='h' * 64,
            headers_json={'x-request-id': 'req-window-1'},
            body_json=_body('pay-window'), processing_status='received',
            received_at=timezone.now(),
        )
        data.update(extra)
        with transaction.atomic():
            return OldDelivery.objects.create(**data)

    def test_new_not_null_columns_have_no_database_default(self):
        with connection.cursor() as cur:
            cur.execute(
                "SELECT column_name, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_name = %s AND column_name IN ('attempts','flow','ref','error_category')",
                [WebhookDelivery._meta.db_table],
            )
            rows = {name: (nullable, default) for name, nullable, default in cur.fetchall()}
        self.assertEqual(rows, {c: ('NO', None) for c in ('attempts', 'flow', 'ref', 'error_category')})

    def test_old_writer_cannot_persist_a_delivery_after_0023(self):
        with self.assertRaises(IntegrityError) as cm:
            self._old_writer_create()
        self.assertIn('not-null', str(cm.exception))
        # No hint-less RECEIVED payment row exists for anyone to lose.
        self.assertFalse(WebhookDelivery.objects.exists())
        self.assertFalse(eligible_for_retry_qs().exists())

    @patch('mercadopago.SDK')
    def test_mp_retry_of_the_rejected_notification_is_processed_by_new_code(self, mock_sdk):
        # The old view has no try/except around receive_webhook() and runs it
        # before any business logic: the IntegrityError is an HTTP 500, no
        # effect was applied, and Mercado Pago re-sends the notification
        # (same notification_url, so flow/ref are present again).
        business = Business.objects.create(name='Resto', default_service='restaurante')
        MercadoPagoConnection.objects.create(business=business, access_token=BUSINESS_TOKEN,
                                             status='connected')
        tip = TipTransaction.objects.create(business=business, amount='100.00', currency='ARS',
                                            status='pending', external_reference='TIP-WINDOW000001')
        with self.assertRaises(IntegrityError):
            self._old_writer_create()
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'pending')

        calls = []
        mock_sdk.side_effect = _sdk_factory(
            forbidden={GLOBAL_TOKEN}, calls=calls,
            responses={BUSINESS_TOKEN: _approved('TIP-WINDOW000001')},
        )
        resp = APIClient().post(
            f'{WEBHOOK_URL}?flow=tip&ref=TIP-WINDOW000001', _body('pay-window'),
            format='json', HTTP_X_REQUEST_ID='req-window-1',
        )

        self.assertEqual(resp.status_code, 200)
        d = WebhookDelivery.objects.get()
        self.assertEqual((d.processing_status, d.flow, d.ref, d.attempts),
                         (S.PROCESSED, 'tip', 'TIP-WINDOW000001', 1))
        tip.refresh_from_db()
        self.assertEqual(tip.status, 'approved')
        self.assertEqual(calls, [BUSINESS_TOKEN])

    @patch('mercadopago.SDK')
    def test_hintless_payment_row_after_0023_is_classified_never_fetched(self, mock_sdk):
        # The only writer able to insert after 0023 is the new one; a payment
        # row without flow/ref therefore means the notification_url carried no
        # hint (pre-5B.2.2 preference) — the 5B.2 rule applies: fail closed,
        # no fetch, no mutation, IGNORED with an explicit category (never
        # PROCESSED, never retried in a loop).
        stale = timezone.now() - timedelta(hours=1)
        d = WebhookDelivery.objects.create(
            topic='payment', resource_id='pay-hintless', signature_valid=True,
            x_request_id='req-hintless', payload_hash='h' * 64,
            body_json=_body('pay-hintless'), received_at=stale,
        )
        self.assertEqual((d.flow, d.ref, d.processing_status), ('', '', S.RECEIVED))

        counts = retry_due_deliveries()

        self.assertEqual(counts['picked'], 1)
        mock_sdk.assert_not_called()
        d.refresh_from_db()
        self.assertEqual((d.processing_status, d.error_category), (S.IGNORED, 'legacy_unresolved'))
        self.assertEqual(retry_due_deliveries()['picked'], 0)


@override_settings(**BASE_SETTINGS)
class NewCodeBefore0023Tests(_MigratingTestCase):
    """New API/worker/Beat code running while the schema is still at 0022."""

    def setUp(self):
        super().setUp()
        self._migrate([BILLING_0022, MENU_0014])
        webhook_lifecycle._lifecycle_schema_ready = False
        OldDelivery = self._old_delivery_model()
        stale = timezone.now() - timedelta(hours=1)
        self.old_row = OldDelivery.objects.create(
            topic='payment', resource_id='pay-pre', processing_status='received',
            signature_valid=True, x_request_id='req-pre', payload_hash='h' * 64,
            body_json=_body('pay-pre'), received_at=stale,
        )

    def test_sweeper_task_does_nothing_until_0023_is_applied(self):
        result = retry_failed_webhooks.apply().get()

        self.assertEqual(result, {'picked': 0, 'skipped': 0, 'schema_not_ready': True})
        OldDelivery = self._old_delivery_model()
        self.assertEqual(OldDelivery.objects.get(pk=self.old_row.pk).processing_status, 'received')

        # Once 0023 runs, its data migration classifies the row (5B.4.1) and
        # the sweeper starts working — without restarting the worker.
        self._migrate([BILLING_0023])
        d = WebhookDelivery.objects.get(pk=self.old_row.pk)
        self.assertEqual((d.processing_status, d.error_category), (S.DEAD_LETTER, 'legacy_unverified'))
        self.assertNotIn('schema_not_ready', retry_failed_webhooks.apply().get())

    def test_new_api_before_0023_answers_503_and_persists_nothing(self):
        resp = APIClient().post(f'{WEBHOOK_URL}?flow=tip&ref=TIP-PRE', _body('pay-new'),
                                format='json', HTTP_X_REQUEST_ID='req-new')

        self.assertEqual(resp.status_code, 503)   # Mercado Pago retries later.
        OldDelivery = self._old_delivery_model()
        self.assertEqual(list(OldDelivery.objects.values_list('pk', flat=True)), [self.old_row.pk])
