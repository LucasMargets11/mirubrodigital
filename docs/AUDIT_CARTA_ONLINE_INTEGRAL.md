# Auditoría Integral — Carta Online / Menú QR

**Fecha:** 2026-04-15  
**Alcance:** Inventario funcional, mapa de rutas, componentes, UX/IA, entitlements, propuesta de reorganización  
**Base:** Código real del monorepo MiRubro (frontend Next.js + backend Django)

---

## 1. Inventario Funcional Completo

| # | Función | Existe | Dónde vive (ruta/UI) | Archivo / Componente | API / Hook asociado | Notas |
|---|---------|--------|----------------------|----------------------|---------------------|-------|
| 1 | Gestión de categorías (CRUD) | ✅ | `/app/carta` y `/app/menu` | `apps/web/src/app/app/carta/menu-client.tsx` | `useMenuCategories`, `useCreateMenuCategory`, `useUpdateMenuCategory`, `useDeleteMenuCategory` → `POST/PATCH/DELETE /api/v1/menu/categories/` | Panel lateral izquierdo del editor |
| 2 | Gestión de ítems/productos (CRUD) | ✅ | `/app/carta` y `/app/menu` | `menu-client.tsx` — formulario modal | `useMenuItems`, `useCreateMenuItem`, `useUpdateMenuItem`, `useDeleteMenuItem` → `/api/v1/menu/items/` | Grid de 2 columnas con búsqueda, tags, disponibilidad |
| 3 | Imágenes por producto | ✅ (gated) | `/app/carta` y `/app/menu` | `menu-client.tsx` — upload inline en item card | `useUploadMenuItemImage`, `useDeleteMenuItemImage` → `POST/DELETE /api/v1/menu/items/{id}/image/` | Requiere plan Visual+ o feature `menu_item_images`. JPG/PNG/WebP, max 5MB |
| 4 | Imágenes por categoría | ✅ (gated) | `/app/settings/online-menu` (layout editor) | `apps/web/src/components/app/menu-layout-editor.tsx` | `useUploadMenuCategoryImage`, `useDeleteMenuCategoryImage` | Se gestionan dentro de los bloques de layout, NO en el editor de categorías |
| 5 | Import/Export Excel | ✅ | `/app/carta` y `/app/menu` | `menu-client.tsx` — panel "Bulk Sync" | `useImportMenu`, `useExportMenu` → `POST /api/v1/menu/import/`, `GET /api/v1/menu/export/` | XLSX con fecha en nombre de archivo |
| 6 | Estructura (Kitchen Preview) | ✅ | `/app/carta` y `/app/menu` | `menu-client.tsx` — sección colapsable inferior | `useMenuStructure` → `GET /api/v1/menu/structure/` | Vista read-only de categorías → ítems |
| 7 | Bloques de layout (template-driven) | ✅ | `/app/settings/online-menu` | `menu-layout-editor.tsx` (650+ líneas) | `listMenuLayoutBlocks`, `createMenuLayoutBlock`, `updateMenuLayoutBlock`, `deleteMenuLayoutBlock`, `reorderMenuLayoutBlocks` → `/api/v1/menu/layout/blocks/` | Stack vs grid, columnas responsive, presets (drinks_first / food_first) |
| 8 | Slug / menú público | ✅ | `/app/settings/online-menu` (sección "Config General") | `online-menu-settings-client.tsx` | `getPublicMenuConfig`, `updatePublicMenuConfig` → `/api/v1/menu/public/config/` | Toggle on/off + slug editable |
| 9 | Branding visual (colores, fuentes) | ✅ | `/app/settings/online-menu` (sección "Personalización") | `online-menu-settings-client.tsx` | `useMenuBrandingSettings`, `useUpdateMenuBrandingSettings` → `/api/v1/menu/branding/` | 5 colores hex + 2 tipografías + tamaños. Presets de tema. Live preview inline |
| 10 | Logo (upload, posición, tamaño) | ✅ | `/app/settings/online-menu` (sección "Logo") | `online-menu-settings-client.tsx` | `uploadMenuLogo` → `/api/v1/menu/logo/upload` | 4 posiciones: top_center, title_left, top_right_small, watermark. 3 tamaños. Opacidad configurable |
| 11 | Preview público | ✅ | `/app/menu/preview` | `apps/web/src/app/app/menu/preview/page.tsx` | `serverApiFetch /api/v1/menu-qr/{businessId}/` → iframe al `public_url` | SSR, iframe embebido 70vh |
| 12 | QR (generación, descarga, URL) | ✅ | `/app/menu/qr` | `apps/web/src/app/app/menu/qr/page.tsx` → `MenuQrPageClient` | `useMenuQrCode` → `GET /api/v1/menu-qr/{businessId}/` | SVG, descarga, copy URL. Regenerar QR. Links a preview y branding |
| 13 | QR inline en settings | ✅ | `/app/settings/online-menu` (sección "QR Access Direct") | `online-menu-settings-client.tsx` | Renderiza QR desde URL pública | Duplica parcialmente la funcionalidad de `/app/menu/qr` |
| 14 | Tips / Propinas (MercadoPago) | ✅ (gated) | `/app/settings/online-menu` (EngagementSettingsSection) | `online-menu-settings-client.tsx` | `getMenuEngagementSettings`, `updateMenuEngagementSettings`, `startMercadoPagoOAuth`, `disconnectMercadoPago`, `getMercadoPagoConnectionStatus` | 3 modos: mp_link, mp_qr_image, mp_oauth_checkout. Requiere plan Pro+ o addon |
| 15 | Reseñas Google | ✅ (gated) | `/app/settings/online-menu` (EngagementSettingsSection) | `online-menu-settings-client.tsx` | Mismas APIs de engagement | Place ID + Review URL. Requiere plan Pro+ o addon |
| 16 | Menú público (consumer-facing) | ✅ | `/m/[slug]` (público, sin auth) | `apps/web/src/app/m/[slug]/page.tsx` → `PublicMenuLayout` | `GET /api/v1/menu/public/slug/{slug}/` | Incluye: brand header, bloques, ítems, CTA propinas/reseñas, footer Mirubro |
| 17 | Resolver QR → slug | ✅ | `/q/[public_id]` (público) | `apps/web/src/app/q/[public_id]/route.ts` | `GET /api/v1/menu/public/resolve/{public_id}/` → redirect `/m/{slug}` | QR apunta a `/q/...` que resuelve y redirige |
| 18 | Páginas tip success/pending/failure | ✅ | `/m/[slug]/tip/success`, `/pending`, `/failure` | 3 pages bajo `apps/web/src/app/m/[slug]/tip/` | `createPublicTipPreference`, `getPublicTipStatus`, `verifyPublicTip` | Flujo post-pago MercadoPago |
| 19 | Dominio custom | ⚠️ Flag existe, sin UI | No tiene pantalla propia | — | Feature flag `menu_custom_domain` en plans Premium | Flag definida en `qr_entitlements.py`, no hay UI de configuración visible |
| 20 | Multi-branch | ⚠️ Flag existe, sin UI específica para menú | — | — | Feature flag `multi_branch` en plan Premium | Es feature general, no específica de Carta Online |

