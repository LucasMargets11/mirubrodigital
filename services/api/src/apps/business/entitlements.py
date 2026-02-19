"""
Sistema de entitlements para feature gating del servicio Gestión Comercial.

Los entitlements definen qué features/módulos están habilitados para cada plan.
Trabajan en conjunto con RBAC: el business necesita el entitlement Y el usuario
necesita el permiso correspondiente.
"""

from typing import Set


# Entitlements por plan
PLAN_ENTITLEMENTS = {
    'start': {
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
    },
    'pro': {
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
    },
    'business': {
        # Todos los de PRO +
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.multi_branch',
        'gestion.transfers',
        'gestion.consolidated_reports',
    },
    'enterprise': {
        # Todos los de BUSINESS
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.multi_branch',
        'gestion.transfers',
        'gestion.consolidated_reports',
    },
    
    # Legacy plans (compatibilidad)
    'starter': {
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
    },
    'plus': {
        # Plus era el plan anterior más alto, mapearlo a BUSINESS
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.multi_branch',
        'gestion.transfers',
        'gestion.consolidated_reports',
    },
}


# Entitlements agregados por add-ons
ADDON_ENTITLEMENTS = {
    'invoices_module': {'gestion.invoices'},
}


# Mapeo de entitlements a upgrade hint
ENTITLEMENT_UPGRADE_HINTS = {
    'gestion.customers': 'PRO',
    'gestion.cash': 'PRO',
    'gestion.quotes': 'PRO',
    'gestion.reports': 'PRO',
    'gestion.export': 'PRO',
    'gestion.treasury': 'PRO',
    'gestion.inventory_advanced': 'PRO',
    'gestion.sales_advanced': 'PRO',
    'gestion.rbac_full': 'PRO',
    'gestion.audit': 'PRO',
    'gestion.invoices': 'BUSINESS o ADD-ON',
    'gestion.multi_branch': 'BUSINESS',
    'gestion.transfers': 'BUSINESS',
    'gestion.consolidated_reports': 'BUSINESS',
}


def get_plan_entitlements(plan: str) -> Set[str]:
    """
    Retorna los entitlements base del plan.
    
    Args:
        plan: Código del plan (start, pro, business, enterprise)
    
    Returns:
        Set de códigos de entitlements
    """
    return PLAN_ENTITLEMENTS.get(plan.lower(), set()).copy()


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
    
    Args:
        business: Instancia de Business
        entitlement_code: Código del entitlement (ej: 'gestion.customers')
    
    Returns:
        True si el business tiene el entitlement, False en caso contrario
    """
    try:
        subscription = business.subscription
        if not subscription or subscription.status != 'active':
            return False
        
        entitlements = get_effective_entitlements(subscription)
        return entitlement_code in entitlements
    except Exception:
        # Si no hay subscription, no tiene entitlements
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
