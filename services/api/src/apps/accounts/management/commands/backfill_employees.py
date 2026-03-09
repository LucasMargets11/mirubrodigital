"""
Phase 3 — backfill_employees
=============================
Migrates operational-role Membership rows into EmployeeProfile records.

Role classification (FINAL — closed decision)
----------------------------------------------
ADMINISTRATIVE (stay in Membership, not migrated to EmployeeProfile):
  owner, admin, manager, viewer
  analyst   → also stays in Membership; DEPRECATED (same permissions as viewer
              in rbac.py gestion block); a WARNING is emitted per occurrence.

CORE OPERATIONAL (auto-migrated to EmployeeProfile):
  cashier  →  RoleType.CASHIER
  kitchen  →  RoleType.KITCHEN
  salon    →  RoleType.SERVER   (mozo/salón)

AMBIGUOUS OPERATIONAL (default: flagged for manual review, NOT auto-migrated):
  staff    →  rbac.py gives staff dashboard-level read access (view_reports,
              view_stock, view_purchases) that a POS CASHIER does not have.
              Silent mapping to CASHIER would be a permission demotion.
              Default behaviour: list as NEEDS_REVIEW, skip migration.
              Override with --include-staff to create EmployeeProfile
              (role_type=CASHIER + _needs_role_review: true) while
              keeping the Membership in place.

For every auto-migrated Membership the command will:
  1. Skip if an EmployeeProfile already exists for the same (HQ business,
     linked_user) pair  →  idempotent.
  2. Build first_name / last_name / alias from auth.User fields.
  3. Generate a unique employee_code per HQ business (EMP-0001, EMP-0002…).
  4. Set must_change_pin=True and login_code_hash to an unusable hash.
  5. Copy branch_scope from the Membership onto the EmployeeProfile.branch.
  6. Store full migration provenance in permission_overrides (see below).
  7. Does NOT delete or modify the original Membership row.

Provenance stored in permission_overrides
------------------------------------------
  _migrated_from        : 'membership'
  _legacy_membership_id : <int>  — original Membership.pk
  _legacy_role          : <str>  — original Membership.role value
  _legacy_business_id   : <int>  — original Membership.business_id
  _needs_role_review    : true   — present ONLY for staff migrations

IDEMPOTENT: safe to run multiple times.

Usage:
    python manage.py backfill_employees [--dry-run] [--business-id N]
    python manage.py backfill_employees --include-staff   # also migrate staff
"""
from __future__ import annotations

import re

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from apps.accounts.models import EmployeeProfile, Membership
from apps.business.models import Business

# Roles migrated automatically to EmployeeProfile
CORE_OPERATIONAL_ROLES = {'cashier', 'kitchen', 'salon'}

# Roles that are AMBIGUOUS — not auto-migrated without explicit --include-staff
STAFF_ROLES = {'staff'}

# Roles that always remain in Membership (never become EmployeeProfile)
ADMIN_ROLES = {'owner', 'admin', 'manager', 'viewer', 'analyst'}

# 'analyst' is deprecated — same permission set as 'viewer' in rbac.py.
# It stays in Membership but produces a per-occurrence WARNING.
DEPRECATED_ADMIN_ROLES = {'analyst'}

# Membership.role  →  EmployeeProfile.RoleType
ROLE_MAP = {
    'cashier': EmployeeProfile.RoleType.CASHIER,
    'kitchen': EmployeeProfile.RoleType.KITCHEN,
    'salon':   EmployeeProfile.RoleType.SERVER,
    # 'staff' handled separately (see --include-staff flag)
}

STATUS_MAP = {
    Membership.Status.ACTIVE:    EmployeeProfile.Status.ACTIVE,
    Membership.Status.INACTIVE:  EmployeeProfile.Status.INACTIVE,
    Membership.Status.SUSPENDED: EmployeeProfile.Status.SUSPENDED,
}


