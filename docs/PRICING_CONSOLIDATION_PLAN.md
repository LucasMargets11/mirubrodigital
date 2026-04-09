# Consolidación de Pricing: Propuesta de Implementación

> **Fecha:** Abril 2026
> **Base:** Auditoría `PRICING_AUDIT_FULL.md`
> **Directiva:** La fuente canónica de precios es la que hoy usan marketing/landings/cards.

---

## 1. Decisión de Arquitectura Recomendada

### Opción elegida: A — Catálogos frontend como fuente canónica

**NO se crea un `packages/pricing/` compartido.** Se formalizan los catálogos que ya existen en `apps/web/src/features/billing/data/` como la fuente canónica única, y el backend consume un archivo JSON generado a partir de ellos.

### Justificación

| Criterio | Opción A (catálogos frontend) | Opción B (paquete shared) |
|----------|-------------------------------|---------------------------|
| **Trabajo requerido** | Bajo — los catálogos ya existen y están correctos | Alto — hay que crear paquete, configurar workspace, TypedDict sync |
| **Fuente real hoy** | Ya es la verdad de hecho (marketing renderiza desde ahí) | No existe, hay que construirla de cero |
| **Monorepo config** | No necesita cambios en workspaces ni tsconfig | Necesita agregar `packages/pricing` a workspaces, paths, tsconfig |
| **Python sync** | Script genera JSON → Python lee JSON | Igual mecanismo de sync necesario |
| **Riesgo de drift** | CI valida JSON vs catálogo en cada build | Mismo mecanismo, más indirección |
| **Complejidad** | Mínima — se trabaja sobre lo que ya funciona | Mayor — nueva abstracción para un solo consumidor (backend) |

**Conclusión:** El monorepo actual tiene `workspaces: ["apps/web"]` solamente. Los `packages/config` y `packages/ui` no son ni siquiera npm packages (no tienen `package.json`). Crear un paquete compartido real implicaría reconfigurar la infraestructura del monorepo sin beneficio proporcional. Los catálogos TS ya están bien estructurados, tipados y son la verdad de negocio. Mejor formalizarlos como canónicos y generar un artefacto consumible por Python.

---

## 2. Fuente Canónica Final Propuesta

### Gestión Comercial

**Source of truth:** `apps/web/src/features/billing/data/gestion-comercial-catalog.ts`

Ya exporta: `GC_PLANS`, `ADDONS`, `EXTRAS`, `PLAN_LIMITS`, `FEATURE_CATALOG`, `GC_PLAN_KEY_FEATURES`, `GC_PLAN_META`, `LEGACY_PLANS`.

Estado: **Correcto. No necesita cambios de datos.** Solo formalización.

### Menú QR

**Source of truth:** `apps/web/src/features/billing/data/menu-qr-catalog.ts`

Ya exporta: `QR_PLANS`, `QR_ADDONS`, `QR_FEATURE_CATALOG`.

Estado: **Correcto. No necesita cambios de datos.** Solo formalización.

### QR de Reseñas

**Source of truth actual:** Precios inline en `QrReviewsPlanBuilder.tsx` + strings en `reviews/product.ts`.

**Acción:** Crear `apps/web/src/features/billing/data/qr-reviews-catalog.ts` extrayendo los datos de ambos archivos.

---

## 3. Estructura de Archivos Objetivo

```
apps/web/src/features/billing/
├── data/
│   ├── gestion-comercial-catalog.ts    ← CANÓNICO (ya existe, sin cambios de datos)
│   ├── menu-qr-catalog.ts             ← CANÓNICO (ya existe, sin cambios de datos)
│   ├── qr-reviews-catalog.ts          ← CANÓNICO (NUEVO — extraer de QrReviewsPlanBuilder)
│   └── pricing-export.ts              ← NUEVO — genera JSON canónico para backend
│
├── components/
│   ├── GestionComercialPlanBuilder.tsx  ← sin cambios (ya importa del catálogo)
│   ├── MenuQrPlanBuilder.tsx            ← sin cambios (ya importa del catálogo)
│   ├── QrReviewsPlanBuilder.tsx         ← MODIFICAR: importar de qr-reviews-catalog.ts
│   ├── CommercialPlanBuilder.tsx         ← DEPRECAR (gated false &&, usa API vieja)
│   ├── PlansBundles.tsx                 ← DEPRECAR (fallback, usa API vieja)
│   └── PlansBuilderWizard.tsx           ← DEPRECAR (gated false &&, usa API vieja)

apps/web/src/components/gestion/
├── plan-comparison.tsx                  ← MODIFICAR: importar de gestion-comercial-catalog
├── plan-change-dialog.tsx               ← MODIFICAR: consumir precios dinámicos del API

apps/web/src/features/reviews/
├── product.ts                           ← MODIFICAR: importar precios de qr-reviews-catalog

services/api/src/apps/billing/
├── pricing.json                         ← NUEVO — artefacto generado desde catálogos TS
├── canonical_pricing.py                 ← NUEVO — lee pricing.json, expone helpers
├── commercial_plans.py                  ← MODIFICAR: reescribir para consumir canonical_pricing
├── commercial_views.py                  ← sin cambios (sigue importando de commercial_plans)
├── services/commercial/preview.py       ← sin cambios (sigue importando de commercial_plans)
├── services/commercial/limits.py        ← sin cambios
├── services/commercial/apply.py         ← sin cambios
├── management/commands/seed_billing.py  ← MODIFICAR: leer de canonical_pricing

scripts/
├── sync-pricing.ts                      ← NUEVO — script Node que exporta catálogos a JSON
```

