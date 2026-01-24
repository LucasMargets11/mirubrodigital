from decimal import Decimal

from django.db.models import (
	Case,
	CharField,
	DecimalField,
	ExpressionWrapper,
	F,
	Q,
	Sum,
	Value,
	When,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership, HasPermission, request_has_permission
from .importer import (
	InventoryImportError,
	apply_inventory_import,
	parse_inventory_import,
	serialize_preview_rows,
)
from .models import InventoryImportJob, ProductStock, StockMovement
from .serializers import (
    InventoryImportJobSerializer,
	ProductStockSerializer,
	StockMovementCreateSerializer,
	StockMovementSerializer,
)


def _resolve_limit(raw_value: str | None, default: int = 5, maximum: int = 50) -> int:
	try:
		value = int(raw_value) if raw_value is not None else default
	except (TypeError, ValueError):
		value = default
	return max(1, min(value, maximum))


def _ensure_inventory_feature(request):
	membership = resolve_request_membership(request)
	if membership is None:
		return None, Response({'detail': 'No encontramos un negocio asociado al usuario.'}, status=403)
	context = resolve_business_context(request, membership)
	features = context.get('features', {})
	if not (features.get('inventory') and features.get('products')):
		return None, Response({'detail': 'Tu plan no incluye importaciones masivas de inventario.'}, status=403)
	return membership, None


class ProductStockListView(generics.ListAPIView):
	serializer_class = ProductStockSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_stock'
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = ProductStock.objects.select_related('product').filter(business=business, product__is_active=True)

		search = self.request.query_params.get('search')
		if search:
			queryset = queryset.filter(
				Q(product__name__icontains=search)
				| Q(product__sku__icontains=search)
				| Q(product__barcode__icontains=search)
			)

		status_filter = self.request.query_params.get('status')
		if status_filter == 'low':
			queryset = queryset.filter(quantity__lt=F('product__stock_min'), quantity__gt=0)
		elif status_filter == 'out':
			queryset = queryset.filter(quantity__lte=0)
		elif status_filter == 'ok':
			queryset = queryset.filter(quantity__gte=F('product__stock_min'))

		return queryset.order_by('product__name')


class StockMovementListCreateView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_stock',
		'POST': 'manage_stock',
	}
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = StockMovement.objects.select_related('product').filter(business=business)
		product_id = self.request.query_params.get('product_id')
		if product_id:
			queryset = queryset.filter(product_id=product_id)
		limit = _resolve_limit(self.request.query_params.get('limit'), default=100, maximum=200)
		return queryset.order_by('-created_at')[:limit]

	def get_serializer_class(self):
		if self.request.method == 'POST':
			return StockMovementCreateSerializer
		return StockMovementSerializer


class StockMovementDetailView(generics.RetrieveAPIView):
	serializer_class = StockMovementSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_stock'

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return StockMovement.objects.select_related('product').filter(business=business)


class InventorySummaryView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_stock'

	def get(self, request):
		business = getattr(request, 'business')
		queryset = ProductStock.objects.select_related('product').filter(business=business, product__is_active=True)
		total_products = queryset.count()
		low_stock = queryset.filter(quantity__lt=F('product__stock_min'), quantity__gt=0).count()
		out_of_stock = queryset.filter(quantity__lte=0).count()

		healthy_products = max(total_products - low_stock - out_of_stock, 0)
		healthy_ratio = (healthy_products / total_products) if total_products else None
		low_ratio = (low_stock / total_products) if total_products else None
		out_ratio = (out_of_stock / total_products) if total_products else None

		return Response(
			{
				'total_products': total_products,
				'low_stock': low_stock,
				'out_of_stock': out_of_stock,
				'healthy_products': healthy_products,
				'healthy_ratio': healthy_ratio,
				'low_ratio': low_ratio,
				'out_ratio': out_ratio,
			}
		)


