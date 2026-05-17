# Root cause — env cambia entre localhost, ngrok y mirubro.com

**Fecha:** 2026-05-09  
**Rama analizada:** `develop` comparada con `master`  
**Auditor:** Senior DevOps / Copilot  
**Premisa:** Los `.env` reales no están trackeados por Git (confirmado). No se modificó nada.

---

## 1. Resumen ejecutivo

Hay **cuatro causas raíz independientes** que en combinación explican por qué aparecen `localhost`, `ngrok` y `mirubro.com` en distintos contextos:

1. **`infra/docker-compose.yml` en `master` tenía `https://www.mirubro.com` hardcodeado** en los `build.args` y `environment` del servicio `web`. Cualquier imagen construida desde `master` tenía esta URL baked-in en el bundle de JavaScript. Fue corregido en `develop` usando variables `${VAR:-default}`.

2. **Cuando se activa un túnel ngrok para webhooks de MercadoPago**, el desarrollador sigue las instrucciones del propio `docker-compose.dev-backup.yml` y edita manualmente `services/api/.env` (y también `infra/.env`). Nadie revierte esas URLs cuando el túnel se cierra — quedan "pegadas" en los archivos `.env` locales.

3. **`infra/.env` es la fuente de interpolación de Docker Compose para `${}`**. Cuando `npm run dev` ejecuta `docker compose -f infra/docker-compose.yml`, Docker Compose carga `infra/.env` (el directorio del compose file) para resolver `${NEXT_PUBLIC_BASE_URL:-...}`. Si `infra/.env` tiene la URL de ngrok, esa URL entra al build.

4. **`NEXT_PUBLIC_*` se bake en el bundle de Next.js en tiempo de `build`**. Cambiar el `.env` después del build no tiene efecto hasta que se reconstruya la imagen. El desarrollador ve una URL en el browser que ya no está en el `.env` actual.

**No es un problema de Git.** Git no trackea ni sobreescribe `.env` reales entre ramas. Los `.env` viven solo en disco y cambian solo por edición manual.

---

## 2. Respuesta corta

| Pregunta | Respuesta |
|---|---|
| ¿Git está pisando `.env` reales entre ramas? | **No.** Ningún `.env` real está trackeado. Git no los modifica. |
| ¿Qué archivo afecta al backend? | `services/api/.env` — leído dos veces: por `load_dotenv()` en `settings.py` Y por Docker Compose `env_file:` |
| ¿Qué archivo afecta al frontend (Next.js)? | `apps/web/.env` (via Docker `env_file:`), `apps/web/.env.local` (solo en `next dev` local), y los `build.args` del `docker-compose.yml` (baked en el bundle) |
| ¿Qué rol cumple `infra/.env`? | Fuente de interpolación de variables `${}` en el YAML de Docker Compose (incluyendo `NEXT_PUBLIC_BASE_URL`, `NGROK_AUTHTOKEN`, etc.) |
| ¿Por qué aparece `localhost`? | Estado normal. Defaults en `settings.py`, en `apps/web/.env` y en el fallback `${VAR:-http://localhost:8000}` del compose |
| ¿Por qué aparece la URL de ngrok? | El desarrollador editó `services/api/.env` e `infra/.env` para configurar webhooks de MP (siguiendo las instrucciones del codebase) y no revirtió los valores |
| ¿Por qué aparece `mirubro.com`? | `infra/docker-compose.yml` en `master` tenía `NEXT_PUBLIC_API_URL: https://www.mirubro.com` y `NEXT_PUBLIC_BASE_URL: https://www.mirubro.com` hardcodeados (corregido en `develop`) |

---

## 3. Evidencia

