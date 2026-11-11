# TURNOS RECEPCIONISTA 02B — Demo pública

## Motivo y alcance

El Recepcionista es una demostración comercial, no un módulo operativo de la
aplicación autenticada. Cualquier visitante puede probarlo en
`/turnos#recepcionista-ia`, sin iniciar sesión y sin Business, Membership,
Subscription, permisos ni backend.

Se eliminó `apps/web/src/app/app/turnos/recepcionista/page.tsx` y la entrada
`Turnos > Recepcionista` del sidebar, incluido su comentario. No hay alias,
redirect específico, ruta legacy ni otro enlace interno equivalente. El build
ya no registra `/app/turnos/recepcionista`.

La feature `apps/web/src/features/appointments/receptionist-sandbox/` se conserva.
No se copiaron sus paneles ni su motor al grupo marketing.

## Integración comercial

Orden de la landing:

1. Hero.
2. Beneficios.
3. Cómo funciona.
4. **Probá el Recepcionista IA**.
5. Capacidades.
6. Planes y tiers informativos de IA existentes.
7. CTA final.

La sección tiene `id="recepcionista-ia"`, badge **Demo interactiva**, subtítulo
comercial y aviso visible: **Esta es una simulación. No se envían mensajes ni se
guardan datos.**

Se conservaron los CTAs del hero para no agregar ruido. El deep link permite
compartir directamente la demo.

Se utiliza `SiteContainer` con máximo de 1400 px, conservando su padding
horizontal compartido. El bloque tiene fondo ligeramente contrastado, borde
suave, radio de 24 px y sombra discreta. No hay sidebar, breadcrumb,
AppPageHeader ni acciones administrativas.

## Arquitectura server/client

```text
TurnosPage (Server Component)
  ReceptionistDemoSection (Server Component)
    ReceptionistSandboxLoader (Client Component pequeño)
      placeholder: SandboxPlaceholder (renderizado por el servidor)
      import() diferido: ReceptionistSandbox (Client Component)
```

La landing no tiene `use client`. Next sigue publicando `/turnos` como página
estática prerenderizada. Hero, beneficios, pasos, capacidades, precios y CTAs
se renderizan independientemente del código de la demo.

`SandboxLayout` es una presentación compartida por el placeholder y el sandbox:
define orden, columnas y alturas sin duplicar la experiencia.

## Lazy loading y estabilidad

- Un IntersectionObserver carga el módulo al acercarse a 300 px del viewport.
- El `import()` solamente se ejecuta desde un effect después de esa señal.
- El observer se desconecta al detectar proximidad y al desmontar.
- Si el navegador no soporta IntersectionObserver, se carga después del mount,
  pero sigue sin autoplay.
- La resolución del import no actualiza componentes desmontados.
- Si falla el chunk, se conserva el shell y se muestra un error explícito con
  indicación de recargar. El error se registra; no se sustituye por éxito ficticio.
- Conversación e Inteligencia reservan 620 px; MiRubro reserva 360 px.
- La toolbar reserva 80 px en mobile y 36 px desde `sm`. Esto contempla sus
  dos filas sin desplazar el pricing al reemplazar el placeholder.
- El chat tiene scroll propio; no usa `scrollIntoView` sobre la página.

Se demoró intencionalmente el chunk en el navegador y se compararon altura del
sandbox y posición absoluta del pricing antes/después: **delta 0 px en las seis
resoluciones**.

## Comportamiento preservado

El motor y el fixture de RECEPCIONISTA 02 no se modificaron.

- Inicio explícito mediante **Iniciar demo**.
- Conversación local de ocho mensajes, typing y orden originales.
- Intención, cinco datos detectados, progreso 0/5 a 5/5, fases y timeline.
- Pausar, Reanudar, Reiniciar y Repetir demo.
- Reiniciar vuelve al estado inicial; repetir reproduce el fixture nuevamente.
- Composer siempre deshabilitado. Copy: **Modo interactivo próximamente**,
  o indicación de simulación en curso.
- Sin animación infinita del paso activo mientras está idle.
- Panel MiRubro siempre placeholder, incluso al completar:
  - Contacto: Los datos identificados aparecerán acá.
  - Lead: La consulta se convertirá en una oportunidad.
  - Reserva: Cuando el cliente confirme, el turno aparecerá acá.

No se implementaron estados dinámicos de Contacto, Lead o Reserva.

## Responsive

Desktop conserva **Inteligencia | Conversación | MiRubro**. Las columnas usan
`minmax(0, ...)`, sin mínimos rígidos que desborden a 1024 px.

En mobile: título/copy, controles, chat, Inteligencia y MiRubro.
Desde 768 px el chat ocupa toda la primera fila y los paneles auxiliares la segunda.

Medición con Playwright y CDP, verificando el ancho CSS real, no sólo el viewport
nominal de la vista integrada:

| Ancho CSS | Documento scroll/client | Sandbox scroll/client | Delta pricing al cargar |
| --------- | ----------------------- | --------------------- | ----------------------- |
| 320       | 320 / 320               | 246 / 246             | 0 px                    |
| 375       | 375 / 375               | 301 / 301             | 0 px                    |
| 768       | 768 / 768               | 670 / 670             | 0 px                    |
| 1024      | 1024 / 1024             | 894 / 894             | 0 px                    |
| 1280      | 1280 / 1280             | 1150 / 1150           | 0 px                    |
| 1440      | 1440 / 1440             | 1270 / 1270           | 0 px                    |

También se ejecutó la demo completa a 320 px y se verificaron las seis
resoluciones con la conversación completada: ambas desigualdades siguen
cumpliéndose. No se comprimieron tres columnas en mobile.

## Bundle y runtime

Inspección del build final:

- Chunk diferido del sandbox: `9cbaec02760bec45.js`.
- Tamaño sin comprimir: **24.606 bytes**; gzip: **7.558 bytes**.
- El chunk no aparece en los scripts/preloads del HTML inicial de `/turnos`.
- En el hero, antes de acercarse a la sección: cero botones de inicio montados
  y ningún recurso correspondiente al chunk del sandbox.
- Sin dependencias nuevas, nuevas importaciones de framer-motion ni imágenes externas.

El tamaño es del chunk generado, no una medición diferencial del bundle completo
de marketing. El loader pequeño sí forma parte de la frontera cliente inicial.

Validación contra frontend de producción local, sin backend ni login, abriendo
directamente `/turnos#recepcionista-ia`:

- Inicio, pausa, reanudación, corrida completa, repetición y reinicio comprobados.
- Ocho mensajes, progreso final 5/5 y placeholders de MiRubro preservados.
- **0 requests durante la corrida**, **0 requests API**, **0 auth**, **0 redirects**.
- **0 errores de consola o página durante la corrida**.
- Máximo **1 timeout pendiente**, **0 intervalos** y **0 timers al completar**.
- **0 animaciones activas del sandbox al completar**.
- Delta de scroll de la landing durante la corrida: **0 px**.
- `TaskDuration` de Chromium durante la corrida instrumentada: **0,484 s**.
  Es tiempo de trabajo del hilo de la página, no un benchmark aislado del motor.

La descarga diferida del chunk es una request de recurso estático anterior al
inicio, no una request de la simulación. La navegación de marketing conserva
sus prefetches existentes de Next; no fueron agregados por este slice.

Con JavaScript deshabilitado: HTTP 200, hero, sección, contenido, pricing y tres
CTAs de consulta visibles; sin botón de inicio funcional. Al abortar únicamente
el chunk de la demo: el contenido server y el shell permanecen, con aviso de error.

## Tests y checks

Se mantuvo el runner canónico `npm --prefix apps\web test -- ...`, focalizado en:

- `src/features/appointments/receptionist-sandbox`
- `src/app/(marketing)/turnos/__tests__/page.test.tsx`
- `src/components/navigation/__tests__/sidebar-appointments.test.tsx`

Resultado final: **5 archivos, 46 tests aprobados, exit code 0**.

| Suite          | Tests | Cobertura relevante                                                                         |
| -------------- | ----- | ------------------------------------------------------------------------------------------- |
| Motor original | 13    | Orden, typing, fases, extracción, pausa, restart y dispose                                  |
| UI del sandbox | 10    | Idle, conversación, 0/5 a 5/5, pause/resume/restart/repeat, composer y placeholders         |
| Loader público | 3     | Proximidad, shell, carga sin sesión/autoplay y cleanup del observer                         |
| Landing Turnos | 10    | Shell SSR, sección/orden, ruta eliminada, frontera cliente, metadata y catálogo sin cambios |
| Sidebar Turnos | 10    | Ausencia de Recepcionista y navegación operativa preservada                                 |

El test de red verifica además cero fetch, setInterval y WebSocket; muestrea
timers a lo largo de toda la corrida para comprobar el máximo de un scheduler.
Unmount y restart dejan cero timers.

Checks finales:

- `npm --prefix apps\web run type-check`: **exit 0**.
- ESLint focal, incluida navegación: **exit 0**, dos warnings previos del sidebar
  (`set-state-in-effect` y variable `err` sin usar).
- Prettier focal con `apps/web/prettier.config.cjs`: **exit 0**.
- Chequeo adicional del sidebar completo: formato preexistente no conforme
  (**exit 1**). No se reformateó el archivo entero para evitar cambios ajenos.
- `npm --prefix apps\web run build`: **exit 0**, `/turnos` estática.

Un primer build detectó tipos generados de desarrollo apuntando a la ruta
eliminada. Se regeneraron con Next; typecheck y builds finales aprobaron.
Se preservaron los warnings existentes de lockfiles, middleware y Browserslist.
Los servidores usados para validación se detienen al finalizar.

## Invariantes y límites

Sin cambios en backend, billing, Mercado Pago, checkout, pricing, seats, S8,
OpenAI, WhatsApp, webhooks, lifecycle ni `appointments.is_active`.
Metadata y JSON-LD existentes intactos: sin IA ficticia ni Offer adicional.

Cero APIs, polling, WebSocket, OpenAI y persistencia del sandbox. No se aceptan
datos personales reales. No se avanzó a RECEPCIONISTA 03.

TURNOS RECEPCIONISTA 02B — CLOSED
