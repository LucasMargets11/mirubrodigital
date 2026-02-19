from __future__ import annotations

from datetime import datetime

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership, HasPermission, HasEntitlement
from apps.accounts.rbac import permissions_for_service
from apps.business.scope import resolve_scope_ids
from .models import Invoice, InvoiceSeries, DocumentSeries
from .pdf import render_invoice_pdf
from .serializers import (
  InvoiceDetailSerializer,
  InvoiceIssueSerializer,
  InvoiceListSerializer,
  InvoiceSeriesSerializer,
  DocumentSeriesSerializer,
)


class InvoiceListView(generics.ListAPIView):
  serializer_class = InvoiceListSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.invoices'
  required_permission = 'view_invoices'
  pagination_class = None

  def get_queryset(self):
    business_ids = resolve_scope_ids(self.request)
    queryset = Invoice.objects.filter(business__in=business_ids).select_related('sale', 'series')

    status_param = (self.request.query_params.get('status') or '').strip()
    if status_param in Invoice.Status.values:
      queryset = queryset.filter(status=status_param)

    date_from = self._parse_date(self.request.query_params.get('date_from'))
    if date_from:
      queryset = queryset.filter(issued_at__date__gte=date_from)

    date_to = self._parse_date(self.request.query_params.get('date_to'))
    if date_to:
      queryset = queryset.filter(issued_at__date__lte=date_to)

    search = (self.request.query_params.get('q') or '').strip()
    if search:
      filters = Q(full_number__icontains=search) | Q(customer_name__icontains=search)
      if search.isdigit():
        filters |= Q(sale__number=int(search))
      queryset = queryset.filter(filters)

    return queryset.order_by('-issued_at', '-number')

  def get_serializer_context(self):
    context = super().get_serializer_context()
    context.update({'request': self.request})
    return context

  @staticmethod
  def _parse_date(value: str | None):
    if not value:
      return None
    try:
      return datetime.fromisoformat(value).date()
    except ValueError:
      return None


class InvoiceDetailView(generics.RetrieveAPIView):
  serializer_class = InvoiceDetailSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.invoices'
  required_permission = 'view_invoices'

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return Invoice.objects.filter(business=business).select_related('sale', 'series', 'sale__customer')

  def get_serializer_context(self):
    context = super().get_serializer_context()
    context.update({'request': self.request})
    return context


class InvoiceSeriesListView(generics.ListAPIView):
  serializer_class = InvoiceSeriesSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.invoices'
  required_permission = 'issue_invoices'
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return InvoiceSeries.objects.filter(business=business, is_active=True).order_by('code')


class InvoiceIssueView(APIView):
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.invoices'
  required_permission = 'issue_invoices'

  def post(self, request):
    serializer = InvoiceIssueSerializer(data=request.data, context={
      'request': request,
      'business': getattr(request, 'business'),
      'user': request.user,
    })
    serializer.is_valid(raise_exception=True)
    invoice = serializer.save()
    return Response(InvoiceDetailSerializer(invoice, context={'request': request}).data, status=201)


class InvoicePDFView(APIView):
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.invoices'
  required_permission = 'view_invoices'

  def get(self, request, pk: str):
    business = getattr(request, 'business')
    invoice = get_object_or_404(Invoice.objects.select_related('sale', 'sale__customer', 'business'), pk=pk, business=business)
    pdf_bytes = render_invoice_pdf(invoice)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="factura-{invoice.full_number}.pdf"'
    return response


class DocumentSeriesListCreateView(APIView):
  """Vista para listar y crear series de documentos."""
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  required_permission = 'manage_commercial_settings'

  def get(self, request):
    """Listar todas las series del negocio."""
    business = getattr(request, 'business')
    series = DocumentSeries.objects.filter(business=business).order_by('document_type', 'letter', 'point_of_sale')
    serializer = DocumentSeriesSerializer(series, many=True, context={'request': request})
    return Response(serializer.data)

  def post(self, request):
    """Crear una nueva serie de documento."""
    business = getattr(request, 'business')
    serializer = DocumentSeriesSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save(business=business)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentSeriesDetailView(APIView):
  """Vista para actualizar y eliminar una serie de documento."""
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  required_permission = 'manage_commercial_settings'

  def patch(self, request, pk):
    """Actualizar serie de documento."""
    business = getattr(request, 'business')
    series = get_object_or_404(DocumentSeries, pk=pk, business=business)
    serializer = DocumentSeriesSerializer(series, data=request.data, partial=True, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

  def delete(self, request, pk):
    """Eliminar serie de documento (solo si no tiene documentos emitidos)."""
    business = getattr(request, 'business')
    series = get_object_or_404(DocumentSeries, pk=pk, business=business)
    
    # Validar que no tenga documentos emitidos
    if series.next_number > 1:
      return Response(
        {'detail': 'No se puede eliminar una serie que tiene documentos emitidos.'},
        status=status.HTTP_400_BAD_REQUEST
      )
    
    series.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentSeriesSetDefaultView(APIView):
  """Vista para establecer una serie como predeterminada."""
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  required_permission = 'manage_commercial_settings'

  def post(self, request, pk):
    """Establecer serie como predeterminada para su tipo de documento."""
    business = getattr(request, 'business')
    series = get_object_or_404(DocumentSeries, pk=pk, business=business)
    
    # Desactivar otras series default del mismo tipo
    DocumentSeries.objects.filter(
      business=business,
      document_type=series.document_type,
      is_default=True
    ).exclude(pk=series.pk).update(is_default=False)
    
    # Activar esta serie como default
    series.is_default = True
    series.save(update_fields=['is_default'])
    
    serializer = DocumentSeriesSerializer(series, context={'request': request})
    return Response(serializer.data)
