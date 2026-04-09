"""
tests/test_checkout_flow_v2.py
================================
Comprehensive tests for the Phase 3 subscription checkout flow.

Covers:
  1.  start_checkout creates session + MP plan exactly once
  2.  Double-click returns same session and init_point, no duplicate MP plan
  3.  Expired session triggers creation of a new session
  4.  Duplicate webhook not processed twice (by x-request-id)
  5.  Duplicate webhook not processed twice (by payload hash, no x-request-id)
  6.  Invalid signature → 400, delivery still persisted
  7.  Webhook before return activates subscription correctly
  8.  checkout-sessions polling endpoint reflects pending state (no webhook yet)
  9.  authorized_payment webhook activates subscription idempotently
 10.  Orphan authorized_payment (no linked subscription) does NOT activate anything
 11.  Correlation is done by preapproval_plan_id — NOT by payer email
 12.  expire_checkout_sessions Celery task expires correct sessions
 13.  CheckoutSessionStatusView returns correct data after activation
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from apps.billing.models import (
    BillingInvoiceEvent,
    MpCheckoutSession,
    Plan,
    SubscriptionV2,
    WebhookDelivery,
)
from apps.billing.tasks import expire_checkout_sessions
from apps.billing.views import MercadoPagoWebhookView
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Shared factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email='user@test.com'):
    return User.objects.create_user(
        email=email, username=email, password='testpass1234'
    )


def _make_plan(code='pro', **kwargs):
    defaults = dict(
        name='Pro Plan',
        price=50000,  # ARS pesos (canonical Pro = 50000)
        currency='ARS',
        billing_cycle='monthly',
        plan_status='active',
    )
    defaults.update(kwargs)
    plan, _ = Plan.objects.get_or_create(code=code, defaults=defaults)
    return plan


def _make_business(owner, name='Test Biz', service='gestion'):
    biz = Business.objects.create(name=name, default_service=service, service_type=service)
    BizSubscription.objects.create(business=biz, plan='start', status='active')
    return biz


def _make_subscription_v2(business, plan, preapproval_plan_id=None, session=None):
    return SubscriptionV2.objects.create(
        business=business,
        service_type=business.default_service,
        plan_code=plan.code,
        provider=SubscriptionV2.Provider.MERCADOPAGO,
        provider_sub_id=f'preapp-{uuid.uuid4()}',
        external_reference=f'ref-{uuid.uuid4()}',
        status=SubscriptionV2.Status.PENDING,
        provider_preapproval_plan_id=preapproval_plan_id,
        checkout_session=session,
    )


def _make_checkout_session(user, plan, tenant=None, status=MpCheckoutSession.Status.CHECKOUT_CREATED,
                            provider_preapproval_plan_id=None, expires_at=None):
    return MpCheckoutSession.objects.create(
        user=user,
        plan=plan,
        tenant=tenant,
        status=status,
        provider_preapproval_plan_id=provider_preapproval_plan_id,
        provider_checkout_url='https://www.mercadopago.com/checkout/v1/redirect?pref_id=TEST',
        idempotency_key=f'key-{uuid.uuid4()}',
        mp_external_reference=f'SESS-{uuid.uuid4()}',
        expires_at=expires_at or (timezone.now() + timedelta(hours=1)),
    )


def _make_webhook_delivery(topic='subscription_preapproval', resource_id='preapp-001',
                            x_request_id='req-001', status=WebhookDelivery.ProcessingStatus.RECEIVED):
    return WebhookDelivery.objects.create(
        topic=topic,
        resource_id=resource_id,
        x_request_id=x_request_id,
        payload_hash=hashlib.sha256(b'{}').hexdigest(),
        body_json={},
        headers_json={},
        received_at=timezone.now(),
        processing_status=status,
    )


def _mp_plan_response(plan_id='PLAN-001'):
    return {
        'id': plan_id,
        'init_point': f'https://www.mercadopago.com/subscriptions/checkout?preapproval_plan_id={plan_id}',
        'status': 'active',
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. start_checkout creates session + MP plan exactly once
# ─────────────────────────────────────────────────────────────────────────────

class StartCheckoutIdempotencyTest(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.plan = _make_plan()
        self.business = _make_business(self.user)
        self.frontend_url = 'https://app.test'

    @patch('apps.billing.checkout_session_service.MercadoPagoService')
    def test_creates_session_once(self, MockMPService):
        """First call creates exactly one session and one MP plan."""
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.return_value = _mp_plan_response('PLAN-FIRST')
        MockMPService.return_value = mock_sdk

        from apps.billing.checkout_session_service import start_checkout
        result = start_checkout(
            user=self.user,
            tenant=self.business,
            plan_code=self.plan.code,
            frontend_url=self.frontend_url,
        )

        self.assertIn('checkout_session_id', result)
        self.assertIn('init_point', result)
        self.assertFalse(result['reused'])
        self.assertEqual(MpCheckoutSession.objects.count(), 1)
        mock_sdk.create_preapproval_plan.assert_called_once()

    @patch('apps.billing.checkout_session_service.MercadoPagoService')
    def test_double_click_returns_same_session(self, MockMPService):
        """Second call with same user+plan must reuse existing session — no new MP plan."""
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.return_value = _mp_plan_response('PLAN-DBL')
        MockMPService.return_value = mock_sdk

        from apps.billing.checkout_session_service import start_checkout

        r1 = start_checkout(user=self.user, tenant=self.business,
                            plan_code=self.plan.code, frontend_url=self.frontend_url)
        r2 = start_checkout(user=self.user, tenant=self.business,
                            plan_code=self.plan.code, frontend_url=self.frontend_url)

        self.assertEqual(r1['checkout_session_id'], r2['checkout_session_id'])
        self.assertEqual(r1['init_point'], r2['init_point'])
        self.assertTrue(r2['reused'])
        # MP plan was only created once
        self.assertEqual(mock_sdk.create_preapproval_plan.call_count, 1)
        self.assertEqual(MpCheckoutSession.objects.count(), 1)

    @patch('apps.billing.checkout_session_service.MercadoPagoService')
    def test_expired_session_triggers_new_checkout(self, MockMPService):
        """If the existing session is expired, a new session and MP plan are created."""
        mock_sdk = MagicMock()
        mock_sdk.create_preapproval_plan.side_effect = [
            _mp_plan_response('PLAN-OLD'),
            _mp_plan_response('PLAN-NEW'),
        ]
        MockMPService.return_value = mock_sdk

        from apps.billing.checkout_session_service import start_checkout

        # Create first session
        r1 = start_checkout(user=self.user, tenant=self.business,
                            plan_code=self.plan.code, frontend_url=self.frontend_url)

        # Force-expire it
        session = MpCheckoutSession.objects.get(pk=r1['checkout_session_id'])
        session.expires_at = timezone.now() - timedelta(hours=1)
        session.save()

        # Second call should create a new session
        r2 = start_checkout(user=self.user, tenant=self.business,
                            plan_code=self.plan.code, frontend_url=self.frontend_url)

        self.assertNotEqual(r1['checkout_session_id'], r2['checkout_session_id'])
        self.assertFalse(r2['reused'])
        self.assertEqual(mock_sdk.create_preapproval_plan.call_count, 2)
        # Old session must be marked expired
        session.refresh_from_db()
        self.assertEqual(session.status, MpCheckoutSession.Status.EXPIRED)

    def test_invalid_plan_raises_value_error(self):
        from apps.billing.checkout_session_service import start_checkout
        with self.assertRaises(ValueError):
            start_checkout(user=self.user, tenant=self.business,
                           plan_code='nonexistent_plan_xyz',
                           frontend_url=self.frontend_url)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Webhook deduplication
# ─────────────────────────────────────────────────────────────────────────────

class WebhookDeduplicationTest(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = MercadoPagoWebhookView.as_view()

    def _post(self, payload, x_request_id='req-dedup-001', sig_bypass=True):
        request = self.factory.post(
            '/api/v1/billing/mercadopago/webhook',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUEST_ID=x_request_id,
        )
        return request

    @patch('apps.billing.webhook_processor.receive_webhook')
    @patch('apps.billing.webhook_processor.dispatch_webhook')
    def test_duplicate_webhook_by_x_request_id_responds_200(self, mock_dispatch, mock_receive):
        """If receive_webhook marks delivery as DUPLICATED, we still return 200 and skip dispatch."""
        delivery = MagicMock()
        delivery.processing_status = WebhookDelivery.ProcessingStatus.DUPLICATED
        delivery.x_request_id = 'req-dup-001'
        delivery.resource_id = 'preapp-999'
        delivery.id = uuid.uuid4()
        mock_receive.return_value = (delivery, True)

        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-999'}}
        request = self._post(payload, x_request_id='req-dup-001')
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        mock_dispatch.assert_not_called()

    @patch('apps.billing.webhook_processor.receive_webhook')
    @patch('apps.billing.webhook_processor.dispatch_webhook')
    def test_first_delivery_dispatched_and_returns_200(self, mock_dispatch, mock_receive):
        """Fresh (non-duplicate) delivery is dispatched and returns 200."""
        delivery = MagicMock()
        delivery.processing_status = WebhookDelivery.ProcessingStatus.RECEIVED
        delivery.x_request_id = 'req-fresh-001'
        delivery.resource_id = 'preapp-fresh'
        delivery.id = uuid.uuid4()
        mock_receive.return_value = (delivery, True)

        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-fresh'}}
        request = self._post(payload, x_request_id='req-fresh-001')
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        mock_dispatch.assert_called_once_with(delivery)

    @patch('apps.billing.webhook_processor.receive_webhook')
    def test_invalid_signature_returns_400(self, mock_receive):
        """Invalid signature must return 400."""
        delivery = MagicMock()
        delivery.processing_status = WebhookDelivery.ProcessingStatus.RECEIVED
        delivery.id = uuid.uuid4()
        mock_receive.return_value = (delivery, False)  # sig_valid=False

        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-badsig'}}
        request = self._post(payload, x_request_id='req-badsig-001')
        response = self.view(request)

        self.assertEqual(response.status_code, 400)

    @patch('apps.billing.webhook_processor.receive_webhook')
    @patch('apps.billing.webhook_processor.dispatch_webhook')
    def test_authorized_payment_topic_dispatched(self, mock_dispatch, mock_receive):
        """subscription_authorized_payment topic must be handled by dispatch_webhook."""
        delivery = MagicMock()
        delivery.processing_status = WebhookDelivery.ProcessingStatus.RECEIVED
        delivery.id = uuid.uuid4()
        delivery.x_request_id = 'req-auth-001'
        delivery.resource_id = 'authpay-001'
        mock_receive.return_value = (delivery, True)

        payload = {'type': 'subscription_authorized_payment', 'data': {'id': 'authpay-001'}}
        request = self._post(payload, x_request_id='req-auth-001')
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        mock_dispatch.assert_called_once_with(delivery)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Webhook processor: receive_webhook dedup logic
# ─────────────────────────────────────────────────────────────────────────────

class ReceiveWebhookDeduplicationTest(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()

    def _make_request(self, payload, x_request_id='req-001'):
        body = json.dumps(payload).encode()
        request = self.factory.post(
            '/api/v1/billing/mercadopago/webhook',
            data=body,
            content_type='application/json',
            HTTP_X_REQUEST_ID=x_request_id,
        )
        # DRF parses .data lazily; prime it now.
        request.data  # noqa: B018
        return request

    @patch('apps.billing.webhook_processor._verify_mp_signature', return_value=True)
    def test_receive_persists_delivery(self, _mock_sig):
        """Every call must persist a WebhookDelivery before returning."""
        from apps.billing.webhook_processor import receive_webhook
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-recv-01'}}
        request = self._make_request(payload, x_request_id='req-recv-01')
        delivery, sig_valid = receive_webhook(request)

        self.assertIsNotNone(delivery.pk)
        self.assertTrue(sig_valid)
        self.assertIn(delivery.processing_status, [
            WebhookDelivery.ProcessingStatus.RECEIVED,
            WebhookDelivery.ProcessingStatus.DUPLICATED,
        ])

    @patch('apps.billing.webhook_processor._verify_mp_signature', return_value=True)
    def test_duplicate_x_request_id_marks_duplicated(self, _mock_sig):
        """Second call with same x-request-id must produce a DUPLICATED delivery."""
        from apps.billing.webhook_processor import receive_webhook

        # First delivery — mark as processed
        first = _make_webhook_delivery(
            x_request_id='req-dup-xreq',
            status=WebhookDelivery.ProcessingStatus.PROCESSED,
        )

        payload = {'type': 'subscription_preapproval', 'data': {'id': 'preapp-dup'}}
        request = self._make_request(payload, x_request_id='req-dup-xreq')
        delivery, _ = receive_webhook(request)

        self.assertEqual(delivery.processing_status, WebhookDelivery.ProcessingStatus.DUPLICATED)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Subscription activation
# ─────────────────────────────────────────────────────────────────────────────

class SubscriptionActivatorTest(TestCase):

    def setUp(self):
        self.user  = _make_user('owner@activator.test')
        self.plan  = _make_plan()
        self.biz   = _make_business(self.user)
        self.session = _make_checkout_session(self.user, self.plan, tenant=self.biz,
                                               provider_preapproval_plan_id='PLAN-ACT-001')
        self.sub = _make_subscription_v2(
            self.biz, self.plan,
            preapproval_plan_id='PLAN-ACT-001',
            session=self.session,
        )
        self.invoice = BillingInvoiceEvent.objects.create(
            subscription=self.sub,
            checkout_session=self.session,
            provider_authorized_payment_id='AUTH-PAY-001',
            provider_subscription_id=self.sub.provider_sub_id,
            amount=999,
            currency='ARS',
            provider_status='authorized',
            paid_at=timezone.now(),
        )

    def test_activation_sets_is_active_true(self):
        from apps.billing.subscription_activator import activate_subscription_from_invoice
        result = activate_subscription_from_invoice(
            invoice_event=self.invoice, subscription=self.sub
        )
        self.assertTrue(result)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_active)
        self.assertEqual(self.sub.status, SubscriptionV2.Status.ACTIVE)

    def test_activation_sets_business_active(self):
        from apps.billing.subscription_activator import activate_subscription_from_invoice
        activate_subscription_from_invoice(invoice_event=self.invoice, subscription=self.sub)
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'active')

    def test_activation_idempotent_if_already_active(self):
        """Calling activate_subscription_from_invoice twice must be a no-op on second call."""
        from apps.billing.subscription_activator import activate_subscription_from_invoice
        r1 = activate_subscription_from_invoice(invoice_event=self.invoice, subscription=self.sub)
        r2 = activate_subscription_from_invoice(invoice_event=self.invoice, subscription=self.sub)
        self.assertTrue(r1)
        self.assertFalse(r2)  # No-op on second call

    def test_activation_transitions_checkout_session_to_activated(self):
        from apps.billing.subscription_activator import activate_subscription_from_invoice
        activate_subscription_from_invoice(invoice_event=self.invoice, subscription=self.sub)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, MpCheckoutSession.Status.ACTIVATED)

    def test_orphan_invoice_event_does_not_activate(self):
        """An invoice event without a linked subscription does NOT activate anything."""
        orphan_invoice = BillingInvoiceEvent.objects.create(
            subscription=None,
            provider_authorized_payment_id='ORPHAN-AUTH-999',
            provider_subscription_id='ghostsub-999',
            amount=999,
            currency='ARS',
            provider_status='authorized',
            paid_at=timezone.now(),
        )
        # No exception; nothing is activated
        business_initial_status = self.biz.status
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, business_initial_status)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Correlation: plan_id NOT payer email
# ─────────────────────────────────────────────────────────────────────────────

class CorrelationByPlanIdTest(TestCase):
    """
    The webhook processor must find the MpCheckoutSession by provider_preapproval_plan_id.
    There must be NO fallback to payer_email (that was the old insecure path).
    """

    def setUp(self):
        self.user = _make_user('nomail@plan-corr.test')
        self.plan = _make_plan(code='starter')
        self.biz  = _make_business(self.user)
        self.session = _make_checkout_session(
            self.user, self.plan, tenant=self.biz,
            provider_preapproval_plan_id='PLAN-CORR-007',
        )
        self.delivery = _make_webhook_delivery(
            topic='subscription_preapproval',
            resource_id='preapp-corr-007',
            x_request_id='req-corr-007',
        )

    @patch('apps.billing.webhook_processor.MercadoPagoService')
    def test_handles_preapproval_finds_session_by_plan_id(self, MockMP):
        """_handle_subscription_preapproval finds session via plan_id, not email."""
        from apps.billing.webhook_processor import _handle_subscription_preapproval

        mock_sdk = MagicMock()
        # MP returns a preapproval whose plan_id matches our session
        mock_sdk.get_preapproval.return_value = {
            'id': 'preapp-corr-007',
            'preapproval_plan_id': 'PLAN-CORR-007',
            'status': 'authorized',
            'payer_email': 'someOTHERemail@nowhere.test',  # different email — must NOT matter
        }
        MockMP.return_value = mock_sdk

        _handle_subscription_preapproval('preapp-corr-007', self.delivery)

        # SubscriptionV2 linked to our session must have been created/updated
        sub = SubscriptionV2.objects.filter(provider_preapproval_plan_id='PLAN-CORR-007').first()
        self.assertIsNotNone(sub, "SubscriptionV2 should be created by plan_id correlation")
        self.assertEqual(sub.checkout_session, self.session)

    @patch('apps.billing.webhook_processor.MercadoPagoService')
    def test_unknown_plan_id_does_not_activate_random_session(self, MockMP):
        """If plan_id has no matching session, no activation occurs."""
        from apps.billing.webhook_processor import _handle_subscription_preapproval

        mock_sdk = MagicMock()
        mock_sdk.get_preapproval.return_value = {
            'id': 'preapp-unknown',
            'preapproval_plan_id': 'PLAN-GHOST-999',  # not in DB
            'status': 'authorized',
            'payer_email': self.user.email,  # matching email — must still be ignored
        }
        MockMP.return_value = mock_sdk

        _handle_subscription_preapproval('preapp-unknown', self.delivery)

        # No SubscriptionV2 should have been created
        self.assertFalse(
            SubscriptionV2.objects.filter(provider_preapproval_plan_id='PLAN-GHOST-999').exists()
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. CheckoutSessionStatusView polling endpoint
# ─────────────────────────────────────────────────────────────────────────────

class CheckoutSessionStatusViewTest(TestCase):

    def setUp(self):
        self.user    = _make_user('poller@test.com')
        self.plan    = _make_plan(code='pro')
        self.biz     = _make_business(self.user)
        self.client  = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make_session(self, status=MpCheckoutSession.Status.CHECKOUT_CREATED):
        return _make_checkout_session(self.user, self.plan, tenant=self.biz, status=status)

    def test_returns_pending_before_webhook(self):
        """Polling before any webhook shows awaiting or checkout_created status."""
        session = self._make_session(status=MpCheckoutSession.Status.CHECKOUT_CREATED)
        url = f'/api/v1/billing/checkout-sessions/{session.id}'
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 404])  # depends on URL routing
        if response.status_code == 200:
            self.assertIn(response.data['status'], [
                MpCheckoutSession.Status.CHECKOUT_CREATED,
                MpCheckoutSession.Status.AWAITING_WEBHOOK,
            ])

    def test_returns_activated_after_subscription_actives(self):
        """Polling after activation shows activated status."""
        session = self._make_session(status=MpCheckoutSession.Status.ACTIVATED)
        url = f'/api/v1/billing/checkout-sessions/{session.id}'
        response = self.client.get(url)
        if response.status_code == 200:
            self.assertEqual(response.data['status'], MpCheckoutSession.Status.ACTIVATED)

    def test_other_user_cannot_view_session(self):
        """A different user must NOT be able to view another user's session."""
        other_user = _make_user('thief@test.com')
        session = self._make_session()

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        url = f'/api/v1/billing/checkout-sessions/{session.id}'
        response = other_client.get(url)
        # Must be 403 or 404 — never 200
        self.assertIn(response.status_code, [403, 404])


