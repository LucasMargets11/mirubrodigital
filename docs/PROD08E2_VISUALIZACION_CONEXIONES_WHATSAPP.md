# PROD-08E2 — Visualización administrativa de conexiones WhatsApp

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `d60b9bd` · Bot
`ef5e329` sin cambios. Solo frontend (`apps/web`). Sin backend, endpoints ni
dependencias.

## 1. Resultado

En `/admin/clientes/[clienteId]`, dentro del bloque Recepcionista IA, apareció
la sección **«Conexiones WhatsApp»**, entre la configuración del agente y el
consumo comercial.

- **Datos:** consume `GET .../clients/{id}/whatsapp-connections/` (PROD-08E1)
  con el `businessId` del cliente de la ruta. La query key es
  `['platform-admin', 'whatsapp-connections', businessId]`.
- **Provider:** usa el `Providers` del bloque (PROD-08C/08D), así que todas las
  secciones comparten un solo `QueryClient`.
- **Estados propios:** carga, error y vacío son independientes de la
  configuración, el consumo y las métricas.
- **Sin polling:** el botón «Actualizar» de la cabecera vuelve a consultar
  (`refetch`) y queda deshabilitado mientras consulta. Ante un error,
  «Reintentar» hace lo mismo.
- **Visibilidad:** si el cliente no tiene Recepcionista (404 de dominio de la
  configuración), el bloque entero se oculta y no se consulta este endpoint.

## 2. Reutilizado

- **Bloque y montaje:** `receptionist-admin-card.tsx`, con su `Providers` y la
  regla de ocultamiento.
- **Componentes de `/admin`:** `SectionCard` (con `actions` para el botón),
  `StatusBadge`, `EmptyState` (sin canales), `LoadingState` y `ErrorState`
  (con `retry`).
- **Botón:** `Button` de `components/ui`, con el ícono `RefreshCw` que ya usa
  el detalle de suscripciones.
- **Utilidades:** `formatDateTimeAR`, `ApiError`, y el patrón de
  `features/reception/{api,hooks,types}.ts`, con las mismas opciones de lectura
  administrativa que 08D.

**Nuevo:**
- `components/admin/admin-whatsapp-connections-section.tsx`.
- En `features/reception`: `getAdminWhatsAppConnections`,
  `useAdminWhatsAppConnections` y los tipos del contrato.

## 3. Qué se muestra

Se ven todos los canales del cliente, activos e inactivos, en el orden en que
los devuelve el backend. Cada canal es una tarjeta compacta: un encabezado con
el estado y debajo una grilla de 1 a 3 columnas. Contiene:

- **Phone Number ID**, rotulado como ID. No se muestra como teléfono.
- **WABA ID**, solo si existe.
- **Canal:** «Activo», o «Desactivado · fecha».
- **Instancia del agente:** nombre y si está habilitada (o deshabilitada, con
  fecha).
- **Autorización:** «Del comercio» o «De plataforma», con su estado (activa,
  revocada o inválida), o «Sin autorización».
- **Vencimiento:** solo si hay autorización. Muestra la fecha y «vencida»
  según el flag del backend, o «Sin vencimiento informado».
- **Revocada:** la fecha, solo si existe.
- **Alta del canal.**

Un dato nulo se muestra como «Sin dato», nunca como una fecha inventada.

No se muestran los ids internos del canal y de la autorización ni el
`external_id` de la instancia. Tampoco si la autorización es del propio
negocio: eso ya lo expresa «Autorización inconsistente».

## 4. Estados

`local_status` es la única fuente; el frontend no recalcula reglas de
autorización.

| `local_status` | Texto | Color |
|---|---|---|
| `credential_ready` | Credencial vigente (estado local) | verde |
| `channel_not_active` | Canal desactivado | gris |
| `whatsapp_authorization_missing` | Sin autorización | ámbar |
| `whatsapp_authorization_owner_mismatch` | Autorización inconsistente | rojo |
| `whatsapp_authorization_revoked` | Autorización revocada | rojo |
| `whatsapp_authorization_invalid` | Autorización inválida | rojo |
| `whatsapp_authorization_expired` | Autorización vencida | ámbar |
| `whatsapp_waba_missing` | WABA no informada | ámbar |
| `agent_instance_disabled` | Instancia deshabilitada | ámbar |
| cualquier otro | Estado no reconocido (`código`) | rojo, nunca válido |

Lo mismo vale para el tipo y el estado de la autorización: un valor desconocido
se muestra como «no reconocido».

**Aclaración fija.** Arriba de la lista dice: «Estado local registrado en Mi
Rubro, evaluado el {fecha}. No se realizó verificación externa con Meta: no
indica WhatsApp conectado, agente online ni envío disponible.» Así,
`evaluated_at` es la hora de la evaluación local y no una verificación de
conectividad.

La sección no tiene ninguna operación de escritura ni pide datos o secretos.
Configuración, conexiones, consumo y métricas siguen en secciones separadas.

## 5. Tests

`components/admin/__tests__/receptionist-admin-whatsapp.test.tsx`: 10 casos, a
través de `ClienteDetailContent`.
- Cliente sin canales, con el estado vacío y la aclaración.
- Varios canales: datos visibles y sin ids técnicos.
- Los nueve estados más uno desconocido.
- Autorización de plataforma, revocada, vencida, y valores nulos.
- Sin indicadores falsos de conectividad, sin campos de texto y con un solo
  botón («Actualizar»); sin `POST`/`PATCH`.
- Actualización manual: una consulta inicial y otra solo al pulsar.
- 403 y error de red, sin afectar la configuración.
- Cambio de cliente sin mezclar datos.
- Un único `Providers` montado para todo el bloque y ninguna llamada a
  endpoints del comercio.
- Cliente sin Recepcionista: no se consulta el endpoint.

Las suites de 08C y 08D simulan la sección nueva, como ya hacían entre sí, y
siguen sin cambios en sus casos.

| Corrida | Baseline `d60b9bd` | Final |
|---|---|---|
| Dirigida: `receptionist-admin-whatsapp` | — | 10/10 |
| Regresión: `app/admin`, `components`, `lib`, `features/reception`, `features/leads`, `app/app/recepcionista` (incluye configuración, consumo y métricas) | 566/568 | 576/578 |
| TypeScript | 4 errores preexistentes (`google-place-autocomplete.tsx`) | los mismos 4 |
| ESLint (archivos tocados) | — | sin warnings |

Las 2 fallas de la regresión son las preexistentes de
`admin/notificaciones-content.test.tsx`.

## 6. Riesgos

- R1: no se verificó en un navegador real. Falta revisar que la grilla de cada
  canal se vea bien en pantallas angostas y que la sección no quede demasiado
  larga con muchos canales.
- R2: «Credencial vigente (estado local)» va en verde. La aclaración fija evita
  leerlo como conexión, pero el color puede sugerir más de lo que significa.
- R3: los datos se consideran frescos durante 60 s (`staleTime`). Al volver a
  la página dentro de ese tiempo se ve lo ya cargado hasta pulsar «Actualizar».
- R4: un estado nuevo que agregue el backend se muestra como «no reconocido»
  hasta actualizar el mapa de textos. Es el comportamiento buscado.

## 7. HEAD

Un commit con la sección y sus tests, y otro con este reporte, empujados a
`origin/feat/recepcionista` sin force push. No se avanzó a PROD-09.
