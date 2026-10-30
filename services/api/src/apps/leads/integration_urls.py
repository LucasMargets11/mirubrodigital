"""Rutas máquina-a-máquina del agente (montadas en /api/v1/integrations/agent/).

Separadas de la API humana del CRM (/api/v1/leads/, `urls.py`).
"""
from django.urls import path

from .views import AgentAppointmentContextView, AgentLeadSyncView

urlpatterns = [
    path(
        'leads/<uuid:external_lead_id>/appointment-context/',
        AgentAppointmentContextView.as_view(), name='agent-appointment-context',
    ),
    path('leads/<uuid:external_lead_id>/', AgentLeadSyncView.as_view(), name='agent-lead-sync'),
]
