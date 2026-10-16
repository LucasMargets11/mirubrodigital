"""
Motor de disponibilidad real de turnos (Slice 3B).

Calcula, a partir de la configuración de horarios, excepciones y los
`Appointment` ya confirmados, los slots en los que un servicio puede
reservarse en una fecha dada.

Reglas (ver docs/IA para el detalle completo):
  1. El negocio debe estar abierto en esa fecha/hora (AppointmentSchedule /
     AppointmentException con professional=None).
  2. Si se pide un profesional, su disponibilidad se calcula como la
     intersección entre el horario del negocio y el horario propio del
     profesional. Un profesional sin horario propio para ese día no está
     disponible ese día.
  3. Precedencia de excepciones: excepción del negocio primero, luego
     excepción del profesional. Una excepción nunca puede abrir horario
     fuera del horario efectivo del negocio (se garantiza intersecando
     siempre contra el negocio).
  4. Un slot solo es válido si el servicio completo entra en el bloque.
  5. Granularidad fija de slots: `SLOT_GRANULARITY_MINUTES`.
  6. Un slot que se superpone con un `Appointment` ocupante
     (`AppointmentQuerySet.occupying`, Slice 4B: `confirmed` o
     `pending_payment` con hold vigente) que compite por ese recurso se
     elimina del resultado (ver `conflicting_appointments`).
  7. Modo de scheduling (Slice 7B.1), SIEMPRE derivado server-side: si el
     servicio tiene al menos un profesional elegible (activo, del mismo
     Business, asignado al servicio) el profesional es OBLIGATORIO; si no
     tiene ninguno, el turno es "del negocio" (`professional=None`). Ver
     `service_requires_professional`.

Timezone: se usa `Business.timezone` (IANA tz name, ver
`apps.business.models.Business.timezone`), que es la fuente canónica de
timezone por negocio en MiRubro. Internamente se trabaja siempre con
datetimes timezone-aware.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from django.db.models import Q, QuerySet
from django.utils import timezone as dj_timezone

from apps.business.models import Business

from ..models import (
  Appointment,
  AppointmentException,
  AppointmentProfessional,
  AppointmentSchedule,
  AppointmentService,
)

# Intervalo fijo entre slots candidatos. Centralizado acá para poder
# ajustarlo a futuro (p.ej. configurable por negocio) sin tocar el algoritmo.
SLOT_GRANULARITY_MINUTES = 15

TimeInterval = tuple[dt.time, dt.time]


class AvailabilityError(Exception):
  """Error de validación de entrada del motor de disponibilidad."""

  def __init__(self, message: str, field: str | None = None):
    super().__init__(message)
    self.message = message
    self.field = field


class ServiceNotFound(AvailabilityError):
  pass


class ServiceInactive(AvailabilityError):
  pass


class ProfessionalNotFound(AvailabilityError):
  pass


class ProfessionalInactive(AvailabilityError):
  pass


class ProfessionalCannotPerformService(AvailabilityError):
  pass


class ProfessionalRequired(AvailabilityError):
  pass


class SlotNotAvailable(AvailabilityError):
  pass


@dataclass(frozen=True)
class Slot:
  start: dt.datetime
  end: dt.datetime

  def to_dict(self) -> dict:
    return {'start': self.start.isoformat(), 'end': self.end.isoformat()}


@dataclass(frozen=True)
class AvailabilityResult:
  date: dt.date
  service: AppointmentService
  professional: AppointmentProfessional | None
  slots: list[Slot] = field(default_factory=list)


def resolve_business_timezone(business: Business) -> dt.tzinfo:
  """Devuelve el tzinfo del negocio.

  Fuente canónica: `Business.timezone` (IANA name, ej.
  'America/Argentina/Buenos_Aires'). Si el valor faltara o fuera inválido,
  se cae al timezone default de Django (`settings.TIME_ZONE`).
  """
  tz_name = getattr(business, 'timezone', None)
  if tz_name:
    try:
      return ZoneInfo(tz_name)
    except Exception:
      pass
  return dj_timezone.get_default_timezone()


def eligible_professionals(service: AppointmentService) -> QuerySet[AppointmentProfessional]:
  """Profesionales que pueden atender `service`: activos, del mismo Business
  y asignados al servicio. Única definición de "elegible" (Slice 7B.1)."""
  return AppointmentProfessional.objects.filter(
    business_id=service.business_id, is_active=True, services=service,
  )


def service_requires_professional(service: AppointmentService) -> bool:
  """True si el servicio funciona CON profesionales (Slice 7B.1).

  - Sin profesionales elegibles: `professional=None` es el único valor
    válido (cualquier profesional puntual falla igual en
    `_resolve_professional`, porque no sería elegible).
  - Con al menos uno: el profesional es obligatorio; no existe el modo
    "sin profesional" para ese servicio.
  """
  return eligible_professionals(service).exists()


def _services_with_professionals_q(business: Business) -> Q:
  """Q sobre `Appointment`: su servicio tiene HOY profesionales elegibles."""
  services = AppointmentService.objects.filter(
    business=business, professionals__business=business, professionals__is_active=True,
  )
  return Q(service__in=services)


def conflicting_appointments(
  *,
  business: Business,
  service: AppointmentService,
  professional: AppointmentProfessional | None,
) -> QuerySet[Appointment]:
  """Turnos ocupantes que compiten por el recurso de un turno de `service`
  con `professional`. Base común de availability y del chequeo de
  solapamiento de booking/panel/webhook (el caller agrega el rango horario).

  `occupying()` sigue siendo la única fuente de verdad de "ocupa" (estados
  + vencimiento dinámico del hold).

  Compatibilidad legacy (Slice 7B.1): antes de esta regla podían crearse
  turnos `professional=None` para servicios que tienen profesionales. No se
  migran ni se les inventa profesional; mientras el servicio tenga
  profesionales elegibles, un turno así es AMBIGUO y se trata como
  ocupación de todo el negocio en ese intervalo:

  - slot de un profesional: lo bloquean sus propios turnos Y los turnos
    legacy `None` de servicios con profesionales;
  - turno "del negocio" de un servicio sin profesionales: lo bloquean los
    turnos `None` (agenda del negocio, sin cambios);
  - turno legacy `None` que vuelve a ocupar (p.ej. confirmación tardía por
    webhook): lo bloquea cualquier turno ocupante del negocio.
  """
  qs = Appointment.objects.occupying().filter(business=business)
  if professional is not None:
    return qs.filter(Q(professional=professional) | (Q(professional__isnull=True) & _services_with_professionals_q(business)))
  if service_requires_professional(service):
    return qs
  return qs.filter(professional__isnull=True)


def _intersect_intervals(a: list[TimeInterval], b: list[TimeInterval]) -> list[TimeInterval]:
  result: list[TimeInterval] = []
  for a_start, a_end in a:
    for b_start, b_end in b:
      start = max(a_start, b_start)
      end = min(a_end, b_end)
      if start < end:
        result.append((start, end))
  result.sort()
  return result


def _business_intervals(business: Business, target_date: dt.date) -> list[TimeInterval]:
  exception = (
    AppointmentException.objects
    .filter(business=business, professional__isnull=True, date=target_date)
    .first()
  )
  if exception is not None:
    if exception.is_closed:
      return []
    return [(exception.start_time, exception.end_time)]

  weekday = target_date.weekday()
  schedules = AppointmentSchedule.objects.filter(
    business=business, professional__isnull=True, weekday=weekday,
  ).order_by('start_time')
  return [(s.start_time, s.end_time) for s in schedules]


def _professional_intervals(
  business: Business, professional: AppointmentProfessional, target_date: dt.date,
) -> list[TimeInterval]:
  exception = (
    AppointmentException.objects
    .filter(business=business, professional=professional, date=target_date)
    .first()
  )
  if exception is not None:
    if exception.is_closed:
      return []
    return [(exception.start_time, exception.end_time)]

  weekday = target_date.weekday()
  schedules = AppointmentSchedule.objects.filter(
    business=business, professional=professional, weekday=weekday,
  ).order_by('start_time')
  # Sin horario propio para ese día => no disponible (aunque el negocio
  # esté abierto).
  return [(s.start_time, s.end_time) for s in schedules]


def _resolve_service(business: Business, service_id: str) -> AppointmentService:
  try:
    service = AppointmentService.objects.get(pk=service_id, business=business)
  except (AppointmentService.DoesNotExist, ValueError, TypeError):
    raise ServiceNotFound('Servicio no encontrado.', field='service')
  if not service.is_active:
    raise ServiceInactive('El servicio no está activo.', field='service')
  return service


def _resolve_professional(
  business: Business, professional_id: str, service: AppointmentService,
) -> AppointmentProfessional:
  try:
    professional = AppointmentProfessional.objects.get(pk=professional_id, business=business)
  except (AppointmentProfessional.DoesNotExist, ValueError, TypeError):
    raise ProfessionalNotFound('Profesional no encontrado.', field='professional')
  if not professional.is_active:
    raise ProfessionalInactive('El profesional no está activo.', field='professional')
  if not professional.services.filter(pk=service.pk).exists():
    raise ProfessionalCannotPerformService(
      'El profesional no realiza este servicio.', field='professional',
    )
  return professional


def resolve_professional_for_service(
  business: Business, service: AppointmentService, professional_id: str | None,
) -> AppointmentProfessional | None:
  """Aplica la regla profesional/null de Slice 7B.1 (nunca confiar en el cliente).

  - `professional_id` presente: debe ser elegible para el servicio (activo,
    del Business, asignado). Un servicio sin profesionales no tiene ninguno
    elegible, así que cualquier id se rechaza.
  - `professional_id` ausente: solo válido si el servicio NO tiene
    profesionales elegibles.
  """
  if professional_id:
    return _resolve_professional(business, professional_id, service)
  if service_requires_professional(service):
    raise ProfessionalRequired('Este servicio requiere elegir un profesional.', field='professional')
  return None


def _generate_slots(
  intervals: list[TimeInterval],
  target_date: dt.date,
  duration: dt.timedelta,
  tzinfo: dt.tzinfo,
) -> list[Slot]:
  granularity = dt.timedelta(minutes=SLOT_GRANULARITY_MINUTES)
  slots: list[Slot] = []
  for start_time, end_time in intervals:
    block_start = dt.datetime.combine(target_date, start_time, tzinfo=tzinfo)
    block_end = dt.datetime.combine(target_date, end_time, tzinfo=tzinfo)
    cursor = block_start
    while cursor + duration <= block_end:
      slots.append(Slot(start=cursor, end=cursor + duration))
      cursor += granularity
  slots.sort(key=lambda s: s.start)
  return slots


def _occupying_intervals(
  business: Business,
  service: AppointmentService,
  professional: AppointmentProfessional | None,
  target_date: dt.date,
  tzinfo: dt.tzinfo,
  exclude_appointment_id: str | None,
) -> list[tuple[dt.datetime, dt.datetime]]:
  """Intervalos ocupados ese día para un turno de `service`/`professional`
  (ver `conflicting_appointments`, incluida la compatibilidad legacy)."""
  day_start = dt.datetime.combine(target_date, dt.time.min, tzinfo=tzinfo)
  day_end = day_start + dt.timedelta(days=1)

  appointments = conflicting_appointments(business=business, service=service, professional=professional).filter(
    start_at__lt=day_end,
    end_at__gt=day_start,
  )
  if exclude_appointment_id:
    appointments = appointments.exclude(pk=exclude_appointment_id)

  return [(appt.start_at, appt.end_at) for appt in appointments]


def _remove_occupied_slots(
  slots: list[Slot], occupied: list[tuple[dt.datetime, dt.datetime]],
) -> list[Slot]:
  if not occupied:
    return slots
  return [
    slot for slot in slots
    if not any(slot.start < occ_end and slot.end > occ_start for occ_start, occ_end in occupied)
  ]


def compute_availability(
  *,
  business: Business,
  service_id: str,
  target_date: dt.date,
  professional_id: str | None = None,
  exclude_appointment_id: str | None = None,
) -> AvailabilityResult:
  """Calcula la disponibilidad REAL para `service` en `target_date`.

  Levanta `AvailabilityError` (o una subclase) si `service_id`/
  `professional_id` no son válidos para este `business`, o si el
  profesional no puede realizar el servicio. Una fecha sin disponibilidad
  (negocio cerrado, excepción, etc.) NO es un error: se devuelve
  `AvailabilityResult` con `slots=[]`.

  Los slots teóricos (horarios ∩ profesional ∩ excepciones) se descuentan
  contra los `Appointment` ocupantes que compiten por ese recurso ese día
  (`conflicting_appointments`). `exclude_appointment_id` permite
  ignorar un turno puntual (uso interno, para reprogramar sin que el turno
  se bloquee a sí mismo).
  """
  service = _resolve_service(business, service_id)

  professional = resolve_professional_for_service(business, service, professional_id)

  business_intervals = _business_intervals(business, target_date)

  if professional is not None:
    professional_intervals = _professional_intervals(business, professional, target_date)
    effective_intervals = _intersect_intervals(business_intervals, professional_intervals)
  else:
    effective_intervals = business_intervals

  tzinfo = resolve_business_timezone(business)
  duration = dt.timedelta(minutes=service.duration_minutes)
  slots = _generate_slots(effective_intervals, target_date, duration, tzinfo)

  occupied = _occupying_intervals(business, service, professional, target_date, tzinfo, exclude_appointment_id)
  slots = _remove_occupied_slots(slots, occupied)

  return AvailabilityResult(
    date=target_date, service=service, professional=professional, slots=slots,
  )


def validate_slot_within_availability(
  *,
  business: Business,
  service_id: str,
  target_start: dt.datetime,
  target_end: dt.datetime,
  professional_id: str | None = None,
) -> tuple[AppointmentService, AppointmentProfessional | None]:
  """Valida que `[target_start, target_end)` esté completamente contenido en
  algún bloque abierto para `business`/`professional`, reusando el mismo
  cálculo de intervalos que `compute_availability` (Slice 0/3A).

  A diferencia de `compute_availability`, no genera slots discretos: valida
  directamente que el rango pedido entre completo dentro de un bloque
  efectivo, lo que evita problemas de alineación con `SLOT_GRANULARITY_MINUTES`.

  Devuelve `(service, professional)` resueltos. Levanta `AvailabilityError`
  (o una subclase, incluyendo `SlotNotAvailable`) si el servicio/profesional
  no son válidos para este `business`, o si el horario pedido no está
  disponible.
  """
  service = _resolve_service(business, service_id)

  professional = resolve_professional_for_service(business, service, professional_id)

  tzinfo = resolve_business_timezone(business)
  local_start = target_start.astimezone(tzinfo)
  local_end = target_end.astimezone(tzinfo)

  if local_start.date() != local_end.date():
    raise SlotNotAvailable('El turno debe comenzar y terminar el mismo día.', field='start_at')

  target_date = local_start.date()
  business_intervals = _business_intervals(business, target_date)

  if professional is not None:
    professional_intervals = _professional_intervals(business, professional, target_date)
    effective_intervals = _intersect_intervals(business_intervals, professional_intervals)
  else:
    effective_intervals = business_intervals

  start_time = local_start.time()
  end_time = local_end.time()
  fits = any(start_time >= b_start and end_time <= b_end for b_start, b_end in effective_intervals)
  if not fits:
    raise SlotNotAvailable('El horario elegido no está disponible.', field='start_at')

  return service, professional
