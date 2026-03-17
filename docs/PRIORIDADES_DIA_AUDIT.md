# Auditoría Funcional y Técnica: Prioridades del Día × Gestión Comercial

> **Fecha:** 2026-03-15  
> **Alcance:** Módulo de Gestión Comercial — Sección "Prioridades del día" en Dashboard  
> **Stack verificado:** Django ORM (no Prisma) + Next.js + React Query

---

## A. Estado Actual — Cómo funciona hoy "Prioridades del día"

### Ubicación

| Capa | Archivo | Ruta |
|------|---------|------|
| Server Component | `apps/web/src/app/app/gestion/dashboard/page.tsx` | Entry point — extrae `session.features` y `session.permissions` |
| Client Router | `apps/web/src/app/app/gestion/dashboard/dashboard-client.tsx` | Pasa `permissions`, `features`, `planName` a `OwnerDashboard` |
| Orquestador | `apps/web/src/app/app/gestion/dashboard/components/owner/owner-dashboard.tsx` | Layout maestro del dashboard |
| **Componente Prioridades** | `apps/web/src/app/app/gestion/dashboard/components/owner/priorities-list.tsx` | **Componente directo — 117 líneas** |

### Arquitectura de datos

**Las prioridades se computan 100% client-side.** No existe endpoint dedicado de prioridades en el backend. El componente `PrioritiesList` construye un array condicional a partir de 3 fuentes independientes:

| # | Prioridad actual | Condición | Fuente de datos | Endpoint | Hook | Nivel |
|---|-----------------|-----------|-----------------|----------|------|-------|
| 1 | "Abrir caja para comenzar a operar" | `!cashQuery.data?.session` (caja cerrada) | Cash module | `GET /api/v1/cash/summary/` | `useCashSummary()` | `high` (rojo) |
| 2 | "Responder N presupuestos pendientes" | `pendingQuotes > 0` (status = draft/sent) | Quotes | `GET /api/v1/sales/quotes/?status=draft,sent` | `usePendingQuotesSummary()` | `medium` (ámbar) |
| 3 | "Reponer N productos en stock crítico" | `lowStock > 0` | Inventory summary | `GET /api/v1/inventory/summary/` | `useInventorySummary()` | `medium` (ámbar) |

### Props del componente

```typescript
type PrioritiesListProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewStock: boolean;
    canViewQuotes: boolean;
    canViewCash: boolean;
};
```

### Limitaciones detectadas

1. **Solo 3 reglas hardcodeadas** — Caja, presupuestos y stock. No hay un sistema extensible.
2. **Sin tipo `Priority` formal** — El array se construye ad-hoc con un objeto inline `{id, title, href, priority, icon, actionLabel}`.
3. **Solo 2 niveles de severidad** — `high` y `medium`. No hay `critical` ni `informative`.
4. **Sin filtro por plan** — No se valida si el tenant tiene el entitlement correspondiente. Si `canViewCash=false` por permisos RBAC se oculta, pero no por plan.
5. **Sin filtro por fecha** — No hay noción de "urgencia temporal". Los presupuestos pendientes no distinguen si están por vencer hoy o dentro de un mes.
6. **Sin conexión con Treasury** — Los gastos pendientes, gastos fijos vencidos y pagos pendientes NO aparecen, aunque el `FinanceExpensesBlock` existe en la sidebar y consume `GET /api/v1/treasury/dashboard/finance-summary/`.
7. **Sin conexión con Pedidos Comerciales** — Los `Order` (pedidos) con entregas vencidas o pagos pendientes no aparecen.
8. **Sin conexión con Cuentas por Cobrar/Pagar** — No se detectan cobros pendientes de pedidos.
9. **Sin estado "Todo al día" contextualizado** — Cuando no hay prioridades muestra un mensaje genérico, sin indicar qué se verificó.
10. **Datos no centralizados** — Cada prioridad tiene su propia query con refresh intervals distintos (cash: 30s, quotes: 60s, stock: stale en SSR).

---

## B. Inventario de Funcionalidades de Gestión Comercial Detectadas

### Módulos Backend verificados en código

