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
