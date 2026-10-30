# Auditoría: MiRubro Turnos como vertical de primera clase

> **Alcance:** auditoría de solo lectura. No se modificó código, migraciones, seeds, env ni billing.
> **Método:** lectura directa de código fuente (`services/api/src/apps/...`, `apps/web/src/...`) y verificación cruzada contra documentación existente en `docs/` (usada solo como pista, no como fuente de verdad).
> **Convención:** ✅ completo · 🟡 parcial · 🔴 ausente · ⚠️ implementado pero desacoplado/inconsistente · `NO IMPLEMENTADO` (confirmado ausente) · `NO DETERMINADO` (no se pudo verificar con la evidencia disponible).

---

## A. Resumen ejecutivo

**Turnos tiene el dominio operativo y la UX más maduros de todo MiRubro fuera de Gestión Comercial, pero no es hoy un producto vendible de forma autónoma.**

- El **backend de dominio** (`apps.appointments` + `apps.leads`) es extenso, con modelos, servicios, validaciones de concurrencia, checkout con Mercado Pago, integración real (HTTP/HMAC) con el agente de WhatsApp, y una batería de tests que cubre concurrencia, aislamiento multi-tenant y hardening. Es comparable o superior en profundidad técnica a Gestión Comercial.
- El **frontend** tiene una sección de primer nivel, claramente llamada "Turnos", separada de Gestión Comercial, con Agenda, Leads, Servicios, Profesionales, Horarios y Configuración propios, navegación dedicada y gating por permiso/plan.
- Sin embargo, **la capa comercial está incompleta**: el producto `appointments` figura **inactivo** en el catálogo de precios (`generated/pricing.json`), no tiene un plan comercial definitivo (el único plan existente está marcado literalmente como *"tentative — sin pricing comercial definitivo aún"*), el checkout comercial no permite seleccionarlo como producto independiente, el onboarding de negocio no lo contempla, y el panel de administración interno de MiRubro **no tiene ninguna herramienta específica para Turnos** (ni visibilidad de plan, ni activación/desactivación, ni diagnóstico, ni auditoría).
- Tampoco existe una **capa de analytics** para Turnos: los reportes de MiRubro (`apps.reports`) están construidos exclusivamente sobre ventas/caja/productos; no hay un solo endpoint de reporting sobre `Appointment`.
- El modelo de **equipo/RBAC** tiene una laguna estructural: `AppointmentProfessional` es una entidad de datos (nombre, teléfono, email) sin vínculo a `User`/`Membership`/`EmployeeProfile`; un profesional no puede iniciar sesión ni ver "solo su agenda".

**Conclusión de una línea:** Turnos es un **módulo interno muy sólido y casi vendible**, bloqueado para convertirse en producto autoservicio por brechas de **billing/catálogo, onboarding y admin interno**, no por brechas de dominio o UX.

---

## B. Mapa funcional actual de Turnos

```
Turnos
├── Agenda                         ✅ implementado  (/app/turnos/turnos)
├── Leads (WhatsApp)               ✅ implementado  (/app/turnos/leads)
├── Servicios                      ✅ implementado  (/app/turnos/servicios)
│   └── Categorías                 ✅ implementado  (/app/turnos/servicios/categorias)
├── Profesionales                  ✅ implementado  (/app/turnos/profesionales)
├── Horarios / Disponibilidad      ✅ implementado  (/app/turnos/horarios: general, por profesional, excepciones)
├── Configuración                  🟡 parcial       (/app/turnos/configuracion: pagos, recordatorios, reply-to, emails;
│                                                     falta: buffer, anticipación mínima, horizonte máximo, cancelación, capacidad)
├── Reserva pública                ✅ implementado  (/app/t/[slug], checkout Mercado Pago)
├── Clientes                       ✅ implementado, COMPARTIDO con Gestión Comercial (/app/clientes)
├── Automatización (recordatorios) 🟡 parcial       (reconciliación interna sí; envío externo al cliente NO DETERMINADO)
├── Analytics / Reportes           🔴 ausente
├── Admin interno MiRubro          🔴 ausente       (sin módulo específico; solo `service_type` genérico visible)
├── Onboarding dedicado            🔴 ausente       (no está en `BusinessOnboardingProgress.PRODUCT_TYPE_CHOICES`)
├── Plan/pricing comercial activo  🔴 ausente       (`appointments` inactivo en `generated/pricing.json`)
└── Login/agenda propia de Professional 🔴 ausente  (sin FK a User/Membership/EmployeeProfile)
```

---

## C. Arquitectura / modelo de dominio

### C.1 Inventario backend (`apps.appointments`)

