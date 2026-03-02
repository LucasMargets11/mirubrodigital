from __future__ import annotations

from typing import Any, Iterable, List

from rest_framework import serializers

from .qr_entitlements import get_subscription_for_business, resolve_menu_qr_flags, NEW_MENU_QR_PLANS
from .models import (
    MenuBrandingSettings,
    MenuCategory,
    MenuItem,
    MenuLayoutBlock,
    MenuLayoutBlockCategory,
    PublicMenuConfig,
    MenuEngagementSettings,
    MercadoPagoConnection,
    TipTransaction,
    ensure_public_menu_config,
)


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
    image_url = serializers.SerializerMethodField(read_only=True)

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
            'image_url',
        ]
        read_only_fields = ['id', 'category_name', 'image_url']

    def to_representation(self, instance: MenuItem):  # type: ignore[override]
        payload = super().to_representation(instance)
        payload['tags'] = instance.tag_list
        return payload

    def get_category_name(self, instance: MenuItem) -> str | None:
        return instance.category.name if instance.category else None

    def get_image_url(self, instance: MenuItem) -> str | None:
        url = instance.image_url_value
        if url:
            request = self.context.get('request')
            if request and url.startswith('/'):
                return request.build_absolute_uri(url)
        return url

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
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = ['id', 'name', 'description', 'price', 'tags', 'is_available', 'is_featured', 'position', 'image_url']

    def get_tags(self, obj: MenuItem) -> List[str]:
        return obj.tag_list

    def get_image_url(self, instance: MenuItem) -> str | None:
        url = instance.image_url_value
        if url:
            request = self.context.get('request') if hasattr(self, 'context') else None
            if request and url.startswith('/'):
                return request.build_absolute_uri(url)
        return url


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


class MenuLogoUploadSerializer(serializers.Serializer):
    file = serializers.ImageField()


class PublicMenuConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicMenuConfig
        fields = [
            'enabled',
            'slug',
            'public_id',
            'brand_name',
            'logo_url',
            'theme_json',
            'template_key',
            'updated_at',
        ]
        read_only_fields = ['public_id', 'updated_at']


class MenuBrandingSettingsSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = MenuBrandingSettings
        fields = [
            'display_name',
            'logo_url',
            'palette_primary',
            'palette_secondary',
            'palette_background',
            'palette_text',
            'font_heading',
            'font_body',
            'font_scale_heading',
            'font_scale_body',
            'updated_at',
        ]
        read_only_fields = ['logo_url', 'updated_at']

    def get_logo_url(self, obj):
        url = obj.logo_url
        request = self.context.get('request') if hasattr(self, 'context') else None
        if url and request and url.startswith('/'):
            return request.build_absolute_uri(url)
        return url

    def update(self, instance, validated_data):
        branding = super().update(instance, validated_data)
        config = ensure_public_menu_config(branding.business)
        if config.brand_name != branding.display_name:
            config.brand_name = branding.display_name
            config.save(update_fields=['brand_name'])
        return branding


class PublicMenuItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            'id',
            'name',
            'description',
            'price',
            'is_available',
            'tags',
            'sku',
            'image_url',
        ]

    def get_image_url(self, instance: MenuItem) -> str | None:
        url = instance.image_url_value
        if url:
            request = self.context.get('request')
            if request and url.startswith('/'):
                return request.build_absolute_uri(url)
        return url


class PublicMenuCategorySerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'description', 'position', 'items']

    def get_items(self, obj):
        # We show all items to indicate availability status
        items = obj.items.all().order_by('position', 'name')
        return PublicMenuItemSerializer(
            items,
            many=True,
            context=self.context,
        ).data


class MenuItemImageUploadSerializer(serializers.Serializer):
    """Validates the image file before upload to a MenuItem."""

    ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
    MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

    file = serializers.ImageField()

    def validate_file(self, value):
        content_type = getattr(value, 'content_type', None)
        if content_type and content_type not in self.ALLOWED_TYPES:
            raise serializers.ValidationError(
                'Formato no válido. Subí una imagen JPG, PNG o WebP.'
            )
        if value.size > self.MAX_SIZE_BYTES:
            max_mb = self.MAX_SIZE_BYTES // (1024 * 1024)
            raise serializers.ValidationError(
                f'El archivo es demasiado grande. Máximo {max_mb} MB.'
            )
        return value


