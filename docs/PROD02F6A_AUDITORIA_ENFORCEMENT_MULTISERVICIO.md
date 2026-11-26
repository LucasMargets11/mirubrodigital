# PROD-02F6A: Auditoría de enforcement y lifecycle multiservicio

- **Fecha:** 2026-11-26
- **Repo y rama:** `mirubrodigital-release`, `feat/recepcionista`
- **Baseline:** `5516a98`
- **Bot:** `5eb3dda`, sin cambios
- **Tipo:** solo auditoría y diseño. No hay cambios de código, modelos, migraciones ni datos.
- **Referencias:** PROD-02C (RBAC multiservicio), 02D (guards), 02E1 (fuente IA), 02F1 (diseño), 02F5 (alta de servicios) y 02F5.1 (exclusión IA).

Las rutas de este informe son relativas a `services/api/src/apps/`.

---

## 1. Estado actual real

### 1.1 Resumen ejecutivo

1. **`Business.status` no participa del enforcement autenticado.** `HasBusinessMembership` y `HasEntitlement` deciden solo por la suscripción resuelta (`billing.runtime.resolve_subscription`). Un Business con `status='suspended'` y una suscripción vigente tiene acceso completo al panel. El estado global solo lo leen:
   - las páginas públicas;
   - el receiver de leads;
   - la autorización de IA (`ai_source._business_may_consume`);
   - el contador IA de Turnos (`ai_usage._source_subscription`).
2. **El estado global mezcla causas de varias suscripciones.** Cualquier suscripción de cualquier producto lo escribe (§2). Un fallo de pago de Gestión pone el Business en `past_due`, y eso apaga la IA de Recepcionista aunque Recepcionista esté al día. Al revés, la activación de cualquier producto lo pone en `active` desde cualquier estado, incluido `suspended`.
3. **Ningún código escribe hoy `Business.status='suspended'`.** No hay acción administrativa, tarea ni admin de Django que lo haga. Ese valor solo puede venir de datos legacy o de cambios manuales. No hay forma de distinguir una suspensión administrativa de una comercial.
4. **El gate comercial general depende del servicio principal.** `HasBusinessMembership` llama a `resolve_subscription(business)` sin `service_type`, es decir con `Business.service_type → default_service → 'gestion'`. Si el producto principal se suspende, el Business pierde el acceso a todos los endpoints de panel, también los de productos vigentes como Recepcionista o Turnos.
5. **Muchos endpoints de Gestión no tienen un gate comercial propio.** Catálogo, inventario, ventas, órdenes y caja (parcial) dependen de `HasBusinessMembership` (el gate global por principal) más RBAC (`HasPermission`). **Por eso no se puede relajar el gate global sin antes agregar gates por producto:** si se relaja, Gestión suspendida + Recepcionista activa abriría Gestión por RBAC.
6. **El POS operativo no tiene ningún control comercial.** `EmployeeLoginView` (`accounts/employee_views.py`) y todos los endpoints `EmployeeIsAuthenticated` (`*/pos_views.py`, `sales/pos_offline_views.py`) no consultan suscripción ni `Business.status`. Es un problema preexistente, pero bloquea el diseño objetivo.
7. **Las sucursales no heredan el estado comercial del HQ.** `BranchViewSet.create` (`business/views.py`) les crea una `business.Subscription` legacy propia, activa, copiando el plan. `resolve_subscription(branch)` resuelve esa fila y nunca mira al HQ. Si el HQ se suspende o cancela, la sucursal conserva el acceso.
8. **La activación de QR de Reseñas cambia el servicio principal.** `billing/service_activation.py::_qr_reviews_business_fields` fuerza `status='active'`, `default_service='qr_reviews'` y `service_type='qr_reviews'`. En un Business multiservicio, comprar QR cambia el contexto de todo el panel y el gate global pasa a resolver QR.

### 1.2 Piezas del enforcement actual

