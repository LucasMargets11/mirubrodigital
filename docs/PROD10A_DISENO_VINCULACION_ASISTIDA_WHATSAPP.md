# PROD-10A — Auditoría y diseño de vinculación asistida de WhatsApp

Fecha: 2026-11-28 · Mi Rubro `feat/recepcionista` @ `40049f3` · Bot
`agenterecep-lead-handoff` (`feat/recepcionista`) @ `de7e932`, solo lectura.

Este slice es solo de revisión, diseño y regresión. No se cambió código
funcional, no se llamó a Meta y no se tocaron credenciales reales.

## 1. Infraestructura reutilizable

### Mi Rubro (`apps.leads`)

| Pieza | Qué ya hace | Estado |
|---|---|---|
| `AgentInstance` | Instancia del bot (`external_id`, `is_enabled`) | Una instancia compartida sirve a muchos negocios. Se reutiliza tal cual |
| `AgentCredential` | Secreto HMAC agente ↔ Mi Rubro, cifrado | Independiente de Meta. No se toca |
| `AgentChannel` | Número de Meta (`phone_number_id`) → Business + instancia. Tiene `waba_id` y FK `whatsapp_authorization` (RESTRICT) | `UniqueConstraint (provider, phone_number_id)` **activo único global**; formato de pnid y WABA validado; `save()` exige que el dueño de la autorización sea el Business del canal |
| `WhatsAppAuthorization` | Token de Meta cifrado (`encrypted_access_token`), `owner_business` nullable (null = plataforma), `status` active/revoked/invalid, `expires_at`, `revoked_at` | Hay constraints de estado, de cifrado (prefijo Fernet) y de coherencia de revocación |
| `crypto.encrypt_agent_secret` / `decrypt_agent_secret` | Fernet con `AGENT_SECRET_ENCRYPTION_KEY` | **Sin MultiFernet**: no hay rotación de la clave maestra |
| `services/whatsapp_authorizations.py` | `create_whatsapp_authorization`, `associate_channel`, `rotate_whatsapp_authorization`, `revoke_whatsapp_authorization` | Actor de plataforma obligatorio, orden de locks autorización → canal, auditoría `WHATSAPP_AUTHORIZATION_*` (accounts/0036). Rotar es en el lugar; revocar es **solo local** (`meta_revocation=not_performed`) |
| `channel_credential_problem(channel, now)` | Regla única y pura (nunca descifra) | La comparten la entrega al bot (04C) y el estado admin (08E1). Códigos: `channel_not_active`, `whatsapp_authorization_missing\|owner_mismatch\|revoked\|invalid\|expired`, `whatsapp_waba_missing` |
| `GET /api/v1/integrations/agent/channels/<pnid>/whatsapp-credential/` | Entrega al bot con HMAC fail-closed, nonce, throttle y `no-store` | Errores 403 con el código; descifrado fallido da 503 |
| `provision_agent` (management command) | Crea instancia, credencial HMAC y canal; crea, asocia, rota o revoca autorizaciones | **Solo por shell.** El token llega por stdin o env. Si el pnid está activo en otro canal: «Desactivarlo primero», pero **no existe operación de desactivar** |
| `GET platform-admin/clients/<id>/whatsapp-connections/` (08E1) | Canales del Business, bloque de autorización (sin token) y `local_status` | `external_verification: {performed:false, meta_connectivity:'unknown'}`. Gate `admin_reception_business` |
| `whatsapp_metrics` (02E4C) | `sync_observed`, mensajes sincronizados por Business | Es la única señal de tráfico real disponible |
| `ReceptionistConfig.automatic_attention_enabled` (09C1/09C3) | Habilitación operativa, solo desde admin | Independiente del canal. Las bajas la pausan (09D1) |

### Frontend

- `AdminWhatsAppConnectionsSection`, dentro de `ReceptionistAdminCard`: un
  único `Providers`, `useAdminWhatsAppConnections`, refresco manual y mapa
  `LOCAL_STATUS`.
- Ya existen `Modal`, `Button`, `SectionCard`, `apiPost`/`ApiError` y el
  patrón de rol superadmin desde la sesión del servidor (09D2/09E).

### Bot (`de7e932`)

