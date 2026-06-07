from django.urls import path

from .pos_views import (
    PosCounterOrderCreateView,
    PosKitchenBoardView,
    PosKitchenItemStatusView,
    PosKitchenOrderBulkUpdateView,
)


urlpatterns = [
    path('counter/', PosCounterOrderCreateView.as_view(), name='pos-order-counter-create'),
    path('kitchen/board/', PosKitchenBoardView.as_view(), name='pos-kitchen-board'),
    path('kitchen/items/<uuid:pk>/', PosKitchenItemStatusView.as_view(), name='pos-kitchen-item-status'),
    path('kitchen/orders/<uuid:pk>/bulk/', PosKitchenOrderBulkUpdateView.as_view(), name='pos-kitchen-order-bulk'),
]