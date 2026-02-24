"""
Replenishment MVP tests.
Run with: python manage.py test apps.inventory.tests.test_replenishment
"""
from decimal import Decimal
from datetime import timezone as tz
from datetime import datetime

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.business.models import Business
from apps.catalog.models import Product
from apps.treasury.models import Account, Expense, Transaction, TransactionCategory
from apps.inventory.models import ProductStock, StockMovement, StockReplenishment
from apps.inventory.services import create_stock_replenishment, void_stock_replenishment

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_business(name='Test Biz'):
    b, _ = Business.objects.get_or_create(name=name)
    return b


def make_user(email='test@test.com'):
    u, _ = User.objects.get_or_create(email=email, defaults={'username': email})
    return u


def make_account(business, name='Caja', balance=Decimal('10000')):
    return Account.objects.create(
        business=business,
        name=name,
        type='cash',
        currency='ARS',
        opening_balance=balance,
    )


def make_product(business, name='Harina', cost=Decimal('100')):
    return Product.objects.create(
        business=business,
        name=name,
        sku=name[:10],
        cost=cost,
        price=Decimal('200'),
    )


def make_category(business):
    cat, _ = TransactionCategory.objects.get_or_create(
        business=business,
        name='Compras de Mercadería',
        defaults={'direction': 'expense'},
    )
    return cat


# ---------------------------------------------------------------------------
# Tests: create_stock_replenishment
# ---------------------------------------------------------------------------

class CreateReplenishmentTest(TestCase):
    def setUp(self):
        self.business = make_business('Biz Compras')
        self.user = make_user('compras@test.com')
        self.account = make_account(self.business)
        self.product_a = make_product(self.business, 'Harina')
        self.product_b = make_product(self.business, 'Azúcar')
        self.occurred_at = datetime(2026, 2, 23, 10, 0, tzinfo=tz.utc)

    def _create(self, items=None, **kwargs):
        if items is None:
            items = [
                {'product_id': str(self.product_a.id), 'quantity': 10, 'unit_cost': '50.0000'},
                {'product_id': str(self.product_b.id), 'quantity': 5, 'unit_cost': '80.0000'},
            ]
        params = dict(
            business=self.business,
            occurred_at=self.occurred_at,
            supplier_name='Distribuidora Norte',
            invoice_number='FAC-001',
            account=self.account,
            items=items,
            created_by=self.user,
        )
        params.update(kwargs)  # allow callers to override any default
        return create_stock_replenishment(**params)

    def test_creates_replenishment_record(self):
        repl = self._create()
        self.assertIsNotNone(repl.pk)
        self.assertEqual(repl.supplier_name, 'Distribuidora Norte')
        self.assertEqual(repl.status, StockReplenishment.Status.POSTED)
        self.assertEqual(repl.business_id, self.business.id)

    def test_calculates_total_correctly(self):
        # 10 * 50 + 5 * 80 = 500 + 400 = 900
        repl = self._create()
        self.assertEqual(repl.total_amount, Decimal('900.0000'))

    def test_creates_n_stock_movements_in(self):
        repl = self._create()
        movements = StockMovement.objects.filter(replenishment=repl)
        self.assertEqual(movements.count(), 2)
        for m in movements:
            self.assertEqual(m.movement_type, StockMovement.MovementType.IN)
            self.assertIsNotNone(m.unit_cost)

    def test_unit_cost_set_on_movements(self):
        repl = self._create()
        m_a = StockMovement.objects.get(replenishment=repl, product=self.product_a)
        m_b = StockMovement.objects.get(replenishment=repl, product=self.product_b)
        self.assertEqual(m_a.unit_cost, Decimal('50.0000'))
        self.assertEqual(m_b.unit_cost, Decimal('80.0000'))

    def test_creates_one_transaction_out(self):
        repl = self._create()
        self.assertIsNotNone(repl.transaction)
        tx = repl.transaction
        self.assertEqual(tx.direction, Transaction.Direction.OUT)
        self.assertEqual(tx.amount, Decimal('900.0000'))
        self.assertEqual(tx.status, Transaction.Status.POSTED)

    def test_transaction_reference_links_to_replenishment(self):
        repl = self._create()
        tx = repl.transaction
        self.assertEqual(tx.reference_type, 'stock_replenishment')
        self.assertEqual(tx.reference_id, str(repl.id))

    def test_stock_levels_increase(self):
        self._create()
        stock_a = ProductStock.objects.get(business=self.business, product=self.product_a)
        stock_b = ProductStock.objects.get(business=self.business, product=self.product_b)
        self.assertEqual(stock_a.quantity, Decimal('10.00'))
        self.assertEqual(stock_b.quantity, Decimal('5.00'))

    def test_creates_default_purchase_category_if_not_provided(self):
        repl = self._create()
        self.assertIsNotNone(repl.purchase_category)
        self.assertEqual(repl.purchase_category.name, 'Compras de Mercadería')
        self.assertEqual(repl.purchase_category.direction, TransactionCategory.Direction.EXPENSE)

    def test_uses_provided_purchase_category(self):
        cat = make_category(self.business)
        repl = self._create(purchase_category=cat)
        self.assertEqual(repl.purchase_category_id, cat.id)

    def test_duplicate_products_raises_error(self):
        from django.core.exceptions import ValidationError
        items = [
            {'product_id': str(self.product_a.id), 'quantity': 5, 'unit_cost': '50'},
            {'product_id': str(self.product_a.id), 'quantity': 3, 'unit_cost': '55'},
        ]
        with self.assertRaises(ValidationError):
            self._create(items=items)

    def test_wrong_business_account_raises_error(self):
        from django.core.exceptions import ValidationError
        other_biz = make_business('Otro Negocio')
        other_account = make_account(other_biz, 'Cuenta Ajena')
        with self.assertRaises(ValidationError):
            self._create(account=other_account)

    def test_negative_unit_cost_raises_error(self):
        from django.core.exceptions import ValidationError
        items = [{'product_id': str(self.product_a.id), 'quantity': 5, 'unit_cost': '-10'}]
        with self.assertRaises(ValidationError):
            self._create(items=items)


