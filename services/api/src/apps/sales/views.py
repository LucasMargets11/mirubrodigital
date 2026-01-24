from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db.models import Count, Q, Sum, DecimalField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.cash.models import Payment
from .models import Sale, SaleItem
from .serializers import (
	SaleCancelSerializer,
	SaleCreateSerializer,
	SaleDetailSerializer,
	SaleListSerializer,
	SaleTimelineSerializer,
)


def _annotate_payments_totals(queryset):
	payment_totals = (
		Payment.objects.filter(sale_id=OuterRef('pk'))
		.values('sale_id')
		.annotate(total=Sum('amount'))
		.values('total')[:1]
	)
	zero_value = Value(Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2))
	return queryset.annotate(
		payments_total=Coalesce(
			Subquery(payment_totals, output_field=DecimalField(max_digits=12, decimal_places=2)),
			zero_value,
		)
	)


class SalesPagination(LimitOffsetPagination):

	default_limit = 25
	max_limit = 100
	limit_query_param = 'limit'
	offset_query_param = 'offset'


class SaleListCreateView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_sales',
		'POST': 'create_sales',
	}
	serializer_class = SaleListSerializer
	pagination_class = SalesPagination

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = (
			Sale.objects.filter(business=business)
			.select_related('customer', 'invoice')
			.annotate(items_count=Count('items'))
		)

		status_param = self.request.query_params.get('status') or ''
		statuses = [value.strip() for value in status_param.split(',') if value.strip() in Sale.Status.values]
		if statuses:
			queryset = queryset.filter(status__in=statuses)

		payment_param = self.request.query_params.get('payment_method') or ''
		payment_methods = [value.strip() for value in payment_param.split(',') if value.strip() in Sale.PaymentMethod.values]
		if payment_methods:
			queryset = queryset.filter(payment_method__in=payment_methods)

		date_from = self._parse_date(self.request.query_params.get('date_from'))
		if date_from:
			queryset = queryset.filter(created_at__date__gte=date_from)

		date_to = self._parse_date(self.request.query_params.get('date_to'))
		if date_to:
			queryset = queryset.filter(created_at__date__lte=date_to)

		search = (self.request.query_params.get('search') or '').strip()
		if search:
			uuid_filter = self._parse_uuid(search)
			filters = Q(customer__name__icontains=search) | Q(notes__icontains=search)
			filters |= Q(customer__doc_number__icontains=search)
			filters |= Q(customer__email__icontains=search)
			filters |= Q(customer__phone__icontains=search)
			if search.isdigit():
				filters |= Q(number=int(search))
			if uuid_filter:
				filters |= Q(pk=uuid_filter)
			queryset = queryset.filter(filters)

		queryset = _annotate_payments_totals(queryset)
		return queryset.order_by('-created_at', '-number')

	def get_serializer_class(self):
		if self.request.method == 'POST':
			return SaleCreateSerializer
		return SaleListSerializer

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['business'] = getattr(self.request, 'business')
		return context

	@staticmethod
	def _parse_date(value: str | None):
		if not value:
			return None
		try:
			return datetime.fromisoformat(value).date()
		except ValueError:
			return None

	@staticmethod
	def _parse_uuid(value: str | None):
		if not value:
			return None
		try:
			return UUID(value)
		except (ValueError, AttributeError):
			return None


class SaleDetailView(generics.RetrieveAPIView):
	serializer_class = SaleDetailSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_sales'

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return _annotate_payments_totals(
			Sale.objects.filter(business=business)
			.select_related('customer', 'invoice')
			.prefetch_related('items__product', 'payments')
		)


class SaleCancelView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'cancel_sales'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		sale = get_object_or_404(Sale, pk=pk, business=business)
		serializer = SaleCancelSerializer(data=request.data, context={'sale': sale, 'user': request.user})
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(SaleDetailSerializer(sale, context={'request': request}).data)


class SalesTodaySummaryView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_sales'

	def get(self, request):
		business = getattr(request, 'business')
		today = timezone.localdate()
		queryset = Sale.objects.filter(business=business, status=Sale.Status.COMPLETED, created_at__date=today)
		aggregates = queryset.aggregate(
			total_amount=Coalesce(Sum('total'), Decimal('0')),
			orders=Count('id'),
		)
		total_amount = aggregates['total_amount'] or Decimal('0')
		orders = aggregates['orders'] or 0
		average_ticket = (total_amount / orders) if orders else Decimal('0')
		return Response(
			{
				'total_amount': f"{total_amount:.2f}",
				'orders_count': orders,
				'average_ticket': f"{average_ticket:.2f}",
			}
		)


class SalesRecentView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_sales'

	def get(self, request):
		business = getattr(request, 'business')
		limit = self._resolve_limit(request.query_params.get('limit'), default=5, maximum=20)
		queryset = (
			Sale.objects.filter(business=business)
			.select_related('customer')
			.order_by('-created_at', '-number')[:limit]
		)
		serializer = SaleTimelineSerializer(queryset, many=True)
		return Response(serializer.data)

	@staticmethod
	def _resolve_limit(raw_value: str | None, default: int, maximum: int) -> int:
		try:
			value = int(raw_value) if raw_value is not None else default
		except (TypeError, ValueError):
			value = default
		return max(1, min(value, maximum))


class SalesTopProductsView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_sales'

	def get(self, request):
		business = getattr(request, 'business')
		limit = SalesRecentView._resolve_limit(request.query_params.get('limit'), default=5, maximum=25)
		window_days = self._resolve_range_days(request.query_params.get('range'))
		since = timezone.now() - timedelta(days=window_days)
		items = (
			SaleItem.objects.filter(
				sale__business=business,
				sale__status=Sale.Status.COMPLETED,
				sale__created_at__gte=since,
			)
			.values('product_id', 'product_name_snapshot')
			.annotate(
				total_qty=Coalesce(Sum('quantity'), Decimal('0')),
				total_sales=Coalesce(Sum('line_total'), Decimal('0')),
			)
			.order_by('-total_qty', '-total_sales')[:limit]
		)
		response = [
			{
				'product_id': str(item['product_id']) if item['product_id'] else None,
				'name': item['product_name_snapshot'],
				'total_qty': f"{Decimal(item['total_qty']):.2f}",
				'total_sales': f"{Decimal(item['total_sales']):.2f}",
			}
			for item in items
		]
		return Response({'range_days': window_days, 'items': response})

	@staticmethod
	def _resolve_range_days(raw_value: str | None) -> int:
		if not raw_value:
			return 7
		value = raw_value.lower().strip()
		if value.endswith('d'):
			number = value[:-1]
		else:
			number = value
		try:
			days = int(number)
		except ValueError:
			days = 7
		return max(1, min(days, 90))
