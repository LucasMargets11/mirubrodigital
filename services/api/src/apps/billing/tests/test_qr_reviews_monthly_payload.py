"""
tests/test_qr_reviews_monthly_payload.py
==========================================
Unit tests with mocks to validate the monthly Mercado Pago payload
for QR de Reseñas plans: qr_reviews_base and qr_reviews_pro.

Covers:
  1. qr_reviews_base → transaction_amount=15000.00, currency=ARS,
     frequency=1, frequency_type=months
  2. qr_reviews_pro  → transaction_amount=20000.00, currency=ARS,
     frequency=1, frequency_type=months
  3. Amount is sourced from Plan.price (not hardcoded)
  4. A free-form amount sent by the frontend cannot override Plan.price
  5. external_reference and current metadata are preserved
"""
from __future__ import annotations

import inspect
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.billing.checkout_session_service import (
    _create_mp_plan_for_session,
    start_checkout,
)
from apps.billing.models import MpCheckoutSession, Plan
from apps.billing.reviews_views import ReviewsUpgradeView
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email='qr_test@test.com'):
    return User.objects.create_user(email=email, username=email, password='testpass1234')


def _make_plan(code, price, frequency=1, frequency_type='months', currency='ARS'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults=dict(
            name=f'{code} Plan',
            price=Decimal(str(price)),
            currency=currency,
            frequency=frequency,
            frequency_type=frequency_type,
            interval='monthly',
            plan_status='active',
        ),
    )
    return plan


def _make_business(owner, plan='qr_reviews_base', service='qr_reviews'):
    biz = Business.objects.create(name='QR Biz', default_service=service, service_type=service)
    BizSubscription.objects.create(business=biz, plan=plan, status='active')
    Membership.objects.create(user=owner, business=biz, role='owner')
    return biz


