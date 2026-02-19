from django.urls import path

from .views import LoginView, LogoutView, MeView, RefreshView, RegisterView, SwitchBusinessView

urlpatterns = [
	path('login/', LoginView.as_view(), name='auth-login'),
	path('register/', RegisterView.as_view(), name='auth-register'),
	path('logout/', LogoutView.as_view(), name='auth-logout'),
	path('refresh/', RefreshView.as_view(), name='auth-refresh'),
	path('me/', MeView.as_view(), name='auth-me'),
	path('switch-business/', SwitchBusinessView.as_view(), name='auth-switch-business'),
]
