# Auditoría: Módulo Finanzas → Gastos

**Fecha:** 2026-02-11  
**Tech Lead:** Sistema de Auditoría  
**Objetivo:** Mapear estado actual antes de evolucionar a "Gastos Fijos con seguimiento mensual"

---

## 1. Estado Actual del Frontend

### Ubicación

- **Archivo principal:** `apps/web/src/app/app/gestion/finanzas/gastos/expenses-client.tsx`
- **Componente:** `ExpensesClient`

### Funcionalidad Actual

#### UI Layout

- **Tabs:** Pendientes / Pagados
- **Vista:** Grid de tarjetas (3 columnas en desktop)
- **Botón:** "Nuevo Gasto" abre modal

#### Modelo de Datos (Frontend)

```typescript
interface Expense {
  id: number;
  template_name?: string;
  category_name?: string; // ← Concepto actual: "Categoría"
  name: string;
  amount: string;
  due_date: string;
  status: "pending" | "paid" | "cancelled";
  paid_at?: string;
  paid_account?: number;
  category?: number;
  notes?: string;
}
```

#### Flujo de Creación

1. Usuario hace click en "Nuevo Gasto"
2. Modal solicita:
   - Descripción (name)
   - **Categoría** (select de TransactionCategory con direction='expense')
   - Monto
   - Fecha de vencimiento
3. Al crear: `POST /api/v1/treasury/expenses/`

#### Flujo de Pago

1. Click "Registrar Pago" en gasto pendiente
2. Modal solicita:
   - Cuenta desde la cual pagar
3. Llama: `POST /api/v1/treasury/expenses/{id}/pay/`
4. Actualiza queries: expenses, transactions, accounts

### Problemas Identificados

- ❌ **"Categoría"** se usa como etiqueta, no como entidad recurrente
- ❌ No hay concepto de "Gasto Fijo" (template real)
- ❌ No hay navegación por secciones/gastos fijos
- ❌ No se ve histórico mensual
- ❌ ExpenseTemplate existe en backend pero NO se usa en frontend

---

## 2. Estado Actual del Backend

### Modelos Existentes

#### `ExpenseTemplate` (YA EXISTE pero NO se usa)

**Ubicación:** `services/api/src/apps/treasury/models.py:75`

```python
class ExpenseTemplate(models.Model):
    business = ForeignKey(Business)
    name = CharField(max_length=255)
    category = ForeignKey(TransactionCategory, null=True)
    amount = DecimalField(max_digits=19, decimal_places=4)
    frequency = CharField  # 'monthly'
    due_day = PositiveSmallIntegerField  # 1-28
    start_date = DateField
    is_active = BooleanField(default=True)
```

**Problema:** Este modelo existe pero:

- No se genera automáticamente el expense del mes
- No tiene endpoint funcional de generación
- Frontend lo ignora completamente

#### `Expense` (Instancia actual de un gasto)

**Ubicación:** `services/api/src/apps/treasury/models.py:90`

```python
class Expense(models.Model):
    business = ForeignKey(Business)
    template = ForeignKey(ExpenseTemplate, null=True)  # ← FK existe pero no se usa
    name = CharField(max_length=255)
    category = ForeignKey(TransactionCategory, null=True)
    amount = DecimalField
    due_date = DateField
    status = CharField  # PENDING | PAID | CANCELLED

    # Cuando se paga:
    paid_at = DateTimeField(null=True)
    paid_account = ForeignKey(Account, null=True)
    payment_transaction = ForeignKey(Transaction, null=True)

    notes = TextField(null=True)
    created_at = DateTimeField(auto_now_add=True)
```

**Características:**

- ✅ Ya tiene estados (PENDING, PAID, CANCELLED)
- ✅ Ya guarda paid_account y paid_at
- ✅ Ya crea Transaction al pagar
- ❌ NO tiene campo de periodo mensual (year+month)
- ❌ FK a template no se usa

#### `Transaction` (Movimientos en el Ledger)

**Ubicación:** `services/api/src/apps/treasury/models.py:42`

```python
class Transaction(models.Model):
    business = ForeignKey(Business)
    account = ForeignKey(Account)
    direction = CharField  # IN | OUT | ADJUST
    amount = DecimalField
    occurred_at = DateTimeField
    category = ForeignKey(TransactionCategory, null=True)
    description = TextField
    status = CharField  # posted | voided

    # Referencia polimórfica
    reference_type = CharField(null=True)  # 'expense', 'payroll', 'sale'
    reference_id = CharField(null=True)

    transfer_group_id = UUIDField(null=True)
    created_by = ForeignKey(User, null=True)
```

**Características:**

