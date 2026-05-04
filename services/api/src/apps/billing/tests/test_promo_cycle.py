"""
tests/test_promo_cycle.py
=========================
Tests for:
  - apps.billing.promo_cycle_service.handle_promo_cycle
  - apps.billing.tasks.reconcile_promotional_discounts

Coverage
--------
 1. Approved payment consumes one cycle.
 2. First payment transitions redemption PENDING → ACTIVE.
 3. Rejected/non-authorized payment does NOT consume a cycle (tested via
    webhook_processor._handle_authorized_payment integration).
 4. Duplicate authorized_payment_id does NOT consume a second cycle.
 5. When cycles_used reaches cycles_total the original price is restored on MP.
 6. If update_preapproval fails: webhook does not raise, price_restored=False.
 7. reconcile_promotional_discounts retries restore and marks price_restored=True.
 8. reconcile skips redemptions without a linked subscription.provider_sub_id.
 9. No PromoCodeRedemption → handle_promo_cycle is a no-op (webhook unaffected).
10. Third-cycle event when cycles_total=3 restores price; prior cycles don't.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import (
    MpCheckoutSession,
    Plan,
    PromoCode,
    PromoCodeRedemption,
    SubscriptionV2,
)
from apps.billing.promo_cycle_service import handle_promo_cycle
from apps.billing.tasks import reconcile_promotional_discounts
from apps.business.models import Business
from apps.business.models import Subscription as BizSubscription
from apps.accounts.models import Membership

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Test factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email='cycle@test.com'):
    return User.objects.create_user(email=email, username=email, password='testpass')


def _make_plan(code='gestion_pro', price=50000):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults=dict(
            name='Pro Plan',
            price=Decimal(str(price)),
            interval='monthly',
            currency='ARS',
            frequency=1,
            frequency_type='months',
            plan_status='active',
        ),
    )
    return plan


def _make_business(name='Cycle Biz', service='gestion'):
    biz = Business.objects.create(
        name=name, default_service=service, service_type=service, status='active',
    )
    BizSubscription.objects.create(business=biz, plan='start', status='active')
    return biz


def _make_subscription(business, plan, provider_sub_id=None, status=None):
    return SubscriptionV2.objects.create(
        business=business,
        service_type=business.default_service,
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        external_reference=f"SUB-{uuid.uuid4()}",
        provider_sub_id=provider_sub_id or f"PREAPPROVAL-{uuid.uuid4()}",
        status=status or SubscriptionV2.Status.ACTIVE,
        is_active=True,
    )


def _make_promo(code='SAVE50', plan_code='gestion_pro', **kwargs):
    defaults = dict(
        name='50% Off',
        discount_type=PromoCode.DiscountType.PERCENT,
        discount_value=Decimal('50'),
        duration_cycles=3,
        active=True,
        applies_to_plan_codes=[plan_code],
        applies_to_billing_periods=['monthly'],
    )
    defaults.update(kwargs)
    return PromoCode.objects.create(code=code, **defaults)


def _make_redemption(subscription, promo, cycles_total=3, status=None, **kwargs):
    """Creates a PromoCodeRedemption in the given status."""
    defaults = dict(
        business=subscription.business,
        user=None,
        subscription=subscription,
        original_amount=Decimal('50000.00'),
        discounted_amount=Decimal('25000.00'),
        cycles_total=cycles_total,
        cycles_used=0,
        status=status or PromoCodeRedemption.Status.PENDING,
        last_applied_payment_id='',
    )
    defaults.update(kwargs)
    return PromoCodeRedemption.objects.create(promo_code=promo, **defaults)


# ─────────────────────────────────────────────────────────────────────────────
# 1–6: handle_promo_cycle direct unit tests
# ─────────────────────────────────────────────────────────────────────────────

class HandlePromoCycleTest(TestCase):
    """Direct unit tests for handle_promo_cycle()."""

    def setUp(self):
        self.plan = _make_plan()
        self.biz = _make_business()
        self.sub = _make_subscription(self.biz, self.plan, provider_sub_id='PREAP-001')
        self.promo = _make_promo()
        self.redemption = _make_redemption(self.sub, self.promo, cycles_total=3)

    # ── Test 1: approved payment consumes exactly one cycle ──────────────────

    def test_approved_payment_consumes_one_cycle(self):
        handle_promo_cycle(self.sub, 'AUTHPAY-001')
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 1)

    # ── Test 2: first payment transitions PENDING → ACTIVE ───────────────────

    def test_first_payment_transitions_pending_to_active(self):
        self.assertEqual(self.redemption.status, PromoCodeRedemption.Status.PENDING)
        handle_promo_cycle(self.sub, 'AUTHPAY-001')
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, PromoCodeRedemption.Status.ACTIVE)

    # ── Test 4: duplicate payment_id does not consume a second cycle ─────────

    def test_duplicate_payment_id_does_not_consume_cycle(self):
        handle_promo_cycle(self.sub, 'AUTHPAY-DUP')
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 1)

        # Second call with the same ID — must be a no-op.
        handle_promo_cycle(self.sub, 'AUTHPAY-DUP')
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 1, "Duplicate payment must not re-count")

    # ── Test: second and third payments each consume one cycle ────────────────

    def test_three_payments_each_consume_one_cycle(self):
        handle_promo_cycle(self.sub, 'PAY-1')
        handle_promo_cycle(self.sub, 'PAY-2')
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 2)
        self.assertEqual(self.redemption.status, PromoCodeRedemption.Status.ACTIVE)

    # ── Test 5: final cycle restores price and marks COMPLETED ───────────────

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_last_cycle_restores_price_and_marks_completed(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.update_preapproval.return_value = {'status': 'authorized'}

        # 3 payments → 3rd one triggers restore
        handle_promo_cycle(self.sub, 'PAY-1')
        handle_promo_cycle(self.sub, 'PAY-2')
        handle_promo_cycle(self.sub, 'PAY-3')

        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 3)
        self.assertEqual(self.redemption.status, PromoCodeRedemption.Status.COMPLETED)
        self.assertTrue(self.redemption.price_restored)
        self.assertIsNotNone(self.redemption.price_restored_at)

        # MP must have been called with the original amount
        mock_mp.update_preapproval.assert_called_once_with(
            self.sub.provider_sub_id,
            {"auto_recurring": {"transaction_amount": float(self.redemption.original_amount)}},
        )

    # ── Test: first two payments don't restore price ──────────────────────────

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_intermediate_cycles_do_not_restore_price(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp

        handle_promo_cycle(self.sub, 'PAY-1')
        handle_promo_cycle(self.sub, 'PAY-2')

        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, PromoCodeRedemption.Status.ACTIVE)
        mock_mp.update_preapproval.assert_not_called()

    # ── Test 6: MP failure does not raise, leaves price_restored=False ────────

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_mp_failure_does_not_raise_and_leaves_price_restored_false(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.update_preapproval.side_effect = Exception("MP API timeout")

        # Should NOT raise even though MP fails
        handle_promo_cycle(self.sub, 'PAY-1')
        handle_promo_cycle(self.sub, 'PAY-2')
        handle_promo_cycle(self.sub, 'PAY-3')  # triggers restore attempt — must not raise

        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, PromoCodeRedemption.Status.COMPLETED)
        self.assertFalse(self.redemption.price_restored)
        self.assertIsNone(self.redemption.price_restored_at)

    # ── Test 9: no redemption → silent no-op ─────────────────────────────────

    def test_no_redemption_is_noop(self):
        # A subscription with no PromoCodeRedemption must not raise or error.
        biz2 = _make_business(name='NoBiz')
        sub2 = _make_subscription(biz2, self.plan, provider_sub_id='PREAP-002')

        # No redemption attached to sub2
        handle_promo_cycle(sub2, 'AUTHPAY-000')  # must be silent

        # Original redemption untouched
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 0)

    # ── Test: ACTIVE redemption also accepts cycle (already past 1st payment) ─

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_active_redemption_accepts_cycle(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp

        # Start with an already-ACTIVE redemption (cycles_used=1)
        self.redemption.status = PromoCodeRedemption.Status.ACTIVE
        self.redemption.cycles_used = 1
        self.redemption.last_applied_payment_id = 'PAY-1'
        self.redemption.save()

        handle_promo_cycle(self.sub, 'PAY-2')
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 2)
        self.assertEqual(self.redemption.status, PromoCodeRedemption.Status.ACTIVE)

    # ── Test: subscription without provider_sub_id — price_restored=False ─────

    def test_no_provider_sub_id_marks_price_restored_false(self):
        # Use a fresh business to avoid uq_subscriptionv2_active_per_service constraint.
        biz_no_mp = _make_business(name='NoMP Biz')
        sub_no_id = _make_subscription(biz_no_mp, self.plan, provider_sub_id=None)
        # Override the auto-generated ID with an empty string to simulate missing MP link
        SubscriptionV2.objects.filter(pk=sub_no_id.pk).update(provider_sub_id='')
        sub_no_id.refresh_from_db()

        redemption = _make_redemption(sub_no_id, self.promo, cycles_total=1)

        handle_promo_cycle(sub_no_id, 'PAY-X')
        redemption.refresh_from_db()
        self.assertEqual(redemption.status, PromoCodeRedemption.Status.COMPLETED)
        self.assertFalse(redemption.price_restored)


# ─────────────────────────────────────────────────────────────────────────────
# 3: Rejected payment does NOT consume cycle (integration with webhook processor)
# ─────────────────────────────────────────────────────────────────────────────

class RejectPaymentNoCycleTest(TestCase):
    """
    Verifies that handle_promo_cycle is NOT called when ap_status != 'authorized'.
    Tests via webhook_processor._handle_authorized_payment integration.
    """

    def setUp(self):
        self.plan = _make_plan()
        self.biz = _make_business(name='Reject Biz')
        self.sub = _make_subscription(self.biz, self.plan, provider_sub_id='PREAP-REJ')
        self.promo = _make_promo(code='REJ50')
        self.redemption = _make_redemption(self.sub, self.promo, cycles_total=3)

    @patch('apps.billing.promo_cycle_service.handle_promo_cycle')
    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_rejected_payment_does_not_call_promo_cycle(self, mock_mp_cls, mock_handle):
        from apps.billing.webhook_processor import _handle_authorized_payment
        from apps.billing.models import WebhookDelivery

        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.get_authorized_payment.return_value = {
            'id': 'AUTHPAY-REJ',
            'status': 'cancelled',
            'preapproval_id': self.sub.provider_sub_id,
            'payment_id': 'PAY-REJ',
            'transaction_amount': 50000,
            'currency_id': 'ARS',
        }

        delivery = WebhookDelivery.objects.create(
            provider='mercadopago',
            topic='subscription_authorized_payment',
            resource_id='AUTHPAY-REJ',
            action='payment.updated',
            payload_hash='abc',
            body_json={},
            processing_status=WebhookDelivery.ProcessingStatus.RECEIVED,
            received_at=timezone.now(),
        )

        _handle_authorized_payment('AUTHPAY-REJ', delivery)

        # handle_promo_cycle must NOT have been called
        mock_handle.assert_not_called()
        # Cycles untouched
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.cycles_used, 0)

    @patch('apps.billing.promo_cycle_service.handle_promo_cycle')
    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_authorized_payment_calls_promo_cycle(self, mock_mp_cls, mock_handle):
        from apps.billing.webhook_processor import _handle_authorized_payment
        from apps.billing.models import WebhookDelivery, BillingInvoiceEvent

        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.get_authorized_payment.return_value = {
            'id': 'AUTHPAY-OK',
            'status': 'authorized',
            'preapproval_id': self.sub.provider_sub_id,
            'payment_id': 'PAY-OK',
            'transaction_amount': 25000,
            'currency_id': 'ARS',
            'date_approved': '2026-04-26T10:00:00.000-03:00',
        }

        delivery = WebhookDelivery.objects.create(
            provider='mercadopago',
            topic='subscription_authorized_payment',
            resource_id='AUTHPAY-OK',
            action='payment.updated',
            payload_hash='def',
            body_json={},
            processing_status=WebhookDelivery.ProcessingStatus.RECEIVED,
            received_at=timezone.now(),
        )

        _handle_authorized_payment('AUTHPAY-OK', delivery)

        # handle_promo_cycle must have been called with the subscription and payment_id
        mock_handle.assert_called_once_with(self.sub, 'AUTHPAY-OK')


# ─────────────────────────────────────────────────────────────────────────────
# 7–8: reconcile_promotional_discounts task
# ─────────────────────────────────────────────────────────────────────────────

class ReconcilePromotionalDiscountsTest(TestCase):
    """Tests for the reconcile_promotional_discounts Celery task."""

    def setUp(self):
        self.plan = _make_plan(code='gestion_pro_r')
        self.biz = _make_business(name='Recon Biz')
        self.sub = _make_subscription(self.biz, self.plan, provider_sub_id='PREAP-RECON')
        self.promo = _make_promo(code='RECON50', plan_code='gestion_pro_r')

    def _make_completed_unrestored(self):
        return _make_redemption(
            self.sub, self.promo,
            cycles_total=3, cycles_used=3,
            status=PromoCodeRedemption.Status.COMPLETED,
            price_restored=False,
        )

    # ── Test 7: retries restore and marks price_restored=True ─────────────────

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_retries_restore_and_marks_price_restored_true(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.update_preapproval.return_value = {'status': 'authorized'}

        redemption = self._make_completed_unrestored()

        result = reconcile_promotional_discounts.apply().get()

        redemption.refresh_from_db()
        self.assertTrue(redemption.price_restored)
        self.assertIsNotNone(redemption.price_restored_at)
        self.assertEqual(result['restored'], 1)
        self.assertEqual(result['failed'], 0)

        mock_mp.update_preapproval.assert_called_once_with(
            self.sub.provider_sub_id,
            {"auto_recurring": {"transaction_amount": float(redemption.original_amount)}},
        )

    # ── Test: MP failure is counted as failed, not raised ─────────────────────

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_mp_failure_increments_failed_count_not_raises(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.update_preapproval.side_effect = Exception("MP error")

        self._make_completed_unrestored()

        result = reconcile_promotional_discounts.apply().get()

        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['restored'], 0)

    # ── Test 8: skip when no provider_sub_id ─────────────────────────────────

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_skip_redemption_without_provider_sub_id(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp

        # Use a fresh business to avoid uq_subscriptionv2_active_per_service constraint.
        biz_no_mp = _make_business(name='No MP Biz R')
        sub_no_mp = _make_subscription(biz_no_mp, self.plan, provider_sub_id=None)
        SubscriptionV2.objects.filter(pk=sub_no_mp.pk).update(provider_sub_id='')

        _make_redemption(
            sub_no_mp, self.promo,
            cycles_total=3, cycles_used=3,
            status=PromoCodeRedemption.Status.COMPLETED,
            price_restored=False,
        )

        result = reconcile_promotional_discounts.apply().get()

        mock_mp.update_preapproval.assert_not_called()
        self.assertEqual(result['skipped'], 1)

    # ── Test: reconcile also catches ACTIVE with cycles_used >= cycles_total ──

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_reconciles_active_exhausted_redemptions(self, mock_mp_cls):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.update_preapproval.return_value = {'status': 'authorized'}

        redemption = _make_redemption(
            self.sub, self.promo,
            cycles_total=3, cycles_used=3,
            status=PromoCodeRedemption.Status.ACTIVE,
            price_restored=False,
        )

        result = reconcile_promotional_discounts.apply().get()

        redemption.refresh_from_db()
        self.assertTrue(redemption.price_restored)
        self.assertEqual(result['restored'], 1)

    # ── Test: nothing to do returns all-zero counts ───────────────────────────

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_nothing_to_do_returns_zero_counts(self, mock_mp_cls):
        result = reconcile_promotional_discounts.apply().get()
        self.assertEqual(result, {'restored': 0, 'failed': 0, 'skipped': 0})
        mock_mp_cls.assert_not_called()
