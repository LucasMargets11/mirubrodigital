# TURNOS PUBLIC 03B-AUDIT — auditoría pre-activación

**Fecha:** 2026-10-30  
**Alcance:** auditoría estática de contratación, onboarding, billing, lifecycle y operación de MiRubro Turnos.  
**Veredicto:** bloqueado; Turnos no está conectado a una ruta de compra pública y hay gaps de retorno, recuperación de webhooks, cuotas de asientos y operación de IA.

## 1. Resumen ejecutivo

La presencia pública de Turnos y su catálogo informativo están implementados. También existen piezas backend para cotizar, crear un checkout Mercado Pago, registrar una `SubscriptionV2`, aplicar add-ons, resolver entitlements y operar cambios de plan. Sin embargo, esas piezas no componen hoy un flujo autoservicio completo:

1. `/pricing?service=appointments` es informativo. Sus enlaces no abren `/subscribe` ni llaman a quote/checkout.
2. Los endpoints de quote y checkout S5 son `IsAdminUser`, están bajo `internal/` y no forman parte del flujo normal de onboarding. El producto sigue inactivo.
3. El checkout genera un retorno con `appointments_checkout_id`, pero `/subscribe/return` solo procesa `checkout_session_id` o `intent_id`.
4. Si el webhook de pago llega antes que el de preapproval, el evento autorizado queda huérfano. La reconciliación genérica puede activar la suscripción cuando ya existe, pero no finaliza el `AppointmentsCheckout` ni aplica los add-ons S5.
5. No hay expiración ni limpieza de `AppointmentsCheckout` pendiente/viejo. Puede bloquear nuevos intentos del negocio.
6. El catálogo declara 5 usuarios secundarios para Pro/IA, pero `get_seat_limit()` no reconoce esos códigos y aplica el fallback de 2.
7. El acceso de IA depende de `AI_USAGE_METERING_ENABLED`; el contrato S8 indica que permanece apagado. El adaptador de cobro de overage siempre es `disabled`, y la homologación MP real sigue pendiente.
8. No se encontró un onboarding guiado de primer uso ni UI frontend para el lifecycle S6. Hay pantallas operativas para configurar manualmente horarios, profesionales, reservas públicas e integraciones.
9. IVA/impuestos no forman parte del quote ni de la presentación de Turnos. Sigue abierta la decisión comercial solicitada.

### Bloqueantes principales para activar

- Integrar un checkout público autenticado, con identidad del negocio derivada del membership y no confiada al cliente.
- Completar el retorno y la recuperación idempotente/ordenada de webhook para `AppointmentsCheckout`.
- Resolver el límite de usuarios secundarios Pro/IA (2 efectivos vs. 5 declarados).
- Homologar Mercado Pago en un slice autorizado posterior; esta auditoría no llamó al proveedor.
- Definir el tratamiento comercial de IVA y del overage de IA; no se toman decisiones nuevas aquí.
- No vender IA como funcional hasta habilitar y validar el metering/agente bajo un procedimiento operativo controlado.

### Alcance y método

Se leyó código, catálogo, documentación y pruebas existentes. No se ejecutaron tests, comandos Django, llamadas al proveedor, checkout, migraciones ni consultas a una DB. No se leyeron `.env` ni credenciales. No se modificó funcionalidad; el único archivo creado es este reporte. El worktree ya contenía cambios de PUBLIC 02/03A en marketing y documentación; se dejaron intactos.

## 2. Mapa end-to-end actual

| Etapa | Implementación encontrada | Estado / desconexión |
|---|---|---|
| `/pricing?service=appointments` | `apps/web/src/app/(marketing)/pricing/pricing-client.tsx`, `AppointmentsPricingSection` | Selecciona la pestaña visual desde el query param; usa catálogo local. |
| Plan y ciclo mensual/anual | `appointments-pricing-section.tsx`; `lib/pricing/plans.ts`; `lib/pricing/usage-tiers.ts` | Muestra Base, Pro, IA y tiers. No arma payload de compra. El toggle anual/mensual solo cambia precios mostrados. |
| Tier IA | `appointments-pricing-section.tsx` | Visualiza `ai_300`, `ai_1500`, `ai_3000` y `custom`; no envía `usage_tier`. |
| Add-ons/extras | `lib/pricing/addons.ts`, `lib/pricing/extras.ts`; backend S5 | La sección de Turnos no selecciona automatizaciones ni profesionales extra. |
| Quote | `POST /api/v1/billing/internal/appointments/quote/`; `AppointmentsQuoteView` | Solo administrador; no existe llamada desde la página pública. |
| Checkout | `POST /api/v1/billing/internal/appointments/checkout/`; `AppointmentsCheckoutView` | Solo administrador; requiere `business_id`; no es el endpoint de compra pública. |
| Mercado Pago | `create_appointments_checkout()` → `MercadoPagoService.create_preapproval_plan()` | Crea plan recurrente y devuelve `init_point`; no se probó proveedor. |
| Return | S5 construye `/subscribe/return?appointments_checkout_id=<uuid>` | La página actual no reconoce ese parámetro. |
| Webhook | `POST /api/v1/billing/mercadopago/webhook`; `webhook_processor.py` | Persiste y procesa preapproval/authorized payment; activación solo desde pago autorizado confirmado server-to-server. |
| `SubscriptionV2` | `apply_appointments_preapproval()` y `activate_subscription_from_invoice()` | Preapproval crea vínculo en `CHECKOUT_PENDING`; pago autorizado activa. Hay un caso de orden de eventos con recuperación incompleta (ver §9). |
| `SubscriptionAddon` | `apply_appointments_authorized_payment()` | Persiste profesional extra y automatizaciones pagas; IA obtiene automatizaciones del plan sin add-on cobrado. |
| Entitlements/cuotas | `runtime.py`, `billing/services/appointments.py`, `professional_quota.py` | Resolver V2 presente; la cuota de profesionales usa el extra. La cuota de asientos secundarios tiene mismatch para Pro/IA. |
| Onboarding | `app/app/onboarding/*`; `app/app/turnos/*` | El catálogo activo excluye Turnos. No hay puente desde el checkout S5 a un first-run de Turnos. |

