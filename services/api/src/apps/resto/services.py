from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Dict, Optional

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.orders.models import Order
from .models import Table, TableLayout, TablePlacement

ACTIVE_TABLE_ORDER_STATUSES = {
  Order.Status.OPEN,
  Order.Status.SENT,
}


def ensure_table_available(*, business, table_id, allow_occupied=False, ignore_order_id=None) -> Table:
  try:
    table = Table.objects.get(pk=table_id, business=business)
  except Table.DoesNotExist as exc:
    raise serializers.ValidationError({'table_id': 'La mesa no existe en este negocio.'}) from exc

  if not table.is_enabled:
    raise serializers.ValidationError({'table_id': 'La mesa está deshabilitada.'})

  if allow_occupied:
    return table

  conflict_qs = Order.objects.filter(business=business, table=table, status__in=ACTIVE_TABLE_ORDER_STATUSES)
  if ignore_order_id:
    conflict_qs = conflict_qs.exclude(pk=ignore_order_id)

  conflict = conflict_qs.order_by('-opened_at').first()
  if conflict:
    raise serializers.ValidationError({'table_id': f"La mesa está ocupada por la orden #{conflict.number}."})

  return table


def get_or_create_layout(business) -> TableLayout:
  layout, _created = TableLayout.objects.get_or_create(
    business=business,
    defaults={'grid_cols': 12, 'grid_rows': 8},
  )
  return layout


def build_table_status_map(business):
  tables = Table.objects.filter(business=business).order_by('code')
  status_map = {}
  for table in tables:
    if not table.is_enabled:
      base_status = 'DISABLED'
    elif table.is_paused:
      base_status = 'PAUSED'
    else:
      base_status = 'FREE'

    status_map[str(table.id)] = {
      'status': base_status,
      'isPaused': table.is_paused,
      'isEnabled': table.is_enabled,
    }

  active_orders = (
    Order.objects.filter(business=business, table__isnull=False, status__in=ACTIVE_TABLE_ORDER_STATUSES)
    .select_related('table')
    .order_by('-opened_at')
  )
  for order in active_orders:
    if not order.table_id:
      continue
    status_map[str(order.table_id)] = {
      'status': 'OCCUPIED',
      'orderId': str(order.id),
      'orderNumber': order.number,
      'orderStatus': order.status,
      'orderStatusLabel': order.get_status_display(),
      'isPaused': status_map.get(str(order.table_id), {}).get('isPaused', False),
      'isEnabled': True,
    }

  return status_map


def apply_table_configuration(*, business, tables_data, layout_data):
  with transaction.atomic():
    existing_tables = {str(table.id): table for table in Table.objects.filter(business=business)}
    seen_ids: set[str] = set()
    updated_instances: list[Table] = []

    for entry in tables_data:
      table_id = str(entry.get('id') or uuid.uuid4())
      seen_ids.add(table_id)
      fields = {
        'code': entry['code'],
        'name': entry['name'],
        'capacity': entry.get('capacity'),
        'area': entry.get('area', ''),
        'notes': entry.get('notes', ''),
        'is_enabled': entry.get('is_enabled', True),
        'is_paused': entry.get('is_paused', False),
      }

      instance = existing_tables.get(table_id)
      if instance is None:
        instance = Table.objects.create(id=table_id, business=business, **fields)
      else:
        for field, value in fields.items():
          setattr(instance, field, value)
        instance.save(update_fields=[*fields.keys(), 'updated_at'])
      updated_instances.append(instance)

    for table in Table.objects.filter(business=business):
      if str(table.id) not in seen_ids:
        table.delete()

    layout = get_or_create_layout(business)
    layout.grid_cols = layout_data['grid_cols']
    layout.grid_rows = layout_data['grid_rows']
    layout.save(update_fields=['grid_cols', 'grid_rows', 'updated_at'])
    layout.placements.all().delete()

    placements = []
    table_map = {str(table.id): table for table in Table.objects.filter(business=business)}
    for placement in layout_data['placements']:
      table_id = str(placement['table_id'])
      table = table_map.get(table_id)
      if table is None:
        raise serializers.ValidationError({'layout': f'Mesa no encontrada para ubicar: {table_id}.'})
      placements.append(
        TablePlacement(
          business=business,
          layout=layout,
          table=table,
          x=placement['x'],
          y=placement['y'],
          w=placement.get('w', 1),
          h=placement.get('h', 1),
          rotation=placement.get('rotation', 0),
          z_index=placement.get('z_index', 0),
        )
      )

    if placements:
      TablePlacement.objects.bulk_create(placements)

  refreshed_layout = get_or_create_layout(business)
  refreshed_tables = Table.objects.filter(business=business).order_by('code')
  return refreshed_tables, refreshed_layout


