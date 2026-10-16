from django.urls import path

from .public_views import (
  PublicAppointmentAvailabilityView,
  PublicAppointmentBookingCreateView,
  PublicAppointmentBookingStatusView,
  PublicAppointmentCheckoutView,
  PublicAppointmentBusinessView,
  PublicAppointmentProfessionalsView,
)
from .views import (
  AppointmentAvailabilityView,
  AppointmentCategoryDetailView,
  AppointmentCategoryListCreateView,
  AppointmentDetailView,
  AppointmentExceptionDetailView,
  AppointmentExceptionListCreateView,
  AppointmentListCreateView,
  AppointmentProfessionalDetailView,
  AppointmentProfessionalListCreateView,
  AppointmentScheduleDetailView,
  AppointmentScheduleListCreateView,
  AppointmentServiceDetailView,
  AppointmentServiceListCreateView,
  CommunicationAutomationSettingsView,
  CustomerCommunicationSettingsView,
  ReminderAutomationSettingsView,
)

app_name = 'appointments'

urlpatterns = [
  path('categories/', AppointmentCategoryListCreateView.as_view(), name='category-list'),
  path('categories/<uuid:pk>/', AppointmentCategoryDetailView.as_view(), name='category-detail'),
  path('services/', AppointmentServiceListCreateView.as_view(), name='service-list'),
  path('services/<uuid:pk>/', AppointmentServiceDetailView.as_view(), name='service-detail'),
  path('professionals/', AppointmentProfessionalListCreateView.as_view(), name='professional-list'),
  path('professionals/<uuid:pk>/', AppointmentProfessionalDetailView.as_view(), name='professional-detail'),
  path('schedules/', AppointmentScheduleListCreateView.as_view(), name='schedule-list'),
  path('schedules/<uuid:pk>/', AppointmentScheduleDetailView.as_view(), name='schedule-detail'),
  path('exceptions/', AppointmentExceptionListCreateView.as_view(), name='exception-list'),
  path('exceptions/<uuid:pk>/', AppointmentExceptionDetailView.as_view(), name='exception-detail'),
  path('appointments/', AppointmentListCreateView.as_view(), name='appointment-list'),
  path('appointments/<uuid:pk>/', AppointmentDetailView.as_view(), name='appointment-detail'),
  path('availability/', AppointmentAvailabilityView.as_view(), name='availability'),
  path('reminder-automation/', ReminderAutomationSettingsView.as_view(), name='reminder-automation'),
  path('communication-settings/', CustomerCommunicationSettingsView.as_view(), name='communication-settings'),
  path(
    'communication-automation-settings/',
    CommunicationAutomationSettingsView.as_view(),
    name='communication-automation-settings',
  ),
  # Público (Slice 4A) — sin autenticación, resuelto únicamente por slug.
  path('public/<slug:slug>/', PublicAppointmentBusinessView.as_view(), name='public-business'),
  path('public/<slug:slug>/professionals/', PublicAppointmentProfessionalsView.as_view(), name='public-professionals'),
  path('public/<slug:slug>/availability/', PublicAppointmentAvailabilityView.as_view(), name='public-availability'),
  path('public/<slug:slug>/bookings/', PublicAppointmentBookingCreateView.as_view(), name='public-booking-create'),
  path(
    'public/<slug:slug>/bookings/<uuid:public_token>/',
    PublicAppointmentBookingStatusView.as_view(),
    name='public-booking-status',
  ),
  path(
    'public/<slug:slug>/bookings/<uuid:public_token>/checkout/',
    PublicAppointmentCheckoutView.as_view(),
    name='public-booking-checkout',
  ),
]
