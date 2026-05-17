# Auditoría de Eventos de Email — Módulo Billing

> **Scope**: Identificar exactamente *dónde* y *cuándo* se deben disparar emails transaccionales
> relacionados con el ciclo de vida de suscripciones y pagos. **Solo auditoría — cero código modificado.**
>
> **Autor**: GitHub Copilot — PR-6  
> **Fecha**: 2025

---

## 1. Resumen ejecutivo

El módulo `apps.billing` implementa un sistema robusto de suscripciones con MercadoPago.
Actualmente **ningún email transaccional se dispara** desde este módulo; la infraestructura
(`queue_transactional_email`, `EmailDelivery`, Celery) ya está disponible en `apps.notifications`.

Se identifican **4 eventos** que merecen un email transaccional, distribuidos en **4 PRs**:

| PR | Template key | Evento | Prioridad |
|----|-------------|--------|-----------|
| PR-7  | `subscription_activated` | Primera activación de suscripción (pago exitoso) | Alta |
| PR-8  | `payment_failed`         | Fallo de cobro recurrente → PAST_DUE           | Alta |
| PR-9  | `subscription_suspended` | Gracia expirada → SUSPENDED                     | Media |
| PR-10 | `cancellation_confirmed` | Cancelación efectiva ejecutada                   | Media |

---

## 2. Mapa de eventos de billing

### 2.1 Máquina de estados `SubscriptionV2`

```
CHECKOUT_PENDING
    │ (webhook preapproval recibido → MpCheckoutSession.LINKED)
    ▼
TRIALING ──── trial_ends_at expirado (tarea) ────────────────┐
    │ (primer pago authorized)                                │
    ▼                                                         │
ACTIVE ──── current_period_end expirado (tarea) ───► PAST_DUE │
    │ (pago recurrente falla → record_failed_payment)         │  └─► SUSPENDED ──► CANCELED (manual/MP)
    └─────────────────────────────────────────────────────────┘
    │ (schedule_cancellation + execute_cancellation)
    ▼
CANCELED (terminal)
```

### 2.2 Tabla de eventos

| # | Evento | Archivo | Función | Estado anterior | Estado nuevo | Idempotente | Email recomendado |
|---|--------|---------|---------|-----------------|--------------|-------------|-------------------|
| 1 | Primer pago aprobado (webhook `subscription_authorized_payment`) | `webhook_processor.py` | `_handle_authorized_payment()` → `activate_subscription_from_invoice()` | CHECKOUT_PENDING / TRIALING | ACTIVE | Sí — doble-checked lock en `activate_subscription_from_invoice()` + `BillingInvoiceEvent` dedup por `provider_authorized_payment_id` | `subscription_activated` |
| 2 | Pago recurrente rechazado | `webhook_processor.py` | `_handle_authorized_payment()` → `record_failed_payment()` | ACTIVE | PAST_DUE | Sí — `BillingInvoiceEvent` dedup + `record_failed_payment()` solo actúa si status==ACTIVE | `payment_failed` |
| 3 | Período vencido sin pago (tarea Celery) | `tasks.py` | `_transition_active_to_past_due()` | ACTIVE | PAST_DUE | Sí — `update()` con filtro `status=ACTIVE`; retorna 0 si ya cambió | `payment_failed` (mismo template, contexto distinto) |
| 4 | Gracia expirada → suspensión (tarea Celery) | `tasks.py` | `_transition_past_due_to_suspended()` | PAST_DUE | SUSPENDED | Sí — `update()` con filtro `status=PAST_DUE`; retorna 0 si ya cambió | `subscription_suspended` |
| 5 | Trial expirado sin pago (tarea Celery) | `tasks.py` | `_transition_trial_to_suspended()` | TRIALING | SUSPENDED | Sí — `update()` con filtro `status=TRIALING`; retorna 0 si ya cambió | `subscription_suspended` |
| 6 | Cancelación ejecutada (HTTP / servicio) | `cancellation_service.py` | `execute_cancellation()` | ACTIVE / PAST_DUE | CANCELED | Sí — `execute_cancellation()` es no-op si ya está CANCELED | `cancellation_confirmed` |
| 7 | Cancelación sync desde MP (webhook) | `webhook_processor.py` | `_handle_subscription_preapproval()` | ACTIVE / cualquiera | CANCELED (sync) | Sí — mismo guard que en el servicio | `cancellation_confirmed` (con cautela, ver §4) |

---

## 3. Emails recomendados

### 3.1 `subscription_activated` (PR-7)

