# MiRubro → Agent: control humano de la conversación (MIRUBRO TAKEOVER 05A)

Un usuario de MiRubro toma una conversación (el bot deja de responder) y después la devuelve (el bot vuelve a responder). MiRubro guarda el estado y envía comandos firmados al agente. El contrato del agente está en `docs/MIRUBRO_TAKEOVER.md` del repo del bot (AGENT TAKEOVER 01A).

Este slice **no** incluye inbox, envío de mensajes desde MiRubro, sync de mensajes, takeover automático ni UI. "Tomar conversación" significa: el bot se calla y recepción habla desde WhatsApp (botón existente "Abrir WhatsApp"). El contrato Agent → MiRubro (`lead.sync`) y el receiver no cambian.

Código: `services/api/src/apps/leads/` → `models.py` (`ConversationControl`, `TakeoverCommand`), `services/takeover.py` (estados y entrega), `takeover_client.py` (HMAC/HTTP), `tasks.py`, `crm_views.py` (endpoints), `checks.py`. Migración `leads/0004_conversation_takeover`.

## 1. Modelo

### `ConversationControl`: un registro por conversación

Identidad `(business, external_conversation_id)`, única. La pausa es de la **Conversation** del agente, no del Lead: dos Leads de la misma conversación (por ejemplo uno nuevo después de 72 h) leen el mismo registro. El id sale de `LeadAgentState.external_conversation_id` y tiene que tener el formato del agente (`wac1_` + 32 hex). Nunca se usa el teléfono, `external_lead_id` ni el teléfono del Customer. Un Lead sin `agent_state`, o con otro formato de id, no puede usar takeover.

| Campo | Uso |
|---|---|
| `state` | `active` · `takeover_pending` · `taken` · `release_pending` · `error` |
| `command_version` | Versión del último comando creado (empieza en 0, monotónica, no se reutiliza) |
| `last_command_action` | `takeover`/`release` del último comando (sirve para reintentar desde `error`) |
| `last_event_id` | `event_id` del último comando |
| `agent_applied_version` | Mayor `applied_version` que informó el agente |
| `taken_at` / `taken_by` | Se setean **con el ACK** del takeover, con el `requested_by` del comando. El release los borra |
| `released_at` | ACK del último release |
| `last_command_at`, `last_success_at`, `last_error_code` | Operación |

### `TakeoverCommand`: outbox, un registro por comando

`(conversation_control, version)` único y `event_id` único. Campos: `action`, `status` (`pending` · `delivering` · `delivered` · `failed`), `result` (`applied` · `duplicate` · `stale`), `occurred_at` (se fija al crear y no se regenera), `attempts`, `next_attempt_at`, `lease_until`, `last_status` (HTTP), `last_error` (código), `agent_applied_version`, `requested_by`, `requested_from_lead`, `delivered_at`, `failed_at`. No guarda payload crudo, headers, request ids ni PII.

## 2. Máquina de estados

```
active ──takeover──▶ takeover_pending ──ACK──▶ taken
taken  ──release───▶ release_pending  ──ACK──▶ active
*_pending ──fallo terminal / reintentos agotados / version_regression / estado inesperado──▶ error
error  ──takeover | release (versión nueva)──▶ *_pending
```

| Pedido \ estado | active | takeover_pending | taken | release_pending | error |
|---|---|---|---|---|---|
| takeover | **nuevo v+1** (202) | 200, sin comando | 200, sin comando | 409 `command_in_progress` | **nuevo v+1** (202) |
| release | 200, sin comando | 409 `command_in_progress` | **nuevo v+1** (202) | 200, sin comando | **nuevo v+1** (202) |

Mientras un comando está en curso hay una sola acción a la vez: para cambiar de decisión hay que esperar a que termine (MVP). Un release sobre una conversación que nunca se tomó responde `active`, versión 0, y no crea el registro.

`taken` significa que el agente confirmó (2xx) el comando vigente. Nunca se informa `taken` antes del ACK.

## 3. Pedido humano (outbox)

En **una** transacción:

1. `INSERT … ON CONFLICT DO NOTHING` del control (solo para takeover) y `SELECT … FOR UPDATE` de esa fila.
2. Se valida la transición (tabla de arriba).
3. Los `pending` viejos de ese control (solo pueden existir después de un `error`) pasan a `failed superseded`.
4. `version = max(command_version, agent_applied_version) + 1`. Se crea `TakeoverCommand` pending con un `event_id` UUIDv4 persistido y `next_attempt_at=now`.
5. El control pasa a `*_pending`, con `command_version=version`.
6. Actividad `takeover_requested` / `release_requested` en el Lead.

**COMMIT**. Después, `on_commit_safely` dispara `leads.deliver_takeover_command.delay(id)` (best-effort: si el broker falla, lo levanta el Beat). La request humana no hace HTTP.

## 4. Entrega

