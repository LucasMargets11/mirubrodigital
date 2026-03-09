"""
Tests for Phase 3 backfill_subscriptions management command.
"""
from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.billing.models import Plan, Subscription as LegacySubscription, SubscriptionV2
from apps.business.models import Business, Subscription as BizSubscription

User = get_user_model()


def _make_hq(name="HQ", service="gestion"):
    biz = Business.objects.create(name=name, default_service=service, service_type=service)
    # business.Subscription is required by the Membership seat-limit signal
    BizSubscription.objects.create(business=biz, plan="starter", status="active")
    return biz


def _make_legacy_sub(biz, status="active", billing_period="monthly", plan_type="bundle"):
    return LegacySubscription.objects.create(
        business=biz,
        plan_type=plan_type,
        billing_period=billing_period,
        status=status,
        price_snapshot={"total": 2000},
    )


def _call(cmd, *args, **kwargs):
    out = StringIO()
    call_command(cmd, *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


class BackfillSubscriptionsTest(TestCase):

    def setUp(self):
        self.biz      = _make_hq(service="gestion")
        self.leg_sub  = _make_legacy_sub(self.biz, status="active")

    # ── happy path ──────────────────────────────────────────────────────────

    def test_creates_subscriptionv2_for_active(self):
        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.filter(external_reference=ref).first()
        self.assertIsNotNone(v2)
        self.assertEqual(v2.business,     self.biz)
        self.assertEqual(v2.service_type, SubscriptionV2.ServiceType.GESTION)
        self.assertEqual(v2.status,       SubscriptionV2.Status.ACTIVE)
        self.assertEqual(v2.provider,     SubscriptionV2.Provider.MANUAL)

    def test_status_trial_mapped_to_trialing(self):
        self.leg_sub.status = "trial"
        self.leg_sub.save(update_fields=["status"])

        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.status, SubscriptionV2.Status.TRIALING)

    def test_status_past_due_mapped_correctly(self):
        self.leg_sub.status = "past_due"
        self.leg_sub.save(update_fields=["status"])

        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.status, SubscriptionV2.Status.PAST_DUE)

    def test_status_canceled_mapped_correctly(self):
        self.leg_sub.status = "canceled"
        self.leg_sub.save(update_fields=["status"])

        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.status, SubscriptionV2.Status.CANCELED)

    def test_service_type_resolved_from_default_service(self):
        biz2      = _make_hq(service="restaurante")
        leg_sub2  = _make_legacy_sub(biz2)

        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{leg_sub2.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.service_type, SubscriptionV2.ServiceType.RESTAURANTE)

    def test_plan_code_derived_from_plan_fk(self):
        plan = Plan.objects.create(
            code="gestion_pro_monthly",
            name="Gestión Pro",
            price=2000,
            interval="monthly",
        )
        self.leg_sub.plan = plan
        self.leg_sub.save(update_fields=["plan"])

        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.plan_code, "gestion_pro_monthly")

    def test_price_snapshot_contains_provenance(self):
        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.price_snapshot["_migrated_from"], "billing.Subscription")
        self.assertEqual(v2.price_snapshot["_legacy_id"],     self.leg_sub.pk)
        self.assertEqual(v2.price_snapshot["total"],          2000)   # original data preserved

    def test_mp_preapproval_id_copied_to_provider_sub_id(self):
        self.leg_sub.mp_preapproval_id = "mp-12345"
        self.leg_sub.save(update_fields=["mp_preapproval_id"])

        _call("backfill_subscriptions")

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.provider_sub_id, "mp-12345")

    # ── idempotency ──────────────────────────────────────────────────────────

    def test_idempotent(self):
        _call("backfill_subscriptions")
        _call("backfill_subscriptions")   # second run

        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        self.assertEqual(
            SubscriptionV2.objects.filter(external_reference=ref).count(), 1
        )

    def test_dry_run_creates_nothing(self):
        _call("backfill_subscriptions", dry_run=True)
        self.assertEqual(SubscriptionV2.objects.count(), 0)

    # ── business-id scoping ──────────────────────────────────────────────────

    def test_business_id_filter(self):
        other_biz     = _make_hq(name="Other HQ", service="menu_qr")
        other_leg_sub = _make_legacy_sub(other_biz)

        _call("backfill_subscriptions", business_id=self.biz.id)

        other_ref = f"LEGACY-BILLING-SUB-{other_leg_sub.pk}"
        self.assertFalse(
            SubscriptionV2.objects.filter(external_reference=other_ref).exists()
        )

    # ── unknown service fallback ─────────────────────────────────────────────

    def test_unknown_service_defaults_to_gestion(self):
        self.biz.default_service = "nonexistent_service"
        self.biz.service_type    = None
        self.biz.save(update_fields=["default_service", "service_type"])

        output = _call("backfill_subscriptions")

        self.assertIn("defaulting to 'gestion'", output)
        ref = f"LEGACY-BILLING-SUB-{self.leg_sub.pk}"
        v2  = SubscriptionV2.objects.get(external_reference=ref)
        self.assertEqual(v2.service_type, SubscriptionV2.ServiceType.GESTION)
