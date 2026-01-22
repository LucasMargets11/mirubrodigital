from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission, request_has_permission
from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer, OrderStatusSerializer


class OrderListCreateView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_orders',
		'POST': 'create_orders',
	}
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = Order.objects.filter(business=business).prefetch_related('items')

		status_param = self.request.query_params.get('status') or ''
		statuses = [value.strip() for value in status_param.split(',') if value.strip()]
		if statuses:
			queryset = queryset.filter(status__in=statuses)

		search = self.request.query_params.get('search') or self.request.query_params.get('q')
		if search:
			if search.isdigit():
				queryset = queryset.filter(number=int(search))
			else:
				queryset = queryset.filter(
					Q(customer_name__icontains=search)
					| Q(table_name__icontains=search)
					| Q(note__icontains=search)
				)

		try:
			limit = int(self.request.query_params.get('limit', '100'))
		except ValueError:
			limit = 100
		limit = max(1, min(limit, 200))
		return queryset.order_by('-opened_at', '-number')[:limit]

	def get_serializer_class(self):
		if self.request.method == 'POST':
			return OrderCreateSerializer
		return OrderSerializer

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['business'] = getattr(self.request, 'business')
		return context


class OrderDetailView(generics.RetrieveAPIView):
	serializer_class = OrderSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_orders'

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return Order.objects.filter(business=business).prefetch_related('items')


class OrderStatusUpdateView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership]

	def post(self, request, pk: str):
		if not (
			request_has_permission(request, 'change_order_status')
			or request_has_permission(request, 'kitchen_update_status')
		):
			return Response({'detail': 'No tenes permisos para actualizar el estado.'}, status=status.HTTP_403_FORBIDDEN)

		business = getattr(request, 'business')
		order = get_object_or_404(Order, pk=pk, business=business)

		serializer = OrderStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		new_status = serializer.validated_data['status']

		order.status = new_status
		user = request.user if request.user.is_authenticated else None
		order.updated_by = user
		if new_status in (Order.Status.DELIVERED, Order.Status.CANCELED):
			order.closed_at = timezone.now()
		else:
			order.closed_at = None
		order.save(update_fields=['status', 'updated_at', 'closed_at', 'updated_by'])

		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)
