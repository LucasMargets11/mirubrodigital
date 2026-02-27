from rest_framework.permissions import BasePermission
from .services import PricingService

class CheckFeatureAccess(BasePermission):
    message = "Esta función no está incluida en su plan actual."

    def has_permission(self, request, view):
        feature = getattr(view, 'required_feature', None)
        if not feature:
            return True

        # request.business is set by HasBusinessMembership, which always runs first
        business = getattr(request, 'business', None)
        if not business:
            return False

        return PricingService.tenant_has_feature(business.id, feature)
