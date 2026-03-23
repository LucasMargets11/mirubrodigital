from django.urls import path

from .platform_admin_views import (
    AdminMeView,
    AdminDashboardMetricsView,
)
from .platform_auth_views import (
    AdminLoginView,
    AdminMFAVerifyView,
    AdminMFARecoveryView,
    AdminMFAEnrollView,
    AdminMFAConfirmView,
    AdminMFADisableView,
    AdminLogoutView,
)

urlpatterns = [
    # ── Auth (Phase 1.1 hardening) ───────────────────────────────────────
    path('auth/login/', AdminLoginView.as_view(), name='platform-admin-login'),
    path('auth/mfa-verify/', AdminMFAVerifyView.as_view(), name='platform-admin-mfa-verify'),
    path('auth/mfa-recovery/', AdminMFARecoveryView.as_view(), name='platform-admin-mfa-recovery'),
    path('auth/mfa-enroll/', AdminMFAEnrollView.as_view(), name='platform-admin-mfa-enroll'),
    path('auth/mfa-confirm/', AdminMFAConfirmView.as_view(), name='platform-admin-mfa-confirm'),
    path('auth/mfa-disable/', AdminMFADisableView.as_view(), name='platform-admin-mfa-disable'),
    path('auth/logout/', AdminLogoutView.as_view(), name='platform-admin-logout'),
    # ── Data endpoints ───────────────────────────────────────────────────
    path('me/', AdminMeView.as_view(), name='platform-admin-me'),
    path('dashboard/metrics/', AdminDashboardMetricsView.as_view(), name='platform-admin-dashboard-metrics'),
]
