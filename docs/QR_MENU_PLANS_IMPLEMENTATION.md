# QR Menu Plans — Implementación y Auditoría

> Fecha: 2026-02-24 | Estado: ✅ Implementado

---

## 1. Auditoría Inicial

### 1.1 Módulo QR Menu — Ubicación en código

**Backend** (`services/api/src/apps/menu/`)
| Archivo | Contenido |
|---|---|
| `models.py` | `MenuCategory`, `MenuItem`, `PublicMenuConfig`, `MenuBrandingSettings` |
| `views.py` | CRUD categorías, items, config pública, QR, branding, import/export |
| `serializers.py` | Serializers para admin y vista pública |
| `urls.py` | URL patterns |
| `importer.py` | Import/export Excel |

**Frontend** (`apps/web/src/`)
| Path | Contenido |
|---|---|
| `app/app/carta/page.tsx` | Server component — gate por `session.features.resto_menu` |
| `app/app/carta/menu-client.tsx` | Client component completo (927 líneas) — CRUD carta |
| `app/m/[slug]/page.tsx` | Carta pública por slug |
| `features/menu/api.ts` | Funciones API |
| `features/menu/hooks.ts` | React Query hooks |
| `features/menu/types.ts` | Tipos TS |
| `components/public-menu/` | Componentes rendering carta pública |

---

### 1.2 Sistema de Planes/Entitlements

#### Dos sistemas coexistentes (por diseño histórico)

**Sistema A — Legacy (`apps/business/`)**
- `business.Subscription` → `plan` (string: `menu_qr`, `pro`, etc.)
- `business/features.py` → `PLAN_FEATURES` dict → `feature_flags_for_plan()`
- `business/context.py` → `build_business_context()` → expuesto en `/api/v1/auth/me/`
- Frontend recibe: `session.features: Record<string, boolean>`

**Sistema B — Billing (`apps/billing/`)**
- `billing.Bundle` → contiene múltiples `Module`s
- `billing.Subscription` → FK a `Bundle` + M2M `selected_modules`
- `PricingService.tenant_has_feature(business_id, module_code)` → checks modules
- `billing/permissions.py` → `CheckFeatureAccess` → usa PricingService

**Cuál usa cada cosa:**
- Access principal QR menu (service check): `require_service('menu_qr')` en `service_policy.py`
  - Busca `business.default_service` o `business.subscription.service`
- Feature gating de permisos CRUD: `HasPermission` con `permission_map` (RBAC)
- Feature gating de imágenes (NUEVO): `CheckFeatureAccess` con `required_feature = 'menu_item_images'`
  - Checks `billing.Subscription.bundle.modules.filter(code='menu_item_images')`
- Frontend gating: `session.features.menu_item_images` (del sistema legacy A)

#### Exposición al frontend
- `/api/v1/auth/me/` retorna `session.features` → `Record<string, bool>`
- Las flags vienen de `features.py` → `PLAN_FEATURES[plan]`
- `session.permissions` vienen de `rbac.py` → `MENU_QR_PERMISSIONS`

#### Errores de plan
- `CheckFeatureAccess`: retorna HTTP 403 (DRF BasePermission por defecto)
- `HasEntitlement`: retorna 403 con `code: 'plan_entitlement_required'`
- `require_service()`: retorna 403 con mensaje de servicio

---

### 1.3 Endpoints existentes QR Menu

**Endpoints admin (autenticados):**
```
GET/POST   /api/v1/menu/categories/
GET/PATCH/DELETE /api/v1/menu/categories/<uuid>/
GET/POST   /api/v1/menu/items/
GET/PATCH/DELETE /api/v1/menu/items/<uuid>/
GET        /api/v1/menu/structure/
POST       /api/v1/menu/import/
GET        /api/v1/menu/export/
GET/PATCH  /api/v1/menu/public/config/
GET/PATCH  /api/v1/menu/branding/
POST       /api/v1/menu/public/logo/
GET        /api/v1/menu/qr/<business_id>/         (QR code generation)
```

**Endpoints públicos (sin auth):**
```
GET        /api/v1/menu/public/slug/<slug>/
GET        /api/v1/menu/public/resolve/<public_id>/
```

**Nuevos endpoints (implementados en esta PR):**
```
POST       /api/v1/menu/items/<uuid>/image/       (upload image — requiere qr_menu.images)
DELETE     /api/v1/menu/items/<uuid>/image/       (delete image — requiere qr_menu.images)
```

---

## 2. Planes y Features — Source of Truth

### Módulos creados (billing)

| Código módulo | Plan mínimo | Descripción |
|---|---|---|
| `menu_builder_core` | QR Básico | Editor de carta (categorías + items) |
| `menu_branding_basic` | QR Básico | Logo, colores, tipografías |
| `menu_qr_tools` | QR Básico | QR + link público |
| `menu_item_images` | **QR Visual** | Imágenes por producto |
| `menu_custom_domain` | **QR Marca** | Dominio personalizado |

### Bundles creados (billing)