---

## 2. Mapa de Rutas Actual

### Rutas internas (autenticadas)

| Ruta | Archivo | Propósito aparente | Label en sidebar | Modo | Problema detectado |
|------|---------|-------------------|-----------------|------|-------------------|
| `/app/carta` | `apps/web/src/app/app/carta/page.tsx` | Editor de carta (categorías + ítems) | "Carta" | restaurante | **Duplica** `/app/menu` — mismo componente `MenuClient` |
| `/app/menu` | `apps/web/src/app/app/menu/page.tsx` | Editor de carta (categorías + ítems) | "Carta Online" | menu_qr | **Duplica** `/app/carta` — mismo `MenuClient` |
| `/app/menu/branding` | `apps/web/src/app/app/menu/branding/page.tsx` | Branding | "Branding" | menu_qr | **Ruta fantasma**: solo hace `redirect('/app/settings/online-menu')` |
| `/app/menu/qr` | `apps/web/src/app/app/menu/qr/page.tsx` | QR y URL pública | "QR y enlaces" | menu_qr | OK, pero QR también aparece en settings |
| `/app/menu/preview` | `apps/web/src/app/app/menu/preview/page.tsx` | Preview en iframe | "Preview público" | menu_qr | OK, funcional |
| `/app/settings/online-menu` | `apps/web/src/app/app/settings/online-menu/page.tsx` | **Mega-página**: slug, logo, colores, fuentes, layout blocks, QR, tips, reseñas | "Carta Online" (en Configuración) | restaurante | **Concentra demasiado**: ~8 funciones distintas en una sola página de 500+ líneas |

