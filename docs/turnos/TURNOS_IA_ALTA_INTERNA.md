# Turnos IA — alta interna del piloto

Permite que el personal de plataforma (`superadmin`) cree desde
`/admin/clientes/nuevo` un negocio con **Turnos IA Recepcionista** como acceso
bonificado, y que su recepción abra la bandeja de Leads.

## Qué cambió

- `seed_appointments_catalog` ahora crea la fila `Plan` `appointments_ai`
  (inactiva, `price=0`, `features_json.pricing_mode='usage_tier'`). Antes la
  salteaba y el formulario solo ofrecía Turnos y Turnos Pro. Una fila existente
  conserva su precio. El comando se puede ejecutar varias veces sin duplicar.
- `GET /api/v1/platform-admin/clients/provisioning-options/` agrega
  `usage_tiers` **solo** al plan `appointments_ai`: `ai_300`, `ai_1500`,
  `ai_3000`, tomados de `generated/pricing.json`. `custom` queda afuera porque
  no tiene conversaciones incluidas y la medición de IA lo rechaza.
- `POST /api/v1/platform-admin/clients/` acepta `usage_tier` (opcional).
  `grant_complimentary_access()` lo exige para Turnos IA y lo rechaza para
  cualquier otro plan. El error es `400 invalid_complimentary_usage_tier` en el
  campo `usage_tier`, y el alta completa se revierte.
- El formulario muestra "Nivel de uso" solo cuando el plan elegido trae tiers.
  Para Turnos, Turnos Pro y los demás servicios, el payload sigue teniendo los
  mismos 10 campos.
- Sin cambios en Turnos, Turnos Pro, las suscripciones existentes ni el checkout
  público: todos los checkouts exigen `plan_status='active'`, y el producto
  Turnos sigue con `is_active=false`.

## Qué representa cada valor

| Valor | Dónde | Significado |
|---|---|---|
| `appointments_ai` | `SubscriptionV2.plan_code` | Turnos IA: incluye Pro y Automatizaciones. Otorga `appointments.leads` |
| `ai_300` | `SubscriptionV2.usage_tier` | 300 conversaciones de IA por mes (tier canónico) |
| `appointments_base` | plan legacy | Lo usa `qa-turnos`, creado por shell. También otorga Leads, pero no se ofrece en el admin |

## Guía corta

1. En el servidor: `python manage.py seed_appointments_catalog`.
2. Panel admin → Clientes → Nuevo cliente:
   - Servicio: **Turnos**.
   - Plan: **Turnos IA Recepcionista**.
   - Nivel de uso: **IA 300** (o el que corresponda).
   - Fechas de inicio y fin, y motivo: los completa quien hace el alta.
3. El responsable ingresa con Google, con el mismo email cargado
   (`/entrar/cliente`).
4. Responsable → Configuración → Roles & Accesos → Accesos (Cuentas) →
   **+ Crear usuario** → rol **Manager / Encargado**. Ese es el rol de
   recepción.
5. Recepción ingresa en `/entrar` con su usuario. Si se marcó, cambia la
   contraseña en el primer ingreso y después abre **Leads**
   (`/app/turnos/leads`).

Acceso del rol Manager en Turnos: tiene `view_leads` y `manage_leads` (ver,
tomar, asignar, notas, vincular cliente/turno), además de turnos, clientes,
notas y recordatorios. **No** tiene `manage_users`,
`manage_agent_channels` ni `manage_reminder_automations`.

## Verificación 2026-11-17 (local aislado, datos ficticios)

Base `mirubro_turnos_ia` en el postgres del compose. API y web corrieron desde
este worktree en 127.0.0.1:8100 y 127.0.0.1:3100.

- Navegador, admin: Turnos → Turnos IA Recepcionista → IA 300, 6 meses →
  "Cliente creado correctamente". Suscripción guardada:
  `appointments / appointments_ai / ai_300 / manual / trialing / is_active`,
  con el período elegido y el motivo. No se corrigió nada por shell.
- La primera prueba en navegador encontró un bug: `lib/admin/client.ts`
  descartaba `usage_tier`. Se corrigió y se agregó un test.
