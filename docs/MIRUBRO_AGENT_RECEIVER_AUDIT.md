# MIRUBRO AGENT 01 — Auditoría del receptor de Leads del agente

> Solo auditoría y diseño. No se creó ningún modelo, migración, endpoint, permiso ni UI.
> Fecha: 2026-10-04 · Rama auditada: `develop` (árbol de trabajo con cambios sin commitear, incluido el traslado `/app/gestion/clientes` → `/app/clientes`).
>
> Nota: `docs/MIRUBRO_AGENT_CONTRACT.md` vive en el repo de `dental-whatsapp-agent`, no en este. Se validaron
> las decisiones del contrato tal como fueron enunciadas (Agent → MiRubro, snapshot `lead.sync`, PUT idempotente,
> `external_lead_id` del agente, `version` monotónica, HMAC, MiRubro caído no bloquea al agente, ownership dividido,
> sin DB ni código compartidos).

---

## 1. Resumen ejecutivo

- **No existe ningún concepto de Lead** en MiRubro (ni Prospect, Inquiry, ContactRequest, Conversation ni Handoff). Hace falta una entidad nueva, en una app nueva. No hay nada que reutilizar a la fuerza.
- **No existe autenticación service-to-service**: toda la API es usuario (JWT en cookie + sesión) o empleado (token POS). El receptor necesita una clase de autenticación nueva. Sí hay patrones reutilizables: HMAC + `compare_digest` (webhook MP), cifrado Fernet con clave dedicada (`merchant_payments/crypto.py`), notificaciones idempotentes (`BusinessNotification`), idempotencia por constraint única (`CustomerMessageDelivery`, `WebhookDelivery`).
- **No existe integración con WhatsApp Cloud API**: lo único de WhatsApp es `BusinessBranding.whatsapp_phone` (contacto público para links `wa.me`) y un flag huérfano `whatsapp_bot` del vertical Restaurante. El mapping `phone_number_id → Business` necesita un modelo nuevo.
- **El contrato encaja** con la arquitectura real, con correcciones puntuales: `external_lead_id` UUID, `business_id` = PK entera, tenant derivado de la vinculación (no de headers), `external_conversation_id` opaco con HMAC (no UUIDv5), `event_id` scopeado por instancia, firma con canonical string completo.
- **Hallazgo P1 de matching**: la normalización actual de teléfono de `Customer` es "solo dígitos" y deliberadamente no infiere prefijos AR. Un teléfono E.164 del agente (`+5491112345678`) **no matchea** un Customer cargado como `11 1234-5678`. Usar el matcher actual tal cual daría casi siempre "sin coincidencias".
- **MiRubro está listo para implementar el receptor** (no hay bloqueantes P0 en el código existente), condicionado a cerrar los cambios de contrato de §20 y la decisión comercial de entitlement (§13).

---

## 2. Arquitectura relevante de MiRubro

Backend Django + DRF en `services/api/src`, PostgreSQL, Celery + Redis, cache `django_redis` compartido. Rutas montadas en `config/urls.py` bajo `api/v1/<app>/`, todas con barra final.

| Área | Archivo | Modelo / servicio | Responsabilidad | Reutilización |
|---|---|---|---|---|
| Business | `apps/business/models.py` | `Business` (PK `BigAutoField`), `Subscription`, `BusinessBranding`, `CommercialSettings` | Tenant; `parent`/`branches` para sucursales; `status` (onboarding/trialing/active/past_due/suspended/canceled); `slug` mutable/derivado; `timezone`, `country` | FK destino de todo; `status` para gating de ingesta |
| Contexto tenant | `apps/business/context.py`, `apps/accounts/access.py` | `build_business_context`, `resolve_request_membership` | Resuelve Business por `X-Business-Id`/cookie sobre las memberships del usuario | **No** aplica al receptor (no hay usuario); el tenant sale de la vinculación del canal |
| Membership | `apps/accounts/models.py` | `Membership` (`role`, `status`, `branch_scope`, `permissions` JSON) | Usuarios del negocio; `unique(user, business)` | Validar `assigned_to` (membership activa del Business) |
| RBAC | `apps/accounts/rbac.py`, `rbac_registry.py`, `permissions.py` | Sets por servicio, `SERVICE_ROLE_PERMISSIONS`, `RolePermissionOverride`, `HasPermission` + `permission_map`, `HasEntitlement` | Permisos por servicio × rol, overrides por Business | Agregar permisos de leads siguiendo el mismo patrón |
| Entitlements | `apps/business/entitlements.py`, `features.py` | `PLAN_ENTITLEMENTS`, `CUSTOMER_CORE_ENTITLEMENTS` | Gating por plan/add-on | Nuevo entitlement para el módulo |
| Customers | `apps/customers/models.py` | `Customer` (PK UUID, `phone` texto libre, sin unicidad de teléfono), `CustomerNote`, `CustomerReminder`, `CustomerContactPreferences`, `CustomerMessageDelivery` | Padrón canónico compartido (Gestión + Turnos) | Vínculo opcional `Lead.customer`; nunca escritura por sync |
| Teléfono | `apps/customers/phone.py`, `apps/business/whatsapp.py` | `normalize_phone_for_matching`, `filter_by_phone_key`, `normalize_whatsapp_phone` | Matching por dígitos (sin inferir país) / normalización AR→E.164 para wa.me | Ver §11 |
| Turnos | `apps/appointments/models.py`, `services/*` | `Appointment` (`customer` FK nullable, snapshots `customer_*`, `status`, `source` manual/public), `AppointmentPayment`, `customer_link.resolve_customer_for_appointment`, `availability`, `booking`, `payment` | Agenda, disponibilidad, profesionales, señas MP | Destino futuro Lead → Appointment, solo por acción humana |
| Notificaciones | `apps/notifications/models.py`, `business_notifications.py`, `views.py` | `BusinessNotification` (kind, severity, `dedupe_key` única por Business, `read_at` compartido), `create_business_notification`, `on_commit_safely`, `KIND_VIEW_PERMISSIONS` | Bandeja in-app del equipo; `GET /api/v1/notifications/business/` devuelve `unread_count` | Handoff → nuevo kind; reutilización directa |
| Audit | `apps/accounts/models.py` | `AuditLog` (acciones de seguridad/admin, `details` JSON, ip, user_agent) | Auditoría de acceso/administración | **No** para eventos de lead (no meter PII ahí) |
| Webhooks | `apps/billing/models.py`, `webhook_processor.py`, `webhook_lifecycle.py` | `WebhookDelivery` (persiste `headers_json` + `body_json`, `payload_hash`, lifecycle con lease/reintentos), `_verify_mp_signature` | Ingesta MP | Patrón de firma y hash sí; **no** copiar la persistencia del body (PII) |
| Mercado Pago merchant | `apps/merchant_payments/` | `MercadoPagoConnection` (OAuth por Business), `EncryptedTextField`, `crypto.py` (Fernet, clave dedicada, sin fallback a plaintext) | Tokens MP cifrados en reposo | Patrón de cifrado para secretos del agente (clave propia) |
| Integraciones | — | — | No existe app `integrations`, ni `IntegrationCredential`, ni modelo de canal | Todo nuevo |
| Auth técnica | `apps/accounts/authentication.py` | `CookieJWTAuthentication`, `EmployeeTokenAuthentication` | Usuario / empleado POS | Ninguna sirve; hace falta `AgentHmacAuthentication` |
| Frontend | `apps/web/src/components/navigation/sidebar.tsx`, `apps/web/src/app/app/*` | Secciones por servicio; Turnos en `/app/turnos/*`; Clientes top-level `/app/clientes` | Navegación con `permissionKey` / `featureKey` | Ubicación del módulo futuro (§18) |
| Logging | `config/settings.py` | `LOGGING` JSON en prod, `django.request` a WARNING; sin Sentry en el repo | Logs técnicos | Ver §17 |