# ---------------------------------------------------------------------------
# Engagement: tips + reviews serializers
# ---------------------------------------------------------------------------

class MenuEngagementSettingsSerializer(serializers.ModelSerializer):
    """Private serializer for the admin panel (full data, write access)."""

    google_write_review_url = serializers.ReadOnlyField()
    mp_qr_image_url = serializers.SerializerMethodField()

    class Meta:
        model = MenuEngagementSettings
        fields = [
            'tips_enabled',
            'tips_mode',
            'mp_tip_url',
            'mp_qr_image',
            'mp_qr_image_url',
            'reviews_enabled',
            'google_place_id',
            'google_review_url',
            'google_write_review_url',
            'updated_at',
        ]
        read_only_fields = ['google_write_review_url', 'mp_qr_image_url', 'updated_at']
        extra_kwargs = {
            'mp_qr_image': {'write_only': True, 'required': False},
        }

    def get_mp_qr_image_url(self, obj) -> str | None:
        if not obj.mp_qr_image:
            return None
        url = obj.mp_qr_image.url
        request = self.context.get('request')
        if request and url.startswith('/'):
            return request.build_absolute_uri(url)
        return url

    def validate(self, data):
        inst = self.instance
        tips_enabled = data.get('tips_enabled', inst.tips_enabled if inst else False)
        tips_mode = data.get('tips_mode', inst.tips_mode if inst else 'mp_link')
        mp_tip_url = data.get('mp_tip_url', inst.mp_tip_url if inst else None)
        mp_qr_image = data.get('mp_qr_image', inst.mp_qr_image if inst else None)

        reviews_enabled = data.get('reviews_enabled', inst.reviews_enabled if inst else False)
        place_id = data.get('google_place_id', inst.google_place_id if inst else None)
        review_url = data.get('google_review_url', inst.google_review_url if inst else None)

        # ── Plan-level entitlement check ─────────────────────────────────
        # Only enforce for businesses on a new QR plan (Lite/Pro/Premium).
        # Legacy plans (menu_qr, menu_qr_visual, menu_qr_marca) keep existing behavior.
        request = self.context.get('request')
        if request and hasattr(request, 'business'):
            business = request.business
            subscription = get_subscription_for_business(business)
            plan = getattr(subscription, 'plan', None) if subscription else None
            if plan in NEW_MENU_QR_PLANS:
                flags = resolve_menu_qr_flags(subscription)
                if tips_enabled and not flags['tips_allowed']:
                    raise serializers.ValidationError({
                        'tips_enabled': (
                            'Propinas no está disponible en tu plan actual. '
                            'Actualizá a Menú QR Pro (elige Propina como módulo incluido) '
                            'o agregá el add-on Propina.'
                        )
                    })
                if reviews_enabled and not flags['reviews_allowed']:
                    raise serializers.ValidationError({
                        'reviews_enabled': (
                            'Reseñas no está disponible en tu plan actual. '
                            'Actualizá a Menú QR Pro (elige Reseñas como módulo incluido) '
                            'o agregá el add-on Reseñas.'
                        )
                    })

        # Auto-enable reviews when a place_id or review_url is provided and the caller
        # did not explicitly set reviews_enabled=False in this payload.
        if (place_id or review_url) and 'reviews_enabled' not in data:
            data['reviews_enabled'] = True
            reviews_enabled = True

        if tips_enabled:
            if tips_mode == 'mp_link' and not mp_tip_url:
                raise serializers.ValidationError(
                    {'mp_tip_url': 'URL de Mercado Pago requerida para modo Link.'}
                )
            if tips_mode == 'mp_qr_image' and not mp_qr_image:
                raise serializers.ValidationError(
                    {'mp_qr_image': 'Imagen QR requerida para modo QR. Subí la imagen primero.'}
                )

        if reviews_enabled and not place_id and not review_url:
            raise serializers.ValidationError(
                {'google_place_id': 'Se requiere Google Place ID o URL de reseña cuando las reseñas están activas.'}
            )

        return data


class MercadoPagoConnectionStatusSerializer(serializers.Serializer):
    """Read-only connection status for the admin panel (never exposes tokens)."""
    connected = serializers.BooleanField()
    status = serializers.CharField(allow_null=True)
    mp_user_id = serializers.CharField(allow_blank=True, allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)


