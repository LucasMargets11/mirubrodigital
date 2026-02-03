from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CommercialSettingsView, ServiceHubView, BranchViewSet

app_name = 'business'

router = DefaultRouter()
router.register('branches', BranchViewSet, basename='branches')

urlpatterns = [
	path('services/', ServiceHubView.as_view(), name='services'),
	path('commercial/settings/', CommercialSettingsView.as_view(), name='commercial-settings'),
	path('', include(router.urls)),
]
