# Evaluación Técnica: Unidad Monetaria Canónica

> **Fecha:** 9 de abril de 2026  
> **Alcance:** Decisión de unidad monetaria para `lib/pricing/` (fuente canónica)  
> **Opciones:** (A) Pesos ARS enteros vs. (B) Centavos ARS enteros

---

## 1. Mapa Actual de Unidades Monetarias

Auditado archivo por archivo contra el repo real:

### Pesos enteros (int)

| Pieza | Archivo(s) | Ejemplo | Nota |
|-------|-----------|---------|------|
| GC Catalog `priceMonthly` | `gestion-comercial-catalog.ts` | `36000` | Son los precios de negocio correctos |
| QR Catalog `priceMonthly` | `menu-qr-catalog.ts` | `18000` / `30000` / `55000` | Idem |
| QR Reviews inline | `QrReviewsPlanBuilder.tsx` | `25000` / `35000` | Hardcoded en componente |
| `formatARS(value)` | `lib/format.ts` | `formatARS(36000)` → `$36.000` | **No divide**, recibe pesos directos |
| `formatArsPrice(value)` | `menu-qr-catalog.ts` | Recibe pesos, usa `Intl.NumberFormat` | **No divide** |

### Centavos enteros (int)

| Pieza | Archivo(s) | Ejemplo | Nota |
|-------|-----------|---------|------|
| `commercial_plans.py` PLANS | `commercial_plans.py` | `9900` = $99 | TypedDict: `monthly: int  # En centavos` |
| `commercial_plans.py` ADDONS | `commercial_plans.py` | `2000` = $20 | Idem |
| `BRANCH_EXTRA_PRICING` | `commercial_plans.py` | `5000` = $50 | Idem |
| `SEAT_EXTRA_PRICING` | `commercial_plans.py` | `500` = $5 | Idem |
| `Module.price_monthly` | `models.py` IntegerField | `0` (módulos core) | `help_text="Price in cents"` |
| `Bundle.fixed_price_monthly` | `models.py` IntegerField | `9900` | `help_text="Override price in cents"` |
| `Promotion.fixed_override_price` | `models.py` IntegerField | — | Sin help_text pero se infiere centavos |
| `PendingSubscriptionChange.total_amount` | `models.py` IntegerField | — | `help_text="Total amount in centavos"` |
| `preview.py` LineItem | `preview.py` TypedDict | `unit_price: int  # in centavos` | Toda la preview opera en centavos |
| `preview.py` PreviewResult | `preview.py` TypedDict | `subtotal: int  # in centavos` | Idem |
| `formatPrice(cents)` ×4 copias | `plan-comparison.tsx`, `plan-change-dialog.tsx`, `billing-page-client.tsx`, `addon-purchase-dialog.tsx` | `(cents / 100).toFixed(0)` | 4 funciones locales duplicadas |

### Decimal en pesos

| Pieza | Archivo(s) | Ejemplo | Nota |
|-------|-----------|---------|------|
| `Plan.price` | `models.py` DecimalField(10,2) | `Decimal('99.00')` | Seeds: `Decimal('99.00')` a `Decimal('499.00')` |
| `BillingInvoiceEvent.amount` | `models.py` DecimalField | — | Registra monto del pago real |

### Float en pesos (solo para MP)

| Pieza | Archivo(s) | Ejemplo | Nota |
|-------|-----------|---------|------|
| MP preapproval `transaction_amount` | `checkout_session_service.py` L256 | `float(plan.price)` → `99.0` | Directo de Plan.price (Decimal pesos) |
| MP preference `unit_price` | `commercial_views.py` L465 | `item['unit_price'] / 100.0` → `99.0` | Convierte preview centavos a pesos |
| MP addon preference `unit_price` | `commercial_views.py` L691 | `price / 100.0` → `20.0` | Idem para addons |

### Strings de display

| Pieza | Archivo(s) | Ejemplo | Nota |
|-------|-----------|---------|------|
| GC Catalog addon pricing | `gestion-comercial-catalog.ts` | `'$8.000/mes'` | No calculable |
| QR Catalog addon pricing | `menu-qr-catalog.ts` | `'$12.000/mes'` | No calculable |
| `reviews/product.ts` | `product.ts` | `'$25.000'` | No calculable |
| `plan-change-dialog.tsx` hardcoded | `plan-change-dialog.tsx` | `"$20/mes"`, `"$150/mes"` | Strings sueltos sin variable |

