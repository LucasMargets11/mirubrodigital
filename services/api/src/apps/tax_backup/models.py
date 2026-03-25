from django.db import models
from django.conf import settings
from apps.business.models import Business
from apps.treasury.models import Expense, FixedExpense, FixedExpensePeriod


# ─────────────────────────────────────────────────────────────────────────────
# Enums (TextChoices)
# ─────────────────────────────────────────────────────────────────────────────

class TaxStatus(models.TextChoices):
    REGISTERED = 'registrado', 'Registrado'
    BACKED = 'respaldado', 'Respaldado'
    POTENTIALLY_DEDUCTIBLE = 'potencialmente_deducible', 'Potencialmente Deducible'
    NEEDS_REVIEW = 'a_revisar', 'A Revisar'
    NOT_BACKED = 'no_respaldado_fiscalmente', 'No Respaldado Fiscalmente'


class AllocationType(models.TextChoices):
    BUSINESS = 'business', 'Negocio'
    MIXED = 'mixed', 'Mixto'
    PERSONAL = 'personal', 'Personal'


class DocumentType(models.TextChoices):
    FACTURA = 'factura', 'Factura'
    RECIBO = 'recibo', 'Recibo'
    TICKET = 'ticket', 'Ticket'
    NOTA_CREDITO = 'nota_credito', 'Nota de Crédito'
    NOTA_DEBITO = 'nota_debito', 'Nota de Débito'
    OTRO = 'otro', 'Otro'


class ParseStatus(models.TextChoices):
    MANUAL = 'manual', 'Ingreso manual'
    PENDING = 'pending', 'Pendiente de extracción'
    PARSED = 'parsed', 'Datos extraídos'
    FAILED = 'failed', 'Extracción fallida'


class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Efectivo'
    TRANSFER = 'transfer', 'Transferencia'
    CARD = 'card', 'Tarjeta'
    MERCADOPAGO = 'mercadopago', 'MercadoPago'
    CHECK = 'check', 'Cheque'
    OTHER = 'other', 'Otro'


class AlertType(models.TextChoices):
    MISSING_INVOICE = 'missing_invoice', 'Comprobante faltante'
    INCOMPLETE_DATA = 'incomplete_data', 'Datos incompletos'


class AlertStatus(models.TextChoices):
    OPEN = 'open', 'Abierta'
    RESOLVED = 'resolved', 'Resuelta'
    DISMISSED = 'dismissed', 'Descartada'


class DuplicateMatchType(models.TextChoices):
    PROVIDER_INVOICE_DATE_AMOUNT = 'provider_invoice_date_amount', 'Proveedor + Factura + Fecha + Monto'
    EXACT_AMOUNT_DATE = 'exact_amount_date', 'Monto exacto + Fecha'


class DuplicateStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    CONFIRMED = 'confirmed_duplicate', 'Duplicado confirmado'
    DISMISSED = 'dismissed', 'Descartado'


# ─────────────────────────────────────────────────────────────────────────────
# Upload paths — include business PK for tenant isolation in storage
# ─────────────────────────────────────────────────────────────────────────────

def fiscal_document_upload_path(instance, filename):
    """tax_backup/docs/{business_id}/{YYYY}/{MM}/{filename}"""
    profile = instance.fiscal_profile
    biz_id = profile.business_id
    d = instance.created_at or __import__('django.utils.timezone', fromlist=['now']).now()
    return f'tax_backup/docs/{biz_id}/{d.year}/{d.month:02d}/{filename}'


def payment_proof_upload_path(instance, filename):
    """tax_backup/payments/{business_id}/{YYYY}/{MM}/{filename}"""
    profile = instance.fiscal_profile
    biz_id = profile.business_id
    d = instance.created_at or __import__('django.utils.timezone', fromlist=['now']).now()
    return f'tax_backup/payments/{biz_id}/{d.year}/{d.month:02d}/{filename}'


# ─────────────────────────────────────────────────────────────────────────────
# 1. ExpenseFiscalProfile — perfil fiscal de un Expense existente
# ─────────────────────────────────────────────────────────────────────────────

class SourceType(models.TextChoices):
    EXPENSE = 'expense', 'Gasto puntual'
    FIXED_EXPENSE_PERIOD = 'fixed_expense_period', 'Período de gasto fijo'