| Campo | Valor |
|-------|-------|
| **template_key** | `subscription_activated` |
| **Subject** | `¡Tu suscripción a MiRubro está activa!` |
| **Destinatario** | Owner del negocio: `checkout_session.user` (disponible en activator) |
| **Contexto** | `business_name`, `plan_name`, `billing_period`, `next_billing_date`, `amount`, `dashboard_url` |
| **Trigger exacto** | Después de que `activate_subscription_from_invoice()` retorna `True` en `_handle_authorized_payment()`, **fuera** del bloque `transaction.atomic()` (mismo patrón que `handle_promo_cycle()`) |
| **Riesgo duplicación** | Bajo — la función retorna `False` si la sub ya estaba ACTIVE; `BillingInvoiceEvent` deduplicado por `provider_authorized_payment_id` |
| **Prioridad** | Alta |

### 3.2 `payment_failed` (PR-8)

#### Origen 1: webhook `subscription_authorized_payment` rechazado

| Campo | Valor |
|-------|-------|
| **template_key** | `payment_failed` |
| **Subject** | `Hubo un problema con el pago de tu suscripción` |
| **Destinatario** | Owner: `subscription.checkout_session.user` o via `Membership` (ver §3.6) |
| **Contexto** | `business_name`, `plan_name`, `amount`, `failure_reason`, `retry_date`, `billing_url` |
| **Trigger exacto** | Dentro de `record_failed_payment()`, después de `_set_tenant_past_due(subscription)` — fuera de cualquier transacción activa |
| **Riesgo duplicación** | Bajo — `record_failed_payment()` actúa solo si `status==ACTIVE`; la invoice event está deduplicada |
| **Prioridad** | Alta |

#### Origen 2: tarea `_transition_active_to_past_due`

| Campo | Valor |
|-------|-------|
| **template_key** | `payment_failed` |
| **Subject** | `Tu suscripción está con pago vencido` |
| **Destinatario** | Owner: resolución via `Membership` por `business_id` (disponible en `row['business_id']`) |
| **Contexto** | `business_name`, `grace_until`, `billing_url` |
| **Trigger exacto** | Dentro del loop en `_transition_active_to_past_due()`, cuando `updated == 1`, **después** del `SubscriptionV2.objects.filter(pk=...).update(...)` |
| **Riesgo duplicación** | Bajo si `updated == 1` (condición estricta); riesgo si la tarea Celery reintenta tras fallo parcial — `retry_count` en la sub puede usarse como guard extra |
| **Prioridad** | Alta |

### 3.3 `subscription_suspended` (PR-9)

| Campo | Valor |
|-------|-------|
| **template_key** | `subscription_suspended` |
| **Subject** | `Tu acceso a MiRubro fue suspendido` |
| **Destinatario** | Owner: resolución via `Membership` por `business_id` |
| **Contexto** | `business_name`, `grace_expired_at`, `reactivation_url`, `support_email` |
| **Trigger exacto** | Dentro del loop en `_transition_past_due_to_suspended()` y `_transition_trial_to_suspended()`, cuando `updated == 1` |
| **Riesgo duplicación** | Bajo — `update()` condicional en `status=PAST_DUE` o `status=TRIALING`; riesgo si Celery reintenta (max_retries=3) sin idempotencia adicional |
| **Prioridad** | Media |

### 3.4 `cancellation_confirmed` (PR-10)

| Campo | Valor |
|-------|-------|
| **template_key** | `cancellation_confirmed` |
| **Subject** | `Tu suscripción a MiRubro fue cancelada` |
| **Destinatario** | Owner: `subscription.checkout_session.user` o via `Membership` |
| **Contexto** | `business_name`, `plan_name`, `canceled_at`, `access_until`, `resubscribe_url` |
| **Trigger exacto** | Al final de `execute_cancellation()`, después de `subscription.save()` y **fuera** de cualquier transacción activa — o desde la vista HTTP que invoca el servicio |
| **Riesgo duplicación** | Medio — `execute_cancellation()` es idempotente (no-op si ya CANCELED), pero si se llama dos veces antes de que la DB persista (race), podría disparar dos emails; agregar guard `subscription.status != Status.CANCELED` antes de enviar |
| **Prioridad** | Media |

### 3.5 Resolución del owner (patrón recomendado)

Dependiendo del punto de inyección, hay dos caminos:

**Camino A — Desde `subscription_activator.py` o similar (sesión de checkout disponible)**

```python
owner = getattr(subscription, 'checkout_session', None) and subscription.checkout_session.user
```

**Camino B — Desde tasks.py (solo `business_id` disponible en el loop)**

