# Auditoría Técnica y Funcional: Sistema de Planes, Pricing y Suscripciones

> **Fecha:** Julio 2025  
> **Alcance:** `/app/servicios`, `/app/gestion/configuracion/plan-facturacion`, marketing/landings, backend billing  
> **Directiva:** El precio oficial vigente es el mostrado en las cards de pricing y landings de cada vertical.

---

## 1. Resumen Ejecutivo

El sistema de planes y pricing de Mi Rubro presenta **una desalineación crítica de precios** entre la capa de marketing/catálogo (lo que el usuario VE) y la capa de backend/checkout (lo que se COBRA).

**Precios oficiales** (marketing cards/landings): $36.000 / $50.000 / $75.000 ARS/mes para Gestión Comercial.  
**Precios en backend** (commercial_plans.py → MercadoPago): $99 / $299 / $499 ARS/mes.

Esto significa que si un usuario completa un checkout, se le cobraría **~360x menos** de lo anunciado. El mismo patrón se replica en addons y extras.

### Hallazgos Críticos

| # | Severidad | Hallazgo |
|---|-----------|----------|
| 1 | 🔴 CRÍTICO | Backend cobra $99 cuando el catálogo anuncia $36.000 (Starter) |
| 2 | 🔴 CRÍTICO | 6 precios de addons/extras desalineados entre frontend y backend |
| 3 | 🟠 ALTO | `plan-comparison.tsx` y `plan-change-dialog.tsx` muestran precios del backend, no los oficiales |
| 4 | 🟠 ALTO | No existe fuente canónica única — precios duplicados en 4+ archivos |
| 5 | 🟡 MEDIO | QR Reseñas tiene precios inline hardcodeados (no usa catálogo dedicado) |
| 6 | 🟡 MEDIO | `CommercialPlanBuilder.tsx` y `PlansBuilderWizard.tsx` están ocultos con `false &&` pero usan API con precios viejos |
| 7 | 🟢 INFO  | `plan-facturacion` no muestra precios — solo estado de suscripción |

---

## 2. Mapa de Precios Oficiales Vigentes

> Fuente de verdad definida por directiva de negocio: los precios publicados en marketing cards/landings.

### Gestión Comercial

| Plan | Mensual (ARS) | Anual (ARS) | Fuente |
|------|---------------|-------------|--------|
| Starter | $36.000 | $345.600 | `gestion-comercial-catalog.ts` L374-375 |
| Pro | $50.000 | $480.000 | `gestion-comercial-catalog.ts` L383-384 |
| Business | $75.000 | $720.000 | `gestion-comercial-catalog.ts` L392-393 |

**Addons GC:**

| Addon | Mensual | Anual | Fuente |
|-------|---------|-------|--------|
| CRM | $8.000 | $76.800 | `gestion-comercial-catalog.ts` ADDONS |
| Facturación Electrónica | $15.000 | $144.000 | `gestion-comercial-catalog.ts` ADDONS |

**Extras GC:**

| Extra | Mensual | Anual | Fuente |
|-------|---------|-------|--------|
| Sucursal adicional | $12.000 | $115.200 | `gestion-comercial-catalog.ts` EXTRAS |
| Usuario adicional | $5.000 | $48.000 | `gestion-comercial-catalog.ts` EXTRAS |

### Menú QR Online

| Plan | Mensual (ARS) | Anual (ARS) | Fuente |
|------|---------------|-------------|--------|
| Lite | $18.000 | $172.800 | `menu-qr-catalog.ts` L83-84 |
| Pro | $30.000 | $288.000 | `menu-qr-catalog.ts` L92-93 |
| Premium | $55.000 | $528.000 | `menu-qr-catalog.ts` L101-102 |

**Addons Menú QR (solo plan Pro):**

| Addon | Mensual | Anual | Fuente |
|-------|---------|-------|--------|
| Google Reviews | $12.000 | $115.200 | `menu-qr-catalog.ts` L114-120 |
| Propinas (MP) | $12.000 | $115.200 | `menu-qr-catalog.ts` L123-129 |

