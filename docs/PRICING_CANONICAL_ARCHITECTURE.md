# Arquitectura Canónica de Pricing — Propuesta Productiva

> **Fecha:** 9 de abril de 2026  
> **Alcance:** Toda la plataforma Mi Rubro (GC, Menú QR, QR Reseñas, futuros verticales)  
> **Objetivo:** Una fuente canónica normalizada de precios que elimine drift, soporte pagos reales y sea fácil de mantener.

---

## Hallazgo previo: Inventario de fuentes de precios actuales

Antes de proponer, resumo lo que existe hoy (auditado archivo por archivo):

| # | Fuente | Ubicación | Unidad | Valores GC Starter | Rol |
|---|--------|-----------|--------|-------------------|-----|
| 1 | **GC Catalog** | `features/billing/data/gestion-comercial-catalog.ts` | Pesos enteros | 36000 | Marketing/landing + PlanBuilder |
| 2 | **QR Catalog** | `features/billing/data/menu-qr-catalog.ts` | Pesos enteros | — | Marketing/landing + PlanBuilder |
| 3 | **QR Reviews inline** | `features/billing/components/QrReviewsPlanBuilder.tsx` | Pesos enteros | — | PlanBuilder UI (inline) |
| 4 | **reviews/product.ts** | `features/reviews/product.ts` | Strings (`'$25.000'`) | — | Landing copy |
| 5 | **commercial_plans.py** | `services/api/.../commercial_plans.py` | Centavos | 9900 | Backend billing: preview, checkout, limits |
| 6 | **seed_billing.py Bundles** | `management/commands/seed_billing.py` | Centavos | 9900 | DB Bundle.fixed_price_monthly |
| 7 | **seed_billing.py Plans** | `management/commands/seed_billing.py` | Pesos Decimal | Decimal('99.00') | DB Plan.price → MP transaction_amount |
| 8 | **plan-comparison.tsx** | `components/gestion/plan-comparison.tsx` | Centavos | 9900 | UI interna /app/servicios |
| 9 | **plan-change-dialog.tsx** | `components/gestion/plan-change-dialog.tsx` | Strings hardcoded | "$20/mes" | UI interna dialog |
| 10 | **billing-page-client.tsx** | `components/gestion/billing-page-client.tsx` | Centavos (del API) | — | Dashboard billing |
| 11 | **CommercialPlanBuilder.tsx** | `features/billing/components/CommercialPlanBuilder.tsx` | Centavos (×100 error) | 1200000 | Dead code |
| 12 | **DB Module.price_monthly** | `billing.Module` model | Centavos (IntegerField) | 0 (core) | API /bundles, /modules |
| 13 | **DB Bundle.fixed_price_**** | `billing.Bundle` model | Centavos (IntegerField) | 9900 | API /bundles fallback |
| 14 | **DB Plan.price** | `billing.Plan` model | Pesos (DecimalField) | Decimal('99.00') | MP preapproval_plan → transaction_amount |

### Unidades en uso simultáneo

| Subsistema | Unidad actual | Ejemplo Starter |
|---|---|---|
| Catálogos TS (marketing) | Pesos ARS enteros | `36000` |
| `commercial_plans.py` | Centavos | `9900` |
| `Bundle.fixed_price_monthly` (DB) | Centavos | `9900` |
| `Plan.price` (DB) | Pesos Decimal | `Decimal('99.00')` |
| `preview.py` LineItem.unit_price | Centavos | `9900` |
| `commercial_views.py` → MP preference | Pesos float (centavos/100) | `99.0` |
| `checkout_session_service.py` → MP preapproval | Pesos float (Plan.price) | `99.0` |
| `formatArsPrice()` | Pesos enteros (no divide) | `36000` → "$36.000" |
| `formatPrice()` | Centavos (divide /100) | `9900` → "$99" |
| `lib/format.ts formatARS()` | Pesos (no divide) | genérica |

### Divergencia crítica

**Frontend marketing muestra $36.000/mes — MercadoPago cobra $99/mes.**

Esto no es un bug cosmético: son precios de negocio completamente diferentes. Los catálogos TS tienen los precios que negocio quiere cobrar; el backend tiene valores placeholder de desarrollo.

---

## 1. Recomendación de Arquitectura Final

### Opción elegida: Capa de dominio neutral en `apps/web/src/lib/pricing/`

**NO usar los catálogos de marketing como fuente canónica.**  
**NO crear un `packages/pricing/`.**  
**Crear una capa de dominio de pricing desacoplada de UI, marketing y componentes.**

### Opciones evaluadas

| Opción | Descripción | Veredicto |
|--------|-------------|-----------|
| **A: Catálogos marketing como fuente** | Formalizar `gestion-comercial-catalog.ts` y `menu-qr-catalog.ts` como fuente única | ❌ Rechazada |
| **B: `packages/pricing/` compartido** | Paquete npm/monorepo consumible por frontend y backend | ❌ Rechazada |
| **C: `apps/web/src/lib/pricing/`** | Módulo de dominio neutral dentro del frontend, que exporta datos canónicos y genera JSON para backend | ✅ **Elegida** |
| **D: Backend Python como fuente** | El backend define precios, frontend los consume por API | ❌ Rechazada |
| **E: JSON standalone en raíz** | Un `pricing.json` en la raíz del repo, consumido por TS y Python | ❌ Rechazada |

### Justificación por opción

**Opción A rechazada** porque:
- Los archivos de catálogo mezclan datos de negocio (precios numéricos) con datos de presentación (copy, badges, ctaLabel, descriptions, `isRecommended`).
- Los addons/extras tienen precios como **strings** (`'$8.000/mes'`), lo que impide cálculos. No son consumibles por backend.
- `formatArsPrice()` vive en el catálogo de Menú QR y la importan componentes de GC — acoplamiento inadecuado.
- Los catálogos son convenientes para UI pero inadecuados como fuente de verdad de negocio.

