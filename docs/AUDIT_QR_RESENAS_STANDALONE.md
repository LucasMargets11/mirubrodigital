# Auditoría Técnica: QR de Reseñas como Producto Independiente

**Fecha:** 2026-04-03  
**Alcance:** Monorepo Mi Rubro Digital — Análisis completo para separar QR de Reseñas de Carta Online  

---

## A. Resumen Ejecutivo

### Cómo está implementado hoy Menú QR / Carta Online

Menú QR es una **vertical completa** con 3 planes legacy (`menu_qr`, `menu_qr_visual`, `menu_qr_marca`) y 3 planes nuevos (`menu_qr_lite`, `menu_qr_pro`, `menu_qr_premium`). Incluye:

- **Editor de carta**: categorías, ítems, precios, imágenes (gated)
- **Branding**: logo, paleta de colores, tipografía
- **Página pública** en `/m/[slug]`
- **QR code generation** y enlaces compartibles
- **Engagement** (tips + reviews): configurado via `MenuEngagementSettings`, un OneToOne por business dentro de la app `menu`

### Dónde está mezclado hoy QR de Reseñas

La funcionalidad de reseñas está **acoplada a la app `menu`** en 3 niveles:

1. **Modelo**: `MenuEngagementSettings` (campo `reviews_enabled` + `google_place_id` + `google_review_url`) vive en `apps/menu/models.py`
2. **Feature flags**: `menu_qr_reviews` se define y se resuelve dentro del plan `menu_qr_*` en `business/features.py`
3. **UI pública**: La CTA de reseñas se renderiza dentro del componente `PublicMenuLayout` (`components/public-menu/menu-layout.tsx`), acoplada a la página pública de la carta (`/m/[slug]`)

**Dato clave**: Las reseñas NO almacenan datos locales — solo redirigen al formulario de reseñas de Google (`google_write_review_url`). No hay modelo `Review`, ni ratings, ni comentarios locales. Es un CTA externo.

### Principal recomendación arquitectónica

**Crear "QR de Reseñas" como un nuevo service_type (`qr_reviews`) reutilizando la infraestructura de billing, onboarding y engagement existente.** No es un módulo dentro de Carta Online ni un feature flag adicional — es un producto con su propio onboarding, pricing, dashboard y página pública de QR, que reutiliza el modelo `MenuEngagementSettings` (renombrado/generalizado) y la infraestructura de billing V2.

---

## B. Mapa de Acoplamientos

### Archivos donde existe dependencia entre Carta Online y Reseñas