### QR de Reseñas

| Plan | Mensual (ARS) | Anual (ARS) | Fuente |
|------|---------------|-------------|--------|
| QR Reseñas (Base) | $25.000 | $240.000 | `QrReviewsPlanBuilder.tsx` L42-43 (inline) |
| Reseñas Pro | $35.000 | $336.000 | `QrReviewsPlanBuilder.tsx` L50-51 (inline) |

> ⚠️ QR Reseñas NO tiene archivo de catálogo dedicado. Los precios están duplicados entre `QrReviewsPlanBuilder.tsx` (numérico) y `reviews/product.ts` (strings de display como `"$25.000"`).

### Descuento anual

Fórmula uniforme: `mensual × 12 × 0.8 = anual` (20% de descuento). Verificada para todas las verticales.

---

## 3. Mapa de Fuentes de Verdad (Estado Actual)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FUENTES DE PRECIOS                              │
│                                                                     │
│  ┌─ MARKETING (Oficial vigente) ─────────────────────────────────┐  │
│  │ gestion-comercial-catalog.ts  → GC: $36k/$50k/$75k (pesos)   │  │
│  │ menu-qr-catalog.ts           → QR: $18k/$30k/$55k (pesos)    │  │
│  │ QrReviewsPlanBuilder.tsx      → Rev: $25k/$35k (pesos,inline) │  │
│  │ reviews/product.ts            → Rev: "$25.000"/"$35.000" (str)│  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ BACKEND (Desactualizado) ────────────────────────────────────┐  │
│  │ commercial_plans.py           → GC: 9900/29900/49900 (¢)     │  │
│  │   → Alimenta: preview, checkout, subscription API             │  │
│  │   → MP cobra: $99/$299/$499 ARS                               │  │
│  │ seed_billing.py               → Bundles DB: mismos valores    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ HARDCODED FRONTEND (Copia del backend) ──────────────────────┐  │
│  │ plan-comparison.tsx           → GC: 9900/29900/49900 (¢)     │  │
│  │ plan-change-dialog.tsx        → Addons: "$20","$150","$50","$5"│  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Tabla de Discrepancias

| Ítem | Precio Oficial (pesos) | Backend (centavos → pesos) | Factor de error |
|------|----------------------|---------------------------|-----------------|
| GC Starter | $36.000/mes | 9.900¢ → $99/mes | **364×** |
| GC Pro | $50.000/mes | 29.900¢ → $299/mes | **167×** |
| GC Business | $75.000/mes | 49.900¢ → $499/mes | **150×** |
| Addon CRM | $8.000/mes | 2.000¢ → $20/mes | **400×** |
| Addon Facturación | $15.000/mes | 15.000¢ → $150/mes | **100×** |
| Extra Sucursal | $12.000/mes | 5.000¢ → $50/mes | **240×** |
| Extra Usuario | $5.000/mes | 500¢ → $5/mes | **1.000×** |

### Unidades de precio — diferencia clave

| Capa | Unidad | Ejemplo | Formato |
|------|--------|---------|---------|
| Catálogos frontend | **ARS pesos** | `36000` = $36.000 | `formatArsPrice()` — sin dividir por 100 |
| Backend + hardcoded | **Centavos** | `9900` = $99 | `formatPrice()` — divide por 100 |
| MercadoPago | **Pesos (float)** | `99.00` | Backend divide unit_price / 100.0 |

---

## 4. Hallazgos por Ruta

### 4.1 `/app/servicios` (billing-page-client.tsx)

**Componentes involucrados:**
- `billing-page-client.tsx` — Dashboard principal de billing para servicio Gestión
- `plan-comparison.tsx` — Grid de comparación de planes (se muestra al cambiar plan)
- `plan-change-dialog.tsx` — Modal de configuración pre-checkout

**Flujo de datos:**

