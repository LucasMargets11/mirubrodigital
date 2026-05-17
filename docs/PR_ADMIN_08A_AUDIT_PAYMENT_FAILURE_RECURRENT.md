# PR-ADMIN-08A — Audit: Email Interno `admin_payment_failure_recurrent`

**Tipo**: Auditoría técnica (read-only — sin cambios de código)
**Fecha**: 2026-05-11
**Autor**: GitHub Copilot
**Prerequisito**: PR-ADMIN-07 ✅ (`reviews_weekly_digest`)
**Próximo PR**: PR-ADMIN-08 (implementación del email)

---

## 1. Resumen Ejecutivo

El objetivo de este audit es mapear con precisión el flujo de pago fallido en
`apps.billing` para diseñar, sin ambigüedad, la notificación interna
`admin_payment_failure_recurrent`. Este email debe alertar al equipo de billing
cuando una suscripción **ya activa** recibe un fallo de cobro recurrente
(renovación), incrementando el contador `retry_count`.

**Hallazgo principal**: el punto de integración es `record_failed_payment()` en
`subscription_activator.py`, específicamente dentro del bloque que sólo ejecuta
cuando `subscription.status == ACTIVE`. Ya existe un email al cliente
(`send_payment_failed_email`) disparado desde ese mismo punto; el nuevo email
admin se agrega en paralelo, con el mismo patrón fire-and-forget.

**No existe** ninguna referencia a `admin_payment_failure_recurrent` en el
codebase — la implementación parte de cero.

---

## 2. Archivos Revisados

| Archivo | Propósito |
|---|---|
| `apps/billing/webhook_processor.py` | Entry point de webhooks MP; despacha a handlers por topic |
| `apps/billing/subscription_activator.py` | Activación, fallo y suspensión de suscripciones |
| `apps/billing/email_helpers.py` | Todos los helpers de email de billing (cliente + admin) |
| `apps/billing/models.py` | `SubscriptionV2`, `BillingInvoiceEvent`, `WebhookDelivery`, `MpCheckoutSession` |
| `apps/billing/tasks.py` | Tareas Celery: `expire_subscriptions`, `expire_checkout_sessions` |
| `apps/billing/tests/test_pr8_payment_failed_email.py` | Tests actuales del flujo de pago fallido |
| `apps/billing/tests/test_pr_admin_03_subscription_payment_email.py` | Referencia de patrón para email admin en billing |

---

## 3. Flujo Actual de Pago Fallido

### 3.1 Ruta principal — `subscription_authorized_payment` webhook

```
MP → POST /api/v1/billing/webhook/
  │
  ▼
webhook_processor.receive_webhook()
  │   ├── Persiste WebhookDelivery (ANTES de toda lógica)
  │   ├── Verifica firma HMAC-SHA256
  │   └── Detección de duplicados (x_request_id o payload_hash)
  │
  ▼
webhook_processor.dispatch_webhook()
  │
  ▼
_handle_authorized_payment(authorized_payment_id, delivery)
  │   ├── Fetch autoritativo desde MP: get_authorized_payment()
  │   ├── Upsert BillingInvoiceEvent (idempotente por provider_authorized_payment_id)
  │   ├── Busca SubscriptionV2 por provider_sub_id
  │   │
  │   ├── [ap_status == 'authorized'] → activate_subscription_from_invoice()
  │   │     → Si returns True: send_subscription_activated_email()
  │   │                         send_admin_subscription_payment_created_email()  ← PR-ADMIN-03
  │   │
  │   └── [ap_status != 'authorized'] → LOG "not activating"
  │         ⚠️  NO HAY LLAMADA A record_failed_payment() DESDE ESTE PUNTO
  │
  ▼
  (status != 'authorized' es logueado pero NO maneja fallo activo)
```