| # | Archivo | Acoplamiento | Riesgo |
|---|---------|--------------|--------|
| 1 | `services/api/src/apps/menu/models.py` | `MenuEngagementSettings` (reviews + tips) vive dentro de la app `menu` | **ALTO** |
| 2 | `services/api/src/apps/menu/views.py` | Endpoints de engagement (`/engagement/`, `/engagement/upload-qr/`) dentro de menu views | **ALTO** |
| 3 | `services/api/src/apps/menu/serializers.py` | `MenuEngagementSettingsSerializer` valida reviews dentro del serializador de menu | **ALTO** |
| 4 | `services/api/src/apps/menu/urls.py` | Rutas de engagement bajo `/api/v1/menu/engagement/` | **ALTO** |
| 5 | `services/api/src/apps/menu/qr_entitlements.py` | `resolve_menu_qr_flags()` mezcla lógica de reviews/tips con lógica de menú | **ALTO** |
| 6 | `services/api/src/apps/business/features.py` | Feature keys `menu_qr_reviews`, `menu_qr_tips` hardcodeados en mapeo de planes QR | **MEDIO** |
| 7 | `services/api/src/apps/business/models.py` | `pro_included_module` + addon codes `menu_qr_addon_reviews/tips` | **MEDIO** |
| 8 | `services/api/src/apps/business/entitlements.py` | No tiene entitlements separados para reviews (se resuelve via feature flags) | **BAJO** |
| 9 | `apps/web/src/components/public-menu/menu-layout.tsx` | CTA de reseñas renderizada DENTRO de PublicMenuLayout | **ALTO** |
| 10 | `apps/web/src/components/app/engagement-settings-section.tsx` | Panel de configuración de reviews dentro de la sección de engagement del menú | **MEDIO** |
| 11 | `apps/web/src/features/menu/types.ts` | Tipos `MenuEngagementSettings` y `PublicMenuEngagement` en módulo menu | **MEDIO** |
| 12 | `apps/web/src/features/menu/api.ts` | Funciones de API de engagement en módulo menu | **MEDIO** |
| 13 | `apps/web/src/features/billing/data/menu-qr-catalog.ts` | Reviews aparece como feature de planes QR en catálogo de pricing | **BAJO** |
| 14 | `apps/web/src/features/billing/components/MenuQrPlanBuilder.tsx` | PRO module selector (reviews vs tips) | **BAJO** |
| 15 | `apps/web/src/features/billing/components/MenuQrComparisonTable.tsx` | Tabla de comparación incluye reviews como feature de menú QR | **BAJO** |
| 16 | `apps/web/src/components/navigation/sidebar.tsx` | Sección `MENU_QR` del sidebar incluye ítems de engagement | **MEDIO** |
| 17 | `apps/web/src/components/app/app-shell.tsx` | Route gate para `menu_qr` permite solo rutas de menú | **MEDIO** |
| 18 | `apps/web/src/lib/services/index.ts` | `SERVICE_ENTRY_ROUTES` solo tiene 3 servicios (gestion, restaurante, menu_qr) | **BAJO** |
| 19 | `apps/web/src/app/app/onboarding/servicio/page.tsx` | `SERVICE_OPTIONS` hardcodeada con 3 opciones | **BAJO** |
| 20 | `services/api/src/apps/accounts/onboarding_views.py` | `VALID_SERVICE_TYPES` hardcodeado a 3 valores | **BAJO** |
| 21 | `apps/web/src/app/(marketing)/pricing/page.tsx` | `SERVICE_OPTIONS` con 2 servicios publicados | **BAJO** |
| 22 | `apps/web/src/components/navigation/marketing-footer.tsx` | Link roto a `/services#qr_reviews` (sin anchor real) | **BAJO** |
| 23 | `services/api/src/apps/billing/runtime.py` | `_KNOWN_TIERS` no incluye tier de qr_reviews | **BAJO** |

---

## C. Alternativas de Implementación

### Alternativa 1: Separar QR de Reseñas como feature/entitlement dentro de la vertical Menú QR actual

**Descripción:** No crear un service_type nuevo. Crear un plan mínimo de Menú QR (ej. `menu_qr_reviews_only`) que incluya SOLO `menu_qr_reviews` + `public_menu` (sin `menu_builder`, sin items, sin branding completo). El negocio contrata "Menú QR" pero con un plan ultraliviano que solo habilita el QR de reseñas.

| Aspecto | Detalle |
|---------|---------|
| **Pros** | Mínimo cambio de schema; reutiliza todo el billing existente; no requiere nuevo service_type; no rompe nada |
| **Contras** | El producto se llama "Menú QR" comercialmente — confuso para el usuario que no quiere carta; la UX fuerza al usuario a estar en `/app/menu` aunque no use menú; el pricing page muestra features de carta que no aplican; el dashboard no es autónomo |
| **Impacto técnico** | Bajo — solo agregar plan nuevo en `features.py`, `entitlements.py`, y crear bundle |
| **Impacto UX** | **Negativo** — el usuario ve la UI de "Carta" cuando solo quiere reseñas |
| **Impacto billing** | Nulo — misma vertical, nuevo tier |
| **Complejidad** | Baja (~2-3 días) |
| **Riesgo regresión** | Bajo |

**Veredicto:** Solución rápida pero comercialmente débil. No cumple el objetivo de vender QR de Reseñas como producto independiente con identidad propia.

---

### Alternativa 2: Crear QR de Reseñas como service_type nuevo reutilizando infraestructura existente (RECOMENDADA)

