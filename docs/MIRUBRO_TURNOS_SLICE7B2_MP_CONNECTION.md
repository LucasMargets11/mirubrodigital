# MiRubro Turnos — Slice 7B.2: conexión Mercado Pago desde Turnos

Un Business con solo `appointments` puede ver, conectar, reconectar y desconectar
su cuenta Mercado Pago desde `/app/turnos/configuracion`, sin pasar por Menú QR.

Se reutiliza **una sola** `MercadoPagoConnection` por Business
(`apps.merchant_payments`), compartida por Propinas (Menú) y señas de Turnos.
No hay tablas, tokens ni endpoints específicos de Turnos. Checkout, webhooks,
cifrado y ciclo de vida de tokens no cambian.

## Backend (`apps/merchant_payments/views.py`)

- `GET connect/start/?context=appointments|menu`
  - `context` es un valor cerrado; ausente ⇒ `menu` (compatibilidad). Cualquier
    otro valor ⇒ `400`, sin crear `state`.
  - El cache guarda `{'business_id', 'context'}` asociado al `state` (TTL 10 min).
    El Business sale de la sesión (`request.business`), nunca del cliente.
- `GET connect/callback/`
  - Consume el `state` **atómicamente** (`_consume_state`: solo quien logra el
    `cache.delete` lo usa) — también cuando MP devuelve `error` (cancelación).
  - Ignora cualquier parámetro extra (`business_id`, `return_url`, `next`, …).
  - Redirect solo a dos paths internos fijos:

    | context        | éxito                                      | error                                           |
    |----------------|--------------------------------------------|-------------------------------------------------|
    | `appointments` | `/app/turnos/configuracion?mp=connected`   | `/app/turnos/configuracion?mp=error` (sin motivo) |
    | `menu`         | `/app/settings/online-menu?mp_connected=1` | `/app/settings/online-menu?mp_error=<motivo>` (sin cambios) |

  - Entradas de cache previas a 7B.2 (valor = id entero, `state` válido) ⇒
    contexto `menu` (solo Menú iniciaba OAuth antes).
  - **7B.2.1** — sin `state` válido (faltante, expirado, reutilizado, o error/
    cancelación de MP sin `state`) el producto de origen es desconocido ⇒
    `/app?mp=error` (home neutral), nunca una página exclusiva de Menú. Antes
    iba a `/app/settings/online-menu?mp_error=state_expired|missing_params`.
- Status / disconnect: semántica sin cambios (5B.3B); permisos en la sección siguiente.

## Permisos (7B.2.1)

| acción              | owner | admin | manager | viewer |
|---------------------|:-----:|:-----:|:-------:|:------:|
| start OAuth         | ✓     | ✓     | 403     | 403    |
| disconnect          | ✓     | ✓     | 403     | 403    |
| status (solo lectura) | ✓   | ✓     | ✓       | 403    |

- start/disconnect: `manage_settings` **y** `IsBusinessOwnerOrAdmin` (rol de la
  membresía resuelta para el Business actual). Aplica a todos los productos que
  comparten la conexión (también Menú/Propinas).
- status: sigue con `manage_settings`.
- UI de Turnos: manager ve el estado sin botones; viewer ve solo un aviso.
  La card de Propinas de Menú no se ajustó: un manager de restaurante ve el botón
  y recibe el 403 del backend.

## Frontend

- `features/merchant-payments/{api,types}.ts`: cliente único de los endpoints;
  `features/menu/api.ts` y `features/menu/types.ts` lo re-exportan (Menú sigue
  llamando `startMercadoPagoOAuth()` ⇒ `context=menu`).
- `features/merchant-payments/mercado-pago-connection-card.tsx`: card de Turnos
  (no conectado / conectado + ID de cuenta / reconectar / error de carga).
  La card de Propinas de Menú (`engagement-settings-section.tsx`) no se tocó:
  está embebida en el formulario de propinas y extraerla era un refactor mayor.
- Ruta `app/app/turnos/configuracion/page.tsx`; link "Configuración" en el
  sidebar de Turnos (`manage_settings`) y acceso desde el inicio de Turnos.

## Deuda

- **Rutas legacy**: los endpoints siguen bajo `/api/v1/menu/mercadopago/connect/…`
  (el callback es el redirect URI registrado en la app de MP). Canonicalizar a un
  prefijo neutro (p. ej. `/api/v1/merchant-payments/mercadopago/…`) requiere
  alias + actualización del redirect URI en MP; fuera de este slice.
- El landing de Menú (`/app/settings/online-menu`) redirige a `/app/carta`, por lo
  que los query params `mp_connected`/`mp_error` probablemente no llegan a la card
  de Propinas (preexistente, no tocado).
- `AppShell`: las allowlists por servicio incluyen `/app` y `pathMatches` lo
  trata como prefijo, así que no restringen ninguna ruta `/app/*` (preexistente).
