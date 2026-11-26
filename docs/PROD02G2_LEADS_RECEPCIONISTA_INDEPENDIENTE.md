# PROD-02G2: Leads y atención humana independientes de Turnos

- **Fecha:** 2026-11-26
- **Repo y rama:** `mirubrodigital-release`, `feat/recepcionista`
- **Baseline:** `ffa1632`
- **Bot:** `agenterecep-lead-handoff` en `5eb3dda`, sin cambios
- **Referencia:** `docs/PROD02G1_MODULO_WEB_RECEPCIONISTA.md`

Solo se tocó el frontend. El backend no se modificó.

## 1. Rutas

| Ruta | Contenido |
|---|---|
| `/app/recepcionista/leads` | Bandeja de Leads de Recepcionista IA |
| `/app/recepcionista/leads/[id]` | Detalle de un Lead de Recepcionista IA |
| `/app/turnos/leads` y `/[id]` | Se conservan para Turnos. Delegan en el mismo cuerpo compartido, con las mismas props y el mismo copy |

**Deep links.** El layout de `/app/turnos` (`app/app/turnos/layout.tsx`) redirige `/app/turnos/leads/*` a la ruta equivalente de Recepcionista solo cuando el negocio **tiene Recepcionista y no tiene Turnos**. Esto cubre:
- bookmarks;
- el `action_url` que el backend sigue generando en las notificaciones `agent_lead_handoff` y `lead_assigned` (`/app/turnos/leads/{id}`).

En cualquier otro caso se mantiene la redirección previa a `/app/servicios`. No hay bucle: `/app/recepcionista` exige `reception` en `services.enabled`.

## 2. Componentes reutilizados (un solo CRM)

La bandeja y el detalle se movieron con `git mv` de `app/app/turnos/leads/` a `features/leads/ui/`, con su historia:
- `leads-inbox-client`
- `lead-detail-client`
- `lead-activity`
- `lead-appointment-picker`
- `lead-assignee-select`
- `lead-conversation-control`
- `lead-conversation-history`
- `lead-message-composer`
- `lead-notes`

Recepcionista ya no importa nada de las páginas de Turnos/Leads. `features/leads/{api,hooks,types,access,errors}` siguen sin cambios: no se agregaron servicios HTTP, hooks ni modelos.

Archivos nuevos en `features/leads/ui/`:
- **`leads-routes.ts` (puro, apto para servidor):** contexto del producto (`basePath`, `agendaEnabled`, `product`), vocabulario (`contactNoun`, `personalize`), `leadDetailHref` y `receptionLeadsPathFor` para los deep links.
- **`leads-context.tsx` (cliente):** `LeadsContextProvider` y `useLeadsContext`. El valor por defecto es Turnos, así que **la salida de Turnos queda idéntica** y sus páginas no usan provider.
- **`leads-pages.tsx` (servidor):** `renderLeadsInboxPage` y `renderLeadDetailPage`. Es el único gating, el de LEADS 05A/05B: flag `leads` + `view_leads`, y las acciones con `manage_leads`. También define `leadsContextFor()`.

Los enlaces de regreso, los CTA, el clic en la fila, el nombre del lead y el error definitivo usan `basePath`.

## 3. Funcionalidades disponibles en Recepcionista

Se mantienen todas las del CRM actual:
- bandeja con filtros (excepto «Turno»), búsqueda, paginación y polling;
- detalle con conversación e historial, estados de entrega, gestión de estado/resultado, asignación, vínculo con Cliente, notas y actividad;
- derivación humana, alerta de atención y reconocimiento;
- takeover y release (`Tomar conversación` / `Reactivar bot`);
- envío de mensajes humanos con el chat tomado.

**Navegación:**
- Sidebar: *Leads* (`view_leads` y flag `leads`).
- Inicio: botón «Ver leads».

**Clientes:** `/app/clientes` y la ficha no necesitaron cambios. Verifiqué en el código y con tests que un comercio solo de Recepcionista no ve ventas, presupuestos, pedidos, resumen de Turnos, historial ni «Nuevo turno». Lo controlan los permisos del mapa `reception` y el `appointments_summary`, que el backend solo envía con Turnos.

## 4. Controles de agenda

`agendaEnabled` vale `session.features.agenda_integration === true` en Recepcionista y `true` en Turnos. El backend define ese flag como Leads + acceso efectivo a Turnos (`business/context.py`).

Sin agenda, la UI oculta:
- **en la bandeja:** el filtro «Turno», el resumen del turno vinculado y las CTA «Ver turno» / «Gestionar turno»;
- **en el detalle:** el dato «Turno» del encabezado y la tarjeta de turno, con sus propuestas, confirmación, vínculo, reprogramación, creación, profesionales y «Ver en agenda». Tampoco se consulta la propuesta vigente.

