# TURNOS PUBLIC 03B3A — alineación de usuarios secundarios

## Causa y fuente de verdad

`billing.plans.get_seat_limit()` usaba únicamente `PLAN_SEAT_LIMITS`, que no contiene los códigos canónicos `appointments`, `appointments_pro` ni `appointments_ai`. Los tres caían al fallback histórico de 2; ese valor solo coincidía accidentalmente con Turnos Base.

Para los planes incluidos en `appointments_plans.PLAN_CODES`, el límite ahora se obtiene de `canonical_pricing.get_plan(plan_code)['secondary_users_included']`. Es el mismo catálogo consumido por `resolve_appointments_subscription_config()`. La cuota no se deriva de `usage_tier`; `appointments_ai` mantiene 5 con `ai_300`, `ai_1500` y `ai_3000`.

`appointments_base` no se promovió ni se normalizó: permanece fuera del catálogo canónico de Turnos y conserva el fallback histórico 2. Los límites estáticos legacy y de otras verticales permanecen intactos.

## Comportamiento

| Plan | Usuarios secundarios incluidos |
|---|---:|
| Turnos Base (`appointments`) | 2 |
| Turnos Pro (`appointments_pro`) | 5 |
| Turnos IA (`appointments_ai`) | 5 |

- El owner no consume asiento.
- Cada Membership secundaria cuenta una vez según la consulta existente; un rol profesional con login consume un asiento.
- Un profesional de agenda sin Membership/login no consume un asiento.
- `appointments_extra_professional` solo amplía la cuota de profesionales. Pro con 3 adicionales conserva 5 usuarios secundarios.
- No se modificaron roles, permisos, checkout, precios, tiers, UI, ni el estado inactivo del producto `appointments`.
- Enforcement, servicios de creación y `seat_info` reutilizan `get_seat_limit()`. La Membership solo se crea cuando `resolve_subscription()` concede acceso; no se amplían los accesos para suscripciones suspendidas, vencidas o sin suscripción.

## Concurrencia

La comprobación ocurría en `pre_save`, pero el bloqueo de la transacción que rodea la comprobación e inserción no estaba serializado por negocio. Las nuevas Membership secundarias ahora bloquean la fila del negocio HQ con `select_for_update()` dentro de una transacción que abarca el `save()` y su señal. El conteo y el insert quedan así dentro del mismo bloqueo; las Membership owner siguen excluidas.

Una prueba PostgreSQL concurrente intenta crear tres usuarios para Turnos Base: dos obtienen los asientos y el tercero es rechazado.

## Archivos cambiados

- `services/api/src/apps/billing/plans.py`: delega los límites de planes canónicos de Turnos al catálogo; conserva el mapa y fallback legacy.
- `services/api/src/apps/accounts/models.py`: serializa la creación de Membership secundaria por negocio.
- `services/api/src/apps/accounts/tests/test_seat_limits_v2.py`: cobertura de límites efectivos, endpoint, owner, profesional con/sin login, suscripción sin acceso, legacy y concurrencia.
- `services/api/src/apps/billing/tests/test_appointments_commercial_v2.py`: consistencia con el resolver comercial, independencia de tiers y separación del add-on profesional.
- `services/api/Dockerfile`: desactiva la carga de `.env` en las etapas Docker.

## Validación

- API Docker basada en la imagen oficial `python:3.12-slim`; runtime ejecutado como `appuser`.
- `.env` continúa excluido del contexto por `.dockerignore`; se comprobó su ausencia en la imagen. `PYTHON_DOTENV_DISABLED=1` quedó definido en las etapas Docker.
- Build de la imagen runtime completado, incluyendo `collectstatic` (162 archivos).
- PostgreSQL 16 desechable; no se contactó a Mercado Pago ni a otro proveedor.
- `python manage.py check`: sin problemas.
- `python manage.py makemigrations --check --dry-run`: `No changes detected`.
- 41 pruebas focalizadas de accounts/membership, cuotas profesionales, catálogo, tiers IA, legacy, suscripciones suspendidas, endpoint de seats y concurrencia: pasan.
- No se tocó frontend. No se generaron migraciones.

## Invariantes de cierre

Base=2, Pro=5 e IA=5; el tier IA no altera seats; owner excluido; profesional con login incluido en la cuenta; profesional sin login excluido; extra professionals no suman seats; sexto usuario rechazado en Pro/IA; legacy y otras verticales conservados; producto `appointments` inactivo; sin venta de usuarios extra.
