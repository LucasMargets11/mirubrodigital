# Auditoría de Emails Transaccionales — MiRubro

**Fecha de auditoría:** 2026-05-09  
**Auditor:** GitHub Copilot (Senior Technical Auditor role)  
**Alcance:** `services/api/src/` — backend Django/DRF completo  
**Estado:** Solo auditoría — ningún código modificado, ninguna migración creada  

---

## 1. Resumen ejecutivo

### Cantidades detectadas

| Métrica | Valor |
|---|---|
| Puntos de envío real (`send_mail`) | **4** (5 triggers documentados — ver nota) |
| Apps con lógica de email | **2** (`accounts`, `reviews`) |
| Emails críticos (P0) | **2** (verificación de email, reset de contraseña) |
| Emails P1 importantes | **0** (billing/pagos: no envía emails actualmente) |
| Emails P2 secundarios | **2** (notificación de reseña negativa, digest semanal) |
| Tasks Celery que gestionan email | **2** (`send_verification_email`, `send_weekly_digest`) |
| Templates HTML existentes | **0** — todos son texto plano inline |

> **Nota sobre conteo:** Se detectan **4 flujos lógicos** de envío y **5 triggers documentados**, porque la verificación de email puede dispararse desde el registro inicial y desde el reenvío de verificación. Ambos usan el mismo método `EmailService.send_verification_email` vía el mismo Celery task, pero desde dos vistas distintas.

### Apps involucradas

- **`apps.accounts`**: 2 emails críticos de seguridad y autenticación.
- **`apps.reviews`**: 2 emails informativos / operativos para el dueño del negocio.
- **`apps.billing`**: ningún email directo actualmente (gap importante a cubrir).
- **`apps.accounts.support_ticket`**: modelo existe, pero sin envío de email.

### Emails críticos (P0)

1. `EmailService.send_verification_email` — verificación de cuenta en registro.
2. `EmailService.send_password_reset_email` — recuperación de contraseña.

### Riesgos principales

1. **`send_password_reset_email` es síncrono dentro del request HTTP** — sin Celery. Puede bloquear la respuesta si el proveedor de email falla o está lento (aunque el error se traga con `logger.exception`).
2. **Deuda legacy en `settings.py`**: el default hardcoded de `EMAIL_HOST` apunta a `smtp.sendgrid.net` y `DEFAULT_FROM_EMAIL` apunta a `no-reply@mirubro.com`. El proveedor real (boto3/SESv2 con IAM Role) ya funciona en producción, pero los defaults del código son inconsistentes con esa arquitectura.
3. **Cero templates HTML** — todos los emails usan texto plano con f-strings. No son mantenibles a largo plazo ni aportan branding.
4. **Sin modelo de trazabilidad** — no existe `EmailDelivery` ni equivalente. No hay forma de auditar qué emails se enviaron, cuándo y si llegaron.
5. **Billing sin emails** — suscripciones activas, pagos fallidos, periodos de gracia (PAST_DUE) y suspensiones no generan ningún email al tenant.
6. **Sandbox SES activo** — mientras SES esté en sandbox, solo se pueden enviar emails a `mirubrodigital@gmail.com` u otros destinatarios verificados.

### Recomendación general

La migración a `apps.notifications` debe realizarse en 3 fases bien delimitadas:

1. **Fase 1 (P0)**: migrar los 2 emails críticos de `accounts` con templates HTML y Celery, reemplazando `EmailService`.
2. **Fase 2 (P1)**: implementar emails de billing (pago exitoso, falla de pago, suspensión).
3. **Fase 3 (P2)**: migrar reviews y digest a templates HTML unificados.

---

## 2. Configuración actual de email

Extraído de `services/api/src/config/settings.py` (líneas 325–342):

```python
# In development: EMAIL_BACKEND defaults to console so no SMTP is needed.
# In production: set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# and populate the EMAIL_HOST_* vars.
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST        = os.getenv('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT        = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS     = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER   = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Mirubro <no-reply@mirubro.com>')

EMAIL_VERIFICATION_TOKEN_HOURS = int(os.getenv('EMAIL_VERIFICATION_TOKEN_HOURS', '48'))
PASSWORD_RESET_TOKEN_HOURS = int(os.getenv('PASSWORD_RESET_TOKEN_HOURS', '2'))
```

### Análisis de la configuración en `settings.py` (defaults hardcoded)

La siguiente tabla refleja el estado del archivo `settings.py` — no las variables de `.env` de producción:

| Variable | Valor actual (default hardcoded) | Estado | Nota |
|---|---|---|---|
| `EMAIL_BACKEND` | `console.EmailBackend` | ⚠️ Correcto en dev | La futura `AmazonSESProvider` llamará directamente a boto3 sin pasar por `EMAIL_BACKEND`; útil como fallback local |
| `EMAIL_HOST` | `smtp.sendgrid.net` | ❌ Deuda legacy | Default confuso que apunta a SendGrid. El proveedor destino (boto3/SESv2) **no usa SMTP**, pero el default inerte puede inducir a error |
| `EMAIL_HOST_USER` | `''` | — N/A para boto3 | El proveedor SESv2 vía IAM Role no requiere credenciales SMTP |
| `EMAIL_HOST_PASSWORD` | `''` | — N/A para boto3 | El proveedor SESv2 vía IAM Role no requiere credenciales SMTP |
| `DEFAULT_FROM_EMAIL` | `'Mirubro <no-reply@mirubro.com>'` | ❌ Default desactualizado en `settings.py` | Ya corregido en `services/api/.env` como `MiRubro <notificaciones@mirubro.com>` |
| `EMAIL_VERIFICATION_TOKEN_HOURS` | `48` | ✅ Razonable | — |
| `PASSWORD_RESET_TOKEN_HOURS` | `2` | ✅ Correcto | — |

### Variables de email ya configuradas en `services/api/.env`

Las siguientes variables **ya existen en el entorno de producción** y han sido verificadas (desde EC2 host con `aws sesv2 send-email` y desde el contenedor Django con boto3):

| Variable | Valor confirmado | Estado |
|---|---|---|
| `EMAIL_PROVIDER` | `amazon_ses` | ✅ Confirmado en `.env` |
| `AWS_SES_REGION` | `sa-east-1` | ✅ Confirmado en `.env` |
| `AWS_SES_CONFIGURATION_SET` | `mirubro-transactional` | ✅ Confirmado en `.env` |
| `DEFAULT_FROM_EMAIL` | `"MiRubro <notificaciones@mirubro.com>"` | ✅ Confirmado en `.env` |
| `SERVER_EMAIL` | `"MiRubro <notificaciones@mirubro.com>"` | ✅ Confirmado en `.env` |
| `SUPPORT_EMAIL` | `mirubrodigital@gmail.com` | ✅ Confirmado en `.env` |
| `BILLING_EMAIL` | `mirubrodigital@gmail.com` | ✅ Confirmado en `.env` |
| `EMAIL_TRANSACTIONAL_ENABLED` | `true` | ✅ Confirmado en `.env` |
| `EMAIL_MARKETING_ENABLED` | `false` | ✅ Confirmado en `.env` |

**Pendiente de formalizar en `settings.py`**: estas variables existen en `.env` y funcionan en producción, pero `settings.py` todavía no las expone como Django settings formales (e.g. `AWS_SES_REGION = os.getenv('AWS_SES_REGION', 'sa-east-1')`). La futura app `notifications` necesitará acceder a ellas vía `settings.*`.

### Inconsistencias detectadas

1. **`EMAIL_HOST` default = SendGrid** — aunque en producción se sobreescriba vía `.env`, el default en el código apunta a SendGrid. El proveedor destino (boto3/SESv2) **no depende de `EMAIL_HOST`**, pero el default es inerte y confuso; debe eliminarse o actualizarse para evitar errores si alguien intenta configurar un fallback SMTP.
2. **`DEFAULT_FROM_EMAIL` default = `no-reply@mirubro.com`** — el valor correcto ya está en `.env` como `MiRubro <notificaciones@mirubro.com>`. El default hardcoded en `settings.py` es inconsistente y debe corregirse en una tarea de deuda técnica.
3. **`EMAIL_MARKETING_ENABLED` / `EMAIL_TRANSACTIONAL_ENABLED`** — ya existen en `services/api/.env` y están confirmadas en el contenedor, pero todavía no están expuestas en `settings.py` como variables Django formales.
4. **`AWS_SES_REGION` / `AWS_SES_CONFIGURATION_SET`** — ya existen en `services/api/.env` y fueron confirmadas en el contenedor. Pendiente exponerlas en `settings.py` formalmente (`os.getenv(...)`) para que la futura app `notifications` pueda usarlas vía `settings.*`.
5. **`SERVER_EMAIL`** — ya existe en `.env` como `MiRubro <notificaciones@mirubro.com>`, pero `settings.py` todavía no lo lee explícitamente.

---

## 3. Inventario completo de envíos actuales

| App | Archivo | Función/método | Trigger | Tipo | Sync/Async | API usada | Destinatario | Template | Tenant/Business | User | Riesgo | Prioridad | Observaciones |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| accounts | `services.py` | `EmailService.send_verification_email` | `RegisterView.post` (via Celery `on_commit`) | Autenticación | **Async** (Celery) | `django.core.mail.send_mail` | `user.email` | Texto plano inline | No (usuario nuevo, no tiene business aún) | Sí | Medio | **P0** | Disparado por `send_verification_email_task.delay()` después de commit. Bien diseñado. |
| accounts | `services.py` | `EmailService.send_verification_email` | `ResendVerificationView.post` (directo `.delay()`) | Autenticación | **Async** (Celery) | `django.core.mail.send_mail` | `user.email` | Texto plano inline | No | Sí | Medio | **P0** | Mismo email, segunda vía de disparo. |
| accounts | `services.py` | `EmailService.send_password_reset_email` | `ForgotPasswordView.post` (síncrono en request) | Seguridad | **Síncrono** | `django.core.mail.send_mail` | `user.email` | Texto plano inline | No (memberships buscados best-effort) | Sí | **Alto** | **P0** | Síncrono dentro del request. Si falla el proveedor de email o `send_mail`, el error se traga pero el bloqueo afecta latencia. Sin Celery. |
| reviews | `notifications.py` | `notify_negative_feedback` | Señal/call cuando se recibe reseña negativa | Reviews | **Síncrono** | `django.core.mail.send_mail` | `owner.email` del primer owner activo | Texto plano inline | Sí (`review.business`) | No (lookup de owner) | Medio | **P2** | Anti-spam: 1 email/hora por business (cache). Sin Celery. |
| reviews | `digest.py` → `tasks.py` | `send_digest_for_business` / `run_weekly_digest` | Celery Beat: lunes 12:00 UTC | Digest | **Async** (Celery Beat) | `django.core.mail.send_mail` | `owner.email` del primer owner activo | Texto plano inline | Sí (`business`) | No | Bajo | **P2** | Bien diseñado: idempotente (cache por semana), skip si 0 actividad. |

