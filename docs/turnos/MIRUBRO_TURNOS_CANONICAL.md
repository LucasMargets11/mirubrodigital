# MiRubro Turnos — Fuente Canónica de Producto

> **Estado:** CANÓNICO  
> **Ubicación sugerida en el repo:** `docs/turnos/MIRUBRO_TURNOS_CANONICAL.md`  
> **Fecha de consolidación:** 2026-10-27  
> **Uso:** este documento debe tomarse como fuente de verdad para diseño, implementación, billing, entitlements, UX, prompts a Copilot y decisiones futuras relacionadas con MiRubro Turnos.

---

## Integración S8H — autorización previa al LLM (2026-10-29)

### Flujo real verificado antes de modificar código

- Agente externo: `src/modules/whatsapp/whatsapp.controller.ts`, `receiveWebhook`, recibe el webhook firmado de Meta, persiste el inbound con `waMessageId` único y agenda `processBatch` mediante debounce. La memoria persiste el timestamp del mensaje; no se usa el reloj del retry.
- `processBatch` verifica takeover/pausa, separa mensajes no soportados y responde a un batch exclusivamente no soportado sin LLM. El modo `fixed` también responde sin LLM. Para texto en modo `openai`, construye `agentInput` y llama a `OpenAIService.generateAgentResponse`. La eventual corrección de cierre (`closingRetryReply`) vuelve a llamar al mismo servicio con el mismo contexto de interacción.
- La llamada efectiva al proveedor es `src/modules/openai/openai.service.ts`, `client.responses.create`. La autorización S8H está inmediatamente antes de esta llamada y fuera del catch del proveedor; también cubre la corrección de cierre. Se deshabilitan retries internos del SDK para no introducir invocaciones ocultas. El endpoint de desarrollo no obtiene permiso sin contexto canónico; no es un bypass ni acepta identidad IA desde su body.
- Conversación existente: `Conversation.externalConversationId`, `wac1_` + 32 hex de HMAC sobre el número del negocio y el `wa_id`. Se toma de la memoria persistente usada para takeover; no se envían teléfonos, mensajes ni prompts al endpoint de metering.
- Mi Rubro resuelve la conversación mediante `LeadAgentState`, `AgentChannel` activo e instancia HMAC autenticada. Todos deben concordar en Business e instancia. Varios episodios Lead del mismo canal son válidos; más de un canal/negocio es ambiguo y se bloquea. No se acepta `business_id`, ni siquiera como campo adicional.
- El sync inicial de Lead es asíncrono y puede no haber llegado: en ese caso se devuelve `unsafe_conversation_context`, sin crear Lead artificial, sesión ni ledger y sin llamar al LLM. No se infiere consumo del sync. La integración y el contexto sincronizado deben estar operativos antes de habilitar tráfico IA.

### Contrato interno único (Mi Rubro es fuente de verdad)

`POST /api/internal/appointments/ai-usage/authorize/`, JSON, autenticación **AgentHMAC v1** existente (`AgentHmacAuthentication`). Reutiliza `AGENT_INTEGRATION_ENABLED`, credenciales cifradas e instancia técnica; no autentica usuarios, cookies, JWT ni Membership. El agente usa sus variables existentes `MIRUBRO_BASE_URL`, `MIRUBRO_AGENT_KEY_ID`, `MIRUBRO_AGENT_SECRET` y configuración de sync. La rotación existente admite credenciales `active`/`retiring` y rechaza `revoked`; la comparación sigue siendo `hmac.compare_digest`. Nunca se persiste ni se loggea el secreto en texto plano; no se introduce otra credencial.

Headers: `X-Agent-Key-Id`, `X-Agent-Timestamp` (segundos Unix), `X-Request-Id` (nonce UUID nuevo por intento HTTP), `X-Agent-Signature` (`v1=<HMAC-SHA256>`). La firma cubre método **POST**, path exacto con slash final, timestamp, nonce, key id y hash del body, con el canonical string v1 existente.

Request: exactamente estos tres campos, obligatorios:

```json
{
  "external_conversation_id": "wac1_0123456789abcdef0123456789abcdef",
  "interaction_id": "d591209a-09ad-838a-9b82-d6f58404af03",
  "occurred_at": "2026-10-29T12:00:00.000Z"
}
```

`interaction_id`: UUIDv8 determinístico, primeros 128 bits de SHA-256 de `JSON.stringify(["mirubro-ai-s8h-v1", externalConversationId, waMessageId])`, con bits UUID versión/variante normalizados. Se usa el último inbound de texto persistido del batch, no el UUID del Lead ni IDs aleatorios. `occurred_at` conserva su timestamp persistido, con zona explícita. Los retries y la corrección de cierre conservan los tres campos; **solo el nonce/firma HTTP cambia**.

HTTP 200 autorizado, sin información económica:

```json
{
  "allowed": true,
  "session_id": "d591209a-09ad-838a-9b82-d6f58404af03",
  "created": false,
  "usage_tier": "ai_300",
  "period_start": "2026-10-12T14:30:00Z",
  "period_end": "2026-11-12T14:30:00Z",
  "used": 123,
  "included": 300,
  "remaining": 177
}
```

HTTP 200 bloqueado: `{"allowed": false, "reason": "<codigo>"}`.

| Código estable | Significado |
|---|---|
| `hard_cap_reached` | S8B no admite una sesión nueva; una ventana vigente puede reutilizarse según S8A/S8B. |
| `suspended` | Business o lifecycle actual sin acceso; incluye grace vencido y fin efectivo de cancelación. |
| `invalid_tier` | Tier desconocido, histórico sin resolver o configuración IA inválida. |
| `no_ai_entitlement` | Sin suscripción efectiva IA canónica. |
| `manual_contract_required` | `custom` requiere resolución comercial manual, sin defaults. |
| `unsafe_conversation_context` | Contexto inexistente, ambiguo, inactivo o ajeno a la instancia. |
| `interaction_conflict` | Se intentó reutilizar la interacción con otra conversación o timestamp. |
| `interaction_expired` | La ventana original ya venció; el replay no autoriza consumo actual. |
| `invalid_request` | Timestamp futuro; los errores estructurales se rechazan con HTTP 400. |
| `usage_unavailable` | Otra configuración canónica de usage/período no resuelta; sin fallback. |

Los errores HTTP conservan el envelope de integración existente: HTTP 400 `invalid_request`, 401 `invalid_signature`, 429 `rate_limited`, 503 `unavailable`; un error inesperado es HTTP 500 `internal_error`. No se interpreta ninguno como autorización. Solo HTTP 200 con respuesta completa y `allowed` booleano verdadero habilita IA.

### Atomicidad, fallo cerrado y separación de S7

- Se bloquea Business y se delega en los servicios S8A/S8B/S8C existentes. Sesión y ledger se crean juntos; el nuevo recibo `AppointmentAIUsageAuthorization` (migración expansiva `appointments.0015`) vincula **también interacciones que reutilizan** sesión con unicidad `(business, interaction_id)`. No modifica precios, reglas de 24h ni ledger previo.
- Cada invocación consulta backend, también con sesión reutilizada; no hay caché local de 24h. Se reevalúa lifecycle/tier **actual** antes de aceptar el timestamp histórico y se rechaza una ventana vencida. Un rechazo revierte sesión/ledger/recibo creados dentro de la transacción.
- Timeout total explícito de **3000 ms** para autorización, sin redirects y sin retries automáticos. Un caller que repita la autorización conserva interacción/timestamp y renueva nonce HMAC.
- En el agente, HTTP 401/403 se normaliza a `service_authentication_failed`; HTTP no exitoso/red caída a `backend_unavailable`; timeout a `authorization_timeout`; respuesta incompleta/desconocida a `invalid_authorization_response`; integración apagada a `metering_unconfigured`. Todos impiden invocar LLM.
- El batch bloqueado usa la respuesta determinística de error/derivación existente y marca el inbound como procesado, evitando un bucle de LLM. Si falla solo la autorización de una corrección de cierre, se conserva la primera respuesta ya obtenida, sin segunda llamada IA.
- Modo fijo, takeover, batch no soportado, delivery statuses, `lead.sync`, mensajes salientes genéricos y outbound tradicional no llaman este endpoint. S7 sigue en los servicios de reminders/deliveries de Mi Rubro, con su gate `appointments.automations` independiente.
- Logs S8H: Business resuelto, hash estable de conversación, sesión, created/reused y resultado; agente: UUID de interacción y códigos internos. No registrar body, prompts, mensajes, firma, secretos ni access tokens. Se eliminan los logs de contenido del flujo IA intervenido.
- No habilita cobros, Mercado Pago, invoices, IVA, dispatch S8F, cambios a `SubscriptionV2.amount`, UI ni S8I.

### Validación S8H

- **Mi Rubro: 283/283 tests aprobados**, exit code 0, sin skips, en PostgreSQL 16 descartable. Selección: `apps.appointments.tests.test_ai_usage_s8a` hasta `test_ai_usage_s8h` y `apps.customers.test_appointments_outbound_s7b`. Incluye 21 tests S8H (HTTP HMAC, idempotencia de apertura/reutilización, conflictos, lifecycle/tier, aislamiento tenant, payload inválido y dos carreras PostgreSQL) y una aserción explícita de que reminders/no-show S7 no autorizan ni crean usage IA.
- **Agente: 459/459 tests aprobados**, exit code 0, 17 suites relevantes de `modules/openai`, `modules/whatsapp` y `modules/mirubro-sync`, excluyendo los specs `.pg.spec.ts` del agente. LLM/Meta mockeados y servidor Mi Rubro simulado en loopback; no APIs reales. Cubre orden autorización/LLM, denegaciones, timeout, backend caído, respuesta reutilizada, identidad estable, branches determinísticos, outbound tradicional, HMAC POST y ausencia de secretos/contenido en logs.
- Lint focalizado del agente: exit code 0, sin errores; seis warnings preexistentes de non-null assertions en controller/tests. Build Nest/TypeScript: exit code 0. No se agregaron dependencias.
- `python services/api/manage.py check`: sin issues. `makemigrations --check --dry-run`: `No changes detected`. Sintaxis Pylance de vista, servicio y tests S8H: sin errores.
- Cache y broker/backend Celery en memoria durante las pruebas Django; infraestructura de prueba aislada, sin workers ni dispatch reales. La migración nueva se aplicó solamente en la base descartable de tests, **no** en la base habitual/compartida. Aplicar `appointments.0015` con sus dependencias al desplegar ambos repositorios.

## S8I - rollout seguro y operacion de S8H (2026-10-30)

### Gates y alcance

- `AI_USAGE_METERING_ENABLED=false` es el default explicito tanto en Mi Rubro como en el agente. Solo `true` habilita el gate. Es independiente de `AGENT_INTEGRATION_ENABLED`: apagar metering no apaga `lead.sync`, takeover ni los flujos deterministas sin LLM.
- El gate se verifica en la vista y en el servicio de autorizacion. Apagado, una solicitud canonica autenticada devuelve `{"allowed": false, "reason": "metering_disabled"}` sin crear sesiones, ledger ni recibos. El agente no puede convertir un error o una desactivacion en permiso para llamar al LLM.
- En el agente, `MIRUBRO_SYNC_ENABLED` sigue siendo independiente. Con metering encendido, el guard exige sync habilitado y configuracion valida de `MIRUBRO_BASE_URL`, `MIRUBRO_AGENT_INSTANCE_ID`, `MIRUBRO_BUSINESS_ID`, `MIRUBRO_AGENT_KEY_ID`, `MIRUBRO_AGENT_SECRET` y `MIRUBRO_CONVERSATION_ID_KEY`; solo muestra nombres/reglas, nunca valores. Sin variable de flag el default es `metering_disabled`; sin configuracion del servicio/autorizador se bloquea con `metering_unconfigured`.
- La infraestructura existente de `business.features` deriva acceso de planes/entitlements; no es una plataforma de rollout por tenant. S8I usa **solo flag global**, sin porcentajes, listas nuevas de negocios ni cambios al catalogo. Los permisos actuales por Business siguen siendo obligatorios, pero no se reinterpretan como cohortes de rollout.
- Las variables se leen al iniciar cada proceso. Cambiar configuracion y hacer restart/rolling restart de **todos** los procesos afectados, sin reconstruir imagen ni modificar codigo. No hay hot reload: un proceso antiguo conserva su valor hasta reiniciar. Nunca enrutar trafico a una version anterior que no respete el gate.

### Health/readiness y guards

- `GET /api/internal/appointments/ai-usage/health/`, firmado con **AgentHMAC v1**, metodo `GET`, path exacto con slash final y SHA-256 del body vacio. Usar timestamp actual y **nonce UUID nuevo para cada probe**; el nonce es `X-Request-Id` y la respuesta lo conserva. No usar cookies, JWT ni un probe publico sin firma.
- Respuesta HTTP 200: `{"status":"ok","metering_enabled":false,"agent_integration_enabled":true,"database":"ok"}`. Solo cuatro campos tecnicos; sin credenciales, precios, conversaciones ni datos de clientes. `Cache-Control: no-store`; las respuestas de autorizacion tampoco se cachean.
- Readiness verifica conectividad, registro de `appointments.0015_ai_usage_authorization` y lectura de columnas de session/ledger/receipt. Una base sin 0015 **no esta lista**, aun con el flag apagado. Base/esquema no disponible o metering encendido con integracion apagada: HTTP 503. Un fallo de HMAC, nonce, throttle o DB durante autenticacion conserva el envelope seguro de errores de integracion, no revela detalles internos.
- El health sigue autenticado cuando `AGENT_INTEGRATION_ENABLED=false`, para poder diagnosticar ese estado. Con ambos flags apagados y DB lista devuelve `ok`; esto indica estado tecnico, **no permiso de consumo**. Exige credencial existente y clave de cifrado operativa.
- `manage.py check` detecta metering encendido sin integracion (`appointments.E001`); los checks de cifrado HMAC existentes siguen vigentes. Antes de activar, ejecutar tambien `python manage.py check --database default` **con la configuracion candidata encendida**: `appointments.E002` detecta base/esquema/migracion no disponible. El check de DB es opt-in para no impedir aplicar migraciones primero.

### Observabilidad sin contenido

- Se reutilizan `logging` y el formatter JSON de produccion (`LOG_FORMAT=json`); no se agrega Prometheus ni otro stack. Logger `apps.appointments.ai_usage_views` a INFO, aun si el nivel global es WARNING.
- Un evento `event=ai_usage_authorization` por respuesta, `count=1`, con `metric` igual a `authorization_allowed` (nueva sesion), `authorization_reused`, `authorization_blocked`, `authorization_auth_failed`, `authorization_timeout` o `backend_error`. `reason` permite contar separadamente `unsafe_conversation_context`, `hard_cap_reached`, `no_ai_entitlement`, `invalid_tier`, `metering_disabled` y las demas denegaciones S8H. No sumar los antiguos mensajes de servicio como eventos adicionales.
- `duration_ms` usa reloj monotono e incluye HMAC, throttle y autorizacion. Retener estas muestras permite obtener p50/p95/p99 despues en el consumidor de logs; S8I no calcula percentiles locales ni agrega analytics. Comparar volumen, tasas de bloqueo/error y latencia antes/despues de activar; observar spikes de timeout del agente y HTTP 5xx/429.
- Correlacion: `interaction_id` UUID validado, `request_id` (nonce HMAC validado), `business_id` resuelto, `conversation_hash`, `session_id` y `session_created`. El recibo se encuentra por `(business_id, interaction_id)` y referencia esa session. En errores previos a validar el payload no se loggea una identidad de interaccion no confiable. No se guarda el nonce en el ledger ni se modifica la identidad idempotente.
- Nunca loggear body, contenido, prompts, telefonos, firma HMAC, canonical string, secretos ni tokens. Los errores tecnicos usan codigos/tipos, no mensajes crudos de excepciones. El agente mantiene timeout total de **3 segundos**, sin retries de autorizacion, sin redirects y sin retries ocultos del SDK del proveedor; diferencia timeout, DNS/conexion, HTTP 5xx, autenticacion y respuesta invalida.
- El agente emite JSON con el logger Nest existente: `authorization_timeout`, `authorization_connect_error`, `authorization_http5xx`, `authorization_auth_failed`, `authorization_invalid_response` y `authorization_backend_error`, ademas de allowed/reused/blocked. Incluye duracion, status, interaccion y nonce sanitizados; no URLs ni errores crudos. `signMirubroRequest()` existente puede firmar el probe GET con `body: Buffer.alloc(0)` y pathname exacto.