```python
from apps.accounts.models import Membership

def _get_owner_user(business_id):
    """Resolve the owner User for a Business. Returns None if not found or no email."""
    m = (
        Membership.objects
        .filter(business_id=business_id, role='owner')
        .select_related('user')
        .first()
    )
    if m and m.user and m.user.email:
        return m.user
    return None
```

Este helper debe vivir en un módulo compartido (p.ej. `apps.billing.email_helpers`) para evitar duplicación entre PRs.

### 3.6 Template base y contexto mínimo común

Todos los templates extienden `emails/base.html`.
Contexto mínimo garantizado por `queue_transactional_email`:

- `user_name` — nombre del destinatario
- `business_name` — nombre del negocio
- `support_email` — email de soporte

---

## 4. Riesgos identificados

### 4.1 Webhooks duplicados de MercadoPago

**Descripción**: MP puede enviar el mismo webhook múltiples veces (reintentos por timeout o error 5xx).

**Mitigación existente**:
- `WebhookDelivery` deduplicado por `x_request_id` (primary) y `payload_hash` (fallback) — procesamiento se salta si `ProcessingStatus == DUPLICATED`
- `BillingInvoiceEvent` deduplicado por `provider_authorized_payment_id` via `get_or_create`
- `activate_subscription_from_invoice()` usa `select_for_update()` + re-check tras lock → retorna `False` si sub ya ACTIVE

**Gap**: Si el primer webhook falla *después* de disparar el email pero *antes* de guardar `WebhookDelivery.PROCESSED`, el reintento pasará la deduplicación y podría enviar un segundo email.

**Mitigación adicional recomendada** (PR-7): Verificar `subscription.is_active` *antes* de enviar el email dentro del bloque email — esto no es 100% seguro pero reduce ventana de duplicación.

### 4.2 Pago reintentado vs. pago nuevo

**Descripción**: Una sub en PAST_DUE puede recibir un nuevo `authorized_payment` webhook cuando MercadoPago reintenta el cobro automáticamente. `activate_subscription_from_invoice()` volvería a correr y retornaría `True` (re-activación desde PAST_DUE → ACTIVE).

**Impacto email**: `subscription_activated` se enviaría tanto en la activación inicial como en re-activaciones desde PAST_DUE.

**Decisión de diseño**: En PR-7, considerar un subject diferente para re-activaciones (ej. "Tu suscripción fue reactivada"). Se puede distinguir chequeando `subscription.retry_count > 0` antes de enviar.

### 4.3 Cambio de estado repetido en tareas Celery

**Descripción**: La tarea `expire_subscriptions` tiene `max_retries=3`. Si el worker muere tras hacer el `.update()` pero antes de completar el loop (ej. mid-email), el retry verá `status=PAST_DUE` y NO actualizará (condición `status=ACTIVE` falla) — por tanto no enviará email duplicado. **Este es el comportamiento correcto**: el guard `updated == 1` en el loop es suficiente.

**Riesgo residual**: Si el email se dispara *antes* del commit de la transacción, el email llegaría pero la DB no lo reflejaría. Todos los emails deben dispararse **después** del `.update()` confirmado.

### 4.4 Owner sin email (cuenta Google-only)

**Descripción**: Usuarios que se registraron solo con Google OAuth no necesariamente tienen `email` poblado en el User record (depende del proveedor).

**Mitigación**: Siempre verificar `user.email` antes de invocar `queue_transactional_email`. El helper `_get_owner_user()` del §3.5 ya incluye este guard.

### 4.5 Negocio sin owner con rol `owner`

**Descripción**: En teoría posible si un `Membership` fue borrado manualmente o si la sub se creó por un path de datos corruptos.

**Mitigación**: El helper `_get_owner_user()` retorna `None` y el caller debe loguear y no fallar. El email es best-effort — no debe bloquear el cambio de estado.

### 4.6 Email disparado antes de commit (transacciones)

**Descripción**: Si el email se envía dentro de un `transaction.atomic()` y la transacción hace rollback posterior, el email ya habrá sido encolado/enviado con datos incorrectos.

**Regla**: **Nunca** llamar a `queue_transactional_email` dentro de un bloque `transaction.atomic()`. Todos los puntos de inyección identificados en este documento están fuera de transacciones activas (mismo patrón que `handle_promo_cycle()` en PR-3).

### 4.7 Cancelación sincronizada desde MP webhook

**Descripción**: `_handle_subscription_preapproval()` puede setear la sub a CANCELED cuando MP reporta `status='cancelled'` en el webhook (sin que el usuario lo haya pedido explícitamente desde nuestro sistema).

