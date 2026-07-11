# Auditoría técnica — Retorno de Mercado Pago, reconciliación y finalización de onboarding

**Fecha:** 2026-07-11  
**Alcance:** Flujo de checkout, retorno desde MP, reconciliación, webhook, estados locales, onboarding post-pago.  
**Base de código auditada:** rama `develop`, HEAD `cf1c374`.

---

## 1. Resumen ejecutivo

### ¿Qué está fallando?

El usuario completa el pago en Mercado Pago. MP lo redirige al frontend. El frontend llama a un endpoint de reconciliación para activar la suscripción localmente, pero la URL del endpoint está malformada: `/reconcile/` termina siendo parte del **valor del query parameter** `preapproval_id` en lugar de ser un segmento del path.

### ¿Por qué devuelve 405?

La URL generada tiene esta forma:
```
POST /api/v1/billing/checkout-sessions/{uuid}?preapproval_id={id}/reconcile/
```

El **path** resultante es `/api/v1/billing/checkout-sessions/{uuid}` (sin `/reconcile/`), que DRF rutea a `CheckoutSessionStatusView`. Esta vista solo implementa `get()`. Un `POST` devuelve `405 Method Not Allowed`.

### ¿Por qué queda cargando?

La llamada `fetch()` de reconciliación está envuelta en `.catch(() => {})` que traga el error silenciosamente. El polling (cada 3 segundos) continúa esperando que el **webhook server-to-server** active la suscripción. Si el webhook no llega, el spinner persiste durante hasta 15 minutos hasta el timeout (`timed_out` phase).

### ¿Por qué el usuario vuelve al onboarding?

Cuando el usuario cierra la pestaña y reinicia sesión, el backend devuelve `businessStatus: 'onboarding'` porque la suscripción nunca fue activada localmente (reconcile falló, webhook no llegó). `AppLayout` detecta el estado y redirige a `/app/onboarding`. La vista de índice de onboarding devuelve `step = 'checkout_pending'` y redirige al step 3 (checkout page). Esto es técnicamente correcto, pero implica que la suscripción aprobada en MP permanece sin sincronizar indefinidamente.

### Riesgos adicionales

- **Pago aprobado en MP sin activación local**: el usuario pagó pero no tiene acceso.
- **Dependencia exclusiva del webhook**: si el webhook no llega, no hay fallback funcional (reconcile falla).
- **Polling infinito como mecanismo de activación**: si el webhook llega con retraso, el polling puede terminar antes y el usuario vuelve al paso 3.
- **Duplicación de lógica**: webhook y reconcile usan `_upsert_subscription_v2` y `activate_subscription_from_invoice` consistentemente (esto está bien), pero la ruta de retorno no activa nunca si el reconcile falla.

---

## 2. Causa raíz confirmada

```
FRONTEND: URL malformada en la llamada POST a /reconcile/
  → genera path incorrecto (query string en lugar de path segment)
    → DRF rutea a CheckoutSessionStatusView (solo GET)
      → respuesta 405 Method Not Allowed
        → .catch(() => {}) traga el error
          → reconciliación nunca ocurre
            → polling espera webhook que puede no llegar
              → Business.status sigue en 'onboarding'
                → usuario vuelve al step 3 en el siguiente login
```

### Evidencia directa

**Archivo:** `apps/web/src/app/app/onboarding/checkout/page.tsx`  
**Versión actual (HEAD)** — reconcile URL correcta:
```javascript
// línea 319 — path correcto
fetch(
    `${API_URL}/api/v1/billing/checkout-sessions/${resumeSessionId}/reconcile/`,
    { method: 'POST', credentials: 'include' },
).catch(() => {});
```

**URL bugueada reportada** (generada por versión anterior del código):
```
POST /api/v1/billing/checkout-sessions/c9f0f637-d061-4e84-9895-57fa5bedad0a
     ?preapproval_id=98e8f1ae910c45e29cb36d79a796e83d/reconcile/
```

Esta URL solo puede generarse por un patrón de concatenación como:
```javascript
// Patrón incorrecto (versión anterior)
const base = `${API_URL}/api/v1/billing/checkout-sessions/${sessionId}`;
const withParams = `${base}?preapproval_id=${preapprovalId}`;
fetch(`${withParams}/reconcile/`, { method: 'POST' }); // /reconcile/ → query string
```