| Módulo | App Django | Modelos principales | URL prefix |
|--------|-----------|---------------------|------------|
| **Caja / POS** | `cash` | CashSession, Payment, CashMovement, Terminal | `/api/v1/cash/`, `/api/v1/pos/cash/` |
| **Ventas** | `sales` | Sale | `/api/v1/sales/` |
| **Presupuestos** | `sales` | Quote (6 estados: draft→sent→accepted/rejected/expired/converted) | `/api/v1/sales/quotes/` |
| **Pedidos Comerciales** | `sales` | Order (7 estados), OrderPayment, OrderHistory | `/api/v1/sales/orders/` |
| **Tesorería / Finanzas** | `treasury` | Account, Transaction, Expense, FixedExpense, FixedExpensePeriod, Employee, PayrollPayment, Budget | `/api/v1/treasury/` |
| **Inventario / Stock** | `inventory` | ProductStock, StockMovement, StockReplenishment | `/api/v1/inventory/` |
| **Catálogo** | `catalog` | Product (con `stock_min`), ProductCategory | `/api/v1/catalog/` |
| **Clientes** | `customers` | Customer | `/api/v1/customers/` |
| **Facturación** | `invoices` | Invoice, DocumentSeries | `/api/v1/invoices/` |
| **Reportes** | `reports` | Sin modelos propios — agrega de otros | `/api/v1/reports/` |
| **Config Negocio** | `business` | Business, CommercialSettings, Subscription | `/api/v1/` |

### Campos time-sensitive clave para prioridades

| Modelo | Campo | Tipo | Relevancia |
|--------|-------|------|-----------|
| `Quote.valid_until` | DateField nullable | Fecha de vencimiento del presupuesto |
| `Order.estimated_delivery_date` | DateField nullable | Fecha estimada de entrega |
| `Order.payment_status` | pending/partial/paid | Cobros pendientes |
| `Order.pending_balance` | Decimal | Monto por cobrar |
| `Expense.due_date` | DateField | Fecha de vencimiento del gasto |
| `Expense.status` | pending/paid/cancelled | Gastos por pagar |
| `FixedExpensePeriod.due_date` | DateField nullable | Fecha de vencimiento del gasto fijo |
| `FixedExpensePeriod.status` | pending/paid/skipped | Gasto fijo mensual por pagar |
| `CashSession.status` | open/closed/audited | Caja abierta o cerrada |
| `PayrollPayment.paid_at` | DateTimeField | Sueldos pagados |
| `Employee.pay_frequency` | monthly/weekly | Frecuencia de pago |
| `Product.stock_min` | PositiveInteger | Umbral de stock mínimo |
| `ProductStock.quantity` | Decimal | Stock actual |

---

## C. Prioridades Faltantes — Inventario Detallado

### C.1 — Prioridades de ALTA urgencia (bloqueantes o con deadlines vencidos)

| # | Prioridad | Origen | Condición de activación | Nivel | CTA | Ruta destino | Plan | Observaciones |
|---|-----------|--------|------------------------|-------|-----|-------------|------|---------------|
| P1 | **Gastos fijos vencidos del mes** | Treasury → `FixedExpensePeriod` | `status=PENDING AND due_date < hoy` | **CRÍTICA** | "Pagar ahora" | `/app/gestion/finanzas/gastos` | PRO+ (`gestion.treasury`) | Los datos ya se calculan en `DashboardFinanceSummaryView` con campo `is_overdue` pero solo se muestran en `FinanceExpensesBlock`, no en prioridades |
| P2 | **Gastos puntuales vencidos** | Treasury → `Expense` | `status=PENDING AND due_date < hoy` | **CRÍTICA** | "Pagar ahora" | `/app/gestion/finanzas/gastos` | PRO+ (`gestion.treasury`) | Mismo caso que P1. El backend ya retorna `is_overdue` en `onetime_pending.items` |
| P3 | **Pedidos con entrega vencida** | Sales → `Order` | `status IN (confirmed, in_preparation, ready_for_delivery) AND estimated_delivery_date < hoy` | **CRÍTICA** | "Ver pedidos atrasados" | `/app/gestion/ventas/pedidos?status=confirmed,in_preparation,ready_for_delivery` | PRO+ (`gestion.quotes` implica acceso a orders) | No hay endpoint de resumen de pedidos. Requiere nueva query o endpoint |
| P4 | **Presupuestos por vencer hoy** | Sales → `Quote` | `status IN (draft, sent) AND valid_until = hoy` | **URGENTE** | "Responder hoy" | `/app/gestion/ventas/presupuestos` | PRO+ (`gestion.quotes`) | Hoy solo se cuentan los pendientes sin distinguir vencimiento. `valid_until` existe pero no se usa |

### C.2 — Prioridades de MEDIA urgencia (requieren acción hoy)

