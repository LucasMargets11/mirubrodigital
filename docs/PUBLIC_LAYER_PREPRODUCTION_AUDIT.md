# Auditoría de Pre-Producción — Capa Pública MiRubro

**Fecha:** 2026-04-08  
**Scope:** Frontend público Next.js 16+ App Router  
**Objetivo:** Dejar la capa pública lista para producción con SEO alto, performance sólida y preparación CDN  
**Restricción:** No incluye AWS, Terraform, ni infraestructura  

---

## A. Resumen ejecutivo

La capa pública de MiRubro tiene una base sólida gracias al trabajo de Fase 1 (separación marketing/private, metadata base, robots, sitemap, fonts, providers) y Fase 2 (consentimiento y control de scripts). Sin embargo, existen **6 problemas críticos** y **12 problemas moderados** que impiden apuntar a un puntaje 90+ en Lighthouse y a un SEO técnico excelente.

### Problema raíz más importante

**La home page es dinámica en cada request** porque `BlogResourcesSection` es un server component async que llama a la API del blog en cada render. Esto impide SSG/ISR en la ruta más importante del sitio y destruye TTFB + FCP.

### Tabla de estado

| Área | Estado | Nota |
|------|--------|------|
| Metadata base | ✅ resuelto (Fase 1) | 10 de 16 páginas marketing tienen metadata completa |
| Robots/Sitemap | ✅ resuelto (Fase 1) | Correcto, con 14 rutas estáticas + blog dinámico |
| Fonts | ✅ resuelto (Fase 1) | `next/font/google` con `display: swap`, aislamiento de menu fonts |
| Consent/Scripts | ✅ resuelto (Fase 2) | ConsentProvider + CookieBanner, framework listo |
| QueryClient isolation | ✅ resuelto (Fase 1) | No carga en marketing, solo en `/app` y `/pos` |
| Metadata faltante | 🔴 crítico | `/pricing`, `/features`, `/services`, `/entrar` sin metadata |
| OG images | 🔴 crítico | Solo blog tiene `openGraph.images`. Home y landing pages no |
| Home dinámica | 🔴 crítico | `BlogResourcesSection` fuerza SSR en cada request |
| Hero sin imágenes reales | 🟡 moderado | Placeholders CSS, no hay LCP image real |
| framer-motion en home | 🟡 moderado | ~50KB gzipped solo para scroll animation |
| Pricing client-only | 🟡 moderado | 7 componentes billing sin code-splitting |
| Cache-Control | 🟡 moderado | Solo 1 ruta tiene headers explícitos |
| JSON-LD parcial | 🟡 moderado | Solo blog y FAQ. Falta en home, product pages, Organization |
| Assets de debug | 🟠 menor | `asd.png`, `asaa.png` en `/public/logo/` |
| Páginas huérfanas | 🟠 menor | `/features` y `/services` sin links internos |

---

## B. Estado actual de optimización pública

### B.1 Rutas públicas auditadas

| Ruta | Tipo | Render | Metadata | OG images | JSON-LD | Canonical |
|------|------|--------|----------|-----------|---------|-----------|
| `/` (home) | Server | 🔴 Dinámico (blog fetch) | ✅ | ❌ falta | ❌ falta | ✅ |
| `/blog` | Server async | Dinámico (fetch) | ✅ | ❌ falta | ✅ Blog | ✅ |
| `/blog/[slug]` | Server async | ✅ SSG (`generateStaticParams`) | ✅ `generateMetadata` | ✅ por post | ✅ BlogPosting | ✅ |
| `/pricing` | 🔴 Client | Client-only | ❌ falta | ❌ falta | ❌ falta | ❌ falta |
| `/gestion` | Server | ✅ Estático | ✅ | ❌ falta | ❌ falta | ✅ |
| `/carta` | Server | ✅ Estático | ✅ | ❌ falta | ❌ falta | ✅ |
| `/resenas` | Server | ✅ Estático | ✅ | ❌ falta | ❌ falta | ✅ |
| `/nosotros` | Server | ✅ Estático | ✅ | ❌ falta | ❌ falta | ✅ |
| `/contacto` | Server | ✅ Estático | ✅ | ❌ falta | ❌ falta | ✅ |
| `/soporte` | Server | ✅ Estático | ✅ | ❌ falta | ❌ falta | ✅ |
| `/preguntas-frecuentes` | Server | ✅ Estático | ✅ | ❌ falta | ✅ FAQPage | ✅ |
| `/features` | Server | ✅ Estático | ❌ falta | ❌ falta | ❌ falta | ❌ falta |
| `/services` | Server | ✅ Estático | ❌ falta | ❌ falta | ❌ falta | ❌ falta |
| `/privacidad` | Server | ✅ Estático | ✅ | — | — | ✅ |
| `/terminos` | Server | ✅ Estático | ✅ | — | — | ✅ |
| `/entrar` | Server (form client) | ✅ Estático | ❌ falta | — | — | ❌ falta |
| `/m/[slug]` | Server async | 🔴 `force-dynamic` | ❌ falta | — | — | — |
| `/r/[slug]` | Server async | Dinámico (`no-store`) | ✅ `generateMetadata` | — | — | — |
| `/q/[public_id]` | Route handler | Redirect 302 | — | — | — | — |
| `/subscribe` | Server | Redirect | — | — | — | — |
| `/blog/preview/[id]` | Server async | Dinámico | ✅ `noindex` | — | — | — |