**Riesgo**: Si se dispara `cancellation_confirmed` desde aquí, puede llegar al owner como cancelación inesperada. Podría confundirse con una cancelación por falta de pago.

**Recomendación**: En PR-10, evaluar si disparar el email desde el webhook MP o solo desde `execute_cancellation()`. Preferir solo desde `execute_cancellation()` para evitar emails por sincronizaciones internas de MP.

---

## 5. Plan de implementación por PRs

### PR-7: `subscription_activated`

**Archivo a modificar**: `services/api/src/apps/billing/webhook_processor.py`  
**Función**: `_handle_authorized_payment()`  
**Ubicación exacta**: Después del bloque `if activated:` que llama a `handle_promo_cycle()`, usando el mismo patrón fire-and-forget.

```python
# Pseudocódigo — NO implementar aquí, solo referencia para PR-7
if activated:
    handle_promo_cycle(subscription)  # ya existe
    # >>> NUEVO (PR-7): enviar email subscription_activated
    _send_subscription_activated_email(subscription)
```

**Template**: `emails/subscription_activated.html` (crear en PR-7)  
**Helper de email**: `EmailService.send_subscription_activated_email(subscription)` (crear en PR-7)  
**Owner**: `subscription.checkout_session.user` (selectivamente) con fallback a `Membership`

---

### PR-8: `payment_failed`

**Archivos a modificar**:
1. `services/api/src/apps/billing/subscription_activator.py` — función `record_failed_payment()`
2. `services/api/src/apps/billing/tasks.py` — función `_transition_active_to_past_due()`

**Ubicación en `record_failed_payment()`**: Después de `_set_tenant_past_due(subscription)`, fuera de cualquier transacción.

**Ubicación en `_transition_active_to_past_due()`**: Dentro del loop, cuando `updated == 1`, después del `.update()`.

**Template**: `emails/payment_failed.html` (crear en PR-8)  
**Owner para tarea**: helper `_get_owner_user(business_id)` — consulta `Membership` por `business_id`

---

### PR-9: `subscription_suspended`

**Archivos a modificar**: `services/api/src/apps/billing/tasks.py`  
**Funciones**: `_transition_past_due_to_suspended()` y `_transition_trial_to_suspended()`  
**Ubicación**: Dentro del loop, cuando `updated == 1`, después del `.update()`.

**Template**: `emails/subscription_suspended.html` (crear en PR-9)  
**Owner**: mismo helper que PR-8 (`_get_owner_user(business_id)`)

**Nota**: Los loops ya existen en la implementación actual (el código lee los registros con `.values()` y actualiza uno por uno) — agregar email es un cambio mínimo.

---

### PR-10: `cancellation_confirmed`

**Archivo a modificar**: `services/api/src/apps/billing/cancellation_service.py`  
**Función**: `execute_cancellation()`  
**Ubicación**: Al final de la función, después de `subscription.save(...)` y del bloque condicional que actualiza el estado.

**Template**: `emails/cancellation_confirmed.html` (crear en PR-10)  
**Owner**: `subscription.checkout_session.user` (si disponible) con fallback a `Membership`  
**Guard**: Verificar que el cambio de estado realmente ocurrió (no fue un no-op por idempotencia).

---

## 6. Tests necesarios

Para cada PR, el plan de tests sigue el patrón establecido en PR-4 y PR-5.

### Estructura recomendada por PR

```
apps/billing/tests/test_pr7_subscription_activated_email.py
apps/billing/tests/test_pr8_payment_failed_email.py
apps/billing/tests/test_pr9_subscription_suspended_email.py
apps/billing/tests/test_pr10_cancellation_confirmed_email.py
```

### Casos de test por evento

#### PR-7 — `subscription_activated`

| # | Caso | Tipo |
|---|------|------|
| 1 | `activate_subscription_from_invoice()` retorna `True` → email encolado 1 vez | Unit |
| 2 | `activate_subscription_from_invoice()` retorna `False` (ya activa) → email NO disparado | Unit |
| 3 | Email con owner sin `email` (Google-only) → función retorna `False`, no crashea | Unit |
| 4 | Webhook duplicado (segundo `authorized_payment` mismo ID) → email NO disparado segunda vez | Unit |
| 5 | `queue_transactional_email` lanza excepción → activación no se revierte | Unit |
| 6 | Flujo completo webhook → activación → email encolado | Integration |

#### PR-8 — `payment_failed`