| # | Evidencia | Archivo / comando | Impacto |
|---|---|---|---|
| E1 | `master` compose tiene `NEXT_PUBLIC_API_URL: https://www.mirubro.com` y `NEXT_PUBLIC_BASE_URL: https://www.mirubro.com` en `build.args` y `environment` del servicio `web` | `git diff master...develop -- infra/docker-compose.yml` | Imagen de Next.js construida desde `master` tiene mirubro.com baked-in |
| E2 | `develop` corrigió con `${NEXT_PUBLIC_API_URL:-http://localhost:8000}` (parametrizado) | `git diff master...develop -- infra/docker-compose.yml` | En `develop`, el valor viene de `infra/.env` o del fallback |
| E3 | `settings.py` line 9: `load_dotenv(BASE_DIR.parent / '.env')` resuelve a `services/api/.env` | `services/api/src/config/settings.py:8-9` | Django carga explícitamente el mismo archivo que Docker Compose inyecta vía `env_file:` |
| E4 | `settings.py` lines 25-31: si `BASE_PUBLIC_URL` está seteado, su hostname se auto-agrega a `ALLOWED_HOSTS` | `settings.py:25-31` | El host ngrok funciona automáticamente sin configuración explícita |
| E5 | `settings.py` lines 170-174: si `DEBUG=True` y `BASE_PUBLIC_URL` está seteado, su origen se auto-agrega a `CORS_ALLOWED_ORIGINS` | `settings.py:170-174` | CORS para ngrok se abre automáticamente cuando `DEBUG=True` |
| E6 | `infra/.env` tiene las mismas variables que docker-compose interpola: `NEXT_PUBLIC_BASE_URL`, `BASE_PUBLIC_URL`, `NGROK_AUTHTOKEN`, `DJANGO_DEBUG`, etc. | `infra\.env keys` audit | Cuando Docker Compose carga `infra/.env`, si esas vars tienen URLs de ngrok, entran al build |
| E7 | `docker-compose.dev-backup.yml` (comentario en el servicio ngrok): *"Then update services/api/.env: `BASE_PUBLIC_URL=https://xxxx.ngrok-free.app`"* | `infra/docker-compose.dev-backup.yml:ngrok service comments` | El workflow de ngrok INSTRUCCIONALMENTE edita `services/api/.env` → el dev no revirtió |
| E8 | `infra/docker-compose.override.yml` existe solo en `develop` (no en `master`) y pone `NEXT_PUBLIC_BASE_URL: http://localhost:3000` (literal, no interpolado) en `build.args` y `environment` | `git show master:infra/docker-compose.override.yml → fatal` | En `develop`, el override neutraliza el ngrok de `infra/.env` para el frontend. En `master`, no existe ese safety net |
| E9 | `apps/web/.env.local` tiene `NEXT_PUBLIC_API_URL` (mismo que `apps/web/.env`). En Next.js, `.env.local` tiene mayor prioridad que `.env` | `apps/web/.env` y `apps/web/.env.local` comparados | Conflicto silencioso si los valores divergen en el futuro |
| E10 | `services/api/.env` tiene `NEXT_PUBLIC_BASE_URL` (variable de frontend) — no afecta al backend pero genera confusión | `services/api/.env keys` audit | Conceptual: frontend var en env de backend |
| E11 | `services/api/.env` tiene `DJANGO_DEBUG`, `PUBLIC_MENU_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` duplicados | `services/api/.env duplicate check` | `python-dotenv` usa el PRIMER valor — mismo valor en ambas ocurrencias, sin impacto funcional actual |
| E12 | En código productivo Next.js: `metadataBase: new URL('https://www.mirubro.com')` en `layout.tsx`, `SITE_URL = 'https://www.mirubro.com'` en múltiples pages, `sitemap.xml`, `robots.ts` | grep code search | **Intencional** — SEO/metadata tiene mirubro.com hardcodeado. No es un bug, es correcto |
| E13 | No se encontraron scripts que copien o sobreescriban `.env` automáticamente | Shell scripts audit (`.sh`, `.ps1`, `.bat`, `Makefile`) | No hay automatización → los cambios son 100% manuales |
| E14 | `npm run dev` → `docker compose -f infra/docker-compose.yml up --build` (desde raíz del repo) | `package.json scripts` | Docker Compose usa `infra/` como project directory → carga `infra/.env` para interpolación Y auto-merge `infra/docker-compose.override.yml` |

---

## 4. Precedencia de variables

### 4.1 Backend (Django)

Orden de precedencia (mayor a menor):

```
1. Variables de entorno del proceso/shell (más alto)
   ↓ (si no está en el proceso)
2. Docker Compose env_file: ../services/api/.env  (en Docker)
   ↓ (si no está en env_file)
3. load_dotenv(services/api/.env) en settings.py  (solo si la var NO fue pre-seteada)
   ↓ (si no está en el archivo .env)
4. os.getenv('VAR', 'default_en_settings.py')     (valor por defecto hardcodeado)
```

