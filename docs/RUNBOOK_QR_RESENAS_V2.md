# Runbook Operativo — Release QR de Reseñas v2

| Campo | Valor |
|---|---|
| **Producto** | QR de Reseñas (MiRubro) |
| **Versión runbook** | 2.0 |
| **Fecha de redacción** | 2026-04-14 |
| **Módulos backend** | `apps.reviews` · `apps.billing.reviews_views` |
| **Módulo frontend** | `apps/web/src/app/app/resenas/` · `apps/web/src/app/r/[slug]/` |
| **Tests automatizados** | 268 (246 reviews + 22 billing upgrade/downgrade) |

---

## 0. Resumen Ejecutivo de Correcciones vs V1

| # | Corrección | Detalle |
|---|-----------|---------|
| 1 | **Precio Pro: $35.000 → $40.000** | `generated/pricing.json` decía 35000; frontend `plans.ts` ya tenía 40000. Se corrigió `pricing.json` para alinear. Backend ahora cobra $40.000 vía MercadoPago. |
| 2 | **Plan codes unificados** | V1 mezclaba `reviews_pro`, `qr_reviews_pro`, `qr_reviews`. V2 usa nomenclatura canónica: `qr_reviews` (legacy/bundle), `qr_reviews_base`, `qr_reviews_pro`. |
| 3 | **Validación de seed reforzada** | V1 usaba conteos (`Modules=2, Bundles=1`). V2 valida por `code`, `name` y `precio exacto`. |
| 4 | **Smoke funcional separado de atajos** | V1 mezclaba flujo real de usuario con `manage.py shell`. V2 separa: sección 7 = usuario real en browser, sección 8 = atajos por shell. |
| 5 | **Caso "sin Google URL" documentado** | V1 no lo cubría. V2 documenta comportamiento exacto: landing muestra "El negocio aún no configuró su enlace de reseñas", submit con redirect devuelve thank-you en lugar de crash. |
| 6 | **Mitigación parcial agregada** | V1 solo tenía rollback completo. V2 agrega sección de contención operativa (feature disable, kill celery, etc.). |
| 7 | **Plan DB `qr_reviews` con precio stale** | Detectado: `billing.Plan(code='qr_reviews').price = 49.00` (valor de seed viejo). Re-ejecutar `seed_billing` lo lleva a `25000.00`. Documentado como paso obligatorio pre-deploy. |

---

## 1. Inconsistencias Encontradas y Resolución

### 1.1 Precio canónico vs frontend (CORREGIDA EN CÓDIGO)

- **Fuente canónica backend** (`generated/pricing.json`): `qr_reviews_pro` = 35000/mes
- **Frontend** (`apps/web/src/lib/pricing/plans.ts`): `REVIEWS_PRO.priceMonthly` = 40000
- **Decisión de producto**: $40.000/mes es el precio correcto.
- **Fix aplicado**: `generated/pricing.json` actualizado a `price_monthly: 40000`, `price_yearly: 384000`.
- **Impacto**: `plan_price('qr_reviews_pro', 'monthly')` ahora devuelve 40000. El upgrade view (`ReviewsUpgradeView`) crea la preferencia MP con $40.000.
- **Verificación**: 268 tests pasan post-fix.

### 1.2 Plan DB stale (OPERATIVA — requiere re-seed)

- `billing.Plan(code='qr_reviews')` tiene `price=49.00` en DB.
- Después de re-ejecutar `seed_billing`, queda en `25000.00` (precio canónico de `qr_reviews_base`).
- Este Plan se usa en el checkout de onboarding. No afecta el upgrade/downgrade (que lee de `canonical_pricing.py`).
- **Acción**: re-ejecutar `seed_billing` como paso obligatorio del pre-deploy.

### 1.3 Naming de plan codes (NO ES BUG — documentada)

| Código | Dónde se usa | Significado |
|--------|-------------|-------------|
| `qr_reviews` | `Bundle.code`, `Plan.code`, `SubscriptionV2.service_type`, `business.Subscription.service` | Legacy / bundle / service identifier. Equivale funcionalmente a Base. |
| `qr_reviews_base` | `business.Subscription.plan`, `BusinessPlan.QR_REVIEWS_BASE`, `entitlements._QR_REVIEWS_PLAN_CODES` | Plan Base explícito (post-downgrade). |
| `qr_reviews_pro` | `business.Subscription.plan`, `BusinessPlan.QR_REVIEWS_PRO`, `_TARGET_PLAN`, `_PRO_PLAN_CODES` | Plan Pro. |

- `qr_reviews` y `qr_reviews_base` son **funcionalmente idénticos** en entitlements y en upgrade eligibility.
- El demo seed crea la suscripción con plan `qr_reviews` (legacy). Un downgrade la deja en `qr_reviews_base`.

### 1.4 Frontend `QrReviewsPlanBuilder` internal keys (NO ES BUG)

- El componente usa `plan: 'reviews_base'` / `plan: 'reviews_pro'` como keys internos de UI.
- Los `PlanDef` canónicos (`REVIEWS_BASE.code` / `REVIEWS_PRO.code`) usan `qr_reviews_base` / `qr_reviews_pro`.
- No hay confusión funcional: el `onSubscribe` callback envía el `planCode` correcto al backend.

---

## 2. Referencia Rápida de Plan Codes y Precios

| Plan code canónico | Nombre display | Precio mensual (ARS) | Precio anual (ARS) | Fuente |
|-------------------|----------------|---------------------|--------------------|----|
| `qr_reviews_base` | QR Reseñas / Reseñas Base | 25.000 | 240.000 | `generated/pricing.json` |
| `qr_reviews_pro` | Reseñas Pro | 40.000 | 384.000 | `generated/pricing.json` |

**Nota**: valores en pesos argentinos enteros. `25000` = $25.000 ARS.

---

## 3. PRE-DEPLOY

### Paso 1 — Verificar migraciones `reviews`

**Ejecuta**: Backend. **Evidencia**: captura de output.

```powershell
docker exec mirubro-api python manage.py showmigrations reviews
```

