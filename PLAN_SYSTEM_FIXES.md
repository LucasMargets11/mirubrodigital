# Correcciones del Sistema de Planes - Resumen

## Fecha
Completado exitosamente

## Problema Inicial
Al intentar iniciar Docker después de implementar el sistema de planes de Gestión Comercial, surgieron múltiples errores de importación relacionados con mixins eliminados (`InvoicesFeatureMixin`, `ReportsFeatureMixin`).

## Errores Encontrados y Corregidos

### 1. InvoicesFeatureMixin en invoices/views.py
**Error:** `NameError: name 'InvoicesFeatureMixin' is not defined`

**Archivos afectados:**
- `services/api/src/apps/invoices/views.py`

**Corrección:**
- Línea 76: `InvoiceDetailView` - Eliminada herencia de `InvoicesFeatureMixin`, agregado `HasEntitlement` a `permission_classes` y `required_entitlement = 'gestion.invoices'`
- Línea 90: `InvoiceSeriesListView` - Misma corrección

### 2. InvoicesFeatureMixin en orders/views.py
**Error:** `ImportError: cannot import name 'InvoicesFeatureMixin' from 'apps.invoices.views'`

**Archivos afectados:**
- `services/api/src/apps/orders/views.py`

**Corrección:**
- Línea 17: Eliminada importación de `InvoicesFeatureMixin`, agregada `HasEntitlement` a imports
- Línea 406: `OrderInvoiceView` - Eliminada herencia de `InvoicesFeatureMixin`, agregado `HasEntitlement` y `required_entitlement = 'gestion.invoices'`

### 3. ReportsFeatureMixin en resto/reports/views.py
**Error:** Importación de `ReportsFeatureMixin` obsoleto

**Archivos afectados:**
- `services/api/src/apps/resto/reports/views.py`
- `services/api/src/apps/reports/views.py`

**Corrección:**
- Eliminada clase `RestaurantReportsFeatureMixin` que heredaba de `ReportsFeatureMixin`
- `RestaurantReportSummaryView`, `RestaurantReportProductsView`, `RestaurantReportCashSessionsView` - Eliminada herencia del mixin
- Eliminada clase `ReportsFeatureMixin` completa de `apps/reports/views.py` (líneas 273-288)

**Nota:** Las vistas de reportes de restaurante mantienen solo permisos RBAC (`HasPermission`), no requieren entitlements de Gestión Comercial ya que pertenecen al módulo separado de restaurante.

### 4. TopProductsReportView inexistente
**Error:** `ImportError: cannot import name 'TopProductsReportView'`

**Archivos afectados:**
- `services/api/src/apps/reports/urls.py`

**Corrección:**
- Eliminada importación de `TopProductsReportView` (no existe en codebase)
- Eliminada ruta `path('products/top/', TopProductsReportView.as_view())`

### 5. Conflicto de Migraciones
**Error:** `CommandError: Conflicting migrations detected; multiple leaf nodes in the migration graph`

**Problema:**
Las nuevas migraciones fueron creadas con números 0002 y 0003, pero ya existían migraciones con esos números en el historial.

**Corrección:**
- Renombrado: `0002_subscription_plans_addons.py` → `0011_subscription_plans_addons.py`
- Renombrado: `0003_migrate_legacy_plans.py` → `0012_migrate_legacy_plans.py`
- Actualizada dependencia en 0011: `('business', '0010_alter_businessbillingprofile_options_and_more')`
- Actualizada dependencia en 0012: `('business', '0011_subscription_plans_addons')`

## Migraciones Aplicadas Exitosamente

```
Running migrations:
  Applying business.0011_subscription_plans_addons... OK
  Applying business.0012_migrate_legacy_plans...Plan migration completed successfully OK
```

## Estado Final

### Servicios Docker
✅ **mirubro-api** - Running (puerto 8000)  
✅ **mirubro-postgres** - Running (puerto 5432)  
✅ **mirubro-redis** - Running (puerto 6379)  
✅ **mirubro-web** - Running (puerto 3000)

### Endpoints Protegidos con Entitlements

Todos los siguientes endpoints ahora están protegidos con el sistema de entitlements:

1. **Clientes** (`gestion.customers`)
   - `/api/v1/customers/` - `CustomerListCreateView`, `CustomerDetailView`

2. **Caja** (`gestion.cash`)
   - `/api/v1/cash/registers/` - `CashRegisterListView`
   - `/api/v1/cash/sessions/open/` - `CashSessionOpenView`
   - `/api/v1/cash/sessions/active/` - `ActiveCashSessionView`
   - `/api/v1/cash/summary/` - `CashSummaryView`
   - `/api/v1/cash/sessions/<id>/summary/` - `CashSessionSummaryView`
   - `/api/v1/cash/sessions/<id>/close/` - `CashSessionCloseView`
   - `/api/v1/cash/sessions/<id>/collect-pending/` - `CashSessionCollectPendingView`
   - `/api/v1/cash/payments/` - `CashPaymentView`
   - `/api/v1/cash/movements/` - `CashMovementView`

