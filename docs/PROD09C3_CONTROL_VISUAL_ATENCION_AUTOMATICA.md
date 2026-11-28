# PROD-09C3 — Control visual de atención automática

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `a1a2b74` · Bot
`de7e932` sin cambios. Solo frontend (`apps/web`). Sin backend, endpoints,
modelos ni dependencias.

## 1. Implementación

### Platform Admin: «Preparación del agente»

Nuevo bloque **«Atención automática»**: `Switch` + `StatusBadge` (Habilitada,
Pausada o Estado desconocido).

- **Fuente de verdad:** únicamente `config.automatic_attention_enabled`, de la
  query de configuración que el bloque ya tenía. El checklist informa, nunca
  autoriza.
- **Escritura:** el PATCH admin existente (`receptionistConfigAdapter`,
  target `platform_admin`), con **solo**
  `{ expected_version, automatic_attention_enabled }`. No hay mutaciones
  paralelas.
- **Confirmación:** tanto habilitar como pausar pasan por el `Modal`
  existente, con el nombre del comercio («Clínica Sol (ID 7)»). Cancelar no
  envía nada.
- **Sin estado optimista:** el interruptor refleja el backend. No cambia
  hasta que llega la respuesta, que se guarda con `setQueryData` en la misma
  query que lee el formulario. Mientras viaja, el interruptor y los botones
  del modal quedan deshabilitados.
- **Condiciones:**
  - habilitar exige configuración `ready`; si no, el interruptor se
    deshabilita y se explica por qué;
  - las condiciones comerciales o técnicas pendientes se informan, pero no
    bloquean, porque Mi Rubro controla el consumo en cada interacción;
  - pausar está permitido con consumo agotado o suscripción suspendida;
  - si el campo falta, el estado es desconocido: no se puede operar y nunca
    se asume habilitada.
- **Errores:**
  - 403: texto propio de Platform Admin;
  - 400 `validation_error`: «tiene que estar lista»;
  - otros: el `detail` del backend o un mensaje genérico;
  - 409: mensaje y botón **«Recargar estado»**, sin reintento automático.
- **Textos:** «Solo se activa desde acá: nunca al completar la
  configuración, contratar el servicio ni vincular WhatsApp. Volver a
  borrador también la pausa; marcarla otra vez como lista no la reactiva.
  Habilitada no significa que el agente esté conectado ni respondiendo.»

### Checklist actualizado

Se quitaron los avisos de 09B («Puede haber atención automática» y «La
atención automática empieza sola… no hay un interruptor independiente»).

Las condiciones se agrupan en:
1. **Cuenta y configuración** (owner y configuración «lista»);
2. **Estado comercial** (acceso y política IA);
3. **Conexiones (estado local)** (canal, autorización e instancia);
4. **Atención automática**, el bloque nuevo.

Se mantiene el recuadro «No verificable desde Mi Rubro».

### Comercio: «Mi agente»

Dentro de la tarjeta de estado del formulario compartido, solo para el
target `business`, se agregó «Atención automática» con su badge, de solo
lectura y sin interruptor.

- **Habilitada o Pausada:** «La habilita o la pausa el equipo de Mi Rubro.»
- **Estado desconocido:** si falta el campo.
- **Aviso fijo:** volver a borrador la pausa y marcarla como lista no la
  reactiva.
- **Edición:** la edición de la configuración no cambia. El comercio nunca
  envía el campo; el backend ya lo rechaza (`protected_fields`).

**Modal «¿Volver a borrador?»** (los dos targets). Ahora dice que volver a
borrador también pausa la atención automática y que marcarla otra vez como
lista no la reactiva. El texto anterior («deja de atender hasta que la
vuelvas a marcar como lista») era incorrecto desde 09C1.

## 2. Componentes reutilizados

- **Componentes de UI:** `Switch`, `Modal` y `Button` (`components/ui`);
  `SectionCard` y `StatusBadge` (`components/admin`).
- **Bloque y datos:**
  - `receptionist-admin-card.tsx` y su único `Providers`;
  - `useReceptionistConfig` y su `adapter`, que ahora se pasan a la
    preparación;
  - `receptionistConfigAdapter` y `errorCode`;
  - la query key compartida.
- **Formulario compartido:** la misma pieza para comercio y admin.

**Nuevo:**
- `attentionStateOf` y `ATTENTION_LABELS`, exportados del formulario y
  usados por las dos pantallas;
- `AttentionControl`, local de la sección de preparación;
- `AttentionLine`, local del formulario;
- `automatic_attention_enabled?` en los tipos.

## 3. Consistencia del versionado