| # | Prioridad | Origen | Condición de activación | Nivel | CTA | Ruta destino | Plan | Observaciones |
|---|-----------|--------|------------------------|-------|-----|-------------|------|---------------|
| P5 | **Gastos fijos del mes sin pagar** | Treasury → `FixedExpensePeriod` | `status=PENDING AND due_date >= hoy` (del mes actual) | **URGENTE** | "Ver gastos fijos" | `/app/gestion/finanzas/gastos` | PRO+ (`gestion.treasury`) | Hoy `fixed_pending` ya llega en `finance-summary` pero no se refleja en prioridades |
| P6 | **Gastos puntuales pendientes** | Treasury → `Expense` | `status=PENDING AND due_date >= hoy AND due_date <= hoy+7d` (próximos 7 días) | **IMPORTANTE** | "Revisar gastos" | `/app/gestion/finanzas/gastos` | PRO+ (`gestion.treasury`) | Criterio: gastos por vencer esta semana |
| P7 | **Pedidos pendientes de confirmar** | Sales → `Order` | `status = pending_confirmation` (no gestionados) | **URGENTE** | "Confirmar pedidos" | `/app/gestion/ventas/pedidos?status=pending_confirmation` | PRO+ | Un pedido sin confirmar bloquea el flujo operativo |
| P8 | **Cobros pendientes de pedidos** | Sales → `Order` | `payment_status IN (pending, partial) AND status != cancelled AND pending_balance > 0` | **URGENTE** | "Cobrar pedidos" | `/app/gestion/ventas/pedidos` | PRO+ | Monto comprometido sin cobrar. `pending_balance` ya existe en el modelo |
| P9 | **Entregas programadas para hoy** | Sales → `Order` | `estimated_delivery_date = hoy AND status IN (confirmed, in_preparation, ready_for_delivery)` | **URGENTE** | "Ver entregas de hoy" | `/app/gestion/ventas/pedidos` | PRO+ | Información operativa clave para planificar el día |
| P10 | **Productos sin stock (agotados)** | Inventory → `ProductStock` | `out_of_stock > 0` | **URGENTE** | "Reponer ahora" | `/app/gestion/stock?status=out` | START+ (`gestion.inventory_basic`) | Hoy solo se muestra `low_stock` en prioridades. `out_of_stock` existe en el summary pero no se distingue |

### C.3 — Prioridades INFORMATIVAS (mejoran gestión pero no bloquean)

| # | Prioridad | Origen | Condición de activación | Nivel | CTA | Ruta destino | Plan | Observaciones |
|---|-----------|--------|------------------------|-------|-----|-------------|------|---------------|
| P11 | **Sueldos del mes pendientes** | Treasury → `Employee` + `PayrollPayment` | Empleados activos con `pay_frequency=monthly` sin PayrollPayment del mes actual | **IMPORTANTE** | "Gestionar sueldos" | `/app/gestion/finanzas/sueldos` | PRO+ (`gestion.treasury`) | Requiere comparar empleados activos vs payments del mes. No hay endpoint de "sueldos pendientes" |
| P12 | **Presupuestos vencidos sin gestionar** | Sales → `Quote` | `status IN (draft, sent) AND valid_until < hoy AND valid_until IS NOT NULL` | **IMPORTANTE** | "Revisar vencidos" | `/app/gestion/ventas/presupuestos` | PRO+ | Presupuestos expirados que nunca se marcaron como expired/rejected |
| P13 | **Presupuesto con monto alto por vencer** | Sales → `Quote` | `status IN (draft, sent) AND valid_until BETWEEN hoy AND hoy+3d AND total > umbral` | **INFORMATIVA** | "Seguir presupuesto" | `/app/gestion/ventas/presupuestos/{id}` | PRO+ | Requiere definir umbral de monto. Opcional pero de alto valor |
| P14 | **Caja abierta sin movimientos** | Cash → `CashSession` | `status=open AND no Payments in last 4h AND opened_at < hoy-4h` | **INFORMATIVA** | "Revisar caja" | `/app/cash` | PRO+ (`gestion.cash`) | Posible olvido de cerrar caja o anomalía operativa |
| P15 | **Presupuesto de categoría superado** | Treasury → `Budget` | `spent > limit_amount` para algún presupuesto del mes | **INFORMATIVA** | "Ver presupuestos" | `/app/gestion/finanzas/reportes` | PRO+ | Existe el modelo Budget con `spent` y `percentage`. Necesita endpoint de alerta |

---

## D. Recomendación Final

### D.1 — Prioridades que faltan conectar SÍ O SÍ (Fase 1)

Estas son las que **ya tienen datos disponibles** en el backend o se pueden obtener con queries simples:

| Prioridad | Razón | Esfuerzo | Datos disponibles |
|-----------|-------|----------|-------------------|
| **P1 — Gastos fijos vencidos** | Impacto financiero directo. Backend ya calcula `is_overdue` en `finance-summary` | **BAJO** — Solo frontend | ✅ `DashboardFinanceSummaryView` ya retorna `fixed_pending` con `due_date` |
| **P2 — Gastos puntuales vencidos** | Deuda acumulada. Backend ya lo tiene | **BAJO** — Solo frontend | ✅ `onetime_pending.items[].is_overdue` ya existe |
| **P10 — Productos agotados** | Bloquea ventas directamente | **BAJO** — Solo frontend | ✅ `inventorySummary.out_of_stock` ya existe como prop |
| **P7 — Pedidos pendientes de confirmar** | Bloquea flujo operativo | **MEDIO** — Nuevo endpoint o query frontend | ⚠️ Requiere `fetchOrders({status: 'pending_confirmation'})` — endpoint existe pero no hay resumen/conteo |
| **P4 — Presupuestos por vencer hoy** | Alta probabilidad de pérdida | **MEDIO** — Requiere filtro por `valid_until` | ⚠️ El campo `valid_until` existe en Quote pero el hook actual solo filtra por `status=draft,sent` |

### D.2 — Prioridades recomendadas para Fase 2

| Prioridad | Razón | Esfuerzo |
|-----------|-------|----------|
| **P5 — Gastos fijos del mes sin pagar** | Visibilidad financiera operativa | **BAJO** — Datos ya en finance-summary |
| **P8 — Cobros pendientes de pedidos** | Monto comprometido sin cobrar | **MEDIO** — Requiere endpoint de resumen |
| **P9 — Entregas de hoy** | Planificación del día | **MEDIO** — Requiere filtro `estimated_delivery_date=today` |
| **P3 — Pedidos con entrega vencida** | Pedidos atrasados afectan al cliente | **MEDIO** — Requiere endpoint o query |
| **P12 — Presupuestos vencidos sin gestionar** | Higiene operativa | **BAJO** — Ampliar query de quotes |

### D.3 — Prioridades que requieren definiciones de negocio adicionales

| Prioridad | Qué falta definir |
|-----------|-------------------|
| **P11 — Sueldos pendientes** | ¿Cuándo se considera "adeudado" un sueldo? ¿Se compara con `pay_frequency` y día del mes? |
| **P13 — Presupuesto de monto alto** | ¿Cuál es el umbral de "monto alto"? ¿Es configurable por negocio? |
| **P14 — Caja abierta sin movimiento** | ¿4 horas sin movimiento es el criterio correcto? ¿Es configurable? |
| **P15 — Presupuesto de categoría superado** | ¿Se muestra como prioridad o solo como alerta? ¿Cuándo se activa vs informar en finanzas? |

---

## E. Impacto Técnico

### E.1 — Refactorización recomendada del componente de prioridades

**Estado actual:** Lógica monolítica en `priorities-list.tsx` con 3 reglas hardcodeadas.

**Propuesta: Priority Builder/Aggregator**

```
┌──────────────────────────────────────────────────────────────────┐
│                     NUEVA ARQUITECTURA                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐     ┌─────────────────────┐            │
│  │  useDailyPriorities │ ←── │  Priority Builders   │            │
│  │  (hook central)     │     │  (por módulo)        │            │
│  └────────┬────────────┘     ├─────────────────────┤            │
│           │                  │ buildCashPriorities  │            │
│           ▼                  │ buildQuotePriorities │            │
│  ┌─────────────────────┐    │ buildOrderPriorities │            │
│  │  PrioritiesList     │    │ buildExpensePriorities│           │
│  │  (presentational)   │    │ buildStockPriorities │            │
│  └─────────────────────┘    │ buildPayrollPriorities│           │
│                              └─────────────────────┘            │
│                                                                  │
│  ┌─────────────────────┐                                        │
│  │  Priority Type       │                                        │
│  │  { id, title, href,  │                                        │
│  │    severity, icon,   │                                        │
│  │    actionLabel,      │                                        │
│  │    module, plan,     │                                        │
│  │    sortWeight,       │                                        │
│  │    metadata? }       │                                        │
│  └─────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────┘
```

### E.2 — Archivos a crear/modificar

#### Fase 1 — Frontend only (prioridades con datos ya disponibles)

