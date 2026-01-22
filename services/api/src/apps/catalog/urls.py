from django.urls import path

from .views import ProductDetailView, ProductListCreateView

app_name = 'catalog'

urlpatterns = [
	path('products/', ProductListCreateView.as_view(), name='product-list'),
	path('products/<uuid:pk>/', ProductDetailView.as_view(), name='product-detail'),
]