class LowStockAlertView(generics.ListAPIView):
	serializer_class = ProductStockSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_stock'
	pagination_class = None
	status_filter = 'low'
	maximum_limit = 50

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = ProductStock.objects.select_related('product').filter(
			business=business,
			product__is_active=True,
		)
		if self.status_filter == 'low':
			queryset = queryset.filter(quantity__lt=F('product__stock_min'), quantity__gt=0)
		elif self.status_filter == 'out':
			queryset = queryset.filter(quantity__lte=0)
		ordering = self.request.query_params.get('ordering')
		if ordering == 'qty':
			queryset = queryset.order_by('quantity', 'product__name')
		else:
			queryset = queryset.order_by('product__name')
		limit = _resolve_limit(self.request.query_params.get('limit'), default=5, maximum=self.maximum_limit)
		return queryset[:limit]


class OutOfStockAlertView(LowStockAlertView):
	status_filter = 'out'


class InventoryRecentMovementsView(generics.ListAPIView):
	serializer_class = StockMovementSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_stock'
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		limit = _resolve_limit(self.request.query_params.get('limit'), default=5, maximum=100)
		return StockMovement.objects.select_related('product').filter(business=business).order_by('-created_at')[:limit]


class InventoryValuationView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_stock'

	def get(self, request):
		membership = resolve_request_membership(request)
		if membership is None:
			return Response({'detail': 'No encontramos un negocio asociado al usuario.'}, status=403)

		context = resolve_business_context(request, membership)
		features = context.get('features', {})
		if not (features.get('inventory') and features.get('products')):
			return Response({'detail': 'Tu plan no incluye inventario y productos habilitados.'}, status=403)

		can_view_costs = request_has_permission(request, 'manage_products')
		business = membership.business
		queryset = ProductStock.objects.select_related('product').filter(business=business)

		active_param = request.query_params.get('active')
		if active_param == 'false':
			queryset = queryset.filter(product__is_active=False)
		elif active_param in (None, '', 'true'):
			queryset = queryset.filter(product__is_active=True)

		search = request.query_params.get('q')
		if search:
			queryset = queryset.filter(
				Q(product__name__icontains=search)
				| Q(product__sku__icontains=search)
				| Q(product__barcode__icontains=search)
			)

		status_filter = request.query_params.get('status')
		if status_filter == 'low':
			queryset = queryset.filter(quantity__lt=F('product__stock_min'), quantity__gt=0)
		elif status_filter == 'out':
			queryset = queryset.filter(quantity__lte=0)
		elif status_filter == 'ok':
			queryset = queryset.filter(quantity__gte=F('product__stock_min'))

		if request.query_params.get('only_in_stock') == 'true':
			queryset = queryset.filter(quantity__gt=0)

		sale_value_expr = ExpressionWrapper(
			F('quantity') * F('product__price'),
			output_field=DecimalField(max_digits=24, decimal_places=2),
		)
		cost_value_expr = ExpressionWrapper(
			F('quantity') * F('product__cost'),
			output_field=DecimalField(max_digits=24, decimal_places=2),
		)
		profit_expr = ExpressionWrapper(
			F('quantity') * (F('product__price') - F('product__cost')),
			output_field=DecimalField(max_digits=24, decimal_places=2),
		)
		margin_expr = Case(
			When(
				product__price__gt=0,
				then=ExpressionWrapper(
					(F('product__price') - F('product__cost')) / F('product__price'),
					output_field=DecimalField(max_digits=10, decimal_places=4),
				),
			),
			default=Value(None),
			output_field=DecimalField(max_digits=10, decimal_places=4),
		)
		status_expr = Case(
			When(quantity__lte=0, then=Value('out')),
			When(quantity__lt=F('product__stock_min'), then=Value('low')),
			default=Value('ok'),
			output_field=CharField(max_length=8),
		)

		annotated_queryset = queryset.annotate(
			price=F('product__price'),
			cost=F('product__cost'),
			stock_min=F('product__stock_min'),
			sale_value=sale_value_expr,
			cost_value=cost_value_expr,
			potential_profit=profit_expr,
			margin_pct=margin_expr,
			status=status_expr,
		)

		sort_param = request.query_params.get('sort') or 'sale_value_desc'
		sort_map = {
			'profit_desc': '-potential_profit' if can_view_costs else '-sale_value',
			'sale_value_desc': '-sale_value',
			'qty_desc': '-quantity',
			'name_asc': 'product__name',
		}
		ordering = sort_map.get(sort_param, '-sale_value')
		ordered_queryset = annotated_queryset.order_by(ordering, 'product__name')

		items_count = ordered_queryset.count()
		values_queryset = ordered_queryset.values(
			'product_id',
			'product__name',
			'product__sku',
			'product__is_active',
			'quantity',
			'price',
			'sale_value',
			'stock_min',
			'status',
			'cost',
			'cost_value',
			'potential_profit',
			'margin_pct',
		)

		items = []
		for row in values_queryset:
			item = {
				'product_id': row['product_id'],
				'name': row['product__name'],
				'sku': row['product__sku'],
				'is_active': row['product__is_active'],
				'qty': row['quantity'],
				'price': row['price'],
				'sale_value': row['sale_value'],
				'stock_min': row['stock_min'],
				'status': row['status'],
			}
			if can_view_costs:
				item.update(
					{
						'cost': row['cost'],
						'cost_value': row['cost_value'],
						'potential_profit': row['potential_profit'],
						'margin_pct': row['margin_pct'],
					}
				)
			items.append(item)

		positive_queryset = annotated_queryset.filter(quantity__gt=0)
		total_sale_value = positive_queryset.aggregate(
			total=Coalesce(Sum(sale_value_expr), Decimal('0'))
		)['total']
		total_cost_value = None
		total_potential_profit = None
		if can_view_costs:
			aggregates = positive_queryset.aggregate(
				total_cost=Coalesce(Sum(cost_value_expr), Decimal('0')),
				total_profit=Coalesce(Sum(profit_expr), Decimal('0')),
			)
			total_cost_value = aggregates['total_cost']
			total_potential_profit = aggregates['total_profit']

		return Response(
			{
				'totals': {
					'total_cost_value': total_cost_value,
					'total_sale_value': total_sale_value,
					'total_potential_profit': total_potential_profit,
					'items_count': items_count,
				},
				'items': items,
			}
		)


