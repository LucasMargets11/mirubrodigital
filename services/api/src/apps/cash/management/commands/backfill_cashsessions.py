"""
Phase 3 — backfill_cashsessions
================================
Populates the Phase 2A nullable columns on existing CashSession rows:

  terminal              ←  looked up via Terminal.cash_register == session.register
  branch                ←  copied from Terminal.branch (when not already set)
  opened_by_employee    ←  EmployeeProfile whose linked_user == session.opened_by
  closed_by_employee    ←  EmployeeProfile whose linked_user == session.closed_by

Prerequisites
-------------
Run AFTER backfill_terminals and backfill_employees, because:
  - Terminal rows must exist before we can set session.terminal.
  - EmployeeProfile rows must exist before we can resolve employee FKs.

Legacy fields preserved (not touched)
--------------------------------------
  session.register    (still points to legacy CashRegister)
  session.opened_by   (still points to auth.User)
  session.closed_by   (still points to auth.User)

IDEMPOTENT: only processes sessions where terminal IS NULL.
A second run will find no remaining sessions (terminal already set) and do nothing.

Usage:
    python manage.py backfill_cashsessions [--dry-run] [--business-id N]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.models import EmployeeProfile
from apps.cash.models import CashSession, Terminal


class Command(BaseCommand):
    help = (
        "Phase 3 — Populate CashSession.terminal / branch / *_employee FKs "
        "from legacy register / opened_by / closed_by fields. "
        "Run after backfill_terminals and backfill_employees."
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
            help='Restrict to a single business (integer PK, HQ or branch).',
        )

    # -------------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run     = options['dry_run']
        business_id = options.get('business_id')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN mode — no changes will be written.\n"
            ))

        # Only sessions that still need the terminal FK populated
        qs = (
            CashSession.objects
            .filter(terminal__isnull=True)
            .select_related('register', 'opened_by', 'closed_by', 'business')
        )
        if business_id:
            qs = qs.filter(business_id=business_id)

        total = qs.count()
        self.stdout.write(f"CashSessions without terminal FK : {total}\n")

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                "Nothing to do — all sessions already have terminal set.\n"
            ))
            return

        # Pre-build employee lookup map: (hq_business_id, user_id) → EmployeeProfile
        employee_map = self._build_employee_map(business_id)

        summary = {
            'terminal_set':            0,
            'branch_set':              0,
            'opened_by_employee_set':  0,
            'closed_by_employee_set':  0,
            'no_register':             0,
            'no_terminal_for_register': 0,
        }

        for session in qs.iterator():
            self._process_session(session, dry_run, summary, employee_map)

        self._print_summary(summary, dry_run)

    # -------------------------------------------------------------------------

    def _build_employee_map(self, business_id):
        """
        Pre-fetch all EmployeeProfiles that have a linked_user and build a
        (hq_business_id, user_id) → EmployeeProfile lookup dict.

        EmployeeProfile.business is always the HQ, so an employee from a
        branch session is still found via the HQ id.
        """
        ep_qs = (
            EmployeeProfile.objects
            .filter(linked_user__isnull=False)
            .only('id', 'business_id', 'linked_user_id')
        )
        if business_id:
            # Accept HQ id or branch id: for a branch we'd need the HQ, but
            # filtering by business_id is a reasonable scope limiter here.
            ep_qs = ep_qs.filter(business_id=business_id)

        mapping: dict[tuple, EmployeeProfile] = {}
        for ep in ep_qs:
            mapping[(ep.business_id, ep.linked_user_id)] = ep
        return mapping

    # -------------------------------------------------------------------------

    def _process_session(self, session, dry_run, summary, employee_map):
        # ── Step 1: resolve Terminal from legacy register ──────────────────
        if session.register_id is None:
            summary['no_register'] += 1
            self.stdout.write(
                f"  SKIP  Session {session.id}: no register FK (legacy manual session?)."
            )
            return

        try:
            terminal = Terminal.objects.get(cash_register_id=session.register_id)
        except Terminal.DoesNotExist:
            summary['no_terminal_for_register'] += 1
            self.stdout.write(self.style.WARNING(
                f"  WARN  Session {session.id}: CashRegister {session.register_id} "
                f"has no Terminal yet (run backfill_terminals first)."
            ))
            return

        update_fields: list[str] = []

        session.terminal = terminal
        update_fields.append('terminal')
        summary['terminal_set'] += 1

        # ── Step 2: set branch if terminal has one and session doesn't ─────
        if terminal.branch_id is not None and session.branch_id is None:
            session.branch_id = terminal.branch_id
            update_fields.append('branch')
            summary['branch_set'] += 1

        # ── Step 3: resolve opened_by_employee ────────────────────────────
        if session.opened_by_id and session.opened_by_employee_id is None:
            hq_id = session.business.parent_id or session.business_id
            ep    = employee_map.get((hq_id, session.opened_by_id))
            if ep:
                session.opened_by_employee = ep
                update_fields.append('opened_by_employee')
                summary['opened_by_employee_set'] += 1

        # ── Step 4: resolve closed_by_employee ────────────────────────────
        if session.closed_by_id and session.closed_by_employee_id is None:
            hq_id = session.business.parent_id or session.business_id
            ep    = employee_map.get((hq_id, session.closed_by_id))
            if ep:
                session.closed_by_employee = ep
                update_fields.append('closed_by_employee')
                summary['closed_by_employee_set'] += 1

        if update_fields and not dry_run:
            session.save(update_fields=update_fields)

    # -------------------------------------------------------------------------

    def _print_summary(self, summary, dry_run):
        mode = "[DRY-RUN] " if dry_run else ""
        sep  = "=" * 56
        self.stdout.write(f"\n{sep}")
        self.stdout.write(f"  {mode}backfill_cashsessions  SUMMARY")
        self.stdout.write(sep)
        self.stdout.write(f"  terminal FK set            : {summary['terminal_set']}")
        self.stdout.write(f"  branch FK set              : {summary['branch_set']}")
        self.stdout.write(f"  opened_by_employee set     : {summary['opened_by_employee_set']}")
        self.stdout.write(f"  closed_by_employee set     : {summary['closed_by_employee_set']}")
        self.stdout.write(f"  Sessions w/o register      : {summary['no_register']}")
        self.stdout.write(f"  Registers w/o Terminal     : {summary['no_terminal_for_register']}")
        self.stdout.write(sep)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN complete. Re-run without --dry-run to apply.\n"
            ))
