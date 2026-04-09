# Modal de Ayuda / Onboarding Interno — Diseño Funcional

> **Estado:** Propuesta de diseño — no implementado  
> **Fecha:** 2026-04-15  
> **Scope:** Gestión Comercial · Carta Online / Menú QR · QR de Reseñas  
> **Exclusión explícita:** Restaurante Inteligente (servicio `restaurante`)

---

## 1. Principio rector

**Un solo componente** `<HelpModal />` con 3 tabs, reutilizable en toda la app.  
Se alimenta de un **modelo de datos declarativo** — nunca JSX hardcodeado.  
El contenido se filtra en runtime por `session.current.service` + `session.features`.

---

## 2. Arquitectura del modal

### 2.1 Componente raíz

```
<HelpModal />
├── Tab "Configuración inicial"   → <SetupChecklist />
├── Tab "Cómo usar"               → <HowToUseGuide />
└── Tab "Consejos y optimización"  → <TipsOptimization />
```

- Usa `<Dialog>` de `@/components/ui/modal.tsx` (portal-based, ya existente).
- Tabs con `<Tabs>` de shadcn/ui.
- Ancho fijo `max-w-2xl`, scroll interno por tab.

### 2.2 Puntos de invocación

| Trigger | Comportamiento |
|---------|---------------|
| **Primera entrada post-activación** | Auto-open en tab "Configuración inicial" |
| **Botón `?` en sidebar** | Open en último tab visitado (o tab 1 por defecto) |
| **Deep link (futuro)** | `<HelpModal defaultTab="tips" />` |

### 2.3 Detección de primera entrada

**Estado actual:** `business.status` solo controla `onboarding → trialing → active`.  
Una vez que el usuario termina el checkout, el status pasa a `trialing`/`active`  
y el layout nunca más redirige a `/app/onboarding`.

**No existe** un campo `setup_wizard_seen` o `first_login_tracked`.

**Propuesta — campo nuevo en backend:**

```python
# Business model — nuevo campo
setup_guide_dismissed_at = models.DateTimeField(null=True, blank=True)
```

**Lógica:**

```
IF business.status IN ('trialing', 'active')
   AND business.setup_guide_dismissed_at IS NULL
   → auto-open HelpModal en tab "Configuración inicial"
```

**Alternativa sin migración (MVP):**

Usar `localStorage` key `mirubro:help_dismissed:{business_id}`.  
Desventaja: se pierde al cambiar dispositivo/browser.

**Recomendación:** Implementar el campo backend para robustez. Es una migración AddField trivial y futuriza el tracking de setup completion.

---

## 3. Modelo de datos — Schema declarativo

### 3.1 Tipos TypeScript

```typescript
// types/help-modal.ts

type StepStatus = 'pending' | 'in_progress' | 'completed';

type ServiceSlug = 'gestion' | 'menu_qr' | 'qr_reviews';

type SetupStep = {
  /** ID único del paso — e.g. 'gestion.create_first_product' */
  id: string;
  /** Servicio al que pertenece */
  service: ServiceSlug;
  /** Título corto visible en el checklist */
  title: string;
  /** Descripción de una línea */
  description: string;
  /** Ruta de la app a la que lleva el CTA */
  href: string;
  /** Texto del botón CTA */
  ctaLabel: string;
  /** Feature flag requerido para mostrar este paso (session.features[key]) */
  featureGate?: string;
  /** Entitlement requerido (useEntitlements().hasEntitlement(code)) */
  entitlementGate?: string;
  /** Orden dentro de su servicio */
  order: number;
  /** Cómo detectar si ya está completado — ver §3.3 */
  completionCheck: CompletionCheck;
};

type CompletionCheck =
  | { type: 'api'; endpoint: string; field: string }
  | { type: 'count'; endpoint: string; minCount: number }
  | { type: 'boolean'; endpoint: string; field: string }
  | { type: 'manual' };

type HowToStep = {
  id: string;
  service: ServiceSlug;
  title: string;
  description: string;
  /** Opcional — link a sección de la app */
  href?: string;
  featureGate?: string;
  order: number;
};

type Tip = {
  id: string;
  service: ServiceSlug;
  title: string;
  description: string;
  /** Plan mínimo — 'starter' | 'pro' | 'business' (gestion) o 'lite' | 'pro' | 'premium' (menu_qr) */
  minPlan?: string;
  featureGate?: string;
  /** CTA upgrade si el usuario no tiene el plan */
  upgradeHref?: string;
  order: number;
};
```

