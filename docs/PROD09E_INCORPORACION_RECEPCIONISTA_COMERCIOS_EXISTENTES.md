# PROD-09E — Incorporación de Recepcionista IA a comercios existentes

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `3f3c8d2` · Bot
`de7e932` sin cambios. Solo frontend (`apps/web`). Sin endpoints, modelos,
migraciones ni dependencias nuevas.

## 1. Implementación

| Pieza | Archivo |
|---|---|
| Sección y modal «Agregar Recepcionista IA» | `components/admin/add-reception-service.tsx` → `AddReceptionServiceSection` y `hasActiveTurnosIA` |
| Montaje | `components/admin/receptionist-admin-card.tsx`: ante el 404 `client_not_found` de la configuración muestra la incorporación en lugar de nada, solo si `canAddReception`. Es el mismo `Providers` y el mismo QueryClient que el bloque |
| Rol y estado | `app/admin/clientes/[clienteId]/page.tsx`: `canAddReception` sale de la sesión superadmin del servidor, como en 09D2. `client.status` llega desde el detalle |
| Llamada | `lib/admin/client.ts` → `addServiceToAdminClient`, que comparte con `provisionAdminClient` el parser de respuestas extraído (`postProvisioning`) |
| Tipos | `lib/admin/types.ts` → `AdminClientServiceAdditionInput` y `AdminClientServiceAdditionResult` |
| Extraídos del alta (duplicación real) | `lib/admin/complimentary-grant.ts`: `validateComplimentaryGrant`, `customAllowanceOf` y `usageTierPayload`. `components/admin/complimentary-grant-fields.tsx`: `UsageTierFields`, `ComplimentaryPeriodFields` y `GrantReasonField`, con los mismos ids, labels, clases y mensajes. El formulario de alta los usa ahora y quedó con −195 líneas |

## 2. Visibilidad (revisando datos existentes)

La acción se ofrece solo si se cumplen todas estas condiciones:

1. **Superadmin.** Lo resuelve la sesión del servidor. El backend vuelve a
   verificarlo.
2. **Sin Recepcionista no cancelada.** La configuración admin responde 404
   `client_not_found`. Es la regla `admin_reception_business` del backend:
   cualquier `SubscriptionV2` de reception no cancelada, sea servicio
   principal o adicional. **Nunca** se infiere desde `service_type`.
3. **Cliente en estado `active` o `trialing`.** Son los mismos estados que
   acepta 02F5. Para cualquier otro estado se informa el motivo.
4. **Sin Turnos IA no cancelado,** según `GET .../ai-usage/` (la misma query
   del bloque): `diagnosis.candidates` o `source_subscription` con producto
   `appointments_ai`. Si esa lectura falla no se ofrece, y se muestra
   «Reintentar».

El solapamiento de períodos de consumo no se puede conocer desde el frontend
sin un endpoint nuevo. Lo responde el backend: 409 `ai_usage_period_overlap`
en el campo de inicio.

## 3. Modal y contrato

**Muestra:**
- Comercio con su ID.
- Niveles de uso del catálogo (`provisioning-options`, servicio `reception`):
  300, 1.500 y 3.000, y Custom con su cupo (`custom_allowance` min/max).
- Período bonificado con accesos rápidos de 6 meses, 1 año y personalizado.
- Motivo obligatorio, de hasta 255 caracteres. Es el límite de
  `manual_grant_reason` y de la política Custom.

El plan `reception` se elige solo cuando es el único. Solo aparece un
selector si el catálogo ofreciera más de uno.

**No pide** owner, país, moneda, servicio ni otros datos comerciales.

**Contrato:** `POST /api/v1/platform-admin/clients/{business_id}/services/`,
con `business_id` tomado de la ruta.

```json
{ "service_type": "reception", "plan_code": "reception",
  "complimentary_start": "YYYY-MM-DD", "complimentary_end": "YYYY-MM-DD",
  "grant_reason": "…", "usage_tier": "reception_300|…|reception_custom",
  "custom_included_sessions": 750 }
```

- `custom_included_sessions` se envía solo con Custom.
- Las fechas siguen la misma semántica que el alta: fecha sin hora, que el
  backend interpreta a las 00:00 de su TIME_ZONE, con fin exclusivo.
- Las validaciones son las del alta compartidas, más el máximo de 255 del
  motivo.

**No se envía ni se modifica nada más.** No se tocan:
- Owner ni usuarios.
- Servicio principal.
- Suscripciones actuales.
- Configuración ni atención automática: no hay `PATCH`.
- Canales ni credenciales de WhatsApp.

## 4. Guardado y errores

