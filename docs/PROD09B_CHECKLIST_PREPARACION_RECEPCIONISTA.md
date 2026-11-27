# PROD-09B — Checklist de preparación de Recepcionista IA

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `f3c188c` · Bot
`ef5e329` sin cambios. Solo frontend; el backend solo se leyó. Sin endpoints,
modelos, migraciones ni dependencias.

## 1. Resultado

**«Preparación del agente»** es la primera sección del bloque Recepcionista IA
en `/admin/clientes/[clienteId]`. Es un resumen **derivado**: no tiene estado
propio, no es un wizard y no persiste nada.

- **Datos:**
  - la query de configuración que el bloque ya tiene (se pasa por prop);
  - `useAdminAIUsage(businessId)` y `useAdminWhatsAppConnections(businessId)`,
    con las mismas query keys que las secciones de consumo y conexiones;
  - el `owner` que ya trae el detalle del cliente.
- **Sin requests nuevos:** usa el mismo `Providers` (un `QueryClient`). React
  Query sirve las dos lecturas con una sola consulta por endpoint, y el test lo
  verifica: cada endpoint del bloque se pide una vez.
- **Sin reglas propias:** traduce a cinco estados lo que el backend ya
  calculó: `diagnosis.code`, `summary.status`, `config.status` y
  `local_status`.

## 2. Reutilizado

- **Componentes de `/admin`:** `SectionCard` y `StatusBadge`.
- **Bloque:** `receptionist-admin-card.tsx`, con su `Providers` y su regla de
  ocultamiento por el 404 de dominio.
- **Hooks:** `useAdminAIUsage` y `useAdminWhatsAppConnections`
  (`features/reception/hooks.ts`), y la query de `useReceptionistConfig` del
  bloque.
- **Tipos:** `AdminMember` (`lib/admin/types.ts`) y los tipos de
  `features/reception/types.ts`.
- **Errores:** `ApiError`, para distinguir 403 de otros errores.

**Nuevo:**
- `components/admin/receptionist-readiness-section.tsx`.
- En el bloque, la prop `owner`, que se pasa desde `cliente-detail-content.tsx`
  (una línea).

## 3. Condiciones y estados

Estados: **Cumplida**, **Verificación parcial**, **Pendiente**,
**Bloqueada** y **Desconocida**. Si un dato está cargando, falló o no tiene
acceso (403), la condición queda **Desconocida** con su motivo; nunca
cumplida.

| Condición | Fuente | Cómo se resuelve |
|---|---|---|
| Cuenta owner y membership | `client.owner` (membership activa) | Con owner: **parcial** («no se verifica si vinculó Google ni si ya ingresó»). Sin owner: pendiente. Nunca cumplida |
| Acceso comercial vigente | `ai-usage.diagnosis.code` y `source_subscription` | Ver detalle abajo |
| Política IA y cupo disponible | `ai-usage.summary.status` | `available` → cumplida (quedan N de M). `exhausted`, `suspended`, `not_contracted`, `ambiguous_source` → bloqueada. `policy_not_configured` → pendiente. `unavailable`, sin `summary` o un valor no reconocido → desconocida |
| Configuración «lista» | `config.status` y `missing_for_ready` | `ready` → cumplida. `draft` → pendiente (faltan N campos). Inexistente → pendiente |
| Canal WhatsApp activo | canal elegido: `is_active` | Activo → cumplida. Desactivado → bloqueada. Sin canales → pendiente |
| Autorización local vigente | canal elegido: `local_status` | `credential_ready` → **parcial** («vigente en Mi Rubro; no verificada con Meta»). Faltante o sin WABA → pendiente. Revocada, inválida, vencida o inconsistente → bloqueada. Canal desactivado o sin canal → desconocida (no evaluada). Un estado no reconocido → desconocida |
| Instancia asignada y habilitada | canal elegido: `agent_instance.is_enabled` | Habilitada → cumplida. Deshabilitada → bloqueada. Sin canal → desconocida |

