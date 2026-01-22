from django.urls import path

from .views import (
	InventorySummaryView,
	InventoryValuationView,
	ProductStockListView,
	StockMovementDetailView,
	StockMovementListCreateView,
)

app_name = 'inventory'

urlpatterns = [
	path('stock/', ProductStockListView.as_view(), name='stock-list'),
	path('movements/', StockMovementListCreateView.as_view(), name='movement-list'),
	path('movements/<uuid:pk>/', StockMovementDetailView.as_view(), name='movement-detail'),
	path('summary/', InventorySummaryView.as_view(), name='inventory-summary'),
	path('valuation/', InventoryValuationView.as_view(), name='inventory-valuation'),
]