3. **Tesorería** (`gestion.treasury`)
   - Todos los viewsets en `treasury/views.py` mediante `BaseTreasuryViewSet`

4. **Facturas** (`gestion.invoices`)
   - `/api/v1/invoices/` - `InvoiceListView`, `InvoiceDetailView`
   - `/api/v1/invoices/series/` - `InvoiceSeriesListView`
   - `/api/v1/invoices/issue/` - `InvoiceIssueView`
   - `/api/v1/invoices/<id>/pdf/` - `InvoicePDFView`
   - `/api/v1/orders/<id>/invoice/` - `OrderInvoiceView`

5. **Reportes** (`gestion.reports`)
   - `/api/v1/reports/summary/` - `ReportSummaryView`
   - `/api/v1/reports/sales/` - `ReportSalesListView`, `ReportSalesDetailView`
   - `/api/v1/reports/payments/` - `PaymentsReportView`
   - `/api/v1/reports/products/` - `ReportProductsView`
   - `/api/v1/reports/stock/alerts/` - `StockAlertsReportView`
   - `/api/v1/reports/cash/closures/` - `CashClosureListView`, `CashClosureDetailView`

### Entitlements por Plan

**START:**
- gestion.products
- gestion.inventory_basic
- gestion.sales_basic
- gestion.dashboard_basic
- gestion.settings_basic

**PRO (14 entitlements):**
- Todo de START +
- gestion.customers ✅
- gestion.cash ✅
- gestion.quotes
- gestion.reports ✅
- gestion.export
- gestion.treasury ✅
- gestion.inventory_advanced
- gestion.sales_advanced
- gestion.rbac_full
- gestion.audit

**BUSINESS (18 entitlements):**
- Todo de PRO +
- gestion.invoices ✅
- gestion.multi_branch
- gestion.transfers
- gestion.consolidated_reports

**ENTERPRISE:**
- Todo de BUSINESS (personalizable)

### Add-ons Disponibles
- `extra_branch` - Sucursales adicionales
- `extra_seat` - Usuarios adicionales
- `invoices_module` - Módulo de facturación para plan PRO

## Archivos Modificados

1. `services/api/src/apps/invoices/views.py` - 2 clases actualizadas
2. `services/api/src/apps/orders/views.py` - 1 importación + 1 clase actualizada
3. `services/api/src/apps/resto/reports/views.py` - 1 mixin eliminado + 3 clases actualizadas
4. `services/api/src/apps/reports/views.py` - Clase `ReportsFeatureMixin` eliminada
5. `services/api/src/apps/reports/urls.py` - Importación y ruta eliminadas
6. `services/api/src/apps/business/migrations/0011_subscription_plans_addons.py` - Renombrado y dependencia actualizada
7. `services/api/src/apps/business/migrations/0012_migrate_legacy_plans.py` - Renombrado y dependencia actualizada

## Lecciones Aprendidas

1. **Refactoring completo de mixins:** Al eliminar una clase base (mixin), es crítico buscar TODAS las referencias en el proyecto, no solo las más obvias.

2. **Numeración de migraciones:** Siempre verificar el último número de migración existente antes de crear nuevas migraciones para evitar conflictos.

3. **Módulos separados:** No todos los módulos necesitan entitlements del servicio Gestión Comercial. El módulo `resto` (restaurante) es independiente y mantiene solo RBAC.

4. **Reconstrucción de Docker:** Usar `--build --force-recreate` cuando los cambios no se reflejan por caché.

## Próximos Pasos

1. ✅ Migraciones aplicadas
2. ⏭️ Testing funcional de entitlements (probar con diferentes planes)
3. ⏭️ Validar frontend con `useEntitlements` hook
4. ⏭️ Testing end-to-end de upgrade flow
5. ⏭️ Documentar casos de uso para product team

## Comandos Útiles

```bash
# Ver estado de contenedores
docker compose ps

# Ver logs de API
docker compose logs api -f

# Reconstruir API
docker compose up -d --build api

# Hacer merge de migraciones (si es necesario)
docker compose exec api python manage.py makemigrations --merge

# Aplicar migraciones
docker compose exec api python manage.py migrate

# Verificar entitlements de un business (en Django shell)
docker compose exec api python manage.py shell
>>> from apps.business.models import Business
>>> from apps.business.entitlements import get_effective_entitlements
>>> business = Business.objects.first()
>>> entitlements = get_effective_entitlements(business.subscription)
>>> print(entitlements)
```
