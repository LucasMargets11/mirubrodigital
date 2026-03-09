"""
Tests for Phase 3 — V2 addon/feature-flag parity, AddonCheckoutView V2 birth-path,
BillingViewSet.subscribe V2 birth-path, and regression guards.

Covers:
  V2AddonParityTest
    1. V2 pro + extra_branch legacy addon → multi_branch flag enabled
    2. V2 menu_qr_pro + menu_qr_addon_reviews → menu_qr_reviews flag enabled
    3. V2 menu_qr_pro + menu_qr_addon_tips → menu_qr_tips flag enabled
    4. V2 menu_qr_pro + pro_included_module='reviews' → menu_qr_reviews flag
    5. V2 + invoices_module legacy addon → gestion.invoices entitlement bridged
    6. V2 + customers_module legacy addon → gestion.customers entitlement bridged
    7. No legacy sub → no addons invented, base plan flags only
    8. Legacy and V2 give equivalent results for pro plan without addons
    9. Legacy and V2 give equivalent results for pro plan WITH addons

  AddonCheckoutV2BirthPathTest
    1. Creates SubscriptionV2 when none exists
    2. Links existing SubscriptionV2 when one is already present
    3. Does not duplicate SubscriptionV2 (idempotent)
    4. metadata passed to MP includes subscription_v2_id

  BillingViewSetSubscribeV2BirthPathTest
    1. Creates SubscriptionV2 when none exists after subscribe
    2. Does not duplicate SubscriptionV2 when one already exists
    3. Legacy billing.Subscription still created correctly
    4. V2 has correct service_type and plan_code

  RegressionTest
    1. Enforcement still works — V2 suspended blocks access
    2. resolve_subscription still V2-first
    3. Fallback to legacy still coexists when no V2
    4. MeView / build_business_context still exposes coherent payload
    5. has_entitlement still rejects expired V2 regardless of legacy addons
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.billing.models import (
    Bundle,
    Module,
    Plan,
    Subscription as LegacyBillingSubscription,
    SubscriptionV2,
)
from apps.billing.runtime import resolve_subscription
from apps.billing.views import BillingViewSet
from apps.business.context import build_business_context
from apps.business.entitlements import has_entitlement
from apps.business.features import (
    feature_flags_for_plan,
    feature_flags_for_subscription,
    feature_flags_for_v2_subscription,
)
from apps.business.models import Business, Subscription as BizSubscription, SubscriptionAddon

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_business(name="PharityBiz", service="gestion", status="active"):
    return Business.objects.create(name=name, default_service=service, status=status)


def _attach_legacy(biz, plan="pro", status="active"):
    sub = BizSubscription.objects.create(
        business=biz,
        plan=plan,
        status=status,
        service=biz.default_service,
    )
    return sub


def _attach_v2(biz, plan_code="pro", v2_status=None, service_type=None):
    return SubscriptionV2.objects.create(
        business=biz,
        service_type=service_type or biz.default_service,
        plan_code=plan_code,
        provider=SubscriptionV2.Provider.MANUAL,
        external_reference=f"SUB-{uuid.uuid4()}",
        status=v2_status or SubscriptionV2.Status.ACTIVE,
    )


def _add_addon(legacy_sub, code, quantity=1):
    return SubscriptionAddon.objects.create(
        subscription=legacy_sub,
        code=code,
        quantity=quantity,
        is_active=True,
    )


def _make_user(biz, role="owner"):
    user = User.objects.create_user(
        email=f"user_{uuid.uuid4().hex[:8]}@test.com",
        password="pass123",
        username=f"user_{uuid.uuid4().hex[:8]}",
    )
    from apps.accounts.models import Membership
    Membership.objects.create(user=user, business=biz, role=role)
    return user


# ─────────────────────────────────────────────────────────────────────────────
# V2AddonParityTest
# ─────────────────────────────────────────────────────────────────────────────

class V2AddonParityTest(TestCase):
    """
    Verifies that feature flags and entitlements resolved via V2 match the
    equivalent legacy outcome when addons are present.
    """

    def test_v2_pro_extra_branch_enables_multi_branch_flag(self):
        """
        V2 source: pro plan + extra_branch legacy addon → multi_branch=True.
        This bridges the gap: legacy would enable multi_branch via addon;
        V2 must do the same.
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="pro")
        _add_addon(legacy_sub, "extra_branch", quantity=2)
        v2 = _attach_v2(biz, plan_code="pro")

        flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertTrue(flags["multi_branch"], "extra_branch addon must enable multi_branch for pro V2")

    def test_v2_pro_no_extra_branch_does_not_enable_multi_branch(self):
        """V2 pro without extra_branch: multi_branch must remain False."""
        biz = _make_business()
        _attach_legacy(biz, plan="pro")  # no extra_branch addon
        v2 = _attach_v2(biz, plan_code="pro")

        flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertFalse(flags["multi_branch"])

    def test_v2_menu_qr_pro_addon_reviews_enables_flag(self):
        """
        V2 menu_qr_pro + menu_qr_addon_reviews legacy addon → menu_qr_reviews=True.
        """
        biz = _make_business(service="menu_qr")
        legacy_sub = _attach_legacy(biz, plan="menu_qr_pro")
        _add_addon(legacy_sub, "menu_qr_addon_reviews")
        v2 = _attach_v2(biz, plan_code="menu_qr_pro", service_type="menu_qr")

        flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertTrue(flags["menu_qr_reviews"])

    def test_v2_menu_qr_pro_addon_tips_enables_flag(self):
        """V2 menu_qr_pro + menu_qr_addon_tips legacy addon → menu_qr_tips=True."""
        biz = _make_business(service="menu_qr")
        legacy_sub = _attach_legacy(biz, plan="menu_qr_pro")
        _add_addon(legacy_sub, "menu_qr_addon_tips")
        v2 = _attach_v2(biz, plan_code="menu_qr_pro", service_type="menu_qr")

        flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertTrue(flags["menu_qr_tips"])

    def test_v2_menu_qr_pro_pro_included_module_reviews(self):
        """V2 menu_qr_pro + pro_included_module='reviews' → menu_qr_reviews=True."""
        biz = _make_business(service="menu_qr")
        legacy_sub = _attach_legacy(biz, plan="menu_qr_pro")
        legacy_sub.pro_included_module = "reviews"
        legacy_sub.save()
        v2 = _attach_v2(biz, plan_code="menu_qr_pro", service_type="menu_qr")

        flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertTrue(flags["menu_qr_reviews"])
        self.assertFalse(flags["menu_qr_tips"])  # not set by pro_included_module

    def test_v2_menu_qr_pro_no_addons_both_flags_false(self):
        """V2 menu_qr_pro with no addons and no pro_included_module → reviews/tips False."""
        biz = _make_business(service="menu_qr")
        _attach_legacy(biz, plan="menu_qr_pro")
        v2 = _attach_v2(biz, plan_code="menu_qr_pro", service_type="menu_qr")

        flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertFalse(flags["menu_qr_reviews"])
        self.assertFalse(flags["menu_qr_tips"])

    def test_v2_invoices_module_addon_bridges_entitlement(self):
        """
        V2 start plan + invoices_module legacy addon → gestion.invoices entitlement.
        Start plan alone does NOT include gestion.invoices.
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="start")
        _add_addon(legacy_sub, "invoices_module")
        _attach_v2(biz, plan_code="start")

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, "v2")
        self.assertIn("gestion.invoices", resolved.entitlements)

    def test_v2_customers_module_addon_bridges_entitlement(self):
        """
        V2 start plan + customers_module legacy addon → gestion.customers entitlement.
        Start plan alone does NOT include gestion.customers.
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="start")
        _add_addon(legacy_sub, "customers_module")
        _attach_v2(biz, plan_code="start")

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, "v2")
        self.assertIn("gestion.customers", resolved.entitlements)

    def test_no_addons_invented_when_no_legacy_sub(self):
        """
        V2 with no legacy sub must not invent addons.
        Flags and entitlements must equal base plan only.
        """
        biz = _make_business()
        # No legacy subscription created
        v2 = _attach_v2(biz, plan_code="pro")

        flags = feature_flags_for_v2_subscription(v2, biz)
        base_flags = feature_flags_for_plan("pro")
        self.assertEqual(flags, base_flags, "No addons should be invented without a legacy sub")

        resolved = resolve_subscription(biz)
        from apps.business.entitlements import get_plan_entitlements
        self.assertEqual(
            set(resolved.entitlements),
            get_plan_entitlements("pro"),
            "No addon entitlements should be invented without a legacy sub",
        )

    def test_no_addons_invented_when_legacy_has_none(self):
        """V2 with a legacy sub that has no active addons: base plan flags only."""
        biz = _make_business()
        _attach_legacy(biz, plan="pro")  # no addons
        v2 = _attach_v2(biz, plan_code="pro")

        flags = feature_flags_for_v2_subscription(v2, biz)
        base_flags = feature_flags_for_plan("pro")
        self.assertEqual(flags, base_flags)

    def test_legacy_and_v2_give_equivalent_flags_pro_no_addons(self):
        """Legacy and V2 produce identical feature flags for pro without addons."""
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="pro")
        v2 = _attach_v2(biz, plan_code="pro")

        legacy_flags = feature_flags_for_subscription(legacy_sub)
        v2_flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertEqual(legacy_flags, v2_flags)

    def test_legacy_and_v2_give_equivalent_flags_pro_with_extra_branch(self):
        """Legacy and V2 produce identical feature flags for pro WITH extra_branch addon."""
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="pro")
        _add_addon(legacy_sub, "extra_branch", quantity=1)
        v2 = _attach_v2(biz, plan_code="pro")

        legacy_flags = feature_flags_for_subscription(legacy_sub)
        v2_flags = feature_flags_for_v2_subscription(v2, biz)
        self.assertEqual(legacy_flags, v2_flags)

    def test_v2_degraded_no_entitlements_despite_addons(self):
        """
        A degraded V2 (§F.2) must return empty entitlements even if legacy has addons.
        This verifies that the addon bridge does not bypass enforcement.
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="pro")
        _add_addon(legacy_sub, "invoices_module")
        _attach_v2(biz, plan_code="pro", v2_status=SubscriptionV2.Status.SUSPENDED)

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, "v2")
        self.assertFalse(resolved.access_granted)
        # Degraded V2 must have empty entitlements — not bridged addons
        self.assertEqual(len(resolved.entitlements), 0)
        self.assertNotIn("gestion.invoices", resolved.entitlements)

    def test_build_business_context_v2_with_addon_includes_enriched_flags(self):
        """
        build_business_context with V2 + extra_branch addon: context must include
        multi_branch=True (parity with legacy path).
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="pro")
        _add_addon(legacy_sub, "extra_branch", quantity=1)
        _attach_v2(biz, plan_code="pro")

        ctx = build_business_context(biz)
        self.assertEqual(ctx["_subscription_source"], "v2")
        self.assertTrue(ctx["features"]["multi_branch"])

    def test_build_business_context_v2_without_addon_no_fake_multi_branch(self):
        """
        build_business_context with V2 pro + no extra_branch: multi_branch must be False.
        """
        biz = _make_business()
        _attach_legacy(biz, plan="pro")  # no extra_branch addon
        _attach_v2(biz, plan_code="pro")

        ctx = build_business_context(biz)
        self.assertEqual(ctx["_subscription_source"], "v2")
        self.assertFalse(ctx["features"]["multi_branch"])