class ExpenseFiscalProfile(models.Model):
    """
    Enriquecimiento fiscal/documental de un gasto de Treasury.
    Soporta dos orígenes mutuamente excluyentes:
      - expense → treasury.Expense (gasto puntual)
      - fixed_expense_period → treasury.FixedExpensePeriod (período de gasto fijo)
    Se crea automáticamente al pagar o manualmente desde Respaldo Impositivo.
    """
    expense = models.OneToOneField(
        Expense,
        on_delete=models.CASCADE,
        related_name='fiscal_profile',
        null=True, blank=True,
        help_text='Gasto puntual de treasury (mutuamente excluyente con fixed_expense_period)',
    )
    fixed_expense_period = models.OneToOneField(
        FixedExpensePeriod,
        on_delete=models.CASCADE,
        related_name='fiscal_profile',
        null=True, blank=True,
        help_text='Período de gasto fijo de treasury (mutuamente excluyente con expense)',
    )
    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
        help_text='Tipo de origen del perfil fiscal',
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='expense_fiscal_profiles',
        help_text='Aislamiento multi-tenant',
    )

    # ── Clasificación fiscal ───────────────────────────────────────────────
    allocation_type = models.CharField(
        max_length=20,
        choices=AllocationType.choices,
        default=AllocationType.BUSINESS,
        help_text='Destino del gasto: negocio, mixto o personal',
    )
    tax_status = models.CharField(
        max_length=40,
        choices=TaxStatus.choices,
        default=TaxStatus.REGISTERED,
        db_index=True,
        help_text='Estado fiscal calculado automáticamente por el rule engine',
    )

    # ── Montos desagregados ────────────────────────────────────────────────
    amount_net = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        help_text='Monto neto sin IVA',
    )
    amount_vat = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        help_text='IVA',
    )

    # ── Flags especiales ───────────────────────────────────────────────────
    is_capital_asset = models.BooleanField(
        default=False,
        help_text='Bien de uso / activo fijo — requiere revisión de amortización',
    )
    review_reason = models.TextField(
        null=True, blank=True,
        help_text='Motivo de revisión (generado por reglas o manual)',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['business', 'tax_status'], name='tb_fp_biz_status_idx'),
            models.Index(fields=['business', 'allocation_type'], name='tb_fp_biz_alloc_idx'),
            models.Index(fields=['business', 'created_at'], name='tb_fp_biz_created_idx'),
            models.Index(fields=['business', 'source_type'], name='tb_fp_biz_source_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['expense'],
                condition=models.Q(expense__isnull=False),
                name='tb_one_fiscal_profile_per_expense',
            ),
            models.UniqueConstraint(
                fields=['fixed_expense_period'],
                condition=models.Q(fixed_expense_period__isnull=False),
                name='tb_one_fiscal_profile_per_fep',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(expense__isnull=False, fixed_expense_period__isnull=True)
                    | models.Q(expense__isnull=True, fixed_expense_period__isnull=False)
                ),
                name='tb_fp_exactly_one_source',
            ),
        ]

    def __str__(self):
        if self.expense_id:
            return f'FiscalProfile(expense={self.expense_id}) — {self.get_tax_status_display()}'
        return f'FiscalProfile(fep={self.fixed_expense_period_id}) — {self.get_tax_status_display()}'

    @property
    def source_name(self) -> str:
        """Nombre del gasto origen para display."""
        if self.expense_id:
            return self.expense.name if self.expense else ''
        if self.fixed_expense_period_id:
            fep = self.fixed_expense_period
            return f'{fep.fixed_expense.name} — {fep.period.strftime("%Y-%m")}' if fep else ''
        return ''

    @property
    def source_amount(self):
        """Monto del origen."""
        if self.expense_id and self.expense:
            return self.expense.amount
        if self.fixed_expense_period_id and self.fixed_expense_period:
            return self.fixed_expense_period.amount
        return None

    @property
    def source_due_date(self):
        """Fecha de vencimiento/período del origen."""
        if self.expense_id and self.expense:
            return self.expense.due_date
        if self.fixed_expense_period_id and self.fixed_expense_period:
            return self.fixed_expense_period.due_date or self.fixed_expense_period.period
        return None

    @property
    def source_period_label(self):
        """Label tipo '2026-03' para gastos fijos, None para puntuales."""
        if self.fixed_expense_period_id and self.fixed_expense_period:
            return self.fixed_expense_period.period.strftime('%Y-%m')
        return None

    @property
    def source_status(self):
        """Status del gasto/período origen."""
        if self.expense_id and self.expense:
            return self.expense.status
        if self.fixed_expense_period_id and self.fixed_expense_period:
            return self.fixed_expense_period.status
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. RecurringServiceProfile — perfil fiscal de un FixedExpense (servicio)
# ─────────────────────────────────────────────────────────────────────────────