### Resumen visual

```
╔══════════════════════════════╦════════════════════╦═══════════════════════╗
║         CAPA                 ║  UNIDAD HOY        ║  PROBLEMAS            ║
╠══════════════════════════════╬════════════════════╬═══════════════════════╣
║ Catálogos marketing TS       ║ Pesos enteros      ║ Precios correctos     ║
║ Plan.price (DB)              ║ Decimal pesos      ║ Valores placeholder   ║
║ commercial_plans.py          ║ Centavos enteros   ║ Valores placeholder   ║
║ Module / Bundle (DB)         ║ Centavos enteros   ║ Valores placeholder   ║
║ PendingSubscriptionChange    ║ Centavos enteros   ║ —                     ║
║ preview.py LineItem          ║ Centavos enteros   ║ —                     ║
║ commercial_views → MP        ║ Pesos float (/100) ║ Conversión implícita  ║
║ checkout_session → MP        ║ Pesos float (cast) ║ Directo de Plan.price ║
║ formatPrice() frontend ×4   ║ Centavos (÷100)    ║ 4 copias duplicadas   ║
║ formatARS() / formatArsPrice ║ Pesos (sin ÷)     ║ —                     ║
║ Addon/Extra pricing catálogo ║ Strings            ║ No calculable         ║
╚══════════════════════════════╩════════════════════╩═══════════════════════╝
```

---

## 2. Opción A: Pesos Enteros — Pros y Contras

**Canónico:** `pricing: { monthly: 36000 }` donde `36000` = $36.000 ARS

### Pros

1. **Coincide con MercadoPago nativamente.** MP recibe pesos en `transaction_amount` y `unit_price`. Si el canónico es pesos, el número que se escribe en la fuente es el mismo que MP cobra. Zero conversión en la capa de pagos.

2. **Coincide con el lenguaje de negocio.** Producto dice "Starter cuesta $36.000/mes". El dev escribe `36000`. No hay multiplicación mental.

3. **Coincide con los catálogos que ya tienen los precios correctos.** Los catálogos de marketing (GC y QR) ya usan pesos enteros con los valores de negocio correctos. La fuente canónica adoptaría la misma unidad que las únicas piezas que hoy tienen precios reales.

4. **Coincide con `Plan.price` (DecimalField).** El modelo Plan ya almacena pesos. Con pesos canónico, `Plan.price = Decimal('36000.00')` → `float(plan.price)` → MP cobra `36000.0`. Lineal.

5. **Coincide con formatters de display.** `formatARS(36000)` → `"$36.000"`. Sin divisiones intermedias.

6. **Mínimo riesgo de error humano al editar precios.** El dev lee `36000`, entiende `$36.000`. Si producto pide cambiar a `$40.000`, escribe `40000`. Sin multiplicar ni dividir.

7. **ARS no usa centavos comercialmente.** Ningún precio de SaaS en Argentina usa sub-peso. Los centavos no aportan precisión útil.

### Contras

1. **Inconsistente con backend actual.** `commercial_plans.py`, Module, Bundle, PendingSubscriptionChange y preview todos usan centavos. Migrar a pesos requiere tocar esos archivos y modelos.

2. **Contra "estándar de industria billing".** Stripe, PayPal y otros usan la unidad mínima de la moneda. Elegir pesos se desvía de esa convención.

3. **Si algún día hay precios con centavos, no se pueden representar como enteros.** Ejemplo: $99,50 no es representable como `int` en pesos. (Contraargumento: en ARS esto es prácticamente imposible para SaaS pricing, y si ocurriera se resuelve con Decimal puntual.)

4. **Prorrateo diario puede dar fracciones.** `36000 / 30 × 17 = 20400` (OK), pero `8000 / 30 × 17 = 4533.33` requiere redondeo al peso. (Contraargumento: centavos tampoco eliminan esto — `800000 / 30 × 17 = 453333.33`, también requiere redondeo. La diferencia es que se redondea a $1 vs a $0.01, ambos irrelevantes para ARS.)

---

## 3. Opción B: Centavos Enteros — Pros y Contras

**Canónico:** `pricing: { monthly: 3_600_000 }` donde `3_600_000` = $36.000,00 ARS

### Pros

1. **Consistente con backend actual.** Module, Bundle, PendingSubscriptionChange, preview, commercial_plans todos usan centavos. No requiere migrar esos modelos.

