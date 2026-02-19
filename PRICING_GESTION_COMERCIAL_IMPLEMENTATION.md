# Implementación de Precios - Gestión Comercial

## Problema Identificado (Root Cause)

**Archivo:** `apps/web/src/features/billing/components/PlansBundles.tsx` (línea 25)  
**Mensaje:** "No hay packs disponibles para esta vertical"

**Causa raíz:**
- La página de pricing usaba `vertical='commercial'` para buscar bundles
- El endpoint `/api/v1/billing/bundles/?vertical=commercial` devolvía array vacío
- El seed original (`seed_billing.py`) solo tenía 2 bundles obsoletos: `comm_initial` y `comm_full`
- No existían los planes START, PRO y BUSINESS especificados

## Solución Implementada

### 1. Backend - Planes y Módulos

**Archivo modificado:** `services/api/src/apps/billing/management/commands/seed_billing.py`

**Módulos creados (19 total):**

#### Core (Plan START) - 5 módulos incluidos:
- `gestion_products` - Catálogo de productos
- `gestion_inventory_basic` - Inventario básico
- `gestion_sales_basic` - Ventas básicas
- `gestion_dashboard_basic` - Dashboard básico
- `gestion_settings_basic` - Configuración básica

#### Plan PRO - Agrega 10 módulos:
- `gestion_customers` - Clientes/CRM
- `gestion_cash` - Caja
- `gestion_quotes` - Presupuestos
- `gestion_reports` - Reportes
- `gestion_export` - Exportación
- `gestion_treasury` - **Tesorería y Finanzas** ✨
- `gestion_inventory_advanced` - Inventario avanzado
- `gestion_sales_advanced` - Ventas avanzadas
- `gestion_rbac_full` - Control de acceso completo
- `gestion_audit` - Auditoría

#### Plan BUSINESS - Agrega 4 módulos:
- `gestion_invoices` - **Facturación Electrónica** (incluida) ✨
- `gestion_multi_branch` - Multi-sucursal
- `gestion_transfers` - Transferencias entre sucursales
- `gestion_consolidated_reports` - Reportes consolidados

**Bundles creados:**

```python
# START - $99/mes - $950.40/año (20% off)
Bundle(code='gestion_start', name='Start')
- 1 sucursal fija
- 5 módulos core
- Usuarios ilimitados

# PRO - $299/mes - $2,870.40/año (20% off) ⭐ RECOMENDADO
Bundle(code='gestion_pro', name='Pro')
- 1-3 sucursales (configurables)
- 15 módulos (core + PRO)
- Addon: Facturación opcional (+$150/mes)
- Usuarios ilimitados

# BUSINESS - $499/mes - $4,790.40/año (20% off)  
Bundle(code='gestion_business', name='Business')
- 1-5 sucursales incluidas + ilimitadas extra
- 19 módulos (todos)
- Facturación INCLUIDA
- Usuarios ilimitados
```

**Comando ejecutado:**
```bash
docker compose exec api python manage.py seed_billing
# ✅ Successfully seeded billing data
```

### 2. Frontend - Packs Recomendados

**Archivo modificado:** `apps/web/src/features/billing/components/PlansBundles.tsx`

**Mejoras implementadas:**
- ✅ Cards rediseñadas con mejor jerarquía visual
- ✅ Plan PRO destacado con `scale-105` y ring
- ✅ Información de sucursales/usuarios por plan
- ✅ Highlights específicos:
  - START: "Ideal para empezar"
  - PRO: "Incluye Tesorería" 
  - BUSINESS: "Facturación incluida"
- ✅ Badge de "Recomendado" en PRO
- ✅ Precios con descuento anual (20% off)
- ✅ Muestra solo los 6 módulos más relevantes por plan

**Funciones helper agregadas:**
- `getPlanFeatures()` - Características específicas por plan
- `getKeyModules()` - Prioriza módulos importantes para UI

### 3. Frontend - Armá Tu Plan

**Archivo nuevo:** `apps/web/src/features/billing/components/CommercialPlanBuilder.tsx`

**Características implementadas:**

#### Paso 1: Selección de Plan Base
- Grid de 3 cards (START/PRO/BUSINESS)
- Muestra precio base según periodo (mensual/anual)
- Badges visuales
- Selección reactiva

#### Paso 2: Configuración de Sucursales
- **START:** 1 sucursal fija (controles deshabilitados)
- **PRO:** Selector 1-3 sucursales
  - 1 incluida + hasta 2 extras ($50/mes cada una)
- **BUSINESS:** Selector 1-20 sucursales
  - 5 incluidas + extras ilimitadas ($50/mes cada una)
- Controles +/- con límites automáticos
- Cálculo de precio en tiempo real

#### Paso 3: Add-ons Opcionales
- **PRO:** Toggle "Facturación Electrónica" (+$150/mes)
  - Checkbox con precio visible
  - Confirmación visual cuando se agrega