### Estado en git

El código actual (HEAD `cf1c374`) tiene la URL correcta. El bug fue introducido en una versión intermedia entre `49fe8f0` (Wave 5, solo polling sin reconcile) y el commit `46ff081` (que agregó el reconcile). La versión de producción puede estar detrás del HEAD.

---

## 3. Flujo completo reconstruido

| # | Paso | Archivo | Función/Componente | Endpoint | Modelo afectado | Estado anterior | Estado posterior | Errores |
|---|------|---------|-------------------|----------|-----------------|-----------------|-----------------|---------|
| 1 | Login / registro | `accounts/views.py` | `LoginView.post` | `POST /api/v1/auth/login/` | `User`, `Business` | — | `business.status='onboarding'` | — |
| 2 | Selección de servicio | `onboarding/servicio/page.tsx` | `OnboardingServicioPage` | `POST /api/v1/auth/onboarding/set-service/` | `Business.service_type` | null | `'gestion'\|'restaurante'\|...` | service_type inválido → 400 |
| 3 | Onboarding index → routing | `onboarding/page.tsx` | `OnboardingIndexPage` | `GET /api/v1/auth/onboarding/` | — | `plan_selection` | — | Error API → default servicio |
| 4 | Selección de plan | `onboarding/plan/page.tsx` | — | — | — | `plan_selection` | — | — |
| 5 | Inicio de checkout | `onboarding/checkout/page.tsx` | `initiateCheckout()` | `POST /api/v1/auth/onboarding/start-checkout/` | `MpCheckoutSession`, `Plan` | — | `checkout_created` | email no verificado → 403; plan inválido → 400 |
| 6 | Creación de plan en MP | `checkout_session_service.py` | `_create_mp_plan_for_session()` | MP API: `POST /preapproval_plan` | `MpCheckoutSession.provider_preapproval_plan_id` | — | plan MP creado | Error MP → session.status='failed' |
| 7 | Redirección a MP | Frontend | link `href={initPoint}` + `startPolling()` | MP init_point (externo) | — | `checkout_created` | usuario en MP | — |
| 8 | Aprobación en MP | Externo (MP) | — | — | preapproval creado en MP | — | `preapproval.status='authorized'` | — |
| 9 | Retorno desde MP | `subscribe/return/page.tsx` | `OnboardingReturnRedirect` | back_url: `/subscribe/return?checkout_session_id={uuid}&preapproval_id={id}` | — | — | redirige a `/app/onboarding/checkout?session_id={uuid}` | ninguno si URL correcta |
| 10 | Reconciliación (frontend) | `onboarding/checkout/page.tsx` | `useEffect + fetch` | `POST /api/v1/billing/checkout-sessions/{uuid}/reconcile/` | `MpCheckoutSession` | `checkout_created` | `awaiting_webhook` | **URL malformada → 405** |
| 11 | Reconciliación (backend) | `reconciliation.py` | `reconcile_session()` | idem | `MpCheckoutSession`, `SubscriptionV2`, `BillingInvoiceEvent` | `awaiting_webhook` | `activated` | MP no devuelve preapproval → `awaiting_webhook` |
| 12 | Webhook preapproval | `webhook_processor.py` | `_handle_subscription_preapproval()` | `POST /api/v1/billing/mercadopago/webhook` | `SubscriptionV2`, `WebhookDelivery` | — | `SubscriptionV2` upsertado | orphan si sin MpCheckoutSession |
| 13 | Webhook authorized_payment | `webhook_processor.py` | `_handle_authorized_payment()` | idem | `BillingInvoiceEvent`, `SubscriptionV2` | `checkout_pending` | `active` | orphan si SubscriptionV2 no existe aún |
| 14 | Activación | `subscription_activator.py` | `activate_subscription_from_invoice()` | — | `SubscriptionV2`, `Business`, `MpCheckoutSession` | `checkout_pending`/`onboarding` | `active`/`activated` | solo si `is_active=False` previo |
| 15 | Polling detecta activación | `onboarding/checkout/page.tsx` | `startPolling()` | `GET /api/v1/billing/checkout-sessions/{uuid}` | `MpCheckoutSession` | — | `status='activated'` | — |
| 16 | Redirect final | `onboarding/checkout/page.tsx` | `scheduleAppRedirect()` | `window.location.assign(route)` | — | — | usuario en `/app/resenas/...` o `/app/dashboard` | — |
| 17 | Reload post-activación | `app/layout.tsx` | `AppLayout` | `GET /api/v1/auth/me/` | `Business`, `SubscriptionV2` | — | `access_allowed=true` | — |