**Observación crítica:** En Docker, `env_file:` inyecta las vars ANTES de que Python arranque. Cuando `settings.py` llama a `load_dotenv()`, esas vars ya existen en el entorno del proceso, y `python-dotenv` por defecto NO sobreescribe vars existentes. Resultado: en Docker, `env_file:` gana siempre. En local (`npm run dev:api`), solo `load_dotenv` opera.

**Como ambas fuentes leen el mismo archivo** (`services/api/.env`), el valor es siempre el mismo — pero la ilusión es que el archivo "se carga dos veces".

**Efecto especial de `BASE_PUBLIC_URL`:** Si está seteado (no vacío y sin `xxxx`):
- El hostname ngrok se auto-añade a `ALLOWED_HOSTS` (lines 25-31)
- El origin ngrok se auto-añade a `CORS_ALLOWED_ORIGINS` cuando `DEBUG=True` (lines 170-174)

### 4.2 Frontend (Next.js)

#### En Docker (vía `npm run dev` o `docker compose up web`)

```
1. build.args en docker-compose.yml/override (baked en el bundle JS — solo NEXT_PUBLIC_*)
   → en develop: docker-compose.override.yml pisa con http://localhost:3000 (literal)
   → en master: docker-compose.yml tenía https://www.mirubro.com (hardcoded)
   ↓
2. environment: en docker-compose.yml/override (runtime, overrides env_file)
   → mismo comportamiento que build.args para las vars NEXT_PUBLIC_*
   ↓
3. env_file: ../apps/web/.env (runtime, menor prioridad que environment:)
   ↓
4. Defaults de Next.js / next.config.mjs
```

**Nota sobre `NEXT_PUBLIC_*`:** Estas variables se inyectan al bundle en tiempo de `next build`. El valor en runtime no cambia lo que está en el JavaScript del browser. **Requieren rebuild para cambiar.**

#### En local sin Docker (`npm run dev:web` → `next dev`)

```
1. process.env del shell
   ↓
2. .env.local (más alta prioridad entre archivos)
   ↓
3. .env.development.local (no existe actualmente)
   ↓
4. .env.development (no existe actualmente)
   ↓
5. .env (apps/web/.env — menor prioridad)
```

`apps/web/.env.local` tiene `NEXT_PUBLIC_API_URL` y `NEXT_PUBLIC_API_BASE_URL`, que sombrea silenciosamente `apps/web/.env` si los valores divergen.

### 4.3 Docker Compose (interpolación `${}`)

Cuando se ejecuta `docker compose -f infra/docker-compose.yml [up]`:

1. Docker Compose determina su **project directory** como el directorio que contiene el compose file → `infra/`
2. Busca y carga `infra/.env` para resolver variables `${VAR}` y `${VAR:-default}` en el YAML
3. Auto-merge de `infra/docker-compose.override.yml` (solo existe en `develop`) — el override tiene **mayor prioridad** que el main compose file

**Jerarquía de merge en `develop`:**

```
infra/docker-compose.yml      (base)
       ↓ merged by
infra/docker-compose.override.yml  (mayor prioridad para web service)
       ↑
infra/.env                    (fuente de interpolación ${} para ambos archivos)
```

En `master` no existe `docker-compose.override.yml` → solo se usa el compose principal.

---

## 5. Scripts o procesos que pisan env

| Script/proceso | Evidencia | Riesgo |
|---|---|---|
| **Ninguno automatizado encontrado** | Búsqueda en `.sh`, `.ps1`, `.bat`, `Makefile` no arrojó scripts que copien/sobreescriban `.env` | — |
| `infra/terraform/bootstrap/bootstrap.sh` | No toca archivos `.env` — solo provisiona infraestructura AWS | BAJO |
| `services/api/docker-entrypoint.sh` | No toca `.env` — solo corre `migrate` y `collectstatic` condicionalmente | BAJO |
| **Workflow manual ngrok** (documentado en el repo) | El comentario en `docker-compose.dev-backup.yml` dice explícitamente: *"update services/api/.env: BASE_PUBLIC_URL=https://xxxx"* | ALTO — es el workflow oficial pero no hay script de reversión |
| `docs/README.md` | Dice `cp apps/web/.env.example apps/web/.env` y `cp services/api/.env.example services/api/.env` — solo en setup inicial | BAJO — copy única, no automática |

**Conclusión:** No existe automatización que sobreescriba `.env`. Los cambios son 100% manuales por el desarrollador.

---

## 6. Variables conflictivas