- **Una sola app de Meta:** `WHATSAPP_APP_SECRET` y `WHATSAPP_VERIFY_TOKEN`
  globales, que es lo correcto para una app central.
- **Verificación del webhook:** `GET` con `hub.mode`/`hub.verify_token`/`hub.challenge`.
  El `POST` se valida con HMAC-SHA256 y `timingSafeEqual`
  (`whatsapp-signature.guard.ts`).
- **Resolución por `phone_number_id`:** en cada operación, sin caché
  (06A/06B/07A). Una falla transitoria devuelve 500 para que Meta reintente;
  una definitiva registra `CHANNEL REJECTED` y devuelve 200.
- **Envío:** `sendTextMessage(channel)` re-resuelve la credencial, verifica
  que el Business coincida y nunca usa un token global.
  - Un 401 de Meta o los códigos 190/10/200 se registran como
    `META AUTHORIZATION REJECTED`, pero **no se informan a Mi Rubro**.
- **Graph:** `WHATSAPP_GRAPH_VERSION` por defecto `v23.0`.
- **Atención:** depende de que la config esté `ready` y
  `automatic_attention_enabled`, con verificación estricta antes de cada
  envío (09C2.1).

**Conclusión:** almacenamiento, cifrado, aislamiento, entrega, resolución
dinámica y estado local ya existen. Faltan:
- La **obtención y verificación** de recursos en Meta.
- Las **operaciones administrativas por HTTP**, hoy solo hay shell.
- La **desactivación de canales**.
- El **estado verificado** distinto del local.

## 2. Flujo de vinculación asistida propuesto

**Idea central:** una sola operación de servidor, *vincular recursos de
WhatsApp a un Business*, con dos formas de obtener la autorización:

- **Asistida (PROD-10):** un superadmin ingresa WABA ID, Phone Number ID y un
  token **del cliente**.
- **Embedded Signup (PROD-11):** se obtiene el *business token* por
  intercambio del `code`.

Después de la obtención todo es idéntico: verificación, almacenamiento,
asociación, webhook, auditoría y uso por el bot.

### 2.1 Datos de entrada

| Dato | Origen | Validación local |
|---|---|---|
| `business_id` | Ruta del detalle admin. Nunca del body ni de `bid` | HQ con Recepcionista no cancelada (`admin_reception_business`) |
| `waba_id` | Cliente (WhatsApp Manager) o evento de Embedded Signup | Regex existente `WABA_ID_REGEX` |
| `phone_number_id` | Ídem | Regex existente; único activo global |
| Token de acceso | Asistida: token de system user del portafolio del cliente. ES: *business token* | Solo POST sobre HTTPS; nunca se devuelve, registra ni audita |
| `expires_at` | Opcional (asistida). ES: el que devuelva `debug_token` | `_validate_expiry` existente |
| `reason` | Admin | Obligatorio, 255 caracteres como máximo |

### 2.2 Secuencia (servidor, en este orden)

1. **Autorización y gate.**
   - El actor es superadmin; se reutiliza `_require_admin` endureciéndolo a
     superadmin para escritura.
   - Business HQ con Recepcionista.
   - El `phone_number_id` no está activo en **otro** canal: 409
     `phone_number_in_use`, sin revelar a qué negocio pertenece.
2. **Verificación en Meta**, solo lecturas e idempotente, antes de escribir
   nada:
   - `GET /debug_token?input_token=<token>` con **app access token**
     (`app_id|app_secret`). Se exige:
     - `is_valid=true`.
     - Que `app_id` sea nuestra app.
     - `scopes` con `whatsapp_business_management` y `whatsapp_business_messaging`.
     - Que `granular_scopes[].target_ids` incluya el `waba_id`, o que no
       tenga targets si el permiso cubre todo.
     - Se toman `expires_at` y `data_access_expires_at`.
   - `GET /<WABA_ID>/phone_numbers` con el token: el `phone_number_id` debe
     pertenecer a esa WABA. Se guardan como metadatos no secretos
     `display_phone_number`, `verified_name`, `code_verification_status`,
     `quality_rating` y `platform_type` (se espera `CLOUD_API`).
   - `GET /<WABA_ID>/subscribed_apps`: indica si nuestra app ya está
     suscripta.
