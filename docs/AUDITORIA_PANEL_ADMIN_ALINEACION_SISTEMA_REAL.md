# Auditoría integral del panel admin — Alineación con el sistema real

| Metadato | Valor |
|---|---|
| **Fecha de actualización** | 2026-08-04 |
| **Rama** | `develop` |
| **Commit auditado (HEAD)** | `7e1ef92` |
| **Commit base de la auditoría anterior** | `3e33830` (ver nota de vigencia abajo) |
| **Evento entre ambas auditorías** | Merge `origin/master` → `develop` (integración del código de producción) |
| **Merge base detectado** | `origin/master` en `7446016` |
| **Working tree** | Sin cambios de código — único archivo modificado: este documento (untracked) |
| **Autor de la auditoría** | GitHub Copilot (asistente) |

> **Nota de vigencia**: Esta actualización **reemplaza** las conclusiones de la auditoría realizada sobre `3e33830`. Ninguna conclusión de esa versión se reutiliza como vigente sin re-verificación explícita sobre `7e1ef92`. Los resultados de tests de `3e33830` se conservan solo como referencia histórica marcada explícitamente como tal (ver §15).

---

## 1. Resumen ejecutivo

El panel de plataforma de Mi Rubro (`/admin`) está operativo en las rutas auditadas y usa `billing.SubscriptionV2` como fuente canónica de suscripciones, con separación correcta de roles y auditoría de acciones sensibles. **La firma y parte de la idempotencia [del flujo de webhooks de Mercado Pago] fueron verificadas, pero el flujo no puede calificarse como robusto: los handlers fallidos responden 200 y no existe recuperación interna demostrada para deliveries `FAILED`.**

**Cambio principal respecto a la auditoría anterior (3e33830)**: el merge de `origin/master` → `develop` incorporó al repositorio la sección de configuración de QR de Reseñas del panel admin que en la auditoría anterior se había clasificado como **POSIBLE DIVERGENCIA ENTRE REPOSITORIO ACTUAL Y DESPLIEGUE** (HAL-001). Esa clasificación **queda cerrada y resuelta**: el código ahora existe en el repositorio, fue re-auditado de forma independiente línea por línea (frontend + backend), y sus 22 tests backend + 16 tests frontend (12 tests de `QRResenasCard` + 4 tests de `url.ts`) nuevos se ejecutaron y pasan en `7e1ef92` (evidencia en §15).

La re-auditoría del endpoint nuevo (`AdminQRReviewsConfigView`) encontró un hallazgo propio no reportado antes: ambos métodos `GET` y `PATCH` registran la misma acción de auditoría `ADMIN_CLIENT_VIEWED`, de modo que las escrituras (cambios de slug, Place ID, etc.) quedan indistinguibles de las lecturas en `AccessAuditLog` (ver §8.5 y R-04 nuevo en §18).

Se re-confirmaron sobre `7e1ef92` (no se asumieron desde la auditoría anterior): los 3 tests con fallo en el módulo de autenticación MFA del admin (mismos 3, mismo síntoma), y las duplicaciones reales de `google_place_id` entre `ReviewConfig` y `MenuEngagementSettings` sin sincronización entre ellas. Además, se detectó un hallazgo nuevo no relacionado al merge de QR Reseñas: la suite `apps.billing.tests.test_checkout_flow_v2` tiene 20 errores por desalineación de esquema (`Plan.billing_cycle` no existe como campo) — deuda técnica preexistente, fuera del alcance de este merge, documentada en §15.3 y §18.

---

## 2. Veredicto general

| Área | Estado |
|---|---|
| Panel admin — estructura general | ✅ Funcional y alineado |
| Suscripciones — fuente canónica | ✅ `SubscriptionV2` exclusivo |
| Cancelación administrativa (camino feliz) | ✅ Implementada correctamente (49/49 tests, re-ejecutado en 7e1ef92) |
| Cancelación administrativa — MP éxito + escritura local fallida | ⚠️ Escenario posible sin recuperación demostrada por test real (ver §11.8, R-16) |
| Webhooks — Firma HMAC | ✅ Verificada (9/9 tests `test_webhook_signature` re-ejecutados en 7e1ef92) |
| Webhooks — Deduplicación | ⚠️ Comprobada por código (`x_request_id`/hash), pero las suites que la ejercen contra la vista actual (`test_mp_integration`, `test_subscriptionv2_birth_path`) están rotas — ver §15.1 |
| Webhooks — Procesamiento de tópicos (`subscription_preapproval`, `subscription_authorized_payment`) | ❌ Cobertura incompleta — mismas suites rotas, sin test vigente que ejercite el handler real end-to-end |
| Webhooks — Recuperación de deliveries `FAILED` | ❌ Ausente — sin mecanismo de reprocesamiento (ver §13.6, R-02) |
| Webhooks — Entrega efectiva desde Mercado Pago | ❓ No verificada — `notification_url` no se envía en `create_preapproval()`/`create_preapproval_plan()` y el contrato externo no está resuelto (ver §13.5b) |
| Reconcile URL | ✅ Ruta correcta (`/reconcile/` como path segment, 18/18 tests) |
| QR de Reseñas en panel admin | ✅ HECHO COMPROBADO — implementado, endpoint propio, 22/22 tests backend + 16/16 tests frontend (12 `QRResenasCard` + 4 `url.ts`) |
| Auditoría de escritura en QR Reseñas admin | ⚠️ Acción `ADMIN_CLIENT_VIEWED` mal etiquetada para PATCH (hallazgo nuevo) |
| `google_place_id` duplicado | ⚠️ Dos modelos sin sincronización (re-confirmado) |
| Modelo legacy `billing.Subscription` | ⚠️ Sigue escribiéndose en activación `qr_reviews` |
| Tests MFA admin | ❌ 3 fallos re-confirmados en 7e1ef92 (respuestas 403 en vez de 200/400) |
| `test_checkout_flow_v2` (billing) | ❌ 20 errores por desalineación de esquema — preexistente, no causado por este merge |

---

## 3. Baseline manual observado

**Evidencia funcional** (no modificar ni consultar producción — registro manual conservado de la auditoría anterior, usado únicamente como referencia para contrastar contra el código ya confirmado en `7e1ef92`):

La URL `https://www.mirubro.com/admin/clientes/12` mostraba una sección funcional de QR de Reseñas con:

| Campo observado | Valor |
|---|---|
| Producto habilitado | Sí |
| Modo | Filtro inteligente |
| Umbral | 5 estrellas |
| Slug | `downtownbasket` |
| URL pública | `https://www.mirubro.com/r/downtownbasket/` |
| Google Place ID mostrado | `ChIJyXhfcgC_V5QRL3of_PcNk0E` |
| Place ID en `google_review_url` | `ChIJQZ9x31i-V5QRn-XwCutktZQ` |
| URL personalizada | `https://g.page/mi-negocio/review` |

**Clasificación actualizada**: **HECHO COMPROBADO — CONSISTENTE**. El merge `origin/master → develop` incorporó el componente `QRResenasCard` (`apps/web/src/components/admin/qr-reviews-card.tsx`) y el endpoint `AdminQRReviewsConfigView` (`services/api/src/apps/reviews/admin_views.py`), que juntos reproducen exactamente los campos observados manualmente: slug editable, Google Place ID, `google_review_url`, `custom_redirect_url`, modo y umbral. La divergencia repo/deploy reportada en la auditoría anterior (HAL-001) queda **cerrada**. Ver sección 8 para el detalle completo re-auditado del flujo frontend + backend.

---

## 4. Inventario del panel admin

### 4.1 Rutas y estructura Next.js

```
apps/web/src/app/admin/
├── page.tsx                                   → redirección a /admin/dashboard
├── layout.tsx                                 → shell admin con navbar
├── login/                                     → autenticación platform staff
├── mfa-setup/                                 → enrolamiento TOTP
├── dashboard/                                 → métricas globales
├── clientes/
│   ├── page.tsx                               → listado paginado
│   ├── clientes-content.tsx                   → componente cliente (usa RSC)
│   └── [clienteId]/
│       ├── page.tsx                           → SSR detail con getAdminClientDetail()
│       └── cliente-detail-content.tsx         → render completo del cliente
├── suscripciones/
│   ├── page.tsx                               → listado paginado
│   ├── suscripciones-content.tsx
│   └── [subscriptionId]/
│       ├── page.tsx                           → SSR detail
│       ├── suscripcion-detail-content.tsx     → render + cancel modal
│       └── __tests__/                         → 10 tests (todos pasan)
├── soporte/                                   → tickets de soporte
├── reportes/                                  → reporting overview
├── blog/                                      → CMS blog (content_admin)
├── configuracion/                             → settings de plataforma
├── promociones/                               → promo codes
└── notificaciones/                            → notificaciones internas staff
```

### 4.2 Mapa por ruta

| Ruta | Componente | Servicio/Hook | Endpoint backend | Modelos | Escrituras | Roles | Tests | Estado |
|---|---|---|---|---|---|---|---|---|
| `/admin/dashboard` | `AdminDashboardMetrics` | `getAdminDashboardMetrics()` | `GET /platform-admin/dashboard/metrics/` | `Business`, `SubscriptionV2`, `SupportTicket`, `AccessAuditLog` | Ninguna | superadmin, operations | Parcial | Completo |
| `/admin/clientes` | `ClientesContent` | `getAdminClients()` | `GET /platform-admin/clients/` | `Business`, `SubscriptionV2`, `Membership` | Ninguna | superadmin, operations | Parcial | Completo |
| `/admin/clientes/[id]` | `ClienteDetailContent` + `QRResenasCard` (condicional) | `getAdminClientDetail()` + `GET/PATCH /platform-admin/clients/{id}/qr-reviews-config/` (fetch propio del componente, no via `getAdminClientDetail`) | `GET /platform-admin/clients/{id}/` (datos generales) y endpoint separado de QR | `Business`, `SubscriptionV2`, `PaymentAttempt`, `BillingEvent`, `AccessAuditLog`, `AdminInternalNote`, `SupportTicket`, `reviews.ReviewConfig` (vía endpoint separado) | Notas internas vía POST; QR config vía PATCH propio | superadmin, operations (QR: mismos roles) | 22 tests backend + 16 tests frontend (12 `QRResenasCard` + 4 `url.ts`) | Completo (QR confirmado en `7e1ef92`) |
| `/admin/suscripciones` | `SuscripcionesContent` | `getAdminSubscriptions()` | `GET /platform-admin/subscriptions/` | `SubscriptionV2`, `BillingEvent` | Ninguna | superadmin, operations | Ninguno | Completo |
| `/admin/suscripciones/[id]` | `SuscripcionDetailContent` | `getAdminSubscriptionDetail()` | `GET /platform-admin/subscriptions/{id}/` | `SubscriptionV2`, `PaymentAttempt`, `BillingEvent`, `BillingInvoiceEvent`, `WebhookDelivery` | Cancelar (POST `cancel/`), notas | superadmin, operations | 10 tests (pasan) | Completo |
| `/admin/soporte` | Tickets | `getAdminTickets()` | `GET /platform-admin/tickets/` | `SupportTicket`, `Business` | Crear/asignar tickets | superadmin, support_agent | Parcial | Completo |
| `/admin/reportes` | Reporting | `getAdminReporting()` | `GET /platform-admin/reports/overview/` | `Business`, `SubscriptionV2` | Ninguna | superadmin, operations | Ninguno | Parcial |
| `/admin/blog` | BlogCMS | `getAdminBlogPosts()` | `GET /platform-admin/blog/posts/` | `BlogPost` | CRUD posts | superadmin, content_admin | Ninguno | Completo |
| `/admin/notificaciones` | Notifications | `getAdminNotifications()` | `GET /platform-admin/notifications/` | `AdminNotification` | Leer/archivar | todos (role-filtered) | Varios | Completo |
| `/admin/promociones` | PromoCodes | `getAdminPromoCodes()` | `GET /platform-admin/promo-codes/` | `PromoCode`, `PromoRedemption` | CRUD promo codes | superadmin, operations | `test_promo_admin.py` | Completo |

### 4.3 Rutas no encontradas en el repositorio

| Ruta esperada | Estado |
|---|---|
| `/admin/configuracion` | Directorio existe pero sin funcionalidad observable en el código |

---

## 5. Detalle de clientes (`/admin/clientes/[id]`)

### 5.1 Datos retornados por `AdminClientDetailView`

**HECHO COMPROBADO** — Archivo: `services/api/src/apps/accounts/platform_admin_clients_views.py`

El endpoint `GET /api/v1/platform-admin/clients/{business_id}/` retorna:

- Datos generales del negocio: `id`, `name`, `slug`, `status`, `service_type`, `country`, `currency`, `created_at`, `activated_at`
- Owner y miembros activos (hasta 20)
- Suscripción activa de `SubscriptionV2` (no canceladas, la más reciente)
- Risk badges calculados dinámicamente
- Últimos 10 pagos de `PaymentAttempt`
- Últimos 10 eventos de `BillingEvent`
- Últimos 10 registros de `AccessAuditLog`
- Hasta 20 notas internas de `AdminInternalNote`
- Perfil fiscal de `BillingProfile`
- Resumen de tickets de soporte con últimos 5 tickets

**AUSENTE del endpoint `AdminClientDetailView` (pero disponible vía endpoint separado)**:

- `ReviewConfig` / QR de Reseñas — **HECHO COMPROBADO**: no está embebido en `AdminClientDetailView`/`AdminClientDetail` (confirmado por lectura de `platform_admin_clients_views.py` y del tipo `AdminClientDetail` en `lib/admin/types.ts`), pero **sí existe y está implementado** como endpoint independiente: `GET/PATCH /api/v1/platform-admin/clients/{business_id}/qr-reviews-config/` (`AdminQRReviewsConfigView`, `services/api/src/apps/reviews/admin_views.py`). El componente `QRResenasCard` (`apps/web/src/components/admin/qr-reviews-card.tsx`) hace su propio fetch a este endpoint, independiente de `getAdminClientDetail()`. Se renderiza condicionalmente en `cliente-detail-content.tsx` solo si `client.service_type === 'qr_reviews'`. Ver detalle completo en §8.

**AUSENTE de ambos (endpoint principal y endpoint QR)**:

- `MenuEngagementSettings`
- `BillingInvoiceEvent` (nota: sí aparece en el detalle de *suscripción*, no en el de *cliente*)
- Entitlements
- Branding/logos

### 5.2 Comportamiento ante ID inexistente

```python
# platform_admin_clients_views.py, línea ~228
try:
    biz = Business.objects.get(pk=business_id, parent__isnull=True)
except Business.DoesNotExist:
    return Response({'detail': 'Cliente no encontrado.'}, status=404)
```

Frontend (`page.tsx`): `if (!client) notFound()` → Next.js 404 page.  
**INFERENCIA**: el filtro `parent__isnull=True` excluye sucursales. Un business_id de sucursal devuelve 404.

### 5.3 Protección entre clientes

Cada `GET /platform-admin/clients/{id}/` carga solo el `Business` con ese PK y `parent__isnull=True`. No hay riesgo de cross-tenant desde este endpoint.

Nota: el endpoint de notas (`POST /platform-admin/notes/`) acepta `target_id` libre. **HECHO COMPROBADO**: no valida que `target_id` sea un business al que el admin tenga acceso específico — cualquier `superadmin` u `operations` puede poner notas en cualquier business_id. Esto es consistente con el modelo de confianza del staff interno, pero no existe validación de ownership en las notas.

### 5.4 Actualización post-guardado

La página es Server Component: usa `router.refresh()` tras acciones del lado cliente (notas). No hay query client TanStack en el detalle de cliente — la invalidación se hace vía hard refresh de Next.js.