**Acceso comercial**, según `diagnosis.code`:
- **Bloqueada:** diagnósticos de ciclo de vida (sin suscripción, cancelada,
  suspendida, bonificación vencida, negocio inactivo, etc.).
- **Pendiente:** `benefit_not_started`.
- **Cumplida:** `ok` y los diagnósticos posteriores al ciclo de vida
  (política, cupo, medición), porque significan que el acceso comercial pasó.
- **Desconocida:** `ambiguous_ai_source`, `resolution_error` o un código no
  reconocido.

**Un solo canal.** Canal, autorización e instancia se evalúan siempre sobre el
**mismo** canal. Se elige el primero que cumpla, en este orden:

1. `credential_ready`;
2. `agent_instance_disabled` (credencial vigente pero instancia deshabilitada);
3. el primer activo;
4. el primero de la lista.

La sección indica qué canal evaluó («Canal evaluado: Phone Number ID …») y
cuántos hay. Nunca combina el estado favorable de un canal con el de otro.

**Resumen y avisos fijos:**
- La línea de resumen dice «N de 7 condiciones sin cumplir o sin verificar».
  Si todas están cumplidas o parciales, dice «Condiciones locales cumplidas.
  Puede haber atención automática: lo que no se verifica desde Mi Rubro sigue
  pendiente de comprobar.». Nunca dice «conectado», «operativo» ni «activado».
- Un recuadro **«No verificable desde Mi Rubro»** lista:
  - conectividad real con Meta;
  - el proceso del agente online;
  - los flags del entorno;
  - una conversación real de prueba.
- Un aviso explica que la atención automática empieza sola cuando se cumplen
  las condiciones técnicas y comerciales, que no hay un interruptor
  independiente, y que para cortarla hay que volver a «Borrador».

## 4. Revisión de activación (solo lectura)

Busqué un campo o mecanismo, por comercio, para habilitar o pausar la atención
automática que sea independiente de `ReceptionistConfig.status`, de la
suscripción, de la autorización y de la instancia compartida.

| Candidato | Por comercio | Sirve como pausa | Motivo |
|---|---|---|---|
| `AgentChannel.is_active` | Sí, por canal | **No** | Con el canal inactivo, `resolve_channel_by_phone` y la entrega de la credencial fallan. El agente rechaza el webhook en forma definitiva y los mensajes se descartan, sin lead ni derivación a humano. Además, reactivar no tiene operación: el modelo trata la reactivación como reasignación, y `provision_agent` no desactiva ni reactiva. Sirve como corte de emergencia, no como pausa |
| `Business.status` | Sí | No | Es comercial y global para todos los productos. El receptor lo filtra (`ALLOWED_BUSINESS_STATUSES`) |
| `ConversationControl` / takeover | Por conversación | No | Pausa una conversación, no el comercio |
| `AgentInstance.is_enabled` | No (compartida) | No | Corta a todos los comercios de la instancia |
| `ReceptionistConfig` | Sí (1:1) | No hay campo | Solo existen `status` (`draft`/`ready`), contenido y `version` |

**Conclusión:** hoy no existe ningún mecanismo reutilizable. El único corte por
comercio que mantiene la recepción de mensajes y la derivación a humano es
volver la configuración a borrador. Eso tiene un costo: mezcla «contenido
completo» con «encendido».

### Propuesta mínima para PROD-09C

Un booleano **`automatic_attention_enabled`** en `ReceptionistConfig`,
`default=False`.

- **Por qué ahí:** es 1:1 con el Business y ya tiene versionado optimista,
  auditoría estricta, endpoints de comercio y admin, y entrega al agente.