| Pieza | Archivo / función | Qué decide | Depende de |
|---|---|---|---|
| Gate de panel | `accounts/permissions.py::HasBusinessMembership` + `_get_enforcement_decision` | Bloquea cualquier endpoint de panel si la suscripción **principal** no da acceso. Excepción: `billing_enforcement_bypass` | Principal + `AccountProfile.account_status` (con flag de rollout). **No** mira `Business.status` ni `Membership.status` |
| Entitlement | `accounts/permissions.py::HasEntitlement` | Para prefijos `appointments.`, `gestion.` y `reception.` (`SERVICE_SCOPED_ENTITLEMENT_PREFIXES`) resuelve por servicio. Para el resto, usa la principal | Suscripción del servicio. Corre **después** de `HasBusinessMembership`, así que el gate principal manda |
| Runtime | `billing/runtime.py::resolve_subscription`, `_find_best_v2`, `_v2_grants_access` | V2 primero y legacy como respaldo. Turnos y Recepcionista quedan aislados. Los demás servicios conservan un **fallback cruzado** histórico (por ejemplo, Menú QR puede satisfacer el principal Gestión) | Solo la suscripción. Nunca `Business.status` |
| Decisión | `billing/enforcement.py::get_enforcement_decision` | Traduce el resultado a `reason_code` y datos de gracia | Solo `ResolvedSubscription` |
| Servicio | `business/service_policy.py::business_has_service`, `require_service` | Turnos: suscripción de Turnos con acceso. Otros: identidad del producto (`legacy.service` / `default_service` más `SERVICE_IMPLIES`), **sin** estado comercial | Legacy o principal |
| RBAC | `accounts/service_permissions.py::effective_permissions`, `leads_providers`, `agenda_service` | Mapa de roles del `active_service` (el principal) más Leads y Agenda de los servicios con acceso | `resolve_subscription(...).access_granted` por servicio; el principal define el mapa base |
| Agenda | `appointments/services/agenda_access.py::has_agenda_access` | Turnos resuelto por servicio y por lifecycle | Suscripción de Turnos |
| IA | `billing/services/ai_source.py::resolve_ai_source`, `_business_may_consume` | Una sola fuente, fail-closed | Suscripción de la fuente **más `Business.status`** (`active`, o `trialing` con beneficio vigente) |
| Contexto | `business/context.py::build_business_context`, `accounts/access.py::resolve_business_context` | `active_service`, plan y flags de la sesión | Principal |
| Membership | `accounts/access.py::list_user_memberships`, `select_membership` | Selecciona el Business (cookie o header). Admite herencia HQ → sucursal para owner/admin | **No filtra `Membership.status`**. Solo `request_has_permission` exige ACTIVE |
| Cuenta | `HasBusinessMembership` (rollout `SUBSCRIPTION_STATUS_ENFORCEMENT`) | Bloquea `AccountProfile.account_status='suspended'` | Flag de rollout |
| POS | `accounts/permissions.py::EmployeeIsAuthenticated`, `PinChangeNotRequired` | Solo identidad del empleado | Nada comercial |

---

## 2. Inventario de escrituras sobre `Business.status`