### Throttle, replay y cache

- Se reutiliza el scope `agent_leads_sync`, configurable con `AGENT_LEADS_SYNC_THROTTLE_RATE`, default **600/minute por AgentInstance**, compartido con sync/context y probes de health. Rotar key IDs no reinicia ese presupuesto. No hay cuota nueva ni limite arbitrario por Business: varios negocios en una instancia comparten capacidad; dimensionar usando trafico observado, incluyendo autorizaciones de correccion de cierre y probes. HTTP 429 conserva `Retry-After`, pero el agente no reintenta autorizaciones automaticamente.
- No confundir throttle de proteccion con cuotas IA: el hard cap sigue en S8B. El throttle DRF existente es una proteccion de trafico con cache, no un contador contractual exacto bajo concurrencia.
- Se conserva protocolo HMAC v1, tolerancia de reloj **+/-300 segundos** y nonce **600 segundos** por credencial. Fuera de ventana se rechaza; dentro de tolerancia se admite; mismo nonce se rechaza; cualquier alteracion del body invalida firma.
- Hardening acotado: authorize/health **fallan cerrado** si falla el cache de nonce o throttle (503), en vez del fail-open legacy pensado para sync idempotente. El comportamiento de sync no cambia. Usar el Redis compartido existente entre workers/replicas; cache local por proceso no da proteccion global de replay/throttle. Validar sincronizacion NTP y cache antes de activar. Los headers se validan completos para evitar inyeccion de saltos de linea en correlacion/logs.

### Orden de despliegue (sin activacion automatica)

1. Desplegar Mi Rubro con metering **off** y aplicar sus migraciones, incluida **appointments.0015** y dependencias. Desde `services/api`: `python manage.py migrate`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`. No ejecutar un downgrade destructivo como rollback.
2. Con credencial interna operativa, verificar health firmado: DB `ok`, metering `false`. Revisar tambien Redis compartido, reloj y presupuesto del throttle.
3. Desplegar el agente S8I con su flag **off**, URL/credencial de sync correctas y providers mockeados en las pruebas. Confirmar que no intenta LLM cuando metering no esta habilitado.
4. Mantener ambos flags off hasta verificar HMAC con health (GET firmado y nonce nuevo), sync/contexto canonico y guards con la configuracion candidata. No usar una llamada al LLM para probar conectividad.
5. Activar primero el gate de Mi Rubro y reiniciar sus procesos; confirmar health/checks. Activar despues el gate del agente y reiniciar sus procesos. En el intervalo el agente sigue cerrado. Rollout global y supervisado; sin porcentajes inventados.
6. Observar eventos, motivos, 5xx/429 y latencia; ampliar trafico operativo solo tras validar salud. No activar cobros ni dispatch como parte del rollout.
7. **Rollback = apagar flag de metering**, primero en Mi Rubro y despues en el agente, propagandolo a todos los procesos. Las nuevas autorizaciones quedan denegadas; una llamada ya autorizada/en vuelo no se puede deshacer. No borrar receipts, sesiones, ledger, conversaciones ni migraciones. Rehabilitar despues reevalua politica actual y reutiliza ventanas vigentes segun S8H, sin doble consumo.

### Recovery fail closed

| Incidente | Accion operativa |
|---|---|
| Mi Rubro caido / DNS / conexion / 5xx / timeout | Mantener IA bloqueada; distinguir categoria en logs del agente, restaurar DB/red/backend, verificar health/HMAC y luego habilitar. Sin retries automaticos ni bypass; usar la respuesta determinista/derivacion existente. |
| Metering deshabilitado | Esperar `metering_disabled`, sin nuevos consumos ni LLM. Confirmar flags efectivos en todos los procesos; solo activar tras completar guards/health. |
| HMAC revocado / 401 / 403 | Mantener bloqueo, revisar estado de instancia/credencial; provisionar/rotar con mecanismo existente y verificar health con nuevo nonce. No imprimir ni loggear secretos para diagnosticar. |
| Sync atrasado / `unsafe_conversation_context` | Restaurar `lead.sync` y validar canal activo, instancia y Business concordantes. No crear Lead artificial ni inferir consumo desde sync. Un mensaje posterior puede autorizarse al recuperar contexto; no reprocesar automaticamente el batch bloqueado ni cambiar su identidad. |
| `hard_cap_reached` | Mantener denegacion de nuevas ventanas; revisar periodo/entitlement y canal comercial existente. No elevar limites ni cambiar tier/precio para sortear el bloqueo. |
| 0015 pendiente / `appointments.E002` / DB no lista | Dejar flag off, aplicar 0015 y dependencias en Mi Rubro, verificar health y check de DB antes de activar el agente. No falsear registro de migracion ni tocar historico. |

S8I no habilita Mercado Pago, cobros reales, invoices, IVA, UI de billing ni dispatch S8F; tampoco modifica pricing, ventanas, importes ni semantica de la migracion 0015. No implementa S8J.

### Validacion S8I

- **Mi Rubro: 348/348 tests aprobados**, exit 0, sin skips: S8A-S8I, outbound S7B, HMAC, replay, throttle y logs del receiver, contrato y checks. S8I agrega 26 tests; S8H mantiene sus 21 tests, incluidas carreras PostgreSQL. Reejecucion focalizada final: 64/64 (S8I + S8H + HMAC).
- PostgreSQL 16 descartable, cache y Celery en memoria, sin workers ni providers reales. Health verificado tambien por HTTP real en loopback: GET firmado 200 con forma minima/correlacion/no-store, anonimo 401 y contexto no sincronizado denegado sin session/receipt. No es una prueba E2E contra Meta/OpenAI.
- `manage.py check`, `manage.py check --database default` con metering/integracion habilitados y `makemigrations --check --dry-run`: exit 0, sin issues/cambios. Pylance: sin errores de sintaxis en vistas/checks/tests y hardening HMAC/throttle. Migraciones aplicadas **solo** en PostgreSQL descartable; no en la base habitual ni de produccion.
- Una ejecucion extendida de 404 tests del receiver completo y S8 encontro **19 errores ajenos a S8I**: fixtures de `CrmIsolationTests`/`ProposalConfirmationTests` crean profesionales sin suscripcion Turnos y fallan con `ProfessionalQuotaUnavailable`. No se modificaron esas fixtures ni el quota guard. Esa ejecucion extendida **no esta verde**; los 348 tests relevantes anteriores si.
- **Agente: 846 tests aprobados, 105 omitidos**, 37 suites aprobadas y 5 omitidas, exit 0. Seleccion S8I/S8H: 71 aprobados, exit 0. Build Nest/TypeScript: exit 0. Los omitidos requieren `OUTBOX_PG_TEST_URL`; sin E2E real agente-Django/Meta/OpenAI.
- Lint del agente focalizado en cambios funcionales S8I: exit 0, 0 errores y 6 warnings existentes. Lint completo: **exit 1, 188 errores/40 warnings preexistentes** (177 errores en archivos sin cambios respecto a HEAD; 11 `no-inferrable-types` ya presentes en `env.validation.ts`). No se corrigio baseline ajeno ni se declara lint global aprobado.
- Todo con tooling/cache de imagenes ya instalado, sin instalaciones ni acceso externo. Sin commits, cobros, activaciones automaticas ni modificaciones a la migracion 0015.

## 1. Propósito de este documento

Este archivo consolida las decisiones de producto actualmente definidas para **MiRubro Turnos**.

Ante cualquier contradicción entre código legacy, documentación histórica, nombres anteriores de planes o decisiones viejas y este archivo, **este documento prevalece para el diseño futuro del producto**, salvo que posteriormente sea actualizado de forma explícita.

No debe interpretarse como una descripción exacta del estado actual del repositorio. El repo contiene funcionalidades ya implementadas, parciales y ausentes. Este documento define el **producto objetivo y sus reglas canónicas**.

## Estado de implementación — S2 (2026-10-28)

El catálogo y pricing declarativo de S2 está preparado, **sin publicar ni habilitar venta**:

- Fuente única: [pricing TypeScript](../../apps/web/src/lib/pricing/index.ts) → [exportador](../../apps/web/src/lib/pricing/export-json.ts) → [generated/pricing.json](../../generated/pricing.json) → [lector Python](../../services/api/src/apps/billing/canonical_pricing.py). Regenerar desde la raíz con `npx tsx apps/web/src/lib/pricing/export-json.ts`.
- Se exportan `products`, `plans`, `addons`, `extras` y `usage_tiers`. Las ofertas de los otros verticales conservan su semántica y tienen regresión por snapshot.
- `products.appointments.is_active = false`. Los endpoints públicos de productos, bundles y módulos no ofrecen Turnos; cotización e inicio de checkout rechazan los planes canónicos inactivos incluso si hubiera filas activas en DB.
- `appointments_ai` es un único plan lógico con precio fijo `null`, resuelto mediante `usage_tier`. Los tiers son precios completos, no recargos sobre Pro/Automatizaciones. `custom` queda `contact_sales` / `manual`, sin precio cero.
- `appointments_extra_professional` es exclusivamente un extra de cantidad entera no negativa; no es un segundo add-on fijo. Los cupos y cantidades son metadatos, sin enforcement en S2.
- Consulta interna: acción `appointments_catalog` de billing (`GET /billing/appointments_catalog/`, bajo el prefijo API existente), restringida a usuarios staff; expone el producto inactivo, planes, tiers, add-on y extra directamente desde la fuente canónica.
- Preparación opcional y acotada: [seed_appointments_catalog](../../services/api/src/apps/billing/management/commands/seed_appointments_catalog.py), mediante `python services/api/src/manage.py seed_appointments_catalog`. **No ejecutar contra una DB compartida sin autorización.** Es idempotente, transaccional y solo escribe códigos nuevos de Turnos; no modifica `appointments_base`, otros verticales ni suscripciones.
- El seed prepara tres `Bundle` inactivos, el `Module` de Automatizaciones inactivo y los `Plan` fijos Turnos/Pro con `plan_status=inactive`. No crea un `Module` para el extra cuantitativo ni un `Plan` IA de precio ficticio: `Plan.price` hoy es obligatorio. Si ya existiera un `Plan appointments_ai`, solo deshabilita su venta.
- Pendiente para slices posteriores: modelar la contratación de IA + tier en billing, checkout, add-ons V2, cuotas de profesionales y usage IA. S2 no modifica compatibilidad runtime S1 ni migra legacy.

---

## Estado de implementación — S3 (2026-10-28)

Persistencia comercial V2 preparada, **sin publicar Turnos ni implementar contratación/apply**:

- `billing.SubscriptionV2.usage_tier`: `CharField(max_length=16, null=True, blank=True)`, sin default; reconoce `ai_300`, `ai_1500`, `ai_3000`, `custom`. Nuevas configuraciones IA requieren tier explícito; Turnos/Pro requieren `null`. `clean()` y `save()` validan también cambios parciales. Una configuración IA histórica persistida con tier `null` sigue legible y admite actualizaciones de lifecycle sin asignar un tier por defecto; no habilita IA desde el helper mientras permanezca incompleta.
- Se reutiliza `business.SubscriptionAddon`: `subscription` conserva su nombre y filas legacy; se agrega `subscription_v2`. Ambos son nullable con XOR en DB. La unicidad legacy `(subscription, code)` se conserva y se agrega `(subscription_v2, code)`; incluye filas inactivas, por lo que reactivar/cambiar cantidad reutiliza la misma fila.
- Add-ons Turnos solo admiten propietario V2 de Turnos canónico. `appointments_automations.quantity` admite 0/1; `appointments_extra_professional.quantity` admite enteros no negativos. Se valida antes de la coerción de `IntegerField`, tanto en `save()` como en `full_clean()`. DB agrega el máximo 1 de Automatizaciones y conserva el mínimo 0 del campo positivo.
- [appointments_plans](../../services/api/src/apps/billing/appointments_plans.py) lee cupos, inclusiones y configuración económica desde S2; no duplica precios. [resolve_appointments_subscription_config](../../services/api/src/apps/billing/services/appointments.py) entrega `plan_code`, `usage_tier`, profesionales incluidos/extra/límite efectivo, usuarios secundarios incluidos, Automatizaciones, IA, configuración del tier y add-ons redundantes. El límite es solo `incluidos + extras activos`; no consulta ni bloquea `AppointmentProfessional`.
- IA incluye `appointments.automations` sin fila extra. Una fila activa redundante se informa en `redundant_addons` y con warning, sin sumarle capacidad, calcular cargos ni borrar datos. Base/Pro requieren add-on activo con cantidad 1. Runtime y flags V2 usan la relación nativa, sin puente desde Gestión; el contexto híbrido también conserva ese resultado. Se preserva la normalización S1 de códigos Turnos con `service_type` histórico incorrecto, sin omitir la validación del tier. Un tier desconocido persistido se rechaza en el helper y falla cerrado en runtime.
- `custom` mantiene precio, conversaciones, overage y spend cap `null` provenientes del catálogo, sin valores sustitutos. Reconocer el tier comercial no activa ni configura una recepcionista.
- `PendingSubscriptionChange` agrega `subscription_v2` nullable con `PROTECT` y `target_usage_tier` nullable. `target_plan_code` y `billing_cycle` se reutilizan; `config_snapshot` Turnos tiene forma `{"addons": {"appointments_automations": 0|1}, "quantities": {"appointments_extra_professional": N}}`. Se pueden omitir las secciones sin cambios. `total_amount` es nullable para no inventar un importe, especialmente en custom; los cambios legacy siguen requiriendo importe. No se modifican snapshots históricos. El procesador legacy ignora explícitamente cambios vinculados a V2 antes de consultar pagos; no existe apply V2.
- Las migraciones son expansivas y sin backfill: `billing.0024_appointments_commercial_v2` y `business.0028_subscriptionaddon_v2_owner`. No migran `appointments_base` ni add-ons existentes de otros productos.
- Las validaciones comerciales de tier viven en modelo/service, no en un constraint global, para permitir el `null` histórico. `QuerySet.update()`/`bulk_create()` evitan hooks de Django: no usarlos para nuevas configuraciones comerciales; XOR/unicidad sí están protegidos en DB y runtime rechaza tiers desconocidos. S3 no implementa metering, workers, checkout ni cambios de precio/publicación.

## Estado de implementación — S4 (2026-10-28)

Enforcement de profesionales y acceso propio backend preparados; Turnos sigue sin publicarse:

- `AppointmentProfessional.membership` es nullable y opcional. La Membership debe pertenecer al mismo Business, estar activa y tener rol `professional`; ese rol solo puede usarse con suscripción Turnos Pro/IA vigente. La restricción parcial `unique_active_professional_membership_business` impide compartir una Membership entre profesionales activos del mismo Business; las filas profesionales inactivas conservan vínculos históricos. No se creó un sistema de usuarios paralelo.
- Las altas activas y reactivaciones resuelven el límite mediante `resolve_appointments_subscription_config`: Turnos `2 + appointments_extra_professional.quantity`; Pro e IA `5 + quantity`. Solo cuentan `is_active=True`; un owner que atiende cuenta por su fila activa, sin necesitar vincular su Membership. El guardado bloquea la fila Business con `select_for_update()` dentro de una transacción antes de contar y guardar; si no hay cupo, devuelve error de dominio y no desactiva ni elimina registros. Cambios a inactivo siguen permitidos.
- `count_active_professionals` y `detect_over_limit` exponen conteo y detección de exceso sin mutaciones, para una futura selección de downgrade. La base instalada SQLite no soporta `select_for_update`; la prueba de concurrencia está condicionada a esa capacidad y requiere PostgreSQL para ejecutarse.
- El rol `professional` solo obtiene permisos propios (turnos, agenda y clientes relacionados), aun si hubiera overrides; no recibe permisos globales. Listados, detalle, mutaciones e historial/timeline filtran por profesional vinculado. La disponibilidad limita la consulta a su perfil y horarios/excepciones propios. Los roles globales existentes conservan sus capacidades.
- La Membership profesional sigue contando como usuario secundario cuando consume un seat; `appointments_extra_professional` solo suma cupo de profesionales y nunca altera seats. La cuota y los seats se resuelven separadamente.
- La migración `appointments.0009_appointmentprofessional_membership_and_more` agrega el vínculo y la unicidad parcial; `accounts.0034_alter_membership_role_and_more` agrega el rol en las elecciones de Membership y RolePermissionOverride. Sin backfill.
- Los tests enfocados de cuotas/scopes, CRUD de profesionales/horarios, S3, pricing canónico S2 y runtime S1 pasaron en SQLite: 131 tests, con la prueba concurrente omitida por capacidad de SQLite. En `test_customer_core_access`, los 35 casos compatibles pasaron; 2 flujos de reserva/seed no se pudieron ejecutar en SQLite porque dependen de `regexp_replace` de PostgreSQL. No se certificó concurrencia ni esas rutas con PostgreSQL local.
- S4 no implementa cuotas de `AppointmentProfessional` para otros flujos externos a su save, selección de downgrade, UI Mi Agenda, cambios de plan/aplicación, checkout, payment ni metering IA; no cambia precios ni publica Turnos.

## Estado de implementación — S5 (2026-10-28)

Contratación inicial canónica integrada a billing, todavía **sin publicar Turnos**:

- `billing.services.appointments_checkout.quote_appointments` arma cotizaciones desde `canonical_pricing`; mensual/anual y tiers IA usan los enteros del catálogo. IA no suma Pro ni Automatizaciones, y el extra profesional es cuantitativo. `custom` devuelve `contact_sales / manual_contract_required`.
- Los endpoints `POST /billing/internal/appointments/quote/` y `/billing/internal/appointments/checkout/` requieren usuario staff. El servicio de checkout también requiere el flag interno explícito mientras `products.appointments.is_active = false`; el flujo público no puede comprar Turnos.
- El checkout persiste `AppointmentsCheckout`, metadata y snapshot (líneas, unit prices, cantidades, subtotal, descuento, total, moneda, versión del catálogo y fecha) antes de enviar el monto exacto a un preapproval recurrente de Mercado Pago. No crea ni requiere `Plan appointments_ai`.
- El webhook vuelve a consultar el preapproval/pago con credenciales del servidor, correlaciona por referencias locales, valida importe/moneda contra el snapshot persistido y vincula una `SubscriptionV2` con ciclo/tier. El pago autorizado activa el período y persiste add-ons V2; el extra profesional conserva su cantidad. Automatizaciones IA permanecen incluidas sin fila facturable.
- Reintentos reutilizan el checkout abierto; las referencias de checkout/preapproval/pago y la unicidad parcial por negocio evitan duplicaciones. La aplicación de add-ons es idempotente y no toca `business.Subscription`.
- Alcance limitado a compra inicial y activación: no implementa prorrateo, upgrades, downgrades, renovaciones/lifecycle completo, usage metering, cortesías, migración de `appointments_base` ni publicación.

## Estado de implementación — S6 (2026-10-28)

Lifecycle comercial backend de Turnos implementado sin publicar el producto:

- `billing.services.appointments_lifecycle` centraliza acceso por estado, prorrateo, quotes de cambio, cambios pendientes, renovación idempotente, grace, tier efectivo y policies para nuevas reservas, automatizaciones e IA.
- Upgrade y aumento de tier son inmediatos tras el pago de una preferencia única por la diferencia proporcional del período vigente. El cálculo usa `Decimal`, segundos enteros/microsegundos y redondeo explícito a peso entero; el webhook confirma referencia, importe y moneda antes de aplicar. El `SubscriptionV2`, período pagado, Business, profesionales, turnos e add-ons se conservan.
- Downgrades de plan, tier o capacidad y los cambios mensual/anual se cotizan explícitamente y se programan para el fin del período vigente. La cotización informa ciclo actual/nuevo, monto, fecha efectiva y siguiente renovación. Mercado Pago recibe el monto/frecuencia nuevos con `start_date` en el próximo límite, sin acortar el período pagado.
- Los excesos de profesionales persisten en `PendingSubscriptionChange` como `blocked`, con conteo actual, límite futuro y exceso. No se archivan ni borran perfiles; el owner debe desactivarlos y confirmar la resolución. Una reducción pendiente limita nuevas activaciones para no volver a exceder el límite.
- El pago de renovación bloquea Business, SubscriptionV2 y el cambio pendiente; aplica una sola vez por `provider_authorized_payment_id`, avanza el período y conserva add-ons/cantidades. Un pago válido recupera `past_due`/`suspended`; un fallo inicia tres días de grace; el vencimiento suspende sin borrar ni cancelar turnos históricos. La cancelación sigue usando `cancel_at_period_end` y conserva acceso hasta el límite.
- Los endpoints owner-only son `POST /billing/appointments/lifecycle/quote/`, `/change/` y `/changes/<id>/resolve/`. No agregan UI comercial general. Reserva pública y creación admin consultan la policy central; profesionales activos no pueden crearse/reactivarse en `suspended`. Se exponen policies lifecycle para futuros envíos de Automatizaciones e inicio de IA, sin workers ni metering.
- `billing.0026_appointments_lifecycle` agrega timestamps de grace/suspensión, tier efectivo, idempotency key de renovación y resolución del cambio pendiente. No migra `appointments_base`, otros verticales ni datos históricos.
- S6 no implementa ledger/overage S9, campañas/workers, devolución proporcional ni publicación. El contrato `usage_tier_change_context` permite a S9 evaluar solo overage todavía abierto y declara inmutable el ya cerrado/facturado.
- Riesgos para S7: falta UI del flujo de quote/resolución; verificar en entorno Mercado Pago de prueba los cambios de `auto_recurring` y `start_date` para todas las combinaciones de ciclo; instrumentar alertas/conciliación operativa de cambios `blocked` y fallos de actualización del proveedor. IA `custom` continúa requiriendo contrato manual.

### S6B — Homologación externa bloqueada (2026-10-29)

**Bloqueado por entorno de prueba de Mercado Pago. S6 permanece implementado y validado internamente, pero NO cerrado definitivamente con evidencia real del proveedor.** El sandbox/test-user no permitió reproducir `POST /preapproval` para esta configuración; no demuestra una incompatibilidad general del proveedor.

- Se usó exclusivamente el archivo local `.env.mercadopago.test`, ignorado por Git y no versionado; no se usaron credenciales productivas ni fallback al entorno normal. Seller QA verificado mediante API como `test_user` y `MLA`; buyer QA verificado por ID, nickname y `MLA`, distinto del seller.
- Monto canónico consultado: `appointments monthly = 23000 ARS`. Payload mínimo sin plan: `reason` de QA, `external_reference = MIRUBRO-S6B-QA-<uuid>`, `payer_email` de prueba, `back_url = https://example.com/mirubro-turnos-qa/return` y `auto_recurring = {"frequency": 1, "frequency_type": "months", "transaction_amount": 23000, "currency_id": "ARS"}`. Los intentos mínimos omitieron `metadata`, `status`, `preapproval_plan_id` y `card_token_id`.
- Se realizaron intentos controlados y autorizados con emails QA: `mirubro.turnos.qa@testuser.com`, `test_payer_<número>@testuser.com`, `test@testuser.com` y `testuser<buyer_id>@testuser.com`. El error final fue HTTP 400, `{"message": "User bad request", "status": 400}`. El email genérico `test@testuser.com` devolvió previamente HTTP 400, `guest_site_mismatch`, `Payer is associated with a different site`.
- `GET /users/{buyer_id}` no expuso `email`. El único intento de `POST /users/test` con caller test devolvió HTTP 403, código `40311`, `authorization: the caller.id must be a productive user`; no se introdujeron credenciales productivas para sortearlo.
- No se obtuvo preapproval ID ni `init_point`. No se ejecutaron upgrades, downgrades, cambios de ciclo, cancelaciones ni cobros reales. No se modificó código funcional por este bloqueo y no se harán más llamadas mutativas en este cierre.