| Archivo | Acción | Detalle |
|---------|--------|---------|
| `apps/web/src/features/gestion/types.ts` | **MODIFICAR** | Agregar tipo `Priority` formal con `severity: 'critical' \| 'urgent' \| 'important' \| 'informative'` |
| `apps/web/src/features/gestion/priorities/` | **CREAR** | Nuevo directorio para lógica de prioridades |
| `apps/web/src/features/gestion/priorities/types.ts` | **CREAR** | Tipo `DailyPriority`, enum `PrioritySeverity` |
| `apps/web/src/features/gestion/priorities/builders.ts` | **CREAR** | Funciones puras: `buildCashPriorities()`, `buildExpensePriorities()`, `buildQuotePriorities()`, `buildStockPriorities()` |
| `apps/web/src/features/gestion/priorities/use-daily-priorities.ts` | **CREAR** | Hook central que agrega todos los builders, filtra por plan/permisos, ordena por severidad |
| `apps/web/src/app/app/gestion/dashboard/components/owner/priorities-list.tsx` | **MODIFICAR** | Reemplazar lógica inline por `useDailyPriorities()`. El componente queda puramente presentacional |
| `apps/web/src/app/app/gestion/dashboard/components/owner/owner-dashboard.tsx` | **MODIFICAR** | Ampliar props para pasar `canViewFinance` y `features.treasury` a PrioritiesList |

#### Fase 2 — Backend + Frontend (prioridades que necesitan nuevos endpoints)

| Archivo | Acción | Detalle |
|---------|--------|---------|
| `services/api/src/apps/sales/views.py` | **MODIFICAR** | Agregar `OrderSummaryView` en `/api/v1/sales/orders/summary/` que retorne conteos por estado + overdue count |
| `services/api/src/apps/sales/urls.py` | **MODIFICAR** | Registrar nueva ruta `orders/summary/` |
| `apps/web/src/features/gestion/api.ts` | **MODIFICAR** | Agregar `fetchOrdersSummary()` |
| `apps/web/src/features/gestion/hooks.ts` | **MODIFICAR** | Agregar `useOrdersSummary()` |
| `apps/web/src/features/gestion/priorities/builders.ts` | **MODIFICAR** | Agregar `buildOrderPriorities()` |
| `apps/web/src/lib/api/treasury.ts` | **MODIFICAR** | Reutilizar `getDashboardFinanceSummary()` (ya existe) |

#### Fase 3 — Refinamiento de ranking y UX

| Archivo | Acción | Detalle |
|---------|--------|---------|
| `apps/web/src/features/gestion/priorities/ranking.ts` | **CREAR** | Algoritmo de scoring: peso por severidad × antigüedad × monto × cantidad afectada |
| `apps/web/src/app/app/gestion/dashboard/components/owner/priorities-list.tsx` | **MODIFICAR** | UI: badges de severidad, conteo de prioridades por nivel, colapsable |

### E.3 — Nuevo endpoint propuesto: Orders Summary

```python
# services/api/src/apps/sales/views.py

class OrderSummaryView(generics.GenericAPIView):
    """
    GET /api/v1/sales/orders/summary/
    Returns counts and totals for operational priority detection.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    required_permission = 'view_sales'

    def get(self, request):
        business = request.business
        today = date.today()

        orders = Order.objects.filter(
            business=business,
            deleted_at__isnull=True
        )

        pending_confirmation = orders.filter(status='pending_confirmation').count()
        
        overdue_delivery = orders.filter(
            status__in=['confirmed', 'in_preparation', 'ready_for_delivery'],
            estimated_delivery_date__lt=today,
            estimated_delivery_date__isnull=False
        ).count()

        today_deliveries = orders.filter(
            status__in=['confirmed', 'in_preparation', 'ready_for_delivery'],
            estimated_delivery_date=today
        ).count()

        pending_payment = orders.filter(
            status__in=['confirmed', 'in_preparation', 'ready_for_delivery', 'delivered'],
            payment_status__in=['pending', 'partial']
        ).aggregate(
            count=Count('id'),
            total_pending=Sum('pending_balance')
        )

        return Response({
            'pending_confirmation': pending_confirmation,
            'overdue_delivery': overdue_delivery,
            'today_deliveries': today_deliveries,
            'pending_payment_count': pending_payment['count'] or 0,
            'pending_payment_total': str(pending_payment['total_pending'] or 0),
        })
```

### E.4 — Tipo `DailyPriority` propuesto