| # | Archivo / función | Transición | Disparador | Causa | Condición |
|---|---|---|---|---|---|
| W1 | `billing/complimentary_access_service.py::_advance_business_to_trialing` | `onboarding` / `pending_activation` → `trialing` | Beneficio bonificado (alta de cliente, F5) | Suscripción | Desde F5, solo para negocios nunca activados |
| W2 | `billing/subscription_activator.py::_activate_tenant` | **cualquiera** → `active` (o `trialing` si la suscripción es TRIALING) | Primera activación o recuperación de **cualquier** suscripción (webhook, reconciliación, finalización de Turnos) | Suscripción | **Sin guard de origen.** Reactiva negocios `suspended`/`canceled`. El docstring dice lo contrario |
| W3 | `billing/subscription_activator.py::_set_tenant_past_due` | `active` / `trialing` → `past_due` | Fallo de pago recurrente de **cualquier** suscripción (`record_failed_payment`) | Suscripción | El fallo de un producto marca todo el Business |
| W4 | `billing/cancellation_service.py::_revert_business_for_admin_cancel` (desde `cancel_subscription_immediately`) | → `onboarding` | Cancelación inmediata, por ejemplo la administrativa de Platform Admin. **`execute_cancellation`** (programada y por fin de período) **no** toca el estado global | Suscripción | Solo si no quedan otras suscripciones no canceladas (multiservicio correcto). También cancela la legacy |
| W5 | `billing/service_activation.py::_qr_reviews_business_fields` | → `active`, y además `default_service`/`service_type` → `qr_reviews` | Activación de QR de Reseñas | Suscripción | **Cambia el principal** |
| W6 | `billing/reconciliation.py::reconcile_session` (red de seguridad) | `onboarding` → `active` | Reconciliación con suscripción activa | Suscripción | Solo desde `onboarding` |
| W7 | `accounts/onboarding_views.py` (curación) | `onboarding` → `active` | Polling de onboarding con V2 `is_active` | Suscripción | Solo desde `onboarding` |
| W8 | `business/views.py::BranchViewSet.create` | Crea sucursal `active` | Alta de sucursal | Estructural | Sucursal con legacy propia |
| W9 | Alta de cliente (`accounts/admin_client_provisioning_service.py`) | Crea `onboarding` y W1 la pasa a `trialing` | Platform Admin | Administrativa y de suscripción | — |
| W10 | Comandos de seed y QA (`seed_*`, `create_checkout_test_user`, `billing_smoke_test`) | Varios | Manual | Desarrollo | Fuera de producción |

**No escriben `Business.status`:**
- Las tareas de expiración (`billing/tasks.py::_transition_active_to_past_due`, `_transition_past_due_to_suspended`, `_transition_trial_to_suspended`): solo tocan la `SubscriptionV2`. Por eso un Business puede quedar `active` con todas sus suscripciones suspendidas, o `past_due` para siempre.
- Platform Admin: no tiene ninguna acción de suspender o reactivar un Business. El detalle del cliente solo muestra `_admin_status_label`.
- No existe `ModelAdmin` de Business.

**Propagación HQ ↔ sucursal:** no existe en ningún sentido. Ninguna escritura sobre el HQ actualiza sus sucursales.

**¿Se distinguen las causas?** **No.**
- No hay campo de motivo, actor ni fecha de suspensión administrativa. `Business.suspended_at` existe, pero ningún flujo lo escribe.
- La auditoría (`AccessAuditLog`) no registra cambios de `Business.status`.
- Un `suspended` histórico es, por definición, **ambiguo**. Un `past_due` o `trialing` histórico se puede explicar, solo de forma heurística, mirando las suscripciones.

---

## 3. Matriz de protección de endpoints

Notación:
- **HBM** = `HasBusinessMembership`, el gate comercial por suscripción principal.
- **HP** = `HasPermission` (RBAC del `active_service`).
- **HE(x)** = `HasEntitlement` con entitlement `x`.
- **Riesgo si se quita el gate principal:** qué queda abierto si HBM pasa a aceptar "algún servicio con acceso".