**Recepcionista + Turnos (agenda_integration):** la agenda vuelve a aparecer, también dentro de `/app/recepcionista/leads`.

**Copy en Recepcionista:**
- «paciente» pasa a «cliente» en estos textos:
  - el nombre confirmado;
  - «pidió una persona»;
  - el compositor (placeholder y aria-label);
  - el remitente del historial;
  - las pistas y modales de takeover y release;
  - el mensaje «Sin mensajes…».
- «El bot derivó la consulta a una persona» reemplaza a «…para coordinar un turno».

No cambian estados, códigos ni lógica.

## 5. Tests y resultados

**Nuevos:**
- **`app/app/recepcionista/__tests__/recepcionista-leads.test.tsx` (11):**
  - mapeo de deep links y vocabulario;
  - páginas de Recepcionista con la implementación compartida y el contexto sin agenda;
  - agenda solo con `agenda_integration`;
  - gating sin plan y sin permiso;
  - Turnos sin provider;
  - matriz de redirección del layout de Turnos.
- **`leads-inbox.test.tsx`, bloque Recepcionista (5):** links y navegación, sin turno/filtro/CTA de agenda, copy, `resolveLeadCta` y Turnos intacto.
- **`lead-detail.test.tsx`, bloque Recepcionista (7):**
  - «Volver» a Recepcionista, sin tarjeta, propuestas ni acciones de agenda;
  - gestión y copy;
  - takeover;
  - chat tomado con compositor, historial, «Entregado» y release;
  - agenda con `agenda_integration`;
  - error definitivo;
  - Turnos intacto.
- **`clientes-turnos.test.tsx`, bloque Recepcionista (2):** listado y ficha sin funcionalidades ajenas.
- **Actualizados:** `sidebar-reception` (Leads presente y su gating) y `recepcionista-access` («Ver leads»).

**Corridas:**
- **Vitest dirigido** (`app/app/turnos`, `features/leads`, `app/app/clientes`, `features/business-notifications`, `components/navigation`, `app/app/recepcionista`): 34 archivos, 522 tests en verde.
- **Vitest amplio** (`src/app/app`, `src/components`, `src/features`, `src/lib`): 10 fallos, **idénticos en `ffa1632`** (worktree temporal):
  - 3 de `public-booking-link-card` (inicio de Turnos);
  - 6 de `pos.test`;
  - 1 de `onboarding-service-options`.

  No hay fallos nuevos.
- **TypeScript:** solo los 4 errores preexistentes de `google-place-autocomplete.tsx`, idénticos al baseline.
- **ESLint** sobre leads, turnos/leads, recepcionista y sidebar: 1 error y 5 warnings, los mismos que el baseline (`react/display-name` en un mock de test, `any` en tests, `setState` en effect y `err` sin usar en `sidebar.tsx`).

## 6. Riesgos pendientes

- **Deep links de notificaciones:** dependen de que `x-pathname` llegue al layout de Turnos, igual que el gate de `/app`. Si no llega, la notificación lleva a `/app/servicios`. La solución de fondo es que el backend genere `action_url` según el producto (`/app/recepcionista/leads/{id}`). Es un cambio chico, que queda para cuando se habilite tocar el backend.
- **Dependencia con Turnos:** el detalle compartido sigue importando `AppointmentFormModal` y `agendaHref`/`formatAppointmentWhen` desde módulos de Turnos y Clientes. Solo se renderizan con agenda, pero entran en el bundle de la ruta de Recepcionista. Moverlos a `features/appointments` toca Turnos y Clientes y quedó fuera de este alcance.
- **Etiqueta «Turno agendado»:** el resultado CRM `booked` mantiene esa etiqueta, que es un estado interno, también en Recepcionista. Los textos que escribe el bot (motivo y resumen) pueden mencionar turnos o pacientes; son datos, no copy.
- **Recepcionista como servicio adicional:** un negocio con otro servicio principal (por ejemplo, Gestión) y Recepcionista agregado sigue con el sidebar del principal. Entra a Leads por `/app/recepcionista/leads`.
- **Prueba en navegador:** no la hice; la validación es con Vitest, TypeScript y ESLint.
- **Snapshot de `lib/pricing`:** Vitest reescribe su fin de línea; se restauró y no se versionó.

## 7. Commits y HEAD

- `c212a95` refactor(web): one Leads CRM implementation shared by Turnos and Recepcionista
- `649b702` feat(web): Leads inside Recepcionista IA with deep links from Turnos
- `6e928b7` test(web): cover Recepcionista Leads routes, context, gating and deep links
- `7a2d69b` test(web): Clientes for a Recepcionista-only business shows no sales, quotes, orders or agenda
- docs(prod): este reporte. Es el HEAD final y está respaldado en `origin/feat/recepcionista` sin force push.
