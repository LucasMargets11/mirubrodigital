from django.urls import path

from .views import (
    GoogleAuthView,
    GooglePreauthorizedLoginView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    SwitchBusinessView,
    VerifyEmailView,
    ResendVerificationView,
    ForgotPasswordView,
    ResetPasswordView,
    ChangePasswordView,
    ForceChangePasswordView,
)
from .onboarding_views import (
    OnboardingStatusView,
    OnboardingSetServiceView,
    OnboardingStartCheckoutView,
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('refresh/', RefreshView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('switch-business/', SwitchBusinessView.as_view(), name='auth-switch-business'),
    # Email verification
    path('verify-email/', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('resend-verification/', ResendVerificationView.as_view(), name='auth-resend-verification'),
    # Google OAuth
    path('google/', GoogleAuthView.as_view(), name='auth-google'),
    # ADMIN-CLIENTES 04C: preauthorized owner login (no autocreation)
    path('google/preauthorized/', GooglePreauthorizedLoginView.as_view(), name='auth-google-preauthorized'),
    # Self-service password recovery
    path('forgot-password/', ForgotPasswordView.as_view(), name='auth-forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='auth-reset-password'),
    # Authenticated password change (personal accounts)
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('force-change-password/', ForceChangePasswordView.as_view(), name='auth-force-change-password'),
    # Wave 3: Authenticated onboarding funnel
    # Gated by rollout.NEW_ONBOARDING on the frontend; backend always accepts
    # requests so unauthenticated-path users aren't broken if flag is off.
    path('onboarding/', OnboardingStatusView.as_view(), name='auth-onboarding-status'),
    path('onboarding/set-service/', OnboardingSetServiceView.as_view(), name='auth-onboarding-set-service'),
    # Wave 4: Checkout initiation from onboarding funnel
    path('onboarding/start-checkout/', OnboardingStartCheckoutView.as_view(), name='auth-onboarding-start-checkout'),
]

