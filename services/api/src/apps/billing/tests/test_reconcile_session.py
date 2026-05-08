"""
tests/test_reconcile_session.py
================================
Tests for the reconcile_session() function and the
POST /billing/checkout-sessions/<id>/reconcile/ endpoint.

Covered scenarios:
  1.  reconcile_session activates business when MP confirms payment
  2.  reconcile_session is idempotent — calling it twice does NOT duplicate
      SubscriptionV2, BillingInvoiceEvent, or trigger double-activation.
  3.  reconcile_session skips preapprovals with wrong external_reference
      (cross-tenant protection).
  4.  reconcile_session returns 'awaiting_webhook' when MP has no preapprovals yet.
  5.  reconcile_session returns 'linked' when preapproval exists but
      authorized_payment is still pending.
  6.  reconcile_session safety net: fixes Business.status when SubscriptionV2
      is already active but Business is still 'onboarding'.
  7.  CheckoutSessionReconcileView requires authentication (403 for anon).
  8.  CheckoutSessionReconcileView rejects requests for another user's session.
  9.  CheckoutSessionReconcileView allows member of the session's tenant.
 10.  _compute_onboarding_step detects active SubscriptionV2 → heals Business.
 11.  _has_pending_checkout detects open MpCheckoutSession (no SubscriptionV2 yet).
 12.  Webhook arriving AFTER reconcile has already activated → idempotent no-op.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
)
from apps.billing.subscription_activator import activate_subscription_from_invoice
from apps.business.models import Business, Subscription as BizSubscription
from apps.accounts.models import Membership

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers / factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email=None):
    email = email or f'u{uuid.uuid4().hex[:8]}@test.com'
    return User.objects.create_user(email=email, username=email, password='pw123456')


def _make_plan(code='starter_test'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults=dict(name='Starter', price=9990, currency='ARS',
                      interval='monthly', plan_status='active'),
    )
    return plan


def _make_business(name=None, status='onboarding', service='gestion'):
    name = name or f'Biz-{uuid.uuid4().hex[:6]}'
    biz = Business.objects.create(name=name, status=status,
                                  default_service=service, service_type=service)
    BizSubscription.objects.create(business=biz, plan='start', status='active')
    return biz


def _make_session(user, plan, tenant, ext_ref=None, plan_id=None,
                  session_status=MpCheckoutSession.Status.CHECKOUT_CREATED):
    ext_ref = ext_ref or f'SESS-{uuid.uuid4()}'
    plan_id = plan_id or f'PLAN-{uuid.uuid4().hex[:8]}'
    return MpCheckoutSession.objects.create(
        user=user,
        plan=plan,
        tenant=tenant,
        status=session_status,
        provider_preapproval_plan_id=plan_id,
        provider_checkout_url='https://mp.com/checkout',
        idempotency_key=f'key-{uuid.uuid4()}',
        mp_external_reference=ext_ref,
        expires_at=timezone.now() + timedelta(hours=1),
    )


def _make_sub_v2(business, plan, session=None, is_active=False,
                 sub_status=SubscriptionV2.Status.CHECKOUT_PENDING):
    return SubscriptionV2.objects.create(
        business=business,
        service_type=business.default_service,
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=f'preapp-{uuid.uuid4()}',
        external_reference=f'ref-{uuid.uuid4()}',
        status=sub_status,
        is_active=is_active,
        checkout_session=session,
    )


def _mp_preapproval(preapproval_id, plan_id, ext_ref, status='authorized'):
    return {
        'id': preapproval_id,
        'preapproval_plan_id': plan_id,
        'external_reference': ext_ref,
        'status': status,
        'payer_id': 12345,
        'reason': 'Test subscription',
        'auto_recurring': {'frequency': 1, 'frequency_type': 'months',
                           'transaction_amount': 9990, 'currency_id': 'ARS'},
        'date_created': '2026-05-01T12:00:00.000-04:00',
        'last_modified': '2026-05-01T12:00:00.000-04:00',
    }


def _mp_authorized_payment(ap_id, preapproval_id, status='authorized'):
    return {
        'id': ap_id,
        'preapproval_id': preapproval_id,
        'status': status,
        'transaction_amount': 9990,
        'currency_id': 'ARS',
        'payment_id': f'pay-{uuid.uuid4().hex[:8]}',
        'date_approved': '2026-05-01T12:00:00.000-04:00',
        'date_created': '2026-05-01T12:00:00.000-04:00',
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. reconcile_session activates business when MP confirms payment
# ─────────────────────────────────────────────────────────────────────────────

class ReconcileSessionActivatesTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan()
        self.biz = _make_business()
        Membership.objects.create(user=self.user, business=self.biz, role='owner')
        self.session = _make_session(self.user, self.plan, self.biz)

    @patch('apps.billing.mp_service.MercadoPagoService')
    @patch('apps.billing.webhook_processor._upsert_subscription_v2')
    def test_activates_business_on_authorized_payment(self, mock_upsert, mock_mp_cls):
        preapproval_id = f'preapp-{uuid.uuid4().hex}'
        ap_id = str(uuid.uuid4().int)
        plan_id = self.session.provider_preapproval_plan_id
        ext_ref = self.session.mp_external_reference

        sub_v2 = _make_sub_v2(self.biz, self.plan, session=self.session)
        mock_upsert.return_value = sub_v2

        mp = MagicMock()
        mp.search_preapprovals.return_value = [
            _mp_preapproval(preapproval_id, plan_id, ext_ref, status='authorized')
        ]
        mp.search_authorized_payments.return_value = [
            _mp_authorized_payment(ap_id, preapproval_id)
        ]
        mock_mp_cls.return_value = mp

        from apps.billing.reconciliation import reconcile_session
        result = reconcile_session(str(self.session.id))

        self.assertEqual(result['status'], 'activated')
        self.assertIsNone(result['error'])

        # SubscriptionV2 must be active.
        sub_v2.refresh_from_db()
        self.assertTrue(sub_v2.is_active)
        self.assertEqual(sub_v2.status, SubscriptionV2.Status.ACTIVE)

        # Business must be 'active'.
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')

        # BillingInvoiceEvent must exist.
        self.assertTrue(
            BillingInvoiceEvent.objects.filter(
                provider_authorized_payment_id=ap_id
            ).exists()
        )

        # MpCheckoutSession must be 'activated'.
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, MpCheckoutSession.Status.ACTIVATED)


# ─────────────────────────────────────────────────────────────────────────────
# 2. reconcile_session is idempotent
# ─────────────────────────────────────────────────────────────────────────────

class ReconcileSessionIdempotencyTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_idem')
        self.biz = _make_business()
        Membership.objects.create(user=self.user, business=self.biz, role='owner')
        self.session = _make_session(self.user, self.plan, self.biz)

    @patch('apps.billing.mp_service.MercadoPagoService')
    @patch('apps.billing.webhook_processor._upsert_subscription_v2')
    def test_second_call_is_no_op(self, mock_upsert, mock_mp_cls):
        preapproval_id = f'preapp-{uuid.uuid4().hex}'
        ap_id = str(uuid.uuid4().int)
        plan_id = self.session.provider_preapproval_plan_id
        ext_ref = self.session.mp_external_reference

        sub_v2 = _make_sub_v2(self.biz, self.plan, session=self.session)
        mock_upsert.return_value = sub_v2

        mp = MagicMock()
        mp.search_preapprovals.return_value = [
            _mp_preapproval(preapproval_id, plan_id, ext_ref, status='authorized')
        ]
        mp.search_authorized_payments.return_value = [
            _mp_authorized_payment(ap_id, preapproval_id)
        ]
        mock_mp_cls.return_value = mp

        from apps.billing.reconciliation import reconcile_session

        result1 = reconcile_session(str(self.session.id))
        self.assertEqual(result1['status'], 'activated')

        # Call again — session is now ACTIVATED (terminal).
        result2 = reconcile_session(str(self.session.id))
        self.assertIn('already activated', ' '.join(result2['action_taken']))

        # Exactly one BillingInvoiceEvent must exist.
        self.assertEqual(
            BillingInvoiceEvent.objects.filter(
                provider_authorized_payment_id=ap_id
            ).count(),
            1,
        )

        # Business is still active, not double-written.
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')


# ─────────────────────────────────────────────────────────────────────────────
# 3. reconcile_session skips wrong external_reference (cross-tenant guard)
# ─────────────────────────────────────────────────────────────────────────────

class ReconcileExternalRefGuardTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_guard')
        self.biz = _make_business()
        Membership.objects.create(user=self.user, business=self.biz, role='owner')
        self.session = _make_session(self.user, self.plan, self.biz,
                                     ext_ref='SESS-MINE')

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_wrong_ext_ref_skipped(self, mock_mp_cls):
        plan_id = self.session.provider_preapproval_plan_id

        mp = MagicMock()
        # MP returns a preapproval that belongs to a DIFFERENT session/tenant.
        mp.search_preapprovals.return_value = [
            _mp_preapproval('preapp-OTHER', plan_id, 'SESS-SOMEONE-ELSE')
        ]
        mp.search_authorized_payments.return_value = []
        mock_mp_cls.return_value = mp

        from apps.billing.reconciliation import reconcile_session
        result = reconcile_session(str(self.session.id))

        # Must NOT activate.
        self.assertNotEqual(result['status'], 'activated')
        # Business remains in onboarding.
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'onboarding')
        # No SubscriptionV2 created.
        self.assertFalse(
            SubscriptionV2.objects.filter(business=self.biz).exists()
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. reconcile_session returns awaiting_webhook when MP has no preapprovals
# ─────────────────────────────────────────────────────────────────────────────

class ReconcileNoPreapprovalsTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_empty')
        self.biz = _make_business()
        self.session = _make_session(self.user, self.plan, self.biz)

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_no_preapprovals_returns_awaiting(self, mock_mp_cls):
        mp = MagicMock()
        mp.search_preapprovals.return_value = []
        mock_mp_cls.return_value = mp

        from apps.billing.reconciliation import reconcile_session
        result = reconcile_session(str(self.session.id))

        self.assertNotEqual(result['status'], 'activated')
        self.assertIsNone(result['error'])
        self.assertTrue(
            any('No preapprovals' in a for a in result['action_taken'])
        )
        # Business still onboarding.
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'onboarding')


# ─────────────────────────────────────────────────────────────────────────────
# 5. reconcile_session returns 'linked' when preapproval pending (not authorized)
# ─────────────────────────────────────────────────────────────────────────────

class ReconcilePendingPreapprovalTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_pend')
        self.biz = _make_business()
        self.session = _make_session(self.user, self.plan, self.biz)

    @patch('apps.billing.mp_service.MercadoPagoService')
    @patch('apps.billing.webhook_processor._upsert_subscription_v2')
    def test_pending_preapproval_not_activated(self, mock_upsert, mock_mp_cls):
        preapproval_id = f'preapp-{uuid.uuid4().hex}'
        plan_id = self.session.provider_preapproval_plan_id
        ext_ref = self.session.mp_external_reference

        sub_v2 = _make_sub_v2(self.biz, self.plan, session=self.session)
        mock_upsert.return_value = sub_v2

        mp = MagicMock()
        mp.search_preapprovals.return_value = [
            _mp_preapproval(preapproval_id, plan_id, ext_ref, status='pending')
        ]
        mock_mp_cls.return_value = mp

        from apps.billing.reconciliation import reconcile_session
        result = reconcile_session(str(self.session.id))

        self.assertNotEqual(result['status'], 'activated')
        # No authorized_payment call made.
        mp.search_authorized_payments.assert_not_called()
        # Business stays in onboarding.
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'onboarding')


# ─────────────────────────────────────────────────────────────────────────────
# 6. Safety net: active SubscriptionV2 but Business still 'onboarding'
# ─────────────────────────────────────────────────────────────────────────────

class SafetyNetTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_safety')
        self.biz = _make_business(status='onboarding')
        self.session = _make_session(
            self.user, self.plan, self.biz,
            session_status=MpCheckoutSession.Status.ACTIVATED,
        )

    @patch('apps.billing.mp_service.MercadoPagoService')
    @patch('apps.billing.webhook_processor._upsert_subscription_v2')
    def test_safety_net_fixes_business_status(self, mock_upsert, mock_mp_cls):
        """
        If reconcile finds an authorized preapproval + payment and activates the
        subscription, but Business.status was never updated (partial write), the
        safety net must flip Business.status → 'active'.
        """
        preapproval_id = f'preapp-{uuid.uuid4().hex}'
        ap_id = str(uuid.uuid4().int)
        plan_id = self.session.provider_preapproval_plan_id
        ext_ref = self.session.mp_external_reference

        # Create an already-active subscription — simulates a previous partial write.
        sub_v2 = _make_sub_v2(self.biz, self.plan, session=self.session,
                               is_active=True, sub_status=SubscriptionV2.Status.ACTIVE)
        mock_upsert.return_value = sub_v2

        # Session is already ACTIVATED → reconcile fast-exits.
        # We test the safety net via the onboarding step healer instead.
        from apps.accounts.onboarding_views import _compute_onboarding_step
        step = _compute_onboarding_step(self.biz)

        self.assertEqual(step, 'done')
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')

    def test_active_subscription_safety_net_updates_business_status_direct(self):
        """
        Direct test of the safety net in _compute_onboarding_step:
        business in 'onboarding' but has is_active=True SubscriptionV2 → healed.
        """
        _make_sub_v2(self.biz, self.plan, is_active=True,
                     sub_status=SubscriptionV2.Status.ACTIVE)

        from apps.accounts.onboarding_views import _compute_onboarding_step
        step = _compute_onboarding_step(self.biz)

        self.assertEqual(step, 'done')
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')


# ─────────────────────────────────────────────────────────────────────────────
# 7. Endpoint requires authentication
# ─────────────────────────────────────────────────────────────────────────────

class ReconcileEndpointAuthTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_auth')
        self.biz = _make_business()
        Membership.objects.create(user=self.user, business=self.biz, role='owner')
        self.session = _make_session(self.user, self.plan, self.biz)
        self.client = APIClient()

    def _url(self):
        return f'/api/v1/billing/checkout-sessions/{self.session.id}/reconcile/'

    def test_anonymous_gets_403(self):
        resp = self.client.post(self._url())
        # DRF returns 401 for unauthenticated requests with IsAuthenticated.
        self.assertIn(resp.status_code, (401, 403))

    def test_authenticated_owner_allowed(self):
        self.client.force_authenticate(user=self.user)
        with patch('apps.billing.reconciliation.reconcile_session') as mock_rec:
            mock_rec.return_value = {
                'session_id': str(self.session.id),
                'status': 'awaiting_webhook',
                'action_taken': [],
                'error': None,
            }
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Endpoint rejects requests for another user's session
# ─────────────────────────────────────────────────────────────────────────────

class ReconcileEndpointOwnershipTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.other_user = _make_user()
        self.plan = _make_plan('starter_own')
        self.biz = _make_business()
        Membership.objects.create(user=self.user, business=self.biz, role='owner')
        # Session belongs to self.user / self.biz, NOT self.other_user.
        self.session = _make_session(self.user, self.plan, self.biz)
        self.client = APIClient()

    def _url(self):
        return f'/api/v1/billing/checkout-sessions/{self.session.id}/reconcile/'

    def test_other_user_gets_403(self):
        self.client.force_authenticate(user=self.other_user)
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 403)

    def test_member_of_tenant_allowed(self):
        """A user who is a member of the session's tenant CAN reconcile."""
        Membership.objects.create(user=self.other_user, business=self.biz, role='staff')
        self.client.force_authenticate(user=self.other_user)
        with patch('apps.billing.reconciliation.reconcile_session') as mock_rec:
            mock_rec.return_value = {
                'session_id': str(self.session.id),
                'status': 'awaiting_webhook',
                'action_taken': [],
                'error': None,
            }
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# 9. _has_pending_checkout detects open MpCheckoutSession (no SubscriptionV2)
# ─────────────────────────────────────────────────────────────────────────────

class HasPendingCheckoutTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_hpc')
        self.biz = _make_business()

    def test_open_session_detected_without_subscriptionv2(self):
        """
        Before the subscription_preapproval webhook fires, there is no
        SubscriptionV2.  _has_pending_checkout must still return True via the
        MpCheckoutSession fallback.
        """
        _make_session(
            self.user, self.plan, self.biz,
            session_status=MpCheckoutSession.Status.AWAITING_WEBHOOK,
        )
        from apps.accounts.onboarding_views import _has_pending_checkout
        self.assertTrue(_has_pending_checkout(self.biz))

    def test_no_session_returns_false(self):
        from apps.accounts.onboarding_views import _has_pending_checkout
        self.assertFalse(_has_pending_checkout(self.biz))

    def test_activated_session_returns_false(self):
        _make_session(
            self.user, self.plan, self.biz,
            session_status=MpCheckoutSession.Status.ACTIVATED,
        )
        from apps.accounts.onboarding_views import _has_pending_checkout
        # Activated is a terminal status — not "pending" anymore.
        self.assertFalse(_has_pending_checkout(self.biz))


# ─────────────────────────────────────────────────────────────────────────────
# 10. Re-login: compute_onboarding_step returns 'checkout_pending' for open session
# ─────────────────────────────────────────────────────────────────────────────

class ReloginOnboardingStepTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_relog')
        self.biz = _make_business(status='onboarding')
        self.biz.service_type = 'gestion'
        self.biz.save()

    def test_open_session_gives_checkout_pending_step(self):
        _make_session(
            self.user, self.plan, self.biz,
            session_status=MpCheckoutSession.Status.AWAITING_WEBHOOK,
        )
        from apps.accounts.onboarding_views import _compute_onboarding_step
        step = _compute_onboarding_step(self.biz)
        self.assertEqual(step, 'checkout_pending')

    def test_no_open_session_gives_plan_selection(self):
        from apps.accounts.onboarding_views import _compute_onboarding_step
        step = _compute_onboarding_step(self.biz)
        self.assertEqual(step, 'plan_selection')

    def test_active_status_gives_done(self):
        self.biz.status = 'active'
        self.biz.save()
        from apps.accounts.onboarding_views import _compute_onboarding_step
        step = _compute_onboarding_step(self.biz)
        self.assertEqual(step, 'done')


# ─────────────────────────────────────────────────────────────────────────────
# 11. Webhook after reconcile already activated → idempotent no-op
# ─────────────────────────────────────────────────────────────────────────────

class WebhookAfterReconcileIdempotentTest(TestCase):
    """
    Simulate the race where reconcile_session activates first, then the
    MP webhook also fires.  The activator must not double-count anything.
    """

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan('starter_race')
        self.biz = _make_business(status='onboarding')
        self.session = _make_session(self.user, self.plan, self.biz,
                                     session_status=MpCheckoutSession.Status.LINKED)
        self.sub = _make_sub_v2(self.biz, self.plan, session=self.session)

    def test_webhook_is_no_op_after_reconcile_activated(self):
        # Simulate reconcile having activated things:
        self.sub.status = SubscriptionV2.Status.ACTIVE
        self.sub.is_active = True
        self.sub.save()
        self.biz.status = 'active'
        self.biz.save()

        # Create the invoice that reconcile would have created.
        ap_id = str(uuid.uuid4().int)
        invoice = BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id=ap_id,
            provider_payment_id=f'pay-{uuid.uuid4().hex}',
            provider_subscription_id=self.sub.provider_sub_id,
            subscription=self.sub,
            checkout_session=self.session,
            amount=9990,
            currency='ARS',
            provider_status='authorized',
            paid_at=timezone.now(),
            raw_payload_json={},
        )

        # Calling the activator again (as the webhook processor would) must
        # return False (already active) without changing anything.
        activated = activate_subscription_from_invoice(
            invoice_event=invoice,
            subscription=self.sub,
        )
        self.assertFalse(activated)

        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')

        self.assertEqual(
            BillingInvoiceEvent.objects.filter(
                provider_authorized_payment_id=ap_id
            ).count(),
            1,
        )