**Descripción:** Agregar `qr_reviews` como nuevo `ServiceType` en el backend. Crear planes propios (ej. `qr_reviews_basic`, `qr_reviews_pro`). Reutilizar `MenuEngagementSettings` (o migrar a `EngagementSettings` compartido). Crear dashboard mínimo en `/app/resenas/`. Reutilizar la página pública de QR (`/q/[id]`) adaptada para reseñas standalone.

| Aspecto | Detalle |
|---------|---------|
| **Pros** | Identidad de producto clara; onboarding directo (el usuario elige "QR de Reseñas" al registrarse); pricing page propio; dashboard dedicado sin noise de carta; escalable para agregar funcionalidades futuras (analytics de reseñas, multi-plataforma, respuestas); ventas directas como producto standalone |
| **Contras** | Más archivos a tocar (~30-40); requiere nuevo sidebar section; requiere nueva sección en marketing |
| **Impacto técnico** | Medio — nuevo service_type en 6-8 enums/validaciones; nuevo entry route; nuevos bundles/modules; dashboard mínimo nuevo (`/app/resenas/`); adaptar engagement settings para funcionar sin menú |
| **Impacto UX** | **Positivo** — experiencia clear y enfocada; el usuario solo ve lo que contrató |
| **Impacto billing** | Bajo — SubscriptionV2 ya soporta múltiples service_types; solo crear bundles nuevos |
| **Complejidad** | Media (~2-3 semanas) |
| **Riesgo regresión** | Bajo — los cambios son aditivos; no se modifica lógica existente de Carta Online |

**Detalle técnico clave:** 
- `SubscriptionV2` ya soporta `service_type` como campo — agregar `qr_reviews` es un AlterField
- El constraint `unique_together(business, service_type)` para non-canceled subs ya existe → un negocio podría tener Carta Online Y QR de Reseñas como suscripciones separadas
- `build_business_context()` ya resuelve features por service_type → cambios mínimos
- La página pública del QR de reseñas puede ser simplemente `/r/[slug]` o reutilizar `/q/[id]` con un redirect

---

### Alternativa 3: Crear dominio nuevo aislado (`apps/reviews` o `apps/engagement`)

**Descripción:** Extraer `MenuEngagementSettings`, `TipTransaction`, `MercadoPagoConnection` a una nueva Django app `apps/engagement` (o `apps/reviews`). Crear modelos, vistas, serializers, URLs, todo independiente de `apps/menu`. El servicio "QR de Reseñas" usa exclusivamente esta app nueva.

| Aspecto | Detalle |
|---------|---------|
| **Pros** | Desacoplamiento total del dominio menu; si en el futuro se agrega reviews de múltiples fuentes (Google, TripAdvisor, Instagram), la app está preparada; DDD puro |
| **Contras** | **Rompe el sistema actual de Carta Online**: las views de engagement, la página pública del menú con CTA de reviews, y los endpoints de tips quedarían en una app diferente a la de menu → hay que refactorizar todas las importaciones; migración de datos compleja (mover tablas de menu a engagement); riesgo de downtime durante migración |
| **Impacto técnico** | Alto — crear app nueva, migrar modelos (SeparateDatabaseOperations), refactorizar imports en menu views/serializers, actualizar URLs |
| **Impacto UX** | Neutral — el usuario final no nota la diferencia |
| **Impacto billing** | Bajo — mismo patrón que Alt 2 |
| **Complejidad** | Alta (~4-6 semanas) |
| **Riesgo regresión** | **ALTO** — migración de modelos entre apps Django es riesgosa; hay que mantener backward compatibility en la app menu que hoy importa engagement models |

**Veredicto:** Over-engineering para la necesidad actual. El beneficio DDD no justifica el riesgo y complejidad. Se puede migrar a esta arquitectura en el futuro si el producto crece.

---

## D. Recomendación Final

### **Alternativa 2: Crear `qr_reviews` como service_type nuevo reutilizando infraestructura existente**

**Justificación:**

