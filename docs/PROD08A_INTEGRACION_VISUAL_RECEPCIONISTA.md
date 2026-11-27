# PROD-08A — Integración visual de Recepcionista IA (revisión y diseño)

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `5ebae1c` · Bot
`ef5e329` (worktree `agenterecep-lead-handoff`) sin cambios. Slice de revisión:
no se modificó código, solo se agrega este reporte.

## 1. Pantallas y componentes existentes reutilizables

Rutas relativas a `apps/web/src/`.

| Pieza | Archivo | Uso en 08 |
|---|---|---|
| Detalle de cliente admin (SSR + client content, grilla 2/3 + 1/3 de `SectionCard`) | `app/admin/clientes/[clienteId]/page.tsx`, `cliente-detail-content.tsx` | Contenedor de las tarjetas de Recepcionista. Ya inserta tarjetas condicionales (`QRResenasCard` si `service_type === 'qr_reviews'`). |
| Tarjeta de configuración admin con carga propia, `apiGet/apiPatch`, estados `idle/saving/saved/error` | `components/admin/qr-reviews-card.tsx` | **Patrón** a seguir (tarjeta que se carga sola por `businessId`). No se reutiliza el componente. |
| Alta de cliente | `app/admin/clientes/nuevo/nuevo-cliente-form.tsx`, `lib/admin/client.ts` (`provisionAdminClient`, envelope `{code, detail, field}` vs. errores DRF) | Sin cambios: ya provisiona Recepcionista (02F2/02F3/02F4). Se reutiliza su **mapeo de errores** de dominio/campo como referencia. |
| Primitivas admin | `components/admin/section-card.tsx`, `status-badge.tsx`, `loading-state.tsx`, `error-state.tsx`, `empty-state.tsx`, `stat-card.tsx` | Contenedor, badge draft/ready, estados de carga/error/vacío, KPIs de métricas. |
| Primitivas UI | `components/ui/tabs.tsx`, `alert.tsx`, `badge.tsx`, `button.tsx`, `card.tsx`, `modal.tsx`, `switch.tsx`, `date-range-picker.tsx` | Secciones del formulario (Tabs), aviso de conflicto 409 (Alert), confirmaciones (Modal), rango de métricas. |
| Módulo comercio | `app/app/recepcionista/layout.tsx` (gate `services.enabled` incluye `reception`), `page.tsx` (Inicio, accesos por permiso), `consumo/page.tsx` | Inicio recibe el estado de configuración; nueva subruta de configuración bajo el mismo layout. |
| Consumo IA | `features/reception/ai-usage-summary-panel.tsx`, `hooks.ts`, `api.ts`, `types.ts` (contrato v1) | Se reutiliza también en admin: la respuesta admin `ai-usage/` trae `summary` con el **mismo contrato v1**. |
| Sidebar | `components/navigation/sidebar.tsx:247-258` (comentario: «Mi agente y WhatsApp se suman cuando existan») | Agregar un ítem con `permissionKey: 'manage_agent_channels'`. |
| Sin acceso | `components/app/access-message.tsx` | Rol sin `manage_agent_channels`. |
| Cliente API | `lib/api/client.ts` (`ApiError` con `status` + `payload`, `apiGet/apiPost/apiPatch`) | Ambos adaptadores. `payload.code` cubre `version_conflict`, `validation_error.fields`, `receptionist_config_exists`. |
| Lectura de errores por código | `features/leads/errors.ts` (`appointmentProposalErrorCode`, `resolveLeadApiError`) | Mismo enfoque para el formulario (código → mensaje; el backend decide). |
| Sesión | `lib/auth` (`session.permissions` = permisos efectivos; incluye `manage_agent_channels`) | Gate de edición en comercio. |
| React Query | `features/reception/hooks.ts` (`retry: false`, `staleTime`) | Mismo criterio para la config (sin reintentos ante 403/404). |

## 2. APIs

### Disponibles (implementadas, sin cambios)