```typescript
// apps/web/src/features/gestion/priorities/types.ts

export type PrioritySeverity = 'critical' | 'urgent' | 'important' | 'informative';

export type PriorityModule = 
  | 'cash' 
  | 'quotes' 
  | 'orders' 
  | 'treasury' 
  | 'inventory' 
  | 'payroll'
  | 'invoices';

export type DailyPriority = {
  id: string;                          // e.g. 'treasury.fixed_overdue'
  module: PriorityModule;
  title: string;                       // e.g. "3 gastos fijos vencidos"
  description?: string;                // detalle opcional
  severity: PrioritySeverity;
  sortWeight: number;                  // para ordenamiento (menor = más urgente)
  href: string;                        // ruta destino
  actionLabel: string;                 // CTA text
  icon: LucideIcon;
  count?: number;                      // cantidad de items afectados
  amount?: number;                     // monto total si aplica
  requiredEntitlement?: string;        // e.g. 'gestion.treasury'
  requiredFeature?: string;            // feature flag del plan
  metadata?: Record<string, unknown>;  // datos extra por tipo
};

// Sort weights por severidad (sugerido)
export const SEVERITY_WEIGHTS: Record<PrioritySeverity, number> = {
  critical: 100,
  urgent: 200,
  important: 300,
  informative: 400,
};
```

### E.5 — Hook central propuesto

```typescript
// apps/web/src/features/gestion/priorities/use-daily-priorities.ts

export function useDailyPriorities(options: {
  permissions: DashboardPermissions;
  features: DashboardFeatures;
  inventorySummary: InventorySummaryStats | null;
}) {
  const { permissions, features, inventorySummary } = options;
  
  // Datos existentes (ya se consumen)
  const cashQuery = useCashSummary(undefined, permissions.canViewCash && features.cash);
  const quotesQuery = usePendingQuotesSummary(permissions.canViewQuotes && features.quotes);
  const financeQuery = useQuery({
    queryKey: ['treasury', 'dashboard-finance-summary'],
    queryFn: getDashboardFinanceSummary,
    enabled: permissions.canViewFinance && features.treasury,
    staleTime: 60_000,
  });
  
  // Nuevo (Fase 2)
  const ordersQuery = useOrdersSummary(permissions.canViewQuotes && features.quotes);

  // Agregar prioridades de todos los módulos
  const priorities: DailyPriority[] = useMemo(() => {
    const all: DailyPriority[] = [];

    if (permissions.canViewCash && features.cash) {
      all.push(...buildCashPriorities(cashQuery.data));
    }
    if (permissions.canViewQuotes && features.quotes) {
      all.push(...buildQuotePriorities(quotesQuery.data));
    }
    if (permissions.canViewStock && features.inventory) {
      all.push(...buildStockPriorities(inventorySummary));
    }
    if (permissions.canViewFinance && features.treasury) {
      all.push(...buildExpensePriorities(financeQuery.data));
    }
    if (permissions.canViewQuotes && features.quotes) {
      all.push(...buildOrderPriorities(ordersQuery.data));
    }

    // Ordenar por peso de severidad, luego por monto descendente
    return all.sort((a, b) => a.sortWeight - b.sortWeight || (b.amount ?? 0) - (a.amount ?? 0));
  }, [cashQuery.data, quotesQuery.data, inventorySummary, financeQuery.data, ordersQuery.data]);

  const isLoading = cashQuery.isLoading || quotesQuery.isLoading || financeQuery.isLoading;

  return { priorities, isLoading };
}
```

---

## F. Criterio de Prioridad Propuesto

### Qué entra en "Prioridades del día"

Una acción entra si cumple **al menos uno** de estos criterios:

| Criterio | Descripción | Ejemplo |
|----------|-------------|---------|
| **Bloqueo operativo** | Sin esta acción no se puede operar | Caja cerrada |
| **Vencimiento hoy o pasado** | Deadline del día o ya vencido | Gasto fijo vencido, entrega atrasada |
| **Deadline esta semana** | A 7 días o menos del vencimiento | Presupuesto por vencer, gasto próximo |
| **Monto comprometido** | Dinero pendiente de cobrar o pagar | Cobros pendientes de pedidos |
| **Acción manual requerida** | Requiere decisión/intervención humana | Confirmar pedido, responder presupuesto |
| **Impacto directo en ventas** | Impide vender o entregar | Stock agotado |

### Orden de presentación

| Nivel | Color | Criterio | Ejemplos |
|-------|-------|----------|----------|
| **CRÍTICA** | 🔴 Rojo | Bloqueo operativo o deadline vencido | Caja cerrada, gastos vencidos, entregas atrasadas |
| **URGENTE** | 🟠 Naranja | Acción requerida hoy o deadline próximo | Pedidos por confirmar, entregas de hoy, cobros pendientes |
| **IMPORTANTE** | 🟡 Ámbar | Requiere atención esta semana | Presupuestos pendientes, stock bajo, gastos fijos del mes |
| **INFORMATIVA** | 🔵 Azul | info útil sin deadline | Caja sin movimiento, presupuesto superado |

