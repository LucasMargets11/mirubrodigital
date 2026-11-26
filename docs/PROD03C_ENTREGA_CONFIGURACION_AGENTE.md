# PROD-03C — Entrega segura de configuración al agente

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `6057203` · Bot
`8b69e4d` sin cambios. Referencias: PROD-03A, PROD-03B,
`docs/LEADS_PROPOSAL_CONFIRMATION_SIGNAL.md` (Contract V1 HMAC).

## 1. Endpoint

`GET /api/v1/integrations/agent/businesses/{business_id}/channels/{phone_number_id}/receptionist-config/`

- Montado en la infraestructura existente `/api/v1/integrations/agent/`,
  sobre `AgentIntegrationView`. Hereda el flag `AGENT_INTEGRATION_ENABLED`
  (apagado da 503), la auth HMAC Contract V1, el throttle por instancia, el
  envelope de errores, `X-Request-Id` y el log técnico sin PII.
- **Por qué los ids van en el path:** la firma HMAC cubre el path, no el
  query string. Ponerlos en el path deja business y canal firmados, sin
  cambiar la autenticación. Se firma igual que `appointment-context`: `GET`,
  path exacto con slash final y SHA-256 del body vacío.
- El Business se resuelve solo con `resolve_channel`: canal activo del
  `phone_number_id`, perteneciente a la instancia autenticada. `business_id`
  no elige el tenant; solo se contrasta con el del canal, igual que en
  `lead.sync`. Si difieren, `409 business_mismatch`.
- No necesita Lead ni conversación: funciona desde el primer mensaje.
- Respuesta con `Cache-Control: no-store`. Solo lectura: no crea, no
  modifica y no audita.

## 2. Contrato JSON real

Capturado de `agent_receptionist_config` sobre PostgreSQL descartable:

```json
{
  "ok": true,
  "contract_version": 1,
  "business": {
    "id": 1,
    "name": "Peluquería Demo",
    "timezone": "America/Argentina/Buenos_Aires",
    "address": "Av. Siempreviva 742, Posadas",
    "website": "https://peluqueria.test",
    "whatsapp_phone": "+5493764000000"
  },
  "channel": {"provider": "whatsapp_cloud", "phone_number_id": "1234567890"},
  "config": {
    "status": "ready",
    "version": 1,
    "updated_at": "2026-11-26T09:36:11.362063+00:00",
    "missing_for_ready": [],
    "content": {
      "assistant_name": "Sofía",
      "business_category": "Peluquería",
      "business_description": "Peluquería unisex en el centro.",
      "custom_instructions": "",
      "tone": "warm",
      "language": "es-AR",
      "welcome_message": "¡Hola! Soy Sofía, ¿en qué te ayudo?",
      "operational_info": "",
      "business_hours": "",
      "services": [{"name": "Corte", "description": "Corte y peinado."}],
      "reference_info": "",
      "faqs": [{"answer": "Sí, con turno previo.", "question": "¿Hacen color?"}],
      "handoff_rules": ""
    }
  }
}
```

Borrador (mismo negocio, después de vaciar la bienvenida):

```json
"config": {
  "status": "draft", "version": 2, "updated_at": "2026-11-26T09:36:11.380419+00:00",
  "missing_for_ready": ["welcome_message"], "content": null
}
```

Sin configuración:
`"config": {"status": "missing", "version": null, "updated_at": null, "missing_for_ready": null, "content": null}`.

- **`config.status`:** los tres estados se distinguen. `content` solo viaja
  con `ready`; un borrador, aunque esté completo, no entrega texto usable.
- **`config.version`:** es la de `ReceptionistConfig`. Sube con cambios de
  contenido o estado, no con cambios de Business ni de sus perfiles (nombre,
  dirección, zona horaria, WhatsApp). Esos datos se leen en vivo en cada
  request y no se copian.
- **Consistencia:** estado, versión, `updated_at` y contenido salen de una
  única lectura de la fila, así que siempre son coherentes entre sí.
- **`business`:** datos comerciales públicos.
  - De `Business`: nombre y zona horaria.
  - De `BusinessBillingProfile`: dirección comercial y web.
  - De `BusinessBranding`: WhatsApp público (el opt-in de 6D).
  - Un perfil ausente da `null`, no error.
- **`contract_version`:** sube solo ante cambios incompatibles; los campos
  aditivos no lo mueven.

**Errores** (envelope Contract V1):
- `401 invalid_signature`: firma, credencial, timestamp, replay o instancia.
- `403 channel_disabled`: canal ajeno, desconocido o inactivo.
- `403 business_inactive`.
- `409 business_mismatch`.
- `404` del router: path malformado.
- `405`: otro método.
- `429` y `503`.

## 3. Seguridad

- **Autenticación:** reutiliza `AgentHmacAuthentication` sin cambios
  (credencial `active`/`retiring`, instancia habilitada, ventana de
  timestamp, `compare_digest`, nonce de `X-Request-Id`). Como
  `appointment-context`, no usa la variante fail-closed del nonce: es una
  lectura idempotente y sin efectos. La firma queda atada al path; firmar
  para un negocio y pedir otro da 401.
