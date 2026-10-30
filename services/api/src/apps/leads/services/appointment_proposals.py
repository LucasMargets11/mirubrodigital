"""SLICE 3A — propuesta estructurada de turno desde recepción a un Lead.

Recepción elige servicio/profesional/horario; el backend valida la
disponibilidad real (mismos helpers que la reserva manual: horarios,
excepciones, profesional, solapamientos), congela snapshots, arma el texto
de WhatsApp de forma determinística y lo encola en el outbox
`LeadStaffMessage`, todo en una sola transacción bajo el lock del Lead.

Nunca crea `Appointment`, `AppointmentPayment`, hold ni `pending_payment`:
la propuesta NO ocupa el slot hasta su conversión manual (Slice 3C.1).
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.appointments.models import Appointment, AppointmentProfessional, AppointmentService
from apps.appointments.serializers import AppointmentSerializer
from apps.appointments.services.availability import resolve_business_timezone
from apps.appointments.services.booking import (
    BookingError, ServiceSnapshot, compute_end_at, ensure_no_overlap, ensure_slot_available, lock_professionals,
)
from apps.appointments.services.deposit import compute_deposit_amount

from ..models import AppointmentProposal, Lead, LeadAgentState
from .human_messages import enqueue_staff_message
from .lead_appointments import appointment_data_for_lead, link_lead_appointment
from .takeover import TakeoverUnavailable, conversation_id_for, takeover_enabled

logger = logging.getLogger('apps.leads.appointment_proposals')

Status = AppointmentProposal.Status

# Campo del error de booking/availability → campo del payload de este endpoint.
_PAYLOAD_FIELDS = {'service': 'service_id', 'professional': 'professional_id', 'start_at': 'start_at'}


class ProposalConflict(Exception):
    """El estado actual impide crear la propuesta (HTTP 409)."""

    def __init__(self, code: str, detail: str):
        super().__init__(code)
        self.code = code
        self.detail = detail


class ProposalInvalid(Exception):
    """Dato del pedido inválido para este negocio/agenda (HTTP 400)."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True)
class ProposalResult:
    proposal: AppointmentProposal
    created: bool


def _is_expired(proposal: AppointmentProposal, now) -> bool:
    return proposal.status == Status.QUEUED and proposal.expires_at is not None and proposal.expires_at <= now


def current_proposal(lead: Lead, *, now=None) -> AppointmentProposal | None:
    """Propuesta activa del Lead (`pending_delivery` o `queued` vigente); vence lazy las `queued` pasadas."""
    now = now or timezone.now()
    if lead.appointment_id is not None:
        return None
    proposals = AppointmentProposal.objects.filter(business_id=lead.business_id, lead=lead)
    proposals.filter(status=Status.QUEUED, expires_at__lte=now).update(status=Status.EXPIRED, updated_at=now)
    return (
        proposals.filter(status__in=AppointmentProposal.ACTIVE_STATUSES)
        .select_related('service', 'professional', 'staff_message')
        .first()
    )