| Grupo | Archivos | Permission classes | Entitlement / servicio | Control comercial efectivo | Depende del gate global | Riesgo si se quita el gate principal |
|---|---|---|---|---|---|---|
| Gestión: catálogo, inventario, ventas, órdenes | `catalog/views.py`, `inventory/views.py`, `sales/views.py`, `orders/views.py` | HBM + HP (más algún HE puntual en orders) | Ninguno sistemático | Solo el gate principal | **Total** | **Alto:** Gestión suspendida con otra fuente activa abre Gestión por RBAC |
| Gestión: caja, tesorería, facturas, reportes, backups, imprimibles | `cash/views.py`, `treasury/views.py`, `invoices/views.py`, `reports/views.py`, `tax_backup/`, `printables/` | HBM + HE(`gestion.*` u otro) + HP | `required_entitlement` en la mayoría | HE de Gestión resuelto por servicio, pero el principal manda antes | Parcial | Medio: según un conteo aproximado de declaraciones (`HasBusinessMembership` contra `required_entitlement`), algunos endpoints quedan sin HE: `cash` ~1 de 10, `invoices` ~3 de 9, `reports` ~4 de 11. Hay que confirmarlos uno por uno en F6B |
| POS operativo | `accounts/pos_views.py`, `cash/pos_views.py`, `catalog/pos_views.py`, `customers/pos_views.py`, `sales/pos_views.py`, `sales/pos_offline_views.py`, `orders/pos_views.py`, `accounts/employee_views.py::EmployeeLoginView` | `EmployeeIsAuthenticated` + `PinChangeNotRequired` | Ninguno | **Ninguno**, ni principal ni global | No aplica | **Ya abierto hoy:** un Business suspendido, cancelado o sin suscripción sigue vendiendo por POS |
| Recepcionista / Leads | `leads/crm_views.py`, `leads/views.py`, `leads/ai_telemetry_views.py` (HMAC), `leads/services/receiver.py` | HBM + HE(`leads` any-of Recepcionista/Turnos) + `has_agenda_access` en las acciones de agenda. Las integraciones van por HMAC, sin HBM | Entitlement por servicio (02D) | HE por servicio más el gate principal | Sí (panel) | Bajo para el panel. **El receiver** acepta leads según `Business.status ∈ {onboarding, trialing, active, past_due}` (`leads/contract.py`), sin mirar la suscripción de Recepcionista |
| Clientes compartidos | `customers/views.py` | HBM + HE(`gestion.customers` \| `appointments.customers`) (+ HP) | Any-of por servicio | HE por servicio más el gate principal | Sí | Bajo, si Recepcionista no da Clientes; hoy no lo da (02D) |
| Turnos | `appointments/views.py`, `appointments/admin_views.py` | HBM + `HasAgendaAccess` + HP | Suscripción de Turnos y lifecycle | `has_agenda_access` por servicio | Sí | Bajo para la agenda. Turnos activo con principal suspendido hoy queda **bloqueado de más** |
| Turnos públicos | `appointments/public_views.py`, `appointments/public_page.py` | Sin autenticación (`[]`) | `business_has_service('appointments')` + `Business.status ∈ PUBLISHABLE_STATUSES` | Servicio más estado global | Estado global | Si el estado global deja de reflejar el lifecycle, la página pública depende solo de la suscripción de Turnos (correcto) |
| Carta Online / Menú QR | `menu/views.py` | HBM + HP (+ `require_service('menu_qr')` en 1 vista). El público usa `AllowAny` | `require_service` es identidad, no estado comercial | Solo el gate principal | **Total** | **Alto:** con el principal relajado, la carta queda abierta sin su suscripción. El menú público depende de `Business.status` y `config.enabled`, **no** de la suscripción del menú |
| Restaurante | `resto/views.py` | HBM + `require_service('restaurante')` + HP | Identidad | Solo el gate principal | **Total** | Alto (igual que Carta) |
| QR de Reseñas | `reviews/views.py` | HBM + HP. El público usa `AllowAny` | Ninguno de servicio | Solo el gate principal | **Total** | Alto. El público depende de `Business.status` |
| Usuarios y configuración | `accounts/owner_views.py`, `accounts/views.py`, `business/views.py` (branding, sucursales, settings) | HBM + HP (`manage_users`, `manage_commercial_settings`, …) | — | Gate principal | Total | Medio: debe seguir disponible mientras haya al menos un servicio vigente |
| Billing y checkout | `billing/views.py`, `billing/appointments_lifecycle_views.py`, `billing/commercial_views.py` | HBM con `billing_enforcement_bypass=True` (15 vistas) | — | Bypass, para poder regularizar | No | Ninguno: debe quedar así |
| Auth y sesión | `accounts/views.py::LoginView`, `GooglePreauthorizedLoginView`, `MeView` | `AllowAny` o `IsAuthenticated` | — | Ninguno | No | `MeView` expone el contexto del principal: hay que extenderlo a servicios con acceso efectivo |
| Platform Admin | `accounts/platform_admin_*` | `IsPlatformStaff` + `HasInternalRole` | — | Independiente | No | Ninguno |
| Pagos de comercio / blog | `merchant_payments/views.py` (webhooks `AllowAny`), `blog/` | Público o HMAC | — | No aplica | No | Ninguno |

