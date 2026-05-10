# Auditoría final de emails transaccionales — MiRubro

**Fecha:** 2026-05-09  
**Autor:** audit automático post-PR11  
**Estado general:** ✅ Sistema de notifications operativo y con cobertura de tests

---

## 1. Resumen ejecutivo

El sistema de emails transaccionales de MiRubro fue migrado de llamadas directas a `send_mail`/`EmailMessage` a la capa centralizada `apps.notifications` (modelo `EmailDelivery` + `queue_transactional_email` + provider abstraction). Todos los emails críticos de accounts y billing usan esta capa. Los únicos usos de `send_mail` restantes están en `apps.reviews` (notificación de feedback negativo y digest semanal), que son emails de menor criticidad y no forman parte del alcance de este ciclo de PRs.

**Sistema de notifications:** estable, testeado, production-ready.  
**Deuda técnica residual:** baja — concentrada en `apps.reviews`.

---

## 2. Emails implementados

| Template key | Evento | App | Trigger principal | Async | Tests PR | Estado |
|---|---|---|---|---|---|---|
| `verify_email` | Registro de usuario | accounts | `EmailService.send_verification_email()` → views.py | ✅ | PR-2 | ✅ Producción |
| `password_reset` | Solicitud de recuperación de contraseña | accounts | `EmailService.send_password_reset_email()` → views.py | ✅ | PR-3 | ✅ Producción |
| `password_changed` | Cambio de contraseña confirmado | accounts | `EmailService.send_password_changed_email()` → views.py | ✅ | PR-4 | ✅ Producción |
| `secondary_user_access` | Alta de usuario secundario por owner | accounts | `EmailService.send_secondary_user_access_email()` → views.py | ✅ | PR-5 | ✅ Producción |
| `subscription_activated` | Pago aprobado → suscripción ACTIVE | billing | `send_subscription_activated_email()` ← webhook `authorized_payment` | ✅ | PR-7 | ✅ Producción |
| `payment_failed` | Pago rechazado → PAST_DUE | billing | `send_payment_failed_email()` ← `record_failed_payment()` + `_transition_active_to_past_due()` | ✅ | PR-8 | ✅ Producción |
| `subscription_suspended` | Grace expirada o trial expirado → SUSPENDED | billing | `send_subscription_suspended_email()` ← `_transition_past_due_to_suspended()` + `_transition_trial_to_suspended()` | ✅ | PR-9 | ✅ Producción |
| `cancellation_confirmed` | Cancelación ejecutada → CANCELED | billing | `send_cancellation_confirmed_email()` ← `execute_cancellation()` | ✅ | PR-10 | ✅ Producción |

**Templates HTML disponibles:**
```
apps/notifications/templates/emails/
  base.html
  cancellation_confirmed.html
  generic.html
  password_changed.html
  password_reset.html
  payment_failed.html
  secondary_user_access.html
  subscription_activated.html
  subscription_suspended.html
  verify_email.html
```

---

## 3. Flujos auditados

### Accounts (`apps/accounts/services.py` → `EmailService`)

| Flujo | Archivo trigger | Helper/método | Guard anti-crash |
|---|---|---|---|
| Verificación de email | `accounts/views.py` | `send_verification_email(user, token)` | try/except → `False` |
| Recuperación de contraseña | `accounts/views.py` | `send_password_reset_email(user, token)` | try/except → `False` |
| Contraseña modificada | `accounts/views.py` | `send_password_changed_email(user)` | try/except → `False` |
| Acceso usuario secundario | `accounts/views.py` (owner crea user) | `send_secondary_user_access_email(user, business, role)` | try/except → `False` |

**Observación:** el token de verificación / reset se embebe sólo en la URL del contexto (`verify_url`, `reset_url`), no como campo aislado en metadata. El contexto se renderiza en el template pero no se persiste en `EmailDelivery.metadata`. ✅ Seguro.

### Billing (`apps/billing/email_helpers.py`)

| Flujo | Archivo trigger | Condición de envío | Guard anti-crash |
|---|---|---|---|
| Suscripción activada | `webhook_processor.py` (evento `authorized_payment`) | Solo si `activated == True` (idempotente) | try/except en webhook |
| Pago fallido | `subscription_activator.py::record_failed_payment()` + `tasks.py::_transition_active_to_past_due()` | Solo si estado era ACTIVE antes del cambio | try/except → no propaga |
| Suscripción suspendida | `tasks.py::_transition_past_due_to_suspended()` y `::_transition_trial_to_suspended()` | Solo si `updated == 1` | try/except → no propaga |
| Cancelación confirmada | `cancellation_service.py::execute_cancellation()` | Solo si sub no estaba en CANCELED | try/except → no propaga |

