from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class CashRegister(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='cash_registers', on_delete=models.CASCADE)
  name = models.CharField(max_length=128)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['name']
    constraints = [
      models.UniqueConstraint(fields=['business', 'name'], name='cash_register_unique_name_per_business'),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"{self.name} · {self.business_id}"


class CashSession(models.Model):
  class Status(models.TextChoices):
    OPEN = 'open', 'Abierta'
    CLOSED = 'closed', 'Cerrada'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='cash_sessions', on_delete=models.CASCADE)
  register = models.ForeignKey('cash.CashRegister', related_name='sessions', null=True, blank=True, on_delete=models.PROTECT)
  opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='cash_sessions_opened', on_delete=models.PROTECT)
  opened_by_name = models.CharField(max_length=120, blank=True, default='')
  closed_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='cash_sessions_closed',
    null=True,
    blank=True,
    on_delete=models.PROTECT,
  )
  opening_cash_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  closing_cash_counted = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
  expected_cash_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
  difference_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
  closing_note = models.TextField(blank=True)
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
  opened_at = models.DateTimeField(auto_now_add=True)
  closed_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-opened_at']
    constraints = [
      models.UniqueConstraint(
        fields=['register'],
        condition=Q(status='open'),
        name='cash_session_unique_open_register',
      ),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"Sesion caja {self.id} · {self.business_id}"


class Payment(models.Model):
  class Method(models.TextChoices):
    CASH = 'cash', 'Efectivo'
    DEBIT = 'debit', 'Débito'
    CREDIT = 'credit', 'Crédito'
    TRANSFER = 'transfer', 'Transferencia'
    WALLET = 'wallet', 'Billetera'
    ACCOUNT = 'account', 'Cuenta corriente'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='payments', on_delete=models.CASCADE)
  sale = models.ForeignKey('sales.Sale', related_name='payments', on_delete=models.PROTECT)
  session = models.ForeignKey('cash.CashSession', related_name='payments', on_delete=models.PROTECT)
  method = models.CharField(max_length=16, choices=Method.choices)
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  reference = models.CharField(max_length=128, blank=True)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='payments_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at']
    indexes = [
      models.Index(fields=['business', 'created_at']),
      models.Index(fields=['business', 'session']),
      models.Index(fields=['business', 'sale']),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"Pago {self.amount} · {self.sale_id}"


class CashMovement(models.Model):
  class MovementType(models.TextChoices):
    IN = 'in', 'Ingreso'
    OUT = 'out', 'Egreso'

  class Category(models.TextChoices):
    EXPENSE = 'expense', 'Gasto'
    WITHDRAW = 'withdraw', 'Retiro'
    DEPOSIT = 'deposit', 'Depósito'
    OTHER = 'other', 'Otro'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='cash_movements', on_delete=models.CASCADE)
  session = models.ForeignKey('cash.CashSession', related_name='movements', on_delete=models.PROTECT)
  movement_type = models.CharField(max_length=8, choices=MovementType.choices)
  category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
  method = models.CharField(max_length=16, choices=Payment.Method.choices, default=Payment.Method.CASH)
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  note = models.TextField(blank=True)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='cash_movements_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at']
    indexes = [
      models.Index(fields=['business', 'created_at']),
      models.Index(fields=['business', 'session']),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"Movimiento {self.movement_type} · {self.amount}"