---

## 4. Detalle por app

### 4.1 App: `accounts`

#### ¿Qué hace hoy?

La app `accounts` tiene una clase `EmailService` en `services.py` con dos métodos estáticos:

1. **`send_verification_email(user, token)`**
   - Construye una URL `{FRONTEND_URL}/verificar-email?token={token}`
   - Envía texto plano con el enlace de verificación
   - Subject: `"Verificá tu email en Mirubro"`
   - From: `settings.DEFAULT_FROM_EMAIL`
   - Destinatario: `user.email`
   - Los errores se loggean pero no se propagan (`return False` en exception)

2. **`send_password_reset_email(user, token)`**
   - Construye una URL `{FRONTEND_URL}/nueva-contrasena?token={token}`
   - Envía texto plano con el enlace de reset
   - Subject: `"Recuperá tu contraseña en Mirubro"`
   - From: `settings.DEFAULT_FROM_EMAIL`
   - Destinatario: `user.email`
   - Los errores se loggean pero no se propagan

#### ¿Cómo se dispara?

| Email | Vista | Mecanismo |
|---|---|---|
| Verificación (nuevo registro) | `RegisterView.post` | `transaction.on_commit(lambda: send_verification_email_task.delay(user.id, token))` |
| Re-verificación | `ResendVerificationView.post` | `send_verification_email_task.delay(user.id, token)` directamente |
| Password reset | `ForgotPasswordView.post` | `EmailService.send_password_reset_email(user, token)` — **síncrono** |

#### Arquitectura de tareas Celery

`accounts/tasks.py` define:
- `send_verification_email_task` → llama a `EmailService.send_verification_email`
- No tiene `max_retries` ni `default_retry_delay` — la tarea no reintenta en fallo

#### Datos que usa

- `user.email` como destinatario
- `settings.FRONTEND_URL` para construir el link
- `settings.EMAIL_VERIFICATION_TOKEN_HOURS` y `PASSWORD_RESET_TOKEN_HOURS` para el mensaje
- Los tokens son generados por `AccountProfile.generate_verification_token()` y `generate_password_reset_token()` — se almacena el hash SHA-256, se envía el token en plaintext

#### Problemas detectados

1. **`send_password_reset_email` es síncrono en request** — es el único de los 2 que no usa Celery. Debe migrarse a async (Celery task) antes de la migración a `notifications`.
2. **Sin reintentos automáticos** — `send_verification_email_task` no tiene `max_retries`. Si el worker Celery falla durante el envío, el email se pierde silenciosamente.
3. **Sin template HTML** — solo texto plano. No hay branding, no hay botones de acción, no es responsive.
4. **Sin model de trazabilidad** — si el usuario no recibe el email y llama a soporte, no hay forma de saber si el email fue intentado y cuándo.
5. **FROM email inconsistente** — el default es `Mirubro <no-reply@mirubro.com>` pero el dominio canónico definido para SES es `notificaciones@mirubro.com`.
6. **No hay `password_changed` email** — `ChangePasswordView` y `ForceChangePasswordView` cambian la contraseña exitosamente pero no envían confirmación. Es una buena práctica de seguridad notificar al usuario.

#### Cómo conviene migrarlo

```
accounts.EmailService → notifications.services.send_transactional_email(
    template='verify_email',  # o 'password_reset'
    context={...},
    recipient=user.email,
)
```
Mantener `EmailService` como wrapper durante la transición (alias → notifications).

---

### 4.2 App: `reviews`

#### ¿Qué hace hoy?

La app `reviews` tiene dos módulos de email:

1. **`notifications.py` — `notify_negative_feedback(review)`**
   - Alerta en tiempo real cuando llega un review negativo (por rating < threshold)
   - Anti-spam: cache key `review_notif:{business_id}` con TTL de 3600 segundos (1 email/hora/business)
   - Busca el primer `Membership` activo con `role='owner'` para obtener el email
   - Subject: `"Nuevo feedback en {business.name} — {review.rating}★"`
   - Cuerpo incluye: estrellas, comentario (si existe), contact_info (si existe), link al panel
   - Síncrono — se llama desde el flujo de recepción de reseña

