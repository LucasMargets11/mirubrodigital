# TURNOS RECEPCIONISTA 04 — polish visual, ritmo y legibilidad

## Alcance

Demo pública en `/turnos#recepcionista-ia`. Se conserva el loader dinámico,
IntersectionObserver, shell sin JavaScript y arranque manual. Este slice
reemplaza las decisiones de altura y sincronización descritas en el slice 03;
no cambia los datos ni el resultado del escenario.

## Layout y scroll

- Inteligencia y MiRubro ya no tienen altura fija ni `overflow-y-auto`.
  Crecen con el documento y muestran completos los datos, proceso y actividad.
- Desde 1280 CSS px se muestran las tres columnas, con mayor ancho para el
  chat. Entre 768 y 1279 px, el chat ocupa la primera fila y los paneles
  comparten la siguiente. En móvil se apilan chat, Inteligencia y MiRubro.
- El chat conserva una altura estable de 660 px en móvil, 720 px en tablet y
  960 px en desktop. Solo su historial puede desplazarse: se evita así una
  conversación móvil excesivamente alta y se mantienen cabecera y composer
  visibles. A 1440 px, los ocho mensajes caben sin scroll interno.
- La toolbar reserva espacio estable para el escenario y su estado. Los
  controles compactos comparten fila en móvil. Se corrigió un salto de 22 px
  detectado a 320 px al pasar de idle a completed.
- El placeholder comparte superficies, proporciones y layout con la demo.

## Identidad visual

- **Inteligencia:** superficie violeta, icono IA, badge de estado con dot,
  campos pendientes/detectados diferenciados, checks, progreso de mayor
  contraste y paso activo resaltado.
- **Chat:** fondo suave de mensajería, burbujas blancas para Lucía y teal para
  el recepcionista, identificación de emisor, más separación y cabecera con
  nombre, teléfono, estado y badge Simulación. Composer deshabilitado con
  explicación visible de que no se envían mensajes.
- **MiRubro:** superficie emerald, cards blancas independientes, badges de
  Identificado/Nuevo/Calificado/Convertido/Pendiente/Confirmada y feed legible
  con iconos y estado textual. La preferencia continúa visible al convertir
  el lead.
- Los datos y estados nuevos tienen entradas cortas; las cards operativas
  reciben un highlight emerald de 950 ms. No se agregan timers de animación
  ni estado React paralelo. CSS respeta `prefers-reduced-motion`.
- Al pausar, el indicador del chat dice En pausa y deja de animarse.

## Ritmo y scheduler

Se reutiliza el único scheduler recursivo del motor:

1. Cliente: `900 + min(longitud × 18, 900)` ms antes del mensaje.
2. Recepcionista: typing visible durante
   `1400 + min(longitud × 24, 1800)` ms.
3. El mensaje aparece y desaparece el typing.
4. Después de **500 ms**, se actualizan juntos Inteligencia y MiRubro con
   los eventos declarativos existentes.
5. Se dejan **700 ms** de lectura antes del siguiente paso.

Los overrides opcionales `delayMs`/`typingMs` siguen siendo válidos; el fixture
público usa ahora el cálculo por longitud. La duración observada es de unos
**26 segundos**, frente al avance acelerado previo.

Pausar conserva la acción pendiente y el tiempo restante, también durante
typing, lectura o los 500 ms previos al snapshot. Reanudar no reinicia la
demora completa ni pierde eventos. Reiniciar/repetir limpian el estado; al
completar o desmontar no quedan timers.

## Archivos de implementación

- [Sección pública](<../../apps/web/src/app/(marketing)/turnos/receptionist-demo-section.tsx>).
- [Layout](../../apps/web/src/features/appointments/receptionist-sandbox/sandbox-layout.tsx).
- [Toolbar y controles](../../apps/web/src/features/appointments/receptionist-sandbox/receptionist-sandbox.tsx).
- [Chat](../../apps/web/src/features/appointments/receptionist-sandbox/conversation-panel.tsx).
- [Inteligencia](../../apps/web/src/features/appointments/receptionist-sandbox/intelligence-panel.tsx).
- [MiRubro](../../apps/web/src/features/appointments/receptionist-sandbox/mirubro-panel.tsx).
- [Placeholder](../../apps/web/src/features/appointments/receptionist-sandbox/sandbox-placeholder.tsx).
- [Motor](../../apps/web/src/features/appointments/receptionist-sandbox/simulation-engine.ts).
- [Fixture](../../apps/web/src/features/appointments/receptionist-sandbox/simulation-data.ts).
- [Tests del motor](../../apps/web/src/features/appointments/receptionist-sandbox/__tests__/simulation-engine.test.ts).
- [Tests de UI](../../apps/web/src/features/appointments/receptionist-sandbox/__tests__/receptionist-sandbox.test.tsx).
- [Microanimaciones](../../apps/web/src/styles/globals.css).

