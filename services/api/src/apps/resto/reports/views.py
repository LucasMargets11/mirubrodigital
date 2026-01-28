from __future__ import annotations

from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Dict, List, Optional

from django.db.models import Count, DecimalField, Sum
from django.db.models.functions import Coalesce, TruncDay
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.cash.models import CashSession, Payment
from apps.reports.serializers import CashClosureListSerializer
from apps.reports.views import (
    DateRange,
    ReportsFeatureMixin,
    _format_decimal,
    _format_money,
    _parse_date_range,
    _parse_limit,
    _resolve_timezone,
)
from apps.sales.models import Sale, SaleItem


class RestaurantReportsFeatureMixin(ReportsFeatureMixin):
    required_feature = 'resto_reports'
    feature_denied_message = 'Tu plan no incluye Reportes de Restaurante.'


class RestaurantReportSummaryView(RestaurantReportsFeatureMixin, APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'view_restaurant_reports'

    def get(self, request):
        business = getattr(request, 'business')
        tzinfo = _resolve_timezone(business)
        date_range = _parse_date_range(request.query_params, tzinfo)
        compare_flag = _should_compare(request.query_params.get('compare'))

        payload = _build_summary_payload(business, date_range, tzinfo)
        if compare_flag:
            previous_range = _previous_period(date_range)
            payload['compare'] = _build_summary_payload(business, previous_range, tzinfo)

        return Response(payload)


class RestaurantReportProductsView(RestaurantReportsFeatureMixin, APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'view_restaurant_reports'

    def get(self, request):
        business = getattr(request, 'business')
        tzinfo = _resolve_timezone(business)
        date_range = _parse_date_range(request.query_params, tzinfo)
        limit = _parse_limit(request.query_params.get('limit'), default=10, max_value=50)

        items_queryset = (
            SaleItem.objects.filter(
                sale__business=business,
                sale__status=Sale.Status.COMPLETED,
                sale__created_at__gte=date_range.start,
                sale__created_at__lte=date_range.end,
            )
            .values('product_id', 'product_name_snapshot')
            .annotate(
                total_quantity=Coalesce(Sum('quantity'), Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2)),
                total_amount=Coalesce(Sum('line_total'), Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
            .filter(total_quantity__gt=0)
        )

        top_rows = list(items_queryset.order_by('-total_quantity', '-total_amount')[:limit])
        bottom_rows = list(items_queryset.order_by('total_quantity', 'total_amount')[:limit])

        response = {
            'range': _serialize_range(date_range),
            'top': [_serialize_product_row(row) for row in top_rows],
            'bottom': [_serialize_product_row(row) for row in bottom_rows],
        }
        return Response(response)


class RestaurantReportCashSessionsView(RestaurantReportsFeatureMixin, APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'view_restaurant_reports'

    def get(self, request):
        business = getattr(request, 'business')
        tzinfo = _resolve_timezone(business)
        date_range = _parse_date_range(request.query_params, tzinfo)
        limit = _parse_limit(request.query_params.get('limit'), default=10, max_value=50)

        sessions = (
            CashSession.objects.filter(
                business=business,
                status=CashSession.Status.CLOSED,
                closed_at__isnull=False,
                closed_at__gte=date_range.start,
                closed_at__lte=date_range.end,
            )
            .select_related('register', 'opened_by', 'closed_by')
            .order_by('-closed_at', '-opened_at')[:limit]
        )

        serializer = CashClosureListSerializer(sessions, many=True)
        return Response({'range': _serialize_range(date_range), 'results': serializer.data})


def _should_compare(raw_value: Optional[str]) -> bool:
    if not raw_value:
        return False
    normalized = raw_value.strip().lower()
    return normalized in {'1', 'true', 'yes', 'on'}


def _previous_period(current: DateRange) -> DateRange:
    duration = current.end_local - current.start_local
    previous_end_local = current.start_local - timedelta(seconds=1)
    previous_start_local = previous_end_local - duration
    return DateRange(
        start=previous_start_local.astimezone(dt_timezone.utc),
        end=previous_end_local.astimezone(dt_timezone.utc),
        start_local=previous_start_local,
        end_local=previous_end_local,
    )


def _serialize_range(date_range: DateRange) -> Dict[str, str]:
    return {
        'date_from': date_range.start_local.date().isoformat(),
        'date_to': date_range.end_local.date().isoformat(),
    }


def _build_summary_payload(business, date_range: DateRange, tzinfo):
    sales_queryset = Sale.objects.filter(
        business=business,
        status=Sale.Status.COMPLETED,
        created_at__gte=date_range.start,
        created_at__lte=date_range.end,
    )

    aggregates = sales_queryset.aggregate(
        revenue=Coalesce(Sum('total'), Decimal('0')),
        count=Count('id'),
    )
    revenue_total = aggregates['revenue'] or Decimal('0')
    sales_count = int(aggregates['count'] or 0)
    avg_ticket = Decimal('0')
    if sales_count:
        avg_ticket = (revenue_total / sales_count).quantize(Decimal('0.01'))

    sessions_queryset = CashSession.objects.filter(
        business=business,
        status=CashSession.Status.CLOSED,
        closed_at__isnull=False,
        closed_at__gte=date_range.start,
        closed_at__lte=date_range.end,
    )
    cash_sessions_closed = sessions_queryset.count()
    cash_diff_total = sessions_queryset.aggregate(
        total=Coalesce(Sum('difference_amount'), Decimal('0')),
    )['total'] or Decimal('0')

    payment_rows = (
        Payment.objects.filter(
            business=business,
            created_at__gte=date_range.start,
            created_at__lte=date_range.end,
        )
        .values('method')
        .annotate(
            amount=Coalesce(Sum('amount'), Decimal('0')),
            count=Count('id'),
        )
        .order_by('-amount')
    )
    payments: List[Dict[str, object]] = []
    for row in payment_rows:
        method = row['method']
        try:
            method_label = Payment.Method(method).label
        except ValueError:
            method_label = (method or '').replace('_', ' ').title()
        payments.append(
            {
                'method': method,
                'method_label': method_label,
                'amount': _format_money(row['amount']),
                'count': row['count'],
            }
        )

    series_rows = (
        sales_queryset.annotate(day=TruncDay('created_at', tzinfo=tzinfo))
        .values('day')
        .annotate(
            revenue=Coalesce(Sum('total'), Decimal('0')),
            count=Count('id'),
        )
        .order_by('day')
    )
    series = []
    for row in series_rows:
        period = row['day']
        if period is None:
            continue
        local_period = period.astimezone(tzinfo)
        series.append(
            {
                'date': local_period.date().isoformat(),
                'revenue': _format_money(row['revenue']),
                'sales_count': row['count'],
            }
        )

    kpis = {
        'revenue_total': _format_money(revenue_total),
        'sales_count': sales_count,
        'avg_ticket': _format_money(avg_ticket),
        'cash_sessions_closed': cash_sessions_closed,
        'cash_diff_total': _format_money(cash_diff_total),
        'top_payment_method': payments[0] if payments else None,
    }

    return {
        'range': _serialize_range(date_range),
        'kpis': kpis,
        'payments': payments,
        'series_daily': series,
    }


def _serialize_product_row(row):
    return {
        'product_id': str(row['product_id']) if row.get('product_id') else None,
        'name': row.get('product_name_snapshot') or 'Producto',
        'qty': _format_decimal(row.get('total_quantity') or Decimal('0')),
        'revenue': _format_money(row.get('total_amount') or Decimal('0')),
    }