### Lógica del flujo de sincronización

```
catálogos TS (fuente canónica)
       │
       ▼
scripts/sync-pricing.ts     → ejecuta en CI / pre-build
       │
       ▼
services/api/src/apps/billing/pricing.json   (artefacto generado)
       │
       ▼
canonical_pricing.py         → lee JSON, expone get_plan_pricing() etc.
       │
       ▼
commercial_plans.py          → reescrito para delegar pricing a canonical_pricing
       │
       ├──► commercial_views.py         (sin cambios de imports)
       ├──► preview.py                  (sin cambios de imports)
       ├──► limits.py                   (sin cambios de imports)
       ├──► apply.py                    (sin cambios de imports)
       └──► cancellation_views.py       (sin cambios de imports)
```

---

## 4. Modelo/Tipo Canónico Sugerido

### 4.1 JSON Intermedio (`pricing.json`)

Este es el artefacto generado. No se edita a mano, nunca. Se genera desde los catálogos TS.

```json
{
  "version": "2026-04-09",
  "currency": "ARS",
  "unit": "pesos",
  "annual_discount": 0.20,
  "verticals": {
    "gestion_comercial": {
      "plans": [
        {
          "code": "starter",
          "name": "Starter",
          "description": "Gestión básica de productos, inventario y ventas. Ideal para empezar.",
          "pricing": { "monthly": 36000, "yearly": 345600 },
          "limits": {
            "branches_included": 1,
            "branches_max_total": 1,
            "branches_extra_allowed": false,
            "max_branches_extra": 0,
            "seats_included": 2
          },
          "is_custom": false
        },
        {
          "code": "pro",
          "name": "Pro",
          "pricing": { "monthly": 50000, "yearly": 480000 },
          "limits": {
            "branches_included": 1,
            "branches_max_total": 3,
            "branches_extra_allowed": true,
            "max_branches_extra": 2,
            "seats_included": 10
          },
          "is_custom": false
        },
        {
          "code": "business",
          "name": "Business",
          "pricing": { "monthly": 75000, "yearly": 720000 },
          "limits": {
            "branches_included": 5,
            "branches_max_total": null,
            "branches_extra_allowed": true,
            "max_branches_extra": null,
            "seats_included": 20
          },
          "is_custom": false
        }
      ],
      "addons": [
        {
          "code": "crm",
          "name": "CRM / Gestión de clientes",
          "pricing": { "monthly": 8000, "yearly": 76800 },
          "available_for": ["starter"],
          "included_in": ["pro", "business", "enterprise"]
        },
        {
          "code": "invoicing",
          "name": "Facturación Electrónica",
          "pricing": { "monthly": 15000, "yearly": 144000 },
          "available_for": ["starter"],
          "included_in": ["pro", "business", "enterprise"]
        }
      ],
      "extras": {
        "branch": { "monthly": 12000, "yearly": 115200 },
        "seat": { "monthly": 5000, "yearly": 48000 }
      }
    },
    "menu_qr": {
      "plans": [
        { "code": "lite", "name": "Lite", "pricing": { "monthly": 18000, "yearly": 172800 } },
        { "code": "pro", "name": "Pro", "pricing": { "monthly": 30000, "yearly": 288000 } },
        { "code": "premium", "name": "Premium", "pricing": { "monthly": 55000, "yearly": 528000 } }
      ],
      "addons": [
        { "code": "menu_qr_addon_reviews", "name": "Reseñas de Google", "pricing": { "monthly": 12000, "yearly": 115200 }, "available_for": ["pro"], "included_in": ["premium"] },
        { "code": "menu_qr_addon_tips", "name": "Propinas (MP)", "pricing": { "monthly": 12000, "yearly": 115200 }, "available_for": ["pro"], "included_in": ["premium"] }
      ]
    },
    "qr_reviews": {
      "plans": [
        { "code": "reviews_base", "name": "QR Reseñas", "pricing": { "monthly": 25000, "yearly": 240000 } },
        { "code": "reviews_pro", "name": "Reseñas Pro", "pricing": { "monthly": 35000, "yearly": 336000 } }
      ]
    }
  }
}
```