1. **Claim** (transacción corta): `SELECT … FOR UPDATE SKIP LOCKED` del comando. Es elegible si está `pending` con `next_attempt_at <= now`, o `delivering` con `lease_until <= now` (el worker murió). Si el control ya tiene una versión mayor, el comando pasa a `failed superseded` y no se envía. Si no: `delivering`, `attempts += 1`, `lease_until = now + 60 s`.
2. **HTTP** fuera de transacción (`takeover_client.send_command`).
3. **Resultado** (transacción): lock control → command, en el mismo orden que el pedido humano. *Fencing*: se aplica solo si el comando sigue `delivering` con el mismo `attempts` que el claim. Si otro intento lo volvió a tomar, gana el resultado de ese intento.

Un comando `delivering` con el lease vencido se reenvía. Es at-least-once, y el agente lo resuelve por idempotencia (versión + event_id).

### ACK tardío

El resultado de un comando cambia el estado del control **solo si `command.version == control.command_version`**. Si llega la respuesta de un comando viejo, el comando se marca `delivered`/`failed` según lo que contestó el agente, pero `state`, `taken_*` y `last_error_code` del control no se tocan. (La única excepción es `version_regression`, ver abajo.) Tests: `test_late_ack_never_overwrites_newer_command`, `test_late_failure_of_old_command_does_not_touch_state` y `test_d_late_ack_racing_new_release` (PostgreSQL).

## 5. Respuestas del agente

| Respuesta | Comando | Control (si es el vigente) | ¿Reintenta? |
|---|---|---|---|
| 200 `applied` / `duplicate`, con `applied_version == version` y el `state` esperado (`paused`/`active`) | `delivered` | `taken` / `active`, `last_success_at` | — |
| 200 `applied`/`duplicate` con otro `state` u otra versión | `delivered` | `error unexpected_agent_state` | No |
| 200 `stale` con `applied_version > control.command_version` | `delivered` (stale) | `error version_regression` (también si el comando no es el vigente) + log ERROR | No |
| 200 `stale` de un comando viejo (`applied_version <= command_version`) | `delivered` (stale) | sin cambios | — |
| 400 `invalid_payload`, 401 `invalid_signature`, 403 `takeover_disabled`/`tls_required`, 404 `conversation_not_found`, 409 `version_conflict`/`business_mismatch`, otro 4xx (`http_<status>`), 3xx (`unexpected_redirect`) | `failed` | `error <code>` + log ERROR | No |
| 5xx, 408, 429, timeout, error de red, 200 ilegible (`invalid_response`), cliente sin configurar | `pending` + backoff | sigue `*_pending`, `last_error_code=<code>` | Sí |
| Reintentos agotados (`AGENT_TAKEOVER_MAX_ATTEMPTS`, default 10) | `failed` | `error delivery_exhausted` | No |

`version_regression` quiere decir que el agente tiene una versión mayor que cualquiera emitida por MiRubro (se perdió estado). La versión del agente no se baja. Se guarda `agent_applied_version`, y el próximo comando humano sale con `max(command_version, agent_applied_version) + 1`.

401 y 403 no se reintentan, para no golpear al agente cada pocos segundos con una credencial o configuración rota. El humano reintenta a mano (desde `error` se crea una versión nueva) después de arreglar la configuración.

Desde `error`, el estado real del bot es desconocido. `last_action` y `last_error_code` dicen qué se intentó.

## 6. Reintentos

- Backoff después del intento N: 30 s, 1 m, 2 m, 4 m, 8 m, y desde ahí 15 m (`AGENT_TAKEOVER_RETRY_BACKOFF_SECONDS`).
- Después de un fallo transitorio: `apply_async(countdown=backoff)` (best-effort) y además el Beat `leads-retry-due-takeover-commands`, que corre cada minuto y levanta pendientes vencidos, kicks perdidos y `delivering` con el lease vencido. Si el kick y el Beat corren a la vez, el `SKIP LOCKED` y el estado del claim evitan el doble envío.
- Celery no hace autoretry: la política vive en la DB.
- Timeout HTTP de 10 s, sin redirects.
- Todo reintento usa el mismo `version`, `event_id`, `occurred_at` y body byte a byte, con `X-Request-Id`, timestamp y firma nuevos.

## 7. HMAC

Credencial **propia** de esta dirección, solo en env (no está en la DB, el admin ni la API, y no se loguea):

```
AGENT_TAKEOVER_ENABLED=false      # default
AGENT_TAKEOVER_BASE_URL=          # https://bot.example.com[/prefijo]
AGENT_TAKEOVER_KEY_ID=            # = MIRUBRO_INBOUND_KEY_ID del bot
AGENT_TAKEOVER_SECRET=            # = MIRUBRO_INBOUND_SECRET del bot (32–512 bytes)
AGENT_TAKEOVER_MAX_ATTEMPTS=10
```

No se reutiliza `AGENT_SECRET_ENCRYPTION_KEY` ni la credencial Agent → MiRubro. Con el flag en `true`, `manage.py check` falla si falta algo: `leads.E003` (base URL), `E004` (key id `^[A-Za-z0-9_.-]{1,64}$`), `E005` (secret de 32 a 512 bytes), `E006` (`http://` fuera de DEBUG; el bot exige TLS). Con el flag apagado, POST takeover/release responde 503 `takeover_disabled` y la entrega no hace nada: los pendientes quedan hasta que se encienda.

