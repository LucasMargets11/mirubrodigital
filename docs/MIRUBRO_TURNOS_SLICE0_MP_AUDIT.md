# MiRubro Turnos — Slice 0: Auditoría técnica de Mercado Pago, OAuth y arquitectura de pagos

**Branch:** `develop` · **HEAD auditado:** `d87e17104c1ee11890d446c024c6d03141bca153` · **Fecha:** 2026-09-15

**Cambios preexistentes en el working tree (no generados por este slice, no modificados ni revertidos):**
- `M services/api/docker-entrypoint.sh` — el diff de contenido es **vacío** (`git diff` no devuelve líneas de cambio, solo una advertencia de normalización LF→CRLF de Git). Es un cambio de metadata de line-endings, no de contenido.
- `?? docs/IA/TRANSFERENCIA_MIRUBRO_A_CLAUDE_2026-09-03.md` — archivo sin trackear, preexistente.

Este documento es el único artefacto nuevo generado por este slice. No se crearon migraciones, no se modificó código, no se corrigieron tests.

---

## 1. Resumen ejecutivo

El repo **ya tiene** una prueba de concepto funcional de "cliente final → Mercado Pago → cuenta MP del negocio": el flujo de propinas de Carta Online (`apps.menu`), vía OAuth Connect (`MercadoPagoConnection`) y `TipTransaction`. La creación del pago usa correctamente el token del negocio. **Pero la confirmación asíncrona (webhook) está probablemente rota para negocios con OAuth real**, porque el servicio que re-consulta el pago contra la API de MP (`MercadoPagoService`) está *hardcodeado* al token global de la plataforma, no al del negocio — hallazgo crítico. El billing de suscripciones (dominio separado, correcto) tiene una máquina de webhooks (`WebhookDelivery`, firma HMAC, dedup) bien diseñada y con buena cobertura de tests, pero su estado `DEAD_LETTER` y el reintento automático de entregas `FAILED` están **definidos pero nunca implementados**. Los tokens OAuth se guardan **en texto plano**, sin cifrado. No existe ningún código de `appointments`/Turnos todavía. Recomendación: **extraer** la conexión OAuth de `menu` a una app genérica (`merchant_payments`), corrigiendo antes los defectos de seguridad y del bug del token en el webhook, y reutilizar la maquinaria de webhooks de `billing` (no la de `menu`, más débil) para Turnos. No hay bloqueantes de arquitectura, pero sí bloqueantes de seguridad/corrección que deben resolverse antes de manejar dinero real de clientes finales.

---

## 2. Estado actual Mercado Pago — mapa de componentes

| Componente | Ubicación | Dominio | Rol |
|---|---|---|---|
| `MercadoPagoConnection` (modelo) | `apps/menu/models.py:247-271` | Menu/Tips | Conexión OAuth por-negocio (token, scope, status) |
| `TipTransaction` (modelo) | `apps/menu/models.py:278-315` | Menu/Tips | Registro de una propina/pago de cliente final |
| OAuth Start/Callback/Status/Disconnect | `apps/menu/views.py:787-929` | Menu/Tips | Conectar/desconectar la cuenta MP del negocio |
| `PublicTipCreatePreferenceView` / `PublicTipVerifyView` | `apps/menu/views.py:936-1199` | Menu/Tips | Crear preferencia de pago + verificación por polling |
| `MercadoPagoService` | `apps/billing/mp_service.py` (562 líneas) | Billing | Wrapper SDK: preapproval/plan + preference/payment — **token global hardcodeado** |
| `MercadoPagoWebhookView` | `apps/billing/views.py:702-948` | Billing (compartido con Tips) | Único receptor de webhooks MP de todo el repo; despacha por `topic` o por prefijo `external_reference` |
| `webhook_processor.py` | `apps/billing/webhook_processor.py` | Billing | Verificación HMAC, dedup, `WebhookDelivery`, dispatch de eventos de suscripción |
| `WebhookDelivery`, `PaymentEvent`, `BillingEvent`, `BillingInvoiceEvent` | `apps/billing/models.py` | Billing | Ledger de entregas de webhook + eventos de pago (suscripciones) |
| `SubscriptionV2`, `PaymentAttempt`, `MpCheckoutSession` | `apps/billing/models.py` | Billing | Modelos de suscripción — **no reutilizables para Turnos** |
| `reconciliation.py`, `reconcile_billing` (mgmt command) | `apps/billing/` | Billing | Reconciliación manual contra la API de MP |
| `tasks.py` (Celery) | `apps/billing/tasks.py` | Billing | 4 tareas periódicas — ninguna reintenta webhooks `FAILED` |
| `Account.Type.MERCADOPAGO`, `Invoice.payment_method` | `apps/treasury/models.py:13`, `apps/tax_backup/models.py:61` | Treasury/Tax | Solo un valor de enum para contabilidad interna — **sin integración real** |
| Env vars | `config/settings.py:311-320,361-368`, `.env`/`.env.example` | Global | `MP_ACCESS_TOKEN`, `MP_CLIENT_ID`, `MP_CLIENT_SECRET`, `MP_REDIRECT_URI`, `MP_WEBHOOK_SECRET`, `MP_BASE_URL` — todas **globales de plataforma**, ninguna por-negocio |
| Frontend `/m/[slug]/tip/{success,pending,failure}` | `apps/web/src/app/m/[slug]/tip/*` | Menu/Tips | Páginas de retorno de Checkout Pro — patrón análogo al que necesitaría `/t/[slug]` |

