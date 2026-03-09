"""
URL patterns for POS cash operative endpoints.
All routes are prefixed with /api/v1/pos/cash/
"""
from django.urls import path

from .pos_views import (
    PosCashCurrentCloseView,
    PosCashCurrentView,
    PosCashMovementView,
    PosCashOpenView,
)

urlpatterns = [
    path('open/',              PosCashOpenView.as_view(),         name='pos-cash-open'),
    path('current/',           PosCashCurrentView.as_view(),      name='pos-cash-current'),
    path('current/close/',     PosCashCurrentCloseView.as_view(), name='pos-cash-current-close'),
    path('current/movements/', PosCashMovementView.as_view(),     name='pos-cash-movement-create'),
]
