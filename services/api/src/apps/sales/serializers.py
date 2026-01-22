from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.cash.models import Payment
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.customers.serializers import CustomerSummarySerializer
from apps.inventory.models import StockMovement
from apps.inventory.services import register_stock_movement
from apps.invoices.models import Invoice
from .models import Sale, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
  product_id = serializers.SerializerMethodField()
  product_name = serializers.CharField(source='product_name_snapshot', read_only=True)

  class Meta:
    model = SaleItem
    fields = ['id', 'product_id', 'product_name', 'quantity', 'unit_price', 'line_total']
    read_only_fields = fields

  def get_product_id(self, obj: SaleItem):
    return getattr(obj.product, 'id', None)


class SalePaymentSerializer(serializers.ModelSerializer):
  method_label = serializers.CharField(source='get_method_display', read_only=True)

  class Meta:
    model = Payment
    fields = ['id', 'method', 'method_label', 'amount', 'reference', 'created_at']
    read_only_fields = fields


class SaleListSerializer(serializers.ModelSerializer):
  status_label = serializers.CharField(source='get_status_display', read_only=True)
  payment_method_label = serializers.CharField(source='get_payment_method_display', read_only=True)
  customer_name = serializers.SerializerMethodField()
  items_count = serializers.SerializerMethodField()
  invoice = serializers.SerializerMethodField()
  customer = CustomerSummarySerializer(read_only=True)
  paid_total = serializers.SerializerMethodField()
  balance = serializers.SerializerMethodField()

  class Meta:
    model = Sale
    fields = [
      'id',
      'number',
      'status',
      'status_label',
      'payment_method',
      'payment_method_label',
      'customer_id',
      'customer_name',
      'customer',
      'subtotal',
      'discount',
      'total',
      'notes',
      'created_at',
      'items_count',
      'invoice',
      'paid_total',
      'balance',
    ]
    read_only_fields = fields

  def get_customer_name(self, obj: Sale) -> Optional[str]:
    return getattr(obj.customer, 'name', None)

  def get_items_count(self, obj: Sale) -> int:
    annotated = getattr(obj, 'items_count', None)
    if annotated is not None:
      return int(annotated)
    return obj.items.count()

  def get_invoice(self, obj: Sale):
    try:
      invoice = obj.invoice
    except Invoice.DoesNotExist:
      return None
    if invoice is None:
      return None
    return {
      'id': str(invoice.id),
      'full_number': invoice.full_number,
      'status': invoice.status,
    }

  def get_paid_total(self, obj: Sale) -> Decimal:
    total = getattr(obj, 'payments_total', None)
    if total is not None:
      return Decimal(total)
    aggregate = obj.payments.aggregate(total=Sum('amount'))
    return aggregate.get('total') or Decimal('0')

  def get_balance(self, obj: Sale) -> Decimal:
    total = obj.total or Decimal('0')
    balance = total - self.get_paid_total(obj)
    return balance if balance > 0 else Decimal('0')


class SaleDetailSerializer(SaleListSerializer):
  items = SaleItemSerializer(many=True, read_only=True)
  payments = SalePaymentSerializer(many=True, read_only=True)

  class Meta(SaleListSerializer.Meta):
    fields = SaleListSerializer.Meta.fields + ['items', 'payments']


