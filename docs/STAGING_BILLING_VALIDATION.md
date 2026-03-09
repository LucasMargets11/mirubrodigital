# Staging Billing Validation Guide

## Overview

Esta guía cubre la validación end-to-end del circuito billing/SubscriptionV2 en staging.
Todo el legacy (`billing.Subscription`, `business.Subscription`) sigue coexistiendo sin cleanup.

---

## 1. Pre-requisitos — Variables de entorno críticas

Archivo: `services/api/.env`

```env
# Mercado Pago
MP_ACCESS_TOKEN=TEST-xxxx-...          # token de TEST de tu cuenta MP
MP_WEBHOOK_SECRET=your_webhook_secret  # secreto de notificaciones MP (puede omitirse en dev)

# URLs públicas (necesarias para que el webhook funcione desde MP)
BASE_PUBLIC_URL=https://xxxx.ngrok-free.app   # URL del API expuesta (ngrok / tunnel)
FRONTEND_URL=https://xxxx.ngrok-free.app       # URL del frontend (o localhost:3000 en dev)

# Django
DJANGO_SECRET_KEY=change-me-in-staging
DJANGO_DEBUG=False                     # False en staging real
DJANGO_LOG_LEVEL=INFO                  # INFO es suficiente; DEBUG para verbose

# DB / Redis
POSTGRES_DB=mirubro
POSTGRES_USER=mirubro
POSTGRES_PASSWORD=secure_password
REDIS_URL=redis://redis:6379/0
```

> **Sin `BASE_PUBLIC_URL` real, MP no puede enviar webhooks.** En local usá ngrok (ver sección 3).

---

## 2. Levantar el stack completo

```bash
# Desde infra/
cd infra

# Stack sin tunnel (dev local)
docker compose up --build

# Stack con tunnel ngrok (necesario para webhooks MP reales)
NGROK_AUTHTOKEN=tu_token docker compose --profile tunnel up --build
```

### Servicios que deben estar corriendo

| Contenedor               | Propósito                              |
|--------------------------|----------------------------------------|
| `mirubro-api`            | Django / DRF API                       |
| `mirubro-celery-worker`  | Procesa tareas async (billing, etc.)   |
| `mirubro-celery-beat`    | Encola tareas periódicas cada hora     |
| `mirubro-redis`          | Broker Celery                          |
| `mirubro-postgres`       | Base de datos                          |
| `mirubro-ngrok` *(opt)*  | Túnel HTTPS para webhooks MP           |

### Verificar worker y beat activos

```bash
# Worker
docker compose logs celery-worker --tail=30

# Beat  
docker compose logs celery-beat --tail=30

# Conectividad Redis
docker compose exec celery-worker celery -A config inspect ping
```

---

## 3. Exponer el webhook para Mercado Pago

```bash
# 1. Levantar stack con ngrok
NGROK_AUTHTOKEN=tu_token docker compose --profile tunnel up -d

# 2. Obtener la URL pública
docker compose logs ngrok | grep "url="
#  → url=https://abc123.ngrok-free.app

# 3. Actualizar services/api/.env
BASE_PUBLIC_URL=https://abc123.ngrok-free.app

# 4. Reiniciar API y workers
docker compose restart api celery-worker celery-beat

# 5. Verificar configuración MP
curl http://localhost:8000/api/v1/billing/dev/mp/status
```

La URL del webhook que MP debe notificar es:
```
https://<BASE_PUBLIC_URL>/api/v1/billing/mercadopago/webhook
```

---

## 4. Correr los smoke tests automatizados

```bash
# Rápido (todos los tests, limpia datos al terminar)
docker compose exec api python manage.py billing_smoke_test

# Verbose + conservar datos para inspección
docker compose exec api python manage.py billing_smoke_test --verbose --keep

# Con output de colores en PowerShell/CMD
docker compose exec api python manage.py billing_smoke_test
```

### Tests cubiertos

