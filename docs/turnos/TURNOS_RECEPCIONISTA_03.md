# TURNOS RECEPCIONISTA 03 — Panel MiRubro reactivo

## Alcance

El panel MiRubro evoluciona durante la demo pública en `/turnos#recepcionista-ia`.
Contacto, Lead, Reserva y la actividad son una **representación visual de lo que
MiRubro haría**. No se crean entidades reales ni se guardan datos; el aviso
global de la landing sigue indicando que es una simulación.

## Modelo y sincronización

`SimulationSnapshot` contiene ahora `intelligence` y `mirubro`. Ambos se
actualizan al revelar el mismo mensaje dentro del scheduler existente. Cada
mensaje del fixture declara sus `mirubroEvents`; no se infieren eventos a partir
del texto.

El reducer de MiRubro consume los valores ya extraídos por Inteligencia para
servicio, nombre, preferencia, día y horario. El fixture comparte el teléfono
local de Lucía entre el chat y el evento de contacto para evitar valores
divergentes.

### Contacto

- Inicial: **Todavía no identificado**.
- El evento de identificación se emite después de `Lucía.`.
- Muestra el nombre detectado, el teléfono de fixture, origen WhatsApp y estado
  textual **Identificado**.

### Lead

- Inicial: **Todavía no creado**.
- La consulta inicial crea el estado visual **Nuevo**, con intención **Reservar
  turno**, servicio y origen WhatsApp.
- La preferencia declarada califica el lead y muestra **Mañana · Tarde**.
- La confirmación del mensaje final lo cambia a **Convertido**.

### Reserva

- Inicial: **Sin turno**.
- La consulta de disponibilidad crea una reserva visual **Pendiente** para
  Limpieza y Mañana.
- El evento de selección agrega 17:30.
- El evento de confirmación muestra **Confirmada**, sin ID, precio ni seña.

### Activity feed

El feed inicia vacío y agrega hasta seis eventos declarativos:

1. Consulta recibida.
2. Contacto identificado.
3. Lead calificado.
4. Disponibilidad consultada.
5. Horario seleccionado.
6. Turno confirmado.

El evento actual se marca como **En curso** y los anteriores como
**Completado**; el evento final se completa al confirmarse. Los estados también
se representan con texto, y el evento activo lleva `aria-current="step"`. No se
anuncia cada fila con `aria-live`.

## Ciclo de vida y rendimiento

- Pausar conserva MiRubro y detiene el avance; reanudar continúa el mismo
  fixture.
- Reiniciar y repetir limpian el snapshot de MiRubro, Inteligencia y chat antes
  de avanzar.
- No se agregó estado React independiente para Contacto, Lead o Reserva.
- Los eventos se procesan en el único scheduler de `SimulationEngine`.
- No se agregaron fetch, API, persistencia, polling, WebSocket ni dependencias.
- El motor queda sin timers al completar.
- Se preservan el import dinámico, IntersectionObserver, fallback server,
  shell estático y ausencia de autoplay del loader público.
- El chunk JS diferido del sandbox queda en **30,973 B sin comprimir /
  8,752 B gzip**. Se mantiene fuera de la carga inicial y se descarga al
  acercarse la demo al viewport.

## Responsive y layout

La demo se verificó en idle, parcial y completed. La sesión de navegador usa
`deviceScaleFactor=0.8`; por esa escala, el viewport solicitado de 1024 px se
reportó como 1023 CSS px. También se verificó 1025 px para cubrir el límite
adyacente del layout desktop.

| Viewport solicitado | CSS medido | Documento scroll/client | Sandbox scroll/client | MiRubro idle/completed | Sin overflow en los 3 estados |
| ------------------- | ---------- | ----------------------- | --------------------- | --------------------- | ----------------------------- |
| 320                 | 320        | 301 / 301               | 227 / 227             | 227 / 227             | Sí                            |
| 375                 | 375        | 356 / 356               | 282 / 282             | 282 / 282             | Sí                            |
| 768                 | 768        | 750 / 750               | 652 / 652             | 318 / 318             | Sí                            |
| 1024                | 1023       | 1005 / 1005             | 907 / 907             | 445 / 445             | Sí                            |
| 1025 (límite)        | 1025       | 1006 / 1006             | 876 / 876             | 224 / 224             | Sí                            |
| 1280                | 1280       | 1261 / 1261             | 1131 / 1131           | 292 / 292             | Sí                            |
| 1440                | 1440       | 1421 / 1421             | 1270 / 1270           | 329 / 329             | Sí                            |

El feed completo queda visible dentro de los 360 px reservados por el panel
MiRubro en los siete anchos (scrollHeight y clientHeight: 360 / 360). Para cada
ancho, el delta idle→completed fue **0 px** en altura del sandbox, posición del
chat y posición del pricing. A 320 px se reservan 122 px para el toolbar en
todos los estados para evitar el salto de 42 px que aparecía al cambiar sus
etiquetas.

Con `prefers-reduced-motion: reduce`, la demo completa conserva sus estados y
contenido; las animaciones de las cards y el feed se desactivan.

## Verificación

- Sandbox, motor, loader, landing pública de Turnos y sidebar: **51 tests
  aprobados en 6 archivos**.
- La landing y su aviso de simulación siguen visibles sin login.
- TypeScript: `npm --prefix apps/web run type-check`.
- ESLint focal: sin errores.
- Prettier focal: sin diferencias.
- Build: `npm --prefix apps/web run build`.
- Browser production: secuencia completa, seis anchos solicitados más 1025 px,
  idle/parcial/completed, overflow, estabilidad de layout y reduced motion.

## Invariantes preservados

Sin cambios a backend, billing, Mercado Pago, checkout, pricing, seats, S8,
OpenAI, WhatsApp, webhooks, lifecycle ni `appointments.is_active`. No se
persiste ni se crean Contact, Lead o Appointment reales. No se implementa modo
manual.

TURNOS RECEPCIONISTA 03 — CLOSED
