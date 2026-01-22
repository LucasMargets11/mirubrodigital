import uuid

from django.db import models


class Product(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='products', on_delete=models.CASCADE)
  name = models.CharField(max_length=255)
  sku = models.CharField(max_length=64, blank=True)
  barcode = models.CharField(max_length=128, blank=True)
  cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  stock_min = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['name']
    indexes = [
      models.Index(fields=['business', 'name']),
      models.Index(fields=['business', 'sku']),
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"