---

## 3. Modelos reutilizables

| Reutilizar tal cual | Reutilizar el patrón (no el modelo) | No reutilizar |
|---|---|---|
| `Business` (FK), `Membership` (asignación), `Customer` (vínculo opcional), `Appointment` (vínculo opcional), `BusinessNotification` + `create_business_notification` + `on_commit_safely` + `KIND_VIEW_PERMISSIONS`, `HasPermission`/`HasEntitlement`, `normalize_whatsapp_phone`, `filter_by_phone_key` | Fernet con clave dedicada (`merchant_payments/crypto.py`), HMAC + `hmac.compare_digest` (`_verify_mp_signature`), `payload_hash` SHA-256, constraint única como idempotencia (`CustomerMessageDelivery.idempotency_key`), `select_for_update` + transacción corta (`payment.py`) | `WebhookDelivery` (guarda body y headers completos → PII), `AuditLog` (dominio seguridad/admin), `BusinessBranding.whatsapp_phone` (contacto público), `CustomerCommunicationSettings` (salida a clientes), `CustomerMessageDelivery` (envíos salientes), flag `whatsapp_bot` (Restaurante, sin implementación) |

---

## 4. ¿Existe el concepto de Lead?

Búsqueda global (modelos, servicios, vistas, migraciones) de `Lead`, `ContactLead`, `CustomerLead`, `Prospect`, `Inquiry`, `ContactRequest`, `Conversation`, `Handoff`: **cero resultados** (el único match de `Lead*` es `TopProductsLeaderboardView`, irrelevante).

**Veredicto: C — no existe, hace falta uno nuevo.**

El candidato tentador sería `Customer`, y debe descartarse: `Customer` es el padrón canónico compartido por Gestión (ventas, presupuestos, facturas) y Turnos; un Lead conversacional es una intención no verificada (puede ser un familiar que consulta por otro, un número equivocado, spam). Convertirlo automáticamente en `Customer` contaminaría el padrón y las métricas de Gestión. El Lead vive aparte y se vincula a un `Customer` solo por decisión humana.

---

## 5. Identidad del Business

- PK: `BigAutoField` (entero de 64 bits) — `apps/business/migrations/0001_*`, `DEFAULT_AUTO_FIELD = BigAutoField`.
- Serialización actual: entero JSON (`'id': membership.business_id` en el payload de sesión, `apps/accounts/views.py`). En URLs: `<int:business_id>` (`menu-qr`).
- Resolución de tenant en APIs: `resolve_request_membership` sobre las memberships del usuario, elegida por header `X-Business-Id` o cookie; HQ owner/admin hereda acceso a sucursales.
- Alternativos: `slug` (único, nullable, **derivado del nombre y por lo tanto no estable como identidad**); no existe `public_id`.

**Decisión:** `business_id` en el contrato = **`Business.pk` como entero JSON** (no string, no slug). Es el único identificador inmutable que existe.

Regla de seguridad: el `business_id` del payload **no autoriza nada por sí mismo**. MiRubro deriva el Business de la vinculación activa `(agent_instance, phone_number_id)` y exige que coincida con el `business_id` informado; si no coincide → `409 business_mismatch`. Un lead nunca cambia de Business una vez creado. El receptor **no** usa `X-Business-Id` ni cookies.