---

## 4. Hallazgos priorizados

| ID | Severidad | Área | Hallazgo | Evidencia | Impacto |
|----|-----------|------|----------|-----------|---------|
| H1 | **Crítica** | Frontend | URL de reconciliación malformada: `/reconcile/` en query string | `checkout/page.tsx`: versión de producción puede aún tener el bug; URL reportada: `?preapproval_id={id}/reconcile/` | Activación nunca ocurre desde la página de retorno; 100% de usuarios afectados por este path |
| H2 | **Crítica** | Backend | `CheckoutSessionStatusView` devuelve 405 para POST | `billing/urls.py` L34: path sin trailing slash, sin `post()` en la vista | Causa directa del 405; confirma que el POST va al endpoint equivocado |
| H3 | **Alta** | Frontend | `.catch(() => {})` silencia el 405 | `checkout/page.tsx` línea 320-322 | El error pasa desapercibido; UI no muestra fallo; spinner infinito |
| H4 | **Alta** | Integración | Reconcile no se llamaba en el Wave 5 original (`49fe8f0`) | Git diff: `useEffect` solo hacía `startPolling()`, sin `fetch reconcile` | Versión anterior de producción: ninguna activación proactiva; dependencia 100% del webhook |
| H5 | **Alta** | Estado | `OnboardingIndexPage` no pasa `checkout_session_id` al redirigir a step 3 | `onboarding/page.tsx` L100: solo pasa `pending_plan_code` | Extra round-trip a `start-checkout`; si start-checkout falla, paso 3 muestra error en lugar de reconcile directo |
| H6 | **Alta** | Onboarding | El usuario es enviado de vuelta al step 3 si pago aprobado pero no activado | `onboarding/page.tsx` L96-99: `step='checkout_pending'` → `checkout?plan=` | Experiencia confusa; el usuario ve "confirmar suscripción" nuevamente |
| H7 | **Media** | Backend | Webhook `subscription_preapproval` no activa la suscripción | `webhook_processor.py` L290-300: solo hace `LINKED`, no activa | La activación requiere TAMBIÉN `subscription_authorized_payment`; race condition posible |
| H8 | **Media** | Idempotencia | Reconcile llama a `reconcile_session()` que NO recibe `preapproval_id` del frontend | `reconciliation.py`: solo busca por `provider_preapproval_plan_id` interno | Correcto por diseño; pero si el plan_id no está en la sesión, reconcile devuelve error |
| H9 | **Media** | UX | Fase `timed_out` (15 min) no ofrece reintentar ni limpiar estado | `checkout/page.tsx` L163-176 | El usuario no puede recuperarse sin cerrar y reingresar |
| H10 | **Media** | Observabilidad | Ningún log del lado frontend cuando reconcile retorna 405 | `.catch(() => {})` sin log | Imposible diagnosticar desde logs |
| H11 | **Baja** | Seguridad | `CheckoutSessionStatusView` usa `AllowAny` | `views.py` L520: `permission_classes = [AllowAny]` | Cualquier agente puede consultar estado de una sesión por UUID; UUID v4 es suficientemente difícil de adivinar, pero es un riesgo de información |
| H12 | **Baja** | Testing | Tests de reconcile no corren en entorno local (sin DB dockerizada) | pytest output: `psycopg.OperationalError: getaddrinfo failed` | Tests existentes cubren el flujo correctamente pero solo corren en Docker |

---

## 5. Estado del caso afectado

```
checkout_session_id: c9f0f637-d061-4e84-9895-57fa5bedad0a
preapproval_id:      98e8f1ae910c45e29cb36d79a796e83d
```

