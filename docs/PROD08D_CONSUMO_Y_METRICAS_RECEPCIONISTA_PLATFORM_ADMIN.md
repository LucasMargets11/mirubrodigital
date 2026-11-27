# PROD-08D — Consumo IA y métricas operativas en Platform Admin

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `faa6f91` · Bot
`ef5e329` sin cambios. Solo frontend (`apps/web`). Sin backend, endpoints,
modelos ni dependencias.

## 1. Resultado

En `/admin/clientes/[clienteId]`, debajo de «Recepcionista IA», aparecen dos
secciones nuevas:

- **Consumo comercial de IA** — `GET .../clients/{id}/ai-usage/` (PROD-02E3B).
- **Métricas operativas** — `GET .../clients/{id}/operational-metrics/`
  (PROD-02E4C/02E4D).

Las tres secciones comparten un único `Providers`, es decir un solo
`QueryClient` para todo el bloque Recepcionista. El bloque completo se oculta
solo ante el 404 de dominio `client_not_found` del endpoint de configuración
(PROD-08C), así que vale igual si Recepcionista es el servicio principal o uno
adicional. Cada sección maneja por separado su carga, sus errores y la ausencia
de datos. El Business sale siempre del id de la ruta y las claves de query van
por cliente y por rango.

## 2. Reutilizado

- **`AIUsageSummaryPanel`.** Se separó en el wrapper del comercio (mismo hook y
  misma salida) y `AIUsageSummaryView`, la misma presentación pero con los
  datos que le pasa quien la usa. Platform Admin le pasa el `summary` de su
  endpoint, así que nunca consulta `/api/v1/ai-usage/`. Para
  `audience="platform_admin"` cambian los textos de estado y de 403: hablan
  del cliente, no de «tu plan».
- **Componentes de `/admin`:** `SectionCard`, `StatCard`, `StatusBadge`, y
  `Providers` (PROD-08C), ahora uno solo para el bloque.
- **Filtro de fechas:** `DateRangePicker` (`components/ui`) con
  `localDateToString` y `parseDateOnly`.
- **Formato:** `formatNumber` (con opciones `Intl` para USD),
  `formatDateAR`, `formatDateTimeAR` y `formatDateFromTimestampAR`.
- **Capa de datos:** el patrón de `features/reception/{api,hooks,types}.ts` y
  `ApiError`.
- **Gráficos: no se usaron.** `SalesTrendChart` y `PaymentsDonutChart` son
  específicos de ventas y pagos en ARS. Usarlos acá obligaba a escribir otra
  opción de ECharts, que en la práctica es un componente nuevo. Indicadores y
  filas simples alcanzan para estos conteos.

## 3. Datos incorporados

**Consumo comercial**
- Plan y tier.
- Fuente de consumo (`plan_code`).
- Período vigente.
- Sesiones incluidas, usadas y disponibles, con la barra del panel.
- Estado comercial y diagnóstico, con su código.
- Suscripción: estado, si es bonificada, si cancela al fin del período, y su
  vigencia.
- Política (catálogo o personalizada).
- Tope del período y excedentes.
- Cambio de cupo programado.
- Hora de evaluación.

Se respetan los estados `available`, `exhausted`, `suspended`,
`policy_not_configured`, `not_contracted`, `ambiguous_source` y `unavailable`.

**Métricas operativas**
- Rango: el mismo `DateRangePicker`. Si no se elige uno, el backend usa los
  últimos 30 días y la pantalla muestra el período que devolvió. Antes de
  consultar se valida que «Desde» no sea posterior a «Hasta» y que el rango no
  pase de 92 días, el mismo límite que el backend. Un 400 del backend se
  muestra como rango inválido.
- **WhatsApp:**
  - mensajes recibidos y enviados (bot y recepción);
  - conversaciones con actividad;
  - estado de entrega: entregado, leído, enviado, fallido y sin estado.
- **Derivaciones y atención humana:**
  - derivaciones solicitadas;
  - bot pausado;
  - tomas de conversación;
  - devoluciones al bot;
  - mensajes de recepción enviados desde Mi Rubro, y cuántos fallaron.
- **IA (OpenAI):**
  - ejecuciones, por resultado;
  - tokens de entrada y salida reportados, y en cuántas ejecuciones faltan;
  - latencia promedio;
  - p95, o el mínimo de muestras que hace falta para calcularlo.
- **Costos operativos estimados:**
  - total en USD de OpenAI, marcado como completo, parcial (con sus motivos) o
    sin estimar;
  - Meta/WhatsApp siempre «Sin datos».
  - Una aclaración fija dice que es una estimación y no facturación.