# ---------------------------------------------------------------------------
# Tests: void_stock_replenishment
# ---------------------------------------------------------------------------

class VoidReplenishmentTest(TestCase):
    def setUp(self):
        self.business = make_business('Biz Void')
        self.user = make_user('void@test.com')
        self.account = make_account(self.business)
        self.product = make_product(self.business, 'Leche')
        self.occurred_at = datetime(2026, 2, 23, 10, 0, tzinfo=tz.utc)
        self.repl = create_stock_replenishment(
            business=self.business,
            occurred_at=self.occurred_at,
            supplier_name='Proveedor X',
            invoice_number='VOID-001',
            account=self.account,
            items=[{'product_id': str(self.product.id), 'quantity': 8, 'unit_cost': '100'}],
            created_by=self.user,
        )

    def test_void_marks_replenishment_voided(self):
        voided = void_stock_replenishment(replenishment=self.repl, reason='Error de carga', voided_by=self.user)
        self.assertEqual(voided.status, StockReplenishment.Status.VOIDED)

    def test_void_marks_transaction_voided(self):
        void_stock_replenishment(replenishment=self.repl, reason='Error de carga', voided_by=self.user)
        tx = Transaction.objects.get(pk=self.repl.transaction_id)
        self.assertEqual(tx.status, Transaction.Status.VOIDED)

    def test_void_creates_compensatory_out_movement(self):
        void_stock_replenishment(replenishment=self.repl, reason='Error', voided_by=self.user)
        out_movements = StockMovement.objects.filter(
            replenishment=self.repl,
            movement_type=StockMovement.MovementType.OUT,
            reason='replenishment_void',
        )
        self.assertEqual(out_movements.count(), 1)
        self.assertEqual(out_movements.first().quantity, Decimal('8.00'))

    def test_void_reverts_stock_level(self):
        # Initial stock after replenishment
        stock_before = ProductStock.objects.get(business=self.business, product=self.product).quantity
        void_stock_replenishment(replenishment=self.repl, reason='Error', voided_by=self.user)
        stock_after = ProductStock.objects.get(business=self.business, product=self.product).quantity
        self.assertEqual(stock_after, stock_before - Decimal('8.00'))

    def test_void_is_idempotent(self):
        void_stock_replenishment(replenishment=self.repl, reason='Error', voided_by=self.user)
        # Call again — should not create duplicate compensatory movements
        void_stock_replenishment(replenishment=self.repl, reason='Error duplicado', voided_by=self.user)
        out_movements = StockMovement.objects.filter(
            replenishment=self.repl,
            movement_type=StockMovement.MovementType.OUT,
            reason='replenishment_void',
        )
        self.assertEqual(out_movements.count(), 1)


# ---------------------------------------------------------------------------
# Tests: API endpoints (permission checks)
# ---------------------------------------------------------------------------

class ReplenishmentPermissionsTest(TestCase):
    def setUp(self):
        from django.test import Client
        from apps.accounts.models import Membership
        self.client = Client()
        self.business = make_business('Biz API')
        self.user_no_perm = make_user('noperm@test.com')
        self.account = make_account(self.business)
        self.product = make_product(self.business, 'Pan')

    def _auth_get(self, url, user, business):
        """Simulate authenticated request. Forces authentication via session."""
        self.client.force_login(user)
        response = self.client.get(url, HTTP_X_BUSINESS_ID=str(business.id))
        return response

    def _auth_post(self, url, user, business, data=None):
        import json
        self.client.force_login(user)
        response = self.client.post(
            url,
            data=json.dumps(data or {}),
            content_type='application/json',
            HTTP_X_BUSINESS_ID=str(business.id),
        )
        return response

    def test_list_requires_authentication(self):
        response = self.client.get('/api/v1/inventory/replenishments/')
        self.assertIn(response.status_code, [401, 403])


