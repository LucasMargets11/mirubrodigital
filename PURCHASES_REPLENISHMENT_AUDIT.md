# Auditoría: Compras de Mercadería / Reposición de Stock
**Fecha:** 2026-02-23  
**Alcance:** Gestión Comercial — integración Inventario ↔ Finanzas  
**Método:** Inspección directa del repositorio (modelos, serializers, servicios, señales, rutas, UI)

---

## Tabla de Contenidos

1. [Mapa Actual del Sistema](#1-mapa-actual-del-sistema)
2. [Hallazgos por Área](#2-hallazgos-por-área)
3. [Respuestas a las Preguntas Clave](#3-respuestas-a-las-preguntas-clave)
4. [Gaps Priorizados](#4-gaps-priorizados)
5. [Propuesta MVP](#5-propuesta-mvp-rápida)
6. [Propuesta Ideal (Módulo Completo)](#6-propuesta-ideal-módulo-completo)
7. [Checklist de Pruebas Manuales](#7-checklist-de-pruebas-manuales)

---

## 1. Mapa Actual del Sistema

### 1.1 Backend — Modelos

| App | Modelo | Campos clave relevantes | Observaciones |
|-----|--------|------------------------|---------------|
| `inventory` | `StockMovement` | `business`, `product`, `movement_type` (IN/OUT/ADJUST/WASTE), `quantity`, `note`, `reason`, `metadata` (JSONField), `created_by` | **Falta**: `unit_cost`, `cost_total`, `reference_type`, `reference_id`, `supplier` |
| `inventory` | `ProductStock` | `business`, `product`, `quantity` | Snapshot del stock actual. No tiene costo |
| `inventory` | `InventoryImportJob` | CSV masivo de ajuste de stock | No impacta finanzas |
| `catalog` | `Product` | `cost` (Decimal, estático), `price`, `category`, `sku`, `barcode`, `stock_min` | `cost` se edita manualmente desde UI de producto |
| `catalog` | `ProductCategory` | `name`, `business` | Categoriza productos para reportes |
| `treasury` | `Account` | `type` (cash/bank/mercadopago/card_float/other), `name`, `currency`, `opening_balance` | Representa cuentas reales |
| `treasury` | `Transaction` | `direction` (IN/OUT/ADJUST), `amount`, `account`, `category`, `reference_type`, `reference_id`, `occurred_at`, `status` (posted/voided) | Tiene campos de referencia polimórfica listos para usar |
| `treasury` | `TransactionCategory` | `direction` (income/expense), `name` | Categoría "Proveedores" presente en datos demo |
| `treasury` | `Expense` | `paid_account`, `payment_transaction`, `attachment` | Gasto operativo general. No relacionado con stock |
| `treasury` | `TreasurySettings` | Mapeo método-de-pago → cuenta | Solo cubre ventas |
| `cash` | `CashMovement` | `movement_type` (in/out), `category` (expense/withdraw/deposit/other), `session` | Ligado a sesión de caja; no genera `Transaction` treasury |

> **No existe** ningún modelo llamado `Purchase`, `PurchaseOrder`, `StockReplenishment`, `Supplier`, `Vendor` o equivalente en todo el codebase.

---

### 1.2 Backend — Endpoints de Inventario

**Base:** `api/v1/inventory/`

| Método | Path | Permiso | Descripción |
|--------|------|---------|-------------|
| GET | `stock/` | `view_stock` | Listar niveles de stock con filtros |
| GET | `low-stock/` | `view_stock` | Alertas de stock bajo |
| GET | `out-of-stock/` | `view_stock` | Alertas sin stock |
| GET/POST | `movements/` | GET=`view_stock`, POST=`manage_stock` | Crear/listar movimientos (**UN producto a la vez**) |
| GET | `movements/recent/` | `view_stock` | Últimos movimientos |
| GET | `movements/<uuid>/` | `view_stock` | Detalle de un movimiento |
| GET | `summary/` | `view_stock` | Totales del inventario |
| GET | `valuation/` | `view_stock` | Valorización (quantity × product.cost) |
| POST | `imports/` | `manage_stock` | Subir CSV de stock masivo |
| GET/POST | `imports/<id>/` | `manage_stock` | Detalle / preview / aplicar importación |

**Nótese:** No hay ningún endpoint de tipo `purchases/`, `replenishments/`, `bulk-movement/`, ni `reposicion/`.

---

### 1.3 Backend — Endpoints de Tesorería

**Base:** `api/v1/treasury/`  
Implementados via `DefaultRouter`:

- `accounts/` — CRUD de cuentas
- `categories/` — CRUD de categorías de transacción
- `transactions/` — CRUD de transacciones (manualmente)
- `expenses/` — CRUD de gastos operativos
- `fixed-expenses/`, `fixed-expense-periods/` — gastos fijos recurrentes
- `employees/`, `payroll-payments/` — RRHH/sueldos
- `budgets/` — presupuestos por categoría

---

### 1.4 Backend — Señales / Servicios de Integración

| Archivo | Función | Qué hace |
|---------|---------|----------|
| `treasury/signals.py` | `create_transaction_from_sale` | **Solo ventas** → crea `Transaction IN` automáticamente |
| `inventory/services.py` | `register_stock_movement` | Crea `StockMovement` y actualiza `ProductStock`. No toca finanzas |

> **No existe** ninguna señal, servicio ni función que conecte un `StockMovement IN` con una `Transaction OUT`.

---

### 1.5 Frontend — Rutas de Inventario

**App Router base:** `/app/gestion/`

| Ruta | Componente principal | Operaciones disponibles |
|------|---------------------|------------------------|
| `/app/gestion/stock` → redirect | `stock-client.tsx` | Ver niveles, filtrar, crear **un** movimiento a la vez (modal) |
| `/app/gestion/stock/valorizacion` | `valuation-client.tsx` | Ver valorización quantity × product.cost |
| `/app/gestion/stock/importar` | CSV import flow | Carga masiva desde archivo |

> **No existe** ninguna ruta tipo `/compras`, `/purchases`, `/stock/reponer`, `/stock/intake`, `/recepciones` ni equivalente.

---

### 1.6 Frontend — Formulario de Movimiento (Modal Actual)

Campos del modal en `stock-client.tsx` / `StockMovementPayload` (type):

```typescript
// apps/web/src/features/gestion/types.ts
export type StockMovementPayload = {
    product_id: string;
    movement_type: 'IN' | 'OUT' | 'ADJUST' | 'WASTE';
    quantity: number;
    note?: string;
};
```

**Ausentes:** `unit_cost`, `supplier_id`, `invoice_number`, `account_id`, `attachment`.  
**Unidad:** un producto por llamada. No hay "lote" ni "evento de compra".

---

### 1.7 Permisos Existentes (RBAC)

Definidos en `accounts/rbac_registry.py`:

| Código | Módulo | Descripción |
|--------|--------|-------------|
| `view_stock` | Stock | Consultar niveles y movimientos |
| `manage_stock` | Stock | Ajustar inventario, registrar entradas/salidas |
| `manage_products` | Stock | Crear/editar productos (también habilita ver costos en valorización) |
| `view_finance` | Finanzas | Ver información financiera |
| `manage_finance` | Finanzas | Administrar operaciones financieras |

**Ausentes:** `view_purchases`, `manage_purchases`.

---

### 1.8 Multi-sucursal

- `StockMovement.business` → FK a `Business` (no a sucursal/branch)
- `ProductStock` → constraint único `(business, product)` → un solo nivel de stock por negocio
- **No existe granularidad por sucursal/depósito** en inventario actualmente

---

## 2. Hallazgos por Área

### A) Inventario / Stock

| Aspecto | Estado | Evidencia |
|---------|--------|-----------|
| Modelo de movimiento base | ✅ Existe | `StockMovement` en `inventory/models.py` |
| Tipos IN/OUT/ADJUST/WASTE | ✅ Existe | `MovementType` choices |
| Campo `reason` (string libre) | ✅ Existe | usado en demo con `'purchase'`, `'replenishment'` |
| Campo `metadata` (JSONField) | ✅ Existe | Podría albergar datos extra sin migración |
| Campo `unit_cost` en movimiento | ❌ No existe | No hay en modelo ni serializer |
| Campo `reference_type/id` en StockMovement | ❌ No existe | Solo existe en `Transaction` |
| Soporte para proveedor | ❌ No existe | Ningún modelo `Supplier` |
| Adjuntos en movimiento | ❌ No existe | `Transaction` sí tiene `attachment`; StockMovement no |
| Evento de compra multi-producto agrupado | ❌ No existe | Cada movimiento es independiente |
| Actualización automática de `Product.cost` desde stock IN | ❌ No existe | `Product.cost` es campo estático editable a mano |
| Valorización | ✅ Parcial | `quantity × product.cost` estático. No es costo real de compra |

---

### B) Finanzas / Tesorería

| Aspecto | Estado | Evidencia |
|---------|--------|-----------|
| Modelo de cuenta (varios tipos) | ✅ Existe | `Account` con tipo cash/bank/mercadopago/card_float |
| Transacción OUT con categoría | ✅ Existe | `Transaction` + `TransactionCategory` (dirección expense) |
| Campos de referencia polimórfica | ✅ Existe | `Transaction.reference_type`, `Transaction.reference_id` |
| Adjunto en transacción | ✅ Existe | `Transaction.attachment` (FileField) |
| Categoría "Proveedores" | ✅ En demo | `seed_demo.py` y `seed_gestion_comercial_test_data.py` crean esta categoría |
| Creación manual de TX OUT desde UI | ✅ Existe | Vía `/app/gestion/finanzas/movimientos/` |
| Creación automática TX OUT al registrar stock | ❌ No existe | `signals.py` solo cubre Sales → TX IN |
| Egreso vinculado a evento concreto de compra | ❌ No existe | No hay `purchase_id` en Transaction en uso |
| Categoría específica "Compras de Mercadería" | ❌ No existe (predefinida) | Existe mecanismo para crearla manualmente |

---

### C) Integración Inventario ↔ Finanzas

| Aspecto | Estado | Evidencia |
|---------|--------|-----------|
| Signal Stock IN → Transaction OUT | ❌ No existe | `signals.py` solo tiene `create_transaction_from_sale` |
| Servicio atómico compra → stock + finanzas | ❌ No existe | `register_stock_movement` no toca finanzas |
| Trazabilidad inversa TX → StockMovement | ❌ No existe | `Transaction.reference_type` no se usa para stock |
| Trazabilidad inversa StockMovement → TX | ❌ No existe | StockMovement no tiene FK a Transaction |
| Datos demo de "compra" | ⚠️ Desconectados | Demo crea TX OUT con description="Compra proveedor" Y crea StockMovements con reason='purchase' **por separado**, sin FK entre sí |

---

### D) Rutas y UI

| Aspecto | Estado |
|---------|--------|
| Página de stock actual | ✅ `/app/gestion/stock` |
| Formulario de movimiento (un producto) | ✅ Modal en stock |
| Importación masiva CSV | ✅ `/app/gestion/stock/importar` |
| Valorización de inventario | ✅ `/app/gestion/stock/valorizacion` |
| Página de compras / reposición | ❌ No existe |
| Formulario multi-ítem con costo y cuenta de pago | ❌ No existe |
| Historial de eventos de compra | ❌ No existe |
| Impacto financiero desde vista de stock | ❌ No existe |

---

## 3. Respuestas a las Preguntas Clave

### 3.1 ¿Existe un modelo "Purchase/Compra" o equivalente?

**No. Ausente por completo.**  
No existe ninguna app, modelo, tabla ni migración con nombre `Purchase`, `PurchaseOrder`, `StockReplenishment`, `Supplier`, `Vendor`, `Intake` o similar en todo el repositorio.

---

### 3.2 ¿Los movimientos de stock guardan costo?

**No directamente.**  
`StockMovement` no tiene campos `unit_cost`, `cost_total` ni `purchase_price`. El único campo de "costo" en el dominio de catálogo es `Product.cost` (Decimal, estático), que puede editarse desde la UI de productos.

Podría almacenarse en `StockMovement.metadata` (JSONField), pero hoy ningún endpoint ni serializer lo propone ni lo valida.

---

### 3.3 ¿La valuación actual usa costos reales?

**No. Usa costo estático del producto.**  
`InventoryValuationView` calcula `quantity × product.cost`, donde `product.cost` es un campo que se actualiza manualmente desde la ficha del producto. No existe promedio ponderado, FIFO ni ninguna actualización automática del costo basada en compras reales.

---

### 3.4 ¿Se puede atribuir un egreso financiero a una reposición concreta?

**No.** La única integración automática de inventario con finanzas existe para ventas. Para compras/reposición no hay señal, servicio ni FK que vincule ambos lados. En los datos de demo, los TX OUT de "compra proveedor" y los `StockMovement IN` con `reason='purchase'` son entidades independientes sin ningún ID compartido.

---

### 3.5 ¿Qué piezas faltan exactamente?

#### Backend
- [ ] **Modelo `Supplier`** (`catalog` o nueva app `purchases`)
- [ ] **Modelo `StockReplenishment`** — evento de reposición con campos: `supplier`, `account` (Account FK), `invoice_number`, `occurred_at`, `notes`, `attachment`, `transaction` (Transaction FK), `total_amount`, `status`
- [ ] **Modelo `StockReplenishmentItem`** — línea por producto: `replenishment`, `product`, `quantity`, `unit_cost`, `line_total`, `stock_movement` (StockMovement FK)
- [ ] **Campos en `StockMovement`**: `unit_cost` (Decimal, nullable), `replenishment_item` (FK opcional, nullable)
- [ ] **Servicio atómico** `create_replenishment()`: crea `StockReplenishment` + N `StockReplenishmentItem` + N `StockMovement IN` (con `unit_cost`) + 1 `Transaction OUT` en una transacción DB
- [ ] **Endpoint** `POST /api/v1/inventory/replenishments/` + `GET/retrieve`
- [ ] **Permisos nuevos**: `view_purchases`, `manage_purchases` en `rbac_registry.py`

#### Frontend
- [ ] **Ruta** `/app/gestion/stock/reponer` — formulario multi-ítem (producto + cantidad + costo unitario), proveedor, cuenta de pago, comprobante, notas
- [ ] **Ruta** `/app/gestion/stock/compras` — historial de eventos de reposición (con filtros fecha/proveedor)
- [ ] **Enlace cruzado** en vista de movimientos: ver TX financiera asociada
- [ ] **Enlace cruzado** en finanzas: desde una TX OUT categoría "Compras" ver el evento de reposición

#### Reportes
- [ ] Gasto en mercadería por mes (agrupar TXs OUT categoría "Compras")
- [ ] Gasto por proveedor
- [ ] Gasto por categoría de producto
- [ ] Gasto por producto (unit_cost history)

---

## 4. Gaps Priorizados

| # | Gap | Impacto | Esfuerzo | Prioridad |
|---|-----|---------|----------|-----------|
| 1 | No existe evento de compra agrupado multi-producto | Alto | Medio | 🔴 P1 |
| 2 | `StockMovement` no guarda `unit_cost` | Alto | Bajo | 🔴 P1 |
| 3 | No hay integración automática Stock IN → TX OUT | Alto | Medio | 🔴 P1 |
| 4 | No existe modelo `Supplier` / Proveedor | Medio | Bajo | 🟠 P2 |
| 5 | No hay UI de reposición multi-ítem | Alto | Alto | 🟠 P2 |
| 6 | No hay trazabilidad bidireccional movimiento ↔ finanzas | Medio | Bajo (solo FK) | 🟠 P2 |
| 7 | Valorización usa costo estático, no costo real de compra | Medio | Medio | 🟡 P3 |
| 8 | Permisos `view_purchases`, `manage_purchases` ausentes | Bajo | Bajo | 🟡 P3 |
| 9 | No hay historial de compras / eventos de reposición en UI | Medio | Alto | 🟡 P3 |
| 10 | Sin granularidad de stock por sucursal/depósito | Bajo | Alto | ⚪ P4 |
| 11 | Reportes de gasto en mercadería ausentes | Medio | Medio | 🟡 P3 |
| 12 | Sin recepciones parciales ni cuentas por pagar | Bajo | Alto | ⚪ P4 |

---

## 5. Propuesta MVP (Rápida)

**Objetivo:** En un sprint de ≈2 semanas permitir registrar una "Reposición de Stock" que cree múltiples `StockMovement IN` con costo y una `Transaction OUT` vinculados, con trazabilidad básica.

### 5.1 Cambios de Modelo (mínimos)

**Opción A — Sin nueva tabla (usa metadata + note):**
- Agregar campo `unit_cost` (DecimalField, null/blank) a `StockMovement`
- En `StockMovement.metadata`, almacenar `{ "replenishment_group": "<uuid>", "transaction_id": "<uuid>" }`
- Una `Transaction OUT` con `reference_type='stock_replenishment'` y `reference_id=<group_uuid>`

> Ventaja: 1 migración. Desventaja: trazabilidad frágil (JSONField).

**Opción B — Tabla mínima de grupo (recomendada):**

```python
# services/api/src/apps/inventory/models.py

class StockReplenishment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('business.Business', on_delete=models.CASCADE, related_name='stock_replenishments')
    occurred_at = models.DateTimeField()
    supplier_name = models.CharField(max_length=255, blank=True)   # Texto libre (MVP, sin FK)
    invoice_number = models.CharField(max_length=128, blank=True)
    account = models.ForeignKey('treasury.Account', null=True, blank=True, on_delete=models.SET_NULL)
    transaction = models.OneToOneField('treasury.Transaction', null=True, blank=True, on_delete=models.SET_NULL, related_name='replenishment')
    total_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
```

```python
# Agregar a StockMovement:
unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
replenishment = models.ForeignKey(
    'inventory.StockReplenishment',
    null=True, blank=True,
    on_delete=models.SET_NULL,
    related_name='movements'
)
```

**Migraciones:** 2 migraciones, ~30 líneas de código.

---

### 5.2 Nuevo Servicio Atómico

```python
# services/api/src/apps/inventory/services.py

@transaction.atomic
def create_stock_replenishment(
    *,
    business,
    items: list[dict],          # [{product, quantity, unit_cost}, ...]
    account,                     # treasury.Account
    occurred_at,
    supplier_name: str = '',
    invoice_number: str = '',
    notes: str = '',
    created_by=None,
    purchase_category=None,      # TransactionCategory (expense)
) -> tuple[StockReplenishment, Transaction]:
    total = sum(Decimal(i['unit_cost']) * Decimal(i['quantity']) for i in items)
    
    replenishment = StockReplenishment.objects.create(
        business=business, occurred_at=occurred_at,
        supplier_name=supplier_name, invoice_number=invoice_number,
        account=account, total_amount=total,
        notes=notes, created_by=created_by,
    )
    
    for item in items:
        movement, _ = register_stock_movement(
            business=business, product=item['product'],
            movement_type=StockMovement.MovementType.IN,
            quantity=item['quantity'],
            note=f"Reposición #{replenishment.id}",
            reason='replenishment',
            metadata={'replenishment_id': str(replenishment.id)},
            created_by=created_by,
        )
        movement.unit_cost = item['unit_cost']
        movement.replenishment = replenishment
        movement.save(update_fields=['unit_cost', 'replenishment'])
    
    tx = Transaction.objects.create(
        business=business, account=account,
        direction=Transaction.Direction.OUT,
        amount=total, occurred_at=occurred_at,
        category=purchase_category,
        description=f"Compra mercadería {supplier_name or ''} #{invoice_number or ''}".strip(),
        reference_type='stock_replenishment',
        reference_id=str(replenishment.id),
        created_by=created_by,
    )
    replenishment.transaction = tx
    replenishment.save(update_fields=['transaction'])
    
    return replenishment, tx
```

---

### 5.3 Nuevo Endpoint

```
POST /api/v1/inventory/replenishments/
GET  /api/v1/inventory/replenishments/
GET  /api/v1/inventory/replenishments/<uuid>/
```

**Payload POST:**
```json
{
  "occurred_at": "2026-02-20T10:00:00",
  "supplier_name": "Mayorista Norte SA",
  "invoice_number": "FAC-0001-000123",
  "account_id": "<uuid>",
  "notes": "Compra mensual gastronomía",
  "purchase_category_id": "<uuid>",
  "items": [
    {"product_id": "<uuid>", "quantity": "20.00", "unit_cost": "1500.00"},
    {"product_id": "<uuid>", "quantity": "10.00", "unit_cost": "850.00"}
  ]
}
```

---

### 5.4 Nuevos Permisos (mínimos)

En `accounts/rbac_registry.py`:
```python
register_capability('view_purchases', 'Ver Compras', 'Consultar eventos de reposición de stock', 'Stock', 'gestion')
register_capability('manage_purchases', 'Gestionar Compras', 'Registrar compras y reposición de stock', 'Stock', 'gestion')
```

---

### 5.5 Nueva Ruta Frontend (MVP)

- `/app/gestion/stock/reponer` — Formulario con tabla de ítems (agregar fila), selector de cuenta de pago, proveedor (texto libre), número comprobante
- Agrega acceso desde la nav de Stock (`stock-nav.tsx`)

---

### 5.6 Trazabilidad MVP

```
StockReplenishment ──── transaction ────→ Transaction (OUT)
       │
       ├── movements ──→ StockMovement IN (producto A, qty, unit_cost)
       ├── movements ──→ StockMovement IN (producto B, qty, unit_cost)
       └── movements ──→ StockMovement IN (producto C, qty, unit_cost)
```

**Desde una transacción:** `transaction.replenishment` → ver el evento de compra y cada producto.  
**Desde un movimiento de stock:** `movement.replenishment` → ver el evento de compra completo y la transacción.

---

## 6. Propuesta Ideal (Módulo Completo)

### 6.1 Nueva App `purchases`

```
services/api/src/apps/purchases/
    models.py     — Supplier, PurchaseOrder, PurchaseOrderItem, PurchaseReceipt, PurchaseReceiptItem
    serializers.py
    services.py   — create_purchase_order(), create_receipt(), record_payment()
    views.py
    urls.py
    signals.py
    admin.py
    migrations/
```

### 6.2 Modelos (Ideal)

```python
class Supplier(models.Model):
    business = FK(Business)
    name = CharField(255)
    tax_id = CharField(50, blank=True)      # CUIT / RUT
    email = CharField(255, blank=True)
    phone = CharField(50, blank=True)
    address = TextField(blank=True)
    is_active = BooleanField(default=True)
    payment_terms_days = PositiveIntegerField(default=0)  # días de crédito

class PurchaseOrder(models.Model):
    """Orden de compra — puede tener recepciones parciales."""
    class Status(TextChoices):
        DRAFT = 'draft', 'Borrador'
        SENT = 'sent', 'Enviada'
        PARTIAL = 'partial', 'Parcialmente Recibida'
        RECEIVED = 'received', 'Recibida'
        CANCELLED = 'cancelled', 'Cancelada'
    business = FK(Business)
    supplier = FK(Supplier, null=True, blank=True)
    status = CharField(choices=Status)
    expected_date = DateField(null=True, blank=True)
    notes = TextField(blank=True)
    created_by = FK(User)

class PurchaseOrderItem(models.Model):
    order = FK(PurchaseOrder, related_name='items')
    product = FK(Product)
    quantity_ordered = DecimalField()
    unit_cost = DecimalField()

class PurchaseReceipt(models.Model):
    """Recepción de mercadería (puede ser parcial respecto a la OC)."""
    order = FK(PurchaseOrder, null=True, blank=True)  # puede ser sin OC
    business = FK(Business)
    supplier = FK(Supplier, null=True, blank=True)
    invoice_number = CharField(blank=True)
    occurred_at = DateTimeField()
    # Pago
    payment_status = CharField(choices=['unpaid','partial','paid'])  # cuentas por pagar
    # Finanzas
    transaction = OneToOneField(Transaction, null=True, blank=True)
    account = FK(Account, null=True, blank=True)
    total_amount = DecimalField()
    attachment = FileField(null=True, blank=True)
    notes = TextField(blank=True)
    created_by = FK(User)

class PurchaseReceiptItem(models.Model):
    receipt = FK(PurchaseReceipt, related_name='items')
    product = FK(Product)
    quantity = DecimalField()
    unit_cost = DecimalField()
    stock_movement = OneToOneField(StockMovement, null=True, blank=True)

class PurchasePayment(models.Model):
    """Pagos parciales para cuentas por pagar."""
    receipt = FK(PurchaseReceipt, related_name='purchase_payments')
    account = FK(Account)
    amount = DecimalField()
    paid_at = DateTimeField()
    transaction = OneToOneField(Transaction, null=True, blank=True)
    notes = TextField(blank=True)
```

---

### 6.3 Índice de Objetos Adicionales (Ideal)

| Objeto | Descripción |
|--------|-------------|
| `purchases` Django app | Separación limpia de dominio |
| `Supplier` | Entidad proveedor con datos de contacto y condiciones |
| `PurchaseOrder` | Orden de compra pre-recepción (opcional pero útil) |
| `PurchaseReceipt` | Evento de recepción real (anclado a Finanzas) |
| `PurchaseReceiptItem` | Línea por producto con `unit_cost` y FK a `StockMovement` |
| `PurchasePayment` | Pagos parciales para gestionar cuentas por pagar |
| Avg-cost update | Al recibir mercadería, actualizar `Product.cost` con promedio ponderado |
| `purchase_category_id` en TreasurySettings | Cuenta/categoría por defecto para compras |

---

### 6.4 Rutas Frontend Completas (Ideal)

```
/app/gestion/stock/compras/              → Historial de recepciones
/app/gestion/stock/compras/nueva         → Formulario multi-ítem (nueva recepción)
/app/gestion/stock/compras/<id>          → Detalle recepción + pagos + movimientos de stock
/app/gestion/stock/proveedores/          → CRUD de proveedores
/app/gestion/stock/ordenes/              → Órdenes de compra (si se implementan)
/app/gestion/reportes/compras/           → Reportes: gasto por mes/proveedor/categoría/producto
```

---

### 6.5 Actualización de Costo Promedio (Ideal)

Al registrar una `PurchaseReceiptItem`:

```python
# Promedio ponderado (WAC)
new_avg_cost = (
    (product.cost * current_stock) + (unit_cost * receipt_quantity)
) / (current_stock + receipt_quantity)

product.cost = new_avg_cost
product.save(update_fields=['cost'])
```

Esto mejora la valorización existente (`InventoryValuationView`) sin cambiarla.

---

## 7. Checklist de Pruebas Manuales

Una vez implementado el MVP, validar los siguientes escenarios:

### Registro de Compra
- [ ] Crear una reposición con 3 productos distintos, costo unitario diferente
- [ ] Verificar que se crearon 3 `StockMovement` de tipo IN
- [ ] Verificar que el `StockMovement.unit_cost` refleja el costo ingresado
- [ ] Verificar que `ProductStock.quantity` aumentó correctamente para los 3 productos
- [ ] Verificar que se creó 1 `Transaction OUT` con el total correcto (`Σ qty_i × unit_cost_i`)
- [ ] Verificar que `Transaction.account` corresponde a la cuenta seleccionada
- [ ] Verificar que `Transaction.category` corresponde a la categoría de compra seleccionada
- [ ] Verificar que `Transaction.reference_type='stock_replenishment'` y `reference_id` apunta al evento

### Trazabilidad
- [ ] Desde el historial de transacciones treasury, encontrar la TX OUT y navegar al evento de compra
- [ ] Desde el historial de movimientos de stock, ver los 3 movimientos y navegar al evento de compra
- [ ] Desde el evento de compra, ver los 3 ítems y la transacción vinculada
- [ ] Desde el evento de compra, navegar a la transacción y ver el saldo de la cuenta afectada

### Finanzas
- [ ] Verificar que el saldo de la cuenta (Caja/Banco/MercadoPago) decrementó correctamente
- [ ] Verificar que la TX OUT aparece en el listado de movimientos de la cuenta
- [ ] Anular la compra: verificar que el stock y la transacción se revierten (o se marca como voided)

### Permisos
- [ ] Usuario con rol sin `manage_purchases` no puede crear reposición (403)
- [ ] Usuario con `view_purchases` puede ver el listado pero no crear
- [ ] Usuario con `manage_purchases` puede crear y ver

### Validaciones
- [ ] Crear reposición con product_id de otro negocio → error 403/400
- [ ] Crear reposición con cantidad 0 → error validación
- [ ] Crear reposición con unit_cost negativo → error validación
- [ ] Crear reposición con account_id de otro negocio → error 403/400
- [ ] Crear reposición con items duplicados (mismo producto dos veces) → verificar comportamiento esperado

### Costo y Valorización
- [ ] Antes de la compra: anotar `Product.cost` actual y stock actual
- [ ] Registrar compra con unit_cost diferente al costo del producto
- [ ] Verificar si `Product.cost` se actualiza (MVP: no; Ideal: sí con promedio ponderado)
- [ ] Verificar que la valorización en `/stock/valorizacion` refleja el stock nuevo

### Reportes (futuros)
- [ ] Filtrar transacciones por categoría "Compras" y rango de fechas → totales correctos
- [ ] Agrupar por proveedor → totales por proveedor correctos
- [ ] Comparar gasto mensual vs mes anterior → tendencia coherente

---

## Resumen Ejecutivo

| Pregunta | Respuesta |
|----------|-----------|
| ¿Existe modelo Purchase/Compra? | ❌ **No existe** |
| ¿StockMovement guarda costo? | ❌ **No** (sólo `Product.cost` estático) |
| ¿Valorización usa costos reales? | ❌ **No** (costo manual del producto) |
| ¿Se puede vincular egreso a reposición? | ❌ **No** (ninguna integración) |
| ¿Hay UI de compras/reposición? | ❌ **No existe** |
| ¿Hay proveedor en el sistema? | ❌ **No existe** modelo Supplier |
| ¿Inventario es multi-sucursal? | ❌ **No** (sólo por Business) |
| ¿Stock cargable por lote multi-producto? | ❌ **No** (un producto por llamada) |
| ¿Permisos manage_purchases existen? | ❌ **No registrados** en RBAC |
| **¿Qué SÍ existe y es reutilizable?** | `Transaction` (con reference fields), `Account`, `TransactionCategory`, `StockMovement` (con `metadata`/`reason`), servicio `register_stock_movement`, 2 permisos base de stock, categoría "Proveedores" en demo |

**El camino más corto al MVP es ~2 sprints:** nueva tabla `StockReplenishment`, campo `unit_cost` en `StockMovement`, un servicio atómico que cree movimientos + transacción, un endpoint REST, dos permisos RBAC y una página frontend de formulario multi-ítem. La base de la tesorería (`Transaction` + `Account`) ya está lista y es perfectamente adecuada para registrar el egreso de compra.