Modelos (`services/api/src/apps/appointments/models.py`):

| Modelo | Rol |
|---|---|
| `AppointmentCategory` | Agrupación de servicios por negocio (líneas 9–35) |
| `AppointmentService` | Servicio reservable: duración, precio, seña (líneas 150–205) |
| `AppointmentProfessional` | Profesional/staff reservable, M2M a servicios (líneas 37–66) |
| `AppointmentSchedule` | Horario recurrente por día de semana, general o por profesional (líneas 68–107) |
| `AppointmentException` | Excepción puntual de horario (feriado/cierre) (líneas 109–148) |
| `Appointment` | Turno: `status` (`pending_payment`, `confirmed`, `completed`, `cancelled`, `no_show`, `expired`), `source` (`manual`, `public`) (líneas 228–356) |
| `AppointmentPayment` | Intento de pago Mercado Pago, con estados y constraint de "un intento activo por turno" (línea 358+, migración `0007_appointmentpayment_webhook_review.py`) |

Servicios de dominio (`services/api/src/apps/appointments/services/`): `booking.py` (reserva/validación de solapamiento), `availability.py` (cálculo de disponibilidad, sin modelo persistido separado), `admin_mutation.py` (mutaciones administrativas), `expiration.py` (vencimiento de holds), `customer_link.py` (deduplicación de cliente por teléfono), `customer_history.py`, `payment.py` / `payment_confirmation.py` (checkout y conciliación Mercado Pago), `reminder_automation.py` (recordatorios internos), `contact.py` (deep-link WhatsApp).

Endpoints internos (`appointments/urls.py:33-52`): categorías, servicios, profesionales, horarios, excepciones, turnos, disponibilidad, automatización de recordatorios/comunicación. Endpoints públicos (`appointments/urls.py:54-73`, `public_views.py`): negocio público, profesionales, disponibilidad, creación de reserva, estado de reserva, checkout.

Tareas Celery: `appointments.expire_appointment_holds` (`tasks.py:25`). No existe un dispatcher Celery dedicado que envíe recordatorios al cliente.

### C.2 Inventario backend (`apps.leads`)

`Lead` (`leads/models.py:175`) con FKs opcionales a `Customer` y `Appointment`, validando que ambos pertenezcan al mismo `Business` (líneas 260–304). `AppointmentProposal` (`leads/models.py:856`) es el puente conversacional entre el bot/agente y un `Appointment` real — un concepto de dos etapas intencional (propuesta conversacional → turno reservado), no una duplicación accidental.

Integración con el agente externo de WhatsApp:
- **Entrante:** `leads/contract.py` (firma HMAC, `lead.sync`), `AgentHmacAuthentication` (`authentication.py:87`), `receive_lead_sync()` (`services/receiver.py:369`). Modelos: `AgentInstance`, `AgentCredential`, `AgentChannel`, `LeadAgentState`, `LeadAgentMessage`.
- **Saliente:** `takeover_client.py` (comandos `PUT` de takeover/release, HMAC, `AGENT_TAKEOVER_BASE_URL`) y `human_message_client.py` (mensajes humanos → conversación del agente). Ambos son clientes HTTP reales dentro de este repo; el runtime del agente/bot en sí **no vive en este repositorio**.
- `ConversationControl` (`leads/models.py:590`) y `TakeoverCommand` (`leads/models.py:670`) gestionan el ciclo bot↔humano.

### C.3 Diagrama real de dominio

```
Customer (transversal, compartido con Ventas/Gestión)
   │  FK opcional + snapshot histórico en Appointment
   │
Lead ── ConversationControl ── LeadAgentState/LeadAgentMessage (bot WhatsApp)
   │ FK opcional a Customer y a Appointment (misma Business)
   │
AppointmentProposal  (propuesta conversacional: profesional, servicio, seña)
   │  confirmación humana / señal del agente
   ▼
Appointment ── AppointmentPayment (Mercado Pago)
   │
   ├── Service (duración, precio, seña)
   ├── Professional (M2M con Service)
   └── Schedule + Exception (disponibilidad calculada, no persistida)
```

No existe una clase de máquina de estados centralizada: las transiciones de `Appointment`, `Lead` y `AppointmentProposal` están distribuidas entre serializers, servicios de booking/pago/mutación administrativa y la tarea de expiración. Funcionalmente correcto (con amplio testing de concurrencia), pero arquitectónicamente disperso.

---

## D. Integración transversal MiRubro