**Opción B rechazada** porque:
- `workspaces` del monorepo solo incluye `["apps/web"]`.
- `packages/config/` y `packages/ui/` no son paquetes npm (no tienen package.json).
- tsconfig no resuelve `packages/` — habría que reconfigurar infraestructura del monorepo para un solo módulo.
- Sobre-ingeniería para el tamaño actual del proyecto.

**Opción C elegida** porque:
- `apps/web/src/lib/` ya existe como capa utilitaria con `format.ts`, `dates.ts`, `api-url.ts`, etc.
- No requiere cambios en workspaces, tsconfig, ni infraestructura del monorepo.
- Se importa con `@/lib/pricing/...` — consistente con el patrón existente.
- Separa limpiamente: datos de negocio (pricing) vs. presentación (catalogs) vs. transaccional (views).
- Los catálogos de marketing pasan a ser **consumidores** del pricing canónico, no la fuente.
- Un script genera `pricing.json` para Python — misma estrategia que Opción A pero con mejor separación.

**Opción D rechazada** porque:
- Los precios cambian por decisión de negocio/producto, no de backend. Es más natural que la fuente viva donde el equipo de producto la puede ver y modificar (TypeScript, no Python).
- Requeriría que el frontend consuma precios por API para todo, incluyendo landings SSR/SSG. Agrega latencia y complejidad.

**Opción E rechazada** porque:
- Un JSON plano no tiene tipos, ni validaciones en tiempo de compilación, ni autocompletado.
- Se pierde la verificación de TypeScript que previene errores.
- Requiere parsear JSON en TS con tipos manuales — duplicación.

---

## 2. Ubicación Recomendada en el Repo

### Estructura propuesta

```
apps/web/src/lib/pricing/
├── index.ts                    ← Re-export público
├── types.ts                    ← Interfaces y tipos canónicos
├── plans.ts                    ← Datos canónicos de TODOS los planes
├── addons.ts                   ← Datos canónicos de TODOS los addons/extras
├── catalog.ts                  ← Features catalog (qué incluye cada plan)
├── rules.ts                    ← Reglas de negocio: descuento anual, limits, compatibilidad
├── selectors.ts                ← Getters tipados: getPlan(), getAddon(), getExtra()
├── format.ts                   ← formatArsPrice() y funciones de formato (ÚNICO lugar)
├── export-json.ts              ← Exporta todo como JSON serializable (para script)
└── __tests__/
    ├── invariants.test.ts      ← Verifica anual = mensual × 12 × 0.8, etc.
    └── selectors.test.ts       ← Verifica que selectors devuelven datos correctos

scripts/
└── sync-pricing-to-backend.ts  ← Genera services/api/.../pricing.json

services/api/src/apps/billing/
├── pricing.json                ← Generado (NO editar manualmente)
└── canonical_pricing.py        ← Lee pricing.json, expone getters tipados
```

### Por qué `lib/pricing/` y no `features/billing/data/` o `domain/pricing/`

| Ruta | Argumento | Contra |
|------|-----------|--------|
| `features/billing/data/` | Ya existen catálogos ahí | Mezcla datos de negocio con datos de UI; el directorio `billing/` es una feature de UI, no una capa de dominio |
| `domain/pricing/` | Semánticamente correcto | El directorio `domain/` no existe; crear un nuevo directorio top-level agrega una convención que nadie más usa |
| `lib/pricing/` | **Consistente con `lib/format.ts`, `lib/dates.ts`; ya es la capa utilitaria del proyecto** | Ninguno significativo — `lib/` es exactly la capa neutral esistente |
| `packages/shared-pricing/` | Compartido entre frontend y backend | Requiere reconfigurar monorepo workspaces y tsconfig |

### Relación con los catálogos existentes

Los catálogos (`gestion-comercial-catalog.ts`, `menu-qr-catalog.ts`) **no se eliminan**. Pasan a ser **adaptadores de UI** que importan desde `lib/pricing/` y agregan copy, badges, y estructura de presentación.

```
lib/pricing/plans.ts (FUENTE CANÓNICA)
    ↓ importa
features/billing/data/gestion-comercial-catalog.ts (ADAPTADOR UI)
    ↓ importa
components/marketing/gestion-pricing-section.tsx (PRESENTACIÓN)
```

---

## 3. Unidad Monetaria Recomendada

> **NOTA:** Esta sección fue reemplazada por la evaluación detallada en
> `docs/PRICING_UNIT_EVALUATION.md`. La decisión final es **Pesos ARS enteros**.
> A continuación se mantiene un resumen actualizado.

### Recomendación: **Pesos ARS enteros (int)**

| Criterio | Pesos enteros | Centavos enteros | Pesos Decimal |
|----------|--------------|-----------------|---------------|
| **MercadoPago** | MP acepta pesos float, OK | Dividir /100 para MP, explícito | DecimalField, OK |
| **Cálculos** | OK para planes actuales (múltiplos de $1000), pero si algún precio tiene centavos se rompe | ✅ Siempre exacto | ✅ Exacto |
| **DB** | IntegerField OK | ✅ IntegerField estándar de billing | DecimalField más pesado |
| **Industry standard** | No estándar | ✅ Stripe, PayPal, MP internamente usan centavos | Pesos como Decimal es aceptable |
| **Errores de conversión** | ¿Es pesos o centavos? Ambiguo si el parámetro se llama `cents` | Explícito: siempre centavos, se divide 1 vez para display | Requiere float() para MP |
| **Consistencia interna** | Requiere migrar TODO el backend a pesos | ✅ Backend ya usa centavos internamente | Inconsistente con IntegerField actual |
| **Display** | Se formatea directo | Se divide /100 y formatea | Se convierte a float y formatea |
| **Futura internacionalización** | No soporta USD, BRL, etc. correctamente | ✅ Estándar global | Pesos-only |

