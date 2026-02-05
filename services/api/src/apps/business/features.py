from typing import Dict, Iterable

BASE_ALWAYS_ON: Iterable[str] = ('dashboard', 'services', 'settings')
FEATURE_KEYS: Iterable[str] = (
  'dashboard',
  'services',
  'products',
  'inventory',
  'stock',
  'sales',
  'customers',
  'invoices',
  'cash',
  'reports',
  'orders',
  'tables',
  'whatsapp_bot',
  'resto_orders',
  'resto_kitchen',
  'resto_sales',
  'resto_tables',
  'resto_recipes',
  'resto_menu',
  'resto_reports',
  'settings',
  'menu_builder',
  'menu_branding',
  'public_menu',
  'menu_qr_tools',
)

PLAN_FEATURES: Dict[str, Iterable[str]] = {
  'starter': ('products', 'inventory', 'stock', 'sales', 'customers'),
  'pro': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'reports'),
  'plus': (
    'products',
    'inventory',
    'stock',
    'sales',
    'customers',
    'invoices',
    'cash',
    'reports',
    'orders',
    'tables',
    'whatsapp_bot',
    'resto_orders',
    'resto_kitchen',
    'resto_sales',
    'resto_tables',
    'resto_recipes',
    'resto_menu',
    'resto_reports',
  ),
  'menu_qr': (
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
  ),
}


def feature_flags_for_plan(plan: str) -> Dict[str, bool]:
  normalized_plan = plan if plan in PLAN_FEATURES else 'starter'
  flags = {key: False for key in FEATURE_KEYS}
  for key in BASE_ALWAYS_ON:
    flags[key] = True
  for key in PLAN_FEATURES[normalized_plan]:
    flags[key] = True
  return flags
