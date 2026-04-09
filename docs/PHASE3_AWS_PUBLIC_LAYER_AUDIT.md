# Fase 3 — Auditoría Técnica: Capa Pública AWS

**Fecha:** 2026-04-08  
**Última actualización:** 2026-04-08 (post-descubrimiento)  
**Alcance:** Bootstrap completo de infraestructura AWS + capa pública (dominio, CDN, S3, WAF, caché). Incluye la creación de infraestructura core (VPC, ECS, ALB, RDS) como prerequisito. Excluye app autenticada y API privada salvo donde afecten routing público.  
**Estado:** Auditoría + plan de implementación — sin cambios implementados.

---

## A. Resumen ejecutivo

MiRubro tiene la capa de marketing y público correctamente separada en el frontend (App Router con route groups `(marketing)` y `(auth)`), con SEO base funcional (sitemap, robots, metadata, OpenGraph). **No existe absolutamente ninguna infraestructura AWS desplegada** — ni pública ni privada. El proyecto debe construirse desde cero en AWS.

### Decisiones confirmadas (2026-04-08)

| Decisión | Valor confirmado |
|---|---|
| **DNS** | Migrar gestión de Hostinger a AWS Route 53 |
| **Infra AWS existente** | **Nada** — no hay VPC, ECS, ALB, RDS, CloudFront, S3, ACM, Route 53, WAF |
| **Deployment público actual** | No existe. Dominio parqueado en Hostinger |
| **Terraform state** | States separados por capa: `core/base`, `public/dns-certs`, `public/cdn`, `private/app-api` |
| **Dominio canónico** | `www.mirubro.com` (alineado con el código existente) |
| **Consecuencia** | La Fase 3 se redefine como bootstrap AWS completo + capa pública, no solo CDN sobre infra existente |

### Estado real de infraestructura

**En AWS: nada existe.**

**En el repositorio (solo como código/plan, no desplegado):**
- 📄 WAF `.tf` (asociado a ALB via variable — ALB no existe)
- 📄 ElastiCache `.tf` (Redis 7.1 — no desplegado)
- 📄 Secrets Manager + KMS `.tf` (no desplegado)
- 📄 S3 backend config para state (bucket `mirubro-terraform-state` — **no existe**, hay que crearlo)
- ❌ Route 53 — no existe ni en código ni en AWS
- ❌ ACM — no existe ni en código ni en AWS
- ❌ CloudFront — no existe ni en código ni en AWS
- ❌ S3 para assets — no existe ni en código ni en AWS
- ❌ VPC, ECS, ALB, RDS — no existen ni en código ni en AWS

### Descubrimiento DNS real (verificado 2026-04-08)

| Dato | Valor |
|---|---|
| **Registrador** | Hostinger |
| **Nameservers** | `nova.dns-parking.com`, `cosmos.dns-parking.com` (Hostinger parking) |
| **`mirubro.com` A** | `2.57.91.91` (IP de Hostinger parking) |
| **`www.mirubro.com`** | CNAME → `mirubro.com` (misma IP parking) |
| **`api.mirubro.com`** | NXDOMAIN — no existe |
| **`app.mirubro.com`** | NXDOMAIN — no existe |
| **Contenido actual** | Parking page genérica de Hostinger (`noindex, nofollow`) |
| **Server** | `hcdn` (Hostinger CDN) |

---

## B. Dominio canónico y routing público

### B.1 Dominio canónico actual

| Fuente | Dominio usado | Archivo |
|--------|--------------|---------|
| `metadataBase` (root layout) | `https://www.mirubro.com` | `apps/web/src/app/layout.tsx` L22 |
| `sitemap.ts` SITE_URL | `https://www.mirubro.com` | `apps/web/src/app/sitemap.ts` L4 |
| `robots.ts` sitemap | `https://www.mirubro.com/sitemap.xml` | `apps/web/src/app/robots.ts` L12 |
| Homepage canonical | `https://www.mirubro.com` | `apps/web/src/app/(marketing)/page.tsx` L8 |
| Blog posts OG URL | `https://www.mirubro.com/blog/...` | `apps/web/src/app/(marketing)/blog/[slug]/page.tsx` L10 |

**Consistencia: ✅ 100% consistente en `www.mirubro.com`.**

### B.2 Dominio canónico — CONFIRMADO

**Decisión: `www.mirubro.com` es el dominio canónico.** ✅ Confirmado.

Motivos:
- Ya es el dominio hardcodeado en todo el código, sitemap y robots
- `www` se puede apuntar vía CNAME a CloudFront (apex `mirubro.com` requiere alias A record en Route 53)
- Para SEO, `www` es perfectamente válido
- Apex `mirubro.com` redirigirá 301 a `www.mirubro.com`

### B.3 Redirecciones necesarias

| Origen | Destino | Tipo | Dónde implementar |
|--------|---------|------|-------------------|
| `mirubro.com` (apex) | `https://www.mirubro.com` | 301 | CloudFront + Route 53 alias |
| `http://www.mirubro.com` | `https://www.mirubro.com` | 301 | CloudFront viewer protocol |
| `http://mirubro.com` | `https://www.mirubro.com` | 301 | CloudFront o S3 redirect bucket |

**Confirmado:** DNS actualmente gestionado por Hostinger (parking). Se migrará a Route 53 como parte de esta fase. Pasos: crear hosted zone en Route 53, actualizar nameservers en Hostinger.

---

## C. Superficie pública real

### C.1 Marketing (distribución pública principal)

