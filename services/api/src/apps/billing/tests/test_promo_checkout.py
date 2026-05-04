"""
tests/test_promo_checkout.py
============================
Integration tests for the promo code flow through start_checkout() and the
OnboardingStartCheckoutView.

Coverage
--------
  1.  start_checkout with valid promo: discounted amount sent to MP, redemption created.
  2.  start_checkout with invalid promo: ValueError raised, no session created.
  3.  start_checkout without promo: original amount sent to MP, no redemption created.
  4.  Reuse existing session WITH matching promo redemption → idempotent return.
  5.  Reuse existing session WITHOUT promo redemption when promo provided → expires old, creates new.
  6.  ValidatePromoCodeView POST: valid code returns 200 with discount details.
  7.  ValidatePromoCodeView POST: invalid code returns 200 with error payload.
  8.  ValidatePromoCodeView POST: unauthenticated → 401.
  9.  OnboardingStartCheckoutView with promo_code in body → promo applied.
 10.  OnboardingStartCheckoutView without promo_code → plain checkout (no redemption).
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import (
    MpCheckoutSession,
    Plan,
    PromoCode,
    PromoCodeRedemption,
    SubscriptionV2,
)
from apps.billing.checkout_session_service import start_checkout
from apps.business.models import Business
from apps.business.models import Subscription as BizSubscription
from apps.accounts.models import Membership

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email='checkout@test.com'):
    return User.objects.create_user(email=email, username=email, password='testpass1234')


def _make_plan(code='start', price=29900):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults=dict(
            name='Start Plan',
            price=Decimal(str(price)),
            interval='monthly',
            currency='ARS',
            frequency=1,
            frequency_type='months',
            plan_status='active',
        ),
    )
    return plan


def _make_business(owner=None, name='Promo Biz', service='gestion', status='onboarding'):
    biz = Business.objects.create(
        name=name, default_service=service, service_type=service, status=status,
    )
    BizSubscription.objects.create(business=biz, plan='start', status='active')
    if owner:
        Membership.objects.create(user=owner, business=biz, role='owner')
    return biz


def _make_promo(code='SAVE10', **kwargs):
    defaults = dict(
        name='10% Off',
        discount_type=PromoCode.DiscountType.PERCENT,
        discount_value=Decimal('10'),
        duration_cycles=2,
        active=True,
        applies_to_plan_codes=['start'],
        applies_to_billing_periods=['monthly'],
    )
    defaults.update(kwargs)
    return PromoCode.objects.create(code=code, **defaults)


_FAKE_MP_PLAN = {
    'id': 'PLAN-MOCK-001',
    'init_point': 'https://www.mercadopago.com/checkout?pref_id=MOCK',
    'sandbox_init_point': 'https://sandbox.mercadopago.com/checkout?pref_id=MOCK',
}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: start_checkout()
# ─────────────────────────────────────────────────────────────────────────────

@patch('apps.billing.mp_service.MercadoPagoService')
class StartCheckoutPromoTests(TestCase):

    def setUp(self):
        self.user = _make_user('svc@test.com')
        self.plan = _make_plan()
        self.business = _make_business(owner=self.user)

    def _run(self, mock_mp_cls, promo_code=None, plan_id='PLAN-MOCK-001'):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.create_preapproval_plan.return_value = {**_FAKE_MP_PLAN, 'id': plan_id}
        return start_checkout(
            user=self.user,
            tenant=self.business,
            plan_code='start',
            frontend_url='http://localhost:3000',
            promo_code=promo_code,
        )

    # ── 1. Valid promo: discounted amount used in MP plan, redemption created ─

    def test_promo_applies_discounted_amount(self, mock_mp_cls):
        promo = _make_promo()
        result = self._run(mock_mp_cls, promo_code='SAVE10')

        self.assertFalse(result['reused'])
        session = MpCheckoutSession.objects.get(id=result['checkout_session_id'])

        # PromoCodeRedemption created
        redemption = PromoCodeRedemption.objects.get(checkout_session=session)
        self.assertEqual(redemption.promo_code, promo)
        self.assertEqual(redemption.business, self.business)
        self.assertEqual(redemption.status, PromoCodeRedemption.Status.PENDING)
        self.assertEqual(redemption.original_amount, Decimal('29900.00'))
        self.assertEqual(redemption.discounted_amount, Decimal('26910.00'))
        self.assertEqual(redemption.cycles_total, 2)

        # MP plan was called with the discounted amount
        call_kwargs = mock_mp_cls.return_value.create_preapproval_plan.call_args
        auto_recurring = call_kwargs[1].get('auto_recurring') or call_kwargs[0][1]
        self.assertAlmostEqual(auto_recurring['transaction_amount'], 26910.0, places=2)

    # ── 2. Invalid promo: ValueError raised, no session or redemption ─────────

    def test_invalid_promo_raises_value_error(self, mock_mp_cls):
        with self.assertRaises(ValueError):
            self._run(mock_mp_cls, promo_code='BADCODE')

        self.assertEqual(MpCheckoutSession.objects.count(), 0)
        self.assertEqual(PromoCodeRedemption.objects.count(), 0)

    # ── 3. No promo: original amount, no redemption ───────────────────────────

    def test_no_promo_uses_original_amount(self, mock_mp_cls):
        result = self._run(mock_mp_cls, promo_code=None)

        self.assertFalse(result['reused'])
        self.assertEqual(PromoCodeRedemption.objects.count(), 0)

        call_kwargs = mock_mp_cls.return_value.create_preapproval_plan.call_args
        auto_recurring = call_kwargs[1].get('auto_recurring') or call_kwargs[0][1]
        self.assertAlmostEqual(auto_recurring['transaction_amount'], 29900.0, places=2)

    # ── 4. Reuse session with matching promo redemption ───────────────────────

    def test_reuse_session_with_matching_redemption(self, mock_mp_cls):
        promo = _make_promo()
        # First call: creates session + redemption
        result1 = self._run(mock_mp_cls, promo_code='SAVE10')
        self.assertFalse(result1['reused'])

        # Second call with same promo: should reuse
        result2 = self._run(mock_mp_cls, promo_code='SAVE10')
        self.assertTrue(result2['reused'])
        self.assertEqual(result1['checkout_session_id'], result2['checkout_session_id'])

        # Only ONE redemption created
        self.assertEqual(PromoCodeRedemption.objects.count(), 1)
        # MP plan creation called only once (early reuse skips MP on second call)
        self.assertEqual(mock_mp_cls.call_count, 1)

    # ── 5. Existing session WITHOUT redemption when promo provided → new session

    def test_existing_session_without_promo_expires_on_promo_request(self, mock_mp_cls):
        promo = _make_promo()
        # First call: plain checkout (no promo)
        result1 = self._run(mock_mp_cls, promo_code=None, plan_id='PLAN-MOCK-001')
        old_session_id = result1['checkout_session_id']
        self.assertFalse(result1['reused'])

        # Second call WITH promo: old session must be expired, new one created.
        # Use a different plan_id to avoid unique constraint on provider_preapproval_plan_id.
        result2 = self._run(mock_mp_cls, promo_code='SAVE10', plan_id='PLAN-MOCK-002')
        self.assertFalse(result2['reused'])
        self.assertNotEqual(old_session_id, result2['checkout_session_id'])

        # Old session is now expired
        old_session = MpCheckoutSession.objects.get(id=old_session_id)
        self.assertEqual(old_session.status, MpCheckoutSession.Status.EXPIRED)

        # New session has a redemption
        self.assertEqual(PromoCodeRedemption.objects.count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: ValidatePromoCodeView
# ─────────────────────────────────────────────────────────────────────────────

class ValidatePromoCodeViewTests(TestCase):

    def setUp(self):
        self.user = _make_user('api@test.com')
        self.plan = _make_plan()
        self.business = _make_business(owner=self.user)
        self.client = APIClient()
        self.url = '/api/v1/billing/promo-codes/validate/'

    def _post(self, data):
        return self.client.post(self.url, data, format='json')

    # ── 6. Valid code → 200 with discount details ─────────────────────────────

    def test_valid_code_returns_discount_info(self):
        _make_promo(code='VALID20', discount_value=Decimal('20'))
        self.client.force_authenticate(user=self.user)
        resp = self._post({'code': 'VALID20', 'plan_code': 'start'})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['valid'])
        self.assertEqual(data['code'], 'VALID20')
        self.assertIn('discounted_amount', data)
        self.assertIn('summary', data)

    # ── 7. Invalid code → 200 with error payload ──────────────────────────────

    def test_invalid_code_returns_error_payload(self):
        self.client.force_authenticate(user=self.user)
        resp = self._post({'code': 'NOPE', 'plan_code': 'start'})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['valid'])
        self.assertEqual(data['error_code'], 'CODE_NOT_FOUND')

    # ── 8. Unauthenticated → 401 ──────────────────────────────────────────────

    def test_unauthenticated_returns_401(self):
        resp = self._post({'code': 'VALID20', 'plan_code': 'start'})
        self.assertEqual(resp.status_code, 401)

    # ── 9. Missing plan_code → 400 ────────────────────────────────────────────

    def test_missing_plan_code_returns_400(self):
        self.client.force_authenticate(user=self.user)
        resp = self._post({'code': 'VALID20'})
        self.assertEqual(resp.status_code, 400)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: OnboardingStartCheckoutView
# ─────────────────────────────────────────────────────────────────────────────

@patch('apps.billing.mp_service.MercadoPagoService')
class OnboardingCheckoutWithPromoTests(TestCase):

    def setUp(self):
        self.user = _make_user('onboarding@test.com')
        self.plan = _make_plan()
        self.business = _make_business(
            owner=self.user, name='Onboarding Biz', status='onboarding',
        )
        self.business.service_type = 'gestion'
        self.business.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v1/auth/onboarding/start-checkout/'

    def _post(self, mock_mp_cls, data):
        mock_mp = MagicMock()
        mock_mp_cls.return_value = mock_mp
        mock_mp.create_preapproval_plan.return_value = _FAKE_MP_PLAN
        return self.client.post(self.url, data, format='json')

    # ── 9. Onboarding checkout with promo_code ────────────────────────────────

    def test_onboarding_checkout_with_promo(self, mock_mp_cls):
        promo = _make_promo(code='ONBOARD10')
        resp = self._post(mock_mp_cls, {'plan_code': 'start', 'promo_code': 'ONBOARD10'})

        self.assertIn(resp.status_code, [200, 201])
        data = resp.json()
        self.assertIn('checkout_session_id', data)

        # A redemption must exist
        session = MpCheckoutSession.objects.get(id=data['checkout_session_id'])
        redemption = PromoCodeRedemption.objects.get(checkout_session=session)
        self.assertEqual(redemption.promo_code, promo)
        self.assertEqual(redemption.status, PromoCodeRedemption.Status.PENDING)

    # ── 10. Onboarding checkout without promo_code → no redemption ────────────

    def test_onboarding_checkout_without_promo(self, mock_mp_cls):
        resp = self._post(mock_mp_cls, {'plan_code': 'start'})

        self.assertIn(resp.status_code, [200, 201])
        self.assertEqual(PromoCodeRedemption.objects.count(), 0)