```
billing-page-client.tsx
  ↓ GET /api/v1/billing/commercial/subscription/
  ↓ (CommercialSubscriptionView → get_plan_config() → commercial_plans.py)
  ↓ Respuesta: current_plan.pricing.monthly = 9900 (centavos)
  ↓ formatPrice(9900) → "$99"
  ↓
  ├─ PlanComparison (hardcoded PLANS[]: 9900/29900/49900)
  │   ↓ formatPrice(9900) → "$99"
  │
  └─ PlanChangeDialog
      ↓ POST /api/v1/billing/commercial/preview-change/
      ↓ (preview.py → commercial_plans.py → line_items con precios viejos)
      ↓ Muestra: CRM "$20/mes", Facturación "$150/mes" (HARDCODED en JSX)
      ↓ Sucursal extra "× $50/mes", Usuario extra "× $5/mes" (HARDCODED en JSX)
      ↓ Total calculado = preview.total_recurring (con precios viejos)
      ↓
      └─ POST /api/v1/billing/commercial/checkout/
          ↓ Crea preferencia MP con unit_price/100.0
          ↓ COBRA $99 / $299 / $499 en vez de $36.000 / $50.000 / $75.000
```

**Hallazgos:**

| # | Componente | Problema | Archivo:Línea |
|---|------------|----------|---------------|
| 4.1.1 | `plan-comparison.tsx` | PLANS[] hardcoded con 9900/29900/49900 (centavos, precios viejos) | `plan-comparison.tsx` L27-29, L47-48, L64-65 |
| 4.1.2 | `plan-comparison.tsx` | `formatPrice()` divide por 100 → muestra "$99" en vez de "$36.000" | `plan-comparison.tsx` L103 |
| 4.1.3 | `plan-change-dialog.tsx` | CRM hardcoded como "$20/mes" | `plan-change-dialog.tsx` ~L211 |
| 4.1.4 | `plan-change-dialog.tsx` | Facturación hardcoded como "$150/mes" | `plan-change-dialog.tsx` ~L222 |
| 4.1.5 | `plan-change-dialog.tsx` | Sucursal extra "× $50/mes" | `plan-change-dialog.tsx` ~L255 |
| 4.1.6 | `plan-change-dialog.tsx` | Usuario extra "× $5/mes" | `plan-change-dialog.tsx` ~L280 |
| 4.1.7 | `billing-page-client.tsx` | Muestra precios de API (commercial_plans.py) vía `formatPrice()` | Indirecto vía API |
| 4.1.8 | API preview | `preview_subscription_change()` calcula totales con precios $99/$299/$499 | `preview.py` L121-192 |
| 4.1.9 | API checkout | MercadoPago recibe `unit_price = 99.00` en vez de `36000.00` | `commercial_views.py` ~L438 |

**Riesgo:** Si un usuario ejecuta un cambio de plan hoy, vería un checkout de ~$99 y pagaría eso — **discrepancia financiera directa**.

### 4.2 `/app/gestion/configuracion/plan-facturacion` (plan-billing-client.tsx)

**Componentes:** `plan-billing-client.tsx` únicamente.

**Flujo de datos:**
```
plan-billing-client.tsx
  ↓ GET /api/v1/billing/subscription-status/
  ↓ Muestra: plan_name, status, current_period_end, max_seats, max_branches
  ↓ POST /api/v1/billing/cancel-subscription/ (si owner)
  ↓ POST /api/v1/billing/undo-cancel/ (si cancellation scheduled)
```

**Hallazgos:**

| # | Problema | Severidad |
|---|----------|-----------|
| 4.2.1 | No muestra precios — solo estado, nombre de plan, fecha de renovación y límites | 🟢 Sin impacto directo |
| 4.2.2 | No hay link cruzado hacia `/app/servicios` para cambiar plan | 🟡 UX mejorable |
| 4.2.3 | Cancellation solo disponible para OWNER (correcto per-design) | 🟢 OK |

**Conclusión:** Esta ruta NO tiene problemas de pricing. Es read-only del estado de suscripción.