Sucursales: el `phone_number_id` se vincula al Business concreto (HQ o sucursal) que atiende ese número; el owner/admin de HQ lo ve por la herencia existente.

---

## 6. Mapping `phone_number_id → Business`

Ninguno de los lugares existentes sirve:

- `BusinessBranding.whatsapp_phone`: es el número público para links `wa.me`, opt-in del negocio, sin relación con Meta.
- `CustomerCommunicationSettings`: configuración de comunicaciones salientes a clientes.
- `MercadoPagoConnection`: OAuth de pagos.
- No existe `WhatsAppIntegration`, `BusinessCommunicationSettings` ni `IntegrationCredential`.

**Recomendación:** modelo nuevo en la app nueva, nombre tentativo **`AgentChannel`** (canal de WhatsApp atendido por una instancia de agente):

| Campo | Notas |
|---|---|
| `id` UUID | |
| `business` FK | Business que atiende el número |
| `agent_instance` FK | Instancia autorizada a sincronizar leads de este número |
| `provider` | `whatsapp_cloud` (único valor inicial) |
| `phone_number_id` | ID de Meta (no es PII del paciente) |
| `display_phone_e164` | Número del negocio, solo informativo |
| `is_active` | Activar/desactivar canal sin borrar historia |
| `created_at`, `deactivated_at` | |

Constraints:
- `UniqueConstraint(provider, phone_number_id, condition=Q(is_active=True))` → un número no puede estar activo en dos Business a la vez (reasignar = desactivar + crear).
- Varios canales activos por Business permitidos (múltiples números a futuro).
- **No se guardan access tokens de Meta**: MiRubro no habla con Meta; el owner de WhatsApp es el agente. Si algún día MiRubro enviara por Cloud API, el token iría cifrado con su propia clave Fernet, en otro modelo.

Fuente de verdad: MiRubro (valida). El agente mantiene su propia copia de configuración; el alta inicial es manual vía shell/management command, igual que el aprovisionamiento piloto de Turnos.

---

## 7. Endpoint

Convenciones auditadas:
- Prefijo `api/v1/<dominio>/`, siempre barra final (`APPEND_SLASH` por defecto; ninguna ruta sin barra).
- Path params UUID con `<uuid:...>` en todos los recursos con PK UUID (customers, appointments, notifications).
- Escritura: PATCH es lo habitual (varias vistas restringen `http_method_names` a `get/patch`). No hay un PUT "upsert" hoy, pero PUT con snapshot completo + idempotencia es semánticamente correcto y no choca con nada.
- No existe namespace `integrations`. Los namespaces "técnicos" actuales (`billing/webhooks/...`, `menu/mercadopago/...`) están atados a su dominio.

**Decisión: aprobado con correcciones.**

```
PUT /api/v1/integrations/agent/leads/<uuid:external_lead_id>/
```

- `integrations/agent/` es correcto: separa claramente tráfico máquina-a-máquina del API de panel (`/api/v1/leads/...` quedará para el CRM humano, con JWT). Montar la app nueva bajo `path('api/v1/integrations/agent/', include(...))`.
- `external_lead_id` **debe ser UUID** (v4 o v7) para usar `<uuid:>` y no aceptar strings arbitrarios en el path.
- Vista con `authentication_classes = [AgentHmacAuthentication]` (sin cookie/sesión → sin CSRF), `permission_classes` propia, `http_method_names = ['put']`, throttle propio por `key_id`.
- Códigos de respuesta propuestos:

| Caso | HTTP | `result` |
|---|---|---|
| Lead creado | 201 | `created` |
| Versión nueva aplicada | 200 | `applied` |
| Misma versión, mismo hash | 200 | `duplicate` |
| Versión menor a la aplicada | 200 | `stale` |
| Misma versión, hash distinto | 409 | `version_conflict` |
| `business_id` ≠ vinculación, o lead existente de otro Business | 409 | `business_mismatch` |
| Canal inactivo / Business suspendido o cancelado | 403 | `channel_disabled` / `business_inactive` |
| Firma, key o timestamp inválidos | 401 | `invalid_signature` (sin detalle) |
| Validación | 400 | códigos de campo, **sin eco de valores** |
| Throttle | 429 | — |

Política del agente: reintentar solo red/408/429/5xx con backoff; 4xx son terminales para esa versión; 403 de canal = estacionar el lead localmente y reintentar con cadencia lenta.

---

## 8. Modelo receptor conceptual

Naming: los modelos existentes usan `<Dominio><Cosa>` en singular y sin sufijo técnico (`CustomerNote`, `CustomerReminder`, `AppointmentPayment`, `BusinessNotification`). "ConversationLead" ata el concepto CRM a su origen; "AgentLead" igual. El lead es un concepto CRM que mañana puede venir de otro origen (formulario web, Instagram).

**Recomendación: app `apps.leads`, dos modelos con separación estructural:**

### `Lead` — estado CRM (lo escriben humanos)
| Campo | Notas |
|---|---|
| `id` UUID | ID interno de MiRubro (el del panel) |
| `business` FK | Inmutable |
| `source` | `whatsapp_agent` (único valor inicial) |
| `status` | CRM, ver §10 |
| `outcome` | Motivo de cierre CRM, ver §10 |
| `assigned_to` FK user nullable | Validado contra membership activa |
| `customer` FK nullable `SET_NULL` | Solo por acción humana |
| `appointment` FK nullable `SET_NULL` | Solo por acción humana |
| `needs_attention_at` | Se setea en la transición de handoff (lo único que el sync "toca" del lado CRM; ver §9) |
| `closed_at`, `closed_by` | CRM |
| `created_at`, `updated_at` | |