**Esperado exacto** (7 migraciones, todas aplicadas):

```
reviews
 [X] 0001_initial
 [X] 0002_migrate_engagement_data
 [X] 0003_update_review_statuses
 [X] 0004_alter_review_status_choices
 [X] 0005_reviewvisit
 [X] 0006_rename index
 [X] 0007_add_mode_and_trial_fields
```

**NO-GO si**: alguna migración aparece como `[ ]` (no aplicada), o hay menos de 7.

---

### Paso 2 — Re-ejecutar `seed_billing` y validar datos exactos

**Ejecuta**: Backend. **Evidencia**: output completo del seed + validación.

```powershell
docker exec mirubro-api python manage.py seed_billing
```

Luego validar datos exactos:

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.billing.models import Module, Bundle, Plan
from apps.billing.canonical_pricing import plan_price

# ── Modules ──
m1 = Module.objects.get(code='qr_reviews_core')
m2 = Module.objects.get(code='qr_reviews_qr_gen')
assert m1.name == 'Configuración de Reseñas', f'Module name wrong: {m1.name}'
assert m1.vertical == 'qr_reviews', f'Module vertical wrong: {m1.vertical}'
assert m2.name == 'Generador de QR', f'Module name wrong: {m2.name}'
assert m2.vertical == 'qr_reviews', f'Module vertical wrong: {m2.vertical}'
print('✅ Modules: qr_reviews_core + qr_reviews_qr_gen OK')

# ── Bundle ──
b = Bundle.objects.get(code='qr_reviews')
assert b.name == 'QR de Reseñas', f'Bundle name wrong: {b.name}'
assert b.vertical == 'qr_reviews', f'Bundle vertical wrong: {b.vertical}'
assert b.fixed_price_monthly == plan_price('qr_reviews_base', 'monthly'), f'Bundle price wrong: {b.fixed_price_monthly}'
assert b.fixed_price_monthly == 25000, f'Bundle price not 25000: {b.fixed_price_monthly}'
assert b.modules.count() == 2, f'Bundle modules count wrong: {b.modules.count()}'
print(f'✅ Bundle: qr_reviews · \$25.000/mes · 2 módulos OK')

# ── Plan (checkout) ──
p = Plan.objects.get(code='qr_reviews')
assert p.name == 'QR de Reseñas', f'Plan name wrong: {p.name}'
from decimal import Decimal
expected_price = Decimal('25000.00')
assert p.price == expected_price, f'Plan price wrong: {p.price} (expected {expected_price})'
assert p.currency == 'ARS', f'Plan currency wrong: {p.currency}'
assert p.plan_status == 'active', f'Plan status wrong: {p.plan_status}'
print(f'✅ Plan: qr_reviews · \${p.price} ARS · active OK')

# ── Canonical pricing ──
base_m = plan_price('qr_reviews_base', 'monthly')
pro_m  = plan_price('qr_reviews_pro', 'monthly')
pro_y  = plan_price('qr_reviews_pro', 'yearly')
assert base_m == 25000, f'Canonical base price wrong: {base_m}'
assert pro_m  == 40000, f'Canonical pro price wrong: {pro_m}'
assert pro_y  == 384000, f'Canonical pro yearly wrong: {pro_y}'
print(f'✅ Canonical pricing: Base=\$25.000 · Pro=\$40.000/mes · \$384.000/año OK')

print()
print('🎯 SEED VALIDATION PASSED — all assertions OK')
"
```

**Esperado**: todas las líneas `✅` y final `🎯 SEED VALIDATION PASSED`.

**NO-GO si**: cualquier assertion falla. Revisar que `generated/pricing.json` tenga `qr_reviews_pro.price_monthly = 40000` y re-ejecutar `seed_billing`.

---

### Paso 3 — Verificar env vars de producción/staging

**Ejecuta**: Backend. **Evidencia**: output (sin leakear secrets).

```powershell
docker exec mirubro-api python manage.py shell -c "
from django.conf import settings
import os

checks = [
    ('EMAIL_BACKEND',       settings.EMAIL_BACKEND,       'django.core.mail.backends.smtp.EmailBackend'),
    ('EMAIL_HOST',          settings.EMAIL_HOST,           'smtp.sendgrid.net'),
    ('EMAIL_PORT',          str(settings.EMAIL_PORT),      '587'),
    ('EMAIL_USE_TLS',       str(settings.EMAIL_USE_TLS),   'True'),
    ('DEFAULT_FROM_EMAIL',  settings.DEFAULT_FROM_EMAIL,   'Mirubro <no-reply@mirubro.com>'),
]

all_ok = True
for name, got, expected in checks:
    ok = got == expected
    icon = '✅' if ok else '❌'
    if not ok:
        all_ok = False
        print(f'  {icon} {name}: got={got!r} expected={expected!r}')
    else:
        print(f'  {icon} {name}: {got}')

secrets = [
    ('MP_ACCESS_TOKEN',     bool(os.environ.get('MP_ACCESS_TOKEN'))),
    ('MP_WEBHOOK_SECRET',   bool(os.environ.get('MP_WEBHOOK_SECRET'))),
    ('EMAIL_HOST_PASSWORD',  bool(os.environ.get('EMAIL_HOST_PASSWORD'))),
    ('DJANGO_SECRET_KEY',   bool(settings.SECRET_KEY and len(settings.SECRET_KEY) > 10)),
]

for name, present in secrets:
    icon = '✅' if present else '❌'
    if not present:
        all_ok = False
    print(f'  {icon} {name}: {\"SET\" if present else \"MISSING\"}')

# Cache backend
cache_backend = settings.CACHES.get('default', {}).get('BACKEND', '')
cache_ok = 'RedisCache' in cache_backend or 'redis' in cache_backend.lower()
icon = '✅' if cache_ok else '❌'
if not cache_ok: all_ok = False
print(f'  {icon} CACHE_BACKEND: {cache_backend}')

