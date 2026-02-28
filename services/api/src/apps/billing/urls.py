from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import BillingViewSet, StartSubscriptionView, IntentStatusView, MercadoPagoWebhookView, DevMercadoPagoPingView
from .commercial_views import (
    CommercialSubscriptionView, 
    CommercialPreviewChangeView, 
    CommercialCheckoutView,
    AddonCheckoutView,
)

router = DefaultRouter()
router.register(r'', BillingViewSet, basename='billing')

urlpatterns = [
    path('start-subscription', StartSubscriptionView.as_view(), name='start-subscription'),
    path('intent-status', IntentStatusView.as_view(), name='intent-status'),
    path('mercadopago/webhook', MercadoPagoWebhookView.as_view(), name='mp-webhook'),
    # DEV diagnostics — two paths for convenience
    path('dev/mercadopago/ping', DevMercadoPagoPingView.as_view(), name='mp-dev-ping'),
    path('dev/mp/status', DevMercadoPagoPingView.as_view(), name='mp-dev-status'),
    path('commercial/subscription/', CommercialSubscriptionView.as_view(), name='commercial-subscription'),
    path('commercial/preview-change/', CommercialPreviewChangeView.as_view(), name='commercial-preview-change'),
    path('commercial/checkout/', CommercialCheckoutView.as_view(), name='commercial-checkout'),
    path('commercial/addon-checkout/', AddonCheckoutView.as_view(), name='addon-checkout'),
] + router.urls

