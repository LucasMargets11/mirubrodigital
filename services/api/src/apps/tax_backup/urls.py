from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    DuplicateFlagViewSet,
    ExpenseFiscalProfileViewSet,
)

router = DefaultRouter()
router.register(r'profiles', ExpenseFiscalProfileViewSet)
router.register(r'duplicates', DuplicateFlagViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