| Punto de integración | Estado | Evidencia |
|---|---|---|
| `Customer` compartido | ✅ completo | `Appointment.customer` FK (`models.py:275-282`); también usado por `sales`, `leads`; UI compartida en `/app/clientes` |
| `service_type` canónico | ✅ completo | `Business.ServiceType.APPOINTMENTS`, `SubscriptionV2.ServiceType.APPOINTMENTS` (`business/models.py:21-30`, `billing/models.py:278`) |
| `ServicePolicy` (implicación entre servicios) | 🔴 ausente | `SERVICE_IMPLIES` no define expansión para `appointments` (`business/service_policy.py:12-19`) |
| Entitlements de negocio | 🟡 parcial | Existe `appointments.leads`; no existe entitlement general para CRUD de turnos |
| Notificaciones in-app | ✅ completo | `BusinessNotification` con eventos `appointment_confirmed`, `appointment_payment_review` (`appointments/services/notifications.py`) |
| Membership/RBAC de negocio | ✅ completo | Vistas usan `HasBusinessMembership` + `HasPermission` igual que otras verticales |
| Modelo de empleados/login (`EmployeeProfile`) | 🔴 ausente para Turnos | `AppointmentProfessional` no tiene FK a `EmployeeProfile`/`User` (a diferencia de Caja, que sí usa `EmployeeProfile`) |
| Onboarding de negocio | 🔴 ausente | No está en `BusinessOnboardingProgress.PRODUCT_TYPE_CHOICES` (`business/models.py:423-432`) |
| Admin interno | 🔴 ausente | Sin ruta, vista ni auditoría específica en `platform_admin_*` |

---

## E. Comparativa con Gestión Comercial / Carta Online / QR Reseñas

| Capacidad | Gestión Comercial | Carta Online (`menu_qr`) | QR de Reseñas | **Turnos** |
|---|---|---|---|---|
| Servicio/módulo canónico | ✅ completo | ✅ completo | ✅ completo | ✅ completo (`service_type='appointments'`, `billing/models.py:278`) |
| Planes propios | ✅ completo (start/pro/business/enterprise) | ✅ completo (menu_qr lite/pro/premium) | ✅ completo (qr_reviews base/pro) | 🔴 ausente (plan legacy `appointments_base` "tentative, sin pricing definitivo", `business/models.py:134-135`; **inactivo** en `generated/pricing.json`) |
| Billing / compra | ✅ completo | ✅ completo | 🟡 parcial (comparte infraestructura, sin checkout exclusivo) | 🟡 parcial (`SubscriptionV2` soporta el servicio estructuralmente, pero checkout comercial usa `business.default_service`, no selección independiente — `commercial_views.py:433`) |
| Entitlement específico | ✅ completo | ✅ completo | 🟡 parcial (reutiliza lógica de Menú QR) | 🟡 parcial (`appointments.leads` existe; no hay entitlement general sobre el CRUD de turnos) |
| Onboarding dedicado | ✅ completo (wizard propio) | 🔴 ausente | 🔴 ausente | 🔴 ausente (no está en `PRODUCT_TYPE_CHOICES`) |
| Sidebar/nav dedicado | ✅ completo | ✅ completo | ⚠️ desacoplado (vive dentro de `features/reviews`/engagement) | ✅ completo (grupo "Turnos" propio, `sidebar.tsx:220-237`) |
| Configuración propia | ✅ completo | ✅ completo | ⚠️ desacoplado (alojada en app `menu`) | 🟡 parcial (pagos/recordatorios sí; reglas de booking completas no) |
| Admin interno | 🟡 parcial (genérico) | 🟡 parcial (genérico) | ✅ completo (endpoint dedicado + auditoría propia) | 🔴 ausente (solo `service_type` genérico visible) |
| Dashboard propio | ✅ completo | 🟡 parcial | 🟡 parcial (stats sin UI dedicada confirmada) | 🟡 parcial (home de Turnos es landing de accesos, sin KPIs) |
| Analytics | ✅ completo | 🟡 parcial | ✅ completo | 🔴 ausente (ningún endpoint de `apps.reports` cubre `Appointment`) |
| Superficie pública | 🔴 ausente | ✅ completo | ✅ completo | ✅ completo (`/app/t/[slug]`, checkout público) |
| RBAC específico | ✅ completo | ✅ completo | ✅ completo | 🟡 parcial (RBAC de negocio completo; **sin identidad de Professional** para login/"mi agenda") |
| Lifecycle de suscripción | ✅ completo | ✅ completo | 🟡 parcial | 🟡 parcial (gate público sí acoplado — `public_page.py:12-31`; gate interno **NO DETERMINADO**) |
| Notificaciones | 🟡 parcial | 🔴 ausente | 🔴 ausente | 🟡 parcial (in-app sí; envío externo al cliente no confirmado) |
| Branding | 🟡 parcial (genérico) | ✅ completo (modelo propio) | 🔴 ausente | 🔴 ausente (branding genérico de `Business`) |
| Audit logs | 🔴 ausente | 🔴 ausente | 🔴 ausente | 🔴 ausente |
| Tests | ✅ completo | ✅ completo | ✅ completo | ✅ completo (≈30 archivos backend incl. concurrencia/multitenant + ≈20 archivos frontend) |

