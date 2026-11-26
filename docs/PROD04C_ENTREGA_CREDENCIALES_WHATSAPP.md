# PROD-04C — Entrega segura de credenciales WhatsApp al bot

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `6682c6f` · Bot
`8b69e4d` sin cambios. Referencia:
`docs/PROD04B_ALMACENAMIENTO_AUTORIZACIONES_WHATSAPP.md`. Sin modelos,
migraciones, dependencias, caché, frontend ni llamadas a Meta.

## 1. Endpoint

`GET /api/v1/integrations/agent/channels/<phone_number_id>/whatsapp-credential/`

- **Firma:** HMAC Contract V1 de la instancia (`AgentHmacAuthentication`). La
  firma cubre el path, así que el número forma parte de lo firmado (el query
  string no se firma y no se usa).
- **Tenant:** el Business sale del canal activo de la instancia autenticada.
  El bot no necesita conocerlo de antemano.
- **Respuesta:** solo lectura, con `Cache-Control: no-store` en todas las
  respuestas, también en errores.

## 2. Contrato (datos ficticios)

```json
{
  "ok": true,
  "contract_version": 1,
  "business_id": 4242,
  "phone_number_id": "1234567890",
  "waba_id": "102030405060",
  "access_token": "EAAG-TOKEN-FICTICIO-DE-EJEMPLO",
  "expires_at": "2027-01-31T12:00:00+00:00"
}
```

`expires_at` es `null` para tokens de system user, que no vencen.

Errores (envelope Contract V1, nunca con el token):

| Status | `code` | Causa |
|---|---|---|
| 401 | `invalid_signature` | Firma, timestamp, key, credencial o instancia inválidos; replay; sesión humana |
| 403 | `channel_disabled` | Número desconocido, inactivo, de otra instancia, o reasignado entre lecturas |
| 403 | `business_inactive` | Negocio suspendido o cancelado |
| 403 | `whatsapp_authorization_missing` / `_owner_mismatch` / `_revoked` / `_invalid` / `_expired` | Estado de la autorización (04B) |
| 403 | `whatsapp_waba_missing` | Canal con autorización pero sin WABA (solo posible salteando `save()`) |
| 405 | `invalid_request` | Método distinto de GET |
| 429 | `rate_limited` | Throttle por instancia |
| 503 | `unavailable` | Flag apagado, Redis caído (nonce o throttle), o token indescifrable |

## 3. Controles de seguridad

- **Replay fail-closed:** si Redis no responde, ni el nonce ni el throttle
  aceptan la request (503). Firma y timestamp siguen siendo obligatorios.
- **Aislamiento:** se rechazan canales ajenos, desconocidos o inactivos y
  negocios fuera de `ALLOWED_BUSINESS_STATUSES`, con la misma lógica que el
  receiver.
- **Dos lecturas, contrastadas:** el canal se lee una vez para resolver el
  tenant y otra para resolver el token. La segunda vuelve a validar el dueño,
  el estado, el vencimiento y la WABA, y además que el canal siga siendo de la
  misma instancia, negocio y número (si cambió en el medio ⇒
  `channel_disabled`).
- **Descifrado fail-closed:** si el descifrado falla, se loguea
  `agent_whatsapp_credential_undecryptable` solo con el id del canal y se
  responde 503, sin texto plano ni el mensaje de la excepción.
- **Sin exposición del token:** el log de éxito registra resultado, negocio,
  número y vencimiento; los errores solo su código. El `repr` de la
  credencial resuelta no incluye el token. Tampoco se exponen el id del
  canal, el de la autorización, `key_id` ni `external_id`.
- **Sin sesiones humanas:** la única autenticación es HMAC y el permiso exige
  `AgentPrincipal`. Una sesión de staff, un login de Django o un
  `force_authenticate` reciben 401.
- **Sin efectos:** no hay escrituras en la base (verificado capturando SQL:
  ningún INSERT, UPDATE ni DELETE) ni auditoría.
- **Alcance:** entregar la credencial no autoriza IA (eso sigue siendo
  `ai-usage/authorize`) ni el envío de mensajes. Tampoco prueba que el token
  tenga permisos reales ante Meta: es solo lo que Mi Rubro tiene guardado.

## 4. Infraestructura reutilizada y elementos nuevos

