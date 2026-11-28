# PROD-09D1 — Extensión de vigencia y continuidad comercial de Recepcionista IA

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `0d73840` · Bot
`de7e932` sin cambios. Solo backend. Una migración (solo de `choices`); sin
modelos, dependencias ni endpoints de pago.

## 1. Implementación

| Pieza | Archivo | Qué hace |
|---|---|---|
| Servicio de extensión | `billing/complimentary_access_service.py` → `extend_complimentary_access` | Mueve `current_period_end` de la misma `SubscriptionV2`. Valida, bloquea, extiende la política custom y audita, todo en una transacción |
| Extensión de política | `billing/services/reception_ai_policy.py` → `extend_reception_custom_policy` | Extiende solo la versión activa alineada con el vencimiento anterior. Escribe fila append-only `ReceptionAIUsagePolicyChange(action='extended')` |
| Continuidad del cupo | `appointments/services/ai_usage.py` → `_count_used_sessions` | Ciclo bonificado: cuenta las sesiones con el mismo inicio de período y fin dentro del período (ver §3) |
| Actor y vista | `accounts/admin_client_service_addition.py` → `extend_client_service`; `AdminClientSubscriptionExtensionView`; `AdminClientServiceExtensionInputSerializer` | Superadmin reverificado (`_authorize_actor`) y mapeo de errores |
| Baja ⇒ pausa | `leads/services/receptionist_config.py` → `pause_attention_for_canceled_subscription`; `billing/cancellation_service.py` | Llamado desde `cancel_subscription_immediately` y `execute_cancellation`, solo para `service_type='reception'` |
| Migración | `billing/0030_reception_ai_policy_change_extended` | `AlterField` de `choices` en `ReceptionAIUsagePolicyChange.action`. Sin cambio de esquema en la base |

## 2. Contrato del endpoint

`POST /api/v1/platform-admin/clients/<business_id>/subscriptions/<subscription_uuid>/extension/`

- **Permisos:** `IsPlatformStaff` + `HasInternalRole(['superadmin'])`. El
  servicio vuelve a verificar el actor desde la base: `operations` o un
  usuario de comercio dan 403.
- **Body:** solo estos dos campos. Cualquier otro da 400 `Campo no permitido.`

```json
{ "complimentary_end": "2027-01-31T23:59:00-03:00", "reason": "Extensión piloto" }
```

`complimentary_end` es un `DateTimeField` de DRF, con la misma convención que el
alta (02F2/02F5). Con zona explícita se respeta. Sin zona se interpreta en
`TIME_ZONE`. La respuesta devuelve los instantes almacenados.

**200**

```json
{
  "business": { "id": 7, "status": "trialing", "service_type": "reception", "default_service": "reception" },
  "subscription": { "id": "…", "service_type": "reception", "plan_code": "reception",
                    "usage_tier": "reception_custom", "provider": "manual", "status": "trialing",
                    "current_period_start": "…", "current_period_end": "<nuevo>" },
  "custom_policy": { "id": "…", "included_sessions": 8, "valid_from": "…", "valid_until": "<nuevo>" },
  "extension": { "previous_end": "…", "new_end": "…" }
}
```

`custom_policy` es `null` en los tiers fijos, o si la política vigente no
tiene fin (no hay nada que extender).

**Errores:** `{code, detail, field}`, sin escrituras.

