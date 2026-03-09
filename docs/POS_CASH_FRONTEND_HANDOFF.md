# POS Cash — Frontend Handoff

> Versión: 1.0 · Fecha: 2026-03-09  
> Base URL: `/api/v1/pos/` (prefijo del router POS operative)  
> Autenticación: `X-Employee-Token: <employee_jwt>` (obligatorio en todos los endpoints)

---

## Resumen de endpoints

| Método | Ruta | Acción |
|--------|------|--------|
| `POST` | `/api/v1/pos/cash/open/` | Abrir nueva sesión de caja |
| `GET` | `/api/v1/pos/cash/current/` | Consultar sesión abierta |
| `POST` | `/api/v1/pos/cash/current/close/` | Cerrar sesión abierta |
| `POST` | `/api/v1/pos/cash/current/movements/` | Registrar movimiento de caja |

---

## 1. Capability guard: cuándo mostrar los controles de caja

Antes de renderizar el componente de caja, consultá `GET /api/v1/pos/capabilities/` y verificá:

```json
{
  "can_open_cash": true,
  "can_close_cash": true,
  "can_register_cash_movement": true
}
```

- **Cashier** y **Manager Operativo** tienen estas 3 capabilities.
- **Server**, **Kitchen**, **Delivery** no las tienen → ocultar la sección de caja completamente.

---

## 2. POST `/api/v1/pos/cash/open/`

### Request body (todos opcionales)

