"""Entregas externas al Customer (CUSTOMER 07D.2; SES real en 07D.3A).

    evento lógico → prepare_customer_delivery → (consent gate + destination
    snapshot + idempotency_key) → execute_delivery → provider (fake | SES) →
    sent / failed / skipped → reintento controlado → historial auditable.

Patrón de referencia: `billing/webhook_lifecycle.py` (claim corto con
`select_for_update(skip_locked)`, `attempts` como token de la escritura final,
backoff persistido en `next_retry_at`) + `reminder_dispatch.py` (fallos
aislados por fila, logs solo con ids). No se reutiliza `WebhookDelivery`
(financiero) ni `notifications.EmailDelivery` (emails transaccionales de la
plataforma: sin Customer, sin idempotencia, guarda el cuerpo renderizado).

Estados (`CustomerMessageDelivery.Status`):

    pending ──claim──▶ processing ──▶ sent (──▶ delivered, cuando un proveedor real lo informe)
       │                    └──────▶ failed (+ next_retry_at si es reintentable y quedan intentos)
       │                                └──claim (next_retry_at <= now)──▶ processing …
       └──▶ skipped   (al preparar o al ejecutar: regla de negocio, nunca error técnico)
    pending / failed con reintento ──▶ cancelled (cancel_delivery)

Garantías:
- Consentimiento re-validado con datos ACTUALES justo antes de enviar (dentro
  del claim, con el Delivery bloqueado): `automatic_channel_status` (= gate
  `can_contact_automatically`) y además que el destino usable actual sea
  EXACTAMENTE `destination_snapshot`. Si no → `skipped` con el motivo; nunca
  se cambia el destino del Delivery.
- Un solo `provider.send` por intento: el claim (lock + `processing` +
  `attempt_count += 1`) se commitea ANTES de llamar al proveedor; otro worker
  saltea la fila bloqueada o la ve `processing`. La escritura del resultado
  está condicionada a (status=processing, attempt_count=el del claim).
- At-most-once ante resultado desconocido: si el proveedor lanza una
  excepción o el worker muere durante el envío (`processing` vencido), el
  Delivery queda `failed` SIN reintento (`provider_exception` /
  `outcome_unknown`). Preferimos no enviar a mandar dos veces.
- `CustomerReminder.notified_at` (aviso interno 07C) NO se toca ni se usa.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from .contact_preferences import automatic_channel_status, consent_destination
from .delivery_providers import DeliveryMessage, DeliveryProvider, ProviderSendResult, get_provider
from .models import Customer, CustomerMessageDelivery

logger = logging.getLogger(__name__)

Delivery = CustomerMessageDelivery
Status = CustomerMessageDelivery.Status

SKIP_CUSTOMER_INACTIVE = 'customer_inactive'
# El destino usable actual es otro que el congelado en el Delivery (el cliente
# reconfirmó otro teléfono/email): no se envía al viejo ni se reescribe.
SKIP_DESTINATION_CHANGED = 'destination_changed'

FAILURE_PROVIDER_EXCEPTION = 'provider_exception'
FAILURE_OUTCOME_UNKNOWN = 'outcome_unknown'

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = (60, 300, 1800)
DEFAULT_PROCESSING_LEASE_SECONDS = 600
# Un `pending` recién creado se encola on_commit; el barrido solo lo toma
# pasado este margen (encolado perdido), para no competir con la task.
DEFAULT_PENDING_GRACE_SECONDS = 60
DEFAULT_BATCH_SIZE = 200

DEFAULT_TEMPLATE_BY_PURPOSE = {
  Delivery.Purpose.APPOINTMENT_REMINDER: Delivery.TemplateKey.APPOINTMENT_REMINDER_V1,
  Delivery.Purpose.NO_SHOW_FOLLOWUP: Delivery.TemplateKey.NO_SHOW_FOLLOWUP_V1,
}


class DeliveryPreparationError(ValueError):
  """Input inválido para preparar (tenant cruzado, canal/propósito desconocido,
  idempotency_key reutilizada para otra comunicación). Error de programación,
  no una regla de negocio: no se crea nada."""


# ── Política de reintentos (única fuente: settings.CUSTOMER_DELIVERY_*) ─────

def max_attempts() -> int:
  return max(1, int(getattr(settings, 'CUSTOMER_DELIVERY_MAX_ATTEMPTS', DEFAULT_MAX_ATTEMPTS)))


def retry_backoff_seconds() -> tuple[int, ...]:
  value = getattr(settings, 'CUSTOMER_DELIVERY_RETRY_BACKOFF_SECONDS', DEFAULT_RETRY_BACKOFF_SECONDS)
  return tuple(int(v) for v in value) or DEFAULT_RETRY_BACKOFF_SECONDS


def processing_lease() -> timedelta:
  return timedelta(seconds=int(getattr(settings, 'CUSTOMER_DELIVERY_PROCESSING_LEASE_SECONDS', DEFAULT_PROCESSING_LEASE_SECONDS)))


def compute_next_retry_at(attempt_count: int, now):
  """Espera tras el intento N (1-based): backoff[N-1], el último se repite."""
  backoff = retry_backoff_seconds()
  return now + timedelta(seconds=backoff[min(max(attempt_count, 1), len(backoff)) - 1])


# ── Helpers ──────────────────────────────────────────────────────────────────

def mask_destination(channel: str, value: str | None) -> str | None:
  """Destino parcialmente oculto para el historial (el backend no expone el completo)."""
  if not value:
    return None
  if channel == Delivery.Channel.EMAIL:
    local, sep, domain = value.partition('@')
    if not sep:
      return '•••'
    return f'{local[:1]}•••@{domain}'
  digits = ''.join(ch for ch in value if ch.isdigit())
  return f'•••• {digits[-4:]}' if digits else '••••'


def business_reply_to(business) -> str | None:
  """Reply-To = email operativo configurado explícitamente por el Business
  (`CustomerCommunicationSettings.reply_to_email`). Sin configurar → None (sin
  Reply-To). Nunca cae al email fiscal, del owner ni del Customer."""
  from django.core.exceptions import ValidationError
  from django.core.validators import validate_email

  from .models import CustomerCommunicationSettings

  email = (
    CustomerCommunicationSettings.objects.filter(business=business).values_list('reply_to_email', flat=True).first() or ''
  ).strip()
  if not email:
    return None
  try:
    validate_email(email)
  except ValidationError:
    return None
  return email


def build_delivery_context(customer: Customer, *, appointment=None, reminder=None) -> dict:
  """Snapshot mínimo para el render (`delivery_templates`): ids + los datos que
  muestra el mensaje. Sin teléfono/email del cliente (el destino va en
  `destination_snapshot`), sin objetos completos, sin secretos."""
  business = customer.business
  context = {
    'customer_id': str(customer.pk),
    'appointment_id': str(appointment.pk) if appointment is not None else None,
    'reminder_id': str(reminder.pk) if reminder is not None else None,
    'customer_name': customer.name,
    'business_name': business.name,
    'business_timezone': business.timezone,
    'business_reply_to': business_reply_to(business),
  }
  if appointment is not None:
    context['service_name'] = appointment.service_name
    context['appointment_start_at'] = appointment.start_at.isoformat()
  return context


def _validate_inputs(business, customer, channel, purpose, idempotency_key, appointment, reminder, template_key):
  if channel not in Delivery.Channel.values:
    raise DeliveryPreparationError(f'Unsupported channel: {channel}')
  if purpose not in Delivery.Purpose.values:
    raise DeliveryPreparationError(f'Unsupported purpose: {purpose}')
  if template_key is not None and template_key not in Delivery.TemplateKey.values:
    raise DeliveryPreparationError(f'Unsupported template_key: {template_key}')
  if not (idempotency_key or '').strip():
    raise DeliveryPreparationError('idempotency_key is required')
  if customer.business_id != business.pk:
    raise DeliveryPreparationError('Customer belongs to another business')
  if appointment is not None:
    if appointment.business_id != business.pk:
      raise DeliveryPreparationError('Appointment belongs to another business')
    if appointment.customer_id is not None and appointment.customer_id != customer.pk:
      raise DeliveryPreparationError('Appointment belongs to another customer')
  if reminder is not None and (reminder.business_id != business.pk or reminder.customer_id != customer.pk):
    raise DeliveryPreparationError('Reminder belongs to another customer')


def _check_same_communication(existing: Delivery, customer, channel, purpose) -> None:
  if (existing.customer_id, existing.channel, existing.purpose) != (customer.pk, channel, purpose):
    raise DeliveryPreparationError('idempotency_key already used for a different communication')


def _gate(customer: Customer, channel: str) -> tuple[str | None, str | None]:
  """(skip_reason, destino actual). skip_reason None = se puede enviar."""
  destination = consent_destination(customer, channel)
  if not customer.is_active:
    return SKIP_CUSTOMER_INACTIVE, destination
  status = automatic_channel_status(customer, channel)
  return (None if status['usable'] else status['reason']), destination


# ── Preparación ──────────────────────────────────────────────────────────────

def prepare_customer_delivery(
  *, business, customer: Customer, channel: str, purpose: str, idempotency_key: str,
  appointment=None, reminder=None, template_key: str | None = None, enqueue: bool = True, now=None,
) -> tuple[Delivery, bool]:
  """Crea (o devuelve, si la `idempotency_key` ya existe en el Business) el Delivery.

  Devuelve `(delivery, created)`. Si el canal no es usable AHORA, igual crea el
  Delivery como `skipped` con el motivo (auditoría de por qué una
  automatización no envió). Con `enqueue` un `pending` nuevo se encola
  on_commit (`customers.execute_delivery`).
  """
  idempotency_key = (idempotency_key or '').strip()
  _validate_inputs(business, customer, channel, purpose, idempotency_key, appointment, reminder, template_key)

  existing = Delivery.objects.filter(business=business, idempotency_key=idempotency_key).first()
  if existing is not None:
    _check_same_communication(existing, customer, channel, purpose)
    return existing, False

  now = now or dj_timezone.now()
  skip_reason, destination = _gate(customer, channel)
  delivery = Delivery(
    business=business,
    customer=customer,
    appointment=appointment,
    reminder=reminder,
    channel=channel,
    purpose=purpose,
    template_key=template_key or DEFAULT_TEMPLATE_BY_PURPOSE.get(purpose),
    destination_snapshot=destination,
    idempotency_key=idempotency_key,
    context=build_delivery_context(customer, appointment=appointment, reminder=reminder),
  )
  if skip_reason is not None:
    delivery.status = Status.SKIPPED
    delivery.skip_reason = skip_reason
    delivery.skipped_at = now
  try:
    with transaction.atomic():
      delivery.save()
  except IntegrityError:
    # Otro proceso preparó la misma comunicación en paralelo: gana esa fila.
    existing = Delivery.objects.filter(business=business, idempotency_key=idempotency_key).first()
    if existing is None:
      raise
    _check_same_communication(existing, customer, channel, purpose)
    return existing, False

  logger.info(
    '[CustomerDelivery] prepared delivery=%s business=%s customer=%s channel=%s purpose=%s status=%s reason=%s',
    delivery.pk, business.pk, customer.pk, channel, purpose, delivery.status, delivery.skip_reason or '-',
  )
  if enqueue and delivery.status == Status.PENDING:
    from .tasks import execute_customer_delivery

    delivery_id = str(delivery.pk)
    transaction.on_commit(lambda: execute_customer_delivery.delay(delivery_id))
  return delivery, True


# ── Ejecución ────────────────────────────────────────────────────────────────

def _claim(delivery_id, provider_name: str, now):
  """Claim corto con el Delivery bloqueado. Devuelve el Delivery `processing`
  para enviar, o un str con el resultado si no hay que enviar."""
  with transaction.atomic():
    delivery = (
      Delivery.objects.select_for_update(skip_locked=True, of=('self',))
      .filter(pk=delivery_id)
      .first()
    )
    if delivery is None:
      return 'locked_or_missing'
    if delivery.status == Status.PENDING:
      pass
    elif delivery.status == Status.FAILED and delivery.next_retry_at is not None and delivery.next_retry_at <= now:
      if delivery.attempt_count >= max_attempts():  # p. ej. max bajado por config
        delivery.next_retry_at = None
        delivery.save(update_fields=['next_retry_at', 'updated_at'])
        return 'not_eligible'
    else:
      # processing (otro worker lo está enviando), final, o reintento no vencido.
      return 'not_eligible'

    customer = Customer.objects.select_related('business').get(pk=delivery.customer_id)
    if customer.business_id != delivery.business_id:  # invariante de save(); nunca cruzar tenants
      raise ValueError('CustomerMessageDelivery.customer belongs to another business')
    skip_reason, destination = _gate(customer, delivery.channel)
    if skip_reason is None and destination != delivery.destination_snapshot:
      skip_reason = SKIP_DESTINATION_CHANGED
    if skip_reason is not None:
      delivery.status = Status.SKIPPED
      delivery.skip_reason = skip_reason
      delivery.skipped_at = now
      delivery.next_retry_at = None
      delivery.save(update_fields=['status', 'skip_reason', 'skipped_at', 'next_retry_at', 'updated_at'])
      _log(delivery)
      return Status.SKIPPED

    delivery.status = Status.PROCESSING
    delivery.attempt_count += 1
    delivery.last_attempt_at = now
    delivery.next_retry_at = None
    delivery.provider = provider_name
    delivery.save(update_fields=['status', 'attempt_count', 'last_attempt_at', 'next_retry_at', 'provider', 'updated_at'])
  return delivery


def _guarded_update(delivery: Delivery, **fields) -> bool:
  """Persiste el resultado solo si este worker sigue dueño del intento."""
  fields['updated_at'] = dj_timezone.now()
  updated = Delivery.objects.filter(
    pk=delivery.pk, status=Status.PROCESSING, attempt_count=delivery.attempt_count,
  ).update(**fields)
  if not updated:
    logger.warning('[CustomerDelivery] attempt result discarded delivery=%s attempt=%s', delivery.pk, delivery.attempt_count)
    return False
  for key, value in fields.items():
    setattr(delivery, key, value)
  return True


def _failure_fields(delivery: Delivery, code: str, message: str | None, *, retryable: bool, now) -> dict:
  retry = retryable and delivery.attempt_count < max_attempts()
  return {
    'status': Status.FAILED,
    'failed_at': now,
    'failure_code': (code or 'provider_error')[:64],
    'failure_message': (message or '')[: Delivery.FAILURE_MESSAGE_MAX_LENGTH] or None,
    'next_retry_at': compute_next_retry_at(delivery.attempt_count, now) if retry else None,
  }


def _record_result(delivery: Delivery, result: ProviderSendResult) -> str | None:
  now = dj_timezone.now()
  if result.accepted:
    fields = {
      'status': Status.SENT,
      'sent_at': now,
      'provider_message_id': (result.provider_message_id or '')[:255] or None,
      'failure_code': None,
      'failure_message': None,
      'next_retry_at': None,
    }
  else:
    fields = _failure_fields(delivery, result.error_code, result.error_message, retryable=result.retryable, now=now)
  if not _guarded_update(delivery, **fields):
    return None
  _log(delivery)
  return delivery.status


def _message(delivery: Delivery) -> DeliveryMessage:
  return DeliveryMessage(
    delivery_id=str(delivery.pk),
    business_id=str(delivery.business_id),
    channel=delivery.channel,
    purpose=delivery.purpose,
    destination=delivery.destination_snapshot,
    idempotency_key=delivery.idempotency_key,
    template_key=delivery.template_key,
    context=dict(delivery.context or {}),
  )


def execute_delivery(delivery_id, *, provider: DeliveryProvider | None = None, now=None) -> str | None:
  """Ejecuta UN intento si el Delivery es elegible. Idempotente.

  Devuelve 'sent' | 'failed' | 'skipped', o None si no correspondía enviar
  (bloqueado por otro worker, ya procesado, reintento no vencido, sin fila).
  Nunca reenvía un Delivery `sent`/`processing`.
  """
  now = now or dj_timezone.now()
  channel = Delivery.objects.filter(pk=delivery_id).values_list('channel', flat=True).first()
  if channel is None:
    return None
  provider = provider or get_provider(channel)
  if provider.channel and provider.channel != channel:
    raise ValueError(f'Provider {provider.name} cannot send channel {channel}')

  claimed = _claim(delivery_id, provider.name, now)
  if isinstance(claimed, str):
    return Status.SKIPPED if claimed == Status.SKIPPED else None

  try:
    result = provider.send(_message(claimed))
  except Exception as exc:  # noqa: BLE001 — resultado desconocido: no reintentar (at-most-once)
    logger.exception('[CustomerDelivery] provider raised delivery=%s provider=%s', claimed.pk, provider.name)
    fields = _failure_fields(claimed, FAILURE_PROVIDER_EXCEPTION, type(exc).__name__, retryable=False, now=dj_timezone.now())
    if not _guarded_update(claimed, **fields):
      return None
    _log(claimed)
    return Status.FAILED
  return _record_result(claimed, result)


def cancel_delivery(delivery_id, *, now=None) -> bool:
  """Cancela un Delivery que todavía no salió (pending, o failed con reintento).
  Para futuras automatizaciones (p. ej. el turno se canceló). Idempotente."""
  now = now or dj_timezone.now()
  with transaction.atomic():
    delivery = Delivery.objects.select_for_update(of=('self',)).filter(pk=delivery_id).first()
    if delivery is None:
      return False
    cancellable = delivery.status == Status.PENDING or (
      delivery.status == Status.FAILED and delivery.next_retry_at is not None
    )
    if not cancellable:
      return False
    delivery.status = Status.CANCELLED
    delivery.cancelled_at = now
    delivery.next_retry_at = None
    delivery.save(update_fields=['status', 'cancelled_at', 'next_retry_at', 'updated_at'])
  _log(delivery)
  return True


# ── Barrido (Beat) ───────────────────────────────────────────────────────────

@dataclass
class SweepResult:
  stale: int = 0
  due: int = 0
  sent: int = 0
  failed: int = 0
  skipped: int = 0
  noop: int = 0
  errors: int = 0

  def as_dict(self) -> dict[str, int]:
    return dict(self.__dict__)


def _resolve_stale_processing(now, batch_size: int) -> int:
  """`processing` con el lease vencido = el worker murió durante el envío.
  No sabemos si el proveedor lo recibió → failed `outcome_unknown`, sin reintento."""
  cutoff = now - processing_lease()
  resolved = 0
  ids = list(
    Delivery.objects.filter(status=Status.PROCESSING, last_attempt_at__lte=cutoff)
    .order_by('last_attempt_at').values_list('id', flat=True)[:batch_size]
  )
  for delivery_id in ids:
    updated = Delivery.objects.filter(pk=delivery_id, status=Status.PROCESSING, last_attempt_at__lte=cutoff).update(
      status=Status.FAILED, failed_at=now, failure_code=FAILURE_OUTCOME_UNKNOWN,
      failure_message='Processing lease expired; provider outcome unknown', next_retry_at=None, updated_at=now,
    )
    if updated:
      resolved += 1
      logger.error('[CustomerDelivery] outcome unknown (lease expired) delivery=%s', delivery_id)
  return resolved


def retry_due_customer_deliveries(*, now=None, provider: DeliveryProvider | None = None, batch_size: int = DEFAULT_BATCH_SIZE) -> SweepResult:
  """Reintentos vencidos + pendientes cuyo encolado se perdió. Seguro en paralelo."""
  now = now or dj_timezone.now()
  result = SweepResult()
  result.stale = _resolve_stale_processing(now, batch_size)
  grace = timedelta(seconds=int(getattr(settings, 'CUSTOMER_DELIVERY_PENDING_GRACE_SECONDS', DEFAULT_PENDING_GRACE_SECONDS)))
  retry_ids = list(
    Delivery.objects.filter(status=Status.FAILED, next_retry_at__lte=now)
    .order_by('next_retry_at', 'id').values_list('id', flat=True)[:batch_size]
  )
  pending_ids = list(
    Delivery.objects.filter(status=Status.PENDING, created_at__lte=now - grace)
    .order_by('created_at', 'id').values_list('id', flat=True)[:batch_size]
  )
  ids = retry_ids + pending_ids
  result.due = len(ids)
  level = logging.INFO if (result.due or result.stale) else logging.DEBUG
  logger.log(level, '[CustomerDelivery] sweep started due=%d stale=%d', result.due, result.stale)
  for delivery_id in ids:
    try:
      outcome = execute_delivery(delivery_id, provider=provider, now=now)
    except Exception:  # noqa: BLE001 — un Delivery roto no frena al resto
      result.errors += 1
      logger.exception('[CustomerDelivery] sweep error delivery=%s', delivery_id)
      continue
    if outcome == Status.SENT:
      result.sent += 1
    elif outcome == Status.FAILED:
      result.failed += 1
    elif outcome == Status.SKIPPED:
      result.skipped += 1
    else:
      result.noop += 1
  logger.log(level, '[CustomerDelivery] sweep finished %s', result.as_dict())
  return result


def _log(delivery: Delivery) -> None:
  level = logging.WARNING if delivery.status == Status.FAILED else logging.INFO
  logger.log(
    level,
    '[CustomerDelivery] delivery=%s business=%s channel=%s purpose=%s status=%s attempt=%s reason=%s failure=%s next_retry_at=%s',
    delivery.pk, delivery.business_id, delivery.channel, delivery.purpose, delivery.status, delivery.attempt_count,
    delivery.skip_reason or '-', delivery.failure_code or '-',
    delivery.next_retry_at.isoformat() if delivery.next_retry_at else '-',
  )