### 3.2 Resolución de estado (StepStatus)

El status **no se hardcodea** en el catálogo — se computa en runtime:

```typescript
async function resolveStepStatus(step: SetupStep): Promise<StepStatus> {
  const check = step.completionCheck;

  switch (check.type) {
    case 'count': {
      // GET endpoint → if array.length >= minCount → 'completed'
      const data = await fetchApi(check.endpoint);
      const count = Array.isArray(data) ? data.length : (data?.count ?? 0);
      return count >= check.minCount ? 'completed' : 'pending';
    }
    case 'boolean': {
      // GET endpoint → if data[field] === true → 'completed'
      const data = await fetchApi(check.endpoint);
      return data?.[check.field] === true ? 'completed' : 'pending';
    }
    case 'api': {
      // GET endpoint → if data[field] exists and is truthy → 'completed'
      const data = await fetchApi(check.endpoint);
      return data?.[check.field] ? 'completed' : 'pending';
    }
    case 'manual':
      // Se marca manualmente (localStorage o backend flag)
      return getManualStepStatus(step.id);
  }
}
```

**Nota:** Estos checks se ejecutan una sola vez al abrir el modal (no polling).  
Se cachean con React Query (`staleTime: 30s`) para evitar refetch en cambio de tab.

### 3.3 CompletionCheck por paso

El `completionCheck` mapea cada paso a un endpoint existente de la API:

| Paso | type | endpoint | field/minCount |
|------|------|----------|---------------|
| Crear primer producto | `count` | `/api/v1/products/` | `minCount: 1` |
| Configurar negocio | `boolean` | `/api/v1/businesses/current/` | `phone` (truthy) |
| Registrar primera venta | `count` | `/api/v1/sales/` | `minCount: 1` |
| Configurar stock | `count` | `/api/v1/stock/movements/` | `minCount: 1` |
| Crear categoría de menú | `count` | `/api/v1/menu/categories/` | `minCount: 1` |
| Subir logo/branding | `api` | `/api/v1/menu/settings/` | `logo_url` |
| Generar QR | `boolean` | `/api/v1/menu/qr/` | `generated` |
| Conectar Google Reviews | `boolean` | `/api/v1/reviews/settings/` | `google_place_id` |

---

## 4. Catálogo de contenido por servicio

### 4.1 Tab "Configuración inicial" — Checklist

#### Gestión Comercial

| # | Paso | href | Feature Gate | Entitlement Gate | Plan mínimo |
|---|------|------|-------------|-----------------|-------------|
| 1 | Completar datos del negocio | `/app/gestion/configuracion/negocio` | — | — | starter |
| 2 | Crear tu primer producto | `/app/gestion/productos` | `products` | `gestion.products` | starter |
| 3 | Registrar tu primera venta | `/app/gestion/ventas` | `sales` | `gestion.sales_basic` | starter |
| 4 | Configurar tu stock inicial | `/app/gestion/stock` | `inventory` | `gestion.inventory_basic` | starter |
| 5 | Cargar tu primer cliente | `/app/gestion/clientes` | `customers` | `gestion.customers` | pro |
| 6 | Configurar caja | `/app/operacion/caja` | `cash` | `gestion.cash` | pro |
| 7 | Emitir tu primera factura | `/app/gestion/facturas` | `invoices` | `gestion.invoices` | pro |
| 8 | Configurar tesorería | `/app/gestion/finanzas` | `treasury` | `gestion.treasury` | pro |
| 9 | Invitar a un colaborador | `/app/settings/access` | `rbac_full` | `gestion.rbac_full` | pro |

