"""
accounts/employee_serializers.py — Serializers for EmployeeProfile management.

Covers:
  EmployeeProfileSerializer      — read-only representation (list + detail)
  CreateEmployeeSerializer       — validated write for POST /owner/employees/
  UpdateEmployeeSerializer       — validated write for PATCH /owner/employees/:id/
  EmployeeLoginSerializer        — validates operative login credentials
  EmployeeSessionSerializer      — formats the session payload returned after login
"""
from __future__ import annotations

import re

from django.contrib.auth.hashers import make_password
from rest_framework import serializers

from apps.accounts.models import EmployeeProfile


# ── Validation helpers ────────────────────────────────────────────────────────

_PIN_RE = re.compile(r'^\d{4,8}$')
_CODE_RE = re.compile(r'^[A-Z0-9\-]{1,20}$', re.IGNORECASE)

VALID_ROLE_TYPES = {c.value for c in EmployeeProfile.RoleType}
VALID_CREDENTIAL_TYPES = {c.value for c in EmployeeProfile.CredentialType}
VALID_STATUSES = {c.value for c in EmployeeProfile.Status}


def _hash_pin(pin: str) -> str:
    """Hash a raw PIN/code using Django's password hasher."""
    return make_password(pin)


# ── Read serializers ──────────────────────────────────────────────────────────

class EmployeeProfileSerializer(serializers.ModelSerializer):
    """
    Read-only representation of an EmployeeProfile.
    Intentionally omits login_code_hash and permission_overrides internal keys.
    """
    role_type_display = serializers.CharField(
        source='get_role_type_display', read_only=True
    )
    credential_type_display = serializers.CharField(
        source='get_credential_type_display', read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )
    branch_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeProfile
        fields = [
            'id',
            'first_name',
            'last_name',
            'alias',
            'employee_code',
            'role_type',
            'role_type_display',
            'credential_type',
            'credential_type_display',
            'must_change_pin',
            'status',
            'status_display',
            'branch',
            'branch_name',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_branch_name(self, obj: EmployeeProfile) -> str | None:
        return obj.branch.name if obj.branch else None

    def get_created_by_name(self, obj: EmployeeProfile) -> str | None:
        if obj.created_by_membership:
            u = obj.created_by_membership.user
            return u.get_full_name() or u.email
        return None


# ── Write serializers ─────────────────────────────────────────────────────────

class CreateEmployeeSerializer(serializers.Serializer):
    """Validates input for creating a new EmployeeProfile."""

    first_name      = serializers.CharField(max_length=120)
    last_name       = serializers.CharField(max_length=120)
    alias           = serializers.CharField(max_length=80, required=False, allow_blank=True, default='')
    employee_code   = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role_type       = serializers.ChoiceField(choices=list(VALID_ROLE_TYPES))
    credential_type = serializers.ChoiceField(
        choices=list(VALID_CREDENTIAL_TYPES),
        default=EmployeeProfile.CredentialType.PIN,
    )
    # Initial PIN (4-8 digits).  If omitted, a random one is generated and returned.
    initial_pin     = serializers.CharField(required=False, allow_blank=True)
    branch          = serializers.IntegerField(required=False, allow_null=True)

    def validate_initial_pin(self, value: str) -> str:
        if value and not _PIN_RE.match(value):
            raise serializers.ValidationError('El PIN debe tener entre 4 y 8 dígitos numéricos.')
        return value

    def validate_employee_code(self, value: str) -> str:
        if value and not _CODE_RE.match(value):
            raise serializers.ValidationError(
                'El código solo puede contener letras, números y guiones (máx. 20 caracteres).'
            )
        return value.upper() if value else value


class UpdateEmployeeSerializer(serializers.Serializer):
    """Validates input for PATCH /owner/employees/:id/."""

    first_name      = serializers.CharField(max_length=120, required=False)
    last_name       = serializers.CharField(max_length=120, required=False)
    alias           = serializers.CharField(max_length=80, required=False, allow_blank=True)
    role_type       = serializers.ChoiceField(choices=list(VALID_ROLE_TYPES), required=False)
    credential_type = serializers.ChoiceField(choices=list(VALID_CREDENTIAL_TYPES), required=False)
    branch          = serializers.IntegerField(required=False, allow_null=True)


class ResetPinSerializer(serializers.Serializer):
    """Validates input for POST /owner/employees/:id/reset-pin/."""
    new_pin = serializers.CharField(required=False, allow_blank=True)

    def validate_new_pin(self, value: str) -> str:
        if value and not _PIN_RE.match(value):
            raise serializers.ValidationError('El PIN debe tener entre 4 y 8 dígitos numéricos.')
        return value


# ── Operative login ───────────────────────────────────────────────────────────

class EmployeeLoginSerializer(serializers.Serializer):
    """Validates credentials for operative login."""
    business_id   = serializers.IntegerField()
    employee_code = serializers.CharField()
    pin           = serializers.CharField(trim_whitespace=False)


class EmployeeSessionSerializer(serializers.Serializer):
    """Formats the response payload after a successful operative login.

    This is used for documentation / explicit shaping; we build it manually
    in EmployeeLoginView rather than .data() because permissions must be
    resolved at runtime.
    """
    token          = serializers.CharField()
    actor_type     = serializers.CharField()
    employee_id    = serializers.CharField()
    employee_code  = serializers.CharField()
    display_name   = serializers.CharField()
    business_id    = serializers.IntegerField()
    business_name  = serializers.CharField()
    role_type      = serializers.CharField()
    must_change_pin = serializers.BooleanField()
    permissions    = serializers.DictField(child=serializers.BooleanField())


class ChangePinSerializer(serializers.Serializer):
    """Validates input for POST /auth/employee-change-pin/."""

    current_pin     = serializers.CharField(trim_whitespace=False, write_only=True)
    new_pin         = serializers.CharField(trim_whitespace=False, write_only=True)
    confirm_new_pin = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_new_pin(self, value: str) -> str:
        if not _PIN_RE.match(value):
            raise serializers.ValidationError(
                'El PIN debe tener entre 4 y 8 dígitos numéricos.'
            )
        return value

    def validate(self, data):
        if data.get('new_pin') != data.get('confirm_new_pin'):
            raise serializers.ValidationError(
                {'confirm_new_pin': 'Los PINs nuevos no coinciden.'}
            )
        if data.get('current_pin') == data.get('new_pin'):
            raise serializers.ValidationError(
                {'new_pin': 'El PIN nuevo debe ser diferente al PIN actual.'}
            )
        return data
