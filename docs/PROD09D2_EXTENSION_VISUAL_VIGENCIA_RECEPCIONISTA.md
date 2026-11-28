# PROD-09D2 — Extensión visual de vigencia comercial de Recepcionista IA

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `0819c3a` · Bot
`de7e932` sin cambios. Solo frontend (`apps/web`). Sin endpoints, modelos,
migraciones ni dependencias nuevas.

## 1. Implementación

| Pieza | Archivo |
|---|---|
| Acción y modal | `components/admin/reception-validity-extension.tsx` → `ReceptionValidityExtension`, más `extendableReceptionSubscription` y `extensionFailure` |
| Montaje dentro de «Consumo comercial de IA» | `components/admin/admin-ai-usage-section.tsx`: props `businessName` y `canExtendValidity` |
| Llamada | `features/reception/api.ts` → `extendAdminReceptionSubscription` (`POST .../subscriptions/{id}/extension/`) |
| Tipos | `features/reception/types.ts` → `AdminSubscriptionExtension` y `AdminSubscriptionExtensionResponse` |
| Query key compartida | `features/reception/hooks.ts` → `adminAIUsageKey(businessId)`, la misma que usa `useAdminAIUsage` |
| Fecha AR | `lib/dates.ts` → `dateStringFromTimestampAR` |
| Rol | `app/admin/clientes/[clienteId]/page.tsx`: `getAdminSession()` en el servidor → `canExtendValidity`, el mismo patrón que `canCreateClient`. Se pasa por `ClienteDetailContent` y `ReceptionistAdminCard` |

## 2. Reglas

### Suscripción

- **Origen del id:** `source_subscription.id` de `GET .../ai-usage/`. Es la
  fuente comercial real del consumo, que el backend resuelve. Nunca se usa
  `client.subscription`, la suscripción principal del comercio.
- **Cuándo se muestra la acción:** solo para superadmin y cuando la fuente
  cumple todo esto:
  - `reception/reception`.
  - `provider=manual`.
  - `complimentary`.
  - `status=trialing`.
  - Sin baja programada.
  - Con la vigencia en curso (inicio ≤ ahora < fin).
- **Autoridad:** es solo una guía para mostrar la acción. El backend sigue
  decidiendo.

### Fechas

Se usa la misma semántica que el alta:
- Se envía `complimentary_end` como `"YYYY-MM-DD"`.
- El backend lo interpreta como 00:00 de ese día en
  `America/Argentina/Buenos_Aires`, con vencimiento exclusivo.
- No hay conversión a UTC en el navegador.

Para validar la fecha:
- El vencimiento actual se convierte a su día calendario en Argentina.
- La nueva fecha tiene que ser posterior a ese día. El calendario deshabilita
  ese día y los anteriores con `min`.
- Esto equivale exactamente a la regla del backend `new_end > current_end`.
  Ejemplo: un fin a las 23:30 AR del día D no permite elegir D; sí permite D+1.
- El campo arranca con la sugerencia «vencimiento actual + 1 mes», editable.
  Esa sugerencia nunca se envía sin el motivo y la confirmación.

### Modal

- **Muestra:** comercio con su ID, plan (`Recepcionista IA · <tier>`),
  vencimiento actual, nueva fecha (con el `DatePicker` existente) y motivo
  obligatorio de hasta 255 caracteres, con contador.
- **Aclara** que extender no reinicia el consumo, no cambia el cupo y no
  modifica la atención automática.

### Guardado

- **Body:** exactamente `{complimentary_end, reason}`, con el motivo recortado.
- **Mientras se procesa:**
  - Un `fieldset disabled` deshabilita la fecha y el motivo.
  - Cancelar y confirmar quedan deshabilitados.
  - Un `ref` impide el doble envío.