> Pasos 5-9 se muestran solo si el usuario tiene el plan PRO+.  
> Si no tiene el feature, el paso se renderiza con badge "PRO" + CTA "Mejorar plan".

#### Carta Online / Menú QR

| # | Paso | href | Feature Gate | Plan mínimo |
|---|------|------|-------------|-------------|
| 1 | Crear tu primera categoría | `/app/menu` | `menu_builder` | lite |
| 2 | Agregar productos al menú | `/app/menu` | `menu_builder` | lite |
| 3 | Personalizar branding | `/app/menu/branding` | `menu_branding` | lite |
| 4 | Generar tu código QR | `/app/menu/qr` | `menu_qr_tools` | lite |
| 5 | Subir fotos de productos | `/app/menu` | `menu_item_images` | pro |
| 6 | Activar reseñas de Google | `/app/menu` (config) | `menu_qr_reviews` | pro (módulo) |
| 7 | Activar propinas | `/app/menu` (config) | `menu_qr_tips` | pro (módulo) |
| 8 | Conectar dominio personalizado | `/app/menu/branding` | `menu_custom_domain` | premium |

#### QR de Reseñas

| # | Paso | href | Feature Gate | Entitlement Gate |
|---|------|------|-------------|-----------------|
| 1 | Conectar tu ficha de Google | `/app/resenas/configuracion` | — | `qr_reviews.config` |
| 2 | Personalizar tu QR | `/app/resenas/qr` | — | `qr_reviews.qr` |
| 3 | Compartir con clientes | `/app/resenas/qr` | — | `qr_reviews.qr` |
| 4 | Revisar primer feedback | `/app/resenas/feedback` | — | `qr_reviews.dashboard` |

### 4.2 Tab "Cómo usar"

Contenido estático, filtrado por servicio activo. Formato: lista de cards con título + descripción + link opcional.

#### Gestión Comercial

| # | Título | Descripción |
|---|--------|-------------|
| 1 | Productos y categorías | Cargá productos, organizalos por categoría y definí precios. |
| 2 | Registrar ventas | Creá ventas desde el panel o usá la caja para operación rápida. |
| 3 | Control de stock | Registrá movimientos, recibí alertas de stock bajo y exportá. |
| 4 | Gestión de clientes | Asociá ventas a clientes y llevá un historial de compras. |
| 5 | Facturación electrónica | Emití facturas vinculadas a ventas. Requiere datos fiscales. |
| 6 | Finanzas y tesorería | Registrá ingresos, egresos y controlá saldos por cuenta. |
| 7 | Reportes | Consultá métricas de venta, stock y finanzas desde Reportes. |

#### Carta Online / Menú QR

| # | Título | Descripción |
|---|--------|-------------|
| 1 | Tu carta digital | Los clientes escanean el QR y ven tu menú en el celular. |
| 2 | Branding | Personalizá colores, logo y tipografía de tu carta online. |
| 3 | Reseñas y propinas | Activá Google Reviews y propinas con Mercado Pago. |
| 4 | Compartir el QR | Descargá o imprimí tu QR desde la sección "QR y enlaces". |

#### QR de Reseñas

| # | Título | Descripción |
|---|--------|-------------|
| 1 | Filtrado automático | Las buenas reseñas van a Google. Las malas quedan como feedback privado. |
| 2 | Tu QR personal | Imprimí el QR y ponelo en el mostrador, mesa o recibo. |
| 3 | Dashboard de feedback | Revisá opiniones privadas y hacé seguimiento. |

### 4.3 Tab "Consejos y optimización"

Tips contextuales, algunos gated por plan para funcionar como upgrade nudge.

#### Gestión Comercial

| # | Tip | Plan mínimo | CTA upgrade |
|---|-----|-------------|-------------|
| 1 | Usá categorías para organizar productos — mejora la búsqueda. | starter | — |
| 2 | Configurá alertas de stock bajo para no quedarte sin mercadería. | starter | — |
| 3 | Asociá ventas a clientes para tener historial de compras. | pro | Mejorar a PRO |
| 4 | Exportá reportes en CSV para tu contador. | pro | Mejorar a PRO |
| 5 | Usá presupuestos para enviar cotizaciones a clientes. | pro | Mejorar a PRO |
| 6 | Abrí sucursales para gestionar múltiples locales desde un panel. | business | Mejorar a BUSINESS |

