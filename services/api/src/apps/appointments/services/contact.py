"""Contacto manual por WhatsApp desde la página pública de la reserva (Slice 6D).

El backend arma el link `https://wa.me/...` completo (teléfono normalizado +
mensaje prearmado URL-encoded); el frontend solo lo abre cuando el cliente
toca el botón. Nada se envía automáticamente.

Solo hay link en dos situaciones (mismo criterio que `deriveBookingView`
del frontend):
- turno `confirmed` → mensaje que dice que la reserva está confirmada;
- pago `requires_review` con el turno NO confirmado → mensaje neutral que
  nunca afirma confirmación ni pago.
En cualquier otro estado (pending, uncertain, expired, ...) → None.

El mensaje nunca incluye montos, ids de Mercado Pago, `external_reference`,
`public_token` ni URLs.
"""
from __future__ import annotations

from apps.business.models import BusinessBranding
from apps.business.whatsapp import build_whatsapp_url

from ..models import Appointment, AppointmentPayment
from .notifications import local_start

CONTACT_CONFIRMED = 'confirmed'
CONTACT_REQUIRES_REVIEW = 'requires_review'


def booking_contact_kind(appointment: Appointment, payment_status: str | None) -> str | None:
  if appointment.effective_status() == Appointment.Status.CONFIRMED:
    return CONTACT_CONFIRMED
  if payment_status == AppointmentPayment.Status.REQUIRES_REVIEW:
    return CONTACT_REQUIRES_REVIEW
  return None


def business_whatsapp_phone(business) -> str:
  try:
    return business.branding.whatsapp_phone or ''
  except BusinessBranding.DoesNotExist:
    return ''


def build_booking_message(appointment: Appointment, kind: str) -> str:
  start = local_start(appointment)
  what = appointment.service_name
  if appointment.professional_id:
    what = f'{what} con {appointment.professional.name}'
  when = f'el {start:%d/%m/%Y} a las {start:%H:%M}'
  business_name = appointment.business.name
  if kind == CONTACT_CONFIRMED:
    return f'Hola, reservé un turno en {business_name} para {what} {when}. Mi reserva está confirmada.'
  return (
    f'Hola, hice una reserva en {business_name} para {what} {when} '
    'y el sistema indica que necesita revisión.'
  )


def booking_whatsapp_url(appointment: Appointment, payment_status: str | None) -> str | None:
  kind = booking_contact_kind(appointment, payment_status)
  if kind is None:
    return None
  phone = business_whatsapp_phone(appointment.business)
  if not phone:
    return None
  return build_whatsapp_url(phone, build_booking_message(appointment, kind))
