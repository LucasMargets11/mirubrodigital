from decimal import Decimal

from rest_framework import serializers

from apps.accounts.permissions import request_has_permission
from apps.inventory.services import ensure_stock_record
from .models import Product, ProductCategory


class ProductCategorySerializer(serializers.ModelSerializer):
  products_count = serializers.IntegerField(read_only=True, default=0)
  
  class Meta:
    model = ProductCategory
    fields = ['id', 'business', 'name', 'is_active', 'products_count', 'created_at', 'updated_at']
    read_only_fields = ['id', 'business', 'products_count', 'created_at', 'updated_at']

  def validate_name(self, value: str) -> str:
    value = value.strip()
    if len(value) < 2:
      raise serializers.ValidationError('El nombre debe tener al menos 2 caracteres.')
    if len(value) > 100:
      raise serializers.ValidationError('El nombre no puede exceder 100 caracteres.')
    return value

  def validate(self, attrs):
    business = attrs.get('business') or getattr(self.instance, 'business', None)
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)
    
    name = attrs.get('name')
    if business and name:
      # Check for duplicate category name (case-insensitive)
      conflict = ProductCategory.objects.filter(business=business, name__iexact=name)
      if self.instance:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'name': 'Ya existe una categoría con este nombre.'})
    
    return attrs


class ProductCategorySummarySerializer(serializers.ModelSerializer):
  """Serializer reducido para embeber en otros serializers"""
  class Meta:
    model = ProductCategory
    fields = ['id', 'name']
    read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
  stock_quantity = serializers.SerializerMethodField()
  category = ProductCategorySummarySerializer(read_only=True)
  category_id = serializers.PrimaryKeyRelatedField(
    queryset=ProductCategory.objects.all(),
    source='category',
    allow_null=True,
    required=False,
    write_only=True
  )
  
  class Meta:
    model = Product
    fields = [
      'id',
      'business',
      'category',
      'category_id',
      'name',
      'sku',
      'barcode',
      'cost',
      'price',
      'stock_min',
      'is_active',
      'stock_quantity',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'created_at', 'updated_at', 'stock_quantity', 'category']

  def validate_category_id(self, value):
    """Validate that category belongs to the same business as the product"""
    if value is None:
      return value
    
    business = getattr(self.instance, 'business', None) if self.instance else None
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)
    
    if business and value.business_id != business.id:
      raise serializers.ValidationError('La categoría no pertenece a este negocio.')
    
    return value

  def validate_cost(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El costo debe ser positivo.')
    return value

  def validate_price(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El precio debe ser positivo.')
    return value

  def validate_stock_min(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El stock minimo debe ser igual o mayor a cero.')
    return value

  def validate(self, attrs):
    business = attrs.get('business') or getattr(self.instance, 'business', None)
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)
    sku = attrs.get('sku')
    if business and sku:
      conflict = Product.objects.filter(business=business, sku__iexact=sku)
      if self.instance:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'sku': 'Ya existe un producto con este SKU.'})
    return attrs

  def create(self, validated_data):
    business = validated_data['business']
    product = Product.objects.create(**validated_data)
    ensure_stock_record(business, product)
    return product

  def update(self, instance, validated_data):
    validated_data.pop('business', None)
    return super().update(instance, validated_data)

  def to_representation(self, instance):
    data = super().to_representation(instance)
    request = self.context.get('request') if isinstance(self.context, dict) else None
    if request is not None and not request_has_permission(request, 'manage_products'):
      data.pop('cost', None)
    return data
  
  def get_stock_quantity(self, obj):
    stock_level = getattr(obj, 'stock_level', None)
    if stock_level is None:
      return None
    return stock_level.quantity


class ProductSummarySerializer(serializers.ModelSerializer):
  category = ProductCategorySummarySerializer(read_only=True)
  
  class Meta:
    model = Product
    fields = ['id', 'name', 'sku', 'barcode', 'stock_min', 'is_active', 'category']
    read_only_fields = fields