| Test | Qué valida |
|------|------------|
| T1   | SubscriptionV2 birth path (CHECKOUT_PENDING) |
| T2   | BillingEvent idempotencia (get_or_create) |
| T3   | PaymentAttempt creado + idempotencia |
| T3b  | PaymentAttempt no duplicado en segunda llamada |
| T4   | Transición CHECKOUT_PENDING → ACTIVE |
| T5   | runtime=v2 → access_granted=True para ACTIVE |
| T6a  | SUSPENDED → access_allowed=False, reason=suspended |
| T6b  | Sin suscripción → access_allowed=False, reason=no_subscription |
| T6c  | CANCELED → access_allowed=False, reason=canceled |
| T7   | expire_subscriptions: ACTIVE → PAST_DUE |
| T7b  | V2.status = PAST_DUE después de la tarea |
| T7c  | expire_subscriptions es idempotente |
| T8   | expire_subscriptions: PAST_DUE → SUSPENDED (grace vencido) |
| T8b  | V2.status = SUSPENDED después de la tarea |
| T9   | Runtime V2 resuelve entitlements para plan 'pro' |

---

## 5. Simular un webhook de Mercado Pago

```bash
# 5a. Desde dentro del contenedor (usando el script incluido)
docker compose exec api python scripts/simulate_mp_webhook.py \
    --data-id 2c938084746d3318017478c2360b0000 \
    --topic subscription_preapproval \
    --verbose

# 5b. Desde fuera del contenedor (requiere requests: pip install requests)
python services/api/scripts/simulate_mp_webhook.py \
    --url http://localhost:8000 \
    --data-id 2c938084746d3318017478c2360b0000

# 5c. Con firma HMAC (si MP_WEBHOOK_SECRET está configurado)
python services/api/scripts/simulate_mp_webhook.py \
    --data-id 2c938084746d3318017478c2360b0000 \
    --secret tu_webhook_secret

# 5d. Con curl directo (DEV, sin firma)
curl -X POST http://localhost:8000/api/v1/billing/mercadopago/webhook \
  -H "Content-Type: application/json" \
  -H "x-request-id: test-$(date +%s)" \
  -d '{"type":"subscription_preapproval","data":{"id":"PREAPPROVAL_ID"}}'
```

---

## 6. Verificar / ejecutar la tarea periódica manualmente

```bash
# Forzar ejecución inmediata de expire_subscriptions
docker compose exec api python manage.py shell -c "
from apps.billing.tasks import expire_subscriptions
result = expire_subscriptions.apply().get()
print('expire_subscriptions result:', result)
"

# O a través de Celery (encola en Redis, ejecuta el worker)
docker compose exec api celery -A config call billing.expire_subscriptions

# Ver resultado en logs
docker compose logs celery-worker --tail=50
```

La tarea corre automáticamente cada hora (minuto 0) cuando celery-beat está activo.  
Schedule configurado en `settings.CELERY_BEAT_SCHEDULE['billing-expire-subscriptions']`.

---

## 7. Qué logs mirar

```bash
# Logs combinados de todos los servicios de billing
docker compose logs api celery-worker celery-beat --follow

# Filtrar solo eventos de billing
docker compose logs api --follow | grep -E '\[MPWebhook\]|\[billing\.task\]|\[runtime\]|\[enforcement\]'

# PaymentAttempt / BillingEvent creados
docker compose logs api | grep -E 'BillingEvent (created|deduplicated)|PaymentAttempt'

# Denials de enforcement
docker compose logs api | grep 'access_denied'

# Transiciones de expiración
docker compose logs celery-worker | grep 'expire_subscriptions\|active→past_due\|past_due→suspended'
```

### Líneas de log clave y su significado

| Prefijo / pattern | Significa |
|-------------------|-----------|
| `[MPWebhook] received topic=...` | Webhook recibido (primer log del handler) |
| `[MPWebhook] BillingEvent created id=...` | BillingEvent nuevo persistido |
| `[MPWebhook] BillingEvent deduplicated id=...` | Webhook duplicado — idempotencia OK |
| `[MPWebhook] duplicate PaymentEvent` | PaymentEvent ya existía — skip temprano |
| `[MPWebhook] activate_tenant business=...` | Flujo de activación iniciado |
| `[activate_tenant] Synced SubscriptionV2 ... → active` | V2 pasó a ACTIVE |
| `[_create_payment_attempt] Created PaymentAttempt ...` | PaymentAttempt registrado |
| `[runtime] source=v2 business=...` | Resolución V2-first exitosa |
| `[runtime] source=v2(no_access) ...` | V2 degradado, acceso denegado |
| `[runtime] source=legacy ...` | Fallback a legacy (sin V2 usable) |
| `[enforcement] access_denied status=...` | Enforcement denegó acceso |
| `[enforcement] grace_period_active ...` | PAST_DUE dentro de gracia |
| `[billing.task] active→past_due ...` | Tarea movió sub a PAST_DUE |
| `[billing.task] past_due→suspended ...` | Tarea movió sub a SUSPENDED |
| `[billing.task] expire_subscriptions complete: ...` | Resumen final de la tarea |

