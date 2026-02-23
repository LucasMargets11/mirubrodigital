"""
Preview service for calculating subscription changes.
Handles plan upgrades/downgrades, addon changes, and resource adjustments.
"""
from typing import Optional, TypedDict, List
from decimal import Decimal

from apps.business.models import Business, Subscription as BusinessSubscription, SubscriptionAddon
from apps.billing.commercial_plans import (
    get_plan_config,
    is_addon_available_for_plan,
    BRANCH_EXTRA_PRICING,
    SEAT_EXTRA_PRICING,
    ADDONS,
)
from apps.billing.services.commercial.limits import get_branch_limits, validate_branch_creation


class LineItem(TypedDict):
    """Represents a single line item in the preview."""
    description: str
    quantity: int
    unit_price: int  # in centavos
    total: int       # in centavos
    is_recurring: bool


class ValidationError(TypedDict):
    """Represents a validation error."""
    field: str
    message: str


class PreviewResult(TypedDict):
    """Result of a subscription change preview."""
    line_items: List[LineItem]
    subtotal: int  # in centavos
    total_now: int  # Amount to pay now (upgrades, prorated, etc.)
    total_recurring: int  # Amount for next billing cycle
    requires_checkout: bool
    is_upgrade: bool
    is_downgrade: bool
    validation_errors: List[ValidationError]
    change_summary: str


def _get_plan_level(plan_code: str) -> int:
    """Return numeric level for plan comparison (higher = better)."""
    levels = {'start': 1, 'pro': 2, 'business': 3, 'enterprise': 4}
    return levels.get(plan_code.lower(), 0)


def _validate_plan_change(current_plan: str, new_plan: str) -> Optional[str]:
    """Validate if plan change is allowed. Returns error message if invalid."""
    if current_plan == new_plan:
        return None  # Allowed - might be changing other settings
    
    current_level = _get_plan_level(current_plan)
    new_level = _get_plan_level(new_plan)
    
    # Enterprise can only be coordinated manually
    if new_plan.lower() == 'enterprise':
        return "El cambio a plan Enterprise debe coordinarse con Customer Success"
    
    if current_level == 0 or new_level == 0:
        return "Plan no válido"
    
    return None  # All other changes allowed


def _validate_addon_for_plan(addon_code: str, plan_code: str) -> Optional[str]:
    """Validate if addon can be enabled for the given plan."""
    if not is_addon_available_for_plan(addon_code, plan_code):
        return f"El addon {addon_code} no está disponible para el plan {plan_code}"
    return None


