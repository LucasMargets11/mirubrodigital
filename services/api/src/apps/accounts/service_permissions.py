"""Effective permissions across services (PROD-02C).

The RBAC maps stay per service (`rbac.SERVICE_ROLE_PERMISSIONS`) and so do
the `RolePermissionOverride` rows. What changes is *which* service a
permission is evaluated in: some capabilities belong to a product that may be
contracted next to a different principal service.

Resolution (never a union of maps):

* Leads capability (`LEADS_PERMISSIONS`) — owner service, first match:
    1. `reception` with effective access (Recepcionista IA contracted),
    2. `reception` as principal service,
    3. `appointments` as principal service (Turnos IA / Turnos Base, as today),
    4. `appointments` with effective access (Turnos contracted next to
       another principal service),
    5. none → False.
  Defaults and explicit allows come only from the owner service. An explicit
  deny (`enabled=False`) in ANY service that provides the capability wins, so
  contracting a second provider never neutralizes a deny.
* Agenda capability (`AGENDA_PERMISSIONS`) — `appointments` when it is the
  principal service, or when Recepcionista is the principal service and Turnos
  has effective access. Any other principal keeps its own map, as before
  (e.g. Gestión + Turnos is unchanged; out of PROD-02C scope). Recepcionista's
  map never contains agenda permissions.
* Everything else (Clientes core, users, settings, Gestión...) — the
  principal (active) service, exactly as before.

`professional` keeps its own path in `request_has_permission`; here it simply
never gets the Leads capability.
"""
from __future__ import annotations

from typing import Dict, Optional

from apps.accounts.rbac import ALL_PERMISSIONS, permissions_for_service

RECEPTION = 'reception'
APPOINTMENTS = 'appointments'

LEADS_PERMISSIONS = frozenset({'view_leads', 'manage_leads', 'manage_agent_channels', 'view_ai_usage'})
AGENDA_PERMISSIONS = frozenset({'view_appointments', 'manage_appointments', 'manage_reminder_automations'})


class _ServiceAccess:
    """Memoized `resolve_subscription(...).access_granted` per service."""

    def __init__(self, business):
        self.business = business
        self._cache: Dict[str, bool] = {}

    def __call__(self, service: str) -> bool:
        if service not in self._cache:
            from apps.billing.runtime import resolve_subscription

            self._cache[service] = bool(
                resolve_subscription(self.business, service_type=service).access_granted
            )
        return self._cache[service]


def leads_providers(business, active_service: str, access=None) -> list[str]:
    """Services providing the Leads capability, owner first (see module doc)."""
    access = access or _ServiceAccess(business)
    providers = []
    if access(RECEPTION) or active_service == RECEPTION:
        providers.append(RECEPTION)
    if active_service == APPOINTMENTS or access(APPOINTMENTS):
        providers.append(APPOINTMENTS)
    return providers


def agenda_service(business, active_service: str, access=None) -> Optional[str]:
    """Service whose map answers agenda permissions (None = no agenda)."""
    access = access or _ServiceAccess(business)
    if active_service == APPOINTMENTS:
        return APPOINTMENTS
    if active_service == RECEPTION:
        return APPOINTMENTS if access(APPOINTMENTS) else None
    return active_service


def _explicit_denies(business, role: str, services, codes) -> set[str]:
    from apps.accounts.models import RolePermissionOverride

    if not services:
        return set()
    return set(RolePermissionOverride.objects.filter(
        business=business, role=role or 'viewer', service__in=list(services),
        permission__in=list(codes), enabled=False,
    ).values_list('permission', flat=True))


def effective_permissions(business, role: str, active_service: str, *, base=None) -> Dict[str, bool]:
    """Effective permission map of `role` in `business` (same shape as permissions_for_service).

    `base` is the per-service map function (defaults to rbac.permissions_for_service);
    request_has_permission passes its own reference so existing test patches apply.
    """
    base = base or permissions_for_service
    access = _ServiceAccess(business)
    maps: Dict[str, Dict[str, bool]] = {active_service: base(active_service, role, business)}

    def map_for(service: str) -> Dict[str, bool]:
        if service not in maps:
            maps[service] = base(service, role, business)
        return maps[service]

    result = dict(maps[active_service])

    providers = [] if role == 'professional' else leads_providers(business, active_service, access)
    if providers:
        owner = map_for(providers[0])
        denied = _explicit_denies(business, role, providers, LEADS_PERMISSIONS)
        for code in LEADS_PERMISSIONS:
            result[code] = bool(owner.get(code, False)) and code not in denied
    else:
        for code in LEADS_PERMISSIONS:
            result[code] = False

    if role != 'professional':
        agenda = agenda_service(business, active_service, access)
        source = map_for(agenda) if agenda else {}
        for code in AGENDA_PERMISSIONS:
            result[code] = bool(source.get(code, False))

    for code in ALL_PERMISSIONS:
        result.setdefault(code, False)
    return result


def permission_in_business(business, role: str, active_service: str, code: str) -> bool:
    return bool(effective_permissions(business, role, active_service).get(code, False))
