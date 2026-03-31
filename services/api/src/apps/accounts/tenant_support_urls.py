from django.urls import path

from .tenant_support_views import (
    TenantTicketListCreateView,
    TenantTicketDetailView,
    TenantTicketReplyView,
    TenantTicketCloseReopenView,
)

urlpatterns = [
    path('tickets/', TenantTicketListCreateView.as_view(), name='tenant-tickets'),
    path('tickets/<str:ticket_id>/', TenantTicketDetailView.as_view(), name='tenant-ticket-detail'),
    path('tickets/<str:ticket_id>/reply/', TenantTicketReplyView.as_view(), name='tenant-ticket-reply'),
    path('tickets/<str:ticket_id>/close/', TenantTicketCloseReopenView.as_view(), name='tenant-ticket-close'),
]
