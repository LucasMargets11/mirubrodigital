"""
Sprint 1 — Payment model tests
================================
Covers:
  - Expense pay → creates Payment
  - FixedExpensePeriod pay → creates Payment
  - Double pay attempt → blocked by DB constraint
  - Transaction void → Payment voided + fiscal cascade
  - Backfill with valid and inconsistent data
  - DB constraints enforcement
"""
from decimal import Decimal
from datetime import date, datetime, timezone as tz
from io import StringIO
from unittest.mock import patch

from django.test import TestCase
from django.db import IntegrityError
from django.core.management import call_command

from apps.treasury.models import (
    Account, Transaction, TransactionCategory, Expense,
    FixedExpense, FixedExpensePeriod, Payment,
)
from apps.tax_backup.models import ExpenseFiscalProfile, TaxStatus, TaxStatusLog, SourceType
from apps.tax_backup.services import handle_payment_voided
from apps.business.models import Business


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def make_business(name='Test Biz'):
    b, _ = Business.objects.get_or_create(name=name, defaults={'slug': name.lower().replace(' ', '-')})
    return b


def make_account(business, name='Caja', balance=Decimal('10000')):
    return Account.objects.create(
        business=business, name=name, type='cash', currency='ARS',
        opening_balance=balance, opening_balance_date=date.today(),
    )


def make_category(business, name='Gastos'):
    cat, _ = TransactionCategory.objects.get_or_create(
        business=business, name=name, defaults={'direction': 'expense'},
    )
    return cat


def make_expense(business, name='Test Expense', amount=Decimal('500'), status='pending'):
    return Expense.objects.create(
        business=business, name=name, amount=amount,
        due_date=date.today(), status=status,
    )


def make_fixed_expense(business, name='Alquiler', amount=Decimal('2000')):
    return FixedExpense.objects.create(
        business=business, name=name, default_amount=amount,
        due_day=10, frequency='monthly',
    )


def make_period(fixed_expense, period_date=None, amount=None, status='pending'):
    if not period_date:
        period_date = date.today().replace(day=1)
    if amount is None:
        amount = fixed_expense.default_amount or Decimal('0')
    return FixedExpensePeriod.objects.create(
        fixed_expense=fixed_expense, period=period_date,
        amount=amount, status=status,
    )


def make_transaction(business, account, amount, direction='OUT', ref_type=None, ref_id=None):
    return Transaction.objects.create(
        business=business, account=account, direction=direction,
        amount=amount, occurred_at=datetime.now(tz=tz.utc),
        status='posted', description='Test',
        reference_type=ref_type, reference_id=ref_id,
    )


def pay_expense(business, expense, account):
    """Helper: simulate the pay flow matching views.py logic."""
    from django.utils import timezone as dj_tz
    now = dj_tz.now()
    txn = Transaction.objects.create(
        business=business, account=account, direction='OUT',
        amount=expense.amount, occurred_at=now, status='posted',
        description=f'Pago gasto: {expense.name}',
        reference_type='expense', reference_id=str(expense.id),
    )
    payment = Payment.objects.create(
        business=business, expense=expense, transaction=txn,
        account=account, amount=expense.amount, currency='ARS',
        status=Payment.Status.COMPLETED, paid_at=now,
    )
    expense.status = Expense.Status.PAID
    expense.paid_at = now
    expense.paid_account = account
    expense.payment_transaction = txn
    expense.save()
    return payment, txn


def pay_period(business, period, account, amount=None):
    """Helper: simulate the pay flow matching views.py logic."""
    from django.utils import timezone as dj_tz
    now = dj_tz.now()
    amt = amount or period.amount
    txn = Transaction.objects.create(
        business=business, account=account, direction='OUT',
        amount=amt, occurred_at=now, status='posted',
        description=f'Pago {period.fixed_expense.name}',
        reference_type='fixed_expense_period', reference_id=str(period.id),
    )
    payment = Payment.objects.create(
        business=business, fixed_expense_period=period, transaction=txn,
        account=account, amount=amt, currency='ARS',
        status=Payment.Status.COMPLETED, paid_at=now,
    )
    period.status = FixedExpensePeriod.Status.PAID
    period.paid_at = now
    period.paid_account = account
    period.payment_transaction = txn
    period.save()
    return payment, txn


# ═════════════════════════════════════════════════════════════════════════════
# Test cases
# ═════════════════════════════════════════════════════════════════════════════

