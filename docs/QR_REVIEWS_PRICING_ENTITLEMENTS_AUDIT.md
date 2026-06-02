# Auditoría — Pricing y Entitlements de QR de Reseñas

**Fecha:** 2026-06-02  
**Tipo:** Auditoría de solo lectura (no se modifica producción).  
**Producto:** QR de Reseñas (standalone, separado de Menú QR / Carta Online).  
**Objetivo:** Mapear el estado actual de precios, checkout y entitlements como pre-requisito para una futura PR que cambie tarifas y permisos.  
**Cambio propuesto a futuro (NO ejecutado en esta auditoría):**

| Plan         | Precio actual | Precio propuesto |
|--------------|--------------:|-----------------:|
| Reseñas Base | $25.000/mes   | $20.000/mes      |
| Reseñas Pro  | $40.000/mes ⚠️ | $28.000/mes      |
| Empresarial  | Custom        | Custom           |

> ⚠️ El precio actual de **Reseñas Pro es $40.000/mes** en todas las capas (no $35.000 como se mencionó en el enunciado). El valor $35.000 era el precio histórico — la migración 2026-04-14 lo subió a $40.000 (ver memoria `qr_reviews_implementation_complete.md` y `generated/pricing.json`). Confirmar con producto antes de cualquier PR.

---

## 1. Fuente de verdad de pricing

La arquitectura canónica está documentada en [docs/PRICING_CANONICAL_ARCHITECTURE.md](PRICING_CANONICAL_ARCHITECTURE.md). En resumen:

```
generated/pricing.json   ← ÚNICA fuente de verdad para precios
        │
        ├─► apps/web/src/lib/pricing/plans.ts        (frontend, integers ARS)
        │       ├─ REVIEWS_BASE.priceMonthly = 25000
        │       └─ REVIEWS_PRO.priceMonthly  = 40000
        │
        └─► services/api/src/apps/billing/canonical_pricing.py
                ├─ plan_price('qr_reviews_base','monthly') = 25000
                └─ plan_price('qr_reviews_pro','monthly')  = 40000
                    │
                    ├─► seed_billing.py → Bundle.fixed_price_monthly
                    ├─► seed_billing.py → Plan.price (Decimal pesos)
                    └─► reviews_views.py (upgrade preference)
```

Unidad uniforme: **ARS pesos integers** (no centavos). Existen guards (`assert_not_centavos`, `assert_canonical_match`) en `canonical_pricing.py`.

---

## 2. Tabla — Dónde aparece hoy el pricing

### 2.1 Backend

