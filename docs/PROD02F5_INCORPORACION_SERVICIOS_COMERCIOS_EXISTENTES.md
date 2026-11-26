# PROD-02F5: Incorporación de servicios a comercios existentes

- **Fecha:** 2026-11-26
- **Repo y rama:** `mirubrodigital-release`, `feat/recepcionista`
- **Baseline:** `262b587`
- **Bot:** `5eb3dda`, sin cambios

## 1. Servicio y contrato JSON del endpoint

El servicio es `accounts/admin_client_service_addition.py::add_service_to_client`. Hace todo en una sola transacción:

1. Valida que el actor sea superadmin (`_authorize_actor` de F2/F4: personal de plataforma activo con `internal_role=superadmin`, recargado desde la base).
2. Toma `SELECT … FOR UPDATE` sobre el Business HQ (`parent IS NULL`).
3. Valida que el estado del Business sea `active` o `trialing`.
4. Llama a `grant_complimentary_access` mediante `grant_with_domain_errors`. Esta función comparte la taxonomía de errores con el alta de clientes nuevos.

**Endpoint:** `POST /api/v1/platform-admin/clients/<business_id>/services/`. Requiere `IsPlatformStaff` + `HasInternalRole(['superadmin'])`. Las memberships nunca autorizan esta operación.

**Request.** Cualquier otro campo da 400 con `"Campo no permitido."`. Esto incluye `owner_email`, `business_*`, `status`, `default_service`, `country`, `currency`, `attach_existing_owner` y `provider`.

```json
{
  "service_type": "reception",
  "plan_code": "reception",
  "usage_tier": "reception_custom",
  "complimentary_start": "2026-12-01",
  "complimentary_end": "2027-06-01",
  "grant_reason": "Piloto Recepcionista IA",
  "custom_included_sessions": 600
}
```

Reglas de cada campo:
- `usage_tier` solo se envía en los planes con tiers.
- `custom_included_sessions` solo se envía en `reception_custom`. Debe ser un entero JSON estricto entre 1 y 1.000.000.
- Las fechas siguen la misma regla que en el alta de clientes: si se envía solo la fecha, se toma la medianoche de America/Argentina/Buenos_Aires.

**Response 201.** Solo incluye los datos del servicio agregado. No devuelve propietario, usuarios, credenciales ni otros servicios.

```json
{
  "business": {"id": 42, "status": "active", "service_type": "gestion", "default_service": "gestion"},
  "subscription": {
    "id": "6f0c…", "service_type": "reception", "plan_code": "reception",
    "usage_tier": "reception_custom", "provider": "manual", "status": "trialing",
    "current_period_start": "2026-12-01T00:00:00-03:00",
    "current_period_end": "2027-06-01T00:00:00-03:00"
  },
  "custom_policy": {"id": "a1b2…", "included_sessions": 600,
                    "valid_from": "2026-12-01T03:00:00+00:00", "valid_until": "2027-06-01T03:00:00+00:00"}
}
```

`custom_policy` es `null` cuando el tier no es Custom. Las fechas son ISO 8601 con zona horaria: el período sale tal como se parseó y la política tal como quedó guardada (UTC).

**Errores.** Todos usan el formato `{code, detail, field}`:

| HTTP | code | Caso |
|---|---|---|
| 400 | campo → mensajes | Forma inválida o campo desconocido |
| 400 | `invalid_complimentary_period` / `invalid_complimentary_grant_reason` / `invalid_complimentary_service_type` / `invalid_complimentary_usage_tier` / `invalid_custom_included_sessions` / `complimentary_plan_not_available` / `complimentary_plan_service_mismatch` | Mismos validadores del alta de clientes |
| 403 | — | No es superadmin, o es un owner/membership del negocio |
| 404 | `client_not_found` | El Business no existe o es una sucursal |
| 409 | `client_status_not_eligible` | El Business está en `onboarding`, `pending_activation`, `past_due`, `suspended` o `canceled` |
| 409 | `active_complimentary_subscription_conflict` | Ya existe una suscripción no cancelada del mismo servicio |
| 409 | `incompatible_ai_service` | Recepcionista y Turnos IA a la vez |
| 409 | `ai_usage_period_overlap` | El alta reiniciaría un cupo de IA ya contado |
| 422 | `complimentary_grant_failed` | Causa no clasificada |

El único modo de este flujo es el beneficio bonificado: `provider=manual`, `status=trialing`, sin Mercado Pago ni `PaymentAttempt`.

## 2. Reglas de compatibilidad

Se validan dentro de `grant_complimentary_access`, con el lock del Business tomado. Por eso aplican también al alta de clientes nuevos.