2. **Convención billing estándar.** Stripe, PayPal usan "smallest currency unit". Cualquier dev con experience en fintech lo espera.

3. **Soporta sub-peso teórico.** $99,50 se representa como `9950`. (Irrelevante en práctica para ARS.)

4. **Menos cambios en backend.** `commercial_plans.py` ya está en centavos; solo cambian los valores numéricos, no la estructura ni las conversiones existentes.

### Contras

1. **No coincide con MercadoPago.** MP recibe pesos. Siempre hay que dividir por 100 antes de enviar. Si la conversión falla, falta, o se aplica doble: cobro incorrecto con dinero real.

2. **No coincide con el lenguaje de negocio.** Producto dice "$36.000/mes". Dev escribe `3_600_000`. Requiere multiplicar mentalmente ×100. Error-prone.

3. **No coincide con los catálogos correctos.** Los catálogos de marketing usan pesos enteros. Si canónico es centavos, los catálogos necesitan una conversión ×100 para adoptar la fuente canónica, o los valores canónicos quedan en una unidad distinta a la que las únicas piezas correctas ya usan.

4. **No coincide con `Plan.price`.** Plan.price es Decimal pesos. Si canónico es centavos, hay que convertir canónico → Plan.price (`÷100`), y luego Plan.price → MP (`float()`, ya pesos). Dos conversiones.

5. **No coincide con display.** `$36.000` requiere dividir el canónico. Cada punto de display necesita adaptador.

6. **7 dígitos son difíciles de leer.** `3_600_000` vs `3_500_000` — la diferencia es $1.000 ARS pero visualmente son casi idénticos. Con pesos: `36000` vs `35000` — inmediatamente claro.

7. **El argumento "estándar de industria" no aplica directamente.** Stripe usa centavos porque opera en 100+ monedas con subunidades distintas. Mi Rubro opera exclusivamente en ARS. La convención existe para generalización multi-moneda, no para decisiones de fuente canónica single-currency.

8. **Mayor riesgo de error de cobro real.** Si alguien pone `3600000` (correcto) vs `360000` (falta un cero) → MP cobra $3.600 en vez de $36.000. La magnitud del error es de un orden de magnitud pero los números son similares visualmente.

---

## 4. Evaluación Específica con Mercado Pago

### Cómo funciona MP

MercadoPago siempre recibe **pesos ARS** (no centavos):

- `create_preapproval_plan()` → `auto_recurring.transaction_amount`: pesos float
- `create_preference()` → `items[].unit_price`: pesos float

Esto está verificado en el código real:

**Flujo 1 — Suscripción recurrente (preapproval):**
```python
# checkout_session_service.py L256
"transaction_amount": float(plan.price),   # Plan.price es Decimal('99.00') → 99.0
```

**Flujo 2 — Cambio de plan (preference):**
```python
# commercial_views.py L465
'unit_price': item['unit_price'] / 100.0,  # preview centavos 9900 → 99.0
```

**Flujo 3 — Addon purchase (preference):**
```python
# commercial_views.py L691
'unit_price': price / 100.0,               # addon centavos 2000 → 20.0
```

### Impacto por opción

#### Con Opción A (pesos canónico)

**Flujo 1 (preapproval):**
```
canonical: 36000 (pesos)
    → Plan.price = Decimal('36000.00')
    → float(plan.price) = 36000.0
    → MP cobra $36.000 ✅
```
Conversiones: **cero**. El número canónico ES el que MP recibe.

**Flujo 2 y 3 (preference):**

*Variante A1*: Si backend migra a pesos internamente:
```
canonical: 36000 (pesos)
    → preview unit_price = 36000 (pesos)
    → commercial_views: 36000 (ELIMINAR / 100.0)
    → MP recibe 36000.0
    → MP cobra $36.000 ✅
```
Conversiones: **cero**. Se elimina la `/100.0`.

*Variante A2*: Si backend mantiene centavos internamente:
```
canonical: 36000 (pesos)
    → canonical_pricing.py: 36000 × 100 = 3600000 (centavos, para backend)
    → preview unit_price = 3600000 (centavos)
    → commercial_views: 3600000 / 100.0 = 36000.0
    → MP cobra $36.000 ✅
```
Conversiones: **dos** (×100 entrando, /100 saliendo) — pero se cancelan y son en capas internas, no expuestas a edición humana.

