from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import (
	Case,
	CharField,
	Count,
	DecimalField,
	F,
	IntegerField,
	OuterRef,
	Q,
	Subquery,
	Sum,
	Value,
	When,
)
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.cash.models import CashMovement, CashSession, Payment
from apps.inventory.models import ProductStock
from apps.cash.services import compute_session_totals, get_session_sales_queryset
from apps.sales.models import Sale, SaleItem
from .serializers import (
	CashClosureListSerializer,
	CashMovementSummarySerializer,
	CashPaymentSummarySerializer,
	CashSessionSaleSerializer,
	ReportPaymentSerializer,
	ReportSaleDetailSerializer,
	ReportSaleListSerializer,
)


MONEY_PLACES = Decimal('0.01')


@dataclass
class DateRange:
	start: datetime
	end: datetime
	start_local: datetime
	end_local: datetime

	def as_payload(self, group_by: str) -> Dict[str, str]:
		return {
			'from': self.start_local.date().isoformat(),
			'to': self.end_local.date().isoformat(),
			'group_by': group_by,
		}


def _format_money(value: Optional[Decimal]) -> str:
	if value is None:
		return '0.00'
	if not isinstance(value, Decimal):
		value = Decimal(value)
	return f"{value.quantize(MONEY_PLACES):.2f}"


def _format_decimal(value: Optional[Decimal]) -> str:
	if value is None:
		return '0.00'
	if not isinstance(value, Decimal):
		value = Decimal(value)
	return f"{value.quantize(Decimal('0.01')):.2f}"


def _format_percentage(value: Optional[Decimal]) -> str:
	if value is None:
		return '0.0'
	if not isinstance(value, Decimal):
		value = Decimal(value)
	return f"{value.quantize(Decimal('0.1')):.1f}"


def _resolve_timezone(business) -> ZoneInfo:
	tz_name = getattr(business, 'timezone', None)
	if not tz_name:
		settings_obj = getattr(business, 'settings', None)
		tz_name = getattr(settings_obj, 'timezone', None)
	if tz_name:
		try:
			return ZoneInfo(tz_name)
		except Exception:  # pragma: no cover - fallback to default tz
			pass
	return timezone.get_default_timezone()


def _parse_iso_datetime(raw_value: str, tzinfo: ZoneInfo, end_of_day: bool) -> datetime:
	try:
		parsed = datetime.fromisoformat(raw_value)
	except ValueError as exc:
		raise ValidationError('Formato de fecha inválido.') from exc
	if parsed.tzinfo is None:
		parsed = timezone.make_aware(parsed, tzinfo)
	else:
		parsed = parsed.astimezone(tzinfo)
	if len(raw_value) <= 10:  # solo fecha
		if end_of_day:
			parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
		else:
			parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
	return parsed


