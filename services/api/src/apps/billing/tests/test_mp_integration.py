"""
Regression and integration tests for the Mercado Pago bridge fixes.

Covers:
  - apply_subscription_change: correct SubscriptionAddon FK, no FieldError, lowercase plan
  - apply_addon_activation: correct subscription FK, no price field
  - webhook: BillingEvent persisted and idempotent; PaymentEvent legacy still written
  - activate_tenant: SubscriptionV2 synced to active when found
  - apply_subscription_change: SubscriptionV2 synced when found
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.billing.models import (
    BillingEvent,
    PaymentEvent,
    Plan,
    Subscription as LegacyBillingSubscription,
    SubscriptionIntent,
    SubscriptionV2,
)
from apps.billing.services.commercial.apply import (
    apply_addon_activation,
    apply_subscription_change,
)
from apps.billing.views import MercadoPagoWebhookView
from apps.business.models import Business, Subscription as BizSubscription, SubscriptionAddon

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_business(name="TestBiz", service="gestion"):
    biz = Business.objects.create(name=name, default_service=service, service_type=service)
    BizSubscription.objects.create(business=biz, plan="start", status="active")
    return biz


def _attach_v2(biz, plan_code="start", status=None):
    return SubscriptionV2.objects.create(
        business=biz,
        service_type=biz.default_service,
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MANUAL,
        external_reference=f"SUB-{uuid.uuid4()}",
        status=status or SubscriptionV2.Status.ACTIVE,
    )


# ─────────────────────────────────────────────────────────────────────────────
# A. apply_subscription_change
# ─────────────────────────────────────────────────────────────────────────────

class ApplySubscriptionChangeTest(TestCase):

    def setUp(self):
        self.biz = _make_business()

    def test_no_fielderror_on_plan_change(self):
        """Core regression: must not raise FieldError on SubscriptionAddon."""
        sub = apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={},
        )
        self.assertEqual(sub.status, 'active')

    def test_plan_code_stored_lowercase(self):
        """plan must be stored as lowercase to match BusinessPlan choices."""
        sub = apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={},
        )
        self.assertEqual(sub.plan, 'pro')  # NOT 'PRO'

    def test_extra_branch_addon_uses_subscription_fk(self):
        apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={'branches_extra_qty': 2},
        )
        sub = BizSubscription.objects.get(business=self.biz)
        addon = sub.addons.filter(code='extra_branch', is_active=True).first()
        self.assertIsNotNone(addon, "extra_branch addon must be created")
        self.assertEqual(addon.quantity, 2)
        self.assertEqual(addon.subscription_id, sub.pk)

    def test_extra_seat_addon_uses_subscription_fk(self):
        apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={'seats_extra_qty': 3},
        )
        sub = BizSubscription.objects.get(business=self.biz)
        addon = sub.addons.filter(code='extra_seat', is_active=True).first()
        self.assertIsNotNone(addon)
        self.assertEqual(addon.quantity, 3)

    def test_clears_previous_addons_on_change(self):
        """Plan change replaces addons; no leftovers from previous config."""
        sub = BizSubscription.objects.get(business=self.biz)
        SubscriptionAddon.objects.create(
            subscription=sub, code='extra_branch', quantity=5, is_active=True
        )
        apply_subscription_change(
            business=self.biz,
            target_plan_code='business',
            billing_cycle='monthly',
            config={},  # no extras requested
        )
        sub.refresh_from_db()
        self.assertEqual(sub.addons.count(), 0)

    def test_syncs_subscriptionv2_plan_and_status(self):
        v2 = _attach_v2(self.biz, plan_code='start')
        apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={},
        )
        v2.refresh_from_db()
        self.assertEqual(v2.plan_code, 'pro')
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)

    def test_succeeds_without_subscriptionv2(self):
        """No SubscriptionV2 must not break the flow."""
        sub = apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='monthly',
            config={},
        )
        self.assertIsNotNone(sub)

    def test_yearly_renews_at_set(self):
        sub = apply_subscription_change(
            business=self.biz,
            target_plan_code='pro',
            billing_cycle='yearly',
            config={},
        )
        self.assertIsNotNone(sub.renews_at)


# ─────────────────────────────────────────────────────────────────────────────
# B. apply_addon_activation
# ─────────────────────────────────────────────────────────────────────────────

class ApplyAddonActivationTest(TestCase):

    def setUp(self):
        self.biz = _make_business()

    def test_creates_addon_with_subscription_fk(self):
        addon = apply_addon_activation(business=self.biz, addon_code='crm')
        sub = BizSubscription.objects.get(business=self.biz)
        self.assertEqual(addon.subscription_id, sub.pk)
        self.assertTrue(addon.is_active)

    def test_reactivates_inactive_addon(self):
        sub = BizSubscription.objects.get(business=self.biz)
        existing = SubscriptionAddon.objects.create(
            subscription=sub, code='crm', quantity=1, is_active=False
        )
        apply_addon_activation(business=self.biz, addon_code='crm')
        existing.refresh_from_db()
        self.assertTrue(existing.is_active)

    def test_does_not_duplicate_active_addon(self):
        apply_addon_activation(business=self.biz, addon_code='crm')
        apply_addon_activation(business=self.biz, addon_code='crm')
        sub = BizSubscription.objects.get(business=self.biz)
        self.assertEqual(sub.addons.filter(code='crm').count(), 1)

    def test_raises_for_missing_subscription(self):
        biz_no_sub = Business.objects.create(name="NoSub", default_service="gestion")
        with self.assertRaises(ValueError):
            apply_addon_activation(business=biz_no_sub, addon_code='crm')

    def test_raises_for_invalid_addon_code(self):
        with self.assertRaises(ValueError):
            apply_addon_activation(business=self.biz, addon_code='nonexistent_xyzabc')


# ─────────────────────────────────────────────────────────────────────────────
# C. Webhook: BillingEvent idempotency + PaymentEvent legacy compat
# ─────────────────────────────────────────────────────────────────────────────

class WebhookBillingEventTest(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = MercadoPagoWebhookView.as_view()

    def _webhook_request(self, payload, request_id):
        return self.factory.post(
            '/api/v1/billing/mercadopago/webhook',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUEST_ID=request_id,
        )

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    @patch.object(MercadoPagoWebhookView, 'process_subscription_event')
    def test_billing_event_persisted(self, _mock_process, _mock_sig):
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-111'}}
        response = self.view(self._webhook_request(payload, 'req-001'))
        self.assertEqual(response.status_code, 200)

        be = BillingEvent.objects.filter(provider_event_id='req-001').first()
        self.assertIsNotNone(be, "BillingEvent must be created on first receive")
        self.assertEqual(be.provider, BillingEvent.Provider.MERCADOPAGO)
        self.assertEqual(be.status, BillingEvent.ProcessingStatus.RECEIVED)
        self.assertEqual(be.event_type, BillingEvent.EventType.PREAPPROVAL_UPDATED)

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    @patch.object(MercadoPagoWebhookView, 'process_subscription_event')
    def test_billing_event_not_duplicated_on_resend(self, _mock_process, _mock_sig):
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-222'}}
        self.view(self._webhook_request(payload, 'req-002'))
        self.view(self._webhook_request(payload, 'req-002'))

        count = BillingEvent.objects.filter(provider_event_id='req-002').count()
        self.assertEqual(count, 1, "Duplicate webhook must not create duplicate BillingEvent")

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    @patch.object(MercadoPagoWebhookView, 'process_subscription_event')
    def test_payment_event_legacy_still_written(self, _mock_process, _mock_sig):
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-333'}}
        self.view(self._webhook_request(payload, 'req-003'))

        pe = PaymentEvent.objects.filter(event_id='req-003').first()
        self.assertIsNotNone(pe, "PaymentEvent (legacy) must still be written")

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    @patch.object(MercadoPagoWebhookView, 'process_payment_event')
    def test_billing_event_type_unknown_for_payment_topic(self, _mock_process, _mock_sig):
        payload = {'type': 'payment', 'data': {'id': 'pay-444'}}
        self.view(self._webhook_request(payload, 'req-004'))

        be = BillingEvent.objects.filter(provider_event_id='req-004').first()
        self.assertIsNotNone(be)
        self.assertEqual(be.event_type, BillingEvent.EventType.UNKNOWN)

    @patch.object(MercadoPagoWebhookView, '_verify_mp_signature', return_value=True)
    @patch.object(MercadoPagoWebhookView, 'process_subscription_event')
    def test_second_webhook_call_returns_200(self, _mock_process, _mock_sig):
        """Idempotent resend must still return 200."""
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-555'}}
        r1 = self.view(self._webhook_request(payload, 'req-005'))
        r2 = self.view(self._webhook_request(payload, 'req-005'))
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# D. activate_tenant: SubscriptionV2 sync
# ─────────────────────────────────────────────────────────────────────────────

class ActivateTenantV2SyncTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@testbiz.com', username='owner@testbiz.com', password='testpass'
        )
        self.biz = Business.objects.create(
            name='ActivateBiz', default_service='gestion', status='pending_activation'
        )
        BizSubscription.objects.create(business=self.biz, plan='start', status='active')
        self.plan = Plan.objects.create(
            code='test_plan_act', name='Test Plan', price=100, interval='monthly'
        )
        self.intent = SubscriptionIntent.objects.create(
            tenant=self.biz,
            user=self.user,
            plan_code=self.plan.code,
            status='created',
        )
        self.legacy_billing_sub = LegacyBillingSubscription.objects.create(
            business=self.biz,
            plan_type='bundle',
            billing_period='monthly',
            status='pending',
            mp_preapproval_id='preapp-act-001',
        )

    def test_legacy_flow_completes(self):
        view = MercadoPagoWebhookView()
        view.activate_tenant(self.intent, 'preapp-act-001')

        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')

        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, 'confirmed')

        self.legacy_billing_sub.refresh_from_db()
        self.assertEqual(self.legacy_billing_sub.status, 'active')

    def test_v2_synced_by_provider_sub_id(self):
        v2 = SubscriptionV2.objects.create(
            business=self.biz,
            service_type='gestion',
            plan_code='start',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id='preapp-act-002',
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )
        LegacyBillingSubscription.objects.filter(business=self.biz).update(
            mp_preapproval_id='preapp-act-002'
        )

        view = MercadoPagoWebhookView()
        view.activate_tenant(self.intent, 'preapp-act-002')

        v2.refresh_from_db()
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)

    def test_v2_synced_by_business_fallback(self):
        """When SubscriptionV2 has no provider_sub_id, find by business+service_type."""
        v2 = SubscriptionV2.objects.create(
            business=self.biz,
            service_type='gestion',
            plan_code='start',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=None,  # not yet linked
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )

        view = MercadoPagoWebhookView()
        view.activate_tenant(self.intent, 'preapp-act-003')

        v2.refresh_from_db()
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)
        self.assertEqual(v2.provider_sub_id, 'preapp-act-003')

    def test_activation_succeeds_without_v2(self):
        """No SubscriptionV2 in DB: legacy flow must still complete normally."""
        view = MercadoPagoWebhookView()
        view.activate_tenant(self.intent, 'preapp-act-001')

        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')
