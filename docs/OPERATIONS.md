# Operaciones de producción — MiRubro

Referencia rápida para operar web y API en contenedores de producción.

---

## Migraciones de base de datos

La imagen de producción (`runtime` stage) incluye un `docker-entrypoint.sh`
que soporta tres patrones de ejecución de migraciones:

### Opción A — Tarea one-off (recomendada para ECS/Fargate)

```bash
# Ejecuta migraciones y termina (exit 0).
# Ideal como ECS RunTask antes de actualizar el servicio.
docker run --rm --env-file .env mirubro-api:latest \
  sh docker-entrypoint.sh migrate
```

### Opción B — Auto-migrate al arrancar

```bash
# La variable RUN_MIGRATIONS=true ejecuta migrate antes de gunicorn.
# Útil en despliegues simples (un solo contenedor / staging).
docker run --rm --env-file .env -e RUN_MIGRATIONS=true mirubro-api:latest
```

### Opción C — Manual (docker exec)

```bash
# Dentro de un contenedor ya corriendo:
docker exec mirubro-api python src/manage.py migrate --noinput
```

> **En docker-compose dev**, el comando del servicio `api` ya ejecuta
> `python manage.py migrate && python manage.py runserver ...` automáticamente.

### Precondición — `merchant_payments.0002_encrypt_mp_tokens`

Esta migración cifra en reposo (Fernet) `access_token`/`refresh_token` de
`MercadoPagoConnection`. **Antes de aplicarla en un ambiente con filas
existentes**, `MP_TOKEN_ENCRYPTION_KEY` debe estar configurada con una
Fernet key válida — si falta o es inválida, la migración falla de forma
segura (no transforma parcialmente ninguna fila; ver `check_mp_token_encryption_key`
más abajo). Validar antes de desplegar:

```bash
python manage.py check --deploy --tag security
```

**Rollback**: revertir por debajo de `0002` vuelve a dejar los tokens en
texto plano en la base de datos (es el comportamiento correcto de un
rollback de esquema, pero no es una respuesta segura ante un incidente de
compromiso de la clave — un rollback en ese escenario reexpondría las
credenciales que la migración protege).

### Deploy de `billing.0023_webhookdelivery_retry_lifecycle` (Slice 5B.4)

Estrategia canónica: **mantenimiento breve** (no rolling). Ningún writer
pre-5B.4 debe recibir webhooks después de aplicar 0023.

Qué pasa si igual se cruzan versiones (verificado en PostgreSQL real,
`apps/billing/tests/test_webhook_deploy_window.py`):

- **Código viejo + schema 0023**: las columnas nuevas `attempts`, `flow`,
  `ref`, `error_category` son NOT NULL sin default de base, así que el INSERT
  del `receive_webhook()` viejo falla (`IntegrityError`) antes de cualquier
  lógica de negocio → HTTP 500 → Mercado Pago reintenta y el código nuevo lo
  procesa con `flow`/`ref`. No puede quedar un `payment` RECEIVED sin
  `flow`/`ref` escrito por el código viejo.
- **Código nuevo + schema 0022**: la API responde 503 (MP reintenta) y el
  sweeper `billing.retry_failed_webhooks` no toca la tabla hasta que 0023
  figure como aplicada (devuelve `schema_not_ready`).
- Filas RECEIVED anteriores a 0023: las clasifica la propia migración
  (IGNORED sólo con efecto probado; el resto DEAD_LETTER `legacy_unverified`).

Orden (docker compose, desde `infra/`):

```bash
docker compose build api celery-worker celery-beat
# 1. Cortar a todos los writers/consumers viejos (MP reintenta mientras tanto).
docker compose stop celery-beat celery-worker api
# 2. Migrar con la imagen nueva, sin levantar la API todavía.
docker compose run --rm --no-deps api python manage.py migrate --noinput
docker compose run --rm --no-deps api python manage.py showmigrations billing   # 0023 [X]
# 3. API (su `migrate` al arrancar es no-op) → verificar /health.
docker compose up -d api
# 4. Workers, 5. Beat al final (Beat nuevo + worker viejo = task no registrada).
docker compose up -d celery-worker
docker compose up -d celery-beat
```

Después: confirmar en los logs de Beat que se agenda
`billing.retry_failed_webhooks` y en los del worker que no aparece
`retry sweep skipped`. Revisar las deliveries DEAD_LETTER con
`error_category=legacy_unverified` (alertas del admin) antes de reprocesarlas
con `retry_mp_webhooks --id <id> --revive-dead-letter`.

**Rollback**: volver a la imagen vieja exige también
`migrate billing 0022` con la API detenida; código viejo sobre schema 0023
no puede persistir webhooks.

### Turnos — webhook `flow=appointment` (Slice 6B, `appointments.0007`)

`appointments.0007` agrega `AppointmentPayment.review_reason`, el estado
`requires_review` y dos constraints (único parcial sobre
`provider_payment_id`, y "cobrado ⇒ tiene `provider_payment_id`"). Tabla
nueva y chica: migración online, sin ventana. Si la API nueva corre antes de
migrar, el webhook falla al escribir → delivery FAILED `internal_error` →
reintento automático.