**RBAC no es suscripción:**
- `permissions_for_service` y los overrides (`RolePermissionOverride`, `Membership.permissions`) nunca miran el estado comercial.
- `leads_providers` incluye a Recepcionista cuando `active_service == 'reception'` **aunque no tenga acceso** (`accounts/service_permissions.py`). Hoy lo compensa que HE y HBM corren antes.
- Ningún diseño debe depender de RBAC para cerrar un producto suspendido.

---

## 4. Riesgos de seguridad

Ordenados por severidad.

1. **R1. `_activate_tenant` reactiva cualquier Business.** Lo hace desde `suspended` o `canceled` ante cualquier pago o activación de cualquier producto. Rompe "nunca reactivar automáticamente" y vuelve inútil una futura suspensión administrativa.
2. **R2. POS sin control comercial.** El login operativo y todos los endpoints POS ignoran el estado comercial y el global. Es preexistente, pero es la mayor superficie abierta del modelo actual.
3. **R3. Gate global por principal.** Relajarlo a "algún servicio" sin gates por producto abre Gestión, Carta, Restaurante y QR por RBAC. Por eso el orden de los slices importa.
4. **R4. Sucursales con legacy propia.** No heredan suspensión, cancelación ni vencimiento del HQ. `HasBusinessMembership` sobre una sucursal usa esa fila.
5. **R5. `_set_tenant_past_due` global.** Un producto en mora degrada al Business entero. Hoy eso apaga la IA de Recepcionista (`_business_may_consume`) y las páginas públicas no se ven afectadas (`past_due` es publicable). Es inconsistente.
6. **R6. Fallback cruzado en `_find_best_v2`.** Entre servicios no aislados (Gestión, Menú, Restaurante, QR), la suscripción de un producto puede satisfacer el principal de otro.
7. **R7. QR de Reseñas cambia el principal** (W5).
8. **R8. Membership suspendida.** `HasBusinessMembership` no filtra `Membership.status`. Solo `request_has_permission` lo exige, así que los endpoints protegidos únicamente con HBM aceptan miembros suspendidos.
9. **R9. Receiver de leads e IA por `Business.status`.** Ambos dependen del estado global y no de la suscripción de Recepcionista. El receiver ni siquiera exige suscripción vigente.
10. **R10. Estados históricos ambiguos.** No se puede auditar ni distinguir una suspensión administrativa de una comercial.

---

## 5. Arquitectura propuesta

### 5.1 Separación de responsabilidades

| Capa | Representa | Fuente | Quién escribe |
|---|---|---|---|
| **A. Estado administrativo global** | Si el Business puede operar (bloqueo administrativo, fraude, cierre) | Campos nuevos: `admin_status ∈ {ok, suspended, closed}`, `admin_status_reason`, `admin_status_changed_at`, `admin_status_changed_by` | **Solo** acciones explícitas de Platform Admin con auditoría estricta (`record_platform_action`). Nunca el lifecycle |
| **B. Estado comercial por producto** | Si cada producto da acceso ahora | `SubscriptionV2` por `service_type` (`_v2_grants_access` y lifecycle de Turnos) | Billing (webhooks, tareas, cancelación, beneficios) |
| **C. Permisos individuales** | Qué puede hacer cada usuario dentro de un producto con acceso | RBAC y overrides | Owner/admin |
| **D. Servicio principal** | Contexto predeterminado (navegación, mapa RBAC base) | `Business.service_type` / `default_service` | Alta y Platform Admin. **Nunca** una activación (corrige W5) |

`Business.status` pasa a ser un **resumen derivado** para compatibilidad, mientras dure la transición. No se usa para decidir acceso, salvo `admin_status`.

### 5.2 Reglas objetivo

