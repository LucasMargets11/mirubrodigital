"""Single rule for *operational* access to the Turnos agenda (PROD-02D).

A Business can operate the agenda (services, professionals, schedules,
availability, appointments, proposals) only while it has an effective Turnos
subscription. This is a commercial check and complements RBAC: a role, an
override (`manage_appointments`), the owner role, a session flag,
`Business.service_type` or existing professionals/appointments never grant it.

Rule (fail closed on any error):
  1. `resolve_subscription(business, 'appointments')` finds a real Turnos
     subscription (V2 or legacy) with `access_granted` — so suspended,
     canceled, checkout_pending and not-yet-started benefits are out;
  2. it is a Turnos plan (`is_appointments_plan_code`);
  3. the billing enforcement decision allows access;
  4. for V2, the Turnos lifecycle also allows creation
     (`appointments_v2_allows_creation`, e.g. cancel-at-period-end boundary).
Legacy Turnos subscriptions keep working. Unlike
`business_has_service('appointments')`, a Business without any subscription
is never granted agenda through its `service_type`.
"""
from __future__ import annotations

import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

AGENDA_UNAVAILABLE = {
    'code': 'agenda_unavailable',
    'message': 'La agenda de Turnos no está disponible para este negocio.',
}


def has_agenda_access(business, *, at=None) -> bool:
    if business is None:
        return False
    try:
        from apps.billing.enforcement import get_enforcement_decision
        from apps.billing.runtime import is_appointments_plan_code, resolve_subscription
        from apps.billing.services.appointments_lifecycle import appointments_v2_allows_creation

        resolved = resolve_subscription(business, service_type='appointments')
        if resolved.source == 'none' or not resolved.access_granted:
            return False
        if resolved.service_type != 'appointments' or not is_appointments_plan_code(resolved.plan or ''):
            return False
        if not get_enforcement_decision(resolved).access_allowed:
            return False
        if resolved.source == 'v2' and appointments_v2_allows_creation(business, at=at) is False:
            return False
        return True
    except Exception:  # noqa: BLE001 — ambiguous state never opens the agenda
        logger.exception('agenda_access check failed business=%s', getattr(business, 'pk', None))
        return False


class HasAgendaAccess(BasePermission):
    """DRF guard: the request's Business must have operational Turnos access."""

    message = AGENDA_UNAVAILABLE

    def has_permission(self, request, view) -> bool:
        return has_agenda_access(getattr(request, 'business', None))