### 4.2 Unidad canónica: PESOS (no centavos)

**Decisión:** La unidad canónica es **pesos ARS enteros** (no centavos).

Justificación:
- Los catálogos TS ya usan pesos (`36000` = $36.000 ARS).
- `formatArsPrice()` ya espera pesos (no divide por 100).
- Los precios de negocio son múltiplos de $1.000 — no hay subdivisión en centavos real.
- MercadoPago acepta pesos directamente — la conversión centavos→pesos actual (`/100.0`) fue un artefacto del backend viejo, no un requerimiento.

**Impacto en backend:**
- `commercial_plans.py` pasa a almacenar **pesos** (no centavos).
- La línea `unit_price / 100.0` en `commercial_views.py` (L465, L691) se cambia a `float(unit_price)`.
- El comentario "En centavos" se elimina de todos los TypedDict.
- `preview.py` no necesita cambios internos — ya pasa `unit_price` tal cual viene de `commercial_plans`.

### 4.3 Tipo canónico TypeScript (ya existente, solo formalizar)

Los tipos `GcPlanEntry`, `QrPlanEntry`, `AddonEntry`, `ExtraEntry` ya están correctamente definidos. Se agrega un tipo espejo para QR Reseñas:

```typescript
// qr-reviews-catalog.ts
export interface QrReviewsPlanEntry {
  plan: 'reviews_base' | 'reviews_pro';
  label: string;
  description: string;
  priceMonthly: number;   // ARS pesos
  priceYearly: number;    // ARS pesos
  badge?: string;
  isRecommended?: boolean;
  ctaLabel: string;
}
```

### 4.4 Tipo canónico Python (canonical_pricing.py)

```python
"""
Precios canónicos — generados desde catálogos frontend.
NO EDITAR MANUALMENTE. Editar los catálogos TS y correr sync-pricing.
"""
import json
from pathlib import Path
from typing import TypedDict, Optional, List

class PlanPricing(TypedDict):
    monthly: int  # ARS pesos enteros
    yearly: int   # ARS pesos enteros

_PRICING_FILE = Path(__file__).parent / 'pricing.json'
_DATA = json.loads(_PRICING_FILE.read_text(encoding='utf-8'))

def get_vertical(vertical: str) -> dict:
    return _DATA['verticals'][vertical]

def get_plan_pricing(vertical: str, plan_code: str) -> PlanPricing:
    for plan in _DATA['verticals'][vertical]['plans']:
        if plan['code'] == plan_code:
            return plan['pricing']
    raise ValueError(f"Plan {plan_code} not found in {vertical}")

def get_addon_pricing(vertical: str, addon_code: str) -> PlanPricing:
    for addon in _DATA['verticals'][vertical].get('addons', []):
        if addon['code'] == addon_code:
            return addon['pricing']
    raise ValueError(f"Addon {addon_code} not found in {vertical}")

def get_extra_pricing(vertical: str, extra_code: str) -> PlanPricing:
    extras = _DATA['verticals'][vertical].get('extras', {})
    if extra_code in extras:
        return extras[extra_code]
    raise ValueError(f"Extra {extra_code} not found in {vertical}")
```

---

## 5. Flujo de Datos Final

```
┌─────────────────────────────────────────────────────────────────────┐
│                  FLUJO FINAL CONSOLIDADO                            │
│                                                                     │
│  FUENTE CANÓNICA (frontend TS catalogs)                            │
│  ┌──────────────────────────────────────────────┐                  │
│  │ gestion-comercial-catalog.ts  GC_PLANS etc.  │                  │
│  │ menu-qr-catalog.ts           QR_PLANS etc.   │                  │
│  │ qr-reviews-catalog.ts        REVIEWS_PLANS   │ ← NUEVO         │
│  └──────────┬───────────────────────────────────┘                  │
│             │                                                       │
│    ┌────────┼────────────────┐                                     │
│    │        │                │                                      │
│    ▼        ▼                ▼                                      │
│  Landing   /pricing        sync-pricing.ts                         │
│  Pages     Page               │                                    │
│  (SSR)     (CSR)              ▼                                    │
│                          pricing.json (artefacto generado)         │
│                               │                                    │
│                               ▼                                    │
│                        canonical_pricing.py                        │
│                               │                                    │
│                               ▼                                    │
│                        commercial_plans.py (reescrito)             │
│                           │         │         │                    │
│                           ▼         ▼         ▼                    │
│                        views    preview    checkout                │
│                           │         │         │                    │
│                           ▼         ▼         ▼                    │
│                  /app/servicios   line_items  MercadoPago          │
│                  (precios OK)   (precios OK)  (pesos OK)          │
│                                                                     │
│  COMPONENTES BILLING (migrados)                                    │
│  ┌──────────────────────────────────────────────┐                  │
│  │ plan-comparison.tsx  → importa GC_PLANS      │                  │
│  │ plan-change-dialog.tsx → precios del API     │                  │
│  │   (que ahora devuelve precios correctos)     │                  │
│  └──────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Flujo de checkout (post-consolidación)

```
Usuario ve $36.000 en landing (← catálogo TS)
  ↓
