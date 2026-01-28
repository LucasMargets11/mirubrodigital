import uuid

from django.conf import settings
from django.db import models


class Order(models.Model):
  class Status(models.TextChoices):
    DRAFT = 'draft', 'Borrador'
    OPEN = 'open', 'Abierta'
    SENT = 'sent', 'Enviada a cocina'
    PAID = 'paid', 'Pagada'
    CANCELLED = 'cancelled', 'Cancelada'

  class Channel(models.TextChoices):
    DINE_IN = 'dine_in', 'Salón'
    PICKUP = 'pickup', 'Retiro'
    DELIVERY = 'delivery', 'Delivery'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='orders', on_delete=models.CASCADE)
  sale = models.OneToOneField('sales.Sale', related_name='order', null=True, blank=True, on_delete=models.SET_NULL)
  number = models.PositiveIntegerField()
  status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
  channel = models.CharField(max_length=24, choices=Channel.choices, default=Channel.DINE_IN)
  table = models.ForeignKey('resto.Table', related_name='orders', null=True, blank=True, on_delete=models.SET_NULL)
  table_name = models.CharField(max_length=64, blank=True)
  customer_name = models.CharField(max_length=128, blank=True)
  note = models.TextField(blank=True)
  total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='orders_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  updated_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='orders_updated',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  opened_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  closed_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    ordering = ['-opened_at', '-number']
    constraints = [
      models.UniqueConstraint(fields=['business', 'number'], name='order_business_number_unique'),
    ]
    indexes = [
      models.Index(fields=['business', 'status']),
      models.Index(fields=['business', 'opened_at']),
      models.Index(fields=['business', 'table']),
    ]

  def __str__(self) -> str:
    return f"Orden #{self.number} · {self.business_id}"

  def recalculate_totals(self):
    aggregated = self.items.aggregate(total=models.Sum('total_price'))
    self.total_amount = aggregated.get('total') or 0
    self.save(update_fields=['total_amount', 'updated_at'])


class OrderItem(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  order = models.ForeignKey('orders.Order', related_name='items', on_delete=models.CASCADE)
  product = models.ForeignKey('catalog.Product', related_name='order_items', null=True, blank=True, on_delete=models.SET_NULL)
  name = models.CharField(max_length=255)
  note = models.CharField(max_length=255, blank=True)
  quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
  unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  modifiers = models.JSONField(default=list, blank=True)
  sold_without_stock = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['created_at']
    indexes = [
      models.Index(fields=['order']),
    ]

  def __str__(self) -> str:
    return f"Item · {self.name} ({self.order_id})"


class OrderDraft(models.Model):
  class Status(models.TextChoices):
    EDITING = 'editing', 'En edición'
    SUBMITTED = 'submitted', 'Confirmado'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='order_drafts', on_delete=models.CASCADE)
  channel = models.CharField(max_length=24, choices=Order.Channel.choices, default=Order.Channel.DINE_IN)
  table = models.ForeignKey('resto.Table', related_name='drafts', null=True, blank=True, on_delete=models.SET_NULL)
  table_name = models.CharField(max_length=64, blank=True)
  customer_name = models.CharField(max_length=128, blank=True)
  note = models.TextField(blank=True)
  status = models.CharField(max_length=24, choices=Status.choices, default=Status.EDITING)
  total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  items_count = models.PositiveIntegerField(default=0)
  client_reference = models.CharField(max_length=64, blank=True)
  source = models.CharField(max_length=32, default='pos')
  order = models.OneToOneField('orders.Order', related_name='draft', null=True, blank=True, on_delete=models.SET_NULL)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='order_drafts_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  updated_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='order_drafts_updated',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-updated_at']
    indexes = [
      models.Index(fields=['business', 'status']),
      models.Index(fields=['business', 'client_reference']),
    ]

  def __str__(self) -> str:
    return f"Borrador · {self.business_id} · {self.status}"

  def recalculate_totals(self):
    aggregated = self.items.aggregate(
      total=models.Sum('total_price'),
      count=models.Count('id'),
    )
    self.total_amount = aggregated.get('total') or 0
    self.items_count = aggregated.get('count') or 0
    self.save(update_fields=['total_amount', 'items_count', 'updated_at'])


class OrderDraftItem(models.Model):
  class StockStatus(models.TextChoices):
    IN_STOCK = 'in', 'Stock OK'
    LOW = 'low', 'Stock bajo'
    CRITICAL = 'critical', 'Crítico'
    OUT = 'out', 'Sin stock'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  draft = models.ForeignKey('orders.OrderDraft', related_name='items', on_delete=models.CASCADE)
  menu_item = models.ForeignKey('menu.MenuItem', related_name='order_draft_items', null=True, blank=True, on_delete=models.SET_NULL)
  product = models.ForeignKey('catalog.Product', related_name='order_draft_items', null=True, blank=True, on_delete=models.SET_NULL)
  name = models.CharField(max_length=255)
  note = models.CharField(max_length=255, blank=True)
  quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
  unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  stock_status = models.CharField(max_length=16, choices=StockStatus.choices, default=StockStatus.IN_STOCK)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['created_at']
    indexes = [
      models.Index(fields=['draft']),
      models.Index(fields=['draft', 'menu_item']),
    ]

  def __str__(self) -> str:
    return f"DraftItem · {self.name} ({self.draft_id})"