#### Carta Online / Menú QR

| # | Tip | Plan mínimo | CTA upgrade |
|---|-----|-------------|-------------|
| 1 | Agregá fotos a tus productos — las cartas con fotos tienen 40% más engagement. | pro | Mejorar a PRO |
| 2 | Activá las propinas con Mercado Pago para tus mozos. | pro (módulo) | Activar módulo |
| 3 | Conectá tu dominio personalizado para una URL de marca. | premium | Mejorar a PREMIUM |

#### QR de Reseñas

| # | Tip | CTA |
|---|-----|-----|
| 1 | Poné el QR en la mesa y en el ticket — duplicás la tasa de feedback. | — |
| 2 | Respondé las reseñas negativas desde el dashboard de feedback. | — |

---

## 5. Matriz producto × plan × features

### 5.1 Gestión Comercial

| Feature Key (backend) | Entitlement (frontend) | starter | pro | business |
|-----------------------|----------------------|---------|-----|----------|
| `products` | `gestion.products` | ✅ | ✅ | ✅ |
| `inventory` / `stock` | `gestion.inventory_basic` | ✅ | ✅ | ✅ |
| — | `gestion.inventory_advanced` | ❌ | ✅ | ✅ |
| `sales` | `gestion.sales_basic` | ✅ | ✅ | ✅ |
| — | `gestion.sales_advanced` | ❌ | ✅ | ✅ |
| `orders` | `gestion.orders` | ✅ | ✅ | ✅ |
| `customers` | `gestion.customers` | ❌ | ✅ | ✅ |
| `cash` | `gestion.cash` | ❌ | ✅ | ✅ |
| `quotes` | `gestion.quotes` | ❌ | ✅ | ✅ |
| `invoices` | `gestion.invoices` | ❌ | ✅ | ✅ |
| `treasury` | `gestion.treasury` | ❌ | ✅ | ✅ |
| `reports` | `gestion.reports` | ❌ | ✅ | ✅ |
| — | `gestion.export` | ❌ | ✅ | ✅ |
| — | `gestion.rbac_full` | ❌ | ✅ | ✅ |
| — | `gestion.audit` | ❌ | ✅ | ✅ |
| — | `gestion.dashboard_finance` | ❌ | ✅ | ✅ |
| `multi_branch` | `gestion.multi_branch` | ❌ | ❌¹ | ✅ |
| — | `gestion.transfers` | ❌ | ❌ | ✅ |
| — | `gestion.consolidated_reports` | ❌ | ❌ | ✅ |
| — | `gestion.tax_backup` | ❌ | ❌ | ✅ |

> ¹ PRO puede acceder a `multi_branch` si tiene addon de sucursales extras (`effective_max_branches > 1`).

### 5.2 Carta Online / Menú QR

| Feature Key | lite | pro | premium |
|-------------|------|-----|---------|
| `menu_builder` | ✅ | ✅ | ✅ |
| `menu_branding` | ✅ | ✅ | ✅ |
| `public_menu` | ✅ | ✅ | ✅ |
| `menu_qr_tools` | ✅ | ✅ | ✅ |
| `menu_item_images` | ❌ | ✅ | ✅ |
| `menu_qr_reviews` | ❌ | Módulo² | ✅ |
| `menu_qr_tips` | ❌ | Módulo² | ✅ |
| `menu_qr_tips_pro` | ❌ | ❌ | ✅ |
| `menu_custom_domain` | ❌ | ❌ | ✅ |
| `multi_branch` | ❌ | ❌ | ✅ |

> ² PRO incluye 1 módulo (reviews O tips). El otro se puede agregar como add-on.

### 5.3 QR de Reseñas

| Entitlement | qr_reviews |
|-------------|-----------|
| `qr_reviews.config` | ✅ |
| `qr_reviews.qr` | ✅ |
| `qr_reviews.dashboard` | ✅ |

