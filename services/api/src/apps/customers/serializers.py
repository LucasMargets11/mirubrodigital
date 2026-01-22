from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import Customer


class CustomerSummarySerializer(serializers.ModelSerializer):
  class Meta:
    model = Customer
    fields = ['id', 'name', 'doc_type', 'doc_number', 'email', 'phone']
    read_only_fields = fields


class CustomerSerializer(serializers.ModelSerializer):
  class Meta:
    model = Customer
    fields = [
      'id',
      'business',
      'name',
      'type',
      'doc_type',
      'doc_number',
      'tax_condition',
      'email',
      'phone',
      'address_line',
      'city',
      'province',
      'postal_code',
      'country',
      'note',
      'tags',
      'is_active',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'created_at', 'updated_at']

  def validate_name(self, value: str) -> str:
    if not value.strip():
      raise serializers.ValidationError('El nombre no puede estar vacío.')
    return value

  def validate_doc_number(self, value: str) -> str:
    if value is None:
      return ''
    return value.strip()

  def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
    business = attrs.get('business') or getattr(self.instance, 'business', None)
    email = attrs.get('email')
    if business and email:
      conflict = Customer.objects.filter(business=business, email__iexact=email)
      if self.instance is not None:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'email': 'Ya existe un cliente con este email.'})
    doc_type = attrs.get('doc_type')
    doc_number = attrs.get('doc_number')
    if business and doc_type and doc_number:
      lookup = Customer.objects.filter(business=business, doc_type=doc_type, doc_number__iexact=doc_number)
      if self.instance is not None:
        lookup = lookup.exclude(pk=self.instance.pk)
      if lookup.exists():
        raise serializers.ValidationError({'doc_number': 'Ya existe un cliente con este documento.'})

    return attrs

  def create(self, validated_data: dict[str, Any]) -> Customer:
    if 'tags' not in validated_data or validated_data['tags'] is None:
      validated_data['tags'] = []
    return Customer.objects.create(**validated_data)

  def update(self, instance: Customer, validated_data: dict[str, Any]) -> Customer:
    validated_data.pop('business', None)
    if 'tags' in validated_data and validated_data['tags'] is None:
      validated_data['tags'] = []
    return super().update(instance, validated_data)

  def to_representation(self, instance: Customer) -> dict[str, Any]:
    data = super().to_representation(instance)
    if data.get('note') == '':
      data['note'] = None
    if data.get('tags') == []:
      data['tags'] = []
    return data