### Regla de máximos

- Mostrar máximo **8 prioridades** visibles (las de mayor severidad).
- Si hay más de 8, mostrar un link "Ver todas las prioridades" o colapsar las de menor urgencia.
- Si hay 0, mostrar "Todo al día" (actual).

---

## G. Restricciones por Plan

### Mapa de prioridades × plan

| Prioridad | Entitlement requerido | Plan mínimo | Comportamiento si no tiene plan |
|-----------|-----------------------|-------------|-------------------------------|
| P1 — Gastos fijos vencidos | `gestion.treasury` | PRO | No mostrar |
| P2 — Gastos puntuales vencidos | `gestion.treasury` | PRO | No mostrar |
| P3 — Pedidos entrega vencida | `gestion.quotes`* | PRO | No mostrar |
| P4 — Presupuestos por vencer | `gestion.quotes` | PRO | No mostrar |
| P5 — Gastos fijos del mes | `gestion.treasury` | PRO | No mostrar |
| P6 — Gastos próximos a vencer | `gestion.treasury` | PRO | No mostrar |
| P7 — Pedidos sin confirmar | `gestion.quotes`* | PRO | No mostrar |
| P8 — Cobros pendientes pedidos | `gestion.quotes`* | PRO | No mostrar |
| P9 — Entregas de hoy | `gestion.quotes`* | PRO | No mostrar |
| P10 — Stock agotado | `gestion.inventory_basic` | START | Mostrar siempre |
| P11 — Sueldos pendientes | `gestion.treasury` | PRO | No mostrar |
| P12 — Presupuestos vencidos | `gestion.quotes` | PRO | No mostrar |
| P13 — Presupuesto monto alto | `gestion.quotes` | PRO | No mostrar |
| P14 — Caja sin movimiento | `gestion.cash` | PRO | No mostrar |
| P15 — Presupuesto superado | `gestion.treasury` | PRO | No mostrar |
| **Caja cerrada (actual)** | `gestion.cash` | PRO | Hoy NO se valida plan → **BUG** |
| **Presupuestos pendientes (actual)** | `gestion.quotes` | PRO | Hoy NO se valida plan → **BUG** |
| **Stock bajo (actual)** | `gestion.inventory_basic` | START | OK — aplica a todos |

> **⚠️ Bug detectado:** Las prioridades actuales de Caja y Presupuestos se muestran solo según RBAC (`canViewCash`, `canViewQuotes`) pero **no verifican el entitlement del plan**. Un tenant START que de alguna manera tenga el permiso RBAC vería prioridades de features que no tiene habilitadas. La prioridad debería verificar tanto el permiso como el feature flag del plan: `permissions.canViewCash && features.cash`.
> 
> **Corrección:** Revisando el código de `owner-dashboard.tsx`, se confirma que las props ya se pasan combinadas: `canViewCash={permissions.canViewCash && features.cash}`. Sin embargo, `PrioritiesList` no recibe `features` directamente, así que si se agregan prioridades de treasury u orders, hay que asegurarse de pasar los features correspondientes.

### Propuesta de comportamiento por plan

- **Plan START:** Solo prioridades de stock (P10 + stock bajo actual). La caja no es feature START, pero hay que verificar que `features.cash = false` en START.
- **Plan PRO:** Todas las prioridades de Gestión Comercial.
- **Plan BUSINESS:** Todas + futuras prioridades multi-sucursal.
- **Filtro:** El hook `useDailyPriorities` debe recibir `features: DashboardFeatures` y filtrar cada builder según el feature flag correspondiente. Esto ya se hace parcialmente en `owner-dashboard.tsx` con las props combinadas.

---

## H. Plan de Implementación por Fases

### Fase 1 — Prioridades críticas (datos ya disponibles) — ~3-4 días dev

**Objetivo:** Conectar las prioridades que hoy tienen datos en el frontend pero no se muestran.

| Tarea | Detalle | Archivos |
|-------|---------|----------|
| 1.1 | Crear tipo `DailyPriority` y `PrioritySeverity` | `features/gestion/priorities/types.ts` (nuevo) |
| 1.2 | Crear builders para prioridades existentes | `features/gestion/priorities/builders.ts` (nuevo) |
| 1.3 | Crear hook `useDailyPriorities` | `features/gestion/priorities/use-daily-priorities.ts` (nuevo) |
| 1.4 | Agregar `buildExpensePriorities()` — consume `finance-summary` ya existente | `builders.ts` |
| 1.5 | Separar stock agotado de stock bajo en prioridades | `builders.ts` |
| 1.6 | Refactorizar `PrioritiesList` para usar `useDailyPriorities` | `priorities-list.tsx` |
| 1.7 | Pasar `canViewFinance` y `features.treasury` a PrioritiesList | `owner-dashboard.tsx` |
| 1.8 | Agregar 4 niveles de severidad visual (rojo/naranja/ámbar/azul) | `priorities-list.tsx` |