1. **Identidad de producto clara**: El usuario contrata "QR de Reseñas", ve un dashboard de reseñas, configura su Google Place ID, obtiene su QR y listo. No se contamina con UI de carta.

2. **Mínimo riesgo**: Todos los cambios son **aditivos**. No se modifica ningún flujo existente de Carta Online. Se agregan valores a enums, se crean bundles nuevos, se agrega una sección de frontend. Nada se rompe.

3. **Billing ya preparado**: `SubscriptionV2` ya maneja `service_type` como campo. Agregar un nuevo tipo es un `AlterField` + nuevo bundle. El onboarding ya soporta selección de servicio dinámico.

4. **Modelo de engagement reutilizable**: `MenuEngagementSettings` se puede reusar tal cual — ya tiene `reviews_enabled`, `google_place_id` y `google_review_url`. Solo se necesita que el modelo sea accesible sin requerir que el business tenga un menú activo. La relación es `business → engagement`, no `menu → engagement`.

5. **Escalabilidad**: Si mañana se quiere agregar "reviews de TripAdvisor", "reviews de Instagram", analytics de reputación, etc., el service_type `qr_reviews` ya existe como vertical y se le pueden agregar features sin tocar Carta Online.

6. **Sobre la Alternativa 3**: Extraer a una app Django separada sería ideal en un mundo de greenfield, pero el costo de migración de tablas entre apps Django (rename de tablas, update de content types, update de FKs) no se justifica ahora. Se puede hacer later si el dominio crece.

---

## E. Plan de Implementación por Fases

### Fase 1: Dominio y Modelado (Backend Foundation)
**Duración estimada: 2-3 días**

1. Agregar `QR_REVIEWS = 'qr_reviews'` a `Business.ServiceType` y `SubscriptionV2.ServiceType`
2. Agregar `QR_REVIEWS_BASIC = 'qr_reviews_basic'` y `QR_REVIEWS_PRO = 'qr_reviews_pro'` a `BusinessPlan`
3. Agregar feature keys nuevos en `FEATURE_KEYS`: `'qr_reviews_config'`, `'qr_reviews_analytics'`
4. Definir `PLAN_FEATURES` para los planes nuevos en `features.py`
5. Definir entitlements para el nuevo service en `entitlements.py`
6. Agregar `qr_reviews` a `SERVICE_CATALOG` en `service_catalog.py`
7. Agregar `'qr_reviews'` a `_KNOWN_TIERS` en `runtime.py`
8. Crear migration `business/0020_add_qr_reviews_service_type.py`
9. Crear migration `billing/0011_add_qr_reviews_plan_choices.py`
10. Asegurar que `MenuEngagementSettings` funcione sin que exista `PublicMenuConfig` (agregar método `ensure_engagement_standalone()` o reutilizar `ensure_menu_engagement()`)

### Fase 2: Billing y Entitlements
**Duración estimada: 2-3 días**

1. Crear módulos de billing (`Module`) para qr_reviews: `qr_reviews_core`, `qr_reviews_analytics`
2. Crear bundles (`Bundle`) con vertical `qr_reviews`: `qr_reviews_basic`, `qr_reviews_pro`
3. Crear registros de `Plan` (catálogo de checkout) para los planes nuevos
4. Actualizar `seed_billing.py` con los módulos y bundles nuevos
5. Actualizar `resolve_menu_qr_flags()` en `qr_entitlements.py` para que también soporte business con service_type `qr_reviews`
6. Agregar pricing en `commercial_plans.py` (o crear `qr_reviews_plans.py`)
7. Actualizar `feature_flags_for_plan()` y `feature_flags_for_v2_subscription()` para los planes nuevos
8. Crear demo accounts: `seed_qr_reviews_demo_accounts.py`

### Fase 3: Onboarding y Checkout
**Duración estimada: 2 días**