### Decisión: **Centavos enteros** como unidad canónica interna

Justificación resumida:

1. **Es el estándar de la industria** — Stripe, MercadoPago, PayPal, y toda la fintech trabajan en la unidad más pequeña de la moneda (centavos para ARS, cents para USD).

2. **El backend ya usa centavos** — `commercial_plans.py`, `preview.py` (LineItem.unit_price: int, "in centavos"), `Module.price_monthly` (IntegerField, "Price in cents"), `Bundle.fixed_price_monthly` (IntegerField, "Override price in cents"), `PendingSubscriptionChange.total_amount` (IntegerField, "Total amount in centavos"). Migrar a pesos implicaría tocar 7+ archivos backend, modelos DB, y migraciones. Innecesario.

3. **Evita errores de ambigüedad** — Con centavos, hay un solo punto de conversión documentado: al formatear para display y al enviar a MP. Con pesos enteros, queda la duda: ¿este `36000` es $36.000 o 360 pesos con 00 centavos? Con centavos: `3600000` siempre es $36.000,00 — sin ambigüedad.

4. **El problema real no es la unidad, es la divergencia de valores** — Los catálogos dicen $36.000 (3.600.000 centavos), el backend dice $99 (9.900 centavos). Cambiar la unidad no resuelve esto; lo que lo resuelve es tener UNA fuente canónica. Sea cual sea la unidad, los valores deben sincronizarse.

5. **`Plan.price` (DecimalField) es la excepción** — El modelo `Plan` usa `Decimal('99.00')` directo a MP `transaction_amount`. Es el único que está en pesos. Se actualizará a `Decimal('36000.00')` para alinear con la fuente canónica. MP lo acepta sin problemas.

### Conversiones explícitas (2 puntos, no más)

```
CANÓNICO (centavos int)
    │
    ├──→ Display: centavos ÷ 100 → formatear con Intl
    │
    └──→ MercadoPago: centavos ÷ 100 → float pesos (una sola conversión, en un solo lugar)
```

### Precios reales de negocio en centavos

| Producto | Plan | Mensual (centavos) | Anual (centavos) |
|----------|------|-------------------|-----------------|
| GC | Starter | 3_600_000 | 34_560_000 |
| GC | Pro | 5_000_000 | 48_000_000 |
| GC | Business | 7_500_000 | 72_000_000 |
| QR | Lite | 1_800_000 | 17_280_000 |
| QR | Pro | 3_000_000 | 28_800_000 |
| QR | Premium | 5_500_000 | 52_800_000 |
| Reseñas | Base | 2_500_000 | 24_000_000 |
| Reseñas | Pro | 3_500_000 | 33_600_000 |
| GC Addon | CRM | 800_000 | 7_680_000 |
| GC Addon | Facturación | 1_500_000 | 14_400_000 |
| GC Extra | Sucursal | 1_200_000 | 11_520_000 |
| GC Extra | Usuario | 500_000 | 4_800_000 |
| QR Addon | Reviews | 1_200_000 | 11_520_000 |
| QR Addon | Propinas | 1_200_000 | 11_520_000 |

> Nota: Los valores actuales del backend (`9900`, `29900`, etc.) están desactualizados. La migración los reemplazará con estos valores correctos.

---

## 4. Modelo Canónico Sugerido

### 4.1 Tipos canónicos (`lib/pricing/types.ts`)

```typescript
// ─── Unidad monetaria ────────────────────────────────────────────
/**
 * Todos los precios canónicos se expresan en CENTAVOS de ARS (enteros).
 *   3_600_000 = $36.000 ARS
 * Convertir a pesos para display: cents / 100
 * Convertir a pesos para MP: cents / 100
 */
export type CentsARS = number;

// ─── Enums ───────────────────────────────────────────────────────
export type Vertical = 'gestion_comercial' | 'menu_qr' | 'qr_reviews';
export type BillingCycle = 'monthly' | 'yearly';
export type Currency = 'ARS';

// ─── Pricing primitivo ──────────────────────────────────────────
export interface PricingPair {
  /** Precio mensual en centavos ARS */
  monthly: CentsARS;
  /** Precio anual en centavos ARS (= monthly × 12 × (1 - annualDiscount)) */
  yearly: CentsARS;
}

// ─── Plan canónico ──────────────────────────────────────────────
export interface CanonicalPlan {
  vertical: Vertical;
  code: string;                    // 'starter', 'pro', 'lite', 'reviews_base'
  name: string;                    // 'Starter', 'Pro', 'Lite'
  pricing: PricingPair;
  limits: PlanLimits;
  isCustom: boolean;               // Enterprise
  active: boolean;
  /** Addons incluidos gratis en este plan */
  includedAddons: string[];
  /** Addons comprables como extra en este plan */
  availableAddons: string[];
}

export interface PlanLimits {
  branchesIncluded: number;
  branchesMaxTotal: number | null;  // null = ilimitado
  branchesExtraAllowed: boolean;
  maxBranchesExtra: number | null;
  seatsIncluded: number;
}

// ─── Addon canónico ─────────────────────────────────────────────
export interface CanonicalAddon {
  vertical: Vertical;
  code: string;                    // 'crm', 'invoicing', 'menu_qr_addon_reviews'
  name: string;
  description: string;
  pricing: PricingPair;
  /** Planes donde se puede comprar (si no está incluido) */
  availableFor: string[];
  /** Planes donde ya viene incluido */
  includedIn: string[];
}

// ─── Extra canónico (branch, seat) ──────────────────────────────
export interface CanonicalExtra {
  vertical: Vertical;
  code: string;                    // 'branch', 'seat'
  name: string;
  pricing: PricingPair;
}

// ─── Feature / Entitlement ──────────────────────────────────────
export type FeatureAvailability = 'included' | 'addon' | 'not_available' | 'custom';

export interface CanonicalFeature {
  vertical: Vertical;
  key: string;                     // 'gestion.products', 'menu_builder'
  title: string;
  description: string;
  category: string;
  availability: Record<string, FeatureAvailability>;
}

// ─── Reglas globales ────────────────────────────────────────────
export interface PricingConfig {
  currency: Currency;
  annualDiscountPercent: number;   // 20
  version: string;                 // ISO date '2026-04-09'
}

// ─── Aggregated export ──────────────────────────────────────────
export interface CanonicalPricingData {
  config: PricingConfig;
  plans: CanonicalPlan[];
  addons: CanonicalAddon[];
  extras: CanonicalExtra[];
  features: CanonicalFeature[];
}
```