class PaymentModelConstraintsTest(TestCase):
    """DB-level constraints on Payment model."""

    def setUp(self):
        self.biz = make_business('Biz Constraints')
        self.account = make_account(self.biz)
        self.expense = make_expense(self.biz)
        self.fe = make_fixed_expense(self.biz, name='Internet Constraints')
        self.period = make_period(self.fe)

    def test_payment_requires_exactly_one_source(self):
        """Payment must have either expense or fixed_expense_period, not both."""
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                business=self.biz,
                expense=self.expense,
                fixed_expense_period=self.period,
                amount=Decimal('100'),
                status=Payment.Status.COMPLETED,
                paid_at=datetime.now(tz=tz.utc),
            )

    def test_payment_requires_at_least_one_source(self):
        """Payment must have at least one source."""
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                business=self.biz,
                expense=None,
                fixed_expense_period=None,
                amount=Decimal('100'),
                status=Payment.Status.COMPLETED,
                paid_at=datetime.now(tz=tz.utc),
            )

    def test_only_one_completed_payment_per_expense(self):
        """DB prevents two completed Payments for the same Expense."""
        Payment.objects.create(
            business=self.biz, expense=self.expense,
            amount=Decimal('500'), status=Payment.Status.COMPLETED,
            paid_at=datetime.now(tz=tz.utc),
        )
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                business=self.biz, expense=self.expense,
                amount=Decimal('500'), status=Payment.Status.COMPLETED,
                paid_at=datetime.now(tz=tz.utc),
            )

    def test_only_one_completed_payment_per_fep(self):
        """DB prevents two completed Payments for the same FixedExpensePeriod."""
        Payment.objects.create(
            business=self.biz, fixed_expense_period=self.period,
            amount=Decimal('2000'), status=Payment.Status.COMPLETED,
            paid_at=datetime.now(tz=tz.utc),
        )
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                business=self.biz, fixed_expense_period=self.period,
                amount=Decimal('2000'), status=Payment.Status.COMPLETED,
                paid_at=datetime.now(tz=tz.utc),
            )

    def test_voided_payment_allows_new_completed(self):
        """After voiding a Payment, a new completed Payment should be allowed."""
        p1 = Payment.objects.create(
            business=self.biz, expense=self.expense,
            amount=Decimal('500'), status=Payment.Status.COMPLETED,
            paid_at=datetime.now(tz=tz.utc),
        )
        p1.void(reason='Error')
        # New completed should work
        p2 = Payment.objects.create(
            business=self.biz, expense=self.expense,
            amount=Decimal('500'), status=Payment.Status.COMPLETED,
            paid_at=datetime.now(tz=tz.utc),
        )
        self.assertEqual(p2.status, Payment.Status.COMPLETED)


class ExpensePaymentFlowTest(TestCase):
    """Expense.pay() → creates Payment correctly."""

    def setUp(self):
        self.biz = make_business('Biz Expense Pay')
        self.account = make_account(self.biz)
        self.expense = make_expense(self.biz, amount=Decimal('1500'))

    def test_pay_creates_payment(self):
        payment, txn = pay_expense(self.biz, self.expense, self.account)

        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertEqual(payment.amount, Decimal('1500'))
        self.assertEqual(payment.expense_id, self.expense.id)
        self.assertIsNone(payment.fixed_expense_period_id)
        self.assertEqual(payment.transaction_id, txn.id)
        self.assertEqual(payment.account_id, self.account.id)

    def test_pay_updates_legacy_fields(self):
        pay_expense(self.biz, self.expense, self.account)
        self.expense.refresh_from_db()

        self.assertEqual(self.expense.status, Expense.Status.PAID)
        self.assertIsNotNone(self.expense.paid_at)
        self.assertEqual(self.expense.paid_account_id, self.account.id)
        self.assertIsNotNone(self.expense.payment_transaction_id)

    def test_double_pay_blocked(self):
        """After paying, creating another completed Payment for same expense fails."""
        pay_expense(self.biz, self.expense, self.account)
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                business=self.biz, expense=self.expense,
                amount=Decimal('1500'), status=Payment.Status.COMPLETED,
                paid_at=datetime.now(tz=tz.utc),
            )


class FixedExpensePeriodPaymentFlowTest(TestCase):
    """FixedExpensePeriod.pay() → creates Payment correctly."""

    def setUp(self):
        self.biz = make_business('Biz FEP Pay')
        self.account = make_account(self.biz)
        self.fe = make_fixed_expense(self.biz, name='Luz', amount=Decimal('800'))
        self.period = make_period(self.fe)

    def test_pay_creates_payment(self):
        payment, txn = pay_period(self.biz, self.period, self.account)

        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertEqual(payment.amount, Decimal('800'))
        self.assertIsNone(payment.expense_id)
        self.assertEqual(payment.fixed_expense_period_id, self.period.id)
        self.assertEqual(payment.transaction_id, txn.id)

    def test_pay_updates_legacy_fields(self):
        pay_period(self.biz, self.period, self.account)
        self.period.refresh_from_db()

        self.assertEqual(self.period.status, FixedExpensePeriod.Status.PAID)
        self.assertIsNotNone(self.period.paid_at)
        self.assertEqual(self.period.paid_account_id, self.account.id)

    def test_double_pay_blocked(self):
        pay_period(self.biz, self.period, self.account)
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                business=self.biz, fixed_expense_period=self.period,
                amount=Decimal('800'), status=Payment.Status.COMPLETED,
                paid_at=datetime.now(tz=tz.utc),
            )


