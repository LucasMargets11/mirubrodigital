from __future__ import annotations

from rest_framework import serializers

from .models import Review, ReviewConfig, ReviewStatus


class ReviewConfigSerializer(serializers.ModelSerializer):
    """Private serializer for dashboard — full read/write access."""

    redirect_url = serializers.ReadOnlyField()

    class Meta:
        model = ReviewConfig
        fields = [
            'enabled',
            'google_place_id',
            'google_review_url',
            'custom_redirect_url',
            'redirect_threshold',
            'collect_contact',
            'thank_you_message',
            'redirect_url',
            'updated_at',
        ]
        read_only_fields = ['redirect_url', 'updated_at']

    def validate_redirect_threshold(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError('El umbral debe estar entre 1 y 5.')
        return value

    def validate_google_review_url(self, value):
        if value and not value.startswith('http'):
            raise serializers.ValidationError('Ingresá una URL válida.')
        return value

    def validate_custom_redirect_url(self, value):
        if value and not value.startswith('http'):
            raise serializers.ValidationError('Ingresá una URL válida.')
        return value


class PublicReviewConfigSerializer(serializers.ModelSerializer):
    """Public serializer — only exposes what the landing page needs."""

    business_name = serializers.CharField(source='business.name', read_only=True)
    redirect_url = serializers.ReadOnlyField()

    class Meta:
        model = ReviewConfig
        fields = [
            'business_name',
            'redirect_url',
            'redirect_threshold',
            'collect_contact',
            'thank_you_message',
            'enabled',
        ]


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
