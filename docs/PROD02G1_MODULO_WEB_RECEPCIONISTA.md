# PROD-02G1 — Módulo web independiente de Recepcionista IA

Fecha: 2026-11-26 · Rama: `feat/recepcionista` · Baseline `51431e3`.

**Estado verificado antes de empezar:**
- Mi Rubro: `mirubrodigital-release` en `51431e3`, igual que `origin/feat/recepcionista`, sin cambios locales de código.
- Bot: `5eb3dda` en su worktree `D:\BOT RECEPCIONISTA\agenterecep-lead-handoff` (`feat/recepcionista`), sin modificar. El checkout principal `agenterecep` está en `develop` (`e8b70fb`), que no contiene `5eb3dda`. No se tocó.

**Cambios por capa:**
- Solo frontend.
- Backend sin cambios: la sesión ya expone el producto desde PROD-02C (`business/context.py`). Incluye:
  - `services.enabled ∋ 'reception'` y `current.service = 'reception'` cuando Recepcionista es el servicio principal;
  - `features.reception_core`, `features.leads` y `features.customers` según los entitlements de Recepcionista;
  - los permisos del mapa `reception` (`view_leads`, `manage_leads`, `view_ai_usage`, `view_customers`, `manage_customers`, `manage_users`, `manage_settings`).

## 1. Rutas y navegación implementadas

| Ruta | Contenido | Control |
|---|---|---|
| `/app/recepcionista` | **Inicio:** encabezado del producto, accesos a Consumo y Clientes, y resumen compacto del consumo | Layout del módulo y permisos para cada acceso |
| `/app/recepcionista/consumo` | **Consumo:** conversaciones usadas y restantes, período, próximo cupo (Custom) y estados del servicio | `view_ai_usage`. La API es `GET /api/v1/ai-usage/` (PROD-02E3A, contrato v1) |
| `/app/clientes` (existente) | Clientes core compartido | Flag `customers` (entitlement `reception.customers`) más `view_customers`, como ya aplica la página |
| `/app/settings/access`, `/app/planes`, `/app/soporte` (existentes) | Usuarios y accesos, plan y facturación, soporte | `manage_users` en Usuarios; las otras dos son rutas comunes |

**Sidebar `reception`:**
- Grupo *Recepcionista IA*: Inicio, Consumo y Clientes.
- Grupo *Configuración*: Usuarios y accesos, y Plan y facturación.
- Soporte.

**Entrada:** `getServiceEntryPath('reception') = '/app/recepcionista'`. El login (contraseña, Google y acceso preautorizado del cliente) termina en `/app/dashboard`, y desde ahí `/app` redirige a esa ruta. Los nombres visibles son «Recepcionista IA» (servicio y plan).

**Gating de rutas (`service-path-gating`):** para el servicio `reception` solo se permiten:
- las rutas comunes;
- `/app/recepcionista/*`;
- `/app/clientes/*`.

Turnos (agenda, leads de Turnos, profesionales, horarios), Gestión, POS, caja, ventas, stock, Carta, Reseñas y sucursales muestran el mensaje «No disponible en tu plan».

**Pendiente y fuera de la navegación (para no crear rutas ficticias):**
- **Leads:** queda para PROD-02G2. Ver §3.
- **Configuración del agente, Mi agente y WhatsApp / Meta Embedded Signup:** quedan excluidos por alcance. Hoy la configuración disponible es Usuarios y accesos, y Plan y facturación.

## 2. Controles de acceso reutilizados

- **Enforcement global de `/app`** (`app/app/layout.tsx`): sin cambios. Si el beneficio es futuro o venció, `subscription.access_allowed=false` y la sesión redirige a `/app/planes` (o al estado de cuenta), incluso por URL directa.
- **Layout del módulo** (`app/app/recepcionista/layout.tsx`): exige `'reception' ∈ services.enabled`. Si no está, redirige a `/app/servicios`, igual que `/app/turnos`. El backend solo agrega `reception` con una suscripción de Recepcionista que da acceso efectivo, también cuando es un servicio adicional (por ejemplo, Gestión principal).
- **Sidebar:** filtra por `permissionKey` y `featureKey` como el resto de los productos.
- **Páginas:** chequean el permiso efectivo de la sesión, como las de Turnos. Todo esto es UX: cada API sigue con sus guards (`HasBusinessMembership`, `HasPermission` y `HasEntitlement`).
- **Sin cambios:** no se relajaron guards globales ni se tocó el enforcement multiservicio (PROD-02F6 en pausa).

## 3. Componentes y reutilización

**Modificados:**
- `lib/services/index.ts`: entrada y nombres.
- `components/app/service-path-gating.ts`: allowlist de `reception`.
- `components/navigation/sidebar.tsx`: `NAV_CONFIG.reception`.

**Nuevos:**
- `app/app/recepcionista/{layout,page}.tsx` y `consumo/page.tsx`.
- `features/reception/{types,api,hooks}.ts`: primer cliente HTTP de `/api/v1/ai-usage/`. No había otro en el frontend, así que no se duplica nada. Usa `apiGet` y React Query, como el resto.
- `features/reception/ai-usage-summary-panel.tsx`.