| Ruta | Tipo | Cache-friendly | Notas |
|------|------|----------------|-------|
| `/` | SSR (usa `serverApiFetch` para blog) | ⚠ Parcial — depende de blog API | Homepage; `BlogResourcesSection` hace fetch a API |
| `/pricing` | Client component | ✅ Muy cacheable | Sin metadata server-side hardcodeada |
| `/gestion` | Estático | ✅ Muy cacheable | Landing de vertical |
| `/carta` | Estático | ✅ Muy cacheable | Landing de vertical |
| `/resenas` | Estático | ✅ Muy cacheable | Landing de vertical |
| `/features` | Estático | ✅ Muy cacheable | Features página |
| `/services` | Estático | ✅ Muy cacheable | |
| `/contacto` | Estático/formulario | ✅ Page cacheable | |
| `/soporte` | Estático | ✅ Muy cacheable | |
| `/nosotros` | Estático | ✅ Muy cacheable | |
| `/preguntas-frecuentes` | Estático | ✅ Muy cacheable | |
| `/privacidad` | Estático | ✅ Muy cacheable | |
| `/terminos` | Estático | ✅ Muy cacheable | |
| `/subscribe` | Formulario | ⚠ Page sí, submit no | Bloqueada en robots |

### C.2 Blog

| Ruta | Tipo | Cache-friendly | Notas |
|------|------|----------------|-------|
| `/blog` | SSR (lista de posts) | ⚠ Requiere revalidación | Fetch a API CMS |
| `/blog/[slug]` | ISR (`generateStaticParams`) | ✅ Muy cacheable | Pre-generado en build, revalida por slug |

### C.3 Auth pública

| Ruta | Tipo | Cache-friendly | Notas |
|------|------|----------------|-------|
| `/entrar` | Client | ⚠ Shell cacheable, no contenido | Login form |
| `/olvidar-contrasena` | Client | ⚠ Idem | |
| `/cambiar-contrasena` | Client | ⚠ Idem | |
| `/nueva-contrasena` | Client | ⚠ Idem | |
| `/verificar-email` | Client | ⚠ Idem | |

### C.4 Rutas públicas especiales (requieren trato diferenciado)

| Ruta | Tipo | Cache-friendly | Notas |
|------|------|----------------|-------|
| `/m/[slug]` | `force-dynamic` + `revalidate=0` | ❌ No cachear en CDN | Menú público por negocio — datos cambian en tiempo real |
| `/r/[slug]` | SSR + `cache: 'no-store'` | ❌ No cachear en CDN | Review landing — datos dinámicos |
| `/q/[public_id]` | Route handler (302 redirect) | ❌ No cachear | Resolver QR → redirect a `/m/{slug}` |
| `/plantillas/importar-stock.xlsx` | Route handler | ✅ `max-age=86400` ya setteado | Template Excel generado |

### C.5 Rutas que NO deben entrar en distribución pública

| Ruta | Motivo |
|------|--------|
| `/app/*` | Experiencia autenticada (otro CloudFront o sin CDN) |
| `/admin/*` | Backoffice plataforma |
| `/pos/*` | Terminal POS (app autenticada) |
| `/api/*` | Si se hace proxy — NO debe pasar por CloudFront público |

---

## D. Assets públicos y estrategia S3

### D.1 Estado actual de assets

```
apps/web/public/
├── blog/
│   ├── blog-importar-excel-inventario-cover.svg
│   ├── blog-propinas-digitales-cover.svg
│   ├── blog-qr-resenas-sin-carta-cover.svg
│   └── blog-resenas-menu-qr-cover.svg
├── logo/
│   ├── rubroicono.png          ← favicon (referenciado en root layout)
│   ├── asaa.png                ← ⚠ DEBUG — eliminar
│   └── asd.png                 ← ⚠ DEBUG — eliminar

public/ (raíz repo)
├── logo/
│   ├── mirubro_icon.png
│   └── mirubro_logo.png
```

### D.2 Problemas detectados

| Problema | Ubicación | Severidad |
|----------|-----------|-----------|
| Archivos debug `asaa.png` y `asd.png` | `apps/web/public/logo/` | Baja (pero expuestos públicamente) |
| Logos duplicados en dos ubicaciones | `apps/web/public/logo/` vs `public/logo/` | Media — confusión |
| Blog covers son SVG estáticos en `/public` | `apps/web/public/blog/` | Baja — correcto para ahora |
| Imágenes de blog dinámcos (API) servidas desde Django media | Servidor API | Alta — sin CDN |
| Imágenes de menú QR servidas desde Django media | API `image_url` reescritas por `buildMediaUrl()` | Alta — sin CDN |
| No hay OG image estática para la homepage | Root metadata sin `openGraph.images` | Media |

### D.3 Candidatos a S3 + CloudFront

**Mover a S3 bucket público:**
- ✅ Blog cover SVGs (`/blog/*.svg`) — estáticos, no cambian
- ✅ Logos (`/logo/*`) — después de limpiar debug files
- ✅ Futuros OG images estáticos
- ✅ Futuros screenshots de producto para marketing

**Mantener en Next.js `/public` por ahora:**
- `favicon.ico` / `rubroicono.png` — Next.js los sirve eficientemente

**Requiere estrategia separada (Fase 4+):**
- Imágenes de menú QR (subidas por usuarios → Django media → actualmente sin S3)
- Imágenes de productos/blog dinámicos del CMS (Django media)
- Estos son candidatos a S3 **privado** con CloudFront signed URLs o proxy, no al bucket público

### D.4 Propuesta de bucket y estructura

