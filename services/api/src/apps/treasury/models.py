from django.db import models
from django.conf import settings
from apps.business.models import Business
from django.utils import timezone
from datetime import date
import uuid

class Account(models.Model):
    class Type(models.TextChoices):
        CASH = 'cash', 'Caja'
        BANK = 'bank', 'Banco'
        MERCADOPAGO = 'mercadopago', 'MercadoPago'
        CARD_FLOAT = 'card_float', 'Tarjeta (Flotante)'
        OTHER = 'other', 'Otro'

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='treasury_accounts')
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.CASH)
    currency = models.CharField(max_length=10, default='ARS')
    opening_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    opening_balance_date = models.DateField(default=date.today)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

class TransactionCategory(models.Model):
    class Direction(models.TextChoices):
        INCOME = 'income', 'Ingreso'
        EXPENSE = 'expense', 'Egreso'

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='treasury_categories')
    direction = models.CharField(max_length=10, choices=Direction.choices)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_direction_display()})"

class Transaction(models.Model):
    class Direction(models.TextChoices):
        IN = 'IN', 'Ingreso'
        OUT = 'OUT', 'Egreso'
        ADJUST = 'ADJUST', 'Ajuste'
    
    class Status(models.TextChoices):
        POSTED = 'posted', 'Confirmado'
        VOIDED = 'voided', 'Anulado'

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='treasury_transactions')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    direction = models.CharField(max_length=10, choices=Direction.choices)
    # Amount is always positive
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    occurred_at = models.DateTimeField()
    category = models.ForeignKey(TransactionCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    
    # Polymorphic-like reference but loose coupling
    reference_type = models.CharField(max_length=50, null=True, blank=True) # e.g., 'sale', 'expense', 'payroll'
    reference_id = models.CharField(max_length=100, null=True, blank=True) # UUID or Int as string
    
    transfer_group_id = models.UUIDField(null=True, blank=True)
    attachment = models.FileField(upload_to='treasury/attachments/%Y/%m/', null=True, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.direction} {self.amount} - {self.description}"

class FixedExpense(models.Model):
    """Representa un gasto fijo recurrente (ej: Internet, Alquiler, Luz)"""
    class Frequency(models.TextChoices):
        WEEKLY = 'weekly', 'Semanal'
        MONTHLY = 'monthly', 'Mensual'
        QUARTERLY = 'quarterly', 'Trimestral'
        YEARLY = 'yearly', 'Anual'

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='fixed_expenses')
    name = models.CharField(max_length=255, help_text="Nombre del gasto fijo (ej: Internet, Alquiler)")
    category = models.ForeignKey('TransactionCategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='fixed_expenses', help_text="Categoría para agrupación")
    default_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True, help_text="Monto por defecto opcional")
    due_day = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Día del mes de vencimiento (1-28)")
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['business', 'name']]
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.business.name})"

class FixedExpensePeriod(models.Model):
    """Representa un periodo mensual de un gasto fijo (instancia pagada o pendiente)"""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        PAID = 'paid', 'Pagado'
        SKIPPED = 'skipped', 'Omitido'

    fixed_expense = models.ForeignKey(FixedExpense, on_delete=models.CASCADE, related_name='periods')
    period = models.DateField(help_text="Primer día del mes (YYYY-MM-01)")
    amount = models.DecimalField(max_digits=19, decimal_places=4, help_text="Monto para este periodo")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    due_date = models.DateField(null=True, blank=True)
    
    # Campos de pago
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='paid_fixed_expense_periods')
    payment_transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='fixed_expense_period_payments')
    
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['fixed_expense', 'period']]
        ordering = ['-period']

    def __str__(self):
        return f"{self.fixed_expense.name} - {self.period.strftime('%Y-%m')}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate due_date if not set
        if not self.due_date and self.fixed_expense.due_day:
            from calendar import monthrange
            year = self.period.year
            month = self.period.month
            day = min(self.fixed_expense.due_day, monthrange(year, month)[1])
            self.due_date = date(year, month, day)
        super().save(*args, **kwargs)

