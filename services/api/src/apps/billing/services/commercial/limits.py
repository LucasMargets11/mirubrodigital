"""
Servicio para calcular límites de sucursales para Gestión Comercial.
"""
from typing import NamedTuple, Optional
from apps.billing.commercial_plans import get_plan_config


class BranchLimits(NamedTuple):
    """Límites de sucursales para un plan."""
    included: int  # Sucursales incluidas en el plan base
    max_total: Optional[int]  # Máximo total permitido (None = ilimitado)
    extras_allowed: bool  # Si permite comprar sucursales extra
    max_extras: Optional[int]  # Máximo de extras permitidas (None = ilimitado)
    current_extras: int  # Extras actualmente contratadas
    current_total: int  # Total actual (included + current_extras)
    can_add_more: bool  # Si puede agregar más
    remaining: Optional[int]  # Cuántas más puede agregar (None = ilimitado)


def get_branch_limits(
    plan_code: str,
    current_branches_extra: int = 0,
) -> BranchLimits:
    """
    Calcula los límites de sucursales para un plan y cantidad de extras actual.
    
    Args:
        plan_code: Código del plan (start, pro, business, enterprise)
        current_branches_extra: Cantidad de sucursales extra contratadas
        
    Returns:
        BranchLimits con toda la información de límites
        
    Raises:
        ValueError: Si el plan no existe
    """
    plan_config = get_plan_config(plan_code)
    if not plan_config:
        raise ValueError(f"Plan '{plan_code}' no encontrado")
    
    limits = plan_config['limits']
    included = limits['branches_included']
    max_total = limits['branches_max_total']
    extras_allowed = limits['branches_extra_allowed']
    max_extras = limits['max_branches_extra']
    
    current_total = included + current_branches_extra
    
    # Calcular si puede agregar más
    can_add_more = False
    remaining: Optional[int] = None
    
    if extras_allowed:
        if max_total is None:
            # Ilimitado
            can_add_more = True
            remaining = None
        else:
            # Tiene límite
            can_add_more = current_total < max_total
            remaining = max(0, max_total - current_total)
    
    return BranchLimits(
        included=included,
        max_total=max_total,
        extras_allowed=extras_allowed,
        max_extras=max_extras,
        current_extras=current_branches_extra,
        current_total=current_total,
        can_add_more=can_add_more,
        remaining=remaining,
    )


def validate_branch_creation(
    plan_code: str,
    current_branches_count: int,
    current_branches_extra: int,
) -> tuple[bool, Optional[str]]:
    """
    Valida si se puede crear una nueva sucursal.
    
    Args:
        plan_code: Código del plan
        current_branches_count: Cantidad actual de sucursales (HQ + branches)
        current_branches_extra: Cantidad de extras contratadas
        
    Returns:
        (is_valid, error_message)
        - is_valid: True si puede crear, False si no
        - error_message: Mensaje de error si is_valid=False, None si is_valid=True
    """
    try:
        limits = get_branch_limits(plan_code, current_branches_extra)
    except ValueError as e:
        return False, str(e)
    
    # El límite efectivo es included + current_extras
    effective_limit = limits.included + limits.current_extras
    
    if current_branches_count >= effective_limit:
        if limits.can_add_more:
            return False, (
                f"Has alcanzado el límite de sucursales ({effective_limit}). "
                f"Puedes contratar hasta {limits.remaining} sucursales extra más."
            )
        else:
            return False, (
                f"Has alcanzado el límite máximo de {effective_limit} sucursales de tu plan. "
                f"Actualiza tu plan para obtener más sucursales."
            )
    
    return True, None


def calculate_branches_cost(
    plan_code: str,
    branches_extra_qty: int,
    billing_cycle: str = 'monthly',
) -> int:
    """
    Calcula el costo de sucursales extra.
    
    Args:
        plan_code: Código del plan
        branches_extra_qty: Cantidad de sucursales extra
        billing_cycle: 'monthly' o 'yearly'
        
    Returns:
        Costo en centavos
        
    Raises:
        ValueError: Si el plan no permite extras o la cantidad excede el límite
    """
    from apps.billing.commercial_plans import BRANCH_EXTRA_PRICING
    
    if branches_extra_qty <= 0:
        return 0
    
    limits = get_branch_limits(plan_code, 0)
    
    if not limits.extras_allowed:
        raise ValueError(f"El plan {plan_code} no permite sucursales extra")
    
    if limits.max_extras is not None and branches_extra_qty > limits.max_extras:
        raise ValueError(
            f"El plan {plan_code} permite máximo {limits.max_extras} sucursales extra, "
            f"solicitaste {branches_extra_qty}"
        )
    
    unit_price = BRANCH_EXTRA_PRICING[billing_cycle]
    return unit_price * branches_extra_qty