```
Bucket: mirubro-public-assets-{environment}
Region: us-east-1

├── logo/
│   ├── mirubro_icon.png
│   ├── mirubro_logo.png
│   └── rubroicono.png
├── blog/
│   └── covers/
│       ├── blog-importar-excel-inventario-cover.svg
│       └── ...
├── og/
│   └── default-og.png       ← crear OG image por defecto
└── marketing/
    └── screenshots/          ← futuras imágenes de producto
```

**Naming/versionado:**
- Archivos estáticos: nombre semántico + content hash en deploy (`logo/mirubro_logo.a3f2b.png`)
- O bien: versionado via CloudFront cache invalidation en deploy
- NO usar timestamps — usar hashes o invalidation explícita

**Riesgos de migrar:**
- Bajo para assets estáticos (SVGs/logos): cambiar rutas en código y verificar
- Medio para OG images en blog posts: si Django ya devuelve URLs absolutas del API host, cambiar a S3 requiere actualizar el pipeline del CMS o el `buildMediaUrl()`

---

## E. Estrategia de caché por tipo de recurso

### E.1 Reglas propuestas para CloudFront

| Recurso | Path pattern | TTL recomendado | `Cache-Control` | Notas |
|---------|-------------|-----------------|-----------------|-------|
| **HTML marketing** | `/`, `/pricing`, `/gestion`, `/carta`, etc. | s-maxage=300, stale-while-revalidate=3600 | `public, s-maxage=300, stale-while-revalidate=3600` | 5 min CDN, 1 hora stale — balance entre frescura y performance |
| **HTML blog listing** | `/blog` | s-maxage=300, stale-while-revalidate=3600 | Idem marketing | Revalida cuando se publica nuevo post |
| **HTML blog post** | `/blog/*` | s-maxage=3600, stale-while-revalidate=86400 | `public, s-maxage=3600, stale-while-revalidate=86400` | 1 hora CDN, 1 día stale — posts cambian poco |
| **Next.js static** | `/_next/static/*` | max-age=31536000, immutable | `public, max-age=31536000, immutable` | Next.js ya genera hashes en filenames — cachear indefinidamente |
| **Imágenes S3** | `/assets/*` (S3 origin) | max-age=2592000 | `public, max-age=2592000` | 30 días — versionado por hash o invalidation |
| **Favicon/logos** | `/logo/*`, `/favicon.ico` | max-age=604800 | `public, max-age=604800` | 7 días |
| **Plantillas** | `/plantillas/*` | max-age=86400 | `public, max-age=86400` | Ya tiene header setteado (24h) |
| **Public menu** `/m/*` | `/m/*` | **NO cachear en CloudFront** | `private, no-store` | `force-dynamic` — datos del negocio cambian en tiempo real |
| **Public reviews** `/r/*` | `/r/*` | **NO cachear en CloudFront** | `private, no-store` | Idem — datos dinámicos de config del negocio |
| **QR resolver** `/q/*` | `/q/*` | **NO cachear** | — | Route handler 302 — siempre pasar a origin |
| **Auth pages** | `/entrar`, `/olvidar-*`, `/cambiar-*`, `/verificar-*`, `/nueva-*` | s-maxage=3600 | `public, s-maxage=3600` | Shell HTML cacheable, la lógica es client-side |
| **sitemap.xml** | `/sitemap.xml` | s-maxage=3600 | `public, s-maxage=3600` | Refresco horario — Google no pide más frecuencia |
| **robots.txt** | `/robots.txt` | s-maxage=86400 | `public, s-maxage=86400` | Cambia raramente |

### E.2 Qué NO cachear

- `/m/*`, `/r/*`, `/q/*` — datos dinámicos por negocio
- `/app/*`, `/admin/*`, `/pos/*` — no deben pasar por distribución pública
- Cualquier ruta que setee cookies de autenticación
- POST/PUT/DELETE (CloudFront por defecto solo cachea GET/HEAD)

### E.3 Cautela especial

- **Homepage** (`/`): contiene `BlogResourcesSection` que hace fetch SSR — si la API del blog falla, el CDN serviría la última versión cacheada (stale-while-revalidate lo cubre bien)
- **Blog listing** (`/blog`): similar — si la API CMS no responde, el stale fallback evita una página rota

---

## F. Propuesta de CloudFront público

### F.1 Distribución objetivo

```
CloudFront Distribution: mirubro-public
  Domain: www.mirubro.com  (+ mirubro.com como alias)
  ACM Certificate: *.mirubro.com + mirubro.com (us-east-1, obligatorio para CF)
  Price Class: PriceClass_100 (NA + EU — público latam usa edge NA)
  HTTP/2: enabled
  HTTP/3: enabled (QUIC)
  Compress: true (Brotli + Gzip automático)
  Default root object: (ninguno — Next.js maneja /)
  Viewer protocol policy: redirect-to-https
  WAF: nueva WebACL scope=CLOUDFRONT (separada del WAF ALB actual)
```

### F.2 Origins

| Origin ID | Tipo | Destino | Notas |
|-----------|------|---------|-------|
| `next-origin` | Custom (HTTP) | ALB que corre Next.js + Django (se creará en Sprint 1) | Origin protocol HTTPS, port 443. Keep-alive enabled. |
| `s3-assets` | S3 (OAC) | `mirubro-public-assets-{env}.s3.amazonaws.com` (se creará en Sprint 3) | Origin Access Control — bucket NO público |

### F.3 Cache Behaviors (ordenados por prioridad)