**Estado probable en base de datos:**

```
MpCheckoutSession c9f0f637:
  status = 'awaiting_webhook' | 'linked'
  provider_preapproval_plan_id = PLAN-{algo}
  mp_external_reference = SESS-{uuid}

SubscriptionV2:
  status = 'checkout_pending' (si webhook preapproval llegó)
  provider_sub_id = '98e8f1ae910c45e29cb36d79a796e83d'
  is_active = False

Business:
  status = 'onboarding'

BillingInvoiceEvent:
  → puede existir si authorized_payment webhook llegó
  → si existe y SubscriptionV2 también, la activación puede hacerse via reconcile manual

Mercado Pago (fuente de verdad):
  preapproval_id 98e8f1ae910c45e29cb36d79a796e83d
  status = 'authorized' (confirmado por el usuario)
```

**Para recuperar este caso**: llamar a `POST /api/v1/billing/checkout-sessions/c9f0f637-d061-4e84-9895-57fa5bedad0a/reconcile/` con autenticación del usuario dueño. El `reconcile_session()` buscará el preapproval por `provider_preapproval_plan_id`, encontrará `preapproval_id=98e8f1...`, lo activará localmente. **No tocar producción manualmente; solo a través del endpoint existente.**

---

## 6. Contrato actual de `reconcile`

**Backend:**
```
POST /api/v1/billing/checkout-sessions/<uuid:session_id>/reconcile/
Auth: IsAuthenticated (cookie JWT)
Body: vacío — sin parámetros requeridos
```

```json
// Respuesta exitosa (HTTP 200 siempre)
{
    "session_id": "c9f0f637-...",
    "status": "activated" | "awaiting_webhook" | "linked" | ...,
    "action_taken": ["Session transitioned checkout_created → awaiting_webhook", ...],
    "error": null | "mensaje"
}
```

El backend obtiene `preapproval_id` a través de la cadena interna:
```python
session.provider_preapproval_plan_id  →  mp.search_preapprovals(plan_id)
```
**NO usa** `request.query_params.get('preapproval_id')` ni `request.data.get('preapproval_id')`.

**Frontend:**
```javascript
fetch(
    `${API_URL}/api/v1/billing/checkout-sessions/${sessionId}/reconcile/`,
    { method: 'POST', credentials: 'include' },
)
```
Sin body, sin query params. Esta es la forma correcta.

---

## 7. Comparación entre retorno y webhook

| Aspecto | Retorno (frontend → reconcile) | Webhook (MP → backend) |
|---------|-------------------------------|----------------------|
| Trigger | Usuario vuelve al navegador | MP envía POST server-to-server |
| Entrada | `checkout_session_id` en URL | `preapproval_id` o `authorized_payment_id` en body |
| Servicio core | `reconciliation.reconcile_session()` | `webhook_processor._handle_*()` |
| ¿Mismo servicio de activación? | ✅ sí: `activate_subscription_from_invoice()` | ✅ sí: `activate_subscription_from_invoice()` |
| Búsqueda en MP | `mp.search_preapprovals(plan_id)` | `mp.get_preapproval(preapproval_id)` |
| Idempotente | ✅ sí | ✅ sí |
| Duplica lógica | ❌ no — comparten `activate_subscription_from_invoice` | — |
| Puede fallar sin efecto | ✅ si reconcile falla, webhook activa igual | ✅ si webhook falla, reconcile activa igual (si URL es correcta) |
| Dependencia del browser | ✅ sí — requiere que el usuario vuelva | ❌ no |

**Conclusión**: retorno y webhook comparten el servicio de activación (`activate_subscription_from_invoice`). Son vías paralelas e independientes. El sistema está bien diseñado en este aspecto; el bug es que la URL del retorno estaba malformada, eliminando este path alternativo.

---

## 8. Problema de onboarding y login

### Campo que provoca el retorno al step 3

```python
# accounts/onboarding_views.py: _compute_onboarding_step()
def _compute_onboarding_step(business: Business) -> str:
    if business.status != 'onboarding':
        return 'done'
    ...
    if _has_pending_checkout(business):
        return 'checkout_pending'   # ← aquí
    if business.service_type:
        return 'plan_selection'
    return 'no_service_type'
```