@transaction.atomic
def confirm_appointment_proposal(*, lead: Lead, proposal_id, user) -> Appointment:
    """Única conversión Proposal → Appointment; replay devuelve el turno original.

    Orden de locks compatible con crear/reemplazar/vincular desde Lead:
    Lead → Proposal → profesionales/Business del booking canónico.
    Ningún lock se libera entre validar disponibilidad y crear/vincular.
    """
    lead = (
        Lead.objects.select_for_update(of=('self',))
        .select_related('business', 'customer', 'agent_state')
        .get(pk=lead.pk, business_id=lead.business_id)
    )
    proposal = get_object_or_404(
        AppointmentProposal.objects.select_for_update(of=('self',)).select_related('appointment'),
        pk=proposal_id, business_id=lead.business_id, lead_id=lead.pk,
    )
    if proposal.appointment_id is not None:
        return proposal.appointment

    errors = {
        Status.EXPIRED: ('proposal_expired', 'La propuesta venció. Proponé otro horario.'),
        Status.SUPERSEDED: ('proposal_superseded', 'La propuesta fue reemplazada. Actualizá el detalle.'),
        Status.DELIVERY_FAILED: ('proposal_delivery_failed', 'No se pudo enviar esta propuesta. Proponé otro horario.'),
    }
    if proposal.status in errors:
        raise ProposalConflict(*errors[proposal.status])
    now = timezone.now()
    if proposal.expires_at is not None and proposal.expires_at <= now:
        raise ProposalConflict('proposal_expired', 'La propuesta venció. Proponé otro horario.')
    if lead.appointment_id is not None:
        raise ProposalConflict('lead_already_has_appointment', 'El lead ya tiene un turno vinculado.')
    if lead.status == Lead.Status.CLOSED or proposal.status not in AppointmentProposal.ACTIVE_STATUSES:
        raise ProposalConflict('proposal_not_confirmable', 'Esta propuesta no se puede confirmar.')
    if proposal.proposed_start_at <= now:
        raise ProposalConflict('slot_unavailable', 'El horario propuesto ya pasó.')

    snapshot = ServiceSnapshot(
        name=proposal.service_name, duration_minutes=proposal.service_duration_minutes, price=proposal.service_price,
        deposit_type=proposal.deposit_type, deposit_value=proposal.deposit_value, currency=proposal.currency,
    )
    # Appointment no tiene moneda propia ni depósito almacenado: se preservan
    # los inputs históricos de su propiedad deposit_amount, sin reinterpretarlos.
    if (
        proposal.proposed_end_at != proposal.proposed_start_at + dt.timedelta(minutes=snapshot.duration_minutes)
        or proposal.deposit_amount != compute_deposit_amount(
            price=snapshot.price, deposit_type=snapshot.deposit_type, deposit_value=snapshot.deposit_value,
        )
    ):
        raise ProposalConflict('proposal_not_confirmable', 'La oferta cambió o sus snapshots no son compatibles. Proponé otro horario.')

    try:
        data = appointment_data_for_lead(lead, {
            'service_id': str(proposal.service_id),
            'professional_id': str(proposal.professional_id) if proposal.professional_id else None,
            'start_at': proposal.proposed_start_at,
        })
        serializer = AppointmentSerializer(data=data, context={'business': lead.business})
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save(business=lead.business, service_snapshot=snapshot)
    except ValidationError as exc:
        # El serializer conserva la causa de booking para distinguir slot
        # ocupado de identidad/servicio/profesional inválidos.
        cause = exc.__cause__
        if isinstance(cause, BookingError):
            code = 'slot_unavailable' if cause.field == 'start_at' else 'proposal_not_confirmable'
            raise ProposalConflict(code, cause.message) from exc
        raise ProposalConflict(
            'proposal_not_confirmable', 'No se puede confirmar la propuesta. Revisá los datos del paciente, servicio y profesional.',
        ) from exc

    link_lead_appointment(lead, appointment, user=user)
    proposal.appointment = appointment
    proposal.status = Status.CONVERTED
    proposal.save(update_fields=['appointment', 'status', 'updated_at'])
    logger.info('appointment_proposal_converted proposal=%s lead=%s appointment=%s', proposal.pk, lead.pk, appointment.pk)
    return appointment


def create_and_send_appointment_proposal(
    *, lead: Lead, service_id, professional_id, start_at: dt.datetime, idempotency_key, user,
) -> ProposalResult:
    """Crea la propuesta + su `LeadStaffMessage` (atómico) o devuelve el replay idempotente.

    Enviar una propuesta es una acción estructurada de recepción: NO requiere
    que la conversación esté tomada (`ConversationControl.state == taken`) ni
    la toma, asigna o pausa el bot. Eso queda reservado a los mensajes
    humanos libres (`services.human_messages.send_staff_message`).

    Errores: `TakeoverUnavailable` (integración apagada / Lead sin
    conversación del agente), `ProposalConflict` (key reutilizada con otro
    payload, Lead cerrado o con turno), `ProposalInvalid` (servicio/profesional/horario).
    """
    if not takeover_enabled():
        raise TakeoverUnavailable('takeover_disabled')
    payload = dict(lead=lead, service_id=service_id, professional_id=professional_id, start_at=start_at)
    try:
        return _create(**payload, idempotency_key=idempotency_key, user=user)
    except IntegrityError:
        # Misma key en paralelo desde OTRO Lead (el lock del Lead serializa el
        # mismo Lead): la transacción perdedora se revierte entera y se
        # resuelve contra la que ganó.
        existing = _existing(lead.business_id, idempotency_key)
        if existing is None:
            raise
        return _replay(existing, **payload)


def _existing(business_id, idempotency_key) -> AppointmentProposal | None:
    return (
        AppointmentProposal.objects.select_related('service', 'professional', 'staff_message')
        .filter(business_id=business_id, idempotency_key=idempotency_key)
        .first()
    )


def _replay(existing: AppointmentProposal, *, lead, service_id, professional_id, start_at) -> ProposalResult:
    same = (
        existing.lead_id == lead.pk
        and str(existing.service_id) == str(service_id)
        and str(existing.professional_id or '') == str(professional_id or '')
        and existing.proposed_start_at == start_at
    )
    if not same:
        raise ProposalConflict(
            'idempotency_key_reused', 'Esta clave de idempotencia ya se usó para otra propuesta.',
        )
    now = timezone.now()
    if _is_expired(existing, now):
        AppointmentProposal.objects.filter(pk=existing.pk, status=Status.QUEUED).update(
            status=Status.EXPIRED, updated_at=now,
        )
        existing.refresh_from_db(fields=['status', 'updated_at'])
    return ProposalResult(existing, created=False)


