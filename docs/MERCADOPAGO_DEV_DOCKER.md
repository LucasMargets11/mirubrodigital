# Mercado Pago Checkout Pro (Propinas) — DEV con Docker

Guía completa para levantar y probar el flujo de propinas con Mercado Pago Checkout Pro
en ambiente DEV usando Docker Compose.

---

## Tabla de contenidos

1. [Arquitectura del flujo](#1-arquitectura-del-flujo)
2. [Auditoría del código existente](#2-auditoría-del-código-existente)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Cómo levantar con Docker Compose](#4-cómo-levantar-con-docker-compose)
5. [Cómo levantar el túnel (ngrok)](#5-cómo-levantar-el-túnel-ngrok)
6. [Configurar Credenciales TEST de Mercado Pago](#6-configurar-credenciales-test-de-mercado-pago)
7. [Crear cuentas de prueba en Mercado Pago](#7-crear-cuentas-de-prueba-en-mercado-pago)
8. [Configurar Webhooks en el panel de MP](#8-configurar-webhooks-en-el-panel-de-mp)
9. [Configurar el Menú para activar propinas](#9-configurar-el-menú-para-activar-propinas)
10. [Flujo QA paso a paso](#10-flujo-qa-paso-a-paso)
11. [Comandos curl de referencia](#11-comandos-curl-de-referencia)
12. [Checklist de validación](#12-checklist-de-validación)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Arquitectura del flujo

```
Cliente (browser)           Next.js Web (3000)          Django API (8000)          Mercado Pago
       │                           │                           │                         │
       │  GET /m/<slug>            │                           │                         │
       │──────────────────────────►│  GET /api/v1/menu/        │                         │
       │                           │  public/slug/<slug>/      │                         │
       │                           │──────────────────────────►│                         │
       │◄──────────────────────────│◄──────────────────────────│                         │
       │                           │                           │                         │
       │  [click Propina]          │                           │                         │
       │  POST create-preference   │                           │                         │
       │──────────────────────────►│ (client-side fetch)       │                         │
       │                           │  POST /api/v1/menu/       │                         │
       │                           │  public/slug/<slug>/      │                         │
       │                           │  tips/create-preference/  │                         │
       │                           │──────────────────────────►│  POST /preferences      │
       │                           │                           │────────────────────────►│
       │                           │                           │◄────────────────────────│
       │                           │                           │  {init_point, id}       │
       │                           │◄──────────────────────────│                         │
       │◄──────────────────────────│  {init_point, tip_id}     │                         │
       │                           │                           │                         │
       │  window.location = init_point (redirect a MP)         │                         │
       │──────────────────────────────────────────────────────────────────────────────►│
       │                           (usuario paga con cuenta TEST)                        │
       │◄──────────────────────────────────────────────────────────────────────────────│
       │  redirect back_url /m/<slug>/tip/success?tip_id=...                            │
       │                           │                           │                         │
       │                           │                           │◄─── POST webhook ───────│
       │                           │                           │  /api/v1/billing/       │
       │                           │                           │  mercadopago/webhook    │
       │  GET tip status           │  GET /api/v1/menu/        │                         │
       │──────────────────────────►│  public/tips/<id>/status/ │                         │
       │◄──────────────────────────│◄──────────────────────────│                         │
```

---

## 2. Auditoría del código existente

### ✅ Ya implementado (antes de este PR)

| Componente | Estado | Ubicación |
|---|---|---|
| `MercadoPagoService.create_preference()` | ✅ | `billing/mp_service.py` |
| `MercadoPagoWebhookView` | ✅ | `billing/views.py` |
| `process_tip_payment()` idempotente | ✅ | `billing/views.py` |
| `PublicTipCreatePreferenceView` | ✅ | `menu/views.py` |
| `PublicTipStatusView` | ✅ | `menu/views.py` |
| Rutas webhook y tip | ✅ | `billing/urls.py`, `menu/urls.py` |
| Frontend `/m/[slug]` con `TipAmountSelector` | ✅ | `apps/web/src/app/m/[slug]/` |
| Páginas success/pending/failure | ✅ | `apps/web/src/app/m/[slug]/tip/` |
| `createPublicTipPreference` + `getPublicTipStatus` | ✅ | `features/menu/api.ts` |
| Modelos `TipTransaction`, `MercadoPagoConnection` | ✅ | `menu/models.py` |
| `PaymentEvent` deduplication | ✅ | `billing/views.py` |

### 🔧 Bugs corregidos en este PR

| Bug | Descripción | Fix |
|---|---|---|
| `settings.BASE_URL` no existe | `mp_service.create_preference()` crasheaba con `AttributeError` | Reemplazado por `BASE_PUBLIC_URL` / `PUBLIC_MENU_BASE_URL` / `FRONTEND_URL` con fallback |
| No fallback token en DEV | `PublicTipCreatePreferenceView` requería OAuth per-business; bloqueaba DEV | Ahora usa global `MP_ACCESS_TOKEN` si no hay OAuth connection |
| No `notification_url` en tip preference | Los webhooks de MP no llegaban automáticamente | Agregado dinámicamente desde `BASE_PUBLIC_URL` |
| No validación HMAC webhook | `MP_WEBHOOK_SECRET` se leía pero no se usaba | Implementado `x-signature` HMAC-SHA256 verification (bypass en DEV si no hay secret) |
| `apps/web/.env` faltaba `API_URL_INTERNAL` | SSR usaba fallback incorrecto | Agregado en `apps/web/.env` |

### 🆕 Agregado en este PR

- `DevMercadoPagoPingView`: `GET /api/v1/billing/dev/mercadopago/ping` — diagnóstico de credenciales
- `ngrok` service opcional en docker-compose (profile `tunnel`)
- Esta documentación

---

## 3. Variables de entorno

### `services/api/.env` (Django)

```dotenv
# ── Credenciales MP TEST ──
MP_ACCESS_TOKEN=TEST-xxxx-xxxx-xxxx-xxxx-xxxx   # Credencial TEST de tu cuenta MP
MP_WEBHOOK_SECRET=mi-secreto-local-dev            # String aleatorio — debe coincidir con el secret en panel MP

# ── URL pública (actualizar con tu ngrok URL) ──
BASE_PUBLIC_URL=https://xxxx-xx-xx-xx-xx.ngrok-free.app
PUBLIC_MENU_BASE_URL=https://xxxx-xx-xx-xx-xx.ngrok-free.app  # o el dominio público del frontend
FRONTEND_URL=http://localhost:3000  # URL del frontend en el browser

# ── OAuth per-business (opcional — solo para Fase 2) ──
MP_CLIENT_ID=
MP_CLIENT_SECRET=
MP_REDIRECT_URI=https://xxxx-xxxx.ngrok-free.app/api/v1/menu/mercadopago/connect/callback/
```

> **Importante:** `BASE_PUBLIC_URL` es la URL públicamente accesible del **API** (donde llegan los webhooks de MP).  
> `PUBLIC_MENU_BASE_URL` / `FRONTEND_URL` es la URL del **frontend** (donde van los `back_urls` del checkout).  
> En DEV básico sin webhooks puedes dejar `BASE_PUBLIC_URL` vacío y los `back_urls` funcionarán igual (solo sin webhook).

### `apps/web/.env` (Next.js)

```dotenv
API_URL_INTERNAL=http://api:8000          # SSR Docker-internal: NO cambiar
NEXT_PUBLIC_API_URL=http://localhost:8000  # Browser → API (accesible desde el browser DEV)
NEXT_PUBLIC_BASE_URL=http://localhost:3000 # URL pública del frontend (para links QR, etc.)
```

---

## 4. Cómo levantar con Docker Compose

```bash
# Desde la raíz del proyecto
cd infra

# Build + up (todos los servicios base)
docker compose up --build

# Solo rebuild y up del API (si solo cambias Python)
docker compose up --build api

# Ver logs en tiempo real
docker compose logs -f api
docker compose logs -f web
```

Servicios disponibles:
- **API**: http://localhost:8000
- **Web**: http://localhost:3000
- **Postgres**: localhost:5432
- **Redis**: localhost:6379
- **API Docs**: http://localhost:8000/api/docs/

### Verificar que el API arrancó bien

```bash
curl http://localhost:8000/api/v1/health/
# {"status": "ok"}
```

### Verificar credenciales MP (DEV ping)

```bash
curl http://localhost:8000/api/v1/billing/dev/mercadopago/ping
```

Respuesta esperada (con token correcto):
```json
{
  "mp_access_token_set": true,
  "mp_access_token_prefix": "TEST-12345…",
  "mp_webhook_secret_set": true,
  "base_public_url": "https://xxxx.ngrok-free.app",
  "webhook_url": "https://xxxx.ngrok-free.app/api/v1/billing/mercadopago/webhook",
  "mp_client_id_set": false,
  "mp_api_reachable": true
}
```

---

## 5. Cómo levantar el túnel (ngrok)

El túnel es **necesario** para que Mercado Pago pueda enviarte webhooks en DEV.

### Opción A: ngrok como servicio Docker (recomendado)

1. Obtené tu token en https://dashboard.ngrok.com/authtokens
2. Creá `infra/.env` (o exportalo en tu shell):

```dotenv
NGROK_AUTHTOKEN=tu_token_de_ngrok_aqui
```

3. Levantá con el profile `tunnel`:

```bash
cd infra
docker compose --profile tunnel up
```

4. Obtené la URL pública del ngrok:

```bash
docker compose logs ngrok
# Buscá: url=https://xxxx-yy-zz.ngrok-free.app

# O abrí el dashboard ngrok:
open http://localhost:4040
```

5. Copiá la URL HTTPS y actualizá `services/api/.env`:

```dotenv
BASE_PUBLIC_URL=https://xxxx-yy-zz.ngrok-free.app
PUBLIC_MENU_BASE_URL=https://xxxx-yy-zz.ngrok-free.app
```

6. Reiniciá el API:

```bash
docker compose up api
```

### Opción B: ngrok manual (sin Docker)

```bash
# Instalar ngrok: https://ngrok.com/download
# O con scoop (Windows): scoop install ngrok
# O con brew (Mac): brew install ngrok

# Autenticar (una sola vez):
ngrok config add-authtoken TU_TOKEN

# Exponer el API (debe estar corriendo en 8000):
ngrok http 8000
```

Verás algo como:
```
Session Status: online
Account: tu@email.com
Forwarding: https://xxxx-yy-zz.ngrok-free.app -> http://localhost:8000
```

Copiá la URL `https://...` y actualizá `services/api/.env` → `BASE_PUBLIC_URL`.

### Alternativa: cloudflared (Cloudflare Tunnel)

```bash
# Instalar: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:8000
```

---

## 6. Configurar Credenciales TEST de Mercado Pago

1. Loguearse en https://www.mercadopago.com.ar/
2. Ir a **Tus integraciones** → **Credenciales**
3. Seleccionar la app (o crear una nueva)
4. Ir a la pestaña **Credenciales de prueba**
5. Copiar el **Access Token TEST** (empieza con `TEST-...`)
6. Pegarlo en `services/api/.env` como `MP_ACCESS_TOKEN`

> **Nunca** usar credenciales de producción en DEV/staging.

---

## 7. Crear cuentas de prueba en Mercado Pago

Necesitás dos cuentas TEST: una de **vendedor** y una de **comprador**.

1. Ir a https://www.mercadopago.com.ar/developers/panel/app
2. Seleccionar tu app → **Cuentas de prueba**
3. Crear cuenta **vendedor** (type: `SELLER`)
4. Crear cuenta **comprador** (type: `BUYER`)
5. Anotar los emails y contraseñas

> Al crear la preferencia y llegar al checkout, iniciar sesión con la cuenta **comprador**.
> La cuenta **vendedor** es la propietaria de las credenciales en uso.

### Tarjetas de prueba

Usar las tarjetas TEST de MP: https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/integration-test/test-cards

Ejemplo para Argentina:
- Visa aprobada: `4509953566233704`, vencimiento: `11/25`, CVV: `123`, DNI: `12345678`

---

## 8. Configurar Webhooks en el panel de MP

1. Ir a https://www.mercadopago.com.ar/developers/panel/app
2. Seleccionar tu app → **Webhooks**
3. **Modo:** Prueba (TEST)
4. **URL del webhook:** `https://xxxx.ngrok-free.app/api/v1/billing/mercadopago/webhook`
5. **Eventos a suscribir:** ✅ `Payments`
6. **Secret (firma):** Generar o copiar → pegar en `services/api/.env` como `MP_WEBHOOK_SECRET`
7. Guardar

> La URL del webhook debe ser la de ngrok (pública). No sirve `localhost`.

### Verificar que el webhook funciona

```bash
# Simular un webhook desde el panel MP (botón "Enviar notificación de prueba")
# O esperar a que llegue tras un pago TEST
docker compose logs -f api | grep TipWebhook
```

---

## 9. Configurar el Menú para activar propinas

Para que el botón "Propina" aparezca en la carta pública `/m/<slug>`:

1. Loguearse en el panel de Mirubro (http://localhost:3000)
2. Ir a **Menú** → **Configurar Menú** → **Interacción y Propinas**
3. Activar **Propinas**
4. Seleccionar modo: **Checkout Pro MP (Dinámico)** (`mp_oauth_checkout`)
5. Guardar

> **Nota DEV:** Con el modo `mp_oauth_checkout` y sin OAuth per-business configurado,
> el sistema automáticamente usará el `MP_ACCESS_TOKEN` global de `services/api/.env`.
> Esto es el comportamiento DEV. En producción, cada negocio debe conectar su propia cuenta MP via OAuth.

---

## 10. Flujo QA paso a paso

### Pre-requisitos
- [ ] `docker compose up --build` corriendo sin errores
- [ ] `MP_ACCESS_TOKEN=TEST-...` en `services/api/.env`
- [ ] Propinas activadas con modo `mp_oauth_checkout` en settings del menú
- [ ] (Para webhooks) ngrok corriendo y `BASE_PUBLIC_URL` actualizado

### Paso 1: Abrir la carta pública

```
http://localhost:3000/m/<tu-slug>
```

Debería ver el menú con un botón **💸 Propina** en la barra inferior.

### Paso 2: Crear preferencia de propina

Hacer click en **Propina** → seleccionar monto (ej. $1000) → click **"Propina de $1.000"**.

El frontend llama:
```
POST http://localhost:8000/api/v1/menu/public/slug/<slug>/tips/create-preference/
{ "amount": 1000, "table_ref": "" }
```

Respuesta esperada:
```json
{
  "tip_id": "uuid-...",
  "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=...",
  "external_reference": "TIP-XXXXXXXXXX"
}
```

El browser redirige a `init_point`.

### Paso 3: Pagar en Mercado Pago

- Iniciar sesión con la cuenta TEST **comprador**
- Usar una tarjeta TEST para pagar
- Debería redirigir a: `http://localhost:3000/m/<slug>/tip/success?tip_id=<id>`

### Paso 4: Verificar estado

La página `success` hace polling automático a:
```
GET http://localhost:8000/api/v1/menu/public/tips/<tip_id>/status/
```

Debería ver `"status": "approved"` si el webhook llegó, o `"pending"` si el webhook aún no procesó.

### Paso 5: Verificar webhook (con ngrok)

```bash
docker compose logs -f api | grep -E "TipWebhook|MPWebhook"
# [TipWebhook] TIP-XXXX → approved (mp_payment_id=12345)
```

O verificar en la DB:
```bash
docker compose exec api python manage.py shell -c "
from apps.menu.models import TipTransaction
t = TipTransaction.objects.last()
print(t.external_reference, t.status, t.mp_payment_id)
"
```

---

## 11. Comandos curl de referencia

### Health Check
```bash
curl http://localhost:8000/api/v1/health/
```

### DEV MP Ping
```bash
curl http://localhost:8000/api/v1/billing/dev/mercadopago/ping | python -m json.tool
```

### Obtener menú público
```bash
curl http://localhost:8000/api/v1/menu/public/slug/<slug>/
```

### Crear preferencia de propina
```bash
curl -X POST http://localhost:8000/api/v1/menu/public/slug/<slug>/tips/create-preference/ \
  -H "Content-Type: application/json" \
  -d '{"amount": 500, "table_ref": "mesa-5"}'
```

### Consultar status de propina
```bash
curl http://localhost:8000/api/v1/menu/public/tips/<tip_id>/status/
```

### Simular webhook (sin firma — DEV con MP_WEBHOOK_SECRET vacío)
```bash
curl -X POST http://localhost:8000/api/v1/billing/mercadopago/webhook \
  -H "Content-Type: application/json" \
  -d '{"type": "payment", "data": {"id": "12345678"}}'
```

---

## 12. Checklist de validación

### Configuración
- [ ] `MP_ACCESS_TOKEN` setteado en `services/api/.env` (valor TEST)
- [ ] `docker compose up` inicia sin errores
- [ ] `GET /api/v1/health/` retorna 200
- [ ] `GET /api/v1/billing/dev/mercadopago/ping` muestra `mp_api_reachable: true`
- [ ] Propinas habilitadas en el panel con modo `mp_oauth_checkout`

### Flujo básico (sin webhooks)
- [ ] `/m/<slug>` muestra botón "Propina"
- [ ] Click → modal con presets y campo custom
- [ ] Confirmar → redirige a `init_point` de Mercado Pago
- [ ] Pagar con cuenta TEST → redirige a `/m/<slug>/tip/success`
- [ ] Página success muestra estado (puede ser `pending` si no hay webhook)
- [ ] Página failure tiene botón "Intentar de nuevo"

### Flujo completo (con webhooks — requiere ngrok)
- [ ] ngrok corriendo y URL actualizada en `BASE_PUBLIC_URL`
- [ ] Panel MP tiene webhook apuntando a `https://<ngrok>/api/v1/billing/mercadopago/webhook`
- [ ] Pago TEST → webhook llega a la API (ver logs)
- [ ] `TipTransaction.status` cambia a `approved`
- [ ] Página success muestra `approved`

### Robustez
- [ ] Sin `MP_ACCESS_TOKEN` → create-preference retorna 503 con mensaje claro
- [ ] Sin `BASE_PUBLIC_URL` → warning en logs (no crash); back_urls pueden no funcionar correctamente
- [ ] Webhook duplicado → idempotente (segundo POST devuelve 200 sin procesar)
- [ ] Propinas deshabilitadas → create-preference retorna 400

---

## 13. Troubleshooting

### El API no arranca: `Settings.BASE_URL` AttributeError
**Solución:** Este bug fue corregido en este PR. Reconstruir el container: `docker compose up --build api`.

### `docker compose up` falla: `env_file ../apps/web/.env not found`
**Solución:** El archivo `apps/web/.env` ya fue creado en este PR. Si sigue fallando:
```bash
touch apps/web/.env
```

### `create-preference` retorna 503: "Pago no disponible"
**Causa:** `MP_ACCESS_TOKEN` no está en `services/api/.env`.  
**Solución:** Agregar credencial TEST.

### `create-preference` retorna 400: "Propinas dinámicas no habilitadas"
**Causa:** El menú no tiene `tips_enabled=True` y `tips_mode=mp_oauth_checkout`.  
**Solución:** Configurar en el panel: Menú → Interacción → Propinas → Modo Checkout Pro.

### El browser redirige a `init_point` pero la URL de retorno es `localhost`
**Causa:** `PUBLIC_MENU_BASE_URL` está como `http://localhost:3000`.  
**Comportamiento esperado en DEV sin ngrok:** las `back_urls` apuntarán a localhost, lo que es correcto si el browser accede desde localhost. Solo fallará si accedés desde otro dispositivo.  
**Solución para testing en otro dispositivo:** usar ngrok para el frontend también.

### El webhook llega a ngrok pero no a la API
**Causa posible:** La URL del webhook en el panel MP usa el hostname equivocado.  
**Verificar:** `docker compose logs ngrok` y confirmar que la URL en el panel MP coincide exactamente.

### `mp_api_reachable: false` en el ping
**Causa:** Token incorrecto o expirado.  
**Solución:** Regenerar credenciales TEST en https://www.mercadopago.com.ar/developers → Credenciales.

### El webhook devuelve 400: "Invalid signature"
**Causa:** `MP_WEBHOOK_SECRET` no coincide con el configurado en el panel MP (o la firma está mal calculada).  
**DEV bypass:** Dejar `MP_WEBHOOK_SECRET=` vacío en `.env` — el sistema loguea warning pero acepta el webhook.
