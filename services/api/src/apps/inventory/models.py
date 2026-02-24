import uuid

from django.conf import settings
from django.db import models


class StockReplenishment(models.Model):
  """Evento de reposición de stock (compra de mercadería)."""

  class Status(models.TextChoices):
    POSTED = 'posted', 'Confirmado'
    VOIDED = 'voided', 'Anulado'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='stock_replenishments', on_delete=models.CASCADE)
  # DateField: the purchase date is conceptually date-only (no time component).
  # Using DateField eliminates UTC-shift bugs when the frontend sends YYYY-MM-DD.
  occurred_at = models.DateField()
  supplier_name = models.CharField(max_length=255)
  invoice_number = models.CharField(max_length=100, blank=True)
  account = models.ForeignKey(
    'treasury.Account',
    related_name='stock_replenishments',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  transaction = models.OneToOneField(
    'treasury.Transaction',
    related_name='stock_replenishment',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  purchase_category = models.ForeignKey(
    'treasury.TransactionCategory',
    related_name='stock_replenishments',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  total_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
  notes = models.TextField(blank=True)
  status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='stock_replenishments_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['-occurred_at']
    indexes = [
      models.Index(fields=['business', 'occurred_at']),
      models.Index(fields=['business', 'status']),
    ]

  def __str__(self) -> str:
    return f"Reposición {self.supplier_name} — {self.occurred_at:%Y-%m-%d}"


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
  unit_cost = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
  replenishment = models.ForeignKey(
    StockReplenishment,
    related_name='stock_movements',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
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
      models.Index(fields=['business', 'replenishment']),
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