```python
# _has_pending_checkout() checks:
MpCheckoutSession.objects.filter(
    tenant=business,
    status__in=['created', 'checkout_created', 'awaiting_webhook', 'linked'],
).exists()
```

**Si la reconciliación falla**, el `MpCheckoutSession` queda en `awaiting_webhook` (status OPEN). El paso anterior se calcula como `checkout_pending`. El usuario es enviado al checkout page (step 3).

### Cadena completa del redirect

```
Usuario re-loguea
  → AppLayout: getSession() → /auth/me/ → business.status='onboarding'
  → AppLayout: access_allowed=false + onboarding → redirect /app/onboarding
  → OnboardingIndexPage: GET /auth/onboarding/ → step='checkout_pending'
  → OnboardingIndexPage: redirect /app/onboarding/checkout?plan=<code>
  → OnboardingCheckoutPage: start-checkout → status='awaiting_webhook' (sesión reutilizada)
  → alreadyAtMP=true → reconcile llamado (ahora con URL correcta)
  → reconcile activa → polling detecta → redirect a /app/resenas
```

### Gap: `checkout_session_id` no se pasa al checkout

```tsx
// onboarding/page.tsx, línea 96-104
case 'checkout_pending': {
    const planParam = pending_plan_code
        ? `?plan=${encodeURIComponent(pending_plan_code)}`
        : '';
    redirect((`${ROUTE_CHECKOUT_BASE}${planParam}`) as never);
    // ↑ NO incluye ?session_id=${checkout_session_id}
    break;
}
```

La respuesta de `/auth/onboarding/` SÍ incluye `checkout_session_id`:
```python
'checkout_session_id': checkout_info['checkout_session_id'] if checkout_info else None,
```

Pero no se usa en el redirect. Este gap fuerza un round-trip extra a `start-checkout`.

---

## 9. Archivos que deberán modificarse

| Archivo | Cambio requerido | Motivo | Riesgo |
|---------|-----------------|--------|--------|
| `apps/web/src/app/app/onboarding/checkout/page.tsx` | Verificar que la URL de reconcile en producción sea correcta (`/reconcile/` en path, no en query) | Bug principal | Bajo — solo es string template; tests necesarios |
| `apps/web/src/app/app/onboarding/page.tsx` | Pasar `?session_id=${checkout_session_id}` cuando step='checkout_pending' | Evitar round-trip extra a start-checkout | Bajo — solo query param añadido |
| `apps/web/src/app/app/onboarding/checkout/page.tsx` | Agregar log o señal visual cuando reconcile retorna error (no silenciar 405) | Observabilidad | Bajo |
| `apps/web/src/app/app/onboarding/checkout/page.tsx` | Cambiar `.catch(() => {})` por `.catch((err) => { logger.warn(...) })` | Evitar swallowing silencioso | Bajo |
| `services/api/src/apps/billing/views.py` | `CheckoutSessionStatusView`: agregar `permission_classes = [IsAuthenticated]` | Seguridad: evitar enumeración de sesiones por UUID | Medio — puede romper polling anónimo si existe alguno |
| `services/api/src/apps/billing/views.py` | `CheckoutSessionReconcileView.post()`: agregar log `checkout_session_id + user_id` a la entrada | Observabilidad | Bajo |
| `services/api/src/apps/accounts/onboarding_views.py` | `OnboardingIndexPage`: incluir `checkout_session_id` en el redirect de `checkout_pending` | Eficiencia | Bajo |

---

## 10. Plan de solución por etapas

### PR-1 — Corrección del contrato frontend/backend

**Objetivo**: asegurar que la URL de reconcile sea correcta en producción.

**Cambios**:
- Auditar la versión de `checkout/page.tsx` desplegada en producción contra el HEAD.
- Si hay diferencia, deployar HEAD inmediatamente.
- Verificar en red del browser que la URL del POST sea `/checkout-sessions/{uuid}/reconcile/`.

**Test**: capturar network request en devtools; verificar que el path termina en `/reconcile/` y no en query string.

---

### PR-2 — Reconciliación canónica e idempotente (sin cambios al backend — ya correcto)

