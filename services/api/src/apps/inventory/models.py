import uuid

from django.conf import settings
from django.db import models


class StockMovement(models.Model):
  class MovementType(models.TextChoices):
    IN = 'IN', 'Entrada'
    OUT = 'OUT', 'Salida'
    ADJUST = 'ADJUST', 'Ajuste'
    WASTE = 'WASTE', 'Merma'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='stock_movements', on_delete=models.CASCADE)
  product = models.ForeignKey('catalog.Product', related_name='stock_movements', on_delete=models.PROTECT)
  movement_type = models.CharField(max_length=16, choices=MovementType.choices)
  quantity = models.DecimalField(max_digits=12, decimal_places=2)
  note = models.TextField(blank=True)
  reason = models.CharField(max_length=64, blank=True)
  metadata = models.JSONField(default=dict, blank=True)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='inventory_movements',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['-created_at']
    indexes = [
      models.Index(fields=['business', 'created_at']),
      models.Index(fields=['business', 'product']),
    ]

  def __str__(self) -> str:
    return f"{self.get_movement_type_display()} · {self.product_id}"


class ProductStock(models.Model):
  business = models.ForeignKey('business.Business', related_name='inventory_levels', on_delete=models.CASCADE)
  product = models.OneToOneField('catalog.Product', related_name='stock_level', on_delete=models.CASCADE)
  quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    constraints = [
      models.UniqueConstraint(fields=['business', 'product'], name='product_stock_business_product'),
    ]

  def __str__(self) -> str:
    return f"{self.product_id} · {self.quantity}"


class InventoryImportJob(models.Model):
  class Status(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    PROCESSING = 'processing', 'Procesando'
    DONE = 'done', 'Completado'
    FAILED = 'failed', 'Fallido'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='inventory_imports', on_delete=models.CASCADE)
  created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='inventory_imports', on_delete=models.SET_NULL, null=True)
  filename = models.CharField(max_length=255)
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
  rows = models.JSONField(default=list, blank=True)
  summary = models.JSONField(default=dict, blank=True)
  created_count = models.PositiveIntegerField(default=0)
  updated_count = models.PositiveIntegerField(default=0)
  adjusted_count = models.PositiveIntegerField(default=0)
  skipped_count = models.PositiveIntegerField(default=0)
  error_count = models.PositiveIntegerField(default=0)
  warning_count = models.PositiveIntegerField(default=0)
  result_url = models.URLField(blank=True)
  errors = models.JSONField(default=list, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at']

  def __str__(self) -> str:
    return f"Importación {self.filename} ({self.status})"
