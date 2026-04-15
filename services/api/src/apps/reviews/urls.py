from django.urls import path

from . import views

app_name = 'reviews'

urlpatterns = [
    # Private (authenticated)
    path('config/', views.ReviewConfigView.as_view(), name='config'),
    path('qr/', views.ReviewQRCodeView.as_view(), name='qr'),
    path('stats/', views.ReviewStatsView.as_view(), name='stats'),
    path('trial/activate/', views.ActivateTrialView.as_view(), name='trial-activate'),
    path('', views.ReviewListView.as_view(), name='list'),
    path('<uuid:id>/', views.ReviewDetailView.as_view(), name='detail'),

    # Public (unauthenticated)
    path('public/<slug:slug>/', views.PublicReviewLandingView.as_view(), name='public-landing'),
    path('public/<slug:slug>/submit/', views.PublicReviewSubmitView.as_view(), name='public-submit'),
]