### Rutas públicas (sin auth)

| Ruta | Archivo | Propósito | Problema detectado |
|------|---------|-----------|-------------------|
| `/m/[slug]` | `apps/web/src/app/m/[slug]/page.tsx` | Menú público por slug | OK |
| `/q/[public_id]` | `apps/web/src/app/q/[public_id]/route.ts` | Resolver QR → redirect a `/m/{slug}` | OK |
| `/m/[slug]/tip/success` | `apps/web/src/app/m/[slug]/tip/success/page.tsx` | Confirmación de propina | OK |
| `/m/[slug]/tip/pending` | `apps/web/src/app/m/[slug]/tip/pending/page.tsx` | Propina en proceso | OK |
| `/m/[slug]/tip/failure` | `apps/web/src/app/m/[slug]/tip/failure/page.tsx` | Error de propina | OK |

### Diagrama de navegación actual

```
MODO RESTAURANTE                          MODO MENÚ QR
─────────────────────                     ─────────────────────
Sidebar:                                  Sidebar:
  ├─ Restaurante Inteligente              ├─ Menú QR
  │   └─ Carta (/app/carta)  ──┐         │   ├─ Carta Online (/app/menu)  ──┐
  └─ Operación                  │         │   ├─ Branding (/app/menu/branding) → redirect!
     └─ Configuración           │         │   ├─ QR y enlaces (/app/menu/qr)
        └─ Carta Online         │         │   └─ Preview público (/app/menu/preview)
           (/app/settings/      │         └─ Cuenta
            online-menu)  ──────┤                └─ Configuración (/app/settings)
                                │
                     MISMO COMPONENTE: MenuClient
                     MISMA API: /api/v1/menu/*
```

---

## 3. Problemas de UX / IA

### P0 — Críticos

1. **`/app/settings/online-menu` es una mega-página cajón de sastre**  
   Concentra ~8 funciones heterogéneas: toggle público, slug, logo, colores, fuentes, bloques de layout, QR parcial, tips (MercadoPago OAuth), reseñas Google. Un usuario que quiere cambiar un color tiene que scrollear junto a la configuración de OAuth de MercadoPago. **Complejidad cognitiva altísima**.  
   Evidencia: `online-menu-settings-client.tsx` — 500+ líneas, 5 secciones mayores.

2. **Duplicación de rutas carta ↔ menu sin razón funcional**  
   `/app/carta` y `/app/menu` renderizan exactamente el mismo componente (`MenuClient` de `carta/menu-client.tsx`). Misma lógica, mismos permisos (ajustados por feature flag), mismas APIs. La duplicación solo existe por la separación de modos `restaurante` vs `menu_qr`, pero genera confusión si un negocio migra de modo.  
   Evidencia: Ambos pages importan `MenuClient` del mismo path.

3. **"Branding" en sidebar es un engaño: redirige a Settings**  
   `/app/menu/branding` es un item de sidebar (modo `menu_qr`) que solo hace `redirect('/app/settings/online-menu')`. El usuario cree que va a una página de branding y termina en una mega-página de settings genérica. La promesa del label no se cumple.  
   Evidencia: `apps/web/src/app/app/menu/branding/page.tsx` contiene solo `redirect()`.

### P1 — Importantes

4. **QR aparece en 2 lugares distintos con funcionalidad parcialmente solapada**  
   - `/app/menu/qr`: Página dedicada con QR SVG, descarga, regenerar, copy URL.  
   - `/app/settings/online-menu`: Sección "QR Access Direct" con QR PNG y descarga.  
   El usuario no sabe cuál es "el" lugar para gestionar su QR.  
   Evidencia: Ambas vistas renderizan QR con APIs diferentes (`useMenuQrCode` vs generación inline).

5. **Carta no muestra categorías de forma editable en la estructura de bloques**  
   Las imágenes de categoría se gestionan dentro del layout editor (`/app/settings/online-menu`) pero la categoría en sí se edita en el editor de carta (`/app/carta`). El usuario tiene que ir a dos pantallas distintas para configurar completamente una categoría.  
   Evidencia: `menu-layout-editor.tsx` tiene upload de imagen por categoría; `menu-client.tsx` tiene CRUD de categoría sin imagen.