# Celery broker
broker = getattr(settings, 'CELERY_BROKER_URL', '')
broker_ok = broker.startswith('redis://')
icon = '✅' if broker_ok else '❌'
if not broker_ok: all_ok = False
print(f'  {icon} CELERY_BROKER_URL: {broker[:30]}...')

print()
if all_ok:
    print('🎯 ENV VALIDATION PASSED')
else:
    print('🚫 ENV VALIDATION FAILED — fix before proceeding')
"
```

**NO-GO si**:
- `EMAIL_BACKEND` = `console` (emails se pierden)
- `MP_ACCESS_TOKEN`: `MISSING` (upgrade checkout rompe)
- `EMAIL_HOST_PASSWORD`: `MISSING` (notificaciones no se envían)
- `CACHE_BACKEND` no contiene `Redis` (stats cache no funciona)

---

### Paso 4 — Ejecutar test suite completo

**Ejecuta**: Backend. **Evidencia**: output completo con timestamp.

```powershell
docker exec mirubro-api python manage.py test apps.reviews apps.billing.tests.test_reviews_upgrade apps.billing.tests.test_reviews_downgrade --verbosity 0 --keepdb
```

**Esperado exacto**: `Ran 268 tests ... OK`

Desglose: 246 (reviews) + 10 (upgrade) + 12 (downgrade).

**NO-GO si**: `failures > 0` o count distinto de 268.

---

### Paso 5 — Verificar Redis cache

**Ejecuta**: Backend. **Evidencia**: output.

```powershell
docker exec mirubro-api python manage.py shell -c "
from django.core.cache import cache
cache.set('_release_probe', 'ok', 10)
val = cache.get('_release_probe')
assert val == 'ok', f'Redis cache broken: got {val!r}'
cache.delete('_release_probe')
print('✅ Redis cache: read/write/delete OK')
"
```

**NO-GO si**: assertion falla (Redis no responde o backend usa LocMemCache).

---

### Paso 6 — Snapshot de base de datos

**Ejecuta**: Backend / DevOps. **Evidencia**: archivo de backup.

```powershell
# Nombre con timestamp
$ts = Get-Date -Format "yyyyMMdd_HHmm"
docker exec mirubro-postgres pg_dump -U mirubro mirubro > "backup_pre_release_qr_resenas_$ts.sql"
```

Verificar que el archivo no esté vacío:

```powershell
(Get-Item "backup_pre_release_qr_resenas_$ts.sql").Length
```

**Esperado**: tamaño > 0 bytes.

---

## 4. DEPLOY BACKEND

### Paso 7 — Levantar / actualizar API

**Ejecuta**: Backend / DevOps.

```powershell
docker compose -f infra/docker-compose.yml up -d api
```

Esperar a que el container esté listo y verificar que no quedaron migraciones pendientes:

```powershell
docker exec mirubro-api python manage.py migrate --check
```

**Esperado**: `No migrations to apply.` (exit code 0).

**Si hay migraciones pendientes**: el container ya ejecutó `migrate` en su `command`. Verificar logs:

```powershell
docker logs mirubro-api --tail 30 2>&1 | Select-String "migrate|Migration"
```

---

### Paso 8 — Reiniciar Celery worker y verificar tarea registrada

**Ejecuta**: Backend. **Evidencia**: captura de log.

```powershell
docker compose -f infra/docker-compose.yml restart celery-worker celery-beat
```

Esperar 10 segundos, luego:

```powershell
docker logs mirubro-celery-worker --tail 50 2>&1 | Select-String "reviews"
```

**Esperado**: línea conteniendo `reviews.send_weekly_digest` en la lista de tareas registradas.

**NO-GO si**: la tarea no aparece (módulo reviews no se cargó en el worker).

---

### Paso 9 — Verificar Celery beat schedule

**Ejecuta**: Backend. **Evidencia**: captura de log.

```powershell
docker logs mirubro-celery-beat --tail 50 2>&1 | Select-String "reviews"
```

**Esperado**: entrada `reviews-send-weekly-digest` en el schedule.

**Horario programado**: lunes 12:00 UTC (09:00 ART). Definido en `config/settings.py` línea 277.

---

### Paso 10 — Healthcheck API

**Ejecuta**: Backend.

```powershell
# Endpoint público (slug inexistente = 404 esperado)
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/reviews/public/nonexistent/" -Method GET -SkipHttpErrorCheck
Write-Host "Status: $($r.StatusCode)"
Write-Host "Body: $($r.Content)"
```

**Esperado**: `Status: 404`, body contiene `"detail"`.

Si no tenés `Invoke-WebRequest` disponible:

```powershell
docker exec mirubro-api python -c "
import django; import os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from django.test import RequestFactory
from apps.reviews.views import PublicReviewLandingView
rf = RequestFactory()
req = rf.get('/api/v1/reviews/public/nonexistent/')
resp = PublicReviewLandingView.as_view()(req, slug='nonexistent')
print(f'Status: {resp.status_code}')
print('API is alive ✅')
"
```

---

## 5. DEPLOY FRONTEND

### Paso 11 — Build frontend

**Ejecuta**: Frontend. **Evidencia**: output final del build.

```powershell
cd apps/web; npm run build
```

**NO-GO si**: errores de TypeScript en `features/reviews/`, `app/resenas/`, o `app/r/[slug]/`.

---

### Paso 12 — Levantar / actualizar web

**Ejecuta**: Frontend / DevOps.

```powershell
docker compose -f infra/docker-compose.yml up -d web
```

---

### Paso 13 — Verificar rutas clave (visual rápido)

**Ejecuta**: Frontend / QA.

| Ruta | Sin sesión | Con sesión (qr_reviews) |
|------|-----------|------------------------|
| `http://localhost:3000/entrar` | Formulario de login visible | N/A |
| `http://localhost:3000/app/resenas` | Redirect a `/entrar` | Dashboard carga con título "QR de Reseñas" |
| `http://localhost:3000/app/resenas/configuracion` | Redirect a `/entrar` | Formulario de configuración |
| `http://localhost:3000/app/resenas/qr` | Redirect a `/entrar` | QR SVG generado |
| `http://localhost:3000/app/resenas/analytics` | Redirect a `/entrar` | Analytics con gráficos |
| `http://localhost:3000/app/resenas/feedback` | Redirect a `/entrar` | Lista de reviews |
| `http://localhost:3000/r/nonexistent` | 404 limpio (Next.js not-found) | N/A |
| `http://localhost:3000/app/onboarding/servicio` | Redirect a `/entrar` | 4 opciones incluyendo "QR de Reseñas" |