La homologación final deberá ejecutarse más adelante en un entorno de proveedor soportado/controlado. Quedan pendientes exclusivamente: creación/autorización real de `preapproval`, modificación de `transaction_amount`, frecuencia mensual/anual, comportamiento de `next_payment_date` y preservación del período, downgrade en renovación, `cancel_at_period_end`, rechazo de cobro e idempotencia real del proveedor. En ese cierre no se avanzó a S7; S7A se implementa por separado abajo, sin cerrar la homologación externa pendiente.

## Estado de implementación — S7A (2026-10-29)

Entitlement efectivo de Automatizaciones consolidado, sin implementar S7B:

- Helper canónico: [can_use_appointments_automations](../../services/api/src/apps/billing/services/appointments.py), con `business` y parámetro opcional `at` para evaluar límites temporales. Selecciona la suscripción efectiva mediante `resolve_subscription(..., service_type='appointments')`, usa `resolve_appointments_subscription_config` de S3 para la configuración comercial actual y `subscription_lifecycle_access` de S6 para el acceso temporal. No consulta intenciones de `PendingSubscriptionChange`.
- `appointments` y `appointments_pro` requieren add-on V2 activo con cantidad 1. `appointments_ai` incluye Automatizaciones sin fila adicional para `ai_300`, `ai_1500`, `ai_3000` y `custom`; conserva también la inclusión S3 de filas IA históricas con tier `null`. Una fila redundante no suma entitlement, no cambia el resultado ni modifica datos o cargos.
- `active` y `past_due` dentro de los tres días de grace conservan el entitlement comercial. Grace vencido, `suspended`, `canceled`, `checkout_pending`, `trialing` y estados desconocidos no habilitan Automatizaciones. La cancelación programada conserva acceso hasta antes del fin del período; una cancelación sin fecha final es ambigua y falla cerrada.
- Un downgrade pendiente, incluso vencido pero no aplicado, no cambia el acceso. El helper refleja un downgrade/upgrade solo cuando S6 persiste la nueva configuración; vuelve a resolver normalmente tras una reactivación.
- `appointments_base` solo conserva Automatizaciones si el resolver existente las reconoce explícitamente. Hoy no reconoce ese add-on para legacy ni para V2 base: S7A no agrega soporte, aliases, venta ni migraciones. Los códigos Turnos desconocidos/compuestos y las filas con `service_type` incorrecto fallan cerrados en este gate; se preserva el resolver comercial histórico S1/S3 sin ampliarlo.
- `has_entitlement(..., 'appointments.automations')`, los flags efectivos de suscripción y contexto de negocio, y el helper de compatibilidad `can_send_appointments_automation` delegan al mismo gate. Los entitlements declarativos de plan/configuración S3 siguen describiendo inclusiones comerciales, no reemplazan el gate efectivo de S7A.
- Tests focalizados: [test_appointments_automations_s7a](../../services/api/src/apps/billing/tests/test_appointments_automations_s7a.py). Usar PostgreSQL aislado para validar este dominio y sus constraints existentes.
- Validación local en PostgreSQL 16 aislado: 37/37 tests S7A y 99/101 regresiones S3/S6/runtime aprobados; `manage.py check` sin issues y `makemigrations --check --dry-run` sin cambios. La regresión completa no queda verde: dos tests S3 existentes fallan sin invocar el gate S7A. `test_pending_v2_cannot_enter_legacy_payment_apply` conserva una expectativa previa al soporte S6; `test_expansive_migrations_preserve_legacy_rows` consulta el modelo actual sobre un esquema anterior a `billing.0026` y falla por `grace_started_at`. No se modificaron esos tests ni sus flujos fuera de alcance.
- Sin cambios a pricing, checkout, Mercado Pago, profesionales/seats, usage metering IA, estados de lifecycle, Celery, jobs, envíos ni canales externos. **No se avanza a S7B.**

## Estado de implementación — S7B (2026-10-29)

Gate real del outbound automático existente, sin cambiar la semántica S7A:

- Outbound encontrado: `appointment_reminder` (previo al turno) y `no_show_followup` (seguimiento de inasistencia). Ambos parten de [reminder_deliveries](../../services/api/src/apps/customers/reminder_deliveries.py) y usan [deliveries](../../services/api/src/apps/customers/deliveries.py). No existen otros envíos automáticos al cliente en el módulo de Turnos: las confirmaciones de pago y avisos operativos son `BusinessNotification` internas.
- Gate pre-enqueue: `prepare_customer_delivery` consulta `can_use_appointments_automations(business)` para ambos propósitos, incluso si se invoca sin pasar por el productor de recordatorios. Un resultado falso crea un delivery `skipped`, con `skip_reason=appointments_automations_unavailable` y `skipped_at`; no encola la task. El dispatch y la recuperación existentes pasan por esta preparación.
- Gate runtime: `_claim`, con el delivery bloqueado, vuelve a resolver S7A con el negocio actual antes de inicializar el proveedor, reclamar el intento o ejecutar `provider.send`. Aplica tanto a `customers.execute_delivery` como al barrido `customers.retry_due_deliveries` y al comando operativo que llama al mismo servicio. Un job encolado antes de suspensión/downgrade no conserva acceso por su snapshot.
- Sin acceso en runtime: `skipped`, sin `sent_at` ni `provider_message_id`, sin nuevo intento y con `next_retry_at` eliminado; se usa el log de auditoría existente. Los avisos internos y `CustomerReminder.notified_at` conservan su semántica.
- Idempotencia conservada: misma key devuelve el mismo delivery; `sent`/`processing`/`skipped` no se reenvían. La reactivación permite nuevos eventos elegibles, pero no revive eventos finales omitidos ni duplica envíos.
- Manuales separados: los recordatorios manuales siguen internos; mensajes humanos y propuestas de recepción usan `LeadStaffMessage` y no se someten al gate de Automatizaciones, aunque su transporte tenga tasks y retries.
- Tests nuevos: [test_appointments_outbound_s7b](../../services/api/src/apps/customers/test_appointments_outbound_s7b.py), con proveedores mockeados. Los fixtures de regresión de deliveries/SES/recordatorios externos ahora declaran acceso IA real para continuar probando consentimiento, lifecycle e idempotencia bajo S7B; no se amplió el fixture legacy compartido.
- Validación final con PostgreSQL 16 aislado y broker/cache en memoria: **481/481 tests aprobados**, incluidos 16 S7B, 37 S7A, S6/lifecycle, runtime, deliveries (incluida concurrencia), SES mockeado, dispatch/recuperación, automatizaciones internas, notificaciones y mensajes/propuestas manuales. `manage.py check` sin issues y `makemigrations --check --dry-run` sin cambios. No quedan fallos en este alcance; no se ejecutó homologación externa ni se hicieron envíos reales.
- Sin cambios a copy/templates, horarios, scheduling, proveedores/canales, pricing, checkout, Mercado Pago, billing/lifecycle, profesionales/seats ni metering IA. Sin migraciones. **No se avanza a S7C.**

## Estado de implementación — S7C (2026-10-29)

Integración del lifecycle efectivo de Automatizaciones validada sin agregar reglas de billing ni modificar código productivo:

- [test_appointments_lifecycle_s7c](../../services/api/src/apps/customers/test_appointments_lifecycle_s7c.py) agrega 29 tests de integración sobre PostgreSQL real, reloj controlado y proveedor mockeado. Usa el resolver/configuración S3, las transiciones S6, el helper S7A y la preparación/worker S7B reales. Verifica `appointment_reminder` y `no_show_followup`, tanto pre-enqueue como runtime.
- `active` con inclusión IA o add-on efectivo permite enviar; Pro sin add-on no. Un fallo de pago conserva acceso durante tres días de grace: el último microsegundo anterior y el instante exacto de `grace_until` permiten enviar; `grace_until + 1 microsegundo` bloquea incluso antes del job de suspensión. Un segundo fallo no extiende grace.
- `cancel_at_period_end` conserva acceso hasta `current_period_end - 1 microsegundo`; bloquea en el instante exacto y después, aun con grace vigente y sin esperar una transición de estado.
- La renovación idempotente recupera acceso durante grace, tras grace vencido y desde `suspended`, limpia los timestamps de grace/suspensión y no concede un entitlement comercial ausente.
- AI → Pro sin add-on conserva acceso mientras el downgrade está pendiente, incluso en la fecha efectiva si todavía no se aplicó. La renovación S6 aplica el cambio y bloquea; AI → Pro con Automatizaciones conserva acceso después de aplicarse. Pro → AI y agregar el add-on por upgrade habilitan inmediatamente después de aplicar el cambio, no durante el pago pendiente.
- Remover el add-on con efecto futuro conserva acceso hasta aplicar el cambio en la renovación. La fila del add-on se conserva, desactivada; Automatizaciones no interpreta fechas de cambios pendientes.
- Los jobs encolados antes de suspensión, grace vencido, cancelación, downgrade o remoción del add-on vuelven a resolver el estado actual al ejecutar: quedan `skipped` con `appointments_automations_unavailable`, sin inicializar proveedor ni consumir un nuevo intento. Un pendiente no ejecutado o un retry elegible puede enviar tras reactivación; los deliveries `sent`, `skipped` y fallos no reintentables no reviven ni se duplican.
- Se verifica que perder acceso no borra ni modifica deliveries históricos, turnos pasados/futuros, notas, recordatorios internos, consentimiento ni configuraciones del negocio. Solo se bloquea outbound automático nuevo/elegible.
- Validación: **29/29 S7C aprobados** y corrida conjunta final **105/105** (29 S7C, 16 S7B, 37 S7A, 23 S6). La corrida ampliada ejecutó **461 tests: 447 aprobados y 14 errores preexistentes** en `billing.tests.test_cancellation.CancellationViewTest`, reproducidos ejecutando esa clase aislada sin S7C. Su fixture crea el admin antes de la suscripción y falla en el guard de seats; no se modifica por estar fuera de alcance. S7A, S7B, S6/lifecycle, runtime, enforcement, servicios/tasks de cancelación, deliveries (incluida concurrencia), SES mockeado, dispatch, recuperación y automatizaciones internas aprobaron. `manage.py check` sin issues y `makemigrations --check --dry-run` sin cambios. PostgreSQL 16 exclusivo de esta validación, broker/cache en memoria y sin envíos externos.
- Sin cambios a pricing, checkout, Mercado Pago, estados, profesionales/seats, metering IA, mensajes ni copy/templates. Sin migraciones ni refactor. **No se avanza a S7D.**

## Estado de implementación — S7D (2026-10-29)

Hardening de idempotencia, retries y concurrencia del outbound existente. **S7A–S7D quedan cerrados; no se avanza a S8.**

- Se conservan el claim corto `select_for_update(skip_locked=True, of=('self',))`, el estado `processing` y `attempt_count` como token de la escritura final. Dos workers sobre un pendiente o retry elegible producen un solo claim, un solo nuevo intento y una sola llamada al proveedor.
- [deliveries](../../services/api/src/apps/customers/deliveries.py) exige ahora `transaction.atomic(durable=True)` en el claim: el intento debe quedar confirmado antes de llamar al proveedor. Ejecutar dentro de una transacción externa genera `RuntimeError` antes de reclamar o enviar; el caller debe ejecutar fuera de ella o encolar con `on_commit`. Evita que un rollback externo deshaga un intento que ya llegó al proveedor.
- Protección mínima adicional, sin migración: un candidato `pending`/retriable que conserva `sent_at` o `provider_message_id` no vuelve a enviarse. Queda `failed` terminal con `prior_send_evidence`, sin próximo retry ni incremento de intentos; conserva la evidencia previa y usa el logging existente.
- Se reutiliza el constraint `customer_delivery_unique_idempotency_key` sobre `(business, idempotency_key)` y la key estable por turno/recordatorio/canal. La carrera real de preparación se prueba para recordatorio previo y seguimiento de inasistencia: una fila y un solo enqueue. No se agregan constraints ni infraestructura.
- Un rechazo conocido y reintentable puede volver a intentar sobre la misma fila, respetando backoff y máximo de intentos. Cada claim elegible vuelve a consultar `can_use_appointments_automations(business)` con datos actuales, antes de inicializar proveedor o consumir intento. Si perdió acceso queda `skipped`, con motivo y timestamp, sin llamada al proveedor. Reactivar permite ejecutar únicamente pendientes/retries todavía elegibles: no revive `sent`, `skipped` ni fallos terminales.
- Recovery de pendientes con enqueue perdido pasa por el mismo claim/gate. Recovery de recordatorios sin delivery vuelve a la preparación idempotente y su posterior ejecución revalida entitlement. Un `processing` vencido sigue siendo `failed/outcome_unknown` **sin retry**, incluso si el negocio se reactiva. Un resultado tardío del worker no puede sobrescribir ese terminal. No se borran históricos.
- Se conserva la estrategia segura ante timeout ambiguo y fallo de persistencia posterior a la aceptación: excepción del proveedor → `provider_exception` terminal; aceptación sin resultado persistido → permanece `processing` hasta recovery `outcome_unknown`, nunca reenvío ciego. **El proveedor SES actual no utiliza una idempotency key remota real**: la key local y los tags solo identifican/correlacionan, no deduplican en SES. Los retries internos de botocore siguen desactivados (`total_max_attempts=1`). Esta política evita duplicados ante resultado desconocido a costa de que un envío pueda no ocurrir o no quedar confirmado localmente; no promete entrega exactamente una vez.
- [test_appointments_idempotency_s7d](../../services/api/src/apps/customers/test_appointments_idempotency_s7d.py): **22/22 tests nuevos aprobados**, con PostgreSQL 16 exclusivo, proveedores mockeados, conexiones independientes y carreras sincronizadas. Antes del cambio reprodujeron el reenvío con evidencia previa y la ausencia del guard de transacción externa.
- Validación final: **405/405 aprobados** (22 S7D, 29 S7C, 16 S7B, 37 S7A, 23 S6 y 278 regresiones de deliveries, SES, dispatch/recovery, automatizaciones internas, runtime y lifecycle/retries/concurrencia de webhooks). Broker/cache en memoria y sin envíos externos. `manage.py check` sin issues; `makemigrations --check --dry-run` sin cambios.
- La corrida ampliada original fue **405 aprobados + 1 error externo**: `billing.tests.test_webhook_delivery_lifecycle.Migration0023HistoricReceivedTests.test_historic_received_classification`. Usa el modelo actual de `PendingSubscriptionChange` al retroceder a un esquema anterior sin `subscription_v2_id`. Se reprodujo el mismo error ejecutando únicamente ese test con el código de deliveries capturado **antes de S7D**, sin los tests nuevos. Se excluyó únicamente ese caso de la corrida final verde; no se modificaron billing ni sus migraciones.
- Sin cambios a lifecycle S6, canales, templates/copy, pricing, checkout, Mercado Pago, profesionales/seats ni metering IA. Sin sistema de auditoría nuevo, refactor amplio ni implementación de S8.

---

## Estado de implementación — S8A (2026-10-29)

Modelo canónico interno de usage metering para `appointments_ai`, sin enforcement ni facturación:

- [AppointmentAIUsageSession](../../services/api/src/apps/appointments/models.py) conserva business, suscripción V2, identidad canónica `external_conversation_id`, UUID de la interacción de apertura, inicio/vencimiento, límites del usage month y tier vigente al abrir. No duplica mensajes, tokens ni contenido; no crea un registro por request. Migración expansiva [appointments.0010](../../services/api/src/apps/appointments/migrations/0010_ai_usage_session.py), sin backfill ni cambios a tablas de otros dominios. Suscripción y business quedan protegidos contra borrados que eliminarían evidencia comercial.
- [ai_usage](../../services/api/src/apps/appointments/services/ai_usage.py) es la única API interna: `resolve_appointments_ai_usage_period`, `get_or_create_ai_usage_session`, `count_ai_sessions_for_usage_period`, `resolve_ai_usage_limit` y `get_appointments_ai_usage`. El resumen devuelve `usage_tier`, `period_start`, `period_end`, `used`, `included`, `remaining`; `remaining` se limita a cero, pero no impide registrar otra sesión.
- La primera participación real de IA en respuesta a una interacción válida de cliente abre `[started_at, started_at + 24h)`. Dentro de esa ventana no aumenta el contador ni se desplaza el vencimiento; **exactamente en +24h empieza otra sesión**. Toda fecha se normaliza a UTC; no intervienen medianoches, fechas locales ni inactividad.
- El contexto se verifica contra `LeadAgentState` del business/canal activo. Varios episodios Lead de la misma conversación comparten sesión; otro business u otra conversación no. Un contexto ausente, ajeno o ambiguo se rechaza explícitamente.
- El usage month sigue `SubscriptionV2.current_period_start/current_period_end` de S6, no el día 1. Para anual se forman subperíodos mensuales usando la aritmética de `appointments_period_end` de S6; se conserva el día/hora del ancla, ajustando el día al último válido en meses cortos sin arrastrar ese recorte al siguiente mes. En grace S6, el siguiente usage month empieza en el boundary de renovación. Un ancla incompleta/inválida no se adivina; no se hace backfill comercial anterior al ciclo actual.
- Una sesión pertenece al período donde **empezó**. Cruzar renovación, incluso con apply S6 en el medio, no la divide ni crea otra. La interacción posterior a vencer su ventana abre sesión en su nuevo período.
- Cuotas leídas del catálogo S2 mediante configuración S3: `ai_300` = 300, `ai_1500` = 1500, `ai_3000` = 3000. No hay planes nuevos. `custom` lanza `ManualContractRequired`: requiere resolución comercial manual y no se le inventa cuota ni se registran sesiones.
- El resumen usa el tier efectivo persistido, no el target pendiente: upgrade aplicado cambia inmediatamente el cupo del período; downgrade programado mantiene el actual y renewal/apply S6 usa el nuevo. Los snapshots e historial nunca se recalculan ni borran por downgrade/cancelación.
- Concurrencia: transacción + `SELECT FOR UPDATE` de Business y luego SubscriptionV2, igual al orden S6; el lock existe aun antes de la primera sesión. DB impone unicidad de apertura por business/evento y por business/conversación/inicio, duración exacta de 24h, inclusión del inicio en el período y tiers resueltos.
- Contrato de retry: conservar **UUID y timestamp original inmutables de la interacción**, nunca usar hora de recepción. Una apertura repetida recupera su fila; una interacción interna repetida recupera la ventana histórica que contiene su timestamp. Reusar UUID de apertura con otra identidad/fecha se rechaza. Una interacción fuera de orden que solaparía una sesión ya registrada queda explícitamente unresolved, sin modificar historia.
- Fail closed mediante resolver S3 + acceso lifecycle S6, sin fallback legacy ni a otro plan: sin IA efectiva, tier inválido/null, business suspendido, suscripción suspendida/grace vencida/cancelación efectiva o contexto inseguro no se registra consumo.
- **Alcance de integración confirmado:** este repo no contiene la invocación del LLM del agente externo. `lead.sync`, `sender=bot` y los mensajes replicados no prueban uso IA (pueden ser respuestas determinísticas). No se conectan automáticamente al contador. El futuro caller interno deberá invocar el servicio **solo después de confirmar participación real de IA**, excluyendo manuales, automatizaciones S7, notificaciones, errores/rechazos previos a IA, health checks y previews/tests internos. S8A no cambia el protocolo del agente ni bloquea su ejecución.
- Validación: **104/104 aprobados**, exit code 0, sobre PostgreSQL **16.15** en contenedor aislado y puerto local efímero: 41 nuevos S8A (incluyen 3 pruebas reales de concurrencia), 23 S6, 30 runtime resolver y 10 casos S3 de tier/configuración/fail closed. Tiempos explícitos, sin `sleep`. `manage.py check` sin issues; `makemigrations --check --dry-run` sin cambios; sintaxis Python compilada correctamente.
- La corrida ampliada de 125 tests tuvo **123 aprobados, 1 fallo y 1 error fuera del alcance S8A**: `AppointmentsCommercialV2Tests.test_pending_v2_cannot_enter_legacy_payment_apply` espera `billing_v2_change_not_supported`, pero el flujo actual devuelve `billing_ref_mismatch`; `AppointmentsCommercialMigrationTests.test_expansive_migrations_preserve_legacy_rows` retrocede a billing.0025 y usa el modelo actual que requiere `grace_started_at` agregado en S6/billing.0026. No se modificaron esos tests ni los módulos involucrados; la selección final verde de S3 cubre específicamente el resolver/configuración relevante, no afirma que la suite ampliada esté completamente verde.
- No se implementan overage monetario, hard cap, bloqueo por cuota, billing por consumo, UI, analytics/dashboard ni S8B. Sin cambios a pricing, checkout, Mercado Pago, S7, profesionales o seats.

## Estado de implementación — S8B (2026-10-29)

Policy canónica de consumo y admisión para `appointments_ai`, sin cobro real:

- [ai_usage](../../services/api/src/apps/appointments/services/ai_usage.py) agrega `resolve_ai_usage_policy(business, at=...)` y `can_start_ai_usage_session(business, at=...)`. Ambos usan el resolver S3, lifecycle S6, usage month y contador S8A. El resumen S8A de seis campos no cambia; la policy es un resumen separado con `usage_tier`, `included_sessions`, `used_sessions`, `overage_sessions`, `overage_unit_price`, `overage_amount`, `hard_cap_amount`, `max_overage_sessions`, `max_total_sessions`, `can_start_new_session`, `blocked_reason`.
- Términos del catálogo canónico S2, en **ARS enteros**, sin floats:

  | Tier | Incluidas | ARS/sesión extra | Hard cap ARS/usage month | Máximo de extras | Máximo total |
  |---|---:|---:|---:|---:|---:|
  | `ai_300` | 300 | 300 | 75.000 | 250 | 550 |
  | `ai_1500` | 1.500 | 200 | 137.500 | 687 | 2.187 |
  | `ai_3000` | 3.000 | 160 | 192.500 | 1.203 | 4.203 |