### B.2 Lo que ya está resuelto (Fase 1 + Fase 2)

1. **✅ Separación marketing/private**: `(marketing)/layout.tsx` no carga `QueryClientProvider`, providers de app, ni ninguna dependencia pesada de la app autenticada.
2. **✅ Robots.ts**: Bloquea correctamente `/app/`, `/admin/`, `/pos/`, `/q/`, `/m/`, `/r/`, `/subscribe/`.
3. **✅ Sitemap.ts**: 14 rutas estáticas + blog dinámico. Prioridades correctas.
4. **✅ Fonts optimizados**: `next/font/google` con `display: swap`, CSS variables, solo Inter + Space Grotesk en marketing. 10 menu fonts aislados en `/m/` layout.
5. **✅ ConsentProvider**: Lightweight context, localStorage. No impacta render.
6. **✅ CookieBanner**: Render condicional, suprimido en rutas operativas.
7. **✅ Blog [slug]**: `generateStaticParams` + `generateMetadata` + JSON-LD BlogPosting.
8. **✅ Blog preview**: `noindex` correcto.
9. **✅ No hay scripts externos**: No tracking, no analytics third-party cargando.
10. **✅ No hay `@import url()` en CSS**: globals.css limpio, solo Tailwind directives.

---

## C. Hallazgos de performance y render

### C.1 🔴 CRÍTICO — Home page forzada a SSR dinámico

**Archivo:** `src/components/marketing/sections/blog-resources.tsx`  
**Impacto:** TTFB, FCP, LCP de la home page

`BlogResourcesSection` es un server component async que ejecuta:
```ts
const [listing, categories] = await Promise.all([
    getBlogListing({ page: 1 }),
    getBlogCategories(),
]);
```

Esto hace que **toda la home page se renderice en cada request** (SSR dinámico), eliminando cualquier posibilidad de SSG o ISR. La home es la ruta con priority 1.0 en el sitemap.

**Solución recomendada:**  
- Extraer `BlogResourcesSection` a un componente con ISR propio (revalidate cada 60-300s)
- O convertirlo a client component con `useQuery` y skeleton de loading
- O usar `unstable_cache` / `next/cache` en las funciones de fetch del blog

### C.2 🔴 CRÍTICO — Pricing page es 100% client component

**Archivo:** `src/app/(marketing)/pricing/page.tsx`  
**Impacto:** Bundle JS, FCP, SEO (sin metadata), no indexable

La page completa es `'use client'` con 7 imports pesados de `@/features/billing/`:
- `PlansBundles`
- `PlansBuilderWizard`
- `CommercialPlanBuilder`
- `GestionComercialPlanBuilder`
- `GestionComercialComparisonTable`
- `MenuQrPlanBuilder` + `MenuQrComparisonTable`
- `QrReviewsPlanBuilder`

Todos estos se cargan eagerly sin code-splitting. No puede exportar metadata por ser client component.

**Solución recomendada:**  
- Server component wrapper con metadata estática
- Dynamic imports con `next/dynamic` para cada builder (carga lazy por vertical)
- Suspense boundaries con skeletons

### C.3 🟡 MODERADO — framer-motion en home (~50KB gzipped)

**Archivo:** `src/components/marketing/sections/expanding-panel.tsx`  
**Impacto:** Bundle JS público, Time to Interactive

`ExpandingPanelSection` es `'use client'` e importa:
- `useScroll`, `useTransform`, `motion` de `framer-motion`
- Scroll listener continuo con transforms (width, opacity, y, borderRadius)

~50KB de JS solo para un efecto de expansión visual en scroll.

**Solución recomendada:**  
- Reemplazar con CSS `scroll-driven-animations` (soporte 85%+ browsers)
- O usar `IntersectionObserver` + CSS transitions (0KB de JS extra)
- O al menos `next/dynamic` con `ssr: false` para no bloquear SSR

### C.4 🟡 MODERADO — Hero sin LCP image real

**Archivo:** `src/components/marketing/sections/hero.tsx`  
**Impacto:** LCP score

