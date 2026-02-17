from django.urls import path

from .views import (
	SaleCancelView,
	SaleDetailView,
	SaleListCreateView,
	SalesRecentView,
	SalesTodaySummaryView,
	SalesTopProductsView,
)
from .quote_views import (
	QuoteListCreateView,
	QuoteDetailView,
	QuoteMarkSentView,
	QuoteMarkAcceptedView,
	QuoteMarkRejectedView,
	QuotePDFView,
)

app_name = 'sales'

urlpatterns = [
	path('', SaleListCreateView.as_view(), name='sale-list'),
	path('summary/today/', SalesTodaySummaryView.as_view(), name='sales-summary-today'),
	path('recent/', SalesRecentView.as_view(), name='sales-recent'),
	path('top-products/', SalesTopProductsView.as_view(), name='sales-top-products'),
	path('<uuid:pk>/', SaleDetailView.as_view(), name='sale-detail'),
	path('<uuid:pk>/cancel/', SaleCancelView.as_view(), name='sale-cancel'),
	
	# Quotes (Presupuestos)
	path('quotes/', QuoteListCreateView.as_view(), name='quote-list'),
	path('quotes/<uuid:pk>/', QuoteDetailView.as_view(), name='quote-detail'),
	path('quotes/<uuid:pk>/mark-sent/', QuoteMarkSentView.as_view(), name='quote-mark-sent'),
	path('quotes/<uuid:pk>/mark-accepted/', QuoteMarkAcceptedView.as_view(), name='quote-mark-accepted'),
	path('quotes/<uuid:pk>/mark-rejected/', QuoteMarkRejectedView.as_view(), name='quote-mark-rejected'),
	path('quotes/<uuid:pk>/pdf/', QuotePDFView.as_view(), name='quote-pdf'),
]
