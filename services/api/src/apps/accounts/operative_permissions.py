"""
accounts/operative_permissions.py — Permission resolution for EmployeeProfile.

Bridges EmployeeProfile.RoleType values → SERVICE_ROLE_PERMISSIONS role keys,
then applies per-employee permission_overrides on top.

Usage
-----
    from apps.accounts.operative_permissions import resolve_employee_permissions

    perms = resolve_employee_permissions(employee, service='restaurante')
    # → {'view_orders': True, 'create_orders': True, 'manage_cash': False, ...}

The returned dict has the SAME shape as permissions_for_service() so the
frontend can consume both admin and employee permissions identically.
"""
from __future__ import annotations

from typing import Dict, Set

from apps.accounts.rbac import permissions_for_service, ALL_PERMISSIONS


# ── Role type → rbac role mapping ─────────────────────────────────────────────
# Maps EmployeeProfile.RoleType values to the closest role in SERVICE_ROLE_PERMISSIONS.
# The mapping is service-aware: 'server' maps to 'salon' in restaurante (where that
# role exists) but falls back to 'cashier' in gestion (POS operator context).

_EMPLOYEE_ROLE_MAP: Dict[str, Dict[str, str]] = {
    'gestion': {
        'cashier':    'cashier',
        'server':     'staff',      # gestion has no dedicated server role
        'kitchen':    'viewer',     # kitchen staff in gestion → read-only
        'delivery':   'cashier',    # delivery acts like a cashier in gestion
        'manager_op': 'manager',
    },
    'restaurante': {
        'cashier':    'cashier',
        'server':     'salon',
        'kitchen':    'kitchen',
        'delivery':   'cashier',    # delivery = cashier-level
        'manager_op': 'manager',
    },
    'menu_qr': {
        'cashier':    'staff',
        'server':     'staff',
        'kitchen':    'viewer',
        'delivery':   'viewer',
        'manager_op': 'manager',
    },
}

# Fallback when service is unknown or employee role is unknown
_FALLBACK_ROLE = 'viewer'


def _map_role(employee_role_type: str, service: str) -> str:
    """Return the rbac role key for the given employee role type and service."""
    service_map = _EMPLOYEE_ROLE_MAP.get(service, {})
    return service_map.get(employee_role_type, _FALLBACK_ROLE)


def resolve_employee_permissions(employee, service: str) -> Dict[str, bool]:
    """
    Resolve the effective permissions for an EmployeeProfile.

    Pipeline:
      1. Map employee.role_type → rbac role for the given service.
      2. Fetch base permissions from permissions_for_service() (which also
         applies any RolePermissionOverride rows for the business).
      3. Apply employee.permission_overrides on top (individual overrides
         stored as {permission_code: bool}).

    Returns a Dict[str, bool] with the union of ALL_PERMISSIONS as keys so
    the frontend receives a stable, complete map regardless of service.
    """
    rbac_role = _map_role(employee.role_type, service)

    # Base permissions from the role (includes business overrides)
    base_perms = permissions_for_service(service, rbac_role, employee.business)

    # Fill in missing keys from other services with False
    effective: Dict[str, bool] = {perm: False for perm in ALL_PERMISSIONS}
    effective.update(base_perms)

    # Apply per-employee overrides (skipping internal metadata keys like _migrated_from)
    overrides = employee.permission_overrides or {}
    for code, value in overrides.items():
        if not code.startswith('_') and code in ALL_PERMISSIONS and isinstance(value, bool):
            effective[code] = value

    return effective


def employee_permissions_summary(employee, service: str) -> Dict[str, bool]:
    """
    Convenience: return only the GRANTED permissions (True values).
    Used for session payloads where a sparse dict is preferred over the full matrix.
    """
    perms = resolve_employee_permissions(employee, service)
    return {code: True for code, granted in perms.items() if granted}


# ── POS operational capabilities ──────────────────────────────────────────────
#
# Explicit, centralized capability matrix for operative terminals.
# These model what the POS terminal itself permits a given role to DO —
# they are independent of the dashboard RBAC system.
#
# Keys are stable identifiers consumed by the POS frontend.
# Per-employee permission_overrides that match a capability key are applied
# on top of role defaults.

_POS_ROLE_CAPABILITIES: Dict[str, Set[str]] = {
    'manager_op': {
        'can_open_pos',
        'can_view_assigned_branch',
        'can_create_sale',
        'can_refund_sale',
        'can_manage_cash',
        'can_view_reports',
        'can_manage_employees_pos',
        # Cash session capabilities (granular)
        'can_open_cash',
        'can_close_cash',
        'can_register_cash_movement',
    },
    'cashier': {
        'can_open_pos',
        'can_view_assigned_branch',
        'can_create_sale',
        'can_manage_cash',
        # Cash session capabilities (granular)
        'can_open_cash',
        'can_close_cash',
        'can_register_cash_movement',
    },
    'server': {
        'can_open_pos',
        'can_view_assigned_branch',
        'can_create_sale',
    },
    'kitchen': {
        'can_open_pos',
        'can_view_assigned_branch',
    },
    'delivery': {
        'can_open_pos',
        'can_view_assigned_branch',
        'can_create_sale',
    },
}

# Frozen union of all capability keys — used to produce a stable response shape.
_ALL_CAPABILITIES: frozenset = frozenset().union(*_POS_ROLE_CAPABILITIES.values())


def resolve_pos_capabilities(employee) -> Dict[str, bool]:
    """
    Return a stable dict of all POS capabilities with True/False values
    for the given employee's role_type.

    Per-employee permission_overrides that match a capability key are
    applied on top of role defaults, allowing individual overrides.
    """
    role_caps: Set[str] = _POS_ROLE_CAPABILITIES.get(employee.role_type, set())
    result: Dict[str, bool] = {cap: cap in role_caps for cap in _ALL_CAPABILITIES}

    # Apply per-employee overrides for capability keys
    overrides = employee.permission_overrides or {}
    for key, value in overrides.items():
        if key in _ALL_CAPABILITIES and isinstance(value, bool):
            result[key] = value

    return result
