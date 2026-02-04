from __future__ import annotations

from typing import Type

from rest_framework.permissions import BasePermission

from apps.accounts.access import resolve_request_membership


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
    if business is None or not service_slug:
        return False
    subscription = getattr(business, 'subscription', None)
    subscription_service = getattr(subscription, 'service', None)
    if subscription_service:
        return subscription_service == service_slug
    default_service = getattr(business, 'default_service', None) or 'gestion'
    return default_service == service_slug


def require_service(service_slug: str) -> Type[BasePermission]:
    class RequireBusinessService(BasePermission):
        message = 'Este recurso no está disponible para tu servicio actual.'

        def has_permission(self, request, view) -> bool:
            business = _resolve_business(request)
            if business is None:
                return False
            return business_has_service(business, service_slug)

    RequireBusinessService.__name__ = f"Require{service_slug.title().replace('_', '')}Service"
    return RequireBusinessService
