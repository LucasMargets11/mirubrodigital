"""
Service for applying subscription changes to business.Subscription (legacy model).
"""
from typing import Dict, Any
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from apps.business.models import Business, Subscription as BusinessSubscription, SubscriptionAddon
from apps.billing.commercial_plans import get_plan_config


def apply_subscription_change(
    business: Business,
    target_plan_code: str,
    billing_cycle: str,
    config: Dict[str, Any],
) -> BusinessSubscription:
    """
    Apply a subscription change to the legacy business.Subscription model.
    
    Args:
        business: Business instance
        target_plan_code: New plan code
        billing_cycle: 'monthly' or 'yearly'
        config: Configuration dict with:
            - crm: bool
            - invoicing: bool
            - branches_extra_qty: int
            - seats_extra_qty: int
    
    Returns:
        Updated BusinessSubscription instance
    """
    with transaction.atomic():
        # Get or create subscription
        subscription, created = BusinessSubscription.objects.get_or_create(
            business=business,
            defaults={
                'plan': target_plan_code.upper(),
                'service': 'gestion',
                'status': 'active',
                'max_branches': 1,
                'max_seats': 2,
            }
        )
        
        # Update plan
        plan_config = get_plan_config(target_plan_code)
        if not plan_config:
            raise ValueError(f"Invalid plan code: {target_plan_code}")
        
        subscription.plan = target_plan_code.upper()
        subscription.max_branches = plan_config['limits']['branches_included']
        subscription.max_seats = plan_config['limits']['seats_included']
        subscription.status = 'active'
        
        # Calculate next renewal (simple logic for now)
        if billing_cycle == 'monthly':
            from datetime import timedelta
            subscription.renews_at = timezone.now() + timedelta(days=30)
        else:
            from datetime import timedelta
            subscription.renews_at = timezone.now() + timedelta(days=365)
        
        subscription.save()
        
        # Clear existing addons
        SubscriptionAddon.objects.filter(business=business).delete()
        
        # Add branch extras
        branches_extra_qty = config.get('branches_extra_qty', 0)
        if branches_extra_qty > 0:
            SubscriptionAddon.objects.create(
                business=business,
                code='extra_branch',
                quantity=branches_extra_qty,
                price=5000,  # $50 in centavos
                is_active=True,
            )
        
        # Add seat extras
        seats_extra_qty = config.get('seats_extra_qty', 0)
        if seats_extra_qty > 0:
            SubscriptionAddon.objects.create(
                business=business,
                code='extra_seat',
                quantity=seats_extra_qty,
                price=500,  # $5 in centavos
                is_active=True,
            )
        
        # Add CRM addon if requested and not included
        enable_crm = config.get('crm', False)
        crm_included = 'crm' in plan_config.get('included_addons', [])
        if enable_crm and not crm_included:
            SubscriptionAddon.objects.create(
                business=business,
                code='crm',
                quantity=1,
                price=2000,  # $20 in centavos
                is_active=True,
            )
        
        # Add Invoicing addon if requested and not included
        enable_invoicing = config.get('invoicing', False)
        invoicing_included = 'invoicing' in plan_config.get('included_addons', [])
        if enable_invoicing and not invoicing_included:
            SubscriptionAddon.objects.create(
                business=business,
                code='invoicing_module',
                quantity=1,
                price=15000,  # $150 in centavos
                is_active=True,
            )
        
        return subscription


def apply_addon_activation(
    business: Business,
    addon_code: str,
) -> SubscriptionAddon:
    """
    Activate a single addon without affecting the rest of the subscription.
    
    Args:
        business: Business instance
        addon_code: Code of the addon to activate (e.g., 'crm', 'invoicing')
    
    Returns:
        Created or updated SubscriptionAddon instance
    """
    from apps.billing.commercial_plans import get_addon_config
    
    addon_config = get_addon_config(addon_code)
    if not addon_config:
        raise ValueError(f"Invalid addon code: {addon_code}")
    
    with transaction.atomic():
        # Check if addon already exists
        addon, created = SubscriptionAddon.objects.get_or_create(
            business=business,
            code=addon_code,
            defaults={
                'quantity': 1,
                'price': addon_config['pricing']['monthly'],  # Store monthly price
                'is_active': True,
            }
        )
        
        if not created:
            # If it exists but was inactive, reactivate it
            addon.is_active = True
            addon.save()
        
        return addon
