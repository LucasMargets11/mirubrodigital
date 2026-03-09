"""
cash/pos_views.py — POS operative endpoints for cash domain.

All routes require X-Employee-Token authentication (EmployeeTokenAuthentication).
Employee must have passed must_change_pin before accessing any of these routes.

Routes
------
  POST /api/v1/pos/cash/open/                → open a cash session
  GET  /api/v1/pos/cash/current/             → get current open session
  POST /api/v1/pos/cash/current/close/       → close current session
  POST /api/v1/pos/cash/current/movements/   → register a cash movement

Capabilities required
---------------------
  can_open_cash   → open / close
  can_close_cash  → close
  can_register_cash_movement → movements
"""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import EmployeeTokenAuthentication
from apps.accounts.models import AccessAuditLog
from apps.accounts.operative_permissions import resolve_pos_capabilities
from apps.accounts.permissions import EmployeeIsAuthenticated, PinChangeNotRequired

from .models import CashSession
from .pos_serializers import (
    PosCashCloseSerializer,
    PosCashMovementCreateSerializer,
    PosCashOpenSerializer,
    PosCashSessionSerializer,
)

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _check_capability(employee, capability: str) -> bool:
    """Return True if the employee has the given POS capability."""
    caps = resolve_pos_capabilities(employee)
    return bool(caps.get(capability, False))


def _get_open_session(employee, business) -> CashSession | None:
    """Return the employee's current open CashSession or None."""
    return (
        CashSession.objects
        .filter(
            business=business,
            status=CashSession.Status.OPEN,
            opened_by_employee=employee,
        )
        .select_related('opened_by_employee', 'register', 'terminal', 'branch')
        .first()
    )


def _audit(action: str, employee, business, entity_type: str = '', entity_id: str = '',
           details: dict | None = None, after_json: dict | None = None) -> None:
    """Create an AccessAuditLog entry for a POS employee cash action."""
    try:
        AccessAuditLog.objects.create(
            action=action,
            actor=None,
            actor_type=AccessAuditLog.ActorType.EMPLOYEE,
            actor_employee=employee,
            target_user=None,
            business=business,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            after_json=after_json,
        )
    except Exception:
        logger.exception('POS audit log creation failed for action=%s employee=%s', action, employee.pk)


# ── Views ──────────────────────────────────────────────────────────────────────


class PosCashOpenView(APIView):
    """
    POST /api/v1/pos/cash/open/

    Opens a new cash session for the authenticated employee.

    Required capability: can_open_cash

    Business rules
    --------------
    - Employee must be ACTIVE and have passed must_change_pin.
    - Employee must not already have an open session.
    - If register_id is provided, that register must not already have an open session.
    - The new session is linked to the employee via opened_by_employee.
    - opened_by (legacy auth.User FK) is intentionally left NULL for POS flows.

    Request (JSON, all optional)
    ----------------------------
    {
        "opening_cash_amount": "500.00",  // default 0
        "register_id": "<uuid>"           // optional — link to physical register
    }

    Response 201
    ------------
    { "session": <PosCashSessionSerializer> }

    Errors
    ------
    403 → capability missing / must_change_pin
    400 → already has open session / register conflict
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def post(self, request) -> Response:
        employee = request.employee
        business = request.business

        if not _check_capability(employee, 'can_open_cash'):
            return Response(
                {'detail': 'No tenés permiso para abrir caja.', 'code': 'capability_required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PosCashOpenSerializer(
            data=request.data,
            context={'employee': employee, 'business': business},
        )
        serializer.is_valid(raise_exception=True)
        session: CashSession = serializer.save()

        _audit(
            action='CASH_SESSION_OPENED',
            employee=employee,
            business=business,
            entity_type='cash_session',
            entity_id=str(session.pk),
            details={
                'opening_cash_amount': str(session.opening_cash_amount),
                'register_id': str(session.register_id) if session.register_id else None,
                'branch_id': session.branch_id,
            },
            after_json={'status': session.status, 'opened_at': session.opened_at.isoformat()},
        )

        return Response(
            {'session': serializer.to_representation(session)},
            status=status.HTTP_201_CREATED,
        )


class PosCashCurrentView(APIView):
    """
    GET /api/v1/pos/cash/current/

    Returns the employee's current open cash session, or null.

    Response 200
    ------------
    { "session": <PosCashSessionSerializer> | null }

    Errors
    ------
    403 → not authenticated / must_change_pin
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def get(self, request) -> Response:
        employee = request.employee
        business = request.business
        session = _get_open_session(employee, business)
        if session is None:
            return Response({'session': None})
        return Response({'session': PosCashSessionSerializer(session).data})