### 4.2 Qué entra y qué NO entra en el pricing canónico

| Dato | ¿Dentro de pricing canónico? | Motivo |
|------|------------------------------|--------|
| Plan code, name, pricing | ✅ Sí | Dato de negocio fundamental |
| Limits (branches, seats) | ✅ Sí | Condición de negocio del plan |
| Addons (code, pricing, availability) | ✅ Sí | Dato de negocio |
| Extras (branch/seat pricing) | ✅ Sí | Dato de negocio |
| Features catalog (qué incluye cada plan) | ✅ Sí | Define entitlements |
| Descuento anual (20%) | ✅ Sí | Regla de negocio |
| Currency (ARS) | ✅ Sí | Config |
| `badge`, `ctaLabel`, `isRecommended` | ❌ No | Presentación/marketing |
| `description` largo de plan | ❌ No | Copy de marketing |
| `highlight`, plan position/order | ❌ No | Presentación |
| PLAN_KEY_FEATURES (bullet list) | ❌ No | Copy para cards |
| PLAN_META (highlight text) | ❌ No | Copy para UI |
| Feature `title` y `description` | ✅ Sí* | *Solo el título breve; la descripción larga es copy |
| MP checkout URLs, session IDs | ❌ No | Transaccional/runtime |
| Subscription status, period dates | ❌ No | State/runtime |

### 4.3 Separación clara: canónico vs. derivado

```
CANÓNICO (lib/pricing/)
├── Qué planes existen y cuánto cuestan
├── Qué addons/extras existen y cuánto cuestan
├── Qué features incluye cada plan
├── Reglas: descuento anual, limits
└── NO contiene: copy, badges, CTA labels, UI hints

DERIVADO PARA UI (features/billing/data/*-catalog.ts)
├── Importa precios de lib/pricing/
├── Agrega: badges, descriptions largas, ctaLabels
├── Agrega: isRecommended, highlight
├── Agrega: key features bullet lists (PLAN_KEY_FEATURES)
├── Agrega: UI metadata (PLAN_META)
└── Exporta para consumo de componentes React

DERIVADO PARA BACKEND (pricing.json → canonical_pricing.py)
├── JSON generado con precios y reglas
├── Python lee JSON, expone helpers tipados
├── commercial_plans.py consume canonical_pricing
└── preview/checkout/limits operan sobre centavos correctos

COPY DE MARKETING (features/reviews/product.ts, etc.)
├── Importa precios formateados de lib/pricing/
├── Agrega: beneficios, flow steps, CTA text
└── NO define precios propios
```

---

## 5. Separación de Responsabilidades

### 5.1 Pricing canónico (`lib/pricing/`)

**Responsabilidad:** Definir qué existe, cuánto cuesta, y qué reglas aplican.

```
plans.ts    → CanonicalPlan[] para las 3 verticales
addons.ts   → CanonicalAddon[] para todas las verticales
catalog.ts  → CanonicalFeature[] para feature/entitlement mapping
rules.ts    → annualDiscount, pricing invariants
selectors.ts → getPlan(vertical, code), getAddon(vertical, code), etc.
format.ts   → formatCentsToARS(cents) — ÚNICA función de formateo monetario
```

### 5.2 UI / Marketing adapters (`features/billing/data/`)

**Responsabilidad:** Enriquecer datos canónicos con información de presentación.

```typescript
// gestion-comercial-catalog.ts
import { getPlansForVertical, getAddonsForVertical } from '@/lib/pricing';
import { formatCentsToARS } from '@/lib/pricing/format';

const gcPlans = getPlansForVertical('gestion_comercial');

export const GC_PLANS: GcPlanEntry[] = gcPlans.map(plan => ({
  plan: plan.code,
  label: plan.name,
  priceMonthly: plan.pricing.monthly,  // centavos (para formateo)
  priceYearly: plan.pricing.yearly,
  description: GC_DESCRIPTIONS[plan.code],  // copy local
  ctaLabel: GC_CTA_LABELS[plan.code],       // copy local
  badge: plan.code === 'pro' ? 'Recomendado' : undefined,
  isRecommended: plan.code === 'pro',
}));
```

Los catálogos siguen exportando la misma interfaz que hoy → **cero cambios en componentes que ya los consumen**.

### 5.3 Backend billing (`commercial_plans.py`)

**Responsabilidad:** Exponer precios al resto del backend Python manteniendo la misma API.