> Producto de un solo tier — no tiene feature gating interno.

---

## 6. Integración con el sistema existente

### 6.1 Gating — Reutilizar lo existente

```
┌────────────────────┐     ┌──────────────────────┐
│  getSession()      │────▶│  session.features     │──▶ featureGate
│  (server component)│     │  session.services     │──▶ service filter
│                    │     │  session.subscription  │──▶ plan detection
└────────────────────┘     └──────────────────────┘

┌────────────────────┐
│  useEntitlements() │────▶ hasEntitlement(code)   ──▶ entitlementGate
│  (client hook)     │────▶ plan                   ──▶ upgrade CTA logic
└────────────────────┘
```

**No se crea** un nuevo sistema de gating. Se reutilizan:
- `session.features[key]` para feature flags (fast, always available)
- `useEntitlements().hasEntitlement(code)` para entitlements (React Query cached)
- `session.current.service` para filtrar por servicio activo

### 6.2 Filtrado en runtime

```typescript
function getVisibleSteps(
  steps: SetupStep[],
  service: ServiceSlug,
  features: FeatureFlags,
  hasEntitlement: (code: string) => boolean,
): (SetupStep & { locked: boolean })[] {
  return steps
    .filter(s => s.service === service)
    .sort((a, b) => a.order - b.order)
    .map(step => {
      const featureOk = !step.featureGate || features[step.featureGate] === true;
      const entitlementOk = !step.entitlementGate || hasEntitlement(step.entitlementGate);
      return { ...step, locked: !featureOk || !entitlementOk };
    });
}
```

- Pasos **locked** se muestran con opacidad reducida + badge del plan requerido + CTA "Mejorar plan" → `/app/servicios`.  
- Pasos **unlocked** muestran status (pending/completed) + CTA primario.

### 6.3 Punto de montaje

El `<HelpModal />` se monta en `<AppShell>` (layout autenticado).  
El botón `?` se agrega al sidebar, debajo de la navegación principal.

```
AppShell
├── Sidebar
│   ├── NAV_CONFIG[service] items
│   ├── ─────────── separator
│   └── HelpButton (?) ← trigger
├── Main content
└── HelpModal (portal, conditionally rendered)
```

---

## 7. Flujo de auto-apertura (primera entrada)

```
┌─ App layout.tsx ─────────────────────────────────┐
│                                                   │
│  session = await getSession()                     │
│                                                   │
│  IF status = 'onboarding' → redirect /onboarding  │
│  IF !access_allowed → redirect /planes             │
│                                                   │
│  ✅ access_allowed = true                          │
│  → render <AppShell session={session}>             │
│                                                   │
└───────────────────────────────────────────────────┘
                    │
                    ▼
┌─ AppShell ──────────────────────────────────────┐
│                                                  │
│  IF session.current.business.setup_guide_seen    │
│     = false (from /api/v1/auth/me/ response)     │
│  → auto-open <HelpModal defaultTab="setup" />    │
│                                                  │
│  User can dismiss → PATCH /businesses/current/   │
│    { setup_guide_dismissed_at: now() }           │
│                                                  │
└──────────────────────────────────────────────────┘
```

### Timeline:

1. Usuario completa checkout → `business.status` = `trialing`
2. Redirige a entry route del servicio (e.g. `/app/gestion/dashboard`)
3. `AppShell` detecta `setup_guide_dismissed_at == null` → auto-open modal
4. Usuario explora el checklist, hace click en pasos → navega a las secciones
5. Usuario cierra el modal → `PATCH` marca `setup_guide_dismissed_at`
6. En visitas futuras, el modal no se abre automáticamente
7. El botón `?` en el sidebar está siempre disponible para abrir manualmente

---

## 8. Estructura de archivos propuesta

