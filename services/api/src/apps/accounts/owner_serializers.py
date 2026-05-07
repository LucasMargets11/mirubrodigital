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
    email = serializers.CharField(allow_blank=True, default='')
    username = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    role_display = serializers.CharField()
    is_active = serializers.BooleanField()
    has_usable_password = serializers.BooleanField()
    membership_status = serializers.CharField(required=False, default='active')
    account_mode = serializers.CharField(required=False, default='owner_managed')
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
    pos_access_code = serializers.CharField(required=False, allow_null=True)


class PasswordResetResponseSerializer(serializers.Serializer):
    """Response for password reset operation."""
    success = serializers.BooleanField()
    message = serializers.CharField()
    temporary_password = serializers.CharField(required=False)
    username = serializers.CharField()
    email = serializers.CharField()


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for audit logs.

    Handles all three actor types:
      - USER     → actor FK set, actor_employee NULL
      - EMPLOYEE → actor NULL, actor_employee FK set
      - SYSTEM   → both NULL

    target_user can also be NULL for employee-only audit actions (e.g. cash flows).
    """
    actor_email = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()
    actor_type = serializers.CharField(read_only=True)
    actor_employee_code = serializers.SerializerMethodField()
    target_email = serializers.SerializerMethodField()
    target_name = serializers.SerializerMethodField()
    entity_type = serializers.CharField(read_only=True)
    entity_id = serializers.CharField(read_only=True)

    class Meta:
        model = AccessAuditLog
        fields = [
            'id',
            'action',
            'actor_type',
            'actor_email',
            'actor_name',
            'actor_employee_code',
            'target_email',
            'target_name',
            'entity_type',
            'entity_id',
            'details',
            'ip_address',
            'created_at',
        ]

    def get_actor_email(self, obj):
        if obj.actor:
            return obj.actor.email
        return None

    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        if obj.actor_employee:
            emp = obj.actor_employee
            return emp.alias or f'{emp.first_name} {emp.last_name}'.strip()
        return 'Sistema'

    def get_actor_employee_code(self, obj):
        if obj.actor_employee:
            return obj.actor_employee.employee_code
        return None

    def get_target_email(self, obj):
        if obj.target_user:
            return obj.target_user.email
        return None

    def get_target_name(self, obj):
        if obj.target_user:
            return obj.target_user.get_full_name() or obj.target_user.username
        return None


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


class CreateMemberSerializer(serializers.Serializer):
    """Input for creating an internal user (member) by the owner."""
    first_name = serializers.CharField(max_length=150, help_text='Nombre')
    last_name = serializers.CharField(max_length=150, help_text='Apellido')
    username = serializers.RegexField(
        regex=r'^[a-zA-Z0-9._-]+$',
        min_length=3,
        max_length=150,
        help_text='Nombre de usuario (letras, números, punto, guión o guión bajo)',
        error_messages={
            'invalid': 'El nombre de usuario solo puede contener letras, números, punto (.), guión (-) o guión bajo (_).',
        },
    )
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False, write_only=True)
    role = serializers.CharField(max_length=24)
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    account_mode = serializers.ChoiceField(
        choices=['owner_managed', 'personal'],
        default='owner_managed',
        required=False,
        help_text='Modo de la cuenta: owner_managed (gestionada por el dueño) o personal',
    )
    force_password_change = serializers.BooleanField(
        default=False,
        required=False,
        help_text='Si es True, el usuario deberá cambiar su contraseña en el próximo inicio de sesión',
    )


class CreateMemberResponseSerializer(serializers.Serializer):
    """Response after creating an internal user."""
    success = serializers.BooleanField()
    message = serializers.CharField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    role_display = serializers.CharField()


class SetPasswordSerializer(serializers.Serializer):
    """Input for owner-initiated password reset with explicit password."""
    new_password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False, write_only=True)
