"""
Phase 3 — backfill_terminals
=============================
Creates a Terminal record for every existing CashRegister that doesn't already
have one (checked via the Terminal.cash_register OneToOneField).

Strategy
--------
- Terminal.business is always the HQ of the CashRegister's business.
- Terminal.branch is set when the CashRegister belongs to a branch (not the HQ).
- Terminal.code  is derived as  CR-{first-8-chars-of-register-uuid}.
- Terminal.name  copies the CashRegister name.
- terminal_type  defaults to CASHIER  (CashRegisters are cash terminals by nature).
- is_active      mirrors CashRegister.is_active.

The original CashRegister row is NOT deleted (retained for backward compat).
The Terminal.cash_register FK preserves the link for Phase 2C consolidation.

IDEMPOTENT: if a Terminal already points to a CashRegister we skip it.

Usage:
    python manage.py backfill_terminals [--dry-run] [--business-id N]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from apps.business.models import Business
from apps.cash.models import CashRegister, Terminal


class Command(BaseCommand):
    help = (
        "Phase 3 — Create Terminal records from existing CashRegister rows. "
        "Legacy CashRegister rows are NOT deleted."
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

        summary = {
            'businesses':      0,
            'terminals_created': 0,
            'already_exists':  0,
            'errors':          0,
        }

        for business in qs.iterator():
            self._process_business(business, dry_run, summary)
            summary['businesses'] += 1

        self._print_summary(summary, dry_run)

    # -------------------------------------------------------------------------

    def _process_business(self, business, dry_run, summary):
        self.stdout.write(f"\n── Business #{business.id}: {business.name} ──")

        family_ids = [business.id] + list(
            business.branches.values_list('id', flat=True)
        )

        registers = CashRegister.objects.filter(
            business_id__in=family_ids
        ).select_related('business')

        if not registers.exists():
            self.stdout.write("  No CashRegisters found.")
            return

        # Build set of codes already used by Terminals in this HQ to prevent conflicts
        existing_codes: set[str] = set(
            Terminal.objects.filter(business=business)
            .values_list('code', flat=True)
        )

        for reg in registers:
            # Idempotency guard: skip if a Terminal already owns this CashRegister
            if Terminal.objects.filter(cash_register=reg).exists():
                summary['already_exists'] += 1
                self.stdout.write(
                    f"  SKIP  CashRegister {reg.id} ({reg.name}): Terminal already exists."
                )
                continue

            # Determine branch (NULL when CashRegister is at HQ level)
            branch = reg.business if reg.business.parent_id is not None else None

            code = self._unique_code(reg, existing_codes)
            existing_codes.add(code)

            self.stdout.write(
                f"  CREATE  Terminal '{reg.name}' (code={code}, "
                f"active={reg.is_active}) ← CashRegister {reg.id}"
            )

            if dry_run:
                summary['terminals_created'] += 1
                continue

            try:
                with transaction.atomic():
                    Terminal.objects.create(
                        business=business,
                        branch=branch,
                        cash_register=reg,
                        code=code,
                        name=reg.name,
                        terminal_type=Terminal.TerminalType.CASHIER,
                        shared_mode_enabled=False,
                        requires_operator_selection=False,
                        device_token='',
                        is_active=reg.is_active,
                        config=None,
                    )
                summary['terminals_created'] += 1
            except IntegrityError as exc:
                summary['errors'] += 1
                self.stdout.write(self.style.ERROR(
                    f"  ERROR  CashRegister {reg.id}: {exc}"
                ))

    # -------------------------------------------------------------------------

    def _unique_code(self, reg: CashRegister, existing_codes: set[str]) -> str:
        """
        Derive a unique terminal code from the register UUID.
        Format: CR-{first 8 hex chars of UUID}.  Appends -{n} if duplicate.
        """
        base = f"CR-{str(reg.id).replace('-', '')[:8].upper()}"
        code = base
        n    = 2
        while code in existing_codes:
            code = f"{base}-{n}"
            n   += 1
        return code

    # -------------------------------------------------------------------------

    def _print_summary(self, summary, dry_run):
        mode = "[DRY-RUN] " if dry_run else ""
        sep  = "=" * 56
        self.stdout.write(f"\n{sep}")
        self.stdout.write(f"  {mode}backfill_terminals  SUMMARY")
        self.stdout.write(sep)
        self.stdout.write(f"  Businesses processed  : {summary['businesses']}")
        self.stdout.write(f"  Terminals created     : {summary['terminals_created']}")
        self.stdout.write(f"  Already exists (skip) : {summary['already_exists']}")
        if summary['errors']:
            self.stdout.write(self.style.ERROR(
                f"  Errors                : {summary['errors']}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS("  No errors."))
        self.stdout.write(sep)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN complete. Re-run without --dry-run to apply.\n"
            ))
