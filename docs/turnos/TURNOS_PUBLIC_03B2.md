# TURNOS PUBLIC 03B2 — retorno, polling y recuperación

## Alcance e invariantes

Este slice completa la consulta del estado de un checkout público de Turnos, el retorno del navegador, la recuperación idempotente de pagos recibidos fuera de orden y la expiración local. No habilita la compra pública: `appointments.is_active` permanece en `false`, y el gate existente impide crear un checkout público mientras siga inactivo. No se habilitan seats ni S8, no se despliega y no se realizan llamadas reales a Mercado Pago.

## Estados y vencimiento

`AppointmentsCheckout` admite `pending`, `linked`, `active`, `failed` y `expired`. `expires_at` fija un TTL técnico de 24 horas desde la creación; la migración asigna esa fecha a checkouts históricos a partir de `created_at`, sin eliminarlos. `failure_code` conserva el motivo público del fallo.

Al consultar el estado o preparar otro checkout, se vencen localmente los checkouts `pending`/`linked` cuyo TTL terminó. La expiración conserva el historial y no cancela ni consulta recursos del proveedor. Si el checkout vencido tenía una suscripción todavía inactiva en `CHECKOUT_PENDING`, se cancela localmente para liberar el slot. Un pago autorizado válido puede completar la suscripción asociada aunque el checkout haya expirado.

El endpoint calcula `can_retry` solo para `failed`/`expired`, si el producto está activo y no hay ya una suscripción activa. `multiple_authorized_payments` no permite retry automático. Con el producto Turnos inactivo, el retry público permanece deshabilitado.

## Estado autenticado

`GET /api/v1/billing/appointments/checkouts/<uuid>/status/` requiere sesión autenticada y membership activa con rol `owner`. El negocio se deriva del contexto autorizado del usuario; no se acepta un `business_id` en la solicitud. Una consulta de otro tenant devuelve `404`.

La respuesta expone únicamente `checkout_id`, `status`, `plan_code`, `usage_tier`, `billing_cycle`, `subscription_status`, `can_retry` y `failure_code`; no incluye IDs, metadata ni URL del proveedor.

## Retorno del navegador

`/subscribe/return?appointments_checkout_id=<uuid>` consulta el endpoint anterior con cookies de sesión. Sondea inmediatamente y luego cada 2 segundos, con un límite de 60 segundos; limpia el intervalo, timeout y solicitud al terminar o desmontarse. `active`, `failed` y `expired` son estados terminales para el polling. Errores transitorios de red conservan la consulta hasta el timeout.

El retorno presenta mensajes y acciones acordes al estado, ofrece ir a Turnos cuando está activo, soporte cuando falla y planes cuando vence. Conserva los flujos anteriores basados en `checkout_session_id` e `intent_id`.

## Webhooks fuera de orden e idempotencia

La correlación usa el `provider_preapproval_id` persistido y valida el checkout, la referencia externa, el plan, el snapshot de cotización y el importe/moneda autoritativos. Si llega primero el pago autorizado, se conserva su invoice y se finaliza al quedar disponible la preapproval correlacionada; si llega primero la preapproval, el pago posterior completa el mismo flujo.

Un finalizador transaccional común aplica el pago autorizado, activa la `SubscriptionV2`, actualiza sus addons desde el snapshot y marca el checkout activo. Los IDs únicos de invoice y las actualizaciones idempotentes evitan duplicar la aplicación en reintentos o reconciliación. La reconciliación reutiliza el mismo finalizador.

Antes de activar, el servicio detecta otros checkouts con pagos autorizados o una suscripción ya activa. Registra el conflicto (`multiple_authorized_payments` cuando corresponde), conserva cualquier suscripción ya activa y no inicia reembolsos automáticos.

## Validación

- Backend en Docker con PostgreSQL 16 desechable: 57 pruebas focalizadas pasan, incluidos contrato 03B1, checkout S5, precios canónicos, status/expiración, orden inverso, reconciliación y concurrencia.
- `manage.py check` y `makemigrations --check --dry-run` pasan; no hay migraciones pendientes.
- Frontend: 10 pruebas del retorno, type-check, ESLint focalizado y Prettier para ambos archivos.
- Los límites del proveedor están mockeados en las pruebas; no se contactó a Mercado Pago real.
- Las pruebas y builds de este slice no habilitan Turnos ni cambian el gate de compra pública.
