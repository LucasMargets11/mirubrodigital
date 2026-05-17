# Auditoría de credenciales y archivos .env — MiRubro

**Fecha:** 2026-05-09  
**Rama auditada:** `develop`  
**Comparada con:** `master`  
**Auditor:** Senior DevSecOps / Copilot  

---

## 1. Resumen ejecutivo

| Item | Resultado |
|---|---|
| Archivos `.env` encontrados en disco | 5 |
| Archivos `.env` trackeados por Git | 0 (ninguno) |
| Archivos `.env.example` trackeados por Git | 2 (`develop` únicamente) |
| Archivos con valores productivos reales | 0 detectados |
| Archivos con valores locales / dev | 5 |
| Archivos con inconsistencias / duplicados | 1 (`services/api/.env`) |
| Riesgo principal | `services/api/.env` tiene variables duplicadas y una URL de túnel ngrok activa en `BASE_PUBLIC_URL`; `infra/.env` tiene `DJANGO_DEBUG=False` pero el API usa su propio `.env` con `DJANGO_DEBUG=True` — confusión de fuentes |

**Conclusión general:** El esquema de ignore está bien configurado. No se detectaron credenciales productivas reales commiteadas. Los riesgos son operativos (duplicados, inconsistencias entre archivos, ausencia de `.env.example` en `master`).

---

## 2. Inventario de archivos .env

| Archivo | Trackeado por Git | Ignorado por `.gitignore` | Consumido por | Ambiente aparente | Riesgo |
|---|---|---|---|---|---|
| `services/api/.env` | NO | SI (línea 18: `**/.env`) | api, celery-worker, celery-beat (docker-compose) | Desarrollo local | MEDIO — tiene variables duplicadas y URL de túnel ngrok |
| `services/api/.env.example` | SI (develop only) | NO (excluido por `!**/.env.example`) | Referencia para devs | Template | BAJO |
| `apps/web/.env` | NO | SI (línea 18: `**/.env`) | web (docker-compose) | Desarrollo local | BAJO — solo URLs locales |
| `apps/web/.env.example` | SI (develop only) | NO | Referencia para devs | Template | BAJO |
| `apps/web/.env.local` | NO | SI (línea 19: `**/.env.*`) | Next.js (carga automática local) | Desarrollo local | BAJO — solo URLs locales |
| `infra/.env` | NO | SI (línea 18: `**/.env`) | Docker Compose (interpolación de `${}`) | Desarrollo local | MEDIO — `DJANGO_DEBUG=False` inconsistente con `services/api/.env` |

---

## 3. Variables críticas detectadas

### 3.1 Variables sensibles — presencia (sin mostrar valores)

| Variable | `services/api/.env` | `apps/web/.env` | `infra/.env` | `.env.example` (develop) | Riesgo |
|---|---|---|---|---|---|
| `DJANGO_SECRET_KEY` | presente | — | — | presente | ALTO si commiteado — no lo está |
| `POSTGRES_PASSWORD` | presente | — | — | presente | ALTO si commiteado — no lo está |
| `MP_ACCESS_TOKEN` | presente | — | — | presente | ALTO — comentario en .env indica "TEST credentials" |
| `MP_WEBHOOK_SECRET` | presente | — | — | presente | ALTO si commiteado — no lo está |
| `MFA_ENCRYPTION_KEY` | presente | — | — | presente | ALTO si commiteado — no lo está |
| `NGROK_AUTHTOKEN` | — | — | presente | — | MEDIO — token de cuenta ngrok |
| `GOOGLE_OAUTH_CLIENT_ID` | presente | presente | presente | presente | BAJO — Client ID es público por diseño OAuth |
| `EMAIL_HOST_PASSWORD` | presente | — | — | presente | ALTO si commiteado — no lo está |

### 3.2 Variables públicas / URLs