class Command(BaseCommand):
    help = (
        "Phase 3 — Migrate operational Membership roles to EmployeeProfile. "
        "Legacy Membership rows are NOT deleted."
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
            help='Restrict to a single HQ business (integer PK).',
        )
        parser.add_argument(
            '--include-staff',
            action='store_true',
            help=(
                'Also migrate "staff" role Memberships to EmployeeProfile '
                '(role_type=CASHIER, _needs_role_review=true). '
                'Keeps the Membership in place. Requires human follow-up '
                'via validate_phase3 --stage=post to review each case.'
            ),
        )

    # -------------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run       = options['dry_run']
        business_id   = options.get('business_id')
        include_staff = options.get('include_staff', False)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN mode — no changes will be written.\n"
            ))
        if include_staff:
            self.stdout.write(self.style.WARNING(
                "--include-staff: staff memberships will be migrated as CASHIER "
                "with _needs_role_review=true. Review them after with "
                "validate_phase3 --stage=post.\n"
            ))

        qs = Business.objects.filter(parent__isnull=True)
        if business_id:
            qs = qs.filter(id=business_id)

        summary = {
            'businesses':             0,
            'employees_created':      0,
            'employees_review_flag':  0,   # staff migrated with _needs_role_review
            'already_linked':         0,
            'staff_skipped_review':   0,   # staff NOT migrated (default)
            'analyst_deprecated':     0,   # analyst memberships warned
            'skipped_no_user':        0,
            'errors':                 0,
        }

        for business in qs.iterator():
            self._process_business(business, dry_run, include_staff, summary)
            summary['businesses'] += 1

        self._print_summary(summary, dry_run, include_staff)

    # -------------------------------------------------------------------------

    def _process_business(self, business, dry_run, include_staff, summary):
        self.stdout.write(f"\n── Business #{business.id}: {business.name} ──")

        # Include branches: employees in a branch still belong to HQ
        family_ids = [business.id] + list(
            business.branches.values_list('id', flat=True)
        )

        # --- Warn about deprecated 'analyst' memberships (stays in Membership) ---
        analyst_qs = (
            Membership.objects
            .filter(business_id__in=family_ids, role__in=DEPRECATED_ADMIN_ROLES)
            .select_related('user')
        )
        for am in analyst_qs:
            self.stdout.write(self.style.WARNING(
                f"  DEPRECATED_ROLE  Membership {am.id} ({am.user}): "
                f"role='{am.role}' has identical permissions to 'viewer' in rbac.py. "
                f"Will NOT be migrated to EmployeeProfile. "
                f"Recommend manual remap to 'viewer'."
            ))
            summary['analyst_deprecated'] += 1

        # --- Determine which roles to process ---
        active_roles = set(CORE_OPERATIONAL_ROLES)
        if include_staff:
            active_roles |= STAFF_ROLES

        op_memberships = (
            Membership.objects
            .filter(business_id__in=family_ids, role__in=active_roles)
            .select_related('user', 'business', 'branch_scope')
            .order_by('id')
        )

        # Report staff members that will be skipped (when --include-staff not set)
        if not include_staff:
            staff_pending = (
                Membership.objects
                .filter(business_id__in=family_ids, role__in=STAFF_ROLES)
                .select_related('user')
            )
            for sm in staff_pending:
                self.stdout.write(self.style.WARNING(
                    f"  NEEDS_REVIEW  Membership {sm.id} ({sm.user}): "
                    f"role='staff' is ambiguous — has dashboard read permissions. "
                    f"Run with --include-staff to migrate as CASHIER+review flag, "
                    f"or manually reassign the role first."
                ))
                summary['staff_skipped_review'] += 1

        if not op_memberships.exists():
            self.stdout.write("  No operational memberships found.")
            return

        # Build the set of existing codes for this HQ to avoid collisions
        existing_codes: set[str] = set(
            EmployeeProfile.objects.filter(business=business)
            .values_list('employee_code', flat=True)
        )
        next_n = self._next_code_start(existing_codes)

        for m in op_memberships:
            if not m.user_id:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP  Membership {m.id}: no user linked (orphan)."
                ))
                summary['skipped_no_user'] += 1
                continue

            # Idempotency guard
            existing = EmployeeProfile.objects.filter(
                business=business, linked_user_id=m.user_id
            ).first()
            if existing:
                self.stdout.write(
                    f"  SKIP  Membership {m.id} ({m.user}): "
                    f"EmployeeProfile {existing.id} already linked."
                )
                summary['already_linked'] += 1
                continue

            # Determine branch:
            #   - take the explicit branch_scope from the Membership, OR
            #   - use the Membership's own business if that business is a branch
            branch = None
            if m.branch_scope_id:
                branch = m.branch_scope
            elif m.business.parent_id is not None:
                branch = m.business

            # Generate a unique code within this HQ
            code = self._next_code(next_n, existing_codes)
            existing_codes.add(code)
            next_n += 1

            # role_type: only core operational roles are in ROLE_MAP;
            # staff is only reached here if --include-staff is set
            role_type          = ROLE_MAP.get(m.role, EmployeeProfile.RoleType.CASHIER)
            emp_status         = STATUS_MAP.get(m.status, EmployeeProfile.Status.ACTIVE)
            is_staff_migration = (m.role in STAFF_ROLES)

            first_name = (m.user.first_name or '').strip() or m.user.username[:60]
            last_name  = (m.user.last_name  or '').strip()
            alias      = m.user.get_full_name().strip() or m.user.username[:60]

            # ── Provenance (exact structure stored in permission_overrides) ─────
            # _migrated_from        : always 'membership'
            # _legacy_membership_id : original Membership PK (int)
            # _legacy_role          : original role value string
            # _legacy_business_id   : original Membership.business_id (may be branch)
            # _needs_role_review    : true ONLY for staff migrations
            #                        (flag for POST-7 in validate_phase3 --stage=post)
            permission_overrides = {
                '_migrated_from':        'membership',
                '_legacy_membership_id': m.id,
                '_legacy_role':          m.role,
                '_legacy_business_id':   m.business_id,
            }
            if is_staff_migration:
                permission_overrides['_needs_role_review'] = True

            label = "REVIEW" if is_staff_migration else "CREATE"
            self.stdout.write(
                f"  {label}  {first_name} {last_name} "
                f"(role_type={role_type}, code={code}) "
                f"← Membership {m.id} (role={m.role})"
                + (" [NEEDS ROLE REVIEW]" if is_staff_migration else "")
            )

            if dry_run:
                summary['employees_created'] += 1
                if is_staff_migration:
                    summary['employees_review_flag'] += 1
                continue

            try:
                with transaction.atomic():
                    EmployeeProfile.objects.create(
                        business=business,
                        branch=branch,
                        linked_user=m.user,
                        first_name=first_name,
                        last_name=last_name,
                        alias=alias,
                        employee_code=code,
                        role_type=role_type,
                        credential_type=EmployeeProfile.CredentialType.PIN,
                        # Unusable hash — employee must set a PIN on first POS login
                        login_code_hash=make_password(None),
                        must_change_pin=True,
                        permission_overrides=permission_overrides,
                        status=emp_status,
                    )
                summary['employees_created'] += 1
                if is_staff_migration:
                    summary['employees_review_flag'] += 1
            except IntegrityError as exc:
                summary['errors'] += 1
                self.stdout.write(self.style.ERROR(
                    f"  ERROR  Membership {m.id}: {exc}"
                ))

    # -------------------------------------------------------------------------

    def _next_code_start(self, existing_codes: set[str]) -> int:
        """Return the integer suffix to start generating from."""
        max_n = 0
        for code in existing_codes:
            m = re.match(r'^EMP-(\d+)$', code)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return max_n + 1

    def _next_code(self, start: int, existing_codes: set[str]) -> str:
        """Return first EMP-NNNN code not already in existing_codes."""
        n = start
        while True:
            code = f"EMP-{n:04d}"
            if code not in existing_codes:
                return code
            n += 1

    # -------------------------------------------------------------------------

    def _print_summary(self, summary, dry_run, include_staff):
        mode = "[DRY-RUN] " if dry_run else ""
        sep  = "=" * 60
        self.stdout.write(f"\n{sep}")
        self.stdout.write(f"  {mode}backfill_employees  SUMMARY")
        self.stdout.write(sep)
        self.stdout.write(f"  Businesses processed            : {summary['businesses']}")
        self.stdout.write(f"  EmployeeProfiles created        : {summary['employees_created']}")
        if summary['employees_review_flag']:
            self.stdout.write(self.style.WARNING(
                f"  Created with NEEDS_ROLE_REVIEW   : {summary['employees_review_flag']} "
                f"(staff migrants — query: permission_overrides @> '{{\"_needs_role_review\":true}}')"
            ))
        self.stdout.write(f"  Already linked (skipped)        : {summary['already_linked']}")
        self.stdout.write(f"  Skipped (no user / orphan)      : {summary['skipped_no_user']}")
        if not include_staff and summary['staff_skipped_review']:
            self.stdout.write(self.style.WARNING(
                f"  Staff skipped (needs review)     : {summary['staff_skipped_review']} "
                f"— re-run with --include-staff once roles are confirmed."
            ))
        if summary['analyst_deprecated']:
            self.stdout.write(self.style.WARNING(
                f"  Analyst memberships (deprecated) : {summary['analyst_deprecated']} "
                f"— same permissions as viewer; recommend manual remap."
            ))
        if summary['errors']:
            self.stdout.write(self.style.ERROR(
                f"  Errors                          : {summary['errors']}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS("  No errors."))
        self.stdout.write(sep)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN complete. Re-run without --dry-run to apply.\n"
            ))
