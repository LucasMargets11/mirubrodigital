# PROD-03A — Configuración individual de Recepcionista IA

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `c9085aa` · Bot
de referencia (solo lectura) `agenterecep-lead-handoff@8b69e4d`.

Objetivo: base persistente, en Mi Rubro, de la configuración individual de
cada recepcionista. Mi Rubro pasa a ser la fuente de verdad, sin endpoints ni
frontend todavía.

## 1. Configuración hardcodeada identificada (bot)

| Dato | Dónde está hoy en el bot |
|---|---|
| Identidad «Dental Posadas II», rubro odontológico, ciudad | `src/modules/openai/agent.prompt.ts` (encabezado y datos) |
| Dirección «Morcillo 2568…» | `agent.prompt.ts` (datos y respuesta de dirección) y `knowledge/clinic-knowledge.ts` |
| Servicios, precios, descuentos, planes de implantes | `knowledge/clinic-knowledge.ts` |
| Tono (español argentino, «vos») | `agent.prompt.ts` («IDENTIDAD Y TONO») |
| Bienvenida fija | `whatsapp/whatsapp.service.ts` («Soy el asistente virtual de Dental Posadas II») |
| Aviso de lead «🦷 Nuevo lead Dental Posadas II» | `conversations/lead-notice.util.ts` |
| Horarios, obras sociales, medios de pago | no cargados; el prompt prohíbe inventarlos |
| Reglas de seguridad, urgencias, medicación, derivación | `agent.prompt.ts` (reglas del sistema, no del negocio) |

No migré ningún dato de Dental Posadas II. El bot no cambia en este slice.

## 2. Modelo implementado y relaciones

`apps.leads.ReceptionistConfig` (migración `leads/0013_receptionist_config`).

- `business`: `OneToOneField(Business, CASCADE)`, una configuración por
  negocio. Es el agente lógico del negocio. Inmutable: `save()` rechaza
  reasignarla.
- Sin FK a `AgentInstance`. La relación agente ↔ negocio ya tiene una única
  fuente, el `AgentChannel` activo, y una `AgentInstance` puede atender varios
  negocios. Guardarla también en la configuración crearía dos verdades que
  podrían divergir.
- Acceso del agente: `services/receptionist_config.py::receptionist_config_for_agent`
  reutiliza `resolve_channel` del receiver (canal activo de esa instancia,
  negocio operativo, `business_id` coincidente). Devuelve `None` si el canal
  es válido y todavía no hay configuración. No es un endpoint: es la regla
  que va a usar PROD-03B.

## 3. Campos, validaciones y estados

| Campo | Tipo / límite |
|---|---|
| `assistant_name` | texto ≤ 80 |
| `business_category` (rubro) | texto ≤ 80 |
| `business_description` | texto ≤ 1000 |
| `custom_instructions` | texto ≤ 4000 |
| `tone` | `warm` \| `professional` \| `formal` (default `warm`) |
| `language` | `es-AR` \| `es` (default `es-AR`) |
| `welcome_message` | texto ≤ 500 |
| `operational_info` | texto ≤ 2000 (pagos, coberturas, políticas) |
| `business_hours` | texto ≤ 1000 |
| `services` | lista ≤ 30 de `{name ≤ 120, description? ≤ 500}` |
| `reference_info` | texto ≤ 4000 |
| `faqs` | lista ≤ 30 de `{question ≤ 300, answer ≤ 1000}` |
| `handoff_rules` | texto ≤ 2000 |
| `status` | `draft` (default) \| `ready` |
| `version` | entero > 0, no editable |
| `created_at` / `updated_at` | automáticas |

- Los textos son `CharField`, así que el largo también lo aplica la base. Se
  rechazan el carácter nulo y el texto que parezca un secreto (`sk-…`, tokens
  `EAA…` de Meta, Fernet `gAAAAA…`, claves privadas PEM, `Bearer …`, `AKIA…`).
