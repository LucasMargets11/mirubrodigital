from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission, request_has_permission
from apps.cash.models import CashSession, Payment
from apps.cash.serializers import CashSessionSerializer
from apps.cash.services import get_active_session
from apps.invoices.serializers import InvoiceDetailSerializer, InvoiceIssueSerializer
from apps.invoices.views import InvoicesFeatureMixin
from apps.sales.models import Sale
from apps.sales.serializers import SaleDetailSerializer
from .models import Order, OrderDraft, OrderDraftItem, OrderItem
from .rules import LOCKED_ORDER_MESSAGE, is_order_editable, is_order_paid
from .serializers import (
	OrderCloseSerializer,
	OrderCreateSaleSerializer,
	OrderCreateSerializer,
	OrderDraftAssignTableSerializer,
	OrderDraftConfirmSerializer,
	OrderDraftItemCreateSerializer,
	OrderDraftItemUpdateSerializer,
	OrderDraftSerializer,
	OrderDraftWriteSerializer,
	OrderItemCreateSerializer,
	OrderItemUpdateSerializer,
	OrderPaySerializer,
	OrderSerializer,
	OrderStartSerializer,
	OrderStatusSerializer,
	OrderUpdateSerializer,
)


ACTIVE_ORDER_STATUSES = {Order.Status.OPEN, Order.Status.SENT}
ZERO = Decimal('0')
TWO_PLACES = Decimal('0.01')


class ConflictError(exceptions.APIException):
	status_code = status.HTTP_409_CONFLICT
	default_detail = 'No pudimos completar la operación.'
	default_code = 'conflict'


class OrderDraftListCreateView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'create_orders',
		'POST': 'create_orders',
	}
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return (
			OrderDraft.objects.filter(business=business, status=OrderDraft.Status.EDITING)
			.select_related('table')
			.prefetch_related('items')
		)

	def get_serializer_class(self):
		if self.request.method == 'POST':
			return OrderDraftWriteSerializer
		return OrderDraftSerializer

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['business'] = getattr(self.request, 'business')
		context['request'] = self.request
		context['allow_table_assignment'] = request_has_permission(self.request, 'manage_order_table')
		return context

	def perform_create(self, serializer):
		serializer.save()


class OrderDraftDetailView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'create_orders',
		'PATCH': 'create_orders',
		'DELETE': 'create_orders',
	}

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = OrderDraft.objects.filter(business=business).select_related('table').prefetch_related('items')
		if self.request.method in {'PATCH', 'PUT', 'DELETE'}:
			queryset = queryset.filter(status=OrderDraft.Status.EDITING)
		return queryset

	def get_serializer_class(self):
		if self.request.method in {'PATCH', 'PUT'}:
			return OrderDraftWriteSerializer
		return OrderDraftSerializer

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['business'] = getattr(self.request, 'business')
		context['request'] = self.request
		context['allow_table_assignment'] = request_has_permission(self.request, 'manage_order_table')
		return context