Notas humanas: modelo relacionado `LeadNote` (mismo patrón que `CustomerNote`: `author`, `body`, constraint `body != ''`), no un campo de texto pisable.

### `LeadAgentState` — réplica del agente (lo escribe solo el sync), OneToOne con `Lead`
| Campo | Notas |
|---|---|
| `lead` OneToOne | |
| `agent_instance` FK | |
| `channel` FK `AgentChannel` | |
| `external_lead_id` UUID | `UniqueConstraint(agent_instance, external_lead_id)` |
| `external_conversation_id` | Opaco (§15), max 64, índice |
| `patient_name` | Texto ≤150, lo informado por el bot |
| `whatsapp_profile_name` | ≤150, baja confianza |
| `phone_e164` | Normalizado por MiRubro (`+549…`); se rechaza si no normaliza |
| `reason`, `preferred_time` | Texto acotado (≤500) |
| `urgency` | Enum cerrado del contrato |
| `agent_status` | Enum cerrado del contrato |
| `handoff_requested` bool, `handoff_reasons` JSON lista de códigos | Lista de códigos de un enum cerrado, no texto libre |
| `summary` | ≤2000 |
| `opened_at`, `closed_at`, `close_reason`, `last_message_at` | Fechas del agente |
| `applied_version` bigint, `payload_hash` char(64), `last_event_id` UUID, `last_synced_at` | Idempotencia y diagnóstico |

### Qué NO se almacena
Mensajes/transcripciones, prompts y respuestas del LLM, payload crudo, headers, firma, `wa_id`, tokens de Meta, scores internos del modelo, metadatos de la cuenta WhatsApp del paciente más allá del profile name. Si en el futuro se quiere ver la conversación, se consulta al agente on-demand (no se replica).

---

## 9. Ownership: estado del agente vs estado CRM

Regla validada: `agent_*` = réplica de lo que informó el bot; campos CRM = decisiones humanas en MiRubro.

La separación en dos tablas la hace estructural: el código del sync solo escribe `LeadAgentState` y, al crear, inserta un `Lead` con defaults (`status=new`, sin asignación, sin customer). Después **nunca** actualiza `Lead`, con una única excepción acotada:

- En la transición `handoff_requested: false → true` (o primer sync con `true`) setea `Lead.needs_attention_at` si está vacío y dispara la notificación. No cambia `status`, ni `assigned_to`, ni reabre un lead cerrado.

El sync nunca: renombra ni edita `Customer`, toca `LeadNote`, cambia `status`/`outcome`, reasigna, vincula customer/appointment, ni cierra el `Lead`. Que el agente marque `agent_status=closed` solo se muestra como badge.

Lead cerrado en CRM que recibe actividad nueva del agente: se aplica el snapshot (réplica), no se reabre; si trae handoff nuevo, se notifica igual y el panel lo muestra como "actividad posterior al cierre". Un episodio nuevo del paciente debería llegar con un `external_lead_id` nuevo (decisión del lado agente, a confirmar en el contrato).

Patrón coherente con lo existente: `Appointment.customer_*` son snapshots que nunca se reescriben desde `Customer` y `Customer` nunca se edita desde una reserva pública (`customer_link.py`).

---

## 10. Estados CRM

Patrones existentes: `TextChoices` en minúscula, pocos estados y el "por qué" en un campo aparte (`CustomerMessageDelivery.status` + `skip_reason`/`failure_code`; `Appointment.status` con estados operativos).

`pending`/`contacted` son ambiguos para recepción (¿pendiente de qué?; contactar es una acción, no un estado). `converted` mezcla estado y resultado.

**Propuesta mínima:**

`status`
- `new` — llegó, nadie lo tomó.
- `in_progress` — alguien lo está gestionando (se setea al asignar o al primer cambio manual).
- `closed` — terminado.

`outcome` (obligatorio al cerrar, nulo antes)
- `booked` — se agendó turno (idealmente con `appointment` vinculado).
- `linked_customer` — se identificó/creó el cliente sin turno.
- `not_interested`
- `unreachable`
- `duplicate`
- `spam`
- `other`

"Pendiente de atención humana" no es un estado: es `needs_attention_at` no nulo + `status != closed`, y alimenta la bandeja. `agent_status` queda en `LeadAgentState`, separado.

---

## 11. Customer matching

Estado actual:
- `Customer.phone`: `CharField(64)` texto libre, sin validación de formato, sin unicidad, índice `(business, phone)`.
- `apps/customers/phone.py::normalize_phone_for_matching`: clave = solo dígitos (6–15), sin inferir país ni `0`/`15`/`9`. Reproducible en SQL (`filter_by_phone_key` con `regexp_replace`). Decisión explícita de CUSTOMER 01 para no fusionar fijos con móviles.
- `apps/business/whatsapp.py::normalize_whatsapp_phone`: sí infiere AR (`011 1234-5678` → `5491112345678`, `+54 11…` → `549 11…`); no es reproducible en SQL.
- `customer_link.resolve_customer_for_appointment`: 1 match activo → reutiliza sin editar; 0 → **crea** Customer mínimo; >1 → no vincula.

**Problema (P1):** el agente envía `+5491112345678`; clave de matching `5491112345678`. Un Customer cargado como `11 1234-5678` tiene clave `1112345678`. No matchean. Con el matcher actual casi ningún lead encontraría su cliente.