| Prioridad | Path pattern | Origin | Cache Policy | Notas |
|-----------|-------------|--------|-------------|-------|
| 1 | `/_next/static/*` | `next-origin` | Immutable (TTL 365d) | Next.js hashed assets |
| 2 | `/assets/*` | `s3-assets` | LongCache (TTL 30d) | Assets estáticos en S3 |
| 3 | `/logo/*` | `next-origin` o `s3-assets` | MediumCache (TTL 7d) | Logos |
| 4 | `/m/*` | `next-origin` | CachingDisabled | Menú público dinámico |
| 5 | `/r/*` | `next-origin` | CachingDisabled | Reviews público dinámico |
| 6 | `/q/*` | `next-origin` | CachingDisabled | QR resolver |
| 7 | `/app/*` | ❌ NO incluir | — | Bloquear o no rutear |
| 8 | `/admin/*` | ❌ NO incluir | — | Idem |
| 9 | `/pos/*` | ❌ NO incluir | — | Idem |
| 10 (default) | `*` | `next-origin` | Marketing (TTL 5min, stale 1h) | Marketing + blog + auth |

### F.4 Forwarding (qué NO forwardear)

**Cookies — NO forwardear ninguna en behaviors cacheables:**
- `access_token`, `refresh_token`, `csrftoken`, `sessionid` — son de app autenticada
- `mirubro_consent` — cookie de consentimiento, NO afecta rendering server-side
- Excepción: `/m/*`, `/r/*`, `/q/*` → forwardear todo (CachingDisabled ya lo hace)

**Headers — forwardear solo los necesarios:**
- `Host` — siempre (requerido)
- `Accept-Encoding` — CloudFront lo maneja automáticamente con compress=true
- `Accept` — forwardear para content negotiation
- NO forwardear: `Authorization`, `Cookie`, `x-pathname` (internal)

**Query strings:**
- Marketing/blog: NO forwardear (las páginas no usan query params)
- `/m/*`, `/r/*`: forwardear todo (pueden necesitar params)
- `/blog`: forwardear `page`, `category` si se usan en listing

### F.5 Rutas privadas — estrategia de bloqueo

Opción recomendada: **CloudFront Function** que retorne 403 para `/app/*`, `/admin/*`, `/pos/*`:

```javascript
// CloudFront Function (viewer-request)
function handler(event) {
  var uri = event.request.uri;
  if (uri.startsWith('/app/') || uri.startsWith('/admin/') || uri.startsWith('/pos/')) {
    return {
      statusCode: 403,
      statusDescription: 'Forbidden',
      body: { encoding: 'text', data: 'Not available via public CDN' }
    };
  }
  return event.request;
}
```

Esto evita que la distribución pública sirva rutas autenticadas por error. La app privada debería acceder directamente al ALB o mediante una distribución separada (Fase 4).

---

## G. Seguridad pública y WAF base

### G.1 Headers faltantes en capa pública

| Header | Estado actual | Recomendación |
|--------|--------------|---------------|
| `Strict-Transport-Security` | ❌ No existe | Agregar `max-age=63072000; includeSubDomains; preload` via CloudFront response header policy |
| `X-Content-Type-Options` | ❌ No existe | Agregar `nosniff` |
| `X-Frame-Options` | ❌ No existe (CSP tiene `frame-ancestors 'none'` pero solo en Report-Only) | Agregar `DENY` como header real |
| `Referrer-Policy` | ❌ No existe | Agregar `strict-origin-when-cross-origin` |
| `Permissions-Policy` | ❌ No existe | Agregar política restrictiva (camera=(), microphone=(), geolocation=()) |
| CSP | ⚠ Solo Report-Only | Fase futura: promover a enforcement. Por ahora Report-Only es correcto |

**Implementar via:** CloudFront Response Headers Policy (no en middleware Next.js — CloudFront los aplica a nivel de edge, consistente para todos los responses incluyendo S3).

### G.2 WAF para distribución pública (NUEVA, scope CLOUDFRONT)

El WAF actual (`mirubro-admin-waf`) en el repo es scope=REGIONAL y está diseñado para ALB — pero **no está desplegado** ya que no existe ALB. Se migrará al state `core/` cuando se cree la infra base. CloudFront requiere un WAF separado con scope=CLOUDFRONT y región us-east-1.

**Propuesta de nueva WebACL:** `mirubro-public-waf`

| Regla | Prioridad | Acción | Descripción |
|-------|-----------|--------|-------------|
| Geo-restrict (opcional) | 1 | Count/Block | Si se quiere limitar a LATAM + NA + EU |
| Bot Control — Common | 5 | Count → Block | AWS Managed Bot Control (nivel common) — bloquea scrapers conocidos |
| Rate limit global | 10 | Block | 1000 req/5 min por IP (más agresivo que API — marketing no necesita tantas) |
| Rate limit `/m/*` | 15 | Block (429) | 200 req/5 min por IP (menú público, evitar scraping de menús) |
| AWS Core Rule Set | 20 | Override none | OWASP top 10 |
| AWS Known Bad Inputs | 30 | Override none | SQLi, XSS |
| AWS Anonymous IP List | 35 | Count | Monitorear tráfico desde VPNs/Tor/proxies anónimos |

**Costo estimado:** ~$5/mes base WAF + $1/millón requests + managed rules ($1-5/mes cada una).

### G.3 Riesgos de exposición

| Riesgo | Severidad | Mitigación |
|--------|-----------|------------|
| Rutas `/app/*`, `/admin/*` accesibles via CloudFront público | Alta | CloudFront Function que bloquea (sección F.5) |
| Archivos debug en `/logo/asaa.png`, `/logo/asd.png` expuestos | Baja | Eliminar archivos antes de producción |
| CSP solo en Report-Only | Media | Aceptable por ahora; promover a enforce en fase posterior |
| `img-src` permite `via.placeholder.com` y `images.unsplash.com` | Baja | Son para dev/demo; limpiar en producción |
| `TRUSTED_PROXY_DEPTH=1` en Django | Media | Debe ser `2` si CloudFront → ALB (dos proxies) |