**Evidencia**: screenshots de al menos dashboard + config + landing 404.

---

## 6. Comportamiento Exacto: "Sin Google URL Configurado"

### Contexto

El `ReviewConfig.redirect_url` es un property calculado con prioridad:
1. `custom_redirect_url` (URL manual seteada por el owner)
2. `google_place_id` → genera `https://search.google.com/local/writereview?placeid=<id>`
3. `google_review_url` (URL legacy)
4. Si ninguno existe → `None`

### Comportamiento por modo

| Modo | `redirect_url` | Comportamiento landing | Comportamiento submit |
|------|----------------|----------------------|----------------------|
| `direct` | con URL | Countdown 3s → redirect automático a Google | Response: `action=redirect, redirect_url=<url>` |
| `direct` | `None` | Muestra: **"El negocio aún no configuró su enlace de reseñas."** Sin redirect, sin countdown. | Response: `action=redirect, redirect_url=null` → frontend muestra thank-you genérico |
| `smart_filter` | con URL | Formulario de rating | Rating ≥ threshold: `action=redirect` con URL · Rating < threshold: `action=submitted` (review guardada) |
| `smart_filter` | `None` | Formulario de rating | Rating ≥ threshold: `action=redirect, redirect_url=null` → frontend muestra thank-you en vez de redirect · Rating < threshold: guardado normal |

### Criterio Go/No-Go

- **Aceptable para release**: que un negocio SIN Place ID vea el mensaje informativo. No es un error, es estado de configuración incompleta.
- **NO-GO si**: la landing crashea (500), el submit crashea, o un negocio CON Place ID válido no redirige.

---

## 7. SMOKE TEST FUNCIONAL REAL (browser, sin atajos)

**Ejecuta**: QA. **Prerrequisito**: cuenta demo creada (ver Paso ST-0 en sección 8).

### ST-F1: Login

1. Abrir `http://localhost:3000/entrar` en browser.
2. Ingresar: `qr.reviews@demo.local` / `Demo12345!`.
3. **Esperado**: redirect a `/app/resenas` (o `/app` → navegar a reseñas).
4. **Evidencia**: screenshot post-login.

### ST-F2: Dashboard

1. Verificar en `/app/resenas`:
   - Título "QR de Reseñas" visible.
   - Cards de navegación: Configuración, Mi QR, Feedback, Analytics.
   - Stats iniciales: todo en 0 (negocio nuevo).
2. **Evidencia**: screenshot del dashboard.

### ST-F3: Configuración

1. Ir a `/app/resenas/configuracion`.
2. Verificar Place ID pre-cargado: `ChIJYYBCryHKvJURGnvIRqKJFPU` (si demo seed fue ejecutado).
3. Cambiar `thank_you_message` a "¡Gracias por elegirnos!".
4. Guardar → verificar toast/confirmación.
5. **Esperado**: guardado sin error. Al recargar, el mensaje persiste.
6. **Evidencia**: screenshot de config guardada.

### ST-F4: Generación de QR

1. Ir a `/app/resenas/qr`.
2. **Esperado**: QR SVG renderizado, botón de descarga visible.
3. URL pública mostrada: `http://localhost:3000/r/demo-qr-reviews/`.
4. **Evidencia**: screenshot del QR.

### ST-F5: Landing pública — modo direct (Base)

1. Abrir `http://localhost:3000/r/demo-qr-reviews/` en navegador **incógnito** (sin sesión).
2. **Esperado (Base plan, mode=direct)**:
   - Nombre del negocio "Demo QR Reviews" visible.
   - Countdown de 3 segundos.
   - Redirect automático a `https://search.google.com/local/writereview?placeid=ChIJYYBCryHKvJURGnvIRqKJFPU`.
3. **Evidencia**: screenshot de la landing antes del redirect.

### ST-F6: Landing sin Google URL

1. Desde el dashboard, ir a `/app/resenas/configuracion`.
2. Borrar el Place ID (dejar vacío). Guardar.
3. Abrir landing pública en incógnito.
4. **Esperado**: muestra "El negocio aún no configuró su enlace de reseñas." Sin redirect.
5. Restaurar Place ID después del test.
6. **Evidencia**: screenshot del mensaje.

### ST-F7: Stats post-visitas

1. Abrir el dashboard `/app/resenas` (sesión autenticada).
2. Verificar: `total_visits` > 0 (de las visitas de ST-F5 y ST-F6).
3. `total_reviews` = 0 (modo direct no crea reviews).
4. **Evidencia**: screenshot de stats.

### ST-F8: Dedup (429)

1. Con Place ID restaurado, abrir landing 2 veces seguidas rápido (misma IP, < 10 min).
2. No aplica en modo direct — este test requiere smart_filter. **Postergar a ST-A4** (sección 8).

---

## 8. SMOKE TEST ASISTIDO / ATAJOS OPERATIVOS (shell)

**Ejecuta**: Backend (shell) + QA (browser para verificar resultados).

### ST-A0: Crear cuenta demo

```powershell
docker exec mirubro-api python manage.py seed_billing
docker exec mirubro-api python manage.py seed_qr_reviews_demo
```

**Credenciales resultantes**:
- Email: `qr.reviews@demo.local`
- Password: `Demo12345!`
- Business slug: `demo-qr-reviews`
- Plan: `qr_reviews` (legacy = funcionalmente Base)
- Place ID: `ChIJYYBCryHKvJURGnvIRqKJFPU` (Obelisco de Buenos Aires)

**Esperado**: seed termina con `✅ CUENTA DEMO QR DE RESEÑAS — LISTA`.

