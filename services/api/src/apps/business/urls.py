from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
	CommercialSettingsView, 
	ServiceHubView, 
	BranchViewSet,
	BusinessBillingProfileView,
	BusinessBrandingView,
)

app_name = 'business'

router = DefaultRouter()
router.register('branches', BranchViewSet, basename='branches')

urlpatterns = [
	path('services/', ServiceHubView.as_view(), name='services'),
	path('commercial/settings/', CommercialSettingsView.as_view(), name='commercial-settings'),
	path('settings/billing/', BusinessBillingProfileView.as_view(), name='billing-profile'),
	path('settings/branding/', BusinessBrandingView.as_view(), name='branding'),
	path('', include(router.urls)),
]