```json
{
  "opening_cash_amount": "500.00",
  "register_id": "uuid-de-la-caja-fisica"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `opening_cash_amount` | string (decimal) | No | Efectivo inicial. Default `"0.00"`. Mínimo `"0"`. |
| `register_id` | UUID | No | Caja física. Si se omite, la sesión queda sin caja asignada. |

### Response 201 — sesión creada

```json
{
  "id": "a1b2c3d4-...",
  "status": "OPEN",
  "opening_cash_amount": "500.00",
  "closing_cash_counted": null,
  "expected_cash_total": null,
  "difference_amount": null,
  "closing_note": "",
  "opened_by_name": "Lucia Gomez",
  "opened_at": "2026-03-09T12:00:00Z",
  "closed_at": null,
  "opened_by_employee": {
    "id": "uuid",
    "employee_code": "EMP-001",
    "display_name": "Lucia Gomez"
  },
  "totals": {
    "total_sales": "0.00",
    "total_in": "0.00",
    "total_out": "0.00",
    "cash_expected_total": "500.00",
    "cash_in_from_sales": "0.00"
  }
}
```

### Errores

| Status | `detail` | Qué hacer |
|--------|----------|-----------|
| `400` | `"Ya tenés una sesión de caja abierta..."` | Ir a `current/` en lugar de abrir nueva |
| `400` | `"Esta caja física ya tiene una sesión abierta."` | Elegir otra caja o continuar sin asignar |
| `400` | `"No encontramos la caja seleccionada..."` | El `register_id` no existe en este negocio |
| `403` | `"Capability 'can_open_cash' required."` | El rol no tiene permiso; ocultar el botón |
| `403` | `"Debés cambiar tu PIN antes de operar."` | Redirigir a pantalla de cambio de PIN |
| `401` | — | Token expirado o inválido; redirigir al login POS |

---

## 3. GET `/api/v1/pos/cash/current/`

Sin request body.

### Response 200 — hay sesión abierta

```json
{
  "session": {
    "id": "a1b2c3d4-...",
    "status": "OPEN",
    "opening_cash_amount": "500.00",
    "closing_cash_counted": null,
    "expected_cash_total": null,
    "difference_amount": null,
    "closing_note": "",
    "opened_by_name": "Lucia Gomez",
    "opened_at": "2026-03-09T12:00:00Z",
    "closed_at": null,
    "opened_by_employee": { ... },
    "totals": {
      "total_sales": "1200.00",
      "total_in": "200.00",
      "total_out": "50.00",
      "cash_expected_total": "1850.00",
      "cash_in_from_sales": "1200.00"
    }
  }
}
```

### Response 200 — sin sesión abierta

```json
{ "session": null }
```

> La sesión es **específica del empleado autenticado**. Un cashier no ve la sesión de otro cashier.

### Errores

| Status | Causa |
|--------|-------|
| `401` | Token expirado o inválido |

---

## 4. POST `/api/v1/pos/cash/current/close/`

### Request body (todos opcionales)

```json
{
  "closing_cash_counted": "1850.00",
  "closing_note": "Todo en orden"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `closing_cash_counted` | string (decimal) | No | Efectivo físico contado al cierre. Si se omite, `difference_amount` queda null. |
| `closing_note` | string | No | Nota libre. Default `""`. |

### Response 200 — sesión cerrada

```json
{
  "id": "a1b2c3d4-...",
  "status": "CLOSED",
  "opening_cash_amount": "500.00",
  "closing_cash_counted": "1850.00",
  "expected_cash_total": "1850.00",
  "difference_amount": "0.00",
  "closing_note": "Todo en orden",
  "opened_at": "2026-03-09T12:00:00Z",
  "closed_at": "2026-03-09T20:00:00Z",
  "opened_by_employee": { ... },
  "totals": { ... }
}
```

### Errores

| Status | `detail` | Qué hacer |
|--------|----------|-----------|
| `400` | `"No hay una sesión de caja abierta para cerrar."` | Ir a pantalla principal, no hay sesión |
| `403` | `"Capability 'can_close_cash' required."` | El rol no puede cerrar cajas |
| `403` | `"Debés cambiar tu PIN antes de operar."` | Redirigir a cambio de PIN |
| `401` | — | Redirect a login |

---

## 5. POST `/api/v1/pos/cash/current/movements/`

### Request body

```json
{
  "movement_type": "IN",
  "category": "CASH_ADJUSTMENT",
  "method": "CASH",
  "amount": "200.00",
  "note": "Cambio adicional"
}
```

| Campo | Tipo | Requerido | Valores posibles |
|-------|------|-----------|------------------|
| `movement_type` | string | **Sí** | `IN` · `OUT` |
| `category` | string | No (default `OTHER`) | `CASH_ADJUSTMENT` · `PETTY_CASH` · `BANK_DEPOSIT` · `SUPPLIER_PAYMENT` · `OTHER` |
| `method` | string | No (default `CASH`) | `CASH` · `CARD` · `TRANSFER` · `QR` · `OTHER` |
| `amount` | string (decimal) | **Sí** | Mínimo `"0.01"` |
| `note` | string | No | Descripción libre |

### Response 201 — movimiento registrado

```json
{
  "id": "uuid",
  "movement_type": "IN",
  "category": "CASH_ADJUSTMENT",
  "method": "CASH",
  "amount": "200.00",
  "note": "Cambio adicional",
  "created_at": "2026-03-09T14:30:00Z"
}
```

### Errores

| Status | `detail` | Qué hacer |
|--------|----------|-----------|
| `400` | `"No hay una sesión de caja abierta..."` | Abrir caja primero |
| `400` | amount `"Ensure this value is greater than or equal to 0.01."` | Validar input antes de enviar |
| `400` | movement_type `"\"FOO\" is not a valid choice."` | Bug en el frontend, verificar los valores |
| `403` | `"Capability 'can_register_cash_movement' required."` | El rol no puede registrar movimientos |
| `401` | — | Redirect a login |

---

## 6. Objeto `totals` — referencia

Incluido en todas las respuestas de sesión (`open`, `current`, `close`).

```ts
interface CashSessionTotals {
  total_sales: string;         // Suma de todas las ventas en la sesión
  total_in: string;            // Suma de movimientos IN (sin ventas)
  total_out: string;           // Suma de movimientos OUT
  cash_expected_total: string; // opening_cash_amount + cash_in_from_sales + total_in - total_out
  cash_in_from_sales: string;  // Ventas cobradas en efectivo
}
```

---

## 7. Flujo de integración recomendado para `/app/pos/terminal`

```
1. Al montar la pantalla:
   a. GET /api/v1/pos/capabilities/
      → almacenar { can_open_cash, can_close_cash, can_register_cash_movement }
   b. GET /api/v1/pos/cash/current/
      → if session != null → mostrar UI con sesión activa
      → if session == null && can_open_cash → mostrar botón "Abrir Caja"
      → if session == null && !can_open_cash → ocultar sección de caja

2. Abrir caja (botón "Abrir Caja"):
   → Mostrar modal con campo de efectivo inicial (opcional)
   → POST /api/v1/pos/cash/open/
   → On 201: guardar session en estado local, mostrar resumen
   → On 400 "ya existe sesión": hacer GET /current/ y mostrarla

3. Durante la sesión:
   → Refrescar GET /current/ periódicamente (o al volver a la pantalla) para actualizar totals
   → Registrar movimiento: modal → POST /current/movements/
   → Recargar GET /current/ al completar el movimiento

4. Cerrar caja (botón "Cerrar Caja"):
   → Mostrar modal con: totals.cash_expected_total como referencia, campo "efectivo contado" (opcional), notas
   → POST /current/close/
   → On 200: limpiar estado de sesión, mostrar resumen de cierre (diferencia)
   → Redirigir a pantalla de fin de turno o logout

5. Manejo de errores comunes:
   → 401 en cualquier endpoint → redirect a /pos/login
   → 403 (capability) → toast de error, ocultar acciones no permitidas
   → 403 (must_change_pin) → redirect a /pos/change-pin
```

---

## 8. TypeScript interfaces (sugeridas)

```ts
interface PosEmployeeSummary {
  id: string;
  employee_code: string;
  display_name: string;
}

interface CashSessionTotals {
  total_sales: string;
  total_in: string;
  total_out: string;
  cash_expected_total: string;
  cash_in_from_sales: string;
}

interface CashSession {
  id: string;
  status: 'OPEN' | 'CLOSED' | 'FORCE_CLOSED';
  opening_cash_amount: string;
  closing_cash_counted: string | null;
  expected_cash_total: string | null;
  difference_amount: string | null;
  closing_note: string;
  opened_by_name: string;
  opened_at: string;  // ISO 8601
  closed_at: string | null;
  opened_by_employee: PosEmployeeSummary | null;
  totals: CashSessionTotals;
}

interface CashMovement {
  id: string;
  movement_type: 'IN' | 'OUT';
  category: 'CASH_ADJUSTMENT' | 'PETTY_CASH' | 'BANK_DEPOSIT' | 'SUPPLIER_PAYMENT' | 'OTHER';
  method: 'CASH' | 'CARD' | 'TRANSFER' | 'QR' | 'OTHER';
  amount: string;
  note: string;
  created_at: string;
}
```

---

## 9. Notas de implementación

- El `session.id` devuelto al abrir es el que debés usar como referencia para mostrar el estado de caja. No es necesario pasarlo en requests posteriores — los endpoints `current/` y `current/close/` y `current/movements/` identifican la sesión a partir del token del empleado autenticado.
- `difference_amount` puede ser negativo (faltante) o positivo (sobrante). Mostrarlo con color según signo.
- `totals.cash_expected_total` es el valor de referencia para el conteo físico al cierre.
- La sesión es exclusiva por empleado — si un cashier tiene una sesión abierta y otro cashier inicia sesión, cada uno ve solo la suya propia.