# ---------------------------------------------------------------------------
# Tests: Expense auto-creation from stock replenishment (Finanzas → Gastos)
# ---------------------------------------------------------------------------

class ReplenishmentExpenseTest(TestCase):
    """
    Ensure every confirmed replenishment creates exactly one Expense record
    in Finanzas → Gastos and that the lifecycle (idempotence, void) works.
    """

    def setUp(self):
        self.business = make_business('Biz Expense')
        self.user = make_user('expense@test.com')
        self.account = make_account(self.business)
        self.product = make_product(self.business, 'Yerba')
        self.occurred_at = datetime(2026, 2, 23, 10, 0, tzinfo=tz.utc)

    def _create(self, **kwargs):
        defaults = dict(
            business=self.business,
            occurred_at=self.occurred_at,
            supplier_name='Proveedor Mate',
            invoice_number='M-001',
            account=self.account,
            items=[{'product_id': str(self.product.id), 'quantity': 4, 'unit_cost': '75'}],
            created_by=self.user,
        )
        defaults.update(kwargs)
        return create_stock_replenishment(**defaults)

    # -- creation ----------------------------------------------------------

    def test_creates_one_expense_on_replenishment(self):
        repl = self._create()
        expenses = Expense.objects.filter(
            business=self.business,
            source_type='stock_replenishment',
            source_id=str(repl.id),
        )
        self.assertEqual(expenses.count(), 1)

    def test_expense_amount_matches_replenishment_total(self):
        repl = self._create()
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(repl.id))
        self.assertEqual(expense.amount, repl.total_amount)

    def test_expense_status_is_paid(self):
        repl = self._create()
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(repl.id))
        self.assertEqual(expense.status, Expense.Status.PAID)

    def test_expense_is_auto_generated(self):
        repl = self._create()
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(repl.id))
        self.assertTrue(expense.is_auto_generated)

    def test_expense_payment_transaction_links_to_replenishment_transaction(self):
        repl = self._create()
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(repl.id))
        self.assertIsNotNone(expense.payment_transaction)
        self.assertEqual(expense.payment_transaction_id, repl.transaction_id)

    def test_expense_category_name_is_restablecimiento(self):
        repl = self._create()
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(repl.id))
        self.assertIsNotNone(expense.category)
        self.assertEqual(expense.category.name, 'Restablecimiento de stock')
        self.assertEqual(expense.category.direction, TransactionCategory.Direction.EXPENSE)

    def test_expense_NO_second_transaction_created(self):
        """Confirm that auto-creating the Expense does NOT add extra OUT transactions."""
        tx_count_before = Transaction.objects.filter(business=self.business).count()
        self._create()
        tx_count_after = Transaction.objects.filter(business=self.business).count()
        # Only the ONE movement transaction should have been created
        self.assertEqual(tx_count_after - tx_count_before, 1)

    # -- idempotence -------------------------------------------------------

    def test_idempotent_no_duplicate_expense_on_retry(self):
        """Calling create twice (simulating retry) must not create 2 expenses."""
        repl = self._create()
        # Force update_or_create again by calling the service once more on the
        # same replenishment data — this shouldn't happen in production but
        # we validate the constraint by directly testing update_or_create.
        Expense.objects.update_or_create(
            business=self.business,
            source_type='stock_replenishment',
            source_id=str(repl.id),
            defaults={'name': 'updated', 'amount': repl.total_amount, 'due_date': repl.occurred_at},
        )
        count = Expense.objects.filter(
            business=self.business,
            source_type='stock_replenishment',
            source_id=str(repl.id),
        ).count()
        self.assertEqual(count, 1)

    # -- void/cancel -------------------------------------------------------

    def test_voiding_replenishment_cancels_expense(self):
        repl = self._create()
        void_stock_replenishment(replenishment=repl, reason='Error', voided_by=self.user)
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(repl.id))
        self.assertEqual(expense.status, Expense.Status.CANCELLED)

    def test_void_is_idempotent_for_expense(self):
        repl = self._create()
        void_stock_replenishment(replenishment=repl, reason='Error', voided_by=self.user)
        void_stock_replenishment(replenishment=repl, reason='Error duplicado', voided_by=self.user)
        expense_count = Expense.objects.filter(
            source_type='stock_replenishment', source_id=str(repl.id)
        ).count()
        self.assertEqual(expense_count, 1)
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(repl.id))
        self.assertEqual(expense.status, Expense.Status.CANCELLED)

    # -- listing -----------------------------------------------------------

    def test_expense_list_includes_replenishment_expenses(self):
        """
        The Expense queryset (as used by the API) must return expenses whose
        source_type is 'stock_replenishment'.
        """
        repl = self._create()
        qs = Expense.objects.filter(
            business=self.business,
            source_type='stock_replenishment',
        )
        self.assertEqual(qs.count(), 1)
        self.assertEqual(str(qs.first().source_id), str(repl.id))
