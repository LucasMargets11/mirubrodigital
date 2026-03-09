"""
accounts/pos_views.py — Operative POS endpoints protected by X-Employee-Token.

All routes require a valid X-Employee-Token header (issued by employee-login).
Routes that are accessible even when must_change_pin=True are explicitly noted.

Routes
------
  GET /api/v1/pos/me/           → employee identity         (pin-change exempt)
  GET /api/v1/pos/capabilities/ → effective permissions + POS capabilities
  GET /api/v1/pos/health/       → auth validation probe     (pin-change exempt)
"""
from __future__ import annotations

import logging

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import EmployeeTokenAuthentication
from apps.accounts.operative_permissions import (
    employee_permissions_summary,
    resolve_pos_capabilities,
)
from apps.accounts.permissions import EmployeeIsAuthenticated, PinChangeNotRequired
from apps.business.context import build_business_context

logger = logging.getLogger(__name__)


class PosMeView(APIView):
    """
    GET /api/v1/pos/me/

    Returns the operative identity of the authenticated employee.
    Accessible even when must_change_pin=True so the POS can render the
    PIN change screen with correct employee data already available.
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated]
    # NOTE: PinChangeNotRequired is intentionally ABSENT — this route is whitelisted.

    def get(self, request) -> Response:
        employee = request.employee
        display_name = employee.alias or f'{employee.first_name} {employee.last_name}'.strip()
        return Response({
            'id':              str(employee.pk),
            'employee_code':   employee.employee_code,
            'display_name':    display_name,
            'full_name':       f'{employee.first_name} {employee.last_name}'.strip(),
            'role_type':       employee.role_type,
            'branch':          employee.branch_id,
            'branch_name':     employee.branch.name if employee.branch else None,
            'status':          employee.status,
            'must_change_pin': employee.must_change_pin,
            'business_id':     employee.business.pk,
            'business_name':   employee.business.name,
        })


class PosCapabilitiesView(APIView):
    """
    GET /api/v1/pos/capabilities/

    Returns the effective RBAC permissions and POS capabilities for the
    authenticated employee.  Blocked when must_change_pin=True — the employee
    must first complete PIN change via POST /auth/employee-change-pin/.
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def get(self, request) -> Response:
        employee = request.employee
        context = build_business_context(employee.business)
        service = context.get('service', 'gestion')
        permissions = employee_permissions_summary(employee, service)
        capabilities = resolve_pos_capabilities(employee)
        return Response({
            'role_type':    employee.role_type,
            'service':      service,
            'permissions':  permissions,
            'capabilities': capabilities,
        })


class PosHealthView(APIView):
    """
    GET /api/v1/pos/health/

    Lightweight auth validation probe.  Can be used by POS terminals to verify
    that the stored employee token is still valid before attempting an operation.
    Accessible even when must_change_pin=True.
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated]
    # NOTE: PinChangeNotRequired is intentionally ABSENT — this route is whitelisted.

    def get(self, request) -> Response:
        employee = request.employee
        return Response({
            'status':          'ok',
            'employee_code':   employee.employee_code,
            'business_id':     employee.business.pk,
            'must_change_pin': employee.must_change_pin,
        })
