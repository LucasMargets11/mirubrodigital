from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission, request_has_permission
from apps.orders.models import Order
from apps.orders.serializers import OrderCreateSerializer, OrderSerializer

from .models import Table
from .serializers import (
	OrderTableAssignmentSerializer,
	TableConfigurationWriteSerializer,
	TableLayoutSerializer,
	TableSerializer,
	TableSettingsSerializer,
)
from .services import (
	apply_table_configuration,
	build_table_status_map,
	build_tables_configuration_payload,
	build_tables_map_state_payload,
	get_or_create_layout,
)


class TableListView(generics.ListAPIView):
	serializer_class = TableSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = ['view_tables', 'manage_order_table']
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return Table.objects.filter(business=business).order_by('code', 'name')

	def get_serializer_context(self):
		context = super().get_serializer_context()
		business = getattr(self.request, 'business')
		context['status_map'] = build_table_status_map(business)
		return context


class TableLayoutView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_tables'

	def get(self, request):
		business = getattr(request, 'business')
		layout = get_or_create_layout(business)
		serializer = TableLayoutSerializer(layout, context={'request': request})
		return Response(serializer.data)


class TableStatusView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_tables'

	def get(self, request):
		business = getattr(request, 'business')
		status_map = build_table_status_map(business)
		return Response({'statuses': status_map, 'generated_at': timezone.now()})


class RestoOrderCreateView(generics.CreateAPIView):
	serializer_class = OrderCreateSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def get_serializer_context(self):
		context = super().get_serializer_context()
		business = getattr(self.request, 'business')
		context['business'] = business
		context['allow_table_assignment'] = request_has_permission(self.request, 'manage_order_table')
		return context


class OrderTableAssignmentView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_order_table'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(Order.objects.filter(business=business).select_related('table'), pk=pk)
		serializer = OrderTableAssignmentSerializer(
			data=request.data,
			context={'order': order, 'business': business},
		)
		serializer.is_valid(raise_exception=True)
		order = serializer.save()
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)


class TableConfigurationView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_tables'

	def get(self, request):
		business = getattr(request, 'business')
		layout = get_or_create_layout(business)
		tables = Table.objects.filter(business=business).order_by('code')
		payload = {
			'tables': TableSettingsSerializer(tables, many=True).data,
			'layout': TableLayoutSerializer(layout, context={'request': request}).data,
		}
		return Response(payload)

	def put(self, request):
		business = getattr(request, 'business')
		serializer = TableConfigurationWriteSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		updated_tables, updated_layout = apply_table_configuration(
			business=business,
			tables_data=serializer.validated_data['tables'],
			layout_data=serializer.validated_data['layout'],
		)
		payload = {
			'tables': TableSettingsSerializer(updated_tables, many=True).data,
			'layout': TableLayoutSerializer(updated_layout, context={'request': request}).data,
		}
		return Response(payload)


class RestaurantTablesSnapshotView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_tables'

	def get(self, request):
		business = getattr(request, 'business')
		payload = build_tables_configuration_payload(business)
		return Response(payload)


class RestaurantTablesMapStateView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_tables'

	def get(self, request):
		business = getattr(request, 'business')
		payload = build_tables_map_state_payload(business)
		return Response(payload)