**Regla propuesta (solo sugerencia, sin vínculo automático):**

1. MiRubro normaliza el teléfono del payload con `normalize_whatsapp_phone` → `549XXXXXXXXXX` (no confía en la normalización del agente). Si no normaliza → 400.
2. Para un móvil AR `549` + N (10 dígitos) se generan claves candidatas: `549N`, `54N`, `N`, `0N`. Para otros países: solo la clave E.164.
3. `filter_by_phone_key` sobre `Customer` activos del Business con `__in` de esas claves (sigue siendo SQL, sigue siendo tenant-scoped).
4. Resultado:
   - 0 matches → Lead sin Customer, sin sugerencia.
   - 1 match → **sugerencia** visible ("posible cliente: X"). El vínculo lo confirma un humano. No se vincula automáticamente: en una clínica es habitual que un padre escriba por un hijo (mismo teléfono, otra persona).
   - >1 match → "varios clientes con ese teléfono", el humano elige.
   - Formatos con `15` (`011 15 1234-5678`) no se cubren → sin match → humano. Aceptable.
5. Nunca se crea `Customer` desde el sync. La creación ocurre cuando un humano lo pide desde el lead, o implícitamente al agendar (ver §19).

La sugerencia se calcula al leer (no se persiste) o se cachea en `LeadAgentState` sin FK; nunca es fuente de verdad.

Mejora futura (no ahora): columna normalizada en `Customer` (p. ej. `phone_e164`) poblada por backfill, para matching exacto e indexado.

---

## 12. Handoff y notificaciones

Infraestructura existente y reutilizable sin cambios de diseño:
- `BusinessNotification` con `UniqueConstraint(business, dedupe_key)` y `create_business_notification` get-or-create idempotente.
- `on_commit_safely`: se crea después del commit; un fallo no revierte el sync ni devuelve error al agente.
- `KIND_VIEW_PERMISSIONS`: un kind puede habilitarse para roles fuera de owner/admin por permiso RBAC (mecanismo de CUSTOMER 07C.1).
- `GET /api/v1/notifications/business/` ya devuelve `unread_count` → el badge/contador existe.
- `action_url` restringido a `/app/...`.

Al recibir `handoff_requested = true` (transición):
1. `Lead.needs_attention_at = now` (si estaba vacío).
2. Nuevo kind `agent_lead_handoff` (≤48 chars), `severity=critical` si `urgency` es la máxima, `info` si no.
3. `dedupe_key = agent_lead_handoff:{lead.id}:{applied_version}` → un reintento del mismo sync no duplica; un handoff nuevo en otra versión sí notifica.
4. Título y mensaje **sin PII** ("Un paciente pidió hablar con recepción"), `related_object_type='lead'`, `related_object_id=lead.id`, `action_url=/app/.../<lead.id>`. El nombre se ve al abrir el lead (con permisos), no en la fila de notificación.
5. `KIND_VIEW_PERMISSIONS['agent_lead_handoff'] = 'view_leads'` — sin esto, por defecto solo lo verían owner/admin.

Bandeja: la "inbox" es la lista de leads filtrada (`status != closed`, ordenada por `needs_attention_at`), no una entidad nueva. Asignación: manual (`assigned_to`); no hay auto-asignación en MVP. No se envían emails ni WhatsApp por el handoff.

---

## 13. RBAC

Patrón real: sets por servicio en `rbac.py`, mapa servicio × rol en `SERVICE_ROLE_PERMISSIONS`, registro descriptivo en `rbac_registry.py`, overrides por Business (`RolePermissionOverride`), vistas con `HasPermission` + `permission_map` por método, entitlement aparte con `HasEntitlement`.

Nombres: siguiendo `view_customers`/`manage_customers`, el permiso describe el objeto CRM, no el origen:

| Permiso | Alcance | owner | admin | manager | viewer |
|---|---|---|---|---|---|
| `view_leads` | Lista, detalle, notas, ver handoffs (kind de notificación) | ✔ | ✔ | ✔ | — |
| `manage_leads` | Cambiar estado/outcome, asignar (a sí o a otros), notas, vincular customer/appointment | ✔ | ✔ | ✔ | — |
| `manage_agent_channels` | Ver/activar/desactivar canales del Business (cuando exista UI) | ✔ | ✔ | — | — |

Descartados para MVP: `assign_agent_leads` (se fusiona en `manage_leads`; separarlo después si aparece la necesidad), `view_agent_conversations` (no se replican conversaciones). `viewer` sin acceso: los leads tienen PII operativa y no hay caso de uso de solo lectura.

Servicio: agregar a `APPOINTMENTS_PERMISSIONS` (el caso inicial es clínica dental en Turnos). Si después se habilita para Gestión, se agrega al set correspondiente, igual que se hizo con `view_customers`.

Entitlement: nuevo, p. ej. `appointments.leads`, **no** incluido en `appointments_base`; se otorga por add-on/complimentary. Gatea el panel. La ingesta se gatea por canal activo + estado del Business (§20), no por entitlement, para no perder leads ante un problema de facturación transitorio.

Brecha de producto (P2): el servicio `appointments` solo define owner/admin/manager/viewer. No hay rol "recepción" y `manager` tiene `manage_settings`. No se crea un rol nuevo ahora; si las clínicas necesitan recepcionistas sin acceso a configuración, la vía es agregar `staff` al mapa de `appointments` (rol que ya existe en `Membership`).

---

## 14. Autenticación service-to-service

