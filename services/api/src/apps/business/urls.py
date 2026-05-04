from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
	CommercialSettingsView, 
	ServiceHubView, 
	BranchViewSet,
	BusinessBillingProfileView,
	BusinessBrandingView,
	BusinessLogoUploadView,
	BusinessEntitlementsView,
	AvailableAddonsView,
)
from .onboarding_views import (
	GestionOnboardingContextView,
	GestionOnboardingBusinessBasicsView,
	GestionOnboardingFirstProductView,
	GestionOnboardingSalesSetupView,
	GestionOnboardingSkipStepView,
	GestionOnboardingCompleteView,
	GestionOnboardingDismissView,
)
from .setup_views import GestionSetupContextView

app_name = 'business'

router = DefaultRouter()
router.register('branches', BranchViewSet, basename='branches')

urlpatterns = [
	path('services/', ServiceHubView.as_view(), name='services'),
	path('commercial/settings/', CommercialSettingsView.as_view(), name='commercial-settings'),
	path('settings/billing/', BusinessBillingProfileView.as_view(), name='billing-profile'),
	path('settings/branding/', BusinessBrandingView.as_view(), name='branding'),
	path('settings/branding/upload-logo/', BusinessLogoUploadView.as_view(), name='branding-upload-logo'),
	path('entitlements/', BusinessEntitlementsView.as_view(), name='entitlements'),
	path('addons/available/', AvailableAddonsView.as_view(), name='available-addons'),
	# ── Gestión Comercial setup center (Phase 1 – read-only progress) ─────
	path('setup/gestion/context', GestionSetupContextView.as_view(), name='setup-gestion-context'),
	# ── Gestión Comercial onboarding wizard (MVP v1) ───────────────────────
	path('onboarding/gestion/context', GestionOnboardingContextView.as_view(), name='onboarding-gestion-context'),
	path('onboarding/gestion/business-basics', GestionOnboardingBusinessBasicsView.as_view(), name='onboarding-gestion-business-basics'),
	path('onboarding/gestion/first-product', GestionOnboardingFirstProductView.as_view(), name='onboarding-gestion-first-product'),
	path('onboarding/gestion/sales-setup', GestionOnboardingSalesSetupView.as_view(), name='onboarding-gestion-sales-setup'),
	path('onboarding/gestion/skip-step', GestionOnboardingSkipStepView.as_view(), name='onboarding-gestion-skip-step'),
	path('onboarding/gestion/complete', GestionOnboardingCompleteView.as_view(), name='onboarding-gestion-complete'),
	path('onboarding/gestion/dismiss', GestionOnboardingDismissView.as_view(), name='onboarding-gestion-dismiss'),
	path('', include(router.urls)),
]
