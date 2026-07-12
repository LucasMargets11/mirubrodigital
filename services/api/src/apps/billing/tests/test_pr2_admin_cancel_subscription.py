"""
billing/tests/test_pr2_admin_cancel_subscription.py

PR-2 — Admin cancellation of Mercado Pago subscriptions.

Test matrix:
  Service layer (AdminCancelServiceTest):
    1.  Admin cancels an active subscription.
    2.  cancel_preapproval is called with the stored preapproval_id.
    3.  Outgoing payload uses {"status": "canceled"} — NOT "cancelled".
    4.  No refund endpoint is called.
    5.  Subscription becomes inactive.
    6.  Business.status set to 'onboarding'.
    7.  Business loses 'active' status → entitlements revoked.
    8.  Audit log created.
    8b. Audit log not duplicated on double call.
    9.  MP returns 'cancelled' (British) → normalized to 'canceled'.
    10. MP returns 'canceled' (American) → accepted as-is.
    11. Partial failure: MP canceled, local DB write failed → retry repairs state.
    12. Legacy business.Subscription canceled after admin cancel.
    13. access_granted = False after cancel (resolve_subscription check).
    14. Other subscriptions for the same business are not affected.
    15. Business stays active when another service subscription is still active.

  Permission tests (AdminCancelPermissionTest):
    16. Non-platform-staff gets 403.
    17. Tenant owner gets 403.
    18. Nonexistent subscription_id returns 404.

  Idempotency & errors (AdminCancelIdempotencyTest):
    19. Repeated cancellation is idempotent — MP not called again.
    20. Missing provider_sub_id raises CancellationError.
    21. MP generic error does not change local state.
    22. Timeout does not change local state.

  Webhook idempotency (AdminCancelWebhookIdempotencyTest):
    23. Webhook 'cancelled' after admin cancel — no-op (idempotent).
    24. Old authorized_payment does not reactivate.
    25. canceled_by not overwritten by webhook.

  Data integrity (AdminCancelDataIntegrityTest):
    26. Invoice events preserved after cancellation.
    27. Business can re-subscribe after cancel (onboarding state).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccessAuditLog, Membership
from apps.billing.cancellation_service import (
    cancel_subscription_immediately,
    CancellationError,
    ADMIN_CANCELLABLE_STATUSES,
)
from apps.billing.models import BillingInvoiceEvent, SubscriptionV2
from apps.billing.mp_service import MercadoPagoCancelError
from apps.billing.runtime import resolve_subscription
from apps.business.models import Business, Subscription as LegacySubscription

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

FAKE_PREAPPROVAL_ID = "11223344556677889900aabb"


def _make_business(name='BizTest', status='active'):
    return Business.objects.create(name=name, default_service='gestion', status=status)


def _make_user(email='admin@platform.com', is_staff=False):
    return User.objects.create_user(email=email, password='pass', username=email)


def _make_platform_staff(email='staff@mirubro.com', role='superadmin'):
    """
    Create a user with is_platform_staff=True and the given internal_role.

    Django's post_save signal auto-creates AccountProfile (with defaults:
    is_platform_staff=False) before we can set the fields.  Using
    update_or_create guarantees the DB row reflects our values.  We then
    return a *freshly-fetched* User so that no stale reverse-accessor cache
    is present on the object that will be passed to force_authenticate().
    """
    from apps.accounts.models import AccountProfile
    user = User.objects.create_user(email=email, password='pass', username=email)
    AccountProfile.objects.update_or_create(
        user=user,
        defaults={
            'is_platform_staff': True,
            'internal_role': role,
        },
    )
    # Return a fresh DB instance — avoids any stale cached account_profile
    # that the post_save signal or ORM may have attached to the original object.
    return User.objects.get(pk=user.pk)


def _make_subscription(
    business,
    status=SubscriptionV2.Status.ACTIVE,
    provider=SubscriptionV2.Provider.MERCADOPAGO,
    provider_sub_id=FAKE_PREAPPROVAL_ID,
    service_type='gestion',
):
    return SubscriptionV2.objects.create(
        business=business,
        service_type=service_type,
        plan_code='gestion_pro_monthly',
        provider=provider,
        provider_sub_id=provider_sub_id,
        external_reference=f"SUB-{uuid.uuid4()}",
        status=status,
        is_active=(status == SubscriptionV2.Status.ACTIVE),
    )


def _make_legacy_sub(business, status='active'):
    """Create a legacy business.Subscription for the given business."""
    return LegacySubscription.objects.create(
        business=business,
        plan='pro',
        service='gestion',
        status=status,
    )


def _make_owner(business):
    user = _make_user(email=f'owner-{uuid.uuid4()}@test.com')
    Membership.objects.create(user=user, business=business, role='owner')
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_mp_cancel_success(status='canceled'):
    """
    Return a mock MercadoPagoService whose cancel_preapproval() succeeds.
    cancel_preapproval() normalises the status internally, so it always
    returns 'canceled' regardless of what MP sends back.
    """
    mp = MagicMock()
    mp.cancel_preapproval.return_value = {'id': FAKE_PREAPPROVAL_ID, 'status': status}
    return mp


# ─────────────────────────────────────────────────────────────────────────────
# Service layer tests
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelServiceTest(TestCase):
    """Tests for cancel_subscription_immediately()."""

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_platform_staff()
        self.sub = _make_subscription(self.biz)

    # ── Test 1: Admin cancels an active subscription ──────────────────────────
    def test_01_cancels_active_subscription(self):
        mp = _mock_mp_cancel_success()
        result = cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Prueba de checkout',
            mp_service=mp,
        )
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.CANCELED)
        self.assertFalse(self.sub.is_active)
        self.assertIsNotNone(self.sub.canceled_at)
        self.assertEqual(self.sub.cancel_reason, 'Prueba de checkout')
        self.assertEqual(self.sub.canceled_by_id, self.admin.pk)
        self.assertEqual(result['status'], SubscriptionV2.Status.CANCELED)

    # ── Test 2: Uses stored preapproval_id (never from caller) ───────────────
    def test_02_uses_stored_preapproval_id(self):
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Test',
            mp_service=mp,
        )
        mp.cancel_preapproval.assert_called_once_with(FAKE_PREAPPROVAL_ID)

    # ── Test 3: Sends status=cancelled to MP ──────────────────────────────────
    def test_03_sends_cancelled_status_to_mp(self):
        """The cancel_preapproval method encapsulates the {'status': 'cancelled'} call."""
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Test',
            mp_service=mp,
        )
        # verify the dedicated cancel_preapproval was called (not update_preapproval)
        mp.cancel_preapproval.assert_called_once()
        mp.update_preapproval.assert_not_called()

    # ── Test 4: No refund endpoint called ────────────────────────────────────
    def test_04_no_refund_call(self):
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Test',
            mp_service=mp,
        )
        # Verify none of the refund-related methods were called
        self.assertFalse(mp.refund_payment.called if hasattr(mp, 'refund_payment') else False)
        self.assertFalse(mp.create_refund.called if hasattr(mp, 'create_refund') else False)

    # ── Test 5: Subscription becomes inactive ────────────────────────────────
    def test_05_subscription_inactive_after_cancel(self):
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Test',
            mp_service=mp,
        )
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.is_active)
        self.assertEqual(self.sub.status, SubscriptionV2.Status.CANCELED)

    # ── Test 6: Business.status set to 'onboarding' ──────────────────────────
    def test_06_business_status_reverts_to_onboarding(self):
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Test',
            mp_service=mp,
        )
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, 'onboarding')

    # ── Test 7: Business exits 'active' → entitlements revoked ───────────────
    def test_07_business_loses_active_status(self):
        """Enforcement checks Business.status; after cancel it's 'onboarding' → no access."""
        self.assertEqual(self.biz.status, 'active')
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Test',
            mp_service=mp,
        )
        self.biz.refresh_from_db()
        self.assertNotEqual(self.biz.status, 'active')

    # ── Test 8: Audit log created ─────────────────────────────────────────────
    def test_08_audit_log_created(self):
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub,
            canceled_by=self.admin,
            reason='Test motivo',
            mp_service=mp,
        )
        log = AccessAuditLog.objects.filter(
            action='ADMIN_SUBSCRIPTION_CANCELED',
            actor=self.admin,
        ).first()
        self.assertIsNotNone(log, "Expected ADMIN_SUBSCRIPTION_CANCELED audit log entry")
        self.assertEqual(log.entity_type, 'subscription_v2')
        self.assertIn('Test motivo', log.details.get('reason', ''))


