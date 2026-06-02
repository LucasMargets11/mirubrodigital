# QR de Reseñas — Pricing Change Runbook (PR-B)

> Reduce QR Reseñas Base **$25.000 → $20.000** y Pro **$40.000 → $28.000**
> Cambio aplica a **nuevas altas, upgrades y seeds**. Suscripciones activas
> NO se migran automáticamente — ver sección *Suscripciones activas* abajo.

---

## 1. Resumen del cambio

| Plan                  | Antes (mensual) | Después (mensual) | Antes (anual) | Después (anual) |
| --------------------- | --------------- | ----------------- | ------------- | --------------- |
| `qr_reviews_base`     | $25.000         | **$20.000**       | $240.000      | **$192.000**    |
| `qr_reviews_pro`      | $40.000         | **$28.000**       | $384.000      | **$268.800**    |
| `qr_reviews_empresarial` | Custom       | Custom (sin cambios) | Custom    | Custom          |

- Unidad canónica: **ARS pesos integer**.
- Descuento anual mantenido en **20%** (anual = mensual × 12 × 0.8).
- No se tocaron entitlements ni gating de PR-A.
- No se tocó MercadoPago real (sandbox/preference test sigue funcionando con los nuevos montos).

---

## 2. Archivos modificados

### Fuente canónica (frontend)
- [apps/web/src/lib/pricing/plans.ts](../apps/web/src/lib/pricing/plans.ts) — `REVIEWS_BASE` y `REVIEWS_PRO` actualizados.

### Fuente canónica (consumida por backend)
- [generated/pricing.json](../generated/pricing.json) — `qr_reviews_base` y `qr_reviews_pro` actualizados.

### Fix de plan_code mismatch (Paso 0)
- [apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx](../apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx) — `onSubscribe` ahora emite los códigos canónicos `qr_reviews_base` / `qr_reviews_pro` (antes emitía `reviews_base` / `reviews_pro`, que el backend no podía resolver vía `Plan.objects.get`).

### Backend (comentarios + seeds alineados)
- [services/api/src/apps/billing/management/commands/seed_billing.py](../services/api/src/apps/billing/management/commands/seed_billing.py) — comentarios actualizados a los nuevos valores. Los `fixed_price_*` siguen derivando de `plan_price(...)` (no requiere cambios funcionales).

### Tests backend
- [services/api/src/apps/billing/tests/test_canonical_pricing.py](../services/api/src/apps/billing/tests/test_canonical_pricing.py) — nuevas aserciones para Base y Pro (mensual + anual).
- [services/api/src/apps/billing/tests/test_reviews_upgrade.py](../services/api/src/apps/billing/tests/test_reviews_upgrade.py) — verifica que MP preference recibe `unit_price=28000` y `total_amount=28000`.
- [services/api/src/apps/billing/tests/test_promo_admin.py](../services/api/src/apps/billing/tests/test_promo_admin.py) — fixtures de `Plan` para `qr_reviews` / `qr_reviews_pro` actualizadas a 20000 / 28000.

### Tests frontend
- [apps/web/src/features/reviews/__tests__/product.test.ts](../apps/web/src/features/reviews/__tests__/product.test.ts) — contrato de pricing PR-B (Base 20.000 / Pro 28.000 + sin literales legacy).
- [apps/web/src/features/billing/components/__tests__/QrReviewsPlanBuilder.test.tsx](../apps/web/src/features/billing/components/__tests__/QrReviewsPlanBuilder.test.tsx) — nuevo. Cubre precios mensual/anual y normalización de `plan_code` canónico.
- [apps/web/src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx](../apps/web/src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx) — guard de literales: agrega `20000` y `28000` a la regex prohibida.

### NO se tocaron
- Migrations `0014_add_qr_reviews_pro_plan.py` ni `0016_seed_menu_qr_qr_reviews_copy_refresh.py` (son históricas; `seed_billing` las sobreescribe).
- `commercial_plans.py`, `canonical_pricing.py`, `reviews_views.py` — ya consumían `plan_price(...)` desde la fuente canónica.
- Entitlements / gating de PR-A.
- Carta Online, Restaurante, Gestión Comercial, Menú QR.

---

## 3. Despliegue

### Paso 3.1 — Re-seed billing (obligatorio)

```powershell
docker compose -f infra/docker-compose.yml exec -T api `
  sh -lc "cd /app && DJANGO_SETTINGS_MODULE=config.settings python manage.py seed_billing"