**No existe ningún código de `appointments`/Turnos** en el repo (backend ni frontend) — confirmado por grep exhaustivo, cero resultados para "turnos"/"appointments".

---

## 3. OAuth y `MercadoPagoConnection` — flujo actual completo

*(Fuente: agente de auditoría dedicado, HECHO COMPROBADO salvo que se indique lo contrario)*

**Modelo** (`apps/menu/models.py:247-271`): `OneToOneField('business.Business', related_name='mp_connection', on_delete=CASCADE)` — exactamente una conexión por negocio a nivel de DB. Campos: `access_token` (`CharField(512)`), `refresh_token` (`CharField(512)`, **guardado pero nunca leído/usado en ningún punto del código** — no hay refresh implementado), `token_expires_at`, `mp_user_id`, `scope`, `status` (`connected/expired/revoked/error` — **solo `'connected'` se escribe alguna vez**; `expired`/`revoked`/`error` están en el enum pero el código nunca los asigna), `last_error` (nunca se le asigna un valor no vacío), timestamps.

**Cifrado: NO existe.** `access_token`/`refresh_token` son `CharField` planos — texto claro en la base de datos. Grep de `Fernet|encrypt|EncryptedField|cryptography` en `apps/menu` y alrededores: cero resultados relevantes.

**Flujo OAuth** (`apps/menu/urls.py:59-62`, `views.py:787-929`):
- **Start**: requiere usuario autenticado + membership + permiso `manage_settings`. Genera `state = base64(f"{business.id}:{secrets.token_urlsafe(24)}")`, pero la fuente de verdad es `cache.set(f"mp_oauth_state:{state}", business.id, ttl=600)` en **Redis compartido** — el `business_id` embebido en el propio token no se usa para validar, solo la entrada de cache. Esto es un diseño CSRF correcto y robusto (192 bits de entropía, un solo uso, TTL 10 min).
- **Callback**: `AllowAny` (correcto, MP redirige sin sesión). Valida `state` contra cache (borra tras uso → previene replay), intercambia `code` por tokens contra `https://api.mercadopago.com/oauth/token` con `MP_CLIENT_ID`/`MP_CLIENT_SECRET` globales, resuelve el `Business` por el `business_id` recuperado del cache (no por sesión), y hace `update_or_create(business=business, defaults={...})` — **sobrescribe totalmente** la conexión anterior sin versionado ni historial.
- **Disconnect**: `DELETE` físico de la fila; **no revoca el token en el lado de MP**.
- **Reconexión/expiración**: no hay ningún mecanismo (Celery, chequeo en request-time) que compare `token_expires_at` con `now()` y dispare un refresh o marque `status='expired'`. El ciclo de vida de `status` está definido en el modelo pero no implementado operativamente.

**Multi-tenant**: no hay `Manager`/queryset que fuerce el scoping por `business` (no existe `for_business()`); todos los call sites actuales acceden vía `business.mp_connection` (reverse OneToOne desde una instancia de `Business` ya resuelta) o filtran manualmente por `business=business` — **hoy no hay fuga cross-tenant demostrada**, pero tampoco hay barrera estructural que la impida a futuro si alguien escribe `MercadoPagoConnection.objects.get(pk=<id de URL>)` sin filtrar. Tampoco hay `unique=True` en `mp_user_id`: nada impide que la misma cuenta MP quede asociada a dos `Business` distintos sin que el sistema lo detecte.

**Consumidores**: `MercadoPagoConnection` **solo se usa dentro de `apps/menu`** (grep exhaustivo en todo `services/api/src`, cero resultados fuera de esa app) — ni `billing` ni ningún otro módulo la conocen. `billing` usa exclusivamente el token global `MP_ACCESS_TOKEN`, un mecanismo completamente separado.

**Tests**: **cero.** Ninguno de los 7 archivos de test de `apps/menu/tests/` menciona `MercadoPagoConnection`, OAuth, ni las vistas Start/Callback/Status/Disconnect.

### Clasificación de reutilización (respuesta a la pregunta obligatoria de la Sección 5)

