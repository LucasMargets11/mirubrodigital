# Implementación de Ordenamiento (Sortable Headers)

## ✅ Módulos Compartidos Creados

### 1. Hook `useTableSort`

**Ubicación:** `src/lib/table/useTableSort.ts`

**Características:**

- Manejo de estado de ordenamiento (sortKey, sortDir)
- Persistencia en URL con query params (`?ordering=field` o `?ordering=-field`)
- Toggle ASC → DESC → ASC
- Soporte para server-side y client-side sorting
- Helper `sortArray()` para ordenamiento client-side con tipos: string, number, date, boolean
- Nulls last por defecto
- Custom comparators para casos especiales (ej: Estado con ranking)

**Uso:**

```typescript
const { sortKey, sortDir, onToggleSort } = useTableSort({
  defaultSortKey: "name",
  defaultSortDir: "asc",
  persistInUrl: true,
});
```

### 2. Componente `SortableHeader`

**Ubicación:** `src/components/ui/sortable-header.tsx`

**Características:**

- Componente reutilizable para headers de tabla
- Ícono de flecha (↑/↓) con estado visual
- `aria-sort` para accesibilidad
- Cursor pointer y hover effects
- Soporte para columnas no ordenables (sin sortKey)

**Uso:**

```tsx
<SortableHeader
  label="Producto"
  sortKey="name"
  activeSortKey={sortKey}
  sortDir={sortDir}
  onToggleSort={onToggleSort}
/>
```

## ✅ Listados Actualizados

### 1. Productos (`apps/web/src/app/app/gestion/productos/products-client.tsx`)

**Columnas ordenables:**

- ✅ Producto (nombre) - string
- ✅ SKU - string
- ✅ Precio - number
- ✅ Stock min. - number
- ✅ Estado (is_active) - boolean

**Tipo:** Client-side sorting (no paginado)
**URL:** Persiste en `?ordering=`

### 2. Stock (`apps/web/src/app/app/gestion/stock/stock-client.tsx`)

**DOS tablas implementadas:**

**A) Niveles de Stock:**

- ✅ Producto - string
- ✅ Cantidad - number
- ✅ Stock mínimo - number
- ✅ Estado (ok/low/out) - custom comparator con ranking

**B) Movimientos:**

- ✅ Fecha - date
- ✅ Producto - string
- ✅ Tipo (IN/OUT/ADJUST/WASTE) - string
- ✅ Cantidad - number

**Tipo:** Client-side sorting (no paginado)
**URL:** Movimientos persisten en URL, Stock no (evitar conflicto)

## 🔄 Listados Pendientes de Actualizar

### Alta Prioridad (Uso frecuente):

1. **Ventas** (`apps/web/src/app/app/gestion/ventas/sales-client.tsx`)
   - Fecha, Total, Estado, Número

2. **Clientes** (`apps/web/src/app/app/gestion/clientes/ customers-client.tsx`)
   - Nombre, Última compra, Total gastado

3. **Facturas** (`apps/web/src/app/app/gestion/facturas/invoices-client.tsx`)
   - Fecha, Número, Cliente, Total, Estado

### Media Prioridad:

4. **Reportes - Ventas** (`apps/web/src/app/app/gestion/reportes/ventas/sales-client.tsx`)
5. **Reportes - Products** (`apps/web/src/app/app/gestion/reportes/productos/products-client.tsx`)
6. **Reportes - Pagos** (`apps/web/src/app/app/gestion/reportes/pagos/payments-client.tsx`)
7. **Stock - Valorización** (`apps/web/src/app/app/gestion/stock/valuation-client.tsx`)

### Baja Prioridad:

8. **Finanzas - Gastos** (`apps/web/src/app/app/gestion/finanzas/gastos/expenses-client.tsx`)
9. **Finanzas - Movimientos** (`apps/web/src/app/app/gestion/finanzas/movimientos/transactions-client.tsx`)
10. **Finanzas - Cuentas** (`apps/web/src/app/app/gestion/finanzas/cuentas/accounts-client.tsx`)

### Casos Especiales:

11. **AccountsTable** (`src/components/app/owner-access/accounts-table.tsx`)
    - Usuario, Rol, Estado, Último acceso