---

## 5. Hallazgos por Componente

### 5.1 Componentes de Marketing (Oficiales — OK)

| Componente | Fuente de Precios | Estado |
|------------|-------------------|--------|
| `GestionComercialPlanBuilder.tsx` | Importa `GC_PLANS` del catálogo | ✅ Correcto |
| `MenuQrPlanBuilder.tsx` | Importa `QR_PLANS` del catálogo | ✅ Correcto |
| `gestion-pricing-section.tsx` | Importa `GC_PLANS` del catálogo | ✅ Correcto |
| `carta-pricing-section.tsx` | Importa `QR_PLANS` del catálogo | ✅ Correcto |
| `resenas-pricing-section.tsx` | Importa `REVIEW_PRICING_CARDS` | ✅ Correcto |
| `pricing-client.tsx` | Orquesta builders, no tiene precios propios | ✅ Correcto |

### 5.2 Componentes de Billing (Problemáticos)

| Componente | Fuente de Precios | Problema |
|------------|-------------------|----------|
| `plan-comparison.tsx` | HARDCODED `PLANS[]` con 9900/29900/49900 centavos | 🔴 Precios viejos |
| `plan-change-dialog.tsx` | HARDCODED strings "$20", "$150", "$50", "$5" | 🔴 Precios viejos |
| `billing-page-client.tsx` | API commercial/subscription (vía commercial_plans.py) | 🟠 Hereda precios viejos del backend |
| `CommercialPlanBuilder.tsx` | `useBundles('commercial')` API + hardcoded ADDON_PRICES | 🟠 Oculto con `false &&` pero usa API vieja |
| `PlansBundles.tsx` | `useBundles(vertical)` API | 🟠 Fallback genérico, precios de bundles DB |
| `PlansBuilderWizard.tsx` | `useModules(vertical)` + `useQuote()` API | 🟠 Oculto con `false &&` |

### 5.3 QR Reseñas (Caso Especial)

| Componente | Problema |
|------------|----------|
| `QrReviewsPlanBuilder.tsx` | Precios correctos ($25.000/$35.000) pero INLINE, no desde catálogo | 🟡 |
| `reviews/product.ts` | Tiene `REVIEW_PRICING_CARDS` con strings — es para display de marketing | 🟡 Dual source |

---

## 6. Diagnóstico de Arquitectura

### 6.1 Problema Central: Dos Sistemas de Precios Desconectados

```
ARQUITECTURA ACTUAL (Rota)
══════════════════════════

┌──────────────────┐         ┌──────────────────┐
│   MARKETING      │         │   BILLING/APP    │
│   (Catálogos TS) │         │   (Backend Py)   │
│                  │         │                  │
│ $36k/$50k/$75k   │◄─ NO ─►│ $99/$299/$499    │
│ (pesos)          │ SYNC    │ (centavos→pesos) │
│                  │         │                  │
│ Renderiza cards  │         │ Calcula checkout │
│ pricing page     │         │ Preview, MP pago │
│ landing pages    │         │ Subscription API │
└──────────────────┘         └──────────────────┘
        │                            │
        ▼                            ▼
   Usuario VE                  Usuario PAGA
   $36.000/mes                 $99/mes
```

### 6.2 Problemas Específicos

1. **Sin fuente canónica única:** Los catálogos TS no alimentan al backend. El backend tiene su propio `commercial_plans.py` con valores diferentes.

2. **Unidades mixtas:** Los catálogos usan pesos enteros (`36000`). El backend usa centavos (`9900`). La función `formatArsPrice()` no divide por 100 (espera pesos). La función `formatPrice()` en billing SÍ divide por 100 (espera centavos).

3. **Hardcoding triple:**
   - Catálogos TS (pesos, oficial)
   - commercial_plans.py (centavos, viejo)
   - plan-comparison.tsx / plan-change-dialog.tsx (centavos + strings, viejo)