**NO-GO si**: error en seed (bundle no existe, feature check falla).

---

### ST-A1: Upgrade forzado a Pro

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.business.models import Business
from apps.billing.reviews_views import apply_reviews_plan_upgrade
biz = Business.objects.get(slug='demo-qr-reviews')
print(f'Before: plan={biz.subscription.plan}')
apply_reviews_plan_upgrade(biz, 'qr_reviews_pro')
biz.subscription.refresh_from_db()
assert biz.subscription.plan == 'qr_reviews_pro', f'Upgrade failed: {biz.subscription.plan}'
print(f'After:  plan={biz.subscription.plan}')
print('✅ Upgrade to qr_reviews_pro OK')
"
```

**Esperado**: plan cambia a `qr_reviews_pro`.

---

### ST-A2: Verificar smart_filter habilitado (post-upgrade)

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.business.models import Business
from apps.reviews.entitlements import is_reviews_pro, smart_filter_allowed
biz = Business.objects.get(slug='demo-qr-reviews')
assert is_reviews_pro(biz), 'Not Pro!'
assert smart_filter_allowed(biz), 'Smart filter not allowed!'
print('✅ is_reviews_pro=True, smart_filter_allowed=True')
"
```

---

### ST-A3: Setear modo smart_filter

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.business.models import Business
from apps.reviews.models import ReviewConfig
biz = Business.objects.get(slug='demo-qr-reviews')
config = biz.review_config
config.mode = 'smart_filter'
config.save(update_fields=['mode', 'updated_at'])
print(f'✅ mode={config.mode}, effective_mode={config.effective_mode}')
"
```

**Esperado**: `mode=smart_filter, effective_mode=smart_filter`.

---

### ST-A4: Smart filter — flujo completo (browser)

> Ahora el negocio es Pro con smart_filter activo.

1. **Incógnito**: abrir `http://localhost:3000/r/demo-qr-reviews/`.
2. **Esperado**: formulario de rating (NO redirect automático).
3. **Enviar rating 5**: → debería mostrar redirect a Google (rating ≥ threshold=4).
4. **Nuevo incógnito** (distinta IP o esperar 10 min): enviar rating 2, comment "Test negativo". → mensaje "¡Gracias por tu opinión!" (o el custom). Review guardada como internal feedback.
5. **Dashboard**: verificar review con status `new`, rating=2.
6. **Email**: verificar notificación al owner (`qr.reviews@demo.local`). Si `EMAIL_BACKEND=console`, revisar logs del container API.
7. **Evidencia**: screenshots de landing con formulario, redirect, thank-you, review en dashboard, email.

---

### ST-A5: Dedup (429)

1. Mismo incógnito: volver a enviar rating 3 (sin cambiar IP, dentro de 10 min).
2. **Esperado**: HTTP 429 con mensaje "Ya enviaste una reseña recientemente. Intentá más tarde."
3. **Evidencia**: screenshot del error.

---

### ST-A6: Status pipeline

1. En dashboard `/app/resenas/feedback`, encontrar la review de ST-A4.
2. Cambiar status: `new` → `read` → `contacted` → `resolved`.
3. Verificar que cada cambio persiste.
4. **Evidencia**: screenshot de la review en estado `resolved`.

---

### ST-A7: Downgrade Pro → Base

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.business.models import Business
from apps.billing.reviews_views import apply_reviews_plan_downgrade
biz = Business.objects.get(slug='demo-qr-reviews')
print(f'Before: plan={biz.subscription.plan}')
apply_reviews_plan_downgrade(biz, 'qr_reviews_base', user=biz.memberships.first().user)
biz.subscription.refresh_from_db()
assert biz.subscription.plan == 'qr_reviews_base', f'Downgrade failed: {biz.subscription.plan}'
print(f'After:  plan={biz.subscription.plan}')

# Verify effective_mode falls back to direct
config = biz.review_config
print(f'mode={config.mode}, effective_mode={config.effective_mode}')
assert config.effective_mode == 'direct', f'Expected direct, got {config.effective_mode}'
print('✅ Downgrade to qr_reviews_base OK — effective_mode=direct')
"
```

**Esperado**:
- Plan: `qr_reviews_base`.
- `mode` sigue en `smart_filter` (no se borra), pero `effective_mode` = `direct` (entitlements lo fuerza).

---

### ST-A8: Datos históricos preservados post-downgrade

1. En dashboard, verificar la review de ST-A4 sigue visible.
2. Stats: `total_reviews` sigue siendo > 0.
3. Landing pública: ahora vuelve a ser redirect directo (modo direct).
4. **Evidencia**: screenshot de reviews históricas en dashboard.

---

### ST-A9: Trial activation (reset primero)

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.business.models import Business
from apps.reviews.models import ReviewConfig
biz = Business.objects.get(slug='demo-qr-reviews')
config = biz.review_config
config.trial_used = False
config.trial_ends_at = None
config.mode = 'direct'
config.save(update_fields=['trial_used', 'trial_ends_at', 'mode', 'updated_at'])
print(f'✅ Trial reset: trial_used={config.trial_used}, trial_ends_at={config.trial_ends_at}')
"
```

Luego en browser (sesión demo):
1. Ir a config → debe ver opción "Activar prueba gratis".
2. Activar trial.
3. **Esperado**: mode cambia a `smart_filter`, banner de "prueba por X días" visible.
4. **Evidencia**: screenshot.

---

### ST-A10: Edge cases

```powershell
# Slug inexistente → 404
docker exec mirubro-api python -c "
import requests
r = requests.get('http://localhost:8000/api/v1/reviews/public/slug-inexistente/')
assert r.status_code == 404, f'Expected 404, got {r.status_code}'
print('✅ Slug inexistente: 404')
"
```

```powershell
# Config disabled → 404
docker exec mirubro-api python manage.py shell -c "
from apps.business.models import Business
biz = Business.objects.get(slug='demo-qr-reviews')
config = biz.review_config
config.enabled = False
config.save(update_fields=['enabled'])
import requests
r = requests.get('http://localhost:8000/api/v1/reviews/public/demo-qr-reviews/')
assert r.status_code == 404, f'Expected 404, got {r.status_code}'
config.enabled = True
config.save(update_fields=['enabled'])
print('✅ Disabled config: 404, re-enabled')
"
```