---

## 6. Mapa completo: frontend → API → backend → modelo

### 6.1 Detalle de cliente (admin)

```
/admin/clientes/12
  └── getAdminClientDetail(12)                    [lib/admin/index.ts]
        └── serverApiFetch('/api/v1/platform-admin/clients/12/')
              └── AdminClientDetailView.get()      [platform_admin_clients_views.py]
                    ├── Business.objects.get(pk=12, parent__isnull=True)
                    ├── SubscriptionV2.objects.filter(business=biz).exclude(status='canceled')
                    ├── PaymentAttempt.objects.filter(subscription=latest_sub)[:10]
                    ├── BillingEvent.objects.filter(business=biz)[:10]
                    ├── AccessAuditLog.objects.filter(business=biz)[:10]
                    └── SupportTicket.objects.filter(business=biz)
```

### 6.2 Cancelación administrativa

```
/admin/suscripciones/{id} → botón "Cancelar suscripción"
  └── CancelSubscriptionModal → POST /api/v1/platform-admin/subscriptions/{id}/cancel/
        └── AdminSubscriptionCancelView.post()     [platform_admin_subscriptions_views.py]
              └── cancel_subscription_immediately(subscription, canceled_by, reason)
                    ├── select_for_update() → re-valida estado
                    ├── MercadoPagoService.cancel_preapproval(provider_sub_id)
                    │     └── PUT /preapproval/{preapproval_id} {"status": "canceled"}
                    ├── SubscriptionV2: status=CANCELED, is_active=False, canceled_at
                    ├── Business.status = 'onboarding'
                    └── AccessAuditLog (log_platform_action)
```

### 6.3 Flujo público de QR de Reseñas (app del dueño, NO panel admin)

```
/app/resenas/configuracion
  └── review-config-client.tsx
        ├── GET /api/v1/reviews/qr/config/         → ReviewConfigSerializer
        └── PATCH /api/v1/reviews/qr/config/       → ReviewConfigSerializer
              └── ReviewConfig (one-to-one con Business)
                    ├── google_place_id  (editable)
                    ├── google_review_url (editable, independiente)
                    └── custom_redirect_url (editable)
```

### 6.4 Redirect público post-reseña positiva

```
/r/{slug}/  (Next.js route)
  └── backend resolve: Business.slug → ReviewConfig.redirect_url
        └── redirect_url @property:
              1. custom_redirect_url (si existe)
              2. f"https://search.google.com/local/writereview?placeid={google_place_id}"
              3. google_review_url
              4. None
```

### 6.5 QR de Reseñas — panel admin (HECHO COMPROBADO, confirmado en `7e1ef92`)

```
/admin/clientes/{id}  (solo si client.service_type === 'qr_reviews')
  └── QRResenasCard({businessId})              [components/admin/qr-reviews-card.tsx]
        ├── GET  /api/v1/platform-admin/clients/{id}/qr-reviews-config/
        │     └── AdminQRReviewsConfigView.get()  [reviews/admin_views.py]
        │           ├── allowed_internal_roles = ['superadmin', 'operations']
        │           ├── admin_service.build_qr_reviews_snapshot(business)
        │           └── log_platform_action(action='ADMIN_CLIENT_VIEWED')  ← también en GET
        │
        └── PATCH /api/v1/platform-admin/clients/{id}/qr-reviews-config/  (2 formularios independientes: slug / Google Business)
              └── AdminQRReviewsConfigView.patch()  [reviews/admin_views.py]
                    ├── Rechaza campos desconocidos → 400 + `allowed_fields`
                    ├── admin_service.update_admin_qr_reviews_config()
                    │     └── transaction.atomic():
                    │           ├── validate_slug() → lowercase, regex ^[a-z0-9-]+$, max 80, único en DB
                    │           ├── Business.slug = nuevo valor (si se envía)
                    │           └── ReviewConfig: google_place_id / google_place_name /
                    │                 google_place_formatted_address / google_review_url /
                    │                 custom_redirect_url (si se envían; ReviewConfig se crea
                    │                 si no existía — "Sin ReviewConfig — se creará al guardar")
                    ├── Estampa google_place_updated_at SOLO si google_place_id cambió de valor
                    │     (NO recalcula google_review_url)
                    └── log_platform_action(action='ADMIN_CLIENT_VIEWED')  ← BUG: mismo nombre que GET, ver §8.5
```

**slugPreview en el frontend**: `QRResenasCard` construye el preview como
`https://www.mirubro.com/r/${slugValue}/` **hardcodeado** (no usa `lib/url.ts` ni
`NEXT_PUBLIC_SITE_URL`). `lib/url.ts` (`toAbsoluteUrl()`) solo se usa en la página de
blog (`app/(marketing)/blog/[slug]/page.tsx`) — confirmado por grep de todo el repo. Esto
es una duplicación menor, no un bug funcional (ver R nuevo en §18).

---

## 7. Fuentes canónicas actuales

| Dominio | Fuente canónica | Modelo legacy activo | Panel admin lee |
|---|---|---|---|
| Cliente / negocio | `business.Business` | — | Sí |
| Owner | `accounts.Membership` (role=owner) | — | Sí |
| Plan | `billing.Plan` | — | Indirecto (plan_code) |
| Suscripción | `billing.SubscriptionV2` | `billing.Subscription` (legacy, OneToOne) | SubscriptionV2 exclusivamente |
| Pagos recurrentes | `billing.PaymentAttempt` | `billing.PaymentEvent` (legacy) | PaymentAttempt |
| Eventos de billing | `billing.BillingEvent` | — | Sí |
| Facturación autorizada | `billing.BillingInvoiceEvent` | — | Sí (en detalle suscripción) |
| Webhooks | `billing.WebhookDelivery` | — | Sí (errores) |
| QR Reseñas config | `reviews.ReviewConfig` | — | **Sí** — vía `GET/PATCH /platform-admin/clients/{id}/qr-reviews-config/` (endpoint separado, no embebido en `AdminClientDetailView`) |
| Slug (QR Reseñas) | `business.Business.slug` | — | Sí — editable desde el mismo endpoint QR, misma validación (`validate_slug()`) que la fuente canónica de `Business.save()` |
| Google Place (reseñas) | `reviews.ReviewConfig.google_place_id` | `menu.MenuEngagementSettings.google_place_id` (independiente, sin sync) | Sí (solo el de `ReviewConfig`; `MenuEngagementSettings` no tiene UI admin) |
| Entitlements QR Reseñas | `billing.SubscriptionV2.plan_code` + `reviews.entitlements` | — | No |
| Notas internas | `accounts.AdminInternalNote` | — | Sí |
| Auditoría admin | `accounts.AccessAuditLog` | — | Sí (con hallazgo de mislabeling en QR, ver §8.5) |

---

## 8. Auditoría de QR de Reseñas

### 8.1 Implementación confirmada — divergencia repo/deploy CERRADA

**ID histórico**: HAL-001 (auditoría 3e33830) — **ESTADO: CERRADO/RESUELTO en `7e1ef92`**

**HECHO COMPROBADO** mediante lectura completa de código + ejecución de tests:

El merge `origin/master → develop` incorporó al repositorio la implementación completa de la sección de QR de Reseñas del panel admin observada manualmente en producción (§3). Se verificó línea por línea:

1. `apps/web/src/lib/admin/types.ts` — tipos `AdminQRReviewsConfig` / `AdminQRReviewsConfigPatch` agregados (líneas ~675-707), reflejando exactamente el snapshot dict del backend.
2. `apps/web/src/components/admin/qr-reviews-card.tsx` — componente `QRResenasCard({businessId})` con dos formularios de guardado independientes (slug / datos de Google Business), banner de advertencia sobre reimpresión de QR al cambiar el slug, y badge "Sin ReviewConfig — se creará al guardar" cuando `!review_config_exists`.
3. `apps/web/src/app/admin/clientes/[clienteId]/cliente-detail-content.tsx` — renderiza `<QRResenasCard businessId={client.id} />` condicionado a `client.service_type === 'qr_reviews'`.
4. `services/api/src/apps/reviews/admin_views.py` — `AdminQRReviewsConfigView` (APIView) con `GET`/`PATCH`, `allowed_internal_roles = ['superadmin', 'operations']`.
5. `services/api/src/apps/reviews/admin_service.py` — `validate_slug()` y `update_admin_qr_reviews_config()` con transacción atómica.
6. `services/api/src/apps/reviews/tests/test_admin_qr_reviews.py` — 22 tests nuevos, **22/22 OK re-ejecutados en `7e1ef92`** (evidencia completa en §15).
7. Tests frontend `qr-reviews-card.test.tsx` (12 tests) + `url.test.ts` (4 tests) — **16/16 passed re-ejecutados en `7e1ef92`**.

**Conclusión**: no existe divergencia entre repositorio y despliegue para esta funcionalidad. El código de `7e1ef92` reproduce fielmente el comportamiento observado manualmente en producción.

### 8.2 Slug: fuente canónica y flujo

**HECHO COMPROBADO**:

- **Fuente canónica**: `Business.slug` (campo `SlugField(max_length=80)` en `business.models.Business`).
- **Normalización**: `django.utils.text.slugify()` sobre `Business.name`.
- **Unicidad**: Constraint único parcial a nivel DB: `UniqueConstraint(fields=['slug'], condition=Q(slug__isnull=False), name='uq_business_slug')`.
- **Auto-generación**: El método `Business.save()` genera el slug si está vacío, usando counter (`-1`, `-2`...) para evitar colisiones.
- **Longitud máxima**: 80 caracteres. El sufijo se ajusta para no superar ese límite.
- **Slug vacío**: No se acepta — el `save()` genera uno automáticamente.
- **Ruta pública**: `/r/{slug}/` → la plataforma usa `Business.slug` para resolver el tenant.

**El slug es compartido entre servicios**:
- `/r/{slug}/` — landing de QR de Reseñas
- `/m/{slug}/` — Carta Online (menú digital)

Ambas rutas usan `Business.slug`. **No existe un slug separado por servicio**. Cambiar el slug de un business **rompe ambas rutas públicas simultáneamente** y cualquier QR impreso que apunte al slug anterior dejará de resolver.

**INFERENCIA**: No existen aliases ni redirects por slug anterior en el código actual.

**Confirmado en `7e1ef92`**: el endpoint admin `AdminQRReviewsConfigView.patch()` permite editar el slug usando `admin_service.validate_slug()`, que reimplementa las mismas reglas (minúsculas, regex `^[a-z0-9-]+$`, máx. 80 caracteres, unicidad en DB) que `Business.save()`. El componente `QRResenasCard` muestra explícitamente un banner de advertencia sobre el riesgo de invalidar QR impresos al cambiar el slug — el hallazgo de la auditoría anterior ("cambiar el slug rompe ambas rutas") ya está comunicado al operador en la UI.

### 8.3 Google Business: campos y comportamiento

**HECHO COMPROBADO** — Archivo: `services/api/src/apps/reviews/models.py`

El modelo `ReviewConfig` tiene los siguientes campos:

| Campo | Tipo | Editable | Auto-calculado |
|---|---|---|---|
| `google_place_id` | CharField(255) | Sí | No |
| `google_place_name` | CharField(255) | Sí | No (informativo, no sincroniza con Google) |
| `google_place_formatted_address` | CharField(500) | Sí | No |
| `google_place_updated_at` | DateTimeField | No (read-only en serializer) | Timestamp de última actualización del admin |
| `google_review_url` | URLField | Sí | **No — independiente de `google_place_id`** |
| `custom_redirect_url` | URLField | Sí | No |

**No existe sincronización con la API de Google Places**. Todos los campos son persistidos manualmente. El "nombre del lugar" y la "dirección formateada" son inputs guardados, no reflejan estado real de Google.

### 8.4 Consumidores de `google_place_id`

| Modelo | Campo | Ruta que lo usa | Propósito |
|---|---|---|---|
| `reviews.ReviewConfig` | `google_place_id` | `/r/{slug}/` → redirect post-reseña positiva | Construye `https://search.google.com/local/writereview?placeid={id}` |
| `menu.MenuEngagementSettings` | `google_place_id` | `/m/{slug}/` → botón "Deja tu reseña" | Construye la misma URL |

Estos son **dos campos completamente independientes** sin sincronización. Un operador puede actualizar `ReviewConfig.google_place_id` sin tocar `MenuEngagementSettings.google_place_id` y viceversa.

**Confirmado en `7e1ef92`**: se leyó `services/api/src/apps/menu/models.py` — `MenuEngagementSettings` mantiene sus propios campos `google_place_id`/`google_review_url` con una propiedad `google_write_review_url` propia (misma lógica de prioridad: place_id > url), sin ninguna relación (`ForeignKey`, `signal`, propiedad derivada) hacia `reviews.ReviewConfig`. La duplicación reportada en la auditoría anterior sigue vigente sin cambios en este merge. **No se recomienda unificación automática** sin evidencia adicional de que ambos productos comparten intención de consumidor (ver §17, NR-02 se mantiene sin cambios).

### 8.5 Hallazgo nuevo: acción de auditoría mal etiquetada en escrituras del endpoint QR admin

**HECHO COMPROBADO** — Archivo: `services/api/src/apps/reviews/admin_views.py`

Tanto `AdminQRReviewsConfigView.get()` como `AdminQRReviewsConfigView.patch()` llaman a:

```python
log_platform_action(action='ADMIN_CLIENT_VIEWED', ...)
```

**Impacto**: las escrituras (cambio de slug, Place ID, URL personalizada, etc.) quedan registradas en `AccessAuditLog` con la misma acción `ADMIN_CLIENT_VIEWED` que las lecturas. No existe una acción distinta (p. ej. `ADMIN_QR_REVIEWS_CONFIG_UPDATED`) ni se registran valores anteriores/nuevos en el detalle del log, a diferencia de `_log_admin_cancel_audit()` en `cancellation_service.py` (billing), que sí usa una acción propia `ADMIN_SUBSCRIPTION_CANCELED` con `previous_status`/`new_status`/`reason` en el detalle (ver §11.7). Esta inconsistencia de trazabilidad es específica del endpoint QR admin, no sistémica en todo el panel.

**Cobertura de test**: `test_admin_qr_reviews.py` (22 tests) no incluye ninguna aserción sobre el contenido o la acción registrada en `AccessAuditLog` tras un PATCH exitoso — el hallazgo no está cubierto por test (ver hueco en §19).

---

## 9. Explicación de la inconsistencia de Place ID observada

**HECHO COMPROBADO** basado en el código:

```
ReviewConfig.google_place_id    = ChIJyXhfcgC_V5QRL3of_PcNk0E
ReviewConfig.google_review_url  = https://...?placeid=ChIJQZ9x31i-V5QRn-XwCutktZQ
```

**Causa exacta**: `google_review_url` y `google_place_id` son **campos independientes y editables por separado**. No existe ningún signal, validator, save hook ni lógica de recálculo que actualice `google_review_url` cuando cambia `google_place_id`.

**HECHO COMPROBADO**: `google_place_id` y `google_review_url` son campos independientes y pueden divergir.

**NO VERIFICADO**: no se conoce el orden histórico de las modificaciones ni qué actor o flujo generó la divergencia observada en el business 12 (§3). No hay ningún registro de auditoría, historial de campo (`django-simple-history` o equivalente) ni timestamp comparativo entre ambos campos que permita reconstruir la secuencia real de ediciones.

**Clasificación de la causa**: **Campo independiente editable, URL no recalculada** (mecanismo confirmado); **secuencia temporal de la divergencia específica del business 12: no verificada**.