3. **Escritura local, en una transacción:**
   - `create_whatsapp_authorization(owner_business=business)`. **Nunca**
     `platform=True` en este flujo.
   - Crear o reutilizar el `AgentChannel` en la instancia compartida.
   - `associate_channel(waba_id)`.
   - Registrar la verificación (§4).
   - Auditar.
4. **Webhook**, paso explícito e idempotente:
   - `POST /<WABA_ID>/subscribed_apps` con el token del cliente, **sin
     override**. La app central entrega al callback por defecto del bot, que
     ya resuelve cada pnid.
   - Se marca `webhook_subscribed_at` solo con `{"success": true}`.
   - El `override_callback_uri` queda reservado para varias instancias de
     bot. Hoy no se usa.
5. **Sin efectos sobre la atención.** No se toca `automatic_attention_enabled`
   ni la `ReceptionistConfig`.

**No se registra el número** (`POST /<PHONE_NUMBER_ID>/register` con PIN).
- En la vinculación asistida de un número que ya opera en Cloud API, volver a
  registrarlo cambiaría su PIN de dos pasos y podría interrumpirlo.
- Solo aplica a números nuevos de Embedded Signup (PROD-11), que deben
  registrarse dentro de los 14 días (*Client phone numbers*).

### 2.3 Instancia compartida del bot

- Todos los canales usan la `AgentInstance` existente, la única por
  despliegue, elegida por configuración (`external_id`). No se crea una por
  comercio.
- El webhook de la app central llega al mismo bot. La firma se valida con el
  único app secret; el ruteo es por `phone_number_id`, como en 06B.

## 3. Requisitos oficiales de Meta y referencias

### Comprobado en la documentación oficial (leída el 2026-11-28)

