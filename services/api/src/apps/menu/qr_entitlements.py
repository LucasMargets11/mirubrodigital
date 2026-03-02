"""
Menú QR Online — feature entitlements resolver.

Single source of truth para determinar qué funcionalidades de engagement
(Reseñas, Propinas, Analytics, Imágenes, Dominio) tiene habilitadas un
negocio según su plan y add-ons activos.

Inputs:
  subscription → business.Subscription (puede ser None)

Outputs (dict):
  reviews_allowed      → bool  — Puede activar Reseñas de Google
  tips_allowed         → bool  — Puede activar Propinas (MP)
  analytics_advanced   → bool  — Acceso a analíticas avanzadas
  images_allowed       → bool  — Puede subir imágenes por producto
  custom_domain_allowed → bool — Puede usar dominio personalizado
  multi_branch_allowed → bool  — Puede operar con múltiples sucursales
  pro_included_module  → str|None — Módulo incluido en el plan PRO ('reviews'|'tips'|None)
  plan                 → str   — Código del plan activo

Compatibilidad con planes legacy:
  menu_qr, menu_qr_visual, menu_qr_marca → comportamiento original (sin restricciones engagement)
"""

from __future__ import annotations

from typing import TypedDict


# Plans que usan el nuevo gating de modules
NEW_MENU_QR_PLANS = frozenset({'menu_qr_lite', 'menu_qr_pro', 'menu_qr_premium'})
# Plans legacy — mantienen comportamiento original (reviews/tips siempre habilitados)
LEGACY_MENU_QR_PLANS = frozenset({'menu_qr', 'menu_qr_visual', 'menu_qr_marca'})


class MenuQRFlags(TypedDict):
    reviews_allowed: bool
    tips_allowed: bool
    analytics_advanced: bool
    images_allowed: bool
    custom_domain_allowed: bool
    multi_branch_allowed: bool
    pro_included_module: str | None
    plan: str


def resolve_menu_qr_flags(subscription) -> MenuQRFlags:
    """
    Calcula los feature entitlements de Menú QR para una suscripción.

    Reglas:
      Lite:    reviews=N  tips=N  images=N  analytics=N  domain=N  branches=N
      Pro:     reviews=? (según pro_included_module + addon)
               tips=?    images=Y  analytics=Y  domain=N  branches=N
      Premium: reviews=Y  tips=Y  images=Y  analytics=Y  domain=Y  branches=Y
      Legacy (menu_qr/visual/marca): mismo comportamiento de siempre

    Returns MenuQRFlags dict.
    """
    if subscription is None:
        return _empty_flags('menu_qr_lite')

    plan: str = getattr(subscription, 'plan', 'menu_qr_lite') or 'menu_qr_lite'

    # ── Plan LITE ─────────────────────────────────────────────────────────
    if plan == 'menu_qr_lite':
        return MenuQRFlags(
            reviews_allowed=False,
            tips_allowed=False,
            analytics_advanced=False,
            images_allowed=False,
            custom_domain_allowed=False,
            multi_branch_allowed=False,
            pro_included_module=None,
            plan=plan,
        )

    # ── Plan PRO ──────────────────────────────────────────────────────────
    if plan == 'menu_qr_pro':
        pro_module: str | None = getattr(subscription, 'pro_included_module', None)
        has_addon_reviews: bool = subscription.has_addon('menu_qr_addon_reviews')
        has_addon_tips: bool = subscription.has_addon('menu_qr_addon_tips')

        # No duplicar: si el módulo ya está incluido, el add-on es redundante
        # pero no está prohibido (simplemente no cambia nada)
        reviews_allowed = (pro_module == 'reviews') or has_addon_reviews
        tips_allowed = (pro_module == 'tips') or has_addon_tips

        return MenuQRFlags(
            reviews_allowed=reviews_allowed,
            tips_allowed=tips_allowed,
            analytics_advanced=True,
            images_allowed=True,
            custom_domain_allowed=False,
            multi_branch_allowed=False,
            pro_included_module=pro_module,
            plan=plan,
        )

    # ── Plan PREMIUM ──────────────────────────────────────────────────────
    if plan == 'menu_qr_premium':
        return MenuQRFlags(
            reviews_allowed=True,
            tips_allowed=True,
            analytics_advanced=True,
            images_allowed=True,
            custom_domain_allowed=True,
            multi_branch_allowed=True,
            pro_included_module=None,
            plan=plan,
        )

    # ── Planes LEGACY (menu_qr, menu_qr_visual, menu_qr_marca) ───────────
    if plan in LEGACY_MENU_QR_PLANS:
        images = plan in ('menu_qr_visual', 'menu_qr_marca')
        domain = plan == 'menu_qr_marca'
        return MenuQRFlags(
            reviews_allowed=True,
            tips_allowed=True,
            analytics_advanced=False,
            images_allowed=images,
            custom_domain_allowed=domain,
            multi_branch_allowed=False,
            pro_included_module=None,
            plan=plan,
        )

    # ── Planes NO-QR (Restaurante tiene acceso al menú) ──────────────────
    if plan in ('restaurante', 'plus'):
        return MenuQRFlags(
            reviews_allowed=True,
            tips_allowed=True,
            analytics_advanced=False,
            images_allowed=True,
            custom_domain_allowed=False,
            multi_branch_allowed=True,
            pro_included_module=None,
            plan=plan,
        )

    # Fallback — sin acceso
    return _empty_flags(plan)


def _empty_flags(plan: str) -> MenuQRFlags:
    return MenuQRFlags(
        reviews_allowed=False,
        tips_allowed=False,
        analytics_advanced=False,
        images_allowed=False,
        custom_domain_allowed=False,
        multi_branch_allowed=False,
        pro_included_module=None,
        plan=plan,
    )


def get_subscription_for_business(business) -> object | None:
    """
    Helper para obtener la suscripción activa de un negocio,
    con fallback graceful si no tiene suscripción.
    """
    try:
        sub = business.subscription
        return sub if sub.status == 'active' else None
    except Exception:
        return None
