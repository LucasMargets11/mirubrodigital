from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common.health import health_check

urlpatterns = [
  path('admin/', admin.site.urls),
  path('api/schema/', SpectacularAPIView.as_view(api_version='v1'), name='schema'),
  path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
  path('api/v1/health/', health_check, name='health-check'),
  path('api/v1/auth/', include('apps.accounts.urls')),
  path('api/v1/', include('apps.business.urls')),
  path('api/v1/catalog/', include('apps.catalog.urls')),
  path('api/v1/customers/', include('apps.customers.urls')),
  path('api/v1/inventory/', include('apps.inventory.urls')),
  path('api/v1/invoices/', include('apps.invoices.urls')),
  path('api/v1/orders/', include('apps.orders.urls')),
  path('api/v1/cash/', include('apps.cash.urls')),
  path('api/v1/sales/', include('apps.sales.urls')),
  path('api/v1/reports/', include('apps.reports.urls')),
]
