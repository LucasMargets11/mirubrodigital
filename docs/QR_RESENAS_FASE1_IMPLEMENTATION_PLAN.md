# QR de Reseñas — Fase 1: Plan de Implementación Técnico

**Fecha:** 2026-04-03  
**Basado en:** [AUDIT_QR_RESENAS_STANDALONE.md](AUDIT_QR_RESENAS_STANDALONE.md)  
**Alcance:** Modelado base + Billing base + Onboarding base + Routing base + Compatibilidad Menu QR

---

## A. Decisiones de Implementación

### 1. ¿1 plan o 2 planes en V1?

**→ 1 plan único: `qr_reviews`**

Justificación:
- No hay funcionalidad diferencial para justificar 2 tiers todavía. No hay analytics, no hay tips, no hay multi-branch.
- 1 plan simplifica enormemente el seed, el pricing, el plan builder frontend y el checkout.
- Cuando haya features pro (analytics de escaneos, multi-plataforma, tips) se agrega un segundo plan.
- Precio sugerido: ARS $15.000/mes (el producto más barato del catálogo, por debajo de QR Lite $18.000).

### 2. ¿`/app/resenas` como ruta autenticada?

**→ Sí, `/app/resenas`**

Es corto, claro, no colisiona con ninguna ruta existente. El pattern ya existe con `/app/gestion/` y `/app/menu/`.

### 3. ¿`/r/[slug]` como ruta pública?

**→ Sí, `/r/[slug]`**

Paralelo a `/m/[slug]` para menú. Corto, memorable. La página es una landing intermedia que muestra logo del negocio (usando business.name, sin branding avanzado en V1) y redirige a Google Reviews.

### 4. ¿Dejar `MenuEngagementSettings` con ese nombre?

**→ Sí, dejarlo como está**

El campo ya es `business → settings` (FK a Business, no a Menu). Renombrarlo implica rename de tabla SQL + actualizar content types + refactorizar imports. Cero valor para V1. Nota: para QR de Reseñas standalone no se requiere que exista `PublicMenuConfig` — solo se necesita que exista `MenuEngagementSettings` con `reviews_enabled=True` y `google_place_id` seteado.

### 5. ¿Coexistencia `menu_qr` + `qr_reviews` en el mismo business desde V1?

**→ No en V1**

Razones:
- `Business.service_type` es un campo único — no soporta múltiples servicios activos naturalmente.
- `enabled_services()` + sidebar + routing dependen de un service activo.
- Soportar multi-service requiere cambiar `Business.service_type` a M2M o agregar un switching UX. Es scope de V2.
- En V1: si un negocio ya tiene Carta Online con reviews, no necesita contratar QR de Reseñas separado. Los usuarios nuevos eligen UNO de los dos al onboardear.

**Corrección respecto a la auditoría**: La auditoría sugería que `SubscriptionV2` soporta múltiples service_types por su unique constraint `(business, service_type)`. Técnicamente la tabla sí, pero el frontend (sidebar, routing, dashboard) no. Lo habilitamos después cuando haya UX de switching.

---

## B. Orden Exacto de Ejecución

```
 PR1  │ 1. Agregar enums/choices en modelos backend
      │ 2. Crear migraciones Django
      │ 3. Verificar que migraciones corren sin romper nada
      │
 PR2  │ 4. Agregar PLAN_FEATURES para qr_reviews en features.py
      │ 5. Agregar qr_reviews a service_catalog.py
      │ 6. Agregar qr_reviews a _KNOWN_TIERS en runtime.py
      │ 7. Agregar qr_reviews a entitlements.py (mínimo)
      │ 8. Agregar módulos + bundle + Plan en seed_billing.py
      │ 9. Correr seed_billing y verificar
      │
 PR3  │ 10. Agregar 'qr_reviews' a VALID_SERVICE_TYPES (onboarding backend)
      │ 11. Agregar opción en onboarding/servicio frontend
      │ 12. Agregar verticalMap en onboarding/plan frontend
      │ 13. Agregar SERVICE_LABELS en sidebar
      │ 14. Agregar entry route en lib/services/index.ts
      │ 15. Agregar section qr_reviews en NAV_CONFIG del sidebar
      │ 16. Agregar qr_reviews paths en app-shell.tsx route gate
      │
 PR4  │ 17. Crear /app/resenas/layout.tsx (guard)
      │ 18. Crear /app/resenas/page.tsx (dashboard mínimo)
      │ 19. Crear /app/resenas/configuracion/page.tsx (Google Place ID)
      │ 20. Crear /app/resenas/qr/page.tsx (ver QR + link)
      │ 21. Crear /r/[slug]/page.tsx (página pública)
      │
 PR5  │ 22. Tests backend (features, runtime, onboarding)
      │ 23. Tests frontend (onboarding, routing)
      │ 24. Seed demo account para QR Reviews
```

