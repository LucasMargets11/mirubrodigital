# ── WAF ──────────────────────────────────────────────────────────────────────

output "waf_web_acl_arn" {
  description = "ARN of the WAF WebACL attached to the ALB"
  value       = aws_wafv2_web_acl.admin.arn
}

output "waf_log_group" {
  description = "CloudWatch Log Group for WAF logs"
  value       = aws_cloudwatch_log_group.waf.name
}

# ── ElastiCache ──────────────────────────────────────────────────────────────

output "elasticache_endpoint" {
  description = "Primary endpoint for ElastiCache (use as CACHE_REDIS_URL with rediss:// scheme)"
  value       = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/1"
}

output "celery_broker_url" {
  description = "Celery broker URL (ElastiCache, db 0)"
  value       = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
}

# ── Secrets Manager ──────────────────────────────────────────────────────────

output "mfa_key_secret_arn" {
  description = "ARN of the MFA encryption key secret (use in ECS task definition valueFrom)"
  value       = aws_secretsmanager_secret.mfa_key.arn
}

output "django_secret_key_arn" {
  description = "ARN of the Django SECRET_KEY secret"
  value       = aws_secretsmanager_secret.django_secret_key.arn
}

output "db_credentials_secret_arn" {
  description = "ARN of the DB credentials secret"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "secrets_read_policy_arn" {
  description = "IAM policy ARN to attach to ECS task execution role for reading secrets"
  value       = aws_iam_policy.secrets_read.arn
}
