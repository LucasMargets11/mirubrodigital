from __future__ import annotations

from typing import Dict, Iterable, Set

GESTION_PERMISSIONS: Set[str] = {
  'view_dashboard',
  'view_products',
  'manage_products',
  'view_stock',
  'manage_stock',
  'view_sales',
  'create_sales',
  'cancel_sales',
  'view_quotes',
  'create_quotes',
  'manage_quotes',
  'send_quotes',
  'view_invoices',
  'issue_invoices',
  'void_invoices',
  'view_customers',
  'manage_customers',
  'view_cash',
  'manage_cash',
  'view_reports',
  'view_reports_sales',
  'view_reports_cash',
  'view_reports_products',
  'export_reports',
  'manage_users',
  'manage_settings',
  'manage_commercial_settings',
  'view_finance',
  'manage_finance',
}

RESTAURANT_PERMISSIONS: Set[str] = {
  'view_restaurant_dashboard',
  'view_orders',
  'create_orders',
  'edit_orders',
  'change_order_status',
  'close_orders',
  'view_tables',
  'manage_tables',
  'view_menu',
  'manage_menu',
  'import_menu',
  'export_menu',
  'view_kitchen_board',
  'kitchen_update_status',
  'view_cash',
  'manage_cash',
  'view_restaurant_reports',
  'manage_users',
  'manage_settings',
  'manage_whatsapp_bot',
  'manage_menu_branding',
  'view_menu_admin',
  'view_public_menu',
}

MENU_QR_PERMISSIONS: Set[str] = {
  'view_menu',
  'manage_menu',
  'manage_menu_branding',
  'view_menu_admin',
  'view_public_menu',
  'manage_settings',
  'manage_users',
}

ALL_PERMISSIONS: Set[str] = GESTION_PERMISSIONS.union(RESTAURANT_PERMISSIONS).union(MENU_QR_PERMISSIONS)

SERVICE_ROLE_PERMISSIONS: Dict[str, Dict[str, Set[str]]] = {
  'gestion': {
    'owner': set(GESTION_PERMISSIONS),
    'admin': set(GESTION_PERMISSIONS),
    'manager': GESTION_PERMISSIONS - {'manage_users'},
    'cashier': {
      'view_dashboard',
      'view_sales',
      'create_sales',
      'view_quotes',
      'create_quotes',
      'send_quotes',
      'view_invoices',
      'issue_invoices',
      'view_customers',
      'manage_customers',
      'view_cash',
      'manage_cash',
      'view_reports_cash',
      'view_finance',
    },
    'staff': {
      'view_dashboard',
      'view_products',
      'view_stock',
      'view_sales',
      'create_sales',
      'view_quotes',
      'create_quotes',
      'view_invoices',
      'view_customers',
      'manage_customers',
      'view_reports',
      'view_reports_sales',
      'view_reports_products',
    },
    'viewer': {
      'view_dashboard',
      'view_products',
      'view_stock',
      'view_sales',
      'view_quotes',
      'view_invoices',
      'view_customers',
      'view_cash',
      'view_reports',
      'view_reports_sales',
      'view_reports_cash',
      'view_reports_products',
    },
    'analyst': {
      'view_dashboard',
      'view_products',
      'view_stock',
      'view_sales',
      'view_quotes',
      'view_invoices',
      'view_customers',
      'view_cash',
      'view_reports',
      'view_reports_sales',
      'view_reports_cash',
      'view_reports_products',
    },
  },
  'restaurante': {
    'owner': set(RESTAURANT_PERMISSIONS) | GESTION_PERMISSIONS,
    'admin': set(RESTAURANT_PERMISSIONS) | GESTION_PERMISSIONS,
    'manager': RESTAURANT_PERMISSIONS - {'manage_users', 'manage_whatsapp_bot'},
    'salon': {
      'view_orders',
      'create_orders',
      'edit_orders',
      'change_order_status',
      'view_tables',
      'manage_tables',
      'view_menu',
    },
    'kitchen': {
      'view_orders',
      'view_kitchen_board',
      'kitchen_update_status',
    },
    'cashier': {
      'view_orders',
      'change_order_status',
      'close_orders',
      'view_cash',
      'manage_cash',
      'view_tables',
    },
    'viewer': {
      'view_orders',
      'view_tables',
      'view_menu',
      'view_kitchen_board',
      'view_restaurant_reports',
    },
  },
  'menu_qr': {
    'owner': set(MENU_QR_PERMISSIONS),
    'manager': MENU_QR_PERMISSIONS - {'manage_users'},
    'staff': {
      'view_menu',
      'manage_menu',
      'view_menu_admin',
      'view_public_menu',
    },
    'viewer': {
      'view_menu',
      'view_menu_admin',
      'view_public_menu',
    },
  },
}


def _normalize_role(role: str) -> str:
  return role or 'viewer'


def permissions_for_service(service: str, role: str, business=None) -> Dict[str, bool]:
  """
  Get permissions for a role in a service.
  
  Args:
    service: Service name (gestion, restaurante, menu_qr)
    role: Role name (owner, manager, cashier, etc)
    business: Business instance (optional). If provided, applies custom overrides.
  
  Returns:
    Dict mapping permission keys to boolean enabled status
  """
  normalized_role = _normalize_role(role)
  
  # Start with all permissions disabled
  baseline = {perm: False for perm in ALL_PERMISSIONS}
  
  # Get default permissions for this role from hardcoded config
  allowed = SERVICE_ROLE_PERMISSIONS.get(service, {}).get(normalized_role)
  if allowed is None and normalized_role == 'admin':
    allowed = SERVICE_ROLE_PERMISSIONS.get(service, {}).get('owner', set())
  if allowed is None and normalized_role == 'analyst':
    allowed = SERVICE_ROLE_PERMISSIONS.get(service, {}).get('viewer', set())
  if not allowed:
    allowed = set()
  
  # Apply default permissions
  for perm in allowed:
    baseline[perm] = True
  
  # Apply business-specific overrides if business is provided
  if business:
    from apps.accounts.models import RolePermissionOverride
    overrides = RolePermissionOverride.objects.filter(
      business=business,
      service=service,
      role=normalized_role
    )
    for override in overrides:
      baseline[override.permission] = override.enabled
  
  return baseline


def list_permissions() -> Iterable[str]:
  return sorted(ALL_PERMISSIONS)
