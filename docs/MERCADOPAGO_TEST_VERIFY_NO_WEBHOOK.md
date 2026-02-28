# Mercado Pago — Verificación sin Webhook (Opción A: DEV/TEST)

> **⚠️ DEV/TEST only.** Este flujo permite verificar el pago contra la API de MP desde el browser return URL, **sin necesitar ngrok, túnel ni webhook**. En producción el webhook es la fuente de verdad.

---

## Cómo funciona

```
[Carta /m/[slug]]
        │ POST create-preference
        ▼
[API] TipTransaction(status=created) → MP preference(init_point)
        │ redirect
        ▼
[Mercado Pago TEST — paga con cuenta de prueba]
        │ redirect a back_url/success?tip_id=...&payment_id=...
        ▼
[/m/[slug]/tip/success] — lee payment_id del querystring
        │ GET /api/v1/menu/public/tips/<tip_id>/verify/?payment_id=<id>
        ▼
[API] sdk.payment().get(payment_id)
        → valida external_reference == TipTransaction.external_reference
        → actualiza TipTransaction.status
        │ responde {status, mp_status, ...}
        ▼
[UI] muestra Aprobado / Pendiente / Rechazado
```

MP siempre incluye `payment_id` (o `collection_id`) en los query params de la `back_url` de éxito, lo que hace este flujo funcional **sin webhook**.

---

## Endpoint de verificación

### `GET /api/v1/menu/public/tips/<tip_id>/verify/`

**Autenticación:** pública (AllowAny)  
**Query params:**

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `payment_id` | string/int | Sí* | ID de pago de MP (preferido) |
| `collection_id` | string/int | Sí* | Alias de `payment_id` (fallback) |

\* Al menos uno de los dos.

**Respuesta exitosa (200):**
```json
{
  "tip_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "approved",
  "mp_payment_id": "1234567890",
  "amount": "500.00",
  "currency": "ARS",
  "mp_status": "approved",
  "mp_status_detail": "accredited",
  "verified_at": "2026-02-27T21:00:00Z"
}
```

**Errores:**

| HTTP | Causa |
|---|---|
| 400 | `payment_id` ausente, o `external_reference` no coincide con el tip |
| 404 | `tip_id` no existe en la BD, o MP no encontró el payment |
| 503 | No hay credenciales MP configuradas |
| 502 | Error de comunicación con la API de MP |

### Seguridad
- El payment debe tener `external_reference == TipTransaction.external_reference`.
- Si no coincide → `400` y no se toca nada. Esto previene que alguien pase un `payment_id` ajeno para actualizar un tip.
- Idempotente: llamar N veces con el mismo `payment_id` produce el mismo resultado.

---

## Mapeo de estados MP → TipTransaction

| `mp_status` | `TipTransaction.status` |
|---|---|
| `approved` | `approved` |
| `pending` | `pending` |
| `in_process` | `pending` |
| `authorized` | `pending` |
| `rejected` | `rejected` |
| `cancelled` | `cancelled` |
| `refunded` | `cancelled` |
| `charged_back` | `cancelled` |

---

## Pruebas manuales con curl

### 1. Crear preferencia
```bash
curl -s -X POST http://localhost:8000/api/v1/menu/public/slug/carta-qr-demo/tips/create-preference/ \
  -H "Content-Type: application/json" \
  -d '{"amount": 500}' | jq .
# Guarda tip_id e init_point
```

### 2. Simular retorno de MP (con un payment_id real de TEST)
```bash
TIP_ID="<uuid-del-tip>"
PAYMENT_ID="<id-del-pago-mp>"

curl -s "http://localhost:8000/api/v1/menu/public/tips/${TIP_ID}/verify/?payment_id=${PAYMENT_ID}" | jq .
```

### 3. Verificar idempotencia (llamar 3 veces)
```bash
for i in 1 2 3; do
  curl -s "http://localhost:8000/api/v1/menu/public/tips/${TIP_ID}/verify/?payment_id=${PAYMENT_ID}" \
    | jq '{status, mp_status}'
  sleep 1
done
# Debe devolver el mismo status las 3 veces
```