**SÍ, pero requiere extracción/refactor.** El modelo en sí no tiene ninguna FK hacia entidades de dominio de Menu (`MenuItem`, `MenuCategory`, etc.) — su única relación es con `Business`; es, en esencia, ya un modelo "a nivel de Business" mal ubicado dentro de `menu`. Lo que sí está acoplado es: (a) el namespace de URLs (`/api/v1/menu/mercadopago/...`), (b) el redirect final hardcodeado a `/app/settings/online-menu?mp_connected=1`, y (c) que hoy es la **misma** conexión OneToOne la que serviría tanto a Tips como a Turnos — desconectar MP desde la pantalla de Carta Online cortaría también los pagos de Turnos, violando la independencia de producto exigida en el brief. Antes de reutilizar en producción para dinero de clientes de Turnos: cifrar los tokens, implementar el refresh real, decidir la política sobre `mp_user_id` duplicado, y agregar tests (hoy inexistentes).

---

## 4. Pagos de clientes existentes — Menu/Tips

*(HECHO COMPROBADO salvo lo marcado)*

**`TipTransaction`** (`apps/menu/models.py:278-315`): PK UUID, `business` FK, `amount`/`currency`, `status` (`created/pending/approved/rejected/cancelled` — **sin estado `refunded`**), `provider='mercadopago'`, `mp_preference_id`, `mp_payment_id`, `external_reference` único (`"TIP-{uuid4().hex[:20].upper()}"` — opaco, no adivinable), `menu_slug`, `table_ref`.

**Creación del pago** — `PublicTipCreatePreferenceView` (`views.py:936-1063`): usa el SDK oficial de MP para crear una **preferencia de Checkout Pro** (no Bricks/Checkout API). **Selección de credencial** (`views.py:963-983`, el punto más importante de todo el audit):

```python
try:
    conn = business.mp_connection
    if conn.status == 'connected':
        access_token = conn.access_token          # ← token del NEGOCIO (correcto)
except MercadoPagoConnection.DoesNotExist:
    pass
if not access_token:
    access_token = getattr(settings, 'MP_ACCESS_TOKEN', None)   # ← fallback GLOBAL de la plataforma
```

Cuando el negocio está conectado, la preferencia se crea con **su propio** `access_token` — esto demuestra técnicamente que el dinero llega a la cuenta MP del negocio (no hay `marketplace_fee`/`application_fee`/`collector_id` en ningún lugar del código — flujo simple, sin comisión de plataforma implementada). Si el negocio **no** conectó OAuth, cae silenciosamente (solo un log) al token global de MiRubro — es decir, el dinero de esa propina iría a la cuenta de **MiRubro**, no del negocio, sin error visible.

**Webhook**: no vive en `menu` — el `notification_url` que se manda a MP apunta a `apps/billing/mercadopago/webhook`, el mismo endpoint compartido con billing. El despacho usa el prefijo `"TIP-"` de `external_reference` (`billing/views.py:837`) para enrutar a `process_tip_payment`.

**HALLAZGO CRÍTICO** (HECHO COMPROBADO en código, consecuencia en runtime marcada NO VERIFICADO — requiere sandbox): la re-consulta autoritativa del pago contra la API de MP (recomendada y correctamente implementada como patrón — nunca se confía en el body del webhook) se hace con:
```python
class MercadoPagoService:
    def __init__(self):
        self.sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)   # SIEMPRE el token global
```
(`mp_service.py:102-104`). No existe forma de instanciarlo con el token del negocio. `GET /v1/payments/{id}` de Mercado Pago típicamente solo devuelve el pago al token de la cuenta que lo cobró. Para un negocio con OAuth real conectado (`conn.access_token` distinto del token global), el webhook probablemente no puede recuperar el pago, `get_payment()` devuelve `None`, y `process_payment_event` retorna temprano **sin actualizar `TipTransaction` y sin marcar la entrega como fallida** (ver §6). La única confirmación que funcionaría en ese caso es el polling del cliente vía `PublicTipVerifyView` (que sí resuelve correctamente el token del negocio). **Esta es la corrección obligatoria antes de reutilizar este patrón para Turnos.**

**Idempotencia**: sólida en 3 capas (dedup de `WebhookDelivery` por `x_request_id`, `PaymentEvent.event_id` único, actualización write-if-changed en `TipTransaction`). **Gaps**: el mapa de estados del webhook no traduce `refunded`/`charged_back` (sólo lo hace el verify view — inconsistencia), no hay guardas contra webhooks fuera de orden (podría regresar de `approved` a `pending`), y el webhook de tips **nunca transiciona `WebhookDelivery.processing_status`** a `PROCESSED`/`FAILED` — queda en `RECEIVED` para siempre, un punto ciego de auditoría que sí está resuelto para el flujo de suscripciones.

**Tests**: cero — ningún test en todo el repo ejercita `TipTransaction`, las vistas públicas de tips, o el tópico `payment` del webhook.

**Veredicto sobre la pregunta obligatoria de la Sección 6**: el flujo demuestra **PARCIALMENTE** "cliente final → MP → cuenta MP del Business" — sí en la creación del pago, no verificado/probablemente roto en la confirmación asíncrona.

---

## 5. Billing — qué puede reutilizarse y qué no

