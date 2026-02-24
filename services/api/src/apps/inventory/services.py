from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.business.models import Business
from .models import ProductStock, StockMovement, StockReplenishment


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
  reason: str = '',
  metadata: Dict[str, Any] | None = None,
  allow_negative_stock: bool = False,
) -> Tuple[StockMovement, ProductStock]:
  if product.business_id != business.id:
    raise ValidationError('Producto fuera del negocio actual.')

  stock = ensure_stock_record(business, product)
  normalized_qty = Decimal(quantity)
  movement_enum = StockMovement.MovementType
  if movement_type == movement_enum.ADJUST:
    if normalized_qty < 0:
      raise ValidationError('La cantidad debe ser mayor o igual a cero para un ajuste.')
  else:
    if normalized_qty <= 0:
      raise ValidationError('La cantidad debe ser mayor a cero.')

  if movement_type not in movement_enum.values:
    raise ValidationError('Tipo de movimiento invalido.')

  if movement_type == movement_enum.ADJUST:
    new_quantity = normalized_qty
  elif movement_type == movement_enum.IN:
    new_quantity = stock.quantity + normalized_qty
  else:
    new_quantity = stock.quantity - normalized_qty

  if new_quantity < 0 and not allow_negative_stock:
    raise ValidationError('Stock insuficiente para realizar la operacion solicitada.')

  metadata_payload: Dict[str, Any] = metadata or {}
  stock.quantity = new_quantity
  stock.save(update_fields=['quantity', 'updated_at'])

  movement = StockMovement.objects.create(
    business=business,
    product=product,
    movement_type=movement_type,
    quantity=normalized_qty,
    note=note,
    reason=reason,
    metadata=metadata_payload,
    created_by=created_by,
  )
  return movement, stock


@transaction.atomic
def create_stock_replenishment(
  *,
  business: Business,
  occurred_at=None,
  supplier_name: str,
  invoice_number: str = '',
  account,
  purchase_category=None,
  notes: str = '',
  items: List[Dict[str, Any]],
  created_by=None,
) -> StockReplenishment:
  """
  Crea una reposición de stock (compra de mercadería) de forma atómica:
  - N movimientos de stock IN (uno por producto)
  - 1 transacción financiera OUT por el total (Σ qty × unit_cost)
  - Trazabilidad bidireccional entre reposición, movimientos y transacción
  """
  from apps.treasury.models import Account, TransactionCategory, Transaction
  from datetime import datetime, time as dt_time

  if occurred_at is None:
    occurred_at = timezone.localdate()

  # If occurred_at is a date (not datetime), convert to an aware datetime
  # at noon in the configured timezone to avoid day-boundary issues.
  if not isinstance(occurred_at, datetime):
    naive_noon = datetime.combine(occurred_at, dt_time(12, 0))
    occurred_at_dt = timezone.make_aware(naive_noon)
  else:
    occurred_at_dt = occurred_at

  # Validate account belongs to business
  if account.business_id != business.id:
    raise ValidationError('La cuenta no pertenece a este negocio.')

  # Validate purchase_category
  if purchase_category is not None:
    if purchase_category.business_id != business.id:
      raise ValidationError('La categoría no pertenece a este negocio.')
    if purchase_category.direction != TransactionCategory.Direction.EXPENSE:
      raise ValidationError('La categoría debe ser de tipo Egreso.')

  # Validate no duplicate products
  product_ids = [str(item['product_id']) for item in items]
  if len(product_ids) != len(set(product_ids)):
    raise ValidationError('No se permiten productos duplicados. Consolidá las cantidades en un solo ítem.')

  if not items:
    raise ValidationError('Debe incluir al menos un producto.')

  # Validate and resolve items
  validated_items = []
  for item in items:
    product_id = item['product_id']
    quantity = Decimal(str(item['quantity']))
    unit_cost = Decimal(str(item['unit_cost']))

    if quantity <= 0:
      raise ValidationError(f'La cantidad del producto debe ser mayor a cero.')
    if unit_cost < 0:
      raise ValidationError(f'El costo unitario no puede ser negativo.')

    try:
      product = Product.objects.get(pk=product_id, business=business)
    except Product.DoesNotExist:
      raise ValidationError(f'Producto {product_id} no encontrado en este negocio.')

    validated_items.append({'product': product, 'quantity': quantity, 'unit_cost': unit_cost})

  # Calculate total
  total_amount = sum(item['quantity'] * item['unit_cost'] for item in validated_items)

  # Get or create default category if not provided
  if purchase_category is None:
    purchase_category, _ = TransactionCategory.objects.get_or_create(
      business=business,
      name='Compras de Mercadería',
      direction=TransactionCategory.Direction.EXPENSE,
    )

  # Create StockReplenishment (without transaction yet)
  # occurred_at is a date value for the replenishment itself.
  replenishment = StockReplenishment.objects.create(
    business=business,
    occurred_at=occurred_at if not isinstance(occurred_at, datetime) else occurred_at.date(),
    supplier_name=supplier_name,
    invoice_number=invoice_number,
    account=account,
    purchase_category=purchase_category,
    total_amount=total_amount,
    notes=notes,
    status=StockReplenishment.Status.POSTED,
    created_by=created_by,
  )

  # Create stock movements (IN) for each item
  for item in validated_items:
    movement, _ = register_stock_movement(
      business=business,
      product=item['product'],
      movement_type=StockMovement.MovementType.IN,
      quantity=item['quantity'],
      note=f'Reposición — {supplier_name}',
      created_by=created_by,
      reason='replenishment',
    )
    movement.unit_cost = item['unit_cost']
    movement.replenishment = replenishment
    movement.save(update_fields=['unit_cost', 'replenishment'])

  # Build description
  invoice_part = f' ({invoice_number})' if invoice_number else ''
  description = f'Compra mercadería — {supplier_name}{invoice_part}'

  # Create OUT transaction: Transaction.occurred_at is a DateTimeField,
  # so we use the aware datetime (noon AR) derived from the replenishment date.
  tx = Transaction.objects.create(
    business=business,
    account=account,
    direction=Transaction.Direction.OUT,
    amount=total_amount,
    occurred_at=occurred_at_dt,
    category=purchase_category,
    description=description,
    status=Transaction.Status.POSTED,
    reference_type='stock_replenishment',
    reference_id=str(replenishment.id),
    created_by=created_by,
  )

  # Link transaction to replenishment
  replenishment.transaction = tx
  replenishment.save(update_fields=['transaction'])

  # ------------------------------------------------------------------ #
  # Create / update the Expense record for reporting in Finanzas → Gastos
  # This does NOT create a new financial movement; it re-uses *tx*.
  # The update_or_create guarantees idempotence: retrying / re-posting
  # will update the existing expense instead of duplicating it.
  # ------------------------------------------------------------------ #
  from apps.treasury.models import Expense

  expense_category, _ = TransactionCategory.objects.get_or_create(
    business=business,
    name='Restablecimiento de stock',
    defaults={'direction': TransactionCategory.Direction.EXPENSE},
  )

  invoice_suffix = f' ({invoice_number})' if invoice_number else ''
  expense_name = f'Reposición de stock — {supplier_name}{invoice_suffix}'

  Expense.objects.update_or_create(
    business=business,
    source_type='stock_replenishment',
    source_id=str(replenishment.id),
    defaults=dict(
      name=expense_name,
      category=expense_category,
      amount=total_amount,
      due_date=replenishment.occurred_at,   # DateField on Expense
      status=Expense.Status.PAID,
      paid_at=occurred_at_dt,
      paid_account=account,
      payment_transaction=tx,              # links to the existing OUT movement
      notes=notes or None,
      is_auto_generated=True,
    ),
  )

  return replenishment