**Lectura de la matriz:** en las columnas de dominio/UX/tests, Turnos está a la par o por encima de las otras tres verticales. En las columnas de **comercialización** (planes, billing, onboarding, admin interno, analytics), Turnos es la más débil de las cuatro — incluso QR Reseñas, pese a estar desacoplada dentro de la app `menu`, tiene mejor cobertura comercial y de admin interno que Turnos.

---

## F. UX y navegación actual

- **Sí** existe una sección claramente llamada "Turnos", de primer nivel, no anidada en Gestión Comercial: grupo propio en el sidebar (`apps/web/src/components/navigation/sidebar.tsx:220-237`).
- **Agenda** (`/app/turnos/turnos`) es el centro operativo real: vista diaria/semanal, alta/edición/cancelación/no-show, filtrado por profesional.
- **Leads** (`/app/turnos/leads`) es una bandeja específica de consultas de WhatsApp (no la UI genérica de CRM), con gating propio por plan ("Turnos Base") y permiso.
- **Servicios, Profesionales y Horarios** están correctamente agrupados bajo Turnos, no dispersos en Business settings ni en Gestión Comercial.
- **Configuración** (`/app/turnos/configuracion`) cubre hoy: enlace de reserva pública, conexión Mercado Pago, recordatorios internos, Reply-To de emails y emails automáticos al cliente. **No** existe una pantalla de reglas de booking (buffer entre turnos, anticipación mínima, horizonte máximo de reserva, política de cancelación formal, capacidad concurrente, selector de moneda).
- **Empty states** existen para horarios sin profesionales / sin selección, pero **no se encontró** un wizard guiado "primer servicio → primer profesional → primer turno".
- **Único módulo compartido explícito con Gestión Comercial:** la ficha de `Clientes` (`/app/clientes`), documentada en el propio código como "ficha canónica compartida" — no es duplicación accidental.

---

## G. Billing / entitlements / lifecycle

| Pregunta | Respuesta |
|---|---|
| ¿Existe `service_type`/`module_code` canónico `appointments`? | **Sí** — `Business.ServiceType.APPOINTMENTS`, `SubscriptionV2.ServiceType.APPOINTMENTS`, `Module`/`Bundle.VERTICAL_CHOICES` (`billing/models.py:77-117, 278`) |
| ¿Tiene planes propios? | Solo un plan **legacy** `appointments_base` ("Turnos Base"), marcado en el propio código como *tentative, sin pricing comercial definitivo* (`business/models.py:134-135`) |
| ¿Está activo en el catálogo comercial? | **No** — `generated/pricing.json` marca el producto `appointments` con `"is_active": false`; no hay ningún plan con `vertical: "appointments"` en el pricing canónico |
| ¿Puede venderse hoy como producto independiente vía checkout de autoservicio? | **NO IMPLEMENTADO / no demostrable** — el checkout comercial resuelve `service_type = business.default_service` (`commercial_views.py:433`), no una selección independiente de Turnos |
| ¿Existe entitlement propio? | Parcial: `appointments.leads` (usado solo por Leads/CRM); **no** hay entitlement general que gatee el CRUD de turnos en `apps/appointments/views.py` (usa RBAC genérico `HasPermission`) |
| ¿Se activa/desactiva correctamente por suscripción? | Gate público sí (`PUBLISHABLE_STATUSES = {active, trialing, past_due}`, `public_page.py:12-31`). Gate interno sobre creación/listado de turnos por estado de negocio/suscripción: **NO DETERMINADO** — no se encontró comprobación directa de `Business.status`/`SubscriptionV2.status` en las vistas internas de appointments |
| ¿Límites comerciales (profesionales, turnos/mes)? | **NO IMPLEMENTADO** — `PLAN_SEAT_LIMITS` no incluye `appointments_base` |
| Riesgo de naming | Doble fuente de verdad `Business.default_service` (deprecated) vs `Business.service_type` (canónico); el checkout comercial usa la primera |

**Conclusión de la sección 2 del pedido original:** Turnos está **modelado** como vertical independiente a nivel de dominio y de `SubscriptionV2`, pero **no alcanza hoy el nivel de producto vendible en autoservicio**. Comercialmente solo sería activable mediante *provisioning manual* de staff (el servicio de provisioning admite `service_type` arbitrario), no mediante el flujo comercial estándar.