| Variable | Local esperado | Ngrok (tunnel activo) | Producción | Archivo actual | Riesgo |
|---|---|---|---|---|---|
| `BASE_PUBLIC_URL` | `(vacío)` | URL ngrok | `https://api.mirubro.com` | `services/api/.env`: ngrok URL activa ⚠ | MEDIO — ngrok URL quedó de una sesión anterior |
| `NEXT_PUBLIC_BASE_URL` | `http://localhost:3000` | URL ngrok | `https://www.mirubro.com` | `infra/.env`: ngrok URL ⚠ / `apps/web/.env`: localhost / `services/api/.env`: ngrok URL (var de frontend en backend env ⚠) | ALTO — tres archivos, tres valores distintos |
| `FRONTEND_URL` | `http://localhost:3000` | URL ngrok | `https://www.mirubro.com` | `services/api/.env`: localhost | OK |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `http://localhost:8000` | `https://www.mirubro.com` | `apps/web/.env`: localhost / `apps/web/.env.local`: localhost | OK local; en `master` compose tenía mirubro.com ⚠ |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | `http://localhost:3000,https://ngrok-url` | `https://www.mirubro.com` | `services/api/.env`: localhost (×2 duplicado) | BAJO — Django auto-añade ngrok vía `BASE_PUBLIC_URL` |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:3000` | `http://localhost:3000` | `https://www.mirubro.com` | `services/api/.env`: localhost (×2 duplicado) | BAJO |
| `DJANGO_DEBUG` | `True` | `True` | `False` | `services/api/.env`: `True` (×2 duplicado) / `infra/.env`: `False` ⚠ | MEDIO — inconsistencia, pero la fuente real del backend es `services/api/.env` |
| `PUBLIC_MENU_BASE_URL` | `http://localhost:3000` | URL ngrok | `https://www.mirubro.com` | `services/api/.env`: localhost (×2 duplicado) | BAJO |

> **No se incluyen secretos.** Todas las columnas muestran solo URLs públicas.

---

## 7. Causa raíz

Se identificaron **5 causas reales**, ordenadas por impacto:

### 7.1 ⭐ PRIMARIA — `master` tiene `mirubro.com` hardcodeado en el compose

**Causa:** `infra/docker-compose.yml` en `master` tenía `NEXT_PUBLIC_API_URL: https://www.mirubro.com` y `NEXT_PUBLIC_BASE_URL: https://www.mirubro.com` en `build.args` **y** en `environment` del servicio `web`. No hay interpolación — son strings literales.

**Efecto:** Cualquier build desde `master` genera una imagen Next.js con mirubro.com baked-in en el JS bundle. Runtime changes a `.env` no sirven de nada hasta rebuild.

**Estado:** Corregido en `develop`. Pendiente merge a `master`.

### 7.2 ⭐ PRIMARIA — El mismo `.env` local sirve para múltiples contextos sin separación

**Causa:** No existe separación `.env.local` / `.env.ngrok` / `.env.production`. Hay **un solo** `services/api/.env` y **un solo** `infra/.env` local que un desarrollador edita manualmente para todos los contextos (local, ngrok, y potencialmente staging).

**Efecto:** Cuando se activa ngrok, el desarrollador edita `services/api/.env` e `infra/.env` con la URL del túnel. Cuando el túnel se cierra, nadie revierte los valores. La URL de ngrok queda "stuck" en ambos archivos hasta que el desarrollador los edita manualmente de vuelta.

**Evidencia directa:** Estado actual de `services/api/.env` y `infra/.env` tienen URL ngrok activa (`https://hopeless-janean-impuissant.ngrok-free.dev`).

### 7.3 SECUNDARIA — `NEXT_PUBLIC_*` se bake en el bundle (runtime change ≠ efectivo)

**Causa:** Next.js bake las variables `NEXT_PUBLIC_*` en el JavaScript estático durante `next build`. Estas no cambian en runtime.

**Efecto:** Un desarrollador que cambió el `.env` después del build sigue viendo la URL anterior en el browser hasta que haga `docker compose build web` (o `npm run build`).

### 7.4 SECUNDARIA — `docker-compose.override.yml` solo existe en `develop` y no neutraliza el backend

**Causa:** El override file (`infra/docker-compose.override.yml`) fue añadido en `develop` como safety net para forzar localhost en el frontend. No existe en `master`.