```python
# canonical_pricing.py — lee pricing.json
import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / 'pricing.json').read_text())

def get_plan_pricing(vertical: str, code: str) -> dict:
    ...

# commercial_plans.py — reescrito para delegar
from .canonical_pricing import get_plan_pricing, get_addon_pricing, get_extra_pricing

_gc_starter = get_plan_pricing('gestion_comercial', 'starter')

PLANS = [
    {
        'code': 'starter',
        'pricing': _gc_starter,  # {'monthly': 3600000, 'yearly': 34560000}
        'limits': { ... },       # limits definidos aquí, no en pricing
        ...
    },
]
```

Los 7 archivos que importan de `commercial_plans.py` no cambian sus imports.

### 5.4 Checkout (`commercial_views.py`)

**Responsabilidad:** Construir MP preferences/preapprovals con precios correctos.

El flujo no cambia conceptualmente. Solo cambian los valores numéricos.

```python
# Hoy: item['unit_price'] / 100.0  →  9900 / 100 = 99.0 (INCORRECTO)
# Post-migración: item['unit_price'] / 100.0  →  3600000 / 100 = 36000.0 (CORRECTO)
```

La conversión `/100.0` sigue siendo correcta — porque ahora los centavos son los correctos.

### 5.5 Seeds (`seed_billing.py`)

**Responsabilidad:** Inicializar DB con datos consistentes.

Pasa a leer de `canonical_pricing.py` en vez de tener valores hardcoded.

### 5.6 Entitlements

**Responsabilidad:** Definir qué puede hacer un negocio según su plan.

El features catalog en `lib/pricing/catalog.ts` define la relación plan → features con `FeatureAvailability`. El backend verifica entitlements consultando la config del plan (que ahora viene de `canonical_pricing.py`). No se duplican features entre frontend y backend.

### 5.7 Adapters / Selectors (`lib/pricing/selectors.ts`)

**Responsabilidad:** API ergonómica para consultar pricing.

```typescript
export function getPlan(vertical: Vertical, code: string): CanonicalPlan | undefined;
export function getPlansForVertical(vertical: Vertical): CanonicalPlan[];
export function getAddon(vertical: Vertical, code: string): CanonicalAddon | undefined;
export function getAddonsForVertical(vertical: Vertical): CanonicalAddon[];
export function getExtra(vertical: Vertical, code: string): CanonicalExtra | undefined;
export function getPlanPrice(vertical: Vertical, code: string, cycle: BillingCycle): CentsARS;
export function isAddonIncludedInPlan(vertical: Vertical, addonCode: string, planCode: string): boolean;
```

---

## 6. Integración con Mercado Pago

### 6.1 Dos flujos de pago

Mi Rubro tiene **dos** flujos MP distintos (hallado en la auditoría):

| Flujo | Endpoint | Mecanismo MP | Cómo llega el precio |
|-------|----------|-------------|---------------------|
| **Suscripción recurrente** | `checkout_session_service.py` | `create_preapproval_plan` → `auto_recurring.transaction_amount` | `float(Plan.price)` — precio en pesos Decimal |
| **Cambio de plan / addon** | `commercial_views.py` | `create_preference` → `items[].unit_price` | `line_item['unit_price'] / 100.0` — centavos a pesos |

### 6.2 Qué valores deben llegar a MP

Ejemplo GC Starter mensual:

```
Canónico:                  3_600_000 centavos
    ↓
preview.py LineItem:       unit_price = 3_600_000 (centavos)
    ↓
commercial_views.py:       unit_price / 100.0 = 36000.0
    ↓
MP preference item:        {'title': 'Starter - Mensual', 'unit_price': 36000.0, 'currency_id': 'ARS'}
    ↓
MP cobra al usuario:       $36.000 ARS ✅
```

Para suscripciones recurrentes:

```
Canónico:                  3_600_000 centavos
    ↓
Plan.price (DB):           Decimal('36000.00')  ← actualizado por seed
    ↓
checkout_session:          float(plan.price) = 36000.0
    ↓
MP preapproval_plan:       {'transaction_amount': 36000.0, 'currency_id': 'ARS'}
    ↓
MP cobra recurrente:       $36.000 ARS/mes ✅
```

### 6.3 Cómo evitar errores de conversión

1. **Un solo lugar de conversión** — `centavos / 100.0` solo ocurre en `commercial_views.py` (preferencias) y `checkout_session_service.py` (suscripciones). Nunca en preview, nunca en selectors.

2. **Plan.price se actualiza desde canonical_pricing** — El seed escribe `Decimal(str(cents / 100))` al Plan.price. `float(plan.price)` = pesos correctos.

3. **Test de paridad** — Un test verifica que `Plan.price * 100 == canonical_pricing.get_plan_pricing(vertical, code)['monthly']`.

### 6.4 Membresías mensuales y renovaciones

MP preapproval plans con `frequency: 1, frequency_type: 'months'` cobran automáticamente cada mes. El `transaction_amount` se fija al crear el plan. Para cambiar precio:

- Se crea un **nuevo** preapproval plan con el precio actualizado.
- Se cancela la suscripción anterior.
- El usuario se suscribe al nuevo plan.

El `price_snapshot` en `SubscriptionV2` registra el precio al momento de la suscripción — esto asegura que si los precios canónicos cambian, las suscripciones existentes mantienen su precio original hasta renovación.

### 6.5 Addons y extras en checkout

Los addons/extras se cobran como line items en una preference (pago único) o se incluyen en el transaction_amount del preapproval plan si es una suscripción que los incluye como paquete. Actualmente se usan preferences para addons standalone — esto sigue igual.

---