Pagos a revisar a mano (dinero cobrado en la cuenta MP del Business, turno
**no** confirmado; refund todavía no automatizado):

- `AppointmentPayment.status = requires_review`, motivo en `review_reason`
  (`approved_after_expiry`, `slot_conflict`, `appointment_already_confirmed`,
  `appointment_not_payable`, `approval_time_unknown`). `paid_at` = fecha de
  aprobación de MP. La delivery queda PROCESSED con nota `requires_review`.
- Deliveries DEAD_LETTER sin mutación local, `error_category`:
  `appointment_financial_mismatch` (monto/moneda/cobrador/metadata),
  `appointment_payment_id_conflict` (el pago MP ya está en otro intento),
  `appointment_duplicate_capture` (segundo pago aprobado para el mismo
  intento), `merchant_reauth_required` (reprocesar con
  `retry_mp_webhooks --id <id> --revive-dead-letter` cuando el negocio
  reconecte MP).

### Turnos — expiración de holds (Slice 7C)

Beat agenda `appointments.expire_holds` cada 2 minutos
(`CELERY_BEAT_SCHEDULE`, `appointments-expire-holds`): pasa
`pending_payment` con `expires_at` vencido → `expired`. Solo cambia
`status`; no toca `expires_at` ni los `AppointmentPayment`. Idempotente.

La disponibilidad **no** depende de esta tarea: `occupying()` ya libera un
hold vencido aunque su `status` siga en `pending_payment`. Si Beat está
caído, los horarios siguen siendo correctos; solo el estado persistido queda
atrasado en el panel. Ejecución manual equivalente:
`python manage.py expire_appointment_holds`.

### Clientes — emails al Customer vía Amazon SES (CUSTOMER 07D.3A / 07D.3A.1)

`CustomerMessageDelivery` (canal email) usa SES **solo** con
`CUSTOMER_DELIVERY_PROVIDER_EMAIL=ses`; el default es `fake` (no envía).
Migraciones: `customers.0012` (choices, no-op SQL), `customers.0013`
(`CustomerCommunicationSettings`, tabla nueva vacía). Ambas aditivas.

Qué espera el código:

| Setting | Valor | Nota |
|---|---|---|
| `AWS_SES_REGION` | `sa-east-1` | Compartido con `apps.notifications`. La identidad debe estar verificada en **esta** región. |
| `AWS_SES_FROM_EMAIL` | vacío → dirección de `DEFAULT_FROM_EMAIL` | Prod: `notificaciones@mirubro.com` (identidad ya usada por notifications). No poner un dominio no verificado (p. ej. `mirubro.com.ar`). |
| `AWS_SES_FROM_NAME` | `MiRubro` | Display: `"<Negocio> vía MiRubro"`. El Business no elige el From. |
| `AWS_SES_CONFIGURATION_SET` | opcional | Prod `.env` usa `mirubro-transactional`; si se setea, debe existir en la región o SES rechaza (`ses_configuration_error`). |
| Credenciales | cadena de boto3 | Prod: IAM Role de la instancia/task. Nunca keys en repo/DB/settings. |

Reply-To: solo `CustomerCommunicationSettings.reply_to_email` ("Email para
respuestas" en Turnos → Configuración, owner/admin). Vacío = sin Reply-To.
Nunca se usa el email fiscal (`BusinessBillingProfile.email`), del owner ni del cliente.

IAM mínimo para el runtime que envía (role existente; no usuarios admin):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "CustomerDeliverySend",
    "Effect": "Allow",
    "Action": "ses:SendEmail",
    "Resource": [
      "arn:aws:ses:sa-east-1:<ACCOUNT_ID>:identity/mirubro.com",
      "arn:aws:ses:sa-east-1:<ACCOUNT_ID>:identity/notificaciones@mirubro.com",
      "arn:aws:ses:sa-east-1:<ACCOUNT_ID>:configuration-set/mirubro-transactional"
    ],
    "Condition": {"StringEquals": {"ses:FromAddress": "notificaciones@mirubro.com"}}
  }]
}
```

SES v2 `SendEmail` autoriza contra la identidad usada (dominio o dirección,
según cuál esté verificada) y contra el configuration set si se pasa. No hace
falta `ses:SendRawEmail` ni permisos de lectura. Para la verificación previa a
la QA (opcional, solo lectura, desde una consola/perfil de operador — no el
runtime): `ses:GetAccount`, `ses:GetEmailIdentity`, `ses:GetConfigurationSet`.

Sandbox: mientras la cuenta esté en sandbox solo se puede enviar a
destinatarios verificados (`ses_identity_not_verified` en el Delivery si no).
El pedido de production access es manual (consola SES), fuera del código.

QA controlada (cliente QA, nunca reales):

```bash
python manage.py customer_deliveries prepare --customer <uuid> --channel email \
    --purpose appointment_reminder --key qa:ses:<n> --appointment <uuid>
