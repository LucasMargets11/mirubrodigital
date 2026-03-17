import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


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
  # ── Operative (POS) identity fields ─────────────────────────────────────────
  # created_by (auth.User FK above) remains for admin/backoffice flows.
  # created_by_employee is exclusively set by POS operative endpoints.
  created_by_employee = models.ForeignKey(
    'accounts.EmployeeProfile',
    related_name='sales_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  # cancelled_by_employee mirrors cancelled_by for future POS cancellation flows.
  cancelled_by_employee = models.ForeignKey(
    'accounts.EmployeeProfile',
    related_name='sales_cancelled',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
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
    return f"QuoteItem {self.name_snapshot} ({self.quantity}) - {self.quote.number}"


class OrderSequence(models.Model):
  """Tabla para manejar la numeración correlativa de pedidos por negocio."""
  business = models.OneToOneField('business.Business', related_name='order_sequence', on_delete=models.CASCADE, primary_key=True)
  last_number = models.PositiveIntegerField(default=0)

  class Meta:
    db_table = 'sales_order_sequence'

  def __str__(self) -> str:
    return f"Order Sequence · {self.business_id} · {self.last_number}"


class Order(models.Model):
  """Pedido comercial: encargo confirmado o en gestión."""
  class Status(models.TextChoices):
    # Borrador
    DRAFT = 'draft', 'Borrador'
    # Pendiente de confirmación (ej: stock insuficiente, revisión)
    PENDING_CONFIRMATION = 'pending_confirmation', 'Pendiente de Confirmación'
    # Confirmado (stock reservado)
    CONFIRMED = 'confirmed', 'Confirmado'
    # En preparación
    IN_PREPARATION = 'in_preparation', 'En Preparación'
    # Listo para entregar
    READY_FOR_DELIVERY = 'ready_for_delivery', 'Listo para Entregar'
    # Entregado (stock descontado)
    DELIVERED = 'delivered', 'Entregado'
    # Cancelado (libera reserva)
    CANCELLED = 'cancelled', 'Cancelado'

  class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    PARTIAL = 'partial', 'Parcial'
    PAID = 'paid', 'Pagado'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='commercial_orders', on_delete=models.CASCADE)
  # Nummeración secuencial (separada de Presupuestos y Ventas)
  number = models.CharField(max_length=20)  # Formato: O-000001
  
  customer = models.ForeignKey(
    'customers.Customer',
    related_name='commercial_orders',
    on_delete=models.PROTECT,
  )
  quote = models.ForeignKey(
    'sales.Quote',
    related_name='resulting_orders',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  sale = models.OneToOneField(
    'sales.Sale',
    related_name='source_order',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )

  status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
  payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

  order_date = models.DateField(default=timezone.now)
  estimated_delivery_date = models.DateField(null=True, blank=True)

  # Totales
  subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  surcharge_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  
  # Pagos
  total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

  notes = models.TextField(blank=True)
  metadata = models.JSONField(default=dict, blank=True)

  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='commercial_orders_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  deleted_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    ordering = ['-created_at']
    constraints = [
      models.UniqueConstraint(fields=['business', 'number'], name='orders_business_number_unique'),
    ]
    indexes = [
      models.Index(fields=['business', 'status']),
      models.Index(fields=['business', 'payment_status']),
      models.Index(fields=['business', 'customer']),
    ]

  def __str__(self) -> str:
    return f"Pedido {self.number} · {self.business_id}"


class OrderItem(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  order = models.ForeignKey('sales.Order', related_name='items', on_delete=models.CASCADE)
  product = models.ForeignKey('catalog.Product', related_name='sales_order_items', null=True, blank=True, on_delete=models.SET_NULL)
  
  # Snapshots
  sku_snapshot = models.CharField(max_length=64, blank=True)
  name_snapshot = models.CharField(max_length=255)
  description_snapshot = models.TextField(blank=True)
  
  unit_price = models.DecimalField(max_digits=12, decimal_places=2)
  quantity = models.DecimalField(max_digits=10, decimal_places=2)
  discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  subtotal = models.DecimalField(max_digits=12, decimal_places=2)
  
  # Trazabilidad de stock
  reserved_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
  delivered_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
  
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  def __str__(self) -> str:
    return f"Item {self.name_snapshot} ({self.quantity}) - {self.order.number}"


class OrderPayment(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  order = models.ForeignKey('sales.Order', related_name='payments', on_delete=models.CASCADE)
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  payment_date = models.DateTimeField(default=timezone.now)
  payment_method = models.CharField(max_length=50)  # O FK a PaymentMethod si existe
  notes = models.TextField(blank=True)
  
  # Link opcional a movimiento de caja real si se implementa integración full
  cash_movement = models.ForeignKey(
    'cash.CashMovement',
    related_name='order_payments',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )

  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='order_payments_registered',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self) -> str:
    return f"Pago {self.amount} - {self.order.number}"


class OrderHistory(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  order = models.ForeignKey('sales.Order', related_name='history', on_delete=models.CASCADE)
  action = models.CharField(max_length=50)
  from_status = models.CharField(max_length=50, blank=True, null=True)
  to_status = models.CharField(max_length=50, blank=True, null=True)
  payload = models.JSONField(default=dict, blank=True)
  
  user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='order_history_entries',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['-created_at']

  def __str__(self) -> str:
    return f"{self.action} - {self.order.number}"
