# ═══════════════════════════════════════════════════════════════════════════════
# Public DNS & Certificates — Variables
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
  description = "Canonical subdomain (e.g. www). Apex will 301 redirect to this."
  type        = string
  default     = "www"
}