| Variable | `services/api/.env` | `infra/.env` | `apps/web/.env` | Observación |
|---|---|---|---|---|
| `FRONTEND_URL` | `http://localhost:3000` | `http://localhost:3000` | — | Consistente — dev local |
| `NEXT_PUBLIC_API_URL` | — | — | `http://localhost:8000` | Consistente — dev local |
| `NEXT_PUBLIC_BASE_URL` | `https://hopeless-janean-impuissant.ngrok-free.dev` ⚠ | `https://hopeless-janean-impuissant.ngrok-free.dev` ⚠ | `http://localhost:3000` | **Inconsistente** — ngrok en API .env y infra, local en web .env |
| `BASE_PUBLIC_URL` | `https://hopeless-janean-impuissant.ngrok-free.dev` ⚠ | `https://hopeless-janean-impuissant.ngrok-free.dev` ⚠ | — | URL de túnel dev activa — no es producción |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` (×2 ⚠) | — | — | **Duplicada** en `services/api/.env` |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:3000` (×2 ⚠) | — | — | **Duplicada** en `services/api/.env` |
| `DJANGO_DEBUG` | `True` (×2 ⚠) | `False` ⚠ | — | **Duplicada** en API .env; **inconsistente** con infra .env |
| `COOKIE_DOMAIN` | *(vacío)* | — | — | OK para dev local |
| `COOKIE_SECURE` | `False` | — | — | OK para dev local |
| `COOKIE_SAMESITE` | `Lax` | — | — | OK |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,mirubro-api,api` | — | — | OK para dev local |
| `PUBLIC_MENU_BASE_URL` | `http://localhost:3000` (×2 ⚠) | — | — | **Duplicada** en `services/api/.env` |
| `API_URL` | — | `http://localhost:8000` | — | Solo interpolación Docker |

---

## 4. Diferencias master vs develop

### Archivos que cambiaron entre master → develop

| Archivo | Estado | Descripción del cambio |
|---|---|---|
| `.gitignore` | M (modificado) | Reglas de ignore actualizadas |
| `apps/web/.env.example` | A (añadido en develop) | No existía en master |
| `services/api/.env.example` | A (añadido en develop) | No existía en master |
| `infra/docker-compose.yml` | M (modificado) | Cambios en servicios |
| `services/api/src/config/settings.py` | M (modificado) | Cambios de configuración |

### Variables públicas — master vs develop

Los archivos `.env` reales no están en Git (correctamente). La comparación se hace sobre los templates `.env.example`:

- **`master`**: No tiene `.env.example` en `services/api/` ni en `apps/web/`. Los desarrolladores en master no tienen template de referencia.
- **`develop`**: Tiene ambos `.env.example`. El de `services/api` cubre 32 variables. El de `apps/web` cubre 7 variables.

**Variables en `services/api/.env.example` (develop) ausentes en master:** todas (el archivo no existe en master).

### Variables sensibles — master vs develop

| Variable | master | develop |
|---|---|---|
| `DJANGO_SECRET_KEY` | ausente (no hay .env.example) | presente en .env.example (vacío, como template) |
| `MP_ACCESS_TOKEN` | ausente | presente en .env.example (vacío) |
| `MFA_ENCRYPTION_KEY` | ausente | presente en .env.example (vacío) |
| `EMAIL_HOST_PASSWORD` | ausente | presente en .env.example (vacío) |

> Aclaración: en ambas ramas los `.env` reales no están commiteados. Las diferencias son solo de templates.

---

## 5. Servicios que consumen cada env