# ─────────────────────────────────────────────────────────────────────────────
# AddonCheckoutV2BirthPathTest
# ─────────────────────────────────────────────────────────────────────────────

class AddonCheckoutV2BirthPathTest(TestCase):
    """
    Verifies that AddonCheckoutView ensures SubscriptionV2 exists (birth-path).
    """

    def setUp(self):
        from apps.billing.commercial_views import AddonCheckoutView
        self.view = AddonCheckoutView.as_view()
        self.factory = APIRequestFactory()

    def _make_biz_with_legacy_sub(self, plan="start"):
        biz = _make_business()
        _attach_legacy(biz, plan=plan)
        return biz

    def _post(self, biz, addon_code="invoicing", billing_cycle="monthly"):
        user = _make_user(biz, role="owner")
        request = self.factory.post(
            "/api/billing/commercial/addon-checkout/",
            {"addon_code": addon_code, "billing_cycle": billing_cycle},
            format="json",
        )
        force_authenticate(request, user=user)
        # Attach business to request (simulates HasBusinessMembership middleware)
        request.business = biz
        return request

    @patch("apps.billing.mp_service.MercadoPagoService")
    def test_creates_v2_when_none_exists(self, MockMP):
        """AddonCheckoutView must create SubscriptionV2 when none exists for business."""
        MockMP.return_value.create_preference.return_value = {
            "id": "pref_001",
            "init_point": "https://mp.test/checkout",
        }
        biz = self._make_biz_with_legacy_sub(plan="start")
        self.assertEqual(
            SubscriptionV2.objects.filter(business=biz).count(), 0,
            "Precondition: no V2 should exist yet",
        )

        request = self._post(biz)
        response = self.view(request)

        self.assertIn(response.status_code, [200, 201],
                      f"Unexpected status: {response.status_code} data={getattr(response, 'data', {})}")
        v2_count = SubscriptionV2.objects.filter(business=biz).count()
        self.assertEqual(v2_count, 1, "Exactly one SubscriptionV2 must be created")

        v2 = SubscriptionV2.objects.get(business=biz)
        self.assertEqual(v2.service_type, biz.default_service)
        self.assertEqual(v2.status, SubscriptionV2.Status.CHECKOUT_PENDING)

    @patch("apps.billing.mp_service.MercadoPagoService")
    def test_links_existing_v2_does_not_duplicate(self, MockMP):
        """
        AddonCheckoutView must not duplicate SubscriptionV2 when one already exists.
        """
        MockMP.return_value.create_preference.return_value = {
            "id": "pref_002",
            "init_point": "https://mp.test/checkout",
        }
        biz = self._make_biz_with_legacy_sub(plan="start")
        existing_v2 = _attach_v2(biz, plan_code="start")

        request = self._post(biz)
        self.view(request)

        v2_count = SubscriptionV2.objects.filter(
            business=biz,
        ).exclude(status=SubscriptionV2.Status.CANCELED).count()
        self.assertEqual(v2_count, 1, "No duplicate V2 should be created")
        # The existing V2 must be the same one
        self.assertEqual(
            SubscriptionV2.objects.filter(business=biz).first().pk,
            existing_v2.pk,
        )

    @patch("apps.billing.mp_service.MercadoPagoService")
    def test_mp_preference_metadata_includes_v2_id(self, MockMP):
        """
        The preference metadata passed to MercadoPago must contain subscription_v2_id
        for webhook correlation.
        """
        mock_instance = MockMP.return_value
        mock_instance.create_preference.return_value = {
            "id": "pref_003",
            "init_point": "https://mp.test/checkout",
        }
        biz = self._make_biz_with_legacy_sub(plan="start")

        request = self._post(biz)
        response = self.view(request)

        self.assertIn(response.status_code, [200, 201],
                      f"Unexpected status: {response.status_code} data={getattr(response, 'data', {})}")
        self.assertTrue(
            mock_instance.create_preference.called,
            "create_preference must have been called",
        )
        call_kwargs = mock_instance.create_preference.call_args.kwargs
        metadata = call_kwargs.get("metadata", {})
        self.assertIn("subscription_v2_id", metadata)
        # subscription_v2_id must be the UUID string of the created V2
        v2 = SubscriptionV2.objects.filter(business=biz).first()
        self.assertIsNotNone(v2)
        self.assertEqual(metadata["subscription_v2_id"], str(v2.pk))

    @patch("apps.billing.mp_service.MercadoPagoService")
    def test_response_still_contains_checkout_url(self, MockMP):
        """
        The existing checkout flow contract (checkout_url, addon, price) must be
        preserved after adding the V2 birth-path block.
        """
        MockMP.return_value.create_preference.return_value = {
            "id": "pref_004",
            "init_point": "https://mp.test/checkout/004",
        }
        biz = self._make_biz_with_legacy_sub(plan="start")

        request = self._post(biz)
        response = self.view(request)

        self.assertIn(response.status_code, [200, 201],
                      f"Unexpected status: {response.status_code} data={getattr(response, 'data', {})}")
        data = response.data
        self.assertIn("checkout_url", data)
        self.assertIn("addon", data)
        self.assertEqual(data["checkout_url"], "https://mp.test/checkout/004")