Existente:
- `hmac.compare_digest` / `secrets.compare_digest`: webhook MP, MFA admin, tokens de email/reset, blog preview.
- Verificación HMAC-SHA256 sobre manifest (`_verify_mp_signature`), fail-closed en no-DEBUG si falta el secreto.
- Cifrado Fernet con clave dedicada por dominio, sin fallback a plaintext (`merchant_payments/crypto.py`, `admin_mfa`).
- Redis cache compartido (`django_redis`) apto para nonces.
- No existe auth por API key/credencial de integración.

**Decisión: HMAC-SHA256 aprobado** (mTLS/JWT firmados no aportan para un único servicio y agregan operación). Especificación a fijar en el contrato:

Headers: `X-Agent-Key-Id`, `X-Agent-Timestamp` (unix segundos), `X-Request-Id` (UUID), `X-Agent-Signature` (`v1=<hex minúscula>`).

Canonical string (separado por `\n`):
```
v1
PUT
/api/v1/integrations/agent/leads/<external_lead_id>/
<X-Agent-Timestamp>
<X-Request-Id>
<X-Agent-Key-Id>
<sha256 hex del body crudo>
```

Verificación en MiRubro (clase `AgentHmacAuthentication`):
1. Headers presentes y bien formados; `key_id` existe y está activa; la instancia está habilitada.
2. `|now − timestamp| ≤ 300 s`.
3. HMAC sobre `request.body` crudo (antes del parseo de DRF), `hmac.compare_digest`.
4. Nonce: `cache.add('agent-req:{key_id}:{request_id}', 1, timeout=600)`; si ya existía → 401. Si Redis falla, fail-open en el nonce (la idempotencia por versión ya hace inocuo un replay de un PUT).
5. Cualquier fallo → 401 genérico; el log técnico registra solo `key_id`, motivo codificado y `request_id`.

Fail-closed: sin clave de cifrado configurada o secreto indescifrable → 401/503, nunca bypass (a diferencia del bypass DEBUG de MP, que no debe copiarse).

---

## 15. AgentInstance

Necesaria: el HMAC necesita una identidad que firme y un alcance que autorice.

**Nombre:** `AgentInstance` (una instalación/deployment del servicio agente). Credenciales en modelo aparte para rotación con solapamiento:

`AgentInstance`: `id` UUID (= `agent_instance_id` del contrato), `name`, `is_enabled`, `created_at`, `disabled_at`.

`AgentCredential`: `instance` FK, `key_id` (único, público), `secret` cifrado con Fernet y **clave dedicada** (p. ej. `AGENT_SECRET_ENCRYPTION_KEY`, independiente de `MP_TOKEN_ENCRYPTION_KEY` y `MFA_ENCRYPTION_KEY`), `status` (`active` / `retiring` / `revoked`), `created_at`, `revoked_at`.
- Se cifra (no se hashea) porque HMAC requiere el secreto en ambos extremos.
- Rotación: crear credencial nueva `active`, el agente migra, la anterior pasa a `revoked`. Pueden convivir dos activas durante la ventana.

Alcance: una instancia puede servir **varios** Business (el servicio agente es multi-tenant), pero solo los que tienen un `AgentChannel` activo apuntando a ella. La autorización real es la tupla `(instance, channel, business)`, no la instancia sola. Esto limita el radio de un agente comprometido a los Business vinculados y a escribir leads (nunca leer ni tocar otros modelos).

MVP: una instancia, una credencial, alta por management command (sin UI).

---

## 16. Idempotencia

Patrones existentes: `WebhookDelivery` (hash SHA-256 del body + dedupe por `x_request_id`), `CustomerMessageDelivery.idempotency_key` única por Business, `BusinessNotification.dedupe_key`, `AppointmentPayment` con `select_for_update` + constraint parcial.

**Regla validada con ajuste:**

- Identidad del lead: `UniqueConstraint(agent_instance, external_lead_id)`.
- `version`: entero positivo, estrictamente creciente por lead. Misma versión ⇒ mismo snapshot.
- `payload_hash`: SHA-256 que **calcula MiRubro** sobre la serialización canónica (JSON, claves ordenadas, sin campos de transporte) de los campos validados del snapshot. No sobre el body crudo (un reenvío puede variar el orden o un `sent_at`) y no confiando en un hash enviado por el agente.
- `event_id`: MiRubro lo recalcula y lo compara; si difiere → 400. Se guarda como `last_event_id` para correlación de logs.

Transacción conceptual (PostgreSQL, `READ COMMITTED`):
```
atomic():
  state = LeadAgentState.select_for_update()
            .filter(agent_instance, external_lead_id).first()
  if state is None:
      try: atomic(savepoint): crear Lead + LeadAgentState(version, hash)  → 201
      except IntegrityError: re-leer con select_for_update y seguir abajo
  if state.lead.business_id != channel.business_id: 409 business_mismatch
  if v <  state.applied_version: 200 stale
  if v == state.applied_version: 200 duplicate si hash igual, si no 409 version_conflict
  aplicar snapshot; applied_version = v; payload_hash; last_event_id
  detectar transición de handoff → needs_attention_at
on_commit_safely(crear BusinessNotification)
```
Transacción corta, sin I/O externo dentro. No se guarda un log de eventos con body (a diferencia de `WebhookDelivery`); si hace falta trazabilidad, una tabla de recibos sin PII (`event_id`, `version`, `result`, `received_at`) es opcional (P3).

---

## 17. PII y logging

