from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    BillingViewSet,
    StartSubscriptionView,
    IntentStatusView,
    MercadoPagoWebhookView,
    DevMercadoPagoPingView,
    CheckoutSessionStatusView,
    CheckoutSessionReconcileView,
    AppointmentsQuoteView,
    AppointmentsCheckoutView,
    ValidatePromoCodeView,
)
from .commercial_views import (
    CommercialSubscriptionView,
    CommercialPreviewChangeView,
    CommercialCheckoutView,
    AddonCheckoutView,
)
from .cancellation_views import (
    SubscriptionStatusView,
    CancelSubscriptionView,
    UndoCancelSubscriptionView,
)
from .reviews_views import ReviewsUpgradeView, ReviewsDowngradeView
from .appointments_lifecycle_views import (
    AppointmentsLifecycleChangeView,
    AppointmentsLifecycleQuoteView,
    AppointmentsLifecycleResolveView,
)

router = DefaultRouter()
router.register(r'', BillingViewSet, basename='billing')

urlpatterns = [
    path('start-subscription', StartSubscriptionView.as_view(), name='start-subscription'),
    path('intent-status', IntentStatusView.as_view(), name='intent-status'),
    path('mercadopago/webhook', MercadoPagoWebhookView.as_view(), name='mp-webhook'),
    # Phase 3: checkout session status polling endpoint
    path('checkout-sessions/<uuid:session_id>', CheckoutSessionStatusView.as_view(), name='checkout-session-status'),
    # Phase 5: proactive reconciliation — called when user returns from MercadoPago
    path('checkout-sessions/<uuid:session_id>/reconcile/', CheckoutSessionReconcileView.as_view(), name='checkout-session-reconcile'),
    path('internal/appointments/quote/', AppointmentsQuoteView.as_view(), name='appointments-quote-internal'),
    path('internal/appointments/checkout/', AppointmentsCheckoutView.as_view(), name='appointments-checkout-internal'),
    path('appointments/lifecycle/quote/', AppointmentsLifecycleQuoteView.as_view(), name='appointments-lifecycle-quote'),
    path('appointments/lifecycle/change/', AppointmentsLifecycleChangeView.as_view(), name='appointments-lifecycle-change'),
    path('appointments/lifecycle/changes/<uuid:pending_change_id>/resolve/', AppointmentsLifecycleResolveView.as_view(), name='appointments-lifecycle-resolve'),
    # DEV diagnostics — two paths for convenience
    path('dev/mercadopago/ping', DevMercadoPagoPingView.as_view(), name='mp-dev-ping'),
    path('dev/mp/status', DevMercadoPagoPingView.as_view(), name='mp-dev-status'),
    path('commercial/subscription/', CommercialSubscriptionView.as_view(), name='commercial-subscription'),
    path('commercial/preview-change/', CommercialPreviewChangeView.as_view(), name='commercial-preview-change'),
    path('commercial/checkout/', CommercialCheckoutView.as_view(), name='commercial-checkout'),
    path('commercial/addon-checkout/', AddonCheckoutView.as_view(), name='addon-checkout'),
    path('subscription-status/', SubscriptionStatusView.as_view(), name='subscription-status'),
    path('cancel-subscription/', CancelSubscriptionView.as_view(), name='cancel-subscription'),
    path('undo-cancel/', UndoCancelSubscriptionView.as_view(), name='undo-cancel'),
    path('reviews/upgrade/', ReviewsUpgradeView.as_view(), name='reviews-upgrade'),
    path('reviews/downgrade/', ReviewsDowngradeView.as_view(), name='reviews-downgrade'),
    path('promo-codes/validate/', ValidatePromoCodeView.as_view(), name='promo-code-validate'),
] + router.urls
