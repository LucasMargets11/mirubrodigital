# PROD-02F5.1: Protección transversal de la exclusión comercial IA

- **Fecha:** 2026-11-26
- **Repo y rama:** `mirubrodigital-release`, `feat/recepcionista`
- **Baseline:** `a579b25`
- **Bot:** `5eb3dda`, sin cambios
- **Referencia:** `docs/PROD02F5_INCORPORACION_SERVICIOS_COMERCIOS_EXISTENTES.md`

## 1. Regla compartida

La regla vive en un único lugar: `billing/services/ai_commercial_rules.py`. Ningún camino tiene una copia propia.

Funciones que expone:

- `find_ai_commercial_conflict(...)`: devuelve el conflicto o `None`.
- `assert_ai_source_allowed(...)`: lanza el conflicto si existe.
- `is_ai_source(...)`: indica si un par servicio/plan es fuente IA.

Los errores son `IncompatibleAISourceConflict` y `AIUsagePeriodOverlapConflict`. Ambos heredan de `ValueError` y tienen un atributo `.code` con `incompatible_ai_service` o `ai_usage_period_overlap`.

**Fuentes IA:** son las de `ai_source.AI_SOURCES`, es decir `reception/reception` y `appointments/appointments_ai`.

**Exclusión.** Se aplica en ambos sentidos. Una fuente IA no se abre si existe otra que esté en alguno de estos casos:

- Una suscripción de la otra fuente en cualquier estado distinto de `canceled`. Esto incluye `checkout_pending`, `trialing`, `past_due` y `suspended`.
- Si lo pedido es Recepcionista: una **compra de Turnos IA en curso**. Cuenta un `AppointmentsCheckout` de `appointments_ai` en estado `linked`, o `pending` sin vencer. También cuenta un `PendingSubscriptionChange` hacia `appointments_ai` en estado `pending_payment`, `processing` o `scheduled`. Sin esto, la Recepcionista otorgada mientras el cliente paga convertiría ese pago en un conflicto manual. Lo detectó el test de concurrencia.

**Continuidad de cupos (de F5).** Una fuente IA nueva no puede empezar mientras exista consumo ya contado (`AppointmentAIUsageSession`) en un período que sigue vigente a su inicio. El consumo de la propia suscripción no se cuenta, así que las renovaciones, recuperaciones y cambios de tier dentro de Turnos IA nunca se bloquean. No se tocó el motor de conteo.

**Compatibles:** Turnos Base (`appointments`) y Turnos Pro (`appointments_pro`) conviven con Recepcionista, igual que Gestión y el resto.

**Lock.** La regla exige estar en una transacción; fuera de ella lanza `RuntimeError`. Quien la llama debe tener tomado el lock del Business. El orden es siempre Business → SubscriptionV2 / checkout / cambio. El activador central ahora también toma el Business primero.

## 2. Caminos protegidos

| Camino | Momento | Comportamiento ante conflicto |
|---|---|---|
| `grant_complimentary_access`: alta de clientes (F2–F4) y alta de servicios (F5) | Bajo lock | Usa la regla compartida y mantiene su taxonomía: `incompatible_ai_service` / `ai_usage_period_overlap` (409) |
| `create_appointments_checkout`: vista interna y vista pública | Antes de llamar a Mercado Pago | 409 con `{code, detail}`. No se crea checkout ni plan en MP |
| `apply_appointments_preapproval`: webhook de preapproval y reconciliación del checkout | Antes de crear la `SubscriptionV2` | No se abre la suscripción. El checkout queda `failed` con `failure_code` igual al código de la regla y guarda `provider_preapproval_id`. La delivery queda `processed` |
| `finalize_appointments_authorized_payment`: webhook de pago, recuperación de pagos huérfanos, reconciliación de facturas | Después de los locks y antes de activar | Se registra con `_record_appointments_checkout_conflict(failure_code=...)` y no se activa. La factura se conserva |
| `activate_subscription_from_invoice`: activador central de webhook, `reconcile_session`, `reconcile_subscription`, `reconcile_invoice_event` y finalización | Bajo lock Business → SubscriptionV2 | Devuelve `False` y registra un log ERROR. Continuidad solo en la primera activación (`checkout_pending`) |
| Webhook genérico (`MpCheckoutSession`) | Después del activador | Deja en la delivery una nota `incompatible_ai_service: activation blocked … manual review required` |
| Reconciliación (3 puntos de activación) | Después del activador | `result['error']` con el código y el aviso de revisión manual |
| `request_appointments_change`: paso de Base/Pro a IA | Al pedir el cambio | 409 `{code, detail}` en la vista. No se crea `PendingSubscriptionChange` |
| `prepare_appointments_provider_change` | Antes de cambiar el precio en Mercado Pago | Lanza el conflicto. MP no se toca |
| `apply_appointments_change`: aplicación inmediata, por pago o en la renovación | Bajo lock | El cambio queda `blocked` con `requires_resolution` y `resolution_details={code, conflicting_subscription_id}`. La suscripción conserva su plan. La renovación sigue con el plan actual |
| Pago de upgrade (`payment_webhook._apply_billing_payment`) | Antes de `prepare` | El cambio queda `blocked` y conserva `mp_payment_id`. Se crea el `PaymentAttempt` y el `BillingEvent` queda `error` con el código. MP no se toca y no hay devolución |

