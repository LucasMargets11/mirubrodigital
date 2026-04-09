# ═══════════════════════════════════════════════════════════════════════════════
# Private Application Layer — Variables
# ═══════════════════════════════════════════════════════════════════════════════

# ── General ──────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region for all resources"
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

# ── Container Images ─────────────────────────────────────────────────────────

variable "api_image" {
  description = "Full ECR image URI for Django API"
  type        = string
}

variable "web_image" {
  description = "Full ECR image URI for Next.js Web"
  type        = string
}

# ── ECS Task Sizing ──────────────────────────────────────────────────────────

variable "api_cpu" {
  description = "CPU units for API task (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Memory in MiB for API task"
  type        = number
  default     = 512
}

variable "web_cpu" {
  description = "CPU units for Web task"
  type        = number
  default     = 256
}

variable "web_memory" {
  description = "Memory in MiB for Web task"
  type        = number
  default     = 512
}

variable "celery_worker_cpu" {
  description = "CPU units for Celery worker task"
  type        = number
  default     = 256
}

variable "celery_worker_memory" {
  description = "Memory in MiB for Celery worker task"
  type        = number
  default     = 512
}

variable "celery_beat_cpu" {
  description = "CPU units for Celery beat task"
  type        = number
  default     = 256
}

variable "celery_beat_memory" {
  description = "Memory in MiB for Celery beat task"
  type        = number
  default     = 256
}

# ── ECS Service Scaling ─────────────────────────────────────────────────────

variable "api_desired_count" {
  description = "Desired number of API task instances"
  type        = number
  default     = 1
}

variable "web_desired_count" {
  description = "Desired number of Web task instances"
  type        = number
  default     = 1
}

variable "celery_worker_desired_count" {
  description = "Desired number of Celery worker task instances"
  type        = number
  default     = 1
}

# ── Auto Scaling Limits ─────────────────────────────────────────────────────

variable "api_min_count" {
  description = "Minimum API task count for auto-scaling"
  type        = number
  default     = 1
}

variable "api_max_count" {
  description = "Maximum API task count for auto-scaling"
  type        = number
  default     = 3
}

variable "web_min_count" {
  description = "Minimum Web task count for auto-scaling"
  type        = number
  default     = 1
}

variable "web_max_count" {
  description = "Maximum Web task count for auto-scaling"
  type        = number
  default     = 3
}

# ── Secrets (stored in Secrets Manager, injected into tasks) ─────────────────

variable "django_secret_key" {
  description = "Django SECRET_KEY"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "PostgreSQL master username (plain env var, not a secret)"
  type        = string
  default     = "mirubro"
}

variable "mfa_encryption_key" {
  description = "Fernet key for MFA TOTP encryption"
  type        = string
  sensitive   = true
}

variable "mp_access_token" {
  description = "MercadoPago production access token"
  type        = string
  sensitive   = true
}

variable "mp_webhook_secret" {
  description = "MercadoPago webhook signature secret"
  type        = string
  sensitive   = true
}

# ── Application Config ───────────────────────────────────────────────────────

variable "django_allowed_hosts" {
  description = "Comma-separated list of allowed hosts for Django"
  type        = string
  default     = "api.mirubro.com,www.mirubro.com"
}

variable "cors_allowed_origins" {
  description = "Comma-separated list of CORS origins"
  type        = string
  default     = "https://www.mirubro.com"
}

variable "domain_name" {
  description = "Root domain (e.g. mirubro.com)"
  type        = string
  default     = "mirubro.com"
}

# ── CloudWatch ───────────────────────────────────────────────────────────────

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}
