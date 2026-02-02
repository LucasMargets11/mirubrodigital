from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .models import Order, OrderItem
from .serializers_kitchen import KitchenOrderSerializer, KitchenItemSerializer


class KitchenBoardView(generics.ListAPIView):
    serializer_class = KitchenOrderSerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_kitchen_board',
    }
    pagination_class = None

    def get_queryset(self):
        business = getattr(self.request, 'business')
        updated_after = self.request.query_params.get('updated_after')

        kitchen_active_statuses = [
            OrderItem.KitchenStatus.PENDING,
            OrderItem.KitchenStatus.IN_PROGRESS,
            OrderItem.KitchenStatus.READY,
        ]

        if self.request.query_params.get('include_done') == 'true':
             kitchen_active_statuses.append(OrderItem.KitchenStatus.DONE)

        queryset = Order.objects.filter(
            business=business,
            status=Order.Status.SENT,
            items__kitchen_status__in=kitchen_active_statuses
        ).distinct()

        if updated_after:
            queryset = queryset.filter(updated_at__gt=updated_after)

        return queryset.prefetch_related('items').order_by('opened_at')


class KitchenItemStatusView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'PATCH': 'view_kitchen_board', # Simplified permission for now
    }

    def patch(self, request, pk):
        business = getattr(request, 'business')
        item = get_object_or_404(OrderItem, id=pk, order__business=business)
        
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
        item.save()
        
        # Touch order to ensure polling picks up the change
        # Even if we return the item, the board view needs to see order updated if we filter by order.updated_at
        item.order.save(update_fields=['updated_at'])

        return Response(KitchenItemSerializer(item).data)


class KitchenOrderBulkUpdateView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'PATCH': 'view_kitchen_board',
    }

    def patch(self, request, pk):
        business = getattr(request, 'business')
        order = get_object_or_404(Order, id=pk, business=business)
        
        new_status = request.data.get('kitchen_status')
        if not new_status:
             return Response({'error': 'Missing status'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        items = order.items.all()
        
        # Logic to update timestamps for all items
        for item in items:
            item.kitchen_status = new_status
            if new_status == OrderItem.KitchenStatus.IN_PROGRESS and not item.kitchen_started_at:
                item.kitchen_started_at = now
            if new_status == OrderItem.KitchenStatus.READY and not item.kitchen_ready_at:
                item.kitchen_ready_at = now
            if new_status == OrderItem.KitchenStatus.DONE and not item.kitchen_done_at:
                item.kitchen_done_at = now
            item.save()
        
        order.save(update_fields=['updated_at'])
        
        return Response(KitchenOrderSerializer(order).data)