*(HECHO COMPROBADO salvo lo marcado)*

`mp_service.py` es un wrapper delgado sobre la API de MP (preapproval/plan + preference/payment), siempre instanciado con el token **global** de la plataforma — correcto para suscripciones (MiRubro cobra al negocio), pero **no apto tal cual** para un flujo donde el token debe variar por negocio (Turnos).

**Correlación de suscripciones**: nunca por heurísticas de email — siempre por un identificador dedicado devuelto por MP (`provider_sub_id`, `provider_preapproval_plan_id`) y guardado en el momento de creación. Este *patrón* arquitectónico (no el código) es directamente aplicable a Turnos.

**`WebhookDelivery`** (`billing/models.py:736-794`): modelo bien diseñado — `RECEIVED/DUPLICATED/IGNORED/PROCESSED/FAILED/DEAD_LETTER`, con hash de payload, `x_request_id`, `signature_valid`. **Gap crítico**: `DEAD_LETTER` está definido en el enum pero **jamás se asigna en ningún punto del código** (grep exhaustivo). No existe ninguna tarea Celery que escanee entregas `FAILED` y las reintente — `tasks.py` solo define 4 tareas no relacionadas (`expire_subscriptions`, `expire_checkout_sessions`, `execute_scheduled_cancellations`, `reconcile_promotional_discounts`), y `reconcile_billing` (management command) es **manual únicamente** — no está en `CELERY_BEAT_SCHEDULE` ni en ningún cron. El diseño de recuperación de fallos existe solo en el modelo/docstrings, no en código ejecutable.

**El webhook siempre responde 200** incluso si el procesamiento interno falla (`dispatch_webhook` atrapa toda excepción, marca `FAILED` y nunca re-lanza). Esto **es la práctica recomendada por MP** (evita que los reintentos automáticos de MP dependan de un bug que fallará igual), pero solo es seguro si está emparejado con un reintento interno automático — que, como se documentó arriba, **no existe**. La combinación 200-siempre + sin reintento automático es el hallazgo de mayor riesgo operativo de todo `billing`.

**Firma HMAC** (`_verify_mp_signature`, `webhook_processor.py:596-656`): implementación correcta del esquema documentado de MP (manifest `id:...;request-id:...;ts:...`, `hmac.compare_digest`), fail-closed en producción si falta el secreto, bypass solo en `DEBUG=True` con warning explícito. **Es el componente más sólido y directamente reutilizable de todo el audit.**

**Manejo de excepciones**: patrón consistente y correcto — efectos secundarios no críticos (emails, campos legacy, logs de auditoría) están envueltos en `except Exception` con log, nunca silenciados sin log, y nunca hacen rollback del estado canónico. No se encontró ningún `except: pass` silencioso sobre algo con dinero/estado real, salvo el punto ciego ya mencionado del tópico `payment` en el webhook de tips.

### Clasificación por pieza

| Pieza | Clasificación |
|---|---|
| Verificación de firma HMAC | **REUTILIZAR** tal cual |
| `WebhookDelivery` (modelo + patrón persist-first) | **EXTRAER A INFRAESTRUCTURA GENÉRICA, con corrección** (implementar `DEAD_LETTER`/retry antes) |
| Creación de preference/payment (`mp_service.create_preference`) | **EXTRAER**, parametrizando el token (hoy hardcodeado al global) |
| Preapproval/preapproval plan | **NO REUTILIZAR** (dominio de suscripción recurrente, sin analogía en depósitos únicos) |
| Retry/dead-letter de webhooks fallidos | **REQUIERE CORRECCIÓN ANTES DE REUTILIZAR** (no existe funcionalmente hoy) |
| Patrón de correlación por identificador dedicado (no email) | **REUTILIZAR** (patrón, no código) |
| Reconciliación manual (`reconciliation.py`, mgmt command) | **NO REUTILIZAR el código** / **REUTILIZAR el patrón** |
| Guard de "ownership" anti cross-tenant en búsquedas de MP (`reconciliation.py:156-165`) | **REUTILIZAR** (patrón) — crítico para cuando Turnos busque contra la cuenta MP *del negocio*, que puede devolver pagos de otros clientes de ese mismo negocio |
| `SubscriptionV2`, `PaymentAttempt`, `MpCheckoutSession`, `BillingInvoiceEvent` | **NO REUTILIZAR** — saturados de campos específicos de suscripción recurrente |

---

## 6. Webhooks — estado real, idempotencia y recuperación

