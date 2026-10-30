"""API humana de Leads (LEADS 04A), montada en `/api/v1/leads/`."""
from django.urls import path

from .crm_views import (
    LeadAcknowledgeAttentionView, LeadAppointmentProposalsView, LeadAssigneesView, LeadCurrentAppointmentProposalView,
    LeadDetailView, LeadListView, LeadMessagesView, LeadNoteDetailView, LeadNotesView, LeadReleaseView,
    LeadTakeoverView, LeadCreateAppointmentView, LeadConfirmAppointmentProposalView,
)

app_name = 'leads'

urlpatterns = [
    path('', LeadListView.as_view(), name='lead-list'),
    path('assignees/', LeadAssigneesView.as_view(), name='lead-assignees'),
    path('<uuid:lead_id>/', LeadDetailView.as_view(), name='lead-detail'),
    path('<uuid:lead_id>/appointment/', LeadCreateAppointmentView.as_view(), name='lead-create-appointment'),
    path(
        '<uuid:lead_id>/appointment-proposals/', LeadAppointmentProposalsView.as_view(),
        name='lead-appointment-proposals',
    ),
    path(
        '<uuid:lead_id>/appointment-proposals/<uuid:proposal_id>/confirm/',
        LeadConfirmAppointmentProposalView.as_view(), name='lead-appointment-proposal-confirm',
    ),
    path(
        '<uuid:lead_id>/appointment-proposals/current/', LeadCurrentAppointmentProposalView.as_view(),
        name='lead-appointment-proposal-current',
    ),
    path(
        '<uuid:lead_id>/acknowledge-attention/', LeadAcknowledgeAttentionView.as_view(),
        name='lead-acknowledge-attention',
    ),
    path('<uuid:lead_id>/takeover/', LeadTakeoverView.as_view(), name='lead-takeover'),
    path('<uuid:lead_id>/release/', LeadReleaseView.as_view(), name='lead-release'),
    path('<uuid:lead_id>/messages/', LeadMessagesView.as_view(), name='lead-messages'),
    path('<uuid:lead_id>/notes/', LeadNotesView.as_view(), name='lead-notes'),
    path('<uuid:lead_id>/notes/<uuid:note_id>/', LeadNoteDetailView.as_view(), name='lead-note-detail'),
]
