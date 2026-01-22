from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from django.db import transaction
from rest_framework import serializers

from apps.catalog.models import Product
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
  class Meta:
    model = OrderItem
    fields = ['id', 'name', 'note', 'quantity', 'unit_price', 'total_price', 'product_id']
    read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
  items = OrderItemSerializer(many=True, read_only=True)
  status_label = serializers.CharField(source='get_status_display', read_only=True)
  channel_label = serializers.CharField(source='get_channel_display', read_only=True)

  class Meta:
    model = Order
    fields = [
      'id',
      'number',
      'status',
      'status_label',
      'channel',
      'channel_label',
      'table_name',
      'customer_name',
      'note',
      'total_amount',
      'opened_at',
      'updated_at',
      'closed_at',
      'items',
    ]
    read_only_fields = fields


class OrderItemInputSerializer(serializers.Serializer):
  product_id = serializers.UUIDField(required=False)
  name = serializers.CharField(max_length=255, required=False, allow_blank=True)
  note = serializers.CharField(max_length=255, required=False, allow_blank=True)
  quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
  unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)

  def validate_quantity(self, value: Decimal) -> Decimal:
    if value <= 0:
      raise serializers.ValidationError('La cantidad debe ser mayor a cero.')
    return value

  def validate_unit_price(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El precio debe ser positivo.')
    return value

  def validate(self, attrs):
    if not attrs.get('product_id') and not (attrs.get('name') and attrs['name'].strip()):
      raise serializers.ValidationError('Cada item necesita un producto o nombre.')
    return attrs


class OrderCreateSerializer(serializers.Serializer):
  channel = serializers.ChoiceField(choices=Order.Channel.choices, default=Order.Channel.DINE_IN)
  table_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
  customer_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
  note = serializers.CharField(required=False, allow_blank=True)
  items = OrderItemInputSerializer(many=True)

  def validate_items(self, value: List[dict]) -> List[dict]:
    if not value:
      raise serializers.ValidationError('Agregá al menos un item a la orden.')
    return value

  def _resolve_product(self, business, product_id) -> Optional[Product]:
    if not product_id:
      return None
    try:
      return Product.objects.get(pk=product_id, business=business)
    except Product.DoesNotExist as exc:
      raise serializers.ValidationError('Producto no encontrado en este negocio.') from exc

  @transaction.atomic
  def create(self, validated_data):
    business = self.context['business']
    request = self.context.get('request')
    created_by = getattr(request, 'user', None) if request else None

    last_number = (
      Order.objects.select_for_update()
      .filter(business=business)
      .order_by('-number')
      .values_list('number', flat=True)
      .first()
    ) or 0
    order = Order.objects.create(
      business=business,
      number=last_number + 1,
      channel=validated_data.get('channel', Order.Channel.DINE_IN),
      table_name=validated_data.get('table_name', ''),
      customer_name=validated_data.get('customer_name', ''),
      note=validated_data.get('note', ''),
      created_by=created_by if getattr(created_by, 'is_authenticated', False) else None,
    )

    total = Decimal('0')
    items_payload: List[dict] = validated_data['items']
    bulk_items: List[OrderItem] = []
    for payload in items_payload:
      product = self._resolve_product(business, payload.get('product_id'))
      item_name = payload.get('name') or (product.name if product else '')
      if not item_name:
        raise serializers.ValidationError('Cada item necesita un nombre.')
      quantity = Decimal(payload['quantity'])
      unit_price = Decimal(payload['unit_price'])
      line_total = quantity * unit_price
      total += line_total
      bulk_items.append(
        OrderItem(
          order=order,
          product=product,
          name=item_name,
          note=payload.get('note', ''),
          quantity=quantity,
          unit_price=unit_price,
          total_price=line_total,
        )
      )

    OrderItem.objects.bulk_create(bulk_items)
    order.total_amount = total
    order.save(update_fields=['total_amount'])
    return order

  def to_representation(self, instance):
    return OrderSerializer(instance, context=self.context).data


class OrderStatusSerializer(serializers.Serializer):
  status = serializers.ChoiceField(choices=Order.Status.choices)
