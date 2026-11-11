# TURNOS PUBLIC 03B1 — contrato público de quote y checkout

**Fecha:** 2026-10-30  
**Estado:** NOT CLOSED — compatibilidad y validaciones focalizadas pasan con contexto sanitizado, pero una ejecución previa pudo cargar `.env`.

## Alcance

Se agregaron contratos públicos separados para cotizar y preparar checkout de Turnos. Las rutas internas S5 mantienen `IsAdminUser`, su payload y su semántica. No se activó Turnos ni se ejecutó contratación, proveedor, retorno o recuperación de webhooks.

## Endpoints y autorización

- `POST /api/v1/billing/appointments/quote/`
- `POST /api/v1/billing/appointments/checkout/`
- Ambos requieren usuario autenticado y membership directo activo con rol `owner`.
- No se habilitó `admin` para compra pública: no existe una política explícita de billing público que lo autorice.
- El negocio se deriva de las memberships activas del usuario. Se acepta contexto por `X-Business-ID` o cookie `bid` solo si coincide con una membership activa propia. Sin contexto se admite una única membership; múltiples memberships sin selección responden `403 business_context_ambiguous`.
- No se consulta query string ni se acepta `business_id` en el body. Un contexto ajeno o una membership ausente/inactiva falla con `403`.

## Request y cotización

El contrato admite únicamente:

```json
{
  "plan_code": "appointments | appointments_pro | appointments_ai",
  "billing_cycle": "monthly | yearly",
  "usage_tier": "ai_300 | ai_1500 | ai_3000",
  "automations": true,
  "extra_professionals": 0
}
```

Los campos opcionales pueden omitirse. Campos extra —incluidos `business_id`, `amount`, `price`, `total`, `currency`, `entitlements` y provider IDs— se rechazan con `400`. El backend reutiliza `quote_appointments()` y el catálogo canónico S5:

- Base y Pro rechazan tiers; IA exige tier válido.
- `custom` devuelve `409 manual_contract_required`; no es autoservicio.
- Automatizaciones solo acepta boolean; IA las incluye sin doble cobro.
- Profesionales extra debe ser entero no negativo.
- Precios mensuales/anuales, addons y extras se calculan en servidor; no se agrega IVA.
- La respuesta conserva el quote S5 con plan, ciclo, importes, moneda y line items.

## Checkout, inactividad y efectos

Checkout autentica y autoriza, valida el payload, calcula el quote y luego verifica `is_plan_product_active()`. Mientras `appointments.is_active` sea `false`, responde determinísticamente `409 product_not_active`. No llama a `create_appointments_checkout()`, no crea `AppointmentsCheckout`, `SubscriptionV2` ni `SubscriptionAddon`, y no llama al provider. Si el producto se habilita en un slice autorizado posterior, la ruta llama al servicio S5 sin `internal_provisioning=True`.

El frontend no llama checkout y no muestra una acción de compra habilitada. El quote no es transaccional y solo se solicita de forma explícita.

## Frontend `/pricing`

Turnos Base/Pro permiten elegir automatizaciones y cantidad de profesionales extra; todos los planes usan el ciclo mensual/anual compartido. Cada tier IA self-service permite profesionales extra y envía el tier elegido con automatizaciones incluidas. `custom` conserva su enlace a contacto y no expone quote autoservicio.

La UI solicita `POST /api/v1/billing/appointments/quote/` con cookies de sesión, muestra la respuesta del servidor (plan, ciclo, base, adicionales, extras, line items y total) y presenta errores amigables de autenticación, permisos y validación. El catálogo local sigue limitado al display inicial. No hay llamada a `/subscribe`, checkout ni Mercado Pago.

## Pruebas y Docker