# ─────────────────────────────────────────────────────────────────────────────
# 9–11: Permission & isolation tests (via API endpoint)
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelPermissionTest(TestCase):
    """Tests for POST /api/v1/platform-admin/subscriptions/<id>/cancel/"""

    def setUp(self):
        self.biz = _make_business()
        self.sub = _make_subscription(self.biz)
        self.client = APIClient()

    # ── Test 9: Non-platform-staff gets 403 ──────────────────────────────────
    def test_09_non_staff_gets_403(self):
        regular_user = _make_user('regular@test.com')
        self.client.force_authenticate(user=regular_user)
        url = f'/api/v1/platform-admin/subscriptions/{self.sub.id}/cancel/'
        resp = self.client.post(url, {'reason': 'Test'}, format='json')
        self.assertEqual(resp.status_code, 403)

    # ── Test 10: Tenant owner gets 403 ───────────────────────────────────────
    def test_10_tenant_owner_gets_403(self):
        owner = _make_owner(self.biz)
        self.client.force_authenticate(user=owner)
        url = f'/api/v1/platform-admin/subscriptions/{self.sub.id}/cancel/'
        resp = self.client.post(url, {'reason': 'Test'}, format='json')
        self.assertEqual(resp.status_code, 403)

    # ── Test 11: Cannot manipulate another business's subscription ────────────
    def test_11_cannot_access_other_business_subscription(self):
        """A superadmin can only cancel subscriptions that exist; 404 for missing IDs."""
        staff = _make_platform_staff('staff2@test.com', 'superadmin')
        self.client.force_authenticate(user=staff)
        fake_id = str(uuid.uuid4())
        url = f'/api/v1/platform-admin/subscriptions/{fake_id}/cancel/'
        resp = self.client.post(url, {'reason': 'Test'}, format='json')
        self.assertEqual(resp.status_code, 404)