class OrderDraftItemCreateView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		draft = get_object_or_404(
			OrderDraft.objects.filter(business=business, status=OrderDraft.Status.EDITING).prefetch_related('items'),
			pk=pk,
		)
		serializer = OrderDraftItemCreateSerializer(
			data=request.data,
			context={'draft': draft, 'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		payload = serializer.save()
		return Response(payload, status=status.HTTP_201_CREATED)


class OrderDraftItemDetailView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def _get_resources(self, request, pk: str, item_pk: str):
		business = getattr(request, 'business')
		draft = get_object_or_404(
			OrderDraft.objects.filter(business=business, status=OrderDraft.Status.EDITING).prefetch_related('items'),
			pk=pk,
		)
		item = get_object_or_404(OrderDraftItem.objects.filter(draft=draft), pk=item_pk)
		return business, draft, item

	def patch(self, request, pk: str, item_pk: str):
		business, draft, item = self._get_resources(request, pk, item_pk)
		serializer = OrderDraftItemUpdateSerializer(
			instance=item,
			data=request.data,
			partial=True,
			context={'draft': draft, 'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		payload = serializer.save()
		return Response(payload)

	def delete(self, request, pk: str, item_pk: str):
		_business, draft, item = self._get_resources(request, pk, item_pk)
		item.delete()
		draft.recalculate_totals()
		return Response(OrderDraftSerializer(draft, context={'request': request}).data)


class OrderDraftAssignTableView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		allow_assignment = request_has_permission(request, 'manage_order_table')
		draft = get_object_or_404(
			OrderDraft.objects.filter(business=business, status=OrderDraft.Status.EDITING).select_related('table'),
			pk=pk,
		)
		serializer = OrderDraftAssignTableSerializer(
			data=request.data,
			context={
				'draft': draft,
				'business': business,
				'request': request,
				'allow_table_assignment': allow_assignment,
			},
		)
		serializer.is_valid(raise_exception=True)
		draft = serializer.save()
		return Response(OrderDraftSerializer(draft, context={'request': request}).data)


class OrderDraftConfirmView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		draft = get_object_or_404(
			OrderDraft.objects.filter(business=business).prefetch_related('items__product'),
			pk=pk,
		)
		serializer = OrderDraftConfirmSerializer(
			data=request.data,
			context={'draft': draft, 'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		order = serializer.save()
		return Response(
			OrderSerializer(order, context={'request': request, 'business': business}).data,
			status=status.HTTP_201_CREATED,
		)


class OrderStartView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def post(self, request):
		business = getattr(request, 'business')
		serializer = OrderStartSerializer(
			data=request.data,
			context={'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		validated_order = serializer.context.get('validated_order')
		table = serializer.context.get('validated_table')
		with transaction.atomic():
			conflict_qs = (
				Order.objects.select_for_update()
				.filter(business=business, table=table, status__in=ACTIVE_ORDER_STATUSES)
			)
			if validated_order:
				conflict_qs = conflict_qs.exclude(pk=validated_order.pk)
			conflict = conflict_qs.first()
			if conflict:
				return Response(
					{'detail': 'La mesa ya tiene una orden activa.', 'active_order_id': str(conflict.id)},
					status=status.HTTP_409_CONFLICT,
				)
			order = serializer.save()
		return Response(
			OrderSerializer(order, context={'request': request, 'business': business}).data,
			status=status.HTTP_201_CREATED,
		)


class OrderItemCreateView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def _get_order(self, request, pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(
			Order.objects.filter(business=business)
			.select_related('sale')
			.prefetch_related('items__product', 'sale__payments'),
			pk=pk,
		)
		if not is_order_editable(order):
			detail = LOCKED_ORDER_MESSAGE if is_order_paid(order) else 'No podés modificar ítems de una orden cancelada.'
			raise exceptions.ValidationError({'detail': detail})
		return business, order

	def post(self, request, pk: str):
		business, order = self._get_order(request, pk)
		serializer = OrderItemCreateSerializer(
			data=request.data,
			context={'order': order, 'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(
			OrderSerializer(order, context={'request': request, 'business': business}).data,
			status=status.HTTP_201_CREATED,
		)


class OrderItemDetailView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def _get_resources(self, request, pk: str, item_pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(
			Order.objects.filter(business=business)
			.select_related('sale')
			.prefetch_related('items__product', 'sale__payments'),
			pk=pk,
		)
		if not is_order_editable(order):
			detail = LOCKED_ORDER_MESSAGE if is_order_paid(order) else 'No podés modificar ítems de una orden cancelada.'
			raise exceptions.ValidationError({'detail': detail})
		item = get_object_or_404(OrderItem.objects.filter(order=order), pk=item_pk)
		return business, order, item

	def patch(self, request, pk: str, item_pk: str):
		business, order, item = self._get_resources(request, pk, item_pk)
		serializer = OrderItemUpdateSerializer(
			instance=item,
			data=request.data,
			partial=True,
			context={'order': order, 'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)

	def delete(self, request, pk: str, item_pk: str):
		business, order, item = self._get_resources(request, pk, item_pk)
		item.delete()
		order.recalculate_totals()
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)


class OrderListCreateView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_orders',
		'POST': 'create_orders',
	}
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = (
			Order.objects.filter(business=business)
			.select_related('sale', 'sale__invoice')
			.prefetch_related('items', 'sale__payments')
		)

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
		context['allow_table_assignment'] = request_has_permission(self.request, 'manage_order_table')
		return context


class OrderDetailView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_orders',
		'PATCH': 'create_orders',
		'PUT': 'create_orders',
	}

	def _get_order(self, request, pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(
			Order.objects.filter(business=business)
			.select_related('sale', 'sale__invoice')
			.prefetch_related('items__product', 'sale__payments'),
			pk=pk,
		)
		return business, order

	def get(self, request, pk: str):
		business, order = self._get_order(request, pk)
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)

	def patch(self, request, pk: str):
		business, order = self._get_order(request, pk)
		serializer = OrderUpdateSerializer(
			instance=order,
			data=request.data,
			partial=True,
			context={
				'order': order,
				'business': business,
				'request': request,
				'allow_table_assignment': request_has_permission(request, 'manage_order_table'),
			},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)

	def put(self, request, pk: str):
		return self.patch(request, pk)


class OrderInvoiceView(InvoicesFeatureMixin, APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_invoices',
		'POST': 'issue_invoices',
	}

	def _get_order(self, request, pk: str):
		business = getattr(request, 'business')
		return get_object_or_404(
			Order.objects.filter(business=business).select_related('sale', 'sale__invoice', 'sale__customer'),
			pk=pk,
		)

	def _ensure_sale_ready(self, order: Order) -> Sale:
		sale = getattr(order, 'sale', None)
		if sale is None:
			raise exceptions.ValidationError({'detail': 'La orden no tiene una venta asociada.'})
		if sale.status != Sale.Status.COMPLETED:
			raise exceptions.ValidationError({'detail': 'La orden debe estar cobrada para facturar.'})
		return sale

	def get(self, request, pk: str):
		order = self._get_order(request, pk)
		sale = self._ensure_sale_ready(order)
		invoice = getattr(sale, 'invoice', None)
		if not invoice:
			raise exceptions.NotFound('La orden no tiene factura emitida.')
		return Response(InvoiceDetailSerializer(invoice, context={'request': request}).data)

	def post(self, request, pk: str):
		order = self._get_order(request, pk)
		sale = self._ensure_sale_ready(order)
		payload = request.data.copy()
		payload['sale_id'] = str(sale.pk)
		serializer = InvoiceIssueSerializer(
			data=payload,
			context={
				'request': request,
				'business': getattr(request, 'business'),
				'user': request.user,
			},
		)
		serializer.is_valid(raise_exception=True)
		invoice = serializer.save()
		return Response(InvoiceDetailSerializer(invoice, context={'request': request}).data, status=status.HTTP_201_CREATED)


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

		serializer = OrderStatusSerializer(data=request.data, exclude_statuses={Order.Status.PAID})
		serializer.is_valid(raise_exception=True)
		new_status = serializer.validated_data['status']

		order.status = new_status
		user = request.user if request.user.is_authenticated else None
		order.updated_by = user
		if new_status == Order.Status.CANCELLED:
			order.closed_at = timezone.now()
		else:
			order.closed_at = None
		order.save(update_fields=['status', 'updated_at', 'closed_at', 'updated_by'])

		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)


class OrderCloseView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'close_orders'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(
			Order.objects.filter(business=business)
			.select_related('sale')
			.prefetch_related('items__product', 'sale__payments'),
			pk=pk,
		)
		serializer = OrderCloseSerializer(
			data=request.data,
			context={'order': order, 'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		order = serializer.save()
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)


class OrderCancelView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'create_orders'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(Order.objects.filter(business=business).prefetch_related('items'), pk=pk)
		if order.status == Order.Status.PAID:
			return Response({'detail': 'La orden ya fue pagada.'}, status=status.HTTP_400_BAD_REQUEST)
		if order.status == Order.Status.CANCELLED:
			return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)
		order.status = Order.Status.CANCELLED
		order.closed_at = timezone.now()
		order.save(update_fields=['status', 'closed_at', 'updated_at'])
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)


def _decimal_str(value: Decimal | str | int | float) -> str:
	if not isinstance(value, Decimal):
		value = Decimal(value)
	return f"{value.quantize(TWO_PLACES)}"


def build_checkout_payload(*, order: Order, business, request):
	sale = getattr(order, 'sale', None)
	order_total = Decimal(order.total_amount or ZERO)
	sale_total = order_total
	paid_total = ZERO
	sale_payload = None
	if sale is not None:
		sale_total = Decimal(sale.total or sale_total)
		aggregate = sale.payments.aggregate(total=Sum('amount'))
		paid_total = aggregate.get('total') or ZERO
		sale_payload = SaleDetailSerializer(sale, context={'request': request}).data
	balance = sale_total - paid_total
	if balance < ZERO:
		balance = ZERO
	active_session = get_active_session(business)
	return {
		'order': OrderSerializer(order, context={'request': request, 'business': business}).data,
		'sale': sale_payload,
		'totals': {
			'order_total': _decimal_str(order_total),
			'sale_total': _decimal_str(sale_total),
			'paid_total': _decimal_str(paid_total),
			'balance': _decimal_str(balance),
		},
		'payment_methods': [{'value': value, 'label': label} for value, label in Payment.Method.choices],
		'cash_session': CashSessionSerializer(active_session, context={'request': request}).data if active_session else None,
		'allow_partial_payments': False,
		'default_payment_method': Sale.PaymentMethod.CASH,
	}


def resolve_sale_payment_method(payments: list[dict]) -> str:
	methods = {entry.get('method') for entry in payments if entry.get('method')}
	if not methods:
		return Sale.PaymentMethod.CASH
	if len(methods) == 1:
		method = next(iter(methods))
		if method == Payment.Method.CASH:
			return Sale.PaymentMethod.CASH
		if method == Payment.Method.TRANSFER:
			return Sale.PaymentMethod.TRANSFER
		if method in {Payment.Method.DEBIT, Payment.Method.CREDIT}:
			return Sale.PaymentMethod.CARD
	return Sale.PaymentMethod.OTHER


class OrderCheckoutView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'close_orders'

	def get(self, request, pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(
			Order.objects.filter(business=business)
			.select_related('sale')
			.prefetch_related('items', 'sale__payments', 'sale__items'),
			pk=pk,
		)
		payload = build_checkout_payload(order=order, business=business, request=request)
		return Response(payload)


class OrderCreateSaleView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'close_orders'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		order = get_object_or_404(
			Order.objects.filter(business=business)
			.select_related('sale')
			.prefetch_related('items__product', 'sale__payments'),
			pk=pk,
		)
		serializer = OrderCreateSaleSerializer(
			data=request.data,
			context={'order': order, 'business': business, 'request': request},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		refreshed = (
			Order.objects.filter(pk=order.pk)
			.select_related('sale')
			.prefetch_related('items', 'sale__payments', 'sale__items')
			.first()
		)
		payload = build_checkout_payload(order=refreshed or order, business=business, request=request)
		return Response(payload)


class OrderPayView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'close_orders'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		with transaction.atomic():
			order = get_object_or_404(
				Order.objects.select_for_update(of=('self',))
				.filter(business=business)
				.select_related('sale')
				.prefetch_related('items__product', 'sale__payments'),
				pk=pk,
			)
			if is_order_paid(order):
				raise ConflictError(LOCKED_ORDER_MESSAGE)
			if order.status == Order.Status.CANCELLED:
				return Response({'detail': 'No podés cobrar una orden cancelada.'}, status=status.HTTP_400_BAD_REQUEST)

			payload_serializer = OrderPaySerializer(data=request.data)
			payload_serializer.is_valid(raise_exception=True)
			session = self._resolve_session(business=business, session_id=payload_serializer.validated_data.get('cash_session_id'))
			payments_payload = payload_serializer.validated_data['payments']
			if order.sale_id is None:
				bootstrap = OrderCreateSaleSerializer(
					data={'payment_method': Sale.PaymentMethod.CASH, 'discount': '0', 'notes': order.note},
					context={'order': order, 'business': business, 'request': request},
				)
				bootstrap.is_valid(raise_exception=True)
				sale = bootstrap.save()
			else:
				sale = order.sale

			sale_total = Decimal(sale.total or ZERO)
			aggregate = sale.payments.aggregate(total=Sum('amount'))
			paid_total = aggregate.get('total') or ZERO
			balance = (sale_total - paid_total).quantize(TWO_PLACES)
			if balance <= ZERO:
				raise ConflictError('La venta ya está saldada.')

			incoming_total = sum((payment['amount'] for payment in payments_payload), ZERO).quantize(TWO_PLACES)
			if incoming_total != balance:
				raise serializers.ValidationError(
					{'payments': f'Los pagos deben cubrir el saldo pendiente (${_decimal_str(balance)}).'}
				)

			user = request.user if request.user.is_authenticated else None
			for payment in payments_payload:
				Payment.objects.create(
					business=sale.business,
					sale=sale,
					session=session,
					method=payment['method'],
					amount=payment['amount'],
					reference=payment.get('reference') or '',
					created_by=user,
				)

			sale.cash_session = session
			sale.payment_method = resolve_sale_payment_method(payments_payload)
			sale.save(update_fields=['cash_session', 'payment_method', 'updated_at'])

			order.status = Order.Status.PAID
			order.total_amount = sale_total
			order.closed_at = timezone.now()
			update_fields = ['status', 'total_amount', 'closed_at', 'updated_at']
			if user is not None:
				order.updated_by = user
				update_fields.append('updated_by')
			order.save(update_fields=update_fields)

		order = Order.objects.filter(pk=order.pk).select_related('sale').prefetch_related('items').first() or order
		return Response(OrderSerializer(order, context={'request': request, 'business': business}).data)

	@staticmethod
	def _resolve_session(*, business, session_id: str | None):
		if session_id:
			try:
				session = CashSession.objects.get(pk=session_id, business=business)
			except CashSession.DoesNotExist as exc:
				raise serializers.ValidationError({'cash_session_id': 'La sesión de caja no existe.'}) from exc
		else:
			session = get_active_session(business)
		if session is None:
			raise ConflictError('Necesitás abrir una sesión de caja para cobrar.')
		if session.status != CashSession.Status.OPEN:
			raise ConflictError('Esta sesión de caja ya está cerrada.')
		return session