`/subscribe` genérico solo conserva `plan_code`, `billing_period`, `vertical` y algunos campos propios de otras verticales. No conoce `usage_tier`, `extra_professionals` ni el contrato `billing_cycle` S5. No existe una ruta transaccional de Turnos desde pricing al endpoint interno.

## 3. Entrada de pricing y contrato frontend

### Estado actual

- `PricingVertical = BillingVertical | 'appointments'` se mantiene deliberadamente separado de `BillingVertical`.
- `isBillingVertical()` devuelve `false` para Turnos; todos los handlers genéricos de suscripción salen sin navegar.
- Para Turnos se renderiza `AppointmentsPricingSection`; sus CTAs dirigen a `/turnos` y Contactar ventas dirige a `/contacto`.
- `appointments.is_active === false` se refleja como “Contratación online próximamente”.
- Las pruebas de PUBLIC 03A verifican que la sección no navega a `/subscribe` ni hace fetch.
- `/app/onboarding/servicio` consume `GET /api/v1/billing/products/`, filtra productos activos, y el backend `get_products_catalog()` elimina los inactivos. Turnos no aparece como opción de onboarding.

### Recomendación de contrato

Mantener `PricingVertical` separado por ahora. No ampliar `BillingVertical` solo para mostrar un selector: el checkout existente espera bundles y `billing_period`, mientras que el checkout canónico S5 espera plan lógico, `billing_cycle`, tier y cantidades. Una integración posterior debe agregar un flujo Turnos explícito y decidir si adapta `/subscribe` o introduce una ruta de checkout dedicada. En ambos casos, el precio final debe recalcularse en backend.

**Estado:** `PARTIAL` — display público listo; selección y compra no conectadas.  
**Impacto:** compras Base/Pro/IA, addons y UX.

## 4. Checkout canónico S5 y payloads

### Modelo y servicios

- Modelo: `billing.models.AppointmentsCheckout`; estado `pending → linked → active` o `failed`.
- Quote y creación: `billing/services/appointments_checkout.py`, `quote_appointments()` y `create_appointments_checkout()`.
- View/endpoint: `AppointmentsQuoteView` y `AppointmentsCheckoutView` en `billing/views.py`.
- No se encontró un serializer DRF dedicado a estos endpoints. `_appointments_quote_request()` proyecta los campos conocidos desde `request.data`; el dominio valida valores/tipos y el catálogo.
- El endpoint de checkout requiere además `business_id`; la view lo resuelve directamente y ambas views son `IsAdminUser`.
- El checkout público está protegido actualmente por dos barreras separadas: producto inactivo (`is_plan_product_active`) y permisos de administrador. El endpoint S5 llama `internal_provisioning=True`, que omite el guard de producto inactivo solo para provisión interna.

### Payload de quote

`POST /api/v1/billing/internal/appointments/quote/`

```json
{
  "plan_code": "appointments | appointments_pro | appointments_ai",
  "billing_cycle": "monthly | yearly",
  "usage_tier": "ai_300 | ai_1500 | ai_3000 | custom",
  "automations": true,
  "automations_quantity": 1,
  "extra_professionals": 2
}
```

`usage_tier` es necesario solo para `appointments_ai`; para Base/Pro debe omitirse o ser null. `automations` y `automations_quantity` son formas alternativas coherentes (si se mandan ambas, deben coincidir); cantidad válida: 0 o 1. `extra_professionals` debe ser entero no negativo. El quote no admite precios enviados por cliente.

Respuesta canónica: `service_type`, `plan_code`, `usage_tier`, `billing_cycle`, estado de automatizaciones, cantidad de profesionales extra, `base_amount`, `addons_amount`, `extras_amount`, `discount_amount`, `total_amount`, `subtotal`, `currency`, `line_items`, `unit_prices`, `quantities`, versiones de catálogo/quote y `created_at`.

### Payload de checkout

`POST /api/v1/billing/internal/appointments/checkout/` acepta los campos de quote más:

```json
{ "business_id": 123 }
```

Respuesta: `checkout_id`, `external_reference`, `init_point`, `status`, `reused` y `quote`. La view usa el usuario administrador autenticado y el `Business` del `business_id` proporcionado; no es un contrato apto para exponer directamente a usuarios finales.

### Precios actuales del catálogo

| Plan / concepto | Mensual ARS | Anual ARS |
|---|---:|---:|
| `appointments` | 23.000 | 220.800 |
| `appointments_pro` | 28.000 | 268.800 |
| `appointments_ai` / `ai_300` | 150.000 | 1.440.000 |
| `appointments_ai` / `ai_1500` | 275.000 | 2.640.000 |
| `appointments_ai` / `ai_3000` | 385.000 | 3.696.000 |
| `appointments_automations` | 8.500 | 81.600 |
| `appointments_extra_professional`, por unidad | 3.000 | 28.800 |

## 5. Quote, tiers, custom y complementos

### Fuente de precios y duplicación

La UI usa `apps/web/src/lib/pricing/*`; el backend lee `generated/pricing.json` vía `canonical_pricing.py`, producido desde la capa canónica frontend. No se encontró una tabla de precios Turnos duplicada dentro del servicio de quote. El backend usa enteros ARS y recalcula todo desde catálogo. El quote S5 no aplica prorrateo ni descuentos; el prorrateo aparece en el servicio de lifecycle para upgrades.

La futura UI puede usar el catálogo local para mostrar precio orientativo, pero el quote y el total de checkout deben venir del servidor antes de iniciar el pago. No asumir que el importe local es autoridad de cobro.

### IA y `usage_tier`

- `appointments_ai` es el plan lógico único; el backend exige tier explícito válido.
- El tier se valida en `appointments_plans.validate_usage_tier()` y `canonical_pricing`; se persiste en `AppointmentsCheckout.usage_tier` y luego en `SubscriptionV2.usage_tier`.
- Los tiers self-service son `ai_300`, `ai_1500`, `ai_3000`; el backend rechaza tier no relacionado con el plan.
- Base/Pro rechazan un tier no nulo.
- `custom` existe en catálogo como `contact_sales`/manual y sin precios ni allowance numérica. El quote/checkout self-service responde `409 manual_contract_required`; la capa de autorización IA también requiere resolución comercial manual.
- No hay fallback de tier nulo a un tier predeterminado en el checkout actual ni conversión de precio custom nulo a cero. La capa de plan exige tier para IA; `usage_tier_price()` rechaza tiers no self-service. Los `0` del quote corresponden a descuentos actuales nulos, add-ons no seleccionados o automatizaciones incluidas, no al precio de `custom`.
- El pricing público presenta custom como Contactar ventas, pero no existe la ruta de contratación ni una selección de tier conectada a S5.