1. Si `admin_status != ok`, se bloquean todos los servicios: panel, POS, páginas públicas, receiver e IA. La única excepción es billing y soporte, que conserva `billing_enforcement_bypass` en modo solo lectura para poder regularizar.
2. Cada endpoint de producto exige **acceso comercial de su producto** (`HasProductAccess(product)`). Esto reemplaza al gate principal:
   - Gestión: `gestion`.
   - Carta: `menu_qr*` / `restaurante`, con `SERVICE_IMPLIES`.
   - QR: `qr_reviews`.
   - Turnos: `HasAgendaAccess` (ya existe).
   - Recepcionista y Leads: HE por servicio (ya existe).
3. Los endpoints transversales (usuarios, configuración, perfil, sucursales, notificaciones, `/me`) exigen **al menos un producto con acceso efectivo** (`HasAnyProductAccess`), más RBAC.
4. RBAC y overrides solo filtran dentro de un producto con acceso. Un override nunca concede un producto sin acceso. `leads_providers` y `agenda_service` exigen `access()` también para el `active_service`.
5. Los entitlements compartidos se resuelven en modo any-of por servicio (Clientes = Gestión o Turnos; Leads = Recepcionista o Turnos), como hoy en HE.
6. **POS:** el login operativo y cada endpoint `EmployeeIsAuthenticated` exigen `admin_status == ok` y acceso comercial al producto que opera el POS (Gestión o Restaurante).
7. **Sucursales:** heredan la capa A y la capa B del HQ (`resolve_subscription` sobre `business.parent or business`). La legacy de sucursal deja de ser una fuente comercial (solo límites históricos).
8. **IA y receiver:** usan la capa A más la suscripción de la fuente (`resolve_ai_source`). Se quita la dependencia de `Business.status`.
9. **Páginas públicas:** capa A más la suscripción del producto publicado (Turnos ya lo hace; Carta y QR hoy no).
10. **El servicio principal no cambia automáticamente** (se elimina W5). Si el principal no tiene acceso, el panel abre en el primer producto con acceso, pero sin persistir el cambio.

### 5.3 Escrituras corregidas

| Escritura | Cambio propuesto |
|---|---|
| W2 | Solo `onboarding`/`pending_activation`/`trialing`/`past_due` → `active`. Nunca reactiva `suspended` ni `canceled`. Nunca toca `admin_status` |
| W3 | `Business.status` como resumen: `past_due` solo si **ningún** producto da acceso pleno. Mejor aún: dejar de escribirlo y derivarlo |
| W5 | No tocar `default_service`/`service_type`. `status` según W2 |
| Tareas de expiración | Siguen sin escribir el estado global (correcto) |

---

## 6. Tratamiento de estados históricos

- **Inventario previo (solo lectura, en una copia descartable de producción, slice F6B):** contar los Business por `status` y cruzarlos con sus suscripciones.

  | Clase | Situación |
  |---|---|
  | `suspended` + sin suscripción con acceso | **Ambiguo** |
  | `suspended` + alguna suscripción con acceso | **Ambiguo y peligroso:** hoy tiene acceso al panel |
  | `past_due` + alguna suscripción plena | Desfasado, probablemente por W3 |
  | `trialing` + sin beneficio vigente | Residual de W1 |
  | `canceled` | Cierre |

- **Migración propuesta (solo datos, en un slice propio):**
  1. Agregar los campos `admin_status*` con `admin_status='ok'` por defecto, salvo:
     - **Todo `suspended` histórico** pasa a `admin_status='suspended'` con `admin_status_reason='legacy_ambiguous'`. **Nunca se reactiva automáticamente.** Platform Admin lo revisa a mano y lo libera con un motivo auditado.
     - `canceled` pasa a `admin_status='closed'` con `reason='legacy_canceled'`, también con revisión manual.
  2. `past_due` y `trialing` históricos no cambian de capa A (son comerciales). El acceso ya lo decide la capa B.
  3. Las sucursales copian el `admin_status` del HQ cuando el HQ está bloqueado.
- **Compatibilidad:** `Business.status` se sigue escribiendo como resumen hasta que frontend, bot y reportes dejen de leerlo. Hay que verificar los lectores: `platform_admin_clients_views`, `platform_admin_reporting`, frontend `/app` y el bot. El bot no se modifica en este programa.

