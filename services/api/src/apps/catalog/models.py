import uuid

from django.db import models


class ProductCategory(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='product_categories', on_delete=models.CASCADE)
  name = models.CharField(max_length=100)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['name']
    verbose_name = 'Categoría de Producto'
    verbose_name_plural = 'Categorías de Productos'
    constraints = [
      models.UniqueConstraint(
        fields=['business', 'name'],
        name='unique_category_per_business'
      )
    ]
    indexes = [
      models.Index(fields=['business', 'name']),
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"


class Product(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='products', on_delete=models.CASCADE)
  category = models.ForeignKey(
    'catalog.ProductCategory',
    related_name='products',
    null=True,
    blank=True,
    on_delete=models.SET_NULL
  )
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
      models.Index(fields=['business', 'category']),
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"
