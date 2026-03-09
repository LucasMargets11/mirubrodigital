from typing import Iterable, Optional

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.rbac import permissions_for_service
from apps.business.entitlements import get_upgrade_hint
from .models import Membership


def _get_enforcement_decision(request: Request, business):
    """
    Resolve and cache the billing enforcement decision for *business* on *request*.

    Caches the result on the request object to avoid redundant DB queries when
    multiple permission classes check enforcement for the same request.

    Returns EnforcementDecision.
    """
    cached = getattr(request, '_billing_enforcement', None)
    if cached is not None and cached[0] == business.pk:
        return cached[1]

    from apps.billing.runtime import resolve_subscription
    from apps.billing.enforcement import get_enforcement_decision
    resolved = resolve_subscription(business)
    decision = get_enforcement_decision(resolved)
    request._billing_enforcement = (business.pk, decision)
    return decision


class HasBusinessMembership(BasePermission):
    """
    Verifies that the authenticated user has a Membership for a Business.

    In addition to membership resolution, this class applies **global billing
    enforcement** so that suspended, canceled, and access-denied businesses are
    blocked from all operational endpoints without duplicating enforcement logic
    across every ViewSet.

    Bypass mechanism
    ----------------
    Views that must remain accessible regardless of billing state (e.g. billing
    subscription management, plan selection, checkout, support flows) should set
    the class attribute::

        billing_enforcement_bypass = True

    This attribute is checked before enforcement runs.  Auth views (login,
    logout, me) use AllowAny / IsAuthenticated directly and never instantiate
    HasBusinessMembership, so they are implicitly exempt.

    Enforcement policy (mirrors billing.enforcement):
      active / trialing / past_due(grace) → PASS
      past_due(expired) / suspended / canceled                 → BLOCK
      checkout_pending / onboarding / none (no subscription)  → BLOCK
    """
    message = 'No encontramos un negocio asociado al usuario.'

    def has_permission(self, request: Request, view) -> bool:
        membership = resolve_request_membership(request)
        if membership is None:
            return False

        # ── Global billing enforcement ──────────────────────────────────────
        # Skip for views that explicitly opt out (billing, checkout, support).
        if getattr(view, 'billing_enforcement_bypass', False):
            return True

        business = getattr(request, 'business', None)
        if business is not None:
            from apps.billing.enforcement import enforcement_message
            decision = _get_enforcement_decision(request, business)
            if not decision.access_allowed:
                self.message = {
                    'code': 'subscription_access_denied',
                    'reason_code': decision.reason_code,
                    'enforcement_status': decision.enforcement_status,
                    'message': enforcement_message(decision.reason_code),
                    'show_renewal_prompt': decision.show_renewal_prompt,
                    'access_allowed': False,
                }
                return False

        return True


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


# ── Operative (employee) permission classes ───────────────────────────────────


class EmployeeIsAuthenticated(BasePermission):
    """
    Verifies that the request was authenticated via EmployeeTokenAuthentication
    (i.e. request.user is an EmployeeIdentity instance).

    Use as the primary permission class on all POS/operative endpoints.
    """
    message = 'Autenticación operativa requerida.'

    def has_permission(self, request: Request, view) -> bool:
        from apps.accounts.authentication import EmployeeIdentity
        return (
            bool(request.user and request.user.is_authenticated)
            and isinstance(request.user, EmployeeIdentity)
        )


class PinChangeNotRequired(BasePermission):
    """
    Blocks access to operative endpoints when the authenticated employee has
    a mandatory PIN change pending (employee.must_change_pin == True).

    Place this *after* EmployeeIsAuthenticated in permission_classes.

    Whitelisted endpoints (must NOT include this permission class):
      - POST /api/v1/auth/employee-change-pin/
      - GET  /api/v1/pos/me/
      - GET  /api/v1/pos/health/
    """
    message = {
        'error': 'Debe cambiar su PIN antes de continuar.',
        'code':  'pin_change_required',
    }

    def has_permission(self, request: Request, view) -> bool:
        employee = getattr(request, 'employee', None)
        if employee is None:
            # No employee on request — let EmployeeIsAuthenticated handle it.
            return True
        return not employee.must_change_pin


class HasEntitlement(BasePermission):
    """
    Permission class que verifica que el business tenga el entitlement requerido.

    Integra enforcement global de suscripción (billing.enforcement) antes de
    verificar pertenencia al plan.  Si la suscripción está bloqueada globalmente
    (suspended, past_due sin gracia, canceled, etc.) se deniega el acceso aunque
    el plan incluya el entitlement.

    Usa la caché de enforcement del request (_billing_enforcement) cuando
    HasBusinessMembership ya la computó, evitando queries redundantes.

    Se usa en conjunto con HasPermission: el business necesita el entitlement
    Y el usuario necesita el permiso RBAC.

    Uso:
        class CustomerViewSet(viewsets.ModelViewSet):
            permission_classes = [HasBusinessMembership, HasEntitlement, HasPermission]
            required_entitlement = 'gestion.customers'
            required_permission = 'customers.view_customer'

    Respuesta de error incluye:
      - code: 'subscription_access_denied' (bloqueo por estado) o
              'plan_entitlement_required' (plan sin el entitlement)
      - reason_code: código legible por máquina (ver billing.enforcement.ReasonCode)
      - enforcement_status: estado efectivo de la suscripción
      - show_renewal_prompt: bool para que el frontend muestre prompt de renovación
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

        # Obtener el business del request (ya fue resuelto por HasBusinessMembership)
        business = getattr(request, 'business', None)
        if not business:
            self.message = 'No se pudo determinar el negocio.'
            return False

        from apps.billing.enforcement import enforcement_message
        from apps.billing.runtime import resolve_subscription

        # Reuse cached enforcement decision if available (avoids double DB query
        # when HasBusinessMembership already ran for this request).
        cached = getattr(request, '_billing_enforcement', None)
        if cached is not None and cached[0] == business.pk:
            decision = cached[1]
            resolved = resolve_subscription(business)
        else:
            from apps.billing.enforcement import get_enforcement_decision
            resolved = resolve_subscription(business)
            decision = get_enforcement_decision(resolved)
            request._billing_enforcement = (business.pk, decision)

        # ── 1. Enforcement global: bloqueo por estado de suscripción ─────────
        if not decision.access_allowed:
            self.message = {
                'code': 'subscription_access_denied',
                'reason_code': decision.reason_code,
                'enforcement_status': decision.enforcement_status,
                'message': enforcement_message(decision.reason_code),
                'show_renewal_prompt': decision.show_renewal_prompt,
                'source': decision.source,
            }
            return False

        # ── 2. Entitlement por plan: estado permite acceso pero plan no ───────
        if required_entitlement not in resolved.entitlements:
            upgrade_hint = get_upgrade_hint(required_entitlement)
            self.message = {
                'code': 'plan_entitlement_required',
                'entitlement': required_entitlement,
                'reason_code': 'plan_entitlement_required',
                'upgrade_hint': upgrade_hint,
                'message': (
                    f'Tu plan actual no incluye esta funcionalidad. '
                    f'Actualiza tu plan a {upgrade_hint}.'
                ),
            }
            return False

        return True
