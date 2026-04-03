"""
sales/pos_views.py — POS operative endpoint for the sales domain.

Route:
  POST /api/v1/pos/sales/ — create a sale as an authenticated employee

Auth: EmployeeTokenAuthentication + PinChangeNotRequired
Capability: can_create_sale

Business rules
--------------
  1. Employee must be ACTIVE and have passed must_change_pin.
  2. Employee must have the `can_create_sale` capability.
  3. The sale is automatically linked to the employee's current open cash session
     (if one exists).  If CommercialSettings.block_sales_if_no_open_cash_session
     is True and no open session exists, the serializer will reject the request
     with code CASH_SESSION_REQUIRED.
  4. `created_by` (auth.User FK) is left NULL.  `created_by_employee` is set instead.
  5. All item / stock / customer / settings validations are delegated to
     PosSaleCreateSerializer → SaleCreateSerializer (no logic duplicated here).
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
from apps.cash.models import CashSession

from .pos_serializers import PosSaleCreateSerializer
from .serializers import SaleDetailSerializer

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _check_capability(employee, capability: str) -> bool:
    caps = resolve_pos_capabilities(employee)
    return bool(caps.get(capability, False))


def _get_open_session(employee, business) -> CashSession | None:
    """Return the employee's current open CashSession, or None."""
    return (
        CashSession.objects
        .filter(
            business=business,
            status=CashSession.Status.OPEN,
            opened_by_employee=employee,
        )
        .first()
    )


def _audit_sale_created(employee, business, sale) -> None:
    try:
        AccessAuditLog.objects.create(
            action='SALE_CREATED_POS',
            actor=None,
            actor_type=AccessAuditLog.ActorType.EMPLOYEE,
            actor_employee=employee,
            target_user=None,
            business=business,
            entity_type='sale',
            entity_id=str(sale.pk),
            details={
                'sale_number': sale.number,
                'total': str(sale.total),
                'payment_method': sale.payment_method,
                'items_count': sale.items.count(),
                'cash_session_id': str(sale.cash_session_id) if sale.cash_session_id else None,
            },
            after_json={
                'status': sale.status,
                'created_at': sale.created_at.isoformat(),
            },
        )
    except Exception:
        logger.exception(
            'POS audit log creation failed for SALE_CREATED_POS sale=%s employee=%s',
            sale.pk,
            employee.pk,
        )


# ── Views ──────────────────────────────────────────────────────────────────────


class PosSaleCreateView(APIView):
    """
    POST /api/v1/pos/sales/

    Creates a sale as an authenticated employee.

    Required capability: can_create_sale

    Request (JSON) — Single payment (legacy)
    -----------------------------------------
    {
        "payment_method": "cash" | "transfer" | "card" | "other",
        "items": [{ "product_id": "<uuid>", "quantity": 1 }],
        "customer_id": "<uuid> | null",
        "discount": 0.00,
        "notes": ""
    }

    Request (JSON) — Split payment (new)
    -------------------------------------
    {
        "items": [{ "product_id": "<uuid>", "quantity": 1 }],
        "payments": [
            { "method": "cash", "amount": "10000.00", "reference": "" },
            { "method": "transfer", "amount": "20000.00", "reference": "Op 123" }
        ],
        "customer_id": "<uuid> | null",
        "discount": 0.00,
        "notes": ""
    }

    Note: `cash_session_id` is NOT a request field.  The view automatically
    resolves the employee's current open session and attaches it.

    Response 201
    ------------
    { "sale": <SaleDetailSerializer> }

    Errors
    ------
    403 → capability missing / must_change_pin
    400 → validation errors (items, stock, customer, cash session required, payments sum mismatch)
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def post(self, request) -> Response:
        employee = request.employee
        business = request.business

        if not _check_capability(employee, 'can_create_sale'):
            return Response(
                {'detail': 'No tenés permiso para crear ventas.', 'code': 'capability_required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Auto-resolve the employee's open cash session (may be None).
        cash_session = _get_open_session(employee, business)

        serializer = PosSaleCreateSerializer(
            data=request.data,
            context={
                'employee': employee,
                'business': business,
                'cash_session': cash_session,
                # Intentionally no 'request' key → created_by stays NULL.
            },
        )
        serializer.is_valid(raise_exception=True)
        sale = serializer.save()

        _audit_sale_created(employee, business, sale)

        response_data = SaleDetailSerializer(sale, context={'request': request}).data
        return Response({'sale': response_data}, status=status.HTTP_201_CREATED)