```
PUT {base_path}/integrations/mirubro/conversations/{external_conversation_id}/{takeover|release}
Content-Type: application/json
X-Mirubro-Key-Id: <key id>
X-Mirubro-Timestamp: <unix s>
X-Request-Id: <uuid v4 minúsculas, nuevo por intento>
X-Mirubro-Signature: v1=<hex HMAC-SHA256(secret, canonical)>

{"event_id":"<uuid>","version":N,"occurred_at":"2026-10-06T12:00:00.000000Z","business_id":<Business.pk>}
```

Canonical (7 líneas unidas por LF, sin newline final): `v1`, `PUT`, path exacto (incluye el prefijo de la base URL, sin query), timestamp, request_id, key_id y el sha256 hex del body. Es el mismo helper que usa el receiver (`contract.canonical_string`). El body lleva exactamente esas cuatro claves, sin teléfono, nombre, Lead ni mensajes.

`business_id` tiene que coincidir con el `MIRUBRO_BUSINESS_ID` del bot. Si no, el bot responde `409 business_mismatch`.

## 8. API humana

| Endpoint | Permiso | Respuesta |
|---|---|---|
| `POST /api/v1/leads/{id}/takeover/` | `manage_leads` + entitlement `appointments.leads` | 202 `{"ok":true,"state":"takeover_pending","command_version":N}` · 200 idempotente · 400 `conversation_unavailable` · 409 `command_in_progress` · 503 `takeover_disabled` |
| `POST /api/v1/leads/{id}/release/` | igual | igual, con `release_pending` |

Owner, admin y manager pueden usarlos. Viewer no. Con solo `view_leads`, se ve el estado. Un Lead de otro Business da 404. El tenant sale del contexto de la sesión. El body se ignora.

Lectura:

- Detalle: `conversation_control` vale `null` si el Lead no tiene conversación del agente. Si no: `{state, command_version, last_action, taken_at, taken_by{id,display_name}, released_at, last_error_code, available}`. `available` indica si el flag está encendido y el id tiene el formato del agente. Sin event_id, request ids, secretos ni datos de transporte.
- Bandeja: `conversation_state`, con el mismo `null` / `active` por defecto. Sale de un subquery anotado, sin una query extra por fila.

Actividad del Lead desde el que se pidió el comando: `takeover_requested` (con actor), `takeover_applied`, `takeover_failed`, `release_requested`, `release_applied`, `release_failed` (sistema, `metadata.version`/`error_code`). Un ACK tardío que no cambia el estado no genera actividad. No se crean BusinessNotification: los errores de entrega van a log/alerta técnica (`apps.leads.takeover`: `takeover_command_failed`, `takeover_command_exhausted`, `takeover_version_regression`, `takeover_unexpected_agent_state`, todos en ERROR).

Admin: `ConversationControl` y `TakeoverCommand` son de solo lectura.

## 9. Concurrencia (PostgreSQL, `TakeoverConcurrencyTests`)

- **A**: varios takeover simultáneos, incluido el primer INSERT, generan un solo comando y una sola versión.
- **B**: takeover y release simultáneos desde `active` dejan un comando, `takeover_pending` v1. El release devuelve `active` idempotente o 409, según quién tomó el lock primero.
- **C**: cuatro entregas paralelas del mismo comando hacen un solo HTTP, con el mismo `event_id`.
- **D**: un ACK tardío de v1 en carrera con el release v2 termina siempre en `release_pending` v2.

## 10. E2E local

Ver el reporte del slice. Ambiente: MiRubro (`mirubro-api-dev` + compose postgres, Business 3 `qa-turnos`, instancia `dental-agent-local`) y el bot con `MIRUBRO_TAKEOVER_ENABLED=true`, sin Meta ni OpenAI reales (harness/mocks).

## 11. Deuda (05B / inbox)

- **Historial incompleto después del release**: durante la pausa, los mensajes del paciente se guardan en el bot, pero lo que contesta el humano por WhatsApp no entra al historial del bot. Al reanudar, el modelo tiene contexto incompleto. Se resuelve con el inbox/espejo de mensajes.
- No hay UI (botones Tomar/Reanudar/Reintentar): queda para 05B. El backend ya expone `available`, `state` y `last_action`.
- Un solo endpoint y credencial de agente por entorno (`AGENT_TAKEOVER_*`). Con varias `AgentInstance`, el endpoint y la credencial tendrían que ir por instancia, y `business_id` tiene que coincidir con el del bot.
- MiRubro solo conoce el estado del bot por sus propias respuestas: no hay lectura del estado en el agente ni en `lead.sync`. Después de un `error`, el estado real es desconocido hasta el próximo comando.
- Mientras hay un comando en curso, el usuario no puede cambiar de decisión. Si el agente está caído, eso dura hasta agotar los reintentos (unas 2 h con los defaults).
- No hay release automático por timeout.
- No hay rotación con dos claves simultáneas.