### Add-on `appointments_automations`

- Catálogo: disponible para Base/Pro a ARS 8.500 mensual / 81.600 anual; incluido en IA.
- Quote: en Base/Pro se incluye una línea si se selecciona; en IA marca la línea como incluida y su total es 0.
- Persistencia: checkout autorizado crea `SubscriptionAddon` solo cuando el estado es `enabled`. IA guarda `included` y no crea un add-on cobrable.
- Resolver: IA la obtiene del plan; Base/Pro la obtienen de add-on activo. Si hubiera un add-on redundante en IA, el resolver lo reporta y no cobra otra vez.
- Resultado: regla de no doble cobro está implementada en quote y resolución de entitlements.

**Estado:** `READY` a nivel de lógica canónica; `PARTIAL` para compra pública y gestión por UI.  
**Impacto:** addons, compra Base/Pro/IA, lifecycle.

### Extra `appointments_extra_professional`

- Cantidad entera no negativa; precio por unidad de ARS 3.000 mensual / 28.800 anual.
- Quote y checkout multiplican precio unitario por cantidad.
- El checkout guarda `extra_professional_quantity`; al pago crea/actualiza el `SubscriptionAddon` V2.
- El resolver suma cantidad a la cuota de profesionales incluidos; el control de alta aplica lock del Business.
- No agrega asientos de usuario secundarios.
- No se encontró selector frontend de cantidad en pricing ni UI de checkout.

**Estado:** `PARTIAL` — cálculo, persistencia y cuota existen; la selección pública no.  
**Impacto:** addons, compra Base/Pro/IA, lifecycle, UX.

## 6. Usuarios secundarios y profesionales con login

El catálogo declara:

| Plan | Profesionales incluidos | Usuarios secundarios incluidos |
|---|---:|---:|
| Base | 2 | 2 |
| Pro | 5 | 5 |
| IA | 5 | 5 |

El owner no consume asiento: `Membership.check_seat_limit` excluye `role='owner'`. Un `Membership` de tipo `professional` sí cuenta como usuario secundario; para crearlo exige plan Pro/IA y acceso profesional habilitado. Un profesional de agenda sin login no crea ese asiento. El extra de profesional aumenta capacidad de agenda, no usuarios con login.

**Mismatch confirmado:** `billing/plans.py::PLAN_SEAT_LIMITS` no contiene `appointments`, `appointments_pro` ni `appointments_ai`; `get_seat_limit()` devuelve el fallback de 2. Por lo tanto, aunque el catálogo muestre cinco usuarios secundarios para Pro/IA, el control de creación de Membership aplica dos asientos secundarios. El valor `secondary_users_included` del resolver Turnos no alimenta ese contador.

No existe precio de usuario secundario extra en el catálogo Turnos ni un add-on Turnos para esa capacidad. No se inventa uno.

**Estado:** `BLOCKER` para Pro/IA si se conserva la promesa comercial de 5 usuarios; `OPEN DECISION` sobre venta de asientos extra fuera de la capacidad incluida.  
**Impacto:** compra Pro/IA, profesionales con login, onboarding/UX.

## 7. Impuestos e IVA

- El quote contiene importes ARS, líneas y total, pero no campos `tax`, IVA, neto/bruto, tasa ni desglose fiscal.
- El request a Mercado Pago usa el total del quote como `transaction_amount`.
- La sección pública de Turnos no menciona si el precio incluye IVA.
- No se encontró en el flujo de checkout Turnos generación de factura fiscal ni vínculo de invoice fiscal; `BillingInvoiceEvent` es evidencia de pago, no una factura fiscal.

No se determina si los importes son finales o netos ni se propone política.

**Estado:** `OPEN DECISION — IVA/TAX PRESENTATION`.  
**Impacto:** compra Base/Pro/IA, billing y provider.

## 8. Mercado Pago S5/S6

### Código implementado (no probado en esta auditoría)

- S5 usa `MercadoPagoService.create_preapproval_plan()` (creación de plan recurrente de MP, no `POST /preapproval` directo).
- El payload incluye `reason`, `auto_recurring` (`frequency`, `frequency_type`, `transaction_amount`, `currency_id`), `back_url`, `status=active`, métodos de pago permitidos, `external_reference` y metadata.
- Checkout anual usa frecuencia 12 meses; mensual, 1 mes. El importe es el total canónico mensual/anual del quote.
- El flujo de plan S5 no pasa `payer_email`; el pagador completa el flujo alojado por el proveedor. El método separado `create_preapproval(email, ...)` no es el que invoca `create_appointments_checkout()`.
- S5 construye el back URL con `appointments_checkout_id`; la notificación de webhook se espera en `/api/v1/billing/mercadopago/webhook`.
- El payload de plan recurrente S5 no añade explícitamente `notification_url`; en otra ruta de preferencias one-time sí se construye a partir de `BASE_PUBLIC_URL`. El funcionamiento de suscripción depende de la configuración de notificaciones del proveedor y debe verificarse en homologación.
- El handler de webhook verifica firma según configuración, persiste delivery, deduplica y soporta reintentos para fallas transitorias. El handler consulta la representación autoritativa del provider antes de aplicar estados/pagos.
- El preapproval, por sí solo, deja la suscripción en `CHECKOUT_PENDING`; no activa negocio. La activación exige `subscription_authorized_payment` autorizado y validación server-to-server.

### Homologación real pendiente

Según el estado previo entregado para este slice, S6B no obtuvo evidencia real de provider con sandbox/test payer. Esta auditoría no volvió a probar Mercado Pago ni usó credenciales. El contrato de importe, frecuencia anual, retorno, notificaciones, payer/consentimiento, estados y renovaciones necesita validación controlada antes de activar compras públicas.