- **Duplicados:** no se permite una segunda suscripción no cancelada del mismo `service_type`. La regla ya existía y ahora queda serializada por el lock.
- **Exclusión de IA en ambos sentidos:** las fuentes de IA son las de `ai_source.AI_SOURCES`, es decir `reception/reception` y `appointments/appointments_ai`. No se otorga una si la otra existe en un estado distinto de `canceled`.
- **Combinaciones compatibles:** Recepcionista con Turnos Base (`appointments`) o Pro (`appointments_pro`), en cualquier orden. También con Gestión y con los demás servicios.
- **Suscripciones canceladas:** nunca se reutilizan. Cada alta crea una `SubscriptionV2` y una `ReceptionAIUsagePolicy` nuevas. La política vieja queda ligada a su suscripción cancelada, sin cambios.
- **Fuera de alcance:** este flujo no permite cambios de tier ni migraciones entre productos.

**Otros caminos de escritura comercial.** Estos caminos pueden crear combinaciones incompatibles y quedan para protegerse más adelante. Hoy el resolvedor de IA (`ai_source`) igual falla cerrado con `ambiguous_ai_source` y no consume, pero la combinación se puede crear:

1. `billing/services/appointments_checkout.py` (líneas ~423 y ~730): el checkout y webhook públicos de Turnos crean `appointments_ai` revisando solo otra suscripción de Turnos. No revisan si hay Recepcionista.
2. `billing/services/appointments_lifecycle.py` (~415): el cambio de plan pendiente pasa `appointments`/`appointments_pro` a `appointments_ai` sin revisar si hay Recepcionista.
3. `billing/webhook_processor.py` (~725) y `billing/reconciliation.py` (~456): hacen `get_or_create` de SubscriptionV2 desde Mercado Pago, con el `service_type` tomado de `default_service`.
4. `billing/service_activation.py`, `billing/services/commercial/apply.py`, `billing/commercial_views.py`, `billing/views.py` y `billing/reviews_views.py`: escriben suscripciones de Gestión y QR. No producen fuentes de IA, pero no pasan por un lock de Business.
5. Comando `backfill_subscriptions`: operativo y manual.

## 3. Preservación del Business

El flujo nunca escribe en:
- Business: `service_type`, `default_service`, `status`, `name`, `slug`, `parent`, `activated_at`, `suspended_at`;
- owner, usuarios y memberships (incluidas sus `permissions`);
- `RolePermissionOverride`;
- `Customer`;
- las suscripciones existentes.

Tampoco crea `AgentInstance`, `AgentChannel` ni credenciales.

**Corrección de `_advance_business_to_trialing`:** ahora solo pasa a `trialing` los negocios `onboarding` y `pending_activation`, es decir los que nunca se activaron. No toca los `active`, `trialing`, `past_due`, `suspended` ni `canceled`. Esto también corrige el alta original: antes degradaba a un `active` y podía reactivar uno `suspended`.

**Decisión sobre negocios no operativos:** este endpoint solo acepta negocios `active` o `trialing`. Así su estado global nunca cambia. Los negocios `onboarding` y `pending_activation` quedan rechazados para no "activarlos" de forma lateral. Si se quiere habilitarlos, hay que decidirlo en otra etapa.

## 4. Atomicidad y concurrencia

**Orden de locks:** Business → SubscriptionV2. Lo toman tanto `add_service_to_client` como `grant_complimentary_access`.

**Contenido de la transacción:** se crean juntas:
- la suscripción nueva;
- el beneficio bonificado;
- la política Custom con su `ReceptionAIUsagePolicyChange` (auditoría autoritativa de la política);
- la auditoría administrativa obligatoria.

Si cualquier paso falla, se revierte todo. Hay tests que hacen fallar la política y la auditoría, también por HTTP con un 500 sin persistir nada.

**Concurrencia real:** se probó con `TransactionTestCase` y dos hilos, cada uno con su conexión:

| Altas simultáneas | Resultado |
|---|---|
| Recepcionista y Turnos IA | 1 OK y 1 `incompatible_ai_service` |
| Recepcionista dos veces | 1 OK y 1 conflicto de duplicado |
| Recepcionista y Turnos Pro | ambas OK |

Sin los locks, los dos primeros tests fallan (verificado de forma temporal).

## 5. Auditoría

`ADMIN_COMPLIMENTARY_ACCESS_GRANTED` pasó a escribirse con `record_platform_action` (F4), que es estricto: si falla, revierte la operación. Antes lo escribía un helper best-effort. Es un solo evento por alta, sin duplicados.

- Se usa la acción existente, así que no hace falta migración.
- `actor` es el superadmin.
- `details` registra:
  - `operation`: `client_service_added`, o `client_provisioning` en el alta de clientes nuevos;
  - Business y suscripción: `business_id`, `business_status`, `subscription_id`, `service_type`, `plan_code`;
  - tier y cupo: `usage_tier`, `custom_included_sessions`, `custom_policy_id`;
  - vigencia: `current_period_start`, `current_period_end`;
  - motivo: `reason`.