**Conclusión crítica**: el webhook `subscription_authorized_payment` con
`ap_status != 'authorized'` no llama a `record_failed_payment()`. El flujo de
pago fallido actualmente se activa desde **dos fuentes separadas**:

### 3.2 Ruta A — Tarea Celery `expire_subscriptions`

```
celery beat → expire_subscriptions()
  │
  ▼
_transition_active_to_past_due(SubscriptionV2, now)
  │   ├── Filtra: status=ACTIVE, current_period_end < now
  │   ├── UPDATE status=PAST_DUE, grace_until=…
  │   └── [updated == 1] → send_payment_failed_email(sub)  ← email al cliente
  │         ⚠️  NO llama record_failed_payment()
  │         ⚠️  NO incrementa retry_count
  │
  ▼
_transition_past_due_to_suspended(SubscriptionV2, now)
  │   ├── Filtra: status=PAST_DUE, grace_until < now
  │   ├── UPDATE status=SUSPENDED
  │   └── send_subscription_suspended_email(sub, reason='grace_period_expired')
```

### 3.3 Ruta B — `record_failed_payment()` en `subscription_activator.py`

```python
def record_failed_payment(*, invoice_event, subscription, reason=''):
    if subscription.status == SubscriptionV2.Status.ACTIVE:
        # Renewal failure — downgrade to past_due
        subscription.status     = SubscriptionV2.Status.PAST_DUE
        subscription.retry_count = (subscription.retry_count or 0) + 1
        subscription.save(update_fields=['status', 'retry_count', 'updated_at'])
        _set_tenant_past_due(subscription)
        send_payment_failed_email(subscription, reason=reason or None,
                                  amount=getattr(invoice_event, 'amount', None))
    # else: still checkout_pending or trialing — leave as is.
```

**Callers actuales de `record_failed_payment()`**: únicamente
`apps/billing/tests/test_pr8_payment_failed_email.py` (tests). No hay ninguna
llamada a `record_failed_payment()` desde `webhook_processor.py` ni desde
`tasks.py`. La función existe pero **no está integrada en el flujo de producción**.

---

## 4. Modelos y Campos Disponibles

### 4.1 `SubscriptionV2`

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `business` | FK → Business | Tenant |
| `service_type` | CharField | `gestion`, `qr_reviews`, etc. |
| `plan_code` | CharField | e.g. `gestion_pro_monthly` |
| `provider` | CharField | `mercadopago` / `stripe` / `manual` |
| `provider_sub_id` | CharField unique | MP preapproval ID |
| `status` | CharField | `checkout_pending` / `trialing` / `active` / `past_due` / `suspended` / `canceled` |
| `retry_count` | SmallIntegerField | Incrementado en `record_failed_payment()` |
| `grace_until` | DateTimeField nullable | Deadline antes de SUSPENDED |
| `current_period_end` | DateTimeField nullable | Fin del período de facturación |
| `is_active` | BooleanField | True sólo cuando se confirmó primer pago |
| `checkout_session` | FK → MpCheckoutSession | Origen del checkout |
| `created_at` / `updated_at` | DateTimeField | Auditoría |

**Campos clave para "recurrente"**:
- `retry_count`: cuántas veces falló el cobro en el período actual
- `status == PAST_DUE`: estado post-fallo
- `grace_until`: cuándo expira la gracia

### 4.2 `BillingInvoiceEvent`

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `subscription` | FK → SubscriptionV2 | Nullable (race condition) |
| `provider_authorized_payment_id` | CharField unique | Idempotency key MP |
| `provider_payment_id` | CharField | MP payment_id |
| `provider_subscription_id` | CharField | MP preapproval_id |
| `amount` | DecimalField | Monto intentado |
| `currency` | CharField | `ARS` |
| `provider_status` | CharField | `authorized` / `pending` / `cancelled` |
| `paid_at` | DateTimeField nullable | Fecha del pago (si authorized) |
| `webhook_delivery` | FK → WebhookDelivery | Trazabilidad |
| `created_at` / `updated_at` | DateTimeField | Auditoría |