---

## C. Cambios Exactos Archivo por Archivo

### PR1: Enums + Migraciones

---

#### C1. `services/api/src/apps/business/models.py`

**Objetivo:** Agregar `qr_reviews` como ServiceType y BusinessPlan válidos.

**Cambio 1 — SERVICE_CHOICES** (línea ~10):
```python
SERVICE_CHOICES = [
    ('gestion', 'Gestion Comercial'),
    ('restaurante', 'Restaurantes'),
    ('menu_qr', 'Menú QR Online'),
    ('menu_qr_visual', 'Menú QR Visual'),
    ('menu_qr_marca', 'Menú QR Marca'),
    ('qr_reviews', 'QR de Reseñas'),          # ← AGREGAR
]
```

**Cambio 2 — ServiceType enum** (línea ~20):
```python
class ServiceType(models.TextChoices):
    GESTION        = 'gestion',        'Gestión Comercial'
    RESTAURANTE    = 'restaurante',    'Restaurantes'
    MENU_QR        = 'menu_qr',        'Menú QR'
    MENU_QR_VISUAL = 'menu_qr_visual', 'Menú QR Visual'
    MENU_QR_MARCA  = 'menu_qr_marca',  'Menú QR Marca'
    QR_REVIEWS     = 'qr_reviews',     'QR de Reseñas'   # ← AGREGAR
```

**Cambio 3 — BusinessPlan** (línea ~110, después de MENU_QR_PREMIUM):
```python
  MENU_QR_PREMIUM = 'menu_qr_premium', 'Menú QR Premium'

  # QR de Reseñas
  QR_REVIEWS = 'qr_reviews', 'QR de Reseñas'           # ← AGREGAR
```

- **Crítico:** Sí — todo lo demás depende de esto.
- **Dependencias:** Ninguna (primer cambio de la cadena).

---

#### C2. `services/api/src/apps/billing/models.py`

**Objetivo:** Agregar `qr_reviews` a SubscriptionV2.ServiceType y `qr_reviews` a Module/Bundle VERTICAL_CHOICES.

**Cambio 1 — SubscriptionV2.ServiceType** (línea ~270):
```python
class ServiceType(models.TextChoices):
    GESTION        = 'gestion',        'Gestión Comercial'
    RESTAURANTE    = 'restaurante',    'Restaurantes'
    MENU_QR        = 'menu_qr',        'Menú QR'
    MENU_QR_VISUAL = 'menu_qr_visual', 'Menú QR Visual'
    MENU_QR_MARCA  = 'menu_qr_marca',  'Menú QR Marca'
    QR_REVIEWS     = 'qr_reviews',     'QR de Reseñas'  # ← AGREGAR
```

**Cambio 2 — Module.VERTICAL_CHOICES** (línea ~83):
```python
VERTICAL_CHOICES = [
    ('commercial', 'Commercial'),
    ('restaurant', 'Restaurant'),
    ('both', 'Both'),
    ('menu_qr', 'Menu QR'),
    ('qr_reviews', 'QR de Reseñas'),                    # ← AGREGAR
]
```

**Cambio 3 — Bundle.VERTICAL_CHOICES** (línea ~117):
```python
VERTICAL_CHOICES = [
    ('commercial', 'Commercial'),
    ('restaurant', 'Restaurant'),
    ('menu_qr', 'Menu QR'),
    ('qr_reviews', 'QR de Reseñas'),                    # ← AGREGAR
]
```

- **Crítico:** Sí.
- **Dependencias:** C1 (Business model debe tener QR_REVIEWS primero, porque billing importa Business).

---

#### C3. Migraciones

**Crear:**
- `services/api/src/apps/business/migrations/0020_add_qr_reviews_service_type.py`
  - `AlterField` para `service_type` (nuevos choices)
  - `AlterField` para `default_service` (nuevos choices en SERVICE_CHOICES)
  - NO es data migration, solo schema choices (no rompe columnas existentes)

- `services/api/src/apps/billing/migrations/0011_add_qr_reviews_vertical.py`
  - `AlterField` para `SubscriptionV2.service_type` (nuevos choices)
  - `AlterField` para `Module.vertical` (nuevos choices)
  - `AlterField` para `Bundle.vertical` (nuevos choices)

**Comando:** `docker exec mirubro-api python manage.py makemigrations business billing`

- **Crítico:** Sí.
- **Dependencias:** C1, C2.

---

### PR2: Billing + Features + Seeds

---

#### C4. `services/api/src/apps/business/features.py`

**Objetivo:** Definir feature flags para plan `qr_reviews`.

