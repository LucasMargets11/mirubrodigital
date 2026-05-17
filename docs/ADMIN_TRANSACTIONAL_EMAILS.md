# Emails transaccionales internos ADMIN — MiRubro

> **Estado:** Fase 1 completa — 4 emails admin internos (QR de Reseñas emails **removidos** — ver §5.4 y §10.1).  
> **Última actualización:** 2026-05-11  
> **Relacionado con:** PR-ADMIN-01 · PR-ADMIN-02 · PR-ADMIN-03 · PR-ADMIN-04 · PR-ADMIN-05 · PR-ADMIN-06 · PR-ADMIN-07 · PR-ADMIN-08 · PR-ADMIN-09

---

## 1. Objetivo

Los **emails internos ADMIN** son notificaciones automáticas enviadas al equipo de MiRubro
cuando ocurren eventos críticos de negocio (soporte, billing, cancelaciones, operaciones).

Son **completamente independientes** de los emails al cliente:

- No reemplazan los emails transaccionales que recibe el usuario final.
- No son visibles por los clientes.
- Sirven para alertar a los equipos de soporte, billing y operaciones sin depender de
  revisión manual de la base de datos ni del backoffice.

---

## 2. Arquitectura

```
Evento del sistema
        ↓
helper específico del módulo          (e.g. send_admin_subscription_payment_created_email)
        ↓
queue_admin_transactional_email(...)  (apps/notifications/admin_helpers.py)
        ↓
queue_transactional_email(...)        (apps/notifications/services.py)
        ↓
EmailDelivery                         (DB record — trazabilidad completa)
        ↓
Celery / send_email_delivery.delay()
        ↓
Provider (Amazon SES)
```

### Principios de diseño

| Principio | Detalle |
|---|---|
| **Best-effort** | Todos los helpers devuelven `bool`. Nunca propagan excepciones al caller. |
| **Fire-and-forget** | Fallos de email no revierten ni bloquean el flujo de negocio. |
| **Trazabilidad** | Todo email pasa por `EmailDelivery` — queda registrado en base de datos. |
| **Sin legacy** | Nunca se usa `send_mail` ni `EmailMessage` directamente. |
| **Lazy imports** | Los helpers específicos importan `queue_admin_transactional_email` dentro del cuerpo de la función para evitar imports circulares. |

---

## 3. Helper reusable

### Archivo

```
services/api/src/apps/notifications/admin_helpers.py
```

### Función principal

```python
def queue_admin_transactional_email(
    *,
    recipient_category: str,
    subject: str,
    template_key: str = "admin_generic",
    context: dict | None = None,
    related_business=None,
    related_user=None,
    metadata: dict | None = None,
    send_async: bool = True,
) -> bool:
    ...
```

### Categorías de destinatarios

| `recipient_category` | Setting Django | Default (si no configurado) |
|---|---|---|
| `support` | `SUPPORT_EMAIL` | `mirubrodigital@gmail.com` |
| `billing` | `BILLING_EMAIL` | `mirubrodigital@gmail.com` |
| `operations` | `OPERATIONS_EMAIL` | `mirubrodigital@gmail.com` |
| `platform_admin` | `ADMIN_EMAIL` | `mirubrodigital@gmail.com` |

### Settings requeridas

Todas en `config/settings.py`, leídas desde variables de entorno:

```python
SUPPORT_EMAIL      = env("SUPPORT_EMAIL",      default="mirubrodigital@gmail.com")
BILLING_EMAIL      = env("BILLING_EMAIL",       default="mirubrodigital@gmail.com")
OPERATIONS_EMAIL   = env("OPERATIONS_EMAIL",    default="mirubrodigital@gmail.com")
ADMIN_EMAIL        = env("ADMIN_EMAIL",         default="mirubrodigital@gmail.com")
ADMIN_FRONTEND_URL = env("ADMIN_FRONTEND_URL",  default="http://localhost:3000/admin")
```

### Template genérico

`admin_generic.html` — usado como fallback y para eventos ad-hoc futuros. No requiere
contexto especial más allá de `subject`.

---

## 4. Tabla de emails implementados

