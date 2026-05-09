# ENVIRONMENT_SETUP.md — Guía de entornos MiRubro

> **Última actualización:** 2026-05-09  
> **Rama de referencia:** `develop`

---

## 1. Archivos de entorno — mapa rápido

| Archivo | Quién lo lee | Propósito | Trackeado por Git |
|---|---|---|---|
| `services/api/.env` | Django, Celery (via `env_file:`) + `load_dotenv()` | Variables del backend | NO |
| `services/api/.env.example` | Referencia para devs | Template con defaults locales | SI |
| `apps/web/.env` | Next.js (via `env_file:`) | Variables del frontend | NO |
| `apps/web/.env.example` | Referencia para devs | Template con defaults locales | SI |
| `infra/.env` | Docker Compose (interpolación `${}`) | Resuelve `${VAR:-default}` en el YAML | NO |
| `infra/.env.example` | Referencia para devs | Template con defaults locales | SI |
| `apps/web/.env.local` | Next.js (`next dev` sin Docker) | Override local para dev sin Docker | NO |

---

## 2. Setup inicial — desarrollo local

```bash
# 1. Clonar el repo
git clone https://github.com/LucasMargets11/mirubrodigital.git
cd mirubrodigital
git checkout develop

# 2. Copiar templates
cp services/api/.env.example services/api/.env
cp apps/web/.env.example apps/web/.env
cp infra/.env.example infra/.env

# 3. Completar los campos REQUIRED en services/api/.env:
#    - DJANGO_SECRET_KEY  (ver instrucción de generación en el archivo)
#    - POSTGRES_PASSWORD
#    - MFA_ENCRYPTION_KEY  (ver instrucción de generación en el archivo)
#    - MP_ACCESS_TOKEN     (credenciales de TEST desde mercadopago.com.ar)
#    - MP_WEBHOOK_SECRET

# 4. Levantar el stack
npm run dev
# → docker compose -f infra/docker-compose.yml up --build
# → Docker carga infra/.env para interpolación ${}
# → Cada servicio usa su propio env_file
```

---

## 3. Entornos disponibles

### 3.1 Desarrollo local (sin webhooks)

```bash
npm run dev
# Frontend: http://localhost:3000
# API:      http://localhost:8000
# Admin:    http://localhost:8000/admin/

# NEXT_PUBLIC_* están forzadas a localhost por docker-compose.override.yml
# (safety net — invalida cualquier URL de ngrok en infra/.env)
```

### 3.2 Desarrollo local — API sin Docker

```bash
npm run dev:api
# cd services/api && python manage.py runserver 0.0.0.0:8000
# Lee services/api/.env via load_dotenv() en settings.py
```

### 3.3 Desarrollo local — Frontend sin Docker

```bash
npm run dev:web
# → next dev
# Lee apps/web/.env.local (mayor prioridad) y luego apps/web/.env
# NO usa Docker, NO lee apps/web/.env desde docker-compose
```

### 3.4 Con túnel ngrok (webhooks de MercadoPago)

> ⚠️ Revertir los valores al terminar la sesión. Ver pasos más abajo.

```bash
# 1. Asegurarse de tener NGROK_AUTHTOKEN en infra/.env
#    Obtener en: https://dashboard.ngrok.com/authtokens

# 2. Levantar stack con el perfil tunnel
docker compose -f infra/docker-compose.yml --profile tunnel up

# 3. Obtener la URL del túnel
docker compose -f infra/docker-compose.yml logs ngrok
# Buscar: url=https://abc123.ngrok-free.app

# 4. Pegar la URL en services/api/.env
#    BASE_PUBLIC_URL=https://abc123.ngrok-free.app
#    (también en infra/.env si se necesita en compose)

# 5. Reiniciar el API
docker compose -f infra/docker-compose.yml restart api

# 6. Configurar el webhook en MP con la misma URL:
#    https://abc123.ngrok-free.app/api/v1/billing/mercadopago/webhook/

# ── Al terminar la sesión de ngrok ──────────────────────────────────────────
# Revertir services/api/.env:
#   BASE_PUBLIC_URL=        ← dejar vacío
# Revertir infra/.env (si se editó):
#   BASE_PUBLIC_URL=        ← dejar vacío
#   NEXT_PUBLIC_BASE_URL=http://localhost:3000
# Reiniciar: docker compose -f infra/docker-compose.yml up api
```

---

## 4. Cómo funciona la precedencia de variables

### 4.1 Backend Django

```
1. Variables de entorno del proceso (shell export, ECS task definition)  ← gana siempre
2. docker-compose env_file: ../services/api/.env                         ← en Docker
3. load_dotenv() en settings.py (lee el mismo services/api/.env)         ← sin Docker
   (python-dotenv NO sobreescribe vars ya presentes en el proceso)
4. os.getenv('VAR', 'valor_por_defecto') en settings.py                  ← fallback
```

**Regla simple:** En Docker, `env_file:` gana. Sin Docker, `load_dotenv()` gana. Ambos leen el mismo archivo.

### 4.2 Frontend Next.js

#### Variables `NEXT_PUBLIC_*` — se embeben en build time

```
1. build.args del compose (o export de shell)                            ← baked en el JS
   En develop: docker-compose.override.yml fuerza localhost:3000/8000
   En master sin override: docker-compose.yml ${VAR:-localhost:8000}
```

