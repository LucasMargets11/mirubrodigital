from __future__ import annotations

from rest_framework import serializers


class MercadoPagoConnectionStatusSerializer(serializers.Serializer):
    """Read-only connection status for the admin panel (never exposes tokens)."""
    connected = serializers.BooleanField()
    status = serializers.CharField(allow_null=True)
    mp_user_id = serializers.CharField(allow_blank=True, allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
