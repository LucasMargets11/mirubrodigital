"""
URL patterns for operative POS endpoints.
All routes are prefixed with /api/v1/pos/
"""
from django.urls import include, path

from .pos_views import PosCapabilitiesView, PosHealthView, PosMeView

urlpatterns = [
    path('me/',           PosMeView.as_view(),           name='pos-me'),
    path('capabilities/', PosCapabilitiesView.as_view(), name='pos-capabilities'),
    path('health/',       PosHealthView.as_view(),       name='pos-health'),
    # Cash domain operative routes
    path('cash/', include('apps.cash.pos_urls')),
    # Sales domain operative routes
    path('sales/', include('apps.sales.pos_urls')),
    # Catalog operative routes (product search for POS terminal)
    path('catalog/', include('apps.catalog.pos_urls')),
    # Customer operative routes (search + create for POS sale creation)
    path('customers/', include('apps.customers.pos_urls')),
]