**Estado:** código `PARTIAL`; homologación `BLOCKER` de provider.  
**Impacto:** toda compra transaccional y lifecycle.

## 9. `SubscriptionV2`, webhook, orden de eventos e idempotencia

### Camino esperado

1. Checkout crea `AppointmentsCheckout` con quote y metadata inmutables de plan/tier/ciclo/add-ons.
2. Webhook de preapproval correlaciona por `provider_preapproval_plan_id` y `external_reference`, valida importe/moneda y crea `SubscriptionV2` con `service_type=appointments`, plan, tier, ciclo, `provider_sub_id`, `provider_preapproval_plan_id`, snapshot y estado `CHECKOUT_PENDING`. El checkout pasa a `linked`.
3. Webhook de pago autorizado hace fetch autoritativo, valida monto/moneda contra snapshot, crea/enlaza `BillingInvoiceEvent` y llama al activador.
4. El activador marca `SubscriptionV2` `ACTIVE`/`is_active=True`, fija `current_period_start` desde `paid_at` y `current_period_end` según ciclo; activa el Business de forma atómica.
5. El handler S5 aplica add-ons y marca `AppointmentsCheckout` `active`.

El snapshot conserva plan, tier, billing cycle, precio y provider IDs. La correlación evita confiar en un plan/precio enviado por el browser.

### Orden de eventos: pago antes de preapproval

El webhook autorizado crea el `BillingInvoiceEvent`, busca `SubscriptionV2` por `provider_sub_id` y, si aún no existe, registra el evento como huérfano y retorna sin error de reintento. El webhook posterior de preapproval puede crear la suscripción, pero no se encontró un enlace automático posterior que aplique ese invoice event al `AppointmentsCheckout`.

La reconciliación existente (`reconcile_invoice_event` / `reconcile_subscription`) puede activar una `SubscriptionV2` ya creada, pero el camino genérico solo llama al activador: no invoca la validación ni `apply_appointments_authorized_payment()`. Por tanto, en este orden puede faltar la transición de checkout a `active` y la persistencia de `SubscriptionAddon`. El comando manual tampoco sirve como prueba de que el ciclo S5 de Turnos quede completo.

**Estado:** `BLOCKER` de recuperación de webhook fuera de orden.  
**Impacto:** activación, add-ons, soporte y billing.

### Idempotencia y concurrencia

- Checkout serializa por Business y checkout con `select_for_update`; reutiliza un checkout abierto si coincide el request y existe restricción única parcial para un `pending`/`linked` por Business.
- `external_reference` de checkout es UUID único; `provider_preapproval_plan_id`, preapproval y payment IDs tienen unicidad en modelo.
- `SubscriptionV2.provider_sub_id` es único; `BillingInvoiceEvent` identifica de forma única el authorized payment; el webhook persiste/deduplica deliveries.
- La aplicación de add-ons usa `update_or_create`; el activador y la aplicación S5 vuelven a tomar locks y evitan doble activación.
- Hay tests existentes de concurrencia de checkout/webhook; no se ejecutaron.
- No se encontró un idempotency key enviado explícitamente a Mercado Pago al crear el plan. Si MP crea el plan y falla la persistencia local/commit, no está demostrado que un retry no deje un plan remoto huérfano o duplicado. `external_reference` ayuda a correlacionar, pero no es evidencia de idempotencia del provider.

**Estado:** `PARTIAL` — fuerte idempotencia local; creación remota y recuperación de huérfanos requieren cierre.  
**Impacto:** checkout, provider, lifecycle.

## 10. Return y checkouts pendientes

### Return

- S5 genera `/subscribe/return?appointments_checkout_id=<uuid>`.
- `apps/web/src/app/(marketing)/subscribe/return/page.tsx` solo lee `checkout_session_id` e `intent_id`.
- No hace polling de `AppointmentsCheckout`, no consume estado `pending/linked/active/failed` y no tiene vistas de éxito, pendiente, rechazo o cancelación para este modelo.
- Si llega el retorno S5 actual, cae al poller legacy sin `intent_id` y muestra que no encontró información de pago.
- El retorno no debe activar por sí mismo; la regla de activación por webhook autorizado es correcta, pero la UI necesita observar el modelo correcto.

**Estado:** `BLOCKER` de UX/recuperación del pago.

### Pendientes y reintentos

- `AppointmentsCheckout` no tiene `expires_at`; no se halló tarea/cleanup de checkouts pendientes Turnos.
- Un checkout de estado `pending` o `linked` puede seguir ocupando el único slot abierto del Business. Un request idéntico reutiliza el existente, incluso si es antiguo; otro request puede recibir “Another Turnos checkout is already in progress”.
- Cerrar la ventana de MP no es un estado que el frontend pueda reconciliar hoy.
- La aplicación de webhook de preapproval cancelado sí puede marcar el checkout fallido, pero eso no cubre abandono sin notificación.

**Estado:** `BLOCKER` para reintento confiable; cleanup no se implementa en esta auditoría.  
**Impacto:** UX, compra, soporte/operación.

## 11. Lifecycle y suscripciones existentes

S6 tiene endpoints backend owner-only de quote, cambio y resolución de cambios, pero no se encontró consumo de esos endpoints en el frontend. El checkout inicial no incorpora ninguna UI de gestión.

- Upgrade/diferencia de precio: se prorratea la diferencia positiva por el período restante; se cobra como preferencia one-time y se aplica tras pago.
- Downgrade: se agenda para `current_period_end`; si los profesionales activos superan el límite futuro, el cambio queda bloqueado hasta reducirlos/resolver exceso.
- Ciclo mensual/anual: el cambio se aplica en renovación y prepara el próximo cobro de MP.
- Tier IA: se persiste el nuevo tier y `usage_tier_effective_from`; la política S8 conserva evidencia histórica.
- Automatizaciones/profesionales extra: el snapshot de cambio permite actualizar cantidades y activar/desactivar registros V2.
- Grace: S6 declara 3 días; acceso `PAST_DUE` solo mientras `grace_until` no venció.
- Cancelación genérica: el servicio permite programar cancelación en `current_period_end`, y el resolver de lifecycle quita acceso al alcanzar ese límite. La ruta S6 de Turnos no se integra en la UI de pricing; no se encontró reembolso prorrateado en el flujo.
- Reactivación y actualización remota de preapproval dependen del provider y deben homologarse. Los estados de error se registran en backend; el usuario no tiene una pantalla Turnos de lifecycle.