## 7. Flujo de Datos Final Propuesto

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FLUJO DE DATOS PRODUCCIÓN                       │
│                                                                         │
│  ┌──────────────────────────────────────────────┐                      │
│  │   lib/pricing/ (FUENTE CANÓNICA)             │                      │
│  │                                              │                      │
│  │   plans.ts  ← CanonicalPlan[] (centavos)     │                      │
│  │   addons.ts ← CanonicalAddon[] (centavos)    │                      │
│  │   catalog.ts ← CanonicalFeature[]            │                      │
│  │   rules.ts  ← descuento anual, config        │                      │
│  │   selectors.ts ← getPlan(), getAddon()       │                      │
│  │   format.ts  ← formatCentsToARS()            │                      │
│  └──────┬───────────────┬───────────────┬───────┘                      │
│         │               │               │                               │
│    ┌────▼────┐   ┌──────▼──────┐  ┌─────▼──────┐                      │
│    │ UI      │   │ Marketing   │  │ Script     │                       │
│    │ Adapters│   │ Adapters    │  │ sync       │                       │
│    │         │   │             │  │            │                       │
│    │ GC      │   │ product.ts  │  │ pricing   │                       │
│    │ catalog │   │ landing     │  │ .json     │                       │
│    │ QR      │   │ sections    │  └─────┬─────┘                       │
│    │ catalog │   └─────────────┘        │                              │
│    └───┬─────┘                    ┌─────▼──────────────────────┐       │
│        │                          │ canonical_pricing.py       │       │
│        ▼                          │ (lee pricing.json)         │       │
│   ┌─────────────────┐            └─────┬──────────────────────┘       │
│   │ Plan Builders   │                  │                               │
│   │ Comparison      │           ┌──────▼──────────────────────┐       │
│   │ Change Dialog   │           │ commercial_plans.py          │       │
│   │ Billing Page    │           │ (reescrito, delega pricing)  │       │
│   └─────────────────┘           └──┬─────┬─────┬─────┬───────┘       │
│                                    │     │     │     │                 │
│                               ┌────▼┐ ┌──▼──┐ ┌▼───┐ ┌▼────────┐    │
│                               │prev │ │limit│ │appl│ │cancellat│    │
│                               │iew  │ │s    │ │y   │ │ion      │    │
│                               └──┬──┘ └─────┘ └────┘ └─────────┘    │
│                                  │                                    │
│                           ┌──────▼──────────────────┐                 │
│                           │ commercial_views.py      │                 │
│                           │ → ÷100 → MP float pesos │                 │
│                           └──────┬──────────────────┘                 │
│                                  │                                    │
│                           ┌──────▼──────────────────┐                 │
│                           │ MercadoPago             │                 │
│                           │ preference / preapproval│                 │
│                           └──────┬──────────────────┘                 │
│                                  │                                    │
│                           ┌──────▼──────────────────┐                 │
│                           │ Webhook → Invoice →     │                 │
│                           │ Subscription Activation │                 │
│                           └─────────────────────────┘                 │
│                                                                         │
│  ┌──────────────────────────────────────────────────┐                  │
│  │ seed_billing.py                                   │                  │
│  │ → lee canonical_pricing.py                        │                  │
│  │ → escribe Bundle.fixed_price_* (centavos)        │                  │
│  │ → escribe Plan.price (Decimal pesos)             │                  │
│  └──────────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Flujo de un cambio de precio

```
1. Desarrollador edita lib/pricing/plans.ts
   → Cambia starter.pricing.monthly de 3_600_000 a 4_000_000

2. npx tsx scripts/sync-pricing-to-backend.ts
   → Regenera services/api/.../pricing.json
   → Script valida: anual = mensual × 12 × 0.8

3. CI pre-merge check:
   → Ejecuta sync-pricing --check (diff contra pricing.json committeado)
   → Ejecuta invariants.test.ts (TypeScript)
   → Ejecuta test_pricing_consistency.py (Python)
   → Si alguno falla → PR bloqueado

4. Deploy:
   → python manage.py seed_billing (actualiza Bundle/Plan en DB)
   → Suscripciones existentes: mantienen price_snapshot original
   → Nuevos checkouts: usan precio actualizado automáticamente
```

---

## 8. Plan de Implementación

### Fase 0: Crear `lib/pricing/` (bajo riesgo, cero impacto)

| Tarea | Archivos | Riesgo |
|-------|----------|--------|
| Crear `lib/pricing/types.ts` | NUEVO | Nulo |
| Crear `lib/pricing/plans.ts` con datos para GC, QR, Reseñas | NUEVO | Nulo |
| Crear `lib/pricing/addons.ts` | NUEVO | Nulo |
| Crear `lib/pricing/catalog.ts` (features) | NUEVO | Nulo |
| Crear `lib/pricing/rules.ts` | NUEVO | Nulo |
| Crear `lib/pricing/selectors.ts` | NUEVO | Nulo |
| Crear `lib/pricing/format.ts` (`formatCentsToARS()`) | NUEVO | Nulo |
| Crear `lib/pricing/index.ts` | NUEVO | Nulo |
| Crear `lib/pricing/__tests__/invariants.test.ts` | NUEVO | Nulo |

**Criterio de aceptación:** Tests pasan. `getPlan('gestion_comercial', 'starter').pricing.monthly === 3_600_000`. `formatCentsToARS(3_600_000) === '$36.000'`.

### Fase 1: Script de sync + backend canónico (bajo riesgo)

| Tarea | Archivos | Riesgo |
|-------|----------|--------|
| Crear `lib/pricing/export-json.ts` | NUEVO | Nulo |
| Crear `scripts/sync-pricing-to-backend.ts` | NUEVO | Bajo |
| Generar `services/api/.../pricing.json` | NUEVO | Nulo |
| Crear `canonical_pricing.py` | NUEVO | Bajo |
| Crear `test_pricing_consistency.py` | NUEVO | Nulo |

**Criterio:** `canonical_pricing.get_plan_pricing('gestion_comercial', 'starter') == {'monthly': 3600000, 'yearly': 34560000}`. Tests pasan. `sync-pricing --check` pasa.