El hero section usa **placeholders CSS** (divs con backgrounds) en lugar de imágenes reales para los mockups de dashboard, tablet y mobile. No hay elemento `<Image>` ni `<img>` con `priority`, por lo que el LCP candidate es el texto del heading.

**Estado actual:** Texto como LCP es aceptable pero **no hay hero image preparada**.

**Cuando haya assets definitivos:**  
- Agregar `<Image priority>` para el mockup principal
- El hero image debería ser el LCP element explícito
- Preload via `<link rel="preload">` si es crítico

### C.5 🟡 MODERADO — Blog listing page es dinámica sin ISR

**Archivo:** `src/app/(marketing)/blog/page.tsx`  
**Impacto:** TTFB del blog index

Blog page es server async con fetch en cada request (no tiene `revalidate`). No usa `generateStaticParams`.

**Solución recomendada:** Agregar `export const revalidate = 300` (5 min ISR) o `unstable_cache`.

### C.6 🟡 MODERADO — Marketing nav con scroll listener

**Archivo:** `src/components/navigation/marketing-nav.tsx`  
**Impacto:** Leve en JS público (el listener es ligero)

Client component con `useScrollDirection()` hook que monitorea scroll para hide/show del nav. Aceptable pero representa JS obligatorio en toda ruta marketing.

### C.7 🟢 OK — Bibliotecas pesadas aisladas

Verificado que **echarts** (~300KB), **xlsx** (~150KB) y **recharts** no se importan en ningún componente marketing. Solo cargan en `/app/` (dashboard, reportes, exports). Buen tree-shaking.

### C.8 🟢 OK — Menu fonts aislados

Los 10 Google Fonts de personalización de menú solo se aplican via `menuFontsVariablesClassName` en `m/layout.tsx`, no en marketing.

---

## D. Hallazgos sobre imágenes y assets

### D.1 Inventario de `/public/`

| Archivo | Tipo | Observación |
|---------|------|-------------|
| `logo/rubroicono.png` | PNG | ✅ Logo principal, usado como favicon y en nav |
| `logo/asd.png` | PNG | 🔴 Archivo de debug — eliminar |
| `logo/asaa.png` | PNG | 🔴 Archivo de debug — eliminar |
| `blog/blog-importar-excel-inventario-cover.svg` | SVG | ✅ Blog cover |
| `blog/blog-propinas-digitales-cover.svg` | SVG | ✅ Blog cover (900×506) |
| `blog/blog-qr-resenas-sin-carta-cover.svg` | SVG | ✅ Blog cover (900×506) |
| `blog/blog-resenas-menu-qr-cover.svg` | SVG | ✅ Blog cover (900×506) |

**Total:** 7 archivos, 2 son basura.

### D.2 Uso de `next/image` — bien implementado

| Archivo | Props | Observación |
|---------|-------|-------------|
| `marketing-nav.tsx` | `fill`, `sizes` | ✅ Logo responsive |
| `blog-resources.tsx` | `fill`, `priority` (cond), `sizes` | ✅ Correcto |
| `BlogFeaturedHero.tsx` | `fill`, `priority`, `sizes` | ✅ Above-fold priority |
| `BlogCard.tsx` | `fill`, `loading="lazy"`, `sizes` (3-tier) | ✅ Lazy, responsive |
| `BlogPostHero.tsx` | `fill`, `priority`, `sizes` | ✅ Hero con priority |
| `BlogPostContent.tsx` | `width=36`, `height=36` | ✅ Small logo, explicit dims |

**Bien:** Todas las instancias usan `sizes`, `fill` o explicit dimensions. Blog images tienen `priority` en above-fold.

### D.3 🔴 Favicon como PNG — debería ser multi-formato

**Archivo:** `src/app/layout.tsx` → `icons: { icon: '/logo/rubroicono.png' }`

Solo hay un PNG como favicon. Falta:
- `favicon.ico` (legacy browsers)
- `apple-touch-icon.png` (192×192 o 180×180)
- `icon.svg` (modern browsers, scalable)
- Entrada `manifest` para PWA (opcional)

### D.4 🔴 No hay OG image default para el sitio

Ninguna marketing page (excepto blog posts individuales) define `openGraph.images`. Cuando se comparte `/`, `/pricing`, `/gestion`, `/carta`, etc. en redes sociales, **no hay preview image**.

**Solución recomendada:**
- Crear `src/app/opengraph-image.png` (1200×630) como fallback global
- O agregar `openGraph.images` en root layout metadata
- Crear OG images específicas para cada product page (gestion, carta, resenas)

### D.5 🟡 Blog covers son SVG — limitaciones de social sharing

Blog covers son SVGs que se sirven via `next/image` con `dangerouslyAllowSVG: true`. SVGs no son universalmente soportados como OG images en redes sociales (Facebook, LinkedIn rechazan SVG en `og:image`).