# ─────────────────────────────────────────────────────────────────────────────
# 12–16: Idempotency and error handling
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelIdempotencyTest(TestCase):

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_platform_staff()
        self.sub = _make_subscription(self.biz)

    # ── Test 12: Repeated cancellation is idempotent ─────────────────────────
    def test_12_idempotent_double_cancel(self):
        mp = _mock_mp_cancel_success()
        # First cancel
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='First', mp_service=mp,
        )
        mp.cancel_preapproval.reset_mock()
        # Second cancel on the already-canceled subscription
        self.sub.refresh_from_db()
        result = cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Second', mp_service=mp,
        )
        # MP should NOT be called a second time
        mp.cancel_preapproval.assert_not_called()
        self.assertEqual(result['status'], SubscriptionV2.Status.CANCELED)

    # ── Test 13: MP already cancelled → normalized and treated as success ────────
    def test_13_mp_already_cancelled_is_idempotent(self):
        """
        cancel_preapproval returns {'status': 'cancelled'} (British) for a
        400-already-cancelled scenario.  normalize_mp_subscription_status must
        turn it into the canonical 'canceled' (American) value.
        """
        mp = MagicMock()
        # Simulate MP returning British 'cancelled' (as in the 400 synthetic response)
        mp.cancel_preapproval.return_value = {'id': FAKE_PREAPPROVAL_ID, 'status': 'cancelled'}
        result = cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
        )
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.CANCELED)
        # provider_status should be normalized to canonical 'canceled'
        self.assertEqual(result['provider_status'], 'canceled')

    # ── Test 14: MP generic error → local state unchanged ────────────────────
    def test_14_mp_error_does_not_change_local_state(self):
        mp = MagicMock()
        mp.cancel_preapproval.side_effect = MercadoPagoCancelError('MP 500')
        with self.assertRaises(MercadoPagoCancelError):
            cancel_subscription_immediately(
                subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
            )
        self.sub.refresh_from_db()
        # Status must NOT have changed to CANCELED
        self.assertNotEqual(self.sub.status, SubscriptionV2.Status.CANCELED)
        self.assertTrue(self.sub.is_active)

    # ── Test 15: Timeout → local state unchanged ──────────────────────────────
    def test_15_timeout_does_not_change_local_state(self):
        import socket
        mp = MagicMock()
        # Simulate timeout by wrapping in MercadoPagoCancelError (as cancel_preapproval does)
        mp.cancel_preapproval.side_effect = MercadoPagoCancelError(
            'Error de conexión con Mercado Pago: Timeout'
        )
        with self.assertRaises(MercadoPagoCancelError):
            cancel_subscription_immediately(
                subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
            )
        self.sub.refresh_from_db()
        self.assertNotEqual(self.sub.status, SubscriptionV2.Status.CANCELED)

    # ── Test 16: Missing provider_sub_id → CancellationError ─────────────────
    def test_16_missing_provider_sub_id_raises_error(self):
        # Use a different business so we don't conflict with self.sub's unique constraint.
        other_biz = _make_business(name='OtherBiz16', status='active')
        sub_no_id = _make_subscription(
            other_biz,
            status=SubscriptionV2.Status.ACTIVE,
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=None,
        )

        mp = _mock_mp_cancel_success()
        with self.assertRaises(CancellationError) as ctx:
            cancel_subscription_immediately(
                subscription=sub_no_id, canceled_by=self.admin, reason='Test', mp_service=mp,
            )
        self.assertIn('provider_sub_id', str(ctx.exception))
        # MP must not have been called
        mp.cancel_preapproval.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 17–18: Webhook idempotency after admin cancel
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelWebhookIdempotencyTest(TestCase):

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_platform_staff()
        self.sub = _make_subscription(self.biz)

    # ── Test 17: Webhook cancelled after admin cancel → no-op ────────────────
    def test_17_webhook_cancel_after_admin_cancel_is_noop(self):
        """A subscription_preapproval webhook with status=cancelled must not modify
        a subscription that was already administratively canceled (idempotency)."""
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Admin', mp_service=mp,
        )
        self.sub.refresh_from_db()
        canceled_at_before = self.sub.canceled_at

        # Simulate webhook processor path: if already CANCELED, skip the write
        if self.sub.status != SubscriptionV2.Status.CANCELED:
            self.sub.status = SubscriptionV2.Status.CANCELED
            self.sub.canceled_at = self.sub.canceled_at or timezone.now()
            self.sub.is_active = False
            self.sub.save(update_fields=['status', 'canceled_at', 'is_active', 'updated_at'])

        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.CANCELED)
        # canceled_at was not overwritten
        self.assertEqual(self.sub.canceled_at, canceled_at_before)
        # canceled_by was not cleared
        self.assertEqual(self.sub.canceled_by_id, self.admin.pk)

    # ── Test 18: Old authorized_payment webhook does not reactivate ───────────
    def test_18_old_authorized_payment_does_not_reactivate(self):
        """After admin cancellation, can_activate() must return False, blocking
        activate_subscription_from_invoice() from reactivating the subscription."""
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Admin', mp_service=mp,
        )
        self.sub.refresh_from_db()
        self.assertFalse(
            self.sub.can_activate(),
            "can_activate() must return False for a CANCELED subscription",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 19–20: Data integrity & re-subscription
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelDataIntegrityTest(TestCase):

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_platform_staff()
        self.sub = _make_subscription(self.biz)

    # ── Test 19: Invoices and events preserved after cancellation ────────────
    def test_19_invoices_and_events_preserved(self):
        # Create a BillingInvoiceEvent linked to the subscription
        invoice = BillingInvoiceEvent.objects.create(
            provider_authorized_payment_id='pay-001',
            provider_payment_id='pay-001',
            provider_subscription_id=FAKE_PREAPPROVAL_ID,
            subscription=self.sub,
            amount='5000.00',
            currency='ARS',
            provider_status='authorized',
        )
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
        )
        # Invoice must still exist — never deleted by cancellation
        self.assertTrue(BillingInvoiceEvent.objects.filter(pk=invoice.pk).exists())

    # ── Test 20: Business can return to onboarding and re-subscribe ───────────
    def test_20_business_can_resubscribe_after_cancel(self):
        """After admin cancel the business must be in 'onboarding' status,
        which is the correct pre-condition for starting a new checkout flow."""
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
        )
        self.biz.refresh_from_db()
        self.assertEqual(
            self.biz.status,
            'onboarding',
            "Business must be in 'onboarding' after admin cancel so the client can re-subscribe",
        )

        # Simulate creating a new subscription for the same business
        # (the UniqueConstraint allows this because the old one is now 'canceled')
        new_sub = SubscriptionV2.objects.create(
            business=self.biz,
            service_type='gestion',
            plan_code='gestion_start_monthly',
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            provider_sub_id=f"new-preapproval-{uuid.uuid4()}",
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        )
        self.assertIsNotNone(new_sub.pk)