### 4.3 `WebhookDelivery`

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `topic` | CharField | `subscription_authorized_payment` |
| `resource_id` | CharField | authorized_payment_id |
| `x_request_id` | CharField | Idempotency key MP |
| `processing_status` | CharField | `received` / `processed` / `failed` / `duplicated` / `ignored` |
| `error_message` | TextField | Error si falló |
| `received_at` | DateTimeField | Cuándo llegó |
| `processed_at` | DateTimeField nullable | Cuándo se procesó |

---

## 5. Dónde se Dispara el Email al Cliente en Fallo de Pago

Actualmente **dos rutas** disparan `send_payment_failed_email()`:

| Fuente | Condición | Incrementa retry_count |
|---|---|---|
| `_transition_active_to_past_due()` en `tasks.py` | `status=ACTIVE` + `current_period_end < now` → UPDATE a PAST_DUE | ❌ No |
| `record_failed_payment()` en `subscription_activator.py` | `status=ACTIVE` → PAST_DUE por fallo explícito | ✅ Sí |

**Importante**: `record_failed_payment()` no está llamada desde ningún path de
producción en este momento — sólo está testeada directamente.

La ruta real de producción para "período expirado sin cobro nuevo" es la tarea
Celery `expire_subscriptions` → `_transition_active_to_past_due()`.

---

## 6. Riesgos de Duplicación

### 6.1 Dedup en WebhookDelivery

Cada webhook MP crea un `WebhookDelivery`. La deduplicación es por:
- **Primary key**: `x_request_id` (presente en casi todos los webhooks MP)
- **Fallback**: `(topic + resource_id + payload_hash)`

Si llega un webhook duplicado: `processing_status=DUPLICATED` → flujo se
detiene antes del handler → no se crea ni actualiza BillingInvoiceEvent →
no se dispara ningún email. **El guard de dupes ya existe y funciona.**

### 6.2 Dedup en `_handle_authorized_payment()`

`BillingInvoiceEvent` se hace upsert con `get_or_create(provider_authorized_payment_id=...)`.
Si el evento ya existe, sólo actualiza campos mutables (status, paid_at). No
activa, no envía email. **Idempotente a nivel BillingInvoiceEvent.**

### 6.3 Riesgo de doble email admin

El email admin `admin_payment_failure_recurrent` será disparado en el mismo
punto que el email cliente `send_payment_failed_email`. Dado que ese punto
sólo se alcanza cuando:
1. `WebhookDelivery` no es duplicado
2. O la tarea Celery hace `updated == 1` (optimistic update)

**El riesgo de doble disparo es bajo**, siempre que se mantenga el mismo
condicional de guarda (`if updated:` o el check de status en
`record_failed_payment`).

### 6.4 Riesgo de retry_count alto sin email separado

Si el mismo negocio tiene múltiples fallos (retry_count = 2, 3…), actualmente
se envía un `payment_failed` al cliente en cada ciclo. El email admin futuro
debería distinguir si es el **primer fallo** (`retry_count == 1`) o un **fallo
recurrente** (`retry_count >= 2`) para alertar con mayor urgencia al equipo
billing.

---

## 7. Definición Recomendada de "Pago Fallido Recurrente"

Para el email `admin_payment_failure_recurrent` se recomienda la siguiente
semántica:

> **Pago fallido recurrente** = cualquier transición de `ACTIVE → PAST_DUE`
> disparada por expiración de período (`current_period_end < now`) o por
> rechazo explícito del cobro MP (`provider_status != 'authorized'`), cuando la
> suscripción tenía estado `ACTIVE` — es decir, ya había sido activada
> previamente por al menos un pago aprobado.

Esto excluye:
- Suscripciones en `CHECKOUT_PENDING` o `TRIALING` que nunca pagaron.
- Transiciones `PAST_DUE → SUSPENDED` (ya cubiertas por otra alerta futura).
- Webhooks duplicados (ya filtrados por `WebhookDelivery`).

