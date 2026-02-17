import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class DocumentSeries(models.Model):
  """Serie unificada para todos los tipos de documentos."""
  
  class DocumentType(models.TextChoices):
    INVOICE = 'invoice', 'Factura'
    QUOTE = 'quote', 'Presupuesto'
    RECEIPT = 'receipt', 'Recibo'
    CREDIT_NOTE = 'credit_note', 'Nota de Crédito'
    DEBIT_NOTE = 'debit_note', 'Nota de Débito'
    DELIVERY_NOTE = 'delivery_note', 'Remito'
  
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    'business.Business',
    related_name='document_series',
    on_delete=models.CASCADE
  )
  document_type = models.CharField(
    max_length=32,
    choices=DocumentType.choices
  )
  
  # Letra (A/B/C/M/X/etc)
  letter = models.CharField(max_length=8, default='X')
  
  # Formato
  prefix = models.CharField(max_length=16, blank=True)
  suffix = models.CharField(max_length=16, blank=True)
  point_of_sale = models.CharField(max_length=8, blank=True, help_text='Punto de venta (ej: 0001)')
  
  # Numeración
  next_number = models.PositiveIntegerField(default=1)
  
  # Estado
  is_active = models.BooleanField(default=True)
  is_default = models.BooleanField(default=False)
  
  # Multi-sucursal (opcional)
  branch = models.ForeignKey(
    'business.Business',
    null=True,
    blank=True,
    related_name='series_by_branch',
    on_delete=models.CASCADE
  )
  
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  
  class Meta:
    db_table = 'document_series'
    ordering = ['document_type', 'letter']
    constraints = [
      models.UniqueConstraint(
        fields=['business', 'document_type', 'letter', 'point_of_sale'],
        name='unique_series_per_doc_type',
      ),
    ]
    indexes = [
      models.Index(fields=['business', 'document_type', 'is_active']),
    ]
  
  def __str__(self) -> str:
    return f"{self.get_document_type_display()} · {self.letter} · {self.business.name}"
  
  def format_full_number(self, number: int) -> str:
    """
    Formato configurable:
    - Con PV: A-0001-00000123
    - Sin PV: A-00000123
    - Con prefix: A-SUCU1-00000123
    """
    parts = [self.letter]
    if self.point_of_sale:
      parts.append(self.point_of_sale.zfill(4))
    if self.prefix:
      parts.append(self.prefix)
    parts.append(str(number).zfill(8))
    return '-'.join(parts)
  
  def get_next_number(self) -> int:
    """Obtiene y reserva el próximo número de forma atómica."""
    from django.db import transaction
    with transaction.atomic():
      # Lock row para evitar race conditions
      series = DocumentSeries.objects.select_for_update().get(pk=self.pk)
      current_number = series.next_number
      series.next_number += 1
      series.save(update_fields=['next_number', 'updated_at'])
      return current_number


class InvoiceSeries(models.Model):
  """
  DEPRECADO: Usar DocumentSeries en su lugar.
  Mantenido para compatibilidad temporal durante migración.
  """
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='invoice_series', on_delete=models.CASCADE)
  code = models.CharField(max_length=8, default='X')
  prefix = models.CharField(max_length=16, blank=True)
  next_number = models.PositiveIntegerField(default=1)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['code']
    constraints = [
      models.UniqueConstraint(fields=['business', 'code'], name='invoice_series_unique_code_per_business'),
    ]

  def __str__(self) -> str:  # pragma: no cover - repr utility
    return f"Serie {self.code} ({self.business_id}) [DEPRECADO]"

  def format_full_number(self, number: int) -> str:
    prefix_part = (self.prefix or '').strip()
    padded_prefix = prefix_part.zfill(4) if prefix_part else None
    padded_number = str(number).zfill(8)
    if padded_prefix:
      return f"{self.code}-{padded_prefix}-{padded_number}"
    return f"{self.code}-{padded_number}"


class Invoice(models.Model):
  class Status(models.TextChoices):
    ISSUED = 'issued', 'Emitida'
    VOIDED = 'voided', 'Anulada'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='invoices', on_delete=models.CASCADE)
  sale = models.OneToOneField('sales.Sale', related_name='invoice', on_delete=models.PROTECT)
  series = models.ForeignKey(InvoiceSeries, related_name='invoices', on_delete=models.PROTECT)
  number = models.PositiveIntegerField()
  full_number = models.CharField(max_length=48)
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
  issued_at = models.DateTimeField(default=timezone.now)
  customer_name = models.CharField(max_length=255, blank=True)
  customer_tax_id = models.CharField(max_length=64, blank=True)
  customer_address = models.CharField(max_length=255, blank=True)
  subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='invoices_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  pdf_file = models.FileField(upload_to='invoices/', null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-issued_at', '-number']
    constraints = [
      models.UniqueConstraint(fields=['business', 'series', 'number'], name='invoice_unique_number_per_series'),
    ]
    indexes = [
      models.Index(fields=['business', 'issued_at']),
      models.Index(fields=['business', 'status']),
    ]

  def __str__(self) -> str:  # pragma: no cover - repr utility
    return f"Factura {self.full_number}"