1. Agregar `'qr_reviews'` a `VALID_SERVICE_TYPES` en `onboarding_views.py`
2. Agregar nueva opción en frontend `SERVICE_OPTIONS` en `onboarding/servicio/page.tsx`
3. Agregar mapping `qr_reviews: 'qr_reviews'` en `verticalMap` en `onboarding/plan/page.tsx`
4. Crear `QrReviewsPlanBuilder.tsx` (componente de selección de plan para QR Reviews)
5. Actualizar lógica de `plan/page.tsx` para mostrar plan builder de QR Reviews cuando `vertical === 'qr_reviews'`
6. Verificar que el checkout flow (MercadoPago) funciona sin cambios — solo consume `plan_code` y `service_type`

### Fase 4: Dashboard y Rutas Autenticadas
**Duración estimada: 3-4 días**

1. Crear `/app/resenas/` con su layout.tsx y page.tsx (dashboard principal)
2. Crear `/app/resenas/configuracion/` — panel para configurar Google Place ID, ver QR, ver preview del link
3. Crear `/app/resenas/qr/` — generador de QR con download (PNG/SVG) y link para compartir
4. Crear `/app/resenas/analytics/` (plan PRO) — métricas básicas de escaneos
5. Agregar entry route `qr_reviews: '/app/resenas'` en `SERVICE_ENTRY_ROUTES`
6. Agregar sección `QR_REVIEWS` en `NAV_CONFIG` del sidebar:
   - Inicio (dashboard)
   - Configuración (Google Place ID)
   - QR y Enlaces
   - Analytics (gated por plan pro)
   - Cuenta (planes, facturación, config, soporte)
7. Agregar route gate para `qr_reviews` en `app-shell.tsx` (permitir solo `/app/resenas/*`, `/app/servicios`, `/app/planes`, `/app/settings*`)
8. Crear página pública `/r/[slug]/` (o reutilizar `/q/[id]`) que muestre solo el CTA de reseña Google — sin menú

### Fase 5: Marketing Site
**Duración estimada: 2-3 días**

1. Agregar `{ key: 'qr_reviews', label: 'QR de Reseñas' }` en `SERVICE_OPTIONS` de pricing
2. Crear `qr-reviews-catalog.ts` con features y planes
3. Crear `QrReviewsPlanBuilder.tsx` para pricing page
4. Crear `QrReviewsComparisonTable.tsx` (si aplica, o simplificar con lista de features)
5. Agregar sección en `/services` para QR de Reseñas (`#qr_reviews` anchor)
6. Fix footer link existente que ya apunta a `/services#qr_reviews`
7. Actualizar contact/support forms con producto "QR de Reseñas" en selectors

### Fase 6: Migraciones y Compatibilidad Retroactiva
**Duración estimada: 1-2 días**

1. Ejecutar migraciones en staging
2. Backfill: ningún negocio existente se ve afectado (cambios puramente aditivos)
3. Verificar que `backfill_subscriptions` no rompe con nuevo service_type
4. Verificar que `validate_phase3` sigue pasando
5. Seed demo accounts de QR Reviews
6. Verificar que `build_business_context()` resuelve correctamente para `qr_reviews`

### Fase 7: Testing
**Duración estimada: 2-3 días**

1. Tests backend:
   - Resolución de features para planes `qr_reviews_basic` y `qr_reviews_pro`
   - Onboarding con service_type `qr_reviews`
   - Checkout flow end-to-end (mock MP)
   - Engagement settings sin menú activo
   - `build_business_context()` para qr_reviews
   - Runtime resolve_subscription para qr_reviews
2. Tests frontend:
   - Onboarding service selection con 4 opciones
   - Plan builder de QR Reviews
   - Dashboard de QR Reviews
   - Sidebar sections correctas para cada service_type
   - Route gate para qr_reviews

---

## F. Archivos a Tocar

### Backend

