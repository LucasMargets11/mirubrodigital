"""
Tests for Phase 2B – SubscriptionV2 birth path, PaymentAttempt population,
webhook correlation hardening, and regression guards.

Covers:
  1. StartSubscriptionView: creates SubscriptionV2 at birth, idempotency on retry
  2. CommercialCheckoutView (paid path): ensures SubscriptionV2 created before MP redirect
  3. apply_subscription_change (free path): creates SubscriptionV2 if missing
  4. Webhook (subscription_preapproval): correlates against V2 by provider_sub_id (not heuristic)
  5. Webhook (payment): creates PaymentAttempt linked to SubscriptionV2
  6. Regression: legacy flows unbroken, BillingEvent still idempotent,
     business.Subscription still the runtime source of truth
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.billing.models import (
    BillingEvent,
    MpCheckoutSession,
    PaymentAttempt,
    PaymentEvent,
    Plan,
    Subscription as LegacyBillingSubscription,
    SubscriptionIntent,
    SubscriptionV2,
)
from apps.billing.services.commercial.apply import apply_subscription_change
from apps.billing.views import MercadoPagoWebhookView, _resolve_subscriptionv2
from apps.accounts.models import Membership
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Network guard: no test in this module may reach Mercado Pago (or any host).
# The MP SDK sends every request through requests.Session.request; any real
# attempt is recorded and rejected so the test fails closed.
# ─────────────────────────────────────────────────────────────────────────────

class _NetworkGuard:
    def __init__(self):
        self.target_calls = []
        self._patcher = patch('requests.sessions.Session.request', side_effect=self._reject)

    def _reject(self, method, url, *args, **kwargs):
        self.target_calls.append((method, url))
        raise AssertionError(f'Real HTTP request attempted in tests: {method} {url}')

    def start(self):
        self.target_calls.clear()
        self._patcher.start()

    def stop(self):
        self._patcher.stop()


_network_guard = _NetworkGuard()


def setUpModule():
    _network_guard.start()


def tearDownModule():
    _network_guard.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_business(name="TestBiz", service="gestion", status="pending_activation"):
    biz = Business.objects.create(name=name, default_service=service, status=status)
    BizSubscription.objects.create(business=biz, plan="start", status="active")
    return biz


def _make_plan(code="plan_birth_001"):
    return Plan.objects.create(
        code=code,
        name="Test Plan Birth",
        price=Decimal("100.00"),
        interval="monthly",
        mp_preapproval_plan_id="mp_plan_id_123",
    )


def _attach_v2(biz, plan_code="start", status=None, provider_sub_id=None):
    return SubscriptionV2.objects.create(
        business=biz,
        service_type=biz.default_service,
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=provider_sub_id,
        external_reference=f"SUB-{uuid.uuid4()}",
        status=status or SubscriptionV2.Status.ACTIVE,
    )


def _make_webhook_view():
    return MercadoPagoWebhookView()


def _make_intent(biz, user, plan, status='created'):
    return SubscriptionIntent.objects.create(
        tenant=biz, user=user, plan_code=plan.code, status=status,
    )


def _make_legacy_billing_sub(biz, preapproval_id=None):
    return LegacyBillingSubscription.objects.create(
        business=biz,
        plan_type='bundle',
        billing_period='monthly',
        status='active',
        mp_preapproval_id=preapproval_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. StartSubscriptionView — secure, idempotent checkout start
# ─────────────────────────────────────────────────────────────────────────────

INVALID_CREDENTIALS = {'error': 'Credenciales inválidas.'}


def _fake_mp_plan(**kwargs):
    """Stand-in for MercadoPagoService.create_preapproval_plan: unique id per call."""
    plan_id = f'preapp-plan-{uuid.uuid4()}'
    url = f'https://mp.example.com/checkout/{plan_id}'
    return {'id': plan_id, 'init_point': url, 'sandbox_init_point': url}


class StartSubscriptionViewContractTest(TestCase):
    """
    Contract of POST /billing/start-subscription:
      - 201 when a checkout session is created (one MP plan creation);
      - 200 when the open session for the same user + business + plan is
        reused (same checkout_session_id / init_point, no MP call);
      - 401 with a generic message when an existing account does not
        authenticate (wrong password, or no usable password), with no writes
        and no MP call.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.plan = _make_plan("plan_start_001")
        # checkout_session_service imports MercadoPagoService locally at call
        # time, so the mock must replace the symbol at its source module.
        patcher = patch('apps.billing.mp_service.MercadoPagoService')
        self.MockMP = patcher.start()
        self.addCleanup(patcher.stop)
        self.mp = self.MockMP.return_value
        self.mp.create_preapproval_plan.side_effect = _fake_mp_plan

    def tearDown(self):
        self.assertEqual(_network_guard.target_calls, [], 'Real HTTP request attempted')

    # ── helpers ───────────────────────────────────────────────────────────────

    def _post(self, **overrides):
        from apps.billing.views import StartSubscriptionView
        payload = {
            'email': 'newuser@test.com',
            'password': 'Passw0rd!',
            'business_name': 'My Biz',
            'plan_code': self.plan.code,
        }
        payload.update(overrides)
        request = self.factory.post(
            '/api/v1/billing/start-subscription',
            data=json.dumps(payload),
            content_type='application/json',
        )
        return StartSubscriptionView.as_view()(request)

    def _mp_calls(self):
        return self.mp.create_preapproval_plan.call_count

    def _existing_user(self, email='owner@test.com', password='Passw0rd!', usable=True):
        user = User.objects.create_user(username=email, email=email, password=password)
        if not usable:
            user.set_unusable_password()
            user.save(update_fields=['password'])
        biz = Business.objects.create(name=f'Biz {email}', default_service='gestion', status='onboarding')
        Membership.objects.create(user=user, business=biz, role='owner')
        return user, biz

    def _snapshot(self, user):
        user.refresh_from_db()
        return {
            'users': User.objects.count(),
            'businesses': Business.objects.count(),
            'memberships': Membership.objects.count(),
            'intents': SubscriptionIntent.objects.count(),
            'sessions': list(MpCheckoutSession.objects.values_list('id', 'status', 'updated_at')),
            'v2': SubscriptionV2.objects.count(),
            'password': user.password,
            'last_login': user.last_login,
        }

    def _assert_no_subscription_before_payment(self, business, intent_email=None):
        """
        Birth invariants: nothing is subscribed until MP confirms payment.
        Only the new-user path creates a SubscriptionIntent; pass its email
        to also check that intent.
        """
        business.refresh_from_db()
        self.assertEqual(business.status, 'onboarding')
        self.assertFalse(SubscriptionV2.objects.filter(business=business).exists())
        self.assertFalse(LegacyBillingSubscription.objects.filter(business=business).exists())
        if intent_email is None:
            return
        intent = SubscriptionIntent.objects.get(user__email=intent_email, tenant=business)
        self.assertEqual(intent.status, 'created')
        self.assertIsNone(intent.subscription_v2_id)

    # ── new users ─────────────────────────────────────────────────────────────

    def test_new_user_returns_201_and_creates_one_session(self):
        response = self._post()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(self.MockMP.called, 'MercadoPagoService was not mocked')
        self.assertEqual(self._mp_calls(), 1)
        self.assertFalse(response.data['reused'])

        session = MpCheckoutSession.objects.get()
        business = Business.objects.get(name='My Biz')
        self.assertEqual(response.data['checkout_session_id'], str(session.id))
        self.assertEqual(response.data['init_point'], session.provider_checkout_url)
        self.assertEqual(session.tenant, business)
        self.assertEqual(session.status, MpCheckoutSession.Status.CHECKOUT_CREATED)
        intent = SubscriptionIntent.objects.get(user__email='newuser@test.com')
        self.assertEqual(intent.tenant, business)
        self.assertEqual(intent.mp_init_point, session.provider_checkout_url)
        self._assert_no_subscription_before_payment(business, 'newuser@test.com')

    def test_new_user_retry_same_intent_returns_200_and_same_session(self):
        r1 = self._post()
        r2 = self._post()

        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertTrue(r2.data['reused'])
        self.assertEqual(r2.data['checkout_session_id'], r1.data['checkout_session_id'])
        self.assertEqual(r2.data['init_point'], r1.data['init_point'])
        self.assertEqual(self._mp_calls(), 1)
        self.assertEqual(MpCheckoutSession.objects.count(), 1)
        self.assertEqual(User.objects.filter(email='newuser@test.com').count(), 1)
        self.assertEqual(Business.objects.filter(name='My Biz').count(), 1)
        self.assertEqual(SubscriptionIntent.objects.count(), 1)
        self._assert_no_subscription_before_payment(
            Business.objects.get(name='My Biz'), 'newuser@test.com',
        )

    # ── existing users ────────────────────────────────────────────────────────

    def test_existing_user_correct_password_first_checkout_returns_201(self):
        user, biz = self._existing_user()

        r1 = self._post(email=user.email, password='Passw0rd!')
        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertEqual(self._mp_calls(), 1)
        session = MpCheckoutSession.objects.get()
        self.assertEqual((session.user, session.tenant), (user, biz))
        self._assert_no_subscription_before_payment(biz)

        r2 = self._post(email=user.email, password='Passw0rd!')
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(r2.data['checkout_session_id'], r1.data['checkout_session_id'])
        self.assertEqual(self._mp_calls(), 1)
        self.assertEqual(Business.objects.count(), 1)
        self._assert_no_subscription_before_payment(biz)

    def test_existing_user_wrong_password_returns_401_without_side_effects(self):
        user, _ = self._existing_user()
        before = self._snapshot(user)

        response = self._post(email=user.email, password='wrong-password')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, INVALID_CREDENTIALS)
        self.assertEqual(self._mp_calls(), 0)
        self.assertEqual(self._snapshot(user), before)

    def test_wrong_password_does_not_expose_open_session(self):
        r1 = self._post()
        response = self._post(password='wrong-password')

        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, INVALID_CREDENTIALS)
        self.assertEqual(self._mp_calls(), 1)

    def test_account_without_usable_password_is_rejected(self):
        """Google-only accounts (unusable password) cannot be taken over here."""
        user, _ = self._existing_user(email='google@test.com', usable=False)
        before = self._snapshot(user)

        for password in ('Passw0rd!', '!'):
            response = self._post(email=user.email, password=password)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.data, INVALID_CREDENTIALS)

        self.assertEqual(self._mp_calls(), 0)
        self.assertEqual(self._snapshot(user), before)

    # ── session reuse boundaries ──────────────────────────────────────────────

    def test_failed_session_does_not_block_new_checkout(self):
        r1 = self._post()
        MpCheckoutSession.objects.update(status=MpCheckoutSession.Status.FAILED)

        r2 = self._post()

        self.assertEqual(r2.status_code, 201, r2.data)
        self.assertNotEqual(r2.data['checkout_session_id'], r1.data['checkout_session_id'])
        self.assertEqual(self._mp_calls(), 2)
        self.assertEqual(
            MpCheckoutSession.objects.get(id=r1.data['checkout_session_id']).status,
            MpCheckoutSession.Status.FAILED,
        )

    def test_expired_session_does_not_block_new_checkout(self):
        r1 = self._post()
        MpCheckoutSession.objects.update(expires_at=timezone.now() - timedelta(minutes=1))

        r2 = self._post()

        self.assertEqual(r2.status_code, 201, r2.data)
        self.assertNotEqual(r2.data['checkout_session_id'], r1.data['checkout_session_id'])
        self.assertEqual(self._mp_calls(), 2)
        self.assertEqual(
            MpCheckoutSession.objects.get(id=r1.data['checkout_session_id']).status,
            MpCheckoutSession.Status.EXPIRED,
        )

    def test_different_plan_is_not_reused(self):
        """The plan (and therefore the service) is part of the reuse scope."""
        user, _ = self._existing_user()
        other_plan = _make_plan("plan_start_002")

        r_a = self._post(email=user.email)
        r_b = self._post(email=user.email, plan_code=other_plan.code)
        r_a2 = self._post(email=user.email)

        self.assertEqual((r_a.status_code, r_b.status_code, r_a2.status_code), (201, 201, 200))
        self.assertNotEqual(r_a.data['checkout_session_id'], r_b.data['checkout_session_id'])
        self.assertEqual(r_a2.data['checkout_session_id'], r_a.data['checkout_session_id'])
        self.assertEqual(self._mp_calls(), 2)

    def test_sessions_are_not_reused_across_users(self):
        r1 = self._post(email='first@test.com', business_name='First Biz')
        r2 = self._post(email='second@test.com', business_name='Second Biz')

        self.assertEqual((r1.status_code, r2.status_code), (201, 201))
        self.assertNotEqual(r1.data['checkout_session_id'], r2.data['checkout_session_id'])
        self.assertEqual(self._mp_calls(), 2)

    def test_sessions_are_not_reused_across_businesses(self):
        from apps.billing.checkout_session_service import start_checkout
        user, biz_a = self._existing_user()
        biz_b = Business.objects.create(name='Second Branch', default_service='gestion', status='onboarding')

        res_a = start_checkout(user=user, tenant=biz_a, plan_code=self.plan.code)
        res_b = start_checkout(user=user, tenant=biz_b, plan_code=self.plan.code)

        self.assertFalse(res_a['reused'])
        self.assertFalse(res_b['reused'])
        self.assertNotEqual(res_a['checkout_session_id'], res_b['checkout_session_id'])
        self.assertEqual(self._mp_calls(), 2)