> **Importante:** Si cambiás `NEXT_PUBLIC_*` en `.env` **después** de haber hecho el build, el cambio NO se aplica en el browser hasta que hagas:
> ```bash
> docker compose -f infra/docker-compose.yml build web
> docker compose -f infra/docker-compose.yml up web
> ```

#### Variables runtime

```
1. environment: del compose (Mayor prioridad)
2. env_file: ../apps/web/.env
3. .env.local (solo next dev sin Docker — mayor prioridad que .env)
4. .env (apps/web/.env — menor prioridad entre archivos)
```

### 4.3 Docker Compose — interpolación `${}`

```
1. Variables del proceso (export en shell)
2. infra/.env (automático, porque es el directorio del compose file)
3. Fallback ${VAR:-valor_por_defecto} en el YAML
```

El archivo `infra/.env.example` documenta exactamente qué variables necesita Docker Compose para interpolación.

### 4.4 `docker-compose.override.yml` — safety net local

Docker Compose fusiona automáticamente `docker-compose.override.yml` sobre `docker-compose.yml` cuando ambos están en el mismo directorio.

El override local **fuerza** las URLs del frontend a `localhost` con valores literales (no interpolados), neutralizando cualquier URL de ngrok que pueda estar en `infra/.env`. Esto garantiza que `npm run dev` siempre arranque con URLs locales.

---

## 5. Variables `NEXT_PUBLIC_*` — guía rápida

| Variable | Default local | Con ngrok | Producción |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `http://localhost:8000` (no cambia) | `https://www.mirubro.com` |
| `NEXT_PUBLIC_BASE_URL` | `http://localhost:3000` | `http://localhost:3000` (no cambia) | `https://www.mirubro.com` |

Estas variables van en:
- `apps/web/.env` (valor runtime)
- `build.args` del compose (valor baked en el bundle JS)
- `infra/.env` como fuente de interpolación para el compose

---

## 6. Variables de URL del backend — guía rápida

| Variable | Default local | Con ngrok activo | Producción |
|---|---|---|---|
| `FRONTEND_URL` | `http://localhost:3000` | `http://localhost:3000` (no cambia) | `https://www.mirubro.com` |
| `PUBLIC_MENU_BASE_URL` | `http://localhost:3000` | `http://localhost:3000` (no cambia) | `https://www.mirubro.com` |
| `BASE_PUBLIC_URL` | *(vacío)* | `https://TU-URL.ngrok-free.app` | `https://api.mirubro.com` |

`BASE_PUBLIC_URL` es la única variable que debe cambiar cuando se activa ngrok. Cuando está seteada y `DEBUG=True`, `settings.py` auto-añade el hostname de ngrok a `ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` — no hace falta configurarlos manualmente.

---

## 7. Producción — principios

> **Regla:** Producción NUNCA debe usar `.env` locales.

En producción (EC2/ECS):

1. **Secretos** (`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `MP_ACCESS_TOKEN`, `MFA_ENCRYPTION_KEY`) → AWS Secrets Manager, inyectados como variables de entorno en la task definition de ECS.
2. **URLs públicas** (`FRONTEND_URL`, `BASE_PUBLIC_URL`, `NEXT_PUBLIC_*`) → hardcodeados en el compose de producción o en las variables de entorno del servidor.
3. **Email** → `EMAIL_PROVIDER=amazon_ses` con IAM Role. No se necesitan access keys.
4. **Ngrok** → nunca en producción.
5. **`DJANGO_DEBUG=False`** → obligatorio.

---

## 8. Limpieza manual recomendada (services/api/.env local)

> Solo necesario si se creó el `.env` local antes de este PR. No son cambios en el repo.

Editar manualmente `services/api/.env` en el disco local para:

- **Eliminar duplicados:** si aparece dos veces `DJANGO_DEBUG`, `PUBLIC_MENU_BASE_URL`, `CORS_ALLOWED_ORIGINS` o `CSRF_TRUSTED_ORIGINS`, eliminar la segunda aparición.
- **Sacar variable de frontend del env del backend:** eliminar `NEXT_PUBLIC_BASE_URL` del archivo `services/api/.env` (no corresponde al backend, no tiene efecto pero genera confusión).
- **Vaciar `BASE_PUBLIC_URL`** si no hay una sesión de ngrok activa:
  ```
  BASE_PUBLIC_URL=
  ```

Ninguna de estas acciones requiere reiniciar Docker — Django lee el archivo al arrancar el proceso.

---

## 9. Checklist setup nuevo desarrollador

- [ ] Clonar desde `develop` (no `master` — `master` no tiene `.env.example`)
- [ ] `cp services/api/.env.example services/api/.env`
- [ ] `cp apps/web/.env.example apps/web/.env`
- [ ] `cp infra/.env.example infra/.env`
- [ ] Completar `DJANGO_SECRET_KEY` en `services/api/.env`
- [ ] Completar `POSTGRES_PASSWORD` en `services/api/.env`
- [ ] Completar `MFA_ENCRYPTION_KEY` en `services/api/.env`
- [ ] Completar `MP_ACCESS_TOKEN` con credenciales **TEST** de MercadoPago
- [ ] Completar `GOOGLE_OAUTH_CLIENT_ID` (si se usa OAuth)
- [ ] `npm run dev`
- [ ] Verificar que `http://localhost:3000` carga el frontend
- [ ] Verificar que `http://localhost:8000/api/v1/health/` responde