**Cambio 1 — FEATURE_KEYS** (después de `menu_qr_tips_pro`):
```python
  'menu_qr_tips_pro',  # Dynamic tip amount via MP OAuth Checkout (Fase 2)
  # QR de Reseñas standalone
  'qr_reviews_config',   # Admin puede configurar Google Place ID
  'qr_reviews_qr',       # Admin puede generar y descargar QR
)
```

**Cambio 2 — PLAN_FEATURES** (agregar al final del dict, antes del cierre):
```python
  # ── QR de Reseñas standalone ───────────────────────────────────────────
  'qr_reviews': (
    'menu_qr_reviews',     # Reutiliza el feature flag existente
    'qr_reviews_config',
    'qr_reviews_qr',
  ),
```

Nota: Reutilizamos `menu_qr_reviews` para que la lógica existente en `MenuEngagementSettings` que chequea este flag siga funcionando. El plan `qr_reviews` habilita el mismo flag que los planes de menu_qr para reviews.

- **Crítico:** Sí — sin esto, el usuario qr_reviews tendría todos los features en False.
- **Dependencias:** C1 (BusinessPlan.QR_REVIEWS debe existir).

---

#### C5. `services/api/src/apps/business/service_catalog.py`

**Objetivo:** Registrar `qr_reviews` como servicio habilitado.

**Cambio 1 — SERVICE_CATALOG** (agregar al final de la tupla):
```python
  ServiceDefinition(
    slug='qr_reviews',
    name='QR de Reseñas',
    description='QR para reseñas de Google: configurá tu negocio y compartí el código.',
    features=['menu_qr_reviews', 'qr_reviews_config'],
    min_plan=BusinessPlan.QR_REVIEWS,
  ),
```

**Cambio 2 — PLAN_ORDER** (agregar):
```python
  # QR de Reseñas
  BusinessPlan.QR_REVIEWS: 0,
```

- **Crítico:** Sí — `enabled_services()` usa esto para decidir si el servicio está disponible.
- **Dependencias:** C1, C4.

---

#### C6. `services/api/src/apps/billing/runtime.py`

**Objetivo:** Que `_extract_plan_tier` reconozca `qr_reviews` como tier válido.

**Cambio — _KNOWN_TIERS** (agregar `qr_reviews` al final, antes de los tiers genéricos):
```python
_KNOWN_TIERS = [
    'menu_qr_premium', 'menu_qr_visual', 'menu_qr_marca',
    'menu_qr_lite', 'menu_qr_pro', 'menu_qr',
    'qr_reviews',                                        # ← AGREGAR
    'enterprise', 'business', 'starter', 'start', 'plus', 'pro',
]
```

- **Crítico:** Sí — sin esto, `resolve_subscription` no puede extraer el tier y devuelve `plan_code` raw como fallback → features vacías.
- **Dependencias:** Ninguna.

---

#### C7. `services/api/src/apps/business/entitlements.py`

**Objetivo:** Agregar entitlements mínimos para QR Reviews (aunque la V1 no los consume activamente).

**Cambio — PLAN_ENTITLEMENTS** (agregar al final, antes de los aliases):
```python
    # QR de Reseñas
    'qr_reviews': {
        'qr_reviews.config',
        'qr_reviews.qr',
        'qr_reviews.dashboard_basic',
    },
```

- **Crítico:** No bloqueante — el sistema actual no enforcea entitlements para QR Reviews explícitamente, pero es buena práctica tenerlo definido.
- **Dependencias:** Ninguna.

---

#### C8. `services/api/src/apps/billing/management/commands/seed_billing.py`

**Objetivo:** Crear módulos, bundle y plan de checkout para QR de Reseñas.

**Cambio — Agregar al final del `handle()`, antes del `success` message:**

```python
        # ── QR de Reseñas ──────────────────────────────────────────────────
        qr_reviews_mods_data = [
            ('qr_reviews_core', 'QR de Reseñas', 'Configuración de Google Place ID y enlace de reseñas.', 'operation', 0, True),
            ('qr_reviews_qr_gen', 'Generador de QR', 'Generación de QR y link público para reseñas.', 'insights', 0, True),
        ]
        qr_reviews_modules = {}
        for code, name, desc, cat, price, is_core in qr_reviews_mods_data:
            mod, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': desc,
                    'category': cat,
                    'price_monthly': price,
                    'price_yearly': 0,
                    'is_core': is_core,
                    'vertical': 'qr_reviews',
                }
            )
            qr_reviews_modules[code] = mod

        b_qr_reviews, _ = Bundle.objects.update_or_create(
            code='qr_reviews',
            defaults={
                'name': 'QR de Reseñas',
                'description': 'QR y enlace público para recopilar reseñas de Google.',
                'vertical': 'qr_reviews',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 15000,   # ARS $150/mes (en centavos)
                'fixed_price_yearly': 144000,   # ARS $150 * 12 * 0.8
                'is_default_recommended': True,
                'badge': '',
            }
        )
        b_qr_reviews.modules.set(list(qr_reviews_modules.values()))

        # Plan de checkout
        Plan.objects.update_or_create(
            code='qr_reviews',
            defaults={
                'name': 'QR de Reseñas',
                'price': Decimal('150.00'),
                'interval': 'monthly',
                'currency': 'ARS',
                'frequency': 1,
                'frequency_type': 'months',
                'plan_status': 'active',
            }
        )
```