- Listas: solo las claves admitidas, la clave identidad obligatoria y no
  vacía, sin duplicados (sin distinguir mayúsculas), y toda FAQ con respuesta.
- `ready` exige `assistant_name`, `business_category`,
  `business_description`, `welcome_message`, `business_hours` (sin contar
  espacios) y al menos un servicio. Se aplica en `clean()` y con un
  CheckConstraint en la base, que también cubre `update()`. Un borrador
  incompleto es válido, pero no queda listo.
- `save()` ejecuta `full_clean()`. `version` sube solo cuando cambia el
  contenido; pasar de `draft` a `ready` no la mueve.
- La base también aplica checks de `status`, `tone`, `language` y `version`.

## 4. Separación entre configuración, capacidades y credenciales

| Capa | Dónde vive |
|---|---|
| Datos del negocio ya existentes (nombre, dirección comercial, teléfono, WhatsApp público, zona horaria) | `Business`, `BusinessBillingProfile`, `BusinessBranding`: se reutilizan, no se copian |
| Información editable del negocio e instrucciones personalizadas | `ReceptionistConfig` |
| Reglas obligatorias del sistema (seguridad, no diagnosticar, no inventar disponibilidad, handoff determinístico) | código del agente; prevalecen sobre `custom_instructions` y `handoff_rules` |
| Capacidades (agenda, permisos, consumo IA) | suscripciones/entitlements, `has_agenda_access`, la política de IA |
| Credenciales y conexiones | `AgentCredential` (cifrada) y `AgentChannel` |

El modelo no tiene campos de capacidad, plan, cupo, canal, agente ni
credencial; un test verifica la lista de campos y que la única relación sea
con `Business`. Una configuración `ready` que diga «tenés agenda» no cambia
`has_agenda_access` (también cubierto por test).

## 5. Migraciones

`leads/0013_receptionist_config`: crea la tabla y 5 constraints, con
dependencias `leads/0012` y `business/0029`. No incluye migración de datos y
no crea configuraciones para los negocios existentes.

Validada sobre PostgreSQL 16 descartable (tmpfs): `migrate` completo desde
cero, rollback a `0012`, re-aplicación de `0013` y `makemigrations --check`
sin cambios pendientes. `sqlmigrate` confirma el CHECK de `ready` (`"services"
= '[]'::jsonb`).

## 6. Tests y resultados

`apps/leads/tests/test_receptionist_config_03a.py`, con 35 tests:

- **Creación y validación:** el default es un borrador v1; una configuración
  completa puede quedar lista; el contenido se recupera igual; los choices
  inválidos se rechazan en el modelo y en la base.
- **Configuración incompleta:** cada campo mínimo bloquea `ready`; los
  espacios cuentan como vacío; sin servicios no queda lista; la base rechaza
  `update(status='ready')` incompleto; vaciar una configuración lista falla.
- **Límites:** largo de los 9 textos (límite ok, límite+1 falla), carácter
  nulo, tamaño de las listas, forma de los elementos y duplicados.
- **Aislamiento y unicidad:** una configuración por Business (también con
  `bulk_create`); dos negocios independientes; Business inmutable; borrar un
  negocio borra solo su configuración.
- **Relaciones agente-negocio:** una instancia con dos negocios resuelve cada
  uno por su canal. Fallan con su error: instancia ajena (`channel_disabled`),
  `business_id` distinto (`business_mismatch`), canal inactivo o desconocido
  (`channel_disabled`) y negocio suspendido (`business_inactive`). Un canal
  sin configuración devuelve `None`.
- **Preservación:** un negocio nuevo no recibe configuración automática; la
  versión cuenta solo cambios de contenido; una instancia vieja no retrocede la
  versión; un guardado inválido no altera lo guardado.
- **Sin secretos ni capacidades:** sin campos prohibidos; sin datos
  duplicados de Business; secretos rechazados en textos y listas; texto común
  no se confunde con un secreto; `ready` no concede agenda.

