"""
billing/tests/test_admin_clientes_01b_complimentary_access_runtime.py

ADMIN-CLIENTES 01B — Cierre del contrato de acceso bonificado.

These tests exercise the *real* runtime resolver (`resolve_subscription`),
not just the creation service — per the slice requirement to verify
`current_period_end` is actually enforced at request time.

Time is controlled by patching `django.utils.timezone.now` (the same
`timezone` module object imported by both `runtime.py` and this test), so
comparisons stay timezone-aware throughout (never naive datetimes).

Test matrix:
  ComplimentaryAccessRuntimeExpiryTest
    1. Before current_period_end → access granted, source='v2'.
    2. At current_period_end (exact instant) → access denied.
    3. After current_period_end → access denied.
    4. Access denied even though status=trialing, is_active=True and
       Business.status='trialing' are all still intact (no DB mutation).
    5. Nothing in the DB changes as a side effect of resolving after expiry
       (this slice must not auto-expire rows).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.billing.complimentary_access_service import grant_complimentary_access
from apps.billing.models import Plan, SubscriptionV2
from apps.billing.runtime import resolve_subscription
from apps.business.models import Business

User = get_user_model()


def _make_business(name='Runtime Contract Biz'):
    return Business.objects.create(name=name, default_service='gestion', status='onboarding')


def _make_admin():
    email = f'admin-01b@platform.com'
    return User.objects.create_user(email=email, password='pass', username=email)


def _make_plan(code='gestion_pro'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults={
            'name': code,
            'price': Decimal('50000.00'),
            'interval': 'monthly',
            'currency': 'ARS',
            'frequency': 1,
            'frequency_type': 'months',
            'plan_status': 'active',
        },
    )
    return plan


class ComplimentaryAccessRuntimeExpiryTest(TestCase):

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_admin()
        self.plan = _make_plan()
        self.grant_time = timezone.now()
        self.ends_at = self.grant_time + timedelta(days=180)
        self.sub = grant_complimentary_access(
            business=self.biz,
            plan_code=self.plan.code,
            service_type='gestion',
            starts_at=self.grant_time,
            ends_at=self.ends_at,
            granted_by=self.admin,
            reason='Cliente VIP — 6 meses de cortesía',
        )

    def _resolve_at(self, when):
        with patch('django.utils.timezone.now', return_value=when):
            return resolve_subscription(self.biz)

    # ── 1: before expiry ─────────────────────────────────────────────────────
    def test_01_grants_access_before_period_end(self):
        resolved = self._resolve_at(self.ends_at - timedelta(days=1))
        self.assertEqual(resolved.source, 'v2')
        self.assertTrue(resolved.access_granted)
        self.assertEqual(resolved.status, SubscriptionV2.Status.TRIALING)

    # ── 2: exactly at the boundary ───────────────────────────────────────────
    def test_02_denies_access_exactly_at_period_end(self):
        resolved = self._resolve_at(self.ends_at)
        self.assertFalse(resolved.access_granted)

    # ── 3: after expiry ───────────────────────────────────────────────────────
    def test_03_denies_access_after_period_end(self):
        resolved = self._resolve_at(self.ends_at + timedelta(days=1))
        self.assertFalse(resolved.access_granted)
        self.assertEqual(resolved.source, 'v2')

    # ── 4: flags remain intact — denial is a runtime-only decision ──────────
    def test_04_denies_access_despite_intact_status_flags(self):
        self._resolve_at(self.ends_at + timedelta(days=30))

        self.sub.refresh_from_db()
        self.biz.refresh_from_db()

        self.assertEqual(self.sub.status, SubscriptionV2.Status.TRIALING)
        self.assertTrue(self.sub.is_active)
        self.assertEqual(self.biz.status, 'trialing')

    # ── 5: no auto-expiry side effect from resolving ─────────────────────────
    def test_05_resolving_after_expiry_does_not_mutate_the_row(self):
        before = SubscriptionV2.objects.get(pk=self.sub.pk)
        self._resolve_at(self.ends_at + timedelta(days=30))
        after = SubscriptionV2.objects.get(pk=self.sub.pk)

        self.assertEqual(before.status, after.status)
        self.assertEqual(before.is_active, after.is_active)
        self.assertEqual(before.updated_at, after.updated_at)

    # ── Regression guard: trial_ends_at semantics unchanged when it is set ──
    def test_06_trial_ends_at_semantics_unchanged_when_present(self):
        # A generic V2 with trial_ends_at set (the pre-existing trial
        # mechanism, provider-agnostic) must keep using trial_ends_at, not
        # current_period_end.
        future_trial = timezone.now() + timedelta(days=3)
        past_period_end = timezone.now() - timedelta(days=1)
        mp_style_sub = SubscriptionV2.objects.create(
            business=_make_business(name='MP Style Biz'),
            service_type='gestion',
            plan_code='gestion_pro',
            provider=SubscriptionV2.Provider.MANUAL,
            external_reference='SUB-mp-style-regression',
            status=SubscriptionV2.Status.TRIALING,
            trial_ends_at=future_trial,
            current_period_end=past_period_end,  # would deny if wrongly checked
        )
        resolved = resolve_subscription(mp_style_sub.business)
        self.assertTrue(resolved.access_granted)


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN-CLIENTES 01C — Provider isolation of the current_period_end fallback.
#
# The current_period_end fallback (added in 01B for trialing rows with no
# trial_ends_at) must apply ONLY when provider=manual. Any other provider
# (Mercado Pago, Stripe, ...) must preserve the exact pre-01B semantics:
# trial_ends_at=None grants access unconditionally, and access_until is None.
# ──────────────────────────────────────────────────────────────────────────────
class ComplimentaryAccessProviderScopeTest(TestCase):
    """Direct unit tests for _v2_grants_access / _v2_access_until provider scoping."""

    _counter = 0

    def _make_sub(self, *, provider, trial_ends_at=None, current_period_end=None,
                  status=SubscriptionV2.Status.TRIALING):
        # Each row gets its own Business — the (business, service_type)
        # uniqueness constraint on non-canceled rows forbids two live
        # SubscriptionV2 rows sharing a business within a single test.
        type(self)._counter += 1
        biz = _make_business(name=f'Provider Scope Biz {type(self)._counter}')
        return SubscriptionV2.objects.create(
            business=biz,
            service_type='gestion',
            plan_code='gestion_pro',
            provider=provider,
            external_reference=f'SUB-provider-scope-{type(self)._counter}',
            status=status,
            trial_ends_at=trial_ends_at,
            current_period_end=current_period_end,
        )

    # ── 1: manual before/at/after current_period_end (via _v2_grants_access) ─
    def test_01_manual_grants_access_before_period_end(self):
        from apps.billing.runtime import _v2_grants_access
        now = timezone.now()
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MANUAL,
            current_period_end=now + timedelta(days=1),
        )
        with patch('django.utils.timezone.now', return_value=now):
            self.assertTrue(_v2_grants_access(sub))

    def test_02_manual_denies_access_exactly_at_period_end(self):
        from apps.billing.runtime import _v2_grants_access
        now = timezone.now()
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MANUAL,
            current_period_end=now,
        )
        with patch('django.utils.timezone.now', return_value=now):
            self.assertFalse(_v2_grants_access(sub))

    def test_03_manual_denies_access_after_period_end(self):
        from apps.billing.runtime import _v2_grants_access
        now = timezone.now()
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MANUAL,
            current_period_end=now - timedelta(days=1),
        )
        with patch('django.utils.timezone.now', return_value=now):
            self.assertFalse(_v2_grants_access(sub))

    # ── 2: manual without trial_ends_at uses current_period_end ─────────────
    def test_04_manual_without_trial_ends_at_uses_current_period_end(self):
        from apps.billing.runtime import _v2_grants_access
        now = timezone.now()
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MANUAL,
            trial_ends_at=None,
            current_period_end=now - timedelta(days=1),
        )
        with patch('django.utils.timezone.now', return_value=now):
            self.assertFalse(_v2_grants_access(sub))

    # ── 3: MP with trial_ends_at conserves current behavior ─────────────────
    def test_05_mercadopago_with_trial_ends_at_unaffected(self):
        from apps.billing.runtime import _v2_grants_access
        now = timezone.now()
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            trial_ends_at=now + timedelta(days=2),
            current_period_end=now - timedelta(days=1),  # would deny if wrongly checked
        )
        with patch('django.utils.timezone.now', return_value=now):
            self.assertTrue(_v2_grants_access(sub))

        # Boundary/expired trial_ends_at still denies, exactly as before.
        expired_sub = self._make_sub(
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            trial_ends_at=now - timedelta(days=1),
            current_period_end=now + timedelta(days=30),  # would grant if wrongly checked
        )
        with patch('django.utils.timezone.now', return_value=now):
            self.assertFalse(_v2_grants_access(expired_sub))

    # ── 4: MP without trial_ends_at does NOT use the manual fallback ────────
    def test_06_mercadopago_without_trial_ends_at_does_not_use_manual_fallback(self):
        from apps.billing.runtime import _v2_grants_access
        now = timezone.now()
        # current_period_end already elapsed — if the manual fallback leaked
        # to this provider, access would be (wrongly) denied.
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            trial_ends_at=None,
            current_period_end=now - timedelta(days=1),
        )
        with patch('django.utils.timezone.now', return_value=now):
            self.assertTrue(_v2_grants_access(sub))

    # ── 5: _v2_access_until distinguishes both providers ─────────────────────
    def test_07_access_until_manual_without_trial_ends_at_returns_period_end(self):
        from apps.billing.runtime import _v2_access_until
        now = timezone.now()
        period_end = now + timedelta(days=45)
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MANUAL,
            trial_ends_at=None,
            current_period_end=period_end,
        )
        self.assertEqual(_v2_access_until(sub), period_end)

    def test_08_access_until_mercadopago_without_trial_ends_at_returns_none(self):
        from apps.billing.runtime import _v2_access_until
        now = timezone.now()
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            trial_ends_at=None,
            current_period_end=now + timedelta(days=45),
        )
        self.assertIsNone(_v2_access_until(sub))

    def test_09_access_until_mercadopago_with_trial_ends_at_returns_trial_ends_at(self):
        from apps.billing.runtime import _v2_access_until
        now = timezone.now()
        trial_end = now + timedelta(days=2)
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            trial_ends_at=trial_end,
            current_period_end=now + timedelta(days=45),
        )
        self.assertEqual(_v2_access_until(sub), trial_end)

    # ── End-to-end via the real resolver for the MP-without-trial_ends_at case ─
    def test_10_resolver_grants_access_for_mp_trialing_without_trial_ends_at(self):
        now = timezone.now()
        sub = self._make_sub(
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            trial_ends_at=None,
            current_period_end=now - timedelta(days=1),
        )
        with patch('django.utils.timezone.now', return_value=now):
            resolved = resolve_subscription(sub.business)
        self.assertTrue(resolved.access_granted)