---

## 9. OBSERVABILIDAD PRIMERAS 24H

### 9.1 Logs estructurados a monitorear

El módulo usa el prefijo `[Reviews]` en todos los logs. Patrones clave:

| Log pattern | Significado | Acción si anómalo |
|------------|-------------|-------------------|
| `[Reviews] Config updated` | Owner modificó configuración | Normal |
| `[Reviews] Submit redirect` | Visitor redirigido a Google | Normal |
| `[Reviews] Submit stored` | Feedback interno guardado (smart_filter) | Normal |
| `[Reviews] Submit dedup` | Intento duplicado bloqueado | Normal si < 20% del total |
| `[Reviews] Landing 404 reason=plan_not_allowed` | Acceso a landing sin plan activo | Investigar si es alto volumen |
| `[Reviews] Landing 404 reason=disabled` | Config disabled | Normal |
| `[ReviewNotif] Failed to send` | Email de notificación falló | **Verificar SendGrid API key** |
| `[ReviewNotif] No owner email` | Negocio sin owner con email | **Investigar dato corrupto** |
| `[ReviewDigest] Failed to send` | Digest semanal falló | **Revisar template/SMTP** |
| `[ReviewsUpgrade] MP preference creation failed` | MercadoPago no disponible | Verificar `MP_ACCESS_TOKEN` |
| `[Reviews] QR denied reason=plan_not_allowed` | Intent de generar QR sin plan | Normal (free tier) |

### 9.2 Comandos de monitoreo

```powershell
# Errores del módulo (últimas 2000 líneas)
docker logs mirubro-api --tail 2000 2>&1 | Select-String "\[Reviews\].*ERROR|\[ReviewNotif\].*Failed|\[ReviewDigest\].*Failed|\[ReviewsUpgrade\].*failed"

# Distribución de submits
docker logs mirubro-api --tail 5000 2>&1 | Select-String "\[Reviews\] Submit (stored|redirect|dedup)"

# 5xx errors en cualquier endpoint
docker logs mirubro-api --tail 5000 2>&1 | Select-String "\"(POST|GET|PATCH) /api/v1/reviews/.*\" 5\d\d"

# Métricas agregadas de DB
docker exec mirubro-api python manage.py shell -c "
from apps.reviews.models import Review, ReviewVisit, ReviewConfig
print(f'Configs enabled:  {ReviewConfig.objects.filter(enabled=True).count()}')
print(f'Total visits:     {ReviewVisit.objects.count()}')
print(f'Total reviews:    {Review.objects.count()}')
from apps.billing.models import SubscriptionV2
print(f'Active Pro subs:  {SubscriptionV2.objects.filter(service_type=\"qr_reviews\", plan_code=\"qr_reviews_pro\", status=\"active\").count()}')
"
```

### 9.3 Alertas a configurar

| Condición | Umbral | Severidad |
|-----------|--------|-----------|
| `[ReviewNotif] Failed to send` | ≥ 1 en 1h | Critical |
| `5xx` en endpoints `/api/v1/reviews/` | ≥ 1 en 1h | Critical |
| `Submit dedup` / `Submit total` | > 30% en 24h | Warning |
| `Landing 404 plan_not_allowed` | > 50 en 24h | Warning |
| `send_weekly_digest` no ejecutó el lunes | No log para el lunes | Warning |
| 0 `Submit` después de 48h con configs enabled | — | Warning |

---

## 10. GO / NO-GO

### Checklist estricta

| # | Criterio | Verificación exacta | ✅/❌ |
|---|---------|---------------------|------|
| 1 | 268 tests pasan | `Ran 268 tests ... OK` | |
| 2 | 7 migraciones aplicadas | `showmigrations reviews` → 7x `[X]` | |
| 3 | Seed: Module `qr_reviews_core` name="Configuración de Reseñas" | Assertion en Paso 2 | |
| 4 | Seed: Module `qr_reviews_qr_gen` name="Generador de QR" | Assertion en Paso 2 | |
| 5 | Seed: Bundle `qr_reviews` price=25000 | Assertion en Paso 2 | |
| 6 | Seed: Plan `qr_reviews` price=25000.00 | Assertion en Paso 2 | |
| 7 | Canonical: `qr_reviews_pro` monthly=40000 | Assertion en Paso 2 | |
| 8 | Env: EMAIL_BACKEND=smtp, MP_ACCESS_TOKEN set | Paso 3 | |
| 9 | Redis cache: read/write OK | Paso 5 | |
| 10 | Celery: `reviews.send_weekly_digest` registrada | Paso 8 | |
| 11 | API: healthcheck 404 en slug inexistente | Paso 10 | |
| 12 | Frontend: build sin errores TS | Paso 11 | |
| 13 | ST-F1: login funciona | Browser | |
| 14 | ST-F5: landing pública redirige a Google | Browser | |
| 15 | ST-F6: landing sin URL muestra mensaje informativo | Browser | |
| 16 | ST-A3: smart_filter en Pro funciona | Shell + browser | |
| 17 | ST-A4: review guardada con notificación email | Browser + email | |
| 18 | ST-A5: dedup 429 | Browser | |
| 19 | ST-A7: downgrade preserva datos, effective_mode=direct | Shell | |
| 20 | Zero 5xx en logs durante smoke tests | Log check | |

**GO**: 20/20 checks.
**NO-GO**: cualquier check falla → bloquea release hasta resolución.

### Firmas requeridas

| Rol | Responsable | Firma | Fecha |
|-----|------------|-------|-------|
| Backend | | | |
| Frontend | | | |
| QA | | | |
| Producto | | | |

---

## 11. MITIGACIÓN PARCIAL (sin rollback completo)

Para problemas que no requieren revertir el deploy completo.

### 11.1 Desactivar landing pública sin deploy