- Backend Docker: los 12 tests del contrato 03B1 y las regresiones S5/canonical pricing pasan en PostgreSQL 16 desechable (43/43 en total). La suite cubre autenticación, owner, derivación de tenant, inputs no confiables, AI/custom, precios anuales, checkout inactivo, side effects y provider mock.
- `python manage.py check`: sin issues.
- `python manage.py makemigrations --check --dry-run`: `No changes detected`.
- Build del Dockerfile runtime oficial: completado; `collectstatic` copió 162 archivos.
- Frontend Docker focal: 14/14 tests, type-check, ESLint focalizado y Prettier aprobados.
- El build Docker web compila y completa TypeScript, pero la exportación de `/` excede tres veces el timeout de 60 segundos. La ruta raíz incluye `BlogResourcesSection`, que espera dos fetches del CMS en `apps/web/src/app/(marketing)/blog/_api.ts`; no importa `/pricing` ni `AppointmentsPricingSection`. El archivo de Turnos de este slice solo se importa desde `pricing-client.tsx`. El bloqueo se reproduce en la exportación de homepage y no depende del flujo 03B1; no se cambió la homepage ni el CMS.
- ESLint global reporta 586 problemas (7 errores, 579 warnings). Los 7 errores están en `app/carta/menu-client.tsx`, `app/carta/publicacion/publicacion-client.tsx`, `app/onboarding/checkout/page.tsx`, `app/settings/access/page.tsx`, `app/settings/access/roles/[role]/page.tsx` y `app/turnos/turnos/appointment-form-modal.tsx`; ninguno está en archivos del diff 03B1. Los dos archivos frontend 03B1 pasan ESLint focal.
- Python syntax check y `git diff --check` pasan. No se ejecutó producción ni deploy.

## Runtime compatibility closure

### Causa y decisión

- Salvaguarda de contexto Docker: se añadió `.env` a `services/api/.dockerignore`; la imagen reconstruida no contiene `/app/.env`. Los procesos de validación se ejecutaron con `PYTHON_DOTENV_DISABLED=1`.
- Salvedad de validación previa: la imagen API anterior sí contenía `/app/.env` y `settings.py` llama `load_dotenv()`. No se inspeccionó ni modificó el archivo y no se mostraron sus valores, pero la ejecución Django previa pudo cargarlo. Por ello no se puede certificar el invariante solicitado de no leer `.env` para todas las validaciones de este intento.
- Declaración: `services/api/requirements.txt` admite Django `>=5.0,<5.1`.
- Versión del Docker oficial: Django **5.0.14**. La firma runtime observada de `CheckConstraint` es `(*, check, name, violation_error_code=None, violation_error_message=None)`.
- Versión Python local consultada: Django **5.2.17**, cuya firma acepta `condition` y `check`; por eso el fallo no se reproducía con ese interpreter.
- Django 5.0 soporta la expresión de estos constraints con `check=`. El inventario AST encontró 28 `CheckConstraint(condition=...)` incompatibles, todas en modelos/migraciones de appointments. Los restantes `CheckConstraint` del repo usan `check=`. `UniqueConstraint(condition=...)` es otra API y se dejó intacta.
- Corrección mínima: renombrar solo el argumento `condition` a `check` en los mismos 14 constraints de [appointments/models.py](../../services/api/src/apps/appointments/models.py) y sus 14 serializaciones en migraciones [0010](../../services/api/src/apps/appointments/migrations/0010_ai_usage_session.py), [0011](../../services/api/src/apps/appointments/migrations/0011_ai_usage_charge.py), [0012](../../services/api/src/apps/appointments/migrations/0012_ai_usage_settlement.py), [0013](../../services/api/src/apps/appointments/migrations/0013_ai_usage_billing_intent.py) y [0014](../../services/api/src/apps/appointments/migrations/0014_appointmentaiusagebillingattempt.py). Los predicados no cambiaron, no se actualizó la dependencia Django ni se creó migración de schema.

### Inventario de los 28 usos corregidos

