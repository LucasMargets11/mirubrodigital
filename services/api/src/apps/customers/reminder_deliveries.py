"""Recordatorio automático vencido → comunicación externa al Customer (CUSTOMER 07D.4A).

    CustomerReminder automático llega a remind_at
      → BusinessNotification interna + notified_at (07C, su propia transacción)
      → prepare_reminder_deliveries(reminder)  (best-effort, transacción aparte)
      → prepare_customer_delivery (consent gate + snapshot + idempotency, 07D.2)
      → execute_delivery (encolado on_commit; proveedor según entorno: fake por default)

Punto único: `prepare_reminder_deliveries`. Decide:
- source: solo `appointment_upcoming` y `no_show_followup`. Los manuales siguen
  siendo internos (nunca generan Delivery).
- Business: `CustomerCommunicationSettings.appointment_email_enabled` /
  `no_show_email_enabled` (apagados por defecto).
- canal: SOLO email (sin lógica de `preferred_channel`; WhatsApp todavía no).
- vigencia: el turno sigue siendo el evento del recordatorio (upcoming:
  `confirmed`, mismo horario que la `automation_key`, mismo Customer, todavía
  futuro; no-show: sigue `no_show`). Si no, no se prepara nada.
- consentimiento: lo resuelve `prepare_customer_delivery` → si el canal no es
  usable el Delivery se crea `skipped` con el motivo (auditoría).
- idempotency_key estable por (turno, recordatorio, canal): reprocesar (Beat,
  retry, recuperación) devuelve el mismo Delivery.

`CustomerReminder.notified_at` NO cambia de semántica: es solo el aviso
interno. Un recordatorio avisado puede tener su Delivery pending/sent/skipped.

Ciclo de vida (`cancel_stale_appointment_deliveries`, llamado desde la
reconciliación de Turnos con el turno bloqueado): un Delivery que todavía no
salió (pending / failed con reintento) cuyo turno se canceló, venció,
reprogramó o cambió de Customer pasa a `cancelled`. Nunca se reescribe su
destino/contexto: el nuevo horario genera otro recordatorio → otro Delivery
(otra key). sent/delivered/skipped/failed final no se tocan.
"""
from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone as dj_timezone

from .deliveries import cancel_delivery, prepare_customer_delivery
from .models import CustomerCommunicationSettings, CustomerMessageDelivery, CustomerReminder

logger = logging.getLogger(__name__)

Delivery = CustomerMessageDelivery
DStatus = Delivery.Status
Source = CustomerReminder.Source
EMAIL = Delivery.Channel.EMAIL

# source → (purpose, switch del Business, prefijo de la idempotency_key, template)
_RULES = {
  Source.APPOINTMENT_UPCOMING: (
    Delivery.Purpose.APPOINTMENT_REMINDER, 'appointment_email_enabled', 'appointment-reminder',
    Delivery.TemplateKey.APPOINTMENT_REMINDER_V1,
  ),
  Source.NO_SHOW_FOLLOWUP: (
    Delivery.Purpose.NO_SHOW_FOLLOWUP, 'no_show_email_enabled', 'no-show',
    Delivery.TemplateKey.NO_SHOW_FOLLOWUP_V1,
  ),
}

# Recuperación: si preparar falló justo después del aviso interno, el barrido
# lo reintenta mientras el aviso sea reciente (la idempotencia evita duplicar).
DEFAULT_RECOVERY_WINDOW_MINUTES = 60
DEFAULT_RECOVERY_BATCH_SIZE = 200


def delivery_idempotency_key(reminder: CustomerReminder, channel: str = EMAIL) -> str:
  """`appointment-reminder:<appt>:<reminder>:email` / `no-show:<appt>:<reminder>:email`."""
  _, _, prefix, _ = _RULES[reminder.source]
  return f'{prefix}:{reminder.appointment_id}:{reminder.pk}:{channel}'


def recovery_window() -> dt.timedelta:
  minutes = int(getattr(settings, 'CUSTOMER_REMINDER_DELIVERY_RECOVERY_MINUTES', DEFAULT_RECOVERY_WINDOW_MINUTES))
  return dt.timedelta(minutes=max(1, minutes))


def _stale_reason(reminder: CustomerReminder, appointment, now) -> str | None:
  """Por qué el turno ya no corresponde a este recordatorio (o None si sigue vigente)."""
  from apps.appointments.models import Appointment
  from apps.appointments.services.reminder_automation import upcoming_key

  if appointment.customer_id != reminder.customer_id:
    return 'customer_changed'
  if reminder.source == Source.APPOINTMENT_UPCOMING:
    if appointment.status != Appointment.Status.CONFIRMED:
      return f'appointment_{appointment.status}'
    if reminder.automation_key != upcoming_key(appointment):
      return 'appointment_rescheduled'
    if appointment.start_at <= now:
      return 'appointment_started'
  elif appointment.status != Appointment.Status.NO_SHOW:
    return f'appointment_{appointment.status}'
  return None