- Navegador, responsable: creó a "Recepción Ficticia" como Manager/Encargado
  desde Accesos (Cuentas).
- Navegador, recepción: login por `/entrar`, cambio de contraseña forzado y
  bandeja de Leads vacía ("0 LEADS"). `GET /api/v1/leads/` respondió 200 y
  `/me` informó `features.leads=true`.
- Control (alta por el mismo formulario con el plan Turnos): sin `usage_tier`,
  `GET /leads/` → 403, `GET /customers/` → 200, `features.leads=false`. Esto se
  verificó con el test client del API, no en el navegador.
- **Bloqueo del entorno:** el responsable creado por el admin es
  `owner_managed` sin contraseña y solo entra con Google preautorizado.
  "Olvidé mi contraseña" no aplica a esas cuentas, a propósito. Localmente se
  emitió un JWT para esa cuenta (sin tocar la suscripción). En producción, el
  responsable entra con su Google real.

## Uso de IA del piloto bonificado (2026-11-17, segundo commit)

### Problema

El bot pide permiso antes de cada interacción con
`POST /api/internal/appointments/ai-usage/authorize/`, firmado con la HMAC del
agente. Antes del cambio, el piloto creado por el formulario recibía
`{"allowed": false, "reason": "suspended"}` por tres condiciones:

1. `_locked_subscription` exigía `Business.status='active'`, y el alta
   bonificada deja `trialing`.
2. `subscription_lifecycle_access` solo aceptaba `active` o `past_due` en
   gracia, no `manual` + `trialing`. Por la misma causa, el negocio bonificado
   **tampoco podía crear turnos** ni usar automatizaciones
   (`appointments_v2_allows_creation=False`).
3. `resolve_appointments_ai_usage_period` exigía `billing_cycle` mensual o
   anual, y el alta deja `''`.

### Regla implementada

- **Elegibilidad** (`complimentary_grant_active`, en
  `billing/services/appointments_lifecycle.py`). Aplica solo a
  `provider=manual` + `status=trialing` **sin `trial_ends_at`**, que es la forma
  exacta del alta del admin. Una fila con `trial_ends_at` es un trial y sigue
  sin acceso (regla S7A). Exige
  `current_period_start <= ahora < current_period_end`. El fin es el mismo que ya usaba
  `billing.runtime._v2_grants_access`, sin incluir ese instante; además, un
  beneficio futuro no da acceso.
- Quedan afuera los beneficios futuros, los vencidos, los revocados
  (`canceled`) y los suspendidos. Los trials de Mercado Pago no cambian.
- Esa regla se suma a `subscription_lifecycle_access`. Con eso, el bonificado
  vigente también puede crear turnos, tomar reservas públicas y, si el plan las
  incluye, usar automatizaciones. Para la IA, `_locked_subscription` acepta
  `Business.status='trialing'` solo con un bonificado vigente.
- Se siguen exigiendo servicio `appointments`, plan `appointments_ai`, un
  nivel de uso con conversaciones incluidas, autenticación HMAC del agente,
  canal activo y conversación ligada a un lead del mismo negocio.

### Período de consumo

- Se reutiliza la regla mensual de la IA anual. El período **empieza en
  `current_period_start`**, es decir, en la fecha de inicio que se cargó en el
  alta. Se renueva el mismo día de cada mes siguiente y, en meses cortos, en el
  último día.
- El último período **se recorta en `current_period_end`**. Un beneficio de 6
  meses da 6 períodos contiguos, y uno de 10 días da un único período de 10
  días.
- Al llegar a `current_period_end` el beneficio termina, sin gracia: se
  responde `allowed:false` y no se registra uso.
- El nivel de uso funciona como **tope sin excedente**: con `ai_300`, la
  conversación 301 del mes responde `hard_cap_reached`. Una ventana de 24 h ya
  abierta se sigue reutilizando. Los cargos quedan como `included` con monto 0,
  así que no hay cobro.
- No se modifica la suscripción (`manual`, `trialing`, `billing_cycle=''`) ni se
  necesita corregir nada por shell. Los pilotos ya creados con `bc85c3f`
  quedan cubiertos tal como están.

### Evidencia