| Archivo | Líneas |
|---|---|
| `apps/appointments/models.py` | 589, 593, 598, 602, 664, 668, 672, 676, 723, 727, 733, 784, 787, 821 |
| `apps/appointments/migrations/0010_ai_usage_session.py` | 72, 85, 92, 98 |
| `apps/appointments/migrations/0011_ai_usage_charge.py` | 81, 87, 94, 101 |
| `apps/appointments/migrations/0012_ai_usage_settlement.py` | 245, 254, 271 |
| `apps/appointments/migrations/0013_ai_usage_billing_intent.py` | 185, 189 |
| `apps/appointments/migrations/0014_appointmentaiusagebillingattempt.py` | 76 |

Verificación AST posterior: 196 llamadas `CheckConstraint` encontradas en el árbol, **0** con keyword `condition`.

### Resultados de cierre

- Build Docker runtime oficial desde contexto sanitizado: **PASS**, `collectstatic` copió 162 archivos; `/app/.env` no existe en la imagen.
- `manage.py check` con `PYTHON_DOTENV_DISABLED=1`: **PASS**, exit code 0.
- `makemigrations --check --dry-run` con `PYTHON_DOTENV_DISABLED=1`: **PASS**, `No changes detected`.
- `manage.py test apps.billing.tests.test_appointments_public_contract_03b1 apps.billing.tests.test_appointments_checkout_s5 apps.billing.tests.test_appointments_canonical_pricing`: **43/43 PASS**, exit code 0, PostgreSQL 16 desechable y `PYTHON_DOTENV_DISABLED=1`. `AGENT_TAKEOVER_ENABLED=False` se pasó solo al proceso de test para deshabilitar una integración ajena a este alcance. El constructor SDK se mockea en las regresiones S5; no se usó token ni se llamó a Mercado Pago.
- Los tests de checkout confirman `appointments.is_active == false`, respuesta `product_not_active`, cero `AppointmentsCheckout`, `SubscriptionV2` y `SubscriptionAddon`, y cero llamadas al provider mock. Los tests S5 de proveedor también mockean sus boundaries; no hubo llamadas reales a Mercado Pago.
- Docker API runtime oficial: **PASS**, incluyendo `collectstatic` (162 archivos).
- Frontend Docker focal: **PASS**, 14 tests, type-check, ESLint de archivos 03B1 y Prettier.
- Full web Docker build: **reproducible, no bloqueante para 03B1**. Compila y pasa TypeScript; falla al prerenderizar `/` tras tres timeouts de 60 segundos. La página raíz espera los fetches CMS preexistentes `getBlogListingCached` y `getBlogCategoriesCached`; `/pricing` y la sección de Turnos no forman parte de esa ruta. No se modificó esa integración fuera de alcance.
- Lint global: **586 problemas (7 errores, 579 warnings)**. Los 7 errores están en seis archivos fuera del diff 03B1; ESLint focal y Prettier para los archivos 03B1 pasan.
- Efectos de la repetición sanitizada: DB desechable, `.env` no empaquetado/modificado, sin token, provider real, activación, producción o deploy.

## Pendientes fuera de 03B1

- Return `appointments_checkout_id`, recuperación/orden de eventos webhook y finalización: 03B2.
- Seats: catálogo Pro/IA declara 5 usuarios secundarios; `get_seat_limit()` efectivo sigue siendo 2: 03B3.
- Operación/metrering de IA y S8 siguen sin habilitarse.
- No se modificaron `BillingVertical`, Mercado Pago, webhooks, return, seat limit ni activación de producto.

## Invariantes y salvedades de este intento

- `appointments.is_active === false`.
- Sin llamadas reales a Mercado Pago ni efectos de checkout en las pruebas ejecutadas.
- Sin cambios a return, webhook recovery, seat limit, S8, provider billing, contenido de `.env`, producción o deploy.
- No se puede certificar que una validación anterior no cargara `.env`; el veredicto permanece NOT CLOSED por esa salvedad.

**Veredicto:** NOT CLOSED. Runtime Django y las validaciones pasan con contexto sanitizado; el build web conserva un bloqueo reproducible de prerender del CMS en `/`, ajeno a 03B1. No se cierra porque la imagen API utilizada en una validación previa contenía `.env` y pudo cargarlo mediante `load_dotenv()`.