| HTTP | `code` | Caso |
|---|---|---|
| 400 | `invalid_end` | Fecha igual o anterior al vencimiento actual, o fecha sin zona válida a nivel de servicio |
| 400 | `invalid_reason` | Motivo vacío o de más de 255 caracteres |
| 400 | (errores de serializer) | Faltan campos, hay campos desconocidos o la fecha es inválida |
| 403 | `unauthorized_provisioning_actor` | El actor no es superadmin |
| 404 | `client_not_found` | No es un Business HQ (incluye sucursales) |
| 404 | `subscription_not_found` | La suscripción no existe o es de otro negocio |
| 409 | `subscription_not_extendable` | No es Recepcionista (`reception`/`reception`) |
| 409 | `subscription_canceled` | La suscripción está cancelada |
| 409 | `subscription_suspended` | La suscripción está suspendida. **No se reactiva** |
| 409 | `subscription_not_complimentary` | No es una bonificación manual (Mercado Pago, trial con `trial_ends_at`) |
| 409 | `cancellation_scheduled` | Tiene `cancel_at_period_end` |
| 409 | `subscription_not_current` | Vencida o todavía sin comenzar |
| 409 | `custom_policy_not_extendable` | Política custom revocada, ausente o no alineada con el vencimiento |

**Qué no modifica:** `plan_code`, `usage_tier`, `current_period_start`,
`provider`, `status`, `is_active`, `trial_ends_at`, `Business.status` ni la
atención automática. No crea otra suscripción.

**Concurrencia:** orden de locks `Business → SubscriptionV2 → políticas`, el
mismo del motor, de `authorize` y de 02E2B. Dos extensiones simultáneas se
serializan. Si la segunda pide una fecha que ya no es posterior, da
`invalid_end`. Una extensión simultánea con consumo, o una baja simultánea con
autorización, terminan sin deadlock.

**Auditoría obligatoria**, en la misma transacción: `AccessAuditLog
PLATFORM_ADMIN_ACTION` con `operation: complimentary_extension`. Detalles:
suscripción, plan, tier, inicio, fin anterior y nuevo, motivo y la política o
cambio de política afectados. No incluye secretos. Si la auditoría falla, la
extensión entera se revierte.

## 3. Continuidad del consumo

**Riesgo encontrado.** El motor cuenta sesiones por clave exacta
`(usage_period_start, usage_period_end)`. En una bonificación, el último
período se recorta al vencimiento: `min(límite mensual, current_period_end)`.
Si se extiende con consumo ya registrado en ese período, la clave del período
en curso cambia de `(S, fin_anterior)` a `(S, límite mensual)`. El contador
volvería a 0 y daría un cupo nuevo completo. Se verificó: con el motor de
`HEAD` montado sobre el cambio, los tres tests de continuidad fallan con
`used=0` en lugar de 299, 10 y 4.

**Solución mínima.** Para el ciclo bonificado, `_count_used_sessions` cuenta
las sesiones con el mismo `usage_period_start` y
`usage_period_start < usage_period_end ≤ fin del período`. Los demás ciclos
(mensual, anual, Mercado Pago) siguen con la clave exacta, sin cambios.

- **No reinicia ni duplica el cupo.** Las sesiones de la clave corta siguen
  sumando. La sesión siguiente toma `session_ordinal = usados + 1` y, al
  agotarse, da `hard_cap_reached`, sin excedente.
- **No reescribe nada.** Sesiones, cargos y recibos quedan con su clave
  original.
- **El anclaje no cambia.** `current_period_start` está intacto y los límites
  mensuales son los mismos.
- **Preserva las ventanas abiertas.** La ventana de 24 h se reutiliza por
  conversación y suscripción, sin importar la clave.
- **Ninguna otra suscripción comparte ese inicio.** La guarda de solapamiento
  de 02F5 rechaza un alta de IA si hay sesiones con fin posterior a su inicio.
- **Si el período no estaba recortado**, su clave no cambia y el período
  siguiente empieza en 0, como siempre.

## 4. Plan personalizado (`reception_custom`)

- Se extiende solo la versión **activa** cuyo `valid_until` coincide con el
  vencimiento anterior: la vigente o una reducción programada.
  - El cupo, `valid_from` y las versiones anteriores no se tocan.
  - `valid_until` es el único campo mutable que el modelo permite. Es la misma
    vía que ya usan `change_reception_custom_allowance` y
    `cancel_scheduled_reception_custom_change`.
