# ═══════════════════════════════════════════════════════════════════════════════
# Public CDN & Distribution — Variables
# ═══════════════════════════════════════════════════════════════════════════════

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
  default     = "staging"
}

variable "project_name" {
  description = "Project identifier used in resource naming"
  type        = string
  default     = "mirubro"
}

variable "domain_name" {
  description = "Root domain name (e.g. mirubro.com)"
  type        = string
  default     = "mirubro.com"
}

variable "canonical_subdomain" {
  description = "Canonical subdomain (e.g. www)"
  type        = string
  default     = "www"
}

# ── CloudFront ───────────────────────────────────────────────────────────────

variable "cloudfront_price_class" {
  description = "CloudFront price class (PriceClass_100 = NA+EU, PriceClass_200 = +Asia, PriceClass_All)"
  type        = string
  default     = "PriceClass_100"
}

variable "cloudfront_default_ttl" {
  description = "Default TTL in seconds for cacheable responses (marketing pages)"
  type        = number
  default     = 300 # 5 minutes
}

# ── WAF ──────────────────────────────────────────────────────────────────────

variable "waf_rate_limit_global" {
  description = "Global rate limit per IP per 5 minutes for public distribution"
  type        = number
  default     = 1000
}

variable "waf_rate_limit_menu" {
  description = "Rate limit per IP per 5 minutes for /m/* (public menus)"
  type        = number
  default     = 200
}