**Impacto en runtime**: la inconsistencia no participa actualmente en la redirección mientras exista `custom_redirect_url` (prioridad 1) para el business 12. Sin embargo, permanece almacenada en `ReviewConfig.google_review_url` y **podría convertirse en fallback** si se eliminan los campos de mayor prioridad (`custom_redirect_url` y luego `google_place_id`), ya que `google_review_url` tiene prioridad 3 en `redirect_url` (ver §10). No se afirma que el impacto actual o futuro sea nulo de forma permanente — depende de qué campos conserve el operador.

---

## 10. Prioridad real de redirecciones

**HECHO COMPROBADO** — Código exacto en `reviews/models.py`, propiedad `redirect_url`:

```python
@property
def redirect_url(self) -> str | None:
    """Best redirect URL with priority: custom > place_id > google_review_url."""
    if self.custom_redirect_url:
        return self.custom_redirect_url
    place_id = (self.google_place_id or '').strip()
    if place_id:
        return f"https://search.google.com/local/writereview?placeid={place_id}"
    if self.google_review_url:
        return self.google_review_url
    return None
```

| Prioridad | Condición | URL generada |
|---|---|---|
| 1 | `custom_redirect_url` no vacío | El valor de `custom_redirect_url` tal cual |
| 2 | `google_place_id` no vacío | `https://search.google.com/local/writereview?placeid={google_place_id}` |
| 3 | `google_review_url` no vacío | El valor de `google_review_url` tal cual |
| 4 | Ninguno tiene valor | `None` (el frontend no redirige) |

**En modo `DIRECT`** (backend, `views.py` línea ~166):
```python
if config.effective_mode == ReviewMode.DIRECT and config.redirect_url:
    target_url = config.redirect_url
```

**En modo `SMART_FILTER`** (filtro inteligente): solo se usa `redirect_url` cuando la calificación es ≥ `redirect_threshold`. Si la calificación es baja, se registra la reseña internamente.

La propiedad `effective_mode` degrada a `DIRECT` si el plan no tiene entitlement para `smart_filter`, sin necesidad de migración de datos.

Para el backend de Carta Online (`menu/views.py`), la lógica equivalente usa `MenuEngagementSettings.google_write_review_url` (que también prioriza `google_place_id` sobre `google_review_url`).

---

## 11. Auditoría de suscripciones en el panel admin

### 11.1 Fuente canónica

**HECHO COMPROBADO**: `billing.SubscriptionV2` es la fuente canónica en todos los endpoints del panel admin:

- `GET /platform-admin/subscriptions/` → `AdminSubscriptionListView` → `SubscriptionV2.objects.all()`
- `GET /platform-admin/subscriptions/{id}/` → `AdminSubscriptionDetailView` → `SubscriptionV2.objects.get(pk=...)`
- `GET /platform-admin/clients/{id}/` → suscripción embebida desde `SubscriptionV2`

**El panel admin NO lee** `billing.Subscription` (legacy OneToOne).

### 11.2 Estado de `billing.Subscription` (legacy)

**HECHO COMPROBADO**: El modelo legacy `billing.Subscription` sigue existiendo y se escribe en cada activación de `qr_reviews` vía `service_activation._qr_reviews_legacy_subscription()`. No se lee en el panel admin pero puede estar siendo leída en endpoints de usuario (e.g., entitlements, runtime access) en flujos que no pasaron por `SubscriptionV2`.

### 11.3 Navegación entre vistas

Desde `/admin/suscripciones/{id}` hay enlace a `/admin/clientes/{business_id}` y viceversa. Ambas vistas presentan el mismo estado ya que leen de `SubscriptionV2`.

**INFERENCIA**: Si se cancela una suscripción desde `/admin/suscripciones/{id}` y luego se navega a `/admin/clientes/{id}`, el estado puede aparecer desactualizado hasta que el usuario navegue (RSC re-fetch). El componente usa `router.refresh()` post-cancelación en la vista de suscripción, pero la vista de cliente no tiene invalidación reactiva.

### 11.4 Estados diferenciados

El panel admin diferencia correctamente:

| Estado interno | Label admin |
|---|---|
| `active` | Activo |
| `trialing` | En prueba |
| `past_due` | Pago vencido |
| `suspended` | Suspendido |
| `canceled` | Cancelado |
| `checkout_pending` | Checkout pendiente |
| `cancel_at_period_end=True` | Cancelación programada |

### 11.5 Pagos demorados / rechazados

**HECHO COMPROBADO**: `PaymentAttempt` es la fuente de datos de intentos de cobro. Aparecen en:
- `/admin/suscripciones/{id}` → sección "Pagos"
- `/admin/clientes/{id}` → sección "Pagos recientes" (últimos 10)

Risk badges calculados dinámicamente en cada request: `pago_atrasado`, `cancelacion_programada`, `suspendido`, `reintentos_cobro` (retry_count ≥ 2).

### 11.6 Trazabilidad hasta el evento

**HECHO COMPROBADO**: `/admin/suscripciones/{id}` expone:
- `payments` → `PaymentAttempt` (últimos 20)
- `events` → `BillingEvent` (últimos 20)
- `invoice_events` → `BillingInvoiceEvent` (últimos 10)
- `webhook_errors` → `WebhookDelivery` con `processing_status in ['failed', 'dead_letter']`

La cadena de evidencia es completa para investigación de soporte.

### 11.7 Cancelación administrativa (PR-2)

**HECHO COMPROBADO** — 49/49 tests pasando (re-ejecutado en `7e1ef92`, `EXITCODE=0`).

Flujo en `cancel_subscription_immediately()` (cancellation_service.py):

1. Fast-path idempotente: si ya está `CANCELED`, retorna sin llamar a MP.
2. Pre-flight: valida que el estado esté en `ADMIN_CANCELLABLE_STATUSES` = {`active`, `trialing`, `past_due`, `suspended`}.
3. `SELECT FOR UPDATE` en TX atómica: re-valida, lee `provider_sub_id` de la DB.
4. Si MP: `cancel_preapproval(preapproval_id)` — FUERA de la transacción para no sostener lock.
5. Segunda TX: escribe estado `CANCELED`, `is_active=False`, `canceled_at`, `cancel_reason`, `canceled_by`.
6. `_revert_business_for_admin_cancel()`: setea `Business.status = 'onboarding'` si no hay otras suscripciones activas.
7. `_log_admin_cancel_audit()`: escribe `AccessAuditLog` dentro de la misma TX.

**Manejo de errores**:

| Error | Respuesta HTTP | Estado local |
|---|---|---|
| Suscripción no encontrada | 404 | Sin cambios |
| Reason vacío | 400 | Sin cambios |
| Estado no cancellable | 400/409 | Sin cambios |
| `ProviderSubscriptionNotFound` | 502 | Sin cambios |
| `MercadoPagoAuthError` | 502 | Sin cambios |
| `MercadoPagoCancelError` (timeout) | 504 | Sin cambios |
| `MercadoPagoCancelError` (otro) | 502 | Sin cambios |

**Garantías verificadas**:
- `provider_sub_id` siempre de la DB, nunca del request body.
- Sin reembolsos.
- Pagos históricos preservados.
- Webhook posterior de cancelación en MP → no-op (test_17 pasa).
- Authorized payment tardío no reactiva una suscripción cancelada (test_18 pasa).
- La suscripción cancelada con `cancel_at_period_end=True` previa: también idempotente.

**Auditoría registrada** — **CORREGIDO respecto a la auditoría anterior** (código exacto de `_log_admin_cancel_audit()` en `cancellation_service.py`, líneas ~493-525):
```python
log_platform_action(
    action='ADMIN_SUBSCRIPTION_CANCELED',
    actor=canceled_by,
    entity_type='subscription_v2',
    entity_id=str(subscription.id),
    business=subscription.business,
    details={
        'subscription_id': str(subscription.id),
        'business_id': subscription.business_id,
        'plan_code': subscription.plan_code,
        'service_type': subscription.service_type,
        'previous_status': previous_status,
        'new_status': SubscriptionV2.Status.CANCELED,
        'provider_status': provider_status,
        'reason': reason,
        'preapproval_id_masked': ...,
    },
)
```

**HECHO COMPROBADO**: a diferencia de lo concluido en la auditoría anterior (3e33830), `previous_status` **sí se registra explícitamente** en el campo `details` de `AccessAuditLog`, junto con `new_status`, `provider_status`, `plan_code`, `service_type` y `reason`. No requiere inferencia del historial. El riesgo R-10 de la auditoría anterior ("`previous_status` no en AccessAuditLog") **queda cerrado** — ver §18.

### 11.8 Escenario: Mercado Pago cancela correctamente → falla la segunda transacción/escritura local

**HECHO COMPROBADO** — Análisis de `cancel_subscription_immediately()` (`cancellation_service.py`, líneas 259-420) y de `AdminSubscriptionCancelView.post()` (`platform_admin_subscriptions_views.py`):

El flujo tiene una ventana real entre el paso 3 (llamada a MP, **fuera** de cualquier transacción) y el paso 4 (segunda transacción atómica que escribe `SubscriptionV2.status = CANCELED`, revierte `Business.status` y escribe el audit log):

1. **`SubscriptionV2` puede permanecer activa localmente**: si la segunda transacción (paso 4) lanza una excepción después de que `svc.cancel_preapproval()` ya tuvo éxito, Django revierte (`rollback`) **todo** el bloque `transaction.atomic()` — incluyendo la escritura de `status/is_active/canceled_at` que ya se había asignado en memoria. El resultado es `SubscriptionV2.status` sin cambios (por ejemplo, sigue `ACTIVE`) mientras en Mercado Pago el `preapproval` ya está `canceled`.
2. **`Business.status` y entitlements pueden permanecer activos**: `_revert_business_for_admin_cancel()` se invoca dentro del mismo bloque atómico que la escritura de `SubscriptionV2`; si ese bloque falla y revierte, `Business.status` **también** queda sin cambios (activo). Como los entitlements se derivan de `Business.status`/`plan_code` en cada request (no hay caché ni bandera separada), el negocio conserva acceso completo al servicio.
3. **La vista no captura este caso específicamente**: `AdminSubscriptionCancelView.post()` solo captura `CancellationError`, `ProviderSubscriptionNotFound`, `MercadoPagoAuthError` y `MercadoPagoCancelError`. Una excepción distinta durante la escritura local (p. ej. un error de base de datos) **no está contemplada** en ese `except` — se propaga sin manejar y DRF la traduce en una respuesta 500 sin mensaje específico sobre la desalineación MP/local.
4. **Un webhook posterior NO corrige necesariamente el estado completo**: `_handle_subscription_preapproval()` (`webhook_processor.py`, línea 207) sí sincroniza `SubscriptionV2.status = CANCELED` cuando MP reporta `canceled` (línea ~281), pero **no toca `Business.status` en absoluto** — se confirmó por lectura completa de la función que no existe ninguna llamada a `_revert_business_for_admin_cancel()` ni actualización equivalente de `Business` en ese handler. Es decir, incluso si el webhook llega y se procesa correctamente, el negocio podría seguir con `Business.status` desalineado (activo) mientras `SubscriptionV2` ya figura como cancelada. Además, esta corrección depende de que MP efectivamente envíe el webhook, lo cual **no puede darse por sentado** mientras `notification_url` continúe sin verificar (§13.5b).
5. **No existe reconciliación, retry ni alerta para este escenario específico**: no hay ningún comando de management, tarea periódica ni chequeo de consistencia que compare el estado de `SubscriptionV2`/`Business` contra el estado real en MP fuera del flujo de webhooks. No hay alerta (email, notificación interna) que se dispare cuando la escritura local posterior a un cancel exitoso en MP falla.
6. **Los 49 tests de `test_pr2_admin_cancel_subscription.py` NO cubren este escenario de forma efectiva**: existe una clase `AdminCancelPartialFailureTest` con un test llamado `test_retry_after_mp_cancel_but_local_fail_repairs_state`, cuyo docstring de clase describe exactamente este escenario ("Local DB write fails (simulated by mocking step 4 to raise on first call)"). Se leyó el cuerpo del test (líneas 699-717): **no simula ninguna falla de escritura local** — solo invoca `cancel_subscription_immediately()` una vez con un mock de MP exitoso y verifica que la suscripción quede cancelada. No hay mock que fuerce una excepción en el paso 4, no hay una segunda invocación que verifique "reparación", y no se verifica en ningún momento el estado intermedio (MP cancelado / local aún activo). **El test está mal etiquetado: su nombre y docstring prometen cobertura de este escenario, pero el código no lo ejercita.**

**Conclusión**: no existe recuperación demostrada para el escenario "Mercado Pago cancela correctamente → falla la escritura local". Se registra como **riesgo ALTO** (R-16, ver §18) — no se asume que un webhook posterior siempre llegará ni que, si llega, corrige completamente el estado (`Business.status` queda fuera de su alcance). No se propone corrección de código en esta auditoría.

---

## 12. Flujo completo de Mercado Pago

```
Usuario inicia checkout
  └── POST /api/v1/billing/checkout-sessions/         [CheckoutSessionCreateView]
        └── MpCheckoutSession.status = 'created'
              └── MercadoPagoService.create_preapproval_plan()
                    └── MpCheckoutSession.status = 'checkout_created'
                          └── redirect al init_point de MP

Usuario completa en MP
  └── back_url → /app/onboarding/checkout/?session_id={id}
        └── POST /api/v1/billing/checkout-sessions/{id}/reconcile/  [CheckoutSessionReconcileView]
              └── reconcile_session(session_id)
                    └── MercadoPagoService.search_preapprovals(plan_id)
                          └── external_reference guard (evita activación cross-tenant)
                                └── _upsert_subscription_v2()
                                      └── activate_subscription_from_invoice() si hay pagos

MP envía webhook
  └── POST /billing/mercadopago/webhook                [MercadoPagoWebhookView]
        ├── WebhookDelivery persisted ANTES de procesar
        ├── Verificación HMAC-SHA256 (MP_WEBHOOK_SECRET)
        ├── Deduplicación (x_request_id + payload_hash)
        └── dispatch_webhook(delivery)
              ├── topic=subscription_preapproval
              │     └── _handle_subscription_preapproval(preapproval_id)
              │           ├── MP.get_preapproval(preapproval_id) — server-to-server
              │           ├── MpCheckoutSession find by provider_preapproval_plan_id
              │           ├── _upsert_subscription_v2()
              │           └── session.transition_to(LINKED)
              │
              ├── topic=subscription_authorized_payment
              │     └── _handle_authorized_payment(authorized_payment_id)
              │           ├── MP.get_authorized_payment(ap_id) — server-to-server
              │           ├── BillingInvoiceEvent upsert
              │           ├── SubscriptionV2 find by provider_sub_id = preapproval_id
              │           └── activate_subscription_from_invoice()
              │                 ├── SELECT FOR UPDATE → re-valida
              │                 ├── SubscriptionV2.status = ACTIVE, is_active = True
              │                 ├── Business.status = 'active'
              │                 ├── _run_service_activation_hook()
              │                 │     └── ensure_service_activation() → legacy sync
              │                 └── session.transition_to(ACTIVATED)
              │
              ├── topic=payment
              │     └── process_payment_event() — flujo legacy
              │
              └── otros topics → IGNORED, 200 OK
```

---

## 13. Auditoría de webhooks

### 13.1 Endpoint

```
POST /billing/mercadopago/webhook
permission_classes = [AllowAny]
```

Ubicación: `services/api/src/apps/billing/urls.py` línea 36 (implícita) → `views.py` línea 702.

**HECHO COMPROBADO**: URL registrada en `billing/urls.py` como `MercadoPagoWebhookView`.

### 13.2 Seguridad del webhook

**Verificación de firma HMAC-SHA256**:

```python
def _verify_mp_signature(request, x_request_id, x_signature) -> bool:
    secret = getattr(settings, 'MP_WEBHOOK_SECRET', None)
    if not secret:
        if settings.DEBUG:
            return True   # DEV bypass — warning loggeado
        # Non-DEBUG sin secret → rechaza TODOS los webhooks
        return False
    # Verifica x-signature header: ts=...,v1=...
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts}"
    expected = HMAC-SHA256(manifest, secret)
    return hmac.compare_digest(expected, v1)
```

**Configuración**: `MP_WEBHOOK_SECRET = os.getenv('MP_WEBHOOK_SECRET')` en `settings.py`.

**Hallazgo MEDIO — re-confirmado en `7e1ef92`**: Si `MP_WEBHOOK_SECRET` no está seteado en producción (non-DEBUG), todos los webhooks son rechazados con `Invalid signature` (400) — comportamiento **fail-closed**, verificado en `_verify_mp_signature()` (`webhook_processor.py` líneas ~606-622): si `DEBUG=True` y no hay secret, bypass con `WARNING` en logs; si `DEBUG=False` y no hay secret, `ERROR` en logs y `sig_valid=False` para toda solicitud. Si el secret está seteado, la firma HMAC es obligatoria en ambos modos. **Esto es una buena práctica de seguridad** (falla cerrado, no abierto, ante misconfiguración en producción).

**Firma inválida**: Se responde 400, no 200. El delivery queda en `IGNORED`. MP reintentará el webhook.

**Re-ejecutado en `7e1ef92`**: `apps.billing.tests.test_webhook_signature` — **9/9 OK** (`EXITCODE=0`), cubre: DEV bypass sin secret, rechazo de firma inválida, header `x-signature` mal formado o ausente, manifest tampering.

### 13.3 Tópicos soportados

| Topic | Handler | Lógica |
|---|---|---|
| `subscription_preapproval` | `_handle_subscription_preapproval()` | Upsert SubscriptionV2, transición a LINKED |
| `subscription_authorized_payment` | `_handle_authorized_payment()` | Activación condicional al primer pago |
| `payment` | `process_payment_event()` (legacy) | Cambios de plan, addons, tips |
| Otros | `IGNORED` | Responde 200, log INFO, sin trazabilidad de contenido |

### 13.4 Idempotencia y orden

**HECHO COMPROBADO**:

- **Deduplicación primaria**: `x_request_id` — clave única por entrega de MP.
- **Deduplicación secundaria**: `topic + resource_id + payload_hash` cuando no hay `x_request_id`.
- **Respuesta ante duplicado**: 200 OK inmediato, sin re-procesamiento.
- **Eventos fuera de orden**: La activación en `_handle_authorized_payment` verifica `subscription.can_activate()` — no activa si ya está `CANCELED`.
- **Eventos viejos post-cancelación**: `subscription.can_activate()` retorna `False` para `CANCELED` → `TERMINAL_STATUSES`. No hay reactivación.
- **Lock en activación**: `SELECT FOR UPDATE` previene doble activación concurrente.
- **Doble cancelación**: Idempotente — si ya está `CANCELED`, `_handle_subscription_preapproval` sincroniza pero no falla.

### 13.5 Sincronización local que hace el webhook

| Campo actualizado | Por qué evento |
|---|---|
| `SubscriptionV2.status = ACTIVE` | `subscription_authorized_payment` (primer pago) |
| `SubscriptionV2.is_active = True` | Ídem |
| `SubscriptionV2.current_period_start` | Ídem (`paid_at`) |
| `SubscriptionV2.status = CANCELED` | `subscription_preapproval` con `status=canceled` en MP |
| `SubscriptionV2.canceled_at` | Ídem |
| `Business.status = 'active'` | `_activate_tenant()` en activación |
| `Business.status = 'past_due'` | `record_failed_payment()` en pago rechazado |
| `MpCheckoutSession.status = LINKED` | `subscription_preapproval` |
| `MpCheckoutSession.status = ACTIVATED` | `subscription_authorized_payment` (primer pago) |
| `BillingInvoiceEvent` (upsert) | `subscription_authorized_payment` |

**NO actualiza automáticamente**:
- `business.Subscription` (legacy) — solo se sincroniza en `service_activation`, no en el webhook processor.
- `MenuEngagementSettings`
- Entitlements en tiempo real (se derivan de `Business.status` y `plan_code` en cada request).

### 13.5b `notification_url` en la creación de suscripciones — hallazgo re-verificado en `7e1ef92`

**HECHO COMPROBADO DEL REPOSITORIO** — Archivo: `services/api/src/apps/billing/mp_service.py` (líneas 100-230 y 500-560, releídas de forma independiente en esta actualización):

- `create_preference()` (pagos únicos/legacy) **sí** envía `notification_url` a MP, condicionado a que `settings.BASE_PUBLIC_URL` esté configurado.
- `create_preapproval_plan()` y `create_preapproval()` (flujo de suscripciones, el que usa el panel admin y el checkout actual) **NO incluyen `notification_url`** en el payload enviado a MP. Confirmado leyendo el payload completo de ambos métodos: ninguno construye ni asigna esa clave.

**Clasificación**: **NO VERIFICADO — CONTRATO EXTERNO NO RESUELTO**.

No se afirma ni se descarta que la entrega dependa "enteramente de la configuración del panel de Mercado Pago". La documentación pública de MP es contradictoria/insuficiente para resolver esto desde el repositorio:

- La documentación de webhooks de Checkout Pro ([mercadopago.com.ar/developers/es/docs/checkout-pro/additional-content/notifications/webhooks](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/additional-content/notifications/webhooks)) indica que la configuración vía "Tus integraciones" **no está disponible para Suscripciones** y remite a configurar la notificación durante la creación del recurso.
- Sin embargo, la referencia actual de `POST /preapproval` ([mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/create-preapproval/post](https://www.mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/create-preapproval/post)) **no expone claramente** un campo `notification_url` en el contrato documentado.

**Conclusión de esta actualización**: no se puede determinar, solo con lectura de código y de la documentación pública disponible, si (a) MP soporta `notification_url` en `preapproval`/`preapproval_plan` y el código simplemente no lo usa, o (b) existe un mecanismo distinto no identificado para asociar la URL receptora a los tópicos de Suscripciones. **No se asume como alternativa que "la entrega dependa exclusivamente de configuración de cuenta/aplicación"** — la documentación oficial de Webhooks ([mercadopago.com.ar/developers/es/docs/subscriptions/additional-content/your-integrations/notifications/webhooks](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/additional-content/your-integrations/notifications/webhooks)) declara explícitamente que la configuración mediante "Tus integraciones" **no está disponible para Suscripciones**, por lo que ese mecanismo no puede darse por sentado como fallback. **Debe comprobarse mediante documentación específica vigente, soporte de Mercado Pago o una prueba sandbox controlada antes de implementar una propiedad posiblemente no soportada.** No se propone todavía ninguna corrección de código (ver Slice 1 renumerado en §20 y checklist en §21).

### 13.6 Fallos y respuestas

| Situación | Respuesta | Estado local |
|---|---|---|
| Fallo de DB al crear `WebhookDelivery` | Exception sin capturar | Webhook delivery perdido |
| Signature inválida | 400 | Delivery en IGNORED |
| Duplicate | 200 | Delivery en DUPLICATED |
| Error al procesar (topic handler lanza exception, incluyendo fallos de consulta a MP) | **200 (siempre)** — corregido respecto a la auditoría anterior | Delivery en FAILED |

**Corrección respecto a la auditoría anterior**: la fila "Fallo de consulta posterior a MP → Exception en handler → Delivery en FAILED; MP reintenta" de la versión `3e33830` era **inexacta**. Se releyó `dispatch_webhook()` completo (`webhook_processor.py`, línea 164 en adelante): la función envuelve **todo** el procesamiento del topic handler en un bloque `try/except` que nunca re-lanza (`raise`) — cualquier excepción interna (incluyendo fallos de consulta server-to-server a MP) se captura, se marca `WebhookDelivery.processing_status = FAILED`, y el método retorna normalmente. La vista (`MercadoPagoWebhookView.post()`) responde **200** en todos los casos donde `dispatch_webhook()` fue invocado, sin importar el resultado interno. **MP NO reintenta** en este caso porque MP solo reintenta ante respuestas no-2xx.

**HECHO COMPROBADO**: `dispatch_webhook()` siempre responde 200 al caller. Los errores internos quedan en `WebhookDelivery.processing_status = FAILED`. Dado que MP considera exitosa cualquier respuesta 2xx, **no reintentará** una entrega cuyo procesamiento interno falló — el error queda silenciosamente en `FAILED` sin que MP lo sepa.

**ALTO riesgo — CONFIRMADO, sin mecanismo de recuperación**: se realizó un grep de todo el repositorio buscando el estado `DEAD_LETTER` (definido en `WebhookDelivery.ProcessingStatus`) y **no se encontró ningún lugar del código que lo asigne** — ni tarea de Celery, ni comando de management, ni endpoint de replay/retry para entregas en estado `FAILED`. Una vez que un webhook queda en `FAILED` (por ejemplo, por un timeout transitorio al consultar MP), **no existe ningún mecanismo automático ni manual en el código para reprocesarlo**. La única visibilidad es el listado `webhook_errors` en `/admin/suscripciones/{id}` (solo lectura, sin acción de reintento).

**Riesgo adicional, en dos escenarios distintos según el orden real del código** (`WebhookDelivery.objects.create()` ocurre **antes** del dispatch al handler de tópico, confirmado en `dispatch_webhook()`/la vista, ver §12):

- **Falla al crear el delivery, antes de cualquier procesamiento**: si `WebhookDelivery.objects.create()` falla (ej: DB down), la excepción no está capturada en la vista y el webhook retornará **500**. En ese punto el handler de tópico **todavía no pudo ejecutarse** — no hay evento parcialmente procesado. MP reintentará por la respuesta no-2xx; al recuperarse la DB, el reintento se procesará normalmente como una entrega nueva.
- **Falla del handler después de que el delivery ya fue creado**: es el caso ya documentado arriba — el `try/except` de `dispatch_webhook()` captura la excepción, marca `WebhookDelivery.processing_status = FAILED`, y la vista responde **200**. MP **no reintenta** en este caso (ver R-02).
- No se documenta ningún escenario adicional (por ejemplo, duplicados originados en una creación fallida) porque no se verificó en el código un camino donde una falla de creación previa al dispatch pueda coexistir con un evento ya procesado.

### 13.7 Reconcile URL — CORREGIDO

**HECHO COMPROBADO**:

Frontend (`features/billing/api.ts`):
```typescript
const url = `${apiUrl}/api/v1/billing/checkout-sessions/${encodeURIComponent(sessionId)}/reconcile/`;
```

Backend (`billing/urls.py`):
```python
path('checkout-sessions/<uuid:session_id>/reconcile/', CheckoutSessionReconcileView.as_view(), ...)
```

El bug reportado `?preapproval_id={id}/reconcile/` **NO existe en el código actual**. La URL se construye correctamente con `/reconcile/` como segmento de ruta. Tests específicos lo verifican:

- `src/features/billing/__tests__/reconcile-checkout.test.ts` — 12 tests, todos pasan.
- Test explícito: `'calls POST with /reconcile/ as a PATH segment — no query string'`.
- Backend: `apps.billing.tests.test_reconcile_session` — **re-ejecutado en `7e1ef92`: 18/18 OK** (`EXITCODE=0`). Cubre reconciliación idempotente, `external_reference` guard (evita activación cross-tenant), transiciones de estado y activación correcta.

---

## 14. Matriz de permisos

### 14.1 Roles internos y secciones autorizadas

**HECHO COMPROBADO** — `platform_permissions.py`:

| Rol | Secciones autorizadas |
|---|---|
| `superadmin` | dashboard, clientes, suscripciones, soporte, blog, reportes, configuracion, promociones, notificaciones |
| `operations` | dashboard, clientes, suscripciones, reportes, notificaciones |
| `support_agent` | dashboard, soporte, notificaciones |
| `content_admin` | dashboard, blog |

### 14.2 Acceso por acción sensible

| Acción | Roles permitidos | Validación backend | Auditoría |
|---|---|---|---|
| Ver clientes | superadmin, operations | `HasInternalRole` en view | `log_platform_action('ADMIN_CLIENT_VIEWED')` |
| Editar datos cliente | N/A (no existe endpoint de edición) | — | — |
| Ver config. QR Reseñas (slug, Google Place) | superadmin, operations | `AdminQRReviewsConfigView.get()` + `allowed_internal_roles` | `log_platform_action('ADMIN_CLIENT_VIEWED')` |
| Modificar slug (QR Reseñas) | superadmin, operations | `AdminQRReviewsConfigView.patch()` + `validate_slug()` | `log_platform_action('ADMIN_CLIENT_VIEWED')` — **mal etiquetado, ver §8.5** |
| Modificar Google Place ID / review URL / redirect (QR Reseñas) | superadmin, operations | `AdminQRReviewsConfigView.patch()` (rechaza campos desconocidos, 400) | `log_platform_action('ADMIN_CLIENT_VIEWED')` — **mal etiquetado, ver §8.5** |
| Modificar branding | N/A (no hay endpoint admin) | — | — |
| Cambiar productos/entitlements | N/A (no hay endpoint admin) | — | — |
| Ver suscripciones | superadmin, operations | `HasInternalRole` en view | `log_platform_action('ADMIN_SUBSCRIPTION_VIEWED')` |
| Cancelar suscripciones | superadmin, operations | `HasInternalRole` + validación de estado | `log_platform_action('ADMIN_SUBSCRIPTION_CANCELED')` (con `previous_status`/`new_status` en `details`, ver §11.7) |
| Consultar pagos | superadmin, operations | `HasInternalRole` en view | Ídem subscription viewed |
| Acceder a auditoría | superadmin, operations | `HasInternalRole` en view | Via AccessAuditLog en response |
| Ver/crear tickets | superadmin, support_agent | `HasInternalRole` en view | Propia del modelo ticket |
| Crear notas internas | superadmin, operations, support_agent | `IsAuthenticated, IsPlatformStaff` | Timestamp en AdminInternalNote |

### 14.3 Implementación del guard de rol

```python
class HasInternalRole(BasePermission):
    def has_permission(self, request, view) -> bool:
        allowed = getattr(view, 'allowed_internal_roles', None)
        if not allowed:
            return True  # Sin restricción de rol
        profile = getattr(request.user, 'account_profile', None)
        if profile is None:
            return False
        return profile.internal_role in allowed
```

**HECHO COMPROBADO**: La validación de rol es **server-side**, independiente del frontend. El frontend solo muestra las secciones autorizadas (`authorized_sections` en `AdminSession`) pero el backend siempre valida.

**NOTA**: El campo `is_platform_staff` en `AccountProfile` es el gate primario. Un usuario autenticado sin `is_platform_staff=True` recibe 403 antes de llegar a la validación de rol.

---

## 15. Matriz de tests y resultados

> **Convención de esta sección**: cada resultado está marcado como **RE-EJECUTADO EN `7e1ef92`** (con `EXITCODE` explícito, evidencia de esta actualización) o **HISTÓRICO — NO RE-VERIFICADO EN 7e1ef92** (resultado heredado de la auditoría sobre `3e33830`, no vuelto a ejecutar en esta sesión y por lo tanto no debe asumirse vigente sin re-ejecución).

### 15.1 Tests backend — RE-EJECUTADOS EN `7e1ef92`

#### `apps.reviews.tests.test_admin_qr_reviews` — **NUEVO, incorporado por el merge**
```
Ran 22 tests in 4.850s → OK   (EXITCODE=0, verificado explícitamente tras descartar un falso positivo de PowerShell)
```

| Clase de test | Qué valida |
|---|---|
| `AdminQRReviewsGetTests` (4) | GET: admin puede leer config; 403 para no-admin; 400 para business sin `service_type='qr_reviews'`; 404 para business inexistente |
| `AdminQRReviewsSlugPatchTests` (6) | PATCH slug: cambio válido, slug duplicado rechazado, apóstrofes/espacios/mayúsculas/caracteres especiales rechazados |
| `AdminQRReviewsPlaceIdPatchTests` (5) | PATCH Google Place: guardar place_id, guardar todos los campos de lugar, `google_place_updated_at` estampado, ReviewConfig creado si no existía |
| `AdminQRReviewsPermissionAndFieldTests` (7) | Roles: `content_admin`/`support_agent` rechazados (403), `operations` permitido; PATCH vacío → 400; campos desconocidos/mixtos → 400 |

**Huecos de cobertura identificados en esta suite** (ver también §19): sin test de la acción registrada en `AccessAuditLog` tras un PATCH (ver §8.5). **Corrección respecto a formulaciones anteriores**: `superadmin` y `operations` son roles internos globales (no están vinculados a un `business_id` específico), por lo que no corresponde exigirles 404/403 al consultar *otro* negocio — pueden legítimamente consultar cualquier `business_id` válido. La cobertura correcta a verificar es: (a) roles no autorizados (`content_admin`, `support_agent`) reciben 403 — **cubierto**, `AdminQRReviewsPermissionAndFieldTests`; (b) el `business_id` seleccionado en el PATCH es el único negocio modificado — **no cubierto explícitamente**; (c) no se alteran configuraciones de otros negocios — **no cubierto explícitamente**; (d) IDs inexistentes reciben 404 — **cubierto**, `AdminQRReviewsGetTests`; (e) no hay mezcla de datos entre respuestas de distintos `business_id` — **no cubierto explícitamente**.

#### Tests frontend `qr-reviews-card.test.tsx` + `url.test.ts` — **NUEVO, incorporado por el merge**
```
16/16 passed (vitest)
```
- `qr-reviews-card.test.tsx`: 12 tests — render con/sin ReviewConfig, guardado independiente de slug y Google Business, validaciones de error, banner de advertencia de reimpresión de QR.
- `url.test.ts`: 4 tests — `toAbsoluteUrl()`, confirmado que solo se usa en la página de blog (grep de todo el repo), no en `qr-reviews-card.tsx`.

#### `apps.billing.tests.test_pr2_admin_cancel_subscription`
```
Ran 49 tests in 6.546s → OK   (EXITCODE=0)
```

| Test | Qué valida |
|---|---|
| `test_01_cancels_active_subscription` | Flujo completo: estado ACTIVE → CANCELED, MP llamado |
| `test_02_uses_stored_preapproval_id` | `provider_sub_id` siempre desde DB |
| `test_03_sends_cancelled_status_to_mp` | PUT con `{"status": "canceled"}` |
| `test_04_no_refund_call` | No se llama a ningún endpoint de reembolso |
| `test_05_subscription_inactive_after_cancel` | `is_active=False` post-cancel |
| `test_06_business_status_reverts_to_onboarding` | Business → onboarding |
| `test_07_business_loses_active_status` | Business ya no `active` |
| `test_08_audit_log_created` | AccessAuditLog escrito (con `previous_status`/`new_status`, confirmado en §11.7) |
| `test_09_non_staff_gets_403` | Usuarios sin `is_platform_staff` → 403 |
| `test_10_tenant_owner_gets_403` | Owner del negocio → 403 |
| `test_11_cannot_access_other_business_subscription` | 404 para IDs inexistentes |
| `test_17_webhook_cancel_after_admin_cancel_is_noop` | Webhook tardío no modifica |
| `test_18_old_authorized_payment_does_not_reactivate` | Pago tardío no activa cancelada |
| [+36 más] | Combinaciones de estados, errores MP, retry, scheduled_cancel, etc. |

#### `apps.billing.tests.test_reconcile_session`
```
Ran 18 tests → OK   (EXITCODE=0)
```

Valida reconciliación idempotente, `external_reference` guard (evita cross-tenant), transiciones de estado, activación correcta.

#### `apps.billing.tests.test_webhook_signature` — **re-auditado de forma independiente en esta actualización**
```
Ran 9 tests in 0.020s → OK   (EXITCODE=0)
```

Valida: DEV bypass sin `MP_WEBHOOK_SECRET` (con `DEBUG=True`), rechazo fail-closed sin secret en modo no-DEBUG, header `x-signature` ausente/mal formado, manifest tampering (firma no coincide), verificación HMAC-SHA256 correcta.

#### `apps.accounts.tests.test_admin_auth + test_admin_dashboard_and_client_tickets` — **re-confirmado en `7e1ef92`, mismo resultado que en `3e33830`**
```
Ran 60 tests in 11.904s → FAILED (failures=3)   (EXITCODE=1)
```

| Test | Resultado | Aserción fallida |
|---|---|---|
| `test_enrollment_flow` | FALLO | `assertEqual(resp1.status_code, 200)` → recibido 403 |
| `test_double_enrollment_rejected` | FALLO | `assertEqual(resp.status_code, 400)` → recibido 403 |
| `test_admin_me_after_login` | FALLO | `assertEqual(resp.status_code, 200)` → recibido 403 |
| Resto (57) | OK | — |

**Re-confirmado, no es un artefacto de la auditoría anterior**: se re-ejecutó explícitamente esta suite sobre `7e1ef92`, en el contenedor `mirubro-api` ya en ejecución (no se reconstruyó la imagen en esta sesión — ver §22), y los **mismos 3 tests fallan con el mismo síntoma exacto** (403 en vez de 200/400) que en `3e33830`. Esto confirma que el problema es preexistente y **no fue introducido ni corregido por el merge** de `origin/master`. Análisis sin cambios: los tests de MFA enrollment esperan que un usuario autenticado (sin MFA aún) pueda acceder a `/api/v1/platform-admin/auth/mfa-enroll/`; la respuesta 403 sugiere que el endpoint exige MFA completo antes de acceder, lo cual crea una dependencia circular en el flujo de enrolamiento.

#### `apps.billing.tests.test_checkout_flow_v2` — **hallazgo nuevo, no relacionado al merge de QR Reseñas — re-ejecutado en esta actualización**
```
Ran 24 tests in 2.895s → FAILED (errors=20)   (EXITCODE=1)
```

**Corrección respecto a una versión anterior de este documento**: el conteo real, obtenido al inspeccionar la salida redirigida a archivo temporal de `docker exec mirubro-api python manage.py test apps.billing.tests.test_checkout_flow_v2 --verbosity=2` (wrapper real en §22), es **24 tests totales**, no 33. De esos 24, **20 terminan en error** (0 en `FAIL`, 0 pasan como fallo de aserción) y **4 pasan**. De los 20 errores, exactamente **18 son `django.core.exceptions.FieldError: Invalid field name(s) for model Plan: 'billing_cycle'`** (el campo no existe en el modelo `Plan` actual) y **2 son `AttributeError: 'WSGIRequest' object has no attribute 'data'`** (el test usa `request.data` sobre un `WSGIRequest` crudo en vez de un `Request` de DRF). 18 + 2 = 20, consistente con `errors=20` del resumen de `unittest`. **Esto es deuda técnica preexistente y desalineación de esquema, fuera del alcance del merge de QR Reseñas/webhooks que motiva esta auditoría** — no debe conflacionarse con las conclusiones de la sección 13 (webhooks), que se basan en `test_webhook_signature` (aislado, 9/9 OK) y en lectura directa de código. Se documenta aquí porque fue descubierto al intentar aislar tests de webhook y constituye un riesgo de cobertura real (ver R-10 en §18).

#### `apps.billing.tests.test_mp_integration` y `apps.billing.tests.test_subscriptionv2_birth_path` — **hallazgo nuevo de esta actualización, directamente relevante a la sección 13 (webhooks)**

Estos son los módulos de test más cercanos a "duplicados", `subscription_preapproval`, `subscription_authorized_payment" y procesamiento real del webhook (más allá de la sola verificación de firma). Se ejecutaron por separado, con su salida completa redirigida a archivo temporal e inspeccionada mediante lecturas parciales y filtros (wrappers reales en §22):

```
apps.billing.tests.test_mp_integration
Ran 22 tests in 1.297s → FAILED (errors=9)   (EXITCODE=1)

apps.billing.tests.test_subscriptionv2_birth_path
Ran 22 tests in 7.955s → FAILED (failures=4, errors=8)   (EXITCODE=1)
```

**HECHO COMPROBADO**: se inspeccionó directamente el código fuente de ambos módulos de test y se confirmó que usan `@patch.object(MercadoPagoWebhookView, 'process_subscription_event', ...)` / `'process_payment_event'` — métodos que **ya no existen** en la vista actual (el procesamiento fue refactorizado hacia `dispatch_webhook()` / `webhook_processor.py`, documentado en §12-§13). Los mensajes de error capturados durante la ejecución (`AttributeError: <class 'apps.billing.views.MercadoPagoWebhookView'> does not have the attribute 'process_subscription_event'`, u homólogo para `'process_payment_event'`) fueron confirmados para un subconjunto de los bloques de error — la inspección de `test_subscriptionv2_birth_path` usó `Select-String ... | Select-Object -First 15`, es decir, se revisaron los primeros 15 encabezados de traceback, no la totalidad de los 12 casos fallidos (4 failures + 8 errors) de ese módulo (ver wrapper real en §22).

**INFERENCIA**: que **la totalidad** de los 9 errores de `test_mp_integration` y los 12 casos fallidos de `test_subscriptionv2_birth_path` comparten exactamente la misma causa raíz (el mock roto) es una inferencia razonable dado el patrón observado en los casos efectivamente inspeccionados, pero **no fue demostrada mediante revisión completa de cada traza individual**. En particular, los 4 `FAIL` (no `ERROR`) en `test_subscriptionv2_birth_path` son `AssertionError: 500 != 200` — consistente con que un mock roto deje pasar una excepción no manejada hacia la vista real, pero no se verificó traza por traza que las 4 fallas de aserción no tengan, en algún caso, una causa adicional o distinta.

**Impacto en la cobertura**: estos son los únicos módulos que, por nombre y docstring, prometían ejercer el procesamiento real (no solo la firma) de `subscription_preapproval`/`subscription_authorized_payment`, deduplicación de `BillingEvent`/`PaymentEvent`, y correlación de webhooks contra `SubscriptionV2`. Al estar rotos contra la arquitectura vigente, **no ofrecen ninguna cobertura efectiva hoy** sobre esa lógica — solo demuestran que el mock apunta a atributos inexistentes. Los **9 tests de `test_webhook_signature`** (§13.2) no demuestran el procesamiento completo de webhooks: solo cubren verificación de firma HMAC, no el dispatch a los handlers de tópico ni la deduplicación real contra la vista actual.

### 15.1b Tests backend — HISTÓRICOS, NO RE-VERIFICADOS EN `7e1ef92`

> Los siguientes resultados provienen de la auditoría anterior sobre `3e33830` y **no fueron re-ejecutados en esta actualización**. No deben citarse como evidencia vigente de `7e1ef92` — se conservan únicamente como referencia histórica.

#### `apps.reviews.tests.test_reviews + test_public_flow + test_public_hardening + test_e2e_lifecycle`
```
HISTÓRICO (3e33830): Ran 153 + 65 = ~218 tests → OK
```

| Clase de test | Qué valida |
|---|---|
| `ReviewConfigModelTest.test_redirect_url_priority_*` | Prioridad custom > place_id > google_url |
| `test_submit_returns_redirect_url` | API pública retorna redirect_url correcto |
| `test_custom_redirect_url_validation` | Solo HTTPS, rechazo de HTTP |
| `test_smart_filter_*` | Modo smart_filter con umbral |

### 15.2 Tests frontend — RE-EJECUTADOS EN `7e1ef92`

Ver "Tests frontend `qr-reviews-card.test.tsx` + `url.test.ts`" arriba (16/16 passed, nuevo).

### 15.2b Tests frontend — HISTÓRICOS, NO RE-VERIFICADOS EN `7e1ef92`

#### `src/app/admin/suscripciones/[subscriptionId]/__tests__/suscripcion-detail-content.test.tsx`
```
HISTÓRICO (3e33830): 10 tests → OK (929ms)
```

Valida: render de datos, botón cancelar visible/oculto según `can_cancel`, modal de cancelación, notas.

#### `src/features/billing/__tests__/reconcile-checkout.test.ts`
```
HISTÓRICO (3e33830): 12 tests → OK
```

Valida: URL `POST /reconcile/` como path segment, sin query params, manejo de 403/500, red errors, respuesta correcta.

#### `src/app/app/onboarding/__tests__/checkout-page-reconcile.test.tsx`
```
HISTÓRICO (3e33830): 9 tests → OK (311ms)
```

Valida: `reconcileInFlightRef` bloquea clics concurrentes (C1), transición a activated (C2), race condition reconcile+polling (C_race), warning y retry (C3).

#### `src/features/billing/components/__tests__/QrReviewsPlanBuilder.test.tsx`
```
HISTÓRICO (3e33830): 5 tests → OK
```

Valida: precios, plan_codes canónicos (`qr_reviews_base`/`qr_reviews_pro`).

### 15.3 Cobertura faltante identificada

| Área | Tests faltantes |
|---|---|
| `/admin/clientes/[id]` | Ningún test de componente (ni unitario ni integración) |
| `/admin/clientes` (lista) | Sin tests de componente |
| Endpoint `GET /platform-admin/clients/{id}/` | Sin test de integración backend |
| `MenuEngagementSettings.google_place_id` | Sin test de divergencia con `ReviewConfig.google_place_id` |
| Auditoría de escritura en `AdminQRReviewsConfigView.patch()` | La suite `test_admin_qr_reviews.py` (22 tests) no verifica el contenido/acción de `AccessAuditLog` tras un PATCH — el hallazgo de §8.5 no está cubierto por test |
| Aislamiento del endpoint QR admin (no es "cross-tenant": `superadmin`/`operations` son roles globales) | Sin test explícito de que un PATCH sobre `business_id=A` no modifica ni expone datos de `business_id=B`; sin test de que IDs inexistentes devuelven 404 combinado con el resto de la matriz (roles no autorizados → 403 sí está cubierto) |
| Flujo completo QR: slug change → QR impreso inválido | Sin test end-to-end |
| Nota interna en business: ownership check | Sin test que verifique cross-tenant access |
| `apps.billing.tests.test_checkout_flow_v2` | 20/24 tests en error por desalineación de esquema (`Plan.billing_cycle`, 18) y mock de `request.data` en `WSGIRequest` (2) — deuda técnica no cubierta por corrección, riesgo de falsos negativos en CI si esta suite se ejecuta como parte de un pipeline |
| `apps.billing.tests.test_mp_integration` / `test_subscriptionv2_birth_path` (procesamiento real de webhooks) | `test_mp_integration`: 9 de 22 tests en error; `test_subscriptionv2_birth_path`: 4 fallos + 8 errores de 22 tests — sin cobertura efectiva vigente de deduplicación/correlación real contra la arquitectura actual del webhook (ver §15.1) |
| Escenario "MP cancela → falla escritura local" | `test_retry_after_mp_cancel_but_local_fail_repairs_state` (en `test_pr2_admin_cancel_subscription.py`) no simula ninguna falla real — el nombre/docstring no corresponde al código (ver §11.8) |

---

## 16. Duplicaciones e inconsistencias

### 16.1 `google_place_id` duplicado

| Modelo | Campo | Editable en | Consumidor |
|---|---|---|---|
| `reviews.ReviewConfig` | `google_place_id` | App `/app/resenas/configuracion` | `/r/{slug}/` redirect |
| `menu.MenuEngagementSettings` | `google_place_id` | App `engagement-settings-section.tsx` | `/m/{slug}/` botón reseña |

**Sin sincronización**. Un usuario puede configurar Place IDs distintos para los dos productos.  
**Re-confirmado en `7e1ef92`** (§8.4): no existe ninguna relación (`ForeignKey`, `signal`, propiedad derivada) entre ambos modelos.  
**Fuente canónica recomendada**: si el negocio tiene ambos productos, `ReviewConfig.google_place_id` podría ser la fuente única, y `MenuEngagementSettings` derivar de ahí — **pero no se recomienda unificar automáticamente sin evidencia de que ambos consumidores (`/r/{slug}/` y `/m/{slug}/`) deban compartir el mismo Place ID de negocio** (un mismo local puede tener páginas de Google distintas para menú vs. reseñas generales en algunos casos de uso reales). Ver NR-02 con esta salvedad.

### 16.2 `billing.Subscription` (legacy OneToOne) todavía activo

**Estado**: Se escribe en `service_activation._qr_reviews_legacy_subscription()` en cada activación de `qr_reviews`. No se lee en el panel admin, pero puede ser leído en código de entitlements de `qr_reviews` en la ruta del dueño.

**Deuda técnica**: Este modelo debe ser eliminado una vez todos los consumidores lean de `SubscriptionV2`.

### 16.3 `billing.PaymentEvent` (legacy) duplica `billing.BillingEvent`

**HECHO COMPROBADO**: En `MercadoPagoWebhookView._write_legacy_billing_event()`, se escriben ambos `PaymentEvent` Y `BillingEvent` para cada webhook recibido. El panel admin usa `BillingEvent` exclusivamente. `PaymentEvent` parece no tener consumidores activos en el panel admin.

### 16.4 Estados de `Business.status` calculados de manera diferente

| Lugar | Cálculo |
|---|---|
| Backend `_admin_status_label()` | `mapping.get(business.status, business.status)` — normalización 1:1 |
| Backend `_subscription_admin_status()` | Añade `scheduled_cancel` si `cancel_at_period_end` |
| Frontend `statusLabel()` | `display.ts` — map de strings |

Los tres deben estar sincronizados. **INFERENCIA**: Si se añade un nuevo estado a `Business.status`, los tres lugares deben actualizarse.

### 16.5 `external_reference` y `provider_sub_id` de `SubscriptionV2`

- `external_reference`: Siempre presente (`SUB-{uuid}`), único, usado para correlación con MP.
- `provider_sub_id`: El `preapproval_id` de MP, asignado cuando el usuario completa el checkout. Sparse unique.

La cancellación administrativa exige `provider_sub_id` cuando `provider=mercadopago`. Si está vacío, lanza `CancellationError` y el admin no puede cancelar automáticamente — debe hacerlo manualmente en MP.

---

## 17. Normalizaciones recomendadas

> No implementar todavía. Solo descripción del estado objetivo. **Se removió de esta lista la normalización "implementar sección QR de Reseñas en el panel admin" de la auditoría anterior (NR-05 en `3e33830`) porque ya fue implementada por el merge — ver §8.**

### NR-01: Eliminar `billing.Subscription` (legacy)
- Verificar que ningún consumer lea `business.billing_subscription` en runtime.
- Migrar el único consumer (`qr_reviews` entitlements si lo usa) a `SubscriptionV2`.
- Hacer DROP del modelo.

### NR-02: Unificar `google_place_id` en `ReviewConfig` (con salvedad)
- `MenuEngagementSettings.google_place_id` podría derivarse de `ReviewConfig.google_place_id` si el negocio tiene `qr_reviews`.
- Para negocios `menu_qr` sin `qr_reviews`: `MenuEngagementSettings` sigue siendo la fuente.
- **No mantener dos campos editables paralelos para el mismo dato SI se confirma que ambos productos deben apuntar al mismo Place ID de Google** — esta condición de negocio no fue verificada en esta auditoría (ver §16.1) y debe confirmarse con el equipo de producto antes de implementar, no asumirse desde el código.

### NR-03: Auto-calcular `google_review_url` al guardar `google_place_id`
- Si el usuario actualiza `google_place_id`, `google_review_url` debería ofrecer recalcularse o al menos marcarse como obsoleta.
- Alternativa: deprecar `google_review_url` como campo editable y derivarlo siempre de `google_place_id` vía la propiedad `redirect_url`.

### NR-04: Eliminar doble escritura `PaymentEvent` + `BillingEvent`
- `PaymentEvent` puede ser removido una vez se verifique que no tiene consumers activos.
- Solo escribir `BillingEvent` + `BillingInvoiceEvent` en el nuevo flujo.

### NR-05 (nuevo): Corregir etiquetado de auditoría en `AdminQRReviewsConfigView.patch()`
- Reemplazar `log_platform_action(action='ADMIN_CLIENT_VIEWED')` por una acción propia, p. ej. `ADMIN_QR_REVIEWS_CONFIG_UPDATED`, exclusiva para el método `patch()`.
- Incluir en `details` los campos modificados y, si es posible, valores anteriores/nuevos (siguiendo el patrón ya usado en `_log_admin_cancel_audit()`, ver §11.7).
- Añadir test que verifique la acción y el contenido del `AccessAuditLog` tras un PATCH exitoso (hueco identificado en §19).

### NR-06 (nuevo, prioridad baja): Alinear `apps.billing.tests.test_checkout_flow_v2` con el esquema actual de `Plan`
- Investigar por qué el test referencia `Plan.billing_cycle`, campo inexistente en el modelo actual — determinar si el campo fue renombrado/eliminado en una migración posterior a la creación del test, o si el test corresponde a una versión de `Plan` no fusionada.
- Corregir las 20 aserciones/fixtures afectadas y las 2 fallas de `request.data` en `WSGIRequest`.
- Fuera del alcance de esta auditoría (no relacionado al merge de QR Reseñas/webhooks), pero debe resolverse antes de confiar en esta suite como señal de CI.

---

## 18. Riesgos ordenados por severidad

> Renumerado completo respecto a la auditoría anterior. Se removieron: R-01 (divergencia repo/deploy — **resuelto**, ver §8), R-10 histórico (`previous_status` ausente de auditoría — **resuelto**, ver §11.7). Se agregaron: riesgo de recuperación de webhooks fallidos, riesgo de `notification_url` ausente en suscripciones (reclasificado como NO VERIFICADO — CONTRATO EXTERNO NO RESUELTO, ver §13.5b), riesgo de auditoría mal etiquetada en el nuevo endpoint QR admin, riesgo de la suite `test_checkout_flow_v2`, riesgo de las suites `test_mp_integration`/`test_subscriptionv2_birth_path` rotas (R-17 en esta numeración), y riesgo del escenario "MP cancela → falla escritura local" sin recuperación demostrada (R-16, §11.8).

### CRÍTICO

**No se afirma que no existan riesgos críticos.** Dos condiciones permanecen sin resolver y ambas afectan directamente la integridad de cobros/cancelaciones: (a) la entrega de webhooks de suscripción vía `notification_url` no está verificada (§13.5b, R-03), y (b) existe un escenario sin recuperación demostrada donde Mercado Pago cancela correctamente pero el estado local (`SubscriptionV2`/`Business.status`) puede quedar desalineado, con una corrección por webhook posterior que es, en el mejor caso, parcial e incierta (§11.8, R-16). Mientras esto no se resuelva, **no corresponde declarar el dominio de cobros/cancelaciones libre de riesgo crítico**. No se incluye aquí una fila con severidad CRÍTICO formal porque no se demostró un incidente activo en producción durante esta auditoría (solo lectura de código y tests) — pero la ausencia de verificación en ambos puntos impide cerrar esta sección con una afirmación de "ningún riesgo crítico".

### ALTO

| ID | Riesgo | Área | Impacto |
|---|---|---|---|
| R-01 | 3 tests MFA admin fallando — re-confirmado en `7e1ef92` | Autenticación | El flujo de enrolamiento MFA puede estar roto o los tests no siguen el contrato actual — riesgo de que el enrolamiento no sea posible en ambientes de testing o CI |
| R-02 | Webhooks en estado `FAILED` no tienen mecanismo de recuperación | Billing, Webhooks | `DEAD_LETTER` está definido en `WebhookDelivery.ProcessingStatus` pero nunca se asigna en ningún lugar del código (confirmado por grep de todo el repo); no existe tarea de Celery, comando ni endpoint de replay/retry. Un fallo transitorio (timeout a MP, error de DB puntual) deja el evento permanentemente en `FAILED` sin que MP lo sepa (la vista siempre responde 200), y sin ninguna forma automática de reprocesarlo |
| R-03 | `notification_url` no se envía a MP para suscripciones — **NO VERIFICADO, contrato externo no resuelto** | Billing, Webhooks | `create_preapproval_plan()`/`create_preapproval()` no incluyen `notification_url` en el payload (solo `create_preference()`, para pagos únicos, lo hace). No se puede determinar desde el repositorio ni desde la documentación pública disponible si esto es soportado por MP para Suscripciones; debe validarse con soporte de MP o prueba sandbox antes de asumir que la entrega depende únicamente de la configuración de cuenta (ver §13.5b) |
| R-16 (nuevo) | Escenario "MP cancela correctamente → falla la escritura local" sin recuperación demostrada | Billing, Cancelación | Si la segunda transacción de `cancel_subscription_immediately()` falla tras un `cancel_preapproval()` exitoso, `SubscriptionV2`/`Business.status` pueden quedar activos localmente mientras MP ya canceló. `_handle_subscription_preapproval()` no actualiza `Business.status`, y depende de que el webhook llegue (no garantizado mientras R-03 no se resuelva). El test que promete cubrir este escenario (`test_retry_after_mp_cancel_but_local_fail_repairs_state`) no lo simula realmente (ver §11.8) |
| R-17 (nuevo) | Suites `test_mp_integration` y `test_subscriptionv2_birth_path` rotas contra la arquitectura actual del webhook | QA, Billing, Webhooks | Ambas mockean métodos (`process_subscription_event`/`process_payment_event`) que ya no existen en `MercadoPagoWebhookView` — 9/22 y 12/22 tests fallan respectivamente. Son los módulos más cercanos a probar deduplicación y correlación real de `subscription_preapproval`/`subscription_authorized_payment`; su ruptura deja sin cobertura efectiva esa lógica (ver §15.1) |
| R-05 | `google_review_url` no se recalcula al cambiar `google_place_id` | QR Reseñas | Place IDs divergentes; `google_review_url` en prioridad 3 no tiene efecto si hay `custom_redirect_url` o `google_place_id`, pero si se borran ambos, el redirect puede apuntar a un lugar incorrecto |
| R-06 | Dos `google_place_id` independientes (ReviewConfig vs MenuEngagementSettings) | QR, Menú | Un negocio con ambos productos puede tener reseñas en dos lugares distintos de Google sin saberlo — re-confirmado en `7e1ef92`, sin cambios |
| R-07 | Modelo legacy `billing.Subscription` sigue escribiéndose | Billing | Acumulación de deuda técnica; eventual inconsistencia si el legacy model queda out-of-sync |
| R-08 | Nota interna sin validación de ownership del target | Admin | Cualquier superadmin/operations puede agregar notas a cualquier business_id sin validación |
| R-09 | `BillingEvent` y `PaymentEvent` escritos en paralelo | Billing | Doble contabilidad de eventos; confusión en auditoría si alguien lee PaymentEvent |
| R-10 | `apps.billing.tests.test_checkout_flow_v2` con 20/24 tests en error | QA, Billing | `FieldError: Plan.billing_cycle` (campo inexistente, 18 casos) y `AttributeError` en `WSGIRequest.data` (2 casos) — deuda técnica de esquema no relacionada al merge de QR Reseñas; riesgo de falsos negativos si esta suite se corre sin filtrar en un pipeline de CI |

### MEDIO

| ID | Riesgo | Área | Impacto |
|---|---|---|---|
| R-04 | PATCH de QR Reseñas registrado como `ADMIN_CLIENT_VIEWED` | Auditoría, QR Reseñas | Las escrituras quedan indistinguibles de las lecturas en `AccessAuditLog`; no se registran claramente la acción de actualización ni los campos anteriores/nuevos |

**Corrección respecto a versiones anteriores de este documento**: `R-04` se citaba en el resumen ejecutivo (§1), en §8.5, en el Slice 6 (§20) y en el checklist (§21), pero no existía como fila en esta sección — se agrega aquí por primera vez con severidad MEDIO, consistente con todas esas referencias. No se reclasificaron otras severidades sin justificación adicional a la ya documentada en cada riesgo.

### BAJO

| ID | Riesgo | Área | Impacto |
|---|---|---|---|
| R-11 | Vista `/admin/clientes/[id]` sin tests de componente | Frontend | Regresiones silenciosas en UI del detalle de cliente (incluyendo la nueva `QRResenasCard`) |
| R-12 | `Business.status` no invalidado en navegación admin-cliente tras cancelar | UX | Estado stale hasta que el usuario recargue la vista del cliente |
| R-13 | Sin test de divergencia `google_place_id` entre ReviewConfig y MenuEngagementSettings | Tests | No hay detección automatizada de inconsistencia |
| R-14 | Sin test dedicado que confirme que un PATCH en `AdminQRReviewsConfigView` para `business_id=A` no altera ni expone datos de otro `business_id` | Tests | `superadmin`/`operations` son roles internos globales — no corresponde exigirles 404/403 al consultar otro negocio (eso sería un bug). Lo que falta cubrir es: el `business_id` seleccionado es el único modificado, no hay mezcla de datos entre respuestas, e IDs inexistentes devuelven 404 (esto último sí está cubierto) |
| R-15 | `slugPreview` en `QRResenasCard` hardcodea el dominio en vez de usar `lib/url.ts`/`NEXT_PUBLIC_SITE_URL` | Frontend | Duplicación menor; el preview mostrado al operador podría no reflejar el dominio real si cambia `NEXT_PUBLIC_SITE_URL` en algún ambiente |

---

## 19. Huecos de cobertura

| Área | Hueco |
|---|---|
| Permisos backend | `allowed_internal_roles` declarado en la clase pero no en todos los métodos (el check lo hace `HasInternalRole.__call__`, que lee la clase) — correcto, pero no hay test que verifique rol `support_agent` accediendo a un endpoint de `operations` |
| Auditoría de escritura QR Reseñas admin | `test_admin_qr_reviews.py` no verifica la acción/contenido de `AccessAuditLog` tras un PATCH — no cubre el hallazgo de §8.5 |
| Aislamiento por `business_id` del endpoint QR admin (no "cross-tenant": roles globales) | Sin test dedicado que verifique que un PATCH sobre un `business_id` no toca configuración de otro; sin test de "no mezcla de datos entre respuestas" |
| Reconcile cross-tenant | El test `external_reference guard` existe, pero no hay test que simule un usuario intentando reconciliar una sesión de otro tenant |
| Slug change → QR impreso roto | Sin test end-to-end |
| `billing.Subscription` eliminación | Sin test de contrato que verifique que entitlements siguen funcionando sin el modelo legacy |
| Webhook con `MP_WEBHOOK_SECRET` no configurado en producción | Solo warning/error en logs, sin alerta programática (métrica, health-check o notificación) |
| Webhooks en estado `FAILED`/recuperación | Sin test ni mecanismo que verifique reprocesamiento — `DEAD_LETTER` nunca se alcanza en el código (ver R-02) |
| Estados transitivos: `PAST_DUE → SUSPENDED → CANCELED` | Cobertura parcial; el flujo completo no tiene test e2e de la cadena de estados |
| `apps.billing.tests.test_checkout_flow_v2` | 20/24 tests en error por desalineación de esquema — la suite no puede usarse como señal confiable hasta corregirse (ver R-10) |
| Suites `test_mp_integration`/`test_subscriptionv2_birth_path` (procesamiento real de webhooks) | Rotas contra la arquitectura actual (mocks a métodos inexistentes) — sin cobertura efectiva de deduplicación/correlación real (ver R-17) |
| Escenario "MP cancela → falla escritura local" | Sin recuperación demostrada; el test que promete cubrirlo no lo simula (ver R-16, §11.8) |

---

## 20. Propuesta de remediación en slices

> Ningún slice implementa código. Solo descripción de objetivo, archivos y contrato. **Se removió el slice "Añadir `review_config` read-only al endpoint de cliente admin" de la auditoría anterior (Slice 2 en `3e33830`) porque la funcionalidad equivalente ya está implementada como endpoint independiente — ver §8.** Slices reordenados en esta actualización: los que afectan la integridad de activaciones/cancelaciones y la confiabilidad de la suite de webhooks se priorizan por encima de MFA y de la auditoría del endpoint QR.

### Slice 1 — Resolver el contrato real de entrega de notificaciones para Suscripciones (`notification_url`) (ALTA prioridad)
- **Objetivo**: Determinar de forma concluyente cómo Mercado Pago entrega notificaciones para `preapproval`/`preapproval_plan`, y corregir el código en consecuencia (R-03, §13.5b).
- **Archivos**: `services/api/src/apps/billing/mp_service.py` (`create_preapproval`, `create_preapproval_plan`).
- **Contrato esperado**: Antes de escribir código, verificar con documentación actual de MP y/o soporte de MP y/o una prueba controlada en sandbox si `notification_url` es una propiedad soportada en `POST /preapproval` y `POST /preapproval_plan`. Si lo es, incluirla en el payload apuntando al mismo endpoint que usa `create_preference()`. Si `notification_url` no está soportado por `POST /preapproval` o `POST /preapproval_plan`, identificar mediante documentación oficial específica, soporte de Mercado Pago o prueba sandbox cuál es el mecanismo soportado para asociar la URL receptora a los tópicos de Suscripciones. No asumir como fallback la configuración mediante "Tus integraciones", porque la documentación oficial vigente declara que ese método no está disponible para Suscripciones.
- **Tests necesarios**: Test que verifique el payload enviado incluye (o no, según se determine) `notification_url`; si aplica, test de integración/sandbox que confirme la recepción real de webhooks de suscripción.
- **Riesgo**: Medio — un cambio incorrecto en el payload podría ser ignorado silenciosamente por MP o, en el peor caso, rechazado.
- **Dependencias**: Ninguna. Debe resolverse antes o en paralelo al Slice 3 (la reconciliación depende de saber si los webhooks de suscripción llegan de forma confiable).

### Slice 2 — Mecanismo de recuperación para webhooks `FAILED` (ALTA prioridad)
- **Objetivo**: Dar visibilidad y capacidad de reprocesamiento a entregas en `FAILED` (hallazgo §13.6, R-02).
- **Archivos**: `services/api/src/apps/billing/webhook_processor.py`, nuevo comando de management o tarea Celery.
- **Contrato esperado**: Comando `reprocess_failed_webhooks` (o tarea periódica) que reintente `dispatch_webhook()` para deliveries en `FAILED` con backoff, marcando `DEAD_LETTER` tras N intentos.
- **Tests necesarios**: Test que simule un handler fallido y verifique reprocesamiento exitoso en el reintento.
- **Riesgo**: Medio — requiere cuidado para no reactivar suscripciones ya canceladas (reusar `can_activate()` existente).
- **Dependencias**: Ninguna.

### Slice 3 — Resolver desalineación MP/local tras cancelación parcial (ALTA prioridad)
- **Objetivo**: Diseñar (no implementar todavía) un mecanismo que garantice que, si `cancel_preapproval()` tiene éxito en MP pero la escritura local subsiguiente falla, el sistema detecte y corrija la desalineación entre el estado real en MP y `SubscriptionV2`/`Business.status` (R-16, §11.8).
- **Archivos**: `services/api/src/apps/billing/cancellation_service.py`, `platform_admin_subscriptions_views.py`, posible nuevo comando de reconciliación.
- **Contrato esperado**: Definir el estado objetivo — por ejemplo, separar la llamada a MP de la escritura local en pasos idempotentes y re-ejecutables, agregar un mecanismo de reconciliación periódica que compare el estado de `SubscriptionV2` contra `MP.get_preapproval()` para suscripciones recientemente canceladas por admin, y/o una alerta cuando la escritura final del paso 4 falla tras un `cancel_preapproval()` exitoso. Debe considerar explícitamente que un webhook posterior no corrige `Business.status` (gap confirmado en `_handle_subscription_preapproval()`).
- **Tests necesarios**: Test que simule realmente una falla en la escritura local posterior a un `cancel_preapproval()` exitoso (a diferencia de `test_retry_after_mp_cancel_but_local_fail_repairs_state`, que actualmente no lo hace) y verifique la corrección/detección propuesta.
- **Riesgo**: Alto — toca el flujo crítico de cancelación; requiere diseño cuidadoso antes de tocar código.
- **Dependencias**: Se beneficia de que el Slice 1 esté resuelto (para saber si puede confiarse en un webhook posterior como parte de la corrección), pero puede diseñarse en paralelo.

### Slice 4 — Recuperar una suite confiable para procesamiento de webhooks (ALTA prioridad)
- **Objetivo**: Corregir `test_mp_integration.py` y `test_subscriptionv2_birth_path.py` para que mockeen la arquitectura actual (`dispatch_webhook()`/`webhook_processor.py`) en lugar de los métodos removidos `process_subscription_event`/`process_payment_event` (R-17, §15.1).
- **Archivos**: `services/api/src/apps/billing/tests/test_mp_integration.py`, `services/api/src/apps/billing/tests/test_subscriptionv2_birth_path.py`.
- **Contrato esperado**: Ambas suites pasan 22/22 usando mocks/fixtures alineados con `_handle_subscription_preapproval()`/`_handle_authorized_payment()` actuales, sin cambiar comportamiento de producción.
- **Tests necesarios**: Las mismas suites, corregidas.
- **Riesgo**: Bajo — cambios acotados a fixtures/mocks de test.
- **Dependencias**: Ninguna.

### Slice 5 — Alinear tests MFA admin (MEDIA prioridad)
- **Objetivo**: Hacer pasar los 3 tests fallidos de MFA enrollment.
- **Archivos**: `services/api/src/apps/accounts/tests/test_admin_auth.py`, `platform_auth_views.py`.
- **Contrato esperado**: Determinar si el endpoint de enrolamiento requiere MFA previo (y actualizar el test) o si hay un bug en la vista (y corregir la vista).
- **Tests necesarios**: Los 3 actuales deben pasar sin modificar el comportamiento de seguridad.
- **Riesgo**: Bajo — no modifica flujo de producción si solo se ajustan fixtures de test.
- **Dependencias**: Ninguna.

### Slice 6 — Corregir etiquetado de auditoría en `AdminQRReviewsConfigView.patch()` (MEDIA prioridad)
- **Objetivo**: Distinguir lecturas de escrituras en `AccessAuditLog` para el endpoint QR admin (hallazgo §8.5, R-04 — severidad MEDIO; el slice mantiene la misma prioridad relativa, sin escalar).
- **Archivos**: `services/api/src/apps/reviews/admin_views.py`.
- **Contrato esperado**: `patch()` registra una acción propia (p. ej. `ADMIN_QR_REVIEWS_CONFIG_UPDATED`) con campos modificados en `details`; `get()` conserva `ADMIN_CLIENT_VIEWED`.
- **Tests necesarios**: Nuevo test que verifique la acción y el contenido de `AccessAuditLog` tras un PATCH exitoso.
- **Riesgo**: Bajo — solo agrega/renombra una acción de auditoría, no cambia comportamiento funcional.
- **Dependencias**: Ninguna.

### Slice 7 — Resto de normalizaciones (BAJA prioridad)

Los siguientes slices no afectan integridad de activaciones/cancelaciones ni la confiabilidad de tests de webhooks; se agrupan como normalizaciones de menor impacto.

#### 7.1 Documentar y corregir `google_review_url` stale
- **Objetivo**: Prevenir divergencia entre `google_place_id` y `google_review_url`.
- **Archivos**: `reviews/serializers.py`, `reviews/models.py`.
- **Contrato esperado**: Al guardar `google_place_id` via `ReviewConfigSerializer`, si `google_review_url` contiene un `placeid=` diferente, emitir un `warning` en el response. O bien: recalcular `google_review_url` automáticamente si el usuario no lo editó explícitamente en esta request.
- **Tests necesarios**: `test_redirect_url_priority_*` deben seguir pasando.
- **Riesgo**: Bajo — solo es un campo informativo; la propiedad `redirect_url` ya tiene la prioridad correcta.
- **Dependencias**: Ninguna.

#### 7.2 Unificar `google_place_id` en ReviewConfig como fuente única (condicionado)
- **Objetivo**: `MenuEngagementSettings.google_place_id` lee de `ReviewConfig` si existe, en lugar de almacenarse por separado.
- **Archivos**: `menu/models.py`, `menu/serializers.py`, `reviews/models.py`.
- **Contrato esperado**: `MenuEngagementSettings.google_write_review_url` usa `ReviewConfig.google_place_id` si el negocio tiene QR Reseñas activado.
- **Precondición no verificada en esta auditoría**: confirmar con producto que ambos productos deben compartir el mismo Place ID antes de implementar (ver NR-02 con salvedad, §17).
- **Tests necesarios**: `test_qr_reviews`, `test_menu_qr_access` deben pasar.
- **Riesgo**: Medio — puede romper negocios `menu_qr` sin `qr_reviews`.
- **Dependencias**: Confirmación de producto (bloqueante).

#### 7.3 Eliminar modelo legacy `billing.Subscription`
- **Objetivo**: Remover el OneToOne legacy.
- **Archivos**: `billing/models.py`, `billing/service_activation.py`, `business/models.py` (si `Subscription` está en `business.models`).
- **Contrato esperado**: Entitlements de `qr_reviews` usan `SubscriptionV2` exclusivamente.
- **Tests necesarios**: `test_qr_reviews_service_activation.py` debe pasar. Test de regresión de entitlements.
- **Riesgo**: Alto si hay consumers ocultos. Requiere auditoría completa de código que lee `business.billing_subscription`.
- **Dependencias**: Ninguna (este slice y el 7.2 son dominios independientes; **corrección respecto a una versión anterior de este documento**, que declaraba una dependencia entre ambos sin justificación — no comparten código ni modelos).

#### 7.4 Test de componente para `/admin/clientes/[id]` incluyendo `QRResenasCard`
- **Objetivo**: Añadir tests de componente React para `ClienteDetailContent` y `QRResenasCard`.
- **Archivos**: Nuevo `__tests__/cliente-detail-content.test.tsx`.
- **Tests necesarios**: Render con cliente activo, con suscripción cancelada, sin suscripción, risk badges, con/sin `service_type='qr_reviews'`.
- **Riesgo**: Ninguno (solo tests, sin cambio de código).
- **Dependencias**: Ninguna.

#### 7.5 Alinear `test_checkout_flow_v2` con el esquema actual de `Plan`
- **Objetivo**: Corregir los 18 errores por `Plan.billing_cycle` y los 2 por `WSGIRequest.data`.
- **Archivos**: `services/api/src/apps/billing/tests/test_checkout_flow_v2.py`.
- **Contrato esperado**: Suite pasa 24/24 sin modificar comportamiento de producción.
- **Riesgo**: Bajo — cambios acotados a fixtures/aserciones de test.
- **Dependencias**: Ninguna.

---

## 21. Checklist de QA manual

### Investigación previa a cualquier remediación (bloqueante para Slice 1, §20)
- [ ] Confirmar con documentación vigente de MP (o soporte de MP) si `notification_url` es una propiedad soportada en `POST /preapproval` y `POST /preapproval_plan` — actualmente **NO VERIFICADO** (§13.5b, R-03)
- [ ] Si no es soportada vía API, confirmar cómo está configurada la entrega de webhooks de suscripción en el panel de cuenta de MP en producción
- [ ] Prueba controlada en sandbox de MP: crear un `preapproval` de prueba y confirmar si se reciben webhooks sin `notification_url` en el payload

### Panel admin — autenticación y acceso
- [ ] Login como `superadmin` — acceso a todas las secciones
- [ ] Login como `support_agent` — solo ve soporte y notificaciones
- [ ] Login como `content_admin` — solo ve blog
- [ ] Usuario sin `is_platform_staff` — 403 en todos los endpoints `/platform-admin/`
- [ ] MFA requerido en login — verificar enrolamiento y recovery

### Panel admin — clientes
- [ ] `/admin/clientes` lista businesses HQ (sin sucursales)
- [ ] Filtros de búsqueda, estado, plan, trial
- [ ] Risk badges visibles en rows con `past_due`, `cancel_at_period_end`
- [ ] `/admin/clientes/{id}` carga datos correctos de `Business` 12
- [ ] Suscripción activa visible con `plan_code`, estado, período
- [ ] Pagos recientes con estado y motivo de fallo
- [ ] Eventos de billing con tipo y estado
- [ ] Nota interna: crear, aparece en la lista
- [ ] Enlace "Ver suscripción" navega a `/admin/suscripciones/{id}`
- [ ] ID inexistente → 404 page (no error 500)
- [ ] Si `client.service_type === 'qr_reviews'` — `QRResenasCard` visible bajo "Actividad reciente"
- [ ] Si `client.service_type !== 'qr_reviews'` — `QRResenasCard` NO se renderiza

### Panel admin — QR de Reseñas (nuevo, `AdminQRReviewsConfigView`)
- [ ] `GET /platform-admin/clients/{id}/qr-reviews-config/` — `superadmin`/`operations` reciben 200; otros roles reciben 403
- [ ] Business con `service_type != 'qr_reviews'` → 400 al consultar el endpoint
- [ ] Business inexistente → 404
- [ ] Cambio de slug válido → 200, `Business.slug` actualizado, banner de advertencia mostrado antes de guardar
- [ ] Slug duplicado / con mayúsculas / con espacios / con apóstrofes / con caracteres especiales → 400 con mensaje específico
- [ ] PATCH con campo desconocido → 400 con `allowed_fields`
- [ ] PATCH vacío → 400
- [ ] Guardar `google_place_id` → `google_place_updated_at` se actualiza; `google_review_url` NO se recalcula automáticamente
- [ ] Business sin `ReviewConfig` previo → se crea al guardar (badge "Sin ReviewConfig — se creará al guardar" visible antes)
- [ ] Revisar `AccessAuditLog` tras un PATCH — confirmar (o corregir, ver R-04) que la acción quede correctamente identificada como escritura

### Panel admin — suscripciones
- [ ] Lista con filtros por estado, plan, payment_issue
- [ ] Risk badge `reintentos_cobro` visible cuando `retry_count >= 2`
- [ ] Detalle con todos los pagos, eventos, invoice events y webhook errors
- [ ] Botón "Cancelar" solo visible cuando `can_cancel=true`
- [ ] Modal de cancelación: reason obligatorio
- [ ] Cancelación exitosa → estado cambia a `canceled`
- [ ] Business sin otras suscripciones → status = `onboarding`
- [ ] Tentativa de cancelar suscripción ya cancelada → respuesta idempotente

### QR de Reseñas (app del dueño)
- [ ] `/app/resenas/configuracion` muestra `google_place_id`, `google_review_url`, `custom_redirect_url`
- [ ] Guardar nuevo `google_place_id` — `google_review_url` NO cambia automáticamente (comportamiento actual)
- [ ] `redirect_url` en API response usa prioridad custom > place_id > google_url
- [ ] Borrar `custom_redirect_url` → redirect usa `google_place_id` (no el URL con place_id obsoleto)

### Webhook y activación
- [ ] Checkout exitoso → sesión pasa a `activated`, Business a `active`
- [ ] Webhook duplicado → segunda entrega recibe 200 sin re-procesamiento
- [ ] Webhook con firma inválida → 400, `WebhookDelivery.status = IGNORED`
- [ ] Suscripción cancelada → webhook tardío de `subscription_authorized_payment` → no reactiva
- [ ] POST reconcile retorna `status=activated` cuando ya hay pago en MP

---

## 22. Comandos ejecutados en esta actualización (develop@7e1ef92)

```bash
# Git baseline
git status --short
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git diff --stat
git diff --check
# → develop, 7e1ef92 (HEAD); origin/master en 7446016
# → git diff --stat: sin salida para archivos trackeados
# → git diff --check: sin salida, EXITCODE=0 para archivos trackeados (ver alcance real en §23)

# Verificación de contenedores activos — NO se reconstruyó la imagen en esta sesión
docker ps --format "table {{.Names}}\t{{.Status}}"
# → mirubro-api, mirubro-postgres, mirubro-redis ya estaban corriendo (Up). No se ejecutó
#   `docker compose build api` ni `docker compose up -d api` en esta actualización: no hay evidencia
#   de esos comandos en la sesión. Los resultados de test que siguen corresponden al código ya
#   presente en el contenedor `mirubro-api` en ejecución al momento de esta auditoría.

# Patrón real usado para ejecutar cada suite y capturar su exit code, redirigiendo la salida
# completa a un archivo temporal (no se imprimió la salida completa en la conversación):
$out = docker exec mirubro-api python manage.py test apps.billing.tests.test_pr2_admin_cancel_subscription --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t1.txt"
Get-Content "$env:TEMP\t1.txt" -Tail 6
# → Ran 49 tests in 6.546s, OK — EXITCODE=0

$out = docker exec mirubro-api python manage.py test apps.billing.tests.test_reconcile_session --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t2.txt"
Get-Content "$env:TEMP\t2.txt" -Tail 6
# → Ran 18 tests, OK — EXITCODE=0

$out = docker exec mirubro-api python manage.py test apps.billing.tests.test_webhook_signature --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t3.txt"
Get-Content "$env:TEMP\t3.txt" -Tail 6
# → Ran 9 tests in 0.020s, OK — EXITCODE=0

$out = docker exec mirubro-api python manage.py test apps.accounts.tests.test_admin_auth apps.accounts.tests.test_admin_dashboard_and_client_tickets --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t4.txt"
Get-Content "$env:TEMP\t4.txt" -Tail 15
# → Ran 60 tests in 11.904s, FAILED (failures=3) — EXITCODE=1 — mismos 3 tests que en 3e33830

$out = docker exec mirubro-api python manage.py test apps.reviews.tests.test_admin_qr_reviews --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t5.txt"
Get-Content "$env:TEMP\t5.txt" -Tail 6
# → Ran 22 tests in 4.850s, OK — EXITCODE=0

$out = docker exec mirubro-api python manage.py test apps.billing.tests.test_mp_integration apps.billing.tests.test_subscriptionv2_birth_path --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t6.txt"
Get-Content "$env:TEMP\t6.txt" -Tail 40
# → corrida combinada inicial, usada para inspección exploratoria; luego re-ejecutadas por separado (t7, t8) para aislar el resultado de cada módulo

$out = docker exec mirubro-api python manage.py test apps.billing.tests.test_mp_integration --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t7.txt"
Get-Content "$env:TEMP\t7.txt" -Tail 8
# → Ran 22 tests in 1.297s, FAILED (errors=9) — EXITCODE=1

$out = docker exec mirubro-api python manage.py test apps.billing.tests.test_subscriptionv2_birth_path --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t8.txt"
Get-Content "$env:TEMP\t8.txt" -Tail 8
Select-String -Path "$env:TEMP\t8.txt" -Pattern "^ERROR: |Error:" | Select-Object -First 15
# → Ran 22 tests in 7.955s, FAILED (failures=4, errors=8) — EXITCODE=1
# → el Select-String con -First 15 inspeccionó solo los primeros 15 encabezados de error/traceback,
#   no la totalidad de los 12 bloques fallidos — ver corrección de causalidad en §15.1

$out = docker exec mirubro-api python manage.py test apps.billing.tests.test_checkout_flow_v2 --verbosity=2 2>&1
$code = $LASTEXITCODE
$out | Out-File -FilePath "$env:TEMP\t9.txt"
Select-String -Path "$env:TEMP\t9.txt" -Pattern "\.\.\. ok$"
$lines = Get-Content "$env:TEMP\t9.txt"; $lines | Where-Object { $_ -match '^test_.*\.\.\. ok$' -or $_ -match '\) \.\.\. ok$' }
# → Ran 24 tests in 2.895s, FAILED (errors=20: 18 FieldError + 2 AttributeError) — EXITCODE=1
# → Select-String y Where-Object se usaron para identificar los 4 tests que sí pasaron, no para
#   imprimir la salida completa

# Tests frontend (desde apps/web) — QR Reseñas admin + url.ts
npx vitest run "src/components/admin/__tests__/qr-reviews-card.test.tsx" "src/lib/__tests__/url.test.ts"
$code = $LASTEXITCODE; Write-Host "EXITCODE=$code"
# → 16 tests (12 + 4), passed — EXITCODE=0
```

**Corrección respecto a versiones anteriores de esta sección**: los procesos de test fueron ejecutados completos y su salida se redirigió a archivos temporales (`Out-File -FilePath "$env:TEMP\tN.txt"`). Para inspeccionar resultados se utilizaron lecturas parciales y filtros como `Get-Content -Tail`, `Select-String`, `Select-Object` y `Where-Object`. Por lo tanto, **la bitácora no constituye una reproducción literal e íntegra de toda la salida de consola**: los bloques de comando arriba muestran los wrappers reales usados para ejecutar cada suite y capturar su `$LASTEXITCODE`, pero las inspecciones de contenido (qué tests pasaron, qué patrón de error aparece) se hicieron sobre porciones filtradas del archivo temporal, no sobre la totalidad de la salida impresa en la conversación. Se eliminó la afirmación anterior de que "todos los comandos fueron ejecutados sin filtros de salida" — es inexacta.

**Sobre `docker compose build api` / `docker compose up -d api`**: estos comandos **no fueron ejecutados** en esta sesión y se eliminaron de esta sección. La única verificación realizada fue `docker ps`, que confirmó que `mirubro-api` (junto con `mirubro-postgres` y `mirubro-redis`) ya estaba corriendo. No hay evidencia de que la imagen haya sido reconstruida durante esta actualización.

> Los comandos y resultados de tests de la auditoría anterior sobre `3e33830` (`test_reviews`, `test_public_flow`, `test_public_hardening`, `test_e2e_lifecycle`, tests de componente de suscripción, `reconcile-checkout.test.ts`, `checkout-page-reconcile.test.tsx`, `QrReviewsPlanBuilder.test.tsx`) **no se re-ejecutaron en esta actualización** — se conservan únicamente como referencia histórica en §15.1b/§15.2b.

---

## 23. Estado final de Git

```bash
$ git status --short
?? docs/AUDITORIA_PANEL_ADMIN_ALINEACION_SISTEMA_REAL.md

$ git branch --show-current
develop

$ git rev-parse --short HEAD
7e1ef92

$ git rev-parse --short origin/master
7446016

$ git diff --stat
(sin salida)

$ git diff --check
(sin salida, EXITCODE=0)
```

**Nota**: `git diff` no muestra el contenido de un archivo *untracked* — `git status --short` es la evidencia de su existencia (marca `??`). `git diff --stat` sin salida solo demuestra que no existen diferencias en archivos ya trackeados por git; **no demuestra que no haya archivos nuevos** (el propio documento de esta auditoría es untracked y no aparece en ese diff). `git diff --check` finalizó con **EXITCODE=0** para los cambios trackeados. **Este resultado no valida el contenido del documento de auditoría porque permanece untracked** — `git diff --check` no inspecciona archivos untracked. El working tree no tiene cambios en archivos trackeados: **no se modificó código, configuración, tests, migraciones ni dependencias durante esta auditoría** (afirmación basada en `git status --short` y `git diff --stat`, no en `git diff --check`).

**El único cambio generado por esta actualización es el presente archivo:**

```
docs/AUDITORIA_PANEL_ADMIN_ALINEACION_SISTEMA_REAL.md
```

---

## 24. Entrega — resumen de esta corrección

> Esta sección describe la matriz resultante tras las correcciones aplicadas. No se autocalifica el documento como "sin contradicciones" — se listan los hechos demostrados y se señala expresamente qué permanece como inferencia o sin resolver.

- **Veredicto corregido**: se eliminó la afirmación "el flujo de webhooks de Mercado Pago es robusto" del resumen ejecutivo y del veredicto general (§1, §2). El veredicto distingue: Firma HMAC (verificada, §13.2), Deduplicación (verificada por código; suites que la ejercen contra la vista actual rotas, §15.1), Procesamiento de tópicos (cobertura incompleta, §15.1), Recuperación de `FAILED` (ausente, R-02), Entrega efectiva de webhooks de suscripción desde MP (no verificada, R-03).
- **Matriz de riesgos**: se agregó la sección `### MEDIO` a §18, que no existía, con `R-04` (PATCH de QR Reseñas registrado como `ADMIN_CLIENT_VIEWED`) — riesgo referenciado en §1, §8.5, el Slice 6 y el checklist desde antes, pero ausente de la tabla de riesgos hasta esta corrección. Se agregaron también R-16 (MP cancela / falla local) y R-17 (suites de webhook rotas) a ALTO. No se reclasificaron severidades adicionales sin justificación ya presente en cada fila.
- **Qué resultados de tests están demostrados**: los conteos y `EXITCODE` de la tabla de abajo provienen de ejecuciones reales de esta sesión, con su salida redirigida a archivos temporales e inspeccionada mediante lecturas parciales (`Get-Content -Tail`) y filtros (`Select-String`, `Select-Object`, `Where-Object`) — ver wrappers reales en §22. Esto es una limitación reconocida: la bitácora no es una transcripción literal e íntegra de toda la salida de consola.
- **Qué causas siguen siendo inferencias**: que la totalidad de los 9 errores de `test_mp_integration` y de los 12 casos fallidos de `test_subscriptionv2_birth_path` comparten exactamente la misma causa raíz (mocks a métodos inexistentes) es razonable dado el patrón observado, pero no fue demostrado mediante revisión completa de cada traza — solo se inspeccionaron los primeros 15 encabezados de error de `test_subscriptionv2_birth_path` (ver §15.1, §22). Se separó explícitamente HECHO COMPROBADO de INFERENCIA en esa sección.
- **`notification_url` permanece sin resolver**: clasificación **NO VERIFICADO — CONTRATO EXTERNO NO RESUELTO** (§13.5b, R-03). No se afirma que la entrega dependa de configuración de cuenta/aplicación como alternativa de respaldo.
- **La configuración mediante "Tus integraciones" no debe asumirse como fallback para Suscripciones**: la documentación oficial de Webhooks ([mercadopago.com.ar/developers/es/docs/subscriptions/additional-content/your-integrations/notifications/webhooks](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/additional-content/your-integrations/notifications/webhooks)) declara explícitamente que ese método no está disponible para Suscripciones. El Slice 1 (§20) y el checklist (§21) reflejan esta restricción y no proponen ese mecanismo como solución por defecto.
- **`R-04` ya aparece correctamente en MEDIO** (§18), consistente con sus referencias previas en §1, §8.5, Slice 6 y checklist.
- **La bitácora reconoce el uso real de filtros**: §22 fue reescrito para mostrar los wrappers reales (`$out = ... 2>&1; $code = $LASTEXITCODE; $out | Out-File ...`, seguido de `Get-Content -Tail`, `Select-String`, `Select-Object`, `Where-Object` para inspección parcial) y declara explícitamente que no constituye una reproducción literal e íntegra de la salida de consola.
- **Los comandos Docker no demostrados fueron eliminados**: `docker compose build api` y `docker compose up -d api` no tienen evidencia de ejecución en esta sesión y se removieron de §22, junto con la afirmación de que la imagen fue reconstruida. La única verificación registrada es `docker ps`, que confirmó que los contenedores ya estaban corriendo. No se ejecutó ningún rebuild para justificar retroactivamente la afirmación anterior.
- **`git diff --check` no inspeccionó el documento untracked**: finalizó con `EXITCODE=0` únicamente para archivos trackeados; no valida el contenido de `docs/AUDITORIA_PANEL_ADMIN_ALINEACION_SISTEMA_REAL.md`, que permanece untracked (§23).
- **Resultado del escenario "MP cancela exitosamente → falla la escritura local"**: documentado en §11.8. `SubscriptionV2.status` y `Business.status` pueden permanecer sin cambios tras un rollback de la segunda transacción, incluso con `cancel_preapproval()` ya exitoso en MP. Un webhook posterior no corrige `Business.status` y depende de la entrega de notificaciones, no verificada (R-03). El test que promete cubrir este escenario no lo simula realmente. Registrado como **riesgo ALTO (R-16)**, sin recuperación demostrada.
- **Tests efectivamente ejecutados en esta actualización (con conteos reales y `EXITCODE`)**:
  | Suite | Resultado | EXITCODE |
  |---|---|---|
  | `test_admin_qr_reviews` | Ran 22, OK | 0 |
  | `test_pr2_admin_cancel_subscription` | Ran 49, OK | 0 |
  | `test_reconcile_session` | Ran 18, OK | 0 |
  | `test_webhook_signature` | Ran 9, OK | 0 |
  | `test_checkout_flow_v2` | Ran 24, FAILED (errors=20: 18 FieldError + 2 AttributeError) | 1 |
  | `test_mp_integration` | Ran 22, FAILED (errors=9) | 1 |
  | `test_subscriptionv2_birth_path` | Ran 22, FAILED (failures=4, errors=8) | 1 |
  | `test_admin_auth` + `test_admin_dashboard_and_client_tickets` | Ran 60, FAILED (failures=3) | 1 |
  | Frontend: `qr-reviews-card.test.tsx` + `url.test.ts` | 16 passed (12+4) | 0 |
- **Estado Git completo**: branch `develop`, HEAD `7e1ef92`, `origin/master` en `7446016`. `git status --short` solo muestra este documento como archivo nuevo (`??`); `git diff --stat` sin salida para archivos trackeados; `git diff --check` con `EXITCODE=0` para archivos trackeados, sin validar el documento untracked (§23).
- **Confirmación explícita**: durante esta actualización **no se modificó código, tests, configuración ni migraciones** — el único archivo alterado es `docs/AUDITORIA_PANEL_ADMIN_ALINEACION_SISTEMA_REAL.md`. **No se implementó ninguna remediación**; todos los slices de §20 describen objetivo, archivos y contrato esperado, sin código. No se ejecutó ningún test, build, Docker, instalación, commit, push ni deploy durante esta corrección.

---

*Actualización de la auditoría — 2026-08-04 · develop@7e1ef92 (post-merge origin/master@7446016 → develop) · Auditoría base reemplazada: 3e33830*