**Efecto en `develop`:** El override neutraliza el ngrok de `infra/.env` para el servicio `web` (frontend). PERO no afecta `services/api/.env` — el backend sigue teniendo `BASE_PUBLIC_URL=ngrok-url`. Resultado: frontend con localhost, backend con ngrok → inconsistencia.

**Efecto en `master`:** Sin override, el compose principal (con mirubro.com hardcoded) domina todo.

### 7.5 SECUNDARIA — `infra/.env` es la fuente de interpolación y tiene URL ngrok

**Causa:** Docker Compose usa `infra/` como project directory (el directorio del compose file). Carga `infra/.env` para resolver `${VAR}` en el YAML. `infra/.env` actualmente tiene `NEXT_PUBLIC_BASE_URL=ngrok-url` (misma sesión que el API).

**Efecto:** En `develop` sin override (o si el override no existe), la URL ngrok de `infra/.env` entraría al build del frontend. Con el override activo, el override gana.

---

## 8. Solución propuesta por PRs

### PR A — Normalizar templates (prerequisito para todo lo demás)

**Archivos a modificar:**
- Crear `infra/.env.example` con: `NGROK_AUTHTOKEN=`, `BASE_PUBLIC_URL=`, `FRONTEND_URL=http://localhost:3000`, `DJANGO_DEBUG=True`, `NEXT_PUBLIC_BASE_URL=http://localhost:3000`, `NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID=`, `NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY=false`, `API_URL=http://localhost:8000`
- Actualizar `services/api/.env.example`: agregar `EMAIL_PROVIDER=django`, `AWS_SES_REGION=sa-east-1`, `AWS_SES_CONFIGURATION_SET=`, `EMAIL_TRANSACTIONAL_ENABLED=true`, `EMAIL_MARKETING_ENABLED=false`, `SUPPORT_EMAIL=`, `BILLING_EMAIL=`
- Mergear `.env.example` a `master`

**No cambia nada funcional. Solo documentación de referencia.**

### PR B — Separar local / ngrok / production en templates

**Archivos a crear (templates de referencia, no archivos activos):**

```
services/api/.env.local.example     # BASE_PUBLIC_URL=(vacío), FRONTEND_URL=http://localhost:3000
services/api/.env.ngrok.example     # BASE_PUBLIC_URL=https://REPLACE.ngrok-free.app, FRONTEND_URL=http://localhost:3000
infra/.env.local.example            # NEXT_PUBLIC_BASE_URL=http://localhost:3000, BASE_PUBLIC_URL=
infra/.env.ngrok.example            # NEXT_PUBLIC_BASE_URL=https://REPLACE.ngrok-free.app, BASE_PUBLIC_URL=https://REPLACE.ngrok-free.app
```

**Instrucción de uso:**
- Desarrollo local: `cp services/api/.env.local.example services/api/.env` + `cp infra/.env.local.example infra/.env`
- Ngrok (MP webhooks): `cp services/api/.env.ngrok.example services/api/.env`, editar URL, luego **revertir** con el `.env.local.example` al terminar

### PR C — Limpiar env local (sin tocar código)

**Solo documentación:** instrucciones para que el desarrollador ejecute manualmente:
- Resetear `BASE_PUBLIC_URL=` (vacío) en `services/api/.env`
- Resetear `NEXT_PUBLIC_BASE_URL=http://localhost:3000` en `infra/.env`
- Resetear `BASE_PUBLIC_URL=` (vacío) en `infra/.env`
- Eliminar duplicados en `services/api/.env`: segunda aparición de `DJANGO_DEBUG`, `PUBLIC_MENU_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`
- Mover `NEXT_PUBLIC_BASE_URL` de `services/api/.env` al `infra/.env` (donde corresponde)

### PR D — Compose explícito y override para producción

**Archivos a modificar:**
- Crear `infra/docker-compose.prod.yml` (compose file de producción separado) con variables inyectadas desde servidor / Secrets Manager, sin `env_file:` apuntando a archivos locales
- Documentar en `docs/README.md`:
  - `npm run dev` → usa `docker-compose.yml` + `docker-compose.override.yml` → siempre localhost para frontend
  - `npm run dev:tunnel` → usar `infra/.env.ngrok.example` como `infra/.env` → ngrok URLs
  - Producción → usar `docker-compose.prod.yml` con variables de entorno del servidor