- **BUSINESS:** Muestra "Facturación Incluida" (no editable)
  - Badge verde destacado
  
#### Resumen y Confirmación
- Precio total calculado dinámicamente
- Desglose visible de extras
- Descuento anual automático (20%)
- Botón CTA grande "Confirmar Plan"
- Notas: usuarios ilimitados, cancelación flexible, soporte incluido

**Integración con página principal:**
```tsx
// pricing/page.tsx - usa CommercialPlanBuilder solo para vertical='commercial'
{vertical === 'commercial' ? (
  <CommercialPlanBuilder ... />
) : (
  <PlansBuilderWizard ... /> // Otros verticales
)}
```

### 4. Precios Configurados

| Plan | Mensual | Anual (20% off) | Sucursales | Facturación |
|------|---------|-----------------|------------|-------------|
| **START** | $99 | $950.40 | 1 fija | ❌ No disponible |
| **PRO** ⭐ | $299 | $2,870.40 | 1-3 | ➕ Add-on $150/mes |
| **BUSINESS** | $499 | $4,790.40 | 5 incluidas + extras | ✅ Incluida |

**Add-ons:**
- Sucursal extra: $50/mes - $480/año
- Facturación (solo PRO): $150/mes - $1,440/año

### 5. Validación de Cumplimiento (QA)

✅ **Al ir a Precios → Gestión Comercial:**
- NO se muestra "No hay packs disponibles"
- Se ven 3 cards: Start, Pro ⭐, Business
- Plan Pro destacado visualmente

✅ **Toggle Mensual/Anual:**
- Funciona correctamente
- Muestra descuento 20% en modo anual
- Recalcula precios en tiempo real

✅ **Armá tu plan:**
- START: 1 sucursal bloqueada ✓
- PRO: Selector 1-3 sucursales ✓
- BUSINESS: Selector 1-5+ sucursales ✓
- Cálculo de extras funciona ✓

✅ **Tesorería/Finanzas:**
- Listado en módulos de plan PRO ✓
- Descripción: "Control financiero, gastos e ingresos" ✓

✅ **Facturación:**
- PRO: Aparece como addon opcional (+$150) ✓
- BUSINESS: Aparece como "Incluida" con badge verde ✓

## Archivos Modificados/Creados

### Backend
- ✏️ `services/api/src/apps/billing/management/commands/seed_billing.py` (líneas 9-128)

### Frontend
- ✏️ `apps/web/src/features/billing/components/PlansBundles.tsx` (líneas 16-117)
- ➕ `apps/web/src/features/billing/components/CommercialPlanBuilder.tsx` (nuevo, 385 líneas)
- ✏️ `apps/web/src/app/(marketing)/pricing/page.tsx` (líneas 1-6, 80-95, 150-165)

## Estado de Servicios

```bash
docker compose ps
```

✅ mirubro-api (puerto 8000) - Running  
✅ mirubro-web (puerto 3000) - Running  
✅ mirubro-postgres (puerto 5432) - Running  
✅ mirubro-redis (puerto 6379) - Running

**Logs web:**
```
GET /pricing 200 in 99ms (compile: 47ms, render: 53ms) ✓
```

## Testing Manual

### Packs Recomendados
1. Navegar a http://localhost:3000/pricing
2. Seleccionar "Gestión Comercial"
3. Verificar que aparecen 3 planes
4. Toggle Mensual/Anual funciona

### Armá Tu Plan
1. Click en tab "Armá tu plan"
2. Seleccionar PRO
3. Aumentar sucursales a 3
4. Activar addon "Facturación"
5. Ver precio actualizado: $299 + $100 (2 sucursales extra) + $150 (facturación) = $549/mes
6. Cambiar a BUSINESS
7. Ver que facturación aparece como "Incluida"

## Próximos Pasos (Opcional)

1. **Agregar Enterprise:** Si se requiere un plan Enterprise personalizable
2. **Backend de checkout:** Implementar flujo `/subscribe` completo
3. **Migraciones:** Crear migration para persistir Plan/Price en DB si se requiere
4. **Tests automatizados:** E2E tests con Playwright/Cypress
5. **Analytics:** Tracking de conversión por plan

## Notas Técnicas

- Los precios están en centavos (stored as integers): 9900 = $99.00
- Los bundles tienen `is_active=True` por defecto
- Los módulos core (`is_core=True`) se pre-seleccionan automáticamente en el builder genérico
- El periodo de facturación afecta el precio con fórmula: `yearly = monthly * 12 * 0.8`
- La configuración de sucursales usa límites por plan definidos en `PLAN_LIMITS`
- El componente `CommercialPlanBuilder` es específico para Gestión Comercial
- Otros verticales (restaurant, menu_qr) siguen usando `PlansBuilderWizard` genérico
