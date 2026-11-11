# TURNOS RECEPCIONISTA 02 — Inteligencia reactiva

## Alcance

El panel Inteligencia ahora refleja el mismo snapshot en memoria que actualiza el
motor local de conversación. Los eventos son metadata declarativa en el fixture:
no se interpreta el texto ni se agregan llamadas de red, persistencia, backend,
OpenAI o dependencias.

## Modelo y eventos

`SimulationSnapshot` contiene `IntelligenceSnapshot`: intención, fase, campos
extraídos y pasos de timeline. Cada mensaje del fixture puede declarar
`intelligenceEvents` para detectar intención/campos, cambiar fase y actualizar
pasos. `typingPhase` permite mostrar estados como «Consultando agenda…» mientras
el recepcionista escribe, sin crear un scheduler adicional.

Fases tipadas: `idle`, `understanding`, `collecting_identity`,
`collecting_service`, `collecting_availability`, `offering_slots`, `confirming`
y `completed`. La conversación de reserva detecta intención de reservar,
servicio, nombre, día, preferencia horaria y horario seleccionado.

Los pasos se actualizan con los mensajes: mensaje recibido, intención detectada,
identificación, preferencia, disponibilidad, selección, confirmación y cierre.
El panel conserva como máximo ocho pasos, con estados pendiente, activo o
completado. El panel MiRubro continúa estático.

## Panel y accesibilidad

- Estado superior derivado de fase y typing.
- Intención con una transición breve.
- Cinco campos con placeholder, valor y check visual al detectar.
- Progreso de 0/5 a 5/5, con `role="progressbar"` y valores ARIA.
- Timeline semántica con `aria-current="step"` para el paso activo.
- Anuncio `aria-live="polite"` para el estado y animaciones CSS respetando
  `prefers-reduced-motion`.
- Cards con altura mínima, valores que permiten wrap y sin cambios al orden del
  layout del slice 01 (chat primero en mobile).

## Ciclo de vida y performance

Los eventos se procesan solo al revelar el mensaje o iniciar su typing, dentro
del scheduler ya existente. Pausar conserva exactamente el snapshot y cancela
el timer; reanudar continúa en el mismo índice. Reiniciar y repetir crean un
estado de inteligencia limpio. No se agregaron `fetch`, API, polling, websockets,
persistencia, procesos paralelos ni dependencias.

## Tests

`npm --prefix apps/web run test -- src/features/appointments/receptionist-sandbox`

- Motor: estado inicial; intent/servicio; nombre; día/preferencia; disponibilidad;
  horario; 5/5 y cierre; pausa/reanudación; reinicio y repetición limpios.
- UI: estado inicial; valores y checks progresivos; progreso; timeline pendiente,
  activa y completada; pausa; reinicio/repetición; cierre y preservación de los
  tests del slice 01.
- Resultado: **23 tests passed**.

También pasan `npm --prefix apps/web run type-check`, ESLint focal y
`npm --prefix apps/web run build`. El build mantiene `/app/turnos/recepcionista`
como ruta dinámica.

## Responsive

Se mantuvo intacta la estructura de columnas y el orden mobile del slice 01.
Ver «Cierre responsive autenticado» más abajo para la validación real en
navegador con sesión autenticada.

## Cierre responsive autenticado

### Entorno

Entorno local desechable, levantado y destruido solo para esta validación,
sin tocar ningún contenedor/servicio de desarrollo existente:

- **PostgreSQL 16-alpine** desechable (`turnos-qa-postgres`, puerto `55433`,
  DB `turnosqa`), creado y eliminado solo para este cierre.
- **Redis 7-alpine** desechable (`turnos-qa-redis`, puerto `56380`) para que
  el rate limiter de login no cayera en `fail-open` con reintentos lentos.
- **API Django local** (`python manage.py runserver 0.0.0.0:8010`,
  `DJANGO_DEBUG=True`), con variables de entorno propias apuntando al
  Postgres/Redis desechables — sin Docker, sin tocar `services/api/.env`.
- **Frontend Next.js local** (`next dev -p 3010`, `apps/web`) con
  `NEXT_PUBLIC_API_URL=http://localhost:8010`.
- Migraciones reales (`manage.py migrate`) y seed real
  (`manage.py seed_turnos_qa --password ...`), el mismo comando que usa
  cualquier desarrollador para QA manual de Turnos. Sin Mercado Pago (no se
  crea `MercadoPagoConnection`), sin OpenAI, sin credenciales productivas.
- Login por el mecanismo normal de `/entrar` (formulario email + contraseña,
  el mismo `login()` de `@/lib/auth/client`), sin interceptar respuestas, sin
  mockear permisos ni rutas QA públicas.

### Usuario y permiso

- Owner real: `owner@qa-turnos.test`, `Membership` real (`role=owner`) en el
  Business `QA Turnos` (`SubscriptionV2` manual/`appointments_base`).
- Sidebar autenticado confirma el contexto real: "Dueño · Turnos".
- `/app/turnos/recepcionista` **no redirige a `/entrar`**: carga directamente
  el shell del sandbox con sesión real y permiso `view_appointments=true`.

### Estados probados (navegador real, timers reales)