| Archivo | Línea / referencia | Cómo expone el precio | Lectura/Hardcoded |
|---|---|---|---|
| [generated/pricing.json](../generated/pricing.json) | `qr_reviews_base` / `qr_reviews_pro` | `price_monthly: 25000`, `price_yearly: 240000`; `price_monthly: 40000`, `price_yearly: 384000` | **Hardcoded canónico** |
| [services/api/src/apps/billing/canonical_pricing.py](../services/api/src/apps/billing/canonical_pricing.py) | `plan_price(code, cycle)` | Loader que parsea `pricing.json` y indexa por `code` | Derivado |
| [services/api/src/apps/billing/management/commands/seed_billing.py](../services/api/src/apps/billing/management/commands/seed_billing.py#L411-L450) | Bundle seeds `qr_reviews_base`, `qr_reviews_pro`, `qr_reviews_empresarial` (+ legacy `qr_reviews`) | `fixed_price_monthly = plan_price('qr_reviews_base'/'qr_reviews_pro', 'monthly')` | Derivado |
| [services/api/src/apps/billing/management/commands/seed_billing.py](../services/api/src/apps/billing/management/commands/seed_billing.py#L468-L500) | `PLAN_SEEDS` → `Plan.price` | `price_to_decimal(plan_price(...))` para `qr_reviews`, `qr_reviews_base`, `qr_reviews_pro` | Derivado |
| [services/api/src/apps/billing/reviews_views.py](../services/api/src/apps/billing/reviews_views.py#L100-L160) | `ReviewsUpgradeView.post` | `price = plan_price('qr_reviews_pro', 'monthly')` → enviado a MP como `unit_price` | Derivado |
| DB `billing_plan` (runtime) | filas `qr_reviews`, `qr_reviews_base`, `qr_reviews_pro` | `Plan.price = Decimal('25000.00' / '40000.00')` | Persistido (necesita re-seed) |
| DB `billing_bundle` (runtime) | bundles homónimos | `Bundle.fixed_price_monthly = 25000 / 40000` (int) | Persistido (necesita re-seed) |
| Tests | [test_canonical_pricing.py](../services/api/src/apps/billing/tests/test_canonical_pricing.py), [test_promo_admin.py](../services/api/src/apps/billing/tests/test_promo_admin.py#L309-L390), [test_promo_cycle.py](../services/api/src/apps/billing/tests/test_promo_cycle.py#L114-L347), [test_promo_codes.py](../services/api/src/apps/billing/tests/test_promo_codes.py#L382) | `25000` / `40000` hardcoded en asserts | **Tests hardcoded** |

### 2.2 Frontend

| Archivo | Cómo expone el precio | Hardcoded |
|---|---|---|
| [apps/web/src/lib/pricing/plans.ts](../apps/web/src/lib/pricing/plans.ts#L86-L107) | `REVIEWS_BASE.priceMonthly = 25000`, `REVIEWS_PRO.priceMonthly = 40000` (y `priceYearly` 240000 / 384000) | **Hardcoded canónico** |
| [apps/web/src/features/reviews/product.ts](../apps/web/src/features/reviews/product.ts#L83-L130) | `REVIEW_PRICING_CARDS` consume `REVIEWS_BASE/REVIEWS_PRO` vía `formatPrice(...)` | Derivado |
| [apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx](../apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx#L33-L52) | `QR_REVIEWS_PLANS[]` con `priceMonthly` / `priceYearly` de las constantes canónicas | Derivado |
| [apps/web/src/components/marketing/product-landing/resenas-pricing-section.tsx](../apps/web/src/components/marketing/product-landing/resenas-pricing-section.tsx) | Renderiza `REVIEW_PRICING_CARDS` | Derivado |
| [apps/web/src/app/(marketing)/pricing/pricing-client.tsx](../apps/web/src/app/(marketing)/pricing/pricing-client.tsx#L249-L255) | Monta `<QrReviewsPlanBuilder>` cuando `vertical === 'qr_reviews'` | Derivado |
| [apps/web/src/app/(marketing)/resenas/page.tsx](../apps/web/src/app/(marketing)/resenas/page.tsx) | Landing pública que incluye `<ResenasPricingSection>` | Derivado |
| Tests | [apps/web/src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx](../apps/web/src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx#L134) | Regex `\b(18000|25000|30000|36000|40000|50000|55000|75000)\b` valida ausencia de literales | **Test guard** |

### 2.3 Búsqueda de literales `25000` / `35000` / `25.000` / `35.000` / `20000` / `28000`

- **No se encontró ningún literal `35000` / `35.000`** asociado a precios de QR de Reseñas en código fuente vivo. Aparece en:
  - Tests de POS / split-payment (no relacionados).
  - Seed `seed_gestion_comercial_test_data.py` (costos de productos demo, no relacionados).
- **`25000`** sólo aparece como precio canónico (`pricing.json`, `plans.ts`) y en tests de billing (`test_promo_cycle.py`, `test_promo_admin.py`), no en hardcodes dispersos.
- **`20000` / `28000`** no aparecen como precios de Reseñas. Sólo `20000` aparece en seeds de gestión comercial.

✅ Conclusión: **no hay valores de pricing duplicados u "olvidados" fuera del canónico**. El cambio se propaga editando `generated/pricing.json` + re-seed.

---

## 3. Flujo de checkout → MercadoPago → webhook → activación

### 3.1 Checkout inicial (alta nueva desde landing / onboarding)

```
[/(marketing)/pricing?service=qr_reviews]  o  /app/app/onboarding/plan
                │
                ▼
QrReviewsPlanBuilder → onSubscribe({planCode}) → router.push('/subscribe?plan_code=reviews_pro|reviews_base&billing_period=…&vertical=qr_reviews')
                │
                ▼
/subscribe (page no auditada en detalle) → POST checkout
                │
                ▼ (autenticado)
StartSubscriptionView / OnboardingStartCheckoutView
        → billing.checkout_session_service.start_checkout(user, tenant, plan_code)
        → crea/reusa MpCheckoutSession (idempotencia sha256(user:tenant:plan_code))
        → MercadoPagoService.create_preapproval_plan(Plan.code → Plan.price)
        → init_point devuelto al frontend
                │
                ▼
Usuario paga en MercadoPago
                │
                ▼
MercadoPagoWebhookView (services/api/src/apps/billing/views.py)
        → webhook_processor / subscription_activator
        → crea SubscriptionV2(service_type='qr_reviews', plan_code=<plan>) ACTIVE
        → sincroniza business.Subscription legacy
        → habilita acceso (resolve_subscription)
```

Observaciones clave:
- ⚠️ `QrReviewsPlanBuilder` envía `planCode` con valores **`reviews_base` / `reviews_pro`** (sin prefijo `qr_`). La página `/subscribe` y el backend esperan los códigos canónicos `qr_reviews_base` / `qr_reviews_pro`. Hay que verificar qué hace `/subscribe` con esa transformación antes de tocar precios — la incongruencia es **pre-existente** y no la introdujimos.

### 3.2 Upgrade in-place (Base → Pro, ya activo)

Documentado en memoria `bloque11_reviews_upgrade.md`.

```
[apps/web /app/resenas/* (UpgradeToProButton)]
   POST /api/v1/billing/reviews/upgrade/
   │
   ▼
ReviewsUpgradeView (reviews_views.py)
   - valida plan actual ∈ {qr_reviews, qr_reviews_base}
   - idempotencia: reusa PendingSubscriptionChange existente
   - price = plan_price('qr_reviews_pro','monthly')  # 40000
   - PendingSubscriptionChange(status='pending_payment')
   - MercadoPagoService.create_preference(items=[…], external_reference=f'reviews_upgrade_{pending.id}')
   - back_urls = /app/resenas?upgrade=success|failure|pending&change_id=<id>
   │
   ▼ usuario paga
MercadoPagoWebhookView (billing/views.py L819-L900)
   if external_reference.startswith('reviews_upgrade_'):
       apply_reviews_plan_upgrade(business, 'qr_reviews_pro')
         - business.subscription.plan = 'qr_reviews_pro'
         - SubscriptionV2(service_type='qr_reviews').plan_code = 'qr_reviews_pro' / ACTIVE
   │
   ▼
Frontend (dashboard-client.tsx) lee ?upgrade=success → UpgradeSuccessBanner
   polling getReviewSettings() hasta smart_filter_allowed=true (banner state machine)
```

### 3.3 Downgrade in-place (Pro → Base, inmediato sin pago)

```
DowngradeToBaseButton → POST /api/v1/billing/reviews/downgrade/ {confirm:true}
   ReviewsDowngradeView → apply_reviews_plan_downgrade(business, 'qr_reviews_base')
   (immediate, no MP, sin reembolso ni proration)
```

---

## 4. Entitlements actuales

### 4.1 Tabla maestra

| Plan code        | `business/entitlements.py` (`PLAN_ENTITLEMENTS`) | `business/features.py` (`PLAN_FEATURES`) | `reviews/entitlements.py` |
|------------------|---------------------------------------------------|------------------------------------------|---------------------------|
| `qr_reviews` (legacy) | `qr_reviews.config`, `qr_reviews.qr`, `qr_reviews.dashboard` | `qr_reviews_core` | `reviews_allowed=True`, `is_reviews_pro=False` |
| `qr_reviews_base` | (alias de `qr_reviews`) `qr_reviews.config`, `qr_reviews.qr`, `qr_reviews.dashboard` | `qr_reviews_core` | `reviews_allowed=True`, `is_reviews_pro=False` |
| `qr_reviews_pro` | `qr_reviews.config`, `qr_reviews.qr`, `qr_reviews.dashboard`, **`qr_reviews.print_posters`** | `qr_reviews_core`, **`print_signage`** | `reviews_allowed=True`, `is_reviews_pro=True`, `smart_filter_allowed=True` |
| `qr_reviews_empresarial` | (no definido) — se trata como custom contractual | (no definido) | (resuelve via runtime si SubscriptionV2 activa) |

### 4.2 Capacidades gateadas hoy

| Capacidad UX                                | Gating actual                                                                                  | Plan que la habilita | Ubicación de la verificación |
|---------------------------------------------|------------------------------------------------------------------------------------------------|----------------------|------------------------------|
| Acceso al producto (`/app/resenas`)         | `reviews_allowed(business)` (V2 o legacy) — cualquier plan `qr_reviews*` activo                | Base, Pro            | `apps/web/src/app/app/resenas/layout.tsx`, `reviews/entitlements.reviews_allowed` |
| Generar QR / link compartible               | Entitlement `qr_reviews.qr`                                                                    | Base, Pro            | `reviews/views.py ReviewQRCodeView` |
| Redirección a Google (`mode=direct`)        | Sin gating extra (configurable desde Base)                                                     | Base, Pro            | `review-config-client.tsx` |
| Feedback privado (`mode=smart_filter`)      | `smart_filter_allowed(business)` = **Pro O trial activo de 7 días**                            | **Pro** (y trial)    | `reviews/entitlements.smart_filter_allowed`, `serializers.validate_mode` |
| Pantalla **Feedback** (`/app/resenas/feedback`) | `config.smart_filter_allowed` (Pro o trial)                                                  | Pro (y trial)        | `feedback-client.tsx` L137-L190 |
| Pantalla **Analytics** (`/app/resenas/analytics`) | sidebar `planKey: 'qr_reviews_pro'`; vistas internas chequean entitlement                  | Pro                  | `sidebar.tsx` L175, `analytics-client.tsx` |
| Pantalla **Carteles** (`/app/resenas/carteles`) | Tabs visibles si `is_reviews_pro`; vistas backend exigen `qr_reviews.print_posters`         | Pro                  | `resenas-nav.tsx` L62-L69, `reviews/views.py` L618-L922 |
| Personalización / impresión de carteles      | Entitlement `qr_reviews.print_posters` (403 a Base)                                            | Pro                  | `test_qr_poster_designs.test_qr_reviews_base_plan_returns_403` |
| Estados de gestión (status distribution)     | Visible sólo en `effective_mode === 'smart_filter'`                                            | Pro (vía smart filter) | `dashboard-client.tsx`, `analytics-client.tsx` |
| Métricas de conversión / analytics avanzadas | Sólo Pro (tab y vistas)                                                                        | Pro                  | sidebar + `analytics-client.tsx` |
| **Filtro inteligente (lógica)** ⚠️           | **Sólo Pro** (o trial 7 días). `smart_filter_allowed = is_reviews_pro OR trial_active`         | **Pro**              | `reviews/entitlements.py L77-L88` |

> 🔴 **Hallazgo crítico #1 — Filtro inteligente:** hoy el filtro inteligente es la propuesta de valor *diferencial* de Pro. La matriz propuesta lo mueve a Base. Eso requiere reescribir `smart_filter_allowed()`, los gates de las pantallas Feedback/Analytics y la lógica de trial. **Es un cambio funcional grande, no sólo de pricing.** Ver §6 y §8.

---

## 5. Matriz actual vs propuesta

### 5.1 Matriz **actual** (verificada en código, 2026-06-02)

| Feature                                | Base (`qr_reviews_base`)         | Pro (`qr_reviews_pro`)           |
|----------------------------------------|----------------------------------|----------------------------------|
| Precio mensual                         | $25.000                          | $40.000                          |
| QR y link compartible                  | ✅                               | ✅                               |
| QR descargable simple                  | ✅                               | ✅                               |
| Redirección directa a Google           | ✅                               | ✅                               |
| Filtro inteligente (smart_filter)      | ❌ (sólo trial 7 días)            | ✅                               |
| Feedback privado automático            | ❌ (sólo durante trial)           | ✅                               |
| Pantalla Feedback                       | ❌                               | ✅                               |
| Estados de gestión                      | ❌                               | ✅                               |
| Analytics avanzadas                     | ❌                               | ✅                               |
| Carteles profesionales imprimibles      | ❌ (403 backend)                  | ✅ (`qr_reviews.print_posters`)  |
| Personalización avanzada de carteles    | ❌                               | ✅                               |
| Métricas de conversión                  | ❌                               | ✅                               |

### 5.2 Matriz **propuesta** (objetivo, NO implementada)

| Feature                                | Base ($20.000)                   | Pro ($28.000)                    |
|----------------------------------------|----------------------------------|----------------------------------|
| QR + link compartible + QR descargable | ✅                               | ✅ (incluye todo de Base)        |
| Redirección a Google                   | ✅                               | ✅                               |
| Feedback privado                        | ✅                               | ✅                               |
| **Filtro inteligente**                  | ✅ **(NUEVO en Base)**            | ✅                               |
| Analytics avanzadas                     | ❌                               | ✅                               |
| Estados de gestión                      | ❌                               | ✅                               |
| Carteles profesionales                  | ❌                               | ✅                               |
| Métricas de conversión                  | ❌                               | ✅                               |
| Personalización avanzada                | ❌                               | ✅                               |

Δ neto:
- Precio: Base −$5.000, Pro −$12.000.
- Permisos: el **filtro inteligente y el feedback privado bajan a Base**. Pro retiene Analytics, Carteles, Estados, Métricas y Personalización.

---

## 6. Archivos que habría que tocar en la PR posterior

### 6.1 Cambio de **precios** (alcance acotado, bajo riesgo si se respeta el canónico)

1. [generated/pricing.json](../generated/pricing.json) — actualizar `qr_reviews_base.price_monthly` a `20000` (y `price_yearly` con la fórmula `20000*12*0.8 = 192000`), `qr_reviews_pro.price_monthly` a `28000` (yearly `268800`).
2. [apps/web/src/lib/pricing/plans.ts](../apps/web/src/lib/pricing/plans.ts) — actualizar `REVIEWS_BASE.priceMonthly/priceYearly` y `REVIEWS_PRO.*` (mantener sincronía con `pricing.json`; idealmente verificar que el script de generación es idempotente).
3. Re-ejecutar `python manage.py seed_billing` en cada entorno tras el deploy para propagar a:
   - `billing_plan.price` (filas `qr_reviews`, `qr_reviews_base`, `qr_reviews_pro`).
   - `billing_bundle.fixed_price_monthly` / `fixed_price_yearly`.
4. [apps/web/src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx](../apps/web/src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx#L134) — ajustar regex de literales prohibidos (`25000`/`40000` → `20000`/`28000`).
5. [services/api/src/apps/billing/tests/test_promo_admin.py](../services/api/src/apps/billing/tests/test_promo_admin.py) — actualizar `price=D('25000'|'40000')` a los nuevos.
6. [services/api/src/apps/billing/tests/test_promo_cycle.py](../services/api/src/apps/billing/tests/test_promo_cycle.py) y [test_promo_codes.py](../services/api/src/apps/billing/tests/test_promo_codes.py) — revisar asserts de `discounted_amount` / `transaction_amount`.
7. Comentarios en [seed_billing.py](../services/api/src/apps/billing/management/commands/seed_billing.py#L418-L432) (`# 25000` / `# 40000`) → actualizar.

### 6.2 Cambio de **entitlements** (mover smart_filter a Base)

8. [services/api/src/apps/reviews/entitlements.py](../services/api/src/apps/reviews/entitlements.py) — `smart_filter_allowed()` debe devolver `True` para cualquier suscripción `qr_reviews*` activa (no sólo Pro). Eliminar (o re-semantizar) el concepto de trial de smart_filter.
9. [services/api/src/apps/reviews/serializers.py](../services/api/src/apps/reviews/serializers.py) — `validate_mode` ya consulta `smart_filter_allowed`; revisar mensaje de error.
10. [services/api/src/apps/reviews/models.py](../services/api/src/apps/reviews/models.py) `ReviewConfig.save` — reset automático a `direct` ya consulta `smart_filter_allowed`; verificar que el cambio no migra plans existentes silenciosamente.
11. [apps/web/src/features/reviews/product.ts](../apps/web/src/features/reviews/product.ts) — actualizar `REVIEW_PRICING_CARDS` (highlights de Base y Pro, label de `CTA_DOWNGRADE_TO_BASE` que hoy dice "perderás filtro inteligente").
12. [apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx](../apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx) — `PLAN_KEY_FEATURES` (bullets de cada plan).
13. [apps/web/src/features/reviews/downgrade-to-base-button.tsx](../apps/web/src/features/reviews/downgrade-to-base-button.tsx) y [upgrade-success-banner.tsx](../apps/web/src/features/reviews/upgrade-success-banner.tsx) — el banner hoy hace polling de `smart_filter_allowed` como prueba de que el upgrade activó. Si Base ya lo tiene, el banner debería gatear contra otra capacidad (p.ej. `is_reviews_pro` o `qr_reviews.print_posters`).
14. Trial: el flag `ReviewConfig.trial_*` y la API `trial_active/trial_available/trial_used` quedan huérfanos para smart_filter — decidir si se reaprovecha para otra capacidad (p.ej. Analytics Pro trial) o se deprecan.
15. Documentación operativa: [docs/RUNBOOK_QR_RESENAS_V2.md](RUNBOOK_QR_RESENAS_V2.md) y memorias `bloque11_*` / `bloque12_*` deben reflejar el nuevo gating.

### 6.3 Archivos que **NO** deben tocarse en esta PR

- `apps/web/src/features/billing/data/menu-qr-catalog.ts` y addons de Menú QR — pertenecen a otro vertical.
- `services/api/src/apps/menu/qr_entitlements.py` — sólo cambia el path legacy menu_qr; el cambio nuestro va en `reviews/entitlements.py`.
- Plans Gestión Comercial / Restaurante.

---

## 7. Riesgos para producción

| # | Riesgo | Severidad | Mitigación propuesta |
|---|--------|----------|----------------------|
| 1 | **Suscripciones activas a $25.000 / $40.000** seguirán cobrando ese importe en MP hasta que el cliente reactive. Cambiar `pricing.json` no migra automáticamente las preapprovals existentes. | Alta | Comunicar el cambio comercialmente, decidir si se hace grandfathering o se fuerza re-suscripción. Documentar política antes del deploy. |
| 2 | `Plan.price` vive también en DB (Decimal) y se envía a MP en `create_preapproval_plan`. Si no se re-ejecuta `seed_billing` tras el deploy, las nuevas altas seguirán pagando el precio viejo. | Alta | Incluir `seed_billing` como paso obligatorio del runbook; agregar `assert_canonical_match` al startup. |
| 3 | `Bundle.fixed_price_monthly` (int pesos) en DB se usa para mostrar el plan builder y para snapshots de suscripción. Mismo riesgo de drift que `Plan.price`. | Alta | Idem #2. |
| 4 | **Mover el filtro inteligente a Base habilita la pantalla Feedback** y permite seleccionar `mode=smart_filter` a *todas* las suscripciones Base existentes — incluyendo demos, trials vencidos y cuentas que pueden estar usando el banner "Upgrade a Pro" como CTA. Eso rompe la propuesta de valor de Pro y desactiva CTAs. | Alta | Definir explícitamente qué pasa con cuentas Base activas el día del deploy. Auditar el copy de CTAs y banners post-deploy. |
| 5 | El banner `UpgradeSuccessBanner` hace polling sobre `smart_filter_allowed`. Si Base ya lo tiene, el banner nunca pasará por estado "activating" → "success" porque la condición siempre será true. | Media | Cambiar el gating del banner a `is_reviews_pro` (o `print_posters`) en la misma PR. |
| 6 | El test guard de literales `\b(18000|25000|...|40000)\b` en `onboarding-service-options.test.tsx` fallará en CI si no se actualiza. | Baja | Actualizar regex en la misma PR. |
| 7 | Hay un mismatch pre-existente: `QrReviewsPlanBuilder` envía `planCode: 'reviews_base' / 'reviews_pro'` (sin prefijo). `/subscribe`/backend esperan `qr_reviews_base` / `qr_reviews_pro`. Si el adaptador intermedio falla en algún edge case, el cambio de precio podría enmascararlo. | Media | Auditar la página `/subscribe` antes del deploy (no en alcance de esta auditoría). |
| 8 | Trial de 7 días de smart_filter pierde sentido. Cuentas con `trial_ends_at` futuro al momento del deploy no se verán afectadas (es inocuo), pero el código del trial queda sin lectores válidos. | Baja | Deprecar gradualmente; no eliminar en la misma PR. |
| 9 | `ReviewConfig.save()` resetea `mode='direct'` si `smart_filter_allowed=False`. Tras el cambio, *ningún* business Base activo sufrirá downgrade — pero hay que verificar que no hay migraciones que lo hagan. | Baja | Confirmar; sólo un test manual de regresión. |
| 10 | Promociones existentes con `applies_to_plan_codes=['qr_reviews_pro']` y descuento `Decimal('40000')` quedarán inconsistentes con el nuevo precio. | Media | Auditar tabla `billing_promocode` antes del deploy; ajustar manualmente si hace falta. |

---

## 8. Tests mínimos a agregar / actualizar

### 8.1 Backend (Django)

- [ ] `apps/billing/tests/test_canonical_pricing.py` — agregar asserts duros: `plan_price('qr_reviews_base','monthly') == 20000`, `plan_price('qr_reviews_pro','monthly') == 28000`, `price_yearly` con descuento 20%.
- [ ] `apps/billing/tests/test_reviews_upgrade.py` — actualizar fixture/assert del `unit_price` enviado a MP (`28000.0`).
- [ ] `apps/billing/tests/test_promo_admin.py`, `test_promo_codes.py`, `test_promo_cycle.py` — refrescar precios hardcoded.
- [ ] **Nuevo** `apps/reviews/tests/test_smart_filter_base.py`:
  - Business con `plan='qr_reviews_base'` activo: `smart_filter_allowed(biz) is True`.
  - Mismo business: `PATCH /api/v1/menu/engagement/ {mode: 'smart_filter'}` retorna 200.
  - Mismo business: pantalla Feedback (vista DRF correspondiente) ya no retorna 403.
- [ ] **Nuevo** `apps/reviews/tests/test_carteles_still_pro_only.py`:
  - Business Base: `GET /api/v1/reviews/posters/` retorna 403.
  - Business Pro: 200.
- [ ] **Nuevo** `apps/reviews/tests/test_analytics_still_pro_only.py` — análogo si existe endpoint analytics gateado.
- [ ] Actualizar `apps/reviews/tests/test_e2e_lifecycle.py` casos `trial_*` (eliminar o re-semantizar).
- [ ] `apps/business/tests/test_features.py` (si existe) — verificar que `feature_flags_for_plan('qr_reviews_base')` ahora incluye el flag que el frontend usa para feedback (definir nombre, p.ej. `qr_reviews_smart_filter`).

### 8.2 Frontend (Jest / RTL)

- [ ] Actualizar regex en `apps/web/src/app/app/onboarding/__tests__/onboarding-service-options.test.tsx` (`25000|40000` → `20000|28000`).
- [ ] **Nuevo** `apps/web/src/features/reviews/__tests__/product.test.tsx` (no existe hoy): renderiza `REVIEW_PRICING_CARDS`, assert literal `$20.000` para Base y `$28.000` para Pro, y que el bullet "Filtro inteligente" aparece **también** en Base.
- [ ] **Nuevo** `apps/web/src/app/app/resenas/__tests__/dashboard-base-smart-filter.test.tsx`: mock `getReviewSettings()` con `is_reviews_pro:false, smart_filter_allowed:true` → no debe renderizar `UpgradeToProButton` ni gating de Feedback.
- [ ] **Nuevo** `apps/web/src/features/reviews/__tests__/upgrade-success-banner.test.tsx`: confirmar que el banner ahora gatea sobre `is_reviews_pro` y no sobre `smart_filter_allowed`.

### 8.3 Integración / manual

- [ ] Smoke en staging post-deploy: alta nueva Base → ver tab Feedback habilitado.
- [ ] Smoke en staging: alta nueva Pro → ver tabs Carteles + Analytics habilitados, precio $28.000 en MP preference.
- [ ] Backfill check: query SQL `SELECT plan, COUNT(*), AVG(price) FROM billing_plan WHERE code LIKE 'qr_reviews%'` antes y después del re-seed.

---

## 9. Conclusión y go/no-go

✅ **Pre-requisitos cumplidos para una PR de pricing-only** (sólo cambiar montos):
- Fuente de verdad centralizada y consumida en cascada.
- Sin literales dispersos en producción.
- Tests guards existentes detectarán inconsistencias.
- Camino claro: editar 2 archivos canónicos + re-seed.

🔴 **Bloqueantes para una PR de pricing + entitlements** (lo que el enunciado pide en realidad):
- Mover `smart_filter` a Base es un **cambio de modelo de gating**, no un toggle. Requiere reescribir `reviews/entitlements.smart_filter_allowed`, actualizar el trial, el banner de upgrade, los CTAs y las pantallas de Feedback/Analytics.
- Existen suscripciones activas en producción al precio viejo — la política de grandfathering debe definirse antes de tocar `pricing.json`.
- El `UpgradeSuccessBanner` y `DowngradeToBaseButton` están acoplados al diferencial actual ("vas a perder filtro inteligente").

**Recomendación operativa:** dividir el trabajo en **dos PRs separadas**:
1. **PR-A** (gating): mover `smart_filter` a Base + adaptar UX + tests. Sin tocar precios. Permite validar la regresión funcional aislada.
2. **PR-B** (pricing): editar `pricing.json` + `plans.ts` + tests + runbook de re-seed. Coordinada con comms y política de grandfathering.

---

## Apéndice — Pantallas que consumen la matriz de pricing

| Ruta                                                        | Componente raíz                                  | Plan/precio que muestra                                |
|-------------------------------------------------------------|--------------------------------------------------|---------------------------------------------------------|
| `/resenas` (landing público marketing)                       | [ResenasPage](../apps/web/src/app/(marketing)/resenas/page.tsx) → `ResenasPricingSection` | `REVIEW_PRICING_CARDS` (Base / Pro / Empresarial)       |
| `/pricing?service=qr_reviews` (público)                      | [PricingClient](../apps/web/src/app/(marketing)/pricing/pricing-client.tsx) → `QrReviewsPlanBuilder` | Base / Pro vía `lib/pricing` (toggle mensual/anual)     |
| `/app/planes` (usuario logueado)                             | [page.tsx](../apps/web/src/app/app/planes/page.tsx) | Redirige a `/pricing?service=qr_reviews` (no muestra precio) |
| `/app/resenas` (dashboard)                                    | `dashboard-client.tsx`                           | CTAs upgrade (sin precio) + `UpgradeToProButton`        |
| `/app/resenas/configuracion`                                 | `review-config-client.tsx`                       | `UpgradeToProButton` + `DowngradeToBaseButton`          |
| Admin de suscripciones                                       | No hay UI específica de QR Reseñas — usa `lib/admin/display.ts` para nombres | Plan code → label |
| Onboarding (`/app/onboarding/plan` → checkout)               | `onboarding/plan/page.tsx` → POST `/api/v1/billing/...` | `Bundle.fixed_price_monthly` (DB) servido por bundles API |
