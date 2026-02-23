from django.urls import path

from .views import (
	ProductCategoryDetailView,
	ProductCategoryListCreateView,
	ProductDetailView,
	ProductListCreateView,
)

app_name = 'catalog'

urlpatterns = [
	path('categories/', ProductCategoryListCreateView.as_view(), name='category-list'),
	path('categories/<uuid:pk>/', ProductCategoryDetailView.as_view(), name='category-detail'),
	path('products/', ProductListCreateView.as_view(), name='product-list'),
	path('products/<uuid:pk>/', ProductDetailView.as_view(), name='product-detail'),
]