| Bundle code | Nombre | Precio/mes | Módulos incluidos |
|---|---|---|---|
| `menu_qr_basico` | QR Básico | $29 (2900 ARS) | builder + branding + qr_tools |
| `menu_qr_visual` | QR Visual | $59 (5900 ARS) | + `menu_item_images` |
| `menu_qr_marca` | QR Marca | $99 (9900 ARS) | + `menu_custom_domain` |

> El bundle legacy `menu_qr_online` queda en DB como alias (no se elimina para no romper registros existentes).

### Feature flags (sistema legacy, expuesto en session.features)

| Feature key | QR Básico | QR Visual | QR Marca | Restaurante |
|---|---|---|---|---|
| `menu_builder` | ✅ | ✅ | ✅ | ✅ |
| `menu_branding` | ✅ | ✅ | ✅ | ✅ |
| `public_menu` | ✅ | ✅ | ✅ | ✅ |
| `menu_qr_tools` | ✅ | ✅ | ✅ | ✅ |
| `menu_item_images` | ❌ | ✅ | ✅ | ✅ |
| `menu_custom_domain` | ❌ | ❌ | ✅ | ❌ |

> Nota: `menu_qr` (plan legacy) mapea a QR Básico — sin imágenes.
> `plus` (Restaurante Inteligente) activa `menu_item_images` porque el restaurante incluye carta QR completa.

### Plan keys (legacy business.Subscription.plan)

| Plan key | Nuevo | Maps to |
|---|---|---|
| `menu_qr` | existente | QR Básico (sin images) |
| `menu_qr_visual` | **nuevo** | QR Visual (con images) |
| `menu_qr_marca` | **nuevo** | QR Marca (con images + custom domain) |

---

## 3. Cambios Backend

### 3.1 Archivos modificados

| Archivo | Cambio |
|---|---|
| `apps/menu/models.py` | + campo `image` (ImageField) + `image_updated_at` en `MenuItem` |
| `apps/menu/migrations/0005_menuitem_image.py` | Nueva migración |
| `apps/menu/serializers.py` | + `image_url` en `MenuItemSerializer`, `MenuItemWriteSerializer`, `PublicMenuItemSerializer` |
| `apps/menu/views.py` | + `MenuItemImageUploadView` + `MenuItemImageDeleteView` |
| `apps/menu/urls.py` | + rutas para image upload/delete |
| `apps/business/models.py` | + `MENU_QR_VISUAL`, `MENU_QR_MARCA` en `BusinessPlan` + SERVICE_CHOICES |
| `apps/business/features.py` | + `menu_item_images`, `menu_custom_domain` en FEATURE_KEYS y plan features |
| `apps/business/service_catalog.py` | + PLAN_ORDER para nuevos planes |
| `billing/management/commands/seed_billing.py` | + nuevos módulos y 3 bundles tiered |

### 3.2 Archivos nuevos

| Archivo | Contenido |
|---|---|
| `billing/management/commands/seed_qr_menu_demo_accounts.py` | Seed idempotente 3 cuentas demo |

---

## 4. Cambios Frontend

| Archivo | Cambio |
|---|---|
| `features/menu/types.ts` | + `image_url` en `MenuItem`, `PublicMenuItem` |
| `features/menu/api.ts` | + `uploadMenuItemImage()`, `deleteMenuItemImage()` |
| `features/menu/hooks.ts` | + `useUploadMenuItemImage()`, `useDeleteMenuItemImage()` |
| `app/app/carta/page.tsx` | + prop `canUploadImages` desde `session.features.menu_item_images` |
| `app/app/carta/menu-client.tsx` | + UI de subida/borrado de imagen por producto + gating UI |
| `components/public-menu/types.ts` | + `image_url?: string` en `MenuItem` |
| `components/public-menu/item-row.tsx` | + render imagen si `image_url` presente |

---

## 5. Demo Accounts (seed)

Comando: `python manage.py seed_qr_menu_demo_accounts`

| Email | Plan | Bundle | Password |
|---|---|---|---|
| `qr.basico.demo@demo.local` | QR Básico | `menu_qr_basico` | `Demo12345!` |
| `qr.visual.demo@demo.local` | QR Visual | `menu_qr_visual` | `Demo12345!` |
| `qr.marca.demo@demo.local` | QR Marca | `menu_qr_marca` | `Demo12345!` |

Prerequisito: `python manage.py seed_billing`

---

## 6. Flujo de Upload de Imagen

```
Admin UI (item card)
  └─ [Subir imagen] button (visible solo si session.features.menu_item_images)
       └─ file input (jpg/png/webp, max 5MB)
            └─ POST /api/v1/menu/items/<uuid>/image/
                 └─ CheckFeatureAccess checks billing.Subscription.modules includes menu_item_images
                      ├─ 403 → "Tu plan no incluye imágenes de productos"
                      └─ 200 → { image_url: "https://..." }
                           └─ React Query invalidates item list → UI actualiza
```

---

## 7. Decisión: Export/Import

- `export`: NO incluye `image_url` (las URLs de media no son portables entre entornos)
- `import`: NO incluye image URLs (columna ignorada si presente)
- Las imágenes se gestionan sólo por la API de upload
