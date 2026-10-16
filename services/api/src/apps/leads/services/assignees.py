"""Regla única de asignabilidad de Leads (LEADS 05B.1).

La comparten `LeadUpdateSerializer.validate_assigned_to` (PATCH) y
`GET /api/v1/leads/assignees/`, para que el listado ofrezca exactamente las
personas que el PATCH después acepta.

Asignable = Membership ACTIVA directamente sobre el Business del Lead, usuario
activo y rol con `view_leads` efectivo en el servicio activo (defaults del rol
+ `RolePermissionOverride` del Business de esa membership). Los owner/admin
del HQ que operan una sucursal por herencia NO tienen membership en la
sucursal, así que no son asignables allí.
"""
from __future__ import annotations

from apps.accounts.models import Membership
from apps.accounts.rbac import permissions_for_service


def active_memberships(business_id):
    """Memberships activas de usuarios activos sobre `business_id` (sin herencia HQ)."""
    return Membership.objects.select_related('user', 'business').filter(
        business_id=business_id, status=Membership.Status.ACTIVE, user__is_active=True,
    )


def membership_can_view_leads(membership: Membership, service: str) -> bool:
    return bool(permissions_for_service(service, membership.role, membership.business).get('view_leads', False))


def assignable_memberships(business_id, service: str) -> list[Membership]:
    """Todas las memberships asignables del Business (una por usuario)."""
    by_role: dict[str, bool] = {}
    result = []
    for membership in active_memberships(business_id).order_by('id'):
        if membership.role not in by_role:
            by_role[membership.role] = membership_can_view_leads(membership, service)
        if by_role[membership.role]:
            result.append(membership)
    return result
