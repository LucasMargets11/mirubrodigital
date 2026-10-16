from django.urls import path

from .views import CustomerAppointmentsView, CustomerContactPreferencesView, CustomerDeliveriesView, CustomerDetailView, CustomerListCreateView, CustomerNoteDetailView, CustomerNotesView, CustomerReminderDetailView, CustomerRemindersView, CustomerQuotesView, CustomerSalesView, CustomerTimelineView

app_name = 'customers'

urlpatterns = [
  path('', CustomerListCreateView.as_view(), name='customer-list'),
  path('<uuid:pk>/', CustomerDetailView.as_view(), name='customer-detail'),
  path('<uuid:pk>/sales/', CustomerSalesView.as_view(), name='customer-sales'),
  path('<uuid:pk>/quotes/', CustomerQuotesView.as_view(), name='customer-quotes'),
  path('<uuid:pk>/appointments/', CustomerAppointmentsView.as_view(), name='customer-appointments'),
  path('<uuid:pk>/timeline/', CustomerTimelineView.as_view(), name='customer-timeline'),
  path('<uuid:pk>/notes/', CustomerNotesView.as_view(), name='customer-notes'),
  path('<uuid:pk>/notes/<uuid:note_id>/', CustomerNoteDetailView.as_view(), name='customer-note-detail'),
  path('<uuid:pk>/reminders/', CustomerRemindersView.as_view(), name='customer-reminders'),
  path('<uuid:pk>/contact-preferences/', CustomerContactPreferencesView.as_view(), name='customer-contact-preferences'),
  path('<uuid:pk>/deliveries/', CustomerDeliveriesView.as_view(), name='customer-deliveries'),
  path('<uuid:pk>/reminders/<uuid:reminder_id>/', CustomerReminderDetailView.as_view(), name='customer-reminder-detail'),
]
