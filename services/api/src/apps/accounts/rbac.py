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
}

ALL_PERMISSIONS: Set[str] = GESTION_PERMISSIONS.union(RESTAURANT_PERMISSIONS)

SERVICE_ROLE_PERMISSIONS: Dict[str, Dict[str, Set[str]]] = {
  'gestion': {
    'owner': set(GESTION_PERMISSIONS),
    'admin': set(GESTION_PERMISSIONS),
    'manager': GESTION_PERMISSIONS - {'manage_users'},
    'cashier': {
      'view_dashboard',
      'view_sales',
      'create_sales',
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
}


def _normalize_role(role: str) -> str:
  return role or 'viewer'


def permissions_for_service(service: str, role: str) -> Dict[str, bool]:
  normalized_role = _normalize_role(role)
  baseline = {perm: False for perm in ALL_PERMISSIONS}
  allowed = SERVICE_ROLE_PERMISSIONS.get(service, {}).get(normalized_role)
  if allowed is None and normalized_role == 'admin':
    allowed = SERVICE_ROLE_PERMISSIONS.get(service, {}).get('owner', set())
  if allowed is None and normalized_role == 'analyst':
    allowed = SERVICE_ROLE_PERMISSIONS.get(service, {}).get('viewer', set())
  if not allowed:
    allowed = set()
  for perm in allowed:
    baseline[perm] = True
  return baseline


def list_permissions() -> Iterable[str]:
  return sorted(ALL_PERMISSIONS)