def _parse_date_range(params, tzinfo: ZoneInfo) -> DateRange:
	raw_from = params.get('from') or params.get('date_from')
	raw_to = params.get('to') or params.get('date_to')
	now_local = timezone.now().astimezone(tzinfo)
	end_local = _parse_iso_datetime(raw_to, tzinfo, end_of_day=True) if raw_to else now_local.replace(
		hour=23,
		minute=59,
		second=59,
		microsecond=999999,
	)
	default_start = (end_local - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
	start_local = _parse_iso_datetime(raw_from, tzinfo, end_of_day=False) if raw_from else default_start
	if start_local > end_local:
		raise ValidationError('El rango de fechas es inválido (from > to).')
	if (end_local - start_local).days > 366:
		raise ValidationError('El rango máximo es de 366 días.')
	return DateRange(
		start=start_local.astimezone(dt_timezone.utc),
		end=end_local.astimezone(dt_timezone.utc),
		start_local=start_local,
		end_local=end_local,
	)


def _parse_uuid(value: Optional[str]) -> Optional[UUID]:
	if not value:
		return None
	try:
		return UUID(str(value))
	except (ValueError, AttributeError):
		return None


def _parse_list(value: Optional[str], allowed: Iterable[str]) -> List[str]:
	if not value:
		return []
	allowed_set = set(allowed)
	parsed = [item.strip() for item in value.split(',') if item.strip()]
	return [item for item in parsed if item in allowed_set]


def _parse_group_by(params) -> str:
	value = (params.get('group_by') or 'day').lower()
	if value not in {'day', 'week', 'month'}:
		raise ValidationError('group_by debe ser day, week o month.')
	return value


def _parse_statuses(params) -> List[str]:
	statuses = _parse_list(params.get('status'), Sale.Status.values)
	if not statuses:
		return [Sale.Status.COMPLETED]
	return statuses


def _parse_limit(raw_value: Optional[str], default: int = 10, max_value: int = 50) -> int:
	if raw_value in (None, ''):
		return default
	try:
		parsed = int(raw_value)
	except (TypeError, ValueError) as exc:
		raise ValidationError('limit debe ser un número entero.') from exc
	if parsed < 1:
		raise ValidationError('limit debe ser un número positivo.')
	return min(parsed, max_value)


def _parse_products_ordering(raw_value: Optional[str]) -> str:
	value = (raw_value or '').lower()
	ordering_map = {
		'amount': 'total_amount',
		'-amount': '-total_amount',
		'units': 'total_quantity',
		'-units': '-total_quantity',
		'name': 'product_name_snapshot',
		'-name': '-product_name_snapshot',
		'sales': 'sales_count',
		'-sales': '-sales_count',
	}
	return ordering_map.get(value, '-total_amount')


def _apply_sale_filters(queryset, statuses: List[str], payment_methods: List[str], user_id: Optional[UUID]):
	if statuses:
		queryset = queryset.filter(status__in=statuses)
	if payment_methods:
		queryset = queryset.filter(payment_method__in=payment_methods)
	if user_id:
		queryset = queryset.filter(created_by__id=user_id)
	return queryset


def _apply_payment_sale_filters(queryset, statuses: List[str], payment_methods: List[str]):
	if statuses:
		queryset = queryset.filter(sale__status__in=statuses)
	if payment_methods:
		queryset = queryset.filter(sale__payment_method__in=payment_methods)
	return queryset


def _annotate_payments_total(queryset):
	payment_totals = (
		Payment.objects.filter(sale_id=OuterRef('pk'))
		.values('sale_id')
		.annotate(total=Sum('amount'))
		.values('total')[:1]
	)
	zero = Value(Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2))
	return queryset.annotate(
		payments_total=Coalesce(
			Subquery(payment_totals, output_field=DecimalField(max_digits=12, decimal_places=2)),
			zero,
		)
	)


def _apply_sales_search(queryset, term: str):
	if not term:
		return queryset
	filters = Q(customer__name__icontains=term) | Q(notes__icontains=term)
	filters |= Q(customer__doc_number__icontains=term)
	filters |= Q(customer__email__icontains=term)
	filters |= Q(customer__phone__icontains=term)
	if term.isdigit():
		filters |= Q(number=int(term))
	term_uuid = _parse_uuid(term)
	if term_uuid:
		filters |= Q(pk=term_uuid)
	return queryset.filter(filters)


class ReportsFeatureMixin:
	required_feature = 'reports'
	feature_denied_message = 'Tu plan no incluye Reportes.'

	def initial(self, request, *args, **kwargs):  # type: ignore[override]
		super().initial(request, *args, **kwargs)
		membership = resolve_request_membership(request)
		if membership is None:
			raise PermissionDenied(self.feature_denied_message)
		context = resolve_business_context(request, membership)
		features = context.get('features', {})
		if not features.get(self.required_feature, False):
			raise PermissionDenied(self.feature_denied_message)


class ReportsPagination(LimitOffsetPagination):
	default_limit = 25
	max_limit = 100
	limit_query_param = 'limit'
	offset_query_param = 'offset'


