from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import EmployeeTokenAuthentication
from apps.accounts.operative_permissions import (
    resolve_employee_permissions,
    resolve_pos_capabilities,
)
from apps.accounts.permissions import EmployeeIsAuthenticated, PinChangeNotRequired
from apps.resto.models import RestaurantOperationSettings

from .serializers import CounterOrderCreateSerializer, OrderSerializer


def _can_create_counter_order(employee, business) -> bool:
    service = getattr(business, 'default_service', None) or 'restaurante'
    permissions = resolve_employee_permissions(employee, service)
    capabilities = resolve_pos_capabilities(employee)
    return bool(
        permissions.get('create_orders', False)
        or capabilities.get('can_create_sale', False)
    )


class PosCounterOrderCreateView(APIView):
    """
    POST /api/v1/pos/orders/counter/

    Creates a pickup order for the kitchen flow using operative employee auth.
    Reuses CounterOrderCreateSerializer to keep business rules aligned with
    the owner/staff endpoint at /api/v1/orders/counter/.
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def post(self, request) -> Response:
        employee = request.employee
        business = request.business
        operation_settings = RestaurantOperationSettings.objects.for_business(business)

        if not _can_create_counter_order(employee, business):
            return Response(
                {
                    'detail': 'No tenés permiso para crear pedidos de mostrador.',
                    'code': 'capability_required',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not operation_settings.kitchen_enabled:
            return Response(
                {
                    'detail': 'La cocina esta deshabilitada para este negocio.',
                    'code': 'kitchen_disabled',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not operation_settings.counter_orders_enabled:
            return Response(
                {
                    'detail': 'Los pedidos de mostrador estan deshabilitados para este negocio.',
                    'code': 'counter_orders_disabled',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CounterOrderCreateSerializer(
            data=request.data,
            context={'business': business},
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        return Response(
            OrderSerializer(order, context={'request': request, 'business': business}).data,
            status=status.HTTP_201_CREATED,
        )