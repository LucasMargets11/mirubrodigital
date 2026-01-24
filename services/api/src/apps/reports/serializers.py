from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, Iterable, List

from rest_framework import serializers

from apps.cash.models import CashMovement, CashSession, Payment
from apps.sales.serializers import SaleDetailSerializer, SaleListSerializer


def _format_decimal(value: Decimal | None) -> str:
  if value is None:
    return '0.00'
  if not isinstance(value, Decimal):
    value = Decimal(value)
  return f"{value.quantize(Decimal('0.01')):.2f}"


class UserSummarySerializer(serializers.Serializer):
  id = serializers.CharField(source='pk', read_only=True)
  name = serializers.SerializerMethodField()
  email = serializers.EmailField(read_only=True)

  def get_name(self, obj):  # pragma: no cover - formatting helper
    full_name = getattr(obj, 'get_full_name', None)
    if callable(full_name):
      value = full_name()
      if value:
        return value
    first_name = getattr(obj, 'first_name', '')
    last_name = getattr(obj, 'last_name', '')
    if first_name or last_name:
      return f"{first_name} {last_name}".strip()
    return getattr(obj, 'email', None) or getattr(obj, 'username', '') or 'Usuario'


class PaymentsSummaryMixin(serializers.Serializer):
  payments_summary = serializers.SerializerMethodField()

  def _fetch_payments(self, obj) -> Iterable[Payment]:
    payments = getattr(obj, '_prefetched_payments', None)
    if payments is not None:
      return payments
    if hasattr(obj, 'payments'):
      payments = list(obj.payments.all())
      setattr(obj, '_prefetched_payments', payments)
      return payments
    return []

  def get_payments_summary(self, obj) -> List[Dict[str, Any]]:
    payments = self._fetch_payments(obj)
    if not payments:
      return []
    totals: Dict[str, Decimal] = defaultdict(lambda: Decimal('0'))
    for payment in payments:
      totals[payment.method] += payment.amount or Decimal('0')
    summary = []
    for method, amount in totals.items():
      try:
        method_label = Payment.Method(method).label
      except ValueError:  # pragma: no cover - safety net for unknown methods
        method_label = method.replace('_', ' ').title()
      summary.append({
        'method': method,
        'method_label': method_label,
        'amount': amount,
      })
    summary.sort(key=lambda row: row['amount'], reverse=True)
    for row in summary:
      row['amount'] = _format_decimal(row['amount'])
    return summary


class ReportSaleListSerializer(PaymentsSummaryMixin, SaleListSerializer):
  cashier = UserSummarySerializer(source='created_by', read_only=True)

  class Meta(SaleListSerializer.Meta):  # type: ignore[misc]
    fields = SaleListSerializer.Meta.fields + ['cashier', 'payments_summary']
    read_only_fields = fields


class ReportSaleDetailSerializer(PaymentsSummaryMixin, SaleDetailSerializer):
  cashier = UserSummarySerializer(source='created_by', read_only=True)

  class Meta(SaleDetailSerializer.Meta):  # type: ignore[misc]
    fields = SaleDetailSerializer.Meta.fields + ['cashier', 'payments_summary']
    read_only_fields = fields


class ReportPaymentSerializer(serializers.ModelSerializer):
  method_label = serializers.CharField(source='get_method_display', read_only=True)
  sale_number = serializers.IntegerField(source='sale.number', read_only=True)
  sale_total = serializers.DecimalField(source='sale.total', max_digits=12, decimal_places=2, read_only=True)
  cashier = UserSummarySerializer(source='created_by', read_only=True)
  register = serializers.SerializerMethodField()

  class Meta:
    model = Payment
    fields = [
      'id',
      'sale_id',
      'sale_number',
      'sale_total',
      'session_id',
      'register',
      'method',
      'method_label',
      'amount',
      'reference',
      'created_at',
      'cashier',
    ]
    read_only_fields = fields

  def get_register(self, obj):
    session = getattr(obj, 'session', None)
    register = getattr(session, 'register', None)
    if register is None:
      return None
    return {'id': str(register.id), 'name': register.name}


class CashMovementSummarySerializer(serializers.ModelSerializer):
  created_by = UserSummarySerializer(read_only=True)

  class Meta:
    model = CashMovement
    fields = [
      'id',
      'movement_type',
      'category',
      'method',
      'amount',
      'note',
      'created_by',
      'created_at',
    ]
    read_only_fields = fields


class CashPaymentSummarySerializer(serializers.ModelSerializer):
  sale_number = serializers.IntegerField(source='sale.number', read_only=True)
  customer_name = serializers.SerializerMethodField()

  class Meta:
    model = Payment
    fields = ['id', 'sale_id', 'sale_number', 'amount', 'reference', 'created_at', 'customer_name']
    read_only_fields = fields

  def get_customer_name(self, obj) -> str | None:
    customer = getattr(obj.sale, 'customer', None)
    if customer is None:
      return getattr(obj.sale, 'customer_name', None)
    return getattr(customer, 'name', None)


class CashClosureListSerializer(serializers.ModelSerializer):
  register = serializers.SerializerMethodField()
  opened_by = UserSummarySerializer(read_only=True)
  closed_by = UserSummarySerializer(read_only=True)
  expected_cash = serializers.DecimalField(source='expected_cash_total', max_digits=12, decimal_places=2, read_only=True, allow_null=True)
  counted_cash = serializers.DecimalField(source='closing_cash_counted', max_digits=12, decimal_places=2, read_only=True, allow_null=True)
  difference = serializers.DecimalField(source='difference_amount', max_digits=12, decimal_places=2, read_only=True, allow_null=True)
  note = serializers.CharField(source='closing_note', read_only=True)
  opened_by_name = serializers.CharField(read_only=True)

  class Meta:
    model = CashSession
    fields = [
      'id',
      'status',
      'register',
      'opened_at',
      'closed_at',
      'opening_cash_amount',
      'expected_cash',
      'counted_cash',
      'difference',
      'note',
      'opened_by',
      'opened_by_name',
      'closed_by',
    ]
    read_only_fields = fields

  def get_register(self, obj):
    register = getattr(obj, 'register', None)
    if register is None:
      return None
    return {'id': str(register.id), 'name': register.name}


class CashSessionSaleSerializer(ReportSaleListSerializer):
  class Meta(ReportSaleListSerializer.Meta):  # type: ignore[misc]
    fields = [
      'id',
      'number',
      'status',
      'status_label',
      'payment_method',
      'payment_method_label',
      'customer_id',
      'customer_name',
      'subtotal',
      'discount',
      'total',
      'created_at',
      'items_count',
      'invoice',
      'paid_total',
      'balance',
    ]
    read_only_fields = fields