- `overage_sessions = max(0, used_sessions - included_sessions)`; `overage_amount = overage_sessions * overage_unit_price`. El resumen deriva el consumo del período usando el tier efectivo actual; no es una liquidación, cargo, deuda ni recálculo de filas históricas.
- `max_overage_sessions = hard_cap_amount // overage_unit_price`; `max_total_sessions = included_sessions + max_overage_sessions`. Se permite abrir una sesión **si y solo si** `used_sessions < max_total_sessions`, además de cumplir acceso/configuración. Con `used < included`, la próxima sesión está incluida; con `used == included`, la próxima es la primera extra. La sesión que deja el consumo exactamente en el máximo técnico se permite; la siguiente se bloquea, aunque quede un remanente monetario insuficiente para pagar otra sesión. En `ai_1500` el máximo monetario alcanzable es ARS 137.400; en `ai_3000`, ARS 192.480.
- `get_or_create_ai_usage_session` aplica la autorización solo cuando realmente necesita crear una sesión. Recuperar una apertura por UUID o reutilizar una ventana `[inicio, inicio + 24h)` no evalúa el cap, no aumenta consumo ni desplaza vencimiento. Exactamente al vencer las 24h se necesita autorización nueva. Esto también vale para una ventana que cruza al siguiente usage month.
- La policy devuelve `can_start_new_session=False` y `blocked_reason='hard_cap_reached'` si el próximo cupo excede el máximo; intentar crearlo lanza `AIUsageHardCapReached` (subclase de `AIUsageUnavailable`). Los rechazos de lifecycle/configuración conservan las excepciones explícitas de S8A: sin IA efectiva, suspended, grace vencida, tier inválido/null o configuración incompleta → `AIUsageUnavailable`; `custom` → `ManualContractRequired`. No se inventan cuota, precio o cap manuales. Grace vigente y cancelación al cierre vigente permiten según cap hasta su boundary S6; no lo evaden.
- Upgrade aplicado usa inmediatamente cuota/precio/cap nuevos y conserva las sesiones del mismo usage month. Downgrade pendiente no cambia la policy; al aplicarse usa los nuevos términos sin borrar historial. Si el consumo previo supera el nuevo máximo, no admite nuevas sesiones, pero una ventana ya abierta sigue reutilizable respecto del cap. El lifecycle sigue siendo el gate de acceso S6 existente.
- Concurrencia PostgreSQL: la decisión, el conteo y el insert permanecen dentro de la misma transacción de creación, con `SELECT FOR UPDATE` de Business y luego SubscriptionV2, en el orden existente S8A/S6. Dos conversaciones distintas compitiendo por el último cupo no pueden superar el límite. La preautorización aislada **no reserva** capacidad; la creación siempre reevalúa bajo lock. No usar `can_start_ai_usage_session` para bloquear mensajes de una ventana abierta ni separar la decisión del insert.
- Solo defaults del catálogo: no existe infraestructura específica de override de cap; el override de precio de suscripción no se reutiliza para este fin. Sin nuevas tablas ni migraciones, UI o configuración custom.
- [Tests S8B](../../services/api/src/apps/appointments/tests/test_ai_usage_s8b.py) cubren límites de los tres tiers, remanentes, ventana activa/vencida, cambios de tier, lifecycle, fail closed, resumen exacto, ausencia de escrituras contables y carrera real por el último cupo en PostgreSQL.
- Validación: **134/134 aprobados**, exit code 0, sin skips: 30 S8B, 41 S8A, 23 S6/lifecycle, 30 runtime resolver y los mismos 10 S3 relevantes seleccionados en S8A. Incluye la nueva carrera por el último cupo y las tres carreras S8A. PostgreSQL **16.15** en contenedor aislado, puerto local efímero; Python local con Django **5.2.17** (la imagen API existente con Django 5.0.14 no carga los constraints S8A). `manage.py check` sin issues, `makemigrations --check --dry-run` sin cambios y sintaxis Python correcta en los dos módulos S8. No se modificaron dependencias.
- **Sin cobro automático, cargos, invoices, deuda, cambios de subscription amount, Mercado Pago ni integración del agente externo.** No cambia la definición de sesión, el cálculo de usage period, S7, pricing base, profesionales/seats ni UI. No implementa S8C.

## Estado de implementación — S8C (2026-10-29)

Ledger económico canónico de sesiones IA, sin cobro:

- [AppointmentAIUsageCharge](../../services/api/src/apps/appointments/models.py) registra una fila por sesión **nueva efectivamente creada** por la API interna S8A. Guarda business, SubscriptionV2, sesión, usage period de inicio, tier, ordinal de consumo, allowance snapshot, clasificación, precio unitario, importe, moneda ARS y fecha de registro. No guarda contenido de conversación. [Migración 0011](../../services/api/src/apps/appointments/migrations/0011_ai_usage_charge.py): una sola tabla, índice por business/período, FK protegidas, unicidad PostgreSQL de session mediante OneToOne y checks de período, tier, moneda y clasificación/importes.
- La creación de sesión y ledger comparte la transacción y los locks Business → SubscriptionV2 existentes. Consume una única resolución de policy S8B antes del insert: `used_sessions < included_sessions` → `included`, precio e importe 0; en otro caso → `overage`, precio e importe iguales al precio vigente. `session_ordinal = used_sessions + 1`; el contador de sesiones S8A, **no el ledger**, sigue siendo la fuente de consumo/admisión. El hard cap no cambia.
- Snapshots en ARS enteros, sin floats: extras `ai_300` = 300, `ai_1500` = 200, `ai_3000` = 160. Los cambios de tier/precio no actualizan filas anteriores. Upgrade aplicado usa la nueva cuota/precio para las sesiones siguientes; downgrade pendiente conserva policy actual y downgrade aplicado usa los nuevos términos, sin reclasificar historia.
- Reutilización de ventana de 24h y retry devuelven antes de escribir ledger. La unicidad por sesión protege también frente a duplicados directos en DB. Un error al persistir ledger revierte la sesión; no hay éxito parcial. Preautorización, contexto inválido, cap agotado y `custom` no crean filas económicas. No hay hook nuevo en sync, preview/test ni agente externo: se conserva la obligación del caller S8A de acreditar participación real de IA.
- [resolve_ai_overage_statement](../../services/api/src/apps/appointments/services/ai_usage.py) resume **evidencia histórica**, sin resolver la suscripción actual ni recalcular con precios actuales: `total_sessions` cuenta filas registradas; `included_sessions` cuenta filas clasificadas incluidas (no es el allowance actual); `overage_sessions` e `overage_amount` cuentan/suman únicamente filas overage. El allowance que justificó cada clasificación está en `included_sessions_snapshot`. Devuelve fechas, moneda y `usage_tiers`; `usage_tier` es el único tier registrado, o `null` si hay varios o no hay filas. Un período vacío devuelve contadores e importes enteros 0, sin inventar términos.
- Cierre **conceptual derivado**, sin tabla ni mutación: antes del fin → `open`, `settlement_ready_amount=0`; desde el fin exacto → `eligible_for_settlement`, `settlement_ready_amount=overage_amount`. Las filas del período comparten esa elegibilidad por sus límites persistidos. No existe acción ni marca de liquidado/pagado; consultar el statement no reserva ni consume importes. La futura liquidación deberá implementar su propia idempotencia antes de cobrar.
- Una ventana que cruza usage month conserva una sola fila en el período donde comenzó. Los statements se aíslan por business y límites exactos y verifican correspondencia sesión/suscripción/tier/período. Sesiones sin ledger (incluidas las anteriores a S8C) producen `AIUsageUnavailable`: no se hace backfill ni se presenta un importe incompleto como liquidable. Tampoco se fabrica un cero para evidencia inconsistente.
- [Tests S8C](../../services/api/src/apps/appointments/tests/test_ai_usage_s8c.py) cubren snapshots de los tres tiers, clasificación exacta, suma histórica, retries/reutilización, cap, atomicidad, constraints, upgrade/downgrade, cruce mensual, cierre, aislamiento, evidencia incompleta/inconsistente y carreras PostgreSQL con conexiones independientes.
- Validación: **168/168 aprobados**, exit code 0, sin skips: 34 S8C, 30 S8B, 41 S8A, 23 S6/lifecycle, 30 runtime resolver y 10 S3 relevantes. Incluye 8 carreras reales PostgreSQL (4 S8C, 3 S8A, 1 S8B). PostgreSQL **16.15** en contenedor exclusivo, puerto local efímero; Django **5.2.17**. Migración aplicada y constraint UNIQUE de session verificado en `pg_constraint`; `manage.py check` sin issues, `makemigrations --check --dry-run` sin cambios y sintaxis Pylance correcta en modelo, servicio, migración y tests S8C. Sin cambios de dependencias ni migración de la base del entorno habitual.
- **Sin cobro real, Mercado Pago, invoices, deuda, cambios de subscription amount, UI, integración de agente externo ni S8D.** La policy S8B y el resumen S8A mantienen sus contratos; únicamente se conecta el snapshot económico al insert efectivo.

---

## Estado de implementación — S8D (2026-10-29)

Cierre interno inmutable de usage periods terminados de `appointments_ai`, **sin cobro**:

- [AppointmentAIUsageSettlement](../../services/api/src/apps/appointments/models.py) conserva business, SubscriptionV2, límites exactos del usage period, moneda ARS, total de sesiones, sesiones incluidas, sesiones extra, importe entero, snapshot de términos por charge, estado `pending`/`finalized`, fecha de creación y `finalized_at`. El UUID es la referencia estable; `(business, subscription, usage_period_start, usage_period_end)` es la clave lógica idempotente con constraint UNIQUE PostgreSQL. No existe estado `charged` ni estados de pago.
- `included_sessions_snapshot` del settlement copia `included_sessions` del statement: **cantidad histórica clasificada incluida**, no el allowance actual del plan. `terms_snapshot` conserva además, por charge/session ID, tier, ordinal, allowance que justificó la clasificación, clasificación, precio unitario, importe y moneda. Se preservan múltiples tiers y precios históricos sin reinterpretarlos con el catálogo actual.
- [finalize_ai_usage_settlement](../../services/api/src/apps/appointments/services/ai_usage_settlement.py) requiere business y subscription explícitos, límites históricos y `at` timezone-aware. Solo finaliza con `at >= period_end`, período positivo y statement completo/elegible. Antes del límite rechaza sin crear siquiera un pending. Sesiones sin ledger, evidencia inconsistente, otra suscripción en la evidencia del período o charges reservadas por otro settlement fallan cerrado con `AIUsageUnavailable`; no hay backfill ni montos sustitutos.
- Un período sin overage también se finaliza por cero. Si no tiene sesiones, se exige que el ancla persistida pruebe sus límites; no se inventan períodos vacíos históricos cuyo ancla ya se perdió. No se consulta el tier/precio/acceso actual para cerrar. Cancelación, suspensión, inactividad del business, upgrade/downgrade y cambio posterior a un plan no IA no bloquean evidencia histórica válida. Con filas, sus límites persistidos permiten cerrar aunque el ancla actual ya haya avanzado.
- La finalización copia los totales exactos del statement y los términos del ledger en una transacción. Un retry de un settlement `finalized` devuelve su misma fila **sin recalcular el statement ni consultar precios actuales**. Un pending existente se reconstruye desde evidencia completa y se finaliza atómicamente. No cambia `SubscriptionV2.amount` ni escribe importes económicos del ledger.
- `AppointmentAIUsageSettlementEntry` relaciona explícitamente cada charge con su settlement: FK `PROTECT` y **OneToOne de charge**, sin poder asignarla a dos liquidaciones. PostgreSQL verifica coincidencia de business/subscription/período y rechaza reasignaciones; al finalizar verifica que la cantidad de sesiones y los totales coincidan con las relaciones persistidas.
- [Migración 0012](../../services/api/src/apps/appointments/migrations/0012_ai_usage_settlement.py) crea únicamente las dos tablas internas, relaciones, constraints y triggers de protección. PostgreSQL impide actualizar/borrar un settlement finalizado, alterar su membresía o su evidencia económica/sesiones y agregar nuevas filas al período cerrado. Una interacción histórica nueva posterior al cierre produce un error explícito, no una sesión silenciosamente sin liquidar. El siguiente período sigue admitiendo sesiones normalmente.
- Concurrencia: lock transaccional Business → SubscriptionV2, igual al orden S8A/S6, más unicidad en DB. Los triggers de evidencia/membresía también serializan por Business. Dos closers reutilizan un único settlement; un writer concurrente queda incluido antes del cierre o se rechaza después, sin ventana de subliquidación.
- `resolve_ai_overage_statement` conserva su contrato de lectura/calculado y sus estados `open`/`eligible_for_settlement`: no consulta settlements ni requiere que exista uno. El settlement es la persistencia congelada separada.
- **Sin cron/task nuevo:** entry point interno/manual, con período histórico explícito:

  ```python
  from apps.appointments.services.ai_usage_settlement import finalize_ai_usage_settlement

  settlement = finalize_ai_usage_settlement(
      business=business,
      subscription=subscription,
      period_start=recorded_period_start,
      period_end=recorded_period_end,
      at=closure_time,
  )
  ```

  Las fechas deben ser aware; no derivar un período histórico de la hora de ejecución. Para anual se llama por cada usage month independiente, no por el año completo. Una futura task solo podrá descubrir candidatos e invocar este servicio idempotente, sin cobro.
- [Tests S8D](../../services/api/src/apps/appointments/tests/test_ai_usage_s8d.py): **39 nuevos** cubren boundary exacto, ceros, los tres tiers, términos mixtos, ausencia de repricing, freeze, idempotencia, recuperación de pending, aislamiento, lifecycle posterior, evidencia incompleta, enteros ARS, ancla no calendario, subperíodos anuales, rollback y protecciones PostgreSQL.
- Validación final: **207/207 aprobados**, sin skips: 39 S8D, 34 S8C, 30 S8B, 41 S8A, 23 S6/lifecycle, 30 runtime resolver y 10 S3 relevantes. Incluye **10 carreras PostgreSQL** con conexiones independientes (2 S8D, 4 S8C, 1 S8B, 3 S8A). PostgreSQL **16.15** exclusivo en localhost, Django **5.2.17**, broker/cache/email en memoria, sin usar la base habitual ni integrar agente externo. `manage.py check` sin issues; `makemigrations --check --dry-run` sin cambios; migración 0012 aplicada, revertida y reaplicada correctamente.
- La corrida ampliada anterior de 194 tests reprodujo **192 aprobados y los mismos 2 problemas S3 preexistentes documentados en S8A**: categoría legacy `billing_ref_mismatch` frente a `billing_v2_change_not_supported`, y test de migración que consulta `grace_started_at` tras retroceder a billing.0025. No se cambiaron esos tests ni esos flujos; la selección final S3 es explícitamente la relevante a tier/configuración.
- **No se implementaron cobro real, Mercado Pago, invoices, deuda contable, cambios de subscription amount, UI, integración de agente externo ni S8E.** No se modificaron S7 ni los servicios/tests existentes S8A/B/C.

---

## Estado de implementación — S8E (2026-10-29)

Billing Intent exclusivamente interno para settlements finalizados de `appointments_ai`:

- [AppointmentAIUsageBillingIntent](../../services/api/src/apps/appointments/models.py) copia settlement UUID, business, subscription, `overage_amount` entero y moneda ARS. **El amount es el monto de overage congelado previo a cualquier tratamiento fiscal que se defina posteriormente.** No se calcula IVA, no se agregan impuestos ni se modifica el settlement o `SubscriptionV2.amount`.
- [prepare_ai_usage_billing_intent](../../services/api/src/apps/appointments/services/ai_usage_billing_intent.py) relee la fila persistida bajo lock y exige settlement existente, `finalized`, ARS, monto no negativo y subscription del mismo business. Confía en la evidencia finalizada e inmutable de S8D, protegida por PostgreSQL; no recalcula importes desde ledger, sesiones, pricing, tier ni catálogo.
- OneToOne UNIQUE PostgreSQL con settlement y referencia UNIQUE determinística `MIRUBRO-AI-OVERAGE-<settlement_uuid>`. Preparar repetidamente devuelve la misma fila sin actualizar el snapshot. Cambios posteriores de pricing, tier, estado/cancelación o plan de la suscripción no reinterpretan el histórico.
- Monto positivo: `pending` significa preparado, **no cobrado ni deuda cobrada**. Monto cero: `void`, motivo `zero_amount`, `completed_at` y ningún proveedor; no se presenta un éxito de pago ficticio.
- Lifecycle explícito: prepare → `pending`; claim → `processing`; resultado correlacionado → `succeeded` o `failed`. `succeeded` y `void` son terminales. Void manual solo desde `pending`/`failed`; un procesamiento en curso no se cancela ni se reclama de nuevo por timeout.
- Claim usa lock de fila transaccional y genera `attempt_token` UUID para el único worker ganador. Los helpers de resultado exigen intent y token coincidentes, además de estado `processing`; resultados viejos, duplicados o ajenos producen `AIUsageBillingIntentConflict` sin escribir. No hay recuperación automática de un worker perdido.
- `failed` no admite claim directo. Solo `retry_ai_usage_billing_intent`, con token del fallo y `confirmed_no_charge=True`, permite volver a `pending`; requiere reconciliación externa/autorizada que confirme ausencia de cargo. Un timeout o resultado incierto **no autoriza un retry**. El nuevo claim genera otro token y conserva la referencia externa estable. Un futuro proveedor deberá usar esa referencia como clave de idempotencia/correlación y resolver resultados inciertos antes de reintentar.
- Failure data usa códigos permitidos y mensajes internos constantes; **se descarta por completo el mensaje crudo del proveedor**, incluso códigos desconocidos se normalizan a `provider_error`. No se persisten payloads, headers, tarjetas ni tokens dentro de errores. Provider/reference son identificadores acotados, no contenedores de payloads. Los futuros adaptadores deberán pasar exclusivamente el nombre del proveedor y su identificador de operación.
- [Migración 0013](../../services/api/src/apps/appointments/migrations/0013_ai_usage_billing_intent.py) crea únicamente esta tabla, sus constraints y su trigger: snapshot/referencia inmutables, comprobación inicial contra settlement, transiciones acotadas, protección de tokens, errores sanitizados y prohibición de borrado histórico. No crea tablas invoice/payment/debt. Aplicación, reversión a 0012 y reaplicación verificadas en PostgreSQL aislado; los 29 tests S8E volvieron a aprobar después de reaplicar.
- [Tests S8E](../../services/api/src/apps/appointments/tests/test_ai_usage_s8e.py) cubren snapshots, idempotencia/constraints, rechazo de evidencia inválida, cero, lifecycle posterior, ausencia de repricing/red, sanitización, resultados tardíos y carreras con conexiones PostgreSQL independientes.
- Validación: **226/226 aprobados, sin skips**: 29 S8E, 39 S8D, 34 S8C, 30 S8B, 41 S8A, 23 S6/lifecycle y 30 runtime resolver. Incluye las 3 carreras nuevas S8E (dos preparadores, dos claims y resultados success/failure concurrentes), además de las 10 carreras S8A–S8D. PostgreSQL **16.15** exclusivo, sin red externa, Django **5.2.17**, broker/cache/email en memoria e integraciones de agente deshabilitadas; no se usa la base habitual. `manage.py check` sin issues y `makemigrations --check --dry-run` sin cambios. La imagen API local tenía Django anterior: para validar se montó el Django 5.2.17 ya instalado, sin modificar dependencias del repositorio.
- **Sin cobro real, llamadas Mercado Pago, Access Token, preapprovals, payments, invoices, impuestos, webhooks, cron/workers nuevos, UI ni integración del agente externo.** Los helpers de resultado son contrato para integración futura, no un simulador ni un procesador conectado. No se modifican S7 ni servicios/tests S8A–S8D; no se implementa S8F.

---

## Estado de implementación — S8F (2026-10-29)

Adapter interno exclusivamente; **no habilita cobros reales ni avanza a S8G**.

- [AIUsageBillingProvider](../../services/api/src/apps/appointments/services/ai_usage_billing_provider.py) define `charge(request)` y `get_status(provider_reference, external_reference=...)`. No declara cancelaciones ni capacidades de Mercado Pago no homologadas. No existe adapter real, SDK, endpoint, webhook, worker programado ni lectura de credenciales en S8F.
- `AIUsageBillingRequest` es un snapshot inmutable de intent UUID, amount entero positivo ARS y `external_reference`, releído de la fila bloqueada. `idempotency_key` es exactamente `intent.external_reference`; nunca se genera una nueva referencia por retry. No representa importe fiscal final ni agrega IVA.
- `AIUsageBillingResult` expone solamente `status`, `provider_reference` y `failure_code`. Estados: `succeeded`, `failed`, `outcome_unknown`. Solo `declined` y `provider_not_enabled` son fallos conocidos; timeouts, errores genéricos y códigos desconocidos se normalizan a resultado ambiguo, incluso si un adapter los etiqueta `failed`. Success exige referencia válida. No se persisten respuestas crudas, mensajes de excepciones, headers, tarjetas ni tokens.
- Configuración [AI_USAGE_BILLING_PROVIDER](../../services/api/src/config/settings.py), documentada en [.env.example](../../services/api/.env.example): default obligatorio `disabled`. Todo otro valor, incluido `mercadopago`, devuelve el adapter deshabilitado y registra una advertencia fija sin propagar el valor configurado. No hay un modo real habilitable por configuración. El disabled devuelve `failed / provider_not_enabled`, no efectúa red ni simula éxito.
- `process_ai_usage_billing_intent` reclama un intent `pending`, o recibe un token S8E ya reclamado, y reserva una sola ejecución por claim. La reserva se confirma con `atomic(durable=True)` **antes** de invocar `charge`; una transacción externa se rechaza para no perder la reserva después de una operación remota. Solo el ganador del lock puede despachar. `succeeded`, `void` y amount cero no llegan al adapter.
- [AppointmentAIUsageBillingAttempt](../../services/api/src/apps/appointments/models.py) conserva el proveedor, token, referencia y resultado normalizado de cada intento. Se agrega en [migración 0014](../../services/api/src/apps/appointments/migrations/0014_appointmentaiusagebillingattempt.py), sin modificar la migración ni el lifecycle S8E. UNIQUE por token, trigger de identidad/referencia inmutable, resultados finales inmutables y prohibición de borrado histórico. Una referencia puede establecerse desde NULL una sola vez; nunca se reemplaza ni se borra. El histórico permanece aunque S8E autorice posteriormente un retry.
- Antes de dispatch se persiste `outcome_unknown / dispatch_incomplete`. Timeout, error de conexión, caída del worker o resultado inválido dejan el intent S8E en `processing`, sin `completed_at`; **no existe retry automático ni lease que vuelva a cobrar**. Una reserva ambigua previa también bloquea un nuevo dispatch. Los errores inesperados se propagan explícitamente y la reserva durable sigue bloqueando duplicados.
- `record_ai_usage_billing_result` aplica evidencia inmediata o tardía solo al intent/token reservado vigente. Rechaza tokens viejos/ajenos, referencias distintas y resultados duplicados/finales. Al resolver, usa los helpers S8E para persistir `provider_reference` en el intent y cerrar `succeeded` o `failed`, atómicamente con el resultado S8F. S8E conserva sus mensajes sanitizados; el motivo preciso `provider_not_enabled` permanece en el registro S8F.
- `reconcile_ai_usage_billing_intent` consulta únicamente `get_status` del mismo provider y la referencia persistida, correlacionada con la referencia externa estable. Success fake cierra succeeded; rechazo conocido fake cierra failed; unknown/timeout mantienen processing y bloquean retry. Sin referencia no se inventa una consulta remota: se exige evidencia tardía correlacionada vía contrato interno, o intervención futura; nunca se vuelve a llamar `charge` para averiguar el estado.
- El retry sigue siendo exclusivamente el gate explícito S8E (`confirmed_no_charge=True` y token correcto), después de un fallo conocido. Genera otro token, mantiene external_reference e histórico de provider references. No se alteraron servicios/tests S8A–S8E.
- **Bloqueos vigentes:** (1) S6B todavía no tiene homologación externa real completa de Mercado Pago; (2) presentación fiscal/IVA de overage pendiente. Cualquier provider real debe permanecer deshabilitado/fail closed hasta resolver ambos en un slice posterior.
- Validación: **203/203 tests aprobados, sin skips**: 30 S8F, 29 S8E, 39 S8D, 34 S8C, 30 S8B y 41 S8A. Incluye concurrencia con conexiones PostgreSQL independientes: dos workers sobre pending y dos workers con el mismo claim ejecutan el provider fake una sola vez; la reserva ya está confirmada antes de dispatch. `manage.py check` sin issues; `makemigrations --check --dry-run` sin cambios. PostgreSQL **16.15** exclusivo, Django **5.2.17** ya instalado montado sobre la imagen API local, sin instalar dependencias ni requerir Internet. Contenedor PostgreSQL con `--network none`, runner compartiendo únicamente ese namespace aislado; ningún `.env` cargado, email/cache/broker en memoria, agentes deshabilitados y base habitual intacta. Tests S8F bloquean HTTP/sockets externos y accesos a credenciales durante el procesamiento.
- **Sin cobros reales, llamadas Mercado Pago, Access Token, invoices, IVA/impuestos, cambios de subscription amount, UI, agente externo ni S8G.** Los fakes se inyectan explícitamente solo en los tests del contrato; no se registran como provider configurable.

---

## Estado de implementación — S8G (2026-10-29)

Orquestación automática **offline** de usage billing; termina al preparar Billing Intent, sin dispatch ni S8H.

- [discover_ai_usage_periods_ready_for_settlement](../../services/api/src/apps/appointments/services/ai_usage_billing_pipeline.py) descubre tuplas persistidas business/subscription/start/end en sesiones, charges y settlements pendientes. También considera anchors conocidos de suscripciones `appointments_ai`, independientemente de su estado actual, y enumera sus subperíodos usando el resolver mensual S8A existente. Solo incluye `at >= usage_period_end`. No extrapola meses antes ni después del anchor vigente ni deriva historia vacía desde “ahora”.
- Discovery devuelve `AIUsagePeriodDiscovery(periods, skipped)`: solo tuplas vencidas no finalizadas con evidencia estructural suficiente. Sesiones sin charge, período vacío sin anchor demostrable, ownership inválido, múltiples subscriptions para el mismo período y períodos superpuestos se omiten con razón fija. Un anchor inválido se registra/omite sin abortar otras empresas. Un período vacío explícitamente registrado como pending puede validar su anchor con el mismo resolver aunque hoy el plan ya no sea IA; esto no habilita a inventar otros períodos vacíos de planes no-IA. La validación económica definitiva pertenece exclusivamente a S8D, bajo sus locks y constraints: no se calculan precios, cantidades económicas ni amounts en S8G.
- [process_due_ai_usage_billing](../../services/api/src/apps/appointments/services/ai_usage_billing_pipeline.py) fija un único `at` para toda la corrida, llama a `finalize_ai_usage_settlement(...)` y después a `prepare_ai_usage_billing_intent(...)`. Un barrido adicional de settlements finalizados vencidos **sin intent** recupera preparaciones interrumpidas sin revalidar ni reinterpretar economía finalizada. Un settlement que ya tiene intent no requiere trabajo: la repetición completa es no-op sin escrituras. No filtra historia por acceso actual, business activo, tier actual ni lifecycle.
- Finalización y preparación son transacciones separadas: si falla S8D no se prepara intent; si falla S8E el settlement finalizado queda persistido y la próxima corrida completa el intent faltante. Errores controlados de evidencia/integridad/filas ausentes se contabilizan por período y no abortan otras empresas. No se devuelven ni loguean excepciones crudas. Fallos inesperados/operacionales no se convierten en éxito: se propagan para que la infraestructura registre el error.
- Idempotencia y carreras: se reutilizan las constraints S8D/S8E, el lock business → subscription para finalizar y el lock de settlement para preparar. Dos workers pueden descubrir la misma tupla; uno crea/finaliza y el otro observa el existente, sin duplicar settlement, entries, intent ni charges. La clasificación created/existing se hace dentro de esos locks. El pipeline nunca crea charges, ni claims ni `AppointmentAIUsageBillingAttempt`.
- Resumen JSON estable: `scanned`, `settlements_created`, `settlements_existing`, `intents_created`, `intents_existing`, `skipped`, `failed`. `scanned` cuenta períodos de trabajo y omisiones de evidencia/anchors inválidos; no incluye períodos abiertos ni historia finalizada con intent. Se cumple `scanned = skipped + failed + intents_created + intents_existing`. `settlements_created` cuenta nuevas finalizaciones, incluida recuperación de una fila pending. Si falla la preparación, esa finalización sigue contabilizada. Los existing representan recuperación de intent faltante o trabajo concurrente, no un recuento global del histórico.
- Logging existente registra scope temporal/business/subscription, resultado fijo, UUID de settlement/intent y resumen numérico; sin tokens, payloads, respuestas de provider ni plataforma de auditoría nueva.
- [Task Celery](../../services/api/src/apps/appointments/tasks.py) `process_due_ai_usage_billing_task`, nombre `appointments.process_due_ai_usage_billing`, solo llama al servicio y devuelve su resumen. Se registra en el [Beat canónico existente](../../services/api/src/config/settings.py) **cada hora al minuto 10**, frecuencia conservadora sin requisito de precisión al segundo. No se crea un scheduler separado ni un schedule persistido irreversible. Invocación manual desde Django shell: `from apps.appointments.tasks import process_due_ai_usage_billing_task; process_due_ai_usage_billing_task.delay()`. Para una corrida síncrona con corte explícito usar el servicio con `at` timezone-aware.
- Sin overage: el mismo camino produce settlement cero y S8E prepara `void / zero_amount`. Con overage: intent `pending`, sin claim/provider. Suscripciones históricas canceladas/suspendidas o con cambios posteriores de tier/plan/anchor no alteran los snapshots registrados.
- Validación: **248/248 tests aprobados, sin skips**: 42 S8G (incluye task/Celery y dos carreras nuevas), 30 S8F, 29 S8E, 39 S8D, 34 S8C, 30 S8B, 41 S8A y 3 tests existentes de la task `expire_holds`. PostgreSQL **16.15** exclusivo, conexiones independientes en concurrencia, Django **5.2.17** ya instalado montado sobre la imagen API local; sin instalar dependencias ni requerir Internet. Se verificaron cierre de subperíodos anuales por separado, anchor día 31 tras febrero, recuperación de pending vacío tras downgrade no-IA, fallos parciales y protección de red/provider/credenciales. `manage.py check` sin issues y `makemigrations --check --dry-run` sin cambios; S8G no requiere migración ni modifica modelos o servicios/tests S8A–S8F. PostgreSQL con `--network none`, runner compartiendo exclusivamente su namespace aislado; ningún `.env` cargado, broker/cache/email en memoria, agentes deshabilitados y base habitual intacta. Contenedor descartable retirado tras validar.
- **Sin cobro real, Mercado Pago, dispatch, reconciliación remota, Access Token, invoices, IVA/impuestos, cambios de `SubscriptionV2.amount`, UI, integración de agente ni S8H.** No se importa ni resuelve el provider en S8G; incluso `AI_USAGE_BILLING_PROVIDER=mercadopago` no habilita ninguna llamada. Permanecen el default S8F `disabled` y los bloqueos S6B/fiscal.

---

# 2. Definición del producto

## 2.1 Qué es MiRubro Turnos

**MiRubro Turnos** es una plataforma para gestionar reservas, clientes y atención de negocios que trabajan principalmente mediante turnos o citas.

El flujo central que debe resolver es:

```text
Cliente consulta
→ se identifica necesidad
→ se consulta disponibilidad real
→ se reserva / coordina
→ existe un Appointment real
→ el profesional atiende
→ se completa / cancela / reprograma / marca no-show
→ queda historial
```

MiRubro Turnos no debe pensarse únicamente como una agenda online.

Su propuesta de valor es:

> **Centralizar agenda, profesionales, clientes, reservas y atención en un solo lugar, permitiendo que el negocio organice su día y que sus clientes reserven y coordinen turnos fácilmente, incluso desde WhatsApp.**

---

## 2.2 Rubros objetivo iniciales

El producto está pensado inicialmente para negocios donde la reserva representa principalmente **tiempo de una persona/profesional**:

- peluquerías;
- barberías;
- centros de estética;
- uñas;
- depilación;
- spa;
- odontología;
- consultorios;
- psicología;
- terapia;
- nutrición;
- kinesiología;
- entrenadores;
- tatuadores;
- estudios profesionales;
- servicios técnicos con agenda;
- otros servicios profesionales con reserva previa.

No se debe expandir inicialmente el modelo hacia recursos complejos como canchas, habitaciones, boxes, maquinaria o inventario reservable, salvo definición futura explícita.

---

# 3. Principios de producto

Estas reglas son estructurales y deben mantenerse en implementaciones futuras.

## 3.1 Appointment es la fuente de verdad

`Appointment` es la única entidad autoritativa que prueba que existe un turno real.

No son prueba de turno:

- mensajes;
- Leads;
- conversaciones;
- propuestas;
- texto escrito por staff;
- confirmaciones informales;
- intención detectada por IA.

---