---

## H. Archivos/módulos concretos a crear (por state)

### H.0 Bootstrap — prerequisito antes de cualquier Terraform

| Recurso | Tipo | Motivo |
|---------|------|--------|
| Bucket S3 `mirubro-terraform-state` | Manual o script | Backend para todos los states. Debe existir antes de `terraform init` |
| Tabla DynamoDB `mirubro-tf-locks` | Manual o script | Lock table para evitar apply concurrentes |
| IAM user/role con permisos para Terraform | Manual | Necesario para ejecutar `terraform apply` |

> **Nota:** Estos recursos deben crearse manualmente o con un script de bootstrap (no pueden gestionarse por el mismo Terraform que los usa como backend).

### H.1 State: `core/base` — Infraestructura fundacional

**State key:** `core/base/terraform.tfstate`

| Archivo | Contenido |
|---------|-----------|
| `infra/terraform/core/main.tf` | Provider AWS, backend S3 con key `core/base/terraform.tfstate` |
| `infra/terraform/core/vpc.tf` | VPC, subnets públicas/privadas, NAT gateway, internet gateway, route tables |
| `infra/terraform/core/security-groups.tf` | SGs para ALB, ECS, RDS, ElastiCache |
| `infra/terraform/core/rds.tf` | RDS PostgreSQL 16, subnet group, parameter group |
| `infra/terraform/core/elasticache.tf` | Redis 7.1 (mover del Terraform actual) |
| `infra/terraform/core/secrets.tf` | Secrets Manager + KMS (mover del Terraform actual) |
| `infra/terraform/core/ecr.tf` | ECR repos para API (Django) y Web (Next.js) |
| `infra/terraform/core/ecs.tf` | ECS cluster, task definitions, services, ALB, target groups, auto-scaling |
| `infra/terraform/core/variables.tf` | Variables del core |
| `infra/terraform/core/outputs.tf` | VPC ID, subnet IDs, ALB ARN/DNS, ECS cluster name, SG IDs |

### H.2 State: `public/dns-certs` — DNS y certificados

**State key:** `public/dns-certs/terraform.tfstate`

| Archivo | Contenido |
|---------|-----------|
| `infra/terraform/public-dns/main.tf` | Provider, backend S3 con key `public/dns-certs/terraform.tfstate`, data source `terraform_remote_state` al core |
| `infra/terraform/public-dns/route53.tf` | Hosted zone `mirubro.com`, records para `www`, apex redirect, ACM validation |
| `infra/terraform/public-dns/acm.tf` | Certificado ACM en us-east-1: `*.mirubro.com` + `mirubro.com`, DNS validation |
| `infra/terraform/public-dns/variables.tf` | Variables (domain name, etc.) |
| `infra/terraform/public-dns/outputs.tf` | Zone ID, ACM cert ARN, nameservers |

### H.3 State: `public/cdn` — CloudFront y distribución

**State key:** `public/cdn/terraform.tfstate`

| Archivo | Contenido |
|---------|-----------|
| `infra/terraform/public-cdn/main.tf` | Provider, backend S3, data sources (remote state de core y dns-certs) |
| `infra/terraform/public-cdn/s3.tf` | Bucket assets públicos + OAC policy |
| `infra/terraform/public-cdn/cloudfront.tf` | Distribución pública: origins, behaviors, OAC |
| `infra/terraform/public-cdn/waf-public.tf` | WebACL scope=CLOUDFRONT |
| `infra/terraform/public-cdn/cloudfront-functions.tf` | CF Function para bloqueo rutas privadas |
| `infra/terraform/public-cdn/headers-policy.tf` | Response Headers Policy (HSTS, X-Frame, etc.) |
| `infra/terraform/public-cdn/variables.tf` | Variables |
| `infra/terraform/public-cdn/outputs.tf` | CloudFront distribution ID, domain name, S3 bucket ARN |

### H.4 State: `security/admin-hardening` — EXISTENTE (refactorizar)

**State key:** `security/admin-hardening/terraform.tfstate` (actual)

**Acción:** El WAF actual (`waf.tf`) permanece aquí solo si se mantiene scope REGIONAL asociado al ALB del core. ElastiCache y Secrets se moverán al state `core/base`. Esto requiere `terraform state mv` o import en el nuevo state + remove del antiguo.

| Cambio | Detalle |
|--------|---------|
| Mover `elasticache.tf` → `core/` | Parte de la infra base, no de admin-hardening |
| Mover `secrets.tf` → `core/` | Secrets de Django/DB/MFA son del core, no solo de admin |
| `waf.tf` permanece o se mueve a `core/` | Depende de si se mantiene WAF REGIONAL separado del WAF CLOUDFRONT |

### H.5 Archivos Terraform existentes — estado

| Archivo actual | Destino | Acción |
|---|---|---|
| `infra/terraform/main.tf` | Refactorizar | Backend key actual es `security/admin-hardening` — cada state tendrá su propio `main.tf` |
| `infra/terraform/variables.tf` | Refactorizar | Variables se distribuyen entre los states correspondientes |
| `infra/terraform/outputs.tf` | Refactorizar | Outputs se distribuyen entre los states correspondientes |
| `infra/terraform/waf.tf` | Evaluar | Puede quedar en `core/` o en `security/` — el WAF CLOUDFRONT irá en `public/cdn` |
| `infra/terraform/elasticache.tf` | → `core/` | |
| `infra/terraform/secrets.tf` | → `core/` | |
| `infra/terraform/production.tfvars.example` | Refactorizar | Un `.tfvars.example` por state |
| `infra/terraform/README.md` | Reescribir | Documentar la nueva estructura multi-state |