**Estado:** backend `PARTIAL/READY` para cambios de ciclo de vida bajo V2; experiencia cliente/provider `PARTIAL`.  
**Impacto:** lifecycle, billing, UX, provider.

## 12. Entitlements y capacidades efectivas

El resolver S3 lee la `SubscriptionV2`, valida plan/tier y add-ons activos:

| Plan | Resultado de resolución actual |
|---|---|
| Base | Entitlement `appointments.customers`; límite base de profesionales desde catálogo. |
| Pro | `appointments.customers`; capacidad de 5 profesionales y login profesional habilitado. |
| IA | `appointments.customers`, `appointments.leads` y `appointments.automations`; capacidad de 5 profesionales; `ai_enabled` solo con tier válido. |
| Base/Pro + automatizaciones | `appointments.automations` solo con add-on activo. |
| Todos + profesional extra | `effective_professional_limit = incluidos + quantity`. |

IA incluye automatizaciones desde el plan, no desde un add-on duplicado. El código de entitlements de IA no agrega un entitlement distinto denominado “Pro”; sus capacidades Pro visibles en este dominio provienen de cuota/login de profesional. El frontend debe comunicar recursos reales y no inferir capacidades adicionales desde el label.

La resolución no activa por sí sola el servicio: requiere suscripción efectiva y lifecycle con acceso. `checkout_pending`, `suspended` y `canceled` no deben otorgar uso normal.

**Estado:** `PARTIAL` por mismatch de seats y dependencia de activación.  
**Impacto:** entitlements, compra Pro/IA, onboarding.

## 13. Onboarding y first-run

### Capacidad encontrada

- La activación del webhook puede poner Business en estado activo.
- Existen páginas para inicio Turnos, agenda, profesionales, servicios/categorías, horarios y configuración.
- La página de profesionales indica que son opcionales; sin profesionales, la reserva puede apuntar al negocio.
- La página de horarios permite configurar horario general, por profesional y excepciones.
- La página Turnos muestra el enlace público de reservas si está disponible.
- Configuración incluye la conexión MP para señas de reservas, automatizaciones y datos de contacto WhatsApp.

### Ausencias / clasificación

| Paso de primer uso | Clasificación | Evidencia actual |
|---|---|---|
| Crear primer profesional | Opcional | UI disponible, el negocio puede operar sin perfiles individuales. |
| Configurar horarios | Operación necesaria para reservas con disponibilidad; no hay wizard | Pantalla de horarios existente. |
| Crear/activar servicios | Manual | Pantallas de catálogo/servicios existentes; no hay recorrido post-compra. |
| Generar/compartir link de reservas | Disponible, no guiado | Card muestra/copia link cuando backend lo habilita. |
| Branding del negocio | Manual / transversal | No se ofrece como paso de compra Turnos. |
| WhatsApp de contacto público | Opcional | Campo de contacto; no equivale al canal/agente de WhatsApp IA. |
| Conexión MP para señas | Opcional e independiente del billing de suscripción | OAuth por Business para cobrar señas; no es MP de la suscripción MiRubro. |
| Configuración de IA/agente WhatsApp | Inexistente como onboarding autoservicio | No hay wizard de conexión/sync/health posterior a compra. |

No se encontró un flujo guiado `contrató → configura agenda → publica link → recibe primera reserva`. Esto es `POST-LAUNCH DEBT` para Base/Pro, pero el acceso/configuración del canal IA es un blocker funcional para vender IA operativa.

## 14. IA, metering, overage y hard cap

### Onboarding/activación de IA

El tier se conserva en SubscriptionV2 y el resolver canónico puede exponerlo. La autorización previa al LLM depende además de:

- `AI_USAGE_METERING_ENABLED`; el endpoint deniega con `metering_disabled` si está apagado.
- Integración interna del agente autenticada por HMAC, con contexto de conversación no ambiguo, canal activo y Lead/Business coincidentes.
- Sync/contexto del agente disponible; un contexto ausente o ambiguo se bloquea, no se imputa por supuesto.
- `AGENT_INTEGRATION_ENABLED`, health de DB/nonce/throttle y configuración operativa válida.

Los defaults documentados y el estado de S8 entregado mantienen los flags apagados; este audit no lee configuración real ni los modifica. Por tanto, el código del checkout no equivale a IA utilizable inmediatamente tras comprar.

**Estado:** `BLOCKER` de operación para IA hasta la habilitación y validación controladas.  
**Impacto:** compra IA, onboarding, integraciones y operación.

### Períodos y allowance

- Una suscripción mensual usa su período corriente como ventana de uso.
- Una suscripción anual conserva el período de cobro anual, pero crea subperíodos de uso mensuales anclados al inicio/renovación; el código conserva el día del ancla cuando el mes es más corto.
- Se cuenta una sesión de conversación de hasta 24 horas, no cada mensaje individual.
- Los tres tiers tienen allowance mensual del catálogo: 300, 1.500 o 3.000 sesiones.
- `custom` requiere resolución comercial manual y no es admitido por el flujo de autorización automática.
- El endpoint de autorización revalida lifecycle/tier actual y usa locks; el hard cap impide iniciar una sesión nueva. Una ventana existente puede reutilizarse según las reglas S8.

### Overage: ledger no equivale a cobro

El código separa autorización/metering, ledger de cargos, settlement, `BillingIntent` y ejecución del provider. El ledger puede registrar sesiones overage a precio/tier congelado y S8D/S8G puede preparar settlement/intents. Pero `AI_USAGE_BILLING_PROVIDER=disabled` utiliza `DisabledAIUsageBillingProvider`; incluso una configuración diferente no registra un provider real y produce warning/adapter disabled.

**No se observó un cargo real de overage habilitable por configuración en el estado actual.** El sistema sí permite sesiones por encima de la allowance hasta el hard cap. Por ello, si el precio por sesión adicional se comunica como cobro efectivo, existe riesgo de uso overage no cobrable. No se decide aquí si se debe vender IA solo con allowance, absorber un máximo de overage, bloquear al llegar a incluido o implementar cobro automático.

