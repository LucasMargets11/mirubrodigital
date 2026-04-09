# ═══════════════════════════════════════════════════════════════════════════════
# ACM Certificate + DNS Validation
# ═══════════════════════════════════════════════════════════════════════════════
#
# REGION: us-east-1 (same as all layers).
#   - ALB lives in us-east-1 (core/base) → cert is valid for the ALB HTTPS listener.
#   - CloudFront requires certs in us-east-1 → same cert works for public-cdn.
#   → One certificate serves both consumers. No need for a second regional cert.
#
# Single certificate covering mirubro.com + www.mirubro.com + api.mirubro.com.
# Validated automatically via Route 53 DNS records.
#
# Consumers:
#   1. core/alb.tf HTTPS listener (uncomment after cert is ISSUED)
#   2. public-cdn CloudFront viewer certificate
#
# ── Apply in two phases ──────────────────────────────────────────────────────
#
# Phase A — first apply (can run immediately after core/base + private-app):
#   terraform apply creates:
#     - Route 53 hosted zone (route53.tf)
#     - ACM certificate request
#     - DNS validation CNAME records inside the new zone
#   BUT aws_acm_certificate_validation will BLOCK because the zone's
#   nameservers are not yet authoritative (Hostinger still points elsewhere).
#   → Ctrl+C is safe. Re-run apply after the manual step below.
#
# Phase B — after NS migration:
#   1. Copy the 4 NS records from `terraform output zone_name_servers`
#   2. Replace Hostinger's default nameservers with those 4 values
#   3. Wait for propagation (typically 15 min–2 h, worst case 48 h):
#      dig +short NS mirubro.com  # should return the Route 53 NS
#   4. Re-run: terraform apply
#      → aws_acm_certificate_validation completes, cert status → ISSUED
#   5. Copy `terraform output acm_certificate_arn` → uncomment HTTPS
#      listener in core/alb.tf, paste ARN, terraform apply on core.
# ═══════════════════════════════════════════════════════════════════════════════

resource "aws_acm_certificate" "main" {
  domain_name               = var.domain_name            # mirubro.com
  subject_alternative_names = [
    "www.${var.domain_name}",                            # www.mirubro.com
    "api.${var.domain_name}",                            # api.mirubro.com
  ]
  validation_method = "DNS"

  tags = { Name = "${var.project_name}-${var.environment}-cert" }

  lifecycle { create_before_destroy = true }
}

# ── Validation DNS records ───────────────────────────────────────────────────
# ACM creates one CNAME per unique validation token. For SANs under the same
# zone, AWS often reuses the same token, but we handle the general case with
# distinct_domain_names.

resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id         = aws_route53_zone.main.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 300
  allow_overwrite = true
}

# ── Wait for validation ─────────────────────────────────────────────────────
# Blocks until ACM confirms the certificate is ISSUED.
# Requires nameservers to already be pointed to Route 53.

resource "aws_acm_certificate_validation" "main" {
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
}