**Reutilizado:**
- `AgentIntegrationView` (flag, envelope, handler de errores, `X-Request-Id`,
  logging técnico) y `AgentHmacAuthentication`;
- `AgentLeadSyncThrottle`, con su mismo scope y límite por instancia;
- la resolución de canales del receiver;
- `resolve_channel_access_token` y las reglas de 04B, en una sola función;
- `errors.*`, `ALLOWED_BUSINESS_STATUSES`, la factory y la base de tests HMAC
  de 03C.

**Nuevo, imprescindible:**
- **`resolve_channel_by_phone`:** es el cuerpo de `resolve_channel`
  extraído. `resolve_channel` ahora lo llama y agrega solo el contraste de
  `business_id`. No es lógica duplicada: el endpoint no conoce el negocio.
- **`resolve_channel_whatsapp_credential`:** el mismo cuerpo de 04B, ahora
  devuelve también canal y vencimiento. `resolve_channel_access_token` quedó
  como wrapper y sus tests de 04B pasan sin cambios. Se sumó la verificación
  de WABA.
- **`agent_whatsapp_credential` (payload) y la vista con su ruta.**
- **`FailClosedAgentHmacAuthentication` y `FailClosedAgentThrottle`:**
  subclases de una línea en los módulos base, para no crear una tercera copia
  local como las de `ai_usage_views` y `ai_telemetry_views`, que quedan sin
  tocar.

**No creado:** modelos, migraciones, scope de throttle nuevo (no hubo que
tocar `settings`), caché de tokens, auditoría por lectura ni dependencias.

## 5. Tests

`apps/leads/tests/test_agent_whatsapp_credential_04c.py`, con 29 tests:

- **Contrato:** resolución por número sin conocer el Business, forma exacta,
  `expires_at`, una instancia con dos negocios, autorización compartida del
  negocio y de plataforma para dos negocios.
- **Aislamiento:** canal de otra instancia (en ambos sentidos), número
  desconocido o inactivo, negocio suspendido, dueño ajeno forzado por
  `update()`, canal legacy sin autorización o sin WABA, reasignación
  concurrente entre las dos lecturas y número malformado (404 del router).
- **Ciclo de vida:** la rotación y la revocación rigen en la consulta
  siguiente; vencida, inválida; token indescifrable (503, sin el cifrado en
  logs).
- **Autenticación:** firma inválida, timestamp fuera de ventana, key
  desconocida, headers ausentes, firma ligada al número, replay, nonce con
  Redis caído, throttle con Redis caído, credencial revocada, instancia
  deshabilitada, sesiones humanas, flag apagado y métodos distintos de GET.
- **Sin secretos ni efectos:** logs de éxito y error sin el token, el cifrado
  ni sus fragmentos; la respuesta sin otros ids ni secretos; ninguna
  escritura SQL y snapshot de modelos y auditoría idéntico.

| Corrida (PostgreSQL 16 descartable, tmpfs) | Resultado |
|---|---|
| 04C + 04B | 63/63 OK |
| Regresión: `apps.leads` completo + 5 suites de `ai-usage` y reception AI | 948/948 OK |
| `manage.py check` / `makemigrations --check` | sin issues / sin cambios |

## 6. Riesgos

- **R1:** el token viaja en el cuerpo de la respuesta. Depende de TLS entre
  el bot y Mi Rubro, y de que el bot no lo loguee ni lo persista (lo cubre
  PROD-04D).
- **R2:** como no hay caché, el bot consulta por cada uso o mantiene el token
  en memoria. El throttle por instancia es el de sync, compartido: si el bot
  consulta en cada mensaje, puede competir con los PUT de sync.
- **R3:** una credencial HMAC comprometida da acceso a los tokens de todos
  los canales de su instancia. Mitigación: revocar la credencial (401
  inmediato) y rotar las autorizaciones.
- **R4:** `expires_at` es el que se cargó localmente; Meta puede invalidar el
  token antes. El estado `invalid` sigue sin setter (PROD-04D).
- **R5:** heredado de 04B: no se puede rotar la clave Fernet y la revocación
  es solo local.

## 7. Commits y HEAD final

Commits sobre `6682c6f`: endpoint y servicio, tests, y este reporte.
Empujados a `origin/feat/recepcionista` sin force push. No se modificó el
bot ni se avanzó a PROD-05.
