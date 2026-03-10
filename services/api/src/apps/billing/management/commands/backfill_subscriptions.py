"""
Phase 3 — backfill_subscriptions
==================================
Creates a SubscriptionV2 record for every existing `billing.Subscription` row
that has not yet been migrated.

Coexistence strategy
--------------------
  billing.Subscription  (legacy OneToOne)  ──┐  both kept during Phase 3
  business.Subscription (legacy OneToOne)  ──┘  (no deletions in this phase)
  billing.SubscriptionV2 (new FK, Phase 2A)  ←  canonical target

Idempotency key
---------------
SubscriptionV2.external_reference = "LEGACY-SUB-{billing.Subscription.pk}"
Re-running the command skips any row whose external_reference already exists.

Service type resolution order
------------------------------
  1. business.service_type      (Phase 2A canonical, populated by migration 0016)
  2. business.default_service   (legacy fallback)
  3. 'gestion'                  (hard default)

Plan code derivation (best-effort)
------------------------------------
  1. billing.Subscription.plan.code           (Plan FK is set)
  2. "bundle-{bundle.code}-{billing_period}"  (Bundle FK is set)
  3. "legacy-{plan_type}-{billing_period}"    (fallback)

Status mapping
--------------
  active   → ACTIVE
  trial    → TRIALING
  past_due → PAST_DUE
  canceled → CANCELED

IDEMPOTENT: safe to run multiple times.

Usage:
    python manage.py backfill_subscriptions [--dry-run] [--business-id N]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from apps.billing.models import Subscription as LegacyBillingSubscription, SubscriptionV2
from apps.business.models import Subscription as LegacyBizSubscription

# Mapping billing.Subscription.status → SubscriptionV2.Status  (4-value, includes 'trial')
BILLING_STATUS_MAP: dict[str, str] = {
    'active':   SubscriptionV2.Status.ACTIVE,
    'trial':    SubscriptionV2.Status.TRIALING,
    'past_due': SubscriptionV2.Status.PAST_DUE,
    'canceled': SubscriptionV2.Status.CANCELED,
}

# Mapping business.Subscription.status → SubscriptionV2.Status  (3-value, no 'trial')
BIZ_STATUS_MAP: dict[str, str] = {
    'active':   SubscriptionV2.Status.ACTIVE,
    'past_due': SubscriptionV2.Status.PAST_DUE,
    'canceled': SubscriptionV2.Status.CANCELED,
}

# Mapping legacy service strings → SubscriptionV2.ServiceType
SERVICE_MAP: dict[str, str] = {
    'gestion':        SubscriptionV2.ServiceType.GESTION,
    'restaurante':    SubscriptionV2.ServiceType.RESTAURANTE,
    'menu_qr':        SubscriptionV2.ServiceType.MENU_QR,
    'menu_qr_visual': SubscriptionV2.ServiceType.MENU_QR_VISUAL,
    'menu_qr_marca':  SubscriptionV2.ServiceType.MENU_QR_MARCA,
}


class Command(BaseCommand):
    help = (
        "Phase 3 — Create SubscriptionV2 records from legacy billing.Subscription "
        "(primary) and business.Subscription (fallback) rows. "
        "Legacy rows are NOT deleted."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate without writing to the database.',
        )
        parser.add_argument(
            '--business-id',
            type=int,
            default=None,
            help='Restrict to a single business (integer PK).',
        )

    # -------------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run     = options['dry_run']
        business_id = options.get('business_id')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN mode — no changes will be written.\n"
            ))

        summary = {
            'billing_processed': 0,
            'billing_created':   0,
            'billing_skipped':   0,
            'biz_processed':     0,
            'biz_created':       0,
            'biz_skipped':       0,
            'conflict_blocked':  0,
            'service_unknown':   0,
            'errors':            0,
        }

        # ── Pass 1: billing.Subscription (PRIMARY) ─────────────────────────
        self.stdout.write(
            "\n── Pass 1: billing.Subscription (PRIMARY) ──────────────"
        )
        billing_qs = LegacyBillingSubscription.objects.select_related(
            'business', 'plan', 'bundle'
        )
        if business_id:
            billing_qs = billing_qs.filter(business_id=business_id)

        # Track which HQ IDs are already covered so Pass 2 skips them
        covered_hq_ids: set[int] = set()
        for leg in billing_qs.iterator():
            hq = leg.business.parent if leg.business.parent_id else leg.business
            covered_hq_ids.add(hq.id)
            summary['billing_processed'] += 1
            self._process_billing_sub(leg, hq, dry_run, summary)

        # ── Pass 2: business.Subscription (FALLBACK) ───────────────────────
        self.stdout.write(
            f"\n── Pass 2: business.Subscription (FALLBACK, "
            f"{len(covered_hq_ids)} HQ(s) already covered by Pass 1) ──"
        )
        biz_qs = LegacyBizSubscription.objects.select_related('business')
        if business_id:
            biz_qs = biz_qs.filter(business_id=business_id)

        for biz_sub in biz_qs.iterator():
            hq = biz_sub.business.parent if biz_sub.business.parent_id else biz_sub.business
            if hq.id in covered_hq_ids:
                self.stdout.write(
                    f"  SKIP  business.Subscription {biz_sub.pk} for HQ #{hq.id}: "
                    f"already covered by billing.Subscription (Pass 1)."
                )
                summary['biz_skipped'] += 1
                continue
            summary['biz_processed'] += 1
            self._process_biz_sub(biz_sub, hq, dry_run, summary)

        self._print_summary(summary, dry_run)

    # -------------------------------------------------------------------------

    # ── Pass 1 helper ─────────────────────────────────────────────────────────

    def _process_billing_sub(self, leg, hq, dry_run, summary):
        external_reference = f"LEGACY-BILLING-SUB-{leg.pk}"

        # Idempotency guard
        if SubscriptionV2.objects.filter(external_reference=external_reference).exists():
            self.stdout.write(
                f"  SKIP  billing.Subscription {leg.pk} "
                f"(already migrated as {external_reference})."
            )
            summary['billing_skipped'] += 1
            return

        service_type = self._resolve_service(hq, 'billing.Subscription', leg.pk, summary)
        v2_status    = BILLING_STATUS_MAP.get(leg.status, SubscriptionV2.Status.ACTIVE)
        plan_code    = self._derive_plan_code_billing(leg)

        # Conflict guard: another non-canceled V2 for (hq, service_type) with different ref
        if self._has_conflict(hq, service_type, external_reference):
            summary['conflict_blocked'] += 1
            self.stdout.write(self.style.ERROR(
                f"  CONFLICT  HQ #{hq.id}: non-canceled SubscriptionV2 already exists "
                f"for service='{service_type}' with a different external_reference. "
                f"Skipping billing.Subscription {leg.pk}. Manual review required."
            ))
            return

        # Price snapshot: billing data + optional business.Subscription metadata
        price_snapshot = dict(leg.price_snapshot or {})
        price_snapshot['_migrated_from'] = 'billing.Subscription'
        price_snapshot['_legacy_id']     = leg.pk
        # Merge business.Subscription metadata if both exist for the same HQ
        try:
            biz_sub = hq.subscription  # related_name='subscription' on business.Subscription
            price_snapshot['_biz_sub_id']           = biz_sub.pk
            price_snapshot['_biz_sub_plan']         = biz_sub.plan
            price_snapshot['_biz_sub_max_seats']    = biz_sub.max_seats
            price_snapshot['_biz_sub_max_branches'] = biz_sub.max_branches
        except Exception:
            pass  # No business.Subscription for this HQ — that is fine

        self.stdout.write(
            f"  CREATE  SubscriptionV2 for HQ #{hq.id} "
            f"(service={service_type}, plan={plan_code}, status={v2_status}) "
            f"\u2190 billing.Subscription {leg.pk}"
        )

        if dry_run:
            summary['billing_created'] += 1
            return

        try:
            with transaction.atomic():
                SubscriptionV2.objects.create(
                    business=hq,
                    service_type=service_type,
                    plan_code=plan_code,
                    provider=SubscriptionV2.Provider.MANUAL,
                    provider_sub_id=leg.mp_preapproval_id or None,
                    external_reference=external_reference,
                    status=v2_status,
                    current_period_end=leg.current_period_end,
                    price_snapshot=price_snapshot,
                )
            summary['billing_created'] += 1
        except IntegrityError as exc:
            summary['errors'] += 1
            self.stdout.write(self.style.ERROR(
                f"  ERROR  billing.Subscription {leg.pk}: {exc}"
            ))

    # ── Pass 2 helper ─────────────────────────────────────────────────────────

    def _process_biz_sub(self, biz_sub, hq, dry_run, summary):
        external_reference = f"LEGACY-BIZ-SUB-{biz_sub.pk}"

        # Idempotency guard
        if SubscriptionV2.objects.filter(external_reference=external_reference).exists():
            self.stdout.write(
                f"  SKIP  business.Subscription {biz_sub.pk} "
                f"(already migrated as {external_reference})."
            )
            summary['biz_skipped'] += 1
            return

        raw_service = (
            getattr(hq, 'service_type', None)
            or getattr(hq, 'default_service', None)
            or getattr(biz_sub, 'service', None)
            or 'gestion'
        )
        service_type = SERVICE_MAP.get(raw_service)
        if service_type is None:
            self.stdout.write(self.style.WARNING(
                f"  WARN  HQ #{hq.id}: unknown service '{raw_service}' "
                f"\u2192 defaulting to 'gestion'."
            ))
            service_type = SubscriptionV2.ServiceType.GESTION
            summary['service_unknown'] += 1

        v2_status = BIZ_STATUS_MAP.get(biz_sub.status, SubscriptionV2.Status.ACTIVE)
        plan_code = biz_sub.plan or 'legacy-unknown'

        # Conflict guard
        if self._has_conflict(hq, service_type, external_reference):
            summary['conflict_blocked'] += 1
            self.stdout.write(self.style.ERROR(
                f"  CONFLICT  HQ #{hq.id}: non-canceled SubscriptionV2 already exists "
                f"for service='{service_type}' with a different external_reference. "
                f"Skipping business.Subscription {biz_sub.pk}. Manual review required."
            ))
            return

        price_snapshot = {
            '_migrated_from':       'business.Subscription',
            '_legacy_id':           biz_sub.pk,
            '_biz_sub_plan':        biz_sub.plan,
            '_biz_sub_max_seats':   biz_sub.max_seats,
            '_biz_sub_max_branches': biz_sub.max_branches,
            '_biz_sub_renews_at':   str(biz_sub.renews_at) if biz_sub.renews_at else None,
            '_biz_sub_pro_included': biz_sub.pro_included_module,
        }

        self.stdout.write(
            f"  CREATE  SubscriptionV2 for HQ #{hq.id} "
            f"(service={service_type}, plan={plan_code}, status={v2_status}) "
            f"\u2190 business.Subscription {biz_sub.pk} [FALLBACK]"
        )

        if dry_run:
            summary['biz_created'] += 1
            return

        try:
            with transaction.atomic():
                SubscriptionV2.objects.create(
                    business=hq,
                    service_type=service_type,
                    plan_code=plan_code,
                    provider=SubscriptionV2.Provider.MANUAL,
                    provider_sub_id=None,
                    external_reference=external_reference,
                    status=v2_status,
                    current_period_end=biz_sub.renews_at,
                    price_snapshot=price_snapshot,
                )
            summary['biz_created'] += 1
        except IntegrityError as exc:
            summary['errors'] += 1
            self.stdout.write(self.style.ERROR(
                f"  ERROR  business.Subscription {biz_sub.pk}: {exc}"
            ))

    # ── Shared helpers ─────────────────────────────────────────────────────────

    def _resolve_service(self, hq, source_label: str, leg_pk: int, summary) -> str:
        """Resolve service_type string for hq, defaulting to 'gestion'."""
        raw_service = (
            getattr(hq, 'service_type', None)
            or getattr(hq, 'default_service', None)
            or 'gestion'
        )
        service_type = SERVICE_MAP.get(raw_service)
        if service_type is None:
            self.stdout.write(self.style.WARNING(
                f"  WARN  HQ #{hq.id}: unknown service '{raw_service}' "
                f"\u2192 defaulting to 'gestion' ({source_label} {leg_pk})."
            ))
            service_type = SubscriptionV2.ServiceType.GESTION
            summary['service_unknown'] += 1
        return service_type

    def _has_conflict(self, hq, service_type: str, expected_ref: str) -> bool:
        """True if a non-canceled SubscriptionV2 for (hq, service_type) exists
        with a DIFFERENT external_reference (would block a new insert)."""
        return (
            SubscriptionV2.objects
            .filter(business=hq, service_type=service_type)
            .exclude(status=SubscriptionV2.Status.CANCELED)
            .exclude(external_reference=expected_ref)
            .exists()
        )

    def _derive_plan_code_billing(self, sub) -> str:
        """Best-effort derivation of plan_code from a billing.Subscription row.

        Priority:
          1. billing.Subscription.plan.code  (e.g. 'gestion_pro' from billing.Plan FK)
          2. billing.Subscription.bundle.code (e.g. 'gestion_pro', 'menu_qr_visual')
             Stored as the raw bundle code — NOT wrapped as 'bundle-{code}-{period}'
             so that billing.runtime._extract_plan_tier() can parse it directly.
          3. 'legacy-{plan_type}-{billing_period}' as last-resort fallback.
        """
        if sub.plan_id and sub.plan:
            return sub.plan.code
        if sub.bundle_id and sub.bundle:
            # Store bundle.code directly (e.g. 'gestion_pro', 'menu_qr_visual').
            # The old format 'bundle-{code}-{period}' was not parseable by
            # _extract_plan_tier and caused feature flags to fall back to 'starter'.
            return sub.bundle.code
        return f"legacy-{sub.plan_type}-{sub.billing_period}"

    # ── Summary ────────────────────────────────────────────────────────────────

    def _print_summary(self, summary, dry_run):
        mode = "[DRY-RUN] " if dry_run else ""
        sep  = "=" * 62
        self.stdout.write(f"\n{sep}")
        self.stdout.write(f"  {mode}backfill_subscriptions  SUMMARY")
        self.stdout.write(sep)
        self.stdout.write("  Pass 1 (billing.Subscription — PRIMARY):")
        self.stdout.write(f"    Processed : {summary['billing_processed']}")
        self.stdout.write(f"    Created   : {summary['billing_created']}")
        self.stdout.write(f"    Skipped   : {summary['billing_skipped']}")
        self.stdout.write("  Pass 2 (business.Subscription — FALLBACK):")
        self.stdout.write(f"    Processed : {summary['biz_processed']}")
        self.stdout.write(f"    Created   : {summary['biz_created']}")
        self.stdout.write(f"    Skipped   : {summary['biz_skipped']}")
        if summary['conflict_blocked']:
            self.stdout.write(self.style.ERROR(
                f"  Conflicts blocked (manual review): {summary['conflict_blocked']}"
            ))
        if summary['service_unknown']:
            self.stdout.write(self.style.WARNING(
                f"  Unknown service (defaulted to gestion): {summary['service_unknown']}"
            ))
        if summary['errors']:
            self.stdout.write(self.style.ERROR(
                f"  Errors: {summary['errors']}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS("  No errors."))
        self.stdout.write(sep)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN complete. Re-run without --dry-run to apply.\n"
            ))
