# ═══════════════════════════════════════════════════════════════════════════════
# Core Infrastructure — Variables
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

# ── VPC / Networking ─────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs to use (2 minimum for ALB and multi-AZ services)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# ── RDS ──────────────────────────────────────────────────────────────────────

variable "rds_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ for RDS (recommended for production)"
  type        = bool
  default     = false
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "mirubro"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "mirubro"
}

variable "db_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

# ── ElastiCache ──────────────────────────────────────────────────────────────

variable "elasticache_node_type" {
  description = "ElastiCache node instance type"
  type        = string
  default     = "cache.t4g.micro"
}

# ── ECR ──────────────────────────────────────────────────────────────────────

variable "ecr_repo_names" {
  description = "ECR repository names to create"
  type        = list(string)
  default     = ["mirubro-api", "mirubro-web", "mirubro-celery-worker", "mirubro-celery-beat"]
}

# ── Domain (informational, used in ALB naming) ───────────────────────────────

variable "domain_name" {
  description = "Root domain (e.g. mirubro.com). Informational in core layer."
  type        = string
  default     = "mirubro.com"
}
