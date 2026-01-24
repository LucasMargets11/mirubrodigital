from django.urls import path

from .views import CommercialSettingsView, ServiceHubView

app_name = 'business'

urlpatterns = [
	path('services/', ServiceHubView.as_view(), name='services'),
	path('commercial/settings/', CommercialSettingsView.as_view(), name='commercial-settings'),
]