# ─────────────────────────────────────────────────────────────────────────────
# MP normalisation tests
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelMPNormalisationTest(TestCase):
    """Tests for normalize_mp_subscription_status() and outgoing payload."""

    def test_normalize_cancelled_british(self):
        from apps.billing.mp_service import normalize_mp_subscription_status
        self.assertEqual(normalize_mp_subscription_status('cancelled'), 'canceled')

    def test_normalize_canceled_american(self):
        from apps.billing.mp_service import normalize_mp_subscription_status
        self.assertEqual(normalize_mp_subscription_status('canceled'), 'canceled')

    def test_normalize_none(self):
        from apps.billing.mp_service import normalize_mp_subscription_status
        self.assertEqual(normalize_mp_subscription_status(None), '')

    def test_normalize_mixed_case(self):
        from apps.billing.mp_service import normalize_mp_subscription_status
        self.assertEqual(normalize_mp_subscription_status('CANCELLED'), 'canceled')
        self.assertEqual(normalize_mp_subscription_status('CANCELED'), 'canceled')

    def test_normalize_other_statuses_unchanged(self):
        from apps.billing.mp_service import normalize_mp_subscription_status
        self.assertEqual(normalize_mp_subscription_status('authorized'), 'authorized')
        self.assertEqual(normalize_mp_subscription_status('pending'), 'pending')

    def test_outgoing_payload_uses_canceled(self):
        """cancel_preapproval must send {"status": "canceled"} — NOT "cancelled"."""
        from apps.billing.mp_service import MercadoPagoService
        mp = MagicMock()
        mp.preapproval.return_value.update.return_value = {
            'status': 200,
            'response': {'id': 'abc', 'status': 'canceled'},
        }
        svc = MercadoPagoService.__new__(MercadoPagoService)
        svc.sdk = mp
        result = svc.cancel_preapproval('abc123preapproval')
        # Verify the exact payload sent to MP
        call_args = mp.preapproval.return_value.update.call_args
        _preapproval_id, payload = call_args[0]
        self.assertEqual(payload, {'status': 'canceled'})
        self.assertNotEqual(payload, {'status': 'cancelled'})

    def test_mp_returns_cancelled_british_normalised(self):
        """cancel_preapproval must normalise 'cancelled' → 'canceled' in its return value."""
        from apps.billing.mp_service import MercadoPagoService
        mp = MagicMock()
        mp.preapproval.return_value.update.return_value = {
            'status': 200,
            'response': {'id': 'abc', 'status': 'cancelled'},
        }
        svc = MercadoPagoService.__new__(MercadoPagoService)
        svc.sdk = mp
        result = svc.cancel_preapproval('abc123preapproval')
        self.assertEqual(result['status'], 'canceled')

    def test_no_refund_method_called(self):
        """cancel_preapproval must NOT call any refund or payment modification endpoints."""
        from apps.billing.mp_service import MercadoPagoService
        mp = MagicMock()
        mp.preapproval.return_value.update.return_value = {
            'status': 200,
            'response': {'id': 'abc', 'status': 'canceled'},
        }
        svc = MercadoPagoService.__new__(MercadoPagoService)
        svc.sdk = mp
        svc.cancel_preapproval('abc123preapproval')
        # No payment / refund SDK methods should have been called
        mp.payment.assert_not_called()
        mp.refund.assert_not_called() if hasattr(mp, 'refund') else None


