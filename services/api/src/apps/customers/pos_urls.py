"""
URL patterns for POS operative customer endpoints.
All routes are prefixed with /api/v1/pos/customers/
"""
from django.urls import path

from .pos_views import PosCustomersView

urlpatterns = [
    path('', PosCustomersView.as_view(), name='pos-customers'),
]