- **Idempotencia**: sólida (dedup por `x_request_id`, campos `unique=True` en `provider_sub_id`/`provider_authorized_payment_id`/`event_id`, updates write-if-changed, chequeos con `select_for_update()` para condiciones de carrera).
- **Recuperación de fallos**: **no implementada** pese a que el modelo está diseñado para ello. `FAILED` es un estado terminal de facto — sin reintento automático, sin promoción a `DEAD_LETTER`, dependiente de que un operador note el error en logs/admin y ejecute `reconcile_billing` manualmente con los identificadores correctos extraídos a mano del `body_json`.
- **Punto ciego específico de Tips**: el tópico `payment` (el que usan tanto tips como, potencialmente, Turnos) nunca actualiza `WebhookDelivery.processing_status` más allá de `RECEIVED` — a diferencia de `subscription_preapproval`/`subscription_authorized_payment`, que sí transicionan correctamente a `PROCESSED`/`FAILED`.
- **Conclusión para Turnos**: la infraestructura de firma + ledger de `billing` es la base correcta, pero **antes de construir Turnos sobre ella** hay que: (1) arreglar el bug de token en `MercadoPagoService` (§4), (2) hacer que el tópico `payment` transicione `WebhookDelivery` igual que los tópicos de suscripción, y (3) construir el reintento automático de `FAILED`→`DEAD_LETTER` que hoy no existe para ningún flujo del repo.

---

## 7. Seguridad y multi-tenant — hallazgos

### OAuth
- `state` con 192 bits de entropía, un solo uso, TTL 10 min en Redis compartido — **robusto** contra CSRF/replay.
- El `business` de origen se resuelve por membership real del usuario autenticado, nunca por un parámetro que el cliente controle — correcto.
- Sin PKCE (**NO VERIFICADO** si MP lo soporta/recomienda para este flujo — requiere validación contra documentación oficial).
- Desconexión no revoca el token en el lado de MP (solo borra la fila local).

### Tokens
- **Almacenados en texto plano** en `MercadoPagoConnection.access_token`/`refresh_token` — sin cifrado, sin KMS. Cualquiera con acceso de lectura a la base (o a un backup/dump) puede leer el token de cualquier negocio. **Debe cifrarse antes de manejar depósitos de clientes reales.**
- `refresh_token` se guarda pero nunca se usa — el ciclo de vida de expiración/renovación no está implementado.
- No aparecen en serializers públicos (`MercadoPagoConnectionStatusSerializer` solo expone `connected`/`status`/`mp_user_id`/`updated_at`) — correcto.

### Webhooks
- Verificación HMAC correcta y con test dedicado que pasa (`test_webhook_signature.py`, 9/9 tests).
- Re-consulta server-to-server contra la API de MP en vez de confiar en el payload — patrón correcto, pero roto para tokens por-negocio (§4/§5).
- Sin replay real posible gracias al dedup por `x_request_id` + `external_reference` opaco.

### Multi-tenant
- No hay un caso de fuga cross-tenant demostrado hoy, pero tampoco hay una barrera estructural (`Manager` con scoping obligatorio) que lo impida a futuro en `MercadoPagoConnection`.
- El patrón de "ownership guard" de `reconciliation.py:156-165` (filtrar explícitamente resultados de búsqueda de MP para no procesar registros de otro tenant) es el guard mínimo que Turnos **debe** replicar, porque al buscar contra la cuenta MP *del negocio* (no la de la plataforma), esa cuenta puede tener otros pagos no relacionados con MiRubro.
- `mp_user_id` no tiene restricción de unicidad — nada impide que la misma cuenta MP quede vinculada a dos `Business`.

### Público
- La landing pública `/m/[slug]` y el análogo esperable `/t/[slug]` ya usan slugs opacos de negocio, no IDs secuenciales — patrón correcto a mantener. `TipTransaction.external_reference` es UUID-derivado, no adivinable — el mismo esquema debe aplicarse al `AppointmentPayment` de Turnos.

---

## 8. Comparativa de arquitecturas

### Opción A — Reutilizar directamente `menu.MercadoPagoConnection`
- **Acoplamiento**: alto — Turnos importaría un modelo de la app `menu`, violando la independencia de producto exigida en el brief.
- **Riesgo específico y decisivo**: al ser un `OneToOneField` con `business`, **una sola conexión serviría a Tips y a Turnos simultáneamente**. Desconectar MP desde la pantalla de configuración de Carta Online cortaría también los cobros de depósitos de Turnos (y viceversa) — un acoplamiento operativo inaceptable entre dos productos que el brief exige mantener independientes.
- **Migraciones**: ninguna nueva, pero el namespace de URLs/redirects sigue atado a Menu.
- Descartada.

### Opción B — Extraer a infraestructura genérica (`merchant_payments` o equivalente)
- **Acoplamiento**: bajo — Menu y Turnos (y futuros productos) consumen un servicio compartido, cada uno con su propia lógica de negocio encima.
- **Riesgo**: moderado y acotado — requiere migrar el modelo existente (posible con `state_operations`/migración de datos estándar de Django) sin romper Tips.
- **Duplicación**: mínima — el flujo OAuth (Start/Callback/Status/Disconnect), que ya es sólido en su diseño de `state`/CSRF, se escribe **una sola vez** y sirve a todos los productos.
- **Multi-tenant/seguridad**: se corrigen los defectos encontrados (cifrado, refresh, `mp_user_id` único opcional) **una sola vez**, beneficiando a Menu retroactivamente.
- **Deuda técnica**: la existente (texto plano, sin refresh, sin tests) se paga una vez en la extracción en vez de duplicarse.
- **Costo**: el más alto de las tres opciones en el corto plazo (Slice 1), pero el único que escala a "otros productos futuros" mencionados explícitamente en el brief.