| Requisito | Fuente |
|---|---|
| Un Tech Provider, después de Embedded Signup, intercambia el `code` (`GET /oauth/access_token` con client_id, client_secret y code) por un *business token*, suscribe la app (`POST /<WABA_ID>/subscribed_apps`) y registra el número (`POST /<PHONE_NUMBER_ID>/register` con PIN de 6 dígitos). Todo server-to-server. El cliente agrega el método de pago | [Onboarding as a Tech Provider](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-customers-as-a-tech-provider/) |
| El *business integration system user token* está acotado al cliente incorporado y **solo se genera con Embedded Signup** | [Access tokens](https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/) |
| El system user token lo crea el dueño del portafolio en *Business settings › System users*, con la app asignada y acceso a la cuenta de WhatsApp **y** a la Messaging account. Es de larga duración con vencimiento elegible. Permisos: `business_management`, `whatsapp_business_management` y `whatsapp_business_messaging` | [Access tokens](https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/), [Get started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started) |
| Para incorporar clientes hace falta **acceso avanzado** aprobado para cada permiso. Sin él, las llamadas sobre cuentas ajenas devuelven el error 200 | [Embedded Signup overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview), [Manage accounts](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-accounts) |
| El límite es de 10 cuentas nuevas por 7 días móviles. Con Business Verification, App Review y Access Verification sube a 200 | [Embedded Signup overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview) |
| Los clientes incorporados por Embedded Signup son dueños de sus activos de WhatsApp. El cliente puede dejar de compartir la cuenta con el partner | [Embedded Signup overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview), [Manage accounts](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-accounts) |
| **Embedded Signup v2 y v3 se deprecaban el 15/10/2026.** Hay que usar v4. En v4 el evento `WA_EMBEDDED_SIGNUP` devuelve `phone_number_id`, `waba_id` y `business_id`, con eventos `FINISH`, `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`, `CANCEL` y `ERROR`. El `code` dura 5 minutos | [Embedded Signup overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview), [Implementation](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/implementation/) |
| Modelo en beta: la WABA se divide en *WhatsApp account* y *Messaging account*. Los `waba_id` existentes pasan a ser IDs de Messaging account. No requiere migración para nuestros datos | [Embedded Signup overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview) |
| `debug_token`: `is_valid`, `expires_at`, `data_access_expires_at`, `scopes`, `granular_scopes[].target_ids` (se omiten si el permiso cubre todo). Lo invoca un app access token | [debug_token](https://developers.facebook.com/docs/graph-api/reference/debug_token), [Manage accounts](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-accounts) |
| `GET /<WABA_ID>/phone_numbers` devuelve `display_phone_number`, `verified_name`, `code_verification_status`, `quality_rating`, `platform_type` y `webhook_configuration`. El registro debe hacerse dentro de los 14 días posteriores al flujo | [Client phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-phone-numbers) |
| Webhooks: verificación `hub.*`; firma `X-Hub-Signature-256: sha256=` con HMAC-SHA256 y app secret; reintentos hasta 7 días, con duplicados posibles; lotes de hasta 1000. Override por WABA (`override_callback_uri` + `verify_token` en `subscribed_apps`) o por número (`webhook_configuration`); las plantillas y `account_*` no admiten override | [Create webhook endpoint](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint), [Webhook overrides](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/override), [Webhooks overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview/) |

### Supuestos o no comprobados (requieren confirmación de Meta o pruebas en sandbox)

- **S1 — No hay vía oficial sin Embedded Signup.** Ninguna página
  documenta un camino oficial para que un Tech Provider acceda a la WABA
  existente de un cliente sin Embedded Signup.
  - La vía asistida supone que el cliente puede **agregar nuestra app a su
    portafolio**, crear un system user propio, asignarle la app y la WABA y
    generar un token para nuestra app.
  - Hay que validarlo en sandbox. Si no es posible, la vía asistida queda
    limitada a clientes con app propia o se adelanta PROD-11.
- **S2 — Duración del business token.** No está documentada. El nombre de la
  plantilla de configuración sugiere 60 días, pero no se confirma. Se toma de
  `debug_token.expires_at`.
- **S3 — `debug_token` con system user token.** *Manage accounts* lo muestra
  así, pero la referencia de `debug_token` no lo lista. Se usará el app
  access token.
- **S4 — Permisos no obtenidos.** No consta que nuestra app tenga App Review
  ni acceso avanzado, ni que el negocio esté verificado. Sin eso, las
  lecturas sobre WABAs de terceros fallan con el error 200.
- **S5 — Versión de Graph.** Los ejemplos van de v21.0 a v27.0 y el bot usa
  v23.0. Hay que fijar una versión vigente común (configurable) antes de
  PROD-10B.

## 4. Operaciones faltantes

| # | Operación | Dónde | Reutiliza |
|---|---|---|---|
| F1 | **Cliente de Graph servidor** (lecturas `debug_token`, `phone_numbers`, `subscribed_apps` y `POST subscribed_apps`), con timeout corto, sin reintentos automáticos y errores tipados (`meta_unavailable`, `meta_permission_denied`, `token_invalid`, `resource_mismatch`). `requests` ya es dependencia | `apps/leads/services/meta_graph.py` | Patrón de `takeover_client`/`human_message_client` |
| F2 | **Configuración** `META_APP_ID`, `META_APP_SECRET` (para el app access token) y `META_GRAPH_VERSION`. Fail-closed si faltan | settings | Validación al iniciar, como `leads.E006` |
| F3 | **Servicio `link_whatsapp_channel`** (§2.2): verificación, alta o reutilización de autorización y canal, asociación y auditoría en una transacción. Idempotente por `(business, phone_number_id)` | `services/whatsapp_authorizations.py` | `create_*`, `associate_channel`, la regla `channel_credential_problem` |
| F4 | **Desactivar canal**: `is_active=False` + `deactivated_at`, auditado. Requisito para reasignar un pnid. Hoy no existe | Ídem | Orden de locks existente |
| F5 | **Registro de verificación**: `meta_verified_at`, metadatos no secretos del número y `webhook_subscribed_at`. Sin token. Necesita **una migración de campos** en `AgentChannel` (la única estructura nueva) | `leads` | — |
| F6 | **Endpoints admin** (superadmin), bajo `clients/<id>/whatsapp-connections/`: `POST` vincular, `POST <channel>/verify` (re-verifica y actualiza F5 sin tocar secretos), `POST <channel>/subscribe-webhook`, `POST authorizations/<id>/rotate` y `/revoke`, `POST <channel>/deactivate` | `whatsapp_connection_views.py` | `admin_reception_business`, `record_platform_action`, taxonomía `{code, detail, field}` |
| F7 | **Contrato de lectura 08E1** ampliado: `external_verification` por canal, de forma aditiva | Ídem | `admin_whatsapp_connections` |
| F8 | **Señal de rechazo del bot**: hoy un 401 o código 190 de Meta muere en el log del bot. Propuesta para otro slice: un endpoint HMAC para reportar `meta_authorization_rejected` → `status=invalid` | Bot + Mi Rubro | Patrón 04C |

**Fuera de PROD-10:**
- El registro del número con PIN y el intercambio del `code` (PROD-11).
- La revocación remota en Meta.
- La rotación de la clave Fernet (MultiFernet).

## 5. Riesgos y requisitos de seguridad

- **Propiedad.**
  - El token debe ser del portafolio **del cliente**: un system user suyo, o
    el business token de Embedded Signup.
  - La autorización se crea siempre con `owner_business = Business` de la
    ruta.
  - `platform=True` (token global) queda solo como excepción por shell, nunca
    por este flujo.
  - Nunca se piden contraseñas de Meta.
- **Aislamiento.**
  - Ya existe en tres niveles: la constraint de pnid activo único, `save()`
    con dueño igual al Business, y `channel_credential_problem` con
    `owner_mismatch`.
  - Lo nuevo: verificar en Meta que el pnid pertenece a la WABA y que el
    token cubre esa WABA (`target_ids`). Así un admin no puede asociar un
    número ajeno al token.
- **Phone Number ID duplicado.**
  - Activo en otro Business: 409 sin revelar dueño. Reasignar requiere F4
    explícito.
  - Mismo Business y misma WABA: idempotente (rota el token si cambió).
- **Credenciales vencidas o revocadas.**
  - Se guarda `expires_at` de `debug_token`, y la regla local ya bloquea
    vencidas, revocadas e inválidas.
  - Una revocación del lado del cliente en Meta solo se detecta con
    re-verificación (F6) o con la señal del bot (F8).
- **Rotación.** `rotate_whatsapp_authorization` en el lugar, con la misma
  verificación previa: el token nuevo debe cubrir la WABA del canal.
- **Reintentos e idempotencia.**
  - Las lecturas de Meta van antes de escribir. `subscribed_apps` es
    idempotente en Meta.
  - Sin reintentos automáticos: el admin reintenta y la operación converge.
- **Fallas parciales.**
  - Verificación OK y transacción fallida: nada local cambia.
  - Transacción OK y suscripción del webhook fallida: el canal queda «sin
    webhook» y se reintenta con F6.
  - Webhook suscripto sin canal local: el bot lo rechaza de forma definitiva
    (200) y no hay atención.
- **Auditoría.**
  - Se reutilizan `WHATSAPP_AUTHORIZATION_*` y una acción nueva
    (`WHATSAPP_CHANNEL_LINKED`/`_DEACTIVATED`/`_VERIFIED`). Eso es otra
    migración de choices en accounts, o bien `PLATFORM_ADMIN_ACTION` con
    `operation`.
  - Solo metadatos: nunca token, `app_secret` ni respuestas crudas de Meta.
- **Exposición de secretos.**
  - El token se recibe una sola vez, se cifra al instante, no vuelve en
    ninguna respuesta y no se registra.
  - Hay que excluir el body en los logs de errores del cliente Graph.
  - El app access token solo se arma en memoria del servidor.
- **Clave maestra única sin rotación.** Riesgo ya conocido (04A). Si se
  filtra `AGENT_SECRET_ENCRYPTION_KEY` se exponen todos los tokens. Hace
  falta MultiFernet antes de escalar.

## 6. Activación independiente

| Estado | Fuente | Hoy |
|---|---|---|
| Canal registrado | `AgentChannel.is_active` | Sí |
| Autorización local vigente | `local_status = credential_ready` | Sí |
| Recursos verificados en Meta | `meta_verified_at` + metadatos (F5) | **Falta** |
| Webhook configurado | `webhook_subscribed_at` (F5), comprobado con `GET subscribed_apps` | **Falta** |
| Funcionamiento real comprobado | Último mensaje entrante sincronizado del canal (`LeadAgentState`/mensajes, 02E4C) | Parcial: existe por Business, no por canal |
| Atención automática | `ReceptionistConfig.automatic_attention_enabled` | Sí. **Ninguna operación de PROD-10 la modifica** |

Cada estado se muestra por separado. Ninguno implica al siguiente. Que
existan credenciales nunca implica conectividad.

## 7. Compatibilidad con Embedded Signup (PROD-11)

- **Lo que PROD-11 agrega:**
  - Un paso de obtención: el frontend v4 recibe `code`, `waba_id` y
    `phone_number_id`.
  - El servidor intercambia el `code` por el business token.
  - Para números nuevos, `register` con PIN.
- **Lo que reutiliza sin cambios:** `link_whatsapp_channel` (F3), con la
  misma verificación, almacenamiento, asociación, webhook (F6), estados (F5) y
  entrega al bot.
- **Firma propuesta:**
  `link_whatsapp_channel(business, waba_id, phone_number_id, token, source='assisted'|'embedded_signup', actor, reason)`.
  - `source` solo se audita.
  - La diferencia queda en cómo se obtiene `token`, nunca en cómo se guarda
    o usa.
- **Requisitos de Embedded Signup:** App Review, acceso avanzado y Business
  Verification (S4) son también requisitos de la vía asistida para WABAs de
  terceros. Conviene tramitarlos ya.

## 8. Integración visual mínima

Todo dentro de `AdminWhatsAppConnectionsSection`, con el mismo `Providers`,
la misma query y sin otra página ni wizard:

- **«Vincular número»** (superadmin): un `Modal` con WABA ID, Phone Number ID,
  token y motivo, como en el formulario de 09D2/09E.
  - El token va en un campo `password` (sin autocompletar) que se limpia al
    cerrar.
  - Después del 200 se invalida `useAdminWhatsAppConnections` y se vuelve a
    leer el checklist.
- **Por canal:**
  - «Verificar en Meta».
  - «Suscribir webhook» (solo si falta).
  - «Rotar token» (Modal con token y motivo).
  - «Revocar» (confirmación).
  - «Desactivar canal» (confirmación).
- **Estados:** las seis filas de §6 con su badge. «Sin verificar» es el
  valor por defecto, nunca «conectado».

## 9. Regresión de cierre de PROD-09

Es la misma regresión de 09C3: `app/admin`, `components`, `lib`,
`features/reception`, `features/leads` y `app/app/recepcionista`, con Vitest
en `node:20-alpine`.

| Base | Resultado |
|---|---|
| 09C3 (`0d73840`) | 609/611 |
| Ahora (`40049f3`, con 09D2 y 09E) | **641/643** (+16 de 09D2, +16 de 09E) |

Las 2 fallas son las mismas preexistentes de
`app/admin/notificaciones/__tests__/notificaciones-content.test.tsx`
(mark-read y archive). No se corrigieron porque están fuera de alcance.

## 10. Slices mínimos para completar PROD-10

| Slice | Alcance | Depende de |
|---|---|---|
| **10B** | Backend: F1 cliente Graph + F2 config + F3 `link_whatsapp_channel` (asistida) + F4 desactivar + F5 campos de verificación (1 migración). Tests con Graph simulado | — |
| **10C** | Backend: F6 endpoints admin (vincular, verificar, webhook, rotar, revocar, desactivar) + F7 contrato aditivo | 10B |
| **10D** | Frontend: acciones y estados en «Conexiones WhatsApp» (§8) | 10C |
| **10E** | Prueba controlada en sandbox de Meta: confirmar S1–S5 con un número de prueba propio, nunca de un cliente | 10B–10D, aprobación de Meta |
| Posterior | F8 (rechazo del bot → `invalid`), MultiFernet, PROD-11 Embedded Signup v4 | — |

**Decisión pendiente:** si S1 resulta inviable (el cliente no puede generar
un token para nuestra app), la vía asistida queda solo para el piloto o para
clientes con app propia, y PROD-11 pasa a ser el camino principal. 10B–10D no
se pierden porque son la base común.