**Estado:** metering `PARTIAL/BLOCKER` mientras esté apagado; settlement/provider `PARTIAL` y decisión de producto abierta.  
**Impacto:** IA, billing y riesgo económico.

### Hard cap observable

`resolve_ai_usage_policy()` calcula `max_overage_sessions = floor(default_extra_spend_limit / extra_conversation_price)` y `max_total_sessions = included + max_overage_sessions`. La próxima sesión nueva se bloquea al llegar al límite. La API devuelve `hard_cap_reached`; el agente debe usar la respuesta determinística sin invocar LLM. No se crea un cobro real al alcanzar el cap. El período siguiente se vuelve elegible por sus límites temporales; no se cambia ninguna regla.

## 15. Compra anual y renovaciones

- Los precios anuales del catálogo son mensuales × 12 × 0,8 (20% de descuento).
- S5 solicita a MP frecuencia `12` de tipo `months` para anual y envía el importe anual total.
- El activador fija el período V2 anual con `appointments_period_end(..., 'yearly')`.
- La ventana mensual de uso IA es independiente y se ancla dentro del período anual.
- Los add-ons seleccionados y profesionales extra se agregan al mismo total anual del quote.
- El provider debe confirmar que admite el contrato real de frecuencia/importe y que las fechas de renovación coinciden con el modelo; esto no se probó.
- Los cambios de ciclo facturan el importe del ciclo objetivo al vencimiento y actualizan la recurrencia prevista en MP.

**Estado:** cálculo y payload anual implementados; comportamiento real `BLOCKER` de homologación.  
**Impacto:** billing, AI metering, addons, provider.

## 16. Seguridad, tenant y validación de entradas

### Protecciones presentes en la ruta interna

- Quote/checkout S5 son admin-only, no endpoints de compra pública.
- El checkout verifica el estado de disponibilidad salvo en provisión interna autorizada.
- El backend recibe códigos/tier/cantidades, valida contra catálogo canónico y recalcula los importes.
- Valida tipo entero estricto para cantidades y cantidad 0/1 de automatizaciones; rechaza tiers no permitidos, tier en Base/Pro y custom self-service.
- Guarda metadata de `business_id`, plan/tier/ciclo/add-ons y verifica consistencia del snapshot con el checkout.
- Preapproval exige correlación de `external_reference`; el pago exige monto/moneda exactos contra snapshot persistido.
- Lifecycle S6 resuelve la membresía, exige rol owner y opera sobre su propio Business.

### Límite actual y requisito para exposición pública

El endpoint S5 acepta `business_id` en el body y usa el permiso global `IsAdminUser`; eso es apropiado solo como provisión interna, no para el checkout del cliente. Antes de abrirlo debe existir una ruta autenticada para owner, derivar Business del membership del request, verificar ownership/permisos, y mantener plan/precio/tier/add-on quantity validados en servidor. No confiar en query params, precio ni `business_id` del browser.

No se identificó un bypass público existente desde `/pricing`: la UI actual no llama al endpoint y el endpoint requiere administrador. El riesgo de tenant aparece si se expone el contrato interno sin adaptar autorización/derivación de Business.

**Estado:** protección de la ruta actual `READY` como endpoint interno; diseño de compra pública `BLOCKER` pendiente.  
**Impacto:** seguridad/tenant, compra, billing.

## 17. Estados de error y respuesta UX

| Caso | Backend / estado actual | UX Turnos actual |
|---|---|---|
| Precio/plan inválido | Error de validación del catálogo | Sin flujo de compra que lo presente. |
| Tier inválido o ausente en IA | Rechazo explícito; no default | No hay envío desde la UI actual. |
| Custom | `409 manual_contract_required` | CTA actual a contacto; checkout no debe ser self-service. |
| Producto inactivo | Catálogo de productos lo excluye; compra pública genérica bloqueada | Pricing informa “próximamente”. |
| Checkout pendiente repetido | Reusa request coincidente o conflicto si otro config está abierto | Sin pantalla/polling Turnos. |
| Fallo MP al crear plan | Excepción/HTTP de conflicto en endpoint; estado local puede quedar sin respuesta usable | No hay estado Turnos de provider failure. |
| Usuario cierra MP | No hay expiración local | Reintento puede quedar bloqueado por checkout abierto. |
| Return después de MP | El parámetro S5 no lo lee la página return | Poller legacy muestra falta de información. |
| Webhook duplicado | Delivery deduplicada; respuesta 200 | No se muestra estado de reconciliación. |
| Webhook atrasado o fuera de orden | Puede dejar invoice huérfano; recuperación S5 incompleta | No hay polling S5 ni mensaje de pendiente. |
| Pago rechazado/cancelado | Webhook puede marcar preapproval/checkout fallido si llega el evento correspondiente | No hay pantalla Turnos de failure/cancel. |
| Hard cap IA | Respuesta de autorización `hard_cap_reached`, se bloquea nueva sesión | No hay onboarding/UX cliente Turnos que explique recuperación. |

## 18. Qué está listo y qué falta para activar

| Superficie/componente | Estado actual |
|---|---|
| Landing `/turnos`, nav, home, footer, sitemap | `READY` como presencia informativa. |
| Pricing y catálogo visual | `READY` informativo; ciclo y tiers mostrados; no contratable. |
| Producto canónico / tiers / precios | `READY` como catálogo; `appointments.is_active=false`. |
| `BillingVertical` y builders genéricos | Correctamente sin Turnos; no modificar hasta diseñar contrato. |
| Quote S5 | `PARTIAL`: código canónico y tests existentes; admin-only, sin integración frontend. |
| Checkout S5 | `PARTIAL`: crea plan y snapshot; admin-only, con gaps de return/expiración/orden de eventos. |
| Webhook / SubscriptionV2 | `PARTIAL`: regla de activación segura e idempotencia local; recovery del orden no cubre artifacts S5. |
| Lifecycle S6 | `PARTIAL`: lógica backend presente; UI y homologación MP no confirmadas. |
| Add-ons y cuota de profesional | `PARTIAL`: reglas server-side; selector frontend ausente. |
| Cuotas de usuarios secundarios | `BLOCKER`: mismatch Pro/IA. |
| Entitlements | `PARTIAL`: resolver V2 presente, condicionado a cuota/activación. |
| Onboarding post-compra | `POST-LAUNCH DEBT` para Base/Pro; no hay first-run guiado. |
| IA onboarding y metering | `BLOCKER` operacional mientras flags/contexto no estén habilitados y verificados. |
| Overage | `OPEN DECISION` + `PARTIAL`: ledger/settlement existen; provider real deshabilitado. |
| IVA/tax | `OPEN DECISION`. |
| Observabilidad | `PARTIAL`: eventos y logs webhook/metering presentes; falta UX operativa de estado S5 y validación de alertas/runbook. |