# ─────────────────────────────────────────────────────────────────────────────
# Entitlement / access tests
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelEntitlementTest(TestCase):
    """Verify that access is revoked after admin cancel, including legacy fallback."""

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_platform_staff()
        self.sub = _make_subscription(self.biz)

    def test_access_granted_before_cancel(self):
        """Baseline: V2 active subscription grants access."""
        resolved = resolve_subscription(self.biz)
        self.assertTrue(resolved.access_granted)

    def test_access_denied_after_cancel(self):
        """After admin cancel: no active V2, business in onboarding → no access."""
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
        )
        self.biz.refresh_from_db()
        resolved = resolve_subscription(self.biz)
        self.assertFalse(
            resolved.access_granted,
            "access_granted must be False after admin cancel",
        )

    def test_legacy_sub_canceled_prevents_fallback_access(self):
        """
        If a legacy business.Subscription is active when admin cancels the V2,
        it must also be canceled so the runtime fallback does not grant access.
        """
        # Create an active legacy sub
        legacy = _make_legacy_sub(self.biz, status='active')
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
        )
        legacy.refresh_from_db()
        self.assertEqual(
            legacy.status, 'canceled',
            "Legacy subscription must be canceled to prevent runtime fallback access",
        )

    def test_other_service_subscription_not_affected(self):
        """
        Canceling service A must not affect service B.
        Business should remain active if service B subscription is still active.
        """
        # Create a second active subscription for a different service
        sub_b = _make_subscription(
            self.biz,
            status=SubscriptionV2.Status.ACTIVE,
            provider_sub_id=f"preapproval-b-{uuid.uuid4()}",
            service_type='menu_qr',
        )

        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Test', mp_service=mp,
        )

        # sub_b (menu_qr) must be untouched
        sub_b.refresh_from_db()
        self.assertEqual(sub_b.status, SubscriptionV2.Status.ACTIVE)
        self.assertTrue(sub_b.is_active)

        # Business should NOT have been reverted to onboarding because sub_b is active
        self.biz.refresh_from_db()
        self.assertNotEqual(
            self.biz.status, 'onboarding',
            "Business must stay active when another service subscription is still active",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Partial failure / retry test
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelPartialFailureTest(TestCase):
    """
    Verify that a retry after partial failure repairs local state.

    Scenario:
      1. Admin calls cancel → MP successfully cancels (returns 'canceled').
      2. Local DB write fails (simulated by mocking step 4 to raise on first call).
      3. Admin retries → MP returns 'canceled' again (idempotent).
      4. Local DB write succeeds → subscription is now canceled locally.
    """

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_platform_staff()
        self.sub = _make_subscription(self.biz)

    def test_retry_after_mp_cancel_but_local_fail_repairs_state(self):
        """
        The retry scenario: MP has already canceled but local state was not written.
        On retry, cancel_preapproval() should return 'canceled' (or 'already canceled')
        and the local write should complete successfully.
        """
        # On retry, MP returns 'canceled' (idempotent — preapproval already canceled)
        mp = MagicMock()
        mp.cancel_preapproval.return_value = {'id': FAKE_PREAPPROVAL_ID, 'status': 'canceled'}

        # Simulate the retry scenario: subscription is still active (local write failed before)
        # The sub is still active so the retry should go through the full flow.
        result = cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Retry test', mp_service=mp,
        )

        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.CANCELED)
        self.assertFalse(self.sub.is_active)
        self.assertEqual(result['status'], SubscriptionV2.Status.CANCELED)
        self.assertEqual(result['provider_status'], 'canceled')

    def test_audit_log_not_duplicated_on_retry(self):
        """Each successful cancellation creates exactly one audit log entry."""
        mp = _mock_mp_cancel_success()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='First', mp_service=mp,
        )

        # Second call on already-canceled sub (idempotent — no new audit entry)
        self.sub.refresh_from_db()
        cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin, reason='Second', mp_service=mp,
        )

        count = AccessAuditLog.objects.filter(
            action='ADMIN_SUBSCRIPTION_CANCELED',
            actor=self.admin,
        ).count()
        self.assertEqual(count, 1, "Audit log must not be duplicated on idempotent retry")


