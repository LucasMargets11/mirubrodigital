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
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.billing.models import (
    BillingEvent,
    PaymentAttempt,
    PaymentEvent,
    Plan,
    Subscription as LegacyBillingSubscription,
    SubscriptionIntent,
    SubscriptionV2,
)
from apps.billing.services.commercial.apply import apply_subscription_change
from apps.billing.views import MercadoPagoWebhookView, _resolve_subscriptionv2
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()

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
# 1. StartSubscriptionView — SubscriptionV2 created at birth
# ─────────────────────────────────────────────────────────────────────────────

class StartSubscriptionViewBirthPathTest(TestCase):
    """StartSubscriptionView must create SubscriptionV2 at the same time as the intent."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.plan = _make_plan("plan_start_001")

    def _post(self, payload):
        from apps.billing.views import StartSubscriptionView
        request = self.factory.post(
            '/api/v1/billing/start-subscription',
            data=json.dumps(payload),
            content_type='application/json',
        )
        return StartSubscriptionView.as_view()(request)

    def _mock_mp_service(self):
        mock_svc = MagicMock()
        mock_svc.create_preapproval.return_value = {
            'id': f'preapp-{uuid.uuid4()}',
            'init_point': 'https://mp.example.com/checkout',
        }
        return mock_svc

    @patch('apps.billing.views.MercadoPagoService')
    def test_creates_subscriptionv2_on_new_signup(self, MockMP):
        MockMP.return_value = self._mock_mp_service()

        payload = {
            'email': 'newuser@test.com',
            'password': 'Passw0rd!',
            'business_name': 'My Biz',
            'plan_code': self.plan.code,
        }
        response = self._post(payload)

        self.assertEqual(response.status_code, 200, response.data)

        # Must have created exactly one SubscriptionV2
        v2_qs = SubscriptionV2.objects.filter(service_type='gestion')
        self.assertEqual(v2_qs.count(), 1, "Exactly one SubscriptionV2 must be created")

        v2 = v2_qs.first()
        self.assertEqual(v2.status, SubscriptionV2.Status.CHECKOUT_PENDING)
        self.assertIsNotNone(v2.provider_sub_id, "provider_sub_id must be set to MP preapproval ID")
        self.assertTrue(v2.external_reference.startswith("SUB-"))

    @patch('apps.billing.views.MercadoPagoService')
    def test_intent_linked_to_subscriptionv2(self, MockMP):
        MockMP.return_value = self._mock_mp_service()

        payload = {
            'email': 'linked@test.com',
            'password': 'Passw0rd!',
            'business_name': 'Linked Biz',
            'plan_code': self.plan.code,
        }
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)

        intent_id = response.data['intent_id']
        intent = SubscriptionIntent.objects.get(pk=intent_id)

        self.assertIsNotNone(intent.subscription_v2_id, "Intent must be linked to V2")
        self.assertEqual(intent.subscription_v2.status, SubscriptionV2.Status.CHECKOUT_PENDING)

    @patch('apps.billing.views.MercadoPagoService')
    def test_legacy_subscription_still_created(self, MockMP):
        MockMP.return_value = self._mock_mp_service()

        payload = {
            'email': 'legacy@test.com',
            'password': 'Passw0rd!',
            'business_name': 'Legacy Biz',
            'plan_code': self.plan.code,
        }
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)

        # Legacy billing subscription must still exist
        self.assertTrue(
            LegacyBillingSubscription.objects.filter(business__name='Legacy Biz').exists(),
            "Legacy billing.Subscription must still be created",
        )

    @patch('apps.billing.views.MercadoPagoService')
    def test_duplicate_email_rejected_legacy_guard(self, MockMP):
        """Second signup attempt with same email must fail; no duplicate V2."""
        MockMP.return_value = self._mock_mp_service()
        payload = {
            'email': 'dup@test.com',
            'password': 'Passw0rd!',
            'business_name': 'Dup Biz',
            'plan_code': self.plan.code,
        }
        r1 = self._post(payload)
        self.assertEqual(r1.status_code, 200)

        r2 = self._post(payload)
        # Must reject: email already registered
        self.assertEqual(r2.status_code, 400)
        # Count must remain 1 (no duplicate V2)
        self.assertEqual(SubscriptionV2.objects.filter(service_type='gestion').count(), 1)


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
