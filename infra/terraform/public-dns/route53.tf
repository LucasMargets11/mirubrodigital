# ═══════════════════════════════════════════════════════════════════════════════
# Route 53 Hosted Zone + DNS Records
# ═══════════════════════════════════════════════════════════════════════════════
#
# Creates the hosted zone for mirubro.com and an A alias record for
# api.mirubro.com → ALB. The www and apex records are created by public-cdn
# (they will point to CloudFront, not directly to the ALB).

locals {
  core = data.terraform_remote_state.core.outputs
}

# ── Hosted Zone ──────────────────────────────────────────────────────────────

resource "aws_route53_zone" "main" {
  name    = var.domain_name
  comment = "${var.project_name} ${var.environment} — managed by Terraform"

  tags = { Name = "${var.project_name}-${var.environment}-zone" }
}

# ── API subdomain → ALB ─────────────────────────────────────────────────────
# api.mirubro.com always goes directly to the ALB (not through CloudFront).

resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = local.core.alb_dns_name
    zone_id                = local.core.alb_zone_id
    evaluate_target_health = true
  }
}