class RecurringServiceProfile(models.Model):
    """
    Enriquecimiento fiscal de un servicio recurrente (FixedExpense).
    Agrega datos del proveedor y requisitos de documentación mensual.
    """
    fixed_expense = models.OneToOneField(
        FixedExpense,
        on_delete=models.CASCADE,
        related_name='service_profile',
        help_text='Gasto fijo / servicio recurrente asociado',
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='recurring_service_profiles',
    )

    # ── Datos del proveedor ────────────────────────────────────────────────
    provider_name = models.CharField(
        max_length=255,
        help_text='Razón social o nombre del proveedor',
    )
    provider_tax_id = models.CharField(
        max_length=50, null=True, blank=True,
        help_text='CUIT / RFC / RUT del proveedor',
    )

    # ── Requisitos documentales ────────────────────────────────────────────
    needs_monthly_invoice = models.BooleanField(
        default=False,
        help_text='¿Requiere comprobante fiscal por cada período?',
    )
    expected_document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.FACTURA,
        help_text='Tipo de comprobante esperado cada período',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['business'], name='tb_rsp_biz_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['fixed_expense'],
                name='tb_one_service_profile_per_fixed',
            ),
        ]

    def __str__(self):
        return f'ServiceProfile({self.fixed_expense_id}) — {self.provider_name}'


# ─────────────────────────────────────────────────────────────────────────────
# 3. FiscalDocument — comprobante fiscal adjunto a un perfil fiscal
# ─────────────────────────────────────────────────────────────────────────────

class FiscalDocument(models.Model):
    """
    Comprobante fiscal (factura, recibo, ticket, etc.) vinculado a un
    ExpenseFiscalProfile. Soporta múltiples documentos por gasto.
    """
    fiscal_profile = models.ForeignKey(
        ExpenseFiscalProfile,
        on_delete=models.CASCADE,
        related_name='documents',
    )

    # ── Archivo ────────────────────────────────────────────────────────────
    file = models.FileField(
        upload_to=fiscal_document_upload_path,
        help_text='Imagen o PDF del comprobante (max 10 MB)',
    )
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.FACTURA,
    )

    # ── Datos del emisor ───────────────────────────────────────────────────
    issuer_name = models.CharField(max_length=255, null=True, blank=True, help_text='Razón social del emisor')
    issuer_tax_id = models.CharField(max_length=50, null=True, blank=True, help_text='CUIT / RFC del emisor')

    # ── Datos del comprador ────────────────────────────────────────────────
    buyer_name = models.CharField(max_length=255, null=True, blank=True, help_text='Razón social del comprador')
    buyer_tax_id = models.CharField(max_length=50, null=True, blank=True, help_text='CUIT / RFC del comprador')

    # ── Datos del comprobante ──────────────────────────────────────────────
    point_of_sale = models.CharField(max_length=10, null=True, blank=True, help_text='Punto de venta (ej: 0001)')
    invoice_number = models.CharField(max_length=50, null=True, blank=True, help_text='Número de comprobante')
    issue_date = models.DateField(null=True, blank=True, help_text='Fecha de emisión')

    # ── Montos ─────────────────────────────────────────────────────────────
    currency = models.CharField(max_length=10, default='ARS')
    subtotal = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    vat = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    total = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)

    # ── Clasificación ──────────────────────────────────────────────────────
    is_fiscal_document = models.BooleanField(
        default=False,
        help_text='True si es un comprobante fiscal válido (factura tipo A/B/C, etc.)',
    )
    parse_status = models.CharField(
        max_length=20,
        choices=ParseStatus.choices,
        default=ParseStatus.MANUAL,
        help_text='Estado de extracción automática de datos (OCR futuro)',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=['fiscal_profile'],
                name='tb_doc_profile_idx',
            ),
            # Índice para detección de duplicados
            models.Index(
                fields=['issuer_tax_id', 'invoice_number', 'issue_date', 'total'],
                name='tb_doc_dup_detect_idx',
            ),
        ]

    def __str__(self):
        return f'{self.get_document_type_display()} #{self.invoice_number or "s/n"}'


# ─────────────────────────────────────────────────────────────────────────────
# 4. ExpensePaymentDetail — detalle de pago con respaldo
# ─────────────────────────────────────────────────────────────────────────────

class ExpensePaymentDetail(models.Model):
    """
    Registro del medio de pago utilizado para un gasto fiscal.
    Soporta múltiples pagos parciales por gasto (ej: seña + saldo).
    """
    fiscal_profile = models.ForeignKey(
        ExpenseFiscalProfile,
        on_delete=models.CASCADE,
        related_name='payment_details',
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
    )
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    reference = models.CharField(
        max_length=255, null=True, blank=True,
        help_text='Nro de transferencia, código de operación, etc.',
    )
    proof_file = models.FileField(
        upload_to=payment_proof_upload_path,
        null=True, blank=True,
        help_text='Comprobante de pago (transferencia, recibo, etc.)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['fiscal_profile'], name='tb_pay_profile_idx'),
        ]

    def __str__(self):
        return f'{self.get_payment_method_display()} — ${self.amount}'


