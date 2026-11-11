# TURNOS RECEPCIONISTA 01 — shell visual del sandbox + simulación automática

**Fecha:** 2026-11-02 (cierre revisado 2026-11-03)
**Estado:** TURNOS RECEPCIONISTA 01 — CLOSED

## Alcance

Se agregó `Turnos > Recepcionista` (`/app/turnos/recepcionista`): un sandbox visual
para probar cómo atendería el Recepcionista IA, con una conversación de ejemplo que
se reproduce sola (motor local, sin red) y paneles laterales preparados para los
siguientes slices. No se integró OpenAI, no se integró WhatsApp, no se llama al
agente real, no hay persistencia y no se creó backend nuevo.

## Auditoría previa

- Navegación de Turnos: grupo `appointments` en [sidebar.tsx](/apps/web/src/components/navigation/sidebar.tsx:218), gateado por `permissionKey`/`featureKey` por ítem (sin iconos por ítem — convención del repo es texto plano, no se agregaron iconos ad-hoc para no romper el patrón).
- Páginas de Turnos siguen el mismo patrón server component: `getSession()` → chequeo de permiso → `AccessMessage` si no hay acceso → `AppPageHeader` (título/descripción/acciones) → contenido (ver [horarios/page.tsx](/apps/web/src/app/app/turnos/horarios/page.tsx), [configuracion/page.tsx](/apps/web/src/app/app/turnos/configuracion/page.tsx)).
- UI existente reutilizada: [Button](/apps/web/src/components/ui/button.tsx), [Card](/apps/web/src/components/ui/card.tsx), [Badge](/apps/web/src/components/ui/badge.tsx), [AppPageHeader](/apps/web/src/components/navigation/app-page-header.tsx), `lucide-react` (ya instalado) y `cn()` de `@/lib/utils`. No existe un componente `Avatar`; se usa un círculo con iniciales (mismo patrón ad-hoc que otras pantallas de Turnos para badges/estado).
- Patrón de burbujas de chat tomado de [lead-conversation-history.tsx](/apps/web/src/app/app/turnos/leads/[id]/lead-conversation-history.tsx) (cliente a la izquierda, agente a la derecha, `bg-brand-600` para el lado del agente).
- `framer-motion` está en `package.json` pero no se usa en ningún componente de producción (solo se menciona en comentarios de [expanding-panel.tsx](/apps/web/src/components/marketing/sections/expanding-panel.tsx) explicando que se reemplazó por CSS para ahorrar bundle). Se mantuvo esa convención: todas las microanimaciones de este slice son CSS puro (keyframes + clases scoped), igual que `.stock-select-content` en [globals.css](/apps/web/src/styles/globals.css). No se agregó ninguna dependencia nueva.
- No existe un hook de `prefers-reduced-motion` en JS; se agregó una comprobación local mínima en el chat (`window.matchMedia`) solo para decidir el `behavior` de `scrollIntoView`; el resto del respeto a `prefers-reduced-motion` es 100% CSS (`@media (prefers-reduced-motion: reduce)` y la utilidad `motion-reduce:` de Tailwind).

## Arquitectura

```
apps/web/src/features/appointments/receptionist-sandbox/
  types.ts                 # tipos del slice (ChatMessage, ScenarioFixture, SimulationSnapshot, placeholders)
  simulation-data.ts        # fixture local de la conversación (8 mensajes, sin red)
  simulation-engine.ts      # SimulationEngine (agnóstico de React) + hook useReceptionistSimulation
  conversation-panel.tsx    # chat central (header, mensajes, typing, composer)
  intelligence-panel.tsx    # panel izquierdo "Inteligencia" (placeholder terminado)
  mirubro-panel.tsx         # panel derecho "MiRubro" (placeholder terminado)
  receptionist-sandbox.tsx  # shell: toolbar + layout de 3 columnas
  __tests__/
    simulation-engine.test.ts
    receptionist-sandbox.test.tsx

apps/web/src/app/app/turnos/recepcionista/page.tsx   # ruta server (sesión + permiso)
```

Ningún archivo supera las ~230 líneas.

## Motor de simulación