```
apps/web/src/features/help/
├── types.ts                      # SetupStep, HowToStep, Tip, CompletionCheck
├── data/
│   ├── gestion-setup.ts          # Checklist steps para Gestión Comercial
│   ├── menu-qr-setup.ts          # Checklist steps para Menú QR
│   ├── qr-reviews-setup.ts       # Checklist steps para QR de Reseñas
│   ├── how-to-use.ts             # Contenido "Cómo usar" por servicio
│   └── tips.ts                   # Contenido "Consejos" por servicio
├── hooks/
│   ├── use-setup-status.ts       # React Query hook: computa status de cada paso
│   ├── use-help-modal.ts         # State management del modal (open/close/tab)
│   └── use-first-entry.ts        # Lógica de auto-apertura primera entrada
├── components/
│   ├── help-modal.tsx            # Componente raíz (Dialog + Tabs)
│   ├── setup-checklist.tsx       # Tab 1: renderiza pasos con status
│   ├── how-to-guide.tsx          # Tab 2: lista de cards
│   ├── tips-optimization.tsx     # Tab 3: tips con upgrade nudges
│   ├── setup-step-card.tsx       # Card individual de un paso del checklist
│   └── help-trigger.tsx          # Botón (?) para el sidebar
└── lib/
    └── completion-resolver.ts    # resolveStepStatus() — fetch + compute
```

---

## 9. API: cambios backend necesarios

### 9.1 Campo nuevo en Business

```python
# apps/business/models.py
setup_guide_dismissed_at = models.DateTimeField(null=True, blank=True)
```

Migración: `AddField`, non-destructive, null=True.

### 9.2 Endpoint /auth/me/ — nuevo campo en response

Agregar `setup_guide_dismissed_at` al serializador de sesión.  
El frontend lo consume como `session.current.business.setup_guide_dismissed_at`.

### 9.3 PATCH /businesses/current/ — dismiss

Endpoint existente. Solo necesita aceptar `setup_guide_dismissed_at` en el serializador.

### 9.4 Endpoint nuevo (opcional, futuro): GET /api/v1/help/setup-status/

Para centralizar la resolución de status del checklist en el backend  
en lugar de hacer N llamadas individuales. Esto es una optimización  
que puede implementarse después del MVP.

```json
{
  "steps": {
    "gestion.create_first_product": "completed",
    "gestion.configure_business": "completed",
    "gestion.first_sale": "pending",
    "gestion.setup_stock": "pending"
  }
}
```

---

## 10. Progresión de implementación sugerida

| Fase | Alcance | Complejidad |
|------|---------|-------------|
| **MVP** | Modal con tabs, checklist estático (sin completion checks), primera entrada con localStorage | Baja |
| **V1** | Completion checks via API, campo backend `setup_guide_dismissed_at`, badge de progreso en sidebar | Media |
| **V2** | Endpoint consolidado `/help/setup-status/`, analytics de conversión, A/B test de tips | Media-Alta |

---

## 11. Decisiones de diseño

| Decisión | Elegida | Alternativa descartada | Motivo |
|----------|---------|----------------------|--------|
| 1 modal vs 2 (onboarding + help) | **1 modal** | 2 separados | Menos código, UX consistente, único source of truth |
| Feature gating | Reusar `session.features` + `useEntitlements()` | Sistema propio | Ya implementado y testeado |
| Contenido | Catálogo declarativo (TS objects) | MDX / CMS | No necesitamos formatting rico; TS da type-safety |
| Completion check | Frontend fetch on-demand | Backend pre-computed | Menor acoplamiento en MVP; backend endpoint como V2 |
| Primera entrada | Backend field (`setup_guide_dismissed_at`) | localStorage | Persiste cross-device; single source of truth |
| UI base | `Dialog` existente + `Tabs` shadcn | Sheet/Drawer | Dialog es estándar para modales informativos |
| Scope inicial | Solo servicios activos del usuario | Todos los servicios | Evita confusión; el usuario solo ve lo relevante |

---

## 12. Ejemplo: catálogo Gestión Comercial starter