```

Si `docker-compose.yml` está en raíz:

```powershell
docker compose exec -T api `
  sh -lc "cd /app && DJANGO_SETTINGS_MODULE=config.settings python manage.py seed_billing"
```

### Paso 3.2 — Verificar DB

```sql
-- Plan price (DB Decimal, ARS pesos)
SELECT code, price FROM billing_plan WHERE code LIKE 'qr_reviews%' ORDER BY code;
-- Esperado:
--  qr_reviews             20000.00
--  qr_reviews_base        20000.00
--  qr_reviews_pro         28000.00

-- Bundle fixed prices (centavos / pesos según campo)
SELECT code, fixed_price_monthly, fixed_price_yearly
FROM billing_bundle
WHERE code LIKE 'qr_reviews%' ORDER BY code;
-- Esperado:
--  qr_reviews              20000   192000
--  qr_reviews_base         20000   192000
--  qr_reviews_pro          28000   268800
--  qr_reviews_empresarial  NULL    NULL
```

### Paso 3.3 — Re-deploy frontend

El bundle de Next.js incluye los nuevos precios desde `lib/pricing/plans.ts`. Asegurate de re-buildear (`pnpm build` o el pipeline) para que `/resenas` y `/pricing?service=qr_reviews` muestren los valores nuevos.

---

## 3.bis Ejecución verificada en dev (2026-06-02)

| Paso | Comando | Resultado |
| --- | --- | --- |
| Seed billing | `docker compose -f infra/docker-compose.yml exec -T api sh -lc "cd /app && DJANGO_SETTINGS_MODULE=config.settings python manage.py seed_billing"` | `Successfully seeded billing data` |
| Verificar `billing_plan` | `SELECT code, price FROM billing_plan WHERE code LIKE '%reviews%'` | `qr_reviews=20000.00`, `qr_reviews_base=20000.00`, `qr_reviews_pro=28000.00` ✅ |
| Verificar `billing_bundle` | `SELECT code, fixed_price_monthly, fixed_price_yearly FROM billing_bundle WHERE code LIKE '%reviews%'` | `qr_reviews=20000/192000`, `qr_reviews_base=20000/192000`, `qr_reviews_empresarial=NULL/NULL`, `qr_reviews_pro=28000/268800` ✅ |
| Verificar bundle Next build | `grep -lE '20\.000\|28\.000' .next/server/app/resenas.html` (sin matches de `25\.000\|40\.000`) | Sólo aparece los nuevos precios ✅ |
| Tests backend billing PR-B | `python manage.py test apps.billing.tests.test_canonical_pricing apps.billing.tests.test_reviews_upgrade apps.billing.tests.test_promo_admin` | `Ran 69 tests` — `test_qr_reviews_base`, `test_qr_reviews_pro` y todos los relevantes a PR-B pasan ✅ |

**Notas:**
- 2 errores pre-existentes (`test_qr_reviews_addon`, `test_qr_tips_addon`) usan códigos legacy `qr_reviews`/`qr_tips` que no existen en `_ADDON_INDEX` (los códigos canónicos son `menu_qr_addon_reviews`/`menu_qr_addon_tips`). **No introducidos por PR-B.**
- Onboarding sirve los nuevos precios automáticamente: `apps/web/src/app/app/onboarding/plan/page.tsx` consume `/api/v1/billing/bundles/?vertical=qr_reviews&checkout=true` que ahora devuelve `fixed_price_monthly=20000` (Base) y `28000` (Pro).

---

## 4. Smoke manual

1. **Landing `/resenas`** — Base muestra `$20.000/mes`, Pro muestra `$28.000/mes`. Features de PR-A intactas.
2. **Landing `/pricing?service=qr_reviews`** — Base `$20.000`, Pro `$28.000`. Toggle anual → `$192.000` / `$268.800`.
3. **Checkout nueva alta Base** — `/subscribe?plan_code=qr_reviews_base&billing_period=monthly&vertical=qr_reviews` → `start-checkout` recibe `plan_code='qr_reviews_base'` y crea preferencia MP por **20000**.
4. **Checkout nueva alta Pro** — idem con `qr_reviews_pro` → preferencia MP por **28000**.
5. **Upgrade Base → Pro** — desde `/app/resenas`, click upgrade → `POST /api/v1/billing/reviews/upgrade/` → MP preference con `unit_price=28000`. Success activa Pro y banner usa `is_reviews_pro`.
6. **Downgrade Pro → Base** — desde `/app/resenas`, click downgrade → no toca pagos. Negocio pierde analytics/carteles/estados pero conserva filtro inteligente.