def prepare_reminder_deliveries(reminder: CustomerReminder, *, now=None, enqueue: bool = True) -> list[Delivery]:
  """Prepara la comunicación externa de un recordatorio automático vencido.

  Devuelve los Deliveries (nuevos o ya existentes por idempotencia); lista
  vacía si no corresponde ninguno (manual, regla apagada, turno ya no vigente).
  Las excepciones se propagan: el caller (`prepare_reminder_deliveries_safely`)
  las aísla del aviso interno.
  """
  rule = _RULES.get(reminder.source)
  if rule is None or reminder.appointment_id is None or reminder.status == CustomerReminder.Status.CANCELLED:
    return []
  purpose, switch, _, template_key = rule
  communication = CustomerCommunicationSettings.for_business(reminder.business)
  if not getattr(communication, switch):
    return []

  now = now or dj_timezone.now()
  appointment = reminder.appointment
  reason = _stale_reason(reminder, appointment, now)
  if reason is not None:
    logger.debug('[ReminderDelivery] not prepared reminder=%s appointment=%s reason=%s', reminder.pk, appointment.pk, reason)
    return []

  delivery, created = prepare_customer_delivery(
    business=reminder.business, customer=reminder.customer, channel=EMAIL, purpose=purpose,
    idempotency_key=delivery_idempotency_key(reminder, EMAIL), appointment=appointment, reminder=reminder,
    template_key=template_key, enqueue=enqueue, now=now,
  )
  if created:
    logger.info(
      '[ReminderDelivery] prepared reminder=%s appointment=%s delivery=%s status=%s',
      reminder.pk, appointment.pk, delivery.pk, delivery.status,
    )
  return [delivery]


def prepare_reminder_deliveries_safely(reminder_id, *, now=None) -> list[Delivery]:
  """Wrapper best-effort: transacción propia, nunca propaga (el aviso interno ya
  se commiteó). Un fallo se loguea con ids y lo reintenta la recuperación."""
  try:
    with transaction.atomic():
      reminder = CustomerReminder.objects.select_related('business', 'customer', 'appointment').get(pk=reminder_id)
      return prepare_reminder_deliveries(reminder, now=now)
  except Exception:  # noqa: BLE001 — un error técnico acá no rompe el recordatorio ni la notificación
    logger.exception('[ReminderDelivery] prepare failed reminder=%s', reminder_id)
    return []


def recover_missing_reminder_deliveries(*, now=None, batch_size: int = DEFAULT_RECOVERY_BATCH_SIZE) -> int:
  """Recordatorios automáticos avisados hace poco, con la regla encendida y sin
  Delivery de email: vuelve a intentar prepararlos. Idempotente y barato (Beat)."""
  now = now or dj_timezone.now()
  rule_enabled = Q()
  for source, (_, switch, _, _) in _RULES.items():
    rule_enabled |= Q(source=source, **{f'business__customer_communication_settings__{switch}': True})
  has_delivery = Delivery.objects.filter(reminder=OuterRef('pk'), channel=EMAIL)
  ids = list(
    CustomerReminder.objects.filter(
      rule_enabled,
      appointment__isnull=False,
      notified_at__isnull=False,
      notified_at__gte=now - recovery_window(),
      notified_at__lte=now,
    )
    .exclude(status=CustomerReminder.Status.CANCELLED)
    .filter(~Exists(has_delivery))
    .order_by('notified_at', 'id')
    .values_list('id', flat=True)[:batch_size]
  )
  prepared = 0
  for reminder_id in ids:
    if prepare_reminder_deliveries_safely(reminder_id, now=now):
      prepared += 1
  if prepared:
    logger.info('[ReminderDelivery] recovered=%d', prepared)
  return prepared


# ── Ciclo de vida del turno ──────────────────────────────────────────────────

def _parse(value) -> dt.datetime | None:
  try:
    return dt.datetime.fromisoformat(str(value))
  except (TypeError, ValueError):
    return None


def _delivery_stale_reason(delivery: Delivery, appointment) -> str | None:
  from apps.appointments.models import Appointment

  if delivery.customer_id != appointment.customer_id:
    return 'customer_changed'
  if delivery.purpose == Delivery.Purpose.APPOINTMENT_REMINDER:
    if appointment.status != Appointment.Status.CONFIRMED:
      return f'appointment_{appointment.status}'
    if _parse((delivery.context or {}).get('appointment_start_at')) != appointment.start_at:
      return 'appointment_rescheduled'
  elif delivery.purpose == Delivery.Purpose.NO_SHOW_FOLLOWUP and appointment.status != Appointment.Status.NO_SHOW:
    return f'appointment_{appointment.status}'
  return None


def cancel_stale_appointment_deliveries(appointment, *, now=None) -> int:
  """Cancela los Deliveries que todavía no salieron y ya no corresponden al turno.

  Solo pending y failed-con-reintento (`cancel_delivery` lo vuelve a chequear con
  la fila bloqueada); nunca sent/delivered/skipped/failed final ni processing.
  """
  now = now or dj_timezone.now()
  candidates = Delivery.objects.filter(business_id=appointment.business_id, appointment_id=appointment.pk).filter(
    Q(status=DStatus.PENDING) | Q(status=DStatus.FAILED, next_retry_at__isnull=False),
  )
  cancelled = 0
  for delivery in candidates:
    reason = _delivery_stale_reason(delivery, appointment)
    if reason is not None and cancel_delivery(delivery.pk, now=now):
      cancelled += 1
      logger.info(
        '[ReminderDelivery] cancelled delivery=%s appointment=%s reason=%s', delivery.pk, appointment.pk, reason,
      )
  return cancelled
