import uuid

from django.conf import settings
from django.db import models


class Sale(models.Model):
  class Status(models.TextChoices):
    COMPLETED = 'completed', 'Completada'
    CANCELLED = 'cancelled', 'Cancelada'

  class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Efectivo'
    TRANSFER = 'transfer', 'Transferencia'
    CARD = 'card', 'Tarjeta'
    OTHER = 'other', 'Otro'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='sales', on_delete=models.CASCADE)
  customer = models.ForeignKey(
    'customers.Customer',
    related_name='sales',
    null=True,
    blank=True,
    on_delete=models.PROTECT,
  )
  number = models.PositiveIntegerField()
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.COMPLETED)
  payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
  subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  notes = models.TextField(blank=True)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='sales_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  cancelled_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='sales_cancelled',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  cash_session = models.ForeignKey(
    'cash.CashSession',
    related_name='sales',
    null=True,
    blank=True,
    on_delete=models.PROTECT,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  cancelled_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    ordering = ['-created_at', '-number']
    constraints = [
      models.UniqueConstraint(fields=['business', 'number'], name='sales_business_number_unique'),
    ]
    indexes = [
      models.Index(fields=['business', 'status']),
      models.Index(fields=['business', 'created_at']),
    ]

  def __str__(self) -> str:
    return f"Venta #{self.number} · {self.business_id}"


class SaleItem(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  sale = models.ForeignKey('sales.Sale', related_name='items', on_delete=models.CASCADE)
  product = models.ForeignKey('catalog.Product', related_name='sale_items', null=True, blank=True, on_delete=models.SET_NULL)
  product_name_snapshot = models.CharField(max_length=255)
  quantity = models.DecimalField(max_digits=10, decimal_places=2)
  unit_price = models.DecimalField(max_digits=12, decimal_places=2)
  line_total = models.DecimalField(max_digits=12, decimal_places=2)
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['created_at']
    indexes = [
      models.Index(fields=['sale']),
      models.Index(fields=['sale', 'product']),
    ]

  def __str__(self) -> str:
    return f"Venta #{self.sale_id} · {self.product_name_snapshot}"


class QuoteSequence(models.Model):
  """Tabla para manejar la numeración correlativa de presupuestos por negocio."""
  business = models.OneToOneField('business.Business', related_name='quote_sequence', on_delete=models.CASCADE, primary_key=True)
  last_number = models.PositiveIntegerField(default=0)

  class Meta:
    db_table = 'sales_quote_sequence'

  def __str__(self) -> str:
    return f"Quote Sequence · {self.business_id} · {self.last_number}"


class Quote(models.Model):
  """Presupuesto: cotización sin afectar stock ni finanzas."""
  class Status(models.TextChoices):
    DRAFT = 'draft', 'Borrador'
    SENT = 'sent', 'Enviado'
    ACCEPTED = 'accepted', 'Aceptado'
    REJECTED = 'rejected', 'Rechazado'
    EXPIRED = 'expired', 'Vencido'
    CONVERTED = 'converted', 'Convertido'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='quotes', on_delete=models.CASCADE)
  number = models.CharField(max_length=20)  # Formato: P-000001
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
  
  # Cliente: si existe customer, sino campos directos
  customer = models.ForeignKey(
    'customers.Customer',
    related_name='quotes',
    null=True,
    blank=True,
    on_delete=models.PROTECT,
  )
  customer_name = models.CharField(max_length=255, blank=True)
  customer_email = models.EmailField(blank=True)
  customer_phone = models.CharField(max_length=50, blank=True)
  
  # Validez y condiciones
  valid_until = models.DateField(null=True, blank=True)
  notes = models.TextField(blank=True)
  terms = models.TextField(blank=True)
  currency = models.CharField(max_length=3, default='ARS')
  
  # Totales
  subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  
  # Auditoría
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='quotes_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  sent_at = models.DateTimeField(null=True, blank=True)
  is_deleted = models.BooleanField(default=False)

  class Meta:
    ordering = ['-created_at', '-number']
    constraints = [
      models.UniqueConstraint(fields=['business', 'number'], name='quotes_business_number_unique'),
    ]
    indexes = [
      models.Index(fields=['business', 'status']),
      models.Index(fields=['business', 'created_at']),
      models.Index(fields=['business', 'is_deleted']),
    ]

  def __str__(self) -> str:
    return f"Presupuesto {self.number} · {self.business_id}"


class QuoteItem(models.Model):
  """Ítem de un presupuesto."""
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  quote = models.ForeignKey('sales.Quote', related_name='items', on_delete=models.CASCADE)
  product = models.ForeignKey('catalog.Product', related_name='quote_items', null=True, blank=True, on_delete=models.SET_NULL)
  name_snapshot = models.CharField(max_length=255)
  quantity = models.DecimalField(max_digits=10, decimal_places=2)
  unit_price = models.DecimalField(max_digits=12, decimal_places=2)
  discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total_line = models.DecimalField(max_digits=12, decimal_places=2)
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['created_at']
    indexes = [
      models.Index(fields=['quote']),
      models.Index(fields=['quote', 'product']),
    ]

  def __str__(self) -> str:
    return f"Presupuesto {self.quote.number} · {self.name_snapshot}"