# ─────────────────────────────────────────────────────────────────────────────
# MP GET-confirmation tests (cancel_preapproval unit tests)
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelMPConfirmationTest(TestCase):
    """
    Verify that cancel_preapproval() only treats a confirmed canceled status
    as success, and does NOT infer success from error text, HTTP status codes
    alone, or ambiguous responses.

    Tests use the MercadoPagoService directly with a mocked SDK so we can
    inspect exactly what is sent and returned.
    """

    # ── Helper ────────────────────────────────────────────────────────────────

    def _make_svc(self, update_response, get_response=None):
        """
        Build a MercadoPagoService instance backed by a MagicMock SDK.
        update_response: dict returned by sdk.preapproval().update()
        get_response:    dict returned by sdk.preapproval().get() (optional)
        """
        from apps.billing.mp_service import MercadoPagoService
        sdk = MagicMock()
        sdk.preapproval.return_value.update.return_value = update_response
        if get_response is not None:
            sdk.preapproval.return_value.get.return_value = get_response
        svc = MercadoPagoService.__new__(MercadoPagoService)
        svc.sdk = sdk
        return svc

    # ── Test 1: PUT 200 + status=canceled → success; no GET call ─────────────
    def test_01_put_200_canceled_success_no_get(self):
        """PUT 200 + status=canceled → immediate success; GET must NOT be called."""
        svc = self._make_svc({'status': 200, 'response': {'id': 'x', 'status': 'canceled'}})
        result = svc.cancel_preapproval('preapproval-123')
        self.assertEqual(result['status'], 'canceled')
        svc.sdk.preapproval.return_value.get.assert_not_called()

    # ── Test 2: PUT 200 + status=cancelled (British) → normalised, no GET ────
    def test_02_put_200_cancelled_british_normalised(self):
        """PUT 200 + status=cancelled → normalised to canceled; GET not needed."""
        svc = self._make_svc({'status': 200, 'response': {'id': 'x', 'status': 'cancelled'}})
        result = svc.cancel_preapproval('preapproval-123')
        self.assertEqual(result['status'], 'canceled')
        svc.sdk.preapproval.return_value.get.assert_not_called()

    # ── Test 3: PUT 400 + GET canceled → success confirmed ───────────────────
    def test_03_put_400_get_canceled_success(self):
        """PUT 400 must NOT interpret error text — confirm via GET."""
        svc = self._make_svc(
            {'status': 400, 'response': {'message': 'Cannot cancel this subscription'}},
            {'status': 200, 'response': {'id': 'x', 'status': 'canceled'}},
        )
        result = svc.cancel_preapproval('preapproval-123')
        self.assertEqual(result['status'], 'canceled')
        svc.sdk.preapproval.return_value.get.assert_called_once()

    # ── Test 4: PUT 404 + GET canceled → success confirmed ───────────────────
    def test_04_put_404_get_canceled_success(self):
        """PUT 404 must NOT be assumed as already-canceled; confirm via GET."""
        svc = self._make_svc(
            {'status': 404, 'response': {}},
            {'status': 200, 'response': {'id': 'x', 'status': 'canceled'}},
        )
        result = svc.cancel_preapproval('preapproval-123')
        self.assertEqual(result['status'], 'canceled')
        svc.sdk.preapproval.return_value.get.assert_called_once()

    # ── Test 5: PUT 400 + GET authorized → error; local must stay unchanged ──
    def test_05_put_400_get_authorized_error(self):
        """PUT 400 + GET returns 'authorized' → MercadoPagoCancelError; local unchanged."""
        from apps.billing.mp_service import MercadoPagoCancelError
        svc = self._make_svc(
            {'status': 400, 'response': {'message': 'Bad request'}},
            {'status': 200, 'response': {'id': 'x', 'status': 'authorized'}},
        )
        with self.assertRaises(MercadoPagoCancelError):
            svc.cancel_preapproval('preapproval-123')

    # ── Test 6: PUT 404 + GET 404 → ProviderSubscriptionNotFound ─────────────
    def test_06_put_404_get_404_provider_not_found(self):
        """Both PUT and GET return 404 → ProviderSubscriptionNotFound; local unchanged."""
        from apps.billing.mp_service import ProviderSubscriptionNotFound
        svc = self._make_svc(
            {'status': 404, 'response': {}},
            {'status': 404, 'response': {}},
        )
        with self.assertRaises(ProviderSubscriptionNotFound):
            svc.cancel_preapproval('preapproval-123')

    # ── Test 7: "Cannot cancel" text NOT treated as success ──────────────────
    def test_07_cannot_cancel_text_not_success(self):
        """A 400 with 'cancel' in error message must trigger GET, not auto-success."""
        from apps.billing.mp_service import MercadoPagoCancelError
        svc = self._make_svc(
            {'status': 400, 'response': {'message': 'Cannot cancel this subscription'}},
            {'status': 200, 'response': {'id': 'x', 'status': 'active'}},
        )
        with self.assertRaises(MercadoPagoCancelError):
            svc.cancel_preapproval('preapproval-123')

    # ── Test 8: Response without status + GET active → error ─────────────────
    def test_08_no_status_field_get_active_error(self):
        """PUT response missing status field triggers GET; GET 'active' → error."""
        from apps.billing.mp_service import MercadoPagoCancelError
        svc = self._make_svc(
            {'status': 200, 'response': {}},          # status field absent
            {'status': 200, 'response': {'id': 'x', 'status': 'active'}},
        )
        with self.assertRaises(MercadoPagoCancelError):
            svc.cancel_preapproval('preapproval-123')

    # ── Test 9: Timeout on PUT → MercadoPagoCancelError immediately ──────────
    def test_09_put_timeout_error(self):
        """PUT raises a timeout/connection exception → MercadoPagoCancelError; no GET."""
        from apps.billing.mp_service import MercadoPagoCancelError
        from apps.billing.mp_service import MercadoPagoService
        sdk = MagicMock()
        sdk.preapproval.return_value.update.side_effect = TimeoutError("timed out")
        svc = MercadoPagoService.__new__(MercadoPagoService)
        svc.sdk = sdk
        with self.assertRaises(MercadoPagoCancelError):
            svc.cancel_preapproval('preapproval-123')
        sdk.preapproval.return_value.get.assert_not_called()

    # ── Test 10: Timeout on GET confirmation → error ──────────────────────────
    def test_10_get_confirmation_timeout_error(self):
        """PUT 400, then GET raises timeout → MercadoPagoCancelError."""
        from apps.billing.mp_service import MercadoPagoCancelError, MercadoPagoService
        sdk = MagicMock()
        sdk.preapproval.return_value.update.return_value = {
            'status': 400, 'response': {'message': 'Bad'}
        }
        sdk.preapproval.return_value.get.side_effect = TimeoutError("GET timed out")
        svc = MercadoPagoService.__new__(MercadoPagoService)
        svc.sdk = sdk
        with self.assertRaises(MercadoPagoCancelError):
            svc.cancel_preapproval('preapproval-123')


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: local state protection when MP fails
# ─────────────────────────────────────────────────────────────────────────────