def _create(*, lead, service_id, professional_id, start_at, idempotency_key, user) -> ProposalResult:
    with transaction.atomic():
        lead = (
            Lead.objects.select_for_update(of=('self',))
            .select_related('business', 'agent_state', 'customer')
            .get(pk=lead.pk, business_id=lead.business_id)
        )
        business = lead.business

        existing = _existing(business.pk, idempotency_key)
        if existing is not None:
            return _replay(
                existing, lead=lead, service_id=service_id, professional_id=professional_id, start_at=start_at,
            )

        if lead.status == Lead.Status.CLOSED:
            raise ProposalConflict('lead_closed', 'El lead está cerrado.')
        if lead.appointment_id is not None:
            raise ProposalConflict('lead_has_appointment', 'El lead ya tiene un turno vinculado.')
        # Solo se exige que el Lead tenga una conversación de agente para
        # poder enrutar el envío; el estado de takeover (`ConversationControl`)
        # es irrelevante para esta acción estructurada (no pausa el bot).
        if conversation_id_for(lead) is None:
            raise TakeoverUnavailable('conversation_unavailable')

        now = timezone.now()
        if start_at <= now:
            raise ProposalInvalid('start_at', 'El horario propuesto ya pasó.')
        service = AppointmentService.objects.filter(pk=service_id, business=business).first()
        if service is None:
            raise ProposalInvalid('service_id', 'Servicio no encontrado.')
        professional = None
        if professional_id:
            professional = AppointmentProfessional.objects.filter(pk=professional_id, business=business).first()
            if professional is None:
                raise ProposalInvalid('professional_id', 'Profesional no encontrado.')

        # Mismo orden de validación que la reserva manual (AppointmentSerializer.create):
        # lock → end_at desde la duración → disponibilidad (activo, elegibilidad,
        # horarios, excepciones) → solapamiento. Sin crear nada en la agenda.
        lock_professionals(business, {professional})
        end_at = compute_end_at(service, start_at)
        try:
            ensure_slot_available(
                business=business, service=service, professional=professional, start_at=start_at, end_at=end_at,
            )
            ensure_no_overlap(
                business=business, service=service, professional=professional, start_at=start_at, end_at=end_at,
            )
        except BookingError as exc:
            raise ProposalInvalid(_PAYLOAD_FIELDS.get(exc.field, 'start_at'), exc.message) from exc

        previous = (
            AppointmentProposal.objects.select_for_update()
            .filter(business=business, lead=lead, status__in=AppointmentProposal.ACTIVE_STATUSES)
            .first()
        )
        if previous is not None:
            previous.status = Status.EXPIRED if _is_expired(previous, now) else Status.SUPERSEDED
            previous.save(update_fields=['status', 'updated_at'])

        deposit_amount = compute_deposit_amount(
            price=service.price, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
        )
        proposal = AppointmentProposal(
            business=business, lead=lead, service=service, professional=professional,
            proposed_start_at=start_at, proposed_end_at=end_at,
            service_name=service.name, professional_name=professional.name if professional else None,
            service_duration_minutes=service.duration_minutes, service_price=service.price,
            currency=business.currency, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
            deposit_amount=deposit_amount, status=Status.PENDING_DELIVERY, idempotency_key=idempotency_key,
            created_by=user,
        )
        proposal.staff_message = enqueue_staff_message(lead, build_proposal_text(lead, proposal), user=user)
        proposal.save(force_insert=True)
        logger.info(
            'appointment_proposal_created proposal=%s lead=%s msg=%s previous=%s',
            proposal.pk, lead.pk, proposal.staff_message_id, previous.pk if previous else None,
        )
        return ProposalResult(proposal, created=True)


# ── Texto determinístico (español fijo, sin LLM) ─────────────────────────────

def _patient_name(lead: Lead) -> str:
    try:
        agent = lead.agent_state
    except LeadAgentState.DoesNotExist:
        agent = None
    name = ((agent.patient_name or agent.whatsapp_profile_name) if agent else '') or (
        lead.customer.name if lead.customer_id else ''
    )
    return (name or '').strip()


def _money(amount: Decimal, currency: str) -> str:
    """`ARS 1.500` / `ARS 1.500,50` (formato es-AR, sin depender del locale del proceso)."""
    value = amount.quantize(Decimal('0.01'))
    integer, cents = f'{value:,.2f}'.split('.')
    integer = integer.replace(',', '.')
    return f'{currency} {integer}' if cents == '00' else f'{currency} {integer},{cents}'


def build_proposal_text(lead: Lead, proposal: AppointmentProposal) -> str:
    local_start = proposal.proposed_start_at.astimezone(resolve_business_timezone(lead.business))
    name = _patient_name(lead)
    greeting = f'Hola, {name}.' if name else 'Hola.'
    with_professional = f' con {proposal.professional_name}' if proposal.professional_name else ''
    parts = [
        f'{greeting} Tenemos disponibilidad para {proposal.service_name} el {local_start:%d/%m/%Y} '
        f'a las {local_start:%H:%M}{with_professional}.'
    ]
    if proposal.service_price > 0:
        parts.append(f'Precio: {_money(proposal.service_price, proposal.currency)}.')
    if proposal.deposit_amount > 0:
        parts.append(f'Seña: {_money(proposal.deposit_amount, proposal.currency)}.')
    parts.append('El horario está sujeto a disponibilidad al confirmar. ¿Querés que recepción lo confirme?')
    return ' '.join(parts)
