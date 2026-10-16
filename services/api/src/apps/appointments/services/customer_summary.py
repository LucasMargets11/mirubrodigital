"""Resumen de Turnos de un `Customer` (Turnos CUSTOMER 02).

Se deriva de `Appointment.customer` y SIEMPRE se filtra también por el
`Business` del Customer: nunca alcanza solo con la FK.

Definiciones (únicas; el frontend no las recalcula):

- `total`: turnos vinculados que existieron como reserva real, es decir todos
  menos los vencidos (`expired`, incluido el `pending_payment` con hold
  vencido según `Appointment.effective_status`): un checkout abandonado no es
  un turno del cliente.
- `completed` / `cancelled` / `no_show`: conteo por `status`.
- `upcoming`: turnos futuros que ocupan agenda AHORA (misma regla que
  `AppointmentQuerySet.occupying`: `confirmed`, o `pending_payment` con hold
  vigente). Cancelados y vencidos nunca son "próximos".
- `next_appointment`: el primero de `upcoming` por `start_at`.
- `last_appointment`: el turno pasado (`start_at <= now`) más reciente que
  efectivamente se agendó: `completed`, `no_show` o `confirmed` (aún no
  cerrado). Cancelados, vencidos y holds sin pagar no cuentan.

Todo se compara contra instantes (`start_at` es aware), así que "futuro" y
"pasado" no dependen de la zona horaria; el panel muestra los horarios en la
timezone del Business (`/auth/me` → `business.timezone`).
"""
from __future__ import annotations

from django.db.models import Count, Q
from django.utils import timezone as dj_timezone

from apps.appointments.models import Appointment

from .customer_history import upcoming_appointments

S = Appointment.Status

# Estados de un turno pasado que "sucedió" en la agenda del cliente.
LAST_APPOINTMENT_STATUSES = (S.COMPLETED, S.NO_SHOW, S.CONFIRMED)


def _effective_expired_q(now) -> Q:
  return Q(status=S.EXPIRED) | Q(status=S.PENDING_PAYMENT, expires_at__lte=now)


def _serialize(appointment: Appointment | None, now) -> dict | None:
  if appointment is None:
    return None
  return {
    'id': str(appointment.pk),
    'start_at': appointment.start_at.isoformat(),
    'end_at': appointment.end_at.isoformat(),
    'status': appointment.effective_status(now=now),
    'service_name': appointment.service_name,
    'professional_name': appointment.professional.name if appointment.professional_id else None,
  }


def build_customer_appointments_summary(customer, *, now=None) -> dict:
  now = now or dj_timezone.now()
  qs = Appointment.objects.filter(business_id=customer.business_id, customer=customer)

  counts = qs.aggregate(
    total=Count('pk', filter=~_effective_expired_q(now)),
    completed=Count('pk', filter=Q(status=S.COMPLETED)),
    cancelled=Count('pk', filter=Q(status=S.CANCELLED)),
    no_show=Count('pk', filter=Q(status=S.NO_SHOW)),
  )

  # Misma partición que el historial (`customer_history`): una sola regla.
  upcoming = upcoming_appointments(qs, now=now)
  counts['upcoming'] = upcoming.count()
  next_appointment = upcoming.select_related('professional').order_by('start_at', 'pk').first()
  last_appointment = (
    qs.select_related('professional')
    .filter(start_at__lte=now, status__in=LAST_APPOINTMENT_STATUSES)
    .order_by('-start_at', '-pk').first()
  )

  return {
    **counts,
    'next_appointment': _serialize(next_appointment, now),
    'last_appointment': _serialize(last_appointment, now),
  }