class InventoryImportUploadView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_stock'
	parser_classes = [MultiPartParser]

	def post(self, request):
		membership, error_response = _ensure_inventory_feature(request)
		if error_response:
			return error_response

		upload = request.FILES.get('file')
		if upload is None:
			return Response({'detail': 'Debes adjuntar un archivo .xlsx.'}, status=400)
		if not (upload.name or '').lower().endswith('.xlsx'):
			return Response({'detail': 'El archivo debe tener formato .xlsx.'}, status=400)

		try:
			rows, summary = parse_inventory_import(upload, business=membership.business)
		except InventoryImportError as exc:
			return Response({'detail': str(exc)}, status=400)

		job = InventoryImportJob.objects.create(
			business=membership.business,
			created_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
			filename=upload.name or 'importar-stock.xlsx',
			rows=rows,
			summary=summary,
			error_count=summary.get('error_count', 0),
			warning_count=summary.get('warning_count', 0),
		)
		serializer = InventoryImportJobSerializer(job)
		return Response(serializer.data, status=201)


class InventoryImportDetailView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_stock'

	def get(self, request, import_id):
		membership, error_response = _ensure_inventory_feature(request)
		if error_response:
			return error_response
		job = get_object_or_404(InventoryImportJob, pk=import_id, business=membership.business)
		serializer = InventoryImportJobSerializer(job)
		return Response(serializer.data)


class InventoryImportPreviewView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_stock'

	def post(self, request, import_id):
		membership, error_response = _ensure_inventory_feature(request)
		if error_response:
			return error_response
		job = get_object_or_404(InventoryImportJob, pk=import_id, business=membership.business)
		return Response({'summary': job.summary or {}, 'rows': serialize_preview_rows(job.rows)})


class InventoryImportApplyView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_stock'

	def post(self, request, import_id):
		membership, error_response = _ensure_inventory_feature(request)
		if error_response:
			return error_response
		job = get_object_or_404(InventoryImportJob, pk=import_id, business=membership.business)
		if job.status == InventoryImportJob.Status.PROCESSING:
			return Response({'detail': 'La importación ya se está procesando.'}, status=409)
		if job.status == InventoryImportJob.Status.DONE:
			serializer = InventoryImportJobSerializer(job)
			return Response(serializer.data)
		try:
			apply_inventory_import(job, business=membership.business, user=request.user)
		except InventoryImportError as exc:
			return Response({'detail': str(exc)}, status=400)
		serializer = InventoryImportJobSerializer(job)
		return Response(serializer.data)