Después de agregar, agregar `'qr_reviews'` a PLAN_SEEDS también:
```python
            ('qr_reviews',             'QR de Reseñas',                      Decimal('150.00'),  'qr_reviews'),
```

- **Crítico:** Sí — sin bundle ni Plan, el onboarding no puede encontrar plans para mostrar.
- **Dependencias:** C2 (vertical choices deben incluir 'qr_reviews').

---

### PR3: Onboarding + Routing + Sidebar

---

#### C9. `services/api/src/apps/accounts/onboarding_views.py`

**Objetivo:** Permitir `qr_reviews` como service_type válido en onboarding.

**Cambio — VALID_SERVICE_TYPES** (línea 56):
```python
VALID_SERVICE_TYPES = frozenset(['gestion', 'restaurante', 'menu_qr', 'qr_reviews'])
```

- **Crítico:** Sí — sin esto el POST set-service devuelve 400 al elegir QR de Reseñas.
- **Dependencias:** C1.

---

#### C10. `apps/web/src/app/app/onboarding/servicio/page.tsx`

**Objetivo:** Agregar 4ta opción de servicio.

**Cambio — SERVICE_OPTIONS** (línea ~15):
```typescript
const SERVICE_OPTIONS: ServiceOption[] = [
    {
        code: 'gestion',
        label: 'Gestión Comercial',
        description: 'Ventas, stock, clientes, caja y facturación para comercios.',
    },
    {
        code: 'restaurante',
        label: 'Restaurante',
        description: 'Mesas, pedidos, cocina y delivery para gastronomía.',
    },
    {
        code: 'menu_qr',
        label: 'Menú QR',
        description: 'Carta digital con código QR para que tus clientes vean tu menú.',
    },
    {
        code: 'qr_reviews',
        label: 'QR de Reseñas',
        description: 'Un QR para que tus clientes dejen reseñas en Google fácilmente.',
    },
];
```

- **Crítico:** Sí.
- **Dependencias:** C9.

---

#### C11. `apps/web/src/app/app/onboarding/plan/page.tsx`

**Objetivo:** Mapear `qr_reviews` a su vertical de billing.

**Cambio 1 — verticalMap** (línea ~57):
```typescript
const verticalMap: Record<string, string> = {
    gestion: 'commercial',
    restaurante: 'restaurant',
    menu_qr: 'menu_qr',
    qr_reviews: 'qr_reviews',                           // ← AGREGAR
};
```

**Cambio 2 — serviceLabel** (línea ~76):
```typescript
const serviceLabel: Record<string, string> = {
    gestion: 'Gestión Comercial',
    restaurante: 'Restaurante',
    menu_qr: 'Menú QR',
    qr_reviews: 'QR de Reseñas',                        // ← AGREGAR
};
```

- **Crítico:** Sí — sin esto, al elegir qr_reviews el fetch de bundles no tiene vertical y falla.
- **Dependencias:** C8 (bundles deben existir en DB).

---

#### C12. `apps/web/src/lib/services/index.ts`

**Objetivo:** Agregar entry route para QR de Reseñas.

**Cambio:**
```typescript
const SERVICE_ENTRY_ROUTES: Record<string, string> = {
    gestion: '/app/gestion/dashboard',
    restaurante: '/app/orders',
    menu_qr: '/app/menu',
    qr_reviews: '/app/resenas',                          // ← AGREGAR
};
```

- **Crítico:** Sí — sin esto, al completar checkout el redirect a /app cae en fallback /app/servicios.
- **Dependencias:** La ruta /app/resenas debe existir (PR4).

---

#### C13. `apps/web/src/components/navigation/sidebar.tsx`

**Objetivo:** Agregar sección de navegación para QR de Reseñas y su label.

**Cambio 1 — SERVICE_LABELS** (línea ~14):
```typescript
const SERVICE_LABELS: Record<string, string> = {
    gestion: 'Gestión Comercial',
    restaurante: 'Restaurante Inteligente',
    menu_qr: 'Menú QR Online',
    qr_reviews: 'QR de Reseñas',                        // ← AGREGAR
};
```