- **Una sola query.** El interruptor y el formulario leen la misma clave
  (`['reception','receptionist-config','platform_admin', id]`). El test lo
  verifica: una sola consulta de configuración por cliente.
- **Interruptor con cambios sin guardar en el formulario.**
  - El formulario guarda solo **ediciones de contenido**, sobre el snapshot
    del servidor.
  - Un PATCH exitoso del interruptor parte de la misma `expected_version` y
    solo cambia el flag, así que el contenido base no cambia: las ediciones
    locales siguen, no hay conflicto.
  - El siguiente «Guardar cambios» envía solo el contenido editado con la
    versión nueva (tests: `expected_version` 4, luego 5).
- **Protección nueva en el formulario.**
  - Si el **contenido** del snapshot cambia mientras hay cambios sin guardar
    y no es una escritura propia, el formulario entra en su estado de
    conflicto existente («Otra persona guardó cambios…»), con «Guardar»
    deshabilitado. El ejemplo típico: «Recargar estado» tras un 409 trae
    cambios de otra persona.
  - Las ediciones se conservan y la versión nueva **nunca** se adopta en
    silencio para guardar encima.
  - Un cambio solo de versión o de atención automática no dispara el
    conflicto.
- **Draft y ready desde el formulario.** Las respuestas actualizan la misma
  query, así que el interruptor refleja la pausa automática del backend al
  volver a borrador y sigue en pausa al volver a «lista».
- **Cambio de cliente:** las claves son por cliente y el bloque se remonta
  por `key`, así que no se mezclan estados ni versiones.

## 4. Tests

- **Platform Admin**, `components/admin/__tests__/receptionist-attention-control.test.tsx`
  (16 casos, detalle del cliente completo):
  - estado inicial pausado, sin afirmaciones de conectividad;
  - habilitar: modal con el comercio, sin PATCH antes de confirmar, cuerpo
    exacto, botones y switch bloqueados mientras viaja, y cambio recién con
    la respuesta;
  - pausar con suscripción suspendida;
  - cancelar el modal;
  - borrador: no habilitable;
  - condiciones pendientes: informadas, sin bloquear;
  - 403, 400 y 500;
  - 409: sin reintento, recarga explícita;
  - formulario con cambios pendientes y guardado sobre la versión nueva;
  - contenido ajeno bajo cambios pendientes: conflicto, sin adoptar en
    silencio;
  - `ready → draft → ready` sin reactivación, con la versión compartida;
  - estado desconocido;
  - cambio de cliente;
  - una sola consulta de configuración.
- **Comercio**, `features/reception/__tests__/receptionist-attention-merchant.test.tsx`
  (5 casos):
  - Habilitada y Pausada, sin interruptor;
  - estado desconocido;
  - guardar contenido sin enviar el flag;
  - borrador que pausa y «lista» que no reactiva.
- **Actualizados:**
  - `receptionist-readiness.test.tsx`: sin el aviso de activación
    automática;
  - `receptionist-config-form.test.tsx`: el texto nuevo del modal de
    borrador.
- **Comprobación:** con la protección de contenido del formulario
  desactivada, el test de conflicto falla.

| Corrida | Baseline `a1a2b74` | Final |
|---|---|---|
| Dirigida: los 2 suites nuevos | — | 21/21 |
| Regresión: `app/admin`, `components`, `lib`, `features/reception`, `features/leads`, `app/app/recepcionista` (configuración, consumo, métricas, conexiones y preparación) | 588/590 | 609/611 |
| TypeScript | 4 errores preexistentes (`google-place-autocomplete.tsx`) | los mismos 4 |
| ESLint (archivos tocados) | — | sin warnings |

Las 2 fallas de la regresión son las preexistentes de
`admin/notificaciones-content.test.tsx`.

## 5. Riesgos

- R1: no se verificó en un navegador real (diseño del bloque y del modal).
- R2: la protección de conflicto del formulario compara el contenido
  serializado. Si el backend normalizara el contenido de otra forma (por
  ejemplo, el orden de claves en `services`), podría dar un conflicto
  conservador. Nunca una sobrescritura.
- R3: con una suscripción cancelada, el bloque Recepcionista se oculta (404
  de dominio), así que no se puede pausar desde el panel. Es el riesgo R2 de
  09C1 y no cambió.
- R4: el comercio ve el estado al cargar la pantalla. Un cambio hecho por
  Platform Admin no se refleja hasta recargar, porque no hay polling.

## 6. HEAD

`f8e527a` (implementación y tests) y este reporte, empujados a
`origin/feat/recepcionista` sin force push. No se avanzó a PROD-09D.
