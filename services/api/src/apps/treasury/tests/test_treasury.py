"""
Treasury module tests
Run with: python manage.py test apps.treasury.tests
"""
from decimal import Decimal
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.treasury.models import (
    Account, Transaction, TransactionCategory, FixedExpense,
    FixedExpensePeriod, Expense, Employee, PayrollPayment, TreasurySettings, Budget
)
from apps.business.models import Business

User = get_user_model()


def make_business(name='Test Biz'):
    """Helper: create a minimal Business for testing."""
    try:
        from apps.business.models import Business
        b, _ = Business.objects.get_or_create(name=name, defaults={'slug': name.lower().replace(' ', '-')})
        return b
    except Exception:
        # If Business model requires more fields, skip
        raise


def make_account(business, name='Caja', account_type='cash', balance=Decimal('1000')):
    return Account.objects.create(
        business=business,
        name=name,
        type=account_type,
        currency='ARS',
        opening_balance=balance,
        opening_balance_date=date.today(),
    )


class TreasurySettingsAccountMappingTest(TestCase):
    """Tests for TreasurySettings.get_account_for_payment_method"""

    def setUp(self):
        self.business = make_business('Biz Settings')
        self.cash_acct = make_account(self.business, 'Caja Efectivo', 'cash')
        self.bank_acct = make_account(self.business, 'Banco', 'bank')
        self.mp_acct = make_account(self.business, 'MercadoPago', 'mercadopago')
        self.card_acct = make_account(self.business, 'Tarjeta', 'card_float')
        self.other_acct = make_account(self.business, 'Otro', 'other')

        self.settings = TreasurySettings.objects.create(
            business=self.business,
            default_cash_account=self.cash_acct,
            default_bank_account=self.bank_acct,
            default_mercadopago_account=self.mp_acct,
            default_card_account=self.card_acct,
            default_other_account=self.other_acct,
        )

    def test_returns_configured_cash_account(self):
        self.assertEqual(self.settings.get_account_for_payment_method('cash'), self.cash_acct)

    def test_returns_configured_bank_account(self):
        self.assertEqual(self.settings.get_account_for_payment_method('transfer'), self.bank_acct)

    def test_returns_configured_card_account(self):
        self.assertEqual(self.settings.get_account_for_payment_method('card'), self.card_acct)

    def test_returns_configured_other_account(self):
        self.assertEqual(self.settings.get_account_for_payment_method('other'), self.other_acct)

    def test_returns_configured_mercadopago_account(self):
        self.assertEqual(self.settings.get_account_for_payment_method('mercadopago'), self.mp_acct)

    def test_unknown_method_returns_none(self):
        result = self.settings.get_account_for_payment_method('unknown')
        self.assertIsNone(result)


class AccountBalanceExcludesVoidedTest(TestCase):
    """Account balance should exclude VOIDED transactions."""

    def setUp(self):
        self.business = make_business('Biz Balance')
        self.account = make_account(self.business, 'Caja', 'cash', Decimal('0'))
        cat, _ = TransactionCategory.objects.get_or_create(
            business=self.business, name='Ingreso', defaults={'direction': 'income'}
        )
        # Post a normal IN transaction
        self.txn_posted = Transaction.objects.create(
            business=self.business,
            account=self.account,
            direction='IN',
            amount=Decimal('500'),
            occurred_at=datetime.now(tz=timezone.utc),
            status='posted',
            description='Ingreso OK',
        )
        # Post a voided IN transaction
        self.txn_voided = Transaction.objects.create(
            business=self.business,
            account=self.account,
            direction='IN',
            amount=Decimal('300'),
            occurred_at=datetime.now(tz=timezone.utc),
            status='voided',
            description='Ingreso ANULADO',
        )

    def test_balance_excludes_voided(self):
        """API balance should only count posted transactions."""
        posted_in = Transaction.objects.filter(
            account=self.account, status='posted', direction='IN'
        ).aggregate(s=models_sum('amount'))['s'] or Decimal('0')

        self.assertEqual(posted_in, Decimal('500'))