**Cambio 2 — NAV_CONFIG** (agregar después de `menu_qr`):
```typescript
    qr_reviews: [
        {
            title: 'QR de Reseñas',
            items: [
                { href: '/app/resenas', label: 'Inicio' },
                { href: '/app/resenas/configuracion', label: 'Configuración' },
                { href: '/app/resenas/qr', label: 'QR y enlace' },
            ],
        },
        {
            title: 'Cuenta',
            items: [
                { href: '/app/servicios', label: 'Planes y upgrades' },
                { href: '/app/planes', label: 'Facturación' },
                { href: '/app/settings', label: 'Configuración' },
                { href: '/app/soporte', label: 'Soporte', roleKey: 'owner' },
            ],
        },
    ],
```

- **Crítico:** Sí — sin esto el sidebar queda vacío para un usuario qr_reviews.
- **Dependencias:** Ninguna (funciona aunque las rutas no existan aún — los links simplemente llevan a 404).

---

#### C14. `apps/web/src/components/app/app-shell.tsx`

**Objetivo:** Agregar route gate para que qr_reviews solo vea sus rutas.

**Cambio 1 — Agregar constante:**
```typescript
const QR_REVIEWS_ALLOWED_PATHS = [
    '/app',
    '/app/resenas',
    '/app/servicios',
    '/app/planes',
    '/app/settings',
];
```

**Cambio 2 — isRestricted logic** (en `AppShellContent`):
```typescript
    const isRestricted = useMemo(() => {
        if (service === 'menu_qr') {
            return !isMenuQrPathAllowed(pathname);
        }
        if (service === 'qr_reviews') {
            return !QR_REVIEWS_ALLOWED_PATHS.some((p) => pathMatches(pathname, p));
        }
        return false;
    }, [pathname, service]);
```