- ✅ Ledger unificado YA implementado
- ✅ Al pagar gasto se crea Transaction con reference_type='expense'
- ✅ Serializer mejorado con transaction_type y reference_details

### Endpoints Actuales

**URL Base:** `/api/v1/treasury/`

| Endpoint                                 | Método | Funcionalidad                       |
| ---------------------------------------- | ------ | ----------------------------------- |
| `expenses/`                              | GET    | Lista todos los expenses            |
| `expenses/`                              | POST   | Crea expense (sin template)         |
| `expenses/{id}/pay/`                     | POST   | Paga expense → crea Transaction     |
| `expense-templates/`                     | GET    | Lista templates (no usado en front) |
| `expense-templates/`                     | POST   | Crea template                       |
| `expense-templates/{id}/generate-month/` | POST   | **NO IMPLEMENTADO** (501)           |

**Código ViewSet:**

```python
class ExpenseViewSet(BaseTreasuryViewSet):
    queryset = Expense.objects.all()

    def perform_create(self, serializer):
        # Valida amount > 0
        super().perform_create(serializer)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        # ✅ Idempotencia: no pagar 2 veces
        # ✅ Valida cuenta pertenece a business
        # ✅ Crea Transaction con reference_type='expense'
        # ✅ Actualiza expense: status=PAID, paid_at, paid_account
```

### Ledger / Movimientos

**Ubicación Frontend:** `apps/web/src/app/app/gestion/finanzas/movimientos/transactions-client.tsx`

- ✅ **Rediseño completo ya implementado** (cards con iconos)
- ✅ Muestra transferencias, gastos, sueldos, ventas, conciliaciones
- ✅ transaction_type automático en serializer
- ✅ reference_details trae nombre del gasto y fecha de vencimiento

**Serializer Enhancement:**

```python
class TransactionSerializer:
    def get_transaction_type(self, obj):
        if obj.reference_type == 'expense':
            return 'expense'
        # ... otros tipos

    def get_reference_details(self, obj):
        if obj.reference_type == 'expense':
            expense = Expense.objects.filter(id=obj.reference_id).first()
            return {'name': expense.name, 'due_date': expense.due_date}
```

---

## 3. Calculo de Saldo

### Modelo Account

```python
class Account(models.Model):
    opening_balance = DecimalField
    opening_balance_date = DateField(default=date.today)
```

### Cálculo (en AccountSerializer)

```python
def get_balance(self, obj):
    in_total = obj.transactions.filter(direction='IN').aggregate(Sum('amount'))['s'] or 0
    out_total = obj.transactions.filter(direction='OUT').aggregate(Sum('amount'))['s'] or 0
    return obj.opening_balance + in_total - out_total
```

**Regla:** Saldo = opening_balance + ingresos - egresos

---

## 4. Multi-tenant

- ✅ Todos los modelos tienen `business = ForeignKey(Business)`
- ✅ BaseTreasuryViewSet filtra por `request.business`
- ✅ Validaciones aseguran que Account/Expense pertenezcan al mismo business

---

## 5. Categorías vs Gastos Fijos

### Estado Actual

- **TransactionCategory:** Entidad para categorizar movimientos (Servicios, Sueldos, Proveedores...)
  - `direction`: 'income' | 'expense'
  - Se usa en CREAR GASTO como dropdown
  - También se usa en Transactions

- **ExpenseTemplate:** Modelo backend que SÍ representa "gasto fijo recurrente" **pero está inactivo**

### Problema Conceptual

1. Frontend usa "Categoría" como si fuera el concepto de "Gasto Fijo"
2. ExpenseTemplate existe pero:
   - No se usa en el frontend
   - No genera automáticamente los periodos mensuales
   - Endpoint de generación retorna 501

---

## 6. Decisiones de Diseño para Evolución

### A. Reutilizar ExpenseTemplate

**Decisión:** ✅ **Renombrar ExpenseTemplate → FixedExpense**

- Ya tiene los campos necesarios (name, amount, due_day, is_active)
- Solo requiere agregar lógica de generación automática de periodos

### B. Crear FixedExpensePeriod

**Decisión:** ✅ **Nuevo modelo**

```python
class FixedExpensePeriod(models.Model):
    fixed_expense = ForeignKey(FixedExpense)
    period = DateField  # Primer día del mes: YYYY-MM-01
    amount = DecimalField  # Default from fixed_expense.amount
    status = CharField  # PENDING | PAID | SKIPPED
    due_date = DateField  # Calculada from fixed_expense.due_day
    paid_at = DateTimeField(null=True)
    paid_account = ForeignKey(Account, null=True)
    payment_transaction = ForeignKey(Transaction, null=True)

    class Meta:
        unique_together = [['fixed_expense', 'period']]
```