Si las landings públicas causan problemas (500s, abuso):

```powershell
# Desactivar TODAS las configs de reviews
docker exec mirubro-api python manage.py shell -c "
from apps.reviews.models import ReviewConfig
count = ReviewConfig.objects.filter(enabled=True).update(enabled=False)
print(f'Disabled {count} review configs')
"
```

**Efecto**: todas las landings (`/r/<slug>/`) devuelven 404. Dashboard sigue funcionando. Reversible re-habilitando.

### 11.2 Desactivar smart_filter globalmente

Si el filtro inteligente causa problemas (reviews mal enrutadas):

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.reviews.models import ReviewConfig
count = ReviewConfig.objects.filter(mode='smart_filter').update(mode='direct')
print(f'Reset {count} configs to direct mode')
"
```

**Efecto**: todos los negocios vuelven a redirect directo. No se pierden datos.

### 11.3 Detener digest semanal

Si el digest genera spam o errores:

```powershell
# Opción 1: detener celery-beat (detiene TODOS los schedules)
docker compose -f infra/docker-compose.yml stop celery-beat

# Opción 2: solo detener el worker (las tareas se encolan pero no se ejecutan)
docker compose -f infra/docker-compose.yml stop celery-worker
```

**Efecto**: `send_weekly_digest` no se ejecuta el próximo lunes. Emails detenidos. Reversible con `start`.

### 11.4 Desactivar notificaciones de reviews

Si SendGrid falla o se envían emails incorrectos:

```powershell
# Cambiar backend a console (solo afecta el container actual)
docker exec mirubro-api python manage.py shell -c "
from django.conf import settings
settings.EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
print('Email backend changed to console (runtime only, no persist)')
"
```

**Nota**: esto solo afecta el proceso Django actual. En un restart se vuelve al `.env`.

Para persistir:

```powershell
# En services/api/.env, cambiar:
# EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# Y reiniciar:
docker compose -f infra/docker-compose.yml restart api celery-worker
```

### 11.5 Bloquear upgrade/downgrade (billing)

Si MercadoPago tiene problemas o se detectan cargos incorrectos:

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.billing.models import PendingSubscriptionChange
# Cancelar todos los pendientes de reviews
count = PendingSubscriptionChange.objects.filter(
    target_plan_code='qr_reviews_pro',
    status='pending_payment'
).update(status='canceled')
print(f'Canceled {count} pending upgrades')
"
```

**Efecto**: los checkout links existentes ya no se procesan. La vista de upgrade sigue disponible pero creará nuevos pendientes. Para bloquear completamente, se requiere un deploy con la vista deshabilitada.

---

## 12. ROLLBACK TOTAL

### 12.1 Rollback backend

```powershell
# 1. Rebuild con imagen/commit anterior
docker compose -f infra/docker-compose.yml up -d api

# 2. Las 7 migraciones de reviews son ADITIVAS (crean tablas/columnas nuevas).
#    NO revertir migraciones — el código viejo ignora las tablas nuevas.
#    Si se necesita revertir (caso extremo):
#    docker exec mirubro-api python manage.py migrate reviews 0006_rename

# 3. Reiniciar celery para quitar la tarea del schedule
docker compose -f infra/docker-compose.yml restart celery-worker celery-beat
```

### 12.2 Rollback frontend

```powershell
# Revertir a build anterior de Next.js
docker compose -f infra/docker-compose.yml up -d web

# Las rutas /app/resenas y /r/[slug] desaparecen.
# No hay side effects en backend.
```

### 12.3 Rollback billing (MercadoPago)

```powershell
docker exec mirubro-api python manage.py shell -c "
from apps.billing.models import PendingSubscriptionChange, SubscriptionV2

# 1. Cancelar pending changes
pending = PendingSubscriptionChange.objects.filter(
    target_plan_code__startswith='qr_reviews',
    status='pending_payment'
)
print(f'Pending changes to cancel: {pending.count()}')
# pending.update(status='canceled')  # DESCOMENTAR PARA EJECUTAR

# 2. Si se crearon SubscriptionV2 incorrectas
v2 = SubscriptionV2.objects.filter(service_type='qr_reviews', status='active')
print(f'Active qr_reviews V2 subs: {v2.count()}')
# v2.update(status='canceled')  # DESCOMENTAR PARA EJECUTAR
"
```

### 12.4 Restaurar DB (caso extremo)

```powershell
# Usar el backup del Paso 6
docker exec -i mirubro-postgres psql -U mirubro mirubro < backup_pre_release_qr_resenas_XXXXXXXX_XXXX.sql
docker compose -f infra/docker-compose.yml restart api celery-worker celery-beat
```

---

## 13. EVIDENCIA A GUARDAR

| # | Paso | Evidencia | Formato | Quién |
|---|------|-----------|---------|-------|
| 1 | Paso 1 | Output `showmigrations reviews` (7 migraciones [X]) | txt | Backend |
| 2 | Paso 2 | Output `seed_billing` + validation script completo | txt | Backend |
| 3 | Paso 3 | Output de verificación env vars | txt | Backend |
| 4 | Paso 4 | Output `Ran 268 tests ... OK` con timestamp | txt | Backend |
| 5 | Paso 5 | Output Redis cache OK | txt | Backend |
| 6 | Paso 6 | Archivo de backup DB con tamaño | file | Backend |
| 7 | Paso 8 | Log celery-worker con `reviews.send_weekly_digest` | txt | Backend |
| 8 | ST-A0 | Output seed demo completo | txt | Backend |
| 9 | ST-F1 | Screenshot post-login | png | QA |
| 10 | ST-F2 | Screenshot dashboard con stats en 0 | png | QA |
| 11 | ST-F3 | Screenshot config con Place ID | png | QA |
| 12 | ST-F4 | Screenshot QR generado | png | QA |
| 13 | ST-F5 | Screenshot landing con countdown | png | QA |
| 14 | ST-F6 | Screenshot landing sin URL (mensaje informativo) | png | QA |
| 15 | ST-A4 | Screenshot review en dashboard + email de notificación | png | QA |
| 16 | ST-A5 | Screenshot error 429 dedup | png | QA |
| 17 | ST-A6 | Screenshot review en estado `resolved` | png | QA |
| 18 | ST-A7 | Output downgrade + effective_mode=direct | txt | Backend |
| 19 | ST-A8 | Screenshot datos históricos post-downgrade | png | QA |
| 20 | Go/No-Go | Checklist 20/20 firmada | md/pdf | Todos |