class StartCheckoutConcurrencyTest(TransactionTestCase):
    """
    Two simultaneous starts for the same (user, business, plan) must create a
    single MpCheckoutSession and a single MP plan. The partial unique
    constraint uq_checkout_session_open_per_tenant_user_plan makes the loser's
    INSERT wait for the winner's transaction (which includes the MP call) and
    then fail; start_checkout recovers by returning the winner's session.
    """
    # Same workaround as apps/appointments/tests/test_appointments_concurrency.py:
    # the unmanaged treasury.ExpenseTemplate FK breaks the default TRUNCATE
    # flush; setting available_apps enables allow_cascade.
    available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

    def test_concurrent_starts_create_one_session_and_one_mp_plan(self):
        from apps.billing.checkout_session_service import start_checkout
        user = User.objects.create_user(username='conc@test.com', email='conc@test.com', password='Passw0rd!')
        biz = Business.objects.create(name='Conc Biz', default_service='gestion', status='onboarding')
        plan = _make_plan("plan_conc_001")

        mp_calls = []

        def slow_fake_mp_plan(**kwargs):
            mp_calls.append(kwargs.get('external_reference'))
            time.sleep(0.5)  # keep the winner's transaction open
            return _fake_mp_plan(**kwargs)

        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker():
            try:
                barrier.wait(timeout=10)
                results.append(start_checkout(user=user, tenant=biz, plan_code=plan.code))
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)
            finally:
                connection.close()

        with patch('apps.billing.mp_service.MercadoPagoService') as MockMP:
            MockMP.return_value.create_preapproval_plan.side_effect = slow_fake_mp_plan
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        self.assertFalse(any(t.is_alive() for t in threads), 'worker thread hung')
        self.assertEqual(errors, [])
        self.assertEqual(len(mp_calls), 1)
        self.assertEqual(MpCheckoutSession.objects.count(), 1)
        self.assertEqual(len({r['checkout_session_id'] for r in results}), 1)
        self.assertEqual(sorted(r['reused'] for r in results), [False, True])
        self.assertEqual(_network_guard.target_calls, [])


