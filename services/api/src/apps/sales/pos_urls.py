"""
URL patterns for POS sales operative endpoints.
All routes are prefixed with /api/v1/pos/sales/
"""
from django.urls import path

from .pos_views import PosSaleCreateView

urlpatterns = [
    path('', PosSaleCreateView.as_view(), name='pos-sale-create'),
]
