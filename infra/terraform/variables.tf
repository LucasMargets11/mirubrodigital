variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project identifier used in resource naming"
  type        = string
  default     = "mirubro"
}

# ── ALB ──────────────────────────────────────────────────────────────────────

variable "alb_arn" {
  description = "ARN of the existing ALB to attach WAF WebACL to"
  type        = string
}

# ── ElastiCache ──────────────────────────────────────────────────────────────

variable "vpc_id" {
  description = "VPC ID for ElastiCache subnet group and security group"
  type        = string
}

variable "elasticache_subnet_ids" {
  description = "Private subnet IDs for ElastiCache cluster"
  type        = list(string)
}

variable "app_security_group_id" {
  description = "Security group ID of the ECS tasks / EC2 instances that will connect to ElastiCache"
  type        = string
}

variable "elasticache_node_type" {
  description = "ElastiCache node instance type"
  type        = string
  default     = "cache.t4g.micro"
}

# ── Secrets Manager ──────────────────────────────────────────────────────────

variable "mfa_encryption_key" {
  description = "Fernet key for MFA secret encryption (generated via: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  type        = string
  sensitive   = true
}

variable "ecs_task_execution_role_arn" {
  description = "ARN of the ECS task execution role that needs access to read secrets"
  type        = string
  default     = ""
}
