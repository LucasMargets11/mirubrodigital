# PROD-08C.1 — Aislamiento estricto de escrituras de ReceptionistConfig

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `87c239c` · Bot
`ef5e329` sin cambios. Solo backend, acotado a `ReceptionistConfigView`. Sin
modelos, migraciones, endpoints, dependencias ni cambios de frontend.

## 1. Causa

`ReceptionistConfigView` (comercio) toma el Business de
`resolve_request_membership` (`apps/accounts/access.py`), que es global:

1. Lee `X-Business-Id` y, si no está, la cookie `bid`.
2. `select_membership` busca ese id entre las memberships del usuario. Si no lo
   encuentra, usa `memberships[0]`.
3. `_try_resolve_inherited_membership` solo cubre sucursales de un HQ
   owner/admin. Si tampoco resuelve, se queda con el fallback del punto 2.
4. `list_user_memberships` no filtra por `Membership.status`: una membership
   `suspended` o `inactive` resuelve igual.

Consecuencia: un `X-Business-Id` explícito que no correspondía (membership
eliminada, suspendida, negocio ajeno o inexistente, valor mal formado) no se
rechazaba: el request seguía contra otro negocio del usuario. Con versiones
iguales (enteros chicos), un `PATCH` escribía allí. Se reprodujo contra `HEAD`
con el suite nuevo: 17 fallas, entre ellas escrituras reales en el negocio
equivocado (`{A: ('X', 2), B: ('X', 2)}` con un header mal formado) y un `GET`
que devolvía la configuración del otro negocio.

## 2. Corrección

Un permiso nuevo, `ExplicitBusinessMatch`, en
`apps/leads/receptionist_config_views.py`, ubicado en `permission_classes`
después de `IsAuthenticated` y **antes** de `HasBusinessMembership`. Así corre
en GET, POST y PATCH antes de cualquier lectura o escritura.

- **Sin header:** pasa. El contrato de PROD-03B no cambia (cookie y fallback
  existentes).
- **Con header:** exige que el valor sea un entero ASCII positivo, sin espacios,
  comas ni notación; si no, 403 `business_header_invalid`. Después reutiliza
  `resolve_request_membership` y exige:
  - que `request.business.pk` sea el id pedido;
  - que la membership que lo autoriza, propia o la del HQ heredada, tenga
    `status == active`.

  Si algo no se cumple, 403 `business_access_denied`. Nunca usa otra membership,
  otro negocio ni la cookie.
- La resolución queda cacheada en el request: `HasBusinessMembership`,
  `HasEntitlement` y `HasPermission` siguen igual, sobre el mismo negocio.
- Cuerpo de error `{code, detail}`, igual que el resto de la API de
  configuración. Nunca incluye datos de configuración.
- Platform Admin (`AdminClientReceptionistConfigView`) no cambia. No usa este
  permiso ni resolución de tenant: el Business sale de la ruta.
- El frontend de PROD-08C ya manda `X-Business-Id` con el negocio de la
  pantalla, así que no hubo que tocarlo.

## 3. Infraestructura reutilizada

`resolve_request_membership` (sin modificar), `Membership.Status`, el patrón
`BasePermission` con `message` de dominio de `HasBusinessMembership`, el orden
de `permission_classes` del endpoint y los helpers de tests de 02B y 03B
(`reception_business`, `staff_client`, `admin_url`, `complete`). No se tocó la
resolución global de tenants ni otros módulos.

## 4. Tests

`apps/leads/tests/test_receptionist_config_isolation_08c1.py`, 14 tests. Base:
un usuario owner de A y de B, ambos con configuración en versión 1 y la cookie
apuntando a B.

- **Header válido:**
  - el header gana sobre la cookie;
  - con la misma versión en los dos negocios, PATCH y cambio de estado tocan
    solo A.
- **Acceso perdido** (GET, POST y PATCH → 403, sin escrituras ni auditoría y sin
  datos en la respuesta):
  - membership eliminada;
  - membership `suspended` o `inactive`;
  - negocio ajeno;
  - negocio inexistente;
  - POST que no crea nada en ningún negocio.
- **Header inválido:** `''`, `abc`, `0`, `-1`, con espacios, lista, `1e3` y
  dígito no ASCII → 403 `business_header_invalid`, sin escrituras.
- **Compatibilidad:**
  - sin header decide la cookie, como antes;
  - un manager con header válido sigue con 403 de permisos;
  - con header válido, el versionado sigue en 409 `version_conflict`;
  - un anónimo con header sigue sin autenticar.
- **Platform Admin:** ignora el header y la cookie; escribe solo en el cliente
  de la ruta.

Corridas sobre PostgreSQL 16 descartable (tmpfs) y Redis descartable, en una
red Docker propia, eliminadas al terminar:

| Corrida | Resultado |
|---|---|
| 08C.1 con la corrección | 14/14 OK |
| 08C.1 contra la vista de `HEAD` (demostración) | 17 fallas (el bug) |
| 03A + 03B + 03C + 08C.1 + `test_reception_service_02b` | 142/142 OK |
| `apps.leads` completo | 870/870 OK |
| `manage.py check` | sin issues |
| `makemigrations --check` | No changes detected |

Nota: sin Redis, `test_agent_receptionist_config_03c.test_replay_is_rejected`
falla por `agent_nonce_unavailable`. Es del entorno y no está relacionado con
este cambio; con Redis pasa.

## 5. Riesgos

- R1: sin header, una membership `suspended` o `inactive` sigue resolviendo,
  porque `list_user_memberships` no filtra por estado. Es comportamiento global
  preexistente; corregirlo es un cambio de tenants fuera de alcance.
- R2: los demás endpoints del comercio mantienen el fallback global con
  `X-Business-Id`. Hoy solo el frontend de configuración manda el header.
- R3: un cliente que mande un header mal formado al endpoint de configuración
  ahora recibe 403 en lugar de caer en un negocio. Es el cambio buscado;
  ninguna parte de Mi Rubro lo hacía.

## 6. HEAD

Commits sobre `87c239c`: corrección, tests y este reporte, empujados a
`origin/feat/recepcionista` sin force push. No se avanzó a PROD-08D.
