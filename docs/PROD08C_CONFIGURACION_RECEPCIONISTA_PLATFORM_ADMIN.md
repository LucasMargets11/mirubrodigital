# PROD-08C — Configuración de Recepcionista IA desde Platform Admin

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `a7b79c8` · Bot
`ef5e329` sin cambios. Solo frontend (`apps/web`). Sin backend, endpoints ni
dependencias.

## 1. Resultado

- `/admin/clientes/[clienteId]` muestra la sección «Recepcionista IA» (un
  `SectionCard`) en la columna principal, junto a la tarjeta condicional de QR
  de Reseñas. Adentro va el mismo `ReceptionistConfigForm` de PROD-08B con el
  target `platform_admin`. No hay un segundo formulario ni modal.
- Comercio configurado visible: «Negocio: {nombre} (ID {id})».
- Detección por API, no por `service_type`: la sección aparece si
  `GET .../clients/<id>/receptionist-config/` responde, también cuando
  Recepcionista es un servicio adicional (p. ej. Gestión principal).
- Se oculta **solo** ante 404 con `code: client_not_found` (cliente sin
  Recepcionista no cancelada, sucursal o id inexistente). Un 403, un 404 sin ese
  código, un 5xx o un error de red muestran la sección con su estado de error.
  Mientras carga no se muestra nada, para que no aparezca y desaparezca en
  clientes sin el servicio.
- Permisos: deciden los del backend (`superadmin`, `operations`). El frontend no
  duplica la lista de roles. Un 403 muestra «Sin acceso» con un texto propio de
  Platform Admin y sin reintentos.
- Creación explícita, edición por diff, `expected_version`, 409, validaciones por
  campo y paso a «lista»/«borrador» con modal salen del formulario compartido,
  sin cambios. Sigue la aclaración «lista ≠ agente conectado». No se muestra
  WhatsApp, consumo ni métricas.

## 2. Revisión de seguridad

### Platform Admin: independiente de `bid` — verificado

`AdminClientReceptionistConfigView` usa `IsAuthenticated + IsPlatformStaff +
HasInternalRole`, sin `HasBusinessMembership`, y resuelve el Business solo con
`business_id` de la URL (`parent__isnull=True` + Recepcionista no cancelada). No
lee cookie ni `X-Business-Id`. En el frontend, el adaptador `platform_admin`
arma la ruta con el id del cliente y no manda headers de negocio (tests:
llamadas con `undefined` como opciones y la cookie `bid=99` presente).

### Comercio: escritura cruzada entre negocios — confirmado y corregido

- **Caso:** `ReceptionistConfigView` toma `request.business` de
  `resolve_request_membership`, con este orden: `X-Business-Id`, si no la cookie
  `bid`. `POST /auth/switch-business/` reescribe `bid` para todas las pestañas.
  Con «Mi agente» abierto para el negocio A y un cambio a B en otra pestaña, el
  `PATCH` de la pestaña vieja llegaba a B con la versión leída de A. Las
  versiones son enteros chicos (1, 2, 3…), así que coinciden con frecuencia. En
  ese caso los campos editados para A, o el paso a «lista»/«borrador», se
  escribían en B. «Crear borrador» también podía crear el de B. El usuario tiene
  permiso en ambos negocios, así que no gana privilegios, pero los datos de un
  negocio terminan en otro.
- **Corrección mínima con infraestructura existente:** el adaptador del comercio
  manda `X-Business-Id` con el negocio de la sesión que renderizó la pantalla.
  El backend ya lo prioriza sobre la cookie y CORS ya lo permite
  (`CORS_ALLOW_HEADERS`). Para eso `lib/api/client.ts` admite un tercer
  argumento opcional `{ headers }` en `apiGet/apiPost/apiPatch`. De paso se
  corrigió que `...init` pisaba el `Content-Type` cuando se pasaban headers;
  ningún llamador lo hacía hasta ahora. Las demás llamadas no cambian.