---

## 5. Tests

### Backend (dentro del contenedor `api`)

```powershell
docker compose -f infra/docker-compose.yml exec -T api sh -lc `
  "cd /app && DJANGO_SETTINGS_MODULE=config.settings python manage.py test \
   apps.billing.tests.test_canonical_pricing \
   apps.billing.tests.test_reviews_upgrade \
   apps.billing.tests.test_promo_admin \
   apps.billing.tests.test_promo_cycle \
   apps.billing.tests.test_promo_codes \
   apps.reviews.tests.test_smart_filter_base \
   apps.reviews.tests.test_reviews \
   apps.reviews.tests.test_notifications \
   apps.reviews.tests.test_public_flow \
   apps.reviews.tests.test_e2e_lifecycle \
   apps.reviews.tests.test_stats_cache --noinput"
```

### Frontend (desde `apps/web`)

```powershell
cd apps/web
npx vitest run `
  src/features/reviews/__tests__/product.test.ts `
  src/features/billing/components/__tests__/QrReviewsPlanBuilder.test.tsx `
  src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx
```

> **Nota:** El archivo `src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx` tiene un test pre-existente (`resolves qr_reviews product and uses vertical=qr_reviews for bundles query path`) que falla porque la URL ahora incluye `&checkout=true`. NO es regresión de PR-B. De los tests modificados en esta PR, todos pasan.
>
> Asimismo, `src/lib/pricing/__tests__/pricing.test.ts` tiene 2 tests pre-existentes con conteos desactualizados (`contains 9 plans` espera 9 pero hay 11; `getPlansForVertical('menu_qr')` espera 3 pero hay 4). Tampoco son regresión de PR-B.

---

## 6. Suscripciones activas — política

`pricing.json` + `seed_billing` actualizan los precios de **Plan** y **Bundle** en la DB, pero NO modifican las preapprovals activas de MercadoPago. Esto significa:

- **Clientes nuevos** (después del deploy): cobran $20.000 / $28.000 desde la primera renovación.
- **Clientes con preapproval activa**: siguen cobrándose el monto pactado original (`$25.000` / `$40.000`) hasta que su preapproval se cancele o se actualice manualmente vía MP API.

Opciones (definir antes del deploy productivo):

1. **Grandfather**: dejarlos con el precio histórico. Cero esfuerzo, asimetría temporal.
2. **Migración manual**: equipo CX ejecuta `mercadopago_service.update_preapproval(...)` para bajar `transaction_amount` de cada cliente activo. Requiere comunicación previa (mail) por nota de buena fe.
3. **Comunicación + auto-migración**: enviar email a clientes activos informando la baja de precio + script que actualice las preapprovals en batch.

> **Recomendación**: Opción 3 si el equipo comercial quiere maximizar buena voluntad. Opción 1 es defendible si se quiere preservar ARR existente.

---

## 7. Rollback

Si hay que revertir:

1. Revertir `generated/pricing.json` (4 valores: 192000→240000, 20000→25000, 268800→384000, 28000→40000).
2. Revertir `apps/web/src/lib/pricing/plans.ts` (mismos 4 valores).
3. (Opcional) Revertir cambio de `plan_code` canónico en `QrReviewsPlanBuilder.tsx` solo si causara regresión — preferentemente mantenerlo dado que era un bug pre-existente.
4. Re-correr `seed_billing` para que `billing_plan` y `billing_bundle` queden con los valores viejos.
5. Verificar con queries de la sección 3.2 (valores 25000 / 40000 / 240000 / 384000).
6. Re-deploy frontend y backend.
7. Notificar a CX si ya se enviaron comunicaciones de baja de precio.

---

## 8. Riesgos / pendientes

- **Pre-existente — onboarding bundles test** (`onboarding-service-options.test.tsx`): pasa el guard de literales actualizado en PR-B, pero un test independiente (`bundles query path`) falla por `&checkout=true` agregado en otro PR. Crear issue de seguimiento.
- **Pre-existente — pricing canonical counts** (`pricing.test.ts`): 2 tests con números mágicos desactualizados. Crear issue de seguimiento.
- **Suscripciones activas**: ver sección 6 — requiere decisión comercial antes del deploy productivo.
- **Migraciones históricas** (`0014`, `0016`) hardcodean los precios viejos. Inocuo en entornos ya migrados (seed_billing pisa los valores), pero un entorno nuevo correrá `migrate` → quedará brevemente con valores viejos hasta correr `seed_billing`. Documentado.