def _make_checkout_session(user, plan, tenant=None):
    return MpCheckoutSession.objects.create(
        user=user,
        plan=plan,
        tenant=tenant,
        status=MpCheckoutSession.Status.CREATED,
        provider_mode='sandbox',
        idempotency_key='key-test',
        mp_external_reference=f'SESS-TEST-{plan.code}',
        return_url='https://app.test/subscribe/return',
        expires_at=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. qr_reviews_base payload
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsBasePayloadTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.business = _make_business(self.user, plan='qr_reviews_base')
        self.plan = _make_plan('qr_reviews_base', 15000)

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_base_generates_correct_monthly_payload(self, MockMPService):
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.return_value = {
            'id': 'PLAN-BASE',
            'init_point': 'https://www.mercadopago.com/subscriptions/checkout?preapproval_plan_id=PLAN-BASE',
            'status': 'active',
        }
        MockMPService.return_value = mock_sdk

        result = start_checkout(
            user=self.user,
            tenant=self.business,
            plan_code='qr_reviews_base',
            frontend_url='https://app.test',
        )

        self.assertEqual(MpCheckoutSession.objects.count(), 1)
        call_kwargs = mock_sdk.create_preapproval_plan.call_args.kwargs
        auto_recurring = call_kwargs['auto_recurring']

        self.assertEqual(auto_recurring['transaction_amount'], 15000.00)
        self.assertEqual(auto_recurring['currency_id'], 'ARS')
        self.assertEqual(auto_recurring['frequency'], 1)
        self.assertEqual(auto_recurring['frequency_type'], 'months')


# ─────────────────────────────────────────────────────────────────────────────
# 2. qr_reviews_pro payload
# ─────────────────────────────────────────────────────────────────────────────

class QrReviewsProPayloadTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.business = _make_business(self.user, plan='qr_reviews_base')
        self.plan = _make_plan('qr_reviews_pro', 20000)

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_pro_generates_correct_monthly_payload(self, MockMPService):
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.return_value = {
            'id': 'PLAN-PRO',
            'init_point': 'https://www.mercadopago.com/subscriptions/checkout?preapproval_plan_id=PLAN-PRO',
            'status': 'active',
        }
        MockMPService.return_value = mock_sdk

        result = start_checkout(
            user=self.user,
            tenant=self.business,
            plan_code='qr_reviews_pro',
            frontend_url='https://app.test',
        )

        self.assertEqual(MpCheckoutSession.objects.count(), 1)
        call_kwargs = mock_sdk.create_preapproval_plan.call_args.kwargs
        auto_recurring = call_kwargs['auto_recurring']

        self.assertEqual(auto_recurring['transaction_amount'], 20000.00)
        self.assertEqual(auto_recurring['currency_id'], 'ARS')
        self.assertEqual(auto_recurring['frequency'], 1)
        self.assertEqual(auto_recurring['frequency_type'], 'months')


# ─────────────────────────────────────────────────────────────────────────────
# 3. Amount comes from Plan.price
# ─────────────────────────────────────────────────────────────────────────────

class PlanPriceSourceTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.business = _make_business(self.user, plan='qr_reviews_base')
        self.plan = _make_plan('qr_reviews_base', 15000)

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_amount_reflects_plan_price_changes(self, MockMPService):
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.return_value = {
            'id': 'PLAN-PRICE',
            'init_point': 'https://www.mercadopago.com/subscriptions/checkout?preapproval_plan_id=PLAN-PRICE',
            'status': 'active',
        }
        MockMPService.return_value = mock_sdk

        plan = Plan.objects.get(code='qr_reviews_base')
        original_price = plan.price
        new_price = Decimal('35000.00')
        plan.price = new_price
        plan.save(update_fields=['price'])

        start_checkout(
            user=self.user,
            tenant=self.business,
            plan_code='qr_reviews_base',
            frontend_url='https://app.test',
        )

        call_kwargs = mock_sdk.create_preapproval_plan.call_args.kwargs
        auto_recurring = call_kwargs['auto_recurring']
        self.assertEqual(auto_recurring['transaction_amount'], float(new_price))
        self.assertNotEqual(auto_recurring['transaction_amount'], float(original_price))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Frontend free-form amount cannot override Plan.price
# ─────────────────────────────────────────────────────────────────────────────

class FrontendAmountCannotOverrideTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.business = _make_business(self.user, plan='qr_reviews_base')
        self.plan = _make_plan('qr_reviews_base', 15000)

    def test_start_checkout_has_no_frontend_amount_parameter(self):
        sig = inspect.signature(start_checkout)
        param_names = list(sig.parameters.keys())
        self.assertNotIn('amount', param_names)
        self.assertNotIn('frontend_amount', param_names)
        self.assertNotIn('transaction_amount', param_names)

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_override_amount_only_from_internal_promo(self, MockMPService):
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.return_value = {
            'id': 'PLAN-OVR',
            'init_point': 'https://www.mercadopago.com/subscriptions/checkout?preapproval_plan_id=PLAN-OVR',
            'status': 'active',
        }
        MockMPService.return_value = mock_sdk

        start_checkout(
            user=self.user,
            tenant=self.business,
            plan_code='qr_reviews_base',
            frontend_url='https://app.test',
        )

        call_kwargs = mock_sdk.create_preapproval_plan.call_args.kwargs
        auto_recurring = call_kwargs['auto_recurring']
        self.assertEqual(auto_recurring['transaction_amount'], 15000.00)

    def test_create_mp_plan_for_session_only_accepts_override_amount(self):
        sig = inspect.signature(_create_mp_plan_for_session)
        param_names = list(sig.parameters.keys())
        self.assertIn('override_amount', param_names)
        allowed_params = {'session', 'plan', 'frontend_url', 'override_amount'}
        self.assertEqual(set(param_names), allowed_params)


# ─────────────────────────────────────────────────────────────────────────────
# 5. external_reference and metadata preserved
# ─────────────────────────────────────────────────────────────────────────────

class ExternalReferenceAndMetadataTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.business = _make_business(self.user, plan='qr_reviews_base')
        self.plan = _make_plan('qr_reviews_base', 15000)

    @patch('apps.billing.mp_service.MercadoPagoService')
    def test_external_reference_passed_to_mp_plan(self, MockMPService):
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.return_value = {
            'id': 'PLAN-EXTREF',
            'init_point': 'https://www.mercadopago.com/subscriptions/checkout?preapproval_plan_id=PLAN-EXTREF',
            'status': 'active',
        }
        MockMPService.return_value = mock_sdk

        start_checkout(
            user=self.user,
            tenant=self.business,
            plan_code='qr_reviews_base',
            frontend_url='https://app.test',
        )

        call_kwargs = mock_sdk.create_preapproval_plan.call_args.kwargs
        session = MpCheckoutSession.objects.first()
        self.assertEqual(call_kwargs['external_reference'], session.mp_external_reference)
        self.assertIn('SESS-', call_kwargs['external_reference'])

    @patch('apps.billing.reviews_views.MercadoPagoService')
    def test_external_reference_and_metadata_in_upgrade_preference(self, MockMP):
        MockMP.return_value.create_preference.return_value = {
            'id': 'pref-upgrade',
            'init_point': 'https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref-upgrade',
        }

        client = APIClient()
        client.force_authenticate(user=self.user)
        res = client.post('/api/v1/billing/reviews/upgrade/')
        self.assertEqual(res.status_code, 200)

        call_kwargs = MockMP.return_value.create_preference.call_args.kwargs
        self.assertIn('external_reference', call_kwargs)
        self.assertIn('reviews_upgrade_', call_kwargs['external_reference'])
        self.assertIn('metadata', call_kwargs)
        metadata = call_kwargs['metadata']
        self.assertEqual(metadata['plan_code'], 'qr_reviews_pro')
        self.assertIn('business_id', metadata)
        self.assertIn('pending_change_id', metadata)