- **Reducción programada:** la versión vigente conserva su corte. La
  programada pasa a terminar en el nuevo vencimiento y sigue siendo
  cancelable. Al cancelarla, la vigente llega hasta el nuevo fin.
- **Políticas revocadas o reemplazadas:** nunca vuelven. Sin una versión
  activa alineada, da `custom_policy_not_extendable` y se revierte todo.
- **Versión sin fin** (`valid_until=null`): ya cubre la extensión. No escribe
  nada.
- **Atomicidad:** suscripción, política, fila de cambio y auditoría van en una
  sola transacción. Hay tests de rollback con falla de política y con falla de
  auditoría.

## 5. Atención automática en la baja

Este cambio cierra el riesgo que quedó registrado en PROD-09C1.

- **Cuándo pausa:** una cancelación definitiva de Recepcionista pone
  `automatic_attention_enabled=False` en la **misma transacción**.
  - Aplica a la baja inmediata del admin y a la baja programada que ejecuta la
    tarea.
  - Orden de locks `Business → SubscriptionV2 → ReceptionistConfig`.
- **Versionado y auditoría:** reutiliza `_save`, así que sube `version`.
  Registra `RECEPTIONIST_CONFIG_UPDATED` con `automatic_attention:
  paused_by_cancellation` y `subscription_id`.
  - Desde el admin, el actor es el admin.
  - Desde la tarea, `actor_type=SYSTEM` y `source=system`.
- **Si falla la pausa o su auditoría**, la baja se revierte.
- **Sin configuración, o con la atención ya pausada:** no escribe nada.
- **Recontratación:** una contratación posterior no toca la configuración, así
  que `authorize` responde `automatic_attention_disabled` hasta que un admin la
  habilite de nuevo.
- **Extender no cambia la atención:** ni la habilita ni la pausa.
- **Otros productos:** Turnos, Gestión y demás siguen igual. No hay lock de
  Business adicional ni pausa.

## 6. Componentes reutilizados

**Reutilizados:**
- `SubscriptionV2` (`current_period_end`).
- `is_complimentary_grant` y `complimentary_grant_active`.
- `_authorize_actor`.
- `record_platform_action`.
- Taxonomía de respuesta y `_service_addition_success_response` (02F5).
- `ReceptionAIUsagePolicy`/`ReceptionAIUsagePolicyChange`, más `_lock`,
  `_require` y `_audit` (02E2B).
- `_save` y `_audit` de la configuración (09C1).
- `cancel_subscription_immediately` y `execute_cancellation`.

**Creados:**
- Dos funciones de servicio.
- Una vista con su serializer.
- Un helper de pausa.
- La acción `extended`.
- Una migración solo de `choices`.

**Evitados:**
- Modelo de extensión.
- Re-anclaje de períodos.
- Reescritura de sesiones o cargos.
- Una nueva versión de política futura, que habría bloqueado los cambios de
  cupo como "cambio programado pendiente".
- Acciones nuevas de `AccessAuditLog`, que no tienen migración.

## 7. Tests

**Archivo:** `billing/tests/test_complimentary_extension_09d1.py`, 25 tests.
Todos pasan sobre PostgreSQL 16 descartable (tmpfs) y Redis 7.

**Qué cubren:**
- **Extensión fija:** se conserva la identidad comercial, hay auditoría y la
  atención no cambia.
- **Validaciones:** fechas inválidas y motivo inválido.
- **Suscripciones rechazadas:** ajena, cancelada, suspendida, vencida, sin
  comenzar, de Mercado Pago, trial, con baja programada, de otro producto o de
  una sucursal. Ninguna escribe.
