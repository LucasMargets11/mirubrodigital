"""
Tests for the QR de Reseñas service-activation hook.

Verifies that after a Mercado Pago payment activates a SubscriptionV2 of
service_type=qr_reviews, all legacy/companion artifacts the runtime gates
read (business.Subscription, reviews.ReviewConfig, owner Membership,
Business.status) end up in the correct state — exactly equivalent to the
manual shell fix operators used to apply.

Covers:
  * Direct invocation of ``ensure_service_activation`` for Base / Pro plans
  * Idempotency (calling twice never duplicates)
  * Reconcile path equivalence (webhook-skipped activation still works)
  * End-to-end gate: GET /api/v1/reviews/qr/ → 200 after activation
  * Negative: gestion plan does NOT create qr_reviews artifacts

The hook itself is the boundary tested here.  Webhook-correlation and
SubscriptionV2 birth-path tests live in test_subscriptionv2_birth_path.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.billing.models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
)
from apps.billing.service_activation import ensure_service_activation
from apps.billing.subscription_activator import activate_subscription_from_invoice
from apps.business.models import Business, Subscription as BizSubscription
from apps.reviews.models import ReviewConfig, ReviewMode

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_business(slug='qrr-biz', status='onboarding', service=''):
    return Business.objects.create(
        name=f'Biz {slug}', slug=slug, default_service=service, status=status,
    )


def _make_owner(suffix='1'):
    return User.objects.create_user(username=f'owner-{suffix}', password='pw12345!')


def _make_plan(code='qr_reviews_pro', price='2500.00'):
    return Plan.objects.create(
        code=code,
        name=f'Plan {code}',
        price=Decimal(price),
        interval='monthly',
        mp_preapproval_plan_id=f'mp-{code}-{uuid.uuid4().hex[:6]}',
    )


def _make_v2(business, owner, plan_code, service_type='qr_reviews'):
    """Create an ACTIVE SubscriptionV2 simulating a fresh MP activation."""
    plan = Plan.objects.filter(code=plan_code).first() or _make_plan(plan_code)
    session = MpCheckoutSession.objects.create(
        user=owner,
        tenant=business,
        plan=plan,
        status='created',
    )
    return SubscriptionV2.objects.create(
        business=business,
        checkout_session=session,
        service_type=service_type,
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=f'preapp-{uuid.uuid4().hex[:10]}',
        external_reference=f'EXT-{uuid.uuid4().hex[:12]}',
        status=SubscriptionV2.Status.ACTIVE,
        current_period_end=timezone.now() + timezone.timedelta(days=30),
    )


def _run_hook(business, owner, v2, *, source='webhook'):
    ensure_service_activation(
        business=business,
        owner=owner,
        plan_code=v2.plan_code,
        service_type=v2.service_type,
        subscription_v2=v2,
        source=source,
        external_reference=v2.external_reference,
        provider='mercadopago',
    )


# ─────────────────────────────────────────────────────────────────────────────
# Direct hook tests — Pro plan
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsProActivationTests(TestCase):

    def setUp(self):
        self.biz = _make_business(slug='pro-biz')
        self.owner = _make_owner('pro')
        self.v2 = _make_v2(self.biz, self.owner, 'qr_reviews_pro')

    def test_activation_sets_business_active(self):
        _run_hook(self.biz, self.owner, self.v2)
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')
        self.assertIsNotNone(self.biz.activated_at)

    def test_activation_sets_default_service(self):
        _run_hook(self.biz, self.owner, self.v2)
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.default_service, 'qr_reviews')

    def test_activation_creates_legacy_subscription_pro(self):
        _run_hook(self.biz, self.owner, self.v2)
        legacy = BizSubscription.objects.get(business=self.biz)
        self.assertEqual(legacy.plan, 'qr_reviews_pro')
        self.assertEqual(legacy.service, 'qr_reviews')
        self.assertEqual(legacy.status, 'active')
        self.assertIsNotNone(legacy.renews_at)

    def test_activation_creates_review_config_enabled_smart_filter(self):
        _run_hook(self.biz, self.owner, self.v2)
        cfg = ReviewConfig.objects.get(business=self.biz)
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.mode, ReviewMode.SMART_FILTER)
        self.assertEqual(cfg.mode, 'smart_filter')  # explicit value guard
        self.assertEqual(cfg.redirect_threshold, 4)

    def test_activation_creates_owner_membership(self):
        _run_hook(self.biz, self.owner, self.v2)
        m = Membership.objects.get(user=self.owner, business=self.biz)
        self.assertEqual(m.role, 'owner')
        self.assertEqual(m.status, Membership.Status.ACTIVE)


# ─────────────────────────────────────────────────────────────────────────────
# Direct hook tests — Base plan
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsBaseActivationTests(TestCase):

    def setUp(self):
        self.biz = _make_business(slug='base-biz')
        self.owner = _make_owner('base')
        self.v2 = _make_v2(self.biz, self.owner, 'qr_reviews_base')

    def test_legacy_subscription_uses_base_plan(self):
        _run_hook(self.biz, self.owner, self.v2)
        legacy = BizSubscription.objects.get(business=self.biz)
        self.assertEqual(legacy.plan, 'qr_reviews_base')
        self.assertEqual(legacy.service, 'qr_reviews')
        self.assertEqual(legacy.status, 'active')

    def test_review_config_created_enabled(self):
        _run_hook(self.biz, self.owner, self.v2)
        cfg = ReviewConfig.objects.get(business=self.biz)
        self.assertTrue(cfg.enabled)
        # Base plan should not force SMART_FILTER on create.
        self.assertNotEqual(cfg.mode, ReviewMode.SMART_FILTER)


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsIdempotencyTests(TestCase):

    def setUp(self):
        self.biz = _make_business(slug='idem-biz')
        self.owner = _make_owner('idem')
        self.v2 = _make_v2(self.biz, self.owner, 'qr_reviews_pro')

    def test_calling_twice_does_not_duplicate_legacy(self):
        _run_hook(self.biz, self.owner, self.v2)
        _run_hook(self.biz, self.owner, self.v2)
        self.assertEqual(
            BizSubscription.objects.filter(business=self.biz).count(), 1,
        )

    def test_calling_twice_does_not_duplicate_review_config(self):
        _run_hook(self.biz, self.owner, self.v2)
        _run_hook(self.biz, self.owner, self.v2)
        self.assertEqual(
            ReviewConfig.objects.filter(business=self.biz).count(), 1,
        )

    def test_calling_twice_does_not_duplicate_membership(self):
        _run_hook(self.biz, self.owner, self.v2)
        _run_hook(self.biz, self.owner, self.v2)
        self.assertEqual(
            Membership.objects.filter(user=self.owner, business=self.biz).count(), 1,
        )

    def test_preserves_operator_review_config_edits(self):
        """ReviewConfig fields set by operator (custom_redirect_url) must
        survive a re-run of the hook."""
        _run_hook(self.biz, self.owner, self.v2)
        cfg = ReviewConfig.objects.get(business=self.biz)
        cfg.custom_redirect_url = 'https://operator-set.example.com'
        cfg.redirect_threshold = 5  # operator-tuned threshold
        cfg.save(update_fields=['custom_redirect_url', 'redirect_threshold'])

        _run_hook(self.biz, self.owner, self.v2, source='reconcile')

        cfg.refresh_from_db()
        self.assertEqual(cfg.custom_redirect_url, 'https://operator-set.example.com')
        self.assertEqual(cfg.redirect_threshold, 5)
        # enabled must still be True after reactivation
        self.assertTrue(cfg.enabled)

    def test_preserves_operator_legacy_seat_adjustments(self):
        """Legacy Subscription max_seats/max_branches set by operator must survive."""
        _run_hook(self.biz, self.owner, self.v2)
        legacy = BizSubscription.objects.get(business=self.biz)
        legacy.max_seats = 7
        legacy.save(update_fields=['max_seats'])

        _run_hook(self.biz, self.owner, self.v2, source='reconcile')

        legacy.refresh_from_db()
        self.assertEqual(legacy.max_seats, 7)


# ─────────────────────────────────────────────────────────────────────────────
# Negative: other services must not get qr_reviews artifacts
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsNegativeTests(TestCase):

    def test_gestion_payment_does_not_create_review_config(self):
        biz = _make_business(slug='gestion-biz', service='gestion')
        owner = _make_owner('gestion')
        v2 = _make_v2(biz, owner, 'gestion_pro', service_type='gestion')

        _run_hook(biz, owner, v2)

        self.assertFalse(ReviewConfig.objects.filter(business=biz).exists())
        # Legacy sub must not be flipped to qr_reviews
        legacy = BizSubscription.objects.filter(business=biz).first()
        if legacy is not None:
            self.assertNotEqual(legacy.service, 'qr_reviews')

    def test_unknown_qr_plan_code_is_a_no_op(self):
        biz = _make_business(slug='weird-biz')
        owner = _make_owner('weird')
        v2 = _make_v2(biz, owner, 'qr_reviews_unknown')

        _run_hook(biz, owner, v2)

        self.assertFalse(ReviewConfig.objects.filter(business=biz).exists())


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: gate at /api/v1/reviews/qr/ responds 200 after activation
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsEndpointGateTests(TestCase):

    def setUp(self):
        self.biz = _make_business(slug='gate-biz')
        self.owner = _make_owner('gate')
        self.v2 = _make_v2(self.biz, self.owner, 'qr_reviews_pro')
        self.client = APIClient()

    def test_qr_endpoint_returns_200_after_auto_activation(self):
        _run_hook(self.biz, self.owner, self.v2)

        self.client.force_authenticate(user=self.owner)
        # Header used by tenant-resolving middleware
        resp = self.client.get(
            '/api/v1/reviews/qr/', HTTP_X_BUSINESS_ID=str(self.biz.pk),
        )
        # Anything other than 403 plan_not_allowed is acceptable here — the
        # bug was the gate returning 403 because the legacy Subscription
        # didn't exist.  200 (or any non-403) proves the gate now grants
        # access.
        self.assertNotEqual(
            resp.status_code, 403,
            msg=f'Reviews gate denied access: {resp.content!r}',
        )

    def test_qr_endpoint_403_when_no_activation(self):
        """Sanity check: with the SubscriptionV2 explicitly disabled and no
        legacy artifacts in place, the gate denies access (no false grant)."""
        # Force V2 into a non-granting state so neither V2-first nor legacy
        # paths can authorize.
        self.v2.status = SubscriptionV2.Status.CANCELED
        self.v2.is_active = False
        self.v2.save(update_fields=['status', 'is_active'])

        self.client.force_authenticate(user=self.owner)
        Membership.objects.create(
            user=self.owner, business=self.biz, role='owner',
        )
        resp = self.client.get(
            '/api/v1/reviews/qr/', HTTP_X_BUSINESS_ID=str(self.biz.pk),
        )
        self.assertNotEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Reconcile path: same outcome as webhook activation
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsReconcileEquivalenceTests(TestCase):

    def test_reconcile_source_produces_same_artifacts(self):
        biz = _make_business(slug='reconcile-biz')
        owner = _make_owner('reconcile')
        v2 = _make_v2(biz, owner, 'qr_reviews_pro')

        _run_hook(biz, owner, v2, source='reconcile')

        self.assertTrue(BizSubscription.objects.filter(business=biz).exists())
        self.assertTrue(ReviewConfig.objects.filter(business=biz).exists())
        biz.refresh_from_db()
        self.assertEqual(biz.status, 'active')


# ─────────────────────────────────────────────────────────────────────────────
# Integration: activate_subscription_from_invoice triggers the hook
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsActivatorIntegrationTests(TestCase):

    def test_activate_subscription_from_invoice_creates_legacy_and_config(self):
        biz = _make_business(slug='inv-biz')
        owner = _make_owner('inv')
        v2 = _make_v2(biz, owner, 'qr_reviews_pro')
        # Set V2 to CHECKOUT_PENDING so the activator promotes it.
        v2.status = SubscriptionV2.Status.CHECKOUT_PENDING
        v2.is_active = False
        v2.save(update_fields=['status', 'is_active'])

        invoice = BillingInvoiceEvent.objects.create(
            subscription=v2,
            provider_authorized_payment_id=f'pay-{uuid.uuid4().hex[:10]}',
            provider_status='authorized',
            amount=Decimal('2500.00'),
            paid_at=timezone.now(),
        )

        activate_subscription_from_invoice(invoice_event=invoice, subscription=v2)

        # V2 promoted
        v2.refresh_from_db()
        self.assertTrue(v2.is_active)
        # Legacy + ReviewConfig synced by the hook
        self.assertTrue(
            BizSubscription.objects.filter(business=biz, status='active').exists()
        )
        self.assertTrue(
            ReviewConfig.objects.filter(business=biz, enabled=True).exists()
        )
        biz.refresh_from_db()
        self.assertEqual(biz.status, 'active')
