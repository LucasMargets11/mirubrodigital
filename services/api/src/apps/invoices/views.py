from __future__ import annotations

from datetime import datetime

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .models import Invoice, InvoiceSeries
from .pdf import render_invoice_pdf
from .serializers import (
  InvoiceDetailSerializer,
  InvoiceIssueSerializer,
  InvoiceListSerializer,
  InvoiceSeriesSerializer,
)


class InvoicesFeatureMixin:
  required_feature = 'invoices'
  feature_denied_message = 'Tu plan no incluye Facturas.'

  def initial(self, request, *args, **kwargs):  # type: ignore[override]
    super().initial(request, *args, **kwargs)
    membership = resolve_request_membership(request)
    if membership is None:
      raise PermissionDenied(self.feature_denied_message)
    context = resolve_business_context(request, membership)
    features = context.get('features', {})
    if not features.get(self.required_feature, False):
      raise PermissionDenied(self.feature_denied_message)


class InvoiceListView(InvoicesFeatureMixin, generics.ListAPIView):
  serializer_class = InvoiceListSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  required_permission = 'view_invoices'
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = Invoice.objects.filter(business=business).select_related('sale', 'series')

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


class InvoiceDetailView(InvoicesFeatureMixin, generics.RetrieveAPIView):
  serializer_class = InvoiceDetailSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  required_permission = 'view_invoices'

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return Invoice.objects.filter(business=business).select_related('sale', 'series', 'sale__customer')

  def get_serializer_context(self):
    context = super().get_serializer_context()
    context.update({'request': self.request})
    return context


class InvoiceSeriesListView(InvoicesFeatureMixin, generics.ListAPIView):
  serializer_class = InvoiceSeriesSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  required_permission = 'issue_invoices'
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return InvoiceSeries.objects.filter(business=business, is_active=True).order_by('code')


class InvoiceIssueView(InvoicesFeatureMixin, APIView):
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
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


class InvoicePDFView(InvoicesFeatureMixin, APIView):
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  required_permission = 'view_invoices'

  def get(self, request, pk: str):
    business = getattr(request, 'business')
    invoice = get_object_or_404(Invoice.objects.select_related('sale', 'sale__customer', 'business'), pk=pk, business=business)
    pdf_bytes = render_invoice_pdf(invoice)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="factura-{invoice.full_number}.pdf"'
    return response
