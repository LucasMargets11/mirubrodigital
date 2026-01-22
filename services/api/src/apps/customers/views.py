from rest_framework import generics
from rest_framework.filters import SearchFilter
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .models import Customer
from .serializers import CustomerSerializer


class CustomerPagination(LimitOffsetPagination):
	default_limit = 25
	max_limit = 100
	limit_query_param = 'limit'
	offset_query_param = 'offset'


class CustomerListCreateView(generics.ListCreateAPIView):
  serializer_class = CustomerSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
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
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
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