#### Con Opción B (centavos canónico)

**Flujo 1 (preapproval):**
```
canonical: 3_600_000 (centavos)
    → Plan.price = Decimal(str(3600000 / 100)) = Decimal('36000.00')
    → float(plan.price) = 36000.0
    → MP cobra $36.000 ✅
```
Conversiones: **una** (÷100 para Plan.price). Riesgo: si la conversión falla o se aplica mal al seedear, Plan.price queda incorrecto y MP cobra mal.

**Flujo 2 y 3 (preference):**
```
canonical: 3_600_000 (centavos)
    → preview unit_price = 3600000 (centavos, nativo)
    → commercial_views: 3600000 / 100.0 = 36000.0
    → MP cobra $36.000 ✅
```
Conversiones: **una** (/100 para MP). La `/100.0` existente se mantiene.

### Comparación de riesgo MP

| Escenario de error | Pesos (A) | Centavos (B) |
|---|---|---|
| Dev escribe el precio equivocado | `40000` en vez de `36000` → MP cobra $40.000 (error de negocio, no de unidad) | `4000000` en vez de `3600000` → idem |
| Dev olvida un cero | `3600` → MP cobra $3.600 (obvio visualmente) | `360000` → MP cobra $3.600 (menos obvio entre 7 dígitos) |
| Se aplica `/100` de más | Imposible: no hay `/100` en el path de preapproval | Posible si alguien agrega `/100` pensando que Plan.price está en centavos |
| Se olvida `/100` para preference | N/A si se elimina (Variante A1); o es el `/100` existente (A2) | El `/100` existente sigue, riesgo bajo |
| Plan.price se seedea mal | `Decimal('36000.00')` = obvio | `Decimal(str(3600000/100))` = hay cálculo, puede fallar |

**Conclusión MP: Opción A reduce riesgo de cobro incorrecto** porque el número canónico es el mismo que MP espera. Con B, hay al menos una conversión adicional en el path de preapproval que no existe con A.

---

## 5. Evaluación de DX / Mantenibilidad / Riesgo Humano

### Legibilidad humana

| Criterio | Pesos (A) | Centavos (B) |
|---|---|---|
| Plan Starter mensual | `36000` → lee directo: "$36.000" | `3_600_000` → necesita dividir mentalmente por 100 |
| Addon CRM mensual | `8000` → "$8.000" | `800_000` → "$8.000" |
| Seat extra mensual | `500` → "$500" | `50_000` → "$500" |
| Plan Pro anual | `480000` → "$480.000" | `48_000_000` → "$480.000" |
| **Ganador** | **A — lectura directa** | B — requiere cálculo mental |

### Facilidad para cambiar precios

Producto dice: "Subí el Starter de $36.000 a $40.000":

- **A:** Dev cambia `36000` → `40000`. Listo.
- **B:** Dev cambia `3_600_000` → `4_000_000`. ¿O era `40_000_00`? ¿O `400_0000`? Los separadores de miles ayudan pero no eliminan el error.

### Facilidad para seeds

Hoy el seed escribe `Plan.price = Decimal('99.00')`.

- **A:** Seed escribe `Decimal('36000.00')` directo del canónico.
- **B:** Seed calcula `Decimal(str(3600000 / 100))` → `Decimal('36000.0')` — aritmética intermedia.

### Facilidad para tests

Test verifica que checkout genera precio correcto:

- **A:** `assert mp_preference['items'][0]['unit_price'] == 36000.0` — el número canónico
- **B:** `assert mp_preference['items'][0]['unit_price'] == 3600000 / 100` — necesita saber la conversión

### Claridad para equipo producto y devs

- **A:** "El archivo dice `36000`, MP cobra `36000`, la UI muestra `$36.000`" — **una sola realidad numérica**.
- **B:** "El archivo dice `3_600_000`, MP cobra `36000`, la UI muestra `$36.000`" — el equipo necesita saber que el archivo está en otra unidad.

### Extensibilidad futura

| Escenario futuro | Pesos (A) | Centavos (B) |
|---|---|---|
| USD como segunda moneda | Agregar moneda y usar Decimal o centavos para USD, sin afectar ARS | Natural para USD ($9.99 = 999 cents) |
| Descuento 15% sobre $36.000 | `36000 × 0.85 = 30600` ✅ int exacto | `3600000 × 0.85 = 3060000` ✅ int exacto |
| Prorrateo diario (17/30 de $8.000) | `8000 × 17/30 = 4533.33` → redondear a `4533` | `800000 × 17/30 = 453333.33` → redondear a `453333` |
| Precio con centavos ($99.50) | No representable como int → usar Decimal puntual | `9950` ✅ representable como int |