### Fase 2: Refactorizar catálogos como adaptadores (riesgo bajo-medio)

| Tarea | Archivos | Riesgo |
|-------|----------|--------|
| Refactorizar `gestion-comercial-catalog.ts` para importar de `lib/pricing/` | MODIFICAR | Bajo |
| Refactorizar `menu-qr-catalog.ts` para importar de `lib/pricing/` | MODIFICAR | Bajo |
| Crear `qr-reviews-catalog.ts` importando de `lib/pricing/` | NUEVO | Bajo |
| Refactorizar `QrReviewsPlanBuilder.tsx`: imports del nuevo catálogo | MODIFICAR | Bajo |
| Refactorizar `reviews/product.ts`: imports de `lib/pricing/` | MODIFICAR | Bajo |
| Convertir addon/extra pricing de strings a números en catálogos | MODIFICAR | Medio |
| Eliminar `formatArsPrice()` de `menu-qr-catalog.ts`, usar `lib/pricing/format.ts` | MODIFICAR | Bajo |

**Criterio:** Marketing landings y plan builders renderizan exactamente igual. No quedan precios inline o strings. Todos los componentes importan precios de `lib/pricing/` (indirectamente vía catalogos o directamente).

### Fase 3: Migrar backend a precios reales (CRÍTICO — deploy atómico)

| Tarea | Archivos | Riesgo |
|-------|----------|--------|
| Reescribir `commercial_plans.py` para consumir `canonical_pricing` | MODIFICAR | CRÍTICO |
| Actualizar `seed_billing.py` — Bundles y Plans con precios correctos | MODIFICAR | ALTO |
| Ejecutar `seed_billing` en staging | MANUAL | ALTO |
| Verificar preview: line_items en centavos correctos | TEST | - |
| Verificar checkout: MP preference con pesos correctos | TEST | - |
| Verificar preapproval: Plan.price con pesos correctos | TEST | - |

**NOTA:** La conversión `/100.0` en `commercial_views.py` L465/L691 **NO se toca**. Sigue dividiendo centavos entre 100. Lo que cambia son los centavos de entrada: de `9900` a `3_600_000`, resultando en `36000.0` pesos para MP en vez de `99.0`.

**Criterio:** Un checkout de GC Starter genera MP preference con `unit_price: 36000.0`. Un nuevo preapproval plan tiene `transaction_amount: 36000.0`. Suscripciones existentes NO se alteran.

### Fase 4: Migrar componentes hardcoded (riesgo medio)

| Tarea | Archivos | Riesgo |
|-------|----------|--------|
| Migrar `plan-comparison.tsx`: eliminar PLANS[], importar de `lib/pricing/` | MODIFICAR | Medio |
| Migrar `plan-change-dialog.tsx`: eliminar strings hardcoded | MODIFICAR | Medio |
| Migrar `addon-purchase-dialog.tsx`: cambiar `formatPrice(cents)` | MODIFICAR | Bajo |
| Migrar `billing-page-client.tsx`: cambiar `formatPrice(cents)` | MODIFICAR | Bajo |
| Eliminar todas las funciones `formatPrice()` locales | MODIFICAR (4 archivos) | Bajo |

**Criterio:** `plan-comparison.tsx` muestra $36.000 / $50.000 / $75.000. No existe ninguna función `formatPrice()` que divida por 100 de forma local. Todos usan `formatCentsToARS()` de `lib/pricing/format.ts`.

### Fase 5: Cleanup y validación (bajo riesgo)

| Tarea | Archivos | Riesgo |
|-------|----------|--------|
| Evaluar `CommercialPlanBuilder.tsx` — marcar para eliminación | DEPRECAR | Bajo |
| Evaluar `PlansBuilderWizard.tsx` — marcar para eliminación | DEPRECAR | Bajo |
| Agregar CI check: `sync-pricing --check` | CI config | Bajo |
| Documentar flujo de cambio de precios en README | docs | Nulo |

### Orden de deploy

```
Deploy 1 — Fases 0 + 1 (solo archivos nuevos, cero impacto):
  ✅ lib/pricing/ completo
  ✅ scripts/sync-pricing-to-backend.ts
  ✅ pricing.json + canonical_pricing.py
  ✅ Tests nuevos

Deploy 2 — Fase 2 (refactor catalogs):
  ✅ Catálogos refactorizados como adaptadores
  ✅ QR Reviews catalog creado
  ✅ formatArsPrice → formatCentsToARS

Deploy 3 — Fase 3 (CRÍTICO, atómico, con staging previo):
  ⚠️ commercial_plans.py reescrito
  ⚠️ seed_billing.py actualizado
  ⚠️ Ejecutar seed en producción post-deploy

Deploy 4 — Fases 4 + 5 (cleanup):
  ✅ Componentes hardcoded migrados
  ✅ cleanup de dead code
  ✅ CI checks activos
```

---

## 9. Criterios de Aceptación

### Tests automatizados que deben existir

#### TypeScript (`lib/pricing/__tests__/invariants.test.ts`)

```typescript
describe('Pricing invariants', () => {
  test('all plans have yearly = monthly × 12 × 0.8', () => {
    for (const plan of ALL_PLANS) {
      if (plan.isCustom) continue;
      expect(plan.pricing.yearly).toBe(
        Math.round(plan.pricing.monthly * 12 * 0.8)
      );
    }
  });

  test('all prices are positive integers', () => {
    for (const plan of ALL_PLANS) {
      if (plan.isCustom) continue;
      expect(Number.isInteger(plan.pricing.monthly)).toBe(true);
      expect(plan.pricing.monthly).toBeGreaterThan(0);
    }
  });

  test('addon availability references valid plan codes', () => {
    const validCodes = new Set(ALL_PLANS.map(p => p.code));
    for (const addon of ALL_ADDONS) {
      for (const code of [...addon.availableFor, ...addon.includedIn]) {
        expect(validCodes.has(code)).toBe(true);
      }
    }
  });

  test('every vertical has at least one plan', () => {
    for (const v of ['gestion_comercial', 'menu_qr', 'qr_reviews'] as const) {
      expect(getPlansForVertical(v).length).toBeGreaterThan(0);
    }
  });

  test('formatCentsToARS formats correctly', () => {
    expect(formatCentsToARS(3_600_000)).toBe('$36.000');
    expect(formatCentsToARS(100)).toBe('$1');
    expect(formatCentsToARS(0)).toBe('$0');
  });
});
```