| # | Caso | Tipo |
|---|------|------|
| 1 | `record_failed_payment()` en sub ACTIVE → email encolado | Unit |
| 2 | `record_failed_payment()` en sub ya PAST_DUE → email NO encolado (guard status) | Unit |
| 3 | Tarea `_transition_active_to_past_due()` para 1 sub → email encolado 1 vez | Unit |
| 4 | Tarea para 3 subs → 3 emails (una por sub) | Unit |
| 5 | Negocio sin owner con rol `owner` → log warning, no crash | Unit |
| 6 | `updated == 0` (race condition, otra tarea ganó) → email NO encolado | Unit |

#### PR-9 — `subscription_suspended`

| # | Caso | Tipo |
|---|------|------|
| 1 | `_transition_past_due_to_suspended()` para 1 sub → email encolado | Unit |
| 2 | `_transition_trial_to_suspended()` para 1 sub → email encolado | Unit |
| 3 | `updated == 0` → email NO encolado | Unit |
| 4 | Owner sin email → log, no crash | Unit |
| 5 | Tarea reintenta (Celery retry) → segunda pasada no reenvía (guard updated==0) | Unit |

#### PR-10 — `cancellation_confirmed`

| # | Caso | Tipo |
|---|------|------|
| 1 | `execute_cancellation()` en sub ACTIVE → email encolado | Unit |
| 2 | `execute_cancellation()` en sub ya CANCELED (idempotente) → email NO encolado | Unit |
| 3 | Owner sin email → log, no crash | Unit |
| 4 | MP API falla → `execute_cancellation()` lanza excepción → email NO encolado | Unit |
| 5 | Flujo completo: HTTP cancellation request → DB update → email | Integration |

---

## 7. Apéndice técnico

### 7.1 Referencia de archivos clave

| Archivo | Propósito |
|---------|-----------|
| `apps/billing/webhook_processor.py` | Recibe, deduplica y despacha webhooks de MP |
| `apps/billing/subscription_activator.py` | Activa subs, registra fallos de pago |
| `apps/billing/cancellation_service.py` | Ciclo de vida de cancelación |
| `apps/billing/tasks.py` | Tareas Celery: expire_subscriptions, expire_checkout_sessions |
| `apps/billing/models.py` | SubscriptionV2, BillingInvoiceEvent, WebhookDelivery, MpCheckoutSession |
| `apps/billing/enforcement.py` | Capa de decisión de acceso (no modificar para emails) |
| `apps/notifications/__init__.py` | `queue_transactional_email()` — punto de entrada de emails |
| `apps/accounts/services.py` | `EmailService` — patrón a seguir para métodos de email |

### 7.2 Signatura de `queue_transactional_email`

```python
queue_transactional_email(
    *,
    to_email: str,
    subject: str,
    template_key: str,     # busca emails/{template_key}.html
    context: dict,
    business=None,         # FK a Business, opcional
    user=None,             # FK a User, opcional
    send_async: bool = True,
)
```

### 7.3 Patrón de email helper (seguir en cada PR)

```python
# En apps/billing/email_helpers.py (nuevo archivo a crear en PR-7)
import logging
from apps.notifications import queue_transactional_email

logger = logging.getLogger(__name__)

def get_owner_user(business_id):
    """Resolve the owner User for a Business. Returns None if not found or no email."""
    from apps.accounts.models import Membership
    m = (
        Membership.objects
        .filter(business_id=business_id, role='owner')
        .select_related('user')
        .first()
    )
    if m and m.user and getattr(m.user, 'email', None):
        return m.user
    return None
```

### 7.4 Estado actual de tests en `apps/billing/tests/`

Los 18 archivos de test existentes cubren: webhook signature, webhook processor, subscription birth path, enforcement, promo cycle, cancellation, upgrade/downgrade de reviews, etc. **Ninguno prueba emails.** Los tests de PR-7 a PR-10 son los primeros en este dominio.

### 7.5 Deduplicación vs. idempotencia — resumen

| Capa | Mecanismo | Cubre |
|------|-----------|-------|
| `WebhookDelivery` | `x_request_id` + `payload_hash` | Webhooks duplicados de MP |
| `BillingInvoiceEvent` | `provider_authorized_payment_id` unique | Pagos duplicados procesados |
| `activate_subscription_from_invoice()` | `select_for_update()` + re-check | Race conditions en activación |
| `execute_cancellation()` | guard `status == CANCELED` | Cancelaciones dobles |
| `tasks.py` loops | `updated == 1` check | Tareas Celery con retry |
| **Email layer** | **ninguno (GAP)** | **Envíos duplicados** |

El GAP en la capa de email se mitiga con los guards en las capas superiores. Para un sistema de producción a escala, agregar en PR-7 un campo `email_sent_at` en `SubscriptionV2` o una tabla `BillingEmailLog` permitiría deduplicación explícita.