- **Sin estado optimista.** Después del 200:
  - Se cierra el modal y se muestra «Vigencia extendida hasta …».
  - Se invalida `['platform-admin','ai-usage',id]`. Es la misma query que lee
    el checklist de preparación, así que no se agrega ninguna consulta
    paralela.
  - `router.refresh()` vuelve a leer el detalle comercial del servidor.
  - La configuración del agente no se toca: no hay `PATCH`.

### Errores

Se usan `errorCode` y `ApiError`, los mismos mecanismos existentes.

| Respuesta | Comportamiento |
|---|---|
| `invalid_end`, `invalid_reason`, errores de serializer `{campo: [...]}` | Mensaje en el campo; los datos ingresados se conservan |
| 403 | «Solo un superadmin…» |
| 404 y 409 de dominio de 09D1: `client_not_found`, `subscription_not_found`, `subscription_not_extendable`, `subscription_canceled`, `subscription_suspended`, `subscription_not_complimentary`, `cancellation_scheduled`, `subscription_not_current`, `custom_policy_not_extendable` | Mensaje específico con «No se cambió nada» y botón **«Recargar datos»**, que recarga el consumo y el detalle |
| Cualquier otro | Mensaje genérico |

No hay reintentos automáticos ni reactivación de nada.

## 3. Componentes reutilizados, creados y evitados

**Reutilizados:**
- `SectionCard`, `Modal`, `Button` y `DatePicker`.
- `useAdminAIUsage` y su query.
- `apiPost`, `ApiError` y `errorCode`.
- `aiUsageTierLabel`.
- `addCalendarMonths` (alta), `addDaysToDateString`, `todayDateString` y
  `formatDateFromTimestampAR`.
- `Providers` del bloque.
- El patrón de sesión del servidor para el rol.

**Creados:**
- Un componente.
- Una función de API.
- Dos tipos.
- Un helper de fecha.
- Una key exportada.

**Evitados:**
- Otra pantalla.
- Otra consulta para el checklist.
- Un endpoint de rol en el cliente.
- Estado optimista.

## 4. Tests

**Archivo:** `components/admin/__tests__/receptionist-validity-extension.test.tsx`,
16 tests, todos OK.

**Qué cubren:**
- Plan fijo y plan personalizado.
- Rol `operations`, que no ve la acción.
- Recepcionista como servicio adicional: el id sale de la fuente, no de la
  suscripción principal.
- Diez casos no extendibles.
- Validación del motivo: vacío y más de 255 caracteres.
- El día del vencimiento actual no se puede elegir; otra fecha se envía sin
  conversión.
- Vencimiento a las 23:30 AR.
- `dateStringFromTimestampAR`.
- Cancelar.
- Solicitud en curso y doble envío.
- Errores 400 de dominio y de forma, 403, y 404/409 con recarga explícita.
- Mapeo de todos los códigos de dominio.
- Éxito: se refresca el consumo, se llama a `router.refresh` y la
  configuración no se toca.
- Cambio de cliente sin mezclar estado.

**Regresión** (Vitest en `node:20-alpine`):

| Suite | Resultado |
|---|---|
| `components/admin`, `features/reception`, `app/admin`, `components/ui` y `lib` | 331/333. Las 2 fallas son las preexistentes de `notificaciones-content` |
| TypeScript | Solo los 4 errores preexistentes de `google-place-autocomplete.tsx` |
| ESLint (archivos tocados) | 0 errores. 6 warnings preexistentes de íconos sin usar en `cliente-detail-content.tsx`, en líneas que este cambio no toca |

## 5. Riesgos

- **No verificado en un navegador real:** `/admin` necesita sesión de
  Platform Admin. Está cubierto con tests de componente.
- **Rol desactualizado:** se resuelve en el servidor al cargar la página. Si
  cambia durante la sesión, el backend responde 403 y la UI lo muestra.
- **La acción depende del diagnóstico de consumo:** si la fuente no se puede
  resolver (`resolution_error`, ambigüedad), no se ofrece. Es fail-closed.
- **Requiere el backend de PROD-09D1 desplegado.** Sin él, el POST da 404 y se
  muestra «No encontramos la suscripción…».