**Alternativa más simple:** agregar script `npm run dev:ngrok` que corra:
```
docker compose -f infra/docker-compose.yml -f infra/docker-compose.ngrok.yml up
```
donde `docker-compose.ngrok.yml` lee `BASE_PUBLIC_URL` de `infra/.env` (sin override de localhost).

### PR E — Eliminar hardcoding de mirubro.com en compose (ya hecho en develop, falta merge)

**Acción:** Asegurarse de que el diff de `docker-compose.yml` entre `develop` y `master` llegue a `master`. El cambio ya está en `develop`:

```yaml
# master (problema):
NEXT_PUBLIC_API_URL: https://www.mirubro.com
NEXT_PUBLIC_BASE_URL: https://www.mirubro.com

# develop (correcto):
NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
NEXT_PUBLIC_BASE_URL: ${NEXT_PUBLIC_BASE_URL:-http://localhost:3000}
```

### PR F — Secret management en producción

**Principio:** Producción NUNCA debe usar archivos `.env` locales.

| Variable | Mecanismo en producción |
|---|---|
| `DJANGO_SECRET_KEY` | AWS Secrets Manager → ECS task definition |
| `POSTGRES_PASSWORD` | AWS Secrets Manager → ECS task definition |
| `MP_ACCESS_TOKEN` | AWS Secrets Manager |
| `MP_WEBHOOK_SECRET` | AWS Secrets Manager |
| `MFA_ENCRYPTION_KEY` | AWS Secrets Manager |
| `NEXT_PUBLIC_API_URL` | Hardcodeado en `docker-compose.prod.yml` con la URL real (no un `.env`) |
| `NEXT_PUBLIC_BASE_URL` | Hardcodeado en `docker-compose.prod.yml` |
| `BASE_PUBLIC_URL` | Variable de entorno del servidor / ECS task definition |
| `NGROK_AUTHTOKEN` | Solo local. Jamás en producción. |

---

## 9. Diagrama de flujo de las URLs

```
┌─────────────────────────────────────────────────────────────────┐
│                      npm run dev (raíz)                         │
│  docker compose -f infra/docker-compose.yml up --build          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                 ┌─────────────▼──────────────┐
                 │   Docker Compose carga      │
                 │   infra/.env (project dir)  │
                 │   ← NEXT_PUBLIC_BASE_URL    │
                 │   ← BASE_PUBLIC_URL         │
                 │   ← NGROK_AUTHTOKEN         │
                 └─────────────┬──────────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                  │
    ┌─────────▼──────────┐            ┌──────────▼──────────┐
    │  docker-compose.yml │            │ docker-compose.     │
    │  (base)             │  MERGED    │ override.yml        │
    │  ${NEXT_PUBLIC_BASE │ ─────────► │ (SOLO en develop)   │
    │  _URL:-localhost}   │            │ http://localhost:3000│
    │  (o mirubro.com     │            │ (literal, wins)     │
    │   en master)        │            └──────────┬──────────┘
    └─────────────────────┘                       │
                                    ┌─────────────▼─────────────┐
                                    │    web service container   │
                                    │  build.args (baked in JS) │
                                    │  environment (runtime)    │
                                    │                           │
                                    │ DEVELOP: localhost:3000   │
                                    │ MASTER:  mirubro.com ⚠   │
                                    └───────────────────────────┘

    ┌───────────────────────────────────────┐
    │          api service container        │
    │  env_file: ../services/api/.env       │
    │  + load_dotenv() en settings.py       │
    │                                       │
    │  BASE_PUBLIC_URL=ngrok-url (actual) ⚠ │
    │  → ALLOWED_HOSTS += ngrok hostname    │
    │  → CORS_ALLOWED_ORIGINS += ngrok      │
    └───────────────────────────────────────┘
```

---

## 10. Checklist de verificación

- [x] No se imprimieron secretos.
- [x] No se modificaron archivos `.env`.
- [x] No se modificó código.
- [x] No se hicieron commits.
- [x] Se revisaron todos los scripts (`.sh`, `.ps1`, `.bat`, `Makefile`).
- [x] Se revisaron todos los Docker Compose files (3 encontrados).
- [x] Se documentó la precedencia de env en backend, frontend y compose.
- [x] Se identificó qué archivo es la fuente de interpolación `${}`.
- [x] Se verificó qué existe en `master` vs `develop`.
- [x] Se identificaron las 5 causas raíz.
- [x] Se propusieron PRs separados con scope quirúrgico.
- [x] Se confirmó que no hay automatización que sobreescriba `.env`.
