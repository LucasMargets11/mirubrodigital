"""Aplicación de un pago de Mercado Pago a `AppointmentPayment` / `Appointment` (Slice 6B).

Lo invoca el webhook `flow=appointment` (`apps.billing.payment_webhook`)
DESPUÉS de resolver el `AppointmentPayment` por `external_reference` y de
re-obtener el pago con el token del Business
(`merchant_payments.get_merchant_payment`). Este módulo no habla con
Mercado Pago ni conoce el lifecycle de `WebhookDelivery`: recibe el payload
autoritativo y devuelve un `ConfirmationOutcome` que el webhook traduce a
PROCESSED / IGNORED / DEAD_LETTER.

Validaciones del pago re-obtenido (antes de mutar nada)
------------------------------------------------------
- `external_reference` idéntica al intento local;
- `transaction_amount` == `AppointmentPayment.amount`, `currency_id` ==
  `currency`;
- `collector_id` == `mp_user_id` de la conexión del Business (si ambos
  existen): el pago fue cobrado por la cuenta del Business;
- `metadata.appointment_payment_id` (copiada de la Preference) == id local,
  si viene;
- el `provider_payment_id` no está asociado a otro `AppointmentPayment`
  (además, constraint única parcial `appointment_payment_unique_provider_payment`).
La respuesta de `GET /v1/payments/{id}` no documenta el id de la Preference,
así que `provider_preference_id` NO se valida contra el pago.

Estados de Mercado Pago → estado local
--------------------------------------
approved → APPROVED (aplicado) o REQUIRES_REVIEW (cobrado, no aplicable)
rejected → REJECTED · cancelled → CANCELLED
pending / in_process / authorized → PENDING (`authorized` = reservado sin
capturar: el dinero todavía no está cobrado)
in_mediation / refunded / charged_back / desconocido → solo se guarda
`provider_status` (sin transición: refunds/contracargos son otro slice).

Monotonicidad: los estados "cobrados" (`CAPTURED_STATUSES`) son absorbentes;
un webhook viejo o duplicado nunca los hace retroceder. Una misma
Preference puede generar varios pagos (el cliente reintenta con otra
tarjeta): un pago distinto no pisa un `pending` con un rechazo viejo, y un
segundo pago APROBADO para el mismo intento es un doble cobro
(`DUPLICATE_CAPTURE`, sin mutación, para revisión humana).

Confirmación del turno
----------------------
Todo dentro de una transacción, lockeando en el mismo orden que el resto
de Turnos: profesional (o Business si no hay profesional; ver
`booking.lock_professionals`) → `Appointment` → `AppointmentPayment`.
Así se serializa contra reservas nuevas (mismo lock), contra el checkout
(`Appointment` → `AppointmentPayment`) y contra otro webhook del mismo pago.
La expiración de holds (UPDATE por fila) también espera el lock del turno.

Un pago aprobado confirma el turno SOLO si:
- el turno está `pending_payment` (o `expired` por el vencimiento del hold);
- la fecha autoritativa `date_approved` de MP es <= `expires_at` (no la
  hora de llegada del webhook);
- ningún otro turno ocupa hoy el horario (`ensure_no_overlap`).
Si no, el pago queda REQUIRES_REVIEW (con `paid_at` y `review_reason`) y el
turno no se toca — salvo materializar `expired` si su hold ya venció.
Nunca se reabre un turno cancelado/completado/no_show.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime

from ..models import Appointment, AppointmentPayment
from . import notifications
from .booking import SlotOverlap, ensure_no_overlap, lock_professionals
from .reminder_automation import reconcile_appointment_reminders

logger = logging.getLogger(__name__)

Status = AppointmentPayment.Status
ReviewReason = AppointmentPayment.ReviewReason

# Estados reales de Mercado Pago (API de Payments) con transición local.
PROVIDER_STATUS_MAP = {
  'approved': Status.APPROVED,
  'rejected': Status.REJECTED,
  'cancelled': Status.CANCELLED,
  'pending': Status.PENDING,
  'in_process': Status.PENDING,
  'authorized': Status.PENDING,
}


class Result:
  APPLIED = 'applied'                      # pago aprobado + turno confirmado
  ALREADY_APPLIED = 'already_applied'      # webhook repetido, nada que hacer
  REQUIRES_REVIEW = 'requires_review'      # dinero cobrado, turno NO confirmado
  STATUS_RECORDED = 'status_recorded'      # pending / rejected / cancelled / informativo
  STALE = 'stale'                          # evento viejo u otro pago de la misma Preference
  REF_MISMATCH = 'ref_mismatch'            # el pago no es de este intento
  FINANCIAL_MISMATCH = 'financial_mismatch'  # monto/moneda/cobrador/metadata no coinciden
  PAYMENT_ID_CONFLICT = 'payment_id_conflict'  # el pago de MP ya está asociado a otro intento
  DUPLICATE_CAPTURE = 'duplicate_capture'  # segundo pago aprobado para el mismo intento


@dataclass(frozen=True)
class ConfirmationOutcome:
  result: str
  # Código corto sin PII ni tokens (apto para WebhookDelivery.error_message).
  detail: str = ''


class ConcurrentAppointmentChange(Exception):
  """El turno cambió de profesional entre la lectura y el lock: reintentar."""


def parse_provider_datetime(value) -> dt.datetime | None:
  """ISO 8601 de MP (`2026-09-28T10:09:00.000-04:00`) → datetime aware en UTC.

  None si falta, no parsea o no trae offset: nunca se adivina la zona.
  """
  if not value or not isinstance(value, str):
    return None
  try:
    parsed = parse_datetime(value)
  except ValueError:
    return None
  if parsed is None or dj_timezone.is_naive(parsed):
    return None
  return parsed.astimezone(dt.timezone.utc)


def _to_amount(value) -> Decimal | None:
  try:
    return Decimal(str(value)).quantize(Decimal('0.01'))
  except (InvalidOperation, TypeError, ValueError):
    return None


def validate_provider_payment(payment: AppointmentPayment, payment_data: dict, *, merchant_user_id: str | None) -> ConfirmationOutcome | None:
  """Chequeos que no requieren locks. None si el pago es consistente."""
  fetched_ref = payment_data.get('external_reference')
  if fetched_ref != payment.external_reference:
    return ConfirmationOutcome(Result.REF_MISMATCH, 'external_reference')

  if _to_amount(payment_data.get('transaction_amount')) != payment.amount.quantize(Decimal('0.01')):
    return ConfirmationOutcome(Result.FINANCIAL_MISMATCH, 'amount')
  if payment_data.get('currency_id') != payment.currency:
    return ConfirmationOutcome(Result.FINANCIAL_MISMATCH, 'currency')

  collector_id = payment_data.get('collector_id')
  if merchant_user_id and collector_id is not None and str(collector_id) != str(merchant_user_id):
    return ConfirmationOutcome(Result.FINANCIAL_MISMATCH, 'collector')

  metadata = payment_data.get('metadata')
  if isinstance(metadata, dict) and metadata.get('appointment_payment_id') not in (None, ''):
    if str(metadata['appointment_payment_id']) != str(payment.pk):
      return ConfirmationOutcome(Result.FINANCIAL_MISMATCH, 'metadata')
  return None


def apply_provider_payment(*, appointment_payment_id, provider_payment_id, payment_data: dict) -> ConfirmationOutcome:
  """Aplica el estado autoritativo de un pago de MP ya validado.

  Lanza `ConcurrentAppointmentChange` (transitorio) si el turno se movió de
  profesional mientras se tomaban los locks.
  """
  provider_payment_id = str(provider_payment_id)
  provider_status = str(payment_data.get('status') or '')[:32]

  snapshot = (
    AppointmentPayment.objects.select_related('appointment__professional', 'business')
    .get(pk=appointment_payment_id)
  )
  professional = snapshot.appointment.professional

  try:
    with transaction.atomic():
      lock_professionals(snapshot.business, {professional})
      appointment = Appointment.objects.select_for_update().get(pk=snapshot.appointment_id)
      if appointment.professional_id != (professional.id if professional else None):
        raise ConcurrentAppointmentChange()
      payment = AppointmentPayment.objects.select_for_update().get(pk=snapshot.pk)

      if (
        AppointmentPayment.objects.filter(provider=payment.provider, provider_payment_id=provider_payment_id)
        .exclude(pk=payment.pk).exists()
      ):
        return ConfirmationOutcome(Result.PAYMENT_ID_CONFLICT, 'provider_payment_id')

      outcome = _apply_locked(
        payment=payment, appointment=appointment,
        provider_payment_id=provider_payment_id, provider_status=provider_status, payment_data=payment_data,
      )
      # Slice 6D: registradas dentro del atomic → corren solo si commitea
      # (y se descartan si hace rollback). Ver `services.notifications`.
      if outcome.result == Result.APPLIED:
        notifications.schedule_appointment_confirmed(appointment.pk)
      elif outcome.result == Result.REQUIRES_REVIEW:
        notifications.schedule_appointment_payment_review(payment.pk)
  except IntegrityError:
    # La constraint única atrapó una asociación concurrente del mismo pago.
    return ConfirmationOutcome(Result.PAYMENT_ID_CONFLICT, 'provider_payment_id')

  logger.info(
    '[AppointmentPayment] payment=%s provider_payment_id=%s provider_status=%s result=%s detail=%s',
    snapshot.pk, provider_payment_id, provider_status or '-', outcome.result, outcome.detail or '-',
  )
  return outcome


def _save(payment: AppointmentPayment, **fields) -> None:
  # Un IntegrityError (constraint única del pago) aborta TODA la transacción
  # externa, incluida una eventual confirmación del turno.
  for name, value in fields.items():
    setattr(payment, name, value)
  payment.save(update_fields=[*fields, 'updated_at'])


def _apply_locked(*, payment, appointment, provider_payment_id, provider_status, payment_data) -> ConfirmationOutcome:
  mapped = PROVIDER_STATUS_MAP.get(provider_status)

  # ── Dinero ya cobrado: estado absorbente ───────────────────────────────
  if payment.status in AppointmentPayment.CAPTURED_STATUSES:
    if payment.provider_payment_id == provider_payment_id:
      if mapped is None and provider_status and provider_status != payment.provider_status:
        # `refunded`/`charged_back`/`in_mediation` posteriores: se registra
        # el valor real. Nunca un estado previo (pending/...) de un evento viejo.
        _save(payment, provider_status=provider_status)
      return ConfirmationOutcome(Result.ALREADY_APPLIED)
    if mapped == Status.APPROVED:
      logger.error(
        '[AppointmentPayment] payment=%s: second approved provider payment %s (already captured by %s)',
        payment.pk, provider_payment_id, payment.provider_payment_id,
      )
      return ConfirmationOutcome(Result.DUPLICATE_CAPTURE, 'second_approved_payment')
    return ConfirmationOutcome(Result.STALE, 'other_provider_payment')

  other_payment = bool(payment.provider_payment_id) and payment.provider_payment_id != provider_payment_id

  # ── Estados informativos (mediación, devolución, ...) ──────────────────
  if mapped is None:
    if other_payment:
      return ConfirmationOutcome(Result.STALE, 'other_provider_payment')
    _save(payment, provider_payment_id=provider_payment_id, provider_status=provider_status)
    return ConfirmationOutcome(Result.STATUS_RECORDED, f'unmapped:{provider_status or "-"}'[:64])

  # ── pending / rejected / cancelled ─────────────────────────────────────
  if mapped != Status.APPROVED:
    if other_payment and not (
      mapped == Status.PENDING and payment.status in (Status.REJECTED, Status.CANCELLED)
    ):
      # Un rechazo viejo de otro pago nunca pisa un intento en curso.
      return ConfirmationOutcome(Result.STALE, 'other_provider_payment')
    fields = {'provider_payment_id': provider_payment_id, 'provider_status': provider_status}
    if payment.status != mapped:
      fields['status'] = mapped
    _save(payment, **fields)
    return ConfirmationOutcome(Result.STATUS_RECORDED, mapped)

  # ── approved ───────────────────────────────────────────────────────────
  paid_at = parse_provider_datetime(payment_data.get('date_approved'))
  review_reason = _review_reason(appointment=appointment, paid_at=paid_at)

  if review_reason is None:
    appointment.status = Appointment.Status.CONFIRMED
    appointment.expires_at = None
    appointment.save(update_fields=['status', 'expires_at', 'updated_at'])
    # CUSTOMER 07B: recién confirmado → recordatorio previo si aplica (idempotente, best-effort).
    reconcile_appointment_reminders(appointment)
    _save(
      payment, status=Status.APPROVED, provider_payment_id=provider_payment_id,
      provider_status=provider_status, paid_at=paid_at, review_reason='',
    )
    return ConfirmationOutcome(Result.APPLIED)

  # Pago cobrado pero no aplicable: el turno no se confirma. Si su hold ya
  # venció se materializa `expired` (mismo criterio que el checkout); el
  # `expires_at` se conserva como evidencia.
  if (
    appointment.status == Appointment.Status.PENDING_PAYMENT
    and appointment.effective_status() == Appointment.Status.EXPIRED
  ):
    appointment.status = Appointment.Status.EXPIRED
    appointment.save(update_fields=['status', 'updated_at'])
    reconcile_appointment_reminders(appointment)
  _save(
    payment, status=Status.REQUIRES_REVIEW, provider_payment_id=provider_payment_id,
    provider_status=provider_status, paid_at=paid_at, review_reason=review_reason,
  )
  logger.warning(
    '[AppointmentPayment] payment=%s approved but NOT applied: reason=%s appointment_status=%s',
    payment.pk, review_reason, appointment.status,
  )
  return ConfirmationOutcome(Result.REQUIRES_REVIEW, review_reason)


def _review_reason(*, appointment: Appointment, paid_at) -> str | None:
  """None si el turno puede confirmarse con este pago; si no, el motivo."""
  if appointment.status == Appointment.Status.CONFIRMED:
    return ReviewReason.APPOINTMENT_ALREADY_CONFIRMED
  if appointment.status not in (Appointment.Status.PENDING_PAYMENT, Appointment.Status.EXPIRED):
    return ReviewReason.APPOINTMENT_NOT_PAYABLE
  if paid_at is None:
    return ReviewReason.APPROVAL_TIME_UNKNOWN
  # Ventana del hold juzgada con la fecha de aprobación de MP, no con la
  # hora de llegada del webhook (puede llegar tarde).
  if appointment.expires_at is None or paid_at > appointment.expires_at:
    return ReviewReason.APPROVED_AFTER_EXPIRY
  try:
    ensure_no_overlap(
      business=appointment.business, service=appointment.service, professional=appointment.professional,
      start_at=appointment.start_at, end_at=appointment.end_at, exclude_pk=appointment.pk,
    )
  except SlotOverlap:
    return ReviewReason.SLOT_CONFLICT
  return None