**Reutilización prevista en PROD-02G2 (sin mover nada ahora):**
- **Leads:** `features/leads/{api,hooks,types,access,errors}.ts` son neutros de ruta y se reutilizan tal cual. Lo que está acoplado a Turnos es la capa de páginas:
  - `app/app/turnos/leads/leads-inbox-client.tsx` (`leadCta` arma `/app/turnos/leads/${id}`);
  - `app/app/turnos/leads/[id]/lead-detail-client.tsx` (`INBOX_HREF`);
  - el layout `/app/turnos`, que exige `appointments`.

  **Estrategia:**
  1. Parametrizar esos dos clientes con una base de ruta (`basePath`, por defecto `/app/turnos/leads`).
  2. Montarlos también en `/app/recepcionista/leads` y `/[id]`.
  3. Las acciones de agenda ya dependen de `agenda_integration`, `view_appointments` y `has_agenda_access` en el backend.
  4. Para Recepcionista principal, `/app/turnos/leads` puede redirigir a `/app/recepcionista/leads`. Para Turnos, se mantiene la ruta actual.
- **Clientes:** `/app/clientes` y `features/customers` son la ficha canónica compartida, con gating por flag y permiso, y timeline con gating por fuente en el backend. Se reutilizan sin duplicarlos. En G2 conviene revisar qué secciones de la ficha aplican a un comercio solo de Recepcionista; no se verificaron en el navegador.

## 4. Funcionalidades disponibles y pendientes

| Disponible ahora | Pendiente |
|---|---|
| Ingreso y redirección al panel propio | Leads bajo `/app/recepcionista` (G2) |
| Inicio con accesos según permisos | Mi agente y WhatsApp (embedded signup) |
| Consumo del período (fijo y Custom, próximo cupo, agotado, suspendido, sin contrato, sin permiso) | Configuración propia del agente |
| Clientes compartidos (si el plan incluye `reception.customers`) | Entrada a Recepcionista desde la navegación de Gestión o Turnos cuando es un servicio adicional (hoy se entra por URL o desde el hub) |
| Usuarios y accesos, Plan y facturación, Soporte | — |

## 5. Tests y resultados

**Nuevos, 21 tests en verde:**
- **`app/app/recepcionista/__tests__/recepcionista-access.test.tsx` (12):**
  - entrada y nombres;
  - login → `/app/dashboard` y `/app` → `/app/recepcionista`;
  - entradas de Turnos y Gestión sin cambios;
  - beneficio vigente (renderiza);
  - beneficio futuro o vencido → `/app/planes`, también por URL directa;
  - módulo sin el servicio → `/app/servicios`;
  - Recepcionista como servicio adicional;
  - Inicio sin rutas ajenas y con accesos según permisos y flags;
  - Consumo con y sin `view_ai_usage`.
- **`components/navigation/__tests__/sidebar-reception.test.tsx` (3):**
  - contenido del sidebar;
  - ausencia de Turnos, Gestión, POS, caja, ventas, stock, Mi agente, WhatsApp y Leads;
  - gating por flag y permiso.
- **`features/reception/__tests__/ai-usage-summary-panel.test.tsx` (6):** disponible, agotado, Custom con cambio programado, suspendido (beneficio futuro o vencido), 403 sin contrato o sin rol, y carga.

**Extendidos:** `components/app/__tests__/service-path-gating.test.ts` (+29 casos `reception`).

**Corridas:**
- **Vitest dirigido:** 11 archivos, 151 tests en verde.
- **Vitest de compatibilidad** (`src/app/app`, `src/components`, `features/leads`, `features/customers`, `features/reception`, `src/lib`): 74 archivos y 958 tests, con **1 fallo preexistente**: `onboarding-service-options` › «resolves qr_reviews product…». Falla igual en `51431e3`.
- **TypeScript:** solo los 4 errores preexistentes de `features/reviews/google-place-autocomplete.tsx`, idénticos en `51431e3`. Se usó un tsconfig temporal que excluye `.next`, como en F3 y F4.
- **ESLint** sobre los archivos tocados: 0 errores y 2 warnings preexistentes en líneas de `sidebar.tsx` que no se modificaron.
- **Entorno:** `node:20-alpine` con el volumen `mirubro_web_nm_recep2`.

## 6. Riesgos o bloqueantes

- **Leads:** el primer cliente necesita la bandeja de Leads dentro de su panel. Hasta G2, un comercio solo de Recepcionista no tiene Leads en la web, porque `/app/turnos/leads` exige el servicio Turnos.
- **Servicio principal:** el panel solo es independiente cuando Recepcionista es el servicio principal del Business. El alta de F2/F3 lo deja así. Un Business con otro servicio principal y Recepcionista agregado (F5) entra por URL, pero:
  - su sidebar sigue siendo el del principal;
  - sus permisos de sesión son los del mapa del principal (PROD-02C: Leads/Agenda por dueño de la capacidad);
  - si el principal se suspende, el gate global bloquea también Recepcionista (PROD-02F6A, en pausa).
- **Configuración:** hoy no hay configuración del agente, así que el grupo Configuración solo agrupa Usuarios y accesos, y Plan y facturación.
- **Prueba en navegador:** no se probó manualmente en el navegador. La validación es con Vitest, TypeScript y ESLint.

## 7. Commits y HEAD

- `3484aed` feat(web): register Recepcionista IA as an independent service in navigation
- `ef423a2` feat(web): Recepcionista IA module with home and AI usage pages
- `2ef5f39` test(web): cover the independent Recepcionista IA navigation and access
- docs(prod): este reporte. Es el HEAD final y está respaldado en `origin/feat/recepcionista` sin force push.
