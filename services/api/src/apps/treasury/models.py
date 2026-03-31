from django.db import models
from django.conf import settings
from apps.business.models import Business
from django.utils import timezone
from datetime import date
import os
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
    """DEPRECATED: Usar FixedExpense en su lugar. Modelo congelado — no usar en código nuevo."""
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

    class Meta:
        managed = False  # Sprint 1: frozen — table stays for legacy reads
        db_table = 'treasury_expensetemplate'

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


# ─────────────────────────────────────────────────────────────────────────────
# Payment — entidad de pago desacoplada (Sprint 1)
# ─────────────────────────────────────────────────────────────────────────────

class Payment(models.Model):
    """
    Representa un pago ejecutado sobre un origen pagable (Expense o FixedExpensePeriod).

    Sprint 1: cada origen solo puede tener un Payment con status=completed.
    La relación con Transaction es 1-a-1.
    """

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completado'
        VOIDED = 'voided', 'Anulado'

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='treasury_payments',
    )

    # ── Origen pagable (exactamente uno seteado) ──────────────────────────
    expense = models.ForeignKey(
        'Expense', on_delete=models.CASCADE, null=True, blank=True,
        related_name='payments',
        help_text='Gasto puntual pagado (mutuamente excluyente con fixed_expense_period)',
    )
    fixed_expense_period = models.ForeignKey(
        'FixedExpensePeriod', on_delete=models.CASCADE, null=True, blank=True,
        related_name='payments',
        help_text='Período de gasto fijo pagado (mutuamente excluyente con expense)',
    )

    # ── Datos del pago ────────────────────────────────────────────────────
    transaction = models.OneToOneField(
        Transaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payment',
        help_text='Transacción financiera asociada al pago',
    )
    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments',
        help_text='Cuenta desde la que se realizó el pago',
    )
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=10, default='ARS')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED,
    )
    paid_at = models.DateTimeField()

    # ── Metadata ──────────────────────────────────────────────────────────
    is_backfilled = models.BooleanField(
        default=False,
        help_text='True si fue generado por el backfill de migración',
    )
    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['business', 'status'], name='payment_biz_status_idx'),
            models.Index(fields=['business', 'paid_at'], name='payment_biz_paid_idx'),
        ]
        constraints = [
            # Exactamente un origen seteado
            models.CheckConstraint(
                check=(
                    models.Q(expense__isnull=False, fixed_expense_period__isnull=True)
                    | models.Q(expense__isnull=True, fixed_expense_period__isnull=False)
                ),
                name='payment_exactly_one_source',
            ),
            # Solo un Payment completed por Expense
            models.UniqueConstraint(
                fields=['expense'],
                condition=models.Q(status='completed', expense__isnull=False),
                name='payment_one_completed_per_expense',
            ),
            # Solo un Payment completed por FixedExpensePeriod
            models.UniqueConstraint(
                fields=['fixed_expense_period'],
                condition=models.Q(status='completed', fixed_expense_period__isnull=False),
                name='payment_one_completed_per_fep',
            ),
        ]

    def __str__(self):
        origin = f'expense={self.expense_id}' if self.expense_id else f'fep={self.fixed_expense_period_id}'
        return f'Payment({origin}, {self.amount}, {self.status})'

    def void(self, reason: str | None = None):
        """Marca este pago como anulado."""
        self.status = self.Status.VOIDED
        if reason:
            self.notes = (self.notes or '') + f' [ANULADO: {reason}]'
        self.save(update_fields=['status', 'notes', 'updated_at'])


# ─────────────────────────────────────────────────────────────────────────────
# ExpenseDocument — capa documental común para gastos (Sprint 2)
# ─────────────────────────────────────────────────────────────────────────────

def expense_document_upload_path(instance, filename):
    """Generate upload path: treasury/documents/{business_id}/{YYYY}/{MM}/{uuid}_{safe_name}"""
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f'{uuid.uuid4().hex[:12]}{ext}'
    now = timezone.now()
    return f'treasury/documents/{instance.business_id}/{now:%Y}/{now:%m}/{safe_name}'


EXPENSE_DOCUMENT_ALLOWED_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/webp',
}