**Solución recomendada:** Generar versiones PNG/WebP de los covers. O usar `opengraph-image.tsx` con generación dinámica.

### D.6 Preparación CDN futura

| Recurso | Ubicación actual | Ready para CDN | Acción |
|---------|-----------------|----------------|--------|
| Logo | `/public/logo/` | ✅ | Servir con `Cache-Control: public, max-age=31536000, immutable` |
| Blog covers (SVG) | `/public/blog/` | ✅ | Cache largo, versionado por contenido |
| Blog images (API) | `localhost:8000` | ❌ | Cuando haya S3 + CloudFront, configurar `remotePatterns` |
| Menu item images | API media | ❌ | Requiere `img-src` en CSP + `remotePatterns` en next.config |

### D.7 `next.config.mjs` — `remotePatterns` a limpiar

```js
remotePatterns: [
  { protocol: 'https', hostname: 'via.placeholder.com' },   // → eliminar en prod
  { protocol: 'https', hostname: 'images.unsplash.com' },   // → mantener si blog usa
  { protocol: 'http', hostname: 'localhost', port: '8000' }, // → solo dev
]
```

En producción deberá agregarse el dominio del CDN/S3.

---

## E. Hallazgos SEO técnicos

### E.1 🔴 Páginas con metadata faltante

| Página | Priority sitemap | Impacto | Estado |
|--------|-----------------|---------|--------|
| `/pricing` | 0.8 | 🔴 Máximo | `'use client'` impide metadata. Sin título, descripción, canonical, OG |
| `/features` | 0.6 | 🔴 Alto | Sin metadata. Además, página huérfana (sin links internos) |
| `/services` | 0.6 | 🔴 Alto | Sin metadata. Página completamente huérfana |
| `/entrar` | — | 🟡 Medio | Sin metadata (auth, no indexada, pero debería tener título) |

### E.2 🔴 Páginas huérfanas (zero internal links)

| Página | En sitemap | En nav | En footer | Links entrantes | Problema |
|--------|-----------|--------|-----------|----------------|----------|
| `/features` | ✅ | ❌ | ❌ | 1 (buried component `industries.tsx`) | Google puede descartarla |
| `/services` | ✅ | ❌ | ❌ | 0 | **Completamente huérfana** |

**Decisión necesaria:** ¿Se mantienen `/features` y `/services` como rutas independientes? Si sí, necesitan links desde nav/footer. Si no, sacarlas del sitemap y poner `noindex`.

### E.3 🟡 OG Images faltantes en páginas clave

| Página | `openGraph.images` | Resultado al compartir |
|--------|-------------------|----------------------|
| `/` (home) | ❌ | Sin preview image en redes |
| `/pricing` | ❌ | Sin preview (ni tiene metadata) |
| `/gestion` | ❌ | Sin preview image |
| `/carta` | ❌ | Sin preview image |
| `/resenas` | ❌ | Sin preview image |
| `/blog` (index) | ❌ | Sin preview image |
| `/blog/[slug]` | ✅ | Cover image del post |
| `/contacto` | ❌ | Sin preview image |
| `/nosotros` | ❌ | Sin preview image |

### E.4 🟡 JSON-LD incompleto

| Esquema | Existe | Ubicación | Faltante |
|---------|--------|-----------|----------|
| `Blog` | ✅ | `/blog` page | — |
| `BlogPosting` | ✅ | `/blog/[slug]` | — |
| `FAQPage` | ✅ | `/preguntas-frecuentes` | — |
| `Organization` | ❌ | — | Debería estar en home o root layout |
| `WebSite` + `SearchAction` | ❌ | — | Para sitelinks en Google |
| `Product` / `SoftwareApplication` | ❌ | — | Para product pages (gestion, carta, resenas) |
| `BreadcrumbList` | ❌ | — | Para navegación estructurada |
| `LocalBusiness` | ❌ | — | Si aplica al tipo de negocio |

### E.5 🟡 Canonical URLs inconsistentes

- Las 10 páginas con metadata definen `alternates.canonical` correctamente con `https://www.mirubro.com/...`
- `/pricing`, `/features`, `/services` no tienen canonical (no tienen metadata)
- **No hay `hreflang`** — no necesario por ahora (solo español)

### E.6 🟡 Posible canibalización SEO

| Par de páginas | Riesgo | Observación |
|----------------|--------|-------------|
| `/features` vs `/gestion` | 🟡 Medio | Ambas describen funcionalidades comerciales. Si `/features` se elimina, no hay conflicto |
| `/services` vs product pages | 🟡 Medio | `/services` describe las 3 verticales, igual que product pages individuales. Redundante |

