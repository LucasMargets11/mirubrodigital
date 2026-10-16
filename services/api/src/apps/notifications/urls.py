from django.urls import path

from .views import BusinessNotificationListView, BusinessNotificationReadView

app_name = 'notifications'

urlpatterns = [
    path('business/', BusinessNotificationListView.as_view(), name='business-list'),
    path('business/<uuid:pk>/read/', BusinessNotificationReadView.as_view(), name='business-read'),
]