---

## H. RBAC / equipo

- `Professional` (`AppointmentProfessional`) **es una entidad independiente** (no un campo/etiqueta dentro de `Appointment`), con nombre, teléfono, email y M2M a servicios.
- **No puede vincularse a una cuenta de plataforma**: no tiene FK a `AUTH_USER_MODEL`, ni a `Membership`, ni a `EmployeeProfile` (el modelo de empleados con `linked_user` que sí usa Caja/POS).
- Consecuencia: **un profesional no puede iniciar sesión ni ver "solo su agenda"**; tampoco existe el control inverso ("¿puede gestionar turnos de otros?") porque no hay identidad de profesional autenticada que restringir.
- El RBAC que sí existe es **de negocio**, no de profesional: `HasBusinessMembership` + `HasPermission` (`view_appointments`/`manage_appointments`), probado explícitamente contra el rol `viewer` (`appointments/tests/test_services.py:160-162`).
- **Comparación con el resto de la plataforma:** el patrón es divergente. Gestión Comercial usa `Membership`; Caja usa `EmployeeProfile` con `linked_user` y tokens de empleado; Tesorería tiene su propio `Employee`; Turnos usa `AppointmentProfessional`, aislado de los tres.

---

## I. CRM / Clientes

- `Customer` **es transversal**, no específico de Turnos: lo usan `Appointment.customer`, `Lead.customer`, Ventas/Presupuestos.
- **Reutilización por teléfono:** sí, implementada explícitamente en `appointments/services/customer_link.py` (normaliza teléfono, busca cliente activo del mismo negocio, reutiliza o crea).
- **Historial de turnos:** disponible vía relación inversa `Appointment.customer` (no como campo agregado en `Customer`).
- **Historial de conversaciones:** parcialmente modelado, pero vive en Leads/`LeadAgentState`, no en `Customer` — **NO DETERMINADO** como historial unificado visible desde la ficha de cliente.
- **No-show/cancelaciones como contador agregado en Customer:** **NO IMPLEMENTADO** (el estado existe en `Appointment`, no se agrega en `Customer`).
- **Preferencias de contacto:** sí, modelo dedicado `CustomerContactPreferences` (incluye `do_not_contact`).
- **Deduplicación:** lógica por teléfono en el flujo de turnos; constraint de base de datos solo para documento único por negocio — **no hay constraint único de teléfono**, por lo que otros caminos manuales de creación podrían generar duplicados.
- **Lead → Customer → Appointment:** modelado y validado explícitamente (mismo `Business` obligatorio), con tests dedicados (`leads/tests/test_appointment_link.py`, `test_create_appointment.py`, `test_confirm_appointment_proposals.py`).

---

## J. Automatizaciones y comunicaciones

El bot externo de WhatsApp **sí tiene contrato e integración reales dentro de este repo** (no se cuenta solo por existir fuera): `leads/contract.py`, `AgentHmacAuthentication`, `takeover_client.py`, `human_message_client.py`.

| Capacidad | Estado |
|---|---|
| Recepción de sincronización del agente (`lead.sync`) | ✅ Implementado — endpoint HMAC autenticado |
| Propuestas de turno desde Leads | ✅ Implementado — creación, envío y serialización |
| Confirmación de propuesta | 🟡 Parcial — la señal del agente registra la confirmación, pero no crea/confirma el turno por sí sola; requiere flujo humano complementario |
| Takeover (agente humano reemplaza al bot) | ✅ Implementado — ciclo `active → takeover_pending → taken`, comandos HTTP firmados, tareas Celery con retry |
| Recordatorios | 🟡 Parcial — reconciliación interna robusta (`reminder_automation.py`), pero el propio código documenta que **no envía WhatsApp/email/SMS**; no se halló el dispatcher externo |
| Cancelaciones | 🟡 Parcial — mutación de estado implementada; aviso automático al cliente **no evidenciado** |
| Reprogramaciones | 🟡 Parcial — operación implementada; notificación específica de reprogramación **NO IMPLEMENTADO** |
| Notificaciones internas al staff | ✅ Implementado (limitado) — `appointment_confirmed`, `appointment_payment_review`, handoff de leads; faltan eventos de cancelación/no-show/reprogramación |
| Emails salientes | 🟡 Parcial / **NO DETERMINADO** — infraestructura genérica de `EmailDelivery`/Celery existe y la UI permite configurarlo, pero no se encontró el punto donde Turnos invoque `queue_transactional_email` |
| Celery / background jobs | ✅ Implementado — `expire_appointment_holds`, tareas de takeover/mensajes en Leads, envío genérico de emails; **no** hay task específico de despacho de recordatorios al cliente |