## 3.2 Proposal no es Appointment

El flujo conversacional puede utilizar `AppointmentProposal`, pero:

```text
Sin turno
→ Propuesta pendiente
→ Turno real
```

Una propuesta:

- no reserva definitivamente el slot;
- no sustituye al Appointment;
- debe revalidar disponibilidad al convertirse;
- puede vencer;
- puede ser reemplazada;
- puede fallar por slot ocupado.

---

## 3.3 Cliente transversal

`Customer` debe seguir siendo una entidad compartida por el ecosistema MiRubro.

No crear un CRM exclusivo de Turnos si el Customer transversal ya resuelve la necesidad.

Un mismo Customer debe poder concentrar, cuando corresponda:

- turnos;
- compras/ventas;
- presupuestos;
- conversaciones;
- notas;
- preferencias de contacto;
- pagos;
- actividad histórica.

---

## 3.4 Turnos funciona sin IA

MiRubro Turnos debe ser un producto completo aun cuando el negocio no contrate IA.

La IA es una capa premium de atención y automatización.

---

## 3.5 Disponibilidad real

Ningún bot, frontend, staff o automatización debe inventar horarios.

La disponibilidad siempre debe provenir del motor real de disponibilidad de Turnos.

---

## 3.6 Owner controla el negocio

El owner mantiene control total de:

- equipo;
- accesos;
- profesionales;
- permisos;
- billing;
- add-ons;
- IA;
- límites de consumo.

El owner no cuenta como asiento de usuario secundario.

---

# 4. Estructura comercial oficial

MiRubro Turnos tendrá tres niveles principales y un add-on.

```text
MiRubro Turnos
├── Turnos
├── Turnos Pro
├── Add-on Automatizaciones
└── Turnos IA Recepcionista
    ├── IA 300
    ├── IA 1.500
    ├── IA 3.000
    └── Business
```

---

# 5. Plan Turnos

## 5.1 Precio

```text
$23.000 ARS / mes
```

Pago anual:

```text
20% de descuento
$220.800 ARS / año
```

No existe prueba gratis pública.

MiRubro puede otorgar acceso gratuito/manual de forma excepcional desde administración interna.

---

## 5.2 Profesionales incluidos

Turnos incluye:

```text
2 profesionales activos/reservables
```

Un profesional archivado o inactivo no consume cupo.

Si el owner también atiende turnos, cuenta como profesional porque ocupa agenda.

---

## 5.3 Funcionalidad esperada

Turnos debe ser un producto completo y operativo.

Incluye conceptualmente:

- agenda;
- vista diaria;
- vista semanal;
- crear turnos;
- editar;
- reprogramar;
- cancelar;
- completar;
- no-show;
- servicios;
- categorías;
- profesionales;
- horarios;
- excepciones;
- clientes;
- historial;
- reserva pública;
- link público;
- Mercado Pago;
- señas;
- gestión de pagos del turno;
- configuración básica;
- analytics básicos;
- reservas ilimitadas;
- clientes ilimitados.

---

## 5.4 Lo que NO debe requerir Pro

Estas capacidades forman parte de Turnos y no deben bloquearse detrás de Pro:

- Mercado Pago;
- señas;
- reserva pública;
- clientes;
- historial;
- agenda funcional;
- profesionales como recursos;
- horarios;
- servicios;
- estados de turno.

---

# 6. Plan Turnos Pro

## 6.1 Precio

```text
$28.000 ARS / mes
```

Pago anual:

```text
20% de descuento
$268.800 ARS / año
```

---

## 6.2 Profesionales incluidos

Turnos Pro incluye:

```text
5 profesionales activos/reservables
```

Los profesionales adicionales se cobran por separado.

---

## 6.3 Diferencial principal

Turnos Pro no existe para desbloquear funciones básicas.

Su valor principal es:

> **gestión avanzada de equipo + identidad/login por profesional + analytics superiores.**

---

## 6.4 Funcionalidad Pro

Pro incluye todo Turnos más:

- login individual por profesional;
- vínculo entre profesional y usuario/Membership;
- panel propio;
- `Mi agenda`;
- acceso limitado por profesional;
- permisos específicos;
- disponibilidad propia;
- bloqueo de horarios;
- posibilidad de editar disponibilidad según permisos;
- clientes vinculados al profesional;
- analytics avanzados;
- analytics por profesional;
- métricas de ocupación;
- métricas de servicios;
- comparativas de rendimiento;
- dashboard de equipo.

---

# 7. Profesional adicional

Código conceptual:

```text
appointments_extra_professional
```

Precio:

```text
+$3.000 ARS / mes por profesional activo adicional
```

Anual:

```text
+$28.800 ARS / año
```

El descuento anual del 20% sí aplica a este add-on recurrente.

---

## 7.1 Regla de conteo

Cuenta:

- profesional activo;
- profesional reservable;
- owner que además atiende como profesional.

No cuenta:

- profesional archivado;
- profesional desactivado;
- profesional histórico sin reservas nuevas.

---

## 7.2 Límite comercial recomendado

Turnos Pro puede escalar mediante profesionales adicionales.

Como regla comercial inicial:

```text
15+ profesionales → evaluar Business
```

Esto no implica necesariamente una restricción técnica absoluta.

---

# 8. Add-on Automatizaciones

## 8.1 Precio

```text
+$8.500 ARS / mes
```

Anual:

```text
+$81.600 ARS / año
```

Disponible para:

- Turnos;
- Turnos Pro.

Turnos IA lo incluye automáticamente.

---

## 8.2 Qué incluye conceptualmente

El add-on Automatizaciones debe centralizar comunicaciones y acciones automáticas como:

- recordatorios previos al turno;
- seguimiento de no-show;
- confirmación automática;
- avisos de cancelación;
- avisos de reprogramación;
- recordatorio de seña pendiente;
- mensaje post-turno;
- solicitud de reseña;
- email;
- otros canales futuros.

No todas estas capacidades necesariamente existen hoy en el repo.

El entitlement del add-on puede existir antes de que todas las automatizaciones futuras estén implementadas.

---

## 8.3 Separación respecto de IA

Las automatizaciones:

- no consumen conversaciones IA por sí solas;
- tienen lifecycle independiente;
- pueden pausarse sin cancelar Turnos;
- pueden desactivarse por configuración aunque el add-on siga contratado.

---

# 9. Turnos IA Recepcionista

## 9.1 Definición

Turnos IA debe venderse como:

> **Turnos Pro + Automatizaciones + Recepcionista IA por WhatsApp.**

No debe comunicarse solamente como “chatbot”.

La propuesta es una recepcionista que:

- atiende consultas;
- entiende intención;
- consulta servicios;
- consulta precios;
- consulta disponibilidad real;
- recibe solicitudes;
- propone horarios;
- detecta intención de confirmar;
- escala a humano;
- soporta takeover/release;
- consulta turnos existentes;
- puede evolucionar hacia más acciones autónomas controladas.

---

## 9.2 Qué incluye

Turnos IA incluye automáticamente:

```text
Turnos Pro
+
Automatizaciones
+
Solicitudes/Leads
+
WhatsApp
+
Recepcionista IA
+
usage tier
```

No se cobra Pro ni Automatizaciones por separado cuando el cliente ya contrata Turnos IA.

---

# 10. Precios Turnos IA

## 10.1 IA 300

```text
Precio: $150.000 ARS / mes
Conversaciones incluidas: 300
```

Anual:

```text
$1.440.000 ARS / año
```

---

## 10.2 IA 1.500

```text
Precio: $275.000 ARS / mes
Conversaciones incluidas: 1.500
```

Anual:

```text
$2.640.000 ARS / año
```

---

## 10.3 IA 3.000

```text
Precio: $385.000 ARS / mes
Conversaciones incluidas: 3.000
```

Anual:

```text
$3.696.000 ARS / año
```

---

## 10.4 Business

```text
Precio: a medida
```

Business aplica especialmente a:

- más de 3.000 conversaciones sostenidas;
- múltiples números de WhatsApp;
- múltiples sucursales;
- más de 15 profesionales;
- integraciones especiales;
- necesidades contractuales;
- soporte prioritario;
- SLA;
- configuración custom;
- grandes volúmenes.

---

# 11. Definición canónica de conversación IA

Una conversación IA es:

> **Una sesión de atención de un cliente con la Recepcionista IA dentro de una ventana fija de 24 horas, iniciada a partir de una interacción real del cliente y en la que la IA efectivamente participa.**

---

## 11.1 Inicio de conversación

Una conversación comienza cuando:

1. entra un mensaje válido del cliente;
2. la IA efectivamente participa.

No basta con recibir un webhook.

---

## 11.2 Ventana de 24 horas

La ventana se fija desde el inicio de la conversación.

Ejemplo:

```text
Lunes 14:00 → inicia conversación
Martes 13:59 → sigue siendo la misma
Martes 14:01 → una nueva interacción puede iniciar otra conversación
```

No usar una ventana móvil que se renueve con cada mensaje.

---

## 11.3 Qué no consume conversación IA

No consumen por sí solos:

- delivery receipts;
- webhooks duplicados;
- eventos técnicos;
- spam descartado;
- mensajes internos;
- conversaciones 100% humanas;
- automatizaciones salientes;
- recordatorios;
- avisos de cancelación;
- avisos de reprogramación;
- solicitudes de reseña.

---

## 11.4 Automatización + respuesta

Ejemplo:

```text
MiRubro envía recordatorio
→ no consume IA

Cliente responde
→ IA interviene
→ comienza conversación IA
```

---

## 11.5 Takeover humano

Si la IA intervino y luego recepción toma control:

```text
IA → humano
```

la conversación cuenta como una conversación IA.

Los mensajes humanos posteriores no generan otra conversación IA dentro de la misma ventana.

---

## 11.6 Conversación totalmente humana

Si el cliente es derivado directamente a un humano y la IA nunca interviene:

```text
0 conversaciones IA
```

---

## 11.7 Cruce de período

Si una conversación comienza en un período y termina en el siguiente:

```text
31/10 23:30 → inicia
01/11 00:30 → continúa
```

se imputa al período donde comenzó.

---

## 11.8 No confundir con Appointment

```text
ConversationUsage != Appointment
```

Una conversación puede:

- generar un turno;
- no generar turno;
- generar propuesta;
- terminar en consulta;
- escalar a humano.

Una reserva pública puede generar Appointment sin consumir conversación IA.

---

# 12. Conversaciones adicionales

## 12.1 Regla general

Cuando el cliente consume todas las conversaciones incluidas, la Recepcionista IA **no se corta automáticamente**.

El consumo adicional viene:

```text
ACTIVADO POR DEFECTO
```

---

## 12.2 Precio por conversación adicional

### IA 300

```text
$300 ARS por conversación adicional
```

### IA 1.500

```text
$200 ARS por conversación adicional
```

### IA 3.000

```text
$160 ARS por conversación adicional
```

### Business

```text
A medida
```

---

# 13. Tope adicional por defecto

El límite de gasto adicional inicial debe equivaler al:

```text
50% del valor mensual del plan
```

Por lo tanto:

| Plan | Precio mensual | Tope adicional default |
|---|---:|---:|
| IA 300 | $150.000 | $75.000 |
| IA 1.500 | $275.000 | $137.500 |
| IA 3.000 | $385.000 | $192.500 |

---

## 13.1 Control del owner

El owner puede:

- bajar el tope;
- subir el tope;
- desactivar consumo adicional;
- eventualmente seleccionar “sin límite” si MiRubro lo habilita.

El owner **no puede modificar el precio unitario por conversación extra**.

Ese precio pertenece al catálogo comercial de MiRubro.

---

## 13.2 Al llegar al tope

Cuando se alcanza el tope adicional configurado:

- conversaciones activas terminan normalmente;
- no se deben cortar sesiones activas;
- no se inician nuevas sesiones IA;
- nuevas consultas pasan a recepción humana / Solicitudes;
- se ofrece upgrade.

---

# 14. Puntos de conveniencia entre planes

Los precios adicionales están diseñados para que exista incentivo natural al upgrade.

## 14.1 IA 300 → IA 1.500

```text
Diferencia de plan:
$275.000 - $150.000 = $125.000

Extra IA 300:
$300

Break-even:
aprox. 417 conversaciones adicionales
```

Por lo tanto:

```text
aprox. 717 conversaciones totales
```

es el punto donde IA 1.500 empieza a ser económicamente más conveniente.

---

## 14.2 IA 1.500 → IA 3.000

```text
Diferencia:
$385.000 - $275.000 = $110.000

Extra IA 1.500:
$200

Break-even:
550 conversaciones adicionales
```

Por lo tanto:

```text
aprox. 2.050 conversaciones totales
```

es el punto donde IA 3.000 empieza a ser más conveniente.

---

## 14.3 IA 3.000 → Business

IA 3.000 puede seguir consumiendo extras a $160.

Si el negocio supera 3.000 de manera sostenida o alcanza volúmenes altos, MiRubro debe sugerir Business.

---

# 15. Alertas de consumo

MiRubro debe avisar al owner de forma anticipada.

## 15.1 Conversaciones incluidas

Recomendado:

```text
80% → aviso informativo
95% → alerta importante
100% → comienza consumo adicional
```

---

## 15.2 Gasto adicional

Recomendado:

```text
50% del tope → aviso
80% → alerta
95% → alerta crítica
100% → detener nuevas conversaciones IA
```

---

# 16. Upgrade y downgrade

## 16.1 Upgrade

El upgrade debe ser:

```text
inmediato
```

Ejemplos:

```text
Turnos → Pro
IA 300 → IA 1.500
IA 1.500 → IA 3.000
```

Debe conservar:

- datos;
- turnos;
- profesionales;
- clientes;
- historial;
- conversaciones;
- uso actual.

---

## 16.2 Upgrade IA y overage del período

Si un cliente estaba usando adicionales y hace upgrade dentro del mismo período:

```text
uso total del período
→ se reevalúa contra el nuevo límite incluido
```

Ejemplo:

```text
IA 300
400 conversaciones totales
100 adicionales todavía no facturadas

Upgrade → IA 1.500

400 / 1.500
0 adicionales
```

Los adicionales todavía no cerrados/facturados pueden recalcularse.

No recalcular períodos ya cerrados.

---

## 16.3 Downgrade

El downgrade entra en vigencia:

```text
en la próxima renovación
```

Nunca reducir límites inmediatamente sobre un período ya pagado.

---

# 17. Downgrade Pro → Turnos

Si el negocio supera el límite del nuevo plan:

- no borrar profesionales;
- no borrar historial;
- pedir al owner elegir profesionales activos;
- profesionales excedentes quedan archivados/inactivos;
- cuentas profesionales pierden capacidades Pro;
- usuarios secundarios pueden conservar otros accesos MiRubro si corresponden.

---

# 18. Anualidad

## 18.1 Descuento

Todos los planes recurrentes fijos tienen:

```text
20% de descuento anual
```

Aplica a:

- Turnos;
- Turnos Pro;
- Turnos IA;
- Automatizaciones;
- profesional adicional.

---

## 18.2 El usage IA sigue siendo mensual

Aunque la suscripción sea anual:

```text
el cupo de conversaciones se reinicia mensualmente
```

No convertir:

```text
300/mes
```

en:

```text
3.600 conversaciones anuales acumulables
```

---

## 18.3 Overage no tiene descuento anual

El 20% anual no aplica a:

```text
conversaciones adicionales
```

Se cobran al precio unitario vigente completo.

---

# 19. Prueba gratis y complimentary access

## 19.1 No hay trial público

Regla oficial:

```text
NO existe prueba gratis pública
```

No comunicar “7 días gratis”, “14 días gratis” ni similar salvo decisión futura.

---

## 19.2 Acceso gratuito excepcional

MiRubro puede otorgar acceso manual por:

- demo;
- beta;
- cliente estratégico;
- partner;
- alianza;
- soporte;
- cortesía;
- negociación comercial.

Debe ser un mecanismo interno auditable.

Conceptualmente:

```text
ComplimentaryAccess
- business
- product
- plan
- starts_at
- ends_at
- reason
- created_by
```

---

# 20. Lifecycle de suscripción

## 20.1 Active

Operación completa según plan.

---

## 20.2 Past due / grace

Durante una gracia inicial:

- owner puede entrar;
- agenda puede seguir operativa temporalmente;
- mostrar alertas claras;
- evitar pérdida abrupta de operación.

La política exacta de días puede definirse posteriormente.

---

## 20.3 Suspended

En suspensión:

- no nuevas reservas;
- reserva pública no acepta nuevos turnos;
- IA no inicia nuevas conversaciones;
- automatizaciones no generan nuevos envíos;
- owner mantiene acceso administrativo limitado;
- historial/datos se conservan.

---

## 20.4 Canceled

Cancelación por defecto:

```text
cancel_at_period_end
```

El cliente conserva acceso hasta finalizar el período ya pagado.

No borrar datos.

---

## 20.5 Pausa futura

Puede existir a futuro un estado `paused`:

- no nuevas reservas;
- datos preservados;
- IA pausada;
- automatizaciones pausadas;
- reserva pública informa indisponibilidad temporal.

No es obligación de MVP.

---

# 21. Cancelación anual

Un plan anual:

- se paga por adelantado;
- puede cancelarse la renovación;
- no implica devolución proporcional automática;
- mantiene acceso hasta fin del período anual contratado.

---

# 22. Roles

## 22.1 Owner

Puede gestionar:

- todo Turnos;
- usuarios;
- profesionales;
- permisos;
- pagos;
- billing;
- plan;
- add-ons;
- IA;
- usage limits.

No cuenta como asiento secundario.

---

## 22.2 Admin

Puede operar casi todo el producto, salvo restricciones sensibles definidas por permisos.

No debe asumir automáticamente capacidad para:

- transferir propiedad;
- cancelar suscripción;
- modificar billing sensible.

---

## 22.3 Recepción / Manager

Rol operativo.

Debe poder manejar:

- agenda;
- creación de turnos;
- reprogramación;
- cancelación;
- confirmación;
- no-show;
- clientes;
- cobros/señas según permiso;
- disponibilidad;
- Solicitudes/Leads cuando IA está activa.

No necesita acceso a billing ni configuración sensible.

---

## 22.4 Viewer

Solo lectura.

---

## 22.5 Professional

Rol funcional exclusivo de Pro/IA.

Debe tener scope propio.

No debe obtener acceso global por defecto.

Su acceso debe derivar de:

```text
Membership
+
Professional vinculado
+
Permisos
+
Scope de datos
```

---

# 23. Experiencia del profesional

El profesional autenticado puede tener:

```text
Inicio
Mi agenda
Mis clientes
Mi disponibilidad
Mi actividad
```

Puede, según permisos:

- ver sus turnos;
- completar;
- marcar no-show;
- reprogramar;
- cancelar;
- bloquear horarios;
- editar disponibilidad;
- ver clientes vinculados;
- ver analytics propios;
- ver pagos si el owner lo permite.

No debe ver por defecto:

- agenda de otros;
- todos los clientes;
- billing;
- configuración general;
- analytics globales;
- usuarios;
- información financiera global.

---

# 24. Navegación por plan

## 24.1 Turnos

```text
Inicio
Agenda
Clientes

Gestión
  Servicios
  Profesionales
  Horarios

Configuración
```

---

## 24.2 Turnos Pro

```text
Inicio
Agenda
Clientes
Equipo
Analytics

Gestión
  Servicios
  Profesionales
  Horarios

Configuración
```

---

## 24.3 Turnos IA

```text
Inicio
Agenda
Solicitudes
Clientes
Equipo
Analytics

IA Recepcionista
  Conversaciones
  Configuración IA
  Uso

Gestión
  Servicios
  Profesionales
  Horarios

Automatizaciones
Configuración
```

---

# 25. Nombre visible Leads

Internamente puede continuar usándose `Lead`.

En interfaz de usuario se prefiere:

```text
Solicitudes
```

para evitar una terminología demasiado CRM/marketing.

---

# 26. Dashboard Turnos

Debe responder:

> ¿Cómo está mi agenda hoy?

Puede incluir:

- cantidad de turnos de hoy;
- próximos turnos;
- confirmados;
- cancelados;
- no-show;
- reservas nuevas;
- señas;
- alertas operativas;
- mini agenda.

---

# 27. Dashboard Pro

Debe enfocarse en:

> ¿Cómo está funcionando mi equipo?

Puede incluir:

- ocupación;
- performance por profesional;
- turnos por profesional;
- cancelaciones;
- no-show;
- servicios más solicitados;
- horarios libres;
- señas;
- comparativas.

---

# 28. Dashboard IA

Debe combinar:

```text
agenda
+
recepción automática
```

Puede incluir:

- conversaciones del día;
- conversaciones del período;
- uso vs límite;
- resueltas por IA;
- derivadas;
- Solicitudes pendientes;
- propuestas;
- pacientes que quieren confirmar;
- conversión;
- alertas IA;
- costo adicional acumulado.

---

# 29. Onboarding Turnos

Objetivo:

> llegar al primer turno lo antes posible.

Flujo recomendado:

```text
Datos del negocio
→ primer servicio
→ primer profesional
→ horarios
→ reserva online
→ Mercado Pago opcional
→ listo
```

No debe ser un wizard bloqueante de demasiados pasos.

Usar checklist progresivo.

---

## 29.1 Owner que también atiende

Preguntar conceptualmente:

> ¿Vos también atendés turnos?

Si responde sí, se puede crear automáticamente un Professional asociado al owner.

---

# 30. Onboarding Pro

Agrega:

- equipo;
- accesos;
- vincular Professional ↔ User/Membership;
- permisos;
- disponibilidad individual.

---

# 31. Onboarding Automatizaciones

Solo mostrar capacidades realmente disponibles.

Puede incluir:

- recordatorios;
- horas antes;
- no-show;
- email;
- Reply-To;
- otros eventos implementados.

---

# 32. Onboarding IA

Debe ocurrir después de tener Turnos Pro operativo.

Pasos conceptuales:

```text
Turnos configurado
→ equipo
→ identidad de recepcionista
→ datos/políticas del negocio
→ capacidades permitidas
→ reglas de escalamiento
→ conectar WhatsApp
→ confirmar tier
→ prueba
→ activar
```

---

## 32.1 IA no se activa automáticamente al pagar

Estados conceptuales:

```text
not_configured
setup
ready
active
paused
suspended
```

---

# 33. Source of truth de IA

La IA debe leer la información real de MiRubro:

- servicios;
- precios;
- profesionales;
- horarios;
- disponibilidad;
- negocio;
- políticas;
- reservas.

No pedirle al cliente mantener manualmente una segunda base duplicada de información.

---

# 34. Fair use y protección técnica

Una conversación comercial puede incluir múltiples mensajes, pero no debe permitir consumo técnico infinito.

MiRubro puede establecer límites internos de seguridad por sesión:

- mensajes;
- tokens;
- adjuntos;
- loops;
- spam;
- abuso;
- prompt injection.

Ante abuso o anomalía:

```text
escalar a humano
```

No crear arbitrariamente una nueva conversación facturable solo para compensar consumo técnico.

---

# 35. Métricas internas IA

Además del usage comercial, almacenar métricas técnicas:

```text
messages_in
messages_out
llm_input_tokens
llm_output_tokens
tool_calls
takeovers
appointments_created
proposals_created
resolved_by_ai
escalated
estimated_cost
```

Estas métricas:

```text
NO son unidades de billing
```

Sirven para rentabilidad, soporte, analytics y mejora del producto.

---

# 36. Arquitectura comercial canónica sugerida

## 36.1 Service type

Mantener:

```text
service_type = appointments
```

---

## 36.2 Plan codes objetivo

Preferencia canónica:

```text
appointments
appointments_pro
appointments_ai
```

`appointments_base` debe considerarse legacy/deprecado para el diseño futuro.

---

## 36.3 IA como plan + tier

No duplicar funcionalidades en tres planes IA distintos.

Preferencia:

```text
plan_code = appointments_ai
usage_tier = ai_300 | ai_1500 | ai_3000 | custom
```

---

## 36.4 Tiers IA

```text
ai_300
ai_1500
ai_3000
custom
```

---

# 37. Entitlements conceptuales

## Core

```text
appointments.core
appointments.public_booking
appointments.customers
appointments.payments
appointments.basic_analytics
```

## Pro

```text
appointments.professional_accounts
appointments.professional_scopes
appointments.team_permissions
appointments.advanced_analytics
appointments.team_dashboard
```

## Automatizaciones

```text
appointments.automations
```

## IA

```text
appointments.ai
appointments.leads
appointments.agent
appointments.takeover
appointments.proposals
appointments.automations
```

No asumir que estos códigos existen actualmente: representan la arquitectura objetivo.

---

# 38. Usage policy IA

Conceptualmente debe existir una policy por negocio/suscripción:

```text
additional_usage_enabled = true
additional_spend_limit = valor configurable
```

Default:

```text
50% del valor mensual del plan
```

El owner puede modificar el límite.

---

# 39. Usage metering IA

Se recomienda separar:

```text
Subscription
UsagePolicy
AIConversationSession
AIUsagePeriod
```

No guardar todo el usage directamente dentro de `SubscriptionV2`.

---

## 39.1 Conversation session

Debe poder auditar:

```text
business
subscription
channel
external_contact_id
started_at
ends_at
billing_period
usage_tier
included
unit_price
amount
status
```

---

## 39.2 Snapshot de precio

Cada conversación adicional debe persistir:

```text
unit_price vigente cuando ocurrió
```

Nunca recalcular consumos históricos contra el precio actual del catálogo.

---

# 40. Pago y billing

Diferenciar siempre:

```text
billing SaaS de MiRubro
!=
pagos/señas de los clientes del comercio
```

Mercado Pago de reserva pública pertenece al flujo operativo del comercio.

La suscripción de Turnos pertenece al billing SaaS de MiRubro.

---

# 41. Upgrade billing

Upgrade:

```text
inmediato
```

Idealmente prorrateado por el período restante según la infraestructura comercial vigente.

---

# 42. Downgrade billing

Downgrade:

```text
en próxima renovación
```

---

# 43. Datos y cancelación

Nunca eliminar automáticamente por billing:

- Customers;
- Appointments;
- Professionals;
- Services;
- pagos;
- conversaciones;
- analytics históricos;
- mensajes;
- propuestas.

Billing controla acceso/capacidad, no propiedad de los datos.

---

# 44. Reserva pública y pagos

Turnos común debe mantener:

- link público;
- reserva;
- servicio;
- profesional;
- fecha/hora;
- datos del cliente;
- disponibilidad real;
- seña;
- Mercado Pago.

No convertir estos puntos en diferenciales Pro.

---

# 45. Analytics

## 45.1 Turnos básico

Debe ofrecer analytics simples suficientes para operar:

- turnos por período;
- completados;
- cancelados;
- no-show;
- señas;
- servicio más reservado;
- información operativa básica.

---

## 45.2 Pro

Debe ofrecer:

- ocupación;
- rendimiento por profesional;
- horas disponibles vs ocupadas;
- cancelaciones por profesional;
- no-show por profesional;
- servicios por profesional;
- comparativas;
- métricas más avanzadas.

---

## 45.3 IA

Debe poder medir:

- conversaciones;
- resolución automática;
- escalamiento;
- Leads;
- propuestas;
- conversiones;
- turnos;
- uso;
- overage;
- costo estimado.

---

# 46. Qué no debe ser MiRubro Turnos

No convertir el producto en:

- ERP médico;
- historia clínica;
- sistema odontológico vertical completo;
- recetas;
- software RRHH;
- marketplace;
- CRM separado;
- call center generalista.

Core:

```text
tiempo
+
reservas
+
clientes
+
profesionales
+
atención
```

---

# 47. Integración con otros productos MiRubro

Turnos debe poder contratarse de forma independiente.

No exigir Gestión Comercial.

Si un negocio usa varios productos, se deben compartir cuando corresponda:

- Business;
- owner;
- usuarios;
- Customer;
- branding;
- Mercado Pago;
- información fiscal;
- otros datos transversales.

Ejemplos:

```text
Barbería → Turnos
Centro estético → Turnos Pro + Gestión
Consultorio → Turnos IA
```

---

# 48. Reglas para prompts futuros a Copilot

Cuando se trabaje sobre Turnos:

1. Leer este archivo primero.
2. Tratarlo como fuente canónica de decisiones de producto.
3. No reintroducir `appointments_base` como diseño futuro salvo migración/compatibilidad explícita.
4. No inventar nuevos planes sin autorización.
5. No mover Mercado Pago, reserva pública o clientes a Pro.
6. No convertir Automatizaciones en requisito para usar Turnos.
7. No hacer de IA la arquitectura base del producto.
8. No usar Lead/Proposal como prueba de Appointment.
9. No crear un segundo Customer específico de Turnos.
10. No implementar límites de reservas o clientes salvo nueva decisión explícita.
11. Mantener profesionales incluidos:
    - Turnos: 2;
    - Pro/IA: 5.
12. Profesional adicional:
    - $3.000 ARS/mes.
13. Automatizaciones:
    - $8.500 ARS/mes.
14. Mantener precios IA definidos en este documento.
15. Respetar definición de conversación IA.
16. Respetar overage y spend cap.
17. Upgrade inmediato / downgrade próxima renovación.
18. Sin trial público.
19. 20% off anual.
20. No borrar datos por downgrade/cancelación.

---

# 49. Pricing canónico resumido

| Producto | Precio mensual | Incluido |
|---|---:|---|
| Turnos | $23.000 | 2 profesionales |
| Turnos Pro | $28.000 | 5 profesionales |
| Profesional adicional | +$3.000 | 1 profesional |
| Automatizaciones | +$8.500 | add-on |
| Turnos IA 300 | $150.000 | 300 conversaciones |
| Turnos IA 1.500 | $275.000 | 1.500 conversaciones |
| Turnos IA 3.000 | $385.000 | 3.000 conversaciones |
| Business | A medida | custom |

---

# 50. Overage IA resumido

| Tier | Extra por conversación | Spend cap default |
|---|---:|---:|
| IA 300 | $300 | $75.000 |
| IA 1.500 | $200 | $137.500 |
| IA 3.000 | $160 | $192.500 |
| Business | Custom | Custom |

---

# 51. Anualidad resumida

| Producto | Precio anual |
|---|---:|
| Turnos | $220.800 |
| Turnos Pro | $268.800 |
| Profesional adicional | $28.800 |
| Automatizaciones | $81.600 |
| IA 300 | $1.440.000 |
| IA 1.500 | $2.640.000 |
| IA 3.000 | $3.696.000 |

El uso adicional IA se cobra por separado y no recibe descuento anual.

---

# 52. Decisiones todavía abiertas

Este documento deja abiertas únicamente decisiones que todavía no fueron cerradas expresamente, entre ellas:

- duración exacta del grace por mora;
- política final de prorrateo según proveedor de billing;
- si se permite `additional_spend_limit = unlimited`;
- reglas contractuales exactas de Business;
- límites técnicos internos de fair use;
- precio y packaging futuro de nuevos canales de automatización;
- política exacta de múltiples sucursales;
- comportamiento definitivo de IA para reprogramación/cancelación autónoma;
- naming final comercial de tiers IA si se quisiera reemplazar `IA 300 / 1.500 / 3.000`;
- eventuales impuestos/precios finales publicados con IVA u otras condiciones comerciales.

Todo lo demás definido en este documento debe considerarse cerrado hasta actualización explícita.

---

# 53. Regla de actualización

Cuando una decisión de producto cambie:

1. actualizar este archivo;
2. indicar claramente la decisión nueva;
3. eliminar o marcar como deprecada la regla anterior;
4. evitar que código/documentación/prompts futuros dependan de decisiones viejas.

Este archivo debe mantenerse breve, explícito y autoritativo frente a documentación histórica.
