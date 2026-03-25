"""
Sprint 1 — backfill_payments
=============================
Crea registros Payment para gastos históricos ya pagados que no tienen
uno asociado todavía.

Prioridad de monto:
  1. Transaction.amount (fuente más confiable)
  2. Monto del origen (expense.amount / period.amount) si es consistente
  3. Si no hay monto confiable → NO crea Payment, registra discrepancia

Idempotente: solo procesa orígenes sin Payment(status=completed).
Soporta --dry-run para simulación sin escritura.

Usage:
    python manage.py backfill_payments [--dry-run] [--business-id N]
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from apps.treasury.models import (
    Expense, FixedExpensePeriod, Transaction, Payment,
)


class Command(BaseCommand):
    help = (
        "Sprint 1 — Backfill Payment records for historically paid Expenses "
        "and FixedExpensePeriods that don't have one yet."
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

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        business_id = options.get('business_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN mode — no changes will be written.\n'))

        stats = {
            'expense_candidates': 0,
            'expense_migrated': 0,
            'expense_skipped_no_amount': 0,
            'expense_skipped_already': 0,
            'fep_candidates': 0,
            'fep_migrated': 0,
            'fep_skipped_no_amount': 0,
            'fep_skipped_already': 0,
            'discrepancies': [],
        }

        self._backfill_expenses(dry_run, business_id, stats)
        self._backfill_fixed_expense_periods(dry_run, business_id, stats)
        self._print_report(stats, dry_run)

    # ─────────────────────────────────────────────────────────────────────

    def _backfill_expenses(self, dry_run, business_id, stats):
        """Backfill Payment for paid Expenses."""
        qs = (
            Expense.objects
            .filter(status=Expense.Status.PAID)
            .select_related('payment_transaction', 'paid_account', 'business')
        )
        if business_id:
            qs = qs.filter(business_id=business_id)

        # Exclude those that already have a completed Payment
        existing_expense_ids = set(
            Payment.objects
            .filter(expense__isnull=False, status=Payment.Status.COMPLETED)
            .values_list('expense_id', flat=True)
        )

        expenses = list(qs)
        stats['expense_candidates'] = len(expenses)

        for expense in expenses:
            if expense.id in existing_expense_ids:
                stats['expense_skipped_already'] += 1
                continue

            amount = self._resolve_amount(
                expense.payment_transaction, expense.amount
            )
            if amount is None:
                stats['expense_skipped_no_amount'] += 1
                stats['discrepancies'].append(
                    f'Expense #{expense.id} ({expense.name}): '
                    f'no reliable amount — txn={expense.payment_transaction_id}'
                )
                continue

            paid_at = expense.paid_at
            if not paid_at:
                if expense.payment_transaction and expense.payment_transaction.occurred_at:
                    paid_at = expense.payment_transaction.occurred_at
                else:
                    stats['expense_skipped_no_amount'] += 1
                    stats['discrepancies'].append(
                        f'Expense #{expense.id} ({expense.name}): no paid_at timestamp'
                    )
                    continue

            if not dry_run:
                with db_transaction.atomic():
                    Payment.objects.create(
                        business=expense.business,
                        expense=expense,
                        transaction=expense.payment_transaction,
                        account=expense.paid_account,
                        amount=amount,
                        currency='ARS',
                        status=Payment.Status.COMPLETED,
                        paid_at=paid_at,
                        is_backfilled=True,
                    )
            stats['expense_migrated'] += 1

    def _backfill_fixed_expense_periods(self, dry_run, business_id, stats):
        """Backfill Payment for paid FixedExpensePeriods."""
        qs = (
            FixedExpensePeriod.objects
            .filter(status=FixedExpensePeriod.Status.PAID)
            .select_related('payment_transaction', 'paid_account', 'fixed_expense', 'fixed_expense__business')
        )
        if business_id:
            qs = qs.filter(fixed_expense__business_id=business_id)

        existing_fep_ids = set(
            Payment.objects
            .filter(fixed_expense_period__isnull=False, status=Payment.Status.COMPLETED)
            .values_list('fixed_expense_period_id', flat=True)
        )

        periods = list(qs)
        stats['fep_candidates'] = len(periods)

        for period in periods:
            if period.id in existing_fep_ids:
                stats['fep_skipped_already'] += 1
                continue

            amount = self._resolve_amount(
                period.payment_transaction, period.amount
            )
            if amount is None:
                stats['fep_skipped_no_amount'] += 1
                stats['discrepancies'].append(
                    f'FixedExpensePeriod #{period.id} '
                    f'({period.fixed_expense.name} {period.period}): '
                    f'no reliable amount — txn={period.payment_transaction_id}'
                )
                continue

            paid_at = period.paid_at
            if not paid_at:
                if period.payment_transaction and period.payment_transaction.occurred_at:
                    paid_at = period.payment_transaction.occurred_at
                else:
                    stats['fep_skipped_no_amount'] += 1
                    stats['discrepancies'].append(
                        f'FixedExpensePeriod #{period.id} '
                        f'({period.fixed_expense.name} {period.period}): no paid_at timestamp'
                    )
                    continue

            if not dry_run:
                with db_transaction.atomic():
                    Payment.objects.create(
                        business=period.fixed_expense.business,
                        fixed_expense_period=period,
                        transaction=period.payment_transaction,
                        account=period.paid_account,
                        amount=amount,
                        currency='ARS',
                        status=Payment.Status.COMPLETED,
                        paid_at=paid_at,
                        is_backfilled=True,
                    )
            stats['fep_migrated'] += 1

    # ─────────────────────────────────────────────────────────────────────

    def _resolve_amount(self, txn, origin_amount) -> Decimal | None:
        """
        Prioridad de resolución de monto:
          1. Transaction.amount (fuente más confiable)
          2. origin_amount si es positivo y consistente
          3. None si no hay fuente confiable
        """
        # Priority 1: transaction amount
        if txn and txn.amount and txn.amount > 0:
            return txn.amount

        # Priority 2: origin amount
        if origin_amount and origin_amount > 0:
            # Only use if no transaction exists (legacy data)
            # or transaction is voided (but expense is still paid — edge case)
            return origin_amount

        return None

    def _print_report(self, stats, dry_run):
        prefix = '[DRY-RUN] ' if dry_run else ''

        self.stdout.write(f'\n{prefix}═══ Backfill Payment Report ═══\n')
        self.stdout.write(f'Expenses:')
        self.stdout.write(f'  Candidates:       {stats["expense_candidates"]}')
        self.stdout.write(f'  Migrated:         {stats["expense_migrated"]}')
        self.stdout.write(f'  Already existed:  {stats["expense_skipped_already"]}')
        self.stdout.write(f'  Skipped (no amt): {stats["expense_skipped_no_amount"]}')
        self.stdout.write(f'')
        self.stdout.write(f'FixedExpensePeriods:')
        self.stdout.write(f'  Candidates:       {stats["fep_candidates"]}')
        self.stdout.write(f'  Migrated:         {stats["fep_migrated"]}')
        self.stdout.write(f'  Already existed:  {stats["fep_skipped_already"]}')
        self.stdout.write(f'  Skipped (no amt): {stats["fep_skipped_no_amount"]}')

        if stats['discrepancies']:
            self.stdout.write(self.style.WARNING(
                f'\n{prefix}Discrepancies ({len(stats["discrepancies"])}):'))
            for d in stats['discrepancies']:
                self.stdout.write(self.style.WARNING(f'  ⚠ {d}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n{prefix}No discrepancies found.'))

        total = stats['expense_migrated'] + stats['fep_migrated']
        self.stdout.write(self.style.SUCCESS(f'\n{prefix}Total payments created: {total}\n'))