**Ejecutado por HTTP** en el entorno aislado (`api-tia`, base
`mirubro_turnos_ia`, negocio `clinica-piloto-ia` creado por el formulario):

- Preparación:
  - `provision_agent` creó la instancia `pilot-ia-agent`, la credencial
    `pilot-ia-key-1` y un canal ficticio.
  - `PUT /api/v1/integrations/agent/leads/<uuid>/` firmado respondió `201`:
    lead creado con su conversación.
  - No se conectó WhatsApp.
- Antes del cambio: `authorize` → `200 {"allowed":false,"reason":"suspended"}`.
- Después del cambio:
  - Consumo antes: `used 0 / included 300`, período del 17/11 al 17/12, 03:00
    UTC.
  - Misma interacción: `{"allowed":true,"created":true,"used":1,"remaining":299}`.
  - Reintento del mismo evento: `created:false`, mismo `session_id`,
    `used:1`.
  - Segunda interacción de la misma conversación dentro de 24 h: misma sesión,
    `used:1`.
  - Filas: 1 sesión, 1 cargo `('included', 0)`, 2 autorizaciones.
  - La suscripción sigue `appointments_ai / ai_300 / manual / trialing / ''`.
- Control con Turnos convencional bonificado (canal y lead propios):
  `{"allowed":false,"reason":"no_ai_entitlement"}`.

**Cubierto solo por pruebas**
(`apps/appointments/tests/test_ai_usage_complimentary.py`, con fechas
controladas):

- Tope del nivel.
- Comienzo del mes siguiente.
- Seis períodos que terminan exactamente en el fin del beneficio.
- Recorte de un beneficio corto.
- Vencimiento, beneficio futuro, revocado y suspendido.
- Aislamiento entre negocios y firma inválida (401).
- Trial de Mercado Pago sin cambios.
- IA mensual paga sin cambios, con excedente habilitado.

### Cómo ver cuánto cupo consumió el piloto

```bash
docker compose -f infra/docker-compose.yml exec api python manage.py shell -c "from django.utils import timezone; from apps.business.models import Business; from apps.appointments.services.ai_usage import get_appointments_ai_usage; print(get_appointments_ai_usage(Business.objects.get(slug='<slug>'), at=timezone.now()))"
```

Devuelve `usage_tier`, `period_start`, `period_end`, `used`, `included` y
`remaining` del período en curso. Es solo lectura. Si el beneficio no está
vigente, lanza `AIUsageUnavailable`.

## Inicio del beneficio (2026-11-17, tercer commit)

### Problema

Con un alta Turnos IA que empieza mañana, un día antes del inicio:

- `/me` devolvía `subscription.access_allowed=true` y `features.leads=true`.
  El layout de `/app` dejaba entrar, y el menú mostraba Leads.
- `GET /api/v1/leads/` respondía `200`.
- En cambio, la autorización de IA y la creación de turnos ya lo rechazaban
  (`complimentary_grant_active`).

Causa: `billing.runtime._v2_grants_access` solo miraba el fin del beneficio
(`current_period_end`), no el inicio. De esa función dependen `/me`,
`HasEntitlement`, `has_entitlement` y el control de cupos.

### Regla

Ahora, para `provider=manual` + `trialing` sin `trial_ends_at`, la ventana es
`[current_period_start, current_period_end)`, la misma que
`complimentary_grant_active`.

La regla es compartida por todos los servicios: Gestión, Menú QR, QR Reseñas
y Turnos. Para todos ellos, un bonificado futuro ya no da acceso antes de su
inicio. No cambia nada para:

- filas manuales sin `current_period_start`, como las del backfill: siguen con
  la regla de solo fin;
- trials con `trial_ends_at`;
- Mercado Pago (con o sin `trial_ends_at`);
- filas `active`, `past_due` y canceladas.

El cupo de usuarios usa la misma regla. Antes del inicio no se pueden crear
usuarios que no sean owner, como recepción. La membresía owner del alta no
consume cupo, así que el alta con fecha futura sigue funcionando. Durante esa
espera, el responsable ve `/app/planes`, porque el layout redirige sin acceso.

