"""
Tests for V2-first migration of build_business_context() and has_entitlement().

Covers:
  BuildBusinessContextV2FirstTest
    1. Context uses V2 plan when V2 active
    2. Fallback to legacy plan when no V2
    3. No subscription → status='none', no 'active' injection
    4. V2 suspended → status reflects V2, not legacy
    5. _subscription_source key present and correct

  HasEntitlementV2FirstTest
    1. Entitlement granted with V2 valid
    2. Entitlement via fallback to legacy
    3. Entitlement denied when no subscription
    4. Entitlement denied when V2 suspended (even if legacy active)
    5. Entitlement denied when V2 plan doesn't include it (even if legacy plan does)

  RegressionTests
    1. Legacy flows still work with controlled fallback
    2. business.Subscription still coexists
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import SubscriptionV2
from apps.business.context import build_business_context
from apps.business.entitlements import get_plan_entitlements, has_entitlement
from apps.business.models import Business, BusinessPlan, Subscription as BizSubscription


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_business(name='CtxBiz', service='gestion'):
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
               grace_until=None, trial_ends_at=None):
    return SubscriptionV2.objects.create(
        business=biz,
        service_type=service_type or biz.default_service,
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MANUAL,
        external_reference=f'SUB-{uuid.uuid4()}',
        status=status or SubscriptionV2.Status.ACTIVE,
        grace_until=grace_until,
        trial_ends_at=trial_ends_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# BuildBusinessContextV2FirstTest
# ─────────────────────────────────────────────────────────────────────────────

class BuildBusinessContextV2FirstTest(TestCase):

    def test_context_uses_v2_plan_when_v2_active(self):
        biz = _make_business()
        _attach_legacy(biz, plan='start')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        ctx = build_business_context(biz)

        self.assertEqual(ctx['plan'], 'pro')
        self.assertEqual(ctx['status'], SubscriptionV2.Status.ACTIVE)
        self.assertEqual(ctx['_subscription_source'], 'v2')

    def test_context_fallback_to_legacy_plan(self):
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')

        ctx = build_business_context(biz)

        self.assertEqual(ctx['plan'], 'pro')
        self.assertEqual(ctx['status'], 'active')
        self.assertEqual(ctx['_subscription_source'], 'legacy')

    def test_no_subscription_no_active_status_injected(self):
        """
        When no subscription exists, status must NOT default to 'active'.
        This was the dangerous default in the old implementation.
        """
        biz = _make_business()

        ctx = build_business_context(biz)

        self.assertEqual(ctx['_subscription_source'], 'none')
        # Status must not pretend active
        self.assertNotEqual(ctx['status'], 'active')
        self.assertEqual(ctx['status'], 'none')

    def test_no_subscription_plan_is_starter_display_fallback(self):
        """
        When no subscription exists, plan falls back to STARTER for display
        purposes only.  Access is controlled by has_entitlement() returning False.
        """
        biz = _make_business()

        ctx = build_business_context(biz)

        self.assertEqual(ctx['plan'], BusinessPlan.STARTER)
        self.assertEqual(ctx['_subscription_source'], 'none')

    def test_v2_suspended_status_reflects_v2_not_legacy(self):
        """
        V2 suspended + legacy active → context status must reflect V2 state.
        The dangerous old default would have given 'active' via legacy.
        """
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)

        ctx = build_business_context(biz)

        self.assertEqual(ctx['_subscription_source'], 'v2')
        self.assertEqual(ctx['status'], SubscriptionV2.Status.SUSPENDED)

    def test_subscription_source_key_always_present(self):
        """_subscription_source is always in the returned context."""
        biz = _make_business()

        ctx = build_business_context(biz)

        self.assertIn('_subscription_source', ctx)
        self.assertIn(ctx['_subscription_source'], ('v2', 'legacy', 'none'))

    def test_backward_compat_keys_always_present(self):
        """All original context keys are preserved."""
        biz = _make_business()
        _attach_legacy(biz, plan='start', status='active')

        ctx = build_business_context(biz)

        for key in ('plan', 'status', 'features', 'enabled_services',
                    'default_service', 'service'):
            with self.subTest(key=key):
                self.assertIn(key, ctx)

    def test_v2_features_use_plan_tier_flags(self):
        """V2 source computes feature flags from the plan tier."""
        biz = _make_business()
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        ctx = build_business_context(biz)

        # Pro plan features should be True
        self.assertTrue(ctx['features'].get('customers'))
        self.assertTrue(ctx['features'].get('reports'))
        self.assertEqual(ctx['_subscription_source'], 'v2')

    def test_legacy_features_use_subscription_including_addons(self):
        """Legacy source passes subscription to feature_flags_for_subscription."""
        biz = _make_business()
        _attach_legacy(biz, plan='start', status='active')

        ctx = build_business_context(biz)

        # Should have used feature_flags_for_subscription (no crash)
        self.assertEqual(ctx['_subscription_source'], 'legacy')
        self.assertIsInstance(ctx['features'], dict)


# ─────────────────────────────────────────────────────────────────────────────
# HasEntitlementV2FirstTest
# ─────────────────────────────────────────────────────────────────────────────

class HasEntitlementV2FirstTest(TestCase):

    def test_plan_catalog_includes_pos_offline_contingency_entitlement(self):
        self.assertIn(
            'gestion.restaurant_pos_offline_contingency',
            get_plan_entitlements('business'),
        )
        self.assertIn(
            'gestion.restaurant_pos_offline_contingency',
            get_plan_entitlements('enterprise'),
        )

    def test_entitlement_granted_with_v2_valid(self):
        """V2 active with pro plan → pro entitlements are granted."""
        biz = _make_business()
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        self.assertTrue(has_entitlement(biz, 'gestion.customers'))
        self.assertTrue(has_entitlement(biz, 'gestion.cash'))
        self.assertTrue(has_entitlement(biz, 'gestion.reports'))

    def test_pos_offline_contingency_denied_without_entitlement(self):
        biz = _make_business()
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        self.assertFalse(has_entitlement(biz, 'gestion.restaurant_pos_offline_contingency'))

    def test_pos_offline_contingency_granted_with_business_tier(self):
        biz = _make_business()
        _attach_v2(biz, plan_code='business', status=SubscriptionV2.Status.ACTIVE)

        self.assertTrue(has_entitlement(biz, 'gestion.restaurant_pos_offline_contingency'))

    def test_entitlement_fallback_to_legacy_when_no_v2(self):
        """No V2 → falls back to legacy plan entitlements."""
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')

        self.assertTrue(has_entitlement(biz, 'gestion.customers'))
        self.assertTrue(has_entitlement(biz, 'gestion.reports'))

    def test_entitlement_denied_no_subscription(self):
        """No subscription at all → always False, no defaults."""
        biz = _make_business()

        self.assertFalse(has_entitlement(biz, 'gestion.products'))
        self.assertFalse(has_entitlement(biz, 'gestion.customers'))

    def test_entitlement_denied_v2_suspended_even_if_legacy_active(self):
        """
        §F.2: V2 suspended + legacy active → entitlement denied.
        V2 takes precedence over legacy; suspended V2 must not be bypassed.
        """
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)

        self.assertFalse(has_entitlement(biz, 'gestion.customers'))
        self.assertFalse(has_entitlement(biz, 'gestion.products'))

    def test_entitlement_denied_v2_plan_does_not_include_it(self):
        """
        V2 start plan (active) + legacy pro active → entitlement from pro
        denied because V2 start doesn't include it.
        """
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='start', status=SubscriptionV2.Status.ACTIVE)

        # V2 start doesn't include gestion.customers (pro-only)
        self.assertFalse(has_entitlement(biz, 'gestion.customers'))
        # V2 start includes gestion.products
        self.assertTrue(has_entitlement(biz, 'gestion.products'))

    def test_entitlement_denied_v2_past_due_grace_expired(self):
        """past_due V2 with expired grace window → access denied."""
        biz = _make_business()
        past_grace = timezone.now() - timedelta(hours=1)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.PAST_DUE,
                   grace_until=past_grace)

        self.assertFalse(has_entitlement(biz, 'gestion.customers'))

    def test_entitlement_granted_v2_past_due_within_grace(self):
        """past_due V2 with active grace window → access granted."""
        biz = _make_business()
        future_grace = timezone.now() + timedelta(days=3)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.PAST_DUE,
                   grace_until=future_grace)

        self.assertTrue(has_entitlement(biz, 'gestion.customers'))

    def test_entitlement_granted_v2_trialing(self):
        """Trialing V2 within window → access granted."""
        biz = _make_business()
        future = timezone.now() + timedelta(days=14)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.TRIALING,
                   trial_ends_at=future)

        self.assertTrue(has_entitlement(biz, 'gestion.customers'))

    def test_entitlement_start_plan_baseline(self):
        """V2 start plan — only start-tier entitlements are present."""
        biz = _make_business()
        _attach_v2(biz, plan_code='start', status=SubscriptionV2.Status.ACTIVE)

        self.assertTrue(has_entitlement(biz, 'gestion.products'))
        self.assertTrue(has_entitlement(biz, 'gestion.sales_basic'))
        # Pro-only should be False
        self.assertFalse(has_entitlement(biz, 'gestion.customers'))
        self.assertFalse(has_entitlement(biz, 'gestion.cash'))

    def test_legacy_canceled_denies_entitlement(self):
        """Legacy canceled → no access via legacy fallback."""
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='canceled')

        self.assertFalse(has_entitlement(biz, 'gestion.customers'))


# ─────────────────────────────────────────────────────────────────────────────
# Regression tests
# ─────────────────────────────────────────────────────────────────────────────

class RegressionV2FirstTest(TestCase):

    def test_legacy_subscription_model_still_exists(self):
        """business.Subscription is not removed; can be created and queried."""
        biz = _make_business()
        sub = _attach_legacy(biz, plan='pro', status='active')

        self.assertIsNotNone(sub.pk)
        fetched = BizSubscription.objects.get(business=biz)
        self.assertEqual(fetched.plan, 'pro')

    def test_legacy_flow_still_works_via_fallback(self):
        """
        Post-migration legacy-only businesses remain functional via fallback.
        """
        biz = _make_business()
        _attach_legacy(biz, plan='business', status='active')

        ctx = build_business_context(biz)
        self.assertEqual(ctx['_subscription_source'], 'legacy')

        # Multi-branch entitlement is in 'business' plan
        self.assertTrue(has_entitlement(biz, 'gestion.multi_branch'))

    def test_nothing_breaks_in_absence_of_v2(self):
        """Full context + entitlement path with only legacy present — no exceptions."""
        biz = _make_business()
        _attach_legacy(biz, plan='pro', status='active')

        ctx = build_business_context(biz)
        granted = has_entitlement(biz, 'gestion.reports')

        self.assertIsNotNone(ctx)
        self.assertTrue(granted)
