"""Identidad y vínculo compartidos por el alta manual y la conversión de propuestas."""
from rest_framework.exceptions import ValidationError

from apps.appointments.models import Appointment

from ..models import Lead, LeadAgentState
from .activity import record_update_activity, snapshot_for_activity


def appointment_data_for_lead(lead: Lead, data: dict) -> dict:
    data = data.copy()
    customer = lead.customer
    if customer is not None:
        if customer.business_id != lead.business_id:
            raise ValidationError({'customer_id': ['El cliente no pertenece a este negocio.']})
        if 'customer_id' in data and str(data['customer_id']) != str(customer.pk):
            raise ValidationError({'customer_id': ['Usá el cliente vinculado al lead.']})
        data['customer_id'] = str(customer.pk)
    try:
        agent = lead.agent_state
    except LeadAgentState.DoesNotExist:
        agent = None
    defaults = {
        'customer_name': (
            (agent.patient_name or agent.whatsapp_profile_name) if agent else ''
        ) or (customer.name if customer else ''),
        'customer_phone': (agent.phone_e164 if agent else '') or (customer.phone if customer else '') or '',
        'customer_email': (customer.email if customer else '') or '',
    }
    for field, value in defaults.items():
        data.setdefault(field, value)
    return data


def link_lead_appointment(lead: Lead, appointment: Appointment, *, user) -> None:
    """El caller mantiene el lock del Lead hasta el commit."""
    previous = snapshot_for_activity(lead)
    lead.appointment = appointment
    if lead.customer_id is None and appointment.customer_id is not None:
        lead.customer = appointment.customer
    lead.save(update_fields=['appointment', 'customer', 'updated_at'])
    record_update_activity(lead, previous, actor=user)