class TipCreatePreferenceSerializer(serializers.Serializer):
    """Validates a tip preference creation request from the public menu."""
    amount = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=10)
    table_ref = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')

    def validate_amount(self, value):
        if value > 50000:
            raise serializers.ValidationError('El monto máximo de propina es $50.000.')
        return value


class TipTransactionSerializer(serializers.Serializer):
    """Public read-only tip transaction status."""
    id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    status = serializers.CharField()
    external_reference = serializers.CharField()
    created_at = serializers.DateTimeField()


# ---------------------------------------------------------------------------
# MenuLayoutBlock — admin + public serializers
# ---------------------------------------------------------------------------

class MenuLayoutBlockCategorySerializer(serializers.ModelSerializer):
    category_id = serializers.UUIDField(source='category.id', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_active = serializers.BooleanField(source='category.is_active', read_only=True)

    class Meta:
        model = MenuLayoutBlockCategory
        fields = ['category_id', 'category_name', 'is_active', 'position']


class MenuLayoutBlockSerializer(serializers.ModelSerializer):
    """Admin serializer for reading and writing a single layout block."""
    block_categories = MenuLayoutBlockCategorySerializer(many=True, read_only=True)
    # Write: ordered list of category UUIDs
    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        default=list,
    )

    class Meta:
        model = MenuLayoutBlock
        fields = [
            'id', 'title', 'position', 'layout',
            'columns_desktop', 'columns_tablet', 'columns_mobile',
            'badge_text', 'block_categories', 'category_ids',
        ]
        read_only_fields = ['id']

    def _sync_categories(self, block: MenuLayoutBlock, category_ids: list) -> None:
        business = block.business
        # Delete orphans
        MenuLayoutBlockCategory.objects.filter(block=block).exclude(
            category_id__in=category_ids
        ).delete()
        existing = {
            str(bc.category_id): bc
            for bc in MenuLayoutBlockCategory.objects.filter(block=block)
        }
        for pos, cat_id in enumerate(category_ids):
            cat_id_str = str(cat_id)
            if cat_id_str in existing:
                bc = existing[cat_id_str]
                if bc.position != pos:
                    bc.position = pos
                    bc.save(update_fields=['position'])
            else:
                from apps.menu.models import MenuCategory as MC
                try:
                    cat = MC.objects.get(pk=cat_id, business=business)
                    MenuLayoutBlockCategory.objects.get_or_create(
                        block=block, category=cat, defaults={'position': pos}
                    )
                except MC.DoesNotExist:
                    pass

    def create(self, validated_data: dict):
        category_ids = validated_data.pop('category_ids', [])
        block = super().create(validated_data)
        self._sync_categories(block, category_ids)
        return block

    def update(self, instance: MenuLayoutBlock, validated_data: dict):
        category_ids = validated_data.pop('category_ids', None)
        block = super().update(instance, validated_data)
        if category_ids is not None:
            self._sync_categories(block, category_ids)
        return block


class MenuLayoutBlockReorderSerializer(serializers.Serializer):
    """PATCH /layout/blocks/reorder/ — list of {id, position}."""
    id = serializers.UUIDField()
    position = serializers.IntegerField(min_value=0)


# Public version: lightweight, used in PublicMenuBySlugView response
class PublicMenuLayoutBlockCategorySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='category.id')
    name = serializers.CharField(source='category.name')
    description = serializers.CharField(source='category.description')
    items = serializers.SerializerMethodField()

    class Meta:
        model = MenuLayoutBlockCategory
        fields = ['id', 'name', 'description', 'items']

    def get_items(self, obj):
        # .all() hits the prefetch cache set in PublicMenuBySlugView
        items = obj.category.items.all()
        return PublicMenuItemSerializer(items, many=True, context=self.context).data


class PublicMenuLayoutBlockSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()

    class Meta:
        model = MenuLayoutBlock
        fields = [
            'id', 'title', 'position', 'layout',
            'columns_desktop', 'columns_tablet', 'columns_mobile',
            'badge_text', 'categories',
        ]

    def get_categories(self, obj):
        block_cats = (
            obj.block_categories
            .select_related('category')
            .prefetch_related('category__items')
            .order_by('position', 'category__name')
        )
        # Filter: only active categories with at least one item
        active = [bc for bc in block_cats if bc.category.is_active]
        return PublicMenuLayoutBlockCategorySerializer(
            active, many=True, context=self.context
        ).data