# ─────────────────────────────────────────────────────────────────────────────
# 5. TaxStatusLog — trazabilidad de cambios de estado fiscal
# ─────────────────────────────────────────────────────────────────────────────

class TaxStatusLog(models.Model):
    """
    Cada cambio de tax_status en un ExpenseFiscalProfile genera un log.
    Permite auditar qué regla provocó el cambio.
    """
    fiscal_profile = models.ForeignKey(
        ExpenseFiscalProfile,
        on_delete=models.CASCADE,
        related_name='status_logs',
    )
    previous_status = models.CharField(
        max_length=40, choices=TaxStatus.choices, null=True, blank=True,
        help_text='Null para el primer estado asignado',
    )
    new_status = models.CharField(max_length=40, choices=TaxStatus.choices)
    rule_code = models.CharField(
        max_length=50,
        help_text='Código de la regla que disparó el cambio (ej: RULE_NO_FISCAL_DOC)',
    )
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['fiscal_profile', '-created_at'], name='tb_log_profile_date_idx'),
        ]

    def __str__(self):
        return f'{self.previous_status} → {self.new_status} ({self.rule_code})'


# ─────────────────────────────────────────────────────────────────────────────
# 6. ServicePeriodAlert — alerta de servicio sin comprobante
# ─────────────────────────────────────────────────────────────────────────────

class ServicePeriodAlert(models.Model):
    """
    Alerta generada cuando un servicio recurrente que requiere factura
    mensual no tiene comprobante asociado para un período determinado.
    """
    service_profile = models.ForeignKey(
        RecurringServiceProfile,
        on_delete=models.CASCADE,
        related_name='period_alerts',
    )
    fixed_expense_period = models.ForeignKey(
        FixedExpensePeriod,
        on_delete=models.CASCADE,
        related_name='tax_backup_alerts',
    )
    alert_type = models.CharField(max_length=30, choices=AlertType.choices)
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.OPEN,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['service_profile', 'status'], name='tb_alert_svc_status_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['service_profile', 'fixed_expense_period', 'alert_type'],
                name='tb_one_alert_per_period_type',
            ),
        ]

    def __str__(self):
        return f'Alert({self.service_profile_id}) — {self.get_alert_type_display()} [{self.status}]'


# ─────────────────────────────────────────────────────────────────────────────
# 7. DuplicateFlag — posible gasto duplicado
# ─────────────────────────────────────────────────────────────────────────────

class DuplicateFlag(models.Model):
    """
    Marcador de posible duplicado entre dos perfiles fiscales.
    Se genera automáticamente cuando un FiscalDocument coincide con otro
    del mismo business por (issuer_tax_id + invoice_number + issue_date + total).

    Convención: fiscal_profile_id siempre < matched_profile_id (par canónico).
    El save() lo garantiza. El UniqueConstraint impide el espejo A-B / B-A.
    """
    fiscal_profile = models.ForeignKey(
        ExpenseFiscalProfile,
        on_delete=models.CASCADE,
        related_name='duplicate_flags',
        help_text='Perfil con ID menor del par',
    )
    matched_profile = models.ForeignKey(
        ExpenseFiscalProfile,
        on_delete=models.CASCADE,
        related_name='flagged_by',
        help_text='Perfil con ID mayor del par',
    )
    match_type = models.CharField(max_length=40, choices=DuplicateMatchType.choices)
    status = models.CharField(
        max_length=30,
        choices=DuplicateStatus.choices,
        default=DuplicateStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['fiscal_profile', 'status'], name='tb_dup_profile_status_idx'),
        ]
        constraints = [
            # Par canónico: (min_id, max_id) — save() garantiza el orden
            models.UniqueConstraint(
                fields=['fiscal_profile', 'matched_profile'],
                name='tb_unique_duplicate_pair',
            ),
            # Impedir que un perfil se marque como duplicado de sí mismo
            models.CheckConstraint(
                check=~models.Q(fiscal_profile=models.F('matched_profile')),
                name='tb_dup_no_self_ref',
            ),
        ]

    def save(self, *args, **kwargs):
        # Normalizar: fiscal_profile_id siempre es el menor del par
        if self.fiscal_profile_id and self.matched_profile_id:
            if self.fiscal_profile_id > self.matched_profile_id:
                self.fiscal_profile_id, self.matched_profile_id = (
                    self.matched_profile_id, self.fiscal_profile_id
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Duplicate? {self.fiscal_profile_id} ↔ {self.matched_profile_id} [{self.status}]'