- **Actor:** se rechazan `operations` y los usuarios de comercio.
- **Consumo:**
  - Período recortado con 299/300: después de extender quedan 299, se
    reutiliza la ventana, entra el último incluido (ordinal 300) y luego
    `hard_cap_reached`, sin excedente. Las filas no cambian.
  - Período sin recorte: la clave no cambia y el período siguiente empieza en
    0.
  - Consumo después del fin anterior.
- **Política personalizada:**
  - Extensión de la versión alineada, con cupo conservado.
  - Reducción programada preservada, y cancelable después.
  - Política revocada: no se reactiva.
- **Rollback:** con falla de auditoría y con falla de política.
- **Aislamiento entre negocios.**
- **Endpoint:** contrato, errores y permisos.
- **Baja:**
  - Desde el admin: pausa y la recontratación no la reactiva (`authorize`
    responde `automatic_attention_disabled`).
  - Programada: pausa como SYSTEM, y es idempotente.
  - Sin configuración o ya pausada: no hay auditoría.
  - Rollback si falla la pausa.
  - Turnos no se ve afectado.
  - Aislamiento entre negocios.
- **Concurrencia** (`TransactionTestCase`): extensión + extensión,
  extensión + consumo, baja + autorización.

**Regresión:** ver §9.

## 8. Riesgos y pendientes

- **Liquidación offline (S8D, solo Turnos IA con cargos).** Si se extendió con
  sesiones en el período recortado, ese mes de Recepcionista queda con dos
  claves solapadas, `(S, fin_anterior)` y `(S, límite)`.
  - El descubrimiento de períodos las marca como `incomplete_or_ambiguous_evidence`
    y no las liquida.
  - El impacto económico es nulo: la bonificación nunca cobra y todos los
    cargos son `included` con monto 0. El historial queda intacto. Solo se
    registra un warning por corrida.
- **Sin endpoint de lectura del historial de extensiones:** la fuente son la
  auditoría y las filas `extended`. Sin UI: el frontend queda para un slice
  posterior.
- **Bonificaciones de Turnos IA:** no se pueden extender, por alcance. El
  cambio de conteo es inerte para ellas porque nunca tienen claves anidadas.
- **Bajas fuera del servicio de cancelación:** las de `appointments_checkout`
  y el webhook de Mercado Pago no pausan la atención. Hoy no aplican a
  Recepcionista, que no tiene checkout público ni Mercado Pago.
- **Sin despliegue.** Orden: Mi Rubro con la migración `billing/0030`. El bot
  no cambia.

## 9. Verificación

Todo corrió en PostgreSQL 16 descartable (tmpfs, `fsync=off`) con Redis 7 y
env de prueba propio.

| Suite | Resultado |
|---|---|
| `test_complimentary_extension_09d1` | 25/25 OK |
| Mismos tests de continuidad con `ai_usage.py` de `HEAD` montado | 3 FAIL (`used=0`): se confirma el reinicio que se corrige |
| `apps.billing` completo (1108) | 41 fallas/errores **idénticas** a `HEAD`. Se comparó contra un export limpio de `0d73840` sobre los 9 módulos afectados: `test_cancellation` (seat limit en `setUp`), `test_mp_integration`, `test_subscriptionv2_birth_path`, `test_v2_addon_parity`, `test_appointments_commercial_v2`, `test_webhook_delivery_lifecycle`, `test_admin_notification_billing_integration`, `test_backfill_subscriptions`, `test_reviews_downgrade` |
| Motor de consumo IA (`appointments` s8a–s8i + complimentary) y alta/add-service/RBAC (02C, 02F2–02F5, 03A, Turnos IA provisioning) | 446/446 OK |
| `apps.leads` (918) | 917 OK, 1 flake de orden |

Sobre el flake de `apps.leads`: es
`test_activity.test_close_is_single_event_with_outcome`, con dos eventos
creados en el mismo instante. El módulo da 26/26 al repetirlo, tanto con el
cambio como en `HEAD`.

- `manage.py check`: sin problemas.
- `makemigrations --check --dry-run`: `No changes detected`.