**Criterio de urgencia por retry_count**:
| `retry_count` | Significado | Urgencia en email |
|---|---|---|
| 1 | Primer fallo del período | 🟡 Aviso |
| 2 | Segundo fallo | 🟠 Atención |
| ≥ 3 | Múltiples fallos consecutivos | 🔴 Crítico |

El email admin puede incluir `retry_count` en el context para que el template
muestre la urgencia apropiada.

---

## 8. Punto Exacto de Integración Recomendado

### Opción A — Integrar en `record_failed_payment()` (RECOMENDADA)

```python
# subscription_activator.py — record_failed_payment()

if subscription.status == SubscriptionV2.Status.ACTIVE:
    subscription.status     = SubscriptionV2.Status.PAST_DUE
    subscription.retry_count = (subscription.retry_count or 0) + 1
    subscription.save(update_fields=['status', 'retry_count', 'updated_at'])
    _set_tenant_past_due(subscription)

    # Existing: email al cliente
    from .email_helpers import send_payment_failed_email
    send_payment_failed_email(subscription, reason=reason or None,
                              amount=getattr(invoice_event, 'amount', None))

    # NEW PR-ADMIN-08: email interno admin
    from .email_helpers import send_admin_payment_failure_recurrent_email
    try:
        send_admin_payment_failure_recurrent_email(subscription, invoice_event, reason=reason)
    except Exception as exc:
        logger.exception("[activator] send_admin_payment_failure_recurrent_email failed: %s", exc)
```

### Opción B — Integrar en `_transition_active_to_past_due()` en `tasks.py`

Mismo patrón: después del `send_payment_failed_email(sub)` ya existente,
agregar llamada al helper admin. Esta es la ruta de producción real actualmente.

**Recomendación**: implementar en **ambas rutas** para cobertura completa, dado
que `record_failed_payment()` y `_transition_active_to_past_due()` son paths
independientes. La función helper `send_admin_payment_failure_recurrent_email()`
es idempotente por diseño (fire-and-forget, no hace upsert).

---

## 9. Guard Anti-Duplicado Recomendado

No se necesita un guard en DB para el email admin, por las mismas razones que
los demás emails en este sistema: la deduplicación ya ocurre aguas arriba
(WebhookDelivery o el `if updated:` de la tarea).

Sin embargo, el helper **sí debe**:
1. No lanzar excepciones (fire-and-forget con `try/except` + `logger.exception`).
2. Verificar que puede resolver un destinatario admin (fallar silenciosamente si
   no hay `ADMIN_BILLING_EMAIL` configurado).
3. Pasar `metadata` con `subscription_id` + `business_id` + `retry_count` para
   que `EmailDelivery` sea consultable sin duplicar lógica.

---

## 10. Especificación del Email `admin_payment_failure_recurrent`

### 10.1 Tipo y Destinatario

| Atributo | Valor |
|---|---|
| Tipo | **ADMIN interno** (usa `queue_admin_transactional_email`) |
| `recipient_category` | `"billing"` |
| Subject | `"⚠️ Pago fallido — {business_name} (intento #{retry_count})"` |
| `template_key` | `"admin_payment_failure_recurrent"` |

### 10.2 Context del Template

| Variable | Fuente | Descripción |
|---|---|---|
| `business_name` | `subscription.business.name` | Nombre del negocio |
| `business_id` | `subscription.business.pk` | ID interno |
| `plan_code` | `subscription.plan_code` | Código del plan |
| `service_type` | `subscription.service_type` | Tipo de servicio |
| `retry_count` | `subscription.retry_count` | Nro de intento fallido |
| `amount` | `invoice_event.amount` | Monto intentado cobrar |
| `currency` | `invoice_event.currency` | Moneda (ARS) |
| `failure_reason` | `reason` arg | Razón del fallo (si aplica) |
| `grace_until` | `subscription.grace_until` | Deadline antes de suspend |
| `current_period_end` | `subscription.current_period_end` | Fin del período |
| `provider_status` | `invoice_event.provider_status` | Status MP |
| `admin_url` | `_build_admin_subscription_url(subscription.pk)` | Link al admin |
| `owner_email` | owner resuelto vía `get_owner_user()` | Email del dueño del negocio |

