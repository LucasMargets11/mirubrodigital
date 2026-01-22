import uuid

from django.conf import settings
from django.db import models


class Order(models.Model):
  class Status(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    PREPARING = 'preparing', 'En preparación'
    READY = 'ready', 'Lista'
    DELIVERED = 'delivered', 'Entregada'
    CANCELED = 'canceled', 'Cancelada'

  class Channel(models.TextChoices):
    DINE_IN = 'dine_in', 'Salón'
    PICKUP = 'pickup', 'Retiro'
    DELIVERY = 'delivery', 'Delivery'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='orders', on_delete=models.CASCADE)
  number = models.PositiveIntegerField()
  status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
  channel = models.CharField(max_length=24, choices=Channel.choices, default=Channel.DINE_IN)
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
    ]

  def __str__(self) -> str:
    return f"Orden #{self.number} · {self.business_id}"


class OrderItem(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  order = models.ForeignKey('orders.Order', related_name='items', on_delete=models.CASCADE)
  product = models.ForeignKey('catalog.Product', related_name='order_items', null=True, blank=True, on_delete=models.SET_NULL)
  name = models.CharField(max_length=255)
  note = models.CharField(max_length=255, blank=True)
  quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
  unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['created_at']
    indexes = [
      models.Index(fields=['order']),
    ]

  def __str__(self) -> str:
    return f"Item · {self.name} ({self.order_id})"
