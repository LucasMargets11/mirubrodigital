from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .models import Product
from .serializers import ProductSerializer


class ProductListCreateView(generics.ListCreateAPIView):
	serializer_class = ProductSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_products',
		'POST': 'manage_products',
	}
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = Product.objects.filter(business=business)

		include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
		if not include_inactive:
			queryset = queryset.filter(is_active=True)

		search = self.request.query_params.get('search')
		if search:
			queryset = queryset.filter(
				Q(name__icontains=search)
				| Q(sku__icontains=search)
				| Q(barcode__icontains=search)
			)

		return queryset.order_by('name')

	def perform_create(self, serializer):
		serializer.save(business=self.request.business)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
	serializer_class = ProductSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_products',
		'PUT': 'manage_products',
		'PATCH': 'manage_products',
		'DELETE': 'manage_products',
	}

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return Product.objects.filter(business=business)

	def perform_destroy(self, instance):
		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])
