# PROD-09C1 — Control independiente de atención automática

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `cceddf1` · Bot
`ef5e329` sin cambios (leído con `git show`). Solo backend. Una migración de
campo; sin modelos ni endpoints nuevos.

## 1. Implementación

### Modelo

`ReceptionistConfig.automatic_attention_enabled` (`BooleanField`, default
`False`).
- **Independencia:** es independiente del contenido y de `status`. Se suma a
  `VERSIONED_FIELDS`, así que su cambio sube `version`.
- **Invariante, con doble protección:** habilitada implica lista.
  - `clean()` exige `is_ready`.
  - La constraint de DB `receptionist_config_attention_requires_ready` exige
    `enabled=False OR status='ready'`, y alcanza también a `update()`.
  - Junto con la constraint existente `ready ⇒ completa`, habilitada implica
    configuración completa.
- **Nunca se enciende sola:** ni al completar, ni al contratar, ni al vincular
  WhatsApp. La única escritura es explícita.

### Operaciones

Usan el mismo servicio (`services/receptionist_config.py`) y los mismos
endpoints.

| Operación | Resultado |
|---|---|
| Platform Admin (`superadmin` / `operations`), `PATCH .../clients/<id>/receptionist-config/` con `{expected_version, automatic_attention_enabled}` | Habilita o pausa. Booleano estricto: `1`, `"true"` o `null` dan 400 `validation_error`. `expected_version` obsoleta da 409 `version_conflict` |
| Habilitar sin `ready` | 400 `validation_error` en `automatic_attention_enabled` |
| Mismo `PATCH` con `status: ready` + `true` | Permitido: es explícito |
| Volver a `draft` con la atención habilitada (admin o comercio) | Se pausa **en la misma escritura**. Una sola versión nueva; auditoría `automatic_attention: paused_by_draft` |
| `draft` + `true` en el mismo `PATCH` | 400; no se aplica nada |
| Volver a `ready` | **No** la reactiva |
| Sin cambios (mismo valor) | Sin versión nueva ni auditoría |
| Comercio: `GET /api/v1/receptionist-config/` | Ve el campo |
| Comercio: `PATCH` con el campo | 400 `protected_fields` (`fields: ["automatic_attention_enabled"]`), sin escrituras |
| `POST` (crear), admin o comercio, con el campo | 400 `protected_fields`: crear nunca habilita |
| Pausa con suscripción `suspended`, `past_due` o `trialing` | Permitida: no depende del estado comercial |

**Auditoría.** Es la existente, `RECEPTIONIST_CONFIG_UPDATED`, en la misma
transacción y sin acciones nuevas, así que no hay migración de `accounts`.
- Todos los detalles incluyen `automatic_attention_enabled`.
- Los cambios de habilitación agregan `automatic_attention` con
  `enabled`, `paused` o `paused_by_draft`.
- Si la auditoría falla, la escritura se revierte.

### Protección de ejecución

En `authorize_ai_interaction`, `POST /api/internal/appointments/ai-usage/authorize/`:

1. Se resuelve la fuente actual (`get_ai_usage_and_source`).
2. Si es Recepcionista, se lee la configuración con `SELECT … FOR UPDATE`.
   El orden de locks es Business → config; la pausa solo bloquea la config,
   así que no hay deadlock.
3. Si no hay configuración o está pausada:
   `{"allowed": false, "reason": "automatic_attention_disabled"}`.
4. La verificación ocurre **antes** de leer recibos o abrir sesión:
   - Un replay de una interacción ya autorizada también se rechaza.
   - Tampoco se reutiliza una ventana de 24 h abierta.
   - No se crean sesiones, recibos ni cargos.
5. Sesiones, recibos y cargos anteriores quedan intactos. Al reanudar, el
   replay vuelve a ser aceptado con la misma sesión (`created: false`).

**Turnos IA (`appointments_ai`) no se controla.** La verificación está
condicionada a `_is_reception(current_source)`. Una configuración pausada o
inexistente en un negocio con Turnos IA no lo bloquea.

**La atención humana no cambia.** El receptor (`lead.sync`), las derivaciones,
la toma de conversación y los mensajes de recepción no consultan el campo.

## 2. Contrato con el agente (PROD-03C)

Se agrega una clave **aditiva** en el bloque `config`, `contract_version`
sigue en 1:

```json
"config": {
  "status": "ready",
  "version": 4,
  "updated_at": "…",
  "missing_for_ready": [],
  "content": { "…": "…" },
  "automatic_attention_enabled": false
}
```

- `status` sigue siendo el real (`ready`, `draft` o `missing`). Con la
  configuración lista y pausada se entrega `ready` con contenido: **no se
  simula borrador**.
- Con `missing` o `draft`, la clave vale `false`.

### Compatibilidad con el bot `ef5e329`

- **Parser de configuración** (`receptionist-config.ts`). `hasKeys` exige las
  claves conocidas y **acepta claves extra** en `config`. La respuesta nueva
  es válida para el bot actual, que ignora la clave.
- **Autorización** (`http-mirubro.transport.ts` y
  `ai-usage-observability.ts`). Una negativa con un `reason` desconocido se
  normaliza a `invalid_authorization_response`. El controller la trata como
  `AIUsageBlockedError`.
  - El paciente recibe `FALLBACK_REPLY`: «tuve un inconveniente para procesar
    tu mensaje…».
  - **No** hay derivación a humano ni lead marcado como
    `agent_handoff_required`.
  - No hay consumo.
  - Es el mismo comportamiento que hoy tiene `hard_cap_reached`.

**Consecuencia.** Con Mi Rubro nuevo y el bot actual, una configuración
`ready` pausada **no consume ni responde con IA**, pero el paciente recibe el
mensaje genérico de inconveniente en lugar de pasar a humano. La seguridad
comercial está garantizada; la experiencia no es la buena.

### Extensión mínima del bot (PROD-09C2, no hecha)

1. **Parser:** leer `config.automatic_attention_enabled` como booleano
   **obligatorio**. Si falta o no es booleano, la respuesta es inválida, a
   prueba de fallos.
2. **Controller:** con `ready` y `automatic_attention_enabled=false`, seguir
   el mismo camino que `draft` en `configUnavailable` (`toHuman`):
   `agent_handoff_required` y mensajes no atendidos. No llamar a
   `authorize` ni a OpenAI.
3. **`REASONS`:** agregar `automatic_attention_disabled`, como defensa si una
   pausa ocurre entre la lectura de la configuración y la autorización.

### Orden seguro de despliegue

1. **Mi Rubro 09C1.**
   - Migración `leads/0016`: todas las configuraciones quedan pausadas.
   - Con el bot actual nadie consume IA de Recepcionista. Un canal ya vivo
     respondería con el mensaje genérico.
   - Hoy no hay clientes de Recepcionista en producción (PROD-09A), así que la
     ventana no afecta a nadie.
2. **Bot 09C2** (requiere la clave). Las configuraciones pausadas pasan a
   derivarse a humano.
3. **Habilitar comercio por comercio** desde Platform Admin.

**No desplegar el bot 09C2 antes que Mi Rubro 09C1.** El bot nuevo, con el
campo obligatorio, rechazaría la respuesta vieja sin la clave. Todas las
conversaciones quedarían como no atendidas: es seguro, pero no hay servicio.

## 3. Seguridad

- **Escritura solo de Platform Admin**, con los roles existentes del endpoint
  admin. El comercio no puede ni encender ni apagar.
- **Booleano estricto, `expected_version` y auditoría** en la misma
  transacción.
- **Habilitar exige lista** en dos niveles: `clean` y constraint de DB.
- **La pausa se respeta** aunque haya replays o ventanas abiertas, y una
  autorización en curso espera el lock de una pausa que se está aplicando.
- **Aislamiento:** pausar un negocio no afecta a otros ni a otros productos.
- **No se tocaron** canales, autorizaciones WhatsApp, suscripciones ni el
  frontend.

## 4. Migración

`leads/0016_receptionist_config_automatic_attention`:
- `AddField` con `BooleanField(default=False)`. Las filas existentes quedan en
  `False`.
- `AddConstraint`.
- Sin `RunPython` ni `RunSQL`, y sin migraciones en otras apps.

Es reversible: hacia atrás quita la constraint y el campo.

## 5. Tests

Corridos sobre PostgreSQL 16 descartable (tmpfs, `fsync=off`) y Redis
descartable, en una red Docker propia.

**Nuevo, `apps/leads/tests/test_automatic_attention_09c1.py` (27 tests):**
- **Modelo:** default deshabilitado en todos los caminos de creación;
  habilitar exige lista (en `clean` y en DB); el campo mueve la versión.