EXPENSE_DOCUMENT_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class ExpenseDocument(models.Model):
    """
    Documento/comprobante adjunto a un origen de gasto.

    Sprint 2: capa documental común — almacena archivos con metadata
    básica y estados mínimos. No incluye OCR, QR ni validación fiscal.
    """

    class Status(models.TextChoices):
        UPLOADED = 'uploaded', 'Subido'
        ARCHIVED = 'archived', 'Archivado'
        QUEUED = 'queued', 'En cola'
        PROCESSING = 'processing', 'Procesando'
        PROCESSED = 'processed', 'Procesado'
        PROCESSED_WITH_WARNINGS = 'processed_with_warnings', 'Procesado con advertencias'
        FAILED = 'failed', 'Fallido'

    class UploadSource(models.TextChoices):
        WEB = 'web', 'Web'
        MOBILE = 'mobile', 'Móvil'
        API = 'api', 'API'
        BULK = 'bulk', 'Carga masiva'

    class DocumentKind(models.TextChoices):
        INVOICE = 'invoice', 'Factura'
        RECEIPT = 'receipt', 'Recibo'
        TICKET = 'ticket', 'Ticket'
        CONTRACT = 'contract', 'Contrato'
        OTHER = 'other', 'Otro'

    class ExtractionSource(models.TextChoices):
        QR = 'qr', 'QR'
        OCR = 'ocr', 'OCR'
        MIXED = 'mixed', 'QR + OCR'
        NONE = 'none', 'Sin extracción'

    # ── Negocio ───────────────────────────────────────────────────────────
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='expense_documents',
    )

    # ── Origen (exactamente uno seteado, multiples FKs nullable) ──────────
    expense = models.ForeignKey(
        'Expense', on_delete=models.CASCADE, null=True, blank=True,
        related_name='documents',
    )
    fixed_expense_period = models.ForeignKey(
        'FixedExpensePeriod', on_delete=models.CASCADE, null=True, blank=True,
        related_name='documents',
    )

    # ── Archivo ───────────────────────────────────────────────────────────
    file = models.FileField(upload_to=expense_document_upload_path)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()

    # ── Metadata ──────────────────────────────────────────────────────────
    document_kind = models.CharField(
        max_length=20, choices=DocumentKind.choices, default=DocumentKind.OTHER,
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.UPLOADED,
    )
    notes = models.TextField(null=True, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='uploaded_expense_documents',
    )
    upload_source = models.CharField(
        max_length=20, choices=UploadSource.choices,
        default=UploadSource.WEB,
        help_text='Origen de la subida (web, mobile, api, bulk).',
    )

    # ── Procesamiento (Sprint 3) ──────────────────────────────────────────
    raw_extraction = models.JSONField(
        null=True, blank=True,
        help_text='Resultado crudo de la extracción (QR payload, OCR text, etc.)',
    )
    normalized_data = models.JSONField(
        null=True, blank=True,
        help_text='Datos normalizados: issuer_name, issuer_tax_id, total_amount, etc.',
    )
    processing_errors = models.JSONField(
        null=True, blank=True,
        help_text='Lista de errores/advertencias del pipeline de procesamiento.',
    )
    processed_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Timestamp de finalización del procesamiento.',
    )
    extraction_source = models.CharField(
        max_length=10, choices=ExtractionSource.choices,
        null=True, blank=True,
        help_text='Fuente de extracción usada (qr, ocr, mixed, none).',
    )
    pipeline_version = models.CharField(
        max_length=20, default='1.0',
        help_text='Versión del pipeline que procesó el documento.',
    )
    processing_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text='Cantidad de intentos de procesamiento realizados.',
    )
    error_trace = models.JSONField(
        null=True, blank=True,
        help_text='Traza estructurada de errores: [{step, error, timestamp}, ...]',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['business', 'status'], name='expdoc_biz_status_idx',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(expense__isnull=False, fixed_expense_period__isnull=True)
                    | models.Q(expense__isnull=True, fixed_expense_period__isnull=False)
                ),
                name='expdoc_exactly_one_origin',
            ),
        ]

    def __str__(self):
        origin = f'expense={self.expense_id}' if self.expense_id else f'fep={self.fixed_expense_period_id}'
        return f'ExpenseDocument({origin}, {self.original_filename})'

    @property
    def origin(self):
        """Return the linked origin object (Expense or FixedExpensePeriod)."""
        return self.expense or self.fixed_expense_period

    @property
    def origin_business_id(self):
        """Return the business_id of the linked origin for ownership validation."""
        if self.expense_id:
            return self.expense.business_id
        if self.fixed_expense_period_id:
            return self.fixed_expense_period.fixed_expense.business_id
        return None