### 4. Probar mismatch (payment_id de otro pago)
```bash
curl -s "http://localhost:8000/api/v1/menu/public/tips/${TIP_ID}/verify/?payment_id=9999999" | jq .
# Debe devolver 400: "El pago no corresponde a esta propina."
```

### 5. Verificar en la BD
```bash
docker exec mirubro-api python manage.py shell -c "
from apps.menu.models import TipTransaction
t = TipTransaction.objects.get(id='${TIP_ID}')
print(t.status, t.mp_payment_id)
"
```

---

## Flujo completo QA step-by-step

### Pre-requisitos
1. `docker compose up -d` (todos los contenedores healthy)
2. Tips habilitados: admin → Menu → Interacción y Propinas → Modo: **Checkout Pro MP (Dinámico)**
3. Cuentas de prueba MP: [https://www.mercadopago.com.ar/developers/panel/test-users](https://www.mercadopago.com.ar/developers/panel/test-users)

### Caso 1 — Pago aprobado ✅
1. Abrir `http://localhost:3000/m/carta-qr-demo`
2. Hacer clic en propina → elegir monto → confirmar
3. En MP TEST loguearse como **comprador de prueba**
4. Usar tarjeta aprobada: `4509 9535 6623 3704` / CVV: `123` / Vto: fecha futura
5. Completar el pago → MP redirige a `/tip/success?tip_id=...&payment_id=...`
6. La página llama a `verify` automáticamente → muestra ✅ **¡Gracias por tu propina!**

### Caso 2 — Pago pendiente ⏳
1. Repetir flujo pero usar tarjeta pendiente (ej. `5031 7557 3453 0604`)
2. MP redirige a `/tip/pending?tip_id=...&payment_id=...`  
   *(auto_return solo aplica a `approved`, para pending redirige a pending URL)*
3. Botón **Verificar estado** en la página pending → llama verify → redirige a success si cambió
4. Si sigue pendiente: muestra "El pago sigue en proceso."

### Caso 3 — Mismatch (adversarial) ❌
```bash
curl "http://localhost:8000/api/v1/menu/public/tips/<TIP_A>/verify/?payment_id=<PAYMENT_B>"
# Responde: 400 "El pago no corresponde a esta propina."
```

### Caso 4 — Idempotencia
```bash
# Llamar 5 veces seguidas → status estable, no duplicados
for i in {1..5}; do curl -s ".../verify/?payment_id=..." | jq .status; done
```

---

## Query params que MP envía en back_urls

MP agrega automáticamente estos params al redirigir:

```
/tip/success?tip_id=<uuid>&collection_id=123&collection_status=approved&payment_id=123&status=approved&payment_type=credit_card&merchant_order_id=456&preference_id=...&site_id=MLA&processing_mode=aggregator&merchant_account_id=null
```

| Param | Descripción | Usado por verify |
|---|---|---|
| `payment_id` | ID del pago (principal) | ✅ |
| `collection_id` | Alias de `payment_id` | ✅ (fallback) |
| `status` / `collection_status` | Estado informativo | No (no confiar, validar en API) |
| `preference_id` | ID de la preferencia creada | No |

---

## Diferencia con Webhooks (producción)

| | Opción A (verify) | Producción (webhook) |
|---|---|---|
| Requiere ngrok/túnel | ❌ No | ✅ Sí |
| Iniciado por | Browser (back_url redirect) | MP server-to-server |
| Confiabilidad | Solo si el usuario termina el flujo | Siempre, aunque el browser se cierre |
| Verificación | `external_reference` match | HMAC signature + `external_reference` |
| Uso recomendado | DEV/TEST | Producción |

En producción, la Opción A puede coexistir como verificación adicional (actualiza si el webhook tardó), pero el webhook es la fuente de verdad.