- **Residual (requiere backend, fuera de alcance):** si el usuario pierde la
  membership del negocio del header mientras la pantalla sigue abierta,
  `select_membership` cae en otra membership en lugar de responder 403 (03B R3).
  Para que una escritura llegue a otro negocio en ese caso, además tiene que
  coincidir la versión. Corrección propuesta: responder 403 cuando un
  `X-Business-Id` explícito no se resuelve, en vez de caer en otro negocio.

## 3. Reutilizado

`ReceptionistConfigForm`, `receptionistConfigAdapter` (`platform_admin`),
`SectionCard`, `Providers` (`app/providers.tsx`; `/admin` no tenía
`QueryClient`), `ApiError`, el patrón de tarjeta condicional de
`QRResenasCard` en `cliente-detail-content.tsx` y el `key` por cliente para
remontar.

## 4. Cambios

**Nuevo**
- `components/admin/receptionist-config-card.tsx`: montaje fino
  (`Providers` + `SectionCard` + formulario). Decide solo si se oculta.
- Tests `components/admin/__tests__/receptionist-config-card.test.tsx` y
  `lib/api/__tests__/client-headers.test.ts`.

**Modificado**
- `features/reception/receptionist-config-form.tsx`:
  - `useReceptionistConfig(target)` exportado: una sola query compartida por la
    tarjeta y el formulario.
  - `isClientWithoutReception(error)`.
  - Textos por `kind` (vacío y 403).
  - `retryOnMount: false`, para que el segundo observador no vuelva a pedir un
    error ya resuelto y la tarjeta no entre en un ciclo de mostrar y ocultar.
- `features/reception/receptionist-config-api.ts`: `X-Business-Id` solo para
  `business`.
- `lib/api/client.ts`: opciones de headers y orden de merge corregido.
- `app/admin/clientes/[clienteId]/cliente-detail-content.tsx`: una línea de
  montaje y un import.
- `features/reception/__tests__/receptionist-config-form.test.tsx`: las
  expectativas del comercio ahora incluyen el header fijado.

## 5. Tests

| Corrida | Baseline `a7b79c8` | Final |
|---|---|---|
| Dirigida: `features/reception`, `app/app/recepcionista`, tarjeta admin, `lib/api` | 56 | 67/67 |
| Regresión: `app/admin`, `components`, `lib`, `features/reception`, `features/leads`, `app/app/recepcionista` | admin + `lib`: 203/205 | 552/554 |
| TypeScript | 4 errores preexistentes (`google-place-autocomplete.tsx`) | los mismos 4 |
| ESLint (archivos tocados) | warnings preexistentes en `cliente-detail-content.tsx`, `owner-access.ts`, `treasury.ts` | los mismos; archivos nuevos y cambiados limpios |

Las 2 fallas de la regresión son las preexistentes de
`admin/notificaciones-content.test.tsx`.

Casos de admin (14): Recepcionista principal; Recepcionista adicional; sin
Recepcionista (404 de dominio); 403, 404 sin código, 500 y red diferenciados;
texto y sin reintento ante 403; creación y edición; 409; validación en otra tab;
paso a borrador con modal; cambio de cliente sin arrastrar datos ni versión;
independencia de `bid`. En el comercio, todas las escrituras y lecturas exigen
`X-Business-Id` del negocio de la pantalla, incluido el cambio de negocio
(`pinned(2)`).

## 6. Riesgos

- R1: no se verificó en un navegador real; falta una pasada visual del
  formulario dentro de `SectionCard`, que queda con tarjetas anidadas.
- R2: el residual del §2 (fallback de membership) necesita backend.
- R3: la sección no se ve mientras carga; si la API tarda, aparece después que
  el resto del detalle.
- R4: cada tarjeta admin tiene su propio `QueryClient` (vía `Providers`). Hoy es
  la única consumidora de React Query en `/admin`.

## 7. HEAD

Commits sobre `a7b79c8`: corrección de seguridad del comercio, montaje admin,
tests y este reporte, empujados a `origin/feat/recepcionista` sin force push.
No se avanzó a PROD-08D.
