"""Mutaciones internas (admin) de un `Appointment` existente (Slice 6B.1).

Única vía para que el panel modifique un turno ya creado: PATCH/PUT
(datos del cliente, reprogramación, cambio de profesional/servicio, cambio
manual de estado) y DELETE (cancelación lógica). Comparte el protocolo de
locking de `booking` y del webhook de pago (`payment_confirmation`):

  1. profesional(es) origen/destino, ordenados por PK, y siempre el
     `Business` (`booking.lock_professionals`);
  2. `Appointment` (`SELECT ... FOR UPDATE`);
  3. `AppointmentPayment`: nunca se modifica desde acá (solo se lee).

El profesional ORIGEN se conoce leyendo el turno sin lock; si después del
lock resulta que otro request lo movió de profesional, se reintenta con el
estado nuevo (acotado): nunca se trabaja con un lock que no cubre al
profesional actual.

Todas las reglas se evalúan contra el estado BLOQUEADO, no contra la
instancia que la vista leyó al inicio del request, y solo se escriben los
campos que realmente cambian (`update_fields`). Así un PATCH armado con un
formulario viejo no revierte un `confirmed` del webhook, no pisa el
`expires_at` que el webhook limpió ni un `expired` materializado por
`expire_appointment_holds`.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction

from apps.business.models import Business

from ..models import Appointment, AppointmentPayment
from .availability import service_requires_professional
from .booking import BookingError, ensure_no_overlap, ensure_slot_available, lock_professionals
from .customer_link import phone_identity_changed, resolve_customer_for_appointment
from .reminder_automation import reconcile_appointment_reminders

Status = Appointment.Status

# Estados que maneja el sistema (hold de seña / su vencimiento): el admin no
# puede llevar un turno a ellos a mano.
SYSTEM_MANAGED_STATUSES = frozenset({Status.PENDING_PAYMENT, Status.EXPIRED})

CUSTOMER_FIELDS = ('customer_name', 'customer_phone', 'customer_email', 'notes')

_MAX_LOCK_ATTEMPTS = 3


class _ProfessionalMoved(Exception):
  pass


def _run_locked(*, business: Business, appointment_id, target_professionals, fn):
  for _ in range(_MAX_LOCK_ATTEMPTS):
    snapshot = Appointment.objects.select_related('professional').get(pk=appointment_id, business=business)
    try:
      with transaction.atomic():
        lock_professionals(business, {snapshot.professional, *target_professionals})
        appointment = (
          Appointment.objects.select_for_update(of=('self',))
          .select_related('service', 'professional')
          .get(pk=appointment_id, business=business)
        )
        if appointment.professional_id != snapshot.professional_id:
          raise _ProfessionalMoved()
        return fn(appointment)
    except _ProfessionalMoved:
      continue
  raise BookingError('El turno fue modificado al mismo tiempo por otra operación. Volvé a intentar.', field='non_field_errors')


def has_financial_payment(appointment: Appointment) -> bool:
  """True si el turno tiene un intento de pago en curso o dinero cobrado."""
  return AppointmentPayment.objects.filter(
    appointment=appointment,
    status__in=(*AppointmentPayment.ACTIVE_STATUSES, *AppointmentPayment.CAPTURED_STATUSES),
  ).exists()


def update_appointment(*, business: Business, appointment_id, changes: dict) -> Appointment:
  """Aplica `changes` (claves de `AppointmentSerializer.validated_data`;
  `customer` es el `Customer` ya validado de `customer_id`).

  Lanza `BookingError` si la transición/reprogramación no es válida contra
  el estado actual.
  """
  targets = [changes['professional']] if changes.get('professional') is not None else []
  if 'professional' in changes and changes['professional'] is None:
    targets.append(None)  # destino "sin profesional" → lock del Business
  return _run_locked(
    business=business, appointment_id=appointment_id, target_professionals=targets,
    fn=lambda appointment: _apply_changes(appointment, changes),
  )


def cancel_appointment(*, business: Business, appointment_id) -> Appointment:
  """Cancelación lógica. Nunca toca `AppointmentPayment` (sin refund automático)."""
  return update_appointment(business=business, appointment_id=appointment_id, changes={'status': Status.CANCELLED})


def _apply_changes(appointment: Appointment, changes: dict) -> Appointment:
  update_fields: set[str] = set()
  previous_status = appointment.status

  # ── Estado ───────────────────────────────────────────────────────────
  new_status = appointment.status
  if 'status' in changes and changes['status'] != appointment.status:
    requested = changes['status']
    if requested in SYSTEM_MANAGED_STATUSES:
      raise BookingError(
        f'No se puede cambiar manualmente un turno a "{Status(requested).label}" '
        f'(estado actual: "{appointment.get_status_display()}").',
        field='status',
      )
    new_status = requested

  # ── Horario / profesional / servicio ────────────────────────────────
  service = changes.get('service', appointment.service)
  professional = changes['professional'] if 'professional' in changes else appointment.professional
  start_at = changes.get('start_at', appointment.start_at)

  service_changed = service.pk != appointment.service_id
  professional_changed = (professional.pk if professional else None) != appointment.professional_id
  start_changed = start_at != appointment.start_at
  slot_changed = service_changed or professional_changed or start_changed

  if service_changed and has_financial_payment(appointment):
    raise BookingError(
      'No se puede cambiar el servicio de un turno con un pago de seña en curso o cobrado.', field='service_id',
    )

  if slot_changed:
    # `ensure_slot_available` revalida la regla profesional/null (Slice
    # 7B.1) contra el servicio DESTINO: cambiar a un servicio con
    # profesionales exige elegir uno; a uno sin profesionales, soltarlo.
    duration = service.duration_minutes if service_changed else appointment.service_duration_minutes
    end_at = start_at + dt.timedelta(minutes=duration)
    ensure_slot_available(
      business=appointment.business, service=service, professional=professional, start_at=start_at, end_at=end_at,
    )
    ensure_no_overlap(
      business=appointment.business, service=service, professional=professional, start_at=start_at, end_at=end_at,
      exclude_pk=appointment.pk,
    )
    appointment.professional = professional
    appointment.start_at = start_at
    appointment.end_at = end_at
    update_fields |= {'professional', 'start_at', 'end_at'}
    if service_changed:
      # Nuevo snapshot solo si cambia el servicio (mover un turno no lo re-cotiza).
      appointment.service = service
      appointment.service_name = service.name
      appointment.service_duration_minutes = service.duration_minutes
      appointment.service_price = service.price
      appointment.deposit_type = service.deposit_type
      appointment.deposit_value = service.deposit_value
      update_fields |= {
        'service', 'service_name', 'service_duration_minutes', 'service_price', 'deposit_type', 'deposit_value',
      }

  if new_status != appointment.status:
    if new_status == Status.CONFIRMED:
      # Reactivar (cancelled/expired/... → confirmed) vuelve a ocupar el
      # horario: nunca sin revalidar solapamiento contra el estado actual.
      if not slot_changed:
        # Slice 7B.1: un turno legacy `professional=None` de un servicio que
        # hoy tiene profesionales no vuelve a ocupar sin asignarle uno.
        if appointment.professional_id is None and service_requires_professional(appointment.service):
          raise BookingError('Este servicio requiere elegir un profesional.', field='professional')
        ensure_no_overlap(
          business=appointment.business, service=appointment.service, professional=appointment.professional,
          start_at=appointment.start_at, end_at=appointment.end_at, exclude_pk=appointment.pk,
        )
      if appointment.expires_at is not None:
        appointment.expires_at = None
        update_fields.add('expires_at')
    appointment.status = new_status
    update_fields.add('status')

  # Turnos CUSTOMER 05: un `customer_id` explícito (CustomerPicker) es el
  # vínculo y gana sobre el teléfono: nunca se re-resuelve por teléfono.
  # El serializer ya validó mismo Business + activo (o el vínculo actual).
  explicit_customer = 'customer' in changes
  if explicit_customer and changes['customer'].pk != appointment.customer_id:
    # Contra el estado bloqueado: la excepción "conservar el vínculo actual"
    # del serializer se evaluó sobre la instancia sin lock.
    if not changes['customer'].is_active:
      raise BookingError('El cliente está dado de baja. Reactivalo desde su ficha o elegí otro.', field='customer_id')
    appointment.customer = changes['customer']
    update_fields.add('customer')

  # Turnos CUSTOMER 01: sin `customer_id`, solo un cambio de teléfono que
  # cambia la identidad (no solo el formato) re-resuelve el `Customer`,
  # dentro del mismo negocio y con los datos ya actualizados. Cambiar
  # nombre/email/notas, horario, profesional o servicio conserva el vínculo
  # (incluido un NULL legacy).
  rebind_customer = not explicit_customer and 'customer_phone' in changes and phone_identity_changed(
    appointment.customer_phone, changes['customer_phone'],
  )

  for field in CUSTOMER_FIELDS:
    if field in changes and getattr(appointment, field) != changes[field]:
      setattr(appointment, field, changes[field])
      update_fields.add(field)

  if rebind_customer:
    customer = resolve_customer_for_appointment(
      business=appointment.business,
      customer_name=appointment.customer_name,
      customer_phone=appointment.customer_phone,
      customer_email=appointment.customer_email,
    )
    if (customer.pk if customer else None) != appointment.customer_id:
      appointment.customer = customer
      update_fields.add('customer')

  if update_fields:
    appointment.save(update_fields=[*sorted(update_fields), 'updated_at'])
    # CUSTOMER 07B: mover/cancelar el previo automático y, en la primera
    # transición a `no_show`, crear el seguimiento. Mismo lock y transacción.
    reconcile_appointment_reminders(appointment, previous_status=previous_status)
  return appointment