#### Modificar:
| Archivo | Cambio |
|---------|--------|
| `services/api/src/apps/business/models.py` | Agregar `QR_REVIEWS` a ServiceType + BusinessPlan choices |
| `services/api/src/apps/billing/models.py` | Agregar `QR_REVIEWS` a SubscriptionV2.ServiceType |
| `services/api/src/apps/business/features.py` | Agregar PLAN_FEATURES para `qr_reviews_basic/pro` + feature keys |
| `services/api/src/apps/business/entitlements.py` | Agregar entitlements para plans qr_reviews |
| `services/api/src/apps/business/service_catalog.py` | Agregar ServiceDefinition para qr_reviews |
| `services/api/src/apps/billing/runtime.py` | Agregar `qr_reviews_basic/pro` a `_KNOWN_TIERS` |
| `services/api/src/apps/accounts/onboarding_views.py` | Agregar `'qr_reviews'` a `VALID_SERVICE_TYPES` |
| `services/api/src/apps/menu/qr_entitlements.py` | Extender `resolve_menu_qr_flags()` para soportar plans `qr_reviews_*` |
| `services/api/src/apps/menu/models.py` | Asegurar que `ensure_menu_engagement()` funcione standalone (sin PublicMenuConfig) |
| `services/api/src/apps/billing/management/commands/seed_billing.py` | Agregar módulos y bundles de qr_reviews |

#### Crear:
| Archivo | Propósito |
|---------|-----------|
| `services/api/src/apps/business/migrations/0020_add_qr_reviews_service.py` | Migration: nuevo ServiceType + BusinessPlan |
| `services/api/src/apps/billing/migrations/0011_qr_reviews_support.py` | Migration: SubscriptionV2 + Plan choices |
| `services/api/src/apps/billing/management/commands/seed_qr_reviews_demo_accounts.py` | Demo accounts |
| `services/api/src/apps/billing/qr_reviews_plans.py` (opcional) | Definición de planes y pricing |

### Frontend

#### Modificar:
| Archivo | Cambio |
|---------|--------|
| `apps/web/src/lib/services/index.ts` | Agregar `qr_reviews: '/app/resenas'` |
| `apps/web/src/app/app/onboarding/servicio/page.tsx` | Agregar opción QR de Reseñas |
| `apps/web/src/app/app/onboarding/plan/page.tsx` | Agregar `qr_reviews: 'qr_reviews'` en verticalMap |
| `apps/web/src/components/navigation/sidebar.tsx` | Agregar sección QR_REVIEWS en NAV_CONFIG |
| `apps/web/src/components/app/app-shell.tsx` | Agregar route gate para qr_reviews |
| `apps/web/src/app/(marketing)/pricing/page.tsx` | Agregar SERVICE_OPTION qr_reviews |
| `apps/web/src/app/(marketing)/services/page.tsx` | Agregar sección QR de Reseñas |
| `apps/web/src/components/navigation/marketing-footer.tsx` | Fix link `/services#qr_reviews` |
| `apps/web/src/app/(marketing)/soporte/_constants.ts` | Actualizar SUPPORT_TOPICS |
| `apps/web/src/app/(marketing)/contacto/_constants.ts` | Actualizar INQUIRY_OPTIONS |
| `apps/web/src/app/(marketing)/nosotros/_data.ts` | Actualizar PRODUCT_CARDS |
| `apps/web/src/lib/auth/types.ts` | Agregar `'qr_reviews'` al tipo de service |

#### Crear:
| Archivo | Propósito |
|---------|-----------|
| `apps/web/src/app/app/resenas/layout.tsx` | Layout de QR de Reseñas (guard + navigation) |
| `apps/web/src/app/app/resenas/page.tsx` | Dashboard principal |
| `apps/web/src/app/app/resenas/configuracion/page.tsx` | Configurar Google Place ID |
| `apps/web/src/app/app/resenas/qr/page.tsx` | Generador QR + link público |
| `apps/web/src/app/app/resenas/analytics/page.tsx` | Métricas (plan pro) |
| `apps/web/src/features/billing/data/qr-reviews-catalog.ts` | Catálogo de features por plan |
| `apps/web/src/features/billing/components/QrReviewsPlanBuilder.tsx` | Selector de plan |
| `apps/web/src/app/r/[slug]/page.tsx` | Página pública de QR de reseñas (redirect a Google) |