### Opción C — `AppointmentMercadoPagoConnection` dedicada
- **Acoplamiento**: nulo con Menu — aislamiento total.
- **Riesgo**: bajo a corto plazo, pero **reinventa** una pieza (el flujo OAuth con `state` en Redis, CSRF, exchange de tokens) que ya está bien resuelta en `menu` — duplicar esa lógica es trabajo redundante y una segunda superficie de bugs para el mismo problema.
- **Duplicación**: alta — si mañana POS o Restaurante también necesitan cobrar a través de MP con la cuenta del negocio, se triplicaría el mismo código.
- **Evolución**: mala — no hay un lugar único donde arreglar/mejorar el flujo OAuth para todos los productos.

### Selección

**Opción B.** Es la única que respeta la independencia de producto exigida en el brief sin duplicar una pieza de infraestructura (el flujo OAuth) que ya está bien diseñada en su núcleo (manejo de `state`, CSRF, Redis) y que solo necesita — no reescribirse, sino — corregirse en un lugar (cifrado, refresh, token por-negocio en el webhook) y reubicarse fuera del dominio de Menu.

---

## 9. Recomendación final — árbol de archivos tentativo

```
services/api/src/apps/merchant_payments/          # nueva app, Slice 1
├── __init__.py
├── apps.py
├── models.py            # MerchantMercadoPagoConnection (ex menu.MercadoPagoConnection, migrada)
│                         # + WebhookDelivery genérico (adaptado de billing, con DEAD_LETTER real)
├── oauth.py              # Start/Callback/Status/Disconnect (extraído de menu/views.py, generalizado
│                         #   con un campo de "origen"/producto para el redirect final)
├── mercadopago_client.py # Wrapper SDK PARAMETRIZADO por token (a diferencia de billing.mp_service,
│                         #   que está hardcodeado al token global — este acepta business/connection)
├── webhooks.py            # Verificación HMAC + dispatch + dedup (adaptado de billing/webhook_processor.py)
├── services.py            # Resolución de token (business → connection → error explícito, SIN fallback
│                         #   silencioso al token global para flujos de dinero de terceros)
├── serializers.py
├── urls.py
├── migrations/
│   └── 0001_move_mercadopago_connection.py   # migra datos desde menu.MercadoPagoConnection
└── tests/
    ├── test_oauth_flow.py
    ├── test_webhook_signature.py
    └── test_token_resolution.py

services/api/src/apps/appointments/               # Slice 1+ (NO en este slice)
├── models.py            # Appointment, AppointmentPayment (FK a merchant_payments vía business)
├── ...
```

`apps/menu` pasa a **consumir** `merchant_payments` (import de `MerchantMercadoPagoConnection` en vez de definir su propio modelo) en un slice posterior, sin romper `TipTransaction` (que se queda en `menu`, solo cambia de dónde obtiene el token).

---

## 10. Flujo Turnos → Mercado Pago (diagrama textual end-to-end)

```
Cliente final
   │
   ▼
GET /t/[slug]                         → resuelve Business por slug (público, opaco)
   │
   ▼
Cliente elige servicio/horario/profesional
   │
   ▼
POST /api/v1/appointments/public/slug/<slug>/book/
   → crea Appointment(status=PENDING_PAYMENT), AppointmentPayment(status=CREATED)
   → external_reference = f"APPT-{uuid4().hex[:20].upper()}"   (prefijo NUEVO, distinto de "TIP-")
   │
   ▼
Resolver MerchantMercadoPagoConnection del Business
   → si status != 'connected': ERROR EXPLÍCITO (503), *nunca* fallback silencioso al token
     global de MiRubro — a diferencia de Tips, acá el fallback movería fondos de un cliente
     final a la cuenta de MiRubro por error de configuración del negocio, inaceptable.
   │
   ▼
POST /checkout/preferences  (Mercado Pago, Checkout Pro)
   con: access_token = connection.access_token (del NEGOCIO)
        external_reference = "APPT-..."
        notification_url = <BASE_PUBLIC_URL>/api/v1/merchant-payments/mercadopago/webhook
        metadata = {appointment_id, business_id}
        back_urls = /t/<slug>/booking/<id>/{success,pending,failure}
   │
   ▼
Cliente paga en MP con SU medio de pago → dinero va a la cuenta MP del Business (no de MiRubro)
   │
   ├──▶ (sync) Cliente vuelve a back_url `success` → polling/verify: resuelve token del
   │           NEGOCIO correspondiente al Appointment y confirma contra la API de MP
   │
   └──▶ (async) Mercado Pago → POST webhook → verificación HMAC → WebhookDelivery(RECEIVED)
              → dedup por x_request_id
              → resolver Appointment/business por external_reference "APPT-..."
              → re-consultar el pago usando el token DEL NEGOCIO correcto (fix del bug de §4)
              → AppointmentPayment.status = APPROVED (idempotente, write-if-changed)
              → Appointment.status = CONFIRMED (con guarda de máquina de estados: nunca
                regresar desde un estado terminal)
              → WebhookDelivery.processing_status = PROCESSED (o FAILED con reintento real)
              → notificación interna a MiRubro (email/Slack) al negocio
```