`SimulationEngine` (clase, sin React) mantiene `status`, `messages`, `isTyping` y un
único `setTimeout` recursivo (nunca más de un timer activo a la vez). `start`,
`pause`, `resume` y `restart` solo tocan ese timer + el snapshot emitido a los
listeners. `useReceptionistSimulation` conecta el engine al ciclo de vida de React
y llama `engine.dispose()` (clear timer + listeners) en el cleanup del `useEffect`.

Timing por mensaje (dentro de los rangos pedidos): cliente 320–480 ms, typing del
bot 850–1000 ms, más una pausa de "lectura" de 300 ms tras cada mensaje para que la
conversación no se sienta atropellada. Duración total real medida: **~8.7 s**
(objetivo 8–12 s).

Estados del botón principal de la toolbar:

| `status`    | Label                  | Acción   |
|-------------|------------------------|----------|
| `idle`      | Iniciar simulación     | `start`  |
| `running`   | Pausar                 | `pause`  |
| `paused`    | Reanudar               | `resume` |
| `completed` | Repetir simulación     | `start`  |

"Reiniciar" (botón secundario) siempre llama `restart` y está deshabilitado en `idle`.

## Chat central

Header con iniciales "LF", "Lucía Fernández", teléfono, indicador verde animado
(`animate-ping` + `motion-reduce:animate-none`), "En línea" y badge "Simulación".
Mensajes con `role="log"` y `aria-live="polite"`; burbujas con
`data-testid="receptionist-message-bubble"`. Typing con tres puntos animados en CSS
(`receptionist-typing-dot`, `role="status"` con `aria-label`). Composer deshabilitado
solo mientras `status === 'running'` (placeholder "La simulación automática está en
curso"); en cualquier otro estado queda habilitado mostrando "Escribí un
mensaje..." pero sin lógica de envío (fuera de alcance de este slice). Auto-scroll
con `scrollIntoView({ behavior })`, `smooth` salvo `prefers-reduced-motion`. Al
completarse se muestra, de forma discreta, "Simulación completada" dentro del chat
y como anuncio `aria-live` en la toolbar.

## Paneles laterales

`IntelligencePanel` (Intención / Datos detectados / Proceso) y `MiRubroPanel`
(Contacto / Lead / Reserva) están visualmente terminados con placeholders fijos
("Esperando conversación" / "Todavía no hay información"). Los tipos
`IntelligenceSnapshot` y `MiRubroSnapshot` ya están declarados (siempre `null` en
este slice) para que RECEPCIONISTA 03 los complete sin tocar el layout.

## Responsive

- Desktop (`lg:`): grid `270px | minmax(420px,1fr) | 300px`, contenido en
  `max-w-[1400px] mx-auto`.
- Tablet (`md:`): chat ocupa las dos columnas arriba; Inteligencia y MiRubro debajo,
  uno al lado del otro.
- Mobile: una columna, orden toolbar → chat → Inteligencia → MiRubro (vía `order-*`
  responsivos).
- Se detectó un overflow horizontal real a 320px, causado por los controles de
  este toolbar (selector + botón primario + "Reiniciar"), más anchos que los de
  cualquier otra pantalla de Turnos. **Se corrigió localmente en
  `ReceptionistSandbox`** (ver sección "Revisión de cierre" más abajo): los
  controles ya no viven en el slot `actions` de `AppPageHeader` sino en su
  propio `<div className="flex flex-wrap ...">` debajo del header, con libertad
  total para envolver a 320px. `AppPageHeader` quedó intacto (sin diff respecto
  a su versión original). Revalidado en navegador real (Playwright) con
  `document.documentElement.scrollWidth <= clientWidth` en
  320/375/768/1024/1440: **todas pasan**.

## Revisión de cierre (2026-11-03)

Antes del cierre se pidió auditar dos puntos del reporte original. Resultado:

### 1. Prettier — el reporte original estaba mal

El reporte anterior decía "no hay `.prettierrc` en el repo, se usa el default".
Eso era **incorrecto**: existe configuración real.

- [apps/web/prettier.config.cjs](/apps/web/prettier.config.cjs) → `module.exports = require('../../packages/config/prettier/base.cjs')`.
- [packages/config/prettier/base.cjs](/packages/config/prettier/base.cjs) →
  `{ singleQuote: true, semi: true, trailingComma: "all", printWidth: 100, tabWidth: 2 }`.

Prettier resuelve esta config automáticamente al correr desde `apps/web` (no hace
falta `--config`). Con la config real, los archivos nuevos del slice (escritos en
4 espacios para calzar visualmente con el resto de `app/app/turnos`, que tampoco
cumple esta config) fallaban `--check` por `tabWidth`/comillas, no por ausencia de
config. Se corrigió:

```
cd apps/web
npx prettier --write \
  "src/features/appointments/receptionist-sandbox/**/*.{ts,tsx}" \
  "src/app/app/turnos/recepcionista/**/*.tsx"
```

Solo se formatearon los archivos nuevos de RECEPCIONISTA 01 (10 archivos); no se
tocó ningún archivo legacy. Resultado:

```
npx prettier --check \
  "src/features/appointments/receptionist-sandbox/**/*.{ts,tsx}" \
  "src/app/app/turnos/recepcionista/**/*.tsx"
→ All matched files use Prettier code style!
```

**PASS.** (El resto del módulo Turnos sigue sin cumplir esta config — es una
deuda preexistente del repo, fuera de alcance de este slice.)

### 2. `AppPageHeader` — se optó por B: revertir y mover el fix al sandbox

El cambio compartido en `app-page-header.tsx` (fila `flex-col sm:flex-row` +
`flex-wrap` en las acciones) solo existía para resolver el overflow a 320px de
**este** toolbar. Aunque era retrocompatible, no había necesidad real de tocar un
componente usado por páginas de admin/gestión (`suscripciones-content.tsx`,
`soporte-content.tsx`, `reportes-content.tsx`, `clientes-content.tsx`,
`lead-detail-client.tsx`, etc.) para un problema 100% local a este sandbox.

Se revirtió `app-page-header.tsx` a su versión original (`git diff` vacío contra
`HEAD`) y se movió el toolbar (selector de escenario + botones) fuera del slot
`actions` de `AppPageHeader`, a su propio `<div>` debajo del header dentro de
[receptionist-sandbox.tsx](/apps/web/src/features/appointments/receptionist-sandbox/receptionist-sandbox.tsx).
`AppPageHeader` ahora se usa solo con `title`/`description`, igual que en
`horarios/page.tsx` y `turnos/page.tsx`. Cero riesgo para otras pantallas.

Verificado:

- `git diff -- apps/web/src/components/navigation/app-page-header.tsx` → sin
  cambios (idéntico a `HEAD`).
- El toolbar propio ya usaba `flex flex-wrap items-center gap-2`; al quedar en su
  propia fila (sin competir con el título por espacio), envuelve libremente a
  320px.

### 3. Regresiones re-ejecutadas tras el revert

- `navigation-refactor.test.tsx` (cubre `AppPageHeader`) → **9/9** ✅
- `sidebar-appointments.test.tsx` → **9/9** ✅
- Inspección responsive de una segunda página de Turnos que usa `AppPageHeader`
  sin tocar (`horarios/page.tsx`, sin `actions`): sin cambios posibles ya que el
  componente volvió a su estado original — no aplica regresión.

### 4. Re-chequeo completo del slice

- `npx vitest run src/features/appointments/receptionist-sandbox` → **15/15** ✅
- `npx tsc --noEmit` → sin errores ✅
- `npx eslint` focal (sandbox + `recepcionista/page.tsx` + `sidebar.tsx` +
  `app-page-header.tsx`) → 0 errores (2 warnings preexistentes en `sidebar.tsx`,
  no relacionados con este cambio) ✅
- `npx prettier --check` sobre los archivos nuevos → **PASS** ✅
- `npx next build` → build de producción completo sin errores;
  `/app/turnos/recepcionista` sigue registrada como ruta dinámica (`ƒ`) ✅

### 5. Responsive revalidado tras el refactor

Como el layout del toolbar cambió (ya no vive dentro de `AppPageHeader`), se
repitió la comprobación completa en navegador real (Playwright):

| Ancho | `scrollWidth` | `clientWidth` | OK |
|-------|---------------|---------------|----|
| 320   | 381           | 381           | ✅ |
| 375   | 450           | 450           | ✅ |
| 768   | 960           | 960           | ✅ |
| 1024  | 1280          | 1280          | ✅ |
| 1440  | 1800          | 1800          | ✅ |

(Los valores no son 1:1 con el ancho nominal por el factor de escala del entorno
de captura; lo relevante es `scrollWidth <= clientWidth` en los cinco casos.)

Además se verificaron por `getBoundingClientRect()` los tres layouts:

- 320: una columna, orden toolbar → chat → Inteligencia → MiRubro, toolbar
  envuelve en varias líneas.
- 768: chat a todo el ancho arriba, Inteligencia y MiRubro lado a lado debajo.
- 1440: 3 columnas `270px | flex | 300px`, sin overflow.

## Tests

`npx vitest run src/features/appointments/receptionist-sandbox` → **15/15** passed:

- `simulation-engine.test.ts` (6): idle inicial, orden de mensajes + typing antes
  de cada respuesta, pause detiene / resume continúa, restart limpia, dispose
  corta timers y listeners, reinicio tras completar.
- `receptionist-sandbox.test.tsx` (9): idle con paneles placeholder, reproducción
  con orden y typing correctos, pause/resume, restart, estado completed +
  "Repetir simulación", **0 llamadas a `fetch`** durante toda la simulación,
  cleanup de timers en `unmount` sin throw, `prefers-reduced-motion` no rompe
  (scroll usa `behavior: 'auto'`), paneles Inteligencia/MiRubro visibles durante
  la reproducción.

Suites existentes que podían verse afectadas, re-ejecutadas en verde:

- `src/components/navigation/__tests__/sidebar-appointments.test.tsx` → 9/9.
- `src/components/navigation/__tests__/navigation-refactor.test.tsx` (cubre
  `AppPageHeader`) → 9/9.

## Validación (estado final, post-revisión de cierre)

- `npx vitest run src/features/appointments/receptionist-sandbox` → 15/15 ✅
- `npx tsc --noEmit` → sin errores ✅
- `npx eslint` focal (sandbox + `recepcionista/page.tsx` + `sidebar.tsx` +
  `app-page-header.tsx`) → 0 errores (2 warnings preexistentes en `sidebar.tsx`,
  no relacionados con este cambio) ✅
- `npx prettier --check` sobre los archivos nuevos (config real de
  `apps/web/prettier.config.cjs` → `packages/config/prettier/base.cjs`) →
  **PASS** ✅
- `npx next build` → build de producción completo sin errores;
  `/app/turnos/recepcionista` aparece registrada como ruta dinámica (`ƒ`) ✅
- Responsive 320/375/768/1024/1440 validado en navegador real (Playwright):
  `scrollWidth <= clientWidth` en los cinco anchos, sin overflow horizontal ✅
- Validación manual end-to-end en navegador: iniciar → mensajes en orden con
  typing antes de cada respuesta del bot → pausar → reanudar → completar →
  "Simulación completada" → "Repetir simulación" ✅
- Performance: 0 requests de red durante toda la simulación (confirmado por test
  con `fetch` espiado y por inspección manual), 0 polling, 0 websockets, 0
  dependencias nuevas (sin cambios en `package.json`/lockfiles), sin imágenes
  externas ✅

## Invariantes respetados

No se tocó backend billing, Mercado Pago, checkout, pricing, seats, S8, OpenAI,
WhatsApp, webhooks, lifecycle ni `appointments.is_active`. No se creó persistencia
ni tablas nuevas. `AppPageHeader` quedó **sin modificar** respecto a `HEAD` (el
fix de responsive vive enteramente dentro de `ReceptionistSandbox`). Los únicos
archivos pre-existentes tocados son [sidebar.tsx](/apps/web/src/components/navigation/sidebar.tsx) (2 líneas: entrada de nav) y
[globals.css](/apps/web/src/styles/globals.css) (keyframes scoped nuevos, nada eliminado/alterado).

## Siguiente slice

RECEPCIONISTA 02 (no iniciado): el modo manual del composer y la extracción
reactiva de los paneles laterales quedan fuera de este slice, tal como se pidió.

---

**TURNOS RECEPCIONISTA 01 — CLOSED**