### Shared types/config
| Archivo | Cambio |
|---------|--------|
| `apps/web/src/types/billing.ts` | Agregar tipos para planes/service qr_reviews |
| `apps/web/src/features/menu/types.ts` | Reutilizar engagement types (sin cambio real, solo re-export) |

### Seeds / Demo data
| Archivo | Cambio |
|---------|--------|
| `services/api/src/apps/billing/management/commands/seed_billing.py` | Agregar modules + bundles qr_reviews |
| `services/api/src/apps/billing/management/commands/seed_qr_reviews_demo_accounts.py` | **CREAR**: Demo accounts |
| `services/api/src/apps/blog/management/commands/seed_blog_posts.py` | Ya tiene post sobre QR de reseñas (no cambiar) |

### Tests
| Archivo | Propósito |
|---------|-----------|
| `services/api/src/apps/billing/tests/test_qr_reviews_plans.py` | **CREAR**: Test resolución features/entitlements |
| `services/api/src/apps/accounts/tests/test_onboarding_qr_reviews.py` | **CREAR**: Test onboarding con service_type qr_reviews |
| `apps/web/src/__tests__/qr-reviews-onboarding.test.tsx` | **CREAR**: Test frontend onboarding |
| `apps/web/src/__tests__/qr-reviews-dashboard.test.tsx` | **CREAR**: Test dashboard routing |

---

## G. Riesgos y Compatibilidad

### Riesgos para clientes actuales
- **BAJO**: Todos los cambios son aditivos. No se modifica ningún plan existente, ningún feature flag existente, ningún flujo de Carta Online.
- La única área de cuidado es la función `ensure_menu_engagement()` que hoy asume un contexto de menú. Hay que verificar que funcione para un business sin `PublicMenuConfig`.

### Riesgos para suscripciones existentes
- **NULO**: Las suscripciones existentes no cambian. `SubscriptionV2` ya tiene `service_type` como campo, y agregar un nuevo valor al enum no afecta registros existentes.
- `backfill_subscriptions` seguirá funcionando (solo procesa subs existentes, no crea nuevos tipos).

### Riesgos para onboarding actual
- **BAJO**: Se agrega una opción al selector de servicios. El flujo servicio → plan → checkout es genérico y no tiene condiciones hardcodeadas por service_type.
- **Verificar**: Que el paso de checkout funcione correctamente con bundles de vertical `qr_reviews`.

### Riesgos de mezclar tenants con productos diferentes
- **NULO**: Un business tiene un service_type principal. Si un negocio tiene Carta Online y quiere también QR de Reseñas, la pregunta es: ¿debería poder tener dos suscripciones (una menu_qr + una qr_reviews)?
  - `SubscriptionV2` tiene constraint `unique(business, service_type)` para no cancelados → SÍ puede tener ambos productos activos simultáneamente.
  - Pero el `Business.service_type` (campo en el modelo) es uno solo. Esto ya se maneja con `enabled_services` en la sesión. Hay que verificar que la navegación soporte switching.

### Riesgos en permisos o navegación
- **BAJO**: El sidebar ya tiene patrones por service_type. Agregar `QR_REVIEWS` es aditivo.
- El route gate en `app-shell.tsx` necesita agregar `qr_reviews` con sus paths permitidos.
- **Cuidado**: Asegurar que un usuario con role `staff` en un business `qr_reviews` tenga los permisos mínimos (view_engagement, manage_engagement) correctamente mapeados.

---

## H. Dudas Abiertas

### Funcionales (requieren decisión de negocio)

1. **¿Puede un negocio tener tanto Carta Online como QR de Reseñas?**
   - Técnicamente sí (`SubscriptionV2` lo soporta). Pero el UX de switching entre servicios necesita revisión. Hoy `Business.service_type` determina el servicio "activo" y la UI cambia acorde.
   - **Recomendación**: Sí, permitirlo. Si tiene Carta Online con engagement, las reseñas ya están incluidas ahí. Si contrata QR de Reseñas standalone, queda como producto independiente.

