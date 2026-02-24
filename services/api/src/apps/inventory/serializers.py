from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Product
from apps.catalog.serializers import ProductSummarySerializer
from apps.treasury.models import Account, TransactionCategory
from .models import InventoryImportJob, ProductStock, StockMovement, StockReplenishment
from .services import register_stock_movement, create_stock_replenishment, void_stock_replenishment


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
  replenishment_id = serializers.UUIDField(source='replenishment.id', read_only=True, allow_null=True)

  class Meta:
    model = StockMovement
    fields = ['id', 'product', 'movement_type', 'quantity', 'note', 'unit_cost', 'replenishment_id', 'created_at']
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


# ---------------------------------------------------------------------------
# Replenishment serializers
# ---------------------------------------------------------------------------

class ReplenishmentItemInputSerializer(serializers.Serializer):
  product_id = serializers.UUIDField()
  quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
  unit_cost = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=Decimal('0'))


class StockReplenishmentCreateSerializer(serializers.Serializer):
  # DateField: accept and store only the date (YYYY-MM-DD).
  # Using timezone.localdate as default ensures "today in AR timezone".
  occurred_at = serializers.DateField(default=timezone.localdate)
  supplier_name = serializers.CharField(max_length=255)
  invoice_number = serializers.CharField(max_length=100, allow_blank=True, required=False, default='')
  account_id = serializers.IntegerField()
  purchase_category_id = serializers.IntegerField(required=False, allow_null=True)
  notes = serializers.CharField(allow_blank=True, required=False, default='')
  items = ReplenishmentItemInputSerializer(many=True, min_length=1)

  def validate_account_id(self, value):
    request = self.context['request']
    business = getattr(request, 'business')
    try:
      account = Account.objects.get(pk=value, business=business, is_active=True)
    except Account.DoesNotExist as exc:
      raise serializers.ValidationError('Cuenta no encontrada en este negocio.') from exc
    self.context['account'] = account
    return value

  def validate_purchase_category_id(self, value):
    if value is None:
      return value
    request = self.context['request']
    business = getattr(request, 'business')
    try:
      category = TransactionCategory.objects.get(pk=value, business=business, is_active=True)
    except TransactionCategory.DoesNotExist as exc:
      raise serializers.ValidationError('Categoría no encontrada en este negocio.') from exc
    if category.direction != TransactionCategory.Direction.EXPENSE:
      raise serializers.ValidationError('La categoría debe ser de tipo Egreso.')
    self.context['purchase_category'] = category
    return value

  def create(self, validated_data):
    request = self.context['request']
    business = getattr(request, 'business')
    account = self.context['account']
    purchase_category = self.context.get('purchase_category')
    items_data = validated_data['items']
    items = [
      {
        'product_id': str(item['product_id']),
        'quantity': item['quantity'],
        'unit_cost': item['unit_cost'],
      }
      for item in items_data
    ]
    try:
      replenishment = create_stock_replenishment(
        business=business,
        occurred_at=validated_data['occurred_at'],
        supplier_name=validated_data['supplier_name'],
        invoice_number=validated_data.get('invoice_number', ''),
        account=account,
        purchase_category=purchase_category,
        notes=validated_data.get('notes', ''),
        items=items,
        created_by=request.user,
      )
    except DjangoValidationError as exc:
      message = getattr(exc, 'message', None) or '; '.join(exc.messages)
      raise serializers.ValidationError({'detail': message}) from exc
    return replenishment

  def to_representation(self, instance):
    return StockReplenishmentDetailSerializer(instance, context=self.context).data


class ReplenishmentTransactionSummarySerializer(serializers.Serializer):
  id = serializers.IntegerField()
  amount = serializers.DecimalField(max_digits=19, decimal_places=4)
  direction = serializers.CharField()
  occurred_at = serializers.DateTimeField()
  status = serializers.CharField()
  account_name = serializers.SerializerMethodField()

  def get_account_name(self, obj):
    return obj.account.name if obj.account_id else None


class ReplenishmentMovementSummarySerializer(serializers.Serializer):
  id = serializers.UUIDField()
  product_name = serializers.SerializerMethodField()
  product_sku = serializers.SerializerMethodField()
  movement_type = serializers.CharField()
  quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
  unit_cost = serializers.DecimalField(max_digits=19, decimal_places=4, allow_null=True)
  line_total = serializers.SerializerMethodField()
  created_at = serializers.DateTimeField()

  def get_product_name(self, obj):
    return obj.product.name if obj.product_id else None

  def get_product_sku(self, obj):
    return obj.product.sku if obj.product_id else None

  def get_line_total(self, obj):
    if obj.unit_cost is not None:
      return obj.quantity * obj.unit_cost
    return None


class StockReplenishmentListSerializer(serializers.ModelSerializer):
  account_name = serializers.CharField(source='account.name', read_only=True, allow_null=True)
  transaction_id = serializers.IntegerField(source='transaction.id', read_only=True, allow_null=True)

  class Meta:
    model = StockReplenishment
    fields = [
      'id', 'occurred_at', 'supplier_name', 'invoice_number',
      'account_id', 'account_name', 'total_amount', 'status',
      'transaction_id', 'created_at',
    ]
    read_only_fields = fields


class StockReplenishmentDetailSerializer(serializers.ModelSerializer):
  account_name = serializers.CharField(source='account.name', read_only=True, allow_null=True)
  purchase_category_name = serializers.CharField(source='purchase_category.name', read_only=True, allow_null=True)
  transaction = serializers.SerializerMethodField()
  items = serializers.SerializerMethodField()

  class Meta:
    model = StockReplenishment
    fields = [
      'id', 'occurred_at', 'supplier_name', 'invoice_number',
      'account_id', 'account_name',
      'purchase_category_id', 'purchase_category_name',
      'total_amount', 'notes', 'status', 'created_at',
      'transaction', 'items',
    ]
    read_only_fields = fields

  def get_transaction(self, obj):
    tx = getattr(obj, 'transaction', None)
    if tx is None:
      return None
    return {
      'id': tx.id,
      'amount': str(tx.amount),
      'direction': tx.direction,
      'occurred_at': tx.occurred_at,
      'status': tx.status,
      'account_id': tx.account_id,
      'account_name': tx.account.name if tx.account_id else None,
    }

  def get_items(self, obj):
    movements = obj.stock_movements.filter(
      movement_type=StockMovement.MovementType.IN,
      reason='replenishment',
    ).select_related('product')
    return ReplenishmentMovementSummarySerializer(movements, many=True).data


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
