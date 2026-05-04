"""
business/onboarding_serializers.py — Serializers for the Gestión Comercial
embedded onboarding wizard (MVP v1).

These serializers handle input validation only.  Response serialization is
done inline in the views because the context response aggregates data from
multiple models.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.business.models import BusinessOnboardingProgress


# ── Skippable step IDs ────────────────────────────────────────────────────────
SKIPPABLE_STEPS = {'business_basics', 'first_product'}
VALID_STEPS = {'business_basics', 'first_product', 'sales_setup'}


class BusinessBasicsSerializer(serializers.Serializer):
    business_name = serializers.CharField(min_length=2, max_length=120, trim_whitespace=True)
    phone = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)


class FirstProductSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=255, trim_whitespace=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))
    cost = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        min_value=Decimal('0'),
        required=False, allow_null=True,
    )
    category_id = serializers.UUIDField(required=False, allow_null=True)
    category_name = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True,
        trim_whitespace=True,
    )
    initial_stock = serializers.DecimalField(
        max_digits=12, decimal_places=3,
        min_value=Decimal('0'),
        required=False, allow_null=True,
    )


class SkipStepSerializer(serializers.Serializer):
    step_id = serializers.ChoiceField(choices=list(SKIPPABLE_STEPS))

    def validate_step_id(self, value: str) -> str:
        if value not in SKIPPABLE_STEPS:
            raise serializers.ValidationError(
                f'El paso "{value}" no se puede saltar. '
                f'Pasos saltables: {", ".join(sorted(SKIPPABLE_STEPS))}.'
            )
        return value


class OnboardingProgressSerializer(serializers.ModelSerializer):
    """Read-only serializer for embedding progress in responses."""
    class Meta:
        model = BusinessOnboardingProgress
        fields = [
            'product_type', 'version', 'current_step',
            'skipped_steps', 'completed_at', 'dismissed_at',
        ]
        read_only_fields = fields
