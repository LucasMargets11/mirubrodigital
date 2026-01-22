from decimal import Decimal
from typing import Tuple

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import Product
from apps.business.models import Business
from .models import ProductStock, StockMovement


def ensure_stock_record(business: Business, product: Product) -> ProductStock:
  stock, _ = ProductStock.objects.get_or_create(
    business=business,
    product=product,
    defaults={'quantity': Decimal('0')},
  )
  if transaction.get_connection().in_atomic_block:
    stock = ProductStock.objects.select_for_update().get(pk=stock.pk)
  return stock


@transaction.atomic
def register_stock_movement(
  *,
  business: Business,
  product: Product,
  movement_type: str,
  quantity: Decimal,
  note: str = '',
  created_by=None,
) -> Tuple[StockMovement, ProductStock]:
  if product.business_id != business.id:
    raise ValidationError('Producto fuera del negocio actual.')

  stock = ensure_stock_record(business, product)
  normalized_qty = Decimal(quantity)
  if normalized_qty <= 0:
    raise ValidationError('La cantidad debe ser mayor a cero.')

  movement_enum = StockMovement.MovementType
  if movement_type not in movement_enum.values:
    raise ValidationError('Tipo de movimiento invalido.')

  if movement_type == movement_enum.ADJUST:
    new_quantity = normalized_qty
  elif movement_type == movement_enum.IN:
    new_quantity = stock.quantity + normalized_qty
  else:
    new_quantity = stock.quantity - normalized_qty

  if new_quantity < 0:
    raise ValidationError('Stock insuficiente para realizar la operacion solicitada.')

  stock.quantity = new_quantity
  stock.save(update_fields=['quantity', 'updated_at'])

  movement = StockMovement.objects.create(
    business=business,
    product=product,
    movement_type=movement_type,
    quantity=normalized_qty,
    note=note,
    created_by=created_by,
  )
  return movement, stock
