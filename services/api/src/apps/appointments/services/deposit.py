"""Cálculo centralizado del monto de seña (Slice 4B).

Única fuente de verdad para traducir `(price, deposit_type, deposit_value)`
en el monto efectivo a cobrar. Usado tanto al crear una reserva pública
(`services.booking.create_public_appointment`) como al leer el estado de un
turno ya creado (`Appointment.deposit_amount`, sobre el snapshot guardado).

Redondeo: `ROUND_HALF_UP` a 2 decimales, igual que el resto de cálculos
monetarios del repo (ver `apps.sales.serializers`, `apps.billing.canonical_pricing`).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal('0.01')


def compute_deposit_amount(*, price: Decimal, deposit_type: str, deposit_value: Decimal) -> Decimal:
  if deposit_type == 'none':
    return Decimal('0.00')
  if deposit_type == 'fixed':
    return deposit_value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
  if deposit_type == 'percentage':
    amount = (price * deposit_value / Decimal('100'))
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
  raise ValueError(f'Tipo de seña desconocido: {deposit_type!r}')


def deposit_config_error(*, price: Decimal, deposit_type: str, deposit_value: Decimal | None) -> str | None:
  """Regla canónica de configuración de seña de un servicio (Slice 7C).

  Devuelve el mensaje de error (para `deposit_value`) o `None` si es válida.
  Compartida por `AppointmentServiceSerializer.validate` y
  `AppointmentService.clean` para que ambos caminos apliquen lo mismo.

  - `none`: el valor se ignora (el serializer lo fuerza a 0).
  - `fixed`: `0 < deposit_value <= price` (con `price=0` no hay seña fija posible).
  - `percentage`: `0 < deposit_value <= 100` y `price > 0` (si no, el monto es 0).

  Una seña que resulta en monto 0 dejaría la reserva en `pending_payment`
  imposible de pagar (checkout `not_payable`).
  """
  value = deposit_value if deposit_value is not None else Decimal('0')
  if deposit_type == 'none':
    return None
  if deposit_type == 'fixed':
    if value <= 0:
      return 'La seña fija debe ser mayor a 0.'
    if value > price:
      return 'La seña fija no puede superar el precio del servicio.'
    return None
  if deposit_type == 'percentage':
    if value <= 0 or value > 100:
      return 'El porcentaje de seña debe ser mayor a 0 y menor o igual a 100.'
    if price <= 0:
      return 'No se puede cobrar seña porcentual sobre un servicio con precio 0.'
    return None
  return f'Tipo de seña desconocido: {deposit_type!r}'
