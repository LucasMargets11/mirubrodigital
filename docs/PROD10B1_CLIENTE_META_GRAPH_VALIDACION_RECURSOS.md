# PROD-10B1 — Cliente seguro de Meta Graph API y validación de recursos WhatsApp

Fecha: 2026-11-28 · Rama `feat/recepcionista` · Base `8e9caf3` · Bot
`de7e932` sin cambios.

Solo backend. No crea modelos, migraciones, endpoints ni dependencias. No
hace llamadas reales a Meta.

## 1. Contrato interno

Módulo: `apps/leads/services/meta_graph.py`.

| API | Qué hace |
|---|---|
| `verify_whatsapp_resources(*, token, waba_id, phone_number_id, now=None, session=None) -> WhatsAppResourceVerification` | Verificación completa, solo lecturas. El orden es: entrada → configuración → `debug_token` → pertenencia del número a la WABA → suscripción observada. Falla en el primer problema con `MetaGraphError` |
| `MetaGraphClient(session=None)` → `.debug_token(token)`, `.waba_phone_numbers(waba_id, token)`, `.waba_subscribed_apps(waba_id, token)` | Cliente de lectura, un intento por llamada |
| `inspect_token(client, token, *, waba_id, now)` | Solo la inspección del token (reutilizable en PROD-11) |
| `MetaGraphError(code, transient, http_status, meta_code, meta_subcode, detail)` | Error normalizado. El mensaje es el código; `detail` solo lleva metadatos propios: el campo inválido o los nombres de permisos faltantes |

**Resultado: `WhatsAppResourceVerification`**, solo metadatos no secretos.

- `waba_id`, `verified_at`.
- **`token`:** `app_id`, `token_type`, `scopes`, `expires_at` y
  `data_access_expires_at` (`None` = Meta informó 0 o no informó), y
  `scope_coverage` por permiso: `explicit` (la WABA está en `target_ids`) o
  `all_assets` (Meta omite `target_ids`).
- **`phone_number`:** `phone_number_id`, `display_phone_number`,
  `verified_name`, `code_verification_status`, `quality_rating` y
  `platform_type`.
- **`subscription`:** `app_subscribed` y `override_callback_configured`
  (booleano; la URI nunca se devuelve).

El resultado prueba que el token es válido, de nuestra app y con alcance
sobre la WABA, y que el número pertenece a ella. **No prueba la propiedad
legal** de los recursos por parte del comercio.

### Códigos de error

| Grupo | Código | Reintentable |
|---|---|---|
| Configuración | `meta_not_configured` | — |
| Entrada | `invalid_input`, con `detail` `token`/`waba_id`/`phone_number_id`. No llama a Meta | — |
| Token | `token_invalid`, `token_expired`, `token_app_mismatch`, `data_access_expired` | No |
| Permisos y alcance | `permissions_missing` (con `detail` los permisos), `resource_scope_not_granted`, `resource_scope_unverified`, `permission_denied` (Meta 10/200–299) | No |
| Recurso | `resource_not_found` (100/33), `phone_number_not_in_waba`, `meta_request_rejected` (100) | No |
| Transitorios | `meta_rate_limited` (HTTP 429; 4/17/32/613/80007/80008/130429) y `meta_unavailable` (timeout, red, 5xx, 1/2, `is_transient`) | Sí |
| Respuesta | `meta_invalid_response` (redirect, no JSON, esquema, tamaño, paginación excesiva o cursor inválido) y `meta_error` (cualquier otro) | No |

## 2. Configuración

Usa los mismos nombres que el `.env` del bot, porque es la misma app central
de Meta:

| Variable | Default | Regla |
|---|---|---|
| `WHATSAPP_APP_ID` | `''` | Solo dígitos |
| `WHATSAPP_APP_SECRET` | `''` | 16 caracteres como mínimo. Un único secreto de app, nunca por cliente |
| `WHATSAPP_GRAPH_VERSION` | `v23.0` | `vNN.N`. Es el default del bot. Según el [cuadro oficial de versiones](https://developers.facebook.com/docs/graph-api/changelog/versions/) está vigente hasta el 2027-10-08 |
| `WHATSAPP_GRAPH_TIMEOUT_SECONDS` | `10` | Constante en settings, entre 0 y 30 |

Sin configuración válida, solo estas operaciones fallan (`meta_not_configured`)
y sin hacer ninguna llamada. No hay system check bloqueante, así que el resto
de Mi Rubro sigue funcionando.

## 3. Validaciones

**Transporte:**
- Host fijo `https://graph.facebook.com`, versión validada y paths solo con
  ids numéricos validados con los regex de los modelos.
- Sin redirects (un 3xx da `meta_invalid_response`), sin reintentos y con
  timeout.
- Respuesta leída en streaming, con un tope de 1 MiB (por `Content-Length` y
  por bytes leídos).

**Paginación:**
- Usa `paging.cursors.after` validado (`[A-Za-z0-9_-=]`) y reconstruye la URL.
- **Nunca sigue `paging.next`**, porque Meta incluye ahí el `access_token`.
- Tope de 10 páginas de 100. Si se supera, falla: no se decide sobre un
  listado incompleto.

**Token** (`debug_token`):
- `is_valid` debe ser booleano y verdadero.
- `app_id` debe ser nuestro `WHATSAPP_APP_ID`.
- `expires_at` y `data_access_expires_at` deben ser futuros, si Meta los
  informa.
- `scopes` debe incluir `whatsapp_business_management` y
  `whatsapp_business_messaging`.

**Alcance:**
- Por cada permiso requerido tiene que existir su entrada en
  `granular_scopes`.
  - Con `target_ids`, la WABA tiene que estar incluida.
  - Sin `target_ids`, se acepta como `all_assets`: según la referencia de
    `debug_token`, los targets se omiten cuando el permiso aplica a todo.
- **Si falta `granular_scopes` o la entrada de un permiso, el resultado es
  `resource_scope_unverified`.** Nunca se asume acceso universal.

**Recursos:**
- El `phone_number_id` tiene que figurar en `GET /<WABA>/phone_numbers` (con
  los campos acotados en `PHONE_FIELDS`).
- La suscripción se observa en `GET /<WABA>/subscribed_apps`, buscando
  `whatsapp_business_api_data.id` igual a nuestra app.

## 4. Protección de secretos

- **Dónde viaja cada credencial:**
  - El app access token (`app_id|app_secret`) se arma solo en memoria y va
    únicamente en el header `Authorization`.
  - El token del recurso va en el header `Authorization` en las lecturas de
    la WABA.
  - `input_token` va en la query, porque lo exige el contrato de
    `debug_token`, y nunca en la URL armada a mano: `requests` lo agrega
    desde `params`.
- **Logs HTTP:** urllib3 registra en DEBUG la línea `GET /path?query`.
  `_RedactCredentialsFilter`, instalado una sola vez en
  `urllib3.connectionpool`, reemplaza por `[REDACTED]` los valores de
  `input_token`, `access_token`, `appsecret_proof`, `client_secret`, `code` y
  `fb_exchange_token`.
- **Excepciones:** las de `requests`, que pueden contener la URL, se descartan
  (`raise … from None`, sin `__cause__`). Los mensajes y cuerpos de Meta nunca
  se propagan ni se registran.
- **El log propio** registra solo el resultado: WABA, `phone_number_id`,
  `app_subscribed` y la cobertura.
- **Persistencia:** no se guarda nada. `AgentChannel` y
  `WhatsAppAuthorization` no se tocan.

## 5. Compatibilidad

La verificación no depende del origen del token. Sirve igual para:
- Un token de recursos propios en pruebas.
- La vinculación asistida, si Meta la permite (supuesto S1 de 10A, sin
  confirmar).
- Un business token de Embedded Signup.

No asume que la vinculación de terceros esté autorizada.

## 6. Documentación oficial utilizada (leída el 2026-11-28)

- [debug_token](https://developers.facebook.com/docs/graph-api/reference/debug_token):
  `is_valid`, `app_id`, `expires_at`, `data_access_expires_at`, `scopes` y
  `granular_scopes.target_ids` (que se omiten cuando el permiso aplica a todo).
  Se invoca con app access token.
- [Client phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-phone-numbers):
  `GET /<WABA_ID>/phone_numbers` y sus campos.
- [Webhook overrides](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/override):
  `GET /<WABA_ID>/subscribed_apps` con `whatsapp_business_api_data` y
  `override_callback_uri`.
- [Access tokens](https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/)
  y [Manage accounts](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-accounts):
  permisos requeridos y error 200 sin acceso avanzado.
- [Graph API versions](https://developers.facebook.com/docs/graph-api/changelog/versions/):
  v23.0 vigente hasta el 2027-10-08.
- Códigos de error de Graph (190, 10, 200–299, 4/17/32/613, 100/33,
  `is_transient`): guía oficial de manejo de errores de Graph API.

## 7. Componentes

**Reutilizados:**
- `requests` y el patrón de `takeover_client`: config desde settings,
  `allow_redirects=False`, timeout, errores clasificados.
- `PHONE_NUMBER_ID_REGEX` y `WABA_ID_REGEX` de los modelos.
- `TOKEN_MIN_LENGTH`, `TOKEN_MAX_LENGTH` y `_TOKEN_RE` de
  `whatsapp_authorizations`.
- La convención de nombres de env del bot.

**Creados:**
- El módulo `meta_graph.py`.
- Las 3 variables de settings más el timeout.
- 22 tests.

**Evitados:**
- Un SDK de Meta o dependencias nuevas.
- Un system check bloqueante.
- Persistencia.
- Endpoints.

## 8. Tests

`apps/leads/tests/test_meta_graph_10b1.py`: 22 tests con sesión HTTP
simulada. Todas las verificaciones corren dentro de `assertNumQueries(0)`, así
que no hay lecturas ni escrituras en la base.

**Qué cubren:**
- **Token:** válido (metadatos, URLs, headers, params, `allow_redirects`,
  timeout, `stream`), alcance `all_assets`, vencimiento no informado, token
  inválido o vencido (por subcódigo, por fecha y de acceso a datos), app
  incorrecta (sin tocar la WABA), permisos faltantes, alcance insuficiente y
  sin `granular_scopes`.
- **Recursos:** número fuera de la WABA, WABA inexistente, permisos
  denegados y pedido rechazado.
- **Paginación:** por cursor (sin seguir `next`), tope de páginas y cursor
  inválido.
- **Suscripción:** nuestra app con y sin override, otra app y ninguna.
- **Transporte:** timeout y red (transitorios, sin cadena de excepción),
  rate limits, 5xx y `is_transient`, 190/463, errores desconocidos, error en
  un 200, redirect, no JSON, esquema inválido, tamaño por header y por
  streaming, respuesta cerrada siempre.
- **Configuración:** ausente o inválida da `meta_not_configured`, sin
  llamadas. El default es `v23.0`.
- **Entrada:** inválida da `invalid_input`, sin llamadas.
- **Secretos:** ningún secreto en los logs (éxito y fallas), la línea de
  urllib3 aparece redactada y los mensajes de Meta nunca se propagan.

**Regresión** (PostgreSQL 16 descartable + Redis 7):

| Suite | Resultado |
|---|---|
| `test_meta_graph_10b1` + WhatsApp 04B, 04C, 08E1, `provision_command` y 02E4C | 128/128 OK |
| `apps.leads` completo | 940/940 OK (918 + 22) |
| `manage.py check` | Sin problemas |
| `makemigrations --check --dry-run` | `No changes detected` |

## 9. Limitaciones

- **Supuestos sin verificar** contra Meta real (quedan para PROD-10E,
  sandbox con número propio):
  - Que Graph acepte el app access token en el header `Authorization: Bearer`
    para `debug_token`. La referencia indica app token, pero no detalla el
    transporte.
  - Los códigos de error exactos que devuelve cada lectura.
  - Que `expires_at = 0` signifique "sin vencimiento".
- **Permisos de la app:** sin App Review ni acceso avanzado (S4 de 10A),
  las lecturas sobre WABAs de terceros devolverán `permission_denied`.
- **Redacción en logs:** cubre urllib3. Un handler externo que registre
  requests con otro logger no queda cubierto. En este proyecto no existe
  ninguno.
- **Fuera de este slice:** almacenamiento, rotación, revocación,
  desactivación, suscripción de webhooks, registro de números, endpoints y UI
  (PROD-10B2 en adelante).
