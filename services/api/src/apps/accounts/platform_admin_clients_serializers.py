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


class StrictBooleanField(serializers.Field):
    """A JSON boolean only: rejects "true", 1 and every other truthy value."""

    default_error_messages = {'invalid': 'Debe ser true o false.'}

    def to_internal_value(self, data):
        if type(data) is not bool:
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
    # PROD-02F4: explicit confirmation to attach an EXISTING account as owner.
    # The token is the one returned by the 409 confirmation prompt; it is
    # bound server-side to the resolved identity and the admin.
    attach_existing_owner = StrictBooleanField(required=False)
    owner_confirmation_token = serializers.CharField(
        required=False, allow_blank=False, max_length=255, trim_whitespace=True,
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
        if value.get('custom_included_sessions') is None:
            value.pop('custom_included_sessions', None)
        attach = value.pop('attach_existing_owner', False)
        token = value.pop('owner_confirmation_token', None)
        if attach and not token:
            raise serializers.ValidationError({
                'owner_confirmation_token': ['Requerido para asociar una cuenta existente.'],
            })
        if token and not attach:
            raise serializers.ValidationError({
                'attach_existing_owner': ['Debe ser true cuando se envía una confirmación.'],
            })
        if attach:
            value['attach_existing_owner'] = True
            value['owner_confirmation_token'] = token
        return value