**Recomendación:** Evaluar si `/features` y `/services` tienen razón de existir. Las product pages (`/gestion`, `/carta`, `/resenas`) ya cubren ese contenido con mejor SEO.

### E.7 ✅ Enlazado interno correcto entre páginas principales

| Desde | Hacia | Método |
|-------|-------|--------|
| Nav | `/gestion`, `/carta`, `/resenas`, `/pricing`, `/blog` | Links directos |
| Footer | `/gestion`, `/carta`, `/resenas`, `/pricing`, `/contacto`, `/soporte`, `/preguntas-frecuentes`, `/nosotros`, `/blog`, `/privacidad`, `/terminos` | Links organizados en columnas |
| Home (Hero) | `/entrar`, `/pricing` | CTAs principales |
| Home (Products) | `/gestion`, `/carta`, `/resenas` | Cards con links |
| Product pages | `/entrar`, `/pricing?service=X`, `/contacto` | CTAs de conversión |

### E.8 🟡 `/m/[slug]` bloqueado en robots pero sin `noindex` en page

`robots.ts` bloquea `/m/`, pero la page en `m/[slug]/page.tsx` no exporta metadata con `robots: { index: false }`. Si un link directo se indexa (por ejemplo, desde un link externo), Google podría crawlear e indexar pese al `robots.txt` disallow (que es una sugerencia, no una directiva).

**Solución:** Agregar `metadata.robots = { index: false, follow: false }` en la page o en `m/layout.tsx`.

---

## F. Estado de caché y preparación para CDN futura

### F.1 Estado actual de caché por ruta

| Ruta | Render actual | Cache-Control actual | Recomendación |
|------|--------------|---------------------|---------------|
| `/` (home) | 🔴 SSR dinámico | Next.js default (no-cache) | ISR revalidate=300 (5 min) |
| `/blog` | SSR dinámico | Next.js default | ISR revalidate=300 |
| `/blog/[slug]` | SSG via `generateStaticParams` | Next.js auto (long cache) | ✅ Ya correcto. ISR con revalidate |
| `/pricing` | Client render | Next.js default | SSG wrapper + client hydration |
| `/gestion` | ✅ Estático | Next.js auto | `s-maxage=86400, stale-while-revalidate` |
| `/carta` | ✅ Estático | Next.js auto | `s-maxage=86400, stale-while-revalidate` |
| `/resenas` | ✅ Estático | Next.js auto | `s-maxage=86400, stale-while-revalidate` |
| `/contacto` | ✅ Estático | Next.js auto | `s-maxage=86400, stale-while-revalidate` |
| `/nosotros` | ✅ Estático | Next.js auto | `s-maxage=86400, stale-while-revalidate` |
| legal pages | ✅ Estático | Next.js auto | `s-maxage=604800` (1 semana) |
| `/m/[slug]` | `force-dynamic` | `no-store` | ✅ Correcto (contenido en tiempo real) |
| `/r/[slug]` | Dinámico (`no-store`) | `no-store` | ✅ Correcto |
| `/q/[public_id]` | Route handler | — | `no-store` (redirect) |
| Assets `/public/` | Automático Next.js | `public, max-age=31536000` | ✅ Ya correcto |

### F.2 Headers explícitos de Cache-Control

Solo existe **1 ruta** con Cache-Control explícito:

```
/plantillas/importar-stock.xlsx → Cache-Control: public, max-age=86400
```

**Faltante:** `next.config.mjs` no define `headers()` para rutas marketing. Next.js aplica defaults pero no son óptimos para CDN.

### F.3 Recomendación de headers para producción (CDN-ready)

```js
// next.config.mjs headers() — preparar ahora
{
  source: '/(gestion|carta|resenas|nosotros|contacto|soporte|preguntas-frecuentes)',
  headers: [{ key: 'Cache-Control', value: 'public, s-maxage=86400, stale-while-revalidate=3600' }],
},
{
  source: '/(privacidad|terminos)',
  headers: [{ key: 'Cache-Control', value: 'public, s-maxage=604800, stale-while-revalidate=86400' }],
},
{
  source: '/blog',
  headers: [{ key: 'Cache-Control', value: 'public, s-maxage=300, stale-while-revalidate=60' }],
},
```

### F.4 Preparación para CDN futura

| Elemento | Estado | Acción requerida |
|----------|--------|-----------------|
| Static assets fingerprinted | ✅ | Next.js auto-fingerprints `_next/static/` |
| `metadataBase` | ✅ | `https://www.mirubro.com` |
| Image optimization | ✅ | `next/image` funciona con CDN image loader |
| CSP `img-src` | 🟡 | Agregar dominio CDN/S3 cuando exista |
| `remotePatterns` | 🟡 | Agregar dominio CDN cuando exista |
| Font self-hosting | ✅ | `next/font/google` inline los fonts en build |
| SVG handling | 🟡 | `dangerouslyAllowSVG` es válido pero necesita revisión de seguridad |

