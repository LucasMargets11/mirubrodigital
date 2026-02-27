# Stock Replenishment MVP

Módulo para registrar compras a proveedor con impacto atómico en stock y finanzas.

---

## Modelos Django

### `inventory.StockReplenishment`

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | Auto |
| `business` | FK Business | |
| `occurred_at` | DateTimeField | Fecha/hora de la compra |
| `supplier_name` | CharField(255) | Nombre del proveedor |
| `invoice_number` | CharField(100) | Nullable |
| `notes` | TextField | Nullable |
| `total_amount` | Decimal(19,4) | Calculado = Σ qty × unit_cost |
| `status` | CharField | `posted` / `voided` |
| `account` | FK treasury.Account | Cuenta debitada |
| `transaction` | OneToOneField treasury.Transaction | Nullable, SET_NULL |
| `purchase_category` | FK treasury.TransactionCategory | Nullable |
| `created_by` | FK AUTH_USER | Nullable |
| `created_at` | DateTimeField | Auto |

### Extensiones en `inventory.StockMovement`

- `unit_cost`: Decimal(19,4) nullable — costo unitario si viene de una reposición
- `replenishment`: FK nullable → `StockReplenishment` — backlink de trazabilidad

---

## Endpoints

Base URL: `/api/gestion/inventory/`

### `GET /replenishments/`
Lista paginada. Requiere `view_purchases`.

**Query params:** `date_from`, `date_to`, `search` (supplier_name / invoice_number), `account_id`

**Response 200:**
```json
[
  {
    "id": "uuid",
    "occurred_at": "2024-01-15T10:00:00Z",
    "supplier_name": "Proveedor SA",
    "invoice_number": "FC-001",
    "account_id": "uuid",
    "account_name": "Caja Principal",
    "total_amount": "1500.0000",
    "status": "posted",
    "transaction_id": "uuid",
    "created_at": "2024-01-15T10:05:00Z"
  }
]
```

### `POST /replenishments/`
Crea reposición atómica. Requiere `manage_purchases`.

**Body:**
```json
{
  "account_id": "uuid",
  "purchase_category_id": "uuid (opcional)",
  "supplier_name": "Proveedor SA",
  "invoice_number": "FC-001",
  "occurred_at": "2024-01-15T10:00:00Z",
  "notes": "Compra quincenal",
  "items": [
    { "product_id": "uuid", "quantity": 10, "unit_cost": "150.0000" }
  ]
}
```

**Response 201:** `StockReplenishmentDetailSerializer` (ver GET detail)

### `GET /replenishments/{id}/`
Detalle con items y transacción. Requiere `view_purchases`.

**Response 200:**
```json
{
  "id": "uuid",
  "occurred_at": "...",
  "supplier_name": "Proveedor SA",
  "invoice_number": "FC-001",
  "notes": null,
  "total_amount": "1500.0000",
  "status": "posted",
  "account_id": "uuid",
  "account_name": "Caja Principal",
  "purchase_category_id": null,
  "purchase_category_name": null,
  "created_at": "...",
  "transaction": {
    "id": "uuid",
    "amount": "1500.0000",
    "account_id": "uuid",
    "account_name": "Caja Principal",
    "status": "posted"
  },
  "items": [
    {
      "id": "uuid",
      "product_id": "uuid",
      "product_name": "Harina",
      "product_sku": "HAR-001",
      "movement_type": "IN",
      "quantity": "10.0000",
      "unit_cost": "150.0000",
      "line_total": "1500.0000",
      "reason": "replenishment"
    }
  ]
}
```

### `POST /replenishments/{id}/void/`
Anula la reposición. Requiere `manage_purchases`.

**Body:**
```json
{ "reason": "Error de carga" }
```

**Response 200:** `StockReplenishmentDetailSerializer` con `status: "voided"`

---

## Lógica Atómica — `create_stock_replenishment()`

```
BEGIN TRANSACTION
  1. Validar account.business == replenishment.business
  2. Obtener o crear TransactionCategory 'Compra / Reposición de Stock'
  3. Calcular total_amount = Σ (item.quantity × item.unit_cost)  
  4. Crear StockReplenishment (status=posted, transaction=null)
  5. Para cada item:
     a. ensure_stock_record(business, product)
     b. register_stock_movement(..., type=IN, reason='replenishment', unit_cost=...)
     c. Linkar movement.replenishment = replenishment
  6. Crear Transaction (type=EXPENSE, amount=-total, reference=StockReplenishment)
  7. replenishment.transaction = transaction
  8. replenishment.save()
COMMIT
```

---

## Lógica de Anulación — `void_stock_replenishment()`

- **Idempotente**: si `status == 'voided'` retorna sin cambios
- Actualiza `transaction.status = 'voided'` vía `UPDATE` directo
- Crea movimientos OUT compensatorios (`reason='replenishment_void'`) por cada movimiento IN original
- Actualiza `replenishment.status = 'voided'`

---

## RBAC

| Permiso | Módulo | Descripción |
|---|---|---|
| `view_purchases` | Stock | Ver listado y detalle de reposiciones |
| `manage_purchases` | Stock | Crear y anular reposiciones |

### Asignación por rol (servicio `gestion`)

| Rol | view_purchases | manage_purchases |
|---|---|---|
| owner | ✅ | ✅ |
| admin | ✅ | ✅ |
| manager | ✅ | ✅ |
| staff | ✅ | ❌ |
| viewer | ✅ | ❌ |
| analyst | ✅ | ❌ |
| cashier | ❌ | ❌ |

---

## Frontend — Rutas

| Ruta | Componente | Permiso |
|---|---|---|
| `/app/gestion/stock/compras` | `compras/page.tsx` + `compras-client.tsx` | `view_purchases` |
| `/app/gestion/stock/compras/[id]` | `compras/[id]/page.tsx` + `replenishment-detail-client.tsx` | `view_purchases` |
| `/app/gestion/stock/reponer` | `reponer/page.tsx` + `reponer-client.tsx` | `manage_purchases` |

### CTA en Stock principal
Botón "Reponer stock" aparece en `/app/gestion/stock` cuando `manage_purchases == true`.

### Trazabilidad en Finanzas
En `/app/gestion/finanzas/movimientos`, las transacciones con `reference_type == 'stock_replenishment'` muestran:
- Icono naranja `ShoppingCart`
- Chip "Reposición Stock"
- Link "Ver reposición" → `/app/gestion/stock/compras/{id}`

---

## Checklist de Prueba Manual

### Creación
- [ ] Crear reposición con 2 productos → stock aumenta en ambos
- [ ] Total en `Transaction` = Σ qty × unit_cost
- [ ] `Transaction.reference_type = 'stock_replenishment'`
- [ ] Link aparece en finanzas con chip naranja
- [ ] `StockMovement.replenishment_id` apunta a la reposición

### Anulación
- [ ] Anular → status cambia a `voided`
- [ ] Stock disminuye (movimientos OUT compensatorios)
- [ ] `Transaction.status = 'voided'`
- [ ] Anular dos veces → idempotente (no duplica reversas)

### Permisos
- [ ] `viewer` puede ver lista pero no crear/anular
- [ ] `cashier` recibe 403 en todos los endpoints
- [ ] Sin autenticación recibe 401

### Edge Cases
- [ ] Producto duplicado en items → error 400
- [ ] Cuenta de otro negocio → error 400
- [ ] Costo negativo → error 400
- [ ] Cantidad 0 → error 400
