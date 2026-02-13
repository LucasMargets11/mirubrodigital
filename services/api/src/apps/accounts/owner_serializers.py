"""
Serializers for Owner Access Management endpoints.
"""
from __future__ import annotations

from typing import Dict, List

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import Membership, AccessAuditLog
from apps.accounts.rbac import permissions_for_service
from apps.accounts.rbac_registry import get_registry

User = get_user_model()


class CapabilitySerializer(serializers.Serializer):
    """Serializer for individual capability/permission."""
    code = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    module = serializers.CharField()
    service = serializers.CharField()
    granted = serializers.BooleanField(default=False)


class RoleSummarySerializer(serializers.Serializer):
    """Summary of a role with permission count."""
    role = serializers.CharField()
    role_display = serializers.CharField()
    user_count = serializers.IntegerField()
    permission_count = serializers.IntegerField()


class UserAccountSerializer(serializers.Serializer):
    """Serializer for user account in access management."""
    id = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    role_display = serializers.CharField()
    is_active = serializers.BooleanField()
    has_usable_password = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)


class RoleDetailSerializer(serializers.Serializer):
    """Detailed view of a role with permissions and users."""
    role = serializers.CharField()
    role_display = serializers.CharField()
    description = serializers.CharField()
    service = serializers.CharField()
    permissions_by_module = serializers.DictField()
    users = UserAccountSerializer(many=True)


class AccessSummarySerializer(serializers.Serializer):
    """Summary of current user's access."""
    user_id = serializers.IntegerField()
    role = serializers.CharField()
    role_display = serializers.CharField()
    business_name = serializers.CharField()
    service = serializers.CharField()
    permissions_by_module = serializers.DictField()


class PasswordResetResponseSerializer(serializers.Serializer):
    """Response for password reset operation."""
    success = serializers.BooleanField()
    message = serializers.CharField()
    temporary_password = serializers.CharField(required=False)
    username = serializers.CharField()
    email = serializers.CharField()


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for audit logs."""
    actor_email = serializers.EmailField(source='actor.email', allow_null=True)
    actor_name = serializers.SerializerMethodField()
    target_email = serializers.EmailField(source='target_user.email')
    target_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AccessAuditLog
        fields = [
            'id',
            'action',
            'actor_email',
            'actor_name',
            'target_email',
            'target_name',
            'details',
            'ip_address',
            'created_at',
        ]
    
    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return 'Sistema'
    
    def get_target_name(self, obj):
        return obj.target_user.get_full_name() or obj.target_user.username


def get_role_description(role: str, service: str) -> str:
    """Get human-friendly description for a role."""
    descriptions = {
        'gestion': {
            'owner': 'Control total del negocio. Puede gestionar usuarios, configuración y acceder a toda la información.',
            'admin': 'Acceso completo a todas las funcionalidades. Similar a Owner pero no puede eliminar el negocio.',
            'manager': 'Gestión completa de operaciones diarias. No puede administrar usuarios.',
            'cashier': 'Enfocado en ventas y caja. Puede vender, facturar y gestionar la caja.',
            'staff': 'Acceso a ventas y consultas. Puede vender y ver reportes básicos.',
            'viewer': 'Solo lectura. Puede consultar información pero no realizar cambios.',
            'analyst': 'Acceso a reportes y análisis. No puede modificar datos operativos.',
        },
        'restaurante': {
            'owner': 'Control total del restaurante. Acceso a todos los módulos y configuración.',
            'admin': 'Acceso completo a todas las funcionalidades del restaurante.',
            'manager': 'Gestión del restaurante. Puede administrar pedidos, menú y operación diaria.',
            'salon': 'Personal de salón. Toma pedidos, asigna mesas y actualiza estados.',
            'kitchen': 'Personal de cocina. Ve pedidos pendientes y actualiza estado de preparación.',
            'cashier': 'Personal de caja. Cobra pedidos y gestiona la caja.',
            'viewer': 'Solo lectura. Puede consultar pedidos, mesas y reportes.',
        },
        'menu_qr': {
            'owner': 'Control total del menú QR. Gestiona contenido y usuarios.',
            'manager': 'Gestión del menú. Puede editar productos y personalización.',
            'staff': 'Editor del menú. Puede actualizar productos y disponibilidad.',
            'viewer': 'Solo lectura. Puede consultar el menú pero no editarlo.',
        }
    }
    
    service_descriptions = descriptions.get(service, {})
    return service_descriptions.get(role, f'Rol {role} en el servicio {service}')


class PermissionUpdateSerializer(serializers.Serializer):
    """Serializer for updating a single permission."""
    permission = serializers.CharField(help_text='Permission code to update')
    enabled = serializers.BooleanField(help_text='Whether to enable or disable this permission')


class BulkPermissionUpdateSerializer(serializers.Serializer):
    """Serializer for bulk permission updates."""
    permissions = PermissionUpdateSerializer(many=True, help_text='List of permission updates')
    
    def validate_permissions(self, value):
        """Ensure at least one permission is being updated."""
        if not value:
            raise serializers.ValidationError('Debe especificar al menos un permiso para actualizar')
        return value


class PermissionUpdateResponseSerializer(serializers.Serializer):
    """Response after updating permissions."""
    success = serializers.BooleanField()
    message = serializers.CharField()
    role = serializers.CharField()
    service = serializers.CharField()
    updated_count = serializers.IntegerField()
    permissions_by_module = serializers.DictField()
