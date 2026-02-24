from django.urls import path

from .views import (
	InventoryImportApplyView,
	InventoryImportDetailView,
	InventoryImportPreviewView,
	InventoryImportUploadView,
	InventoryRecentMovementsView,
	InventorySummaryView,
	InventoryValuationView,
	LowStockAlertView,
	OutOfStockAlertView,
	ProductStockListView,
	ReplenishmentDetailView,
	ReplenishmentListCreateView,
	ReplenishmentVoidView,
	StockMovementDetailView,
	StockMovementListCreateView,
)

app_name = 'inventory'

urlpatterns = [
	path('stock/', ProductStockListView.as_view(), name='stock-list'),
	path('low-stock/', LowStockAlertView.as_view(), name='low-stock'),
	path('out-of-stock/', OutOfStockAlertView.as_view(), name='out-of-stock'),
	path('movements/', StockMovementListCreateView.as_view(), name='movement-list'),
	path('movements/recent/', InventoryRecentMovementsView.as_view(), name='movement-recent'),
	path('movements/<uuid:pk>/', StockMovementDetailView.as_view(), name='movement-detail'),
	path('summary/', InventorySummaryView.as_view(), name='inventory-summary'),
	path('valuation/', InventoryValuationView.as_view(), name='inventory-valuation'),
	path('imports/', InventoryImportUploadView.as_view(), name='inventory-import-upload'),
	path('imports/<uuid:import_id>/', InventoryImportDetailView.as_view(), name='inventory-import-detail'),
	path('imports/<uuid:import_id>/preview/', InventoryImportPreviewView.as_view(), name='inventory-import-preview'),
	path('imports/<uuid:import_id>/apply/', InventoryImportApplyView.as_view(), name='inventory-import-apply'),
	# Replenishments (compras)
	path('replenishments/', ReplenishmentListCreateView.as_view(), name='replenishment-list'),
	path('replenishments/<uuid:pk>/', ReplenishmentDetailView.as_view(), name='replenishment-detail'),
	path('replenishments/<uuid:pk>/void/', ReplenishmentVoidView.as_view(), name='replenishment-void'),
]