**Guardado:**
- Sin estado optimista.
- Un `ref` y el `fieldset disabled` impiden el doble envío mientras se
  procesa.

**Después del 201:**
- Se cierra el modal.
- Se invalidan dos queries:
  - La configuración admin: deja de responder 404 y la tarjeta muestra el
    bloque completo (preparación, configuración, conexiones, consumo y
    métricas).
  - `adminAIUsageKey`.
- `router.refresh()` actualiza el detalle del servidor.

**Errores** (sobre las respuestas existentes `ok`, `forbidden`,
`domain_error`, `field_errors`, `server_error` y `session_expired`):

| Respuesta | Comportamiento |
|---|---|
| Errores de campo visibles: `invalid_complimentary_period`, `invalid_complimentary_grant_reason`, `invalid_complimentary_usage_tier`, `invalid_custom_included_sessions`, `ai_usage_period_overlap` (inicio) y DRF `{campo: [...]}` | Mensaje en el campo |
| `active_complimentary_subscription_conflict` (ya contratado), `incompatible_ai_service`, `client_status_not_eligible`, `client_not_found` | Aviso «No se cambió nada» con «Recargar datos» |
| `complimentary_plan_*` sin selector visible, 422 `complimentary_grant_failed` | Aviso general |
| 403 | «Solo un superadmin…» |
| `server_error` con `httpStatus` 0 | «Error de red…» |
| 401 | Redirección a `/admin/login`, igual que el alta |

En todos los casos se conserva lo ingresado y nunca se reintenta solo.

## 5. Componentes reutilizados, creados y evitados

**Reutilizados:**
- `SectionCard`, `Modal` y `Button`.
- `getAdminClientProvisioningOptions` y el parser de respuestas del alta.
- `useAdminAIUsage` y `adminAIUsageKey`.
- `receptionistConfigAdapter` y `isClientWithoutReception`.
- `todayDateOnly` y `addCalendarMonths`.
- Los campos y validaciones del alta, ahora compartidos.

**Creados:**
- La sección con su modal.
- Una función de API.
- Dos tipos.

**Evitados:**
- Otra página de onboarding.
- Otro `Providers` u otro QueryClient.
- Un endpoint para detectar Recepcionista o solapamientos.
- Pedir de nuevo datos comerciales o del owner.

## 6. Tests

**Nuevo:** `components/admin/__tests__/add-reception-service.test.tsx`, 16
tests, todos OK.

**Qué cubren:**
- Alta en un comercio existente con plan fijo: payload exacto, aparece el
  bloque completo, `refresh`, sin `PATCH` ni POST de configuración, y el
  servicio principal no cambia.
- Plan Custom con cupo inválido y válido.
- Permisos.
- Recepcionista ya contratada.
- Decisión por configuración y no por `service_type`.
- Turnos IA (por candidatos, por fuente y cancelado) y cliente no elegible.
- Falla al verificar el consumo, con reintento.
- Validaciones de nivel, fechas y motivo.
- Cancelar.
- Solicitud en curso y doble envío.
- Errores de campo (solapamiento, forma, plan sin selector).
- Errores con recarga (ya contratado, Turnos IA, no elegible, no
  encontrado).
- 403 y error de red con el formulario conservado.
- Catálogo no disponible.
- Cambio de cliente.
- Contrato de `addServiceToAdminClient` con `fetch` simulado: URL, body
  exacto, Custom, 409, 403 y red.

**Regresión:**

| Suite | Resultado |
|---|---|
| Formulario de alta original (`app/admin/clientes`) | 55/55 OK después de la extracción |
| `components/admin`, `features/reception`, `app/admin`, `components/ui` y `lib` | 347/349. Las 2 fallas son las preexistentes de `notificaciones-content` |
| TypeScript | Solo los 4 errores preexistentes de `google-place-autocomplete.tsx` |
| ESLint (archivos tocados) | 0 errores. 6 warnings preexistentes de íconos sin usar en `cliente-detail-content.tsx` |

## 7. Riesgos

- **No verificado en un navegador real:** `/admin` necesita sesión de
  Platform Admin.
- **Solapamiento de consumo:** solo lo detecta el backend (409 en el campo de
  inicio). Es imposible anticiparlo sin un endpoint nuevo.
- **Turnos IA:** se detecta con la lectura de consumo actual. Si cambia entre
  la lectura y el envío, el backend responde 409 `incompatible_ai_service` y
  se ofrece recargar.
- **Después del alta:** el bloque aparece con la configuración sin crear
  (`config: null` o borrador) y la atención automática pausada, como en
  cualquier Recepcionista nueva. La activación sigue el circuito de
  preparación existente.
- **Requiere el backend 02F5 desplegado,** que ya está en la rama.
