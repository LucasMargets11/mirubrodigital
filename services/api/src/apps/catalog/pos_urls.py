"""
URL patterns for POS catalog operative endpoints.
All routes are prefixed with /api/v1/pos/catalog/
"""
from django.urls import path

from .pos_views import PosCatalogCategoriesView, PosCatalogProductsView

urlpatterns = [
    path('products/', PosCatalogProductsView.as_view(), name='pos-catalog-products'),
    path('categories/', PosCatalogCategoriesView.as_view(), name='pos-catalog-categories'),
]
