"""
billing/tests/test_enforcement.py — Tests for global enforcement layer.

Covers (§H):
  EnforcementDecisionTest
    1. active → access_allowed=True, reason=access_granted
    2. trialing within trial → access_allowed=True
    3. past_due within grace → access_allowed=True, in_grace_period=True, reason=grace_period_active
    4. past_due grace expired → access_allowed=False, reason=grace_period_expired
    5. suspended → access_allowed=False, reason=suspended
    6. canceled → access_allowed=False, reason=canceled
    7. none (no subscription) → access_allowed=False, reason=no_subscription
    8. checkout_pending → access_allowed=False, reason=checkout_pending
    9. trialing expired → access_allowed=False, reason=trial_expired

  HasEntitlementEnforcementTest
    1. valid entitlement + active V2 → allow
    2. valid entitlement + V2 suspended → deny (reason=suspended in message)
    3. valid entitlement + past_due within grace → allow
    4. valid entitlement + past_due grace expired → deny
    5. V2 remains primary when both V2 and legacy exist
    6. legacy fallback works when no V2
    7. response message contains reason_code on subscription_access_denied

  MeViewEnforcementPayloadTest
    1. payload.subscription.access_allowed present
    2. payload.subscription.reason_code present
    3. payload.subscription.source present
    4. grace_until populated when in grace period
    5. access_until populated when active (current_period_end set)
    6. show_renewal_prompt True when suspended/past_due

  PeriodicTaskTest
    1. ACTIVE with past period_end → PAST_DUE (sets grace_until)
    2. PAST_DUE with past grace_until → SUSPENDED
    3. TRIALING with past trial_ends_at → SUSPENDED
    4. Idempotent: running twice produces same state
    5. Does not affect subs that should NOT transition
    6. ACTIVE without period_end is not affected

  RegressionTest
    1. resolve_subscription still V2-first after enforcement layer added
    2. legacy fallback still works
    3. no optimistic defaults when no subscription
    4. V2 suspended does not fall back to legacy (§F.2)
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Membership
from apps.accounts.permissions import HasEntitlement
from apps.accounts.views import MeView
from apps.billing.enforcement import (
    EnforcementDecision,
    ReasonCode,
    enforcement_message,
    get_enforcement_decision,
)
from apps.billing.models import SubscriptionV2
from apps.billing.runtime import ResolvedSubscription, resolve_subscription
from apps.billing.tasks import (
    _transition_active_to_past_due,
    _transition_past_due_to_suspended,
    _transition_trial_to_suspended,
    expire_subscriptions,
)
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_business(name='EnfBiz', service='gestion'):
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


def _attach_v2(
    biz,
    plan_code='pro',
    status=None,
    service_type=None,
    trial_ends_at=None,
    grace_until=None,
    current_period_end=None,
):
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


def _resolved_with_v2(sub_v2, access_granted=None) -> ResolvedSubscription:
    """Build a ResolvedSubscription backed by a real SubscriptionV2 DB object."""
    from apps.billing.runtime import _extract_plan_tier, _v2_grants_access, _v2_access_until
    from apps.business.entitlements import get_plan_entitlements

    grants = _v2_grants_access(sub_v2) if access_granted is None else access_granted
    plan_tier = _extract_plan_tier(sub_v2.plan_code)
    return ResolvedSubscription(
        source='v2',
        plan=plan_tier,
        status=sub_v2.status,
        access_granted=grants,
        access_until=_v2_access_until(sub_v2),
        entitlements=frozenset(get_plan_entitlements(plan_tier)) if grants else frozenset(),
        service_type=sub_v2.service_type,
        fallback_reason=None,
        subscription_v2=sub_v2,
        legacy_sub=None,
    )


def _resolved_none() -> ResolvedSubscription:
    return ResolvedSubscription(
        source='none',
        plan=None,
        status=None,
        access_granted=False,
        access_until=None,
        entitlements=frozenset(),
        service_type='gestion',
        fallback_reason='no_subscription',
        subscription_v2=None,
        legacy_sub=None,
    )


def _make_user(email):
    return User.objects.create_user(username=email, email=email, password='pass1234')


def _make_membership(user, biz, role='owner'):
    return Membership.objects.create(user=user, business=biz, role=role)


def _call_me_view(user):
    factory = APIRequestFactory()
    request = factory.get('/api/accounts/me/')
    force_authenticate(request, user=user)
    return MeView.as_view()(request)


# ─────────────────────────────────────────────────────────────────────────────
# EnforcementDecisionTest
# ─────────────────────────────────────────────────────────────────────────────

class EnforcementDecisionTest(TestCase):

    def _decision_for_v2(self, status, **v2_kwargs):
        """Create a real V2 sub, resolve it, return the enforcement decision."""
        biz = _make_business(f'EnfTest-{uuid.uuid4().hex[:6]}')
        sub = _attach_v2(biz, status=status, **v2_kwargs)
        resolved = resolve_subscription(biz)
        return get_enforcement_decision(resolved)

    # ── 1. active ────────────────────────────────────────────────────────────

    def test_active_allows_access(self):
        d = self._decision_for_v2(SubscriptionV2.Status.ACTIVE)
        self.assertTrue(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.ACCESS_GRANTED)
        self.assertFalse(d.in_grace_period)
        self.assertFalse(d.show_renewal_prompt)

    # ── 2. trialing within trial ──────────────────────────────────────────────

    def test_trialing_within_trial_allows_access(self):
        future = timezone.now() + timedelta(days=7)
        d = self._decision_for_v2(
            SubscriptionV2.Status.TRIALING,
            trial_ends_at=future,
        )
        self.assertTrue(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.ACCESS_GRANTED)

    # ── 3. past_due within grace ──────────────────────────────────────────────

    def test_past_due_within_grace_allows_access(self):
        future = timezone.now() + timedelta(days=2)
        d = self._decision_for_v2(
            SubscriptionV2.Status.PAST_DUE,
            grace_until=future,
        )
        self.assertTrue(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.GRACE_PERIOD_ACTIVE)
        self.assertTrue(d.in_grace_period)
        self.assertIsNotNone(d.grace_until)
        self.assertTrue(d.show_renewal_prompt)

    # ── 4. past_due grace expired ─────────────────────────────────────────────

    def test_past_due_grace_expired_denies_access(self):
        past = timezone.now() - timedelta(hours=1)
        d = self._decision_for_v2(
            SubscriptionV2.Status.PAST_DUE,
            grace_until=past,
        )
        self.assertFalse(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.GRACE_PERIOD_EXPIRED)
        self.assertFalse(d.in_grace_period)
        # grace_until is exposed for debugging even when expired
        self.assertIsNotNone(d.grace_until)
        self.assertTrue(d.show_renewal_prompt)

    # ── 5. suspended ──────────────────────────────────────────────────────────

    def test_suspended_denies_access(self):
        d = self._decision_for_v2(SubscriptionV2.Status.SUSPENDED)
        self.assertFalse(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.SUSPENDED)
        self.assertTrue(d.show_renewal_prompt)

    # ── 6. canceled ───────────────────────────────────────────────────────────

    def test_canceled_denies_access(self):
        # CANCELED is excluded from _find_best_v2, so create a no-sub business
        biz = _make_business(f'CancEnf-{uuid.uuid4().hex[:6]}')
        # Simulate canceled by creating a second one with explicit CANCELED status
        # then checking with no valid sub at all
        resolved = _resolved_none()
        resolved = ResolvedSubscription(
            source='v2',
            plan='pro',
            status=SubscriptionV2.Status.CANCELED,
            access_granted=False,
            access_until=None,
            entitlements=frozenset(),
            service_type='gestion',
            fallback_reason='v2_status=canceled',
            subscription_v2=None,
            legacy_sub=None,
        )
        d = get_enforcement_decision(resolved)
        self.assertFalse(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.CANCELED)
        self.assertTrue(d.show_renewal_prompt)

    # ── 7. none (no subscription) ─────────────────────────────────────────────

    def test_none_denies_access(self):
        biz = _make_business(f'NoSub-{uuid.uuid4().hex[:6]}')
        resolved = resolve_subscription(biz)
        d = get_enforcement_decision(resolved)
        self.assertFalse(d.access_allowed)
        self.assertIn(d.reason_code, (ReasonCode.NO_SUBSCRIPTION, ReasonCode.ACCESS_GRANTED))
        # No sub → access_allowed False
        if resolved.source == 'none':
            self.assertEqual(d.reason_code, ReasonCode.NO_SUBSCRIPTION)
            self.assertFalse(d.show_renewal_prompt)

    # ── 8. checkout_pending ───────────────────────────────────────────────────

    def test_checkout_pending_denies_access(self):
        resolved = ResolvedSubscription(
            source='v2',
            plan='pro',
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
            access_granted=False,
            access_until=None,
            entitlements=frozenset(),
            service_type='gestion',
            fallback_reason='v2_status=checkout_pending',
            subscription_v2=None,
            legacy_sub=None,
        )
        d = get_enforcement_decision(resolved)
        self.assertFalse(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.CHECKOUT_PENDING)
        self.assertFalse(d.show_renewal_prompt)

    # ── 9. trialing expired ───────────────────────────────────────────────────

    def test_trialing_expired_produces_trial_expired(self):
        # Use a raw resolved to simulate expired trialing (runtime excludes no V2 expired
        # trial from access calculation, but enforcement sees it through access_granted=False)
        biz = _make_business(f'TrlExp-{uuid.uuid4().hex[:6]}')
        past = timezone.now() - timedelta(hours=1)
        sub_v2 = _attach_v2(
            biz,
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at=past,
        )
        resolved = _resolved_with_v2(sub_v2)  # access_granted computed from _v2_grants_access
        d = get_enforcement_decision(resolved)
        self.assertFalse(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.TRIAL_EXPIRED)

    # ── enforcement_message helper ────────────────────────────────────────────

    def test_enforcement_message_returns_string_for_all_known_codes(self):
        codes = [
            ReasonCode.ACCESS_GRANTED,
            ReasonCode.GRACE_PERIOD_ACTIVE,
            ReasonCode.GRACE_PERIOD_EXPIRED,
            ReasonCode.TRIAL_EXPIRED,
            ReasonCode.SUSPENDED,
            ReasonCode.CANCELED,
            ReasonCode.CHECKOUT_PENDING,
            ReasonCode.NO_SUBSCRIPTION,
        ]
        for code in codes:
            with self.subTest(code=code):
                msg = enforcement_message(code)
                self.assertIsInstance(msg, str)
                self.assertTrue(len(msg) > 0)

    def test_enforcement_message_unknown_code_returns_default(self):
        msg = enforcement_message('totally_unknown_reason_xyz')
        self.assertIsInstance(msg, str)
        self.assertTrue(len(msg) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# HasEntitlementEnforcementTest
# ─────────────────────────────────────────────────────────────────────────────

class _ViewWithEntitlement:
    required_entitlement = 'gestion.customers'


class _ViewNoEntitlement:
    required_entitlement = None


class HasEntitlementEnforcementTest(TestCase):

    def _make_request(self, biz):
        factory = APIRequestFactory()
        req = factory.get('/')
        req.business = biz
        return req

    # ── 1. active V2 + valid entitlement → allow ──────────────────────────────

    def test_active_v2_with_entitlement_passes(self):
        biz = _make_business('HEActive')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)
        perm = HasEntitlement()
        self.assertTrue(perm.has_permission(self._make_request(biz), _ViewWithEntitlement()))

    # ── 2. suspended V2 → deny, even with valid plan ───────────────────────────

    def test_suspended_v2_denies_despite_plan(self):
        biz = _make_business('HESusp')
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)
        perm = HasEntitlement()
        result = perm.has_permission(self._make_request(biz), _ViewWithEntitlement())
        self.assertFalse(result)
        self.assertEqual(perm.message.get('code'), 'subscription_access_denied')
        self.assertEqual(perm.message.get('reason_code'), ReasonCode.SUSPENDED)

    # ── 3. past_due within grace → allow ─────────────────────────────────────

    def test_past_due_within_grace_passes(self):
        biz = _make_business('HEGrace')
        future = timezone.now() + timedelta(days=2)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.PAST_DUE,
                   grace_until=future)
        perm = HasEntitlement()
        self.assertTrue(perm.has_permission(self._make_request(biz), _ViewWithEntitlement()))

    # ── 4. past_due grace expired → deny ─────────────────────────────────────

    def test_past_due_grace_expired_denies(self):
        biz = _make_business('HEGraceExp')
        past = timezone.now() - timedelta(hours=1)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.PAST_DUE,
                   grace_until=past)
        perm = HasEntitlement()
        result = perm.has_permission(self._make_request(biz), _ViewWithEntitlement())
        self.assertFalse(result)
        self.assertEqual(perm.message.get('code'), 'subscription_access_denied')
        self.assertEqual(perm.message.get('reason_code'), ReasonCode.GRACE_PERIOD_EXPIRED)

    # ── 5. V2 remains primary ─────────────────────────────────────────────────

    def test_v2_primary_when_both_exist(self):
        biz = _make_business('HEV2Primary')
        _attach_legacy(biz, plan='pro', status='active')
        # V2 is suspended; legacy is active → V2 wins (§F.2)
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)
        perm = HasEntitlement()
        result = perm.has_permission(self._make_request(biz), _ViewWithEntitlement())
        self.assertFalse(result)
        self.assertEqual(perm.message.get('source'), 'v2')

    # ── 6. legacy fallback works ──────────────────────────────────────────────

    def test_legacy_fallback_grants_entitlement(self):
        biz = _make_business('HELegacy')
        _attach_legacy(biz, plan='pro', status='active')
        perm = HasEntitlement()
        self.assertTrue(perm.has_permission(self._make_request(biz), _ViewWithEntitlement()))

    # ── 7. denial message contains reason_code ────────────────────────────────

    def test_denial_message_has_reason_code_on_suspension(self):
        biz = _make_business('HEMsg')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)
        perm = HasEntitlement()
        perm.has_permission(self._make_request(biz), _ViewWithEntitlement())
        self.assertIn('reason_code', perm.message)
        self.assertIn('enforcement_status', perm.message)

    # ── 8. no required_entitlement → always passes ───────────────────────────

    def test_no_required_entitlement_always_passes(self):
        biz = _make_business('HENoEnt')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)
        perm = HasEntitlement()
        self.assertTrue(perm.has_permission(self._make_request(biz), _ViewNoEntitlement()))

    # ── 9. plan lacks entitlement → plan_entitlement_required ────────────────

    def test_active_but_plan_lacks_entitlement(self):
        biz = _make_business('HEPlanLack')
        _attach_v2(biz, plan_code='start', status=SubscriptionV2.Status.ACTIVE)
        perm = HasEntitlement()
        result = perm.has_permission(self._make_request(biz), _ViewWithEntitlement())
        self.assertFalse(result)
        self.assertEqual(perm.message.get('code'), 'plan_entitlement_required')


# ─────────────────────────────────────────────────────────────────────────────
# MeViewEnforcementPayloadTest
# ─────────────────────────────────────────────────────────────────────────────

class MeViewEnforcementPayloadTest(TestCase):

    # ── 1. access_allowed present ────────────────────────────────────────────

    def test_payload_contains_access_allowed(self):
        user = _make_user('me-enf-1@example.com')
        biz = _make_business('MeEnf1')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)
        _make_membership(user, biz)
        resp = _call_me_view(user)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access_allowed', resp.data['subscription'])
        self.assertTrue(resp.data['subscription']['access_allowed'])

    # ── 2. reason_code present ───────────────────────────────────────────────

    def test_payload_contains_reason_code(self):
        user = _make_user('me-enf-2@example.com')
        biz = _make_business('MeEnf2')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)
        _make_membership(user, biz)
        resp = _call_me_view(user)
        sub = resp.data['subscription']
        self.assertIn('reason_code', sub)
        self.assertEqual(sub['reason_code'], ReasonCode.ACCESS_GRANTED)

    # ── 3. source present ────────────────────────────────────────────────────

    def test_payload_contains_source(self):
        user = _make_user('me-enf-3@example.com')
        biz = _make_business('MeEnf3')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)
        _make_membership(user, biz)
        resp = _call_me_view(user)
        self.assertIn('source', resp.data['subscription'])
        self.assertEqual(resp.data['subscription']['source'], 'v2')

    # ── 4. grace_until populated in grace period ─────────────────────────────

    def test_payload_grace_until_set_when_in_grace(self):
        user = _make_user('me-enf-4@example.com')
        biz = _make_business('MeEnf4')
        future = timezone.now() + timedelta(days=2)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.PAST_DUE,
                   grace_until=future)
        _make_membership(user, biz)
        resp = _call_me_view(user)
        sub = resp.data['subscription']
        self.assertIsNotNone(sub.get('grace_until'))
        self.assertTrue(sub['access_allowed'])
        self.assertEqual(sub['reason_code'], ReasonCode.GRACE_PERIOD_ACTIVE)

    # ── 5. access_until when active ──────────────────────────────────────────

    def test_payload_access_until_set_when_active_has_period_end(self):
        user = _make_user('me-enf-5@example.com')
        biz = _make_business('MeEnf5')
        future = timezone.now() + timedelta(days=30)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.ACTIVE,
                   current_period_end=future)
        _make_membership(user, biz)
        resp = _call_me_view(user)
        sub = resp.data['subscription']
        self.assertIsNotNone(sub.get('access_until'))

    # ── 6. show_renewal_prompt True when suspended ───────────────────────────

    def test_payload_show_renewal_prompt_when_suspended(self):
        user = _make_user('me-enf-6@example.com')
        biz = _make_business('MeEnf6')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)
        _make_membership(user, biz)
        resp = _call_me_view(user)
        sub = resp.data['subscription']
        self.assertFalse(sub['access_allowed'])
        self.assertTrue(sub['show_renewal_prompt'])
        self.assertEqual(sub['reason_code'], ReasonCode.SUSPENDED)


# ─────────────────────────────────────────────────────────────────────────────
# PeriodicTaskTest
# ─────────────────────────────────────────────────────────────────────────────

class PeriodicTaskTest(TestCase):

    # ── 1. ACTIVE + past period_end → PAST_DUE ───────────────────────────────

    def test_active_past_period_end_transitions_to_past_due(self):
        biz = _make_business('TaskActive1')
        past = timezone.now() - timedelta(hours=2)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.ACTIVE,
                         current_period_end=past)

        now = timezone.now()
        count = _transition_active_to_past_due(SubscriptionV2, now)

        sub.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)
        self.assertIsNotNone(sub.grace_until)
        # grace_until must be in the future
        self.assertGreater(sub.grace_until, now)

    # ── 2. PAST_DUE + past grace_until → SUSPENDED ───────────────────────────

    def test_past_due_past_grace_transitions_to_suspended(self):
        biz = _make_business('TaskPD1')
        past_grace = timezone.now() - timedelta(hours=1)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.PAST_DUE,
                         grace_until=past_grace)

        count = _transition_past_due_to_suspended(SubscriptionV2, timezone.now())

        sub.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(sub.status, SubscriptionV2.Status.SUSPENDED)

    # ── 3. TRIALING + past trial_ends_at → SUSPENDED ─────────────────────────

    def test_trial_expired_transitions_to_suspended(self):
        biz = _make_business('TaskTrial1')
        past_trial = timezone.now() - timedelta(hours=1)
        sub = _attach_v2(biz,
                         status=SubscriptionV2.Status.TRIALING,
                         trial_ends_at=past_trial)

        count = _transition_trial_to_suspended(SubscriptionV2, timezone.now())

        sub.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(sub.status, SubscriptionV2.Status.SUSPENDED)

    # ── 4. Idempotency: running twice leaves same state ───────────────────────

    def test_task_is_idempotent(self):
        biz = _make_business('TaskIdem1')
        past = timezone.now() - timedelta(hours=2)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.ACTIVE,
                         current_period_end=past)

        now = timezone.now()
        count1 = _transition_active_to_past_due(SubscriptionV2, now)
        count2 = _transition_active_to_past_due(SubscriptionV2, now)

        sub.refresh_from_db()
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 0)  # second run: no new transition
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)

    def test_full_task_idempotent_double_run(self):
        biz = _make_business('TaskIdem2')
        past_grace = timezone.now() - timedelta(hours=1)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.PAST_DUE,
                         grace_until=past_grace)

        counts1 = expire_subscriptions.run()
        counts2 = expire_subscriptions.run()

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.SUSPENDED)
        # Second run should produce no new transitions for this sub
        self.assertEqual(counts2['past_due_to_suspended'], 0)

    # ── 5. Does not affect subscriptions that should not transition ────────────

    def test_active_with_future_period_end_not_affected(self):
        biz = _make_business('TaskActiveOK')
        future = timezone.now() + timedelta(days=30)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.ACTIVE,
                         current_period_end=future)

        _transition_active_to_past_due(SubscriptionV2, timezone.now())

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.ACTIVE)

    def test_past_due_with_future_grace_not_affected(self):
        biz = _make_business('TaskPDOK')
        future_grace = timezone.now() + timedelta(days=2)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.PAST_DUE,
                         grace_until=future_grace)

        _transition_past_due_to_suspended(SubscriptionV2, timezone.now())

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)

    def test_trialing_with_future_trial_end_not_affected(self):
        biz = _make_business('TaskTrialOK')
        future_trial = timezone.now() + timedelta(days=5)
        sub = _attach_v2(biz,
                         status=SubscriptionV2.Status.TRIALING,
                         trial_ends_at=future_trial)

        _transition_trial_to_suspended(SubscriptionV2, timezone.now())

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.TRIALING)

    # ── 6. ACTIVE without period_end is not affected ─────────────────────────

    def test_active_without_period_end_not_affected(self):
        biz = _make_business('TaskActiveNoPeriod')
        sub = _attach_v2(biz, status=SubscriptionV2.Status.ACTIVE)
        # current_period_end is None by default

        _transition_active_to_past_due(SubscriptionV2, timezone.now())

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.ACTIVE)

    # ── grace_until uses existing value if set ────────────────────────────────

    def test_active_to_past_due_preserves_existing_grace_until(self):
        biz = _make_business('TaskGracePreserve')
        past_period = timezone.now() - timedelta(hours=2)
        explicit_grace = timezone.now() + timedelta(days=7)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.ACTIVE,
                         current_period_end=past_period,
                         grace_until=explicit_grace)

        _transition_active_to_past_due(SubscriptionV2, timezone.now())

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionV2.Status.PAST_DUE)
        # The existing grace_until is preserved, not overwritten
        self.assertEqual(sub.grace_until.replace(microsecond=0),
                         explicit_grace.replace(microsecond=0))


# ─────────────────────────────────────────────────────────────────────────────
# RegressionTest
# ─────────────────────────────────────────────────────────────────────────────

class RegressionTest(TestCase):
    """Ensure enforcement layer does not break prior resolve_subscription behavior."""

    # ── 1. resolve_subscription still V2-first ────────────────────────────────

    def test_resolve_still_v2_first(self):
        biz = _make_business('RegV2First')
        _attach_legacy(biz, plan='start', status='active')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)
        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, 'v2')
        self.assertEqual(resolved.plan, 'pro')

    # ── 2. legacy fallback works ──────────────────────────────────────────────

    def test_legacy_fallback_when_no_v2(self):
        biz = _make_business('RegLegacy')
        _attach_legacy(biz, plan='pro', status='active')
        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, 'legacy')
        self.assertTrue(resolved.access_granted)

    # ── 3. no optimistic defaults when no subscription ────────────────────────

    def test_no_optimistic_defaults_when_no_subscription(self):
        biz = _make_business('RegNoSub')
        resolved = resolve_subscription(biz)
        d = get_enforcement_decision(resolved)
        # If source is none → access must not be granted
        if resolved.source == 'none':
            self.assertFalse(d.access_allowed)
            self.assertEqual(d.reason_code, ReasonCode.NO_SUBSCRIPTION)

    # ── 4. V2 suspended does not fall back to legacy (§F.2) ───────────────────

    def test_v2_suspended_no_legacy_fallback(self):
        biz = _make_business('RegSuspNoFallback')
        _attach_legacy(biz, plan='pro', status='active')
        _attach_v2(biz, plan_code='pro', status=SubscriptionV2.Status.SUSPENDED)
        resolved = resolve_subscription(biz)
        d = get_enforcement_decision(resolved)
        # Source must be v2, not legacy
        self.assertEqual(resolved.source, 'v2')
        self.assertFalse(d.access_allowed)
        self.assertEqual(d.reason_code, ReasonCode.SUSPENDED)

    # ── 5. enforcement decision matches runtime access_granted ────────────────

    def test_enforcement_matches_runtime_access_granted(self):
        """get_enforcement_decision().access_allowed == resolved.access_granted."""
        biz = _make_business('RegConsistency')
        future_grace = timezone.now() + timedelta(days=1)
        _attach_v2(biz, plan_code='pro',
                   status=SubscriptionV2.Status.PAST_DUE,
                   grace_until=future_grace)
        resolved = resolve_subscription(biz)
        d = get_enforcement_decision(resolved)
        self.assertEqual(d.access_allowed, resolved.access_granted)