| Servicio (Docker) | Archivo env usado | Mecanismo | Fuente |
|---|---|---|---|
| `api` (Django/Gunicorn) | `services/api/.env` | `env_file:` en docker-compose.yml | `infra/docker-compose.yml` línea 35 |
| `web` (Next.js) | `apps/web/.env` | `env_file:` en docker-compose.yml | `infra/docker-compose.yml` línea 60 |
| `celery-worker` | `services/api/.env` | `env_file:` en docker-compose.yml | `infra/docker-compose.yml` línea 84 |
| `celery-beat` | `services/api/.env` | `env_file:` en docker-compose.yml | `infra/docker-compose.yml` línea 101 |
| `postgres` | Inline en docker-compose.yml | `environment:` (interpola `${VAR:-default}`) | `infra/docker-compose.yml` línea 6 — las vars `POSTGRES_*` vienen de la shell o de `infra/.env` si se hace `docker compose --env-file infra/.env` |
| `redis` | No usa env file | — | No requiere configuración |
| `ngrok` | Inline en docker-compose.yml | `environment: NGROK_AUTHTOKEN` (interpola `${NGROK_AUTHTOKEN}`) | `infra/docker-compose.yml` línea 117 — viene de `infra/.env` |

> **Nota importante:** `infra/.env` no es cargado automáticamente por Docker Compose a menos que se llame con `--env-file infra/.env` o esté en el mismo directorio que `docker-compose.yml`. Docker Compose busca `.env` en el directorio de trabajo por defecto. Si se ejecuta `docker compose up` desde `infra/`, toma `infra/.env` para interpolación de variables `${}` en el YAML. Los `env_file:` de cada servicio siguen siendo los archivos específicos.

---

## 6. Hallazgos críticos

### 🔴 ALTO

Ninguno. No se detectaron credenciales productivas commiteadas.

### 🟡 MEDIO

**1. `services/api/.env` tiene variables duplicadas**

Los siguientes keys aparecen más de una vez en el mismo archivo. Django `load_dotenv` toma el primer valor encontrado — las segundas entradas son ignoradas silenciosamente:

- `DJANGO_DEBUG` (×2 — ambas `True`)
- `NEXT_PUBLIC_BASE_URL` (×2 — duplicado, además esta variable no corresponde al API)
- `PUBLIC_MENU_BASE_URL` (×2 — mismo valor)
- `CORS_ALLOWED_ORIGINS` (×2 — mismo valor)
- `CSRF_TRUSTED_ORIGINS` (×2 — mismo valor)

**2. `NEXT_PUBLIC_BASE_URL` en `services/api/.env`**

Es una variable del frontend de Next.js. Su presencia en el API `.env` no tiene efecto pero indica que alguien copió/pegó desde otro archivo. Puede generar confusión.

**3. `BASE_PUBLIC_URL` y `NEXT_PUBLIC_BASE_URL` apuntan a una URL de túnel ngrok activa**

```
BASE_PUBLIC_URL=https://hopeless-janean-impuissant.ngrok-free.dev
NEXT_PUBLIC_BASE_URL=https://hopeless-janean-impuissant.ngrok-free.dev
```

Estas son URLs de una sesión de túnel de desarrollo (no producción). No exponen credenciales. Sin embargo, si el túnel está activo, peticiones externas podrían alcanzar el API local. El túnel debería cerrarse cuando no se usa activamente.

**4. `infra/.env` tiene `DJANGO_DEBUG=False`**

El servicio `api` en Docker Compose usa `services/api/.env` (no `infra/.env`), por lo que este valor no afecta al API. Sin embargo, es confuso tener `DJANGO_DEBUG=False` en un archivo de entorno local de desarrollo.

**5. `.env.example` ausentes en `master`**

El branch `master` no tiene `services/api/.env.example` ni `apps/web/.env.example`. Un desarrollador que clone desde `master` no tiene ningún template de referencia sobre qué variables configurar.

### 🟢 BAJO / Positivo

- Las reglas de `.gitignore` son correctas y completas (`**/.env`, `**/.env.*`).
- Los templates `.env.example` están correctamente excluidos del ignore con `!**/.env.example`.
- Ningún `.env` real está commiteado en ninguna rama.
- Los comentarios en `services/api/.env` aclaran explícitamente que `MP_ACCESS_TOKEN` debe ser de TEST en desarrollo.
- El `services/api/.env.example` en `develop` cubre todas las variables críticas conocidas al momento.

