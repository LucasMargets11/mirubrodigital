"""Serializers para presupuestos (Quotes)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.customers.serializers import CustomerSummarySerializer
from .models import Quote, QuoteItem
from .quote_services import generate_quote_number, recalc_quote_totals


class QuoteItemSerializer(serializers.ModelSerializer):
    product_id = serializers.SerializerMethodField()
    product_name = serializers.CharField(source='name_snapshot', read_only=True)

    class Meta:
        model = QuoteItem
        fields = ['id', 'product_id', 'product_name', 'quantity', 'unit_price', 'discount', 'total_line']
        read_only_fields = ['id', 'total_line']

    def get_product_id(self, obj: QuoteItem):
        return str(obj.product_id) if obj.product_id else None


class QuoteListSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer = CustomerSummarySerializer(read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            'id',
            'number',
            'status',
            'status_label',
            'customer_id',
            'customer_name',
            'customer',
            'customer_email',
            'customer_phone',
            'valid_until',
            'currency',
            'subtotal',
            'discount_total',
            'tax_total',
            'total',
            'created_at',
            'sent_at',
            'items_count',
        ]
        read_only_fields = fields

    def get_customer_name(self, obj: Quote) -> Optional[str]:
        if obj.customer:
            return obj.customer.name
        return obj.customer_name or None

    def get_items_count(self, obj: Quote) -> int:
        annotated = getattr(obj, 'items_count', None)
        if annotated is not None:
            return int(annotated)
        return obj.items.count()


class QuoteDetailSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    customer = CustomerSummarySerializer(read_only=True)
    items = QuoteItemSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            'id',
            'number',
            'status',
            'status_label',
            'customer_id',
            'customer',
            'customer_name',
            'customer_email',
            'customer_phone',
            'valid_until',
            'notes',
            'terms',
            'currency',
            'subtotal',
            'discount_total',
            'tax_total',
            'total',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
            'sent_at',
            'items',
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj: Quote) -> Optional[str]:
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip() or obj.created_by.email
        return None


class QuoteItemCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255, required=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'), min_value=Decimal('0'))


class QuoteCreateSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    valid_until = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    terms = serializers.CharField(required=False, allow_blank=True)
    currency = serializers.CharField(max_length=3, default='ARS')
    items = QuoteItemCreateSerializer(many=True, required=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("El presupuesto debe tener al menos un ítem.")
        return value

    def validate(self, attrs):
        # Validar que si no hay customer_id, haya customer_name
        if not attrs.get('customer_id') and not attrs.get('customer_name'):
            raise serializers.ValidationError({
                'customer_name': 'Debe especificar un cliente o ingresar un nombre.'
            })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        business = self.context['business']
        user = self.context['request'].user

        # Generar número
        quote_number = generate_quote_number(business)

        # Validar customer_id si existe
        customer = None
        customer_id = validated_data.pop('customer_id', None)
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id, business=business)
            except Customer.DoesNotExist:
                raise serializers.ValidationError({'customer_id': 'Cliente no encontrado.'})

        # Crear quote
        quote = Quote.objects.create(
            business=business,
            number=quote_number,
            customer=customer,
            created_by=user,
            **validated_data
        )

        # Crear items
        for item_data in items_data:
            product_id = item_data.pop('product_id', None)
            product = None
            if product_id:
                try:
                    product = Product.objects.get(pk=product_id, business=business)
                except Product.DoesNotExist:
                    pass

            QuoteItem.objects.create(
                quote=quote,
                product=product,
                name_snapshot=item_data['name'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                discount=item_data.get('discount', Decimal('0')),
                total_line=Decimal('0')  # Se calcula después
            )

        # Recalcular totales
        recalc_quote_totals(quote)
        quote.refresh_from_db()

        return quote

    @transaction.atomic
    def update(self, instance: Quote, validated_data):
        items_data = validated_data.pop('items', None)
        business = self.context['business']

        # Validar customer_id si existe
        customer_id = validated_data.pop('customer_id', None)
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id, business=business)
                instance.customer = customer
            except Customer.DoesNotExist:
                raise serializers.ValidationError({'customer_id': 'Cliente no encontrado.'})

        # Actualizar campos del quote
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        # Si hay items, reemplazar todos
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                product_id = item_data.pop('product_id', None)
                product = None
                if product_id:
                    try:
                        product = Product.objects.get(pk=product_id, business=business)
                    except Product.DoesNotExist:
                        pass

                QuoteItem.objects.create(
                    quote=instance,
                    product=product,
                    name_snapshot=item_data['name'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    discount=item_data.get('discount', Decimal('0')),
                    total_line=Decimal('0')
                )

            # Recalcular totales
            recalc_quote_totals(instance)
            instance.refresh_from_db()

        return instance


class QuoteMarkStatusSerializer(serializers.Serializer):
    """Serializer para cambiar el estado de un presupuesto."""
    pass  # No necesita campos, solo cambia el estado