| Template | Evento | App origen | Helper | Categoría | Destinatario | Guard |
|---|---|---|---|---|---|---|
| `admin_support_ticket_created` | Cliente crea ticket de soporte | `apps.accounts` | `_queue_ticket_created_email()` en `tenant_support_views.py` | `support` | `SUPPORT_EMAIL` | Solo tickets creados via tenant endpoint (no admin backoffice) |
| `admin_subscription_payment_created` | Pago exitoso + suscripción activada | `apps.billing` | `send_admin_subscription_payment_created_email()` en `email_helpers.py` | `billing` | `BILLING_EMAIL` | Solo si `ap_status == 'authorized'` y `activated == True` en `webhook_processor.py` |
| `admin_cancellation_request_received` | Cliente solicita baja de suscripción | `apps.billing` | `send_admin_cancellation_request_received_email()` en `email_helpers.py` | `operations` | `OPERATIONS_EMAIL` | Solo si `schedule_cancellation()` completa exitosamente el `save()` |

| `admin_payment_failure_recurrent` | Suscripción ACTIVE → PAST_DUE por fallo de cobro o período expirado | `apps.billing` | `send_admin_payment_failure_recurrent_email()` en `email_helpers.py` | `billing` | `BILLING_EMAIL` | Llamado desde `record_failed_payment()` (activator) y `_transition_active_to_past_due()` (task). Fire-and-forget, nunca re-raise. |

---

## 5. Detalle por template

---

### 5.1 `admin_support_ticket_created`

**Cuándo se dispara:**
- Cuando un cliente crea un ticket via `TenantTicketListCreateView.post()`.
- Solo para tickets creados desde el tenant endpoint (`POST /api/v1/tenant/support/tickets/`).

**Cuándo NO se dispara:**
- Tickets creados desde el panel admin (AdminTicketCreateView).
- Tickets creados por staff MiRubro directamente en base de datos.

**Archivo de integración:**
```
services/api/src/apps/accounts/tenant_support_views.py
```
Función: `_queue_ticket_created_email(ticket)` llamada en `.post()` tras `super().post()`.

**Helper usado:**
`queue_admin_transactional_email(recipient_category="support", ...)`  
Importado en el cuerpo de `_queue_ticket_created_email` (lazy import).

**Context enviado al template:**

| Clave | Descripción |
|---|---|
| `ticket_id` | ID del ticket |
| `subject` | Asunto del ticket |
| `priority` | Prioridad |
| `category` | Categoría del ticket |
| `business_name` | Nombre del negocio |
| `owner_email` | Email del owner del negocio |
| `admin_url` | URL directa al ticket en backoffice |

**Metadata guardada:**

| Clave | Valor |
|---|---|
| `event_type` | `"admin_support_ticket_created"` |
| `ticket_id` | ID del ticket (str) |
| `business_id` | ID del negocio (str) |
| `priority` | Prioridad del ticket |

**Tests:**
```
apps.accounts.tests.test_pr_admin_02_support_ticket_email   (17 tests)
```

---

### 5.2 `admin_subscription_payment_created`

**Cuándo se dispara:**
- Cuando llega un webhook de MercadoPago con `ap_status == "authorized"`.
- Y la llamada a `activate_subscription_from_invoice()` retorna `activated == True`.
- Es el Step 7 de `_handle_authorized_payment()` en `webhook_processor.py`.

**Cuándo NO se dispara:**
- Pagos con status `"pending"`, `"in_process"`, `"rejected"`, etc.
- Si la suscripción ya estaba activa y `activated == False`.
- Si `subscription is None` (pago huérfano).
- No se dispara en activaciones manuales de backoffice.

**Archivo de integración:**
```
services/api/src/apps/billing/webhook_processor.py
```
Función: `_handle_authorized_payment()`, Step 7 (bloque try/except independiente).

**Helper usado:**
`send_admin_subscription_payment_created_email(subscription, invoice_event)`  
Importado lazy dentro del bloque try del Step 7.

**Context enviado al template:**

| Clave | Descripción |
|---|---|
| `business_name` | Nombre del negocio |
| `owner_email` | Email del owner (o vacío si no hay owner) |
| `plan_code` | Código del plan |
| `service_type` | Tipo de servicio (e.g. `"gestion"`) |
| `amount` | Monto pagado |
| `currency` | Moneda |
| `paid_at` | Fecha/hora del pago (dd/mm/YYYY HH:MM) |
| `invoice_event_id` | ID del `BillingInvoiceEvent` |
| `admin_url` | URL directa a la suscripción en backoffice |

