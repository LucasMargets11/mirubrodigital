from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db.models import Count, Q, Sum, DecimalField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.cash.models import Payment
from .models import Sale
from .serializers import SaleCancelSerializer, SaleCreateSerializer, SaleDetailSerializer, SaleListSerializer


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
