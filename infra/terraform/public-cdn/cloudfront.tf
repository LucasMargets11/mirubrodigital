# ═══════════════════════════════════════════════════════════════════════════════
# CloudFront Distribution — Public Web
# ═══════════════════════════════════════════════════════════════════════════════
#
# Origin architecture:
#   1. ALB origin (default) — serves Next.js SSR marketing pages
#   2. S3 origin (/assets/*) — static marketing assets via OAC
#
# Behaviors:
#   - /m/*             → ALB (no cache — dynamic public menus)
#   - /r/*             → ALB (no cache — dynamic public reviews)
#   - /q/*             → ALB (no cache — QR redirect API route)
#   - /blog*           → ALB (short cache, query strings in key)
#   - /_next/static/*  → ALB (1 year — immutable build output)
#   - /assets/*        → S3  (1 year — marketing static assets)
#   - * (default)      → ALB (5 min cache — marketing SSR)
#
# Blocked at edge (403):
#   - /app/*   — authenticated dashboard
#   - /admin/* — staff-only backoffice
#   - /pos/*   — POS terminal
#
# NOT served here (lives at api.mirubro.com → ALB directly):
#   - /api/*   — Django REST API
#
# The CloudFront Function handles:
#   1. apex → www 301 redirect (SEO canonicalization)
#   2. 403 for private routes (auth routes not exposed via public CDN)

# ── CloudFront Function: edge router ─────────────────────────────────────────
#
# Runs on viewer-request for the default behavior.
# Handles apex redirect and private route blocking at the edge.

resource "aws_cloudfront_function" "edge_router" {
  name    = "${local.prefix}-edge-router"
  runtime = "cloudfront-js-2.0"
  publish = true
  comment = "Apex redirect + private route blocking"

  code = <<-JSEOF
    function handler(event) {
      var request = event.request;
      var host = request.headers.host.value;
      var uri = request.uri;

      // 1. Apex → www redirect
      if (host === '${local.fqdn_apex}') {
        return {
          statusCode: 301,
          statusDescription: 'Moved Permanently',
          headers: {
            location: { value: 'https://${local.fqdn_www}' + uri }
          }
        };
      }

      // 2. Block private routes — these must not be served via public CDN.
      //    Authenticated users access them via a separate entry point.
      if (uri === '/app' || uri.startsWith('/app/') ||
          uri === '/admin' || uri.startsWith('/admin/') ||
          uri === '/pos' || uri.startsWith('/pos/')) {
        return {
          statusCode: 403,
          statusDescription: 'Forbidden',
          headers: {
            'content-type': { value: 'text/plain; charset=utf-8' }
          },
          body: 'This route is not available on the public domain.'
        };
      }

      return request;
    }
  JSEOF
}

# ── Response Headers Policy ──────────────────────────────────────────────────
#
# Security headers applied to all CloudFront responses. Complements the
# CSP-Report-Only header set by the Next.js middleware.

resource "aws_cloudfront_response_headers_policy" "security" {
  name    = "${local.prefix}-security-headers"
  comment = "Security + caching headers for public distribution"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 63072000 # 2 years
      include_subdomains         = true
      preload                    = true
      override                   = true
    }

    content_type_options {
      override = true # X-Content-Type-Options: nosniff
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = false # let app override if needed
    }

    xss_protection {
      mode_block = true
      protection = true
      override   = true
    }
  }
}

# ── Cache Policies ───────────────────────────────────────────────────────────

