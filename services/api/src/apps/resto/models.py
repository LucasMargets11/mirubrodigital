from __future__ import annotations

import uuid

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Table(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='resto_tables', on_delete=models.CASCADE)
  code = models.CharField(max_length=16)
  name = models.CharField(max_length=120)
  capacity = models.PositiveIntegerField(null=True, blank=True)
  area = models.CharField(max_length=64, blank=True)
  notes = models.CharField(max_length=255, blank=True)
  is_enabled = models.BooleanField(default=True)
  is_paused = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['code']
    constraints = [
      models.UniqueConstraint(fields=['business', 'code'], name='resto_table_unique_code_per_business'),
    ]
    indexes = [
      models.Index(fields=['business', 'is_enabled']),
      models.Index(fields=['business', 'is_paused']),
    ]

  def __str__(self) -> str:  # pragma: no cover - representational helper
    return f"Mesa {self.code} · {self.business_id}"


class RestaurantOperationSettingsManager(models.Manager):
  def for_business(self, business):
    if business is None:
      raise ValueError('Business is required to resolve restaurant operation settings')
    settings, _ = self.get_or_create(business=business)
    return settings


class RestaurantOperationSettings(models.Model):
  class DefaultPosMode(models.TextChoices):
    QUICK_SALE = 'quick_sale', 'Venta rapida'
    KITCHEN_ORDER = 'kitchen_order', 'Pedido a cocina'

  business = models.OneToOneField(
    'business.Business',
    related_name='resto_operation_settings',
    on_delete=models.CASCADE,
  )
  tables_enabled = models.BooleanField(default=True)
  kitchen_enabled = models.BooleanField(default=True)
  counter_orders_enabled = models.BooleanField(default=True)
  pos_quick_sale_enabled = models.BooleanField(default=True)
  allow_pickup_orders = models.BooleanField(default=True)
  allow_dine_in_orders = models.BooleanField(default=True)
  allow_delivery_orders = models.BooleanField(default=False)
  default_pos_mode = models.CharField(
    max_length=32,
    choices=DefaultPosMode.choices,
    default=DefaultPosMode.QUICK_SALE,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  objects = RestaurantOperationSettingsManager()

  class Meta:
    verbose_name = 'Restaurant Operation Settings'
    verbose_name_plural = 'Restaurant Operation Settings'

  def __str__(self) -> str:  # pragma: no cover - representational helper
    return f"Restaurant operation settings · {self.business_id}"


class TableLayout(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.OneToOneField('business.Business', related_name='resto_table_layout', on_delete=models.CASCADE)
  grid_cols = models.PositiveIntegerField(default=12)
  grid_rows = models.PositiveIntegerField(default=8)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['business']

  def __str__(self) -> str:  # pragma: no cover - representational helper
    return f"Layout mesas {self.business_id}"


class TablePlacement(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='resto_table_placements', on_delete=models.CASCADE)
  layout = models.ForeignKey(TableLayout, related_name='placements', on_delete=models.CASCADE)
  table = models.ForeignKey(Table, related_name='placements', on_delete=models.CASCADE)
  x = models.PositiveIntegerField()
  y = models.PositiveIntegerField()
  w = models.PositiveIntegerField(default=1)
  h = models.PositiveIntegerField(default=1)
  rotation = models.IntegerField(default=0)
  z_index = models.IntegerField(default=0)

  class Meta:
    ordering = ['table__code']
    constraints = [
      models.UniqueConstraint(fields=['layout', 'table'], name='resto_tableplacement_unique_layout_table'),
    ]
    indexes = [
      models.Index(fields=['business', 'table']),
      models.Index(fields=['layout']),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"Placement {self.table_id} ({self.x},{self.y})"


@receiver(post_save, sender='business.Business')
def ensure_resto_operation_settings(sender, instance, created: bool, **kwargs):  # pragma: no cover
  RestaurantOperationSettings.objects.get_or_create(business=instance)
