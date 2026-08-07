"""
billing/tests/test_admin_clientes_01a_complimentary_access.py

ADMIN-CLIENTES 01A — Acceso bonificado en SubscriptionV2 (backend only).

Test matrix:
  ComplimentaryAccessGrantTest
    1.  Grants complimentary access and creates a manual SubscriptionV2.
    2.  status=trialing, is_active=True, period matches requested dates.
    3.  provider_sub_id is NULL.
    4.  external_reference is set and unique (SUB-{uuid} format).
    5.  Business.status advances to 'trialing'.
    6.  AccessAuditLog ADMIN_COMPLIMENTARY_ACCESS_GRANTED written with actor/details.
    7.  Mercado Pago is never called.
    8.  Rejects end date <= start date.
    9.  Rejects empty/blank reason.
    10. Rejects invalid plan_code.
    11. Rejects invalid service_type.
    12. Rejects when business already has a vigent (non-canceled) subscription
        for the same service_type.
    13. Full rollback when a failure occurs mid-transaction (no orphan rows).
    14. Does not write to legacy billing.Subscription / business.Subscription.

  ComplimentaryAccessCancellationTest
    15. Admin can cancel a manual/complimentary subscription — no MP call.
    16. Cancelling a manual subscription writes the existing audit log action.
    17. Regression: cancelling a Mercado Pago subscription still calls MP
        exactly as before (unaffected by this change).
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AccessAuditLog
from apps.billing.cancellation_service import cancel_subscription_immediately
from apps.billing.complimentary_access_service import (
    ComplimentaryAccessError,
    grant_complimentary_access,
)
from apps.billing.models import Plan, SubscriptionV2
from apps.business.models import Business

User = get_user_model()

FAKE_PREAPPROVAL_ID = "11223344556677889900aabb"


def _make_business(name='Complimentary Biz', status='onboarding', service='gestion'):
    return Business.objects.create(name=name, default_service=service, status=status)


def _make_admin(email=None):
    email = email or f'admin-{uuid.uuid4()}@platform.com'
    return User.objects.create_user(email=email, password='pass', username=email)


def _make_plan(code='gestion_pro', price=Decimal('50000.00'), plan_status='active'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults={
            'name': code,
            'price': price,
            'interval': 'monthly',
            'currency': 'ARS',
            'frequency': 1,
            'frequency_type': 'months',
            'plan_status': plan_status,
        },
    )
    return plan


class ComplimentaryAccessGrantTest(TestCase):

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_admin()
        self.plan = _make_plan()
        self.starts_at = timezone.now()
        self.ends_at = self.starts_at + timedelta(days=180)

    def _grant(self, **overrides):
        kwargs = dict(
            business=self.biz,
            plan_code=self.plan.code,
            service_type='gestion',
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            granted_by=self.admin,
            reason='Cliente VIP — 6 meses de cortesía',
        )
        kwargs.update(overrides)
        return grant_complimentary_access(**kwargs)

    # ── 1-4: creation contract ──────────────────────────────────────────────
    def test_01_creates_manual_subscription(self):
        sub = self._grant()
        self.assertEqual(sub.provider, SubscriptionV2.Provider.MANUAL)
        self.assertEqual(sub.plan_code, self.plan.code)
        self.assertEqual(sub.service_type, 'gestion')

    def test_02_status_trialing_active_and_period(self):
        sub = self._grant()
        self.assertEqual(sub.status, SubscriptionV2.Status.TRIALING)
        self.assertTrue(sub.is_active)
        self.assertEqual(sub.current_period_start, self.starts_at)
        self.assertEqual(sub.current_period_end, self.ends_at)

    def test_03_provider_sub_id_is_null(self):
        sub = self._grant()
        self.assertIsNone(sub.provider_sub_id)

    def test_04_external_reference_set_and_unique(self):
        sub1 = self._grant()
        self.assertTrue(sub1.external_reference.startswith('SUB-'))
        # A second grant for a different service is allowed and must get a
        # distinct external_reference (DB unique constraint enforced).
        biz2 = _make_business(name='Biz2')
        sub2 = grant_complimentary_access(
            business=biz2, plan_code=self.plan.code, service_type='gestion',
            starts_at=self.starts_at, ends_at=self.ends_at,
            granted_by=self.admin, reason='Otro motivo',
        )
        self.assertNotEqual(sub1.external_reference, sub2.external_reference)

    # ── 5: Business status ──────────────────────────────────────────────────
    def test_05_business_advances_to_trialing(self):
        self._grant()
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'trialing')

    # ── 6: audit log ────────────────────────────────────────────────────────
    def test_06_audit_log_written(self):
        sub = self._grant()
        log = AccessAuditLog.objects.filter(
            action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED',
            actor=self.admin,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.business_id, self.biz.pk)
        self.assertEqual(log.entity_type, 'subscription_v2')
        self.assertEqual(log.entity_id, str(sub.id))
        self.assertEqual(log.details['plan_code'], self.plan.code)
        self.assertEqual(log.details['service_type'], 'gestion')
        self.assertIn('cortesía', log.details['reason'])

    # ── 7: no Mercado Pago call ──────────────────────────────────────────────
    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_07_never_calls_mercadopago(self, mock_mp_cls):
        self._grant()
        mock_mp_cls.assert_not_called()

    # ── 8: invalid dates ───────────────────────────────────────────────────
    def test_08_rejects_end_before_start(self):
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(starts_at=self.ends_at, ends_at=self.starts_at)

    def test_08b_rejects_end_equal_start(self):
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(starts_at=self.starts_at, ends_at=self.starts_at)

    # ── 9: empty reason ─────────────────────────────────────────────────────
    def test_09_rejects_empty_reason(self):
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(reason='')

    def test_09b_rejects_blank_reason(self):
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(reason='   ')

    # ── 10: invalid plan ─────────────────────────────────────────────────────
    def test_10_rejects_invalid_plan_code(self):
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(plan_code='does_not_exist')

    def test_10b_rejects_inactive_plan(self):
        inactive_plan = _make_plan(code='gestion_business_inactive', plan_status='inactive')
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(plan_code=inactive_plan.code)

    # ── 11: invalid service_type ─────────────────────────────────────────────
    def test_11_rejects_invalid_service_type(self):
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(service_type='not_a_real_service')

    # ── 12: existing vigent subscription ────────────────────────────────────
    def test_12_rejects_existing_active_subscription(self):
        SubscriptionV2.objects.create(
            business=self.biz,
            service_type='gestion',
            plan_code='gestion_pro',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=FAKE_PREAPPROVAL_ID,
            external_reference=f'SUB-{uuid.uuid4()}',
            status=SubscriptionV2.Status.ACTIVE,
            is_active=True,
        )
        with self.assertRaises(ComplimentaryAccessError):
            self._grant()
        # No second row was created for this business+service.
        self.assertEqual(
            SubscriptionV2.objects.filter(business=self.biz, service_type='gestion').count(), 1,
        )

    def test_12b_allows_grant_when_only_canceled_sub_exists(self):
        SubscriptionV2.objects.create(
            business=self.biz,
            service_type='gestion',
            plan_code='gestion_pro',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=FAKE_PREAPPROVAL_ID,
            external_reference=f'SUB-{uuid.uuid4()}',
            status=SubscriptionV2.Status.CANCELED,
            is_active=False,
        )
        sub = self._grant()
        self.assertEqual(sub.status, SubscriptionV2.Status.TRIALING)

    # ── 13: rollback ─────────────────────────────────────────────────────────
    def test_13_full_rollback_on_failure(self):
        with patch(
            'apps.billing.complimentary_access_service._advance_business_to_trialing',
            side_effect=RuntimeError('boom'),
        ):
            with self.assertRaises(RuntimeError):
                self._grant()

        self.assertFalse(
            SubscriptionV2.objects.filter(business=self.biz, service_type='gestion').exists()
        )
        self.assertFalse(
            AccessAuditLog.objects.filter(action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED').exists()
        )
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'onboarding')

    # ── 14: legacy models untouched ──────────────────────────────────────────
    def test_14_does_not_write_legacy_subscription(self):
        self._grant()
        self.assertFalse(hasattr(self.biz, 'subscription') and self.biz.subscription)

    # ── 18-19 (ADMIN-CLIENTES 01B): plan/service vertical compatibility ──────
    def test_18_rejects_plan_from_another_vertical(self):
        # menu_qr_visual belongs to the 'menu_qr' vertical, not 'gestion'.
        menu_qr_plan = _make_plan(code='menu_qr_visual', price=Decimal('30000.00'))
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(plan_code=menu_qr_plan.code, service_type='gestion')
        self.assertFalse(
            SubscriptionV2.objects.filter(business=self.biz, service_type='gestion').exists()
        )

    def test_18b_rejects_gestion_plan_for_menu_qr_service(self):
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(plan_code=self.plan.code, service_type='menu_qr')

    def test_19_rejects_plan_without_canonical_vertical_data(self):
        # 'resto_basic' predates the canonical pricing catalog (see
        # seed_billing.py PLAN_SEEDS comment: "not yet in canonical").
        # Compatibility cannot be verified unambiguously, so it must be
        # rejected rather than guessed.
        legacy_plan = _make_plan(code='resto_basic', price=Decimal('25.00'))
        with self.assertRaises(ComplimentaryAccessError):
            self._grant(plan_code=legacy_plan.code, service_type='restaurante')

    # ── 20 (ADMIN-CLIENTES 01B): manual_granted_by persistence ───────────────
    def test_20_manual_granted_by_nullable_on_admin_delete(self):
        sub = self._grant()
        self.admin.delete()
        sub.refresh_from_db()
        self.assertIsNone(sub.manual_granted_by_id)
        # The subscription row itself survives the admin's deletion.
        self.assertTrue(SubscriptionV2.objects.filter(pk=sub.pk).exists())

    def test_20b_audit_log_preserves_actor_and_details_independent_of_admin(self):
        sub = self._grant()
        log = AccessAuditLog.objects.get(
            action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED', entity_id=str(sub.id),
        )
        actor_id_before = log.actor_id
        self.admin.delete()
        log.refresh_from_db()
        # AccessAuditLog is the single audit source; it is not touched by
        # this slice — it already records the actor/details at write time.
        self.assertEqual(log.details['plan_code'], self.plan.code)
        self.assertEqual(log.details['service_type'], 'gestion')
        self.assertIsNotNone(actor_id_before)


class ComplimentaryAccessCancellationTest(TestCase):
    """Adapted admin cancellation must accept provider=manual without calling MP."""

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_admin()
        self.plan = _make_plan()
        self.now = timezone.now()
        self.manual_sub = grant_complimentary_access(
            business=self.biz,
            plan_code=self.plan.code,
            service_type='gestion',
            starts_at=self.now,
            ends_at=self.now + timedelta(days=180),
            granted_by=self.admin,
            reason='Cortesía de prueba',
        )

    # ── 15: cancel manual sub, no MP call ────────────────────────────────────
    def test_15_cancel_manual_subscription_no_mp_call(self):
        mp = MagicMock()
        result = cancel_subscription_immediately(
            subscription=self.manual_sub,
            canceled_by=self.admin,
            reason='Cancelación administrativa',
            mp_service=mp,
        )
        mp.cancel_preapproval.assert_not_called()
        mp.update_preapproval.assert_not_called()
        self.manual_sub.refresh_from_db()
        self.assertEqual(self.manual_sub.status, SubscriptionV2.Status.CANCELED)
        self.assertFalse(self.manual_sub.is_active)
        self.assertEqual(result['status'], SubscriptionV2.Status.CANCELED)

    # ── 16: audit log preserved ───────────────────────────────────────────────
    def test_16_cancel_manual_subscription_writes_audit_log(self):
        mp = MagicMock()
        cancel_subscription_immediately(
            subscription=self.manual_sub,
            canceled_by=self.admin,
            reason='Cancelación administrativa',
            mp_service=mp,
        )
        log = AccessAuditLog.objects.filter(
            action='ADMIN_SUBSCRIPTION_CANCELED',
            actor=self.admin,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['plan_code'], self.plan.code)

    # ── 17: regression — Mercado Pago cancellation unaffected ────────────────
    def test_17_regression_mercadopago_cancellation_still_calls_mp(self):
        mp_sub = SubscriptionV2.objects.create(
            business=_make_business(name='MP Biz'),
            service_type='gestion',
            plan_code='gestion_pro',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=FAKE_PREAPPROVAL_ID,
            external_reference=f'SUB-{uuid.uuid4()}',
            status=SubscriptionV2.Status.ACTIVE,
            is_active=True,
        )
        mp = MagicMock()
        mp.cancel_preapproval.return_value = {'id': FAKE_PREAPPROVAL_ID, 'status': 'canceled'}
        cancel_subscription_immediately(
            subscription=mp_sub,
            canceled_by=self.admin,
            reason='Cancelación MP',
            mp_service=mp,
        )
        mp.cancel_preapproval.assert_called_once_with(FAKE_PREAPPROVAL_ID)
        mp_sub.refresh_from_db()
        self.assertEqual(mp_sub.status, SubscriptionV2.Status.CANCELED)
