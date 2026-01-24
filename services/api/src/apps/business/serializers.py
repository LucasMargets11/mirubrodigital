from rest_framework import serializers

from .models import CommercialSettings


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