---

## K. Analytics

**NO IMPLEMENTADO** como módulo. `apps.reports` agrega exclusivamente `Sale`, `SaleItem`, `Payment` (de caja) y `CashMovement`/`CashSession` — ningún endpoint toca `Appointment` ni `AppointmentPayment`.

Checklist solicitado — todas las métricas: **NO IMPLEMENTADO**:
turnos por período · confirmados/cancelados/no-show · ocupación · servicios más solicitados · performance por profesional · ingresos ligados a turnos · conversión Lead→Appointment · tiempo de respuesta bot/humano · origen del lead/turno · bot vs humano.

Esta es, junto con billing/onboarding/admin, la brecha más crítica frente a Gestión Comercial, que sí tiene series temporales, breakdown de pagos, leaderboard de productos y reportes de caja.

---

## L. Admin interno MiRubro

**Turnos no es de primera clase en el backoffice.** Comparado explícitamente con QR Reseñas, que sí tiene admin dedicado:

| Pregunta | Turnos | QR Reseñas (referencia) |
|---|---|---|
| ¿Staff ve que el cliente usa Turnos? | Solo genérico: campo `service_type` en la ficha de cliente | Tiene tarjeta/componente dedicado en `cliente-detail-content.tsx` |
| ¿Staff ve plan/suscripción de Turnos? | **NO IMPLEMENTADO** (solo última suscripción genérica, sin filtrar por servicio) | — |
| ¿Staff puede activar/desactivar Turnos? | **NO IMPLEMENTADO** (sin ruta en `platform_admin_urls.py`) | Tiene endpoint `GET/PATCH .../qr-reviews-config/` |
| ¿Staff puede diagnosticar servicios/profesionales/horarios? | **NO IMPLEMENTADO** | — |
| ¿Snapshot/config administrativo? | **NO IMPLEMENTADO** | Sí, con validación por vertical |
| ¿Auditoría de acciones admin? | **NO IMPLEMENTADO** — no existe acción `ADMIN_*` para Turnos en `accounts/models.py:417-445` | Sí — `ADMIN_QR_REVIEWS_CONFIG_UPDATED` |
| ¿Soporte interno específico? | **NO IMPLEMENTADO** | — |

---

## M. Onboarding

Flujo ideal (`registro → selección Turnos → suscripción → Business → configuración → servicios → profesionales → horarios → primer turno`) comparado con lo real:

- **No existe** un wizard de onboarding dedicado a Turnos equivalente al de Gestión Comercial.
- `BusinessOnboardingProgress.PRODUCT_TYPE_CHOICES` **no incluye** `appointments` (solo `gestion`, `menu_qr`, `qr_reviews`) — el producto no puede "seleccionarse" en el flujo de onboarding estándar.
- Cada paso operativo individual **sí existe** como pantalla independiente (servicios, profesionales, horarios), pero no hay un flujo guiado que los encadene para un negocio nuevo; se requiere configuración manual paso a paso por el propio dueño, sin checklist ni wizard.
- Activar Turnos para un cliente hoy depende de **provisioning manual de staff** (vía `admin_client_provisioning_service.py`, que acepta `service_type` arbitrario), no de autoservicio.

**Clasificación:** 🔴 ausente a nivel de flujo guiado; 🟡 parcial a nivel de piezas individuales ya construidas.

---

## N. Testing

Cobertura **notablemente sólida**, superior en proporción a lo visto en otras verticales auditadas en este repo:

- **Backend `appointments/tests`** (≈30 archivos): incluye concurrencia de mutación admin, concurrencia de turnos, concurrencia de checkout, concurrencia de webhook de pago, aislamiento multi-tenant (`test_multitenant.py`), disponibilidad, categorías, historial/vinculación de cliente, hardening, modo profesional, reserva pública (incl. concurrencia), automatización de recordatorios y ciclo de vida de despacho, horarios, servicios (incl. RBAC `viewer`), y filtrado semanal.
- **Backend `leads/tests`** (≈21 archivos): propuestas de turno, confirmación de propuestas, creación de turno desde lead, API CRM, mensajes humanos, API de receiver del agente, takeover, RBAC/entitlements, aislamiento de asignados.
- **Frontend**: ≈20 archivos de test entre `features/appointments/__tests__`, `app/app/turnos/**/__tests__`, `app/t/[slug]/__tests__`, `components/navigation/__tests__/sidebar-appointments.test.tsx`, `features/leads/__tests__`, y `app/clientes/__tests__`.
- **Huecos confirmados:** no se encontró test de permiso "profesional ve solo su agenda" (coherente con que esa capacidad no existe); no se encontró test de reporting/analytics (coherente con que no existe el módulo).

