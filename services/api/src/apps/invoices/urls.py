from django.urls import path

from .views import (
  InvoiceDetailView,
  InvoiceIssueView,
  InvoiceListView,
  InvoicePDFView,
  InvoiceSeriesListView,
  DocumentSeriesListCreateView,
  DocumentSeriesDetailView,
  DocumentSeriesSetDefaultView,
)

app_name = 'invoices'

urlpatterns = [
  path('', InvoiceListView.as_view(), name='invoice-list'),
  path('series/', InvoiceSeriesListView.as_view(), name='invoice-series'),
  path('issue/', InvoiceIssueView.as_view(), name='invoice-issue'),
  path('<uuid:pk>/', InvoiceDetailView.as_view(), name='invoice-detail'),
  path('<uuid:pk>/pdf/', InvoicePDFView.as_view(), name='invoice-pdf'),
  # Document series (nuevo sistema unificado)
  path('document-series/', DocumentSeriesListCreateView.as_view(), name='document-series-list'),
  path('document-series/<uuid:pk>/', DocumentSeriesDetailView.as_view(), name='document-series-detail'),
  path('document-series/<uuid:pk>/set-default/', DocumentSeriesSetDefaultView.as_view(), name='document-series-set-default'),
]
