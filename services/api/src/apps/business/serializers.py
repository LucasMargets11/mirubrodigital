from rest_framework import serializers

from .models import CommercialSettings, Business, BusinessBillingProfile, BusinessBranding


class BranchSerializer(serializers.ModelSerializer):
  class Meta:
    model = Business
    fields = ['id', 'name', 'status', 'created_at']
    read_only_fields = ['id', 'created_at', 'status']


class BranchCreateSerializer(serializers.ModelSerializer):
  class Meta:
    model = Business
    fields = ['name']

  def validate_name(self, value):
    if len(value) < 3:
      raise serializers.ValidationError("El nombre debe tener al menos 3 caracteres")
    return value



class CommercialSettingsSerializer(serializers.ModelSerializer):
  class Meta:
    model = CommercialSettings
    fields = [
      'allow_sell_without_stock',
      'block_sales_if_no_open_cash_session',
      'require_customer_for_sales',
      'allow_negative_price_or_discount',
      'warn_on_low_stock_threshold_enabled',
      'low_stock_threshold_default',
      'enable_sales_notes',
      'enable_receipts',
    ]

  def validate_low_stock_threshold_default(self, value: int) -> int:
    if value < 0:
      raise serializers.ValidationError('El umbral debe ser mayor o igual a cero.')
    return value


class BusinessBillingProfileSerializer(serializers.ModelSerializer):
  tax_id_type_display = serializers.CharField(source='get_tax_id_type_display', read_only=True)
  vat_condition_display = serializers.CharField(source='get_vat_condition_display', read_only=True)
  is_complete = serializers.BooleanField(read_only=True)
  
  class Meta:
    model = BusinessBillingProfile
    fields = [
      'legal_name',
      'trade_name',
      'tax_id_type',
      'tax_id_type_display',
      'tax_id',
      'vat_condition',
      'vat_condition_display',
      'iibb',
      'activity_start_date',
      'commercial_address',
      'fiscal_address',
      'email',
      'phone',
      'website',
      'is_complete',
      'updated_at',
    ]
    read_only_fields = ['updated_at']
  
  def validate_tax_id(self, value: str) -> str:
    """Validación básica de formato de CUIT/CUIL."""
    if value and '-' in value:
      parts = value.split('-')
      if len(parts) != 3:
        raise serializers.ValidationError('Formato inválido. Use: XX-XXXXXXXX-X')
    return value


class BusinessBrandingSerializer(serializers.ModelSerializer):
  logo_horizontal_url = serializers.SerializerMethodField()
  logo_square_url = serializers.SerializerMethodField()
  
  class Meta:
    model = BusinessBranding
    fields = [
      'logo_horizontal',
      'logo_horizontal_url',
      'logo_square',
      'logo_square_url',
      'accent_color',
      'updated_at',
    ]
    read_only_fields = ['updated_at']
  
  def get_logo_horizontal_url(self, obj):
    if obj.logo_horizontal:
      request = self.context.get('request')
      if request:
        return request.build_absolute_uri(obj.logo_horizontal.url)
      return obj.logo_horizontal.url
    return None
  
  def get_logo_square_url(self, obj):
    if obj.logo_square:
      request = self.context.get('request')
      if request:
        return request.build_absolute_uri(obj.logo_square.url)
      return obj.logo_square.url
    return None
