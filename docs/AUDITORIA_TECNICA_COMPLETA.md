# AUDITORÍA TÉCNICA COMPLETA — Sistema Mi Rubro

**Fecha:** Junio 2025  
**Alcance:** Análisis end-to-end del sistema desde registro hasta operación en producción  
**Metodología:** Lectura directa de código fuente — sin inferencias ni suposiciones  
**Cambios realizados:** Ninguno — documento de solo lectura/diagnóstico

---

## Índice

1. [Stack Tecnológico y Arquitectura General](#1-stack-tecnológico-y-arquitectura-general)
2. [Flujo de Registro y Login](#2-flujo-de-registro-y-login)
3. [Autenticación y Gestión de Sesión](#3-autenticación-y-gestión-de-sesión)
4. [Onboarding y Activación del Negocio](#4-onboarding-y-activación-del-negocio)
5. [Sistema de Billing y Suscripciones](#5-sistema-de-billing-y-suscripciones)
6. [Webhooks y Ciclo de Vida de Pagos](#6-webhooks-y-ciclo-de-vida-de-pagos)
7. [RBAC — Roles, Permisos y Control de Acceso](#7-rbac--roles-permisos-y-control-de-acceso)
8. [Multi-tenancy y Seguridad de Datos](#8-multi-tenancy-y-seguridad-de-datos)
9. [Gestión de Usuarios por el Owner](#9-gestión-de-usuarios-por-el-owner)
10. [Frontend — Flujo de UI y Protección de Rutas](#10-frontend--flujo-de-ui-y-protección-de-rutas)
11. [Tareas Periódicas y Background Jobs](#11-tareas-periódicas-y-background-jobs)
12. [Resumen de Riesgos y Recomendaciones](#12-resumen-de-riesgos-y-recomendaciones)

---

## 1. Stack Tecnológico y Arquitectura General

### Backend
| Componente | Tecnología | Versión |
|---|---|---|
| Framework | Django + DRF | 5.0 / 3.15 |
| Base de datos | PostgreSQL | via psycopg3 |
| Auth | SimpleJWT (cookie-based) | Custom `CookieJWTAuthentication` |
| Colas | Celery + Redis | — |
| Pagos | MercadoPago SDK | preapproval plans |
| API docs | drf-spectacular | — |

### Frontend
| Componente | Tecnología |
|---|---|
| Framework | Next.js (App Router) |
| Fetch | React Query + cookies |
| Estilos | Tailwind CSS |
| Auth | Server-side session vía `getSession()` → GET `/api/v1/auth/me/` |

### Arquitectura Multi-Tenant
- **Entidad tenant:** `Business` (modelo central en `business/models.py`)
- **Relación usuario↔tenant:** `Membership` (user FK + business FK, unique_together)
- **Scoping:** Todas las queries operativas filtran por `business=` obtenido de la membership resuelta
- **Branches:** `Business.parent` self-FK. Las branches heredan acceso al owner del HQ
- **Servicios duales:** `service_type` en Business: `gestion`, `restaurante`, `menu_qr`
- **14 apps Django:** accounts, business, billing, catalog, inventory, invoices, orders, cash, sales, menu, resto, customers, reports, treasury

### Resumen Arquitectónico
```
[Browser] → [Next.js App Router] → cookies (access_token, refresh_token, bid)
                                         ↓
                                  [Django DRF API]
                                    ├── CookieJWTAuthentication
                                    ├── HasBusinessMembership (billing gate)
                                    ├── resolve_request_membership() → business context
                                    └── Multi-tenant queries (business=)
                                         ↓
                                  [PostgreSQL] ← [Celery + Redis]
                                         ↓
                                  [MercadoPago API] ← webhooks
```

---

## 2. Flujo de Registro y Login

### 2.1 Registro (`RegisterView.post()` — `accounts/views.py`)

**Flujo paso a paso:**
1. Recibe `email`, `password`, `first_name`, `last_name`
2. Crea `User` con `username=email`
3. Signal `post_save` auto-crea `AccountProfile` (1:1 con User)
4. Genera token de verificación de email (SHA-256 hasheado)
5. Envía email de verificación vía `EmailService`
6. Retorna respuesta exitosa

**Lo que NO hace el registro:**
- NO crea `Business`
- NO crea `Membership`
- NO crea `Subscription`
- NO inicia ningún trial

**Hallazgo CRÍTICO — Falta `transaction.atomic` en RegisterView:**  
El flujo de registro NO está envuelto en una transacción atómica a nivel completo. Si el envío de email falla después de crear el usuario, el usuario queda creado sin email de verificación enviado. El `EmailService` usa `fail_silently=True`, por lo que la falla es silenciosa.

### 2.2 Login (`LoginView.post()` — `accounts/views.py`)

**Flujo paso a paso:**
1. Autentica con `email` + `password`
2. Llama a `_ensure_membership()` (decorado con `@transaction.atomic`):
   - Si el usuario NO tiene ninguna membership → crea `Business(status='onboarding')` + `Membership(role='owner')`
   - NO crea Subscription (comentario explícito: "billing required before access is granted")
3. Genera tokens JWT (access + refresh)
4. Setea cookies: `access_token`, `refresh_token`, `bid` (business ID)
5. Retorna `{onboarding: true/false}` según el estado del business

**Hallazgo IMPORTANTE — Business se crea en Login, no en Register:**  
La creación del Business y la Membership ocurre en `_ensure_membership()` durante el primer login, no durante el registro. Esto significa que un usuario registrado que nunca hace login no tiene Business asociado.

### 2.3 Login con Google (`GoogleAuthView` — `accounts/views.py`)

- Recibe token de Google, verifica, crea o busca User
- Misma lógica de `_ensure_membership()` post-autenticación
- Mismo patrón de cookies

---

## 3. Autenticación y Gestión de Sesión

### 3.1 Mecanismo JWT con Cookies

**Implementación:** `CookieJWTAuthentication` en `accounts/authentication.py`

| Cookie | Propósito | Lifetime |
|---|---|---|
| `access_token` | JWT de acceso | 15 minutos |
| `refresh_token` | JWT de refresco | 7 días |
| `bid` | Business ID activo | Sesión |

**Configuración JWT (settings.py):**
```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,  # ← PROBLEMA
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}
```

### 3.2 Sesión del Frontend (`MeView.get()`)

El endpoint `GET /api/v1/auth/me/` retorna el payload completo de sesión:
- Datos del usuario (id, email, nombre, verificado)
- Lista de memberships
- Business actual (id, nombre, tipo servicio, status)
- **Subscription enforcement:** `access_allowed`, `reason_code`, `grace_until`
- Servicios del negocio, features, rollout flags
- **Permisos** del usuario en el negocio actual

Este es el único endpoint que el frontend consulta para determinar el estado completo de la sesión.

### 3.3 Hallazgos de Seguridad JWT

| ID | Severidad | Hallazgo |
|---|---|---|
| **JWT-1** | **CRÍTICO** | `BLACKLIST_AFTER_ROTATION: False` — Los refresh tokens rotados NO se invalidan. Un token robado sigue siendo válido 7 días completos |
| **JWT-2** | **CRÍTICO** | No hay mecanismo de revocación de tokens. `rest_framework_simplejwt.token_blacklist` NO está en `INSTALLED_APPS`. No hay endpoint de logout server-side |
| **JWT-3** | **ALTO** | El cambio de contraseña NO invalida tokens existentes. Un atacante con un refresh token robado puede seguir refrescando después de que el usuario cambie su contraseña |
| **JWT-4** | **MEDIO** | Suspender una cuenta (vía `disable_account` o `suspend_member`) bloquea acceso a nivel de `HasBusinessMembership`, pero el JWT sigue siendo técnicamente válido hasta expiración. La protección funciona pero es a nivel aplicación, no a nivel token |

### 3.4 Logout

El logout actual (`LogoutView`) solo elimina las cookies del cliente. NO invalida el token server-side.

---

## 4. Onboarding y Activación del Negocio

### 4.1 Máquina de Estados del Business

```
onboarding → trialing → active → past_due → suspended → canceled
     │                     ↑
     └─────────────────────┘  (pago directo sin trial)
```

### 4.2 Flujo de Onboarding (Backend)

**Endpoint: `OnboardingStatusView` (GET)**  
Calcula el paso actual del onboarding:
1. `no_service_type` — No se ha elegido tipo de servicio
2. `plan_selection` — Servicio elegido, falta seleccionar plan
3. `checkout_pending` — Checkout iniciado, esperando pago
4. `done` — Onboarding completado

**Endpoint: `OnboardingSetServiceView` (POST)**
- Setea `business.service_type` (gestion/restaurante/menu_qr)
- Valida que `business.status == 'onboarding'`
- **Bypass billing enforcement** — accesible sin suscripción
- **Bypass email verification** — accesible sin email verificado

**Endpoint: `OnboardingStartCheckoutView` (POST)**
- Delega a `checkout_session_service.start_checkout()`
- **Bypass billing enforcement** — accesible sin suscripción
- **Requiere email verificado** (cuando el rollout flag está activado)

### 4.3 Flujo de Checkout (`checkout_session_service.py`)

```
start_checkout()
  ├── SELECT FOR UPDATE en sesiones abiertas del usuario
  ├── Si existe sesión válida no expirada → la reutiliza (idempotente)
  ├── Si existe sesión expirada → la marca EXPIRED
  └── Crea nueva MpCheckoutSession + plan efímero en MP
       └── Retorna {checkout_session_id, init_point, status, reused}
```

**Propiedades de diseño:**
- Idempotente por usuario+plan (SHA-256 idempotency key)
- 1 sesión : 1 MP preapproval plan (correlación perfecta para webhooks)
- Partial unique constraints en la DB para at-most-one sesión abierta por combinación
- SELECT FOR UPDATE previene race conditions

### 4.4 Hallazgos del Onboarding

| ID | Severidad | Hallazgo |
|---|---|---|
| **ONB-1** | **MEDIO** | `OnboardingSetServiceView` no requiere email verificado. Un usuario puede avanzar a selección de plan sin verificar su email. Solo `OnboardingStartCheckoutView` lo requiere (y solo con rollout flag activo) |
| **ONB-2** | **MEDIO** | Los rollout flags `email_verification_enforcement_enabled` y `subscription_status_enforcement_enabled` probablemente están OFF en producción (default=False via env vars). Esto significa que la verificación de email y el enforcement de billing pueden estar desactivados |
| **ONB-3** | **BAJO** | No existe un paso de onboarding para configurar datos del negocio (nombre, país, moneda) antes de ir al checkout. Estos valores se pueden dejar con defaults |

---

## 5. Sistema de Billing y Suscripciones

### 5.1 Dualidad del Sistema de Billing

**HALLAZGO ESTRUCTURAL CRÍTICO:** Existen **TRES modelos de suscripción** en dos apps diferentes:

| Modelo | App | Relación con Business | Estado |
|---|---|---|---|
| `business.Subscription` | business | OneToOneField | Legacy — se usa para seat limits |
| `billing.Subscription` | billing | OneToOneField | Legacy — billing app original |
| `billing.SubscriptionV2` | billing | ForeignKey | **Canónico** — sistema actual |

**¿Cómo coexisten?**
- `runtime.resolve_subscription()` busca primero `SubscriptionV2`. Solo cae a legacy si no hay V2 usable.
- Un V2 degradado (PAST_DUE, SUSPENDED) **NO** permite fallback a legacy (decisión explícita §F.2)
- `SubscriptionV2` usa FK (no OneToOne), habilitando historial de suscripciones por negocio
- Constraint: solo una SubscriptionV2 no-cancelada por business+service (`uq_subscriptionv2_active_per_service`)

### 5.2 Modelo SubscriptionV2 — Estado

```
CHECKOUT_PENDING → TRIALING → ACTIVE → PAST_DUE → SUSPENDED → CANCELED
                              ↑                         │
                              └─ (reactivación manual) ──┘
```

### 5.3 Modelos de Billing Complementarios

| Modelo | Propósito |
|---|---|
| `Plan` | Catálogo de planes (code unique, precio, intervalo, moneda) |
| `Module` | Módulos de funcionalidad con pricing (code unique, categoría, vertical) |
| `Bundle` | Colecciones de módulos con modos de pricing (precio fijo o descuento %) |
| `Promotion` | Descuentos temporales sobre bundles/módulos |
| `MpCheckoutSession` | Sesión de checkout con máquina de estados completa |
| `BillingEvent` | Log inmutable de webhooks (provider_event_id unique = idempotencia) |
| `PaymentAttempt` | Registros individuales de cobro |
| `BillingInvoiceEvent` | Tracking de pagos autorizados |
| `WebhookDelivery` | Persistencia raw de webhooks antes de procesamiento |

### 5.4 Enforcement de Billing

**`HasBusinessMembership`** (permissions.py) actúa como gate global:
1. Resuelve membership del request
2. Verifica `account_status` (si rollout flag está activo)
3. Verifica enforcement de billing (si no está bypassed)
4. Views con `billing_enforcement_bypass = True` saltan el paso 3

**`get_enforcement_decision()`** (enforcement.py) — función pura:
```
ResolvedSubscription → EnforcementDecision
  ├── access_granted (activa)
  ├── grace_period_active (dentro del período de gracia)
  ├── grace_period_expired (gracia vencida)
  ├── trial_expired
  ├── suspended
  ├── canceled
  ├── checkout_pending
  └── no_subscription
```

**`resolve_subscription()`** (runtime.py):
- Prioridad V2 → Legacy fallback
- Excluye CANCELED y CHECKOUT_PENDING del pool de V2 usables
- Si V2 existe pero está degradada, NO cae a legacy
- Retorna `ResolvedSubscription` dataclass con `source='v2'|'legacy'`

### 5.5 Hallazgos de Billing

| ID | Severidad | Hallazgo |
|---|---|---|
| **BIL-1** | **ALTO** | Triple modelo de suscripción crea complejidad innecesaria. `business.Subscription` (legacy) sigue activo para enforce de seat limits en `check_seat_limit` signal (`accounts/models.py`). Si se crea un SubscriptionV2 sin el legacy `business.Subscription`, el límite de seats no se encoforza |
| **BIL-2** | **ALTO** | `check_seat_limit` pre_save signal en Membership depende de `business.Subscription` (legacy), NO de `SubscriptionV2`. Si la migración a V2 se completa sin actualizar este signal, se pierde la limitación de asientos |
| **BIL-3** | **MEDIO** | `StartSubscriptionView` es `AllowAny` — permite crear usuarios + business + checkout sessions sin autenticación previa. Sin rate limiting, es un vector de abuso para spam de creación de cuentas |
| **BIL-4** | **MEDIO** | No existe proceso automatizado de cancelación. `expire_subscriptions` task solo hace ACTIVE→PAST_DUE, PAST_DUE→SUSPENDED, TRIALING→SUSPENDED. La cancelación depende de un flujo de billing manual no implementado |
| **BIL-5** | **BAJO** | Los modelos `Module`, `Bundle`, `Promotion` están definidos pero no es claro cuánto se usan en el flujo operativo actual vs. el plan legacy simple por plan_code |

---

## 6. Webhooks y Ciclo de Vida de Pagos

### 6.1 Recepción de Webhooks (`webhook_processor.py`)

```
MercadoPagoWebhookView (entry point)
  └── receive_webhook()
       ├── Persiste WebhookDelivery ANTES de procesar (crash-safe)
       ├── Verifica firma HMAC-SHA256
       │    └── DEV: bypass cuando DEBUG=True y no hay secret
       │    └── PROD sin secret: rechaza TODOS los webhooks
       ├── Deduplica por x_request_id + payload_hash
       └── dispatch_webhook()
            ├── subscription_preapproval → _handle_subscription_preapproval()
            └── subscription_authorized_payment → _handle_authorized_payment()
```

### 6.2 Procesamiento de subscription_preapproval

```
_handle_subscription_preapproval()
  ├── Fetch server-to-server desde MP (NUNCA confía en el body del webhook)
  ├── Correlaciona vía preapproval_plan_id → MpCheckoutSession
  ├── Upsert SubscriptionV2 (se mantiene en CHECKOUT_PENDING)
  ├── Setea provider_sub_id en SubscriptionV2
  └── Transiciona MpCheckoutSession a LINKED
```

### 6.3 Procesamiento de subscription_authorized_payment

```
_handle_authorized_payment()
  ├── Fetch server-to-server desde MP
  ├── Cross-valida IDs (preapproval_id, plan_id)
  ├── Upsert BillingInvoiceEvent (idempotente por provider_authorized_payment_id)
  ├── Busca SubscriptionV2 por provider_sub_id
  ├── Guard: no procesa si SubscriptionV2 está en estado terminal
  ├── Guard: warning si monto es cero
  └── Si status='authorized' → activate_subscription_from_invoice()
```

### 6.4 Activación de Suscripción (`subscription_activator.py`)

```
activate_subscription_from_invoice()
  ├── Pre-flight: si SubscriptionV2.is_active → ya activada, skip
  ├── SELECT FOR UPDATE dentro de transaction.atomic()
  ├── SubscriptionV2.status = ACTIVE, is_active = True
  ├── _activate_tenant(): Business.status → 'active', activated_at = now
  ├── _activate_checkout_session(): MpCheckoutSession → 'activated'
  ├── _ensure_owner_membership(): get_or_create Membership(role='owner')
  └── _log_onboarding_completed(): AccessAuditLog ONBOARDING_COMPLETED
```

### 6.5 Pagos Fallidos

```
record_failed_payment()
  ├── Si SubscriptionV2.status == ACTIVE → transiciona a PAST_DUE
  ├── Mirrors en Business.status → 'past_due'
  └── Incrementa retry_count
```

### 6.6 Hallazgos de Webhooks

| ID | Severidad | Hallazgo |
|---|---|---|
| **WH-1** | **BUENO** | El sistema NUNCA confía en el body del webhook. Siempre hace fetch server-to-server desde MP para obtener datos reales. Este es el patrón correcto de seguridad |
| **WH-2** | **BUENO** | Idempotencia robusta: `BillingEvent.provider_event_id` unique, `BillingInvoiceEvent.provider_authorized_payment_id` unique, `WebhookDelivery` deduplicación por hash+request_id |
| **WH-3** | **BUENO** | Persistencia crash-safe: `WebhookDelivery` se guarda ANTES del procesamiento |
| **WH-4** | **BUENO** | SELECT FOR UPDATE en activación previene race conditions entre webhooks concurrentes |
| **WH-5** | **MEDIO** | En desarrollo (`DEBUG=True`), la verificación de firma HMAC se bypasea si no hay secret configurado. Asegurar que en producción siempre haya `MP_WEBHOOK_SECRET` |
| **WH-6** | **BAJO** | Detección de webhooks huérfanos (sin sesión correlacionable) emite log pero no alerta. Considerar un sistema de alertas para estos casos |

---

## 7. RBAC — Roles, Permisos y Control de Acceso

### 7.1 Estructura de Permisos

**Permisos definidos en `accounts/rbac.py`:**
| Set | Cantidad |
|---|---|
| `GESTION_PERMISSIONS` | 42 permisos |
| `RESTAURANT_PERMISSIONS` | 23 permisos |
| `MENU_QR_PERMISSIONS` | 9 permisos |

**Roles por tipo de servicio:**
| Servicio | Roles disponibles |
|---|---|
| `gestion` | owner, admin, manager, cashier, staff, viewer, analyst |
| `restaurante` | owner, admin, manager, salon, kitchen, cashier, viewer |
| `menu_qr` | owner, manager, staff, viewer |

### 7.2 Matriz de Permisos

La matriz completa está hardcodeada en `SERVICE_ROLE_PERMISSIONS` (dict de dicts de sets). Cada servicio define qué permisos tiene cada rol.

**Ejemplo de permisos de gestion/owner:**
Todos los 42 permisos → acceso completo.

**Ejemplo de gestion/viewer:**
Solo permisos de lectura: `view_dashboard`, `view_products`, `view_sales`, `view_reports`, etc.

### 7.3 Overrides por Negocio

El modelo `RolePermissionOverride` permite a cada negocio personalizar permisos por rol:
- `business` + `service_type` + `role` + `permission` = permiso overrideado
- `is_granted` boolean (otorgar o revocar un permiso específico)
- `permissions_for_service()` aplica estos overrides sobre la base hardcodeada

### 7.4 Flujo de Resolución de Permisos en Runtime

```
1. MeView.get() → _session_payload()
   ├── Obtiene role del Membership
   ├── Obtiene service_type del Business
   └── permissions_for_service(service, role, business)
        ├── Carga base de SERVICE_ROLE_PERMISSIONS
        └── Aplica RolePermissionOverride del business
2. Frontend recibe permisos en la sesión
3. Frontend controla visibilidad de UI con esos permisos
4. Backend NO re-verifica permisos individuales en cada endpoint
```

### 7.5 Permisos Operativos (`operative_permissions.py`)

Registro de permisos agrupados por módulo para consumo del frontend:
```python
OPERATIVE_PERMISSIONS = {
    'dashboard': {'view_dashboard': 'Ver dashboard'},
    'products': {'view_products': 'Ver productos', 'manage_products': 'Gestionar productos', ...},
    'sales': { ... },
    ...
}
```

### 7.6 Hallazgos de RBAC

| ID | Severidad | Hallazgo |
|---|---|---|
| **RBAC-1** | **ALTO** | El backend NO verifica permisos granulares por endpoint. Los permisos se envían al frontend en la sesión, y el frontend decide qué mostrar. Pero el backend solo verifica `HasBusinessMembership` (que el usuario tenga membership activa y billing ok). Si un `viewer` hace un POST directo a `/api/v1/products/`, el backend lo acepta porque no hay verificación de permisos por acción |
| **RBAC-2** | **MEDIO** | La única protección por rol en el backend es `_is_owner()` en los endpoints de owner management. Todos los demás endpoints confían en que el frontend no mostrará acciones no autorizadas |
| **RBAC-3** | **MEDIO** | Los `RolePermissionOverride` se aplican correctamente en la sesión, pero como no hay enforcement backend, un override que remueve un permiso solo oculta la UI — no bloquea la acción |
| **RBAC-4** | **BAJO** | `EmployeeProfile` (sistema POS) tiene su propio esquema de auth con PIN de 4-6 dígitos, completamente separado del sistema de Membership/JWT. Los permisos de employees son un campo `permissions` JSONB en `EmployeeProfile` |

---

## 8. Multi-tenancy y Seguridad de Datos

### 8.1 Resolución de Contexto de Negocio

**`resolve_request_membership()`** en `accounts/access.py`:
1. Lee `bid` (business ID) de cookie o header `X-Business-Id`
2. Busca `Membership` del usuario para ese business
3. Soporta herencia de branches: si el business es una branch, el owner/admin del HQ tiene acceso
4. Cachea en `request._resolved_membership` para evitar queries repetidas
5. Construye `business_context` con business, branches, family IDs

### 8.2 Scoping de Queries — Auditoría Completa

**Se auditaron las 11 apps operativas. Resultado: TODAS filtran correctamente por business.**

| App | Método de Scoping | Verificado |
|---|---|---|
| catalog | `business=business` en `get_queryset()` | ✅ |
| inventory | `business=business` o `business=membership.business` | ✅ |
| invoices | `business=business` + `resolve_scope_ids` | ✅ |
| orders | `business=business` en queries y `get_object_or_404` | ✅ |
| cash | `business=business` en queries y `get_object_or_404` | ✅ |
| sales | `business=business` en todas las queries | ✅ |
| menu | `business=business`; vistas públicas intencionalmente sin auth | ✅ |
| resto | `business=business` | ✅ |
| customers | `business=business` | ✅ |
| reports | `_resolve_report_business_ids()` → `get_allowed_business_ids()` | ✅ |
| treasury | `BaseTreasuryViewSet.get_queryset()` filtra por `business` | ✅ |

### 8.3 Notas Defensivas Menores (no explotables)

**Nota A — Treasury void lookups:**  
En `TransactionViewSet.void()` (`treasury/views.py` ~L176-196), los lookups de entidades vinculadas para reversión (`Expense`, `FixedExpensePeriod`, `PayrollPayment`) filtran solo por `id=txn.reference_id` sin agregar `business=`. Como `txn` se obtiene vía `self.get_object()` (business-scoped) y `reference_id` es seteado server-side, **no es explotable**. Pero agregar `business=` sería defensa en profundidad.

**Nota B — BaseTreasuryViewSet fallback:**  
`BaseTreasuryViewSet.get_queryset()` usa `getattr(self.request, 'business', None)`. Si `business` fuera `None`, la query `business=None` retorna vacío (falla segura, no leak de datos). Patrón frágil pero funcional.

### 8.4 Hallazgos de Multi-tenancy

| ID | Severidad | Hallazgo |
|---|---|---|
| **MT-1** | **BUENO** | Todas las 11 apps operativas auditadas filtran correctamente por business. No se encontraron vulnerabilidades IDOR |
| **MT-2** | **BUENO** | `resolve_request_membership()` cachea correctamente y previene queries N+1 |
| **MT-3** | **BUENO** | Reports usa `get_allowed_business_ids()` para scoping multi-branch correctamente |
| **MT-4** | **MEDIO** | `DEFAULT_PERMISSION_CLASSES` está seteado a `IsAuthenticatedOrReadOnly` en settings.py. Esto significa que cualquier view que olvide declarar `permission_classes` permite GET anónimos. Todos los views auditados declaran sus permisos explícitamente, pero es peligroso como default |

---

## 9. Gestión de Usuarios por el Owner

### 9.1 Endpoints Disponibles

**V1 (Legacy) — `accounts/owner_views.py`:**
| Endpoint | Acción |
|---|---|
| `GET /owner/access/summary/` | Permisos del usuario actual |
| `GET /owner/access/roles/` | Lista roles con conteo de usuarios |
| `GET /owner/access/roles/:role/` | Detalle de rol con usuarios asignados |
| `PATCH /owner/access/roles/:role/permissions/` | Modificar permisos de un rol |
| `GET /owner/access/accounts/` | Lista de miembros del negocio |
| `POST /owner/access/accounts/:id/reset-password/` | Generar contraseña temporal |
| `POST /owner/access/accounts/:id/disable/` | Toggle active/suspended de la cuenta |
| `GET /owner/access/audit-logs/` | Visor de logs de auditoría |

**V2 (Nuevos) — `accounts/owner_views.py`:**
| Endpoint | Acción |
|---|---|
| `PATCH /owner/access/accounts/:id/role/` | Cambiar rol de un miembro |
| `POST /owner/access/accounts/:id/suspend/` | Toggle suspended/active de membership |
| `DELETE /owner/access/accounts/:id/` | Remover miembro del negocio |

### 9.2 Protecciones Implementadas

- **Owner-only:** Todos los endpoints verifican `_is_owner(membership)` → 403 si no es owner
- **Last-owner guard:** `OwnerGuardService.assert_not_last_owner()` usa `SELECT FOR UPDATE` para prevenir race conditions. Previene:
  - Cambiar rol del último owner activo
  - Suspender al último owner activo
  - Remover al último owner activo
  - Deshabilitar al último owner activo
- **Self-protection:** No puedes cambiar tu propio rol, suspenderte, o removerte
- **Audit logging:** Todas las acciones logean en `AccessAuditLog` con actor, target, detalles y IP

### 9.3 Diferencia entre disable_account vs suspend_member

| Acción | Afecta | Efecto |
|---|---|---|
| `disable_account` (V1) | `User.is_active` + `AccountProfile.account_status` | Bloquea login completo del usuario |
| `suspend_member` (V2) | `Membership.status` | Bloquea acceso a ESE negocio, usuario puede tener acceso a otros negocios |

### 9.4 Hallazgos de Gestión de Usuarios

| ID | Severidad | Hallazgo |
|---|---|---|
| **USR-1** | **CRÍTICO** | **NO EXISTE sistema de invitación.** No hay forma de que un owner agregue nuevos miembros (admin, manager, cashier, etc.) a su negocio. La única forma de crear Memberships es: (a) auto-creación en login (`_ensure_membership`), (b) auto-creación al crear una branch, (c) auto-creación en activación de suscripción. Ninguna de estas permite al owner invitar a un equipo |
| **USR-2** | **ALTO** | `reset_password` genera una contraseña temporal y la retorna en la respuesta HTTP. Esta contraseña se muestra una sola vez en el frontend. No hay forzado de cambio obligatorio del password temporal en el próximo login |
| **USR-3** | **MEDIO** | `disable_account` y `suspend_member` son dos mecanismos paralelos con semántica diferente pero confusamente similar. V1 desactiva el User completo; V2 solo suspende la Membership. No está claro cuando usar cada uno |
| **USR-4** | **BUENO** | Los v2 endpoints (`change_role`, `suspend_member`, `remove_member`) están bien implementados con `transaction.atomic`, last-owner guard, audit logging, y validación completa |

---

## 10. Frontend — Flujo de UI y Protección de Rutas

### 10.1 Middleware Next.js (`middleware.ts`)

El middleware **solo** setea un header `x-pathname`. **NO hace auth logic.** La protección de rutas se hace a nivel de layout.

### 10.2 App Layout (`app/app/layout.tsx`)

Este es el guard principal del frontend:
1. Llama a `getSession()` → `GET /api/v1/auth/me/`
2. Si no hay sesión → redirect a `/entrar`
3. Si `business.status === 'onboarding'` → redirect a `/onboarding`
4. Chequea `access_allowed` del subscription enforcement:
   - Si no → redirect a `/estado` (página de estado de cuenta) o `/planes` (selección de plan)
5. Si todo ok → renderiza la app

### 10.3 Onboarding Frontend (3 pasos)

```
/onboarding/servicio → /onboarding/plan → /onboarding/checkout
```

1. **Servicio:** Selección de tipo (gestion, restaurante, menu_qr)
2. **Plan:** Selección de plan para el servicio elegido
3. **Checkout:** Redirect a MercadoPago + polling de activación

El polling post-checkout consulta `/api/v1/billing/checkout-session/:id/status/` hasta que el status es `activated`.

### 10.4 Permisos en Frontend

- Permisos vienen en `session.permissions` (dict de permiso→boolean)
- Componentes UI condicionan visibilidad con `session.permissions.manage_products`, etc.
- **NO hay enforcement server-side** correspondiente (ver RBAC-1)

### 10.5 Hallazgos del Frontend

| ID | Severidad | Hallazgo |
|---|---|---|
| **FE-1** | **BUENO** | La protección de rutas por billing enforcement está bien implementada a nivel layout. Un usuario sin suscripción activa no puede acceder a la app |
| **FE-2** | **BUENO** | El onboarding es un flujo bien definido de 3 pasos con polling asíncrono para activación |
| **FE-3** | **MEDIO** | La protección de permisos es solo client-side. Un usuario técnico puede acceder a cualquier endpoint del backend si conoce la URL, independientemente de sus permisos |
| **FE-4** | **BAJO** | El middleware no aporta protección de auth. Toda la lógica de auth del frontend está en el layout, lo cual funciona pero no es la primera línea de defensa |

---

## 11. Tareas Periódicas y Background Jobs

### 11.1 Celery Beat Schedule

| Task | Schedule | Propósito |
|---|---|---|
| `billing.expire_subscriptions` | Cada hora (minuto 0) | Transiciones de ciclo de vida de suscripciones |

**Nota:** `expire_checkout_sessions` existe como task pero NO está en el `CELERY_BEAT_SCHEDULE`. Se usa en tests pero no se ejecuta periódicamente.

### 11.2 expire_subscriptions — Detalle

**Transiciones que ejecuta:**
1. `ACTIVE → PAST_DUE` — cuando `current_period_end < now` (setea `grace_until` si no existe, fallback 3 días)
2. `PAST_DUE → SUSPENDED` — cuando `grace_until < now`
3. `TRIALING → SUSPENDED` — cuando `trial_ends_at < now`

**Propiedades:**
- Idempotente: usa filtros status-conditional con `.update()` masivo
- No toca modelos legacy (`business.Subscription`, `billing.Subscription`)
- No cancela suscripciones (la cancelación es un flujo de billing separado)
- No reactiva suscripciones (eso lo hace el webhook de pago)
- max_retries=3, retry_delay=60s, acks_late=True

### 11.3 Hallazgos de Tareas Periódicas

| ID | Severidad | Hallazgo |
|---|---|---|
| **TASK-1** | **MEDIO** | `expire_checkout_sessions` no está en `CELERY_BEAT_SCHEDULE`. Las sesiones de checkout expiradas nunca se limpian automáticamente en producción. Solo se ejecuta en tests |
| **TASK-2** | **MEDIO** | `expire_subscriptions` mirrors el status en `Business.status` vía campo directo, pero `record_failed_payment()` en el activator también hace esta sincronización. Hay dos paths para cambiar `Business.status` que podrían divergir |
| **TASK-3** | **BUENO** | La task es idempotente, con retry, y acks_late (no pierde ejecuciones) |
| **TASK-4** | **BAJO** | Solo hay 1 task periódica configurada. Para un sistema SaaS production-ready, se esperarían más (limpieza de tokens, notificaciones de vencimiento, sincronización de estados con MP) |

---

## 12. Resumen de Riesgos y Recomendaciones

### 12.1 Clasificación por Severidad

#### CRÍTICO (Must-fix antes de producción)

| ID | Área | Descripción | Impacto |
|---|---|---|---|
| **JWT-1/JWT-2** | Auth/Sesiones | No hay revocación de tokens JWT. `BLACKLIST_AFTER_ROTATION: False`. Token robado válido 7 días | Un atacante con refresh token tiene acceso irrevocable durante 7 días. No se puede forzar logout |
| **USR-1** | Gestión Usuarios | No existe sistema de invitación para agregar miembros al negocio | Los owners no pueden crear equipos multi-usuario. Bloquea completamente el modelo de negocio SaaS multi-seat |
| **RBAC-1** | Control Acceso | Backend no verifica permisos granulares. Solo verifica membership activa + billing. Permisos son solo informativos para el frontend | Un viewer puede ejecutar cualquier acción de admin/owner via API directa. Bypaseable con cualquier cliente HTTP |

#### ALTO (Fix prioritario)

| ID | Área | Descripción | Impacto |
|---|---|---|---|
| **RATE-1** | Seguridad | No hay rate limiting en login, register, forgot-password, StartSubscription | Vulnerable a brute-force de credenciales, spam de creación de cuentas, y abuso del endpoint público de suscripción |
| **BIL-1/BIL-2** | Billing | Triple modelo de suscripción. `check_seat_limit` signal depende del modelo legacy | La migración completa a V2 romperá el enforcement de seat limits si no se actualiza el signal |
| **JWT-3** | Auth | Cambio de password no invalida tokens existentes | Cambiar password no protege contra tokens ya robados |
| **USR-2** | Gestión Usuarios | Password temporal no fuerza cambio obligatorio | Password temporal podría quedar como password permanente |

#### MEDIO (Fix planificado)

| ID | Área | Descripción | Impacto |
|---|---|---|---|
| **MT-4** | Multi-tenant | `DEFAULT_PERMISSION_CLASSES = IsAuthenticatedOrReadOnly` | Cualquier view sin `permission_classes` explícito permite GET anónimos |
| **BIL-3** | Billing | `StartSubscriptionView` es AllowAny sin rate limit | Vector de abuso para spam masivo de cuentas |
| **ONB-1/ONB-2** | Onboarding | Rollout flags probablemente OFF. Email verification no enforceada | Usuarios no verificados pueden avanzar en el flujo |
| **RBAC-2/RBAC-3** | RBAC | Protección por rol solo en owner endpoints. RolePermissionOverride no se enforce en backend | Los overrides de permisos son puramente cosméticos en el backend |
| **FE-3** | Frontend | Protección de permisos solo client-side | Seguridad por obscuridad, no por enforcement real |
| **TASK-1** | Tasks | `expire_checkout_sessions` no está schedulada | Sesiones de checkout expiradas se acumulan indefinidamente |
| **USR-3** | Gestión | Dos mecanismos de suspensión paralelos (disable_account vs suspend_member) | Confusión operativa sobre cuál usar |
| **WH-5** | Webhooks | HMAC bypass en development | Asegurar que MP_WEBHOOK_SECRET esté siempre configurado en prod |
| **TASK-2** | Tasks | Business.status se sincroniza desde dos paths independientes | Posible divergencia de estados entre SubscriptionV2 y Business |
| **BIL-4** | Billing | No existe proceso automatizado de cancelación | Suscripciones suspendidas quedan en limbo indefinidamente |

#### BAJO (Mejora futura)

| ID | Área | Descripción |
|---|---|---|
| **ONB-3** | Onboarding | No hay paso de configuración de datos del negocio en onboarding |
| **RBAC-4** | Auth | EmployeeProfile (POS) es sistema completamente separado de Membership |
| **FE-4** | Frontend | Middleware no aporta protección de auth |
| **WH-6** | Webhooks | Webhooks huérfanos solo logean, no alertan |
| **TASK-4** | Tasks | Solo 1 task periódica para un sistema SaaS completo |
| **BIL-5** | Billing | Module/Bundle/Promotion — nivel de adopción en flujo actual poco claro |

### 12.2 Lo Que Está Bien Hecho

| Área | Fortaleza |
|---|---|
| **Multi-tenancy** | Todas las 11 apps operativas filtran por business correctamente. No se encontró ningún IDOR |
| **Webhook Processing** | Diseño ejemplar: persistencia crash-safe, verificación server-to-server (nunca confía en body), idempotencia por unique constraints, SELECT FOR UPDATE |
| **Checkout Flow** | Idempotente, con correlación 1:1 session↔plan, SELECT FOR UPDATE contra race conditions, partial unique constraints |
| **Last-Owner Guard** | Protección robusta con SELECT FOR UPDATE en todos los endpoints de modificación de usuarios |
| **Audit Logging** | AccessAuditLog con 30+ tipos de acción, actor tracking, entity tracking con before/after JSON |
| **Subscription State Machine** | SubscriptionV2 tiene estados bien definidos con transiciones claras y constraints de DB |
| **CORS** | Correctamente configurado, sin wildcards, orígenes por env var |
| **Billing Enforcement** | EnforcementDecision con reason codes granulares permite UI informativa en el frontend |

### 12.3 Recomendaciones Prioritarias (Roadmap Sugerido)

**Fase 1 — Seguridad Crítica (antes de producción):**
1. Activar JWT blacklisting: agregar `token_blacklist` a INSTALLED_APPS, setear `BLACKLIST_AFTER_ROTATION: True`, implementar logout server-side
2. Agregar rate limiting global: `AnonRateThrottle` default + throttles específicos en login (5/min), register (3/min), forgot-password (3/min), StartSubscription (3/min)
3. Implementar enforcement de permisos backend: crear un decorator/mixin `RequiresPermission('manage_products')` que verifique contra la sesión del usuario
4. Cambiar `DEFAULT_PERMISSION_CLASSES` a `IsAuthenticated`

**Fase 2 — Funcionalidad Crítica:**
5. Construir sistema de invitación por email con asignación de rol y expiración
6. Migrar `check_seat_limit` signal de `business.Subscription` a `SubscriptionV2`
7. Forzar cambio de password en próximo login cuando se usa password temporal
8. Activar rollout flags de email verification y subscription enforcement

**Fase 3 — Estabilización:**
9. Agregar `expire_checkout_sessions` al `CELERY_BEAT_SCHEDULE`
10. Implementar proceso de cancelación automatizada
11. Unificar mecanismos de suspensión (elegir disable_account o suspend_member, deprecar el otro)
12. Plan de migración para eliminar los modelos legacy de suscripción

---

**Fin de la auditoría técnica.**  
Ningún cambio fue realizado en el código. Este documento refleja exclusivamente el estado actual del sistema según lectura directa del código fuente.