| Estado                                    | Intención      | Datos                    | Estado superior     | Timeline (paso activo)           |
| ----------------------------------------- | -------------- | ------------------------ | ------------------- | -------------------------------- |
| Idle                                      | Sin detectar   | 0/5                      | Esperando           | Esperando mensaje                |
| Parcial 1 (tras msg 1)                    | Reservar turno | 1/5 (Limpieza)           | Recopilando datos   | Identificando cliente            |
| Parcial 2 (tras nombre+fecha, bot typing) | Reservar turno | 4/5 (Lucía/Mañana/Tarde) | Consultando agenda… | Buscando disponibilidad          |
| Offering slots                            | Reservar turno | 4/5                      | Esperando respuesta | Esperando selección              |
| Completed                                 | Reservar turno | 5/5 (17:30)              | Completado          | Datos necesarios obtenidos (fin) |

Los 5 estados coinciden exactamente con la secuencia esperada del slice.

### Matriz responsive

Los 5 estados de arriba se midieron en los 5 anchos pedidos (320/375/768/
1024/1440) = **25 combinaciones** (supera el mínimo de 15), midiendo tanto
`document.documentElement` como el contenedor del panel Inteligencia:

```
document.documentElement.scrollWidth <= clientWidth
panel.scrollWidth <= panel.clientWidth
```

**25/25 combinaciones: `scrollWidth <= clientWidth`.** Se verificó
específicamente que `Reservar turno`, `Consultando agenda…`,
`Esperando respuesta`, los valores de campos (`Lucía`, `Limpieza`, `Mañana`,
`Tarde`, `17:30`), la timeline y la barra de progreso no generan overflow en
ningún ancho. Captura a 320px (mobile: chat arriba, Inteligencia debajo, sin
overflow) y a 1440px (3 columnas, sin overflow) revisadas visualmente.

### Estabilidad visual

Se comparó el `getBoundingClientRect()` del panel Inteligencia y del chat
entre el estado idle y el estado completed a 1440px: ancho del panel,
posición izquierda y posición superior del chat **idénticos** (0 layout
shift). Las cards usan altura mínima reservada; el timeline no empuja el chat.

### Pause / resume (tiempo real)

Probado dos veces con esperas reales (no fake timers):

1. Pausa a mitad de un mensaje revelado (Parcial 1): snapshot de Inteligencia
   y progreso **sin cambios** tras varios segundos reales; al reanudar,
   continúa exactamente desde el mismo paso.
2. Pausa **durante el typing** del bot (camino a "Consultando agenda…"):
   confirmado que ni el chat ni el snapshot avanzan mientras está en pausa;
   al reanudar, el typing se reinicia desde ese mismo paso (comportamiento
   heredado del scheduler del slice 01: `resume()` reprograma el paso actual
   completo, no un resto parcial) y termina en el estado esperado.

### Restart y Repeat

- **Reiniciar** desde un estado parcial (1/5, "Reservar turno") devuelve
  exactamente a intención `Sin detectar`, `0 de 5`, todos los campos
  "Esperando...", timeline "Esperando mensaje" y chat vacío. Sin residuos.
- **Repetir simulación** tras `completed` vuelve a producir la misma
  secuencia limpia desde `0/5` (nunca muestra `5/5` antes del primer
  mensaje): verificado leyendo el snapshot justo después de reiniciar la
  simulación con el botón.

### Reduced motion

Con `prefers-reduced-motion: reduce` emulado en el navegador real, la
simulación completa corrió de punta a punta sin romper layout, sin overflow
(`scrollWidth <= clientWidth` se mantuvo) y con todos los estados/datos
legibles sin depender de las animaciones.

### Performance (navegador real)

Con un listener de `request` activo durante una corrida completa (reinicio →
inicio → completed, ~9.2 s reales): **0 requests** hacia la API (`:8010`)
generadas por el motor de simulación. Las únicas requests de red de toda la
sesión fueron las normales de autenticación/carga de la app (login, `/auth/me`,
`onboarding-status`, `branding`), anteriores al inicio de cada medición. 0
polling, 0 websockets.

### Checks técnicos (repetidos tras la validación en navegador)

- `npm --prefix apps/web run test -- src/features/appointments/receptionist-sandbox` → **23/23** ✅
- `npm --prefix apps/web run type-check` → sin errores ✅
- ESLint focal (mismos archivos del slice) → 0 errores ✅
- Prettier focal (config real `apps/web/prettier.config.cjs`) → PASS ✅
- `npm --prefix apps/web run build` → build completo; `/app/turnos/recepcionista`
  sigue registrada como ruta dinámica (`ƒ`) ✅
- Sin cambios en `package.json`/lockfiles ✅

### Invariantes (confirmado)

Backend, billing, Mercado Pago, OpenAI, WhatsApp, S8 y
`appointments.is_active` sin cambios: la validación de este cierre solo
ejecutó comandos ya existentes (`migrate`, `seed_turnos_qa`, `runserver`,
`next dev`) contra una base de datos desechable, sin editar código de
backend. El panel MiRubro sigue estático (placeholders "Todavía no hay
información") y el composer manual sigue deshabilitado/no-procesante durante
la simulación automática. El entorno desechable (contenedores Postgres/Redis,
servidores locales) se destruyó al finalizar esta validación.

## Invariantes

No se modificaron backend, billing, Mercado Pago, seats, pricing, S8, OpenAI,
WhatsApp, webhooks, lifecycle, `appointments.is_active`, panel MiRubro dinámico
ni composer manual. No se avanzó a RECEPCIONISTA 03.

TURNOS RECEPCIONISTA 02 — CLOSED