**Metadata guardada:**

| Clave | Valor |
|---|---|
| `event_type` | `"admin_subscription_payment_created"` |
| `subscription_id` | ID de la suscripción (str) |
| `invoice_event_id` | ID del invoice event (str) |
| `related_business_id` | ID del negocio (str) |
| `service_type` | Tipo de servicio |
| `plan_code` | Código del plan |
| `amount` | Monto (str) |
| `currency` | Moneda |

**Tests:**
```
apps.billing.tests.test_pr_admin_03_subscription_payment_email   (21 tests)
```

---

### 5.3 `admin_cancellation_request_received`

**Cuándo se dispara:**
- Cuando `schedule_cancellation(subscription, ...)` completa exitosamente el `save()`.
- Esto implica que `cancel_at_period_end = True` queda guardado en base de datos.

**Cuándo NO se dispara:**
- Si la suscripción ya tenía `cancel_at_period_end = True` → `CancellationError` se
  levanta antes del `save()`.
- Si el `status` de la suscripción es inválido para cancelar → `CancellationError`.
- En `execute_cancellation()` — la ejecución efectiva de la baja al vencer el período.
- En `undo_cancellation()` — reversión de la baja programada.

**Archivo de integración:**
```
services/api/src/apps/billing/cancellation_service.py
```
Función: `schedule_cancellation()`, bloque try/except después del `subscription.save(update_fields=...)`.

**Helper usado:**
`send_admin_cancellation_request_received_email(subscription)`  
Importado lazy dentro del bloque try de integración.

**Context enviado al template:**

| Clave | Descripción |
|---|---|
| `business_name` | Nombre del negocio |
| `business_id` | ID del negocio (str) |
| `owner_email` | Email del owner (o vacío si no hay owner) |
| `plan_code` | Código del plan |
| `service_type` | Tipo de servicio |
| `cancel_requested_at` | Fecha de solicitud de baja (dd/mm/YYYY HH:MM) |
| `effective_date` | Fecha efectiva de baja — `current_period_end` (dd/mm/YYYY HH:MM) |
| `cancel_reason` | Motivo de baja (opcional, puede ser vacío) |
| `admin_url` | URL directa a la suscripción en backoffice |

**Metadata guardada:**

| Clave | Valor |
|---|---|
| `event_type` | `"admin_cancellation_request_received"` |
| `subscription_id` | ID de la suscripción (str) |
| `related_business_id` | ID del negocio (str) |
| `service_type` | Tipo de servicio |
| `plan_code` | Código del plan |

**Tests:**
```
apps.billing.tests.test_pr_admin_04_cancellation_request_email   (22 tests)
```

---

### ~~5.4 `admin_review_negative_feedback`~~ — REMOVIDO

> **POLÍTICA DE PRODUCTO:** QR de Reseñas **NO envía emails** a ningún destinatario.
> El template `admin_review_negative_feedback.html` y toda la lógica de envío fueron eliminados.
>
> **Lo que SÍ existe:** la alerta in-app `review_negative` via `AdminNotification`
> (creada con `create_admin_notification()` en `apps/reviews/notifications.py`).  
> Esta notificación es visible en el centro de notificaciones de la plataforma (PR-ADMIN-10C) y
> **no genera ningún email**.
>
> El digest semanal al cliente (`reviews_weekly_digest`, §10.1) también fue eliminado.
>
> **Rollback completado:** templates borrados, `notify_negative_feedback()` reescrita
> (solo in-app), `send_digest_for_business()` y `run_weekly_digest()` convertidas a no-op.
> 279 tests pasando. Ver `docs/QR_RESENAS_FASE1_IMPLEMENTATION_PLAN.md` para historial.

---

---

### 5.5 `admin_payment_failure_recurrent`

**Cuándo se dispara:**
- Cuando una suscripción activa pasa a estado `PAST_DUE` por fallo de cobro o expiración del período de facturación sin pago confirmado.
- **Path 1 — Webhook/activator:** `record_failed_payment()` en `subscription_activator.py` cuando `subscription.status == ACTIVE`.
- **Path 2 — Tarea periódica:** `_transition_active_to_past_due()` en `tasks.py` cuando el update fue exitoso.