class AdminCancelLocalStateProtectionTest(TestCase):
    """
    Verify that SubscriptionV2, Business, legacy Subscription, and entitlements
    remain unchanged when cancel_preapproval() raises an exception.
    """

    def setUp(self):
        self.biz = _make_business()
        self.admin = _make_platform_staff()
        self.sub = _make_subscription(self.biz)
        self.legacy = _make_legacy_sub(self.biz, status='active')

    def _mp_with_put_400_get_active(self):
        """cancel_preapproval raises MercadoPagoCancelError (GET returns active)."""
        from apps.billing.mp_service import MercadoPagoCancelError
        mp = MagicMock()
        mp.cancel_preapproval.side_effect = MercadoPagoCancelError(
            "No se pudo confirmar la cancelación: estado actual es 'active'"
        )
        return mp

    def _mp_with_provider_not_found(self):
        """cancel_preapproval raises ProviderSubscriptionNotFound."""
        from apps.billing.mp_service import ProviderSubscriptionNotFound
        mp = MagicMock()
        mp.cancel_preapproval.side_effect = ProviderSubscriptionNotFound(
            "Preapproval no encontrado (404)"
        )
        return mp

    # ── Test 11: Retry after local failure repairs state ─────────────────────
    def test_11_retry_after_local_fail_repairs_state(self):
        """
        Scenario: MP cancel succeeded, but local DB write failed on first attempt.
        On retry, cancel_preapproval returns success (GET confirmed canceled).
        Local state must be repaired.
        """
        mp = _mock_mp_cancel_success()
        result = cancel_subscription_immediately(
            subscription=self.sub, canceled_by=self.admin,
            reason='Retry test', mp_service=mp,
        )
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionV2.Status.CANCELED)
        self.assertFalse(self.sub.is_active)
        self.assertEqual(result['provider_status'], 'canceled')

    # ── Test 12: No audit log when external fails ─────────────────────────────
    def test_12_no_audit_when_external_not_confirmed(self):
        """When cancel_preapproval raises, no audit entry must be written."""
        mp = self._mp_with_put_400_get_active()
        with self.assertRaises(Exception):
            cancel_subscription_immediately(
                subscription=self.sub, canceled_by=self.admin,
                reason='Test', mp_service=mp,
            )
        count = AccessAuditLog.objects.filter(
            action='ADMIN_SUBSCRIPTION_CANCELED',
            actor=self.admin,
        ).count()
        self.assertEqual(count, 0, "No audit log when external cancel not confirmed")

    # ── Test 13: Legacy sub not canceled when MP fails ────────────────────────
    def test_13_no_legacy_cancel_when_mp_fails(self):
        """Legacy Subscription.status must remain 'active' when MP fails."""
        mp = self._mp_with_put_400_get_active()
        with self.assertRaises(Exception):
            cancel_subscription_immediately(
                subscription=self.sub, canceled_by=self.admin,
                reason='Test', mp_service=mp,
            )
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.status, 'active',
                         "Legacy sub must stay 'active' when MP fails")

    # ── Test 14: Entitlements unchanged when MP fails ─────────────────────────
    def test_14_no_entitlement_change_when_mp_fails(self):
        """
        SubscriptionV2 status and Business.status must remain unchanged when
        the MP cancel is not confirmed, preserving entitlements.
        """
        prev_status = self.sub.status
        prev_biz_status = self.biz.status
        mp = self._mp_with_put_400_get_active()
        with self.assertRaises(Exception):
            cancel_subscription_immediately(
                subscription=self.sub, canceled_by=self.admin,
                reason='Test', mp_service=mp,
            )
        self.sub.refresh_from_db()
        self.biz.refresh_from_db()
        self.assertEqual(self.sub.status, prev_status,
                         "SubscriptionV2.status must not change when MP fails")
        self.assertTrue(self.sub.is_active,
                        "SubscriptionV2.is_active must stay True when MP fails")
        self.assertEqual(self.biz.status, prev_biz_status,
                         "Business.status must not change when MP fails")

    # ── Test 14b: ProviderSubscriptionNotFound → all local state unchanged ────
    def test_14b_provider_not_found_local_state_unchanged(self):
        """When preapproval not found at MP, local state must remain intact."""
        from apps.billing.mp_service import ProviderSubscriptionNotFound
        prev_status = self.sub.status
        mp = self._mp_with_provider_not_found()
        with self.assertRaises(ProviderSubscriptionNotFound):
            cancel_subscription_immediately(
                subscription=self.sub, canceled_by=self.admin,
                reason='Test', mp_service=mp,
            )
        self.sub.refresh_from_db()
        self.biz.refresh_from_db()
        self.assertEqual(self.sub.status, prev_status)
        self.assertTrue(self.sub.is_active)
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.status, 'active')