class TransactionVoidPaymentTest(TestCase):
    """Transaction void → Payment voided + fiscal cascade."""

    def setUp(self):
        self.biz = make_business('Biz Void')
        self.account = make_account(self.biz)
        self.expense = make_expense(self.biz, amount=Decimal('300'))

    def test_void_payment_changes_status(self):
        payment, txn = pay_expense(self.biz, self.expense, self.account)
        payment.void(reason='Error de monto')
        payment.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.VOIDED)
        self.assertIn('ANULADO', payment.notes)

    def test_void_allows_repayment(self):
        payment, _txn = pay_expense(self.biz, self.expense, self.account)
        payment.void(reason='Error')

        # Reset expense to pending
        self.expense.status = Expense.Status.PENDING
        self.expense.save()

        # Should be able to pay again
        payment2, _txn2 = pay_expense(self.biz, self.expense, self.account)
        self.assertEqual(payment2.status, Payment.Status.COMPLETED)


class FiscalCascadeTest(TestCase):
    """handle_payment_voided triggers fiscal cascade."""

    def setUp(self):
        self.biz = make_business('Biz Fiscal Cascade')
        self.account = make_account(self.biz)
        self.expense = make_expense(self.biz, amount=Decimal('1000'))

    def test_voiding_payment_sets_fiscal_profile_to_needs_review(self):
        payment, txn = pay_expense(self.biz, self.expense, self.account)

        # Create fiscal profile (normally done in view)
        profile = ExpenseFiscalProfile.objects.create(
            business=self.biz, expense=self.expense,
            source_type=SourceType.EXPENSE,
            tax_status=TaxStatus.REGISTERED,
        )

        handle_payment_voided(payment, txn, reason='Duplicado')

        profile.refresh_from_db()
        self.assertEqual(profile.tax_status, TaxStatus.NEEDS_REVIEW)
        self.assertIn('Pago anulado', profile.review_reason)

    def test_voiding_creates_tax_status_log(self):
        payment, txn = pay_expense(self.biz, self.expense, self.account)

        ExpenseFiscalProfile.objects.create(
            business=self.biz, expense=self.expense,
            source_type=SourceType.EXPENSE,
            tax_status=TaxStatus.BACKED,
        )

        handle_payment_voided(payment, txn, reason='Test')

        log = TaxStatusLog.objects.filter(
            fiscal_profile__expense=self.expense,
            rule_code='PAYMENT_VOIDED',
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.previous_status, TaxStatus.BACKED)
        self.assertEqual(log.new_status, TaxStatus.NEEDS_REVIEW)

    def test_voiding_without_profile_does_not_crash(self):
        """If no fiscal profile exists, handle_payment_voided should be a no-op."""
        payment, txn = pay_expense(self.biz, self.expense, self.account)
        # Should not raise
        handle_payment_voided(payment, txn, reason='No profile case')

    def test_fep_fiscal_cascade(self):
        """Fiscal cascade also works for FixedExpensePeriod payments."""
        fe = make_fixed_expense(self.biz, name='Internet Cascade')
        period = make_period(fe)
        payment, txn = pay_period(self.biz, period, self.account)

        profile = ExpenseFiscalProfile.objects.create(
            business=self.biz, fixed_expense_period=period,
            source_type=SourceType.FIXED_EXPENSE_PERIOD,
            tax_status=TaxStatus.REGISTERED,
        )

        handle_payment_voided(payment, txn, reason='Error')
        profile.refresh_from_db()
        self.assertEqual(profile.tax_status, TaxStatus.NEEDS_REVIEW)