Usuario ve $36.000 en /app/servicios (← API commercial/subscription ← commercial_plans ← canonical_pricing ← pricing.json ← catálogo TS)
  ↓
Preview muestra $36.000 (← preview.py ← commercial_plans ← canonical_pricing ← pricing.json)
  ↓
MercadoPago cobra $36.000 (← checkout_view unit_price = 36000.0 ARS)
  ↓
CONSISTENTE ✅
```

---

## 6. Archivos a Modificar

| Archivo | Cambio | Detalle |
|---------|--------|---------|
| `billing/data/gestion-comercial-catalog.ts` | Header comment | Agregar `@canonical` marker y eliminar "synced with commercial_plans.py" |
| `billing/data/menu-qr-catalog.ts` | Header comment | Agregar `@canonical` marker |
| `billing/components/QrReviewsPlanBuilder.tsx` | Refactor imports | Eliminar const inline, importar de `qr-reviews-catalog.ts` |
| `features/reviews/product.ts` | Refactor pricing | `REVIEW_PRICING_CARDS` importa precios numéricos de `qr-reviews-catalog.ts` y formatea |
| `components/gestion/plan-comparison.tsx` | Eliminar PLANS[] hardcoded | Importar `GC_PLANS`, `PLAN_LIMITS`, `GC_PLAN_KEY_FEATURES` del catálogo; cambiar `formatPrice` por `formatArsPrice` |
| `components/gestion/plan-change-dialog.tsx` | Eliminar strings hardcoded | Los precios de addons/extras los consume del response del API (ya viene en `preview.line_items`); eliminar "$20/mes", "$150/mes", "$50/mes", "$5/mes" y mostrar `formatArsPrice(addon.pricing.monthly)` del response |
| `billing/commercial_plans.py` | Reescribir pricing | PLANS, ADDONS, BRANCH_EXTRA_PRICING, SEAT_EXTRA_PRICING → delegan a `canonical_pricing.py`; limits y features se mantienen inline (no son pricing) |
| `billing/commercial_views.py` | Fix MP conversion | L465, L691: cambiar `unit_price / 100.0` → `float(unit_price)` (ya son pesos) |
| `billing/management/commands/seed_billing.py` | Actualizar precios | Leer de `canonical_pricing` y generar bundles/plans con precios correctos |

---

## 7. Archivos a Crear / Eliminar / Deprecar

### Crear

| Archivo | Propósito |
|---------|-----------|
| `apps/web/src/features/billing/data/qr-reviews-catalog.ts` | Catálogo canónico QR Reseñas |
| `apps/web/src/features/billing/data/pricing-export.ts` | Módulo que exporta todos los catálogos en formato JSON |
| `scripts/sync-pricing.ts` | Script Node: importa pricing-export → escribe `pricing.json` en backend |
| `services/api/src/apps/billing/pricing.json` | Artefacto generado (commiteado, verificado en CI) |
| `services/api/src/apps/billing/canonical_pricing.py` | Lector Python del JSON canónico |

### Deprecar / Marcar para eliminación futura

| Archivo | Razón |
|---------|-------|
| `billing/components/CommercialPlanBuilder.tsx` | Gated con `false &&`, usa API bundles con precios viejos. Eliminar cuando se confirme que no se activa. |
| `billing/components/PlansBuilderWizard.tsx` | Gated con `false &&`, usa API modules vieja. Mismo caso. |
| `billing/components/PlansBundles.tsx` | Fallback genérico que usa API bundles. Evaluar si se necesita post-migración. |

### No eliminar todavía

| Archivo | Razón |
|---------|-------|
| `commercial_plans.py` | Se mantiene pero se reescribe internamente para consumir de `canonical_pricing.py`. Sus exports (`get_plan_config`, `BRANCH_EXTRA_PRICING`, etc.) siguen siendo la API pública para el resto del backend — así no se tocan 7 archivos que importan de él. |

---

## 8. Plan de Implementación por Tareas

---

### Task 1: Crear catálogo canónico de QR Reseñas

**Objetivo:** Extraer precios inline de `QrReviewsPlanBuilder.tsx` a un archivo de catálogo dedicado, al mismo nivel que GC y Menú QR.

**Archivos impactados:**
- CREAR: `apps/web/src/features/billing/data/qr-reviews-catalog.ts`
- MODIFICAR: `apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx` (eliminar const inline, importar)
- MODIFICAR: `apps/web/src/features/reviews/product.ts` (importar precios numéricos del catálogo)

**Detalle:**
```typescript
// qr-reviews-catalog.ts — NUEVO
export interface QrReviewsPlanEntry { ... }
export const QR_REVIEWS_PLANS: QrReviewsPlanEntry[] = [ /* datos extraídos */ ];
export const QR_REVIEWS_KEY_FEATURES: Record<string, string[]> = { /* extraído */ };
export const QR_REVIEWS_PLAN_META: Record<string, { highlight: string }> = { /* extraído */ };
```

`QrReviewsPlanBuilder.tsx` pasa de:
```typescript
const QR_REVIEWS_PLANS: QrReviewsPlanEntry[] = [ ... ]; // inline
```
a:
```typescript
import { QR_REVIEWS_PLANS, QR_REVIEWS_KEY_FEATURES, QR_REVIEWS_PLAN_META } from '../data/qr-reviews-catalog';
```

`product.ts` pasa de:
```typescript
price: '$25.000',
```
a:
```typescript
import { QR_REVIEWS_PLANS } from '@/features/billing/data/qr-reviews-catalog';
import { formatArsPrice } from '@/features/billing/data/menu-qr-catalog';
// ...
price: formatArsPrice(QR_REVIEWS_PLANS[0].priceMonthly),
```

**Riesgo:** Bajo — refactor de extracción puro.  
**Criterio de terminado:** `QrReviewsPlanBuilder` y `product.ts` renderizan igual que antes; no quedan precios numéricos inline en ninguno de los dos; los tests de componentes pasan.

---

### Task 2: Formalizar catálogos existentes como canónicos

**Objetivo:** Marcar explícitamente los catálogos GC y Menú QR como fuente canónica. Eliminar comentarios que dicen "synced with commercial_plans.py" (ya no será verdad — commercial_plans será quien syncee con ellos).

**Archivos impactados:**
- MODIFICAR: `gestion-comercial-catalog.ts` (header comment)
- MODIFICAR: `menu-qr-catalog.ts` (header comment)
- MODIFICAR: `qr-reviews-catalog.ts` (ya creado en Task 1)

**Detalle:**
Cambiar el header de gestion-comercial-catalog de:
```
 * Sincronizado con:
 *   - services/api/src/apps/business/entitlements.py
 *   - services/api/src/apps/billing/commercial_plans.py
