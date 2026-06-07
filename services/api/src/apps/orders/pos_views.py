from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
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

from .models import Order, OrderItem
from .serializers import CounterOrderCreateSerializer, OrderSerializer
from .serializers_kitchen import KitchenItemSerializer, KitchenOrderSerializer


def _can_create_counter_order(employee, business) -> bool:
    service = getattr(business, 'default_service', None) or 'restaurante'
    permissions = resolve_employee_permissions(employee, service)
    capabilities = resolve_pos_capabilities(employee)
    return bool(
        permissions.get('create_orders', False)
        or capabilities.get('can_create_sale', False)
    )


_KITCHEN_ALLOWED_POS_ROLES = {
    'kitchen',
    'manager_op',
}


def _ensure_kitchen_access(request) -> tuple[Response | None, RestaurantOperationSettings | None]:
    employee = request.employee
    business = request.business
    operation_settings = RestaurantOperationSettings.objects.for_business(business)

    if employee.role_type not in _KITCHEN_ALLOWED_POS_ROLES:
        return (
            Response(
                {
                    'detail': 'No tenés permiso para operar cocina.',
                    'code': 'kitchen_permission_required',
                },
                status=status.HTTP_403_FORBIDDEN,
            ),
            None,
        )

    if not operation_settings.kitchen_enabled:
        return (
            Response(
                {
                    'detail': 'La cocina esta deshabilitada para este negocio.',
                    'code': 'kitchen_disabled',
                },
                status=status.HTTP_403_FORBIDDEN,
            ),
            None,
        )

    return None, operation_settings


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


class PosKitchenBoardView(generics.ListAPIView):
    """
    GET /api/v1/pos/orders/kitchen/board/

    Operative kitchen board endpoint for employee terminals.
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]
    serializer_class = KitchenOrderSerializer
    pagination_class = None

    def list(self, request, *args, **kwargs):
        denial_response, _operation_settings = _ensure_kitchen_access(request)
        if denial_response is not None:
            return denial_response
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        business = self.request.business
        updated_after = self.request.query_params.get('updated_after')

        kitchen_active_statuses = [
            OrderItem.KitchenStatus.PENDING,
            OrderItem.KitchenStatus.IN_PROGRESS,
            OrderItem.KitchenStatus.READY,
        ]

        if self.request.query_params.get('include_done') == 'true':
            kitchen_active_statuses.append(OrderItem.KitchenStatus.DONE)

        queryset = (
            Order.objects.filter(
                business=business,
                status=Order.Status.SENT,
                items__kitchen_status__in=kitchen_active_statuses,
            )
            .distinct()
            .prefetch_related('items')
            .order_by('opened_at')
        )

        if updated_after:
            queryset = queryset.filter(updated_at__gt=updated_after)

        return queryset


class PosKitchenItemStatusView(APIView):
    """
    PATCH /api/v1/pos/orders/kitchen/items/<uuid:pk>/

    Updates one kitchen item status for operative kitchen terminals.
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def patch(self, request, pk):
        denial_response, _operation_settings = _ensure_kitchen_access(request)
        if denial_response is not None:
            return denial_response

        item = get_object_or_404(OrderItem, id=pk, order__business=request.business)
        new_status = request.data.get('kitchen_status')
        if not new_status:
            return Response({'error': 'Missing status'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        update_fields = ['kitchen_status', 'last_kitchen_update_at']

        if new_status == OrderItem.KitchenStatus.IN_PROGRESS and not item.kitchen_started_at:
            item.kitchen_started_at = now
            update_fields.append('kitchen_started_at')

        if new_status == OrderItem.KitchenStatus.READY and not item.kitchen_ready_at:
            item.kitchen_ready_at = now
            update_fields.append('kitchen_ready_at')

        if new_status == OrderItem.KitchenStatus.DONE and not item.kitchen_done_at:
            item.kitchen_done_at = now
            update_fields.append('kitchen_done_at')

        item.kitchen_status = new_status
        item.save(update_fields=update_fields)
        item.order.save(update_fields=['updated_at'])

        return Response(KitchenItemSerializer(item).data)


class PosKitchenOrderBulkUpdateView(APIView):
    """
    PATCH /api/v1/pos/orders/kitchen/orders/<uuid:pk>/bulk/

    Bulk-updates all items in one order for operative kitchen terminals.
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def patch(self, request, pk):
        denial_response, _operation_settings = _ensure_kitchen_access(request)
        if denial_response is not None:
            return denial_response

        order = get_object_or_404(Order, id=pk, business=request.business)
        new_status = request.data.get('kitchen_status')
        if not new_status:
            return Response({'error': 'Missing status'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        for item in order.items.all():
            update_fields = ['kitchen_status', 'last_kitchen_update_at']
            item.kitchen_status = new_status

            if new_status == OrderItem.KitchenStatus.IN_PROGRESS and not item.kitchen_started_at:
                item.kitchen_started_at = now
                update_fields.append('kitchen_started_at')

            if new_status == OrderItem.KitchenStatus.READY and not item.kitchen_ready_at:
                item.kitchen_ready_at = now
                update_fields.append('kitchen_ready_at')

            if new_status == OrderItem.KitchenStatus.DONE and not item.kitchen_done_at:
                item.kitchen_done_at = now
                update_fields.append('kitchen_done_at')

            item.save(update_fields=update_fields)

        order.save(update_fields=['updated_at'])
        return Response(KitchenOrderSerializer(order).data)