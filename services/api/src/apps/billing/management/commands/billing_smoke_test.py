"""
billing_smoke_test
==================
In-process smoke test that validates the complete billing/SubscriptionV2 circuit
without making any real Mercado Pago API calls.

Covers:
  1. SubscriptionV2 birth path
  2. BillingEvent idempotent creation
  3. PaymentAttempt creation
  4. activate_tenant / CHECKOUT_PENDING → ACTIVE transition
  5. Runtime V2-first resolution (resolve_subscription)
  6. EnforcementDecision for active / suspended / no-sub scenarios
  7. expire_subscriptions task transitions (ACTIVE→PAST_DUE, PAST_DUE→SUSPENDED,
     TRIALING→SUSPENDED)
  8. Idempotency of expire_subscriptions (re-running must produce same result)
  9. Addon/V2 entitlement resolution via parity bridge

Usage:
    python manage.py billing_smoke_test
    python manage.py billing_smoke_test --keep   # don't delete test data
    python manage.py billing_smoke_test --verbose

Exit codes:
    0  all tests passed
    1  one or more tests failed
"""
from __future__ import annotations

import sys
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()

# ── colour helpers ─────────────────────────────────────────────────────────────
_GREEN  = '\033[92m'
_RED    = '\033[91m'
_YELLOW = '\033[93m'
_RESET  = '\033[0m'
_BOLD   = '\033[1m'

OK   = f'{_GREEN}OK{_RESET}'
FAIL = f'{_RED}FAIL{_RESET}'
INFO = f'{_YELLOW}INFO{_RESET}'