| Dato | Comercio | Platform Admin |
|---|---|---|
| ReceptionistConfig | `GET/POST/PATCH /api/v1/receptionist-config/` (owner/admin vía `manage_agent_channels` + `reception.ai`) | `GET/POST/PATCH /api/v1/platform-admin/clients/<id>/receptionist-config/` (`superadmin`, `operations`) |
| Información del negocio | sesión (`business`, `services.enabled`) | `GET .../clients/<id>/` (`AdminClientDetail`) |
| Suscripciones | sesión (`subscription`) | `AdminClientDetail.subscription` (solo la principal), `GET .../subscriptions/<id>/` |
| Consumo IA | `GET /api/v1/ai-usage/` (contrato v1) | `GET .../clients/<id>/ai-usage/` (`summary` v1 + `source_subscription` + `diagnosis`), `.../history/`, `.../policies/` |
| Métricas operativas | — | `GET .../clients/<id>/operational-metrics/?date_from&date_to` (OpenAI, costos estimados, WhatsApp, sesiones) |
| Alta de servicio | — | `POST .../clients/<id>/services/` (02F5, solo POST) |

Contrato de config (03B): `GET` → `{config: null | {...13 campos, status, version, missing_for_ready, id, fechas}}`;
`POST` 201 / 409 `receptionist_config_exists`; `PATCH` exige `expected_version` → 200 / 404
`receptionist_config_not_found` / 409 `version_conflict` con `current_version`; 400 `validation_error`
(`fields`), `unknown_fields`, `protected_fields`. Campos: `assistant_name`, `business_category`,
`business_description`, `custom_instructions`, `tone` (warm/professional/formal), `language` (es-AR/es),
`welcome_message`, `operational_info`, `business_hours`, `services` (≤30, `name`/`description`),
`reference_info`, `faqs` (≤30, `question`/`answer`), `handoff_rules`. `ready` = contenido completo,
**no** bot activo.

### Faltantes (requieren backend; no se crean aquí)

- **Estado de conexión WhatsApp / canal:** no hay ninguna API HTTP de lectura de `AgentChannel` ni de
  `WhatsAppAuthorization` para comercio ni para admin. Hoy solo existen operaciones de shell
  (`provision_agent`) y los GET HMAC para el agente (03C, 04C). La UI **no puede** mostrar
  «conectado».
- **Servicios contratados del cliente en admin:** `AdminClientDetail` expone una sola `subscription` y
  `service_type`; no lista servicios. Un Gestión con Recepcionista agregada (02F5) no se distingue por
  `service_type`. Se resuelve sin backend usando el `GET` de config admin (404 `client_not_found` ⇒ sin
  Recepcionista).
- **Métricas para el comercio:** `operational-metrics` es solo admin; el comercio solo tiene consumo
  comercial.

## 3. Propuesta mínima de integración

### Formulario único compartido
`ReceptionistConfigForm` en `features/reception/` (un componente, dos montajes). Recibe un **adaptador**:

```ts
type ReceptionistConfigAdapter = {
  get(): Promise<{ config: ReceptionistConfig | null }>;
  create(body?: Partial<Content>): Promise<{ config: ReceptionistConfig }>;
  patch(body: Partial<Content> & { status?: Status; expected_version: number }): Promise<{ config: ReceptionistConfig }>;
};
```
- `merchantAdapter` → `/api/v1/receptionist-config/`; `adminAdapter(businessId)` →
  `/api/v1/platform-admin/clients/<id>/receptionist-config/`. Ambos sobre `apiGet/apiPost/apiPatch`.
- `canEdit` lo decide el montaje: comercio = `session.permissions.manage_agent_channels`; admin = acceso
  a la ruta (el backend ya limita a `superadmin/operations`; 403 → solo lectura/aviso).
- Secciones con `Tabs`: **Identidad** (nombre, rubro, descripción, tono, idioma, bienvenida),
  **Servicios**, **Preguntas frecuentes**, **Instrucciones** (custom, handoff, info operativa,
  referencia, horarios opcionales).
- Servicios y FAQs: lista editable inline (filas de inputs + agregar/quitar), límites del backend
  mostrados como contador; sin componente de lista genérico nuevo.
- Sin config: estado vacío con botón «Crear borrador» (`POST` vacío). Nunca se crea al abrir.

### Estado draft/ready
- `StatusBadge`: «Borrador» / «Lista para activar» (labels del modelo).
- `missing_for_ready` se lista tal como llega. «Marcar lista» = `PATCH {status:'ready'}`; deshabilitado
  si falta algo, pero el backend es la autoridad (400 se muestra).