---

## G. Archivos concretos involucrados

### G.1 Archivos que más impactan en performance pública

| # | Archivo | Impacto | Tipo de problema |
|---|---------|---------|-----------------|
| 1 | `src/components/marketing/sections/blog-resources.tsx` | 🔴 Máximo | Fuerza SSR dinámico en home |
| 2 | `src/app/(marketing)/pricing/page.tsx` | 🔴 Máximo | Client-only, sin metadata, bundle pesado |
| 3 | `src/components/marketing/sections/expanding-panel.tsx` | 🟡 Alto | framer-motion ~50KB en home |
| 4 | `src/components/navigation/marketing-nav.tsx` | 🟡 Medio | Scroll listener en todas las páginas |
| 5 | `src/app/layout.tsx` | 🟡 Medio | Falta OG image default, favicon incompleto |
| 6 | `src/app/(marketing)/blog/page.tsx` | 🟡 Medio | Dinámico sin ISR |

### G.2 Archivos que más impactan en SEO

| # | Archivo | Impacto | Tipo de problema |
|---|---------|---------|-----------------|
| 1 | `src/app/(marketing)/pricing/page.tsx` | 🔴 Máximo | Sin metadata (sitemap priority 0.8) |
| 2 | `src/app/(marketing)/features/page.tsx` | 🔴 Alto | Sin metadata, huérfana |
| 3 | `src/app/(marketing)/services/page.tsx` | 🔴 Alto | Sin metadata, completamente huérfana |
| 4 | `src/app/(marketing)/page.tsx` | 🟡 Alto | Sin OG image, sin JSON-LD Organization |
| 5 | `src/app/layout.tsx` | 🟡 Alto | Sin OG image default global |
| 6 | `src/app/m/[slug]/page.tsx` | 🟡 Medio | Sin noindex explícito en page |

### G.3 Archivos a modificar en implementación de optimización

| # | Archivo | Cambio necesario |
|---|---------|-----------------|
| 1 | `src/components/marketing/sections/blog-resources.tsx` | ISR/cache, eliminar SSR dinámico |
| 2 | `src/app/(marketing)/pricing/page.tsx` | Server wrapper + metadata + dynamic imports |
| 3 | `src/components/marketing/sections/expanding-panel.tsx` | Reemplazar framer-motion por CSS/IO |
| 4 | `src/app/layout.tsx` | OG image default, favicon multi-formato |
| 5 | `src/app/(marketing)/page.tsx` | JSON-LD Organization + WebSite |
| 6 | `src/app/(marketing)/features/page.tsx` | Metadata o eliminar ruta |
| 7 | `src/app/(marketing)/services/page.tsx` | Metadata o eliminar ruta |
| 8 | `src/app/(marketing)/gestion/page.tsx` | OG image, JSON-LD SoftwareApplication |
| 9 | `src/app/(marketing)/carta/page.tsx` | OG image, JSON-LD SoftwareApplication |
| 10 | `src/app/(marketing)/resenas/page.tsx` | OG image, JSON-LD SoftwareApplication |
| 11 | `src/app/(marketing)/blog/page.tsx` | ISR revalidate, OG image |
| 12 | `src/app/m/[slug]/page.tsx` | Agregar noindex metadata |
| 13 | `src/app/(auth)/entrar/page.tsx` | Metadata básica (título, descripción) |
| 14 | `apps/web/next.config.mjs` | Headers Cache-Control, limpiar remotePatterns |
| 15 | `public/logo/asd.png` | Eliminar |
| 16 | `public/logo/asaa.png` | Eliminar |

---

## H. Backlog priorizado de optimización

### Sprint Opt-1: Correcciones críticas de SEO + render (impacto inmediato)

| # | Task | Archivo(s) | Impacto | Esfuerzo |
|---|------|-----------|---------|----------|
| H.1 | Resolver home dinámica: ISR o cache en `BlogResourcesSection` | `blog-resources.tsx`, `blog/_api.ts` | 🔴 Máximo | Medio |
| H.2 | Refactorizar `/pricing`: server wrapper + metadata + dynamic imports | `pricing/page.tsx` | 🔴 Máximo | Alto |
| H.3 | Agregar metadata a `/features` y `/services` (o decidir eliminarlas) | `features/page.tsx`, `services/page.tsx` | 🔴 Alto | Bajo |
| H.4 | Crear OG image default global (1200×630) | `layout.tsx`, `public/og-image.png` | 🔴 Alto | Bajo |
| H.5 | Agregar `noindex` a `/m/[slug]` | `m/[slug]/page.tsx` o `m/layout.tsx` | 🟡 Medio | Mínimo |
| H.6 | Eliminar assets de debug | `public/logo/asd.png`, `asaa.png` | 🟠 Bajo | Mínimo |