## Validación frontend

| Validación                                                 | Resultado final                  |
| ---------------------------------------------------------- | -------------------------------- |
| Sandbox, motor, loader y landing pública                   | 42 tests, 4 archivos, exit 0     |
| `npm --prefix apps\web run type-check`                     | PASS, exit 0                     |
| ESLint focal del sandbox y sección pública                 | PASS, exit 0                     |
| Prettier focal de componentes, motor, fixture, tests y CSS | PASS, exit 0                     |
| `npm --prefix apps\web run build`                          | PASS, exit 0; `/turnos` estático |

Se agregaron tests de delays mínimos/máximos y duración total, separación
mensaje/snapshot, pausa durante procesamiento y typing, y ausencia de
XMLHttpRequest/escrituras en Storage. Se conservan las comprobaciones de
fetch, polling, WebSocket, un solo timer, restart, repeat y cleanup.

Durante una corrida simultánea con build, el test del import dinámico superó
su timeout de 1 segundo; la corrida final sin esa contención pasó sin cambiar
el test. Un rebuild encontró un error transitorio de `next/font/google` en
Turbopack; al limpiar únicamente el fetch-cache generado, el build estándar
pasó. No se cambiaron fuentes, configuración ni dependencias. Permanecen los
warnings existentes de múltiples lockfiles, middleware y Browserslist.

## Navegador real / responsive

Build de producción servido con `next start --port 3105`, readiness HTTP 200.
Harness local reproducible con Edge headless, CDP y Node nativo, sin instalar
paquetes. `deviceScaleFactor=1`; los cinco valores de `innerWidth` coinciden
exactamente con los anchos solicitados.

Para cada ancho se verificaron idle, parcial, pausa/reanudación y completed:
los tres paneles están presentes, no hay descendientes fuera del sandbox,
no hay overflow horizontal y el chat conserva altura **y posición**.

Medidas completed en CSS px: `clientHeight / scrollHeight` para paneles e
historial; `scrollWidth / clientWidth` para documento y sandbox.

| Ancho | Documento   | Sandbox     | Inteligencia | MiRubro   | Historial chat |
| ----- | ----------- | ----------- | ------------ | --------- | -------------- |
| 320   | 305 / 305   | 239 / 239   | 908 / 908    | 809 / 809 | 395 / 972      |
| 375   | 360 / 360   | 294 / 294   | 872 / 872    | 809 / 809 | 466 / 904      |
| 768   | 753 / 753   | 663 / 663   | 872 / 872    | 809 / 809 | 548 / 722      |
| 1024  | 1009 / 1009 | 887 / 887   | 872 / 872    | 809 / 809 | 548 / 722      |
| 1440  | 1425 / 1425 | 1278 / 1278 | 872 / 872    | 809 / 809 | 788 / 788      |

- Delta idle→completed de altura y posición del chat: **0 px**, en los cinco
  anchos.
- Duración real medida, excluyendo la pausa manual: **26,11–26,23 s**.
- Cada corrida termina con ocho mensajes, cinco datos y reserva Confirmada.
- **0 requests durante la simulación**, en los cinco anchos, medidos con
  eventos de red del navegador después de cargar la landing y el chunk.
- **0 escrituras de Storage durante la simulación**.
- Reduced motion: animaciones computadas en `none`; flujo completo aprobado.
- **0 excepciones JavaScript**. Harness final: **exit 0 / PASS**.

Los assets iniciales y el consentimiento de cookies de la landing no forman
parte de la simulación; el harness resuelve ese aviso antes de medirla.

## Invariantes

Sin dependencias nuevas ni cambios en manifests/lockfiles. No se agregaron
fetch, polling, WebSocket, persistencia, entidades reales ni llamadas a IA.
Los snapshots siguen siendo estado efímero en memoria.

No se tocaron backend, endpoints, billing, Mercado Pago, checkout, seats,
S8, OpenAI, WhatsApp, webhooks, lifecycle ni `appointments.is_active`.
La experiencia continúa en la landing pública, fuera de `/app/...`.
Se preservaron los cambios preexistentes del worktree.

TURNOS RECEPCIONISTA 04 — CLOSED