6. **El nombre "Configuración → Carta Online" en modo restaurante esconde funcionalidades clave**  
   En el sidebar de restaurante, todo el branding/layout/tips/QR queda enterrado bajo Operación → Configuración → Carta Online. Un usuario no técnico de restaurante difícilmente llega ahí.  
   Evidencia: `NAV_CONFIG` en `sidebar.tsx` — anidado 3 niveles dentro de Operación.

7. **Engagement (Tips + Reseñas) mezclado con Branding**  
   La sección de engagement (MercadoPago OAuth, Google Places ID) vive dentro de la misma página que colores y fuentes. Son dominios completamente distintos: uno es configuración visual, otro es integración con pagos/reseñas.  
   Evidencia: `EngagementSettingsSection` renderizado dentro de `OnlineMenuSettingsClient`.

### P2 — Mejorables

8. **Naming inconsistente: "Carta" vs "Menu" vs "Menú QR" vs "Carta Online" vs "online-menu"**  
   - Sidebar restaurante: "Carta"  
   - Sidebar menu_qr: "Carta Online"  
   - Ruta: `/app/carta` y `/app/menu`  
   - Settings: "online-menu"  
   - Feature flags: `menu_builder`, `resto_menu`  
   - API: `/api/v1/menu/`  
   No hay un nombre canónico consistente.

9. **Preview vive como página separada pero podría ser inline**  
   `/app/menu/preview` renderiza un iframe. Podría ser un panel lateral o modal dentro de la experiencia de edición, evitando salir del editor.

10. **Dominio custom prometido por plan Premium pero sin UI**  
    El feature flag `menu_custom_domain` existe y está habilitado para planes Premium/Marca, pero no hay ninguna pantalla para configurarlo. Si un usuario paga Premium esperando dominio custom, no encuentra cómo hacerlo.  
    Evidencia: `custom_domain_allowed: True` en `qr_entitlements.py` para Premium; sin componente UI.

11. **Plan check hardcodeado como fallback**  
    Ambas pages (`carta/page.tsx` y `menu/page.tsx`) tienen `PLANS_WITH_IMAGES = ['menu_qr_visual', 'menu_qr_marca', 'plus', 'business']` como fallback al feature flag. Si se agrega un plan nuevo, hay que acordarse de actualizar esta lista.

---

## 4. Duplicaciones e Inconsistencias

| Elemento | Duplicación / Inconsistencia | Impacto en usuario | Evidencia |
|----------|------------------------------|-------------------|-----------|
| Editor de carta | 2 rutas (`/app/carta`, `/app/menu`) para el mismo componente `MenuClient` | Confusión si cambia de modo, doble mantenimiento | Ambos importan `@/app/app/carta/menu-client` |
| QR management | QR en `/app/menu/qr` (SVG, regenerar) + QR en `/app/settings/online-menu` (PNG, descarga) | Usuario no sabe cuál usar | `MenuQrPageClient` vs sección inline en settings |
| "Branding" sidebar item | Label "Branding" en sidebar → redirect a settings mega-page | False promise, desorientación | `menu/branding/page.tsx` = `redirect()` |
| Feature gate images | Feature flag `menu_item_images` + hardcoded plan list de fallback | Riesgo de inconsistencia si se agregan plans | `PLANS_WITH_IMAGES` en `carta/page.tsx` y `menu/page.tsx` |
| Category images vs Category CRUD | Categorías se editan en `/app/carta` pero sus imágenes en `/app/settings/online-menu` (layout editor) | Flujo roto: 2 pantallas para 1 entidad | `menu-client.tsx` vs `menu-layout-editor.tsx` |
| Naming | "Carta" / "Menu" / "Menú QR" / "Carta Online" / "online-menu" para el mismo concepto | Confusión de marca/producto | Sidebar, rutas, features, APIs |
| Settings vs Settings | Config en `/app/settings/online-menu` para menu_qr pero en modo restaurante la misma page vive bajo "Configuración" | Inconsistencia en la experiencia cross-modo | Sidebar `NAV_CONFIG` |
| Preview | Página dedicada `/app/menu/preview` + live preview inline en settings | Duplicación parcial | `preview/page.tsx` vs mini-preview en settings |

---

## 5. Modelo Mental Actual Inferido

