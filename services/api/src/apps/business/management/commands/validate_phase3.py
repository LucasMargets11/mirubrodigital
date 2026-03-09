"""
Phase 3 — validate_phase3
==========================
Pre-flight and post-flight validation for all Phase 3 backfill commands.

PRE-FLIGHT  (--stage=pre)
--------------------------
Checks that the data is in a state where the backfill commands can run safely:

  PRE-1  Every HQ business has ≥ 1 active OWNER Membership.
  PRE-2  No Membership rows with NULL user_id (orphans).
  PRE-3  No duplicate CashRegister names within the same business.
  PRE-4  No existing SubscriptionV2 conflict (checks LEGACY-BILLING-SUB-* and
         LEGACY-BIZ-SUB-* formats; crossing will be skipped, not fail).
  PRE-5  No two CashSessions with status=OPEN for the same register.
  PRE-6  No CashSessions with opened_by_id pointing to a deleted User.
  PRE-7  Membership.branch_scope, if set, belongs to the HQ's family tree.
  PRE-8  No employee_code values outside EMP-NNNN format (collision risk).
  PRE-9  No LEGACY-BILLING-SUB-* / LEGACY-BIZ-SUB-* cross-contamination in
         SubscriptionV2 (same external_reference tagged to wrong business).

POST-FLIGHT  (--stage=post)
-----------------------------
Checks that the backfill completed correctly:

  POST-1  Every core operational Membership (cashier/kitchen/salon) has a
          linked EmployeeProfile; staff without EmployeeProfile → WARNING.
  POST-2  Every CashRegister has a corresponding Terminal.
  POST-3  All CashSessions that had a register FK now also have a terminal FK.
  POST-4  All legacy billing.Subscription rows have a SubscriptionV2 counterpart
          (LEGACY-BILLING-SUB-*); fallback business.Subscription rows checked as
          LEGACY-BIZ-SUB-* only when no billing.Subscription covered the HQ.
  POST-5  No duplicate employee_code values per business.
  POST-6  Every HQ business still has ≥ 1 active OWNER (post-backfill sanity).
  POST-7  List all EmployeeProfiles with _needs_role_review=true (staff migrants
          that require a human admin to verify and confirm the role_type).

Exit code
---------
  0  — all checks passed (optionally with warnings)
  1  — one or more ERRORs detected

Usage:
    python manage.py validate_phase3 [--stage=pre|post|both] [--business-id N]
"""
from __future__ import annotations

import sys
from collections import defaultdict

from django.db import connection
from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.accounts.models import EmployeeProfile, Membership
from apps.billing.models import Subscription as LegacyBillingSubscription, SubscriptionV2
from apps.business.models import Business, Subscription as LegacyBizSubscription
from apps.cash.models import CashRegister, CashSession, Terminal

# Core operational roles: auto-migrated to EmployeeProfile by backfill_employees
CORE_OPERATIONAL_ROLES = {'cashier', 'kitchen', 'salon'}
# Ambiguous: 'staff' only migrated when --include-staff is used
AMBIGUOUS_ROLES = {'staff'}
ALL_OPERATIONAL_ROLES  = CORE_OPERATIONAL_ROLES | AMBIGUOUS_ROLES


