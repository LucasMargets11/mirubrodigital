"""
Phase 3 — backfill_memberships
==============================
Normalizes Membership rows toward the Phase 2A schema:

  1. Sets `status = active` on any Membership that has a blank/empty status
     (rows created before Phase 2A added the status field).
  2. Clears `branch_scope` from OWNER memberships — owners must always have
     full-tree access (enforced by service layer going forward).
  3. Reports businesses that have no active OWNER as a WARNING; does NOT
     attempt to auto-assign an owner (that requires human decision).

IDEMPOTENT: safe to run multiple times.  Each run only touches rows that
still require a change.

Usage:
    python manage.py backfill_memberships [--dry-run] [--business-id N]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.models import Membership
from apps.business.models import Business

# Roles that stay in Membership (administrative)
ADMIN_ROLES = {'owner', 'admin', 'manager', 'viewer', 'analyst'}

# Roles that should be migrated to EmployeeProfile (operational)
OPERATIONAL_ROLES = {'cashier', 'kitchen', 'salon'}
# 'staff' is handled by backfill_employees --include-staff; it is NOT auto-migrated
# 'analyst' is deprecated — same rbac.py permissions as 'viewer'; stays in Membership


class Command(BaseCommand):
    help = (
        "Phase 3 — Normalise Membership status + branch_scope fields. "
        "Reports businesses with no active OWNER. Does not delete anything."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate changes without writing to the database.',
        )
        parser.add_argument(
            '--business-id',
            type=int,
            default=None,
            help='Restrict to a single HQ business (by integer PK).',
        )

    # -------------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run     = options['dry_run']
        business_id = options.get('business_id')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN mode — no changes will be written.\n"
            ))

        qs = Business.objects.filter(parent__isnull=True)
        if business_id:
            qs = qs.filter(id=business_id)

        total = qs.count()
        self.stdout.write(f"Processing {total} HQ business(es)...\n")

        summary = {
            'status_set':           0,
            'owner_scope_cleared':  0,
            'no_owner_warnings':    0,
            'analyst_deprecated':   0,
            'businesses_processed': 0,
        }

        for business in qs.iterator():
            self._process_business(business, dry_run, summary)
            summary['businesses_processed'] += 1

        self._print_summary(summary, dry_run)

    # -------------------------------------------------------------------------

    def _process_business(self, business, dry_run, summary):
        self.stdout.write(f"\n── Business #{business.id}: {business.name} ──")

        memberships = (
            Membership.objects
            .filter(business=business)
            .select_related('user', 'branch_scope')
        )

        changed_anything = False

        for m in memberships:
            field_updates = {}

            # ── Rule 1: normalise status ───────────────────────────────────
            # Any row whose status is not an explicit inactive/suspended should
            # be considered active.  This covers:
            #   - Rows where the column was added with a default but somehow
            #     ended up blank (shouldn't happen in practice, belt-and-suspender).
            #   - Legacy rows created before the Phase 2A migration ran.
            valid_statuses = {
                Membership.Status.ACTIVE,
                Membership.Status.INACTIVE,
                Membership.Status.SUSPENDED,
            }
            if m.status not in valid_statuses:
                field_updates['status'] = Membership.Status.ACTIVE
                self.stdout.write(
                    f"  Membership {m.id} ({m.user} / {m.role}): "
                    f"status '{m.status}' → active"
                )
                summary['status_set'] += 1

            # ── Rule 2: OWNER must have NULL branch_scope ──────────────────
            if m.role == 'owner' and m.branch_scope_id is not None:
                field_updates['branch_scope_id'] = None
                self.stdout.write(self.style.WARNING(
                    f"  Membership {m.id} (OWNER {m.user}): "
                    f"branch_scope set → clearing (owners have full-tree access)"
                ))
                summary['owner_scope_cleared'] += 1

            if field_updates and not dry_run:
                for field, value in field_updates.items():
                    setattr(m, field, value)
                m.save(update_fields=list(field_updates.keys()))

            if field_updates:
                changed_anything = True

        if not changed_anything:
            self.stdout.write("  No changes needed.")
        # ── Deprecation warning: 'analyst' role is identical to 'viewer' in rbac.py ──
        # These memberships remain in place — the warning is informational only.
        analyst_memberships = memberships.filter(role='analyst').select_related('user')
        for am in analyst_memberships:
            self.stdout.write(self.style.WARNING(
                f"  DEPRECATED_ROLE  Membership {am.id} ({am.user}): "
                f"role='analyst' has identical permissions to 'viewer' in rbac.py. "
                f"Recommend manually remapping this membership to role='viewer'."
            ))
            summary['analyst_deprecated'] += 1
        # ── Validation: ≥1 active OWNER required ──────────────────────────
        active_owners = memberships.filter(
            role='owner', status=Membership.Status.ACTIVE
        ).count()

        if active_owners == 0:
            summary['no_owner_warnings'] += 1
            self.stdout.write(self.style.ERROR(
                f"  WARNING: Business #{business.id} has NO active OWNER membership!"
            ))
        else:
            self.stdout.write(
                f"  Active OWNER(s): {active_owners}"
            )

    # -------------------------------------------------------------------------

    def _print_summary(self, summary, dry_run):
        mode = "[DRY-RUN] " if dry_run else ""
        sep  = "=" * 60
        self.stdout.write(f"\n{sep}")
        self.stdout.write(f"  {mode}backfill_memberships  SUMMARY")
        self.stdout.write(sep)
        self.stdout.write(f"  Businesses processed : {summary['businesses_processed']}")
        self.stdout.write(f"  Status fields set    : {summary['status_set']}")
        self.stdout.write(f"  OWNER scopes cleared : {summary['owner_scope_cleared']}")
        if summary['analyst_deprecated']:
            self.stdout.write(self.style.WARNING(
                f"  Analyst memberships  : {summary['analyst_deprecated']} "
                f"— role deprecated (= viewer); recommend manual remap."
            ))
        if summary['no_owner_warnings']:
            self.stdout.write(self.style.ERROR(
                f"  Businesses w/o OWNER : {summary['no_owner_warnings']}  <-- ACTION REQUIRED"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "  All businesses have >= 1 active OWNER."
            ))
        self.stdout.write(sep)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN complete. Re-run without --dry-run to apply.\n"
            ))