### Evidencia (`apps/billing/tests/test_complimentary_grant_start.py`)

Alta Turnos IA por `grant_complimentary_access()`, inicio mañana, rol Manager:

| Instante | runtime | `has_entitlement(leads)` | `/me` access_allowed | `GET /leads/` |
|---|---|---|---|---|
| inicio − 1 s (antes del fix) | true | true | true | 200 |
| inicio − 1 s | false | false | false | 403 |
| inicio | true | true | true | 200 |
| fin − 1 s | true | true | true | 200 |
| fin | false | false | false | 403 |

Contratos compartidos verificados sin cambios: 01A, 01B (fin excluido,
alcance por proveedor), `test_runtime_resolver`, cupos V2, alta Turnos IA y
consumo IA bonificado (126 tests OK).

## Circuito local bot ↔ Mi Rubro (2026-11-17)

Ensayo del recorrido de recepción con los dos servicios reales, fuera de
producción. No se tocó el webhook de Meta ni se usó el número del cliente.
Todas las personas, teléfonos (`+54 9 11 5550-73xx`) y wamids son ficticios
y nuevos.

### Entorno

| Pieza | Real o simulado | Detalle |
|---|---|---|
| Mi Rubro API | real | `api-tia` (:8100), base `mirubro_turnos_ia`, negocio `clinica-piloto-ia` (alta del formulario), con `AGENT_TAKEOVER_*` hacia el bot |
| Worker Celery | real | `api-tia-worker`, misma base: entrega tomas y mensajes humanos |
| Panel | real | `web-tia` (:3100), cuenta de recepción (rol Manager) con JWT emitido localmente |
| Bot | real | worktree `agenterecep-lead-handoff` (e8b70fb), `dist/main.js` en :3001, Postgres propio desechable (`bot-tia-pg`, :5434) |
| Firmas, sync, `ai-usage/authorize`, toma, mensajes humanos | reales | credencial `pilot-ia-key-1`; para la toma, una credencial nueva solo de este ensayo |
| Webhook entrante de Meta | **simulado** | `scripts/qa-wa-inbound.js` del bot: POST firmado al controlador real |
| Graph API saliente | **simulado** | `scripts/qa-fake-externals.js` (preload `fetch`, mismo método que `HARNESS_FAKE_META`) |
| Modelo | **simulado** | mismo preload. Respuesta determinista, **después** de la autorización de IA real |

### Resultados

Consumo medido con `get_appointments_ai_usage` antes y después de cada
caso (base: `used 1/300`, de la prueba anterior).

| Caso | Bot | Mi Rubro / panel | Consumo |
|---|---|---|---|
| A1 «Hola, quisiera un turno» (persona nueva) | sync `201 created` **antes** del modelo, autorización `allowed`, 1 respuesta | El lead aparece en la bandeja, sin atención pendiente | 1 → 2 (conversación nueva) |
| A2 motivo + preferencia («limpieza», «el viernes a la tarde») | Autorización `reused`, despedida fija, `BOT PAUSED`, sync v3 `applied` | Aviso «Nueva consulta para recepción», creado 10:18:31, a menos de 1 s del batch. Lead: «Pendiente de recepción · bot pausado», atención pendiente, motivo, horario y los 4 mensajes. Solo ofrece «Tomar chat» | sin cambio (misma sesión de 24 h) |
| Tomar chat → confirmar | Comando firmado `applied`, `state=paused` | Worker: `http=200 result=applied state=taken`. Panel: «Tomada por vos» y composer | — |
| Respuesta desde el panel | `HUMAN MESSAGE … result=queued`, **1** envío a Graph | Worker: `http=201`. El mensaje aparece en el historial | — |
| A3 el paciente vuelve a escribir | `BOT PAUSED batch left to the human`, sin modelo ni salida | El mensaje aparece en el mismo chat (polling del detalle) | sin cambio |
| B «quiero hablar con recepción» en el primer mensaje | Derivación con motivo y horario faltantes. Mensaje fijo «Dejé registrado tu pedido de hablar con recepción…» | Aviso. Lead pendiente de recepción con «Pidió hablar con una persona» | 2 → 3 (nueva) |
| C reinicio del bot (kill + arranque) y mensaje nuevo de B | Arranque: 0 pendientes. El mensaje queda `left to the human` con la pausa vigente | El mensaje se suma al lead de B | sin cambio |
| D el mismo evento entrante 3 veces (durante el debounce y después) | 2 × `duplicate webhook ignored`. 1 modelo, 1 autorización, 1 respuesta | 1 lead, 1 aviso, 2 mensajes | 3 → 4 (una sola vez) |
| D' reenvío de A3 al chat tomado | `duplicate webhook ignored` | Lucía sigue con 6 mensajes (3 del paciente, 2 del bot, 1 de recepción) | sin cambio |