### 10.3 Metadata Recomendada

```python
metadata = {
    "event_type": "admin_payment_failure_recurrent",
    "subscription_id": str(subscription.pk),
    "related_business_id": str(subscription.business_id),
    "plan_code": subscription.plan_code or "",
    "service_type": subscription.service_type or "",
    "retry_count": subscription.retry_count,
    "amount": str(invoice_event.amount),
    "currency": invoice_event.currency or "ARS",
    "provider_status": invoice_event.provider_status or "",
    "invoice_event_id": str(invoice_event.pk),
}
```

### 10.4 Template HTML — Secciones Esperadas

- **Badge interno** (rojo/naranja): "Email Interno — Equipo Billing"
- **Encabezado**: "⚠️ Pago fallido recurrente"
- **Tabla de datos**: Negocio, Plan, Intento #N, Monto, Razón, Período, Grace Until
- **Indicador de urgencia** (condicional en template):
  - `retry_count == 1` → aviso
  - `retry_count == 2` → atención
  - `retry_count >= 3` → crítico
- **Link CTA**: "Ver suscripción en admin" → `admin_url`
- **Footer**: "Email interno — no responder"

---

## 11. Tests Mínimos para PR-ADMIN-08

Archivo sugerido: `apps/billing/tests/test_pr_admin_08_payment_failure_email.py`

### Clase 1 — `SendAdminPaymentFailureEmailTests` (helper directo)

| # | Test | Descripción |
|---|---|---|
| 01 | `test_uses_template_key` | `template_key="admin_payment_failure_recurrent"` |
| 02 | `test_uses_recipient_category_billing` | `recipient_category="billing"` |
| 03 | `test_associates_related_business` | `related_business=subscription.business` |
| 04 | `test_context_business_name` | `context["business_name"]` |
| 05 | `test_context_retry_count` | `context["retry_count"]` |
| 06 | `test_context_amount` | `context["amount"]` == invoice_event.amount |
| 07 | `test_context_admin_url` | `context["admin_url"]` contiene `subscription.pk` |
| 08 | `test_metadata_event_type` | `metadata["event_type"] == "admin_payment_failure_recurrent"` |
| 09 | `test_metadata_subscription_id` | `metadata["subscription_id"]` |
| 10 | `test_metadata_retry_count` | `metadata["retry_count"]` |
| 11 | `test_metadata_invoice_event_id` | `metadata["invoice_event_id"]` |
| 12 | `test_no_send_mail` | Patch `send_mail` → assert never called |
| 13 | `test_queue_failure_returns_false` | Helper devuelve False sin propagar |

### Clase 2 — Integración con `record_failed_payment()`

| # | Test | Descripción |
|---|---|---|
| 14 | `test_record_failed_payment_calls_admin_email` | Sub ACTIVE → se llama admin helper |
| 15 | `test_record_failed_payment_not_active_no_admin_email` | Sub no ACTIVE → no se llama |

### Clase 3 — Integración con `_transition_active_to_past_due()`

| # | Test | Descripción |
|---|---|---|
| 16 | `test_task_calls_admin_email_on_transition` | updated==1 → admin email llamado |
| 17 | `test_task_no_admin_email_when_no_update` | updated==0 → no llamado |

### Clase 4 — Template rendering

