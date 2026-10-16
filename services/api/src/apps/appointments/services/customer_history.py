"""Historial de Turnos de un `Customer` (Turnos CUSTOMER 03).

Se deriva SIEMPRE de `Appointment.customer` (la entidad fuente sigue siendo la
verdad): no existe un modelo persistente de "eventos" que copie turnos. Una
futura timeline unificada (turnos, ventas, pedidos, notas…) podrá combinar
este feed con otros construyendo eventos normalizados en memoria; por eso
cada item expone `type` y `occurred_at`.

Partición (única; el frontend no la recalcula):

- `upcoming` (Próximos): turnos futuros (`start_at > now`) que ocupan agenda
  AHORA — misma regla que `AppointmentQuerySet.occupying` y que el
  `next_appointment` del resumen (`customer_summary`): `confirmed`, o
  `pending_payment` con hold vigente. Orden: el más cercano primero.
- `history` (Historial): todo el resto de los turnos del cliente — pasados en
  cualquier estado, y también futuros cancelados / vencidos (incluido el
  `pending_payment` con hold vencido). Cancelaciones, no-shows y vencidos
  NUNCA se esconden. Orden: `occurred_at` más reciente primero.
- `all`: ambos, por `occurred_at` descendente.

"Futuro" / "pasado" se comparan contra instantes (`start_at` es aware), así
que el corte no depende de la zona horaria; el panel muestra fechas y horas
en `Business.timezone` (`/auth/me` → `business.timezone`).

`occurred_at` (CUSTOMER 04A.1) — cuándo ocurrió la actividad, no cuándo es el
turno. Regla ÚNICA para este historial y para la timeline del Customer
(`customers/timeline.py`), en Python (`appointment_occurred_at`) y en SQL
(`occurred_at_expression`, para ordenar/paginar en la base):

- `cancelled` → `updated_at`. No existe `cancelled_at`; la cancelación es la
  última escritura habitual (el webhook de pago nunca toca un cancelado).
  Limitación: un PATCH posterior del panel (notas, datos del cliente,
  reprogramación) mueve `updated_at`.
- `expired` y `pending_payment` con hold vencido → `expires_at` (el instante
  real de vencimiento; se conserva como evidencia al materializar
  `expired`). Sin `expires_at` (no debería pasar) → `updated_at`.
- `completed` / `no_show` / `confirmed` / resto → `start_at` (no hay
  `completed_at` ni `no_show_at`).

Los estados y la partición próximos/historial NO cambian: solo la fecha
semántica del evento y, por lo tanto, el orden del historial.
"""
from __future__ import annotations

from django.db.models import Case, F, Q, QuerySet, When
from django.utils import timezone as dj_timezone

from apps.appointments.models import Appointment

from .payment_summary import build_payment_summary

SCOPE_UPCOMING = 'upcoming'
SCOPE_HISTORY = 'history'
SCOPE_ALL = 'all'
SCOPES = (SCOPE_UPCOMING, SCOPE_HISTORY, SCOPE_ALL)


S = Appointment.Status


def appointment_occurred_at(appointment: Appointment, *, now):
  """Fecha de la actividad del turno (ver docstring del módulo)."""
  status = appointment.effective_status(now=now)
  if status == S.CANCELLED:
    return appointment.updated_at
  if status == S.EXPIRED:
    return appointment.expires_at or appointment.updated_at
  return appointment.start_at


def occurred_at_expression(*, now):
  """Misma regla que `appointment_occurred_at`, como expresión SQL."""
  return Case(
    When(status=S.CANCELLED, then=F('updated_at')),
    When(Q(status=S.EXPIRED) & Q(expires_at__isnull=False), then=F('expires_at')),
    When(status=S.EXPIRED, then=F('updated_at')),
    When(Q(status=S.PENDING_PAYMENT) & Q(expires_at__lte=now), then=F('expires_at')),
    default=F('start_at'),
  )


def customer_appointments(customer) -> QuerySet:
  """Turnos del Customer, filtrando también por su Business (nunca solo la FK)."""
  return (
    Appointment.objects.filter(business_id=customer.business_id, customer=customer)
    .select_related('professional')
    .prefetch_related('payments')
  )


def upcoming_appointments(queryset: QuerySet, *, now) -> QuerySet:
  return queryset.occupying(now=now).filter(start_at__gt=now)


def scoped_customer_appointments(customer, scope: str, *, now=None) -> QuerySet:
  now = now or dj_timezone.now()
  qs = customer_appointments(customer)
  if scope == SCOPE_UPCOMING:
    return upcoming_appointments(qs, now=now).order_by('start_at', 'pk')
  if scope == SCOPE_HISTORY:
    upcoming_pks = upcoming_appointments(
      Appointment.objects.filter(business_id=customer.business_id, customer=customer), now=now,
    ).values('pk')
    qs = qs.exclude(pk__in=upcoming_pks)
  elif scope != SCOPE_ALL:
    raise ValueError(f'scope inválido: {scope}')
  return qs.annotate(occurred_at=occurred_at_expression(now=now)).order_by('-occurred_at', '-pk')


def serialize_history_item(appointment: Appointment, *, now) -> dict:
  """Item del historial: solo snapshots del turno (sin joins a Service/Customer)."""
  status = appointment.effective_status(now=now)
  return {
    'type': 'appointment',
    'id': str(appointment.pk),
    'occurred_at': appointment_occurred_at(appointment, now=now).isoformat(),
    'start_at': appointment.start_at.isoformat(),
    'end_at': appointment.end_at.isoformat(),
    'status': status,
    'status_display': Appointment.Status(status).label,
    'source': appointment.source,
    'service_name': appointment.service_name,
    'service_price': f'{appointment.service_price:.2f}',
    'professional_id': str(appointment.professional_id) if appointment.professional_id else None,
    'professional_name': appointment.professional.name if appointment.professional_id else None,
    'customer_name': appointment.customer_name,
    'payment_summary': build_payment_summary(appointment),
    'created_at': appointment.created_at.isoformat(),
  }