4. **Checkout con precios equivocados:** El flujo `preview → checkout → MercadoPago` consume exclusivamente `commercial_plans.py`. El catálogo TS jamás se consulta para transacciones.

5. **Bundles en DB desalineados:** `seed_billing.py` siembra bundles con los precios de `commercial_plans.py`, no los del catálogo.

### 6.3 Flujo Ideal vs. Estado Actual

| Paso | Ideal | Estado Actual |
|------|-------|---------------|
| Usuario ve precio en landing | $36.000 ← catálogo | $36.000 ← catálogo ✅ |
| Usuario ve precio en `/app/servicios` | $36.000 | $99 ← backend ❌ |
| Preview de cambio de plan | $36.000 | $99 ← commercial_plans.py ❌ |
| MercadoPago cobra | $36.000 | $99 ← backend/100 ❌ |
| Plan guardado en DB | $36.000 | $99 ← seed_billing ❌ |

---

## 7. Plan de Remediación

### Fase 1 — Corrección Backend (Crítica, Inmediata)

| # | Acción | Archivo | Detalle |
|---|--------|---------|---------|
| 1.1 | Actualizar PLANS en commercial_plans.py | `commercial_plans.py` L86-124 | Starter: 3600000¢, Pro: 5000000¢, Business: 7500000¢ |
| 1.2 | Actualizar ADDONS en commercial_plans.py | `commercial_plans.py` L56-73 | CRM: 800000¢, Invoicing: 1500000¢ |
| 1.3 | Actualizar BRANCH_EXTRA_PRICING | `commercial_plans.py` L44-47 | monthly: 1200000¢ ($12.000) |
| 1.4 | Actualizar SEAT_EXTRA_PRICING | `commercial_plans.py` L49-52 | monthly: 500000¢ ($5.000) |
| 1.5 | Actualizar seed_billing.py | `seed_billing.py` | Sincronizar con nuevos precios |
| 1.6 | Recalcular precios yearly | Todos los anteriores | `monthly × 12 × 0.8` |

> **NOTA sobre unidades:** Si el backend trabaja en centavos y el catálogo en pesos, considerar si conviene unificar a pesos en todo el stack (ver Fase 3).

### Fase 2 — Corrección Frontend Billing (Alta, junto con Fase 1)

| # | Acción | Archivo | Detalle |
|---|--------|---------|---------|
| 2.1 | Reemplazar PLANS[] hardcoded en plan-comparison | `plan-comparison.tsx` | Importar de `gestion-comercial-catalog.ts` o del API actualizado |
| 2.2 | Eliminar strings hardcoded de addons en plan-change-dialog | `plan-change-dialog.tsx` | CRM, Facturación, Branch, Seat → consumir de API o catálogo |
| 2.3 | Unificar `formatPrice()` con `formatArsPrice()` | Ambos archivos | Una sola función de formato, unidad consistente |

### Fase 3 — Formalización Arquitectónica (Estructural)

| # | Acción | Detalle |
|---|--------|---------|
| 3.1 | Definir unidad canónica | Elegir: ¿pesos enteros o centavos? Recomendación: **centavos** (estándar en payment processors) |
| 3.2 | Crear paquete compartido de precios | `packages/pricing/` — exporta tipos y constantes consumibles por frontend Y backend |
| 3.3 | Crear catálogo de QR Reseñas | `reviews-catalog.ts` — mover precios inline de `QrReviewsPlanBuilder.tsx` a archivo dedicado |
| 3.4 | API endpoint de precios públicos | `GET /api/v1/billing/pricing/` → sirve precios vigentes desde la fuente canónica |
| 3.5 | Migrar componentes de billing a catálogos | `plan-comparison.tsx`, `plan-change-dialog.tsx` → importar de catálogos |
| 3.6 | Cleanup componentes ocultos | Decidir sobre `CommercialPlanBuilder.tsx` y `PlansBuilderWizard.tsx` (gated `false &&`) — eliminar o migrar |

### Fase 4 — Validación y Tests

