from django.urls import path

from .views import LoginView, LogoutView, MeView, RefreshView, SwitchBusinessView

urlpatterns = [
	path('login/', LoginView.as_view(), name='auth-login'),
	path('logout/', LogoutView.as_view(), name='auth-logout'),
	path('refresh/', RefreshView.as_view(), name='auth-refresh'),
	path('me/', MeView.as_view(), name='auth-me'),
	path('switch-business/', SwitchBusinessView.as_view(), name='auth-switch-business'),
]
