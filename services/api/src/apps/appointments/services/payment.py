"""Inicio de checkout de seña con Mercado Pago (Slice 6A).

`Appointment(pending_payment)` → `AppointmentPayment(creating)` →
Preference en la cuenta MP del Business → `AppointmentPayment(pending)` +
`checkout_url`. El turno sigue `pending_payment` hasta que el webhook
`flow=appointment` lo confirma (Slice 6B, ver `services.payment_confirmation`).

Todo se deriva server-side a partir de `slug` + `public_token`: monto
(snapshot del turno), moneda, `external_reference`, URLs.

Estrategia contra Preferences duplicadas
----------------------------------------
Mercado Pago no documenta idempotencia para `POST /checkout/preferences`,
así que no se depende de ella:

1. Transacción corta con `SELECT ... FOR UPDATE` sobre el `Appointment`:
   valida, y reserva el intento insertando un `AppointmentPayment` en
   `creating`. La constraint parcial `appointment_payment_single_active`
   (PostgreSQL) garantiza un único intento activo por turno aun si el lock
   se saltease. Requests concurrentes esperan el lock y, al entrar, ven el
   intento activo: reusan el `pending` o reciben 409 si sigue `creating`.
2. La llamada a MP ocurre FUERA de la transacción (no se retiene el lock
   durante I/O de red), sin reintentos automáticos del SDK.
3. Resultado:
   - creado        → `pending` + preference id + checkout_url;
   - rechazo seguro → `error` (terminal; se puede volver a intentar);
   - incierto       → `uncertain`, que sigue siendo "activo": bloquea
     nuevos intentos para ese turno. Nunca se recrea automáticamente.
   Si falla la persistencia local tras crear la Preference, la fila queda
   en `creating`, también bloqueante.

Recuperación de `uncertain`/`creating` colgado: buscar en MP (cuenta del
Business) `GET /checkout/preferences/search?external_reference=<ref>`; si
existe, completar `provider_preference_id`/`checkout_url` y pasar a
`pending`; si no existe, pasar a `error`. Mientras tanto el hold del turno
vence solo (10 min) y la Preference también (`expiration_date_to`).
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote, urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from apps.merchant_payments.services import (
  MerchantPaymentConnectionUnavailable,
  PreferenceOutcome,
  create_merchant_preference,
)

from ..models import APPOINTMENT_PAYMENT_CURRENCY, Appointment, AppointmentPayment
from .reminder_automation import reconcile_appointment_reminders

logger = logging.getLogger(__name__)

WEBHOOK_PATH = '/api/v1/billing/mercadopago/webhook'
WEBHOOK_FLOW = 'appointment'


class CheckoutError(Exception):
  """Error de negocio del checkout. `code` es estable y apto para el cliente."""

  def __init__(self, code: str, message: str):
    self.code = code
    self.message = message
    super().__init__(f'{code}: {message}')


@dataclass(frozen=True)
class CheckoutResult:
  payment: AppointmentPayment
  appointment: Appointment
  created: bool


def build_notification_url(external_reference: str) -> str | None:
  """URL del webhook con routing explícito (arquitectura 5B.2).

  Usa `BASE_PUBLIC_URL` (URL pública de la API), nunca una URL de frontend
  ni input del cliente. None si no está configurada.
  """
  api_public_url = getattr(settings, 'BASE_PUBLIC_URL', None)
  if not api_public_url:
    return None
  return f"{api_public_url.rstrip('/')}{WEBHOOK_PATH}?flow={WEBHOOK_FLOW}&ref={quote(external_reference)}"


def build_back_urls(*, slug: str, public_token) -> dict:
  """Back URLs hacia la página pública `/t/<slug>` del frontend canónico.

  Solo llevan el `public_token` opaco de la reserva y el resultado; sin PII.
  La pantalla de resultado final queda para un slice posterior.
  """
  base = (getattr(settings, 'FRONTEND_URL', None) or 'http://localhost:3000').rstrip('/')
  page = f'{base}/t/{quote(slug)}'
  return {
    result: f'{page}?{urlencode({"booking": str(public_token), "payment": result})}'
    for result in ('success', 'pending', 'failure')
  }


def _reserve_attempt(*, business, public_token) -> tuple[Appointment, AppointmentPayment, bool]:
  """Fase 1 (transacción + lock). Devuelve (appointment, payment, created).

  Lanza CheckoutError. El caso "hold vencido" se normaliza a `expired`
  dentro de la transacción y se reporta después, para que ese UPDATE sí se
  confirme.
  """
  with transaction.atomic():
    try:
      appointment = Appointment.objects.select_for_update().get(business=business, public_token=public_token)
    except Appointment.DoesNotExist:
      raise CheckoutError('not_found', 'Reserva no encontrada.') from None

    now = dj_timezone.now()
    if appointment.source != Appointment.Source.PUBLIC:
      raise CheckoutError('not_payable', 'Esta reserva no admite pago online.')

    if (
      appointment.status == Appointment.Status.PENDING_PAYMENT
      and appointment.effective_status(now=now) == Appointment.Status.EXPIRED
    ):
      appointment.status = Appointment.Status.EXPIRED
      appointment.save(update_fields=['status', 'updated_at'])
      reconcile_appointment_reminders(appointment)
    elif appointment.status != Appointment.Status.PENDING_PAYMENT:
      raise CheckoutError('not_payable', 'Esta reserva no está pendiente de pago.')
    else:
      amount = appointment.deposit_amount
      if amount <= Decimal('0'):
        raise CheckoutError('not_payable', 'Esta reserva no requiere seña.')

      active = (
        AppointmentPayment.objects.select_for_update()
        .filter(appointment=appointment, status__in=AppointmentPayment.ACTIVE_STATUSES)
        .first()
      )
      if active is not None:
        if (
          active.status == AppointmentPayment.Status.PENDING
          and active.checkout_url
          and active.amount == amount
        ):
          return appointment, active, False
        raise CheckoutError('payment_in_progress', 'Ya hay un intento de pago en curso para esta reserva.')

      payment_id = uuid.uuid4()
      try:
        with transaction.atomic():
          payment = AppointmentPayment.objects.create(
            id=payment_id,
            business=business,
            appointment=appointment,
            external_reference=AppointmentPayment.build_external_reference(payment_id),
            amount=amount,
            currency=APPOINTMENT_PAYMENT_CURRENCY,
            status=AppointmentPayment.Status.CREATING,
          )
      except IntegrityError:
        # Defensa en profundidad: la constraint parcial atrapó un intento
        # activo concurrente que el lock no serializó.
        raise CheckoutError('payment_in_progress', 'Ya hay un intento de pago en curso para esta reserva.') from None
      return appointment, payment, True

  # Solo se llega acá si el hold venció (UPDATE a `expired` ya confirmado).
  raise CheckoutError('expired', 'La reserva venció. Volvé a elegir un horario.')


def _build_preference_data(*, business, appointment: Appointment, payment: AppointmentPayment, notification_url: str) -> dict:
  # `from` con margen hacia atrás: tolera desfasaje de reloj con MP.
  valid_from = dj_timezone.now() - dt.timedelta(minutes=5)
  return {
    'items': [{
      'id': str(payment.id),
      'title': f'Seña - {appointment.service_name}'[:256],
      'quantity': 1,
      'unit_price': float(payment.amount),
      'currency_id': payment.currency,
    }],
    'external_reference': payment.external_reference,
    'notification_url': notification_url,
    'back_urls': build_back_urls(slug=business.slug, public_token=appointment.public_token),
    'auto_return': 'approved',
    # La Preference no debe poder pagarse después de que venza el hold.
    'expires': True,
    'expiration_date_from': valid_from.isoformat(timespec='milliseconds'),
    'expiration_date_to': appointment.expires_at.isoformat(timespec='milliseconds'),
    # Medios offline (efectivo/cajero) se acreditan horas/días después: no
    # compatibles con un hold de minutos.
    'payment_methods': {
      'excluded_payment_types': [{'id': 'ticket'}, {'id': 'atm'}],
    },
    # Sin PII del cliente final: solo ids internos opacos.
    'metadata': {'appointment_payment_id': str(payment.id)},
  }


def _finalize(payment: AppointmentPayment, **fields) -> AppointmentPayment:
  """Transición desde `creating` (UPDATE condicional, sin retener locks)."""
  updated = AppointmentPayment.objects.filter(
    pk=payment.pk, status=AppointmentPayment.Status.CREATING,
  ).update(updated_at=dj_timezone.now(), **fields)
  if not updated:
    logger.error('[AppointmentCheckout] payment=%s left creating state unexpectedly', payment.pk)
  payment.refresh_from_db()
  return payment


def start_appointment_checkout(*, business, public_token) -> CheckoutResult:
  """Inicia (o reusa) el checkout de la seña de un turno público.

  `business` ya viene resuelto por slug (y validado como publicable con
  Turnos habilitado) por la vista. Lanza CheckoutError.
  """
  appointment, payment, created = _reserve_attempt(business=business, public_token=public_token)
  if not created:
    return CheckoutResult(payment=payment, appointment=appointment, created=False)

  notification_url = build_notification_url(payment.external_reference)
  if notification_url is None:
    # Sin notification_url el pago nunca podría confirmarse (Slice 6B):
    # no se crea una Preference huérfana.
    logger.error('[AppointmentCheckout] BASE_PUBLIC_URL not set — refusing to create preference')
    _finalize(payment, status=AppointmentPayment.Status.ERROR, failure_reason='notification_url_unavailable')
    raise CheckoutError('payment_unavailable', 'El pago online no está disponible en este momento.')

  preference_data = _build_preference_data(
    business=business, appointment=appointment, payment=payment, notification_url=notification_url,
  )

  try:
    result = create_merchant_preference(business, preference_data)
  except MerchantPaymentConnectionUnavailable as exc:
    # Antes de cualquier llamada remota: estado definitivo y seguro.
    logger.warning('[AppointmentCheckout] payment=%s: %s', payment.pk, exc.reason)
    _finalize(payment, status=AppointmentPayment.Status.ERROR, failure_reason='mp_not_connected')
    raise CheckoutError('payment_unavailable', 'Este negocio no tiene el pago online disponible.') from None

  if result.outcome == PreferenceOutcome.CREATED:
    payment = _finalize(
      payment,
      status=AppointmentPayment.Status.PENDING,
      provider_preference_id=result.preference_id,
      checkout_url=result.init_point,
    )
    return CheckoutResult(payment=payment, appointment=appointment, created=True)

  if result.outcome == PreferenceOutcome.REJECTED:
    _finalize(payment, status=AppointmentPayment.Status.ERROR, failure_reason=f'mp_rejected:{result.detail}'[:64])
    raise CheckoutError('payment_provider_error', 'No pudimos iniciar el pago. Intentá nuevamente.')

  _finalize(
    payment,
    status=AppointmentPayment.Status.UNCERTAIN,
    provider_preference_id=result.preference_id,
    failure_reason=f'mp_uncertain:{result.detail}'[:64],
  )
  raise CheckoutError(
    'payment_uncertain',
    'No pudimos confirmar el inicio del pago. No reintentes: contactá al negocio.',
  )