def preview_subscription_change(
    business: Business,
    new_plan_code: str,
    billing_cycle: str,
    enable_crm: bool,
    enable_invoicing: bool,
    branches_extra_qty: int,
    seats_extra_qty: int,
) -> PreviewResult:
    """
    Preview a subscription change before applying it.
    
    Args:
        business: Business instance
        new_plan_code: Target plan code (start, pro, business, enterprise)
        billing_cycle: 'monthly' or 'yearly'
        enable_crm: Whether to enable CRM addon
        enable_invoicing: Whether to enable Invoicing addon
        branches_extra_qty: Number of extra branches to purchase
        seats_extra_qty: Number of extra seats to purchase
    
    Returns:
        PreviewResult with line items, costs, and validation errors
    """
    line_items: List[LineItem] = []
    validation_errors: List[ValidationError] = []
    
    # Get current subscription
    try:
        current_subscription = BusinessSubscription.objects.get(business=business)
        current_plan_code = current_subscription.plan
    except BusinessSubscription.DoesNotExist:
        current_plan_code = 'start'  # Default
    
    # Validate plan change
    plan_error = _validate_plan_change(current_plan_code, new_plan_code)
    if plan_error:
        validation_errors.append({
            'field': 'plan',
            'message': plan_error
        })
    
    # Get new plan config
    new_plan = get_plan_config(new_plan_code)
    if not new_plan:
        validation_errors.append({
            'field': 'plan',
            'message': f"Plan '{new_plan_code}' no encontrado"
        })
        return {
            'line_items': [],
            'subtotal': 0,
            'total_now': 0,
            'total_recurring': 0,
            'requires_checkout': False,
            'is_upgrade': False,
            'is_downgrade': False,
            'validation_errors': validation_errors,
            'change_summary': 'Cambio inválido'
        }
    
    # Get pricing based on billing cycle
    cycle = 'yearly' if billing_cycle == 'yearly' else 'monthly'
    plan_price = new_plan['pricing'][cycle]
    
    # Add plan line item
    line_items.append({
        'description': f"{new_plan['name']} - {cycle == 'monthly' and 'Mensual' or 'Anual'}",
        'quantity': 1,
        'unit_price': plan_price,
        'total': plan_price,
        'is_recurring': True
    })
    
    # Validate and add branch extras
    branch_limits = get_branch_limits(new_plan_code, branches_extra_qty)
    if branches_extra_qty > 0:
        if not branch_limits.extras_allowed:
            validation_errors.append({
                'field': 'branches_extra_qty',
                'message': f"El plan {new_plan['name']} no permite sucursales extras"
            })
        elif branch_limits.max_extras is not None and branches_extra_qty > branch_limits.max_extras:
            validation_errors.append({
                'field': 'branches_extra_qty',
                'message': f"Máximo {branch_limits.max_extras} sucursales extras para este plan"
            })
        else:
            branch_price = BRANCH_EXTRA_PRICING[cycle]
            branch_total = branch_price * branches_extra_qty
            line_items.append({
                'description': f"Sucursales extras ({branches_extra_qty})",
                'quantity': branches_extra_qty,
                'unit_price': branch_price,
                'total': branch_total,
                'is_recurring': True
            })
    
    # Add seat extras
    if seats_extra_qty > 0:
        seat_price = SEAT_EXTRA_PRICING[cycle]
        seat_total = seat_price * seats_extra_qty
        line_items.append({
            'description': f"Usuarios extras ({seats_extra_qty})",
            'quantity': seats_extra_qty,
            'unit_price': seat_price,
            'total': seat_total,
            'is_recurring': True
        })
    
    # Validate and add CRM addon
    if enable_crm:
        addon_error = _validate_addon_for_plan('crm', new_plan_code)
        if addon_error:
            validation_errors.append({
                'field': 'crm',
                'message': addon_error
            })
        else:
            crm_addon = next((a for a in ADDONS if a['code'] == 'crm'), None)
            if crm_addon:
                # Check if included in plan
                is_included = 'crm' in new_plan.get('included_addons', [])
                if not is_included:
                    crm_price = crm_addon['pricing'][cycle]
                    line_items.append({
                        'description': f"{crm_addon['name']} - Add-on",
                        'quantity': 1,
                        'unit_price': crm_price,
                        'total': crm_price,
                        'is_recurring': True
                    })
    
    # Validate and add Invoicing addon
    if enable_invoicing:
        addon_error = _validate_addon_for_plan('invoicing', new_plan_code)
        if addon_error:
            validation_errors.append({
                'field': 'invoicing',
                'message': addon_error
            })
        else:
            invoicing_addon = next((a for a in ADDONS if a['code'] == 'invoicing'), None)
            if invoicing_addon:
                # Check if included in plan
                is_included = 'invoicing' in new_plan.get('included_addons', [])
                if not is_included:
                    invoicing_price = invoicing_addon['pricing'][cycle]
                    line_items.append({
                        'description': f"{invoicing_addon['name']} - Add-on",
                        'quantity': 1,
                        'unit_price': invoicing_price,
                        'total': invoicing_price,
                        'is_recurring': True
                    })
    
    # Calculate totals
    subtotal = sum(item['total'] for item in line_items)
    total_recurring = subtotal
    
    # Determine if upgrade or downgrade
    current_level = _get_plan_level(current_plan_code)
    new_level = _get_plan_level(new_plan_code)
    is_upgrade = new_level > current_level
    is_downgrade = new_level < current_level
    
    # For upgrades, charge immediately (simplified - no prorating yet)
    # For downgrades, schedule for next billing cycle
    if is_upgrade:
        total_now = total_recurring
        requires_checkout = True
        change_summary = f"Actualización a {new_plan['name']}"
    elif is_downgrade:
        total_now = 0
        requires_checkout = False
        change_summary = f"Cambio a {new_plan['name']} programado para próximo ciclo"
    else:
        # Same plan level, just addon/resource changes
        total_now = total_recurring
        requires_checkout = total_now > 0
        change_summary = f"Modificación de {new_plan['name']}"
    
    return {
        'line_items': line_items,
        'subtotal': subtotal,
        'total_now': total_now,
        'total_recurring': total_recurring,
        'requires_checkout': requires_checkout,
        'is_upgrade': is_upgrade,
        'is_downgrade': is_downgrade,
        'validation_errors': validation_errors,
        'change_summary': change_summary
    }