La ventaja de centavos en precisión sub-peso es **teórica para ARS**. Ningún precio de Mi Rubro usa centavos hoy ni hay plan de hacerlo. Si algún día ocurre (muy improbable para SaaS ARS), Decimal puntual lo resuelve sin cambiar el sistema completo.

### Cuadro resumen DX

| Dimensión | Pesos (A) | Centavos (B) | Ganador |
|---|---|---|---|
| Legibilidad humana | ✅ Directo | ❌ Mental /100 | A |
| Cambio de precios | ✅ Trivial | ⚠ Propenso a error | A |
| Riesgo error humano | ✅ Bajo | ⚠ Medio | A |
| Consistencia con MP | ✅ Nativa | ❌ Requiere /100 | A |
| Consistencia con DB/backend | ❌ Requiere migración | ✅ Nativa | B |
| Facilidad seeds | ✅ Directo | ⚠ Conversión | A |
| Facilidad previews | ⚠ Adaptar unidad | ✅ Nativo | B |
| Facilidad checkout | ✅ Directo a MP | ⚠ /100 a MP | A |
| Facilidad adapters frontend | ✅ Catalog ya en pesos | ⚠ Conversión | A |
| Claridad equipo | ✅ Un solo número | ⚠ Dos mundos | A |
| Extensibilidad multi-moneda | ⚠ Limitado para subunits | ✅ Estándar | B |
| Sub-peso pricing | ❌ Requiere Decimal | ✅ Nativo | B |
| Convención industria | ❌ No estándar | ✅ Estándar | B |
| **Score** | **9 / 13** | **4 / 13** | **A** |

---

## 6. Recomendación Final

### Opción A: Pesos ARS enteros

La unidad canónica de la fuente de verdad (`lib/pricing/plans.ts`) debe ser **pesos ARS enteros**.

### Por qué

1. **MercadoPago recibe pesos.** El número canónico fluye directo a MP sin conversión. Esto elimina la categoría entera de "errores de conversión a pesos" en la capa de pagos — la más peligrosa.

2. **Negocio piensa en pesos.** La fuente canónica es un archivo que humanos editan cuando cambian precios. Debe hablar el idioma del equipo de producto: pesos.

3. **Los catálogos correctos ya están en pesos.** Las únicas piezas del repo que hoy tienen los precios reales de negocio ($36.000, $50.000, $75.000) usan pesos enteros. Adoptar pesos como unidad canónica es adoptar la unidad que ya demostró funcionar en las piezas correctas.

4. **`Plan.price` ya es pesos Decimal.** El modelo que alimenta MP preapproval ya está en pesos. Con canónico en pesos, la relación es directa.

5. **10 de 13 dimensiones de evaluación favorecen A.** Las 3 que favorecen centavos son teóricas (multi-moneda, sub-peso, convención) y no aplican al contexto real de Mi Rubro hoy.

### Qué desventajas aceptamos

1. **Migración del backend de centavos a pesos.** Los modelos Module, Bundle, PendingSubscriptionChange, y los archivos commercial_plans.py, preview.py necesitan cambiar de centavos a pesos. Es trabajo real, pero es un cambio de valores + help_text, no un rediseño.

2. **Desvío de la convención Stripe/PayPal.** Aceptamos no seguir "smallest currency unit" porque la razón de esa convención (soporte multi-moneda de 100+ países) no aplica a un sistema single-currency ARS. Si algún día se agrega USD, se definirá la unidad para esa moneda sin afectar ARS.

3. **Imposibilidad de representar $99,50 como integer pesos.** Aceptamos porque:
   - No existe ningún precio con centavos hoy en Mi Rubro.
   - No hay plan de crear ninguno.
   - Argentina no usa centavos en pricing SaaS.
   - Si fuera necesario algún día, se usa Decimal puntual en ese campo específico.

### Qué adapters hay que implementar

Solo **un adapter backend** es necesario:

| Adapter | Dónde | Qué hace |
|---------|-------|----------|
| `canonical_pricing.py` lee pricing.json | `services/api/.../billing/` | Expone precios directamente en pesos (misma unidad que el canónico). Los modelos DB pasan a almacenar pesos. No hay conversión. |