# ─────────────────────────────────────────────────────────────────────────────
# 2. CommercialCheckoutView (paid path) — SubscriptionV2 ensured before MP redirect
# ─────────────────────────────────────────────────────────────────────────────

class CommercialCheckoutBirthPathTest(TestCase):
    """CommercialCheckoutView must ensure SubscriptionV2 exists when redirecting to MP."""

    def setUp(self):
        self.biz = _make_business(name="CommBiz", service="gestion", status="active")
        self.user = User.objects.create_user(
            email='owner.comm@test.com', username='owner.comm@test.com', password='pass'
        )
        from apps.accounts.models import Membership
        Membership.objects.create(user=self.user, business=self.biz, role='owner')
        self.factory = APIRequestFactory()

    def _post(self, payload, mock_mp=True):
        from apps.billing.commercial_views import CommercialCheckoutView
        request = self.factory.post(
            '/api/v1/billing/commercial/checkout/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        request.user = self.user
        request.business = self.biz
        view = CommercialCheckoutView.as_view()
        if mock_mp:
            mock_pref = {'id': 'pref_123', 'init_point': 'https://mp.example.com/checkout'}
            # MercadoPagoService is imported locally inside the method → patch at source
            with patch('apps.billing.mp_service.MercadoPagoService') as MockMP:
                MockMP.return_value.create_preference.return_value = mock_pref
                with patch('apps.billing.services.commercial.preview.preview_subscription_change') as mock_prev:
                    mock_prev.return_value = {
                        'line_items': [{'description': 'Pro Plan', 'quantity': 1, 'unit_price': 29900, 'total': 29900}],
                        'total_now': 29900,
                        'total_recurring': 29900,
                        'requires_checkout': True,
                        'is_upgrade': True,
                        'is_downgrade': False,
                        'validation_errors': [],
                        'change_summary': 'Upgrade to pro',
                    }
                    return view(request)
        return view(request)

    def test_ensures_v2_created_on_paid_checkout(self):
        self.assertEqual(
            SubscriptionV2.objects.filter(business=self.biz).count(), 0,
            "No V2 before checkout",
        )
        response = self._post({'plan_code': 'pro', 'billing_cycle': 'monthly'})

        # If checkout was created (200 or 500 due to MP mock), V2 must exist
        v2_count = SubscriptionV2.objects.filter(business=self.biz).count()
        self.assertGreaterEqual(v2_count, 1, "SubscriptionV2 must be created during paid checkout")

    def test_does_not_duplicate_existing_v2_on_checkout(self):
        _attach_v2(self.biz, plan_code='start', status=SubscriptionV2.Status.ACTIVE)
        initial_count = SubscriptionV2.objects.filter(business=self.biz).count()

        self._post({'plan_code': 'pro', 'billing_cycle': 'monthly'})

        final_count = SubscriptionV2.objects.filter(business=self.biz).count()
        self.assertEqual(final_count, initial_count, "Must not duplicate existing V2 on checkout")


# ─────────────────────────────────────────────────────────────────────────────
# 3. apply_subscription_change — creates V2 if missing
# ─────────────────────────────────────────────────────────────────────────────

class ApplySubscriptionChangeV2BirthTest(TestCase):
    """apply_subscription_change must create SubscriptionV2 when none exists."""

    def setUp(self):
        self.biz = _make_business(name="ApplyBiz", service="gestion")

    def test_creates_v2_when_none_exists(self):
        self.assertEqual(SubscriptionV2.objects.filter(business=self.biz).count(), 0)

        apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={},
        )

        v2 = SubscriptionV2.objects.filter(business=self.biz).first()
        self.assertIsNotNone(v2, "SubscriptionV2 must be created by apply_subscription_change")
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)
        self.assertEqual(v2.plan_code, 'pro')

    def test_syncs_existing_v2_on_change(self):
        v2 = _attach_v2(self.biz, plan_code='start')

        apply_subscription_change(
            business=self.biz,
            target_plan_code='business',
            billing_cycle='yearly',
            config={},
        )

        v2.refresh_from_db()
        self.assertEqual(v2.plan_code, 'business')
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)

    def test_no_duplicate_v2_on_repeated_change(self):
        apply_subscription_change(
            business=self.biz, target_plan_code='pro', billing_cycle='monthly', config={},
        )
        apply_subscription_change(
            business=self.biz, target_plan_code='business', billing_cycle='monthly', config={},
        )

        # Still only one non-canceled V2
        count = SubscriptionV2.objects.filter(business=self.biz).exclude(
            status=SubscriptionV2.Status.CANCELED
        ).count()
        self.assertEqual(count, 1, "Must not duplicate SubscriptionV2 on repeated changes")

    def test_legacy_subscription_unaffected(self):
        """business.Subscription remains the runtime source of truth after V2 sync."""
        apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={'branches_extra_qty': 1},
        )
        biz_sub = BizSubscription.objects.get(business=self.biz)
        self.assertEqual(biz_sub.status, 'active')
        self.assertEqual(biz_sub.plan, 'pro')