En todo el ensayo `Appointment` siguió en 0: el bot no creó turnos.

### Qué vio recepción y cuándo

- El aviso no aparece en la bandeja de Leads, sino en el panel
  «Notificaciones» de **Turnos** (`/app/turnos/turnos`) y de **Clientes**, que
  se refresca cada 60 s. «Ver consulta» abre el lead y lo marca como leído.
- La bandeja de Leads **no se actualizaba sola**: había que recargarla o usar
  «Actualizar». Se resolvió después; ver «Bandeja abierta». El detalle del
  lead ya actualizaba la conversación.
- La primera vez que se usó «Ver consulta», el enlace quedó en Turnos mientras
  `next dev` compilaba la ruta. Con la ruta compilada, navegó bien. No se
  reprodujo: es propio del modo desarrollo.
- Los mensajes del bot y de recepción figuran «Estado desconocido» porque el
  Meta simulado no envía webhooks de estado (sent/delivered).

### Para decidir la activación

- (Resuelto, ver «Logs sin datos del paciente») El log `[HANDOFF] Lead ready`
  con teléfono, perfil y mensajes.
- La base de conocimiento del bot sigue fija en una sola clínica: el resumen
  dice «Dental Posadas II».
- Pendiente con un teléfono real:
  - que Meta entregue las salidas, incluido el número argentino normalizado
    (`549…` → `54…`);
  - los estados sent/delivered/read en el historial;
  - las ventanas de 24 h y los reintentos reales de Meta;
  - la latencia real del modelo;
  - los mensajes que llegan mientras el bot está caído (Meta los reintenta).

## Bandeja abierta (2026-11-17)

Recepción puede trabajar con `/app/turnos/leads` abierta sin recargar.

- **Bandeja:** se refresca cada 10 s (`LEADS_INBOX_POLL_MS`). Usa el mismo
  mecanismo que los avisos, `refetchInterval` de React Query.
  - Con la pestaña oculta se pausa, y al volver se pone al día.
  - Refresca la página y los filtros que estén en uso.
  - «Actualizando…» aparece solo al pedirlo a mano.
  - Si falla un refresco, la lista ya cargada no se tapa.
- **El refresco solo lee:** `GET /leads/` no toca avisos ni
  `acknowledged_at`. Verificado: tras varios refrescos, el aviso nuevo seguía
  sin leer y el lead sin revisar. No crea avisos, porque se generan una vez
  por derivación en el backend.
- **Chat tomado:** sin cambios de código. La conversación ya se agregaba de a
  poco cada 8 s, y el composer tiene estado propio. Ahora un test lo fija:
  borrador, foco, selección y chat abierto se conservan.

Medido en navegador, con el bot y Mi Rubro locales y la bandeja abierta antes
de enviar:

| Evento | Visible en | Detalle |
|---|---|---|
| Derivación nueva («…control el jueves a la tarde», persona nueva) | **7,1 s** desde el webhook | La fila aparece sola con «Atender» y se abrió desde la bandeja. Peor caso esperable: unos 13 s (debounce de 3 s del bot + 10 s de refresco) |
| Mensaje del paciente con el chat tomado | **9,4 s** | Mismo textarea, borrador intacto, foco y selección (5–14) conservados, misma URL |

## Logs sin datos del paciente (bot, 2026-11-17)