### Cómo está planteado hoy

**El producto no tiene un hub central.** Carta Online existe como un **conjunto fragmentado de funciones** distribuidas entre:

1. **El editor de carta** (`/app/carta` o `/app/menu`): solo maneja categorías e ítems, sin acceso a branding, QR, publicación o engagement.
2. **La mega-página de settings** (`/app/settings/online-menu`): absorbe TODO lo demás — branding, layout, slug, logo, engagement, QR parcial. Funciona como un "cajón de sastre" donde se fue agregando cada feature nueva.
3. **Páginas satélite** (`/app/menu/qr`, `/app/menu/preview`): funciones puntuales sin contexto.
4. **Un redirect fantasma** (`/app/menu/branding`): herencia de cuando branding tenía su ruta propia.

### El problema de raíz

El modelo mental implícito es:

> "Carta Online = Editor de contenido + una página de Settings donde todo lo demás se configura"

Pero **eso no es como un usuario piensa**. Un usuario piensa en **tareas**:
- "Quiero armar mi carta" → OK, va al editor
- "Quiero que se vea linda" → ¿A dónde va? A settings, pero no se llama "apariencia"
- "Quiero compartir mi QR" → ¿A dónde va? Hay 2 opciones
- "Quiero activar propinas" → Dentro de settings junto a colores y fuentes
- "Quiero ver cómo queda" → Hay preview separado, pero también mini-preview en settings

**Diagnóstico: fragmentación por arquitectura, no por tarea. El producto refleja cómo se construyó (incremental), no cómo debería usarse.**

### Modos como agravante

La separación `restaurante` vs `menu_qr` agrega complejidad:
- En modo restaurante, todas las funciones de Carta Online están enterradas en Configuración
- En modo menu_qr, tienen su propia sección pero con naming cuestionable ("Branding" que redirige)
- Ambos modos usan las mismas APIs y el mismo componente editor

---

## 6. Gating por Plan — Mapa de Entitlements

### Plans Menú QR

| Feature | Lite (`menu_qr_basico` / `menu_qr_lite`) | Pro (`menu_qr_visual` / `menu_qr_pro`) | Premium (`menu_qr_marca` / `menu_qr_premium`) |
|---------|------|-----|---------|
| Editor de carta | ✅ | ✅ | ✅ |
| Branding (colores, fuentes) | ✅ | ✅ | ✅ |
| Menú público + slug | ✅ | ✅ | ✅ |
| QR + URL | ✅ | ✅ | ✅ |
| Imágenes por producto | ❌ | ✅ | ✅ |
| Reseñas Google | ❌ (legacy: ✅) | ⚙️ addon (legacy: ✅) | ✅ |
| Propinas MercadoPago | ❌ (legacy: ✅) | ⚙️ addon (legacy: ✅) | ✅ |
| Analytics avanzados | ❌ | ✅ | ✅ |
| Dominio custom | ❌ | ❌ | ✅ (sin UI) |
| Multi-branch | ❌ | ❌ | ✅ |

### Problemas de gating

1. **Legacy vs Nuevo inconsistente**: Plans legacy (`menu_qr`) incluyen tips+reviews por defecto; plans nuevos (`menu_qr_lite`) no. Esto crea experiencias distintas para el mismo tier.
2. **Dominio custom prometido pero no entregado**: Premium habilita `custom_domain_allowed: True` sin UI.
3. **Fallback hardcodeado**: `PLANS_WITH_IMAGES` duplicado en 2 archivos — no es single source of truth.
4. **UX de gating poco clara**: Cuando una feature está bloqueada, el editor muestra un link a la página de planes, pero no explica QUÉ plan necesita ni POR QUÉ la función está deshabilitada.

---

## 7. Flujo Ideal por Tarea

### Estado actual vs ideal

