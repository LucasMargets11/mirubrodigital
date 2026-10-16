"""Notificaciones internas de Turnos al negocio (Slice 6D).

Dos eventos, ambos disparados por el webhook de pago (`payment_confirmation`):

- `appointment_confirmed:<appointment_id>` — el pago aprobado confirmó el turno.
- `appointment_payment_review:<payment_id>` — el pago se cobró pero el turno
  NO quedó confirmado (`AppointmentPayment.REQUIRES_REVIEW`). Prioritaria.

Se crean con `on_commit_safely`: recién después de que la transacción que
confirmó el turno / registró el pago hizo commit, y un fallo solo se loguea
(nunca revierte ni hace fallar el webhook). La deduplicación la garantiza la
constraint única (business, dedupe_key) de `BusinessNotification`.

El contenido es operativo: cliente, servicio, fecha/hora, profesional y un
motivo legible. Nunca ids de Mercado Pago, `external_reference`, montos ni
`public_token`.
"""
from __future__ import annotations

from urllib.parse import urlencode

from apps.notifications.business_notifications import create_business_notification, on_commit_safely
from apps.notifications.models import BusinessNotification

from ..models import Appointment, AppointmentPayment
from .availability import resolve_business_timezone

Kind = BusinessNotification.Kind
ReviewReason = AppointmentPayment.ReviewReason

TURNOS_LIST_PATH = '/app/turnos/turnos'

# Motivo operativo (para el negocio) de cada `review_reason` técnico.
REVIEW_REASON_MESSAGES = {
  ReviewReason.APPROVED_AFTER_EXPIRY: 'El pago se aprobó después de que venciera la reserva temporal.',
  ReviewReason.APPROVAL_TIME_UNKNOWN: 'No se pudo verificar cuándo se aprobó el pago.',
  ReviewReason.SLOT_CONFLICT: 'El horario ya estaba ocupado por otro turno.',
  ReviewReason.APPOINTMENT_ALREADY_CONFIRMED: 'La reserva ya estaba confirmada por otra vía.',
  ReviewReason.APPOINTMENT_NOT_PAYABLE: 'La reserva ya no admitía el pago (cancelada o finalizada).',
}
DEFAULT_REVIEW_MESSAGE = 'El pago no pudo aplicarse automáticamente a la reserva.'


def local_start(appointment: Appointment):
  return appointment.start_at.astimezone(resolve_business_timezone(appointment.business))


def appointment_action_url(appointment: Appointment) -> str:
  query = urlencode({'date': local_start(appointment).date().isoformat(), 'appointment': str(appointment.pk)})
  return f'{TURNOS_LIST_PATH}?{query}'


def _summary(appointment: Appointment) -> str:
  start = local_start(appointment)
  parts = [appointment.customer_name, appointment.service_name, start.strftime('%d/%m/%Y %H:%M')]
  if appointment.professional_id:
    parts.append(f'con {appointment.professional.name}')
  return ' · '.join(parts)


def notify_appointment_confirmed(appointment_id) -> None:
  appointment = Appointment.objects.select_related('business', 'professional').get(pk=appointment_id)
  create_business_notification(
    business_id=appointment.business_id,
    kind=Kind.APPOINTMENT_CONFIRMED,
    dedupe_key=f'{Kind.APPOINTMENT_CONFIRMED}:{appointment.pk}',
    title='Nueva reserva confirmada',
    message=_summary(appointment),
    severity=BusinessNotification.Severity.INFO,
    action_url=appointment_action_url(appointment),
    related_object_type='appointment',
    related_object_id=str(appointment.pk),
  )


def notify_appointment_payment_review(payment_id) -> None:
  payment = (
    AppointmentPayment.objects.select_related('appointment__business', 'appointment__professional')
    .get(pk=payment_id)
  )
  appointment = payment.appointment
  reason = REVIEW_REASON_MESSAGES.get(payment.review_reason, DEFAULT_REVIEW_MESSAGE)
  create_business_notification(
    business_id=payment.business_id,
    kind=Kind.APPOINTMENT_PAYMENT_REVIEW,
    dedupe_key=f'{Kind.APPOINTMENT_PAYMENT_REVIEW}:{payment.pk}',
    title='Pago recibido — reserva requiere revisión',
    message=f'{_summary(appointment)}\n{reason} El turno no quedó confirmado.',
    severity=BusinessNotification.Severity.CRITICAL,
    action_url=appointment_action_url(appointment),
    related_object_type='appointment',
    related_object_id=str(appointment.pk),
  )


def schedule_appointment_confirmed(appointment_id) -> None:
  on_commit_safely(
    lambda: notify_appointment_confirmed(appointment_id),
    description=f'appointment_confirmed appointment={appointment_id}',
  )


def schedule_appointment_payment_review(payment_id) -> None:
  on_commit_safely(
    lambda: notify_appointment_payment_review(payment_id),
    description=f'appointment_payment_review payment={payment_id}',
  )