- Texto fijo bajo el badge: «Lista para activar no significa que el agente esté conectado».

### Versionado optimista y 409
- Se guarda `version` del último GET/PATCH y se envía como `expected_version`. Un solo botón «Guardar»
  envía solo campos cambiados (diff contra el último snapshot).
- 409 `version_conflict`: `Alert` «Otra persona guardó cambios (versión N)» con una sola acción,
  «Cargar la versión actual» (refetch). Hasta que el usuario la use, sus cambios locales quedan en
  pantalla para que pueda copiarlos. Nunca se reintenta automáticamente con la versión nueva ni se
  fusiona en el cliente.
- 409 `receptionist_config_exists` en create → refetch.
- 400 `validation_error.fields` → error por campo; `unknown/protected_fields` → error genérico (bug).

### WhatsApp
- Sin API: en admin, tarjeta informativa estática «Conexión WhatsApp: se gestiona por operaciones; el
  estado no está disponible en el panel». En comercio, no se muestra nada. Ningún indicador verde ni
  «conectado» derivado de `ready`, de consumo o de métricas.

### Consumo y métricas
- Comercio: sin cambios (`/app/recepcionista/consumo`). Inicio suma una línea con el estado de config
  (badge) y link «Configurar agente» si `manage_agent_channels`.
- Admin: `AIUsageSummaryPanel` reutilizado alimentando `summary` del endpoint admin (más `diagnosis` como
  texto). Métricas operativas: una tarjeta con `StatCard` (sesiones iniciadas, mensajes in/out,
  handoffs, costo estimado con nota «estimado») y `date-range-picker`; valores `null` = «sin dato».

### Ubicación
- Admin: `cliente-detail-content.tsx`, columna principal, sección «Recepcionista IA» con tres
  `SectionCard`: Configuración, Consumo IA, Métricas operativas (+ aviso WhatsApp). Se renderiza si el GET
  de config no responde 404 `client_not_found`.
- Comercio: `/app/recepcionista/configuracion` bajo el layout existente + ítem de sidebar «Mi agente».

## 4. Componentes nuevos estrictamente necesarios

| Nuevo | Justificación |
|---|---|
| `features/reception/receptionist-config-form.tsx` | No existe formulario para este contrato; uno solo para admin y comercio evita el panel paralelo. |
| `features/reception/receptionist-config-api.ts` (dos adaptadores) + tipos en `types.ts` | Las rutas difieren solo en el prefijo; el adaptador es lo único que cambia entre montajes. |
| `app/app/recepcionista/configuracion/page.tsx` | Ruta del comercio (montaje fino). |
| `components/admin/reception-card.tsx` (montaje admin: config + consumo + métricas) | Equivalente a `QRResenasCard`; mantiene `cliente-detail-content.tsx` sin lógica nueva. |
| Prop de datos en `AIUsageSummaryPanel` (ampliación, no componente) | Hoy llama a su hook; con `data/query` opcional sirve en admin. |

No se crean: lista genérica, editor de texto enriquecido, sistema de toasts, hooks de formularios ni
estados de conexión.

## 5. Slices recomendados

1. **PROD-08B** — Formulario compartido + adaptadores + tipos; montaje comercio
   (`/app/recepcionista/configuracion`, sidebar, badge en Inicio). Tests vitest: 409, validation,
   permisos, create vacío.
2. **PROD-08C** — Montaje admin en `/admin/clientes/[id]` (`reception-card`, gate por 404) reutilizando
   el formulario.
3. **PROD-08D** — Consumo admin (prop de datos en `AIUsageSummaryPanel`) y tarjeta de métricas
   operativas con rango.
4. **PROD-08E (requiere backend, fuera de 08)** — API de lectura de estado de canal/WhatsApp
   (admin primero) y recién entonces su indicador visual.

Riesgos: R1 `bid` ajeno vuelve al negocio activo (03B R3): el formulario de comercio muestra el nombre
del negocio de la sesión. R2 textos largos (4000) en móviles: `textarea` con contador. R3 el diff por
campo debe comparar listas por valor para no versionar sin cambios (el backend igual no versiona).