- **`[HANDOFF] Lead ready` y `[HANDOFF UPDATE]`:** ya no incluyen el resumen.
  Dejan `notification`, `lead`, `chat=wa:<ref>`, `attempt`, el motivo técnico
  y el resultado. El motivo técnico es `reason=lead_ready|urgency|human_requested_or_incomplete`
  más indicadores `has_reason/has_preferred_time/has_name`. El resultado es
  `result=not_sent_notify_disabled|sent`.
- **Fallas de aviso:** ya no vuelcan el resumen.
- **Cambios de lead:** se nombran los campos, no su texto.
- **Teléfono en todo el flujo** (webhook, debounce, contexto del modelo,
  pausa, envíos, estados, recuperación): pasa a `wa:<10 hex>`, un HMAC con
  `MIRUBRO_CONVERSATION_ID_KEY`. Es estable por chat, y `549…` y `54…` dan la
  misma referencia.
- **Errores de Graph:** solo el status y el código de Meta, sin el cuerpo.
- **Sin cambios:** el aviso que se manda a recepción por WhatsApp y los datos
  que guarda Mi Rubro.

Verificación con una consulta ficticia nueva (Valentina): 61 líneas de salida
del proceso y **0** apariciones del teléfono, el nombre, el texto de los
mensajes, «Paciente:» o «Asistente:». El panel conserva motivo, horario,
perfil, teléfono y los 3 mensajes.

## Prueba con teléfono

Kit fuera de los repos: `D:\Usuario\Desktop\turnos-ia-prueba-telefono\`. Ahí
están `bot.env` (con los secretos locales), `run-bot-real.sh`,
`provision-channel.sh`, `check.sh` y el paso a paso en `README.md`.

- **Número de prueba de Meta:** van en `bot.env`:
  - `WHATSAPP_PHONE_NUMBER_ID` y `WHATSAPP_WABA_ID` del número de prueba;
  - `WHATSAPP_ACCESS_TOKEN` de la app de prueba;
  - `WHATSAPP_APP_SECRET`;
  - `WHATSAPP_VERIFY_TOKEN`, que ya viene generado.

  `provision-channel.sh` da de alta ese `phone_number_id` como canal del
  negocio 3. Reutiliza la instancia y la credencial existentes.
- **Webhook comercial intacto:** la URL del webhook es por app. Por eso se usa
  **otra app de desarrollo** con su propio número de prueba. No se toca la app
  del número comercial.
- **Conexiones reales:**
  - `run-bot-real.sh` arranca sin `-r` y se niega a hacerlo si falta un
    secreto, si quedan valores del simulador o si ya hay algo en :3001.
  - El bot anuncia al arrancar `External calls: real` o `QA FAKES ACTIVE`, y
    `check.sh` lo comprueba.
  - Los wamid reales empiezan con `wamid.HBg`; los del simulador, con
    `wamid.qa.`.
- **Simuladores:** al cerrar esta preparación no queda ninguno corriendo (sin
  proceso en :3001). Se borró la copia vieja del preload que no se anunciaba.
  `scripts/qa-fake-externals.js` solo se carga si alguien lo pasa con `-r`.
- **Identidad del negocio:** fija en el código del bot, en cuatro lugares:
  - `clinic-knowledge.ts` (nombre, dirección, precios);
  - `agent.prompt.ts`;
  - el encabezado de `lead-notice.util.ts`;
  - el texto fijo de `whatsapp.service.ts`.

  Dice «Dental Posadas II». Del lado de Mi Rubro, el destino es
  `MIRUBRO_BUSINESS_ID=3` («Clínica Piloto IA») más el canal. El arranque
  imprime las dos cosas juntas. **Hay que confirmar que el piloto es Dental
  Posadas II** antes de atender al cliente.

Los 5 fallos de `whatsapp.controller.spec.ts` («persists the exact proposal
id…» ×4 y «released: messages stored before the release…») ya estaban en
433213b, sin estos cambios.

## Pendiente para la próxima entrega

- (Resuelto en el segundo commit) Medición de uso de IA con alta bonificada.
- (Resuelto en el tercer commit, ver "Inicio del beneficio") La diferencia de
  `billing.runtime` con un bonificado futuro.
- Alojamiento del bot, tokens permanentes, webhook de Meta, `provision_agent` y
  activación en producción.