2. **`digest.py` → `tasks.py` — `send_weekly_digest()` / `run_weekly_digest()`**
   - Digest semanal con métricas de la semana (reseñas, promedio, negativos, visitas QR)
   - Guard: solo para businesses con `qr_reviews` subscription activa + `smart_filter_allowed`
   - Guard de idempotencia: cache key `review_digest:{business_id}:{year}W{week}` — 1 envío/semana
   - Programado via Celery Beat: lunes 12:00 UTC (09:00 ART)
   - Skip si `new_reviews == 0 AND visits == 0`
   - Subject: `"Resumen semanal — {business.name}"`

#### ¿Cómo se dispara?

- `notify_negative_feedback`: llamado desde señales o el flujo de publicación de reseñas (no auditado directamente, pero inferido del diseño)
- `send_weekly_digest`: Celery Beat task `reviews.send_weekly_digest` (lunes 12:00 UTC)

#### Datos que usa

- `review.business`, `review.rating`, `review.comment`, `review.contact_info`
- `business.review_config.redirect_threshold` (default: 4)
- `Review.objects`, `ReviewVisit.objects`, `ReviewConfig`
- `settings.FRONTEND_URL` para los links del panel

#### Problemas detectados

1. **`notify_negative_feedback` es síncrono** — se llama directamente desde el flujo de recepción. Si el proveedor de email tarda (llamada boto3/SESv2), puede ralentizar el proceso de recepción de reseñas.
2. **Solo se notifica al primer owner activo** — si el negocio tiene múltiples owners, solo uno recibe el email. No hay configuración de preferencias por tenant.
3. **Sin template HTML** — texto plano. No aprovecha el branding ni convierte visualmente.
4. **La función `_get_owner_email` está duplicada** — existe en `notifications.py` y en `digest.py` con código idéntico. Candidata a extraer en un helper compartido.
5. **FROM email inconsistente** — misma inconsistencia que en `accounts`: usa `settings.DEFAULT_FROM_EMAIL` que por default es `no-reply@mirubro.com`.

#### Cómo conviene migrarlo

```python
# notifications.py
→ notifications.services.send_transactional_email(
    template='negative_feedback_alert',
    context={...},
    recipient=owner_email,
    business=review.business,
)

# digest.py
→ notifications.tasks.send_digest_email_task.delay(
    business_id=business.id,
    stats=stats,
)
```

---

### 4.3 App: `billing`

#### ¿Qué hace hoy?

**Ningún email transaccional**. La app `billing` gestiona suscripciones, pagos vía MercadoPago, webhooks y el ciclo de vida `ACTIVE → PAST_DUE → SUSPENDED`, pero **no envía ningún email al tenant** en ninguno de estos eventos.

Los modelos y flujos existentes sin email:

| Evento | Dónde ocurre | Email hoy |
|---|---|---|
| Suscripción activada (pago exitoso) | `webhook_processor.py` / `subscription_activator.py` | ❌ Ninguno |
| Pago fallido / PAST_DUE | `tasks.py` → `billing.expire_subscriptions` | ❌ Ninguno |
| Suspensión por gracia expirada | `tasks.py` → `billing.expire_subscriptions` | ❌ Ninguno |
| Cancelación programada | `cancellation_service.py` | ❌ Ninguno |
| Trial expirado | `tasks.py` | ❌ Ninguno |
| Promoción aplicada / redimida | `promo_service.py` | ❌ Ninguno |

Este es el mayor **gap funcional** de la auditoría. Los tenants no reciben ninguna comunicación sobre el estado de su suscripción.

---

### 4.4 App: `accounts.support_ticket`

#### ¿Qué hace hoy?

El modelo `SupportTicket` existe con los campos `contact_email`, `subject`, `status`, `priority` y `category`. Sin embargo, **no hay ningún envío de email** asociado a la creación, actualización de estado ni mensajes de tickets.

Los tickets son de uso interno del backoffice de plataforma (staff de MiRubro), no expuestos directamente al tenant.

---

## 5. Riesgos detectados

### 5.1 Riesgos técnicos

| # | Riesgo | Archivo | Severidad |
|---|---|---|---|
| T1 | `send_password_reset_email` es **síncrono en request HTTP** — si el proveedor de email (boto3/SESv2) tarda o falla, la latencia de `POST /api/v1/auth/forgot-password/` aumenta (aunque el error se traga) | `accounts/views.py:707` | **Alto** |
| T2 | `send_verification_email_task` no tiene `max_retries` ni `default_retry_delay` — si el worker falla durante el envío, el email se pierde sin reintento | `accounts/tasks.py` | Medio |
| T3 | `notify_negative_feedback` es **síncrono** — llamado desde el flujo de recepción de reseñas sin protección de timeout | `reviews/notifications.py` | Medio |
| T4 | **Sin trazabilidad de envíos** — no existe modelo de auditoría de emails. No se puede saber si un email fue enviado, intentado o si hubo bounce | Todo el sistema | **Alto** |
| T5 | `_get_owner_email` duplicado en dos módulos de `reviews` — cambio en la lógica requiere actualizar dos lugares | `reviews/notifications.py:37`, `reviews/digest.py:63` | Bajo |
| T6 | `EMAIL_HOST` default = `smtp.sendgrid.net` — deuda legacy en `settings.py`. El proveedor destino (boto3/SESv2) **no usa `EMAIL_HOST`**, pero el default confuso puede inducir a error si alguien intenta configurar un fallback SMTP sin saber que SES API es el proveedor real | `config/settings.py:332` | Bajo |
| T7 | `SERVER_EMAIL` existe en `.env` pero `settings.py` no lo lee explícitamente — si el proceso Django lee `SERVER_EMAIL` antes de que `.env` sea cargado, usará el fallback de Django (`DEFAULT_FROM_EMAIL`) | `config/settings.py` | Bajo |