| Corrida (PostgreSQL 16 descartable) | Resultado |
|---|---|
| `test_receptionist_config_03a` | 35/35 OK |
| `apps.leads` completo | 735/735 OK (sin fallas) |
| `manage.py check` | sin issues |

## 7. Riesgos y decisiones técnicas

- **D1, sin FK a AgentInstance:** el vínculo se deriva del canal, la misma
  regla que el receiver. Riesgo: un negocio sin canal tiene configuración pero
  ningún agente puede leerla. Es lo esperado hasta que se conecte el canal.
- **D2, una configuración por Business:** coherente con la suscripción
  `reception` por negocio. Varias recepcionistas por negocio requerirían otro
  diseño; no se agregó por una necesidad hipotética.
- **D3, horarios en texto libre:** `AppointmentSchedule` es la disponibilidad
  de la agenda de Turnos. Reutilizarlo acoplaría la recepcionista a la agenda
  (contrario a PROD-02H). Estructurarlo queda abierto si hace falta.
- **D4, rubro libre:** no existe un campo de rubro en Mi Rubro.
  `Business.service_type` y `billing.vertical` son productos de Mi Rubro, no
  rubros del comercio.
- **R1, concurrencia:** `version` se calcula en `save()` sin lock. Dos
  ediciones simultáneas producen «último gana» con versión correcta pero
  pierden un cambio. La API de PROD-03B debería exigir la versión esperada
  (optimistic lock).
- **R2, detección de secretos heurística:** es una barrera adicional, no
  sustituye la separación estructural (no hay campos de credenciales).
- **R3, prompt injection:** `custom_instructions` y `handoff_rules` son texto
  del negocio. El bot (PROD-03C o siguiente) debe componerlos debajo de las
  reglas del sistema y tratarlos como datos.
- **R4, sin Django admin ni UI:** por alcance, no se registra en el admin.
  Hoy solo se crea por shell o tests.
- **R5, `bulk_create` y `update()`:** saltean `full_clean()`. Las constraints
  de base cubren estados, choices y `ready`, pero no la forma del JSON ni los
  secretos. Todo camino de escritura de 03B debe pasar por `save()` o un
  serializer equivalente.

### Directiva de reutilización

- **Reutilizado:** `Business` (identidad, zona horaria, ciclo de vida y
  cascade), `BusinessBillingProfile` y `BusinessBranding` (dirección,
  contacto, WhatsApp público), `AgentChannel` como única fuente de la
  relación agente ↔ negocio, `resolve_channel` y los errores del receiver, el
  patrón de validación en `save()` de `LeadAgentState`, el patrón OneToOne de
  settings por negocio (`CommercialSettings`, `CustomerCommunicationSettings`)
  y las factories de `apps.leads.tests`.
- **Creado por necesidad:** `ReceptionistConfig`, porque ningún modelo
  existente guarda contenido conversacional del agente. `AgentInstance` es un
  deployment multinegocio, `AgentChannel` es una conexión y los settings
  existentes son de otros productos. También la función de lectura
  `receptionist_config_for_agent` (8 líneas sobre `resolve_channel`), que es
  la única forma de cubrir «relaciones inválidas agente-negocio» sin
  duplicar la regla del receiver.
- **Duplicaciones evitadas:** no se copiaron nombre, dirección, teléfono,
  WhatsApp ni zona horaria; no hay FK paralela a la relación del canal; no se
  reutilizó la agenda para horarios comerciales. Tampoco hay campos de
  capacidad que compitan con entitlements, ni almacenamiento de secretos fuera
  de `AgentCredential`. No se agregó señal de autocreación (a diferencia de
  `CommercialSettings`): la configuración solo existe si alguien la crea.

## 8. Commits y HEAD final

Commits sobre `c9085aa`: modelo y migración, tests, y este reporte.
Empujados a `origin/feat/recepcionista` sin force push. No se modificó el bot
ni se avanzó a PROD-03B.
