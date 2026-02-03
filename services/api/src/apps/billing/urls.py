from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import BillingViewSet, StartSubscriptionView, IntentStatusView, MercadoPagoWebhookView

router = DefaultRouter()
router.register(r'', BillingViewSet, basename='billing')

urlpatterns = [
    path('start-subscription', StartSubscriptionView.as_view(), name='start-subscription'),
    path('intent-status', IntentStatusView.as_view(), name='intent-status'),
    path('mercadopago/webhook', MercadoPagoWebhookView.as_view(), name='mp-webhook'),
] + router.urls