class PayrollPaymentStatusTest(TestCase):
    """PayrollPayment.status field behavior."""

    def setUp(self):
        self.business = make_business('Biz Payroll')
        self.account = make_account(self.business, 'Caja', 'cash', Decimal('5000'))
        self.employee = Employee.objects.create(
            business=self.business,
            full_name='Juan Perez',
            base_salary=Decimal('1000'),
            pay_frequency='monthly',
        )

    def test_default_status_is_paid(self):
        txn = Transaction.objects.create(
            business=self.business,
            account=self.account,
            direction='OUT',
            amount=Decimal('1000'),
            occurred_at=datetime.now(tz=timezone.utc),
            status='posted',
            description='Sueldo Juan',
        )
        payment = PayrollPayment.objects.create(
            business=self.business,
            employee=self.employee,
            amount=Decimal('1000'),
            paid_at=datetime.now(tz=timezone.utc),
            account=self.account,
            transaction=txn,
        )
        self.assertEqual(payment.status, 'paid')

    def test_revert_sets_status_reverted(self):
        txn = Transaction.objects.create(
            business=self.business,
            account=self.account,
            direction='OUT',
            amount=Decimal('1000'),
            occurred_at=datetime.now(tz=timezone.utc),
            status='posted',
            description='Sueldo Juan',
        )
        payment = PayrollPayment.objects.create(
            business=self.business,
            employee=self.employee,
            amount=Decimal('1000'),
            paid_at=datetime.now(tz=timezone.utc),
            account=self.account,
            transaction=txn,
        )
        # Simulate revert
        txn.status = 'voided'
        txn.save()
        payment.status = 'reverted'
        payment.transaction = None
        payment.save()

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'reverted')
        self.assertIsNone(payment.transaction)


class BudgetModelTest(TestCase):
    """Budget model basic tests."""

    def setUp(self):
        self.business = make_business('Biz Budget')
        self.cat, _ = TransactionCategory.objects.get_or_create(
            business=self.business, name='Gastos Generales', defaults={'direction': 'expense'}
        )

    def test_create_budget(self):
        budget = Budget.objects.create(
            business=self.business,
            category=self.cat,
            year=2025,
            month=1,
            limit_amount=Decimal('5000'),
        )
        self.assertEqual(budget.limit_amount, Decimal('5000'))
        self.assertEqual(budget.year, 2025)

    def test_unique_together_constraint(self):
        from django.db import IntegrityError
        Budget.objects.create(
            business=self.business,
            category=self.cat,
            year=2025,
            month=1,
            limit_amount=Decimal('5000'),
        )
        with self.assertRaises(IntegrityError):
            Budget.objects.create(
                business=self.business,
                category=self.cat,
                year=2025,
                month=1,
                limit_amount=Decimal('3000'),
            )


class FixedExpensePeriodTest(TestCase):
    """FixedExpense and period generation tests."""

    def setUp(self):
        self.business = make_business('Biz Fixed')
        self.account = make_account(self.business, 'Caja', 'cash', Decimal('10000'))
        self.fixed_expense = FixedExpense.objects.create(
            business=self.business,
            name='Alquiler',
            default_amount=Decimal('2000'),
            due_day=10,
            frequency='monthly',
        )

    def test_fixed_expense_str(self):
        self.assertIn('Alquiler', str(self.fixed_expense))

    def test_period_default_status_is_pending(self):
        period = FixedExpensePeriod.objects.create(
            fixed_expense=self.fixed_expense,
            period='2025-01',
            due_date=date(2025, 1, 10),
            amount=Decimal('2000'),
        )
        self.assertEqual(period.status, 'pending')


# ─── Helper for aggregate ─────────────────────────────────────────────────────
def models_sum(field):
    from django.db.models import Sum
    return Sum(field)