### 5.2 Riesgos funcionales

| # | Riesgo | Descripción | Severidad |
|---|---|---|---|
| F1 | **Billing totalmente silencioso** — ningún email al tenant en eventos de pago, gracia, suspensión | Los tenants descubren que están suspendidos solo cuando intentan acceder | **Alto** |
| F2 | **Sin email de confirmación de contraseña cambiada** — `ChangePasswordView` y `ForceChangePasswordView` no envían email de confirmación | Riesgo de seguridad: si alguien cambia la contraseña sin autorización, el propietario no lo sabe | **Alto** |
| F3 | **Solo el primer owner activo recibe los emails de reviews** — no hay control por tenant de quién quiere recibir cada tipo de email | Múltiples owners pueden quedar sin notificaciones | Medio |
| F4 | **Sin subjects/from consistentes** — cada email construye su subject y from de forma independiente. No hay fuente única de verdad | Difícil de cambiar en bloque; riesgo de inconsistencia de marca | Medio |
| F5 | **Sin preferencias de notificación** — el tenant no puede desactivar ningún tipo de email | No hay mecanismo de opt-out ni granularidad de preferencias | Bajo (hoy) |
| F6 | **Sin email de bienvenida** — el nuevo usuario solo recibe verificación de email pero no una introducción al producto | Oportunidad de onboarding perdida | Bajo |

### 5.3 Riesgos de seguridad

| # | Riesgo | Descripción | Severidad |
|---|---|---|---|
| S1 | **SES en sandbox** — mientras SES esté en sandbox, todos los emails van solo a destinatarios verificados (`mirubrodigital@gmail.com`). Si se configura `DEFAULT_FROM_EMAIL` con dominio incorrecto, los emails silenciosamente no llegarán | `config/settings.py:337` | **Alto** |
| S2 | **Sin email de confirmación tras cambio de contraseña** — sin aviso al usuario de que su contraseña fue cambiada, no puede detectar acceso no autorizado | `accounts/views.py` — `ChangePasswordView` | **Alto** |
| S3 | **Tokens en URL sin confirmación de entrega** — los tokens de verificación y reset se envían en texto plano en la URL. Sin trazabilidad, si el email nunca llegó no hay mecanismo de alerta | `accounts/services.py` | Medio |
| S4 | **`contact_info` de la reseña incluido sin sanitización en el cuerpo del email** — si un reviewer envía contenido malicioso en `contact_info`, este se incluye directamente en el cuerpo del email enviado al dueño | `reviews/notifications.py:84` | Medio |
| S5 | **`DEFAULT_FROM_EMAIL` default en `settings.py` inconsistente** — el default hardcoded es `no-reply@mirubro.com` pero `.env` ya lo sobreescribe correctamente. Si alguien despliega sin el `.env` correcto, los emails se envían con un FROM no verificado en SES | `config/settings.py:337` | Medio |

---

## 6. Recomendación de arquitectura futura

> Esta sección es conceptual. No implementar hasta completar la auditoría y aprobar el diseño.

### Estructura de la app `notifications`

```
services/api/src/apps/notifications/
├── models.py          # EmailDelivery (ver abajo)
├── services.py        # send_transactional_email() — punto único de entrada
├── tasks.py           # Celery tasks: send_email_task, retry logic
├── providers/
│   ├── base.py        # AbstractEmailProvider (interface)
│   └── amazon_ses.py  # AmazonSESProvider (via boto3/SESv2 API + IAM Role de EC2)
├── templates/
│   └── emails/
│       ├── base.html                # Layout base: header, footer, branding MiRubro
│       ├── verify_email.html        # Verificación de email (P0)
│       ├── password_reset.html      # Reset de contraseña (P0)
│       ├── password_changed.html    # Confirmación de cambio de contraseña (P0)
│       ├── employee_credentials.html # Credenciales de usuario secundario (P0)
│       ├── subscription_active.html  # Suscripción activada (P1)
│       ├── payment_failed.html       # Pago fallido / PAST_DUE (P1)
│       ├── subscription_suspended.html # Suspensión (P1)
│       ├── support_ticket.html       # Notificación de ticket de soporte (P1)
│       ├── negative_feedback.html    # Alerta de reseña negativa (P2)
│       └── weekly_digest.html        # Digest semanal (P2)
├── admin.py           # Admin para EmailDelivery
├── tests.py           # Tests unitarios e integración
└── apps.py
```

