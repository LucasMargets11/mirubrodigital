# PROD-10C1 — Endpoint administrativo de vinculación WhatsApp

Fecha: 2026-11-28. Rama `feat/recepcionista`, base `8ae8ded`. Bot sin cambios (`de7e932`).
Solo backend de Mi Rubro. Sin modelos, migraciones, dependencias, frontend, llamadas reales a Meta ni despliegue.

## 1. Contrato HTTP

`POST /api/v1/platform-admin/clients/{business_id}/whatsapp-connections/`

Es el mismo recurso que el GET 08E1, y siempre responde con `Cache-Control: no-store`.

- **Body exacto:** `{"waba_id", "phone_number_id", "access_token", "reason"}`, los cuatro texto y obligatorios.
  - Cualquier otro campo da `400 unexpected_fields` y no escribe nada. Eso incluye `source`, `business_id`, `platform` y `token`.
- **Origen:** el servicio recibe `source="assisted"` fijado por la vista, nunca desde el body.
- **Business:** sale solo de la ruta, con `admin_reception_business`, y el servicio lo revalida.
- **Respuesta 201** (vinculación nueva) **o 200** (repetición equivalente):

```json
{
  "contract_version": 1, "business_id": 12, "outcome": "linked",
  "created_channel": true, "created_authorization": true,
  "automatic_attention_enabled": false, "evaluated_at": "…",
  "channel": { "…la misma fila del GET…" }
}
```

- **Errores:** siempre `{code, detail, field, retryable}`, con detalle fijo, nunca valores recibidos ni texto de Meta.

| HTTP | Códigos |
|---|---|
| 400 | `invalid_request`, `unexpected_fields`, `invalid_field`, `invalid_token`, `invalid_reason`, `invalid_input` |
| 403 | No es superadmin (operations y usuarios de comercio incluidos) |
| 404 | `client_not_found` (inexistente, sucursal o sin Recepcionista no cancelada) |
| 409 | `automatic_attention_must_be_paused`, `phone_number_unavailable` (no revela el otro comercio), `channel_waba_mismatch`, `channel_agent_instance_mismatch`, `channel_credential_conflict`, `channel_changed_concurrently` (retryable) |
| 422 | `phone_platform_not_supported`, `whatsapp_authorization_expired` y los definitivos de Meta: `token_invalid`, `token_expired`, `token_app_mismatch`, `data_access_expired`, `permissions_missing`, `resource_scope_not_granted`, `resource_scope_unverified`, `permission_denied`, `resource_not_found`, `phone_number_not_in_waba`, `meta_request_rejected` |
| 429 | Throttle `admin_whatsapp_link` (10/min por usuario, `ADMIN_WHATSAPP_LINK_THROTTLE_RATE`). Solo el POST lo consume |
| 502/503 | `meta_invalid_response`/`meta_error`; `meta_unavailable`/`meta_rate_limited` (retryable); `meta_not_configured`, `agent_instance_not_configured`/`_unavailable`, `whatsapp_credential_unreadable` |

Los códigos de Meta son los ya normalizados por 10B1, estables. El mapeo a HTTP es una tabla de la vista; las reglas de vinculación siguen todas en el servicio.

## 2. Permisos

- **GET:** superadmin u operations, sin cambios.
- **POST:** solo superadmin, con la misma `HasInternalRole` existente y roles por método. El servicio lo exige de nuevo.
- **Usuarios de comercio y anónimos:** 403 o 401.
- **Aislamiento:** el Business de la ruta es el único posible. Un número activo en otro cliente da 409 sin id ni nombre.

## 3. Protecciones operativas (en el servicio común, también para Embedded Signup)

- **Cloud API:**
  - Se exige `platform_type == "CLOUD_API"` exacto.
  - `ON_PREMISE`, `NOT_APPLICABLE`, otro valor, vacío, `null` o ausente dan `phone_platform_not_supported`, sin escrituras.
  - Se evalúa sobre el dato ya normalizado por 10B1, sin cambiar el cliente Graph.
- **Atención pausada:**
  - Crear un canal, o dar la primera credencial a uno existente, exige `automatic_attention_enabled = false`. Si no, `409 automatic_attention_must_be_paused`.
  - Nunca se pausa sola y no hay campo nuevo.
  - Se chequea antes de Meta, para fallar rápido, y se revalida dentro de la transacción con lock de la config.
  - Una repetición equivalente sobre una conexión ya operativa refresca la evidencia sin exigir pausa.
- **Concurrencia con el PATCH de atención:**
  - El orden es Business → config, el mismo que authorize y la cancelación.
  - El Business se bloquea con `FOR NO KEY UPDATE`.
    - El test de concurrencia encontró un **deadlock** con `FOR UPDATE`: el PATCH bloquea la config y luego inserta su auditoría, cuya FK pide `KEY SHARE` sobre el Business.
    - `NO KEY UPDATE` sigue serializando vinculaciones entre sí y frente a quien tenga el Business `FOR UPDATE`, sin bloquear esas FK.
  - Tests reales con hilos:
    - Vinculación primero: el PATCH espera y habilita después.
    - PATCH primero: la vinculación se rechaza sin escrituras.

## 4. Evidencia en la lectura (aditiva)