---

## 7. Matriz de escenarios

Notación:
- **Hoy** = comportamiento actual verificado en código.
- **Objetivo** = comportamiento después de los slices.
- Supuesto, salvo aclaración: Gestión es el servicio principal y `admin_status=ok`.

| Escenario | Panel (hoy) | Panel (objetivo) | POS | Público | IA (Recepcionista / Turnos IA) |
|---|---|---|---|---|---|
| Gestión suspendida + Recepcionista activa | Todo bloqueado por HBM principal, incluso Leads y Recepcionista | Gestión bloqueada; Leads, Recepcionista y Clientes (si otra fuente lo habilita) abiertos; configuración abierta | Hoy abierto; objetivo bloqueado (Gestión) | — | Hoy permitida si `Business.status` es `active`; objetivo permitida (fuente vigente) |
| Recepcionista suspendida + Gestión activa | Gestión abierta; Leads denegado por HE por servicio | Igual | Abierto | — | Bloqueada (correcto hoy y objetivo) |
| Turnos suspendido + Recepcionista activa (principal Turnos) | Todo bloqueado por HBM principal (Turnos) | Agenda bloqueada (`has_agenda_access`); Leads y Recepcionista abiertos, sin acciones de agenda | No aplica | Página de turnos cerrada (hoy y objetivo, por `business_has_service`) | Recepcionista permitida |
| Recepcionista suspendida + Turnos Pro activo | Abierto si el principal es Turnos; Leads queda por Turnos (any-of) | Igual; Leads sigue por Turnos | — | Turnos publicado | Sin IA (Turnos Pro no es fuente) |
| Beneficio futuro (F5) | Ese producto sin acceso hasta su inicio (`_v2_grants_access`) | Igual | — | — | Sin IA hasta el inicio |
| Beneficio vencido | Sin acceso al producto. `Business.status` queda `trialing` (residual) | Igual; el estado global deja de importar | — | Hoy publica por `trialing`; objetivo por suscripción | IA bloqueada (ventana) |
| Suscripción en gracia (`past_due` con `grace_until`) | Acceso con banner; W3 marca el Business entero `past_due` | Acceso con banner solo para ese producto; el resto no se ve afectado | Abierto si es Gestión | Publicable | **Hoy** Recepcionista se apaga si el `past_due` es de Gestión (R5); objetivo no |
| Cancelación al fin del período | Acceso hasta el fin; luego `canceled` (`execute_cancellation`). **El estado global no cambia**: puede quedar `active` sin ninguna suscripción | Igual; el acceso lo decide la suscripción | Igual | Hoy publica si el estado es publicable; objetivo por suscripción | Igual |
| Todos los servicios vencidos o suspendidos | Bloqueado (principal sin acceso); `Business.status` puede seguir `active` | Bloqueado (`HasAnyProductAccess`); billing y soporte accesibles por bypass | **Hoy abierto**; objetivo bloqueado | Hoy publica si el status es publicable; objetivo no | Bloqueada |
| Business suspendido globalmente | **Hoy no existe**: un `suspended` legacy con suscripción vigente tiene acceso al panel (R10) y la próxima activación lo reactiva (R1) | Todo bloqueado salvo billing y soporte en solo lectura; nunca se reactiva solo | Bloqueado | Cerrado | Bloqueada |
| Usuario suspendido (`Membership.status`) | Solo bloqueado donde hay HP (R8); `AccountProfile` suspendido solo con flag | Bloqueado en el gate de membership | Empleado suspendido: ya bloqueado en el login | — | — |
| HQ con sucursales | Sucursal con legacy propia, independiente del HQ (R4) | Hereda las capas A y B del HQ | Hereda | Hereda | Fuente IA del HQ (las sucursales no tienen canal propio) |
| Legacy de un solo servicio | Principal = único servicio; comportamiento sin cambios | Sin cambios (el único producto es el principal) | Se agrega el control de POS (cambio visible) | Sin cambios | Sin cambios |

---

## 8. Slices de implementación

En orden seguro. Cada slice debe ser pequeño, probado y sin cambiar la regla de asientos.

