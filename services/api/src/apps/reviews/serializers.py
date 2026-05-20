from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import Review, ReviewConfig, ReviewMode, ReviewStatus


class ReviewConfigSerializer(serializers.ModelSerializer):
    """Private serializer for dashboard — full read/write access."""

    redirect_url = serializers.ReadOnlyField()
    effective_mode = serializers.ReadOnlyField()
    smart_filter_allowed = serializers.SerializerMethodField()
    is_reviews_pro = serializers.SerializerMethodField()
    trial_active = serializers.SerializerMethodField()
    trial_available = serializers.SerializerMethodField()

    class Meta:
        model = ReviewConfig
        fields = [
            'enabled',
            'google_place_id',
            'google_place_name',
            'google_place_formatted_address',
            'google_place_updated_at',
            'google_review_url',
            'custom_redirect_url',
            'redirect_threshold',
            'collect_contact',
            'thank_you_message',
            'redirect_url',
            'mode',
            'effective_mode',
            'trial_ends_at',
            'trial_used',
            'smart_filter_allowed',
            'is_reviews_pro',
            'trial_active',
            'trial_available',
            'updated_at',
        ]
        read_only_fields = [
            'redirect_url',
            'effective_mode',
            'trial_ends_at',
            'trial_used',
            'smart_filter_allowed',
            'is_reviews_pro',
            'trial_active',
            'trial_available',
            'google_place_updated_at',
            'updated_at',
        ]

    def validate_redirect_threshold(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError('El umbral debe estar entre 1 y 5.')
        return value

    def validate_google_review_url(self, value):
        if value and not value.startswith('http'):
            raise serializers.ValidationError('Ingresá una URL válida.')
        return value

    def validate_custom_redirect_url(self, value):
        if value and not value.startswith('https://'):
            raise serializers.ValidationError('La URL debe comenzar con https://.')
        return value

    def validate_mode(self, value):
        """Prevent Base plans from persisting smart_filter without entitlement."""
        if value == ReviewMode.SMART_FILTER:
            business = self.instance.business if self.instance else None
            if business:
                from .entitlements import smart_filter_allowed
                if not smart_filter_allowed(business):
                    raise serializers.ValidationError(
                        'El filtro inteligente no está disponible en tu plan actual.'
                    )
        return value

    def get_smart_filter_allowed(self, obj) -> bool:
        from .entitlements import smart_filter_allowed
        return smart_filter_allowed(obj.business)

    def get_is_reviews_pro(self, obj) -> bool:
        from .entitlements import is_reviews_pro
        return is_reviews_pro(obj.business)

    def get_trial_active(self, obj) -> bool:
        from .entitlements import trial_active
        return trial_active(obj.business)

    def get_trial_available(self, obj) -> bool:
        from .entitlements import trial_available
        return trial_available(obj.business)

    def update(self, instance, validated_data):
        """Auto-set snapshot timestamp and review URL when Place ID changes."""
        new_place_id = validated_data.get('google_place_id')
        if new_place_id is not None and new_place_id != instance.google_place_id:
            validated_data['google_place_updated_at'] = timezone.now()
            # Auto-populate review URL from Place ID if not explicitly provided
            if 'google_review_url' not in validated_data and new_place_id:
                validated_data['google_review_url'] = (
                    f"https://search.google.com/local/writereview?placeid={new_place_id}"
                )
            # Clear snapshot fields if Place ID is being cleared
            if not new_place_id:
                validated_data.setdefault('google_place_name', '')
                validated_data.setdefault('google_place_formatted_address', '')
                validated_data.setdefault('google_review_url', '')
        return super().update(instance, validated_data)


class PublicReviewConfigSerializer(serializers.ModelSerializer):
    """Public serializer — only exposes what the landing page needs."""

    business_name = serializers.CharField(source='business.name', read_only=True)
    redirect_url = serializers.ReadOnlyField()
    effective_mode = serializers.ReadOnlyField()
    logo_url = serializers.SerializerMethodField()
    accent_color = serializers.SerializerMethodField()
    is_pro = serializers.SerializerMethodField()

    class Meta:
        model = ReviewConfig
        fields = [
            'business_name',
            'redirect_url',
            'redirect_threshold',
            'collect_contact',
            'thank_you_message',
            'enabled',
            'mode',
            'effective_mode',
            'logo_url',
            'accent_color',
            'is_pro',
        ]

    def get_logo_url(self, obj) -> str | None:
        branding = getattr(obj.business, 'branding', None)
        if not branding:
            return None
        logo = branding.logo_horizontal or branding.logo_square
        if logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(logo.url)
            return logo.url
        return None

    def get_accent_color(self, obj) -> str | None:
        branding = getattr(obj.business, 'branding', None)
        if branding and branding.accent_color:
            return branding.accent_color
        return None

    def get_is_pro(self, obj) -> bool:
        from .entitlements import is_reviews_pro
        return is_reviews_pro(obj.business)


class ReviewSubmitSerializer(serializers.Serializer):
    """Validates public review submission."""

    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=2000, required=False, default='', allow_blank=True)
    contact_info = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    source = serializers.ChoiceField(
        choices=[('qr', 'QR'), ('menu', 'Menu'), ('direct', 'Direct')],
        default='qr',
    )


class ReviewSerializer(serializers.ModelSerializer):
    """Private serializer for listing/detail of submitted reviews."""

    class Meta:
        model = Review
        fields = [
            'id',
            'rating',
            'comment',
            'contact_info',
            'source',
            'status',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'rating',
            'comment',
            'contact_info',
            'source',
            'created_at',
        ]


class ReviewStatusUpdateSerializer(serializers.Serializer):
    """Only allows updating the status field with strict transition rules."""

    VALID_TRANSITIONS: dict[str, set[str]] = {
        'new': {'read'},
        'read': {'contacted'},
        'contacted': {'resolved'},
        'resolved': {'read'},
    }

    status = serializers.ChoiceField(choices=ReviewStatus.choices)

    def validate_status(self, value):
        current_status = self.context.get('current_status')
        if current_status is not None:
            allowed = self.VALID_TRANSITIONS.get(current_status, set())
            if value not in allowed:
                allowed_str = ', '.join(sorted(allowed)) if allowed else 'ninguna'
                raise serializers.ValidationError(
                    f'Transición no permitida: {current_status} → {value}. '
                    f'Transiciones válidas desde "{current_status}": {allowed_str}.'
                )
        return value