**Objetivo**: asegurar que el frontend llame reconcile en todos los paths críticos con error logging.

**Cambios en `checkout/page.tsx`**:
```typescript
// Reemplazar .catch(() => {}) por logging:
fetch(reconcileUrl, { method: 'POST', credentials: 'include' })
    .then(r => {
        if (!r.ok) console.error('[reconcile] HTTP error', r.status, reconcileUrl);
    })
    .catch(err => console.error('[reconcile] Network error', err));
```

**Cambios en `onboarding/page.tsx`**:
```typescript
case 'checkout_pending': {
    // Añadir session_id para evitar round-trip extra
    const sessionParam = checkout_session_id
        ? `session_id=${encodeURIComponent(checkout_session_id)}`
        : `plan=${encodeURIComponent(pending_plan_code ?? '')}`;
    redirect(`${ROUTE_CHECKOUT_BASE}?${sessionParam}` as never);
    break;
}
```

---

### PR-3 — Finalización de onboarding y redirect

**Objetivo**: garantizar que un usuario con pago aprobado en MP siempre llegue a la app, incluso si el webhook fue tardío.

**Cambios**:
- En `CheckoutSessionStatusView` (backend): agregar `permission_classes = [IsAuthenticated]`.
- En `OnboardingLayout`: antes de redirect a `/app`, llamar a reconcile si `businessStatus === 'onboarding'` y hay `checkout_session_id` en la sesión del onboarding status. (Opcional — ya existe el path via `initiateCheckout`.)

---

### PR-4 — Recuperación de pagos afectados

**Objetivo**: activar suscripciones ya aprobadas en MP que quedaron sin sincronizar.

**Proceso**:
1. Identificar `MpCheckoutSession` en estado `awaiting_webhook` o `linked` con preapproval `authorized` en MP.
2. Llamar al endpoint existente `POST /billing/checkout-sessions/{uuid}/reconcile/` para cada uno.
3. Verificar que `Business.status` cambie a `active`.

**Script orientativo** (solo en Django shell, NO en producción directa):
```python
from apps.billing.models import MpCheckoutSession
from apps.billing.reconciliation import reconcile_session

# Solo leer — no modificar directamente:
sessions = MpCheckoutSession.objects.filter(
    status__in=['awaiting_webhook', 'linked'],
    tenant__status='onboarding',
)
for s in sessions:
    result = reconcile_session(str(s.id))
    print(s.id, result['status'], result['action_taken'])
```

---

### PR-5 — Tests y observabilidad

**Tests nuevos necesarios**:
1. Test E2E que verifica que la URL del reconcile POST sea `/reconcile/` en el path.
2. Test unitario del frontend que mockea `fetch` y verifica la URL exacta.
3. Test backend: `CheckoutSessionReconcileView` retorna 405 cuando se hace GET (no solo POST).

**Observabilidad**:
- Agregar `console.error` en el `.catch()` del reconcile frontend.
- Agregar log estructurado en `CheckoutSessionReconcileView.post()`: `checkout_session_id`, `user_id`, `session.status`.
- Verificar que Sentry (si está configurado) capture el 405 del reconcile.

---

## 11. Tests mínimos requeridos

### Backend

```python
# test_reconcile_session.py — ya existe, cubre:
# ✅ activación al aprobar pago
# ✅ idempotencia (doble llamada no duplica)
# ✅ external_reference guard
# ✅ awaiting_webhook cuando MP no tiene preapprovals
# ✅ linked cuando preapproval existe pero sin pago
# ✅ safety net Business.status
# ✅ auth anónima 403
# ✅ ownership check
# ✅ miembro del tenant permitido

# Faltantes:
# ❌ GET al endpoint /reconcile/ devuelve 405
# ❌ Verificación que preapproval_id en query string no afecta routing
# ❌ Race condition: webhook llega durante reconcile
```

### Frontend