def _placement_to_position(*, placement: TablePlacement, layout: TableLayout) -> Dict[str, float]:
  cols = max(layout.grid_cols, 1)
  rows = max(layout.grid_rows, 1)

  def _percent(value: Decimal) -> float:
    return float(max(0, min(100, round(value, 4))))

  width_ratio = Decimal(placement.w or 1) / Decimal(cols)
  height_ratio = Decimal(placement.h or 1) / Decimal(rows)
  left_ratio = Decimal(max(placement.x - 1, 0)) / Decimal(cols)
  top_ratio = Decimal(max(placement.y - 1, 0)) / Decimal(rows)

  return {
    'x': _percent(left_ratio * 100),
    'y': _percent(top_ratio * 100),
    'w': _percent(width_ratio * 100),
    'h': _percent(height_ratio * 100),
    'rotation': placement.rotation,
    'z_index': placement.z_index,
  }


def _serialize_active_order(order: Optional[Order]):
  if not order:
    return None
  return {
    'id': str(order.id),
    'number': order.number,
    'status': order.status,
    'status_label': order.get_status_display(),
    'total': str(order.total_amount or Decimal('0')),
    'updated_at': order.updated_at.isoformat() if order.updated_at else None,
  }


def _derive_table_state(*, table: Table, active_order: Optional[Order]) -> str:
  if not table.is_enabled:
    return 'DISABLED'
  if active_order is not None:
    return 'OCCUPIED'
  if table.is_paused:
    return 'PAUSED'
  return 'FREE'


def build_tables_map_state_payload(business):
  layout = get_or_create_layout(business)
  placements = {placement.table_id: placement for placement in layout.placements.select_related('table').all()}
  tables = list(Table.objects.filter(business=business).order_by('code', 'name'))

  active_orders = (
    Order.objects.filter(business=business, table__isnull=False, status__in=ACTIVE_TABLE_ORDER_STATUSES)
    .select_related('table')
    .order_by('-opened_at')
  )
  order_map: Dict[uuid.UUID, Order] = {}
  for order in active_orders:
    if order.table_id and order.table_id not in order_map:
      order_map[order.table_id] = order

  items = []
  for table in tables:
    placement = placements.get(table.id)
    active_order = order_map.get(table.id)
    position_payload = None
    if placement:
      position_payload = _placement_to_position(placement=placement, layout=layout)
      position_payload['grid'] = {
        'x': placement.x,
        'y': placement.y,
        'w': placement.w,
        'h': placement.h,
      }

    items.append(
      {
        'id': str(table.id),
        'code': table.code,
        'name': table.name,
        'capacity': table.capacity,
        'area': table.area,
        'notes': table.notes,
        'is_enabled': table.is_enabled,
        'is_paused': table.is_paused,
        'position': position_payload,
        'active_order': _serialize_active_order(active_order),
        'state': _derive_table_state(table=table, active_order=active_order),
      }
    )

  return {
    'server_time': timezone.now().isoformat(),
    'layout': {
      'gridCols': layout.grid_cols,
      'gridRows': layout.grid_rows,
    },
    'tables': items,
  }


def build_tables_configuration_payload(business):
  layout = get_or_create_layout(business)
  placements = {placement.table_id: placement for placement in layout.placements.select_related('table').all()}
  tables = list(Table.objects.filter(business=business).order_by('code', 'name'))

  items = []
  for table in tables:
    placement = placements.get(table.id)
    items.append(
      {
        'id': str(table.id),
        'code': table.code,
        'name': table.name,
        'capacity': table.capacity,
        'area': table.area,
        'notes': table.notes,
        'is_enabled': table.is_enabled,
        'is_paused': table.is_paused,
        'position': _placement_to_position(placement=placement, layout=layout) if placement else None,
      }
    )

  return {
    'layout': {
      'gridCols': layout.grid_cols,
      'gridRows': layout.grid_rows,
    },
    'tables': items,
  }
