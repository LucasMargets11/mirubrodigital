# PROD-03B — API segura de configuración de Recepcionista IA

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `08d9a3c` · Bot
`8b69e4d` sin cambios. Referencia: `docs/PROD03A_CONFIGURACION_INDIVIDUAL_RECEPCIONISTA.md`.

## 1. Endpoints

| Acceso | Método y ruta | Business |
|---|---|---|
| Comercio | `GET/POST/PATCH /api/v1/receptionist-config/` | `request.business` (contexto autenticado) |
| Platform Admin | `GET/POST/PATCH /api/v1/platform-admin/clients/<business_id>/receptionist-config/` | cliente HQ elegido |

- `GET` devuelve `{"config": null}` si no existe y nunca crea registros.
  Con configuración devuelve `{"config": {...}}`: campos editables, `status`,
  `version`, `missing_for_ready`, `id` y fechas. No incluye datos del
  Business. Respuesta con `Cache-Control: no-store`.
- `POST` crea el borrador (cuerpo vacío o con contenido). Responde 201, o 409
  `receptionist_config_exists` si ya existe.
- `PATCH` edita parcialmente con `expected_version` obligatorio. Responde 200,
  404 `receptionist_config_not_found` o 409 `version_conflict` con
  `current_version`.
- Los errores van como `{code, detail, ...}`. `validation_error` trae
  `fields` con los mensajes del modelo; `unknown_fields` y `protected_fields`
  traen la lista de claves.

## 2. Permisos

- **Comercio:** `HasBusinessMembership` + `HasEntitlement(reception.ai)` +
  `HasPermission(manage_agent_channels)`. En el servicio `reception`, ese
  permiso lo tienen owner y admin; manager y viewer no. Los overrides de rol
  del servicio `reception` aplican (un test revoca admin). Si la suscripción
  Recepcionista IA no está vigente (suspendida, cancelada) o el negocio es
  Turnos IA o Gestión sin Recepcionista, responde 403.
- **Platform Admin:** `IsPlatformStaff` + `HasInternalRole(superadmin,
  operations)`. El negocio debe ser HQ y tener un servicio `reception` no
  cancelado (puede preparar un cliente suspendido); si no, 404
  `client_not_found`. Una membership de comercio nunca habilita esta ruta.

## 3. Validaciones

- Se reutilizan las del modelo de PROD-03A (`save()` → `full_clean()`):
  largos, choices, listas, duplicados, secretos, `ready` completo.
- Antes de eso, la API exige:
  - un objeto JSON;
  - tipos JSON estrictos (texto o lista; `123` no se convierte en `"123"`);
  - nada fuera de los 13 campos editables + `status` (+ `expected_version`
    en `PATCH`): lo demás da 400 `unknown_fields`;
  - ningún campo protegido (`id`, `business`, `business_id`, `version`,
    `created_at`, `updated_at`), que da 400 `protected_fields`.
- Capacidades (`agenda_enabled`, `plan`, `usage_tier`, permisos) y
  credenciales (`api_key`, `token`, `phone_number_id`…) no existen en el
  modelo y se rechazan como desconocidas.
- **Horarios:** dejan de ser obligatorios para `ready` (migración
  `leads/0014`). Un negocio a demanda o sin horarios definidos no tiene que
  cargar datos ficticios; sin horarios, el agente no los informa (regla del
  sistema). El mínimo para `ready` queda en nombre del asistente, rubro,
  descripción, bienvenida y al menos un servicio.
- `ready` significa configuración completa, no activación operativa del bot.

## 4. Concurrencia

- **Edición:** dentro de `transaction.atomic()`, `select_for_update` sobre la
  fila de la configuración y comparación con `expected_version`. Si es
  distinta, responde 409 sin escribir.
- **Creación:** `select_for_update` sobre la fila del Business (el mismo orden
  de lock que `grant_complimentary_access`), revisión de existencia y, como
  red de seguridad, `IntegrityError` del OneToOne convertido a 409.
- **Versión:** sube cuando cambia el contenido o el estado (antes solo el
  contenido). Una escritura sin cambios no la mueve ni audita.
- Los tests de concurrencia usan `TransactionTestCase` con dos threads reales
  y conexiones separadas. La auditoría se demora para que el segundo
  escritor espere el lock. Resultado: una creación y un 409, y una edición y
  un 409, con una sola fila de auditoría en cada caso.

## 5. Auditoría

- `record_platform_action` (estricta, PROD-02F4) dentro de la misma
  transacción, sobre `AccessAuditLog`, con las acciones nuevas
  `RECEPTIONIST_CONFIG_CREATED` y `RECEPTIONIST_CONFIG_UPDATED` (migración
  `accounts/0035`, cambio de choices sin efecto en la base).
- Registra `entity_type=receptionist_config`, el actor real, el Business y
  `details = {source: platform_admin|business, version, status,
  changed_fields, previous_version}`.
