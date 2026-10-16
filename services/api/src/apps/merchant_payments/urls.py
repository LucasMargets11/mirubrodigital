from django.urls import path

from .views import (
    MercadoPagoConnectionStatusView,
    MercadoPagoDisconnectView,
    MercadoPagoOAuthCallbackView,
    MercadoPagoOAuthStartView,
)

app_name = 'merchant_payments'

# Mounted at 'api/v1/menu/mercadopago/' in config.urls to preserve the
# existing public URL contract (frontend + already-registered MP redirect
# URI) unchanged across the Slice 5A extraction.
urlpatterns = [
    path('connect/start/', MercadoPagoOAuthStartView.as_view(), name='mp-oauth-start'),
    path('connect/callback/', MercadoPagoOAuthCallbackView.as_view(), name='mp-oauth-callback'),
    path('connect/status/', MercadoPagoConnectionStatusView.as_view(), name='mp-oauth-status'),
    path('connect/', MercadoPagoDisconnectView.as_view(), name='mp-oauth-disconnect'),
]
