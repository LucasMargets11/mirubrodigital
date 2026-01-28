from django.urls import path

from .views import (
    RestaurantReportCashSessionsView,
    RestaurantReportProductsView,
    RestaurantReportSummaryView,
)

app_name = 'restaurant-reports'

urlpatterns = [
    path('summary/', RestaurantReportSummaryView.as_view(), name='summary'),
    path('products/', RestaurantReportProductsView.as_view(), name='products'),
    path('cash-sessions/', RestaurantReportCashSessionsView.as_view(), name='cash-sessions'),
]