| # | Acción | Detalle |
|---|--------|---------|
| 4.1 | Test E2E de checkout | Verificar que MP recibe los precios correctos |
| 4.2 | Test de consistencia | Automated check: catálogo frontend == backend commercial_plans |
| 4.3 | Test de preview | Verificar line_items con precios actualizados |
| 4.4 | Snapshot de precios | Test que falla si un precio cambia sin actualizar todas las fuentes |

---

## 8. Propuesta de Implementación

### Opción A: Quick Fix (mínimo viable, 1-2 días)

Actualizar `commercial_plans.py` con los precios oficiales en centavos, actualizar `seed_billing.py`, actualizar los hardcoded en `plan-comparison.tsx` y `plan-change-dialog.tsx`.

**Pros:** Rápido, resuelve la discrepancia de cobro.  
**Contras:** Sigue habiendo 3+ fuentes de precios desconectadas; require discipline manual para mantener sync.

### Opción B: Consolidación (recomendada, 3-5 días)

1. Crear `packages/pricing/` con un diccionario canónico de precios exportable a TS y generador para Python.
2. Migrar `commercial_plans.py` a consumir de un archivo JSON compartido o generar desde el mismo.
3. Migrar `plan-comparison.tsx` y `plan-change-dialog.tsx` a importar del catálogo o del API.
4. Unificar funciones de formato (`formatPrice` / `formatArsPrice`) en una sola con la unidad canónica.
5. Agregar tests de consistencia cross-layer.

**Pros:** Una única fuente de verdad real; cambios de precio son atómicos.  
**Contras:** Más trabajo upfront; requiere decisión sobre unidad canónica.

### Opción C: API-First (máxima flexibilidad, 5-7 días)

Todo lo de Opción B, más:
1. `GET /api/v1/billing/pricing/` endpoint público que sirve precios vigentes.
2. Marketing pages y billing pages consumen del mismo endpoint (SSR o SWR).
3. Admin panel para actualizar precios sin deploy.

**Pros:** Precios actualizables sin deploy; single source of truth vía DB/API.  
**Contras:** Mayor complejidad; dependency de red para mostrar precios.

---

## 9. Propuesta de Formalización de Precios

### 9.1 Formato Canónico Propuesto

```typescript
// packages/pricing/src/plans.ts (o JSON importable)
export const OFFICIAL_PRICING = {
  currency: 'ARS',
  unit: 'centavos', // 100 centavos = 1 peso
  annualDiscount: 0.20, // 20%

  verticals: {
    gestion_comercial: {
      plans: {
        starter:  { monthly: 3_600_000, yearly: 34_560_000 },
        pro:      { monthly: 5_000_000, yearly: 48_000_000 },
        business: { monthly: 7_500_000, yearly: 72_000_000 },
      },
      addons: {
        crm:       { monthly: 800_000, yearly: 7_680_000, availableFor: ['starter'], includedIn: ['pro','business'] },
        invoicing: { monthly: 1_500_000, yearly: 14_400_000, availableFor: ['starter'], includedIn: ['pro','business'] },
      },
      extras: {
        branch: { monthly: 1_200_000, yearly: 11_520_000 },
        seat:   { monthly: 500_000, yearly: 4_800_000 },
      },
    },
    menu_qr: {
      plans: {
        lite:    { monthly: 1_800_000, yearly: 17_280_000 },
        pro:     { monthly: 3_000_000, yearly: 28_800_000 },
        premium: { monthly: 5_500_000, yearly: 52_800_000 },
      },
      addons: {
        reviews: { monthly: 1_200_000, yearly: 11_520_000 },
        tips:    { monthly: 1_200_000, yearly: 11_520_000 },
      },
    },
    qr_reviews: {
      plans: {
        reviews_base: { monthly: 2_500_000, yearly: 24_000_000 },
        reviews_pro:  { monthly: 3_500_000, yearly: 33_600_000 },
      },
    },
  },
} as const;
```

