"""
Configuración centralizada de planes de Gestión Comercial.
Única fuente de verdad para precios, límites y características.
"""
from typing import TypedDict, List, Optional


class PlanPricing(TypedDict):
    monthly: int  # En centavos
    yearly: int


class AddonConfig(TypedDict):
    code: str
    name: str
    description: str
    pricing: PlanPricing
    availability: List[str]  # Planes donde está disponible
    included_in: List[str]  # Planes donde está incluido


class PlanLimits(TypedDict):
    branches_included: int
    branches_max_total: Optional[int]  # None = ilimitado
    branches_extra_allowed: bool
    max_branches_extra: Optional[int]  # None = ilimitado
    seats_included: int


class PlanConfig(TypedDict):
    code: str
    name: str
    description: str
    pricing: PlanPricing
    limits: PlanLimits
    features: List[str]  # Lista de features incluidas
    is_custom: bool  # True para ENTERPRISE


# Precios de recursos extras
BRANCH_EXTRA_PRICING: PlanPricing = {
    'monthly': 5000,  # $50/mes por sucursal extra (en centavos)
    'yearly': 48000,  # $480/año (descuento 20%)
}

SEAT_EXTRA_PRICING: PlanPricing = {
    'monthly': 500,  # $5/mes por usuario extra
    'yearly': 4800,  # $48/año (descuento 20%)
}

# Configuración de Add-ons
ADDONS: List[AddonConfig] = [
    {
        'code': 'crm',
        'name': 'Gestión de Clientes (CRM)',
        'description': 'CRM básico con historial de compras y segmentación',
        'pricing': {
            'monthly': 2000,  # $20/mes
            'yearly': 19200,  # $192/año (descuento 20%)
        },
        'availability': ['start'],  # Solo START puede comprarlo
        'included_in': ['pro', 'business', 'enterprise'],
    },
    {
        'code': 'invoicing',
        'name': 'Facturación Electrónica',
        'description': 'Emisión de facturas válidas (AFIP, SAT, etc.)',
        'pricing': {
            'monthly': 15000,  # $150/mes
            'yearly': 144000,  # $1440/año (descuento 20%)
        },
        'availability': ['start'],  # Solo START puede comprarlo
        'included_in': ['pro', 'business', 'enterprise'],  # Incluido en PRO+
    },
]

# Configuración de Planes
PLANS: List[PlanConfig] = [
    {
        'code': 'start',
        'name': 'START',
        'description': 'Para emprendedores y pequeños negocios',
        'pricing': {
            'monthly': 9900,  # $99/mes
            'yearly': 95000,  # $950/año (~20% descuento)
        },
        'limits': {
            'branches_included': 1,
            'branches_max_total': 1,
            'branches_extra_allowed': False,
            'max_branches_extra': 0,
            'seats_included': 2,
        },
        'features': [
            'Gestión de productos',
            'Inventario básico',
            'Ventas básicas',
            'Dashboard básico',
            'Configuración comercial básica',
        ],
        'is_custom': False,
    },
    {
        'code': 'pro',
        'name': 'PRO',
        'description': 'Para negocios establecidos con operación completa',
        'pricing': {
            'monthly': 29900,  # $299/mes
            'yearly': 287000,  # $2870/año (~20% descuento)
        },
        'limits': {
            'branches_included': 1,
            'branches_max_total': 3,
            'branches_extra_allowed': True,
            'max_branches_extra': 2,
            'seats_included': 10,
        },
        'features': [
            'Todo START +',
            'CRM / Gestión de clientes',
            'Facturación electrónica',
            'Caja / Sesiones de caja',
            'Cotizaciones con PDF',
            'Reportes avanzados + Exportación',
            'Tesorería / Finanzas',
            'Inventario avanzado',
            'RBAC completo + Auditoría',
        ],
        'is_custom': False,
    },
    {
        'code': 'business',
        'name': 'BUSINESS',
        'description': 'Para empresas multi-sucursal',
        'pricing': {
            'monthly': 49900,  # $499/mes
            'yearly': 479000,  # $4790/año (~20% descuento)
        },
        'limits': {
            'branches_included': 5,
            'branches_max_total': None,  # Ilimitado
            'branches_extra_allowed': True,
            'max_branches_extra': None,  # Ilimitado
            'seats_included': 20,
        },
        'features': [
            'Todo PRO +',
            'Facturación electrónica incluida',
            'Multi-sucursal consolidado',
            'Transferencias entre sucursales',
            'Reportes consolidados',
            'Soporte prioritario',
        ],
        'is_custom': False,
    },
    {
        'code': 'enterprise',
        'name': 'ENTERPRISE',
        'description': 'Solución personalizada para grandes empresas',
        'pricing': {
            'monthly': 0,  # Custom pricing
            'yearly': 0,
        },
        'limits': {
            'branches_included': 999,  # Prácticamente ilimitado
            'branches_max_total': None,
            'branches_extra_allowed': False,  # No usa sistema de extras
            'max_branches_extra': None,
            'seats_included': 999,
        },
        'features': [
            'Todo BUSINESS +',
            'Límites personalizados',
            'Integraciones custom',
            'Soporte dedicado',
            'SLA garantizado',
        ],
        'is_custom': True,
    },
]


def get_plan_config(plan_code: str) -> Optional[PlanConfig]:
    """Obtiene la configuración de un plan por código."""
    for plan in PLANS:
        if plan['code'] == plan_code:
            return plan
    return None


def get_addon_config(addon_code: str) -> Optional[AddonConfig]:
    """Obtiene la configuración de un addon por código."""
    for addon in ADDONS:
        if addon['code'] == addon_code:
            return addon
    return None


def is_addon_available_for_plan(addon_code: str, plan_code: str) -> bool:
    """Verifica si un addon está disponible para comprar en un plan."""
    addon = get_addon_config(addon_code)
    if not addon:
        return False
    return plan_code in addon['availability']


def is_addon_included_in_plan(addon_code: str, plan_code: str) -> bool:
    """Verifica si un addon ya está incluido en un plan."""
    addon = get_addon_config(addon_code)
    if not addon:
        return False
    return plan_code in addon['included_in']


def get_available_addons_for_plan(plan_code: str) -> List[AddonConfig]:
    """Obtiene todos los addons disponibles para un plan (excluye incluidos)."""
    available = []
    for addon in ADDONS:
        if is_addon_available_for_plan(addon['code'], plan_code):
            available.append(addon)
    return available


def get_included_addons_for_plan(plan_code: str) -> List[AddonConfig]:
    """Obtiene todos los addons incluidos en un plan."""
    included = []
    for addon in ADDONS:
        if is_addon_included_in_plan(addon['code'], plan_code):
            included.append(addon)
    return included
