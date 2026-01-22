from decimal import Decimal

from rest_framework import serializers

from apps.accounts.permissions import request_has_permission
from apps.inventory.services import ensure_stock_record
from .models import Product


class ProductSerializer(serializers.ModelSerializer):
  class Meta:
    model = Product
    fields = [
      'id',
      'business',
      'name',
      'sku',
      'barcode',
      'cost',
      'price',
      'stock_min',
      'is_active',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'created_at', 'updated_at']

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


class ProductSummarySerializer(serializers.ModelSerializer):
  class Meta:
    model = Product
    fields = ['id', 'name', 'sku', 'barcode', 'stock_min', 'is_active']
    read_only_fields = fields