### Modelo conceptual `EmailDelivery`

El modelo no debe crearse aún. Concepto para referencia futura:

```python
class EmailDelivery(models.Model):
    """
    Registro inmutable de cada intento de envío de email.
    Permite trazabilidad, debugging y futuro manejo de bounces.
    """
    # Identificación
    id = UUIDField(primary_key=True)
    
    # Tipo y template
    email_type = CharField()   # 'verify_email', 'password_reset', etc.
    template = CharField()     # nombre del template usado
    
    # Destinatario
    recipient_email = EmailField()
    
    # Remitente
    from_email = EmailField()
    subject = CharField()
    
    # Contexto
    business = ForeignKey(Business, null=True)  # tenant (si aplica)
    user = ForeignKey(User, null=True)           # usuario relacionado
    
    # Estado de entrega
    STATUS_QUEUED    = 'queued'
    STATUS_SENT      = 'sent'
    STATUS_FAILED    = 'failed'
    STATUS_BOUNCED   = 'bounced'    # futuro: via SES SNS webhook
    STATUS_COMPLAINT = 'complaint'  # futuro: via SES SNS webhook
    status = CharField(choices=...)
    
    # Trazabilidad
    provider = CharField()         # 'amazon_ses', 'console', 'locmem'
    provider_message_id = CharField(null=True)  # ID de SES para tracking
    error_detail = TextField(null=True)         # Mensaje de error en fallo
    
    # Tiempos
    queued_at = DateTimeField()
    sent_at = DateTimeField(null=True)
    
    # Metadatos
    context_snapshot = JSONField(null=True)  # snapshot del contexto (sin datos sensibles)
```

### Proveedor `AmazonSESProvider`

El proveedor usará **boto3/SESv2 API directamente** — sin `EMAIL_BACKEND` SMTP, sin `EMAIL_HOST`, sin `EMAIL_HOST_USER` ni `EMAIL_HOST_PASSWORD`.

El proveedor debe:
- Crear un cliente `boto3.client("sesv2", region_name=settings.AWS_SES_REGION)`
- Las credenciales se resuelven automáticamente vía **IAM Role de EC2** — no se usa `AWS_ACCESS_KEY_ID` ni `AWS_SECRET_ACCESS_KEY`
- Llamar a `client.send_email(...)` con:
  - `FromEmailAddress = settings.DEFAULT_FROM_EMAIL`
  - `ConfigurationSetName = settings.AWS_SES_CONFIGURATION_SET`
  - `Destination = {"ToAddresses": [recipient_email]}`
  - `Content` con el HTML y/o texto plano renderizados desde template
- Capturar `response["MessageId"]` y guardarlo en `EmailDelivery.provider_message_id` para trazabilidad
- Capturar `ClientError` de boto3 y registrar en `EmailDelivery.error_detail` + status `failed`
- En desarrollo (`DEBUG=True` o `EMAIL_PROVIDER != amazon_ses`), delegar al backend de Django configurado (`console.EmailBackend`) como fallback

**Confirmado en producción**: el acceso boto3 a SES ya funciona desde el contenedor Django/API con IAM Role de EC2 (verificado con `aws sesv2 send-email` desde el host EC2 y con boto3 desde el contenedor).

**No requiere**:
- `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`
- `EMAIL_BACKEND = smtp.EmailBackend`
- Credenciales SMTP de SES (son distintas de las de la API y no se generaron)

---

## 7. Plan de migración recomendado

### Orden de migración

#### PR 1 — Verificación de email (P0, Async)

| Campo | Detalle |
|---|---|
| Archivos afectados | `accounts/services.py`, `accounts/tasks.py`, `accounts/views.py` |
| Riesgo | Medio — ya usa Celery, migración es un reemplazo de backend |
| Tests necesarios | Test de envío con `locmem`, test de fallback si worker falla, test de token válido/expirado |
| Requiere Celery | Sí (ya lo usa) |
| Requiere template | Sí — `verify_email.html` |
| Notas | Mantener `EmailService.send_verification_email` como wrapper por compatibilidad |

#### PR 2 — Password reset (P0, Async)

| Campo | Detalle |
|---|---|
| Archivos afectados | `accounts/services.py`, `accounts/views.py` (`ForgotPasswordView`) |
| Riesgo | **Alto** — actualmente síncrono en request. Migrar a Celery |
| Tests necesarios | Test de envío async, test de anti-enumeración, test de token expirado |
| Requiere Celery | Sí — se debe crear `send_password_reset_task` análogo a `send_verification_email_task` |
| Requiere template | Sí — `password_reset.html` |
| Notas | Validar que el timeout de `PASSWORD_RESET_TOKEN_HOURS=2` sea apropiado dado el delay de Celery |

#### PR 3 — Password changed (P0, Nuevo)

| Campo | Detalle |
|---|---|
| Archivos afectados | `accounts/views.py` (`ChangePasswordView`, `ForceChangePasswordView`, `ResetPasswordView`) |
| Riesgo | Bajo — es un email nuevo, no reemplaza nada |
| Tests necesarios | Test de envío tras cambio exitoso, test de no envío si cambio falla |
| Requiere Celery | Sí — envío async post-cambio |
| Requiere template | Sí — `password_changed.html` |

