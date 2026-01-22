from django.urls import path

from .views import SaleCancelView, SaleDetailView, SaleListCreateView

app_name = 'sales'

urlpatterns = [
	path('', SaleListCreateView.as_view(), name='sale-list'),
	path('<uuid:pk>/', SaleDetailView.as_view(), name='sale-detail'),
	path('<uuid:pk>/cancel/', SaleCancelView.as_view(), name='sale-cancel'),
]
