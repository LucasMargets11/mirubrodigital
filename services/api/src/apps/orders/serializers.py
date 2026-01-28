from __future__ import annotations

import json

from decimal import Decimal
from typing import List, Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.business.models import CommercialSettings
from apps.cash.models import CashSession, Payment
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.inventory.services import ensure_stock_record, register_stock_movement
from apps.menu.models import MenuItem
from apps.sales.models import Sale, SaleItem
from apps.resto.services import ensure_table_available
from .models import Order, OrderDraft, OrderDraftItem, OrderItem


OUT_OF_STOCK_TAGS = {'sin stock', 'out-of-stock', 'out_stock', 'agotado'}
LOW_STOCK_TAGS = {'bajo stock', 'low-stock', 'low_stock'}
CRITICAL_STOCK_TAGS = {'critico', 'crítico', 'critical'}
EDITABLE_ORDER_STATUSES = {Order.Status.DRAFT, Order.Status.OPEN, Order.Status.SENT}


class OrderItemSerializer(serializers.ModelSerializer):
  class Meta:
    model = OrderItem
    fields = ['id', 'name', 'note', 'quantity', 'unit_price', 'total_price', 'product_id', 'modifiers', 'sold_without_stock']
    read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
  items = OrderItemSerializer(many=True, read_only=True)
  status_label = serializers.CharField(source='get_status_display', read_only=True)
  channel_label = serializers.CharField(source='get_channel_display', read_only=True)
  sale_id = serializers.SerializerMethodField()
  sale_number = serializers.SerializerMethodField()
  sale_total = serializers.SerializerMethodField()
  table_id = serializers.SerializerMethodField()
  table_code = serializers.CharField(source='table.code', read_only=True, allow_null=True, default=None)
  subtotal_amount = serializers.SerializerMethodField()

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
      'table_id',
      'table_code',
      'customer_name',
      'note',
      'total_amount',
      'opened_at',
      'updated_at',
      'closed_at',
      'items',
      'sale_id',
      'sale_number',
      'sale_total',
      'subtotal_amount',
    ]
    read_only_fields = fields

  def get_sale_id(self, obj: Order) -> Optional[str]:
    return str(obj.sale_id) if obj.sale_id else None

  def get_sale_number(self, obj: Order) -> Optional[int]:
    sale = getattr(obj, 'sale', None)
    return sale.number if sale else None

  def get_sale_total(self, obj: Order) -> Optional[str]:
    sale = getattr(obj, 'sale', None)
    if not sale:
      return None
    total = sale.total or Decimal('0')
    return f"{total:.2f}"

  def get_table_id(self, obj: Order) -> Optional[str]:
    return str(obj.table_id) if obj.table_id else None

  def get_subtotal_amount(self, obj: Order) -> str:
    items = getattr(obj, 'items', None)
    if items is None:
      iterable = []
    elif hasattr(items, 'all'):
      iterable = items.all()
    else:
      iterable = items
    total = sum((item.total_price for item in iterable), Decimal('0'))
    return f"{total:.2f}"


class OrderDraftItemSerializer(serializers.ModelSerializer):
  menu_item_id = serializers.UUIDField(source='menu_item_id', read_only=True)
  product_id = serializers.UUIDField(source='product_id', read_only=True)

  class Meta:
    model = OrderDraftItem
    fields = [
      'id',
      'menu_item_id',
      'product_id',
      'name',
      'note',
      'quantity',
      'unit_price',
      'total_price',
      'stock_status',
      'created_at',
      'updated_at',
    ]
    read_only_fields = fields


class OrderDraftSerializer(serializers.ModelSerializer):
  items = OrderDraftItemSerializer(many=True, read_only=True)
  table_id = serializers.SerializerMethodField()
  table_code = serializers.CharField(source='table.code', read_only=True, allow_null=True)
  status_label = serializers.CharField(source='get_status_display', read_only=True)
  channel_label = serializers.CharField(source='get_channel_display', read_only=True)

  class Meta:
    model = OrderDraft
    fields = [
      'id',
      'status',
      'status_label',
      'channel',
      'channel_label',
      'table_id',
      'table_code',
      'table_name',
      'customer_name',
      'note',
      'total_amount',
      'items_count',
      'client_reference',
      'source',
      'updated_at',
      'items',
    ]
    read_only_fields = fields

  def get_table_id(self, instance: OrderDraft) -> Optional[str]:
    return str(instance.table_id) if instance.table_id else None