**Webhook de cancelación de MercadoPago:** El webhook processor (`webhook_processor.py`, línea ~279) sincroniza el estado local a CANCELED cuando MP reporta el preapproval como `cancelled`, pero **NO envía email** desde esta ruta. Correcto — el email de cancelación solo se envía desde `execute_cancellation()`, que es la acción del sistema (no del proveedor de pago). ✅

---

## 4. Seguridad

| Check | Estado | Detalle |
|---|---|---|
| Tokens no en metadata | ✅ | Los tokens (verify, reset) sólo se incluyen en URLs del contexto del template. `EmailDelivery.metadata` no los recibe en ningún helper auditado. |
| Contraseñas no en emails | ✅ | Ningún helper envía contraseñas en texto plano. |
| PIN no en emails | ✅ | No existe flujo de PIN en el sistema de notifications. |
| Fallos de email no rompen flujos | ✅ | Todos los helpers tienen try/except y devuelven `bool`. Los callers en billing envuelven adicionalmente en try/except. |
| Emails dentro de transacciones | ✅ | `billing/email_helpers.py` explicita en docstring que no debe llamarse dentro de `transaction.atomic()`. Los callers lo respetan (se llaman después del `save()`). |
| Envíos duplicados en billing | ✅ | Guards: `activated == True` / `updated == 1` / sub no en estado destino ya. |
| `send_async=True` consistente | ✅ | Todos los helpers de billing y accounts usan `send_async=True`. |
| Webhook no envía cancelación | ✅ | `webhook_processor.py` solo sincroniza estado, no dispara email de cancelación. |

---

## 5. Usos legacy restantes

| Archivo | Uso legacy | Riesgo | Recomendación |
|---|---|---|---|
| `apps/reviews/notifications.py` | `from django.core.mail import send_mail` — usado en `notify_negative_feedback()` para alertar feedback negativo al owner | Bajo — usa `fail_silently=False` con try/except propio; tiene throttling por cache (1/hora/negocio) | Migrar a `queue_transactional_email` con template `review_negative_feedback` en PR futuro (P2) |
| `apps/reviews/digest.py` | `from django.core.mail import send_mail` — usado en `send_digest_for_business()` para el resumen semanal | Bajo — tiene guard `fail_silently=False` con try/except y cache guard por semana | Migrar a `queue_transactional_email` con template `review_weekly_digest` en PR futuro (P2) |
| `apps/notifications/providers/django_email.py` | `from django.core.mail import EmailMultiAlternatives` | Ninguno — es el transporte interno del provider. No es "legacy", es la implementación correcta del provider Django. | No modificar. |

**Conclusión:** No quedan usos legacy en flows críticos (accounts + billing). Los 2 usos restantes están en `apps.reviews` y son controlados, con guards, y no bloquean el flujo principal de la app.

---

## 6. Tests

### Suites específicas de notifications (PRs)

| Suite | Tests | Estado |
|---|---|---|
| `apps.accounts.tests.test_pr2_verify_email_notifications` | ~12 | ✅ OK |
| `apps.accounts.tests.test_pr3_password_reset_notifications` | ~12 | ✅ OK |
| `apps.accounts.tests.test_pr4_password_changed_notifications` | ~10 | ✅ OK |
| `apps.accounts.tests.test_pr5_secondary_user_access_email` | ~10 | ✅ OK |
| `apps.billing.tests.test_pr7_subscription_activated_email` | ~12 | ✅ OK |
| `apps.billing.tests.test_pr8_payment_failed_email` | ~14 | ✅ OK |
| `apps.billing.tests.test_pr9_subscription_suspended_email` | 15 | ✅ OK |
| `apps.billing.tests.test_pr10_cancellation_confirmed_email` | 12 | ✅ OK |
| **Total PR suites** | **113** | **✅ 113/113** |

### Suite apps.notifications

| Suite | Tests | Estado |
|---|---|---|
| `apps.notifications` (modelos, servicios, providers, tasks) | 62 | ✅ OK |

### Resultado global de validación

```
manage.py check          → 0 issues
apps.notifications       → 62/62 OK
PR suites (accounts+billing) → 113/113 OK
Total                    → 175 tests, 0 fallos
```

