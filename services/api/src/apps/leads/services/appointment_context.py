"""Contexto de turnos para el agente, independiente del historial de texto."""
from __future__ import annotations

from .. import errors
from ..models import AgentInstance, AppointmentProposal, Lead, LeadAgentState
from ..serializers import AppointmentContextSerializer, ProposalContextSerializer
from .appointment_proposals import current_proposal
from .receiver import resolve_channel


def appointment_context(lead: Lead) -> dict:
    proposal = current_proposal(lead)
    appointment = lead.appointment
    if appointment is not None and appointment.business_id != lead.business_id:
        raise errors.business_mismatch()
    return {
        'proposal': (
            ProposalContextSerializer(proposal).data
            if proposal is not None and proposal.status == AppointmentProposal.Status.QUEUED else None
        ),
        'appointment': AppointmentContextSerializer(appointment).data if appointment is not None else None,
    }


def agent_appointment_context(*, agent_instance: AgentInstance, external_lead_id) -> dict:
    state = (
        LeadAgentState.objects.select_related('lead__appointment', 'channel')
        .filter(agent_instance=agent_instance, external_lead_id=external_lead_id)
        .first()
    )
    if state is None:
        raise errors.AgentApiError(404, 'lead_not_found', 'Lead no encontrado.')
    channel = resolve_channel(agent_instance, {
        'phone_number_id': state.channel.phone_number_id,
        'business_id': state.lead.business_id,
    })
    if channel.pk != state.channel_id:
        raise errors.channel_disabled()
    return {
        'ok': True,
        'external_lead_id': str(state.external_lead_id),
        **appointment_context(state.lead),
    }
