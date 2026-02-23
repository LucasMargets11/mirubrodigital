from django.db import models
from django.db.models import Q, F, Count
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .models import Product, ProductCategory
from .serializers import ProductSerializer, ProductCategorySerializer


class ProductCategoryListCreateView(generics.ListCreateAPIView):
	serializer_class = ProductCategorySerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_products',
		'POST': 'manage_products',
	}
	pagination_class = None

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = ProductCategory.objects.filter(business=business)

		# Annotate with products count (only active products)
		queryset = queryset.annotate(
			products_count=Count('products', filter=Q(products__is_active=True))
		)

		include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
		if not include_inactive:
			queryset = queryset.filter(is_active=True)

		search = self.request.query_params.get('search')
		if search:
			queryset = queryset.filter(name__icontains=search)

		return queryset.order_by('name')

	def perform_create(self, serializer):
		serializer.save(business=self.request.business)


class ProductCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
	serializer_class = ProductCategorySerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_products',
		'PUT': 'manage_products',
		'PATCH': 'manage_products',
		'DELETE': 'manage_products',
	}

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return ProductCategory.objects.filter(business=business).annotate(
			products_count=Count('products', filter=Q(products__is_active=True))
		)

	def perform_destroy(self, instance):
		# Soft delete: mark as inactive instead of deleting
		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])


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
		queryset = Product.objects.filter(business=business).select_related('stock_level', 'category')

		include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
		if not include_inactive:
			queryset = queryset.filter(is_active=True)

		# Filter by category
		category_id = self.request.query_params.get('category')
		if category_id is not None:
			if category_id.lower() == 'null' or category_id == '':
				queryset = queryset.filter(category__isnull=True)
			else:
				queryset = queryset.filter(category_id=category_id)

		search = self.request.query_params.get('search')
		if search:
			queryset = queryset.filter(
				Q(name__icontains=search)
				| Q(sku__icontains=search)
				| Q(barcode__icontains=search)
			)

		# Ordering
		ordering = self.request.query_params.get('ordering', 'name')
		valid_orderings = ['name', '-name', 'category__name', '-category__name', 'price', '-price', 'created_at', '-created_at']
		if ordering in valid_orderings:
			# Handle null categories in ordering (put them at the end)
			if 'category__name' in ordering:
				queryset = queryset.order_by(
					models.F('category__name').asc(nulls_last=True) if ordering == 'category__name' 
					else models.F('category__name').desc(nulls_last=True)
				)
			else:
				queryset = queryset.order_by(ordering)
		else:
			queryset = queryset.order_by('name')

		return queryset

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
		return Product.objects.filter(business=business).select_related('stock_level', 'category')

	def perform_destroy(self, instance):
		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])
