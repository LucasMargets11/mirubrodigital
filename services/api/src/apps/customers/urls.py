from django.urls import path

from .views import CustomerDetailView, CustomerListCreateView, CustomerQuotesView, CustomerSalesView

app_name = 'customers'

urlpatterns = [
  path('', CustomerListCreateView.as_view(), name='customer-list'),
  path('<uuid:pk>/', CustomerDetailView.as_view(), name='customer-detail'),
  path('<uuid:pk>/sales/', CustomerSalesView.as_view(), name='customer-sales'),
  path('<uuid:pk>/quotes/', CustomerQuotesView.as_view(), name='customer-quotes'),
]