> **Nota:** Si se adopta centavos como unidad canónica, los catálogos actuales (que usan pesos) deben migrar sus valores. Ejemplo: `priceMonthly: 36000` pesos → `priceMonthly: 3_600_000` centavos.
>
> **Alternativa simplificada:** Si se prefiere mantener pesos como unidad (más legible, los catálogos ya lo usan), ajustar el backend para trabajar en pesos y cambiar la conversión a MP: `unit_price = amount` (sin dividir por 100). En este caso, `OFFICIAL_PRICING` usaría pesos directos y los valores serían los mismos que los catálogos actuales.

### 9.2 Regla de Consistencia

Todo precio mostrado al usuario, cobrado vía MP, o almacenado en DB, DEBE provenir de la fuente canónica:

```
OFFICIAL_PRICING (packages/pricing/)
        │
        ├──► Frontend catálogos (GC_PLANS, QR_PLANS, etc.) — importan
        ├──► Backend commercial_plans.py — importa o lee del mismo JSON
        ├──► seed_billing.py — genera desde OFFICIAL_PRICING
        ├──► Componentes billing — importan de catálogos o API
        └──► MercadoPago checkout — calcula desde OFFICIAL_PRICING
```

### 9.3 Validación Automática Propuesta

```python
# Test: backend/tests/test_pricing_consistency.py
def test_all_plans_match_canonical_pricing():
    """Verifica que commercial_plans.py refleja los precios canónicos."""
    canonical = load_canonical_pricing()  # Lee de packages/pricing/
    for plan in PLANS:
        expected = canonical['verticals']['gestion_comercial']['plans'][plan['code']]
        assert plan['pricing']['monthly'] == expected['monthly']
        assert plan['pricing']['yearly'] == expected['yearly']
```

---

## 10. Checklist Final de Producción

### Pre-Deploy

- [ ] `commercial_plans.py` PLANS actualizado con precios oficiales
- [ ] `commercial_plans.py` ADDONS actualizado (CRM, Facturación)
- [ ] `commercial_plans.py` BRANCH_EXTRA_PRICING y SEAT_EXTRA_PRICING actualizados
- [ ] `seed_billing.py` sincronizado con nuevos precios
- [ ] `plan-comparison.tsx` PLANS[] actualizado o migrado a importar del catálogo
- [ ] `plan-change-dialog.tsx` strings de addons/extras actualizados o consumidos dinámicamente
- [ ] `formatPrice()` unificado con unidad correcta
- [ ] Tests de preview verifican line_items con precios nuevos
- [ ] Test de checkout verifica MP recibe precios correctos
- [ ] `QrReviewsPlanBuilder.tsx` precios extraídos a catálogo dedicado (deseable)

### Post-Deploy

- [ ] Verificar en staging: `/pricing` muestra mismos precios que `/app/servicios`
- [ ] Verificar preview de cambio de plan devuelve totales coherentes
- [ ] Verificar preferencia de MP tiene unit_price correcto
- [ ] Verificar suscripciones existentes no se ven afectadas adversamente
- [ ] Ejecutar seed_billing en staging para actualizar bundles en DB
- [ ] Monitorear logs de billing 24h post-deploy

### Suscripciones Existentes

> ⚠️ **Atención:** Usuarios con suscripciones activas a precios viejos deben ser gestionados por negocio:
> - Opción A: Grandfather (mantener precio viejo hasta renovación)
> - Opción B: Migrar al precio nuevo en próxima renovación
> - Opción C: Notificar y migrar inmediatamente
> Esto requiere decisión de negocio, no solo técnica.

---

## Anexo A: Inventario Completo de Archivos

### Frontend — Fuentes de Precios