## 19. Checklist de go-live

| Área | Estado | ¿Bloquea activación? | Acción pendiente |
|---|---|---:|---|
| Pricing | `READY` informativo | Sí, para compra pública | Diseñar la transición informativa → transaccional y preservar el display actual. |
| `BillingVertical` | `READY` como tipo separado | No por sí solo | Mantener separación o implementar adaptación explícita del contrato; no agregarlo solo por selector. |
| Quote | `PARTIAL` | Sí | Crear endpoint consumible por owner con auth/tenant y response de quote server-side. |
| Checkout | `PARTIAL` | Sí | Exponer flujo cliente seguro; incluir tier, ciclo, automations y cantidad extra. |
| Mercado Pago | `BLOCKER` | Sí | Homologar plan, aprobación, anual, payer, retorno, notificaciones, renovación y cancelación en sandbox/provider autorizado. |
| Webhook | `PARTIAL` | Sí | Cerrar orden de eventos y aplicar reconciliación específica de `AppointmentsCheckout` y addons. |
| `SubscriptionV2` | `PARTIAL` | Sí | Comprobar birth path con usuario/Business propietario y artifacts S5 en flujo público. |
| `usage_tier` | `READY` en validación backend | Sí para IA | Conectarlo en checkout; mantener obligatorio para IA y sacar `custom` de self-service. |
| Add-ons | `PARTIAL` | Sí si se comercializan | UI/cotización para automatizaciones y profesionales; verificar IA sin doble cobro. |
| Profesionales extra | `PARTIAL` | Sí si se comercializan | Integrar quantity y mostrar que no compra asientos secundarios. |
| Usuarios secundarios | `BLOCKER` Pro/IA | Sí si se mantienen 5 prometidos | Alinear `PLAN_SEAT_LIMITS` o el contrato de catálogo; resolver seats extra como decisión independiente. |
| Annual | `PARTIAL` | Sí | Validar con MP la recurrencia de 12 meses y los subperíodos IA antes de cobro real. |
| Lifecycle | `PARTIAL` | Sí para clientes existentes | Conectar UI y homologar upgrade, downgrade, ciclo, cancelación y renewal. |
| Entitlements | `PARTIAL` | Sí | Corregir cuota de asientos y validar efectivo V2 bajo ACTIVE/PAST_DUE/SUSPENDED. |
| Onboarding | `POST-LAUNCH DEBT` Base/Pro; `BLOCKER` para valor IA | Sí para IA; recomendable Base/Pro | Definir first-run guiado o pasos operativos e integrar el return. |
| AI onboarding | `BLOCKER` | Sí para IA | Health de agente, integración, sync/contexto, canal y flags aprobados antes de venta IA. |
| Metering | `BLOCKER` si flag apagado | Sí para IA | Habilitación gradual/controlada y verificación operativa; no cambiar en esta auditoría. |
| Overage | `OPEN DECISION` / `PARTIAL` | Sí si se promete cargo extra | Definir política o habilitar provider real y reconciliación; hoy el adapter no cobra. |
| Hard cap | `READY` en backend | No para Base/Pro; sí es política de IA | Definir copy, monitorización y comportamiento de atención al alcanzar el límite. |
| IVA/tax | `OPEN DECISION` | Sí antes de comunicar/importar cobro fiscal | Resolver `IVA/TAX PRESENTATION`; no inferir neto/bruto actual. |
| Observabilidad | `PARTIAL` | Sí para operación confiable | Alertas/runbook para webhook huérfano, plan remoto sin vínculo, checkout bloqueado, metering y estado provider. |

## 20. Clasificación consolidada de hallazgos

| # | Hallazgo | Estado | Impacto | Evidencia principal |
|---:|---|---|---|---|
| 1 | Pricing Turnos es informativo; no envía quote ni checkout | `BLOCKER` | compra Base/Pro/IA, UX | `pricing-client.tsx`, `appointments-pricing-section.tsx`, pruebas PUBLIC 03A |
| 2 | `BillingVertical`/`/subscribe` no llevan el contrato S5 de tier/cantidades | `BLOCKER` | compra, UX | `features/billing/types.ts`, `subscribe/page.tsx`, `appointments_checkout.py` |
| 3 | Endpoints de quote/checkout son admin-only e internos | `BLOCKER` | compra, seguridad/tenant | `billing/views.py`, `billing/urls.py` |
| 4 | Return S5 usa parámetro no reconocido | `BLOCKER` | UX, recuperación de pago | `appointments_checkout.py`, `subscribe/return/page.tsx` |
| 5 | Pago antes de preapproval no finaliza todos los artifacts S5 al reconciliar | `BLOCKER` | webhook, subscription, addons, billing | `webhook_processor.py`, `reconciliation.py`, `appointments_checkout.py` |
| 6 | Checkouts `pending/linked` no expiran ni tienen cleanup | `BLOCKER` | checkout, UX/soporte | `AppointmentsCheckout` model, `create_appointments_checkout()` |
| 7 | Pro/IA declaran 5 usuarios secundarios, control estático aplica 2 | `BLOCKER` | compra Pro/IA, profesionales | `generated/pricing.json`, `billing/plans.py`, `accounts/models.py` |
| 8 | Homologación real MP sigue pendiente según estado de S6B | `BLOCKER` | provider, billing, lifecycle | estado previo; `mp_service.py`, tests S5/S6 existentes |
| 9 | IA depende de flags y contexto externo; estado S8 los mantiene apagados | `BLOCKER` IA | compra IA, operación, UX | `settings.py`, `ai_usage_views.py`, contrato canónico S8H |
| 10 | Provider de overage es siempre disabled; metering no equivale a settlement/cobro | `PARTIAL` + `OPEN DECISION` | IA, billing | `ai_usage_billing_provider.py`, `ai_usage_billing_pipeline.py` |
| 11 | Política de IVA/impuestos no está en quote ni UI | `OPEN DECISION` | billing, provider, UX | quote S5, pricing Turnos |
| 12 | No hay first-run guiado ni página return post-compra Turnos | `POST-LAUNCH DEBT` Base/Pro; blocker IA | UX, onboarding | `app/app/turnos/*`, `subscribe/return/page.tsx` |
| 13 | Lifecycle S6 backend sin UI frontend encontrada | `PARTIAL` | lifecycle, UX | `appointments_lifecycle_views.py`, búsqueda de llamadas frontend |
| 14 | Crear plan MP no presenta idempotency key explícito | `PARTIAL` | provider, riesgo de duplicación | `create_appointments_checkout()`, `create_preapproval_plan()` |

