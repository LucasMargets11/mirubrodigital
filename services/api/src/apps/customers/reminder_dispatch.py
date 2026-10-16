"""Aviso interno de recordatorios vencidos (CUSTOMER 07C).

Cuando un `CustomerReminder` pendiente llega a `remind_at`, genera UNA
`BusinessNotification` (`customer_reminder_due`) para el equipo y marca
`notified_at`. Es solo interno: nunca WhatsApp, email ni SMS al cliente.

- Elegible: `status=pending`, `remind_at <= now`, `notified_at IS NULL`
  (manuales y automáticos por igual; no se filtra por `source`).
- El aviso NO completa el recordatorio: sigue `pending` (la ficha lo muestra
  "Vencido · Avisado") hasta que una persona lo complete o cancele.

Idempotencia (como máximo un aviso por recordatorio):
1. Cada recordatorio se procesa en su propia transacción, con la fila
   bloqueada `SELECT ... FOR UPDATE SKIP LOCKED` y re-chequeando la
   elegibilidad: dos workers/Beat duplicados nunca procesan la misma fila (el
   segundo la saltea o, tras el commit del primero, ya no la ve elegible).
2. La notificación y `notified_at` se escriben en esa MISMA transacción: si
   el worker muere antes del commit no queda ni el aviso ni la marca (se
   reintenta entero); nunca queda un aviso sin marca.
3. Red de seguridad: `dedupe_key = customer_reminder_due:<reminder_id>` con
   la constraint única (business, dedupe_key) de `BusinessNotification`.

Errores: un fallo en un recordatorio revierte solo su transacción (sin
`notified_at`, se reintenta en la próxima corrida de Beat) y no frena al
resto. Se loguea con ids; nunca teléfono, email ni texto del recordatorio.

Comunicación externa (CUSTOMER 07D.4A): DESPUÉS de commitear el aviso, en
otra transacción, `reminder_deliveries.prepare_reminder_deliveries_safely`
prepara el email al cliente si el Business lo activó. Un fallo ahí nunca
revierte el aviso interno; la recuperación del mismo barrido lo reintenta
(idempotency_key estable → nunca duplica).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.notifications.business_notifications import create_business_notification
from apps.notifications.models import BusinessNotification

from .models import CustomerReminder
from .reminder_deliveries import prepare_reminder_deliveries_safely, recover_missing_reminder_deliveries

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 500
MESSAGE_DESCRIPTION_MAX = 140
TITLE_PREFIX = 'Recordatorio: '


@dataclass
class DispatchResult:
  due: int = 0
  dispatched: int = 0
  skipped: int = 0
  failed: int = 0

  def as_dict(self) -> dict[str, int]:
    return {'due': self.due, 'dispatched': self.dispatched, 'skipped': self.skipped, 'failed': self.failed}


def dedupe_key(reminder: CustomerReminder) -> str:
  return f'{BusinessNotification.Kind.CUSTOMER_REMINDER_DUE}:{reminder.pk}'


def customer_action_url(reminder: CustomerReminder) -> str:
  return f'/app/clientes/{reminder.customer_id}'


def _eligible(now):
  return CustomerReminder.objects.filter(
    status=CustomerReminder.Status.PENDING, remind_at__lte=now, notified_at__isnull=True,
  )


def _short(text: str, limit: int) -> str:
  text = ' '.join((text or '').split())
  return text if len(text) <= limit else text[: limit - 1].rstrip() + '…'


def build_message(reminder: CustomerReminder) -> str:
  description = _short(reminder.description, MESSAGE_DESCRIPTION_MAX)
  return f'{reminder.customer.name}\n{description}' if description else reminder.customer.name


def _notify(reminder: CustomerReminder) -> bool:
  _, created = create_business_notification(
    business_id=reminder.business_id,
    kind=BusinessNotification.Kind.CUSTOMER_REMINDER_DUE,
    dedupe_key=dedupe_key(reminder),
    title=f'{TITLE_PREFIX}{reminder.title}',
    message=build_message(reminder),
    severity=BusinessNotification.Severity.INFO,
    action_url=customer_action_url(reminder),
    related_object_type='customer_reminder',
    related_object_id=str(reminder.pk),
    metadata={
      'reminder_id': str(reminder.pk),
      'customer_id': str(reminder.customer_id),
      'appointment_id': str(reminder.appointment_id) if reminder.appointment_id else None,
      'reminder_source': reminder.source,
      'remind_at': reminder.remind_at.isoformat(),
    },
  )
  return created


def dispatch_reminder(reminder_id, *, now=None) -> str:
  """Avisa UN recordatorio si sigue elegible. Devuelve 'dispatched' | 'skipped'.

  Las excepciones se propagan (el caller las aísla); la transacción revierte
  aviso y marca juntos.
  """
  now = now or dj_timezone.now()
  with transaction.atomic():
    reminder = (
      _eligible(now)
      .select_for_update(skip_locked=True, of=('self',))
      .select_related('customer')
      .filter(pk=reminder_id)
      .first()
    )
    if reminder is None:
      # Otro worker lo tiene bloqueado, ya fue avisado, o dejó de estar
      # pendiente/vencido entre la búsqueda y el bloqueo.
      return 'skipped'
    if reminder.customer.business_id != reminder.business_id:  # invariante de save(); nunca cruzar tenants
      raise ValueError('CustomerReminder.customer belongs to another business')
    created = _notify(reminder)
    # `.update` y no `save()`: no toca `updated_at` (el aviso no es una edición).
    CustomerReminder.objects.filter(pk=reminder.pk).update(notified_at=now)
  if not created:
    logger.warning('[ReminderDispatch] notification already existed reminder=%s', reminder_id)
  # CUSTOMER 07D.4A: fuera de la transacción del aviso; nunca propaga.
  if reminder.source != CustomerReminder.Source.MANUAL:
    prepare_reminder_deliveries_safely(reminder.pk, now=now)
  return 'dispatched'


def dispatch_due_customer_reminders(*, now=None, batch_size: int = DEFAULT_BATCH_SIZE) -> DispatchResult:
  """Barre los recordatorios vencidos sin avisar. Seguro de correr en paralelo/repetido."""
  now = now or dj_timezone.now()
  result = DispatchResult()
  ids = list(_eligible(now).order_by('remind_at', 'id').values_list('id', flat=True)[:batch_size])
  result.due = len(ids)
  # Corre cada minuto: sin trabajo, solo debug para no inundar el log.
  level = logging.INFO if result.due else logging.DEBUG
  logger.log(level, '[ReminderDispatch] started due=%d', result.due)
  for reminder_id in ids:
    try:
      outcome = dispatch_reminder(reminder_id, now=now)
    except Exception:  # noqa: BLE001 — aislar el fallo: el resto se procesa igual
      result.failed += 1
      logger.exception('[ReminderDispatch] failed reminder=%s', reminder_id)
      continue
    if outcome == 'dispatched':
      result.dispatched += 1
      logger.info('[ReminderDispatch] dispatched reminder=%s', reminder_id)
    else:
      result.skipped += 1
  logger.log(
    level,
    '[ReminderDispatch] finished due=%d dispatched=%d skipped=%d failed=%d',
    result.due, result.dispatched, result.skipped, result.failed,
  )
  # CUSTOMER 07D.4A: avisos recientes cuya preparación de Delivery falló.
  try:
    recover_missing_reminder_deliveries(now=now)
  except Exception:  # noqa: BLE001 — la recuperación nunca rompe el barrido de avisos
    logger.exception('[ReminderDispatch] delivery recovery failed')
  return result