**Qué NO debe confiarse al frontend**: `amount` (siempre desde `Service.price`/`deposit` en servidor, nunca desde el body del POST del cliente — mismo patrón ya usado en `test_qr_reviews_monthly_payload.py` para billing), `business_id` (se resuelve por `slug`, no por ID enviado por el cliente), `external_reference` (generado en servidor).

**Manejo de casos borde**:
- **Pago duplicado**: `external_reference` único a nivel DB + dedup de `WebhookDelivery` por `x_request_id`.
- **Webhook duplicado**: dedup ya cubierto arriba.
- **Webhook fuera de orden**: requiere guarda explícita de máquina de estados (`AppointmentPayment` no debe regresar de `APPROVED`/`REJECTED` a `PENDING`) — **hoy no existe ni siquiera en Tips**, debe construirse para Turnos desde el inicio.
- **Webhook fallido**: debe transicionar a `FAILED` y quedar en una cola de reintento real (a construir — hoy no existe para ningún flujo del repo).
- **Callback exitoso antes del webhook**: aceptable — ambos caminos son idempotentes y convergen al mismo estado final; el callback no debe ser la única fuente de verdad (siempre re-verificar contra la API de MP, nunca contra el query param `status` de la URL de retorno).
- **Cliente abandona el checkout**: `AppointmentPayment` queda en `PENDING`/`CREATED` — requiere una tarea periódica (Celery, siguiendo el patrón de `expire_checkout_sessions` de billing) que expire reservas no pagadas tras un TTL y libere el horario.
- **Pago rechazado**: `AppointmentPayment.status = REJECTED`, `Appointment` vuelve a estado que libera el horario.

---

## 11. Modelo conceptual sugerido (sin migraciones ni código)

- **`MerchantMercadoPagoConnection`** (en `merchant_payments`, ex `menu.MercadoPagoConnection` migrada): identidad OAuth del negocio ante Mercado Pago — un negocio, una cuenta MP, con token cifrado en reposo y ciclo de vida de expiración/refresh implementado (a diferencia del actual).
- **`AppointmentPayment`** (en `appointments`): registro de una intención/resultado de cobro de seña, análogo a `TipTransaction` pero con estados adicionales (incluyendo un estado de reembolso, ausente hoy en `TipTransaction`) y una máquina de estados con guardas contra regresión. Se correlaciona 1:1 (o 1:N si se permiten reintentos de pago) con `Appointment`.
- **`WebhookDelivery`** (genérico, en `merchant_payments`, evolución del de `billing`): ledger de toda notificación entrante de MP para pagos de comercio (Tips + Turnos + futuros), con firma verificada, dedup, y — a diferencia del actual — un mecanismo de reintento/`DEAD_LETTER` realmente implementado.

---

## 12. Riesgos

**CRÍTICO**
- `MercadoPagoService` hardcodeado al token global de la plataforma hace que la confirmación asíncrona (webhook) probablemente falle en silencio para negocios con OAuth real conectado — si se hereda sin corregir, los depósitos de Turnos podrían no confirmarse nunca vía webhook.
- Tokens OAuth almacenados en texto plano — exposición total en caso de acceso a la base/backup.
- Fallback silencioso al token global de la plataforma cuando un negocio no tiene MP conectado (hoy en Tips) — para Turnos, replicar este fallback movería depósitos de clientes reales a la cuenta de MiRubro sin error visible.

**ALTO**
- No existe reintento automático de webhooks `FAILED` ni implementación real de `DEAD_LETTER` — cualquier fallo transitorio en el procesamiento de un pago de depósito requeriría intervención manual para no perderse.
- Sin máquina de estados con guardas anti-regresión para pagos — un webhook fuera de orden podría, en teoría, revertir una confirmación.
- Cero cobertura de tests en todo el flujo de OAuth/tips de `menu` — cualquier regresión ahí pasaría desapercibida.

**MEDIO**
- `mp_user_id` sin restricción de unicidad — una misma cuenta MP podría vincularse a dos negocios sin detección.
- Sin revocación real en el lado de MP al desconectar — el token queda válido en MP aunque se borre localmente.
- Inconsistencia en el mapeo de estados `refunded`/`charged_back` entre el webhook y el verify view de Tips.