| Archivo | Rol | Precios |
|---------|-----|---------|
| `features/billing/data/gestion-comercial-catalog.ts` | Catálogo GC (oficial) | $36k/$50k/$75k + addons + extras |
| `features/billing/data/menu-qr-catalog.ts` | Catálogo QR (oficial) | $18k/$30k/$55k + addons |
| `features/reviews/product.ts` | Marketing QR Reseñas | "$25.000"/"$35.000" (strings) |
| `features/billing/components/QrReviewsPlanBuilder.tsx` | Builder QR Reseñas | 25000/35000 (inline, pesos) |
| `components/gestion/plan-comparison.tsx` | Comparador billing | 9900/29900/49900 (centavos, VIEJOS) |
| `components/gestion/plan-change-dialog.tsx` | Modal pre-checkout | "$20","$150","$50","$5" (strings, VIEJOS) |

### Frontend — Componentes de Renderizado

| Archivo | Usa Catálogo | Usa API | Estado |
|---------|-------------|---------|--------|
| `GestionComercialPlanBuilder.tsx` | ✅ GC_PLANS | ❌ | Activo, correcto |
| `MenuQrPlanBuilder.tsx` | ✅ QR_PLANS | ❌ | Activo, correcto |
| `QrReviewsPlanBuilder.tsx` | ❌ (inline) | ❌ | Activo, precios correctos pero inline |
| `CommercialPlanBuilder.tsx` | ❌ | ✅ useBundles | Oculto (`false &&`) |
| `PlansBundles.tsx` | ❌ | ✅ useBundles | Fallback genérico |
| `PlansBuilderWizard.tsx` | ❌ | ✅ useModules+useQuote | Oculto (`false &&`) |

### Frontend — Hooks de Billing

| Hook | Endpoint | Usado en |
|------|----------|----------|
| `useSubscriptionStatusQuery()` | `GET /billing/subscription-status/` | plan-billing-client.tsx |
| `useCancelSubscriptionMutation()` | `POST /billing/cancel-subscription/` | plan-billing-client.tsx |
| `useUndoCancelSubscriptionMutation()` | `POST /billing/undo-cancel/` | plan-billing-client.tsx |
| `useBundles(vertical)` | `GET /billing/bundles/` | CommercialPlanBuilder, PlansBundles |
| `useModules(vertical)` | `GET /billing/modules/` | PlansBuilderWizard |
| `useQuote()` | `POST /billing/quote/` | PlansBuilderWizard |

### Backend — Fuentes de Precios

| Archivo | Rol | Precios |
|---------|-----|---------|
| `billing/commercial_plans.py` | Config centralizada GC | 9900/29900/49900 centavos (VIEJOS) |
| `billing/management/commands/seed_billing.py` | Seeder de DB | Mismos precios viejos |
| `billing/services/commercial/preview.py` | Cálculo de preview | Consume commercial_plans.py |
| `billing/commercial_views.py` | Views REST | Consume commercial_plans.py |

---

## Anexo B: Navegación entre Rutas

| Desde | Hacia | Link Directo |
|-------|-------|-------------|
| Sidebar | `/app/servicios` | ✅ "Planes y upgrades" |
| Sidebar | `/app/gestion/configuracion/plan-facturacion` | ✅ "Plan y Facturación" |
| `/app/servicios` → `/plan-facturacion` | ❌ No existe |
| `/plan-facturacion` → `/app/servicios` | ❌ No existe |
| Landing `/gestion` | `/pricing?service=commerce` | ✅ via pricing section CTA |
| `/pricing` | Checkout (si logueado) | Via plan builders → subscribe flow |

---

## Anexo C: Session/Auth Subscription Shape

```typescript
// Lo que devuelve /api/v1/auth/me/
session.subscription = {
  plan: string;           // 'starter' | 'pro' | 'business' | ...
  status: string;         // 'active' | 'trialing' | 'past_due' | 'suspended' | 'canceled'
  access_allowed: boolean;
  reason_code: string;    // 'access_granted' | 'grace_period_active' | ...
  grace_until: string | null;
  access_until: string | null;
  show_renewal_prompt: boolean;
  source: string;         // 'v2' | 'legacy' | 'none'
}
```

> **Nota:** La sesión NO incluye información de precios. Los precios se obtienen de endpoints separados (commercial/subscription/) o de los catálogos estáticos.
