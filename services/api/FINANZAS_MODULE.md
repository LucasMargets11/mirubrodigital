# FINANZAS_MODULE.md

Módulo de Tesorería y Finanzas para Mirubro — documentación técnica interna.

---

## Índice

1. [Arquitectura general](#1-arquitectura-general)
2. [Modelos clave](#2-modelos-clave)
3. [Flujos principales](#3-flujos-principales)
4. [Reglas de VOID / Reversa](#4-reglas-de-void--reversa)
5. [Configuración de Tesorería](#5-configuración-de-tesorería)
6. [Paginación y filtros](#6-paginación-y-filtros)
7. [Endpoints disponibles](#7-endpoints-disponibles)
8. [Checklist de pruebas manuales](#8-checklist-de-pruebas-manuales)

---

## 1. Arquitectura general

```
services/api/src/apps/treasury/
  models.py          → Todos los modelos del dominio
  serializers.py     → DRF serializers con campos computados
  views.py           → ModelViewSets + custom @actions
  signals.py         → Auto-crea Transaction IN cuando se cierra una Venta
  urls.py            → Router registration
  migrations/        → Migraciones numeradas 0001 → 0003

apps/web/src/app/app/gestion/finanzas/
  layout.tsx          → Shell compartido con FinanceTabs + FinanceHeader
  components/
    header.tsx        → FinanceTabs (6 pestañas)
    currency.tsx      → <Currency amount /> formateado
    empty-state.tsx   → Estado vacío reutilizable
  resumen/            → Dashboard: saldos + próximos vencimientos
  movimientos/        → Listado paginado de transacciones
  gastos/             → Tabs Fijos | Puntuales
  sueldos/            → Empleados + historial de pagos
  reportes/           → Reporte mensual últimos 12 meses
  configuracion/      → Mapeo método de pago → cuenta

apps/web/src/lib/api/treasury.ts
  → Cliente tipado centralizado para todas las llamadas al backend
```

---

## 2. Modelos clave

### Account
Representa una cuenta de tesorería (caja, banco, MercadoPago, etc.).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `type` | `cash\|bank\|mercadopago\|card_float\|other` | Tipo de cuenta |
| `balance` | `@property` computado | Saldo actual (apertura + IN - OUT de transacciones POSTED) |
| `is_active` | bool | Cuentas inactivas no aceptan nuevas transacciones |

### Transaction
Movimiento monetario único, siempre ligado a una `Account`.

| Campo | Notas |
|-------|-------|
| `direction` | `IN` / `OUT` / `ADJUST` |
| `status` | `posted` (activo) o `voided` (anulado) |
| `transaction_type` | `sale`, `expense`, `fixed_expense`, `payroll`, `transfer`, `reconciliation`, `other` |
| `transfer_group_id` | UUID (string) — vincula par de transacciones de una transferencia interna |
| `reference_type` / `reference_id` | FK genérico al origen (Expense, FixedExpensePeriod, PayrollPayment, Sale) |

**Regla clave:** El saldo de una cuenta solo considera transacciones con `status=posted`.

### FixedExpense + FixedExpensePeriod
- `FixedExpense` = gasto recurrente (alquiler, salarios fijos, servicios).
- `FixedExpensePeriod` = instancia mensual auto-generada con `status: pending|paid|skipped`.
- Frecuencias: `weekly`, `monthly`, `quarterly`, `yearly`.
- El método `ensure_current_period()` crea el período activo si no existe.

### Expense
Gasto puntual no recurrente. `status: pending → paid` al pagar con cuenta.

### Employee + PayrollPayment
- `Employee.is_active` — inactivar en lugar de eliminar si tiene pagos.
- `PayrollPayment.status` — `paid` o `reverted`.
- Al crear un `PayrollPayment` se crea automáticamente una `Transaction OUT` en la cuenta seleccionada.

### TreasurySettings
Singleton por `Business`. Mapea método de pago → cuenta:

```
default_cash_account      → ventas en efectivo
default_bank_account      → ventas por transferencia bancaria
default_mercadopago_account → ventas QR / MP
default_card_account      → ventas con tarjeta
default_other_account     → otros medios
default_income_account    → ingresos manuales
default_expense_account   → egresos manuales
default_payroll_account   → sueldos (pre-selección en UI)
```

### Budget
Límite de gasto mensual por categoría.

```python
Budget(business, category, year, month, limit_amount)
# unique_together: (business, category, year, month)
# computed: spent = SUM(OUT transactions en ese mes/categoría)
# computed: percentage = spent / limit_amount * 100
```

---

## 3. Flujos principales

### 3.1 Venta → Ingreso automático (`signals.py`)

```
Sale.status → 'completed'
  └─ post_save signal → _resolve_account_for_sale(sale, settings)
        1. TreasurySettings.get_account_for_payment_method(sale.payment_method)
        2. Fallback: Account.objects.filter(business, type=tipo_inferido).first()
        3. Last resort: Account.objects.filter(business, type='cash').first()
  └─ Transaction.objects.create(direction='IN', status='posted', ...)
```

Si no existe ninguna cuenta configurada, el signal registra un `WARNING` pero no lanza excepción.

### 3.2 Transferencia interna

```
POST /api/v1/treasury/transactions/transfer/
{
  from_account, to_account, amount, description, occurred_at
}
  → Transaction OUT (from_account, description="<desc> → <to_name>")
  → Transaction IN  (to_account,   description="<desc> ← <from_name>")
  → ambas con el mismo transfer_group_id (UUID)
```

### 3.3 Pago de Gasto Puntual (Expense)

```
POST /api/v1/treasury/expenses/{id}/pay/
{ account_id, paid_at }
  → expense.status = 'paid'
  → Transaction OUT creada con reference_type='expense', reference_id=str(id)
```

### 3.4 Pago de Período de Gasto Fijo

```
POST /api/v1/treasury/fixed-expense-periods/{id}/pay/
{ account_id, amount, paid_at }
  → period.status = 'paid', period.amount = amount
  → Transaction OUT con reference_type='fixed_expense_period'
```

### 3.5 Pago de Sueldo

```
POST /api/v1/treasury/payroll-payments/
{ employee, amount, account, paid_at }
  → PayrollPayment.status = 'paid'
  → Transaction OUT con reference_type='payroll'
```

### 3.6 Reconciliación de Cuenta

```
POST /api/v1/treasury/accounts/{id}/reconcile/
{ real_balance }
  → Calcula diferencia con balance actual (solo transacciones posted)
  → Crea Transaction ADJUST con description='Ajuste de conciliación'
```

---

## 4. Reglas de VOID / Reversa

### Anular Transacción manual

```
POST /api/v1/treasury/transactions/{id}/void/
{ reason: "motivo" }
```

Efectos:
- `transaction.status = 'voided'` → el saldo ya no la cuenta.
- Si `reference_type == 'expense'` → `expense.status = 'pending'`, `expense.paid_at = None`.
- Si `reference_type == 'fixed_expense_period'` → `period.status = 'pending'`.
- Si `reference_type == 'payroll'` → `payroll_payment.status = 'reverted'`, `payroll_payment.transaction = None`.

### Revertir Pago de Sueldo

```
POST /api/v1/treasury/payroll-payments/{id}/revert/
{ reason: "motivo" }
```

Idéntico al VOID de una transacción de tipo `payroll`.

---

## 5. Configuración de Tesorería

Acceso en la UI: **Finanzas → Configuración**

No hay múltiples ajustes — hay un único `TreasurySettings` por negocio (singleton con `get_or_create`).

API:
```
GET    /api/v1/treasury/settings/
PATCH  /api/v1/treasury/settings/update/
```

Los campos FK son opcionales. Si no están configurados, el sistema usa el fallback por tipo de cuenta.

---

## 6. Paginación y filtros

Todas las listas devuelven `PaginatedResponse`:
```json
{ "count": 150, "results": [...] }
```

Parámetros comunes:
- `limit` (default: 50, max: 200)
- `offset` (default: 0)

### Transacciones (`/api/v1/treasury/transactions/`)
| Param | Descripción |
|-------|-------------|
| `account` | ID de cuenta |
| `direction` | `IN`, `OUT`, `ADJUST` |
| `category` | ID de categoría |
| `date_from` | Fecha desde (YYYY-MM-DD) |
| `date_to` | Fecha hasta (YYYY-MM-DD) |
| `status` | `posted`, `voided` |
| `search` | Búsqueda en descripción |

### Gastos Puntuales (`/api/v1/treasury/expenses/`)
| Param | Descripción |
|-------|-------------|
| `status` | `pending`, `paid`, `cancelled` |
| `category` | ID de categoría |
| `date_from` / `date_to` | Rango de `due_date` |

---

## 7. Endpoints disponibles

```
GET    /api/v1/treasury/accounts/                        Lista cuentas
POST   /api/v1/treasury/accounts/                        Crear cuenta
PATCH  /api/v1/treasury/accounts/{id}/                   Actualizar cuenta
POST   /api/v1/treasury/accounts/{id}/reconcile/         Conciliar

GET    /api/v1/treasury/categories/                      Lista categorías
POST   /api/v1/treasury/categories/                      Crear categoría

GET    /api/v1/treasury/transactions/                    Lista (paginada, filtrable)
POST   /api/v1/treasury/transactions/transfer/           Transferencia interna
POST   /api/v1/treasury/transactions/{id}/void/          Anular
GET    /api/v1/treasury/transactions/export-csv/         Exportar CSV
GET    /api/v1/treasury/transactions/monthly-report/     Reporte 12 meses

GET    /api/v1/treasury/expenses/                        Lista gastos puntuales
POST   /api/v1/treasury/expenses/                        Crear gasto
POST   /api/v1/treasury/expenses/{id}/pay/               Pagar

GET    /api/v1/treasury/employees/                       Lista empleados
POST   /api/v1/treasury/employees/                       Crear empleado
PATCH  /api/v1/treasury/employees/{id}/                  Editar (incl. is_active)

GET    /api/v1/treasury/payroll-payments/                Lista pagos de sueldo
POST   /api/v1/treasury/payroll-payments/                Crear pago
POST   /api/v1/treasury/payroll-payments/{id}/revert/    Revertir

GET    /api/v1/treasury/fixed-expenses/                  Lista gastos fijos
POST   /api/v1/treasury/fixed-expenses/                  Crear gasto fijo
PATCH  /api/v1/treasury/fixed-expenses/{id}/             Editar
POST   /api/v1/treasury/fixed-expenses/{id}/ensure-current/   Generar período actual
POST   /api/v1/treasury/fixed-expenses/{id}/generate-periods/ Generar N períodos futuros
POST   /api/v1/treasury/fixed-expenses/ensure-all-current/    Bulk: todos los gastos

GET    /api/v1/treasury/fixed-expense-periods/           Lista períodos
POST   /api/v1/treasury/fixed-expense-periods/{id}/pay/  Pagar período
POST   /api/v1/treasury/fixed-expense-periods/{id}/skip/ Saltar período

GET    /api/v1/treasury/settings/                        Obtener configuración
PATCH  /api/v1/treasury/settings/update/                 Guardar configuración

GET    /api/v1/treasury/budgets/                         Lista presupuestos
POST   /api/v1/treasury/budgets/                         Crear presupuesto
PATCH  /api/v1/treasury/budgets/{id}/                    Actualizar
DELETE /api/v1/treasury/budgets/{id}/                    Eliminar
```

---

## 8. Checklist de pruebas manuales

### Cuentas y Saldos
- [ ] Crear cuenta de tipo `cash`, `bank`, `mercadopago`
- [ ] El saldo inicial refleja `opening_balance`
- [ ] Crear transacción IN → saldo aumenta
- [ ] Crear transacción OUT → saldo disminuye
- [ ] Anular transacción → saldo vuelve al valor anterior

### Transferencias
- [ ] Transferir de Caja a Banco → Caja disminuye, Banco aumenta
- [ ] La descripción muestra "→ NombreCuenta" y "← NombreCuenta" correctamente (no IDs)
- [ ] Ambas aparecen con badge "Transf." en Movimientos

### Ventas → Señal automática
- [ ] Crear venta con pago en Efectivo → aparece IN en cuenta Efectivo
- [ ] Crear venta con MercadoPago → aparece IN en cuenta MP
- [ ] Crear venta con Tarjeta → aparece IN en cuenta Tarjeta
- [ ] Sin configuración de TreasurySettings → fallback a tipo de cuenta correcto

### Gastos Puntuales
- [ ] Crear gasto → aparece en pestaña «Puntuales» con estado pendiente
- [ ] Pagar gasto → status cambia a paid, balance de cuenta disminuye
- [ ] Dar de baja (cancelar) funciona

### Gastos Fijos
- [ ] Crear gasto fijo mensual → se genera período actual
- [ ] Pagar período → Transaction OUT creada, período en paid
- [ ] Saltar período → status skipped
- [ ] Generar períodos futuros funciona

### Sueldos
- [ ] Crear empleado
- [ ] Editar empleado (nombre, salario base)
- [ ] Desactivar empleado → aparece como Inactivo, no en lista de selección
- [ ] Registrar pago → Transaction OUT en cuenta seleccionada
- [ ] Revertir pago → Transaction anulada, saldo restituido, pago en "Revertido"

### Configuración
- [ ] Ir a Finanzas → Configuración
- [ ] Asignar cuentas a métodos de pago
- [ ] Guardar → próxima venta usa la cuenta configurada

### Reportes
- [ ] Ir a Finanzas → Reportes
- [ ] Se muestra tabla y gráfico de barras con últimos 12 meses
- [ ] Totales son correctos

### CSV Export
- [ ] En Movimientos, hacer click en "CSV"
- [ ] Se descarga archivo con los movimientos filtrados