class ReportSummaryView(ReportsFeatureMixin, APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports'

	def get(self, request):
		business = getattr(request, 'business')
		tzinfo = _resolve_timezone(business)
		date_range = _parse_date_range(request.query_params, tzinfo)
		group_by = _parse_group_by(request.query_params)
		statuses = _parse_statuses(request.query_params)
		sale_payment_methods = _parse_list(request.query_params.get('payment_method'), Sale.PaymentMethod.values)
		user_id = _parse_uuid(request.query_params.get('user_id'))

		sale_queryset = Sale.objects.filter(
			business=business,
			created_at__gte=date_range.start,
			created_at__lte=date_range.end,
		)
		sale_queryset = _apply_sale_filters(sale_queryset, statuses, sale_payment_methods, user_id)

		aggregates = sale_queryset.aggregate(
			gross=Coalesce(Sum('subtotal'), Decimal('0')),
			net=Coalesce(Sum('total'), Decimal('0')),
			discounts=Coalesce(Sum('discount'), Decimal('0')),
			count=Count('id'),
		)
		sales_count = int(aggregates['count'] or 0)
		gross_total = aggregates['gross'] or Decimal('0')
		net_total = aggregates['net'] or Decimal('0')
		discount_total = aggregates['discounts'] or Decimal('0')
		avg_ticket = Decimal('0')
		if sales_count:
			avg_ticket = (net_total / sales_count).quantize(MONEY_PLACES)

		items_queryset = SaleItem.objects.filter(
			sale__business=business,
			sale__created_at__gte=date_range.start,
			sale__created_at__lte=date_range.end,
		)
		if statuses:
			items_queryset = items_queryset.filter(sale__status__in=statuses)
		if sale_payment_methods:
			items_queryset = items_queryset.filter(sale__payment_method__in=sale_payment_methods)
		if user_id:
			items_queryset = items_queryset.filter(sale__created_by__id=user_id)
		units_sold = items_queryset.aggregate(total=Coalesce(Sum('quantity'), Decimal('0')))['total'] or Decimal('0')

		cancellations_count = Sale.objects.filter(
			business=business,
			status=Sale.Status.CANCELLED,
			cancelled_at__isnull=False,
			cancelled_at__gte=date_range.start,
			cancelled_at__lte=date_range.end,
		).count()

		trunc_map = {'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth}
		grouper = trunc_map[group_by]
		series_rows = (
			sale_queryset.annotate(period=grouper('created_at', tzinfo=tzinfo))
			.values('period')
			.annotate(gross=Coalesce(Sum('total'), Decimal('0')), count=Count('id'))
			.order_by('period')
		)
		series = []
		for row in series_rows:
			period = row['period']
			if period is None:
				continue
			period_local = period.astimezone(tzinfo)
			gross_value = row['gross'] or Decimal('0')
			period_count = row['count'] or 0
			avg_value = Decimal('0')
			if period_count:
				avg_value = (gross_value / period_count).quantize(MONEY_PLACES)
			series.append(
				{
					'period': period_local.date().isoformat(),
					'gross_sales': _format_money(gross_value),
					'sales_count': period_count,
					'avg_ticket': _format_money(avg_value),
				}
			)

		payment_queryset = Payment.objects.filter(
			business=business,
			created_at__gte=date_range.start,
			created_at__lte=date_range.end,
		)
		payment_queryset = _apply_payment_sale_filters(payment_queryset, statuses, sale_payment_methods)
		if user_id:
			payment_queryset = payment_queryset.filter(created_by__id=user_id)

		breakdown_rows = (
			payment_queryset.values('method')
			.annotate(
				amount_total=Coalesce(Sum('amount'), Decimal('0')),
				payments_count=Count('id'),
				sales_count=Count('sale', distinct=True),
			)
			.order_by('-amount_total')
		)
		payments_breakdown: List[Dict[str, object]] = []
		for row in breakdown_rows:
			method = row['method']
			try:
				method_label = Payment.Method(method).label
			except ValueError:
				method_label = method.replace('_', ' ').title()
			payments_breakdown.append(
				{
					'method': method,
					'method_label': method_label,
					'amount_total': _format_money(row['amount_total']),
					'payments_count': row['payments_count'],
					'sales_count': row['sales_count'],
				}
			)

		top_products_rows = (
			items_queryset.values('product_name_snapshot')
			.annotate(
				total_quantity=Coalesce(Sum('quantity'), Decimal('0')),
				total_amount=Coalesce(Sum('line_total'), Decimal('0')),
			)
			.order_by('-total_amount')[:5]
		)
		top_products = [
			{
				'name': row['product_name_snapshot'] or 'Producto',
				'quantity': _format_decimal(row['total_quantity']),
				'amount_total': _format_money(row['total_amount']),
			}
			for row in top_products_rows
		]

		response_payload = {
			'range': date_range.as_payload(group_by),
			'kpis': {
				'gross_sales_total': _format_money(gross_total),
				'net_sales_total': _format_money(net_total),
				'discounts_total': _format_money(discount_total),
				'sales_count': sales_count,
				'avg_ticket': _format_money(avg_ticket),
				'units_sold': _format_decimal(units_sold),
				'cancellations_count': cancellations_count,
			},
			'series': series,
			'payments_breakdown': payments_breakdown,
			'top_products': top_products,
		}
		return Response(response_payload)


class ReportSalesListView(ReportsFeatureMixin, generics.ListAPIView):
	serializer_class = ReportSaleListSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports_sales'
	pagination_class = ReportsPagination

	def get_queryset(self):
		business = getattr(self.request, 'business')
		tzinfo = _resolve_timezone(business)
		date_range = _parse_date_range(self.request.query_params, tzinfo)
		statuses = _parse_statuses(self.request.query_params)
		payment_methods = _parse_list(self.request.query_params.get('payment_method'), Sale.PaymentMethod.values)
		user_id = _parse_uuid(self.request.query_params.get('user_id'))
		search = (self.request.query_params.get('q') or '').strip()

		queryset = (
			Sale.objects.filter(business=business, created_at__gte=date_range.start, created_at__lte=date_range.end)
			.select_related('customer', 'created_by')
			.prefetch_related('payments')
			.annotate(items_count=Count('items'))
		)
		queryset = _apply_sale_filters(queryset, statuses, payment_methods, user_id)
		queryset = _apply_sales_search(queryset, search)
		queryset = _annotate_payments_total(queryset)
		return queryset.order_by('-created_at', '-number')


class ReportSalesDetailView(ReportsFeatureMixin, generics.RetrieveAPIView):
	serializer_class = ReportSaleDetailSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports_sales'

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = (
			Sale.objects.filter(business=business)
			.select_related('customer', 'created_by')
			.prefetch_related('items__product', 'payments')
		)
		return _annotate_payments_total(queryset)


class PaymentsReportView(ReportsFeatureMixin, APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports_sales'
	pagination_class = ReportsPagination()

	def get(self, request):
		business = getattr(request, 'business')
		tzinfo = _resolve_timezone(business)
		date_range = _parse_date_range(request.query_params, tzinfo)
		statuses = _parse_statuses(request.query_params)
		sale_payment_methods = _parse_list(request.query_params.get('payment_method'), Sale.PaymentMethod.values)
		payment_methods = _parse_list(request.query_params.get('method'), Payment.Method.values)
		user_id = _parse_uuid(request.query_params.get('user_id'))
		register_id = _parse_uuid(request.query_params.get('register_id'))
		sale_id = _parse_uuid(request.query_params.get('sale_id'))
		search = (request.query_params.get('q') or '').strip()

		queryset = Payment.objects.filter(
			business=business,
			created_at__gte=date_range.start,
			created_at__lte=date_range.end,
		).select_related('sale', 'sale__customer', 'session__register', 'created_by')
		queryset = _apply_payment_sale_filters(queryset, statuses, sale_payment_methods)
		if payment_methods:
			queryset = queryset.filter(method__in=payment_methods)
		if user_id:
			queryset = queryset.filter(created_by__id=user_id)
		if register_id:
			queryset = queryset.filter(session__register_id=register_id)
		if sale_id:
			queryset = queryset.filter(sale_id=sale_id)
		if search:
			filters = Q(reference__icontains=search) | Q(sale__customer__name__icontains=search)
			if search.isdigit():
				filters |= Q(sale__number=int(search))
			term_uuid = _parse_uuid(search)
			if term_uuid:
				filters |= Q(pk=term_uuid)
			queryset = queryset.filter(filters)

		breakdown_rows = (
			queryset.values('method')
			.annotate(
				amount_total=Coalesce(Sum('amount'), Decimal('0')),
				payments_count=Count('id'),
				sales_count=Count('sale', distinct=True),
			)
			.order_by('-amount_total')
		)
		breakdown = []
		for row in breakdown_rows:
			method = row['method']
			try:
				method_label = Payment.Method(method).label
			except ValueError:
				method_label = method.replace('_', ' ').title()
			breakdown.append(
				{
					'method': method,
					'method_label': method_label,
					'amount_total': _format_money(row['amount_total']),
					'payments_count': row['payments_count'],
					'sales_count': row['sales_count'],
				}
			)

		paginator = ReportsPagination()
		page = paginator.paginate_queryset(queryset.order_by('-created_at'), request, view=self)
		serializer = ReportPaymentSerializer(page, many=True)
		return Response(
			{
				'breakdown': breakdown,
				'results': serializer.data,
				'count': paginator.count,
				'next': paginator.get_next_link(),
				'previous': paginator.get_previous_link(),
			}
		)


class CashClosureListView(ReportsFeatureMixin, generics.ListAPIView):
	serializer_class = CashClosureListSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports_cash'
	pagination_class = ReportsPagination

	def get_queryset(self):
		business = getattr(self.request, 'business')
		tzinfo = _resolve_timezone(business)
		date_range = _parse_date_range(self.request.query_params, tzinfo)
		register_id = _parse_uuid(self.request.query_params.get('register_id'))
		user_id = _parse_uuid(self.request.query_params.get('user_id'))
		status_param = (self.request.query_params.get('status') or 'closed').lower()
		if status_param not in {'open', 'closed', 'all', ''}:
			raise ValidationError('status debe ser open, closed o all.')
		search_query = (self.request.query_params.get('q') or '').strip()

		closed_q = Q(
			status=CashSession.Status.CLOSED,
			closed_at__isnull=False,
			closed_at__gte=date_range.start,
			closed_at__lte=date_range.end,
		)
		open_q = Q(
			status=CashSession.Status.OPEN,
			opened_at__gte=date_range.start,
			opened_at__lte=date_range.end,
		)

		base_queryset = CashSession.objects.filter(business=business).select_related('register', 'opened_by', 'closed_by')
		if status_param == 'open':
			queryset = base_queryset.filter(open_q)
		elif status_param == 'closed' or status_param == '':
			queryset = base_queryset.filter(closed_q)
		else:
			queryset = base_queryset.filter(open_q | closed_q)
		if register_id:
			queryset = queryset.filter(register_id=register_id)
		if user_id:
			queryset = queryset.filter(Q(closed_by__id=user_id) | Q(opened_by__id=user_id))
		if search_query:
			queryset = queryset.filter(
				Q(register__name__icontains=search_query)
				| Q(opened_by__name__icontains=search_query)
				| Q(opened_by_name__icontains=search_query)
				| Q(closed_by__name__icontains=search_query)
			)
		return queryset.annotate(report_sort_timestamp=Coalesce('closed_at', 'opened_at')).order_by('-report_sort_timestamp', '-opened_at')


class CashClosureDetailView(ReportsFeatureMixin, APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports_cash'

	def get(self, request, pk: str):
		business = getattr(request, 'business')
		session = get_object_or_404(
			CashSession.objects.select_related('register', 'opened_by', 'closed_by'),
			pk=pk,
			business=business,
		)
		serializer = CashClosureListSerializer(session)
		totals = compute_session_totals(session)
		expected_breakdown = {
			'saldo_inicial': _format_money(session.opening_cash_amount or Decimal('0')),
			'cash_sales_total': _format_money(totals['cash_payments_total']),
			'movements_in_total': _format_money(totals['movements_in_total']),
			'movements_out_total': _format_money(totals['movements_out_total']),
			'expected_cash': _format_money(totals['cash_expected_total']),
		}
		movements_qs = session.movements.select_related('created_by').order_by('-created_at')
		movements = CashMovementSummarySerializer(movements_qs, many=True).data
		cash_sales_qs = (
			session.payments.filter(method=Payment.Method.CASH)
			.select_related('sale', 'sale__customer')
			.order_by('-created_at')
		)
		cash_sales = CashPaymentSummarySerializer(cash_sales_qs, many=True).data
		session_sales_qs = (
			get_session_sales_queryset(session)
			.select_related('customer')
			.order_by('-created_at', '-number')
		)
		sales_data = CashSessionSaleSerializer(session_sales_qs, many=True).data
		sale_ids = [sale['id'] for sale in sales_data]
		product_rows = []
		if sale_ids:
			product_rows = (
				SaleItem.objects.filter(sale_id__in=sale_ids)
				.values('product_id', 'product_name_snapshot')
				.annotate(
					total_quantity=Coalesce(Sum('quantity'), Decimal('0')),
					total_amount=Coalesce(Sum('line_total'), Decimal('0')),
					sales_count=Count('sale', distinct=True),
				)
				.order_by('-total_amount', '-total_quantity', 'product_name_snapshot')
			)
		products_summary = [
			{
				'product_id': str(row['product_id']) if row['product_id'] else None,
				'name': row['product_name_snapshot'] or 'Producto',
				'quantity': _format_decimal(row['total_quantity']),
				'amount_total': _format_money(row['total_amount']),
				'sales_count': row['sales_count'],
			}
			for row in product_rows
		]

		payments_by_method = {
			method: _format_money(amount)
			for method, amount in totals['payments_by_method'].items()
		}

		payload = {
			**serializer.data,
			'expected_breakdown': expected_breakdown,
			'payments_summary': {
				'payments_total': _format_money(totals['payments_total']),
				'payments_by_method': payments_by_method,
			},
			'cash_sales': cash_sales,
			'sales': sales_data,
			'products_summary': products_summary,
			'movements': movements,
		}
		return Response(payload)


class TopProductsReportView(ReportsFeatureMixin, APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports'

	def get(self, request):
		business = getattr(request, 'business')
		tzinfo = _resolve_timezone(business)
		date_range = _parse_date_range(request.query_params, tzinfo)
		statuses = _parse_statuses(request.query_params)
		sale_payment_methods = _parse_list(request.query_params.get('payment_method'), Sale.PaymentMethod.values)
		user_id = _parse_uuid(request.query_params.get('user_id'))
		metric = (request.query_params.get('metric') or 'amount').lower()
		if metric not in {'amount', 'units'}:
			raise ValidationError('metric debe ser amount o units.')
		limit = _parse_limit(request.query_params.get('limit'), default=10, max_value=25)

		items_queryset = (
			SaleItem.objects.filter(
				sale__business=business,
				sale__created_at__gte=date_range.start,
				sale__created_at__lte=date_range.end,
			)
		)
		if statuses:
			items_queryset = items_queryset.filter(sale__status__in=statuses)
		if sale_payment_methods:
			items_queryset = items_queryset.filter(sale__payment_method__in=sale_payment_methods)
		if user_id:
			items_queryset = items_queryset.filter(sale__created_by__id=user_id)

		totals = items_queryset.aggregate(
			total_amount=Coalesce(Sum('line_total'), Decimal('0')),
			total_units=Coalesce(Sum('quantity'), Decimal('0')),
		)
		total_amount = totals['total_amount'] or Decimal('0')
		total_units = totals['total_units'] or Decimal('0')
		denominator = total_amount if metric == 'amount' else total_units

		ordering = '-total_amount' if metric == 'amount' else '-total_quantity'
		aggregated_rows = (
			items_queryset.values('product_id', 'product_name_snapshot')
			.annotate(
				total_quantity=Coalesce(Sum('quantity'), Decimal('0')),
				total_amount=Coalesce(Sum('line_total'), Decimal('0')),
			)
			.order_by(ordering, '-total_amount', 'product_name_snapshot')[:limit]
		)

		items: List[Dict[str, object]] = []
		for row in aggregated_rows:
			amount_value = row.get('total_amount') or Decimal('0')
			units_value = row.get('total_quantity') or Decimal('0')
			numerator = amount_value if metric == 'amount' else units_value
			share_value = Decimal('0')
			if denominator > 0 and numerator > 0:
				share_value = numerator / denominator * Decimal('100')
			product_id = row.get('product_id')
			items.append(
				{
					'product_id': str(product_id) if product_id else None,
					'name': row.get('product_name_snapshot') or 'Producto',
					'units': _format_decimal(units_value),
					'amount_total': _format_money(amount_value),
					'share_pct': _format_percentage(share_value),
				}
			)

		return Response(
			{
				'range': {
					'from': date_range.start_local.date().isoformat(),
					'to': date_range.end_local.date().isoformat(),
				},
				'metric': metric,
				'items': items,
			}
		)


class ReportProductsView(ReportsFeatureMixin, APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_reports_products'

	def get(self, request):
		business = getattr(request, 'business')
		tzinfo = _resolve_timezone(business)
		date_range = _parse_date_range(request.query_params, tzinfo)
		statuses = _parse_statuses(request.query_params)
		sale_payment_methods = _parse_list(request.query_params.get('payment_method'), Sale.PaymentMethod.values)
		user_id = _parse_uuid(request.query_params.get('user_id'))
		ordering = _parse_products_ordering(request.query_params.get('ordering'))
		search = (request.query_params.get('q') or '').strip()

		items_queryset = (
			SaleItem.objects.filter(
				sale__business=business,
				sale__created_at__gte=date_range.start,
				sale__created_at__lte=date_range.end,
			)
			.select_related('product')
		)
		if statuses:
			items_queryset = items_queryset.filter(sale__status__in=statuses)
		if sale_payment_methods:
			items_queryset = items_queryset.filter(sale__payment_method__in=sale_payment_methods)
		if user_id:
			items_queryset = items_queryset.filter(sale__created_by__id=user_id)
		if search:
			items_queryset = items_queryset.filter(
				Q(product_name_snapshot__icontains=search) | Q(product__sku__icontains=search)
			)

		totals = items_queryset.aggregate(
			units=Coalesce(Sum('quantity'), Decimal('0')),
			amount=Coalesce(Sum('line_total'), Decimal('0')),
		)
		total_units = totals['units'] or Decimal('0')
		total_amount = totals['amount'] or Decimal('0')
		avg_price = Decimal('0')
		if total_units > 0:
			avg_price = (total_amount / total_units).quantize(MONEY_PLACES)

		aggregated = (
			items_queryset.values('product_id', 'product_name_snapshot', 'product__sku')
			.annotate(
				total_quantity=Coalesce(Sum('quantity'), Decimal('0')),
				total_amount=Coalesce(Sum('line_total'), Decimal('0')),
				sales_count=Count('sale', distinct=True),
			)
			.order_by(ordering)
		)

		paginator = ReportsPagination()
		page = paginator.paginate_queryset(aggregated, request, view=self)

		results: List[Dict[str, object]] = []
		for row in page:
			amount_value = row.get('total_amount') or Decimal('0')
			share_value = Decimal('0')
			if total_amount > 0:
				share_value = (amount_value / total_amount * Decimal('100')).quantize(Decimal('0.01'))
			product_id = row.get('product_id')
			results.append(
				{
					'product_id': str(product_id) if product_id else None,
					'name': row.get('product_name_snapshot') or 'Producto',
					'sku': row.get('product__sku') or '',
					'quantity': _format_decimal(row.get('total_quantity')),
					'amount_total': _format_money(amount_value),
					'sales_count': row.get('sales_count') or 0,
					'share': _format_decimal(share_value),
				}
			)

		return Response(
			{
				'totals': {
					'products_count': paginator.count,
					'units': _format_decimal(total_units),
					'gross_sales': _format_money(total_amount),
					'avg_price': _format_money(avg_price),
				},
				'results': results,
				'count': paginator.count,
				'next': paginator.get_next_link(),
				'previous': paginator.get_previous_link(),
			}
		)


class StockAlertsReportView(ReportsFeatureMixin, APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_stock'

	def get(self, request):
		business = getattr(request, 'business')
		default_threshold = getattr(settings, 'REPORTS_LOW_STOCK_THRESHOLD_DEFAULT', Decimal('5'))
		if not isinstance(default_threshold, Decimal):  # pragma: no cover - defensive
			default_threshold = Decimal(str(default_threshold))
		limit = _parse_limit(request.query_params.get('limit'), default=10, max_value=50)

		base_queryset = ProductStock.objects.select_related('product').filter(
			business=business,
			product__is_active=True,
		)
		annotated_queryset = base_queryset.annotate(
			threshold_value=Case(
				When(
					product__stock_min__gt=0,
					then=F('product__stock_min'),
				),
				default=Value(default_threshold),
				output_field=DecimalField(max_digits=12, decimal_places=2),
			),
		).annotate(
			status=Case(
				When(quantity__lte=0, then=Value('OUT')),
				When(quantity__gt=0, quantity__lte=F('threshold_value'), then=Value('LOW')),
				default=Value('OK'),
				output_field=CharField(max_length=8),
			),
			status_order=Case(
				When(quantity__lte=0, then=Value(0)),
				default=Value(1),
				output_field=IntegerField(),
			),
		)

		alerts_queryset = annotated_queryset.filter(status__in=['OUT', 'LOW'])
		out_of_stock_count = alerts_queryset.filter(status='OUT').count()
		low_stock_count = alerts_queryset.filter(status='LOW').count()
		rows = alerts_queryset.order_by('status_order', 'quantity', 'product__name')[:limit]

		items: List[Dict[str, object]] = []
		for stock in rows:
			items.append(
				{
					'product_id': str(stock.product_id),
					'name': stock.product.name,
					'stock': _format_decimal(stock.quantity),
					'threshold': _format_decimal(stock.threshold_value),
					'status': stock.status,
				}
			)

		return Response(
			{
				'low_stock_threshold_default': _format_decimal(default_threshold),
				'out_of_stock_count': out_of_stock_count,
				'low_stock_count': low_stock_count,
				'items': items,
			}
		)

