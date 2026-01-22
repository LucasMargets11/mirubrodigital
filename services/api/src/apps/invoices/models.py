import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class InvoiceSeries(models.Model):
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
    return f"Serie {self.code} ({self.business_id})"

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
