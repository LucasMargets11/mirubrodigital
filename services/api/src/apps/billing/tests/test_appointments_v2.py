"""
Tests for MiRubro Turnos (`appointments`) — Slice 1B Billing V2 integration.

Verifies the canonical Billing V2 pipeline (the same one qr_reviews/menu_qr
use) correctly recognizes `appointments`:

  SubscriptionV2 (service_type='appointments')
        -> billing.runtime.resolve_subscription()
        -> apps.business.context.build_business_context()
        -> session.services.enabled includes 'appointments'

Covers:
  1. Billing V2 recognizes `appointments` (ServiceType / vertical choices).
  2. An active SubscriptionV2 for appointments enables the service end-to-end.
  3. A canceled/suspended SubscriptionV2 does NOT enable it.
  4. build_business_context() resolves an appointments business from V2.
  5. appointments needs no legacy business.Subscription row to work.
  6. Existing V2 products (qr_reviews, gestion) keep their prior behaviour.
"""
from __future__ import annotations

import uuid

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.billing.models import Bundle, Module, SubscriptionV2
from apps.billing.runtime import resolve_subscription
from apps.business.context import build_business_context
from apps.business.models import Business, Subscription as BizSubscription


def _make_business(name='Turnos Biz', service='appointments'):
    return Business.objects.create(
        name=name,
        default_service=service,
        status='active',
    )


def _attach_v2(biz, plan_code='appointments_base', status=None, service_type=None):
    return SubscriptionV2.objects.create(
        business=biz,
        service_type=service_type or biz.default_service,
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MANUAL,
        external_reference=f'SUB-{uuid.uuid4()}',
        status=status or SubscriptionV2.Status.ACTIVE,
    )


# ---------------------------------------------------------------------------
# 1. Billing V2 recognizes `appointments`
# ---------------------------------------------------------------------------

class AppointmentsBillingV2RegistrationTests(TestCase):

    def test_appointments_in_subscriptionv2_service_type(self):
        self.assertIn('appointments', SubscriptionV2.ServiceType.values)

    def test_appointments_in_module_vertical_choices(self):
        codes = [code for code, _ in Module.VERTICAL_CHOICES]
        self.assertIn('appointments', codes)

    def test_appointments_in_bundle_vertical_choices(self):
        codes = [code for code, _ in Bundle.VERTICAL_CHOICES]
        self.assertIn('appointments', codes)

    def test_can_create_subscriptionv2_with_appointments_service_type(self):
        biz = _make_business()
        sub = _attach_v2(biz)
        self.assertEqual(sub.service_type, 'appointments')
        # Validate the service_type choice specifically (price_snapshot's
        # default empty dict independently fails JSONField's blank check —
        # a pre-existing quirk unrelated to this field, so it's excluded).
        sub.full_clean(exclude=['price_snapshot'])


# ---------------------------------------------------------------------------
# 2 & 3. Active vs canceled/suspended SubscriptionV2
# ---------------------------------------------------------------------------

class AppointmentsV2EntitlementTests(TestCase):

    def test_active_v2_subscription_enables_appointments(self):
        biz = _make_business()
        _attach_v2(biz, status=SubscriptionV2.Status.ACTIVE)

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertTrue(resolved.access_granted)
        self.assertEqual(resolved.plan, 'appointments_base')

        ctx = build_business_context(biz)
        self.assertEqual(ctx['service'], 'appointments')
        self.assertIn('appointments', ctx['enabled_services'])
        self.assertTrue(ctx['features'].get('appointments_core'))
        self.assertTrue(ctx['access_allowed'])
        self.assertEqual(ctx['_subscription_source'], 'v2')

    def test_canceled_v2_subscription_does_not_enable_appointments(self):
        biz = _make_business()
        _attach_v2(biz, status=SubscriptionV2.Status.CANCELED)

        resolved = resolve_subscription(biz)
        # Canceled V2 rows are excluded outright; with no legacy subscription
        # either, nothing grants access.
        self.assertNotEqual(resolved.source, 'v2')
        self.assertFalse(resolved.access_granted)

        ctx = build_business_context(biz)
        self.assertNotIn('appointments', ctx['enabled_services'])
        self.assertFalse(ctx['access_allowed'])

    def test_suspended_v2_subscription_denies_access(self):
        """§F.2: a degraded (suspended) V2 denies access and is not bridged."""
        biz = _make_business()
        _attach_v2(biz, status=SubscriptionV2.Status.SUSPENDED)

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertFalse(resolved.access_granted)
        self.assertEqual(len(resolved.entitlements), 0)

    def test_past_due_grace_expired_denies_access(self):
        biz = _make_business()
        past_grace = timezone.now() - timedelta(days=1)
        sub = _attach_v2(biz, status=SubscriptionV2.Status.PAST_DUE)
        sub.grace_until = past_grace
        sub.save(update_fields=['grace_until'])

        resolved = resolve_subscription(biz)

        self.assertEqual(resolved.source, 'v2')
        self.assertFalse(resolved.access_granted)


# ---------------------------------------------------------------------------
# 4 & 5. build_business_context() from V2, no legacy dependency
# ---------------------------------------------------------------------------

class AppointmentsNoLegacyDependencyTests(TestCase):

    def test_appointments_business_context_derived_purely_from_v2(self):
        biz = _make_business()
        _attach_v2(biz, status=SubscriptionV2.Status.ACTIVE)

        # No legacy business.Subscription row exists for this business.
        self.assertEqual(BizSubscription.objects.filter(business=biz).count(), 0)
        self.assertIsNone(getattr(biz, 'subscription', None))

        ctx = build_business_context(biz)

        self.assertEqual(ctx['_subscription_source'], 'v2')
        self.assertIn('appointments', ctx['enabled_services'])
        self.assertTrue(ctx['access_allowed'])

    def test_appointments_without_any_subscription_is_not_enabled(self):
        """default_service='appointments' alone (no V2, no legacy) grants nothing."""
        biz = _make_business()

        ctx = build_business_context(biz)

        self.assertNotIn('appointments', ctx['enabled_services'])
        self.assertFalse(ctx['access_allowed'])


# ---------------------------------------------------------------------------
# 6. Existing V2 products keep their prior behaviour
# ---------------------------------------------------------------------------

class ExistingV2ProductsUnaffectedTests(TestCase):

    def test_qr_reviews_v2_subscription_unaffected(self):
        biz = _make_business(name='QR Reviews Biz', service='qr_reviews')
        _attach_v2(
            biz, plan_code='qr_reviews_base',
            service_type='qr_reviews', status=SubscriptionV2.Status.ACTIVE,
        )

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, 'v2')
        self.assertEqual(resolved.plan, 'qr_reviews_base')

        ctx = build_business_context(biz)
        self.assertIn('qr_reviews', ctx['enabled_services'])
        self.assertNotIn('appointments', ctx['enabled_services'])

    def test_gestion_pro_v2_subscription_unaffected(self):
        biz = _make_business(name='Gestion Biz', service='gestion')
        _attach_v2(biz, plan_code='pro', service_type='gestion', status=SubscriptionV2.Status.ACTIVE)

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.plan, 'pro')
        self.assertIn('gestion.customers', resolved.entitlements)

        ctx = build_business_context(biz)
        self.assertIn('gestion', ctx['enabled_services'])
        self.assertNotIn('appointments', ctx['enabled_services'])