**Cuándo NO se dispara:**
- Si la suscripción ya estaba en `PAST_DUE` o `SUSPENDED` antes del evento.
- En `_transition_past_due_to_suspended()` — esa es una transición diferente.
- Si fallan ambos paths: el email es fire-and-forget; no se propaga ni se reintenta.

**Archivos de integración:**
```
services/api/src/apps/billing/subscription_activator.py  — record_failed_payment()
services/api/src/apps/billing/tasks.py                   — _transition_active_to_past_due()
```

**Helper usado:**
`queue_admin_transactional_email(recipient_category="billing", ...)`  
Importado lazy dentro del cuerpo de `send_admin_payment_failure_recurrent_email` para evitar imports circulares.

**Context enviado al template:**

| Clave | Descripción |
|---|---|
| `business_name` | Nombre del negocio |
| `business_id` | ID del negocio (str) |
| `owner_email` | Email del owner del negocio (puede estar vacío si no hay owner) |
| `plan_code` | Código del plan de la suscripción |
| `service_type` | Tipo de servicio de la suscripción |
| `retry_count` | Número de intento (mínimo 1, aunque `retry_count` sea 0 en el path de tarea) |
| `urgency` | `"crítico"` (≥3), `"atención"` (=2) o `"aviso"` (<2) |
| `amount` | Monto intentado (str) — vacío si no hay `invoice_event` |
| `currency` | Moneda — `'ARS'` por defecto si no hay `invoice_event` |
| `failure_reason` | Razón del fallo (str) — vacío si no provisto |
| `provider_status` | Estado en proveedor (str) — vacío si no hay `invoice_event` |
| `grace_until` | Fecha/hora de fin de grace period en `dd/mm/YYYY HH:MM` (opcional) |
| `current_period_end` | Fecha/hora de fin de período en `dd/mm/YYYY HH:MM` (opcional) |
| `invoice_event_id` | ID del `BillingInvoiceEvent` (str) — vacío en path de tarea |
| `admin_url` | URL directa a la suscripción en backoffice (`ADMIN_FRONTEND_URL/suscripciones/{pk}`) |

**Metadata guardada:**

| Clave | Valor |
|---|---|
| `event_type` | `"admin_payment_failure_recurrent"` |
| `subscription_id` | ID de la suscripción (str) |
| `related_business_id` | ID del negocio (str) |
| `plan_code` | Código del plan |
| `service_type` | Tipo de servicio |
| `retry_count` | Número de intento (display_retry_count) |
| `amount` | Monto intentado (str, puede ser vacío) |
| `currency` | Moneda |
| `provider_status` | Estado en proveedor (str, puede ser vacío) |
| `invoice_event_id` | ID del InvoiceEvent (str, puede ser vacío) |

**Tests:**
```
apps.billing.tests.test_pr_admin_08_payment_failure_email   (31 tests)
```

---

## 6. Seguridad — Datos prohibidos en metadata y context

Las siguientes categorías de datos **nunca deben incluirse** en `metadata` ni en el
`context` de ningún email interno ADMIN:

| Categoría | Ejemplos |
|---|---|
| Tokens de autenticación | `access_token`, `refresh_token`, `x_signature`, `authorization` |
| Contraseñas y PINs | passwords, PINs, hash de credenciales |
| Payloads completos de MercadoPago | `raw_payload_json`, body completo del webhook |
| Headers de webhook | `x-signature`, `x-request-id` completos |
| Cuerpo completo de tickets | texto libre del usuario sin sanitizar |
| Datos bancarios | CBU, número de cuenta, tarjeta |
| Datos fiscales sensibles | CUIT/CUIL, datos de facturación completos |

**Todos los emails internos deben pasar por `EmailDelivery`** — no existe código path
que envíe emails sin registro en base de datos.

La función `queue_admin_transactional_email` tiene un guard interno que excluye
automáticamente las siguientes claves de cualquier metadata pasada:

```python
SENSITIVE_METADATA_KEYS = {
    "token", "password", "pin", "secret", "authorization",
    "x_signature", "raw_payload_json", "headers",
}
```

Si alguna de estas claves aparece en `metadata`, se excluye y se loguea un WARNING.

---

## 7. Suites de tests

