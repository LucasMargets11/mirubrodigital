"""Views para presupuestos (Quotes)."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .models import Quote
from .quote_serializers import (
    QuoteCreateSerializer,
    QuoteDetailSerializer,
    QuoteListSerializer,
    QuoteMarkStatusSerializer,
)


class QuotesPagination(LimitOffsetPagination):
    default_limit = 25
    max_limit = 100
    limit_query_param = 'limit'
    offset_query_param = 'offset'


class QuoteListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_quotes',
        'POST': 'create_quotes',
    }
    serializer_class = QuoteListSerializer
    pagination_class = QuotesPagination

    def get_queryset(self):
        business = getattr(self.request, 'business')
        queryset = (
            Quote.objects.filter(business=business, is_deleted=False)
            .select_related('customer')
            .annotate(items_count=Count('items'))
        )

        # Filtro por status
        status_param = self.request.query_params.get('status') or ''
        statuses = [
            value.strip()
            for value in status_param.split(',')
            if value.strip() in Quote.Status.values
        ]
        if statuses:
            queryset = queryset.filter(status__in=statuses)

        # Filtro por fecha
        date_from = self._parse_date(self.request.query_params.get('date_from'))
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = self._parse_date(self.request.query_params.get('date_to'))
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        # Búsqueda
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            filters = Q(number__icontains=search) | Q(customer_name__icontains=search)
            filters |= Q(customer__name__icontains=search)
            filters |= Q(customer__email__icontains=search)
            filters |= Q(customer__phone__icontains=search)
            filters |= Q(customer_email__icontains=search)
            queryset = queryset.filter(filters)

        # Ordenamiento
        ordering = self.request.query_params.get('ordering', '-created_at')
        allowed_orderings = [
            'number', '-number',
            'total', '-total',
            'status', '-status',
            'valid_until', '-valid_until',
            'created_at', '-created_at',
            'sent_at', '-sent_at',
        ]
        if ordering in allowed_orderings:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-created_at', '-number')

        return queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QuoteCreateSerializer
        return QuoteListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['business'] = getattr(self.request, 'business')
        return context

    def create(self, request, *args, **kwargs):
        """Override to use QuoteDetailSerializer for response."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        
        # Use QuoteDetailSerializer for the response
        response_serializer = QuoteDetailSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @staticmethod
    def _parse_date(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None


class QuoteDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = QuoteDetailSerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_quotes',
        'PATCH': 'manage_quotes',
        'PUT': 'manage_quotes',
        'DELETE': 'manage_quotes',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business')
        return (
            Quote.objects.filter(business=business, is_deleted=False)
            .select_related('customer', 'created_by')
            .prefetch_related('items__product')
        )

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return QuoteCreateSerializer
        return QuoteDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['business'] = getattr(self.request, 'business')
        return context

    def update(self, request, *args, **kwargs):
        """Override to use QuoteDetailSerializer for response."""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        # Use QuoteDetailSerializer for the response
        response_serializer = QuoteDetailSerializer(instance, context=self.get_serializer_context())
        return Response(response_serializer.data)

    def perform_destroy(self, instance):
        """Soft delete."""
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted'])


class QuoteMarkSentView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'send_quotes'

    def post(self, request, pk: str):
        business = getattr(request, 'business')
        quote = get_object_or_404(
            Quote,
            pk=pk,
            business=business,
            is_deleted=False
        )

        # Solo se puede marcar como enviado si está en DRAFT o SENT
        if quote.status not in [Quote.Status.DRAFT, Quote.Status.SENT]:
            return Response(
                {'error': 'El presupuesto no se puede marcar como enviado en su estado actual.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        quote.status = Quote.Status.SENT
        if not quote.sent_at:
            quote.sent_at = timezone.now()
        quote.save(update_fields=['status', 'sent_at'])

        serializer = QuoteDetailSerializer(quote)
        return Response(serializer.data)


class QuoteMarkAcceptedView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_quotes'

    def post(self, request, pk: str):
        business = getattr(request, 'business')
        quote = get_object_or_404(
            Quote,
            pk=pk,
            business=business,
            is_deleted=False
        )

        if quote.status == Quote.Status.CONVERTED:
            return Response(
                {'error': 'El presupuesto ya fue convertido a venta.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        quote.status = Quote.Status.ACCEPTED
        quote.save(update_fields=['status'])

        serializer = QuoteDetailSerializer(quote)
        return Response(serializer.data)


class QuoteMarkRejectedView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_quotes'

    def post(self, request, pk: str):
        business = getattr(request, 'business')
        quote = get_object_or_404(
            Quote,
            pk=pk,
            business=business,
            is_deleted=False
        )

        if quote.status == Quote.Status.CONVERTED:
            return Response(
                {'error': 'El presupuesto ya fue convertido a venta.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        quote.status = Quote.Status.REJECTED
        quote.save(update_fields=['status'])

        serializer = QuoteDetailSerializer(quote)
        return Response(serializer.data)


class QuotePDFView(APIView):
    """Endpoint para descargar el PDF del presupuesto."""
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'view_quotes'

    def get(self, request, pk: str):
        from .quote_pdf import build_quote_pdf

        business = getattr(request, 'business')
        quote = get_object_or_404(
            Quote.objects.select_related('customer', 'business')
            .prefetch_related('items__product'),
            pk=pk,
            business=business,
            is_deleted=False
        )

        pdf_bytes = build_quote_pdf(quote)
        buffer = BytesIO(pdf_bytes)
        filename = f"Presupuesto_{quote.number}.pdf"

        return FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type='application/pdf'
        )