class OrderDraftWriteSerializer(serializers.ModelSerializer):
  table_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

  class Meta:
    model = OrderDraft
    fields = [
      'channel',
      'table_id',
      'table_name',
      'customer_name',
      'note',
      'client_reference',
      'source',
    ]
    read_only_fields = ['source']

  def validate_table_id(self, value):
    business = self.context['business']
    if value is None:
      self.context['validated_table'] = None
      return value
    allow_assignment = self.context.get('allow_table_assignment', False)
    if not allow_assignment:
      raise serializers.ValidationError('No tenés permisos para asignar mesas.')
    table = ensure_table_available(business=business, table_id=value)
    instance = getattr(self, 'instance', None)
    conflict_qs = OrderDraft.objects.filter(
      business=business,
      status=OrderDraft.Status.EDITING,
      table=table,
    )
    if instance is not None:
      conflict_qs = conflict_qs.exclude(pk=instance.pk)
    conflict = conflict_qs.first()
    if conflict:
      raise serializers.ValidationError('La mesa ya está reservada en otro borrador.')
    self.context['validated_table'] = table
    return value

  def _apply_table(self, instance: OrderDraft, table, payload: dict):
    instance.table = table
    if table and not payload.get('table_name'):
      instance.table_name = table.name
    elif payload.get('table_name') is not None:
      instance.table_name = payload['table_name']

  def update(self, instance: OrderDraft, validated_data: dict):
    table = self.context.get('validated_table', getattr(instance, 'table', None))
    table_field_present = 'table_id' in self.initial_data
    validated_data.pop('table_id', None)
    if table_field_present and table is None:
      instance.table = None
      instance.table_name = ''
    elif table_field_present:
      self._apply_table(instance, table, validated_data)
    for field in ['channel', 'customer_name', 'note', 'client_reference', 'table_name']:
      if field in validated_data:
        setattr(instance, field, validated_data[field] or '')
    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    update_fields = ['channel', 'customer_name', 'note', 'client_reference', 'table', 'table_name', 'updated_at']
    if user and user.is_authenticated:
      instance.updated_by = user
      update_fields.append('updated_by')
    instance.save(update_fields=update_fields)
    return instance

  def create(self, validated_data: dict):
    business = self.context['business']
    table = self.context.get('validated_table')
    validated_data.pop('table_id', None)
    payload = {
      'business': business,
      'channel': validated_data.get('channel', Order.Channel.DINE_IN),
      'table': table,
      'table_name': validated_data.get('table_name') or (table.name if table else ''),
      'customer_name': validated_data.get('customer_name', ''),
      'note': validated_data.get('note', ''),
      'client_reference': validated_data.get('client_reference', ''),
      'source': validated_data.get('source', 'pos'),
    }
    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    if user and user.is_authenticated:
      payload['created_by'] = user
      payload['updated_by'] = user
    draft = OrderDraft.objects.create(**payload)
    return draft

  def to_representation(self, instance):
    return OrderDraftSerializer(instance, context=self.context).data


class OrderDraftAssignTableSerializer(serializers.Serializer):
  table_id = serializers.UUIDField(required=False, allow_null=True)
  table_name = serializers.CharField(required=False, allow_blank=True)

  def validate_table_id(self, value):
    if value is None:
      self.context['validated_table'] = None
      return value
    business = self.context['business']
    allow_assignment = self.context.get('allow_table_assignment', False)
    if not allow_assignment:
      raise serializers.ValidationError('No tenés permisos para asignar mesas.')
    table = ensure_table_available(business=business, table_id=value)
    draft: OrderDraft = self.context['draft']
    conflict = (
      OrderDraft.objects.filter(business=business, status=OrderDraft.Status.EDITING, table=table)
      .exclude(pk=draft.pk)
      .first()
    )
    if conflict:
      raise serializers.ValidationError('La mesa ya está reservada en otro borrador.')
    self.context['validated_table'] = table
    return value

  def save(self, **kwargs):
    draft: OrderDraft = self.context['draft']
    table = self.context.get('validated_table')
    table_name = self.validated_data.get('table_name')
    draft.table = table
    draft.table_name = table_name or (table.name if table else '')
    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    if user and user.is_authenticated:
      draft.updated_by = user
    update_fields = ['table', 'table_name', 'updated_at']
    if user and user.is_authenticated:
      update_fields.append('updated_by')
    draft.save(update_fields=update_fields)
    return draft


class OrderDraftItemBaseSerializer(serializers.Serializer):
  menu_item_id = serializers.UUIDField(required=False, allow_null=True)
  product_id = serializers.UUIDField(required=False, allow_null=True)
  name = serializers.CharField(required=False, allow_blank=True, max_length=255)
  note = serializers.CharField(required=False, allow_blank=True, max_length=255)
  quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
  unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

  def _resolve_menu_item(self, business, menu_item_id):
    if not menu_item_id:
      return None
    try:
      return MenuItem.objects.get(pk=menu_item_id, business=business)
    except MenuItem.DoesNotExist as exc:
      raise serializers.ValidationError({'menu_item_id': 'El producto no existe en la carta del negocio.'}) from exc

  def _resolve_product(self, business, product_id):
    if not product_id:
      return None
    try:
      return Product.objects.get(pk=product_id, business=business)
    except Product.DoesNotExist as exc:
      raise serializers.ValidationError({'product_id': 'Producto no encontrado en este negocio.'}) from exc

  def _resolve_stock_status(self, menu_item: MenuItem | None) -> str:
    if not menu_item:
      return OrderDraftItem.StockStatus.IN_STOCK
    tags = [tag.lower() for tag in menu_item.tag_list]
    if (not menu_item.is_available) or any(tag in OUT_OF_STOCK_TAGS for tag in tags):
      return OrderDraftItem.StockStatus.OUT
    if any(tag in CRITICAL_STOCK_TAGS for tag in tags):
      return OrderDraftItem.StockStatus.CRITICAL
    if any(tag in LOW_STOCK_TAGS for tag in tags):
      return OrderDraftItem.StockStatus.LOW
    return OrderDraftItem.StockStatus.IN_STOCK