class ExpenseTemplate(models.Model):
    """DEPRECATED: Usar FixedExpense en su lugar. Mantenido por compatibilidad."""
    class Frequency(models.TextChoices):
        MONTHLY = 'monthly', 'Mensual'

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='expense_templates')
    name = models.CharField(max_length=255)
    category = models.ForeignKey(TransactionCategory, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    due_day = models.PositiveSmallIntegerField(help_text="Day of the month (1-28)")
    start_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Expense(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        PAID = 'paid', 'Pagado'
        CANCELLED = 'cancelled', 'Cancelado'

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='expenses')
    template = models.ForeignKey(ExpenseTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    name = models.CharField(max_length=255)
    category = models.ForeignKey(TransactionCategory, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    paid_at = models.DateTimeField(null=True, blank=True)
    paid_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='paid_expenses')
    payment_transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_payments')

    attachment = models.FileField(upload_to='treasury/expenses/%Y/%m/', null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    # Polymorphic source reference — used for auto-generated expenses (e.g. stock replenishments).
    # UNIQUE(business, source_type, source_id) prevents duplicates.
    source_type = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="Tipo de origen del gasto automático (ej: 'stock_replenishment')",
    )
    source_id = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="ID del registro de origen (UUID o entero como string)",
    )
    # Flag to distinguish auto-generated expenses from manually created ones
    is_auto_generated = models.BooleanField(
        default=False,
        help_text="True cuando fue creado automáticamente por el sistema (ej. reposición de stock)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'source_type', 'source_id'],
                condition=models.Q(source_type__isnull=False),
                name='expense_unique_auto_source',
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.amount}"

class Employee(models.Model):
    class PayFrequency(models.TextChoices):
        MONTHLY = 'monthly', 'Mensual'
        WEEKLY = 'weekly', 'Semanal'

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='employees')
    full_name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=50, null=True, blank=True, help_text="DNI/CUIT")
    pay_frequency = models.CharField(max_length=20, choices=PayFrequency.choices, default=PayFrequency.MONTHLY)
    base_salary = models.DecimalField(max_digits=19, decimal_places=4)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.full_name

class PayrollPayment(models.Model):
    STATUS_PAID = 'paid'
    STATUS_REVERTED = 'reverted'
    STATUS_CHOICES = [
        (STATUS_PAID, 'Paid'),
        (STATUS_REVERTED, 'Reverted'),
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='payroll_payments')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    paid_at = models.DateTimeField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_payments')
    notes = models.TextField(null=True, blank=True)
    attachment = models.FileField(upload_to='treasury/payroll/%Y/%m/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PAID)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment to {self.employee.full_name} - {self.amount}"

class TreasurySettings(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='treasury_settings')
    # Payment method → account mapping
    default_cash_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    default_bank_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    default_mercadopago_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    default_card_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', help_text="Cuenta destino para pagos con tarjeta")
    default_other_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', help_text="Cuenta destino para otros medios de pago")
    # Functional defaults
    default_income_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', help_text="Cuenta por defecto para ingresos manuales")
    default_expense_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', help_text="Cuenta por defecto para egresos manuales")
    default_payroll_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', help_text="Cuenta por defecto para sueldos")

    def get_account_for_payment_method(self, payment_method: str):
        """Return the configured account for a given payment method string."""
        mapping = {
            'cash': self.default_cash_account,
            'transfer': self.default_bank_account,
            'mercadopago': self.default_mercadopago_account,
            'card': self.default_card_account,
            'other': self.default_other_account,
        }
        return mapping.get(payment_method)

    def __str__(self):
        return f"Treasury Settings for {self.business.name}"


class Budget(models.Model):
    """Presupuesto mensual por categoría para alertas de gasto."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='treasury_budgets')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField(help_text="Mes (1-12)")
    category = models.ForeignKey(TransactionCategory, on_delete=models.CASCADE, related_name='budgets')
    limit_amount = models.DecimalField(max_digits=19, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['business', 'year', 'month', 'category']]
        ordering = ['-year', '-month']

    def __str__(self):
        return f"Budget {self.category.name} {self.year}-{self.month:02d}: {self.limit_amount}"