---

## O. Deuda técnica / inconsistencias

1. **Doble fuente de verdad de servicio:** `Business.default_service` (deprecated) vs `Business.service_type` (canónico); el checkout comercial usa la primera (`commercial_views.py:433`), lo que puede hacer que una suscripción `service_type='appointments'` no sea la fuente efectiva si `default_service` quedó desactualizado.
2. **Producto inactivo pero código funcional completo:** `generated/pricing.json` marca `appointments` con `is_active: false` mientras el dominio está 100% operativo — desalineación entre "lo que el código puede hacer" y "lo que el catálogo comercial permite vender".
3. **Plan legacy sin pricing:** `appointments_base` está literalmente comentado como tentativo en el código fuente.
4. **Naming mixto:** `Appointment`/`appointments`/`view_appointments` (inglés) conviven con `Turno`/`Turnos`/`_HasTurnosAccess`/`seed_turnos_qa` (español) — no es un bug, pero es inconsistencia de convención.
5. **Recordatorios "silenciosos":** la UI permite configurar recordatorios y emails automáticos, pero el propio código de automatización documenta que no despacha WhatsApp/email/SMS — riesgo de expectativa del usuario no cumplida.
6. **Sin entitlement general sobre `apps/appointments/views.py`:** solo Leads tiene el entitlement `appointments.leads`; el CRUD de turnos en sí depende de RBAC genérico, no de un chequeo de suscripción activa — el acoplamiento real con el lifecycle de billing en las rutas internas quedó **NO DETERMINADO**.
7. **`AppointmentProfessional` desconectado del resto del sistema de identidad** (`User`/`Membership`/`EmployeeProfile`), a diferencia del patrón usado en Caja/Tesorería.
8. **Cero paneles de administración interna**, a diferencia de QR Reseñas que sí tiene endpoint, UI y auditoría dedicados — esto es un riesgo operativo de soporte, no solo comercial.

---

## P. Score 0–5 por dimensión

| Dimensión | Score | Justificación breve |
|---|---:|---|
| Dominio operativo | **4/5** | Modelos, servicios, pagos, disponibilidad y concurrencia muy completos; falta una máquina de estados centralizada |
| UX owner | **4/5** | Sección propia, Agenda como centro real, navegación clara; falta pantalla de reglas de booking completas |
| Arquitectura | **3/5** | Sólida pero repartida entre dos apps (`appointments`/`leads`) sin un contrato de estado unificado |
| Billing | **1/5** | Producto inactivo en catálogo, sin plan ni pricing comercial, sin checkout standalone |
| Entitlements | **2/5** | Existe `appointments.leads`; falta entitlement general para el CRUD de turnos |
| RBAC | **2/5** | RBAC de negocio a la par del resto de la plataforma; sin identidad de Professional para login/"mi agenda" |
| Onboarding | **1/5** | No reconocido en `PRODUCT_TYPE_CHOICES`; sin wizard guiado |
| Admin interno | **0/5** | Ninguna herramienta específica; ni siquiera visibilidad de plan por servicio |
| Analytics | **0/5** | Ningún endpoint de reporting sobre `Appointment` |
| Automatización | **3/5** | Integración WhatsApp/takeover real y robusta; dispatch de recordatorios al cliente no confirmado |
| Testing | **4/5** | Cobertura amplia y con foco explícito en concurrencia y tenant isolation |
| Preparación comercial | **1/5** | Solo vendible hoy vía provisioning manual de staff, no autoservicio |

---

## Q. Nivel de madurez 1–5

### **Nivel 2 — Módulo interno usable**, con rasgos de Nivel 3 sin consolidar

**Justificación:** el dominio, la UX y el testing de Turnos superan ampliamente el umbral de "feature experimental" y son operativamente usables hoy (existe incluso un comando `seed_turnos_qa` para aprovisionar datos de QA). Pero el gate explícito hacia "Nivel 3 — Producto MVP vendible" no se cumple: el producto está **inactivo en el catálogo comercial**, carece de plan/pricing definitivo, no tiene checkout de autoservicio, no tiene onboarding reconocido, y no tiene ninguna herramienta de administración interna para que MiRubro lo soporte operativamente. Hoy solo puede "venderse" mediante activación manual de staff vía el servicio de provisioning — es decir, es vendible *a mano*, no como producto autoservicio.

---

## R. Gap analysis