- **Habilitar y pausar:**
  - versión y auditoría;
  - un no-op no escribe;
  - booleano estricto;
  - 409;
  - incompleta o borrador rechazadas;
  - `ready` + `true` en el mismo `PATCH`;
  - `ready → draft → ready` (pausa atómica, sin reactivar);
  - `draft` + `true` rechazado;
  - el comercio pasa a borrador y pausa;
  - pausa con `suspended`, `past_due` y `trialing`;
  - rollback ante una falla de auditoría;
  - aislamiento.
- **Comercio y roles:**
  - el comercio lee y no escribe;
  - crear nunca acepta el campo;
  - `operations` puede; `support_agent` y `content_admin` no.
- **Autorización IA:**
  - pausada o sin configuración: rechazo explícito sin sesiones, recibos ni
    cargos;
  - los replays y la ventana abierta no eluden la pausa, el historial se
    conserva y al reanudar se reutiliza la sesión;
  - otros negocios siguen;
  - Turnos IA no se controla.
- **Contrato con el agente:** `ready` pausada mantiene `ready` y contenido,
  con la clave en `false`; `draft` la informa en `false`.
- **Atención humana:** `lead.sync` con derivación funciona con la atención
  pausada.
- **Migración:** las operaciones de 0016 (campo con default `False`,
  constraint, sin pasos de datos) y la columna aplicada `NOT NULL boolean`.
  - La prueba de datos con `MigrationExecutor` (migrar hacia atrás, crear
    filas, migrar) no se pudo usar. El flush de `TransactionTestCase` falla al
    truncar `business_business` por una FK de `treasury_expensetemplate`, que
    es un problema del entorno de tests y no de esta migración.
  - El relleno con `False` es el comportamiento estándar de `AddField` con
    default.

**Tests existentes adaptados** (solo fixtures y expectativas):
- **Suites de autorización de Recepcionista** (02E1, 02E2A, 02E2B y 02E4A):
  crean una configuración habilitada con el factory compartido
  `enable_reception_attention`, para seguir probando lo mismo que antes.
- **03C:** la clave nueva en `CONFIG_KEYS` y en `missing`.
- **03B:** la clave nueva en los detalles de auditoría.
- **03A:** la guarda contra campos «enabled» admite solo este campo.

| Corrida | Resultado |
|---|---|
| 09C1 | 27/27 OK |
| Antes de adaptar: suites de configuración y consumo IA con el cambio | 35 fallas y 3 errores, todos por falta de configuración habilitada o por la clave nueva (esperado) |
| `apps.leads` + consumo IA (02E1, 02E2A, 02E2B, 02E3A, 02E3B) + Turnos IA (S8H, S8I, complimentary, S7B) | 1087/1087 OK |
| `manage.py check` | sin issues |
| `makemigrations --check` | No changes detected |

Las suites de Turnos IA pasaron **sin cambios** antes y después de adaptar los
fixtures.

## 6. Riesgos

- R1: entre el despliegue de 09C1 y el de 09C2, una configuración lista y
  pausada, con canal vivo, responde con el mensaje genérico en lugar de
  derivar a humano (§2). Mitigación: desplegar 09C2 inmediatamente después,
  o no tener canales vivos en esa ventana.
- R2: con la suscripción **cancelada**, el endpoint admin de configuración
  devuelve 404 (regla de PROD-03B/08C), así que no se puede pausar. La IA ya
  está bloqueada por la falta de fuente comercial, pero el campo puede quedar
  en `true`. Si se vuelve a otorgar Recepcionista, la atención quedaría
  habilitada sin confirmación nueva. Si se quiere evitar, en 09C2 o en un
  slice comercial se puede pausar al cancelar.
- R3: el frontend todavía no muestra ni opera el campo. El tipo no lo conoce y
  el formulario no lo envía, así que no hay rotura. El interruptor y su
  reflejo en «Preparación del agente» quedan para un slice de frontend.
- R4: la prueba de datos real de la migración quedó cubierta solo
  estructuralmente (§5).
- R5: el checkout local del bot sigue en `e8b70fb`, anterior a `ef5e329`
  (D3 de PROD-09A).

## 7. HEAD

`56b85d9` (implementación, migración y tests) y este reporte, empujados a
`origin/feat/recepcionista` sin force push. No se avanzó a PROD-09C2.
