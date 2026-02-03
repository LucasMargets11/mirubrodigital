from typing import List, Optional, Union
from django.db.models import QuerySet
from rest_framework.exceptions import PermissionDenied

from apps.business.models import Business
from apps.accounts.models import Membership

def get_allowed_business_ids(
    user, 
    current_business: Business, 
    scope: str = 'current', 
    selection: Optional[List[int]] = None
) -> List[int]:
    """
    Resolves the list of business IDs allowed for the given scope.
    
    Scopes:
    - 'current': Only the current business (default behavior).
    - 'children': The current business (HQ) + all its active branches.
    - 'selected': A specific subset of branches (must be children of HQ).

    Strict Rules:
    1. 'children'/'selected' require current_business to be HQ (no parent).
    2. 'children'/'selected' require user to be 'owner' or 'admin' of the HQ.
    3. Any ID in 'selected' must be a direct child of the HQ (or the HQ itself).
    """
    if not user or not user.is_authenticated or not current_business:
        return []

    # Default case
    if scope == 'current':
        return [current_business.id]

    # 1. Validate HQ Context
    # Expanded scope is only allowed if acting from HQ
    if current_business.parent is not None:
         raise PermissionDenied("La vista consolidada solo está disponible desde la Casa Matriz.")

    # 2. Validate User Role in HQ
    membership = Membership.objects.filter(user=user, business=current_business).first()
    if not membership or membership.role not in ['owner', 'admin']:
         raise PermissionDenied("Se requieren permisos de administrador/dueño para ver sucursales.")

    children_ids = list(current_business.branches.values_list('id', flat=True))
    allowed_ids = set(children_ids)
    allowed_ids.add(current_business.id)

    if scope == 'children':
        return list(allowed_ids)
    
    if scope == 'selected':
        if not selection:
            return [current_business.id]
        
        final_selection = []
        for bid in selection:
            if bid not in allowed_ids:
                raise PermissionDenied(f"El negocio {bid} no es una sucursal válida de esta cuenta.")
            final_selection.append(bid)
        return final_selection

    return [current_business.id]


def resolve_scope_ids(request) -> List[int]:
	business = getattr(request, 'business')
	scope = request.query_params.get('scope', 'current')
	selection_str = request.query_params.get('business_ids', '')
	selection = [int(s) for s in selection_str.split(',') if s.strip().isdigit()] if selection_str else None
	
	return get_allowed_business_ids(request.user, business, scope, selection)