2. **¿Cuántos planes para QR de Reseñas?**
   - Sugerencia: 2 planes.
   - **Básico** (~$10.000-15.000/mes): Google Place ID + QR + link público + 1 sucursal
   - **Pro** (~$25.000-30.000/mes): + analytics de escaneos + multi-branch + tips via MP (reutilizando la infra de tips)
   - O 1 plan simple por ahora y expandir después.

3. **¿El QR de Reseñas incluye tips (propinas) o no?**
   - Hoy tips y reviews están en el mismo modelo (`MenuEngagementSettings`). Si se quiere ofrecer tips en QR de Reseñas como feature separada, es sólo un feature flag.
   - **Recomendación**: El plan Básico NO incluye tips. El plan Pro SÍ incluye tips (como add-on natural de engagement post-servicio).

4. **¿Branding en la página pública de QR de Reseñas?**
   - Carta Online tiene branding (logo, colores, fonts). ¿QR de Reseñas tiene branding propio?
   - **Recomendación**: Básico sin branding (logo de Mi Rubro). Pro con branding simple (logo del negocio + color primario).

5. **¿Reviews de múltiples plataformas?**
   - Hoy solo Google. ¿Se planea agregar TripAdvisor, Yelp, Facebook, Instagram?
   - Esta decisión impacta si se necesita un modelo `ReviewPlatform` nuevo o si sigue siendo solo un campo `google_place_id`.

6. **¿Nombre de la página pública?**
   - Opciones: `/r/[slug]`, `/resena/[slug]`, o reutilizar `/q/[id]` con redirect condicional.
   - **Recomendación**: `/r/[slug]` (corto, memorable, independiente del slug de menú).

7. **¿El slug de QR de Reseñas es el mismo que el de Carta Online?**
   - Si un negocio tiene ambos productos, ¿usan el mismo slug (de `PublicMenuConfig`) o uno separado?
   - **Recomendación**: Slug separado. El business.slug puede funcionar como base, con una tabla de slugs por producto o simplemente reusar `business.slug` para `/r/` y el `PublicMenuConfig.slug` para `/m/`.

### Técnicas

8. **¿MenuEngagementSettings se renombra o se deja como está?**
   - Renombrarlo a `EngagementSettings` sería más limpio, pero implica rename de tabla en DB + actualizar imports.
   - **Recomendación**: Dejarlo como `MenuEngagementSettings` por ahora. La relación ya es `business → settings`, no `menu → settings`. El nombre es cosmético.

9. **¿Se necesita un modelo de analytics para escaneos de QR?**
   - Hoy no hay tracking de escaneos. Si el plan Pro lo incluye, hay que crear un modelo `QRScan` o similar.
   - Esto puede ir en una fase posterior.

10. **¿Cómo se genera el QR para QR de Reseñas standalone?**
    - El menú QR genera el QR apuntando a `/m/[slug]`. Para reseñas standalone, el QR apuntaría a `/r/[slug]` o directamente al link de Google.
    - **Recomendación**: QR apunta a `/r/[slug]` → página intermedia de Mi Rubro (con logo del negocio si plan Pro) → redirect a Google Reviews. Esto permite medir escaneos.

---

## Resumen de decisión

| Pregunta | Respuesta recomendada |
|----------|----------------------|
| ¿Cómo modelar? | Nuevo `service_type = 'qr_reviews'` |
| ¿Cuántos planes? | 2: Básico + Pro |
| ¿Se rompe Carta Online? | No, cambios 100% aditivos |
| ¿Se crea app Django nueva? | No, reutilizar `apps/menu` para engagement models |
| ¿Cuántos archivos nuevos? | ~12-15 nuevos |
| ¿Cuántos archivos a modificar? | ~20-25 |
| ¿Tiempo estimado total? | 2-3 semanas (incluyendo tests y marketing) |
| ¿Mayor riesgo? | Asegurar que engagement settings funcionen sin menú activo |
| ¿Mayor beneficio? | Producto vendible standalone desde día 1 con pricing, onboarding y dashboard propios |