Revisé otros caminos que escriben suscripciones; no abren fuentes IA:

- `billing/service_activation.py` (QR reviews), `commercial/apply.py`, `commercial_views.py`, `billing/views.py` (Gestión) y `reviews_views.py`.
- `_upsert_subscription_v2` del webhook genérico y el `get_or_create` de `reconcile_subscription`. Pueden crear una fila `checkout_pending` con el `default_service` del negocio, pero activarla pasa siempre por el activador central, que está protegido.
- El comando `backfill_subscriptions`, que es operativo y manual.

Hoy no existe checkout de Recepcionista: el producto sigue inactivo y no se habilitó. El checkout público de Turnos también sigue inactivo, así que el único camino real es el interno.

## 3. Manejo de conflictos financieros

- Ningún evento financiero se pierde. Las validaciones nuevas nunca lanzan `WebhookPermanentError` dentro de la transacción donde se crea el `BillingInvoiceEvent`, porque eso lo revertiría. En su lugar usan los mecanismos que ya existían:
  - el conflicto de checkout (`failed` + `failure_code`);
  - el estado `blocked` de `PendingSubscriptionChange`;
  - `BillingEvent` en `error`;
  - la nota en la delivery;
  - `result['error']` en la reconciliación.
- No se crearon estados financieros nuevos ni migraciones.
- Nunca se cancela, devuelve ni modifica un pago. Tampoco se cancela nada en Mercado Pago.
- **Resolución manual.** Hay que elegir qué fuente se queda:
  1. Si se da de baja la otra (por ejemplo, revocando la Recepcionista), se reprocesa el evento. Para un webhook se usa `retry_mp_webhooks --id … --revive-dead-letter`, o se reintenta la reconciliación o el cambio. En el upgrade, la rama `approved` vuelve a aplicar.
  2. Si no, el pago se devuelve fuera del sistema, por el canal de soporte o Mercado Pago, como se hace hoy.

  Casos que requieren esta resolución:
  - un checkout `failed/incompatible_ai_service` con factura cobrada;
  - un `PendingSubscriptionChange` `blocked` con `resolution_details.code`;
  - una delivery con la nota de revisión manual.

## 4. Concurrencia

Todos los caminos serializan sobre la fila del Business. Se probó con `TransactionTestCase` y dos hilos reales, cada uno con su conexión:

| Carrera | Resultado |
|---|---|
| Alta de Recepcionista y checkout de Turnos IA | Uno OK y el otro conflicto. Nunca quedan los dos |
| Alta de Recepcionista y cambio de Turnos Pro a IA | Uno OK y el otro conflicto. Nunca quedan los dos |
| Carreras de F5 (Recepcionista y Turnos IA, duplicados) | Siguen en verde |

En la primera corrida, las dos carreras dieron "ok/ok" porque una compra en curso no era una `SubscriptionV2`. Se corrigió con la regla de compras en curso del punto 1.

## 5. Tests y resultados

**Suite nueva:** `billing/tests/test_ai_commercial_exclusion_02f51.py`, con 25 tests en verde. Cubre:

- **Checkout:** Recepcionista activa más checkout de Turnos IA (servicio y endpoint interno 409, sin llamar a MP); Base y Pro compatibles; continuidad de cupo.
- **Webhooks y reconciliación:**
  - preapproval incompatible (no abre suscripción, guarda la correlación);
  - pago posterior conservado (factura `authorized`, sin activar, Recepcionista intacta);
  - pago de checkout ya vinculado retenido;
  - activación genérica bloqueada con nota en la delivery;
  - reconciliación con error reportado;
  - pago de Turnos Pro junto a Recepcionista que se activa normalmente.
- **Lifecycle:** cambio de Base/Pro a IA rechazado; Base → Pro sin cambios; cambio pendiente retenido si la Recepcionista aparece antes de aplicarse; upgrade pago retenido con `PaymentAttempt`, `BillingEvent` en error y MP intacto.
- **Continuidad:** renovación y recuperación desde `past_due` de la misma suscripción IA con su propio consumo; cambio de tier dentro de Turnos IA.
- **Compras en curso:** checkout abierto bloquea la Recepcionista; checkout vencido no bloquea; cambio pendiente bloquea; checkout Base no bloquea.
- **Regla compartida:** la taxonomía del grant se mantiene; falla fuera de una transacción; el resolvedor sigue fallando cerrado (`ambiguous_ai_source`) ante datos legados.
- **Concurrencia:** dos carreras con hilos reales.

Las 23 de F5 siguen en verde.

**Regresión dirigida**, sobre Postgres descartable:

| Conjunto | Tests | Fallos |
|---|---|---|
| Checkout, lifecycle, webhooks, reconciliación, cancelación, promo y emails (19 módulos de billing más `customers` s7b/s7c) | 462 | 17, idénticos test por test a `a579b25` (14 `test_cancellation`, 2 `test_appointments_commercial_v2`, 1 de migración 0023) |
| Provisioning (todo `test_admin_clientes_*`), beneficios, políticas Custom, IA (16 módulos de billing más 10 `test_ai_usage*`) y guards de leads | 988 | 2 `test_admin_notification_billing_integration`, ya presentes en el baseline |
| RBAC (`test_reception_rbac_02c`, `test_role_permission_override_enforcement`, `catalog.test_rbac`, `leads.test_rbac_entitlements`, `business.test_branding_permissions`) | 92 | 2 `catalog.test_rbac`, idénticos en `a579b25` |

No hay fallos nuevos frente a `a579b25`.

**Django:** `check` sin issues y `makemigrations --check` sin cambios. No hay migraciones.

## 6. Riesgos pendientes

- **Comprobación por proceso:** la exclusión se aplica en cada proceso, no con una restricción de la base de datos. Cualquier escritura directa (shell, admin de Django, scripts) la saltea; en ese caso el resolvedor IA sigue fallando cerrado. Una restricción en la base es posible, pero exige una migración y revisar los datos existentes.
- **Pago ya cobrado en conflicto:** se retiene y queda para revisión manual; no se devuelve solo. Falta una vista de administración que liste estos casos. Hoy se encuentran por `failure_code`, `resolution_details`, `BillingEvent` en error o las notas de las deliveries.
- **Compras en curso:** un checkout `linked` que nunca se paga bloquea la Recepcionista hasta que alguien lo cierre. Los checkouts `pending` vencidos ya no bloquean.
- **Fila pendiente de Turnos IA:** una `checkout_pending` de un checkout abandonado sin cancelar también cuenta como no cancelada y bloquea la Recepcionista. Es la misma regla de F5.
- **`prepare_appointments_provider_change`:** si encuentra el conflicto (carrera mínima en la misma request), la vista responde el 502 genérico existente. MP no se toca.
- **Fuera de alcance:** enforcement por servicio (02F7), MFA por acción e idempotencia general.

## 7. Commits y HEAD

- `542f7c2` feat(billing): single shared AI commercial rule (Recepcionista vs Turnos IA)
- `f3098b4` fix(billing): enforce the AI commercial rule on every subscription write path
- `74e9166` test(billing): cover the AI commercial rule across checkout, webhooks, reconciliation and lifecycle
- docs(prod): este reporte (HEAD final, respaldado en `origin/feat/recepcionista` sin force push)