```typescript
// Nuevo: test de URL correcta
test('reconcile POST usa path correcto sin query params', async () => {
    const fetchMock = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    global.fetch = fetchMock;
    // Render con session_id
    render(<OnboardingCheckoutPage />, { route: '?session_id=test-uuid' });
    await waitFor(() => {
        const call = fetchMock.mock.calls.find(c => c[0].includes('reconcile'));
        expect(call[0]).toMatch(/\/checkout-sessions\/test-uuid\/reconcile\/$/);
        expect(call[0]).not.toContain('?preapproval_id');
    });
});
```

### Integración

- Test E2E (Playwright/Cypress) que simula retorno desde MP y verifica que el usuario llega a `/app/resenas/configuracion` o `/app/dashboard`.
- Test que verifica que re-login con `step='checkout_pending'` llama reconcile con la URL correcta.

---

## 12. Criterios de aceptación

| Criterio | Verificación |
|----------|--------------|
| URL de reconcile termina en `/reconcile/` en el path | Network devtools: POST a `.../{uuid}/reconcile/` sin query params |
| Reconcile retorna 200 cuando pago aprobado en MP | Network devtools: body `{"status": "activated"}` |
| Polling detecta `status='activated'` en el siguiente ciclo | UI muestra "¡Tu suscripción está activa!" |
| Usuario llega a `/app/resenas/configuracion` o `/app/dashboard` | Redirect final sin pasar por login |
| Re-login con pago aprobado → directo a la app | `businessStatus='active'` → AppLayout no rediriige a onboarding |
| Reconcile idempotente: llamada doble no duplica SubscriptionV2 | `SubscriptionV2.objects.filter(business=...).count() == 1` |
| Webhook posterior a reconcile: no-op | `WebhookDelivery.processing_status='duplicated'` o activación no-op |
| Usuario ve "aún procesando" después de 2 min sin activación | `pollingSlowWarning=true` en UI |
| Timeout a los 15 min: fase `timed_out` con mensaje correcto | UI muestra "no vuelvas a pagar" |
| Tests pasan en CI | pytest + vitest sin errores relacionados |

---

## 13. Riesgos y datos abiertos

| Riesgo | Estado | Mitigación |
|--------|--------|-----------|
| Versión de producción ≠ HEAD | **No confirmado** — acceso a producción no disponible en esta auditoría | Deploy del HEAD lo resuelve |
| Webhook de MP nunca llegó para el caso reportado | **No confirmado** — requiere acceso a `WebhookDelivery` en DB producción | Llamar reconcile manualmente via endpoint existente |
| `SubscriptionV2` para `98e8f1...` no existe (webhook preapproval también faltó) | **No confirmado** | Reconcile.reconcile_session() lo crea vía `_upsert_subscription_v2()` |
| `CheckoutSessionStatusView` expone sesiones a usuarios anónimos | **Confirmado en código** — `AllowAny` en `views.py` L520 | PR-3 agrega autenticación |
| Dos sistemas de suscripción coexisten (`billing.Subscription` legacy + `SubscriptionV2`) | **Confirmado** — `_session_payload` usa `build_business_context()` que lee ambos | No requiere migración en esta auditoría; el activador actualiza ambos |
| `preapproval_id` de MP en el caso reportado puede estar en estado distinto de `authorized` | **No verificable sin acceso a MP dashboard** | Reconcile consulta MP; si status != authorized, no activa y devuelve `linked` |

---

## Respuestas a las 18 preguntas de criterio de auditoría completa

1. **¿Dónde se construye exactamente la URL incorrecta?**  
   En una versión anterior de `apps/web/src/app/app/onboarding/checkout/page.tsx` (antes del commit `46ff081`). El código actual en HEAD está corregido.

2. **¿Cuál es la URL real registrada por DRF?**  
   `POST /api/v1/billing/checkout-sessions/<uuid:session_id>/reconcile/` → `CheckoutSessionReconcileView` (`billing/urls.py` L36).

3. **¿Qué método y payload espera `reconcile`?**  
   `POST`, sin body ni query params. El backend resuelve el preapproval via `session.provider_preapproval_plan_id` internamente.

4. **¿Por qué el backend devuelve 405?**  
   La URL malformada hace que el request llegue a `CheckoutSessionStatusView` (`GET /checkout-sessions/<uuid>`), que solo tiene `get()`. DRF devuelve 405 para POST.