- **F6B: inventario y tests de caracterización.** Sin cambios de comportamiento.
  - Tests que fijan el comportamiento actual de la matriz §7, para detectar cambios después.
  - Script de solo lectura que clasifique los estados históricos (§6) sobre una base descartable.
  - Lista exacta de endpoints sin HE por grupo (§3, filas de Gestión, Carta, Restaurante y QR).
- **F6C: dejar de reactivar y de cambiar el principal.**
  - Guard en W2 (nunca desde `suspended`/`canceled`).
  - W5 sin tocar `default_service`/`service_type`.
  - Tests de webhook, reconciliación y QR.
  - Bajo riesgo y alto valor. No requiere migración.
- **F6D: gates por producto, aditivos.**
  - `HasProductAccess(product)` para Gestión, Carta, Restaurante y QR, sumado a HBM sin quitar nada.
  - `leads_providers` y `agenda_service` exigen acceso también para el `active_service`.
  - Como HBM todavía corre, no cambia ningún resultado actual. Solo protege antes de relajar.
- **F6E: `admin_status`.**
  - Migración de campos más migración de datos con `legacy_ambiguous`.
  - Acción de Platform Admin para suspender y liberar, con `record_platform_action`.
  - Lectura en HBM, POS, público, receiver e IA.
  - `Business.status='suspended'` deja de usarse como señal.
- **F6F: POS con control comercial.** `admin_status` y acceso a Gestión o Restaurante en `EmployeeLoginView` y en `EmployeeIsAuthenticated` (o en un permiso compañero). Necesita comunicación previa a los clientes, porque cambia un comportamiento visible.
- **F6G: relajar el gate principal.**
  - HBM pasa a `admin_status` + `HasAnyProductAccess` + membership ACTIVE (corrige R8).
  - El contexto de sesión (`/me`, `build_business_context`) expone los productos con acceso y el principal efectivo de navegación.
  - Requiere F6D completo, con tests de la matriz §7.
- **F6H: IA, receiver y páginas públicas por suscripción y capa A.** `_business_may_consume`, `ai_usage._source_subscription`, `leads/contract.ALLOWED_BUSINESS_STATUSES`, y Carta y QR públicos. Quita las dependencias de `Business.status`.
- **F6I: sucursales.** Resolución comercial por HQ; la legacy de sucursal deja de ser fuente. Requiere un inventario de sucursales reales.
- **F6J: `Business.status` derivado.** W3 deja de degradar globalmente y se elimina el fallback cruzado de `_find_best_v2` (R6), si el inventario lo confirma.
- **Fuera de alcance:** asientos multiservicio, MFA por acción e idempotencia general.

Tests que se requieren en todos los slices:
- la matriz §7 completa como tests de integración por endpoint representativo de cada grupo;
- regresión de checkout, webhooks y reconciliación (incluido 02F5.1);
- los guards 02D, la fuente IA 02E1 y el POS (test_pos_routes, que tiene fallos preexistentes que hay que comparar).

---

## 9. Bloqueantes productivos

1. **Datos de producción:** sin el inventario de estados históricos (§6) no se puede ejecutar F6E. Esta auditoría no consultó producción.
2. **POS:** el cambio de F6F es visible para clientes que hoy venden sin suscripción vigente. Requiere una decisión comercial y aviso previo.
3. **Lectores de `Business.status`:** hay que confirmar los consumidores en frontend (`/app`, onboarding), reportes de Platform Admin y el bot antes de cambiar su semántica. El bot está fuera de este programa.
4. **Sucursales:** falta un inventario de sucursales reales con legacy propia antes de F6I.
5. **Decisión pendiente:** qué puede hacer un Business con `admin_status=suspended` en billing y soporte (solo lectura, pagar, abrir tickets).
6. **Despliegue con F5/F5.1:** el alta de servicios de F5 ya permite negocios multiservicio. Hasta F6G, un Business con el principal suspendido pierde también los productos agregados. Esto hay que comunicarlo, o evitar otorgar servicios adicionales a negocios cuyo principal pueda vencer pronto.