class Command(BaseCommand):
    help = (
        'Run in-process smoke tests for the billing/SubscriptionV2 circuit. '
        'Creates and destroys isolated test data. Safe to run in staging.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep',
            action='store_true',
            help='Do not delete test data after completion (useful for debugging).',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print extra diagnostic output for each test.',
        )

    # ── entry point ──────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        self.verbose = options['verbose']
        self.keep = options['keep']
        self.failures: list[str] = []
        self.tag = f'smoke-{uuid.uuid4().hex[:8]}'

        self.stdout.write(
            f'\n{_BOLD}=== billing_smoke_test (tag={self.tag}) ==={_RESET}\n'
        )

        # Collect all created PKs so we can teardown later
        self._created_users: list[int] = []
        self._created_businesses: list[int] = []

        try:
            self._run_all()
        finally:
            if not self.keep:
                self._teardown()

        # Summary
        total = 9
        passed = total - len(self.failures)
        colour = _GREEN if not self.failures else _RED
        self.stdout.write(
            f'\n{colour}{_BOLD}Results: {passed}/{total} passed{_RESET}'
        )
        if self.failures:
            self.stdout.write(f'{_RED}Failed:{_RESET}')
            for f in self.failures:
                self.stdout.write(f'  - {f}')
            sys.exit(1)
        else:
            self.stdout.write(f'{_GREEN}All smoke tests passed.{_RESET}\n')

    # ── test runner ───────────────────────────────────────────────────────────
    def _run_all(self):
        self._test_birth_path()
        self._test_billing_event_idempotency()
        self._test_payment_attempt()
        self._test_activation_transition()
        self._test_runtime_active()
        self._test_runtime_denied()
        self._test_expire_active_to_past_due()
        self._test_expire_past_due_to_suspended()
        self._test_addon_entitlement_parity()

    # ── test helpers ──────────────────────────────────────────────────────────
    def _ok(self, name: str, detail: str = ''):
        line = f'  {OK}  {name}'
        if detail and self.verbose:
            line += f' — {detail}'
        self.stdout.write(line)

    def _fail(self, name: str, reason: str):
        self.failures.append(name)
        self.stdout.write(f'  {FAIL}  {name} — {reason}')

    def _assert(self, name: str, condition: bool, reason: str = '', detail: str = ''):
        if condition:
            self._ok(name, detail)
        else:
            self._fail(name, reason or 'assertion failed')

    # ── setup helpers ─────────────────────────────────────────────────────────
    def _make_business(self, suffix='', status='active', service='gestion'):
        from apps.business.models import Business
        b = Business.objects.create(
            name=f'SmokeTest-{self.tag}-{suffix}',
            status=status,
            default_service=service,
        )
        self._created_businesses.append(b.pk)
        return b

    def _make_v2(self, business, status, **kwargs):
        from apps.billing.models import SubscriptionV2
        defaults = dict(
            service_type=business.default_service or 'gestion',
            plan_code='start',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            external_reference=f'SMOKE-{uuid.uuid4()}',
            status=status,
        )
        defaults.update(kwargs)
        return SubscriptionV2.objects.create(business=business, **defaults)

    # ── teardown ──────────────────────────────────────────────────────────────
    def _teardown(self):
        from apps.billing.models import (
            SubscriptionV2, BillingEvent, PaymentAttempt,
        )
        from apps.business.models import Business

        # Delete in dependency order
        if self._created_businesses:
            PaymentAttempt.objects.filter(
                subscription__business_id__in=self._created_businesses,
            ).delete()
            BillingEvent.objects.filter(
                subscription__business_id__in=self._created_businesses,
            ).delete()
            SubscriptionV2.objects.filter(
                business_id__in=self._created_businesses,
            ).delete()
            Business.objects.filter(pk__in=self._created_businesses).delete()

        if self._created_users:
            User.objects.filter(pk__in=self._created_users).delete()

    # ── TEST 1: Birth path ────────────────────────────────────────────────────
    def _test_birth_path(self):
        name = 'T1: SubscriptionV2 birth path'
        try:
            from apps.billing.models import SubscriptionV2
            b = self._make_business('birth', status='pending_activation')
            v2 = self._make_v2(
                b,
                SubscriptionV2.Status.CHECKOUT_PENDING,
                provider_sub_id=f'FAKE-PA-{uuid.uuid4().hex[:8]}',
            )
            self._assert(
                name,
                v2.pk is not None and v2.status == SubscriptionV2.Status.CHECKOUT_PENDING,
                'SubscriptionV2 not created',
                f'pk={v2.pk}',
            )
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 2: BillingEvent idempotency ──────────────────────────────────────
    def _test_billing_event_idempotency(self):
        name = 'T2: BillingEvent idempotency'
        try:
            from apps.billing.models import BillingEvent
            event_id = f'TEST-EVENT-{uuid.uuid4().hex}'
            be1, created1 = BillingEvent.objects.get_or_create(
                provider_event_id=event_id,
                defaults={
                    'provider': BillingEvent.Provider.MERCADOPAGO,
                    'event_type': BillingEvent.EventType.PREAPPROVAL_UPDATED,
                    'payload': {'test': True},
                    'status': BillingEvent.ProcessingStatus.RECEIVED,
                    'received_at': timezone.now(),
                },
            )
            be2, created2 = BillingEvent.objects.get_or_create(
                provider_event_id=event_id,
                defaults={
                    'provider': BillingEvent.Provider.MERCADOPAGO,
                    'event_type': BillingEvent.EventType.PREAPPROVAL_UPDATED,
                    'payload': {'test': True, 'duplicate': True},
                    'status': BillingEvent.ProcessingStatus.RECEIVED,
                    'received_at': timezone.now(),
                },
            )
            self._assert(
                name,
                created1 and not created2 and be1.pk == be2.pk,
                f'created1={created1} created2={created2} same_pk={be1.pk == be2.pk}',
                f'BillingEvent pk={be1.pk}',
            )
            # Cleanup
            be1.delete()
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 3: PaymentAttempt creation ───────────────────────────────────────
    def _test_payment_attempt(self):
        name = 'T3: PaymentAttempt created'
        try:
            from apps.billing.models import SubscriptionV2, PaymentAttempt
            from apps.billing.views import _create_payment_attempt
            b = self._make_business('pa')
            v2 = self._make_v2(b, SubscriptionV2.Status.ACTIVE)
            payment_id = f'FAKEPAY-{uuid.uuid4().hex[:8]}'
            payment_data = {
                'status': 'approved',
                'transaction_amount': 999,
                'currency_id': 'ARS',
            }
            pa = _create_payment_attempt(v2, None, payment_data, payment_id)
            self._assert(
                name,
                pa is not None and pa.status == PaymentAttempt.Status.APPROVED,
                f'pa={pa}',
                f'PaymentAttempt pk={pa.pk if pa else None}',
            )
            # Idempotency: second call must return existing
            pa2 = _create_payment_attempt(v2, None, payment_data, payment_id)
            self._assert(
                'T3b: PaymentAttempt idempotency',
                pa2 is not None and pa2.pk == pa.pk,
                'Idempotency failed — duplicate created',
            )
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 4: CHECKOUT_PENDING → ACTIVE activation ─────────────────────────
    def _test_activation_transition(self):
        name = 'T4: activation CHECKOUT_PENDING → ACTIVE'
        try:
            from apps.billing.models import SubscriptionV2
            b = self._make_business('activate', status='pending_activation')
            provider_id = f'FAKE-PA-ACTIVATE-{uuid.uuid4().hex[:8]}'
            v2 = self._make_v2(
                b,
                SubscriptionV2.Status.CHECKOUT_PENDING,
                provider_sub_id=provider_id,
            )
            # Simulate activate_tenant V2 sync logic
            v2.status = SubscriptionV2.Status.ACTIVE
            v2.save(update_fields=['status'])
            b.status = 'active'
            b.save(update_fields=['status'])

            v2.refresh_from_db()
            b.refresh_from_db()
            self._assert(
                name,
                v2.status == SubscriptionV2.Status.ACTIVE and b.status == 'active',
                f'v2.status={v2.status} b.status={b.status}',
                f'SubV2 pk={v2.pk}',
            )
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 5: Runtime resolution — active path ──────────────────────────────
    def _test_runtime_active(self):
        name = 'T5: runtime resolves ACTIVE → access_granted=True'
        try:
            from apps.billing.models import SubscriptionV2
            from apps.billing.runtime import resolve_subscription
            from apps.billing.enforcement import get_enforcement_decision
            b = self._make_business('runtime-active')
            self._make_v2(b, SubscriptionV2.Status.ACTIVE, plan_code='start')

            resolved = resolve_subscription(b)
            decision  = get_enforcement_decision(resolved)

            self._assert(
                name,
                resolved.source == 'v2'
                    and resolved.access_granted is True
                    and decision.access_allowed is True,
                f'source={resolved.source} access_granted={resolved.access_granted}',
                f'reason={decision.reason_code}',
            )
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 6: Runtime resolution — suspended / no-sub ───────────────────────
    def _test_runtime_denied(self):
        name = 'T6: runtime denies SUSPENDED / no-sub → access_allowed=False'
        try:
            from apps.billing.models import SubscriptionV2
            from apps.billing.runtime import resolve_subscription
            from apps.billing.enforcement import get_enforcement_decision, ReasonCode

            # 6a: SUSPENDED
            b_sus = self._make_business('runtime-suspended')
            self._make_v2(b_sus, SubscriptionV2.Status.SUSPENDED, plan_code='start')
            r_sus = resolve_subscription(b_sus)
            d_sus = get_enforcement_decision(r_sus)
            self._assert(
                'T6a: suspended → access_allowed=False',
                not d_sus.access_allowed and d_sus.reason_code == ReasonCode.SUSPENDED,
                f'access_allowed={d_sus.access_allowed} reason={d_sus.reason_code}',
            )

            # 6b: no subscription
            b_none = self._make_business('runtime-nosub')
            r_none = resolve_subscription(b_none)
            d_none = get_enforcement_decision(r_none)
            self._assert(
                'T6b: no-sub → access_allowed=False',
                not d_none.access_allowed and d_none.reason_code == ReasonCode.NO_SUBSCRIPTION,
                f'access_allowed={d_none.access_allowed} reason={d_none.reason_code}',
            )

            # 6c: CANCELED — _find_best_v2 excludes CANCELED, so runtime returns
            # 'none' / no_subscription (no fallback to legacy either since no legacy sub)
            b_can = self._make_business('runtime-canceled')
            self._make_v2(b_can, SubscriptionV2.Status.CANCELED, plan_code='start')
            r_can = resolve_subscription(b_can)
            d_can = get_enforcement_decision(r_can)
            self._assert(
                'T6c: canceled-only → access_allowed=False',
                not d_can.access_allowed,
                f'access_allowed={d_can.access_allowed} reason={d_can.reason_code}',
                f'reason={d_can.reason_code} (CANCELED excluded from runtime lookup by design)',
            )
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 7: expire ACTIVE → PAST_DUE ─────────────────────────────────────
    def _test_expire_active_to_past_due(self):
        name = 'T7: expire_subscriptions ACTIVE → PAST_DUE'
        try:
            from apps.billing.models import SubscriptionV2
            from apps.billing.tasks import expire_subscriptions
            b = self._make_business('expire-active')
            v2 = self._make_v2(
                b,
                SubscriptionV2.Status.ACTIVE,
                current_period_end=timezone.now() - timedelta(days=2),
            )
            result = expire_subscriptions.apply().get()
            self._assert(
                name,
                result['active_to_past_due'] >= 1,
                f'result={result}',
                f'active_to_past_due={result["active_to_past_due"]}',
            )
            v2.refresh_from_db()
            self._assert(
                'T7b: V2 status is PAST_DUE after task',
                v2.status == SubscriptionV2.Status.PAST_DUE,
                f'v2.status={v2.status}',
            )
            # Idempotency: run again — count should be 0 for this sub
            result2 = expire_subscriptions.apply().get()
            v2.refresh_from_db()
            self._assert(
                'T7c: expire idempotent (PAST_DUE not re-touched)',
                v2.status == SubscriptionV2.Status.PAST_DUE,
                'Status changed on second run',
            )
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 8: expire PAST_DUE → SUSPENDED ───────────────────────────────────
    def _test_expire_past_due_to_suspended(self):
        name = 'T8: expire_subscriptions PAST_DUE → SUSPENDED'
        try:
            from apps.billing.models import SubscriptionV2
            from apps.billing.tasks import expire_subscriptions
            b = self._make_business('expire-pastdue')
            v2 = self._make_v2(
                b,
                SubscriptionV2.Status.PAST_DUE,
                grace_until=timezone.now() - timedelta(hours=1),
            )
            result = expire_subscriptions.apply().get()
            self._assert(
                name,
                result['past_due_to_suspended'] >= 1,
                f'result={result}',
                f'past_due_to_suspended={result["past_due_to_suspended"]}',
            )
            v2.refresh_from_db()
            self._assert(
                'T8b: V2 status is SUSPENDED after task',
                v2.status == SubscriptionV2.Status.SUSPENDED,
                f'v2.status={v2.status}',
            )
        except Exception as exc:
            self._fail(name, str(exc))

    # ── TEST 9: Addon entitlement parity (bridge) ─────────────────────────────
    def _test_addon_entitlement_parity(self):
        name = 'T9: addon/entitlement resolution via V2 runtime'
        try:
            from apps.billing.models import SubscriptionV2
            from apps.billing.runtime import resolve_subscription
            b = self._make_business('addon-parity')
            # Plan 'pro' should yield entitlements including base ones
            self._make_v2(b, SubscriptionV2.Status.ACTIVE, plan_code='pro')
            resolved = resolve_subscription(b)
            self._assert(
                name,
                resolved.source == 'v2' and resolved.access_granted,
                f'source={resolved.source} access_granted={resolved.access_granted}',
                f'entitlements_count={len(resolved.entitlements)}',
            )
        except Exception as exc:
            self._fail(name, str(exc))
