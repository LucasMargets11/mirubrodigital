# PROD-08B — Configuración visual de Recepcionista IA

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `4f29937` · Bot
`ef5e329` sin cambios. Referencia: `docs/PROD08A_INTEGRACION_VISUAL_RECEPCIONISTA.md`.
Solo frontend (`apps/web`). Sin backend, endpoints, modelos ni dependencias.

## 1. Resultado

- `ReceptionistConfigForm` único, con un `target` (`business` | `platform_admin`)
  que elige el adaptador. Montado solo en el comercio:
  `/app/recepcionista/configuracion` («Mi agente»). Platform Admin queda para 08C
  (el adaptador ya existe y está testeado, sin montar).
- Acceso: ítem «Mi agente» en el grupo Recepcionista IA del sidebar y link en
  Inicio, ambos con `permissionKey`/permiso `manage_agent_channels` (owner/admin).
  El layout existente ya exige `reception` en `services.enabled`; el backend
  vuelve a validar permiso y `reception.ai` (403 → «Sin acceso»).
- Cuatro tabs con los 13 campos: **Identidad** (nombre, rubro, descripción,
  bienvenida, tono, idioma), **Servicios**, **Preguntas frecuentes**,
  **Instrucciones** (adicionales, derivación, info operativa, horarios
  opcionales, referencia). Límites del modelo como `maxLength` + contador.
- Negocio activo visible arriba del formulario en todos los estados.

## 2. Estados y guardado

- `GET` con `{config: null}` → estado vacío y «Crear borrador» (`POST {}`). Nunca
  crea al abrir. 409 `receptionist_config_exists` → relee.
- Badge «Borrador» / «Configuración lista» + aclaración fija: no significa
  agente conectado ni atendiendo por WhatsApp. Sin indicadores de conexión.
- «Marcar como lista»: deshabilitado si `missing_for_ready` no está vacío (se
  listan los campos) o si hay cambios sin guardar. «Volver a borrador» pide
  confirmación con el `Modal` existente: en borrador Mi Rubro no entrega la
  configuración al agente (03C) y el agente deja de atender con esos datos.
- «Guardar cambios» envía solo los campos distintos del servidor más
  `expected_version`. Listas comparadas por contenido (descripción ausente =
  vacía); volver al valor original deja el formulario limpio.
- 409 `version_conflict`: alerta con la versión actual, cambios locales intactos,
  guardar deshabilitado, sin reintento ni fusión. «Cargar la versión actual»
  relee y descarta lo local de forma explícita.
- 400 `validation_error.fields`: mensaje bajo cada campo, punto rojo y texto
  «(con errores)» en la tab afectada y resumen clickeable que lleva a la tab.
  `status` y `non_field_errors` se muestran en el bloque de estado/resumen.
- Cambios sin guardar: `beforeunload` y confirmación antes de seguir un link
  interno (listener de click en captura; Next `Link` respeta `preventDefault`).
- Aislamiento por negocio: la query key incluye `kind` y `businessId`, y el
  formulario se monta con `key` por target, así un cambio de negocio nunca
  reutiliza estado, cambios ni caché. Sin `refetchOnWindowFocus`: el servidor se
  relee solo por acción explícita.

## 3. Reutilizado

`components/ui/tabs.tsx`, `components/ui/modal.tsx` (con `footer`),
`components/ui/alert.tsx`, `components/app/access-message.tsx`,
`lib/api/client.ts` (`apiGet/apiPost/apiPatch`, `ApiError.payload.code`),
React Query (mismo criterio `retry: false` que `features/reception/hooks.ts`),
el patrón «edits sobre snapshot del servidor» de
`features/appointments/reminder-automation-card.tsx`, las clases de inputs de
`features/customers/components/customer-form-fields.tsx` y de botones de
`app/app/recepcionista/page.tsx`, `getSession()` y el `NAV_CONFIG` del sidebar
con `permissionKey`.

## 4. Archivos

**Nuevos**
- `features/reception/receptionist-config-form.tsx` — el formulario compartido y
  sus piezas locales (campo de texto con contador, filas de servicios y FAQs,
  guard de cambios sin guardar). Nada exportado como componente genérico.
- `features/reception/receptionist-config-api.ts` — `receptionistConfigAdapter(target)`:
  misma interfaz, solo cambia la ruta y la key.
- `app/app/recepcionista/configuracion/page.tsx` — montaje del comercio.
- `features/reception/__tests__/receptionist-config-form.test.tsx`.

**Modificados**
- `features/reception/types.ts` — tipos del contrato y límites del modelo.
- `components/navigation/sidebar.tsx` — ítem «Mi agente» (sin otros cambios).
- `app/app/recepcionista/page.tsx` — link «Mi agente» en Inicio.
- `components/navigation/__tests__/sidebar-reception.test.tsx`,
  `app/app/recepcionista/__tests__/recepcionista-access.test.tsx`.

**Evitado:** constructor de formularios, componente de lista genérico, input
compartido nuevo, toasts, hooks de formulario, endpoint de estado, indicador de
conexión, cambios en `lib/api/client.ts`.

## 5. Tests

Vitest en `node:20-alpine` (volumen `mirubro_web_nm_recep2`):

| Corrida | Baseline `4f29937` | Final |
|---|---|---|
| `features/reception` + `app/app/recepcionista` + `sidebar-reception` | 4 archivos, 33/33 | 5 archivos, 56/56 |
| Regresión `features/reception` + `app/app/recepcionista` + `components/navigation/__tests__` | — | 12 archivos, 96/96 |
| TypeScript (`tsc --noEmit`, sin `.next`) | 4 errores preexistentes (`google-place-autocomplete.tsx`) | los mismos 4 |
| ESLint (archivos tocados) | 2 warnings preexistentes en `sidebar.tsx` | los mismos 2, archivos nuevos limpios |

Nuevos (18 + 4 + 1): adaptadores y keys; diff de listas por contenido; creación
explícita y 409 al crear; edición con solo campos cambiados y `expected_version`;
volver al valor original; filas de servicios/FAQs; máximo de 30; 409 con cambios
preservados, sin reintento y relectura explícita; validación por campo en otra
tab; ready bloqueado por faltantes y sin presentarse como conectado; draft→ready;
cambios pendientes bloquean el estado; ready→draft con modal y cancelación; solo
lectura; 403 al leer; guard de link y `beforeunload`; cambio de negocio sin
arrastrar estado ni versión; página con y sin `manage_agent_channels`; Inicio;
sidebar.

## 6. Riesgos

- R1: no se verificó en navegador (solo jsdom); falta una pasada visual con
  sesión real, en especial el ancho de las tabs en móvil.
- R2: el guard de navegación cubre links y recarga/cierre, no el botón atrás del
  navegador dentro de la SPA (App Router no expone un evento bloqueable).
- R3: el comercio opera sobre el negocio de la cookie `bid` (03B R3). La key por
  `businessId` de la sesión y la ausencia de recargas automáticas evitan mezclar
  datos en pantalla, pero un cambio de negocio en otra pestaña no se detecta
  hasta recargar.
- R4: los errores dentro de una lista (p. ej. servicio repetido) llegan del
  backend a nivel lista, no por fila; se muestran bajo la lista.

## 7. HEAD

Commits sobre `4f29937`: feature, tests y este reporte, empujados a
`origin/feat/recepcionista` sin force push. No se avanzó a PROD-08C.
