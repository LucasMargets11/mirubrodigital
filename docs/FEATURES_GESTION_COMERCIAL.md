# Funcionalidades Gestión Comercial — Mapping de entitlements

> Fuente canónica: `apps/web/src/features/billing/data/gestion-comercial-catalog.ts`
> Sincronizado con: `services/api/src/apps/business/entitlements.py` y `services/api/src/apps/billing/commercial_plans.py`
> Última revisión: 2026-02-27

---

## Planes disponibles

| Plan | Precio mensual | Precio anual | Sucursales | Usuarios |
|------|----------------|--------------|------------|----------|
| **START** | $99/mes | $950/año | 1 | 2 |
| **PRO** | $299/mes | $2870/año | Hasta 3 (1 incluida + 2 extras) | 10 |
| **BUSINESS** | $499/mes | $4790/año | Ilimitadas (5 incluidas) | 20 base |
| **ENTERPRISE** | Custom | Custom | Ilimitadas | Ilimitados |

---

## Catálogo de entitlements

Leyenda:
- ✅ **Incluido** — incluido en el plan base
- ➕ **Add-on** — disponible como add-on de pago
- — **No incluido**
- ⭐ **Custom** — Enterprise: config personalizada / ilimitada

### Productos

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.products` | Gestión de productos | ✅ | ✅ | ✅ | ⭐ |

### Inventario

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.inventory_basic` | Inventario básico | ✅ | ✅ | ✅ | ⭐ |
| `gestion.inventory_advanced` | Inventario avanzado | — | ✅ | ✅ | ⭐ |

### Ventas

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.sales_basic` | Ventas básicas | ✅ | ✅ | ✅ | ⭐ |
| `gestion.sales_advanced` | Ventas avanzadas | — | ✅ | ✅ | ⭐ |
| `gestion.quotes` | Cotizaciones | — | ✅ | ✅ | ⭐ |

### Clientes

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.customers` | CRM / Gestión de clientes | ➕ | ✅ | ✅ | ⭐ |

### Facturación

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.invoices` | Facturación electrónica | ➕ | ✅ | ✅ | ⭐ |

### Caja

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.cash` | Caja / Sesiones de caja | — | ✅ | ✅ | ⭐ |

### Reportes

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.dashboard_basic` | Dashboard básico | ✅ | ✅ | ✅ | ⭐ |
| `gestion.reports` | Reportes avanzados | — | ✅ | ✅ | ⭐ |
| `gestion.consolidated_reports` | Reportes consolidados | — | — | ✅ | ⭐ |

### Exportación

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.export` | Exportación de datos | — | ✅ | ✅ | ⭐ |

### Tesorería

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.treasury` | Tesorería / Finanzas | — | ✅ | ✅ | ⭐ |

### Seguridad

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.settings_basic` | Configuración comercial básica | ✅ | ✅ | ✅ | ⭐ |
| `gestion.rbac_full` | Control de acceso por roles (RBAC) | — | ✅ | ✅ | ⭐ |

### Auditoría

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.audit` | Registro de auditoría | — | ✅ | ✅ | ⭐ |

### Multi-sucursal

| Entitlement | Título | START | PRO | BUSINESS | ENTERPRISE |
|-------------|--------|-------|-----|----------|------------|
| `gestion.multi_branch` | Gestión multi-sucursal | — | — | ✅ | ⭐ |
| `gestion.transfers` | Transferencias entre sucursales | — | — | ✅ | ⭐ |

---

## Add-ons disponibles (plan START)

| Add-on | Entitlement | Precio mensual | Precio anual | Incluido en |
|--------|-------------|----------------|--------------|-------------|
| CRM / Gestión de clientes | `gestion.customers` | $20/mes | $192/año | PRO, BUSINESS, ENTERPRISE |
| Facturación Electrónica | `gestion.invoices` | $150/mes | $1440/año | PRO, BUSINESS, ENTERPRISE |

---

## Extras (PRO y BUSINESS)

| Extra | Precio mensual | Precio anual |
|-------|----------------|--------------|
| Sucursal adicional | $50/mes | $480/año |
| Usuario adicional | $5/mes | $48/año |

---

## Mapeo de planes legacy

| Código legacy | Nombre | Equivale a |
|---------------|--------|------------|
| `starter` | Starter | **START** |
| `pro` | Pro | **PRO** |
| `plus` | Plus | **BUSINESS** |

---

## Notas de implementación

### Anti-drift
- El catálogo frontend (`gestion-comercial-catalog.ts`) lista explícitamente cada key de entitlement. Si el backend agrega una key nueva en `entitlements.py`, debe agregarse también en el catálogo.
- Se recomienda un test de paridad que verifique que las keys del catálogo frontend coincidan con las del backend.

### Fallback para keys desconocidas
Si en runtime aparece una key no listada en el catálogo, el sistema la muestra como:
- Título: la propia key (ej. `gestion.nueva_feature`)
- Descripción: "Funcionalidad disponible en este plan"

### Archivos involucrados

| Archivo | Rol |
|---------|-----|
| `apps/web/src/features/billing/data/gestion-comercial-catalog.ts` | Single source of truth frontend: keys, títulos, disponibilidad por plan |
| `apps/web/src/features/billing/components/GestionComercialComparisonTable.tsx` | Tabla comparativa (desktop + mobile) |
| `apps/web/src/app/(marketing)/pricing/page.tsx` | Página de precios — renderiza la tabla cuando `vertical === 'commercial'` |
| `services/api/src/apps/business/entitlements.py` | Backend: entitlements por plan |
| `services/api/src/apps/billing/commercial_plans.py` | Backend: precios, límites y descripción de planes |
