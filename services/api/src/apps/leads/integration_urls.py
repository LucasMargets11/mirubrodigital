"""Rutas máquina-a-máquina del agente (montadas en /api/v1/integrations/agent/).

Separadas de la API humana del CRM (/api/v1/leads/, `urls.py`).
"""
from django.urls import path, re_path

from .ai_telemetry_views import AgentAIExecutionView
from .views import AgentAppointmentContextView, AgentLeadSyncView, AgentReceptionistConfigView

urlpatterns = [
    # PROD-02E4A: telemetría operativa de IA (no autoriza ejecuciones).
    path('ai-executions/', AgentAIExecutionView.as_view(), name='agent-ai-executions'),
    path(
        'leads/<uuid:external_lead_id>/appointment-context/',
        AgentAppointmentContextView.as_view(), name='agent-appointment-context',
    ),
    path('leads/<uuid:external_lead_id>/', AgentLeadSyncView.as_view(), name='agent-lead-sync'),
    # PROD-03C: configuración de Recepcionista IA (solo lectura, HMAC).
    re_path(
        r'^businesses/(?P<business_id>[0-9]{1,18})/channels/(?P<phone_number_id>[0-9]{1,32})/receptionist-config/$',
        AgentReceptionistConfigView.as_view(), name='agent-receptionist-config',
    ),
]