python manage.py customer_deliveries execute --id <delivery uuid> --provider ses
```

Para correrlo en local, montar un perfil AWS de operador en el contenedor
(`-v ~/.aws:/root/.aws:ro -e AWS_PROFILE=<perfil>`); boto3 lo toma solo.

---

## Health checks

### API — `GET /api/v1/health/`

Verifica conectividad real con PostgreSQL y Redis.

| Estado       | HTTP | Cuerpo ejemplo |
|-------------|------|----------------|
| Saludable   | 200  | `{"status":"ok","dependencies":{"database":"ok","redis":"ok"}}` |
| Degradado   | 503  | `{"status":"degraded","dependencies":{"database":"ok","redis":"unavailable"}}` |

Configuración sugerida para ALB/ECS:

```json
{
  "healthCheck": {
    "path": "/api/v1/health/",
    "interval": 30,
    "timeout": 5,
    "healthyThreshold": 2,
    "unhealthyThreshold": 3
  }
}
```

### Web — `GET /api/health`

Endpoint liviano (sin dependencias externas). Devuelve siempre `{"status":"ok"}` / 200.

```json
{
  "healthCheck": {
    "path": "/api/health",
    "interval": 30,
    "timeout": 5,
    "healthyThreshold": 2,
    "unhealthyThreshold": 3
  }
}
```

---

## Variables de entorno obligatorias

### API (`services/api/.env`)

| Variable               | Descripción                           |
|------------------------|---------------------------------------|
| `DJANGO_SECRET_KEY`    | Clave criptográfica (≥50 chars)       |
| `DJANGO_DEBUG`         | `False` en producción                 |
| `DJANGO_ALLOWED_HOSTS` | Dominios separados por coma           |
| `POSTGRES_HOST`        | Endpoint de RDS/PostgreSQL            |
| `POSTGRES_DB`          | Nombre de la base de datos            |
| `POSTGRES_USER`        | Usuario de base de datos              |
| `POSTGRES_PASSWORD`    | Contraseña de base de datos           |
| `REDIS_URL`            | URL de Redis/ElastiCache (broker)     |
| `CACHE_REDIS_URL`      | URL de Redis/ElastiCache (cache)      |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos (frontend URL)    |
| `COOKIE_SECURE`        | `True` (HTTPS obligatorio)            |
| `MFA_ENCRYPTION_KEY`   | Fernet key para TOTP                  |
| `MP_ACCESS_TOKEN`      | Token de MercadoPago producción       |
| `MP_WEBHOOK_SECRET`    | Secret de webhook de MercadoPago      |
| `MP_TOKEN_ENCRYPTION_KEY` | Fernet key para cifrar en reposo access_token/refresh_token de MercadoPagoConnection. Requerida antes de `migrate` (ver precondición de `0002_encrypt_mp_tokens` arriba). |
| `AGENT_SECRET_ENCRYPTION_KEY` | Fernet key dedicada para cifrar en reposo los secretos HMAC del agente de WhatsApp (`AgentCredential`, alta con `manage.py provision_agent`). Solo requerida cuando se aprovisiona/usa la integración; sin ella falla cerrado. |
| `AGENT_INTEGRATION_ENABLED` | `true` habilita el receiver `PUT /api/v1/integrations/agent/leads/<uuid>/` (AGENT 02B). Default `false` (responde 503). En `true` sin `AGENT_SECRET_ENCRYPTION_KEY` válida, el system check `leads.E001`/`E002` hace fallar `check`/`migrate`. No habilitar en producción sin aprovisionar instancia/credencial/canal. |
| `AGENT_LEADS_SYNC_THROTTLE_RATE` | Throttle del receiver por `AgentInstance` (default `600/minute`). Fail-open si Redis cae. |

Referencia completa: `services/api/.env.example`

### Web (`apps/web/.env`)

| Variable               | Descripción                          |
|------------------------|--------------------------------------|
| `NEXT_PUBLIC_API_URL`  | URL pública de la API (browser)      |
| `NEXT_PUBLIC_BASE_URL` | URL pública del frontend             |
| `API_URL_INTERNAL`     | URL interna de la API (SSR)          |

Build-time (pasadas como `--build-arg`):

| Variable       | Descripción                                |
|----------------|--------------------------------------------|
| `API_HOSTNAME` | Hostname de API para `next/image` patterns |

Referencia completa: `apps/web/.env.example`

---

## Build de imágenes de producción

```bash
# API
docker build --target runtime -t mirubro-api:latest services/api

# Web (requiere build-args para NEXT_PUBLIC_*)
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://api.mirubro.com \
  --build-arg NEXT_PUBLIC_BASE_URL=https://www.mirubro.com \
  --build-arg API_HOSTNAME=api.mirubro.com \
  -t mirubro-web:latest apps/web
```

---

## Swagger / API docs

`/api/docs/` y `/api/schema/` solo están disponibles cuando `DJANGO_DEBUG=True`.
En producción, exportar el schema offline:

```bash
docker exec mirubro-api python src/manage.py spectacular --file schema.yml
```