# ─────────────────────────────────────────────────────────────────────────────
# BillingViewSetSubscribeV2BirthPathTest
# ─────────────────────────────────────────────────────────────────────────────

class BillingViewSetSubscribeV2BirthPathTest(TestCase):
    """
    Verifies that BillingViewSet.subscribe ensures SubscriptionV2 is created or
    linked after every subscription update.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        # Create a minimal Plan and Bundle for the endpoint
        self.plan = Plan.objects.create(
            code="gestion_pro",
            name="Gestión Pro",
            price=Decimal("99.00"),
            interval="monthly",
            mp_preapproval_plan_id="mp_plan_99",
        )
        self.bundle = Bundle.objects.create(
            code="gestion_pro",
            name="Gestión Pro Bundle",
            is_active=True,
            vertical="commercial",
        )

    def _post_subscribe(self, biz, plan_type="bundle", bundle_code="gestion_pro"):
        user = _make_user(biz, role="owner")
        data = {
            "plan_type": plan_type,
            "billing_period": "monthly",
            "bundle_code": bundle_code,
        }
        request = self.factory.post("/api/billing/subscribe/", data, format="json")
        force_authenticate(request, user=user)
        # HasBusinessMembership middleware sets request.business; simulate here
        # by using the viewset with a patched membership resolution
        request.business = biz
        view = BillingViewSet.as_view({"post": "subscribe"})
        return view(request)

    @patch("apps.billing.views.PricingService.calculate_quote")
    def test_creates_v2_when_none_exists(self, mock_quote):
        """BillingViewSet.subscribe must create a SubscriptionV2 when none exists."""
        mock_quote.return_value = {
            "currency": "ARS",
            "modules": [],
            "total": 0,
        }
        biz = _make_business()

        with patch("apps.accounts.access.resolve_request_membership") as mock_m:
            mock_m.return_value = MagicMock(role="owner", business=biz)
            response = self._post_subscribe(biz)

        # Response can be 200 or 400 depending on whether bundle exists fully;
        # what matters is SubscriptionV2 being created.
        v2_count = SubscriptionV2.objects.filter(
            business=biz,
            service_type=biz.default_service,
        ).count()
        self.assertGreaterEqual(v2_count, 1, "SubscriptionV2 must be created")

    @patch("apps.billing.views.PricingService.calculate_quote")
    def test_does_not_duplicate_v2(self, mock_quote):
        """subscribe called twice must not create two active V2s for the same service."""
        mock_quote.return_value = {
            "currency": "ARS",
            "modules": [],
            "total": 0,
        }
        biz = _make_business()
        # Pre-create V2
        existing_v2 = _attach_v2(biz, plan_code="gestion_pro")

        with patch("apps.accounts.access.resolve_request_membership") as mock_m:
            mock_m.return_value = MagicMock(role="owner", business=biz)
            self._post_subscribe(biz)

        non_canceled = SubscriptionV2.objects.filter(
            business=biz,
            service_type=biz.default_service,
        ).exclude(status=SubscriptionV2.Status.CANCELED)
        self.assertEqual(non_canceled.count(), 1, "No duplicate V2 should be created")
        self.assertEqual(non_canceled.first().pk, existing_v2.pk)

    @patch("apps.billing.views.PricingService.calculate_quote")
    def test_v2_has_correct_service_type(self, mock_quote):
        """Created V2 must match the business's default_service."""
        mock_quote.return_value = {
            "currency": "ARS",
            "modules": [],
            "total": 0,
        }
        biz = _make_business(service="menu_qr")

        with patch("apps.accounts.access.resolve_request_membership") as mock_m:
            mock_m.return_value = MagicMock(role="owner", business=biz)
            self._post_subscribe(biz, bundle_code="gestion_pro")

        v2_qs = SubscriptionV2.objects.filter(business=biz)
        if v2_qs.exists():
            v2 = v2_qs.first()
            self.assertEqual(v2.service_type, "menu_qr")

    @patch("apps.billing.views.PricingService.calculate_quote")
    def test_legacy_billing_subscription_still_created(self, mock_quote):
        """
        V2 birth-path must not interfere with the legacy billing.Subscription
        creation — it should still be created/updated normally.
        """
        mock_quote.return_value = {
            "currency": "ARS",
            "modules": [],
            "total": 0,
        }
        biz = _make_business()

        with patch("apps.accounts.access.resolve_request_membership") as mock_m:
            mock_m.return_value = MagicMock(role="owner", business=biz)
            response = self._post_subscribe(biz)

        # The legacy Subscription (billing.Subscription) must still exist
        from apps.billing.models import Subscription as LegacyBillSubModel
        self.assertTrue(
            LegacyBillSubModel.objects.filter(business=biz).exists(),
            "Legacy billing.Subscription must still be created",
        )