---

## 7. Recomendación inicial

> **No implementar todavía.** Solo recomendaciones para la siguiente iteración.

### 7.1 Archivos a dejar de trackear (si aplica)

Nada que cambiar — ningún `.env` real está trackeado actualmente. Estado correcto.

### 7.2 Templates `.env.example` a crear / completar

| Acción | Prioridad |
|---|---|
| Mergear (o cherry-pick) `services/api/.env.example` y `apps/web/.env.example` a `master` | ALTA |
| Agregar al `services/api/.env.example` las variables nuevas de `notifications`: `EMAIL_PROVIDER`, `AWS_SES_REGION`, `AWS_SES_CONFIGURATION_SET`, `EMAIL_TRANSACTIONAL_ENABLED`, `EMAIL_MARKETING_ENABLED`, `SUPPORT_EMAIL`, `BILLING_EMAIL` | MEDIA |
| Crear `infra/.env.example` con las variables que Docker Compose interpola vía `${}`: `NGROK_AUTHTOKEN`, `BASE_PUBLIC_URL`, `FRONTEND_URL`, `DJANGO_DEBUG`, `NEXT_PUBLIC_BASE_URL`, `NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID`, `NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY`, `API_URL` | MEDIA |

### 7.3 Valores a mover a secretos externos (producción)

| Variable | Almacenamiento recomendado |
|---|---|
| `DJANGO_SECRET_KEY` | AWS Secrets Manager / Parameter Store |
| `POSTGRES_PASSWORD` | AWS Secrets Manager |
| `MP_ACCESS_TOKEN` | AWS Secrets Manager |
| `MP_WEBHOOK_SECRET` | AWS Secrets Manager |
| `MFA_ENCRYPTION_KEY` | AWS Secrets Manager |
| `EMAIL_HOST_PASSWORD` | AWS Secrets Manager (o eliminarlo si se usa SES+IAM Role) |
| `NGROK_AUTHTOKEN` | Solo local — no usar en producción |

### 7.4 Limpiezas recomendadas en `services/api/.env` (local, sin modificar en este PR)

- Eliminar la segunda aparición de `DJANGO_DEBUG`.
- Eliminar la segunda aparición de `PUBLIC_MENU_BASE_URL`.
- Eliminar la segunda aparición de `CORS_ALLOWED_ORIGINS` y `CSRF_TRUSTED_ORIGINS`.
- Eliminar `NEXT_PUBLIC_BASE_URL` (no corresponde al API).
- Resetear `BASE_PUBLIC_URL` a vacío cuando el túnel no esté activo.

### 7.5 Ramas con riesgo

| Rama | Riesgo |
|---|---|
| `master` | Sin `.env.example` — desarrolladores no tienen referencia |
| `develop` | Sin riesgo de credenciales — tiene los templates correctos |

### 7.6 Credenciales a rotar

No se detectaron credenciales commiteadas en ninguna rama. **No es necesario rotar nada** con la información actual.

Si en algún momento pasado algún `.env` estuvo commiteado (verificar con `git log -S "secret" --all`), rotar:
- `DJANGO_SECRET_KEY`
- `MP_ACCESS_TOKEN` / `MP_WEBHOOK_SECRET`
- `POSTGRES_PASSWORD`
- `MFA_ENCRYPTION_KEY`

---

## 8. Checklist

- [x] No se imprimieron secretos.
- [x] No se modificaron archivos (excepto la creación de este documento).
- [x] No se cambió `.env`.
- [x] No se hizo commit.
- [x] Se comparó `master` vs `develop`.
- [x] Se identificó qué servicios consumen cada env.
- [x] No se cambió de rama.
- [x] No se borraron archivos.
- [x] No se rotaron credenciales.
