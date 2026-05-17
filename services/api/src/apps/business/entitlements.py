"""
Sistema de entitlements para feature gating del servicio Gestión Comercial.

Los entitlements definen qué features/módulos están habilitados para cada plan.
Trabajan en conjunto con RBAC: el business necesita el entitlement Y el usuario
necesita el permiso correspondiente.
"""

import logging
from typing import Set

logger = logging.getLogger(__name__)


# Entitlements por plan — 4 planes oficiales + aliases legacy
PLAN_ENTITLEMENTS = {
    'starter': {
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.orders',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
    },
    'pro': {
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.orders',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.dashboard_finance',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.print_signage',
    },
    'business': {
        # Todos los de PRO +
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.orders',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.dashboard_finance',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.multi_branch',
        'gestion.transfers',
        'gestion.consolidated_reports',
        'gestion.tax_backup',
    },
    'enterprise': {
        # Todos los de BUSINESS
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.orders',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.dashboard_finance',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.multi_branch',
        'gestion.transfers',
        'gestion.consolidated_reports',
        'gestion.tax_backup',
    },
    
    # Legacy aliases — mapean a los planes canónicos
    'start': None,   # resolved dynamically below
    'plus': None,     # resolved dynamically below
}

# Legacy slug → canonical slug
_PLAN_ALIAS = {
    'start': 'starter',
    'plus': 'business',
}

# Wire aliases to their canonical entitlement sets
PLAN_ENTITLEMENTS['start'] = PLAN_ENTITLEMENTS['starter']
PLAN_ENTITLEMENTS['plus'] = PLAN_ENTITLEMENTS['business']

# QR de Reseñas — plan base
PLAN_ENTITLEMENTS['qr_reviews'] = {
    'qr_reviews.config',
    'qr_reviews.qr',
    'qr_reviews.dashboard',
}

# QR de Reseñas — plan base explícito (alias)
PLAN_ENTITLEMENTS['qr_reviews_base'] = PLAN_ENTITLEMENTS['qr_reviews']

# QR de Reseñas — plan PRO (superset del base + cartelería)
PLAN_ENTITLEMENTS['qr_reviews_pro'] = {
    'qr_reviews.config',
    'qr_reviews.qr',
    'qr_reviews.dashboard',
    'qr_reviews.print_posters',   # solo PRO
}


# Entitlements agregados por add-ons
ADDON_ENTITLEMENTS = {
    'invoices_module': {'gestion.invoices'},
    'customers_module': {'gestion.customers'},
}


# Mapeo de entitlements a upgrade hint
ENTITLEMENT_UPGRADE_HINTS = {
    'gestion.customers': 'Disponible en PRO o como add-on para Starter.',
    'gestion.cash': 'PRO',
    'gestion.quotes': 'PRO',
    'gestion.reports': 'PRO',
    'gestion.export': 'PRO',
    'gestion.treasury': 'PRO',
    'gestion.dashboard_finance': 'PRO',
    'gestion.inventory_advanced': 'PRO',
    'gestion.sales_advanced': 'PRO',
    'gestion.rbac_full': 'PRO',
    'gestion.audit': 'PRO',
    'gestion.invoices': 'Disponible en PRO o como add-on para Starter.',
    'gestion.multi_branch': 'BUSINESS',
    'gestion.transfers': 'BUSINESS',
    'gestion.consolidated_reports': 'BUSINESS',
    'gestion.tax_backup': 'BUSINESS',
    'gestion.print_signage': 'PRO',
    'qr_reviews.print_posters': 'Reseñas PRO',
}


def get_plan_entitlements(plan: str) -> Set[str]:
    """
    Retorna los entitlements base del plan.
    Resuelve aliases legacy (start→starter, plus→business).
    """
    key = _PLAN_ALIAS.get(plan.lower(), plan.lower())
    return PLAN_ENTITLEMENTS.get(key, set()).copy()


def get_effective_entitlements(subscription) -> Set[str]:
    """
    Calcula los entitlements efectivos de una subscription,
    incluyendo los del plan base + add-ons activos.
    
    Args:
        subscription: Instancia de Subscription
    
    Returns:
        Set de códigos de entitlements efectivos
    """
    entitlements = get_plan_entitlements(subscription.plan)
    
    # Agregar entitlements de add-ons activos
    try:
        for addon in subscription.addons.filter(is_active=True):
            addon_entitlements = ADDON_ENTITLEMENTS.get(addon.code, set())
            entitlements |= addon_entitlements
    except Exception:
        # Si no hay relación addons o error, continuar solo con plan base
        pass
    
    return entitlements


def has_entitlement(business, entitlement_code: str) -> bool:
    """
    Verifica si un business tiene un entitlement específico.

    V2-first: consulta primero SubscriptionV2 a través de la capa de resolución
    runtime (billing.runtime.resolve_subscription). Cae a legacy solo si no
    existe V2 usable. No otorga acceso si no hay suscripción válida.

    El acceso es validado primero por la capa de enforcement global
    (billing.enforcement.get_enforcement_decision) antes de verificar
    pertenencia al plan.

    Args:
        business: Instancia de Business
        entitlement_code: Código del entitlement (ej: 'gestion.customers')

    Returns:
        True si el business tiene el entitlement activo, False en caso contrario
    """
    try:
        from apps.billing.runtime import resolve_subscription
        from apps.billing.enforcement import get_enforcement_decision

        resolved = resolve_subscription(business)
        decision = get_enforcement_decision(resolved)

        if not decision.access_allowed:
            logger.info(
                "[has_entitlement] denied — enforcement: business=%s "
                "entitlement=%s reason=%s source=%s status=%s",
                business.pk, entitlement_code,
                decision.reason_code, resolved.source, resolved.status,
            )
            return False

        result = entitlement_code in resolved.entitlements
        if not result:
            logger.debug(
                "[has_entitlement] denied — not in entitlements: business=%s "
                "entitlement=%s source=%s plan=%s",
                business.pk, entitlement_code, resolved.source, resolved.plan,
            )
        return result
    except Exception:
        logger.exception(
            "[has_entitlement] unexpected error for business=%s entitlement=%s",
            business.pk, entitlement_code,
        )
        return False


def get_upgrade_hint(entitlement_code: str) -> str:
    """
    Retorna la sugerencia de upgrade para un entitlement específico.
    
    Args:
        entitlement_code: Código del entitlement
    
    Returns:
        Hint de upgrade (ej: 'PRO', 'BUSINESS', 'ADD-ON')
    """
    return ENTITLEMENT_UPGRADE_HINTS.get(entitlement_code, 'PRO')


def get_all_entitlements_for_service(service: str = 'gestion') -> Set[str]:
    """
    Retorna todos los entitlements posibles para un servicio.
    
    Args:
        service: Código del servicio (default: 'gestion')
    
    Returns:
        Set con todos los entitlements del servicio
    """
    all_entitlements = set()
    for plan_entitlements in PLAN_ENTITLEMENTS.values():
        all_entitlements |= plan_entitlements
    
    for addon_entitlements in ADDON_ENTITLEMENTS.values():
        all_entitlements |= addon_entitlements
    
    # Filtrar por servicio
    return {e for e in all_entitlements if e.startswith(f'{service}.')}