class SaleCreateItemSerializer(serializers.Serializer):
  product_id = serializers.UUIDField()
  quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
  unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

  def validate_quantity(self, value: Decimal) -> Decimal:
    if value <= 0:
      raise serializers.ValidationError('La cantidad debe ser mayor a cero.')
    return value

  def validate_unit_price(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El precio debe ser mayor o igual a cero.')
    return value


class SaleCreateSerializer(serializers.Serializer):
  customer_id = serializers.UUIDField(required=False, allow_null=True)
  payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices, default=Sale.PaymentMethod.CASH)
  discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0'))
  notes = serializers.CharField(required=False, allow_blank=True)
  items = SaleCreateItemSerializer(many=True)

  def validate_customer_id(self, value: Optional[UUID]):
    if value is None:
      return value
    business = self.context['business']
    try:
      customer = Customer.objects.get(pk=value, business=business)
    except Customer.DoesNotExist as exc:
      raise serializers.ValidationError('Cliente no encontrado en este negocio.') from exc
    self.context['customer'] = customer
    return value

  def validate_discount(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El descuento no puede ser negativo.')
    return value

  def validate_items(self, value: List[dict]) -> List[dict]:
    if not value:
      raise serializers.ValidationError('Agregá al menos un producto a la venta.')
    return value

  def _resolve_product(self, business, product_id: UUID) -> Product:
    try:
      return Product.objects.get(pk=product_id, business=business)
    except Product.DoesNotExist as exc:
      raise serializers.ValidationError(f'Producto {product_id} no encontrado en este negocio.') from exc

  @transaction.atomic
  def create(self, validated_data):
    business = self.context['business']
    request = self.context.get('request')
    user = getattr(request, 'user', None)
    customer = self.context.get('customer')

    last_number = (
      Sale.objects.select_for_update()
      .filter(business=business)
      .order_by('-number')
      .values_list('number', flat=True)
      .first()
    ) or 0

    sale = Sale.objects.create(
      business=business,
      customer=customer,
      number=last_number + 1,
      status=Sale.Status.COMPLETED,
      payment_method=validated_data.get('payment_method', Sale.PaymentMethod.CASH),
      notes=validated_data.get('notes', ''),
      created_by=user if getattr(user, 'is_authenticated', False) else None,
    )

    subtotal = Decimal('0')
    bulk_items: List[SaleItem] = []
    items_payload: List[dict[str, Any]] = validated_data['items']

    for payload in items_payload:
      product = self._resolve_product(business, payload['product_id'])
      quantity = Decimal(payload['quantity'])
      raw_unit_price = payload.get('unit_price')
      unit_price = Decimal(raw_unit_price) if raw_unit_price is not None else Decimal(product.price)
      line_total = (unit_price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
      subtotal += line_total

      bulk_items.append(
        SaleItem(
          sale=sale,
          product=product,
          product_name_snapshot=product.name,
          quantity=quantity,
          unit_price=unit_price,
          line_total=line_total,
        )
      )

      try:
        register_stock_movement(
          business=business,
          product=product,
          movement_type=StockMovement.MovementType.OUT,
          quantity=quantity,
          note=f'Venta #{sale.number}',
          created_by=user,
        )
      except ValidationError as exc:
        message = exc.messages[0] if exc.messages else 'No pudimos actualizar el stock.'
        raise serializers.ValidationError({'items': [f'{product.name}: {message}']}) from exc

    discount_value = validated_data.get('discount')
    discount = Decimal(discount_value) if discount_value is not None else Decimal('0')
    if discount > subtotal:
      raise serializers.ValidationError({'discount': 'El descuento no puede ser mayor al subtotal.'})
    total = subtotal - discount

    SaleItem.objects.bulk_create(bulk_items)
    sale.subtotal = subtotal
    sale.discount = discount
    sale.total = total
    sale.save(update_fields=['subtotal', 'discount', 'total', 'updated_at'])
    return sale

  def to_representation(self, instance):
    return SaleDetailSerializer(instance, context=self.context).data


class SaleCancelSerializer(serializers.Serializer):
  reason = serializers.CharField(required=False, allow_blank=True)

  @transaction.atomic
  def save(self, **kwargs):
    sale: Sale = self.context['sale']
    if sale.status == Sale.Status.CANCELLED:
      return sale

    user = self.context.get('user')
    reason = (self.validated_data.get('reason') or '').strip()

    for item in sale.items.select_related('product'):
      if item.product is None:
        continue
      register_stock_movement(
        business=sale.business,
        product=item.product,
        movement_type=StockMovement.MovementType.IN,
        quantity=item.quantity,
        note=f'Reversa venta #{sale.number}',
        created_by=user,
      )

    sale.status = Sale.Status.CANCELLED
    sale.cancelled_at = timezone.now()
    if getattr(user, 'is_authenticated', False):
      sale.cancelled_by = user

    note_updated = False
    if reason:
      sale.notes = (sale.notes + '\n' if sale.notes else '') + f'Cancelación: {reason}'
      note_updated = True

    update_fields = ['status', 'cancelled_at', 'updated_at']
    if sale.cancelled_by_id:
      update_fields.append('cancelled_by')
    if note_updated:
      update_fields.append('notes')
    sale.save(update_fields=update_fields)
    return sale