# ─────────────────────────────────────────────────────────────────────────────
# 4. Webhook subscription_preapproval — correlates against V2 by provider_sub_id
# ─────────────────────────────────────────────────────────────────────────────

class WebhookV2CorrelationTest(TestCase):
    """
    When the birth path is complete, activate_tenant must find V2 by provider_sub_id
    (not fall back to business+service_type heuristic).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='wh.corr@test.com', username='wh.corr@test.com', password='pass'
        )
        self.biz = Business.objects.create(
            name='WH Corr Biz', default_service='gestion', status='pending_activation'
        )
        BizSubscription.objects.create(business=self.biz, plan='start', status='active')
        self.plan = _make_plan('plan_wh_001')
        self.preapproval_id = f'preapp-{uuid.uuid4()}'

        self.intent = _make_intent(self.biz, self.user, self.plan)
        _make_legacy_billing_sub(self.biz, preapproval_id=self.preapproval_id)

        # V2 created at birth with provider_sub_id already set
        self.v2 = SubscriptionV2.objects.create(
            business=self.biz,
            service_type='gestion',
            plan_code=self.plan.code,
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=self.preapproval_id,
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )
        self.intent.subscription_v2 = self.v2
        self.intent.save(update_fields=['subscription_v2'])

    def test_activates_v2_by_provider_sub_id(self):
        view = _make_webhook_view()
        view.activate_tenant(self.intent, self.preapproval_id)

        self.v2.refresh_from_db()
        self.assertEqual(self.v2.status, SubscriptionV2.Status.ACTIVE)

    def test_activates_v2_via_intent_fk(self):
        """Birth-path FK on intent is the most stable lookup; used first."""
        view = _make_webhook_view()
        # Use a different preapproval_id to prove it uses intent FK, not provider_sub_id
        different_id = f'preapp-other-{uuid.uuid4()}'
        # Re-create V2 without provider_sub_id but linked via intent
        v2_no_pid = SubscriptionV2.objects.create(
            business=Business.objects.create(
                name='IntentFK Biz', default_service='gestion', status='pending_activation'
            ),
            service_type='gestion',
            plan_code='start',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=None,
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )
        BizSubscription.objects.create(business=v2_no_pid.business, plan='start', status='active')
        LegacyBillingSubscription.objects.create(
            business=v2_no_pid.business, plan_type='bundle', billing_period='monthly',
            status='active', mp_preapproval_id=different_id,
        )
        user2 = User.objects.create_user(
            email='fk.only@test.com', username='fk.only@test.com', password='pass'
        )
        intent2 = SubscriptionIntent.objects.create(
            tenant=v2_no_pid.business, user=user2, plan_code='start', status='created',
            subscription_v2=v2_no_pid,
        )

        view.activate_tenant(intent2, different_id)

        v2_no_pid.refresh_from_db()
        self.assertEqual(v2_no_pid.status, SubscriptionV2.Status.ACTIVE)
        # provider_sub_id must be filled in
        self.assertEqual(v2_no_pid.provider_sub_id, different_id)

    def test_billing_event_linked_after_activation(self):
        """BillingEvent passed to activate_tenant must be linked to V2 and marked PROCESSED."""
        be = BillingEvent.objects.create(
            provider=BillingEvent.Provider.MERCADOPAGO,
            provider_event_id=f"req-wh-corr-{uuid.uuid4()}",
            event_type=BillingEvent.EventType.PREAPPROVAL_UPDATED,
            payload={},
            status=BillingEvent.ProcessingStatus.RECEIVED,
            received_at=timezone.now(),
        )

        view = _make_webhook_view()
        view.activate_tenant(self.intent, self.preapproval_id, billing_event=be)

        be.refresh_from_db()
        self.assertEqual(be.status, BillingEvent.ProcessingStatus.PROCESSED)
        self.assertEqual(be.subscription_id, self.v2.pk)

    def test_legacy_flow_completes_even_without_v2(self):
        """If no V2 at all, legacy activation still works."""
        self.v2.delete()
        self.intent.refresh_from_db()

        view = _make_webhook_view()
        view.activate_tenant(self.intent, self.preapproval_id)

        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, 'confirmed')


# ─────────────────────────────────────────────────────────────────────────────
# 5. PaymentAttempt — created when MP payment arrives
# ─────────────────────────────────────────────────────────────────────────────

class PaymentAttemptCreationTest(TestCase):
    """PaymentAttempt must be created for approved/rejected MP payments."""

    def setUp(self):
        self.biz = _make_business(name="PABiz", service="gestion", status="active")
        self.v2 = _attach_v2(self.biz, plan_code='pro', status=SubscriptionV2.Status.ACTIVE)

        self.factory = APIRequestFactory()
        self.view = MercadoPagoWebhookView.as_view()

    def _webhook_request(self, payload, request_id):
        return self.factory.post(
            '/api/v1/billing/mercadopago/webhook',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUEST_ID=request_id,
        )

    def _mock_payment_ok(self, pending_change_id, payment_status='approved'):
        return {
            'status': 200,
            'response': {
                'id': 'pm-111',
                'status': payment_status,
                'external_reference': f'subscription_change_{pending_change_id}',
                'transaction_amount': 29900.0,
                'currency_id': 'ARS',
                'status_detail': 'accredited',
                'payment_method_id': 'credit_card',
            },
        }

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    def test_creates_payment_attempt_on_approved_payment(self, _mock_sig):
        from apps.billing.models import PendingSubscriptionChange
        user = User.objects.create_user(email='pa.owner@test.com', username='pa.owner@test.com', password='pass')
        pending = PendingSubscriptionChange.objects.create(
            business=self.biz,
            user=user,
            target_plan_code='pro',
            billing_cycle='monthly',
            config_snapshot={},
            line_items=[],
            total_amount=29900,
            requires_checkout=True,
            is_upgrade=True,
            status='pending_payment',
        )
        payment_mock = self._mock_payment_ok(pending.id, 'approved')

        with patch.object(
            MercadoPagoWebhookView, 'process_payment_event', wraps=_make_webhook_view().process_payment_event
        ):
            with patch('apps.billing.mp_service.MercadoPagoService') as MockMP:
                MockMP.return_value.sdk.payment.return_value.get.return_value = payment_mock
                with patch('apps.billing.services.commercial.apply.apply_subscription_change'):
                    view_instance = MercadoPagoWebhookView()
                    be = BillingEvent.objects.create(
                        provider=BillingEvent.Provider.MERCADOPAGO,
                        provider_event_id=f"req-pa-{uuid.uuid4()}",
                        event_type=BillingEvent.EventType.UNKNOWN,
                        payload={},
                        status=BillingEvent.ProcessingStatus.RECEIVED,
                        received_at=timezone.now(),
                    )
                    with patch('apps.billing.views.MercadoPagoService') as MockMP2:
                        MockMP2.return_value.sdk.payment.return_value.get.return_value = payment_mock
                        view_instance.process_payment_event('pm-111', billing_event=be)

        pa = PaymentAttempt.objects.filter(external_payment_id='pm-111').first()
        self.assertIsNotNone(pa, "PaymentAttempt must be created for approved payment")
        self.assertEqual(pa.status, PaymentAttempt.Status.APPROVED)
        self.assertEqual(pa.subscription_id, self.v2.pk)
        self.assertEqual(pa.currency, 'ARS')

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    def test_payment_attempt_idempotent_on_duplicate_payment_id(self, _mock_sig):
        """Same external_payment_id must not create duplicate PaymentAttempt."""
        from apps.billing.views import _create_payment_attempt

        payment_data = {
            'status': 'approved',
            'transaction_amount': 10000.0,
            'currency_id': 'ARS',
        }
        _create_payment_attempt(self.v2, None, payment_data, 'pm-dup-001')
        _create_payment_attempt(self.v2, None, payment_data, 'pm-dup-001')

        count = PaymentAttempt.objects.filter(external_payment_id='pm-dup-001').count()
        self.assertEqual(count, 1, "Duplicate payment_id must not create duplicate PaymentAttempt")

    def test_payment_attempt_skipped_gracefully_when_no_v2(self):
        """If V2 cannot be resolved, PaymentAttempt is not created but no exception is raised."""
        from apps.billing.views import _create_payment_attempt
        payment_data = {'status': 'approved', 'transaction_amount': 5000.0, 'currency_id': 'ARS'}
        result = _create_payment_attempt(None, None, payment_data, 'pm-no-v2')
        self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Regression guards
# ─────────────────────────────────────────────────────────────────────────────

class RegressionGuardsTest(TestCase):
    """Ensure legacy flows are not broken by Phase 2B changes."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.webhook_view = MercadoPagoWebhookView.as_view()

    def _webhook_request(self, payload, request_id):
        return self.factory.post(
            '/api/v1/billing/mercadopago/webhook',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUEST_ID=request_id,
        )

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    @patch.object(MercadoPagoWebhookView, 'process_subscription_event')
    def test_billing_event_still_idempotent(self, _mock_process, _mock_sig):
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'rgre-001'}}
        self.webhook_view(self._webhook_request(payload, 'req-rgre-001'))
        self.webhook_view(self._webhook_request(payload, 'req-rgre-001'))

        count = BillingEvent.objects.filter(provider_event_id='req-rgre-001').count()
        self.assertEqual(count, 1, "BillingEvent must still be idempotent")

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    @patch.object(MercadoPagoWebhookView, 'process_subscription_event')
    def test_payment_event_legacy_still_written(self, _mock_process, _mock_sig):
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'rgre-002'}}
        self.webhook_view(self._webhook_request(payload, 'req-rgre-002'))

        pe = PaymentEvent.objects.filter(event_id='req-rgre-002').first()
        self.assertIsNotNone(pe, "PaymentEvent (legacy) must still be written")

    def test_biz_subscription_still_source_of_truth_after_apply(self):
        """After apply_subscription_change, business.Subscription is the runtime source."""
        biz = _make_business(name="RTBiz")
        apply_subscription_change(
            business=biz, target_plan_code='pro', billing_cycle='monthly', config={},
        )
        biz_sub = BizSubscription.objects.get(business=biz)
        self.assertEqual(biz_sub.plan, 'pro')
        self.assertEqual(biz_sub.status, 'active')

    def test_resolve_subscriptionv2_returns_none_gracefully(self):
        """Helper must return None without raising when no V2 exists."""
        biz = Business.objects.create(name='EmptyBiz', default_service='gestion')
        result = _resolve_subscriptionv2(biz, 'gestion', preapproval_id='no-such-id')
        self.assertIsNone(result)

    def test_resolve_subscriptionv2_prefers_provider_sub_id(self):
        """provider_sub_id lookup must take priority over (business, service_type)."""
        biz = _make_business(name="ResolvePreferBiz")
        # Two V2s – the one with matching provider_sub_id must be returned
        v2_a = _attach_v2(biz, plan_code='start', status=SubscriptionV2.Status.ACTIVE)
        v2_b = SubscriptionV2.objects.create(
            business=biz,
            service_type='restaurante',  # different service to avoid UniqueConstraint
            plan_code='start',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id='specific-preapp-id',
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )

        result = _resolve_subscriptionv2(biz, 'gestion', preapproval_id='specific-preapp-id')
        self.assertEqual(result.pk, v2_b.pk, "provider_sub_id must take priority")