class OrderDraftItemCreateSerializer(OrderDraftItemBaseSerializer):
  quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
  unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

  def validate(self, attrs):
    attrs = super().validate(attrs)
    business = self.context['business']
    draft: OrderDraft = self.context['draft']
    settings = CommercialSettings.objects.for_business(business)
    menu_item = self._resolve_menu_item(business, attrs.get('menu_item_id'))
    product = self._resolve_product(business, attrs.get('product_id'))
    stock_status = self._resolve_stock_status(menu_item)
    if stock_status == OrderDraftItem.StockStatus.OUT and not settings.allow_sell_without_stock:
      raise serializers.ValidationError({'menu_item_id': 'Este producto está sin stock.'})
    name = attrs.get('name') or (menu_item.name if menu_item else '')
    if not name:
      raise serializers.ValidationError({'name': 'El ítem necesita un nombre.'})
    quantity = attrs['quantity']
    if quantity <= 0:
      raise serializers.ValidationError({'quantity': 'La cantidad debe ser mayor a cero.'})
    unit_price = attrs.get('unit_price')
    if unit_price is None:
      unit_price = menu_item.price if menu_item else Decimal('0')
    total_price = quantity * unit_price
    attrs.update(
      {
        'menu_item': menu_item,
        'product': product,
        'name': name,
        'quantity': quantity,
        'unit_price': unit_price,
        'total_price': total_price,
        'stock_status': stock_status,
      }
    )
    self.context['draft'] = draft
    return attrs

  def create(self, validated_data):
    draft: OrderDraft = self.context['draft']
    payload = validated_data.copy()
    payload.pop('menu_item_id', None)
    payload.pop('product_id', None)
    item = OrderDraftItem.objects.create(draft=draft, **payload)
    draft.recalculate_totals()
    return item

  def to_representation(self, instance):
    return OrderDraftSerializer(instance.draft, context=self.context).data


class OrderDraftItemUpdateSerializer(OrderDraftItemBaseSerializer):
  def validate(self, attrs):
    attrs = super().validate(attrs)
    draft: OrderDraft = self.context['draft']
    business = self.context['business']
    settings = CommercialSettings.objects.for_business(business)
    menu_item = self._resolve_menu_item(business, attrs.get('menu_item_id')) if 'menu_item_id' in attrs else None
    product = self._resolve_product(business, attrs.get('product_id')) if 'product_id' in attrs else None
    if menu_item is not None:
      stock_status = self._resolve_stock_status(menu_item)
      if stock_status == OrderDraftItem.StockStatus.OUT and not settings.allow_sell_without_stock:
        raise serializers.ValidationError({'menu_item_id': 'Este producto está sin stock.'})
      attrs['menu_item'] = menu_item
      attrs['stock_status'] = stock_status
    if product is not None:
      attrs['product'] = product
    quantity = attrs.get('quantity')
    if quantity is not None and quantity <= 0:
      raise serializers.ValidationError({'quantity': 'La cantidad debe ser mayor a cero.'})
    unit_price = attrs.get('unit_price')
    if quantity is not None or unit_price is not None:
      current_quantity = quantity if quantity is not None else self.instance.quantity
      current_price = unit_price if unit_price is not None else self.instance.unit_price
      attrs['total_price'] = current_quantity * current_price
    attrs['draft'] = draft
    return attrs

  def update(self, instance: OrderDraftItem, validated_data: dict):
    for field in ['menu_item', 'product', 'name', 'note', 'quantity', 'unit_price', 'total_price', 'stock_status']:
      if field in validated_data:
        setattr(instance, field, validated_data[field])
    instance.save()
    instance.draft.recalculate_totals()
    return instance

  def to_representation(self, instance):
    return OrderDraftSerializer(instance.draft, context=self.context).data


class OrderDraftConfirmSerializer(serializers.Serializer):
  def validate(self, attrs):
    draft: OrderDraft = self.context['draft']
    if draft.status != OrderDraft.Status.EDITING:
      raise serializers.ValidationError('El borrador ya fue confirmado.')
    if draft.items_count == 0:
      raise serializers.ValidationError('Agregá al menos un ítem antes de confirmar la orden.')
    if draft.channel == Order.Channel.DINE_IN and not draft.table_id:
      raise serializers.ValidationError({'table_id': 'Seleccioná una mesa antes de confirmar.'})
    return attrs

  def save(self, **kwargs):
    draft: OrderDraft = self.context['draft']
    business = self.context['business']
    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    payload = {
      'channel': draft.channel,
      'table_id': str(draft.table_id) if draft.table_id else None,
      'table_name': draft.table_name,
      'customer_name': draft.customer_name,
      'note': draft.note,
      'items': [
        {
          'product_id': str(item.product_id) if item.product_id else None,
          'name': item.name,
          'note': item.note,
          'quantity': item.quantity,
          'unit_price': item.unit_price,
        }
        for item in draft.items.order_by('created_at')
      ],
    }
    order_serializer = OrderCreateSerializer(
      data=payload,
      context={
        'business': business,
        'request': request,
        'allow_table_assignment': True,
      },
    )
    order_serializer.is_valid(raise_exception=True)
    order = order_serializer.save()
    draft.status = OrderDraft.Status.SUBMITTED
    draft.order = order
    update_fields = ['status', 'order', 'updated_at']
    if user and getattr(user, 'is_authenticated', False):
      draft.updated_by = user
      update_fields.append('updated_by')
    draft.save(update_fields=update_fields)
    return order


