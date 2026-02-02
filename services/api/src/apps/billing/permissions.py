from rest_framework.permissions import BasePermission
from .services import PricingService
from apps.accounts.access import resolve_business_context

class CheckFeatureAccess(BasePermission):
    message = "Esta función no está incluida en su plan actual."

    def has_permission(self, request, view):
        feature = getattr(view, 'required_feature', None)
        if not feature:
            return True
            
        business = resolve_business_context(request)
        if not business:
            return False
            
        return PricingService.tenant_has_feature(business.id, feature)