### Sprint Opt-2: Performance + JSON-LD + internal linking

| # | Task | Archivo(s) | Impacto | Esfuerzo |
|---|------|-----------|---------|----------|
| H.7 | Reemplazar framer-motion en `expanding-panel` por CSS/IO | `expanding-panel.tsx` | 🟡 Alto | Medio |
| H.8 | Agregar ISR a `/blog` index page (revalidate=300) | `blog/page.tsx` | 🟡 Medio | Bajo |
| H.9 | JSON-LD Organization + WebSite en home | `(marketing)/page.tsx` | 🟡 Medio | Bajo |
| H.10 | JSON-LD SoftwareApplication en product pages | `gestion/`, `carta/`, `resenas/` | 🟡 Medio | Medio |
| H.11 | OG images específicas por product page | React OG gen o PNG estáticos | 🟡 Medio | Medio |
| H.12 | Resolver páginas huérfanas: link `/features`, `/services` desde nav/footer (o eliminar) | `marketing-nav.tsx`, `marketing-footer.tsx` | 🟡 Medio | Bajo |
| H.13 | Metadata para `/entrar` | `(auth)/entrar/page.tsx` | 🟡 Bajo | Mínimo |

### Sprint Opt-3: Cache headers + favicon + preparación CDN

| # | Task | Archivo(s) | Impacto | Esfuerzo |
|---|------|-----------|---------|----------|
| H.14 | Agregar `headers()` en next.config.mjs para Cache-Control | `next.config.mjs` | 🟡 Medio | Bajo |
| H.15 | Favicon multi-formato (ico + apple-touch + svg) | `public/`, `layout.tsx` | 🟡 Medio | Bajo |
| H.16 | Limpiar `remotePatterns` (quitar placeholder en prod) | `next.config.mjs` | 🟠 Bajo | Mínimo |
| H.17 | Generar PNG/WebP de blog covers SVG para OG sharing | `public/blog/` | 🟡 Medio | Medio |
| H.18 | JSON-LD BreadcrumbList en product + blog pages | múltiples | 🟠 Bajo | Medio |

### Sprint Opt-4: Depende de assets definitivos / producción

| # | Task | Dependencia | Nota |
|---|------|------------|------|
| H.19 | Hero image real (screenshot dashboard) + `<Image priority>` | Assets finales | LCP improvement |
| H.20 | CSP `img-src` para dominio CDN/S3 | Infraestructura | Cuando haya S3 |
| H.21 | `remotePatterns` con dominio CDN | Infraestructura | Cuando haya CloudFront |
| H.22 | `loading.tsx` skeletons para rutas con data fetching | Diseño UX | Mejora percibida |

---

## I. Checklist pre-producción para apuntar a 90+/100

### Performance (Lighthouse)

| Check | Estado | Categoría |
|-------|--------|-----------|
| Home es estática o ISR | ❌ Dinámica SSR | **Cambio en código (H.1)** |
| Pricing tiene server wrapper | ❌ Client only | **Cambio en código (H.2)** |
| framer-motion eliminado/lazy | ❌ Carga eager ~50KB | **Cambio en código (H.7)** |
| No hay render-blocking resources | ✅ | Resuelto Fase 1 |
| Fonts con display:swap | ✅ | Resuelto Fase 1 |
| Images con sizes/priority | ✅ | Correcto |
| Lazy loading en below-fold images | ✅ | Correcto (blog cards) |
| JS bundle excluye libs pesadas | ✅ | echarts/xlsx solo en /app |
| QueryClient aislado | ✅ | Resuelto Fase 1 |
| LCP element claro con preload | ❌ No hay hero image | **Depende de assets (H.19)** |
| Preconnect a origins externos | ✅ | `next/font` maneja esto |
| loading.tsx en rutas async | ❌ No existen | **Depende de diseño (H.22)** |

### SEO (Lighthouse)

| Check | Estado | Categoría |
|-------|--------|-----------|
| Todas las marketing pages tienen title | ❌ 4 faltantes | **Cambio en código (H.2, H.3, H.13)** |
| Todas las marketing pages tienen description | ❌ 4 faltantes | **Cambio en código** |
| Todas las marketing pages tienen canonical | ❌ 4 faltantes | **Cambio en código** |
| OG image default global | ❌ | **Cambio en código (H.4)** |
| OG images en pages principales | ❌ | **Cambio en código (H.11)** |
| robots.txt correcto | ✅ | Resuelto Fase 1 |
| sitemap.xml completo | ✅ | Resuelto Fase 1 |
| `lang="es"` en html | ✅ | Resuelto |
| No hay contenido duplicado | ⚠️ features/services overlap | **Decisión pendiente (H.3/H.12)** |
| JSON-LD Organization | ❌ | **Cambio en código (H.9)** |
| JSON-LD en product pages | ❌ | **Cambio en código (H.10)** |
| Internal linking completo | ❌ 2 huérfanas | **Cambio en código (H.12)** |
| noindex en rutas privadas públicas | ❌ /m/[slug] sin noindex | **Cambio en código (H.5)** |
| Blog tiene structured data | ✅ | Correcto |
| FAQ tiene structured data | ✅ | Correcto |