---

## 14. RIESGOS RESIDUALES

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|--------|-------------|---------|------------|
| 1 | SendGrid API key inválida en prod | Baja | Medio (emails no se envían) | Test email en Paso 3; fallback: console backend |
| 2 | MercadoPago sandbox vs producción | Media | Alto (cobros incorrectos) | Verificar `MP_ACCESS_TOKEN` es de producción |
| 3 | Rate limit insuficiente (30/hora) | Baja | Bajo (abuso de submit) | Monitorear `Submit dedup` rate; ajustar en `ReviewSubmitThrottle.rate` |
| 4 | Google Place ID inválido en demo | Baja | Ninguno (solo demo) | Obelisco de Buenos Aires es un Place ID estable |
| 5 | Digest se envía con 0 reviews | Baja | Bajo (email vacío) | `compute_digest_stats` ya filtra configs sin actividad |
| 6 | Frontend cache SSR con datos stale | Baja | Bajo | Landing usa `cache: 'no-store'`; dashboard es client-side |
| 7 | Plan DB `qr_reviews` stale si seed no se ejecuta | Media | Alto (checkout cobra $49 en vez de $25.000) | **Paso 2 es obligatorio y tiene assertion exacta** |

---

## 15. ACTA DE RELEASE

```
ACTA DE RELEASE — QR de Reseñas
================================================================
Fecha:              2026-04-__
Hora inicio:        __:__
Hora fin:           __:__
Versión API:        [commit hash]
Versión Web:        [commit hash]
Ambiente:           ☐ staging  ☐ producción
pricing.json ver:   2026-04-09 (Pro=$40.000)

RESULTADO:          ☐ GO  ☐ NO-GO
Motivo no-go:       ____________________________________

CHECKLIST:          __/20 checks passed
Tests:              268/268 passed
Precio Pro:         $40.000/mes (verificado contra canonical)
Precio Base:        $25.000/mes (verificado contra canonical)

FIRMAS
------
  Backend:      ________________  Fecha: __________
  Frontend:     ________________  Fecha: __________
  QA:           ________________  Fecha: __________
  Producto:     ________________  Fecha: __________

MÉTRICAS POST-RELEASE (completar a 24h)
----------------------------------------
  Configs creados:      ___
  Visits (QR scans):    ___
  Reviews guardadas:    ___
  Emails enviados:      ___
  Upgrades Pro:         ___
  Errores 5xx:          ___
  Tasa dedup:           ___%

NOTAS:
  ________________________________________________________
  ________________________________________________________

MITIGACIONES APLICADAS (si hubo):
  ________________________________________________________

================================================================
```

---

## Apéndice A: Referencia de Endpoints

| Método | Ruta | Auth | Función |
|--------|------|------|---------|
| GET | `/api/v1/reviews/config/` | ✅ `manage_reviews` | Leer configuración |
| PATCH | `/api/v1/reviews/config/` | ✅ `manage_reviews` | Modificar configuración |
| GET | `/api/v1/reviews/qr/` | ✅ `manage_reviews` | Generar QR SVG |
| GET | `/api/v1/reviews/stats/` | ✅ `manage_reviews` | Analytics (cached 5 min) |
| POST | `/api/v1/reviews/trial/activate/` | ✅ `manage_reviews` | Activar trial 7 días |
| GET | `/api/v1/reviews/` | ✅ `manage_reviews` | Listar reviews |
| PATCH | `/api/v1/reviews/<uuid:id>/` | ✅ `manage_reviews` | Cambiar status de review |
| GET | `/api/v1/reviews/public/<slug>/` | Público | Landing (config pública) |
| POST | `/api/v1/reviews/public/<slug>/submit/` | Público (throttled 30/h) | Enviar review/redirect |
| POST | `/api/v1/billing/reviews/upgrade/` | ✅ Owner | Iniciar upgrade a Pro (MP) |
| POST | `/api/v1/billing/reviews/downgrade/` | ✅ Owner | Downgrade a Base (inmediato) |

## Apéndice B: Referencia de Rutas Frontend

| Ruta | Componente | Auth | Descripción |
|------|-----------|------|-------------|
| `/entrar` | `AuthForm` | No | Login / signup |
| `/app/resenas` | `ReviewsDashboardClient` | Sí | Dashboard principal |
| `/app/resenas/configuracion` | `ReviewConfigClient` | Sí | Config (Place ID, mode, threshold) |
| `/app/resenas/qr` | `ReviewQrClient` | Sí | Generación de QR |
| `/app/resenas/analytics` | `AnalyticsClient` | Sí | Gráficos y métricas |
| `/app/resenas/feedback` | `FeedbackClient` | Sí | Lista de reviews + status pipeline |
| `/r/[slug]` | `ReviewLandingClient` / `ReviewFlowClient` | No | Landing pública |
| `/app/onboarding/servicio` | `OnboardingServicioPage` | Sí | Selección de servicio (incluye QR de Reseñas) |
| `/app/onboarding/plan` | Plan selection | Sí | Selección de plan |

## Apéndice C: Infraestructura Docker

| Servicio | Container | Puerto | Dependencias |
|----------|-----------|--------|-------------|
| API (Django) | `mirubro-api` | 8000 | postgres, redis |
| Web (Next.js) | `mirubro-web` | 3000 | api |
| PostgreSQL 16 | `mirubro-postgres` | 5432 | — |
| Redis 7 | `mirubro-redis` | 6379 | — |
| Celery Worker | `mirubro-celery-worker` | — | postgres, redis |
| Celery Beat | `mirubro-celery-beat` | — | postgres, redis |