#### Python (`test_pricing_consistency.py`)

```python
class PricingConsistencyTest(TestCase):
    def test_commercial_plans_match_canonical(self):
        """Precios en commercial_plans.py coinciden con pricing.json."""
        for plan in PLANS:
            if plan.get('is_custom'):
                continue
            canonical = get_plan_pricing('gestion_comercial', plan['code'])
            self.assertEqual(plan['pricing'], canonical)

    def test_extras_match_canonical(self):
        self.assertEqual(BRANCH_EXTRA_PRICING, get_extra_pricing('gestion_comercial', 'branch'))
        self.assertEqual(SEAT_EXTRA_PRICING, get_extra_pricing('gestion_comercial', 'seat'))

    def test_annual_discount_20_percent(self):
        for plan in PLANS:
            if plan.get('is_custom'):
                continue
            expected = round(plan['pricing']['monthly'] * 12 * 0.8)
            self.assertEqual(plan['pricing']['yearly'], expected)

    def test_plan_price_model_matches_centavos(self):
        """Plan.price (Decimal pesos) × 100 == canonical centavos."""
        from apps.billing.models import Plan
        for plan_obj in Plan.objects.filter(plan_status='active'):
            canonical = get_plan_pricing_by_plan_code(plan_obj.code)
            if canonical:
                expected_pesos = Decimal(str(canonical['monthly'] / 100))
                self.assertEqual(plan_obj.price, expected_pesos)
```

#### CI checks

```yaml
# En CI pipeline (GitHub Actions / similar)
- name: Verify pricing.json is up to date
  run: npx tsx scripts/sync-pricing-to-backend.ts --check

- name: Run pricing invariant tests
  run: cd apps/web && npx vitest run lib/pricing/__tests__/

- name: Run Python pricing consistency
  run: cd services/api && python manage.py test apps.billing.tests.test_pricing_consistency
```

### Validación manual (staging checklist)

- [ ] Landing de GC muestra $36.000 / $50.000 / $75.000
- [ ] Landing de Menú QR muestra $18.000 / $30.000 / $55.000
- [ ] `/app/servicios` GC muestra $36.000 / $50.000 / $75.000
- [ ] Plan comparison table muestra los mismos precios
- [ ] Plan change dialog muestra addons a $8.000 y $15.000
- [ ] Preview de cambio de plan: line items con importes correctos
- [ ] Checkout MP: preference con unit_price $36.000 para Starter
- [ ] Suscripción MP: preapproval con transaction_amount $36.000
- [ ] Dashboard billing: precios consistentes con lo cobrado
- [ ] Addon checkout: unit_price correcto en preference
- [ ] Seed billing: Bundle.fixed_price_monthly = 3600000

---

## 10. Recomendación Final

### Decisión concreta

1. **Crear `apps/web/src/lib/pricing/`** como fuente canónica única de precios para toda la plataforma. Es un módulo de dominio neutral, desacoplado de UI y de marketing. Contiene _solo_ datos de negocio y reglas de pricing.

2. **Usar centavos ARS enteros** como unidad canónica interna. Es consistente con el backend existente, con el estándar de la industria payments, y tiene un solo punto de conversión a pesos para display/MP.

3. **Los catálogos existentes se convierten en adaptadores de UI** — importan precios de `lib/pricing/`, agregan copy y badges, exportan para componentes React. No se eliminan, no se rompen. Los componentes que ya los consumen siguen funcionando sin cambios.

4. **Un script genera `pricing.json`** que el backend Python consume. El script se ejecuta manualmente y en CI. El JSON se commitea al repo para que sea auditable y determinístico.

5. **`commercial_plans.py` se reescribe para delegar pricing** a `canonical_pricing.py`, manteniendo la misma API pública. Los 7 archivos que importan de él no necesitan cambios.

6. **Los precios se actualizan a los de negocio reales**: GC Starter $36.000, Pro $50.000, Business $75.000, etc. Esto corrige la divergencia de 150-364× que existe hoy entre lo que se muestra y lo que se cobra.

### Lo que NO se hace

- **No se crea un `packages/pricing/`** — el monorepo no tiene la infraestructura y sería sobre-ingeniería.
- **No se cambian imports de componentes existentes** (en fases iniciales) — los catálogos siguen siendo la interfaz para los componentes; solo cambia de dónde los catálogos obtienen sus datos.
- **No se migra de centavos a pesos en el backend** — el backend ya trabaja en centavos y es el estándar correcto.
- **No se toca la conversión `/100.0` en Mercado Pago** — sigue siendo correcta; lo que cambia son los valores de entrada.
- **No se alteran suscripciones existentes** — el `price_snapshot` en `SubscriptionV2` preserva el precio original.

### Resultado esperado

Con esta implementación, modificar un precio requiere:

1. Editar **un número** en `lib/pricing/plans.ts`
2. Correr `npx tsx scripts/sync-pricing-to-backend.ts`
3. Commit + push → CI verifica todo automáticamente

No hay drift. No hay duplicación. No hay manual sync. No hay conversiones ambiguas.