```
a:
```
 * @canonical — Fuente única de verdad para planes y precios de Gestión Comercial.
 * El backend consume estos valores vía pricing.json (generado por sync-pricing).
 * NO duplicar precios en commercial_plans.py ni en componentes de billing.
```

**Riesgo:** Nulo — solo cambios de documentación.  
**Criterio de terminado:** Los 3 catálogos tienen header `@canonical` estandarizado.

---

### Task 3: Crear script de exportación y pricing.json

**Objetivo:** Crear el mecanismo que genera `pricing.json` desde los catálogos TS y lo deposita en el backend.

**Archivos impactados:**
- CREAR: `apps/web/src/features/billing/data/pricing-export.ts`
- CREAR: `scripts/sync-pricing.ts`
- CREAR: `services/api/src/apps/billing/pricing.json`

**Detalle de `pricing-export.ts`:**
Función que importa `GC_PLANS`, `ADDONS`, `EXTRAS`, `PLAN_LIMITS` de GC, `QR_PLANS`, `QR_ADDONS` de Menú QR, `QR_REVIEWS_PLANS` de QR Reseñas, y retorna la estructura JSON canónica con todos los datos de pricing + limits.

**Detalle de `scripts/sync-pricing.ts`:**
- Ejecuta con `npx tsx scripts/sync-pricing.ts`
- Importa la función de export, genera el JSON, lo escribe en `services/api/src/apps/billing/pricing.json`
- Valida que annual = monthly × 12 × 0.8 (invariante de negocio)
- Sale con error si la validación falla

**Detalle de `pricing.json`:**
Se commitea al repo. El CI verifica que esté actualizado (`sync-pricing --check` compara output con archivo existente).

**Riesgo:** Medio — el script debe resolver los imports de TS correctamente fuera del contexto Next.js. `tsx` (esbuild-based) lo maneja bien con la config de paths de tsconfig.  
**Criterio de terminado:** `npx tsx scripts/sync-pricing.ts` genera un `pricing.json` válido que refleja exactamente los precios de los 3 catálogos; CI check pasa.

---

### Task 4: Crear canonical_pricing.py en backend

**Objetivo:** Módulo Python que lee `pricing.json` y expone helpers tipados para obtener precios por vertical/plan/addon/extra.

**Archivos impactados:**
- CREAR: `services/api/src/apps/billing/canonical_pricing.py`

**Detalle:** Ver sección 4.4 del documento. Expone `get_plan_pricing()`, `get_addon_pricing()`, `get_extra_pricing()`, `get_vertical()`.

**Riesgo:** Bajo — módulo nuevo sin dependencias.  
**Criterio de terminado:** `canonical_pricing.get_plan_pricing('gestion_comercial', 'starter')` retorna `{'monthly': 36000, 'yearly': 345600}`.

---

### Task 5: Reescribir commercial_plans.py para consumir canonical_pricing

**Objetivo:** Que `commercial_plans.py` deje de tener precios hardcoded y los obtenga de `canonical_pricing.py`. Mantener la misma API pública (mismos exports, mismos tipos) para no romper los 7 archivos que importan de él.

**Archivos impactados:**
- MODIFICAR: `services/api/src/apps/billing/commercial_plans.py`

**Detalle:** La reescritura cambia solo los valores de precios. Los limits, features, y la lógica de `get_plan_config()` / `get_addon_config()` siguen definidos ahí (no son pricing, son config de negocio de la vertical GC). La diferencia es que los campos `pricing` dentro de cada plan/addon/extra se leen de `canonical_pricing` en vez de estar hardcoded.

Ejemplo de cambio para PLANS:
```python
# ANTES
PLANS = [
    { 'code': 'starter', 'pricing': { 'monthly': 9900, 'yearly': 95000 }, ... },
]