**BAJO**
- `refresh_token` guardado pero nunca usado (deuda, no riesgo inmediato mientras los tokens no expiren en la práctica).
- Suite de tests con `pytest` crudo falla en varios archivos por una colisión de import (`src/__init__.py` + imports relativos) — mitigable usando `manage.py test`; no es un bug de producto pero enlentece cualquier CI futura.

---

## 13. Bloqueantes antes de implementar Turnos con pagos reales

1. Corregir `MercadoPagoService` (o su equivalente en `merchant_payments`) para operar con el token **del negocio correcto**, no el token global — sin esto, el webhook de confirmación no es confiable.
2. Cifrar `access_token`/`refresh_token` en reposo antes de manejar depósitos de clientes finales.
3. Decidir y documentar la política de fallback cuando un negocio no tiene MP conectado (recomendado: **error explícito**, nunca fallback silencioso al token de plataforma, para flujos de dinero de terceros).
4. Verificar contra documentación oficial/sandbox de Mercado Pago (marcado `NO VERIFICADO` en este audit): comportamiento exacto de `GET /v1/payments/{id}` respecto a qué tokens pueden leer un pago dado, y si PKCE aplica/recomienda para este flujo OAuth Connect.

Ninguno de estos bloqueantes es de arquitectura — todos son correcciones puntuales y acotadas sobre código existente.

---

## 14. Próximo slice recomendado (Slice 1)

**Alcance de Slice 1**: extraer `MercadoPagoConnection` de `menu` hacia la nueva app `merchant_payments` (modelo + OAuth Start/Callback/Status/Disconnect generalizados, con redirect final parametrizable por producto de origen), corrigiendo en el mismo movimiento: cifrado de tokens en reposo, eliminación del fallback silencioso al token global para el nuevo consumidor (Turnos), y parametrización de `MercadoPagoService`/`mercadopago_client` por token de negocio en vez de token global. Migrar los call sites de `apps/menu` (Tips) al nuevo modelo sin cambiar su comportamiento observable, agregando en el proceso los tests que hoy no existen para el flujo OAuth y de Tips. **No** crear todavía ningún modelo ni endpoint de `appointments` — eso queda para Slice 2, una vez que `merchant_payments` esté probado y sea la base estable sobre la que construir el dominio de Turnos.

---

## Anexo — Inventario y resultado de tests ejecutados

| Suite | Comando | Tests | Resultado | Alineación |
|---|---|---|---|---|
| `treasury/tests/test_treasury.py` | `pytest treasury/tests/test_treasury.py --reuse-db` | 13 | PASS | Alineada |
| `billing/tests/test_mp_integration.py` | `pytest ...` | 44 | 9 FAILED / 35 pass | **Desalineada** — referencia métodos removidos (`activate_tenant`, `process_subscription_event`), refactorizados a `webhook_processor.py` |
| `billing/tests/test_webhook_signature.py` | `pytest ...` | 9 | PASS | Alineada — cubre `_verify_mp_signature` actual |
| `billing/tests/test_checkout_flow_v2.py` | `pytest ...` | 24 | 20 FAILED / 4 pass | **Desalineada** — fixture `_make_plan()` usa `billing_cycle`, campo removido del modelo `Plan` |
| `billing/tests/test_reconcile_session.py` | `pytest ...` | 18 | PASS | Alineada |
| `billing/tests/test_promo_checkout.py` | `pytest ...` | 11 | PASS | Alineada |
| `billing/tests/test_qr_reviews_monthly_payload.py` | `pytest ...` | 8 | PASS | Alineada |
| `billing/tests/test_subscriptionv2_birth_path.py` | `pytest ...` | 22 | 12 FAILED / 10 pass | **Desalineada** — mismos métodos removidos + mock apuntando al módulo incorrecto tras refactor |
| `billing/tests/test_v2_addon_parity.py` | `pytest ...` | 33 | 3 FAILED / 30 pass | Mayormente alineada — 3 fallos por cambio de regla de negocio (addon `invoicing` ya no disponible en plan `start`), no por bug |
| `reviews/tests/test_e2e_lifecycle.py` | `manage.py test apps.reviews.tests.test_e2e_lifecycle` | 47 | PASS | Alineada (incluye test de idempotencia de webhook) |
| `billing/tests/test_reviews_upgrade.py` | `pytest ...` | 10 | PASS | Alineada |
| `billing/tests/test_qr_reviews_service_activation.py` | `pytest ...` | 18 | PASS | Alineada |
| `billing/tests/test_promo_cycle.py` | `pytest ...` | 17 | PASS | Alineada |
| `apps/menu/tests/*` (7 archivos) | — | — | **Sin cobertura** | Ningún test ejercita OAuth ni Tips |

Nota de infraestructura: no había Postgres/Redis corriendo en el entorno; se levantaron contenedores Docker efímeros y aislados (sin puertos publicados al host) exclusivamente para correr estas suites, y se destruyeron al finalizar — no se modificó ningún archivo del repo ni se dejó infraestructura corriendo.