| Tarea | Flujo actual (pasos) | Flujo ideal |
|-------|---------------------|-------------|
| **Crear/editar la carta** | Ir a `/app/carta` o `/app/menu` → usar editor | ✅ OK, 1 paso. El editor es funcional |
| **Ordenar la estructura** | Ir a `/app/settings/online-menu` → scroll hasta Layout Editor → crear/reordenar bloques | Hub Carta → pestaña "Estructura" → drag & drop |
| **Subir imágenes de ítems** | Estar en el editor → click en item → upload (si plan lo permite) | ✅ OK, inline en editor |
| **Subir imágenes de categoría** | Ir a `/app/settings/online-menu` → scroll hasta layout → encontrar categoría → upload | Hub Carta → pestaña "Estructura" → click en categoría → upload |
| **Personalizar apariencia** | Ir a `/app/settings/online-menu` → scroll hasta "Personalización" | Hub Carta → pestaña "Apariencia" |
| **Previsualizar** | Click en `/app/menu/preview` (sidebar menu_qr) O scroll en settings para ver mini-preview | Hub Carta → botón "Preview" siempre visible / panel lateral |
| **Descargar/compartir QR** | Ir a `/app/menu/qr` O encontrar QR dentro de settings | Hub Carta → pestaña "Publicación" → QR + URL + compartir |
| **Configurar tips** | Ir a `/app/settings/online-menu` → scroll hasta "Engagement" → sección Propinas | Hub Carta → pestaña "Engagement" o "Pagos" |
| **Ver menú público** | Click "Ver Carta" en settings → abre `/m/{slug}` | Botón siempre visible en header del hub |
| **Gestionar dominio** | ❌ No existe UI | Hub Carta → pestaña "Publicación" → sección Dominio |

---

## 8. Propuesta de Nueva Arquitectura

### Principio rector

> **Carta Online debe ser un hub unificado centrado en tareas, no una colección de páginas dispersas.**

Cada funcionalidad debe vivir dentro de un solo punto de entrada (`/app/carta`) organizado por pestañas o secciones claras.

### Nueva estructura

| Sección nueva | Qué incluye | Qué reemplaza / absorbe | Beneficio |
|---------------|-------------|------------------------|-----------|
| **Mi Carta** (pestaña Contenido) | Editor de categorías + ítems + imágenes + import/export | `/app/carta` = `/app/menu` (se unifica) | Punto de entrada claro y único para gestionar contenido |
| **Estructura** (pestaña) | Layout blocks, orden de bloques, imágenes de categoría, presets | Layout Editor que hoy está en `/app/settings/online-menu` | El usuario organiza su carta sin salir del hub |
| **Apariencia** (pestaña) | Colores, fuentes, tamaños, logo, posición, watermark, live preview | Secciones "Personalización" y "Logo" de `/app/settings/online-menu` | Flujo visual aislado — cambiar cómo se ve sin mezclarse con engagement |
| **Publicación** (pestaña) | QR (generar/descargar/compartir), URL pública, slug, toggle on/off, dominio custom | `/app/menu/qr` + `/app/menu/preview` + sección "Config General" y "QR Direct" de settings | Todo lo necesario para poner en línea la carta en un solo lugar |
| **Engagement** (pestaña) | Tips MercadoPago (3 modos + OAuth), Reseñas Google, CTA config | `EngagementSettingsSection` de settings | Separación clara entre visual y funcional |
| *(eliminada)* | — | `/app/menu/branding` (redirect) | Eliminar ruta fantasma |
| *(eliminada)* | — | `/app/settings/online-menu` como página monolítica | Desaparece la mega-page |

### Modo restaurante vs menu_qr

| Aspecto | Modo restaurante | Modo menu_qr |
|---------|-----------------|-------------|
| Ruta del hub | `/app/carta` | `/app/carta` (misma ruta) |
| Label en sidebar | "Carta" | "Carta" |
| Pestañas visibles | Contenido, Estructura, Apariencia, Publicación, Engagement | Todas |
| Settings genéricos | `/app/settings` (sin sección online-menu) | `/app/settings` (sin sección online-menu) |

**Beneficio clave**: eliminar la ruta `/app/menu` y la duplicación. Ambos modos usan `/app/carta` con el mismo componente, que ya es lo que sucede hoy bajo la superficie.

---

## 9. Nueva Navegación Sugerida

### Sidebar — Modo menu_qr (antes)

```
Menú QR
  ├─ Carta Online        (/app/menu)
  ├─ Branding             (/app/menu/branding) → redirect!
  ├─ QR y enlaces         (/app/menu/qr)
  └─ Preview público      (/app/menu/preview)
Cuenta
  ├─ Configuración        (/app/settings)
  │    └─ (Carta Online sub-page con todo)
  └─ ...
```

### Sidebar — Modo menu_qr (propuesta)

