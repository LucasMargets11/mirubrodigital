"""Estado financiero representativo de un turno (Slice 7B.3).

Un `Appointment` puede acumular varios `AppointmentPayment` (reintentos).
Este módulo es la ÚNICA regla que decide cuál de ellos representa el estado
financiero actual del turno; la usan tanto el panel interno
(`AppointmentSerializer.payment_summary`) como la página pública
(`public_serializers.public_payment_status`). No duplicar en el frontend.

Solo lee: nunca muta Appointment/AppointmentPayment.
"""
from __future__ import annotations

from ..models import Appointment, AppointmentPayment

# Prioridad del intento representativo:
#   1. requires_review — dinero cobrado sin aplicar: lo que el negocio (y el
#      cliente) más necesita ver, aunque haya otros intentos;
#   2. approved — dinero cobrado y aplicado;
#   3. intento activo (creating / pending / uncertain);
#   4. el intento más reciente (rejected / cancelled / error).
# Dentro de cada grupo gana el más reciente.
_REPRESENTATIVE_PRIORITY = (
  (AppointmentPayment.Status.REQUIRES_REVIEW,),
  (AppointmentPayment.Status.APPROVED,),
  AppointmentPayment.ACTIVE_STATUSES,
)


def representative_payment(appointment: Appointment) -> AppointmentPayment | None:
  """Intento de pago que representa el estado financiero del turno, o None.

  Usa `appointment.payments.all()` (aprovecha `prefetch_related('payments')`
  en los listados) y ordena en memoria del más reciente al más viejo.
  """
  payments = sorted(appointment.payments.all(), key=lambda p: p.created_at, reverse=True)
  if not payments:
    return None
  for statuses in _REPRESENTATIVE_PRIORITY:
    chosen = next((p for p in payments if p.status in statuses), None)
    if chosen is not None:
      return chosen
  return payments[0]


def build_payment_summary(appointment: Appointment) -> dict | None:
  """Resumen financiero interno (panel del Business) del turno, o None.

  Solo el snapshot persistido del intento representativo: nunca payloads de
  Mercado Pago, `external_reference`, ids del provider, `checkout_url` ni
  `failure_reason`. El importe es el `amount` congelado al crear el intento,
  nunca recalculado desde el `AppointmentService` actual.
  """
  payment = representative_payment(appointment)
  if payment is None:
    return None
  requires_review = payment.status == AppointmentPayment.Status.REQUIRES_REVIEW
  return {
    'status': payment.status,
    'amount': f'{payment.amount:.2f}',
    'currency': payment.currency,
    'paid_at': payment.paid_at,
    'requires_review': requires_review,
    # Código estable (el panel lo traduce a copy humano); vacío salvo revisión.
    'review_reason': (payment.review_reason or None) if requires_review else None,
  }