---

## 8. Checklist de smoke test manual

### 8.1 Alta nueva

- [ ] `POST /api/v1/billing/start-subscription` devuelve `init_point` + `intent_id`
- [ ] `SubscriptionV2` creado con status `CHECKOUT_PENDING` y `provider_sub_id` real
- [ ] `SubscriptionIntent.subscription_v2` apunta al V2 correcto
- [ ] `Business.status = pending_activation`

### 8.2 Webhook de activación

- [ ] Simular webhook con `simulate_mp_webhook.py` (ver sección 5)
- [ ] Log: `[MPWebhook] received topic=subscription_preapproval`
- [ ] Log: `[MPWebhook] BillingEvent created`
- [ ] Log: `[MPWebhook] activate_tenant business=...`
- [ ] Log: `[activate_tenant] Synced SubscriptionV2 ... → active`
- [ ] `Business.status = active` en DB
- [ ] `SubscriptionV2.status = ACTIVE` en DB
- [ ] Segundo POST con mismo `x-request-id`→ log `duplicate PaymentEvent` + HTTP 200 (no duplica BillingEvent)

### 8.3 Entitlements / Enforcement

- [ ] `GET /api/v1/auth/me` (o endpoint que use `get_enforcement_decision`) devuelve `access_allowed=True` para negocio activo
- [ ] Payload incluye `reason_code`, `show_renewal_prompt`
- [ ] Negocio sin SubscriptionV2 → `access_allowed=False`, `reason_code=no_subscription`
- [ ] Negocio con V2 SUSPENDED → `access_allowed=False`, `reason_code=suspended`

### 8.4 Expiración

- [ ] Crear V2 con `current_period_end` en el pasado
- [ ] Ejecutar `expire_subscriptions` manualmente (sección 6)
- [ ] V2 pasa a `PAST_DUE` con `grace_until` seteado
- [ ] Ejecutar de nuevo → V2 sigue en `PAST_DUE` (idempotente)
- [ ] Crear V2 con `grace_until` en el pasado
- [ ] Ejecutar task → V2 pasa a `SUSPENDED`

### 8.5 Legacy coexistencia

- [ ] Negocios con solo `billing.Subscription` siguen funcionales
- [ ] `resolve_subscription` devuelve `source=legacy` para negocios sin V2
- [ ] Ninguna migración destructiva ejecutada (`billing.Subscription` y `business.Subscription` intactos)

---

## 9. Diagnóstico rápido de Mercado Pago

```bash
# Verificar credenciales y URLs configuradas
curl http://localhost:8000/api/v1/billing/dev/mp/status

# Health check genérico
curl http://localhost:8000/api/v1/health/
```

---

## 10. Riesgos residuales

| Riesgo | Severidad | Mitigación actual |
|--------|-----------|-------------------|
| `BASE_PUBLIC_URL` no configurado en staging | Alto | `DevMercadoPagoPingView` lo detecta y advierte |
| V2 sin `provider_sub_id` (birth path parcial) | Medio | Fallback por `(business, service_type)` en `_resolve_subscriptionv2` |
| Beat no iniciado (no celery-beat container) | Medio | Ahora declarado en `docker-compose.yml`; alarma visible en logs |
| MP token expirado / de producción en staging | Alto | Revisar `MP_ACCESS_TOKEN` antes de cada ciclo de prueba |
| BillingEvent `_be` no definido si `event_id=None` | Bajo | Handler ahora inicializa `_be = None` antes del bloque condicional |
| Duplicación de SubscriptionV2 en race condition | Bajo | `get_or_create` + `exclude(CANCELED)` minimiza riesgo; idempotencia probada en T2 |

---

## 11. Qué NO se hace en esta fase

- No se elimina legacy (`billing.Subscription`, `business.Subscription`)
- No se rediseñan addons V2 nativos
- No se toca `OperatorSession` ni POS
- No se hace cleanup masivo de billing
- No se despliega a producción