## 🔧 Patrón de Implementación

Para cada listado, seguir este patrón:

```typescript
// 1. Importar dependencias
import { SortableHeader } from '@/components/ui/sortable-header';
import { useTableSort, sortArray, type ColumnConfig } from '@/lib/table/useTableSort';

// 2. Definir columnas (dentro del componente)
const columnConfigs: Record<string, ColumnConfig<TipoItem>> = useMemo(() => ({
    campo1: { accessor: 'campo1', sortType: 'string' },
    campo2: { accessor: 'campo2', sortType: 'number' },
    campoNested: { accessor: (item) => item.nested.value, sortType: 'string' },
    campoCustom: {
        accessor: 'status',
        customComparator: (a, b) => {
            const order = { pending: 0, active: 1, done: 2 };
            return order[a.status] - order[b.status];
        },
    },
}), []);

// 3. Hook de ordenamiento
const { sortKey, sortDir, onToggleSort } = useTableSort({
    defaultSortKey: 'created_at',
    defaultSortDir: 'desc',
    persistInUrl: true,
});

// 4. Aplicar ordenamiento
const sortedItems = useMemo(() => {
    return sortArray(items, sortKey, sortDir, columnConfigs);
}, [items, sortKey, sortDir, columnConfigs]);

// 5. En el JSX
<thead>
    <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
        <SortableHeader
            label="Campo 1"
            sortKey="campo1"
            activeSortKey={sortKey}
            sortDir={sortDir}
            onToggleSort={onToggleSort}
        />
        {/* Header sin ordenamiento */}
        <th className="px-3 py-2">Acciones</th>
    </tr>
</thead>
<tbody>
    {sortedItems.map(item => ...)}
</tbody>
```

## 🎯 Criterios de Aceptación

- [x] Hook `useTableSort` creado y documentado
- [x] Componente `SortableHeader` creado
- [x] Productos: 5 columnas ordenables
- [x] Stock: 2 tablas con 4 y 5 columnas ordenables
- [ ] Ventas: Mínimo 4 columnas ordenables
- [ ] Clientes: Mínimo 3 columnas ordenables
- [ ] Facturas: Mínimo 5 columnas ordenables
- [ ] Mantiene ordenamiento al recargar (URL)
- [ ] Estados ordenan con ranking (no alfabéticamente)
- [ ] No rompe paginación ni filtros existentes

## 📋 Backend (Pendiente)

Para listados paginados o grandes volúmenes, implementar server-side ordering:

1. **Django DRF OrderingFilter:**

```python
from rest_framework.filters import OrderingFilter

class ProductViewSet:
    filter_backends = [OrderingFilter]
    ordering_fields = ['name', 'sku', 'price', 'stock_min', 'is_active']
    ordering = ['name']  # Default
```

2. **Para campos calculados (ej: Estado):**

```python
def get_queryset(self):
    qs = super().get_queryset()
    qs = qs.annotate(
        status_rank=Case(
            When(quantity=0, then=Value(0)),  # Sin stock
            When(quantity__lte=F('stock_min'), then=Value(1)),  # Bajo
            default=Value(2),  # OK
        )
    )
    return qs

ordering_fields = [..., 'status_rank']
```

## 📝 Notas Técnicas

- **Client-side vs Server-side:** Actualmente todos los listados traen datos completos sin paginación, por lo que client-side sorting es apropiado.
- **Performance:** `sortArray()` usa spread operator (`[...array]`) para no mutar el original y mantiene estabilidad del sort.
- **Accesibilidad:** Todos los headers tienen `aria-sort` y son navegables por teclado (onClick funciona con Enter/Space).
- **URL Persistence:** Se usa formato DRF-style `?ordering=field` y `?ordering=-field` para consistencia con backend futuro.
- **Multiple Sorts:** No implementado (Shift+Click para multi-sort). Se puede agregar si se requiere.

## 🔄 Próximos Pasos

1. Aplicar patrón a Ventas (alta prioridad)
2. Aplicar a Clientes y Facturas
3. Continuar con reportes
4. Implementar backend ordering si hay endpoints paginados
5. Testing completo de todos los listados actualizados
