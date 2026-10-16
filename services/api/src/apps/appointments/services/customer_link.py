"""Vínculo `Appointment` ↔ `Customer` canónico (Turnos CUSTOMER 01).

`Appointment.customer` es la identidad viva del cliente; `customer_name`,
`customer_phone` y `customer_email` siguen siendo snapshots históricos del
turno y nunca se leen del `Customer`.

Reglas de resolución (siempre dentro del `Business` del turno):

- clave: teléfono normalizado (`apps.customers.phone`), solo contra
  `Customer`s activos (`is_active=False` es la baja lógica del módulo);
- exactamente una coincidencia → se reutiliza, SIN modificarla (ni nombre,
  ni email, ni teléfono: una reserva pública no edita la ficha);
- ninguna → se crea un `Customer` mínimo (individual) con nombre/teléfono
  tal como se ingresaron y el email solo si ningún otro cliente activo del
  negocio lo usa (el módulo exige email único por negocio en su API);
- varias (duplicados legacy) → no se vincula (`None`), no se fusiona nada;
- teléfono vacío o no normalizable → no se vincula (`None`): nunca se
  deduplica por nombre ni por email solo.

Concurrencia: los callers ya lockean la fila del `Business`
(`booking.lock_professionals`) antes de llamar, así que dos turnos del mismo
negocio no pueden crear el mismo `Customer` en paralelo.
"""
from __future__ import annotations

from apps.business.models import Business
from apps.customers.models import Customer
from apps.customers.phone import filter_by_phone_key, normalize_phone_for_matching


def resolve_customer_for_appointment(
  *, business: Business, customer_name: str, customer_phone: str, customer_email: str = '',
) -> Customer | None:
  phone_key = normalize_phone_for_matching(customer_phone)
  if phone_key is None:
    return None

  active = Customer.objects.filter(business=business, is_active=True)
  matches = list(filter_by_phone_key(active, phone_key)[:2])
  if len(matches) == 1:
    return matches[0]
  if matches:
    return None

  email = (customer_email or '').strip()
  if email and active.filter(email__iexact=email).exists():
    email = ''
  return Customer.objects.create(
    business=business,
    name=customer_name.strip(),
    phone=customer_phone.strip(),
    email=email,
  )


def phone_identity_changed(old_phone: str, new_phone: str) -> bool:
  """True si el cambio de teléfono cambia la identidad (no solo el formato)."""
  old_key = normalize_phone_for_matching(old_phone)
  new_key = normalize_phone_for_matching(new_phone)
  if old_key is None and new_key is None:
    return old_phone.strip() != new_phone.strip()
  return old_key != new_key