- **Entrega al agente:** en `_config_block` (03C), la configuración se entrega
  como `ready`, con contenido, **solo si** `is_ready` **y**
  `automatic_attention_enabled`. Si no, sale como `draft` y sin contenido, la
  misma forma que hoy.
  - **El agente no cambia:** con `ef5e329` ya trata draft o faltante como
    `agent_handoff_required` con lead para recepción, y el contrato v1 estricto
    no cambia.
  - **Defensa adicional, opcional:** que `ai-usage/authorize` también lo
    rechace.
- **Escritura:** solo Platform Admin, en un principio. Se envía con
  `expected_version`, en el mismo `PATCH` admin y como campo nuevo de la lista
  de escritura. En el frontend, un `Switch` existente con `Modal` de
  confirmación, en «Preparación del agente».
- **Migración:** `leads/00xx`, con default `False`.
  - Una configuración `ready` que ya exista quedaría apagada al desplegar. Hay
    que decidir si se migra en `True` (mantiene el comportamiento actual) o en
    `False` (requiere encenderla a propósito).
- **Efecto:** resuelve R1 de PROD-09A. Pasar a «lista» deja de significar
  «en producción», y el encendido y la pausa son explícitos y reversibles por
  comercio.

## 5. Tests

`components/admin/__tests__/receptionist-readiness.test.tsx`: 12 casos, con el
bloque completo y sin simular secciones.
- **Cliente recién creado:** owner parcial, configuración y canal pendientes,
  autorización e instancia desconocidas, «4 de 7».
- **Owner y configuración:** sin owner; configuración inexistente, draft y
  ready.
- **Consumo:** disponible, agotado y suspendido.
- **Canal:** inactivo y con credencial vigente (verificación parcial).
- **Varios canales:** uno activo sin autorización y otro inactivo autorizado.
  No se combinan; se evalúa uno solo.
- **Instancia deshabilitada** sobre el mismo canal con credencial vigente.
- **Desconocidos:** diagnóstico y estado no reconocidos, y conexiones con 403.
- **Carga:** mientras carga, las condiciones quedan desconocidas.
- **Sin afirmaciones de conexión:** todo local en verde, sin conexión en el
  resumen ni en los badges, con la lista de lo no verificable y el aviso de
  activación automática.
- **Sin requests nuevos:** una consulta por endpoint en todo el bloque.
- **Cambio de cliente** sin arrastrar datos.

Las suites de 08C, 08D y 08E2 simulan la sección nueva, como ya hacían entre
sí.

| Corrida | Baseline `f3c188c` | Final |
|---|---|---|
| Dirigida: `receptionist-readiness` | — | 12/12 |
| Regresión: `app/admin`, `components`, `lib`, `features/reception`, `features/leads`, `app/app/recepcionista` | 576/578 | 588/590 |
| TypeScript | 4 errores preexistentes (`google-place-autocomplete.tsx`) | los mismos 4 |
| ESLint (archivos tocados) | warnings de íconos sin usar en `cliente-detail-content.tsx` | los mismos; archivos nuevos limpios |

Las 2 fallas de la regresión son las preexistentes de
`admin/notificaciones-content.test.tsx`.

## 6. Riesgos

- R1: no se verificó en un navegador real.
- R2: la clasificación de `diagnosis.code` en acceso comercial sigue el orden
  de `_diagnosis` (PROD-02E3B). Si el backend cambia ese orden o agrega
  códigos, un código nuevo queda «Desconocida», nunca cumplida.
- R3: con varios canales, la sección evalúa uno y remite a «Conexiones
  WhatsApp» para el resto. Un segundo canal en mal estado no se refleja en el
  resumen.
- R4: hasta 09C, el aviso de activación automática describe un riesgo que
  sigue existiendo: volver a «Borrador» es el único corte reversible.
- R5: el bot local sigue en `e8b70fb`, anterior a la base (D3 de PROD-09A).

## 7. HEAD

Un commit con la sección y sus tests, y otro con este reporte, empujados a
`origin/feat/recepcionista` sin force push. No se avanzó a PROD-09C.