**Adapters de UI**: cero. Los catálogos ya usan pesos. `formatARS()` ya recibe pesos.

**Adapter para MP**: cero. MP ya recibe pesos.

---

## 7. Cómo Quedan las Conversiones por Capa

### Distinción de capas de unidad

| Capa | Concepto | Unidad recomendada |
|------|----------|-------------------|
| **Canónica de negocio** | Lo que escribe el dev / define producto | **Pesos enteros** |
| **Interna de cálculo** (backend) | Preview, line items, totales | **Pesos enteros** (migrar de centavos) |
| **Persistencia** (DB) | Module, Bundle, PendingSubscriptionChange, Plan | **Pesos enteros** (migrar IntegerField help_text + valores; Plan.price ya pesos) |
| **Enviada a MercadoPago** | transaction_amount, unit_price | **Pesos float** (cast directo, sin ÷100) |
| **Display** (frontend) | formatARS, UI | **Pesos** → `Intl.NumberFormat` directo |

### Flujo sin conversiones

```
lib/pricing/plans.ts          →  { monthly: 36000 }          PESOS INT
        │
        ├──→ catálogos UI     →  priceMonthly: 36000          PESOS INT (import directo)
        │       └──→ display  →  formatARS(36000) → "$36.000" PESOS
        │
        └──→ pricing.json     →  { "monthly": 36000 }         PESOS INT
                │
                └──→ canonical_pricing.py → 36000              PESOS INT
                        │
                        ├──→ commercial_plans.py → 36000       PESOS INT
                        │       │
                        │       ├──→ preview.py LineItem        PESOS INT
                        │       │       └──→ commercial_views
                        │       │               └──→ MP preference
                        │       │                    unit_price: 36000.0   PESOS FLOAT
                        │       │
                        │       └──→ limits.py                  PESOS INT
                        │
                        └──→ seed_billing.py
                                ├──→ Bundle.fixed_price = 36000 PESOS INT
                                └──→ Plan.price = Decimal('36000.00')
                                        └──→ checkout_session
                                              transaction_amount: 36000.0   PESOS FLOAT
```

**Conversiones necesarias: CERO.**

El único cast es `float(plan.price)` para MP y `Decimal(str(price))` para el seed — son cambios de tipo (int→Decimal, Decimal→float), no cambios de magnitud.

### Comparación con centavos

Si el canónico fuera centavos, el flujo tendría:

```
lib/pricing/plans.ts          →  { monthly: 3_600_000 }        CENTAVOS
        │
        ├──→ catálogos UI     →  priceMonthly: 3600000 / 100   CONVERSIÓN 1 (÷100)
        │       └──→ display  →  formatARS(36000) → "$36.000"
        │
        └──→ pricing.json     →  3600000                        CENTAVOS
                │
                └──→ canonical_pricing.py → 3600000             CENTAVOS (nativo)
                        │
                        ├──→ preview.py → 3600000               CENTAVOS
                        │       └──→ commercial_views
                        │               └──→ 3600000 / 100.0    CONVERSIÓN 2 (÷100)
                        │                    → MP: 36000.0
                        │
                        └──→ seed_billing.py
                                └──→ Plan.price = Decimal(str(3600000/100))  CONVERSIÓN 3 (÷100)
                                        └──→ float(plan.price) → 36000.0
```

**Conversiones necesarias: 3** (catalog ÷100, commercial_views ÷100, seed ÷100).

---

## 8. Impacto de Migración

### Archivos que cambian

| Archivo | Cambio | Complejidad |
|---------|--------|-------------|
| `commercial_plans.py` | Valores: `9900` → `36000`; TypedDict docstring: "centavos" → "pesos" | Baja |
| `preview.py` | Docstrings LineItem/PreviewResult: "centavos" → "pesos"; valores no cambian (vienen de commercial_plans) | Baja |
| `commercial_views.py` L465, L691 | **Eliminar** `/ 100.0` en ambas líneas | Baja |
| `models.py` Module | `help_text="Price in cents"` → `"Price in ARS pesos"` | Baja |
| `models.py` Bundle | `help_text="Override price in cents"` → `"Override price in ARS pesos"` | Baja |
| `models.py` PendingSubscriptionChange | `help_text="Total amount in centavos"` → `"Total amount in ARS pesos"` | Baja |
| `seed_billing.py` | Bundle prices: `9900` → `36000`; Plan.price: `Decimal('99.00')` → `Decimal('36000.00')` | Baja |
| `plan-comparison.tsx` | Eliminar `formatPrice(cents)` local; usar import de `lib/pricing/format` | Baja |
| `plan-change-dialog.tsx` | Idem | Baja |
| `billing-page-client.tsx` | Idem + API ahora devuelve pesos, no centavos | Baja |
| `addon-purchase-dialog.tsx` | Idem | Baja |
| `services/pricing.py` | `calculate_quote()` devuelve pesos en vez de centavos | Baja |
| `services/limits.py` | `calculate_branches_cost()` devuelve pesos | Baja |
| Tests existentes | Actualizar valores esperados | Baja |