- Cada canal del GET suma `meta_verification`, calculado solo con `channel_meta_verification`. La misma fila se usa en la respuesta del POST.
  - `{"status": "missing"}`: canal legacy o nunca verificado. Los canales previos siguen igual.
  - `{"status": "invalidated"}`: había evidencia, pero cambió la credencial, su versión, la WABA o el número, o el canal no entregaría hoy su credencial.
  - `valid`: incluye estos campos:
    - `verified_at`, `source`, `resources_verified`, `waba_id`, `phone_number_id`.
    - `app_subscribed_observed`, `override_callback_observed`. Es booleano: nunca la URL.
    - `phone` (nombre, número visible, estado, calidad, plataforma).
    - `legal_ownership_verified: false`.
- No se exponen datos del token ni la ligadura interna.
- `local_status` y `meta_verification` son independientes: una rotación deja `credential_ready` con evidencia `invalidated`.
- `external_verification` del GET sigue `performed: false` / `meta_connectivity: "unknown"`: la evidencia es una observación histórica, no conectividad, webhook funcionando ni mensajes.

## 5. Seguridad

- El token llega solo en el body del POST. Es de escritura y nunca se devuelve, tampoco en errores de validación. Los tests lo comprueban en respuestas, errores y logs.
- No hay middleware que capture bodies ni herramienta de observabilidad que los envíe. `django.request` registra método y path, no el body.
- Los errores 500 (falla de auditoría) revierten todo y no incluyen secretos.
- Ninguna respuesta serializa modelos con credenciales: la fila se arma campo por campo (`admin_whatsapp_channel`).

## 6. Reutilizado y nuevo

- **Reutilizados:**
  - Servicios: `link_whatsapp_channel`, `verify_whatsapp_resources`, `channel_meta_verification`, `admin_reception_business`.
  - Permisos y respuesta: `HasInternalRole`/`IsPlatformStaff`, el formato `{code, detail, field}` y `ScopedRateThrottle`.
  - Lectura y estado: la fila y el `contract_version` de 08E1, y `automatic_attention_enabled`.
  - Tests: los fakes de 10B1/10B2.
- **Refactor sin cambio de contrato:**
  - La fila del GET se extrajo a `admin_whatsapp_channel`, compartida por GET y POST.
  - `channel_meta_verification` y `EVIDENCE_VERSION` pasaron a `whatsapp_authorizations.py` (sin import circular) y se re-exportan desde `whatsapp_link`.
- **Nuevo:** el método POST, el campo aditivo `meta_verification` en la lectura, las reglas Cloud API y atención pausada, y una tasa de throttle.

## 7. Tests

- `test_admin_whatsapp_link_10c1.py`: 39 tests.

| Bloque | Cubre |
|---|---|
| POST | 201, 200, origen fijo, campos extra y faltantes, body no objeto, errores sin token, logs sin secretos, throttle |
| Permisos | Operations lee y no vincula (sin llamar a Meta), comercio, anónimo, cliente inexistente o no elegible, Business solo por ruta, conflicto sin revelar |
| Cloud API | Válida; `ON_PREMISE`, `NOT_APPLICABLE`, minúsculas, vacío, null y ausente; regla también con origen Embedded Signup |
| Atención | Alta bloqueada sin llamar a Meta y sin pausar; primera credencial bloqueada; pausada permitida; re-verificación equivalente sin pausa; token distinto sigue en conflicto; habilitada durante la verificación |
| Conflictos y Meta | WABA, instancia, credencial; instancia y Meta no configurados; definitivos 422; transitorios 503 retryable; texto de Meta nunca expuesto; rollback con 500 |
| GET | Evidencia válida, override y no suscripta observados, invalidada, legacy, solo lectura |
| Concurrencia | Vinculación vs PATCH de habilitación en ambos órdenes |

- **Ajustes de tests existentes**, por el nuevo contrato:
  - 10B2: con atención encendida ahora se bloquea.
  - 08E1: POST ya no es 405.
- **Regresiones:**
  - Las suites 10C1 + 10B2 + 08E1 pasan tres veces seguidas.
  - `apps.leads` completo: **1028/1028 OK**.
  - `check`: sin problemas.
  - `makemigrations --check`: sin cambios.

## 8. Riesgos

- **Deadlock preexistente (09C1), no tocado acá:**
  - El gate `authorize` de consumo IA bloquea Business `FOR UPDATE` y luego la config.
  - El PATCH de atención bloquea la config y luego inserta auditoría con FK a Business.
  - Concurrentes, pueden caer en el mismo deadlock que encontré acá: PostgreSQL aborta uno.
  - Solución propuesta: `select_for_update(no_key=True)` en `authorize`.
- **La pausa es necesaria pero no suficiente:** al reactivar la atención, el número nuevo se atiende si la app ya está suscripta (`app_subscribed_observed`). Lo decide el operador.
- **Revocación o desconexión del lado del cliente:** no se detecta hasta re-verificar (10C2+) o la señal del bot (F8).
- **Sin validación contra Meta real (10E):** el app token en Bearer, los códigos exactos y `expires_at=0`.
- **Throttle:** usa la cache (Redis) como el resto de throttles. Ante una caída de cache, DRF falla según su comportamiento por defecto.
- **Despliegue:** sin migración nueva. Requiere la `0017` de 10B2 y `WHATSAPP_LINK_AGENT_INSTANCE_ID`.