### H.6 Archivos frontend a modificar

| Archivo | Cambio | Cuándo |
|---------|--------|--------|
| `apps/web/Dockerfile` | **Reescribir para producción**: multi-stage build, `next build` + `next start`, no `npm run dev` | Sprint 1 (prerequisito para ECS) |
| `services/api/Dockerfile` | Crear/actualizar para producción: gunicorn, collectstatic, no runserver | Sprint 1 (prerequisito para ECS) |
| `apps/web/src/middleware.ts` | Agregar `TRUSTED_PROXY_DEPTH` awareness si se usa CF | Sprint 3 (go-live) |
| `apps/web/next.config.mjs` | Agregar `remotePatterns` para `assets.mirubro.com` / S3 dominio si se migran imágenes | Sprint 3 |
| `apps/web/src/lib/api-url.ts` | Si se cambia el origin de media a S3, actualizar `buildMediaUrl` | Fase 4+ (imágenes dinámicas) |

### H.7 Archivos a limpiar (pre-deploy)

| Archivo | Acción |
|---------|--------|
| `apps/web/public/logo/asaa.png` | Eliminar |
| `apps/web/public/logo/asd.png` | Eliminar |

### H.8 Separación: cambios frontend vs infraestructura

**Infraestructura core (Terraform `core/base`):**
- VPC, subnets, NAT, IGW
- RDS PostgreSQL, ElastiCache Redis
- ECS cluster, task definitions, services
- ALB, target groups, listeners
- ECR repos, security groups
- Secrets Manager + KMS

**Infraestructura pública (Terraform `public/dns-certs` + `public/cdn`):**
- Route 53 hosted zone + records
- ACM certificados
- CloudFront distribución + behaviors
- S3 assets públicos
- WAF público (scope CLOUDFRONT)
- CloudFront Functions
- Response Headers Policy

**Frontend / Backend (post-infra):**
- Limpiar debug assets
- Dockerfile de producción para Next.js (`next build` + `next start`)
- Dockerfile de producción para Django (gunicorn)
- `TRUSTED_PROXY_DEPTH=2` en Django settings
- Mover assets estáticos a S3
- Configurar env vars de producción (`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL`, etc.)

---

## I. Backlog priorizado de implementación (revisado — desde cero)

> **Contexto:** No hay infraestructura AWS existente. El backlog comienza por el bootstrap del estado de Terraform y la infraestructura core, luego monta la capa pública encima.

### Sprint 0 — Bootstrap de Terraform (prerequisito)

| # | Tarea | Tipo | Riesgo | Dependencia |
|---|-------|------|--------|-------------|
| 0.1 | Crear cuenta AWS (si no existe) o verificar acceso IAM | Manual | N/A | Ninguna |
| 0.2 | Crear bucket S3 `mirubro-terraform-state` con versionamiento + encryption | Script/manual | Bajo | 0.1 |
| 0.3 | Crear tabla DynamoDB `mirubro-tf-locks` | Script/manual | Bajo | 0.1 |
| 0.4 | Crear estructura de directorios: `infra/terraform/{core,public-dns,public-cdn}` | Repo | Nulo | Ninguna |
| 0.5 | Crear `main.tf` para cada state con backend S3 y keys separados | Repo | Bajo | 0.2, 0.3 |

### Sprint 1 — Infraestructura core (VPC + ECS + ALB + RDS)

| # | Tarea | Tipo | Riesgo | Dependencia |
|---|-------|------|--------|-------------|
| 1.1 | VPC: 2 AZs, subnets públicas + privadas, NAT gateway, IGW | Terraform `core/` | Medio | 0.5 |
| 1.2 | Security groups: ALB (443 inbound), ECS (8000/3000 from ALB SG), RDS (5432 from ECS SG) | Terraform `core/` | Medio | 1.1 |
| 1.3 | RDS PostgreSQL 16: subnet group, parameter group, instance `db.t3.micro` (staging) | Terraform `core/` | Medio | 1.1, 1.2 |
| 1.4 | ElastiCache Redis 7.1: replication group, subnet group (migrar `.tf` existente) | Terraform `core/` | Medio | 1.1, 1.2 |
| 1.5 | Secrets Manager + KMS: Django SECRET_KEY, DB credentials, MFA key (migrar `.tf` existente) | Terraform `core/` | Bajo | 1.1 |
| 1.6 | ECR repos: `mirubro-api`, `mirubro-web` | Terraform `core/` | Bajo | 0.5 |
| 1.7 | Dockerfile de producción para Django (gunicorn + collectstatic) | Repo | Medio | Ninguna |
| 1.8 | Dockerfile de producción para Next.js (`next build` + `next start`) | Repo | Medio | Ninguna |
| 1.9 | ECS cluster + task definitions + services (API + Web) | Terraform `core/` | Alto | 1.1–1.6, 1.7, 1.8 |
| 1.10 | ALB: listener HTTPS:443, target groups para API (:8000) y Web (:3000) | Terraform `core/` | Medio | 1.1, 1.2, 1.9 |
| 1.11 | ACM cert temporal para ALB (puede ser `*.mirubro.com` o un dominio temp) | Terraform `core/` | Bajo | 1.10 |
| 1.12 | WAF REGIONAL asociado a ALB (migrar `waf.tf` existente) | Terraform `core/` | Bajo | 1.10 |
| 1.13 | Validar acceso a la app vía ALB DNS temporal (`*.us-east-1.elb.amazonaws.com`) | Manual | Bajo | 1.9, 1.10 |

**Gate:** ✅ App funcionando vía ALB temporal antes de continuar.

