from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.sales.models import Sale
from apps.sales.serializers import SaleItemSerializer
from .models import Invoice, InvoiceSeries, DocumentSeries


@dataclass
class SeriesResult:
  series: InvoiceSeries
  created: bool


def _normalize_series_code(value: str) -> str:
  return (value or 'X').strip().upper() or 'X'


def get_or_create_series(business, code: str) -> SeriesResult:
  normalized = _normalize_series_code(code)
  try:
    series = InvoiceSeries.objects.select_for_update().get(business=business, code=normalized)
    return SeriesResult(series=series, created=False)
  except InvoiceSeries.DoesNotExist:
    try:
      series = InvoiceSeries.objects.create(business=business, code=normalized)
      return SeriesResult(series=series, created=True)
    except IntegrityError:
      series = InvoiceSeries.objects.select_for_update().get(business=business, code=normalized)
      return SeriesResult(series=series, created=False)


class DocumentSeriesSerializer(serializers.ModelSerializer):
  document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
  business_name = serializers.CharField(source='business.name', read_only=True)
  
  class Meta:
    model = DocumentSeries
    fields = [
      'id',
      'business',
      'business_name',
      'document_type',
      'document_type_display',
      'letter',
      'prefix',
      'suffix',
      'point_of_sale',
      'next_number',
      'is_active',
      'is_default',
      'branch',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'created_at', 'updated_at', 'business']
  
  def validate(self, attrs):
    """Validar que solo haya una serie default por tipo de documento."""
    if attrs.get('is_default', False):
      business = attrs.get('business') or self.instance.business if self.instance else None
      document_type = attrs.get('document_type') or self.instance.document_type if self.instance else None
      
      if business and document_type:
        # Verificar que no exista otra serie default del mismo tipo
        existing_default = DocumentSeries.objects.filter(
          business=business,
          document_type=document_type,
          is_default=True
        )
        if self.instance:
          existing_default = existing_default.exclude(pk=self.instance.pk)
        
        if existing_default.exists():
          raise serializers.ValidationError({
            'is_default': f'Ya existe una serie por defecto para {document_type}. Desactívala primero.'
          })
    
    return attrs


class InvoiceSeriesSerializer(serializers.ModelSerializer):
  class Meta:
    model = InvoiceSeries
    fields = ['id', 'code', 'prefix', 'next_number', 'is_active']
    read_only_fields = fields


class InvoiceListSerializer(serializers.ModelSerializer):
  sale_number = serializers.IntegerField(source='sale.number', read_only=True)
  pdf_url = serializers.SerializerMethodField()

  class Meta:
    model = Invoice
    fields = [
      'id',
      'full_number',
      'status',
      'issued_at',
      'sale_id',
      'sale_number',
      'customer_name',
      'total',
      'pdf_url',
    ]
    read_only_fields = fields

  def get_pdf_url(self, obj: Invoice) -> str:
    return f"/api/v1/invoices/{obj.pk}/pdf/"


class InvoiceDetailSerializer(InvoiceListSerializer):
  items = serializers.SerializerMethodField()
  series_code = serializers.CharField(source='series.code', read_only=True)
  series_prefix = serializers.CharField(source='series.prefix', read_only=True)

  class Meta(InvoiceListSerializer.Meta):
    fields = InvoiceListSerializer.Meta.fields + [
      'series_code',
      'series_prefix',
      'number',
      'subtotal',
      'discount',
      'customer_tax_id',
      'customer_address',
      'items',
    ]

  def get_items(self, obj: Invoice):
    sale_items = obj.sale.items.select_related('product').all()
    return SaleItemSerializer(sale_items, many=True).data


class InvoiceIssueSerializer(serializers.Serializer):
  sale_id = serializers.UUIDField()
  series_code = serializers.CharField(required=False, allow_blank=True, default='X')
  customer_name = serializers.CharField(required=False, allow_blank=True)
  customer_tax_id = serializers.CharField(required=False, allow_blank=True)
  customer_address = serializers.CharField(required=False, allow_blank=True)

  def validate_sale_id(self, value: UUID):
    business = self.context['business']
    try:
      sale = Sale.objects.select_related('customer').get(pk=value, business=business)
    except Sale.DoesNotExist as exc:
      raise serializers.ValidationError('Venta no encontrada en este negocio.') from exc
    if sale.status != Sale.Status.COMPLETED:
      raise serializers.ValidationError('Solo podés facturar ventas completadas.')
    if hasattr(sale, 'invoice'):
      raise serializers.ValidationError('La venta ya tiene una factura emitida.')
    self.context['sale'] = sale
    return value

  def validate_series_code(self, value: Optional[str]) -> str:
    return _normalize_series_code(value or 'X')

  @transaction.atomic
  def create(self, validated_data):
    business = self.context['business']
    user = self.context.get('user')
    sale: Sale = self.context['sale']
    series_result = get_or_create_series(business, validated_data['series_code'])
    series = series_result.series

    series = InvoiceSeries.objects.select_for_update().get(pk=series.pk)
    number = series.next_number
    full_number = series.format_full_number(number)

    customer_name = validated_data.get('customer_name') or (sale.customer.name if sale.customer else '')
    customer_tax_id = validated_data.get('customer_tax_id') or (sale.customer.doc_number if sale.customer else '')
    customer_address = validated_data.get('customer_address') or ''

    invoice = Invoice.objects.create(
      business=business,
      sale=sale,
      series=series,
      number=number,
      full_number=full_number,
      status=Invoice.Status.ISSUED,
      issued_at=timezone.now(),
      customer_name=customer_name,
      customer_tax_id=customer_tax_id,
      customer_address=customer_address,
      subtotal=Decimal(sale.subtotal),
      discount=Decimal(sale.discount),
      total=Decimal(sale.total),
      created_by=user if getattr(user, 'is_authenticated', False) else None,
    )

    series.next_number = number + 1
    series.save(update_fields=['next_number', 'updated_at'])
    return invoice

  def to_representation(self, instance):
    return InvoiceDetailSerializer(instance, context=self.context).data