#### PR 4 — Credenciales usuario secundario (P0, Nuevo)

| Campo | Detalle |
|---|---|
| Archivos afectados | `accounts/services.py` (`InternalUserService.create_internal_user`), `accounts/owner_views.py` |
| Riesgo | Bajo — email nuevo cuando el owner crea un usuario interno |
| Tests necesarios | Test de envío con credenciales correctas, test de no envío si email vacío |
| Requiere Celery | Sí |
| Requiere template | Sí — `employee_credentials.html` |
| Notas | Solo enviar si `user.email` no está vacío (usuarios internos pueden no tener email) |

#### PR 5 — Billing: suscripción activa y pago fallido (P1, Nuevo)

| Campo | Detalle |
|---|---|
| Archivos afectados | `billing/webhook_processor.py`, `billing/subscription_activator.py`, `billing/tasks.py` |
| Riesgo | Medio — nuevo email en flujo crítico de billing |
| Tests necesarios | Test de envío tras webhook de pago exitoso, test de envío en PAST_DUE, test de envío en SUSPENDED |
| Requiere Celery | Sí — no bloquear el procesamiento del webhook |
| Requiere template | Sí — `subscription_active.html`, `payment_failed.html`, `subscription_suspended.html` |

#### PR 6 — Soporte (P1, Nuevo)

| Campo | Detalle |
|---|---|
| Archivos afectados | `accounts/support_ticket.py`, `accounts/tenant_support_views.py`, `accounts/platform_admin_support_views.py` |
| Riesgo | Bajo — email nuevo al crear/actualizar ticket |
| Tests necesarios | Test de envío al crear ticket, test de envío al cambiar estado |
| Requiere Celery | Sí |
| Requiere template | Sí — `support_ticket.html` |

#### PR 7 — Reviews: notificación y digest (P2)

| Campo | Detalle |
|---|---|
| Archivos afectados | `reviews/notifications.py`, `reviews/digest.py`, `reviews/tasks.py` |
| Riesgo | Bajo — refactor de email existente a templates HTML |
| Tests necesarios | Tests existentes deben seguir pasando; agregar test de rendering de template HTML |
| Requiere Celery | `notify_negative_feedback` debe migrarse a Celery; `digest` ya lo usa |
| Requiere template | Sí — `negative_feedback.html`, `weekly_digest.html` |

---

## 8. Tests existentes y tests faltantes

### Tests existentes relacionados con email

| Archivo | Qué testea | Calidad |
|---|---|---|
| `accounts/tests/test_auth_phase1_security.py` | Verifica que `send_verification_email_task.delay()` es llamado en el registro | ✅ Bueno — usa `@patch` |
| `accounts/tests/test_pr0_auth_prep.py` | Resend verification — verifica que el task es encolado | ✅ Bueno |
| `accounts/tests/test_account_modes.py` | Verifica que `EmailService.send_password_reset_email` es llamado/no llamado según `account_mode` | ✅ Bueno |
| `reviews/tests/test_notifications.py` | Tests completos de `notify_negative_feedback`: envío, throttle, contenido, fallo del backend de email / `send_mail` | ✅ Muy bueno — usa `locmem` y `mock` |
| `reviews/tests/test_digest.py` | Tests de `send_digest_for_business` y `run_weekly_digest`: envío, skip, fallo del backend de email / `send_mail` | ✅ Muy bueno |
| `reviews/tests/test_e2e_lifecycle.py` | Tests end-to-end que incluyen verificación de notificaciones | ✅ Bueno |

### Gaps identificados

| Test faltante | Prioridad | Descripción |
|---|---|---|
| `EmailService.send_verification_email` — test directo del cuerpo del email | P0 | No hay test que verifique el subject, body y URL del email de verificación |
| `EmailService.send_password_reset_email` — test directo | P0 | No hay test que verifique contenido, subject y URL del email de reset |
| `ForgotPasswordView` — test de envío real a `locmem` | P0 | Los tests existentes mockean `EmailService` completo; falta test de contenido real |
| `ResendVerificationView` — test de throttle | P1 | No hay test de throttle en resend |
| Email de confirmación post-`ChangePasswordView` | P0 | No existe feature, no existe test |
| Email de credenciales de usuario secundario | P0 | No existe feature, no existe test |
| Emails de billing (todos) | P1 | No existen features ni tests |
| `AmazonSESProvider` — test de ConfigurationSet | P1 | No hay test de que `AmazonSESProvider` llama a `send_email` con `ConfigurationSetName=settings.AWS_SES_CONFIGURATION_SET` |

### Tests mínimos necesarios antes de migrar

Antes de implementar `notifications`:

1. **Test de `EmailService` con `locmem`** — verificar subject, body, from, recipient para ambos emails.
2. **Test de task `send_verification_email_task`** — verificar comportamiento cuando `user_id` no existe.
3. **Test de `notify_negative_feedback` con `contact_info` con caracteres especiales** — verificar que no se produce contenido malicioso en el email.
4. **Test de smoke de settings** — verificar que en `DEBUG=False` el `EMAIL_BACKEND` no sea `console`.