class Command(BaseCommand):
    help = (
        "Phase 3 — Run pre-flight or post-flight validation checks. "
        "Use --stage=pre before running backfill commands, "
        "--stage=post after, or --stage=both (default) for a complete report."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--stage',
            choices=['pre', 'post', 'both'],
            default='both',
            help='Validation stage to execute (default: both).',
        )
        parser.add_argument(
            '--business-id',
            type=int,
            default=None,
            help='Restrict to a single HQ business (integer PK).',
        )

    # -------------------------------------------------------------------------

    def handle(self, *args, **options):
        stage       = options['stage']
        business_id = options.get('business_id')

        qs = Business.objects.filter(parent__isnull=True)
        if business_id:
            qs = qs.filter(id=business_id)

        total = qs.count()
        self.stdout.write(f"\nValidating {total} HQ business(es) — stage={stage}\n")

        errors:   list[str] = []
        warnings: list[str] = []

        if stage in ('pre', 'both'):
            self.stdout.write(self.style.HTTP_INFO(
                "── PRE-FLIGHT CHECKS ──────────────────────────────────"
            ))
            e, w = self._pre_checks(qs)
            errors.extend(e)
            warnings.extend(w)

        if stage in ('post', 'both'):
            self.stdout.write(self.style.HTTP_INFO(
                "\n── POST-FLIGHT CHECKS ─────────────────────────────────"
            ))
            e, w = self._post_checks(qs)
            errors.extend(e)
            warnings.extend(w)

        self._print_final(errors, warnings)

        if errors:
            sys.exit(1)

    # ── PRE-FLIGHT ────────────────────────────────────────────────────────────

    def _missing_phase2a_tables(self) -> frozenset:
        """
        Returns the subset of Phase 2A table names that don't yet exist in the
        database.  Used to skip (not crash) checks that depend on those tables
        when migrations haven't been applied yet.
        """
        required = frozenset({
            'billing_subscriptionv2',
            'accounts_employeeprofile',
            'cash_terminal',
        })
        with connection.cursor() as cursor:
            existing = frozenset(connection.introspection.table_names(cursor))
        return required - existing

    def _pre_checks(self, businesses_qs) -> tuple[list[str], list[str]]:
        errors:   list[str] = []
        warnings: list[str] = []

        # ── Phase 2A table guard ───────────────────────────────────────────
        # PRE-4, PRE-8, PRE-9 query tables created by Phase 2A migrations.
        # If those migrations haven't been applied yet, report a clear error
        # and skip only the affected checks — PRE-1/2/3/5/6/7 still run.
        missing = self._missing_phase2a_tables()
        v2_ready = 'billing_subscriptionv2'   not in missing
        ep_ready = 'accounts_employeeprofile' not in missing
        if missing:
            for t in sorted(missing):
                errors.append(
                    f"[PREREQ] Table '{t}' does not exist — "
                    f"Phase 2A migrations have not been applied. "
                    f"Run `manage.py migrate` first. "
                    f"Dependent checks (PRE-4, PRE-8, PRE-9) are skipped."
                )
            self.stdout.write(self.style.WARNING(
                f"  WARNING: {len(missing)} Phase 2A table(s) missing — "
                f"some PRE checks skipped until `migrate` is run."
            ))

        for biz in businesses_qs.iterator():
            family_ids = [biz.id] + list(biz.branches.values_list('id', flat=True))

            # PRE-1: At least one active OWNER per HQ ──────────────────────
            active_owners = Membership.objects.filter(
                business=biz, role='owner', status=Membership.Status.ACTIVE
            ).count()
            if active_owners == 0:
                errors.append(
                    f"[PRE-1] Business #{biz.id} ({biz.name}): "
                    f"no active OWNER Membership."
                )
            elif active_owners > 5:
                warnings.append(
                    f"[PRE-1] Business #{biz.id}: {active_owners} OWNER memberships "
                    f"(unusually high — verify intentional)."
                )

            # PRE-2: No orphaned Memberships (NULL user) ───────────────────
            orphaned = Membership.objects.filter(
                business_id__in=family_ids, user__isnull=True
            ).count()
            if orphaned:
                errors.append(
                    f"[PRE-2] Business #{biz.id}: {orphaned} Membership(s) "
                    f"with NULL user_id."
                )

            # PRE-3: Duplicate CashRegister names per business ─────────────
            dup_regs = (
                CashRegister.objects
                .filter(business_id__in=family_ids)
                .values('business_id', 'name')
                .annotate(cnt=Count('id'))
                .filter(cnt__gt=1)
            )
            for d in dup_regs:
                errors.append(
                    f"[PRE-3] Business #{d['business_id']}: "
                    f"duplicate CashRegister name '{d['name']}' "
                    f"({d['cnt']} rows)."
                )

            # PRE-4: Check SubscriptionV2 conflicts for both legacy sources ───
            # New external_reference format: LEGACY-BILLING-SUB-{pk} / LEGACY-BIZ-SUB-{pk}
            if v2_ready:
              raw_service = (
                getattr(biz, 'service_type', None)
                or getattr(biz, 'default_service', None)
                or 'gestion'
              )
              for leg in LegacyBillingSubscription.objects.filter(business_id__in=family_ids):
                expected_ref = f"LEGACY-BILLING-SUB-{leg.pk}"
                conflict = (
                    SubscriptionV2.objects
                    .filter(business=biz, service_type=raw_service)
                    .exclude(status=SubscriptionV2.Status.CANCELED)
                    .exclude(external_reference=expected_ref)
                    .exists()
                )
                if conflict:
                    warnings.append(
                        f"[PRE-4] Business #{biz.id}: active SubscriptionV2 already "
                        f"exists for service='{raw_service}'. "
                        f"backfill_subscriptions (Pass 1) will skip "
                        f"billing.Subscription {leg.pk}."
                    )
              # Also check fallback source (only for HQs without billing.Subscription)
              has_billing_sub = LegacyBillingSubscription.objects.filter(
                business_id__in=family_ids
              ).exists()
              if not has_billing_sub:
                for biz_sub in LegacyBizSubscription.objects.filter(
                    business_id__in=family_ids
                ):
                    expected_ref = f"LEGACY-BIZ-SUB-{biz_sub.pk}"
                    conflict = (
                        SubscriptionV2.objects
                        .filter(business=biz, service_type=raw_service)
                        .exclude(status=SubscriptionV2.Status.CANCELED)
                        .exclude(external_reference=expected_ref)
                        .exists()
                    )
                    if conflict:
                        warnings.append(
                            f"[PRE-4] Business #{biz.id}: active SubscriptionV2 already "
                            f"exists for service='{raw_service}'. "
                            f"backfill_subscriptions (Pass 2) will skip "
                            f"business.Subscription {biz_sub.pk}."
                        )

            # PRE-5: No two CashSessions with status=OPEN for the same register ─
            open_dup_registers = (
                CashSession.objects
                .filter(
                    business_id__in=family_ids,
                    status=CashSession.Status.OPEN,
                    register__isnull=False,
                )
                .values('register_id')
                .annotate(cnt=Count('id'))
                .filter(cnt__gt=1)
            )
            for row in open_dup_registers:
                errors.append(
                    f"[PRE-5] Business #{biz.id}: CashRegister {row['register_id']} "
                    f"has {row['cnt']} OPEN CashSessions — only 1 allowed at a time."
                )

            # PRE-6: CashSessions opened_by pointing to non-existent User ────
            from django.contrib.auth import get_user_model
            User = get_user_model()
            existing_user_ids = set(
                User.objects.values_list('id', flat=True)
            )
            ghost_count = (
                CashSession.objects
                .filter(
                    business_id__in=family_ids,
                    opened_by__isnull=False,
                )
                .exclude(opened_by_id__in=existing_user_ids)
                .count()
            )
            if ghost_count:
                errors.append(
                    f"[PRE-6] Business #{biz.id}: {ghost_count} CashSession(s) "
                    f"have opened_by_id pointing to a non-existent User."
                )

            # PRE-7: Membership.branch_scope belongs to correct HQ tree ─────
            scoped_membs = (
                Membership.objects
                .filter(business_id__in=family_ids)
                .exclude(branch_scope__isnull=True)
                .select_related('branch_scope')
            )
            branch_ids_in_family = set(family_ids)
            for sm in scoped_membs:
                if sm.branch_scope_id not in branch_ids_in_family:
                    errors.append(
                        f"[PRE-7] Business #{biz.id}: Membership {sm.id} "
                        f"has branch_scope_id={sm.branch_scope_id} which is NOT "
                        f"in the HQ family tree (parent_id={biz.id})."
                    )

            # PRE-8: Employee code collision risk ─────────────────────────────
            # Check that existing EMP-NNNN codes won't conflict with new backfill.
            # The backfill command's _next_code_start avoids collisions at runtime;
            # this check flags if there are already non-EMP-NNNN codes that could
            # conflict with EMP-0001 … EMP-9999 range.
            if ep_ready:
              import re as _re
              bad_codes = (
                EmployeeProfile.objects
                .filter(business=biz)
                .exclude(employee_code__regex=r'^EMP-\d{4}$')
                .values_list('employee_code', flat=True)
              )
              for code in bad_codes:
                warnings.append(
                    f"[PRE-8] Business #{biz.id}: EmployeeProfile has "
                    f"employee_code='{code}' that doesn't match EMP-NNNN format — "
                    f"review manually; backfill will not overwrite existing codes."
                )

            # PRE-9: No LEGACY-BILLING-SUB-* or LEGACY-BIZ-SUB-* cross-contamination ─
            # Ensure no SubscriptionV2 row for THIS HQ was tagged as belonging to
            # a DIFFERENT business (would indicate an earlier migration mistake).
            if v2_ready:
                contaminated = (
                    SubscriptionV2.objects
                    .filter(external_reference__startswith='LEGACY-BILLING-SUB-')
                    .exclude(business=biz)
                    .filter(
                        external_reference__in=[
                            f"LEGACY-BILLING-SUB-{leg.pk}"
                            for leg in LegacyBillingSubscription.objects.filter(
                                business_id__in=family_ids
                            )
                        ]
                    )
                )
                for cv2 in contaminated:
                    errors.append(
                        f"[PRE-9] SubscriptionV2 {cv2.id} has "
                        f"external_reference='{cv2.external_reference}' but "
                        f"business_id={cv2.business_id} ≠ HQ #{biz.id} — cross-contamination!"
                    )
                contaminated_biz = (
                    SubscriptionV2.objects
                    .filter(external_reference__startswith='LEGACY-BIZ-SUB-')
                    .exclude(business=biz)
                    .filter(
                        external_reference__in=[
                            f"LEGACY-BIZ-SUB-{bs.pk}"
                            for bs in LegacyBizSubscription.objects.filter(
                                business_id__in=family_ids
                            )
                        ]
                    )
                )
                for cv2 in contaminated_biz:
                    errors.append(
                        f"[PRE-9] SubscriptionV2 {cv2.id} has "
                        f"external_reference='{cv2.external_reference}' but "
                        f"business_id={cv2.business_id} ≠ HQ #{biz.id} — cross-contamination!"
                    )
        self.stdout.write(
            f"  PRE checks: {len(errors)} error(s), {len(warnings)} warning(s)."
        )
        return errors, warnings

    # ── POST-FLIGHT ───────────────────────────────────────────────────────────

    def _post_checks(self, businesses_qs) -> tuple[list[str], list[str]]:
        errors:   list[str] = []
        warnings: list[str] = []

        # ── Phase 2A table guard ───────────────────────────────────────────
        # All POST checks query Phase 2A tables. If they don't exist, the
        # backfill definitely hasn't run — report each missing table as an
        # ERROR and return early rather than crashing.
        missing = self._missing_phase2a_tables()
        if missing:
            for t in sorted(missing):
                errors.append(
                    f"[POST-PREREQ] Table '{t}' does not exist — "
                    f"Phase 2A migrations have not been applied. "
                    f"Run `manage.py migrate` then re-run the backfill commands "
                    f"before running --stage=post."
                )
            self.stdout.write(
                f"  POST checks: {len(errors)} error(s), 0 warning(s)."
            )
            return errors, warnings

        for biz in businesses_qs.iterator():
            family_ids = [biz.id] + list(biz.branches.values_list('id', flat=True))

            # POST-1: Every CORE operational Membership has a linked EmployeeProfile
            # Core roles (cashier/kitchen/salon) → ERROR if no EmployeeProfile.
            # Ambiguous role (staff) → WARNING if no EmployeeProfile
            #   (may be intentional if --include-staff was not used).
            core_memberships = (
                Membership.objects
                .filter(business_id__in=family_ids, role__in=CORE_OPERATIONAL_ROLES)
                .select_related('user')
            )
            for m in core_memberships:
                if m.user_id is None:
                    continue  # orphaned — caught by PRE-2
                ep_exists = EmployeeProfile.objects.filter(
                    business=biz, linked_user=m.user
                ).exists()
                if not ep_exists:
                    errors.append(
                        f"[POST-1] Business #{biz.id}: Membership {m.id} "
                        f"(role={m.role}, user={m.user}) has no linked EmployeeProfile."
                    )
            # Staff: warning only
            staff_memberships = (
                Membership.objects
                .filter(business_id__in=family_ids, role__in=AMBIGUOUS_ROLES)
                .select_related('user')
            )
            for m in staff_memberships:
                if m.user_id is None:
                    continue
                ep_exists = EmployeeProfile.objects.filter(
                    business=biz, linked_user=m.user
                ).exists()
                if not ep_exists:
                    warnings.append(
                        f"[POST-1] Business #{biz.id}: Membership {m.id} "
                        f"(role='staff', user={m.user}) has no EmployeeProfile — "
                        f"expected if backfill ran without --include-staff."
                    )

            # POST-2: Every CashRegister has a Terminal ────────────────────
            registers = CashRegister.objects.filter(business_id__in=family_ids)
            for reg in registers:
                if not Terminal.objects.filter(cash_register=reg).exists():
                    errors.append(
                        f"[POST-2] Business #{biz.id}: "
                        f"CashRegister {reg.id} ({reg.name}) has no Terminal."
                    )

            # POST-3: All CashSessions that had register also have terminal ─
            sessions_missing = (
                CashSession.objects
                .filter(
                    business_id__in=family_ids,
                    register__isnull=False,
                    terminal__isnull=True,
                )
                .count()
            )
            if sessions_missing:
                errors.append(
                    f"[POST-3] Business #{biz.id}: {sessions_missing} CashSession(s) "
                    f"have a register FK but no terminal FK."
                )

            # POST-4: All legacy subscriptions have a SubscriptionV2 counterpart ─
            # Check billing.Subscription (primary source: LEGACY-BILLING-SUB-*)
            for leg in LegacyBillingSubscription.objects.filter(
                business_id__in=family_ids
            ):
                ref = f"LEGACY-BILLING-SUB-{leg.pk}"
                if not SubscriptionV2.objects.filter(external_reference=ref).exists():
                    errors.append(
                        f"[POST-4] Business #{biz.id}: "
                        f"billing.Subscription {leg.pk} not migrated to SubscriptionV2 "
                        f"(expected external_reference='{ref}')."
                    )
            # Check business.Subscription (fallback: LEGACY-BIZ-SUB-*)
            # Only flag if no billing.Subscription covers this HQ (else Pass 1 handled it)
            has_billing = LegacyBillingSubscription.objects.filter(
                business_id__in=family_ids
            ).exists()
            if not has_billing:
                for bsub in LegacyBizSubscription.objects.filter(
                    business_id__in=family_ids
                ):
                    ref = f"LEGACY-BIZ-SUB-{bsub.pk}"
                    if not SubscriptionV2.objects.filter(external_reference=ref).exists():
                        errors.append(
                            f"[POST-4] Business #{biz.id}: "
                            f"business.Subscription {bsub.pk} not migrated to "
                            f"SubscriptionV2 (expected external_reference='{ref}')."
                        )

            # POST-5: No duplicate employee_code per HQ ────────────────────
            dup_codes = (
                EmployeeProfile.objects
                .filter(business=biz)
                .values('employee_code')
                .annotate(cnt=Count('id'))
                .filter(cnt__gt=1)
            )
            for d in dup_codes:
                errors.append(
                    f"[POST-5] Business #{biz.id}: "
                    f"duplicate employee_code '{d['employee_code']}' "
                    f"({d['cnt']} rows) — DB UniqueConstraint should have prevented this!"
                )

            # POST-6: Still has ≥ 1 active OWNER ──────────────────────────
            active_owners = Membership.objects.filter(
                business=biz, role='owner', status=Membership.Status.ACTIVE
            ).count()
            if active_owners == 0:
                errors.append(
                    f"[POST-6] Business #{biz.id} ({biz.name}): "
                    f"no active OWNER after backfill."
                )
        # POST-7: List all EmployeeProfiles with _needs_role_review=True ─────
        # These were created with role_type=CASHIER from a 'staff' Membership
        # via --include-staff and require a human admin to verify the role.
        #
        # PostgreSQL JSONB operator: @> ({'_needs_role_review': true})
        # For cross-DB compatibility we filter in Python after a targeted query.
        review_eps = EmployeeProfile.objects.filter(
            business__in=businesses_qs,
        ).select_related('business', 'linked_user')
        flagged = [
            ep for ep in review_eps
            if isinstance(ep.permission_overrides, dict)
            and ep.permission_overrides.get('_needs_role_review') is True
        ]
        if flagged:
            warnings.append(
                f"[POST-7] {len(flagged)} EmployeeProfile(s) have "
                f"_needs_role_review=true (migrated from 'staff' role). "
                f"Review and assign correct role_type:"
            )
            for ep in flagged:
                warnings.append(
                    f"[POST-7]   → EmployeeProfile {ep.id} ({ep.first_name} {ep.last_name}) "
                    f"business=#{ep.business_id} "
                    f"linked_user={ep.linked_user}"
                )
        self.stdout.write(
            f"  POST checks: {len(errors)} error(s), {len(warnings)} warning(s)."
        )
        return errors, warnings

    # ── REPORTING ─────────────────────────────────────────────────────────────

    def _print_final(self, errors: list[str], warnings: list[str]):
        sep = "=" * 56
        self.stdout.write(f"\n{sep}")
        self.stdout.write("  validate_phase3  RESULTS")
        self.stdout.write(sep)

        if warnings:
            self.stdout.write(self.style.WARNING(
                f"\n  WARNINGS  ({len(warnings)}):"
            ))
            for w in warnings:
                self.stdout.write(self.style.WARNING(f"    ⚠  {w}"))

        if errors:
            self.stdout.write(self.style.ERROR(
                f"\n  ERRORS  ({len(errors)}):"
            ))
            for e in errors:
                self.stdout.write(self.style.ERROR(f"    ✗  {e}"))
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(
                "  RESULT: FAILED  — fix the errors above and re-run."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n  RESULT: PASSED  — all Phase 3 checks OK."
            ))

        self.stdout.write(sep + "\n")
