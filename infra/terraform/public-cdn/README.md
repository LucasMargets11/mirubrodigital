# Public CDN — Terraform Layer

State key: `public/cdn/terraform.tfstate`

## What this creates

| Resource | Purpose |
|---|---|
| CloudFront distribution | HTTPS CDN for `www.mirubro.com` + `mirubro.com` |
| CloudFront Function (`edge_router`) | 301 apex → www + 403 for private routes |
| CloudFront cache policies ×3 | Marketing (5 min), blog (5 min + qs), static (1 year) |
| CloudFront origin request policy | Forwards Host + cookies to ALB |
| Response headers policy | HSTS, X-Content-Type-Options, X-Frame-Options, XSS-Protection |
| S3 bucket (public-assets) | Static marketing assets served via OAC |
| S3 bucket policy | CloudFront-only reads (OAC) |
| WAF v2 WebACL (CLOUDFRONT) | Common rules, bad inputs, rate limits |
| Route 53 A records | www + apex → CloudFront alias |

## Architecture

```
                      ┌────────────────────┐
        Internet ────►│   CloudFront CDN   │
                      │  (WAF + headers)   │
                      └────┬──────────┬────┘
                           │          │
              /m/* /r/* /q/*      /assets/*
              /blog* /_next/*     (S3 OAC)
              * (default)
                           │          │
                      ┌────▼───┐ ┌────▼────┐
                      │  ALB   │ │   S3    │
                      │ :443   │ │ bucket  │
                      └────┬───┘ └─────────┘
                      ┌────▼───┐
                      │  ECS   │
                      │  web   │
                      └────────┘

  Separate path (NOT through CloudFront):

        api.mirubro.com ────► ALB :443 ────► ECS api (Django)
```

## ALB origin protocol

The distribution connects to the ALB via **HTTPS** (`origin_protocol_policy = "https-only"`). This requires the HTTPS listener in `core/alb.tf` to be uncommented and applied **before** this layer runs.

Pre-requisites (ordered):

1. `core/base` applied — ALB exists
2. `private-app` applied — ECS services running
3. `public-dns` applied — ACM cert issued and validated
4. Core HTTPS listener **uncommented and re-applied** with the ACM cert ARN
5. **Then** apply this layer

## Cache behaviors

| Path pattern | Origin | Cache | Notes |
|---|---|---|---|
| `/m/*` | ALB | **Disabled** | Public menus — `force-dynamic`, real-time data |
| `/r/*` | ALB | **Disabled** | Public reviews — `no-store` fetch |
| `/q/*` | ALB | **Disabled** | QR redirect (API route → 302 to /m/) |
| `/blog*` | ALB | 5 min, qs key | Listing uses `?page=N&categoria=slug` |
| `/_next/static/*` | ALB | 1 year | Immutable Next.js build assets |
| `/assets/*` | S3 | 1 year | Marketing images/logos via OAC |
| `*` (default) | ALB | 5 min | Marketing SSR pages (home, pricing, etc.) |

## Route decisions

### `/api/*` — NOT served by this distribution

The Django REST API lives at `api.mirubro.com`, which points directly to the ALB
via an A-alias record in `public-dns/route53.tf`. This is intentional:

- No CloudFront caching overhead for API calls
- Simpler CORS configuration (single origin)
- Rate limiting at the WAF is only for the public web surface
- API-specific WAF rules can be added independently later (ALB WAF scope)

If a user manually hits `www.mirubro.com/api/v1/...`, the request falls into the
default behavior. The ALB routes it to Django, which responds with its own
`Cache-Control` headers. The marketing cache policy has `min_ttl = 0`, so
no-cache responses from Django are respected and not stored.

The Next.js `/api/health` route (port 3000) also sets `force-dynamic` →
CloudFront respects the origin's `Cache-Control: no-store`.

### `/app/*`, `/admin/*`, `/pos/*` — blocked with 403 at edge

The `edge_router` CloudFront Function returns HTTP 403 for these paths **before
the request reaches the ALB**. This is a deliberate security decision:

- Private routes are not exposed to the public CDN surface
- No risk of accidentally caching authenticated content
- Zero origin load for blocked requests

**Implication**: authenticated users cannot access the dashboard via
`www.mirubro.com/app/`. A separate entry point is required:

| Option | How |
|---|---|
| `app.mirubro.com` → ALB | New A-alias record in `public-dns`, login redirects to this subdomain |
| Separate CloudFront distribution | Private CDN with auth-aware cache behaviors (future) |

The login page (`/entrar`) and registration are marketing routes under `(auth)`
and are **not blocked** — they work normally on `www.mirubro.com`. The post-login
redirect target must be updated to point to the app entry point once it exists.

### `/blog` query params

The blog listing page uses server-side pagination with `?page=N&categoria=slug`.
A dedicated `/blog*` behavior uses a cache policy that includes `page` and
`categoria` in the cache key. This ensures:

- `/blog?page=1` and `/blog?page=2` are cached separately
- `/blog?categoria=marketing` is cached separately from `/blog`
- Blog posts (`/blog/[slug]`) also match this behavior but don't use query
  strings — they're SSG with `generateStaticParams` and cache correctly

## WAF rules

| Priority | Rule | Action |
|---|---|---|
| 10 | AWSManagedRulesCommonRuleSet | Block (SQLi, XSS, OWASP Top 10) |
| 20 | AWSManagedRulesKnownBadInputsRuleSet | Block (Log4j, etc.) |
| 30 | Global rate limit (1000 req/5 min/IP) | Block |
| 40 | `/m/*` rate limit (200 req/5 min/IP) | Block |

## Usage

```bash
cd infra/terraform/public-cdn
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars if needed
terraform init
terraform plan   # review ~16 resources
terraform apply
```

## Outputs

| Output | Description |
|---|---|
| `cloudfront_distribution_id` | For cache invalidation commands |
| `cloudfront_domain_name` | The `d*.cloudfront.net` domain |
| `s3_assets_bucket_name` | For `aws s3 sync` in CI/CD |
| `s3_assets_bucket_arn` | For IAM policies |
| `waf_public_web_acl_arn` | For monitoring dashboards |

## Post-apply validation

```bash
# Check CloudFront
CF_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront get-distribution --id $CF_ID --query 'Distribution.Status'
# → "Deployed"

# DNS propagation
dig +short www.mirubro.com
# → d*.cloudfront.net → IPs

# HTTPS
curl -sI https://www.mirubro.com | head -5
# → HTTP/2 200

# Apex redirect
curl -sI https://mirubro.com | grep -i location
# → location: https://www.mirubro.com/

# Security headers
curl -sI https://www.mirubro.com | grep -i strict-transport
# → strict-transport-security: max-age=63072000; includeSubdomains; preload

# Private route blocking
curl -sI https://www.mirubro.com/app/
# → HTTP/2 403

# Public menu (no cache)
curl -sI https://www.mirubro.com/m/demo-restaurant | grep -i x-cache
# → Miss from cloudfront (always)

# Blog pagination
curl -sI "https://www.mirubro.com/blog?page=2&categoria=marketing"
# → HTTP/2 200 (different from /blog?page=1)
```

## Cache invalidation

```bash
CF_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```
