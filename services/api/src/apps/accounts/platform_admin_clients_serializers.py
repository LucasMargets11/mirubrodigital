"""Input serializers for platform-admin client endpoints."""
from collections.abc import Mapping

from rest_framework import serializers


class StrictIntegerField(serializers.Field):
    """A JSON integer only: rejects booleans, floats (even 10.0) and strings."""

    default_error_messages = {'invalid': 'Debe ser un número entero.'}

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail('invalid')
        return data

    def to_representation(self, value):
        return value


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
    # PROD-02F3: individual allowance, only (and always) for reception_custom.
    # Shape here; range/placement rules live in grant_complimentary_access.
    custom_included_sessions = StrictIntegerField(required=False, allow_null=True)

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
        if value.get('custom_included_sessions') is None:
            value.pop('custom_included_sessions', None)
        return value