class BackfillPaymentsTest(TestCase):
    """backfill_payments management command tests."""

    def setUp(self):
        self.biz = make_business('Biz Backfill')
        self.account = make_account(self.biz)

    def test_backfill_creates_payments_for_paid_expenses(self):
        """Paid expenses without Payment get one created."""
        expense = make_expense(self.biz, name='Legacy Paid', amount=Decimal('750'))
        txn = make_transaction(
            self.biz, self.account, Decimal('750'),
            ref_type='expense', ref_id=str(expense.id),
        )
        expense.status = Expense.Status.PAID
        expense.paid_at = datetime.now(tz=tz.utc)
        expense.paid_account = self.account
        expense.payment_transaction = txn
        expense.save()

        out = StringIO()
        call_command('backfill_payments', stdout=out)

        self.assertEqual(
            Payment.objects.filter(expense=expense, status=Payment.Status.COMPLETED).count(),
            1,
        )
        payment = Payment.objects.get(expense=expense)
        self.assertEqual(payment.amount, Decimal('750'))
        self.assertTrue(payment.is_backfilled)

    def test_backfill_creates_payments_for_paid_fep(self):
        """Paid FEP without Payment gets one created."""
        fe = make_fixed_expense(self.biz, name='Backfill Luz', amount=Decimal('600'))
        period = make_period(fe, status='paid')
        txn = make_transaction(
            self.biz, self.account, Decimal('600'),
            ref_type='fixed_expense_period', ref_id=str(period.id),
        )
        period.paid_at = datetime.now(tz=tz.utc)
        period.paid_account = self.account
        period.payment_transaction = txn
        period.save()

        out = StringIO()
        call_command('backfill_payments', stdout=out)

        self.assertEqual(
            Payment.objects.filter(fixed_expense_period=period, status=Payment.Status.COMPLETED).count(),
            1,
        )
        payment = Payment.objects.get(fixed_expense_period=period)
        self.assertEqual(payment.amount, Decimal('600'))
        self.assertTrue(payment.is_backfilled)

    def test_backfill_is_idempotent(self):
        """Running twice doesn't create duplicate Payments."""
        expense = make_expense(self.biz, name='Idem Expense', amount=Decimal('200'))
        txn = make_transaction(
            self.biz, self.account, Decimal('200'),
            ref_type='expense', ref_id=str(expense.id),
        )
        expense.status = Expense.Status.PAID
        expense.paid_at = datetime.now(tz=tz.utc)
        expense.payment_transaction = txn
        expense.save()

        call_command('backfill_payments', stdout=StringIO())
        call_command('backfill_payments', stdout=StringIO())

        self.assertEqual(
            Payment.objects.filter(expense=expense, status=Payment.Status.COMPLETED).count(),
            1,
        )

    def test_backfill_dry_run_creates_nothing(self):
        """Dry run reports but doesn't write."""
        expense = make_expense(self.biz, name='Dry Run', amount=Decimal('100'))
        txn = make_transaction(
            self.biz, self.account, Decimal('100'),
            ref_type='expense', ref_id=str(expense.id),
        )
        expense.status = Expense.Status.PAID
        expense.paid_at = datetime.now(tz=tz.utc)
        expense.payment_transaction = txn
        expense.save()

        out = StringIO()
        call_command('backfill_payments', '--dry-run', stdout=out)

        self.assertEqual(Payment.objects.filter(expense=expense).count(), 0)
        self.assertIn('DRY-RUN', out.getvalue())

    def test_backfill_skips_no_amount(self):
        """Paid expense without transaction and with 0 amount → discrepancy."""
        expense = make_expense(self.biz, name='No Amount', amount=Decimal('0'))
        expense.status = Expense.Status.PAID
        expense.paid_at = datetime.now(tz=tz.utc)
        expense.save()

        out = StringIO()
        call_command('backfill_payments', stdout=out)

        self.assertEqual(Payment.objects.filter(expense=expense).count(), 0)
        output = out.getvalue()
        self.assertIn('Discrepancies', output)

    def test_backfill_prefers_transaction_amount(self):
        """When txn.amount differs from expense.amount, txn wins."""
        expense = make_expense(self.biz, name='Amount Prio', amount=Decimal('500'))
        txn = make_transaction(
            self.biz, self.account, Decimal('480'),
            ref_type='expense', ref_id=str(expense.id),
        )
        expense.status = Expense.Status.PAID
        expense.paid_at = datetime.now(tz=tz.utc)
        expense.payment_transaction = txn
        expense.save()

        call_command('backfill_payments', stdout=StringIO())

        payment = Payment.objects.get(expense=expense)
        self.assertEqual(payment.amount, Decimal('480'))  # txn amount wins


class PaymentVoidMethodTest(TestCase):
    """Payment.void() method."""

    def setUp(self):
        self.biz = make_business('Biz Void Method')
        self.account = make_account(self.biz)

    def test_void_updates_status_and_notes(self):
        expense = make_expense(self.biz)
        payment, _ = pay_expense(self.biz, expense, self.account)

        payment.void(reason='Duplicado')
        payment.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.VOIDED)
        self.assertIn('ANULADO: Duplicado', payment.notes)

    def test_void_without_reason(self):
        expense = make_expense(self.biz)
        payment, _ = pay_expense(self.biz, expense, self.account)

        payment.void()
        payment.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.VOIDED)
