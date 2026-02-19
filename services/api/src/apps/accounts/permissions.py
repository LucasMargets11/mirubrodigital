from typing import Iterable, Optional

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.rbac import permissions_for_service
from apps.business.entitlements import has_entitlement, get_upgrade_hint
from .models import Membership


class HasBusinessMembership(BasePermission):
  message = 'No encontramos un negocio asociado al usuario.'

  def has_permission(self, request: Request, view) -> bool:
    return resolve_request_membership(request) is not None


class HasPermission(BasePermission):
  message = 'No tenes permisos para operar este recurso.'

  def has_permission(self, request: Request, view) -> bool:
    required_permission = None
    permission_map = getattr(view, 'permission_map', None)
    if isinstance(permission_map, dict):
      required_permission = permission_map.get(request.method.upper())
    if required_permission is None:
      required_permission = getattr(view, 'required_permission', None)
    if not required_permission:
      return True
    if isinstance(required_permission, (list, tuple, set, frozenset)):
      return any(request_has_permission(request, perm) for perm in required_permission)
    if isinstance(required_permission, Iterable) and not isinstance(required_permission, (str, bytes)):
      return any(request_has_permission(request, perm) for perm in required_permission)
    return request_has_permission(request, required_permission)


def request_has_permission(request: Request, permission_code: str) -> bool:
  membership = resolve_request_membership(request)
  if membership is None:
    return False
  context = resolve_business_context(request, membership)
  permission_map = getattr(request, '_permission_cache', None)
  if permission_map is None:
    permission_map = permissions_for_service(context['service'], membership.role)
    request._permission_cache = permission_map
  return bool(permission_map.get(permission_code, False))


def get_request_membership(request: Request) -> Optional[Membership]:
  return resolve_request_membership(request)


class HasEntitlement(BasePermission):
  """
  Permission class que verifica que el business tenga el entitlement requerido.
  
  Se usa en conjunto con HasPermission: el business necesita el entitlement
  Y el usuario necesita el permiso RBAC.
  
  Uso:
      class CustomerViewSet(viewsets.ModelViewSet):
          permission_classes = [HasBusinessMembership, HasEntitlement, HasPermission]
          required_entitlement = 'gestion.customers'
          required_permission = 'customers.view_customer'
  """
  message = {
    'code': 'plan_entitlement_required',
    'message': 'Tu plan actual no incluye esta funcionalidad.',
  }

  def has_permission(self, request: Request, view) -> bool:
    # Si no se especifica entitlement requerido, permitir acceso
    required_entitlement = getattr(view, 'required_entitlement', None)
    if not required_entitlement:
      return True
    
    # Obtener el business del contexto
    context = resolve_business_context(request, resolve_request_membership(request))
    if not context or 'business' not in context:
      self.message = 'No se pudo determinar el negocio.'
      return False
    
    business = context['business']
    
    # Verificar el entitlement
    if not has_entitlement(business, required_entitlement):
      upgrade_hint = get_upgrade_hint(required_entitlement)
      self.message = {
        'code': 'plan_entitlement_required',
        'entitlement': required_entitlement,
        'upgrade_hint': upgrade_hint,
        'message': f'Tu plan actual no incluye esta funcionalidad. Actualiza tu plan a {upgrade_hint}.',
      }
      return False
    
    return True
