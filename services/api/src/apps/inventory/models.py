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
