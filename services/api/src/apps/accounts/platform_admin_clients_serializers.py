"""Input serializers for platform-admin client endpoints."""
from collections.abc import Mapping

from rest_framework import serializers


class AdminClientProvisioningInputSerializer(serializers.Serializer):
    """Validate only the HTTP shape accepted by client provisioning."""

    business_name = serializers.CharField(allow_blank=True, trim_whitespace=False)
    business_slug = serializers.CharField(allow_blank=True, trim_whitespace=False)
    service_type = serializers.CharField(allow_blank=True, trim_whitespace=False)
    country = serializers.CharField(allow_blank=True, trim_whitespace=False)
    currency = serializers.CharField(allow_blank=True, trim_whitespace=False)
    owner_email = serializers.EmailField()
    plan_code = serializers.CharField(allow_blank=True, trim_whitespace=False)
    complimentary_start = serializers.DateTimeField()
    complimentary_end = serializers.DateTimeField()
    grant_reason = serializers.CharField(allow_blank=True, trim_whitespace=False)
    # Only tier-priced plans (Turnos IA) use it; the domain service rejects it
    # for every other plan and requires it for those.
    usage_tier = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, trim_whitespace=True,
    )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = sorted(set(data) - set(self.fields))
            if unknown_fields:
                raise serializers.ValidationError({
                    field: ['Campo no permitido.']
                    for field in unknown_fields
                })
        value = super().to_internal_value(data)
        if not value.get('usage_tier'):
            value.pop('usage_tier', None)
        return value