### Resumen de cobertura

| Suite | Tests | Estado |
|---|---|---|
| `apps.notifications` | ~79 | ✅ Green |
| `apps.accounts.tests.test_pr_admin_02_support_ticket_email` | 17 | ✅ Green |
| `apps.billing.tests.test_pr_admin_03_subscription_payment_email` | 21 | ✅ Green |
| `apps.billing.tests.test_pr_admin_04_cancellation_request_email` | 22 | ✅ Green |
| `apps.billing.tests.test_pr10_cancellation_confirmed_email` | 14 | ✅ Green (no modificado) |
| `apps.reviews.tests.test_pr_admin_06_negative_feedback_email` | 8 | ✅ Green (no-email rollback) |
| `apps.reviews.tests.test_pr_admin_07_reviews_digest_email` | 7 | ✅ Green (no-op rollback) |
| `apps.reviews` (suite completa) | 279 | ✅ OK |
| `apps.billing.tests.test_pr_admin_08_payment_failure_email` | 31 | ✅ Green |
| **Total validado en rollback QR emails** | **279+** | ✅ OK |

### Resultado de `manage.py check`

```
System check identified no issues (0 silenced).
```

### Comando de ejecución completa

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml exec api \
  python manage.py test \
    apps.notifications \
    apps.accounts.tests.test_pr_admin_02_support_ticket_email \
    apps.billing.tests.test_pr_admin_03_subscription_payment_email \
    apps.billing.tests.test_pr_admin_04_cancellation_request_email \
    apps.billing.tests.test_pr10_cancellation_confirmed_email \
    apps.reviews.tests.test_pr_admin_06_negative_feedback_email \
    apps.reviews.tests.test_notifications \
    apps.reviews.tests.test_e2e_lifecycle \
    apps.reviews.tests.test_digest \
    apps.reviews.tests.test_pr_admin_07_reviews_digest_email \
    apps.billing.tests.test_pr_admin_08_payment_failure_email \
  --verbosity=1
