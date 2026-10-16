"""Recordatorios internos automáticos ligados a Turnos (CUSTOMER 07B).

Solo crea/mueve/cancela `CustomerReminder` internos del equipo: NUNCA envía
nada al cliente (ni WhatsApp, ni email, ni SMS). Dos reglas, configuradas por
Business en `CustomerReminderAutomationSettings` (apagadas por defecto):

- `appointment_upcoming`: "Confirmar turno de X", `hours_before` antes del
  turno. Solo turnos `confirmed` con Customer activo y cuyo `remind_at`
  todavía es futuro: un turno creado dentro de la anticipación NO genera un
  recordatorio ya vencido (no hay fallback a "ahora").
- `no_show_followup`: "Contactar por inasistencia", `delay_hours` después de
  la PRIMERA transición a `no_show`. `Appointment` no guarda `no_show_at`: el
  momento de la transición es `now` dentro de `admin_mutation` (única vía que
  escribe `no_show`). Los no-shows históricos no tienen ese dato y no se
  reprocesan (sin backfill).

Punto único: `reconcile_appointment_reminders(appointment, previous_status=...)`,
llamado dentro de la transacción (con el turno bloqueado) desde cada mutación
real: alta interna, reserva pública, `admin_mutation` (edición, reprogramación,
cambio de estado/cliente, cancelación), confirmación por pago y vencimiento
del hold en checkout/webhook.

Idempotencia: `automation_key` único por Business.
- previo: "appointment_upcoming:<appt>:<start_at UTC>" → reprocesar el mismo
  turno/horario nunca duplica; un turno reprogramado es un evento nuevo.
- no-show: "no_show_followup:<appt>" → uno solo por turno, aunque vuelva a
  marcarse no_show.

Ciclo de vida del previo (la automación solo toca lo que ella creó; los
manuales ligados al mismo turno no se tocan nunca):
- turno que deja de estar `confirmed` (cancelled/expired/completed/no_show)
  → su previo pendiente pasa a `cancelled` (trazabilidad, sin borrar).
- reprogramación → el previo PENDIENTE se mueve (nuevo `remind_at` y
  `automation_key`); si el nuevo `remind_at` ya pasó, se cancela.
- si el previo ya estaba completed/cancelled, no se revive: la
  reprogramación crea uno nuevo (otra key) solo si la regla está activa.
- cambio de Customer del turno → el pendiente pasa al nuevo Customer (o se
  cancela si el turno queda sin Customer).
- ya avisado (`notified_at`, CUSTOMER 07C) → evento consumido: la
  automación no lo vuelve a tocar (ni mover, ni cancelar, ni cambiar de
  Customer; tampoco se resetea `notified_at`). Queda `pending` hasta que una
  persona lo resuelva. Si después el turno se reprograma, el nuevo horario es
  un evento nuevo (otra key) y se crea otra instancia solo si la regla está
  activa y el nuevo `remind_at` es futuro.
Los switches gobiernan solo la CREACIÓN: un automático ya creado se sigue
moviendo/cancelando con su turno aunque la regla se apague después.

Best-effort: un error acá se loguea y NO revierte la operación del turno
(p.ej. un webhook de pago aprobado), gracias al savepoint.

Comunicaciones externas (CUSTOMER 07D.4A): en la misma pasada se cancelan los
`CustomerMessageDelivery` todavía no enviados que dejaron de corresponder al
turno (`customers.reminder_deliveries.cancel_stale_appointment_deliveries`).
"""
from __future__ import annotations

import datetime as dt
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from apps.customers.models import CustomerReminder, CustomerReminderAutomationSettings

from ..models import Appointment
from .availability import resolve_business_timezone

logger = logging.getLogger(__name__)

Source = CustomerReminder.Source
RStatus = CustomerReminder.Status
AStatus = Appointment.Status

UPCOMING_TITLE = 'Confirmar turno de {name}'
NO_SHOW_TITLE = 'Contactar por inasistencia'


def upcoming_key(appointment: Appointment) -> str:
  start = appointment.start_at.astimezone(dt.timezone.utc).strftime('%Y%m%dT%H%MZ')
  return f'{Source.APPOINTMENT_UPCOMING}:{appointment.pk}:{start}'


def no_show_key(appointment: Appointment) -> str:
  return f'{Source.NO_SHOW_FOLLOWUP}:{appointment.pk}'


def _local_when(appointment: Appointment) -> str:
  local = appointment.start_at.astimezone(resolve_business_timezone(appointment.business))
  return local.strftime('%d/%m/%Y %H:%M')


def _upcoming_title(customer) -> str:
  return UPCOMING_TITLE.format(name=customer.name)[: CustomerReminder.TITLE_MAX_LENGTH]


def _upcoming_description(appointment: Appointment) -> str:
  return f'Turno de {appointment.service_name} el {_local_when(appointment)}. Recordatorio automático interno.'


def _cancel(reminders) -> None:
  for reminder in reminders:
    reminder.status = RStatus.CANCELLED
    reminder.save(update_fields=['status', 'updated_at'])