### Sprint 2 — DNS y certificados públicos

| # | Tarea | Tipo | Riesgo | Dependencia |
|---|-------|------|--------|-------------|
| 2.1 | Crear hosted zone Route 53 para `mirubro.com` | Terraform `public-dns/` | Bajo | Sprint 0 |
| 2.2 | ACM certificate `*.mirubro.com` + `mirubro.com` en us-east-1 (DNS validation) | Terraform `public-dns/` | Bajo | 2.1 |
| 2.3 | Bajar TTL de records actuales en Hostinger a 300s (48h antes de migración) | Manual en Hostinger | Bajo | Ninguna |
| 2.4 | Actualizar nameservers en Hostinger → apuntar a NS de Route 53 | Manual en Hostinger | **Alto** | 2.1, 2.2 validados |
| 2.5 | Verificar propagación DNS y validación ACM | Manual | Medio | 2.4 |
| 2.6 | Crear record `api.mirubro.com` → ALB | Terraform `public-dns/` | Medio | 2.5, Sprint 1 completado |
| 2.7 | Crear record temporal `www.mirubro.com` → ALB (pre-CloudFront) | Terraform `public-dns/` | Medio | 2.5 |
| 2.8 | Validar acceso a API y Web vía dominios reales | Manual | Medio | 2.6, 2.7 |

**Gate:** ✅ DNS migrado, certificados validados, app accesible por dominio real.

### Sprint 3 — CloudFront y capa pública CDN

| # | Tarea | Tipo | Riesgo | Dependencia |
|---|-------|------|--------|-------------|
| 3.1 | Crear S3 bucket `mirubro-public-assets-{env}` con OAC policy | Terraform `public-cdn/` | Bajo | Sprint 0 |
| 3.2 | Subir assets estáticos a S3 (logos, blog covers) | Script/manual | Bajo | 3.1 |
| 3.3 | Eliminar archivos debug (`asaa.png`, `asd.png`) | Frontend | Nulo | Ninguna |
| 3.4 | Crear WAF WebACL `mirubro-public-waf` (scope CLOUDFRONT, Count mode) | Terraform `public-cdn/` | Bajo | Ninguna |
| 3.5 | Crear CloudFront Function para bloqueo de rutas privadas | Terraform `public-cdn/` | Bajo | Ninguna |
| 3.6 | Crear Response Headers Policy (HSTS, X-Frame-Options, etc.) | Terraform `public-cdn/` | Bajo | Ninguna |
| 3.7 | Crear CloudFront distribution con origins (ALB + S3) y behaviors | Terraform `public-cdn/` | Medio | 2.2 (ACM), 3.1 (S3), 3.4 (WAF), 3.5, 3.6 |
| 3.8 | Verificar distribución con dominio temporal `d111xxx.cloudfront.net` | Manual | Bajo | 3.7 |
| 3.9 | Actualizar record `www.mirubro.com` → CloudFront (reemplaza ALB directo) | Terraform `public-dns/` | Medio | 3.8 validado |
| 3.10 | Crear redirect apex `mirubro.com` → `www.mirubro.com` (S3 redirect + CF o Route 53) | Terraform | Medio | 3.9 |
| 3.11 | Actualizar `TRUSTED_PROXY_DEPTH=2` en Django (CloudFront → ALB = 2 proxies) | Backend env | Bajo | 3.9 |
| 3.12 | Smoke test completo en producción | Manual | — | 3.9 |

**Gate:** ✅ `www.mirubro.com` servido por CloudFront, apex redirige, HSTS activo.

### Sprint 4 — Hardening y observabilidad (post go-live)

| # | Tarea | Tipo | Riesgo | Dependencia |
|---|-------|------|--------|-------------|
| 4.1 | Promover WAF público de Count → Block (después de 48-72h) | Terraform | Bajo | 3.12 OK |
| 4.2 | Activar Bot Control en WAF público | Terraform | Bajo | Monitorear Count |
| 4.3 | Monitorear WAF logs y ajustar rate limits | Manual | — | 3.4 |
| 4.4 | Limpiar `img-src` CSP (quitar placeholder/unsplash) | Frontend | Bajo | Verificar uso |
| 4.5 | Configurar CloudWatch alarms (5xx rate, cache hit ratio, WAF blocks) | Terraform | Bajo | 3.7 |
| 4.6 | Considerar geo-restriction si el tráfico lo justifica | Terraform | Bajo | Datos reales |

---

## J. Riesgos y validaciones

### J.1 Validaciones resueltas

| # | Validación | Estado | Resolución |
|---|-----------|--------|------------|
| V-1 | ¿Dominio `mirubro.com` registrado y con acceso? | ✅ Resuelto | Registrado en Hostinger, actualmente parqueado |
| V-2 | ¿DNS gestionado en Route 53 o externo? | ✅ Resuelto | Externo (Hostinger). Se migrará a Route 53 |
| V-3 | ¿Existe ALB con listener HTTPS ya creado? | ✅ Resuelto | **No existe nada.** Debe crearse desde cero |
| V-4 | ¿El state path de Terraform necesita separación? | ✅ Resuelto | Sí: `core/base`, `public/dns-certs`, `public/cdn`, `private/app-api` |
| V-5 | ¿Next.js está desplegado en ECS/EC2? | ✅ Resuelto | **No.** Solo existe en desarrollo local |
| V-6 | ¿Dominio canónico? | ✅ Resuelto | `www.mirubro.com` |

### J.2 Validaciones pendientes (pre-implementación)