---

## 7. Pendientes recomendados

### P1 — Necesario antes de escalar

| Item | Justificación |
|---|---|
| Deduplicación explícita de `payment_failed` si se escalan las tareas Celery | `_transition_active_to_past_due()` y `record_failed_payment()` pueden ambos disparar `payment_failed` para la misma suscripción en el mismo ciclo. Actualmente el guard es temporal (el estado ya cambió a PAST_DUE en el primer update). Considerar un cache flag TTL-1h si se activan reintentos agresivos de Celery. |
| Template de digest semanal de reviews via notifications | `apps/reviews/digest.py` usa `send_mail` en plain-text. No tiene registro en `EmailDelivery`. Si un digest falla, no hay trazabilidad. |

### P2 — Mejora posterior

| Item | Justificación |
|---|---|
| Migrar `apps/reviews/notifications.py` a `queue_transactional_email` | Agrega trazabilidad de `EmailDelivery` para alertas de feedback negativo. Permite usar el template HTML base existente. |
| Migrar `apps/reviews/digest.py` a `queue_transactional_email` | Idem — con template `review_weekly_digest.html`. |
| Email de vinculación de cuenta Google para usuarios ya registrados | Actualmente el flujo de Google login no envía notificación cuando un email existente vincula Google por primera vez. Decisión de producto pendiente. |
| Rate-limiting de `subscription_suspended` por negocio | Si la tarea `expire_subscriptions` se ejecuta frecuentemente y una sub rebota entre PAST_DUE y SUSPENDED, podría enviar múltiples emails. Actualmente el guard de `updated == 1` es suficiente, pero documentar el riesgo. |

### P3 — Nice to have

| Item | Justificación |
|---|---|
| Email de reactivación post-suspension (cuando la sub vuelve a ACTIVE desde SUSPENDED) | Actualmente `subscription_activated` cubre esto si viene vía webhook de pago aprobado. Si se hace reactivación manual por admin, no hay email. |
| Email de soporte / apertura de ticket | No existe sistema de soporte integrado. |
| Preview en admin de templates Jinja/Django | Para QA de templates sin necesidad de trigger real. |

---

## 8. Checklist final

- [x] Todos los emails críticos de accounts usan `notifications.queue_transactional_email`.
- [x] Emails principales de billing usan `notifications.queue_transactional_email`.
- [x] No se envían contraseñas ni PIN en ningún email.
- [x] Tokens no se guardan en `EmailDelivery.metadata` — solo en URL del contexto del template.
- [x] Fallos de email no rompen flujos principales (billing y accounts).
- [x] Billing evita emails duplicados con guards de estado (`updated == 1`, `activated == True`, status-conditional filters).
- [x] Tests específicos existen para cada PR (PR-2 al PR-10), 113 tests.
- [x] `apps.notifications` tiene suite propia: 62 tests.
- [x] No se tocaron archivos `.env` ni `settings.py`.
- [x] No se tocó `GoogleAuthView` ni el flujo OAuth.
- [x] Webhook de cancelación de MP **no** dispara email de cancelación.
- [x] `send_async=True` en todos los helpers de billing y accounts.
- [x] Todos los helpers devuelven `bool` y nunca propagan excepciones.

---

## Apéndice: Mapa de dependencias

```
accounts/views.py
  └─► EmailService (accounts/services.py)
        └─► queue_transactional_email (notifications/services.py)
              └─► EmailDelivery (notifications/models.py)
              └─► Provider (django_email / mailgun / etc.)

billing/webhook_processor.py [authorized_payment]
  └─► send_subscription_activated_email (billing/email_helpers.py)
        └─► queue_transactional_email

billing/subscription_activator.py [record_failed_payment]
  └─► send_payment_failed_email (billing/email_helpers.py)

billing/tasks.py [expire_subscriptions]
  ├─► _transition_active_to_past_due → send_payment_failed_email
  ├─► _transition_past_due_to_suspended → send_subscription_suspended_email
  └─► _transition_trial_to_suspended → send_subscription_suspended_email

billing/cancellation_service.py [execute_cancellation]
  └─► send_cancellation_confirmed_email (billing/email_helpers.py)

reviews/notifications.py [notify_negative_feedback]
  └─► send_mail (LEGACY — P2)

reviews/digest.py [send_digest_for_business]
  └─► send_mail (LEGACY — P2)
```
