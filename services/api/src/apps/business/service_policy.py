from __future__ import annotations

from typing import Dict, FrozenSet, Type

from rest_framework.permissions import BasePermission

from apps.accounts.access import resolve_request_membership

# Service hierarchy: a business with service X implicitly has access to all
# service endpoints listed in its implied set.
# Rationale: 'restaurante' bundles the full Menú QR feature set.
# 'menu_qr_visual' and 'menu_qr_marca' are supersets of 'menu_qr', so they
# also satisfy require_service('menu_qr').
SERVICE_IMPLIES: Dict[str, FrozenSet[str]] = {
    'restaurante': frozenset({'restaurante', 'menu_qr'}),
    'menu_qr_visual': frozenset({'menu_qr', 'menu_qr_visual'}),
    'menu_qr_marca': frozenset({'menu_qr', 'menu_qr_visual', 'menu_qr_marca'}),
    # qr_reviews intentionally NOT implied by menu_qr — separate products
}



def _resolve_business(request):
    business = getattr(request, 'business', None)
    if business is not None:
        return business
    membership = resolve_request_membership(request)
    if membership is not None:
        request.business = membership.business
        return membership.business
    return None


def business_has_service(business, service_slug: str) -> bool:
    """
    Return True if the business has access to *service_slug*.

    A business's actual service is resolved from its subscription (preferred)
    or its ``default_service`` field.  The actual service is then expanded
    through SERVICE_IMPLIES so that, e.g., a ``restaurante`` subscription
    also satisfies ``require_service('menu_qr')``.
    """
    if business is None or not service_slug:
        return False

    from apps.billing.runtime import resolve_subscription

    if service_slug == 'appointments':
        resolved = resolve_subscription(business, service_type='appointments')
        if resolved.source != 'none':
            from apps.billing.runtime import is_appointments_plan_code

            return (
                resolved.access_granted
                and resolved.service_type == 'appointments'
                and is_appointments_plan_code(resolved.plan or '')
            )

        # Preserve the old service-field fallback only when no subscription
        # record exists; another product's subscription cannot enable Turnos.
        if business.subscriptions_v2.exists() or hasattr(business, 'subscription'):
            return False
        return (
            getattr(business, 'service_type', None) == 'appointments'
            or getattr(business, 'default_service', None) == 'appointments'
        )

    # A Turnos subscription is not a fallback for another product. If Turnos
    # exists, require a separately resolved subscription for the requested
    # service instead of trusting the business's default-service hint.
    appointments = resolve_subscription(business, service_type='appointments')
    if appointments.source != 'none':
        requested = resolve_subscription(business, service_type=service_slug)
        if requested.source == 'none':
            return False

    subscription = getattr(business, 'subscription', None)
    subscription_service = getattr(subscription, 'service', None)
    actual_service = subscription_service or getattr(business, 'default_service', None) or 'gestion'
    implied: FrozenSet[str] = SERVICE_IMPLIES.get(actual_service, frozenset({actual_service}))
    return service_slug in implied


def require_service(service_slug: str) -> Type[BasePermission]:
    """DRF permission class factory: gates a view behind a service check.

    Usage::

        permission_classes = [IsAuthenticated, HasBusinessMembership, require_service('menu_qr')]
    """
    class RequireBusinessService(BasePermission):
        message = 'Este recurso no está disponible para tu servicio actual.'

        def has_permission(self, request, view) -> bool:
            business = _resolve_business(request)
            if business is None:
                return False
            return business_has_service(business, service_slug)

    RequireBusinessService.__name__ = f"Require{service_slug.title().replace('_', '')}Service"
    return RequireBusinessService
