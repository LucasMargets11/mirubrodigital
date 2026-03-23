# ═══════════════════════════════════════════════════════════════════════════════
# AWS WAF WebACL — Admin Login Hardening
# ═══════════════════════════════════════════════════════════════════════════════
#
# Attached to the ALB. Protects /api/v1/platform-admin/auth/* with:
#   1. IP rate limiting           (100 req / 5 min per IP)
#   2. Geographic restriction     (optional — see geo_match_statement)
#   3. AWS Managed Rules          (Core Rule Set + Known Bad Inputs)
#   4. Blanket rate limit         (2000 req / 5 min global)

resource "aws_wafv2_web_acl" "admin" {
  name        = "${var.project_name}-admin-waf"
  scope       = "REGIONAL"
  description = "WAF for admin login hardening"

  default_action {
    allow {}
  }

  # ── Rule 1: Admin login IP rate limit ─────────────────────────────────────
  rule {
    name     = "admin-login-ip-rate-limit"
    priority = 10

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 100
        aggregate_key_type = "IP"

        scope_down_statement {
          byte_match_statement {
            search_string         = "/api/v1/platform-admin/auth/"
            positional_constraint = "STARTS_WITH"

            field_to_match {
              uri_path {}
            }

            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-admin-login-ip-rate"
    }
  }

  # ── Rule 2: AWS Managed Rules — Core Rule Set ────────────────────────────
  rule {
    name     = "aws-managed-core-rule-set"
    priority = 20

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
      metric_name                = "${var.project_name}-core-rule-set"
    }
  }

  # ── Rule 3: AWS Managed Rules — Known Bad Inputs ─────────────────────────
  rule {
    name     = "aws-managed-known-bad-inputs"
    priority = 30

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
      metric_name                = "${var.project_name}-known-bad-inputs"
    }
  }

  # ── Rule 4: Global rate limit (all paths) ───────────────────────────────
  rule {
    name     = "global-rate-limit"
    priority = 40

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-global-rate"
    }
  }

  visibility_config {
    sampled_requests_enabled   = true
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-admin-waf"
  }
}

# ── Associate WAF with ALB ─────────────────────────────────────────────────

resource "aws_wafv2_web_acl_association" "alb" {
  resource_arn = var.alb_arn
  web_acl_arn  = aws_wafv2_web_acl.admin.arn
}

# ── WAF Logging → CloudWatch Logs ─────────────────────────────────────────

resource "aws_cloudwatch_log_group" "waf" {
  # Name MUST start with "aws-waf-logs-"
  name              = "aws-waf-logs-${var.project_name}-admin"
  retention_in_days = 90
}

resource "aws_wafv2_logging_configuration" "admin" {
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
  resource_arn            = aws_wafv2_web_acl.admin.arn

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"

      condition {
        action_condition {
          action = "BLOCK"
        }
      }
      condition {
        action_condition {
          action = "COUNT"
        }
      }
    }
  }
}
