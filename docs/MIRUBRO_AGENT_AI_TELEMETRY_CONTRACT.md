# Contrato de telemetría operativa de IA del agente (PROD-02E4A)

`POST /api/v1/integrations/agent/ai-executions/`

Registra **un intento real contra el proveedor de IA** (por ejemplo, una llamada a `responses.create`). No autoriza nada. La autorización comercial sigue en `POST /api/internal/appointments/ai-usage/authorize/`.

## Autenticación
- Se usa HMAC Contract V1, igual que en el sync de Leads: `X-Agent-Key-Id`, `X-Agent-Timestamp`, `X-Request-Id` (UUID nuevo en cada intento HTTP) y `X-Agent-Signature`. El método firmado es `POST`.
- El nonce es fail-closed: si el cache no está disponible, responde 503.
- Las credenciales `active` y `retiring` se aceptan. Las `revoked` y las de una instancia deshabilitada responden 401.
- Throttle por instancia: `agent_ai_telemetry`, por defecto `1200/minute`. Es fail-closed.
- Flags: `AGENT_INTEGRATION_ENABLED` y `AGENT_AI_TELEMETRY_ENABLED`. Si alguno está apagado, responde 503 `unavailable` con `retryable: true`.

## Body (JSON, sin coerciones; cualquier campo no listado → 400 `unknown_field`)
| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `event_id` | UUID | sí | Identidad estable del intento. Es única por AgentInstance y debe ser la misma en cada reintento HTTP. |
| `phone_number_id` | string | sí | Regex `^[0-9]{1,32}$`. El tenant sale del canal de la instancia activo en `executed_at`. |
| `interaction_id` | UUID \| null | no | La misma que se envió a `authorize`, si corresponde. |
| `provider` | string | sí | `openai` |
| `model` | string | sí | Regex `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` |
| `operation` | string | sí | `response` · `chat_completion` · `embedding` · `transcription` · `moderation` |
| `status` | string | sí | `succeeded` · `failed` · `unknown` (no se sabe si el proveedor ejecutó, por ejemplo en un timeout de red) |
| `error_code` | string \| null | sí si `failed`; prohibido si `succeeded` | `timeout` · `rate_limited` · `provider_unavailable` · `invalid_request` · `authentication` · `content_filtered` · `context_length_exceeded` · `network` · `cancelled` · `unknown` |
| `input_tokens`, `output_tokens` | int ≥ 0 \| null | no | Máximo 10.000.000. `null` (o el campo ausente) significa desconocido; `0` significa realmente cero. |
| `cached_input_tokens` | int ≥ 0 \| null | no | Debe ser ≤ `input_tokens`, que en ese caso no puede ser null. |
| `provider_request_id` | string \| null | no | Regex `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`, por ejemplo el `response.id` de OpenAI. |
| `latency_ms` | int ≥ 0 \| null | no | Máximo 3.600.000. |
| `executed_at` | ISO-8601 con zona | sí | No puede estar más de 60 s en el futuro ni tener más de 30 días. |

**Nunca** enviar prompts, respuestas, mensajes, nombres, teléfonos, secretos ni el payload del proveedor.

## Respuestas
| HTTP | Body | Qué hacer |
|---|---|---|
| 201 | `{"ok": true, "result": "recorded", "event_id": "…"}` | Listo. |
| 200 | `{"ok": true, "result": "duplicate", "event_id": "…"}` | Ya estaba registrado con el mismo contenido. Listo. |
| 400 | `validation_error` con `fields: [{field, code}]` | Bug del emisor. No reintentar. |
| 401 | `invalid_signature` | Revisar la credencial. |
| 403 | `channel_not_authorized` | El canal no era de esta instancia, o no estaba activo en `executed_at`. No reintentar. |
| 409 | `idempotency_conflict` | El mismo `event_id` ya existe con otro contenido. No reintentar. |
| 429 / 503 | `rate_limited` / `unavailable` | Reintentar con backoff, con el mismo body y un `X-Request-Id` nuevo. |

## Semántica
- **Tenant**: se resuelve con el canal de la instancia autenticada que tenía ese `phone_number_id` activo en `executed_at` (`created_at ≤ executed_at < deactivated_at`).
  - Un resultado tardío de un canal que después se desactivó o se reasignó se sigue atribuyendo al Business de ese período.
  - Nunca se acepta un `business_id` del agente.
- **Independencia comercial**: no crea sesiones, cargos, cupos, intents ni settlements, y no concede acceso.
  - Una suspensión o revocación comercial no impide registrar ejecuciones ya ocurridas.
- **Vínculo comercial**: si existe una `AppointmentAIUsageAuthorization` del mismo Business con esa `interaction_id`, y su conversación es de ese canal, se enlaza. Si no existe, el evento se registra igual sin vínculo.
- **Inmutabilidad**: los eventos no se pueden modificar. Un replay con otro contenido no cambia el historial.
