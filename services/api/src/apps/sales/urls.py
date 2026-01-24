from django.urls import path

from .views import (
	SaleCancelView,
	SaleDetailView,
	SaleListCreateView,
	SalesRecentView,
	SalesTodaySummaryView,
	SalesTopProductsView,
)

app_name = 'sales'

urlpatterns = [
	path('', SaleListCreateView.as_view(), name='sale-list'),
	path('summary/today/', SalesTodaySummaryView.as_view(), name='sales-summary-today'),
	path('recent/', SalesRecentView.as_view(), name='sales-recent'),
	path('top-products/', SalesTopProductsView.as_view(), name='sales-top-products'),
	path('<uuid:pk>/', SaleDetailView.as_view(), name='sale-detail'),
	path('<uuid:pk>/cancel/', SaleCancelView.as_view(), name='sale-cancel'),
]