## 21. Blockers reales vs. decisiones abiertas

### Blockers reales de ingeniería/operación

- No hay ruta autoservicio de checkout para el usuario final.
- El endpoint interno no puede exponerse sin autenticación por owner y resolución tenant segura.
- Return incompatible con `appointments_checkout_id`.
- Webhook fuera de orden puede dejar checkout/add-ons incompletos; reconciliación genérica no completa S5.
- Pending checkout sin expiración puede impedir retry.
- Capacidad de usuarios secundarios Pro/IA no coincide con lo ofrecido.
- Homologación de Mercado Pago pendiente.
- IA no es operativa con metering/agent apagados; el flujo de compra no configura ni valida el canal.

### Decisiones abiertas, no resueltas aquí

- `OPEN COMMERCIAL DECISION — IVA/TAX PRESENTATION`.
- Política de overage: habilitar cobro, vender IA limitada al allowance, absorber una cantidad limitada o bloquear al llegar al included; actualmente el código deja consumir hasta el hard cap sin provider de cargo real.
- Si habrá usuarios secundarios extra para Turnos y su precio. No existe precio canónico actual; el extra de profesional no es asiento.

### Deuda de UX que no necesariamente bloquea compra Base/Pro

- Wizard de primer uso, configuración guiada de horarios/servicios y sugerencias de publicación de link.
- UI de lifecycle, estados detallados de pago/renovación y ayuda al recuperar checkout pendiente.

## 22. Secuencia mínima sugerida de slices posteriores (sin implementar)

1. **03B1 — contrato público de quote/checkout:** endpoints owner-scoped, selección de plan/ciclo/tier/add-ons, quote server-side y client dedicado. No habilitar producto todavía.
2. **03B2 — return, webhook recovery y pending checkout:** procesar `appointments_checkout_id`; observar estados; recuperación idempotente que aplique SubscriptionV2, checkout y add-ons sin importar orden; definir expiración/retry y detectar planes MP huérfanos.
3. **03B3 — cuotas comerciales y onboarding:** alinear seats con catálogo; definir pasos posteriores a compra, uso de profesionales/horarios/servicios/link y preparación IA manual/automática.
4. **03B4 — provider y decisiones comerciales:** homologar MP en ambiente/provider de pruebas autorizado (incluyendo anual y webhooks); resolver IVA y modelo de overage antes de mensajes comerciales definitivos.
5. **03B5 — UI de lifecycle y operación:** conectar upgrade/downgrade/cancelación S6, mensajes de pending/failure/grace/cap, métricas/alertas y runbooks.
6. **03B6 — activation gate:** checklist y revisión final de permisos, entitlements, onboarding, seguridad, provider y operación; solo entonces cambiar flags/allow-list de activación mediante un cambio separado y aprobado.

La activación de `appointments.is_active` no resuelve por sí sola las barreras de permisos, UI, webhook/return, onboarding, cuotas ni homologación. No se deben cambiar flags como parte de esta auditoría.

## 23. Evidencia y límites de validación

Fuentes principales revisadas:

- Frontend: `apps/web/src/app/(marketing)/pricing/pricing-client.tsx`, `appointments-pricing-section.tsx`, `features/billing/types.ts`, `features/billing/api.ts`, `app/(marketing)/subscribe/page.tsx`, `app/(marketing)/subscribe/return/page.tsx`, `app/app/onboarding/servicio/page.tsx`, `app/app/turnos/*`.
- Catálogo: `apps/web/src/lib/pricing/{plans,usage-tiers,addons,extras}.ts`, `generated/pricing.json`.
- Billing: `services/api/src/apps/billing/{appointments_plans.py,canonical_pricing.py,models.py,views.py,urls.py,mp_service.py,webhook_processor.py,reconciliation.py,subscription_activator.py,appointments_lifecycle_views.py}`.
- Servicios: `services/api/src/apps/billing/services/{appointments_checkout.py,appointments.py,appointments_lifecycle.py}`.
- Cuotas/entitlements: `services/api/src/apps/appointments/services/{professional_quota.py,ai_usage.py,ai_usage_authorization.py,ai_usage_billing_pipeline.py,ai_usage_billing_provider.py}`, `services/api/src/apps/business/entitlements.py`, `services/api/src/apps/accounts/models.py`.
- Estado de producto previo: `docs/turnos/TURNOS_PUBLIC_02.md`, `docs/turnos/TURNOS_PUBLIC_03A.md`, `docs/turnos/MIRUBRO_TURNOS_CANONICAL.md`.
- Pruebas existentes inspeccionadas, no ejecutadas: `test_appointments_checkout_s5.py`, `test_appointments_checkout_concurrency.py`, `test_appointments_lifecycle_s6.py`, `test_appointments_canonical_pricing.py`, tests S8A–S8I.

Esta auditoría no constituye homologación de provider, prueba de carga/concurrencia ni revisión del entorno desplegado. No se observó ninguna configuración real de credenciales ni se realizaron requests externos.

TURNOS CHECKOUT — BLOCKED BY checkout público no conectado; retorno y recovery S5 incompletos; mismatch de seats Pro/IA; homologación Mercado Pago pendiente; metering/operación IA apagados.
