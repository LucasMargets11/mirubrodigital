from django.urls import path

from .views import ServiceHubView

app_name = 'business'

urlpatterns = [
	path('services/', ServiceHubView.as_view(), name='services'),
]