class OrderStartSerializer(serializers.Serializer):
  table_id = serializers.UUIDField()
  order_id = serializers.UUIDField(required=False, allow_null=True)
  channel = serializers.ChoiceField(choices=Order.Channel.choices, default=Order.Channel.DINE_IN)
  customer_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
  note = serializers.CharField(required=False, allow_blank=True)

  def validate_table_id(self, value):
    business = self.context['business']
    table = ensure_table_available(business=business, table_id=value, allow_occupied=True)
    self.context['validated_table'] = table
    return value

  def validate_order_id(self, value):
    if value is None:
      self.context['validated_order'] = None
      return value
    business = self.context['business']
    try:
      order = Order.objects.get(pk=value, business=business)
    except Order.DoesNotExist as exc:
      raise serializers.ValidationError('La orden no existe en este negocio.') from exc
    if order.status != Order.Status.DRAFT:
      raise serializers.ValidationError('Solo podés iniciar órdenes en borrador.')
    self.context['validated_order'] = order
    return value

  def _next_order_number(self, business) -> int:
    last_number = (
      Order.objects.select_for_update()
      .filter(business=business)
      .order_by('-number')
      .values_list('number', flat=True)
      .first()
      or 0
    )
    return last_number + 1

  def save(self, **kwargs):
    business = self.context['business']
    table = self.context['validated_table']
    order = self.context.get('validated_order')
    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    payload = {
      'channel': self.validated_data.get('channel', Order.Channel.DINE_IN),
      'customer_name': self.validated_data.get('customer_name', ''),
      'note': self.validated_data.get('note', ''),
    }
    if order is None:
      number = self._next_order_number(business)
      order = Order.objects.create(
        business=business,
        number=number,
        status=Order.Status.OPEN,
        table=table,
        table_name=table.name,
        created_by=user if getattr(user, 'is_authenticated', False) else None,
        updated_by=user if getattr(user, 'is_authenticated', False) else None,
        **payload,
      )
    else:
      order.channel = payload['channel']
      order.customer_name = payload['customer_name']
      order.note = payload['note']
      order.table = table
      order.table_name = table.name
      order.status = Order.Status.OPEN
      if user and user.is_authenticated:
        order.updated_by = user
      order.save(update_fields=['channel', 'customer_name', 'note', 'table', 'table_name', 'status', 'updated_at', 'updated_by'])
    return order


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


class OrderItemBaseSerializer(serializers.Serializer):
  product_id = serializers.UUIDField(required=False, allow_null=True)
  name = serializers.CharField(max_length=255, required=False, allow_blank=True)
  note = serializers.CharField(max_length=255, required=False, allow_blank=True)
  quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
  unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
  modifiers = serializers.JSONField(required=False)
  _settings_cache: CommercialSettings | None = None

  def _resolve_product(self, business, product_id) -> Optional[Product]:
    if not product_id:
      return None
    try:
      return Product.objects.get(pk=product_id, business=business)
    except Product.DoesNotExist as exc:
      raise serializers.ValidationError({'product_id': 'Producto no encontrado en este negocio.'}) from exc

  def _get_settings(self) -> CommercialSettings:
    if self._settings_cache is not None:
      return self._settings_cache
    business = self.context['business']
    self._settings_cache = CommercialSettings.objects.for_business(business)
    return self._settings_cache

  def _normalize_name(self, value: str) -> str:
    return (value or '').strip()

  def _normalize_note(self, value: Optional[str]) -> str:
    return (value or '').strip()

  def _normalize_modifiers(self, value):
    if value in (None, ''):
      return []
    if isinstance(value, list):
      return value
    if isinstance(value, tuple):
      return list(value)
    raise serializers.ValidationError({'modifiers': 'Los modificadores deben ser una lista.'})

  def _existing_quantity(self, order: Order, product: Product, *, exclude: OrderItem | None = None) -> Decimal:
    queryset = order.items.filter(product=product)
    if exclude is not None:
      queryset = queryset.exclude(pk=exclude.pk)
    aggregated = queryset.aggregate(total=Sum('quantity'))
    return aggregated.get('total') or Decimal('0')

  def _should_flag_without_stock(self, *, order: Order, product: Product, future_total: Decimal) -> bool:
    settings = self._get_settings()
    stock_record = ensure_stock_record(order.business, product)
    remaining = stock_record.quantity - future_total
    if remaining < 0 and not settings.allow_sell_without_stock:
      raise serializers.ValidationError({'quantity': 'No hay stock suficiente para este producto.'})
    return remaining < 0

  def _modifiers_signature(self, value: list) -> str:
    try:
      return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
      return json.dumps([])

  def _find_merge_candidate(
    self,
    order: Order,
    *,
    product: Product | None,
    name: str,
    note: str,
    unit_price: Decimal,
    modifiers: list,
  ) -> OrderItem | None:
    normalized_name = self._normalize_name(name)
    normalized_note = self._normalize_note(note)
    modifiers_signature = self._modifiers_signature(modifiers)
    product_id = getattr(product, 'id', None)
    for item in order.items.all():
      if getattr(item.product, 'id', None) != product_id:
        continue
      if self._normalize_name(item.name) != normalized_name:
        continue
      if self._normalize_note(item.note) != normalized_note:
        continue
      if Decimal(item.unit_price) != unit_price:
        continue
      if self._modifiers_signature(item.modifiers or []) != modifiers_signature:
        continue
      return item
    return None


