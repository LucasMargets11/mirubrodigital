from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.employee_views import EmployeeLoginView, EmployeeChangePinView
from apps.menu.views import MenuQRCodeView, PublicMenuBySlugView
from apps.resto.views import RestaurantTablesMapStateView, RestaurantTablesSnapshotView
from common.health import health_check

urlpatterns = [
  path('django-admin/', admin.site.urls),
  path('api/v1/health/', health_check, name='health-check'),
  path('api/v1/auth/', include('apps.accounts.urls')),
  path('api/v1/platform-admin/', include('apps.accounts.platform_admin_urls')),
  path('api/v1/auth/employee-login/', EmployeeLoginView.as_view(), name='employee-login'),
  path('api/v1/auth/employee-change-pin/', EmployeeChangePinView.as_view(), name='employee-change-pin'),
  path('api/v1/pos/', include('apps.accounts.pos_urls')),
  path('api/v1/owner/access/', include('apps.accounts.owner_urls')),
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
  # Merchant-side Mercado Pago OAuth (Slice 5A extraction from apps.menu) — mounted
  # under the same 'menu/mercadopago/' prefix as before so existing frontend calls
  # and the registered MP redirect URI keep working unchanged.
  path('api/v1/menu/mercadopago/', include('apps.merchant_payments.urls')),
  path('api/v1/public/menu/<slug:slug>/', PublicMenuBySlugView.as_view(), name='public-menu'),
  path('api/v1/menu-qr/<int:business_id>/', MenuQRCodeView.as_view(), name='menu-qr'),
  path('api/v1/reviews/', include('apps.reviews.urls')),
  path('api/v1/appointments/', include('apps.appointments.urls')),
  path('api/v1/notifications/', include('apps.notifications.urls')),
  # AGENT 02B: ingesta máquina-a-máquina (HMAC).
  path('api/v1/integrations/agent/', include('apps.leads.integration_urls')),
  # LEADS 04A: API humana del CRM de Leads (sesión + RBAC view/manage_leads).
  path('api/v1/leads/', include('apps.leads.urls')),
  path('api/v1/resto/', include('apps.resto.urls')),
  path('api/v1/billing/', include('apps.billing.urls')),
  path('api/v1/treasury/', include('apps.treasury.urls')),
  path('api/v1/tax-backup/', include('apps.tax_backup.urls')),
  path('api/v1/blog/', include('apps.blog.urls')),
  path('api/v1/printables/', include('apps.printables.urls')),
  path('api/v1/support/', include('apps.accounts.tenant_support_urls')),
  path('api/v1/restaurant/tables/', RestaurantTablesSnapshotView.as_view(), name='restaurant-tables'),
  path('api/v1/restaurant/tables/map-state/', RestaurantTablesMapStateView.as_view(), name='restaurant-tables-map'),
  path('api/v1/restaurant/reports/', include('apps.resto.reports.urls')),
]

# ── Dev-only routes ──────────────────────────────────────────────────────────
# API schema & Swagger docs: available in DEBUG mode only.
# In production, use `manage.py spectacular --file schema.yml` to export.
if settings.DEBUG:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(api_version='v1'), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
    ]

# Serve uploaded media files via Django only in development.
# In production, media should be served by a reverse proxy, CDN, or S3.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