def _create(**fields) -> CustomerReminder | None:
  """INSERT idempotente: si la key ya existe (carrera/reintento) no hace nada."""
  if CustomerReminder.objects.filter(business_id=fields['business'].pk, automation_key=fields['automation_key']).exists():
    return None
  try:
    with transaction.atomic():
      return CustomerReminder.objects.create(**fields)
  except IntegrityError:
    return None


def reconcile_appointment_reminders(appointment: Appointment, *, previous_status: str | None = None, now=None) -> None:
  """Lleva los recordatorios automáticos del turno a su estado deseado. Idempotente."""
  now = now or dj_timezone.now()
  try:
    with transaction.atomic():
      settings = CustomerReminderAutomationSettings.for_business(appointment.business)
      _reconcile_upcoming(appointment, settings, now)
      if previous_status is not None and previous_status != AStatus.NO_SHOW and appointment.status == AStatus.NO_SHOW:
        _create_no_show_followup(appointment, settings, now)
  except Exception:  # noqa: BLE001 — nunca romper la mutación del turno por un recordatorio
    logger.exception('[ReminderAutomation] reconcile failed for appointment=%s', appointment.pk)
  # CUSTOMER 07D.4A: emails al cliente todavía no enviados de un turno que se
  # canceló/venció/reprogramó → cancelled. Savepoint propio: independiente de
  # los recordatorios (incluidos los ya avisados, que la reconciliación no toca).
  try:
    with transaction.atomic():
      from apps.customers.reminder_deliveries import cancel_stale_appointment_deliveries

      cancel_stale_appointment_deliveries(appointment, now=now)
  except Exception:  # noqa: BLE001 — idem: nunca romper la mutación del turno
    logger.exception('[ReminderAutomation] delivery cancel failed for appointment=%s', appointment.pk)


def _reconcile_upcoming(appointment: Appointment, settings: CustomerReminderAutomationSettings, now) -> None:
  pending = list(
    CustomerReminder.objects.select_for_update()
    .filter(
      business_id=appointment.business_id, appointment=appointment, source=Source.APPOINTMENT_UPCOMING,
      status=RStatus.PENDING,
      # CUSTOMER 07C: uno ya avisado es un evento consumido (ver docstring).
      notified_at__isnull=True,
    )
    .order_by('created_at', 'id')
  )

  # Turno que ya no está vigente: confirmar no aplica más.
  if appointment.status != AStatus.CONFIRMED:
    _cancel(pending)
    return

  customer = appointment.customer
  key = upcoming_key(appointment)
  current = next((r for r in pending if r.automation_key == key), None)

  if current is not None:
    # Mismo turno y horario (reproceso, edición de notas, ...): solo seguir al Customer.
    _cancel([r for r in pending if r is not current])
    if customer is None:
      _cancel([current])
    elif current.customer_id != customer.pk:
      current.customer = customer
      current.title = _upcoming_title(customer)
      current.save(update_fields=['customer', 'title', 'updated_at'])
    return

  remind_at = appointment.start_at - dt.timedelta(hours=settings.appointment_reminder_hours_before)

  if pending:
    # Reprogramado: mover el pendiente (no crear otro y dejar el viejo vivo).
    moving, rest = pending[0], pending[1:]
    _cancel(rest)
    key_taken = CustomerReminder.objects.filter(business_id=appointment.business_id, automation_key=key).exists()
    if customer is None or remind_at <= now or key_taken:
      # key_taken: volvió a un horario cuyo previo ya se cerró → no se revive.
      _cancel([moving])
      return
    moving.remind_at = remind_at
    moving.automation_key = key
    moving.customer = customer
    moving.title = _upcoming_title(customer)
    moving.description = _upcoming_description(appointment)
    moving.save(update_fields=['remind_at', 'automation_key', 'customer', 'title', 'description', 'updated_at'])
    return

  if not settings.appointment_reminder_enabled:
    return
  if customer is None or not customer.is_active:
    return
  if remind_at <= now:
    return  # dentro de la anticipación: nunca un recordatorio ya vencido
  _create(
    business=appointment.business,
    customer=customer,
    appointment=appointment,
    source=Source.APPOINTMENT_UPCOMING,
    automation_key=key,
    title=_upcoming_title(customer),
    description=_upcoming_description(appointment),
    remind_at=remind_at,
  )


def _create_no_show_followup(appointment: Appointment, settings: CustomerReminderAutomationSettings, now) -> None:
  if not settings.no_show_followup_enabled or appointment.customer_id is None:
    return
  _create(
    business=appointment.business,
    customer=appointment.customer,
    appointment=appointment,
    source=Source.NO_SHOW_FOLLOWUP,
    automation_key=no_show_key(appointment),
    title=NO_SHOW_TITLE,
    description=f'No asistió al turno de {appointment.service_name} del {_local_when(appointment)}.',
    remind_at=now + dt.timedelta(hours=settings.no_show_followup_delay_hours),
  )
