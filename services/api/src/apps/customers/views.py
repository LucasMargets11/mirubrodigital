from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.filters import SearchFilter
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasBusinessMembership, HasPermission, HasEntitlement
from apps.sales.models import Quote, Sale
from apps.sales.quote_serializers import QuoteListSerializer
from apps.sales.serializers import SaleListSerializer
from apps.sales.views import _annotate_payments_totals
from .models import Customer
from .serializers import CustomerSerializer


class CustomerPagination(LimitOffsetPagination):
	default_limit = 25
	max_limit = 100
	limit_query_param = 'limit'
	offset_query_param = 'offset'


class CustomerListCreateView(generics.ListCreateAPIView):
  serializer_class = CustomerSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.customers'
  permission_map = {
    'GET': 'view_customers',
    'POST': ('manage_customers', 'create_sales'),
  }
  pagination_class = CustomerPagination
  filter_backends = [SearchFilter]
  search_fields = ['name', 'doc_number', 'email', 'phone', 'note']

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = Customer.objects.filter(business=business)

    include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
    if not include_inactive:
      queryset = queryset.filter(is_active=True)

    return queryset.order_by('name')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = CustomerSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.customers'
  permission_map = {
    'GET': 'view_customers',
    'PUT': 'manage_customers',
    'PATCH': 'manage_customers',
    'DELETE': 'manage_customers',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return Customer.objects.filter(business=business)

  def perform_destroy(self, instance):
    if instance.is_active:
      instance.is_active = False
      instance.save(update_fields=['is_active', 'updated_at'])


class CustomerSalesView(generics.ListAPIView):
  """GET /api/v1/customers/{pk}/sales/ — ventas del cliente paginadas."""
  serializer_class = SaleListSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.customers'
  permission_map = {'GET': 'view_sales'}
  pagination_class = CustomerPagination

  def get_queryset(self):
    business = getattr(self.request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    qs = (
      Sale.objects.filter(business=business, customer=customer)
      .select_related('customer', 'invoice')
      .annotate(items_count=Count('items'))
      .order_by('-created_at', '-number')
    )
    return _annotate_payments_totals(qs)


class CustomerQuotesView(generics.ListAPIView):
  """GET /api/v1/customers/{pk}/quotes/ — presupuestos del cliente paginados."""
  serializer_class = QuoteListSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.customers'
  permission_map = {'GET': 'view_quotes'}
  pagination_class = CustomerPagination

  def get_queryset(self):
    business = getattr(self.request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    return (
      Quote.objects.filter(business=business, customer=customer, is_deleted=False)
      .select_related('customer')
      .annotate(items_count=Count('items'))
      .order_by('-created_at', '-number')
    )