class OrderItemCreateSerializer(OrderItemBaseSerializer):
  quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
  unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

  def validate(self, attrs):
    attrs = super().validate(attrs)
    business = self.context['business']
    order: Order = self.context['order']
    product = self._resolve_product(business, attrs.get('product_id'))
    name = self._normalize_name(attrs.get('name') or (product.name if product else ''))
    if not name:
      raise serializers.ValidationError({'name': 'El ítem necesita un nombre.'})
    quantity = attrs['quantity']
    if quantity <= 0:
      raise serializers.ValidationError({'quantity': 'La cantidad debe ser mayor a cero.'})
    unit_price = attrs.get('unit_price')
    if unit_price is None:
      unit_price = product.price if product else Decimal('0')
    total_price = quantity * unit_price
    note = self._normalize_note(attrs.get('note'))
    modifiers = self._normalize_modifiers(attrs.get('modifiers'))
    sold_without_stock = False
    if product is not None:
      current_quantity = self._existing_quantity(order, product)
      future_total = current_quantity + quantity
      sold_without_stock = self._should_flag_without_stock(order=order, product=product, future_total=future_total)
    attrs.update(
      {
        'product': product,
        'name': name,
        'note': note,
        'quantity': quantity,
        'unit_price': unit_price,
        'total_price': total_price,
        'modifiers': modifiers,
        'sold_without_stock': sold_without_stock,
      }
    )
    return attrs

  def create(self, validated_data):
    order: Order = self.context['order']
    payload = validated_data.copy()
    payload.pop('product_id', None)
    product = payload.get('product')
    merge_candidate = self._find_merge_candidate(
      order,
      product=product,
      name=payload['name'],
      note=payload.get('note', ''),
      unit_price=payload['unit_price'],
      modifiers=payload.get('modifiers') or [],
    )
    if merge_candidate:
      merge_candidate.quantity += payload['quantity']
      merge_candidate.total_price += payload['total_price']
      if payload.get('sold_without_stock'):
        merge_candidate.sold_without_stock = True
      merge_candidate.save(update_fields=['quantity', 'total_price', 'sold_without_stock'])
      order.recalculate_totals()
      return merge_candidate
    item = OrderItem.objects.create(order=order, **payload)
    order.recalculate_totals()
    return item


class OrderItemUpdateSerializer(OrderItemBaseSerializer):
  def validate(self, attrs):
    attrs = super().validate(attrs)
    business = self.context['business']
    order: Order = self.context['order']
    if 'product_id' in attrs:
      attrs['product'] = self._resolve_product(business, attrs.get('product_id'))
    product = attrs.get('product', self.instance.product)
    name = self._normalize_name(attrs.get('name', self.instance.name))
    note = self._normalize_note(attrs.get('note', self.instance.note))
    quantity = attrs.get('quantity', self.instance.quantity)
    if quantity is not None and quantity <= 0:
      raise serializers.ValidationError({'quantity': 'La cantidad debe ser mayor a cero.'})
    unit_price = attrs.get('unit_price', self.instance.unit_price)
    attrs['total_price'] = quantity * unit_price
    modifiers = self._normalize_modifiers(attrs.get('modifiers', self.instance.modifiers))
    sold_without_stock = False
    if product is not None:
      current_quantity = self._existing_quantity(order, product, exclude=self.instance)
      future_total = current_quantity + quantity
      sold_without_stock = self._should_flag_without_stock(order=order, product=product, future_total=future_total)
    attrs.update(
      {
        'product': product,
        'name': name,
        'note': note,
        'quantity': quantity,
        'unit_price': unit_price,
        'modifiers': modifiers,
        'sold_without_stock': sold_without_stock,
      }
    )
    return attrs

  def update(self, instance: OrderItem, validated_data: dict):
    for field in ['product', 'name', 'note', 'quantity', 'unit_price', 'total_price', 'modifiers', 'sold_without_stock']:
      if field in validated_data:
        setattr(instance, field, validated_data[field])
    instance.save()
    instance.order.recalculate_totals()
    return instance