| # | Test | Descripción |
|---|---|---|
| 18 | `test_template_renders_without_error` | Contexto completo → sin excepciones |
| 19 | `test_template_renders_without_optional_fields` | grace_until=None, reason="" → OK |
| 20 | `test_no_emailmessage` | No usa `django.core.mail.EmailMessage` directamente |

**Total mínimo**: 20 tests.

---

## 12. Validaciones Ejecutadas

> Esta auditoría es **read-only**. No se modificó ningún archivo de código,
> template, modelo, migración ni test.

Greps ejecutados durante el audit:

```bash
# Confirma que record_failed_payment no está llamado desde webhook_processor
grep -R "record_failed_payment" services/api/src/apps/billing/webhook_processor.py
# → 0 matches (confirmado)

# Confirma que admin_payment_failure_recurrent no existe aún
grep -R "admin_payment_failure" services/api/src/apps/billing/
# → 0 matches (implementación parte de cero)

# Confirma campo retry_count disponible
grep -R "retry_count" services/api/src/apps/billing/models.py
# → 1 match: SmallIntegerField(default=0), incrementado en record_failed_payment

# Confirma que send_payment_failed_email se llama en tasks.py también
grep -R "send_payment_failed_email" services/api/src/apps/billing/tasks.py
# → match en _transition_active_to_past_due (línea ~170)
```

Estado del sistema confirmado: `manage.py check` sin errores (verificado en
sesión anterior tras PR-ADMIN-07).

---

## 13. Riesgos Pendientes

| Riesgo | Severidad | Mitigación |
|---|---|---|
| `record_failed_payment()` no está integrado en webhook_processor | 🔴 Alta | El flujo de "pago rechazado por MP" no llama esta función hoy. Evaluar si el webhook de MP notifica pagos rechazados como `subscription_authorized_payment` con `status != 'authorized'` |
| Doble disparo si se integra en ambas rutas (task + record_failed_payment) | 🟡 Media | Ambas rutas son mutuamente excluyentes en el estado actual (una va por webhook, otra por time-based expiry) — verificar con datos reales |
| `grace_until` puede ser null si el webhook fijó la renovación sin setear ese campo | 🟡 Media | Usar `getattr(subscription, 'grace_until', None)` y tratar como opcional en template |
| `ADMIN_BILLING_EMAIL` no configurado en algunos entornos | 🟡 Media | El helper debe fallar silenciosamente si no hay destinatarios admin configurados |
| `retry_count` no se incrementa en la ruta de la tarea Celery | 🟡 Media | `_transition_active_to_past_due()` no llama `record_failed_payment()` — `retry_count` permanece en 0 para pagos expirados por tiempo. La integración futura debería unificar |
| `BillingInvoiceEvent` no siempre disponible en la ruta de tasks.py | 🟠 Media-alta | La tarea no tiene un `invoice_event` asociado — el helper admin deberá soportar `invoice_event=None` o buscar el último evento de la suscripción |

---

## 14. Decisión de Diseño — Implicancias para PR-ADMIN-08

Dado que existen **dos rutas** para llegar al estado `PAST_DUE` y que
`record_failed_payment()` no está actualmente integrado en el webhook de MP:

1. **Integrar en `_transition_active_to_past_due()` (tasks.py)** — cobertura
   inmediata de la ruta de producción real; `invoice_event` no está disponible
   así que el helper recibe `invoice_event=None` y extrae datos del
   `subscription`.

2. **Integrar en `record_failed_payment()` (subscription_activator.py)** —
   cobertura del path explícito (futuro uso cuando MP notifique rechazos);
   `invoice_event` sí está disponible.

3. **Firma recomendada del helper**:
   ```python
   def send_admin_payment_failure_recurrent_email(
       subscription,
       invoice_event=None,   # optional: may not exist in task-based path
       *,
       reason: str | None = None,
   ) -> bool:
   ```

---

*Auditoría completada. Cero archivos de código modificados.  
Próximo paso: PR-ADMIN-08 implementación basada en este informe.*
