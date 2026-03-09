"""
Service for applying subscription changes to business.Subscription (legacy model).
"""
import logging
from datetime import timedelta
from typing import Dict, Any

from django.utils import timezone
from django.db import transaction

from apps.business.models import Business, Subscription as BusinessSubscription, SubscriptionAddon
from apps.billing.commercial_plans import get_plan_config, get_addon_config

logger = logging.getLogger(__name__)


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
                'plan': target_plan_code,  # lowercase — matches BusinessPlan choices
                'service': 'gestion',
                'status': 'active',
                'max_branches': 1,
                'max_seats': 2,
            }
        )

        plan_config = get_plan_config(target_plan_code)
        if not plan_config:
            raise ValueError(f"Invalid plan code: {target_plan_code}")

        # Store plan code as-is (lowercase), matching BusinessPlan choices
        subscription.plan = target_plan_code
        subscription.max_branches = plan_config['limits']['branches_included']
        subscription.max_seats = plan_config['limits']['seats_included']
        subscription.status = 'active'

        if billing_cycle == 'monthly':
            subscription.renews_at = timezone.now() + timedelta(days=30)
        else:
            subscription.renews_at = timezone.now() + timedelta(days=365)

        subscription.save()

        # Clear existing addons via the correct reverse relation
        subscription.addons.all().delete()

        branches_extra_qty = config.get('branches_extra_qty', 0)
        if branches_extra_qty > 0:
            SubscriptionAddon.objects.create(
                subscription=subscription,
                code='extra_branch',
                quantity=branches_extra_qty,
                is_active=True,
            )

        seats_extra_qty = config.get('seats_extra_qty', 0)
        if seats_extra_qty > 0:
            SubscriptionAddon.objects.create(
                subscription=subscription,
                code='extra_seat',
                quantity=seats_extra_qty,
                is_active=True,
            )

        enable_crm = config.get('crm', False)
        crm_included = 'crm' in plan_config.get('included_addons', [])
        if enable_crm and not crm_included:
            SubscriptionAddon.objects.create(
                subscription=subscription,
                code='crm',
                quantity=1,
                is_active=True,
            )

        enable_invoicing = config.get('invoicing', False)
        invoicing_included = 'invoicing' in plan_config.get('included_addons', [])
        if enable_invoicing and not invoicing_included:
            SubscriptionAddon.objects.create(
                subscription=subscription,
                code='invoicing_module',
                quantity=1,
                is_active=True,
            )

    # ── Phase 2B: create or sync SubscriptionV2 (birth path + bridge) ──────────
    try:
        import uuid as _uuid
        from apps.billing.models import SubscriptionV2

        service_type = business.default_service
        v2 = (
            SubscriptionV2.objects
            .filter(business=business, service_type=service_type)
            .exclude(status=SubscriptionV2.Status.CANCELED)
            .first()
        )
        if v2:
            v2.plan_code = target_plan_code
            v2.status = SubscriptionV2.Status.ACTIVE
            v2.save(update_fields=['plan_code', 'status', 'updated_at'])
            logger.info(
                "[apply_subscription_change] Synced SubscriptionV2 %s → plan=%s status=active",
                v2.pk, target_plan_code,
            )
        else:
            # No V2 exists yet (e.g. business created before birth-path was added).
            # Create it now so the canonical record exists after this change.
            v2 = SubscriptionV2.objects.create(
                business=business,
                service_type=service_type,
                plan_code=target_plan_code,
                provider=SubscriptionV2.Provider.MERCADOPAGO,
                external_reference=f"SUB-{_uuid.uuid4()}",
                status=SubscriptionV2.Status.ACTIVE,
            )
            logger.info(
                "[apply_subscription_change] Created SubscriptionV2 %s for business=%s plan=%s",
                v2.pk, business.pk, target_plan_code,
            )
    except Exception as exc:
        logger.warning(
            "[apply_subscription_change] SubscriptionV2 create/sync failed (non-fatal): %s", exc,
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
    addon_config = get_addon_config(addon_code)
    if not addon_config:
        raise ValueError(f"Invalid addon code: {addon_code}")

    with transaction.atomic():
        try:
            subscription = BusinessSubscription.objects.get(business=business)
        except BusinessSubscription.DoesNotExist:
            raise ValueError(f"No subscription found for business {business.pk}")

        addon, created = SubscriptionAddon.objects.get_or_create(
            subscription=subscription,
            code=addon_code,
            defaults={
                'quantity': 1,
                'is_active': True,
            }
        )

        if not created and not addon.is_active:
            addon.is_active = True
            addon.save(update_fields=['is_active', 'updated_at'])

        return addon
