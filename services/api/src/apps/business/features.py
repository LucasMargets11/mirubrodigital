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
  # 4 planes oficiales Gestión Comercial
  'starter': ('products', 'inventory', 'stock', 'sales', 'orders'),
  'pro': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports', 'orders'),
  'business': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports', 'multi_branch', 'orders'),
  'enterprise': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'quotes', 'treasury', 'reports', 'multi_branch', 'orders'),
  # Legacy aliases
  'start': ('products', 'inventory', 'stock', 'sales', 'orders'),
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
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
    'menu_item_images',
    'menu_qr_reviews',
    'menu_qr_tips',
  ),
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
  # ── Nuevos planes Menú QR ────────────────────────────────────────────────
  # Lite: carta digital básica, sin imágenes, sin engagement (reviews/tips)
  'menu_qr_lite': (
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
  ),
  # Pro: con imágenes — reviews/tips se agregan dinámicamente según el módulo
  # incluido (pro_included_module) y/o add-ons activos (ver feature_flags_for_subscription)
  'menu_qr_pro': (
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
    'menu_item_images',
  ),
  # Premium: todo incluido — imágenes, dominio, reviews, tips, analytics avanzado
  'menu_qr_premium': (
    'menu_builder',
    'menu_branding',
    'public_menu',
    'menu_qr_tools',
    'menu_item_images',
    'menu_custom_domain',
    'menu_qr_reviews',
    'menu_qr_tips',
    'menu_qr_tips_pro',
    'multi_branch',
  ),
}


def feature_flags_for_plan(plan: str) -> Dict[str, bool]:
  # Resolve legacy aliases
  _PLAN_ALIAS = {'start': 'starter', 'plus': 'business'}
  resolved = _PLAN_ALIAS.get(plan, plan) if plan not in PLAN_FEATURES else plan
  normalized_plan = resolved if resolved in PLAN_FEATURES else 'starter'
  flags = {key: False for key in FEATURE_KEYS}
  for key in BASE_ALWAYS_ON:
    flags[key] = True
  for key in PLAN_FEATURES[normalized_plan]:
    flags[key] = True
  return flags


def feature_flags_for_subscription(subscription) -> Dict[str, bool]:
  """
  Calcula feature flags basados en la subscription completa,
  incluyendo addons activos y la elección de módulo pro en Menú QR Pro.
  """
  if subscription is None:
    return feature_flags_for_plan('starter')
  
  plan = subscription.plan
  flags = feature_flags_for_plan(plan)
  
  # Gestión Comercial PRO: habilitar multi_branch si tiene addon de sucursales extras
  if plan == 'pro' and subscription.effective_max_branches > 1:
    flags['multi_branch'] = True

  # Menú QR Pro: reviews y tips se habilitan según módulo incluido + add-ons
  if plan == 'menu_qr_pro':
    pro_module = getattr(subscription, 'pro_included_module', None)
    has_addon_reviews = subscription.has_addon('menu_qr_addon_reviews')
    has_addon_tips = subscription.has_addon('menu_qr_addon_tips')
    flags['menu_qr_reviews'] = (pro_module == 'reviews') or has_addon_reviews
    flags['menu_qr_tips'] = (pro_module == 'tips') or has_addon_tips

  return flags


def feature_flags_for_v2_subscription(sub_v2, business) -> Dict[str, bool]:
  """
  Compute feature flags for a SubscriptionV2, with legacy addon bridge.

  Strategy:
    1. Start from plan-tier base flags (same as feature_flags_for_plan).
    2. Enrich with addon-driven flags from the business's legacy subscription,
       if one exists. This bridges the current gap where SubscriptionV2 has no
       native addon model yet.

  Bridge status — addons with full V2 feature-flag parity:
    - extra_branch          → multi_branch (plan='pro' only, via effective_max_branches)
    - menu_qr_addon_reviews → menu_qr_reviews (plan='menu_qr_pro' only)
    - menu_qr_addon_tips    → menu_qr_tips (plan='menu_qr_pro' only)
    - pro_included_module   → menu_qr_reviews or menu_qr_tips (plan='menu_qr_pro')

  Addons not affecting feature flags (handled at entitlement layer or seat limits):
    - extra_seat      → seat limits only
    - invoices_module → gestion.invoices entitlement (see runtime._get_v2_entitlements)
    - customers_module→ gestion.customers entitlement (see runtime._get_v2_entitlements)

  Gaps still pending after this phase: none.
  Legacy is used only as a bridge, not as a primary source.
  """
  import logging as _logging
  from apps.billing.runtime import _extract_plan_tier

  _logger = _logging.getLogger(__name__)
  plan_tier = _extract_plan_tier(sub_v2.plan_code)
  flags = feature_flags_for_plan(plan_tier)

  # Bridge: enrich from legacy subscription addons when available
  try:
    legacy_sub = getattr(business, 'subscription', None)
    if legacy_sub is not None:
      applied: list = []

      # PRO: enable multi_branch if has extra_branch addon
      if plan_tier == 'pro':
        effective_branches = getattr(legacy_sub, 'effective_max_branches', 1)
        if effective_branches > 1:
          flags['multi_branch'] = True
          applied.append('extra_branch→multi_branch')

      # Menu QR Pro: reviews/tips from pro_included_module OR addons
      if plan_tier == 'menu_qr_pro':
        pro_module = getattr(legacy_sub, 'pro_included_module', None)
        has_reviews = legacy_sub.has_addon('menu_qr_addon_reviews')
        has_tips = legacy_sub.has_addon('menu_qr_addon_tips')
        new_reviews = (pro_module == 'reviews') or has_reviews
        new_tips = (pro_module == 'tips') or has_tips
        if new_reviews and not flags.get('menu_qr_reviews'):
          flags['menu_qr_reviews'] = True
          applied.append('menu_qr_addon_reviews')
        if new_tips and not flags.get('menu_qr_tips'):
          flags['menu_qr_tips'] = True
          applied.append('menu_qr_addon_tips')
        # Also handle the case where flags are already True from plan_tier base
        # but pro_module/addon overrides matter for menu_qr_pro specifically:
        flags['menu_qr_reviews'] = new_reviews
        flags['menu_qr_tips'] = new_tips

      if applied:
        _logger.info(
          "[features] v2_addon_bridge business=%s plan=%s applied=%s",
          business.pk, plan_tier, applied,
        )
    else:
      _logger.debug(
        "[features.feature_flags_for_v2_subscription] no legacy sub for business=%s",
        business.pk,
      )
  except Exception as exc:  # noqa: BLE001
    _logger.debug(
      "[features.feature_flags_for_v2_subscription] addon bridge skipped: %s", exc,
    )

  return flags