- **Crítico:** Sí — sin esto un usuario qr_reviews podría navegar manualmente a /app/gestion/* y ver contenido inapropiado.
- **Dependencias:** Ninguna.

---

### PR4: Dashboard Mínimo + Página Pública

---

#### C15. `apps/web/src/app/app/resenas/layout.tsx`

**Objetivo:** Guard que solo permite acceso a servicios qr_reviews.

```tsx
import { redirect } from 'next/navigation';
import { getSession } from '@/lib/auth';

export default async function ResenasLayout({ children }: { children: React.ReactNode }) {
    const session = await getSession();
    if (!session) redirect('/entrar');

    const enabled = session.services?.enabled ?? [];
    if (!enabled.includes('qr_reviews')) {
        redirect('/app/servicios');
    }

    return <>{children}</>;
}
```

- **Crítico:** Sí.

---

#### C16. `apps/web/src/app/app/resenas/page.tsx`

**Objetivo:** Dashboard principal mínimo — muestra estado y link rápido a configurar.

Contenido esperado:
- Título: "QR de Reseñas"
- Estado: si tiene google_place_id configurado → mostrar "✓ Configurado" + link al QR
- Si no → mostrar CTA "Configurá tu Google Place ID" → link a /app/resenas/configuracion
- Link al QR público

Nota: Este dashboard consume `GET /api/v1/menu/engagement/` para obtener el estado de `MenuEngagementSettings`. No se crea un endpoint nuevo. Si el business no tiene `MenuEngagementSettings`, se muestra el estado "no configurado".

- **Crítico:** Sí (es el entry point del producto).
- **Dependencias:** Endpoint `/api/v1/menu/engagement/` debe funcionar sin menú activo (ver C21).

---

#### C17. `apps/web/src/app/app/resenas/configuracion/page.tsx`

**Objetivo:** Formulario para configurar Google Place ID.

Contenido esperado:
- Input de Google Place ID
- Input de URL de review fallback (opcional)
- Toggle reviews_enabled
- Botón guardar → `PATCH /api/v1/menu/engagement/`
- Instrucciones de cómo encontrar el Google Place ID

Reutiliza: La lógica ya existente en `components/app/engagement-settings-section.tsx` (solo la parte de reviews, no tips). Puede importarse o simplificarse.

- **Crítico:** Sí (sin esto no hay funcionalidad).

---

#### C18. `apps/web/src/app/app/resenas/qr/page.tsx`

**Objetivo:** Mostrar QR descargable y link público.

Contenido esperado:
- QR apuntando a `{FRONTEND_URL}/r/{business.slug}`
- Link copiable
- Botón para descargar QR como PNG
- Puede reutilizar lógica de QR de menu (`apps/web/src/app/app/menu/qr/`)

- **Crítico:** Sí (core del producto).

---

#### C19. `apps/web/src/app/r/[slug]/page.tsx`

**Objetivo:** Página pública de QR de reseñas (standalone, sin menú).

Funcionamiento:
1. Recibe slug del business
2. Llama al backend para obtener engagement settings del business → necesita endpoint público
3. Si tiene `google_write_review_url` → muestra landing con logo/nombre + CTA "Dejá tu reseña en Google" + redirect automático en 3s
4. Si no tiene configurado → muestra "Este negocio no ha configurado sus reseñas"

**Endpoint público necesario:** Crear un endpoint nuevo `GET /api/v1/public/reviews/{slug}/` que devuelva `{ business_name, google_write_review_url }` sin autenticación. Alternativa: reutilizar la respuesta del endpoint `/api/v1/public/menu/{slug}/` que ya devuelve el campo `engagement.google_write_review_url`, siempre que el business tenga un `PublicMenuConfig` con slug.

**Problema descubierto:** Si el business es solo `qr_reviews` y nunca creó un `PublicMenuConfig`, el endpoint público del menú no lo encontrará por slug.

**Solución:** Crear un endpoint público mínimo nuevo:

#### C20. `services/api/src/apps/menu/views.py` (agregar view)

```python
class PublicReviewRedirectView(APIView):
    """Public endpoint: returns review URL for a business by slug."""
    permission_classes = []
    authentication_classes = []

    def get(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        engagement = MenuEngagementSettings.objects.filter(business=business).first()
        if not engagement or not engagement.reviews_enabled:
            return Response({'detail': 'Reviews not configured'}, status=404)
        return Response({
            'business_name': business.name,
            'google_write_review_url': engagement.google_write_review_url,
        })
```

Y agregar URL: `path('public/reviews/<slug:slug>/', PublicReviewRedirectView.as_view())`

- **Crítico:** Sí.
- **Dependencias:** C1 (business.slug debe existir — ya existe para todos los business).

---

#### C21. Verificar `MenuEngagementSettings` funciona standalone

**Archivo:** `services/api/src/apps/menu/views.py` — `EngagementSettingsView`

**Riesgo:** El endpoint `GET /api/v1/menu/engagement/` que lee las settings podría tener un guard que exija service_type `menu_qr`. Hay que verificar.

**Acción:** Leer el view y confirmar que funciona con service_type `qr_reviews`. Si tiene guard `require_service('menu_qr')`, hay que relajarlo para aceptar también `qr_reviews`.

**Cambio probable en views.py:**
```python
# En la vista de engagement:
# Si tiene un guard tipo require_service('menu_qr'), cambiar a:
# require_service(['menu_qr', 'qr_reviews'])
```

- **Crítico:** Sí — bloquea el dashboard de reseñas.
- **Dependencias:** C1.

---

### PR5: Tests + Demo

---

#### C22. Test backend: features resolution

**Archivo:** `services/api/src/apps/billing/tests/test_qr_reviews.py` (CREAR)

Tests:
- `feature_flags_for_plan('qr_reviews')` incluye `menu_qr_reviews=True`, `qr_reviews_config=True`, `qr_reviews_qr=True`
- `feature_flags_for_plan('qr_reviews')` NO incluye `menu_builder=True` (no tiene acceso a carta)
- `_extract_plan_tier('qr_reviews')` retorna `'qr_reviews'`
- `enabled_services('qr_reviews', flags)` incluye `'qr_reviews'`
- `enabled_services('qr_reviews', flags)` NO incluye `'menu_qr'`

---

#### C23. Test backend: onboarding

**Archivo:** `services/api/src/apps/accounts/tests/test_onboarding_qr_reviews.py` (CREAR)

Tests:
- POST set-service con `service_type='qr_reviews'` retorna 200
- GET onboarding status devuelve `step='plan_selection'` después de set-service
- GET bundles con `vertical=qr_reviews` devuelve el bundle de QR Reviews

---

#### C24. Seed demo account

**Archivo:** `services/api/src/apps/billing/management/commands/seed_qr_reviews_demo.py` (CREAR)

```python
# Crea un usuario qr.reviews.demo@demo.local con:
# - Business: "Heladería Dulce Sueño" (service_type='qr_reviews', status='active')
# - business.Subscription: plan='qr_reviews', service='qr_reviews'
# - billing.Subscription: bundle='qr_reviews'
# - SubscriptionV2: service_type='qr_reviews', plan_code='qr_reviews', status='active'
# - MenuEngagementSettings: reviews_enabled=True, google_place_id='ChIJ...' (fake)
```

---

## D. Contrato Mínimo de Producto para V1

### Qué puede hacer el usuario

1. **Registrarse** y elegir "QR de Reseñas" como servicio en el onboarding
2. **Seleccionar plan** (único, ~ARS $150/mes) y **completar checkout** vía MercadoPago
3. **Iniciar sesión** y ver un **dashboard mínimo** en `/app/resenas` con estado de configuración
4. **Configurar** su Google Place ID en `/app/resenas/configuracion`
5. **Ver y descargar** su QR + link público en `/app/resenas/qr`
6. **Compartir** el link `/r/{slug}` que lleva a los clientes a dejar una reseña en Google
7. **Ver planes y facturación** en `/app/planes`

### Qué NO puede hacer todavía

- No tiene analytics de escaneos
- No tiene branding personalizado en la página pública (solo nombre del negocio)
- No tiene soporte para TripAdvisor, Instagram, Yelp (solo Google)
- No tiene tips / propinas
- No tiene multi-branch
- No puede tener Carta Online + QR Reseñas simultáneamente
- No tiene comparación de plans (solo 1 plan)

### Feature flags necesarios

| Flag | Valor para plan `qr_reviews` | Propósito |
|------|------------------------------|-----------|
| `menu_qr_reviews` | `True` | Habilita reviews_enabled en engagement settings |
| `qr_reviews_config` | `True` | Permite acceso a configuración |
| `qr_reviews_qr` | `True` | Permite acceso a generador QR |
| `dashboard` | `True` (via BASE_ALWAYS_ON) | Dashboard básico |
| `services` | `True` (via BASE_ALWAYS_ON) | Página de servicios |
| `settings` | `True` (via BASE_ALWAYS_ON) | Configuración general |

### Vistas mínimas

| Ruta | Tipo | Descripción |
|------|------|-------------|
| `/app/resenas` | Autenticada | Dashboard: estado de config, links rápidos |
| `/app/resenas/configuracion` | Autenticada | Formulario Google Place ID |
| `/app/resenas/qr` | Autenticada | QR + link público descargable |
| `/r/[slug]` | Pública | Landing intermedia → redirect a Google Reviews |

### Datos que guarda

| Dato | Modelo | Campo | Notas |
|------|--------|-------|-------|
| Google Place ID | `MenuEngagementSettings` | `google_place_id` | Ya existe |
| Google Review URL (fallback) | `MenuEngagementSettings` | `google_review_url` | Ya existe |
| Reviews habilitado | `MenuEngagementSettings` | `reviews_enabled` | Ya existe |
| Suscripción | `SubscriptionV2` | `service_type='qr_reviews'` | Nuevo valor |
| Business slug | `Business` | `slug` | Ya existe (auto-generado) |

**No se crean tablas nuevas.** Solo nuevos valores en enums y nuevos seeds.

---

## E. Riesgos Técnicos Inmediatos

### 1. Engagement endpoint requiere service_type menu_qr
**Riesgo:** `GET/PATCH /api/v1/menu/engagement/` puede tener un guard o permission class que exija que el business tenga `service_type` en (`menu_qr`, `menu_qr_visual`, `menu_qr_marca`). Si es así, un business `qr_reviews` recibe 403.
**Mitigación:** Verificar las permission classes del view antes de codear. Si hay guard, relajar a `['menu_qr', 'menu_qr_visual', 'menu_qr_marca', 'qr_reviews']` o mejor, chequear feature flag `menu_qr_reviews` en vez de service_type.

### 2. `build_business_context()` no reconoce el service `qr_reviews`
**Riesgo:** `enabled_services()` usa `PLAN_ORDER` y `SERVICE_CATALOG`. Si `qr_reviews` no está en `PLAN_ORDER`, el ranking falla y el servicio no se habilita.
**Mitigación:** Asegurar PR2 (C5) esté completo antes de testear el flujo.

### 3. Frontend `session.current.service` no matchea ningún sidebar
**Riesgo:** Si el backend devuelve `service: 'qr_reviews'` pero el sidebar no tiene `NAV_CONFIG['qr_reviews']`, el sidebar queda vacío y el usuario ve una pantalla en blanco.
**Mitigación:** PR3 (C13) agrega la config. PRs deben mergearse en orden: PR1 → PR2 → PR3 → PR4.

### 4. `PublicMenuConfig.slug` vs `Business.slug`
**Riesgo:** La ruta pública `/m/[slug]` usa `PublicMenuConfig.slug` (tabla separada). La ruta `/r/[slug]` necesita usar `Business.slug`. Son slugs diferentes. Si un negocio tiene ambos, los slugs podrían diferir.
**Mitigación:** `/r/[slug]` usa explícitamente `Business.slug`, no `PublicMenuConfig.slug`. No hay conflicto: son dos rutas diferentes (`/m/` vs `/r/`).

### 5. `seed_billing` corre antes de migración 0020
**Riesgo:** Si alguien corre `seed_billing` antes de correr `makemigrations` + `migrate`, el vertical `qr_reviews` no es válido para `Module.vertical` y Django lanza ValidationError.
**Mitigación:** Documentar en el PR que las migraciones deben correrse ANTES del seed. El script de seed es idempotente — si falla, se re-corre post-migración.

---

## F. PR Plan

### PR1: Backend Enums + Migraciones
**Archivos:**
- `services/api/src/apps/business/models.py` (3 cambios)
- `services/api/src/apps/billing/models.py` (3 cambios)
- `services/api/src/apps/business/migrations/0020_*.py` (auto-generada)
- `services/api/src/apps/billing/migrations/0011_*.py` (auto-generada)

**Tamaño:** ~6 líneas de código + 2 migraciones auto-generadas  
**Riesgo:** Nulo — solo agrega choices, no altera schema de columnas  
**Test manual:** `docker exec mirubro-api python manage.py migrate` → sin errores  

---

### PR2: Features + Service Catalog + Seeds
**Archivos:**
- `services/api/src/apps/business/features.py` (2 cambios)
- `services/api/src/apps/business/service_catalog.py` (2 cambios)
- `services/api/src/apps/billing/runtime.py` (1 cambio)
- `services/api/src/apps/business/entitlements.py` (1 cambio)
- `services/api/src/apps/billing/management/commands/seed_billing.py` (1 bloque nuevo)

**Tamaño:** ~60 líneas  
**Riesgo:** Bajo — todo aditivo  
**Test manual:** `docker exec mirubro-api python manage.py seed_billing` → sin errores; `docker exec mirubro-api python manage.py shell -c "from apps.business.features import feature_flags_for_plan; print(feature_flags_for_plan('qr_reviews'))"` → confirmar flags  
**Depende de:** PR1 mergeado y migrado  

---

### PR3: Onboarding + Routing + Sidebar
**Archivos:**
- `services/api/src/apps/accounts/onboarding_views.py` (1 cambio)
- `apps/web/src/app/app/onboarding/servicio/page.tsx` (1 cambio)
- `apps/web/src/app/app/onboarding/plan/page.tsx` (2 cambios)
- `apps/web/src/lib/services/index.ts` (1 cambio)
- `apps/web/src/components/navigation/sidebar.tsx` (2 cambios)
- `apps/web/src/components/app/app-shell.tsx` (2 cambios)

**Tamaño:** ~50 líneas  
**Riesgo:** Bajo — todo aditivo  
**Test manual:** Crear cuenta nueva → elegir QR de Reseñas → ver plan → pagar → login → sidebar correcto  
**Depende de:** PR2 mergeado (bundles deben existir)  

---

### PR4: Dashboard + Página Pública
**Archivos (CREAR):**
- `apps/web/src/app/app/resenas/layout.tsx`
- `apps/web/src/app/app/resenas/page.tsx`
- `apps/web/src/app/app/resenas/configuracion/page.tsx`
- `apps/web/src/app/app/resenas/qr/page.tsx`
- `apps/web/src/app/r/[slug]/page.tsx`

**Archivos (MODIFICAR):**
- `services/api/src/apps/menu/views.py` (agregar `PublicReviewRedirectView`)
- `services/api/src/apps/menu/urls.py` (agregar ruta pública)
- Posiblemente: relajar guard en `EngagementSettingsView`

**Tamaño:** ~300-400 líneas (5 páginas nuevas + 1 view + 1 URL)  
**Riesgo:** Bajo — no modifica flujos existentes  
**Test manual:** Login con demo qr_reviews → navegar dashboard → configurar Place ID → ver QR → abrir link público  
**Depende de:** PR3 mergeado  

---

### PR5: Tests + Demo Seed
**Archivos (CREAR):**
- `services/api/src/apps/billing/tests/test_qr_reviews.py`
- `services/api/src/apps/accounts/tests/test_onboarding_qr_reviews.py`
- `services/api/src/apps/billing/management/commands/seed_qr_reviews_demo.py`

**Tamaño:** ~200 líneas  
**Riesgo:** Nulo  
**Depende de:** PR4 mergeado  

---

## Resumen

| PR | Scope | Archivos | Líneas | Riesgo |
|----|-------|----------|--------|--------|
| PR1 | Enums + migraciones | 4 | ~10 + auto | Nulo |
| PR2 | Features + seeds | 5 | ~60 | Bajo |
| PR3 | Onboarding + routing | 6 | ~50 | Bajo |
| PR4 | Dashboard + página pública | 7-8 | ~350 | Bajo |
| PR5 | Tests + demo | 3 | ~200 | Nulo |
| **Total** | | **~25 archivos** | **~670 líneas** | **Bajo** |

Cada PR es mergeable de forma independiente (excepto orden de dependencias). Ningún PR modifica lógica existente de Carta Online.
