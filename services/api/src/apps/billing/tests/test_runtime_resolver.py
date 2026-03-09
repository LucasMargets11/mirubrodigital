"""
Tests for billing.runtime — RuntimeSubscriptionResolver (Phase 3: V2-first).

Covers:
  RuntimeSubscriptionResolverTest
    1. Uses V2 when active
    2. Falls back to legacy when no V2 exists
    3. No false defaults when no subscription exists
    4. V2 priority over legacy when both present
    5. V2 suspended → no fallback to legacy (§F.2)
    6. checkout_pending V2 treated as absent → falls back to legacy
    7. V2 trialing within trial window → access granted
    8. V2 past_due within grace → access granted
    9. V2 past_due grace expired → access denied, no fallback
   10. v2_legacy_mismatch logged but never raises
   11. _extract_plan_tier — direct and compound codes
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import SubscriptionV2
from apps.billing.runtime import (
    ResolvedSubscription,
    _extract_plan_tier,
    resolve_subscription,
)
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_business(name='TestBiz', service='gestion'):
    return Business.objects.create(
        name=name,
        default_service=service,
        status='active',
    )


def _attach_legacy(biz, plan='pro', status='active'):
    return BizSubscription.objects.create(
        business=biz,
        plan=plan,
        status=status,
        service=biz.default_service,
    )


def _attach_v2(biz, plan_code='pro', status=None, service_type=None,
               trial_ends_at=None, grace_until=None, current_period_end=None):
    return SubscriptionV2.objects.create(
        business=biz,
        service_type=service_type or biz.default_service,
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MANUAL,
        external_reference=f'SUB-{uuid.uuid4()}',
        status=status or SubscriptionV2.Status.ACTIVE,
        trial_ends_at=trial_ends_at,
        grace_until=grace_until,
        current_period_end=current_period_end,
    )


# ─────────────────────────────────────────────────────────────────────────────
# _extract_plan_tier
# ─────────────────────────────────────────────────────────────────────────────

class ExtractPlanTierTest(TestCase):

    def test_direct_tier_names(self):
        for tier in ('start', 'pro', 'business', 'enterprise',
                     'menu_qr', 'menu_qr_visual', 'menu_qr_marca',
                     'menu_qr_lite', 'menu_qr_pro', 'menu_qr_premium',
                     'starter', 'plus'):
            with self.subTest(tier=tier):
                self.assertEqual(_extract_plan_tier(tier), tier)

    def test_compound_gestion_pro_monthly(self):
        self.assertEqual(_extract_plan_tier('gestion_pro_monthly'), 'pro')

    def test_compound_gestion_start_monthly(self):
        self.assertEqual(_extract_plan_tier('gestion_start_monthly'), 'start')

    def test_compound_menu_qr_visual_monthly(self):
        self.assertEqual(_extract_plan_tier('menu_qr_visual_monthly'), 'menu_qr_visual')

    def test_compound_menu_qr_pro_monthly(self):
        self.assertEqual(_extract_plan_tier('menu_qr_pro_monthly'), 'menu_qr_pro')

    def test_menu_qr_not_masked_by_menu_qr_pro(self):
        # 'menu_qr_monthly' must resolve to 'menu_qr', not 'menu_qr_pro'
        self.assertEqual(_extract_plan_tier('menu_qr_monthly'), 'menu_qr')

    def test_unknown_code_returned_as_is(self):
        self.assertEqual(_extract_plan_tier('some_unknown_plan'), 'some_unknown_plan')

    def test_empty_string_defaults_to_start(self):
        self.assertEqual(_extract_plan_tier(''), 'start')


# ─────────────────────────────────────────────────────────────────────────────
# RuntimeSubscriptionResolverTest
# ─────────────────────────────────────────────────────────────────────────────

class RuntimeSubscriptionResolverTest(TestCase):

    def test_uses_v2_when_active(self):
        biz = _make_business()
        _attach_legacy(biz, plan='start')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertEqual(resolved.plan, 'pro')
        self.assertEqual(resolved.status, SubscriptionV2.Status.ACTIVE)
        self.assertTrue(resolved.access_granted)
        self.assertIsNotNone(resolved.subscription_v2)
        self.assertIsNone(resolved.fallback_reason)

    def test_v2_entitlements_include_plan_entitlements(self):
        biz = _make_business()
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        resolved = resolve_subscription(biz)

        self.assertIn('gestion.customers', resolved.entitlements)
        self.assertIn('gestion.cash', resolved.entitlements)
        self.assertIn('gestion.reports', resolved.entitlements)

    def test_falls_back_to_legacy_when_no_v2(self):
        biz = _make_business()
        legacy = _attach_legacy(biz, plan='pro', status='active')

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'legacy')
        self.assertEqual(resolved.plan, 'pro')
        self.assertEqual(resolved.status, 'active')
        self.assertTrue(resolved.access_granted)
        self.assertEqual(resolved.fallback_reason, 'no_v2_found')
        self.assertIs(resolved.legacy_sub, legacy)
        self.assertIsNone(resolved.subscription_v2)

    def test_no_defaults_when_no_subscription(self):
        """No subscription → source=none, access_granted=False, no optimistic plan."""
        biz = _make_business()

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'none')
        self.assertIsNone(resolved.plan)
        self.assertIsNone(resolved.status)
        self.assertFalse(resolved.access_granted)
        self.assertEqual(len(resolved.entitlements), 0)

    def test_v2_priority_over_legacy_when_both_exist(self):
        """When both V2 and legacy exist, V2 is authoritative."""
        biz = _make_business()
        _attach_legacy(biz, plan='business', status='active')
        _attach_v2(biz, plan_code='start', status=SubscriptionV2.Status.ACTIVE)

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertEqual(resolved.plan, 'start')  # V2 plan, not legacy business

    def test_v2_suspended_no_fallback_to_legacy(self):
        """
        §F.2: V2 suspended + legacy active → source=v2, access_denied.
        Must NOT fall back to legacy.
        """
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertFalse(resolved.access_granted)
        self.assertEqual(len(resolved.entitlements), 0)

    def test_v2_canceled_falls_back_to_legacy(self):
        """
        V2 canceled (excluded from query) → falls back to legacy.
        Canceled is the one exception where legacy fallback is safe.
        """
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.CANCELED)

        resolved = resolve_subscription(biz)

        # Canceled V2 is excluded, so fallback to legacy
        self.assertEqual(resolved.source, 'legacy')
        self.assertTrue(resolved.access_granted)

    def test_checkout_pending_falls_back_to_legacy(self):
        """checkout_pending V2 is treated as absent → falls back to legacy."""
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='start', status=SubscriptionV2.Status.CHECKOUT_PENDING)

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'legacy')
        self.assertTrue(resolved.access_granted)
        self.assertEqual(resolved.plan, 'pro')

    def test_v2_trialing_within_window_grants_access(self):
        biz = _make_business()
        future = timezone.now() + timedelta(days=7)
        _attach_v2(
            biz, plan_code='pro',
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at=future,
        )

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertTrue(resolved.access_granted)
        self.assertEqual(resolved.status, SubscriptionV2.Status.TRIALING)

    def test_v2_trialing_expired_denies_access(self):
        biz = _make_business()
        past = timezone.now() - timedelta(days=1)
        _attach_v2(
            biz, plan_code='pro',
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at=past,
        )

        resolved = resolve_subscription(biz)

        self.assertFalse(resolved.access_granted)
        self.assertEqual(resolved.source, 'v2')

    def test_v2_past_due_within_grace_grants_access(self):
        biz = _make_business()
        future_grace = timezone.now() + timedelta(days=3)
        _attach_v2(
            biz, plan_code='pro',
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until=future_grace,
        )

        resolved = resolve_subscription(biz)

        self.assertTrue(resolved.access_granted)
        self.assertEqual(resolved.source, 'v2')
        self.assertEqual(resolved.access_until, future_grace)

    def test_v2_past_due_grace_expired_denies_access_no_legacy_fallback(self):
        """
        §F.2: past_due V2 where grace_until has expired → deny access.
        Must NOT fall back to legacy, even if legacy is active.
        """
        biz = _make_business()
        past_grace = timezone.now() - timedelta(days=1)
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(
            biz, plan_code='pro',
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until=past_grace,
        )

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertFalse(resolved.access_granted)
        self.assertEqual(resolved.fallback_reason, f'v2_status={SubscriptionV2.Status.PAST_DUE}')

    def test_legacy_not_active_denies_access(self):
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='past_due')

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'legacy')
        self.assertFalse(resolved.access_granted)
        self.assertEqual(len(resolved.entitlements), 0)

    def test_mismatch_tolerated_no_raise(self):
        """
        V2 and legacy with different plans and statuses should log mismatch
        but never raise an exception.
        """
        biz = _make_business()
        _attach_legacy(biz, plan='start', status='active')
        _attach_v2(biz, plan_code='business', status=SubscriptionV2.Status.ACTIVE)

        # Must not raise
        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertEqual(resolved.plan, 'business')

    def test_service_type_override(self):
        """Explicit service_type overrides business.default_service."""
        biz = _make_business(service='gestion')
        _attach_v2(biz, plan_code='menu_qr', service_type='menu_qr',
                   status=SubscriptionV2.Status.ACTIVE)

        resolved = resolve_subscription(biz, service_type='menu_qr')

        self.assertEqual(resolved.source, 'v2')
        self.assertEqual(resolved.service_type, 'menu_qr')

    def test_service_type_cross_lookup_finds_any_v2(self):
        """
        If service_type hint doesn't match any V2, the best available V2
        for the business is returned.
        """
        biz = _make_business(service='gestion')
        _attach_v2(biz, plan_code='menu_qr', service_type='menu_qr',
                   status=SubscriptionV2.Status.ACTIVE)

        # Ask for 'restaurante' but only 'menu_qr' V2 exists
        resolved = resolve_subscription(biz, service_type='restaurante')

        self.assertEqual(resolved.source, 'v2')  # best available V2 is returned
        self.assertEqual(resolved.service_type, 'menu_qr')

    # ── Regression guards ────────────────────────────────────────────────────

    def test_legacy_subscription_model_not_removed(self):
        """Regression: legacy business.Subscription still coexists."""
        biz = _make_business()
        sub = _attach_legacy(biz, plan='pro', status='active')
        self.assertIsNotNone(sub.pk)
        self.assertEqual(BizSubscription.objects.filter(business=biz).count(), 1)

    def test_v2_and_legacy_coexist_simultaneously(self):
        """Both models can exist for the same business without conflict."""
        biz = _make_business()
        legacy = _attach_legacy(biz, plan='start', status='active')
        v2 = _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        self.assertIsNotNone(legacy.pk)
        self.assertIsNotNone(v2.pk)
        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, 'v2')  # V2 wins
