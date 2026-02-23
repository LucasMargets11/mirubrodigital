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
	path('', include(router.urls)),
]