# DESPUÉS
from apps.billing.canonical_pricing import get_plan_pricing

_starter_pricing = get_plan_pricing('gestion_comercial', 'starter')

PLANS = [
    { 'code': 'starter', 'pricing': _starter_pricing, ... },
]
```

Mismo patrón para `ADDONS`, `BRANCH_EXTRA_PRICING`, `SEAT_EXTRA_PRICING`.

**Impacto downstream:** Cero. Los 7 archivos que importan `PLANS`, `get_plan_config()`, etc., siguen funcionando igual — solo cambian los valores numéricos dentro.

**Riesgo:** Medio — es el cambio más sensible porque afecta directamente lo que MercadoPago cobra. Requiere test exhaustivo.  
**Criterio de terminado:** `get_plan_config('starter')['pricing']['monthly']` retorna `36000` (not `9900`); todos los tests del módulo billing pasan.

---

### Task 6: Cambiar conversión a pesos en checkout views

**Objetivo:** Eliminar la división por 100 que convertía centavos a pesos, dado que ahora los precios ya son pesos.

**Archivos impactados:**
- MODIFICAR: `services/api/src/apps/billing/commercial_views.py` L465, L691

**Detalle:**
```python
# ANTES (L465)
'unit_price': item['unit_price'] / 100.0,

