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
  # Premium QR menu features
  'menu_item_images',
  'menu_custom_domain',
  # Engagement features (Fase 1+)
  'menu_qr_reviews',   # Google Reviews CTA on public carta
  'menu_qr_tips',      # Tip CTA on public carta (MP link / QR image)
  'menu_qr_tips_pro',  # Dynamic tip amount via MP OAuth Checkout (Fase 2)
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
    # Restaurante Inteligente includes the full Menú QR Online feature set
    # (including images), so that feature-gated QR menu UI elements are shown.
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
    'menu_item_images',
    'menu_qr_reviews',
    'menu_qr_tips',
  ),
  # New plans (Gestión Comercial)
  'start': ('products', 'inventory', 'stock', 'sales'),
  'pro': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports'),
  'business': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports', 'multi_branch'),
  'enterprise': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports', 'multi_branch'),
  # Menu QR Básico (standalone — sin imágenes)
  'menu_qr': (
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
    'menu_qr_reviews',
    'menu_qr_tips',
  ),
  # Menu QR Visual — con imágenes por producto
  'menu_qr_visual': (
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
    'menu_item_images',
    'menu_qr_reviews',
    'menu_qr_tips',
  ),
  # Menu QR Marca — con imágenes + dominio personalizado
  'menu_qr_marca': (
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
    'menu_item_images',
    'menu_custom_domain',
    'menu_qr_reviews',
    'menu_qr_tips',
    'menu_qr_tips_pro',
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