class OrderUpdateSerializer(serializers.Serializer):
  channel = serializers.ChoiceField(choices=Order.Channel.choices, required=False)
  table_id = serializers.UUIDField(required=False, allow_null=True)
  table_name = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
  customer_name = serializers.CharField(max_length=128, required=False, allow_blank=True, allow_null=True)
  note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    initial = getattr(self, 'initial_data', None)
    self._table_field_present = isinstance(initial, dict) and 'table_id' in initial

  def validate_table_id(self, value):
    if not self._table_field_present:
      return value
    if value is None:
      self.context['validated_table'] = None
      return value
    business = self.context['business']
    order: Order = self.context['order']
    allow_assignment = self.context.get('allow_table_assignment', False)
    if not allow_assignment:
      raise serializers.ValidationError('No tenés permisos para asignar mesas.')
    table = ensure_table_available(
      business=business,
      table_id=value,
      ignore_order_id=order.id,
    )
    self.context['validated_table'] = table
    return value

  def validate(self, attrs):
    attrs = super().validate(attrs)
    order: Order = self.context['order']
    if order.status not in EDITABLE_ORDER_STATUSES:
      raise serializers.ValidationError('No podés modificar esta orden en su estado actual.')
    return attrs

  def _set_field(self, order: Order, dirty_fields: set[str], field: str, value):
    if getattr(order, field) != value:
      setattr(order, field, value)
      dirty_fields.add(field)

  def save(self, **kwargs):
    order: Order = self.context['order']
    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    dirty_fields: set[str] = set()

    if 'channel' in self.validated_data:
      self._set_field(order, dirty_fields, 'channel', self.validated_data['channel'])

    if 'customer_name' in self.validated_data:
      customer_name = (self.validated_data.get('customer_name') or '').strip()
      self._set_field(order, dirty_fields, 'customer_name', customer_name)

    if 'note' in self.validated_data:
      note = (self.validated_data.get('note') or '').strip()
      self._set_field(order, dirty_fields, 'note', note)

    table = self.context.get('validated_table') if self._table_field_present else order.table
    if self._table_field_present:
      self._set_field(order, dirty_fields, 'table', table)
      if table is None:
        self._set_field(order, dirty_fields, 'table_name', '')
      elif 'table_name' not in self.validated_data or (self.validated_data.get('table_name') or '').strip() == '':
        self._set_field(order, dirty_fields, 'table_name', table.name)

    if 'table_name' in self.validated_data:
      table_name = (self.validated_data.get('table_name') or '').strip()
      self._set_field(order, dirty_fields, 'table_name', table_name)

    if user and getattr(user, 'is_authenticated', False):
      order.updated_by = user
      dirty_fields.add('updated_by')

    if dirty_fields:
      dirty_fields.add('updated_at')
      order.save(update_fields=list(dirty_fields))
    return order

  def to_representation(self, instance):
    return OrderSerializer(instance, context=self.context).data