# DESPUÉS
'unit_price': float(item['unit_price']),
```
Mismo cambio en L691 (AddonCheckoutView).

**Riesgo:** CRÍTICO — si se aplica sin haber hecho Task 5, MP cobraría 100x el precio viejo. Aplicar en el mismo deploy que Task 5.  
**Criterio de terminado:** Un checkout de plan Starter genera una preferencia MP con `unit_price: 36000.0`.

---

### Task 7: Migrar plan-comparison.tsx al catálogo

**Objetivo:** Eliminar el array `PLANS[]` hardcoded y consumir del catálogo oficial de Gestión Comercial.

**Archivos impactados:**
- MODIFICAR: `apps/web/src/components/gestion/plan-comparison.tsx`

**Detalle:**
- Eliminar `const PLANS: PlanConfig[]` (L24-98)
- Importar `GC_PLANS`, `PLAN_LIMITS`, `GC_PLAN_KEY_FEATURES`, `GC_PLAN_META` de `@/features/billing/data/gestion-comercial-catalog`
- Importar `formatArsPrice` de `@/features/billing/data/menu-qr-catalog` (o moverla a un util compartido)
- Eliminar `function formatPrice(cents)` local
- Adaptar el rendering para usar `GcPlanEntry` shape en vez de `PlanConfig`
- Mapear: `plan.priceMonthly` en lugar de `plan.price_monthly`, `plan.label` en lugar de `plan.name`, etc.

**Riesgo:** Bajo — refactor de presentación puro. La información de Enterprise se puede mantener como constante local (no tiene pricing).  
**Criterio de terminado:** El componente muestra $36.000 / $50.000 / $75.000 en vez de $99 / $299 / $499; visualmente idéntico salvo los números.

---

### Task 8: Migrar plan-change-dialog.tsx a precios dinámicos

**Objetivo:** Eliminar los 4 strings de precio hardcodeados y mostrar los precios que vienen del API (que post-Task 5 ya serán correctos).

**Archivos impactados:**
- MODIFICAR: `apps/web/src/components/gestion/plan-change-dialog.tsx`

**Detalle:**
- Los addons CRM y Facturación: en vez de `$20/mes` y `$150/mes` hardcoded, mostrar el precio del addon desde el response de `GET /api/v1/billing/commercial/subscription/` (campo `addons.available[].pricing`)
- Los extras Branch y Seat: en vez de `× $50/mes` y `× $5/mes`, mostrar desde `branches.unit_pricing.monthly` y `seats.unit_pricing.monthly` del response
- Usar `formatArsPrice()` para formatear
- Eliminar `function formatPrice(cents)` local

El response del API ya incluye `branches.unit_pricing` y `seats.unit_pricing`. Tras Task 5, esos valores serán los oficiales ($12.000 y $5.000 respectivamente).

Para los addons, el response incluye `addons.available[]` con pricing. Actualmente se ignoran para mostrar strings fijos. Cambiar a consumirlos.

**Riesgo:** Bajo-medio — depende de que el response tenga la estructura esperada, lo cual ya está auditado.  
**Criterio de terminado:** No queda ningún string de precio hardcodeado en el archivo; todos los precios se obtienen del API response.

---

### Task 9: Sincronizar seed_billing.py

**Objetivo:** Que el seeder genere bundles y plans con los precios oficiales.

**Archivos impactados:**
- MODIFICAR: `services/api/src/apps/billing/management/commands/seed_billing.py`

**Detalle:**
- Bundles GC: `fixed_price_monthly` y `fixed_price_yearly` → leer de `canonical_pricing`
- `PLAN_SEEDS`: `Decimal('99.00')` → `Decimal('36000.00')`, etc.
- Menú QR bundles: actualizar de $29/$59/$99 a $18.000/$30.000/$55.000
- QR Reviews bundle: actualizar de $49 a $25.000/$35.000

**Riesgo:** Medio — afecta datos en DB. Las suscripciones existentes no deben alterarse; el seed solo afecta registros creados por él (Bundle, Plan objects).  
**Criterio de terminado:** `python manage.py seed_billing` genera bundles con precios correctos; existing subscriptions untouched.

---

### Task 10: Mover formatArsPrice a utils compartido

**Objetivo:** Hoy `formatArsPrice` vive en `menu-qr-catalog.ts` y se importa desde otros archivos (QrReviewsPlanBuilder). Moverla a un lugar neutral.

**Archivos impactados:**
- CREAR: `apps/web/src/features/billing/utils/format-price.ts`
- MODIFICAR: `menu-qr-catalog.ts` (re-export desde el nuevo util por backward compat)
- MODIFICAR: `plan-comparison.tsx`, `plan-change-dialog.tsx`, `QrReviewsPlanBuilder.tsx` (actualizar imports)

**Riesgo:** Bajo — refactor de imports puro.  
**Criterio de terminado:** Todos los componentes de billing usan `formatArsPrice` desde `@/features/billing/utils/format-price`; no existe `formatPrice(cents)` que divida por 100 en ningún componente de billing.

---

### Task 11: Tests de consistencia cross-layer

**Objetivo:** Agregar tests que fallan si alguien modifica un precio sin actualizar todas las fuentes.

**Archivos impactados:**
- CREAR: `services/api/src/apps/billing/tests/test_pricing_consistency.py`
- CREAR: `scripts/sync-pricing.ts --check` mode
- MODIFICAR: CI pipeline (agregar check)

**Detalle:**

**Test Python:**
```python
def test_commercial_plans_match_canonical():
    """Verifica que commercial_plans.py refleja pricing.json."""
    for plan in PLANS:
        canonical = get_plan_pricing('gestion_comercial', plan['code'])
        assert plan['pricing'] == canonical, f"Plan {plan['code']} pricing mismatch"

def test_branch_extra_matches_canonical():
    canonical = get_extra_pricing('gestion_comercial', 'branch')
    assert BRANCH_EXTRA_PRICING == canonical

def test_annual_is_monthly_times_12_with_discount():
    """Invariante de negocio: anual = mensual × 12 × 0.8"""
    for plan in PLANS:
        if plan['is_custom']:
            continue
        expected_yearly = int(plan['pricing']['monthly'] * 12 * 0.8)
        assert plan['pricing']['yearly'] == expected_yearly