# Marketing pages: short TTL, honour origin Cache-Control
resource "aws_cloudfront_cache_policy" "marketing" {
  name        = "${local.prefix}-marketing"
  comment     = "Marketing pages — short default TTL, respect origin headers"
  default_ttl = var.cloudfront_default_ttl
  max_ttl     = 86400  # 1 day max
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# Static assets: long TTL (files are fingerprinted by Next.js build)
resource "aws_cloudfront_cache_policy" "static_assets" {
  name        = "${local.prefix}-static-assets"
  comment     = "Immutable static assets — long cache"
  default_ttl = 31536000 # 1 year
  max_ttl     = 31536000
  min_ttl     = 86400    # at least 1 day

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# Blog listing: short TTL with query strings in cache key.
# The blog page uses ?page=N&categoria=slug for server-side pagination.
# Without query strings in the key, /blog?page=1 and /blog?page=2 would
# serve the same cached response.
resource "aws_cloudfront_cache_policy" "blog" {
  name        = "${local.prefix}-blog"
  comment     = "Blog pages — short TTL, query strings in cache key"
  default_ttl = var.cloudfront_default_ttl
  max_ttl     = 86400
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "whitelist"
      query_strings {
        items = ["page", "categoria"]
      }
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# ── Origin Request Policy (ALB) ─────────────────────────────────────────────
# Forward Host header so Next.js/Django can read the real hostname.

resource "aws_cloudfront_origin_request_policy" "alb_forward" {
  name    = "${local.prefix}-alb-forward"
  comment = "Forward Host + common headers to ALB origin"

  cookies_config {
    cookie_behavior = "all"
  }

  headers_config {
    header_behavior = "whitelist"
    headers {
      items = [
        "Host",
        "Origin",
        "Referer",
        "Accept",
        "Accept-Language",
        "CloudFront-Forwarded-Proto",
      ]
    }
  }

  query_strings_config {
    query_string_behavior = "all"
  }
}

# ── Distribution ─────────────────────────────────────────────────────────────

resource "aws_cloudfront_distribution" "public" {
  comment             = "${local.prefix} — public web distribution"
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = var.cloudfront_price_class
  aliases             = [local.fqdn_www, local.fqdn_apex]
  web_acl_id          = aws_wafv2_web_acl.public.arn
  default_root_object = ""

  # ── Origin 1: ALB (default — SSR + API) ──────────────────────────────────

  origin {
    domain_name = local.core.alb_dns_name
    origin_id   = "alb"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 30
    }
  }

  # ── Origin 2: S3 assets ─────────────────────────────────────────────────

  origin {
    domain_name              = aws_s3_bucket.assets.bucket_regional_domain_name
    origin_id                = "s3-assets"
    origin_access_control_id = aws_cloudfront_origin_access_control.assets.id
  }

  # ── Default behavior: ALB (marketing SSR) ──────────────────────────────────
  # Catches all paths not matched by ordered behaviors.
  # The edge_router function blocks /app/*, /admin/*, /pos/* with 403
  # and redirects apex → www.

  default_cache_behavior {
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = aws_cloudfront_cache_policy.marketing.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.alb_forward.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.edge_router.arn
    }
  }

  # ── Behavior: /m/* → ALB (public menus — force-dynamic, no cache) ───────

  ordered_cache_behavior {
    path_pattern             = "/m/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3" # AllViewer
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  # ── Behavior: /r/* → ALB (public reviews — no-store fetch, no cache) ────

  ordered_cache_behavior {
    path_pattern             = "/r/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3" # AllViewer
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  # ── Behavior: /q/* → ALB (QR redirect — API route, no cache) ───────────

  ordered_cache_behavior {
    path_pattern             = "/q/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3" # AllViewer
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  # ── Behavior: /blog* → ALB (listing + posts, query strings in key) ─────
  # Blog listing uses ?page=N&categoria=slug for server-side pagination.
  # Blog posts (/blog/[slug]) are SSG with generateStaticParams — they
  # benefit from the cache and don't use query strings.

  ordered_cache_behavior {
    path_pattern             = "/blog*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = aws_cloudfront_cache_policy.blog.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.alb_forward.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  # ── Behavior: /_next/static/* → ALB (immutable build output, long cache) ─

  ordered_cache_behavior {
    path_pattern             = "/_next/static/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = aws_cloudfront_cache_policy.static_assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  # ── Behavior: /assets/* → S3 (marketing static assets) ─────────────────

  ordered_cache_behavior {
    path_pattern             = "/assets/*"
    target_origin_id         = "s3-assets"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = aws_cloudfront_cache_policy.static_assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  # ── TLS ────────────────────────────────────────────────────────────────────

  viewer_certificate {
    acm_certificate_arn      = local.dns.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  # ── Geo restriction ────────────────────────────────────────────────────────

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  tags = { Name = "${local.prefix}-public-cdn" }
}