@transaction.atomic
def void_stock_replenishment(
  *,
  replenishment: StockReplenishment,
  reason: str,
  voided_by=None,
) -> StockReplenishment:
  """
  Anula una reposición de stock de forma segura:
  - Marca la transacción financiera como VOIDED
  - Crea movimientos OUT compensatorios por cada ítem
  - Marca la reposición como VOIDED
  Es idempotente: si ya está anulada devuelve sin duplicar reversas.
  """
  from apps.treasury.models import Transaction

  # Idempotent: already voided
  if replenishment.status == StockReplenishment.Status.VOIDED:
    return replenishment

  # Void the linked transaction
  if replenishment.transaction_id:
    Transaction.objects.filter(pk=replenishment.transaction_id).update(
      status=Transaction.Status.VOIDED
    )

  # Create compensatory OUT movements
  in_movements = (
    StockMovement.objects
    .filter(replenishment=replenishment, movement_type=StockMovement.MovementType.IN)
    .select_related('product')
  )

  for movement in in_movements:
    # Idempotent: skip if compensatory already exists
    already_reversed = StockMovement.objects.filter(
      replenishment=replenishment,
      movement_type=StockMovement.MovementType.OUT,
      reason='replenishment_void',
      product=movement.product,
    ).exists()

    if not already_reversed:
      comp, _ = register_stock_movement(
        business=replenishment.business,
        product=movement.product,
        movement_type=StockMovement.MovementType.OUT,
        quantity=movement.quantity,
        note=f'Anulación de reposición — {reason}',
        created_by=voided_by,
        reason='replenishment_void',
        allow_negative_stock=True,
      )
      comp.replenishment = replenishment
      comp.save(update_fields=['replenishment'])

  # Mark replenishment voided
  replenishment.status = StockReplenishment.Status.VOIDED
  replenishment.save(update_fields=['status'])

  # Cancel the linked Expense (classificatory record only — no money movement created)
  from apps.treasury.models import Expense
  Expense.objects.filter(
    business=replenishment.business,
    source_type='stock_replenishment',
    source_id=str(replenishment.id),
  ).exclude(status=Expense.Status.CANCELLED).update(status=Expense.Status.CANCELLED)

  return replenishment



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
  reason: str = '',
  metadata: Dict[str, Any] | None = None,
  allow_negative_stock: bool = False,
) -> Tuple[StockMovement, ProductStock]:
  if product.business_id != business.id:
    raise ValidationError('Producto fuera del negocio actual.')

  stock = ensure_stock_record(business, product)
  normalized_qty = Decimal(quantity)
  movement_enum = StockMovement.MovementType
  if movement_type == movement_enum.ADJUST:
    if normalized_qty < 0:
      raise ValidationError('La cantidad debe ser mayor o igual a cero para un ajuste.')
  else:
    if normalized_qty <= 0:
      raise ValidationError('La cantidad debe ser mayor a cero.')

  if movement_type not in movement_enum.values:
    raise ValidationError('Tipo de movimiento invalido.')

  if movement_type == movement_enum.ADJUST:
    new_quantity = normalized_qty
  elif movement_type == movement_enum.IN:
    new_quantity = stock.quantity + normalized_qty
  else:
    new_quantity = stock.quantity - normalized_qty

  if new_quantity < 0 and not allow_negative_stock:
    raise ValidationError('Stock insuficiente para realizar la operacion solicitada.')

  metadata_payload: Dict[str, Any] = metadata or {}
  stock.quantity = new_quantity
  stock.save(update_fields=['quantity', 'updated_at'])

  movement = StockMovement.objects.create(
    business=business,
    product=product,
    movement_type=movement_type,
    quantity=normalized_qty,
    note=note,
    reason=reason,
    metadata=metadata_payload,
    created_by=created_by,
  )
  return movement, stock
