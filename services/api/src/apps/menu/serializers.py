from __future__ import annotations

from typing import Any, Iterable, List

from rest_framework import serializers

from .models import MenuCategory, MenuItem


class TagListField(serializers.ListField):
    child = serializers.CharField(max_length=48, allow_blank=False)

    def to_representation(self, value: Any):  # type: ignore[override]
        if isinstance(value, str):
            return [tag.strip() for tag in value.split(',') if tag.strip()]
        if isinstance(value, Iterable):
            return [str(tag).strip() for tag in value if str(tag).strip()]
        return []


class MenuCategorySerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'description', 'position', 'is_active', 'item_count']
        read_only_fields = ['id', 'item_count']


class MenuItemBaseSerializer(serializers.ModelSerializer):
    tags = TagListField(required=False, allow_empty=True)
    category_name = serializers.SerializerMethodField(read_only=True)
    category_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = MenuItem
        fields = [
            'id',
            'category_id',
            'category_name',
            'name',
            'description',
            'price',
            'sku',
            'tags',
            'is_available',
            'is_featured',
            'position',
            'estimated_time_minutes',
        ]
        read_only_fields = ['id', 'category_name']

    def to_representation(self, instance: MenuItem):  # type: ignore[override]
        payload = super().to_representation(instance)
        payload['tags'] = instance.tag_list
        return payload

    def get_category_name(self, instance: MenuItem) -> str | None:
        return instance.category.name if instance.category else None

    def _prepare_tags(self, validated_data: dict) -> None:
        tags: List[str] | None = validated_data.pop('tags', None)
        if tags is None:
            return
        normalized = []
        seen = set()
        for tag in tags:
            clean = tag.strip()
            if not clean or clean.lower() in seen:
                continue
            seen.add(clean.lower())
            normalized.append(clean)
        validated_data['tags'] = ','.join(normalized)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El nombre es obligatorio.')
        return value

    def validate_price(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError('El precio debe ser igual o mayor a 0.')
        return value

    def validate_sku(self, value: str) -> str:
        return value.strip()

    def create(self, validated_data: dict):
        category_id = validated_data.pop('category_id', None)
        if category_id:
            validated_data['category_id'] = category_id
        self._prepare_tags(validated_data)
        return super().create(validated_data)

    def update(self, instance: MenuItem, validated_data: dict):
        category_id = validated_data.pop('category_id', None)
        if category_id is not None:
            validated_data['category_id'] = category_id
        self._prepare_tags(validated_data)
        return super().update(instance, validated_data)


class MenuItemSerializer(MenuItemBaseSerializer):
    class Meta(MenuItemBaseSerializer.Meta):
        read_only_fields = ['id', 'category_name']


class MenuItemWriteSerializer(MenuItemBaseSerializer):
    class Meta(MenuItemBaseSerializer.Meta):
        read_only_fields = ['category_name']


class MenuStructureItemSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = ['id', 'name', 'description', 'price', 'tags', 'is_available', 'is_featured', 'position']

    def get_tags(self, obj: MenuItem) -> List[str]:
        return obj.tag_list


class MenuStructureCategorySerializer(serializers.ModelSerializer):
    items = MenuStructureItemSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'description', 'position', 'items']


class MenuImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        filename = getattr(value, 'name', '') or ''
        if not filename.lower().endswith('.xlsx'):
            raise serializers.ValidationError('Subí un archivo .xlsx generado por la plantilla.')
        return value