- No registra secretos, tokens ni payloads crudos.

## 6. Protección de continuidad de cupos

El motor cuenta sesiones por `(business, usage_period_start, usage_period_end)` y no se modificó. Una suscripción de IA nueva arranca sus períodos desde su propio inicio. Por eso, si se otorga mientras sigue vigente un período que ya tiene consumo contado, arrancaría el contador desde cero.

**Regla aplicada a toda alta de IA** (Recepcionista o Turnos IA): se rechaza con `ai_usage_period_overlap` si existe algún `AppointmentAIUsageSession` del Business con `usage_period_end > complimentary_start`. Esto vale para cualquier suscripción, incluidas las canceladas y las de la otra fuente de IA.

**Restricciones temporales que impone:**
- Para volver a otorgar IA, el inicio debe ser igual o posterior al fin del último período con consumo.
- Las altas que no son de IA ignoran este historial.
- Un negocio sin consumo previo no tiene ninguna restricción. Por ejemplo, una fuente cancelada sin consumo no bloquea la otra.

## 7. Tests y resultados

**Suite nueva:** `accounts/tests/test_admin_clientes_add_service_02f5.py`, con 23 tests en verde. Cubre:
- Gestión activa más Recepcionista fijo y Custom;
- Recepcionista con Turnos Base y Pro, en los dos órdenes;
- preservación del Business, owner, usuarios, overrides, clientes y suscripción previa de Mercado Pago;
- negocio `trialing`;
- beneficio futuro (el resolvedor de IA lo ignora hasta que empieza);
- suscripción cancelada no reutilizada;
- exclusión de IA en los dos sentidos;
- duplicados, también del servicio principal;
- continuidad de cupos (misma fuente, fuente cruzada, inicio exacto en el borde, servicios que no son de IA);
- Business inexistente, sucursal y estados no operativos;
- rollback por fallo de la política, de la auditoría y por HTTP;
- regla de avance de estado para cada estado;
- payload estricto y reutilización de los validadores;
- permisos (operations, support y content_admin reciben 403, sin sesión 401/403, owner del negocio 403);
- checkout público todavía bloqueado;
- tres carreras con hilos reales.

**Regresión dirigida:** 1657 tests en 411 s, sobre Postgres descartable. Incluye:
- todo `apps.accounts` (provisioning, auth, F4);
- 16 módulos de billing (beneficios, políticas Custom, IA, runtime, admin);
- 10 módulos `appointments/tests/test_ai_usage*`;
- RBAC y guards de leads;
- `business/test_branding_permissions`.

Hay 48 fallos (23 F y 25 E), los mismos que en el baseline. Esa lista ya se había comparado con `7b7ca57` en F4 y coincide test por test. Son de POS access code, empleados, birth_path, refinement scope, MFA de admin y notificaciones de billing. Los módulos agregados en esta etapa pasan todos, así que no hay fallos nuevos respecto de `262b587`.

**Django:** `check` sin issues y `makemigrations --check` sin cambios. No hay migraciones.

## 8. Riesgos pendientes

- **Otros caminos de escritura (§2):** checkout, cambio de plan y webhooks de Turnos IA no aplican la exclusión con Recepcionista. Para protegerlos hay que pasar la regla a esos servicios o crear una restricción en la base de datos.
- **Enforcement por servicio (02F7):** si el estado global del Business cambia por otro servicio (por ejemplo, vence el beneficio de Gestión), puede bloquear el consumo de Recepcionista. No se modificó el enforcement ni los asientos multiservicio.
- **Negocios `onboarding` y `pending_activation`:** quedan rechazados. Habilitarlos requiere decidir cómo cambiar su estado de forma explícita.
- **Re-otorgar IA después de un período con consumo:** obliga a esperar a que termine el período. La alternativa es heredar el anclaje del período, lo que exige cambiar el motor.
- **Sin idempotencia general ni MFA por acción:** un doble envío del mismo servicio queda cubierto por la regla de duplicados, pero no hay idempotencia general.
- **Sin interfaz en el panel:** falta el frontend del endpoint y el detalle de cliente multiservicio (02F6).

## 9. Commits y HEAD final

- `7003d3f` fix(billing): complimentary grants lock the Business, keep AI sources exclusive and never downgrade
- `cdf736e` feat(accounts): add a complimentary service to an existing client
- `56171aa` test(accounts): cover adding services to existing clients
- docs(prod): este reporte

El HEAD final es el commit de este reporte, respaldado en `origin/feat/recepcionista` sin force push.
