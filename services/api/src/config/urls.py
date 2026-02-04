from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.menu.views import MenuQRCodeView, PublicMenuBySlugView
from apps.resto.views import RestaurantTablesMapStateView, RestaurantTablesSnapshotView
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
  path('api/v1/menu/', include('apps.menu.urls')),
  path('api/v1/public/menu/<slug:slug>/', PublicMenuBySlugView.as_view(), name='public-menu'),
  path('api/v1/menu-qr/<int:business_id>/', MenuQRCodeView.as_view(), name='menu-qr'),
  path('api/v1/resto/', include('apps.resto.urls')),
  path('api/v1/billing/', include('apps.billing.urls')),
  path('api/v1/restaurant/tables/', RestaurantTablesSnapshotView.as_view(), name='restaurant-tables'),
  path('api/v1/restaurant/tables/map-state/', RestaurantTablesMapStateView.as_view(), name='restaurant-tables-map'),
  path('api/v1/restaurant/reports/', include('apps.resto.reports.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