```typescript
// data/gestion-setup.ts
export const GESTION_SETUP_STEPS: SetupStep[] = [
  {
    id: 'gestion.configure_business',
    service: 'gestion',
    title: 'Completar datos del negocio',
    description: 'Nombre, dirección, logo y datos fiscales de tu comercio.',
    href: '/app/gestion/configuracion/negocio',
    ctaLabel: 'Ir a configuración',
    order: 1,
    completionCheck: {
      type: 'api',
      endpoint: '/api/v1/businesses/current/',
      field: 'phone',
    },
  },
  {
    id: 'gestion.create_first_product',
    service: 'gestion',
    title: 'Crear tu primer producto',
    description: 'Cargá un producto con nombre, precio y categoría.',
    href: '/app/gestion/productos',
    ctaLabel: 'Crear producto',
    featureGate: 'products',
    entitlementGate: 'gestion.products',
    order: 2,
    completionCheck: {
      type: 'count',
      endpoint: '/api/v1/products/',
      minCount: 1,
    },
  },
  {
    id: 'gestion.first_sale',
    service: 'gestion',
    title: 'Registrar tu primera venta',
    description: 'Creá una venta manual desde el panel de ventas.',
    href: '/app/gestion/ventas',
    ctaLabel: 'Registrar venta',
    featureGate: 'sales',
    entitlementGate: 'gestion.sales_basic',
    order: 3,
    completionCheck: {
      type: 'count',
      endpoint: '/api/v1/sales/',
      minCount: 1,
    },
  },
  {
    id: 'gestion.setup_stock',
    service: 'gestion',
    title: 'Configurar tu stock inicial',
    description: 'Registrá el stock inicial de tus productos.',
    href: '/app/gestion/stock',
    ctaLabel: 'Ir a stock',
    featureGate: 'inventory',
    entitlementGate: 'gestion.inventory_basic',
    order: 4,
    completionCheck: {
      type: 'count',
      endpoint: '/api/v1/stock/movements/',
      minCount: 1,
    },
  },
  // PRO+ steps (shown locked for starter users)
  {
    id: 'gestion.first_customer',
    service: 'gestion',
    title: 'Cargar tu primer cliente',
    description: 'Creá un cliente para asociar ventas y llevar historial.',
    href: '/app/gestion/clientes',
    ctaLabel: 'Crear cliente',
    featureGate: 'customers',
    entitlementGate: 'gestion.customers',
    order: 5,
    completionCheck: {
      type: 'count',
      endpoint: '/api/v1/customers/',
      minCount: 1,
    },
  },
  {
    id: 'gestion.setup_cash',
    service: 'gestion',
    title: 'Configurar caja',
    description: 'Abrí tu primera caja para registrar cobros y pagos.',
    href: '/app/operacion/caja',
    ctaLabel: 'Ir a caja',
    featureGate: 'cash',
    entitlementGate: 'gestion.cash',
    order: 6,
    completionCheck: {
      type: 'count',
      endpoint: '/api/v1/cash/sessions/',
      minCount: 1,
    },
  },
];
```

---

## 13. Resumen visual

```
┌────────────────────────────────────────────────────────────┐
│  Ayuda — Gestión Comercial                          [✕]   │
│                                                            │
│  ┌──────────────────┐ ┌────────────┐ ┌─────────────────┐  │
│  │ Config. inicial ◉│ │ Cómo usar  │ │ Consejos        │  │
│  └──────────────────┘ └────────────┘ └─────────────────┘  │
│                                                            │
│  Tu progreso: 2/4 completados                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░░░                 │
│                                                            │
│  ✅ Completar datos del negocio                             │
│     Nombre, dirección, logo y datos fiscales.              │
│                                                            │
│  ✅ Crear tu primer producto                                │
│     Cargá un producto con nombre, precio y categoría.      │
│                                                            │
│  ○  Registrar tu primera venta          [Registrar venta]  │
│     Creá una venta manual desde el panel de ventas.        │
│                                                            │
│  ○  Configurar tu stock inicial              [Ir a stock]  │
│     Registrá el stock inicial de tus productos.            │
│                                                            │
│  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈  │
│  🔒 Cargar tu primer cliente              PRO ↗ Mejorar   │
│  🔒 Configurar caja                       PRO ↗ Mejorar   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```