```

**Script check mode:**
```bash
npx tsx scripts/sync-pricing.ts --check
# Exit 0 si pricing.json está actualizado
# Exit 1 si hay diff → CI falla
```

**Riesgo:** Nulo — solo agrega seguridad.  
**Criterio de terminado:** CI ejecuta ambos checks; un cambio de precio en un catálogo sin regenerar `pricing.json` rompe el build.

---

### Task 12: Cleanup de componentes deprecados

**Objetivo:** Eliminar o aislar definitivamente los componentes que usan el sistema de bundles API viejo.

**Archivos impactados:**
- EVALUAR: `CommercialPlanBuilder.tsx` — ya gated con `false &&`, eliminar si no hay plan de activarlo
- EVALUAR: `PlansBuilderWizard.tsx` — mismo caso
- EVALUAR: `PlansBundles.tsx` — es el fallback de `pricing-client.tsx` para verticales sin builder dedicado

**Riesgo:** Bajo — el código está gated/inactivo.  
**Criterio de terminado:** Decisión explícita documentada para cada uno (eliminar / mantener gated / migrar).

---

## 9. Riesgos de Migración

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **Deploy parcial** — Task 5 (backend en pesos) sin Task 6 (quitar /100) | Media | CRÍTICO — MP cobraría $360 en vez de $36.000 | Deployar Task 5 y Task 6 atómicamente. Nunca uno sin el otro. |
| **Suscripciones existentes** con precios viejos en metadata | Media | Medio — renovaciones podrían traer sorpresas | Revisar si `PendingSubscriptionChange` o `SubscriptionV2` almacenan snapshots de precio. Si sí, migrar datos. |
| **pricing.json desactualizado** después de un cambio de catálogo | Alta (humano se olvida) | Medio — backend y frontend con precios distintos | CI check con `sync-pricing --check` bloquea merge si JSON no está regenerado. |
| **Bundles DB inconsistentes** post-seed update | Baja | Bajo — bundles solo se usan en componentes ocultos | Ejecutar `seed_billing` como parte del deploy. Los componentes que los consumen están gated. |
| **formatArsPrice vs formatPrice** — error de unidad | Media | Alto — precio se muestra 100x más alto o bajo | Task 10 elimina `formatPrice(cents)` por completo. Solo sobrevive `formatArsPrice(pesos)`. |

### Orden de deploy recomendado

```
Deploy 1 (bajo riesgo):
  ✅ Task 1  — catálogo QR Reseñas
  ✅ Task 2  — formalizar headers
  ✅ Task 10 — formatArsPrice util

Deploy 2 (riesgo medio):
  ✅ Task 3  — sync-pricing script + pricing.json
  ✅ Task 4  — canonical_pricing.py
  ✅ Task 7  — plan-comparison.tsx migrado

Deploy 3 (CRÍTICO — atómico):
  ⚠️ Task 5  — commercial_plans.py reescrito (pesos)
  ⚠️ Task 6  — quitar /100 en checkout views
  ⚠️ Task 8  — plan-change-dialog.tsx dinámico
  ⚠️ Task 9  — seed_billing.py actualizado
  ⚠️ Task 11 — tests de consistencia

Deploy 4 (cleanup):
  ✅ Task 12 — deprecar componentes viejos
```

---

## 10. Checklist de Consistencia Final

### Precios alineados

- [ ] `gestion-comercial-catalog.ts` GC_PLANS → $36k / $50k / $75k (pesos)
- [ ] `menu-qr-catalog.ts` QR_PLANS → $18k / $30k / $55k (pesos)
- [ ] `qr-reviews-catalog.ts` QR_REVIEWS_PLANS → $25k / $35k (pesos)
- [ ] `pricing.json` refleja exactamente los 3 catálogos
- [ ] `canonical_pricing.py` lee `pricing.json` correctamente
- [ ] `commercial_plans.py` PLANS pricing = canónicos (pesos, no centavos)
- [ ] `commercial_plans.py` ADDONS pricing = canónicos
- [ ] `commercial_plans.py` BRANCH_EXTRA / SEAT_EXTRA = canónicos
- [ ] `seed_billing.py` bundles y plan seeds = canónicos
- [ ] `commercial_views.py` MP unit_price = `float(price)` (no `/100`)

### Sin hardcodes

- [ ] `plan-comparison.tsx` no tiene const PLANS[] con precios
- [ ] `plan-change-dialog.tsx` no tiene strings "$20", "$150", "$50", "$5"
- [ ] `QrReviewsPlanBuilder.tsx` no tiene precios inline (importa del catálogo)
- [ ] `product.ts` no tiene precios string hardcoded (importa del catálogo)
- [ ] No existe `formatPrice(cents)` → `$${cents/100}` en ningún componente de billing

### Funciones de formato

- [ ] `formatArsPrice(pesos)` es la única función de formato de precio en billing
- [ ] Vive en `features/billing/utils/format-price.ts`
- [ ] Todos los componentes la importan de ahí

### Tests

- [ ] Test Python: `commercial_plans` pricing == `canonical_pricing`
- [ ] Test Python: anual == mensual × 12 × 0.8
- [ ] CI: `sync-pricing --check` verifica pricing.json actualizado
- [ ] Test de preview: line_items tienen precios oficiales
- [ ] Test de checkout: MP preference tiene unit_price correcto

### Documentación

- [ ] Catálogos tienen header `@canonical`
- [ ] `commercial_plans.py` tiene docstring indicando que pricing viene de `canonical_pricing`
- [ ] `pricing.json` tiene comment en header: "GENERATED — DO NOT EDIT"
- [ ] README/CONTRIBUTING explica el flujo de cambio de precios