- Solo nombres de campos: nunca instrucciones, FAQs ni textos (verificado por
  test).
- Si la auditoría falla, la creación o edición se revierte (tests con fallo
  forzado).

## 6. Tests

`apps/leads/tests/test_receptionist_config_api_03b.py`, con 35 tests:

- **Borrador y lectura:** GET sin configuración devuelve `null` y no crea ni
  audita; POST vacío crea un borrador; un segundo POST da 409; el owner lee y
  edita; la respuesta no trae datos del Business.
- **`ready`:** el mínimo y los campos que faltan; `ready` sin horarios
  funciona; romper una configuración lista falla; se reutilizan las
  validaciones del modelo; tipos JSON estrictos.
- **Versión:** `expected_version` obligatorio y estricto; una versión vieja da
  409 con `current_version`; una escritura sin cambios no versiona ni audita;
  un cambio de estado versiona; PATCH sin configuración da 404.
- **Campos protegidos:** rechazados en las dos rutas; capacidades y
  credenciales dan `unknown_fields`; `expected_version` no se acepta al crear;
  un cuerpo que no es objeto se rechaza.
- **Aislamiento:** un `?business_id` ajeno se ignora; un `bid` ajeno vuelve al
  negocio propio y la configuración ajena no se ve ni se toca; las ediciones
  nunca tocan otro negocio.
- **Permisos:** admin sí, manager y viewer no; un override revoca a admin;
  Turnos IA, Gestión y reception suspendida dan 403; anónimo rechazado;
  `operations` sí, `support_agent` y `content_admin` no; un owner del comercio
  no es Platform Admin; sucursal, negocio sin reception, reception cancelada o
  id inexistente dan 404; un cliente suspendido se puede preparar.
- **Auditoría:** con metadatos y sin contenido; rollback ante fallo en la
  creación y en la edición.
- **Concurrencia real:** creación concurrente y edición concurrente con la
  misma versión.

PROD-03A se ajustó a las reglas nuevas (horarios opcionales, `status`
versiona) y queda en 36 tests.

| Corrida (PostgreSQL 16 descartable, tmpfs) | Resultado |
|---|---|
| 03A + 03B | 71/71 OK |
| `apps.leads` + `test_admin_clientes_add_service_02f5` | 794/794 OK (sin fallas) |
| `manage.py check` | sin issues |
| `makemigrations --check` | No changes detected |
| Migraciones | rollback `leads/0013` + `accounts/0034` y re-aplicación OK |

## 7. Infraestructura reutilizada y elementos nuevos

**Reutilizado:**
- `ReceptionistConfig` y todas sus validaciones (03A);
- `HasBusinessMembership`, `HasEntitlement`, `HasPermission` y el
  permiso existente `manage_agent_channels` (sin permiso nuevo);
- `reception.ai` (sin entitlement nuevo);
- `IsPlatformStaff`/`HasInternalRole` con los roles de las otras vistas de
  cliente;
- la regla «cliente HQ» de las vistas admin;
- `AccessAuditLog` + `record_platform_action` (sin tabla de auditoría
  propia);
- el patrón de lock del Business de `grant_complimentary_access`;
- el `Cache-Control: no-store` de las vistas de consumo IA;
- los helpers de test de 02B (`_business`, `_reception`, `_sub`,
  `_superadmin`).

**Nuevo, imprescindible:**
- Las funciones de escritura en el servicio existente
  `services/receptionist_config.py`: es el único lugar que centraliza las
  reglas para los dos accesos.
- `receptionist_config_views.py`: una sola vista base con dos subclases que
  solo eligen el Business.
- Dos rutas.
- Dos choices de auditoría: `AccessAuditLog.action` es un campo con choices
  y no hay acción genérica para cambios del comercio.
- La migración `leads/0014`, que es el cambio pedido sobre horarios.

**Duplicaciones evitadas:**
- un solo servicio y una sola vista base para admin y comercio;
- ningún serializer de escritura paralelo a las validaciones del modelo;
- ningún permiso ni entitlement nuevo;
- ningún modelo de auditoría ni de versión;
- no se devuelven ni copian datos del Business.

## 8. Riesgos y HEAD final

- R1: el rollback de `leads/0014` vuelve a exigir horarios y fallaría si
  existen configuraciones `ready` sin horarios. Es reversible solo antes de
  usarlo.
- R2: `bulk_create`/`update()` siguen salteando `full_clean()`. Las APIs no
  los usan.
- R3: el `bid` ajeno vuelve al negocio propio (comportamiento existente de
  `HasBusinessMembership`), no da 403. Es seguro, pero el frontend debe
  mostrar el negocio activo.
- R4: no hay frontend ni entrega al motor IA (PROD-03C en adelante).
  `ready` no activa el bot.

Commits sobre `08d9a3c`: modelo y migraciones, API y servicio, tests, y este
reporte. Empujados a `origin/feat/recepcionista` sin force push. No se tocó el
bot ni se avanzó a PROD-03C.