class PosCashCurrentCloseView(APIView):
    """
    POST /api/v1/pos/cash/current/close/

    Closes the employee's current open cash session.

    Required capability: can_close_cash

    Request (JSON, all optional)
    ----------------------------
    {
        "closing_cash_counted": "480.00",  // actual cash counted at close
        "closing_note": "Cierre de turno"
    }

    Response 200
    ------------
    { "session": <PosCashSessionSerializer> }

    Errors
    ------
    403 → capability missing / must_change_pin
    400 → no open session for this employee
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def post(self, request) -> Response:
        employee = request.employee
        business = request.business

        if not _check_capability(employee, 'can_close_cash'):
            return Response(
                {'detail': 'No tenés permiso para cerrar caja.', 'code': 'capability_required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        session = _get_open_session(employee, business)
        if session is None:
            return Response(
                {'detail': 'No tenés una sesión de caja abierta para cerrar.', 'code': 'no_open_session'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PosCashCloseSerializer(
            data=request.data,
            context={'session': session, 'employee': employee},
        )
        serializer.is_valid(raise_exception=True)
        closed_session: CashSession = serializer.save()

        _audit(
            action='CASH_SESSION_CLOSED',
            employee=employee,
            business=business,
            entity_type='cash_session',
            entity_id=str(closed_session.pk),
            details={
                'closing_cash_counted': (
                    str(closed_session.closing_cash_counted)
                    if closed_session.closing_cash_counted is not None else None
                ),
                'expected_cash_total': (
                    str(closed_session.expected_cash_total)
                    if closed_session.expected_cash_total is not None else None
                ),
                'difference_amount': (
                    str(closed_session.difference_amount)
                    if closed_session.difference_amount is not None else None
                ),
            },
            after_json={
                'status': closed_session.status,
                'closed_at': closed_session.closed_at.isoformat() if closed_session.closed_at else None,
            },
        )

        return Response({'session': serializer.to_representation(closed_session)})


class PosCashMovementView(APIView):
    """
    POST /api/v1/pos/cash/current/movements/

    Registers a cash movement (in/out) in the employee's current open session.

    Required capability: can_register_cash_movement

    Request (JSON)
    --------------
    {
        "movement_type": "in" | "out",
        "category": "expense" | "withdraw" | "deposit" | "other",
        "method": "cash" | "debit" | "credit" | "transfer" | "wallet" | "account",
        "amount": "100.00",
        "note": "Cambio de turno"
    }

    Response 201
    ------------
    { "movement": { id, movement_type, category, method, amount, note, created_at, session_id } }

    Errors
    ------
    403 → capability missing / must_change_pin
    400 → no open session / invalid data
    """
    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def post(self, request) -> Response:
        employee = request.employee
        business = request.business

        if not _check_capability(employee, 'can_register_cash_movement'):
            return Response(
                {'detail': 'No tenés permiso para registrar movimientos de caja.', 'code': 'capability_required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        session = _get_open_session(employee, business)
        if session is None:
            return Response(
                {'detail': 'No tenés una sesión de caja abierta.', 'code': 'no_open_session'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PosCashMovementCreateSerializer(
            data=request.data,
            context={'session': session, 'business': business},
        )
        serializer.is_valid(raise_exception=True)
        movement = serializer.save()

        _audit(
            action='CASH_MOVEMENT_CREATED',
            employee=employee,
            business=business,
            entity_type='cash_movement',
            entity_id=str(movement.pk),
            details={
                'movement_type': movement.movement_type,
                'category': movement.category,
                'amount': str(movement.amount),
                'session_id': str(session.pk),
            },
        )

        return Response(
            {'movement': serializer.to_representation(movement)},
            status=status.HTTP_201_CREATED,
        )
