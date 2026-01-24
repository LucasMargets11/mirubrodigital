from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.catalog.models import Product
from apps.catalog.serializers import ProductSummarySerializer
from .models import InventoryImportJob, ProductStock, StockMovement
from .services import register_stock_movement


class ProductStockSerializer(serializers.ModelSerializer):
  product = ProductSummarySerializer(read_only=True)
  status = serializers.SerializerMethodField()

  class Meta:
    model = ProductStock
    fields = ['id', 'product', 'quantity', 'status', 'updated_at']
    read_only_fields = fields

  def get_status(self, obj: ProductStock) -> str:
    if obj.quantity <= 0:
      return 'out'
    if obj.quantity < obj.product.stock_min:
      return 'low'
    return 'ok'


class StockMovementSerializer(serializers.ModelSerializer):
  product = ProductSummarySerializer(read_only=True)

  class Meta:
    model = StockMovement
    fields = ['id', 'product', 'movement_type', 'quantity', 'note', 'created_at']
    read_only_fields = fields


class StockMovementCreateSerializer(serializers.Serializer):
  product_id = serializers.UUIDField()
  movement_type = serializers.ChoiceField(choices=StockMovement.MovementType.choices)
  quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
  note = serializers.CharField(allow_blank=True, required=False)

  def validate_quantity(self, value: Decimal) -> Decimal:
    if value <= 0:
      raise serializers.ValidationError('La cantidad debe ser mayor a cero.')
    return value

  def validate_product_id(self, value):
    request = self.context['request']
    business = getattr(request, 'business', None)
    try:
      product = Product.objects.get(pk=value, business=business)
    except Product.DoesNotExist as exc:
      raise serializers.ValidationError('Producto no encontrado en este negocio.') from exc
    self.context['product'] = product
    return value

  def create(self, validated_data):
    request = self.context['request']
    business = getattr(request, 'business')
    product = self.context['product']
    note = validated_data.get('note', '')
    try:
      movement, _ = register_stock_movement(
        business=business,
        product=product,
        movement_type=validated_data['movement_type'],
        quantity=validated_data['quantity'],
        note=note,
        created_by=request.user,
      )
    except DjangoValidationError as exc:
      message = getattr(exc, 'message', None) or '; '.join(exc.messages)
      raise serializers.ValidationError({'detail': message}) from exc
    return movement

  def to_representation(self, instance):
    return StockMovementSerializer(instance).data


class InventoryImportJobSerializer(serializers.ModelSerializer):
  summary = serializers.SerializerMethodField()
  result_url = serializers.SerializerMethodField()

  class Meta:
    model = InventoryImportJob
    fields = [
      'id',
      'filename',
      'status',
      'summary',
      'created_count',
      'updated_count',
      'adjusted_count',
      'skipped_count',
      'error_count',
      'warning_count',
      'result_url',
      'errors',
      'created_at',
      'updated_at',
    ]
    read_only_fields = fields

  def get_summary(self, obj: InventoryImportJob):
    return obj.summary or None

  def get_result_url(self, obj: InventoryImportJob):
    return obj.result_url or None