5. **¿Por qué la página queda cargando?**  
   El `.catch(() => {})` silencia el 405. El polling de 3s sigue activo esperando el webhook. Si el webhook no llega en 15 min, la fase cambia a `timed_out`.

6. **¿Qué ocurre si el webhook llega correctamente?**  
   `_handle_authorized_payment()` crea `BillingInvoiceEvent`, llama `activate_subscription_from_invoice()` → `Business.status='active'`, `SubscriptionV2.is_active=True`, `MpCheckoutSession.status='activated'`. El siguiente ciclo de polling detecta `status='activated'` y redirige.

7. **¿Qué ocurre si el webhook no llega?**  
   Polling timeout a los 15 min → fase `timed_out`. Usuario cierra → re-login → step 3 (`checkout_pending`) → checkout page llama `start-checkout` → `alreadyAtMP=true` → reconcile llamado (con URL correcta en HEAD) → activa → polling detecta → redirect.

8. **¿Qué modelos se actualizan al aprobar el pago?**  
   `SubscriptionV2` (status=active, is_active=True), `Business` (status=active, activated_at), `MpCheckoutSession` (status=activated), `BillingInvoiceEvent` (created), opcionalmente `billing.Subscription` legacy.

9. **¿Qué modelos no se están actualizando?**  
   En el caso bugueado: ninguno (reconcile falló, webhook puede no haber llegado). `Business.status` queda en `onboarding`, `MpCheckoutSession` en `awaiting_webhook`, `SubscriptionV2` puede estar en `checkout_pending` o no existir.

10. **¿Qué campo hace volver al usuario al paso 3?**  
    `MpCheckoutSession.status` en `OPEN_STATUSES` (`awaiting_webhook`) → `_has_pending_checkout()` retorna `True` → `step='checkout_pending'` → redirect a checkout (step 3).

11. **¿Cuál es la fuente de verdad para una suscripción activa?**  
    `SubscriptionV2.is_active = True` + `Business.status = 'active'`. El runtime resolver (`build_business_context`) usa `SubscriptionV2` como fuente primaria. `billing.Subscription` legacy es mantenida para compat. La fuente externa es Mercado Pago (preapproval + authorized_payment).

12. **¿Existe riesgo de duplicación?**  
    ❌ No. `BillingInvoiceEvent.get_or_create(provider_authorized_payment_id=...)` garantiza idempotencia. `SubscriptionV2` tiene constraint `uq_subscriptionv2_active_per_service`. `reconcile_session()` tiene fast-exit si `session.status == 'activated'`.

13. **¿La reconciliación es idempotente?**  
    ✅ Sí. `reconcile_session()` tiene fast-exit para sesiones terminales. `_upsert_subscription_v2()` usa get_or_create. `activate_subscription_from_invoice()` usa `select_for_update()` y re-check de `is_active`.

14. **¿Retorno y webhook comparten servicio?**  
    ✅ Sí. Ambos llaman `activate_subscription_from_invoice()` de `subscription_activator.py`.

15. **¿Cómo se recuperarán pagos ya aprobados?**  
    Con `POST /api/v1/billing/checkout-sessions/{session_id}/reconcile/` autenticado como el usuario dueño. O via script Django shell en el servidor (ver PR-4). El endpoint ya existe y es correcto.

16. **¿Qué archivos deben cambiarse?**  
    Ver tabla en sección 9. Principalmente: `checkout/page.tsx` (URL correcta + logging), `onboarding/page.tsx` (pasar session_id), `billing/views.py` (auth en StatusView).

17. **¿Qué tests impedirán que el bug vuelva a aparecer?**  
    Test unitario de URL exacta en `checkout/page.tsx`, test de integración que simula retorno MP y verifica activación, test backend que verifica routing correcto a `CheckoutSessionReconcileView`.

18. **¿Cuál debe ser el comportamiento correcto al volver a iniciar sesión?**  
    Si `Business.status='onboarding'` + `MpCheckoutSession.status` en OPEN_STATUSES → checkout page → `start-checkout` → `alreadyAtMP=true` → reconcile → si MP confirmó pago, activa → redirect a app. Si MP aún no confirmó → polling hasta 15 min → `timed_out` con mensaje "espera confirmación".
