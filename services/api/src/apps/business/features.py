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
  'quotes',
  'treasury',
  'reports',
  'multi_branch',
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
  # Legacy plans
  'starter': ('products', 'inventory', 'stock', 'sales', 'customers'),
  'plus': (
    'products',
    'inventory',
    'stock',
    'sales',
    'customers',
    'invoices',
    'cash',
    'quotes',
    'treasury',
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
  # New plans (Gestión Comercial)
  'start': ('products', 'inventory', 'stock', 'sales'),
  'pro': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports'),
  'business': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports', 'multi_branch'),
  'enterprise': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports', 'multi_branch'),
  # Menu QR
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


def feature_flags_for_subscription(subscription) -> Dict[str, bool]:
  """
  Calcula feature flags basados en la subscription completa,
  incluyendo addons activos.
  """
  if subscription is None:
    return feature_flags_for_plan('starter')
  
  plan = subscription.plan
  flags = feature_flags_for_plan(plan)
  
  # PRO: habilitar multi_branch si tiene addon de sucursales extras
  if plan == 'pro' and subscription.effective_max_branches > 1:
    flags['multi_branch'] = True
  
  return flags