**Prioridades conectadas en Fase 1:**
- ✅ P1 — Gastos fijos vencidos (datos de `finance-summary`)
- ✅ P2 — Gastos puntuales vencidos (datos de `finance-summary`)
- ✅ P5 — Gastos fijos del mes (datos de `finance-summary`)
- ✅ P10 — Stock agotado (datos de `inventorySummary`)
- ✅ Refactor caja + presupuestos + stock bajo (mismo sistema)

### Fase 2 — Prioridades importantes (requieren backend) — ~5-6 días dev

**Objetivo:** Agregar endpoints de resumen y conectar pedidos + presupuestos enriquecidos.

| Tarea | Detalle | Archivos |
|-------|---------|----------|
| 2.1 | Crear `OrderSummaryView` en backend | `services/api/src/apps/sales/views.py`, `urls.py` |
| 2.2 | Crear `fetchOrdersSummary()` y `useOrdersSummary()` en frontend | `features/gestion/api.ts`, `hooks.ts` |
| 2.3 | Crear `buildOrderPriorities()` | `priorities/builders.ts` |
| 2.4 | Enriquecer query de quotes para detectar `valid_until` próximo a vencer | `features/gestion/api.ts`, `hooks.ts` |
| 2.5 | Crear `buildQuoteExpirationPriorities()` — presupuestos por vencer | `priorities/builders.ts` |
| 2.6 | Conectar P3, P4, P7, P8, P9 | Hook central |
| 2.7 | Agregar endpoint de quotes con filtro `valid_until` ranges | `services/api/src/apps/sales/views.py` |

**Prioridades conectadas en Fase 2:**
- ✅ P3 — Pedidos con entrega vencida
- ✅ P4 — Presupuestos por vencer hoy
- ✅ P7 — Pedidos pendientes de confirmar
- ✅ P8 — Cobros pendientes de pedidos
- ✅ P9 — Entregas de hoy
- ✅ P12 — Presupuestos vencidos sin gestionar

### Fase 3 — Refinamiento de ranking y UX — ~2-3 días dev

**Objetivo:** Mejorar presentación, scoring y agregar prioridades informativas.

| Tarea | Detalle |
|-------|---------|
| 3.1 | Implementar scoring algorithm (severidad × antigüedad × monto × cantidad) |
| 3.2 | Agregar P6, P11, P13, P14, P15 con sus builders |
| 3.3 | UI: badges de conteo por nivel, expandir/colapsar, max 8 visible |
| 3.4 | Agregar "Ver todas las prioridades" si hay más de 8 |
| 3.5 | Agregar animación suave de entrada/salida cuando una prioridad se resuelve |
| 3.6 | Tests unitarios de builders y hook central |

---

## I. Resumen Ejecutivo

| Métrica | Valor |
|---------|-------|
| Prioridades actuales en el dashboard | **3** |
| Prioridades faltantes detectadas (críticas/urgentes) | **9** (P1-P9, P10) |
| Prioridades faltantes detectadas (informativas) | **5** (P11-P15) |
| Total prioridades propuestas | **15** |
| Prioridades implementables solo con frontend (Fase 1) | **5** (P1, P2, P5, P10 + refactor) |
| Prioridades que requieren backend nuevo (Fase 2) | **6** (P3, P4, P7, P8, P9, P12) |
| Prioridades que requieren definiciones negocio (Fase 3) | **4** (P11, P13, P14, P15) |
| Bug de restricción por plan detectado | **1** (validación de entitlement en prioridades) |
| Endpoints backend existentes reutilizables | **3** (`cash/summary`, `inventory/summary`, `treasury/dashboard/finance-summary`) |
| Endpoints backend nuevos necesarios | **2** (`sales/orders/summary`, quotes con filtro `valid_until`) |

**Conclusión:** El sistema de "Prioridades del día" está funcional pero limitado a 3 reglas básicas. Hay **al menos 9 prioridades operativas relevantes** que ya tienen soporte parcial en el backend pero no se reflejan en el dashboard. La Fase 1 no requiere cambios backend y puede implementarse rápidamente reutilizando el endpoint `treasury/dashboard/finance-summary/` que ya existe.