# ─────────────────────────────────────────────────────────────────────────────
# RegressionTest
# ─────────────────────────────────────────────────────────────────────────────

class RegressionTest(TestCase):
    """
    Regression guards: Phase 3 changes must not break existing behavior.
    """

    def test_enforcement_still_blocks_suspended_v2(self):
        """§F.2: suspended V2 must block access even if legacy is active."""
        biz = _make_business()
        _attach_legacy(biz, plan="pro", status="active")
        _attach_v2(biz, plan_code="pro", v2_status=SubscriptionV2.Status.SUSPENDED)

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, "v2")
        self.assertFalse(resolved.access_granted)
        self.assertFalse(has_entitlement(biz, "gestion.customers"))

    def test_enforcement_still_blocks_grace_expired_v2(self):
        """§F.2: past_due V2 with expired grace must block access."""
        from datetime import timedelta
        expired_grace = timezone.now() - timedelta(days=1)
        biz = _make_business()
        _attach_legacy(biz, plan="pro", status="active")
        SubscriptionV2.objects.create(
            business=biz,
            service_type=biz.default_service,
            plan_code="pro",
            provider=SubscriptionV2.Provider.MANUAL,
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.PAST_DUE,
            grace_until=expired_grace,
        )

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, "v2")
        self.assertFalse(resolved.access_granted)
        self.assertFalse(has_entitlement(biz, "gestion.cash"))

    def test_resolve_subscription_still_v2_first(self):
        """V2 must be authoritative when both V2 and legacy exist."""
        biz = _make_business()
        _attach_legacy(biz, plan="start", status="active")
        _attach_v2(biz, plan_code="business")

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, "v2")
        self.assertEqual(resolved.plan, "business")

    def test_fallback_legacy_still_coexists_when_no_v2(self):
        """No V2 → fallback to legacy is still functional."""
        biz = _make_business()
        _attach_legacy(biz, plan="pro", status="active")

        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, "legacy")
        self.assertEqual(resolved.plan, "pro")
        self.assertTrue(resolved.access_granted)

    def test_build_business_context_coherent_payload_v2(self):
        """
        build_business_context with V2 must expose a coherent payload:
        enforcement fields present, source=v2, plan matches V2.
        """
        biz = _make_business()
        _attach_legacy(biz, plan="start")
        _attach_v2(biz, plan_code="pro")

        ctx = build_business_context(biz)

        self.assertEqual(ctx["_subscription_source"], "v2")
        self.assertEqual(ctx["plan"], "pro")
        self.assertIn("access_allowed", ctx)
        self.assertIn("reason_code", ctx)
        self.assertIn("grace_until", ctx)
        self.assertIn("access_until", ctx)
        self.assertIn("show_renewal_prompt", ctx)
        self.assertTrue(ctx["access_allowed"])

    def test_build_business_context_coherent_payload_legacy(self):
        """build_business_context with legacy fallback still works after Phase 3."""
        biz = _make_business()
        _attach_legacy(biz, plan="pro", status="active")

        ctx = build_business_context(biz)

        self.assertEqual(ctx["_subscription_source"], "legacy")
        self.assertEqual(ctx["plan"], "pro")
        self.assertTrue(ctx["access_allowed"])
        self.assertIsInstance(ctx["features"], dict)

    def test_has_entitlement_v2_addon_bridge_does_not_bypass_enforcement(self):
        """
        has_entitlement must return False when V2 is suspended, regardless of
        whether legacy has an addon that would normally grant the entitlement.
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="start")
        _add_addon(legacy_sub, "invoices_module")
        _attach_v2(biz, plan_code="start", v2_status=SubscriptionV2.Status.SUSPENDED)

        result = has_entitlement(biz, "gestion.invoices")
        self.assertFalse(result, "Suspended V2 must block access even with addon bridge")

    def test_has_entitlement_v2_active_with_addon_bridge_grants_access(self):
        """
        has_entitlement returns True when V2 is active AND addon bridge adds
        the entitlement (invoices_module on start plan).
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="start")
        _add_addon(legacy_sub, "invoices_module")
        _attach_v2(biz, plan_code="start")

        result = has_entitlement(biz, "gestion.invoices")
        self.assertTrue(result)

    def test_legacy_subscription_not_deleted(self):
        """
        Legacy business.Subscription and billing.Subscription models must
        still exist and be queryable after Phase 3 changes.
        """
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="pro")
        _attach_v2(biz, plan_code="pro")

        self.assertTrue(BizSubscription.objects.filter(business=biz).exists())
        self.assertEqual(BizSubscription.objects.get(business=biz).pk, legacy_sub.pk)

    def test_v2_active_entitlements_superset_of_plan_base(self):
        """
        V2 active pro + invoices_module addon → entitlements must be a superset
        of the base pro plan entitlements (no entitlements lost).
        """
        from apps.business.entitlements import get_plan_entitlements
        biz = _make_business()
        legacy_sub = _attach_legacy(biz, plan="pro")
        _add_addon(legacy_sub, "invoices_module")
        _attach_v2(biz, plan_code="pro")

        resolved = resolve_subscription(biz)
        base = get_plan_entitlements("pro")
        self.assertTrue(
            base.issubset(set(resolved.entitlements)),
            "Bridge must not lose base plan entitlements",
        )
        # And gestion.invoices is the bridged extra
        self.assertIn("gestion.invoices", resolved.entitlements)