### C. Deprecar Expense actual

**Decisión:** ✅ **Mantener Expense para gastos únicos/variables**

- FixedExpensePeriod → gastos fijos mensuales
- Expense → gastos variables/únicos (ej: reparación, compra especial)

### D. Migración de Categorías

**Decisión:** ✅ **TransactionCategory queda para Transaction**

- Frontend de Gastos deja de mostrar "Categoría" como concepto
- Los FixedExpense tienen nombre propio (Internet, Alquiler...)
- TransactionCategory se usa solo en el ledger/movimientos

---

## 7. Plan de Implementación

### Backend (Prioridad 1)

1. ✅ Renombrar ExpenseTemplate → FixedExpense (migración)
2. ✅ Crear modelo FixedExpensePeriod
3. ✅ Serializers para FixedExpense y FixedExpensePeriod
4. ✅ ViewSet FixedExpenseViewSet con endpoints:
   - GET/POST/PATCH/DELETE fixed-expenses/
   - GET fixed-expenses/{id}/periods/
   - POST fixed-expenses/{id}/periods/ensure-current/
5. ✅ ViewSet FixedExpensePeriodViewSet:
   - POST periods/{id}/pay/ (crea Transaction)
6. ✅ Lógica auto-generación periodos

### Frontend (Prioridad 2)

1. ✅ Nuevo componente `FixedExpensesClient`
2. ✅ Layout: Panel izquierdo (lista) + Panel derecho (detalle/histórico)
3. ✅ Modal "Nuevo Gasto Fijo" (name, amount, due_day)
4. ✅ Modal "Pagar" (account, paid_at, amount override)
5. ✅ Indicadores visuales (✅ Pago / ⚠️ Pendiente)

### Ledger (Ya implementado)

- ✅ Transaction.reference_type ya soporta 'expense'
- ✅ Serializer devuelve transaction_type y reference_details
- ⚠️ Actualizar reference_details para FixedExpensePeriod

---

## 8. Puntos Críticos de Validación

### Idempotencia

- ✅ No permitir pagar dos veces el mismo FixedExpensePeriod
- ✅ Check: `if period.status == PAID: return error`

### Multi-tenant

- ✅ Validar fixed_expense.business == request.business
- ✅ Validar paid_account.business == period.fixed_expense.business

### Integridad

- ✅ unique_together en (fixed_expense, period)
- ✅ Transaction apunta a FixedExpensePeriod via reference_type='fixed_expense_period'

---

## 9. Criterios de Éxito

### Backend

- [ ] Modelo FixedExpense con campos correctos
- [ ] Modelo FixedExpensePeriod con unique_together
- [ ] Endpoint `POST periods/{id}/pay/` crea Transaction
- [ ] Auto-generación de periodo actual al consultar fixed-expense
- [ ] Validaciones de multi-tenant y idempotencia

### Frontend

- [ ] UI de Gastos Fijos (lista + detalle)
- [ ] Histórico por meses visible
- [ ] Indicador claro de estado del mes actual
- [ ] Modal de pago funcional
- [ ] Integración con ledger (movimientos se ven)

### Integración

- [ ] Al pagar → aparece en Movimientos
- [ ] Saldo de cuenta se actualiza
- [ ] No se rompe nada existente

---

## 10. Archivos Clave a Modificar

### Backend

- `services/api/src/apps/treasury/models.py` - Nuevos modelos
- `services/api/src/apps/treasury/serializers.py` - Serializers
- `services/api/src/apps/treasury/views.py` - ViewSets
- `services/api/src/apps/treasury/urls.py` - Rutas
- `services/api/src/apps/treasury/migrations/` - Nueva migración
- `services/api/src/apps/accounts/management/commands/seed_demo.py` - Seed

### Frontend

- `apps/web/src/app/app/gestion/finanzas/gastos/expenses-client.tsx` - Reescribir completamente
- `apps/web/src/lib/api/treasury.ts` - Agregar funciones API

---

## Conclusión

**Estado Actual:**

- ✅ Ledger unificado funcional
- ✅ Transaction con reference_type='expense'
- ✅ Expense.pay() crea Transaction correctamente
- ⚠️ ExpenseTemplate existe pero NO se usa
- ❌ No hay concepto de "periodo mensual"
- ❌ No hay UI de gastos fijos

**Próximos Pasos:**

1. Implementar modelos FixedExpense y FixedExpensePeriod
2. Crear endpoints con auto-generación
3. Reescribir frontend con navegación por gastos fijos
4. Mantener Expense para gastos variables (opcional)

**Riesgo Bajo:**

- No afecta funcionalidad existente
- Ledger ya preparado para reference_type flexible
- Multi-tenant y validaciones ya implementadas