```

---

## 8. QA técnico — Resultado de búsquedas

### `send_mail` en `apps/`

El único uso de `send_mail` en código de producción es:

```
(ninguno en apps/reviews/)
```

**`apps/reviews/digest.py` fue migrado en PR-ADMIN-07.** Ya no usa `send_mail`.

**`apps/reviews/notifications.py` fue migrado en PR-ADMIN-06.** Ya no usa `send_mail`.

**No hay ningún uso de `send_mail` en código de producción en `apps/reviews/`.**

Las únicas ocurrencias de `send_mail` en `apps/reviews/` son en tests (mocks negativos
que verifican que NO se usa).

### `EmailMessage` en `apps/`

No existe ningún uso de `django.core.mail.EmailMessage` en código de producción.
Las únicas ocurrencias son en tests (mocks con `@patch("django.core.mail.EmailMessage")`
que verifican que no se usa).

### `queue_admin_transactional_email` — puntos de uso en producción

```
apps/notifications/admin_helpers.py          — definición de la función
apps/accounts/tenant_support_views.py        — PR-ADMIN-02 (soporte)
apps/billing/email_helpers.py (×3)           — PR-ADMIN-03 (billing), PR-ADMIN-04 (operations) y PR-ADMIN-08 (billing)
```

> `apps/reviews/notifications.py` fue **removido** de esta lista — QR de Reseñas ya no envía emails admin.

### `send_admin_payment_failure_recurrent_email` — puntos de integración

```
apps/billing/email_helpers.py                — PR-ADMIN-08 (definición)
apps/billing/subscription_activator.py      — PR-ADMIN-08 (record_failed_payment)
apps/billing/tasks.py                       — PR-ADMIN-08 (_transition_active_to_past_due)
```

### `queue_transactional_email` — puntos de uso en producción

```
apps/notifications/services.py               — definición de la función
```

> `apps/reviews/digest.py` fue **removido** de esta lista — `send_digest_for_business()` es no-op; no llama a `queue_transactional_email`.

---

## 9. Próximos candidatos (pendiente — no implementar en este PR)

| Candidato | Categoría sugerida | Evento disparador |
|---|---|---|
| ~~Digest semanal de reviews por negocio~~ | ~~`platform_admin`~~ | ✅ Implementado en PR-ADMIN-07 — **REMOVIDO** en rollback: `send_digest_for_business()` es no-op, template eliminado |
| Digest semanal interno de métricas ADMIN | `platform_admin` | Celery beat — lunes 8am (nuevo, distinto de `reviews_weekly_digest`) |
| Digest diario de métricas ADMIN | `platform_admin` | Celery beat — diario |
| ~~Alerta de pago fallido recurrente (N fallos)~~ | ~~`billing`~~ | ✅ Completado en PR-ADMIN-08 |
| Centro de notificaciones in-app para operadores | — | Nueva entidad `AdminNotification` |
| Preview de templates en backoffice | — | Nueva vista de administración |
| ~~Migración de `apps.reviews.notifications`~~ | ~~`support`~~ | ✅ Completado en PR-ADMIN-06 |
| ~~Migración de `apps.reviews.digest`~~ | ~~`platform_admin`~~ | ✅ Completado en PR-ADMIN-07 |

---

## ~~10. Emails transaccionales al cliente — Reviews~~ — REMOVIDO

> **POLÍTICA DE PRODUCTO:** QR de Reseñas no envía emails a ningún destinatario — ni internos ni al cliente.
> Toda esta sección queda archivada como referencia histórica.

---

### ~~10.1 `reviews_weekly_digest`~~ — REMOVIDO

> **REMOVIDO** — El template `reviews_weekly_digest.html` fue eliminado y las funciones
> `send_digest_for_business()` y `run_weekly_digest()` en `apps/reviews/digest.py` son no-op
> (devuelven `False` / `{'sent':0, 'skipped':0, 'failed':0}` respectivamente).
> `compute_digest_stats()` se preserva para uso futuro sin envío.

~~**Tipo:** Email transaccional al cliente (owner del negocio)~~  
~~**Helper:** `queue_transactional_email()` en `apps/notifications/services.py`~~

~~**Cuándo se dispara:**~~
~~- Tarea Celery semanal → `run_weekly_digest()` → `send_digest_for_business(business)`.~~
~~- Solo si `smart_filter_allowed(business) == True` (plan Pro o trial activo).~~
~~- Solo si el negocio tuvo al menos 1 reseña o 1 escaneo QR en los últimos 7 días.~~
~~- Guard de caché por ISO-week: máximo 1 digest por negocio por semana.~~

~~**Cuándo NO se dispara:**~~
~~- Negocio en plan base (sin trial activo).~~
~~- Trial vencido.~~
~~- Ninguna actividad (0 reseñas y 0 visitas en los últimos 7 días).~~
~~- Owner sin email registrado.~~
~~- Ya enviado esta semana (guard de caché).~~

~~**Archivo de integración:**~~
~~`services/api/src/apps/reviews/digest.py`~~
~~Función: `send_digest_for_business(business)` → importa `queue_transactional_email` lazy.~~

~~**Destinatario:** Email del primer owner activo del negocio (`ACTIVE` + `role='owner'`).~~  
~~**NO es un email interno ADMIN.** Va directamente al cliente.~~

~~**Context enviado al template:** (eliminado — template removido)~~

~~**Metadata guardada:** (eliminado — no se persiste email delivery)~~

**Tests (rollback):**
```
apps.reviews.tests.test_pr_admin_07_reviews_digest_email   (7 tests — assert no-op)
apps.reviews.tests.test_digest                              (19 tests — SendDigestNoOpTests + RunWeeklyDigestNoOpTests)
```

---

## QR de Reseñas — política de emails

> **Regla de producto (no negociable):** QR de Reseñas **no envía emails a nadie.**

### Emails removidos

| Email | Motivo de remoción |
|---|---|
| `admin_review_negative_feedback` | Email admin interno. Template eliminado. `notify_negative_feedback()` reescrita como in-app only. |
| `reviews_weekly_digest` | Email transaccional al cliente. Template eliminado. `send_digest_for_business()` convertida a no-op. |

### Lo que SÍ está permitido

- **Notificación in-app** `review_negative` via `AdminNotification` (modelo en `apps/accounts`).
- Creada con `create_admin_notification()` desde `apps/reviews/notifications.py`.
- Visible en el centro de notificaciones de plataforma (PR-ADMIN-10C).
- **No genera ningún email.**

### Estado del código (confirmado post-rollback)

| Archivo | Estado |
|---|---|
| `apps/reviews/notifications.py` | ✅ Solo in-app — `create_admin_notification()`, sin email |
| `apps/reviews/digest.py` | ✅ `send_digest_for_business()` → `return False`. `run_weekly_digest()` → `return {'sent':0,...}`. `compute_digest_stats()` preservada. |
| `notifications/templates/emails/admin_review_negative_feedback.html` | ✅ Eliminado |
| `notifications/templates/emails/reviews_weekly_digest.html` | ✅ Eliminado |

---

## 11. Invariantes de diseño

Estas reglas son **no negociables** para futuros PRs que agreguen emails internos ADMIN:

1. Siempre usar `queue_admin_transactional_email` — nunca `send_mail` ni `EmailMessage`.
2. El helper específico siempre devuelve `bool` — nunca propaga excepciones.
3. La integración en el flujo de negocio siempre está en un `try/except Exception` independiente.
4. El fallo del email nunca revierte ni bloquea la operación de negocio.
5. Metadata nunca contiene tokens, contraseñas, payloads crudos ni headers.
6. Cada email nuevo requiere: template HTML, helper en el módulo correspondiente,
   integración en el punto de evento, y suite de tests con mínimo 15 casos.
7. Los imports de `queue_admin_transactional_email` dentro de helpers de módulos externos
   son lazy (dentro del cuerpo de la función) para evitar imports circulares.
8. El patch target en tests es siempre `"apps.notifications.admin_helpers.queue_admin_transactional_email"`
   (donde está definida la función), no el módulo del helper específico.

---

## Centro de notificaciones in-app ADMIN (PR-ADMIN-10B)

PR-ADMIN-10B crea la base persistente del centro de notificaciones:

- Modelo AdminNotification en pps/accounts/admin_notification.py:
  - 16 tipos (NotifType): soporte x4, billing x4, rese�as x2, seguridad x4, sistema x2.
  - Severidades: info, success, warning, critical.
  - Estados: unread ? read ? resolved | archived (m�todos mark_read(), mark_resolved(), mark_archived() idempotentes con timestamps).
  - Deduplicaci�n opcional via dedupe_key (SHA-256[:64]).
  - 4 �ndices nombrados para PostgreSQL.
- Helper create_admin_notification() en pps/accounts/admin_notification_service.py:
  - Best-effort: captura toda excepci�n, loguea y retorna None.
  - Sanitiza metadata (strip de: 	oken, password, pin, secret, uthorization, x_signature, 
aw_payload_json, headers, ccess_token, 
efresh_token).
  - Deduplicaci�n por ventana de tiempo: si dedupe_window_seconds y 
elated_object_id est�n presentes, omite la creaci�n si ya existe una notificaci�n unread/read con la misma clave dentro del per�odo.
- Migraci�n:  029_admin_notification_phase10b.py (accounts).
- Tests: 	est_admin_notification_model.py (27 casos) + 	est_admin_notification_service.py (23 casos).

**NO incluye**: endpoints, frontend, integraciones con eventos reales, ni Celery tasks.
Eso corresponde a PR-ADMIN-10C (endpoints) y etapas posteriores.

### PR-ADMIN-10C — Endpoints backend

PR-ADMIN-10C expone 5 endpoints REST para consumir el centro de notificaciones:

| Método | Path | Nombre URL | Descripción |
|--------|------|-----------|-------------|
| GET  | `/api/v1/platform-admin/notifications/` | `platform-admin-notifications` | Listado paginado (excluye archived por defecto). Filtros: `status`, `severity`, `type`. |
| GET  | `/api/v1/platform-admin/notifications/unread-count/` | `platform-admin-notifications-unread-count` | Devuelve `{count, critical_count}` del usuario autenticado. |
| POST | `/api/v1/platform-admin/notifications/<uuid>/read/` | `platform-admin-notifications-read` | Marca como leída (idempotente). |
| POST | `/api/v1/platform-admin/notifications/<uuid>/archive/` | `platform-admin-notifications-archive` | Archiva la notificación (idempotente). |
| POST | `/api/v1/platform-admin/notifications/<uuid>/resolve/` | `platform-admin-notifications-resolve` | Resuelve la notificación; si estaba unread también setea `read_at` (idempotente). |

**Permisos**: `IsAuthenticated + IsPlatformStaff` en todos los endpoints.

**Scoping**:
- `superadmin` → ve todas las notificaciones.
- Resto → solo `target_user=request.user` O `target_role=internal_role` (excluye broadcasts vacíos).
- Acciones sobre UUIDs fuera del scope devuelven 404.

**Serializer** (`platform_admin_notification_serializers.py`):  
Expone: `id`, `notif_type`, `severity`, `title`, `message`, `status`, `action_url`, `business_id`, `business_name`, `related_object_type`, `related_object_id`, `created_at`, `read_at`, `resolved_at`, `archived_at`.  
**Excluye deliberadamente**: `metadata`, `dedupe_key`, `target_role`, `target_user`.

**Tests**: `test_platform_admin_notifications_views.py` (43 casos).

**NO incluye**: frontend, Bell icon, integración con eventos reales, Celery tasks.
Eso corresponde a PR-ADMIN-10D (frontend) y etapas posteriores.

---

### PR-ADMIN-10E � Integraciones con eventos MVP

Conecta `create_admin_notification()` a los eventos de sistema m�s importantes. Las notificaciones in-app **conviven** con los correos admin existentes y no los reemplazan.

#### Eventos integrados

| notif_type | severity | target_role | Archivo origen | Descripci�n |
|------------|----------|-------------|---------------|-------------|
| `support_ticket_created` | `warning` | `support_agent` | `tenant_support_views.py` � `_notify_admin_ticket_created()` | Nuevo ticket creado por un tenant. Solo se dispara para `ORIGIN_TENANT`. |
| `billing_cancel_request` | `warning` | `operations` | `cancellation_service.py` � `schedule_cancellation()` | El negocio solicit� la baja de su suscripci�n. `dedupe_window=86400 s`. |
| `review_negative` | `warning` | `support_agent` | `reviews/notifications.py` → `notify_negative_feedback()` | Reseña con rating ≤ 3. `dedupe_window=3600 s`. **Solo in-app** — QR de Reseñas no envía emails. |
| `billing_payment_failure` | `critical` | `operations` | `subscription_activator.py` � `record_failed_payment()` | Pago recurrente fallido, suscripci�n transiciona a PAST_DUE. Solo cuando el estado previo era ACTIVE. `dedupe_window=3600 s`. |
| `billing_payment_failure` | `critical` | `operations` | `billing/tasks.py` � `_transition_active_to_past_due()` | Tarea Celery: per�odo vencido sin pago. |
| `billing_suspended` | `critical` | `operations` | `billing/tasks.py` � `_transition_past_due_to_suspended()` | Tarea Celery: per�odo de gracia vencido ? suspendido. `dedupe_window=86400 s`. |

#### Restricciones aplicadas (non-negotiable)

- Sin modelos nuevos, sin migraciones, sin cambios de frontend, sin endpoints, sin cambios de email, sin templates.
- Todas las llamadas: fire-and-forget, envueltas en `try/except Exception`.
- `create_admin_notification()` ya es exception-safe internamente; el `try/except` exterior es documentaci�n y cintur�n-y-tirantes.
- Sin datos sensibles en `metadata` (sin comentario completo, sin passwords, sin emails de contacto).
- `execute_cancellation()` y `undo_cancellation()` no reciben notificaci�n.
- `billing_payment_failure` solo cuando la transici�n ACTIVE?PAST_DUE ocurri� efectivamente.
- `billing_suspended` solo en `_transition_past_due_to_suspended` (no en `_trial_to_suspended` ni similares).

#### Tests de integraci�n

| Archivo | Casos | Cobertura |
|---------|-------|-----------|
| `apps/accounts/tests/test_admin_notification_support_integration.py` | 12 | helper support, guard ORIGIN_ADMIN, excepci�n no propaga, metadata |
| `apps/billing/tests/test_admin_notification_billing_integration.py` | 15 | schedule/execute cancellation, record_failed_payment, task transitions |
| `apps/reviews/tests/test_admin_notification_reviews_integration.py` | 15 | rating = 3 crea notif, rating = 4 no crea, metadata sin comment, excepci�n |

Total: 42 casos. Todos pasan en `manage.py test`.