```
Carta Online
  ├─ Contenido            (/app/carta)              ← editor de categorías e ítems
  ├─ Estructura           (/app/carta/estructura)    ← layout blocks, orden
  ├─ Apariencia           (/app/carta/apariencia)    ← colores, fuentes, logo
  ├─ Publicación          (/app/carta/publicacion)   ← QR, URL, slug, preview, dominio
  └─ Engagement           (/app/carta/engagement)    ← tips, reseñas
Cuenta
  ├─ Plan y facturación
  ├─ Configuración general
  └─ Soporte
```

### Sidebar — Modo restaurante (propuesta)

```
Restaurante Inteligente
  ├─ Mapa de mesas
  ├─ Órdenes
  ├─ Cocina en vivo
  └─ Carta                ← entry point al hub
       ├─ Contenido       (/app/carta)
       ├─ Estructura      (/app/carta/estructura)
       ├─ Apariencia      (/app/carta/apariencia)
       ├─ Publicación     (/app/carta/publicacion)
       └─ Engagement      (/app/carta/engagement)
Gestión Comercial
  └─ ...
Operación
  ├─ Caja
  ├─ Reportes
  └─ Configuración       ← ya no incluye "Carta Online"
```

### Mapa visual del hub

```
/app/carta  ─────────────────────────────────────────────────────
│                                                                │
│  [Contenido] [Estructura] [Apariencia] [Publicación] [Engagement]
│                                                                │
│  ┌─ Header: "Mi Carta" ──── [Ver menú público ↗] [Preview] ─┐│
│  │                                                            ││
│  │  (contenido de la pestaña activa)                          ││
│  │                                                            ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                │
─────────────────────────────────────────────────────────────────
```

---

## 10. Plan por Fases

### Fase 1 — Quick Wins (riesgo bajo, sin breaking changes)

| # | Cambio | Archivos impactados | Esfuerzo | Riesgo |
|---|--------|---------------------|----------|--------|
| 1.1 | Eliminar ruta fantasma `/app/menu/branding` | Borrar `apps/web/src/app/app/menu/branding/page.tsx`. Actualizar sidebar `NAV_CONFIG` para que "Branding" apunte directo a `/app/settings/online-menu` o se elimine. | Bajo | Bajo |
| 1.2 | Renombrar label "Branding" → "Apariencia" en sidebar menu_qr | `sidebar.tsx` — cambiar label | Bajo | Bajo |
| 1.3 | Renombrar label "Carta Online" → "Contenido" para el link a `/app/menu` | `sidebar.tsx` | Bajo | Bajo |
| 1.4 | Agregar links cruzados en el editor de carta | `menu-client.tsx` — agregar banner/links a Apariencia, Publicación, Structure | Bajo | Bajo |
| 1.5 | Eliminar sección QR duplicada de `/app/settings/online-menu` | `online-menu-settings-client.tsx` — remover "QR Access Direct" (ya existe `/app/menu/qr`) | Bajo | Bajo |
| 1.6 | Unificar `PLANS_WITH_IMAGES` en un solo lugar | Crear constante compartida en `features/menu/` e importar desde ambas pages | Bajo | Bajo |

### Fase 2 — Consolidación (riesgo medio, cambios de navegación)

| # | Cambio | Archivos impactados | Esfuerzo | Riesgo |
|---|--------|---------------------|----------|--------|
| 2.1 | Crear layout de tabs en `/app/carta` | Nuevo layout `apps/web/src/app/app/carta/layout.tsx` con tabs: Contenido, Estructura, Apariencia, Publicación, Engagement | Medio | Bajo |
| 2.2 | Migrar Layout Editor a `/app/carta/estructura` | Mover `menu-layout-editor.tsx` a nueva ruta `apps/web/src/app/app/carta/estructura/page.tsx` | Medio | Medio |
| 2.3 | Migrar Branding/Logo a `/app/carta/apariencia` | Extraer secciones de `online-menu-settings-client.tsx` → nueva page `apps/web/src/app/app/carta/apariencia/page.tsx` | Medio | Medio |
| 2.4 | Migrar QR + Slug + Preview a `/app/carta/publicacion` | Combinar `MenuQrPageClient` + config general + preview iframe → nueva page | Medio | Medio |
| 2.5 | Migrar Engagement a `/app/carta/engagement` | Extraer `EngagementSettingsSection` → nueva page `apps/web/src/app/app/carta/engagement/page.tsx` | Medio | Medio |
| 2.6 | Redirect `/app/menu` → `/app/carta` | `menu/page.tsx` → `redirect('/app/carta')` | Bajo | Bajo |
| 2.7 | Redirect `/app/menu/qr` → `/app/carta/publicacion` | Quick redirect | Bajo | Bajo |
| 2.8 | Redirect `/app/menu/preview` → `/app/carta/publicacion` | Quick redirect | Bajo | Bajo |
| 2.9 | Actualizar sidebar para ambos modos | `sidebar.tsx` — nueva estructura de navegación, eliminar entries viejos | Medio | Medio |
| 2.10 | Eliminar `/app/settings/online-menu` (redirect a `/app/carta/apariencia`) | Convertir page en redirect. Mantener redirect temporal 3 meses. | Bajo | Medio |