### DB migration

**No requiere Django migration SQL** para los IntegerField. El cambio es de valores (datos) y help_text. Los IntegerField siguen siendo IntegerField — solo cambia qué representan. El `help_text` se actualiza en una migration trivial (AlterField).

Para `Plan.price` tampoco hay migration SQL — el DecimalField(10,2) soporta hasta 99.999.999,99 — sobra.

**El seed se re-ejecuta** post-deploy para actualizar valores en DB.

### Riesgo de migración

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Olvidar quitar `/100.0` en commercial_views | Baja | **Crítico** — MP cobraría 1/100 del precio | Test E2E: verificar unit_price de preference |
| Olvidar actualizar valores en un archivo | Baja | Medio — precios inconsistentes | Test de paridad: canónico vs commercial_plans vs seed |
| Frontend recibe pesos pero sigue dividiendo por 100 | Baja | Alto — precios se muestran 100× menores | Test visual en staging |
| Suscripciones activas con price_snapshot antiguo | — | Nulo | price_snapshot se preserva; solo afecta nuevos checkouts |

**Nota crítica:** Las suscripciones existentes en MercadoPago siguen cobrando lo que se configuró en su momento. No se alteran. Los preapproval plans ya creados tienen su transaction_amount fijo. Solo nuevos checkouts usarán los precios actualizados.

---

## 9. Criterios de Aceptación de la Decisión

### Tests que deben pasar ANTES de mergear

```
1. Invariante canónico:
   ✅ Todos los precios en lib/pricing/ son enteros positivos en pesos ARS
   ✅ Anual == mensual × 12 × 0.8 para todos los planes no-custom
   ✅ formatPesosARS(36000) === '$36.000'

2. Paridad backend:
   ✅ commercial_plans.PLANS[x].pricing.monthly == canonical('gestion_comercial', x).monthly
   ✅ Plan.objects.get(code='gestion_start').price == Decimal('36000.00')
   ✅ Bundle.objects.get(code='gestion_start').fixed_price_monthly == 36000

3. MercadoPago:
   ✅ CommercialCheckoutView genera preference con unit_price == 36000.0 para Starter
   ✅ checkout_session genera preapproval con transaction_amount == 36000.0
   ✅ NO existe ninguna línea `/ 100.0` ni `/ 100` en commercial_views.py
   ✅ NO existe ninguna línea `* 100` en canonical_pricing.py ni commercial_plans.py

4. Frontend:
   ✅ NO existe ninguna función formatPrice(cents) que divida por 100
   ✅ formatARS / formatPesosARS es la única función de formato monetario
   ✅ Landing GC muestra $36.000 / $50.000 / $75.000
   ✅ billing-page-client muestra los mismos precios que la landing

5. Ausencia de centavos:
   ✅ grep -r "centavos" en billing/ devuelve 0 resultados (fuera de comentarios históricos)
   ✅ grep -r "in cents" en models.py devuelve 0 resultados
   ✅ Ningún help_text dice "cents" ni "centavos"
```

### Checklist deploy

- [ ] pricing.json generado y committeado
- [ ] canonical_pricing.py lee correctamente
- [ ] Tests TypeScript de invariantes pasan
- [ ] Tests Python de paridad pasan
- [ ] Staging: landing GC muestra precios correctos
- [ ] Staging: checkout genera preference con unit_price correcto
- [ ] Staging: preapproval tiene transaction_amount correcto
- [ ] Staging: billing dashboard muestra precios consistentes
- [ ] Producción: seed_billing re-ejecutado
- [ ] Producción: suscripciones existentes verificadas (sin alteración)
