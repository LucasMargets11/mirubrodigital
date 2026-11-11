# Traslados de stock entre ubicaciones (PR3) — contrato de API

Estado: backend listo para consumir desde la interfaz (PR4). Sin cambios de
dependencias. Validado en Python 3.12, Django 5.1.15 y PostgreSQL 16
descartable con datos ficticios.

Pendiente de despliegue (bloqueo conocido, no resuelto aquí): con Django
5.0.14, la versión que fija `requirements.txt`, el proyecto ya no carga desde
antes de este PR. `apps/appointments/models.py` usa
`CheckConstraint(condition=...)`, disponible desde Django 5.1. La migración
`inventory/0012_stock_transfers.py` usa la misma forma, así que también
requiere Django ≥ 5.1.

## Endpoints

Todas las rutas están bajo `/api/v1/inventory/` y resuelven el negocio por la
membresía activa (cookie `bid`), igual que el resto de inventario.

| Método | Ruta | Permiso | Uso |
| --- | --- | --- | --- |
| `POST` | `transfers/` | `manage_stock` | Confirmar un traslado |
| `GET` | `transfers/?limit=N` | `view_stock` | Historial (más reciente primero, `limit` 50 por defecto, máximo 200) |
| `GET` | `transfers/<uuid>/` | `view_stock` | Detalle de un traslado |

En gestión comercial `manage_stock` lo tienen `owner`, `admin` y `manager`;
`staff`, `viewer`, `analyst` y `contador` solo tienen `view_stock`.

## POST `transfers/` — confirmar

```json
{
  "origin_location_id": "uuid",
  "destination_location_id": "uuid",
  "idempotency_key": "texto, 1 a 255 caracteres",
  "lines": [
    { "product_id": "uuid", "quantity": "2.00" }
  ]
}
```

Reglas:

- `idempotency_key` es **obligatoria**. Si se omite, viene vacía, solo con
  espacios o en `null`, la respuesta es `400` con error en el campo
  `idempotency_key`. En ese caso no se crea traslado, ni movimientos, ni
  saldos. La clave se recorta (trim) y es única por negocio. La interfaz debe
  generar una clave nueva (por ejemplo un UUID v4) por cada intento de
  confirmación del usuario y **reusar la misma** en los reintentos de red
  de ese intento.
- `lines`: al menos un renglón, sin productos repetidos. `quantity > 0`, con
  hasta 2 decimales (máximo 12 dígitos).
- Origen y destino deben ser distintos, pertenecer al negocio y estar activos.
- Se descuenta el **disponible** del origen (`quantity - reserved_quantity`).
  Las reservas no se trasladan. El saldo de destino se crea si no existía.
- Todo o nada: si cualquier renglón falla, no queda ningún efecto parcial.

### Respuestas

| Código | Cuándo | Cuerpo |
| --- | --- | --- |
| `201 Created` | Traslado nuevo confirmado | Detalle del traslado (ver abajo) |
| `200 OK` | Reintento con la misma clave y el mismo contenido (origen, destino y renglones; el orden de los renglones no importa) | El mismo traslado original, sin nuevos movimientos |
| `400 Bad Request` | Error de forma: falta o está vacía `idempotency_key`, ubicación inexistente o de otro negocio, `lines` vacío, producto repetido, cantidad ≤ 0 o con más de 2 decimales | `{ "<campo>": ["mensaje"] }` (formato DRF) |
| `400 Bad Request` | Regla de negocio: stock insuficiente en origen, origen igual a destino, ubicación inactiva, producto de otro negocio | `{ "detail": "mensaje" }` |
| `401 Unauthorized` | Sin sesión | — |
| `403 Forbidden` | Sin membresía en el negocio o sin `manage_stock` | — |
| `409 Conflict` | Misma clave con contenido distinto | `{ "error": { "code": "IDEMPOTENCY_KEY_CONFLICT", "message": "..." } }` |

Un intento rechazado con `400` no consume la clave: puede reintentarse con la
misma clave una vez corregido el problema (por ejemplo, después de reponer
stock).

### Cuerpo del traslado (201 / 200 / GET)

```json
{
  "id": "uuid",
  "origin_location_id": "uuid",
  "origin_location_name": "Depósito",
  "destination_location_id": "uuid",
  "destination_location_name": "Local principal",
  "created_by_name": "Nombre o email",
  "created_at": "2026-11-11T12:00:00-03:00",
  "lines": [
    {
      "id": "uuid",
      "product": { "...": "ProductSummarySerializer" },
      "quantity": "2.00",
      "out_movement_id": "uuid",
      "in_movement_id": "uuid"
    }
  ]
}
```

Cada renglón genera un movimiento `OUT` en origen y uno `IN` en destino, ambos
con `reason="transfer"`, `location` y `transfer` informados.

## Concurrencia

Todo escritor que bloquee varios `ProductStock` en una transacción debe usar
`inventory.services.lock_stock_records`, que crea los saldos faltantes y los
bloquea en un único orden global: `(str(product_id), str(location_id))`.
El traslado y la creación de ventas (`SaleCreateSerializer.create`) ya lo
usan. Antes de este cambio, una venta con renglones B, A y un traslado
saliente de Local principal con A, B cerraban un ciclo y PostgreSQL abortaba
la venta con `deadlock detected` (40P01). Lo cubre
`SaleVersusTransferLockOrderTests`.

Escritores con varios renglones que todavía bloquean en orden comercial y no
tienen prueba contra el traslado (pendientes):

- `SaleCancelSerializer.save` (reversa de venta, `IN` por renglón).
- `OrderViewSet.confirm` y `OrderViewSet.deliver` en `sales/views.py`
  (`reserve_stock`, `release_stock` y `OUT` por ítem).
- `_register_stock` / `_should_flag_without_stock` en `orders/serializers.py`.
- `create_stock_replenishment` y `void_stock_replenishment`.
- Importador de inventario (`ADJUST` por fila).

Todos operan solo sobre Local principal. Un ciclo con un traslado termina en
un abort por deadlock, que hace rollback, no en saldos corruptos. Aun así
conviene migrarlos a `lock_stock_records` con su prueba.
