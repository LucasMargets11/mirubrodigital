from django.urls import path

from .views import (
	CashClosureDetailView,
	CashClosureListView,
	PaymentsReportView,
	ReportProductsView,
	ReportSalesDetailView,
	ReportSalesListView,
	ReportSummaryView,
	StockAlertsReportView,
	TopProductsReportView,
)

app_name = 'reports'

urlpatterns = [
	path('summary/', ReportSummaryView.as_view(), name='summary'),
	path('sales/', ReportSalesListView.as_view(), name='sales-list'),
	path('sales/<uuid:pk>/', ReportSalesDetailView.as_view(), name='sales-detail'),
	path('payments/', PaymentsReportView.as_view(), name='payments'),
	path('products/', ReportProductsView.as_view(), name='products'),
	path('products/top/', TopProductsReportView.as_view(), name='products-top'),
	path('stock/alerts/', StockAlertsReportView.as_view(), name='stock-alerts'),
	path('cash/closures/', CashClosureListView.as_view(), name='cash-closures'),
	path('cash/closures/<uuid:pk>/', CashClosureDetailView.as_view(), name='cash-closure-detail'),
]
