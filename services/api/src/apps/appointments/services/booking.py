"""
Creación/reprogramación de `Appointment` (Slice 3A).

Estrategia de concurrencia (Postgres)
--------------------------------------
No existe todavía una fila "padre" natural que represente
`(business, professional, día)` para lockear (a diferencia de, por ejemplo,
`DocumentSeries`/`QuoteSequence` en otras apps del repo, que sí tienen un
contador persistente). En vez de introducir un mecanismo nuevo (advisory
locks, exclusion constraints con `btree_gist`), seguimos el patrón ya usado
en el repo (`transaction.atomic()` + `select_for_update()` sobre una fila
existente, ver `apps.invoices.serializers.get_or_create_series` o
`apps.billing.subscription_activator`) lockeando las filas del/los
`AppointmentProfessional` involucrados y, SIEMPRE, la fila del `Business`.

Slice 7B.1: el lock del `Business` se toma también en turnos con
profesional. Un turno legacy `professional=None` de un servicio con
profesionales ocupa TODO el negocio en su intervalo
(`availability.conflicting_appointments`), así que su (re)ocupación — que
lockea el `Business` — debe serializarse contra las reservas de cualquier
profesional. Lockear solo la fila del profesional dejaba dos carriles
paralelos (null vs profesional) que podían confirmar el mismo intervalo.

Esto serializa TODAS las creaciones/reprogramaciones concurrentes del
negocio durante la transacción: la segunda request debe esperar a que la primera confirme
(commit) o aborte (rollback) antes de poder leer/escribir, así que el chequeo
de solapamiento que se hace después del lock siempre ve el estado real y
consistente. Es más coarse-grained que un exclusion constraint por rango de
tiempo (bloquea todo el profesional, no solo el horario en cuestión), pero es
correcto, simple y consistente con el resto del código para el volumen
esperado (transacciones cortas, un negocio a la vez). Si el volumen de turnos concurrentes por profesional
creciera lo suficiente como para que esto sea un cuello de botella, la
migración natural es un `ExclusionConstraint` (GiST) sobre
`(business_id, professional_id, tsrange(start_at, end_at))`.

Un turno `reprogramado` puede cambiar de profesional: en ese caso se lockean
ambas filas (la anterior y la nueva), siempre en el mismo orden (por `id`)
para evitar deadlocks entre transacciones concurrentes que lockean el mismo
par de profesionales en distinto orden.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable

from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.business.models import Business

from ..models import Appointment, AppointmentProfessional, AppointmentService
from .availability import AvailabilityError, conflicting_appointments, validate_slot_within_availability
from .customer_link import resolve_customer_for_appointment
from .deposit import compute_deposit_amount
from .reminder_automation import reconcile_appointment_reminders

# Duración del hold temporal para servicios con seña reservados públicamente
# (Slice 4B, punto 6). Ver `Appointment.expires_at` / `AppointmentQuerySet.occupying`.
PUBLIC_HOLD_MINUTES = 10


class BookingError(Exception):
  def __init__(self, message: str, field: str | None = None):
    super().__init__(message)
    self.message = message
    self.field = field


class SlotOverlap(BookingError):
  pass


def lock_professionals(business: Business, professionals: Iterable[AppointmentProfessional | None]) -> None:
  """Lockea, en orden determinístico, las filas involucradas en la reserva.

  Debe llamarse dentro de una `transaction.atomic()` ya abierta por el
  caller. Orden fijo: profesionales (por `id`) y después `Business`, que se
  lockea siempre (Slice 7B.1). Ver docstring del módulo.
  """
  ids = sorted({str(p.id) for p in professionals if p is not None})
  if ids:
    # Materializar: el SELECT ... FOR UPDATE debe ejecutarse ahora, no de forma perezosa.
    list(
      AppointmentProfessional.objects.select_for_update()
      .filter(pk__in=ids)
      .order_by('id')
    )
  Business.objects.select_for_update().get(pk=business.pk)


def compute_end_at(service: AppointmentService, start_at: dt.datetime) -> dt.datetime:
  return start_at + dt.timedelta(minutes=service.duration_minutes)


def ensure_slot_available(
  *,
  business: Business,
  service: AppointmentService,
  professional: AppointmentProfessional | None,
  start_at: dt.datetime,
  end_at: dt.datetime,
) -> None:
  try:
    validate_slot_within_availability(
      business=business,
      service_id=str(service.id),
      professional_id=str(professional.id) if professional else None,
      target_start=start_at,
      target_end=end_at,
    )
  except AvailabilityError as exc:
    raise BookingError(exc.message, field=exc.field or 'start_at') from exc


def ensure_no_overlap(
  *,
  business: Business,
  service: AppointmentService,
  professional: AppointmentProfessional | None,
  start_at: dt.datetime,
  end_at: dt.datetime,
  exclude_pk=None,
) -> None:
  """Ver `availability.conflicting_appointments` (incluye legacy `None`)."""
  overlapping = conflicting_appointments(business=business, service=service, professional=professional).filter(
    start_at__lt=end_at,
    end_at__gt=start_at,
  )
  if exclude_pk is not None:
    overlapping = overlapping.exclude(pk=exclude_pk)
  if overlapping.exists():
    raise SlotOverlap(
      'Ya existe un turno confirmado o con seña pendiente que se superpone con este horario.', field='start_at',
    )


def _resolve_service_for_booking(business: Business, service_id: str) -> AppointmentService:
  try:
    service = AppointmentService.objects.get(pk=service_id, business=business)
  except (AppointmentService.DoesNotExist, ValueError, TypeError):
    raise BookingError('Servicio no encontrado.', field='service')
  if not service.is_active:
    raise BookingError('El servicio no está activo.', field='service')
  return service


def _resolve_professional_for_booking(
  business: Business, professional_id: str, service: AppointmentService,
) -> AppointmentProfessional:
  try:
    professional = AppointmentProfessional.objects.get(pk=professional_id, business=business)
  except (AppointmentProfessional.DoesNotExist, ValueError, TypeError):
    raise BookingError('Profesional no encontrado.', field='professional')
  if not professional.is_active:
    raise BookingError('El profesional no está activo.', field='professional')
  if not professional.services.filter(pk=service.pk).exists():
    raise BookingError('El profesional no realiza este servicio.', field='professional')
  return professional


@transaction.atomic
def create_public_appointment(
  *,
  business: Business,
  service_id: str,
  professional_id: str | None,
  start_at: dt.datetime,
  customer_name: str,
  customer_phone: str,
  customer_email: str = '',
) -> Appointment:
  """Crea una reserva pública (Slice 4B, `/t/[slug]`).

  Flujo crítico completo dentro de una única transacción: resolver
  servicio/profesional, lockear, revalidar disponibilidad y solapamiento, y
  recién ahí crear el `Appointment`. Nunca "chequear y liberar el lock antes
  de crear" (ver docstring de `lock_professionals`).

  Sin seña (`deposit_type='none'`): crea directamente `confirmed`, sin hold.
  Con seña (`fixed`/`percentage`): crea `pending_payment` con
  `expires_at = now + PUBLIC_HOLD_MINUTES`, bloqueando el slot de inmediato.
  Todavía no crea ningún pago (Mercado Pago queda fuera de este slice).
  """
  service = _resolve_service_for_booking(business, service_id)
  professional = None
  if professional_id:
    professional = _resolve_professional_for_booking(business, professional_id, service)

  lock_professionals(business, {professional})

  # `ensure_slot_available` aplica la regla profesional/null (Slice 7B.1):
  # servicio con profesionales + `professional=None` → error.
  end_at = compute_end_at(service, start_at)
  ensure_slot_available(
    business=business, service=service, professional=professional, start_at=start_at, end_at=end_at,
  )
  ensure_no_overlap(business=business, service=service, professional=professional, start_at=start_at, end_at=end_at)

  # Slice 7C: un servicio legacy con seña que calcula monto 0 (`fixed=0`, o
  # `percentage` con precio 0) dejaría un `pending_payment` imposible de
  # pagar. Fail-closed: no se crea la reserva hasta que el negocio corrija
  # la seña (no se reinterpreta en silencio como "sin seña").
  if service.deposit_type != AppointmentService.DepositType.NONE and compute_deposit_amount(
    price=service.price, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
  ) <= 0:
    raise BookingError(
      'Este servicio no admite reservas online por ahora (seña mal configurada).', field='service',
    )

  if service.deposit_type == AppointmentService.DepositType.NONE:
    status = Appointment.Status.CONFIRMED
    expires_at = None
  else:
    status = Appointment.Status.PENDING_PAYMENT
    expires_at = dj_timezone.now() + dt.timedelta(minutes=PUBLIC_HOLD_MINUTES)

  # Bajo el lock del `Business` y recién con el slot validado: una reserva
  # rechazada no deja un `Customer` creado (rollback de esta transacción).
  customer = resolve_customer_for_appointment(
    business=business, customer_name=customer_name, customer_phone=customer_phone, customer_email=customer_email,
  )

  appointment = Appointment.objects.create(
    business=business,
    customer=customer,
    service=service,
    professional=professional,
    start_at=start_at,
    end_at=end_at,
    status=status,
    expires_at=expires_at,
    source=Appointment.Source.PUBLIC,
    service_name=service.name,
    service_duration_minutes=service.duration_minutes,
    service_price=service.price,
    deposit_type=service.deposit_type,
    deposit_value=service.deposit_value,
    customer_name=customer_name,
    customer_phone=customer_phone,
    customer_email=customer_email or '',
  )  # CUSTOMER 07B: sin seña queda `confirmed` → recordatorio previo si aplica.
  # Con seña (`pending_payment`) no: se reconcilia al confirmarse por el pago.
  reconcile_appointment_reminders(appointment)
  return appointment

