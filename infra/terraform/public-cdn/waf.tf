# ═══════════════════════════════════════════════════════════════════════════════
# WAF v2 — CloudFront Scope
# ═══════════════════════════════════════════════════════════════════════════════
#
# Protects the public CloudFront distribution with:
#   1. AWS Managed Common Rule Set (OWASP Top 10)
#   2. AWS Known Bad Inputs rule set
#   3. Global rate limit per IP
#   4. Stricter rate limit for /m/* (public QR menus — high-traffic, low-auth)
#
# IMPORTANT: WAF for CloudFront MUST be created in us-east-1. This layer
# already runs in us-east-1 so no extra provider is needed.

resource "aws_wafv2_web_acl" "public" {
  name        = "${local.prefix}-public-waf"
  description = "WAF for public CloudFront distribution"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # ── Rule 1: AWS Common Rule Set (SQLi, XSS, etc.) ─────────────────────────

  rule {
    name     = "aws-common-rules"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-common-rules"
    }
  }

  # ── Rule 2: Known Bad Inputs (Log4j, etc.) ─────────────────────────────────

  rule {
    name     = "aws-known-bad-inputs"
    priority = 20

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-bad-inputs"
    }
  }

  # ── Rule 3: Global rate limit ──────────────────────────────────────────────

  rule {
    name     = "rate-limit-global"
    priority = 30

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit_global
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-rate-global"
    }
  }

  # ── Rule 4: Stricter rate limit for /m/* (public QR menus) ─────────────────

  rule {
    name     = "rate-limit-menu"
    priority = 40

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit_menu
        aggregate_key_type = "IP"

        scope_down_statement {
          byte_match_statement {
            search_string         = "/m/"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
            positional_constraint = "STARTS_WITH"
          }
        }
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-rate-menu"
    }
  }

  visibility_config {
    sampled_requests_enabled   = true
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.prefix}-public-waf"
  }

  tags = { Name = "${local.prefix}-public-waf" }
}