Estado actual:
- Logs JSON a consola en prod; `django.request` a WARNING (registra método/path/status, no body). Path con `external_lead_id` UUID opaco: aceptable.
- **No hay Sentry** en el repo. Si se agrega: `send_default_pii=False` y scrubbing de body/headers.
- No hay middleware que loguee bodies.
- `webhook_lifecycle.py` tiene un redactor regex de secretos (`access_token`, `authorization`, `x-signature`…) para MP.
- `WebhookDelivery` persiste `body_json` y `headers_json`: correcto para MP, **incorrecto** para el agente.
- `_verify_mp_signature` loguea el `x-signature` crudo cuando está mal formado y el manifest en mismatch: no copiar ese patrón.
- Las respuestas de validación de DRF ecoan el valor en algunos campos (`ChoiceField`: `"X" is not a valid choice`). El receptor debe devolver códigos de error, no mensajes con valores.

Reglas para el receptor:
- Log técnico permitido: `agent_instance_id`, `key_id`, `channel_id`, `business_id`, `lead.id`, `external_lead_id`, `external_conversation_id` (opaco), `version`, `event_id`, `request_id`, `result`, latencia.
- Nunca en logs ni en excepciones: teléfono, nombre del paciente, profile name, motivo, preferencia horaria, resumen, body, firma, secretos.
- Excepciones de validación: capturar y loguear solo el nombre del campo y el código.
- Auditoría de negocio ≠ logging técnico: los cambios humanos del CRM (estado, asignación, vínculo) son historia del lead (timestamps/actor en el propio modelo, o un `LeadEvent` sin PII si se necesita timeline). `AuditLog` queda para seguridad/administración.
- Retención: definir política de borrado/anonimización de leads cerrados sin conversión (pendiente de producto, P2).

---

## 18. Ubicación futura en MiRubro

- Backend: app nueva `apps.leads` (modelos CRM + réplica + canal + instancia). API de panel en `/api/v1/leads/` (JWT, `HasBusinessMembership` + `HasEntitlement` + `HasPermission`); API de ingesta en `/api/v1/integrations/agent/`.
- Frontend: como el caso inicial es Turnos (clínica), entrada en la sección Turnos del sidebar, p. ej. **"Consultas"** en `/app/turnos/consultas`, con `permissionKey: 'view_leads'`, `featureKey` del entitlement y badge desde `unread_count`/contador propio. Mismo camino que siguió Clientes: nació bajo un vertical (`/app/gestion/clientes`) y se está moviendo a top-level (`/app/clientes`) cuando pasó a ser compartido; si leads se vuelve cross-vertical, se promueve a `/app/consultas`.
- No dentro de Clientes: un lead no es un cliente.

---

## 19. Compatibilidad con Turnos

Validado contra el código actual:
- `Customer` es el canónico compartido; `Appointment.customer` es FK nullable, `customer_*` son snapshots.
- Creación interna: `POST /api/v1/appointments/appointments/` (`manage_appointments`); `customer_id` explícito gana sobre el teléfono (CUSTOMER 05). Sin `customer_id`, `resolve_customer_for_appointment` vincula por teléfono y **crea un Customer si no hay match**.
- Disponibilidad: `GET /api/v1/appointments/availability/`; profesionales: `/api/v1/appointments/professionals/` (regla 7B.1: profesional obligatorio si el servicio tiene elegibles).
- Pagos: `pending_payment` con hold (`expires_at`), seña MP vía checkout resuelto por `slug` + `public_token` (flujo público), confirmación por webhook `flow=appointment`.
- Clientes: `POST /api/v1/customers/`, `GET /api/v1/customers/{id}/`.

Flujo futuro `Lead → Customer → Appointment → Payment`, siempre por acción humana desde el panel y usando estos endpoints/servicios (el agente nunca escribe Customer/Appointment/Payment):
1. Recepción abre el lead; ve sugerencia de cliente (§11) → vincula uno existente o crea uno (`POST /customers/`).
2. Agenda con `customer_id` explícito → nunca se dispara la creación implícita por teléfono. Si se agenda sin `customer_id`, tras crear el turno se copia `appointment.customer` a `lead.customer`.
3. `lead.appointment` y `outcome=booked` se setean en la misma acción.
4. Si el servicio requiere seña, se comparte el link público del turno (checkout existente). Hay que verificar en la implementación si la creación interna puede dejar el turno en `pending_payment` o solo en `confirmed`; no es bloqueante para el receptor.

Nada de esto requiere cambiar Turnos para la fase del receptor.

---

## 20. Riesgos