### Best Practices / Accessibility (Lighthouse)

| Check | Estado | Categoría |
|-------|--------|-----------|
| CSP headers | ✅ Report-Only | Correcto para pre-prod |
| No mixed content | ✅ | Todo HTTPS en metadata |
| favicon correcto | ❌ Solo PNG | **Cambio en código (H.15)** |
| Image alt texts | ✅ | Presentes en todas las Image |
| HTML lang attribute | ✅ | `lang="es"` |

### Resumen de blockers por categoría

| Categoría | Cambios en código ahora | Depende de producción/CDN | Depende de assets |
|-----------|------------------------|--------------------------|-------------------|
| Performance | H.1, H.2, H.7, H.8 | — | H.19 |
| SEO | H.3, H.4, H.5, H.9, H.10, H.11, H.12, H.13 | — | — |
| Cache | H.14 | H.20, H.21 | — |
| Assets | H.6, H.15, H.16, H.17 | — | H.19 |
| UX | — | — | H.22 |

---

## J. Recomendación final: qué conviene implementar ahora antes de tocar AWS

### Prioridad inmediata (Sprint Opt-1) — 6 tasks, máximo impacto

1. **H.1 — Resolver home dinámica**: Es el #1 blocker para performance. Un `revalidate` o `unstable_cache` en las funciones de blog puede convertir la home de SSR → ISR con un cambio mínimo.

2. **H.2 — Refactorizar `/pricing`**: Segundo mayor impacto. Server wrapper con metadata estática + `next/dynamic` para los builders eliminará el page sin SEO más importante del sitio.

3. **H.4 — OG image default**: Un solo PNG de 1200×630 en `public/og-default.png` + referencia en root metadata resuelve el problema de sharing para todo el sitio de una vez.

4. **H.3 — Metadata en `/features` y `/services`**: Decisión binaria — o agregar metadata y links, o sacar del sitemap y poner `noindex`. Cualquiera se hace en minutos.

5. **H.5 — noindex en `/m/[slug]`**: Una línea de código. Riesgo real de indexación no deseada.

6. **H.6 — Eliminar assets de debug**: Dos archivos a borrar.

### Prioridad alta (Sprint Opt-2) — 7 tasks, mejora compuesta

7. **H.7 — Reemplazar framer-motion**: -50KB de JS público. Alto esfuerzo pero alto retorno.
8. **H.8 — ISR en blog index**: Una línea (`export const revalidate = 300`).
9. **H.9 + H.10 — JSON-LD Organization + product pages**: Mejora visibilidad en SERPs.
10. **H.11 — OG images de product pages**: Mejora sharing en redes.
11. **H.12 — Resolver huérfanas**: Linkear o eliminar /features, /services.
12. **H.13 — Metadata /entrar**: Mínimo esfuerzo.

### Dejar para después de AWS

- H.14 (Cache headers) — Útil ahora pero más efectivo con CDN
- H.19 (Hero image real) — Requiere assets de diseño
- H.20, H.21 (CSP/remotePatterns CDN) — Requiere infraestructura
- H.22 (loading.tsx) — Mejora percibida, no bloquea SEO ni performance score

### Estimación de impacto esperado

| Métrica | Antes | Después de Opt-1+Opt-2 | Nota |
|---------|-------|------------------------|------|
| TTFB home | ~500-1000ms (SSR) | ~50-100ms (ISR/SSG) | H.1 |
| FCP home | ~1.5s | ~0.8s | H.1 + H.7 |
| JS bundle home | ~150KB+ | ~100KB | H.7 |
| SEO coverage | 10/16 pages | 16/16 pages | H.2 + H.3 + H.13 |
| OG images | 1/16 pages | 16/16 pages | H.4 + H.11 |
| JSON-LD schemas | 3 | 8+ | H.9 + H.10 |
| Lighthouse Performance | ~65-75 | ~85-90 | Combined |
| Lighthouse SEO | ~80 | ~95-100 | Combined |

> **Sin tocar AWS, los Sprints Opt-1 y Opt-2 pueden llevar la capa pública de ~70 a ~90 en Lighthouse.** El 10% restante depende de CDN, hero image real, y cache headers de producción.
