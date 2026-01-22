from django.urls import path

from .views import OrderDetailView, OrderListCreateView, OrderStatusUpdateView

app_name = 'orders'

urlpatterns = [
	path('', OrderListCreateView.as_view(), name='order-list'),
	path('<uuid:pk>/', OrderDetailView.as_view(), name='order-detail'),
	path('<uuid:pk>/status/', OrderStatusUpdateView.as_view(), name='order-status'),
]