### Fase 3 — Cleanup y Refactor (riesgo bajo, post-consolidación)

| # | Cambio | Esfuerzo | Riesgo |
|---|--------|----------|--------|
| 3.1 | Eliminar archivo `menu/page.tsx` (tras período de redirect) | Bajo | Bajo |
| 3.2 | Eliminar todos los redirects temporales (branding, menu/qr, menu/preview, settings/online-menu) | Bajo | Bajo |
| 3.3 | Refactorizar `online-menu-settings-client.tsx` en componentes modulares (si no se hizo en Fase 2) | Medio | Bajo |
| 3.4 | Agregar UI para dominio custom (plan Premium) | Medio | Medio |
| 3.5 | Normalizar naming en todo el codebase: decidir entre "Carta" o "Menú" y aplicar consistentemente | Medio | Bajo |
| 3.6 | Eliminar fallback `PLANS_WITH_IMAGES` hardcodeado (tras confirmar que feature flags son confiables) | Bajo | Bajo |
| 3.7 | Agregar UX de gating explícita: cuando una feature está bloqueada, mostrar qué plan la desbloquea | Medio | Bajo |

### Dependencias

```
Fase 1 (independiente) ──→ Fase 2.1 (layout) ──→ Fase 2.2-2.5 (migraciones, paralelas)
                                                ──→ Fase 2.6-2.8 (redirects)
                                                ──→ Fase 2.9 (sidebar)
                                                ──→ Fase 2.10 (settings cleanup)
                                                         ──→ Fase 3 (post-estabilización)
```

---

## 11. Recomendación Final

### El problema raíz

Carta Online **no tiene un hub**. Tiene un editor de contenido por un lado y un cajón de sastre de settings por otro, con páginas satélite sueltas y una ruta fantasma. El usuario tiene que navegar entre 3-4 destinos distintos para gestionar completamente su carta.

### La solución concreta

**Unificar todo bajo `/app/carta` con pestañas.**

Cinco pestañas claras organizadas por tarea:

1. **Contenido** — "¿Qué tiene mi carta?" (categorías, ítems, precios, imágenes)
2. **Estructura** — "¿Cómo se organiza?" (bloques, orden, presets)
3. **Apariencia** — "¿Cómo se ve?" (colores, fuentes, logo)
4. **Publicación** — "¿Cómo la comparto?" (QR, URL, slug, preview, dominio)
5. **Engagement** — "¿Cómo interactúan mis clientes?" (tips, reseñas)

### Por qué esto funciona

- **Un solo punto de entrada** — el usuario siempre va a "Carta" y desde ahí accede a todo
- **Orientado a tareas** — cada pestaña responde a una pregunta concreta del usuario
- **Elimina duplicación** — una sola ruta, un solo componente, un solo lugar para cada función
- **Escala** — si se agregan features (analítica de carta, A/B testing, menú estacional), se agregan pestañas sin romper el modelo
- **Misma experiencia en ambos modos** — restaurante y menu_qr usan `/app/carta` con las mismas pestañas

### Qué hacer primero

Empezar por **Fase 1** (quick wins en 1-2 días): eliminar la ruta fantasma, renombrar labels confusos, agregar links cruzados, eliminar el QR duplicado en settings. Esto mejora la experiencia **hoy** sin refactor.

Luego planificar **Fase 2** como un sprint dedicado: crear el layout de tabs y migrar cada sección. El backend no necesita cambios — toda la reorganización es frontend.