| # | Riesgo | Prioridad | Mitigación de diseño |
|---|---|---|---|
| R1 | Tenant leakage / mapping a Business incorrecto | **P0** | Business derivado de `AgentChannel` activo de esa instancia; `business_id` del payload solo se cruza; lead inmutable de Business; `409 business_mismatch`; nunca `X-Business-Id` |
| R2 | Agente comprometido | **P0** | Credencial por instancia, alcance limitado a canales vinculados, endpoint solo escribe leads, sin lectura; revocación inmediata (`revoked`, `is_enabled=False`) |
| R3 | Sync pisando CRM / Customer | **P0** | Separación en `Lead` vs `LeadAgentState`; sync no escribe `Lead` salvo `needs_attention_at`; nunca escribe `Customer` |
| R4 | PII en logs / persistencia de body | **P1** | No reutilizar `WebhookDelivery`; errores por código; reglas de §17; tests que verifiquen ausencia de PII en logs |
| R5 | Customer incorrecto | **P1** | Sin vínculo automático; sugerencia + confirmación humana; claves AR candidatas |
| R6 | Matching ineficaz (E.164 vs texto local) | **P1** | Claves candidatas (§11); a futuro columna normalizada |
| R7 | Replay HMAC | **P1** | Ventana 300 s + nonce en Redis + idempotencia por versión |
| R8 | Lead duplicado (carrera de creación) | **P1** | Constraint única `(agent_instance, external_lead_id)` + reintento por `IntegrityError` |
| R9 | Versión obsoleta / conflicto | **P1** | `stale` sin efecto; `version_conflict` 409 |
| R10 | Rotación de secretos | **P1** | Dos credenciales activas durante la ventana; clave Fernet dedicada; fail-closed |
| R11 | Handoff no visible para quien atiende | **P1** | `KIND_VIEW_PERMISSIONS` para `view_leads`; sin esto solo owner/admin lo ven |
| R12 | Business suspendido/cancelado/eliminado | **P2** | Ingesta solo con Business en `onboarding/trialing/active/past_due` y canal activo; si no, 403 y el agente estaciona; borrado de Business → cascade |
| R13 | Subscription/entitlement vencido | **P2** | Panel gateado por entitlement; ingesta no (evita pérdida); revisar política comercial |
| R14 | Falta rol recepción en Turnos | **P2** | Usar manager hoy; `staff` en `appointments` si hace falta |
| R15 | Retención de PII de leads no convertidos | **P2** | Definir política de retención/anonimización |
| R16 | MiRubro caído | **P3** | El agente tiene outbox con reintentos; el receptor es rápido y sin I/O externo; notificaciones post-commit que no fallan el request |
| R17 | Reasignación de un `phone_number_id` entre Business | **P3** | Desactivar + crear canal; leads viejos quedan en su Business original |

En el código existente no hay hallazgos P0. P1 del código actual: R6 (matching), R11 (visibilidad de notificaciones por defecto), y los antipatrones de logging/persistencia a no copiar (R4).

---

## 21. Decisiones finales

**P1. ¿Se aprueba `PUT /api/v1/integrations/agent/leads/{external_lead_id}/`?**
Sí, con `<uuid:external_lead_id>` (UUID obligatorio), barra final, autenticación HMAC propia, tenant derivado del canal y los códigos de respuesta de §7.

**P2. ¿Dónde vive `phone_number_id ↔ Business`?**
En un modelo nuevo `AgentChannel` (app `apps.leads`), FK a `Business` y a `AgentInstance`, unicidad parcial sobre `phone_number_id` activo, múltiples canales por Business, `is_active`, sin tokens de Meta.

**P3. ¿Cómo normaliza MiRubro el teléfono para Customer?**
Hoy: solo dígitos (`normalize_phone_for_matching`), sin inferir AR. Para leads: MiRubro normaliza el entrante con `normalize_whatsapp_phone` a `549…`, genera claves candidatas (`549N`, `54N`, `N`, `0N`) y busca con `filter_by_phone_key`; el resultado es solo una sugerencia.

**`external_conversation_id`:** reemplazar `wa:{phone_number_id}:{wa_id}` por un identificador opaco **con clave**:
`wac1_` + primeros 32 hex de `HMAC-SHA256(K_conv, phone_number_id + ":" + wa_id)`, con `K_conv` solo en el agente. Determinístico, estable, distinto por número del negocio, sin teléfono en claro. Se descarta UUIDv5 o hash sin clave: el espacio de teléfonos es chico y el namespace sería público, así que se podría revertir por fuerza bruta. El prefijo `c1` permite versionar si la clave alguna vez se rota. MiRubro lo trata como string opaco.

**`event_id`:** aprobado `UUIDv5(NS, agent_instance_id + ":" + external_lead_id + ":" + version)`. MiRubro lo recalcula y valida.

### Cambios pedidos al contrato del agente
1. `external_lead_id`: UUID (v4/v7).
2. `business_id`: entero (`Business.pk`); el payload incluye además `phone_number_id`; MiRubro valida la vinculación.
3. `external_conversation_id`: HMAC con clave (formato de arriba). No enviar `wa_id`.
4. `event_id`: scopeado por `agent_instance_id`.
5. Teléfono: `phone_e164` con `+`, tal como lo da Meta; MiRubro normaliza por su cuenta.
6. Firma: canonical string de §14 (versión, método, path, timestamp, request-id, key-id, SHA-256 del body), hex minúscula, ventana de 300 s.
7. Semántica de versión: misma versión ⇒ snapshot idéntico; estrictamente creciente.
8. Enums cerrados y publicados: `agent_status`, `urgency`, códigos de `handoff_reasons`. Longitudes máximas para textos libres.
9. Sin mensajes ni transcripciones en el payload.
10. Fechas ISO-8601 en UTC (`Z`).
11. Tabla de respuestas y política de reintento de §7 (incluye estacionar en 403 de canal).
12. Episodio nuevo del paciente ⇒ `external_lead_id` nuevo (no reabrir uno cerrado).

### ¿Está MiRubro listo para implementar el receptor?
**Sí, con condiciones.** No hay bloqueantes en el código existente y los patrones necesarios (HMAC, Fernet, notificaciones idempotentes, RBAC por servicio, constraints de idempotencia) ya están probados. Antes de implementar: (a) cerrar los cambios de contrato de arriba con el equipo del agente; (b) decidir el entitlement/add-on comercial; (c) aceptar el diseño de dos modelos (`Lead` + `LeadAgentState`) y los permisos `view_leads`/`manage_leads`; (d) planificar el aprovisionamiento por management command (instancia, credencial, canal).
