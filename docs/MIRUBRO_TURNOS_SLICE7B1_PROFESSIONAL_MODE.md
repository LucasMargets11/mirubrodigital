# MiRubro Turnos — Slice 7B.1: modo con / sin profesional

Elimina el carril ambiguo `Appointment.professional = null` para servicios que
tienen profesionales (bug de Slice 7A: mismo servicio y horario, una reserva
`null` + otra con profesional → ambas `201`, ambas confirmadas).

## Regla canónica (server-side)

`eligible_professionals(service)` = profesionales **activos**, del **mismo
Business** y **asignados** al servicio
(`services/availability.py::eligible_professionals`).

| Servicio | `professional` válido |
| --- | --- |
| sin profesionales elegibles | solo `null`; cualquier id se rechaza (no sería elegible) |
| con ≥ 1 profesional elegible | obligatorio y elegible; `null` se rechaza (`ProfessionalRequired`, campo `professional`) |

La regla vive en `resolve_professional_for_service` y se aplica en todo punto de
entrada, sin confiar en el frontend:

- `compute_availability` (availability pública e interna);
- `validate_slot_within_availability` → `booking.ensure_slot_available`, usado por
  la reserva pública, el alta manual del panel y toda reprogramación / cambio de
  servicio / cambio de profesional (`admin_mutation`), siempre contra el
  servicio **destino**;
- reactivación manual (`→ confirmed`) de un turno `null` cuyo servicio hoy tiene
  profesionales: rechazada salvo que el mismo PATCH asigne un profesional.

No se agregó un campo `requires_professional`: `GET .../professionals/?service=`
ya expresa la regla (`[]` ⇔ servicio sin profesionales).

## Compatibilidad legacy (sin migración de datos)

Pueden existir turnos históricos con `professional = null` en servicios que hoy
tienen profesionales. **No se migran, no se borran y no se les asigna un
profesional inventado.** Mientras su servicio tenga profesionales elegibles se
consideran *ambiguos* y ocupan **todo el negocio** en su intervalo
(`availability.conflicting_appointments`):

- slot de un profesional X: lo bloquean los turnos ocupantes de X **y** los
  turnos legacy `null` de servicios con profesionales;
- turno "del negocio" (servicio sin profesionales): lo bloquean los turnos `null`
  (igual que antes; incluye a los legacy);
- un legacy `null` que vuelve a ocupar (confirmación tardía por webhook 6B) se
  valida contra cualquier turno ocupante del negocio → `slot_conflict`.

"Ocupa" sigue definido únicamente por `AppointmentQuerySet.occupying()`
(`confirmed` o `pending_payment` con hold vigente; vencimiento dinámico).

La condición es dinámica: si a un servicio sin profesionales se le asigna uno,
sus turnos `null` existentes pasan a ser legacy y bloquean a todos los
profesionales. Si un servicio pierde todos sus profesionales, sus turnos `null`
vuelven a ser turnos normales del negocio.

El panel puede seguir editando datos del cliente o cancelando un legacy `null`;
reprogramarlo o reactivarlo exige asignarle un profesional.

## Locking

`booking.lock_professionals` ahora lockea **siempre** la fila `Business`
(después de los profesionales, orden fijo). Antes, la reserva `null` lockeaba
`Business` y la de un profesional solo su fila: dos carriles sin exclusión
mutua. Costo: las reservas de un mismo negocio se serializan (transacciones
cortas; aceptable para el volumen actual).

## Frontend `/t/[slug]`

- `200 + []` → servicio sin profesionales, sigue a fecha/horario.
- `200 + [...]` → selección de profesional obligatoria.
- 429 / 5xx / error de red / body que no es lista → "No pudimos cargar los
  profesionales." + **Reintentar**. Nunca se asume lista vacía ni se reserva con
  `professional = null`.
- Cambiar de servicio limpia el profesional y vuelve a resolver; respuestas
  tardías del servicio anterior se descartan.

## Tests

- `apps/appointments/tests/test_professional_mode.py` (PostgreSQL real,
  incluye concurrencia con threads y la reproducción del bug de 7A).
- `apps/web/src/app/t/[slug]/__tests__/turnos-flow-professionals.test.tsx`.