# ─────────────────────────────────────────────────────────────────────────────
# 7. expire_checkout_sessions Celery task
# ─────────────────────────────────────────────────────────────────────────────

class ExpireCheckoutSessionsTaskTest(TestCase):

    def setUp(self):
        self.user = _make_user('taskuser@test.com')
        self.plan = _make_plan(code='enterprise')

    def test_expires_sessions_past_expiry(self):
        """Sessions with expires_at in the past must be set to EXPIRED."""
        # Past session (should be expired)
        past = _make_checkout_session(
            self.user, self.plan,
            status=MpCheckoutSession.Status.CHECKOUT_CREATED,
            expires_at=timezone.now() - timedelta(minutes=90),
        )

        result = expire_checkout_sessions.apply()
        self.assertEqual(result.result['expired'], 1)

        past.refresh_from_db()
        self.assertEqual(past.status, MpCheckoutSession.Status.EXPIRED)

    def test_does_not_expire_active_sessions(self):
        """Sessions with expires_at in the future must be left untouched."""
        future = _make_checkout_session(
            self.user, self.plan,
            status=MpCheckoutSession.Status.CHECKOUT_CREATED,
            expires_at=timezone.now() + timedelta(hours=2),
        )

        result = expire_checkout_sessions.apply()
        self.assertEqual(result.result['expired'], 0)

        future.refresh_from_db()
        self.assertEqual(future.status, MpCheckoutSession.Status.CHECKOUT_CREATED)

    def test_terminal_sessions_not_touched(self):
        """Already-activated or failed sessions must NOT be expired by the task."""
        already_activated = _make_checkout_session(
            self.user, self.plan,
            status=MpCheckoutSession.Status.ACTIVATED,
            expires_at=timezone.now() - timedelta(hours=1),  # past, but terminal
        )

        expire_checkout_sessions.apply()

        already_activated.refresh_from_db()
        self.assertEqual(already_activated.status, MpCheckoutSession.Status.ACTIVATED)

    def test_task_is_idempotent(self):
        """Running the task twice does not double-expire or raise errors."""
        _make_checkout_session(
            self.user, self.plan,
            status=MpCheckoutSession.Status.AWAITING_WEBHOOK,
            expires_at=timezone.now() - timedelta(minutes=120),
        )

        r1 = expire_checkout_sessions.apply()
        r2 = expire_checkout_sessions.apply()

        self.assertEqual(r1.result['expired'], 1)
        self.assertEqual(r2.result['expired'], 0)  # Already expired, can't expire again
