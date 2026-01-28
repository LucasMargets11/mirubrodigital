from __future__ import annotations

import uuid

from rest_framework import serializers

from apps.orders.models import Order
from apps.resto.services import ensure_table_available

from .models import Table, TableLayout


class TableSerializer(serializers.ModelSerializer):
	computed_status = serializers.SerializerMethodField()
	active_order_id = serializers.SerializerMethodField()
	active_order_number = serializers.SerializerMethodField()

	class Meta:
		model = Table
		fields = [
			'id',
			'code',
			'name',
			'capacity',
			'area',
			'notes',
			'is_enabled',
			'is_paused',
			'computed_status',
			'active_order_id',
			'active_order_number',
		]
		read_only_fields = fields

	def _get_status_payload(self, table: Table) -> dict:
		status_map = self.context.get('status_map') or {}
		return status_map.get(str(table.id), {})

	def get_computed_status(self, table: Table) -> str:
		payload = self._get_status_payload(table)
		return payload.get('status', 'DISABLED' if not table.is_enabled else 'FREE')

	def get_active_order_id(self, table: Table):
		payload = self._get_status_payload(table)
		return payload.get('orderId')

	def get_active_order_number(self, table: Table):
		payload = self._get_status_payload(table)
		return payload.get('orderNumber')


class TableLayoutSerializer(serializers.ModelSerializer):
	gridCols = serializers.IntegerField(source='grid_cols', read_only=True)
	gridRows = serializers.IntegerField(source='grid_rows', read_only=True)
	placements = serializers.SerializerMethodField()

	class Meta:
		model = TableLayout
		fields = ['id', 'gridCols', 'gridRows', 'placements']
		read_only_fields = ['id', 'gridCols', 'gridRows', 'placements']

	def get_placements(self, obj: TableLayout):
		data = []
		for placement in obj.placements.select_related('table').all().order_by('table__code'):
			data.append(
				{
					'id': str(placement.id),
					'tableId': str(placement.table_id),
					'x': placement.x,
					'y': placement.y,
					'w': placement.w,
					'h': placement.h,
					'rotation': placement.rotation,
					'zIndex': placement.z_index,
					'tableCode': placement.table.code if placement.table else None,
				}
			)
		return data


class OrderTableAssignmentSerializer(serializers.Serializer):
	table_id = serializers.UUIDField()

	def validate_table_id(self, value):
		business = self.context['business']
		order: Order = self.context['order']
		table = ensure_table_available(
			business=business,
			table_id=value,
			ignore_order_id=order.id,
		)
		self.context['validated_table'] = table
		return value

	def save(self, **kwargs):
		order: Order = self.context['order']
		table = self.context['validated_table']
		order.table = table
		order.table_name = table.name
		order.save(update_fields=['table', 'table_name', 'updated_at'])
		return order


class TableSettingsSerializer(serializers.ModelSerializer):
	class Meta:
		model = Table
		fields = ['id', 'code', 'name', 'capacity', 'area', 'notes', 'is_enabled', 'is_paused']
		read_only_fields = fields


class TableConfigTableSerializer(serializers.Serializer):
	id = serializers.UUIDField(required=False)
	code = serializers.CharField(max_length=16)
	name = serializers.CharField(max_length=120)
	capacity = serializers.IntegerField(required=False, allow_null=True, min_value=1)
	is_enabled = serializers.BooleanField(default=True)
	is_paused = serializers.BooleanField(default=False)
	area = serializers.CharField(required=False, allow_blank=True, max_length=64)
	notes = serializers.CharField(required=False, allow_blank=True, max_length=255)

	def validate_code(self, value):
		clean = value.strip()
		if not clean:
			raise serializers.ValidationError('Ingresá un código para la mesa.')
		return clean

	def validate_name(self, value):
		clean = value.strip()
		if not clean:
			raise serializers.ValidationError('Ingresá un nombre para la mesa.')
		return clean


class TablePlacementConfigSerializer(serializers.Serializer):
	tableId = serializers.UUIDField(source='table_id')
	x = serializers.IntegerField(min_value=1, max_value=64)
	y = serializers.IntegerField(min_value=1, max_value=64)
	w = serializers.IntegerField(required=False, min_value=1, max_value=8, default=1)
	h = serializers.IntegerField(required=False, min_value=1, max_value=8, default=1)
	rotation = serializers.IntegerField(required=False, default=0)
	zIndex = serializers.IntegerField(source='z_index', required=False, default=0)


class TableLayoutConfigSerializer(serializers.Serializer):
	gridCols = serializers.IntegerField(source='grid_cols', min_value=4, max_value=32)
	gridRows = serializers.IntegerField(source='grid_rows', min_value=4, max_value=32)
	placements = TablePlacementConfigSerializer(many=True)


class TableConfigurationWriteSerializer(serializers.Serializer):
	tables = TableConfigTableSerializer(many=True)
	layout = TableLayoutConfigSerializer()

	def validate(self, attrs):
		tables = attrs.get('tables', [])
		codes = set()
		ids = set()
		for table in tables:
			if not table.get('id'):
				new_id = uuid.uuid4()
				table['id'] = new_id
				table_id_value = new_id
			else:
				table_id_value = table['id']
			code_key = table['code'].strip().lower()
			if code_key in codes:
				raise serializers.ValidationError({'tables': 'Los códigos deben ser únicos.'})
			codes.add(code_key)
			ids.add(str(table_id_value))

		layout = attrs.get('layout')
		if layout:
			placement_ids = {str(item['table_id']) for item in layout['placements']}
			missing = placement_ids - ids
			if missing:
				raise serializers.ValidationError({'layout': f'Las ubicaciones hacen referencia a mesas desconocidas: {", ".join(sorted(missing))}.'})
		return attrs