class OrderCreateSerializer(serializers.Serializer):
  channel = serializers.ChoiceField(choices=Order.Channel.choices, default=Order.Channel.DINE_IN)
  table_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
  table_id = serializers.UUIDField(required=False, allow_null=True)
  customer_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
  note = serializers.CharField(required=False, allow_blank=True)
  items = OrderItemInputSerializer(many=True)

  def validate_items(self, value: List[dict]) -> List[dict]:
    if not value:
      raise serializers.ValidationError('Agregá al menos un item a la orden.')
    return value

  def validate_table_id(self, value):
    if value is None:
      self.context['validated_table'] = None
      return value
    allow_assignment = self.context.get('allow_table_assignment', False)
    if not allow_assignment:
      raise serializers.ValidationError('No tenes permisos para asignar mesas.')
    business = self.context['business']
    table = ensure_table_available(business=business, table_id=value)
    self.context['validated_table'] = table
    return value

  def _resolve_product(self, business, product_id) -> Optional[Product]:
    if not product_id:
      return None
    try:
      return Product.objects.get(pk=product_id, business=business)
    except Product.DoesNotExist as exc:
      raise serializers.ValidationError('Producto no encontrado en este negocio.') from exc

  def validate(self, attrs):
    attrs = super().validate(attrs)
    channel = attrs.get('channel', Order.Channel.DINE_IN)
    table = self.context.get('validated_table')
    if channel == Order.Channel.DINE_IN and table is None:
      raise serializers.ValidationError({'table_id': 'Seleccioná una mesa para órdenes de salón.'})
    attrs['table'] = table
    return attrs

  @transaction.atomic
  def create(self, validated_data):
    business = self.context['business']
    request = self.context.get('request')
    created_by = getattr(request, 'user', None) if request else None
    table = validated_data.pop('table', None)

    last_number = (
      Order.objects.select_for_update()
      .filter(business=business)
      .order_by('-number')
      .values_list('number', flat=True)
      .first()
    ) or 0
    raw_table_name = (validated_data.get('table_name') or '').strip()
    if table and not raw_table_name:
      raw_table_name = table.name
    order = Order.objects.create(
      business=business,
      number=last_number + 1,
      channel=validated_data.get('channel', Order.Channel.DINE_IN),
      table=table,
      table_name=raw_table_name,
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

  def __init__(self, *args, **kwargs):
    self._excluded_statuses = set(kwargs.pop('exclude_statuses', []) or [])
    super().__init__(*args, **kwargs)
    if self._excluded_statuses:
      allowed = [choice for choice in Order.Status.choices if choice[0] not in self._excluded_statuses]
      self.fields['status'].choices = allowed


class OrderSaleMixin(serializers.Serializer):
  def __init__(self, *args, **kwargs):
    self._settings: Optional[CommercialSettings] = None
    super().__init__(*args, **kwargs)

  def _get_settings(self) -> CommercialSettings:
    if self._settings is not None:
      return self._settings
    business = self.context['business']
    self._settings = CommercialSettings.objects.for_business(business)
    return self._settings

  def _build_error(self, code: str, message: str, **extra):
    payload = {'code': code, 'message': message}
    payload.update({key: value for key, value in extra.items()})
    return serializers.ValidationError({'error': payload})

  def _out_of_stock_error(self, *, product: Product, available: Decimal, requested: Decimal):
    return self._build_error(
      'OUT_OF_STOCK',
      'No hay stock suficiente para vender este producto.',
      product_id=str(product.id),
      available_stock=f"{available}",
      requested_qty=f"{requested}",
    )

  def _register_stock(self, *, order: Order, item: OrderItem, user, allow_without_stock: bool):
    product = item.product
    if product is None:
      return
    stock_record = ensure_stock_record(order.business, product)
    available_quantity = stock_record.quantity
    quantity = item.quantity
    will_be_negative = (available_quantity - quantity) < 0
    movement_kwargs: dict = {}
    if will_be_negative and not allow_without_stock:
      raise self._out_of_stock_error(product=product, available=available_quantity, requested=quantity)
    if will_be_negative and allow_without_stock:
      movement_kwargs = {
        'reason': 'SALE_ALLOW_NO_STOCK',
        'metadata': {
          'allowed_without_stock': True,
          'product_id': str(product.id),
          'available_stock': f"{available_quantity}",
          'requested_qty': f"{quantity}",
        },
        'allow_negative_stock': True,
      }
    register_stock_movement(
      business=order.business,
      product=product,
      movement_type=StockMovement.MovementType.OUT,
      quantity=quantity,
      note=f'Orden #{order.number}',
      created_by=user if getattr(user, 'is_authenticated', False) else None,
      **movement_kwargs,
    )

  def _ensure_items(self, order: Order) -> list[OrderItem]:
    items = list(order.items.select_related('product').order_by('created_at'))
    if not items:
      raise serializers.ValidationError('La orden no tiene ítems para cobrar.')
    return items

  def validate_customer_id(self, value):
    if value is None:
      self.context['customer'] = None
      return value
    business = self.context['business']
    try:
      customer = Customer.objects.get(pk=value, business=business)
    except Customer.DoesNotExist as exc:
      raise serializers.ValidationError('Cliente no encontrado en este negocio.') from exc
    self.context['customer'] = customer
    return value

  def validate_discount(self, value: Decimal) -> Decimal:
    settings = self._get_settings()
    allow_negative = settings.allow_negative_price_or_discount
    if value < 0 and not allow_negative:
      raise serializers.ValidationError('El descuento no puede ser negativo.')
    return value

  def _validate_totals(self, *, subtotal: Decimal, discount: Decimal) -> Decimal:
    settings = self._get_settings()
    allow_negative = settings.allow_negative_price_or_discount
    if discount > subtotal and not allow_negative:
      raise serializers.ValidationError({'discount': 'El descuento no puede ser mayor al subtotal.'})
    total = subtotal - discount
    if total < 0 and not allow_negative:
      raise serializers.ValidationError({'discount': 'El total no puede ser negativo.'})
    return total

  def _create_sale(
    self,
    *,
    order: Order,
    customer,
    cash_session: CashSession | None,
    payment_method: str,
    discount: Decimal,
    notes: Optional[str],
  ) -> Sale:
    items = self._ensure_items(order)
    subtotal = sum((item.total_price for item in items), Decimal('0'))
    total = self._validate_totals(subtotal=subtotal, discount=discount)
    business = self.context['business']
    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    settings = self._get_settings()
    allow_without_stock = settings.allow_sell_without_stock
    normalized_notes = (notes or order.note or '').strip()

    with transaction.atomic():
      last_number = (
        Sale.objects.select_for_update()
        .filter(business=business)
        .order_by('-number')
        .values_list('number', flat=True)
        .first()
        or 0
      )

      sale = Sale.objects.create(
        business=business,
        customer=customer,
        number=last_number + 1,
        status=Sale.Status.COMPLETED,
        payment_method=payment_method or Sale.PaymentMethod.CASH,
        notes=normalized_notes,
        created_by=user if getattr(user, 'is_authenticated', False) else None,
        cash_session=cash_session,
      )

      sale_items: list[SaleItem] = []
      for item in items:
        sale_items.append(
          SaleItem(
            sale=sale,
            product=item.product,
            product_name_snapshot=item.name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.total_price,
          )
        )
        self._register_stock(order=order, item=item, user=user, allow_without_stock=allow_without_stock)

      SaleItem.objects.bulk_create(sale_items)
      sale.subtotal = subtotal
      sale.discount = discount
      sale.total = total
      sale.save(update_fields=['subtotal', 'discount', 'total', 'updated_at'])

      order.sale = sale
      order.total_amount = total
      update_fields = ['sale', 'total_amount', 'updated_at']
      if getattr(user, 'is_authenticated', False):
        order.updated_by = user
        update_fields.append('updated_by')
      order.save(update_fields=update_fields)

    return sale

  def _update_existing_sale(
    self,
    sale: Sale,
    *,
    order: Order,
    payment_method: str,
    discount: Decimal,
    notes: Optional[str],
  ) -> Sale:
    subtotal = sale.subtotal or Decimal('0')
    total = self._validate_totals(subtotal=subtotal, discount=discount)
    dirty_fields: list[str] = []
    if payment_method and sale.payment_method != payment_method:
      sale.payment_method = payment_method
      dirty_fields.append('payment_method')
    if sale.discount != discount or sale.total != total:
      sale.discount = discount
      sale.total = total
      dirty_fields.extend(['discount', 'total'])
    if notes is not None:
      normalized_notes = (notes or '').strip()
      if normalized_notes != (sale.notes or ''):
        sale.notes = normalized_notes
        dirty_fields.append('notes')
    if dirty_fields:
      dirty_fields.append('updated_at')
      sale.save(update_fields=dirty_fields)
    if order.total_amount != total:
      request = self.context.get('request')
      user = getattr(request, 'user', None) if request else None
      order.total_amount = total
      update_fields = ['total_amount', 'updated_at']
      if getattr(user, 'is_authenticated', False):
        order.updated_by = user
        update_fields.append('updated_by')
      order.save(update_fields=update_fields)
    return sale


class OrderCloseSerializer(OrderSaleMixin):
  payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices, default=Sale.PaymentMethod.CASH)
  discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0'))
  notes = serializers.CharField(required=False, allow_blank=True)
  customer_id = serializers.UUIDField(required=False, allow_null=True)
  cash_session_id = serializers.UUIDField(required=False, allow_null=True)

  def validate_cash_session_id(self, value):
    if value is None:
      self.context['cash_session'] = None
      return value
    business = self.context['business']
    try:
      session = CashSession.objects.get(pk=value, business=business)
    except CashSession.DoesNotExist as exc:
      raise serializers.ValidationError('La sesión de caja no existe en este negocio.') from exc
    if session.status != CashSession.Status.OPEN:
      raise serializers.ValidationError('Esta sesión de caja ya está cerrada.')
    self.context['cash_session'] = session
    return value

  def validate(self, attrs):
    attrs = super().validate(attrs)
    order: Order = self.context['order']
    if order.sale_id:
      raise serializers.ValidationError('La orden ya fue cobrada.')
    if order.status == Order.Status.CANCELLED:
      raise serializers.ValidationError('No podés cobrar una orden cancelada.')
    item_exists = order.items.exists()
    if not item_exists:
      raise serializers.ValidationError('La orden no tiene ítems para cobrar.')
    settings = self._get_settings()
    if settings.require_customer_for_sales and self.context.get('customer') is None:
      raise self._build_error('CUSTOMER_REQUIRED', 'Debes seleccionar un cliente para cobrar la orden.')
    if settings.block_sales_if_no_open_cash_session and self.context.get('cash_session') is None:
      raise self._build_error('CASH_SESSION_REQUIRED', 'Necesitás abrir una sesión de caja para cobrar la orden.')
    return attrs

  @transaction.atomic
  def save(self, **kwargs):
    order: Order = self.context['order']
    customer = self.context.get('customer')
    cash_session = self.context.get('cash_session')
    payment_method = self.validated_data.get('payment_method') or Sale.PaymentMethod.CASH
    discount = self.validated_data.get('discount') or Decimal('0')
    notes = self.validated_data.get('notes')

    sale = self._create_sale(
      order=order,
      customer=customer,
      cash_session=cash_session,
      payment_method=payment_method,
      discount=discount,
      notes=notes,
    )

    request = self.context.get('request')
    user = getattr(request, 'user', None) if request else None
    order.status = Order.Status.PAID
    order.closed_at = timezone.now()
    update_fields = ['status', 'closed_at', 'updated_at']
    if getattr(user, 'is_authenticated', False):
      order.updated_by = user
      update_fields.append('updated_by')
    order.save(update_fields=update_fields)
    self.instance = order
    return order


