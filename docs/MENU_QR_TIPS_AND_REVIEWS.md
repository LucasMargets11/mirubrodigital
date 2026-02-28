# Propinas y Reseñas Google — Menu QR Online

Documentación técnica completa de las funcionalidades de **Propina (Mercado Pago)** y **Reseñas Google** para la carta digital (Menu QR Online) de Mirubro.

---

## Índice

1. [Resumen de funcionalidades](#1-resumen-de-funcionalidades)
2. [Variables de entorno](#2-variables-de-entorno)
3. [Modelos de datos](#3-modelos-de-datos)
4. [Feature flags y planes](#4-feature-flags-y-planes)
5. [Endpoints backend](#5-endpoints-backend)
6. [Flujo Fase 1 — Links / QR provistos por el negocio](#6-flujo-fase-1--links--qr-provistos-por-el-negocio)
7. [Flujo Fase 2 — Checkout Dinámico con MP OAuth](#7-flujo-fase-2--checkout-dinámico-con-mp-oauth)
8. [Webhook de Mercado Pago](#8-webhook-de-mercado-pago)
9. [Frontend — Panel de configuración](#9-frontend--panel-de-configuración)
10. [Frontend — Carta pública (CTAs)](#10-frontend--carta-pública-ctas)
11. [Páginas de resultado de propina](#11-páginas-de-resultado-de-propina)
12. [Google Reviews](#12-google-reviews)
13. [Testing y QA](#13-testing-y-qa)
14. [Checklist QA completo](#14-checklist-de-qa-completo)

---

## 1. Resumen de funcionalidades

| Funcionalidad                        | Plan mínimo       | Modo              |
|--------------------------------------|-------------------|-------------------|
| Link de propina MP (URL arbitraria)  | `menu_qr`         | Fase 1 – Link     |
| QR de propina como imagen            | `menu_qr`         | Fase 1 – QR Image |
| Checkout dinámico MP (OAuth)         | `menu_qr_marca`   | Fase 2 – Pro      |
| Reseñas Google (Place ID o URL)      | `menu_qr`         | Fase 1            |

---

## 2. Variables de entorno

### Backend (`services/api/.env`)

```env
# Mercado Pago — integración global (pagos de suscripción)
MP_ACCESS_TOKEN=APP_USR-...
MP_WEBHOOK_SECRET=tu_webhook_secret

# Mercado Pago — OAuth por negocio (Fase 2 Pro)
MP_CLIENT_ID=tu_client_id
MP_CLIENT_SECRET=tu_client_secret
MP_REDIRECT_URI=https://tu-dominio.com/api/v1/menu/mercadopago/connect/callback/

# Base URLs
FRONTEND_URL=https://tu-dominio.com
PUBLIC_MENU_BASE_URL=https://tu-dominio.com   # Si es diferente al frontend principal
```

### Frontend (`apps/web/.env.local`)

No se requieren variables adicionales. Las llamadas a la API usan el cliente interno con `credentials: 'include'`.

---

## 3. Modelos de datos

### `MenuEngagementSettings`

Configuración de propinas y reseñas por negocio. Relación `OneToOne` con `Business`.

| Campo               | Tipo         | Descripción                                                      |
|---------------------|--------------|------------------------------------------------------------------|
| `business`          | OneToOne FK  | Business propietario                                             |
| `tips_enabled`      | Boolean      | Si las propinas están activas                                    |
| `tips_mode`         | CharField    | `mp_link` / `mp_qr_image` / `mp_oauth_checkout`                 |
| `mp_tip_url`        | URL nullable | URL de propina MP (modo `mp_link`)                               |
| `mp_qr_image`       | ImageField   | Imagen QR subida (modo `mp_qr_image`). Path: `media/menu/tips/qr/` |
| `reviews_enabled`   | Boolean      | Si el CTA de reseñas está activo                                 |
| `google_place_id`   | CharField    | Place ID de Google Maps                                          |
| `google_review_url` | URLField     | URL directa de reseña (alternativa al Place ID)                  |

**Propiedad calculada** `google_write_review_url`:
- Si hay `google_place_id` → `https://search.google.com/local/writereview?placeid={place_id}`
- Si no → valor de `google_review_url`

### `MercadoPagoConnection`

Tokens OAuth por negocio. Relación `OneToOne` con `Business`.

| Campo              | Tipo        | Descripción                                         |
|--------------------|-------------|-----------------------------------------------------|
| `business`         | OneToOne FK | Business propietario                                |
| `access_token`     | TextField   | Token de acceso del negocio en MP                   |
| `refresh_token`    | TextField   | Token de refresco                                   |
| `token_expires_at` | DateTime    | Vencimiento del `access_token`                      |
| `mp_user_id`       | CharField   | User ID del negocio en MP                           |
| `scope`            | CharField   | Scopes otorgados                                    |
| `status`           | CharField   | `connected` / `expired` / `revoked` / `error`       |
| `last_error`       | TextField   | Último mensaje de error                             |

> ⚠️ **Seguridad**: Los tokens **nunca** se exponen en API responses. El endpoint de status solo retorna `connected`, `status`, `mp_user_id`, `updated_at`.

### `TipTransaction`

Registro de cada transacción de propina (Fase 2 Pro).

| Campo                | Tipo        | Descripción                                                       |
|----------------------|-------------|-------------------------------------------------------------------|
| `id`                 | UUID (PK)   | ID único de la transacción                                        |
| `business`           | FK          | Business receptor                                                 |
| `amount`             | Decimal     | Monto de la propina                                               |
| `currency`           | CharField   | Moneda (default `ARS`)                                            |
| `status`             | CharField   | `created` / `pending` / `approved` / `rejected` / `cancelled`    |
| `mp_preference_id`   | CharField   | ID de preferencia creada en MP                                    |
| `mp_payment_id`      | CharField   | ID de pago confirmado por webhook                                 |
| `external_reference` | CharField   | Referencia única en formato `TIP-{hex12}` (único global)          |
| `menu_slug`          | CharField   | Slug del menú desde donde se originó                             |
| `table_ref`          | CharField   | Referencia de mesa (opcional, ej. "M4")                          |

---

## 4. Feature flags y planes

Definidos en `services/api/src/apps/business/features.py`:

| Feature Key          | Descripción                                             |
|----------------------|---------------------------------------------------------|
| `menu_qr_reviews`    | Habilita configuración de reseñas Google                |
| `menu_qr_tips`       | Habilita propinas Fase 1 (link / QR image)              |
| `menu_qr_tips_pro`   | Habilita checkout dinámico MP OAuth (Fase 2 Pro)        |

**Asignación por plan:**

| Plan             | `menu_qr_reviews` | `menu_qr_tips` | `menu_qr_tips_pro` |
|------------------|:-----------------:|:--------------:|:------------------:|
| `menu_qr`        | ✅ | ✅ | ❌ |
| `menu_qr_visual` | ✅ | ✅ | ❌ |
| `menu_qr_marca`  | ✅ | ✅ | ✅ |
| `plus` (compat.) | ✅ | ✅ | ❌ |

---

## 5. Endpoints backend

### Privados (requieren auth + permisos `manage_menu`)

| Método   | URL                                              | Descripción                        |
|----------|--------------------------------------------------|------------------------------------|
| `GET`    | `/api/v1/menu/engagement/`                       | Leer configuración engagement      |
| `PATCH`  | `/api/v1/menu/engagement/`                       | Actualizar configuración           |
| `POST`   | `/api/v1/menu/engagement/upload-qr/`             | Subir imagen QR de propina         |
| `GET`    | `/api/v1/menu/mercadopago/connect/status/`       | Estado de conexión OAuth MP        |
| `GET`    | `/api/v1/menu/mercadopago/connect/start/`        | Iniciar flujo OAuth MP             |
| `GET`    | `/api/v1/menu/mercadopago/connect/callback/`     | Callback OAuth MP                  |
| `DELETE` | `/api/v1/menu/mercadopago/connect/`              | Desconectar cuenta MP              |

### Públicos (sin autenticación)

| Método | URL                                                            | Descripción                          |
|--------|----------------------------------------------------------------|--------------------------------------|
| `GET`  | `/api/v1/menu/public/slug/{slug}/`                            | Carta pública (incluye `engagement`) |
| `POST` | `/api/v1/menu/public/slug/{slug}/tips/create-preference/`     | Crear preferencia de pago (propina)  |
| `GET`  | `/api/v1/menu/public/tips/{uuid}/status/`                     | Consultar estado de una propina      |

---

## 6. Flujo Fase 1 — Links / QR provistos por el negocio

### Modo `mp_link`

1. Admin va a **Configuración → Carta Online → Propinas y Reseñas**
2. Activa "Propinas" y selecciona **"Enlace MP"**
3. Pega su link de Mercado Pago (ej. `https://mpago.la/xxxxx`) → Guardar

En la carta pública (`/m/{slug}/`):
- Aparece el botón **"Dejar propina"** en la barra inferior
- Clic → abre el link en nueva pestaña

### Modo `mp_qr_image`

1. Admin activa "Propinas" y selecciona **"QR de imagen"**
2. Sube imagen QR (JPEG/PNG/GIF, máx 5 MB) → Guardar

En la carta pública:
- Clic en **"Dejar propina"** → abre modal con la imagen QR
- El cliente escanea con su teléfono
- Modal incluye link "Abrir en MP" si también hay `mp_tip_url` configurada

---

## 7. Flujo Fase 2 — Checkout Dinámico con MP OAuth

### Paso 1: Conectar cuenta MP del negocio

```
Admin panel → "Conectar Mercado Pago"
    ↓
GET /api/v1/menu/mercadopago/connect/start/
    ↓ genera state token (almacenado en cache 10 min)
Redirect → https://auth.mercadopago.com/authorization?client_id=...&state=...
    ↓ usuario autoriza en MP
GET /api/v1/menu/mercadopago/connect/callback/?code=...&state=...
    ↓ valida state (CSRF protection)
    ↓ POST https://api.mercadopago.com/oauth/token
    ↓ guarda MercadoPagoConnection
Redirect → /app/settings/online-menu?mp_connected=1
    ↓
Panel muestra "🟢 Conectado"
```

### Paso 2: El cliente deja propina

```
Carta /m/{slug}/ → botón "Dejar propina"
    ↓
TipAmountSelector: selecciona/ingresa monto
    ↓
POST /api/v1/menu/public/slug/{slug}/tips/create-preference/
     { "amount": "500.00", "table_ref": "M4" }
    ↓ backend verifica conexión MP activa
    ↓ crea TipTransaction (external_reference = TIP-{hex})
    ↓ llama sdk.preference().create() con access_token del negocio
    ↓ back_urls configuradas:
        success  → /m/{slug}/tip/success?tip_id={uuid}
        pending  → /m/{slug}/tip/pending?tip_id={uuid}
        failure  → /m/{slug}/tip/failure
    ↓ retorna { tip_id, init_point, external_reference }
Frontend → window.location.href = init_point
    ↓ cliente paga en portal MP
MP redirige según resultado → páginas de resultado
```

---

## 8. Webhook de Mercado Pago

### URL del webhook

```
https://tu-dominio.com/api/v1/billing/mercadopago/webhook/
```

Configurar en el portal de Mercado Pago (cuenta de la plataforma).

### Ruteo por `external_reference`

| Prefijo                  | Handler                    |
|--------------------------|----------------------------|
| `subscription_change_`   | `process_subscription_change()` |
| `addon_purchase_`        | `process_addon_purchase()` |
| `TIP-`                   | `process_tip_payment()` ← **nuevo** |

### Lógica de `process_tip_payment()`

1. Busca `TipTransaction.objects.get(external_reference=ref)`
2. Mapea status MP → status interno:

| Status MP                              | Status interno |
|----------------------------------------|----------------|
| `approved`                             | `approved`     |
| `pending`, `in_process`, `authorized` | `pending`      |
| `rejected`                             | `rejected`     |
| `cancelled`, `refunded`, `charged_back`| `cancelled`    |

3. Actualiza `mp_payment_id` y `status` (idempotente)

### Testing con ngrok

```bash
# Exponer backend local
ngrok http 8000

# Simular webhook manualmente
curl -X POST https://{ngrok-id}.ngrok.io/api/v1/billing/mercadopago/webhook/ \
  -H "Content-Type: application/json" \
  -d '{"type":"payment","data":{"id":"TEST_PAYMENT_ID"}}'
```

---

## 9. Frontend — Panel de configuración

**Ruta:** `/app/settings/online-menu` → sección _"Propinas y Reseñas"_

**Componente:** `apps/web/src/components/app/engagement-settings-section.tsx`

### Sección Propinas (requiere `menu_qr_tips`)

| Control                | Descripción                                             |
|------------------------|---------------------------------------------------------|
| Toggle activo          | Activa/desactiva la funcionalidad                       |
| Selector de modo       | 3 botones: Enlace MP / QR Imagen / Checkout Dinámico    |
| Campo URL (link)       | URL de MP + botón "Probar link"                         |
| Upload QR (imagen)     | Input file + preview de imagen                         |
| Bloque OAuth (pro)     | Badge estado MP + botones conectar/desconectar          |

### Sección Reseñas Google (requiere `menu_qr_reviews`)

| Control                | Descripción                                             |
|------------------------|---------------------------------------------------------|
| Toggle activo          | Activa/desactiva la funcionalidad                       |
| Google Place ID        | Campo + link ayuda                                      |
| URL de reseña directa  | Alternativa al Place ID                                 |
| Preview URL            | Muestra la URL de reseña resultante                     |

---

## 10. Frontend — Carta pública (CTAs)

**Componente:** `apps/web/src/components/public-menu/menu-layout.tsx`

### `StickyCTABar`

Barra fija en la parte inferior. Visible cuando hay al menos un CTA activo.

```
[ ⭐ Dejar reseña ]   [ 💰 Dejar propina ]
```

### Comportamiento por modo

| Modo                 | Acción al tocar "Dejar propina"             |
|----------------------|---------------------------------------------|
| `mp_link`            | `window.open(mp_tip_url, '_blank')`         |
| `mp_qr_image`        | Abre `QRModal` con imagen QR               |
| `mp_oauth_checkout`  | Abre `TipAmountSelector`                   |

### Subcomponentes

- **`QRModal`**: Modal accesible con imagen QR, backdrop+X para cerrar, tecla Escape
- **`TipAmountSelector`**: Modal con botones $200/$500/$1000 + input libre, llama a `createPublicTipPreference()` y redirige a `init_point`

---

## 11. Páginas de resultado de propina

### `/m/[slug]/tip/success?tip_id={uuid}`

- Llama `getPublicTipStatus(tipId)` al montar
- Hace polling cada 3s (máx. 10 intentos) si status es `created`/`pending`
- Muestra monto y estado (`approved` → confetti, `pending` → icono reloj)
- CTA: "Volver a la carta"

### `/m/[slug]/tip/pending?tip_id={uuid}`

- Muestra "Tu pago está en proceso"
- CTA: "Verificar estado" → `/tip/success?tip_id=...`
- CTA: "Volver a la carta"

### `/m/[slug]/tip/failure`

- Muestra "El pago no se completó"
- CTA: "Intentar de nuevo" → `/m/{slug}?retry_tip=1`
- CTA: "Volver a la carta"

---

## 12. Google Reviews

### Cómo obtener el Place ID

1. Ir a [Google Maps](https://maps.google.com)
2. Buscar el negocio
3. Hacer clic derecho → "¿Qué hay aquí?" → copiar el `place_id` de la URL/panel
4. O usar el [Place ID Finder oficial](https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder)

### Cómo obtener la URL de reseña directa

1. Buscar el negocio en Google Maps
2. Clic en "Escribir una reseña"
3. Copiar la URL del navegador

### URL generada automáticamente

```
https://search.google.com/local/writereview?placeid={google_place_id}
```

---

## 13. Testing y QA

### Setup local

```bash
# Backend: aplicar nuevas migraciones
cd services/api
python manage.py migrate

# Verificar modelos
python manage.py shell -c "
from apps.menu.models import MenuEngagementSettings, MercadoPagoConnection, TipTransaction
print('Models OK:', MenuEngagementSettings, MercadoPagoConnection, TipTransaction)
"
```

### Probar feature flags

```python
from apps.business.features import has_feature
from apps.business.models import Business

biz = Business.objects.get(pk=1)
print(has_feature(biz, 'menu_qr_tips'))        # True si plan menu_qr+
print(has_feature(biz, 'menu_qr_tips_pro'))    # True solo menu_qr_marca
print(has_feature(biz, 'menu_qr_reviews'))     # True si plan menu_qr+
```

### Probar endpoints con curl

```bash
# Usar cookie de sesión autenticada
COOKIE="sessionid=xxx"

# Leer engagement settings
curl -b "$COOKIE" http://localhost:8000/api/v1/menu/engagement/

# Actualizar (modo link)
curl -b "$COOKIE" -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"tips_enabled":true,"tips_mode":"mp_link","mp_tip_url":"https://mpago.la/test"}' \
  http://localhost:8000/api/v1/menu/engagement/

# Carta pública (verificar que devuelve engagement)
curl http://localhost:8000/api/v1/menu/public/slug/mi-restaurante/ | jq '.engagement'

# Crear preferencia de propina (Fase 2)
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"amount":"500"}' \
  http://localhost:8000/api/v1/menu/public/slug/mi-restaurante/tips/create-preference/
```

---

## 14. Checklist de QA completo

### Fase 1 — Link / QR

- [ ] Admin puede activar/desactivar propinas
- [ ] Admin configura URL de link MP; "Probar link" abre en nueva pestaña
- [ ] Admin sube imagen QR (< 5 MB JPEG/PNG/GIF); se previsualiza
- [ ] CTA "Dejar propina" aparece en carta pública cuando `tips_enabled=true`
- [ ] Modo `mp_link`: clic abre link en nueva pestaña
- [ ] Modo `mp_qr_image`: clic abre modal con QR; modal cierra con X/backdrop/Escape
- [ ] CTA no aparece cuando `tips_enabled=false`
- [ ] Admin configura Google Place ID o URL de reseña
- [ ] CTA "Dejar reseña" aparece cuando `reviews_enabled=true`
- [ ] Clic abre URL de reseña Google en nueva pestaña
- [ ] CTA no aparece cuando `reviews_enabled=false`
- [ ] Sin plan/features debidas → opciones no visibles en panel

### Fase 2 — Checkout Dinámico MP OAuth

- [ ] "Conectar Mercado Pago" redirige correctamente al portal OAuth de MP
- [ ] Callback OAuth guarda `MercadoPagoConnection` con status `connected`
- [ ] Panel muestra badge "🟢 Conectado" tras conectar
- [ ] "Desconectar" elimina la conexión; badge vuelve a "⚪ No conectado"
- [ ] Modo `mp_oauth_checkout`: clic abre `TipAmountSelector`
- [ ] Botones rápidos $200/$500/$1000 son seleccionables
- [ ] Campo libre acepta montos entre $10 y $50.000
- [ ] Clic "Propinar" con negocio conectado redirige a MP checkout
- [ ] Página `/tip/success?tip_id=...` muestra monto y estado
- [ ] Polling confirma `approved` tras webhook
- [ ] Página `/tip/pending` muestra estado e invita a verificar
- [ ] Página `/tip/failure` permite reintentar
- [ ] Webhook con prefijo `TIP-` actualiza `TipTransaction.status`

### Seguridad

- [ ] State token OAuth validado en callback (CSRF protection)
- [ ] `external_reference` único globalmente (constraint DB)
- [ ] `access_token`/`refresh_token` nunca en API responses
- [ ] Upload QR rechaza archivos no-imagen
- [ ] Upload QR rechaza archivos > 5 MB
- [ ] Monto propina validado server-side (min 10, max 50000)
- [ ] Propinas de negocio A no visibles para negocio B (multi-tenant)