- **Sesiones humanas:** una sesión de usuario (aunque sea superadmin) no
  autentica como agente y recibe 401.
- **Qué nunca sale:** secretos, `key_id`, `external_id` de la instancia, id
  interno del canal, razón social, CUIT, IVA, IIBB, domicilio fiscal ni
  email o teléfono de facturación. Tampoco capacidades, plan, cupos ni
  agenda (los tests lo verifican sobre el body crudo).
- **`ready` no autoriza:** no habilita el uso del bot ni la IA. Cada
  interacción sigue autorizándose con `ai-usage/authorize`, sin cambios, y
  la agenda con `appointment-context.agenda_enabled`. No se agregó gating
  comercial a la lectura: entregar la configuración no habilita nada. No se
  tocaron el resolvedor IA ni el enforcement general.

## 4. Aislamiento

- **Una instancia con dos negocios:** cada canal devuelve su negocio y su
  configuración.
- **Canal de otra instancia:** `channel_disabled`, aunque exista la
  configuración de ese negocio.
- **`business_id` ajeno con un canal propio:** `business_mismatch`, sin
  filtrar contenido.
- **Negocio suspendido:** `business_inactive`.

## 5. Infraestructura reutilizada y elementos nuevos

**Reutilizado:**
- `AgentIntegrationView` (flag, auth, throttle, envelope, logging) y
  `AgentHmacAuthentication` con su nonce;
- `resolve_channel` y sus errores, y `receptionist_config_for_agent`
  (ahora sobre un helper común);
- `ReceptionistConfig` con su `version`, `missing_for_ready`, `is_ready` y
  `CONTENT_FIELDS`;
- `Business`, `BusinessBillingProfile` y `BusinessBranding` como fuente de
  los datos públicos;
- el patrón `no-store` de `appointment-context`;
- `ReceiverTestBase`, `sign_headers` y las factories de tests.

**Nuevo, imprescindible:**
- `agent_receptionist_config` y dos helpers privados en el servicio
  existente `services/receptionist_config.py`: construyen el payload.
- `_resolve_for_agent`: comparte una sola resolución entre la función de
  03A y el payload, para no resolver el canal dos veces.
- Una vista de 15 líneas en `views.py` y una ruta en `integration_urls.py`.
- Sin modelos, migraciones, credenciales, caché ni ETags.

**Duplicaciones evitadas:** no hay autenticación ni permisos paralelos; no
se copian datos de Business; no hay un serializer nuevo del contenido (usa
`CONTENT_FIELDS`); no hay tabla de versiones ni de historial.

## 6. Tests

`apps/leads/tests/test_agent_receptionist_config_03c.py`, con 22 tests:

- **Contrato:** forma completa con `ready` y sin Lead; perfiles ausentes dan
  `null`; `missing`; un `draft` nunca entrega contenido (ni siquiera
  completo); actualización de contenido y versión, incluida la vuelta a
  borrador; cambios de Business se leen en vivo sin mover la versión.
- **Aislamiento:** una instancia con dos negocios; canal ajeno; canal
  desactivado o desconocido; `business_mismatch` sin filtrar contenido;
  negocio suspendido; path malformado da 404.
- **Autenticación:** firma inválida, key desconocida, timestamp fuera de
  ventana; credencial revocada (una nueva sí funciona) e instancia
  deshabilitada; replay de `X-Request-Id`; firma atada al path; una sesión
  humana no es un agente; flag apagado da 503; solo GET.
- **Sin secretos ni efectos:** sin datos fiscales, de facturación, secretos
  ni identificadores internos; GET sin efectos (conteo de todos los modelos
  de `leads`, auditoría y fila de configuración idénticos tras 4 GETs);
  `missing` no crea nada.

| Corrida (PostgreSQL 16 descartable, tmpfs) | Resultado |
|---|---|
| `test_agent_receptionist_config_03c` | 22/22 OK |
| `apps.leads` + AI usage (`appointments` s8a–s8i, complimentary; `billing` 02e3a, 02e3b) | 1131/1131 OK (sin fallas) |
| `manage.py check` | sin issues |
| `makemigrations --check` | No changes detected |

## 7. Riesgos

- **R1:** el nonce es fail-open si Redis cae (igual que `appointment-context`).
  Un replay solo podría repetir una lectura idempotente. La firma y el
  timestamp siguen siendo obligatorios.
- **R2:** `business.timezone` viene de `Business` aunque la configuración no
  esté lista. Es dato público y no conversacional.
- **R3:** el bot todavía no consume este endpoint (PROD-04): hasta entonces
  sigue usando su prompt hardcodeado.
- **R4:** sin caché ni ETag por pedido explícito. El bot deberá decidir
  cuándo consultarlo (por ejemplo, por conversación), apoyándose en
  `version` y `updated_at`.

## 8. Resultados y HEAD final

Regresión: 1131/1131 OK, `check` sin issues, sin migraciones pendientes. Commits sobre
`6057203`: endpoint y servicio, tests, y este reporte. Empujados a
`origin/feat/recepcionista` sin force push. No se tocó el bot ni se avanzó a
PROD-04.