---

## 9. Checklist para aprobar la auditoría

- [x] Se relevaron todos los usos de `send_mail` (`accounts/services.py`, `reviews/notifications.py`, `reviews/digest.py`).
- [x] Se relevaron configuraciones de email (`config/settings.py` líneas 325–342).
- [x] Se relevaron tasks Celery relacionadas (`accounts/tasks.py`, `reviews/tasks.py`).
- [x] Se identificaron emails críticos (`send_verification_email`, `send_password_reset_email`).
- [x] Se clasificaron riesgos (técnicos, funcionales, seguridad — Sección 5).
- [x] Se propuso orden de migración (7 PRs — Sección 7).
- [x] No se modificó comportamiento productivo.
- [x] No se tocaron credenciales ni `.env`.
- [x] No se crearon migraciones.
- [x] No se implementó todavía `notifications`.

---

## Apéndice A — Archivos inspeccionados

| Archivo | Relevancia |
|---|---|
| `services/api/src/config/settings.py` | Configuración de email, Celery Beat schedule |
| `services/api/src/apps/accounts/services.py` | `EmailService` — 2 métodos de envío de email |
| `services/api/src/apps/accounts/views.py` | `RegisterView`, `ForgotPasswordView`, `ResendVerificationView`, `VerifyEmailView`, `ChangePasswordView` |
| `services/api/src/apps/accounts/tasks.py` | `send_verification_email_task` |
| `services/api/src/apps/accounts/models.py` | `AccountProfile` — generación de tokens |
| `services/api/src/apps/accounts/owner_views.py` | `InternalUserService.create_internal_user` — sin email aún |
| `services/api/src/apps/accounts/employee_views.py` | Credenciales de empleados — sin email |
| `services/api/src/apps/accounts/support_ticket.py` | Modelo de ticket — sin email |
| `services/api/src/apps/reviews/notifications.py` | `notify_negative_feedback` |
| `services/api/src/apps/reviews/digest.py` | `send_digest_for_business`, `run_weekly_digest` |
| `services/api/src/apps/reviews/tasks.py` | `send_weekly_digest` Celery task |
| `services/api/src/apps/billing/tasks.py` | `expire_subscriptions` — sin email |
| `services/api/src/apps/billing/webhook_processor.py` | Procesamiento de pagos MP — sin email |
| `services/api/src/apps/billing/subscription_activator.py` | Activación de suscripciones — sin email |
| `services/api/src/apps/accounts/tests/test_auth_phase1_security.py` | Tests de seguridad de auth y email |
| `services/api/src/apps/accounts/tests/test_pr0_auth_prep.py` | Tests de preparación PR0 — resend verification |
| `services/api/src/apps/accounts/tests/test_account_modes.py` | Tests de account_mode y password reset gating |
| `services/api/src/apps/reviews/tests/test_notifications.py` | Tests de `notify_negative_feedback` |
| `services/api/src/apps/reviews/tests/test_digest.py` | Tests de digest semanal |
| `services/api/src/apps/reviews/tests/test_e2e_lifecycle.py` | Tests E2E de ciclo de reseñas |
| `services/api/src/common/storages.py` | S3Boto3 — sin relación con email |

---

## Apéndice B — Próximos pasos recomendados para PR 1

1. **Crear la app `notifications`** con la estructura propuesta en la Sección 6.
2. **Implementar `EmailDelivery` model** + migraciones.
3. **Implementar `AmazonSESProvider`** usando `boto3.client("sesv2", region_name=settings.AWS_SES_REGION)` con IAM Role de EC2 — sin credenciales SMTP, sin `EMAIL_HOST`.
4. **Migrar `send_verification_email`** a `notifications` con template HTML `verify_email.html`.
5. **Migrar `send_password_reset_email`** a Celery + template HTML `password_reset.html`.
6. **Agregar `password_changed` email** en `ChangePasswordView`, `ForceChangePasswordView` y `ResetPasswordView`.
7. **Exponer variables SES en `settings.py`** — agregar `AWS_SES_REGION`, `AWS_SES_CONFIGURATION_SET`, `EMAIL_PROVIDER`, `EMAIL_TRANSACTIONAL_ENABLED`, `EMAIL_MARKETING_ENABLED`, `SUPPORT_EMAIL` y `BILLING_EMAIL` como settings Django formales (`os.getenv(...)`) para que la app `notifications` pueda acceder vía `settings.*`.
8. **Corregir `DEFAULT_FROM_EMAIL` default en `settings.py`** — cambiar de `'Mirubro <no-reply@mirubro.com>'` a `'MiRubro <notificaciones@mirubro.com>'` para que coincida con el `.env` de producción y con la dirección verificada en SES.
9. **Verificar SES sandbox** — antes del primer deploy real, verificar que `mirubrodigital@gmail.com` está en la lista de destinatarios verificados.
10. **Salir del sandbox SES** — solicitar producción access en AWS para poder enviar a cualquier destinatario.
