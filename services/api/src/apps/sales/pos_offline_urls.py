"""
URL patterns for POS offline bootstrap endpoints.
All routes are prefixed with /api/v1/pos/offline/
"""
from django.urls import path

from .pos_offline_views import PosOfflineBootstrapView

urlpatterns = [
    path('bootstrap/', PosOfflineBootstrapView.as_view(), name='pos-offline-bootstrap'),
]