### P0 — Bloquea vender Turnos como producto autoservicio
1. Activar/definir el producto `appointments` en `generated/pricing.json` (hoy `is_active: false`) con un plan comercial real (reemplazando el plan legacy "tentative" `appointments_base`).
2. Habilitar selección independiente de Turnos en el checkout comercial (hoy depende de `business.default_service`, no de una elección explícita de producto).
3. Incorporar `appointments` a `BusinessOnboardingProgress.PRODUCT_TYPE_CHOICES` para que el onboarding estándar lo reconozca.
4. Construir visibilidad mínima de Turnos en platform-admin: que el staff pueda ver plan/estado de suscripción de Turnos y activarlo/desactivarlo seguro, con auditoría — hoy no existe ninguna de estas capacidades.

### P1 — Necesario para producto sólido
1. Analytics mínimos de Turnos: turnos por período, confirmados/cancelados/no-show, ocupación, ingresos de `AppointmentPayment`, conversión Lead→Appointment.
2. Vincular `AppointmentProfessional` a una identidad de login (`User`/`Membership`/`EmployeeProfile`) para habilitar "mi agenda" y escalar a equipos con varios profesionales.
3. Definir y aplicar un entitlement general sobre el CRUD de `apps/appointments` (hoy solo Leads tiene `appointments.leads`); confirmar o corregir el acoplamiento del lifecycle de suscripción sobre las rutas internas (quedó `NO DETERMINADO`).
4. Completar la pantalla de configuración de reglas de booking: buffer entre turnos, anticipación mínima, horizonte máximo de reserva, política de cancelación, capacidad concurrente, selector de moneda.
5. Cerrar el loop de automatización: confirmar/implementar el despacho real (WhatsApp/email) de recordatorios, confirmaciones, cancelaciones y reprogramaciones al cliente — hoy la UI lo promete pero el dispatcher externo no está confirmado.
6. Auditoría de acciones admin específicas de Turnos, siguiendo el patrón ya existente de QR Reseñas (`ADMIN_QR_REVIEWS_CONFIG_UPDATED`).

### P2 — Mejora posterior
1. Unificar `default_service` vs `service_type` como fuente única de verdad.
2. Consolidar las transiciones de `Appointment`/`Lead`/`AppointmentProposal` en una capa de estado explícita en vez de lógica distribuida entre servicios.
3. Branding propio de Turnos (hoy comparte el branding genérico de `Business`) si el negocio lo justifica.
4. Métrica de funnel completo Lead → Propuesta → Appointment y tiempos de respuesta bot/humano.
5. Snapshot/export de configuración de Turnos para soporte, replicando el patrón de QR Reseñas.

---

## S. Estructura recomendada de MiRubro Turnos

La estructura de navegación **actual ya es razonablemente correcta** y no requiere una reorganización profunda:

```
MiRubro Turnos
Inicio                 (ya existe — /app/turnos)
Agenda                 (ya existe — /app/turnos/turnos)
Leads                  (ya existe — /app/turnos/leads)
Clientes               (compartido con Gestión Comercial — mantener así, es intencional)

Gestión
  Servicios             (ya existe)
  Profesionales         (ya existe)
  Horarios              (ya existe, incluye excepciones)

Automatización
  Recordatorios         (ya existe la config; falta confirmar/activar el dispatch externo)
  WhatsApp / Leads      (ya existe vía takeover/human messages)

Configuración
  Reserva pública y pagos   (ya existe)
  Reglas de booking         (NUEVO: buffer, anticipación, horizonte, cancelación, capacidad, moneda)
```

**Lo que movería/agregaría, no reestructuraría:**
- No anidar nada de Turnos dentro de Gestión Comercial — la separación actual es correcta y deliberada.
- Agregar una pestaña de **Analytics** dentro de "Turnos" (hoy inexistente) en vez de intentar reutilizar `apps.reports`, que está modelado íntegramente sobre ventas/caja.
- Agregar, fuera del producto visible al dueño, el **panel de administración interno** equivalente al de QR Reseñas (fuera del alcance de "qué ve el dueño", pero crítico para operar el producto comercialmente).
- Resolver la identidad de Professional **antes** de escalar el producto a negocios con más de un profesional operando simultáneamente — es la única brecha que afecta directamente la experiencia multi-usuario del dueño, el resto de las brechas son de comercialización/soporte.

---

*Documento generado a partir de evidencia directa de código (sin inferencias). Todas las secciones marcadas `NO DETERMINADO` requieren verificación adicional (por ejemplo, trazas en runtime o revisión de despliegue) que excede el alcance de una auditoría estática de este repositorio.*