| # | Validación | Cómo verificar |
|---|-----------|----------------|
| V-7 | ¿Existe cuenta AWS creada con acceso IAM? | Verificar con equipo |
| V-8 | ¿Hay credenciales de panel de Hostinger para cambiar nameservers? | Verificar con equipo |
| V-9 | ¿Presupuesto mensual estimado aprobado? (~$150-300/mes staging) | Decisión de negocio |
| V-10 | ¿Hay CI/CD definido para los deploys? (GitHub Actions, etc.) | Decisión técnica |

### J.3 Riesgos técnicos

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Costo AWS mayor al esperado en core | Media | Alto | Empezar con instancias mínimas (`t3.micro`/`t3.small`), NAT gateway solo 1 AZ, RDS single-AZ staging |
| DNS cut-over causa downtime | Baja | Alto | Bajar TTL 48h antes. Validar CF con dominio temporal primero. Propagación NS toma hasta 48h |
| ECS tasks no arrancan (config, secrets, networking) | Media | Alto | Validar Dockerfiles localmente. Usar task-level logging desde el inicio |
| ACM validation falla | Baja | Bloquea Sprint 2-3 | Usar DNS validation vía Route 53 (automático si hosted zone existe) |
| CloudFront cachea ruta privada por error | Baja | Alto | CF Function + behaviors explícitos. Test con dominio temporal |
| WAF bloquea tráfico legítimo (falso positivo) | Baja-Media | Medio | Empezar en Count mode, promover a Block después de observar |
| `TRUSTED_PROXY_DEPTH` incorrecto | Baja | Alto | Configurar a 2 desde el primer request CF → ALB |
| Dockerfile de dev usado en producción | Alta si no se corrige | Alto | Crear Dockerfiles de producción en Sprint 1 (multi-stage build) |

---

## K. Recomendación final: plan de ejecución

### Principio: incremental, validable, reversible

1. **Primero el core** (Sprint 0-1): No se puede montar CDN sin un origin. VPC + ECS + ALB + RDS primero.
2. **DNS como segundo paso** (Sprint 2): Crear hosted zone y certificados. Migrar nameservers.
3. **CloudFront como tercer paso** (Sprint 3): Montado sobre la infra core ya validada.
4. **Cada sprint tiene un gate de validación** — no avanzar sin el gate previo OK.

### Orden estricto de ejecución

```
[0] Bootstrap: S3 state bucket + DynamoDB locks + IAM
    ↓
[1] Core: VPC → SGs → RDS → ElastiCache → Secrets → ECR → Dockerfiles → ECS → ALB → WAF REGIONAL
    ↓
    ← GATE: app funcionando vía ALB temporal (*.elb.amazonaws.com)
    ↓
[2] DNS: Route 53 hosted zone → ACM cert → cambiar NS en Hostinger → records api/www
    ↓
    ← GATE: DNS propagado, cert validado, app accesible por dominio real
    ↓
[3] CDN: S3 assets → WAF CLOUDFRONT → CF Function → CloudFront distribution → test con d111xxx.cloudfront.net
    ↓
    ← GATE: todo funciona vía dominio temporal de CF
    ↓
[4] Go-live: www → CF, apex redirect, TRUSTED_PROXY_DEPTH=2, smoke test
    ↓
[5] Hardening: WAF Count→Block, Bot Control, alarms, observabilidad
```

### Estimación de costo mensual (staging mínimo)

| Recurso | Estimación |
|---|---|
| ECS Fargate (2 tasks × 0.25 vCPU / 0.5 GB) | ~$25/mes |
| ALB | ~$22/mes |
| RDS `db.t3.micro` single-AZ | ~$15/mes |
| ElastiCache `cache.t3.micro` | ~$13/mes |
| NAT Gateway (1 AZ) | ~$32/mes |
| Route 53 hosted zone | ~$0.50/mes |
| CloudFront (bajo tráfico) | ~$1-5/mes |
| WAF (2 WebACLs + managed rules) | ~$15/mes |
| S3 (assets + state) | ~$1/mes |
| Secrets Manager (3 secrets) | ~$1.20/mes |
| **Total staging estimado** | **~$125-130/mes** |

> Producción con multi-AZ, instancias más grandes, y backups sube a ~$250-400/mes.

### Estructura de carpetas propuesta

```
infra/terraform/
├── bootstrap/              ← Script one-time para S3 bucket + DynamoDB
│   └── bootstrap.sh
├── core/                   ← State: core/base/terraform.tfstate
│   ├── main.tf
│   ├── vpc.tf
│   ├── security-groups.tf
│   ├── rds.tf
│   ├── elasticache.tf
│   ├── secrets.tf
│   ├── ecr.tf
│   ├── ecs.tf
│   ├── alb.tf
│   ├── waf.tf              ← WAF REGIONAL (migrado del actual)
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── public-dns/             ← State: public/dns-certs/terraform.tfstate
│   ├── main.tf
│   ├── route53.tf
│   ├── acm.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── public-cdn/             ← State: public/cdn/terraform.tfstate
│   ├── main.tf
│   ├── s3.tf
│   ├── cloudfront.tf
│   ├── waf-public.tf
│   ├── cloudfront-functions.tf
│   ├── headers-policy.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
└── _legacy/                ← Archivos .tf actuales (referencia, no ejecutar)
    ├── main.tf
    ├── waf.tf
    ├── elasticache.tf
    ├── secrets.tf
    ├── variables.tf
    ├── outputs.tf
    ├── production.tfvars.example
    └── README.md
```

---

*Auditoría basada en código real del repositorio `mirubrodigital` y verificación DNS en vivo a fecha 2026-04-08. Decisiones confirmadas por el equipo. Todos los paths son relativos a la raíz del monorepo.*