class OrderCreateSaleSerializer(OrderSaleMixin):
  payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices, default=Sale.PaymentMethod.CASH)
  discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0'))
  notes = serializers.CharField(required=False, allow_blank=True)
  customer_id = serializers.UUIDField(required=False, allow_null=True)

  def validate(self, attrs):
    attrs = super().validate(attrs)
    order: Order = self.context['order']
    if order.status == Order.Status.CANCELLED:
      raise serializers.ValidationError('No podés cobrar una orden cancelada.')
    return attrs

  @transaction.atomic
  def save(self, **kwargs):
    order: Order = self.context['order']
    customer = self.context.get('customer')
    payment_method = self.validated_data.get('payment_method') or Sale.PaymentMethod.CASH
    discount = self.validated_data.get('discount') or Decimal('0')
    notes = self.validated_data.get('notes')

    if order.sale_id:
      sale = self._update_existing_sale(
        order.sale,
        order=order,
        payment_method=payment_method,
        discount=discount,
        notes=notes,
      )
    else:
      sale = self._create_sale(
        order=order,
        customer=customer,
        cash_session=None,
        payment_method=payment_method,
        discount=discount,
        notes=notes,
      )
    self.instance = sale
    return sale


class OrderPaymentLineSerializer(serializers.Serializer):
  method = serializers.ChoiceField(choices=Payment.Method.choices, default=Payment.Method.CASH)
  amount = serializers.DecimalField(max_digits=12, decimal_places=2)
  reference = serializers.CharField(required=False, allow_blank=True, max_length=128)

  def validate_amount(self, value: Decimal) -> Decimal:
    if value <= 0:
      raise serializers.ValidationError('El monto debe ser mayor a cero.')
    return value


class OrderPaySerializer(serializers.Serializer):
  payments = OrderPaymentLineSerializer(many=True)
  cash_session_id = serializers.UUIDField(required=False, allow_null=True)

  def validate(self, attrs):
    attrs = super().validate(attrs)
    payments = attrs.get('payments') or []
    if not payments:
      raise serializers.ValidationError({'payments': 'Agregá al menos un pago para confirmar.'})
    return attrs