- **Cobertura:**
  - si hay canal del agente;
  - si se observó sincronización;
  - leads en el tope de mensajes;
  - ejecuciones sin tokens.

**Valores desconocidos.** Todo `null` del contrato se muestra como «Sin datos»,
nunca como 0. El costo se muestra como «Sin datos» cuando ninguna ejecución
pudo estimarse. El consumo comercial y los costos operativos van en secciones
separadas.

**Corrección compartida.** Antes, el panel del comercio mostraba «0 de 0» cuando
el cupo estaba agotado y `sessions` venía `null` (tope alcanzado sin lectura).
Ahora muestra «Sin datos de sesiones del período.», sin barra.

## 4. Elementos nuevos (justificados)

- `components/admin/admin-ai-usage-section.tsx`: `SectionCard` con
  `AIUsageSummaryView` más los campos administrativos que el panel del comercio
  no tiene (diagnóstico, suscripción, política, tope, excedentes).
- `components/admin/admin-operational-metrics-section.tsx`: el contrato de
  métricas no tenía ninguna presentación. Arma la sección con `StatCard` y
  filas simples.
- `components/admin/receptionist-admin-card.tsx`: es
  `receptionist-config-card.tsx` renombrado. Ahora monta las tres secciones bajo
  un solo `Providers` y decide si se ocultan.
- En `features/reception`:
  - `getAdminAIUsage` y `getAdminOperationalMetrics`;
  - `useAdminAIUsage` y `useAdminOperationalMetrics`, sin reintentos, sin
    refetch al volver el foco y con claves por cliente y rango;
  - los tipos de ambos contratos;
  - `not_contracted` en `AIUsageStatus`, que solo aparece en Platform Admin.

No se leen las políticas paginadas (`.../ai-usage/policies/`) ni el historial.
No hay edición de políticas ni nada de conexiones WhatsApp.

## 5. Tests

`components/admin/__tests__/receptionist-admin-metrics.test.tsx`: 13 casos, a
través de `ClienteDetailContent`, con respuestas por ruta.
- Consumo:
  - reutilización del panel, sin llamadas a `/api/v1/ai-usage/` y todas las
    rutas del cliente;
  - consumo disponible, agotado sin sesiones (sin ceros), suspendido, no
    contratado y política no configurada.
- Métricas:
  - completas, parciales y desconocidas;
  - costo estimado y costo sin datos;
  - Meta como «Sin datos»;
  - cambio de rango (query string y validaciones sin nueva consulta).
- Integración:
  - 403 con textos de Platform Admin;
  - errores independientes entre consumo, métricas y configuración;
  - cliente sin Recepcionista: solo se consulta la configuración;
  - cambio de cliente sin mezclar datos.

Además:
- Panel del comercio: +1 caso (agotado sin sesiones).
- Suite de 08C: las dos secciones nuevas quedan simuladas; sigue con sus 14
  casos.

| Corrida | Baseline `faa6f91` | Final |
|---|---|---|
| Dirigida: tarjeta admin 08C + 08D, `features/reception` | 38 | 52/52 |
| Regresión: `app/admin`, `components`, `lib`, `features/reception`, `features/leads`, `app/app/recepcionista` | 552/554 | 566/568 |
| TypeScript | 4 errores preexistentes (`google-place-autocomplete.tsx`) | los mismos 4 |
| ESLint (archivos tocados) | warnings de íconos sin usar en `cliente-detail-content.tsx` | los mismos; archivos nuevos y cambiados limpios |

Las 2 fallas de la regresión son las preexistentes de
`admin/notificaciones-content.test.tsx`.

## 6. Riesgos

- R1: no se verificó en un navegador real. Falta una pasada visual: los
  `StatCard` son grandes (`text-3xl`) dentro de la columna principal.
- R2: consumo y métricas empiezan a cargar recién cuando responde el endpoint
  de configuración, porque de él depende si el bloque se muestra.
- R3: si la configuración falla con un error que no es el 404 de dominio, igual
  se muestran consumo y métricas, cada uno con su propio estado.
- R4: el rango se valida con fechas locales del navegador. El backend
  interpreta los días en la zona del Business; si no coinciden, decide el
  backend y la pantalla muestra el 400 como rango inválido.
- R5: los textos de diagnóstico cubren los códigos actuales de PROD-02E3B. Un
  código nuevo se muestra tal cual.

## 7. HEAD

Commits sobre `faa6f91`: secciones y capa de datos, tests y este reporte,
empujados a `origin/feat/recepcionista` sin force push. No se avanzó a
PROD-08E.
